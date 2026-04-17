# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Misc Parameters dialog — matches PCPackRatt 'Misc Parameters'.

Parameters:
  Control characters (hex): BITINV, CANLINE, CANPAC, COMMAND, CWID,
                             HEREIS, RECEIVE, REDISPLA, SENDPAC, TIME
  Tone frequencies:         MARK, SPACE
  Read-only (hardware):     BRIGHT, BARGRAPH, THRESHOLD
  Modem:                    MODEM (text)
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QSpinBox, QVBoxLayout, QWidget,
)

logger = logging.getLogger(__name__)


class HexSpinBox(QSpinBox):
    """A SpinBox that displays values as $XX hex strings."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setRange(0, 127)
        self.setPrefix("$")
        self.setDisplayIntegerBase(16)

    def textFromValue(self, value: int) -> str:
        return format(value, '02X')

    def valueFromText(self, text: str) -> int:
        t = text.lstrip('$').lstrip('0x').lstrip('0X')
        try:
            return int(t, 16) if t else 0
        except ValueError:
            return 0


class MiscParamsDialog(QDialog):
    """Misc Parameters dialog.

    Matches the PCPackRatt 'Misc Parameters' dialog.
    All parameters are sent directly to the TNC via Host Mode when
    the user clicks OK.

    Usage::

        dlg = MiscParamsDialog(parent=self)
        dlg.set_values(canline=0x18, canpac=0x19, mark=2125, space=2295)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            values = dlg.get_values()
    """

    # Default values matching PCPackRatt defaults
    DEFAULTS = {
        "bitinv":   0x30,
        "canline":  0x18,
        "canpac":   0x19,
        "command":  0x03,
        "cwid":     0x06,
        "hereis":   0x02,
        "receive":  0x04,
        "redispla": 0x12,
        "sendpac":  0x0D,
        "time":     0x14,
        "mark":     2125,
        "space":    2295,
    }

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Misc Parameters")
        self.setMinimumWidth(420)
        self.setModal(True)
        self._build_ui()
        self.set_values(**self.DEFAULTS)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # ── Control characters ────────────────────────────────────────
        ctrl_group = QGroupBox("Control Characters")
        form = QFormLayout(ctrl_group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._hx_bitinv   = HexSpinBox(); form.addRow("BITINV:",   self._hx_bitinv)
        self._hx_canline  = HexSpinBox(); form.addRow("CANLINE:",  self._hx_canline)
        self._hx_canpac   = HexSpinBox(); form.addRow("CANPAC:",   self._hx_canpac)
        self._hx_command  = HexSpinBox(); form.addRow("COMMAND:",  self._hx_command)
        self._hx_cwid     = HexSpinBox(); form.addRow("CWID:",     self._hx_cwid)
        self._hx_hereis   = HexSpinBox(); form.addRow("HEREIS:",   self._hx_hereis)
        self._hx_receive  = HexSpinBox(); form.addRow("RECEIVE:",  self._hx_receive)
        self._hx_redispla = HexSpinBox(); form.addRow("REDISPLA:", self._hx_redispla)
        self._hx_sendpac  = HexSpinBox(); form.addRow("SENDPAC:",  self._hx_sendpac)
        self._hx_time     = HexSpinBox(); form.addRow("TIME:",     self._hx_time)
        root.addWidget(ctrl_group)

        # ── Tone frequencies ──────────────────────────────────────────
        tone_group = QGroupBox("Tone Frequencies")
        tone_form  = QFormLayout(tone_group)
        tone_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._sb_mark = QSpinBox()
        self._sb_mark.setRange(100, 3000)
        self._sb_mark.setSuffix(" Hz")
        tone_form.addRow("MARK:", self._sb_mark)

        self._sb_space = QSpinBox()
        self._sb_space.setRange(100, 3000)
        self._sb_space.setSuffix(" Hz")
        tone_form.addRow("SPACE:", self._sb_space)
        root.addWidget(tone_group)

        # ── Read-only hardware values ─────────────────────────────────
        hw_group = QGroupBox("Hardware (read-only)")
        hw_form  = QFormLayout(hw_group)
        hw_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._sb_bright    = QSpinBox(); self._sb_bright.setRange(0, 100)
        self._sb_bright.setEnabled(False); self._sb_bright.setValue(50)
        hw_form.addRow("BRIGHT:", self._sb_bright)

        self._sb_bargraph  = QSpinBox(); self._sb_bargraph.setRange(0, 10)
        self._sb_bargraph.setEnabled(False); self._sb_bargraph.setValue(0)
        hw_form.addRow("BARGRAPH:", self._sb_bargraph)

        self._sb_threshold = QSpinBox(); self._sb_threshold.setRange(0, 100)
        self._sb_threshold.setEnabled(False); self._sb_threshold.setValue(50)
        hw_form.addRow("THRESHOLD:", self._sb_threshold)
        root.addWidget(hw_group)

        # ── Modem ─────────────────────────────────────────────────────
        modem_group = QGroupBox("Modem")
        modem_form  = QFormLayout(modem_group)
        self._le_modem = QLineEdit()
        self._le_modem.setPlaceholderText("(internal)")
        modem_form.addRow("MODEM:", self._le_modem)
        root.addWidget(modem_group)

        # ── Buttons ───────────────────────────────────────────────────
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_values(self, **kwargs) -> None:
        """Pre-fill dialog widgets from keyword arguments.

        Accepted keys: ``bitinv``, ``canline``, ``canpac``, ``command``,
        ``cwid``, ``hereis``, ``receive``, ``redispla``, ``sendpac``,
        ``time``, ``mark``, ``space``.
        """
        mapping = {
            "bitinv":   self._hx_bitinv,
            "canline":  self._hx_canline,
            "canpac":   self._hx_canpac,
            "command":  self._hx_command,
            "cwid":     self._hx_cwid,
            "hereis":   self._hx_hereis,
            "receive":  self._hx_receive,
            "redispla": self._hx_redispla,
            "sendpac":  self._hx_sendpac,
            "time":     self._hx_time,
        }
        for key, widget in mapping.items():
            if key in kwargs:
                widget.setValue(int(kwargs[key]))
        if "mark"  in kwargs: self._sb_mark.setValue(int(kwargs["mark"]))
        if "space" in kwargs: self._sb_space.setValue(int(kwargs["space"]))
        if "modem" in kwargs: self._le_modem.setText(str(kwargs["modem"]))

    def get_values(self) -> dict:
        """Return current dialog values as a dict."""
        return {
            "bitinv":   self._hx_bitinv.value(),
            "canline":  self._hx_canline.value(),
            "canpac":   self._hx_canpac.value(),
            "command":  self._hx_command.value(),
            "cwid":     self._hx_cwid.value(),
            "hereis":   self._hx_hereis.value(),
            "receive":  self._hx_receive.value(),
            "redispla": self._hx_redispla.value(),
            "sendpac":  self._hx_sendpac.value(),
            "time":     self._hx_time.value(),
            "mark":     self._sb_mark.value(),
            "space":    self._sb_space.value(),
            "modem":    self._le_modem.text(),
        }

    # ------------------------------------------------------------------
    # Slot
    # ------------------------------------------------------------------

    def _on_accept(self) -> None:
        self.accept()