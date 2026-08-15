"""
SuperGuard Core - ONVIF Camera Plugin

ONVIF Profile S/T/G camera support with discovery and PTZ.
"""

import asyncio
import logging
from typing import List, Optional

import cv2
import numpy as np
from onvif import ONVIFCamera
from wsdiscovery.discovery import ThreadedWSDiscovery as WSDiscovery
from wsdiscovery.scope import Scope

from superguard_core.core.plugins import CameraPlugin, CameraFrame, DiscoveredCamera, PluginConfig
from superguard_core.core.database import Camera


logger = logging.getLogger(__name__)


class OnvifCameraPlugin(CameraPlugin):
    """ONVIF camera plugin with full Profile S/T/G support."""
    
    name = "onvif"
    version = "1.0.0"
    plugin_type = "camera"
    description = "ONVIF Profile S/T/G camera with PTZ support"
    author = "SuperGuard Team"
    
    def __init__(self, config: PluginConfig, event_bus):
        super().__init__(config, event_bus)
        self._camera: Optional[Camera] = None
        self._onvif_cam: Optional[ONVIFCamera] = None
        self._media_service = None
        self._ptz_service = None
        self._cap: Optional[cv2.VideoCapture] = None
        self._profile_token = None
    
    async def initialize(self) -> None:
        """Initialize plugin."""
        await self._set_status(self.PluginStatus.LOADED)
        self._initialized = True
    
    async def connect(self, camera: Camera) -> None:
        """Connect to ONVIF camera."""
        self._camera = camera
        
        if not camera.username or not camera.password:
            raise ValueError("ONVIF camera requires username and password")
        
        # Parse host from URL or config
        host = camera.config.get("host") if camera.config else None
        port = camera.config.get("port", 80) if camera.config else 80
        
        if not host:
            # Try to extract from URL
            import re
            match = re.search(r'(\d+\.\d+\.\d+\.\d+)', camera.url)
            if match:
                host = match.group(1)
            else:
                raise ValueError("ONVIF camera requires host in config")
        
        logger.info(f"Connecting to ONVIF camera {camera.id} at {host}:{port}")
        
        # Create ONVIF camera
        self._onvif_cam = ONVIFCamera(
            host, port, camera.username, camera.password
        )
        
        # Get services
        self._media_service = self._onvif_cam.create_media_service()
        self._ptz_service = self._onvif_cam.create_ptz_service()
        
        # Get profiles
        profiles = self._media_service.GetProfiles()
        if not profiles:
            raise ConnectionError("No ONVIF profiles found")
        
        # Use first profile (usually the main stream)
        self._profile_token = profiles[0].token
        
        # Get stream URI
        stream_setup = self._media_service.create_type('GetStreamUri')
        stream_setup.ProfileToken = self._profile_token
        stream_setup.StreamSetup = {
            'Stream': 'RTP-Unicast',
            'Transport': {'Protocol': 'RTSP'}
        }
        stream_uri = self._media_service.GetStreamUri(stream_setup)
        
        # Connect via OpenCV to the RTSP URI
        rtsp_url = stream_uri.Uri
        logger.info(f"ONVIF camera {camera.id} RTSP URI: {rtsp_url}")
        
        self._cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        if not self._cap.isOpened():
            raise ConnectionError(f"Failed to open ONVIF RTSP stream: {rtsp_url}")
        
        # Update camera with stream info
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
        
        logger.info(f"ONVIF camera {camera.id} connected: {width}x{height} @ {fps}fps")
    
    async def disconnect(self) -> None:
        """Disconnect from camera."""
        if self._cap:
            self._cap.release()
            self._cap = None
        
        logger.info(f"ONVIF camera {self._camera.id if self._camera else 'unknown'} disconnected")
    
    async def read_frame(self) -> Optional[CameraFrame]:
        """Read frame from camera."""
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
                "source": "onvif",
                "width": frame.shape[1],
                "height": frame.shape[0],
            }
        )
    
    async def get_snapshot(self) -> Optional[CameraFrame]:
        """Get snapshot via ONVIF."""
        if self._media_service and self._profile_token:
            try:
                snapshot_uri = self._media_service.GetSnapshotUri({'ProfileToken': self._profile_token})
                
                # Download snapshot
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(snapshot_uri.Uri) as resp:
                        if resp.status == 200:
                            img_bytes = await resp.read()
                            nparr = np.frombuffer(img_bytes, np.uint8)
                            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                            
                            if frame is not None:
                                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                                return CameraFrame(
                                    image=frame_rgb,
                                    timestamp=asyncio.get_event_loop().time(),
                                    camera_id=self._camera.id if self._camera else 0,
                                    metadata={"source": "onvif_snapshot"}
                                )
            except Exception as e:
                logger.warning(f"ONVIF snapshot failed: {e}")
        
        # Fallback to video frame
        return await self.read_frame()
    
    async def ptz_control(self, command: str, **kwargs) -> bool:
        """PTZ control via ONVIF."""
        if not self._ptz_service or not self._profile_token:
            return False
        
        try:
            # Get PTZ configuration
            ptz_config = self._ptz_service.GetConfigurationOptions({'ProfileToken': self._profile_token})
            
            # Create continuous move
            move = self._ptz_service.create_type('ContinuousMove')
            move.ProfileToken = self._profile_token
            move.Velocity = self._ptz_service.GetStatus({'ProfileToken': self._profile_token}).Position
            move.Velocity.PanTilt.space = ptz_config.Spaces.ContinuousPanTiltVelocitySpace[0].URI
            move.Velocity.Zoom.space = ptz_config.Spaces.ContinuousZoomVelocitySpace[0].URI
            
            # Set velocity based on command
            speed = kwargs.get("speed", 0.5)
            
            if command == "left":
                move.Velocity.PanTilt.x = -speed
                move.Velocity.PanTilt.y = 0
            elif command == "right":
                move.Velocity.PanTilt.x = speed
                move.Velocity.PanTilt.y = 0
            elif command == "up":
                move.Velocity.PanTilt.x = 0
                move.Velocity.PanTilt.y = speed
            elif command == "down":
                move.Velocity.PanTilt.x = 0
                move.Velocity.PanTilt.y = -speed
            elif command == "zoom_in":
                move.Velocity.Zoom.x = speed
            elif command == "zoom_out":
                move.Velocity.Zoom.x = -speed
            elif command == "stop":
                move.Velocity.PanTilt.x = 0
                move.Velocity.PanTilt.y = 0
                move.Velocity.Zoom.x = 0
            else:
                return False
            
            # Start move
            self._ptz_service.ContinuousMove(move)
            
            # If not stop, schedule stop after timeout
            if command != "stop":
                timeout = kwargs.get("timeout", 1.0)
                asyncio.create_task(self._stop_ptz_after(timeout))
            
            return True
            
        except Exception as e:
            logger.error(f"ONVIF PTZ control failed: {e}")
            return False
    
    async def _stop_ptz_after(self, timeout: float):
        """Stop PTZ after timeout."""
        await asyncio.sleep(timeout)
        try:
            stop_move = self._ptz_service.create_type('Stop')
            stop_move.ProfileToken = self._profile_token
            stop_move.PanTilt = True
            stop_move.Zoom = True
            self._ptz_service.Stop(stop_move)
        except Exception:
            pass
    
    @classmethod
    async def discover(cls, timeout: int = 10) -> List[DiscoveredCamera]:
        """Discover ONVIF cameras on network."""
        discovered = []
        
        try:
            wsd = WSDiscovery()
            wsd.start()
            
            # Search for ONVIF devices
            scopes = [Scope('onvif://www.onvif.org/type/video_encoder')]
            services = wsd.searchScopes(scopes, timeout=timeout)
            
            for service in services:
                try:
                    # Parse service info
                    xaddrs = service.getXAddrs()
                    if xaddrs:
                        # Extract host/port from XAddr
                        import re
                        for xaddr in xaddrs:
                            match = re.search(r'https?://([^:]+):(\d+)', xaddr)
                            if match:
                                host, port = match.groups()
                                
                                # Try to get device info
                                try:
                                    from onvif import ONVIFCamera
                                    cam = ONVIFCamera(host, int(port), '', '')
                                    dev_service = cam.create_devicemgmt_service()
                                    info = dev_service.GetDeviceInformation()
                                    
                                    discovered.append(DiscoveredCamera(
                                        name=f"{info.Manufacturer} {info.Model}",
                                        url=f"http://{host}:{port}",
                                        type="onvif",
                                        manufacturer=info.Manufacturer,
                                        model=info.Model,
                                        extra={"xaddrs": xaddrs}
                                    ))
                                except Exception:
                                    # Still add with minimal info
                                    discovered.append(DiscoveredCamera(
                                        name=f"ONVIF Device at {host}",
                                        url=f"http://{host}:{port}",
                                        type="onvif",
                                        extra={"xaddrs": xaddrs}
                                    ))
                except Exception as e:
                    logger.debug(f"Failed to parse ONVIF service: {e}")
            
            wsd.stop()
            
        except Exception as e:
            logger.error(f"ONVIF discovery failed: {e}")
        
        return discovered
    
    async def shutdown(self) -> None:
        """Shutdown plugin."""
        await self.disconnect()
        await self._set_status(self.PluginStatus.UNLOADED)