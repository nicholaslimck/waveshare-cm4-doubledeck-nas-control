import logging
import math
import threading
import time
from enum import Enum, auto
from typing import Tuple

import RPi.GPIO as GPIO
import humanize
from PIL import Image, ImageDraw, ImageFont

from lib.LCD_2inch import LCD_2inch
from lib.monitoring import SystemParameters


# =============================================================================
# Enums
# =============================================================================

class DisplayMode(Enum):
    """Display mode for HMI screens."""
    DEVICE_STATUS = auto()  # General device status with circular gauges
    STORAGE_FOCUS = auto()  # Storage-focused view with disk details


class FanMode(Enum):
    """Fan control mode."""
    DEFAULT = auto()  # 0-50% speed, 65-85°C range
    TURBO = auto()    # 0-100% speed, 50-85°C range


# =============================================================================
# Constants
# =============================================================================

# GPIO Pins
USER_BUTTON_PIN = 20

# Button timing (in 0.1s increments, so 5 = 0.5s, 20 = 2s)
DISPLAY_MODE_TOGGLE_THRESHOLD = 5   # 0.5 seconds hold
FAN_MODE_TOGGLE_THRESHOLD = 20      # 2.0 seconds hold

# Display timing
REFRESH_INTERVAL = 0.2  # seconds
DATETIME_FORMAT = "%Y-%m-%d   %H:%M:%S"

# Fan control parameters
FAN_MIN_DUTY_CYCLE = 35  # Minimum duty cycle to prevent motor stall
FAN_CONTROL_INTERVAL = 5  # seconds
FAN_HYSTERESIS = 3  # Temperature change threshold to trigger fan speed adjustment

# Fan mode parameters: (base_temp, critical_temp, max_speed)
FAN_MODE_PARAMS = {
    FanMode.DEFAULT: (65, 85, 50),
    FanMode.TURBO: (50, 85, 100),
}

# Display brightness (0-100)
BRIGHTNESS_DEFAULT = 100
BRIGHTNESS_DIM = 30
AUTO_DIM_TIMEOUT = 300  # seconds (5 minutes)

# Colors (RGB hex values)
COLOR_GOLD = 0xf7ba47
COLOR_YELLOW = 0xf1b400
COLOR_WHITE = 0xffffff
COLOR_GREEN = 0x60ad4c
COLOR_PURPLE = 0x7f35e9
COLOR_BLUE = 0x0088ff
COLOR_CYAN = 0x00ffff
COLOR_LIGHT_GREEN = 0x00ff00
COLOR_GRAY = 0xC1C0BE

# HMI1 Arc coordinates (x1, y1, x2, y2)
HMI1_CPU_ARC = (10, 80, 70, 142)
HMI1_DISK_ARC = (90, 80, 150, 142)
HMI1_RAM_ARC = (173, 80, 233, 142)
HMI1_TEMP_ARC = (253, 80, 313, 142)

# HMI2 CPU Arc coordinates
HMI2_CPU_ARC = (66, 90, 111, 135)


# =============================================================================
# Fonts
# =============================================================================

font02_10 = ImageFont.truetype("./Font/Font02.ttf", 10)
font02_13 = ImageFont.truetype("./Font/Font02.ttf", 13)
font02_14 = ImageFont.truetype("./Font/Font02.ttf", 14)
font02_15 = ImageFont.truetype("./Font/Font02.ttf", 15)
font02_17 = ImageFont.truetype("./Font/Font02.ttf", 17)
font02_18 = ImageFont.truetype("./Font/Font02.ttf", 18)
font02_20 = ImageFont.truetype("./Font/Font02.ttf", 20)
font02_28 = ImageFont.truetype("./Font/Font02.ttf", 28)  # Title font


# =============================================================================
# Helper Functions
# =============================================================================

def format_speed(speed: float) -> Tuple[str, int]:
    """
    Format network speed with appropriate unit and color.

    Args:
        speed: Speed in bytes per second.

    Returns:
        Tuple of (formatted string, color hex value).
    """
    if speed < 1024:
        return f"{math.floor(speed)}B/s", COLOR_LIGHT_GREEN
    elif speed < 1024 * 1024:
        return f"{math.floor(speed / 1024)}KB/s", COLOR_CYAN
    else:
        return f"{math.floor(speed / 1024 / 1024)}MB/s", COLOR_BLUE


