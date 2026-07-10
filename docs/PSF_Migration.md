# PSF Migration Guide (TurtleNeck to Proportional Sync-Feedback)

This guide covers migrating an AFC NightOwl/ERB setup from TurtleNeck (TN) binary switches to PSF analog sync-feedback. TN and PSF can coexist in the codebase; each printer uses one via `buffer_type`.

## Installer

See [PSF_Install.md](PSF_Install.md) for `install-afc.sh` steps (NightOwl / BoxTurtle, buffer type **B** → PSF).

## Manual config changes

### 1. Unit section

```ini
[AFC_NightOwl NightOwl]
buffer: PSF
buffer_type: psf
```

### 2. Extruder ram sensor

```ini
[AFC_extruder extruder]
pin_tool_start: psf
buffer: PSF
buffer_type: psf
```

### 3. Replace `[AFC_buffer TN]` with `[AFC_psf PSF]`

Comment or remove the TurtleNeck section:

```ini
# [AFC_buffer TN]
# advance_pin: ^NightOwl:TN_ADV
# trailing_pin: ^NightOwl:TN_TRL
```

Add PSF section (use your calibrated values):

```ini
[AFC_psf PSF]
sync_feedback_analog_pin: ^NightOwl:PSF_ADC
sync_feedback_analog_max_compression: 0.75
sync_feedback_analog_max_tension: 0.25
sync_feedback_analog_neutral_point: 0.50
sync_multiplier_low: 0.95
sync_multiplier_high: 1.05
flowguard_enabled: True
flowguard_max_relief: 8
compression_threshold: 0.5
```

### 4. MCU alias (`config/mcu/ERB_2.0.cfg`)

Map `PSF_ADC` to your wired GPIO (example):

```ini
PSF_ADC=gpio1
```

## Calibration

Run on the printer after config update:

```
AFC_CALIBRATE_PSENSOR PSF=PSF
```

Or copy values from an existing Happy-Hare `mmu_hardware.cfg` block.

Query live readings:

```
QUERY_PSENSOR PSF=PSF
```

## G-code reference

| Command | Description |
|---------|-------------|
| `QUERY_PSENSOR PSF=<name>` | Raw/scaled sensor values |
| `AFC_FLOWGUARD PSF=<name> ENABLE=0\|1` | Disable/enable FlowGuard |
| `AFC_CALIBRATE_PSENSOR PSF=<name>` | Auto-calibrate ADC limits |
| `ENABLE_BUFFER BUFFER=<name>` | Arm proportional sync (same as TN) |
| `DISABLE_BUFFER BUFFER=<name>` | Disarm sync |

## FlowGuard vs TN fault timer

In PSF mode, `filament_error_sensitivity` on `[AFC_buffer]` is not used. FlowGuard replaces the TN extruder-position fault timer. FlowGuard is automatically disabled during poop/purge (same as TN `disable_fault`).

## Homing tool check

`enable_buffer_tool_check` uses ADC threshold virtual endstops when `buffer_type: psf`. For initial bring-up, leave this disabled and rely on TOOL_LOAD compression verification.

## Reverting to TurtleNeck

Set `buffer_type: turtleneck`, restore `[AFC_buffer TN]`, set `pin_tool_start: buffer`, and remove `[AFC_psf PSF]`.
