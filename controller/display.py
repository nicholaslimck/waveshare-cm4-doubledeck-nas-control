import logging
import math
import os
import re
import threading
import time

import RPi.GPIO as GPIO
from PIL import Image, ImageDraw, ImageFont

from lib.monitoring import ReadParameters
from lib.LCD_2inch import LCD_2inch

logging.basicConfig(level=logging.DEBUG)

Font1 = ImageFont.truetype("Font/Font01.ttf", 25)
Font2 = ImageFont.truetype("Font/Font01.ttf", 35)
Font3 = ImageFont.truetype("Font/Font02.ttf", 32)


class Display:
    flgh = True

    def __init__(self):
        # display with hardware SPI:
        ''' Warning!!!Don't  creation of multiple displayer objects!!! '''
        # disp = LCD_2inch.LCD_2inch(spi=SPI.SpiDev(bus, device),spi_freq=10000000,rst=RST,dc=DC,bl=BL)
        self.parameters = ReadParameters()
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(20, GPIO.IN)
        GPIO.setup(20, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        t1 = threading.Thread(target=self.parameters.disk_parameters.update, name="thread1")
        t2 = threading.Thread(target=self.key, name="thread2")
        t1.daemon = True
        t2.daemon = True
        t1.start()
        t2.start()

        self.disp = LCD_2inch()

        # Initialize library.
        self.disp.Init()
        # Clear display.
        self.disp.clear()

        # Create blank image for drawing.
        self.image1 = Image.new("RGB", (self.disp.height, self.disp.width), "WHITE")
        self.draw = ImageDraw.Draw(self.image1)

    def key(self):
        count = 0
        while True:
            if (GPIO.input(20) == 0):
                count = count + 1
            else:
                if (count > 5):
                    self.flgh = not self.flgh
                    count = 0

    def HMI1(self):
        try:
            self.image = Image.open('pic/BL.jpg')

            self.draw = ImageDraw.Draw(self.image)
            Font1 = ImageFont.truetype("../Font/Font02.ttf", 28)
            self.draw.text((90, 2), 'Device Status', fill=0xf7ba47, font=Font1)

            Font1 = ImageFont.truetype("../Font/Font02.ttf", 15)
            self.draw.text((267, 141), 'TEMP', fill=0xf7ba47, font=Font1)
            self.draw.text((190, 141), 'RAM', fill=0xf7ba47, font=Font1)
            self.draw.text((267, 141), 'TEMP', fill=0xf7ba47, font=Font1)
            self.draw.text((30, 141), 'CPU', fill=0xf7ba47, font=Font1)
            self.draw.text((107, 141), 'Disk', fill=0xf7ba47, font=Font1)

            Font1 = ImageFont.truetype("../Font/Font02.ttf", 10)
            self.draw.text((205, 170), 'R X', fill=0xffffff, font=Font1, stroke_width=1)

            Font1 = ImageFont.truetype("../Font/Font02.ttf", 10)
            self.draw.text((270, 170), 'T X', fill=0xffffff, font=Font1, stroke_width=1)

            # TIME 时间
            time_t = time.strftime("%Y-%m-%d   %H:%M:%S", time.localtime())
            Font1 = ImageFont.truetype("../Font/Font02.ttf", 15)
            self.draw.text((5, 50), time_t, fill=0xf7ba47, font=Font1)

            # IP
            ip = self.parameters.get_ip_address()
            Font1 = ImageFont.truetype("../Font/Font02.ttf", 15)
            self.draw.text((170, 50), 'IP : ' + ip, fill=0xf7ba47, font=Font1)

            # CPU usage  CPU使用率
            self.CPU_usage = os.popen('top -bi -n 2 -d 0.02').read().split('\n\n\n')[0].split('\n')[2]
            self.CPU_usage = re.sub('[a-zA-z%(): ]', '', self.CPU_usage)
            self.CPU_usage = self.CPU_usage.split(',')

            self.CPU_usagex = 100 - eval(self.CPU_usage[3])

            if self.CPU_usagex >= 100:
                self.draw.text((27, 100), str(math.floor(self.CPU_usagex)) + '%', fill=0xf1b400, font=Font1, )
            elif self.CPU_usagex >= 10:
                self.draw.text((30, 100), str(math.floor(self.CPU_usagex)) + '%', fill=0xf1b400, font=Font1, )
            else:
                self.draw.text((34, 100), str(math.floor(self.CPU_usagex)) + '%', fill=0xf1b400, font=Font1, )

            self.draw.arc((10, 80, 70, 142), 0, 360, fill=0xffffff, width=8)
            self.draw.arc((10, 80, 70, 142), -90, -90 + (self.CPU_usagex * 360 / 100), fill=0x60ad4c, width=8)

            # System disk usage   系统磁盘使用率
            x = os.popen('df -h /')
            i2 = 0
            while 1:
                i2 = i2 + 1
                line = x.readline()
                if i2 == 2:
                    self.Capacity_usage = line.split()[4]  # Memory usage (%)   使用内存（百分值）
                    self.Hard_capacity = int(re.sub('[%]', '', self.Capacity_usage))
                    break
            if (self.Hard_capacity >= 100):
                self.draw.text((107, 100), str(math.floor(self.Hard_capacity)) + '%', fill=0xf1b400, font=Font1, )
            elif (self.Hard_capacity >= 10):
                self.draw.text((111, 100), str(math.floor(self.Hard_capacity)) + '%', fill=0xf1b400, font=Font1, )
            else:
                self.draw.text((114, 100), str(math.floor(self.Hard_capacity)) + '%', fill=0xf1b400, font=Font1, )

            self.draw.arc((90, 80, 150, 142), 0, 360, fill=0xffffff, width=8)
            self.draw.arc((90, 80, 150, 142), -90, -90 + (self.Hard_capacity * 360 / 100), fill=0x7f35e9, width=8)

            # TEMP  温度
            self.temp_t = self.parameters.get_temperature()
            if self.temp_t < 45:
                self.disp._pwm1.ChangeDutyCycle(50)
            elif self.temp_t < 50:
                self.disp._pwm1.ChangeDutyCycle(70)
            elif self.temp_t < 55:
                self.disp._pwm1.ChangeDutyCycle(80)
            else:
                self.disp._pwm1.ChangeDutyCycle(100)
            Font1 = ImageFont.truetype("../Font/Font02.ttf", 18)
            self.draw.text((268, 100), str(math.floor(self.temp_t)) + '℃', fill=0x0088ff, font=Font1)

            self.draw.arc((253, 80, 313, 142), 0, 360, fill=0xffffff, width=8)
            self.draw.arc((253, 80, 313, 142), -90, -90 + (self.temp_t * 360 / 100), fill=0x0088ff, width=8)

            # speed 网速

            TX = self.parameters.get_tx_speed() * 1024

            if TX < 1024:  # B
                Font1 = ImageFont.truetype("../Font/Font02.ttf", 18)
                self.draw.text((250, 190), str(math.floor(TX)) + 'B/s', fill=0x00ff00, font=Font1, )

            elif TX < (1024 * 1024):  # K
                Font1 = ImageFont.truetype("../Font/Font02.ttf", 17)
                self.draw.text((249, 190), str(math.floor(TX / 1024)) + 'KB/s', fill=0x00ffff, font=Font1, )

            else:  # M
                Font1 = ImageFont.truetype("../Font/Font02.ttf", 18)
                self.draw.text((250, 190), str(math.floor(TX / 1024 / 1024)) + 'M/s', fill=0x008fff, font=Font1, )

            TX = self.parameters.get_rx_speed() * 1024

            if TX < 1024:  # B
                Font1 = ImageFont.truetype("../Font/Font02.ttf", 18)
                self.draw.text((183, 190), str(math.floor(TX)) + 'B/s', fill=0x00ff00, font=Font1, )

            elif TX < (1024 * 1024):  # K
                Font1 = ImageFont.truetype("../Font/Font02.ttf", 17)
                self.draw.text((180, 190), str(math.floor(TX / 1024)) + 'KB/s', fill=0x008fff, font=Font1, )

            else:  # M
                Font1 = ImageFont.truetype("../Font/Font02.ttf", 18)
                self.draw.text((181, 190), str(math.floor(TX / 1024 / 1024)) + 'M/s', fill=0x008fff, font=Font1, )

                # memory_percentage  内存百分比
            tot_m, used_m, free_m = map(int, os.popen('free -t -m').readlines()[-1].split()[1:])

            Font1 = ImageFont.truetype("../Font/Font02.ttf", 18)
            memory_percentage = 100 - free_m / tot_m * 100

            if memory_percentage >= 100:
                self.draw.text((186, 100), str(math.floor(memory_percentage)) + '%', fill=0xf1b400, font=Font1, )
            elif memory_percentage >= 10:
                self.draw.text((189, 100), str(math.floor(memory_percentage)) + '%', fill=0xf1b400, font=Font1, )
            else:
                self.draw.text((195, 100), str(math.floor(memory_percentage)) + '%', fill=0xf1b400, font=Font1, )
            self.draw.arc((173, 80, 233, 142), 0, 360, fill=0xffffff, width=8)
            self.draw.arc((173, 80, 233, 142), -90, -90 + (memory_percentage * 360 / 100), fill=0xf1b400, width=8)

            # Disk 使用情况
            if self.parameters.Get_back[0] == 0:
                self.draw.rectangle((40, 177, 142, 190))
                self.draw.rectangle((41, 178, 141, 189), fill=0x000000)
            else:
                self.draw.rectangle((40, 177, 142, 190))
                self.draw.rectangle((41, 178, 41 + self.parameters.Get_back[2], 189), fill=0x7f35e9)
                Font1 = ImageFont.truetype("../Font/Font02.ttf", 13)
                self.draw.text((80, 176), str(math.floor(self.parameters.Get_back[2])) + '%', fill=0xf1b400, font=Font1, )

            if self.parameters.Get_back[1] == 0:
                self.draw.rectangle((40, 197, 142, 210))
                self.draw.rectangle((41, 198, 141, 209), fill=0x000000)
            else:
                self.draw.rectangle((40, 197, 142, 210))
                self.draw.rectangle((41, 198, 41 + self.parameters.Get_back[3], 209), fill=0x7f35e9)
                Font1 = ImageFont.truetype("../Font/Font02.ttf", 13)
                self.draw.text((80, 196), str(math.floor(self.parameters.Get_back[3])) + '%', fill=0xf1b400, font=Font1, )
            if self.parameters.Get_back[4] == 1:
                Font1 = ImageFont.truetype("../Font/Font02.ttf", 15)
                self.draw.text((40, 161), 'RAID', fill=0xf7ba47, font=Font1)

            if ((self.parameters.Get_back[0] == 0 and self.parameters.Get_back[1] == 0) or (
                    self.parameters.Get_back[0] != 0 and self.parameters.Get_back[1] == 0) or (
                    self.parameters.Get_back[0] == 0 and self.parameters.Get_back[1] != 0)):
                Font1 = ImageFont.truetype("../Font/Font02.ttf", 15)
                if (self.parameters.flag > 0):
                    self.draw.text((30, 210), 'Detected but not installed', fill=0xf7ba47, font=Font1)
                else:
                    self.draw.text((50, 210), 'Unpartitioned/NC', fill=0xf7ba47, font=Font1)

            self.image = self.image.rotate(180)
            self.disp.ShowImage(self.image)

        # time.sleep(0.5)
        except IOError as e:
            logging.info(e)
        except KeyboardInterrupt:
            self.disp.module_exit()
            logging.info("quit:")
            exit()

    def HMI2(self):
        try:
            self.image = Image.open('pic/Disk.jpg')

            self.draw = ImageDraw.Draw(self.image)
            Font1 = ImageFont.truetype("../Font/Font02.ttf", 20)
            self.draw.text((60, 55), 'CPU Used', fill=0xC1C0BE, font=Font1)

            Font1 = ImageFont.truetype("../Font/Font02.ttf", 13)
            self.draw.text((45, 140), 'Used', fill=0xC1C0BE, font=Font1)
            self.draw.text((45, 163), 'Free', fill=0xC1C0BE, font=Font1)

            Font1 = ImageFont.truetype("../Font/Font02.ttf", 14)
            self.draw.text((185, 93), 'Disk0:', fill=0xC1C0BE, font=Font1)
            self.draw.text((185, 114), 'Disk1:', fill=0xC1C0BE, font=Font1)

            self.draw.text((188, 155), 'TX:', fill=0xC1C0BE, font=Font1)
            self.draw.text((188, 175), 'RX:', fill=0xC1C0BE, font=Font1)
            Font1 = ImageFont.truetype("../Font/Font02.ttf", 15)
            self.draw.text((133, 205), 'TEMP:', fill=0x0088ff, font=Font1)

            # TIME 时间
            time_t = time.strftime("%Y-%m-%d   %H:%M:%S", time.localtime())
            Font1 = ImageFont.truetype("../Font/Font02.ttf", 15)
            self.draw.text((40, 10), time_t, fill=0xffffff, font=Font1)

            # IP
            ip = self.parameters.get_ip_address()
            Font1 = ImageFont.truetype("../Font/Font02.ttf", 17)
            self.draw.text((155, 58), 'IP : ' + ip, fill=0xC1C0BE, font=Font1)

            # CPU usage  CPU使用率
            self.CPU_usage = os.popen('top -bi -n 2 -d 0.02').read().split('\n\n\n')[0].split('\n')[2]
            self.CPU_usage = re.sub('[a-zA-z%(): ]', '', self.CPU_usage)
            self.CPU_usage = self.CPU_usage.split(',')
            self.CPU_usagex = 100 - eval(self.CPU_usage[3])

            if (self.CPU_usagex >= 100):
                Font1 = ImageFont.truetype("../Font/Font02.ttf", 10)
                self.draw.text((80, 107), str(math.floor(self.CPU_usagex)) + '%', fill=0xf1b400, font=Font1, )
            elif (self.CPU_usagex >= 10):
                Font1 = ImageFont.truetype("../Font/Font02.ttf", 13)
                self.draw.text((79, 105), str(math.floor(self.CPU_usagex)) + '%', fill=0xf1b400, font=Font1, )
            else:
                Font1 = ImageFont.truetype("../Font/Font02.ttf", 15)
                self.draw.text((81, 104), str(math.floor(self.CPU_usagex)) + '%', fill=0xf1b400, font=Font1, )

            self.draw.arc((66, 90, 111, 135), -90, -90 + (self.CPU_usagex * 360 / 100), fill=0x7f35e9, width=3)

            # System disk usage   系统磁盘使用率
            x = os.popen('df -h /')
            i2 = 0
            while 1:
                i2 = i2 + 1
                line = x.readline()
                if i2 == 2:
                    self.Capacity_Used = line.split()[2]
                    self.Capacity_Avail = line.split()[3]
                    if (self.Capacity_Used.count('G') and self.Capacity_Avail.count('G')):
                        self.Used_capacity = float(re.sub('[A-Z]', '', self.Capacity_Used)) * 1024
                        self.Avail_capacity = float(re.sub('[A-Z]', '', self.Capacity_Avail)) * 1024
                    elif (self.Capacity_Used.count('G') and self.Capacity_Avail.count('M')):
                        self.Used_capacity = float(re.sub('[A-Z]', '', self.Capacity_Used)) * 1024
                        self.Avail_capacity = float(re.sub('[A-Z]', '', self.Capacity_Avail))
                    elif (self.Capacity_Used.count('M') and self.Capacity_Avail.count('G')):
                        self.Used_capacity = float(re.sub('[A-Z]', '', self.Capacity_Used))
                        self.Avail_capacity = float(re.sub('[A-Z]', '', self.Capacity_Avail)) * 1024
                    else:
                        self.Used_capacity = float(re.sub('[A-Z]', '', self.Capacity_Used))
                        self.Avail_capacity = float(re.sub('[A-Z]', '', self.Capacity_Avail))

                    break
            if (self.Used_capacity > 1024 and self.Avail_capacity > 1024):
                Font1 = ImageFont.truetype("../Font/Font02.ttf", 13)
                self.draw.text((125, 140), 'G', fill=0xC1C0BE, font=Font1)
                self.draw.text((125, 163), 'G', fill=0xC1C0BE, font=Font1)
                self.Used_capacity = self.Used_capacity / 1024
                self.Avail_capacity = self.Avail_capacity / 1024

                self.Disk_always = self.Used_capacity + self.Avail_capacity
                if (self.Disk_always <= 99):
                    self.draw.text((100, 140), str(round(self.Used_capacity, 2)), fill=0xC1C0BE, font=Font1, )
                    self.draw.text((100, 163), str(round(self.Avail_capacity, 2)), fill=0xC1C0BE, font=Font1, )
                elif (self.Disk_always > 99):
                    self.draw.text((85, 140), str(round(self.Used_capacity, 2)), fill=0xC1C0BE, font=Font1, )
                    self.draw.text((85, 163), str(round(self.Avail_capacity, 2)), fill=0xC1C0BE, font=Font1, )
            else:
                Font1 = ImageFont.truetype("../Font/Font02.ttf", 13)
                self.draw.text((125, 140), 'M', fill=0xC1C0BE, font=Font1)
                self.draw.text((125, 163), 'M', fill=0xC1C0BE, font=Font1)
                self.Disk_always = self.Used_capacity + self.Avail_capacity
                self.draw.text((80, 140), str(round(self.Used_capacity, 2)), fill=0xC1C0BE, font=Font1, )
                self.draw.text((80, 163), str(round(self.Avail_capacity, 2)), fill=0xC1C0BE, font=Font1, )

            self.draw.rectangle((45, 157, 45 + ((self.Used_capacity / self.Disk_always) * 87), 160), fill=0x7f35e9)
            self.draw.rectangle((45, 180, 45 + ((self.Avail_capacity / self.Disk_always) * 87), 183), fill=0x7f35e9)

            # TEMP  温度
            temp_t = self.parameters.get_temperature()
            if self.temp_t < 45:
                self.disp._pwm1.ChangeDutyCycle(50)
            elif self.temp_t < 50:
                self.disp._pwm1.ChangeDutyCycle(70)
            elif self.temp_t < 55:
                self.disp._pwm1.ChangeDutyCycle(80)
            else:
                self.disp._pwm1.ChangeDutyCycle(100)
            Font1 = ImageFont.truetype("../Font/Font02.ttf", 15)
            self.draw.text((170, 205), str(math.floor(temp_t)) + '℃', fill=0x0088ff, font=Font1)

            # speed 网速
            TX = self.parameters.get_tx_speed() * 1024

            Font1 = ImageFont.truetype("../Font/Font02.ttf", 15)
            if (TX < 1024):  # B
                self.draw.text((210, 154), str(math.floor(TX)) + 'B/s', fill=0x00ff00, font=Font1, )

            elif (TX < (1024 * 1024)):  # K
                self.draw.text((210, 154), str(math.floor(TX / 1024)) + 'KB/s', fill=0x00ffff, font=Font1, )

            else:  # M
                self.draw.text((210, 154), str(math.floor(TX / 1024 / 1024)) + 'M/s', fill=0x008fff, font=Font1, )

            TX = self.parameters.get_rx_speed() * 1024

            if (TX < 1024):  # B
                self.draw.text((210, 174), str(math.floor(TX)) + 'B/s', fill=0x00ff00, font=Font1, )

            elif (TX < (1024 * 1024)):  # K
                self.draw.text((210, 174), str(math.floor(TX / 1024)) + 'KB/s', fill=0x008fff, font=Font1, )


            else:  # M
                self.draw.text((210, 174), str(math.floor(TX / 1024 / 1024)) + 'M/s', fill=0x008fff, font=Font1, )

                # Disk 使用情况

            self.Disk0_Avail = self.parameters.Get_back[0] - (self.parameters.Get_back[0] * self.parameters.Get_back[2] // 100)
            self.Disk1_Avail = self.parameters.Get_back[1] - (self.parameters.Get_back[1] * self.parameters.Get_back[3] // 100)

            self.draw.text((240, 93), str(math.floor(self.Disk0_Avail)) + 'G', fill=0xC1C0BE, font=Font1)
            self.draw.text((240, 114), str(math.floor(self.Disk1_Avail)) + 'G', fill=0xC1C0BE, font=Font1)

            if (self.parameters.Get_back[0] == 0):
                self.draw.rectangle((186, 110, 273, 113), fill=0x000000)
            else:
                self.draw.rectangle((186, 110, 186 + (self.parameters.Get_back[2] * 87 / 100), 113), fill=0x7f35e9)

            if (self.parameters.Get_back[1] == 0):
                self.draw.rectangle((186, 131, 273, 134), fill=0x000000)
            else:
                self.draw.rectangle((186, 131, 186 + (self.parameters.Get_back[3] * 87 / 100), 134), fill=0x7f35e9)

            if self.parameters.Get_back[4] == 1:
                self.draw.text((160, 78), 'RAID', fill=0xC1C0BE, font=Font1)

            if ((self.parameters.Get_back[0] == 0 and self.parameters.Get_back[1] == 0) or (
                    self.parameters.Get_back[0] != 0 and self.parameters.Get_back[1] == 0) or (
                    self.parameters.Get_back[0] == 0 and self.parameters.Get_back[1] != 0)):
                Font1 = ImageFont.truetype("../Font/Font02.ttf", 14)
                if (self.parameters.flag > 0):
                    self.draw.text((155, 135), 'Detected but not installed', fill=0xC1C0BE, font=Font1)
                else:
                    self.draw.text((190, 135), 'Unpartitioned/NC', fill=0xC1C0BE, font=Font1)

            self.image = self.image.rotate(180)
            self.disp.ShowImage(self.image)
        # time.sleep(0.5)

        except IOError as e:
            logging.info(e)
        except KeyboardInterrupt:
            self.disp.module_exit()
            logging.info("quit:")
            exit()
