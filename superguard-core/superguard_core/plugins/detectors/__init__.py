"""
SuperGuard Core - Detectors Plugins Package
"""

from superguard_core.plugins.detectors.yolo_onnx import YoloOnnxDetectorPlugin
from superguard_core.plugins.detectors.motion import MotionDetectorPlugin

# Plugin registry
DETECTOR_PLUGINS = {
    "yolo_onnx": YoloOnnxDetectorPlugin,
    "motion": MotionDetectorPlugin,
}

__all__ = [
    "YoloOnnxDetectorPlugin",
    "MotionDetectorPlugin",
    "DETECTOR_PLUGINS",
]