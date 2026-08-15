"""
SuperGuard Alarm - Core Data Models

Defines the fundamental data structures used across the system:
- Zone: Grid-based region of interest (N×M cells, numbered LTR/TTB)
- Target: Detection target specification (YOLO classes + HSV color filters)
- CameraSettings: Per-camera persisted settings (zone, target, actuator bindings)
- AlarmState: Alarm state enumeration (INACTIVE, ACTIVE, AUTO_RESOLVING)
- Alarm: Legacy single-alarm state machine (deprecated, kept for compat)
- CameraAlarmState: Per-camera alarm state machine (concurrent alarms)
- AlarmManager: Manages concurrent per-camera alarms

Key design principles:
- All data structures are pure (no I/O, no side effects)
- Thread-safe where needed (Lock in alarm state machines)
- JSON-serializable for persistence (to_dict/from_dict)
- Type hints throughout for static analysis
"""

from dataclasses import dataclass, field
from typing import Optional, Set, List, Dict, Any
from enum import Enum
import threading


# ============================================================================
# ZONE MODEL
# ============================================================================

@dataclass
class Zone:
    """Grid-based zone definition.
    
    The frame is divided into rows x cols cells, numbered left-to-right, top-to-bottom.
    Cell 1 = top-left, Cell (rows*cols) = bottom-right.
    
    Normalized coordinates (0.0-1.0) are used for resolution-independence.
    The camera resolution doesn't matter - zone logic works on normalized space.
    
    Example: Zone(rows=3, cols=4, cell=9) = N3x4 C9 = row 3, col 1 (bottom-left)
    
    Attributes:
        rows: Number of grid rows (vertical divisions)
        cols: Number of grid columns (horizontal divisions)
        cell: 1-based cell index (1 to rows*cols)
    """
    rows: int
    cols: int
    cell: int
    
    def __post_init__(self):
        """Validate cell is within grid bounds."""
        if not (1 <= self.cell <= self.rows * self.cols):
            raise ValueError(f"Cell {self.cell} out of range for {self.rows}x{self.cols} grid")
    
    @property
    def row(self) -> int:
        """1-based row index (top to bottom). Computed from cell number."""
        return (self.cell - 1) // self.cols + 1
    
    @property
    def col(self) -> int:
        """1-based column index (left to right). Computed from cell number."""
        return (self.cell - 1) % self.cols + 1
    
    def contains_point(self, cx: float, cy: float, frame_w: int, frame_h: int) -> bool:
        """Check if normalized point (cx, cy) falls within this zone cell.
        
        Uses normalized coordinates so the same zone works regardless of frame resolution.
        The frame_w/frame_h parameters are kept for API compatibility but not used
        in the calculation (normalized space is resolution-agnostic).
        
        Args:
            cx: Normalized x coordinate (0.0 to 1.0)
            cy: Normalized y coordinate (0.0 to 1.0)
            frame_w: Frame width (unused, for API compat)
            frame_h: Frame height (unused, for API compat)
            
        Returns:
            True if point center is inside this zone cell boundaries (inclusive)
        """
        col_width = 1.0 / self.cols
        row_height = 1.0 / self.rows
        
        col_min = (self.col - 1) * col_width
        col_max = self.col * col_width
        row_min = (self.row - 1) * row_height
        row_max = self.row * row_height
        
        # Inclusive bounds - point on edge counts as inside
        return (col_min <= cx <= col_max) and (row_min <= cy <= row_max)
    
    def to_list(self) -> List[int]:
        """Serialize to [rows, cols, cell] for JSON storage."""
        return [self.rows, self.cols, self.cell]
    
    @classmethod
    def from_list(cls, data: List[int]) -> Optional["Zone"]:
        """Deserialize from [rows, cols, cell].
        
        Returns None if data is invalid (wrong type, length, or values).
        """
        if not isinstance(data, list) or len(data) != 3:
            return None
        try:
            return cls(rows=int(data[0]), cols=int(data[1]), cell=int(data[2]))
        except (ValueError, TypeError):
            return None
    
    def __str__(self) -> str:
        """Human-readable format: N3x4 C09 (zero-padded cell)."""
        return f"N{self.rows}x{self.cols} C{self.cell:02d}"
    
    def __bool__(self) -> bool:
        """Zone is always truthy when instantiated (not None)."""
        return True


