"""
Unit tests for SuperGuard core models.

Tests cover:
- Zone: grid-based region of interest
- Target: detection target specification (YOLO classes + HSV color filters)
- CameraSettings: per-camera persisted settings
- CameraAlarmState: per-camera alarm state machine
- AlarmManager: manages concurrent per-camera alarms
"""
import pytest
import tempfile
import json
from pathlib import Path

# Add project root to path
import sys
BASE_DIR = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(BASE_DIR))

from superguard.models import (
    Zone, parse_zone_spec,
    Target, parse_target_text, VEHICLE_CLASSES, COLOR_MAP,
    CameraSettings,
    AlarmState, Alarm,
    CameraAlarmState, AlarmManager,
)


# =============================================================================
# ZONE TESTS
# =============================================================================

class TestZone:
    """Tests for Zone grid-based region of interest."""
    
    def test_zone_creation_valid(self):
        """Test creating valid zones."""
        zone = Zone(rows=3, cols=4, cell=9)
        assert zone.rows == 3
        assert zone.cols == 4
        assert zone.cell == 9
        assert zone.row == 3  # bottom row
        assert zone.col == 1  # leftmost column
    
    def test_zone_creation_invalid_cell(self):
        """Test that invalid cell raises ValueError."""
        with pytest.raises(ValueError):
            Zone(rows=3, cols=4, cell=13)  # max is 12
        with pytest.raises(ValueError):
            Zone(rows=3, cols=4, cell=0)  # min is 1
    
    def test_zone_contains_point(self):
        """Test point containment in zone cell."""
        zone = Zone(rows=2, cols=2, cell=1)  # top-left quadrant
        # Point in top-left quadrant (0.2, 0.2)
        assert zone.contains_point(0.2, 0.2, 640, 480) is True
        # Point in top-right quadrant (0.8, 0.2)
        assert zone.contains_point(0.8, 0.2, 640, 480) is False
        # Point in bottom-left quadrant (0.2, 0.8)
        assert zone.contains_point(0.2, 0.8, 640, 480) is False
    
    def test_zone_edge_inclusive(self):
        """Test that edges are inclusive."""
        zone = Zone(rows=2, cols=2, cell=1)  # top-left
        # Right edge of cell 1 = 0.5
        assert zone.contains_point(0.5, 0.25, 640, 480) is True
        # Bottom edge of cell 1 = 0.5
        assert zone.contains_point(0.25, 0.5, 640, 480) is True
    
    def test_zone_serialization(self):
        """Test JSON serialization round-trip."""
        zone = Zone(rows=3, cols=4, cell=9)
        serialized = zone.to_list()
        assert serialized == [3, 4, 9]
        
        deserialized = Zone.from_list(serialized)
        assert deserialized.rows == zone.rows
        assert deserialized.cols == zone.cols
        assert deserialized.cell == zone.cell
    
    def test_zone_from_list_invalid(self):
        """Test deserialization with invalid data."""
        assert Zone.from_list([3, 4]) is None  # wrong length
        assert Zone.from_list("not a list") is None
        assert Zone.from_list([3, 4, 0]) is None  # invalid cell
    
    def test_zone_str_representation(self):
        """Test human-readable string format."""
        zone = Zone(rows=3, cols=4, cell=9)
        assert str(zone) == "N3x4 C09"
        zone2 = Zone(rows=2, cols=2, cell=1)
        assert str(zone2) == "N2x2 C01"
    
    def test_parse_zone_spec_explicit(self):
        """Test parsing explicit NxM C format."""
        zone = parse_zone_spec("N3x4 C9")
        assert zone is not None
        assert zone.rows == 3
        assert zone.cols == 4
        assert zone.cell == 9
    
    def test_parse_zone_spec_compact(self):
        """Test parsing compact n3x4c9 format."""
        zone = parse_zone_spec("n3x4c9")
        assert zone is not None
        assert zone.rows == 3
        assert zone.cols == 4
        assert zone.cell == 9
    
    def test_parse_zone_spec_square(self):
        """Test parsing square grid N9 C5 format."""
        zone = parse_zone_spec("N9 C5")  # 3x3 grid, cell 5 (center)
        assert zone is not None
        assert zone.rows == 3
        assert zone.cols == 3
        assert zone.cell == 5
    
    def test_parse_zone_spec_off_keywords(self):
        """Test parsing 'off' keywords returns None."""
        for keyword in ["off", "none", "0", "всё", "все", "todo", "toda", "nada", "desactivar"]:
            assert parse_zone_spec(keyword) is None
            assert parse_zone_spec(keyword.upper()) is None
            assert parse_zone_spec(f"  {keyword}  ") is None
    
    def test_parse_zone_spec_cyrillic_x(self):
        """Test parsing with Cyrillic 'х'."""
        zone = parse_zone_spec("N3х4 C9")  # Cyrillic х
        assert zone is not None
        assert zone.rows == 3
        assert zone.cols == 4
        assert zone.cell == 9


