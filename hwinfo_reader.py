"""
HWiNFO64 Shared Memory Reader
HWiNFO64 can share sensor data via shared memory - no WMI needed.
This provides excellent AMD Ryzen support.
"""

import ctypes
from ctypes import *
import mmap
import struct
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

# HWiNFO Shared Memory structures
HWINFO_SENSORS_SM_NAME = "Global\\HWiNFO_SENS_SM2"
HWINFO_SENSORS_SM_MUTEX = "Global\\HWiNFO_SM2_MUTEX"

# Sensor types
SENSOR_TYPE_NONE = 0
SENSOR_TYPE_TEMP = 1
SENSOR_TYPE_VOLT = 2
SENSOR_TYPE_FAN = 3
SENSOR_TYPE_CURRENT = 4
SENSOR_TYPE_POWER = 5
SENSOR_TYPE_CLOCK = 6
SENSOR_TYPE_USAGE = 7
SENSOR_TYPE_OTHER = 8


@dataclass
class HWiNFOSensor:
    """Represents a single sensor reading."""
    id: int
    name: str
    label: str
    unit: str
    value: float
    sensor_type: int


class HWiNFOReader:
    """
    Reads sensor data from HWiNFO64 shared memory.
    """
    def __init__(self):
        self.handle = None
        self.map_address = None
        self.kernel32 = None
        self.initialized = False
        self._init_shared_memory()

    def _init_shared_memory(self):
        """Initialize shared memory access using Windows API."""
        import ctypes
        from ctypes import c_void_p

        # Windows API constants
        FILE_MAP_READ = 0x0004
        
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenFileMappingW.restype = c_void_p
        kernel32.MapViewOfFile.restype = c_void_p

        sm_name = "Global\\HWiNFO_SENS_SM2"

        # Clean up any previous mapping
        self._close()

        try:
            # Open the file mapping
            self.handle = kernel32.OpenFileMappingW(FILE_MAP_READ, False, sm_name)
            if not self.handle:
                return
            
            # Map the entire file
            self.map_address = kernel32.MapViewOfFile(self.handle, FILE_MAP_READ, 0, 0, 0)
            if not self.map_address:
                kernel32.CloseHandle(self.handle)
                return
            
            self.initialized = True
            self.kernel32 = kernel32

        except Exception:
            self.sm = None

    def _close(self):
        """Close shared memory mapping."""
        if getattr(self, "map_address", None) and getattr(self, "kernel32", None):
            try:
                self.kernel32.UnmapViewOfFile(self.map_address)
            except Exception:
                pass
        if getattr(self, "handle", None) and getattr(self, "kernel32", None):
            try:
                self.kernel32.CloseHandle(self.handle)
            except Exception:
                pass
        self.handle = None
        self.map_address = None
        self.initialized = False

    def _read_bytes(self, offset: int, size: int) -> bytes:
        """Read bytes from mapped memory."""
        if not self.initialized:
            return b''

        import ctypes
        buffer = (ctypes.c_char * size)()
        ctypes.memmove(buffer, self.map_address + offset, size)
        return bytes(buffer)

    def _ensure_initialized(self) -> bool:
        """Ensure shared memory is mapped; try re-init once if needed."""
        if self.initialized:
            return True
        self._init_shared_memory()
        return self.initialized

    def read_sensors(self) -> List[HWiNFOSensor]:
        """Read all sensors from shared memory."""
        sensors = []

        if not self._ensure_initialized():
            return sensors

        try:
            # Read header (48 bytes)
            header = self._read_bytes(0, 48)
            if len(header) < 48:
                # Try re-init once if header is short
                self._close()
                if not self._ensure_initialized():
                    return sensors
                header = self._read_bytes(0, 48)
                if len(header) < 48:
                    return sensors

            signature = struct.unpack('<I', header[0:4])[0]

            # Verify signature "HWiS"
            if signature != 0x53695748:  # "HWiS" in little endian
                # Reinit once in case HWiNFO restarted
                self._close()
                if not self._ensure_initialized():
                    return sensors
                header = self._read_bytes(0, 48)
                if len(header) < 48:
                    return sensors
                return sensors

            sensor_offset = struct.unpack('<I', header[20:24])[0]
            sensor_size = struct.unpack('<I', header[24:28])[0]
            sensor_count = struct.unpack('<I', header[28:32])[0]

            reading_offset = struct.unpack('<I', header[32:36])[0]
            reading_size = struct.unpack('<I', header[36:40])[0]
            reading_count = struct.unpack('<I', header[40:44])[0]

            # Read sensor names (name at offset 8, 128 bytes)
            sensor_names = {}
            for i in range(sensor_count):
                sensor_data = self._read_bytes(sensor_offset + i * sensor_size, min(sensor_size, 200))
                if len(sensor_data) < 136:
                    continue
                name = sensor_data[8:136].split(b'\x00')[0].decode('utf-8', errors='ignore')
                sensor_names[i] = name
            
            # Read readings - HWiNFO v2 structure:
            # 0-3: sensor_type, 4-7: sensor_index, 8-11: reading_id
            # 12-139: label (128 bytes), 140-267: user_label (128 bytes)
            # 268-283: unit (16 bytes), 284-291: value (double)
            for i in range(reading_count):
                reading_data = self._read_bytes(reading_offset + i * reading_size, min(reading_size, 300))
                if len(reading_data) < 292:
                    continue
                
                sensor_type = struct.unpack('<I', reading_data[0:4])[0]
                sensor_index = struct.unpack('<I', reading_data[4:8])[0]
                reading_id = struct.unpack('<I', reading_data[8:12])[0]
                
                label = reading_data[12:140].split(b'\x00')[0].decode('utf-8', errors='ignore')
                unit = reading_data[268:284].split(b'\x00')[0].decode('utf-8', errors='ignore')
                value = struct.unpack('<d', reading_data[284:292])[0]
                
                sensor_name = sensor_names.get(sensor_index, "Unknown")
                
                sensors.append(HWiNFOSensor(
                    id=reading_id,
                    name=sensor_name,
                    label=label,
                    unit=unit,
                    value=value,
                    sensor_type=sensor_type
                ))
                
        except Exception as e:
            pass
        
        return sensors
    
    def get_cpu_stats(self) -> Dict[str, Any]:
        """Get CPU-related sensor data."""
        stats = {}
        sensors = self.read_sensors()
        
        best_clock = 0.0
        for sensor in sensors:
            name_lower = sensor.name.lower()
            label_lower = sensor.label.lower()
            
            # CPU Temperature - look for Tctl/Tdie or "CPU" temp
            if sensor.sensor_type == SENSOR_TYPE_TEMP:
                if 'cpu_temp' not in stats:
                    # AMD Ryzen: "CPU Tctl/Tdie" under CPU sensor
                    if 'ryzen' in name_lower and 'tctl' in label_lower:
                        stats['cpu_temp'] = sensor.value
                    # Package / CPU
                    elif 'cpu' in label_lower or 'package' in label_lower:
                        stats['cpu_temp'] = sensor.value
            
            # CPU Clock - look for effective clock or core clock
            elif sensor.sensor_type == SENSOR_TYPE_CLOCK:
                if 'ryzen' in name_lower or 'cpu' in name_lower:
                    if 'core' in label_lower and sensor.value and sensor.value > 0:
                        if sensor.value > best_clock:
                            best_clock = sensor.value
            
            # CPU Fan - under motherboard sensor with "CPU" label
            elif sensor.sensor_type == SENSOR_TYPE_FAN:
                if 'cpu_fan' not in stats and ('cpu' in label_lower or 'pump' in label_lower):
                    if sensor.value > 0:
                        stats['cpu_fan'] = int(sensor.value)
        
        if best_clock > 0:
            stats['cpu_clock'] = best_clock
        return stats
    
    def get_gpu_stats(self) -> Dict[str, Any]:
        """Get GPU-related sensor data."""
        stats = {}
        sensors = self.read_sensors()

        # FPS is often under a separate "PresentMon" sensor group, not the GPU group.
        # Scan all sensors first for FPS-related labels.
        for sensor in sensors:
            label_lower = sensor.label.lower()
            if 'fps' in stats:
                break
            if 'framerate' in label_lower or 'fullscreen fps' in label_lower or label_lower.strip() == 'fps':
                if sensor.value and sensor.value > 0:
                    stats['fps'] = sensor.value

        for sensor in sensors:
            name_lower = sensor.name.lower()
            label_lower = sensor.label.lower()
            
            # Prefer discrete GPUs; avoid hardcoded model names
            is_gpu = (
                'radeon' in name_lower or
                'geforce' in name_lower or
                'nvidia' in name_lower or
                'rtx' in name_lower or
                'gtx' in name_lower or
                'arc' in name_lower or
                'rx ' in name_lower or
                name_lower.strip().startswith('rx')
            )
            if not is_gpu:
                continue
            
            # GPU Temperature
            if sensor.sensor_type == SENSOR_TYPE_TEMP:
                if 'gpu_temp' not in stats and ('gpu' in label_lower or 'gpu' in name_lower):
                    stats['gpu_temp'] = sensor.value
            
            # GPU Clock
            elif sensor.sensor_type == SENSOR_TYPE_CLOCK:
                if 'gpu_clock' not in stats and ('gpu' in label_lower or 'core' in label_lower):
                    stats['gpu_clock'] = sensor.value
            
            # GPU Fan
            elif sensor.sensor_type == SENSOR_TYPE_FAN:
                if 'gpu_fan' not in stats and ('gpu' in label_lower or 'fan' in label_lower):
                    stats['gpu_fan'] = int(sensor.value)
            
            # GPU Usage
            elif sensor.sensor_type == SENSOR_TYPE_USAGE:
                if 'gpu_usage' not in stats and (('gpu' in label_lower and 'core' in label_lower) or 'd3d 3d' in label_lower):
                    stats['gpu_usage'] = sensor.value
            
            # FPS is handled above (global scan) to avoid missing PresentMon sensors.
        
        return stats
    
    def get_all_stats(self) -> Dict[str, Any]:
        """Get all relevant hardware stats."""
        stats = {}
        stats.update(self.get_cpu_stats())
        stats.update(self.get_gpu_stats())
        return stats
    
    def list_all_sensors(self) -> List[Dict]:
        """List all available sensors (for debugging)."""
        sensors = self.read_sensors()
        return [
            {
                'name': s.name,
                'label': s.label,
                'value': s.value,
                'unit': s.unit,
                'type': s.sensor_type
            }
            for s in sensors
        ]


# Test
if __name__ == "__main__":
    print("Testing HWiNFO64 Shared Memory Reader...")
    print()
    
    reader = HWiNFOReader()
    
    if reader.initialized:
        print("HWiNFO64 Shared Memory: Connected!")
        print()
        
        print("CPU Stats:")
        cpu_stats = reader.get_cpu_stats()
        for key, value in cpu_stats.items():
            print(f"  {key}: {value}")
        
        print()
        print("GPU Stats:")
        gpu_stats = reader.get_gpu_stats()
        for key, value in gpu_stats.items():
            print(f"  {key}: {value}")
        
        print()
        print("All Sensors (first 20):")
        for sensor in reader.list_all_sensors()[:20]:
            print(f"  [{sensor['type']}] {sensor['name']} / {sensor['label']}: {sensor['value']} {sensor['unit']}")
    else:
        print("HWiNFO64 Shared Memory: NOT AVAILABLE")
        print()
        print("To enable:")
        print("1. Download HWiNFO64: https://www.hwinfo.com/download/")
        print("2. Run HWiNFO64")
        print("3. Go to Settings -> Sensor Settings")
        print("4. Enable 'Shared Memory Support'")
        print("5. Click OK and restart HWiNFO64")