def draw_centered_percentage(
    draw: ImageDraw.ImageDraw,
    value: float,
    center_x: int,
    y: int,
    font: ImageFont.FreeTypeFont,
    color: int
) -> None:
    """
    Draw a percentage value with center-aligned positioning.

    Args:
        draw: PIL ImageDraw object.
        value: Percentage value (0-100).
        center_x: X coordinate for center alignment.
        y: Y coordinate.
        font: Font to use.
        color: Color hex value.
    """
    text = f"{math.floor(value)}%"
    # Estimate offset based on digit count
    if value >= 100:
        offset = -6
    elif value >= 10:
        offset = -3
    else:
        offset = 0
    draw.text((center_x + offset, y), text, fill=color, font=font)


def has_disk_warning(disk0_capacity: int, disk1_capacity: int) -> bool:
    """
    Check if there's a disk warning condition (at least one disk missing).

    Args:
        disk0_capacity: Capacity of disk 0.
        disk1_capacity: Capacity of disk 1.

    Returns:
        True if at least one disk has zero capacity.
    """
    return disk0_capacity == 0 or disk1_capacity == 0


class Display:
    """
    Main display controller for the Waveshare CM4 Double-Deck NAS.

    Manages the LCD display, fan control, and user input through a multi-threaded
    architecture with separate threads for system monitoring, button input,
    fan control, and display rendering.
    """

    def __init__(self) -> None:
        """Initialize the display controller and start daemon threads."""
        # State
        self.display_mode: DisplayMode = DisplayMode.DEVICE_STATUS
        self.fan_mode: FanMode = FanMode.DEFAULT
        self._last_fan_temp: float = 0.0  # For hysteresis
        self._last_activity_time: float = time.time()  # For auto-dim
        self._brightness: int = BRIGHTNESS_DEFAULT
        self._has_error: bool = False  # Error state indicator

        # Pre-rendered base images
        self.hmi1_base: Image.Image | None = None
        self.hmi2_base: Image.Image | None = None

        # System monitoring
        self.system_parameters = SystemParameters()

        # GPIO setup
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(USER_BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        t1 = threading.Thread(target=self.system_parameters.update, name="thread1")
        t2 = threading.Thread(target=self.key, name="thread2")
        t3 = threading.Thread(target=self.control_fan, name="thread3")
        t1.daemon = True
        t2.daemon = True
        t3.daemon = True

        self.disp = LCD_2inch()

        # Initialize display
        self.disp.Init()
        # Clear display
        self.disp.clear()

        # Create blank image for drawing.
        blank_canvas = Image.new("RGB", (self.disp.height, self.disp.width), "WHITE")
        ImageDraw.Draw(blank_canvas)
        self.init_HMI1_base()
        self.init_HMI2_base()

        t1.start()
        t2.start()
        t3.start()

    def key(self) -> None:
        """
        Handle USER button input for mode switching.

        - Hold for 0.5 seconds: Toggle display mode (Device Status / Storage Focus)
        - Hold for 2.0 seconds: Toggle fan mode (Default / Turbo)

        Also resets the auto-dim timer on any button press.
        """
        counter = 0
        while True:
            if GPIO.input(USER_BUTTON_PIN) == 0:
                counter += 1
            else:
                if counter > FAN_MODE_TOGGLE_THRESHOLD:
                    # Toggle fan mode
                    if self.fan_mode == FanMode.DEFAULT:
                        logging.info('Fan mode: turbo')
                        self.fan_mode = FanMode.TURBO
                    else:
                        logging.info('Fan mode: default')
                        self.fan_mode = FanMode.DEFAULT
                    self._reset_activity()
                elif counter > DISPLAY_MODE_TOGGLE_THRESHOLD:
                    # Toggle display mode
                    if self.display_mode == DisplayMode.DEVICE_STATUS:
                        logging.info('HMI display mode: Storage Focus')
                        self.display_mode = DisplayMode.STORAGE_FOCUS
                    else:
                        logging.info('HMI display mode: Device Status')
                        self.display_mode = DisplayMode.DEVICE_STATUS
                    self._reset_activity()

                counter = 0
            time.sleep(0.1)

    def _reset_activity(self) -> None:
        """Reset the activity timer and restore full brightness."""
        self._last_activity_time = time.time()
        if self._brightness != BRIGHTNESS_DEFAULT:
            self._set_brightness(BRIGHTNESS_DEFAULT)

    def _set_brightness(self, brightness: int) -> None:
        """
        Set the display backlight brightness.

        Args:
            brightness: Brightness level (0-100).
        """
        self._brightness = brightness
        self.disp.bl_DutyCycle(brightness)

    def _update_auto_dim(self) -> None:
        """Check and apply auto-dim if idle timeout has elapsed."""
        if self._brightness == BRIGHTNESS_DEFAULT:
            elapsed = time.time() - self._last_activity_time
            if elapsed > AUTO_DIM_TIMEOUT:
                logging.info('Auto-dimming display')
                self._set_brightness(BRIGHTNESS_DIM)

    def render(self) -> None:
        """
        Main render loop for the display.

        Continuously updates the LCD with the appropriate HMI screen
        based on the current display mode. Also handles auto-dimming.
        """
        while True:
            try:
                # Update auto-dim state
                self._update_auto_dim()

                # Render the appropriate HMI screen
                if self.display_mode == DisplayMode.DEVICE_STATUS:
                    self.HMI1()
                else:
                    self.HMI2()

                time.sleep(REFRESH_INTERVAL)

            except IOError as e:
                logging.warning(e)
                self._has_error = True
            except KeyboardInterrupt:
                self.disp.module_exit()
                logging.info("quit:")
                exit()

    def set_fan_speed(self, speed: int) -> None:
        """
        Set the PWM fan speed.

        Args:
            speed: Fan speed percentage (0-100). Values > 0 are scaled
                   to avoid the minimum duty cycle that prevents motor stall.
        """
        if speed:
            duty_cycle = math.floor(
                speed * ((100 - FAN_MIN_DUTY_CYCLE) / 100) + FAN_MIN_DUTY_CYCLE
            )
        else:
            duty_cycle = 0

        self.disp._pwm1.ChangeDutyCycle(duty_cycle)

    def control_fan(self) -> None:
        """
        Control the PWM fan based on CPU and disk temperatures.

        Uses temperature-based fan curves with hysteresis to prevent
        rapid oscillation near threshold temperatures.

        Fan modes:
            - DEFAULT: 0-50% speed, 65-85°C range
            - TURBO: 0-100% speed, 50-85°C range
        """
        while True:
            try:
                temperatures = [
                    self.system_parameters.cpu_temperature,
                    self.system_parameters.disk_parameters.disk0.temperature,
                    self.system_parameters.disk_parameters.disk1.temperature
                ]
                ref_temp = max(temperatures)

                # Apply hysteresis: only adjust if temperature changed significantly
                if abs(ref_temp - self._last_fan_temp) >= FAN_HYSTERESIS:
                    self._last_fan_temp = ref_temp

                    # Get fan parameters for current mode
                    base_temp, critical_temp, max_speed = FAN_MODE_PARAMS[self.fan_mode]

                    # Calculate fan speed
                    fan_speed = 0
                    if ref_temp >= base_temp:
                        fan_speed = math.floor(
                            max_speed * (ref_temp - base_temp) / (critical_temp - base_temp)
                        )
                        fan_speed = min(fan_speed, max_speed)  # Clamp to max

                    self.set_fan_speed(fan_speed)

            except Exception as e:
                logging.warning(f"Fan control error: {e}")
                self._has_error = True

            time.sleep(FAN_CONTROL_INTERVAL)

    def init_HMI1_base(self) -> None:
        """Initialize the base image for HMI1 (Device Status) screen."""
        image = Image.open('pic/BL.jpg')

        draw = ImageDraw.Draw(image)
        draw.text((90, 2), 'Device Status', fill=COLOR_GOLD, font=font02_28)

        draw.text((30, 141), 'CPU', fill=COLOR_GOLD, font=font02_15)
        draw.text((107, 141), 'Disk', fill=COLOR_GOLD, font=font02_15)
        draw.text((190, 141), 'RAM', fill=COLOR_GOLD, font=font02_15)
        draw.text((267, 141), 'TEMP', fill=COLOR_GOLD, font=font02_15)

        draw.text((205, 170), 'R X', fill=COLOR_WHITE, font=font02_10, stroke_width=1)
        draw.text((270, 170), 'T X', fill=COLOR_WHITE, font=font02_10, stroke_width=1)

        # Draw base arc circles
        draw.arc(HMI1_CPU_ARC, 0, 360, fill=COLOR_WHITE, width=8)
        draw.arc(HMI1_DISK_ARC, 0, 360, fill=COLOR_WHITE, width=8)
        draw.arc(HMI1_RAM_ARC, 0, 360, fill=COLOR_WHITE, width=8)
        draw.arc(HMI1_TEMP_ARC, 0, 360, fill=COLOR_WHITE, width=8)

        self.hmi1_base = image

    def init_HMI2_base(self) -> None:
        """Initialize the base image for HMI2 (Storage Focus) screen."""
        image = Image.open('pic/Disk.jpg')

        draw = ImageDraw.Draw(image)
        draw.text((60, 55), 'CPU Used', fill=COLOR_GRAY, font=font02_20)

        draw.text((45, 140), 'Used', fill=COLOR_GRAY, font=font02_13)
        draw.text((45, 163), 'Free', fill=COLOR_GRAY, font=font02_13)

        draw.text((185, 93), 'Disk0:', fill=COLOR_GRAY, font=font02_14)
        draw.text((185, 114), 'Disk1:', fill=COLOR_GRAY, font=font02_14)

        draw.text((188, 155), 'TX:', fill=COLOR_GRAY, font=font02_14)
        draw.text((188, 175), 'RX:', fill=COLOR_GRAY, font=font02_14)

        draw.text((133, 205), 'TEMP:', fill=COLOR_BLUE, font=font02_15)

        self.hmi2_base = image

    def HMI1(self) -> None:
        """
        Render the Device Status HMI screen.

        Shows general device status with circular gauge indicators:
        - Time and IP address
        - CPU/System Disk/RAM usage as circular progress indicators
        - CPU temperature gauge
        - Storage drive usage bars
        - Network TX/RX speeds
        - Error indicator (if any errors detected)
        """
        image = self.hmi1_base.copy()
        draw = ImageDraw.Draw(image)

        # Time
        time_t = time.strftime(DATETIME_FORMAT, time.localtime())
        draw.text((5, 50), time_t, fill=COLOR_GOLD, font=font02_15)

        # IP Address
        ip = self.system_parameters.ip_address
        draw.text((170, 50), f'IP : {ip}', fill=COLOR_GOLD, font=font02_15)

        # CPU usage gauge
        cpu_usage = self.system_parameters.cpu_usage
        draw_centered_percentage(draw, cpu_usage, 34, 100, font02_15, COLOR_YELLOW)
        draw.arc(HMI1_CPU_ARC, -90, -90 + (cpu_usage * 360 / 100), fill=COLOR_GREEN, width=8)

        # System disk usage gauge
        disk_usage = self.system_parameters.disk_usage
        draw_centered_percentage(draw, disk_usage.percent, 114, 100, font02_15, COLOR_YELLOW)
        draw.arc(HMI1_DISK_ARC, -90, -90 + (disk_usage.percent * 360 / 100), fill=COLOR_PURPLE, width=8)

        # Memory usage gauge
        memory_usage = self.system_parameters.memory_usage
        draw_centered_percentage(draw, memory_usage, 192, 100, font02_18, COLOR_YELLOW)
        draw.arc(HMI1_RAM_ARC, -90, -90 + (memory_usage * 360 / 100), fill=COLOR_YELLOW, width=8)

        # Temperature gauge
        temp_t = self.system_parameters.cpu_temperature
        draw.text((268, 100), f'{math.floor(temp_t)}℃', fill=COLOR_BLUE, font=font02_18)
        draw.arc(HMI1_TEMP_ARC, -90, -90 + (temp_t * 360 / 100), fill=COLOR_BLUE, width=8)

        # Network speeds
        tx_text, tx_color = format_speed(self.system_parameters.tx_speed)
        rx_text, rx_color = format_speed(self.system_parameters.rx_speed)
        draw.text((250, 190), tx_text, fill=tx_color, font=font02_17)
        draw.text((183, 190), rx_text, fill=rx_color, font=font02_17)

        # Storage drive usage bars
        disk_parameters = self.system_parameters.disk_parameters

        # Disk 0 bar
        draw.rectangle((40, 177, 142, 190))
        if disk_parameters.disk0.capacity == 0:
            draw.rectangle((41, 178, 141, 189), fill=0x000000)
        else:
            draw.rectangle((41, 178, 41 + disk_parameters.disk0.used_percentage, 189), fill=COLOR_PURPLE)
            draw.text((80, 176), f'{math.floor(disk_parameters.disk0.used_percentage)}%',
                      fill=COLOR_YELLOW, font=font02_13)

        # Disk 1 bar
        draw.rectangle((40, 197, 142, 210))
        if disk_parameters.disk1.capacity == 0:
            draw.rectangle((41, 198, 141, 209), fill=0x000000)
        else:
            draw.rectangle((41, 198, 41 + disk_parameters.disk1.used_percentage, 209), fill=COLOR_PURPLE)
            draw.text((80, 196), f'{math.floor(disk_parameters.disk1.used_percentage)}%',
                      fill=COLOR_YELLOW, font=font02_13)

        # RAID indicator
        if disk_parameters.raid:
            draw.text((40, 161), 'RAID', fill=COLOR_GOLD, font=font02_15)

        # Disk warning messages
        if has_disk_warning(disk_parameters.disk0.capacity, disk_parameters.disk1.capacity):
            if self.system_parameters.flag > 0:
                draw.text((30, 210), 'Detected but not installed', fill=COLOR_GOLD, font=font02_15)
            else:
                draw.text((50, 210), 'Unpartitioned/NC', fill=COLOR_GOLD, font=font02_15)

        # Error indicator
        if self._has_error:
            draw.ellipse((300, 35, 315, 50), fill=0xff0000)

        image = image.rotate(180)
        self.disp.ShowImage(image)

    def HMI2(self) -> None:
        """
        Render the Storage Focus HMI screen.

        Shows storage-focused information:
        - Time and IP address
        - CPU usage (small gauge)
        - System disk used/free with humanized values
        - Disk0/Disk1 available space
        - Network TX/RX speeds
        - Temperature
        - Error indicator (if any errors detected)
        """
        image = self.hmi2_base.copy()
        draw = ImageDraw.Draw(image)

        # Time
        time_t = time.strftime(DATETIME_FORMAT, time.localtime())
        draw.text((40, 10), time_t, fill=COLOR_WHITE, font=font02_15)

        # IP Address
        ip = self.system_parameters.ip_address
        draw.text((155, 58), f'IP : {ip}', fill=COLOR_GRAY, font=font02_17)

        # CPU usage (smaller gauge)
        cpu_usage = self.system_parameters.cpu_usage
        draw_centered_percentage(draw, cpu_usage, 84, 105, font02_13, COLOR_YELLOW)
        draw.arc(HMI2_CPU_ARC, -90, -90 + (cpu_usage * 360 / 100), fill=COLOR_PURPLE, width=3)

        # System disk usage with humanized values
        disk_usage = self.system_parameters.disk_usage
        disk_used = humanize.naturalsize(disk_usage.used)
        disk_free = humanize.naturalsize(disk_usage.free)
        draw.text((85, 140), disk_used, fill=COLOR_GRAY, font=font02_13)
        draw.text((85, 163), disk_free, fill=COLOR_GRAY, font=font02_13)

        # Usage bars (avoid division by zero)
        if disk_usage.total > 0:
            draw.rectangle((45, 157, 45 + ((disk_usage.used / disk_usage.total) * 87), 160), fill=COLOR_PURPLE)
            draw.rectangle((45, 180, 45 + ((disk_usage.free / disk_usage.total) * 87), 183), fill=COLOR_PURPLE)

        # Temperature
        temp_t = self.system_parameters.cpu_temperature
        draw.text((170, 205), f'{math.floor(temp_t)}℃', fill=COLOR_BLUE, font=font02_15)

        # Network speeds
        tx_text, tx_color = format_speed(self.system_parameters.tx_speed)
        rx_text, rx_color = format_speed(self.system_parameters.rx_speed)
        draw.text((210, 154), tx_text, fill=tx_color, font=font02_15)
        draw.text((210, 174), rx_text, fill=rx_color, font=font02_15)

        # Storage drive info
        disk_parameters = self.system_parameters.disk_parameters

        # Disk 0
        draw.text((240, 93), humanize.naturalsize(disk_parameters.disk0.available), fill=COLOR_GRAY, font=font02_15)
        if disk_parameters.disk0.capacity == 0:
            draw.rectangle((186, 110, 273, 113), fill=0x000000)
        else:
            draw.rectangle((186, 110, 186 + (disk_parameters.disk0.used_percentage * 87 / 100), 113), fill=COLOR_PURPLE)

        # Disk 1
        draw.text((240, 114), humanize.naturalsize(disk_parameters.disk1.available), fill=COLOR_GRAY, font=font02_15)
        if disk_parameters.disk1.capacity == 0:
            draw.rectangle((186, 131, 273, 134), fill=0x000000)
        else:
            draw.rectangle((186, 131, 186 + (disk_parameters.disk1.used_percentage * 87 / 100), 134), fill=COLOR_PURPLE)

        # RAID indicator
        if disk_parameters.raid:
            draw.text((160, 78), 'RAID', fill=COLOR_GRAY, font=font02_15)

        # Disk warning messages
        if has_disk_warning(disk_parameters.disk0.capacity, disk_parameters.disk1.capacity):
            if self.system_parameters.flag > 0:
                draw.text((155, 135), 'Detected but not installed', fill=COLOR_GRAY, font=font02_14)
            else:
                draw.text((190, 135), 'Unpartitioned/NC', fill=COLOR_GRAY, font=font02_14)

        # Error indicator
        if self._has_error:
            draw.ellipse((300, 5, 315, 20), fill=0xff0000)

        image = image.rotate(180)
        self.disp.ShowImage(image)
