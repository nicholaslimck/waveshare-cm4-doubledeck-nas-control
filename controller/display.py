import logging
import math
import os
import threading
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Tuple

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
DISPLAY_MODE_TOGGLE_THRESHOLD = 2   # 0.2 seconds hold
FAN_MODE_TOGGLE_THRESHOLD = 20      # 2.0 seconds hold

# Display timing (configurable via environment variable)
REFRESH_INTERVAL = float(os.environ.get('NAS_REFRESH_INTERVAL', '0.5'))  # seconds (default 2 FPS)
DATETIME_FORMAT = "%Y-%m-%d   %H:%M:%S"

# Change detection thresholds for skip-render optimization
CHANGE_THRESHOLD_PERCENT = 1.0  # Skip render if values changed less than this
CHANGE_THRESHOLD_TEMP = 0.5     # Temperature change threshold

# Fan control parameters
FAN_MIN_DUTY_CYCLE = 35  # Minimum duty cycle to prevent motor stall
FAN_CONTROL_INTERVAL = 5  # seconds
FAN_HYSTERESIS = 3  # Temperature change threshold to trigger fan speed adjustment

# Fan curve zones: list of (temp_threshold, fan_speed_percent)
# Fan speed is interpolated between zones for smooth transitions
FAN_CURVE_DEFAULT = [
    (55, 0),    # < 55°C: fan off
    (65, 25),   # 55-65°C: idle cooling
    (75, 40),   # 65-75°C: light load
    (85, 50),   # 75-85°C: max for DEFAULT
]

FAN_CURVE_TURBO = [
    (45, 0),    # < 45°C: fan off
    (55, 30),   # 45-55°C: idle cooling
    (65, 50),   # 55-65°C: moderate load
    (75, 75),   # 65-75°C: heavy load
    (85, 100),  # 75-85°C: max cooling
]

FAN_CURVES = {
    FanMode.DEFAULT: FAN_CURVE_DEFAULT,
    FanMode.TURBO: FAN_CURVE_TURBO,
}

MAX_SPEED_CHANGE = 10  # Max speed change per update cycle for smooth ramping

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
font02_28 = ImageFont.truetype("./Font/Font02.ttf", 28)

# Semantic font aliases for clarity
FONT_TITLE = font02_28
FONT_HEADING = font02_20
FONT_LABEL = font02_15
FONT_VALUE = font02_17
FONT_VALUE_LARGE = font02_18
FONT_SMALL = font02_13
FONT_TINY = font02_10

# Image paths
HMI1_IMAGE_PATH = 'pic/BL.jpg'
HMI2_IMAGE_PATH = 'pic/Disk.jpg'


# =============================================================================
# Helper Functions
# =============================================================================

def calculate_arc_angle(percent: float, max_percent: float = 100.0) -> float:
    """
    Calculate arc end angle for a percentage value, clamped to valid range.

    Args:
        percent: The percentage value (0-100 typically).
        max_percent: Maximum percentage value (default 100).

    Returns:
        Arc end angle in degrees, starting from -90 (top of circle).
    """
    clamped = min(max(percent, 0), max_percent)
    return -90 + (clamped * 360 / max_percent)


def draw_disk_bar(
    draw: ImageDraw.ImageDraw,
    x: int, y: int,
    width: int, height: int,
    used_percentage: float,
    capacity: int,
    show_percentage: bool = True,
    fill_color: int = COLOR_PURPLE,
    text_color: int = COLOR_YELLOW,
    font: ImageFont.FreeTypeFont = font02_13
) -> None:
    """
    Draw a disk usage bar with optional percentage text.

    Args:
        draw: ImageDraw object to draw on.
        x, y: Top-left corner coordinates.
        width, height: Bar dimensions.
        used_percentage: Disk usage percentage (0-100).
        capacity: Disk capacity (0 means disk not available).
        show_percentage: Whether to display percentage text.
        fill_color: Fill color for the usage bar.
        text_color: Color for percentage text.
        font: Font for percentage text.
    """
    # Draw outer border
    draw.rectangle((x, y, x + width, y + height))

    if capacity == 0:
        # Disk not available - fill with black
        draw.rectangle((x + 1, y + 1, x + width - 1, y + height - 1), fill=0x000000)
    else:
        # Draw usage bar (clamped to 100%)
        clamped_percent = min(used_percentage, 100)
        fill_width = clamped_percent * (width - 2) / 100
        draw.rectangle((x + 1, y + 1, x + 1 + fill_width, y + height - 1), fill=fill_color)

        if show_percentage:
            # Center text in bar
            text_x = x + width // 2 - 10
            draw.text((text_x, y - 1), f'{int(used_percentage)}%', fill=text_color, font=font)


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


