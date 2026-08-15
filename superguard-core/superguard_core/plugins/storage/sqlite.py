"""
SuperGuard Core - SQLite Storage Plugin

Local SQLite storage for media files and metadata.
"""

import asyncio
import logging
import os
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

import aiofiles

from superguard_core.core.plugins import StoragePlugin, PluginConfig
from superguard_core.core.database import AlarmMedia, MediaType
from superguard_core.core.events import EventBus, Event, Streams


logger = logging.getLogger(__name__)


class SqliteStoragePlugin(StoragePlugin):
    """Local filesystem storage with SQLite metadata."""
    
    name = "sqlite"
    version = "1.0.0"
    plugin_type = "storage"
    description = "Local filesystem storage with SQLite metadata"
    author = "SuperGuard Team"
    
    def __init__(self, config: PluginConfig, event_bus: EventBus):
        super().__init__(config, event_bus)
        self._base_path: Path = Path("./storage")
        self._media_path: Path = Path("./storage/media")
        self._thumbnails_path: Path = Path("./storage/thumbnails")
        self._recordings_path: Path = Path("./storage/recordings")
        self._max_size_gb: float = 10.0
        self._cleanup_interval: int = 3600  # 1 hour
    
    async def initialize(self, site_id: int) -> None:
        """Initialize storage paths."""
        base = self.config.get("base_path", "./storage")
        self._base_path = Path(base).resolve()
        self._media_path = self._base_path / "media"
        self._thumbnails_path = self._base_path / "thumbnails"
        self._recordings_path = self._base_path / "recordings"
        self._max_size_gb = self.config.get("max_size_gb", 10.0)
        self._cleanup_interval = self.config.get("cleanup_interval", 3600)
        
        # Create directories
        self._media_path.mkdir(parents=True, exist_ok=True)
        self._thumbnails_path.mkdir(parents=True, exist_ok=True)
        self._recordings_path.mkdir(parents=True, exist_ok=True)
        
        # Subscribe to media events
        await self._event_bus.subscribe(
            Streams.MEDIA_EVENTS,
            self._on_media_event,
            group=f"storage-media-{site_id}"
        )
        
        # Start cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        await self._set_status(self.PluginStatus.LOADED)
        self._initialized = True
        
        logger.info(f"SQLite storage initialized at {self._base_path}")
    
    async def save_frame(
        self,
        frame_bytes: bytes,
        camera_id: int,
        alarm_id: int,
        timestamp: datetime,
        metadata: Dict[str, Any] = None,
    ) -> str:
        """Save frame as JPEG."""
        # Generate filename
        date_str = timestamp.strftime("%Y%m%d")
        time_str = timestamp.strftime("%H%M%S")
        
        if alarm_id > 0:
            filename = f"alarm_{alarm_id}_{time_str}.jpg"
            subdir = self._media_path / f"alarm_{alarm_id}"
        else:
            filename = f"cam_{camera_id}_{date_str}_{time_str}.jpg"
            subdir = self._media_path / f"cam_{camera_id}" / date_str
        
        subdir.mkdir(parents=True, exist_ok=True)
        file_path = subdir / filename
        
        # Save frame
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(frame_bytes)
        
        # Generate thumbnail
        thumb_path = await self._generate_thumbnail(file_path, camera_id)
        
        logger.debug(f"Saved frame: {file_path}")
        return str(file_path)
    
    async def save_video(
        self,
        video_path: str,
        camera_id: int,
        alarm_id: int,
        start_time: datetime,
        end_time: datetime,
        metadata: Dict[str, Any] = None,
    ) -> str:
        """Save/move video file."""
        date_str = start_time.strftime("%Y%m%d")
        
        if alarm_id > 0:
            filename = f"alarm_{alarm_id}_{start_time.strftime('%H%M%S')}.mp4"
            subdir = self._recordings_path / f"alarm_{alarm_id}"
        else:
            filename = f"cam_{camera_id}_{date_str}_{start_time.strftime('%H%M%S')}.mp4"
            subdir = self._recordings_path / f"cam_{camera_id}" / date_str
        
        subdir.mkdir(parents=True, exist_ok=True)
        dest_path = subdir / filename
        
        # Move file
        shutil.move(video_path, dest_path)
        
        # Generate thumbnail from first frame
        thumb_path = await self._generate_thumbnail(dest_path, camera_id)
        
        logger.debug(f"Saved video: {dest_path}")
        return str(dest_path)
    
    async def save_snapshot(
        self,
        frame_bytes: bytes,
        camera_id: int,
        timestamp: datetime,
        metadata: Dict[str, Any] = None,
    ) -> str:
        """Save snapshot."""
        return await self.save_frame(frame_bytes, camera_id, 0, timestamp, metadata)
    
    async def delete_file(self, file_path: str) -> bool:
        """Delete file from storage."""
        try:
            path = Path(file_path)
            if path.exists():
                path.unlink()
                
                # Delete thumbnail if exists
                thumb_path = self._thumbnails_path / path.relative_to(self._base_path)
                if thumb_path.exists():
                    thumb_path.unlink()
                
                return True
        except Exception as e:
            logger.error(f"Failed to delete {file_path}: {e}")
        return False
    
    async def get_file_path(self, media_id: int) -> Optional[str]:
        """Get file path for media ID (requires DB lookup)."""
        # This would need a session to look up the media record
        # For now, return None - the API layer handles this
        return None
    
    async def get_storage_stats(self) -> Dict[str, Any]:
        """Get storage statistics."""
        total_size = 0
        file_count = 0
        
        for path in [self._media_path, self._recordings_path, self._thumbnails_path]:
            if path.exists():
                for f in path.rglob("*"):
                    if f.is_file():
                        total_size += f.stat().st_size
                        file_count += 1
        
        # Disk usage
        try:
            usage = shutil.disk_usage(self._base_path)
        except:
            usage = None
        
        return {
            "base_path": str(self._base_path),
            "total_files": file_count,
            "total_size_bytes": total_size,
            "total_size_gb": round(total_size / (1024**3), 2),
            "max_size_gb": self._max_size_gb,
            "disk_total_gb": round(usage.total / (1024**3), 2) if usage else 0,
            "disk_free_gb": round(usage.free / (1024**3), 2) if usage else 0,
            "usage_percent": round((total_size / usage.total * 100) if usage and usage.total > 0 else 0, 1),
        }
    
    async def _generate_thumbnail(self, file_path: Path, camera_id: int) -> Optional[str]:
        """Generate thumbnail for image or video."""
        try:
            import cv2
            
            thumb_name = f"{file_path.stem}_thumb.jpg"
            thumb_path = self._thumbnails_path / file_path.relative_to(self._base_path).parent / thumb_name
            thumb_path.parent.mkdir(parents=True, exist_ok=True)
            
            if file_path.suffix.lower() in [".mp4", ".mov", ".avi"]:
                # Video: extract first frame
                cap = cv2.VideoCapture(str(file_path))
                ret, frame = cap.read()
                cap.release()
                if not ret:
                    return None
            else:
                # Image
                frame = cv2.imread(str(file_path))
                if frame is None:
                    return None
            
            # Resize to thumbnail
            h, w = frame.shape[:2]
            max_dim = 320
            if w > h:
                new_w = max_dim
                new_h = int(h * max_dim / w)
            else:
                new_h = max_dim
                new_w = int(w * max_dim / h)
            
            thumb = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
            cv2.imwrite(str(thumb_path), thumb)
            
            return str(thumb_path)
            
        except Exception as e:
            logger.debug(f"Thumbnail generation failed for {file_path}: {e}")
            return None
    
    async def _cleanup_loop(self) -> None:
        """Periodic cleanup of old files."""
        while self._initialized:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self._cleanup_old_files()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Storage cleanup error: {e}")
    
    async def _cleanup_old_files(self) -> None:
        """Clean up old files if over quota."""
        stats = await self.get_storage_stats()
        
        if stats["total_size_gb"] <= self._max_size_gb:
            return
        
        logger.info(f"Storage over quota ({stats['total_size_gb']:.2f}GB > {self._max_size_gb}GB), cleaning up...")
        
        # Collect all files with mtime
        all_files = []
        for path in [self._media_path, self._recordings_path]:
            if path.exists():
                for f in path.rglob("*"):
                    if f.is_file():
                        all_files.append((f.stat().st_mtime, f))
        
        # Sort by oldest first
        all_files.sort(key=lambda x: x[0])
        
        # Delete oldest until under quota
        target_bytes = self._max_size_gb * (1024**3) * 0.8  # 80% of max
        current_bytes = stats["total_size_bytes"]
        
        for mtime, f in all_files:
            if current_bytes <= target_bytes:
                break
            
            try:
                size = f.stat().st_size
                f.unlink()
                current_bytes -= size
                
                # Delete thumbnail
                thumb_path = self._thumbnails_path / f.relative_to(self._base_path).with_name(f.stem + "_thumb.jpg")
                if thumb_path.exists():
                    thumb_path.unlink()
                    
            except Exception as e:
                logger.debug(f"Cleanup failed for {f}: {e}")
        
        logger.info(f"Cleanup complete, freed {stats['total_size_bytes'] - current_bytes} bytes")
    
    async def _on_media_event(self, event: Event) -> None:
        """Handle media events."""
        # Storage plugin handles media saving internally
        # This is for notifications
        pass
    
    async def shutdown(self) -> None:
        """Shutdown plugin."""
        self._initialized = False
        
        if hasattr(self, '_cleanup_task'):
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        await self._set_status(self.PluginStatus.UNLOADED)