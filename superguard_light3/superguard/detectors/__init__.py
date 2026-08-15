import cv2
import numpy as np
import time
from typing import List, Tuple, Set
from dataclasses import dataclass
from ..models import Zone, Target, VEHICLE_CLASSES, CLASS_MAP

@dataclass
class Detection:
    name: str
    confidence: float
    box: List[float]
    color_fraction: float

    @property
    def is_match(self) -> bool:
        return self.color_fraction > 0

@dataclass
class ProcessedFrame:
    original: np.ndarray
    annotated: np.ndarray
    matches: List[Detection]
    all_detections: List[Detection]
    timestamp: float
    camera_id: int

class YOLODetector:

    def __init__(self, model_path: str='yolo11n.pt', conf: float=0.35, imgsz: int=640):
        from ultralytics import YOLO
        self.model = YOLO(model_path)
        self.conf = conf
        self.imgsz = imgsz
        self.class_names = CLASS_MAP

    def detect(self, frame: np.ndarray) -> List[Detection]:
        results = self.model.track(frame, persist=True, verbose=False, conf=self.conf, imgsz=self.imgsz)
        detections = []
        if not results or not results[0].boxes:
            return detections
        for box in results[0].boxes:
            cls = int(box.cls[0])
            xyxy = box.xyxy[0].tolist()
            name = self.class_names.get(cls, str(cls))
            conf = float(box.conf[0])
            detections.append(Detection(name=name, confidence=conf, box=xyxy, color_fraction=0.0))
        return detections

class ColorFilter:
    DEFAULT_YELLOW_LOW = np.array([15, 60, 80], dtype=np.uint8)
    DEFAULT_YELLOW_HIGH = np.array([40, 255, 255], dtype=np.uint8)

    def __init__(self, color_ranges: List[Tuple[List[int], List[int]]]=None):
        if color_ranges is None:
            self.ranges = [(self.DEFAULT_YELLOW_LOW, self.DEFAULT_YELLOW_HIGH)]
        else:
            self.ranges = [(np.array(low, dtype=np.uint8), np.array(high, dtype=np.uint8)) for low, high in color_ranges]

    def fraction(self, frame: np.ndarray, box: List[float]) -> float:
        x1, y1, x2, y2 = [int(v) for v in box]
        h, w = frame.shape[:2]
        x1, y1 = (max(0, x1), max(0, y1))
        x2, y2 = (min(w, x2), min(h, y2))
        if x2 <= x1 or y2 <= y1:
            return 0.0
        roi = frame[y1:y2, x1:x2]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
        for low, high in self.ranges:
            mask |= cv2.inRange(hsv, low, high)
        return float(mask.mean() / 255.0)

class ZoneFilter:

    @staticmethod
    def in_zone(zone: Zone, box: List[float], frame_w: int, frame_h: int) -> bool:
        if zone is None:
            return True
        x1, y1, x2, y2 = box
        cx = (x1 + x2) / 2 / frame_w
        cy = (y1 + y2) / 2 / frame_h
        return zone.contains_point(cx, cy, frame_w, frame_h)

class DetectionPipeline:

    def __init__(self, detector: YOLODetector, color_filter: ColorFilter, zone_filter: ZoneFilter, target: Target, min_color_fraction: float=0.15):
        self.detector = detector
        self.color_filter = color_filter
        self.zone_filter = zone_filter
        self.target = target
        self.min_color_fraction = min_color_fraction

    def process(self, frame: np.ndarray, zone: Zone) -> ProcessedFrame:
        all_detections = self.detector.detect(frame)
        h, w = frame.shape[:2]
        matches = []
        annotated = frame.copy()
        for det in all_detections:
            if not self.zone_filter.in_zone(zone, det.box, w, h):
                continue
            if not self.target.matches_class(CLASS_MAP.get(det.name, 999)):
                continue
            det.color_fraction = self.color_filter.fraction(frame, det.box)
            color_ok = not self.target.color_ranges or det.color_fraction >= self.min_color_fraction
            if color_ok:
                matches.append(det)
            x1, y1, x2, y2 = [int(v) for v in det.box]
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
            label = f'{det.name} {det.confidence:.2f}'
            if det.color_fraction > 0:
                label += f' y={det.color_fraction * 100:.0f}%'
            cv2.putText(annotated, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        return ProcessedFrame(original=frame, annotated=annotated, matches=matches, all_detections=all_detections, timestamp=time.time(), camera_id=0)

def create_pipeline_from_config(config, target: Target, zone: Zone) -> DetectionPipeline:
    detector = YOLODetector(conf=config.detection.min_conf)
    color_filter = ColorFilter(target.color_ranges if target.color_ranges else None)
    zone_filter = ZoneFilter()
    return DetectionPipeline(detector=detector, color_filter=color_filter, zone_filter=zone_filter, target=target, min_color_fraction=config.detection.yellow_min_fraction)