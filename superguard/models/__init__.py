"""
SuperGuard Alarm - Core Data Models

Defines the fundamental data structures used across the system:
- Zone: Grid-based region of interest
- Target: Detection target (classes + color filters)
- CameraSettings: Per-camera persisted settings
- AlarmState: Alarm state machine
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
    
    Example: Zone(rows=3, cols=4, cell=9) = N3x4 C9 = row 3, col 1 (bottom-left)
    """
    rows: int
    cols: int
    cell: int
    
    def __post_init__(self):
        if not (1 <= self.cell <= self.rows * self.cols):
            raise ValueError(f"Cell {self.cell} out of range for {self.rows}x{self.cols} grid")
    
    @property
    def row(self) -> int:
        """1-based row index (top to bottom)."""
        return (self.cell - 1) // self.cols + 1
    
    @property
    def col(self) -> int:
        """1-based column index (left to right)."""
        return (self.cell - 1) % self.cols + 1
    
    def contains_point(self, cx: float, cy: float, frame_w: int, frame_h: int) -> bool:
        """Check if normalized point (cx, cy) falls within this zone cell.
        
        Args:
            cx: Normalized x coordinate (0.0 to 1.0)
            cy: Normalized y coordinate (0.0 to 1.0)
            frame_w: Frame width (for reference)
            frame_h: Frame height (for reference)
            
        Returns:
            True if point center is inside this zone cell
        """
        col_width = 1.0 / self.cols
        row_height = 1.0 / self.rows
        
        col_min = (self.col - 1) * col_width
        col_max = self.col * col_width
        row_min = (self.row - 1) * row_height
        row_max = self.row * row_height
        
        return (col_min <= cx <= col_max) and (row_min <= cy <= row_max)
    
    def to_list(self) -> List[int]:
        """Serialize to [rows, cols, cell] for JSON storage."""
        return [self.rows, self.cols, self.cell]
    
    @classmethod
    def from_list(cls, data: List[int]) -> Optional["Zone"]:
        """Deserialize from [rows, cols, cell]."""
        if not isinstance(data, list) or len(data) != 3:
            return None
        try:
            return cls(rows=int(data[0]), cols=int(data[1]), cell=int(data[2]))
        except (ValueError, TypeError):
            return None
    
    def __str__(self) -> str:
        return f"N{self.rows}x{self.cols} C{self.cell:02d}"
    
    def __bool__(self) -> bool:
        return True  # Zone is always "truthy" when instantiated


def parse_zone_spec(spec: str) -> Optional[Zone]:
    """Parse zone specification string into Zone object.
    
    Supported formats:
    - "N3x4 C9" or "n3x4c9" - explicit grid
    - "N9 C5" or "n9c5" - square grid (3x3, cell 5)
    - "off", "none", "0" - returns None (whole frame)
    
    Cyrillic 'х' is accepted as 'x'.
    """
    if not spec:
        return None
    
    s = spec.strip().lower().replace("х", "x").replace(" ", "").replace("_", "")
    
    # Handle "off" keywords
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
    
    # Format: N9 C5 -> 3x3 square grid
    m = re.fullmatch(r"n(\d+)c(\d+)", s)
    if m:
        total, cell = int(m.group(1)), int(m.group(2))
        side = int(total ** 0.5)
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
    """
    description: str = ""           # Original user text
    classes: Set[int] = field(default_factory=set)  # COCO class IDs
    color_ranges: List[tuple] = field(default_factory=list)  # HSV (low, high) pairs
    
    def __bool__(self) -> bool:
        return bool(self.description.strip())
    
    def matches_class(self, cls_id: int) -> bool:
        """Check if class ID matches target classes (or all if empty)."""
        return not self.classes or cls_id in self.classes
    
    def has_color_filter(self) -> bool:
        """True if color filter is active (non-empty and not default yellow)."""
        from .config import Y_LOW, Y_HIGH  # Avoid circular import
        import numpy as np
        default_yellow = [(Y_LOW.tolist(), Y_HIGH.tolist())]
        return bool(self.color_ranges and self.color_ranges != default_yellow)
    
    def filter_label(self) -> str:
        """Human-readable description of current filter."""
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


# COCO class IDs for vehicles (subset)
VEHICLE_CLASSES = {2: "car", 5: "bus", 7: "truck"}

# Full CLASS_MAP for parsing (COCO class names -> IDs)
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

# HSV color ranges by name
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
    
    Recognizes:
    - Class words: "car", "person", "bus", "truck", etc.
    - Color words: "red", "blue", "yellow", etc.
    
    Unrecognized words are ignored (filter unchanged).
    Returns Target with empty classes/colors if nothing recognized.
    """
    if not text:
        return Target()
    
    import re
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
    
    if not recognized:
        return Target(description=text)  # Keep description but no filter change
    
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
    """Persisted settings for a single camera."""
    zone: Optional[Zone] = None
    target: Optional[Target] = None
    actuator: Optional[List[str]] = None  # List of actuator names bound to this camera
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize for JSON storage."""
        return {
            "zone": self.zone.to_list() if self.zone else None,
            "target": self.target.description if self.target and self.target.description else "",
            "actuator": self.actuator or [],
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CameraSettings":
        """Deserialize from JSON. Migrates legacy single-name actuator string to list."""
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
# ALARM STATE MACHINE
# ============================================================================

class AlarmState(Enum):
    """Alarm state enumeration."""
    INACTIVE = "inactive"
    ACTIVE = "active"
    AUTO_RESOLVING = "auto_resolving"  # Waiting for clean frames


@dataclass
class Alarm:
    """Alarm state machine with thread-safe locking.
    
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
        """Activate alarm. Returns True if newly activated."""
        with self._lock:
            if self.state == AlarmState.ACTIVE:
                return False
            self.state = AlarmState.ACTIVE
            self.alarm_camera_id = camera_id
            self.auto_mode = auto
            self.clean_frames = 0
            return True
    
    def deactivate(self, keep_trigger: bool = True) -> Dict:
        """Deactivate alarm. Returns info for cleanup."""
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
    
    @property
    def is_active(self) -> bool:
        return self.state in (AlarmState.ACTIVE, AlarmState.AUTO_RESOLVING)
    
    @property
    def is_auto_resolving(self) -> bool:
        return self.state == AlarmState.AUTO_RESOLVING

