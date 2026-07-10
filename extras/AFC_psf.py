# Armored Turtle Automated Filament Changer — PSF (Proportional Sync-Feedback)
#
# Portions adapted from Happy Hare MMU Software
# Copyright (C) 2022-2026  moggieuk (GPLv3)
#
# Copyright (C) 2024-2026 Armored Turtle
#
# This file may be distributed under the terms of the GNU GPLv3 license.

COMPRESSION_STATE_NAME = "Compressed"
TENSION_STATE_NAME = "Tensioned"
NEUTRAL_STATE_NAME = "Neutral"


def lookup_sync_feedback(printer, name, buffer_type="turtleneck"):
    """Resolve TN or PSF sync object by section name."""
    if buffer_type == "psf":
        return printer.lookup_object("AFC_psf {}".format(name))
    return printer.lookup_object("AFC_buffer {}".format(name))


def is_psf_sync(obj):
    return getattr(obj, "buffer_type", "turtleneck") == "psf"


class AFCProportionalSensor:
    """ADC proportional sensor — port of Happy-Hare MmuProportionalSensor."""

    def __init__(self, config):
        self.printer = config.get_printer()
        self._pin = config.get("sync_feedback_analog_pin")
        max_tension = config.getfloat("sync_feedback_analog_max_tension", 1)
        max_compression = config.getfloat("sync_feedback_analog_max_compression", 0)
        raw_min = min(max_tension, max_compression)
        raw_max = max(max_tension, max_compression)
        mid_point = (max_tension + max_compression) / 2.0
        self._neutral_point = config.getfloat(
            "sync_feedback_analog_neutral_point", mid_point,
            minval=raw_min, maxval=raw_max)
        self._gamma = config.getfloat("sync_feedback_analog_gamma", 1)
        self._sample_time = config.getfloat("sync_feedback_analog_sample_time", 0.005)
        self._sample_count = config.getint("sync_feedback_analog_sample_count", 5)
        self._report_time = config.getfloat("sync_feedback_analog_report_time", 0.100)
        self._reversed = max_compression < max_tension
        eps = 1e-12
        if not self._reversed:
            self._d_neg = max(self._neutral_point - max_tension, eps)
            self._d_pos = max(max_compression - self._neutral_point, eps)
        else:
            self._d_pos = max(self._neutral_point - max_compression, eps)
            self._d_neg = max(max_tension - self._neutral_point, eps)
        self.value_raw = 0.0
        self.value = 0.0
        ppins = self.printer.lookup_object("pins")
        self.adc = ppins.setup_pin("adc", self._pin)
        if hasattr(self.adc, "setup_minmax"):
            self.adc.setup_minmax(self._sample_time, self._sample_count)
            self.adc.setup_adc_callback(self._report_time, self._adc_callback)
        else:
            try:
                self.adc.setup_adc_sample(
                    self._report_time, self._sample_time, self._sample_count)
                self.adc.setup_adc_callback(self._adc_callback)
            except TypeError:
                self.adc.setup_adc_sample(self._sample_time, self._sample_count)
                self.adc.setup_adc_callback(self._report_time, self._adc_callback)

    def _map_reading(self, v_raw):
        n = self._neutral_point
        v = float(v_raw)
        if not self._reversed:
            if v >= n:
                y = (v - n) / self._d_pos
            else:
                y = -(n - v) / self._d_neg
        else:
            if v <= n:
                y = (n - v) / self._d_pos
            else:
                y = -(v - n) / self._d_neg
        if self._gamma != 1.0:
            y = (abs(y) ** self._gamma) * (1.0 if y >= 0 else -1.0)
        return max(-1.0, min(1.0, y))

    def _adc_callback(self, *args):
        if len(args) == 1:
            read_time, read_value = args[0][-1]
        elif len(args) == 2:
            read_time, read_value = args
        else:
            raise TypeError("_adc_callback expected 1 or 2 args, got %d" % len(args))
        self.value_raw = float(read_value)
        self.value = self._map_reading(read_value)

    def is_compressed(self, threshold=0.5):
        return self.value >= threshold

    def is_tensioned(self, threshold=0.5):
        return self.value <= -threshold

    def is_pegged(self, threshold=0.95):
        return abs(self.value) >= threshold

    def get_status(self, eventtime):
        state = NEUTRAL_STATE_NAME
        if self.is_compressed(0.5):
            state = COMPRESSION_STATE_NAME
        elif self.is_tensioned(0.5):
            state = TENSION_STATE_NAME
        return {
            "value_raw": self.value_raw,
            "value": self.value,
            "state": state,
        }


