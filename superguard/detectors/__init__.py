"""
SuperGuard Alarm - Detection Pipeline

YOLO detection + HSV color filtering + zone filtering.
Pure functions, no global state - all config passed explicitly.
"""
import cv2
import numpy as np
from typing import List, Tuple, Set
from dataclasses import dataclass

from ..models import Zone, Target, VEHICLE_CLASSES, CLASS_MAP


@dataclass
class Detection:
    """Single detected object."""
    name: str           # Class name (car, person, bus, etc.)
    confidence: float   # YOLO confidence 0-1
    box: List[float]    # [x1, y1, x2, y2] pixel coordinates
    color_fraction: float  # Fraction of pixels matching color filter (0-1)
    
    @property
    def is_match(self) -> bool:
        """True if this detection matches the target filter."""
        return self.color_fraction > 0  # Simplified - actual check in pipeline


class YOLODetector:
    """YOLOv11n object detector wrapper."""
    
    def __init__(self, model_path: str = "yolo11n.pt", conf: float = 0.35, imgsz: int = 640):
        from ultralytics import YOLO
        self.model = YOLO(model_path)
        self.conf = conf
        self.imgsz = imgsz
        self.class_names = CLASS_MAP  # COCO class ID -> name
    
    def detect(self, frame: np.ndarray) -> List[Detection]:
        """Run detection on frame, return all detections above confidence."""
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
    """HSV color filtering for detection regions."""
    
    # Default yellow range (OpenCV HSV: H=0-180)
    DEFAULT_YELLOW_LOW = np.array([15, 60, 80], dtype=np.uint8)
    DEFAULT_YELLOW_HIGH = np.array([40, 255, 255], dtype=np.uint8)
    
    def __init__(self, color_ranges: List[Tuple[List[int], List[int]]] = None):
        """Initialize with HSV ranges.
        
        Args:
            color_ranges: List of (low_hsv, high_hsv) pairs. 
                         Default: yellow only.
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
        
        Args:
            frame: BGR image
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
        
        return float(mask.mean() / 255.0)


class ZoneFilter:
    """Grid-based zone filtering."""
    
    @staticmethod
    def in_zone(zone: Zone, box: List[float], frame_w: int, frame_h: int) -> bool:
        """Check if object center falls within zone."""
        if zone is None:
            return True
        
        x1, y1, x2, y2 = box
        cx = (x1 + x2) / 2 / frame_w
        cy = (y1 + y2) / 2 / frame_h
        
        return zone.contains_point(cx, cy, frame_w, frame_h)


class DetectionPipeline:
    """Complete detection pipeline: YOLO -> Zone -> Color -> Target match."""
    
    def __init__(self, detector: YOLODetector, color_filter: ColorFilter, 
                 zone_filter: ZoneFilter, target: Target, 
                 min_color_fraction: float = 0.15):
        self.detector = detector
        self.color_filter = color_filter
        self.zone_filter = zone_filter
        self.target = target
        self.min_color_fraction = min_color_fraction
    
    def process(self, frame: np.ndarray, zone: Zone) -> Tuple[List[Detection], List[Detection]]:
        """Process frame through full pipeline.
        
        Returns:
            (matches, all_detections) where matches = target filter passed
        """
        # 1. YOLO detection
        all_detections = self.detector.detect(frame)
        h, w = frame.shape[:2]
        
        matches = []
        
        for det in all_detections:
            # 2. Zone filter
            if not self.zone_filter.in_zone(zone, det.box, w, h):
                continue
            
            # 3. Class filter
            if not self.target.matches_class(CLASS_MAP.get(det.name, 999)):
                continue
            
            # 4. Color filter
            det.color_fraction = self.color_filter.fraction(frame, det.box)
            
            # 5. Target match decision
            color_ok = (not self.target.color_ranges or 
                       det.color_fraction >= self.min_color_fraction)
            
            if color_ok:
                matches.append(det)
        
        return matches, all_detections


def create_pipeline_from_config(config, target: Target, zone: Zone) -> DetectionPipeline:
    """Factory: create pipeline from SuperGuardConfig and per-camera settings."""
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