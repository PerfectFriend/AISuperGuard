"""
SuperGuard Core - YOLO ONNX Detector Plugin

YOLO11n detection using ONNX Runtime for cross-platform inference.
"""

import asyncio
import logging
import time
from typing import List, Optional

import cv2
import numpy as np
import onnxruntime as ort

from superguard_core.core.plugins import DetectorPlugin, CameraFrame, ProcessedFrame, Detection, PluginConfig


logger = logging.getLogger(__name__)


class YoloOnnxDetectorPlugin(DetectorPlugin):
    """YOLO detector using ONNX Runtime."""
    
    name = "yolo_onnx"
    version = "1.0.0"
    plugin_type = "detector"
    description = "YOLO11n object detection via ONNX Runtime"
    author = "SuperGuard Team"
    
    # COCO class names (YOLO default)
    COCO_CLASSES = [
        'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck',
        'boat', 'traffic light', 'fire hydrant', 'stop sign', 'parking meter', 'bench',
        'bird', 'cat', 'dog', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra',
        'giraffe', 'backpack', 'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee',
        'skis', 'snowboard', 'sports ball', 'kite', 'baseball bat', 'baseball glove',
        'skateboard', 'surfboard', 'tennis racket', 'bottle', 'wine glass', 'cup',
        'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple', 'sandwich', 'orange',
        'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake', 'chair', 'couch',
        'potted plant', 'bed', 'dining table', 'toilet', 'tv', 'laptop', 'mouse',
        'remote', 'keyboard', 'cell phone', 'microwave', 'oven', 'toaster', 'sink',
        'refrigerator', 'book', 'clock', 'vase', 'scissors', 'teddy bear', 'hair drier',
        'toothbrush'
    ]
    
    def __init__(self, config: PluginConfig, event_bus):
        super().__init__(config, event_bus)
        self._session: Optional[ort.InferenceSession] = None
        self._input_name: str = ""
        self._output_names: List[str] = []
        self._input_shape: tuple = (640, 640)
        self._class_names: List[str] = self.COCO_CLASSES
        self._target_classes: List[int] = []
        self._confidence_threshold: float = 0.35
        self._iou_threshold: float = 0.45
        self._max_detections: int = 100
    
    async def initialize(self) -> None:
        """Initialize ONNX Runtime session."""
        try:
            # Get model path from config
            model_path = self.config.get("model_path", "./yolo11n.onnx")
            
            # Providers: CUDA if available, else CPU
            providers = ['CPUExecutionProvider']
            if 'CUDAExecutionProvider' in ort.get_available_providers():
                providers.insert(0, 'CUDAExecutionProvider')
            
            # Session options
            sess_options = ort.SessionOptions()
            sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            sess_options.intra_op_num_threads = 0  # Use all cores
            
            self._session = ort.InferenceSession(
                model_path,
                sess_options=sess_options,
                providers=providers
            )
            
            # Get input/output info
            self._input_name = self._session.get_inputs()[0].name
            self._output_names = [out.name for out in self._session.get_outputs()]
            
            # Input shape
            input_shape = self._session.get_inputs()[0].shape
            if len(input_shape) == 4:
                self._input_shape = (input_shape[2], input_shape[3])  # H, W
            
            # Configure target classes
            if self.config.get("classes"):
                class_names = self.config["classes"]
                self._target_classes = [self._class_names.index(c) for c in class_names if c in self._class_names]
            else:
                # Default: person, vehicles
                default_classes = ['person', 'bicycle', 'car', 'motorcycle', 'bus', 'truck']
                self._target_classes = [self._class_names.index(c) for c in default_classes if c in self._class_names]
            
            # Thresholds
            self._confidence_threshold = self.config.get("confidence_threshold", 0.35)
            self._iou_threshold = self.config.get("iou_threshold", 0.45)
            self._max_detections = self.config.get("max_detections", 100)
            
            # Warmup
            dummy_input = np.random.randn(1, 3, *self._input_shape).astype(np.float32)
            self._session.run(self._output_names, {self._input_name: dummy_input})
            
            await self._set_status(self.PluginStatus.LOADED)
            self._initialized = True
            
            logger.info(f"YOLO ONNX detector initialized: {model_path}, providers={providers}, input_shape={self._input_shape}")
            
        except Exception as e:
            await self._set_status(self.PluginStatus.ERROR, str(e))
            logger.error(f"YOLO ONNX initialization failed: {e}")
            raise
    
    async def process(self, frame: CameraFrame) -> ProcessedFrame:
        """Process frame and return detections."""
        start_time = time.time()
        
        # Preprocess
        input_tensor, scale, pad = self._preprocess(frame.image)
        
        # Inference
        outputs = self._session.run(self._output_names, {self._input_name: input_tensor})
        
        # Postprocess
        detections = self._postprocess(outputs[0], frame.image.shape[:2], scale, pad)
        
        # Filter by target classes
        if self._target_classes:
            detections = [d for d in detections if d.class_id in self._target_classes]
        
        # Limit detections
        detections = detections[:self._max_detections]
        
        # Draw annotated frame
        annotated = self._draw_detections(frame.image.copy(), detections)
        
        processing_time = time.time() - start_time
        
        return ProcessedFrame(
            frame=frame.image,
            annotated=annotated,
            detections=detections,
            timestamp=frame.timestamp,
            camera_id=frame.camera_id,
            processing_time=processing_time,
            metadata={
                "model": "yolo_onnx",
                "input_shape": self._input_shape,
                "num_detections": len(detections),
            }
        )
    
    async def test_on_frame(self, frame: CameraFrame) -> ProcessedFrame:
        """Test detector on single frame."""
        return await self.process(frame)
    
    def _preprocess(self, image: np.ndarray) -> tuple:
        """Preprocess image for YOLO input."""
        h, w = image.shape[:2]
        target_h, target_w = self._input_shape
        
        # Calculate scale and padding
        scale = min(target_w / w, target_h / h)
        new_w, new_h = int(w * scale), int(h * scale)
        
        # Resize
        resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        
        # Pad to target size
        top = (target_h - new_h) // 2
        bottom = target_h - new_h - top
        left = (target_w - new_w) // 2
        right = target_w - new_w - left
        
        padded = cv2.copyMakeBorder(
            resized, top, bottom, left, right,
            cv2.BORDER_CONSTANT, value=(114, 114, 114)
        )
        
        # Normalize and convert to CHW
        input_tensor = padded.astype(np.float32) / 255.0
        input_tensor = input_tensor.transpose(2, 0, 1)  # HWC -> CHW
        input_tensor = np.expand_dims(input_tensor, 0)  # Add batch dim
        
        return input_tensor, scale, (left, top)
    
    def _postprocess(
        self,
        output: np.ndarray,
        orig_shape: tuple,
        scale: float,
        pad: tuple
    ) -> List[Detection]:
        """Postprocess YOLO output to detections."""
        orig_h, orig_w = orig_shape[:2]
        pad_left, pad_top = pad
        
        # YOLOv8/v11 output format: (batch, num_boxes, 4 + num_classes)
        # or (batch, 4 + num_classes, num_boxes) depending on model
        
        # Handle different output formats
        if output.ndim == 3:
            # (1, num_boxes, 4+classes) or (1, 4+classes, num_boxes)
            if output.shape[1] > output.shape[2]:
                output = output.transpose(0, 2, 1)
            output = output[0]  # (num_boxes, 4+classes)
        else:
            output = output[0]
        
        num_classes = output.shape[1] - 4
        
        # Filter by confidence
        scores = output[:, 4:].max(axis=1)
        mask = scores >= self._confidence_threshold
        output = output[mask]
        scores = scores[mask]
        
        if len(output) == 0:
            return []
        
        # Get class IDs
        class_ids = output[:, 4:].argmax(axis=1)
        
        # Extract boxes (cx, cy, w, h) normalized to input size
        boxes = output[:, :4]
        
        # Convert to xyxy
        cx, cy, w, h = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
        x1 = (cx - w/2) * self._input_shape[1]
        y1 = (cy - h/2) * self._input_shape[0]
        x2 = (cx + w/2) * self._input_shape[1]
        y2 = (cy + h/2) * self._input_shape[0]
        
        # Remove padding
        x1 = (x1 - pad_left) / scale
        y1 = (y1 - pad_top) / scale
        x2 = (x2 - pad_left) / scale
        y2 = (y2 - pad_top) / scale
        
        # Clip to image bounds
        x1 = np.clip(x1, 0, orig_w)
        y1 = np.clip(y1, 0, orig_h)
        x2 = np.clip(x2, 0, orig_w)
        y2 = np.clip(y2, 0, orig_h)
        
        # NMS
        indices = cv2.dnn.NMSBoxes(
            np.column_stack([x1, y1, x2 - x1, y2 - y1]).astype(np.float32).tolist(),
            scores.tolist(),
            self._confidence_threshold,
            self._iou_threshold
        )
        
        if len(indices) == 0:
            return []
        
        if isinstance(indices, tuple):
            indices = indices[0]
        indices = indices.flatten() if hasattr(indices, 'flatten') else indices
        
        # Build detections
        detections = []
        for i in indices:
            class_id = int(class_ids[i])
            class_name = self._class_names[class_id] if class_id < len(self._class_names) else f"class_{class_id}"
            
            detections.append(Detection(
                class_id=class_id,
                class_name=class_name,
                confidence=float(scores[i]),
                bbox=(float(x1[i]) / orig_w, float(y1[i]) / orig_h,
                      float(x2[i]) / orig_w, float(y2[i]) / orig_h),
                metadata={"source": "yolo_onnx"}
            ))
        
        return detections
    
    def _draw_detections(self, image: np.ndarray, detections: List[Detection]) -> np.ndarray:
        """Draw detection boxes on image."""
        for det in detections:
            h, w = image.shape[:2]
            x1, y1, x2, y2 = det.bbox
            x1, y1, x2, y2 = int(x1 * w), int(y1 * h), int(x2 * w), int(y2 * h)
            
            # Color based on class
            color = self._get_class_color(det.class_id)
            
            # Draw box
            cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
            
            # Draw label
            label = f"{det.class_name} {det.confidence:.2f}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(image, (x1, y1 - th - 4), (x1 + tw, y1), color, -1)
            cv2.putText(image, label, (x1, y1 - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        return image
    
    def _get_class_color(self, class_id: int) -> tuple:
        """Get consistent color for class."""
        np.random.seed(class_id)
        return tuple(np.random.randint(50, 255, 3).tolist())
    
    @property
    def supported_classes(self) -> List[str]:
        return self._class_names
    
    async def shutdown(self) -> None:
        """Shutdown plugin."""
        self._session = None
        await self._set_status(self.PluginStatus.UNLOADED)