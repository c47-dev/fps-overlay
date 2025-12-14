"""
Transparent overlay window for displaying hardware stats.
Uses PyQt6 with transparent, always-on-top, click-through window.
"""

import sys
import threading
import json
import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QGraphicsDropShadowEffect,
    QSystemTrayIcon, QMenu
)
from PyQt6.QtCore import Qt, QTimer, QPoint, pyqtSignal, QObject
from PyQt6.QtGui import (
    QFont, QColor, QIcon, QPixmap, QPainter, QMouseEvent, QKeySequence,
    QAction, QShortcut
)

from hardware_monitor import HardwareMonitor
from settings_dialog import SettingsDialog


class HotkeySignals(QObject):
    """Signals for hotkey events to communicate with Qt main thread."""
    toggle_signal = pyqtSignal()
    quit_signal = pyqtSignal()
    settings_signal = pyqtSignal()


class OverlayWidget(QWidget):
    """Main overlay widget displaying hardware statistics."""
    
    def __init__(self, config: dict = None):
        super().__init__()
        
        self.config = config or {}
        self.hardware_monitor = HardwareMonitor()
        self.dragging = False
        self.drag_position = QPoint()
        
        self.init_ui()
        self.setup_timer()
    
    def init_ui(self):
        """Initialize the user interface."""
        # Window flags for overlay behavior
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.X11BypassWindowManagerHint
        )
        
        # Transparent background
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Set initial position
        x = self.config.get('position_x', 10)
        y = self.config.get('position_y', 10)
        self.move(x, y)
        
        # Main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(2)
        
        # Create stat labels
        self.labels = {}
        
        stat_items = [
            ('fps', 'FPS'),
            ('cpu', 'CPU'),
            ('gpu', 'GPU'),
            ('ram', 'RAM'),
        ]
        
        for key, name in stat_items:
            label = self.create_stat_label(name)
            self.labels[key] = label
            layout.addWidget(label)
        
        self.setLayout(layout)
        
        # Set minimum size
        self.setMinimumWidth(200)
        
        # Apply stylesheet
        self.apply_stylesheet()
    
    def create_stat_label(self, name: str) -> QLabel:
        """Create a styled label for displaying stats."""
        label = QLabel(f"{name}: --")
        label.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        
        # Add drop shadow for better visibility
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(4)
        shadow.setColor(QColor(0, 0, 0, 200))
        shadow.setOffset(1, 1)
        label.setGraphicsEffect(shadow)
        
        return label
    
    def _resolve_rgba(self, color_value: str, opacity: float) -> str:
        """Convert color string (hex or 'R, G, B') to rgba with opacity."""
        try:
            text = (color_value or "").strip()
            if "," in text:
                parts = [p.strip() for p in text.split(",")]
                if len(parts) == 3:
                    r, g, b = [max(0, min(255, int(p))) for p in parts]
                    return f"rgba({r}, {g}, {b}, {opacity})"
            qcolor = QColor(text)
            if not qcolor.isValid():
                qcolor = QColor("#141414")
            return f"rgba({qcolor.red()}, {qcolor.green()}, {qcolor.blue()}, {opacity})"
        except Exception:
            return f"rgba(20, 20, 20, {opacity})"

    def apply_stylesheet(self):
        """Apply CSS styling to the overlay."""
        bg_opacity = float(self.config.get('background_opacity', 0.7))
        bg_color = self.config.get('background_color', '#141414')
        text_color = self.config.get('text_color', '#B0B0B0')
        text_opacity = float(self.config.get('text_opacity', 1.0))

        bg_rgba = self._resolve_rgba(bg_color, bg_opacity)
        text_rgba = self._resolve_rgba(text_color, text_opacity)
        
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {bg_rgba};
                border-radius: 8px;
            }}
            QLabel {{
                color: {text_rgba};
                padding: 2px 5px;
                background: transparent;
            }}
        """)
    
    def setup_timer(self):
        """Setup timer for periodic updates."""
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_stats)
        
        interval = self.config.get('update_interval', 1000)
        self.update_timer.start(interval)
        
        # Initial update
        self.update_stats()

    def update_config(self, new_config: dict):
        """Update configuration and refresh overlay appearance/behavior."""
        self.config = new_config or {}
        # position
        self.move(self.config.get('position_x', self.x()), self.config.get('position_y', self.y()))
        # interval
        interval = self.config.get('update_interval', 1000)
        if hasattr(self, 'update_timer'):
            self.update_timer.start(interval)
        # stylesheet
        self.apply_stylesheet()
        # refresh display
        self.update_stats()
    
    def get_temp_color(self, temp: float) -> str:
        """Get color based on temperature (green->yellow->red) with global text opacity."""
        text_opacity = float(self.config.get('text_opacity', 1.0))
        def rgba(hex_color: str) -> str:
            try:
                qc = QColor(hex_color)
                if not qc.isValid():
                    qc = QColor("#00FF00")
                return f"rgba({qc.red()}, {qc.green()}, {qc.blue()}, {text_opacity})"
            except Exception:
                return f"rgba(0, 255, 0, {text_opacity})"

        if temp < 50:
            return rgba("#00FF00")  # Green - cool
        elif temp < 70:
            ratio = (temp - 50) / 20
            r = int(255 * ratio)
            return rgba(f"#{r:02X}FF00")
        elif temp < 85:
            ratio = (temp - 70) / 15
            g = int(255 * (1 - ratio))
            return rgba(f"#FF{g:02X}00")
        else:
            return rgba("#FF0000")  # Red - hot
    
    def update_stats(self):
        """Update displayed statistics."""
        stats = self.hardware_monitor.get_stats()
        
        # FPS line
        if stats.fps is not None:
            self.labels['fps'].setText(f"FPS: {stats.fps}")
        else:
            self.labels['fps'].setText("FPS: --")
        
        # Use full CPU name when enabled; otherwise show generic label
        show_full_names = self.config.get('show_full_device_names', True)
        cpu_label = stats.cpu_name if (show_full_names and stats.cpu_name) else "CPU"
        
        # Build CPU line: CPU: usage | temp | clock | fan
        cpu_parts = [f"{cpu_label}: {stats.cpu_usage:.0f}%"]
        cpu_temp_color = None
        if stats.cpu_temp is not None:
            cpu_temp_color = self.get_temp_color(stats.cpu_temp)
            cpu_parts.append(f'<span style="color:{cpu_temp_color}">{stats.cpu_temp:.0f}C</span>')
        if stats.cpu_clock is not None:
            cpu_parts.append(f"{stats.cpu_clock:.0f}MHz")
        if stats.cpu_fan_rpm is not None:
            cpu_parts.append(f"{stats.cpu_fan_rpm}RPM")
        self.labels['cpu'].setText(" | ".join(cpu_parts))
        
        # GPU line - use full name when enabled; otherwise generic label
        gpu_label = stats.gpu_name if (show_full_names and stats.gpu_name) else "GPU"
        
        # Build GPU line: GPU: usage | temp | clock | fan
        gpu_parts = [f"{gpu_label}:"]
        has_data = False
        if stats.gpu_usage is not None:
            gpu_parts[0] = f"{gpu_label}: {stats.gpu_usage:.0f}%"
            has_data = True
        if stats.gpu_temp is not None:
            gpu_temp_color = self.get_temp_color(stats.gpu_temp)
            gpu_parts.append(f'<span style="color:{gpu_temp_color}">{stats.gpu_temp:.0f}C</span>')
            has_data = True
        if stats.gpu_clock is not None:
            gpu_parts.append(f"{stats.gpu_clock:.0f}MHz")
            has_data = True
        if stats.gpu_fan_rpm is not None:
            gpu_parts.append(f"{stats.gpu_fan_rpm}RPM")
            has_data = True
        elif stats.gpu_fan_percent is not None:
            gpu_parts.append(f"Fan {stats.gpu_fan_percent:.0f}%")
            has_data = True
        
        if not has_data:
            gpu_parts.append("--")
        self.labels['gpu'].setText(" | ".join(gpu_parts))
        
        # RAM line (unchanged)
        ram_text = f"RAM: {stats.ram_usage:.0f}% ({stats.ram_used_gb:.1f}/{stats.ram_total_gb:.1f}GB)"
        self.labels['ram'].setText(ram_text)
        
        # Resize to fit content
        self.adjustSize()
    
    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press for dragging."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
    
    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse move for dragging."""
        if self.dragging:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()
    
    def mouseReleaseEvent(self, event: QMouseEvent):
        """Handle mouse release to stop dragging."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            event.accept()
    
    def closeEvent(self, event):
        """Clean up on close."""
        self.hardware_monitor.shutdown()
        super().closeEvent(event)
    
    def toggle_visibility(self):
        """Toggle overlay visibility."""
        if self.isVisible():
            self.hide()
        else:
            self.show()
    
    def get_position(self) -> tuple:
        """Get current position."""
        return (self.x(), self.y())


class OverlayApp:
    """Main application class managing the overlay."""
    
    def __init__(self, config: dict = None):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        
        self.config = config or {}
        # Remember config path for saving
        self.config_path = Path(self.config.get("__config_path__", Path(__file__).resolve().parent / "config.json"))
        
        self.overlay = OverlayWidget(self.config)

        # In-app Qt shortcuts (works even if keyboard module fails)
        self._settings_shortcut = None
        self.setup_qt_shortcuts()
        
        # Setup signals for thread-safe hotkey communication
        self.hotkey_signals = HotkeySignals()
        self.hotkey_signals.toggle_signal.connect(self.toggle_overlay)
        self.hotkey_signals.quit_signal.connect(self.quit)
        self.hotkey_signals.settings_signal.connect(self.show_settings)
        
        # Setup system tray
        self.setup_tray()
        
        # Setup global hotkey
        self.keyboard = None
        self.keyboard_hotkeys_initialized = False
        self.setup_hotkey()

    def setup_qt_shortcuts(self):
        """Setup Qt-level shortcuts for settings (fallback when tray is hidden)."""
        try:
            settings_hotkey = self.config.get('settings_hotkey', 'ctrl+alt+s')
            # If shortcut already exists, remove it
            if self._settings_shortcut:
                self._settings_shortcut.setParent(None)
                self._settings_shortcut = None
            self._settings_shortcut = QShortcut(QKeySequence(settings_hotkey), self.overlay)
            self._settings_shortcut.activated.connect(self.show_settings)
        except Exception as e:
            print(f"Warning: Could not set Qt shortcut: {e}")
    
    def create_tray_icon(self) -> QIcon:
        """Create a simple colored icon for system tray."""
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setBrush(QColor(0, 255, 0))  # Green
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(4, 4, 24, 24)
        painter.end()
        return QIcon(pixmap)
    
    def setup_tray(self):
        """Setup system tray icon with menu."""
        self.tray_icon = QSystemTrayIcon(self.app)
        self.tray_icon.setIcon(self.create_tray_icon())
        self.tray_icon.setToolTip("FPS Monitor Overlay")
        
        # Create tray menu
        tray_menu = QMenu()
        
        settings_action = QAction("Settings…", self.app)
        settings_action.triggered.connect(self.show_settings)
        tray_menu.addAction(settings_action)
        
        toggle_action = QAction("Toggle Overlay (F12)", self.app)
        toggle_action.triggered.connect(self.toggle_overlay)
        tray_menu.addAction(toggle_action)
        
        tray_menu.addSeparator()
        
        quit_action = QAction("Exit (Ctrl+Shift+Q)", self.app)
        quit_action.triggered.connect(self.quit)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()
    
    def on_tray_activated(self, reason):
        """Handle tray icon activation."""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.toggle_overlay()
    
    def setup_hotkey(self):
        """Setup global hotkey for toggling overlay."""
        try:
            import keyboard
            self.keyboard = keyboard

            # If reloading, clear existing hotkeys
            if self.keyboard_hotkeys_initialized:
                keyboard.unhook_all_hotkeys()

            hotkey = self.config.get('toggle_hotkey', 'f12')
            exit_hotkey = self.config.get('exit_hotkey', 'ctrl+shift+q')
            
            # Use signals to safely communicate with Qt from keyboard thread
            def on_toggle():
                self.hotkey_signals.toggle_signal.emit()
            
            def on_quit():
                self.hotkey_signals.quit_signal.emit()

            def on_settings():
                self.hotkey_signals.settings_signal.emit()
            
            settings_hotkey = self.config.get('settings_hotkey', 'ctrl+alt+s')

            keyboard.add_hotkey(hotkey, on_toggle, suppress=False)
            keyboard.add_hotkey(exit_hotkey, on_quit, suppress=False)
            keyboard.add_hotkey(settings_hotkey, on_settings, suppress=False)
            
            print(f"Hotkeys registered: {hotkey} (toggle), {exit_hotkey} (exit), {settings_hotkey} (settings)")
            self.keyboard_hotkeys_initialized = True
            
        except ImportError:
            print("Warning: 'keyboard' module not available.")
            print("         Use system tray icon to control overlay.")
        except Exception as e:
            print(f"Warning: Could not setup hotkeys: {e}")
            print("         Run as Administrator for hotkey support.")
            print("         Use system tray icon to control overlay.")

    def reload_hotkeys(self):
        """Reload global hotkeys after config changes."""
        self.setup_hotkey()
    
    def toggle_overlay(self):
        """Toggle overlay visibility."""
        self.overlay.toggle_visibility()
    
    def quit(self):
        """Quit the application."""
        self.overlay.hardware_monitor.shutdown()
        if hasattr(self, 'tray_icon'):
            self.tray_icon.hide()
        self.app.quit()

    def save_config(self, new_config: dict):
        """Persist configuration to disk."""
        target = Path(new_config.get("__config_path__", self.config_path))
        fallback = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "fps-overlay" / "config.json"

        def _try_write(path: Path) -> bool:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(new_config, f, indent=4)
                self.config_path = path
                self.config["__config_path__"] = str(path)
                print(f"Config saved to {path}")
                return True
            except Exception as e:
                print(f"Warning: Could not save config to {path}: {e}")
                return False

        if not _try_write(target):
            if target != fallback:
                if _try_write(fallback):
                    new_config["__config_path__"] = str(fallback)
                else:
                    print("Warning: Failed to save config to both primary and fallback locations.")

    def show_settings(self):
        """Open settings dialog and apply changes."""
        dialog = SettingsDialog(self.config, on_change=self.apply_live_settings)
        dialog.exec()
    
    def run(self):
        """Run the application."""
        self.overlay.show()
        return self.app.exec()

    def apply_live_settings(self, updated: dict):
        """Apply settings immediately (live preview) and persist."""
        # Preserve config path marker
        updated["__config_path__"] = str(self.config_path)
        self.config = updated
        self.overlay.update_config(updated)
        self.reload_hotkeys()
        self.save_config(updated)