class AFCExtruderMonitor:
    """Movement-gated extruder monitor — port of Happy-Hare ExtruderMonitor."""

    CHECK_INTERVAL = 0.5

    def __init__(self, printer, reactor):
        self.printer = printer
        self.reactor = reactor
        self.enabled = True
        self._last_pos = None
        self._callbacks = {}
        self._timer = self.reactor.register_timer(self._check_extruder_movement)
        self.enable()

    def enable(self):
        self.reactor.update_timer(self._timer, self.reactor.NOW)
        self.enabled = True

    def disable(self):
        self.reactor.update_timer(self._timer, self.reactor.NEVER)
        self.enabled = False

    def register_callback(self, cb, movement_threshold):
        if not callable(cb):
            raise TypeError("cb must be callable")
        if movement_threshold is None or movement_threshold <= 0:
            raise ValueError("movement_threshold must be positive")
        self._callbacks[cb] = {"threshold": float(movement_threshold), "accum": 0.0}
        if self.enabled:
            self.reactor.update_timer(self._timer, self.reactor.NOW)

    def remove_callback(self, cb):
        self._callbacks.pop(cb, None)

    def _check_extruder_movement(self, eventtime):
        if not self.enabled or not self._callbacks:
            return eventtime + self.CHECK_INTERVAL
        mcu = self.printer.lookup_object("mcu")
        est_print_time = mcu.estimated_print_time(eventtime)
        toolhead = self.printer.lookup_object("toolhead")
        pos = toolhead.get_extruder().find_past_position(est_print_time)
        if self._last_pos is None:
            self._last_pos = pos
            return eventtime + self.CHECK_INTERVAL
        delta = pos - self._last_pos
        self._last_pos = pos
        if delta != 0.0:
            to_trigger = []
            for cb, state in self._callbacks.items():
                state["accum"] += delta
                if abs(state["accum"]) >= state["threshold"]:
                    signed_distance = state["accum"]
                    state["accum"] = 0.0
                    to_trigger.append((cb, signed_distance))
            for cb, signed_distance in to_trigger:
                try:
                    cb(eventtime, signed_distance)
                except Exception as err:
                    pass
        return eventtime + self.CHECK_INTERVAL


class _FlowguardConfig:
    flowguard_extreme_threshold = 0.9
    flowguard_relief_mm = 8.0
    autotune_stable_x_thresh = 0.3


