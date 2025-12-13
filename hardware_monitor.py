"""
Hardware monitoring module for CPU, GPU, RAM temperatures, fan speeds, and clock speeds.
Uses multiple backends: WMI, pynvml, psutil, and LibreHardwareMonitor.
"""

import os
import ctypes
import subprocess
import json
import struct
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
import psutil

# Try clr for .NET interop (LibreHardwareMonitor direct access)
try:
    import clr
    CLR_AVAILABLE = True
except ImportError:
    CLR_AVAILABLE = False

# Try importing optional dependencies
try:
    import wmi
    WMI_AVAILABLE = True
except ImportError:
    WMI_AVAILABLE = False

try:
    import pynvml
    NVML_AVAILABLE = True
except ImportError:
    NVML_AVAILABLE = False


@dataclass
class HardwareStats:
    """Container for all hardware statistics."""
    # CPU
    cpu_name: Optional[str] = None
    cpu_temp: Optional[float] = None
    cpu_usage: float = 0.0
    cpu_clock: Optional[float] = None
    cpu_fan_rpm: Optional[int] = None
    
    # GPU
    gpu_name: Optional[str] = None
    gpu_temp: Optional[float] = None
    gpu_usage: Optional[float] = None
    gpu_clock: Optional[float] = None
    gpu_memory_used: Optional[float] = None
    gpu_memory_total: Optional[float] = None
    gpu_fan_rpm: Optional[int] = None
    gpu_fan_percent: Optional[float] = None
    gpu_power: Optional[float] = None
    
    # RAM
    ram_usage: float = 0.0
    ram_used_gb: float = 0.0
    ram_total_gb: float = 0.0
    
    # FPS (placeholder - actual FPS requires hooking into applications)
    fps: Optional[int] = None


class NvidiaMonitor:
    """Monitor NVIDIA GPU using pynvml."""
    
    def __init__(self):
        self.initialized = False
        self.handle = None
        
        if NVML_AVAILABLE:
            try:
                pynvml.nvmlInit()
                self.handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                self.initialized = True
            except Exception:
                pass
    
    def get_stats(self) -> Dict[str, Any]:
        """Get NVIDIA GPU statistics."""
        stats = {}
        
        if not self.initialized or not self.handle:
            return stats
        
        try:
            # Temperature
            temp = pynvml.nvmlDeviceGetTemperature(self.handle, pynvml.NVML_TEMPERATURE_GPU)
            stats['gpu_temp'] = temp
        except Exception:
            pass
        
        try:
            # GPU utilization
            util = pynvml.nvmlDeviceGetUtilizationRates(self.handle)
            stats['gpu_usage'] = util.gpu
        except Exception:
            pass
        
        try:
            # Memory
            mem = pynvml.nvmlDeviceGetMemoryInfo(self.handle)
            stats['gpu_memory_used'] = mem.used / (1024 ** 3)  # Convert to GB
            stats['gpu_memory_total'] = mem.total / (1024 ** 3)
        except Exception:
            pass
        
        try:
            # Clock speeds
            clock = pynvml.nvmlDeviceGetClockInfo(self.handle, pynvml.NVML_CLOCK_GRAPHICS)
            stats['gpu_clock'] = clock
        except Exception:
            pass
        
        try:
            # Fan speed (percentage)
            fan = pynvml.nvmlDeviceGetFanSpeed(self.handle)
            stats['gpu_fan_percent'] = fan
        except Exception:
            pass
        
        return stats
    
    def shutdown(self):
        """Cleanup NVML."""
        if self.initialized:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass


class WMIMonitor:
    """Monitor hardware using WMI (Windows Management Instrumentation)."""
    
    def __init__(self):
        self.wmi_obj = None
        self.initialized = False
        self.ohm_available = False
        self.gpu_name = None
        self.cpu_name = None
        
        if WMI_AVAILABLE:
            try:
                self.wmi_obj = wmi.WMI()
                self.initialized = True
                
                # Get CPU name from WMI
                try:
                    for cpu in self.wmi_obj.Win32_Processor():
                        name = cpu.Name
                        if name:
                            # Extract model number
                            self.cpu_name = name
                            break
                except Exception:
                    pass
                
                # Get GPU name from WMI
                try:
                    for gpu in self.wmi_obj.Win32_VideoController():
                        name = gpu.Name
                        # Prefer discrete GPU over integrated
                        if name and ('Radeon RX' in name or 'GeForce' in name or 'Arc' in name):
                            self.gpu_name = name
                            break
                        elif name and not self.gpu_name:
                            self.gpu_name = name
                except Exception:
                    pass
                
                # Try to connect to OpenHardwareMonitor/LibreHardwareMonitor WMI namespace
                for namespace in ["root\\LibreHardwareMonitor", "root\\OpenHardwareMonitor"]:
                    try:
                        self.ohm_wmi = wmi.WMI(namespace=namespace)
                        # Test if it works by querying sensors
                        test = self.ohm_wmi.Sensor()
                        if test:
                            self.ohm_available = True
                            break
                    except Exception:
                        continue
            except Exception:
                pass
    
    def get_cpu_temp_from_wmi(self) -> Optional[float]:
        """Try to get CPU temp from standard WMI (works on some systems)."""
        if not self.initialized:
            return None
        try:
            # Try MSAcpi_ThermalZoneTemperature
            w = wmi.WMI(namespace="root\\wmi")
            temps = w.MSAcpi_ThermalZoneTemperature()
            if temps:
                # Temperature is in tenths of Kelvin
                kelvin = temps[0].CurrentTemperature / 10.0
                celsius = kelvin - 273.15
                if 0 < celsius < 150:  # Sanity check
                    return celsius
        except Exception:
            pass
        return None
    
    def get_cpu_temp_from_ohm(self) -> Optional[float]:
        """Get CPU temperature from OpenHardwareMonitor/LibreHardwareMonitor."""
        if not self.ohm_available:
            return None
        
        try:
            sensors = self.ohm_wmi.Sensor()
            for sensor in sensors:
                if sensor.SensorType == 'Temperature' and 'CPU' in sensor.Name:
                    if 'Package' in sensor.Name or 'Core' in sensor.Name:
                        return sensor.Value
        except Exception:
            pass
        
        return None
    
    def get_cpu_clock_from_ohm(self) -> Optional[float]:
        """Get CPU clock speed from OHM/LHM."""
        if not self.ohm_available:
            return None
        
        try:
            sensors = self.ohm_wmi.Sensor()
            for sensor in sensors:
                if sensor.SensorType == 'Clock' and 'CPU' in sensor.Name:
                    return sensor.Value
        except Exception:
            pass
        
        return None
    
    def get_fan_speeds_from_ohm(self) -> Dict[str, int]:
        """Get fan speeds from OHM/LHM."""
        fans = {}
        
        if not self.ohm_available:
            return fans
        
        try:
            sensors = self.ohm_wmi.Sensor()
            for sensor in sensors:
                if sensor.SensorType == 'Fan':
                    fans[sensor.Name] = int(sensor.Value) if sensor.Value else 0
        except Exception:
            pass
        
        return fans
    
    def get_all_ohm_stats(self) -> Dict[str, Any]:
        """Get all available stats from OHM/LHM."""
        stats = {}
        
        if not self.ohm_available:
            return stats
        
        try:
            sensors = self.ohm_wmi.Sensor()
            for sensor in sensors:
                name = sensor.Name if sensor.Name else ""
                stype = sensor.SensorType if sensor.SensorType else ""
                parent = str(sensor.Parent) if sensor.Parent else ""
                value = sensor.Value
                
                if value is None:
                    continue
                
                name_lower = name.lower()
                parent_lower = parent.lower()
                
                # Determine if this is a CPU or GPU sensor based on parent
                is_cpu_sensor = 'cpu' in parent_lower or 'ryzen' in parent_lower or 'intel' in parent_lower
                is_gpu_sensor = 'gpu' in parent_lower or 'radeon' in parent_lower or 'geforce' in parent_lower or 'amd radeon' in parent_lower
                
                # Temperature sensors
                if stype == 'Temperature':
                    # CPU temp: look for Tctl/Tdie (AMD) or Package (Intel)
                    if 'tctl' in name_lower or 'tdie' in name_lower or ('core' in name_lower and is_cpu_sensor):
                        if value > 0 and 'cpu_temp' not in stats:
                            stats['cpu_temp'] = value
                    # GPU temp
                    elif 'gpu' in name_lower and 'core' in name_lower:
                        stats['gpu_temp'] = value
                    elif is_gpu_sensor and 'core' in name_lower:
                        stats['gpu_temp'] = value
                
                # Clock speeds
                elif stype == 'Clock':
                    # CPU clock - look for core clocks that have valid values
                    if is_cpu_sensor and 'core' in name_lower:
                        if value and value > 0 and value == value:  # Check not nan
                            if 'cpu_clock' not in stats:
                                stats['cpu_clock'] = value
                    # GPU clock
                    elif 'gpu' in name_lower and 'core' in name_lower:
                        if value and value > 0 and value == value:
                            stats['gpu_clock'] = value
                    elif is_gpu_sensor and 'core' in name_lower:
                        if value and value > 0 and value == value:
                            stats['gpu_clock'] = value
                
                # Fan speeds
                elif stype == 'Fan':
                    if value and value > 0:
                        if 'cpu' in name_lower or is_cpu_sensor:
                            stats['cpu_fan_rpm'] = int(value)
                        elif 'gpu' in name_lower or is_gpu_sensor:
                            stats['gpu_fan_rpm'] = int(value)
                        elif 'fan' in name_lower:
                            # Generic fan - assign to first available
                            if 'cpu_fan_rpm' not in stats:
                                stats['cpu_fan_rpm'] = int(value)
                
                # GPU Load
                elif stype == 'Load':
                    if ('gpu' in name_lower and 'core' in name_lower) or (is_gpu_sensor and 'core' in name_lower):
                        stats['gpu_usage'] = value
                        
        except Exception as e:
            pass
        
        return stats
    
    def get_all_sensors_debug(self) -> List[Dict]:
        """Get all sensors for debugging."""
        sensors_list = []
        if not self.ohm_available:
            return sensors_list
        try:
            sensors = self.ohm_wmi.Sensor()
            for s in sensors:
                sensors_list.append({
                    'Name': s.Name,
                    'Type': s.SensorType,
                    'Value': s.Value,
                    'Parent': s.Parent
                })
        except Exception:
            pass
        return sensors_list