def get_fan_speed_for_temp(temp: float, curve: list) -> int:
    """
    Get fan speed from temperature using stepped curve with interpolation.

    Args:
        temp: Current temperature in Celsius.
        curve: List of (temp_threshold, fan_speed_percent) tuples.

    Returns:
        Fan speed percentage (0-100).
    """
    for i, (threshold, speed) in enumerate(curve):
        if temp < threshold:
            if i == 0:
                return 0
            # Interpolate between previous and current zone
            prev_threshold, prev_speed = curve[i - 1]
            ratio = (temp - prev_threshold) / (threshold - prev_threshold)
            return int(prev_speed + ratio * (speed - prev_speed))
    # Above highest threshold - return max speed
    return curve[-1][1]


def get_weighted_temp(cpu: float, disk0: float, disk1: float) -> float:
    """
    Calculate weighted reference temperature, filtering invalid sensors.

    CPU is weighted higher (60%) since it responds faster to load changes.
    Disk temps (20% each) are included only if valid (> 0).

    Args:
        cpu: CPU temperature in Celsius.
        disk0: Disk 0 temperature (0 if unavailable).
        disk1: Disk 1 temperature (0 if unavailable).

    Returns:
        Weighted average temperature.
    """
    temps = [(cpu, 0.6)]
    if disk0 > 0:
        temps.append((disk0, 0.2))
    if disk1 > 0:
        temps.append((disk1, 0.2))

    # Normalize weights if sensors are missing
    total_weight = sum(w for _, w in temps)
    return sum(t * w / total_weight for t, w in temps)


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