class _FlowguardEngine:
    """Clog/tangle detection — adapted from Happy-Hare _FlowguardEngine."""

    def __init__(self, cfg, relief_fn):
        self.cfg = cfg
        self._relief_fn = relief_fn
        self.reset()

    def reset(self):
        self._comp_motion_mm = 0.0
        self._tens_motion_mm = 0.0
        self._relief_comp_mm = 0.0
        self._relief_tens_mm = 0.0
        self._trigger = ""
        self._reason = ""
        self._level = 0.0
        self._max_clog = 0.0
        self._max_tangle = 0.0
        self._armed = False
        self._arm_motion_mm = 0.0
        self._arm_last_state = None
        self._active = True

    def deactivate(self):
        self._active = False

    def activate(self):
        self._active = True
        self.reset()

    def _extreme_polarity(self, sensor_reading):
        thr = self.cfg.flowguard_extreme_threshold
        z = float(sensor_reading)
        if z >= thr:
            return 1
        if z <= -thr:
            return -1
        return 0

    def update_flowguard(self, d_ext, sensor_reading):
        if not self._active:
            return self.status()
        effort = self._relief_fn(d_ext)
        state_now = self._extreme_polarity(sensor_reading)
        comp_ext = state_now == 1
        tens_ext = state_now == -1
        self._arm_motion_mm += abs(d_ext)
        if self._arm_last_state is None:
            self._arm_last_state = state_now
        if not self._armed:
            changed_state = state_now != self._arm_last_state
            moved = abs(self._arm_motion_mm) > 0.0
            near_neutral = abs(sensor_reading) < self.cfg.autotune_stable_x_thresh
            if moved and (changed_state or near_neutral):
                self._armed = True
            else:
                return self.status()
        self._arm_last_state = state_now
        if comp_ext:
            self._comp_motion_mm += abs(d_ext)
            if effort < 0:
                self._relief_comp_mm += -effort
            if (self._relief_comp_mm >= self.cfg.flowguard_relief_mm
                    and not self._trigger):
                self._trigger = "clog"
                self._reason = (
                    "Compression stuck after %.2f mm motion and %.2f mm relief"
                    % (self._comp_motion_mm, self._relief_comp_mm))
            c_level = min(1.0, self._relief_comp_mm / self.cfg.flowguard_relief_mm)
            self._level = c_level
            self._max_clog = max(self._max_clog, c_level)
            self._tens_motion_mm = 0.0
            self._relief_tens_mm = 0.0
        elif tens_ext:
            self._tens_motion_mm += abs(d_ext)
            if effort > 0:
                self._relief_tens_mm += effort
            if (self._relief_tens_mm >= self.cfg.flowguard_relief_mm
                    and not self._trigger):
                self._trigger = "tangle"
                self._reason = (
                    "Tension stuck after %.2f mm motion and %.2f mm relief"
                    % (self._tens_motion_mm, self._relief_tens_mm))
            t_level = max(-1.0, -self._relief_tens_mm / self.cfg.flowguard_relief_mm)
            self._level = t_level
            self._max_tangle = min(self._max_tangle, t_level)
            self._comp_motion_mm = 0.0
            self._relief_comp_mm = 0.0
        else:
            self._comp_motion_mm = 0.0
            self._relief_comp_mm = 0.0
            self._tens_motion_mm = 0.0
            self._relief_tens_mm = 0.0
        return self.status()

    def status(self):
        return {
            "active": self._armed and self._active,
            "level": self._level,
            "max_clog": self._max_clog,
            "max_tangle": self._max_tangle,
            "trigger": self._trigger,
            "reason": self._reason,
        }


