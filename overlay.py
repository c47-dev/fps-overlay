"""
Transparent overlay window for displaying hardware stats.
Uses PyQt6 with transparent, always-on-top, click-through window.
"""

import sys
import threading
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QGraphicsDropShadowEffect, QSystemTrayIcon, QMenu
)
from PyQt6.QtCore import Qt, QTimer, QPoint, pyqtSignal, QObject
from PyQt6.QtGui import QColor, QFont, QMouseEvent, QIcon, QPixmap, QPainter, QAction

from hardware_monitor import HardwareMonitor, HardwareStats


class HotkeySignals(QObject):
    """Signals for hotkey events to communicate with Qt main thread."""
    toggle_signal = pyqtSignal()
    quit_signal = pyqtSignal()


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
    
    def apply_stylesheet(self):
        """Apply CSS styling to the overlay."""
        bg_opacity = self.config.get('background_opacity', 0.7)
        bg_color = self.config.get('background_color', '20, 20, 20')
        text_color = self.config.get('text_color', '#00FF00')
        
        self.setStyleSheet(f"""
            QWidget {{
                background-color: rgba({bg_color}, {bg_opacity});
                border-radius: 8px;
            }}
            QLabel {{
                color: {text_color};
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
    
    def get_temp_color(self, temp: float) -> str:
        """Get color based on temperature (green->yellow->red)."""
        if temp < 50:
            return "#00FF00"  # Green - cool
        elif temp < 70:
            # Gradient from green to yellow (50-70)
            ratio = (temp - 50) / 20
            r = int(255 * ratio)
            return f"#{r:02X}FF00"
        elif temp < 85:
            # Gradient from yellow to red (70-85)
            ratio = (temp - 70) / 15
            g = int(255 * (1 - ratio))
            return f"#FF{g:02X}00"
        else:
            return "#FF0000"  # Red - hot
    
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
        self.overlay = OverlayWidget(self.config)
        
        # Setup signals for thread-safe hotkey communication
        self.hotkey_signals = HotkeySignals()
        self.hotkey_signals.toggle_signal.connect(self.toggle_overlay)
        self.hotkey_signals.quit_signal.connect(self.quit)
        
        # Setup system tray
        self.setup_tray()
        
        # Setup global hotkey
        self.setup_hotkey()
    
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
        self.hotkey_thread = None
        
        try:
            import keyboard
            
            hotkey = self.config.get('toggle_hotkey', 'f12')
            exit_hotkey = self.config.get('exit_hotkey', 'ctrl+shift+q')
            
            # Use signals to safely communicate with Qt from keyboard thread
            def on_toggle():
                self.hotkey_signals.toggle_signal.emit()
            
            def on_quit():
                self.hotkey_signals.quit_signal.emit()
            
            keyboard.add_hotkey(hotkey, on_toggle, suppress=False)
            keyboard.add_hotkey(exit_hotkey, on_quit, suppress=False)
            
            print(f"Hotkeys registered: {hotkey} (toggle), {exit_hotkey} (exit)")
            
        except ImportError:
            print("Warning: 'keyboard' module not available.")
            print("         Use system tray icon to control overlay.")
        except Exception as e:
            print(f"Warning: Could not setup hotkeys: {e}")
            print("         Run as Administrator for hotkey support.")
            print("         Use system tray icon to control overlay.")
    
    def toggle_overlay(self):
        """Toggle overlay visibility."""
        self.overlay.toggle_visibility()
    
    def quit(self):
        """Quit the application."""
        self.overlay.hardware_monitor.shutdown()
        if hasattr(self, 'tray_icon'):
            self.tray_icon.hide()
        self.app.quit()
    
    def run(self):
        """Run the application."""
        self.overlay.show()
        return self.app.exec()
