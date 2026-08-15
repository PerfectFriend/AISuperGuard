"""
SuperGuard Core - Plugin System

Base classes and manager for all plugin types.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Type, get_type_hints
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from superguard_core.core.database import Camera, Detector, Actuator, Site
from superguard_core.core.events import EventBus


class PluginType(str, Enum):
    CAMERA = "camera"
    DETECTOR = "detector"
    ACTUATOR = "actuator"
    NOTIFIER = "notifier"
    STORAGE = "storage"


class PluginStatus(str, Enum):
    UNLOADED = "unloaded"
    LOADING = "loading"
    LOADED = "loaded"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass
class PluginMetadata:
    """Plugin metadata from entry point."""
    name: str
    version: str
    plugin_type: PluginType
    class_name: str
    module_path: str
    config_schema: Type[BaseModel]
    description: str = ""
    author: str = ""
    dependencies: List[str] = field(default_factory=list)
    entry_point: Any = None


class PluginConfig(BaseModel):
    """Base plugin configuration."""
    model_config = ConfigDict(extra="allow")
    
    enabled: bool = True
    site_id: Optional[int] = None


class PluginBase(ABC):
    """Base class for all plugins."""
    
    # Class attributes (set by subclasses)
    name: str = ""
    version: str = "1.0.0"
    plugin_type: PluginType = PluginType.CAMERA
    config_class: Type[PluginConfig] = PluginConfig
    description: str = ""
    author: str = ""
    
    def __init__(self, config: PluginConfig, event_bus: EventBus):
        self.config = config
        self.event_bus = event_bus
        self.status = PluginStatus.UNLOADED
        self.error_message: Optional[str] = None
        self._initialized = False
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize plugin resources."""
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """Cleanup plugin resources."""
        pass
    
    @property
    def is_ready(self) -> bool:
        return self.status == PluginStatus.LOADED and self._initialized
    
    async def _set_status(self, status: PluginStatus, error: Optional[str] = None):
        self.status = status
        self.error_message = error
        await self.event_bus.publish("plugins.status", {
            "plugin": self.name,
            "type": self.plugin_type.value,
            "status": status.value,
            "error": error,
            "timestamp": datetime.now().isoformat(),
        })


# ============================================================
# Camera Plugins
# ============================================================

@dataclass
class CameraFrame:
    """Single frame from camera."""
    image: Any  # numpy array
    timestamp: float
    camera_id: int
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DiscoveredCamera:
    """Discovered camera info."""
    name: str
    url: str
    type: str
    manufacturer: str = ""
    model: str = ""
    mac_address: str = ""
    ip_address: str = ""
    onvif_profile: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


class CameraPlugin(PluginBase):
    """Base class for camera plugins."""
    
    plugin_type = PluginType.CAMERA
    
    @abstractmethod
    async def connect(self, camera: Camera) -> None:
        """Connect to camera."""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from camera."""
        pass
    
    @abstractmethod
    async def read_frame(self) -> Optional[CameraFrame]:
        """Read single frame from camera."""
        pass
    
    @abstractmethod
    async def get_snapshot(self) -> Optional[CameraFrame]:
        """Get single snapshot (for JPG cameras)."""
        pass
    
    @abstractmethod
    async def ptz_control(self, command: str, **kwargs) -> bool:
        """PTZ control (if supported)."""
        pass
    
    @classmethod
    @abstractmethod
    async def discover(cls, timeout: int = 10) -> List[DiscoveredCamera]:
        """Discover cameras on network."""
        pass
    
    @classmethod
    def get_supported_types(cls) -> List[str]:
        """Return list of supported camera types."""
        return []


# ============================================================
# Detector Plugins
# ============================================================

@dataclass
class Detection:
    """Single detection result."""
    class_id: int
    class_name: str
    confidence: float
    bbox: tuple  # (x1, y1, x2, y2) normalized 0-1
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessedFrame:
    """Processed frame with detections."""
    frame: Any  # original frame (numpy array)
    annotated: Any  # annotated frame with boxes
    detections: List[Detection]
    timestamp: float
    camera_id: int
    processing_time: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class DetectorPlugin(PluginBase):
    """Base class for detector plugins."""
    
    plugin_type = PluginType.DETECTOR
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize detector (load model, etc.)."""
        pass
    
    @abstractmethod
    async def process(self, frame: CameraFrame) -> ProcessedFrame:
        """Process frame and return detections."""
        pass
    
    @abstractmethod
    async def test_on_frame(self, frame: CameraFrame) -> ProcessedFrame:
        """Test detector on single frame (for UI)."""
        pass
    
    @property
    @abstractmethod
    def supported_classes(self) -> List[str]:
        """List of supported detection classes."""
        pass


# ============================================================
# Actuator Plugins
# ============================================================

@dataclass
class ActuatorState:
    """Actuator state."""
    is_on: bool
    last_changed: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


class ActuatorPlugin(PluginBase):
    """Base class for actuator plugins."""
    
    plugin_type = PluginType.ACTUATOR
    
    @abstractmethod
    async def initialize(self, actuator: Actuator) -> None:
        """Initialize actuator connection."""
        pass
    
    @abstractmethod
    async def turn_on(self) -> ActuatorState:
        """Turn actuator ON."""
        pass
    
    @abstractmethod
    async def turn_off(self) -> ActuatorState:
        """Turn actuator OFF."""
        pass
    
    @abstractmethod
    async def toggle(self) -> ActuatorState:
        """Toggle actuator state."""
        pass
    
    @abstractmethod
    async def get_state(self) -> ActuatorState:
        """Get current actuator state."""
        pass
    
    @abstractmethod
    async def test_connection(self) -> bool:
        """Test actuator connectivity."""
        pass


# ============================================================
# Notifier Plugins
# ============================================================