@dataclass
class RenderCache:
    """Cache of last rendered values for change detection."""
    cpu_usage: float = -1.0
    memory_usage: float = -1.0
    disk_percent: float = -1.0
    cpu_temperature: float = -1.0
    rx_speed: float = -1.0
    tx_speed: float = -1.0
    disk0_percent: float = -1.0
    disk1_percent: float = -1.0
    ip_address: str = ""
    display_mode: Optional['DisplayMode'] = None
    fan_mode: Optional['FanMode'] = None
    last_minute: int = -1  # For time display (only update on minute change)

    def has_significant_change(
        self,
        cpu_usage: float,
        memory_usage: float,
        disk_percent: float,
        cpu_temperature: float,
        rx_speed: float,
        tx_speed: float,
        disk0_percent: float,
        disk1_percent: float,
        ip_address: str,
        display_mode: 'DisplayMode',
        fan_mode: 'FanMode',
        current_minute: int
    ) -> bool:
        """Check if any value has changed significantly enough to warrant a re-render."""
        # Always render on mode change
        if display_mode != self.display_mode:
            return True

        # Always render on fan mode change
        if fan_mode != self.fan_mode:
            return True

        # Always render on minute change (for time display)
        if current_minute != self.last_minute:
            return True

        # Check IP change
        if ip_address != self.ip_address:
            return True

        # Check percentage-based values
        if abs(cpu_usage - self.cpu_usage) >= CHANGE_THRESHOLD_PERCENT:
            return True
        if abs(memory_usage - self.memory_usage) >= CHANGE_THRESHOLD_PERCENT:
            return True
        if abs(disk_percent - self.disk_percent) >= CHANGE_THRESHOLD_PERCENT:
            return True
        if abs(disk0_percent - self.disk0_percent) >= CHANGE_THRESHOLD_PERCENT:
            return True
        if abs(disk1_percent - self.disk1_percent) >= CHANGE_THRESHOLD_PERCENT:
            return True

        # Check temperature
        if abs(cpu_temperature - self.cpu_temperature) >= CHANGE_THRESHOLD_TEMP:
            return True

        # Check network speeds (use relative change for speed)
        if self.rx_speed > 0 and abs(rx_speed - self.rx_speed) / max(self.rx_speed, 1) > 0.1:
            return True
        if self.tx_speed > 0 and abs(tx_speed - self.tx_speed) / max(self.tx_speed, 1) > 0.1:
            return True
        # Also trigger on speed appearing/disappearing
        if (rx_speed > 100) != (self.rx_speed > 100):
            return True
        if (tx_speed > 100) != (self.tx_speed > 100):
            return True

        return False

    def update(
        self,
        cpu_usage: float,
        memory_usage: float,
        disk_percent: float,
        cpu_temperature: float,
        rx_speed: float,
        tx_speed: float,
        disk0_percent: float,
        disk1_percent: float,
        ip_address: str,
        display_mode: 'DisplayMode',
        fan_mode: 'FanMode',
        current_minute: int
    ) -> None:
        """Update the cache with current values."""
        self.cpu_usage = cpu_usage
        self.memory_usage = memory_usage
        self.disk_percent = disk_percent
        self.cpu_temperature = cpu_temperature
        self.rx_speed = rx_speed
        self.tx_speed = tx_speed
        self.disk0_percent = disk0_percent
        self.disk1_percent = disk1_percent
        self.ip_address = ip_address
        self.display_mode = display_mode
        self.fan_mode = fan_mode
        self.last_minute = current_minute


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
        self._current_fan_speed: int = 0  # Current speed for ramp limiting
        self._last_activity_time: float = time.time()  # For auto-dim
        self._brightness: int = BRIGHTNESS_DEFAULT
        self._has_error: bool = False  # Error state indicator
        self._successful_renders: int = 0  # Counter for error reset
        self._render_cache: RenderCache = RenderCache()  # For skip-render optimization
        self._force_render: bool = True  # Force first render

        # Pre-rendered base images (will be rotated during init)
        self.hmi1_base: Optional[Image.Image] = None
        self.hmi2_base: Optional[Image.Image] = None

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
        Handle USER button input for mode switching using edge detection.

        - Hold for 0.5 seconds: Toggle display mode (Device Status / Storage Focus)
        - Hold for 2.0 seconds: Toggle fan mode (Default / Turbo)

        Also resets the auto-dim timer on any button press.

        Uses GPIO edge detection to avoid constant CPU polling. The thread
        sleeps until a button press is detected, then measures hold duration.
        """
        while True:
            # Wait for button press (falling edge) - blocks until pressed
            GPIO.wait_for_edge(USER_BUTTON_PIN, GPIO.FALLING, timeout=1000)

            if GPIO.input(USER_BUTTON_PIN) == 0:
                # Button is pressed - measure hold duration
                press_start = time.time()

                # Wait for button release, checking periodically
                while GPIO.input(USER_BUTTON_PIN) == 0:
                    time.sleep(0.05)  # 50ms resolution for hold detection

                hold_duration = time.time() - press_start

                # Convert to 0.1s units for threshold comparison
                counter = int(hold_duration * 10)

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
        Uses change detection to skip redundant renders.
        """
        while True:
            try:
                # Update auto-dim state
                self._update_auto_dim()

                # Get current values for change detection
                now = time.localtime()
                current_minute = now.tm_min
                current_second = now.tm_sec

                # Force render at minute boundary for clock sync
                if current_second == 0 and self._render_cache.last_minute != current_minute:
                    self._force_render = True

                disk_params = self.system_parameters.disk_parameters
                disk_usage = self.system_parameters.disk_usage

                # Extract values with defaults for None safety
                disk_percent = disk_usage.percent if disk_usage else 0.0
                disk0_pct = disk_params.disk0.used_percentage if disk_params else 0.0
                disk1_pct = disk_params.disk1.used_percentage if disk_params else 0.0

                # Check if we need to render
                should_render = self._force_render or self._render_cache.has_significant_change(
                    cpu_usage=self.system_parameters.cpu_usage,
                    memory_usage=self.system_parameters.memory_usage,
                    disk_percent=disk_percent,
                    cpu_temperature=self.system_parameters.cpu_temperature,
                    rx_speed=self.system_parameters.rx_speed,
                    tx_speed=self.system_parameters.tx_speed,
                    disk0_percent=disk0_pct,
                    disk1_percent=disk1_pct,
                    ip_address=self.system_parameters.ip_address,
                    display_mode=self.display_mode,
                    fan_mode=self.fan_mode,
                    current_minute=current_minute
                )

                if should_render:
                    self._force_render = False

                    # Update cache
                    self._render_cache.update(
                        cpu_usage=self.system_parameters.cpu_usage,
                        memory_usage=self.system_parameters.memory_usage,
                        disk_percent=disk_percent,
                        cpu_temperature=self.system_parameters.cpu_temperature,
                        rx_speed=self.system_parameters.rx_speed,
                        tx_speed=self.system_parameters.tx_speed,
                        disk0_percent=disk0_pct,
                        disk1_percent=disk1_pct,
                        ip_address=self.system_parameters.ip_address,
                        display_mode=self.display_mode,
                        fan_mode=self.fan_mode,
                        current_minute=current_minute
                    )

                    # Render the appropriate HMI screen
                    if self.display_mode == DisplayMode.DEVICE_STATUS:
                        self.HMI1()
                    else:
                        self.HMI2()

                    # Track successful renders to reset error indicator
                    self._successful_renders += 1
                    if self._has_error and self._successful_renders >= 10:
                        logging.info('Clearing error indicator after successful renders')
                        self._has_error = False
                        self._successful_renders = 0

                time.sleep(REFRESH_INTERVAL)

            except IOError as e:
                logging.warning(e)
                self._has_error = True
                self._successful_renders = 0  # Reset counter on error
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

        if self.disp._fan_pwm is not None:
            self.disp._fan_pwm.ChangeDutyCycle(duty_cycle)

    def control_fan(self) -> None:
        """
        Control the PWM fan based on CPU and disk temperatures.

        Uses stepped fan curves with interpolation for smooth, quiet operation.
        CPU temperature is weighted higher (60%) since it responds faster to load.
        Includes ramp limiting to prevent jarring speed changes.

        Fan modes:
            - DEFAULT: Quieter operation, max 50% speed
            - TURBO: Aggressive cooling, max 100% speed
        """
        while True:
            try:
                cpu_temp = self.system_parameters.cpu_temperature
                disk_params = self.system_parameters.disk_parameters
                disk0_temp = disk_params.disk0.temperature if disk_params else 0
                disk1_temp = disk_params.disk1.temperature if disk_params else 0

                # Calculate weighted reference temperature
                ref_temp = get_weighted_temp(cpu_temp, disk0_temp, disk1_temp)

                # Apply hysteresis: only adjust if temperature changed significantly
                if abs(ref_temp - self._last_fan_temp) >= FAN_HYSTERESIS:
                    self._last_fan_temp = ref_temp

                    # Get target speed from stepped curve
                    curve = FAN_CURVES[self.fan_mode]
                    target_speed = get_fan_speed_for_temp(ref_temp, curve)

                    # Apply ramp limiting for smooth transitions
                    delta = target_speed - self._current_fan_speed
                    if abs(delta) > MAX_SPEED_CHANGE:
                        target_speed = self._current_fan_speed + MAX_SPEED_CHANGE * (1 if delta > 0 else -1)

                    self._current_fan_speed = target_speed
                    self.set_fan_speed(target_speed)

            except Exception as e:
                logging.warning(f"Fan control error: {e}")
                self._has_error = True

            time.sleep(FAN_CONTROL_INTERVAL)

    def init_HMI1_base(self) -> None:
        """Initialize the base image for HMI1 (Device Status) screen."""
        if not os.path.exists(HMI1_IMAGE_PATH):
            logging.error(f'Required image not found: {HMI1_IMAGE_PATH}')
            raise FileNotFoundError(f'Missing image: {HMI1_IMAGE_PATH}')

        image = Image.open(HMI1_IMAGE_PATH)

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
        if not os.path.exists(HMI2_IMAGE_PATH):
            logging.error(f'Required image not found: {HMI2_IMAGE_PATH}')
            raise FileNotFoundError(f'Missing image: {HMI2_IMAGE_PATH}')

        image = Image.open(HMI2_IMAGE_PATH)

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
        draw_centered_percentage(draw, cpu_usage, 34, 100, FONT_LABEL, COLOR_YELLOW)
        draw.arc(HMI1_CPU_ARC, -90, calculate_arc_angle(cpu_usage), fill=COLOR_GREEN, width=8)

        # System disk usage gauge
        disk_usage = self.system_parameters.disk_usage
        disk_percent = disk_usage.percent if disk_usage else 0.0
        draw_centered_percentage(draw, disk_percent, 114, 100, FONT_LABEL, COLOR_YELLOW)
        draw.arc(HMI1_DISK_ARC, -90, calculate_arc_angle(disk_percent), fill=COLOR_PURPLE, width=8)

        # Memory usage gauge
        memory_usage = self.system_parameters.memory_usage
        draw_centered_percentage(draw, memory_usage, 192, 100, FONT_VALUE_LARGE, COLOR_YELLOW)
        draw.arc(HMI1_RAM_ARC, -90, calculate_arc_angle(memory_usage), fill=COLOR_YELLOW, width=8)

        # Temperature gauge (clamped to 100 for arc display)
        temp_t = self.system_parameters.cpu_temperature
        draw.text((268, 100), f'{math.floor(temp_t)}℃', fill=COLOR_BLUE, font=FONT_VALUE_LARGE)
        draw.arc(HMI1_TEMP_ARC, -90, calculate_arc_angle(temp_t), fill=COLOR_BLUE, width=8)

        # Network speeds
        tx_text, tx_color = format_speed(self.system_parameters.tx_speed)
        rx_text, rx_color = format_speed(self.system_parameters.rx_speed)
        draw.text((250, 190), tx_text, fill=tx_color, font=font02_17)
        draw.text((183, 190), rx_text, fill=rx_color, font=font02_17)

        # Storage drive usage bars (only if disk_parameters available)
        disk_parameters = self.system_parameters.disk_parameters
        if disk_parameters is not None:
            # Disk 0 bar (width=102, so percentage maps to 0-100 pixels)
            disk0_pct = min(disk_parameters.disk0.used_percentage, 100)
            draw.rectangle((40, 177, 142, 190))
            if disk_parameters.disk0.capacity == 0:
                draw.rectangle((41, 178, 141, 189), fill=0x000000)
            else:
                draw.rectangle((41, 178, 41 + disk0_pct, 189), fill=COLOR_PURPLE)
                draw.text((80, 176), f'{int(disk0_pct)}%', fill=COLOR_YELLOW, font=FONT_SMALL)

            # Disk 1 bar
            disk1_pct = min(disk_parameters.disk1.used_percentage, 100)
            draw.rectangle((40, 197, 142, 210))
            if disk_parameters.disk1.capacity == 0:
                draw.rectangle((41, 198, 141, 209), fill=0x000000)
            else:
                draw.rectangle((41, 198, 41 + disk1_pct, 209), fill=COLOR_PURPLE)
                draw.text((80, 196), f'{int(disk1_pct)}%', fill=COLOR_YELLOW, font=FONT_SMALL)

            # RAID indicator
            if disk_parameters.raid:
                draw.text((40, 161), 'RAID', fill=COLOR_GOLD, font=FONT_LABEL)

            # Disk warning messages
            if has_disk_warning(disk_parameters.disk0.capacity, disk_parameters.disk1.capacity):
                if self.system_parameters.flag > 0:
                    draw.text((30, 210), 'Detected but not installed', fill=COLOR_GOLD, font=FONT_LABEL)
                else:
                    draw.text((50, 210), 'Unpartitioned/NC', fill=COLOR_GOLD, font=FONT_LABEL)

        # Error indicator
        if self._has_error:
            draw.ellipse((300, 35, 315, 50), fill=0xff0000)

        # Turbo mode indicator
        if self.fan_mode == FanMode.TURBO:
            draw.text((255, 35), 'TURBO', fill=COLOR_CYAN, font=font02_13)

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
        draw_centered_percentage(draw, cpu_usage, 84, 105, FONT_SMALL, COLOR_YELLOW)
        draw.arc(HMI2_CPU_ARC, -90, calculate_arc_angle(cpu_usage), fill=COLOR_PURPLE, width=3)

        # System disk usage with humanized values
        disk_usage = self.system_parameters.disk_usage
        if disk_usage is not None:
            disk_used = humanize.naturalsize(disk_usage.used)
            disk_free = humanize.naturalsize(disk_usage.free)
            draw.text((85, 140), disk_used, fill=COLOR_GRAY, font=FONT_SMALL)
            draw.text((85, 163), disk_free, fill=COLOR_GRAY, font=FONT_SMALL)

            # Usage bars (avoid division by zero)
            if disk_usage.total > 0:
                draw.rectangle((45, 157, 45 + ((disk_usage.used / disk_usage.total) * 87), 160), fill=COLOR_PURPLE)
                draw.rectangle((45, 180, 45 + ((disk_usage.free / disk_usage.total) * 87), 183), fill=COLOR_PURPLE)

        # Temperature
        temp_t = self.system_parameters.cpu_temperature
        draw.text((170, 205), f'{math.floor(temp_t)}℃', fill=COLOR_BLUE, font=FONT_LABEL)

        # Network speeds
        tx_text, tx_color = format_speed(self.system_parameters.tx_speed)
        rx_text, rx_color = format_speed(self.system_parameters.rx_speed)
        draw.text((210, 154), tx_text, fill=tx_color, font=font02_15)
        draw.text((210, 174), rx_text, fill=rx_color, font=font02_15)

        # Storage drive info (only if disk_parameters available)
        disk_parameters = self.system_parameters.disk_parameters
        if disk_parameters is not None:
            # Disk 0
            disk0_pct = min(disk_parameters.disk0.used_percentage, 100)
            draw.text((240, 93), humanize.naturalsize(disk_parameters.disk0.available), fill=COLOR_GRAY, font=FONT_LABEL)
            if disk_parameters.disk0.capacity == 0:
                draw.rectangle((186, 110, 273, 113), fill=0x000000)
            else:
                draw.rectangle((186, 110, 186 + (disk0_pct * 87 / 100), 113), fill=COLOR_PURPLE)

            # Disk 1
            disk1_pct = min(disk_parameters.disk1.used_percentage, 100)
            draw.text((240, 114), humanize.naturalsize(disk_parameters.disk1.available), fill=COLOR_GRAY, font=FONT_LABEL)
            if disk_parameters.disk1.capacity == 0:
                draw.rectangle((186, 131, 273, 134), fill=0x000000)
            else:
                draw.rectangle((186, 131, 186 + (disk1_pct * 87 / 100), 134), fill=COLOR_PURPLE)

            # RAID indicator
            if disk_parameters.raid:
                draw.text((160, 78), 'RAID', fill=COLOR_GRAY, font=FONT_LABEL)

            # Disk warning messages
            if has_disk_warning(disk_parameters.disk0.capacity, disk_parameters.disk1.capacity):
                if self.system_parameters.flag > 0:
                    draw.text((155, 135), 'Detected but not installed', fill=COLOR_GRAY, font=font02_14)
                else:
                    draw.text((190, 135), 'Unpartitioned/NC', fill=COLOR_GRAY, font=font02_14)

        # Error indicator
        if self._has_error:
            draw.ellipse((300, 5, 315, 20), fill=0xff0000)

        # Turbo mode indicator
        if self.fan_mode == FanMode.TURBO:
            draw.text((255, 5), 'TURBO', fill=COLOR_CYAN, font=font02_13)

        image = image.rotate(180)
        self.disp.ShowImage(image)
