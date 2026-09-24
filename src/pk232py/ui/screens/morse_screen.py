"""
morse_screen.py – CW/Morse Opmode-Screen

Der PK-232MBX kodiert und dekodiert Morse intern.
Der Host sendet ASCII-Text, der TNC wandelt ihn in CW um.
Empfangener CW wird als dekodierter ASCII-Text zurückgeliefert.

Parameter:
  MSPEED   5–99 WPM    Sendegeschwindigkeit
  MWEIGHT  10–90       Dit/Dah-Verhältnis (10 = Standard)
  MID      0–99 min    Morse-ID-Intervall (0 = aus)

Buttons:
  Send / Receive   prominent (wie RTTY-Screens)
  LOCK             Empfangsgeschwindigkeit auf Signal einrasten
  Toggle: WORDOUT  nur ganze Wörter senden
  Toggle: MOPTT    PTT im Morse-Modus (OFF = Full Break-In)
  (EAS ist immer ON — kein Button; TX-Umfärbung erfolgt beim $2F-Echo)

Sonderzeichen (ITA-2 Morse-Kürzel, TNC-intern):
  *  oder  <  →  SK   (Ende des Kontakts)
  +           →  AR   (Ende der Nachricht)
  (           →  KN   (Nur die Gegenstation)
  =           →  BT   (Pause / Trenner)
  >  oder  %  →  KA   (Achtung)
  &           →  AS   (Bitte warten)
  !           →  SN   (Verstanden)

Standalone-Test: python morse_screen.py
"""

import sys
from datetime import datetime, timezone

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QLineEdit, QPushButton, QSpinBox,
    QFrame, QSizePolicy, QGroupBox,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont

from .opmode_rtty_base import (
    MacroStore, MacroEditDialog, TxInputWidget,
    make_toggle_button, make_help_button, add_hline, apply_app_style,
    apply_macro_tooltips,
    style_rx_widget, style_tx_widget,
    BTN_W, SPACING, MACRO_COUNT,
    STYLE_PROM_INACTIVE, STYLE_SEND_ON, STYLE_SEND_BLINK, STYLE_RECEIVE_ON,
)
from .screen_focus_controller import is_keyboard_input_widget


# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

MSPEED_MIN  =  5
MSPEED_MAX  = 99
MWEIGHT_MIN = 10
MWEIGHT_MAX = 90
MID_MIN     =  0
MID_MAX     = 99


# ---------------------------------------------------------------------------
# MorseScreen
# ---------------------------------------------------------------------------

