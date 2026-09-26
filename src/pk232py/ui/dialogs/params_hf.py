# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""HF Packet Parameter dialog — matches PCPackRatt 'HF Packet Parameters'.

Three tabs:
  Tab 1: Main parameters (numeric spinboxes + flag checkboxes)
  Tab 2: Message parameters (BTEXT, CTEXT, UNPROTO, CFROM, etc.)
  Tab 3: Display (P47/P50) — PC-side only, never uploaded to the TNC
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
        tabs.addTab(self._build_display_tab(), "Display")
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
        # TXSMT does not appear anywhere in the PK-232 TRM Host Mode command
        # list (P13) - likely a command from a different AEA product (PK-900,
        # DSP-2232). Disabled rather than removed: the field and its INI
        # entry stay so existing INI files keep loading cleanly, but nothing
        # is ever sent for it (see ParamsUploader / UPLOAD_EXEMPT).
        self._sb_txsmt.setEnabled(False)
        self._sb_txsmt.setToolTip("Not a PK-232 command — has no effect")
        self._sb_users    = spin(1, 10,  1);     form.addRow("USERS:",    self._sb_users)
        self._sb_users.setToolTip(
            "Maximum number of simultaneous AX.25 connections the TNC "
            "will accept.\nChannels above this number stay unused. "
            "Default 1."
        )

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
        # P55.F: these two are the TNC's OWN link-message timestamp
        # source - independent of the Display tab's "Show timestamps in
        # the RX view" (PK232PY's own added prefix). See that option's
        # own tooltip for the full explanation.
        _stamp_tip = (
            "Uploaded to the TNC (sent as {0} ON/OFF). When ON, the TNC "
            "itself prepends a date and/or time to every link message "
            "(e.g. \"*** 25-Sep-26 21:04:36 CONNECTED to OE3TEC ***\") - "
            "independent of the Display tab's \"Show timestamps in the "
            "RX view\" option, which only controls PK232PY's own added "
            "prefix."
        )
        self._chk_constamp.setToolTip(_stamp_tip.format("CONSTAMP"))
        self._chk_dagstamp.setToolTip(_stamp_tip.format("DAYSTAMP"))
        self._chk_ilfpack   = chk("ILFPACK",    True);  flags_layout.addWidget(self._chk_ilfpack)
        self._chk_acrpack   = chk("ACRPACK",    True);  flags_layout.addWidget(self._chk_acrpack)
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

        # CFROM / DFROM / MFROM / MTO — access filters (P13.3, TRM mnemonics
        # CF/DF/MF/MT). Mode is ALL/NONE/YES/NO; YES/NO additionally use the
        # comma-separated callsign list in the adjacent field (max 8 - see
        # _on_accept()). Defaults per PCPackRatt/TRM factory settings.
        for attr, label, default in [
            ("_cb_cfrom", "CFROM:", "ALL"),
            ("_cb_dfrom", "DFROM:", "ALL"),
            ("_cb_mfrom", "MFROM:", "ALL"),
            ("_cb_mto",   "MTO:",   "NONE"),
        ]:
            cb = QComboBox()
            cb.addItems(["ALL", "NONE", "YES", "NO"])
            cb.setCurrentText(default)
            row = QHBoxLayout()
            row.addWidget(cb)
            le = QLineEdit()
            le.setPlaceholderText("callsigns, comma-separated (YES/NO only)")
            le.setMaximumWidth(180)
            row.addWidget(le)
            setattr(self, attr, cb)
            setattr(self, attr + "_le", le)
            container = QWidget(); container.setLayout(row)
            form.addRow(label, container)

        self._cb_cfrom.setToolTip(
            "Access filter for incoming AX.25 connect requests.\n"
            "ALL = accept from anyone.\n"
            "NONE = rejects every incoming connect.\n"
            "YES = accept only from the listed callsigns.\n"
            "NO = reject the listed callsigns, accept everyone else."
        )

        self._le_mbx = QLineEdit()
        self._le_mbx.setPlaceholderText("None")
        form.addRow("MBX:", self._le_mbx)

        return w

    def _build_display_tab(self) -> QWidget:
        """PC-side display settings (P47) - never sent to the TNC."""
        w = QWidget()
        form = QFormLayout(w)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._chk_show_link_ui = QCheckBox(
            "Show TNC link messages in the UI channel"
        )
        self._chk_show_link_ui.setToolTip(
            "A link message (CONNECTED, DISCONNECTED, Retry count "
            "exceeded, ...) always appears in the channel it actually "
            "happened on. Turn this on to ALSO mirror every one of them "
            "into the UI channel (chip 0), tagged with the channel it "
            "came from, e.g. \"[ch1] *** DISCONNECTED: OE3XTC ***\" - "
            "useful when the UI channel is the one you keep watching.\n"
            "This is a display setting only; it is never sent to the TNC."
        )
        form.addRow(self._chk_show_link_ui)

        # P50 Teil C - optional timestamps in the RX view.
        self._chk_show_timestamps = QCheckBox("Show timestamps in the RX view")
        self._chk_show_timestamps.setToolTip(
            "Prepend \"[HH:MM:SS]\" (muted colour) to every RX line. Off "
            "by default - the CH view already names the channel via the "
            "chip, and the ALL view's own compact \"n|\" tag costs less "
            "width than a repeated timestamp on every line.\n"
            "This is a display setting only; it is never sent to the TNC.\n\n"
            "P55.F: link messages carry the TNC's OWN timestamp already "
            "(e.g. \"*** 25-Sep-26 21:04:36 CONNECTED to OE3TEC ***\") "
            "whenever CONSTAMP and/or DAGSTAMP (Parameters tab, both ON "
            "by default) are enabled on the TNC - that stamp is part of "
            "the message text itself and appears regardless of this "
            "option. This checkbox only controls the SEPARATE "
            "\"[HH:MM:SS]\" prefix PK232PY itself adds to every RX line "
            "(link messages included) - two independent sources of a "
            "timestamp in the same view, not one setting for both."
        )
        form.addRow(self._chk_show_timestamps)

        # P50 Teil B - per-channel RX document size cap.
        self._sb_rx_max_lines = QSpinBox()
        self._sb_rx_max_lines.setRange(100, 100000)
        self._sb_rx_max_lines.setSingleStep(500)
        self._sb_rx_max_lines.setToolTip(
            "Maximum number of lines kept per RX document (each channel's "
            "own history, and the merged ALL view) before the oldest "
            "lines are dropped - keeps a long operating day from growing "
            "memory without bound.\n"
            "This is a display setting only; it is never sent to the TNC."
        )
        form.addRow("Max. RX lines per channel:", self._sb_rx_max_lines)

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
        self._sb_users.setValue(c.users)
        self._sb_txsmt.setValue(c.txsmt)

        self._chk_ax25l2v2.setChecked(c.ax25l2v2)
        self._chk_headerln.setChecked(c.headerln)
        self._chk_constamp.setChecked(c.constamp)
        self._chk_dagstamp.setChecked(c.dagstamp)
        self._chk_ilfpack.setChecked(c.ilfpack)
        self._chk_acrpack.setChecked(c.acrpack)
        self._chk_alfpack.setChecked(c.alfpack)
        self._chk_mrpt.setChecked(c.mrpt)
        self._chk_ppersist.setChecked(c.ppersist)
        self._chk_xmitok.setChecked(c.xmitok)

        self._le_mycall.setText(c.mycall)
        self._le_btext.setText(c.btext)
        self._le_ctext.setText(c.ctext)
        self._le_unproto.setText(c.unproto)

        for cb_attr, mode, calls in [
            ("_cb_cfrom", c.cfrom_mode, c.cfrom_calls),
            ("_cb_dfrom", c.dfrom_mode, c.dfrom_calls),
            ("_cb_mfrom", c.mfrom_mode, c.mfrom_calls),
            ("_cb_mto",   c.mto_mode,   c.mto_calls),
        ]:
            cb = getattr(self, cb_attr)
            idx = cb.findText(mode)
            if idx >= 0:
                cb.setCurrentIndex(idx)
            getattr(self, cb_attr + "_le").setText(calls)

        self._chk_8bitconv.setChecked(c.bitconv8)
        self._chk_hid.setChecked(c.hid)
        self._chk_mbell.setChecked(c.mbell)

        self._chk_show_link_ui.setChecked(c.show_link_messages_in_ui_channel)
        self._chk_show_timestamps.setChecked(c.show_timestamps)
        self._sb_rx_max_lines.setValue(c.rx_max_lines_per_channel)

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
        config.users    = self._sb_users.value()
        config.txsmt    = self._sb_txsmt.value()

        config.ax25l2v2  = self._chk_ax25l2v2.isChecked()
        config.headerln  = self._chk_headerln.isChecked()
        config.constamp  = self._chk_constamp.isChecked()
        config.dagstamp  = self._chk_dagstamp.isChecked()
        config.ilfpack   = self._chk_ilfpack.isChecked()
        config.acrpack   = self._chk_acrpack.isChecked()
        config.alfpack   = self._chk_alfpack.isChecked()
        config.mrpt      = self._chk_mrpt.isChecked()
        config.ppersist  = self._chk_ppersist.isChecked()
        config.xmitok    = self._chk_xmitok.isChecked()

        config.mycall  = self._le_mycall.text().upper().strip()
        config.btext   = self._le_btext.text()
        config.ctext   = self._le_ctext.text()
        config.unproto = self._le_unproto.text()

        config.cfrom_mode  = self._cb_cfrom.currentText()
        config.cfrom_calls = self._cb_cfrom_le.text().strip().upper()
        config.dfrom_mode  = self._cb_dfrom.currentText()
        config.dfrom_calls = self._cb_dfrom_le.text().strip().upper()
        config.mfrom_mode  = self._cb_mfrom.currentText()
        config.mfrom_calls = self._cb_mfrom_le.text().strip().upper()
        config.mto_mode    = self._cb_mto.currentText()
        config.mto_calls   = self._cb_mto_le.text().strip().upper()

        config.bitconv8 = self._chk_8bitconv.isChecked()
        config.hid      = self._chk_hid.isChecked()
        config.mbell    = self._chk_mbell.isChecked()

        config.show_link_messages_in_ui_channel = \
            self._chk_show_link_ui.isChecked()
        config.show_timestamps = self._chk_show_timestamps.isChecked()
        config.rx_max_lines_per_channel = self._sb_rx_max_lines.value()

    def _on_accept(self) -> None:
        # Validate the four access-filter callsign lists before writing
        # anything back — max 8 callsigns each (P13.3).
        for le_attr, label in [
            ("_cb_cfrom_le", "CFROM"), ("_cb_dfrom_le", "DFROM"),
            ("_cb_mfrom_le", "MFROM"), ("_cb_mto_le", "MTO"),
        ]:
            calls = [c for c in getattr(self, le_attr).text().split(",") if c.strip()]
            if len(calls) > 8:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self, "Too many callsigns",
                    f"{label}: at most 8 callsigns are allowed "
                    f"(found {len(calls)})."
                )
                return
        self.apply_to(self._config)
        self.accept()