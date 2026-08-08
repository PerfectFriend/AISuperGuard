"""
SuperGuard Alarm - Storage Layer

Atomic JSON persistence for settings with schema validation and migration.
"""
import os
import json
import threading
import time
from typing import Dict, Any, Optional
from dataclasses import asdict

from ..models import CameraSettings, Zone, Target
from ..config import SuperGuardConfig


class SettingsStore:
    """Thread-safe atomic JSON settings storage with schema validation."""
    
    def __init__(self, config: SuperGuardConfig):
        self.config = config
        self.filepath = config.settings_file
        self._lock = threading.RLock()
        self._cache: Optional[Dict[str, Any]] = None
        self._dirty = False
        self._debounce_timer: Optional[threading.Timer] = None
        self._debounce_ms = 500  # Batch writes within 500ms
    
    def load(self) -> Dict[str, Any]:
        """Load settings from disk (cached after first load)."""
        with self._lock:
            if self._cache is not None:
                return self._cache
            
            if not os.path.exists(self.filepath):
                self._cache = self._default_structure()
                return self._cache
            
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # Validate and migrate schema
                self._cache = self._validate_and_migrate(data)
                return self._cache
            except Exception as e:
                print(f"Settings load error: {e}")
                self._cache = self._default_structure()
                return self._cache
    
    def _default_structure(self) -> Dict[str, Any]:
        """Default settings structure."""
        return {
            "version": 1,
            "lang": "ru",
            "auto": False,
            "active_camera": 1,
            "camera_settings": {},
        }
    
    def _validate_and_migrate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate schema and migrate older versions."""
        # Ensure all required fields exist
        defaults = self._default_structure()
        for key, default_val in defaults.items():
            if key not in data:
                data[key] = default_val
        
        # Validate camera_settings structure
        if "camera_settings" not in data:
            data["camera_settings"] = {}
        
        # Ensure camera_settings values are valid
        for cam_key, cam_data in data["camera_settings"].items():
            if not isinstance(cam_data, dict):
                data["camera_settings"][cam_key] = {}
                continue
            
            # Validate zone
            if "zone" in cam_data and cam_data["zone"] is not None:
                zone = cam_data["zone"]
                if not (isinstance(zone, list) and len(zone) == 3 and
                        all(isinstance(v, int) for v in zone)):
                    cam_data["zone"] = None
            
            # Validate target
            if "target" in cam_data and not isinstance(cam_data["target"], str):
                cam_data["target"] = ""
            
            # Validate actuator
            if "actuator" in cam_data and not isinstance(cam_data["actuator"], str):
                cam_data["actuator"] = None
        
        return data
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a top-level setting."""
        data = self.load()
        return data.get(key, default)
    
    def set(self, key: str, value: Any):
        """Set a top-level setting (debounced write)."""
        with self._lock:
            data = self.load()
            data[key] = value
            self._schedule_write()
    
    def get_camera_settings(self, cam_id: int) -> CameraSettings:
        """Get CameraSettings for a camera."""
        data = self.load()
        cam_key = str(cam_id)
        cam_data = data["camera_settings"].get(cam_key, {})
        return CameraSettings.from_dict(cam_data)
    
    def set_camera_settings(self, cam_id: int, settings: CameraSettings):
        """Set CameraSettings for a camera (debounced write)."""
        with self._lock:
            data = self.load()
            data["camera_settings"][str(cam_id)] = settings.to_dict()
            self._schedule_write()
    
    def get_all_camera_settings(self) -> Dict[int, CameraSettings]:
        """Get all camera settings."""
        data = self.load()
        result = {}
        for cam_key, cam_data in data["camera_settings"].items():
            try:
                result[int(cam_key)] = CameraSettings.from_dict(cam_data)
            except (ValueError, TypeError):
                pass
        return result
    
    def _schedule_write(self):
        """Schedule a debounced write."""
        self._dirty = True
        if self._debounce_timer:
            self._debounce_timer.cancel()
        self._debounce_timer = threading.Timer(
            self._debounce_ms / 1000.0, self._flush
        )
        self._debounce_timer.daemon = True
        self._debounce_timer.start()
    
    def _flush(self):
        """Write to disk atomically."""
        with self._lock:
            if not self._dirty or self._cache is None:
                return
            
            # Atomic write: write to temp, then rename
            temp_path = self.filepath + ".tmp"
            try:
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(self._cache, f, ensure_ascii=False, indent=2)
                os.replace(temp_path, self.filepath)
                self._dirty = False
                print(f"  Settings saved to {self.filepath}")
            except Exception as e:
                print(f"Settings save error: {e}")
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
    
    def force_flush(self):
        """Immediately write pending changes."""
        with self._lock:
            if self._debounce_timer:
                self._debounce_timer.cancel()
            self._flush()
    
    def close(self):
        """Clean up - flush pending writes."""
        self.force_flush()


class EnvWriter:
    """Atomic .env file writer for runtime config updates (e.g., Tuya Cloud IP changes)."""
    
    def __init__(self, env_path: str):
        self.env_path = env_path
        self._lock = threading.Lock()
    
    def update_key(self, key: str, value: str):
        """Update a single key in .env file atomically."""
        with self._lock:
            lines = []
            found = False
            
            if os.path.exists(self.env_path):
                with open(self.env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        stripped = line.strip()
                        if stripped and not stripped.startswith("#") and "=" in stripped:
                            k, _ = stripped.split("=", 1)
                            if k.strip() == key:
                                lines.append(f"{key}={value}\n")
                                found = True
                                continue
                        lines.append(line)
            
            if not found:
                lines.append(f"{key}={value}\n")
            
            # Atomic write
            temp_path = self.env_path + ".tmp"
            try:
                with open(temp_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)
                os.replace(temp_path, self.env_path)
            except Exception as e:
                print(f"Env write error: {e}")
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
    
    def update_multiple(self, updates: Dict[str, str]):
        """Update multiple keys atomically."""
        with self._lock:
            lines = []
            updated_keys = set()
            
            if os.path.exists(self.env_path):
                with open(self.env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        stripped = line.strip()
                        if stripped and not stripped.startswith("#") and "=" in stripped:
                            k, _ = stripped.split("=", 1)
                            if k.strip() in updates:
                                lines.append(f"{k.strip()}={updates[k.strip()]}\n")
                                updated_keys.add(k.strip())
                                continue
                        lines.append(line)
            
            # Add new keys
            for key, value in updates.items():
                if key not in updated_keys:
                    lines.append(f"{key}={value}\n")
            
            temp_path = self.env_path + ".tmp"
            try:
                with open(temp_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)
                os.replace(temp_path, self.env_path)
            except Exception as e:
                print(f"Env write error: {e}")
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass