import json
import os
import re
import socket
import time
from dataclasses import dataclass


@dataclass
class Disk:
    id: str
    capacity: int = None
    usage: int = None

    def calculate_capacity_and_usage(self, children):
        for child in children:
            capacity = child['fsavail']
            usage = float(child['fsuse%'].strip('%'))/100 * capacity

            self.capacity += capacity
            self.usage += usage


@dataclass
class StorageParameters:
    disk0: Disk = Disk('sda')
    disk1: Disk = Disk('sdb')
    raid: bool = False

    update_interval: int = 1.5

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

    def Hard_data(self):
        while True:
            Hard_capacity1 = os.popen('lsblk  -f ').read().split('\n\n\n')[0]
            Disk_number = sum(1 for i in re.finditer(r'^[a-z]', Hard_capacity1, re.MULTILINE))
            Hard_segmentation = Hard_capacity1.split('\n\n\n')[0].split('\n')

            k = 0  # Counting migration 计数偏移
            j = 0  # 连接盘的数量

            disk0_capacity = 0  # total capacity  总容量
            disk0_usage = 0  # have been used  已使用
            disk1_capacity = 0
            disk1_usage = 0

            for i in range(0, Disk_number):
                if i == 0:
                    a = Hard_segmentation[k + 1].strip().split()
                    if len(a) != 1:
                        if a[1].count('raid') == 1:
                            self.Get_back[4] = 1  # 检测是否组RAID '1'表示组了
                    else:
                        self.Get_back[4] = 0
                    if a[0].count('mmcblk') == 1:
                        continue
                    name0 = a[0]

                else:
                    a = Hard_segmentation[k + 1].strip().split()
                    if a[0].count('mmcblk') == 1:
                        continue

                    if len(a) != 1:
                        if a[1].count('raid') == 1:
                            self.Get_back[4] = 1  # 检测是否组RAID '1'表示组了
                    else:
                        self.Get_back[4] = 0
                flgh = 0

                j = j + 1

                if len(a) == 1:
                    disk_partition_Number = Hard_capacity1.count('─' + a[0])
                    self.Get_back[4] = 0
                else:
                    if a[1].count('raid') == 0:
                        self.Get_back[4] = 0
                        disk_partition_Number = Hard_capacity1.count('─' + a[0])
                    else:
                        disk_partition_Number = 1
                        self.Get_back[4] = 1

                if disk_partition_Number == 0:
                    disk_partition_Number = 1
                    flgh = 1

                for i1 in range(0, disk_partition_Number):

                    if disk_partition_Number > 0 and flgh == 0:
                        Partition_data_split = ' '.join(Hard_segmentation[i1 + 2 + k].split()).split(' ')
                    else:
                        Partition_data_split = ' '.join(Hard_segmentation[i1 + 1 + k].split()).split(' ')
                    if (len(Partition_data_split) <= 5 and len(Partition_data_split) > 0):
                        name = re.sub('[├─└]', '', Partition_data_split[0])
                        if (len(Partition_data_split) == 1):
                            # print("%s The drive letter has no partition\r\n"%(name))    
                            self.flag = 0
                        else:
                            # print ("%s This drive letter is not mounted\n"%(name))
                            self.flag = 1  # 检测是否挂载盘 ‘1’表示没有挂载
                        # continue
                    else:
                        # print ("%s The drive letter is properly mounted\n"%(re.sub('[├─└]','',Partition_data_split[0])))                       
                        if disk_partition_Number > 0 and name0 == a[0] or self.Get_back[4] == 1:
                            p = os.popen("df -h " + Partition_data_split[len(Partition_data_split) - 1])
                            i2 = 0
                            while 1:
                                i2 = i2 + 1
                                line = p.readline()
                                if i2 == 2:
                                    Capacity = line.split()[1]  # Total cost of the partition 分区总值
                                    x = int(re.sub('[A-Za-z]', '', Capacity))
                                    disk0_capacity = disk0_capacity + x
                                    Capacity = "".join(list(filter(str.isdigit, Capacity)))
                                    Capacity_usage = line.split()[2]  # Partition memory usage 分区使用内存
                                    if (Capacity_usage.count('G')):
                                        x = float(re.sub('[A-Z]', '', Capacity_usage))
                                        disk0_usage = disk0_usage + x
                                        break
                                    else:
                                        x = float(re.sub('[A-Z]', '', Capacity_usage)) / 1024
                                        disk0_usage = disk0_usage + x
                                        break
                        else:
                            p = os.popen("df -h " + Partition_data_split[len(Partition_data_split) - 1])
                            i2 = 0
                            while 1:
                                i2 = i2 + 1
                                line = p.readline()
                                if i2 == 2:
                                    Capacity = line.split()[1]  # Total cost of the partition 分区总值
                                    x = int(re.sub('[A-Za-z]', '', Capacity))
                                    disk1_capacity = disk1_capacity + x

                                    Capacity_usage = line.split()[2]  # Partition memory usage 分区使用内存
                                    if (Capacity_usage.count('G')):
                                        x = float(re.sub('[A-Z]', '', Capacity_usage))
                                        disk1_usage = disk1_usage + x
                                        break
                                    else:
                                        x = float(re.sub('[A-Z]', '', Capacity_usage)) / 1024
                                        disk1_usage = disk1_usage + x
                                        break

                if flgh == 0:
                    k = k + disk_partition_Number + 1
                else:
                    k = k + disk_partition_Number

                if j == 1 and len(Partition_data_split) > 5:
                    self.flag = 0
            if self.Get_back[4] == 1:
                disk1_capacity = disk0_capacity / 2
                disk0_capacity = disk1_capacity
                disk1_usage = disk0_usage / 2
                disk0_usage = disk1_usage

            if (disk0_capacity == 0) and (disk1_capacity == 0):
                self.Get_back = [disk0_capacity, disk1_capacity, disk0_usage, disk1_usage, self.Get_back[4]]
            elif disk0_capacity == 0 and disk1_capacity != 0:
                disk1_usage = round(disk1_usage / disk1_capacity * 100, 0)
                self.Get_back = [disk0_capacity, disk1_capacity, disk0_usage, disk1_usage, self.Get_back[4]]
            elif disk0_capacity != 0 and disk1_capacity == 0:
                disk0_usage = round(disk0_usage / disk0_capacity * 100, 0)
                self.Get_back = [disk0_capacity, disk1_capacity, disk0_usage, disk1_usage, self.Get_back[4]]
            else:
                disk0_usage = round(disk0_usage / disk0_capacity * 100, 0)
                disk1_usage = round(disk1_usage / disk1_capacity * 100, 0)
                self.Get_back = [disk0_capacity, disk1_capacity, disk0_usage, disk1_usage, self.Get_back[4]]

            time.sleep(1.5)
