from dataclasses import dataclass, field
from typing import Optional, Set, List, Dict, Any
from enum import Enum
import threading

@dataclass
class Zone:
    rows: int
    cols: int
    cell: int

    def __post_init__(self):
        if not 1 <= self.cell <= self.rows * self.cols:
            raise ValueError(f'Cell {self.cell} out of range for {self.rows}x{self.cols} grid')

    @property
    def row(self) -> int:
        return (self.cell - 1) // self.cols + 1

    @property
    def col(self) -> int:
        return (self.cell - 1) % self.cols + 1

    def contains_point(self, cx: float, cy: float, frame_w: int, frame_h: int) -> bool:
        col_width = 1.0 / self.cols
        row_height = 1.0 / self.rows
        col_min = (self.col - 1) * col_width
        col_max = self.col * col_width
        row_min = (self.row - 1) * row_height
        row_max = self.row * row_height
        return col_min <= cx <= col_max and row_min <= cy <= row_max

    def to_list(self) -> List[int]:
        return [self.rows, self.cols, self.cell]

    @classmethod
    def from_list(cls, data: List[int]) -> Optional['Zone']:
        if not isinstance(data, list) or len(data) != 3:
            return None
        try:
            return cls(rows=int(data[0]), cols=int(data[1]), cell=int(data[2]))
        except (ValueError, TypeError):
            return None

    def __str__(self) -> str:
        return f'N{self.rows}x{self.cols} C{self.cell:02d}'

    def __bool__(self) -> bool:
        return True

def parse_zone_spec(spec: str) -> Optional[Zone]:
    if not spec:
        return None
    s = spec.strip().lower().replace('х', 'x').replace(' ', '').replace('_', '')
    if s in ('off', 'none', '0', 'всё', 'все', 'todo', 'toda', 'nada', 'desactivar'):
        return None
    import re
    m = re.fullmatch('n?(\\d+)x(\\d+)c(\\d+)', s)
    if m:
        rows, cols, cell = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        try:
            return Zone(rows=rows, cols=cols, cell=cell)
        except ValueError:
            return None
    m = re.fullmatch('n(\\d+)c(\\d+)', s)
    if m:
        total, cell = (int(m.group(1)), int(m.group(2)))
        side = int(total ** 0.5)
        if side * side == total and 1 <= cell <= total:
            return Zone(rows=side, cols=side, cell=cell)
    return None

@dataclass
class Target:
    description: str = ''
    classes: Set[int] = field(default_factory=set)
    color_ranges: List[tuple] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.description.strip())

    def matches_class(self, cls_id: int) -> bool:
        return not self.classes or cls_id in self.classes

    def has_color_filter(self) -> bool:
        from .config import Y_LOW, Y_HIGH
        import numpy as np
        default_yellow = [(Y_LOW.tolist(), Y_HIGH.tolist())]
        return bool(self.color_ranges and self.color_ranges != default_yellow)

    def filter_label(self) -> str:
        from .i18n import tr
        class_names = [VEHICLE_CLASSES.get(c, str(c)) for c in sorted(self.classes)]
        class_str = ', '.join(class_names) if class_names else 'all'
        if not self.color_ranges:
            color_str = 'any color'
        elif self.color_ranges == [([15, 60, 80], [40, 255, 255])]:
            color_str = 'yellow'
        else:
            color_str = 'custom color'
        return f'classes: {class_str} | color: {color_str}'
VEHICLE_CLASSES = {2: 'car', 5: 'bus', 7: 'truck'}
CLASS_MAP = {'person': 0, 'people': 0, 'human': 0, 'pedestrian': 0, 'bicycle': 1, 'bike': 1, 'cycle': 1, 'car': 2, 'auto': 2, 'vehicle': 2, 'automobile': 2, 'motorcycle': 3, 'moto': 3, 'motorbike': 3, 'airplane': 4, 'plane': 4, 'bus': 5, 'coach': 5, 'train': 6, 'railway': 6, 'truck': 7, 'lorry': 7, 'van': 7, 'pickup': 7, 'boat': 8, 'ship': 8}
COLOR_MAP = {'red': [([0, 60, 80], [10, 255, 255]), ([170, 60, 80], [180, 255, 255])], 'orange': [([10, 60, 80], [25, 255, 255])], 'yellow': [([15, 60, 80], [40, 255, 255])], 'green': [([40, 60, 80], [85, 255, 255])], 'cyan': [([85, 60, 80], [100, 255, 255])], 'blue': [([100, 60, 80], [130, 255, 255])], 'purple': [([130, 60, 80], [150, 255, 255])], 'pink': [([150, 60, 80], [170, 255, 255])], 'white': [([0, 0, 200], [180, 40, 255])], 'black': [([0, 0, 0], [180, 255, 50])], 'gray': [([0, 0, 50], [180, 40, 200])], 'brown': [([10, 60, 40], [20, 255, 150])]}

def parse_target_text(text: str) -> Target:
    if not text:
        return Target()
    import re
    words = re.findall('[a-zа-яё]+', text.lower())
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
        return Target(description=text)
    return Target(description=text, classes=classes if classes else set(VEHICLE_CLASSES.keys()), color_ranges=color_ranges)

@dataclass
class CameraSettings:
    zone: Optional[Zone] = None
    target: Optional[Target] = None
    actuator: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {'zone': self.zone.to_list() if self.zone else None, 'target': self.target.description if self.target and self.target.description else '', 'actuator': self.actuator or []}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CameraSettings':
        zone = Zone.from_list(data['zone']) if data.get('zone') else None
        target = None
        if data.get('target'):
            target = parse_target_text(data['target'])
        actuator = data.get('actuator')
        if isinstance(actuator, str):
            actuator = [actuator] if actuator else []
        return cls(zone=zone, target=target, actuator=actuator)

