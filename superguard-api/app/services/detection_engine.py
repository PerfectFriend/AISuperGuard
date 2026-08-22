"""
Detection Engine - Background YOLO processing service.

Integrates superguard/detectors pipeline with FastAPI background tasks.
Runs continuous detection on all enabled cameras, triggers alarms via WS.
"""
import asyncio
import time
import threading
import sys
import base64
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from datetime import datetime
import cv2
import numpy as np

from app.core.config import settings
from app.core.database import get_db
from app.models.models import Camera, Detector, ActuatorBinding, Actuator, Alarm, AlarmState
from sqlalchemy import select

# Add legacy superguard path
sys.path.insert(0, '/home/thomas/SuperGuard')

# Import legacy detection pipeline
from superguard.detectors import (
    YOLODetector, ColorFilter, ZoneFilter, DetectionPipeline, 
    ProcessedFrame, Target
)
from superguard.models import Zone, CameraSettings
from superguard.config import SuperGuardConfig, DetectionConfig


@dataclass
class CameraDetectionState:
    """Per-camera detection state."""
    camera_id: str
    camera_name: str
    detector_id: Optional[str]
    pipeline: Optional[DetectionPipeline]
    zone: Optional[Zone]
    target: Optional[Target]
    last_frame_time: float = 0
    consecutive_matches: int = 0
    consecutive_clean: int = 0
    alarm_active: bool = False
    last_annotated_frame: Optional[np.ndarray] = None


