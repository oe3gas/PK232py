"""
pk232py.ui.main_window
=======================
Hauptfenster von PK232PY.

Struktur:
  ┌─────────────────────────────────────────────────┐
  │  Menüleiste: File | TNC | Parameters | Configure │
  ├─────────────────────────────────────────────────┤
  │  Toolbar: [Connect] [Disconnect] [Host Mode]     │
  ├───────────────────────┬─────────────────────────┤
  │                       │                         │
  │   Terminal / RX-Panel │   Monitor-Panel          │
  │   (später befüllt)    │   (später befüllt)       │
  │                       │                         │
  ├───────────────────────┴─────────────────────────┤
  │  Statusleiste: Port | Baudrate | Mode | Zeit     │
  └─────────────────────────────────────────────────┘

In v0.1 sind die Panels noch leer – aber das Fenster startet, die Menüs
funktionieren, und der TNC kann bereits verbunden/getrennt werden.
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QTextEdit,
    QStatusBar, QLabel, QMessageBox, QToolBar,
)
from PyQt6.QtGui import QAction, QFont, QColor
from PyQt6.QtCore import Qt, QTimer

from ..comm.serial_manager import SerialManager
from ..comm.frame import HostFrame
from ..comm.constants import FrameType
from .tnc_config_dialog import TncConfigDialog, TncConfig

logger = logging.getLogger(__name__)

# Anwendungsversion
APP_VERSION = "0.1.0-dev"
APP_TITLE   = "PK232PY"


class MainWindow(QMainWindow):
    """
    Das Hauptfenster der Anwendung.

    Koordiniert:
      - SerialManager (Verbindung zum TNC)
      - TncConfigDialog (Konfiguration)
      - Menüleiste und Toolbar
      - StatusBar mit Live-Anzeigen
    """

    def __init__(self) -> None:
        super().__init__()
        self._config: TncConfig = TncConfig()
        self._serial = SerialManager(parent=self)
        self._build_ui()
        self._connect_signals()
        self._update_connection_ui(False)
        logger.info(f"{APP_TITLE} v{APP_VERSION} gestartet")

    # -----------------------------------------------------------------------
    # UI aufbauen
    # -----------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.setWindowTitle(f"{APP_TITLE} v{APP_VERSION}")
        self.resize(900, 600)

        self._build_menubar()
        self._build_toolbar()
        self._build_central()
        self._build_statusbar()

    def _build_menubar(self) -> None:
        """Erstellt die Menüleiste nach PCPackRatt-Vorbild."""
        mb = self.menuBar()

        # ── File ──────────────────────────────────────────────────────────
        file_menu = mb.addMenu("&File")

        act_load_params = QAction("Parameter laden...", self)
        act_load_params.setStatusTip("TNC-Parameter aus Datei laden")
        act_load_params.triggered.connect(self._on_load_params)
        file_menu.addAction(act_load_params)

        act_save_params = QAction("Parameter speichern...", self)
        act_save_params.setStatusTip("TNC-Parameter in Datei speichern")
        act_save_params.triggered.connect(self._on_save_params)
        file_menu.addAction(act_save_params)

        file_menu.addSeparator()

        act_exit = QAction("&Beenden", self)
        act_exit.setShortcut("Ctrl+Q")
        act_exit.setStatusTip("PK232PY beenden")
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        # ── TNC ───────────────────────────────────────────────────────────
        tnc_menu = mb.addMenu("&TNC")

        self._act_connect = QAction("&Verbinden...", self)
        self._act_connect.setShortcut("Ctrl+T")
        self._act_connect.setStatusTip("Seriellen Port öffnen und TNC verbinden")
        self._act_connect.triggered.connect(self._on_connect)
        tnc_menu.addAction(self._act_connect)

        self._act_disconnect = QAction("&Trennen", self)
        self._act_disconnect.setShortcut("Ctrl+D")
        self._act_disconnect.setStatusTip("Verbindung zum TNC trennen")
        self._act_disconnect.triggered.connect(self._on_disconnect)
        tnc_menu.addAction(self._act_disconnect)

        tnc_menu.addSeparator()

        self._act_host_on = QAction("Host Mode &aktivieren", self)
        self._act_host_on.setStatusTip("PK-232 in Host Mode versetzen")
        self._act_host_on.triggered.connect(self._on_host_mode_enter)
        tnc_menu.addAction(self._act_host_on)

        self._act_host_off = QAction("Host Mode &beenden", self)
        self._act_host_off.setStatusTip("Host Mode beenden, TNC zurück in Terminal-Modus")
        self._act_host_off.triggered.connect(self._on_host_mode_exit)
        tnc_menu.addAction(self._act_host_off)

        self._act_recovery = QAction("Host Mode &Recovery", self)
        self._act_recovery.setStatusTip(
            "Notfall-Recovery: TNC aus hängendem Host Mode befreien"
        )
        self._act_recovery.triggered.connect(self._on_recovery)
        tnc_menu.addAction(self._act_recovery)

        tnc_menu.addSeparator()

        act_monitor = QAction("Monitor-Fenster", self)
        act_monitor.setStatusTip("Monitor-Panel ein-/ausblenden")
        act_monitor.setCheckable(True)
        act_monitor.setChecked(True)
        act_monitor.triggered.connect(self._on_toggle_monitor)
        tnc_menu.addAction(act_monitor)
        self._act_monitor = act_monitor

        # ── Parameters ────────────────────────────────────────────────────
        param_menu = mb.addMenu("&Parameters")

        # Sub-Menü für die Parameter-Dialoge (werden in späteren Schritten gebaut)
        for label, slot in [
            ("HF Packet...",          self._on_params_hf_packet),
            ("PACTOR...",             self._on_params_pactor),
            ("AMTOR / NAVTEX / TDM...", self._on_params_amtor),
            ("BAUDOT / ASCII / CW...", self._on_params_baudot),
            ("Misc...",               self._on_params_misc),
            ("MailDrop...",           self._on_params_maildrop),
        ]:
            act = QAction(label, self)
            act.setEnabled(False)   # noch nicht implementiert
            act.triggered.connect(slot)
            param_menu.addAction(act)

        # ── Configure ─────────────────────────────────────────────────────
        cfg_menu = mb.addMenu("&Configure")

        act_tnc_cfg = QAction("TNC &Konfiguration...", self)
        act_tnc_cfg.setStatusTip("Port, Baudrate und Verbindungsoptionen einstellen")
        act_tnc_cfg.triggered.connect(self._on_tnc_config)
        cfg_menu.addAction(act_tnc_cfg)

        cfg_menu.addSeparator()

        act_about = QAction("Ü&ber PK232PY...", self)
        act_about.triggered.connect(self._on_about)
        cfg_menu.addAction(act_about)

    def _build_toolbar(self) -> None:
        """Erstellt die Toolbar mit den wichtigsten Schnellzugriffen."""
        tb = QToolBar("Hauptleiste", self)
        tb.setMovable(False)
        self.addToolBar(tb)

        self._tb_connect = tb.addAction("⚡ Verbinden")
        self._tb_connect.setToolTip("TNC verbinden (Ctrl+T)")
        self._tb_connect.triggered.connect(self._on_connect)

        self._tb_disconnect = tb.addAction("✕ Trennen")
        self._tb_disconnect.setToolTip("Verbindung trennen (Ctrl+D)")
        self._tb_disconnect.triggered.connect(self._on_disconnect)

        tb.addSeparator()

        self._tb_host_on = tb.addAction("⬆ Host Mode")
        self._tb_host_on.setToolTip("Host Mode aktivieren")
        self._tb_host_on.triggered.connect(self._on_host_mode_enter)

        self._tb_recovery = tb.addAction("⟳ Recovery")
        self._tb_recovery.setToolTip("Host Mode Recovery")
        self._tb_recovery.triggered.connect(self._on_recovery)

    def _build_central(self) -> None:
        """
        Erstellt den Hauptbereich:

        Horizontal aufgeteilt in:
          Links (Hauptbereich) – vertikal geteilt:
            Oben:  TNC-Output  (Read-Only, empfangene Daten)
            Unten: User-Input  (Eingabezeile + Send-Button)
          Rechts: Monitor-Panel (optional, Rohdaten)

        Struktur:
          QSplitter (horizontal)
          ├── QWidget (linke Seite)
          │   └── QSplitter (vertikal)
          │       ├── QTextEdit  _rx_display  (TNC Output, oben)
          │       └── QWidget    _input_area  (User Input, unten)
          │           ├── QTextEdit  _tx_input
          │           └── QPushButton  _send_btn
          └── QTextEdit  _monitor  (rechts, ausblendbar)
        """
        from PyQt6.QtWidgets import QPushButton, QVBoxLayout, QHBoxLayout

        # ── Äußerer horizontaler Splitter (Terminal | Monitor) ────────────
        outer_splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Linke Seite: vertikaler Splitter (RX oben | TX unten) ─────────
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        v_splitter = QSplitter(Qt.Orientation.Vertical)

        # Oben: TNC Output (Read-Only)
        self._rx_display = QTextEdit()
        self._rx_display.setReadOnly(True)
        self._rx_display.setFont(QFont("Courier New", 10))
        self._rx_display.setStyleSheet(
            "background-color: #1e1e1e; color: #d4d4d4; border: none;"
        )
        self._rx_display.setPlaceholderText(
            "TNC Output – Empfangene Daten und Antworten erscheinen hier."
        )
        v_splitter.addWidget(self._rx_display)

        # Unten: User Input (Eingabezeile + Send-Button)
        input_widget = QWidget()
        input_widget.setStyleSheet("background-color: #252526;")
        input_layout = QHBoxLayout(input_widget)
        input_layout.setContentsMargins(4, 4, 4, 4)
        input_layout.setSpacing(4)

        self._tx_input = QTextEdit()
        self._tx_input.setFont(QFont("Courier New", 10))
        self._tx_input.setStyleSheet(
            "background-color: #1e1e1e; color: #d4d4d4; border: 1px solid #444;"
        )
        self._tx_input.setPlaceholderText("Befehl eingeben… (Enter = Senden)")
        self._tx_input.setFixedHeight(60)
        # Enter-Taste → Senden (Shift+Enter = neue Zeile)
        self._tx_input.installEventFilter(self)
        input_layout.addWidget(self._tx_input)

        send_btn = QPushButton("Senden")
        send_btn.setFixedWidth(80)
        send_btn.setFixedHeight(60)
        send_btn.setStyleSheet(
            "QPushButton { background-color: #0e639c; color: white; "
            "border: none; font-weight: bold; }"
            "QPushButton:hover { background-color: #1177bb; }"
            "QPushButton:pressed { background-color: #0a4f7e; }"
            "QPushButton:disabled { background-color: #3a3a3a; color: #666; }"
        )
        send_btn.clicked.connect(self._on_send)
        self._send_btn = send_btn
        input_layout.addWidget(send_btn)

        v_splitter.addWidget(input_widget)

        # Verhältnis: RX-Display 80%, Input-Zeile 20%
        v_splitter.setSizes([480, 120])
        v_splitter.setCollapsible(1, False)   # Input-Bereich nicht kollabierbar

        left_layout.addWidget(v_splitter)
        outer_splitter.addWidget(left_widget)

        # ── Rechte Seite: Monitor-Panel ───────────────────────────────────
        self._monitor = QTextEdit()
        self._monitor.setReadOnly(True)
        self._monitor.setFont(QFont("Courier New", 9))
        self._monitor.setStyleSheet(
            "background-color: #0d1117; color: #8b949e; border: none;"
        )
        self._monitor.setPlaceholderText("Monitor – Rohdaten / Frame-Protokoll")
        outer_splitter.addWidget(self._monitor)

        # Monitor standardmäßig ausgeblendet (über TNC → Monitor-Fenster einblendbar)
        self._monitor.setVisible(False)
        outer_splitter.setSizes([900, 0])
        self._splitter = outer_splitter
        self.setCentralWidget(outer_splitter)

        # _terminal als Alias auf _rx_display (für bestehende Log-Methoden)
        self._terminal = self._rx_display

    def _build_statusbar(self) -> None:
        """
        Statusleiste mit mehreren Segmenten:
          [Port: ---] [Baud: ---] [Mode: ---] [Zeit (UTC)]
        """
        sb = self.statusBar()

        self._sb_port = QLabel("Port: ---")
        self._sb_port.setMinimumWidth(120)
        sb.addPermanentWidget(self._sb_port)

        self._sb_baud = QLabel("Baud: ---")
        self._sb_baud.setMinimumWidth(90)
        sb.addPermanentWidget(self._sb_baud)

        self._sb_mode = QLabel("Mode: OFFLINE")
        self._sb_mode.setMinimumWidth(130)
        sb.addPermanentWidget(self._sb_mode)

        self._sb_time = QLabel("UTC: --:--:--")
        self._sb_time.setMinimumWidth(110)
        sb.addPermanentWidget(self._sb_time)

        # UTC-Uhr: jede Sekunde aktualisieren
        self._utc_timer = QTimer(self)
        self._utc_timer.timeout.connect(self._update_utc_clock)
        self._utc_timer.start(1000)
        self._update_utc_clock()

    # -----------------------------------------------------------------------
    # Signal-Verbindungen
    # -----------------------------------------------------------------------

    def _connect_signals(self) -> None:
        """Verbindet SerialManager-Signals mit unseren Slots."""
        self._serial.frame_received.connect(self._on_frame_received)
        self._serial.connection_changed.connect(self._update_connection_ui)
        self._serial.status_message.connect(self._on_status_message)

    # -----------------------------------------------------------------------
    # Slots – TNC-Verbindung
    # -----------------------------------------------------------------------

    def _on_connect(self) -> None:
        """Öffnet zuerst den Konfigurationsdialog, dann verbindet."""
        dlg = TncConfigDialog(self._config, parent=self)
        if dlg.exec() != TncConfigDialog.DialogCode.Accepted:
            return

        self._config = dlg.get_config()
        if not self._config.port_name or self._config.port_name.startswith("("):
            QMessageBox.warning(self, "Kein Port", "Bitte einen gültigen COM-Port auswählen.")
            return

        success = self._serial.connect_port(
            self._config.port_name,
            baudrate=self._config.baudrate,
            rtscts=self._config.rtscts,
        )

        if success:
            self._log_monitor(f"[SYSTEM] Verbunden: {self._config.port_name} @ {self._config.baudrate} Bd")
            # Host Mode direkt nach dem Verbinden aktivieren
            if self._serial.enter_host_mode():
                self._log_monitor("[SYSTEM] Host Mode aktiv")
            else:
                self._log_monitor("[WARNUNG] Host Mode konnte nicht aktiviert werden")

    def _on_disconnect(self) -> None:
        """Trennt die Verbindung zum TNC."""
        self._serial.disconnect_port()
        self._log_monitor("[SYSTEM] Verbindung getrennt")

    def _on_host_mode_enter(self) -> None:
        if self._serial.is_connected:
            self._serial.enter_host_mode()

    def _on_host_mode_exit(self) -> None:
        if self._serial.is_connected:
            self._serial.exit_host_mode()

    def _on_recovery(self) -> None:
        if self._serial.is_connected:
            self._serial.host_mode_recovery()
            self._log_monitor("[SYSTEM] Host Mode Recovery gesendet")

    # -----------------------------------------------------------------------
    # Slots – Parameter-Dialoge (Platzhalter)
    # -----------------------------------------------------------------------

    def _on_tnc_config(self) -> None:
        """TNC-Konfigurationsdialog ohne sofortiges Verbinden öffnen."""
        dlg = TncConfigDialog(self._config, parent=self)
        if dlg.exec() == TncConfigDialog.DialogCode.Accepted:
            self._config = dlg.get_config()

    def _on_load_params(self) -> None:
        self.statusBar().showMessage("Parameter laden – noch nicht implementiert", 3000)

    def _on_save_params(self) -> None:
        self.statusBar().showMessage("Parameter speichern – noch nicht implementiert", 3000)

    def _on_params_hf_packet(self) -> None:
        self.statusBar().showMessage("HF Packet Parameter – kommt in v0.2", 3000)

    def _on_params_pactor(self) -> None:
        self.statusBar().showMessage("PACTOR Parameter – kommt in v0.2", 3000)

    def _on_params_amtor(self) -> None:
        self.statusBar().showMessage("AMTOR/NAVTEX/TDM Parameter – kommt in v0.2", 3000)

    def _on_params_baudot(self) -> None:
        self.statusBar().showMessage("BAUDOT/ASCII/CW Parameter – kommt in v0.2", 3000)

    def _on_params_misc(self) -> None:
        self.statusBar().showMessage("Misc Parameter – kommt in v0.2", 3000)

    def _on_params_maildrop(self) -> None:
        self.statusBar().showMessage("MailDrop Parameter – kommt in v0.2", 3000)

    def _on_toggle_monitor(self, checked: bool) -> None:
        """Monitor-Panel ein-/ausblenden."""
        self._monitor.setVisible(checked)
        if checked:
            self._splitter.setSizes([630, 270])
        else:
            self._splitter.setSizes([900, 0])

    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            f"Über {APP_TITLE}",
            f"<b>{APP_TITLE}</b> v{APP_VERSION}<br><br>"
            "Moderner Cross-Platform Client für den<br>"
            "<b>AEA PK-232/PK-232MBX</b> Multi-Mode TNC.<br><br>"
            "Python 3 + PyQt6<br>"
            "GPL v2 – Open Source<br><br>"
            "73 de OE3GAS",
        )

    # -----------------------------------------------------------------------
    # Slots – empfangene Frames verarbeiten
    # -----------------------------------------------------------------------

    def _on_frame_received(self, frame: HostFrame) -> None:
        """
        Wird aufgerufen wenn ein vollständiger Frame vom TNC eintrifft.

        In v0.1: Rohdaten im Monitor anzeigen, Text im Terminal.
        Später: Frame an den jeweils aktiven Modus-Handler weitergeben.
        """
        # Immer im Monitor anzeigen (Rohdaten)
        self._log_monitor(
            f"[RX] CTL=0x{frame.ctl:02X} "
            f"type={frame.frame_type} "
            f"data={frame.data!r}"
        )

        # Wenn es ein Command-Response ist: Text im Terminal anzeigen
        if frame.is_command_response():
            try:
                text = frame.data.decode("ascii", errors="replace").strip()
                if text:
                    self._log_terminal(text)
            except Exception:
                pass

    def _on_status_message(self, msg: str) -> None:
        """Zeigt Statusmeldungen vom SerialManager in der Statusleiste."""
        self.statusBar().showMessage(msg, 5000)

    # -----------------------------------------------------------------------
    # UI-Zustand aktualisieren
    # -----------------------------------------------------------------------

    def _update_connection_ui(self, connected: bool) -> None:
        """
        Aktiviert/deaktiviert Menüeinträge und Toolbar-Buttons
        je nach Verbindungszustand.
        """
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
            self._sb_mode.setText("Mode: CONNECTED")
        else:
            self._sb_port.setText("Port: ---")
            self._sb_baud.setText("Baud: ---")
            self._sb_mode.setText("Mode: OFFLINE")

    # -----------------------------------------------------------------------
    # Ausgabe-Hilfsmethoden
    # -----------------------------------------------------------------------

    def _log_terminal(self, text: str) -> None:
        """Fügt Text zum Terminal-Panel hinzu."""
        self._terminal.append(text)

    def _log_monitor(self, text: str) -> None:
        """Fügt eine Zeile zum Monitor-Panel hinzu."""
        self._monitor.append(text)

    def _update_utc_clock(self) -> None:
        """Aktualisiert die UTC-Zeitanzeige in der Statusleiste."""
        from datetime import datetime, timezone
        utc = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self._sb_time.setText(f"UTC: {utc}")

    # -----------------------------------------------------------------------
    # Eingabe senden
    # -----------------------------------------------------------------------

    def eventFilter(self, obj, event) -> bool:
        """
        Fängt Enter-Taste im Eingabefeld ab.

        Enter allein  → Senden
        Shift+Enter   → Neue Zeile einfügen (normale Funktion)

        eventFilter ist ein Qt-Mechanismus: Wir registrieren uns als
        "Filter" für Events von _tx_input. Qt ruft uns auf, bevor das
        Widget das Event selbst verarbeitet. Rückgabe True = "geschluckt".
        """
        from PyQt6.QtCore import QEvent
        from PyQt6.QtCore import Qt as _Qt

        if obj is self._tx_input and event.type() == QEvent.Type.KeyPress:
            if (event.key() == _Qt.Key.Key_Return and
                    not (event.modifiers() & _Qt.KeyboardModifier.ShiftModifier)):
                self._on_send()
                return True
        return super().eventFilter(obj, event)

    def _on_send(self) -> None:
        """
        Sendet den Inhalt des Eingabefelds als Befehl an den TNC.

        - Leerzeilen werden ignoriert
        - Gesendeter Text wird im RX-Display mit '> ' Präfix angezeigt (Echo)
        - Eingabefeld wird nach dem Senden geleert
        """
        text = self._tx_input.toPlainText().strip()
        if not text:
            return

        if not self._serial.is_connected:
            self.statusBar().showMessage("Nicht verbunden – zuerst TNC verbinden.", 3000)
            return

        if not self._serial.is_host_mode:
            self.statusBar().showMessage("Host Mode nicht aktiv.", 3000)
            return

        # Echo im RX-Display (blau = gesendete Befehle)
        self._log_terminal(f"<span style='color:#569cd6;'>&gt; {text}</span>")
        self._log_monitor(f"[TX] cmd={text!r}")

        for line in text.splitlines():
            line = line.strip()
            if line:
                self._serial.send_command(line)

        self._tx_input.clear()

    # -----------------------------------------------------------------------
    # Fenster schließen
    # -----------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        """
        Wird aufgerufen wenn der Benutzer das Fenster schließt.

        Stellt sicher, dass die TNC-Verbindung sauber getrennt wird,
        bevor die Anwendung beendet wird.
        """
        if self._serial.is_connected:
            reply = QMessageBox.question(
                self,
                "Beenden",
                "TNC ist noch verbunden. Trotzdem beenden?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

            self._serial.disconnect_port()

        event.accept()
