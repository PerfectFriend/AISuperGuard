"""
SuperGuard Core - Cameras Plugins Package
"""

from superguard_core.plugins.cameras.rtsp import RtspCameraPlugin
from superguard_core.plugins.cameras.hls import HlsCameraPlugin
from superguard_core.plugins.cameras.jpg import JpgCameraPlugin
from superguard_core.plugins.cameras.onvif import OnvifCameraPlugin
from superguard_core.plugins.cameras.webcam import WebcamCameraPlugin

# Plugin registry
CAMERA_PLUGINS = {
    "rtsp": RtspCameraPlugin,
    "hls": HlsCameraPlugin,
    "jpg": JpgCameraPlugin,
    "onvif": OnvifCameraPlugin,
    "webcam": WebcamCameraPlugin,
}

__all__ = [
    "RtspCameraPlugin",
    "HlsCameraPlugin", 
    "JpgCameraPlugin",
    "OnvifCameraPlugin",
    "WebcamCameraPlugin",
    "CAMERA_PLUGINS",
]