# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""AMTOR / NAVTEX / TDM Parameters dialog — matches PCPackRatt layout."""

from __future__ import annotations
import logging
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QSpinBox, QVBoxLayout, QWidget,
)

from pk232py.ui.dialogs.firmware_limits import apply_firmware_limits

from pk232py.ui.dialogs.param_order import add_flags, add_form_rows

logger = logging.getLogger(__name__)


class HexSpinBox(QSpinBox):
    def __init__(self, p=None):
        super().__init__(p); self.setRange(0,127)
        self.setPrefix("$"); self.setDisplayIntegerBase(16)
    def textFromValue(self, v): return format(v, '02X')
    def valueFromText(self, t):
        try: return int(t.lstrip('$').lstrip('0x') or '0', 16)
        except ValueError: return 0


class AMTORParamsDialog(QDialog):
    """AMTOR / NAVTEX / TDM Parameters dialog.

    Covers all three modes in one dialog, matching PCPackRatt.
    Values are stored/retrieved via get_values() / set_values().
    """

    DEFAULTS = dict(
        myselcal="", myaltcal="", myident="",
        aab="", adelay=2, arqtmo=60, arqtol=3,
        code=0, errchar=0x5F, gusers=0, mid=0,
        mweight=10, tdbaud=96, tdchan=0,
        xlength=64,
        navmsg="ALL", navstn="ALL",
        # flags
        rfec=True, rxrev=False, srxall=False, txrev=False,
        usos=False, wideshft=False, xmitok=True,
        afilter=False, marsdisp=False,
    )

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("AMTOR / NAVTEX / TDM Parameters")
        self.setMinimumWidth(560)
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

        # P87: the rows are listed here in any order and placed by add_form_rows()
        # (alphabetical, param_order.py). Only the read-only values form a block of
        # their own, after the inputs.
        self._le_myselcal = QLineEdit(); self._le_myselcal.setMaximumWidth(80)
        self._le_myaltcal = QLineEdit(); self._le_myaltcal.setMaximumWidth(80)
        self._le_myident  = QLineEdit(); self._le_myident.setMaximumWidth(100)
        self._le_aab      = QLineEdit()
        self._sb_adelay  = spin(0, 250, 2)
        self._sb_arqtmo  = spin(0, 250, 60)
        self._sb_arqtol  = spin(1, 5,   3)
        self._sb_code    = spin(0, 8,   0)
        self._hx_errchar = HexSpinBox(); self._hx_errchar.setValue(0x5F)
        self._sb_gusers  = spin(0, 99,  0)
        self._sb_mid     = spin(0, 99,  0)
        self._sb_mweight = spin(10, 90, 10)
        self._sb_xlength = spin(0, 255, 64)
        # NAVTEX filter
        self._le_navmsg = QLineEdit(); self._le_navmsg.setText("ALL")
        self._le_navstn = QLineEdit(); self._le_navstn.setText("ALL")
        # TDM
        self._sb_tdbaud = spin(0, 200, 96)
        self._sb_tdchan = spin(0, 3,   0)
        add_form_rows(form, [
            ("MYSELCAL:", self._le_myselcal), ("MYALTCAL:", self._le_myaltcal),
            ("MYIDENT:", self._le_myident), ("AAB:", self._le_aab),
            ("ADELAY:", self._sb_adelay), ("ARQTMO:", self._sb_arqtmo),
            ("ARQTOL:", self._sb_arqtol), ("CODE:", self._sb_code),
            ("ERRCHAR:", self._hx_errchar), ("GUSERS:", self._sb_gusers),
            ("MID:", self._sb_mid), ("MWEIGHT:", self._sb_mweight),
            ("XLENGTH:", self._sb_xlength), ("NAVMSG:", self._le_navmsg),
            ("NAVSTN:", self._le_navstn), ("TDBAUD:", self._sb_tdbaud),
            ("TDCHAN:", self._sb_tdchan),
        ])

        # Read-only (a block of its own, below the inputs)
        self._sb_qtdm = spin(0,99,3); self._sb_qtdm.setEnabled(False)
        self._sb_qtor = spin(0,99,31); self._sb_qtor.setEnabled(False)
        add_form_rows(form, [("QTDM (r/o):", self._sb_qtdm), ("QTOR (r/o):", self._sb_qtor)])

        row.addWidget(left)

        # ── Right: flags ─────────────────────────────────────────────
        right = QGroupBox("Flags")
        fl = QVBoxLayout(right)
        self._chk_rfec     = QCheckBox("RFEC");     self._chk_rfec.setChecked(True)
        self._chk_rxrev    = QCheckBox("RXREV");    self._chk_rxrev.setChecked(False)
        self._chk_srxall   = QCheckBox("SRXALL");   self._chk_srxall.setChecked(False)
        self._chk_txrev    = QCheckBox("TXREV");    self._chk_txrev.setChecked(False)
        self._chk_usos     = QCheckBox("USOS");     self._chk_usos.setChecked(False)
        self._chk_wideshft = QCheckBox("WIDESHFT"); self._chk_wideshft.setChecked(False)
        self._chk_xmitok   = QCheckBox("XMITOK");  self._chk_xmitok.setChecked(True)
        self._chk_afilter  = QCheckBox("AFILTER");  self._chk_afilter.setChecked(False)
        self._chk_marsdisp = QCheckBox("MARSDISP"); self._chk_marsdisp.setChecked(False)
        add_flags(fl, [self._chk_rfec, self._chk_rxrev, self._chk_srxall,
                       self._chk_txrev, self._chk_usos, self._chk_wideshft,
                       self._chk_xmitok, self._chk_afilter, self._chk_marsdisp])
        fl.addStretch()
        row.addWidget(right)
        root.addLayout(row)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

    def apply_firmware_limits(self, release) -> None:
        """P85 C: grey out what firmware *release* does not know (ARQTOL)."""
        apply_firmware_limits(release, {"ARQTOL": self._sb_arqtol})

    def set_values(self, **kw) -> None:
        if "myselcal"  in kw: self._le_myselcal.setText(str(kw["myselcal"]).upper())
        if "myaltcal"  in kw: self._le_myaltcal.setText(str(kw["myaltcal"]).upper())
        if "myident"   in kw: self._le_myident.setText(str(kw["myident"]).upper())
        if "aab"       in kw: self._le_aab.setText(str(kw["aab"]))
        if "adelay"    in kw: self._sb_adelay.setValue(int(kw["adelay"]))
        if "arqtmo"    in kw: self._sb_arqtmo.setValue(int(kw["arqtmo"]))
        if "arqtol"    in kw: self._sb_arqtol.setValue(int(kw["arqtol"]))
        if "code"      in kw: self._sb_code.setValue(int(kw["code"]))
        if "errchar"   in kw: self._hx_errchar.setValue(int(kw["errchar"]))
        if "gusers"    in kw: self._sb_gusers.setValue(int(kw["gusers"]))
        if "mid"       in kw: self._sb_mid.setValue(int(kw["mid"]))
        if "mweight"   in kw: self._sb_mweight.setValue(int(kw["mweight"]))
        if "xlength"   in kw: self._sb_xlength.setValue(int(kw["xlength"]))
        if "navmsg"    in kw: self._le_navmsg.setText(str(kw["navmsg"]).upper())
        if "navstn"    in kw: self._le_navstn.setText(str(kw["navstn"]).upper())
        if "tdbaud"    in kw: self._sb_tdbaud.setValue(int(kw["tdbaud"]))
        if "tdchan"    in kw: self._sb_tdchan.setValue(int(kw["tdchan"]))
        for attr, key in [
            ("_chk_rfec","rfec"),("_chk_rxrev","rxrev"),("_chk_srxall","srxall"),
            ("_chk_txrev","txrev"),("_chk_usos","usos"),("_chk_wideshft","wideshft"),
            ("_chk_xmitok","xmitok"),("_chk_afilter","afilter"),("_chk_marsdisp","marsdisp"),
        ]:
            if key in kw: getattr(self, attr).setChecked(bool(kw[key]))

    def get_values(self) -> dict:
        return dict(
            myselcal  = self._le_myselcal.text().upper(),
            myaltcal  = self._le_myaltcal.text().upper(),
            myident   = self._le_myident.text().upper(),
            aab       = self._le_aab.text(),
            adelay    = self._sb_adelay.value(),
            arqtmo    = self._sb_arqtmo.value(),
            arqtol    = self._sb_arqtol.value(),
            code      = self._sb_code.value(),
            errchar   = self._hx_errchar.value(),
            gusers    = self._sb_gusers.value(),
            mid       = self._sb_mid.value(),
            mweight   = self._sb_mweight.value(),
            xlength   = self._sb_xlength.value(),
            navmsg    = self._le_navmsg.text().upper(),
            navstn    = self._le_navstn.text().upper(),
            tdbaud    = self._sb_tdbaud.value(),
            tdchan    = self._sb_tdchan.value(),
            rfec      = self._chk_rfec.isChecked(),
            rxrev     = self._chk_rxrev.isChecked(),
            srxall    = self._chk_srxall.isChecked(),
            txrev     = self._chk_txrev.isChecked(),
            usos      = self._chk_usos.isChecked(),
            wideshft  = self._chk_wideshft.isChecked(),
            xmitok    = self._chk_xmitok.isChecked(),
            afilter   = self._chk_afilter.isChecked(),
            marsdisp  = self._chk_marsdisp.isChecked(),
        )