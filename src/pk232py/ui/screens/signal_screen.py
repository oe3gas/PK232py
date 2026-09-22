"""
signal_screen.py – Signal Analysis (SIAM) Opmode-Screen

SIAM = Signal Identification and Acquisition Mode

Der PK-232 analysiert ein empfangenes Signal und erkennt:
  - Baudrate (mit Konfidenzwert 0.00–1.00)
  - Betriebsart: Baudot, ASCII, AMTOR ARQ, AMTOR FEC, TDM, Unknown, Noise
  - RXREV-Empfehlung (ON/OFF)

Typisches Ergebnis-Format vom TNC:
  "0.47: 50 Baud, Baudot, RXREV OFF"

Workflow:
  1. Empfänger auf LSB/FSK einstellen
  2. Signal suchen, Abstimmindikator beobachten
  3. SIGNAL-Befehl absetzen (= diesen Screen aufrufen)
  4. TNC analysiert ~15 Sekunden
  5. Ergebnis erscheint im Ergebnisfeld
  6. [OK] → TNC wechselt in erkannte Betriebsart
  7. [Neu] → neue Analyse starten
  8. [Wide Shift] → für breitbandige Signale (>200 Hz Shift)

Nur Empfang — kein TX, keine Macros.

Standalone-Test: python signal_screen.py
"""

import sys
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QPushButton, QSpinBox,
    QFrame, QSizePolicy, QGroupBox,
    QProgressBar,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor

from .opmode_rtty_base import (
    make_toggle_button, make_help_button, add_hline, apply_app_style,
    style_rx_widget,
    BTN_W, SPACING,
)

if TYPE_CHECKING:
    # Screens don't import modes/ at runtime (see the other screens) -
    # this is a type hint only, for on_mode_result() below.
    from pk232py.modes.signal_analysis import SiamResult


# ---------------------------------------------------------------------------
# Erkennbare Betriebsarten (SIAM-Ausgabe des TNC)
# ---------------------------------------------------------------------------

KNOWN_MODES = [
    "Baudot",
    "ASCII",
    "AMTOR ARQ",
    "AMTOR FEC",
    "TDM",
    "Unknown",
    "Noise",
    "6-Bit",
]

# Farben für Konfidenz-Anzeige
def _confidence_color(value: float) -> str:
    """Gibt eine Farbe abhängig vom Konfidenzwert zurück."""
    if value >= 0.7:
        return "#3a9e3a"   # grün
    if value >= 0.4:
        return "#cc8800"   # orange
    return "#cc3333"       # rot


# ---------------------------------------------------------------------------
# SignalScreen
# ---------------------------------------------------------------------------

