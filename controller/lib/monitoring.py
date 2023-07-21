import json
import logging
import os
import psutil
import re
import socket
import time
from dataclasses import dataclass, field
from psutil._common import sdiskusage


@dataclass
class Disk:
    id: str
    capacity: int = 0
    usage: int = 0

    def calculate_capacity_and_usage(self, children):
        total_capacity = 0
        total_usage = 0
        for child in children:
            capacity = int(child['fsavail'])
            usage = float(child['fsuse%'].strip('%'))/100 * capacity

            total_capacity += capacity
            total_usage += usage

        self.capacity = total_capacity
        self.usage = total_usage


@dataclass
class StorageParameters:
    disk0: Disk = Disk('sda')
    disk1: Disk = Disk('sdb')
    raid: bool = False

    update_interval: int = 1

    def update(self):
        blockdevices = json.loads(os.popen('lsblk  -f -b --json').read())['blockdevices']

        # Check for RAID volumes
        if any(['raid' in device['fstype'] for device in blockdevices
                if device['name'] in [self.disk0.id, self.disk1.id]]):
            self.raid = True

        # Calculate capacity and usage of each disk
        for device in blockdevices:
            for disk in [self.disk0, self.disk1]:
                if device['name'] == disk.id:
                    disk.calculate_capacity_and_usage(children=device['children'])


@dataclass
class SystemParameters:
    disk_parameters: StorageParameters = StorageParameters()
    ip_address: str = '127.0.0.1'
    temperature: float = 0.0
    rx_speed: float = 0.0
    tx_speed: float = 0.0
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    disk_usage: sdiskusage = sdiskusage(total=0, used=0, free=0, percent=0)

    update_interval: int = 1

    flag = 0  # 未挂载还是未分区

    def update(self):
        while True:
            self.disk_parameters.update()
            self.get_ip_address()
            self.get_temperature()
            self.get_rx_speed()
            self.get_tx_speed()
            self.get_cpu_usage()
            self.get_memory_usage()
            self.get_disk_usage()

            logging.debug(self)

            time.sleep(self.update_interval)

    def get_ip_address(self):
        # There will be exceptions, get stuck, get it carefully
        # Threading is better
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect_ex(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        self.ip_address = ip

    def get_temperature(self):
        temp = float(os.popen('vcgencmd measure_temp').read().strip().split('=')[1].strip("'C"))
        self.temperature = temp

    @staticmethod
    def get_network_speed(interface, is_download):
        # Get the corresponding value   获取对应值
        which_num = 0 if is_download else 8

        # Read the file  读取文件
        with open('/proc/net/dev') as f:
            lines = f.readlines()
        # Get result value 获取结果值       
        for line in lines:
            if line.rstrip().split(':')[0].strip() == interface:
                return line.rstrip().split(':')[1].split()[which_num]

    def get_rx_speed(self):
        interface = 'eth0'
        is_upload = True  # False
        get_time = 0.1
        # Computation part 计算部分
        begin = int(self.get_network_speed(interface, is_upload))
        time.sleep(get_time)
        end = int(self.get_network_speed(interface, is_upload))
        self.rx_speed = (end - begin) / get_time / 1024

    def get_tx_speed(self):
        interface = 'eth0'
        is_upload = False
        get_time = 0.1
        # Computation part 计算部分
        begin = int(self.get_network_speed(interface, is_upload))
        time.sleep(get_time)
        end = int(self.get_network_speed(interface, is_upload))
        self.tx_speed = (end - begin) / get_time / 1024

    def get_cpu_usage(self):
        self.cpu_usage = psutil.cpu_percent()

    def get_memory_usage(self):
        self.memory_usage = psutil.virtual_memory().percent
    
    def get_disk_usage(self):
        self.disk_usage = psutil.disk_usage('/')
