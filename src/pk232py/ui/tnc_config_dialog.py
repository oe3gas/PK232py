# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""TNC configuration dialog.

Allows selection of:
  - Serial port (COM1, /dev/ttyUSB0, …)
  - Baud rate
  - Hardware handshake (RTS/CTS)
  - Host Mode on exit
  - Fast initialisation

Based on the PCPackRatt "TNC Configuration" dialog
(see TNC_Config_at_Start.png in project files).

Usage::

    dlg = TncConfigDialog(current_config, parent=self)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        config = dlg.get_config()
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QPushButton, QVBoxLayout,
)

from ..comm.serial_manager import SerialManager
from ..comm.constants import SerialDefaults


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------

@dataclass
class TncConfig:
    """TNC connection settings passed between dialog and MainWindow.

    Note: this covers only the connection-level settings shown in the
    TNC Configuration dialog.  Operating-mode parameters (MYCALL, FRACK,
    MYPTCALL, …) live in config.py / AppConfig.
    """
    port_name:         str  = ""
    baudrate:          int  = SerialDefaults.BAUDRATE   # 9600
    rtscts:            bool = SerialDefaults.RTSCTS     # True
    host_mode_on_exit: bool = True    # send HOST OFF before closing port
    fast_init:         bool = False   # shorter waits during Host Mode init


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class TncConfigDialog(QDialog):
    """Modal TNC configuration dialog.

    Args:
        config: Current :class:`TncConfig` (pre-fills all widgets).
                Defaults to a fresh TncConfig() if omitted.
        parent: Parent widget (MainWindow).
    """

    # Supported baud rates for the PK-232MBX.
    # The TNC supports up to 9600 baud on the host port.
    # 19200 is listed for future/custom firmware; SerialDefaults.BAUDRATE = 9600.
    BAUDRATES = [1200, 2400, 4800, 9600]

    def __init__(
        self,
        config: TncConfig | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._config = config or TncConfig()
        self._build_ui()
        self._populate(self._config)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.setWindowTitle("TNC Configuration")
        self.setMinimumWidth(380)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setSpacing(12)

        # ── Connection group ───────────────────────────────────────────
        conn_group = QGroupBox("Connection")
        form = QFormLayout(conn_group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Port selector with refresh button
        port_row = QHBoxLayout()
        self._port_combo = QComboBox()
        self._port_combo.setMinimumWidth(140)
        self._port_combo.setEditable(True)   # allow manual entry
        port_row.addWidget(self._port_combo)

        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedWidth(32)
        refresh_btn.setToolTip("Refresh available ports")
        refresh_btn.clicked.connect(self._refresh_ports)
        port_row.addWidget(refresh_btn)
        form.addRow("Serial Port:", port_row)

        # Baud rate selector
        self._baud_combo = QComboBox()
        for br in self.BAUDRATES:
            self._baud_combo.addItem(str(br), br)
        form.addRow("Baud Rate:", self._baud_combo)

        root.addWidget(conn_group)

        # ── Options group ──────────────────────────────────────────────
        opt_group = QGroupBox("Options")
        opt_layout = QVBoxLayout(opt_group)

        self._rtscts_cb = QCheckBox("Hardware handshake (RTS/CTS)")
        self._rtscts_cb.setToolTip(
            "Recommended for PK-232MBX.  Disable only if the cable "
            "has no RTS/CTS lines."
        )
        opt_layout.addWidget(self._rtscts_cb)

        self._hm_exit_cb = QCheckBox("Leave Host Mode on disconnect")
        self._hm_exit_cb.setToolTip(
            "Sends HOST OFF frame before closing the port.\n"
            "Returns the TNC to terminal/verbose mode."
        )
        opt_layout.addWidget(self._hm_exit_cb)

        self._fast_init_cb = QCheckBox("Fast initialisation")
        self._fast_init_cb.setToolTip(
            "Use shorter wait times when activating Host Mode.\n"
            "Enable only if the TNC responds quickly."
        )
        opt_layout.addWidget(self._fast_init_cb)

        root.addWidget(opt_group)

        # ── Info label ────────────────────────────────────────────────
        info = QLabel(
            "<small><i>TNC Model: AEA PK-232 / PK-232MBX &nbsp;|&nbsp;"
            " Firmware: v7.1 / v7.2</i></small>"
        )
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(info)

        # ── OK / Cancel buttons ───────────────────────────────────────
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        root.addWidget(btn_box)

        # Initial port scan
        self._refresh_ports()

    def _populate(self, cfg: TncConfig) -> None:
        """Pre-fill widgets from *cfg*."""
        idx = self._port_combo.findText(cfg.port_name)
        if idx >= 0:
            self._port_combo.setCurrentIndex(idx)
        else:
            self._port_combo.setCurrentText(cfg.port_name)

        idx = self._baud_combo.findData(cfg.baudrate)
        if idx >= 0:
            self._baud_combo.setCurrentIndex(idx)

        self._rtscts_cb.setChecked(cfg.rtscts)
        self._hm_exit_cb.setChecked(cfg.host_mode_on_exit)
        self._fast_init_cb.setChecked(cfg.fast_init)

    def _refresh_ports(self) -> None:
        """Re-scan available serial ports and repopulate the combo box."""
        current = self._port_combo.currentText()
        self._port_combo.clear()

        ports = SerialManager.list_ports()
        if ports:
            self._port_combo.addItems(ports)
            idx = self._port_combo.findText(current)
            if idx >= 0:
                self._port_combo.setCurrentIndex(idx)
            else:
                self._port_combo.setCurrentText(current)
        else:
            self._port_combo.addItem("(no ports found)")

    # ------------------------------------------------------------------
    # Result
    # ------------------------------------------------------------------

    def get_config(self) -> TncConfig:
        """Return the user-configured :class:`TncConfig`.

        Call only after ``exec()`` returned ``QDialog.DialogCode.Accepted``.
        """
        return TncConfig(
            port_name         = self._port_combo.currentText(),
            baudrate          = self._baud_combo.currentData(),
            rtscts            = self._rtscts_cb.isChecked(),
            host_mode_on_exit = self._hm_exit_cb.isChecked(),
            fast_init         = self._fast_init_cb.isChecked(),
        )