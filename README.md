
# FPS Monitor Overlay (Windows)

## Features
- CPU/GPU usage, temps, clocks, fan RPM, RAM usage
- FPS from HWiNFO shared memory (when enabled)
- Drag to reposition; stays on top of fullscreen apps
- Toggle/exit via hotkeys and system tray

## Requirements
- Windows
- Python 3.9+ recommended
- HWiNFO64 (for shared memory sensors/FPS) with “Shared Memory Support” enabled
- (Optional but recommended) LibreHardwareMonitor or OpenHardwareMonitor running
- NVIDIA GPUs: NVML bundled with drivers (auto-used if available)

Python deps: `PyQt6`, `psutil`, `wmi`, `pywin32`, `keyboard` (@requirements.txt)

Install:
```bash
pip install -r requirements.txt
```

## Config (config.json)
- `position_x`/`position_y`: starting overlay position (pixels)
- `update_interval`: refresh in ms
- `background_opacity`: 0–1
- `background_color`: `R, G, B` string
- `text_color`: label color
- `toggle_hotkey` / `exit_hotkey`: global hotkeys
- `show_full_device_names`: true to show full CPU/GPU names, false for generic

## Running
- Double-click run_overlay.bat (Run as Administrator recommended), or `python main.py`

## Controls
- F12: toggle overlay (default)
- Ctrl+Shift+Q: exit (default)
- Drag with mouse: move overlay