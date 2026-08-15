"""
SuperGuard Alarm - Detection Pipeline

YOLO detection + HSV color filtering + zone filtering.
Pure functions, no global state - all config passed explicitly.

Pipeline stages:
1. YOLODetector: Runs YOLO11n tracking, returns all detections above confidence
2. ZoneFilter: Filters detections by grid zone (normalized coordinates)
3. ColorFilter: Computes HSV color fraction in detection bounding box
4. DetectionPipeline: Orchestrates stages, applies target match logic, draws annotations

Output: ProcessedFrame with original, annotated, matches, all_detections
"""

import cv2
import numpy as np
import time
from typing import List, Tuple, Set
from dataclasses import dataclass

from ..models import Zone, Target, VEHICLE_CLASSES, CLASS_MAP


@dataclass
class Detection:
    """Single detected object from YOLO.
    
    Attributes:
        name: Class name (car, person, bus, etc.) from CLASS_MAP
        confidence: YOLO confidence score 0.0-1.0
        box: [x1, y1, x2, y2] pixel coordinates (top-left to bottom-right)
        color_fraction: Fraction of pixels in box matching HSV color filter (0.0-1.0)
    """
    name: str           # Class name (car, person, bus, etc.)
    confidence: float   # YOLO confidence 0-1
    box: List[float]    # [x1, y1, x2, y2] pixel coordinates
    color_fraction: float  # Fraction of pixels matching color filter (0-1)
    
    @property
    def is_match(self) -> bool:
        """True if this detection matches the target filter.
        
        Simplified check - actual match logic is in DetectionPipeline.process()
        which considers both class filter and color threshold.
        """
        return self.color_fraction > 0  # Simplified - actual check in pipeline


@dataclass
class ProcessedFrame:
    """Frame processed by YOLO pipeline with annotations.
    
    Contains both raw detection data and visual annotation for Telegram.
    
    Attributes:
        original: Unmodified input frame (BGR)
        annotated: Frame with YOLO boxes drawn (green for all, labels with conf + color%)
        matches: Detections passing ALL filters (zone + class + color)
        all_detections: All detections above confidence (after zone filter)
        timestamp: Unix timestamp of processing
        camera_id: Source camera ID (set by caller)
    """
    original: np.ndarray      # Original frame
    annotated: np.ndarray     # Frame with YOLO boxes drawn
    matches: List[Detection]  # Detections matching target
    all_detections: List[Detection]  # All detections above confidence
    timestamp: float
    camera_id: int


class YOLODetector:
    """YOLOv11n object detector wrapper using ultralytics.
    
    Uses model.track() with persist=True for object tracking across frames.
    This gives consistent track IDs for the same physical object.
    
    Attributes:
        model: Loaded YOLO model (ultralytics.YOLO)
        conf: Confidence threshold
        imgsz: Input image size (resized internally by ultralytics)
        class_names: COCO class ID -> name mapping
    """
    
    def __init__(self, model_path: str = "yolo11n.pt", conf: float = 0.35, imgsz: int = 640):
        """Initialize YOLO detector.
        
        Args:
            model_path: Path to .pt model file (auto-downloads if missing)
            conf: Confidence threshold for detections
            imgsz: Inference image size (larger = slower but more accurate)
        """
        from ultralytics import YOLO
        self.model = YOLO(model_path)
        self.conf = conf
        self.imgsz = imgsz
        self.class_names = CLASS_MAP  # COCO class ID -> name
    
    def detect(self, frame: np.ndarray) -> List[Detection]:
        """Run detection on frame, return all detections above confidence.
        
        Uses model.track() with persist=True for tracking.
        Tracking helps maintain consistent IDs for the same object across frames.
        
        Args:
            frame: BGR numpy array (any resolution, resized internally)
            
        Returns:
            List of Detection objects (color_fraction=0, filled later by ColorFilter)
        """
        # persist=True keeps track IDs across calls
        # verbose=False suppresses ultralytics logging
        results = self.model.track(frame, persist=True, verbose=False, conf=self.conf, imgsz=self.imgsz)
        detections = []
        
        if not results or not results[0].boxes:
            return detections
        
        for box in results[0].boxes:
            cls = int(box.cls[0])
            xyxy = box.xyxy[0].tolist()
            name = self.class_names.get(cls, str(cls))
            conf = float(box.conf[0])
            detections.append(Detection(
                name=name,
                confidence=conf,
                box=xyxy,
                color_fraction=0.0,  # Will be filled by color filter
            ))
        
        return detections


