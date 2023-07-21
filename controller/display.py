import logging
import math
import os
import re
import threading
import time

import humanize
import RPi.GPIO as GPIO
from PIL import Image, ImageDraw, ImageFont

from lib.monitoring import SystemParameters
from lib.LCD_2inch import LCD_2inch


Font1 = ImageFont.truetype("Font/Font01.ttf", 25)
Font2 = ImageFont.truetype("Font/Font01.ttf", 35)
Font3 = ImageFont.truetype("Font/Font02.ttf", 32)


class Display:
    mode = 1 # Default display mode
    refresh_interval = 0.2

    def __init__(self):
        # display with hardware SPI:
        # Warning: Don't create multiple display objects!
        # disp = LCD_2inch.LCD_2inch(spi=SPI.SpiDev(bus, device),spi_freq=10000000,rst=RST,dc=DC,bl=BL)
        self.parameters = SystemParameters()
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(20, GPIO.IN)
        GPIO.setup(20, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        t1 = threading.Thread(target=self.parameters.update, name="thread1")
        t2 = threading.Thread(target=self.key, name="thread2")
        t1.daemon = True
        t2.daemon = True
        t1.start()
        t2.start()

        self.disp = LCD_2inch()

        # Initialize display
        self.disp.Init()
        # Clear display
        self.disp.clear()

        # Create blank image for drawing.
        blank_canvas = Image.new("RGB", (self.disp.height, self.disp.width), "WHITE")
        self.draw = ImageDraw.Draw(blank_canvas)

    def key(self):
        """
        Change HMI display mode when the USER key is held for 0.5 seconds
        """
        counter = 0
        while True:
            if (GPIO.input(20) == 0):
                counter = counter + 1
            else:
                if (counter > 5):
                    logging.debug('Changing HMI display mode')
                    if self.mode == 1:
                        self.mode = 2
                    else:
                        self.mode = 1
                counter = 0
            time.sleep(0.1)

    def render(self):
        while True:
            try:
                if self.mode == 1:
                    self.HMI1()
                elif self.mode == 2:
                    self.HMI2()
                time.sleep(self.refresh_interval)
            
            except IOError as e:
                logging.warning(e)
            except KeyboardInterrupt:
                self.disp.module_exit()
                logging.info("quit:")
                exit()

    def HMI1(self):
        """
        First HMI screen, showing general device status and metrics such as:
        - Time
        - CPU/System Disk/RAM Usage
        - CPU Temperature
        - Storage Drive Usage
        - Upload/Download Speed
        """
        self.image = Image.open('pic/BL.jpg')

        self.draw = ImageDraw.Draw(self.image)
        Font1 = ImageFont.truetype("./Font/Font02.ttf", 28)
        self.draw.text((90, 2), 'Device Status', fill=0xf7ba47, font=Font1)

        Font1 = ImageFont.truetype("./Font/Font02.ttf", 15)
        self.draw.text((267, 141), 'TEMP', fill=0xf7ba47, font=Font1)
        self.draw.text((190, 141), 'RAM', fill=0xf7ba47, font=Font1)
        self.draw.text((267, 141), 'TEMP', fill=0xf7ba47, font=Font1)
        self.draw.text((30, 141), 'CPU', fill=0xf7ba47, font=Font1)
        self.draw.text((107, 141), 'Disk', fill=0xf7ba47, font=Font1)

        Font1 = ImageFont.truetype("./Font/Font02.ttf", 10)
        self.draw.text((205, 170), 'R X', fill=0xffffff, font=Font1, stroke_width=1)

        Font1 = ImageFont.truetype("./Font/Font02.ttf", 10)
        self.draw.text((270, 170), 'T X', fill=0xffffff, font=Font1, stroke_width=1)

        # TIME
        time_t = time.strftime("%Y-%m-%d   %H:%M:%S", time.localtime())
        Font1 = ImageFont.truetype("./Font/Font02.ttf", 15)
        self.draw.text((5, 50), time_t, fill=0xf7ba47, font=Font1)

        # IP
        ip = self.parameters.ip_address
        Font1 = ImageFont.truetype("./Font/Font02.ttf", 15)
        self.draw.text((170, 50), 'IP : ' + ip, fill=0xf7ba47, font=Font1)

        # CPU usage
        CPU_usage = self.parameters.cpu_usage

        if CPU_usage >= 100:
            self.draw.text((27, 100), str(math.floor(CPU_usage)) + '%', fill=0xf1b400, font=Font1, )
        elif CPU_usage >= 10:
            self.draw.text((30, 100), str(math.floor(CPU_usage)) + '%', fill=0xf1b400, font=Font1, )
        else:
            self.draw.text((34, 100), str(math.floor(CPU_usage)) + '%', fill=0xf1b400, font=Font1, )

        self.draw.arc((10, 80, 70, 142), 0, 360, fill=0xffffff, width=8)
        self.draw.arc((10, 80, 70, 142), -90, -90 + (CPU_usage * 360 / 100), fill=0x60ad4c, width=8)

        # System disk usage
        disk_usage = self.parameters.disk_usage
        if (disk_usage.percent >= 100):
            self.draw.text((107, 100), str(math.floor(disk_usage.percent)) + '%', fill=0xf1b400, font=Font1, )
        elif (disk_usage.percent >= 10):
            self.draw.text((111, 100), str(math.floor(disk_usage.percent)) + '%', fill=0xf1b400, font=Font1, )
        else:
            self.draw.text((114, 100), str(math.floor(disk_usage.percent)) + '%', fill=0xf1b400, font=Font1, )

        self.draw.arc((90, 80, 150, 142), 0, 360, fill=0xffffff, width=8)
        self.draw.arc((90, 80, 150, 142), -90, -90 + (disk_usage.percent * 360 / 100), fill=0x7f35e9, width=8)

        # System Temperature
        temp_t = self.parameters.temperature
        if temp_t < 45:
            self.disp._pwm1.ChangeDutyCycle(20)
        elif temp_t < 50:
            self.disp._pwm1.ChangeDutyCycle(30)
        elif temp_t < 55:
            self.disp._pwm1.ChangeDutyCycle(50)
        else:
            self.disp._pwm1.ChangeDutyCycle(75)
        Font1 = ImageFont.truetype("./Font/Font02.ttf", 18)
        self.draw.text((268, 100), str(math.floor(temp_t)) + '℃', fill=0x0088ff, font=Font1)

        self.draw.arc((253, 80, 313, 142), 0, 360, fill=0xffffff, width=8)
        self.draw.arc((253, 80, 313, 142), -90, -90 + (temp_t * 360 / 100), fill=0x0088ff, width=8)

        # Network speed
        TX = self.parameters.tx_speed * 1024

        if TX < 1024:  # B
            Font1 = ImageFont.truetype("./Font/Font02.ttf", 18)
            self.draw.text((250, 190), str(math.floor(TX)) + 'B/s', fill=0x00ff00, font=Font1, )
        elif TX < (1024 * 1024):  # K
            Font1 = ImageFont.truetype("./Font/Font02.ttf", 17)
            self.draw.text((249, 190), str(math.floor(TX / 1024)) + 'KB/s', fill=0x00ffff, font=Font1, )
        else:  # M
            Font1 = ImageFont.truetype("./Font/Font02.ttf", 18)
            self.draw.text((250, 190), str(math.floor(TX / 1024 / 1024)) + 'MB/s', fill=0x008fff, font=Font1, )

        RX = self.parameters.rx_speed * 1024

        if RX < 1024:  # B
            Font1 = ImageFont.truetype("./Font/Font02.ttf", 18)
            self.draw.text((183, 190), str(math.floor(RX)) + 'B/s', fill=0x00ff00, font=Font1, )
        elif RX < (1024 * 1024):  # K
            Font1 = ImageFont.truetype("./Font/Font02.ttf", 17)
            self.draw.text((180, 190), str(math.floor(RX / 1024)) + 'KB/s', fill=0x008fff, font=Font1, )
        else:  # M
            Font1 = ImageFont.truetype("./Font/Font02.ttf", 18)
            self.draw.text((181, 190), str(math.floor(RX / 1024 / 1024)) + 'MB/s', fill=0x008fff, font=Font1, )

        # Memory_percentage
        memory_usage = self.parameters.memory_usage
        Font1 = ImageFont.truetype("./Font/Font02.ttf", 18)

        if memory_usage >= 100:
            self.draw.text((186, 100), str(math.floor(memory_usage)) + '%', fill=0xf1b400, font=Font1, )
        elif memory_usage >= 10:
            self.draw.text((189, 100), str(math.floor(memory_usage)) + '%', fill=0xf1b400, font=Font1, )
        else:
            self.draw.text((195, 100), str(math.floor(memory_usage)) + '%', fill=0xf1b400, font=Font1, )
        self.draw.arc((173, 80, 233, 142), 0, 360, fill=0xffffff, width=8)
        self.draw.arc((173, 80, 233, 142), -90, -90 + (memory_usage * 360 / 100), fill=0xf1b400, width=8)

        # Disk Usage
        disk_parameters = self.parameters.disk_parameters
        if disk_parameters.disk0.capacity == 0:
            self.draw.rectangle((40, 177, 142, 190))
            self.draw.rectangle((41, 178, 141, 189), fill=0x000000)
        else:
            usage_percentage = disk_parameters.disk0.usage/disk_parameters.disk0.capacity
            self.draw.rectangle((40, 177, 142, 190))
            self.draw.rectangle((41, 178, 41 + usage_percentage, 189), fill=0x7f35e9)
            Font1 = ImageFont.truetype("./Font/Font02.ttf", 13)
            self.draw.text((80, 176), str(math.floor(usage_percentage*100)) + '%', fill=0xf1b400, font=Font1, )

        if disk_parameters.disk1.capacity == 0:
            self.draw.rectangle((40, 197, 142, 210))
            self.draw.rectangle((41, 198, 141, 209), fill=0x000000)
        else:
            usage_percentage = disk_parameters.disk1.usage/disk_parameters.disk1.capacity
            self.draw.rectangle((40, 197, 142, 210))
            self.draw.rectangle((41, 198, 41 + disk_parameters.disk1.usage, 209), fill=0x7f35e9)
            Font1 = ImageFont.truetype("./Font/Font02.ttf", 13)
            self.draw.text((80, 196), str(math.floor(usage_percentage*100)) + '%', fill=0xf1b400, font=Font1, )
        if disk_parameters.raid:
            Font1 = ImageFont.truetype("./Font/Font02.ttf", 15)
            self.draw.text((40, 161), 'RAID', fill=0xf7ba47, font=Font1)

        if ((disk_parameters.disk0.capacity == 0 and disk_parameters.disk1.capacity == 0) or 
            (disk_parameters.disk0.capacity != 0 and disk_parameters.disk1.capacity == 0) or 
            (disk_parameters.disk0.capacity == 0 and disk_parameters.disk1.capacity != 0)):
            Font1 = ImageFont.truetype("./Font/Font02.ttf", 15)
            if (self.parameters.flag > 0):
                self.draw.text((30, 210), 'Detected but not installed', fill=0xf7ba47, font=Font1)
            else:
                self.draw.text((50, 210), 'Unpartitioned/NC', fill=0xf7ba47, font=Font1)

        self.image = self.image.rotate(180)
        self.disp.ShowImage(self.image)


    def HMI2(self):
        """
        Second HMI screen, focusing on available storage
        """
        self.image = Image.open('pic/Disk.jpg')

        self.draw = ImageDraw.Draw(self.image)
        Font1 = ImageFont.truetype("./Font/Font02.ttf", 20)
        self.draw.text((60, 55), 'CPU Used', fill=0xC1C0BE, font=Font1)

        Font1 = ImageFont.truetype("./Font/Font02.ttf", 13)
        self.draw.text((45, 140), 'Used', fill=0xC1C0BE, font=Font1)
        self.draw.text((45, 163), 'Free', fill=0xC1C0BE, font=Font1)

        Font1 = ImageFont.truetype("./Font/Font02.ttf", 14)
        self.draw.text((185, 93), 'Disk0:', fill=0xC1C0BE, font=Font1)
        self.draw.text((185, 114), 'Disk1:', fill=0xC1C0BE, font=Font1)

        self.draw.text((188, 155), 'TX:', fill=0xC1C0BE, font=Font1)
        self.draw.text((188, 175), 'RX:', fill=0xC1C0BE, font=Font1)
        Font1 = ImageFont.truetype("./Font/Font02.ttf", 15)
        self.draw.text((133, 205), 'TEMP:', fill=0x0088ff, font=Font1)

        # Time
        time_t = time.strftime("%Y-%m-%d   %H:%M:%S", time.localtime())
        Font1 = ImageFont.truetype("./Font/Font02.ttf", 15)
        self.draw.text((40, 10), time_t, fill=0xffffff, font=Font1)

        # IP Address
        ip = self.parameters.ip_address
        Font1 = ImageFont.truetype("./Font/Font02.ttf", 17)
        self.draw.text((155, 58), 'IP : ' + ip, fill=0xC1C0BE, font=Font1)

        # CPU usage
        CPU_usage = self.parameters.cpu_usage

        if (CPU_usage >= 100):
            Font1 = ImageFont.truetype("./Font/Font02.ttf", 10)
            self.draw.text((80, 107), str(math.floor(CPU_usage)) + '%', fill=0xf1b400, font=Font1, )
        elif (CPU_usage >= 10):
            Font1 = ImageFont.truetype("./Font/Font02.ttf", 13)
            self.draw.text((79, 105), str(math.floor(CPU_usage)) + '%', fill=0xf1b400, font=Font1, )
        else:
            Font1 = ImageFont.truetype("./Font/Font02.ttf", 15)
            self.draw.text((81, 104), str(math.floor(CPU_usage)) + '%', fill=0xf1b400, font=Font1, )

        self.draw.arc((66, 90, 111, 135), -90, -90 + (CPU_usage * 360 / 100), fill=0x7f35e9, width=3)

        # System disk usage
        disk_usage = self.parameters.disk_usage
        disk_used = humanize.naturalsize(disk_usage.used)
        disk_free = humanize.naturalsize(disk_usage.free)
        Font1 = ImageFont.truetype("./Font/Font02.ttf", 13)
        self.draw.text((85, 140), disk_used, fill=0xC1C0BE, font=Font1, )
        self.draw.text((85, 163), disk_free, fill=0xC1C0BE, font=Font1, )
        self.draw.rectangle((45, 157, 45 + ((disk_usage.used / disk_usage.total) * 87), 160), fill=0x7f35e9)
        self.draw.rectangle((45, 180, 45 + ((disk_usage.free / disk_usage.total) * 87), 183), fill=0x7f35e9)

        # System Temperature
        temp_t = self.parameters.temperature
        if temp_t < 45:
            self.disp._pwm1.ChangeDutyCycle(20)
        elif temp_t < 50:
            self.disp._pwm1.ChangeDutyCycle(30)
        elif temp_t < 55:
            self.disp._pwm1.ChangeDutyCycle(50)
        else:
            self.disp._pwm1.ChangeDutyCycle(75)
        Font1 = ImageFont.truetype("./Font/Font02.ttf", 15)
        self.draw.text((170, 205), str(math.floor(temp_t)) + '℃', fill=0x0088ff, font=Font1)

        # Network speed
        TX = self.parameters.tx_speed * 1024

        Font1 = ImageFont.truetype("./Font/Font02.ttf", 15)
        if (TX < 1024):  # B
            self.draw.text((210, 154), str(math.floor(TX)) + 'B/s', fill=0x00ff00, font=Font1, )
        elif (TX < (1024 * 1024)):  # K
            self.draw.text((210, 154), str(math.floor(TX / 1024)) + 'KB/s', fill=0x00ffff, font=Font1, )
        else:  # M
            self.draw.text((210, 154), str(math.floor(TX / 1024 / 1024)) + 'MB/s', fill=0x008fff, font=Font1, )

        RX = self.parameters.rx_speed * 1024

        if (RX < 1024):  # B
            self.draw.text((210, 174), str(math.floor(RX)) + 'B/s', fill=0x00ff00, font=Font1, )
        elif (RX < (1024 * 1024)):  # K
            self.draw.text((210, 174), str(math.floor(RX / 1024)) + 'KB/s', fill=0x008fff, font=Font1, )
        else:  # M
            self.draw.text((210, 174), str(math.floor(RX / 1024 / 1024)) + 'MB/s', fill=0x008fff, font=Font1, )

        # Disk 使用情况
        disk_parameters = self.parameters.disk_parameters

        Disk0_Avail = disk_parameters.disk0.capacity - disk_parameters.disk0.usage
        Disk1_Avail = disk_parameters.disk1.capacity - disk_parameters.disk1.usage

        self.draw.text((240, 93), humanize.naturalsize(Disk0_Avail), fill=0xC1C0BE, font=Font1)
        self.draw.text((240, 114), humanize.naturalsize(Disk1_Avail), fill=0xC1C0BE, font=Font1)

        if (disk_parameters.disk0.capacity == 0):
            self.draw.rectangle((186, 110, 273, 113), fill=0x000000)
        else:
            self.draw.rectangle((186, 110, 186 + (disk_parameters.disk0.usage * 87 / 100), 113), fill=0x7f35e9)

        if (disk_parameters.disk1.capacity == 0):
            self.draw.rectangle((186, 131, 273, 134), fill=0x000000)
        else:
            self.draw.rectangle((186, 131, 186 + (disk_parameters.disk1.usage * 87 / 100), 134), fill=0x7f35e9)

        if disk_parameters.raid:
            self.draw.text((160, 78), 'RAID', fill=0xC1C0BE, font=Font1)

        if ((disk_parameters.disk0.capacity == 0 and disk_parameters.disk1.capacity == 0) or 
            (disk_parameters.disk0.capacity != 0 and disk_parameters.disk1.capacity == 0) or 
            (disk_parameters.disk0.capacity == 0 and disk_parameters.disk1.capacity != 0)):
            Font1 = ImageFont.truetype("./Font/Font02.ttf", 14)
            if (self.parameters.flag > 0):
                self.draw.text((155, 135), 'Detected but not installed', fill=0xC1C0BE, font=Font1)
            else:
                self.draw.text((190, 135), 'Unpartitioned/NC', fill=0xC1C0BE, font=Font1)

        self.image = self.image.rotate(180)
        self.disp.ShowImage(self.image)