class AFCSyncFeedback:
    """PSF proportional sync-feedback — replaces TurtleNeck buffer for NightOwl/ERB."""

    def __init__(self, config):
        self.printer = config.get_printer()
        self.afc = self.printer.load_object(config, "AFC")
        self.reactor = self.afc.reactor
        self.gcode = self.afc.gcode
        self.logger = self.afc.logger
        self.name = config.get_name().split(" ")[-1]
        self.buffer_type = "psf"
        self.lanes = {}
        self.enable = False
        self.last_state = NEUTRAL_STATE_NAME
        self.current = ""
        self.min_event_systime = self.reactor.NEVER
        self._current_multiplier = 1.0

        self.debug = config.getboolean("debug", False)
        self.multiplier_high = config.getfloat("sync_multiplier_high", 1.05, minval=1.0)
        self.multiplier_low = config.getfloat("sync_multiplier_low", 0.95, minval=0.0, maxval=1.0)
        self.move_threshold = config.getfloat("sync_feedback_extrude_threshold", 5.0)
        self.compression_threshold = config.getfloat("compression_threshold", 0.5)
        self.tension_threshold = config.getfloat("tension_threshold", 0.5)
        self.flowguard_enabled = config.getboolean("flowguard_enabled", True)
        self._flowguard_cfg = _FlowguardConfig()
        self._flowguard_cfg.flowguard_relief_mm = config.getfloat(
            "flowguard_max_relief", 8.0, minval=1.0)
        self._flowguard_cfg.flowguard_extreme_threshold = config.getfloat(
            "flowguard_extreme_threshold", 0.9, minval=0.5, maxval=1.0)

        self.sensor = AFCProportionalSensor(config)
        self.extruder_monitor = AFCExtruderMonitor(self.printer, self.reactor)
        self.flowguard = _FlowguardEngine(
            self._flowguard_cfg, self._relief_effort)
        self._movement_cb = self._handle_extruder_movement

        self.function = self.printer.load_object(config, "AFC_functions")
        self.show_macros = self.afc.show_macros
        self.function.register_mux_command(
            self.show_macros, "QUERY_PSENSOR", "PSF", self.name,
            self.cmd_QUERY_PSENSOR, self.cmd_QUERY_PSENSOR_help,
            self.cmd_QUERY_PSENSOR_options)
        self.gcode.register_mux_command(
            "ENABLE_BUFFER", "BUFFER", self.name, self.cmd_ENABLE_BUFFER)
        self.gcode.register_mux_command(
            "DISABLE_BUFFER", "BUFFER", self.name, self.cmd_DISABLE_BUFFER)
        self.gcode.register_mux_command(
            "AFC_FLOWGUARD", "PSF", self.name, self.cmd_AFC_FLOWGUARD,
            desc=self.cmd_AFC_FLOWGUARD_help)
        self.gcode.register_mux_command(
            "AFC_CALIBRATE_PSENSOR", "PSF", self.name,
            self.cmd_AFC_CALIBRATE_PSENSOR, desc=self.cmd_AFC_CALIBRATE_PSENSOR_help)

        self.printer.register_event_handler("klippy:ready", self._handle_ready)
        self.afc.buffers[self.name] = self

    def __str__(self):
        return self.name

    @property
    def advance_state(self):
        return self.sensor.is_compressed(self.compression_threshold)

    @property
    def trailing_state(self):
        return self.sensor.is_tensioned(self.tension_threshold)

    def _handle_ready(self):
        self.min_event_systime = self.reactor.monotonic() + 2.0

    def _relief_effort(self, d_ext):
        mult = self._current_multiplier
        return d_ext * (mult - 1.0)

    def _value_to_multiplier(self, value):
        t = (float(value) + 1.0) / 2.0
        return self.multiplier_high + t * (self.multiplier_low - self.multiplier_high)

    def _handle_extruder_movement(self, eventtime, signed_distance):
        if not self.enable:
            return
        value = self.sensor.value
        multiplier = self._value_to_multiplier(value)
        self._current_multiplier = multiplier
        self.set_multiplier(multiplier)
        if self.flowguard_enabled:
            fg = self.flowguard.update_flowguard(abs(signed_distance), value)
            if fg.get("trigger"):
                self._flowguard_trip(fg)

    def _flowguard_trip(self, fg_status):
        trigger = fg_status.get("trigger", "")
        reason = fg_status.get("reason", "")
        if trigger == "clog":
            msg = "FlowGuard detected clog: %s" % reason
        elif trigger == "tangle":
            msg = "FlowGuard detected tangle (AFC not feeding): %s" % reason
        else:
            msg = "FlowGuard triggered: %s" % reason
        self.flowguard.deactivate()
        self.afc.error.AFC_error(msg, True)

    def is_compressed(self, threshold=None):
        if threshold is None:
            threshold = self.compression_threshold
        return self.sensor.is_compressed(threshold)

    def is_tensioned(self, threshold=None):
        if threshold is None:
            threshold = self.tension_threshold
        return self.sensor.is_tensioned(threshold)

    def is_pegged(self, threshold=0.95):
        return self.sensor.is_pegged(threshold)

    def disable_fault_sensitivity(self):
        self.flowguard.deactivate()

    def restore_fault_sensitivity(self):
        if self.flowguard_enabled:
            self.flowguard.activate()

    def activate_flowguard(self):
        if self.flowguard_enabled:
            self.flowguard.activate()

    def deactivate_flowguard(self):
        self.flowguard.deactivate()

    def update_filament_error_pos(self):
        """Reset FlowGuard after PRINT_START purge (TN buffer API compatibility).

        TurtleNeck uses this to re-baseline extruder fault position; PSF clears
        FlowGuard accumulators so purge motion does not cause a false trip.
        Preserves whether FlowGuard is currently active.
        """
        if not self.flowguard_enabled:
            return
        was_active = self.flowguard._active
        self.flowguard.reset()
        self.flowguard._active = was_active

    def enable_buffer(self):
        self.enable = True
        self._current_multiplier = 1.0
        self.extruder_monitor.register_callback(
            self._movement_cb, self.move_threshold)
        if self.flowguard_enabled:
            self.flowguard.activate()
        multiplier = self._value_to_multiplier(self.sensor.value)
        self.set_multiplier(multiplier)
        self.logger.debug("{} PSF sync enabled".format(self.name))

    def disable_buffer(self):
        self.enable = False
        self.extruder_monitor.remove_callback(self._movement_cb)
        self.flowguard.deactivate()
        self.reset_multiplier()
        self.logger.debug("{} PSF sync disabled".format(self.name))

    def set_multiplier(self, multiplier):
        if not self.enable:
            return
        cur_lane = self.afc.function.get_current_lane_obj()
        if cur_lane is None:
            return
        cur_lane.update_rotation_distance(multiplier)
        if multiplier > 1.0:
            self.last_state = TENSION_STATE_NAME
        elif multiplier < 1.0:
            self.last_state = COMPRESSION_STATE_NAME
        else:
            self.last_state = NEUTRAL_STATE_NAME
        if self.debug:
            self.logger.debug(
                "PSF multiplier {:.4f} (sensor {:.3f})".format(
                    multiplier, self.sensor.value))

    def reset_multiplier(self):
        cur_lane = self.afc.function.get_current_lane_obj()
        if cur_lane is not None:
            cur_lane.update_rotation_distance(1.0)
        self._current_multiplier = 1.0
        self.last_state = NEUTRAL_STATE_NAME

    def buffer_status(self):
        return self.last_state

    cmd_QUERY_PSENSOR_help = "Query PSF sensor raw and scaled values"
    cmd_QUERY_PSENSOR_options = {}
    def cmd_QUERY_PSENSOR(self, gcmd):
        status = self.sensor.get_status(self.reactor.monotonic())
        gcmd.respond_info(
            "PSF {}: raw={:.4f} value={:.4f} state={}".format(
                self.name, status["value_raw"], status["value"],
                status["state"]))

    def cmd_ENABLE_BUFFER(self, gcmd):
        self.enable_buffer()

    def cmd_DISABLE_BUFFER(self, gcmd):
        self.disable_buffer()

    cmd_AFC_FLOWGUARD_help = "Enable or disable FlowGuard for PSF"
    def cmd_AFC_FLOWGUARD(self, gcmd):
        enable = gcmd.get_int("ENABLE", 1, minval=0, maxval=1)
        self.flowguard_enabled = bool(enable)
        if enable:
            self.flowguard.activate()
            gcmd.respond_info("FlowGuard enabled for PSF {}".format(self.name))
        else:
            self.flowguard.deactivate()
            gcmd.respond_info("FlowGuard disabled for PSF {}".format(self.name))

    cmd_AFC_CALIBRATE_PSENSOR_help = (
        "Calibrate PSF sensor compression/tension limits")
    def cmd_AFC_CALIBRATE_PSENSOR(self, gcmd):
        import math
        lane = self.afc.function.get_current_lane_obj()
        if lane is None:
            raise gcmd.error("No active lane for PSF calibration")
        move = gcmd.get_float("MOVE", 14.5, minval=1, maxval=100)
        step_size = gcmd.get_float("STEP", 2.0, minval=0.5, maxval=10)
        steps = math.ceil(move * 1.8 / step_size)

        def _avg_raw(n=10, dwell_s=0.1):
            avg = self.sensor.value_raw
            for _ in range(max(1, n - 1)):
                self.reactor.pause(self.reactor.monotonic() + dwell_s)
                avg += 0.1 * (self.sensor.value_raw - avg)
            return avg

        def _seek_limit(msg, count, step, prev_val, ramp, log_label):
            self.logger.info(msg)
            for _ in range(count):
                lane.move(step, lane.short_moves_speed, lane.short_moves_accel, False)
                self.reactor.pause(self.reactor.monotonic() + 0.2)
                val = _avg_raw()
                delta = val - prev_val
                if ramp is None:
                    if delta == 0:
                        continue
                    ramp = delta > 0
                if (ramp and val >= prev_val) or (not ramp and val <= prev_val):
                    prev_val = val
                    self.logger.info(
                        "Seeking ... ADC %s limit: %.4f" % (log_label, val))
                else:
                    return prev_val, ramp, True
            return prev_val, ramp, False

        lane.unsync_to_extruder()
        try:
            raw0 = _avg_raw()
            c_prev, ramp, found_c = _seek_limit(
                "Finding compression limit", steps, step_size, raw0, None, "compressed")
            lane.move(-(steps * step_size / 2.0), lane.short_moves_speed,
                      lane.short_moves_accel, False)
            self.reactor.pause(self.reactor.monotonic() + 0.5)
            t_prev, ramp, found_t = _seek_limit(
                "Finding tension limit", steps, -step_size, _avg_raw(),
                (not ramp) if found_c else None, "tension")
            lane.move(steps * step_size / 2.0, lane.short_moves_speed,
                      lane.short_moves_accel, False)
            if found_c and found_t:
                neutral = (c_prev + t_prev) / 2.0
                msg = (
                    "Calibration Results for PSF %s:\n"
                    "sync_feedback_analog_max_compression: %.4f\n"
                    "sync_feedback_analog_max_tension:     %.4f\n"
                    "sync_feedback_analog_neutral_point:   %.4f\n"
                    "Restart Klipper after updating your config."
                    % (self.name, c_prev, t_prev, neutral))
                gcmd.respond_info(msg)
            else:
                gcmd.respond_info(
                    "Warning: calibration incomplete (compression=%s tension=%s). "
                    "Try increasing MOVE= parameter." % (found_c, found_t))
        finally:
            lane.sync_to_extruder()

    def get_status(self, eventtime=None):
        sensor_status = self.sensor.get_status(eventtime)
        fg = self.flowguard.status()
        response = {
            "buffer_type": self.buffer_type,
            "state": self.last_state,
            "lanes": [lane.name for lane in self.lanes.values()],
            "enabled": self.enable,
            "value_raw": sensor_status["value_raw"],
            "value": sensor_status["value"],
            "sensor_state": sensor_status["state"],
            "flowguard_enabled": self.flowguard_enabled,
            "flowguard": fg,
        }
        if self.enable:
            lane = self.afc.function.get_current_lane_obj()
            if lane is not None:
                response["rotation_distance"] = (
                    lane.extruder_stepper.stepper.get_rotation_distance()[0])
            else:
                response["rotation_distance"] = None
        else:
            response["rotation_distance"] = None
        return response


