# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""Main application window (MDI frame)."""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, QTimer, QDateTime
from PyQt6.QtWidgets import (
    QMainWindow,
    QMdiArea,
    QStatusBar,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)
from PyQt6.QtGui import QAction

from pk232py import __version__
from pk232py.config import ConfigManager

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """PK232PY main application window."""

    def __init__(self) -> None:
        super().__init__()
        self._config = ConfigManager()
        self._config.load()
        self._setup_window()
        self._setup_menu()
        self._setup_central()
        self._setup_statusbar()
        self._setup_clock()
        logger.info("MainWindow initialised")

    def _setup_window(self) -> None:
        self.setWindowTitle(f"PK232PY v{__version__}")
        self.resize(1000, 700)

    def _setup_menu(self) -> None:
        mb = self.menuBar()

        # File
        m = mb.addMenu("File")
        m.addAction("Load TNC Parameters",      self._on_load_params)
        m.addAction("Load/Init TNC Parameters", self._on_load_init_params)
        m.addAction("Save TNC Parameters",      self._on_save_params)
        m.addSeparator()
        m.addAction("Exit",                     self.close)

        # TNC
        m = mb.addMenu("TNC")
        self._act_open_tnc  = m.addAction("Open TNC Port",  self._on_open_tnc)
        self._act_close_tnc = m.addAction("Close TNC Port", self._on_close_tnc)
        self._act_close_tnc.setEnabled(False)
        m.addSeparator()
        m.addAction("Open Monitor Window",      self._on_monitor)

        # Parameters
        m = mb.addMenu("Parameters")
        sub = m.addMenu("TNC1 Parameters")
        sub.addAction("HF Packet Params",           self._on_params_hf)
        sub.addAction("HF Packet Msg Params",       self._on_params_hf_msg)
        sub.addAction("VHF Packet Params",          self._on_params_vhf)
        sub.addAction("AMTOR/NAVTEX/TDM Params",    self._on_params_amtor)
        sub.addAction("PACTOR Params",              self._on_params_pactor)
        sub.addAction("BAUDOT/ASCII/MORSE Params",  self._on_params_baudot)
        sub.addAction("Misc Params",                self._on_params_misc)
        sub.addSeparator()
        sub.addAction("MailDrop Params",            self._on_params_maildrop)

        # Configure
        m = mb.addMenu("Configure")
        m.addAction("Load Configuration",       self._on_load_config)
        m.addAction("Save Configuration",       self._on_save_config)
        m.addSeparator()
        m.addAction("TNC Configuration",        self._on_tnc_config)
        m.addAction("Program Files",            self._on_program_files)
        m.addAction("Program Configuration",    self._on_program_config)
        m.addAction("QSO Log Defaults",         self._on_qso_defaults)

        # Window
        m = mb.addMenu("Window")
        m.addAction("Cascade",           self._mdi_cascade)
        m.addAction("Tile Vertically",   self._mdi_tile_v)
        m.addAction("Tile Horizontally", self._mdi_tile_h)

        # Help
        m = mb.addMenu("Help")
        m.addAction("About PK232PY",     self._on_about)

    def _setup_central(self) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        self._mdi = QMdiArea()
        self._mdi.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._mdi.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        layout.addWidget(self._mdi, stretch=1)

        self._tx_input = QLineEdit()
        self._tx_input.setPlaceholderText("TX input - Enter to send")
        self._tx_input.returnPressed.connect(self._on_tx_send)
        layout.addWidget(self._tx_input)

        self.setCentralWidget(container)

    def _setup_statusbar(self) -> None:
        sb = self.statusBar()
        self._status_tnc   = QLabel("TNC: Not connected")
        self._status_mode  = QLabel("Mode: -")
        self._status_port  = QLabel("Port: -")
        self._status_clock = QLabel("UTC: --:--:--")
        for lbl in (self._status_tnc, self._status_mode,
                    self._status_port, self._status_clock):
            sb.addPermanentWidget(lbl)

    def _setup_clock(self) -> None:
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._tick_clock)
        self._clock_timer.start(1000)

    def _tick_clock(self) -> None:
        utc = QDateTime.currentDateTimeUtc().toString("HH:mm:ss")
        self._status_clock.setText(f"UTC: {utc}")

    # ------------------------------------------------------------------
    # Menu slots
    # ------------------------------------------------------------------

    def _on_load_params(self)      -> None: self._stub("Load TNC Parameters")
    def _on_load_init_params(self) -> None: self._stub("Load/Init TNC Parameters")
    def _on_save_params(self)      -> None: self._stub("Save TNC Parameters")
    def _on_open_tnc(self)         -> None: self._stub("Open TNC Port")
    def _on_close_tnc(self)        -> None: self._stub("Close TNC Port")
    def _on_monitor(self)          -> None: self._stub("Open Monitor Window")
    def _on_params_hf(self)        -> None: self._stub("HF Packet Params")
    def _on_params_hf_msg(self)    -> None: self._stub("HF Packet Msg Params")
    def _on_params_vhf(self)       -> None: self._stub("VHF Packet Params")
    def _on_params_amtor(self)     -> None: self._stub("AMTOR/NAVTEX/TDM Params")
    def _on_params_pactor(self)    -> None: self._stub("PACTOR Params")
    def _on_params_baudot(self)    -> None: self._stub("BAUDOT/ASCII/MORSE Params")
    def _on_params_misc(self)      -> None: self._stub("Misc Params")
    def _on_params_maildrop(self)  -> None: self._stub("MailDrop Params")
    def _on_load_config(self)      -> None: self._stub("Load Configuration")
    def _on_save_config(self)      -> None: self._stub("Save Configuration")
    def _on_program_files(self)    -> None: self._stub("Program Files")
    def _on_program_config(self)   -> None: self._stub("Program Configuration")
    def _on_qso_defaults(self)     -> None: self._stub("QSO Log Defaults")
    def _on_tx_send(self)          -> None: self._stub(f"Send: {self._tx_input.text()}")

    def _on_tnc_config(self) -> None:
        from pk232py.ui.dialogs.tnc_config import TNCConfigDialog
        dlg = TNCConfigDialog(self._config.app.tnc, parent=self)
        if dlg.exec():
            self._config.save()
            self._status_port.setText(f"Port: {self._config.app.tnc.port}")
            logger.info("TNC config updated: %s @ %s baud",
                        self._config.app.tnc.model,
                        self._config.app.tnc.tbaud)

    def _mdi_cascade(self) -> None: self._mdi.cascadeSubWindows()
    def _mdi_tile_v(self)  -> None: self._mdi.tileSubWindows()
    def _mdi_tile_h(self)  -> None: self._mdi.tileSubWindows()

    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            "About PK232PY",
            f"<b>PK232PY</b> v{__version__}<br><br>"
            "Modern multimode terminal for the<br>"
            "AEA PK-232 / PK-232MBX TNC.<br><br>"
            "Copyright 2026 OE3GAS<br>"
            "License: GNU GPL v2<br><br>"
            "<a href='https://github.com/oe3gas/PK232py'>"
            "github.com/oe3gas/PK232py</a>",
        )

    def _stub(self, name: str) -> None:
        logger.info("Not yet implemented: %s", name)
        self.statusBar().showMessage(f"Not yet implemented: {name}", 3000)