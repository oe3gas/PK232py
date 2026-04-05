# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""TNC Configuration dialog.

Corresponds to the 'TNC Configuration' dialog in PCPackRatt for Windows.
Allows the user to select:
    - TNC model (PK232MBX / PK232 / ...)
    - Serial port (COM1 … / /dev/ttyUSB0 …)
    - TBaud rate (2400 / 4800 / 9600 / 19200)
    - Various initialisation flags

TODO (v0.2): Wire Save/Load buttons to ConfigManager.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QComboBox,
    QCheckBox,
    QPushButton,
)

from pk232py.comm.serial_port import list_ports
from pk232py.config import TNCConfig

logger = logging.getLogger(__name__)

SUPPORTED_MODELS  = ["PK232MBX", "PK232"]
SUPPORTED_TBAUDS  = ["2400", "4800", "9600", "19200"]


class TNCConfigDialog(QDialog):
    """TNC Configuration dialog.

    Args:
        config: Current TNC configuration (will be modified in-place on accept).
        parent: Parent widget.
    """

    def __init__(self, config: TNCConfig, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self.setWindowTitle("TNC Configuration")
        self.setModal(True)
        self._build_ui()
        self._load_from_config()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # ── Top row: Model / Port / TBaud ─────────────────────────────
        top = QHBoxLayout()

        model_box = QGroupBox("TNC Model")
        ml = QVBoxLayout(model_box)
        self._cb_model = QComboBox()
        self._cb_model.addItems(SUPPORTED_MODELS)
        ml.addWidget(self._cb_model)
        top.addWidget(model_box)

        port_box = QGroupBox("Com Port")
        pl = QVBoxLayout(port_box)
        self._cb_port = QComboBox()
        self._cb_port.addItem("NONE")
        self._cb_port.addItems(list_ports())
        self._cb_port.setEditable(True)
        pl.addWidget(self._cb_port)
        top.addWidget(port_box)

        baud_box = QGroupBox("TBaud")
        bl = QVBoxLayout(baud_box)
        self._cb_tbaud = QComboBox()
        self._cb_tbaud.addItems(SUPPORTED_TBAUDS)
        bl.addWidget(self._cb_tbaud)
        top.addWidget(baud_box)

        root.addLayout(top)

        # ── Option checkboxes ──────────────────────────────────────────
        opts = QGroupBox("Options")
        ol = QVBoxLayout(opts)
        self._chk_echo_packets    = QCheckBox("Echo Packets")
        self._chk_utc_time        = QCheckBox("UTC TNC Time")
        self._chk_fast_init       = QCheckBox("Fast Initialization")
        self._chk_host_on_exit    = QCheckBox("Host Mode On Exit")
        self._chk_save_maildrop   = QCheckBox("Save/Restore MailDrop")
        self._chk_dumb_term       = QCheckBox("Dumb Term Initialization")
        self._chk_show_unk_err    = QCheckBox("Show Unknown Command Errors")
        self._chk_show_conn_err   = QCheckBox("Show Not While Connected Errors")
        self._chk_auto_qso        = QCheckBox("Auto QSO Check")
        for chk in (
            self._chk_echo_packets, self._chk_utc_time, self._chk_fast_init,
            self._chk_host_on_exit, self._chk_save_maildrop, self._chk_dumb_term,
            self._chk_show_unk_err, self._chk_show_conn_err, self._chk_auto_qso,
        ):
            ol.addWidget(chk)
        root.addWidget(opts)

        # ── Buttons ────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._btn_save = QPushButton("Save")
        self._btn_load = QPushButton("Load")
        self._btn_save.clicked.connect(self._on_save)
        self._btn_load.clicked.connect(self._on_load)
        btn_row.addWidget(self._btn_save)
        btn_row.addWidget(self._btn_load)
        btn_row.addStretch()
        root.addLayout(btn_row)

        # ── OK / Cancel ───────────────────────────────────────────────
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

    # ------------------------------------------------------------------
    # Load / save between dialog widgets and TNCConfig
    # ------------------------------------------------------------------

    def _load_from_config(self) -> None:
        idx = self._cb_model.findText(self._config.model)
        if idx >= 0:
            self._cb_model.setCurrentIndex(idx)

        port_idx = self._cb_port.findText(self._config.port)
        if port_idx >= 0:
            self._cb_port.setCurrentIndex(port_idx)
        else:
            self._cb_port.setCurrentText(self._config.port)

        baud_idx = self._cb_tbaud.findText(str(self._config.tbaud))
        if baud_idx >= 0:
            self._cb_tbaud.setCurrentIndex(baud_idx)

        self._chk_echo_packets.setChecked(self._config.echo_packets)
        self._chk_utc_time.setChecked(self._config.utc_time)
        self._chk_fast_init.setChecked(self._config.fast_init)
        self._chk_host_on_exit.setChecked(self._config.host_mode_on_exit)
        self._chk_save_maildrop.setChecked(self._config.save_restore_maildrop)
        self._chk_dumb_term.setChecked(self._config.dumb_term_init)
        self._chk_show_unk_err.setChecked(self._config.show_unknown_cmd_errors)
        self._chk_show_conn_err.setChecked(self._config.show_not_while_connected_errors)
        self._chk_auto_qso.setChecked(self._config.auto_qso_check)

    def _save_to_config(self) -> None:
        self._config.model             = self._cb_model.currentText()
        self._config.port              = self._cb_port.currentText()
        self._config.tbaud             = int(self._cb_tbaud.currentText())
        self._config.echo_packets      = self._chk_echo_packets.isChecked()
        self._config.utc_time          = self._chk_utc_time.isChecked()
        self._config.fast_init         = self._chk_fast_init.isChecked()
        self._config.host_mode_on_exit = self._chk_host_on_exit.isChecked()
        self._config.save_restore_maildrop = self._chk_save_maildrop.isChecked()
        self._config.dumb_term_init    = self._chk_dumb_term.isChecked()
        self._config.show_unknown_cmd_errors = self._chk_show_unk_err.isChecked()
        self._config.show_not_while_connected_errors = self._chk_show_conn_err.isChecked()
        self._config.auto_qso_check    = self._chk_auto_qso.isChecked()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_accept(self) -> None:
        self._save_to_config()
        self.accept()

    def _on_save(self) -> None:
        self._save_to_config()
        logger.info("TNC config saved via dialog Save button")

    def _on_load(self) -> None:
        self._load_from_config()
        logger.info("TNC config reloaded via dialog Load button")