class AlarmState(Enum):
    INACTIVE = 'inactive'
    ACTIVE = 'active'
    AUTO_RESOLVING = 'auto_resolving'

@dataclass
class Alarm:
    state: AlarmState = AlarmState.INACTIVE
    auto_mode: bool = False
    trigger_msg_id: Optional[int] = None
    live_msg_id: Optional[int] = None
    control_msg_id: Optional[int] = None
    known_msg_ids: Set[int] = field(default_factory=set)
    alarm_camera_id: Optional[int] = None
    clean_frames: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def activate(self, camera_id: int, auto: bool=False) -> bool:
        with self._lock:
            if self.state == AlarmState.ACTIVE:
                return False
            self.state = AlarmState.ACTIVE
            self.alarm_camera_id = camera_id
            self.auto_mode = auto
            self.clean_frames = 0
            return True

    def deactivate(self, keep_trigger: bool=True) -> Dict:
        with self._lock:
            if self.state == AlarmState.INACTIVE:
                return {'already_inactive': True}
            self.state = AlarmState.INACTIVE
            keep_id = self.trigger_msg_id if keep_trigger else None
            to_delete = [mid for mid in self.known_msg_ids if mid != keep_id]
            self.known_msg_ids.clear()
            self.trigger_msg_id = None
            self.live_msg_id = None
            self.alarm_camera_id = None
            self.clean_frames = 0
            return {'keep_msg_id': keep_id, 'delete_msg_ids': to_delete, 'was_auto': self.auto_mode}

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

    @property
    def is_active(self) -> bool:
        return self.state in (AlarmState.ACTIVE, AlarmState.AUTO_RESOLVING)

    @property
    def is_auto_resolving(self) -> bool:
        return self.state == AlarmState.AUTO_RESOLVING

@dataclass
class CameraAlarmState:
    state: AlarmState = AlarmState.INACTIVE
    cam_id: int = 0
    auto_mode: bool = False
    prev_auto_mode: Optional[bool] = None
    msg_id: Optional[int] = None
    known_msg_ids: Set[int] = field(default_factory=set)
    clean_frames: int = 0
    frame_pool: List = field(default_factory=list)
    first_frame: Any = None
    last_update_ts: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def is_active(self) -> bool:
        return self.state in (AlarmState.ACTIVE, AlarmState.AUTO_RESOLVING)

    def activate(self, auto: bool=False, manual: bool=False) -> bool:
        with self._lock:
            if self.state == AlarmState.ACTIVE:
                return False
            self.state = AlarmState.ACTIVE
            self.clean_frames = 0
            self.frame_pool = []
            self.first_frame = None
            if manual:
                self.prev_auto_mode = auto
                self.auto_mode = False
            else:
                self.prev_auto_mode = None
                self.auto_mode = auto
            return True

    def deactivate(self, keep_trigger: bool=True) -> Dict:
        with self._lock:
            if self.state == AlarmState.INACTIVE:
                return {'already_inactive': True}
            self.state = AlarmState.INACTIVE
            keep_id = self.msg_id if keep_trigger else None
            to_delete = [mid for mid in self.known_msg_ids if mid != keep_id]
            self.known_msg_ids.clear()
            self.msg_id = None
            self.clean_frames = 0
            self.frame_pool = []
            was_auto = self.auto_mode
            had_manual = self.prev_auto_mode is not None
            restored_auto = self.prev_auto_mode
            self.prev_auto_mode = None
            return {'keep_msg_id': keep_id, 'delete_msg_ids': to_delete, 'was_auto': was_auto, 'had_manual': had_manual, 'restored_auto': restored_auto}

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

    def __init__(self):
        self._states: Dict[int, CameraAlarmState] = {}
        self.auto_mode: bool = False
        self.active_camera_id: int = 1
        self.control_msg_id: Optional[int] = None
        self._last_alarm_cam: Optional[int] = None

    def get(self, cam_id: int) -> CameraAlarmState:
        if cam_id not in self._states:
            self._states[cam_id] = CameraAlarmState(cam_id=cam_id)
        return self._states[cam_id]

    def active_cameras(self) -> List[int]:
        return sorted((c for c, s in self._states.items() if s.is_active))

    def any_active(self) -> bool:
        return any((s.is_active for s in self._states.values()))

    def is_cam_active(self, cam_id: int) -> bool:
        s = self._states.get(cam_id)
        return bool(s and s.is_active)

    def activate(self, cam_id: int, auto: bool=False, manual: bool=False) -> bool:
        state = self.get(cam_id)
        if not state.activate(auto=auto, manual=manual):
            return False
        self._last_alarm_cam = cam_id
        self.active_camera_id = cam_id
        return True

    def deactivate(self, cam_id: int, keep_trigger: bool=True) -> Dict:
        state = self._states.get(cam_id)
        if not state:
            return {'already_inactive': True}
        result = state.deactivate(keep_trigger=keep_trigger)
        if not result.get('already_inactive') and result.get('had_manual'):
            if result.get('restored_auto') is not None:
                self.auto_mode = result['restored_auto']
        return result

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
        for state in self._states.values():
            state.state = AlarmState.INACTIVE
            state.msg_id = None
            state.known_msg_ids.clear()
            state.frame_pool = []
            state.first_frame = None
        self._last_alarm_cam = None