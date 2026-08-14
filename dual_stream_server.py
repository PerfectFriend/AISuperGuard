#!/usr/bin/env python3
"""
Dual MJPEG Stream Server for SuperGuard Cameras
- Camera 1 (4K RTSP) -> http://localhost:8081/stream.mjpg (for viewing)
- Camera 2 (HLS) -> http://localhost:8082/stream.mjpg (for bot)
Also provides snapshots and info endpoints.
"""
import sys
import os
import cv2
import numpy as np
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

sys.path.insert(0, r'C:\SuperGuard')
from superguard.cameras import create_camera
from superguard.config import load_config

config = load_config(r'C:\SuperGuard\superguard')

# Global frame buffers
frames = {1: None, 2: None}
frame_locks = {1: threading.Lock(), 2: threading.Lock()}
running = True

def camera_loop(cam_id):
    global frames
    cam = create_camera(config.cameras[cam_id], config.detection.update_every)
    cam.start()
    print(f"Camera {cam_id} ({config.cameras[cam_id].name}) started")
    
    while running:
        frame = cam.latest
        if frame is not None:
            with frame_locks[cam_id]:
                frames[cam_id] = frame.copy()
        time.sleep(0.05)  # ~20 FPS max
    
    cam.stop()
    print(f"Camera {cam_id} loop stopped")

class MJPEGHandler(BaseHTTPRequestHandler):
    def __init__(self, cam_id, *args, **kwargs):
        self.cam_id = cam_id
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        if self.path == '/stream.mjpg' or self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            
            try:
                while running:
                    with frame_locks[self.cam_id]:
                        if frames[self.cam_id] is None:
                            time.sleep(0.1)
                            continue
                        frame = frames[self.cam_id].copy()
                    
                    # Resize for streaming if too large (browser performance)
                    h, w = frame.shape[:2]
                    if w > 1920:
                        scale = 1920 / w
                        new_w = 1920
                        new_h = int(h * scale)
                        frame = cv2.resize(frame, (new_w, new_h))
                    
                    ret, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    if not ret:
                        continue
                    
                    self.wfile.write(b'--frame\r\n')
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', str(len(buf)))
                    self.end_headers()
                    self.wfile.write(buf.tobytes())
                    self.wfile.write(b'\r\n')
                    time.sleep(0.05)  # ~20 FPS
            except (BrokenPipeError, ConnectionResetError):
                pass
        elif self.path == '/snapshot.jpg':
            with frame_locks[self.cam_id]:
                if frames[self.cam_id] is None:
                    self.send_response(503)
                    self.end_headers()
                    return
                frame = frames[self.cam_id].copy()
            
            ret, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if ret:
                self.send_response(200)
                self.send_header('Content-Type', 'image/jpeg')
                self.send_header('Content-Length', str(len(buf)))
                self.end_headers()
                self.wfile.write(buf.tobytes())
        elif self.path == '/info':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            import json
            with frame_locks[self.cam_id]:
                frame = frames[self.cam_id]
            if frame is not None:
                h, w = frame.shape[:2]
                info = {"camera_id": self.cam_id, "width": w, "height": h, "channels": frame.shape[2]}
            else:
                info = {"camera_id": self.cam_id, "status": "no frame yet"}
            self.wfile.write(json.dumps(info).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass

def make_handler(cam_id):
    class Handler(MJPEGHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(cam_id, *args, **kwargs)
    return Handler

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    pass

if __name__ == '__main__':
    # Start camera threads
    cam1_thread = threading.Thread(target=camera_loop, args=(1,), daemon=True)
    cam2_thread = threading.Thread(target=camera_loop, args=(2,), daemon=True)
    cam1_thread.start()
    cam2_thread.start()
    
    # Wait for first frames
    for cam_id in [1, 2]:
        while frames[cam_id] is None:
            time.sleep(0.5)
        h, w = frames[cam_id].shape[:2]
        print(f"Camera {cam_id} ready: {w}x{h}")
    
    # Start servers - swap ports so Cam2 (4K) is on 8081 for viewing
    server1 = ThreadingHTTPServer(('', 8081), make_handler(2))  # Cam2 (4K) on 8081
    server2 = ThreadingHTTPServer(('', 8082), make_handler(1))  # Cam1 (HLS) on 8082
    
    print("=" * 60)
    print("DUAL MJPEG STREAM SERVER RUNNING!")
    print("=" * 60)
    print("Camera 2 (4K Revotech) - Port 8081 (for viewing):")
    print("  http://localhost:8081          - MJPEG stream (live)")
    print("  http://localhost:8081/snapshot.jpg - Single JPEG snapshot")
    print("  http://localhost:8081/info       - Camera info JSON")
    print("")
    print("Camera 1 (HLS Indonesia) - Port 8082 (for bot):")
    print("  http://localhost:8082          - MJPEG stream (live)")
    print("  http://localhost:8082/snapshot.jpg - Single JPEG snapshot")
    print("  http://localhost:8082/info       - Camera info JSON")
    print("=" * 60)
    print("Press Ctrl+C to stop")
    
    # Run servers in threads
    server1_thread = threading.Thread(target=server1.serve_forever, daemon=True)
    server2_thread = threading.Thread(target=server2.serve_forever, daemon=True)
    server1_thread.start()
    server2_thread.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        running = False
        print("\nShutting down...")
        server1.shutdown()
        server2.shutdown()