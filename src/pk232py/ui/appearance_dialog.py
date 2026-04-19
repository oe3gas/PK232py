# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Appearance Settings dialog — font and color configuration."""

from __future__ import annotations
import logging
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QColorDialog, QDialog, QDialogButtonBox, QFontComboBox,
    QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)
from pk232py.config import AppearanceConfig

logger = logging.getLogger(__name__)


class ColorButton(QPushButton):
    """A button that shows and selects a color."""

    def __init__(self, color: str = "#1e1e1e", parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(80, 24)
        self.set_color(color)
        self.clicked.connect(self._pick_color)

    def set_color(self, color: str) -> None:
        self._color = color
        self.setStyleSheet(
            f"background-color:{color}; border:1px solid #888;"
            f"border-radius:3px;"
        )
        self.setText(color)

    def color(self) -> str:
        return self._color

    def _pick_color(self) -> None:
        c = QColorDialog.getColor(
            QColor(self._color), self, "Select Color"
        )
        if c.isValid():
            self.set_color(c.name())


class AppearanceDialog(QDialog):
    """Appearance settings dialog.

    Allows selecting font family, size, background and foreground color
    for the RX/TX display and verbose terminal.

    Usage::

        dlg = AppearanceDialog(config.appearance, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            dlg.apply_to(config.appearance)
    """

    def __init__(self, config: AppearanceConfig, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self.setWindowTitle("Appearance Settings")
        self.setMinimumWidth(400)
        self.setModal(True)
        self._build_ui()
        self._populate()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # ── Font ──────────────────────────────────────────────────────
        font_group = QGroupBox("Display Font")
        font_form  = QFormLayout(font_group)
        font_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._font_combo = QFontComboBox()
        self._font_combo.setFontFilters(
            QFontComboBox.FontFilter.MonospacedFonts
        )
        font_form.addRow("Font family:", self._font_combo)

        self._font_size = QSpinBox()
        self._font_size.setRange(6, 24)
        self._font_size.setSuffix(" pt")
        font_form.addRow("Font size:", self._font_size)

        root.addWidget(font_group)

        # ── Colors ────────────────────────────────────────────────────
        color_group = QGroupBox("Display Colors")
        color_form  = QFormLayout(color_group)
        color_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._bg_btn = ColorButton()
        color_form.addRow("Background:", self._bg_btn)

        self._fg_btn = ColorButton()
        color_form.addRow("Foreground (text):", self._fg_btn)

        root.addWidget(color_group)

        # ── Preview ───────────────────────────────────────────────────
        preview_group = QGroupBox("Preview")
        pv_layout = QVBoxLayout(preview_group)
        self._preview = QLabel("AEA PK-232MBX  Ver. 7.1\ncmd: MYCALL OE3GAS")
        self._preview.setFixedHeight(50)
        self._preview.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._preview.setContentsMargins(6, 4, 6, 4)
        pv_layout.addWidget(self._preview)
        root.addWidget(preview_group)

        # Update preview on change
        self._font_combo.currentFontChanged.connect(self._update_preview)
        self._font_size.valueChanged.connect(self._update_preview)
        self._bg_btn.clicked.connect(self._update_preview)
        self._fg_btn.clicked.connect(self._update_preview)

        # ── Buttons ───────────────────────────────────────────────────
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.Reset
        )
        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(
            self._on_reset
        )
        root.addWidget(bb)

    def _populate(self) -> None:
        c = self._config
        self._font_combo.setCurrentFont(QFont(c.font_family))
        self._font_size.setValue(c.font_size)
        self._bg_btn.set_color(c.bg_color)
        self._fg_btn.set_color(c.fg_color)
        self._update_preview()

    def _update_preview(self) -> None:
        font = self._font_combo.currentFont()
        font.setPointSize(self._font_size.value())
        self._preview.setFont(font)
        self._preview.setStyleSheet(
            f"background-color:{self._bg_btn.color()};"
            f"color:{self._fg_btn.color()};"
        )

    def apply_to(self, config: AppearanceConfig) -> None:
        """Write dialog values into config."""
        config.font_family = self._font_combo.currentFont().family()
        config.font_size   = self._font_size.value()
        config.bg_color    = self._bg_btn.color()
        config.fg_color    = self._fg_btn.color()

    def _on_reset(self) -> None:
        """Reset to defaults."""
        defaults = AppearanceConfig()
        self._font_combo.setCurrentFont(QFont(defaults.font_family))
        self._font_size.setValue(defaults.font_size)
        self._bg_btn.set_color(defaults.bg_color)
        self._fg_btn.set_color(defaults.fg_color)
        self._update_preview()

    def _on_accept(self) -> None:
        self.apply_to(self._config)
        self.accept()