class DetectionEngine:
    """
    Background detection engine.
    
    Runs in separate thread, processes frames from all cameras,
    triggers alarms, updates DB, emits WS events.
    """
    
    def __init__(self, ws_manager=None):
        self.ws_manager = ws_manager
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        
        # Camera states
        self.cameras: Dict[str, CameraDetectionState] = {}
        
        # Detection parameters
        self.detect_every = settings.detection_detect_every  # seconds between detections
        self.update_every = settings.detection_update_every  # seconds between frame updates
        self.min_conf = settings.detection_min_conf
        self.yellow_min_fraction = settings.detection_yellow_min_fraction
        self.auto_resolve_frames = settings.detection_auto_resolve_frames
        self.require_frames = settings.detection_require_frames
        
        # Actuator bindings cache
        self._actuator_bindings: Dict[str, List[str]] = {}
        
    def _create_legacy_config(self) -> SuperGuardConfig:
        """Create legacy SuperGuardConfig for pipeline factory."""
        return SuperGuardConfig(
            detection=DetectionConfig(
                min_conf=self.min_conf,
                update_every=self.update_every,
                detect_every=self.detect_every,
                auto_resolve_frames=self.auto_resolve_frames,
                require_frames=self.require_frames,
                yellow_min_fraction=self.yellow_min_fraction,
            )
        )
    
    async def initialize(self):
        """Load cameras, detectors, zones, targets from DB."""
        async for db in get_db():
            # Load enabled cameras
            result = await db.execute(
                select(Camera).where(Camera.is_enabled == True)
            )
            cameras = result.scalars().all()
            
            for cam in cameras:
                await self._load_camera_state(db, cam)
            
            # Load actuator bindings
            await self._load_actuator_bindings(db)
            
            break
    
    async def _load_camera_state(self, db, camera: Camera):
        """Load zone, target, detector for a camera."""
        # Get detector for this camera (via site)
        result = await db.execute(
            select(Detector).where(
                Detector.site_id == camera.site_id,
                Detector.is_enabled == True
            ).limit(1)
        )
        detector = result.scalars().first()
        
        # Load camera settings (zone, target)
        cfg = camera.config or {}
        zone = None
        target = None
        
        if cfg.get('zone'):
            zone_data = cfg['zone']
            if isinstance(zone_data, list) and len(zone_data) == 3:
                zone = Zone(rows=zone_data[0], cols=zone_data[1], cell=zone_data[2])
        
        if cfg.get('target'):
            target = parse_target_text(cfg['target'])
        
        # Create pipeline if we have detector
        pipeline = None
        if detector:
            pipeline = DetectionPipeline(
                detector=YOLODetector(
                    model_path=detector.model_path or 'yolo11n.pt',
                    conf=detector.confidence_threshold or self.min_conf,
                    imgsz=640
                ),
                color_filter=ColorFilter(target.color_ranges if target and target.color_ranges else None),
                zone_filter=ZoneFilter(),
                target=target if target else Target(),
                min_color_fraction=self.yellow_min_fraction
            )
        
        with self._lock:
            self.cameras[camera.id] = CameraDetectionState(
                camera_id=camera.id,
                camera_name=camera.name,
                detector_id=detector.id if detector else None,
                pipeline=pipeline,
                zone=zone,
                target=target
            )
    
    async def _load_actuator_bindings(self, db):
        """Load camera -> actuator bindings."""
        result = await db.execute(
            select(ActuatorBinding).where(ActuatorBinding.is_active == True)
        )
        bindings = result.scalars().all()
        
        for binding in bindings:
            cam_id = str(binding.camera_id)
            if cam_id not in self._actuator_bindings:
                self._actuator_bindings[cam_id] = []
            # Get actuator name
            act_result = await db.execute(
                select(Actuator).where(Actuator.id == binding.actuator_id)
            )
            actuator = act_result.scalar_one_or_none()
            if actuator:
                self._actuator_bindings[cam_id].append(actuator.name)
    
    def start(self):
        """Start detection loop in background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="detection-engine")
        self._thread.start()
    
    def stop(self):
        """Stop detection engine."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
    
    def _run_loop(self):
        """Main detection loop - runs in background thread."""
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        while self._running:
            try:
                loop.run_until_complete(self._process_all_cameras())
            except Exception as e:
                print(f"[DetectionEngine] Loop error: {e}")
            
            time.sleep(self.detect_every)
        
        loop.close()
    
    async def _process_all_cameras(self):
        """Process one detection cycle for all cameras."""
        async for db in get_db():
            for cam_id, state in list(self.cameras.items()):
                if not state.pipeline:
                    continue
                
                # Get camera from DB to check alive status
                result = await db.execute(select(Camera).where(Camera.id == cam_id))
                camera = result.scalar_one_or_none()
                if not camera or not camera.is_enabled or not camera.is_online:
                    continue
                
                print(f"[DetectionEngine] Processing camera {camera.name} ({camera.id})")
                await self._process_camera(db, camera, state)
            break
    
    async def _process_camera(self, db, camera: Camera, state: CameraDetectionState):
        """Process single camera frame through detection pipeline."""
        # Get frame from camera
        frame = await self._fetch_camera_frame(camera)
        if frame is None:
            return
        
        # Downscale for YOLO if needed (4K -> 1280px max)
        h, w = frame.shape[:2]
        if w > 1280:
            scale = 1280 / w
            frame = cv2.resize(frame, (1280, int(h * scale)))
        
        # Run detection pipeline
        processed: ProcessedFrame = state.pipeline.process(frame, state.zone)
        state.last_annotated_frame = processed.annotated
        state.last_frame_time = time.time()
        
        # Check for matches
        has_matches = len(processed.matches) > 0
        
        if has_matches:
            state.consecutive_matches += 1
            state.consecutive_clean = 0
            
            # Trigger alarm if threshold reached
            if state.consecutive_matches >= self.require_frames and not state.alarm_active:
                await self._trigger_alarm(db, camera, state, processed)
        else:
            state.consecutive_matches = 0
            state.consecutive_clean += 1
            
            # Auto-resolve if alarm active and clean frames threshold reached
            if state.alarm_active and state.consecutive_clean >= self.auto_resolve_frames:
                await self._resolve_alarm(db, camera, state)
        
        # Emit detection stats via WS
        if self.ws_manager and camera.site_id:
            await self.ws_manager.broadcast(str(camera.site_id), {
                "type": "detection.stats",
                "payload": {
                    "camera_id": camera.id,
                    "camera_name": camera.name,
                    "timestamp": datetime.utcnow().isoformat(),
                    "detections": len(processed.all_detections),
                    "matches": len(processed.matches),
                    "match_details": [
                        {
                            "class": m.name,
                            "confidence": m.confidence,
                            "color_fraction": m.color_fraction,
                            "box": m.box
                        }
                        for m in processed.matches
                    ],
                    "alarm_active": state.alarm_active
                }
            })
    
    async def _fetch_camera_frame(self, camera: Camera) -> Optional[np.ndarray]:
        """Fetch frame from camera stream."""
        try:
            import cv2
            cap = cv2.VideoCapture(camera.stream_url)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
            cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 10000)
            
            ret, frame = cap.read()
            cap.release()
            
            if ret and frame is not None:
                return frame
        except Exception as e:
            print(f"[DetectionEngine] Frame fetch error for {camera.name}: {e}")
        return None
    
    async def _trigger_alarm(self, db, camera: Camera, state: CameraDetectionState, processed: ProcessedFrame):
        """Trigger alarm for camera."""
        state.alarm_active = True
        
        # Create alarm record
        alarm = Alarm(
            camera_id=camera.id,
            site_id=camera.site_id,
            detector_id=state.detector_id,
            state=AlarmState.triggered,
            alarm_metadata={
                "matches": len(processed.matches),
                "zone": str(state.zone) if state.zone else "full",
                "target": state.target.description if state.target else "default"
            }
        )
        db.add(alarm)
        await db.flush()
        
        # Turn on bound actuators
        await self._control_actuators(camera.id, True)
        
        # Send WS event
        if self.ws_manager and camera.site_id:
            await self.ws_manager.broadcast(str(camera.site_id), {
                "type": "alarm.triggered",
                "payload": {
                    "alarm_id": alarm.id,
                    "camera_id": camera.id,
                    "camera_name": camera.name,
                    "site_id": str(camera.site_id),
                    "timestamp": datetime.utcnow().isoformat(),
                    "matches": len(processed.matches),
                    "annotated_frame": self._frame_to_base64(processed.annotated)
                }
            })
        
        # Send Telegram notification (async, don't wait)
        asyncio.create_task(self._send_telegram_alarm(camera, processed.annotated, alarm.id))
        
        await db.commit()
    
    async def _resolve_alarm(self, db, camera: Camera, state: CameraDetectionState):
        """Auto-resolve alarm after clean frames."""
        state.alarm_active = False
        state.consecutive_clean = 0
        
        # Find active alarm
        result = await db.execute(
            select(Alarm).where(
                Alarm.camera_id == camera.id,
                Alarm.state == AlarmState.triggered
            ).order_by(Alarm.created_at.desc()).limit(1)
        )
        alarm = result.scalar_one_or_none()
        
        if alarm:
            alarm.state = AlarmState.resolved
            alarm.resolved_at = datetime.utcnow()
            alarm.alarm_metadata = {**alarm.alarm_metadata, "resolve_type": "auto"}
        
        # Turn off bound actuators
        await self._control_actuators(camera.id, False)
        
        # Send WS event
        if self.ws_manager and camera.site_id:
            await self.ws_manager.broadcast(str(camera.site_id), {
                "type": "alarm.resolved",
                "payload": {
                    "camera_id": camera.id,
                    "camera_name": camera.name,
                    "timestamp": datetime.utcnow().isoformat()
                }
            })
        
        await db.commit()
    
    async def _control_actuators(self, camera_id: str, on: bool):
        """Control actuators bound to camera."""
        actuator_names = self._actuator_bindings.get(camera_id, [])
        if not actuator_names:
            return
        
        async for db in get_db():
            for name in actuator_names:
                result = await db.execute(
                    select(Actuator).where(
                        Actuator.name == name,
                        Actuator.is_enabled == True
                    )
                )
                actuator = result.scalar_one_or_none()
                if actuator:
                    # Emit WS event that actuator manager will pick up
                    if self.ws_manager and actuator.site_id:
                        await self.ws_manager.broadcast(str(actuator.site_id), {
                            "type": "actuator.command",
                            "payload": {
                                "actuator_id": actuator.id,
                                "action": "on" if on else "off"
                            }
                        })
            break
    
    async def _send_telegram_alarm(self, camera: Camera, frame: np.ndarray, alarm_id: str):
        """Send alarm notification to Telegram."""
        # TODO: Call Telegram bot API or send via message queue
        pass
    
    def _frame_to_base64(self, frame: np.ndarray) -> str:
        """Encode frame as base64 JPEG."""
        ok, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if ok:
            return base64.b64encode(buf.tobytes()).decode()
        return ""
    
    # Manual control methods (called from API)
    async def manual_trigger(self, camera_id: str):
        """Manually trigger alarm for camera."""
        async for db in get_db():
            result = await db.execute(select(Camera).where(Camera.id == camera_id))
            camera = result.scalar_one_or_none()
            state = self.cameras.get(camera_id)
            
            if camera and state and state.last_annotated_frame is not None:
                # Create a minimal processed frame for trigger
                processed = ProcessedFrame(
                    original=state.last_annotated_frame,
                    annotated=state.last_annotated_frame,
                    matches=[],  # Will be filled by pipeline
                    all_detections=[],
                    timestamp=time.time(),
                    camera_id=camera_id
                )
                await self._trigger_alarm(db, camera, state, processed)
            break
    
    async def manual_cancel(self, camera_id: str):
        """Manually cancel alarm for camera."""
        async for db in get_db():
            state = self.cameras.get(camera_id)
            if state and state.alarm_active:
                # Create a dummy camera object for _resolve_alarm
                result = await db.execute(select(Camera).where(Camera.id == camera_id))
                camera = result.scalar_one_or_none()
                if camera:
                    await self._resolve_alarm(db, camera, state)
            break
    
    def get_camera_state(self, camera_id: str) -> Optional[Dict]:
        """Get current detection state for camera."""
        state = self.cameras.get(camera_id)
        if not state:
            return None
        return {
            "camera_id": camera_id,
            "camera_name": state.camera_name,
            "alarm_active": state.alarm_active,
            "consecutive_matches": state.consecutive_matches,
            "consecutive_clean": state.consecutive_clean,
            "last_frame_time": state.last_frame_time,
            "has_pipeline": state.pipeline is not None,
            "zone": str(state.zone) if state.zone else "full",
            "target": state.target.description if state.target else "default"
        }

    async def test_detector_on_camera(self, detector_id: str, camera_id: str) -> Dict[str, Any]:
        """Test a detector on a specific camera - run single frame detection and return results."""
        state = self.cameras.get(camera_id)
        if not state or not state.pipeline:
            return {
                "detections": [],
                "frame_shape": None,
                "inference_time_ms": None,
                "error": "No pipeline for camera"
            }
        
        # Get frame from camera
        camera = None
        async for db in get_db():
            result = await db.execute(select(Camera).where(Camera.id == camera_id))
            camera = result.scalar_one_or_none()
            break
        
        if not camera:
            return {
                "detections": [],
                "frame_shape": None,
                "inference_time_ms": None,
                "error": "Camera not found"
            }
        
        frame = await self._fetch_camera_frame(camera)
        if frame is None:
            return {
                "detections": [],
                "frame_shape": None,
                "inference_time_ms": None,
                "error": "Failed to fetch frame"
            }
        
        # Downscale for YOLO if needed
        h, w = frame.shape[:2]
        if w > 1280:
            scale = 1280 / w
            frame = cv2.resize(frame, (1280, int(h * scale)))
        
        # Run detection with timing
        import time
        start_time = time.time()
        processed: ProcessedFrame = state.pipeline.process(frame, state.zone)
        inference_time = (time.time() - start_time) * 1000
        
        # Return all detections (not just matches)
        detections = [
            {
                "class": d.name,
                "confidence": float(d.confidence),
                "box": [float(x) for x in d.box],
                "color_fraction": float(d.color_fraction) if d.color_fraction else 0.0,
                "is_match": d in processed.matches
            }
            for d in processed.all_detections
        ]
        
        return {
            "detections": detections,
            "frame_shape": [frame.shape[1], frame.shape[0]],  # width, height
            "inference_time_ms": round(inference_time, 2)
        }


# Import needed for Target parsing
import re
from superguard.models import VEHICLE_CLASSES, CLASS_MAP, COLOR_MAP

def parse_target_text(text: str) -> Target:
    """Parse free-text target description into Target object."""
    if not text:
        return Target()
    
    words = re.findall(r"[a-zа-яё]+", text.lower())
    classes = set()
    color_ranges = []
    recognized = False
    
    for w in words:
        if w in CLASS_MAP:
            classes.add(CLASS_MAP[w])
            recognized = True
        elif w in COLOR_MAP:
            for low, high in COLOR_MAP[w]:
                color_ranges.append((list(low), list(high)))
            recognized = True
    
    if not recognized:
        return Target(description=text)
    
    return Target(
        description=text,
        classes=classes if classes else set(VEHICLE_CLASSES.keys()),
        color_ranges=color_ranges,
    )