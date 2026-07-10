"""
Unit tests for extras/AFC_psf.py
"""

from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from extras.AFC_psf import (
    AFCProportionalSensor,
    AFCSyncFeedback,
    _FlowguardConfig,
    _FlowguardEngine,
)


def _make_sensor(neutral=0.5, max_compression=0.8, max_tension=0.2, reversed_wiring=False):
    sensor = AFCProportionalSensor.__new__(AFCProportionalSensor)
    if reversed_wiring:
        max_compression, max_tension = max_tension, max_compression
    sensor._neutral_point = neutral
    sensor._reversed = max_compression < max_tension
    eps = 1e-12
    if not sensor._reversed:
        sensor._d_neg = max(neutral - max_tension, eps)
        sensor._d_pos = max(max_compression - neutral, eps)
    else:
        sensor._d_pos = max(neutral - max_compression, eps)
        sensor._d_neg = max(max_tension - neutral, eps)
    sensor._gamma = 1.0
    sensor.value_raw = 0.0
    sensor.value = 0.0
    return sensor


class TestMapReading:
    def test_neutral_maps_to_zero(self):
        s = _make_sensor()
        assert s._map_reading(0.5) == pytest.approx(0.0)

    def test_compression_maps_positive(self):
        s = _make_sensor()
        assert s._map_reading(0.8) == pytest.approx(1.0)

    def test_tension_maps_negative(self):
        s = _make_sensor()
        assert s._map_reading(0.2) == pytest.approx(-1.0)

    def test_reversed_wiring(self):
        s = _make_sensor(reversed_wiring=True)
        assert s._map_reading(0.8) == pytest.approx(-1.0)
        assert s._map_reading(0.2) == pytest.approx(1.0)

    def test_is_compressed_and_tensioned(self):
        s = _make_sensor()
        s.value = 0.6
        assert s.is_compressed(0.5)
        assert not s.is_tensioned(0.5)
        s.value = -0.6
        assert s.is_tensioned(0.5)
        assert not s.is_compressed(0.5)


class TestValueToMultiplier:
    def _make_sync(self):
        sync = AFCSyncFeedback.__new__(AFCSyncFeedback)
        sync.multiplier_low = 0.95
        sync.multiplier_high = 1.05
        return sync

    def test_compression_maps_to_low_multiplier(self):
        sync = self._make_sync()
        assert sync._value_to_multiplier(1.0) == pytest.approx(0.95)

    def test_tension_maps_to_high_multiplier(self):
        sync = self._make_sync()
        assert sync._value_to_multiplier(-1.0) == pytest.approx(1.05)

    def test_neutral_maps_to_mid_multiplier(self):
        sync = self._make_sync()
        assert sync._value_to_multiplier(0.0) == pytest.approx(1.0)

    def test_monotonic_decreasing_with_compression(self):
        sync = self._make_sync()
        vals = [sync._value_to_multiplier(v) for v in [-1, -0.5, 0, 0.5, 1]]
        assert vals == sorted(vals, reverse=True)


class TestFlowGuard:
    def _engine(self, relief_mm=8.0):
        cfg = _FlowguardConfig()
        cfg.flowguard_relief_mm = relief_mm
        mult = [1.0]

        def relief(d_ext):
            return d_ext * (mult[0] - 1.0)

        eng = _FlowguardEngine(cfg, relief)
        return eng, mult

    def test_not_armed_before_motion(self):
        eng, _ = self._engine()
        result = eng.update_flowguard(0.0, 0.95)
        assert result["trigger"] == ""

    def test_clog_trip_after_relief_exceeded(self):
        eng, mult = self._engine(relief_mm=2.0)
        eng._armed = True
        mult[0] = 0.9
        for _ in range(20):
            result = eng.update_flowguard(1.0, 0.95)
        assert result["trigger"] == "clog"

    def test_tangle_trip_after_relief_exceeded(self):
        eng, mult = self._engine(relief_mm=2.0)
        eng._armed = True
        mult[0] = 1.1
        for _ in range(20):
            result = eng.update_flowguard(1.0, -0.95)
        assert result["trigger"] == "tangle"


class TestSyncLifecycle:
    def test_disable_resets_multiplier(self):
        from tests.conftest import MockAFC, MockReactor

        sync = AFCSyncFeedback.__new__(AFCSyncFeedback)
        afc = MockAFC()
        sync.afc = afc
        sync.reactor = MockReactor()
        sync.logger = afc.logger
        sync.name = "TN"
        sync.enable = True
        sync._current_multiplier = 0.95
        sync._movement_cb = MagicMock()
        sync.extruder_monitor = MagicMock()
        sync.flowguard = MagicMock()
        sync.sensor = MagicMock()
        sync.sensor.value = 0.0

        lane = MagicMock()
        afc.function.get_current_lane_obj = MagicMock(return_value=lane)

        sync.disable_buffer()
        assert sync.enable is False
        lane.update_rotation_distance.assert_called_with(1.0)
