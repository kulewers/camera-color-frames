
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

pcs = set()
relay = MediaRelay()


class VideoTransformTrack(MediaStreamTrack):
    """
    A video stream track that transforms frames from an another track.
    """

    kind = "video"

    def __init__(self, track):
        super().__init__()  # don't forget this!
        self.track = track

    def set_color(self, color):
        self.color = (color['b'], color['g'], color['r'])

    async def recv(self):
        frame = await self.track.recv()

        img = frame.to_ndarray(format="bgr24")

        height, width = img.shape[:2]

        rect_width = int(width * 0.3)
        rect_height = int(height * 0.3)

        x = (width - rect_width) // 2
        y = (height - rect_height) // 2

        cv2.rectangle(img, (x, y), (x + rect_width, y + rect_height), self.color, -1)

        new_frame = VideoFrame.from_ndarray(img, format="bgr24")
        new_frame.pts = frame.pts
        new_frame.time_base = frame.time_base
        return new_frame

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
                processed_frame = process_frame(message["payload"])
                
                await websocket.send_text(json.dumps({
                    "type": "processed",
                    "payload": processed_frame
                }))

    except Exception as e:
        print(f"Error: {e}")
        try:
            await websocket.send_text(json.dumps({
                "type": "error",
                "payload": str(e)
            }))
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
            video_transform_track = VideoTransformTrack(relay.subscribe(track))
            pc.addTrack(video_transform_track)

    await pc.setRemoteDescription(offer)

    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}

def process_frame(frame_data):
    try:
        # Extract the base64 image and average color
        base64_image = frame_data["data"].split(",")[1] if "," in frame_data["data"] else frame_data["data"]
        avg_color = frame_data["avgColor"]
        
        # Decode base64 to image
        img_data = base64.b64decode(base64_image)
        np_arr = np.frombuffer(img_data, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        
        if img is None:
            raise ValueError("Failed to decode image")
        
        # Get dimensions
        height, width = img.shape[:2]
        
        # Calculate rectangle dimensions (30% of width and height)
        rect_width = int(width * 0.3)
        rect_height = int(height * 0.3)
        
        # Calculate rectangle position (centered)
        x = (width - rect_width) // 2
        y = (height - rect_height) // 2
        
        # Draw filled rectangle with the average color
        color = (avg_color["b"], avg_color["g"], avg_color["r"])  # OpenCV uses BGR
        cv2.rectangle(img, (x, y), (x + rect_width, y + rect_height), color, -1)  # -1 thickness means filled
        
        # Convert back to base64 for sending
        _, buffer = cv2.imencode('.jpg', img)
        encoded_image = base64.b64encode(buffer).decode('utf-8')
        
        return {
            "data": f"data:image/jpeg;base64,{encoded_image}",
            "avgColor": avg_color
        }
    except Exception as e:
        print(f"Error processing frame: {e}")
        raise

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
