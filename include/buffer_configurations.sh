#!/usr/bin/env bash
# Armored Turtle Automated Filament Changer
#
# Copyright (C) 2024-2026 Armored Turtle
#
# This file may be distributed under the terms of the GNU GPLv3 license.

require_afc_psf_module() {
  if [[ ! -f "${afc_path}/extras/AFC_psf.py" ]]; then
    echo "❌ PSF requires extras/AFC_psf.py, but it was not found in ${afc_path}."
    echo "   You are likely on a branch without PSF support (e.g. main)."
    echo "   Check out psf-dev and re-run with: ./install-afc.sh -b psf-dev"
    exit 1
  fi
}

append_buffer_config() {
  local buffer_type="$1"
  local buffer_config=""
  local buffer_name=""
  tn_advance_pin=$2
  tn_trailing_pin=$3

  case "$buffer_type" in
    "TurtleNeck")
      buffer_config=$(cat <<EOF
[AFC_buffer Turtle_1]
advance_pin: ${tn_advance_pin}    # set advance pin
trailing_pin: ${tn_trailing_pin}  # set trailing pin
multiplier_high: 1.05   # default 1.05, factor to feed more filament
multiplier_low:  0.95   # default 0.95, factor to feed less filament
EOF
)
      buffer_name="Turtle_1"
      ;;
    "TurtleNeckV2")
      buffer_config=$(cat <<'EOF'
[AFC_buffer Turtle_1]
advance_pin: !turtleneck:ADVANCE
trailing_pin: !turtleneck:TRAILING
multiplier_high: 1.05   # default 1.05, factor to feed more filament
multiplier_low:  0.95   # default 0.95, factor to feed less filament
led_index: Buffer_Indicator:1

[AFC_led Buffer_Indicator]
pin: turtleneck:RGB
chain_count: 1
color_order: GRBW
initial_RED: 0.0
initial_GREEN: 0.0
initial_BLUE: 0.0
initial_WHITE: 0.0
EOF
)
      buffer_name="Turtle_1"
      ;;
    "PSF")
      require_afc_psf_module
      local psf_adc_pin="${2:-}"
      local psf_section_name="${3:-PSF}"
      if [ -z "$psf_adc_pin" ]; then
        echo "PSF buffer requires ADC pin as second argument"
        return 1
      fi
      buffer_config=$(cat <<EOF
[AFC_psf ${psf_section_name}]
sync_feedback_analog_pin: ${psf_adc_pin}
sync_feedback_analog_max_compression: 0.75
sync_feedback_analog_max_tension: 0.25
sync_feedback_analog_neutral_point: 0.50
sync_multiplier_low: 0.95
sync_multiplier_high: 1.05
flowguard_enabled: True
flowguard_max_relief: 8
EOF
)
      buffer_name="${psf_section_name}"
      ;;
    *)
      echo "Invalid BUFFER_SYSTEM: $buffer_type"
      return 1
      ;;
  esac

  # Check if the buffer configuration already exists in the config file
  if ! grep -qF "$(echo "$buffer_config" | head -n 1)" "$afc_config_dir/AFC_Hardware.cfg"; then
    # Append the buffer configuration to the config file
    echo -e "\n$buffer_config" >> "$afc_config_dir/AFC_Hardware.cfg"
  fi

  # Add [include mcu/TurtleNeckv2.cfg] to AFC_Hardware.cfg if buffer_type is TurtleNeckV2 and not already present
  if [ "$buffer_type" == "TurtleNeckV2" ]; then
    cp "${afc_path}/config/mcu/TurtleNeckv2.cfg" "$afc_config_dir/mcu/"
    if ! grep -qF "[include mcu/TurtleNeckv2.cfg]" "$afc_config_dir/AFC_Hardware.cfg"; then
      echo -e "\n[include mcu/TurtleNeckv2.cfg]" >> "$afc_config_dir/AFC_Hardware.cfg"
    fi
  fi
}

add_buffer_to_extruder() {
  # Function to add a buffer configuration to the [AFC_extruder extruder] section in a configuration file.
  # Arguments:
  #   $1: file_path - The path to the configuration file.
  #   $2: buffer_name - The name of the buffer to be added.
  local file_path="$1"
  local buffer_name="$2"
  local section="[AFC_BoxTurtle Turtle_1]"
  local buffer_line="buffer: $buffer_name"

  awk -v section="$section" -v buffer="$buffer_line" '
    BEGIN { in_section = 0 }
    # Match the start of the target section
    $0 == section {
      in_section = 1
      print $0
      next
    }
    # Insert buffer line before the first blank line within the target section
    in_section && /^$/ {
      print buffer
      in_section = 0
    }
    # End section processing if a new section starts
    in_section && /^\[.+\]/ { in_section = 0 }
    # Print all lines
    { print $0 }
  ' "$file_path" > "$file_path.tmp" && mv "$file_path.tmp" "$file_path"
}

query_tn_pins() {
  # Function to query the user for the TurtleNeck pins.
  # Arguments:
  #   $1: buffer_name - The name of the buffer to be added.
  local buffer_name="$1"
  local input
  tn_advance_pin="^Turtle_1:TN_ADV"
  tn_trailing_pin="^Turtle_1:TN_TRL"

  print_msg INFO "\nPlease enter the pin numbers for the TurtleNeck buffer '$buffer_name':"
  print_msg INFO "(Leave blank to use the default values)"
  print_msg INFO "Ensure you use a pull-up '^' if you are using a AFC end stop pin."
  print_msg INFO "(Default: ^Turtle_1:TN_ADV)"
  print_msg INFO "(Default: ^Turtle_1:TN_TRL)"

  read -p "  Enter the advance pin (default: $tn_advance_pin): " -r input
  if [ -n "$input" ]; then
    tn_advance_pin="$input"
  fi

  read -p "  Enter the trailing pin (default: $tn_trailing_pin): " -r input
  if [ -n "$input" ]; then
    tn_trailing_pin="$input"
  fi

  print_msg INFO "Set ${buffer_name} Advance pin: $tn_advance_pin"
  print_msg INFO "Set ${buffer_name} Trailing pin: $tn_trailing_pin"
}

