# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Control program for the Waveshare CM4 Double-Deck NAS that manages a 2-inch LCD display and PWM cooling fan on a Raspberry Pi CM4.

## Running the Application

```bash
cd controller
python main.py
```

### Dependencies

Install via apt and pip:
```bash
sudo apt-get install python3-pip python3-pil python3-numpy
sudo pip3 install RPi.GPIO psutil humanize spidev
```

## Architecture

### Entry Point
`controller/main.py` creates a `Display` object and calls `display.render()` in the main loop.

### Core Module: controller/display.py
The `Display` class orchestrates everything with 4 concurrent execution paths:
- **Main thread**: Refreshes LCD every 0.2s via `render()`
- **Thread 1** (`system_parameters.update`): Monitors system metrics every 1s
- **Thread 2** (`key`): Handles USER button input on GPIO 20
- **Thread 3** (`control_fan`): Adjusts PWM fan speed every 5s based on temperature

### Hardware Abstraction: controller/lib/
- `monitoring.py`: System metrics collection via psutil, /proc, /sys, smartctl
- `LCD_2inch.py`: 240x320 LCD driver with RGB888→RGB565 conversion over SPI
- `lcdconfig.py`: GPIO/SPI pin configuration, PWM setup for backlight and fan

### Display Modes
Two HMI views toggled by holding USER button for 0.5s:
- **Mode 1**: CPU/Disk/RAM/Temp gauges with network speeds and RAID status
- **Mode 2**: Storage-focused view with humanized disk space values

### Fan Control
Temperature-based PWM with two modes (toggled by 2s button hold):
- **Default**: 0-50% speed between 65-85°C
- **Turbo**: 0-100% speed between 50-85°C
- Minimum duty cycle: 35% to prevent motor stall
- Hysteresis: 3°C threshold to prevent rapid oscillation

### Auto-Dim
Display automatically dims after 5 minutes of inactivity. Any button press restores brightness.

## Configuration

Environment variables for customization (set before running):

| Variable | Default | Description |
|----------|---------|-------------|
| `NAS_NETWORK_INTERFACE` | `end0` | Network interface to monitor |
| `NAS_DISK0_ID` | `sda` | First disk device ID |
| `NAS_DISK1_ID` | `sdb` | Second disk device ID |
| `NAS_UPDATE_INTERVAL` | `1` | Monitoring update interval (seconds) |

Example:
```bash
NAS_NETWORK_INTERFACE=eth0 NAS_DISK0_ID=nvme0n1 python main.py
```

## Hardware Pin Mapping

| Function | GPIO (BCM) |
|----------|------------|
| LCD MOSI | 10 (SPI0) |
| LCD CLK | 11 (SPI0) |
| LCD CS | 8 (CE0) |
| LCD DC | 25 |
| LCD RST | 27 |
| Backlight | 18 (PWM) |
| Fan | 19 (PWM) |
| USER Button | 20 (pull-up) |

## Notes

- No test suite exists; testing is manual on hardware
- Disk temperatures require smartmontools (`smartctl`)
- Graceful degradation: missing disks or failed sensors won't crash the application
