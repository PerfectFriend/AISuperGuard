"""
SuperGuard Alarm - Camera Subsystem

Abstract camera interface with implementations for:
- JPG cameras (HTTP snapshot fetch + cv2.imdecode)
- HLS/RTSP streams (cv2.VideoCapture)

Architecture:
- BaseCamera: Abstract base with thread-safe frame storage and capture loop
- JPGCamera: Fetches static images via HTTP GET (MJPEG, snapshots, JPG URLs)
- HLSCamera: Opens cv2.VideoCapture for HLS (.m3u8) or RTSP streams
- CameraManager: Owns all cameras, tracks active camera, provides factory

Key features:
- Frame deduplication via content hash (avoids redundant processing)
- Thread-safe frame access (lock-protected)
- Automatic reconnection for streams
- 4K downscaling for YOLO (Cam2 Revotech 3840x2160 -> 1280px max)
- Daemon threads for background capture
"""

import cv2
import numpy as np
import threading
import time
import requests
from abc import ABC, abstractmethod
from typing import Optional, Dict
from dataclasses import dataclass, field

from ..config import CameraConfig, SuperGuardConfig


@dataclass
class FrameData:
    """Frame with metadata for tracking and deduplication.
    
    Attributes:
        image: BGR numpy array (OpenCV format)
        timestamp: Unix timestamp of capture
        camera_id: Source camera ID
        hash: Content hash (auto-computed from image bytes, used for dedup)
    """
    image: np.ndarray
    timestamp: float
    camera_id: int
    hash: int = field(init=False)
    
    def __post_init__(self):
        """Compute content hash for deduplication.
        
        Uses Python's built-in hash on raw bytes. Note: hash() is salted per-process
        so values aren't stable across runs, but that's fine for in-process dedup.
        """
        self.hash = hash(self.image.tobytes())


