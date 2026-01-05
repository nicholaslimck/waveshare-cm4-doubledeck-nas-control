import time
from typing import Any, Optional

from .lcdconfig import RaspberryPi


# =============================================================================
# ST7789 Display Commands
# =============================================================================

CMD_SLPOUT = 0x11       # Sleep Out
CMD_INVON = 0x21        # Display Inversion On
CMD_DISPON = 0x29       # Display On
CMD_CASET = 0x2A        # Column Address Set
CMD_RASET = 0x2B        # Row Address Set
CMD_RAMWR = 0x2C        # Memory Write
CMD_MADCTL = 0x36       # Memory Access Control
CMD_COLMOD = 0x3A       # Interface Pixel Format
CMD_PORCTRL = 0xB2      # Porch Setting
CMD_GCTRL = 0xB7        # Gate Control
CMD_VCOMS = 0xBB        # VCOM Setting
CMD_LCMCTRL = 0xC0      # LCM Control
CMD_VDVVRHEN = 0xC2     # VDV and VRH Enable
CMD_VRHS = 0xC3         # VRH Set
CMD_VDVS = 0xC4         # VDV Set
CMD_FRCTRL2 = 0xC6      # Frame Rate Control 2
CMD_PWCTRL1 = 0xD0      # Power Control 1
CMD_PVGAMCTRL = 0xE0    # Positive Voltage Gamma
CMD_NVGAMCTRL = 0xE1    # Negative Voltage Gamma

# Memory Access Control flags
MADCTL_LANDSCAPE = 0x70  # Landscape orientation
MADCTL_PORTRAIT = 0x00   # Portrait orientation

# Pixel format
COLMOD_RGB565 = 0x05     # 16-bit RGB565


