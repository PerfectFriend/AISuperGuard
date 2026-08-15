"""
SuperGuard Core - HLS Camera Plugin

HLS/DASH camera support using OpenCV.
"""

import asyncio
import logging
from typing import List, Optional

import cv2
import numpy as np

from superguard_core.core.plugins import CameraPlugin, CameraFrame, DiscoveredCamera, PluginConfig
from superguard_core.core.database import Camera


logger = logging.getLogger(__name__)


class HlsCameraPlugin(CameraPlugin):
    """HLS/DASH camera plugin using OpenCV VideoCapture."""
    
    name = "hls"
    version = "1.0.0"
    plugin_type = "camera"
    description = "HLS/DASH camera support via OpenCV"
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
        """Connect to HLS camera."""
        self._camera = camera
        
        url = camera.url
        logger.info(f"Connecting to HLS camera {camera.id}: {url}")
        
        # Create VideoCapture for HLS
        self._cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        
        # Set buffer size to minimize latency
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        # Set timeout options
        self._cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000)
        self._cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 15000)
        
        if not self._cap.isOpened():
            raise ConnectionError(f"Failed to open HLS stream: {url}")
        
        # Get stream properties
        width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = self._cap.get(cv2.CAP_PROP_FPS)
        
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
        
        logger.info(f"HLS camera {camera.id} connected: {width}x{height} @ {fps}fps")
    
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
        
        logger.info(f"HLS camera {self._camera.id if self._camera else 'unknown'} disconnected")
    
    async def read_frame(self) -> Optional[CameraFrame]:
        """Read frame from camera."""
        if not self._cap or not self._cap.isOpened():
            return None
        
        ret, frame = self._cap.read()
        
        if not ret or frame is None:
            await self._schedule_reconnect()
            return None
        
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        return CameraFrame(
            image=frame_rgb,
            timestamp=asyncio.get_event_loop().time(),
            camera_id=self._camera.id if self._camera else 0,
            metadata={
                "source": "hls",
                "width": frame.shape[1],
                "height": frame.shape[0],
            }
        )
    
    async def get_snapshot(self) -> Optional[CameraFrame]:
        """Get single snapshot."""
        return await self.read_frame()
    
    async def ptz_control(self, command: str, **kwargs) -> bool:
        """PTZ control (not supported for HLS)."""
        return False
    
    @classmethod
    async def discover(cls, timeout: int = 10) -> List[DiscoveredCamera]:
        """Discover HLS cameras (not implemented)."""
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
        
        logger.info(f"Attempting to reconnect HLS camera {self._camera.id}...")
        
        for attempt in range(5):
            try:
                await asyncio.sleep(2 ** attempt)
                
                if self._cap:
                    self._cap.release()
                
                self._cap = cv2.VideoCapture(self._camera.url, cv2.CAP_FFMPEG)
                self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                self._cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000)
                self._cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 15000)
                
                if self._cap.isOpened():
                    logger.info(f"HLS camera {self._camera.id} reconnected successfully")
                    return
                    
            except Exception as e:
                logger.warning(f"Reconnection attempt {attempt + 1} failed: {e}")
        
        logger.error(f"HLS camera {self._camera.id} reconnection failed permanently")
    
    async def shutdown(self) -> None:
        """Shutdown plugin."""
        await self.disconnect()
        await self._set_status(self.PluginStatus.UNLOADED)