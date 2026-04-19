# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Main window of PK232PY.

Layout:
  ┌─────────────────────────────────────────────────┐
  │  Menu: File | TNC | Parameters | Configure       │
  ├─────────────────────────────────────────────────┤
  │  Toolbar: [Connect] [Disconnect] [Host Mode]     │
  │           [Mode: HF Packet ▼]                    │
  ├───────────────────────┬─────────────────────────┤
  │                       │                         │
  │   RX / Terminal panel │   Monitor panel          │
  │                       │   (toggleable)           │
  ├───────────────────────┴─────────────────────────┤
  │  Status: Port | Baud | Mode | UTC time           │
  └─────────────────────────────────────────────────┘
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from PyQt6.QtCore import QEvent, QSettings, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QFont
from PyQt6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QPushButton, QSplitter, QStackedWidget, QTextEdit, QToolBar,
    QVBoxLayout, QWidget,
)

from pk232py import __version__
from ..comm.serial_manager import SerialManager
from ..comm.frame import HostFrame, FrameKind
from ..mode_manager import ModeManager
from ..comm.params_uploader import ParamsUploader
from .tnc_config_dialog import TncConfigDialog, TncConfig
from .dialogs.params_hf      import HFPacketParamsDialog
from .appearance_dialog      import AppearanceDialog
from .dialogs.params_misc    import MiscParamsDialog
from .dialogs.params_pactor  import PACTORParamsDialog
from .dialogs.params_amtor   import AMTORParamsDialog
from .dialogs.params_baudot  import BaudotParamsDialog
from .dialogs.params_maildrop import MailDropParamsDialog

logger = logging.getLogger(__name__)

APP_TITLE = "PK232PY"


