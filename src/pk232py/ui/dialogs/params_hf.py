# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""HF Packet Parameter dialog — matches PCPackRatt 'HF Packet Parameters'.

Two tabs:
  Tab 1: Main parameters (numeric spinboxes + flag checkboxes)
  Tab 2: Message parameters (BTEXT, CTEXT, UNPROTO, CFROM, etc.)
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea, QSpinBox,
    QTabWidget, QVBoxLayout, QWidget,
)

from pk232py.config import HFPacketConfig

logger = logging.getLogger(__name__)


class HFPacketParamsDialog(QDialog):
    """HF Packet Parameters dialog.

    Matches the PCPackRatt 'HF Packet Parameters' dialog.
    Parameters are stored in :class:`~pk232py.config.HFPacketConfig`.

    Usage::

        dlg = HFPacketParamsDialog(config.hf_packet, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            dlg.apply_to(config.hf_packet)
    """

    def __init__(
        self,
        config: HFPacketConfig,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self.setWindowTitle("HF Packet Parameters")
        self.setMinimumWidth(600)
        self.setModal(True)
        self._build_ui()
        self._populate()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        tabs = QTabWidget()
        tabs.addTab(self._build_main_tab(),    "Parameters")
        tabs.addTab(self._build_msg_tab(),     "Message Params")
        root.addWidget(tabs)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

    def _build_main_tab(self) -> QWidget:
        """Main parameters tab — numeric params + flag checkboxes."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        layout = QHBoxLayout(inner)

        # ── Left column: numeric parameters ───────────────────────────
        left = QGroupBox("Parameters")
        form = QFormLayout(left)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        def spin(lo, hi, val):
            w = QSpinBox(); w.setRange(lo, hi); w.setValue(val); return w

        self._sb_paclen   = spin(1, 255, 64);    form.addRow("PACLEN:",   self._sb_paclen)
        self._sb_txdelay  = spin(0, 255, 30);    form.addRow("TXDELAY:",  self._sb_txdelay)
        self._sb_maxframe = spin(1, 7,   1);     form.addRow("MAXFRAME:", self._sb_maxframe)
        self._sb_frack    = spin(0, 250, 7);     form.addRow("FRACK:",    self._sb_frack)
        self._sb_retry    = spin(0, 15,  10);    form.addRow("RETRY:",    self._sb_retry)
        self._sb_persist  = spin(0, 255, 63);    form.addRow("PERSIST:",  self._sb_persist)
        self._sb_slottime = spin(0, 250, 30);    form.addRow("SLOTTIME:", self._sb_slottime)
        self._sb_dwait    = spin(0, 250, 16);    form.addRow("DWAIT:",    self._sb_dwait)
        self._sb_check    = spin(0, 250, 30);    form.addRow("CHECK:",    self._sb_check)
        self._sb_monitor  = spin(0, 6,   4);     form.addRow("MONITOR:",  self._sb_monitor)
        self._sb_resptime = spin(0, 250, 0);     form.addRow("RESPTIME:", self._sb_resptime)
        self._sb_txsmt    = spin(0, 250, 50);    form.addRow("TXSMT:",    self._sb_txsmt)
        self._sb_users    = spin(0, 26,  1);     form.addRow("USERS:",    self._sb_users)

        # Read-only fields
        self._sb_qhpacket = spin(0, 99, 33); self._sb_qhpacket.setEnabled(False)
        form.addRow("QHPACKET (r/o):", self._sb_qhpacket)
        self._sb_qvpacket = spin(0, 99, 35); self._sb_qvpacket.setEnabled(False)
        form.addRow("QVPACKET (r/o):", self._sb_qvpacket)

        layout.addWidget(left)

        # ── Right column: flag checkboxes ──────────────────────────────
        right = QGroupBox("Flags")
        flags_layout = QVBoxLayout(right)

        def chk(label, default=False):
            w = QCheckBox(label); w.setChecked(default); return w

        self._chk_ax25l2v2  = chk("AX25L2V2",  True);  flags_layout.addWidget(self._chk_ax25l2v2)
        self._chk_headerln  = chk("HEADERLN",   True);  flags_layout.addWidget(self._chk_headerln)
        self._chk_constamp  = chk("CONSTAMP",   True);  flags_layout.addWidget(self._chk_constamp)
        self._chk_dagstamp  = chk("DAGSTAMP",   True);  flags_layout.addWidget(self._chk_dagstamp)
        self._chk_ilfpack   = chk("ILFPACK",    True);  flags_layout.addWidget(self._chk_ilfpack)
        self._chk_aerpack   = chk("AERPACK",    True);  flags_layout.addWidget(self._chk_aerpack)
        self._chk_alfpack   = chk("ALFPACK",    True);  flags_layout.addWidget(self._chk_alfpack)
        self._chk_mrpt      = chk("MRPT",       True);  flags_layout.addWidget(self._chk_mrpt)
        self._chk_ppersist  = chk("PPERSIST",   True);  flags_layout.addWidget(self._chk_ppersist)
        self._chk_xmitok    = chk("XMITOK",     True);  flags_layout.addWidget(self._chk_xmitok)
        self._chk_8bitconv  = chk("8BITCONV",   False); flags_layout.addWidget(self._chk_8bitconv)
        self._chk_mbell     = chk("MBELL",      False); flags_layout.addWidget(self._chk_mbell)
        self._chk_mdigi     = chk("MDIGI",      False); flags_layout.addWidget(self._chk_mdigi)
        self._chk_mproto    = chk("MPROTO",     False); flags_layout.addWidget(self._chk_mproto)
        self._chk_mstamp    = chk("MSTAMP",     False); flags_layout.addWidget(self._chk_mstamp)
        self._chk_passall   = chk("PASSALL",    False); flags_layout.addWidget(self._chk_passall)
        self._chk_hid       = chk("HID",        False); flags_layout.addWidget(self._chk_hid)
        self._chk_bbsmsgs   = chk("BBSMSGS",    False); flags_layout.addWidget(self._chk_bbsmsgs)
        self._chk_fulldp    = chk("FULLDP",     False); flags_layout.addWidget(self._chk_fulldp)
        flags_layout.addStretch()

        layout.addWidget(right)
        scroll.setWidget(inner)
        return scroll

    def _build_msg_tab(self) -> QWidget:
        """Message parameters tab — BTEXT, CTEXT, UNPROTO, etc."""
        w = QWidget()
        form = QFormLayout(w)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._le_mycall  = QLineEdit(); form.addRow("MYCALL:",  self._le_mycall)
        self._le_btext   = QLineEdit(); form.addRow("BTEXT:",   self._le_btext)
        self._le_ctext   = QLineEdit(); form.addRow("CTEXT:",   self._le_ctext)
        self._le_unproto = QLineEdit(); form.addRow("UNPROTO:", self._le_unproto)

        form.addRow(QLabel(""))  # spacer

        # CFROM / DFROM / MFROM / MTO — filter combos
        for attr, label, default in [
            ("_cb_cfrom", "CFROM:", "All"),
            ("_cb_dfrom", "DFROM:", "All"),
            ("_cb_mfrom", "MFROM:", "All"),
            ("_cb_mto",   "MTO:",   "None"),
        ]:
            cb = QComboBox()
            cb.addItems(["All", "None", "Callsign..."])
            cb.setCurrentText(default)
            row = QHBoxLayout()
            row.addWidget(cb)
            le = QLineEdit()
            le.setPlaceholderText("callsign filter")
            le.setMaximumWidth(150)
            row.addWidget(le)
            setattr(self, attr, cb)
            setattr(self, attr + "_le", le)
            container = QWidget(); container.setLayout(row)
            form.addRow(label, container)

        self._le_mbx = QLineEdit()
        self._le_mbx.setPlaceholderText("None")
        form.addRow("MBX:", self._le_mbx)

        return w

    # ------------------------------------------------------------------
    # Populate / apply
    # ------------------------------------------------------------------

    def _populate(self) -> None:
        """Fill widgets from config."""
        c = self._config
        self._sb_paclen.setValue(c.paclen)
        self._sb_txdelay.setValue(c.txdelay)
        self._sb_maxframe.setValue(c.maxframe)
        self._sb_frack.setValue(c.frack)
        self._sb_retry.setValue(c.retry)
        self._sb_persist.setValue(c.persist)
        self._sb_slottime.setValue(c.slottime)
        self._sb_dwait.setValue(c.dwait)
        self._sb_check.setValue(c.check)
        self._sb_monitor.setValue(c.monitor)
        self._sb_resptime.setValue(c.resptime)
        self._sb_users.setValue(1)

        self._chk_ax25l2v2.setChecked(c.ax25l2v2)
        self._chk_headerln.setChecked(c.headerln)
        self._chk_constamp.setChecked(c.constamp)
        self._chk_dagstamp.setChecked(c.dagstamp)
        self._chk_ilfpack.setChecked(c.ilfpack)
        self._chk_aerpack.setChecked(c.aerpack)
        self._chk_alfpack.setChecked(c.alfpack)
        self._chk_mrpt.setChecked(c.mrpt)
        self._chk_ppersist.setChecked(c.ppersist)
        self._chk_xmitok.setChecked(c.xmitok)

        self._le_mycall.setText(c.mycall)
        self._le_btext.setText(c.btext)
        self._le_ctext.setText(c.ctext)
        self._le_unproto.setText(c.unproto)

    def apply_to(self, config: HFPacketConfig) -> None:
        """Write dialog values back into config."""
        config.paclen   = self._sb_paclen.value()
        config.txdelay  = self._sb_txdelay.value()
        config.maxframe = self._sb_maxframe.value()
        config.frack    = self._sb_frack.value()
        config.retry    = self._sb_retry.value()
        config.persist  = self._sb_persist.value()
        config.slottime = self._sb_slottime.value()
        config.dwait    = self._sb_dwait.value()
        config.check    = self._sb_check.value()
        config.monitor  = self._sb_monitor.value()
        config.resptime = self._sb_resptime.value()

        config.ax25l2v2  = self._chk_ax25l2v2.isChecked()
        config.headerln  = self._chk_headerln.isChecked()
        config.constamp  = self._chk_constamp.isChecked()
        config.dagstamp  = self._chk_dagstamp.isChecked()
        config.ilfpack   = self._chk_ilfpack.isChecked()
        config.aerpack   = self._chk_aerpack.isChecked()
        config.alfpack   = self._chk_alfpack.isChecked()
        config.mrpt      = self._chk_mrpt.isChecked()
        config.ppersist  = self._chk_ppersist.isChecked()
        config.xmitok    = self._chk_xmitok.isChecked()

        config.mycall  = self._le_mycall.text().upper().strip()
        config.btext   = self._le_btext.text()
        config.ctext   = self._le_ctext.text()
        config.unproto = self._le_unproto.text()

    def _on_accept(self) -> None:
        self.apply_to(self._config)
        self.accept()