class SignalScreen(QWidget):
    """Signal Analysis (SIAM) Screen — nur Empfang, keine Macros.

    Layout (von oben nach unten):
    ┌──────────────────────────────────────────────────────┐
    │  Signal / SIAM                       UTC  HH:MM:SS  │
    ├──────────────────────────────────────────────────────┤
    │  Info: Passiver Analysemodus                         │
    ├──────────────────────────────────────────────────────┤
    │  ┌─ Analyse-Parameter ─────────────────────────────┐ │
    │  │  SAMPLE: [-][ 0 ][+]   [Wide Shift]             │ │
    │  └─────────────────────────────────────────────────┘ │
    ├──────────────────────────────────────────────────────┤
    │  ┌─ Analyse-Ergebnis ──────────────────────────────┐ │
    │  │  Konfidenz:  ████████░░  0.47                   │ │
    │  │  Baudrate:   50 Baud                            │ │
    │  │  Betriebsart: Baudot                            │ │
    │  │  RXREV:      OFF                                │ │
    │  │                                                 │ │
    │  │  [  OK – In erkannte Betriebsart wechseln  ]   │ │
    │  └─────────────────────────────────────────────────┘ │
    ├──────────────────────────────────────────────────────┤
    │  Analyse-Steuerung: [Neue Analyse]  [Abbrechen]      │
    ├──────────────────────────────────────────────────────┤
    │  Analyse-Log (Verlauf aller Ergebnisse)              │
    └──────────────────────────────────────────────────────┘
    """

    HELP_TOPIC = "signal"   # F1 / ? button → help_signal.md

    def __init__(self, parent=None):
        super().__init__(parent)

        self._utc_timer = QTimer(self)
        self._utc_timer.setInterval(1000)
        self._utc_timer.timeout.connect(self._update_utc)
        self._utc_timer.start()

        # Simulierter Analyse-Timer (nur für Mockup-Demo)
        self._analyse_timer = QTimer(self)
        self._analyse_timer.setSingleShot(True)
        self._analyse_timer.setInterval(3000)   # 3 Sek. Demo-Verzögerung
        self._analyse_timer.timeout.connect(self._on_analyse_complete_demo)

        # Highest confidence seen so far this session (P19.4) — the TNC
        # analyses continuously (~10s cadence), so "sicherstes Ergebnis"
        # tracks across results, not just the latest one. Reset by
        # New Analysis / Cancel, NOT by every incoming result.
        self._best_confidence: Optional[float] = None

        self._build_ui()

        # Central tooltips — applied after all widgets are built.
        from pk232py.ui.tooltips import apply_tooltips
        apply_tooltips(self)

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(6)
        root.setContentsMargins(8, 8, 8, 8)

        # --- Titelzeile --------------------------------------------------
        title_row = QHBoxLayout()
        title = QLabel("Signal / SIAM")
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        title_row.addWidget(title)
        title_row.addStretch()
        self.lbl_utc = QLabel()
        self.lbl_utc.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self.lbl_utc.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._update_utc()
        title_row.addWidget(self.lbl_utc)
        title_row.addWidget(make_help_button("signal"))
        root.addLayout(title_row)

        add_hline(root)

        # --- Info-Zeile --------------------------------------------------
        info_row = QHBoxLayout()
        info_row.setSpacing(20)
        for text in (
            "Passive analysis mode",
            "No TX",
            "Tune the signal to LSB/FSK",
            "DCD LED must be lit",
        ):
            lbl = QLabel(text)
            lbl.setFont(QFont("Segoe UI", 9))
            lbl.setStyleSheet("color: #8aaccc;")
            info_row.addWidget(lbl)
        info_row.addStretch()
        root.addLayout(info_row)

        add_hline(root)

        # --- Parameter-Box -----------------------------------------------
        param_box = QGroupBox("Analysis Parameters")
        param_box.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        param_layout = QHBoxLayout(param_box)
        param_layout.setSpacing(8)

        # SAMPLE SpinBox
        param_layout.addWidget(_field_label("SAMPLE:"))

        self.btn_sample_down = _small_btn("−")
        param_layout.addWidget(self.btn_sample_down)

        self.sb_sample = QSpinBox()
        self.sb_sample.setRange(0, 65535)
        self.sb_sample.setValue(0)
        self.sb_sample.setFont(QFont("Courier New", 10))
        self.sb_sample.setFixedWidth(70)
        self.sb_sample.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sb_sample.setSpecialValueText("Default")
        self.sb_sample.setToolTip(
            "Number of analysis samples.\n"
            "0 = use the TNC default.\n"
            "Higher values = longer, more accurate analysis."
        )
        param_layout.addWidget(self.sb_sample)

        self.btn_sample_up = _small_btn("+")
        param_layout.addWidget(self.btn_sample_up)

        self.btn_sample_down.clicked.connect(
            lambda: self.sb_sample.setValue(self.sb_sample.value() - 1)
        )
        self.btn_sample_up.clicked.connect(
            lambda: self.sb_sample.setValue(self.sb_sample.value() + 1)
        )

        param_layout.addSpacing(20)

        # Wide Shift Toggle
        self.btn_wideshft = make_toggle_button("Wide Shift")
        self.btn_wideshft.setToolTip(
            "WIDESHFT ON: filter for signals >200 Hz shift\n"
            "(commercial stations outside the amateur bands)\n\n"
            "WIDESHFT OFF: for 170/200 Hz shift\n"
            "(amateur-radio standard)"
        )
        param_layout.addWidget(self.btn_wideshft)

        param_layout.addStretch()
        root.addWidget(param_box)

        add_hline(root)

        # --- Ergebnis-Box ------------------------------------------------
        result_box = QGroupBox("Analysis Result")
        result_box.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        result_layout = QVBoxLayout(result_box)
        result_layout.setSpacing(6)

        # Konfidenz-Anzeige
        conf_row = QHBoxLayout()
        conf_row.addWidget(_field_label("Konfidenz:"))
        self.progress_conf = QProgressBar()
        self.progress_conf.setRange(0, 100)
        self.progress_conf.setValue(0)
        self.progress_conf.setFixedHeight(18)
        self.progress_conf.setFixedWidth(200)
        self.progress_conf.setTextVisible(False)
        conf_row.addWidget(self.progress_conf)
        self.lbl_conf_val = QLabel("–")
        self.lbl_conf_val.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self.lbl_conf_val.setFixedWidth(40)
        conf_row.addWidget(self.lbl_conf_val)
        conf_row.addStretch()
        result_layout.addLayout(conf_row)

        # Baudrate
        baud_row = QHBoxLayout()
        baud_row.addWidget(_field_label("Baudrate:"))
        self.lbl_baud = QLabel("–")
        self.lbl_baud.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        baud_row.addWidget(self.lbl_baud)
        baud_row.addStretch()
        result_layout.addLayout(baud_row)

        # Erkannte Betriebsart
        mode_row = QHBoxLayout()
        mode_row.addWidget(_field_label("Mode:"))
        self.lbl_mode = QLabel("–")
        self.lbl_mode.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        mode_row.addWidget(self.lbl_mode)
        mode_row.addStretch()
        result_layout.addLayout(mode_row)

        # RXREV-Empfehlung
        rxrev_row = QHBoxLayout()
        rxrev_row.addWidget(_field_label("RXREV:"))
        self.lbl_rxrev = QLabel("–")
        self.lbl_rxrev.setFont(QFont("Courier New", 10))
        rxrev_row.addWidget(self.lbl_rxrev)
        rxrev_row.addStretch()
        result_layout.addLayout(rxrev_row)

        # Rohtext vom TNC
        raw_row = QHBoxLayout()
        raw_row.addWidget(_field_label("TNC-Text:"))
        self.lbl_raw = QLabel("–")
        self.lbl_raw.setFont(QFont("Courier New", 9))
        self.lbl_raw.setStyleSheet("color: #7090a8;")
        raw_row.addWidget(self.lbl_raw)
        raw_row.addStretch()
        result_layout.addLayout(raw_row)

        # Bisher sicherstes Ergebnis (P19.4 — TNC analysiert fortlaufend,
        # etwa alle 10 s ein neues Ergebnis; dies ist die höchste Konfidenz
        # seit der letzten New Analysis / dem letzten Cancel)
        best_row = QHBoxLayout()
        best_row.addWidget(_field_label("Best so far:"))
        self.lbl_best = QLabel("–")
        self.lbl_best.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self.lbl_best.setStyleSheet("color: #ffcc66;")
        best_row.addWidget(self.lbl_best)
        best_row.addStretch()
        result_layout.addLayout(best_row)

        # Trennlinie + OK-Button
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        result_layout.addWidget(sep)

        ok_row = QHBoxLayout()
        self.btn_ok = QPushButton("OK  –  Switch to the detected mode")
        self.btn_ok.setFixedHeight(36)
        self.btn_ok.setEnabled(False)   # erst nach Analyse aktivieren
        self.btn_ok.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_ok.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.btn_ok.setStyleSheet(
            "QPushButton {"
            "  background-color: #2a5a3a; color: #88ddaa;"
            "  border: 1px solid #3a7a4a; border-radius: 4px;"
            "}"
            "QPushButton:hover { background-color: #336644; }"
            "QPushButton:disabled {"
            "  background-color: #333; color: #555;"
            "  border: 1px solid #444;"
            "}"
        )
        ok_row.addWidget(self.btn_ok)
        result_layout.addLayout(ok_row)

        root.addWidget(result_box)

        add_hline(root)

        # --- Analyse-Steuerung -------------------------------------------
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(8)

        self.btn_neue_analyse = QPushButton("▶  New Analysis")
        self.btn_neue_analyse.setFixedWidth(140)
        self.btn_neue_analyse.setFixedHeight(34)
        self.btn_neue_analyse.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_neue_analyse.setFont(QFont("Segoe UI", 9))
        self.btn_neue_analyse.setStyleSheet(
            "QPushButton {"
            "  background-color: #2a4a6a; color: #88aadd;"
            "  border: 1px solid #3a5a7a; border-radius: 4px;"
            "}"
            "QPushButton:hover { background-color: #335577; }"
        )
        self.btn_neue_analyse.clicked.connect(self._on_neue_analyse)
        ctrl_row.addWidget(self.btn_neue_analyse)

        self.btn_abbrechen = QPushButton("■  Cancel")
        self.btn_abbrechen.setFixedWidth(120)
        self.btn_abbrechen.setFixedHeight(34)
        self.btn_abbrechen.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_abbrechen.setFont(QFont("Segoe UI", 9))
        self.btn_abbrechen.setEnabled(False)
        self.btn_abbrechen.setStyleSheet(
            "QPushButton {"
            "  background-color: #5a2a2a; color: #ddaaaa;"
            "  border: 1px solid #7a3a3a; border-radius: 4px;"
            "}"
            "QPushButton:hover { background-color: #6a3333; }"
            "QPushButton:disabled { background-color: #333; color: #555; border: 1px solid #444; }"
        )
        self.btn_abbrechen.clicked.connect(self._on_abbrechen)
        ctrl_row.addWidget(self.btn_abbrechen)

        # Status-Label
        self.lbl_analyse_status = QLabel("Ready.")
        self.lbl_analyse_status.setFont(QFont("Segoe UI", 9))
        self.lbl_analyse_status.setStyleSheet("color: #607080;")
        ctrl_row.addWidget(self.lbl_analyse_status)

        ctrl_row.addStretch()
        root.addLayout(ctrl_row)

        add_hline(root)

        # --- Analyse-Log (Verlauf) ----------------------------------------
        log_label = QLabel("Analysis Log:")
        log_label.setFont(QFont("Segoe UI", 9))
        root.addWidget(log_label)

        self.rx_log = QTextEdit()
        self.rx_log.setReadOnly(True)
        self.rx_log.setFont(QFont("Courier New", 9))
        style_rx_widget(self.rx_log)
        self.rx_log.setPlaceholderText(
            "Analysis results appear here …\n\n"
            "Example:\n"
            "14:23:11  0.47: 50 Baud, Baudot, RXREV OFF\n"
            "14:24:05  0.92: 100 Baud, Baudot, RXREV OFF\n"
            "14:25:18  0.15: Unknown"
        )
        self.rx_log.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        root.addWidget(self.rx_log, stretch=1)

        # Clear-RX row — receive-only screen clears itself.
        clear_row = QHBoxLayout()
        clear_row.addStretch()
        self.btn_clear_rx = QPushButton("Clear RX")
        self.btn_clear_rx.setFixedWidth(BTN_W)
        self.btn_clear_rx.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_clear_rx.clicked.connect(self._on_clear_rx)
        clear_row.addWidget(self.btn_clear_rx)
        root.addLayout(clear_row)

    def _on_clear_rx(self) -> None:
        """Clear the SIAM analysis log (receive-only, local state)."""
        self.rx_log.clear()

    # ------------------------------------------------------------------
    # Analyse-Steuerung
    # ------------------------------------------------------------------

    def _on_neue_analyse(self) -> None:
        """Startet eine neue SIAM-Analyse."""
        self._reset_result()
        self.btn_neue_analyse.setEnabled(False)
        self.btn_abbrechen.setEnabled(True)
        self.btn_ok.setEnabled(False)
        self.lbl_analyse_status.setStyleSheet("color: #cc8800; font-weight: bold;")
        self.lbl_analyse_status.setText("⏳  Analysis running …  (approx. 15 s)")
        # Mockup-Demo: nach 3 Sek. ein simuliertes Ergebnis anzeigen
        self._analyse_timer.start()

    def _on_abbrechen(self) -> None:
        """Bricht eine laufende Analyse ab."""
        self._analyse_timer.stop()
        self.btn_neue_analyse.setEnabled(True)
        self.btn_abbrechen.setEnabled(False)
        self.lbl_analyse_status.setStyleSheet("color: #607080;")
        self.lbl_analyse_status.setText("Cancelled.")
        self._reset_result()

    def _on_analyse_complete_demo(self) -> None:
        """Simuliertes Analyse-Ergebnis (Mockup-Demo)."""
        # Beispiel-Ergebnis wie TNC es liefern würde
        self._show_result("0.47", "50 Baud", "Baudot", "OFF",
                          "0.47: 50 Baud, Baudot, RXREV OFF")

    def on_mode_result(self, result: "SiamResult") -> None:
        """Live SIAM result from SignalMode.on_result_parsed (P19.4),
        wired by MainWindow._wire_mode_callbacks(). Feeds the same
        display path as the demo timer (_show_result()) — the TNC
        analyses continuously (~10s cadence, T113), so this fires
        repeatedly for one Signal/SIAM session, not just once.
        """
        self._show_result(
            f"{result.confidence:.2f}",
            f"{result.baud} Baud",
            result.mode,
            "ON" if result.rxrev else "OFF",
            result.raw,
        )

    def _show_result(
        self,
        confidence: str,
        baud: str,
        mode: str,
        rxrev: str,
        raw: str,
    ) -> None:
        """Zeigt ein Analyse-Ergebnis an."""
        conf_float = float(confidence)
        color = _confidence_color(conf_float)

        # Bisher sicherstes Ergebnis (P19.4) — nur bei einer NEUEN
        # Bestmarke aktualisieren, nicht bei jedem Ergebnis.
        if self._best_confidence is None or conf_float > self._best_confidence:
            self._best_confidence = conf_float
            self.lbl_best.setText(f"{confidence}: {baud}, {mode}, RXREV {rxrev}")
            self.lbl_best.setStyleSheet(f"color: {color}; font-weight: bold;")

        # Konfidenz-Balken
        self.progress_conf.setValue(int(conf_float * 100))
        self.progress_conf.setStyleSheet(
            f"QProgressBar::chunk {{ background-color: {color}; }}"
        )
        self.lbl_conf_val.setText(confidence)
        self.lbl_conf_val.setStyleSheet(f"color: {color}; font-weight: bold;")

        # Felder befüllen
        self.lbl_baud.setText(baud)
        self.lbl_mode.setText(mode)
        self.lbl_mode.setStyleSheet(
            "color: #d0e4f4; font-weight: bold; font-size: 11pt;"
            if mode not in ("Unknown", "Noise", "6-Bit")
            else "color: #cc8800; font-weight: bold;"
        )
        self.lbl_rxrev.setText(rxrev)
        self.lbl_raw.setText(raw)

        # OK-Button nur aktivieren wenn Modus erkannt und wechselbar
        can_switch = mode not in ("Unknown", "Noise", "6-Bit")
        self.btn_ok.setEnabled(can_switch)
        if can_switch:
            self.btn_ok.setText(f"OK  –  Switch to {mode}")
        else:
            self.btn_ok.setText("OK  –  Mode not recognised (no switch possible)")

        # Log-Eintrag
        now = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self.rx_log.append(f"{now}  {raw}")

        # Steuerung zurücksetzen
        self.btn_neue_analyse.setEnabled(True)
        self.btn_abbrechen.setEnabled(False)
        self.lbl_analyse_status.setStyleSheet("color: #3a9e3a; font-weight: bold;")
        self.lbl_analyse_status.setText("✓  Analysis complete.")

    def _reset_result(self) -> None:
        """Leert alle Ergebnis-Felder."""
        self.progress_conf.setValue(0)
        self.progress_conf.setStyleSheet("")
        self.lbl_conf_val.setText("–")
        self.lbl_conf_val.setStyleSheet("")
        self.lbl_baud.setText("–")
        self.lbl_mode.setText("–")
        self.lbl_mode.setStyleSheet("")
        self.lbl_rxrev.setText("–")
        self.lbl_raw.setText("–")
        self._best_confidence = None
        self.lbl_best.setText("–")
        self.lbl_best.setStyleSheet("color: #ffcc66;")
        self.btn_ok.setEnabled(False)
        self.btn_ok.setText("OK  –  Switch to the detected mode")

    # ------------------------------------------------------------------
    # UTC
    # ------------------------------------------------------------------

    def _update_utc(self) -> None:
        now = datetime.now(timezone.utc)
        self.lbl_utc.setText(now.strftime("UTC  %H:%M:%S"))


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _field_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setFixedWidth(90)
    lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
    lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return lbl


def _small_btn(text: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # kein Focus-Raub
    btn.setFixedWidth(26)
    btn.setFixedHeight(24)
    btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
    btn.setStyleSheet(
        "QPushButton { background-color: #445566; color: white;"
        " border: 1px solid #334455; border-radius: 3px; }"
        "QPushButton:hover { background-color: #556677; }"
        "QPushButton:pressed { background-color: #334455; }"
    )
    return btn


# ---------------------------------------------------------------------------
# Standalone-Test
# ---------------------------------------------------------------------------

class _TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PK232PY – Signal / SIAM Screen (Test)")
        self.resize(700, 680)
        self.setCentralWidget(SignalScreen())


def main() -> None:
    # Theme aus Kommandozeilenargument lesen (vom Launcher übergeben)
    theme = "dark"
    for arg in sys.argv[1:]:
        if arg.startswith("--theme="):
            theme = arg.split("=", 1)[1]
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    apply_app_style(app, theme)
    win = _TestWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