class ColorFilter:
    """HSV color filtering for detection regions.
    
    Computes what fraction of pixels in a bounding box match target HSV ranges.
    Used to filter detections by color (e.g., "yellow vehicle", "red car").
    
    OpenCV HSV ranges: H=0-180, S=0-255, V=0-255
    Default is yellow (H=15-40) which matches construction vehicles, taxis, etc.
    
    Attributes:
        ranges: List of (low_hsv, high_hsv) numpy arrays
    """
    
    # Default yellow range (OpenCV HSV: H=0-180)
    DEFAULT_YELLOW_LOW = np.array([15, 60, 80], dtype=np.uint8)
    DEFAULT_YELLOW_HIGH = np.array([40, 255, 255], dtype=np.uint8)
    
    def __init__(self, color_ranges: List[Tuple[List[int], List[int]]] = None):
        """Initialize with HSV ranges.
        
        Args:
            color_ranges: List of (low_hsv, high_hsv) pairs. 
                         Each is [H, S, V] with H=0-180, S/V=0-255.
                         Default: yellow only ([15,60,80] to [40,255,255]).
        """
        if color_ranges is None:
            self.ranges = [(self.DEFAULT_YELLOW_LOW, self.DEFAULT_YELLOW_HIGH)]
        else:
            self.ranges = [
                (np.array(low, dtype=np.uint8), np.array(high, dtype=np.uint8))
                for low, high in color_ranges
            ]
    
    def fraction(self, frame: np.ndarray, box: List[float]) -> float:
        """Compute fraction of pixels in box matching any color range.
        
        Algorithm:
        1. Extract ROI from frame using box coordinates
        2. Convert ROI to HSV
        3. Create combined mask from all HSV ranges (OR operation)
        4. Return mean of mask (fraction of matching pixels)
        
        Args:
            frame: BGR image (full frame)
            box: [x1, y1, x2, y2] pixel coordinates
            
        Returns:
            Fraction 0.0-1.0 of pixels matching color filter
        """
        x1, y1, x2, y2 = [int(v) for v in box]
        h, w = frame.shape[:2]
        
        # Clamp to frame bounds
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        
        if x2 <= x1 or y2 <= y1:
            return 0.0
        
        roi = frame[y1:y2, x1:x2]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        
        mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
        for low, high in self.ranges:
            mask |= cv2.inRange(hsv, low, high)
        
        # mask is 0 or 255, mean gives fraction
        return float(mask.mean() / 255.0)


class ZoneFilter:
    """Grid-based zone filtering.
    
    Checks if detection center point falls within configured zone.
    Uses normalized coordinates (0.0-1.0) so zone works at any resolution.
    """
    
    @staticmethod
    def in_zone(zone: Zone, box: List[float], frame_w: int, frame_h: int) -> bool:
        """Check if object center falls within zone.
        
        Computes normalized center point of bounding box and delegates
        to Zone.contains_point() for the actual check.
        
        Args:
            zone: Zone object (None = whole frame, always True)
            box: [x1, y1, x2, y2] pixel coordinates
            frame_w: Frame width (for normalization)
            frame_h: Frame height (for normalization)
            
        Returns:
            True if detection center is inside zone
        """
        if zone is None:
            return True
        
        x1, y1, x2, y2 = box
        cx = (x1 + x2) / 2 / frame_w
        cy = (y1 + y2) / 2 / frame_h
        
        return zone.contains_point(cx, cy, frame_w, frame_h)