class HardwareMonitor:
    """Main hardware monitoring class that combines multiple backends."""
    
    def __init__(self):
        self.nvidia_monitor = NvidiaMonitor()
        self.wmi_monitor = WMIMonitor()
        self.hwinfo_reader = None
        self._last_stats = HardwareStats()
        
        # Try to initialize HWiNFO reader as alternative source
        try:
            from hwinfo_reader import HWiNFOReader
            # Keep the reader even if not initialized now; it can re-init later
            self.hwinfo_reader = HWiNFOReader()
        except Exception:
            pass
    
    def get_stats(self) -> HardwareStats:
        """Collect all hardware statistics."""
        stats = HardwareStats()
        
        # CPU Usage (always available via psutil)
        stats.cpu_usage = psutil.cpu_percent(interval=None)
        
        # RAM stats (always available via psutil)
        ram = psutil.virtual_memory()
        stats.ram_usage = ram.percent
        stats.ram_used_gb = ram.used / (1024 ** 3)
        stats.ram_total_gb = ram.total / (1024 ** 3)
        
        # Get CPU and GPU names from WMI
        if self.wmi_monitor.initialized:
            if self.wmi_monitor.cpu_name:
                stats.cpu_name = self.wmi_monitor.cpu_name
            if self.wmi_monitor.gpu_name:
                stats.gpu_name = self.wmi_monitor.gpu_name
        
        # Try to get data from OHM/LHM first (most comprehensive for AMD)
        if self.wmi_monitor.initialized:
            ohm_stats = self.wmi_monitor.get_all_ohm_stats()
            
            if 'cpu_temp' in ohm_stats:
                stats.cpu_temp = ohm_stats['cpu_temp']
            if 'cpu_clock' in ohm_stats:
                stats.cpu_clock = ohm_stats['cpu_clock']
            if 'cpu_fan_rpm' in ohm_stats:
                stats.cpu_fan_rpm = ohm_stats['cpu_fan_rpm']
            if 'gpu_temp' in ohm_stats:
                stats.gpu_temp = ohm_stats['gpu_temp']
            if 'gpu_clock' in ohm_stats:
                stats.gpu_clock = ohm_stats['gpu_clock']
            if 'gpu_usage' in ohm_stats:
                stats.gpu_usage = ohm_stats['gpu_usage']
            if 'gpu_fan_rpm' in ohm_stats:
                stats.gpu_fan_rpm = ohm_stats['gpu_fan_rpm']
            if 'gpu_power' in ohm_stats:
                stats.gpu_power = ohm_stats['gpu_power']
            
            # Fallback: try standard WMI for CPU temp if OHM didn't provide it
            if stats.cpu_temp is None:
                stats.cpu_temp = self.wmi_monitor.get_cpu_temp_from_wmi()
        
        # Get NVIDIA-specific stats (may override some values)
        if self.nvidia_monitor.initialized:
            nvidia_stats = self.nvidia_monitor.get_stats()
            
            if 'gpu_temp' in nvidia_stats:
                stats.gpu_temp = nvidia_stats['gpu_temp']
            if 'gpu_usage' in nvidia_stats:
                stats.gpu_usage = nvidia_stats['gpu_usage']
            if 'gpu_clock' in nvidia_stats:
                stats.gpu_clock = nvidia_stats['gpu_clock']
            if 'gpu_memory_used' in nvidia_stats:
                stats.gpu_memory_used = nvidia_stats['gpu_memory_used']
            if 'gpu_memory_total' in nvidia_stats:
                stats.gpu_memory_total = nvidia_stats['gpu_memory_total']
            if 'gpu_fan_percent' in nvidia_stats:
                stats.gpu_fan_percent = nvidia_stats['gpu_fan_percent']
        
        # Try HWiNFO64 as alternative source (fills in missing values)
        if self.hwinfo_reader:
            hwinfo_stats = self.hwinfo_reader.get_all_stats()
            
            # Fill in missing CPU stats
            if stats.cpu_temp is None and 'cpu_temp' in hwinfo_stats:
                stats.cpu_temp = hwinfo_stats['cpu_temp']
            if stats.cpu_clock is None and 'cpu_clock' in hwinfo_stats:
                stats.cpu_clock = hwinfo_stats['cpu_clock']
            if stats.cpu_fan_rpm is None and 'cpu_fan' in hwinfo_stats:
                stats.cpu_fan_rpm = hwinfo_stats['cpu_fan']
            
            # Fill in missing GPU stats
            if stats.gpu_temp is None and 'gpu_temp' in hwinfo_stats:
                stats.gpu_temp = hwinfo_stats['gpu_temp']
            if stats.gpu_usage is None and 'gpu_usage' in hwinfo_stats:
                stats.gpu_usage = hwinfo_stats['gpu_usage']
            if stats.gpu_clock is None and 'gpu_clock' in hwinfo_stats:
                stats.gpu_clock = hwinfo_stats['gpu_clock']
            if stats.gpu_fan_rpm is None and 'gpu_fan' in hwinfo_stats:
                stats.gpu_fan_rpm = hwinfo_stats['gpu_fan']
            
            # FPS from HWiNFO
            if 'fps' in hwinfo_stats:
                try:
                    fps_val = float(hwinfo_stats['fps'])
                    if fps_val > 1:
                        stats.fps = int(fps_val)
                except Exception:
                    pass
        
        self._last_stats = stats
        return stats
    
    def shutdown(self):
        """Clean up resources."""
        self.nvidia_monitor.shutdown()
    
    def get_status_info(self) -> Dict[str, bool]:
        """Get status of monitoring backends."""
        return {
            'nvml': self.nvidia_monitor.initialized,
            'wmi': self.wmi_monitor.initialized,
            'ohm_lhm': self.wmi_monitor.ohm_available if self.wmi_monitor.initialized else False,
        }
