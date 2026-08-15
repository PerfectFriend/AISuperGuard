"""
SuperGuard Core - Актуаторы Plugins Package
"""

from superguard_core.plugins.actuators.tuya_local import TuyaLocalActuatorPlugin
from superguard_core.plugins.actuators.tuya_cloud import TuyaCloudActuatorPlugin
from superguard_core.plugins.actuators.mqtt import MqttActuatorPlugin

# Реестр плагинов
ACTUATOR_PLUGINS = {
    "tuya_local": TuyaLocalActuatorPlugin,
    "tuya_cloud": TuyaCloudActuatorPlugin,
    "mqtt": MqttActuatorPlugin,
}

__all__ = [
    "TuyaLocalActuatorPlugin",
    "TuyaCloudActuatorPlugin",
    "MqttActuatorPlugin",
    "ACTUATOR_PLUGINS",
]