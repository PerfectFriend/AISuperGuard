"""
Detection Engine - Background YOLO processing service.

Integrates superguard/detectors pipeline with FastAPI background tasks.
Runs continuous detection on all enabled cameras, triggers alarms via WS.
"""
import asyncio
import logging

logger = logging.getLogger(__name__)
import time
import threading
import sys
import base64
import io
from typing import Optional, Dict, List, Any, Union
from dataclasses import dataclass
from datetime import datetime
import cv2
import numpy as np

from app.core.config import settings
from app.core.database import get_db
from app.models.models import Camera, Detector, ActuatorBinding, Actuator, Alarm, AlarmState
from sqlalchemy import select

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode


# ============================================================================
# Inline Detection Classes (replacing legacy superguard module)
# ============================================================================

from ultralytics import YOLO


class YOLODetector:
    """YOLO-based object detector."""
    
    def __init__(self, model_path: str = 'yolo11n.pt', conf: float = 0.5, imgsz: int = 640):
        self.model = YOLO(model_path)
        self.conf = conf
        self.imgsz = imgsz
    
    def detect(self, frame: np.ndarray) -> List[Dict]:
        """Run detection on frame, return list of detections."""
        results = self.model(frame, conf=self.conf, imgsz=self.imgsz, verbose=False)
        detections = []
        for r in results:
            boxes = r.boxes
            for box in boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                conf = box.conf[0].cpu().numpy()
                cls = int(box.cls[0].cpu().numpy())
                detections.append({
                    'bbox': [float(x1), float(y1), float(x2), float(y2)],
                    'conf': float(conf),
                    'class': cls,
                    'class_name': self.model.names[cls]
                })
        return detections


class ColorFilter:
    """HSV color filter for target filtering."""
    
    def __init__(self, color_ranges: Optional[List[Dict]] = None):
        self.color_ranges = color_ranges or []
    
    def filter(self, frame: np.ndarray, bbox: List[float]) -> float:
        """Return color match fraction (0-1) for bbox region."""
        if not self.color_ranges:
            return 1.0
        
        x1, y1, x2, y2 = map(int, bbox)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return 0.0
        
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        total_pixels = roi.shape[0] * roi.shape[1]
        max_match = 0.0
        
        for cr in self.color_ranges:
            lower = np.array(cr.get('lower', [0, 0, 0]))
            upper = np.array(cr.get('upper', [180, 255, 255]))
            mask = cv2.inRange(hsv, lower, upper)
            match = cv2.countNonZero(mask) / total_pixels
            max_match = max(max_match, match)
        
        return max_match


class ZoneFilter:
    """Zone/grid filter for detection zone checking."""
    
    def __init__(self, rows: int = 3, cols: int = 4, cell: int = 1):
        self.rows = rows
        self.cols = cols
        self.cell = cell
    
    def check(self, frame_shape: tuple, bbox: List[float]) -> bool:
        """Check if bbox center falls in target cell."""
        h, w = frame_shape[:2]
        cx = (bbox[0] + bbox[2]) / 2
        cy = (bbox[1] + bbox[3]) / 2
        
        cell_w = w / self.cols
        cell_h = h / self.rows
        
        col = int(cx / cell_w)
        row = int(cy / cell_h)
        
        target_cell = row * self.cols + col + 1
        return target_cell == self.cell


@dataclass
class Target:
    """Detection target configuration."""
    classes: List[int] = None
    color_ranges: List[Dict] = None
    description: str = ""
    
    def __post_init__(self):
        if self.classes is None:
            self.classes = [0, 2, 3, 5, 7]  # person, car, motorcycle, bus, truck
        if self.color_ranges is None:
            self.color_ranges = []


@dataclass
class Zone:
    """Zone configuration."""
    rows: int = 3
    cols: int = 4
    cell: int = 1


@dataclass
class ProcessedFrame:
    """Processed frame with detection results."""
    frame: np.ndarray
    detections: List[Dict]
    timestamp: float
    annotated: Optional[np.ndarray] = None
    matches: List[Dict] = None
    all_detections: List[Dict] = None


