"""
FPS Monitor Overlay - Main Entry Point

A hardware monitoring overlay for Windows 11 that displays:
- CPU temperature, usage, and clock speed
- GPU temperature, usage, and clock speed  
- RAM usage
- Fan speeds (RPM)

The overlay stays on top of fullscreen applications.

Controls:
- F12: Toggle overlay visibility
- Ctrl+Shift+Q: Exit application
- Drag with mouse to reposition

Requirements:
- For full hardware monitoring, install LibreHardwareMonitor
  and run it alongside this application.
- NVIDIA GPU stats work automatically via NVML.

Usage:
    python main.py [--config CONFIG_FILE]

Run as Administrator for best hardware monitoring access.
"""

import sys
import os
import json
import argparse
import ctypes
import subprocess
import time
from pathlib import Path


def is_hwinfo_running() -> bool:
    """Check if HWiNFO64 is running."""
    try:
        output = subprocess.check_output(
            'tasklist /FI "IMAGENAME eq HWiNFO64.exe" /NH',
            shell=True, text=True
        )
        return "HWiNFO64.exe" in output
    except Exception:
        return False


def find_hwinfo_path() -> str:
    """Find HWiNFO64 installation path."""
    common_paths = [
        r"C:\Program Files\HWiNFO64\HWiNFO64.exe",
        r"C:\Program Files (x86)\HWiNFO64\HWiNFO64.exe",
        os.path.expanduser(r"~\Desktop\HWiNFO64\HWiNFO64.exe"),
        os.path.expanduser(r"~\Downloads\HWiNFO64\HWiNFO64.exe"),
    ]
    for path in common_paths:
        if os.path.exists(path):
            return path
    return None


def launch_hwinfo():
    """Launch HWiNFO64 if not running."""
    if is_hwinfo_running():
        return True
    
    print("[!!] HWiNFO64 is not running")
    hwinfo_path = find_hwinfo_path()
    
    if hwinfo_path:
        print(f"     Found HWiNFO64 at: {hwinfo_path}")
        print("     Launching HWiNFO64...")
        try:
            subprocess.Popen([hwinfo_path], shell=True)
            time.sleep(3)  # Wait for HWiNFO to start
            if is_hwinfo_running():
                print("[OK] HWiNFO64 started successfully")
                print("     NOTE: Enable 'Shared Memory Support' in HWiNFO Settings")
                return True
        except Exception as e:
            print(f"     Failed to launch: {e}")
    else:
        print("     HWiNFO64 not found. Please install from:")
        print("     https://www.hwinfo.com/download/")
    
    return False


def is_admin() -> bool:
    """Check if running with administrator privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def load_config(config_path: str = None) -> dict:
    """Load configuration with a dynamic path strategy.

    Priority:
    1) --config CLI argument (explicit path)
    2) FPS_OVERLAY_CONFIG env var (explicit path)
    3) Existing config.json in %APPDATA%/fps-overlay
    4) Existing config.json next to the executable (frozen) or source (dev)
    If none exist, we use %APPDATA%/fps-overlay/config.json as the default target for saves.
    """
    # 1) CLI-provided path
    if config_path:
        chosen_path = Path(config_path)
    else:
        # 2) Environment override
        env_path = os.environ.get("FPS_OVERLAY_CONFIG")
        if env_path:
            chosen_path = Path(env_path)
        else:
            # Common base directories
            appdata_dir = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "fps-overlay"
            appdata_cfg = appdata_dir / "config.json"

            # 3) Prefer existing config in AppData
            if appdata_cfg.exists():
                chosen_path = appdata_cfg
            else:
                # 4) Fallback to local directory
                if getattr(sys, "frozen", False):
                    base_dir = Path(sys.argv[0]).resolve().parent
                else:
                    base_dir = Path(__file__).parent
                local_cfg = base_dir / "config.json"
                if local_cfg.exists():
                    chosen_path = local_cfg
                else:
                    # Default target for first-time save
                    chosen_path = appdata_cfg
    
    config = {}
    
    try:
        with open(chosen_path, 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f"Config file not found: {chosen_path}")
        print("Using default configuration.")
    except json.JSONDecodeError as e:
        print(f"Error parsing config file: {e}")
        print("Using default configuration.")
    
    # Keep track of where the config came from for saving later
    config["__config_path__"] = str(chosen_path)
    return config


def print_startup_info():
    """Print startup information."""
    print("=" * 50)
    print("     FPS Monitor Overlay for Windows 11")
    print("=" * 50)
    print()
    
    if is_admin():
        print("[OK] Running as Administrator")
    else:
        print("[!!] Not running as Administrator")
        print("     Some hardware sensors may not be accessible.")
    print()
    
    # Check and launch HWiNFO64
    if is_hwinfo_running():
        print("[OK] HWiNFO64 is running")
    else:
        launch_hwinfo()
    print()
    
    print("Controls:")
    print("  F12          - Toggle overlay visibility")
    print("  Ctrl+Shift+Q - Exit application")
    print("  Mouse drag   - Reposition overlay")
    print()
    print("=" * 50)
    print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="FPS Monitor Overlay for Windows 11"
    )
    parser.add_argument(
        '--config', '-c',
        type=str,
        default=None,
        help='Path to configuration JSON file'
    )
    parser.add_argument(
        '--silent', '-s',
        action='store_true',
        help='Silent mode (no startup messages)'
    )
    
    args = parser.parse_args()
    
    if not args.silent:
        print_startup_info()
    
    # Load configuration
    config = load_config(args.config)
    
    # Import and run overlay
    from overlay import OverlayApp
    
    app = OverlayApp(config)
    
    try:
        sys.exit(app.run())
    except KeyboardInterrupt:
        print("\nShutting down...")
        app.quit()


if __name__ == "__main__":
    main()
