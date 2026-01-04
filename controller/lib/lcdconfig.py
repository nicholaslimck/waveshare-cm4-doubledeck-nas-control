# /*****************************************************************************
# * | File        :   lcdconfig.py
# * | Author      :   Waveshare team, Nicholas Lim
# * | Function    :   Hardware underlying interface
# * | Info        :
# *----------------
# * | This version:   V1.1
# * | Date        :   2026-01-05
# * | Info        :
# ******************************************************************************
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documnetation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to  whom the Software is
# furished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS OR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

import logging
import time
from typing import Any, List, Optional, Union

import numpy as np
import spidev


# Default GPIO pin assignments (BCM numbering)
DEFAULT_RST_PIN = 27
DEFAULT_DC_PIN = 25
DEFAULT_BL_PIN = 18
DEFAULT_FAN_PIN = 19
DEFAULT_SPI_FREQ = 40_000_000
DEFAULT_PWM_FREQ = 1000


class RaspberryPi:
    """Hardware abstraction layer for Raspberry Pi GPIO and SPI communication."""

    def __init__(
        self,
        spi: Optional[spidev.SpiDev] = None,
        spi_freq: int = DEFAULT_SPI_FREQ,
        rst: int = DEFAULT_RST_PIN,
        dc: int = DEFAULT_DC_PIN,
        bl: int = DEFAULT_BL_PIN,
        fan: int = DEFAULT_FAN_PIN,
        bl_freq: int = DEFAULT_PWM_FREQ,
        i2c=None,
        i2c_freq: int = 100000
    ):
        """
        Initialize the Raspberry Pi hardware interface.

        Args:
            spi: SPI device instance (defaults to SpiDev(0, 0)).
            spi_freq: SPI clock frequency in Hz.
            rst: GPIO pin for display reset.
            dc: GPIO pin for data/command selection.
            bl: GPIO pin for backlight PWM.
            fan: GPIO pin for fan PWM.
            bl_freq: PWM frequency for backlight and fan.
            i2c: I2C device (unused, for future compatibility).
            i2c_freq: I2C frequency (unused, for future compatibility).
        """
        import RPi.GPIO

        # Create default SPI if not provided
        if spi is None:
            spi = spidev.SpiDev(0, 0)

        self.np = np
        self.RST_PIN = rst
        self.DC_PIN = dc
        self.BL_PIN = bl
        self.FAN_PIN = fan
        self.SPEED = spi_freq
        self.BL_freq = bl_freq
        self.GPIO = RPi.GPIO

        self.GPIO.setmode(self.GPIO.BCM)
        self.GPIO.setwarnings(False)
        self.GPIO.setup(self.RST_PIN, self.GPIO.OUT)
        self.GPIO.setup(self.DC_PIN, self.GPIO.OUT)
        self.GPIO.setup(self.BL_PIN, self.GPIO.OUT)
        self.GPIO.output(self.BL_PIN, self.GPIO.HIGH)

        # Initialize SPI
        self.SPI = spi
        if self.SPI is not None:
            self.SPI.max_speed_hz = spi_freq
            self.SPI.mode = 0b00

        # PWM controllers (initialized in module_init)
        # Type is RPi.GPIO.PWM but we use Any to avoid import issues
        self._bl_pwm: Optional[Any] = None
        self._fan_pwm: Optional[Any] = None

    def digital_write(self, pin: int, value: int) -> None:
        """
        Write a digital value to a GPIO pin.

        Args:
            pin: GPIO pin number (BCM).
            value: Value to write (GPIO.HIGH or GPIO.LOW).
        """
        self.GPIO.output(pin, value)

    def digital_read(self, pin: int) -> int:
        """
        Read a digital value from a GPIO pin.

        Args:
            pin: GPIO pin number (BCM).

        Returns:
            Current pin value (GPIO.HIGH or GPIO.LOW).
        """
        return self.GPIO.input(pin)

    def delay_ms(self, delaytime: float) -> None:
        """
        Delay execution for a specified number of milliseconds.

        Args:
            delaytime: Delay duration in milliseconds.
        """
        time.sleep(delaytime / 1000.0)

    def spi_writebyte(self, data: Union[List[int], bytes]) -> None:
        """
        Write bytes to the SPI bus.

        Args:
            data: List of bytes or bytes object to write.
        """
        if self.SPI is not None:
            self.SPI.writebytes(data)

    def bl_DutyCycle(self, duty: int) -> None:
        """
        Set the backlight PWM duty cycle.

        Args:
            duty: Duty cycle percentage (0-100).
        """
        if self._bl_pwm is not None:
            self._bl_pwm.ChangeDutyCycle(duty)

    def bl_Frequency(self, freq: int) -> None:
        """
        Set the backlight PWM frequency.

        Args:
            freq: Frequency in Hz.
        """
        if self._bl_pwm is not None:
            self._bl_pwm.ChangeFrequency(freq)

    def module_init(self) -> int:
        """
        Initialize the display and fan hardware.

        Sets up GPIO pins and starts PWM for backlight and fan.

        Returns:
            0 on success.
        """
        self.GPIO.setup(self.RST_PIN, self.GPIO.OUT)
        self.GPIO.setup(self.DC_PIN, self.GPIO.OUT)
        self.GPIO.setup(self.BL_PIN, self.GPIO.OUT)
        self.GPIO.setup(self.FAN_PIN, self.GPIO.OUT)

        # Initialize backlight PWM at 100% duty cycle
        self._bl_pwm = self.GPIO.PWM(self.BL_PIN, self.BL_freq)
        self._bl_pwm.start(100)

        # Initialize fan PWM at 75% duty cycle
        self._fan_pwm = self.GPIO.PWM(self.FAN_PIN, self.BL_freq)
        self._fan_pwm.start(75)

        if self.SPI is not None:
            self.SPI.max_speed_hz = self.SPEED
            self.SPI.mode = 0b00

        return 0

    def module_exit(self) -> None:
        """Clean up hardware resources on exit."""
        logging.debug("spi end")
        if self.SPI is not None:
            self.SPI.close()

        logging.debug("gpio cleanup...")
        self.GPIO.output(self.RST_PIN, 1)
        self.GPIO.output(self.DC_PIN, 0)

        if self._bl_pwm is not None:
            self._bl_pwm.stop()
        if self._fan_pwm is not None:
            self._fan_pwm.stop()
