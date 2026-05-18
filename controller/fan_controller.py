import logging
import math
import threading
import time
from enum import Enum, auto
from typing import Callable, Optional


class FanMode(Enum):
    """Fan control mode."""
    DEFAULT = auto()  # 0-50% speed, 65-85°C range
    TURBO = auto()    # 0-100% speed, 50-85°C range


# Fan control parameters
FAN_MIN_DUTY_CYCLE = 35  # Minimum duty cycle to prevent motor stall
FAN_CONTROL_INTERVAL = 5  # seconds
FAN_HYSTERESIS = 3  # Temperature change threshold to trigger fan speed adjustment

# Fan curve zones: list of (temp_threshold, fan_speed_percent)
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
            prev_threshold, prev_speed = curve[i - 1]
            ratio = (temp - prev_threshold) / (threshold - prev_threshold)
            return int(prev_speed + ratio * (speed - prev_speed))
    return curve[-1][1]


def get_weighted_temp(cpu: float, disk0: float, disk1: float) -> float:
    """
    Calculate weighted reference temperature, filtering invalid sensors.

    CPU is weighted higher (60%) since it responds faster to load changes.
    Disk temps (20% each) are included only if valid (> 0).
    """
    temps = [(cpu, 0.6)]
    if disk0 > 0:
        temps.append((disk0, 0.2))
    if disk1 > 0:
        temps.append((disk1, 0.2))
    total_weight = sum(w for _, w in temps)
    return sum(t * w / total_weight for t, w in temps)


class FanController:
    """PWM fan controller with temperature-based speed curves and ramp limiting."""

    def __init__(
        self,
        disp,
        system_parameters,
        on_error: Optional[Callable[[], None]] = None,
    ) -> None:
        self._fan_mode: FanMode = FanMode.DEFAULT
        self._fan_mode_lock: threading.Lock = threading.Lock()
        self._disp = disp
        self._system_parameters = system_parameters
        self._on_error = on_error
        self._last_fan_temp: float = 0.0
        self._current_fan_speed: int = 0

    @property
    def fan_mode(self) -> FanMode:
        with self._fan_mode_lock:
            return self._fan_mode

    @fan_mode.setter
    def fan_mode(self, value: FanMode) -> None:
        with self._fan_mode_lock:
            self._fan_mode = value

    def set_speed(self, speed: int) -> None:
        """Set fan PWM speed (0-100). Values > 0 are scaled above FAN_MIN_DUTY_CYCLE."""
        if speed:
            duty_cycle = math.floor(
                speed * ((100 - FAN_MIN_DUTY_CYCLE) / 100) + FAN_MIN_DUTY_CYCLE
            )
        else:
            duty_cycle = 0
        if self._disp._fan_pwm is not None:
            self._disp._fan_pwm.ChangeDutyCycle(duty_cycle)

    def control(self) -> None:
        """Fan control daemon thread: weighted temp → curve lookup → ramp-limited PWM."""
        while True:
            try:
                snapshot = self._system_parameters.get_snapshot()
                cpu_temp = snapshot['cpu_temperature']
                disk_params = snapshot['disk_parameters']
                disk0_temp = disk_params.disk0_temperature if disk_params else 0
                disk1_temp = disk_params.disk1_temperature if disk_params else 0

                ref_temp = get_weighted_temp(cpu_temp, disk0_temp, disk1_temp)

                if abs(ref_temp - self._last_fan_temp) >= FAN_HYSTERESIS:
                    self._last_fan_temp = ref_temp
                    curve = FAN_CURVES[self.fan_mode]
                    target_speed = get_fan_speed_for_temp(ref_temp, curve)

                    delta = target_speed - self._current_fan_speed
                    if abs(delta) > MAX_SPEED_CHANGE:
                        target_speed = self._current_fan_speed + MAX_SPEED_CHANGE * (1 if delta > 0 else -1)

                    self._current_fan_speed = target_speed
                    self.set_speed(target_speed)

            except Exception as e:
                logging.warning(f"Fan control error: {e}")
                if self._on_error:
                    self._on_error()

            time.sleep(FAN_CONTROL_INTERVAL)
