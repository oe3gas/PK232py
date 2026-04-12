"""
pk232py.ui.tnc_config_dialog
=============================
TNC-Konfigurationsdialog.

Ermöglicht die Auswahl von:
  - Seriellem Port (COM1, COM3, /dev/ttyUSB0, ...)
  - Baudrate
  - Hardware-Handshake (RTS/CTS)
  - Host Mode On Exit (TNC beim Beenden in Terminal-Mode zurückversetzen)

Orientiert sich am PCPackRatt "TNC Configuration"-Dialog (TNC_Config_at_Start.png),
vereinfacht für PK232PY v0.1 auf die wesentlichen Parameter.

Verwendung:
    dlg = TncConfigDialog(current_config, parent=self)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        config = dlg.get_config()
"""

from __future__ import annotations
from dataclasses import dataclass

from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QGroupBox,
    QHBoxLayout, QVBoxLayout, QComboBox, QCheckBox,
    QLabel, QPushButton, QSpinBox,
)
from PyQt6.QtCore import Qt

from ..comm.serial_manager import SerialManager
from ..comm.constants import SerialDefaults


# ---------------------------------------------------------------------------
# Konfigurationsdatenklasse
# ---------------------------------------------------------------------------

@dataclass
class TncConfig:
    """
    Hält alle TNC-Verbindungseinstellungen.

    Wird zwischen Dialog und MainWindow übergeben und in der INI-Datei
    gespeichert (kommt in config/settings.py).
    """
    port_name:  str  = ""
    baudrate:   int  = SerialDefaults.BAUDRATE
    rtscts:     bool = SerialDefaults.RTSCTS
    host_mode_on_exit: bool = True    # Host Mode beim Trennen beenden
    fast_init:  bool = False          # Schnelle Initialisierung (kürzer warten)


# ---------------------------------------------------------------------------
# Der Dialog
# ---------------------------------------------------------------------------

class TncConfigDialog(QDialog):
    """
    Modaler Dialog zur TNC-Konfiguration.

    'Modal' bedeutet: Solange der Dialog offen ist, kann der Rest der
    Anwendung nicht bedient werden. Das ist hier gewünscht – wir wollen
    keine Verbindungsversuche während der Konfiguration.
    """

    # Unterstützte Baudraten für den PK-232MBX
    BAUDRATES = [1200, 2400, 4800, 9600, 19200]

    def __init__(
        self,
        config: TncConfig | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._config = config or TncConfig()
        self._build_ui()
        self._populate(self._config)

    # -----------------------------------------------------------------------
    # UI aufbauen
    # -----------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.setWindowTitle("TNC Konfiguration")
        self.setMinimumWidth(380)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setSpacing(12)

        # ── Verbindungs-Gruppe ──────────────────────────────────────────────
        conn_group = QGroupBox("Verbindung")
        form = QFormLayout(conn_group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Port-Auswahl (ComboBox mit Refresh-Button)
        port_row = QHBoxLayout()
        self._port_combo = QComboBox()
        self._port_combo.setMinimumWidth(140)
        self._port_combo.setEditable(True)   # Manuelle Eingabe erlaubt
        port_row.addWidget(self._port_combo)

        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedWidth(32)
        refresh_btn.setToolTip("Verfügbare Ports neu laden")
        refresh_btn.clicked.connect(self._refresh_ports)
        port_row.addWidget(refresh_btn)
        form.addRow("COM Port:", port_row)

        # Baudrate
        self._baud_combo = QComboBox()
        for br in self.BAUDRATES:
            self._baud_combo.addItem(str(br), br)
        form.addRow("Baudrate:", self._baud_combo)

        root.addWidget(conn_group)

        # ── Optionen-Gruppe ─────────────────────────────────────────────────
        opt_group = QGroupBox("Optionen")
        opt_layout = QVBoxLayout(opt_group)

        self._rtscts_cb = QCheckBox("Hardware-Handshake (RTS/CTS)")
        self._rtscts_cb.setToolTip(
            "Empfohlen für PK-232MBX. Deaktivieren nur wenn Kabel kein RTS/CTS hat."
        )
        opt_layout.addWidget(self._rtscts_cb)

        self._hm_exit_cb = QCheckBox("Host Mode beim Trennen beenden")
        self._hm_exit_cb.setToolTip(
            "Sendet HON-Frame bevor der Port geschlossen wird.\n"
            "Versetzt den TNC zurück in den Terminal-Modus."
        )
        opt_layout.addWidget(self._hm_exit_cb)

        self._fast_init_cb = QCheckBox("Schnelle Initialisierung")
        self._fast_init_cb.setToolTip(
            "Kürzere Wartezeiten beim Aktivieren des Host Mode.\n"
            "Nur aktivieren wenn der TNC schnell antwortet."
        )
        opt_layout.addWidget(self._fast_init_cb)

        root.addWidget(opt_group)

        # ── Info-Label ──────────────────────────────────────────────────────
        info = QLabel(
            "<small><i>TNC Modell: AEA PK-232/PK-232MBX &nbsp;|&nbsp; "
            "Firmware: v7.1 / v7.2</i></small>"
        )
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(info)

        # ── Buttons (OK / Abbrechen) ─────────────────────────────────────────
        # QDialogButtonBox erstellt OK/Cancel automatisch mit der richtigen
        # Plattform-Reihenfolge (Windows: OK links, macOS: OK rechts)
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        root.addWidget(btn_box)

        # Ports initial laden
        self._refresh_ports()

    def _populate(self, cfg: TncConfig) -> None:
        """Füllt die Widgets mit den Werten aus cfg."""
        # Port setzen (oder manuell eintragen wenn nicht in Liste)
        idx = self._port_combo.findText(cfg.port_name)
        if idx >= 0:
            self._port_combo.setCurrentIndex(idx)
        else:
            self._port_combo.setCurrentText(cfg.port_name)

        # Baudrate setzen
        idx = self._baud_combo.findData(cfg.baudrate)
        if idx >= 0:
            self._baud_combo.setCurrentIndex(idx)

        self._rtscts_cb.setChecked(cfg.rtscts)
        self._hm_exit_cb.setChecked(cfg.host_mode_on_exit)
        self._fast_init_cb.setChecked(cfg.fast_init)

    def _refresh_ports(self) -> None:
        """Lädt die Liste der verfügbaren seriellen Ports neu."""
        current = self._port_combo.currentText()
        self._port_combo.clear()

        ports = SerialManager.list_ports()
        if ports:
            self._port_combo.addItems(ports)
            # Vorherige Auswahl beibehalten wenn noch vorhanden
            idx = self._port_combo.findText(current)
            if idx >= 0:
                self._port_combo.setCurrentIndex(idx)
            else:
                self._port_combo.setCurrentText(current)
        else:
            self._port_combo.addItem("(keine Ports gefunden)")

    # -----------------------------------------------------------------------
    # Ergebnis abfragen
    # -----------------------------------------------------------------------

    def get_config(self) -> TncConfig:
        """
        Gibt die vom Benutzer eingestellte Konfiguration zurück.

        Aufruf nur sinnvoll nach exec() == QDialog.DialogCode.Accepted.
        """
        return TncConfig(
            port_name  = self._port_combo.currentText(),
            baudrate   = self._baud_combo.currentData(),
            rtscts     = self._rtscts_cb.isChecked(),
            host_mode_on_exit = self._hm_exit_cb.isChecked(),
            fast_init  = self._fast_init_cb.isChecked(),
        )
