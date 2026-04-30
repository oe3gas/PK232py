"""
pactor_screen.py – PACTOR I Opmode-Screen

PACTOR I (Packet Teleprinting Over Radio) is an ARQ mode developed by
DL6MAA and DF4KV in 1990. The PK-232MBX supports PACTOR I via firmware
v7.0 and later.

Key differences from AMTOR:
  - Callsign via MYPTCALL (mnemonic MK), NOT MYCALL
  - Automatic 100/200 baud speed selection (PT200)
  - Huffman compression (PTHUFF) for better throughput
  - Direction change via PTOVER character (default Ctrl-Z, $1A)
  - Channel 0 only (single-channel ARQ)
  - FEC/Unproto mode via PTSEND

Mode buttons:
  Connect   – initiate ARQ connection to a callsign (stays pressed)
  PTLIST    – listen / receive mode (stays pressed)
  PTSEND    – FEC unproto transmission (stays pressed while sending)
  Disconnect – one-shot, terminates active connection
  STBY      – one-shot, return to PACTOR standby

Toggle buttons:
  PT200     – allow 200 baud auto-selection (ON by default)
  PTHUFF    – Huffman compression (ON for text, OFF for binary)
  PTROUND   – after PTSEND: return to PTLIST (ON) or STBY (OFF)
  EAS       – Echo As Sent

Standalone test: python pactor_screen.py
"""

import sys
from datetime import datetime, timezone

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QLineEdit, QPushButton,
    QFrame, QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer, QEvent
from PyQt6.QtGui import QFont

