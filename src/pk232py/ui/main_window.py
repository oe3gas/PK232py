# === E:\PK232\pk232py_repo\src\pk232py\ui\main_window.py ===
# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  --  GPL v2
"""Main window of PK232PY.

Layout:
  +--------------------------------------------------+
  |  Menu: File | TNC | View | Parameters | Configure |
  +--------------------------------------------------+
  |  Toolbar: [Connect] [Disconnect] [Host Mode]     |
  |           [Mode: HF Packet v]                    |
  +----------------------+---------------------------+
  |                      |                           |
  |  Opmode screen stack |  Monitor panel            |
  |  (mode-specific UI)  |  (toggleable)             |
  +----------------------+---------------------------+
  |  Status: Port | Baud | Mode | UTC time           |
  +--------------------------------------------------+
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

# Opmode screens — embedded in MainWindow via QStackedWidget
from .screens.baudot_screen  import BaudotScreen
from .screens.ascii_screen   import AsciiScreen
from .screens.amtor_screen   import AmtorScreen
from .screens.morse_screen   import MorseScreen
from .screens.navtex_screen  import NavtexScreen
from .screens.signal_screen  import SignalScreen
from .screens.fax_screen     import FaxScreen
from .screens.pactor_screen  import PactorScreen   # added

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

 # File 
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

 # TNC 
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

        self._act_host_off = QAction("Leave Host Mode (Enter Verbose Mode)", self)
        self._act_host_off.setStatusTip("Leave Host Mode, return TNC to verbose terminal")
        self._act_host_off.triggered.connect(self._on_host_mode_exit)
        tnc_menu.addAction(self._act_host_off)

        self._act_recovery = QAction("Host Mode &Recovery", self)
        self._act_recovery.setStatusTip(
            "Emergency recovery: free TNC from stuck Host Mode"
        )
        self._act_recovery.triggered.connect(self._on_recovery)
        tnc_menu.addAction(self._act_recovery)

 # View 
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

 # Parameters 
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

 # Configure 
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
        # ── Row 1: Connection controls ───────────────────────────────────────
        tb = QToolBar("Main", self)
        tb.setMovable(False)
        self.addToolBar(tb)

        self._tb_connect = tb.addAction("Connect")
        self._tb_connect.setToolTip("Connect to TNC (Ctrl+T)")
        self._tb_connect.triggered.connect(self._on_connect_verbose)

        self._tb_disconnect = tb.addAction("Disconnect")
        self._tb_disconnect.setToolTip("Disconnect (Ctrl+D)")
        self._tb_disconnect.triggered.connect(self._on_disconnect)

        tb.addSeparator()

        self._tb_host_on = tb.addAction("Host Mode")
        self._tb_host_on.setToolTip("Enter Host Mode")
        self._tb_host_on.triggered.connect(self._on_host_mode_enter)

        self._tb_recovery = tb.addAction("Recovery")
        self._tb_recovery.setToolTip("Host Mode Recovery")
        self._tb_recovery.triggered.connect(self._on_recovery)

        tb.addSeparator()

        # Mode selector ComboBox
        tb.addWidget(QLabel(" Mode: "))
        self._mode_combo = QComboBox()
        self._mode_combo.setMinimumWidth(120)
        self._mode_combo.setToolTip("Select operating mode")
        # Build display list: merge "AMTOR ARQ" and "AMTOR FEC" into "AMTOR"
        _seen: set[str] = set()
        for name in self._modes.available_modes():
            display = "AMTOR" if name.startswith("AMTOR") else name
            if display not in _seen:
                self._mode_combo.addItem(display)
                _seen.add(display)
        self._mode_combo.setEnabled(False)
        self._mode_combo.currentTextChanged.connect(self._on_mode_selected)
        tb.addWidget(self._mode_combo)

        # ── Spacer + Mode/Connection status indicator (right-aligned) ────────
        spacer = QWidget()
        from PyQt6.QtWidgets import QSizePolicy as QSP
        spacer.setSizePolicy(QSP.Policy.Expanding, QSP.Policy.Preferred)
        tb.addWidget(spacer)

        # Prominent mode indicator: shows OFFLINE / VERBOSE / HOST MODE
        # with colour coding so the current state is always visible.
        self._mode_indicator = QLabel("  OFFLINE  ")
        self._mode_indicator.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self._mode_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._mode_indicator.setMinimumWidth(140)
        self._mode_indicator.setFixedHeight(26)
        self._mode_indicator.setStyleSheet(self._indicator_style("offline"))
        tb.addWidget(self._mode_indicator)
        tb.addWidget(QLabel("  "))   # right padding

    # ── Mode indicator styles ─────────────────────────────────────────────────

    @staticmethod
    def _indicator_style(state: str) -> str:
        """Return stylesheet for the mode indicator label.

        state: 'offline' | 'verbose' | 'host' | 'switching'
        """
        styles = {
            "offline":   ("  OFFLINE  ",    "#888888", "#2a2a2a", "#555555"),
            "verbose":   ("  VERBOSE  ",    "#ffcc44", "#2a2200", "#776600"),
            "host":      ("  HOST MODE  ",  "#44ff88", "#00220f", "#007733"),
            "switching": ("  SWITCHING...","#88aaff", "#001133", "#224488"),
        }
        label, fg, bg, border = styles.get(state, styles["offline"])
        return (
            f"QLabel {{"
            f"  color: {fg};"
            f"  background-color: {bg};"
            f"  border: 2px solid {border};"
            f"  border-radius: 4px;"
            f"  padding: 2px 8px;"
            f"}}"
        )

    def _set_mode_indicator(self, state: str) -> None:
        """Update the mode indicator label text and colour."""
        texts = {
            "offline":   "  OFFLINE  ",
            "verbose":   "  VERBOSE MODE  ",
            "host":      "  HOST MODE  ",
            "switching": "  SWITCHING...  ",
        }
        self._mode_indicator.setText(texts.get(state, "  OFFLINE  "))
        self._mode_indicator.setStyleSheet(self._indicator_style(state))

    def _build_central(self) -> None:
        """Build the central widget with two views:
          - Page 0: Host Mode view  ->  QSplitter(opmode_stack | monitor)
          - Page 1: Verbose terminal view (terminal log + command input)

        The opmode_stack holds all 7 operating-mode screens as QWidgets.
        _switch_opmode(name) swaps the visible screen inside that inner stack.
        """
        # -- Outer stack: Page 0 = Host Mode, Page 1 = Verbose Terminal ------
        self._stack = QStackedWidget()

        # -- Page 0: Host Mode view -------------------------------------------
        host_page = QWidget()
        host_layout = QVBoxLayout(host_page)
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.setSpacing(0)

        outer = QSplitter(Qt.Orientation.Horizontal)

        # -- Left side: Opmode screen stack -----------------------------------
        # Each operating mode screen is a self-contained QWidget with its own
        # RX display, TX input, mode buttons and macro bar.  We create all
        # screens once here and switch between them via _opmode_stack.

        self._opmode_stack = QStackedWidget()

        # Map: ModeManager mode name -> screen widget.
        # Keys MUST exactly match the names in ALL_MODES (mode_manager.py).
        # "AMTOR ARQ" and "AMTOR FEC" share one screen — both keys point
        # to the same AmtorScreen instance.
        _amtor = AmtorScreen()
        self._opmode_screens: dict[str, QWidget] = {
            "Baudot RTTY":   BaudotScreen(),
            "ASCII RTTY":    AsciiScreen(),
            "AMTOR ARQ":     _amtor,
            "AMTOR FEC":     _amtor,       # same screen, different sub-mode
            "PACTOR":        PactorScreen(),   # added
            "CW / Morse":    MorseScreen(),
            "NAVTEX":        NavtexScreen(),
            "Signal (SIAM)": SignalScreen(),
            "FAX":           FaxScreen(),
        }
        # Add each unique screen widget to the stack once.
        # (AMTOR ARQ and AMTOR FEC share one widget — add it only once.)
        _added: set[int] = set()
        for screen in self._opmode_screens.values():
            if id(screen) not in _added:
                self._opmode_stack.addWidget(screen)
                _added.add(id(screen))

        # Default: show Baudot on startup
        self._opmode_stack.setCurrentWidget(self._opmode_screens["Baudot RTTY"])

        outer.addWidget(self._opmode_stack)

        # -- Right side: Monitor panel (toggleable) ---------------------------
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
            "Monitor - decoded frames / raw / hex"
        )
        mc_layout.addWidget(self._monitor)

        monitor_container.setVisible(False)
        outer.addWidget(monitor_container)
        outer.setSizes([900, 0])
        self._monitor_container = monitor_container

        self._splitter = outer
        host_layout.addWidget(outer)
        self._stack.addWidget(host_page)   # index 0


 # Page 1: Verbose Terminal view 
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
            "TNC verbose mode - echo and responses appear here."
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
        self._vt_input.setPlaceholderText("type command, Enter to send...")
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
        self._stack.setCurrentIndex(1)     # start in Verbose Terminal view
        self._wire_mode_callbacks()
        # Focus goes to verbose terminal input on startup
        QTimer.singleShot(0, lambda: self._vt_input.setFocus())

    # ------------------------------------------------------------------
    # Opmode screen helpers
    # ------------------------------------------------------------------

    @property
    def _rx_display(self) -> QTextEdit:
        """Return the RX display of the currently visible opmode screen.

        Falls back to the first screen's RX display if the active screen
        has no rx_display attribute (e.g. FAX, Signal, NAVTEX).
        Kept for compatibility with legacy code that references _rx_display.
        """
        screen = self._opmode_stack.currentWidget()
        if hasattr(screen, "rx_display"):
            return screen.rx_display
        # Receive-only screens have no rx_display usable as _terminal;
        # return a dummy that absorbs calls without crashing.
        return self._monitor   # safe fallback: monitor QTextEdit

    @property
    def _tx_input(self) -> QTextEdit | None:
        """Return the TX input of the currently visible opmode screen.

        Returns None for receive-only screens (NAVTEX, Signal, FAX).
        Kept for compatibility with legacy eventFilter / _on_send code.
        """
        screen = self._opmode_stack.currentWidget()
        if hasattr(screen, "tx_input"):
            return screen.tx_input
        return None

    @property
    def _terminal(self) -> QTextEdit:
        """Alias for _rx_display — used by _log_terminal."""
        return self._rx_display

    def _switch_opmode(self, name: str) -> None:
        """Switch the visible opmode screen to the one matching 'name'.

        Called from _on_mode_changed when ModeManager confirms a mode switch.
        If the name is not in _opmode_screens, the current screen is kept.
        """
        screen = self._opmode_screens.get(name)
        if screen is None:
            logger.warning("No opmode screen registered for mode: %s", name)
            return
        self._opmode_stack.setCurrentWidget(screen)
        logger.debug("Opmode screen switched to: %s", name)

        # For RTTY/Morse screens: set RECEIVE button green on entry
        # because the TNC starts in receive mode.
        _rx_modes = ("Baudot RTTY", "ASCII RTTY", "CW / Morse")
        if name in _rx_modes and hasattr(screen, "btn_receive"):
            screen.btn_receive.blockSignals(True)
            screen.btn_receive.setChecked(True)
            screen.btn_receive.blockSignals(False)
            # Trigger visual update directly (signals blocked above)
            screen._on_receive_toggled(True)

        # Focus the TX window of the new screen immediately
        QTimer.singleShot(0, self._focus_active_tx)

    def _focus_active_tx(self) -> None:
        """Set keyboard focus to the TX window of the active opmode screen."""
        tx = self._tx_input   # uses the property above
        if tx is not None:
            tx.setFocus()

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

 # Serial signal status bars (hidden by default) 
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

 # Row 1: Hardware signals 
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

 # Row 2: Program/TNC status 
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
        self._ssl_rx   = _sig_label("RX")
        self._ssl_tx   = _sig_label("TX")

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
 # SerialManager MainWindow
        self._serial.connection_changed.connect(self._update_connection_ui)
        self._serial.host_mode_changed.connect(self._update_host_mode_ui)
        self._serial.status_message.connect(self._on_status_message)
        self._serial.verbose_mode_ready.connect(self._on_verbose_mode_ready)
        self._serial.params_upload_required.connect(self._on_params_upload_required)
        self._serial.raw_data_received.connect(self._on_raw_data_received)

 # SerialManager ModeManager (frame dispatch)
        self._serial.frame_received.connect(self._modes.on_frame)
        self._serial.frame_received.connect(self._on_frame_received)

 # ModeManager MainWindow
        self._modes.mode_changed.connect(self._on_mode_changed)
        self._modes.mode_switch_failed.connect(self._on_mode_switch_failed)
        self._modes.status_message.connect(self._on_status_message)

    # ------------------------------------------------------------------
    # Slots -- TNC connection
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
        """Legacy defaults to verbose mode."""
        self._on_connect_verbose()

    def _on_disconnect(self) -> None:
        self._serial.disconnect_port()
        self._log_monitor("[SYS] Disconnected")

    def _on_verbose_mode_ready(self) -> None:
        """Called when TNC is in verbose mode.

        Always uploads parameters from INI to TNC.
        If _connect_mode == "host": additionally enters Host Mode after upload.
        If _connect_mode == "verbose": stays in verbose terminal after upload.
        """
        self._log_monitor("[SYS] TNC in verbose mode")
        self._sb_mode.setText("Mode: VERBOSE")
        self._set_mode_indicator("verbose")
        self._stack.setCurrentIndex(1)
        self._vt_input.setFocus()
        self._vt_display.clear()
        self._vt_append("[SYS] TNC ready in verbose mode\n")
        # Enable mode selector -- all modes with verbose_command selectable here
        self._mode_combo.setEnabled(True)

        # Always upload parameters from INI to TNC
        import threading
        connect_mode = self._connect_mode
        def _upload():
            self._vt_append("[SYS] Uploading parameters...\n")
            uploader = ParamsUploader(
                self._serial,
                self._app_config,
                echo_callback=self._vt_append,
            )
            n = uploader.upload()
            self._log_monitor(f"[SYS] {n} parameters uploaded")
            if connect_mode == "host":
                self._vt_append(
                    f"[SYS] {n} parameters uploaded -- entering Host Mode...\n"
                )
                self._serial.enter_host_mode()
            else:
                self._vt_append(
                    f"[SYS] {n} parameters uploaded -- verbose terminal ready\n"
                )
                self._vt_input.setFocus()
        threading.Thread(
            target=_upload, daemon=True, name="PK232-ParamUpload"
        ).start()

    def _on_params_upload_required(self) -> None:
        """Called when TNC rebooted same as verbose_mode_ready but with log message."""
        self._log_monitor("[SYS] TNC rebooted re-uploading parameters...")
        self._on_verbose_mode_ready()

    def _on_host_mode_enter(self) -> None:
        """Manual Host Mode entry from menu/toolbar.

        Sets the indicator to SWITCHING immediately so the user sees
        feedback while the TNC initialises. Replaced by HOST MODE once
        _update_host_mode_ui(active=True) fires.
        """
        if self._serial.is_connected:
            self._set_mode_indicator("switching")
            self._sb_mode.setText("Mode: Switching to Host Mode...")
            self._serial.enter_host_mode()

    def _on_host_mode_exit(self) -> None:
        if self._serial.is_connected:
            self._serial.exit_host_mode()

    def _on_recovery(self) -> None:
        if self._serial.is_connected:
            self._serial.recovery()
            self._log_monitor("[SYS] Host Mode recovery sent")

    # ------------------------------------------------------------------
    # Slots -- mode selection
    # ------------------------------------------------------------------

    # Display name -> ModeManager name mapping for merged entries
    _DISPLAY_TO_MODE: dict[str, str] = {
        "AMTOR": "AMTOR ARQ",   # dropdown shows "AMTOR", ModeManager needs "AMTOR ARQ"
    }
    # ModeManager name -> display name (reverse map, for syncing combo)
    _MODE_TO_DISPLAY: dict[str, str] = {
        "AMTOR ARQ": "AMTOR",
        "AMTOR FEC": "AMTOR",
    }

    def _on_mode_selected(self, name: str) -> None:
        """Called when the user selects a mode from the toolbar ComboBox.

        The combo shows display names (e.g. "AMTOR"). Map back to the
        ModeManager name before calling set_mode().
        """
        if not name:
            return
        if not self._serial.is_connected:
            return
        # Translate display name to ModeManager name
        mm_name = self._DISPLAY_TO_MODE.get(name, name)
        # Avoid spurious trigger during programmatic updates
        if mm_name == self._modes.current_mode_name:
            return
        logger.info("User selected mode: %s -> %s", name, mm_name)

        # Inform the user if a mode needs Host Mode but it's not active
        from pk232py.modes import MODE_BY_NAME
        cls = MODE_BY_NAME.get(mm_name)
        if cls is not None:
            needs_host = not getattr(cls, 'verbose_command', None)
            if needs_host and not self._serial.is_host_mode:
                QMessageBox.information(
                    self, "Host Mode required",
                    f"The mode '{name}' requires Host Mode.\n"
                    f"Please click 'Host Mode' to activate it first."
                )
                return
            # Modes that use verbose activation (e.g. PACTOR) will briefly
            # switch to Verbose Mode — inform the user so it is not surprising.
            has_host_cmd = bool(getattr(cls, 'host_command', b''))
            if not has_host_cmd and self._serial.is_host_mode:
                self._log_monitor(
                    f"[SYS] {mm_name} requires Verbose Mode activation "
                    f"-- exiting Host Mode temporarily"
                )

        self._log_monitor(f"[SYS] Switching to mode: {mm_name}")
        self._modes.set_mode(mm_name)

    def _on_mode_changed(self, name: str) -> None:
        """Called by ModeManager when mode switch completes.
        Switches the visible opmode screen and wires callbacks.
        """
        self._sb_mode.setText(f"Mode: {name}")
        self._log_monitor(f"[SYS] Mode switched to: {name}")
        # Sync ComboBox: translate ModeManager name to display name
        display_name = self._MODE_TO_DISPLAY.get(name, name)
        self._mode_combo.blockSignals(True)
        idx = self._mode_combo.findText(display_name)
        if idx >= 0:
            self._mode_combo.setCurrentIndex(idx)
        self._mode_combo.blockSignals(False)
        # Switch the visible opmode screen to match the new mode
        self._switch_opmode(name)
        # Wire active mode callbacks to UI
        self._wire_mode_callbacks()
        # Focus: TX window is handled by _switch_opmode via singleShot.
        # Only override focus to verbose terminal if not in Host Mode.
        if not self._serial.is_host_mode:
            self._vt_input.setFocus()

    def _wire_mode_callbacks(self) -> None:
        """Connect the active mode's data callbacks to the UI."""
        mode = self._modes.current_mode
        if mode is None:
            return

        # ARQ / general received data
        if hasattr(mode, "on_data_received"):
            mode.on_data_received = self._on_mode_data_received

        # PACTOR FEC / Unproto data ($3F) — same handler as ARQ data
        if hasattr(mode, "on_fec_received"):
            mode.on_fec_received = self._on_mode_data_received

        # Echo ($2F)
        if hasattr(mode, "on_echo_received"):
            mode.on_echo_received = self._on_mode_echo_received

        # Link messages → log + screen status label
        if hasattr(mode, "on_link_message"):
            screen = self._opmode_screens.get(mode.name)
            if screen is not None and hasattr(screen, "_set_status"):
                mode.on_link_message = self._make_link_handler(screen)
            else:
                mode.on_link_message = self._on_mode_link_message

        # Wire screen buttons (SEND, RECEIVE) to MainWindow slots
        self._wire_screen_buttons()

        logger.debug("Mode callbacks wired for: %s", mode.name)

    def _make_link_handler(self, screen):
        """Return a link-message handler that updates both the
        monitor log and the screen's _set_status label.

        Maps TNC link-message text to the status keys used by
        AmtorScreen and PactorScreen.
        """
        def handler(msg: str) -> None:
            # 1. General log / monitor
            self._on_mode_link_message(msg)
            # 2. Update screen status label
            m = msg.lower()
            if "connected" in m and "disconnect" not in m:
                status = "CONNECTED"
            elif "disconnect" in m:
                status = "DISCONN"
            elif "calling" in m or "connect request" in m:
                status = "CALLING"
            elif "fec" in m:
                status = "FEC TX"
            else:
                status = "STBY"
            screen._set_status(status)
        return handler

    def _wire_screen_buttons(self) -> None:
        """Connect SEND and RECEIVE buttons of the active screen
        to MainWindow slots.

        Called from _wire_mode_callbacks() whenever the mode changes.
        Safe to call multiple times — Qt ignores duplicate connections
        only if the same signal+slot pair is connected again, but we
        explicitly disconnect first to avoid stacking signals.
        """
        screen = self._opmode_stack.currentWidget()
        if screen is None:
            return

        # SEND button — toggled ON: activate TX; toggled OFF: no-op
        if hasattr(screen, "btn_send"):
            try:
                screen.btn_send.toggled.disconnect(self._on_screen_send)
            except (RuntimeError, TypeError):
                pass   # not connected yet — harmless
            screen.btn_send.toggled.connect(self._on_screen_send)

        # RECEIVE button — toggled ON: put TNC into receive; OFF: standby
        if hasattr(screen, "btn_receive"):
            try:
                screen.btn_receive.toggled.disconnect(self._on_screen_receive)
            except (RuntimeError, TypeError):
                pass
            screen.btn_receive.toggled.connect(self._on_screen_receive)

        # AMTOR mode buttons
        self._wire_amtor_buttons(screen)

        # PACTOR mode buttons
        self._wire_pactor_buttons(screen)

        # RBAUD dropdown — currentIndexChanged: send RB frame to TNC
        if hasattr(screen, "combo_rbaud"):
            try:
                screen.combo_rbaud.currentIndexChanged.disconnect(
                    self._on_screen_rbaud_changed
                )
            except (RuntimeError, TypeError):
                pass
            screen.combo_rbaud.currentIndexChanged.connect(
                self._on_screen_rbaud_changed
            )

        # Phase 3 — identity fields, spinboxes, toggles, NAVTEX filters
        self._wire_identity_fields(screen)
        self._wire_morse_params(screen)
        self._wire_toggle_buttons(screen)
        self._wire_navtex_filters(screen)

    def _on_screen_send(self, active: bool) -> None:
        """Called when the SEND button on the active screen is toggled.

        active=True:
          1. Send XMIT command (XM) — TNC keys PTT and starts DIDDLE.
          2. Send any text already in TX window.
          3. Wire tx_input.textChanged so every new character is sent
             immediately as a data frame.

        active=False:
          1. Warn if unsent text remains in TX window.
          2. Disconnect textChanged.
          3. Send RCVE command (RC) — TNC returns to receive.
        """
        if not self._serial.is_connected or not self._serial.is_host_mode:
            return

        tx = self._tx_input
        if tx is None:
            return

        from pk232py.comm.frame import build_command

        if active:
            # 1. Send XMIT — TNC keys PTT and starts DIDDLE
            xmit = build_command(b'XM')
            self._serial.send_command(xmit[2:4], xmit[4:-1])
            self._log_monitor("[TX] XMIT — PTT ON, DIDDLE started")

            # 2. Send any text already in TX window
            text = tx.toPlainText().strip()
            if text:
                self._send_rtty_text(text)
                tx.blockSignals(True)
                tx.clear()
                tx.blockSignals(False)

            # 3. Wire live-TX: every new character goes out immediately
            try:
                tx.textChanged.disconnect(self._on_rtty_text_changed)
            except (RuntimeError, TypeError):
                pass
            tx.textChanged.connect(self._on_rtty_text_changed)

            # 4. Return keyboard focus to TX window
            #    (btn_send has NoFocus but focus may have drifted)
            QTimer.singleShot(0, tx.setFocus)

        else:
            # 1. Warn if unsent text remains
            pending = tx.toPlainText().strip()
            if pending:
                rx = self._rx_display
                rx.moveCursor(rx.textCursor().MoveOperation.End)
                rx.insertPlainText("\n*** Still text to transmit! ***\n")

            # 2. Disconnect live-TX
            try:
                tx.textChanged.disconnect(self._on_rtty_text_changed)
            except (RuntimeError, TypeError):
                pass

            # 3. Send RCVE — TNC switches back to receive
            rcve = build_command(b'RC')
            self._serial.send_command(rcve[2:4], rcve[4:-1])
            self._log_monitor("[TX] RCVE — PTT OFF, back to receive")

    def _on_rtty_text_changed(self) -> None:
        """Called whenever TX window content changes while SEND is active.

        Sends the complete current content as a data frame, then clears
        the window — producing character-by-character live transmission.
        blockSignals prevents a recursive call when clearing the field.
        """
        if not self._serial.is_connected or not self._serial.is_host_mode:
            return
        tx = self._tx_input
        if tx is None:
            return
        text = tx.toPlainText()
        if not text:
            return
        tx.blockSignals(True)
        tx.clear()
        tx.blockSignals(False)
        self._send_rtty_text(text)

    def _send_rtty_text(self, text: str) -> None:
        """Send text as a data frame via the active mode.

        Baudot mode uppercases automatically via data_frame().
        send_data() expects raw payload bytes — not a full Host frame.
        Also echoes sent text to RX window (local TX echo) in TX colour
        so the operator can see what was transmitted.
        """
        if not self._serial.is_connected or not self._serial.is_host_mode:
            return
        self._serial.send_data(
            text.encode('ascii', errors='replace'),
            channel=0,
        )
        # Local TX echo: show sent chars in RX window in TX colour
        rx = self._rx_display
        from PyQt6.QtGui import QTextCursor, QColor
        cursor = rx.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = cursor.charFormat()
        fmt.setForeground(QColor("#ffee88"))   # TX yellow
        cursor.setCharFormat(fmt)
        cursor.insertText(text)
        # Reset colour to RX blue for subsequent received text
        fmt.setForeground(QColor("#88ccff"))
        cursor.setCharFormat(fmt)
        rx.setTextCursor(cursor)
        rx.ensureCursorVisible()
        self._log_monitor(f"[TX] {text!r}")

    def _on_screen_receive(self, active: bool) -> None:
        """Called when the RECEIVE button on the active screen is toggled.

        active=True:  send RECEIVE command to TNC for the current mode.
        active=False: return TNC to standby for the current mode.

        Each mode has a different receive-activation mnemonic:
          Baudot/ASCII RTTY  — RX is always on; no explicit command needed.
          AMTOR              — receive handled by ALIST / FEC buttons.
          Morse              — RX is always on; no explicit command needed.
          PACTOR             — receive via PTLIST (btn_ptlist on screen).
        For modes where no action is needed, the call is a graceful no-op.
        """
        if not self._serial.is_connected or not self._serial.is_host_mode:
            return

        mode = self._modes.current_mode
        if mode is None:
            return

        mode_name = mode.name

        if active:
            # Mode-specific receive activation
            if mode_name in ("Baudot RTTY", "ASCII RTTY", "CW / Morse"):
                # These modes receive continuously — no command needed.
                # The button is purely visual feedback for the operator.
                logger.debug("RECEIVE: %s — continuous RX, no TNC command",
                             mode_name)

            elif mode_name == "NAVTEX":
                # NAVTEX receives automatically — no command needed.
                logger.debug("RECEIVE: NAVTEX — auto RX")

            else:
                # Unknown mode — log and do nothing.
                logger.debug("RECEIVE: %s — no specific receive command",
                             mode_name)
        else:
            # RECEIVE toggled OFF — no explicit TNC command for most modes.
            logger.debug("RECEIVE OFF: %s", mode_name)

    def _on_screen_rbaud_changed(self, index: int) -> None:
        """Called when the RBAUD dropdown on the active screen changes.

        Reads the selected baud-rate string from the dropdown,
        converts it to an integer and sends an RB command frame.

        Only sent when Host Mode is active — silently ignored
        otherwise (e.g. when the screen is first built and the
        dropdown is populated programmatically).
        """
        if not self._serial.is_connected or not self._serial.is_host_mode:
            return

        mode = self._modes.current_mode
        if mode is None or not hasattr(mode, "rbaud_frame"):
            return

        # Read baud value from the dropdown text (e.g. "45", "100")
        screen = self._opmode_stack.currentWidget()
        if not hasattr(screen, "combo_rbaud"):
            return
        text = screen.combo_rbaud.currentText().strip()
        try:
            baud = int(text)
        except ValueError:
            logger.warning("RBAUD: invalid value %r", text)
            return

        # Update mode instance so get_init_frames() stays in sync
        mode.rbaud = baud

        # Send RB frame to TNC
        frame = mode.rbaud_frame(baud)
        self._serial.send_command(
            frame[2:4],   # mnemonic bytes
            frame[4:-1],  # argument bytes
        )
        logger.info("RBAUD set to %d Bd", baud)
        self._log_monitor(f"[PARAM] RBAUD → {baud} Bd")

    def _wire_amtor_buttons(self, screen) -> None:
        """Connect AMTOR mode buttons to TNC commands.

        Only wires buttons that exist on the screen — safe to call
        for non-AMTOR screens (all hasattr guards).
        """
        def _conn(btn_name: str, slot) -> None:
            btn = getattr(screen, btn_name, None)
            if btn is None:
                return
            try:
                btn.clicked.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
            btn.clicked.connect(slot)

        _conn("btn_arq",        self._on_amtor_arq)
        _conn("btn_fec",        self._on_amtor_fec)
        _conn("btn_selfec",     self._on_amtor_selfec)
        _conn("btn_alist",      self._on_amtor_alist)
        _conn("btn_stby",       self._on_amtor_stby)
        _conn("btn_achg",       self._on_amtor_achg)

    def _wire_pactor_buttons(self, screen) -> None:
        """Connect PACTOR mode buttons to TNC commands."""
        def _conn(btn_name: str, slot) -> None:
            btn = getattr(screen, btn_name, None)
            if btn is None:
                return
            try:
                btn.clicked.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
            btn.clicked.connect(slot)

        _conn("btn_connect",    self._on_pactor_connect)
        _conn("btn_ptlist",     self._on_pactor_ptlist)
        _conn("btn_ptsend",     self._on_pactor_ptsend)
        _conn("btn_disconnect", self._on_pactor_disconnect)
        _conn("btn_stby",       self._on_pactor_stby)

    # ------------------------------------------------------------------
    # AMTOR slots
    # ------------------------------------------------------------------

    def _amtor_send(self, frame: bytes) -> bool:
        """Send a pre-built AMTOR command frame. Returns True on success."""
        if not self._serial.is_connected or not self._serial.is_host_mode:
            return False
        return self._serial.send_command(frame[2:4], frame[4:-1])

    def _on_amtor_arq(self) -> None:
        """ARQ button — call the destination SELCAL (mnemonic AC)."""
        screen = self._opmode_stack.currentWidget()
        selcal = getattr(screen, "le_dest", None)
        if selcal is None:
            return
        dest = selcal.text().strip().upper()
        if not dest:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "ARQ Call",
                                "Please enter a destination SELCAL.")
            return
        from pk232py.modes.amtor import AMTORMode
        frame = AMTORMode.arq_call_frame(dest)
        if self._amtor_send(frame):
            self._log_monitor(f"[AMTOR] ARQ call → {dest}")

    def _on_amtor_fec(self) -> None:
        """FEC button — start Mode B broadcast (mnemonic FE)."""
        from pk232py.modes.amtor import AMTORMode
        frame = AMTORMode.fec_frame()
        if self._amtor_send(frame):
            self._log_monitor("[AMTOR] FEC broadcast started")

    def _on_amtor_selfec(self) -> None:
        """SELFEC button — selective FEC (mnemonic SE)."""
        screen = self._opmode_stack.currentWidget()
        selcal = getattr(screen, "le_dest", None)
        dest = selcal.text().strip().upper() if selcal else ""
        if not dest:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "SELFEC",
                                "Please enter a destination SELCAL.")
            return
        from pk232py.modes.amtor import AMTORMode
        frame = AMTORMode.selfec_frame(dest)
        if self._amtor_send(frame):
            self._log_monitor(f"[AMTOR] SELFEC → {dest}")

    def _on_amtor_alist(self) -> None:
        """ALIST button — Mode A listen (mnemonic AL)."""
        from pk232py.modes.amtor import AMTORMode
        frame = AMTORMode.alist_frame()
        if self._amtor_send(frame):
            self._log_monitor("[AMTOR] ALIST — listening")

    def _on_amtor_stby(self) -> None:
        """STBY button — return to AMTOR standby (mnemonic AM)."""
        if not self._serial.is_connected or not self._serial.is_host_mode:
            return
        from pk232py.comm.frame import build_command
        frame = build_command(b'AM')
        self._serial.send_command(frame[2:4], frame[4:-1])
        self._log_monitor("[AMTOR] Standby")

    def _on_amtor_achg(self) -> None:
        """ACHG button — ARQ changeover / break-in (mnemonic AG)."""
        if not self._serial.is_connected or not self._serial.is_host_mode:
            return
        from pk232py.comm.frame import build_command
        frame = build_command(b'AG')
        self._serial.send_command(frame[2:4], frame[4:-1])
        self._log_monitor("[AMTOR] ACHG — changeover sent")

    # ------------------------------------------------------------------
    # PACTOR slots
    # ------------------------------------------------------------------

    def _pactor_send(self, frame: bytes) -> bool:
        """Send a pre-built PACTOR command frame."""
        if not self._serial.is_connected:
            return False
        return self._serial.send_command(frame[2:4], frame[4:-1])

    def _on_pactor_connect(self) -> None:
        """Connect button — initiate PACTOR ARQ call.

        Sends PACTOR standby (PT) then ARQ call (AC {callsign}).
        MYPTCALL must already be set via get_init_frames().
        """
        screen = self._opmode_stack.currentWidget()
        le_dest = getattr(screen, "le_dest", None)
        if le_dest is None:
            return
        dest = le_dest.text().strip().upper()
        if not dest:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "PACTOR Connect",
                                "Please enter a destination callsign.")
            return
        if not self._serial.is_connected:
            return
        from pk232py.comm.frame import build_command
        # 1. Enter PACTOR standby
        stby = build_command(b'PT')
        self._serial.send_command(stby[2:4], stby[4:-1])
        # 2. Initiate ARQ call (mnemonic AC, same as AMTOR but for PACTOR)
        call = build_command(b'AC', dest.encode('ascii'))
        self._serial.send_command(call[2:4], call[4:-1])
        self._log_monitor(f"[PACTOR] Connecting → {dest}")

    def _on_pactor_ptlist(self) -> None:
        """PTLIST button — enter PACTOR listen mode (mnemonic PN)."""
        from pk232py.modes.pactor import PACTORMode
        frame = PACTORMode.ptlist_frame()
        if self._pactor_send(frame):
            self._log_monitor("[PACTOR] PTLIST — listening")

    def _on_pactor_ptsend(self) -> None:
        """PTSEND button — start PACTOR FEC unproto transmission (mnemonic PD).

        Sends TX window contents as PTSEND unproto.
        """
        if not self._serial.is_connected:
            return
        from pk232py.comm.frame import build_command
        # PD 1,2 = 100 baud, 2 repetitions (sensible default)
        frame = build_command(b'PD', b'1,2')
        self._serial.send_command(frame[2:4], frame[4:-1])
        self._log_monitor("[PACTOR] PTSEND started (100 Bd, 2x)")

    def _on_pactor_disconnect(self) -> None:
        """Disconnect button — terminate PACTOR ARQ (DI then PT standby)."""
        if not self._serial.is_connected:
            return
        from pk232py.comm.frame import build_command
        di = build_command(b'DI')
        self._serial.send_command(di[2:4], di[4:-1])
        self._log_monitor("[PACTOR] Disconnect sent")

    def _on_pactor_stby(self) -> None:
        """STBY button — return to PACTOR standby (mnemonic PT)."""
        if not self._serial.is_connected:
            return
        from pk232py.comm.frame import build_command
        frame = build_command(b'PT')
        self._serial.send_command(frame[2:4], frame[4:-1])
        self._log_monitor("[PACTOR] Standby")

    def _wire_identity_fields(self, screen) -> None:
        """Wire identity QLineEdit fields to TNC parameter frames.

        Covers:
          PACTOR  le_myptcall  → PACTORMode.myptcall_frame()  (MK)
          AMTOR   le_myselcal  → AMTORMode.myselcal_frame()   (MG)
          AMTOR   le_myaltcal  → AMTORMode.myaltcal_frame()   (MK)
          AMTOR   le_myident   → AMTORMode.myident_frame()    (MY)

        Uses editingFinished so the frame is only sent when the
        user leaves the field (Enter or focus-out), not on every
        keystroke.
        """
        def _wire(field_name: str, slot) -> None:
            field = getattr(screen, field_name, None)
            if field is None:
                return
            try:
                field.editingFinished.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
            field.editingFinished.connect(slot)

        _wire("le_myptcall",  self._on_pactor_myptcall_changed)
        _wire("le_myselcal",  self._on_amtor_myselcal_changed)
        _wire("le_myaltcal",  self._on_amtor_myaltcal_changed)
        _wire("le_myident",   self._on_amtor_myident_changed)

    def _on_pactor_myptcall_changed(self) -> None:
        """Send MYPTCALL frame when le_myptcall editingFinished fires."""
        if not self._serial.is_connected:
            return
        screen = self._opmode_stack.currentWidget()
        call = getattr(screen, "le_myptcall", None)
        if call is None:
            return
        text = call.text().strip().upper()
        if not text:
            return
        from pk232py.modes.pactor import PACTORMode
        frame = PACTORMode.myptcall_frame(text)
        self._serial.send_command(frame[2:4], frame[4:-1])
        # Keep mode instance in sync
        mode = self._modes.current_mode
        if hasattr(mode, "myptcall"):
            mode.myptcall = text
        self._log_monitor(f"[PARAM] MYPTCALL → {text}")

    def _on_amtor_myselcal_changed(self) -> None:
        """Send MYSELCAL frame when le_myselcal editingFinished fires."""
        if not self._serial.is_connected or not self._serial.is_host_mode:
            return
        screen = self._opmode_stack.currentWidget()
        field = getattr(screen, "le_myselcal", None)
        if field is None:
            return
        text = field.text().strip().upper()
        if not text:
            return
        from pk232py.modes.amtor import AMTORMode
        frame = AMTORMode.myselcal_frame(text)
        self._serial.send_command(frame[2:4], frame[4:-1])
        mode = self._modes.current_mode
        if hasattr(mode, "myselcal"):
            mode.myselcal = text
        self._log_monitor(f"[PARAM] MYSELCAL → {text}")

    def _on_amtor_myaltcal_changed(self) -> None:
        """Send MYALTCAL frame when le_myaltcal editingFinished fires."""
        if not self._serial.is_connected or not self._serial.is_host_mode:
            return
        screen = self._opmode_stack.currentWidget()
        field = getattr(screen, "le_myaltcal", None)
        if field is None:
            return
        text = field.text().strip().upper()
        from pk232py.modes.amtor import AMTORMode
        frame = AMTORMode.myaltcal_frame(text)
        self._serial.send_command(frame[2:4], frame[4:-1])
        mode = self._modes.current_mode
        if hasattr(mode, "myaltcal"):
            mode.myaltcal = text
        self._log_monitor(f"[PARAM] MYALTCAL → {text or '(cleared)'}")

    def _on_amtor_myident_changed(self) -> None:
        """Send MYIDENT frame when le_myident editingFinished fires."""
        if not self._serial.is_connected or not self._serial.is_host_mode:
            return
        screen = self._opmode_stack.currentWidget()
        field = getattr(screen, "le_myident", None)
        if field is None:
            return
        text = field.text().strip().upper()
        from pk232py.modes.amtor import AMTORMode
        frame = AMTORMode.myident_frame(text)
        self._serial.send_command(frame[2:4], frame[4:-1])
        mode = self._modes.current_mode
        if hasattr(mode, "myident"):
            mode.myident = text
        self._log_monitor(f"[PARAM] MYIDENT → {text or '(cleared)'}")

    # ------------------------------------------------------------------
    # Morse parameter wiring
    # ------------------------------------------------------------------

    def _wire_morse_params(self, screen) -> None:
        """Wire Morse SpinBoxes and LOCK button to TNC commands."""

        def _wire_sb(attr: str, slot) -> None:
            sb = getattr(screen, attr, None)
            if sb is None:
                return
            try:
                sb.valueChanged.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
            sb.valueChanged.connect(slot)

        def _wire_btn(attr: str, slot) -> None:
            btn = getattr(screen, attr, None)
            if btn is None:
                return
            try:
                btn.clicked.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
            btn.clicked.connect(slot)

        _wire_sb("sb_mspeed",  self._on_morse_mspeed_changed)
        _wire_sb("sb_mweight", self._on_morse_mweight_changed)
        _wire_sb("sb_mid",     self._on_morse_mid_changed)
        _wire_btn("btn_lock",  self._on_morse_lock)

    def _morse_send(self, frame: bytes) -> bool:
        """Send a Morse parameter frame. Guard: Host Mode required."""
        if not self._serial.is_connected or not self._serial.is_host_mode:
            return False
        return self._serial.send_command(frame[2:4], frame[4:-1])

    def _on_morse_mspeed_changed(self, value: int) -> None:
        """MSPEED spinbox changed — send MP frame (mnemonic MP)."""
        from pk232py.modes.morse import MorseMode
        frame = MorseMode.mspeed_frame(value)
        if self._morse_send(frame):
            mode = self._modes.current_mode
            if hasattr(mode, "mspeed"):
                mode.mspeed = value
            self._log_monitor(f"[PARAM] MSPEED → {value} WPM")

    def _on_morse_mweight_changed(self, value: int) -> None:
        """MWEIGHT spinbox changed — send MW frame (mnemonic MW)."""
        from pk232py.modes.morse import MorseMode
        frame = MorseMode.mweight_frame(value)
        if self._morse_send(frame):
            mode = self._modes.current_mode
            if hasattr(mode, "mweight"):
                mode.mweight = value
            self._log_monitor(f"[PARAM] MWEIGHT → {value}")

    def _on_morse_mid_changed(self, value: int) -> None:
        """MID spinbox changed — send MI frame (mnemonic MI)."""
        from pk232py.modes.morse import MorseMode
        frame = MorseMode.mid_frame(value)
        if self._morse_send(frame):
            mode = self._modes.current_mode
            if hasattr(mode, "mid"):
                mode.mid = value
            self._log_monitor(f"[PARAM] MID → {value} min")

    def _on_morse_lock(self) -> None:
        """LOCK button — lock RX speed to current signal (mnemonic LO)."""
        from pk232py.modes.morse import MorseMode
        frame = MorseMode.lock_frame()
        if self._morse_send(frame):
            self._log_monitor("[MORSE] LOCK — RX speed locked to signal")

    # ------------------------------------------------------------------
    # Toggle button wiring (RXREV, TXREV, EAS, WIDESHFT, PT200, …)
    # ------------------------------------------------------------------

    def _wire_toggle_buttons(self, screen) -> None:
        """Wire all toggle buttons on the active screen to TNC frames.

        Each entry: (widget_attr, mode_class_path, frame_method_name, instance_attr)
        The slot is built dynamically from these components.
        """
        mode = self._modes.current_mode
        if mode is None:
            return

        # Map: btn_attr → (frame_builder_callable, instance_attr_name)
        # frame_builder takes a bool and returns bytes
        from pk232py.modes.amtor   import AMTORMode
        from pk232py.modes.morse   import MorseMode
        from pk232py.modes.pactor  import PACTORMode
        from pk232py.modes.rtty_baudot import BaudotRTTYMode
        from pk232py.modes.rtty_ascii  import ASCIIRTTYMode

        toggle_map = {
            # AMTOR toggles
            "btn_rxrev":    (AMTORMode.rxrev_frame,   "rxrev"),
            "btn_txrev":    (AMTORMode.txrev_frame,   "txrev"),
            "btn_rfec":     (AMTORMode.rfec_frame,    "rfec"),
            "btn_srxall":   (AMTORMode.srxall_frame,  "srxall"),
            "btn_eas":      (AMTORMode.eas_frame,     "eas"),
            # Morse toggles (share same attr names, same mnemonic pattern)
            "btn_wordout":  (MorseMode.wordout_frame, "wordout"),
            "btn_moptt":    (None,                    None),   # MO toggle — handled separately
            # PACTOR toggles
            "btn_pt200":    (PACTORMode.pt200_frame,  None),
            "btn_pthuff":   (PACTORMode.pthuff_frame, None),
            "btn_ptround":  (PACTORMode.ptround_frame, None),
            # Baudot/ASCII toggles
            "btn_wideshft": (BaudotRTTYMode.wideshft_frame, "wideshft"),
        }

        # _toggle_slots: Dict btn_name → letzter verbundener TNC-Slot
        # Wird auf der Instanz gespeichert um bei erneutem Aufruf
        # nur unseren Slot zu trennen — nicht den screen-internen.
        if not hasattr(self, '_toggle_slots'):
            self._toggle_slots = {}

        for btn_name, (frame_fn, inst_attr) in toggle_map.items():
            btn = getattr(screen, btn_name, None)
            if btn is None or frame_fn is None:
                continue

            # Nur unseren eigenen Slot trennen (nicht screen-interne!)
            old_slot = self._toggle_slots.get(btn_name)
            if old_slot is not None:
                try:
                    btn.toggled.disconnect(old_slot)
                except (RuntimeError, TypeError):
                    pass

            # Neuen Slot erzeugen und speichern
            def _make_slot(fn, attr, bname):
                def slot(checked: bool) -> None:
                    if not self._serial.is_connected or not self._serial.is_host_mode:
                        return
                    frame = fn(checked)
                    self._serial.send_command(frame[2:4], frame[4:-1])
                    if attr:
                        m = self._modes.current_mode
                        if m and hasattr(m, attr):
                            setattr(m, attr, checked)
                    self._log_monitor(
                        f"[PARAM] {bname.replace('btn_', '').upper()}"
                        f" → {'ON' if checked else 'OFF'}"
                    )
                return slot

            new_slot = _make_slot(frame_fn, inst_attr, btn_name)
            self._toggle_slots[btn_name] = new_slot
            btn.toggled.connect(new_slot)

    # ------------------------------------------------------------------
    # NAVTEX filter wiring
    # ------------------------------------------------------------------

    def _wire_navtex_filters(self, screen) -> None:
        """Wire NAVTEX NAVMSG checkboxes and NAVSTN field to TNC."""
        # NAVMSG checkboxes — stateChanged
        msg_checks = getattr(screen, "_msg_checks", None)
        if msg_checks is not None:
            for letter, cb in msg_checks.items():
                try:
                    cb.stateChanged.disconnect(self._on_navtex_navmsg_changed)
                except (RuntimeError, TypeError):
                    pass
                cb.stateChanged.connect(self._on_navtex_navmsg_changed)

        # NAVSTN field — editingFinished
        le_navstn = getattr(screen, "le_navstn", None)
        if le_navstn is not None:
            try:
                le_navstn.editingFinished.disconnect(
                    self._on_navtex_navstn_changed
                )
            except (RuntimeError, TypeError):
                pass
            le_navstn.editingFinished.connect(
                self._on_navtex_navstn_changed
            )

    def _on_navtex_navmsg_changed(self) -> None:
        """Any NAVMSG checkbox changed — rebuild filter and send NM frame."""
        if not self._serial.is_connected or not self._serial.is_host_mode:
            return
        screen = self._opmode_stack.currentWidget()
        if not hasattr(screen, "get_navmsg_filter"):
            return
        filter_str = screen.get_navmsg_filter()
        from pk232py.modes.navtex import NAVTEXMode
        frame = NAVTEXMode.navmsg_frame(filter_str)
        self._serial.send_command(frame[2:4], frame[4:-1])
        mode = self._modes.current_mode
        if hasattr(mode, "navmsg"):
            mode.navmsg = filter_str
        self._log_monitor(f"[PARAM] NAVMSG → {filter_str}")

    def _on_navtex_navstn_changed(self) -> None:
        """NAVSTN field editingFinished — send NS frame."""
        if not self._serial.is_connected or not self._serial.is_host_mode:
            return
        screen = self._opmode_stack.currentWidget()
        if not hasattr(screen, "get_navstn_filter"):
            return
        filter_str = screen.get_navstn_filter()
        from pk232py.modes.navtex import NAVTEXMode
        frame = NAVTEXMode.navstn_frame(filter_str)
        self._serial.send_command(frame[2:4], frame[4:-1])
        mode = self._modes.current_mode
        if hasattr(mode, "navstn"):
            mode.navstn = filter_str
        self._log_monitor(f"[PARAM] NAVSTN → {filter_str}")

    def _on_screen_send(self, active: bool) -> None:
        """Called when the SEND button on the active screen is toggled.

        active=True:
          1. Send XMIT command (XM) — TNC keys PTT and starts DIDDLE.
          2. Send any text already in TX window.
          3. Wire tx_input.textChanged so every new character is sent
             immediately as a data frame.

        active=False:
          1. Warn if unsent text remains in TX window.
          2. Disconnect textChanged.
          3. Send RCVE command (RC) — TNC returns to receive.
        """
        if not self._serial.is_connected or not self._serial.is_host_mode:
            return

        tx = self._tx_input
        if tx is None:
            return

        from pk232py.comm.frame import build_command

        if active:
            # 1. Send XMIT — TNC keys PTT and starts DIDDLE
            xmit = build_command(b'XM')
            self._serial.send_command(xmit[2:4], xmit[4:-1])
            self._log_monitor("[TX] XMIT — PTT ON, DIDDLE started")

            # 2. Send any text already in TX window
            text = tx.toPlainText().strip()
            if text:
                self._send_rtty_text(text)
                tx.blockSignals(True)
                tx.clear()
                tx.blockSignals(False)

            # 3. Wire live-TX: every new character goes out immediately
            try:
                tx.textChanged.disconnect(self._on_rtty_text_changed)
            except (RuntimeError, TypeError):
                pass
            tx.textChanged.connect(self._on_rtty_text_changed)

        else:
            # 1. Warn if unsent text remains
            pending = tx.toPlainText().strip()
            if pending:
                rx = self._rx_display
                rx.moveCursor(rx.textCursor().MoveOperation.End)
                rx.insertPlainText("\n*** Still text to transmit! ***\n")

            # 2. Disconnect live-TX
            try:
                tx.textChanged.disconnect(self._on_rtty_text_changed)
            except (RuntimeError, TypeError):
                pass

            # 3. Send RCVE — TNC switches back to receive
            rcve = build_command(b'RC')
            self._serial.send_command(rcve[2:4], rcve[4:-1])
            self._log_monitor("[TX] RCVE — PTT OFF, back to receive")

    def _on_screen_receive(self, active: bool) -> None:
        """Called when the RECEIVE button on the active screen is toggled.

        active=True:  send RECEIVE command to TNC for the current mode.
        active=False: return TNC to standby for the current mode.

        Each mode has a different receive-activation mnemonic:
          Baudot/ASCII RTTY  — RX is always on; no explicit command needed.
          AMTOR              — receive handled by ALIST / FEC buttons.
          Morse              — RX is always on; no explicit command needed.
          PACTOR             — receive via PTLIST (btn_ptlist on screen).
        For modes where no action is needed, the call is a graceful no-op.
        """
        if not self._serial.is_connected or not self._serial.is_host_mode:
            return

        mode = self._modes.current_mode
        if mode is None:
            return

        mode_name = mode.name

        if active:
            # Mode-specific receive activation
            if mode_name in ("Baudot RTTY", "ASCII RTTY", "CW / Morse"):
                # These modes receive continuously — no command needed.
                # The button is purely visual feedback for the operator.
                logger.debug("RECEIVE: %s — continuous RX, no TNC command",
                             mode_name)

            elif mode_name == "NAVTEX":
                # NAVTEX receives automatically — no command needed.
                logger.debug("RECEIVE: NAVTEX — auto RX")

            else:
                # Unknown mode — log and do nothing.
                logger.debug("RECEIVE: %s — no specific receive command",
                             mode_name)
        else:
            # RECEIVE toggled OFF — no explicit TNC command for most modes.
            logger.debug("RECEIVE OFF: %s", mode_name)

    def _on_mode_data_received(self, data: bytes) -> None:
        """Route decoded TNC data to the correct display widget.

        Host Mode (stack index 0): active opmode screen's rx_display.
        Verbose Mode (stack index 1): verbose terminal _vt_display.
        """
        try:
            text = data.decode("ascii", errors="replace")
        except Exception:
            text = repr(data)

        if self._stack.currentIndex() == 0:
            # Host Mode: write to active opmode screen's rx_display
            self._log_terminal(text)
        else:
            # Verbose Mode: show decoded data in verbose terminal
            self._vt_append(text, color="#88ccff")

        # Monitor panel (always, if visible)
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
    # Slots -- parameter dialogs (placeholders)
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

 # Row 1: Hardware signals 
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

 # Row 2: Program/TNC status 
        self._set_sig(self._ssl_host, self._serial.is_host_mode)
        # PTT and CON are updated via frame_received -- no polling needed
        # (see _on_frame_received for PTT/CON logic)

    def _poll_opmode(self) -> None:
        """Send OPMODE query to TNC keeps monitor alive with responses."""
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
        # Opmode screens: apply font + colors to all screens' RX and TX widgets
        for screen in self._opmode_screens.values():
            if hasattr(screen, "rx_display"):
                screen.rx_display.setFont(font)
                screen.rx_display.setStyleSheet(style_rx)
            if hasattr(screen, "tx_input"):
                screen.tx_input.setFont(font)
                screen.tx_input.setStyleSheet(style_tx)
                # Block cursor: width = one average character
                char_w = screen.tx_input.fontMetrics().averageCharWidth()
                screen.tx_input.setCursorWidth(char_w)
        # Verbose terminal view
        self._vt_display.setFont(font)
        self._vt_display.setStyleSheet(style_vt)
        self._vt_input.setFont(font)
        self._vt_input.setStyleSheet(
            f"background-color:{a.bg_color}; "
            f"color:{a.fg_color}; border:none;"
        )
        # Block cursor on verbose terminal input
        char_w_vt = self._vt_input.fontMetrics().averageCharWidth()
        self._vt_input.setCursorWidth(char_w_vt)
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
    # Slots -- incoming frames (monitor only -- dispatch via ModeManager)
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
                # OPMODE response -- show in status bar
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

        # Monitor logging -- all modes
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
                    f" {txt}" if txt else ""
                )
            # Raw/Hex: handled via _on_raw_data_received

        # RX_DATA / RX_MONITOR / ECHO are routed to the active
        # screen's rx_display via the mode's on_data_received callback
        # (_wire_mode_callbacks → _on_mode_data_received).
        # Writing here as well would produce duplicate output.

    def _on_status_message(self, msg: str) -> None:
        """Route status messages: errors popup, info status bar."""
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
        self._update_serial_signals()
        if self._act_serial_status.isChecked():
            if connected:
                self._serial_sig_timer.start()
            else:
                self._serial_sig_timer.stop()

        if connected:
            self._sb_port.setText(f"Port: {self._config.port_name}")
            self._sb_baud.setText(f"Baud: {self._config.baudrate}")
            # Connected but not yet in any mode → verbose indicator
            self._set_mode_indicator("verbose")
        else:
            self._sb_port.setText("Port: ---")
            self._sb_baud.setText("Baud: ---")
            self._sb_mode.setText("Mode: OFFLINE")
            self._mode_combo.setEnabled(False)
            self._set_mode_indicator("offline")

    def _update_host_mode_ui(self, active: bool) -> None:
        """Switch view and enable mode selector when Host Mode is active."""
        self._mode_combo.setEnabled(active or self._serial.is_connected)
        if active:
            self._sb_mode.setText("Mode: HOST")
            self._set_mode_indicator("host")
            self._stack.setCurrentIndex(0)
            self._wire_mode_callbacks()
        else:
            self._sb_mode.setText("Mode: VERBOSE")
            self._set_mode_indicator("verbose")
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
        """Append text to terminal without forced newline per call.
 
        QTextEdit.append() adds a newline after each call -- wrong for
        streaming RTTY where each character arrives as a separate frame.
        insertPlainText() appends directly at cursor position.
        \r is stripped -- only \n causes a real line break.
        """
        # Strip \r -- QTextEdit handles \n for line breaks
        text = text.replace('\r', '')
        if not text:
            return
        cursor = self._terminal.textCursor()
        from PyQt6.QtGui import QTextCursor
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._terminal.setTextCursor(cursor)
        self._terminal.insertPlainText(text)
        self._terminal.ensureCursorVisible()

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
                    lines.append(f"{i:04X} {hex_part:<48} {asc_part}")
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
                    f"{prefix}{i:04X} {hex_part:<48} {asc_part}"
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
        """Intercept keys in verbose terminal input.

        Note: Opmode screens (Baudot, AMTOR, Morse etc.) manage their own
        TX input Enter-key handling via their own eventFilter.  MainWindow
        only needs to handle the verbose terminal input (_vt_input) here.
        """
        if event.type() == QEvent.Type.KeyPress:
            if obj is self._vt_input:
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
                # Ctrl+C -> $03: TNC back to COMMAND mode
                if key == Qt.Key.Key_C and (mods & ctrl):
                    self._vt_send_raw(b"\x03", echo="[CTRL-C]\n",
                                      color="#ff9900")
                    return True
                # Ctrl+Z -> $1A: PACTOR OVER / PTOVER char
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
        """Display raw bytes received from TNC in verbose terminal.

        TNC responses are shown in white. A blank line is inserted
        before each cmd: prompt to visually separate command/response pairs.
        """
        try:
            text = data.decode('ascii', errors='replace')
        except Exception:
            text = repr(data)
        # Insert blank line before cmd: to separate response blocks
        text = text.replace('cmd:', '\ncmd:')
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
        Receive-only screens (NAVTEX, Signal, FAX) have no TX input;
        _tx_input returns None for those — the call is a no-op.
        """
        tx = self._tx_input   # property: None for receive-only screens
        if tx is None:
            return
        text = tx.toPlainText().strip()
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
                frame_bytes = mode.data_frame(line)
                self._serial.send_data(
                    frame_bytes[2:-1],
                    channel=0,
                )
            else:
                self._serial.send_data(
                    line.encode('ascii', errors='replace')
                )

        tx.clear()

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


# === E:\PK232\pk232py_repo\src\pk232py\ui\tnc_config_dialog.py ===
# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  â€”  GPL v2
"""TNC configuration dialog.

Allows selection of:
  - Serial port (COM1, /dev/ttyUSB0, â€¦)
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