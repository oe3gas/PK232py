# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Appearance Settings dialog — font and color configuration."""

from __future__ import annotations
import logging
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QColorDialog, QDialog, QDialogButtonBox, QFontComboBox,
    QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)
from pk232py.colors import low_contrast_warnings
from pk232py.config import AppearanceConfig

logger = logging.getLogger(__name__)


class ColorButton(QPushButton):
    """A button that shows and selects a color."""

    # Emitted whenever the colour changes (picked OR set from code), so the
    # dialog's preview and contrast warning never miss a change.
    colorChanged = pyqtSignal(str)

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
        self.colorChanged.emit(color)

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

    Allows selecting font family, size, background, foreground, RX text and
    TX text color for the RX/TX displays and the verbose terminal (P77: one
    colour source, AppearanceConfig).

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

        # Show ALL fonts, not just QFontComboBox.MonospacedFonts: that filter
        # only lists fonts the OS *tagged* as monospaced and hides many
        # fixed-pitch TTFs (Cascadia Mono, Consolas variants, …). We list
        # everything and add a hint instead, so no usable font is filtered out.
        self._font_combo = QFontComboBox()
        self._font_combo.setFontFilters(QFontComboBox.FontFilter.AllFonts)
        font_form.addRow("Font family:", self._font_combo)

        hint = QLabel("Monospace fonts recommended for aligned columns.")
        hint.setStyleSheet("color:#888; font-size:8pt;")
        font_form.addRow("", hint)

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

        # P77: received text / TNC output, and typed text / own commands.
        self._rx_btn = ColorButton()
        color_form.addRow("RX text:", self._rx_btn)

        self._tx_btn = ColorButton()
        color_form.addRow("TX text:", self._tx_btn)

        root.addWidget(color_group)

        # ── Preview ───────────────────────────────────────────────────
        preview_group = QGroupBox("Preview")
        pv_layout = QVBoxLayout(preview_group)
        # One line per colour: foreground, RX (TNC output), TX (own command).
        self._preview = QLabel()
        self._preview.setTextFormat(Qt.TextFormat.RichText)
        self._preview.setFixedHeight(70)
        self._preview.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._preview.setContentsMargins(6, 4, 6, 4)
        pv_layout.addWidget(self._preview)
        # P77: shown (never blocking) when a text colour is hard to read on
        # the chosen background; empty = hidden.
        self._warning = QLabel()
        self._warning.setWordWrap(True)
        self._warning.setStyleSheet("color:#c0392b;")
        self._warning.setVisible(False)
        pv_layout.addWidget(self._warning)
        root.addWidget(preview_group)

        # Update preview on change
        self._font_combo.currentFontChanged.connect(self._update_preview)
        self._font_size.valueChanged.connect(self._update_preview)
        for btn in (self._bg_btn, self._fg_btn, self._rx_btn, self._tx_btn):
            btn.colorChanged.connect(self._update_preview)

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
        self._rx_btn.set_color(c.rx_color)
        self._tx_btn.set_color(c.tx_color)
        self._update_preview()

    def _update_preview(self) -> None:
        font = self._font_combo.currentFont()
        font.setPointSize(self._font_size.value())
        self._preview.setFont(font)
        bg, fg = self._bg_btn.color(), self._fg_btn.color()
        rx, tx = self._rx_btn.color(), self._tx_btn.color()
        self._preview.setStyleSheet(f"background-color:{bg}; color:{fg};")
        self._preview.setText(
            f'<span style="color:{fg}">Foreground text</span><br>'
            f'<span style="color:{rx}">AEA PK-232MBX  Ver. 7.1</span><br>'
            f'<span style="color:{tx}">cmd: MYCALL OE3GAS</span>'
        )
        warnings = low_contrast_warnings(bg, fg, rx, tx)
        self._warning.setText("<br>".join(warnings))
        self._warning.setVisible(bool(warnings))

    def apply_to(self, config: AppearanceConfig) -> None:
        """Write dialog values into config."""
        config.font_family = self._font_combo.currentFont().family()
        config.font_size   = self._font_size.value()
        config.bg_color    = self._bg_btn.color()
        config.fg_color    = self._fg_btn.color()
        config.rx_color    = self._rx_btn.color()
        config.tx_color    = self._tx_btn.color()

    def _on_reset(self) -> None:
        """Reset to the active theme's preset values (not hardcoded defaults).

        If the config's theme is a known preset, reset to that preset; for
        "custom" (or an unknown key) fall back to the Dark preset, which also
        matches AppearanceConfig's field defaults.
        """
        from pk232py.ui.themes import THEMES
        t = THEMES.get(self._config.theme, THEMES["dark"])
        self._font_combo.setCurrentFont(QFont(t.font_family))
        self._font_size.setValue(t.font_size)
        self._bg_btn.set_color(t.bg)
        self._fg_btn.set_color(t.fg)
        self._rx_btn.set_color(t.rx)
        self._tx_btn.set_color(t.tx)
        self._update_preview()

    def _on_accept(self) -> None:
        self.apply_to(self._config)
        self.accept()