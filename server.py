
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import json
import base64
import cv2
import numpy as np
import uvicorn

app = FastAPI()

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
