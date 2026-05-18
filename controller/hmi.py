import logging
import math
import os
import time
from typing import Tuple

import humanize
from PIL import Image, ImageDraw, ImageFont

from fan_controller import FanMode


# =============================================================================
# Colors (RGB hex values)
# =============================================================================

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

# Disk warning messages
WARN_DETECTED_NOT_INSTALLED = 'Detected but not installed'
WARN_UNPARTITIONED = 'Unpartitioned/NC'

DATETIME_FORMAT = "%Y-%m-%d   %H:%M:%S"

# Image paths
HMI1_IMAGE_PATH = 'pic/BL.jpg'
HMI2_IMAGE_PATH = 'pic/Disk.jpg'


# =============================================================================
# Fonts
# =============================================================================

def _load_fonts() -> dict:
    try:
        return {
            'font02_10': ImageFont.truetype("./Font/Font02.ttf", 10),
            'font02_13': ImageFont.truetype("./Font/Font02.ttf", 13),
            'font02_14': ImageFont.truetype("./Font/Font02.ttf", 14),
            'font02_15': ImageFont.truetype("./Font/Font02.ttf", 15),
            'font02_17': ImageFont.truetype("./Font/Font02.ttf", 17),
            'font02_18': ImageFont.truetype("./Font/Font02.ttf", 18),
            'font02_20': ImageFont.truetype("./Font/Font02.ttf", 20),
            'font02_28': ImageFont.truetype("./Font/Font02.ttf", 28),
        }
    except OSError as e:
        logging.critical(f"Font file missing: {e}")
        raise

_fonts = _load_fonts()
font02_10 = _fonts['font02_10']
font02_13 = _fonts['font02_13']
font02_14 = _fonts['font02_14']
font02_15 = _fonts['font02_15']
font02_17 = _fonts['font02_17']
font02_18 = _fonts['font02_18']
font02_20 = _fonts['font02_20']
font02_28 = _fonts['font02_28']
del _fonts

FONT_TITLE = font02_28
FONT_HEADING = font02_20
FONT_LABEL = font02_15
FONT_VALUE = font02_17
FONT_VALUE_LARGE = font02_18
FONT_SMALL = font02_13
FONT_TINY = font02_10


# =============================================================================
# Helper functions
# =============================================================================

def calculate_arc_angle(percent: float, max_percent: float = 100.0) -> float:
    """Convert percentage to arc end angle (-90 = top of circle)."""
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
    font: ImageFont.FreeTypeFont = font02_13,
) -> None:
    """Draw a disk usage bar with border, fill, and optional percentage text."""
    draw.rectangle((x, y, x + width, y + height))
    if capacity == 0:
        draw.rectangle((x + 1, y + 1, x + width - 1, y + height - 1), fill=0x000000)
    else:
        clamped_percent = min(used_percentage, 100)
        fill_width = clamped_percent * (width - 2) / 100
        draw.rectangle((x + 1, y + 1, x + 1 + fill_width, y + height - 1), fill=fill_color)
        if show_percentage:
            text_x = x + width // 2 - 11
            draw.text((text_x, y - 1), f'{int(used_percentage)}%', fill=text_color, font=font)


def format_speed(speed: float) -> Tuple[str, int]:
    """Format network speed with unit and color."""
    if speed < 1024:
        return f"{math.floor(speed)}B/s", COLOR_GRAY
    elif speed < 1024 * 1024:
        return f"{math.floor(speed / 1024)}KB/s", COLOR_CYAN
    else:
        return f"{math.floor(speed / 1024 / 1024)}MB/s", COLOR_LIGHT_GREEN


def draw_centered_percentage(
    draw: ImageDraw.ImageDraw,
    value: float,
    center_x: int,
    y: int,
    font: ImageFont.FreeTypeFont,
    color: int,
) -> None:
    """Draw percentage text with digit-count-based center alignment."""
    text = f"{math.floor(value)}%"
    if value >= 100:
        offset = -6
    elif value >= 10:
        offset = -3
    else:
        offset = 0
    draw.text((center_x + offset, y), text, fill=color, font=font)


def has_disk_warning(disk0_capacity: int, disk1_capacity: int) -> bool:
    """True if at least one disk has zero capacity."""
    return disk0_capacity == 0 or disk1_capacity == 0