def parse_zone_spec(spec: str) -> Optional[Zone]:
    """Parse zone specification string into Zone object.
    
    Supported formats (case-insensitive, spaces ignored):
    - "N3x4 C9" or "n3x4c9" - explicit rows x cols grid with cell number
    - "N9 C5" or "n9c5" - square grid (sqrt(total) x sqrt(total)), cell number
    - "off", "none", "0", "всё", "все", "todo", "toda", "nada", "desactivar" - returns None (whole frame)
    
    Cyrillic 'х' is accepted as 'x' for Russian keyboard users.
    
    Args:
        spec: Zone specification string from user input (/zone command)
        
    Returns:
        Zone object or None for "whole frame" (zone disabled)
    """
    if not spec:
        return None
    
    # Normalize: lowercase, replace cyrillic x, remove spaces and underscores
    s = spec.strip().lower().replace("х", "x").replace(" ", "").replace("_", "")
    
    # Handle "off" keywords (multilingual)
    if s in ("off", "none", "0", "всё", "все", "todo", "toda", "nada", "desactivar"):
        return None
    
    # Format: N3x4 C9 or n3x4c9
    import re
    m = re.fullmatch(r"n?(\d+)x(\d+)c(\d+)", s)
    if m:
        rows, cols, cell = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return Zone(rows=rows, cols=cols, cell=cell)
        except ValueError:
            return None
    
    # Format: N9 C5 -> square grid (3x3 for 9, 4x4 for 16, etc.)
    m = re.fullmatch(r"n(\d+)c(\d+)", s)
    if m:
        total, cell = int(m.group(1)), int(m.group(2))
        side = int(total ** 0.5)
        # Only perfect squares supported (9, 16, 25, 36, 49, 64)
        if side * side == total and 1 <= cell <= total:
            return Zone(rows=side, cols=side, cell=cell)
    
    return None


# ============================================================================
# TARGET MODEL (Detection Filter)
# ============================================================================

@dataclass
class Target:
    """Detection target specification.
    
    Combines YOLO class filter + HSV color filter.
    Parsed from free-text like "red car" or "person standing".
    
    The filter works as: (class in classes OR classes empty) AND (color_fraction >= threshold OR no color filter)
    
    Attributes:
        description: Original user text (for display)
        classes: Set of COCO class IDs to match (empty = all vehicle classes)
        color_ranges: List of (low_hsv, high_hsv) tuples for HSV filtering
    """
    description: str = ""           # Original user text
    classes: Set[int] = field(default_factory=set)  # COCO class IDs
    color_ranges: List[tuple] = field(default_factory=list)  # HSV (low, high) pairs
    
    def __bool__(self) -> bool:
        """True if description is non-empty (filter was explicitly set)."""
        return bool(self.description.strip())
    
    def matches_class(self, cls_id: int) -> bool:
        """Check if class ID matches target classes.
        
        If classes set is empty, matches ANY class (default: vehicle classes).
        If classes set is non-empty, only matches those specific classes.
        
        Args:
            cls_id: COCO class ID from YOLO detection
            
        Returns:
            True if class matches filter
        """
        return not self.classes or cls_id in self.classes
    
    def has_color_filter(self) -> bool:
        """True if color filter is active (non-empty and not default yellow).
        
        Note: Imports inside method to avoid circular import with config module.
        """
        from .config import Y_LOW, Y_HIGH  # Avoid circular import
        import numpy as np
        default_yellow = [(Y_LOW.tolist(), Y_HIGH.tolist())]
        return bool(self.color_ranges and self.color_ranges != default_yellow)
    
    def filter_label(self) -> str:
        """Human-readable description of current filter for UI display."""
        from .i18n import tr  # Avoid circular import - will be overridden
        class_names = [VEHICLE_CLASSES.get(c, str(c)) for c in sorted(self.classes)]
        class_str = ", ".join(class_names) if class_names else "all"
        
        if not self.color_ranges:
            color_str = "any color"
        elif self.color_ranges == [([15, 60, 80], [40, 255, 255])]:
            color_str = "yellow"
        else:
            color_str = "custom color"
        
        return f"classes: {class_str} | color: {color_str}"


# COCO class IDs for vehicles (subset - full map in CLASS_MAP)
VEHICLE_CLASSES = {2: "car", 5: "bus", 7: "truck"}

