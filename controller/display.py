import logging
import os
import threading
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

import RPi.GPIO as GPIO

from fan_controller import FanController, FanMode
from hmi import Hmi1Renderer, Hmi2Renderer
from lib.LCD_2inch import LCD_2inch
from lib.monitoring import SystemParameters


# =============================================================================
# Enums
# =============================================================================

class DisplayMode(Enum):
    """Display mode for HMI screens."""
    DEVICE_STATUS = auto()  # General device status with circular gauges
    STORAGE_FOCUS = auto()  # Storage-focused view with disk details


# =============================================================================
# Constants
# =============================================================================

USER_BUTTON_PIN = 20

# Button timing (in 0.1s increments, so 5 = 0.5s, 20 = 2s)
DISPLAY_MODE_TOGGLE_THRESHOLD = 5   # 0.5 seconds hold
FAN_MODE_TOGGLE_THRESHOLD = 20      # 2.0 seconds hold

REFRESH_INTERVAL = float(os.environ.get('NAS_REFRESH_INTERVAL', '0.5'))

# Change detection thresholds for skip-render optimization
CHANGE_THRESHOLD_PERCENT = 1.0  # Skip render if values changed less than this
CHANGE_THRESHOLD_TEMP = 0.5     # Temperature change threshold

# Display brightness (0-100, configurable via environment variables)
BRIGHTNESS_DEFAULT = int(os.environ.get('NAS_BRIGHTNESS_DEFAULT', '100'))
BRIGHTNESS_DIM = int(os.environ.get('NAS_BRIGHTNESS_DIM', '30'))
AUTO_DIM_TIMEOUT = int(os.environ.get('NAS_AUTO_DIM_TIMEOUT', '300'))  # seconds


# =============================================================================
# RenderCache
# =============================================================================

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

    _PERCENT_FIELDS = ('cpu_usage', 'memory_usage', 'disk_percent', 'disk0_percent', 'disk1_percent')
    _TEMP_FIELDS = ('cpu_temperature',)
    _SPEED_FIELDS = ('rx_speed', 'tx_speed')

    def has_significant_change(self, new: 'RenderCache') -> bool:
        """Check if any value has changed significantly enough to warrant a re-render."""
        if new.display_mode != self.display_mode:
            return True
        if new.fan_mode != self.fan_mode:
            return True
        if new.last_minute != self.last_minute:
            return True
        if new.ip_address != self.ip_address:
            return True
        if any(abs(getattr(new, f) - getattr(self, f)) >= CHANGE_THRESHOLD_PERCENT
               for f in self._PERCENT_FIELDS):
            return True
        if any(abs(getattr(new, f) - getattr(self, f)) >= CHANGE_THRESHOLD_TEMP
               for f in self._TEMP_FIELDS):
            return True
        for attr in self._SPEED_FIELDS:
            prev, curr = getattr(self, attr), getattr(new, attr)
            if prev > 0 and abs(curr - prev) / max(prev, 1) > 0.1:
                return True
            if (curr > 100) != (prev > 100):
                return True
        return False

    def update(self, new: 'RenderCache') -> None:
        """Update the cache with values from a new RenderCache snapshot."""
        for f in ('cpu_usage', 'memory_usage', 'disk_percent', 'cpu_temperature',
                  'rx_speed', 'tx_speed', 'disk0_percent', 'disk1_percent',
                  'ip_address', 'display_mode', 'fan_mode', 'last_minute'):
            setattr(self, f, getattr(new, f))


# =============================================================================
# Display
# =============================================================================