def draw_disk_warning(
    draw: ImageDraw.ImageDraw,
    snapshot: dict,
    x_detected: int,
    x_unpartitioned: int,
    y: int,
    font: ImageFont.FreeTypeFont,
    color: int,
) -> None:
    """Draw disk warning message if any disk is missing."""
    disk_params = snapshot['disk_parameters']
    if disk_params is None:
        return
    if not has_disk_warning(disk_params.disk0_capacity, disk_params.disk1_capacity):
        return
    if snapshot['flag'] > 0:
        draw.text((x_detected, y), WARN_DETECTED_NOT_INSTALLED, fill=color, font=font)
    else:
        draw.text((x_unpartitioned, y), WARN_UNPARTITIONED, fill=color, font=font)


def draw_error_indicator(draw: ImageDraw.ImageDraw, has_error: bool, x: int, y: int) -> None:
    """Draw red error circle with '!' if has_error is True."""
    if has_error:
        draw.ellipse((x, y, x + 23, y + 23), fill=0xff0000)
        draw.text((x + 6, y + 2), '!', fill=COLOR_WHITE, font=FONT_VALUE)


def draw_turbo_indicator(draw: ImageDraw.ImageDraw, fan_mode: FanMode, x: int, y: int) -> None:
    """Draw TURBO label if fan is in turbo mode."""
    if fan_mode == FanMode.TURBO:
        draw.text((x, y), 'TURBO', fill=COLOR_CYAN, font=font02_13)


# =============================================================================
# HMI Renderers
# =============================================================================

class Hmi1Renderer:
    """Renders the Device Status screen (circular gauge view)."""

    def __init__(self) -> None:
        self._base: Image.Image = self._init_base()

    def _init_base(self) -> Image.Image:
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
        draw.arc(HMI1_CPU_ARC, 0, 360, fill=COLOR_WHITE, width=8)
        draw.arc(HMI1_DISK_ARC, 0, 360, fill=COLOR_WHITE, width=8)
        draw.arc(HMI1_RAM_ARC, 0, 360, fill=COLOR_WHITE, width=8)
        draw.arc(HMI1_TEMP_ARC, 0, 360, fill=COLOR_WHITE, width=8)
        return image

    def render(self, snapshot: dict, has_error: bool, fan_mode: FanMode) -> Image.Image:
        """Render Device Status screen and return the composed image."""
        image = self._base.copy()
        draw = ImageDraw.Draw(image)

        time_t = time.strftime(DATETIME_FORMAT, time.localtime())
        draw.text((5, 50), time_t, fill=COLOR_GOLD, font=font02_15)
        draw.text((170, 50), f'IP : {snapshot["ip_address"]}', fill=COLOR_GOLD, font=font02_15)

        cpu_usage = snapshot['cpu_usage']
        draw_centered_percentage(draw, cpu_usage, 34, 100, FONT_LABEL, COLOR_YELLOW)
        draw.arc(HMI1_CPU_ARC, -90, calculate_arc_angle(cpu_usage), fill=COLOR_GREEN, width=8)

        disk_usage = snapshot['disk_usage']
        disk_percent = disk_usage.percent if disk_usage else 0.0
        draw_centered_percentage(draw, disk_percent, 114, 100, FONT_LABEL, COLOR_YELLOW)
        draw.arc(HMI1_DISK_ARC, -90, calculate_arc_angle(disk_percent), fill=COLOR_PURPLE, width=8)

        memory_usage = snapshot['memory_usage']
        draw_centered_percentage(draw, memory_usage, 192, 100, FONT_VALUE_LARGE, COLOR_YELLOW)
        draw.arc(HMI1_RAM_ARC, -90, calculate_arc_angle(memory_usage), fill=COLOR_YELLOW, width=8)

        temp_t = snapshot['cpu_temperature']
        draw.text((268, 100), f'{math.floor(temp_t)}℃', fill=COLOR_BLUE, font=FONT_VALUE_LARGE)
        draw.arc(HMI1_TEMP_ARC, -90, calculate_arc_angle(temp_t), fill=COLOR_BLUE, width=8)

        tx_text, tx_color = format_speed(snapshot['tx_speed'])
        rx_text, rx_color = format_speed(snapshot['rx_speed'])
        draw.text((250, 190), tx_text, fill=tx_color, font=font02_17)
        draw.text((183, 190), rx_text, fill=rx_color, font=font02_17)

        disk_parameters = snapshot['disk_parameters']
        if disk_parameters is not None:
            draw_disk_bar(draw, 40, 177, 102, 13,
                          disk_parameters.disk0_used_percentage, disk_parameters.disk0_capacity,
                          font=FONT_SMALL)
            draw_disk_bar(draw, 40, 197, 102, 13,
                          disk_parameters.disk1_used_percentage, disk_parameters.disk1_capacity,
                          font=FONT_SMALL)
            if disk_parameters.raid:
                draw.text((40, 161), 'RAID', fill=COLOR_GOLD, font=FONT_LABEL)
            draw_disk_warning(draw, snapshot, 30, 50, 210, FONT_LABEL, COLOR_GOLD)

        draw_error_indicator(draw, has_error, 295, 32)
        draw_turbo_indicator(draw, fan_mode, 255, 35)

        return image.transpose(Image.Transpose.ROTATE_180)