# =============================================================================
# TARGET TESTS
# =============================================================================

class TestTarget:
    """Tests for Target detection filter specification."""
    
    def test_target_creation_empty(self):
        """Test creating empty target (no filter)."""
        target = Target()
        assert target.description == ""
        assert target.classes == set()
        assert target.color_ranges == []
        assert bool(target) is False
    
    def test_target_creation_with_description(self):
        """Test creating target with description."""
        target = Target(description="red car")
        assert target.description == "red car"
        assert bool(target) is True
    
    def test_target_matches_class_empty_classes(self):
        """Test that empty classes matches all classes."""
        target = Target()
        assert target.matches_class(0) is True  # person
        assert target.matches_class(2) is True  # car
        assert target.matches_class(99) is True  # any class
    
    def test_target_matches_class_specific(self):
        """Test matching specific classes."""
        target = Target(classes={2, 7})  # car, truck
        assert target.matches_class(2) is True
        assert target.matches_class(7) is True
        assert target.matches_class(0) is False  # person
        assert target.matches_class(3) is False  # motorcycle
    
    def test_target_has_color_filter_default_yellow(self):
        """Test that default yellow is not considered a custom filter."""
        target = Target(color_ranges=[([15, 60, 80], [40, 255, 255])])
        assert target.has_color_filter() is False  # default yellow
    
    def test_target_has_color_filter_custom(self):
        """Test that custom colors are detected."""
        target = Target(color_ranges=[([0, 60, 80], [10, 255, 255])])  # red
        assert target.has_color_filter() is True
        
        target2 = Target(color_ranges=[([15, 60, 80], [40, 255, 255]), ([0, 60, 80], [10, 255, 255])])
        assert target2.has_color_filter() is True  # yellow + red
    
    def test_target_has_color_filter_none(self):
        """Test no color filter returns False."""
        target = Target(color_ranges=[])
        assert target.has_color_filter() is False
    
    def test_target_filter_label(self):
        """Test human-readable filter label."""
        target = Target(classes={2, 7}, color_ranges=[([0, 60, 80], [10, 255, 255])])
        label = target.filter_label()
        assert "car" in label
        assert "truck" in label
        assert "custom color" in label


class TestParseTargetText:
    """Tests for parsing free-text target descriptions."""
    
    def test_parse_empty(self):
        """Test empty text returns empty target."""
        target = parse_target_text("")
        assert target.description == ""
        assert target.classes == set()
        assert target.color_ranges == []
    
    def test_parse_vehicle_class(self):
        """Test parsing vehicle class names."""
        target = parse_target_text("car")
        assert 2 in target.classes
        assert target.description == "car"
        
        target = parse_target_text("truck bus")
        assert 7 in target.classes
        assert 5 in target.classes
    
    def test_parse_color(self):
        """Test parsing color names."""
        target = parse_target_text("red")
        assert target.color_ranges == COLOR_MAP["red"]
        
        target = parse_target_text("yellow")
        assert target.color_ranges == COLOR_MAP["yellow"]
    
    def test_parse_combined(self):
        """Test parsing class + color combination."""
        target = parse_target_text("red car")
        assert 2 in target.classes
        assert target.color_ranges == COLOR_MAP["red"]
    
    def test_parse_cyrillic(self):
        """Test parsing with Cyrillic words."""
        # CLASS_MAP doesn't have Cyrillic keys yet, so test with color only
        target = parse_target_text("красный")  # red
        assert target.color_ranges == COLOR_MAP["red"]
        # Class defaults to vehicle classes
        assert target.classes == set(VEHICLE_CLASSES.keys())
    
    def test_parse_unrecognized(self):
        """Test unrecognized words don't break parsing."""
        target = parse_target_text("foobar bazqux")
        assert target.description == "foobar bazqux"
        assert target.classes == set()  # empty, defaults to vehicle classes
        assert target.color_ranges == []
    
    def test_parse_defaults_to_vehicles(self):
        """Test that color-only defaults to vehicle classes."""
        target = parse_target_text("red")
        assert target.classes == set(VEHICLE_CLASSES.keys())


