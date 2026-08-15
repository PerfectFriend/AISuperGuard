"""
SuperGuard Core - Webcam Camera Plugin

Local webcam/USB camera support using OpenCV.
"""

import asyncio
import logging
from typing import List, Optional

import cv2
import numpy as np

from superguard_core.core.plugins import CameraPlugin, CameraFrame, DiscoveredCamera, PluginConfig
from superguard_core.core.database import Camera


logger = logging.getLogger(__name__)


class WebcamCameraPlugin(CameraPlugin):
    """Local webcam/USB camera plugin using OpenCV."""
    
    name = "webcam"
    version = "1.0.0"
    plugin_type = "camera"
    description = "Local USB/MIPI webcam support"
    author = "SuperGuard Team"
    
    def __init__(self, config: PluginConfig, event_bus):
        super().__init__(config, event_bus)
        self._camera: Optional[Camera] = None
        self._cap: Optional[cv2.VideoCapture] = None
        self._device_index: int = 0
    
    async def initialize(self) -> None:
        """Initialize plugin."""
        await self._set_status(self.PluginStatus.LOADED)
        self._initialized = True
    
    async def connect(self, camera: Camera) -> None:
        """Connect to local webcam."""
        self._camera = camera
        
        # Get device index from config or URL
        self._device_index = camera.config.get("device_index", 0) if camera.config else 0
        
        # Try to parse from URL if it's like "webcam://0"
        if camera.url.startswith("webcam://"):
            try:
                self._device_index = int(camera.url.replace("webcam://", ""))
            except:
                pass
        
        logger.info(f"Connecting to webcam {camera.id} at device index {self._device_index}")
        
        # Open webcam
        self._cap = cv2.VideoCapture(self._device_index)
        
        if not self._cap.isOpened():
            raise ConnectionError(f"Failed to open webcam at index {self._device_index}")
        
        # Set properties from config
        if camera.config:
            if "width" in camera.config:
                self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, camera.config["width"])
            if "height" in camera.config:
                self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, camera.config["height"])
            if "fps" in camera.config:
                self._cap.set(cv2.CAP_PROP_FPS, camera.config["fps"])
            if "fourcc" in camera.config:
                fourcc = cv2.VideoWriter_fourcc(*camera.config["fourcc"])
                self._cap.set(cv2.CAP_PROP_FOURCC, fourcc)
        
        # Get actual properties
        width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = self._cap.get(cv2.CAP_PROP_FPS)
        
        # Update camera with detected resolution
        if width > 0 and height > 0:
            from superguard_core.core.database import get_session_factory
            factory = get_session_factory()
            if factory:
                async with factory() as session:
                    from sqlalchemy import update
                    await session.execute(
                        update(Camera)
                        .where(Camera.id == camera.id)
                        .values(width=width, height=height, fps=fps if fps > 0 else None)
                    )
                    await session.commit()
        
        logger.info(f"Webcam {camera.id} connected: {width}x{height} @ {fps}fps")
    
    async def disconnect(self) -> None:
        """Disconnect from webcam."""
        if self._cap:
            self._cap.release()
            self._cap = None
        
        logger.info(f"Webcam {self._camera.id if self._camera else 'unknown'} disconnected")
    
    async def read_frame(self) -> Optional[CameraFrame]:
        """Read frame from webcam."""
        if not self._cap or not self._cap.isOpened():
            return None
        
        ret, frame = self._cap.read()
        
        if not ret or frame is None:
            return None
        
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        return CameraFrame(
            image=frame_rgb,
            timestamp=asyncio.get_event_loop().time(),
            camera_id=self._camera.id if self._camera else 0,
            metadata={
                "source": "webcam",
                "width": frame.shape[1],
                "height": frame.shape[0],
                "device_index": self._device_index,
            }
        )
    
    async def get_snapshot(self) -> Optional[CameraFrame]:
        """Get single snapshot."""
        return await self.read_frame()
    
    async def ptz_control(self, command: str, **kwargs) -> bool:
        """PTZ control (not supported for webcam)."""
        return False
    
    @classmethod
    async def discover(cls, timeout: int = 10) -> List[DiscoveredCamera]:
        """Discover local webcams."""
        discovered = []
        
        # Try indices 0-9
        for i in range(10):
            try:
                cap = cv2.VideoCapture(i)
                if cap.isOpened():
                    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    cap.release()
                    
                    discovered.append(DiscoveredCamera(
                        name=f"Webcam {i}",
                        url=f"webcam://{i}",
                        type="webcam",
                        extra={
                            "device_index": i,
                            "width": width,
                            "height": height,
                            "fps": fps,
                        }
                    ))
            except Exception:
                pass
        
        return discovered
    
    async def shutdown(self) -> None:
        """Shutdown plugin."""
        await self.disconnect()
        await self._set_status(self.PluginStatus.UNLOADED)