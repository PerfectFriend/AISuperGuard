"""
SuperGuard Core - JPG Camera Plugin

JPEG snapshot camera support using HTTP requests.
"""

import asyncio
import logging
from typing import List, Optional

import aiohttp
import cv2
import numpy as np

from superguard_core.core.plugins import CameraPlugin, CameraFrame, DiscoveredCamera, PluginConfig
from superguard_core.core.database import Camera


logger = logging.getLogger(__name__)


class JpgCameraPlugin(CameraPlugin):
    """JPG camera plugin using HTTP snapshot requests."""
    
    name = "jpg"
    version = "1.0.0"
    plugin_type = "camera"
    description = "JPG snapshot camera support via HTTP"
    author = "SuperGuard Team"
    
    def __init__(self, config: PluginConfig, event_bus):
        super().__init__(config, event_bus)
        self._camera: Optional[Camera] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._auth = None
    
    async def initialize(self) -> None:
        """Initialize plugin."""
        await self._set_status(self.PluginStatus.LOADED)
        self._initialized = True
    
    async def connect(self, camera: Camera) -> None:
        """Connect to JPG camera."""
        self._camera = camera
        
        # Setup auth
        if camera.username and camera.password:
            self._auth = aiohttp.BasicAuth(camera.username, camera.password)
        
        # Create HTTP session
        timeout = aiohttp.ClientTimeout(total=10, connect=5)
        self._session = aiohttp.ClientSession(timeout=timeout)
        
        # Test connection
        frame = await self.get_snapshot()
        if frame is None:
            await self.disconnect()
            raise ConnectionError(f"Failed to get snapshot from JPG camera: {camera.url}")
        
        # Update camera with detected resolution
        if frame.image is not None and hasattr(frame.image, 'shape'):
            from superguard_core.core.database import get_session_factory
            factory = get_session_factory()
            if factory:
                async with factory() as session:
                    from sqlalchemy import update
                    await session.execute(
                        update(Camera)
                        .where(Camera.id == camera.id)
                        .values(width=frame.image.shape[1], height=frame.image.shape[0])
                    )
                    await session.commit()
        
        logger.info(f"JPG camera {camera.id} connected: {frame.image.shape[1] if frame.image is not None else '?'}x{frame.image.shape[0] if frame.image is not None else '?'}")
    
    async def disconnect(self) -> None:
        """Disconnect from camera."""
        if self._session:
            await self._session.close()
            self._session = None
        
        logger.info(f"JPG camera {self._camera.id if self._camera else 'unknown'} disconnected")
    
    async def read_frame(self) -> Optional[CameraFrame]:
        """Read frame from camera (alias for get_snapshot for JPG cameras)."""
        return await self.get_snapshot()
    
    async def get_snapshot(self) -> Optional[CameraFrame]:
        """Get single snapshot via HTTP."""
        if not self._session or not self._camera:
            return None
        
        try:
            async with self._session.get(self._camera.url, auth=self._auth) as resp:
                if resp.status != 200:
                    logger.warning(f"JPG camera {self._camera.id} returned status {resp.status}")
                    return None
                
                img_bytes = await resp.read()
                
                # Decode image
                nparr = np.frombuffer(img_bytes, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
                if frame is None:
                    logger.warning(f"JPG camera {self._camera.id}: failed to decode image")
                    return None
                
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                return CameraFrame(
                    image=frame_rgb,
                    timestamp=asyncio.get_event_loop().time(),
                    camera_id=self._camera.id,
                    metadata={
                        "source": "jpg",
                        "width": frame.shape[1],
                        "height": frame.shape[0],
                        "content_type": resp.content_type,
                    }
                )
                
        except asyncio.TimeoutError:
            logger.warning(f"JPG camera {self._camera.id}: request timeout")
            return None
        except Exception as e:
            logger.error(f"JPG camera {self._camera.id} error: {e}")
            return None
    
    async def ptz_control(self, command: str, **kwargs) -> bool:
        """PTZ control (not supported for generic JPG)."""
        return False
    
    @classmethod
    async def discover(cls, timeout: int = 10) -> List[DiscoveredCamera]:
        """Discover JPG cameras (not implemented for generic HTTP)."""
        return []
    
    async def shutdown(self) -> None:
        """Shutdown plugin."""
        await self.disconnect()
        await self._set_status(self.PluginStatus.UNLOADED)