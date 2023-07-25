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


# Font1 = ImageFont.truetype("Font/Font01.ttf", 25)
# Font2 = ImageFont.truetype("Font/Font01.ttf", 35)
# Font3 = ImageFont.truetype("Font/Font02.ttf", 32)

font02_10 = ImageFont.truetype("./Font/Font02.ttf", 10)
font02_13 = ImageFont.truetype("./Font/Font02.ttf", 13)
font02_14 = ImageFont.truetype("./Font/Font02.ttf", 14)
font02_15 = ImageFont.truetype("./Font/Font02.ttf", 15)
font02_17 = ImageFont.truetype("./Font/Font02.ttf", 17)
font02_18 = ImageFont.truetype("./Font/Font02.ttf", 18)
font02_20 = ImageFont.truetype("./Font/Font02.ttf", 20)


class Display:
    display_mode = 1 # Default display mode
    fan_mode = "default"
    refresh_interval = 0.2

    hmi1_base = None
    hmi2_base = None

    def __init__(self):
        # display with hardware SPI:
        # Warning: Don't create multiple display objects!
        # disp = LCD_2inch.LCD_2inch(spi=SPI.SpiDev(bus, device),spi_freq=10000000,rst=RST,dc=DC,bl=BL)
        self.system_pararmeters = SystemParameters()
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(20, GPIO.IN)
        GPIO.setup(20, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        t1 = threading.Thread(target=self.system_pararmeters.update, name="thread1")
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

    def key(self):
        """
        Change HMI display mode when the USER key is held for 0.5 seconds
        Change fan mode when the USER key is held for 2 seconds
        """
        counter = 0
        while True:
            if GPIO.input(20) == 0:
                counter = counter + 1
            else:
                if counter > 20:
                    if self.fan_mode == "default":
                        logging.info('Fan mode: silent')
                        self.fan_mode = "silent"
                    else:
                        logging.info('Fan mode: default')
                        self.fan_mode = "default"
                elif counter > 5:
                    if self.display_mode == 1:
                        logging.info('HMI display mode: 2')
                        self.display_mode = 2
                    else:
                        logging.info('HMI display mode: 1')
                        self.display_mode = 1

                counter = 0
            time.sleep(0.1)

    def render(self):
        while True:
            try:
                if self.display_mode == 1:
                    self.HMI1()
                elif self.display_mode == 2:
                    self.HMI2()
                time.sleep(self.refresh_interval)
            
            except IOError as e:
                logging.warning(e)
            except KeyboardInterrupt:
                self.disp.module_exit()
                logging.info("quit:")
                exit()
    
    def set_fan_speed(self, speed):
        min_duty_cycle = 35
        if speed:
            duty_cycle = math.floor(speed*((100-min_duty_cycle)/100) + min_duty_cycle)
        else:
            duty_cycle = 0
        
        self.disp._pwm1.ChangeDutyCycle(duty_cycle)

    def control_fan(self):
        """
        Control the PWM fan depending on the CPU and disk temperatures

        Default mode: Scale fan speed linearly (0-100%) between 50 and 85 degrees Celsius
        Silent mode: Scale fan speed is linearly (0-50%) between 65 and 85 degrees Celsius
        """
        while True:
            temperatures = [self.system_pararmeters.cpu_temperature,
                            self.system_pararmeters.disk_parameters.disk0.temperature, 
                            self.system_pararmeters.disk_parameters.disk1.temperature]
            ref_temp = max(temperatures)
            fan_speed = 0
            if self.fan_mode == "default":
                base_temp = 50
                critical_temp = 85
                max_speed = 100

            elif self.fan_mode == "silent":
                base_temp = 65
                critical_temp = 85
                max_speed = 50

            if ref_temp >= base_temp:
                fan_speed = math.floor(max_speed*(ref_temp-base_temp)/(critical_temp-base_temp))

            self.set_fan_speed(fan_speed)
            
            time.sleep(5)
        
    def init_HMI1_base(self):
        image = Image.open('pic/BL.jpg')

        draw = ImageDraw.Draw(image)
        title_font = ImageFont.truetype("./Font/Font02.ttf", 28)
        draw.text((90, 2), 'Device Status', fill=0xf7ba47, font=title_font)

        draw.text((30, 141), 'CPU', fill=0xf7ba47, font=font02_15)
        draw.text((107, 141), 'Disk', fill=0xf7ba47, font=font02_15)
        draw.text((190, 141), 'RAM', fill=0xf7ba47, font=font02_15)
        draw.text((267, 141), 'TEMP', fill=0xf7ba47, font=font02_15)

        draw.text((205, 170), 'R X', fill=0xffffff, font=font02_10, stroke_width=1)
        draw.text((270, 170), 'T X', fill=0xffffff, font=font02_10, stroke_width=1)

        draw.arc((10, 80, 70, 142), 0, 360, fill=0xffffff, width=8)
        draw.arc((90, 80, 150, 142), 0, 360, fill=0xffffff, width=8)
        draw.arc((173, 80, 233, 142), 0, 360, fill=0xffffff, width=8)
        draw.arc((253, 80, 313, 142), 0, 360, fill=0xffffff, width=8)

        self.hmi1_base = image
    
    def init_HMI2_base(self):
        image = Image.open('pic/Disk.jpg')

        draw = ImageDraw.Draw(image)
        draw.text((60, 55), 'CPU Used', fill=0xC1C0BE, font=font02_20)

        draw.text((45, 140), 'Used', fill=0xC1C0BE, font=font02_13)
        draw.text((45, 163), 'Free', fill=0xC1C0BE, font=font02_13)

        draw.text((185, 93), 'Disk0:', fill=0xC1C0BE, font=font02_14)
        draw.text((185, 114), 'Disk1:', fill=0xC1C0BE, font=font02_14)

        draw.text((188, 155), 'TX:', fill=0xC1C0BE, font=font02_14)
        draw.text((188, 175), 'RX:', fill=0xC1C0BE, font=font02_14)

        draw.text((133, 205), 'TEMP:', fill=0x0088ff, font=font02_15)

        self.hmi2_base = image

    def HMI1(self):
        """
        First HMI screen, showing general device status and metrics such as:
        - Time
        - CPU/System Disk/RAM Usage
        - CPU Temperature
        - Storage Drive Usage
        - Upload/Download Speed
        """
        image = self.hmi1_base.copy()
        draw = ImageDraw.Draw(image)

        # TIME
        time_t = time.strftime("%Y-%m-%d   %H:%M:%S", time.localtime())
        draw.text((5, 50), time_t, fill=0xf7ba47, font=font02_15)

        # IP
        ip = self.system_pararmeters.ip_address
        draw.text((170, 50), 'IP : ' + ip, fill=0xf7ba47, font=font02_15)

        # CPU usage
        CPU_usage = self.system_pararmeters.cpu_usage

        if CPU_usage >= 100:
            draw.text((27, 100), str(math.floor(CPU_usage)) + '%', fill=0xf1b400, font=font02_15, )
        elif CPU_usage >= 10:
            draw.text((30, 100), str(math.floor(CPU_usage)) + '%', fill=0xf1b400, font=font02_15, )
        else:
            draw.text((34, 100), str(math.floor(CPU_usage)) + '%', fill=0xf1b400, font=font02_15, )

        draw.arc((10, 80, 70, 142), -90, -90 + (CPU_usage * 360 / 100), fill=0x60ad4c, width=8)

        # System disk usage
        disk_usage = self.system_pararmeters.disk_usage
        if (disk_usage.percent >= 100):
            draw.text((107, 100), str(math.floor(disk_usage.percent)) + '%', fill=0xf1b400, font=font02_15, )
        elif (disk_usage.percent >= 10):
            draw.text((111, 100), str(math.floor(disk_usage.percent)) + '%', fill=0xf1b400, font=font02_15, )
        else:
            draw.text((114, 100), str(math.floor(disk_usage.percent)) + '%', fill=0xf1b400, font=font02_15, )

        draw.arc((90, 80, 150, 142), -90, -90 + (disk_usage.percent * 360 / 100), fill=0x7f35e9, width=8)

        # System Temperature
        temp_t = self.system_pararmeters.cpu_temperature

        draw.text((268, 100), str(math.floor(temp_t)) + '℃', fill=0x0088ff, font=font02_18)

        draw.arc((253, 80, 313, 142), -90, -90 + (temp_t * 360 / 100), fill=0x0088ff, width=8)

        # Network speed
        TX = self.system_pararmeters.tx_speed

        if TX < 1024:  # B
            draw.text((250, 190), str(math.floor(TX)) + 'B/s', fill=0x00ff00, font=font02_18, )
        elif TX < (1024 * 1024):  # K
            draw.text((249, 190), str(math.floor(TX / 1024)) + 'KB/s', fill=0x00ffff, font=font02_17, )
        else:  # M
            draw.text((250, 190), str(math.floor(TX / 1024 / 1024)) + 'MB/s', fill=0x008fff, font=font02_18, )

        RX = self.system_pararmeters.rx_speed

        if RX < 1024:  # B
            draw.text((183, 190), str(math.floor(RX)) + 'B/s', fill=0x00ff00, font=font02_18, )
        elif RX < (1024 * 1024):  # K
            draw.text((180, 190), str(math.floor(RX / 1024)) + 'KB/s', fill=0x008fff, font=font02_17, )
        else:  # M
            draw.text((181, 190), str(math.floor(RX / 1024 / 1024)) + 'MB/s', fill=0x008fff, font=font02_18, )

        # Memory_percentage
        memory_usage = self.system_pararmeters.memory_usage

        if memory_usage >= 100:
            draw.text((186, 100), str(math.floor(memory_usage)) + '%', fill=0xf1b400, font=font02_18, )
        elif memory_usage >= 10:
            draw.text((189, 100), str(math.floor(memory_usage)) + '%', fill=0xf1b400, font=font02_18, )
        else:
            draw.text((195, 100), str(math.floor(memory_usage)) + '%', fill=0xf1b400, font=font02_18, )
        
        draw.arc((173, 80, 233, 142), -90, -90 + (memory_usage * 360 / 100), fill=0xf1b400, width=8)

        # Disk Usage
        disk_parameters = self.system_pararmeters.disk_parameters

        # Disk 0 Usage
        if disk_parameters.disk0.capacity == 0:
            draw.rectangle((40, 177, 142, 190))
            draw.rectangle((41, 178, 141, 189), fill=0x000000)
        else:
            draw.rectangle((40, 177, 142, 190))
            draw.rectangle((41, 178, 41 + disk_parameters.disk0.used_percentage, 189), fill=0x7f35e9)
            draw.text((80, 176), str(math.floor(disk_parameters.disk0.used_percentage)) + '%', fill=0xf1b400, font=font02_13, )
        # Disk 1 Usage
        if disk_parameters.disk1.capacity == 0:
            draw.rectangle((40, 197, 142, 210))
            draw.rectangle((41, 198, 141, 209), fill=0x000000)
        else:
            draw.rectangle((40, 197, 142, 210))
            draw.rectangle((41, 198, 41 + disk_parameters.disk1.used_percentage, 209), fill=0x7f35e9)
            draw.text((80, 196), str(math.floor(disk_parameters.disk1.used_percentage)) + '%', fill=0xf1b400, font=font02_13, )
        # RAID Check
        if disk_parameters.raid:
            draw.text((40, 161), 'RAID', fill=0xf7ba47, font=font02_15)

        if ((disk_parameters.disk0.capacity == 0 and disk_parameters.disk1.capacity == 0) or 
            (disk_parameters.disk0.capacity != 0 and disk_parameters.disk1.capacity == 0) or 
            (disk_parameters.disk0.capacity == 0 and disk_parameters.disk1.capacity != 0)):
            if (self.system_pararmeters.flag > 0):
                draw.text((30, 210), 'Detected but not installed', fill=0xf7ba47, font=font02_15)
            else:
                draw.text((50, 210), 'Unpartitioned/NC', fill=0xf7ba47, font=font02_15)

        image = image.rotate(180)
        self.disp.ShowImage(image)


    def HMI2(self):
        """
        Second HMI screen, focusing on available storage
        """
        image = self.hmi2_base.copy()
        draw = ImageDraw.Draw(image)

        # Time
        time_t = time.strftime("%Y-%m-%d   %H:%M:%S", time.localtime())
        draw.text((40, 10), time_t, fill=0xffffff, font=font02_15)

        # IP Address
        ip = self.system_pararmeters.ip_address
        draw.text((155, 58), 'IP : ' + ip, fill=0xC1C0BE, font=font02_17)

        # CPU usage
        CPU_usage = self.system_pararmeters.cpu_usage

        if (CPU_usage >= 100):
            draw.text((80, 107), str(math.floor(CPU_usage)) + '%', fill=0xf1b400, font=font02_10, )
        elif (CPU_usage >= 10):
            draw.text((79, 105), str(math.floor(CPU_usage)) + '%', fill=0xf1b400, font=font02_13, )
        else:
            draw.text((81, 104), str(math.floor(CPU_usage)) + '%', fill=0xf1b400, font=font02_15, )

        draw.arc((66, 90, 111, 135), -90, -90 + (CPU_usage * 360 / 100), fill=0x7f35e9, width=3)

        # System disk usage
        disk_usage = self.system_pararmeters.disk_usage
        disk_used = humanize.naturalsize(disk_usage.used)
        disk_free = humanize.naturalsize(disk_usage.free)
        draw.text((85, 140), disk_used, fill=0xC1C0BE, font=font02_13, )
        draw.text((85, 163), disk_free, fill=0xC1C0BE, font=font02_13, )
        draw.rectangle((45, 157, 45 + ((disk_usage.used / disk_usage.total) * 87), 160), fill=0x7f35e9)
        draw.rectangle((45, 180, 45 + ((disk_usage.free / disk_usage.total) * 87), 183), fill=0x7f35e9)

        # System Temperature
        temp_t = self.system_pararmeters.cpu_temperature
        draw.text((170, 205), str(math.floor(temp_t)) + '℃', fill=0x0088ff, font=font02_15)

        # Network speed
        TX = self.system_pararmeters.tx_speed

        if (TX < 1024):  # B
            draw.text((210, 154), str(math.floor(TX)) + 'B/s', fill=0x00ff00, font=font02_15, )
        elif (TX < (1024 * 1024)):  # K
            draw.text((210, 154), str(math.floor(TX / 1024)) + 'KB/s', fill=0x00ffff, font=font02_15, )
        else:  # M
            draw.text((210, 154), str(math.floor(TX / 1024 / 1024)) + 'MB/s', fill=0x008fff, font=font02_15, )

        RX = self.system_pararmeters.rx_speed

        if (RX < 1024):  # B
            draw.text((210, 174), str(math.floor(RX)) + 'B/s', fill=0x00ff00, font=font02_15, )
        elif (RX < (1024 * 1024)):  # K
            draw.text((210, 174), str(math.floor(RX / 1024)) + 'KB/s', fill=0x008fff, font=font02_15, )
        else:  # M
            draw.text((210, 174), str(math.floor(RX / 1024 / 1024)) + 'MB/s', fill=0x008fff, font=font02_15, )

        # Disk Usage
        disk_parameters = self.system_pararmeters.disk_parameters

        # Disk 0
        draw.text((240, 93), humanize.naturalsize(disk_parameters.disk0.available), fill=0xC1C0BE, font=font02_15)
        if (disk_parameters.disk0.capacity == 0):
            draw.rectangle((186, 110, 273, 113), fill=0x000000)
        else:
            draw.rectangle((186, 110, 186 + (disk_parameters.disk0.used_percentage * 87 / 100), 113), fill=0x7f35e9)
        # Disk 1
        draw.text((240, 114), humanize.naturalsize(disk_parameters.disk1.available), fill=0xC1C0BE, font=font02_15)
        if (disk_parameters.disk1.capacity == 0):
            draw.rectangle((186, 131, 273, 134), fill=0x000000)
        else:
            draw.rectangle((186, 131, 186 + (disk_parameters.disk1.used_percentage * 87 / 100), 134), fill=0x7f35e9)
        # RAID Check
        if disk_parameters.raid:
            draw.text((160, 78), 'RAID', fill=0xC1C0BE, font=font02_15)

        if ((disk_parameters.disk0.capacity == 0 and disk_parameters.disk1.capacity == 0) or 
            (disk_parameters.disk0.capacity != 0 and disk_parameters.disk1.capacity == 0) or 
            (disk_parameters.disk0.capacity == 0 and disk_parameters.disk1.capacity != 0)):
            if (self.system_pararmeters.flag > 0):
                draw.text((155, 135), 'Detected but not installed', fill=0xC1C0BE, font=font02_14)
            else:
                draw.text((190, 135), 'Unpartitioned/NC', fill=0xC1C0BE, font=font02_14)

        image = image.rotate(180)
        self.disp.ShowImage(image)
