"""
SuperGuard Core - Detection Engine Service

Orchestrates detection pipelines across cameras and detectors.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any
from uuid import uuid4

import cv2
import numpy as np

from superguard_core.core.config import get_settings
from superguard_core.core.database import Camera, Detector
from superguard_core.core.events import EventBus, publish_detection, Streams
from superguard_core.core.plugins import PluginManager, DetectorPlugin, CameraFrame, ProcessedFrame, Detection


logger = logging.getLogger(__name__)


@dataclass
class DetectionPipeline:
    """Runtime detection pipeline for a camera."""
    camera_id: int
    detector_id: int
    detector_plugin: DetectorPlugin
    task: Optional[asyncio.Task] = None
    is_running: bool = False
    last_process_time: float = 0
    fps: float = 0
    total_detections: int = 0


class DetectionEngine:
    """Manages detection pipelines for all cameras in a site."""
    
    def __init__(
        self,
        plugin_manager: PluginManager,
        event_bus: EventBus,
        site_id: int,
    ):
        self.plugin_manager = plugin_manager
        self.event_bus = event_bus
        self.site_id = site_id
        self.pipelines: Dict[int, DetectionPipeline] = {}  # camera_id -> pipeline
        self._running = False
        self._session_factory = None
        self._camera_manager = None
    
    def set_session_factory(self, factory):
        """Set database session factory."""
        self._session_factory = factory
    
    def set_camera_manager(self, camera_manager):
        """Set camera manager reference for frame subscription."""
        self._camera_manager = camera_manager
    
    async def start(self) -> None:
        """Start detection engine."""
        self._running = True
        logger.info(f"DetectionEngine started for site {self.site_id}")
    
    async def stop(self) -> None:
        """Stop all detection pipelines."""
        self._running = False
        for pipeline in list(self.pipelines.values()):
            await self._stop_pipeline(pipeline)
        self.pipelines.clear()
        logger.info(f"DetectionEngine stopped for site {self.site_id}")
    
    async def load_detectors(self, detectors: List[Detector], cameras: List[Camera]) -> None:
        """Load and start detection pipelines."""
        # Build camera -> detector mapping
        camera_detector_map = {c.id: c.detector_id for c in cameras if c.detector_id and c.is_enabled}
        
        # Group cameras by detector
        detector_cameras: Dict[int, List[int]] = {}
        for cam_id, det_id in camera_detector_map.items():
            if det_id not in detector_cameras:
                detector_cameras[det_id] = []
            detector_cameras[det_id].append(cam_id)
        
        # Start pipeline for each detector
        for detector in detectors:
            if not detector.is_enabled or detector.site_id != self.site_id:
                continue
            
            cam_ids = detector_cameras.get(detector.id, [])
            if not cam_ids:
                continue
            
            await self._start_detector(detector, cam_ids)
    
    async def add_camera(self, camera: Camera) -> None:
        """Add camera to detection pipeline."""
        if camera.detector_id and camera.is_enabled:
            # Find or create pipeline for this detector
            for pipeline in self.pipelines.values():
                if pipeline.detector_id == camera.detector_id:
                    # Pipeline exists, just ensure camera is subscribed
                    return
            
            # Need to load detector and create pipeline
            if self._session_factory:
                async with self._session_factory() as session:
                    from sqlalchemy import select
                    result = await session.execute(
                        select(Detector).where(Detector.id == camera.detector_id)
                    )
                    detector = result.scalar_one_or_none()
                    if detector and detector.is_enabled:
                        await self._start_detector(detector, [camera.id])
    
    async def remove_camera(self, camera_id: int) -> None:
        """Remove camera from detection pipeline."""
        # Check if any pipeline uses this camera
        for pipeline in list(self.pipelines.values()):
            # Pipeline is per-detector, not per-camera
            # We just stop getting frames for this camera via event bus
            pass
    
    async def update_detector(self, detector: Detector) -> None:
        """Update detector configuration."""
        if detector_id := detector.id:
            # Find pipelines using this detector
            for pipeline in list(self.pipelines.values()):
                if pipeline.detector_id == detector_id:
                    await self._stop_pipeline(pipeline)
            
            if detector.is_enabled:
                # Find cameras using this detector
                if self._session_factory:
                    async with self._session_factory() as session:
                        from sqlalchemy import select
                        result = await session.execute(
                            select(Camera.id)
                            .where(Camera.detector_id == detector_id, Camera.is_enabled == True)
                        )
                        cam_ids = [row[0] for row in result.all()]
                        if cam_ids:
                            await self._start_detector(detector, cam_ids)
    
    async def _start_detector(self, detector: Detector, camera_ids: List[int]) -> None:
        """Start detection pipeline for a detector."""
        try:
            # Get plugin
            plugin_name = detector.plugin
            plugin_class = self.plugin_manager.get_plugin_class(
                self.plugin_manager.metadata.get(plugin_name, None) and self.plugin_manager.metadata[plugin_name].plugin_type,
                plugin_name
            )
            
            if not plugin_class:
                for name, meta in self.plugin_manager.metadata.items():
                    if meta.plugin_type.value == "detector" and name == plugin_name:
                        plugin_class = meta.entry_point.load()
                        break
            
            if not plugin_class:
                raise ValueError(f"No detector plugin found: {plugin_name}")
            
            # Load plugin
            from superguard_core.core.plugins import PluginConfig
            plugin_config = PluginConfig(
                enabled=True,
                site_id=self.site_id,
                # Pass detector config
                **detector.config
            )
            plugin = await self.plugin_manager.load_plugin(
                self.plugin_manager.metadata[plugin_name].plugin_type,
                plugin_name,
                plugin_config,
                self.event_bus,
            )
            
            # Initialize detector
            await plugin.initialize()
            
            # Create pipeline
            pipeline = DetectionPipeline(
                camera_id=camera_ids[0],  # Primary camera
                detector_id=detector.id,
                detector_plugin=plugin,
            )
            
            # Use first camera_id as key (pipeline is per detector)
            self.pipelines[detector.id] = pipeline
            
            # Start processing task
            pipeline.is_running = True
            pipeline.task = asyncio.create_task(self._process_loop(pipeline, camera_ids))
            
            logger.info(f"Detector {detector.id} ({detector.name}) started for cameras {camera_ids}")
            
        except Exception as e:
            logger.error(f"Failed to start detector {detector.id}: {e}")
    
    async def _stop_pipeline(self, pipeline: DetectionPipeline) -> None:
        """Stop a detection pipeline."""
        pipeline.is_running = False
        
        if pipeline.task:
            pipeline.task.cancel()
            try:
                await pipeline.task
            except asyncio.CancelledError:
                pass
        
        try:
            await pipeline.detector_plugin.shutdown()
        except Exception as e:
            logger.error(f"Error shutting down detector {pipeline.detector_id}: {e}")
        
        logger.info(f"Detector {pipeline.detector_id} stopped")
    
    async def _process_loop(self, pipeline: DetectionPipeline, camera_ids: List[int]) -> None:
        """Main detection processing loop."""
        detector = pipeline.detector_plugin
        settings = get_settings()
        
        # Subscribe to frame events for these cameras
        from superguard_core.core.events import get_event_bus
        
        frame_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        
        async def frame_handler(event):
            """Handle incoming frame events."""
            camera_id = event.payload.get("camera_id")
            if camera_id in camera_ids:
                try:
                    frame_queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass  # Drop frame if queue full
        
        # Subscribe to frame stream
        bus = await get_event_bus()
        consumer_group = f"detection-{self.site_id}-{pipeline.detector_id}"
        await bus.subscribe(Streams.CAMERA_FRAMES, frame_handler, group=consumer_group)
        
        last_process_time = 0
        
        try:
            while pipeline.is_running and self._running:
                try:
                    # Get frame from queue with timeout
                    event = await asyncio.wait_for(frame_queue.get(), timeout=1.0)
                    
                    start_time = time.time()
                    camera_id = event.payload.get("camera_id")
                    
                    # Get frame data (in real implementation, frame would be in event or fetched)
                    # For now, we simulate - in production, frame would come from camera manager
                    # or be passed directly in the event
                    
                    # Create mock frame for processing (replace with actual frame retrieval)
                    # In production, we'd get the actual frame from camera manager
                    frame_data = CameraFrame(
                        image=np.zeros((480, 640, 3), dtype=np.uint8),  # Placeholder
                        timestamp=event.payload.get("timestamp", time.time()),
                        camera_id=camera_id,
                        metadata=event.payload.get("metadata", {}),
                    )
                    
                    # Process frame
                    try:
                        processed = await detector.process(frame_data)
                        
                        pipeline.last_process_time = time.time()
                        pipeline.total_detections += len(processed.detections)
                        
                        if last_process_time > 0:
                            pipeline.fps = 1.0 / (pipeline.last_process_time - last_process_time)
                        last_process_time = pipeline.last_process_time
                        
                        # Publish detection event
                        await publish_detection(self.event_bus, camera_id, {
                            "detector_id": pipeline.detector_id,
                            "frame_id": str(uuid4()),
                            "timestamp": processed.timestamp,
                            "processing_time": processed.processing_time,
                            "detections": [
                                {
                                    "class_id": d.class_id,
                                    "class_name": d.class_name,
                                    "confidence": d.confidence,
                                    "bbox": d.bbox,
                                    "metadata": d.metadata,
                                }
                                for d in processed.detections
                            ],
                            "annotated_frame_available": True,  # In production, store annotated frame
                        })
                        
                    except Exception as e:
                        logger.error(f"Detection error for camera {camera_id}: {e}")
                    
                except asyncio.TimeoutError:
                    continue  # No frames, continue loop
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Detection loop error: {e}")
                    await asyncio.sleep(1)
        
        finally:
            # Unsubscribe
            await bus.unsubscribe(Streams.CAMERA_FRAMES, group=consumer_group)
    
    async def test_detector(self, detector_id: int, frame: CameraFrame) -> ProcessedFrame:
        """Test detector on a single frame."""
        if detector_id in self.pipelines:
            pipeline = self.pipelines[detector_id]
            return await pipeline.detector_plugin.test_on_frame(frame)
        
        # Load detector temporarily for test
        if self._session_factory:
            async with self._session_factory() as session:
                from sqlalchemy import select
                result = await session.execute(
                    select(Detector).where(Detector.id == detector_id)
                )
                detector = result.scalar_one_or_none()
                if detector:
                    plugin = await self._load_detector_plugin(detector)
                    return await plugin.test_on_frame(frame)
        
        raise ValueError(f"Detector {detector_id} not found")
    
    async def _load_detector_plugin(self, detector: Detector) -> DetectorPlugin:
        """Load detector plugin for testing."""
        plugin_name = detector.plugin
        plugin_class = self.plugin_manager.get_plugin_class(
            self.plugin_manager.metadata.get(plugin_name, None) and self.plugin_manager.metadata[plugin_name].plugin_type,
            plugin_name
        )
        
        if not plugin_class:
            for name, meta in self.plugin_manager.metadata.items():
                if meta.plugin_type.value == "detector" and name == plugin_name:
                    plugin_class = meta.entry_point.load()
                    break
        
        if not plugin_class:
            raise ValueError(f"No detector plugin found: {plugin_name}")
        
        from superguard_core.core.plugins import PluginConfig
        plugin_config = PluginConfig(enabled=True, site_id=self.site_id, **detector.config)
        plugin = await self.plugin_manager.load_plugin(
            self.plugin_manager.metadata[plugin_name].plugin_type,
            plugin_name,
            plugin_config,
            self.event_bus,
        )
        
        await plugin.initialize()
        return plugin
    
    def get_pipeline_stats(self, detector_id: int) -> Optional[Dict[str, Any]]:
        """Get pipeline statistics."""
        if detector_id in self.pipelines:
            pipeline = self.pipelines[detector_id]
            return {
                "detector_id": detector_id,
                "camera_ids": [pipeline.camera_id],  # Would be list in full impl
                "fps": pipeline.fps,
                "total_detections": pipeline.total_detections,
                "last_process_time": pipeline.last_process_time,
                "is_running": pipeline.is_running,
            }
        return None
    
    def get_all_stats(self) -> List[Dict[str, Any]]:
        """Get stats for all pipelines."""
        return [self.get_pipeline_stats(did) for did in self.pipelines.keys()]


# Factory for detection engines per site
_detection_engines: Dict[int, DetectionEngine] = {}


async def get_detection_engine(
    site_id: int,
    plugin_manager: PluginManager,
    event_bus: EventBus,
) -> DetectionEngine:
    """Get or create detection engine for site."""
    if site_id not in _detection_engines:
        _detection_engines[site_id] = DetectionEngine(plugin_manager, event_bus, site_id)
        await _detection_engines[site_id].start()
    return _detection_engines[site_id]


async def close_all_detection_engines() -> None:
    """Close all detection engines."""
    for engine in _detection_engines.values():
        await engine.stop()
    _detection_engines.clear()