# Full CLASS_MAP for parsing (COCO class names -> IDs)
# Maps user-friendly synonyms to COCO class indices
CLASS_MAP = {
    "person": 0, "people": 0, "human": 0, "pedestrian": 0,
    "bicycle": 1, "bike": 1, "cycle": 1,
    "car": 2, "auto": 2, "vehicle": 2, "automobile": 2,
    "motorcycle": 3, "moto": 3, "motorbike": 3,
    "airplane": 4, "plane": 4,
    "bus": 5, "coach": 5,
    "train": 6, "railway": 6,
    "truck": 7, "lorry": 7, "van": 7, "pickup": 7,
    "boat": 8, "ship": 8,
    # ... (truncated for brevity, full map in parser)
}

# HSV color ranges by name (OpenCV HSV: H=0-180, S=0-255, V=0-255)
# Each color can have multiple ranges (e.g., red wraps around 0/180)
COLOR_MAP = {
    "red": [([0, 60, 80], [10, 255, 255]), ([170, 60, 80], [180, 255, 255])],
    "orange": [([10, 60, 80], [25, 255, 255])],
    "yellow": [([15, 60, 80], [40, 255, 255])],
    "green": [([40, 60, 80], [85, 255, 255])],
    "cyan": [([85, 60, 80], [100, 255, 255])],
    "blue": [([100, 60, 80], [130, 255, 255])],
    "purple": [([130, 60, 80], [150, 255, 255])],
    "pink": [([150, 60, 80], [170, 255, 255])],
    "white": [([0, 0, 200], [180, 40, 255])],
    "black": [([0, 0, 0], [180, 255, 50])],
    "gray": [([0, 0, 50], [180, 40, 200])],
    "brown": [([10, 60, 40], [20, 255, 150])],
}


def parse_target_text(text: str) -> Target:
    """Parse free-text target description into Target object.
    
    Recognizes words from CLASS_MAP and COLOR_MAP.
    Unrecognized words are silently ignored (filter unchanged).
    If nothing recognized, returns Target with description but empty filters.
    
    Args:
        text: User input from /target command (e.g., "red car", "person")
        
    Returns:
        Target object with parsed classes and color_ranges
    """
    if not text:
        return Target()
    
    import re
    # Extract words (Latin + Cyrillic)
    words = re.findall(r"[a-zа-яё]+", text.lower())
    classes = set()
    color_ranges = []
    recognized = False
    
    for w in words:
        if w in CLASS_MAP:
            classes.add(CLASS_MAP[w])
            recognized = True
        elif w in COLOR_MAP:
            for low, high in COLOR_MAP[w]:
                color_ranges.append((list(low), list(high)))
            recognized = True
    
    # If no recognized words, keep description but don't change filters
    if not recognized:
        return Target(description=text)
    
    # Default to vehicle classes if no class specified but color was
    return Target(
        description=text,
        classes=classes if classes else set(VEHICLE_CLASSES.keys()),
        color_ranges=color_ranges,
    )


# ============================================================================
# CAMERA SETTINGS (Persisted Per-Camera)
# ============================================================================