class BaseCamera(ABC):
    """Abstract base class for all camera types.
    
    Provides:
    - Thread-safe frame storage with hash-based deduplication
    - Background capture thread with configurable interval
    - Alive status tracking (True if recent frame received)
    - Clean start/stop lifecycle
    
    Subclasses must implement _fetch_frame() to retrieve a single frame.
    """
    
    def __init__(self, config: CameraConfig, update_interval: float):
        """Initialize camera.
        
        Args:
            config: CameraConfig with cam_id, name, url
            update_interval: Seconds between capture attempts
        """
        self.config = config
        self.cam_id = config.cam_id
        self.name = config.name
        self.url = config.url
        self.update_interval = update_interval
        
        self._lock = threading.Lock()
        self._latest_frame: Optional[FrameData] = None
        self._alive = False
        self._thread: Optional[threading.Thread] = None
        self._running = False
    
    @property
    def alive(self) -> bool:
        """True if camera has produced a frame recently (no errors)."""
        return self._alive
    
    @property
    def latest(self) -> Optional[np.ndarray]:
        """Get latest frame (thread-safe). Returns copy or None.
        
        Returns a COPY to prevent external modification of internal buffer.
        Caller owns the returned array.
        """
        with self._lock:
            if self._latest_frame is None:
                return None
            return self._latest_frame.image.copy()
    
    @property
    def latest_with_meta(self) -> Optional[FrameData]:
        """Get latest frame with metadata (timestamp, camera_id).
        
        Returns a new FrameData with copied image for thread safety.
        """
        with self._lock:
            if self._latest_frame is None:
                return None
            return FrameData(
                image=self._latest_frame.image.copy(),
                timestamp=self._latest_frame.timestamp,
                camera_id=self._latest_frame.camera_id,
            )
    
    def start(self):
        """Start frame capture thread.
        
        Idempotent - safe to call multiple times.
        Thread is daemon so it won't block process exit.
        """
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop frame capture thread.
        
        Waits up to 5 seconds for thread to finish.
        """
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
    
    @abstractmethod
    def _fetch_frame(self) -> Optional[np.ndarray]:
        """Fetch single frame. Implement in subclass.
        
        Returns:
            BGR numpy array or None on failure
        """
        pass
    
    def _run_loop(self):
        """Main capture loop - calls _fetch_frame at intervals.
        
        Implements:
        - Timing control (sleeps to maintain update_interval)
        - Hash-based deduplication (only stores frame if content changed)
        - Alive status updates
        - Exception handling (marks dead on any error)
        """
        while self._running:
            start = time.time()
            try:
                frame = self._fetch_frame()
                if frame is not None and frame.size > 0:
                    with self._lock:
                        # Only update if frame actually changed (hash dedup)
                        new_hash = hash(frame.tobytes())
                        if (self._latest_frame is None or 
                            self._latest_frame.hash != new_hash):
                            self._latest_frame = FrameData(
                                image=frame,
                                timestamp=time.time(),
                                camera_id=self.cam_id,
                            )
                            self._alive = True
                        else:
                            # Frame unchanged - still alive, timestamp not updated
                            self._alive = True
                else:
                    with self._lock:
                        self._alive = False
            except Exception as e:
                print(f"  [cam {self.cam_id}] Fetch error: {e}")
                with self._lock:
                    self._alive = False
            
            # Sleep to maintain update interval
            elapsed = time.time() - start
            sleep_time = max(0, self.update_interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)


class JPGCamera(BaseCamera):
    """Camera that fetches static JPG/JPEG/PNG images via HTTP.
    
    Suitable for:
    - Static snapshot URLs (traffic cams, webcams)
    - MJPEG streams (fetches single frame per interval)
    - Any HTTP endpoint returning image bytes
    
    Uses requests.Session for connection pooling and keep-alive.
    Sets User-Agent to avoid 403 from some servers.
    """
    
    def __init__(self, config: CameraConfig, update_interval: float, 
                 timeout: float = 10.0):
        """Initialize JPG camera.
        
        Args:
            config: CameraConfig with image URL
            update_interval: Seconds between fetches
            timeout: HTTP request timeout in seconds
        """
        super().__init__(config, update_interval)
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0'})
    
    def _fetch_frame(self) -> Optional[np.ndarray]:
        """Fetch single frame via HTTP GET.
        
        Returns:
            Decoded BGR frame or None on failure
        """
        resp = self.session.get(self.url, timeout=self.timeout, stream=True)
        if resp.status_code != 200 or not resp.content:
            return None
        
        img_array = np.frombuffer(resp.content, dtype=np.uint8)
        frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        return frame


class HLSCamera(BaseCamera):
    """Camera for HLS/RTSP streams using cv2.VideoCapture.
    
    Handles:
    - HLS (.m3u8) playlists
    - RTSP streams (TCP/UDP)
    - Automatic reconnection on stream failure
    - Low buffer size (1) for minimal latency
    
    For 4K cameras (Cam2 Revotech), provides get_downscaled_frame()
    to resize before YOLO inference (saves CPU/GPU).
    """
    
    def __init__(self, config: CameraConfig, update_interval: float,
                 reconnect_delay: float = 5.0):
        """Initialize stream camera.
        
        Args:
            config: CameraConfig with stream URL
            update_interval: Target frame interval (not guaranteed for streams)
            reconnect_delay: Seconds to wait before reconnection attempt
        """
        super().__init__(config, update_interval)
        self.reconnect_delay = reconnect_delay
        self._cap: Optional[cv2.VideoCapture] = None
    
    def _fetch_frame(self) -> Optional[np.ndarray]:
        """Read frame from VideoCapture with auto-reconnect.
        
        Flow:
        1. Ensure capture is open (connect if needed)
        2. Read frame
        3. On failure: release capture, return None (triggers reconnect next loop)
        
        Returns:
            BGR frame or None
        """
        # Ensure capture is open
        if self._cap is None or not self._cap.isOpened():
            self._connect()
            if self._cap is None or not self._cap.isOpened():
                return None
        
        ret, frame = self._cap.read()
        if not ret or frame is None:
            # Frame read failed - mark for reconnection
            self._cap.release()
            self._cap = None
            return None
        
        return frame
    
    def _connect(self):
        """Establish VideoCapture connection.
        
        Sets CAP_PROP_BUFFERSIZE=1 to minimize latency (drop old frames).
        Brief sleep allows stream to initialize.
        """
        try:
            self._cap = cv2.VideoCapture(self.url)
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            # Give it a moment to initialize
            time.sleep(0.5)
        except Exception as e:
            print(f"  [cam {self.cam_id}] HLS connect error: {e}")
            self._cap = None
    
    def get_downscaled_frame(self, max_width: int = 1280) -> Optional[np.ndarray]:
        """Get latest frame downscaled to max_width for YOLO processing.
        
        Essential for 4K cameras (3840x2160) - YOLO11n at 640px input
        would waste compute on full resolution. Downscaling preserves
        aspect ratio and keeps detection quality while being much faster.
        
        Args:
            max_width: Maximum width in pixels (default 1280)
            
        Returns:
            Downscaled BGR frame or None if no frame available
        """
        frame = self.latest
        if frame is None:
            return None
        h, w = frame.shape[:2]
        if w <= max_width:
            return frame
        scale = max_width / w
        new_w = max_width
        new_h = int(h * scale)
        return cv2.resize(frame, (new_w, new_h))
    
    def stop(self):
        """Stop capture and release VideoCapture resource."""
        super().stop()
        if self._cap:
            self._cap.release()
            self._cap = None


def create_camera(config: CameraConfig, update_interval: float) -> BaseCamera:
    """Factory: create appropriate camera type based on URL.
    
    Detection logic (URL-based heuristic):
    - Contains .jpg, .jpeg, .png, 'snapshot', 'image' -> JPGCamera
    - Otherwise (HLS .m3u8, RTSP) -> HLSCamera
    
    This is a simple heuristic; for complex cases, explicit type in config
    would be better but current approach works for known sources.
    
    Args:
        config: CameraConfig with URL
        update_interval: Capture interval seconds
        
    Returns:
        BaseCamera instance (JPGCamera or HLSCamera)
    """
    url_lower = config.url.lower()
    
    # JPG/JPEG/PNG or snapshot/image in URL -> JPG camera
    if any(ext in url_lower for ext in ['.jpg', '.jpeg', '.png', 'snapshot', 'image']):
        return JPGCamera(config, update_interval)
    
    # HLS (.m3u8) or RTSP -> stream camera
    return HLSCamera(config, update_interval)


class CameraManager:
    """Manages all cameras, tracks active camera.
    
    Owns camera instances, handles initialization and cleanup.
    Active camera is the one used for manual commands (/togglealarm, etc.)
    and can be switched via /cam command.
    """
    
    def __init__(self, config: SuperGuardConfig):
        """Initialize all cameras from config.
        
        Args:
            config: SuperGuardConfig with cameras dict and detection params
        """
        self.config = config
        self.cameras: Dict[int, BaseCamera] = {}
        self.active_id = 1
        self._init_all()
    
    def _init_all(self):
        """Initialize all cameras from config.
        
        Creates camera instance via factory, starts capture thread.
        Skips cameras with empty URL.
        """
        for cam_id, cam_config in self.config.cameras.items():
            if cam_config.url:
                self.cameras[cam_id] = create_camera(
                    cam_config, self.config.detection.update_every
                )
                self.cameras[cam_id].start()
                print(f"  Initialized camera {cam_id}: {cam_config.name} ({cam_config.url})")
    
    def get_active(self) -> Optional[BaseCamera]:
        """Get currently active camera (for manual commands)."""
        return self.cameras.get(self.active_id)
    
    def set_active(self, cam_id: int) -> bool:
        """Switch active camera.
        
        Args:
            cam_id: Camera ID to make active
            
        Returns:
            True if camera exists and was set active
        """
        if cam_id in self.cameras:
            self.active_id = cam_id
            return True
        return False
    
    def get(self, cam_id: int) -> Optional[BaseCamera]:
        """Get camera by ID."""
        return self.cameras.get(cam_id)
    
    def list_status(self) -> Dict[int, Dict]:
        """Get status dict for all cameras (for UI/debug)."""
        return {
            cid: {"name": c.name, "alive": c.alive, "url": c.url}
            for cid, c in self.cameras.items()
        }
    
    def stop_all(self):
        """Stop all cameras (cleanup on shutdown)."""
        for cam in self.cameras.values():
            cam.stop()