"""
amtor_screen.py – AMTOR Opmode-Screen (ARQ Mode A / FEC Mode B)

Buttons gemäß PPWIN-Dokumentation:

  Modus-Buttons (checkable, bleiben gedrückt, gegenseitig exklusiv):
    ARQ           – öffnet ARQ-Dialog mit Stationsliste; bleibt gedrückt im ARQ-Modus
    FEC           – FEC-Broadcast (CQ / Roundtable); bleibt gedrückt beim Senden
    SELFEC        – Selektiver FEC; bleibt gedrückt beim Senden
    ALIST         – AMTOR Listen-Modus; bleibt gedrückt
    Pactor Listen – Wechsel zu PACTOR Listen-Modus

  Einmal-Buttons (Aktionen):
    STBY      – TNC zurück auf AMTOR Standby
    ACHG      – ARQ Link übernehmen (ACHG-Befehl)
    HOLD      – TX-Buffer halten / freigeben (Toggle)

  Toggle-Buttons (ON/OFF):
    ARXTOR      – Auto-Erkennung AMTOR/PACTOR
    RXREV       – RX-Polarität umkehren
    TXREV       – TX-Polarität umkehren
    RFEC        – FEC im ARQ-Standby empfangen
    SRXALL      – alle SELFEC empfangen
    EAS         – Echo As Sent

  Aktions-Buttons (Einmal-Befehl, kein Toggle):
    Switch figs – Ziffern-Zeichensatz erzwingen (FIGS / ITA-2)
    Switch char – Buchstaben-Zeichensatz erzwingen (LTRS / ITA-2)

Standalone-Test: python amtor_screen.py
"""

import sys
from datetime import datetime, timezone
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QLineEdit, QPushButton,
    QFrame, QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont

from .opmode_rtty_base import (
    MacroStore, MacroEditDialog, TxInputWidget,
    make_toggle_button, make_help_button, add_hline, apply_app_style,
    apply_macro_tooltips,
    style_rx_widget, style_tx_widget,
    BTN_W, SPACING, MACRO_COUNT,
)
from .screen_focus_controller import is_keyboard_input_widget


# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

SELCAL_W = 65    # Breite SELCAL-Feld (4–7 Zeichen Courier)
IDENT_W  = 85    # Breite MYIDENT-Feld (7 Zeichen)

# Verbindungszustände
STATUS_STYLES = {
    "STBY":        ("●  STBY",          "#888888"),
    "CALLING":     ("●  CALLING …",     "#cc8800"),
    "CONNECTED":   ("●  CONNECTED",     "#3a9e3a"),
    "FEC TX":      ("●  FEC TX",        "#2266cc"),
    "SELFEC TX":   ("●  SELFEC TX",     "#2266cc"),
    "ALIST":       ("●  ALIST",         "#888888"),
    "PACTOR LST":  ("●  PACTOR LISTEN", "#555577"),
    "HOLD":        ("●  TX HOLD",       "#cc8800"),
}

# Stil: Modus-Button (checkable, bleibt gedrückt)
def _style_mode_btn(active_color: str) -> tuple[str, str]:
    """Gibt (style_off, style_on) zurück."""
    off = (
        "QPushButton {"
        "  background-color: #445566; color: white;"
        "  border: 1px solid #334455; border-radius: 4px;"
        "  font-weight: bold; padding: 4px 8px;"
        "}"
        "QPushButton:hover { background-color: #556677; }"
    )
    on = (
        f"QPushButton {{"
        f"  background-color: {active_color}; color: white;"
        f"  border: 2px solid #222; border-radius: 4px;"
        f"  font-weight: bold; padding: 4px 8px;"
        f"}}"
    )
    return off, on


# ---------------------------------------------------------------------------
# AmtorScreen
# ---------------------------------------------------------------------------

