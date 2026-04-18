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

from PyQt6.QtCore import QEvent, QSettings, Qt, QTimer
from PyQt6.QtGui import QAction, QFont
from PyQt6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QPushButton, QSplitter, QTextEdit, QToolBar, QVBoxLayout, QWidget,
)

from pk232py import __version__
from ..comm.serial_manager import SerialManager
from ..comm.frame import HostFrame, FrameKind
from ..mode_manager import ModeManager
from ..comm.params_uploader import ParamsUploader
from .tnc_config_dialog import TncConfigDialog, TncConfig
from .dialogs.params_hf      import HFPacketParamsDialog
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
        self._misc_params: dict = {}
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

        self._act_connect = QAction("&Connect...", self)
        self._act_connect.setShortcut("Ctrl+T")
        self._act_connect.setStatusTip("Open serial port and connect to TNC")
        self._act_connect.triggered.connect(self._on_connect)
        tnc_menu.addAction(self._act_connect)

        self._act_disconnect = QAction("&Disconnect", self)
        self._act_disconnect.setShortcut("Ctrl+D")
        self._act_disconnect.setStatusTip("Disconnect from TNC")
        self._act_disconnect.triggered.connect(self._on_disconnect)
        tnc_menu.addAction(self._act_disconnect)

        tnc_menu.addSeparator()

        self._act_host_on = QAction("Enter &Host Mode", self)
        self._act_host_on.setStatusTip("Switch PK-232 to Host Mode")
        self._act_host_on.triggered.connect(self._on_host_mode_enter)
        tnc_menu.addAction(self._act_host_on)

        self._act_host_off = QAction("Leave Host Mode", self)
        self._act_host_off.setStatusTip("Leave Host Mode, return TNC to terminal mode")
        self._act_host_off.triggered.connect(self._on_host_mode_exit)
        tnc_menu.addAction(self._act_host_off)

        self._act_recovery = QAction("Host Mode &Recovery", self)
        self._act_recovery.setStatusTip(
            "Emergency recovery: free TNC from stuck Host Mode"
        )
        self._act_recovery.triggered.connect(self._on_recovery)
        tnc_menu.addAction(self._act_recovery)

        tnc_menu.addSeparator()

        self._act_monitor = QAction("Monitor Window", self)
        self._act_monitor.setStatusTip("Show/hide monitor panel")
        self._act_monitor.setCheckable(True)
        self._act_monitor.setChecked(False)
        self._act_monitor.triggered.connect(self._on_toggle_monitor)
        tnc_menu.addAction(self._act_monitor)

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

        act_about = QAction("&About PK232PY...", self)
        act_about.triggered.connect(self._on_about)
        cfg_menu.addAction(act_about)

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main", self)
        tb.setMovable(False)
        self.addToolBar(tb)

        self._tb_connect = tb.addAction("⚡ Connect")
        self._tb_connect.setToolTip("Connect to TNC (Ctrl+T)")
        self._tb_connect.triggered.connect(self._on_connect)

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
        """Build the central widget: [RX/TX area | Monitor panel]."""
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

        self._monitor = QTextEdit()
        self._monitor.setReadOnly(True)
        self._monitor.setFont(QFont("Courier New", 9))
        self._monitor.setStyleSheet(
            "background-color:#0d1117; color:#8b949e; border:none;"
        )
        self._monitor.setPlaceholderText("Monitor — raw frame log")
        self._monitor.setVisible(False)
        outer.addWidget(self._monitor)
        outer.setSizes([900, 0])

        self._splitter = outer
        self._terminal = self._rx_display
        self.setCentralWidget(outer)

    def _build_statusbar(self) -> None:
        sb = self.statusBar()

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

    def _on_connect(self) -> None:
        dlg = TncConfigDialog(self._config, parent=self)
        if dlg.exec() != TncConfigDialog.DialogCode.Accepted:
            return

        self._config = dlg.get_config()
        if not self._config.port_name or self._config.port_name.startswith("("):
            QMessageBox.warning(self, "No Port", "Please select a valid serial port.")
            return

        ok = self._serial.connect_port(
            self._config.port_name,
            baudrate=self._config.baudrate,
        )
        if ok:
            self._log_monitor(
                f"[SYS] Connected: {self._config.port_name} @ {self._config.baudrate} Bd"
            )
            self._serial.init_tnc()

    def _on_disconnect(self) -> None:
        self._serial.disconnect_port()
        self._log_monitor("[SYS] Disconnected")

    def _on_verbose_mode_ready(self) -> None:
        """Called when TNC is in verbose mode — upload params then enter Host Mode."""
        self._log_monitor("[SYS] TNC in verbose mode — uploading parameters...")
        self._sb_mode.setText("Mode: VERBOSE")
        # Upload parameters in background thread
        import threading
        def _upload():
            uploader = ParamsUploader(self._serial, self._app_config)
            n = uploader.upload()
            self._log_monitor(f"[SYS] {n} parameters uploaded")
            # Now enter Host Mode
            self._serial.enter_host_mode()
        threading.Thread(target=_upload, daemon=True, name="PK232-ParamUpload").start()

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
        self._modes.set_mode(name)

    def _on_mode_changed(self, name: str) -> None:
        """Called by ModeManager when mode switch completes."""
        self._sb_mode.setText(f"Mode: {name}")
        self._log_monitor(f"[SYS] Mode: {name}")
        # Sync ComboBox without triggering _on_mode_selected
        self._mode_combo.blockSignals(True)
        idx = self._mode_combo.findText(name)
        if idx >= 0:
            self._mode_combo.setCurrentIndex(idx)
        self._mode_combo.blockSignals(False)

    def _on_mode_switch_failed(self, reason: str) -> None:
        self.statusBar().showMessage(f"Mode switch failed: {reason}", 4000)

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
        # Pre-fill from stored values if available
        if hasattr(self, '_misc_params'):
            dlg.set_values(**self._misc_params)
        if dlg.exec() == MiscParamsDialog.DialogCode.Accepted:
            self._misc_params = dlg.get_values()
            self._log_monitor("[SYS] Misc parameters updated")

    def _on_params_pactor(self) -> None:
        """Open PACTOR Parameters dialog."""
        dlg = PACTORParamsDialog(self._app_config.pactor, parent=self)
        if dlg.exec() == PACTORParamsDialog.DialogCode.Accepted:
            self._log_monitor("[SYS] PACTOR parameters updated")

    def _on_params_amtor(self) -> None:
        """Open AMTOR / NAVTEX / TDM Parameters dialog."""
        dlg = AMTORParamsDialog(parent=self)
        if hasattr(self, '_amtor_params'):
            dlg.set_values(**self._amtor_params)
        if dlg.exec() == AMTORParamsDialog.DialogCode.Accepted:
            self._amtor_params = dlg.get_values()
            self._log_monitor("[SYS] AMTOR/NAVTEX/TDM parameters updated")

    def _on_params_baudot(self) -> None:
        """Open BAUDOT / ASCII / CW Parameters dialog."""
        dlg = BaudotParamsDialog(parent=self)
        if hasattr(self, '_baudot_params'):
            dlg.set_values(**self._baudot_params)
        if dlg.exec() == BaudotParamsDialog.DialogCode.Accepted:
            self._baudot_params = dlg.get_values()
            self._log_monitor("[SYS] BAUDOT/ASCII/CW parameters updated")

    def _on_params_maildrop(self) -> None:
        """Open MailDrop Parameters dialog."""
        dlg = MailDropParamsDialog(parent=self)
        if hasattr(self, '_maildrop_params'):
            dlg.set_values(**self._maildrop_params)
        if dlg.exec() == MailDropParamsDialog.DialogCode.Accepted:
            self._maildrop_params = dlg.get_values()
            self._log_monitor("[SYS] MailDrop parameters updated")

    def _on_toggle_monitor(self, checked: bool) -> None:
        self._monitor.setVisible(checked)
        self._splitter.setSizes([630, 270] if checked else [900, 0])

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
        """Log every incoming frame to the monitor panel.

        Frame dispatch to the active mode is handled by ModeManager.on_frame()
        which is also connected to frame_received.

        RX_DATA and RX_MONITOR frames additionally show decoded text
        in the terminal panel.
        """
        # Monitor: always log raw frame
        self._log_monitor(
            f"[RX] ctl=0x{frame.ctl:02X} kind={frame.kind.name} "
            f"ch={frame.channel} data={frame.data!r}"
        )

        # Terminal: show received text for data frames
        if frame.kind in (FrameKind.RX_DATA, FrameKind.RX_MONITOR, FrameKind.ECHO):
            text = frame.text.strip()
            if text:
                self._log_terminal(text)

    def _on_status_message(self, msg: str) -> None:
        self.statusBar().showMessage(msg, 5000)

    # ------------------------------------------------------------------
    # UI state updates
    # ------------------------------------------------------------------

    def _update_connection_ui(self, connected: bool) -> None:
        self._act_connect.setEnabled(not connected)
        self._act_disconnect.setEnabled(connected)
        self._act_host_on.setEnabled(connected)
        self._act_host_off.setEnabled(connected)
        self._act_recovery.setEnabled(connected)
        self._tb_connect.setEnabled(not connected)
        self._tb_disconnect.setEnabled(connected)
        self._tb_host_on.setEnabled(connected)
        self._tb_recovery.setEnabled(connected)

        if connected:
            self._sb_port.setText(f"Port: {self._config.port_name}")
            self._sb_baud.setText(f"Baud: {self._config.baudrate}")
        else:
            self._sb_port.setText("Port: ---")
            self._sb_baud.setText("Baud: ---")
            self._sb_mode.setText("Mode: OFFLINE")
            self._mode_combo.setEnabled(False)

    def _update_host_mode_ui(self, active: bool) -> None:
        """Enable mode selector when Host Mode is active."""
        self._mode_combo.setEnabled(active)
        if active:
            self._sb_mode.setText("Mode: HOST")
        else:
            self._sb_mode.setText("Mode: VERBOSE")

    # ------------------------------------------------------------------
    # Output helpers
    # ------------------------------------------------------------------

    def _log_terminal(self, text: str) -> None:
        self._terminal.append(text)

    def _log_monitor(self, text: str) -> None:
        self._monitor.append(text)

    def _update_utc_clock(self) -> None:
        utc = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self._sb_time.setText(f"UTC: {utc}")

    # ------------------------------------------------------------------
    # Input / send
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event) -> bool:
        if (obj is self._tx_input
                and event.type() == QEvent.Type.KeyPress
                and event.key() == Qt.Key.Key_Return
                and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)):
            self._on_send()
            return True
        return super().eventFilter(obj, event)

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
            self.statusBar().showMessage("Not connected — connect to TNC first.", 3000)
            return

        if not self._serial.is_host_mode:
            self.statusBar().showMessage("Host Mode not active.", 3000)
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