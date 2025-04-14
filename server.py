from fastapi import FastAPI, WebSocket, Request
from fastapi.concurrency import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
import json
import base64
import cv2
import numpy as np
import uvicorn
import asyncio

from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaRelay
from av import VideoFrame
from abc import ABC, abstractmethod
from typing import Dict, Any

pcs = set()
relay = MediaRelay()


class AppConfig:
    def __init__(self, shape_type: str = "rectangle", size_factor: float = 0.3):
        self.shape_type = shape_type
        self.size_factor = size_factor


class ShapeDrawer(ABC):
    @abstractmethod
    def draw(self, img: np.ndarray, color: tuple, **kwargs) -> np.ndarray:
        pass


class RectangleDrawer(ShapeDrawer):
    def draw(self, img: np.ndarray, color: tuple, **kwargs) -> np.ndarray:
        height, width = img.shape[:2]
        size_factor = kwargs.get("size_factor", 0.3)

        rect_width = int(width * size_factor)
        rect_height = int(height * size_factor)
        x = (width - rect_width) // 2
        y = (height - rect_height) // 2

        cv2.rectangle(img, (x, y), (x + rect_width, y + rect_height), color, -1)
        return img


class CircleDrawer(ShapeDrawer):
    def draw(self, img: np.ndarray, color: tuple, **kwargs) -> np.ndarray:
        height, width = img.shape[:2]
        size_factor = kwargs.get("size_factor", 0.3)

        radius = int(min(width, height) * size_factor / 2)
        center_x = width // 2
        center_y = height // 2

        cv2.circle(img, (center_x, center_y), radius, color, -1)
        return img


class ShapeDrawerFactory:
    @staticmethod
    def create_drawer(shape_type: str) -> ShapeDrawer:
        if shape_type == "rectangle":
            return RectangleDrawer()
        elif shape_type == "circle":
            return CircleDrawer()
        else:
            raise ValueError(f"Unknown shape type: {shape_type}")


class VideoTransformTrack(MediaStreamTrack):
    kind = "video"

    def __init__(self, track, config: AppConfig):
        super().__init__()
        self.track = track
        self.drawer = ShapeDrawerFactory.create_drawer(config.shape_type)
        self.config = config
        self.color = (0, 0, 0)

    def set_color(self, color: Dict[str, int]):
        self.color = (color["b"], color["g"], color["r"])

    async def recv(self):
        frame = await self.track.recv()
        img = frame.to_ndarray(format="bgr24")

        img = self.drawer.draw(img, self.color, size_factor=self.config.size_factor)

        new_frame = VideoFrame.from_ndarray(img, format="bgr24")
        new_frame.pts = frame.pts
        new_frame.time_base = frame.time_base
        return new_frame


class FrameProcessor:
    def __init__(self, config: AppConfig):
        self.drawer = ShapeDrawerFactory.create_drawer(config.shape_type)
        self.config = config

    def process_frame(self, frame_data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            base64_image = (
                frame_data["data"].split(",")[1]
                if "," in frame_data["data"]
                else frame_data["data"]
            )
            avg_color = frame_data["avgColor"]

            img_data = base64.b64decode(base64_image)
            np_arr = np.frombuffer(img_data, np.uint8)
            img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            if img is None:
                raise ValueError("Failed to decode image")

            color = (avg_color["b"], avg_color["g"], avg_color["r"])
            img = self.drawer.draw(img, color, size_factor=self.config.size_factor)

            _, buffer = cv2.imencode(".jpg", img)
            encoded_image = base64.b64encode(buffer).decode("utf-8")

            return {
                "data": f"data:image/jpeg;base64,{encoded_image}",
                "avgColor": avg_color,
            }
        except Exception as e:
            print(f"Error processing frame: {e}")
            raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app_config = AppConfig(shape_type="circle")
frameProcessor = FrameProcessor(app_config)


@app.get("/")
async def root():
    return {"message": "Camera Color Frames", "status": "online"}


@app.websocket("/")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message["type"] == "frame":
                processed_frame = frameProcessor.process_frame(message["payload"])

                await websocket.send_text(
                    json.dumps({"type": "processed", "payload": processed_frame})
                )

    except Exception as e:
        print(f"Error: {e}")
        try:
            await websocket.send_text(json.dumps({"type": "error", "payload": str(e)}))
        except:
            pass


@app.post("/offer")
async def offer(request: Request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)

    video_transform_track = None

    @pc.on("datachannel")
    def on_datachannel(channel):
        @channel.on("message")
        def on_message(message):
            nonlocal video_transform_track
            if isinstance(message, str):
                try:
                    color = json.loads(message)
                    if video_transform_track:
                        video_transform_track.set_color(color)
                except Exception as e:
                    print(e)

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        if pc.connectionState == "failed":
            await pc.close()
            pcs.discard(pc)

    @pc.on("track")
    def on_track(track):
        nonlocal video_transform_track
        if track.kind == "video":
            video_transform_track = VideoTransformTrack(
                relay.subscribe(track), app_config
            )
            pc.addTrack(video_transform_track)

    await pc.setRemoteDescription(offer)

    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