class DetectionPipeline:
    """Complete detection pipeline: YOLO -> Zone -> Color -> Target match.
    
    Orchestrates all filtering stages and produces annotated output.
    All config passed explicitly - no global state.
    
    Pipeline flow for each detection:
    1. YOLODetector.detect() -> all detections above confidence
    2. ZoneFilter.in_zone() -> keep only in-zone detections
    3. Target.matches_class() -> keep only matching classes
    4. ColorFilter.fraction() -> compute color match fraction
    5. Target match decision: (no color filter OR fraction >= threshold)
    
    Drawing: ALL zone-filtered detections drawn on annotated frame
    (green boxes, labels with class + confidence + color%)
    
    Attributes:
        detector: YOLODetector instance
        color_filter: ColorFilter instance
        zone_filter: ZoneFilter instance
        target: Target specification (classes + color ranges)
        min_color_fraction: Minimum color fraction to count as match
    """
    
    def __init__(self, detector: YOLODetector, color_filter: ColorFilter, 
                 zone_filter: ZoneFilter, target: Target, 
                 min_color_fraction: float = 0.15):
        """Initialize pipeline with all components.
        
        Args:
            detector: YOLODetector instance
            color_filter: ColorFilter instance
            zone_filter: ZoneFilter instance
            target: Target specification
            min_color_fraction: Minimum color fraction for match (default 0.15)
        """
        self.detector = detector
        self.color_filter = color_filter
        self.zone_filter = zone_filter
        self.target = target
        self.min_color_fraction = min_color_fraction
    
    def process(self, frame: np.ndarray, zone: Zone) -> ProcessedFrame:
        """Process frame through full pipeline.
        
        Args:
            frame: Input BGR frame
            zone: Zone to filter by (None = whole frame)
            
        Returns:
            ProcessedFrame with original, annotated, matches, all_detections
        """
        # 1. YOLO detection
        all_detections = self.detector.detect(frame)
        h, w = frame.shape[:2]
    
        matches = []
    
        # Create annotated frame (copy for drawing)
        annotated = frame.copy()
    
        for det in all_detections:
            # 2. Zone filter - skip if outside zone
            if not self.zone_filter.in_zone(zone, det.box, w, h):
                continue
        
            # 3. Class filter - skip if class not in target
            if not self.target.matches_class(CLASS_MAP.get(det.name, 999)):
                continue
        
            # 4. Color filter - compute matching pixel fraction
            det.color_fraction = self.color_filter.fraction(frame, det.box)
        
            # 5. Target match decision
            # Match if: no color filter specified OR fraction meets threshold
            color_ok = (not self.target.color_ranges or 
                       det.color_fraction >= self.min_color_fraction)
        
            if color_ok:
                matches.append(det)
        
            # Draw box on annotated frame for ALL detections (zone-filtered)
            x1, y1, x2, y2 = [int(v) for v in det.box]
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
            label = f"{det.name} {det.confidence:.2f}"
            if det.color_fraction > 0:
                label += f" y={det.color_fraction*100:.0f}%"
            cv2.putText(annotated, label, (x1, y1 - 5), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    
        return ProcessedFrame(
            original=frame,
            annotated=annotated,
            matches=matches,
            all_detections=all_detections,
            timestamp=time.time(),
            camera_id=0  # Will be set by caller
        )


def create_pipeline_from_config(config, target: Target, zone: Zone) -> DetectionPipeline:
    """Factory: create pipeline from SuperGuardConfig and per-camera settings.
    
    Convenience function that wires all components with config values.
    
    Args:
        config: SuperGuardConfig (for detection params)
        target: Per-camera Target (from CameraSettings)
        zone: Per-camera Zone (from CameraSettings)
        
    Returns:
        Configured DetectionPipeline instance
    """
    detector = YOLODetector(conf=config.detection.min_conf)
    color_filter = ColorFilter(target.color_ranges if target.color_ranges else None)
    zone_filter = ZoneFilter()
    
    return DetectionPipeline(
        detector=detector,
        color_filter=color_filter,
        zone_filter=zone_filter,
        target=target,
        min_color_fraction=config.detection.yellow_min_fraction,
    )