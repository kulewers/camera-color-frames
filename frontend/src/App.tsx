import './App.css';
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import React, { useRef, useEffect, useState } from "react";

enum StreamingMode {
  WebSockets,
  WebRTC
}

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
  const [webRTCAddr, setWebRTCAddr] = useState("http://localhost:8000/offer");
  const [processedFrame, setProcessedFrame] = useState<string | null>(null);
  const processedFrameCanvasRef = useRef<HTMLCanvasElement>(null)
  const processedFrameVideoRef = useRef<HTMLVideoElement>(null)
  const peerConnectionRef = useRef<RTCPeerConnection>(null);
  const [streamingMode, setStreamingMode] = useState<StreamingMode>(StreamingMode.WebSockets);
  const dcRef = useRef<RTCDataChannel>(null);
  const [avgColor, setAvgColor] = useState<RGB | null>(null);
  const [dcOpen, setDcOpen] = useState<boolean>(false);

  useEffect(() => {
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

    getVideo();
  }, [])

  useEffect(() => {
    intervalRef.current = window.setInterval(() => {
      const canvas = canvasRef.current;
      const video = videoRef.current;
      const ws = wsRef.current;

      if (canvas && video) {
        const ctx = canvas.getContext('2d');
        if (!ctx) return;
        canvas.width = 640;
        canvas.height = 360;
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

        const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
        const avgColor = calculateAverageColor(imageData);
        setAvgColor(avgColor);

        if (ws?.readyState === WebSocket.OPEN) {
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
      }
    }, 20);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [])

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
        } else if (data.type == 'error') {
          console.error(data.payload);
        }
      } catch (err) {
        console.error(err);
      }
    }
    wsRef.current = ws;
  }

  function createPeerConnection() {
    const config = {
      // iceServers: [
      //   { urls: 'stun:stun.l.google.com:19302' },
      // ],
    }

    const pc = new RTCPeerConnection(config);

    pc.addEventListener('track', (e) => {
      if (processedFrameVideoRef.current) {
        processedFrameVideoRef.current.srcObject = e.streams[0];
      }
    });

    return pc;
  }

  useEffect(() => {
    if (dcOpen) {
      if (dcRef.current) {
        dcRef.current.send(JSON.stringify(avgColor))
      }
    }
  }, [avgColor])

  const handleConnectWebRTC = () => {
    peerConnectionRef.current?.close();
    const pc = createPeerConnection();
    peerConnectionRef.current = pc;

    const dc = pc.createDataChannel('color', { "ordered": true });
    dc.addEventListener('close', () => {
      setDcOpen(false);
    })
    dc.addEventListener('open', () => {
      setDcOpen(true);
    })
    dcRef.current = dc;

    if (videoRef.current) {
      const stream = videoRef.current?.srcObject as MediaStream;
      if (stream) {
        const track = stream.getVideoTracks()[0];
        pc.addTrack(track, stream);
      }
    }
    negotiate();
  }

  const negotiate = async () => {
    const pc = peerConnectionRef.current;
    if (!pc) return;

    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);

    await new Promise<void>((resolve) => {
      if (pc.iceGatheringState === 'complete') {
        resolve();
      }
      const checkState = () => {
        if (pc.iceGatheringState === 'complete') {
          pc.removeEventListener('icegatheringstatechange', checkState);
          resolve();
        }
      };
      pc.addEventListener('icegatheringstatechange', checkState);
    });

    const response = await fetch(webRTCAddr, {
      body: JSON.stringify({
        sdp: offer?.sdp,
        type: offer?.type
      }),
      headers: {
        'Content-Type': 'application/json'
      },
      method: 'POST'
    });
    const answer = await response.json();
    pc.setRemoteDescription(answer);
  }

  const switchStreamingMode = () => {
    if (streamingMode == StreamingMode.WebRTC) {
      peerConnectionRef.current?.close();
      dcRef.current?.close();
      setStreamingMode(StreamingMode.WebSockets);
    } else {
      wsRef.current?.close();
      setStreamingMode(StreamingMode.WebRTC);
    }
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
              <div>
                <video ref={videoRef} className='w-full h-auto rounded-md bg-secondary/20'></video>
                <canvas ref={canvasRef} className='hidden'></canvas>
                {avgColor && (
                  <p>{`R:${avgColor.r} G:${avgColor.g} B:${avgColor.b}`}</p>
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-6">
              <div>
                {streamingMode == StreamingMode.WebSockets ? <>
                  <canvas className={`w-full h-auto rounded-md bg-secondary/20 ${streamingMode == StreamingMode.WebSockets ? "" : "hidden"}`}
                    ref={processedFrameCanvasRef}
                  ></canvas>

                  <Label htmlFor="wsaddr">WebSockets address:</Label>
                  <div className='flex mb-4'>
                    <Input type="text" id='wsaddr' value={wsAddr} onChange={e => setWsAddr(e.target.value)} placeholder='ws://localhost:8000/' />
                    <Button onClick={handleConnectWS}>Connect</Button>
                  </div>
                </> : ''
                }
                {streamingMode == StreamingMode.WebRTC ? <>
                  <video className={`w-full h-auto rounded-md bg-secondary/20 mb-4" ${streamingMode == StreamingMode.WebRTC ? "" : "hidden"}`}
                    autoPlay={true}
                    ref={processedFrameVideoRef}
                  ></video>

                  <Label htmlFor="wsaddr">WebRTC address:</Label>
                  <div className='flex mb-4'>
                    <Input type="text" id='webrtcaddr' value={webRTCAddr} onChange={e => setWebRTCAddr(e.target.value)} placeholder='http://localhost:8000/offer' />
                    <Button onClick={handleConnectWebRTC}>Connect</Button>
                  </div>
                </> : ''
                }
                <Button onClick={switchStreamingMode}>Switch streaming mode</Button>
              </div>
            </CardContent>
          </Card>
        </div>

      </div>
    </div>
  )
}

export default App