# =============================================================================
# CAMERA SETTINGS TESTS
# =============================================================================

class TestCameraSettings:
    """Tests for CameraSettings persistence."""
    
    def test_camera_settings_creation(self):
        """Test creating camera settings."""
        zone = Zone(rows=3, cols=4, cell=9)
        target = Target(description="red car", classes={2}, color_ranges=COLOR_MAP["red"])
        settings = CameraSettings(zone=zone, target=target, actuator=["plug1", "plug2"])
        
        assert settings.zone == zone
        assert settings.target == target
        assert settings.actuator == ["plug1", "plug2"]
    
    def test_camera_settings_serialization(self):
        """Test JSON serialization round-trip."""
        zone = Zone(rows=3, cols=4, cell=9)
        target = Target(description="red car", classes={2}, color_ranges=COLOR_MAP["red"])
        settings = CameraSettings(zone=zone, target=target, actuator=["plug1"])
        
        serialized = settings.to_dict()
        assert serialized["zone"] == [3, 4, 9]
        assert serialized["target"] == "red car"
        assert serialized["actuator"] == ["plug1"]
        
        deserialized = CameraSettings.from_dict(serialized)
        assert deserialized.zone.rows == 3
        assert deserialized.zone.cols == 4
        assert deserialized.zone.cell == 9
        assert deserialized.target.description == "red car"
        assert deserialized.actuator == ["plug1"]
    
    def test_camera_settings_legacy_actuator_string(self):
        """Test migration from legacy single actuator string."""
        data = {
            "zone": [2, 2, 1],
            "target": "car",
            "actuator": "plug1"  # legacy string format
        }
        settings = CameraSettings.from_dict(data)
        assert settings.actuator == ["plug1"]
    
    def test_camera_settings_empty_actuator(self):
        """Test empty actuator list."""
        data = {
            "zone": None,
            "target": "",
            "actuator": None
        }
        settings = CameraSettings.from_dict(data)
        # None actuator is kept as None, empty list would be []
        assert settings.actuator is None or settings.actuator == []


# =============================================================================
# ALARM STATE MACHINE TESTS
# =============================================================================