class Hmi2Renderer:
    """Renders the Storage Focus screen (disk detail view)."""

    def __init__(self) -> None:
        self._base: Image.Image = self._init_base()

    def _init_base(self) -> Image.Image:
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
        return image

    def render(self, snapshot: dict, has_error: bool, fan_mode: FanMode) -> Image.Image:
        """Render Storage Focus screen and return the composed image."""
        image = self._base.copy()
        draw = ImageDraw.Draw(image)

        time_t = time.strftime(DATETIME_FORMAT, time.localtime())
        draw.text((40, 10), time_t, fill=COLOR_WHITE, font=font02_15)
        draw.text((155, 58), f'IP : {snapshot["ip_address"]}', fill=COLOR_GRAY, font=font02_17)

        cpu_usage = snapshot['cpu_usage']
        draw_centered_percentage(draw, cpu_usage, 84, 105, FONT_SMALL, COLOR_YELLOW)
        draw.arc(HMI2_CPU_ARC, -90, calculate_arc_angle(cpu_usage), fill=COLOR_PURPLE, width=3)

        disk_usage = snapshot['disk_usage']
        if disk_usage is not None:
            disk_used = humanize.naturalsize(disk_usage.used)
            disk_free = humanize.naturalsize(disk_usage.free)
            draw.text((85, 140), disk_used, fill=COLOR_GRAY, font=FONT_SMALL)
            draw.text((85, 163), disk_free, fill=COLOR_GRAY, font=FONT_SMALL)
            if disk_usage.total > 0:
                draw.rectangle((45, 157, 45 + ((disk_usage.used / disk_usage.total) * 87), 160), fill=COLOR_PURPLE)
                draw.rectangle((45, 180, 45 + ((disk_usage.free / disk_usage.total) * 87), 183), fill=COLOR_PURPLE)

        temp_t = snapshot['cpu_temperature']
        draw.text((170, 205), f'{math.floor(temp_t)}℃', fill=COLOR_BLUE, font=FONT_LABEL)

        tx_text, tx_color = format_speed(snapshot['tx_speed'])
        rx_text, rx_color = format_speed(snapshot['rx_speed'])
        draw.text((210, 154), tx_text, fill=tx_color, font=font02_15)
        draw.text((210, 174), rx_text, fill=rx_color, font=font02_15)

        disk_parameters = snapshot['disk_parameters']
        if disk_parameters is not None:
            disk0_pct = min(disk_parameters.disk0_used_percentage, 100)
            draw.text((240, 93), humanize.naturalsize(disk_parameters.disk0_available), fill=COLOR_GRAY, font=FONT_LABEL)
            if disk_parameters.disk0_capacity == 0:
                draw.rectangle((186, 110, 273, 113), fill=0x000000)
            else:
                draw.rectangle((186, 110, 186 + (disk0_pct * 87 / 100), 113), fill=COLOR_PURPLE)

            disk1_pct = min(disk_parameters.disk1_used_percentage, 100)
            draw.text((240, 114), humanize.naturalsize(disk_parameters.disk1_available), fill=COLOR_GRAY, font=FONT_LABEL)
            if disk_parameters.disk1_capacity == 0:
                draw.rectangle((186, 131, 273, 134), fill=0x000000)
            else:
                draw.rectangle((186, 131, 186 + (disk1_pct * 87 / 100), 134), fill=COLOR_PURPLE)

            if disk_parameters.raid:
                draw.text((160, 78), 'RAID', fill=COLOR_GRAY, font=FONT_LABEL)
            draw_disk_warning(draw, snapshot, 155, 190, 135, font02_14, COLOR_GRAY)

        draw_error_indicator(draw, has_error, 295, 2)
        draw_turbo_indicator(draw, fan_mode, 255, 5)

        return image.transpose(Image.Transpose.ROTATE_180)