class AmtorScreen(QWidget):
    """AMTOR Opmode-Screen.

    Layout (von oben nach unten):
    ┌─────────────────────────────────────────────────────────┐
    │  AMTOR                                                  │
    ├─────────────────────────────────────────────────────────┤
    │  MYSELCAL [____]  MYALTCAL [____]  MYIDENT [_______]   │
    ├─────────────────────────────────────────────────────────┤
    │  [ARQ] Dest: [____] [FEC] [SELFEC] [ALIST] | [STBY]    │
    │  [HOLD] [ACHG]   Status: ● STBY                        │
    ├─────────────────────────────────────────────────────────┤
    │  [ARXTOR][RXREV][TXREV][NUMS][RFEC][SRXALL][EAS][WRU]  │
    ├─────────────────────────────────────────────────────────┤
    │  RX-Fenster                                             │
    ├─────────────────────────────────────────────────────────┤
    │  TX-Fenster (5 Zeilen)                                  │
    ├─────────────────────────────────────────────────────────┤
    │  [Macro 1]…[Macro 6]                    [Edit Macros]   │
    └─────────────────────────────────────────────────────────┘
    """

    # Signals connected automatically by MainWindow._wire_mode_callbacks()
    clear_tx_req = pyqtSignal()   # emitted by the "Clear TX" button
    clear_rx_req = pyqtSignal()   # emitted by the "Clear RX" button

    HELP_TOPIC = "amtor"   # F1 / ? button → help_amtor.md

    def __init__(self, parent=None):
        super().__init__(parent)
        self._macro_store = MacroStore()
        err = self._macro_store.load()
        if err:
            print(f"[MacroStore] {err}")

        # UTC-Uhr
        self._utc_timer = QTimer(self)
        self._utc_timer.setInterval(1000)
        self._utc_timer.timeout.connect(self._update_utc)
        self._utc_timer.start()

        self._build_ui()

        # ScreenFocusController: tracks focus on le_dest (editable).
        # lbl_myselcal/myaltcal/myident are QLabels — no focus tracking needed.
        from .screen_focus_controller import ScreenFocusController
        self.focus_ctrl = ScreenFocusController(
            fields=[self.le_dest],
            parent=self,
        )

        # Event-Filter: leitet Tastendrücke immer ans TX-Fenster weiter
        self.installEventFilter(self)
        # Initialer Focus: Cursor sofort ins TX-Fenster setzen
        QTimer.singleShot(0, lambda: self.tx_input.setFocus())

        # Central tooltips — applied after all widgets are built.
        # (AMTOR has no btn_wideshft/btn_mopt — those keys simply don't match.)
        from pk232py.ui.tooltips import apply_tooltips
        apply_tooltips(self)

    # ------------------------------------------------------------------
    # Event-Filter: TX-Fenster behält immer den Keyboard-Focus
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event) -> bool:
        """Jeder Tastendruck landet im TX-Fenster, egal welcher Button geklickt wurde.

        Ausnahme: Wenn der Focus bereits in einem Eingabefeld ist (QLineEdit,
        QTextEdit), wird das Event normal weitergeleitet – das würde z.B. die
        SELCAL-Felder betreffen.
        """
        from PyQt6.QtCore import QEvent
        from PyQt6.QtWidgets import QApplication
        if event.type() == QEvent.Type.KeyPress:
            # is_keyboard_input_widget() walks the parent chain and
            # covers every keyboard-input widget type (QComboBox,
            # QAbstractSpinBox too, not just QLineEdit/QTextEdit — P41).
            if (is_keyboard_input_widget(self.focusWidget())
                    or is_keyboard_input_widget(obj)):
                return super().eventFilter(obj, event)
            if hasattr(self, "tx_input") and self.tx_input is not None:
                self.tx_input.setFocus()
                QApplication.sendEvent(self.tx_input, event)
                return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(6)
        root.setContentsMargins(8, 8, 8, 8)

        # --- Titel mit UTC-Uhr rechts ------------------------------------
        title_row = QHBoxLayout()
        title = QLabel("AMTOR")
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        title_row.addWidget(title)
        title_row.addStretch()
        self.lbl_utc = QLabel()
        self.lbl_utc.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self.lbl_utc.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._update_utc()
        title_row.addWidget(self.lbl_utc)
        title_row.addWidget(make_help_button("amtor"))
        root.addLayout(title_row)

        add_hline(root)

        # --- Identität: alle drei Felder in einer Zeile ------------------
        id_row = QHBoxLayout()
        id_row.setSpacing(10)

        id_row.addWidget(_field_label("MYSELCAL:"))
        self.lbl_myselcal = QLabel("---")
        self.lbl_myselcal.setFixedWidth(SELCAL_W)
        self.lbl_myselcal.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self.lbl_myselcal.setToolTip("MYSELCAL — set via TNC \u2192 AMTOR Parameters.")
        id_row.addWidget(self.lbl_myselcal)

        id_row.addSpacing(6)
        id_row.addWidget(_field_label("MYALTCAL:"))
        self.lbl_myaltcal = QLabel("---")
        self.lbl_myaltcal.setFixedWidth(SELCAL_W)
        self.lbl_myaltcal.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self.lbl_myaltcal.setToolTip("MYALTCAL — set via TNC \u2192 AMTOR Parameters.")
        id_row.addWidget(self.lbl_myaltcal)

        id_row.addSpacing(6)
        id_row.addWidget(_field_label("MYIDENT:"))
        self.lbl_myident = QLabel("---")
        self.lbl_myident.setFixedWidth(IDENT_W)
        self.lbl_myident.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self.lbl_myident.setToolTip("MYIDENT — set via TNC \u2192 AMTOR Parameters.")
        id_row.addWidget(self.lbl_myident)

        id_row.addStretch()
        root.addLayout(id_row)

        add_hline(root)

        # --- Modus-Buttons Zeile 1 ----------------------------------------
        #  [ARQ] Dest:[____]  [FEC]  [SELFEC]  [ALIST]  |  [STBY]
        mode_row = QHBoxLayout()
        mode_row.setSpacing(6)

        # ARQ – checkable, bleibt gedrückt im ARQ-Modus
        self.btn_arq = _make_mode_button("ARQ", 60, "#3a7a3a")
        self.btn_arq.toggled.connect(
            lambda on: self._on_mode_toggled(self.btn_arq, on, "CONNECTED", "#3a7a3a")
        )
        mode_row.addWidget(self.btn_arq)

        mode_row.addWidget(QLabel("Dest:"))
        self.le_dest = _make_selcal(7, SELCAL_W + 10, "Target SELCAL")
        mode_row.addWidget(self.le_dest)

        mode_row.addSpacing(4)

        # FEC
        self.btn_fec = _make_mode_button("FEC", 55, "#2255aa")
        self.btn_fec.toggled.connect(
            lambda on: self._on_mode_toggled(self.btn_fec, on, "FEC TX", "#2255aa")
        )
        mode_row.addWidget(self.btn_fec)

        # SELFEC
        self.btn_selfec = _make_mode_button("SELFEC", 65, "#2255aa")
        self.btn_selfec.toggled.connect(
            lambda on: self._on_mode_toggled(self.btn_selfec, on, "SELFEC TX", "#2255aa")
        )
        mode_row.addWidget(self.btn_selfec)

        # ALIST
        self.btn_alist = _make_mode_button("ALIST", 60, "#666633")
        self.btn_alist.toggled.connect(
            lambda on: self._on_mode_toggled(self.btn_alist, on, "ALIST", "#666633")
        )
        mode_row.addWidget(self.btn_alist)

        # PACTOR Listen – einzeilig
        self.btn_pactor_listen = _make_mode_button("Pactor Listen", 90, "#555566")
        self.btn_pactor_listen.toggled.connect(
            lambda on: self._on_mode_toggled(
                self.btn_pactor_listen, on, "PACTOR LST", "#555566"
            )
        )
        mode_row.addWidget(self.btn_pactor_listen)

        # Trennlinie
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        mode_row.addWidget(sep)

        # STBY – Einmal-Button, setzt alles zurück
        self.btn_stby = QPushButton("STBY")
        self.btn_stby.setFixedWidth(55)
        self.btn_stby.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_stby.setStyleSheet(
            "QPushButton { background-color: #555; color: #ccc;"
            " border: 1px solid #444; border-radius: 4px; padding: 4px; }"
            "QPushButton:hover { background-color: #666; }"
        )
        self.btn_stby.clicked.connect(self._on_stby)
        mode_row.addWidget(self.btn_stby)

        mode_row.addStretch()
        root.addLayout(mode_row)

        # --- Modus-Buttons Zeile 2 ----------------------------------------
        #  [HOLD]  [ACHG]   Status: ● STBY
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(6)

        # HOLD – Toggle (TX-Buffer halten)
        self.btn_hold = make_toggle_button("HOLD")
        ctrl_row.addWidget(self.btn_hold)

        # ACHG – Einmal-Button (Link übernehmen)
        self.btn_achg = QPushButton("ACHG")
        self.btn_achg.setFixedWidth(BTN_W)
        self.btn_achg.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_achg.setToolTip("Take over the ARQ link (break-in)")
        self.btn_achg.setStyleSheet(
            "QPushButton { background-color: #664422; color: white;"
            " border: 1px solid #553311; border-radius: 4px; padding: 4px; }"
            "QPushButton:hover { background-color: #775533; }"
        )
        ctrl_row.addWidget(self.btn_achg)

        # Status-Label
        ctrl_row.addSpacing(12)
        self.lbl_status = QLabel("●  STBY")
        self.lbl_status.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.lbl_status.setStyleSheet("color: #888888;")
        ctrl_row.addWidget(self.lbl_status)

        ctrl_row.addStretch()
        root.addLayout(ctrl_row)

        add_hline(root)

        # --- Toggle-Buttons -----------------------------------------------
        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(SPACING)

        self.btn_arxtor    = make_toggle_button("ARXTOR")
        self.btn_rxrev     = make_toggle_button("RxRev")
        self.btn_txrev     = make_toggle_button("TxRev")
        self.btn_rfec      = make_toggle_button("RFEC")
        self.btn_srxall    = make_toggle_button("SRxAll")
        self.btn_eas       = make_toggle_button("EAS")

        # Switch figs / Switch char: Aktions-Buttons (kein Toggle),
        # identisch zu Baudot-Screen — erzwingen FIGS bzw. LTRS-Zeichensatz
        self.btn_figs  = QPushButton("Switch figs")
        self.btn_chars = QPushButton("Switch char")
        for b in (self.btn_figs, self.btn_chars):
            b.setFixedWidth(BTN_W)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        for b in (
            self.btn_arxtor, self.btn_rxrev, self.btn_txrev,
            self.btn_rfec, self.btn_srxall, self.btn_eas,
            self.btn_figs, self.btn_chars,
        ):
            toggle_row.addWidget(b)

        toggle_row.addStretch()
        root.addLayout(toggle_row)

        add_hline(root)

        # --- RX-Fenster ---------------------------------------------------
        self.rx_display = QTextEdit()
        self.rx_display.setReadOnly(True)
        self.rx_display.setFont(QFont("Courier New", 10))
        self.rx_display.setPlaceholderText("RX – received characters appear here …")
        style_rx_widget(self.rx_display)
        self.rx_display.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        root.addWidget(self.rx_display, stretch=1)

        add_hline(root)

        # --- TX-Fenster (5 Zeilen) — TxInputWidget für char-level ACK-Tracking
        # Wie Baudot/ASCII/Morse: liefert char_typed, [^D]-Erkennung,
        # colour_at() und Edit-Schutz. Ersetzt das frühere einfache QTextEdit
        # (Legacy char_ready-Pfad), damit AMTOR den TxController nutzen kann.
        # [^D] bei AMTOR-ARQ → PTOVER-Zeichen (\x1A) in den leeren Puffer;
        # bei AMTOR-FEC → RC (wie Baudot/Morse). Entscheidung in _on_baudot_eot.
        self.tx_input = TxInputWidget()
        self.tx_input.setFont(QFont("Courier New", 10))
        self.tx_input.setPlaceholderText(
            "TX – type here …  (ITA-2: UPPERCASE only)"
        )
        style_tx_widget(self.tx_input)
        fm = self.tx_input.fontMetrics()
        mc = self.tx_input.contentsMargins()
        self.tx_input.setFixedHeight(fm.lineSpacing() * 5 + mc.top() + mc.bottom() + 8)
        root.addWidget(self.tx_input)

        add_hline(root)

        # --- Macro-Sektion ------------------------------------------------
        macro_row = QHBoxLayout()
        macro_row.setSpacing(SPACING)

        self.macro_buttons: list[QPushButton] = []
        for i in range(MACRO_COUNT):
            btn = QPushButton(self._macro_store.names[i])
            btn.setFixedWidth(BTN_W)
            macro_row.addWidget(btn)
            self.macro_buttons.append(btn)

        apply_macro_tooltips(self.macro_buttons, self._macro_store)

        macro_row.addStretch()

        # Clear TX / Clear RX — emit signals; MainWindow does the actual work.
        # NoFocus so a mouse click never steals keyboard focus from TX window.
        self.btn_clear_tx = QPushButton("Clear TX")
        self.btn_clear_tx.setFixedWidth(BTN_W)
        self.btn_clear_tx.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_clear_tx.clicked.connect(self.clear_tx_req.emit)
        macro_row.addWidget(self.btn_clear_tx)

        self.btn_clear_rx = QPushButton("Clear RX")
        self.btn_clear_rx.setFixedWidth(BTN_W)
        self.btn_clear_rx.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_clear_rx.clicked.connect(self.clear_rx_req.emit)
        macro_row.addWidget(self.btn_clear_rx)

        self.btn_edit_macros = QPushButton("Edit Macros")
        self.btn_edit_macros.setFixedWidth(BTN_W + 20)
        self.btn_edit_macros.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # No stylesheet → palette-driven, readable in every theme.
        self.btn_edit_macros.clicked.connect(self._on_edit_macros)
        macro_row.addWidget(self.btn_edit_macros)
        root.addLayout(macro_row)

    # ------------------------------------------------------------------
    # Modus-Button Logik
    # ------------------------------------------------------------------

    # Alle Modus-Buttons in einer Liste für gegenseitiges Ausschalten
    @property
    def _mode_buttons(self) -> list[QPushButton]:
        return [self.btn_arq, self.btn_fec, self.btn_selfec, self.btn_alist,
                self.btn_pactor_listen]

    def _on_mode_toggled(
        self, sender: QPushButton, checked: bool,
        status_key: str, active_color: str
    ) -> None:
        """Stellt sicher dass immer nur ein Modus-Button aktiv ist."""
        style_off, style_on = _style_mode_btn(active_color)
        if checked:
            # Alle anderen Modus-Buttons ausschalten
            for btn in self._mode_buttons:
                if btn is not sender:
                    btn.blockSignals(True)
                    btn.setChecked(False)
                    btn.blockSignals(False)
                    # Stil zurücksetzen
                    btn.setStyleSheet(_style_mode_btn("#445566")[0])
            sender.setStyleSheet(style_on)
            self._set_status(status_key)
        else:
            sender.setStyleSheet(style_off)
            self._set_status("STBY")

    def _on_stby(self) -> None:
        """Alle Modus-Buttons ausschalten, Status auf STBY."""
        for btn in self._mode_buttons:
            btn.blockSignals(True)
            btn.setChecked(False)
            btn.blockSignals(False)
            btn.setStyleSheet(_style_mode_btn("#445566")[0])
        self._set_status("STBY")

    # ------------------------------------------------------------------
    # Status-Label
    # ------------------------------------------------------------------

    def _set_status(self, state: str) -> None:
        text, color = STATUS_STYLES.get(state, (f"●  {state}", "#888888"))
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet(
            f"color: {color}; font-weight: bold; font-size: 10pt;"
        )

    # ------------------------------------------------------------------
    # Macros
    # ------------------------------------------------------------------

    def _on_edit_macros(self) -> None:
        dlg = MacroEditDialog(self._macro_store, parent=self)
        dlg.exec()
        for i, btn in enumerate(self.macro_buttons):
            btn.setText(self._macro_store.names[i])
        apply_macro_tooltips(self.macro_buttons, self._macro_store)

    def _update_utc(self) -> None:
        """Aktualisiert das UTC-Zeit-Label auf die aktuelle Sekunde."""
        now = datetime.now(timezone.utc)
        self.lbl_utc.setText(now.strftime("UTC  %H:%M:%S"))


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _field_label(text: str) -> QLabel:
    """Rechtsbündiges Bezeichner-Label."""
    lbl = QLabel(text)
    lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
    lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return lbl


def _make_selcal(max_len: int, width: int, placeholder: str = "") -> QLineEdit:
    """Editable input field for SELCAL / IDENT (e.g. le_dest)."""
    le = QLineEdit()
    le.setMaxLength(max_len)
    le.setFixedWidth(width)
    le.setFont(QFont("Courier New", 10))
    le.setPlaceholderText(placeholder)
    return le





def _make_mode_button(label: str, width: int, active_color: str) -> QPushButton:
    """Checkable Modus-Button (bleibt gedrückt solange Modus aktiv).

    NoFocus: kein Focus-Raub durch Mausklick.
    """
    style_off, _ = _style_mode_btn(active_color)
    btn = QPushButton(label)
    btn.setFixedWidth(width)
    btn.setCheckable(True)
    btn.setChecked(False)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)   # kein Focus-Raub
    btn.setStyleSheet(style_off)
    return btn


# ---------------------------------------------------------------------------
# Standalone-Test
# ---------------------------------------------------------------------------

class _TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PK232PY – AMTOR Screen (Test)")
        self.resize(820, 640)
        self.setCentralWidget(AmtorScreen())


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