query_psf_pins() {
  # Query ADC pin for PSF proportional sync-feedback sensor.
  # Arguments:
  #   $1: default pin (optional)
  local input
  psf_adc_pin="${1:-^NightOwl:PSF_ADC}"

  print_msg INFO "\nPlease enter the ADC pin for the PSF sensor:"
  print_msg INFO "(Leave blank to use the default value)"
  print_msg INFO "(Default: $psf_adc_pin)"

  read -p "  Enter the PSF ADC pin (default: $psf_adc_pin): " -r input
  if [ -n "$input" ]; then
    psf_adc_pin="$input"
  fi

  print_msg INFO "Set PSF ADC pin: $psf_adc_pin"
}

set_config_key() {
  # Set or insert a key under a [section] in a config file.
  # Arguments:
  #   $1: file_path
  #   $2: section header including brackets, e.g. "[AFC_NightOwl NightOwl]"
  #   $3: key
  #   $4: value
  local file_path="$1"
  local section="$2"
  local key="$3"
  local value="$4"
  local temp_file
  temp_file=$(mktemp)
  local in_section=false
  local key_set=false

  while IFS= read -r line || [ -n "$line" ]; do
    if [[ "$line" == "$section" ]]; then
      in_section=true
      echo "$line" >> "$temp_file"
      continue
    fi
    if $in_section && [[ "$line" =~ ^\[.+\] ]]; then
      if ! $key_set; then
        echo "$key: $value" >> "$temp_file"
        key_set=true
      fi
      in_section=false
    fi
    if $in_section && [[ "$line" =~ ^${key}: ]]; then
      echo "$key: $value" >> "$temp_file"
      key_set=true
      continue
    fi
    echo "$line" >> "$temp_file"
  done < "$file_path"

  if $in_section && ! $key_set; then
    echo "$key: $value" >> "$temp_file"
  fi

  mv "$temp_file" "$file_path"
}

comment_afc_buffer_section() {
  # Comment out an [AFC_buffer name] section in AFC_Hardware.cfg
  # Arguments:
  #   $1: file_path
  #   $2: buffer section name (e.g. TN)
  local file_path="$1"
  local section_name="$2"
  local temp_file
  temp_file=$(mktemp)
  local in_section=false

  while IFS= read -r line || [ -n "$line" ]; do
    if [[ "$line" =~ ^\[AFC_buffer[[:space:]]+${section_name}\]$ ]]; then
      in_section=true
      echo "# $line" >> "$temp_file"
      continue
    fi
    if $in_section && [[ "$line" =~ ^\[.+\] ]]; then
      in_section=false
    fi
    if $in_section && [[ -n "$line" ]] && [[ ! "$line" =~ ^# ]]; then
      echo "# $line" >> "$temp_file"
      continue
    fi
    echo "$line" >> "$temp_file"
  done < "$file_path"

  mv "$temp_file" "$file_path"
}

configure_nightowl_psf() {
  # Convert NightOwl templates from TurtleNeck to PSF.
  # Uses global psf_adc_pin; prompts if unset.
  require_afc_psf_module
  local hardware_cfg="${afc_config_dir}/AFC_Hardware.cfg"
  local unit_cfg
  unit_cfg=$(find "${afc_config_dir}" -maxdepth 1 -name 'AFC_NightOwl*.cfg' | head -n 1)

  if [ -z "$psf_adc_pin" ]; then
    query_psf_pins "^NightOwl:PSF_ADC"
  fi

  if [ -f "$hardware_cfg" ]; then
    comment_afc_buffer_section "$hardware_cfg" "TN"
    # Remove prior commented PSF block markers if re-running; append active section
    if ! grep -qF "[AFC_psf PSF]" "$hardware_cfg"; then
      append_buffer_config "PSF" "$psf_adc_pin" "PSF"
    fi
    set_config_key "$hardware_cfg" "[AFC_extruder extruder]" "buffer" "PSF"
    set_config_key "$hardware_cfg" "[AFC_extruder extruder]" "buffer_type" "psf"
    # Ramming mode uses PSF as the pre-extruder / ram sensor
    if [ "${toolhead_sensor:-}" == "Ramming" ]; then
      set_config_key "$hardware_cfg" "[AFC_extruder extruder]" "pin_tool_start" "psf"
    fi
  fi

  if [ -n "$unit_cfg" ] && [ -f "$unit_cfg" ]; then
    # Unit section name may be NightOwl or a renamed unit
    local unit_section
    unit_section=$(grep -m1 '^\[AFC_NightOwl ' "$unit_cfg" || true)
    if [ -n "$unit_section" ]; then
      set_config_key "$unit_cfg" "$unit_section" "buffer" "PSF"
      set_config_key "$unit_cfg" "$unit_section" "buffer_type" "psf"
    fi
  fi

  print_msg INFO "NightOwl configured for PSF (buffer: PSF, pin_tool_start: psf)"
  print_msg INFO "Update calibration values in [AFC_psf PSF] after AFC_CALIBRATE_PSENSOR or from Happy-Hare values."
}