class LCD_2inch(RaspberryPi):
    """Driver for 2-inch 240x320 ST7789 LCD display."""

    width = 240
    height = 320

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-allocate pixel buffers to avoid allocation per frame
        self._pix_buffer_landscape = self.np.zeros((self.width, self.height, 2), dtype=self.np.uint8)
        self._pix_buffer_portrait: Optional[Any] = None  # numpy.ndarray
        self._clear_buffer: Optional[bytes] = None

    def command(self, cmd: int) -> None:
        """Send a command byte to the display."""
        self.digital_write(self.DC_PIN, self.GPIO.LOW)
        self.spi_writebyte([cmd])

    def data(self, val: int) -> None:
        """Send a data byte to the display."""
        self.digital_write(self.DC_PIN, self.GPIO.HIGH)
        self.spi_writebyte([val])

    def reset(self) -> None:
        """Reset the display."""
        self.GPIO.output(self.RST_PIN, self.GPIO.HIGH)
        time.sleep(0.01)
        self.GPIO.output(self.RST_PIN, self.GPIO.LOW)
        time.sleep(0.01)
        self.GPIO.output(self.RST_PIN, self.GPIO.HIGH)
        time.sleep(0.01)

    def Init(self) -> None:
        """Initialize display with ST7789 configuration."""
        self.module_init()
        self.reset()

        # Memory Access Control
        self.command(CMD_MADCTL)
        self.data(MADCTL_PORTRAIT)

        # Pixel format: RGB565
        self.command(CMD_COLMOD)
        self.data(COLMOD_RGB565)

        # Display Inversion On
        self.command(CMD_INVON)

        # Column Address Set (0-319)
        self.command(CMD_CASET)
        self.data(0x00)
        self.data(0x00)
        self.data(0x01)
        self.data(0x3F)

        # Row Address Set (0-239)
        self.command(CMD_RASET)
        self.data(0x00)
        self.data(0x00)
        self.data(0x00)
        self.data(0xEF)

        # Porch Setting
        self.command(CMD_PORCTRL)
        self.data(0x0C)
        self.data(0x0C)
        self.data(0x00)
        self.data(0x33)
        self.data(0x33)

        # Gate Control
        self.command(CMD_GCTRL)
        self.data(0x35)

        # VCOM Setting
        self.command(CMD_VCOMS)
        self.data(0x1F)

        # LCM Control
        self.command(CMD_LCMCTRL)
        self.data(0x2C)

        # VDV and VRH Enable
        self.command(CMD_VDVVRHEN)
        self.data(0x01)

        # VRH Set
        self.command(CMD_VRHS)
        self.data(0x12)

        # VDV Set
        self.command(CMD_VDVS)
        self.data(0x20)

        # Frame Rate Control
        self.command(CMD_FRCTRL2)
        self.data(0x0F)

        # Power Control 1
        self.command(CMD_PWCTRL1)
        self.data(0xA4)
        self.data(0xA1)

        # Positive Voltage Gamma
        self.command(CMD_PVGAMCTRL)
        self.data(0xD0)
        self.data(0x08)
        self.data(0x11)
        self.data(0x08)
        self.data(0x0C)
        self.data(0x15)
        self.data(0x39)
        self.data(0x33)
        self.data(0x50)
        self.data(0x36)
        self.data(0x13)
        self.data(0x14)
        self.data(0x29)
        self.data(0x2D)

        # Negative Voltage Gamma
        self.command(CMD_NVGAMCTRL)
        self.data(0xD0)
        self.data(0x08)
        self.data(0x10)
        self.data(0x08)
        self.data(0x06)
        self.data(0x06)
        self.data(0x39)
        self.data(0x44)
        self.data(0x51)
        self.data(0x0B)
        self.data(0x16)
        self.data(0x14)
        self.data(0x2F)
        self.data(0x31)

        # Display Inversion On (again for gamma)
        self.command(CMD_INVON)

        # Sleep Out
        self.command(CMD_SLPOUT)

        # Display On
        self.command(CMD_DISPON)

    def SetWindows(self, Xstart: int, Ystart: int, Xend: int, Yend: int) -> None:
        """
        Set the display window for subsequent pixel writes.

        Args:
            Xstart: Starting X coordinate.
            Ystart: Starting Y coordinate.
            Xend: Ending X coordinate.
            Yend: Ending Y coordinate.
        """
        # Set X coordinates
        self.command(CMD_CASET)
        self.data(Xstart >> 8)
        self.data(Xstart & 0xff)
        self.data(Xend >> 8)
        self.data((Xend - 1) & 0xff)

        # Set Y coordinates
        self.command(CMD_RASET)
        self.data(Ystart >> 8)
        self.data(Ystart & 0xff)
        self.data(Yend >> 8)
        self.data((Yend - 1) & 0xff)

        # Memory Write command
        self.command(CMD_RAMWR)

    def _convert_rgb888_to_rgb565(self, img, buffer) -> None:
        """
        Convert RGB888 image to RGB565 format in-place.

        Args:
            img: NumPy array of RGB888 image data.
            buffer: Pre-allocated buffer to store RGB565 data.
        """
        buffer[..., 0] = self.np.add(
            self.np.bitwise_and(img[..., 0], 0xF8),
            self.np.right_shift(img[..., 1], 5)
        )
        buffer[..., 1] = self.np.add(
            self.np.bitwise_and(self.np.left_shift(img[..., 1], 3), 0xE0),
            self.np.right_shift(img[..., 2], 3)
        )

    def ShowImage(self, image: Any, Xstart: int = 0, Ystart: int = 0) -> None:
        """
        Display a PIL Image on the LCD.

        Optimized to use pre-allocated buffers and tobytes() for efficiency.

        Args:
            image: PIL Image to display.
            Xstart: Starting X coordinate (unused, for API compatibility).
            Ystart: Starting Y coordinate (unused, for API compatibility).
        """
        imwidth, imheight = image.size

        if imwidth == self.height and imheight == self.width:
            # Landscape mode (320x240)
            img = self.np.asarray(image)
            self._convert_rgb888_to_rgb565(img, self._pix_buffer_landscape)
            pix_bytes = self._pix_buffer_landscape.tobytes()

            self.command(CMD_MADCTL)
            self.data(MADCTL_LANDSCAPE)
            self.SetWindows(0, 0, self.height, self.width)
            self.digital_write(self.DC_PIN, self.GPIO.HIGH)
            for i in range(0, len(pix_bytes), 4096):
                self.spi_writebyte(pix_bytes[i:i + 4096])

        else:
            # Portrait mode or non-standard size
            img = self.np.asarray(image)

            # Allocate buffer on demand for non-standard sizes
            if self._pix_buffer_portrait is None or self._pix_buffer_portrait.shape[:2] != (imheight, imwidth):
                self._pix_buffer_portrait = self.np.zeros((imheight, imwidth, 2), dtype=self.np.uint8)

            self._convert_rgb888_to_rgb565(img, self._pix_buffer_portrait)
            if self._pix_buffer_portrait is not None:
                pix_bytes = self._pix_buffer_portrait.tobytes()
            else:
                pix_bytes = b''  # Fallback, should not happen

            self.command(CMD_MADCTL)
            self.data(MADCTL_PORTRAIT)
            self.SetWindows(0, 0, self.width, self.height)
            self.digital_write(self.DC_PIN, self.GPIO.HIGH)
            for i in range(0, len(pix_bytes), 4096):
                self.spi_writebyte(pix_bytes[i:i + 4096])

    def clear(self) -> None:
        """Clear the display to white."""
        # Pre-allocate buffer once for efficiency
        if self._clear_buffer is None:
            self._clear_buffer = bytes([0xff] * (self.width * self.height * 2))

        self.SetWindows(0, 0, self.width, self.height)
        self.digital_write(self.DC_PIN, self.GPIO.HIGH)
        for i in range(0, len(self._clear_buffer), 4096):
            self.spi_writebyte(self._clear_buffer[i:i + 4096])
