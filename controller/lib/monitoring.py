import json
import logging
import os
import re
import socket
import time
from dataclasses import dataclass


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
        
        logging.debug(f"{self.id}: {self.usage}/{self.capacity}")

        self.capacity = total_capacity
        self.usage = total_usage


@dataclass
class StorageParameters:
    disk0: Disk = Disk('sda')
    disk1: Disk = Disk('sdb')
    raid: bool = False

    update_interval: int = 1

    def update(self):
        while True:
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

            time.sleep(self.update_interval)


@dataclass
class ReadParameters:
    Get_back = [0, 0, 0, 0, 0]  # 返回Disk的内存
    disk_parameters = StorageParameters()
    flag = 0  # 未挂载还是未分区

    @staticmethod
    def get_ip_address():
        # 会存在异常  卡死   谨慎获取
        # There will be exceptions, get stuck, get it carefully
        # Threading is better
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect_ex(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip

    @staticmethod
    def get_temperature():
        with open('/sys/class/thermal/thermal_zone0/temp', 'rt') as f:
            temp = int(f.read()) / 1000.0
        # print(temp)
        return temp

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
        return (end - begin) / get_time / 1024

    def get_tx_speed(self):
        interface = 'eth0'
        is_upload = False
        get_time = 0.1
        # Computation part 计算部分
        begin = int(self.get_network_speed(interface, is_upload))
        time.sleep(get_time)
        end = int(self.get_network_speed(interface, is_upload))

        return (end - begin) / get_time / 1024
