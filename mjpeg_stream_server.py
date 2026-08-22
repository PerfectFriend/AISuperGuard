#!/usr/bin/env python3
"""
MJPEG Stream Server for SuperGuard Camera 9
Run this and open http://localhost:8080 in browser
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

# Global frame buffer
latest_frame = None
frame_lock = threading.Lock()
running = True

def camera_loop():
    global latest_frame
    cam = create_camera(config.cameras[9], config.detection.update_every)
    cam.start()
    print("Camera started, waiting for frames...")
    
    while running:
        frame = cam.latest
        if frame is not None:
            with frame_lock:
                latest_frame = frame.copy()
        time.sleep(0.1)
    
    cam.stop()
    print("Camera loop stopped")

class MJPEGHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/stream.mjpg' or self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            
            try:
                while running:
                    with frame_lock:
                        if latest_frame is None:
                            time.sleep(0.1)
                            continue
                        frame = latest_frame.copy()
                    
                    # Encode to JPEG
                    ret, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    if not ret:
                        continue
                    
                    # Write multipart frame
                    self.wfile.write(b'--frame\r\n')
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', str(len(buf)))
                    self.end_headers()
                    self.wfile.write(buf.tobytes())
                    self.wfile.write(b'\r\n')
                    time.sleep(0.1)  # ~10 FPS
            except (BrokenPipeError, ConnectionResetError):
                pass
        elif self.path == '/snapshot.jpg':
            with frame_lock:
                if latest_frame is None:
                    self.send_response(503)
                    self.end_headers()
                    return
                frame = latest_frame.copy()
            
            ret, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if ret:
                self.send_response(200)
                self.send_header('Content-Type', 'image/jpeg')
                self.send_header('Content-Length', str(len(buf)))
                self.end_headers()
                self.wfile.write(buf.tobytes())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    pass

if __name__ == '__main__':
    # Start camera thread
    cam_thread = threading.Thread(target=camera_loop, daemon=True)
    cam_thread.start()
    
    # Wait for first frame
    while latest_frame is None:
        time.sleep(0.5)
    
    server = ThreadingHTTPServer(('', 8081), MJPEGHandler)
    print("=" * 50)
    print("MJPEG Stream Server Running!")
    print("=" * 50)
    print("Open in browser:")
    print("  http://localhost:8081          - MJPEG stream (live)")
    print("  http://localhost:8081/snapshot.jpg - Single JPEG snapshot")
    print("=" * 50)
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        running = False
        print("\nShutting down...")
        server.shutdown()