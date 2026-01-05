import json
import logging
import os
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import psutil
from psutil._common import sdiskusage


# =============================================================================
# Configuration (can be overridden via environment variables)
# =============================================================================

# Network interface to monitor (e.g., 'eth0', 'end0', 'wlan0')
NETWORK_INTERFACE = os.environ.get('NAS_NETWORK_INTERFACE', 'end0')

# Disk device IDs to monitor (e.g., 'sda', 'sdb', 'nvme0n1')
DISK0_ID = os.environ.get('NAS_DISK0_ID', 'sda')
DISK1_ID = os.environ.get('NAS_DISK1_ID', 'sdb')

# Update interval in seconds
UPDATE_INTERVAL = int(os.environ.get('NAS_UPDATE_INTERVAL', '1'))

# Disk temperature update interval (smartctl is slow, so update less frequently)
DISK_TEMP_UPDATE_INTERVAL = int(os.environ.get('NAS_DISK_TEMP_INTERVAL', '30'))

# lsblk cache TTL (disk structure rarely changes, so cache results)
LSBLK_CACHE_TTL = int(os.environ.get('NAS_LSBLK_CACHE_TTL', '10'))


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class Disk:
    """Represents a storage disk with capacity, usage, and temperature info."""

    id: str
    capacity: int = 0
    available: int = 0
    used: int = 0
    used_percentage: float = 0.0
    temperature: int = 0

    children: List[Dict[str, Any]] = field(default_factory=list)
    _last_temp_update: float = field(default=0.0, repr=False)

    def update(self) -> None:
        """Update disk capacity, usage, and temperature."""
        self.calculate_capacity_and_usage()
        # Only update temperature if enough time has passed (smartctl is slow)
        now = time.time()
        if now - self._last_temp_update >= DISK_TEMP_UPDATE_INTERVAL:
            self.update_temperature()
            self._last_temp_update = now

    def calculate_capacity_and_usage(self) -> None:
        """Calculate total capacity and usage from child partitions."""
        try:
            self.capacity = sum(int(child['fssize']) for child in self.children if child.get('fssize'))
            self.available = sum(int(child['fsavail']) for child in self.children if child.get('fsavail'))
            self.used = sum(int(child['fsused']) for child in self.children if child.get('fsused'))
            if self.capacity > 0:
                self.used_percentage = 100 * self.used / self.capacity
            else:
                self.used_percentage = 0.0
        except (TypeError, ValueError) as e:
            logging.debug(f"Error calculating disk usage for {self.id}: {e}")

    def update_temperature(self) -> None:
        """Update disk temperature from S.M.A.R.T. data with graceful fallback."""
        try:
            smart_data = self.get_smart_data()
            temp_data = smart_data.get('temperature')
            if temp_data and isinstance(temp_data, dict):
                self.temperature = temp_data.get('current', 0)
            else:
                self.temperature = 0
        except Exception as e:
            logging.debug(f"Error reading temperature for {self.id}: {e}")
            # Keep previous temperature (already initialized to 0)

    def get_smart_data(self) -> Dict[str, Any]:
        """
        Get S.M.A.R.T. data for the disk.

        Returns:
            Dictionary containing S.M.A.R.T. data, or empty dict on failure.
        """
        try:
            result = subprocess.run(
                ['smartctl', '-A', f'/dev/{self.id}', '--json'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 or result.stdout:
                return json.loads(result.stdout)
        except subprocess.TimeoutExpired:
            logging.warning(f"smartctl timeout for {self.id}")
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logging.debug(f"smartctl error for {self.id}: {e}")
        return {}


@dataclass
class StorageParameters:
    """Storage parameters for monitoring multiple disks."""

    disk0: Disk
    disk1: Disk
    raid: bool = False
    _lsblk_cache: Optional[Dict[str, Any]] = field(default=None, repr=False)
    _lsblk_cache_time: float = field(default=0.0, repr=False)

    def _get_lsblk_data(self) -> Optional[Dict[str, Any]]:
        """Get lsblk data with caching to reduce subprocess overhead."""
        now = time.time()
        if self._lsblk_cache is not None and (now - self._lsblk_cache_time) < LSBLK_CACHE_TTL:
            return self._lsblk_cache

        try:
            result = subprocess.run(
                ['lsblk', '-b', '-o', 'NAME,FSTYPE,FSSIZE,FSAVAIL,FSUSED', '--json'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                logging.debug(f"lsblk returned non-zero: {result.returncode}")
                return self._lsblk_cache  # Return stale cache on error

            self._lsblk_cache = json.loads(result.stdout)
            self._lsblk_cache_time = now
            return self._lsblk_cache
        except subprocess.TimeoutExpired:
            logging.warning("lsblk timeout")
            return self._lsblk_cache
        except json.JSONDecodeError as e:
            logging.debug(f"Error parsing lsblk output: {e}")
            return self._lsblk_cache

    def update(self) -> None:
        """Update storage parameters from lsblk output."""
        data = self._get_lsblk_data()
        if data is None:
            return

        blockdevices = data.get('blockdevices', [])
        if not blockdevices:
            return

        try:
            # Check for RAID volumes
            for device in blockdevices:
                device_name = device.get('name')
                if device_name in [self.disk0.id, self.disk1.id]:
                    fstype = device.get('fstype') or ''
                    if 'raid' in fstype.lower():
                        self.raid = True
                        break

            # Calculate capacity and usage of each disk
            for device in blockdevices:
                device_name = device.get('name')
                for disk in [self.disk0, self.disk1]:
                    if device_name == disk.id:
                        if device.get('children'):
                            disk.children = device['children']
                            disk.update()
        except (KeyError, TypeError) as e:
            logging.debug(f"Error processing lsblk data: {e}")


@dataclass
class SystemParameters:
    """System parameters for monitoring CPU, memory, disk, and network."""

    disk_parameters: Optional[StorageParameters] = None
    ip_address: str = '127.0.0.1'
    cpu_usage: float = 0.0
    cpu_temperature: float = 0.0
    rx_speed: float = 0.0
    tx_speed: float = 0.0
    memory_usage: float = 0.0
    disk_usage: Optional[sdiskusage] = None

    network_interface: str = field(default_factory=lambda: NETWORK_INTERFACE)
    update_interval: int = field(default_factory=lambda: UPDATE_INTERVAL)

    flag: int = 0  # 0 = unpartitioned, >0 = detected but not installed

    # Thread lock for safe access to shared state from multiple threads
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self) -> None:
        """Initialize storage parameters and disk usage with configured values."""
        if not self.disk_parameters:
            self.disk_parameters = StorageParameters(Disk(DISK0_ID), Disk(DISK1_ID))
        if not self.disk_usage:
            self.disk_usage = sdiskusage(total=0, used=0, free=0, percent=0)

    def update(self) -> None:
        """Main update loop for all system parameters."""
        while True:
            try:
                # Collect values first (some operations like network speed take time)
                if self.disk_parameters is not None:
                    self.disk_parameters.update()
                self._update_ip_address()
                self._update_cpu_usage()
                self._update_temperature()
                self._update_network_speed()
                self._update_memory_usage()
                self._update_disk_usage()

                logging.debug(self)

                time.sleep(self.update_interval)
            except Exception:
                logging.exception('Parameter update failed')

    def get_snapshot(self) -> dict:
        """Get a thread-safe snapshot of current system parameters.

        Returns:
            Dictionary with current values, safe to read from other threads.
        """
        with self._lock:
            return {
                'cpu_usage': self.cpu_usage,
                'memory_usage': self.memory_usage,
                'cpu_temperature': self.cpu_temperature,
                'rx_speed': self.rx_speed,
                'tx_speed': self.tx_speed,
                'ip_address': self.ip_address,
                'disk_usage': self.disk_usage,
                'disk_parameters': self.disk_parameters,
                'flag': self.flag,
            }

    def _update_ip_address(self) -> None:
        """Update IP address by attempting connection to external host."""
        s = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(2)
            s.connect_ex(('8.8.8.8', 80))
            self.ip_address = s.getsockname()[0]
        except (socket.error, OSError) as e:
            logging.debug(f"Error getting IP address: {e}")
            # Keep previous IP address
        finally:
            if s is not None:
                s.close()

    def _update_temperature(self) -> None:
        """Update CPU temperature from thermal zone."""
        try:
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                temp = float(f.read().strip()) / 1000
                self.cpu_temperature = temp
        except (FileNotFoundError, ValueError) as e:
            logging.debug(f"Error reading CPU temperature: {e}")
            # Keep previous temperature

    @staticmethod
    def _get_network_bytes(interface: str, is_rx: bool) -> Optional[int]:
        """
        Get current network byte count from /proc/net/dev.

        Args:
            interface: Network interface name.
            is_rx: True for received bytes, False for transmitted bytes.

        Returns:
            Byte count, or None if interface not found.
        """
        # RX is column 0, TX is column 8
        column = 0 if is_rx else 8

        try:
            with open('/proc/net/dev') as f:
                for line in f:
                    if ':' in line:
                        iface, stats = line.split(':', 1)
                        if iface.strip() == interface:
                            parts = stats.split()
                            if len(parts) > column:
                                return int(parts[column])
                            return None
        except (FileNotFoundError, ValueError, IndexError) as e:
            logging.debug(f"Error reading network stats: {e}")
        return None

    def _update_network_speed(self) -> None:
        """Update network RX and TX speeds."""
        sample_time = 0.1

        # Get initial readings
        rx_start = self._get_network_bytes(self.network_interface, is_rx=True)
        tx_start = self._get_network_bytes(self.network_interface, is_rx=False)

        if rx_start is None or tx_start is None:
            return

        time.sleep(sample_time)

        # Get final readings
        rx_end = self._get_network_bytes(self.network_interface, is_rx=True)
        tx_end = self._get_network_bytes(self.network_interface, is_rx=False)

        if rx_end is None or tx_end is None:
            return

        self.rx_speed = (rx_end - rx_start) / sample_time
        self.tx_speed = (tx_end - tx_start) / sample_time

    def _update_cpu_usage(self) -> None:
        """Update CPU usage percentage."""
        self.cpu_usage = psutil.cpu_percent()

    def _update_memory_usage(self) -> None:
        """Update memory usage percentage."""
        self.memory_usage = psutil.virtual_memory().percent

    def _update_disk_usage(self) -> None:
        """Update root filesystem disk usage."""
        try:
            self.disk_usage = psutil.disk_usage('/')
        except OSError as e:
            logging.debug(f"Error getting disk usage: {e}")
