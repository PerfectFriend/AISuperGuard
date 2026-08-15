"""
SuperGuard Core - Camera Manager Service

Manages camera lifecycle: connection, reconnection, frame reading, PTZ.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from uuid import uuid4

import cv2
import numpy as np

from superguard_core.core.config import get_settings
from superguard_core.core.database import Camera, CameraStatus, CameraType
from superguard_core.core.events import EventBus, publish_camera_frame, Streams
from superguard_core.core.plugins import PluginManager, CameraPlugin, CameraFrame, DiscoveredCamera


logger = logging.getLogger(__name__)


@dataclass
class CameraInstance:
    """Runtime camera instance."""
    camera: Camera
    plugin: CameraPlugin
    task: Optional[asyncio.Task] = None
    reconnect_task: Optional[asyncio.Task] = None
    consecutive_failures: int = 0
    last_frame_time: float = 0
    fps: float = 0
    is_running: bool = False


class CameraManager:
    """Manages all cameras for a site."""
    
    def __init__(
        self,
        plugin_manager: PluginManager,
        event_bus: EventBus,
        site_id: int,
    ):
        self.plugin_manager = plugin_manager
        self.event_bus = event_bus
        self.site_id = site_id
        self.cameras: Dict[int, CameraInstance] = {}
        self._running = False
        self._session_factory = None
    
    def set_session_factory(self, factory):
        """Set database session factory."""
        self._session_factory = factory
    
    async def start(self) -> None:
        """Start camera manager."""
        self._running = True
        logger.info(f"CameraManager started for site {self.site_id}")
    
    async def stop(self) -> None:
        """Stop all cameras and manager."""
        self._running = False
        for instance in list(self.cameras.values()):
            await self._stop_camera(instance)
        self.cameras.clear()
        logger.info(f"CameraManager stopped for site {self.site_id}")
    
    async def load_cameras(self, cameras: List[Camera]) -> None:
        """Load and start cameras from database."""
        for camera in cameras:
            if camera.is_enabled and camera.site_id == self.site_id:
                await self._start_camera(camera)
    
    async def add_camera(self, camera: Camera) -> None:
        """Add and start a new camera."""
        if camera.is_enabled:
            await self._start_camera(camera)
    
    async def remove_camera(self, camera_id: int) -> None:
        """Remove and stop a camera."""
        if camera_id in self.cameras:
            await self._stop_camera(self.cameras[camera_id])
            del self.cameras[camera_id]
    
    async def update_camera(self, camera: Camera) -> None:
        """Update camera configuration."""
        if camera_id := camera.id:
            if camera_id in self.cameras:
                await self._stop_camera(self.cameras[camera_id])
            if camera.is_enabled:
                await self._start_camera(camera)
    
    async def _start_camera(self, camera: Camera) -> None:
        """Start a single camera."""
        try:
            # Get plugin
            plugin_class = self.plugin_manager.get_plugin_class(
                self.plugin_manager.metadata[camera.type.value].plugin_type if camera.type.value in [m.name for m in self.plugin_manager.metadata.values()] else None,
                camera.type.value
            )
            
            # Try to find plugin by name
            plugin_name = camera.type.value
            plugin_class = self.plugin_manager.get_plugin_class(
                self.plugin_manager.metadata.get(plugin_name, None) and self.plugin_manager.metadata[plugin_name].plugin_type or None,
                plugin_name
            )
            
            if not plugin_class:
                # Try to find by iterating
                for name, meta in self.plugin_manager.metadata.items():
                    if meta.plugin_type.value == "camera" and name == camera.type.value:
                        plugin_class = meta.entry_point.load()
                        break
            
            if not plugin_class:
                raise ValueError(f"No camera plugin found for type: {camera.type.value}")
            
            # Load plugin
            from superguard_core.core.plugins import PluginConfig
            plugin_config = PluginConfig(enabled=True, site_id=self.site_id)
            plugin = await self.plugin_manager.load_plugin(
                self.plugin_manager.metadata[plugin_name].plugin_type,
                plugin_name,
                plugin_config,
                self.event_bus,
            )
            
            # Create instance
            instance = CameraInstance(camera=camera, plugin=plugin)
            self.cameras[camera.id] = instance
            
            # Connect
            await plugin.connect(camera)
            
            # Update status
            await self._update_camera_status(camera.id, CameraStatus.ONLINE)
            
            # Start reading task
            instance.is_running = True
            instance.task = asyncio.create_task(self._read_loop(instance))
            
            logger.info(f"Camera {camera.id} ({camera.name}) started")
            
        except Exception as e:
            logger.error(f"Failed to start camera {camera.id}: {e}")
            await self._update_camera_status(camera.id, CameraStatus.ERROR, str(e))
    
    async def _stop_camera(self, instance: CameraInstance) -> None:
        """Stop a single camera."""
        instance.is_running = False
        
        if instance.task:
            instance.task.cancel()
            try:
                await instance.task
            except asyncio.CancelledError:
                pass
        
        if instance.reconnect_task:
            instance.reconnect_task.cancel()
            try:
                await instance.reconnect_task
            except asyncio.CancelledError:
                pass
        
        try:
            await instance.plugin.disconnect()
        except Exception as e:
            logger.error(f"Error disconnecting camera {instance.camera.id}: {e}")
        
        await self._update_camera_status(instance.camera.id, CameraStatus.OFFLINE)
        logger.info(f"Camera {instance.camera.id} stopped")
    
    async def _read_loop(self, instance: CameraInstance) -> None:
        """Main frame reading loop."""
        camera = instance.camera
        plugin = instance.plugin
        settings = get_settings()
        
        frame_interval = 1.0 / max(camera.fps or 10, 1)  # Default 10 FPS
        last_frame_time = 0
        
        while instance.is_running and self._running:
            try:
                start_time = time.time()
                
                # Read frame
                frame = await plugin.read_frame()
                
                if frame is not None:
                    instance.consecutive_failures = 0
                    instance.last_frame_time = time.time()
                    
                    # Calculate FPS
                    if last_frame_time > 0:
                        instance.fps = 1.0 / (instance.last_frame_time - last_frame_time)
                    last_frame_time = instance.last_frame_time
                    
                    # Update camera last_frame_at
                    if self._session_factory:
                        async with self._session_factory() as session:
                            from sqlalchemy import update
                            await session.execute(
                                update(Camera)
                                .where(Camera.id == camera.id)
                                .values(last_frame_at=datetime.now())
                            )
                            await session.commit()
                    
                    # Publish frame event
                    await publish_camera_frame(self.event_bus, camera.id, {
                        "frame_id": str(uuid4()),
                        "timestamp": frame.timestamp,
                        "width": frame.image.shape[1] if hasattr(frame.image, 'shape') else 0,
                        "height": frame.image.shape[0] if hasattr(frame.image, 'shape') else 0,
                        "metadata": frame.metadata,
                    })
                    
                else:
                    instance.consecutive_failures += 1
                    if instance.consecutive_failures >= 10:
                        logger.warning(f"Camera {camera.id}: {instance.consecutive_failures} consecutive failures")
                        await self._update_camera_status(camera.id, CameraStatus.ERROR, "Frame read failures")
                
                # Sleep to maintain frame rate
                elapsed = time.time() - start_time
                sleep_time = max(0, frame_interval - elapsed)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Camera {camera.id} read error: {e}")
                instance.consecutive_failures += 1
                
                if instance.consecutive_failures >= 5:
                    # Trigger reconnection
                    if not instance.reconnect_task or instance.reconnect_task.done():
                        instance.reconnect_task = asyncio.create_task(
                            self._reconnect_camera(instance)
                        )
                
                await asyncio.sleep(1)
    
    async def _reconnect_camera(self, instance: CameraInstance) -> None:
        """Attempt to reconnect camera."""
        camera = instance.camera
        logger.info(f"Attempting to reconnect camera {camera.id}...")
        
        for attempt in range(5):
            try:
                await instance.plugin.disconnect()
            except Exception:
                pass
            
            try:
                await instance.plugin.connect(camera)
                instance.consecutive_failures = 0
                await self._update_camera_status(camera.id, CameraStatus.ONLINE)
                logger.info(f"Camera {camera.id} reconnected successfully")
                return
            except Exception as e:
                logger.warning(f"Reconnection attempt {attempt + 1} failed: {e}")
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
        
        # All attempts failed
        await self._update_camera_status(camera.id, CameraStatus.ERROR, "Reconnection failed after 5 attempts")
        logger.error(f"Camera {camera.id} reconnection failed permanently")
    
    async def _update_camera_status(
        self,
        camera_id: int,
        status: CameraStatus,
        error: Optional[str] = None,
    ) -> None:
        """Update camera status in database."""
        if not self._session_factory:
            return
        
        try:
            async with self._session_factory() as session:
                from sqlalchemy import update
                values = {"status": status}
                if error:
                    values["error_message"] = error
                elif status == CameraStatus.ONLINE:
                    values["error_message"] = None
                await session.execute(
                    update(Camera)
                    .where(Camera.id == camera_id)
                    .values(**values)
                )
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to update camera status: {e}")
    
    async def get_snapshot(self, camera_id: int) -> Optional[CameraFrame]:
        """Get single snapshot from camera."""
        if camera_id in self.cameras:
            instance = self.cameras[camera_id]
            try:
                return await instance.plugin.get_snapshot()
            except Exception as e:
                logger.error(f"Snapshot failed for camera {camera_id}: {e}")
        return None
    
    async def ptz_control(self, camera_id: int, command: str, **kwargs) -> bool:
        """Control PTZ."""
        if camera_id in self.cameras:
            instance = self.cameras[camera_id]
            try:
                return await instance.plugin.ptz_control(command, **kwargs)
            except Exception as e:
                logger.error(f"PTZ control failed for camera {camera_id}: {e}")
        return False
    
    @classmethod
    async def discover_cameras(cls, timeout: int = 10) -> List[DiscoveredCamera]:
        """Discover cameras using all available plugins."""
        all_discovered = []
        
        # We need a temporary plugin manager for discovery
        from superguard_core.core.plugins import PluginManager
        from superguard_core.core.events import EventBus
        import redis.asyncio as redis
        
        pm = PluginManager()
        await pm.discover_plugins()
        
        for metadata in pm.get_available_plugins():
            if metadata.plugin_type.value == "camera":
                plugin_class = metadata.entry_point.load()
                try:
                    discovered = await plugin_class.discover(timeout)
                    all_discovered.extend(discovered)
                except Exception as e:
                    logger.warning(f"Discovery failed for {metadata.name}: {e}")
        
        return all_discovered
    
    def get_camera_stats(self, camera_id: int) -> Optional[Dict[str, Any]]:
        """Get camera statistics."""
        if camera_id in self.cameras:
            instance = self.cameras[camera_id]
            return {
                "camera_id": camera_id,
                "status": instance.camera.status.value,
                "fps": instance.fps,
                "consecutive_failures": instance.consecutive_failures,
                "last_frame_time": instance.last_frame_time,
                "is_running": instance.is_running,
            }
        return None
    
    def get_all_stats(self) -> List[Dict[str, Any]]:
        """Get stats for all cameras."""
        return [self.get_camera_stats(cid) for cid in self.cameras.keys()]


# Factory function for creating camera managers per site
_camera_managers: Dict[int, CameraManager] = {}


async def get_camera_manager(
    site_id: int,
    plugin_manager: PluginManager,
    event_bus: EventBus,
) -> CameraManager:
    """Get or create camera manager for site."""
    if site_id not in _camera_managers:
        _camera_managers[site_id] = CameraManager(plugin_manager, event_bus, site_id)
        await _camera_managers[site_id].start()
    return _camera_managers[site_id]


async def close_all_camera_managers() -> None:
    """Close all camera managers."""
    for manager in _camera_managers.values():
        await manager.stop()
    _camera_managers.clear()