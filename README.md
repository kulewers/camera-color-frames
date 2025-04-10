
# Camera Color Frames FastAPI Server

This server receives video frames from the frontend, processes them by overlaying a rectangle with the average color, and sends the processed frames back via WebSocket.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the server:
```bash
python server.py
```

The server will start on `http://localhost:8000` and the WebSocket endpoint will be available at `ws://localhost:8000/`.

## Frontend

1. cd into directory:
```bash
cd frontend
```

2. Install required packages:
```bash
npm install
```

3. Run the server;
```bash
npm run dev
```

## API Endpoints

- `GET /`: Returns a simple status message
- `WebSocket /`: WebSocket endpoint for video processing

## WebSocket Protocol

### Messages from Client to Server:

```json
{
  "type": "frame",
  "payload": {
    "data": "base64-encoded-image-data",
    "avgColor": { "r": 255, "g": 0, "b": 0 }
  }
}
```

### Messages from Server to Client:

```json
{
  "type": "processed",
  "payload": {
    "data": "base64-encoded-processed-image-data",
    "avgColor": { "r": 255, "g": 0, "b": 0 }
  }
}
```

In case of errors:

```json
{
  "type": "error",
  "payload": "Error message"
}
```