# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""PACTOR Parameters dialog — matches PCPackRatt 'Pactor Parameters'."""

from __future__ import annotations
import logging
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QSpinBox, QVBoxLayout, QWidget,
)
from pk232py.config import PACTORConfig

logger = logging.getLogger(__name__)


class HexSpinBox(QSpinBox):
    def __init__(self, p=None):
        super().__init__(p); self.setRange(0,127)
        self.setPrefix("$"); self.setDisplayIntegerBase(16)
    def textFromValue(self, v): return format(v, '02X')
    def valueFromText(self, t):
        try: return int(t.lstrip('$').lstrip('0x') or '0', 16)
        except ValueError: return 0


class PACTORParamsDialog(QDialog):
    """PACTOR Parameters dialog matching PCPackRatt layout."""

    def __init__(self, config: PACTORConfig, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self.setWindowTitle("PACTOR Parameters")
        self.setMinimumWidth(480)
        self.setModal(True)
        self._build_ui()
        self._populate()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # ── Left: numeric params / Right: flags ──────────────────────
        row = QHBoxLayout()

        left = QGroupBox("Parameters")
        form = QFormLayout(left)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        def spin(lo, hi, val):
            w = QSpinBox(); w.setRange(lo, hi); w.setValue(val); return w

        self._le_myptcall = QLineEdit()
        self._le_myptcall.setMaximumWidth(120)
        form.addRow("MYPTCALL:", self._le_myptcall)

        self._sb_arqtmo  = spin(0, 250, 60);  form.addRow("ARQTMO:",  self._sb_arqtmo)
        self._sb_adelay  = spin(0, 250, 2);   form.addRow("ADELAY:",  self._sb_adelay)
        self._sb_ptdown  = spin(0, 250, 6);   form.addRow("PTDOWN:",  self._sb_ptdown)
        self._sb_ptup    = spin(0, 250, 3);   form.addRow("PTUP:",    self._sb_ptup)
        self._sb_pthuff  = spin(0, 10,  0);   form.addRow("PTHUFF:",  self._sb_pthuff)
        self._sb_ptsum   = spin(0, 250, 5);   form.addRow("PTSUM:",   self._sb_ptsum)
        self._sb_pttries = spin(0, 250, 2);   form.addRow("PTTRIES:", self._sb_pttries)

        self._hx_ptover  = HexSpinBox()
        self._hx_ptover.setValue(0x1A)
        form.addRow("PTOVER:", self._hx_ptover)

        self._dsb_ptsend = QDoubleSpinBox()
        self._dsb_ptsend.setRange(0.1, 9.9)
        self._dsb_ptsend.setSingleStep(0.1)
        self._dsb_ptsend.setDecimals(1)
        self._dsb_ptsend.setValue(1.2)
        form.addRow("PTSEND:", self._dsb_ptsend)

        # Read-only
        self._sb_qptor = spin(0, 99, 34); self._sb_qptor.setEnabled(False)
        form.addRow("QPTOR (r/o):", self._sb_qptor)

        row.addWidget(left)

        # Flags
        right = QGroupBox("Flags")
        fl = QVBoxLayout(right)
        self._chk_pt200   = QCheckBox("PT200");   self._chk_pt200.setChecked(True)
        self._chk_ptround = QCheckBox("PTROUND"); self._chk_ptround.setChecked(False)
        self._chk_xmitok  = QCheckBox("XMITOK");  self._chk_xmitok.setChecked(True)
        self._chk_8bitconv= QCheckBox("8BITCONV"); self._chk_8bitconv.setChecked(False)
        self._chk_afilter = QCheckBox("AFILTER");  self._chk_afilter.setChecked(False)
        self._chk_xgateway= QCheckBox("XGATEWAY"); self._chk_xgateway.setChecked(False)
        for w in [self._chk_pt200, self._chk_ptround, self._chk_xmitok,
                  self._chk_8bitconv, self._chk_afilter, self._chk_xgateway]:
            fl.addWidget(w)
        fl.addStretch()
        row.addWidget(right)
        root.addLayout(row)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

    def _populate(self) -> None:
        c = self._config
        self._le_myptcall.setText(c.myptcall)
        self._sb_arqtmo.setValue(c.arqtmo)
        self._sb_adelay.setValue(c.adelay)
        self._sb_ptdown.setValue(c.ptdown)
        self._sb_ptup.setValue(c.ptup)
        self._sb_pthuff.setValue(c.pthuff)
        self._sb_ptsum.setValue(c.ptsum)
        self._sb_pttries.setValue(c.pttries)
        self._hx_ptover.setValue(c.ptover)
        self._dsb_ptsend.setValue(c.ptsend)
        self._chk_pt200.setChecked(c.pt200)
        self._chk_ptround.setChecked(c.ptround)
        self._chk_xmitok.setChecked(c.xmitok)

    def apply_to(self, config: PACTORConfig) -> None:
        config.myptcall = self._le_myptcall.text().upper().strip()
        config.arqtmo   = self._sb_arqtmo.value()
        config.adelay   = self._sb_adelay.value()
        config.ptdown   = self._sb_ptdown.value()
        config.ptup     = self._sb_ptup.value()
        config.pthuff   = self._sb_pthuff.value()
        config.ptsum    = self._sb_ptsum.value()
        config.pttries  = self._sb_pttries.value()
        config.ptover   = self._hx_ptover.value()
        config.ptsend   = self._dsb_ptsend.value()
        config.pt200    = self._chk_pt200.isChecked()
        config.ptround  = self._chk_ptround.isChecked()
        config.xmitok   = self._chk_xmitok.isChecked()

    def _on_accept(self) -> None:
        self.apply_to(self._config)
        self.accept()