@dataclass
class CameraSettings:
    """Persisted settings for a single camera.
    
    Stored in sguard_settings.json under camera_settings[cam_id].
    Loaded/saved by SettingsStore and SuperGuardBot.
    
    Attributes:
        zone: Zone object or None (whole frame)
        target: Target object or None (default: yellow vehicle)
        actuator: List of actuator names bound to this camera (many-to-many)
    """
    zone: Optional[Zone] = None
    target: Optional[Target] = None
    actuator: Optional[List[str]] = None  # List of actuator names bound to this camera
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize for JSON storage.
        
        Returns:
            Dict with keys: zone (list or null), target (string), actuator (list)
        """
        return {
            "zone": self.zone.to_list() if self.zone else None,
            "target": self.target.description if self.target and self.target.description else "",
            "actuator": self.actuator or [],
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CameraSettings":
        """Deserialize from JSON. Migrates legacy single-name actuator string to list.
        
        Handles backwards compatibility:
        - Old format stored actuator as string -> converted to list
        - Missing keys -> defaults to None/empty
        
        Args:
            data: Dict from JSON with keys zone, target, actuator
            
        Returns:
            CameraSettings instance
        """
        zone = Zone.from_list(data["zone"]) if data.get("zone") else None
        target = None
        if data.get("target"):
            target = parse_target_text(data["target"])
        actuator = data.get("actuator")
        if isinstance(actuator, str):  # Legacy: single name -> list
            actuator = [actuator] if actuator else []
        return cls(
            zone=zone,
            target=target,
            actuator=actuator,
        )


# ============================================================================
# ALARM STATE MACHINE (Legacy - kept for compat)
# ============================================================================

class AlarmState(Enum):
    """Alarm state enumeration.
    
    INACTIVE: Monitoring, no alarm active
    ACTIVE: Alarm triggered, plug ON, sending frames to Telegram
    AUTO_RESOLVING: Auto mode, threat gone, waiting for clean frames threshold
    """
    INACTIVE = "inactive"
    ACTIVE = "active"
    AUTO_RESOLVING = "auto_resolving"  # Waiting for clean frames


@dataclass
class Alarm:
    """Legacy single-alarm state machine with thread-safe locking.
    
    DEPRECATED: Replaced by per-camera CameraAlarmState + AlarmManager.
    Kept for backward compatibility with status.json and control message.
    
    States:
    - INACTIVE: Monitoring, no alarm
    - ACTIVE: Alarm triggered, plug ON, sending frames
    - AUTO_RESOLVING: Auto mode, threat gone, waiting for clean frames
    
    Transitions:
    - INACTIVE -> ACTIVE: Detection threshold reached (manual or auto)
    - ACTIVE -> INACTIVE: Manual /togglealarm or cancel button
    - ACTIVE -> AUTO_RESOLVING: Auto mode + clean frames threshold
    - AUTO_RESOLVING -> INACTIVE: Clean frames reached (auto-resolve)
    - AUTO_RESOLVING -> ACTIVE: Threat re-detected during auto-resolve
    """
    state: AlarmState = AlarmState.INACTIVE
    auto_mode: bool = False
    trigger_msg_id: Optional[int] = None   # msg A: trigger frame (audit, never deleted)
    live_msg_id: Optional[int] = None      # msg B: live frame (updated, deleted on cancel)
    control_msg_id: Optional[int] = None   # Mode control message
    known_msg_ids: Set[int] = field(default_factory=set)  # All sent message IDs
    alarm_camera_id: Optional[int] = None  # Camera that triggered alarm
    clean_frames: int = 0                  # Consecutive clean frames (auto-resolve)
    
    # Thread safety
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    
    def activate(self, camera_id: int, auto: bool = False) -> bool:
        """Activate alarm. Returns True if newly activated (was INACTIVE)."""
        with self._lock:
            if self.state == AlarmState.ACTIVE:
                return False
            self.state = AlarmState.ACTIVE
            self.alarm_camera_id = camera_id
            self.auto_mode = auto
            self.clean_frames = 0
            return True
    
    def deactivate(self, keep_trigger: bool = True) -> Dict:
        """Deactivate alarm. Returns info for cleanup (message IDs to delete)."""
        with self._lock:
            if self.state == AlarmState.INACTIVE:
                return {"already_inactive": True}
            
            self.state = AlarmState.INACTIVE
            keep_id = self.trigger_msg_id if keep_trigger else None
            to_delete = [mid for mid in self.known_msg_ids if mid != keep_id]
            self.known_msg_ids.clear()
            self.trigger_msg_id = None
            self.live_msg_id = None
            self.alarm_camera_id = None
            self.clean_frames = 0
            
            return {
                "keep_msg_id": keep_id,
                "delete_msg_ids": to_delete,
                "was_auto": self.auto_mode,
            }
    
    def start_auto_resolve(self) -> bool:
        """Enter auto-resolve state. Returns True if entered (was ACTIVE + auto_mode)."""
        with self._lock:
            if self.state != AlarmState.ACTIVE or not self.auto_mode:
                return False
            self.state = AlarmState.AUTO_RESOLVING
            self.clean_frames = 0
            return True
    
    def increment_clean(self) -> int:
        """Increment clean frame counter. Returns new count (0 if not AUTO_RESOLVING)."""
        with self._lock:
            if self.state == AlarmState.AUTO_RESOLVING:
                self.clean_frames += 1
                return self.clean_frames
            return 0
    
    def reset_clean(self) -> int:
        """Reset clean counter (threat re-detected). Returns 0."""
        with self._lock:
            if self.state == AlarmState.AUTO_RESOLVING:
                self.state = AlarmState.ACTIVE
            self.clean_frames = 0
            return 0
    
    @property
    def is_active(self) -> bool:
        """True if alarm is ACTIVE or AUTO_RESOLVING."""
        return self.state in (AlarmState.ACTIVE, AlarmState.AUTO_RESOLVING)
    
    @property
    def is_auto_resolving(self) -> bool:
        """True if in AUTO_RESOLVING state."""
        return self.state == AlarmState.AUTO_RESOLVING


# ============================================================================
# PER-CAMERA ALARM MANAGER (concurrent alarms protocol)
# ============================================================================

@dataclass
class CameraAlarmState:
    """Per-camera alarm state machine (each camera alarms independently).
    
    Single alarm message per camera protocol:
      first frame (trigger) -> live frames from frame_pool every update_every s
      -> on cancel: first frame is restored into the same message, pool cleared.
    
    Manual trigger behavior:
    - auto_mode is forced False for this camera
    - previous global auto_mode is stored in prev_auto_mode
    - manual cancel restores global auto_mode from prev_auto_mode
    
    Attributes:
        state: Current AlarmState
        cam_id: Camera ID this state belongs to
        auto_mode: Mode of THIS alarm (manual overrides force False)
        prev_auto_mode: Global auto_mode saved on manual trigger (for restore)
        msg_id: Single alarm message ID (first frame + live updates)
        known_msg_ids: All message IDs sent for this camera's alarm
        clean_frames: Consecutive clean frames counter (auto-resolve)
        frame_pool: Temporary pool of recent frames for live updates
        first_frame: First (trigger) frame, restored on cancel for audit trail
        last_update_ts: Timestamp of last live frame update
    """
    state: AlarmState = AlarmState.INACTIVE
    cam_id: int = 0
    auto_mode: bool = False                 # mode of THIS alarm (manual overrides)
    prev_auto_mode: Optional[bool] = None   # global auto_mode saved on manual trigger
    msg_id: Optional[int] = None            # single alarm message (first + live frames)
    known_msg_ids: Set[int] = field(default_factory=set)
    clean_frames: int = 0
    frame_pool: List = field(default_factory=list)  # temp pool of live frames
    first_frame: Any = None                 # first (trigger) frame, restored on cancel
    last_update_ts: float = 0.0
    
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    
    @property
    def is_active(self) -> bool:
        """True if alarm is ACTIVE or AUTO_RESOLVING."""
        return self.state in (AlarmState.ACTIVE, AlarmState.AUTO_RESOLVING)
    
    def activate(self, auto: bool = False, manual: bool = False) -> bool:
        """Activate alarm for this camera. Returns True if newly activated.
        
        Args:
            auto: Global auto_mode setting (used if not manual)
            manual: If True, forces manual mode for this alarm and saves
                   global auto_mode in prev_auto_mode for later restore
        """
        with self._lock:
            if self.state == AlarmState.ACTIVE:
                return False
            self.state = AlarmState.ACTIVE
            self.clean_frames = 0
            self.frame_pool = []
            self.first_frame = None
            if manual:
                # Manual trigger forces manual mode for this alarm;
                # remember the global auto_mode so manual cancel can restore it.
                self.prev_auto_mode = auto
                self.auto_mode = False
            else:
                self.prev_auto_mode = None
                self.auto_mode = auto
            return True
    
    def deactivate(self, keep_trigger: bool = True) -> Dict:
        """Deactivate alarm for this camera. Returns cleanup info.
        
        Args:
            keep_trigger: If True, keep the trigger message (first frame) for audit
            
        Returns:
            Dict with keep_msg_id, delete_msg_ids, was_auto, had_manual, restored_auto
        """
        with self._lock:
            if self.state == AlarmState.INACTIVE:
                return {"already_inactive": True}
            self.state = AlarmState.INACTIVE
            keep_id = self.msg_id if keep_trigger else None
            to_delete = [mid for mid in self.known_msg_ids if mid != keep_id]
            self.known_msg_ids.clear()
            self.msg_id = None
            self.clean_frames = 0
            # Clear frame pool (cache cleanup on alarm end)
            self.frame_pool = []
            was_auto = self.auto_mode
            had_manual = self.prev_auto_mode is not None
            restored_auto = self.prev_auto_mode
            self.prev_auto_mode = None
            return {
                "keep_msg_id": keep_id,
                "delete_msg_ids": to_delete,
                "was_auto": was_auto,
                "had_manual": had_manual,
                "restored_auto": restored_auto,
            }
    
    def start_auto_resolve(self) -> bool:
        """Enter auto-resolve state. Returns True if entered."""
        with self._lock:
            if self.state != AlarmState.ACTIVE or not self.auto_mode:
                return False
            self.state = AlarmState.AUTO_RESOLVING
            self.clean_frames = 0
            return True
    
    def increment_clean(self) -> int:
        """Increment clean frame counter. Returns new count."""
        with self._lock:
            if self.state == AlarmState.AUTO_RESOLVING:
                self.clean_frames += 1
                return self.clean_frames
            return 0
    
    def reset_clean(self) -> int:
        """Reset clean counter (threat re-detected). Returns 0."""
        with self._lock:
            if self.state == AlarmState.AUTO_RESOLVING:
                self.state = AlarmState.ACTIVE
            self.clean_frames = 0
            return 0


class AlarmManager:
    """Per-camera concurrent alarms manager.
    
    Every camera runs its own CameraAlarmState; alarms from different cameras
    are handled simultaneously (no global queue). The 'active camera' (used by
    /cam, /zone, /plug commands) is the last camera that triggered an alarm and
    stays active until another camera takes over (auto or manual trigger).
    
    Provides legacy compatibility properties for status.json and control message.
    """
    
    def __init__(self):
        self._states: Dict[int, CameraAlarmState] = {}
        self.auto_mode: bool = False          # global default mode for new alarms
        self.active_camera_id: int = 1        # camera for commands (last alarm source)
        self.control_msg_id: Optional[int] = None
        self._last_alarm_cam: Optional[int] = None
    
    def get(self, cam_id: int) -> CameraAlarmState:
        """Get (lazily create) per-camera state."""
        if cam_id not in self._states:
            self._states[cam_id] = CameraAlarmState(cam_id=cam_id)
        return self._states[cam_id]
    
    def active_cameras(self) -> List[int]:
        """Cameras with an active alarm, in ascending order."""
        return sorted(c for c, s in self._states.items() if s.is_active)
    
    def any_active(self) -> bool:
        """True if any camera has an active alarm."""
        return any(s.is_active for s in self._states.values())
    
    def is_cam_active(self, cam_id: int) -> bool:
        """Check if specific camera has active alarm."""
        s = self._states.get(cam_id)
        return bool(s and s.is_active)
    
    def activate(self, cam_id: int, auto: bool = False, manual: bool = False) -> bool:
        """Activate alarm for a specific camera (concurrent with others).
        
        Also updates active_camera_id to this camera (becomes command target).
        """
        state = self.get(cam_id)
        if not state.activate(auto=auto, manual=manual):
            return False
        self._last_alarm_cam = cam_id
        self.active_camera_id = cam_id
        return True
    
    def deactivate(self, cam_id: int, keep_trigger: bool = True) -> Dict:
        """Deactivate alarm for a specific camera. Returns cleanup info.
        
        If this was a manual alarm, restores global auto_mode from saved state.
        """
        state = self._states.get(cam_id)
        if not state:
            return {"already_inactive": True}
        result = state.deactivate(keep_trigger=keep_trigger)
        if not result.get("already_inactive") and result.get("had_manual"):
            # Manual cancel restores the global auto mode saved at manual trigger.
            if result.get("restored_auto") is not None:
                self.auto_mode = result["restored_auto"]
        return result
    
    # ---- compatibility helpers (status.json, control message) ----
    @property
    def alarm_camera_id(self) -> Optional[int]:
        """Last camera that triggered an alarm (for status.json)."""
        return self._last_alarm_cam
    
    @alarm_camera_id.setter
    def alarm_camera_id(self, cam_id: int):
        self._last_alarm_cam = cam_id
    
    @property
    def is_active(self) -> bool:
        """True if any camera has active alarm."""
        return self.any_active()
    
    @property
    def trigger_msg_id(self) -> Optional[int]:
        """Message ID of the most recent alarm's trigger frame."""
        cams = self.active_cameras()
        if cams:
            return self._states[cams[-1]].msg_id
        return None
    
    @property
    def live_msg_id(self) -> Optional[int]:
        """Alias for trigger_msg_id (single-message protocol)."""
        return self.trigger_msg_id
    
    @property
    def known_msg_ids(self) -> Set[int]:
        """Union of all message IDs across all camera alarms."""
        ids: Set[int] = set()
        for s in self._states.values():
            ids |= s.known_msg_ids
        return ids
    
    @property
    def clean_frames(self) -> int:
        """Clean frames of the most recent active camera."""
        cams = self.active_cameras()
        if cams:
            return self._states[cams[-1]].clean_frames
        return 0
    
    def reset(self):
        """Reset all alarms (used on shutdown)."""
        for state in self._states.values():
            state.state = AlarmState.INACTIVE
            state.msg_id = None
            state.known_msg_ids.clear()
            state.frame_pool = []
            state.first_frame = None
        self._last_alarm_cam = None