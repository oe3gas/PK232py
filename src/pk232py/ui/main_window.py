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
from PyQt6.QtGui import QAction, QActionGroup, QFont, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QPushButton, QSplitter, QStackedWidget, QTextEdit, QToolBar,
    QVBoxLayout, QWidget, QWidgetAction,
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
from .screens.pactor_screen  import PactorScreen
from .screens.packet_screen  import HFPacketScreen, VHFPacketScreen
from .screens.tx_controller import TxController

logger = logging.getLogger(__name__)

APP_TITLE = "PK232PY"

# CW/Morse: the TNC controls WPM timing, so the TxController is ACK-paced and
# its inter-character timer is only a buffer-overflow safety net (not tempo
# control). Adjustable on hardware test: flow stalls → lower; overflow → raise.
_MORSE_TXCTRL_MS = 50

# AMTOR: the TNC controls the 100 Bd ARQ timing (3-char blocks), so the
# TxController is ACK-paced just like Morse; this timer is only a
# buffer-overflow safety net. Adjust down if TX flow stutters on hardware.
_AMTOR_TXCTRL_MS = 50


class MainWindow(QMainWindow):
    """Main application window.

    Coordinates:
      - SerialManager  (TNC serial connection)
      - ModeManager    (operating mode switching + frame dispatch)
      - TncConfigDialog (connection configuration)
      - Menu bar, toolbar, status bar
    """

    # Thread-safe verbose-terminal append: emit from any thread, handled in GUI thread.
    _vt_append_signal = pyqtSignal(str, str)  # (text, color)

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
        # TX state flag — independent of Qt button states.
        self._send_active: bool = False
        # FAX reception gate — applies to BOTH auto-sync and LOCK. Set False by
        # the Stop button to freeze the current image; re-enabled by LOCK or
        # Clear. When False, _on_fax_data_received() drops incoming rows.
        self._fax_receiving: bool = True
        # Shared TX/RX content preserved across mode switches.
        self._shared_tx_text: str = ""
        self._shared_rx_doc  = None  # QTextDocument or None
        # TxController — rate-limited TX with DATA_ACK tracking (character-ACK modes).
        # Proven in baudot_tx_test.py (2026-05-02).
        # Handles: char buffering, rate-limited send, colour_at, EOT marker.
        self._tx_ctrl = TxController(self)
        self._tx_ctrl.set_mspeed(50)   # default 50 Baud — updated from config
        # Re-entry guard for eventFilter.
        self._in_event_filter: bool = False
        # Flag: True when user explicitly requested Host Mode exit
        # (Leave Host Mode button/menu). Ensures the verbose
        # terminal is shown even if an opmode screen is still active.
        # PACTOR temporarily exits Host Mode but keeps its screen —
        # it does NOT set this flag.
        self._exiting_host_mode_by_user: bool = False

        # Packet monitor frame buffer — used for APRS re-decode on toggle.
        # Each entry is (utc_timestamp_str, raw_frame_text).
        # When APRS toggle fires, _packet_rx_redraw() re-renders all entries.
        self._packet_raw_frames: list[tuple[str, str]] = []
        self._packet_aprs_active: bool = False

        # Apply the saved theme's palette + style BEFORE building any widgets,
        # so every widget inherits the right palette at construction time.
        # (A palette set afterwards does not reliably re-style already-built
        # children, and a style switch mid-life is more disruptive.) Capture the
        # native style name first so the Air theme can restore it.
        self._system_style_name = QApplication.instance().style().objectName()
        self._apply_palette()

        self._build_ui()
        self._connect_signals()
        self._update_connection_ui(False)
        # Install application-wide event filter.
        # This makes MainWindow.eventFilter() see ALL key events
        # in the application, regardless of which widget has focus.
        # Needed because NoFocus buttons return focus to
        # QStackedWidget (not MainWindow), so a widget-level filter
        # on MainWindow alone would miss those key events.
        QApplication.instance().installEventFilter(self)
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
        self._act_params_pactor = None
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
            if label == "PACTOR...":
                self._act_params_pactor = act

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

        appear_menu.addSeparator()

        # Theme presets — checkable + mutually exclusive (QActionGroup).
        # The active theme shows a check mark; clicking one applies it live and
        # persists it. See _on_theme_selected() / _sync_theme_checks().
        from pk232py.ui.themes import THEMES, THEME_ORDER
        # Non-clickable bold header above the theme list. A disabled QAction
        # cannot render bold text natively, so we embed a styled QLabel via a
        # QWidgetAction. palette(text) keeps it readable under every theme.
        theme_header_lbl = QLabel("Select Theme")
        # Neutral mid-grey: readable on any menu background (dark or light) and
        # independent of the app palette, which a Qt menu does not necessarily
        # follow. palette(text) was invisible on the dark menu chrome.
        theme_header_lbl.setStyleSheet(
            "font-weight: bold; padding: 4px 20px; color: #808080;"
        )
        theme_header_lbl.setEnabled(False)
        theme_header = QWidgetAction(self)
        theme_header.setDefaultWidget(theme_header_lbl)
        appear_menu.addAction(theme_header)
        appear_menu.addSeparator()

        self._theme_group = QActionGroup(self)
        # ExclusiveOptional: exactly one preset checked, OR none (when the user
        # has a "custom" appearance that matches no preset).
        self._theme_group.setExclusionPolicy(
            QActionGroup.ExclusionPolicy.ExclusiveOptional
        )
        self._theme_actions: dict[str, QAction] = {}
        for key in THEME_ORDER:
            theme = THEMES[key]
            act = QAction(theme.name, self, checkable=True)
            act.setStatusTip(f"Apply the {theme.name} appearance theme")
            act.triggered.connect(lambda _checked, k=key: self._on_theme_selected(k))
            self._theme_group.addAction(act)
            appear_menu.addAction(act)
            self._theme_actions[key] = act
        self._sync_theme_checks()

        cfg_menu.addSeparator()

        act_about = QAction("&About PK232PY...", self)
        act_about.triggered.connect(self._on_about)
        cfg_menu.addAction(act_about)

        # ── Help menu ─────────────────────────────────────────────────────────
        help_menu = mb.addMenu("&Help")

        # Menu item always opens the top-level index (Contents). F1 is handled
        # separately (context-sensitive — see _on_f1) so the menu and the key
        # can differ; hence NO setShortcut("F1") on this action.
        act_help_contents = QAction("&Contents", self)
        act_help_contents.setStatusTip("Open the PK232PY help (table of contents)")
        act_help_contents.triggered.connect(self._on_help_contents)
        help_menu.addAction(act_help_contents)

        help_menu.addSeparator()

        # Reuse the existing About handler — same dialog as Configure → About.
        act_help_about = QAction("&About PK232PY...", self)
        act_help_about.triggered.connect(self._on_about)
        help_menu.addAction(act_help_about)

        # F1 = context help for the active opmode screen (NOT the menu's index).
        self._f1_shortcut = QShortcut(QKeySequence(Qt.Key.Key_F1), self)
        self._f1_shortcut.activated.connect(self._on_f1)

    def _on_help_contents(self) -> None:
        """Open the help viewer at the top-level index page (Help → Contents)."""
        from pk232py.ui.screens.help_viewer import show_help
        show_help("index", parent=self)

    def _on_f1(self) -> None:
        """F1 → context help for the active opmode screen.

        Falls back to the top-level index when no mode is active (e.g. before
        connecting, while the verbose terminal / default screen is shown). Each
        opmode screen carries its topic in a ``HELP_TOPIC`` class attribute —
        the same key its own ``?`` button uses.
        """
        from pk232py.ui.screens.help_viewer import show_help
        if self._modes.current_mode is None:
            topic = "index"
        else:
            screen = self._opmode_stack.currentWidget()
            topic = getattr(screen, "HELP_TOPIC", "index")
        show_help(topic, parent=self)

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

        # TNC Firmware version label — populated in _on_verbose_mode_ready()
        tb.addSeparator()
        tb.addWidget(QLabel(" TNC-Firmware: "))
        self._lbl_firmware = QLabel("—")
        self._lbl_firmware.setFont(QFont("Courier New", 9))
        self._lbl_firmware.setStyleSheet("color: #88aacc;")
        self._lbl_firmware.setToolTip(
            "TNC firmware version from boot banner"
        )
        tb.addWidget(self._lbl_firmware)

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
            "PACTOR":        PactorScreen(),
            "HF Packet":     HFPacketScreen(),
            "VHF Packet":    VHFPacketScreen(),
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

        # Save TX text + RX document from outgoing screen
        old = self._opmode_stack.currentWidget()
        if old is not None and old is not screen:
            if hasattr(old, 'tx_input') and old.tx_input:
                self._shared_tx_text = old.tx_input.toPlainText()
            if hasattr(old, 'rx_display') and old.rx_display:
                self._shared_rx_doc = old.rx_display.document()

        self._opmode_stack.setCurrentWidget(screen)
        logger.debug("Opmode screen switched to: %s", name)

        # Restore TX text + RX document into incoming screen
        if hasattr(screen, 'tx_input') and screen.tx_input:
            if self._shared_tx_text:
                screen.tx_input.setPlainText(self._shared_tx_text)
        if hasattr(screen, 'rx_display') and screen.rx_display:
            if self._shared_rx_doc is not None:
                screen.rx_display.setDocument(self._shared_rx_doc)

        # For RTTY/Morse screens: set RECEIVE button green on entry
        # because the TNC starts in receive mode.
        _rx_modes = ("Baudot RTTY", "ASCII RTTY", "CW / Morse")
        if name in _rx_modes and hasattr(screen, "btn_receive"):
            screen.btn_receive.blockSignals(True)
            screen.btn_receive.setChecked(True)
            screen.btn_receive.blockSignals(False)
            # Trigger visual update directly (signals blocked above)
            screen._on_receive_toggled(True)

        # For Packet screens: populate MYCALL label from AppConfig.
        if name in ("HF Packet", "VHF Packet") and hasattr(screen, "set_mycall"):
            mycall = getattr(self._app_config.hf_packet, "mycall", "")
            if not mycall or mycall.upper() == "NOCALL":
                mycall = ""
            screen.set_mycall(mycall)

        # For PACTOR: populate lbl_myptcall from AppConfig if set.
        if name == "PACTOR" and hasattr(screen, "lbl_myptcall"):
            myptcall = getattr(self._app_config.pactor, "myptcall", "")
            if myptcall and myptcall.upper() != "NOCALL":
                screen.lbl_myptcall.setText(myptcall.upper())

        # For AMTOR: populate lbl_myselcal / lbl_myaltcal from AppConfig if set.
        if name in ("AMTOR ARQ", "AMTOR FEC"):
            amtor_cfg = self._app_config.amtor
            if hasattr(screen, "lbl_myselcal") and amtor_cfg.myselcal:
                screen.lbl_myselcal.setText(amtor_cfg.myselcal.upper())
            if hasattr(screen, "lbl_myaltcal") and amtor_cfg.myaltcal:
                screen.lbl_myaltcal.setText(amtor_cfg.myaltcal.upper())

        # For Morse: load MSPEED / MWEIGHT / MID from AppConfig into the
        # SpinBoxes so the screen reflects the saved config, not the
        # hard-coded widget defaults. blockSignals avoids re-firing the
        # change handlers (which would re-send to the TNC and re-save config).
        if name == "CW / Morse":
            b = self._app_config.baudot
            for attr, val in (
                ("sb_mspeed",  b.mspeed),
                ("sb_mweight", b.mweight),
                ("sb_mid",     b.mid),
            ):
                sb = getattr(screen, attr, None)
                if sb is not None:
                    sb.blockSignals(True)
                    sb.setValue(int(val))
                    sb.blockSignals(False)

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
        self._sb_port.setToolTip("Serial port connected to the TNC")
        sb.addPermanentWidget(self._sb_port)

        self._sb_baud = QLabel("Baud: ---")
        self._sb_baud.setMinimumWidth(90)
        self._sb_baud.setToolTip("Serial port baud rate")
        sb.addPermanentWidget(self._sb_baud)

        self._sb_mode = QLabel("Mode: OFFLINE")
        self._sb_mode.setMinimumWidth(150)
        self._sb_mode.setToolTip(
            "Current TNC connection mode:\n"
            "OFFLINE — not connected\n"
            "VERBOSE — connected, command terminal mode\n"
            "HOST MODE — connected, full program control"
        )
        sb.addPermanentWidget(self._sb_mode)

        self._sb_time = QLabel("UTC: --:--:--")
        self._sb_time.setMinimumWidth(110)
        self._sb_time.setToolTip("Current UTC time")
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

        # Thread-safe VT append — background threads emit this signal
        self._vt_append_signal.connect(self._vt_append)

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

        # Parse firmware version from TNC banner and show in toolbar.
        # Banner example: "AEA PK-232M ...\nRelease 01.AUG.91"
        # We extract the 'Release xx.MON.YY' token.
        _banner = getattr(self._serial, 'tnc_banner', '')
        _fw = "unknown"
        for _line in _banner.splitlines():
            _line = _line.strip()
            if _line.lower().startswith("release"):
                _fw = _line   # e.g. "Release 01.AUG.91"
                break
        if hasattr(self, '_lbl_firmware'):
            self._lbl_firmware.setText(_fw)
        self._stack.setCurrentIndex(1)
        self._vt_input.setFocus()
        self._vt_display.clear()
        self._vt_append("[SYS] TNC ready in verbose mode\n")
        # Enable mode selector
        self._mode_combo.setEnabled(True)

        # Disable 'PACTOR' entry when TNC has no PACTOR option.
        # QStandardItemModel.item(idx).setEnabled(False) greys out
        # the entry so the user sees it is unavailable.
        _has_pactor = getattr(self._serial, 'has_pactor', True)

        # Disable PACTOR opmode in ComboBox
        _cb_model = self._mode_combo.model()
        for _i in range(self._mode_combo.count()):
            if self._mode_combo.itemText(_i) == "PACTOR":
                _cb_item = _cb_model.item(_i)
                _cb_item.setEnabled(_has_pactor)
                if not _has_pactor:
                    _cb_item.setToolTip(
                        "PACTOR nicht verf\u00fcgbar \u2014 "
                        "diese TNC-Firmware hat keine PACTOR-Option"
                    )
                else:
                    _cb_item.setToolTip("")
                break

        # Disable Parameters → PACTOR... menu entry
        if self._act_params_pactor is not None:
            self._act_params_pactor.setEnabled(_has_pactor)
            if not _has_pactor:
                self._act_params_pactor.setToolTip(
                    "PACTOR nicht verf\u00fcgbar \u2014 "
                    "diese TNC-Firmware hat keine PACTOR-Option"
                )
                self._log_monitor(
                    "[SYS] TNC has no PACTOR \u2014 "
                    "PACTOR mode + Parameters menu disabled"
                )
            else:
                self._act_params_pactor.setToolTip("")

        # Upload parameters unless Fast Initialization is selected.
        # Fast Init skips the parameter upload and goes directly to
        # Host Mode (or verbose terminal), trusting the TNC's stored
        # values from battery-backed RAM.
        import threading
        connect_mode = self._connect_mode
        fast_init    = self._config.fast_init

        # Thread-safe wrapper: background thread emits signal → GUI thread calls _vt_append
        def _vt(text: str, color: str = "#cccccc") -> None:
            self._vt_append_signal.emit(text, color)

        def _upload():
            if fast_init:
                _vt("[SYS] Fast Init — parameter upload skipped\n")
                self._log_monitor("[SYS] Fast Init active — no parameter upload")
                if connect_mode == "host":
                    _vt("[SYS] Entering Host Mode...\n")
                    self._serial.enter_host_mode()
                else:
                    _vt("[SYS] Verbose terminal ready (fast init)\n")
                return
            _vt("[SYS] Uploading parameters...\n")
            uploader = ParamsUploader(
                self._serial,
                self._app_config,
                echo_callback=_vt,
            )
            n = uploader.upload()
            self._log_monitor(f"[SYS] {n} parameters uploaded")
            if connect_mode == "host":
                _vt(f"[SYS] {n} parameters uploaded -- entering Host Mode...\n")
                self._serial.enter_host_mode()
            else:
                _vt(f"[SYS] {n} parameters uploaded -- verbose terminal ready\n")
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
            # Signal _update_host_mode_ui that this is a genuine
            # user-initiated exit — always show verbose terminal.
            self._exiting_host_mode_by_user = True
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

        # T51: leaving VHF Packet → restore the HF 300 Bd modem (VHF OFF) so the
        # next mode is not stuck on the 1200 Bd Bell-202 modem. current_mode_name
        # is still the OUTGOING mode here (set_mode deactivates it below). Only
        # meaningful in Host Mode on a live link.
        if (self._modes.current_mode_name == "VHF Packet"
                and self._serial.is_connected and self._serial.is_host_mode):
            from pk232py.modes.packet_vhf import VHFPacketMode
            vh_off = VHFPacketMode.vhf_off_frame()
            self._serial.send_command(vh_off[2:4], vh_off[4:-1])
            self._log_monitor("[PACKET] Leaving VHF Packet — VHF OFF (VH N)")

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

        from .screens.packet_screen import PacketBaseScreen
        _is_packet = isinstance(
            self._opmode_stack.currentWidget(), PacketBaseScreen
        )
        # When leaving packet mode: discard buffer and APRS state.
        # Fresh start next time packet mode is entered.
        if not _is_packet:
            self._packet_raw_frames.clear()
            self._packet_aprs_active = False

        # ARQ / general received data
        if hasattr(mode, "on_data_received"):
            if _is_packet:
                # Packet mode: callback receives (channel, data)
                mode.on_data_received = self._on_packet_data_received
            else:
                mode.on_data_received = self._on_mode_data_received

        # Monitored / unproto frames ($3F)
        if hasattr(mode, "on_monitor_frame"):
            if _is_packet:
                mode.on_monitor_frame = self._on_packet_monitor_frame
            else:
                mode.on_monitor_frame = self._on_mode_data_received

        # MHEARD list entries (polled line-by-line via Refresh, T41)
        if hasattr(mode, "on_mheard_entry"):
            mode.on_mheard_entry = self._on_mheard_entry_received

        # PACTOR FEC / Unproto data ($3F) — same handler as ARQ data
        if hasattr(mode, "on_fec_received"):
            mode.on_fec_received = self._on_mode_data_received

        # EAS (Echo As Sent) — Morse colours the TX window at the *actual*
        # send moment ($2F echo, WPM-paced), not at buffer-accept time
        # ($5F DATA_ACK). The TxController must be in EAS mode for Morse and
        # OUT of it for every other mode — set this unconditionally on every
        # mode switch, even for modes (e.g. AMTOR) that have no echo callback,
        # otherwise on_data_ack() would stop colouring after a Morse session.
        self._tx_ctrl.set_eas_mode(mode.name == "CW / Morse")

        # Echo ($2F)
        if hasattr(mode, "on_echo_received"):
            if mode.name == "CW / Morse":
                # Each $2F byte = one character actually keyed on the air.
                # Route it to TxController.on_echo_char() so the TX window
                # colours in step with the audible keying. (With WORDOUT ON
                # the TNC may batch a whole word into one frame — hence one
                # on_echo_char() call per byte received.)
                def _on_morse_echo(data: bytes) -> None:
                    # One on_echo_char() per echoed BYTE. NOTE: '\r\n' is sent
                    # as two wire bytes but the TNC echoes NO $2F byte for it
                    # (newline has no Morse symbol), so it is excluded from
                    # echo-pacing in TxController (_is_unkeyed) — see tx_controller.
                    for _ in data:
                        self._tx_ctrl.on_echo_char()
                mode.on_echo_received = _on_morse_echo
            else:
                mode.on_echo_received = self._on_mode_echo_received

        # Link messages → log + screen status label
        if hasattr(mode, "on_link_message"):
            screen = self._opmode_screens.get(mode.name)
            if screen is not None and hasattr(screen, "_set_status"):
                mode.on_link_message = self._make_link_handler(screen)
            else:
                mode.on_link_message = self._on_mode_link_message

        # DATA_ACK ($5F) — Packet: flow control; RTTY: colour tracking
        if hasattr(mode, 'on_data_ack'):
            if _is_packet:
                mode.on_data_ack = self._on_packet_data_ack
            else:
                mode.on_data_ack = self._on_rtty_data_ack

        # Packet TX: wire Enter key in tx_input to DATA frame send
        if _is_packet:
            screen = self._opmode_stack.currentWidget()
            if hasattr(screen, 'tx_input'):
                try:
                    screen.tx_input.textChanged.disconnect(
                        self._on_packet_tx_enter
                    )
                except (RuntimeError, TypeError):
                    pass
                # Use keyPressEvent override instead of textChanged
                # — see _on_packet_tx_enter for the Enter detection
                screen.tx_input._packet_send_slot = self._on_packet_tx_enter

        # FAX: wire pixel data callback
        if mode.name == "FAX" and hasattr(mode, 'on_data_received'):
            mode.on_data_received = self._on_fax_data_received

        # Wire screen buttons (SEND, RECEIVE) to MainWindow slots
        self._wire_screen_buttons()

        logger.debug("Mode callbacks wired for: %s", mode.name)

    def _make_link_handler(self, screen):
        """Return a link-message handler that updates both the
        monitor log and the screen's _set_status label.

        Maps TNC link-message text to the status keys used by
        AmtorScreen and PactorScreen.
        """
        def handler(*args) -> None:
            # Accept both 1-arg (msg) and 2-arg (channel, msg) calls.
            # HFPacketMode calls on_link_message(ch, text); AMTOR/PACTOR
            # call on_link_message(text).
            msg = args[-1] if args else ""
            # 1. General log / monitor
            self._on_mode_link_message(msg)
            # 2. Update screen status label
            m = msg.lower()
            if "connected" in m and "disconnect" not in m:
                status = "CONNECTED"
                # AMTOR ARQ: CONNECTED means we are ISS (Information Sending
                # Station). There is no SEND button / XM frame for AMTOR, so the
                # ARQ link coming up is what starts the TxController — chars
                # already queued in TxInputWidget begin flowing to the TNC.
                # mode.name is always "AMTOR ARQ" here (ModeManager never
                # produces "AMTOR FEC"; FEC is a screen sub-state).
                mode = self._modes.current_mode
                if mode is not None and mode.name == "AMTOR ARQ":
                    self._tx_ctrl.on_send_start()
                    self._log_monitor("[AMTOR] CONNECTED → TxController started")
            elif "disconnect" in m:
                # PactorScreen uses "DISCONN"; PacketBaseScreen uses "DISCONNECTED"
                from .screens.packet_screen import PacketBaseScreen
                status = "DISCONNECTED" if isinstance(screen, PacketBaseScreen) \
                         else "DISCONN"
                # AMTOR: link gone — stop the controller and discard queued chars.
                mode = self._modes.current_mode
                if mode is not None and mode.name == "AMTOR ARQ":
                    self._tx_ctrl.on_send_stop()
                    self._log_monitor("[AMTOR] DISCONNECTED → TxController stopped")
            elif "calling" in m or "connect request" in m:
                status = "CALLING"
            elif "fec" in m:
                status = "FEC TX"
            else:
                status = "STBY"
            # Packet only: gate Connect/Disconnect by link state so a second CO
            # cannot be sent while connected or calling. Guarded by hasattr so
            # AMTOR/PACTOR screens (no set_link_state) are unaffected.
            if hasattr(screen, "set_link_state"):
                if status in ("CONNECTED", "CALLING"):
                    screen.set_link_state(status.lower())
                elif status == "DISCONNECTED":
                    screen.set_link_state("disconnected")
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

        # Packet mode buttons (HF + VHF Packet)
        self._wire_packet_buttons(screen)

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

        # Baudot: Switch figs (FIGS 0x1B) and Switch char (LTRS 0x1F)
        # These inject Baudot shift-control bytes directly into TX stream.
        for _btn_name, _byte in (
            ("btn_figs",  "\x1b"),   # FIGS — switch to figures/digits
            ("btn_chars", "\x1f"),   # LTRS — switch back to letters
        ):
            _btn = getattr(screen, _btn_name, None)
            if _btn is not None:
                try:
                    _btn.clicked.disconnect()
                except (RuntimeError, TypeError):
                    pass
                _btn.clicked.connect(
                    (lambda _b=_byte: lambda: self._on_rtty_char_ready(_b))()
                )

        # Baudot: Switch figs / Switch char — direct TNC send, not buffered.
        # FIGS (0x1B) and LTRS (0x1F) are Baudot shift control bytes sent
        # immediately to the TNC regardless of SEND/RECEIVE state.
        for _btn_name, _byte in (
            ("btn_figs",  b"\x1b"),   # FIGS — switch TNC to figures/digits
            ("btn_chars", b"\x1f"),   # LTRS — switch TNC back to letters
        ):
            _btn = getattr(screen, _btn_name, None)
            if _btn is not None:
                try:
                    _btn.clicked.disconnect()
                except (RuntimeError, TypeError):
                    pass
                _btn.clicked.connect(
                    (lambda _b=_byte: lambda: (
                        self._serial.send_data(_b, channel=0)
                        if self._serial.is_connected
                           and self._serial.is_host_mode
                        else None
                    ))()
                )

        # Phase 3 — identity fields, spinboxes, toggles, NAVTEX filters
        self._wire_identity_fields(screen)
        self._wire_morse_params(screen)
        self._wire_toggle_buttons(screen)
        self._wire_navtex_filters(screen)
        self._wire_fax_buttons(screen)

        # TX wiring. TxController-driven modes (Baudot/ASCII/Morse) feed the
        # controller via TxInputWidget.char_typed; legacy modes (AMTOR until 2b)
        # use the screen's char_ready signal. Compute both facts once.
        mode = self._modes.current_mode
        is_rtty = self._is_txctrl_mode(mode)
        tx = getattr(screen, "tx_input", None)
        tx_has_char_typed = tx is not None and hasattr(tx, "char_typed")

        # char_ready: legacy signal — ONLY for screens without a TxInputWidget.
        # The "not tx_has_char_typed" guard prevents double-send: a
        # TxController-driven screen must never also feed the legacy
        # char_ready → _on_rtty_char_ready path.
        if hasattr(screen, "char_ready") and not tx_has_char_typed:
            try:
                screen.char_ready.disconnect(self._on_rtty_char_ready)
            except (RuntimeError, TypeError):
                pass
            screen.char_ready.connect(self._on_rtty_char_ready)

        # char_typed: TxInputWidget signal → TxController (Baudot/ASCII/Morse).
        if is_rtty and tx_has_char_typed:
            try:
                tx.char_typed.disconnect(self._tx_ctrl.on_char_typed)
            except (RuntimeError, TypeError):
                pass
            tx.char_typed.connect(self._tx_ctrl.on_char_typed)
            # Controller → screen: colour ACK'd chars + show in RX
            try:
                self._tx_ctrl.colour_char.disconnect()
            except (RuntimeError, TypeError):
                pass
            self._tx_ctrl.colour_char.connect(
                lambda idx, s, _tx=tx: _tx.colour_at(idx, s)
            )
            try:
                self._tx_ctrl.show_in_rx.disconnect()
            except (RuntimeError, TypeError):
                pass
            self._tx_ctrl.show_in_rx.connect(self._on_baudot_rx_char)
            try:
                self._tx_ctrl.send_to_tnc.disconnect()
            except (RuntimeError, TypeError):
                pass
            self._tx_ctrl.send_to_tnc.connect(self._on_baudot_send_char)
            try:
                self._tx_ctrl.eot_reached.disconnect()
            except (RuntimeError, TypeError):
                pass
            self._tx_ctrl.eot_reached.connect(self._on_baudot_eot)
            try:
                self._tx_ctrl.timed_send_reached.disconnect()
            except (RuntimeError, TypeError):
                pass
            self._tx_ctrl.timed_send_reached.connect(self._on_baudot_timed_send)
            try:
                self._tx_ctrl.status_msg.disconnect()
            except (RuntimeError, TypeError):
                pass
            self._tx_ctrl.status_msg.connect(
                lambda m: self.statusBar().showMessage(m, 3000)
            )
            try:
                self._tx_ctrl.warning.disconnect()
            except (RuntimeError, TypeError):
                pass
            self._tx_ctrl.warning.connect(self._on_baudot_warning)
            # Controller TX pacing.
            #   Baudot/ASCII: rate-limited to the configured Baud rate.
            #   Morse: TNC controls WPM; controller is ACK-paced, so the timer
            #          is only a buffer-overflow safety net (_MORSE_TXCTRL_MS).
            if mode.name == "CW / Morse":
                self._tx_ctrl.set_mspeed_ms(_MORSE_TXCTRL_MS)
            elif mode.name in ("AMTOR ARQ", "AMTOR FEC"):
                # AMTOR: TNC controls 100 Bd ARQ timing; controller is
                # ACK-paced. Small timer only as buffer-overflow safety net.
                self._tx_ctrl.set_mspeed_ms(_AMTOR_TXCTRL_MS)
            else:
                try:
                    mspeed = int(self._app_config.baudot.mspeed)
                    self._tx_ctrl.set_mspeed(mspeed)
                except Exception:
                    pass

        # Clear TX / Clear RX buttons
        for sig, slot in [
            ('clear_tx_req', self._on_clear_tx),
            ('clear_rx_req', self._on_clear_rx),
        ]:
            if hasattr(screen, sig):
                try:
                    getattr(screen, sig).disconnect(slot)
                except (RuntimeError, TypeError):
                    pass
                getattr(screen, sig).connect(slot)

        # Macro buttons — wire each button to insert macro text into TX
        if hasattr(screen, 'macro_buttons') and hasattr(screen, '_macro_store'):
            for i, btn in enumerate(screen.macro_buttons):
                try:
                    btn.clicked.disconnect()
                except (RuntimeError, TypeError):
                    pass
                # Capture index i by default arg
                btn.clicked.connect(
                    lambda checked=False, idx=i, s=screen: self._on_macro_clicked(idx, s)
                )

    def _is_txctrl_mode(self, mode) -> bool:
        """True for modes driven by TxController (char-ACK + EOT marker).

        These use TxInputWidget.char_typed → TxController.on_char_typed and the
        ACK-paced send path (colour tracking, [^D] EOT). AMTOR ARQ/FEC joined
        in package 2b — note the mode names are "AMTOR ARQ" / "AMTOR FEC"
        (ModeManager constants), never the ComboBox display name "AMTOR".
        """
        return mode is not None and mode.name in (
            "Baudot RTTY", "ASCII RTTY", "CW / Morse",
            "AMTOR ARQ", "AMTOR FEC",
        )

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

        mode = self._modes.current_mode
        is_rtty = self._is_txctrl_mode(mode)

        if active:
            self._send_active = True
            # Send XM — TNC keys PTT and starts DIDDLE
            xmit = build_command(b'XM')
            self._serial.send_command(xmit[2:4], xmit[4:-1])
            self._log_monitor("[TX] XMIT — PTT ON, DIDDLE started")
            # For TxController modes (Baudot/ASCII/Morse): on_send_start() is
            # called when XM ACK arrives via _on_frame_received →
            # _on_baudot_xm_ack. The controller then flushes unsent chars
            # (Baudot/ASCII rate-limited by Baud; Morse ACK-paced).
            # For other modes (AMTOR): flush via legacy 300ms timer.
            if not is_rtty:
                unsent_chars = tx.toPlainText()
                if unsent_chars:
                    def _flush_after_xm():
                        self._on_rtty_char_ready(unsent_chars)
                    QTimer.singleShot(300, _flush_after_xm)
            tx.setFocus()

        else:
            self._send_active = False
            # Baudot/ASCII: stop rate-limited send, update cycle anchors
            if is_rtty and hasattr(tx, "char_typed"):
                self._tx_ctrl.on_send_stop()
                # doc_offset must be the actual document position, not the
                # array index. tx.document().characterCount()-1 gives the
                # exact position where new chars will be inserted.
                doc_len = tx.document().characterCount() - 1
                tx.set_cycle_anchor(
                    doc_len,
                    self._tx_ctrl.cycle_start
                )
                if self._tx_ctrl.still_to_transmit():
                    # Show warning in status bar only — not in RX window.
                    # RX window spam with "Still text" on every RECEIVE
                    # press while rate-limited chars are queued is confusing.
                    self.statusBar().showMessage(
                        "⚠ TX buffer not empty — unsent chars remain", 4000
                    )
            # Send RC — PTT off, back to receive
            rcve = build_command(b'RC')
            self._serial.send_command(rcve[2:4], rcve[4:-1])
            self._log_monitor("[TX] RCVE — PTT OFF, back to receive")

    def _flush_tx_buffer(self, tx, chars: list) -> None:
        """Send buffered TX chars one at a time with event-loop yield.

        Each char is deleted from the front of tx_input, sent to the
        TNC via _on_rtty_char_ready(), then the next char is scheduled
        via QTimer.singleShot(0) so Qt repaints between deletions.
        This makes the TX window visibly shrink char by char.
        """
        if not chars:
            return
        if not self._serial.is_connected or not self._serial.is_host_mode:
            return
        # Check SEND is still active before sending each char
        screen = self._opmode_stack.currentWidget()
        if hasattr(screen, 'btn_send') and not screen.btn_send.isChecked():
            return  # SEND was cancelled — stop flushing
        ch = chars[0]
        remaining = chars[1:]
        from PyQt6.QtGui import QTextCursor
        tx.blockSignals(True)
        c = tx.textCursor()
        c.movePosition(QTextCursor.MoveOperation.Start)
        c.deleteChar()
        tx.setTextCursor(c)
        tx.blockSignals(False)
        self._on_rtty_char_ready(ch)
        if remaining:
            QTimer.singleShot(0, lambda: self._flush_tx_buffer(tx, remaining))

    def _on_macro_clicked(self, idx: int, screen) -> None:
        """Insert macro text into TX window when a macro button is clicked.

        Works in both RECEIVE and SEND mode:
        - RECEIVE: text buffered in TX, sent on next SEND press
        - SEND: text immediately queued to rate-limited TX

        Inserts text char by char via char_typed signal directly,
        bypassing insertFromMimeData to avoid parent-chain lookup issues.
        """
        store = getattr(screen, '_macro_store', None)
        if store is None or idx >= len(store.texts):
            return
        text = store.texts[idx]
        if not text:
            return
        tx = getattr(screen, 'tx_input', None)
        if tx is None:
            return

        from PyQt6.QtGui import QTextCharFormat, QColor
        from .screens.ui_theme import get_theme
        t = get_theme()
        f = QTextCharFormat()
        f.setForeground(QColor(t['tx_color']))

        # Move cursor to end before inserting
        c = tx.textCursor()
        from PyQt6.QtGui import QTextCursor
        c.movePosition(QTextCursor.MoveOperation.End)
        tx.setTextCursor(c)

        # Normalise line endings, then iterate with index for [^D] detection
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        i = 0
        while i < len(text):
            if text[i:i+4] == '[^D]':
                # EOT marker — emit sentinel, insert visual marker in TX
                from PyQt6.QtGui import QTextCharFormat as _TCF, QColor as _QC
                f_eot = _TCF()
                f_eot.setForeground(_QC("#ffffff"))
                f_eot.setBackground(_QC("#cc4400"))
                f_eot.setFontWeight(700)
                tx.setCurrentCharFormat(f_eot)
                cur = tx.textCursor()
                doc_pos = cur.position()   # position BEFORE inserting [^D]
                cur.insertText('[^D]')
                tx.setCurrentCharFormat(f)
                # [^D] = 4 doc chars, 1 _arr entry → track discrepancy
                tx._doc_extra = getattr(tx, '_doc_extra', 0) + 3
                tx.char_typed.emit('\x04', '[^D]', doc_pos)
                i += 4
            elif text[i:i+4] == '[^T:':
                # Timed marker [^T:n] — read digits up to ']'
                j = i + 4
                while j < len(text) and text[j].isdigit():
                    j += 1
                if j < len(text) and text[j] == ']':
                    marker = text[i:j+1]          # e.g. '[^T:5]'
                    marker_len = len(marker)
                    try:
                        n_val = int(text[i+4:j])
                        n_val = max(1, min(10, n_val))
                    except ValueError:
                        n_val = 1
                    from PyQt6.QtGui import QTextCharFormat as _TCF, QColor as _QC
                    f_tmr = _TCF()
                    f_tmr.setForeground(_QC("#ffffff"))
                    f_tmr.setBackground(_QC("#8800cc"))
                    f_tmr.setFontWeight(700)
                    tx.setCurrentCharFormat(f_tmr)
                    cur = tx.textCursor()
                    doc_pos = cur.position()   # position BEFORE inserting marker
                    cur.insertText(marker)
                    tx.setCurrentCharFormat(f)
                    tx._doc_extra = getattr(tx, '_doc_extra', 0) + (marker_len - 1)
                    tx.char_typed.emit(f'\x1b{n_val}', marker, doc_pos)
                    i = j + 1
                else:
                    # Malformed — insert as plain text
                    tx.setCurrentCharFormat(f)
                    cur = tx.textCursor()
                    doc_pos = cur.position()
                    cur.insertText(text[i])
                    tx.char_typed.emit(text[i], text[i], doc_pos)
                    i += 1
            elif text[i] == '\n':
                tx.setCurrentCharFormat(f)
                c = tx.textCursor()
                doc_pos = c.position()   # position BEFORE the block break
                c.insertBlock()
                tx.setTextCursor(c)
                tx.char_typed.emit('\r\n', '<CR/LF>\n', doc_pos)
                i += 1
            elif text[i].isprintable():
                tx.setCurrentCharFormat(f)
                cur = tx.textCursor()
                doc_pos = cur.position()   # position BEFORE inserting char
                cur.insertText(text[i])
                tx.char_typed.emit(text[i], text[i], doc_pos)
                i += 1
            else:
                i += 1

    # Mode → TNC stop command for Clear TX while transmitting.
    # Only modes with a continuously-keyed TX buffer appear here:
    #   Baudot / ASCII / CW-Morse → RC  (drop PTT, back to receive)
    #   AMTOR ARQ / FEC           → AM  (standby + flush TNC TX buffer; NOT R,
    #                                    which does not flush — see TX §16/§18)
    # Frame-based modes (HF/VHF Packet — a frame leaves at ETB and cannot be
    # recalled) and out-of-Host-Mode modes (PACTOR) have no keyed buffer to
    # flush, so they are deliberately absent: clearing the unsent line locally
    # IS the correct "Clear TX" for them.
    _CLEAR_TX_STOP_CMD = {
        "Baudot RTTY": b'RC',
        "ASCII RTTY":  b'RC',
        "CW / Morse":  b'RC',
        "AMTOR ARQ":   b'AM',
        "AMTOR FEC":   b'AM',
    }

    def _on_clear_tx(self) -> None:
        """Clear the TX window AND the full TX buffer (PC-side + TNC).

        The previous version only emptied the PC-side buffer (``_tx_ctrl``)
        and the screen but left PTT on, so the TNC kept keying the characters
        it had already received — the operator saw a blank window while the
        radio still transmitted the old text. Now, if a transmission is
        active, we first send the mode-appropriate stop command so the TNC
        aborts and flushes its own transmit buffer, then clear the PC side and
        drop the UI back to RECEIVE.

        Modes without a continuously-keyed buffer (Packet is frame-based;
        PACTOR runs outside Host Mode) send no stop command — see
        ``_CLEAR_TX_STOP_CMD``. The stop commands (RC for RTTY/Morse, AM for
        AMTOR) are software-verified against the mock TNC (Testplan T17/T85).
        """
        from pk232py.comm.frame import build_command

        screen = self._opmode_stack.currentWidget()
        tx = getattr(screen, 'tx_input', None)
        mode = self._modes.current_mode
        mode_name = mode.name if mode is not None else ""

        # 1. Abort the TNC transmission so already-sent chars stop on air.
        #    AMTOR has no SEND/RECEIVE button, so _send_active is never set for
        #    it — ARQ TX is CONNECTED-triggered, not button-triggered (see
        #    _make_link_handler). Its only TX-abort path is therefore Clear TX,
        #    so for AMTOR always send the AM stop command (harmless when already
        #    in standby). For the button-driven modes keep the _send_active
        #    guard so an idle Clear TX does not needlessly key the TNC with RC.
        stop = self._CLEAR_TX_STOP_CMD.get(mode_name)
        is_amtor = mode_name in ("AMTOR ARQ", "AMTOR FEC")
        if (stop is not None and (self._send_active or is_amtor)
                and self._serial.is_connected and self._serial.is_host_mode):
            frame = build_command(stop)
            self._serial.send_command(frame[2:4], frame[4:-1])
            self._log_monitor(
                f"[TX] {stop.decode()} — TX aborted, TNC buffer flushed")

        # 2. Empty the PC-side buffer/queue and reset the document anchors.
        #    _tx_ctrl.clear() resets _arr, _tx_queue, stops the timer and sets
        #    _send_active=False; we mirror the MainWindow flag to match.
        if tx is not None:
            tx.clear()
            if hasattr(tx, 'set_cycle_anchor'):
                tx.set_cycle_anchor(0, 0)
        self._tx_ctrl.clear()
        self._send_active = False

        # 3. Reflect RECEIVE in the UI WITHOUT re-firing the toggle handlers
        #    (they would send a second RC/AM). blockSignals keeps it visual.
        if hasattr(screen, 'btn_send') and screen.btn_send.isChecked():
            screen.btn_send.blockSignals(True)
            screen.btn_send.setChecked(False)
            screen.btn_send.blockSignals(False)
        if hasattr(screen, 'btn_receive') and not screen.btn_receive.isChecked():
            screen.btn_receive.blockSignals(True)
            screen.btn_receive.setChecked(True)
            screen.btn_receive.blockSignals(False)

        self._shared_tx_text = ""
        self._log_monitor("[SYS] TX buffer cleared")

    def _on_clear_rx(self) -> None:
        """Clear RX display window."""
        rx = self._rx_display
        if rx is not None:
            rx.clear()
        self._shared_rx_doc = None
        self._packet_raw_frames: list[tuple[str, str]] = []
        self._packet_aprs_active: bool = False
        self._log_monitor("[SYS] RX display cleared")

    def _on_rtty_data_ack(self) -> None:
        """Called when TNC sends DATA_ACK ($5F XX XX $00) for a sent char.

        For TxController modes (Baudot/ASCII/Morse): delegates to
        TxController.on_data_ack() which handles colour_at() and show_in_rx
        via signals.

        For other modes (AMTOR): legacy inline handling.
        """
        mode = self._modes.current_mode
        is_rtty = self._is_txctrl_mode(mode)
        if is_rtty:
            self._tx_ctrl.on_data_ack()
            return

        # Legacy: non-RTTY modes (AMTOR, Morse, etc.)
        screen = self._opmode_stack.currentWidget()
        tx = getattr(screen, 'tx_input', None)
        from PyQt6.QtGui import QTextCursor, QColor, QTextCharFormat
        rx = self._rx_display
        cursor = rx.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor('#ffee88'))
        cursor.setCharFormat(fmt)
        cursor.insertText(" ")   # placeholder for legacy modes
        fmt.setForeground(QColor('#88ccff'))
        cursor.setCharFormat(fmt)
        rx.setTextCursor(cursor)
        rx.ensureCursorVisible()

    # ── TxController helpers ───────────────────────────────────────

    def _on_baudot_xm_ack(self) -> None:
        """Called when XM ACK arrives — start rate-limited send."""
        self._tx_ctrl.on_send_start()
        self._log_monitor("[TX] XM ACK — TxController sending")

    def _on_baudot_send_char(self, char: str) -> None:
        """Send one character to TNC (called by TxController.send_to_tnc)."""
        if not self._serial.is_connected or not self._serial.is_host_mode:
            return
        if char in ('\r\n', '\n'):
            wire = b'\r\n'
        elif char == '\r':
            wire = b'\r'
        else:
            wire = char.encode('ascii', errors='replace')
        self._serial.send_data(wire, channel=0)
        self._log_monitor(f'[TX] {char!r}')

    def _on_baudot_rx_char(self, display: str) -> None:
        """Show one ACK'd char in RX window (amber — confirmed sent)."""
        rx = self._rx_display
        from PyQt6.QtGui import QTextCursor, QColor, QTextCharFormat
        cursor = rx.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor('#ffaa00'))   # amber — confirmed sent
        cursor.setCharFormat(fmt)
        cursor.insertText(display)
        fmt.setForeground(QColor('#88ccff'))   # reset to RX blue
        cursor.setCharFormat(fmt)
        rx.setTextCursor(cursor)
        rx.ensureCursorVisible()

    def _on_baudot_eot(self) -> None:
        """CTRL+D EOT marker reached — mode-specific turnaround action.

        Baudot / ASCII / CW+Morse:
            Trigger the RECEIVE button → RC sent to TNC.

        AMTOR ARQ sub-mode (btn_fec and btn_selfec NOT checked):
            Send the PTOVER character (\\x1A / Ctrl-Z) into the now-empty TX
            stream. The TNC treats it like the RECEIVE character: it waits for
            the buffer to drain (already done — TxController fires eot_reached
            only after the last DATA_ACK) then swaps ISS↔IRS, keeping the ARQ
            link alive. Do NOT use the OV host command — that fires immediately
            without waiting for the buffer (Technical Reference Manual p.179).

        AMTOR FEC sub-mode (btn_fec or btn_selfec IS checked):
            Stop the TxController. FEC has no connection concept, so no extra
            TNC command is needed — the TNC returns to AMTOR standby naturally.

        AMTOR has no btn_receive, so the RECEIVE-toggle path below is reached
        only by the RTTY/Morse screens. ARQ vs FEC is read from the screen's
        button sub-state — never from mode.name (always "AMTOR ARQ").
        """
        mode = self._modes.current_mode
        mode_name = mode.name if mode is not None else ""

        if mode_name == "AMTOR ARQ":
            screen = self._opmode_stack.currentWidget()
            # ARQ vs FEC is a screen sub-state: btn_fec / btn_selfec are
            # checked while FEC / SELFEC is the active AMTOR sub-mode.
            is_fec = (
                getattr(getattr(screen, 'btn_fec',    None), 'isChecked', lambda: False)()
                or
                getattr(getattr(screen, 'btn_selfec', None), 'isChecked', lambda: False)()
            )
            if is_fec:
                # FEC sub-mode: no ARQ link — just stop the controller.
                self._tx_ctrl.on_send_stop()
                self._log_monitor("[AMTOR] EOT — FEC TX done, controller stopped")
            else:
                # ARQ sub-mode: PTOVER → polite turnaround, link stays up.
                if self._serial.is_connected and self._serial.is_host_mode:
                    self._serial.send_data(b'\x1a', channel=0)
                    self._log_monitor("[AMTOR] EOT — PTOVER (\\x1A) sent, ARQ turnaround")
        else:
            # Baudot / ASCII / Morse: visual RECEIVE toggle triggers RC.
            screen = self._opmode_stack.currentWidget()
            if hasattr(screen, 'btn_receive') and not screen.btn_receive.isChecked():
                screen.btn_receive.setChecked(True)

    def _on_baudot_timed_send(self, n: int) -> None:
        """[^T:n] timed marker reached — RECEIVE, wait n seconds, then SEND.

        Step 1: force RECEIVE mode (PTT off).
        Step 2: after n seconds, activate SEND (PTT on) via QTimer.
        The timer is fire-and-forget; if the user presses SEND manually
        before the timer fires, setChecked(True) on an already-checked
        button is a harmless no-op.
        """
        screen = self._opmode_stack.currentWidget()
        # Step 1 — switch to RECEIVE
        if hasattr(screen, 'btn_receive') and not screen.btn_receive.isChecked():
            screen.btn_receive.setChecked(True)
        # Show countdown in status bar
        self.statusBar().showMessage(
            f"[^T:{n}] — RECEIVE for {n}s, then auto-SEND …", n * 1000)
        # Step 2 — schedule SEND after n seconds
        def _auto_send():
            s = self._opmode_stack.currentWidget()
            if hasattr(s, 'btn_send') and not s.btn_send.isChecked():
                s.btn_send.setChecked(True)
        QTimer.singleShot(n * 1000, _auto_send)

    def _on_baudot_warning(self, msg: str) -> None:
        """Handle warnings from TxController.

        BUFFER_FULL → modal QMessageBox (must be acknowledged).
        A flag prevents repeated dialogs while the box is open — the
        keyboard auto-repeat buffer can queue many BUFFER_FULL events
        before the user clicks OK.
        Other messages → status bar.
        """
        if msg == "BUFFER_FULL":
            if getattr(self, '_buffer_full_shown', False):
                return
            self._buffer_full_shown = True
            QMessageBox.warning(
                self,
                "TX Buffer Full",
                "Buffer full.\nMaximum buffer size: 512 characters.\n\n"
                "Please send or clear the current text before typing more."
            )
            QApplication.instance().processEvents()
            self._buffer_full_shown = False
        else:
            self.statusBar().showMessage(msg, 4000)

    # ─────────────────────────────────────────────────────────────────────────

    def _on_rtty_char_ready(self, char: str) -> None:
        """Send one character and echo it in the RX window.

        Called from screen eventFilter (live typing while SEND active)
        and from _on_screen_send(True) when flushing the TX buffer.
        CR/LF is shown as '<CR/LF>' in the RX window.
        """
        if not self._serial.is_connected or not self._serial.is_host_mode:
            return

        if char in ('\r\n', '\n'):
            display = '<CR/LF>\n'
            wire    = b'\r\n'
        elif char == '\r':
            display = '<CR>\n'
            wire    = b'\r'
        else:
            display = char
            wire    = char.encode('ascii', errors='replace')

        self._serial.send_data(wire, channel=0)
        # RX echo (yellow) will appear in _on_rtty_data_ack
        # when TNC sends DATA_ACK for this character.
        self._log_monitor(f'[TX] {char!r}')

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
            # If SEND was active, deactivate it now.
            # We check self._send_active (not btn_send.isChecked())
            # because RttyBaseScreen._on_receive_toggled() sets
            # btn_send=False with blockSignals BEFORE this method
            # runs, making btn_send.isChecked() already False here.
            if self._send_active:
                self._on_screen_send(False)   # ← clears _send_active + PTT logic

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

        # Also update TxController rate-limited TX speed.
        # Without this, the controller stays at the default 50 Baud
        # regardless of what the user selects in the RBAUD dropdown.
        mode_name = mode.name if mode is not None else ""
        if mode_name in ("Baudot RTTY", "ASCII RTTY"):
            self._tx_ctrl.set_mspeed(baud)
            logger.info("TxController MSPEED → %d Baud", baud)

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
        """Connect PACTOR mode buttons to TNC commands.

        Only wires if screen is a PactorScreen instance —
        PacketBaseScreen also has btn_connect and would otherwise
        receive the PACTOR slots, causing a double warning dialog.
        """
        from .screens.pactor_screen import PactorScreen
        if not isinstance(screen, PactorScreen):
            return
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

    def _wire_packet_buttons(self, screen) -> None:
        """Wire HF/VHF Packet screen buttons to MainWindow slots.

        Called from _wire_screen_buttons() whenever the active screen changes.
        Uses try/disconnect to avoid stacking signals on repeated calls.
        Skips silently for any screen that is not a PacketBaseScreen.
        """
        if not hasattr(screen, "btn_connect"):
            return
        from .screens.packet_screen import PacketBaseScreen
        if not isinstance(screen, PacketBaseScreen):
            return

        def _rewire(signal, slot):
            """Disconnect previous connection, then reconnect."""
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
            signal.connect(slot)

        # Connect button: visual feedback in screen + CO frame in MainWindow
        _rewire(screen.btn_connect.toggled, screen.on_connect_toggled)
        _rewire(screen.btn_connect.toggled, self._on_packet_connect)

        # Disconnect button
        _rewire(screen.btn_disconnect.clicked, self._on_packet_disconnect)

        # Unproto button: visual feedback in screen + UN frame in MainWindow
        _rewire(screen.btn_unproto.toggled, screen.on_unproto_toggled)
        _rewire(screen.btn_unproto.toggled, self._on_packet_unproto)

        # MailDrop button
        _rewire(screen.btn_maildrop.clicked, self._on_packet_maildrop)

        # APRS decode toggle — VHFPacketScreen only (hidden in HFPacketScreen)
        if hasattr(screen, "btn_aprs"):
            _rewire(screen.btn_aprs.toggled, screen.on_aprs_toggled)
            _rewire(screen.btn_aprs.toggled, self._on_packet_aprs_toggled)

        # MHEARD Refresh button
        _rewire(screen.mheard_panel.btn_refresh.clicked, self._on_packet_mheard)

        # HBAUD dropdown
        _rewire(screen.combo_hbaud.currentIndexChanged,
                self._on_packet_hbaud_changed)

        # Monitor level dropdown
        _rewire(screen.combo_monitor.currentIndexChanged,
                self._on_packet_monitor_changed)

        # Toggle buttons: EAS / PASSALL / MRPT / MID / SQUELCH
        # NOTE: PASSALL is mnemonic 'PS', NOT 'PA' — 'PA' is the PACKET-mode
        # activation command (host_command). Sending 'PA Y' here would re-enter
        # Packet mode instead of toggling PASSALL (TRM Host Mode command table).
        toggle_map = [
            (screen.btn_eas,     b'EA'),
            (screen.btn_passall, b'PS'),
            (screen.btn_mrpt,    b'MR'),
            (screen.btn_mid,     b'MI'),
            (screen.btn_squelch, b'SQ'),
        ]
        for btn, mnemonic in toggle_map:
            _rewire(
                btn.toggled,
                lambda checked, mn=mnemonic: self._on_packet_toggle(mn, checked)
            )

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

    # ------------------------------------------------------------------
    # Packet slots
    # ------------------------------------------------------------------

    def _on_packet_connect(self, checked: bool) -> None:
        """Connect button toggled — send CO frame to TNC.

        checked=True:  validate Dest field, send CO {callsign} on channel 1.
        checked=False: no TNC command — user uses Disconnect button to DI.
        """
        if not self._serial.is_connected or not self._serial.is_host_mode:
            return
        if not checked:
            return
        screen = self._opmode_stack.currentWidget()
        dest = getattr(screen, "le_dest", None)
        if dest is None:
            return
        callsign = dest.text().strip().upper()
        if not callsign:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "Packet Connect",
                "Please enter a destination callsign in the Dest field."
            )
            screen.btn_connect.blockSignals(True)
            screen.btn_connect.setChecked(False)
            screen.btn_connect.blockSignals(False)
            screen.on_connect_toggled(False)   # public method on PacketBaseScreen
            return
        # CONNECT is a CHANNEL command: it must go out with CTL=$41 (ch 1), not
        # the general-command CTL=$4F. send_command() rebuilds the frame with
        # CTL=$4F and the channel is lost \u2014 the TNC then treats CO as a plain
        # command and ignores the connect request. send_channel_command() writes
        # the $4x channel frame (build_ch_cmd) directly, preserving the channel.
        self._serial.send_channel_command(1, b'CO', callsign.encode('ascii'))
        self._log_monitor(f"[PACKET] Connecting \u2192 {callsign}")
        # Disable Connect immediately (CALLING): the CO is out, awaiting
        # CONNECTED \u2014 prevent a second CO before the link comes up. Disconnect
        # stays enabled so the user can abort. (set_link_state exists only on
        # the packet screen.)
        if hasattr(screen, "set_link_state"):
            screen.set_link_state("calling")

    def _on_packet_disconnect(self) -> None:
        """Disconnect button clicked — send DI frame to TNC."""
        if not self._serial.is_connected or not self._serial.is_host_mode:
            return
        # DISCONNECT is a channel command too — send the $41 channel frame, not
        # a $4F general command (see _on_packet_connect).
        self._serial.send_channel_command(1, b'DI')
        self._log_monitor("[PACKET] Disconnect sent")
        screen = self._opmode_stack.currentWidget()
        if hasattr(screen, "_set_status"):
            screen._set_status("DISCONNECTED")
        if hasattr(screen, "btn_connect"):
            screen.btn_connect.blockSignals(True)
            screen.btn_connect.setChecked(False)
            screen.btn_connect.blockSignals(False)
            screen.on_connect_toggled(False)   # public method on PacketBaseScreen

    def _on_packet_unproto(self, checked: bool) -> None:
        """Unproto button toggled — set TNC UNPROTO path.

        checked=True:  disable Connect (T39 mutual exclusion), send UN {path}.
        checked=False: re-enable Connect when no link is up; no TNC command.
        """
        screen = self._opmode_stack.currentWidget()
        # T39: Connect and Unproto are mutually exclusive. Do the UI gating
        # FIRST, independently of the link state, so the button stays consistent
        # even when not (yet) in Host Mode. btn_disconnect is enabled only while
        # a link is up/calling (set_link_state), so it is a reliable "link busy"
        # proxy for deciding whether Connect may be re-enabled.
        if hasattr(screen, "btn_connect"):
            if checked:
                screen.btn_connect.setEnabled(False)
            elif not screen.btn_disconnect.isEnabled():
                screen.btn_connect.setEnabled(True)

        if not self._serial.is_connected or not self._serial.is_host_mode:
            return
        if not checked:
            return
        unproto_field = getattr(screen, "le_unproto", None)
        path = unproto_field.text().strip().upper() if unproto_field else "CQ"
        if not path:
            path = "CQ"
        from pk232py.comm.frame import build_command
        frame = build_command(b'UN', path.encode('ascii'))
        self._serial.send_command(frame[2:4], frame[4:-1])
        self._log_monitor(f"[PACKET] UNPROTO path \u2192 {path}")

    def _on_packet_maildrop(self) -> None:
        """MailDrop button clicked — send MDCHECK command to TNC."""
        if not self._serial.is_connected or not self._serial.is_host_mode:
            return
        from pk232py.comm.frame import build_command
        frame = build_command(b'MI')
        self._serial.send_command(frame[2:4], frame[4:-1])
        self._log_monitor("[PACKET] MDCHECK \u2014 logging in to MailDrop")

    def _on_packet_mheard(self) -> None:
        """MHEARD Refresh — poll the heard-stations list line by line (T41).

        TRM §4.11: in Host Mode the MHEARD list is NOT returned by a single
        'MH' command — the verbose response is too long for the small Host Mode
        response buffer.  It must be polled one line at a time: MH0, MH1, … up
        to MH17, until an empty response (SOH $4F 'M' 'H' $00 ETB) signals the
        end of the list (≤ 18 entries, lines 0–17).

        Lernmodus — why fire-and-forget instead of waiting for each line:
        SerialManager is asynchronous — a reader/worker thread delivers each
        response later as a CMD_RESP, dispatched to handle_frame on the Qt event
        loop.  Blocking the GUI thread to wait for each MHx reply would freeze
        the UI (and risk a deadlock against that same thread).  So we send all
        18 poll frames in one burst; the TNC answers them in order and each
        reply arrives as a CMD_RESP (mnemonic 'MH') → HFPacketMode.on_mheard_entry
        → _on_mheard_entry_received().  Polls past the end of the list simply
        return empty responses, which the mode layer filters out.

        (TRM also warns the list can go inconsistent if a packet arrives mid-poll;
        the suggested HBAUD-110 workaround is intentionally NOT done here — too
        complex for v0.1.)
        """
        if not self._serial.is_connected or not self._serial.is_host_mode:
            return
        screen = self._opmode_stack.currentWidget()
        if hasattr(screen, 'mheard_panel'):
            screen.mheard_panel.clear()
        # Line index is ASCII decimal: MH0..MH9 then MH10..MH17 (two digits),
        # i.e. b'MH'+b'0' … b'MH'+b'17' — str(i) covers both without a hex trap.
        for i in range(18):
            self._serial.send_command(b'MH', str(i).encode('ascii'))
        self._log_monitor("[PACKET] MHEARD list requested (MH0..MH17)")

    @staticmethod
    def _parse_mheard_line(line: str) -> tuple[str, str, bool]:
        """Parse one MHEARD response line → (callsign, time_str, direct).

        Robust against DAYTIME being on or off (TRM): the time stamp may or may
        not be present, so we detect it by the ':' in the first token.
          "18:06:27 OE3GAS*" → ("OE3GAS", "18:06", True)   ('*' = heard direct)
          "OE1XYZ"           → ("OE1XYZ", "", False)
        A trailing DAYSTAMP date prefix is not handled (ignored) — too complex
        for v0.1.
        """
        tokens = line.strip().split()
        if not tokens:
            return ("", "", False)
        # Time token (if any) contains ':' — truncate to HH:MM.
        if len(tokens) >= 2 and ':' in tokens[0]:
            time_str = tokens[0][:5]
            call_token = tokens[1]
        else:
            time_str = ""
            call_token = tokens[0]
        direct = call_token.endswith('*')
        callsign = call_token.rstrip('*').strip()
        return (callsign, time_str, direct)

    def _on_mheard_entry_received(self, line: str) -> None:
        """One MHEARD line arrived (CMD_RESP 'MH') — add it to the panel."""
        callsign, time_str, direct = self._parse_mheard_line(line)
        if not callsign:
            return
        screen = self._opmode_stack.currentWidget()
        if hasattr(screen, 'mheard_panel'):
            screen.mheard_panel.add_entry(callsign, time_str, direct)

    def _on_packet_hbaud_changed(self, index: int) -> None:
        """HBAUD dropdown changed — send HB {value} to TNC."""
        if not self._serial.is_connected or not self._serial.is_host_mode:
            return
        screen = self._opmode_stack.currentWidget()
        combo = getattr(screen, "combo_hbaud", None)
        if combo is None:
            return
        value = combo.currentText()
        from pk232py.comm.frame import build_command
        frame = build_command(b'HB', value.encode('ascii'))
        self._serial.send_command(frame[2:4], frame[4:-1])
        self._log_monitor(f"[PACKET] HBAUD \u2192 {value}")

    def _on_packet_monitor_changed(self, index: int) -> None:
        """Monitor dropdown changed — send MN {level} to TNC."""
        if not self._serial.is_connected or not self._serial.is_host_mode:
            return
        screen = self._opmode_stack.currentWidget()
        combo = getattr(screen, "combo_monitor", None)
        if combo is None:
            return
        value = combo.currentText()
        from pk232py.comm.frame import build_command
        frame = build_command(b'MN', value.encode('ascii'))
        self._serial.send_command(frame[2:4], frame[4:-1])
        self._log_monitor(f"[PACKET] Monitor level \u2192 {value}")

    def _on_packet_toggle(self, mnemonic: bytes, checked: bool) -> None:
        """Generic toggle for EAS / PASSALL / MRPT / MID / SQUELCH.

        Sends mnemonic Y (ON) or mnemonic N (OFF) to TNC.
        """
        if not self._serial.is_connected or not self._serial.is_host_mode:
            return
        from pk232py.comm.frame import build_command
        value = b'Y' if checked else b'N'
        frame = build_command(mnemonic, value)
        self._serial.send_command(frame[2:4], frame[4:-1])
        self._log_monitor(
            f"[PACKET] {mnemonic.decode()} \u2192 {'ON' if checked else 'OFF'}"
        )

    def _wire_identity_fields(self, screen) -> None:
        """Wire identity fields to TNC parameter frames.

        Note: MYPTCALL, MYSELCAL, MYALTCAL, MYIDENT are now QLabels
        (display-only).  They are populated via _switch_opmode() from
        AppConfig.  This method wires only the AMTOR le_myident field
        which remains as a QLineEdit for direct entry, and NAVTEX fields.
        The _wire() calls for le_myptcall / le_myselcal / le_myaltcal
        are kept as no-ops: getattr() returns None for QLabels that
        don't have editingFinished, so they silently do nothing.
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
        # Persist outside the send-guard: the user changed the screen, so save
        # it even with no TNC connected (the screen reloads it on next switch).
        self._app_config.baudot.mspeed = value
        self._config_mgr.save()

    def _on_morse_mweight_changed(self, value: int) -> None:
        """MWEIGHT spinbox changed — send MW frame (mnemonic MW)."""
        from pk232py.modes.morse import MorseMode
        frame = MorseMode.mweight_frame(value)
        if self._morse_send(frame):
            mode = self._modes.current_mode
            if hasattr(mode, "mweight"):
                mode.mweight = value
            self._log_monitor(f"[PARAM] MWEIGHT → {value}")
        self._app_config.baudot.mweight = value
        self._config_mgr.save()

    def _on_morse_mid_changed(self, value: int) -> None:
        """MID spinbox changed — send MI frame (mnemonic MI)."""
        from pk232py.modes.morse import MorseMode
        frame = MorseMode.mid_frame(value)
        if self._morse_send(frame):
            mode = self._modes.current_mode
            if hasattr(mode, "mid"):
                mode.mid = value
            self._log_monitor(f"[PARAM] MID → {value} min")
        self._app_config.baudot.mid = value
        self._config_mgr.save()

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

    def _on_mode_data_received(self, ch_or_data, data=None) -> None:
        """Route decoded TNC data to the correct display widget.

        Accepts both 1-arg (data) and 2-arg (channel, data) calls so
        that this handler is safe regardless of which mode wires it.
        Packet modes use _on_packet_data_received instead (see
        _wire_mode_callbacks), but this keeps us crash-proof.

        Host Mode (stack index 0): active opmode screen's rx_display.
        Verbose Mode (stack index 1): verbose terminal _vt_display.
        """
        if data is None:
            data = ch_or_data   # 1-arg call: ch_or_data IS the data
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

    # ------------------------------------------------------------------
    # FAX handlers
    # ------------------------------------------------------------------

    def _wire_fax_buttons(self, screen) -> None:
        """Wire FaxScreen parameter controls to TNC commands.

        Skips silently for any screen that is not a FaxScreen.
        Uses try/disconnect to avoid stacking on repeated calls.
        """
        if not hasattr(screen, 'combo_fspeed'):
            return

        def _rewire(signal, slot):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
            signal.connect(slot)

        _rewire(screen.combo_fspeed.currentIndexChanged,
                self._on_fax_fspeed_changed)
        _rewire(screen.combo_aspect.currentIndexChanged,
                self._on_fax_aspect_changed)
        _rewire(screen.btn_faxneg.toggled,
                self._on_fax_faxneg_toggled)
        _rewire(screen.btn_rxrev.toggled,
                self._on_fax_rxrev_toggled)
        # LOCK is a one-shot action → wire its clicked signal (not toggled).
        if hasattr(screen, 'btn_lock'):
            _rewire(screen.btn_lock.clicked, self._on_fax_lock)
        # Stop freezes reception; Clear re-enables it (image cleared by screen).
        if hasattr(screen, 'btn_stop'):
            _rewire(screen.btn_stop.clicked, self._on_fax_stop)
        for _clr in ('btn_clear', 'btn_clear_image'):
            btn = getattr(screen, _clr, None)
            if btn is not None:
                _rewire(btn.clicked, self._on_fax_clear)

    def _on_fax_data_received(self, data: bytes) -> None:
        """Handle one decoded FAX image row.

        Each call delivers one finished horizontal scan line as bytes
        (grayscale 0=black, 255=white). NB: the $3F payload is actually an
        Epson 9-pin printer-graphics stream — FAXMode's EpsonFaxParser turns it
        into these grayscale rows, so this handler stays unchanged. The row is
        forwarded to FaxImageWidget.append_line() which renders it immediately.
        """
        if not self._fax_receiving:
            return                       # frozen by Stop — drop incoming rows
        screen = self._opmode_stack.currentWidget()
        if not hasattr(screen, 'fax_image'):
            return
        screen.fax_image.append_line(data)
        n = len(screen.fax_image._lines)
        screen.lbl_lines.setText(f"Lines: {n}")
        # Update status on first line and periodically
        if n == 1 or n % 50 == 0:
            screen._set_status("RECEIVING …", "#cc8800")
        self._log_monitor(f"[FAX] line {n} ({len(data)} bytes)")

    def _on_fax_fspeed_changed(self, index: int) -> None:
        """FSPEED dropdown changed — send FS frame to TNC."""
        if not self._serial.is_connected or not self._serial.is_host_mode:
            return
        screen = self._opmode_stack.currentWidget()
        combo = getattr(screen, 'combo_fspeed', None)
        if combo is None:
            return
        from pk232py.modes.fax import FSPEED_TABLE
        _, rpm = FSPEED_TABLE[index]
        from pk232py.modes.fax import FAXMode
        frame = FAXMode.fspeed_frame(rpm)
        self._serial.send_command(frame[2:4], frame[4:-1])
        self._log_monitor(f"[FAX] FSPEED → {rpm} RPM")

    def _on_fax_aspect_changed(self, index: int) -> None:
        """ASPECT ComboBox changed — send AY frame + update display ratio.

        *index* is the ComboBox index (0-3).
        ASPECT_TABLE[index] gives (tnc_value, ioc, ratio, label).
        """
        from pk232py.ui.screens.fax_screen import ASPECT_TABLE
        if index < 0 or index >= len(ASPECT_TABLE):
            return
        tnc_value, ioc, _ratio, _ = ASPECT_TABLE[index]

        # ASPECT only affects TNC sampling — no display effect.
        # Send AY frame to TNC.
        if not self._serial.is_connected or not self._serial.is_host_mode:
            return
        from pk232py.modes.fax import FAXMode
        frame = FAXMode.aspect_frame(tnc_value)
        self._serial.send_command(frame[2:4], frame[4:-1])
        self._log_monitor(
            f"[FAX] ASPECT {tnc_value} (IOC {ioc}, ~{2*ioc} px/line)"
        )

    def _on_fax_faxneg_toggled(self, checked: bool) -> None:
        """FAXNEG button toggled — pure DISPLAY invert (no TNC command).

        We deliberately do NOT send the FN frame any more. The TNC-side FN
        invert only affects lines received AFTER it is toggled, so flipping it
        mid-reception left the already-received top of the image at the old
        polarity while new lines came inverted — the image showed BANDED
        polarity, and it fought the display invert applied here. Doing the
        invert purely in FaxImageWidget makes it uniform and retroactive over
        the whole image. (The EpsonFaxParser invert flag stays False.)
        """
        screen = self._opmode_stack.currentWidget()
        if hasattr(screen, 'fax_image'):
            screen.fax_image.set_faxneg(checked)
        self._log_monitor(f"[FAX] FAXNEG (display) → {'ON' if checked else 'OFF'}")

    def _on_fax_rxrev_toggled(self, checked: bool) -> None:
        """RXREV button toggled — send RX frame to TNC.

        RXREV inverts the entire received signal (including sync).
        Different from FAXNEG which only inverts pixel values.
        TNC mnemonic: RV (RXREV Y/N).
        """
        if not self._serial.is_connected or not self._serial.is_host_mode:
            return
        from pk232py.comm.frame import build_command
        frame = build_command(b'RV', b'Y' if checked else b'N')
        self._serial.send_command(frame[2:4], frame[4:-1])
        self._log_monitor(f"[FAX] RXREV → {'ON' if checked else 'OFF'}")

    def _on_fax_lock(self, _checked: bool = False) -> None:
        """LOCK button clicked — force receive (mnemonic LO).

        One-shot command (no Y/N argument), like Morse LOCK. The PK-232 stays
        in FAX STBY RCVE and emits no pixel data until it detects a phasing
        sync; LO makes it start dumping pixels immediately. The image may be
        horizontally offset — correct with JUSTIFY if needed.
        """
        # Re-enable reception and start a fresh image: reset the parser so a
        # half-finished ESC L block from before the stop can't bleed in.
        self._fax_receiving = True
        self._reset_fax_parser()
        if not self._serial.is_connected or not self._serial.is_host_mode:
            return
        from pk232py.comm.frame import build_command
        frame = build_command(b'LO')
        self._serial.send_command(frame[2:4], frame[4:-1])
        self._log_monitor("[FAX] LOCK — force receive (LO)")

    def _reset_fax_parser(self) -> None:
        """Reset the FAXMode Epson parser (same as get_activate_frames()).

        Drops any partially-collected ESC L block so it cannot bleed into the
        next image after a stop/lock.
        """
        mode = self._modes.current_mode
        if mode is not None and hasattr(mode, '_parser'):
            mode._parser.reset()

    def _on_fax_stop(self, _checked: bool = False) -> None:
        """Stop button — freeze the current image and ignore further data.

        Reception (auto-sync AND LOCK) resumes only via LOCK or Clear. The
        parser is reset so a half-finished block does not bleed into the next
        image. The image stays on screen for viewing/saving.
        """
        self._fax_receiving = False
        self._reset_fax_parser()
        screen = self._opmode_stack.currentWidget()
        if hasattr(screen, '_set_status'):
            screen._set_status("READY", "#888888")
        self._log_monitor("[FAX] reception stopped")

    def _on_fax_clear(self, _checked: bool = False) -> None:
        """Clear button pressed — re-enable reception (image cleared by screen)."""
        self._fax_receiving = True

    # ------------------------------------------------------------------
    # Packet RX/TX handlers
    # ------------------------------------------------------------------

    def _on_packet_data_received(self, channel: int, data: bytes) -> None:
        """Handle $3x — received AX.25 data on *channel*.

        Displays the decoded text in the Packet screen's rx_display
        in the standard RX blue colour.  A channel prefix is shown
        when channel != 0 so multi-stream connections are readable.
        """
        try:
            text = data.decode('ascii', errors='replace')
        except Exception:
            text = repr(data)

        # Channel prefix for multi-stream (channel 0 = unproto/default)
        prefix = f"[CH{channel}] " if channel not in (0, 1) else ""
        self._log_terminal(prefix + text)
        self._log_monitor(f"[PKT RX ch{channel}] {text.rstrip()}")

    def _on_packet_monitor_frame(self, data: bytes) -> None:
        """Handle $3F — monitored/unproto AX.25 frame.

        Steps:
          1. Decode bytes → text
          2. Timestamp the frame (UTC HH:MM:SS)
          3. Append (ts, raw_text) to _packet_raw_frames buffer
             so we can re-render when APRS mode is toggled
          4. Display: raw text (APRS off) or decoded (APRS on)
        """
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")

        try:
            text = data.decode('ascii', errors='replace')
        except Exception:
            text = repr(data)
        text = text.replace('\r', '').strip()

        # Store raw frame in buffer (always — independent of display mode)
        self._packet_raw_frames.append((ts, text))

        # Display: route through decoder if APRS mode is active
        screen = self._opmode_stack.currentWidget()
        if self._packet_aprs_active:
            from pk232py.modes.aprs_decoder import AprsDecoder
            display_text = AprsDecoder.decode_html(text, ts)
            self._packet_rx_append(screen, ts, display_text, is_html=True)
        else:
            self._packet_rx_append(screen, ts, text, is_html=False)
        self._log_monitor(f"[MON] {text[:80]}")

    def _packet_rx_append(
            self, screen, ts: str, text: str,
            is_html: bool = False,
            color: str = "#aaaaaa") -> None:
        """Append one timestamped frame to screen.rx_display.

        All packet monitor output goes through here so the
        formatting is always consistent.

        Parameters
        ----------
        screen  : QWidget — the active opmode screen
        ts      : str     — UTC timestamp string "HH:MM:SS"
        text    : str     — frame text (raw) or HTML (decoded)
        is_html : bool    — if True, render text via insertHtml
        color   : str     — QColor hex string (default grey)
        """
        if not hasattr(screen, "rx_display"):
            return
        from PyQt6.QtGui import QTextCursor, QColor, QTextCharFormat
        cursor = screen.rx_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if is_html:
            cursor.insertHtml(text)
            fmt = QTextCharFormat()
            fmt.setForeground(QColor("#111111"))
            cursor.setCharFormat(fmt)
            cursor.insertText("\n")
        else:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            cursor.setCharFormat(fmt)
            # Timestamp prefix on the first line only
            lines = text.splitlines()
            if lines:
                cursor.insertText(f"[{ts}] {lines[0]}\n")
                for line in lines[1:]:
                    cursor.insertText(f"         {line}\n")
            cursor.insertText("\n")      # blank line between frames
        screen.rx_display.setTextCursor(cursor)
        screen.rx_display.ensureCursorVisible()

    def _packet_rx_redraw(self, screen) -> None:
        """Re-render the entire _packet_raw_frames buffer.

        Called when the APRS toggle changes so the user sees
        all frames in the new mode (raw ↔ decoded).
        The RX display is cleared first, then all buffered
        frames are written again — either raw or decoded.
        """
        if not hasattr(screen, "rx_display"):
            return
        screen.rx_display.clear()
        if self._packet_aprs_active:
            from pk232py.modes.aprs_decoder import AprsDecoder
        for ts, raw_text in self._packet_raw_frames:
            if self._packet_aprs_active:
                display_text = AprsDecoder.decode_html(raw_text, ts)
                self._packet_rx_append(screen, ts, display_text, is_html=True)
            else:
                self._packet_rx_append(screen, ts, raw_text, is_html=False)

    def _on_packet_aprs_toggled(self, checked: bool) -> None:
        """APRS decode button toggled.

        checked=True:  switch to APRS decoded display.
                       All frames in the buffer are decoded
                       and the RX window is redrawn.
        checked=False: switch back to raw display.
                       Buffer is re-rendered as original text.

        The visual button style is handled by
        PacketBaseScreen.on_aprs_toggled() which is also
        connected to btn_aprs.toggled.
        """
        self._packet_aprs_active = checked
        screen = self._opmode_stack.currentWidget()
        self._packet_rx_redraw(screen)
        state = "ON" if checked else "OFF"
        self._log_monitor(f"[APRS] decode mode {state}")

    def _on_packet_data_ack(self, channel: int = 0) -> None:
        """Handle $5F DATA_ACK for Packet mode.

        For Packet, DATA_ACK signals that the TNC has accepted the
        last data block.  No colour tracking needed — just log it.
        Flow control (waiting for ACK before next send) is handled
        by the TNC itself in Host Mode; we just confirm receipt.
        """
        self._log_monitor(f"[PKT ACK ch{channel}]")

    def _on_packet_tx_enter(self) -> None:
        """Send the TX window content as an AX.25 DATA frame.

        Called when the user presses Enter in the Packet screen's
        tx_input.  Grabs the complete text, sends it as build_data()
        on channel 1, then clears the TX window.

        Only fires when connected (btn_connect is checked) or in
        unproto mode (btn_unproto is checked).
        """
        if not self._serial.is_connected or not self._serial.is_host_mode:
            return
        screen = self._opmode_stack.currentWidget()
        if screen is None or not hasattr(screen, 'tx_input'):
            return

        # Only send when connected or in unproto mode
        connected = (hasattr(screen, 'btn_connect')
                     and screen.btn_connect.isChecked())
        unproto   = (hasattr(screen, 'btn_unproto')
                     and screen.btn_unproto.isChecked())
        if not connected and not unproto:
            return

        text = screen.tx_input.toPlainText()
        if not text.strip():
            return

        data = (text + '\r').encode('ascii', errors='replace')
        self._serial.send_data(data, channel=1)
        self._log_monitor(f"[PKT TX] {text.rstrip()!r}")

        # Echo in RX display (TX yellow) — will be confirmed by DATA_ACK
        from PyQt6.QtGui import QTextCursor, QColor, QTextCharFormat
        cursor = screen.rx_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor('#ffee88'))  # TX yellow
        cursor.setCharFormat(fmt)
        cursor.insertText(f'> {text.rstrip()}\n')
        screen.rx_display.setTextCursor(cursor)
        screen.rx_display.ensureCursorVisible()

        # Clear TX window
        screen.tx_input.clear()

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
        """Open Appearance settings dialog (Font & Colors)."""
        dlg = AppearanceDialog(self._app_config.appearance, parent=self)
        if dlg.exec() == AppearanceDialog.DialogCode.Accepted:
            # Hand-tuned values match no preset → mark theme "custom" (so the
            # submenu shows no check mark) unless they still equal a preset.
            self._app_config.appearance.theme = "custom"
            self._config_mgr.save()
            self._apply_appearance()
            self._sync_theme_checks()
            self._log_monitor("[SYS] Appearance settings updated")

    # ------------------------------------------------------------------
    # Theme system
    # ------------------------------------------------------------------

    def _current_theme(self):
        """Return a Theme describing the current appearance config.

        ``air`` → the Air preset (native look). Otherwise a Theme built from the
        stored font/colours, so it works for the presets AND "custom" alike.
        """
        from pk232py.ui.themes import THEMES, Theme
        a = self._app_config.appearance
        if a.theme == "air":
            return THEMES["air"]
        return Theme(
            key=a.theme, name=a.theme.title(),
            font_family=a.font_family, font_size=a.font_size,
            bg=a.bg_color, fg=a.fg_color, system_palette=False,
        )

    def _apply_palette(self) -> None:
        """Set the global QPalette + style from the current theme.

        Themed presets (Dark/Mono/Retro) use the Fusion style because the native
        Windows style ignores ``QPalette.ButtonText`` — OK/Cancel text would be
        unreadable on a dark button. Air restores the captured native style and
        its ``standardPalette()`` for a fully native look.
        """
        from pk232py.ui.themes import build_palette
        app = QApplication.instance()
        if app is None:
            return
        pal = build_palette(self._current_theme())
        if pal is None:                       # Air → native style + palette
            app.setStyle(self._system_style_name)
            app.setPalette(app.style().standardPalette())
        else:                                 # Dark/Mono/Retro → Fusion + palette
            app.setStyle("Fusion")
            app.setPalette(pal)

    def _on_theme_selected(self, key: str) -> None:
        """Apply a theme preset from the submenu — live preview + persisted."""
        from pk232py.ui.themes import THEMES
        theme = THEMES.get(key)
        if theme is None:
            return
        a = self._app_config.appearance
        a.theme       = key
        a.font_family = theme.font_family
        a.font_size   = theme.font_size
        a.bg_color    = theme.bg
        a.fg_color    = theme.fg
        self._config_mgr.save()
        self._apply_appearance()
        self._sync_theme_checks()
        self._log_monitor(f"[SYS] Theme → {theme.name}")

    def _sync_theme_checks(self) -> None:
        """Tick the active preset in the submenu (none when theme == 'custom')."""
        actions = getattr(self, "_theme_actions", None)
        if not actions:
            return
        current = self._app_config.appearance.theme
        for k, act in actions.items():
            act.setChecked(k == current)

    def _apply_appearance(self) -> None:
        """Apply appearance settings: global palette/style + display widgets."""
        a = self._app_config.appearance
        self._apply_palette()   # global QPalette + style (menus, dialogs, buttons)
        font = QFont(a.font_family, a.font_size)
        # TX text colour: a distinct gold accent ONLY on the Dark theme (where
        # it reads well and separates TX from RX). On every other theme — Mono
        # (grey, no colour), Retro (amber), Air (dark on light), or a custom
        # scheme — use the theme foreground so the TX text never ends up an
        # unreadable gold-on-light (the Air bug).
        tx_fg = "#ffee88" if a.theme == "dark" else a.fg_color
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
                # TX text color: always yellow so it is visually distinct
                # from RX text (blue) even before SEND is pressed.
                from PyQt6.QtGui import QTextCharFormat, QColor
                _tx_fmt = QTextCharFormat()
                _tx_fmt.setForeground(QColor(tx_fg))  # theme-aware TX colour
                screen.tx_input.setCurrentCharFormat(_tx_fmt)
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

        Additionally: intercept XM ACK (CMD_RESP, mnemonic=XM, status=0x00)
        to trigger TxController.on_send_start() for Baudot/ASCII modes.
        """
        # RX blink
        if self._act_serial_status.isChecked():
            self._blink_rx()

        # XM ACK → TxController for Baudot/ASCII/Morse
        if frame.kind == FrameKind.CMD_RESP and frame.mnemonic == b'XM':
            if len(frame.data) >= 3 and frame.data[2] == 0x00:
                mode = self._modes.current_mode
                if self._is_txctrl_mode(mode):
                    self._on_baudot_xm_ack()

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
        # CTRL+D is used as EOT marker in TX window during Host Mode.
        # Disable the Disconnect shortcut to prevent conflict.
        self._act_disconnect.setShortcut(
            "" if active else "Ctrl+D"
        )
        if active:
            # Clear TX controller — fresh state for new Host Mode session
            self._tx_ctrl.clear()
            screen = self._opmode_stack.currentWidget()
            tx = getattr(screen, 'tx_input', None)
            if tx is not None:
                if hasattr(tx, 'set_cycle_anchor'):
                    tx.set_cycle_anchor(0, 0)
            self._sb_mode.setText("Mode: HOST")
            self._set_mode_indicator("host")
            self._stack.setCurrentIndex(0)
            self._wire_mode_callbacks()
            # If no mode is active yet, activate Baudot as default.
            # This sends the BA frame to the TNC, syncs the ComboBox
            # to 'Baudot RTTY', wires on_data_received and all buttons.
            # Without this call ModeManager._active_mode stays None
            # and RX display, SEND/PTT and ComboBox are all broken.
            if not self._modes.current_mode_name:
                self._modes.set_mode("Baudot RTTY")
        else:
            self._sb_mode.setText("Mode: VERBOSE")
            self._set_mode_indicator("verbose")
            if self._exiting_host_mode_by_user:
                # Genuine user exit: always show verbose terminal
                # and deactivate the current mode so the next
                # Host Mode entry starts clean.
                self._exiting_host_mode_by_user = False
                if self._modes.current_mode is not None:
                    self._modes.current_mode.deactivate()
                    self._modes._active_mode = None
                self._stack.setCurrentIndex(1)
            else:
                # Temporary exit (e.g. PACTOR verbose activation):
                # keep the opmode screen visible if one is active.
                active_name = self._modes.current_mode_name
                mode_has_screen = (
                    active_name is not None
                    and active_name in self._opmode_screens
                )
                if not mode_has_screen:
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
        from PyQt6.QtGui import QTextCursor, QColor, QTextCharFormat
        cursor = self._terminal.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        # Always force RX blue color — resets any TX yellow left
        # by _on_rtty_char_ready after a SEND -> RECEIVE transition.
        fmt = QTextCharFormat()
        fmt.setForeground(QColor('#88ccff'))  # RX blue
        cursor.setCharFormat(fmt)
        cursor.insertText(text)
        self._terminal.setTextCursor(cursor)
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
        """Intercept keys for verbose terminal and opmode TX window.

        In Host Mode: forward all keypresses to the active screen's
        tx_input so that TX input works regardless of which widget
        currently holds focus. This is necessary because NoFocus
        buttons return focus to MainWindow, not to tx_input.

        Exception: when a modal dialog is open (e.g. MacroEditDialog,
        TNC Configuration), keys are NOT redirected — the dialog
        handles its own input.

        In Verbose Mode: handle _vt_input Enter / Ctrl keys.
        """
        if event.type() == QEvent.Type.KeyPress:
            # --- Host Mode: full TX key routing ---
            # Guard against re-entry: insertPlainText() generates
            # internal Qt events that re-enter this filter.
            # Guard against modal dialogs: QDialog subclasses must
            # handle their own keyboard input without interference.
            if self._serial.is_host_mode and not self._in_event_filter:
                # Skip routing if any modal dialog is currently open
                active = QApplication.activeModalWidget()
                if active is not None:
                    return super().eventFilter(obj, event)
                screen = self._opmode_stack.currentWidget()
                tx = (screen.tx_input
                      if screen is not None and hasattr(screen, 'tx_input')
                      else None)
                if tx is not None:
                    from PyQt6.QtWidgets import QLineEdit as _LE
                    key  = event.key()
                    mods = event.modifiers()
                    Alt  = Qt.KeyboardModifier.AltModifier

                    # ALT+X → SEND
                    if mods == Alt and key == Qt.Key.Key_X:
                        if (hasattr(screen, 'btn_send')
                                and not screen.btn_send.isChecked()):
                            screen.btn_send.setChecked(True)
                        return True

                    # ALT+R → RECEIVE
                    if mods == Alt and key == Qt.Key.Key_R:
                        if self._send_active and hasattr(screen, 'btn_receive'):
                            screen.btn_receive.setChecked(True)
                        return True

                    # If the active screen has a ScreenFocusController
                    # and an input field currently has focus, pass the
                    # keypress through without redirecting to tx_input.
                    _focus_ctrl = getattr(screen, 'focus_ctrl', None)
                    if _focus_ctrl is not None and _focus_ctrl.is_active():
                        return super().eventFilter(obj, event)
                    elif obj is not tx:
                        # Redirect all other keypresses to tx_input.
                        # TxInputWidget.keyPressEvent handles char_typed emission
                        # and edit protection — no manual array filling needed.
                        self._in_event_filter = True
                        try:
                            tx.setFocus()
                            QApplication.sendEvent(tx, event)
                        finally:
                            self._in_event_filter = False
                        return True
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