from .opmode_rtty_base import (
    MacroStore, MacroEditDialog,
    make_toggle_button, add_hline,
    apply_app_style, style_rx_widget, style_tx_widget,
    BTN_W, SPACING, MACRO_COUNT,
    STYLE_PROM_INACTIVE, STYLE_SEND_ON, STYLE_SEND_BLINK, STYLE_RECEIVE_ON,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CALL_W = 120    # width of callsign input field

# Connection states
STATUS_STYLES = {
    "STBY":        ("●  STBY",           "#888888"),
    "CALLING":     ("●  CALLING …",      "#cc8800"),
    "CONNECTED":   ("●  CONNECTED",      "#3a9e3a"),
    "PTLIST":      ("●  LISTENING",      "#2266cc"),
    "PTSEND":      ("●  FEC TX",         "#2266cc"),
    "DISCONN":     ("●  DISCONNECTED",   "#cc4444"),
}


# ---------------------------------------------------------------------------
# Helper: mode button style
# ---------------------------------------------------------------------------

def _mode_style(active_color: str) -> tuple[str, str]:
    """Returns (style_off, style_on) for a mode button."""
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


def _make_mode_btn(label: str, width: int, color: str) -> QPushButton:
    btn = QPushButton(label)
    btn.setFixedWidth(width)
    btn.setCheckable(True)
    btn.setChecked(False)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    btn.setStyleSheet(_mode_style(color)[0])
    return btn


# ---------------------------------------------------------------------------
# PactorScreen
# ---------------------------------------------------------------------------

class PactorScreen(QWidget):
    """PACTOR I Opmode-Screen.

    Layout (top to bottom):
    ┌──────────────────────────────────────────────────────────┐
    │  PACTOR I                              UTC  HH:MM:SS    │
    ├──────────────────────────────────────────────────────────┤
    │  MYPTCALL: [OE3GAS    ]                                  │
    ├──────────────────────────────────────────────────────────┤
    │  [Connect] Dest: [OE3XYZ  ]  [PTLIST]  [PTSEND]         │
    │  [Disconnect]  [STBY]  Status: ●  STBY                  │
    ├──────────────────────────────────────────────────────────┤
    │  [PT200] [PTHUFF] [PTROUND] [EAS]                        │
    ├──────────────────────────────────────────────────────────┤
    │  RX window (expands)                                     │
    ├──────────────────────────────────────────────────────────┤
    │  TX window (5 lines)                                     │
    ├──────────────────────────────────────────────────────────┤
    │  [Macro 1] … [Macro 6]              [Edit Macros]        │
    └──────────────────────────────────────────────────────────┘
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._macro_store = MacroStore()
        err = self._macro_store.load()
        if err:
            print(f"[MacroStore] {err}")

        self._utc_timer = QTimer(self)
        self._utc_timer.setInterval(1000)
        self._utc_timer.timeout.connect(self._update_utc)
        self._utc_timer.start()

        self._build_ui()

        # EventFilter: redirects all keypresses to TX window
        self.installEventFilter(self)
        # Initial focus: cursor goes straight to TX window on open
        QTimer.singleShot(0, lambda: self.tx_input.setFocus())

    # ------------------------------------------------------------------
    # EventFilter: TX window always keeps keyboard focus
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event) -> bool:
        """Any keypress lands in the TX window, regardless of which button was clicked.

        Exception: if focus is already in an input widget (QTextEdit / QLineEdit),
        the event is forwarded normally — e.g. for MYPTCALL or Dest fields.
        """
        if event.type() == QEvent.Type.KeyPress:
            focused = self.focusWidget()
            if isinstance(focused, (QTextEdit, QLineEdit)):
                return super().eventFilter(obj, event)
            if hasattr(self, "tx_input") and self.tx_input is not None:
                self.tx_input.setFocus()
                from PyQt6.QtWidgets import QApplication
                QApplication.sendEvent(self.tx_input, event)
                return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(6)
        root.setContentsMargins(8, 8, 8, 8)

        # --- Title row with UTC ------------------------------------------
        title_row = QHBoxLayout()
        title = QLabel("PACTOR I")
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        title_row.addWidget(title)
        title_row.addStretch()
        self.lbl_utc = QLabel()
        self.lbl_utc.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self.lbl_utc.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._update_utc()
        title_row.addWidget(self.lbl_utc)
        root.addLayout(title_row)

        add_hline(root)

        # --- MYPTCALL row ------------------------------------------------
        myptcall_row = QHBoxLayout()
        myptcall_row.setSpacing(8)

        lbl = QLabel("MYPTCALL:")
        lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lbl.setFixedWidth(80)
        myptcall_row.addWidget(lbl)

        self.le_myptcall = QLineEdit()
        self.le_myptcall.setMaxLength(14)          # max callsign length
        self.le_myptcall.setFixedWidth(CALL_W)
        self.le_myptcall.setFont(QFont("Courier New", 10))
        self.le_myptcall.setPlaceholderText("e.g. OE3GAS")
        self.le_myptcall.setToolTip(
            "PACTOR callsign (MYPTCALL / mnemonic MK).\n"
            "Separate from MYCALL — allows portable suffixes\n"
            "e.g. ZL2/OE3GAS.\n\n"
            "Required before any PACTOR transmission."
        )
        myptcall_row.addWidget(self.le_myptcall)
        myptcall_row.addStretch()
        root.addLayout(myptcall_row)

        add_hline(root)

        # --- Mode buttons row 1: Connect / PTLIST / PTSEND ---------------
        mode_row = QHBoxLayout()
        mode_row.setSpacing(6)

        # Connect – stays pressed while connected
        self.btn_connect = _make_mode_btn("Connect", 80, "#3a7a3a")
        self.btn_connect.toggled.connect(
            lambda on: self._on_mode_toggled(
                self.btn_connect, on, "CALLING", "#3a7a3a"
            )
        )
        mode_row.addWidget(self.btn_connect)

        # Destination callsign
        mode_row.addWidget(_field_label("Dest:"))
        self.le_dest = QLineEdit()
        self.le_dest.setMaxLength(14)
        self.le_dest.setFixedWidth(CALL_W)
        self.le_dest.setFont(QFont("Courier New", 10))
        self.le_dest.setPlaceholderText("e.g. OE3XYZ")
        self.le_dest.setToolTip("Destination callsign for ARQ connection.")
        mode_row.addWidget(self.le_dest)

        mode_row.addSpacing(8)

        # PTLIST – listen mode
        self.btn_ptlist = _make_mode_btn("PTLIST", 75, "#2255aa")
        self.btn_ptlist.toggled.connect(
            lambda on: self._on_mode_toggled(
                self.btn_ptlist, on, "PTLIST", "#2255aa"
            )
        )
        self.btn_ptlist.setToolTip(
            "PTLIST – PACTOR listen / receive mode.\n"
            "Monitor connected and unproto PACTOR traffic.\n"
            "Mnemonic: PN"
        )
        mode_row.addWidget(self.btn_ptlist)

        # PTSEND – FEC unproto transmission
        self.btn_ptsend = _make_mode_btn("PTSEND", 75, "#2255aa")
        self.btn_ptsend.toggled.connect(
            lambda on: self._on_mode_toggled(
                self.btn_ptsend, on, "PTSEND", "#2255aa"
            )
        )
        self.btn_ptsend.setToolTip(
            "PTSEND – FEC unproto transmission.\n"
            "Broadcast without ARQ handshake (like AMTOR FEC).\n"
            "Mnemonic: PD"
        )
        mode_row.addWidget(self.btn_ptsend)

        mode_row.addStretch()
        root.addLayout(mode_row)

        # --- Mode buttons row 2: Disconnect / STBY / Status --------------
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(6)

        # Disconnect – one-shot
        self.btn_disconnect = QPushButton("Disconnect")
        self.btn_disconnect.setFixedWidth(90)
        self.btn_disconnect.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_disconnect.setStyleSheet(
            "QPushButton { background-color: #883333; color: white;"
            " border: 1px solid #661111; border-radius: 4px; padding: 4px; }"
            "QPushButton:hover { background-color: #994444; }"
        )
        self.btn_disconnect.setToolTip(
            "Disconnect – terminate the active ARQ connection.\n"
            "Mnemonic: DI"
        )
        self.btn_disconnect.clicked.connect(self._on_disconnect)
        ctrl_row.addWidget(self.btn_disconnect)

        # STBY – one-shot
        self.btn_stby = QPushButton("STBY")
        self.btn_stby.setFixedWidth(55)
        self.btn_stby.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_stby.setToolTip(
            "STBY – return to PACTOR standby.\n"
            "Deactivates all mode buttons."
        )
        self.btn_stby.clicked.connect(self._on_stby)
        ctrl_row.addWidget(self.btn_stby)

        # Status label
        ctrl_row.addSpacing(12)
        self.lbl_status = QLabel("●  STBY")
        self.lbl_status.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.lbl_status.setStyleSheet("color: #888888;")
        ctrl_row.addWidget(self.lbl_status)

        ctrl_row.addStretch()
        root.addLayout(ctrl_row)

        add_hline(root)

        # --- Toggle buttons ----------------------------------------------
        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(SPACING)

        self.btn_pt200   = make_toggle_button("PT200")
        self.btn_pt200.setChecked(True)    # ON by default per manual
        self.btn_pt200.setToolTip(
            "PT200 ON – allow automatic 100/200 baud speed selection.\n"
            "ON recommended for modern PACTOR stations.\n"
            "Mnemonic: P2"
        )

        self.btn_pthuff  = make_toggle_button("PTHUFF")
        self.btn_pthuff.setChecked(True)   # ON by default
        self.btn_pthuff.setToolTip(
            "PTHUFF ON – Huffman compression for better throughput.\n"
            "Turn OFF for binary file transfers (7-bit data only).\n"
            "Mnemonic: PH"
        )

        self.btn_ptround = make_toggle_button("PTROUND")
        self.btn_ptround.setToolTip(
            "PTROUND ON – after PTSEND return to PTLIST (listen).\n"
            "PTROUND OFF – after PTSEND return to PACTOR standby.\n"
            "Mnemonic: Pr"
        )

        self.btn_eas     = make_toggle_button("EAS")
        self.btn_eas.setToolTip(
            "EAS – Echo As Sent.\n"
            "Show confirmed TX characters in the RX window.\n"
            "Mnemonic: EA"
        )

        for b in (self.btn_pt200, self.btn_pthuff, self.btn_ptround, self.btn_eas):
            toggle_row.addWidget(b)

        toggle_row.addStretch()
        root.addLayout(toggle_row)

        add_hline(root)

        # --- RX window ---------------------------------------------------
        self.rx_display = QTextEdit()
        self.rx_display.setReadOnly(True)
        self.rx_display.setFont(QFont("Courier New", 10))
        self.rx_display.setPlaceholderText(
            "RX – received characters appear here …\n\n"
            "ARQ data: $30 frames (connected)\n"
            "FEC data: $3F frames (PTLIST / PTSEND)"
        )
        self.rx_display.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        style_rx_widget(self.rx_display)
        root.addWidget(self.rx_display, stretch=1)

        add_hline(root)

        # --- TX window (5 lines) -----------------------------------------
        self.tx_input = QTextEdit()
        self.tx_input.setFont(QFont("Courier New", 10))
        self.tx_input.setPlaceholderText(
            "TX – type here …  "
            "(Ctrl-Z = direction change / PTOVER)"
        )
        fm = self.tx_input.fontMetrics()
        mc = self.tx_input.contentsMargins()
        self.tx_input.setFixedHeight(fm.lineSpacing() * 5 + mc.top() + mc.bottom() + 8)
        style_tx_widget(self.tx_input)
        root.addWidget(self.tx_input)

        add_hline(root)

        # --- Macro bar ---------------------------------------------------
        macro_row = QHBoxLayout()
        macro_row.setSpacing(SPACING)

        self.macro_buttons: list[QPushButton] = []
        for i in range(MACRO_COUNT):
            btn = QPushButton(self._macro_store.names[i])
            btn.setFixedWidth(BTN_W)
            macro_row.addWidget(btn)
            self.macro_buttons.append(btn)

        macro_row.addStretch()

        self.btn_edit_macros = QPushButton("Edit Macros")
        self.btn_edit_macros.setFixedWidth(BTN_W + 20)
        self.btn_edit_macros.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_edit_macros.setStyleSheet(
            "QPushButton { border: 1px solid #666; border-radius: 4px; padding: 4px; }"
        )
        self.btn_edit_macros.clicked.connect(self._on_edit_macros)
        macro_row.addWidget(self.btn_edit_macros)
        root.addLayout(macro_row)

    # ------------------------------------------------------------------
    # Mode button mutual exclusion
    # ------------------------------------------------------------------

    @property
    def _mode_buttons(self) -> list[QPushButton]:
        return [self.btn_connect, self.btn_ptlist, self.btn_ptsend]

    def _on_mode_toggled(
        self,
        sender: QPushButton,
        checked: bool,
        status_key: str,
        active_color: str,
    ) -> None:
        style_off, style_on = _mode_style(active_color)
        if checked:
            for btn in self._mode_buttons:
                if btn is not sender:
                    btn.blockSignals(True)
                    btn.setChecked(False)
                    btn.blockSignals(False)
                    btn.setStyleSheet(_mode_style("#445566")[0])
            sender.setStyleSheet(style_on)
            self._set_status(status_key)
        else:
            sender.setStyleSheet(style_off)
            self._set_status("STBY")

    def _on_disconnect(self) -> None:
        """Disconnect – one-shot, deactivates Connect button."""
        for btn in self._mode_buttons:
            btn.blockSignals(True)
            btn.setChecked(False)
            btn.blockSignals(False)
            btn.setStyleSheet(_mode_style("#445566")[0])
        self._set_status("DISCONN")

    def _on_stby(self) -> None:
        """STBY – reset all mode buttons, return to standby."""
        for btn in self._mode_buttons:
            btn.blockSignals(True)
            btn.setChecked(False)
            btn.blockSignals(False)
            btn.setStyleSheet(_mode_style("#445566")[0])
        self._set_status("STBY")

    # ------------------------------------------------------------------
    # Status label
    # ------------------------------------------------------------------

    def _set_status(self, state: str) -> None:
        text, color = STATUS_STYLES.get(state, (f"●  {state}", "#888888"))
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet(
            f"color: {color}; font-weight: bold; font-size: 10pt;"
        )

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _update_utc(self) -> None:
        now = datetime.now(timezone.utc)
        self.lbl_utc.setText(now.strftime("UTC  %H:%M:%S"))

    def _on_edit_macros(self) -> None:
        dlg = MacroEditDialog(self._macro_store, parent=self)
        dlg.exec()
        for i, btn in enumerate(self.macro_buttons):
            btn.setText(self._macro_store.names[i])


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _field_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
    lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return lbl


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

class _TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PK232PY – PACTOR I Screen (Test)")
        self.resize(750, 600)
        self.setCentralWidget(PactorScreen())


def main() -> None:
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