class MainWindow(QMainWindow):
    """Main application window.

    Coordinates:
      - SerialManager  (TNC serial connection)
      - ModeManager    (operating mode switching + frame dispatch)
      - TncConfigDialog (connection configuration)
      - Menu bar, toolbar, status bar
    """

    def __init__(self) -> None:
        super().__init__()
        self._config: TncConfig = TncConfig()
        self._serial = SerialManager(parent=self)
        self._modes  = ModeManager(self._serial, parent=self)
        # Application config (parameters for all modes)
        from pk232py.config import ConfigManager
        self._config_mgr = ConfigManager()
        self._config_mgr.load()
        self._app_config = self._config_mgr.app
        self._misc_params:   dict = {}
        self._connect_mode:  str  = "verbose"
        self._build_ui()
        self._connect_signals()
        self._update_connection_ui(False)
        logger.info("%s v%s started", APP_TITLE, __version__)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.setWindowTitle(f"{APP_TITLE} v{__version__}")
        self.resize(900, 600)
        self._build_menubar()
        self._build_toolbar()
        self._build_central()
        self._build_statusbar()
        self._restore_window_geometry()
        self._apply_appearance()   # apply saved appearance on startup

    def _build_menubar(self) -> None:
        mb = self.menuBar()

        # ── File ──────────────────────────────────────────────────────
        file_menu = mb.addMenu("&File")

        act_load = QAction("&Load Settings...", self)
        act_load.setShortcut("Ctrl+L")
        act_load.setStatusTip("Load settings from INI file")
        act_load.triggered.connect(self._on_load_settings)
        file_menu.addAction(act_load)

        act_save = QAction("&Save Settings...", self)
        act_save.setShortcut("Ctrl+S")
        act_save.setStatusTip("Save settings to INI file")
        act_save.triggered.connect(self._on_save_settings)
        file_menu.addAction(act_save)

        file_menu.addSeparator()

        act_exit = QAction("E&xit", self)
        act_exit.setShortcut("Ctrl+Q")
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        # ── TNC ───────────────────────────────────────────────────────
        tnc_menu = mb.addMenu("&TNC")

        self._act_connect_verbose = QAction("Connect + Enter &Verbose Mode...", self)
        self._act_connect_verbose.setShortcut("Ctrl+T")
        self._act_connect_verbose.setStatusTip(
            "Connect to TNC and enter verbose terminal mode"
        )
        self._act_connect_verbose.triggered.connect(self._on_connect_verbose)
        tnc_menu.addAction(self._act_connect_verbose)

        self._act_disconnect = QAction("&Disconnect", self)
        self._act_disconnect.setShortcut("Ctrl+D")
        self._act_disconnect.setStatusTip("Disconnect from TNC")
        self._act_disconnect.triggered.connect(self._on_disconnect)
        tnc_menu.addAction(self._act_disconnect)

        tnc_menu.addSeparator()

        self._act_connect_host = QAction("Connect + Enter &Host Mode...", self)
        self._act_connect_host.setStatusTip(
            "Connect to TNC, upload parameters and enter Host Mode"
        )
        self._act_connect_host.triggered.connect(self._on_connect_host)
        tnc_menu.addAction(self._act_connect_host)

        self._act_host_off = QAction("Leave Host Mode  (Enter Verbose Mode)", self)
        self._act_host_off.setStatusTip("Leave Host Mode, return TNC to verbose terminal")
        self._act_host_off.triggered.connect(self._on_host_mode_exit)
        tnc_menu.addAction(self._act_host_off)

        self._act_recovery = QAction("Host Mode &Recovery", self)
        self._act_recovery.setStatusTip(
            "Emergency recovery: free TNC from stuck Host Mode"
        )
        self._act_recovery.triggered.connect(self._on_recovery)
        tnc_menu.addAction(self._act_recovery)

        # ── View ──────────────────────────────────────────────────────
        view_menu = mb.addMenu("&View")

        self._act_monitor = QAction("Monitor Window", self)
        self._act_monitor.setStatusTip("Show/hide raw frame monitor panel")
        self._act_monitor.setCheckable(True)
        self._act_monitor.setChecked(False)
        self._act_monitor.triggered.connect(self._on_toggle_monitor)
        view_menu.addAction(self._act_monitor)

        self._act_serial_status = QAction("Serial Status Bar", self)
        self._act_serial_status.setStatusTip(
            "Show/hide serial signal status bar (CTS, DSR, DCD)"
        )
        self._act_serial_status.setCheckable(True)
        self._act_serial_status.setChecked(False)
        self._act_serial_status.triggered.connect(self._on_toggle_serial_status)
        view_menu.addAction(self._act_serial_status)

        # ── Parameters ────────────────────────────────────────────────
        param_menu = mb.addMenu("&Parameters")
        # Implemented dialogs
        _implemented = {"HF Packet...", "Misc...", "PACTOR...", "AMTOR / NAVTEX / TDM...", "BAUDOT / ASCII / CW...", "MailDrop..."}
        for label, slot in [
            ("HF Packet...",             self._on_params_hf_packet),
            ("PACTOR...",                self._on_params_pactor),
            ("AMTOR / NAVTEX / TDM...",  self._on_params_amtor),
            ("BAUDOT / ASCII / CW...",   self._on_params_baudot),
            ("Misc...",                  self._on_params_misc),
            ("MailDrop...",              self._on_params_maildrop),
        ]:
            act = QAction(label, self)
            act.setEnabled(label in _implemented)
            act.triggered.connect(slot)
            param_menu.addAction(act)

        # ── Configure ─────────────────────────────────────────────────
        cfg_menu = mb.addMenu("&Configure")

        act_tnc_cfg = QAction("TNC &Configuration...", self)
        act_tnc_cfg.setStatusTip("Set port, baud rate and connection options")
        act_tnc_cfg.triggered.connect(self._on_tnc_config)
        cfg_menu.addAction(act_tnc_cfg)

        cfg_menu.addSeparator()

        # Appearance submenu
        appear_menu = cfg_menu.addMenu("&Appearance")

        act_font = QAction("Font && Colors...", self)
        act_font.setStatusTip("Set display font, size and colors")
        act_font.triggered.connect(self._on_appearance)
        appear_menu.addAction(act_font)

        cfg_menu.addSeparator()

        act_about = QAction("&About PK232PY...", self)
        act_about.triggered.connect(self._on_about)
        cfg_menu.addAction(act_about)

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main", self)
        tb.setMovable(False)
        self.addToolBar(tb)

        self._tb_connect = tb.addAction("⚡ Connect")
        self._tb_connect.setToolTip("Connect to TNC (Ctrl+T)")
        self._tb_connect.triggered.connect(self._on_connect_verbose)

        self._tb_disconnect = tb.addAction("✕ Disconnect")
        self._tb_disconnect.setToolTip("Disconnect (Ctrl+D)")
        self._tb_disconnect.triggered.connect(self._on_disconnect)

        tb.addSeparator()

        self._tb_host_on = tb.addAction("⬆ Host Mode")
        self._tb_host_on.setToolTip("Enter Host Mode")
        self._tb_host_on.triggered.connect(self._on_host_mode_enter)

        self._tb_recovery = tb.addAction("⟳ Recovery")
        self._tb_recovery.setToolTip("Host Mode Recovery")
        self._tb_recovery.triggered.connect(self._on_recovery)

        tb.addSeparator()

        # Mode selector ComboBox in toolbar
        tb.addWidget(QLabel(" Mode: "))
        self._mode_combo = QComboBox()
        self._mode_combo.setMinimumWidth(120)
        self._mode_combo.setToolTip("Select operating mode")
        for name in self._modes.available_modes():
            self._mode_combo.addItem(name)
        self._mode_combo.setEnabled(False)   # enabled after Host Mode active
        self._mode_combo.currentTextChanged.connect(self._on_mode_selected)
        tb.addWidget(self._mode_combo)

    def _build_central(self) -> None:
        """Build the central widget with two views:
          - Page 0: Host Mode view (RX display + TX input + Monitor)
          - Page 1: Verbose terminal view (terminal log + command input)
        """
        # ── Stack: switches between Host Mode and Verbose Terminal ────
        self._stack = QStackedWidget()

        # ── Page 0: Host Mode view ────────────────────────────────────
        host_page = QWidget()
        host_layout = QVBoxLayout(host_page)
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.setSpacing(0)

        outer = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        ll   = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)

        vs = QSplitter(Qt.Orientation.Vertical)

        self._rx_display = QTextEdit()
        self._rx_display.setReadOnly(True)
        self._rx_display.setFont(QFont("Courier New", 10))
        self._rx_display.setStyleSheet(
            "background-color:#1e1e1e; color:#d4d4d4; border:none;"
        )
        self._rx_display.setPlaceholderText(
            "TNC output — received data and responses appear here."
        )
        vs.addWidget(self._rx_display)

        iw = QWidget()
        iw.setStyleSheet("background-color:#252526;")
        il = QHBoxLayout(iw)
        il.setContentsMargins(4, 4, 4, 4)
        il.setSpacing(4)

        self._tx_input = QTextEdit()
        self._tx_input.setFont(QFont("Courier New", 10))
        self._tx_input.setStyleSheet(
            "background-color:#1e1e1e; color:#d4d4d4; border:1px solid #444;"
        )
        self._tx_input.setPlaceholderText(
            "Enter command… (Enter = send, Shift+Enter = new line)"
        )
        self._tx_input.setFixedHeight(60)
        self._tx_input.installEventFilter(self)
        il.addWidget(self._tx_input)

        self._send_btn = QPushButton("Send")
        self._send_btn.setFixedWidth(80)
        self._send_btn.setFixedHeight(60)
        self._send_btn.setStyleSheet(
            "QPushButton{background:#0e639c;color:white;border:none;font-weight:bold;}"
            "QPushButton:hover{background:#1177bb;}"
            "QPushButton:pressed{background:#0a4f7e;}"
            "QPushButton:disabled{background:#3a3a3a;color:#666;}"
        )
        self._send_btn.clicked.connect(self._on_send)
        il.addWidget(self._send_btn)

        vs.addWidget(iw)
        vs.setSizes([480, 120])
        vs.setCollapsible(1, False)
        ll.addWidget(vs)
        outer.addWidget(left)

        # Monitor panel with mode selector
        monitor_container = QWidget()
        mc_layout = QVBoxLayout(monitor_container)
        mc_layout.setContentsMargins(0, 0, 0, 0)
        mc_layout.setSpacing(0)

        # Monitor toolbar
        mon_tb = QWidget()
        mon_tb.setStyleSheet("background:#161b22; border-bottom:1px solid #30363d;")
        mon_tb_layout = QHBoxLayout(mon_tb)
        mon_tb_layout.setContentsMargins(4, 2, 4, 2)
        mon_tb_layout.setSpacing(4)

        from PyQt6.QtWidgets import QButtonGroup, QRadioButton
        mon_tb_layout.addWidget(QLabel("Monitor:"))

        self._mon_btn_decoded = QRadioButton("Decoded")
        self._mon_btn_raw     = QRadioButton("Raw ASCII")
        self._mon_btn_hex     = QRadioButton("Hex")
        self._mon_btn_decoded.setChecked(True)

        for btn in [self._mon_btn_decoded, self._mon_btn_raw, self._mon_btn_hex]:
            btn.setStyleSheet("color:#8b949e;")
            mon_tb_layout.addWidget(btn)

        self._mon_btn_clear = QPushButton("Clear")
        self._mon_btn_clear.setFixedWidth(50)
        self._mon_btn_clear.setStyleSheet(
            "QPushButton{background:#21262d;color:#8b949e;border:1px solid #30363d;"
            "border-radius:3px;padding:1px 4px;}"
            "QPushButton:hover{background:#30363d;}"
        )
        self._mon_btn_clear.clicked.connect(lambda: self._monitor.clear())
        mon_tb_layout.addWidget(self._mon_btn_clear)
        mon_tb_layout.addStretch()
        mc_layout.addWidget(mon_tb)

        self._monitor = QTextEdit()
        self._monitor.setReadOnly(True)
        self._monitor.setFont(QFont("Courier New", 9))
        self._monitor.setStyleSheet(
            "background-color:#0d1117; color:#8b949e; border:none;"
        )
        self._monitor.setPlaceholderText(
            "Monitor — decoded frames / raw / hex"
        )
        mc_layout.addWidget(self._monitor)

        monitor_container.setVisible(False)
        outer.addWidget(monitor_container)
        outer.setSizes([900, 0])
        self._monitor_container = monitor_container

        self._splitter = outer
        self._terminal = self._rx_display
        host_layout.addWidget(outer)
        self._stack.addWidget(host_page)   # index 0

        # ── Page 1: Verbose Terminal view ─────────────────────────────
        vterm_page = QWidget()
        vt_layout  = QVBoxLayout(vterm_page)
        vt_layout.setContentsMargins(0, 0, 0, 0)
        vt_layout.setSpacing(0)

        # Upper: TNC output (echo + responses)
        self._vt_display = QTextEdit()
        self._vt_display.setReadOnly(True)
        self._vt_display.setFont(QFont("Courier New", 10))
        self._vt_display.setStyleSheet(
            "background-color:#0c0c0c; color:#cccccc; border:none;"
        )
        self._vt_display.setPlaceholderText(
            "TNC verbose mode — echo and responses appear here."
        )
        vt_layout.addWidget(self._vt_display, stretch=1)

        # Separator line
        sep = QWidget()
        sep.setFixedHeight(2)
        sep.setStyleSheet("background-color:#444;")
        vt_layout.addWidget(sep)

        # Lower: command input row
        cmd_row = QWidget()
        cmd_row.setFixedHeight(36)
        cmd_row.setStyleSheet("background-color:#1a1a1a;")
        cmd_layout = QHBoxLayout(cmd_row)
        cmd_layout.setContentsMargins(6, 2, 6, 2)
        cmd_layout.setSpacing(4)

        prompt_label = QLabel("cmd:")
        prompt_label.setFont(QFont("Courier New", 10))
        prompt_label.setStyleSheet("color:#569cd6; background:transparent;")
        cmd_layout.addWidget(prompt_label)

        self._vt_input = QTextEdit()
        self._vt_input.setFont(QFont("Courier New", 10))
        self._vt_input.setStyleSheet(
            "background-color:#1a1a1a; color:#d4d4d4; border:none;"
        )
        self._vt_input.setPlaceholderText("type command, Enter to send…")
        self._vt_input.setFixedHeight(28)
        self._vt_input.installEventFilter(self)
        cmd_layout.addWidget(self._vt_input, stretch=1)

        vt_layout.addWidget(cmd_row)
        self._stack.addWidget(vterm_page)  # index 1

        # Footer container: holds signal status bars (shown/hidden via View menu)
        self._footer = QWidget()
        self._footer.setStyleSheet("background:#111111;")
        self._footer_layout = QVBoxLayout(self._footer)
        self._footer_layout.setContentsMargins(0, 0, 0, 0)
        self._footer_layout.setSpacing(0)
        self._footer.setVisible(False)  # hidden until _build_statusbar adds rows

        # Main container: stack (content) + footer (signal rows)
        main_container = QWidget()
        main_layout = QVBoxLayout(main_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self._stack, stretch=1)
        main_layout.addWidget(self._footer)

        self.setCentralWidget(main_container)
        self._stack.setCurrentIndex(0)     # start in Host Mode view

    def _build_statusbar(self) -> None:
        sb = self.statusBar()

        # Row 1 (Qt status bar): Port | Baud | Mode | UTC
        self._sb_port = QLabel("Port: ---")
        self._sb_port.setMinimumWidth(120)
        sb.addPermanentWidget(self._sb_port)

        self._sb_baud = QLabel("Baud: ---")
        self._sb_baud.setMinimumWidth(90)
        sb.addPermanentWidget(self._sb_baud)

        self._sb_mode = QLabel("Mode: OFFLINE")
        self._sb_mode.setMinimumWidth(150)
        sb.addPermanentWidget(self._sb_mode)

        self._sb_time = QLabel("UTC: --:--:--")
        self._sb_time.setMinimumWidth(110)
        sb.addPermanentWidget(self._sb_time)

        self._utc_timer = QTimer(self)
        self._utc_timer.timeout.connect(self._update_utc_clock)
        self._utc_timer.start(1000)
        self._update_utc_clock()

        # ── Serial signal status bars (hidden by default) ─────────────
        # Container widget holding both rows
        self._serial_status_bar = QWidget(self)
        ssl_outer = QVBoxLayout(self._serial_status_bar)
        ssl_outer.setContentsMargins(4, 1, 4, 1)
        ssl_outer.setSpacing(2)

        def _sig_label(text: str, width: int = 75) -> QLabel:
            lbl = QLabel(text)
            lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
            lbl.setFixedWidth(width)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                "color:#555555; background:#1a1a1a; border:1px solid #333;"
                "border-radius:3px; padding:1px 4px;"
            )
            return lbl

        # ── Row 1: Hardware signals ────────────────────────────────────
        row1 = QWidget()
        row1.setStyleSheet("background:transparent;")
        r1l = QHBoxLayout(row1)
        r1l.setContentsMargins(0, 0, 0, 0)
        r1l.setSpacing(6)

        lbl_hw = QLabel("HW:")
        lbl_hw.setFont(QFont("Courier New", 8))
        lbl_hw.setStyleSheet("color:#666; background:transparent;")
        r1l.addWidget(lbl_hw)

        self._ssl_connected = _sig_label("CONNECTED", 85)
        self._ssl_cts       = _sig_label("CTS")
        self._ssl_dsr       = _sig_label("DSR")
        self._ssl_dcd       = _sig_label("DCD")
        self._ssl_rts       = _sig_label("RTS")
        self._ssl_dtr       = _sig_label("DTR")

        for w in [self._ssl_connected, self._ssl_cts, self._ssl_dsr,
                  self._ssl_dcd,       self._ssl_rts, self._ssl_dtr]:
            r1l.addWidget(w)
        r1l.addStretch()
        ssl_outer.addWidget(row1)

        # ── Row 2: Program/TNC status ──────────────────────────────────
        row2 = QWidget()
        row2.setStyleSheet("background:transparent;")
        r2l = QHBoxLayout(row2)
        r2l.setContentsMargins(0, 0, 0, 0)
        r2l.setSpacing(6)

        lbl_tnc = QLabel("TNC:")
        lbl_tnc.setFont(QFont("Courier New", 8))
        lbl_tnc.setStyleSheet("color:#666; background:transparent;")
        r2l.addWidget(lbl_tnc)

        self._ssl_host = _sig_label("HOST")
        self._ssl_ptt  = _sig_label("PTT")
        self._ssl_con  = _sig_label("CON")
        self._ssl_rx   = _sig_label("RX ▼")
        self._ssl_tx   = _sig_label("TX ▲")

        for w in [self._ssl_host, self._ssl_ptt,
                  self._ssl_con,  self._ssl_rx, self._ssl_tx]:
            r2l.addWidget(w)
        r2l.addStretch()
        ssl_outer.addWidget(row2)

        self._serial_status_bar.setVisible(True)
        self._serial_status_bar.setStyleSheet("background:#111111;")
        # Add signal rows to footer (footer itself is hidden by default)
        self._footer_layout.addWidget(self._serial_status_bar)

        # RX/TX blink timers
        self._rx_blink_timer = QTimer(self)
        self._rx_blink_timer.setSingleShot(True)
        self._rx_blink_timer.setInterval(150)
        self._rx_blink_timer.timeout.connect(
            lambda: self._ssl_rx.setStyleSheet(self._sig_style_inactive())
        )
        self._tx_blink_timer = QTimer(self)
        self._tx_blink_timer.setSingleShot(True)
        self._tx_blink_timer.setInterval(150)
        self._tx_blink_timer.timeout.connect(
            lambda: self._ssl_tx.setStyleSheet(self._sig_style_inactive())
        )

        # Timer for polling serial signal states (500ms)
        self._serial_sig_timer = QTimer(self)
        self._serial_sig_timer.setInterval(500)
        self._serial_sig_timer.timeout.connect(self._update_serial_signals)

        # Timer for periodic OPMODE poll in Host Mode (5s)
        self._opmode_timer = QTimer(self)
        self._opmode_timer.setInterval(5000)
        self._opmode_timer.timeout.connect(self._poll_opmode)

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        # SerialManager → MainWindow
        self._serial.connection_changed.connect(self._update_connection_ui)
        self._serial.host_mode_changed.connect(self._update_host_mode_ui)
        self._serial.status_message.connect(self._on_status_message)
        self._serial.verbose_mode_ready.connect(self._on_verbose_mode_ready)
        self._serial.params_upload_required.connect(self._on_params_upload_required)
        self._serial.raw_data_received.connect(self._on_raw_data_received)

        # SerialManager → ModeManager (frame dispatch)
        self._serial.frame_received.connect(self._modes.on_frame)
        self._serial.frame_received.connect(self._on_frame_received)

        # ModeManager → MainWindow
        self._modes.mode_changed.connect(self._on_mode_changed)
        self._modes.mode_switch_failed.connect(self._on_mode_switch_failed)
        self._modes.status_message.connect(self._on_status_message)

    # ------------------------------------------------------------------
    # Slots — TNC connection
    # ------------------------------------------------------------------

    def _open_connect_dialog(self) -> bool:
        """Show TNC config dialog and open port. Returns True on success."""
        if self._app_config.tnc.port:
            self._config.port_name = self._app_config.tnc.port
        if self._app_config.tnc.tbaud:
            self._config.baudrate  = self._app_config.tnc.tbaud
        dlg = TncConfigDialog(self._config, parent=self)
        if dlg.exec() != TncConfigDialog.DialogCode.Accepted:
            return False
        self._config = dlg.get_config()
        if not self._config.port_name or self._config.port_name.startswith("("):
            QMessageBox.warning(self, "No Port", "Please select a valid serial port.")
            return False
        ok = self._serial.connect_port(
            self._config.port_name,
            baudrate=self._config.baudrate,
        )
        if ok:
            self._app_config.tnc.port  = self._config.port_name
            self._app_config.tnc.tbaud = self._config.baudrate
            self._config_mgr.save()
            self._log_monitor(
                f"[SYS] Connected: {self._config.port_name} @ {self._config.baudrate} Bd"
            )
        return ok

    def _on_connect_verbose(self) -> None:
        """Connect and enter verbose terminal mode (no automatic Host Mode)."""
        if not self._open_connect_dialog():
            return
        self._connect_mode = "verbose"
        self._serial.init_tnc()

    def _on_connect_host(self) -> None:
        """Connect, upload parameters and enter Host Mode automatically."""
        if not self._open_connect_dialog():
            return
        self._connect_mode = "host"
        self._serial.init_tnc()

    def _on_connect(self) -> None:
        """Legacy — defaults to verbose mode."""
        self._on_connect_verbose()

    def _on_disconnect(self) -> None:
        self._serial.disconnect_port()
        self._log_monitor("[SYS] Disconnected")

    def _on_verbose_mode_ready(self) -> None:
        """Called when TNC is in verbose mode.

        If _connect_mode == "verbose": stay in verbose terminal, no Host Mode.
        If _connect_mode == "host":    upload params and enter Host Mode.
        """
        self._log_monitor("[SYS] TNC in verbose mode")
        self._sb_mode.setText("Mode: VERBOSE")
        self._stack.setCurrentIndex(1)
        self._vt_display.clear()
        self._vt_append("[SYS] TNC ready in verbose mode\n")

        if self._connect_mode == "verbose":
            self._vt_append("[SYS] Verbose terminal ready — type commands below\n")
        else:
            import threading
            def _upload():
                self._vt_append("[SYS] Uploading parameters...\n")
                uploader = ParamsUploader(self._serial, self._app_config)
                n = uploader.upload()
                self._log_monitor(f"[SYS] {n} parameters uploaded")
                self._vt_append(
                    f"[SYS] {n} parameters uploaded — entering Host Mode...\n"
                )
                self._serial.enter_host_mode()
            threading.Thread(
                target=_upload, daemon=True, name="PK232-ParamUpload"
            ).start()

    def _on_params_upload_required(self) -> None:
        """Called when TNC rebooted — same as verbose_mode_ready but with log message."""
        self._log_monitor("[SYS] TNC rebooted — re-uploading parameters...")
        self._on_verbose_mode_ready()

    def _on_host_mode_enter(self) -> None:
        """Manual Host Mode entry from menu/toolbar."""
        if self._serial.is_connected:
            self._serial.enter_host_mode()

    def _on_host_mode_exit(self) -> None:
        if self._serial.is_connected:
            self._serial.exit_host_mode()

    def _on_recovery(self) -> None:
        if self._serial.is_connected:
            self._serial.recovery()
            self._log_monitor("[SYS] Host Mode recovery sent")

    # ------------------------------------------------------------------
    # Slots — mode selection
    # ------------------------------------------------------------------

    def _on_mode_selected(self, name: str) -> None:
        """Called when the user selects a mode from the toolbar ComboBox."""
        if not name or not self._serial.is_host_mode:
            return
        # Avoid spurious trigger during programmatic updates
        if name == self._modes.current_mode_name:
            return
        logger.info("User selected mode: %s", name)
        self._log_monitor(f"[TX] Switching to mode: {name}")
        self._modes.set_mode(name)

    def _on_mode_changed(self, name: str) -> None:
        """Called by ModeManager when mode switch completes.
        Wires the active mode's data callbacks to the UI.
        """
        self._sb_mode.setText(f"Mode: {name}")
        self._log_monitor(f"[SYS] Mode switched to: {name}")
        # Sync ComboBox without triggering _on_mode_selected
        self._mode_combo.blockSignals(True)
        idx = self._mode_combo.findText(name)
        if idx >= 0:
            self._mode_combo.setCurrentIndex(idx)
        self._mode_combo.blockSignals(False)
        # Wire active mode callbacks → UI
        self._wire_mode_callbacks()

    def _wire_mode_callbacks(self) -> None:
        """Connect the active mode's data callbacks to the RX display."""
        mode = self._modes.current_mode
        if mode is None:
            return
        # Generic: on_data_received → RX display
        if hasattr(mode, "on_data_received"):
            mode.on_data_received = self._on_mode_data_received
        # Echo ($2F): show in RX display too
        if hasattr(mode, "on_echo_received"):
            mode.on_echo_received = self._on_mode_echo_received
        # Link messages → RX display
        if hasattr(mode, "on_link_message"):
            mode.on_link_message = self._on_mode_link_message
        logger.debug("Mode callbacks wired for: %s", mode.name)

    def _on_mode_data_received(self, data: bytes) -> None:
        """Display decoded data from active mode in RX panel."""
        try:
            text = data.decode("ascii", errors="replace")
        except Exception:
            text = repr(data)
        # Show in RX display
        self._log_terminal(text)
        # Show in monitor (decoded mode)
        if self._monitor_container.isVisible():
            if self._mon_btn_decoded.isChecked():
                self._log_monitor(f"[DATA] {text.rstrip()}")
            elif not self._mon_btn_decoded.isChecked():
                self._monitor_raw("rx", data)

    def _on_mode_echo_received(self, data: bytes) -> None:
        """Display echoed TX chars ($2F) in RX panel."""
        try:
            text = data.decode("ascii", errors="replace")
        except Exception:
            text = repr(data)
        self._log_terminal(f"[echo] {text}")
        if self._monitor_container.isVisible():
            if self._mon_btn_decoded.isChecked():
                self._log_monitor(f"[ECHO] {text.rstrip()}")

    def _on_mode_link_message(self, msg: str) -> None:
        """Display link state messages in RX panel."""
        self._log_terminal(f"*** {msg} ***")
        self._log_monitor(f"[LINK] {msg}")

    def _on_mode_switch_failed(self, reason: str) -> None:
        QMessageBox.warning(self, "Mode Switch Failed",
                            f"Could not switch mode:\n{reason}")

    # ------------------------------------------------------------------
    # Slots — parameter dialogs (placeholders)
    # ------------------------------------------------------------------

    def _on_tnc_config(self) -> None:
        dlg = TncConfigDialog(self._config, parent=self)
        if dlg.exec() == TncConfigDialog.DialogCode.Accepted:
            self._config = dlg.get_config()

    def _on_load_settings(self) -> None:
        """Load settings from INI file and apply to UI."""
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Settings", str(self._config_mgr._path.parent),
            "INI Files (*.ini);;All Files (*)"
        )
        if not path:
            return
        from pathlib import Path
        old_path = self._config_mgr._path
        self._config_mgr._path = Path(path)
        self._config_mgr.load()
        self._config_mgr._path = old_path
        self._app_config = self._config_mgr.app
        self.statusBar().showMessage(f"Settings loaded from {path}", 4000)
        self._log_monitor(f"[SYS] Settings loaded: {path}")

    def _on_save_settings(self) -> None:
        """Save current settings to INI file."""
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Settings", str(self._config_mgr._path),
            "INI Files (*.ini);;All Files (*)"
        )
        if not path:
            return
        from pathlib import Path
        old_path = self._config_mgr._path
        self._config_mgr._path = Path(path)
        self._config_mgr.save()
        self._config_mgr._path = old_path
        self.statusBar().showMessage(f"Settings saved to {path}", 4000)
        self._log_monitor(f"[SYS] Settings saved: {path}")

    def _on_params_hf_packet(self) -> None:
        """Open HF Packet Parameters dialog."""
        from pk232py.config import ConfigManager
        dlg = HFPacketParamsDialog(self._app_config.hf_packet, parent=self)
        if dlg.exec() == HFPacketParamsDialog.DialogCode.Accepted:
            self._log_monitor("[SYS] HF Packet parameters updated")

    def _on_params_misc(self) -> None:
        """Open Misc Parameters dialog."""
        dlg = MiscParamsDialog(parent=self)
        mi = self._app_config.misc
        dlg.set_values(
            canline=mi.canline, canpac=mi.canpac, command=mi.command,
            sendpac=mi.sendpac, mark=mi.mark, space=mi.space,
        )
        if dlg.exec() == MiscParamsDialog.DialogCode.Accepted:
            v = dlg.get_values()
            mi.canline  = v["canline"];  mi.canpac  = v["canpac"]
            mi.command  = v["command"];  mi.sendpac = v["sendpac"]
            mi.mark     = v["mark"];     mi.space   = v["space"]
            self._config_mgr.save()
            self._log_monitor("[SYS] Misc parameters updated")

    def _on_params_pactor(self) -> None:
        """Open PACTOR Parameters dialog."""
        dlg = PACTORParamsDialog(self._app_config.pactor, parent=self)
        if dlg.exec() == PACTORParamsDialog.DialogCode.Accepted:
            self._log_monitor("[SYS] PACTOR parameters updated")

    def _on_params_amtor(self) -> None:
        """Open AMTOR / NAVTEX / TDM Parameters dialog."""
        dlg = AMTORParamsDialog(parent=self)
        am = self._app_config.amtor
        dlg.set_values(
            myselcal=am.myselcal, myaltcal=am.myaltcal, myident=am.myident,
            arqtmo=am.arqtmo, arqtol=am.arqtol, adelay=am.adelay,
            tdbaud=am.tdbaud, tdchan=am.tdchan, xlength=am.xlength,
            rfec=am.rfec, rxrev=am.rxrev, srxall=am.srxall,
            txrev=am.txrev, usos=am.usos, wideshft=am.wideshft, xmitok=am.xmitok,
        )
        if dlg.exec() == AMTORParamsDialog.DialogCode.Accepted:
            v = dlg.get_values()
            am.myselcal = v["myselcal"]; am.myaltcal = v["myaltcal"]
            am.myident  = v["myident"];  am.arqtmo   = v["arqtmo"]
            am.arqtol   = v["arqtol"];   am.adelay   = v["adelay"]
            am.tdbaud   = v["tdbaud"];   am.tdchan   = v["tdchan"]
            am.xlength  = v["xlength"];  am.rfec     = v["rfec"]
            am.rxrev    = v["rxrev"];    am.srxall   = v["srxall"]
            am.txrev    = v["txrev"];    am.usos     = v["usos"]
            am.wideshft = v["wideshft"]; am.xmitok   = v["xmitok"]
            self._config_mgr.save()
            self._log_monitor("[SYS] AMTOR/NAVTEX/TDM parameters updated")

    def _on_params_baudot(self) -> None:
        """Open BAUDOT / ASCII / CW Parameters dialog."""
        dlg = BaudotParamsDialog(parent=self)
        ba = self._app_config.baudot
        dlg.set_values(
            mspeed=ba.mspeed, mweight=ba.mweight, code=ba.code,
            xlength=ba.xlength, xbaud=ba.xbaud, aab=ba.aab,
            alfrtty=ba.alfrtty, diddle=ba.diddle, mopt=ba.mopt,
            rxrev=ba.rxrev, txrev=ba.txrev, usos=ba.usos,
            wideshft=ba.wideshft, xmitok=ba.xmitok,
        )
        if dlg.exec() == BaudotParamsDialog.DialogCode.Accepted:
            v = dlg.get_values()
            ba.mspeed  = v["mspeed"];  ba.mweight = v["mweight"]
            ba.code    = v["code"];    ba.xlength = v["xlength"]
            ba.xbaud   = v["xbaud"];   ba.aab     = v["aab"]
            ba.alfrtty = v["alfrtty"]; ba.diddle  = v["diddle"]
            ba.mopt    = v["mopt"];    ba.rxrev   = v["rxrev"]
            ba.txrev   = v["txrev"];   ba.usos    = v["usos"]
            ba.wideshft= v["wideshft"]; ba.xmitok  = v["xmitok"]
            self._config_mgr.save()
            self._log_monitor("[SYS] BAUDOT/ASCII/CW parameters updated")

    def _on_params_maildrop(self) -> None:
        """Open MailDrop Parameters dialog."""
        dlg = MailDropParamsDialog(parent=self)
        md = self._app_config.maildrop
        dlg.set_values(
            homebbs=md.homebbs, mymail=md.mymail, mtext=md.mtext,
            kilonfwd=md.kilonfwd, maildrop=md.maildrop, mdmon=md.mdmon,
            mmsg=md.mmsg, tmail=md.tmail, third_party=md.third_party,
        )
        if dlg.exec() == MailDropParamsDialog.DialogCode.Accepted:
            v = dlg.get_values()
            md.homebbs     = v["homebbs"];     md.mymail      = v["mymail"]
            md.mtext       = v["mtext"];       md.kilonfwd    = v["kilonfwd"]
            md.maildrop    = v["maildrop"];    md.mdmon       = v["mdmon"]
            md.mmsg        = v["mmsg"];        md.tmail       = v["tmail"]
            md.third_party = v["third_party"]
            self._config_mgr.save()
            self._log_monitor("[SYS] MailDrop parameters updated")

    def _on_toggle_serial_status(self) -> None:
        """Show/hide serial signal status rows (rows 2+3)."""
        visible = self._act_serial_status.isChecked()
        self._footer.setVisible(visible)
        if visible:
            self._update_serial_signals()   # immediate update
            if self._serial.is_connected:
                self._serial_sig_timer.start()
        else:
            self._serial_sig_timer.stop()

    @staticmethod
    def _sig_style_active() -> str:
        return ("color:#00cc00; background:#0a1a0a;"
                "border:1px solid #00cc00; border-radius:3px;"
                "padding:1px 4px; font-weight:bold;")

    @staticmethod
    def _sig_style_inactive() -> str:
        return ("color:#555555; background:#1a1a1a;"
                "border:1px solid #333; border-radius:3px;"
                "padding:1px 4px;")

    def _set_sig(self, label, active: bool) -> None:
        label.setStyleSheet(
            self._sig_style_active() if active else self._sig_style_inactive()
        )

    def _update_serial_signals(self) -> None:
        """Poll serial port signals and update both status bar rows."""
        connected = self._serial.is_connected
        self._set_sig(self._ssl_connected, connected)

        # ── Row 1: Hardware signals ────────────────────────────────────
        if not connected:
            for lbl in [self._ssl_cts, self._ssl_dsr, self._ssl_dcd,
                        self._ssl_rts, self._ssl_dtr]:
                self._set_sig(lbl, False)
        else:
            try:
                port = self._serial._serial
                if port is None or not port.is_open:
                    return
                def _read(attr):
                    try: return bool(getattr(port, attr))
                    except Exception: return False
                self._set_sig(self._ssl_cts, _read("cts"))
                self._set_sig(self._ssl_dsr, _read("dsr"))
                self._set_sig(self._ssl_dcd, _read("dcd"))
                self._set_sig(self._ssl_rts, _read("rts"))
                self._set_sig(self._ssl_dtr, _read("dtr"))
            except Exception:
                pass

        # ── Row 2: Program/TNC status ──────────────────────────────────
        self._set_sig(self._ssl_host, self._serial.is_host_mode)
        # PTT and CON are updated via frame_received — no polling needed
        # (see _on_frame_received for PTT/CON logic)

    def _poll_opmode(self) -> None:
        """Send OPMODE query to TNC — keeps monitor alive with responses."""
        if self._serial.is_host_mode and self._monitor_container.isVisible():
            self._serial.send_command(b"OP")   # OPMODE query

    def _blink_rx(self) -> None:
        """Flash RX indicator for 150ms."""
        self._ssl_rx.setStyleSheet(self._sig_style_active())
        self._rx_blink_timer.start()

    def _blink_tx(self) -> None:
        """Flash TX indicator for 150ms."""
        self._ssl_tx.setStyleSheet(self._sig_style_active())
        self._tx_blink_timer.start()

    def _on_toggle_monitor(self, checked: bool) -> None:
        self._monitor_container.setVisible(checked)
        self._splitter.setSizes([630, 270] if checked else [900, 0])
        if checked and self._serial.is_host_mode:
            self._opmode_timer.start()
            self._poll_opmode()   # immediate first poll
        elif not checked:
            self._opmode_timer.stop()

    def _on_appearance(self) -> None:
        """Open Appearance settings dialog."""
        dlg = AppearanceDialog(self._app_config.appearance, parent=self)
        if dlg.exec() == AppearanceDialog.DialogCode.Accepted:
            self._config_mgr.save()
            self._apply_appearance()
            self._log_monitor("[SYS] Appearance settings updated")

    def _apply_appearance(self) -> None:
        """Apply appearance settings to all display widgets."""
        a = self._app_config.appearance
        font = QFont(a.font_family, a.font_size)
        style_rx = (
            f"background-color:{a.bg_color}; "
            f"color:{a.fg_color}; border:none;"
        )
        style_tx = (
            f"background-color:{a.bg_color}; "
            f"color:{a.fg_color}; border:1px solid #444;"
        )
        style_vt = (
            f"background-color:{a.bg_color}; "
            f"color:{a.fg_color}; border:none;"
        )
        # Host Mode view
        self._rx_display.setFont(font)
        self._rx_display.setStyleSheet(style_rx)
        self._tx_input.setFont(font)
        self._tx_input.setStyleSheet(style_tx)
        # Verbose terminal view
        self._vt_display.setFont(font)
        self._vt_display.setStyleSheet(style_vt)
        self._vt_input.setFont(font)
        self._vt_input.setStyleSheet(
            f"background-color:{a.bg_color}; "
            f"color:{a.fg_color}; border:none;"
        )
        logger.debug("Appearance applied: %s %dpt bg=%s fg=%s",
                     a.font_family, a.font_size, a.bg_color, a.fg_color)

    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            f"About {APP_TITLE}",
            f"<b>{APP_TITLE}</b> v{__version__}<br><br>"
            "Modern cross-platform client for the<br>"
            "<b>AEA PK-232 / PK-232MBX</b> multi-mode TNC.<br><br>"
            "Python 3 + PyQt6 &nbsp;|&nbsp; GPL v2 &nbsp;|&nbsp; Open Source<br><br>"
            "73 de OE3GAS",
        )

    # ------------------------------------------------------------------
    # Slots — incoming frames (monitor only — dispatch via ModeManager)
    # ------------------------------------------------------------------

    def _on_frame_received(self, frame: HostFrame) -> None:
        """Log every incoming frame to monitor and terminal.

        Frame dispatch to the active mode is handled by ModeManager.on_frame()
        which is also connected to frame_received.
        """
        # RX blink
        if self._act_serial_status.isChecked():
            self._blink_rx()

        # PTT indicator + OPMODE response display
        if frame.kind == FrameKind.CMD_RESP:
            if frame.mnemonic == b"OV":
                self._set_sig(self._ssl_ptt, True)
            elif frame.mnemonic == b"SI":
                self._set_sig(self._ssl_ptt, False)
            elif frame.mnemonic == b"OP":
                # OPMODE response — show in status bar
                try:
                    opmode_txt = frame.data[2:].decode('ascii','replace').strip()
                    if opmode_txt:
                        self.statusBar().showMessage(
                            f"TNC: {opmode_txt}", 4000
                        )
                except Exception:
                    pass
        # CON indicator
        if frame.kind == FrameKind.LINK_MSG:
            t = frame.text.lower()
            if "connected" in t:
                self._set_sig(self._ssl_con, True)
            elif "disconnect" in t:
                self._set_sig(self._ssl_con, False)
                self._set_sig(self._ssl_ptt, False)

        # Monitor logging — all modes
        if self._monitor_container.isVisible():
            if self._mon_btn_decoded.isChecked():
                # Decoded: human-readable frame description
                try:
                    mn = frame.mnemonic.decode('ascii','replace')                          if frame.mnemonic else ""
                except Exception:
                    mn = ""
                try:
                    txt = frame.text.strip()[:80] if frame.text else ""
                    if not txt and frame.data:
                        txt = frame.data.hex(" ")[:48]
                except Exception:
                    txt = repr(frame.data[:20])
                self._log_monitor(
                    f"[RX] {frame.kind.name:12s} "
                    f"ctl=0x{frame.ctl:02X} ch={frame.channel}"
                    f"{' '+mn if mn else ''}"
                    f"  {txt}" if txt else ""
                )
            # Raw/Hex: handled via _on_raw_data_received

        # Terminal: show received text for data frames
        if frame.kind in (FrameKind.RX_DATA, FrameKind.RX_MONITOR,
                          FrameKind.ECHO):
            text = frame.text.strip()
            if text:
                self._log_terminal(text)

    def _on_status_message(self, msg: str) -> None:
        """Route status messages: errors → popup, info → status bar."""
        # Keywords that indicate an error requiring user attention
        _error_keywords = (
            "error", "Error", "failed", "Failed",
            "cannot", "Cannot", "not installed",
        )
        if any(kw in msg for kw in _error_keywords):
            QMessageBox.critical(self, "TNC Error", msg)
        else:
            self.statusBar().showMessage(msg, 5000)

    # ------------------------------------------------------------------
    # UI state updates
    # ------------------------------------------------------------------

    def _update_connection_ui(self, connected: bool) -> None:
        self._act_connect_verbose.setEnabled(not connected)
        self._act_connect_host.setEnabled(not connected)
        self._act_disconnect.setEnabled(connected)
        self._act_host_off.setEnabled(connected)
        self._act_recovery.setEnabled(connected)
        self._tb_connect.setEnabled(not connected)
        self._tb_disconnect.setEnabled(connected)
        self._tb_recovery.setEnabled(connected)
        # Always update serial signals immediately on connect/disconnect
        self._update_serial_signals()
        # Keep timer running whenever serial status bar is visible
        if self._act_serial_status.isChecked():
            if connected:
                self._serial_sig_timer.start()
            else:
                self._serial_sig_timer.stop()

        if connected:
            self._sb_port.setText(f"Port: {self._config.port_name}")
            self._sb_baud.setText(f"Baud: {self._config.baudrate}")
        else:
            self._sb_port.setText("Port: ---")
            self._sb_baud.setText("Baud: ---")
            self._sb_mode.setText("Mode: OFFLINE")
            self._mode_combo.setEnabled(False)

    def _update_host_mode_ui(self, active: bool) -> None:
        """Switch view and enable mode selector when Host Mode is active."""
        self._mode_combo.setEnabled(active)
        if active:
            self._sb_mode.setText("Mode: HOST")
            self._stack.setCurrentIndex(0)
        else:
            self._sb_mode.setText("Mode: VERBOSE")
            self._stack.setCurrentIndex(1)
        self._set_sig(self._ssl_host, active)
        if active:
            self._opmode_timer.start()
        else:
            self._opmode_timer.stop()
            self._set_sig(self._ssl_ptt, False)
            self._set_sig(self._ssl_con, False)

    # ------------------------------------------------------------------
    # Output helpers
    # ------------------------------------------------------------------

    def _log_terminal(self, text: str) -> None:
        self._terminal.append(text)

    def _log_monitor(self, text: str, raw: bytes = b"") -> None:
        """Append text to monitor. If raw bytes given, show per selected mode."""
        if raw and hasattr(self, '_mon_btn_raw'):
            if self._mon_btn_hex.isChecked():
                # Hex dump: offset  hex  ascii
                lines = []
                for i in range(0, len(raw), 16):
                    chunk = raw[i:i+16]
                    hex_part = " ".join(f"{b:02X}" for b in chunk)
                    asc_part = "".join(
                        chr(b) if 32 <= b < 127 else "." for b in chunk
                    )
                    lines.append(f"{i:04X}  {hex_part:<48}  {asc_part}")
                self._monitor.append("\n".join(lines))
                return
            elif self._mon_btn_raw.isChecked():
                try:
                    decoded = raw.decode('ascii', errors='replace')
                except Exception:
                    decoded = repr(raw)
                self._monitor.append(decoded)
                return
        self._monitor.append(text)

    def _monitor_raw(self, direction: str, data: bytes) -> None:
        """Log raw serial data to monitor (TX or RX direction)."""
        if not self._monitor_container.isVisible():
            return
        if self._mon_btn_hex.isChecked():
            prefix = f"{'>>TX' if direction=='tx' else '<<RX'} "
            lines = []
            for i in range(0, len(data), 16):
                chunk = data[i:i+16]
                hex_part = " ".join(f"{b:02X}" for b in chunk)
                asc_part = "".join(
                    chr(b) if 32 <= b < 127 else "." for b in chunk
                )
                lines.append(
                    f"{prefix}{i:04X}  {hex_part:<48}  {asc_part}"
                )
            self._monitor.append("\n".join(lines))
        elif self._mon_btn_raw.isChecked():
            try:
                text = data.decode('ascii', errors='replace')
            except Exception:
                text = repr(data)
            prefix = ">> " if direction == "tx" else "<< "
            self._monitor.append(prefix + repr(text))
        # In "Decoded" mode: raw serial not shown (only frames shown)

    def _update_utc_clock(self) -> None:
        utc = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self._sb_time.setText(f"UTC: {utc}")

    # ------------------------------------------------------------------
    # Input / send
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event) -> bool:
        """Intercept keys in TX input (Host Mode) and verbose terminal."""
        if event.type() == QEvent.Type.KeyPress:
            if obj is self._tx_input:
                if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                        and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)):
                    self._on_send()
                    return True
            elif obj is self._vt_input:
                key  = event.key()
                mods = event.modifiers()
                ctrl = Qt.KeyboardModifier.ControlModifier
                # Enter: send command + CR/LF
                if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    if mods & Qt.KeyboardModifier.ShiftModifier:
                        # Shift+Enter: bare CR only
                        self._vt_send_raw(b"\r", echo="[CR]\n",
                                          color="#888888")
                    else:
                        self._on_vt_send()
                    return True
                # Ctrl+C → $03: TNC back to COMMAND mode
                if key == Qt.Key.Key_C and (mods & ctrl):
                    self._vt_send_raw(b"\x03", echo="[CTRL-C]\n",
                                      color="#ff9900")
                    return True
                # Ctrl+Z → $1A: PACTOR OVER / PTOVER char
                if key == Qt.Key.Key_Z and (mods & ctrl):
                    self._vt_send_raw(b"\x1a", echo="[CTRL-Z]\n",
                                      color="#ff9900")
                    return True
        return super().eventFilter(obj, event)

    def _vt_send_raw(self, data: bytes, echo: str = "",
                     color: str = "#888888") -> None:
        """Send raw bytes to TNC without automatic CR/LF."""
        if echo:
            self._vt_append(echo, color=color)
        if self._serial.is_connected:
            self._serial.write_verbose(data)
            if self._act_serial_status.isChecked():
                self._blink_tx()
            if self._monitor_container.isVisible():
                if not self._mon_btn_decoded.isChecked():
                    self._monitor_raw("tx", data)
        else:
            self._vt_append("[ERROR] Not connected\n", color="#f44747")

    def _on_vt_send(self) -> None:
        """Send a command in verbose terminal mode (Enter pressed)."""
        text = self._vt_input.toPlainText().strip()
        if not text:
            return
        self._vt_input.clear()
        self._vt_append(f"cmd:{text}\n", color="#569cd6")
        if self._serial.is_connected:
            raw_tx = f"{text}\r\n".encode('ascii', errors='replace')
            self._serial.write_verbose(raw_tx)
            if self._act_serial_status.isChecked():
                self._blink_tx()
            if self._monitor_container.isVisible():
                if not self._mon_btn_decoded.isChecked():
                    self._monitor_raw("tx", raw_tx)
        else:
            self._vt_append("[ERROR] Not connected\n", color="#f44747")

    def _vt_append(self, text: str, color: str = "#cccccc") -> None:
        """Append coloured text to the verbose terminal display."""
        from PyQt6.QtGui import QTextCursor, QColor
        cursor = self._vt_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = cursor.charFormat()
        fmt.setForeground(QColor(color))
        cursor.setCharFormat(fmt)
        cursor.insertText(text)
        self._vt_display.setTextCursor(cursor)
        self._vt_display.ensureCursorVisible()

    def _on_vt_rx_data(self, data: bytes) -> None:
        """Display raw bytes received from TNC in verbose terminal."""
        try:
            text = data.decode('ascii', errors='replace')
        except Exception:
            text = repr(data)
        self._vt_append(text, color="#cccccc")

    def _on_raw_data_received(self, data: bytes) -> None:
        """Display raw serial data in verbose terminal (only when in verbose mode)."""
        if self._stack.currentIndex() == 1:
            self._on_vt_rx_data(data)

    def _on_send(self) -> None:
        """Send the input field contents via the active mode.

        If a mode is active, its data_frame() method is used to build
        the outgoing frame.  Falls back to raw send_data() if no mode
        is active (v0.1 behaviour).
        """
        text = self._tx_input.toPlainText().strip()
        if not text:
            return

        if not self._serial.is_connected:
            QMessageBox.warning(self, "Not Connected",
                            "Please connect to the TNC first.")
            return

        if not self._serial.is_host_mode:
            QMessageBox.warning(self, "Host Mode Not Active",
                            "Host Mode is not active.\nPlease initialise the TNC first.")
            return

        self._log_terminal(
            f"<span style='color:#569cd6;'>&gt; {text}</span>"
        )
        self._log_monitor(f"[TX] data={text!r}")

        mode = self._modes.current_mode
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if mode is not None and hasattr(mode, 'data_frame'):
                # Use mode-specific frame builder
                frame_bytes = mode.data_frame(line)
                # Extract channel and data from built frame, send via serial
                self._serial.send_data(
                    frame_bytes[2:-1],   # payload between CTL and ETB
                    channel=0,
                )
            else:
                # Fallback: raw data send
                self._serial.send_data(
                    line.encode('ascii', errors='replace')
                )

        self._tx_input.clear()

    # ------------------------------------------------------------------
    # Window close
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        if self._serial.is_connected:
            reply = QMessageBox.question(
                self,
                "Exit",
                "TNC is still connected. Exit anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._serial.disconnect_port()
        self._save_window_geometry()
        # Auto-save settings on exit
        try:
            self._config_mgr.save()
        except Exception:
            pass
        event.accept()

    # ------------------------------------------------------------------
    # Window geometry persistence (QSettings)
    # ------------------------------------------------------------------

    def _save_window_geometry(self) -> None:
        """Save window position and size to QSettings (registry/config)."""
        s = QSettings("OE3GAS", APP_TITLE)
        s.setValue("geometry", self.saveGeometry())
        s.setValue("windowState", self.saveState())
        # Save splitter position (monitor panel)
        s.setValue("splitterSizes", self._splitter.sizes())
        logger.debug("Window geometry saved")

    def _restore_window_geometry(self) -> None:
        """Restore window position and size from QSettings."""
        s = QSettings("OE3GAS", APP_TITLE)
        geom = s.value("geometry")
        if geom:
            self.restoreGeometry(geom)
        state = s.value("windowState")
        if state:
            self.restoreState(state)
        sizes = s.value("splitterSizes")
        if sizes:
            try:
                self._splitter.setSizes([int(x) for x in sizes])
            except Exception:
                pass
        logger.debug("Window geometry restored")