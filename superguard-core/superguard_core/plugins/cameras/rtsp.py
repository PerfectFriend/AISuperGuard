"""
SuperGuard Core - RTSP Camera Plugin

RTSP camera support using OpenCV.
"""

import asyncio
import logging
from typing import List, Optional

import cv2
import numpy as np

from superguard_core.core.plugins import CameraPlugin, CameraFrame, DiscoveredCamera, PluginConfig
from superguard_core.core.database import Camera


logger = logging.getLogger(__name__)


class RtspCameraPlugin(CameraPlugin):
    """RTSP camera plugin using OpenCV VideoCapture."""
    
    name = "rtsp"
    version = "1.0.0"
    plugin_type = "camera"
    description = "RTSP camera support via OpenCV"
    author = "SuperGuard Team"
    
    def __init__(self, config: PluginConfig, event_bus):
        super().__init__(config, event_bus)
        self._cap: Optional[cv2.VideoCapture] = None
        self._camera: Optional[Camera] = None
        self._reconnect_task: Optional[asyncio.Task] = None
    
    async def initialize(self) -> None:
        """Initialize plugin."""
        await self._set_status(self.PluginStatus.LOADED)
        self._initialized = True
    
    async def connect(self, camera: Camera) -> None:
        """Connect to RTSP camera."""
        self._camera = camera
        
        # Build RTSP URL with credentials
        url = camera.url
        if camera.username and camera.password and "@" not in url:
            # Insert credentials into URL
            if url.startswith("rtsp://"):
                url = url.replace("rtsp://", f"rtsp://{camera.username}:{camera.password}@")
        
        logger.info(f"Connecting to RTSP camera {camera.id}: {url}")
        
        # Create VideoCapture
        self._cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        
        # Set buffer size to minimize latency
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        # Try to open
        if not self._cap.isOpened():
            raise ConnectionError(f"Failed to open RTSP stream: {url}")
        
        # Get stream properties
        width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = self._cap.get(cv2.CAP_PROP_FPS)
        
        if width > 0 and height > 0:
            # Update camera with detected resolution
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
        
        logger.info(f"RTSP camera {camera.id} connected: {width}x{height} @ {fps}fps")
    
    async def disconnect(self) -> None:
        """Disconnect from camera."""
        if self._cap:
            self._cap.release()
            self._cap = None
        
        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
        
        logger.info(f"RTSP camera {self._camera.id if self._camera else 'unknown'} disconnected")
    
    async def read_frame(self) -> Optional[CameraFrame]:
        """Read frame from camera."""
        if not self._cap or not self._cap.isOpened():
            return None
        
        # Read frame (non-blocking)
        ret, frame = self._cap.read()
        
        if not ret or frame is None:
            # Try to reconnect
            await self._schedule_reconnect()
            return None
        
        # Convert BGR to RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        return CameraFrame(
            image=frame_rgb,
            timestamp=asyncio.get_event_loop().time(),
            camera_id=self._camera.id if self._camera else 0,
            metadata={
                "source": "rtsp",
                "width": frame.shape[1],
                "height": frame.shape[0],
            }
        )
    
    async def get_snapshot(self) -> Optional[CameraFrame]:
        """Get single snapshot."""
        return await self.read_frame()
    
    async def ptz_control(self, command: str, **kwargs) -> bool:
        """PTZ control (not supported for generic RTSP)."""
        logger.warning(f"PTZ control not supported for RTSP camera: {command}")
        return False
    
    @classmethod
    async def discover(cls, timeout: int = 10) -> List[DiscoveredCamera]:
        """Discover RTSP cameras (not implemented for generic RTSP)."""
        # RTSP cameras typically don't announce themselves
        # This would need ONVIF discovery instead
        return []
    
    async def _schedule_reconnect(self) -> None:
        """Schedule reconnection attempt."""
        if self._reconnect_task and not self._reconnect_task.done():
            return
        
        self._reconnect_task = asyncio.create_task(self._reconnect())
    
    async def _reconnect(self) -> None:
        """Attempt to reconnect to camera."""
        if not self._camera:
            return
        
        logger.info(f"Attempting to reconnect RTSP camera {self._camera.id}...")
        
        for attempt in range(5):
            try:
                await asyncio.sleep(2 ** attempt)
                
                if self._cap:
                    self._cap.release()
                
                url = self._camera.url
                if self._camera.username and self._camera.password and "@" not in url:
                    if url.startswith("rtsp://"):
                        url = url.replace("rtsp://", f"rtsp://{self._camera.username}:{self._camera.password}@")
                
                self._cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
                self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                
                if self._cap.isOpened():
                    logger.info(f"RTSP camera {self._camera.id} reconnected successfully")
                    return
                    
            except Exception as e:
                logger.warning(f"Reconnection attempt {attempt + 1} failed: {e}")
        
        logger.error(f"RTSP camera {self._camera.id} reconnection failed permanently")
    
    async def shutdown(self) -> None:
        """Shutdown plugin."""
        await self.disconnect()
        await self._set_status(self.PluginStatus.UNLOADED)