class DetectionPipeline:
    """Complete detection pipeline: YOLO -> Color -> Zone -> Trigger."""
    
    def __init__(self, detector: YOLODetector, color_filter: ColorFilter, 
                 zone_filter: ZoneFilter, target: Target, min_color_fraction: float = 0.15):
        self.detector = detector
        self.color_filter = color_filter
        self.zone_filter = zone_filter
        self.target = target
        self.min_color_fraction = min_color_fraction
    
    def process(self, frame: np.ndarray) -> ProcessedFrame:
        """Run full pipeline on frame."""
        detections = self.detector.detect(frame)
        
        filtered = []
        for det in detections:
            # Class filter
            if self.target.classes and det['class'] not in self.target.classes:
                continue
            
            # Zone filter
            if self.zone_filter and not self.zone_filter.check(frame.shape, det['bbox']):
                continue
            
            # Color filter
            color_frac = self.color_filter.filter(frame, det['bbox'])
            if color_frac < self.min_color_fraction:
                continue
            
            filtered.append({**det, 'color_fraction': color_frac})
        
        # Create annotated frame (draw boxes)
        annotated = frame.copy()
        for det in filtered:
            x1, y1, x2, y2 = map(int, det['bbox'])
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
            label = f"{det['class_name']} {det['conf']:.2f}"
            cv2.putText(annotated, label, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
        return ProcessedFrame(
            frame=frame, 
            detections=filtered, 
            timestamp=time.time(),
            matches=filtered,
            all_detections=detections,
            annotated=annotated
        )


def parse_target_text(text: str) -> Target:
    """Parse target text like 'car red zone 5' into Target object."""
    target = Target()
    parts = text.lower().split()
    
    class_map = {
        'person': 0, 'bicycle': 1, 'car': 2, 'motorcycle': 3,
        'bus': 5, 'truck': 7
    }
    
    i = 0
    while i < len(parts):
        part = parts[i]
        if part in class_map:
            target.classes = [class_map[part]]
        elif part == 'red' or part == 'красный':
            # Add red color ranges (HSV)
            target.color_ranges = [
                {'lower': [0, 100, 100], 'upper': [10, 255, 255]},
                {'lower': [170, 100, 100], 'upper': [180, 255, 255]}
            ]
        elif part == 'zone' and i + 1 < len(parts) and parts[i + 1].isdigit():
            # Zone cell number - stored in target description for reference
            target.description = f"zone {parts[i + 1]}"
            i += 1
        i += 1
    
    return target


# ============================================================================
# Original Detection Engine continues below
# ============================================================================


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
            # Add red color ranges for "red car" target
            if 'red' in cfg['target'].lower() or 'красн' in cfg['target'].lower():
                target.color_ranges = [
                    {'lower': [0, 100, 100], 'upper': [10, 255, 255]},
                    {'lower': [170, 100, 100], 'upper': [180, 255, 255]}
                ]
        
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
                zone_filter=ZoneFilter(zone.rows if zone else 3, zone.cols if zone else 3, zone.cell if zone else 5),
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
        """Start detection loop as asyncio task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop_async())
    
    def stop(self):
        """Stop detection engine."""
        self._running = False
        if self._task:
            self._task.cancel()
    
    async def _run_loop_async(self):
        """Main detection loop - runs as asyncio task in main event loop."""
        while self._running:
            try:
                await self._process_all_cameras()
            except Exception as e:
                print(f"[DetectionEngine] Loop error: {e}")
            
            await asyncio.sleep(self.detect_every)
    
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
        processed: ProcessedFrame = state.pipeline.process(frame)
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
                            "class": m['class_name'],
                            "confidence": m['conf'],
                            "color_fraction": m['color_fraction'],
                            "box": m['bbox']
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
        
        # Build match details robustly
        match_details = []
        for m in processed.matches:
            # Ensure all expected keys exist with defaults
            cm = m if isinstance(m, dict) else {}
            match_details.append({
                "class_name": cm.get('class_name', 'unknown'),
                "conf": float(cm.get('conf', 0.0)),
                "color_fraction": float(cm.get('color_fraction', 0.0)),
                "bbox": cm.get('bbox', [0, 0, 0, 0])
            })
        
        # Create alarm record with robust field extraction
        primary_match = match_details[0] if match_details else None
        confidence = primary_match['conf'] if primary_match else None
        detection_class = primary_match['class_name'] if primary_match else None
        color_fraction = primary_match['color_fraction'] if primary_match else None
        
        alarm = Alarm(
            camera_id=camera.id,
            site_id=camera.site_id,
            detector_id=state.detector_id,
            state=AlarmState.triggered,
            confidence=confidence,
            detection_class=detection_class,
            color_fraction=color_fraction,
            alarm_metadata={
                "matches": len(processed.matches),
                "zone": str(state.zone) if state.zone else "full",
                "target": state.target.description if state.target else "default",
                "match_details": match_details
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
                    "match_details": match_details,
                    "annotated_frame": self._frame_to_base64(processed.annotated)
                }
            })
        
        # Send Telegram notification with inline keyboard (async, don't wait)
        asyncio.create_task(self._send_telegram_alarm(camera, processed.annotated, alarm.id, match_details))
        
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
                    
                        # Also call actuator engine directly if available (for immediate execution)
                        try:
                            from app.main import app
                            actuator_engine = getattr(app.state, 'actuator_engine', None)
                            if actuator_engine:
                                await actuator_engine.queue_command(actuator.id, "on" if on else "off")
                        except Exception as e:
                            logger.warning(f"Could not queue command to actuator engine: {e}")
                break
    
    async def _send_telegram_alarm(self, camera: Camera, frame: np.ndarray, alarm_id: str, match_details: list):
        """Send alarm notification to Telegram via bot."""
        try:
            from app.services.telegram_bot import get_telegram_bot
            bot = await get_telegram_bot()
            if bot and bot.application:
                # Build caption with match details
                caption = f"🚨 <b>ALARM TRIGGERED</b>\n\n"
                caption += f"📷 <b>Camera:</b> {camera.name}\n"
                caption += f"🕐 <b>Time:</b> {datetime.utcnow().strftime('%H:%M:%S')}\n\n"
                
                if match_details:
                    caption += f"<b>Detections:</b>\n"
                    for i, m in enumerate(match_details[:3], 1):  # Top 3 matches
                        caption += f"  {i}. {m['class_name']} ({m['conf']:.2f}) - color: {m['color_fraction']:.2f}\n"
                
                caption += f"\n🆔 <code>{alarm_id}</code>"
                
                # Send photo with inline keyboard
                import io
                ok, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                if ok:
                    photo_bytes = io.BytesIO(buf.tobytes())
                    photo_bytes.seek(0)
                    
                    keyboard = [
                        [InlineKeyboardButton("✅ Acknowledge", callback_data=f"alarm:ack:{alarm_id}")],
                        [InlineKeyboardButton("🔕 Silence", callback_data=f"alarm:silence:{alarm_id}")],
                        [InlineKeyboardButton("📷 Camera View", callback_data=f"camera:view:{camera.id}")]
                    ]
                    
                    await bot.application.bot.send_photo(
                        chat_id=bot.chat_id,
                        photo=photo_bytes,
                        caption=caption,
                        parse_mode=ParseMode.HTML,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
        except Exception as e:
            print(f"[DetectionEngine] Telegram alarm send error: {e}")
    
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
                    frame=state.last_annotated_frame,
                    annotated=state.last_annotated_frame,
                    detections=[],
                    matches=[],
                    all_detections=[],
                    timestamp=time.time()
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
        processed: ProcessedFrame = state.pipeline.process(frame)
        inference_time = (time.time() - start_time) * 1000
        
        # Return all detections (not just matches)
        detections = [
            {
                "class": d.get('class_name', ''),
                "confidence": float(d.get('conf', 0)),
                "box": [float(x) for x in d.get('bbox', [0,0,0,0])],
                "color_fraction": float(d.get('color_fraction', 0.0)),
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

# ============================================================================
# Inline Constants (replacing superguard.models)
# ============================================================================

VEHICLE_CLASSES = {
    'person': 0, 'bicycle': 1, 'car': 2, 'motorcycle': 3,
    'bus': 5, 'truck': 7
}

CLASS_MAP = {
    'person': 0, 'человек': 0, 'person': 0,
    'bicycle': 1, 'велосипед': 1,
    'car': 2, 'машина': 2, 'авто': 2, 'car': 2,
    'motorcycle': 3, 'мотоцикл': 3, 'байк': 3,
    'bus': 5, 'автобус': 5,
    'truck': 7, 'грузовик': 7, 'фура': 7,
}

COLOR_MAP = {
    'red': [([0, 100, 100], [10, 255, 255]), ([170, 100, 100], [180, 255, 255])],
    'красный': [([0, 100, 100], [10, 255, 255]), ([170, 100, 100], [180, 255, 255])],
    'yellow': [([20, 100, 100], [30, 255, 255])],
    'жёлтый': [([20, 100, 100], [30, 255, 255])],
    'green': [([40, 50, 50], [80, 255, 255])],
    'зелёный': [([40, 50, 50], [80, 255, 255])],
    'blue': [([100, 50, 50], [130, 255, 255])],
    'синий': [([100, 50, 50], [130, 255, 255])],
    'white': [([0, 0, 200], [180, 30, 255])],
    'белый': [([0, 0, 200], [180, 30, 255])],
    'black': [([0, 0, 0], [180, 255, 50])],
    'чёрный': [([0, 0, 0], [180, 255, 50])],
}

VEHICLE_CLASSES_SET = set(VEHICLE_CLASSES.values())

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
        classes=list(classes) if classes else list(VEHICLE_CLASSES.keys()),
        color_ranges=color_ranges,
    )