@dataclass
class NotificationPayload:
    """Notification payload."""
    title: str
    message: str
    priority: str = "normal"  # low, normal, high, critical
    media_urls: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class NotifierPlugin(PluginBase):
    """Base class for notifier plugins."""
    
    plugin_type = PluginType.NOTIFIER
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize notifier (connect to service)."""
        pass
    
    @abstractmethod
    async def send(self, payload: NotificationPayload, targets: List[str]) -> bool:
        """Send notification to targets."""
        pass
    
    @abstractmethod
    async def test(self, target: str) -> bool:
        """Test notification delivery."""
        pass
    
    @property
    @abstractmethod
    def supported_targets(self) -> List[str]:
        """List of supported target types (chat_id, email, phone, etc.)."""
        pass


# ============================================================
# Storage Plugins
# ============================================================

@dataclass
class StoredFile:
    """Stored file info."""
    path: str
    url: str
    size: int
    checksum: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class StoragePlugin(PluginBase):
    """Base class for storage plugins."""
    
    plugin_type = PluginType.STORAGE
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize storage connection."""
        pass
    
    @abstractmethod
    async def save(self, local_path: str, remote_path: str) -> StoredFile:
        """Save file to storage."""
        pass
    
    @abstractmethod
    async def load(self, remote_path: str, local_path: str) -> bool:
        """Load file from storage."""
        pass
    
    @abstractmethod
    async def delete(self, remote_path: str) -> bool:
        """Delete file from storage."""
        pass
    
    @abstractmethod
    async def list(self, prefix: str = "") -> List[StoredFile]:
        """List files in storage."""
        pass
    
    @abstractmethod
    async def get_url(self, remote_path: str, expires: int = 3600) -> str:
        """Get signed URL for file."""
        pass


# ============================================================
# Plugin Manager
# ============================================================

class PluginManager:
    """Manages plugin discovery, loading, and lifecycle."""
    
    def __init__(self):
        self.plugins: Dict[str, PluginBase] = {}
        self.metadata: Dict[str, PluginMetadata] = {}
        self._entry_points_cache: Dict[PluginType, List] = {}
    
    async def discover_plugins(self) -> None:
        """Discover plugins via entry points."""
        import importlib.metadata
        
        for plugin_type in PluginType:
            group = f"superguard.{plugin_type.value}s"
            try:
                entry_points = importlib.metadata.entry_points(group=group)
                self._entry_points_cache[plugin_type] = list(entry_points)
                
                for ep in entry_points:
                    try:
                        plugin_class = ep.load()
                        metadata = PluginMetadata(
                            name=ep.name,
                            version=getattr(plugin_class, "version", "1.0.0"),
                            plugin_type=plugin_type,
                            class_name=plugin_class.__name__,
                            module_path=plugin_class.__module__,
                            config_schema=getattr(plugin_class, "config_class", PluginConfig),
                            description=getattr(plugin_class, "description", ""),
                            author=getattr(plugin_class, "author", ""),
                            entry_point=ep,
                        )
                        self.metadata[ep.name] = metadata
                    except Exception as e:
                        print(f"Failed to load plugin {ep.name}: {e}")
            except Exception:
                self._entry_points_cache[plugin_type] = []
    
    def get_available_plugins(self, plugin_type: Optional[PluginType] = None) -> List[PluginMetadata]:
        """Get list of available plugins."""
        if plugin_type:
            return [m for m in self.metadata.values() if m.plugin_type == plugin_type]
        return list(self.metadata.values())
    
    def get_plugin_class(self, plugin_type: PluginType, name: str) -> Optional[Type[PluginBase]]:
        """Get plugin class by type and name."""
        for ep in self._entry_points_cache.get(plugin_type, []):
            if ep.name == name:
                return ep.load()
        return None
    
    async def load_plugin(
        self,
        plugin_type: PluginType,
        name: str,
        config: PluginConfig,
        event_bus: EventBus,
    ) -> PluginBase:
        """Load and initialize plugin instance."""
        key = f"{plugin_type.value}:{name}"
        
        if key in self.plugins:
            return self.plugins[key]
        
        plugin_class = self.get_plugin_class(plugin_type, name)
        if not plugin_class:
            raise ValueError(f"Plugin not found: {plugin_type.value}:{name}")
        
        try:
            await self.metadata[name]._set_status(PluginStatus.LOADING)
            
            instance = plugin_class(config, event_bus)
            await instance.initialize()
            
            await self.metadata[name]._set_status(PluginStatus.LOADED)
            self.plugins[key] = instance
            
            return instance
        except Exception as e:
            await self.metadata[name]._set_status(PluginStatus.ERROR, str(e))
            raise
    
    async def unload_plugin(self, plugin_type: PluginType, name: str) -> None:
        """Unload plugin instance."""
        key = f"{plugin_type.value}:{name}"
        
        if key in self.plugins:
            instance = self.plugins[key]
            try:
                await instance.shutdown()
            except Exception:
                pass
            del self.plugins[key]
    
    async def shutdown(self) -> None:
        """Shutdown all loaded plugins."""
        for key in list(self.plugins.keys()):
            plugin_type_str, name = key.split(":", 1)
            await self.unload_plugin(PluginType(plugin_type_str), name)
    
    def get_plugin(self, plugin_type: PluginType, name: str) -> Optional[PluginBase]:
        """Get loaded plugin instance."""
        return self.plugins.get(f"{plugin_type.value}:{name}")
    
    def get_loaded_plugins(self, plugin_type: Optional[PluginType] = None) -> List[PluginBase]:
        """Get all loaded plugins."""
        if plugin_type:
            return [p for k, p in self.plugins.items() if k.startswith(f"{plugin_type.value}:")]
        return list(self.plugins.values())