# ============================================================================
# PER-CAMERA ALARM MANAGER (concurrent alarms protocol)
# ============================================================================

@dataclass
class CameraAlarmState:
    """Per-camera alarm state machine (each camera alarms independently).

    Single alarm message per camera:
      first frame (trigger) -> live frames from frame_pool every update_every s
      -> on cancel: first frame is restored into the same message, pool cleared.

    Manual trigger: auto_mode is forced False for this camera and the previous
    global auto_mode is stored in prev_auto_mode; manual cancel restores it.
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
        return self.state in (AlarmState.ACTIVE, AlarmState.AUTO_RESOLVING)

    def activate(self, auto: bool = False, manual: bool = False) -> bool:
        """Activate alarm for this camera. Returns True if newly activated."""
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
        """Deactivate alarm for this camera. Returns cleanup info."""
        with self._lock:
            if self.state == AlarmState.INACTIVE:
                return {"already_inactive": True}
            self.state = AlarmState.INACTIVE
            keep_id = self.msg_id if keep_trigger else None
            to_delete = [mid for mid in self.known_msg_ids if mid != keep_id]
            self.known_msg_ids.clear()
            self.msg_id = None
            self.clean_frames = 0
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
        with self._lock:
            if self.state != AlarmState.ACTIVE or not self.auto_mode:
                return False
            self.state = AlarmState.AUTO_RESOLVING
            self.clean_frames = 0
            return True

    def increment_clean(self) -> int:
        with self._lock:
            if self.state == AlarmState.AUTO_RESOLVING:
                self.clean_frames += 1
                return self.clean_frames
            return 0

    def reset_clean(self) -> int:
        with self._lock:
            if self.state == AlarmState.AUTO_RESOLVING:
                self.state = AlarmState.ACTIVE
            self.clean_frames = 0
            return 0


class AlarmManager:
    """Per-camera concurrent alarms.

    Every camera runs its own CameraAlarmState; alarms from different cameras
    are handled simultaneously (no global queue). The 'active camera' (used by
    /cam, /zone, /plug commands) is the last camera that triggered an alarm and
    stays active until another camera takes over (auto or manual trigger).
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
        return any(s.is_active for s in self._states.values())

    def is_cam_active(self, cam_id: int) -> bool:
        s = self._states.get(cam_id)
        return bool(s and s.is_active)

    def activate(self, cam_id: int, auto: bool = False, manual: bool = False) -> bool:
        """Activate alarm for a specific camera (concurrent with others)."""
        state = self.get(cam_id)
        if not state.activate(auto=auto, manual=manual):
            return False
        self._last_alarm_cam = cam_id
        self.active_camera_id = cam_id
        return True

    def deactivate(self, cam_id: int, keep_trigger: bool = True) -> Dict:
        """Deactivate alarm for a specific camera. Returns cleanup info."""
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
        return self._last_alarm_cam

    @alarm_camera_id.setter
    def alarm_camera_id(self, cam_id: int):
        self._last_alarm_cam = cam_id

    @property
    def is_active(self) -> bool:
        return self.any_active()

    @property
    def trigger_msg_id(self) -> Optional[int]:
        cams = self.active_cameras()
        if cams:
            return self._states[cams[-1]].msg_id
        return None

    @property
    def live_msg_id(self) -> Optional[int]:
        return self.trigger_msg_id

    @property
    def known_msg_ids(self) -> Set[int]:
        ids: Set[int] = set()
        for s in self._states.values():
            ids |= s.known_msg_ids
        return ids

    @property
    def clean_frames(self) -> int:
        cams = self.active_cameras()
        if cams:
            return self._states[cams[-1]].clean_frames
        return 0

    def reset(self):
        self._states.clear()
        self._last_alarm_cam = None
