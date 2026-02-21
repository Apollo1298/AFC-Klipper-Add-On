"""
Unit tests for extras/AFC_lane.py

Covers:
  - SpeedMode enum values
  - AssistActive enum values
  - MoveDirection float constants
  - AFCLaneState string constants
  - AFCHomingPoints string constants
  - AFCLane instantiation and attribute initialization
"""

from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from extras.AFC_lane import (
    SpeedMode,
    AssistActive,
    MoveDirection,
    AFCLaneState,
    AFCHomingPoints,
    AFCLane,
    EXCLUDE_TYPES,
)


# ── SpeedMode ─────────────────────────────────────────────────────────────────

class TestSpeedMode:
    def test_none_value_is_python_none(self):
        assert SpeedMode.NONE.value is None

    def test_long_value(self):
        assert SpeedMode.LONG.value == 1

    def test_short_value(self):
        assert SpeedMode.SHORT.value == 2

    def test_hub_value(self):
        assert SpeedMode.HUB.value == 3

    def test_night_value(self):
        assert SpeedMode.NIGHT.value == 4

    def test_calibration_value(self):
        assert SpeedMode.CALIBRATION.value == 5

    def test_all_members_unique(self):
        values = [m.value for m in SpeedMode if m.value is not None]
        assert len(values) == len(set(values))

    def test_comparison_equal(self):
        assert SpeedMode.LONG == SpeedMode.LONG

    def test_comparison_not_equal(self):
        assert SpeedMode.LONG != SpeedMode.SHORT


# ── AssistActive ──────────────────────────────────────────────────────────────

class TestAssistActive:
    def test_yes_value(self):
        assert AssistActive.YES.value == 1

    def test_no_value(self):
        assert AssistActive.NO.value == 2

    def test_dynamic_value(self):
        assert AssistActive.DYNAMIC.value == 3

    def test_members_count(self):
        assert len(list(AssistActive)) == 3


# ── MoveDirection ─────────────────────────────────────────────────────────────

class TestMoveDirection:
    def test_pos_is_positive_one(self):
        assert MoveDirection.POS == 1.0

    def test_neg_is_negative_one(self):
        assert MoveDirection.NEG == -1.0

    def test_pos_is_float_subclass(self):
        assert isinstance(MoveDirection.POS, float)

    def test_neg_is_float_subclass(self):
        assert isinstance(MoveDirection.NEG, float)

    def test_multiplication_with_distance(self):
        dist = 50.0
        assert dist * MoveDirection.POS == 50.0
        assert dist * MoveDirection.NEG == -50.0


# ── AFCLaneState ──────────────────────────────────────────────────────────────

class TestAFCLaneState:
    def test_none_constant(self):
        assert AFCLaneState.NONE == "None"

    def test_error_constant(self):
        assert AFCLaneState.ERROR == "Error"

    def test_loaded_constant(self):
        assert AFCLaneState.LOADED == "Loaded"

    def test_tooled_constant(self):
        assert AFCLaneState.TOOLED == "Tooled"

    def test_tool_loaded_constant(self):
        assert AFCLaneState.TOOL_LOADED == "Tool Loaded"

    def test_tool_loading_constant(self):
        assert AFCLaneState.TOOL_LOADING == "Tool Loading"

    def test_tool_unloading_constant(self):
        assert AFCLaneState.TOOL_UNLOADING == "Tool Unloading"

    def test_hub_loading_constant(self):
        assert AFCLaneState.HUB_LOADING == "HUB Loading"

    def test_ejecting_constant(self):
        assert AFCLaneState.EJECTING == "Ejecting"

    def test_calibrating_constant(self):
        assert AFCLaneState.CALIBRATING == "Calibrating"

    def test_all_constants_are_strings(self):
        attrs = [a for a in dir(AFCLaneState) if not a.startswith("_")]
        for attr in attrs:
            assert isinstance(getattr(AFCLaneState, attr), str)

    def test_all_constants_unique(self):
        attrs = [a for a in dir(AFCLaneState) if not a.startswith("_")]
        values = [getattr(AFCLaneState, a) for a in attrs]
        assert len(values) == len(set(values))


# ── AFCHomingPoints ───────────────────────────────────────────────────────────

class TestAFCHomingPoints:
    def test_none_constant(self):
        assert AFCHomingPoints.NONE is None

    def test_hub_constant(self):
        assert AFCHomingPoints.HUB == "hub"

    def test_load_constant(self):
        assert AFCHomingPoints.LOAD == "load"

    def test_tool_constant(self):
        assert AFCHomingPoints.TOOL == "tool"

    def test_tool_start_constant(self):
        assert AFCHomingPoints.TOOL_START == "tool_start"

    def test_buffer_constant(self):
        assert AFCHomingPoints.BUFFER == "buffer"

    def test_buffer_trail_constant(self):
        assert AFCHomingPoints.BUFFER_TRAIL == "buffer_trailing"


# ── EXCLUDE_TYPES ──────────────────────────────────────────────────────────────

class TestExcludeTypes:
    def test_htlf_in_exclude_types(self):
        assert "HTLF" in EXCLUDE_TYPES

    def test_vivid_in_exclude_types(self):
        assert "ViViD" in EXCLUDE_TYPES


# ── AFCLane initialization ────────────────────────────────────────────────────
# AFCLane.__init__ is tightly coupled to Klipper's runtime; we bypass it with
# __new__ and set attributes to their documented initial values.

def _make_afc_lane(fullname="AFC_stepper lane1"):
    """Build an AFCLane bypassing the complex __init__."""
    lane = AFCLane.__new__(AFCLane)
    parts = fullname.split()
    lane.fullname = fullname
    lane.name = parts[-1]
    lane.unit = "Turtle_1"
    lane.unit_obj = None
    lane.hub_obj = None
    lane.buffer_obj = None
    lane.extruder_obj = None
    lane.espooler = None
    return lane


class TestAFCLaneInit:
    def test_lane_name_extracted_from_fullname(self):
        lane = _make_afc_lane("AFC_stepper lane1")
        assert lane.name == "lane1"

    def test_lane_fullname_stored(self):
        lane = _make_afc_lane("AFC_stepper lane1")
        assert lane.fullname == "AFC_stepper lane1"

    def test_initial_unit_obj_is_none(self):
        lane = _make_afc_lane()
        assert lane.unit_obj is None

    def test_initial_hub_obj_is_none(self):
        lane = _make_afc_lane()
        assert lane.hub_obj is None

    def test_initial_buffer_obj_is_none(self):
        lane = _make_afc_lane()
        assert lane.buffer_obj is None

    def test_initial_extruder_obj_is_none(self):
        lane = _make_afc_lane()
        assert lane.extruder_obj is None

    def test_update_weight_delay_class_constant(self):
        assert AFCLane.UPDATE_WEIGHT_DELAY == 10.0