class AFCAdcSwitchSensor:
    """Virtual endstop from AFCProportionalSensor thresholds — no ADC pin claim.

    Shares the sensor owned by [AFC_psf]; does not call register_adc_button.
    mode is 'compression' or 'tension'.
    """

    def __init__(self, printer, buffer_name, mode, threshold):
        self.printer = printer
        self.reactor = printer.get_reactor()
        self._buffer_name = buffer_name
        self._mode = mode
        self._threshold = float(threshold)
        self._sensor = None
        self._steppers = []
        self._trigger_completion = None
        self._last_trigger_time = None
        self._homing = False
        self._triggered = False
        self._check_timer = None
        self._poll_interval = 0.01

    def _ensure_sensor(self):
        if self._sensor is None:
            psf = self.printer.lookup_object(
                "AFC_psf {}".format(self._buffer_name))
            self._sensor = psf.sensor
        return self._sensor

    def _is_active(self):
        sensor = self._ensure_sensor()
        if self._mode == "compression":
            return sensor.is_compressed(self._threshold)
        return sensor.is_tensioned(self._threshold)

    def query_endstop(self, print_time):
        return self._is_active()

    def setup_pin(self, pin_type, pin_name):
        return self

    def add_stepper(self, stepper):
        self._steppers.append(stepper)

    def get_steppers(self):
        return list(self._steppers)

    def _check_ready(self, eventtime):
        if not self._homing:
            return self.reactor.NEVER
        if self._is_active() == self._triggered:
            self._last_trigger_time = eventtime
            if self._trigger_completion is not None:
                self._trigger_completion.complete(True)
            return self.reactor.NEVER
        return eventtime + self._poll_interval

    def home_start(self, print_time, sample_time, sample_count, rest_time,
                   triggered):
        self._trigger_completion = self.reactor.completion()
        self._last_trigger_time = None
        self._homing = True
        self._triggered = triggered
        if self._is_active() == self._triggered:
            self._last_trigger_time = print_time
            self._trigger_completion.complete(True)
        else:
            self._check_timer = self.reactor.register_timer(
                self._check_ready, self.reactor.NOW)
        return self._trigger_completion

    def home_wait(self, home_end_time):
        self._homing = False
        if self._check_timer is not None:
            self.reactor.unregister_timer(self._check_timer)
            self._check_timer = None
        if self._trigger_completion is not None:
            self._trigger_completion.wait()
        self._trigger_completion = None
        return self._last_trigger_time


def load_config_prefix(config):
    return AFCSyncFeedback(config)
