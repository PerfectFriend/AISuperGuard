"""
SuperGuard Core - Plugins Package
"""

from superguard_core.plugins.cameras import CAMERA_PLUGINS
from superguard_core.plugins.detectors import DETECTOR_PLUGINS
from superguard_core.plugins.actuators import ACTUATOR_PLUGINS
from superguard_core.plugins.notifiers import NOTIFIER_PLUGINS
from superguard_core.plugins.storage import STORAGE_PLUGINS

# Все плагины по типам
ALL_PLUGINS = {
    "camera": CAMERA_PLUGINS,
    "detector": DETECTOR_PLUGINS,
    "actuator": ACTUATOR_PLUGINS,
    "notifier": NOTIFIER_PLUGINS,
    "storage": STORAGE_PLUGINS,
}

# Плоский список всех плагинов для автообнаружения
PLUGIN_CLASSES = []
for category, plugins in ALL_PLUGINS.items():
    PLUGIN_CLASSES.extend(plugins.values())

__all__ = [
    "CAMERA_PLUGINS",
    "DETECTOR_PLUGINS",
    "ACTUATOR_PLUGINS",
    "NOTIFIER_PLUGINS",
    "STORAGE_PLUGINS",
    "ALL_PLUGINS",
    "PLUGIN_CLASSES",
]