class MorseScreen(QWidget):
    """CW/Morse Opmode-Screen.

    Layout (von oben nach unten):
    ┌────────────────────────────────────────────────────────┐
    │  CW / Morse                            UTC  HH:MM:SS  │
    ├──────────────────────────────┬─────────────────────────┤
    │  MSPEED: [-][  20 WPM][+]   │  MWEIGHT: [-][ 10][+]  │
    │  MID:    [-][   0 min][+]   │                         │
    ├──────────────────────────────┴─────────────────────────┤
    │  [ SEND (prominent) ]  [ RECEIVE (prominent) ]         │
    ├────────────────────────────────────────────────────────┤
    │  [LOCK]  [WORDOUT]  [MOPTT]                           │
    ├────────────────────────────────────────────────────────┤
    │  Sonderzeichen-Referenz (kompakt)                      │
    ├────────────────────────────────────────────────────────┤
    │  RX-Fenster                                            │
    ├────────────────────────────────────────────────────────┤
    │  TX-Fenster (5 Zeilen)                                 │
    ├────────────────────────────────────────────────────────┤
    │  [Macro 1]…[Macro 6]                    [Edit Macros]  │
    └────────────────────────────────────────────────────────┘
    """

    # Signals connected automatically by MainWindow._wire_mode_callbacks()
    clear_tx_req = pyqtSignal()   # emitted by the "Clear TX" button
    clear_rx_req = pyqtSignal()   # emitted by the "Clear RX" button

    HELP_TOPIC = "morse"   # F1 / ? button → help_morse.md

    def __init__(self, parent=None):
        super().__init__(parent)
        self._macro_store = MacroStore()
        err = self._macro_store.load()
        if err:
            print(f"[MacroStore] {err}")

        self._blink_phase = False
        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(400)
        self._blink_timer.timeout.connect(self._on_blink_tick)

        self._utc_timer = QTimer(self)
        self._utc_timer.setInterval(1000)
        self._utc_timer.timeout.connect(self._update_utc)
        self._utc_timer.start()

        self._build_ui()
        self.installEventFilter(self)
        # Initialer Focus: Cursor sofort ins TX-Fenster setzen
        QTimer.singleShot(0, lambda: self.tx_input.setFocus())

        # Central tooltips — applied after all widgets are built.
        from pk232py.ui.tooltips import apply_tooltips
        apply_tooltips(self)

    # ------------------------------------------------------------------
    # Event-Filter: TX-Fenster behält immer den Keyboard-Focus
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event) -> bool:
        """Jeder Tastendruck landet im TX-Fenster, egal welcher Button geklickt wurde."""
        from PyQt6.QtCore import QEvent
        from PyQt6.QtWidgets import QApplication
        if event.type() == QEvent.Type.KeyPress:
            # is_keyboard_input_widget() walks the parent chain and
            # covers every keyboard-input widget type, including the
            # QSpinBox speed/weight/MID fields on this screen (P41) —
            # not just QLineEdit/QTextEdit.
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

        # --- Titelzeile mit UTC ------------------------------------------
        title_row = QHBoxLayout()
        title = QLabel("CW / Morse")
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        title_row.addWidget(title)
        title_row.addStretch()
        self.lbl_utc = QLabel()
        self.lbl_utc.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self.lbl_utc.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._update_utc()
        title_row.addWidget(self.lbl_utc)
        title_row.addWidget(make_help_button("morse"))
        root.addLayout(title_row)

        add_hline(root)

        # --- Parameter-Zeile: MSPEED | MWEIGHT | MID ---------------------
        param_row = QHBoxLayout()
        param_row.setSpacing(16)

        # MSPEED
        param_row.addWidget(_param_label("MSPEED:"))
        self.btn_speed_down = _small_btn("−")
        param_row.addWidget(self.btn_speed_down)
        self.sb_mspeed = _spinbox(MSPEED_MIN, MSPEED_MAX, 20)
        self.sb_mspeed.setSuffix(" WPM")
        self.sb_mspeed.setFixedWidth(78)
        param_row.addWidget(self.sb_mspeed)
        self.btn_speed_up = _small_btn("+")
        param_row.addWidget(self.btn_speed_up)

        # +/- Buttons direkt mit SpinBox verbinden
        self.btn_speed_down.clicked.connect(
            lambda: self.sb_mspeed.setValue(self.sb_mspeed.value() - 1)
        )
        self.btn_speed_up.clicked.connect(
            lambda: self.sb_mspeed.setValue(self.sb_mspeed.value() + 1)
        )

        param_row.addSpacing(12)

        # MWEIGHT
        param_row.addWidget(_param_label("MWEIGHT:"))
        self.btn_weight_down = _small_btn("−")
        param_row.addWidget(self.btn_weight_down)
        self.sb_mweight = _spinbox(MWEIGHT_MIN, MWEIGHT_MAX, 10)
        self.sb_mweight.setFixedWidth(55)
        param_row.addWidget(self.sb_mweight)
        self.btn_weight_up = _small_btn("+")
        param_row.addWidget(self.btn_weight_up)
        self.btn_weight_down.clicked.connect(
            lambda: self.sb_mweight.setValue(self.sb_mweight.value() - 1)
        )
        self.btn_weight_up.clicked.connect(
            lambda: self.sb_mweight.setValue(self.sb_mweight.value() + 1)
        )

        param_row.addSpacing(12)

        # MID
        param_row.addWidget(_param_label("MID:"))
        self.btn_mid_down = _small_btn("−")
        param_row.addWidget(self.btn_mid_down)
        self.sb_mid = _spinbox(MID_MIN, MID_MAX, 0)
        self.sb_mid.setSuffix(" min")
        self.sb_mid.setFixedWidth(62)
        self.sb_mid.setSpecialValueText("off")   # 0 → show "off"
        param_row.addWidget(self.sb_mid)
        self.btn_mid_up = _small_btn("+")
        param_row.addWidget(self.btn_mid_up)
        self.btn_mid_down.clicked.connect(
            lambda: self.sb_mid.setValue(self.sb_mid.value() - 1)
        )
        self.btn_mid_up.clicked.connect(
            lambda: self.sb_mid.setValue(self.sb_mid.value() + 1)
        )

        param_row.addStretch()
        root.addLayout(param_row)

        add_hline(root)

        # --- SEND / RECEIVE (prominent, wie RTTY-Screens) ----------------
        # Breite: beide zusammen bündig zu den 4 Toggle-Buttons unten
        # 4 × BTN_W + 3 × SPACING
        total_toggle = 4 * BTN_W + 3 * SPACING
        prom_w = (total_toggle - SPACING) // 2

        prom_row = QHBoxLayout()
        prom_row.setSpacing(SPACING)

        self.btn_send = QPushButton("Send")
        self.btn_send.setFixedWidth(prom_w)
        self.btn_send.setFixedHeight(46)
        self.btn_send.setCheckable(True)
        self.btn_send.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_send.setStyleSheet(STYLE_PROM_INACTIVE)
        self.btn_send.toggled.connect(self._on_send_toggled)

        self.btn_receive = QPushButton("Receive")
        self.btn_receive.setFixedWidth(prom_w)
        self.btn_receive.setFixedHeight(46)
        self.btn_receive.setCheckable(True)
        self.btn_receive.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_receive.setStyleSheet(STYLE_PROM_INACTIVE)
        self.btn_receive.toggled.connect(self._on_receive_toggled)

        prom_row.addWidget(self.btn_send)
        prom_row.addWidget(self.btn_receive)
        prom_row.addStretch()
        root.addLayout(prom_row)

        # --- Toggle-Buttons ----------------------------------------------
        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(SPACING)

        # LOCK – Einmal-Aktion (kein Toggle): rastet RX-Speed auf Signal ein
        self.btn_lock = QPushButton("LOCK")
        self.btn_lock.setFixedWidth(BTN_W)
        self.btn_lock.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_lock.setToolTip(
            "Lock the receive speed to the current signal (L command)"
        )
        toggle_row.addWidget(self.btn_lock)

        self.btn_wordout = make_toggle_button("WORDOUT")
        self.btn_moptt   = make_toggle_button("MOPTT")

        # MOPTT initial ON (default laut Manual)
        self.btn_moptt.setChecked(True)

        # NB: no EAS toggle. EAS (Echo As Sent) is always ON for Morse so the
        # TX window colours at the real send moment ($2F echo). A user-facing
        # toggle would be redundant and dangerous — EAS OFF would break the
        # time-correct colouring. See TxController.set_eas_mode().
        for b in (self.btn_wordout, self.btn_moptt):
            toggle_row.addWidget(b)

        toggle_row.addStretch()
        root.addLayout(toggle_row)

        add_hline(root)

        # --- Sonderzeichen-Referenz (kompakte Info-Box) ------------------
        ref_box = QGroupBox("Special characters")
        ref_box.setFont(QFont("Segoe UI", 8))
        ref_layout = QHBoxLayout(ref_box)
        ref_layout.setSpacing(16)
        ref_layout.setContentsMargins(6, 2, 6, 2)

        pairs = [
            ("*  or  <", "SK"),
            ("+",          "AR"),
            ("(",          "KN"),
            ("=",          "BT"),
            (">  or  %", "KA"),
            ("&",          "AS"),
            ("!",          "SN"),
        ]
        mono_small = QFont("Courier New", 9)
        for symbol, prosign in pairs:
            lbl = QLabel(f"{symbol} → {prosign}")
            lbl.setFont(mono_small)
            ref_layout.addWidget(lbl)

        ref_layout.addStretch()
        root.addWidget(ref_box)

        add_hline(root)

        # --- RX-Fenster --------------------------------------------------
        self.rx_display = QTextEdit()
        self.rx_display.setReadOnly(True)
        self.rx_display.setFont(QFont("Courier New", 10))
        self.rx_display.setPlaceholderText("RX – decoded CW text appears here …")
        style_rx_widget(self.rx_display)
        self.rx_display.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        root.addWidget(self.rx_display, stretch=1)

        add_hline(root)

        # --- TX-Fenster (5 Zeilen) — TxInputWidget für char-level ACK-Tracking
        # Wie Baudot/ASCII: liefert char_typed, [^D]/[^T]-Marker-Handling,
        # Edit-Schutz und colour_at(). Ersetzt das frühere einfache QTextEdit
        # (Legacy char_ready-Pfad), damit Morse den TxController nutzen kann.
        self.tx_input = TxInputWidget()
        self.tx_input.setFont(QFont("Courier New", 10))
        self.tx_input.setPlaceholderText(
            "TX – type here …  (special chars: * = SK,  + = AR,  = = BT)"
        )
        style_tx_widget(self.tx_input)
        fm = self.tx_input.fontMetrics()
        mc = self.tx_input.contentsMargins()
        self.tx_input.setFixedHeight(fm.lineSpacing() * 5 + mc.top() + mc.bottom() + 8)
        root.addWidget(self.tx_input)

        add_hline(root)

        # --- Macro-Sektion -----------------------------------------------
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
    # Slots – SEND / RECEIVE / Blink
    # ------------------------------------------------------------------

    def _on_send_toggled(self, checked: bool) -> None:
        if checked:
            self.btn_receive.blockSignals(True)
            self.btn_receive.setChecked(False)
            self.btn_receive.blockSignals(False)
            self.btn_receive.setStyleSheet(STYLE_PROM_INACTIVE)
            self._blink_phase = True
            self.btn_send.setStyleSheet(STYLE_SEND_ON)
            self._blink_timer.start()
        else:
            self._blink_timer.stop()
            self.btn_send.setStyleSheet(STYLE_PROM_INACTIVE)

    def _on_receive_toggled(self, checked: bool) -> None:
        if checked:
            self._blink_timer.stop()
            self.btn_send.blockSignals(True)
            self.btn_send.setChecked(False)
            self.btn_send.blockSignals(False)
            self.btn_send.setStyleSheet(STYLE_PROM_INACTIVE)
            self.btn_receive.setStyleSheet(STYLE_RECEIVE_ON)
        else:
            self.btn_receive.setStyleSheet(STYLE_PROM_INACTIVE)

    def _on_blink_tick(self) -> None:
        self._blink_phase = not self._blink_phase
        self.btn_send.setStyleSheet(
            STYLE_SEND_BLINK if self._blink_phase else STYLE_SEND_ON
        )

    # ------------------------------------------------------------------
    # Slots – UTC / Macros
    # ------------------------------------------------------------------

    def _update_utc(self) -> None:
        now = datetime.now(timezone.utc)
        self.lbl_utc.setText(now.strftime("UTC  %H:%M:%S"))

    def _on_edit_macros(self) -> None:
        dlg = MacroEditDialog(self._macro_store, parent=self)
        dlg.exec()
        for i, btn in enumerate(self.macro_buttons):
            btn.setText(self._macro_store.names[i])
        apply_macro_tooltips(self.macro_buttons, self._macro_store)


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _param_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
    lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return lbl


def _small_btn(text: str) -> QPushButton:
    """Kleiner +/- Button für SpinBox-Steuerung."""
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


def _spinbox(lo: int, hi: int, default: int) -> QSpinBox:
    sb = QSpinBox()
    sb.setRange(lo, hi)
    sb.setValue(default)
    sb.setFont(QFont("Courier New", 10))
    sb.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return sb


# ---------------------------------------------------------------------------
# Standalone-Test
# ---------------------------------------------------------------------------

class _TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PK232PY – CW/Morse Screen (Test)")
        self.resize(750, 640)
        self.setCentralWidget(MorseScreen())


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
