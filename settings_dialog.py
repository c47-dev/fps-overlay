from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout,
    QLineEdit, QDoubleSpinBox, QSpinBox, QCheckBox,
    QPushButton, QColorDialog, QLabel
)
from PyQt6.QtGui import QColor


class SettingsDialog(QDialog):
    """Simple settings dialog to adjust overlay appearance and behavior."""

    def __init__(self, config: dict, on_change=None):
        super().__init__()
        self.setWindowTitle("Overlay Settings")
        self.config = config or {}
        self.on_change = on_change
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout()
        form = QFormLayout()

        # Position
        self.pos_x = QSpinBox()
        self.pos_x.setRange(-10000, 10000)
        self.pos_x.setValue(self.config.get("position_x", 0))

        self.pos_y = QSpinBox()
        self.pos_y.setRange(-10000, 10000)
        self.pos_y.setValue(self.config.get("position_y", 0))

        pos_layout = QHBoxLayout()
        pos_layout.addWidget(self.pos_x)
        pos_layout.addWidget(self.pos_y)
        form.addRow("Position X / Y", pos_layout)

        # Update interval (ms)
        self.update_interval = QSpinBox()
        self.update_interval.setRange(100, 10000)
        self.update_interval.setValue(self.config.get("update_interval", 1000))
        form.addRow("Update interval (ms)", self.update_interval)

        # Opacity
        self.opacity = QDoubleSpinBox()
        self.opacity.setRange(0.1, 1.0)
        self.opacity.setSingleStep(0.05)
        self.opacity.setDecimals(2)
        self.opacity.setValue(float(self.config.get("background_opacity", 0.7)))
        form.addRow("Background opacity", self.opacity)

        # Colors with pickers (stored as hex)
        self.bg_color = QLineEdit(self.config.get("background_color", "#141414"))
        bg_pick = QPushButton("Pick…")
        bg_pick.clicked.connect(lambda: self.pick_color(self.bg_color))
        bg_row = QHBoxLayout()
        bg_row.addWidget(self.bg_color)
        bg_row.addWidget(bg_pick)
        form.addRow("Background color", bg_row)

        self.text_color = QLineEdit(self.config.get("text_color", "#B0B0B0"))
        text_pick = QPushButton("Pick…")
        text_pick.clicked.connect(lambda: self.pick_color(self.text_color))
        text_row = QHBoxLayout()
        text_row.addWidget(self.text_color)
        text_row.addWidget(text_pick)
        form.addRow("Text color", text_row)

        # Text opacity
        self.text_opacity = QDoubleSpinBox()
        self.text_opacity.setRange(0.0, 1.0)
        self.text_opacity.setSingleStep(0.05)
        self.text_opacity.setDecimals(2)
        self.text_opacity.setValue(float(self.config.get("text_opacity", 1.0)))
        form.addRow("Text opacity", self.text_opacity)

        # Hotkeys
        self.toggle_hotkey = QLineEdit(self.config.get("toggle_hotkey", "f12"))
        form.addRow("Toggle hotkey", self.toggle_hotkey)

        self.exit_hotkey = QLineEdit(self.config.get("exit_hotkey", "ctrl+shift+q"))
        form.addRow("Exit hotkey", self.exit_hotkey)

        self.settings_hotkey = QLineEdit(self.config.get("settings_hotkey", "ctrl+alt+s"))
        form.addRow("Settings hotkey", self.settings_hotkey)

        # Show full names
        self.show_full_names = QCheckBox("Show full CPU/GPU names")
        self.show_full_names.setChecked(self.config.get("show_full_device_names", True))
        form.addRow(self.show_full_names)

        layout.addLayout(form)

        # Close button only (changes apply immediately)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        close_row = QHBoxLayout()
        close_row.addStretch()
        close_row.addWidget(close_btn)

        layout.addLayout(close_row)
        self.setLayout(layout)

        # Wire live updates
        self.pos_x.valueChanged.connect(self.emit_change)
        self.pos_y.valueChanged.connect(self.emit_change)
        self.update_interval.valueChanged.connect(self.emit_change)
        self.opacity.valueChanged.connect(self.emit_change)
        self.bg_color.textChanged.connect(self.emit_change)
        self.text_color.textChanged.connect(self.emit_change)
        self.text_opacity.valueChanged.connect(self.emit_change)
        self.toggle_hotkey.textChanged.connect(self.emit_change)
        self.exit_hotkey.textChanged.connect(self.emit_change)
        self.settings_hotkey.textChanged.connect(self.emit_change)
        self.show_full_names.stateChanged.connect(self.emit_change)

    def get_config(self) -> dict:
        """Return the updated configuration."""
        return {
            "position_x": int(self.pos_x.value()),
            "position_y": int(self.pos_y.value()),
            "update_interval": int(self.update_interval.value()),
            "background_opacity": float(self.opacity.value()),
            "background_color": self.bg_color.text().strip(),
            "text_color": self.text_color.text().strip(),
            "text_opacity": float(self.text_opacity.value()),
            "toggle_hotkey": self.toggle_hotkey.text().strip() or "f12",
            "exit_hotkey": self.exit_hotkey.text().strip() or "ctrl+shift+q",
            "settings_hotkey": self.settings_hotkey.text().strip() or "ctrl+alt+s",
            "show_full_device_names": bool(self.show_full_names.isChecked()),
        }

    def emit_change(self):
        """Notify listener with current config (live apply)."""
        if self.on_change:
            self.on_change(self.get_config())

    def pick_color(self, line_edit: QLineEdit):
        """Open color picker and update line edit."""
        initial = QColor(line_edit.text()) if QColor.isValidColor(line_edit.text()) else QColor("#FFFFFF")
        color = QColorDialog.getColor(initial, self, "Select Color")
        if color.isValid():
            line_edit.setText(color.name())
            self.emit_change()
