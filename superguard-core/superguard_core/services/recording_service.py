"""
SuperGuard Core - Recording Service

Manages video recording: MP4 segments, retention, MediaMTX integration.
"""

import asyncio
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from uuid import uuid4

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from superguard_core.core.config import get_settings
from superguard_core.core.database import Camera, Alarm, AlarmMedia, MediaType
from superguard_core.core.events import EventBus, Streams
from superguard_core.core.plugins import PluginManager


logger = logging.getLogger(__name__)


@dataclass
class RecordingSession:
    """Active recording session for a camera."""
    camera_id: int
    process: Optional[subprocess.Popen] = None
    segment_start: float = 0
    segment_path: str = ""
    segment_index: int = 0
    is_recording: bool = False
    alarm_id: Optional[int] = None


class RecordingService:
    """Manages video recording for cameras and alarms."""
    
    def __init__(
        self,
        event_bus: EventBus,
        storage_path: str,
        plugin_manager: Optional[PluginManager] = None,
    ):
        self.event_bus = event_bus
        self.storage_path = Path(storage_path)
        self.plugin_manager = plugin_manager
        self.sessions: Dict[int, RecordingSession] = {}
        self._running = False
        self._session_factory = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._mediamtx_url = ""
    
    def set_session_factory(self, factory):
        """Set database session factory."""
        self._session_factory = factory
    
    def set_mediamtx_url(self, url: str):
        """Set MediaMTX API URL."""
        self._mediamtx_url = url
    
    async def start(self) -> None:
        """Start recording service."""
        self._running = True
        
        # Create storage directories
        (self.storage_path / "recordings").mkdir(parents=True, exist_ok=True)
        (self.storage_path / "alarms").mkdir(parents=True, exist_ok=True)
        (self.storage_path / "snapshots").mkdir(parents=True, exist_ok=True)
        
        # Start cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        logger.info("RecordingService started")
    
    async def stop(self) -> None:
        """Stop recording service."""
        self._running = False
        
        # Stop all recordings
        for session in list(self.sessions.values()):
            await self._stop_recording(session)
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        self.sessions.clear()
        logger.info("RecordingService stopped")
    
    async def start_continuous_recording(self, camera_id: int) -> bool:
        """Start continuous recording for camera."""
        if camera_id in self.sessions:
            return True  # Already recording
        
        if not self._session_factory:
            return False
        
        async with self._session_factory() as session:
            from sqlalchemy import select
            result = await session.execute(select(Camera).where(Camera.id == camera_id))
            camera = result.scalar_one_or_none()
            
            if not camera or not camera.is_enabled:
                return False
        
        session_obj = RecordingSession(camera_id=camera_id)
        self.sessions[camera_id] = session_obj
        
        # Start recording in background
        asyncio.create_task(self._record_continuous(session_obj))
        
        logger.info(f"Continuous recording started for camera {camera_id}")
        return True
    
    async def stop_continuous_recording(self, camera_id: int) -> bool:
        """Stop continuous recording for camera."""
        if camera_id in self.sessions:
            await self._stop_recording(self.sessions[camera_id])
            del self.sessions[camera_id]
            logger.info(f"Continuous recording stopped for camera {camera_id}")
            return True
        return False
    
    async def start_alarm_recording(self, alarm_id: int, camera_id: int) -> bool:
        """Start recording for alarm event."""
        if camera_id in self.sessions:
            # Already recording, just mark as alarm recording
            self.sessions[camera_id].alarm_id = alarm_id
            return True
        
        session_obj = RecordingSession(camera_id=camera_id, alarm_id=alarm_id)
        self.sessions[camera_id] = session_obj
        
        asyncio.create_task(self._record_alarm(session_obj))
        
        logger.info(f"Alarm recording started for alarm {alarm_id}, camera {camera_id}")
        return True
    
    async def stop_alarm_recording(self, alarm_id: int, camera_id: int) -> bool:
        """Stop alarm recording."""
        if camera_id in self.sessions:
            session_obj = self.sessions[camera_id]
            if session_obj.alarm_id == alarm_id:
                await self._stop_recording(session_obj)
                del self.sessions[camera_id]
                logger.info(f"Alarm recording stopped for alarm {alarm_id}, camera {camera_id}")
                return True
        return False
    
    async def take_snapshot(self, camera_id: int, alarm_id: Optional[int] = None) -> Optional[str]:
        """Take snapshot from camera (via MediaMTX or camera manager)."""
        if not self._session_factory:
            return None
        
        async with self._session_factory() as session:
            from sqlalchemy import select
            result = await session.execute(select(Camera).where(Camera.id == camera_id))
            camera = result.scalar_one_or_none()
            
            if not camera:
                return None
        
        # Try to get snapshot via MediaMTX API
        snapshot_path = await self._get_snapshot_via_mediamtx(camera)
        
        if snapshot_path and alarm_id:
            # Save to alarm media
            await self._save_alarm_media(alarm_id, camera_id, snapshot_path, MediaType.SNAPSHOT)
        
        return snapshot_path
    
    async def _record_continuous(self, session_obj: RecordingSession) -> None:
        """Continuous recording loop with segment rotation."""
        camera_id = session_obj.camera_id
        settings = get_settings()
        
        segment_duration = settings.recording_segment_duration
        max_segments = settings.recording_max_segments
        codec = settings.recording_codec
        
        camera_dir = self.storage_path / "recordings" / f"camera_{camera_id}"
        camera_dir.mkdir(parents=True, exist_ok=True)
        
        segment_index = 0
        
        while session_obj.is_recording and self._running:
            session_obj.is_recording = True
            session_obj.segment_index = segment_index
            session_obj.segment_start = time.time()
            
            # Generate segment filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            segment_filename = f"seg_{segment_index:04d}_{timestamp}.mp4"
            segment_path = camera_dir / segment_filename
            session_obj.segment_path = str(segment_path)
            
            # Start FFmpeg recording
            try:
                await self._start_ffmpeg_recording(camera_id, str(segment_path), codec)
                
                # Wait for segment duration
                await asyncio.sleep(segment_duration)
                
                # Stop FFmpeg
                await self._stop_ffmpeg(session_obj)
                
                # Save segment metadata
                if self._session_factory:
                    await self._save_recording_segment(camera_id, str(segment_path), segment_index)
                
                segment_index += 1
                
                # Cleanup old segments
                await self._cleanup_old_segments(camera_id, max_segments)
                
            except Exception as e:
                logger.error(f"Recording error for camera {camera_id}: {e}")
                await asyncio.sleep(5)
        
        session_obj.is_recording = False
    
    async def _record_alarm(self, session_obj: RecordingSession) -> None:
        """Alarm recording - records until alarm ends."""
        camera_id = session_obj.camera_id
        alarm_id = session_obj.alarm_id
        settings = get_settings()
        codec = settings.recording_codec
        
        alarm_dir = self.storage_path / "alarms" / f"alarm_{alarm_id}"
        alarm_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        video_filename = f"alarm_{alarm_id}_{timestamp}.mp4"
        video_path = alarm_dir / video_filename
        session_obj.segment_path = str(video_path)
        
        try:
            await self._start_ffmpeg_recording(camera_id, str(video_path), codec)
            
            # Keep recording until alarm ends (monitored externally)
            while session_obj.is_recording and self._running:
                await asyncio.sleep(1)
                
                # Check if alarm still active
                if self._session_factory:
                    async with self._session_factory() as session:
                        from sqlalchemy import select
                        result = await session.execute(
                            select(Alarm).where(Alarm.id == alarm_id)
                        )
                        alarm = result.scalar_one_or_none()
                        if not alarm or alarm.status in ["resolved", "false_positive"]:
                            break
            
            await self._stop_ffmpeg(session_obj)
            
            # Save to alarm media
            if self._session_factory:
                await self._save_alarm_media(alarm_id, camera_id, str(video_path), MediaType.VIDEO)
                
        except Exception as e:
            logger.error(f"Alarm recording error for alarm {alarm_id}: {e}")
        
        session_obj.is_recording = False
    
    async def _start_ffmpeg_recording(self, camera_id: int, output_path: str, codec: str) -> None:
        """Start FFmpeg process for recording."""
        # Get stream URL from MediaMTX
        settings = get_settings()
        mediamtx_url = f"http://localhost:{settings.mediamtx_hls_port}"
        stream_url = f"{mediamtx_url}/camera_{camera_id}/index.m3u8"
        
        # FFmpeg command
        cmd = [
            "ffmpeg", "-y",
            "-i", stream_url,
            "-c:v", "libx264" if codec == "h264" else "libx265",
            "-preset", "veryfast",
            "-tune", "zerolatency",
            "-f", "mp4",
            output_path,
        ]
        
        session_obj = self.sessions[camera_id]
        session_obj.process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        
        # Wait a bit for FFmpeg to start
        await asyncio.sleep(2)
        
        if session_obj.process.poll() is not None:
            raise RuntimeError(f"FFmpeg failed to start: {session_obj.process.returncode}")
    
    async def _stop_ffmpeg(self, session_obj: RecordingSession) -> None:
        """Stop FFmpeg process gracefully."""
        if session_obj.process:
            session_obj.process.terminate()
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(session_obj.process.wait),
                    timeout=10
                )
            except asyncio.TimeoutError:
                session_obj.process.kill()
                await asyncio.to_thread(session_obj.process.wait)
            session_obj.process = None
    
    async def _stop_recording(self, session_obj: RecordingSession) -> None:
        """Stop recording session."""
        session_obj.is_recording = False
        await self._stop_ffmpeg(session_obj)
    
    async def _get_snapshot_via_mediamtx(self, camera: Camera) -> Optional[str]:
        """Get snapshot via MediaMTX API."""
        try:
            import aiohttp
            
            settings = get_settings()
            snapshot_url = f"http://localhost:{settings.mediamtx_hls_port}/camera_{camera.id}/snapshot.jpg"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(snapshot_url, timeout=10) as resp:
                    if resp.status == 200:
                        # Save snapshot
                        snapshot_dir = self.storage_path / "snapshots" / f"camera_{camera.id}"
                        snapshot_dir.mkdir(parents=True, exist_ok=True)
                        
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = f"snapshot_{timestamp}.jpg"
                        filepath = snapshot_dir / filename
                        
                        with open(filepath, 'wb') as f:
                            f.write(await resp.read())
                        
                        return str(filepath)
        except Exception as e:
            logger.warning(f"MediaMTX snapshot failed: {e}")
        
        return None
    
    async def _save_recording_segment(self, camera_id: int, path: str, segment_index: int) -> None:
        """Save recording segment metadata to database."""
        if not self._session_factory:
            return
        
        try:
            async with self._session_factory() as session:
                from sqlalchemy import select
                from superguard_core.core.database import AlarmMedia, MediaType
                import os
                
                file_size = os.path.getsize(path) if os.path.exists(path) else 0
                
                media = AlarmMedia(
                    alarm_id=0,  # Continuous recording
                    camera_id=camera_id,
                    type=MediaType.VIDEO,
                    path=path,
                    file_size=file_size,
                    metadata={"segment_index": segment_index, "continuous": True},
                )
                session.add(media)
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to save segment metadata: {e}")
    
    async def _save_alarm_media(
        self,
        alarm_id: int,
        camera_id: int,
        path: str,
        media_type: MediaType,
    ) -> None:
        """Save alarm media to database."""
        if not self._session_factory:
            return
        
        try:
            async with self._session_factory() as session:
                import os
                
                file_size = os.path.getsize(path) if os.path.exists(path) else 0
                
                media = AlarmMedia(
                    alarm_id=alarm_id,
                    camera_id=camera_id,
                    type=media_type,
                    path=path,
                    file_size=file_size,
                )
                session.add(media)
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to save alarm media: {e}")
    
    async def _cleanup_old_segments(self, camera_id: int, max_segments: int) -> None:
        """Remove old continuous recording segments."""
        camera_dir = self.storage_path / "recordings" / f"camera_{camera_id}"
        
        if not camera_dir.exists():
            return
        
        segments = sorted(camera_dir.glob("seg_*.mp4"))
        
        if len(segments) > max_segments:
            for old_segment in segments[:-max_segments]:
                try:
                    old_segment.unlink()
                    logger.debug(f"Removed old segment: {old_segment}")
                except Exception as e:
                    logger.warning(f"Failed to remove old segment: {e}")
    
    async def _cleanup_loop(self) -> None:
        """Periodic cleanup of old recordings."""
        settings = get_settings()
        
        while self._running:
            try:
                await asyncio.sleep(3600)  # Every hour
                
                # Cleanup old alarm media
                if self._session_factory:
                    async with self._session_factory() as session:
                        from sqlalchemy import select, delete
                        from superguard_core.core.database import AlarmMedia
                        
                        cutoff = datetime.now() - timedelta(days=settings.alarm_frame_retention_days)
                        
                        # Find old media
                        result = await session.execute(
                            select(AlarmMedia)
                            .where(AlarmMedia.timestamp < cutoff)
                        )
                        old_media = result.scalars().all()
                        
                        for media in old_media:
                            try:
                                if os.path.exists(media.path):
                                    os.unlink(media.path)
                            except Exception:
                                pass
                            
                            await session.delete(media)
                        
                        if old_media:
                            await session.commit()
                            logger.info(f"Cleaned up {len(old_media)} old media files")
                
                # Cleanup old continuous recordings
                recordings_dir = self.storage_path / "recordings"
                if recordings_dir.exists():
                    for camera_dir in recordings_dir.iterdir():
                        if camera_dir.is_dir():
                            await self._cleanup_old_segments(
                                int(camera_dir.name.split("_")[1]),
                                settings.recording_max_segments
                            )
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
    
    def get_recording_stats(self, camera_id: int) -> Optional[Dict[str, Any]]:
        """Get recording statistics for camera."""
        if camera_id in self.sessions:
            session_obj = self.sessions[camera_id]
            return {
                "camera_id": camera_id,
                "is_recording": session_obj.is_recording,
                "segment_index": session_obj.segment_index,
                "segment_start": session_obj.segment_start,
                "current_segment": session_obj.segment_path,
                "alarm_id": session_obj.alarm_id,
            }
        return None
    
    def get_all_stats(self) -> List[Dict[str, Any]]:
        """Get stats for all recordings."""
        return [self.get_recording_stats(cid) for cid in self.sessions.keys()]


# Factory
_recording_services: Dict[int, RecordingService] = {}


async def get_recording_service(
    site_id: int,
    event_bus: EventBus,
    storage_path: str,
    plugin_manager: Optional[PluginManager] = None,
) -> RecordingService:
    """Get or create recording service for site."""
    if site_id not in _recording_services:
        _recording_services[site_id] = RecordingService(event_bus, storage_path, plugin_manager)
        await _recording_services[site_id].start()
    return _recording_services[site_id]


async def close_all_recording_services() -> None:
    """Close all recording services."""
    for service in _recording_services.values():
        await service.stop()
    _recording_services.clear()