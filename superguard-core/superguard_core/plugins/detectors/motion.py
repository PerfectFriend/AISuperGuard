"""
SuperGuard Core - Motion Detector Plugin

Classic motion detection using frame differencing.
"""

import asyncio
import logging
from typing import List, Optional

import cv2
import numpy as np

from superguard_core.core.plugins import DetectorPlugin, CameraFrame, ProcessedFrame, Detection, PluginConfig


logger = logging.getLogger(__name__)


class MotionDetectorPlugin(DetectorPlugin):
    """Classic motion detector using frame differencing."""
    
    name = "motion"
    version = "1.0.0"
    plugin_type = "detector"
    description = "Classic motion detection via frame differencing"
    author = "SuperGuard Team"
    
    def __init__(self, config: PluginConfig, event_bus):
        super().__init__(config, event_bus)
        self._prev_frame: Optional[np.ndarray] = None
        self._min_area: int = 500
        self._threshold: int = 25
        self._blur_kernel: tuple = (21, 21)
        self._dilate_iterations: int = 2
    
    async def initialize(self) -> None:
        """Initialize motion detector."""
        self._min_area = self.config.get("min_area", 500)
        self._threshold = self.config.get("threshold", 25)
        self._blur_kernel = tuple(self.config.get("blur_kernel", [21, 21]))
        self._dilate_iterations = self.config.get("dilate_iterations", 2)
        
        await self._set_status(self.PluginStatus.LOADED)
        self._initialized = True
        
        logger.info(f"Motion detector initialized: min_area={self._min_area}, threshold={self._threshold}")
    
    async def process(self, frame: CameraFrame) -> ProcessedFrame:
        """Process frame for motion detection."""
        start_time = asyncio.get_event_loop().time()
        
        # Convert to grayscale
        gray = cv2.cvtColor(frame.image, cv2.COLOR_RGB2GRAY)
        gray = cv2.GaussianBlur(gray, self._blur_kernel, 0)
        
        detections = []
        annotated = frame.image.copy()
        
        if self._prev_frame is not None:
            # Compute difference
            frame_delta = cv2.absdiff(self._prev_frame, gray)
            thresh = cv2.threshold(frame_delta, self._threshold, 255, cv2.THRESH_BINARY)[1]
            
            # Dilate to fill holes
            kernel = np.ones((5, 5), np.uint8)
            thresh = cv2.dilate(thresh, kernel, iterations=self._dilate_iterations)
            
            # Find contours
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            for contour in contours:
                area = cv2.contourArea(contour)
                if area < self._min_area:
                    continue
                
                x, y, w, h = cv2.boundingRect(contour)
                
                # Normalize bbox
                h_img, w_img = frame.image.shape[:2]
                detections.append(Detection(
                    class_id=0,
                    class_name="motion",
                    confidence=min(1.0, area / (h_img * w_img) * 10),
                    bbox=(x / w_img, y / h_img, (x + w) / w_img, (y + h) / h_img),
                    metadata={
                        "area": area,
                        "source": "motion",
                    }
                ))
                
                # Draw on annotated
                cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.putText(annotated, f"Motion {area:.0f}", (x, y - 5),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        
        # Update previous frame
        self._prev_frame = gray
        
        processing_time = asyncio.get_event_loop().time() - start_time
        
        return ProcessedFrame(
            frame=frame.image,
            annotated=annotated,
            detections=detections,
            timestamp=frame.timestamp,
            camera_id=frame.camera_id,
            processing_time=processing_time,
            metadata={
                "model": "motion",
                "num_detections": len(detections),
            }
        )
    
    async def test_on_frame(self, frame: CameraFrame) -> ProcessedFrame:
        """Test on single frame."""
        return await self.process(frame)
    
    @property
    def supported_classes(self) -> List[str]:
        return ["motion"]
    
    async def shutdown(self) -> None:
        """Shutdown plugin."""
        self._prev_frame = None
        await self._set_status(self.PluginStatus.UNLOADED)