class Display:
    """
    Orchestrator for the Waveshare CM4 Double-Deck NAS display system.

    Manages the LCD display, button input, and auto-dimming. Fan control and
    HMI rendering are delegated to FanController and Hmi*Renderer respectively.
    """

    def __init__(self) -> None:
        self.display_mode: DisplayMode = DisplayMode.DEVICE_STATUS
        self._last_activity_time: float = time.time()
        self._brightness: int = BRIGHTNESS_DEFAULT
        self._has_error: bool = False
        self._successful_renders: int = 0
        self._render_cache: RenderCache = RenderCache()
        self._force_render: bool = True

        self.system_parameters = SystemParameters()

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(USER_BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        self.disp = LCD_2inch()
        self.disp.Init()
        self.disp.clear()

        self._fan = FanController(self.disp, self.system_parameters, on_error=self._on_hardware_error)
        self._hmi1 = Hmi1Renderer()
        self._hmi2 = Hmi2Renderer()

        t1 = threading.Thread(target=self.system_parameters.update, name="thread1")
        t2 = threading.Thread(target=self.key, name="thread2")
        t3 = threading.Thread(target=self._fan.control, name="thread3")
        for t in (t1, t2, t3):
            t.daemon = True
            t.start()

    def key(self) -> None:
        """
        Handle USER button input for mode switching using edge detection.

        - Hold for 0.5 seconds: Toggle display mode (Device Status / Storage Focus)
        - Hold for 2.0 seconds: Toggle fan mode (Default / Turbo)
        """
        while True:
            GPIO.wait_for_edge(USER_BUTTON_PIN, GPIO.FALLING, timeout=1000)

            if GPIO.input(USER_BUTTON_PIN) == 0:
                press_start = time.time()
                while GPIO.input(USER_BUTTON_PIN) == 0:
                    time.sleep(0.05)

                hold_duration = time.time() - press_start
                logging.debug(f'Button held for {hold_duration:.2f}s')
                counter = int(hold_duration * 10)

                if counter > FAN_MODE_TOGGLE_THRESHOLD:
                    if self._fan.fan_mode == FanMode.DEFAULT:
                        logging.info('Fan mode: turbo')
                        self._fan.fan_mode = FanMode.TURBO
                    else:
                        logging.info('Fan mode: default')
                        self._fan.fan_mode = FanMode.DEFAULT
                    self._reset_activity()
                elif counter > DISPLAY_MODE_TOGGLE_THRESHOLD:
                    if self.display_mode == DisplayMode.DEVICE_STATUS:
                        logging.info('HMI display mode: Storage Focus')
                        self.display_mode = DisplayMode.STORAGE_FOCUS
                    else:
                        logging.info('HMI display mode: Device Status')
                        self.display_mode = DisplayMode.DEVICE_STATUS
                    self._reset_activity()

    def _on_hardware_error(self) -> None:
        """Called by background threads to surface hardware errors to the display."""
        self._has_error = True
        self._successful_renders = 0

    def _reset_activity(self) -> None:
        """Reset the activity timer and restore full brightness."""
        self._last_activity_time = time.time()
        if self._brightness != BRIGHTNESS_DEFAULT:
            self._set_brightness(BRIGHTNESS_DEFAULT)

    def _set_brightness(self, brightness: int) -> None:
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
        """Main render loop — infinite loop with error handling and sleep."""
        while True:
            try:
                self._tick()
                time.sleep(REFRESH_INTERVAL)
            except IOError as e:
                logging.warning(e)
                self._on_hardware_error()
            except KeyboardInterrupt:
                self.disp.module_exit()
                logging.info("quit:")
                exit()

    def _tick(self) -> None:
        """Single render cycle: auto-dim, change detection, conditional HMI dispatch."""
        self._update_auto_dim()

        now = time.localtime()
        if now.tm_sec == 0 and self._render_cache.last_minute != now.tm_min:
            self._force_render = True

        snapshot = self.system_parameters.get_snapshot()
        fan_mode = self._fan.fan_mode  # single lock acquire for the whole tick
        new_cache = self._build_cache(snapshot, now.tm_min, fan_mode)

        if self._force_render or self._render_cache.has_significant_change(new_cache):
            self._force_render = False
            self._render_cache.update(new_cache)
            self._dispatch_render(snapshot, fan_mode, now)
            self._track_render_success()

    def _build_cache(self, snapshot: dict, current_minute: int, fan_mode: 'FanMode') -> RenderCache:
        """Build a RenderCache from a system snapshot for change detection."""
        disk_params = snapshot['disk_parameters']
        disk_usage = snapshot['disk_usage']
        return RenderCache(
            cpu_usage=snapshot['cpu_usage'],
            memory_usage=snapshot['memory_usage'],
            disk_percent=disk_usage.percent if disk_usage else 0.0,
            cpu_temperature=snapshot['cpu_temperature'],
            rx_speed=snapshot['rx_speed'],
            tx_speed=snapshot['tx_speed'],
            disk0_percent=disk_params.disk0_used_percentage if disk_params else 0.0,
            disk1_percent=disk_params.disk1_used_percentage if disk_params else 0.0,
            ip_address=snapshot['ip_address'],
            display_mode=self.display_mode,
            fan_mode=fan_mode,
            last_minute=current_minute,
        )

    def _dispatch_render(self, snapshot: dict, fan_mode: 'FanMode', now: time.struct_time) -> None:
        """Dispatch to the correct HMI renderer based on current display mode."""
        if self.display_mode == DisplayMode.DEVICE_STATUS:
            image = self._hmi1.render(snapshot, self._has_error, fan_mode, now)
        else:
            image = self._hmi2.render(snapshot, self._has_error, fan_mode, now)
        self.disp.ShowImage(image)

    def _track_render_success(self) -> None:
        """Increment successful render counter; clear error indicator after 10 consecutive."""
        self._successful_renders += 1
        if self._has_error and self._successful_renders >= 10:
            logging.info('Clearing error indicator after successful renders')
            self._has_error = False
            self._successful_renders = 0
