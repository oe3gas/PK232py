# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Main application window (MDI frame).

Layout:
    ┌─────────────────────────────────────────────────┐
    │  Menu bar                                       │
    ├─────────────────────────────────────────────────┤
    │  Toolbar                                        │
    ├───────────────────────────────────┬─────────────┤
    │                                   │  LED panel  │
    │   MDI area                        │  Bargraph   │
    │   (RX/TX sub-windows)             │  Status     │
    │                                   │             │
    ├───────────────────────────────────┴─────────────┤
    │  TX input line                                  │
    ├─────────────────────────────────────────────────┤
    │  Status bar  (TNC | Mode | Port | UTC time)     │
    └─────────────────────────────────────────────────┘

TODO (v0.2):
    - Add RX sub-windows (MDI children)
    - Add monitor window
    - Wire up TNC connect/disconnect actions
    - Implement LED panel widget
    - Implement bargraph tuning indicator widget
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QMainWindow,
    QMdiArea,
    QStatusBar,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
    QMenuBar,
    QMenu,
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

    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------

    def _setup_window(self) -> None:
        self.setWindowTitle(f"PK232PY v{__version__}")
        self.resize(1000, 700)

    def _setup_menu(self) -> None:
        """Build the menu bar — File | TNC | Parameters | Configure | Window | Help."""
        mb = self.menuBar()

        # ── File ──────────────────────────────────────────────────────
        file_menu = mb.addMenu("&File")
        file_menu.addAction(self._action("Load TNC Parameters", self._on_load_params))
        file_menu.addAction(self._action("Load/Init TNC Parameters", self._on_load_init_params))
        file_menu.addAction(self._action("Save TNC Parameters", self._on_save_params))
        file_menu.addSeparator()
        file_menu.addAction(self._action("E&xit", self.close, shortcut="Ctrl+Q"))

        # ── TNC ───────────────────────────────────────────────────────
        tnc_menu = mb.addMenu("&TNC")
        self._act_open_tnc = self._action("Open TNC Port", self._on_open_tnc)
        self._act_close_tnc = self._action("Close TNC Port", self._on_close_tnc)
        self._act_close_tnc.setEnabled(False)
        tnc_menu.addAction(self._act_open_tnc)
        tnc_menu.addAction(self._act_close_tnc)
        tnc_menu.addSeparator()
        tnc_menu.addAction(self._action("Open Monitor Window", self._on_monitor))

        # ── Parameters ────────────────────────────────────────────────
        params_menu = mb.addMenu("&Parameters")
        tnc1_params = params_menu.addMenu("TNC1 Parameters")
        tnc1_params.addAction(self._action("HF Packet Params…",    self._on_params_hf))
        tnc1_params.addAction(self._action("HF Packet Msg Params…", self._on_params_hf_msg))
        tnc1_params.addAction(self._action("VHF Packet Params…",   self._on_params_vhf))
        tnc1_params.addAction(self._action("AMTOR/NAVTEX/TDM Params…", self._on_params_amtor))
        tnc1_params.addAction(self._action("PACTOR Params…",       self._on_params_pactor))
        tnc1_params.addAction(self._action("BAUDOT/ASCII/MORSE Params…", self._on_params_baudot))
        tnc1_params.addAction(self._action("Misc Params…",         self._on_params_misc))
        tnc1_params.addSeparator()
        tnc1_params.addAction(self._action("MailDrop Params…",     self._on_params_maildrop))

        # ── Configure ─────────────────────────────────────────────────
        cfg_menu = mb.addMenu("&Configure")
        cfg_menu.addAction(self._action("Load Configuration",  self._on_load_config))
        cfg_menu.addAction(self._action("Save Configuration",  self._on_save_config))
        cfg_menu.addSeparator()
        tnc1_cfg = cfg_menu.addMenu("TNC1")
        tnc1_cfg.addAction(self._action("TNC Configuration…",    self._on_tnc_config))
        tnc1_cfg.addAction(self._action("Program Files…",        self._on_program_files))
        tnc1_cfg.addAction(self._action("Program Configuration…", self._on_program_config))
        tnc1_cfg.addAction(self._action("QSO Log Defaults…",     self._on_qso_defaults))

        # ── Window ────────────────────────────────────────────────────
        win_menu = mb.addMenu("&Window")
        win_menu.addAction(self._action("Cascade",           self._mdi_cascade))
        win_menu.addAction(self._action("Tile Vertically",   self._mdi_tile_v))
        win_menu.addAction(self._action("Tile Horizontally", self._mdi_tile_h))

        # ── Help ──────────────────────────────────────────────────────
        help_menu = mb.addMenu("&Help")
        help_menu.addAction(self._action("About PK232PY…", self._on_about))

    def _setup_central(self) -> None:
        """Create the central MDI area and TX input line."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        self._mdi = QMdiArea()
        self._mdi.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._mdi.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        layout.addWidget(self._mdi, stretch=1)

        self._tx_input = QLineEdit()
        self._tx_input.setPlaceholderText("TX input — Enter to send")
        self._tx_input.returnPressed.connect(self._on_tx_send)
        layout.addWidget(self._tx_input)

        self.setCentralWidget(container)

    def _setup_statusbar(self) -> None:
        sb = self.statusBar()
        self._status_tnc   = QLabel("TNC: Not connected")
        self._status_mode  = QLabel("Mode: —")
        self._status_port  = QLabel("Port: —")
        self._status_clock = QLabel("UTC: --:--:--")
        for lbl in (self._status_tnc, self._status_mode,
                    self._status_port, self._status_clock):
            sb.addPermanentWidget(lbl)

    def _setup_clock(self) -> None:
        """Update the UTC clock in the status bar every second."""
        from PyQt6.QtCore import QDateTime, Qt as Qt2
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._tick_clock)
        self._clock_timer.start(1000)

    # ------------------------------------------------------------------
    # Clock
    # ------------------------------------------------------------------

    def _tick_clock(self) -> None:
        from PyQt6.QtCore import QDateTime, Qt as Qt2
        utc = QDateTime.currentDateTimeUtc().toString("HH:mm:ss")
        self._status_clock.setText(f"UTC: {utc}")

    # ------------------------------------------------------------------
    # Menu action helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _action(
        text: str,
        slot,
        shortcut: str | None = None,
        enabled: bool = True,
    ) -> QAction:
        act = QAction(text)
        act.triggered.connect(slot)
        if shortcut:
            act.setShortcut(shortcut)
        act.setEnabled(enabled)
        return act

    # ------------------------------------------------------------------
    # Slot stubs — to be implemented in later milestones
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
    def _on_tnc_config(self)       -> None: self._stub("TNC Configuration")
    def _on_program_files(self)    -> None: self._stub("Program Files")
    def _on_program_config(self)   -> None: self._stub("Program Configuration")
    def _on_qso_defaults(self)     -> None: self._stub("QSO Log Defaults")
    def _on_tx_send(self)          -> None: self._stub(f"Send: {self._tx_input.text()}")

    def _mdi_cascade(self) -> None: self._mdi.cascadeSubWindows()
    def _mdi_tile_v(self)  -> None:
        self._mdi.setViewMode(QMdiArea.ViewMode.SubWindowView)
        self._mdi.tileSubWindows()
    def _mdi_tile_h(self)  -> None: self._mdi_tile_v()

    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            "About PK232PY",
            f"<b>PK232PY</b> v{__version__}<br><br>"
            "Modern multimode terminal for the<br>"
            "AEA PK-232 / PK-232MBX TNC.<br><br>"
            "Copyright © 2026 OE3GAS<br>"
            "License: GNU GPL v2<br><br>"
            "<a href='https://github.com/OE3GAS/pk232py'>"
            "github.com/OE3GAS/pk232py</a>",
        )

    def _stub(self, name: str) -> None:
        """Placeholder for not-yet-implemented actions."""
        logger.info("Action not yet implemented: %s", name)
        self.statusBar().showMessage(f"Not yet implemented: {name}", 3000)