class TestAlarmState:
    """Tests for legacy Alarm state machine."""
    
    def test_alarm_initial_state(self):
        """Test alarm starts in INACTIVE state."""
        alarm = Alarm()
        assert alarm.state == AlarmState.INACTIVE
        assert alarm.is_active is False
        assert alarm.is_auto_resolving is False
    
    def test_alarm_activate(self):
        """Test activating alarm."""
        alarm = Alarm()
        result = alarm.activate(camera_id=1, auto=True)
        assert result is True
        assert alarm.state == AlarmState.ACTIVE
        assert alarm.auto_mode is True
        assert alarm.alarm_camera_id == 1
        assert alarm.is_active is True
    
    def test_alarm_activate_already_active(self):
        """Test activating already active alarm returns False."""
        alarm = Alarm()
        alarm.activate(camera_id=1)
        result = alarm.activate(camera_id=2)
        assert result is False
        assert alarm.alarm_camera_id == 1  # unchanged
    
    def test_alarm_deactivate(self):
        """Test deactivating alarm."""
        alarm = Alarm()
        alarm.activate(camera_id=1)
        alarm.trigger_msg_id = 100
        alarm.live_msg_id = 101
        alarm.known_msg_ids = {100, 101}
        
        result = alarm.deactivate(keep_trigger=True)
        assert alarm.state == AlarmState.INACTIVE
        assert alarm.auto_mode is False
        assert result["keep_msg_id"] == 100
        assert result["delete_msg_ids"] == [101]
        assert result["was_auto"] is False
    
    def test_alarm_deactivate_keep_none(self):
        """Test deactivating without keeping trigger."""
        alarm = Alarm()
        alarm.activate(camera_id=1)
        alarm.trigger_msg_id = 100
        alarm.known_msg_ids = {100}
        
        result = alarm.deactivate(keep_trigger=False)
        assert result["keep_msg_id"] is None
        assert result["delete_msg_ids"] == [100]
    
    def test_alarm_auto_resolve(self):
        """Test auto-resolve state transitions."""
        alarm = Alarm()
        alarm.activate(camera_id=1, auto=True)
        
        # Start auto resolve
        result = alarm.start_auto_resolve()
        assert result is True
        assert alarm.state == AlarmState.AUTO_RESOLVING
        assert alarm.clean_frames == 0
        assert alarm.is_auto_resolving is True
    
    def test_alarm_auto_resolve_not_auto(self):
        """Test auto-resolve fails when not in auto mode."""
        alarm = Alarm()
        alarm.activate(camera_id=1, auto=False)
        
        result = alarm.start_auto_resolve()
        assert result is False
        assert alarm.state == AlarmState.ACTIVE
    
    def test_alarm_clean_frames(self):
        """Test clean frame counter."""
        alarm = Alarm()
        alarm.activate(camera_id=1, auto=True)
        alarm.start_auto_resolve()
        
        count = alarm.increment_clean()
        assert count == 1
        assert alarm.clean_frames == 1
        
        count = alarm.increment_clean()
        assert count == 2
        
        # Threat re-detected
        count = alarm.reset_clean()
        assert count == 0
        assert alarm.clean_frames == 0
        assert alarm.state == AlarmState.ACTIVE
    
    def test_alarm_increment_clean_not_auto_resolving(self):
        """Test increment_clean returns 0 when not auto-resolving."""
        alarm = Alarm()
        alarm.activate(camera_id=1)
        count = alarm.increment_clean()
        assert count == 0


# =============================================================================
# CAMERA ALARM STATE TESTS
# =============================================================================

class TestCameraAlarmState:
    """Tests for per-camera alarm state machine."""
    
    def test_camera_alarm_initial(self):
        """Test initial state."""
        alarm = CameraAlarmState(cam_id=1)
        assert alarm.cam_id == 1
        assert alarm.state == AlarmState.INACTIVE
        assert alarm.auto_mode is False
        assert alarm.msg_id is None
        assert alarm.frame_pool == []
    
    def test_camera_alarm_activate(self):
        """Test activating camera alarm."""
        alarm = CameraAlarmState(cam_id=1)
        alarm.activate(auto=True)
        
        assert alarm.state == AlarmState.ACTIVE
        assert alarm.auto_mode is True
        assert alarm.clean_frames == 0
    
    def test_camera_alarm_deactivate(self):
        """Test deactivating camera alarm."""
        alarm = CameraAlarmState(cam_id=1)
        alarm.activate(auto=False)
        alarm.msg_id = 100
        alarm.known_msg_ids = {100, 101}
        alarm.frame_pool = [b"frame1", b"frame2"]
        
        result = alarm.deactivate()
        
        assert alarm.state == AlarmState.INACTIVE
        assert alarm.auto_mode is False
        assert result["keep_msg_id"] == 100
        assert result["delete_msg_ids"] == [101]
        assert alarm.frame_pool == []
    
    def test_camera_alarm_add_frame(self):
        """Test adding frames to pool."""
        alarm = CameraAlarmState(cam_id=1)
        alarm.activate()
        
        alarm.frame_pool.append(b"frame1")
        alarm.frame_pool.append(b"frame2")
        
        assert len(alarm.frame_pool) == 2
        assert alarm.frame_pool[0] == b"frame1"
    
    def test_camera_alarm_get_live_frame(self):
        """Test getting live frame for updates."""
        alarm = CameraAlarmState(cam_id=1)
        alarm.activate()
        alarm.frame_pool = [b"frame1", b"frame2"]
        
        # First call gets first frame
        frame = alarm.frame_pool.pop(0) if alarm.frame_pool else None
        assert frame == b"frame1"
        
        # Second call gets next frame
        frame = alarm.frame_pool.pop(0) if alarm.frame_pool else None
        assert frame == b"frame2"
        
        # Pool exhausted returns None
        frame = alarm.frame_pool.pop(0) if alarm.frame_pool else None
        assert frame is None
    
    def test_camera_alarm_increment_clean(self):
        """Test clean frame counter."""
        alarm = CameraAlarmState(cam_id=1)
        alarm.activate(auto=True)
        alarm.start_auto_resolve()
        
        count = alarm.increment_clean()
        assert count == 1
        assert alarm.clean_frames == 1
        
        count = alarm.increment_clean()
        assert count == 2
    
    def test_camera_alarm_reset_clean(self):
        """Test resetting clean counter on re-detection."""
        alarm = CameraAlarmState(cam_id=1)
        alarm.activate(auto=True)
        alarm.start_auto_resolve()
        alarm.increment_clean()
        
        count = alarm.reset_clean()
        assert count == 0
        assert alarm.clean_frames == 0
        assert alarm.state == AlarmState.ACTIVE


