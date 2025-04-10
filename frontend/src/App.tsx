import './App.css';
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import React, { useRef, useEffect, useState } from "react";

interface RGB {
  r: number;
  g: number;
  b: number;
}

function calculateAverageColor(imageData: ImageData): RGB {
  const data = imageData.data;
  let r = 0, g = 0, b = 0;
  const pixelCount = data.length / 4;

  for (let i = 0; i < data.length; i += 4) {
    r += data[i];
    g += data[i + 1];
    b += data[i + 2];
  }

  return {
    r: Math.round(r / pixelCount),
    g: Math.round(g / pixelCount),
    b: Math.round(b / pixelCount)
  };
}


function App() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wsRef = useRef<WebSocket>(null);
  const intervalRef = useRef<number | null>(null);
  const [wsAddr, setWsAddr] = useState("ws://localhost:8000/");
  const [processedFrame, setProcessedFrame] = useState<string | null>(null);
  const processedFrameCanvasRef = useRef<HTMLCanvasElement>(null)

  const getVideo = async () => {
    try {
      const stream = await navigator.mediaDevices
        .getUserMedia({
          video: { width: 640, height: 360 }
        });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.play();
      }
    } catch (err) {
      console.error("Error accessing camera:", err)
    }
  }

  useEffect(() => {
    getVideo();
  }, [videoRef])

  useEffect(() => {
    intervalRef.current = window.setInterval(() => {
      const canvas = canvasRef.current;
      const video = videoRef.current;
      const ws = wsRef.current;

      if (canvas && video && ws?.readyState === WebSocket.OPEN) {
        const ctx = canvas.getContext('2d');
        if (!ctx) return;
        canvas.width = 640;
        canvas.height = 360;
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

        const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
        const avgColor = calculateAverageColor(imageData);

        const dataUrl = canvas.toDataURL("image/jpeg", 0.7);

        const message = {
          "type": "frame",
          "payload": {
            "data": dataUrl,
            "avgColor": avgColor,
          }
        };
        ws.send(JSON.stringify(message))
      }
    }, 20);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [wsRef])

  useEffect(() => {
    if (processedFrame && processedFrameCanvasRef.current) {
      const canvas = processedFrameCanvasRef.current;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      const img = new Image();
      img.onload = () => {
        canvas.width = img.width;
        canvas.height = img.height;
        ctx.drawImage(img, 0, 0);
      };

      img.src = processedFrame
    }
  }, [processedFrame])

  const handleConnectWS = () => {
    wsRef.current?.close();
    const ws = new WebSocket(wsAddr);
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type == 'processed') {
          console.log("Recieved processed frame");
          setProcessedFrame(data.payload.data);
        }
      } catch (err) {
        console.error(err);
      }
    }
    wsRef.current = ws;
  }

  return (
    <div className='App'>
      <div className="container mx-auto px-4 py-8 max-w-5xl">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold">Video Processing App</h1>
          <p className="text-muted-foreground mt-2">
            Capture video, compute average color, and overlay rectangle on server
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
          <Card>
            <CardContent className="p-6">
              <div className="video-container">
                <video ref={videoRef} className='w-full h-auto rounded-md bg-secondary/20'></video>
                <canvas ref={canvasRef} className='hidden'></canvas>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-6">
              <div className="video-container">
                <canvas className="w-full h-auto rounded-md bg-secondary/20 mb-4"
                  ref={processedFrameCanvasRef}
                ></canvas>
                  <Label htmlFor="wsaddr">WebSockets address:</Label>
                <div className='flex'>
                  <Input type="text" id='wsaddr' value={wsAddr} onChange={e => setWsAddr(e.target.value)} placeholder='ws://localhost:8000/' />
                  <Button onClick={handleConnectWS}>Connect</Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

      </div>
    </div>
  )
}

export default App
