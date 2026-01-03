# Waveshare CM4 Double-Deck NAS Control

Control program for the Waveshare CM4 Double-Deck NAS that manages a 2-inch LCD display and PWM cooling fan on a Raspberry Pi CM4.

## Features

- **Real-time System Monitoring** - CPU, RAM, disk usage, and temperature
- **Dual Display Modes** - Toggle between device status and storage-focused views
- **Smart Fan Control** - Temperature-based PWM with Default and Turbo modes
- **Network Statistics** - Live RX/TX speed monitoring
- **RAID Status** - Automatic RAID detection and display
- **Auto-Dim** - Display dims after 5 minutes of inactivity
- **Configurable** - Customize via environment variables

## Requirements

### Hardware

- Raspberry Pi CM4
- Waveshare CM4 Double-Deck NAS board
- 2-inch LCD display (240x320, SPI)

### Software

- Raspberry Pi OS (or compatible Linux)
- Python 3.7+
- SPI enabled (`sudo raspi-config` → Interface Options → SPI)

## Installation

1. **Install system dependencies:**

   ```bash
   sudo apt-get update
   sudo apt-get install python3-pip python3-pil python3-numpy smartmontools
   ```

2. **Install Python packages:**

   ```bash
   sudo pip3 install RPi.GPIO psutil humanize spidev
   ```

3. **Clone the repository:**

   ```bash
   git clone https://github.com/yourusername/waveshare-cm4-doubledeck-nas-control.git
   cd waveshare-cm4-doubledeck-nas-control
   ```

## Usage

```bash
cd controller
python main.py
```

### Button Controls

| Action           | Duration | Effect                          |
|------------------|----------|---------------------------------|
| Hold USER button | 0.5s     | Toggle display mode             |
| Hold USER button | 2.0s     | Toggle fan mode (Default/Turbo) |

### Display Modes

- **Device Status**: CPU/Disk/RAM/Temp gauges with network speeds
- **Storage Focus**: Detailed disk space with humanized values

### Fan Modes

| Mode    | Temperature Range | Max Speed |
|---------|-------------------|-----------|
| Default | 65-85°C           | 50%       |
| Turbo   | 50-85°C           | 100%      |

## Configuration

Environment variables for customization:

| Variable                 | Default | Description                                |
|--------------------------|---------|--------------------------------------------|
| `NAS_NETWORK_INTERFACE`  | `end0`  | Network interface to monitor               |
| `NAS_DISK0_ID`           | `sda`   | First disk device ID                       |
| `NAS_DISK1_ID`           | `sdb`   | Second disk device ID                      |
| `NAS_UPDATE_INTERVAL`    | `1`     | Monitoring update interval (seconds)       |
| `NAS_REFRESH_INTERVAL`   | `0.5`   | Display refresh interval (seconds)         |
| `NAS_DISK_TEMP_INTERVAL` | `30`    | Disk temperature polling interval (seconds)|

**Example:**

```bash
NAS_NETWORK_INTERFACE=eth0 NAS_DISK0_ID=nvme0n1 python main.py
```

## Hardware Pin Mapping

| Function    | GPIO (BCM)  |
|-------------|-------------|
| LCD MOSI    | 10 (SPI0)   |
| LCD CLK     | 11 (SPI0)   |
| LCD CS      | 8 (CE0)     |
| LCD DC      | 25          |
| LCD RST     | 27          |
| Backlight   | 18 (PWM)    |
| Fan         | 19 (PWM)    |
| USER Button | 20 (pull-up)|

## Running as a Service

To run on boot, create a systemd service:

```bash
sudo nano /etc/systemd/system/nas-display.service
```

```ini
[Unit]
Description=NAS Display Controller
After=multi-user.target

[Service]
Type=simple
WorkingDirectory=/path/to/waveshare-cm4-doubledeck-nas-control/controller
ExecStart=/usr/bin/python3 main.py
Restart=on-failure
User=root

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable nas-display
sudo systemctl start nas-display
```

## License

See [LICENSE.txt](LICENSE.txt) for details.