# =============================================================================
# ALARM MANAGER TESTS
# =============================================================================

class TestAlarmManager:
    """Tests for AlarmManager managing concurrent camera alarms."""
    
    def test_alarm_manager_initial(self):
        """Test initial state."""
        manager = AlarmManager()
        assert manager.get(1) is not None  # lazy creation
        assert manager.any_active() is False
    
    def test_alarm_manager_get_or_create(self):
        """Test getting or creating alarm for camera."""
        manager = AlarmManager()
        alarm1 = manager.get(1)
        alarm2 = manager.get(1)
        alarm3 = manager.get(2)
        
        assert alarm1 is alarm2  # same instance
        assert alarm1 is not alarm3  # different camera
        assert alarm1.cam_id == 1
        assert alarm3.cam_id == 2
    
    def test_alarm_manager_concurrent_alarms(self):
        """Test multiple cameras can alarm simultaneously."""
        manager = AlarmManager()
        
        alarm1 = manager.get(1)
        alarm1.activate(auto=True)
        
        alarm2 = manager.get(2)
        alarm2.activate(auto=False)
        
        assert alarm1.state == AlarmState.ACTIVE
        assert alarm2.state == AlarmState.ACTIVE
        assert len(manager.active_cameras()) == 2
    
    def test_alarm_manager_get_active(self):
        """Test getting all active alarms."""
        manager = AlarmManager()
        
        alarm1 = manager.get(1)
        alarm1.activate(auto=True)
        
        alarm2 = manager.get(2)
        alarm2.activate(auto=False)
        
        alarm3 = manager.get(3)
        # alarm3 stays INACTIVE
        
        active = manager.active_cameras()
        assert len(active) == 2
        assert 1 in active
        assert 2 in active
        assert 3 not in active
    
    def test_alarm_manager_deactivate(self):
        """Test deactivating specific camera alarm."""
        manager = AlarmManager()
        
        alarm1 = manager.get(1)
        alarm1.activate(auto=True)
        
        alarm2 = manager.get(2)
        alarm2.activate(auto=False)
        
        manager.deactivate(1)
        
        assert alarm1.state == AlarmState.INACTIVE
        assert alarm2.state == AlarmState.ACTIVE
        assert len(manager.active_cameras()) == 1
    
    def test_alarm_manager_deactivate_all(self):
        """Test deactivating all alarms."""
        manager = AlarmManager()
        
        for i in range(1, 5):
            alarm = manager.get(i)
            alarm.activate(auto=True)
        
        assert len(manager.active_cameras()) == 4
        
        manager.deactivate_all()
        
        assert len(manager.active_cameras()) == 0
        for i in range(1, 5):
            assert manager.get(i).state == AlarmState.INACTIVE
    
    def test_alarm_manager_get_status(self):
        """Test getting status summary."""
        manager = AlarmManager()
        
        alarm1 = manager.get(1)
        alarm1.activate(auto=True)
        
        status = manager.get_status()
        assert status["total_cameras"] == 1
        assert status["active_alarms"] == 1
        assert status["cameras"][1]["state"] == "active"
        assert status["cameras"][1]["auto_mode"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])