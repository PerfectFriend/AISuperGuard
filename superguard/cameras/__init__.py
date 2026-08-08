"""
SuperGuard Alarm - Camera Subsystem

Abstract camera interface with implementations for:
- JPG cameras (HTTP snapshot fetch + cv2.imdecode)
- HLS/RTSP streams (cv2.VideoCapture)
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
    """Frame with metadata."""
    image: np.ndarray
    timestamp: float
    camera_id: int
    hash: int = field(init=False)
    
    def __post_init__(self):
        self.hash = hash(self.image.tobytes())


class BaseCamera(ABC):
    """Abstract base class for all camera types."""
    
    def __init__(self, config: CameraConfig, update_interval: float):
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
        return self._alive
    
    @property
    def latest(self) -> Optional[np.ndarray]:
        """Get latest frame (thread-safe). Returns copy or None."""
        with self._lock:
            if self._latest_frame is None:
                return None
            return self._latest_frame.image.copy()
    
    @property
    def latest_with_meta(self) -> Optional[FrameData]:
        """Get latest frame with metadata."""
        with self._lock:
            if self._latest_frame is None:
                return None
            return FrameData(
                image=self._latest_frame.image.copy(),
                timestamp=self._latest_frame.timestamp,
                camera_id=self._latest_frame.camera_id,
            )
    
    def start(self):
        """Start frame capture thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop frame capture thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
    
    @abstractmethod
    def _fetch_frame(self) -> Optional[np.ndarray]:
        """Fetch single frame. Implement in subclass."""
        pass
    
    def _run_loop(self):
        """Main capture loop - calls _fetch_frame at intervals."""
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
                            # Frame unchanged - still alive
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
    """Camera that fetches static JPG/JPEG images via HTTP."""
    
    def __init__(self, config: CameraConfig, update_interval: float, 
                 timeout: float = 10.0):
        super().__init__(config, update_interval)
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0'})
    
    def _fetch_frame(self) -> Optional[np.ndarray]:
        resp = self.session.get(self.url, timeout=self.timeout, stream=True)
        if resp.status_code != 200 or not resp.content:
            return None
        
        img_array = np.frombuffer(resp.content, dtype=np.uint8)
        frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        return frame


class HLSCamera(BaseCamera):
    """Camera for HLS/RTSP streams using cv2.VideoCapture."""
    
    def __init__(self, config: CameraConfig, update_interval: float,
                 reconnect_delay: float = 5.0):
        super().__init__(config, update_interval)
        self.reconnect_delay = reconnect_delay
        self._cap: Optional[cv2.VideoCapture] = None
    
    def _fetch_frame(self) -> Optional[np.ndarray]:
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
        """Establish VideoCapture connection."""
        try:
            self._cap = cv2.VideoCapture(self.url)
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            # Give it a moment to initialize
            time.sleep(0.5)
        except Exception as e:
            print(f"  [cam {self.cam_id}] HLS connect error: {e}")
            self._cap = None
    
    def stop(self):
        super().stop()
        if self._cap:
            self._cap.release()
            self._cap = None


def create_camera(config: CameraConfig, update_interval: float) -> BaseCamera:
    """Factory: create appropriate camera type based on URL."""
    url_lower = config.url.lower()
    
    # JPG/JPEG/PNG or snapshot/image in URL -> JPG camera
    if any(ext in url_lower for ext in ['.jpg', '.jpeg', '.png', 'snapshot', 'image']):
        return JPGCamera(config, update_interval)
    
    # HLS (.m3u8) or RTSP -> stream camera
    return HLSCamera(config, update_interval)


class CameraManager:
    """Manages all cameras, tracks active camera."""
    
    def __init__(self, config: SuperGuardConfig):
        self.config = config
        self.cameras: Dict[int, BaseCamera] = {}
        self.active_id = 1
        self._init_all()
    
    def _init_all(self):
        """Initialize all cameras from config."""
        for cam_id, cam_config in self.config.cameras.items():
            if cam_config.url:
                self.cameras[cam_id] = create_camera(
                    cam_config, self.config.detection.update_every
                )
                self.cameras[cam_id].start()
                print(f"  Initialized camera {cam_id}: {cam_config.name} ({cam_config.url})")
    
    def get_active(self) -> Optional[BaseCamera]:
        return self.cameras.get(self.active_id)
    
    def set_active(self, cam_id: int) -> bool:
        if cam_id in self.cameras:
            self.active_id = cam_id
            return True
        return False
    
    def get(self, cam_id: int) -> Optional[BaseCamera]:
        return self.cameras.get(cam_id)
    
    def list_status(self) -> Dict[int, Dict]:
        return {
            cid: {"name": c.name, "alive": c.alive, "url": c.url}
            for cid, c in self.cameras.items()
        }
    
    def stop_all(self):
        for cam in self.cameras.values():
            cam.stop()