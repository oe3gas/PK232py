# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""BAUDOT / ASCII / CW (Morse) Parameters dialog — matches PCPackRatt."""

from __future__ import annotations
import logging
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QSpinBox, QVBoxLayout, QWidget,
)

logger = logging.getLogger(__name__)


class HexSpinBox(QSpinBox):
    def __init__(self, p=None):
        super().__init__(p); self.setRange(0,127)
        self.setPrefix("$"); self.setDisplayIntegerBase(16)
    def textFromValue(self, v): return format(v, '02X')
    def valueFromText(self, t):
        try: return int(t.lstrip('$').lstrip('0x') or '0', 16)
        except ValueError: return 0


class BaudotParamsDialog(QDialog):
    """BAUDOT / ASCII / CW Parameters dialog matching PCPackRatt layout."""

    DEFAULTS = dict(
        acrtty=0, atxrtty=0, audelay=2, code=0,
        errchar=0x5F, mspeed=20, mweight=10,
        xbaud=0, xlength=64, ubit="", aab="",
        # flags
        alfrtty=True, diddle=True, mopt=True, xmitok=True,
        afilter=False, cradd=False, marsdisp=False,
        rframe=False, rxrev=False, txrev=False,
        usos=False, wideshft=False, wru=False,
    )

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("BAUDOT / ASCII / CW Parameters")
        self.setMinimumWidth(520)
        self.setModal(True)
        self._build_ui()
        self.set_values(**self.DEFAULTS)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        row  = QHBoxLayout()

        # ── Left: parameters ─────────────────────────────────────────
        left = QGroupBox("Parameters")
        form = QFormLayout(left)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        def spin(lo, hi, val):
            w = QSpinBox(); w.setRange(lo, hi); w.setValue(val); return w

        self._sb_acrtty  = spin(0, 250, 0);  form.addRow("ACRTTY:",  self._sb_acrtty)
        self._sb_atxrtty = spin(0, 250, 0);  form.addRow("ATXRTTY:", self._sb_atxrtty)
        self._sb_audelay = spin(0, 250, 2);  form.addRow("AUDELAY:", self._sb_audelay)
        self._sb_code    = spin(0, 8,   0);  form.addRow("CODE:",    self._sb_code)
        self._hx_errchar = HexSpinBox(); self._hx_errchar.setValue(0x5F)
        form.addRow("ERRCHAR:", self._hx_errchar)
        self._sb_mspeed  = spin(5, 99,  20); form.addRow("MSPEED:",  self._sb_mspeed)
        self._sb_mweight = spin(10,90,  10); form.addRow("MWEIGHT:", self._sb_mweight)
        self._sb_xbaud   = spin(0, 300, 0);  form.addRow("XBAUD:",   self._sb_xbaud)
        self._sb_xlength = spin(0, 255, 64); form.addRow("XLENGTH:", self._sb_xlength)
        self._le_ubit    = QLineEdit(); form.addRow("UBIT:", self._le_ubit)
        self._le_aab     = QLineEdit(); form.addRow("AAB:",  self._le_aab)

        # Read-only
        self._sb_qmorse = spin(0,99,40); self._sb_qmorse.setEnabled(False)
        form.addRow("QMORSE (r/o):", self._sb_qmorse)
        self._sb_qrtty  = spin(0,99,31); self._sb_qrtty.setEnabled(False)
        form.addRow("QRTTY (r/o):",  self._sb_qrtty)
        self._sb_qwide  = spin(0,99,7);  self._sb_qwide.setEnabled(False)
        form.addRow("QWIDE (r/o):",  self._sb_qwide)

        row.addWidget(left)

        # ── Right: flags ─────────────────────────────────────────────
        right = QGroupBox("Flags")
        fl = QVBoxLayout(right)
        self._chk_alfrtty  = QCheckBox("ALFRTTY");  self._chk_alfrtty.setChecked(True)
        self._chk_diddle   = QCheckBox("DIDDLE");   self._chk_diddle.setChecked(True)
        self._chk_mopt     = QCheckBox("MOPT");     self._chk_mopt.setChecked(True)
        self._chk_xmitok   = QCheckBox("XMITOK");  self._chk_xmitok.setChecked(True)
        self._chk_afilter  = QCheckBox("AFILTER");  self._chk_afilter.setChecked(False)
        self._chk_cradd    = QCheckBox("CRADD");    self._chk_cradd.setChecked(False)
        self._chk_marsdisp = QCheckBox("MARSDISP"); self._chk_marsdisp.setChecked(False)
        self._chk_rframe   = QCheckBox("RFRAME");   self._chk_rframe.setChecked(False)
        self._chk_rxrev    = QCheckBox("RXREV");    self._chk_rxrev.setChecked(False)
        self._chk_txrev    = QCheckBox("TXREV");    self._chk_txrev.setChecked(False)
        self._chk_usos     = QCheckBox("USOS");     self._chk_usos.setChecked(False)
        self._chk_wideshft = QCheckBox("WIDESHFT"); self._chk_wideshft.setChecked(False)
        self._chk_wru      = QCheckBox("WRU");      self._chk_wru.setChecked(False)
        for w in [self._chk_alfrtty, self._chk_diddle, self._chk_mopt,
                  self._chk_xmitok, self._chk_afilter, self._chk_cradd,
                  self._chk_marsdisp, self._chk_rframe, self._chk_rxrev,
                  self._chk_txrev, self._chk_usos, self._chk_wideshft, self._chk_wru]:
            fl.addWidget(w)
        fl.addStretch()
        row.addWidget(right)
        root.addLayout(row)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

    def set_values(self, **kw) -> None:
        if "acrtty"  in kw: self._sb_acrtty.setValue(int(kw["acrtty"]))
        if "atxrtty" in kw: self._sb_atxrtty.setValue(int(kw["atxrtty"]))
        if "audelay" in kw: self._sb_audelay.setValue(int(kw["audelay"]))
        if "code"    in kw: self._sb_code.setValue(int(kw["code"]))
        if "errchar" in kw: self._hx_errchar.setValue(int(kw["errchar"]))
        if "mspeed"  in kw: self._sb_mspeed.setValue(int(kw["mspeed"]))
        if "mweight" in kw: self._sb_mweight.setValue(int(kw["mweight"]))
        if "xbaud"   in kw: self._sb_xbaud.setValue(int(kw["xbaud"]))
        if "xlength" in kw: self._sb_xlength.setValue(int(kw["xlength"]))
        if "ubit"    in kw: self._le_ubit.setText(str(kw["ubit"]))
        if "aab"     in kw: self._le_aab.setText(str(kw["aab"]))
        for attr, key in [
            ("_chk_alfrtty","alfrtty"),("_chk_diddle","diddle"),
            ("_chk_mopt","mopt"),("_chk_xmitok","xmitok"),
            ("_chk_afilter","afilter"),("_chk_cradd","cradd"),
            ("_chk_marsdisp","marsdisp"),("_chk_rframe","rframe"),
            ("_chk_rxrev","rxrev"),("_chk_txrev","txrev"),
            ("_chk_usos","usos"),("_chk_wideshft","wideshft"),("_chk_wru","wru"),
        ]:
            if key in kw: getattr(self, attr).setChecked(bool(kw[key]))

    def get_values(self) -> dict:
        return dict(
            acrtty   = self._sb_acrtty.value(),
            atxrtty  = self._sb_atxrtty.value(),
            audelay  = self._sb_audelay.value(),
            code     = self._sb_code.value(),
            errchar  = self._hx_errchar.value(),
            mspeed   = self._sb_mspeed.value(),
            mweight  = self._sb_mweight.value(),
            xbaud    = self._sb_xbaud.value(),
            xlength  = self._sb_xlength.value(),
            ubit     = self._le_ubit.text(),
            aab      = self._le_aab.text(),
            alfrtty  = self._chk_alfrtty.isChecked(),
            diddle   = self._chk_diddle.isChecked(),
            mopt     = self._chk_mopt.isChecked(),
            xmitok   = self._chk_xmitok.isChecked(),
            afilter  = self._chk_afilter.isChecked(),
            cradd    = self._chk_cradd.isChecked(),
            marsdisp = self._chk_marsdisp.isChecked(),
            rframe   = self._chk_rframe.isChecked(),
            rxrev    = self._chk_rxrev.isChecked(),
            txrev    = self._chk_txrev.isChecked(),
            usos     = self._chk_usos.isChecked(),
            wideshft = self._chk_wideshft.isChecked(),
            wru      = self._chk_wru.isChecked(),
        )