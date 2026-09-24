"""
packet_screen.py  –  Packet Radio (PR) opmode screen — PK232PY mockup v2

ONE screen for HF Packet and VHF Packet.  The band is not a separate screen
any more but a segmented switch in the header: HF (300 Bd) / VHF (1200 Bd).
Switching the band only changes HBAUD, the default monitor level and a handful
of timing parameters — everything else is identical, so a second screen class
would only duplicate code.

New compared to mockup v1 (derived from the PCPackRatt PPWIN.HLP analysis):
  - Channel bar: the PK-232 holds up to 10 AX.25 channels; the bar is the
    primary channel control (click = switch, colour = state)
  - View switch ALL / CH: RX window shows all channels or only the current one
  - Connect dialog with a persistent callsign list and NET/ROM multi-hop syntax
  - Stations panel with double-click-to-connect
  - Tool row: MailDrop, File transfer, Capture, Scrollback, QSO Log
  - Options row (hidden by default) for the rarely changed TNC flags
  - Status strip at the bottom: channel, link partner, capture, scrollback

Layout:

  ┌────────────────────────────────────────────────────┬────────────┐
  │ Packet  [HF 300][VHF 1200]              UTC 14:22:07│  STATIONS  │
  ├────────────────────────────────────────────────────┤  heard     │
  │ MYCALL OE3GAS   Dest [OE3XYZ-9 ▾][…]  ● CONNECTED  │  list      │
  │ [  Connect  ][ Disconnect ][Unproto]               │            │
  ├────────────────────────────────────────────────────┤  dbl-click │
  │ CH [0][1][2][3][4][5][6][7][8][9] [ALL|CH] → call  │  = connect │
  ├────────────────────────────────────────────────────┤            │
  │ [MailDrop][Files…][Capture][Scrollback][QSO Log]   │            │
  │                       HBAUD[300] Monitor[4] [⚙]    │            │
  │ (options row — hidden until ⚙ is pressed)          │            │
  ├────────────────────────────────────────────────────┤ [Refresh]  │
  │ RX window (expands)                                │ [Clear]    │
  ├────────────────────────────────────────────────────┤            │
  │ TX window (5 lines)        [Hold][Clr TX][Clr RX]  │            │
  ├────────────────────────────────────────────────────┤            │
  │ [M1][M2][M3][M4][M5][M6]          [Edit Macros]    │            │
  ├────────────────────────────────────────────────────┴────────────┤
  │ CH 1 · CONNECTED to OE3XYZ-9 · Capture off · Scrollback 0 lines │
  └──────────────────────────────────────────────────────────────────┘

Launch:
    python packet_screen.py                     # HF, dark
    python packet_screen.py --mode=vhf
    python packet_screen.py --theme=light
    python packet_screen.py --shot=preview.png  # render to PNG (dev only)
"""

import sys
from datetime import datetime, timezone

from PyQt6.QtCore import Qt, QTimer, QEvent, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QDialog,
    QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QLineEdit, QPushButton, QComboBox,
    QFrame, QSizePolicy, QScrollArea, QSplitter, QStackedLayout,
    QListWidget, QListWidgetItem, QMessageBox, QDialogButtonBox,
)

from opmode_rtty_base import (
    MacroStore, MacroEditDialog,
    add_hline, apply_app_style, style_rx_widget, style_tx_widget,
    get_theme, BTN_W, SPACING, MACRO_COUNT,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHANNEL_COUNT = 10      # PK-232 supports 10 simultaneous AX.25 channels
CHIP_MIN_W    = 56      # minimum width of one channel chip
CALL_W        = 120

FONT_UI   = "Segoe UI"
FONT_MONO = "Courier New"

# Band presets — the ONLY real difference between HF and VHF packet.
BANDS: dict[str, dict] = {
    "hf": {
        "label":    "HF  300 Bd",
        "hbaud":    "300",
        "hbauds":   ["300", "1200"],
        "monitor":  "4",
        "vhf_flag": "VH N",           # TNC mnemonic sent on mode entry
        "hint":     "MAXFRAME 1 · PACLEN 64 · FRACK 7",
    },
    "vhf": {
        "label":    "VHF  1200 Bd",
        "hbaud":    "1200",
        "hbauds":   ["1200", "9600"],
        "monitor":  "4",
        "vhf_flag": "VH Y",
        "hint":     "MAXFRAME 4 · PACLEN 128 · SLOTTIME 10",
    },
}

# Link state → (label, colour)
STATUS_STYLES: dict[str, tuple[str, str]] = {
    "STBY":         ("●  STBY",         "#888888"),
    "CALLING":      ("●  CALLING …",    "#cc8800"),
    "CONNECTED":    ("●  CONNECTED",    "#3a9e3a"),
    "DISCONNECTED": ("●  DISCONNECTED", "#cc4444"),
    "UNPROTO TX":   ("●  UNPROTO TX",   "#2266cc"),
}

# Channel chip states
CH_FREE      = "free"
CH_CALLING   = "calling"
CH_CONNECTED = "connected"

# Channel chip colours — the "free" chip follows the theme, the two active
# states keep their semantic colours in both themes.
_CHIP_COLORS_DARK = {
    CH_FREE:      ("#3a4552", "#6d7d8c"),   # bg, fg
    CH_CALLING:   ("#8a6a1e", "#ffffff"),
    CH_CONNECTED: ("#2f7a3a", "#ffffff"),
}
_CHIP_COLORS_LIGHT = {
    CH_FREE:      ("#dfe4ea", "#7a8590"),
    CH_CALLING:   ("#c8901f", "#ffffff"),
    CH_CONNECTED: ("#2f7a3a", "#ffffff"),
}


def _is_dark() -> bool:
    return get_theme()["name"] == "Dark"


def _muted() -> str:
    """Secondary text colour (labels, hints) that works in both themes."""
    return "#8fa0ae" if _is_dark() else "#5a6470"


def _chip_colors(state: str) -> tuple[str, str]:
    return (_CHIP_COLORS_DARK if _is_dark() else _CHIP_COLORS_LIGHT)[state]

_STYLE_PRIMARY_OFF = (
    "QPushButton {"
    "  background-color: #445566; color: #ffffff;"
    "  border: 1px solid #334455; border-radius: 4px;"
    "  font-weight: bold; padding: 6px 10px;"
    "}"
    "QPushButton:hover { background-color: #556677; }"
)
_STYLE_CONNECT_ON = (
    "QPushButton {"
    "  background-color: #2f7a3a; color: #ffffff;"
    "  border: 2px solid #1f5a2a; border-radius: 4px;"
    "  font-weight: bold; padding: 6px 10px;"
    "}"
)
_STYLE_CAPTURE_ON = (
    "QPushButton {"
    "  background-color: #a33a3a; color: #ffffff;"
    "  border: 1px solid #7a2222; border-radius: 4px; padding: 4px 8px;"
    "}"
)
_STYLE_UNPROTO_ON = (
    "QPushButton {"
    "  background-color: #1a4a7a; color: #ffffff;"
    "  border: 2px solid #0a2a5a; border-radius: 4px;"
    "  font-weight: bold; padding: 6px 10px;"
    "}"
)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _btn(text: str, width: int | None = None, tip: str = "") -> QPushButton:
    """Plain button that never steals keyboard focus from the TX window."""
    b = QPushButton(text)
    if width:
        b.setFixedWidth(width)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    if tip:
        b.setToolTip(tip)
    return b


def _toggle(text: str, width: int | None = None, tip: str = "") -> QPushButton:
    """Compact checkable toggle — green when ON, grey when OFF.

    A local helper (not the one in opmode_rtty_base) because the packet screen
    needs narrower chips than the RTTY screens and a smaller font.
    """
    b = _btn(text, width, tip)
    b.setCheckable(True)
    b.setFont(QFont(FONT_UI, 8))
    _style_toggle(b)
    b.toggled.connect(lambda _c, x=b: _style_toggle(x))
    return b


def _style_toggle(b: QPushButton) -> None:
    if b.isChecked():
        b.setStyleSheet(
            "QPushButton { background-color: #3a9e3a; color: white;"
            " border: 1px solid #2a7a2a; border-radius: 3px; padding: 3px 6px; }"
        )
    else:
        bg, fg, br = (("#4a5560", "#c8d4de", "#3a4550") if _is_dark()
                      else ("#d8dde3", "#40484f", "#b6bec6"))
        b.setStyleSheet(
            f"QPushButton {{ background-color: {bg}; color: {fg};"
            f" border: 1px solid {br}; border-radius: 3px; padding: 3px 6px; }}"
        )


def _vsep() -> QFrame:
    """Vertical separator between button groups."""
    f = QFrame()
    f.setFrameShape(QFrame.Shape.VLine)
    f.setFrameShadow(QFrame.Shadow.Sunken)
    f.setFixedHeight(22)
    return f


# ---------------------------------------------------------------------------
# ChannelBar — the PK-232's 10 AX.25 channels
# ---------------------------------------------------------------------------

class ChannelChip(QWidget):
    """One channel chip: a button that turns into an input field.

    Free chip  -> double-click (or Enter on the selected chip) opens an
                  inline editor; typing a callsign and pressing Enter
                  connects on THIS channel.
    Busy chip  -> shows the partner callsign; the editor stays closed.

    The chip is the control: there is no separate Connect row any more,
    so a connect can never land on a channel other than the one you see.
    """

    connect_requested = pyqtSignal(int, str)   # channel, callsign
    clicked = pyqtSignal(int)

    def __init__(self, channel: int, parent=None):
        super().__init__(parent)
        self._channel = channel
        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)

        self.button = QPushButton(str(channel))
        self.button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.button.setFixedHeight(24)
        self.button.clicked.connect(lambda: self.clicked.emit(self._channel))

        self.editor = QLineEdit()
        self.editor.setFixedHeight(24)
        self.editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.editor.setFont(QFont(FONT_MONO, 9, QFont.Weight.Bold))
        self.editor.setPlaceholderText("call")
        self.editor.setStyleSheet(
            "QLineEdit { background-color: #12303f; color: #ffffff;"
            " border: 2px solid #e8b23a; border-radius: 4px; }")
        self.editor.returnPressed.connect(self._commit)

        self._stack.addWidget(self.button)
        self._stack.addWidget(self.editor)
        self._stack.setCurrentIndex(0)

    def channel(self) -> int:
        return self._channel

    def editing(self) -> bool:
        return self._stack.currentIndex() == 1

    def start_edit(self, prefill: str = "") -> None:
        self.editor.setText(prefill)
        self._stack.setCurrentIndex(1)
        self.editor.setFocus()
        self.editor.selectAll()

    def cancel_edit(self) -> None:
        self._stack.setCurrentIndex(0)

    def mouseDoubleClickEvent(self, ev) -> None:
        self.clicked.emit(self._channel)

    def _commit(self) -> None:
        call = self.editor.text().strip().upper()
        self._stack.setCurrentIndex(0)
        if call:
            self.connect_requested.emit(self._channel, call)


class ChannelBar(QWidget):
    """Row of 10 channel chips, spanning the full width of the RX window.

    A chip shows the channel NUMBER while the channel is free and the PARTNER
    CALLSIGN as soon as a link is up (or being established).  Colour encodes
    the state, the amber border marks the channel you are typing on.
    One click switches channels; the Up/Down arrow keys do the same.

    Signals:
        channel_changed(int)   user selected another channel
    """

    channel_changed = pyqtSignal(int)
    connect_requested = pyqtSignal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current = 0
        self._state:   list[str] = [CH_FREE] * CHANNEL_COUNT
        self._partner: list[str] = [""] * CHANNEL_COUNT
        self._chips:   list[QPushButton] = []
        self._build_ui()

    def _build_ui(self) -> None:
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(3)

        for ch in range(CHANNEL_COUNT):
            chip = ChannelChip(ch)
            # Expanding + equal stretch: the ten chips always share the full
            # row width, so the bar lines up exactly with the RX/TX windows.
            chip.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            chip.setMinimumWidth(CHIP_MIN_W)
            chip.clicked.connect(self._on_chip_clicked)
            chip.connect_requested.connect(self.connect_requested)
            self._chips.append(chip)
            row.addWidget(chip, 1)

        self._refresh()

    def _on_chip_clicked(self, ch: int) -> None:
        """First click selects, a click on the already selected FREE chip
        opens the editor. Channel 0 is the UI channel and never connects."""
        if ch == self._current and ch != 0 and self._state[ch] == CH_FREE:
            self._chips[ch].start_edit()
            return
        self.set_current(ch)

    def start_edit(self, ch: int, prefill: str = "") -> None:
        if ch != 0 and self._state[ch] == CH_FREE:
            self._chips[ch].start_edit(prefill)

    def start_edit_current(self) -> None:
        ch = self._current
        if ch != 0 and self._state[ch] == CH_FREE:
            self._chips[ch].start_edit()

    # -- public API ----------------------------------------------------

    def set_channel_state(self, ch: int, state: str, partner: str = "") -> None:
        """Set state and link partner of one channel (production: from CSTATUS)."""
        self._state[ch]   = state
        self._partner[ch] = partner
        self._refresh()

    def set_current(self, ch: int) -> None:
        if ch == self._current:
            return
        self._current = ch
        self._refresh()
        self.channel_changed.emit(ch)

    def current(self) -> int:
        return self._current

    def partner(self, ch: int | None = None) -> str:
        return self._partner[self._current if ch is None else ch]

    def state(self, ch: int | None = None) -> str:
        return self._state[self._current if ch is None else ch]

    def channel_map(self) -> dict[str, int]:
        """Callsign → channel, for every channel that carries a link."""
        return {
            call: ch for ch, call in enumerate(self._partner)
            if call and self._state[ch] != CH_FREE
        }

    def step(self, delta: int) -> None:
        """Up/Down arrow keys move one channel (PCPackRatt parity)."""
        self.set_current((self._current + delta) % CHANNEL_COUNT)

    # -- internals -----------------------------------------------------

    def _refresh(self) -> None:
        for ch, wrapper in enumerate(self._chips):
            chip = wrapper.button
            bg, fg = _chip_colors(self._state[ch])
            current = ch == self._current
            border  = "#e8b23a" if current else bg
            width   = 2 if current else 1

            partner = self._partner[ch]
            if partner:
                # Callsign — smaller font so even OE3XYZ-9 fits the chip
                chip.setText(partner)
                chip.setFont(QFont(FONT_MONO, 8, QFont.Weight.Bold))
            else:
                chip.setText(str(ch))
                chip.setFont(QFont(FONT_MONO, 10, QFont.Weight.Bold))

            chip.setStyleSheet(
                f"QPushButton {{ background-color: {bg}; color: {fg};"
                f" border: {width}px solid {border}; border-radius: 4px;"
                f" padding: 2px 0px; }}"
                f"QPushButton:hover {{ border: {width}px solid #e8b23a; }}"
            )
            wrapper.setToolTip(
                f"Channel {ch} — {self._state[ch].upper()}"
                + (f"\nLink partner: {partner}" if partner else " (free)")
                + ("\nClick to switch; click again to type a callsign "
                   "and press Enter to connect."
                   if ch != 0 else
                   "\nUI channel: unproto and monitor, no connects.")
            )


# ---------------------------------------------------------------------------
# StationsPanel — heard stations (MHEARD)
# ---------------------------------------------------------------------------

class StationsPanel(QWidget):
    """Right-hand panel: stations heard, newest first.

    Double-clicking an entry starts a connect to that station — the single
    most used shortcut in packet operation.

    Signals:
        connect_requested(str)  callsign double-clicked
    """

    connect_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries:  list[tuple[str, str, bool]] = []
        self._channels: dict[str, int] = {}
        self._build_ui()
        self._load_demo()

    def _build_ui(self) -> None:
        t = get_theme()
        self.setAutoFillBackground(True)
        self.setStyleSheet(
            f"StationsPanel {{ background-color: {t['bg_input']};"
            f" border-left: 1px solid {t['border_input']}; }}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(4)

        title = QLabel("STATIONS HEARD")
        title.setFont(QFont(FONT_UI, 8, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {_muted()}; letter-spacing: 1px;")
        root.addWidget(title)

        add_hline(root)

        self.list = QListWidget()
        self.list.setFont(QFont(FONT_MONO, 9))
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.setFrameShape(QFrame.Shape.NoFrame)
        self.list.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        self.list.itemDoubleClicked.connect(self._on_double_click)
        root.addWidget(self.list, stretch=1)

        legend = QLabel("CH · call · time\n*  direct   ·   dbl-click = connect")
        legend.setFont(QFont(FONT_UI, 7))
        legend.setStyleSheet(f"color: {_muted()};")
        root.addWidget(legend)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        self.btn_refresh = _btn("Refresh", 70, "Poll MHEARD list from the TNC (MH)")
        self.btn_clear   = _btn("Clear", 70, "Clear the list locally")
        self.btn_clear.clicked.connect(self.clear)
        self.btn_refresh.clicked.connect(self._on_refresh)
        btn_row.addWidget(self.btn_refresh)
        btn_row.addWidget(self.btn_clear)
        root.addLayout(btn_row)

    # -- public API ----------------------------------------------------

    def add_entry(self, callsign: str, time_str: str, direct: bool = False,
                  channel: int | None = None) -> None:
        """Add one heard station (newest first)."""
        self._entries.insert(0, (callsign, time_str, direct))
        if channel is not None:
            self._channels[callsign] = channel
        self._render()

    def set_channel_map(self, mapping: dict[str, int]) -> None:
        """Tell the panel which heard stations are linked on which channel."""
        self._channels = dict(mapping)
        self._render()

    def clear(self) -> None:
        self._entries.clear()
        self.list.clear()

    # -- rendering -----------------------------------------------------

    def _render(self) -> None:
        """Redraw the list.

        The channel number is printed in front of the callsign whenever that
        station is currently linked — two blanks otherwise, so the callsign
        column stays aligned.
        """
        self.list.clear()
        for callsign, time_str, direct in self._entries:
            channel = self._channels.get(callsign)
            prefix  = f"{channel} " if channel is not None else "  "
            text = f"{prefix}{callsign + (' *' if direct else ''):<11}{time_str}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, callsign)

            if channel is not None:
                item.setForeground(QColor("#e8b23a"))     # amber = linked
                item.setToolTip(
                    f"{callsign} — connected on channel {channel}\n"
                    f"Double-click to switch to that channel"
                )
            else:
                # Green = heard directly, blue = heard via a digipeater
                if _is_dark():
                    col = QColor("#66ee66") if direct else QColor("#88ccff")
                else:
                    col = QColor("#1f7a33") if direct else QColor("#1a4e8a")
                item.setForeground(col)
                item.setToolTip(f"Double-click to connect to {callsign}")
            self.list.addItem(item)

    # -- internals -----------------------------------------------------

    def _on_double_click(self, item: QListWidgetItem) -> None:
        self.connect_requested.emit(item.data(Qt.ItemDataRole.UserRole))

    def _on_refresh(self) -> None:
        now = datetime.now(timezone.utc).strftime("%H:%M")
        self.add_entry("OE3GAS", now, direct=True)

    def _load_demo(self) -> None:
        for call, t, direct, ch in [
            ("DL8HCZ",   "13:42", False, None),
            ("OE5REO",   "13:55", False, None),
            ("OE3GAS",   "14:05", True,  None),
            ("DK3WX",    "14:08", False, None),
            ("DB0MUC-8", "14:15", False, 4),
            ("OE1XAB-7", "14:17", True,  7),
            ("OE1KBC",   "14:19", True,  None),
            ("DL1ABC",   "14:21", False, None),
            ("OE3XYZ-9", "14:21", True,  1),
            ("OE5XYZ",   "14:21", True,  None),
        ]:
            self.add_entry(call, t, direct, ch)


# ---------------------------------------------------------------------------
# ConnectDialog — callsign entry with a persistent list
# ---------------------------------------------------------------------------

class ConnectDialog(QDialog):
    """Connect dialog modelled on PCPackRatt.

    Holds a list of frequently used callsigns (persisted in production),
    and accepts the NET/ROM multi-hop syntax with semicolons:
        OE3XNR-8;C OE1XAB-7;C OE3GAS
    """

    def __init__(self, calls: list[str], channel: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Connect — channel {channel}")
        self.setModal(True)
        self.setMinimumWidth(320)
        self._result_call = ""

        root = QVBoxLayout(self)
        root.setSpacing(8)

        self.le_call = QLineEdit()
        self.le_call.setFont(QFont(FONT_MONO, 11))
        self.le_call.setPlaceholderText("OE3XYZ-9   or   NODE;C NODE2;C CALL")
        root.addWidget(self.le_call)

        self.list = QListWidget()
        self.list.setFont(QFont(FONT_MONO, 10))
        self.list.addItems(calls)
        self.list.itemClicked.connect(
            lambda it: self.le_call.setText(it.text())
        )
        self.list.itemDoubleClicked.connect(self._accept_item)
        root.addWidget(self.list, stretch=1)

        edit_row = QHBoxLayout()
        edit_row.addWidget(_btn("Add", 70, "Add the callsign to the list"))
        edit_row.addWidget(_btn("Delete", 70, "Remove the selected entry"))
        edit_row.addStretch()
        root.addLayout(edit_row)

        hint = QLabel(
            "Multi-hop via NET/ROM nodes: separate the hops with ';'.\n"
            "The dialog shows the progress of every hop."
        )
        hint.setFont(QFont(FONT_UI, 8))
        hint.setStyleSheet(f"color: {_muted()};")
        root.addWidget(hint)

        box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        root.addWidget(box)

    def _accept_item(self, item: QListWidgetItem) -> None:
        self.le_call.setText(item.text())
        self.accept()

    def callsign(self) -> str:
        return self.le_call.text().strip().upper()


# ---------------------------------------------------------------------------
# PacketScreen — the PR mask
# ---------------------------------------------------------------------------

class PacketScreen(QWidget):
    """Packet Radio screen, valid for HF and VHF.

    Attributes used by MainWindow in production:
        le_mycall, le_unproto
        combo_hbaud, combo_monitor
        btn_unproto (connects are typed into the channel chips)
        btn_maildrop, btn_files, btn_capture, btn_qsolog
        btn_conperm, btn_mdmon, btn_mailbox, btn_lite,
        btn_eas, btn_passall, btn_mrpt, btn_mid, btn_squelch
        channel_bar, stations, rx_display, tx_input
        macro_buttons, _macro_store
    """

    BAND_DEFAULT = "hf"

    def __init__(self, band: str = "hf", parent=None):
        super().__init__(parent)
        self._band = band if band in BANDS else "hf"
        self._calls = ["OE3XYZ-9", "DB0MUC-8", "OE1XAB-7", "OE3XNR-8", "DL1ABC"]

        self._macro_store = MacroStore()
        err = self._macro_store.load()
        if err:
            print(f"[MacroStore] {err}")

        self._utc_timer = QTimer(self)
        self._utc_timer.setInterval(1000)
        self._utc_timer.timeout.connect(self._update_utc)
        self._utc_timer.start()

        self._build_ui()
        self._apply_band(self._band)
        self._load_demo()

        self.installEventFilter(self)
        QTimer.singleShot(0, self.tx_input.setFocus)

    # ------------------------------------------------------------------
    # Event filter — keystrokes go to TX, Up/Down switch channels
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.KeyPress:
            # Up/Down = channel switch, exactly like PCPackRatt
            if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down) and \
                    not isinstance(self.focusWidget(), QLineEdit):
                self.channel_bar.step(
                    1 if event.key() == Qt.Key.Key_Down else -1
                )
                return True
            focused = self.focusWidget()
            if isinstance(focused, (QTextEdit, QLineEdit)):
                return super().eventFilter(obj, event)
            self.tx_input.setFocus()
            QApplication.sendEvent(self.tx_input, event)
            return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        left = QWidget()
        root = QVBoxLayout(left)
        root.setContentsMargins(10, 8, 10, 6)
        root.setSpacing(6)

        root.addLayout(self._build_header())
        add_hline(root)
        root.addLayout(self._build_identity())      # MYCALL + link state
        root.addLayout(self._build_unproto_row())   # Unproto · via · Monitor
        add_hline(root)
        root.addLayout(self._build_tools())         # MailDrop … HBAUD · view · gear
        root.addWidget(self._build_options())       # hidden flag row
        root.addWidget(self._build_channels())      # chips, flush with RX below
        root.addWidget(self._build_rx(), stretch=1)
        root.addLayout(self._build_tx())
        add_hline(root)
        root.addLayout(self._build_macros())

        self.stations = StationsPanel()
        self.stations.setMinimumWidth(170)
        self.stations.setMaximumWidth(240)
        self.stations.connect_requested.connect(self._on_station_connect)

        splitter.addWidget(left)
        splitter.addWidget(self.stations)
        splitter.setSizes([700, 190])

        outer.addWidget(splitter, stretch=1)
        outer.addWidget(self._build_statusbar())

    # -- header --------------------------------------------------------

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)

        title = QLabel(
            '<span style="font-size:12pt; font-weight:bold;">Packet Radio</span>'
        )
        title.setTextFormat(Qt.TextFormat.RichText)
        row.addWidget(title)

        row.addSpacing(6)

        # Band switch — the single control that turns this into HF or VHF
        self.btn_hf  = _btn("HF  300 Bd", 92,
                            "300 Bd HF packet (VHF OFF, MAXFRAME 1, PACLEN 64)")
        self.btn_vhf = _btn("VHF  1200 Bd", 100,
                            "1200 Bd VHF packet (VHF ON, MAXFRAME 4, PACLEN 128)")
        for b in (self.btn_hf, self.btn_vhf):
            b.setCheckable(True)
            b.setFont(QFont(FONT_UI, 8, QFont.Weight.Bold))
        self.btn_hf.clicked.connect(lambda: self._apply_band("hf"))
        self.btn_vhf.clicked.connect(lambda: self._apply_band("vhf"))
        row.addWidget(self.btn_hf)
        row.addWidget(self.btn_vhf)

        self.lbl_bandhint = QLabel()
        self.lbl_bandhint.setFont(QFont(FONT_UI, 8))
        self.lbl_bandhint.setStyleSheet(f"color: {_muted()};")
        row.addWidget(self.lbl_bandhint)

        row.addStretch()

        self.lbl_utc = QLabel()
        self.lbl_utc.setFont(QFont(FONT_MONO, 10, QFont.Weight.Bold))
        self._update_utc()
        row.addWidget(self.lbl_utc)
        return row

    # -- identity ------------------------------------------------------

    def _build_identity(self) -> QHBoxLayout:
        """MYCALL on the left, link state on the right."""
        row = QHBoxLayout()
        row.setSpacing(8)

        lbl = QLabel("MYCALL")
        lbl.setFont(QFont(FONT_UI, 8, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {_muted()};")
        row.addWidget(lbl)

        self.le_mycall = QLineEdit("OE3GAS")
        self.le_mycall.setReadOnly(True)
        self.le_mycall.setFixedWidth(100)
        self.le_mycall.setFont(QFont(FONT_MONO, 10, QFont.Weight.Bold))
        self.le_mycall.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.le_mycall.setToolTip(
            "Your AX.25 callsign (MYCALL / mnemonic ML).\n"
            "Read-only here — set in Parameters → HF Packet."
        )
        row.addWidget(self.le_mycall)

        row.addStretch()

        self.lbl_status = QLabel()
        self.lbl_status.setFont(QFont(FONT_UI, 10, QFont.Weight.Bold))
        self._set_status("STBY")
        row.addWidget(self.lbl_status)
        return row

    # -- row 2: Unproto · via · Monitor ----------------------------------

    def _build_unproto_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(SPACING)

        self.btn_unproto = _btn("Unproto", 110,
                                "Send unconnected UI frames — CQ, beacons, APRS")
        self.btn_unproto.setCheckable(True)
        self.btn_unproto.setStyleSheet(_STYLE_PRIMARY_OFF)
        self.btn_unproto.toggled.connect(self._on_unproto_toggled)
        row.addWidget(self.btn_unproto)

        lbl_via = QLabel("via")
        lbl_via.setFont(QFont(FONT_UI, 8, QFont.Weight.Bold))
        lbl_via.setStyleSheet(f"color: {_muted()};")
        row.addWidget(lbl_via)

        self.le_unproto = QLineEdit("CQ")
        self.le_unproto.setFixedWidth(CALL_W + 28 + SPACING)
        self.le_unproto.setFont(QFont(FONT_MONO, 10))
        self.le_unproto.setToolTip(
            "UNPROTO path (mnemonic UN).\n"
            "e.g.  CQ  ·  CQ VIA WIDE1-1  ·  APRS VIA WIDE1-1,WIDE2-1"
        )
        row.addWidget(self.le_unproto)

        lbl_mon = QLabel("Monitor")
        lbl_mon.setFont(QFont(FONT_UI, 8, QFont.Weight.Bold))
        lbl_mon.setStyleSheet(f"color: {_muted()};")
        row.addWidget(lbl_mon)

        self.combo_monitor = QComboBox()
        self.combo_monitor.addItems([str(i) for i in range(7)])
        self.combo_monitor.setFixedWidth(52)
        self.combo_monitor.setToolTip(
            "Monitor level (mnemonic MN)\n"
            "0 off · 1 UI only · 2 + I-frames · 3 + C/D\n"
            "4 default · 5 more · 6 everything incl. acknowledgements"
        )
        row.addWidget(self.combo_monitor)

        row.addStretch()
        return row

    # -- channel bar ----------------------------------------------------

    def _build_channels(self) -> QWidget:
        self.channel_bar = ChannelBar()
        self.channel_bar.channel_changed.connect(self._on_channel_changed)
        self.channel_bar.connect_requested.connect(self._on_chip_connect)
        return self.channel_bar

    # -- tool row -------------------------------------------------------

    def _build_tools(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(SPACING)

        self.btn_maildrop = _btn("MailDrop", 84,
                                 "Open the TNC mailbox: read, kill, send messages")
        self.btn_files = _btn("Files…", 74,
                              "ASCII / binary file transfer on this channel")
        self.btn_capture = _btn("Capture", 80,
                                "Save received text to a file (all channels)")
        self.btn_capture.setCheckable(True)
        self.btn_capture.toggled.connect(self._on_capture)
        self.btn_qsolog = _btn("QSO Log", 80, "Open the QSO log for this contact")

        for b in (self.btn_maildrop, self.btn_files,
                  self.btn_capture, self.btn_qsolog):
            b.setFont(QFont(FONT_UI, 8))
            row.addWidget(b)

        row.addStretch()

        # View switch: ALL = merged traffic of every channel,
        #              CH  = only the channel selected in the bar below
        self.btn_view_all = _btn("ALL", 44,
                                 "RX window shows traffic of all channels")
        self.btn_view_ch  = _btn("CH", 44,
                                 "RX window shows the current channel only")
        for b in (self.btn_view_all, self.btn_view_ch):
            b.setCheckable(True)
            b.setFont(QFont(FONT_UI, 8, QFont.Weight.Bold))
        self.btn_view_all.setChecked(True)
        self.btn_view_all.clicked.connect(lambda: self._set_view(True))
        self.btn_view_ch.clicked.connect(lambda: self._set_view(False))
        row.addWidget(self.btn_view_all)
        row.addWidget(self.btn_view_ch)

        row.addSpacing(8)

        lbl_hb = QLabel("HBAUD")
        lbl_hb.setFont(QFont(FONT_UI, 8, QFont.Weight.Bold))
        lbl_hb.setStyleSheet(f"color: {_muted()};")
        row.addWidget(lbl_hb)

        self.combo_hbaud = QComboBox()
        self.combo_hbaud.setFixedWidth(70)
        self.combo_hbaud.setToolTip("On-air baud rate (mnemonic HB)")
        row.addWidget(self.combo_hbaud)

        self.btn_options = _btn("⚙", 30, "Show/hide the TNC flag row")
        self.btn_options.setCheckable(True)
        self.btn_options.toggled.connect(
            lambda on: self.options_row.setVisible(on)
        )
        row.addWidget(self.btn_options)

        self._style_view()
        return row

    def _set_view(self, show_all: bool) -> None:
        self.btn_view_all.setChecked(show_all)
        self.btn_view_ch.setChecked(not show_all)
        self._style_view()
        self._update_statusbar()

    def _style_view(self) -> None:
        for b in (self.btn_view_all, self.btn_view_ch):
            if b.isChecked():
                b.setStyleSheet(
                    "QPushButton { background-color: #2a6496; color: white;"
                    " border: 1px solid #1a4476; border-radius: 3px; padding: 3px; }"
                )
            else:
                bg, fg, br = (("#4a5560", "#b0bcc6", "#3a4550") if _is_dark()
                              else ("#d8dde3", "#40484f", "#b6bec6"))
                b.setStyleSheet(
                    f"QPushButton {{ background-color: {bg}; color: {fg};"
                    f" border: 1px solid {br}; border-radius: 3px; padding: 3px; }}"
                )

    # -- options row (hidden by default) --------------------------------

    def _build_options(self) -> QWidget:
        """Rarely changed TNC flags.

        Hidden behind the gear button so the working screen stays calm — the
        flags are set once per session, not per QSO.
        """
        self.options_row = QWidget()
        row = QHBoxLayout(self.options_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)

        self.btn_conperm = _toggle("CONPERM", 74,
                                   "Keep the link permanent / auto-relink (CP)")
        self.btn_mailbox = _toggle("MAILDROP", 78,
                                   "Open your mailbox to remote stations (MA)")
        self.btn_mdmon   = _toggle("MDMON", 62,
                                   "Monitor mailbox activity of other stations (MD)")
        self.btn_lite    = _toggle("LITE", 52, "HF packet LITE feature (LI)")

        row.addWidget(self.btn_conperm)
        row.addWidget(self.btn_mailbox)
        row.addWidget(self.btn_mdmon)
        row.addWidget(self.btn_lite)
        row.addWidget(_vsep())

        self.btn_eas     = _toggle("EAS", 48, "Echo As Sent (EA)")
        self.btn_passall = _toggle("PASSALL", 72, "Pass frames with CRC errors (PS)")
        self.btn_mrpt    = _toggle("MRPT", 56, "Show digipeater path (MR)")
        self.btn_mid     = _toggle("MID", 46, "Periodic Morse ID (MI)")
        self.btn_squelch = _toggle("SQUELCH", 72, "Suppress duplicate frames (SQ)")

        for b in (self.btn_eas, self.btn_passall, self.btn_mrpt,
                  self.btn_mid, self.btn_squelch):
            row.addWidget(b)

        row.addStretch()
        self.options_row.setVisible(False)
        return self.options_row

    # -- RX / TX --------------------------------------------------------

    def _build_rx(self) -> QWidget:
        self.rx_display = QTextEdit()
        self.rx_display.setReadOnly(True)
        self.rx_display.setFont(QFont(FONT_MONO, 10))
        self.rx_display.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        style_rx_widget(self.rx_display)
        return self.rx_display

    def _build_tx(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(SPACING)

        self.tx_input = QTextEdit()
        self.tx_input.setFont(QFont(FONT_MONO, 10))
        self.tx_input.setPlaceholderText("TX — type here …")
        fm = self.tx_input.fontMetrics()
        mc = self.tx_input.contentsMargins()
        self.tx_input.setFixedHeight(
            fm.lineSpacing() * 5 + mc.top() + mc.bottom() + 8
        )
        style_tx_widget(self.tx_input)
        self.tx_input.setCursorWidth(fm.averageCharWidth())
        row.addWidget(self.tx_input, stretch=1)

        # TX side buttons, stacked so they do not widen the button rows
        side = QVBoxLayout()
        side.setSpacing(3)
        self.btn_hold = _toggle("Hold TX", 84,
                                "Buffer typed text until released")
        self.btn_clear_tx = _btn("Clear TX", 84, "Clear TX window and send TCLEAR")
        self.btn_clear_rx = _btn("Clear RX", 84, "Clear RX window and scrollback")
        self.btn_clear_rx.clicked.connect(self.rx_display.clear)
        self.btn_clear_tx.clicked.connect(self.tx_input.clear)
        for b in (self.btn_hold, self.btn_clear_tx, self.btn_clear_rx):
            b.setFont(QFont(FONT_UI, 8))
            side.addWidget(b)
        side.addStretch()
        row.addLayout(side)
        return row

    # -- macros ---------------------------------------------------------

    def _build_macros(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(SPACING)
        self.macro_buttons: list[QPushButton] = []
        for i in range(MACRO_COUNT):
            b = _btn(self._macro_store.names[i], BTN_W)
            b.setFont(QFont(FONT_UI, 8))
            b.setToolTip(f"Macro {i + 1}  (Alt+{i + 1})")
            self.macro_buttons.append(b)
            row.addWidget(b)
        row.addStretch()
        self.btn_edit_macros = _btn("Edit Macros", BTN_W + 20)
        self.btn_edit_macros.setFont(QFont(FONT_UI, 8))
        self.btn_edit_macros.clicked.connect(self._on_edit_macros)
        row.addWidget(self.btn_edit_macros)
        return row

    # -- status strip ---------------------------------------------------

    def _build_statusbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(24)
        t = get_theme()
        bar.setStyleSheet(
            f"background-color: {t['bg_input']};"
            f" border-top: 1px solid {t['border_input']};"
        )
        row = QHBoxLayout(bar)
        row.setContentsMargins(10, 0, 10, 0)
        row.setSpacing(14)

        self.lbl_sb_channel = QLabel()
        self.lbl_sb_link    = QLabel()
        self.lbl_sb_capture = QLabel()
        self.lbl_sb_buffer  = QLabel()
        for l in (self.lbl_sb_channel, self.lbl_sb_link,
                  self.lbl_sb_capture, self.lbl_sb_buffer):
            l.setFont(QFont(FONT_UI, 8))
            l.setStyleSheet(f"color: {_muted()};")
            row.addWidget(l)
        row.addStretch()

        self.lbl_sb_mode = QLabel()
        self.lbl_sb_mode.setFont(QFont(FONT_UI, 8, QFont.Weight.Bold))
        self.lbl_sb_mode.setStyleSheet(f"color: {_muted()};")
        row.addWidget(self.lbl_sb_mode)

        self._update_statusbar()
        return bar

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _update_utc(self) -> None:
        self.lbl_utc.setText(
            datetime.now(timezone.utc).strftime("UTC  %H:%M:%S")
        )

    def _set_status(self, state: str) -> None:
        text, color = STATUS_STYLES.get(state, (f"●  {state}", "#888888"))
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet(f"color: {color}; font-weight: bold;")

    def _update_statusbar(self) -> None:
        ch = self.channel_bar.current()
        partner = self.channel_bar.partner()
        self.lbl_sb_channel.setText(f"CH {ch}")
        self.lbl_sb_link.setText(
            f"CONNECTED to {partner}" if partner else "no link on this channel"
        )
        capturing = self.btn_capture.isChecked()
        self.lbl_sb_capture.setText(
            "● Capture ON" if capturing else "Capture off"
        )
        self.lbl_sb_capture.setStyleSheet(
            "color: #d05a5a;" if capturing else f"color: {_muted()};"
        )
        self.lbl_sb_buffer.setText("RX buffer 8 lines")
        self.lbl_sb_mode.setText(
            f"{BANDS[self._band]['label']}   ·   {BANDS[self._band]['vhf_flag']}"
        )

    def _apply_band(self, band: str) -> None:
        """Switch the whole screen between HF and VHF packet."""
        self._band = band
        cfg = BANDS[band]

        self.btn_hf.setChecked(band == "hf")
        self.btn_vhf.setChecked(band == "vhf")
        for b, active in ((self.btn_hf, band == "hf"),
                          (self.btn_vhf, band == "vhf")):
            b.setStyleSheet(
                "QPushButton { background-color: #2a6496; color: white;"
                " border: 1px solid #1a4476; border-radius: 4px; padding: 4px; }"
                if active else
                ("QPushButton { background-color: #4a5560; color: #b0bcc6;"
                 " border: 1px solid #3a4550; border-radius: 4px; padding: 4px; }"
                 if _is_dark() else
                 "QPushButton { background-color: #d8dde3; color: #40484f;"
                 " border: 1px solid #b6bec6; border-radius: 4px; padding: 4px; }")
            )

        self.combo_hbaud.blockSignals(True)
        self.combo_hbaud.clear()
        self.combo_hbaud.addItems(cfg["hbauds"])
        self.combo_hbaud.setCurrentText(cfg["hbaud"])
        self.combo_hbaud.blockSignals(False)
        self.combo_monitor.setCurrentText(cfg["monitor"])
        self.lbl_bandhint.setText(cfg["hint"])
        self._update_statusbar()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_channel_changed(self, ch: int) -> None:
        state = self.channel_bar.state(ch)
        self._set_status("CONNECTED" if state == CH_CONNECTED else "STBY")
        self._update_statusbar()

    def _on_chip_connect(self, ch: int, call: str) -> None:
        """A callsign was typed into a free chip and confirmed with Enter."""
        self.channel_bar.set_channel_state(ch, CH_CALLING, call)
        self.channel_bar.set_current(ch)
        self._set_status("CALLING")
        self._update_statusbar()
        QTimer.singleShot(1500, lambda: self._demo_connected(ch))

    def _demo_connected(self, ch: int) -> None:
        if self.channel_bar.state(ch) != CH_CALLING:
            return
        self.channel_bar.set_channel_state(
            ch, CH_CONNECTED, self.channel_bar.partner(ch))
        if ch == self.channel_bar.current():
            self._set_status("CONNECTED")
        self._update_statusbar()

    def _on_disconnect_current(self) -> None:
        ch = self.channel_bar.current()
        self.channel_bar.set_channel_state(ch, CH_FREE, "")
        self._set_status("DISCONNECTED")
        self._update_statusbar()

    def _on_unproto_toggled(self, checked: bool) -> None:
        if checked:
            self.btn_unproto.setStyleSheet(_STYLE_UNPROTO_ON)
            self.channel_bar.set_current(0)
            self._set_status("UNPROTO TX")
        else:
            self.btn_unproto.setStyleSheet(_STYLE_PRIMARY_OFF)
            self._set_status("STBY")

    def _on_station_connect(self, callsign: str) -> None:
        """Double-click in the heard list: prefill the first free chip."""
        for ch in range(1, CHANNEL_COUNT):
            if self.channel_bar.state(ch) == CH_FREE:
                self.channel_bar.set_current(ch)
                self.channel_bar.start_edit(ch, callsign)
                return

    def _on_capture(self, on: bool) -> None:
        """Capture is the one tool button with a recording state — red when on."""
        self.btn_capture.setStyleSheet(_STYLE_CAPTURE_ON if on else "")
        self.btn_capture.setText("● Capture" if on else "Capture")
        self._update_statusbar()

    def _on_edit_macros(self) -> None:
        dlg = MacroEditDialog(self._macro_store, parent=self)
        dlg.exec()
        for i, b in enumerate(self.macro_buttons):
            b.setText(self._macro_store.names[i])

    # ------------------------------------------------------------------
    # Demo content (mockup only)
    # ------------------------------------------------------------------

    def _load_demo(self) -> None:
        self.channel_bar.set_channel_state(1, CH_CONNECTED, "OE3XYZ-9")
        self.channel_bar.set_channel_state(4, CH_CONNECTED, "DB0MUC-8")
        self.channel_bar.set_channel_state(7, CH_CALLING, "OE1XAB-7")
        self.channel_bar.set_current(1)

        t = get_theme()
        rx, tx = t["rx_color"], t["tx_color"]
        hdr = _muted()
        html = (
            f'<pre style="margin:0; font-family:{FONT_MONO};">'
            f'<span style="color:{hdr};">[14:18:02] OE5XYZ&gt;CQ &lt;UI&gt;:</span>\n'
            f'<span style="color:{rx};">  CQ CQ de OE5XYZ  Wien  pse k</span>\n'
            f'<span style="color:{hdr};">[14:19:40] OE3XYZ-9&gt;OE3GAS &lt;I&gt; ch1:</span>\n'
            f'<span style="color:{rx};">  Hallo Gerhard, gut lesbar hier, 599.</span>\n'
            f'<span style="color:{tx};">[14:19:58] &gt;&gt; ch1  Servus! Danke, bei mir auch sauber.</span>\n'
            f'<span style="color:{hdr};">[14:20:11] DB0MUC-8&gt;OE3GAS &lt;I&gt; ch4:</span>\n'
            f'<span style="color:{rx};">  Mailbox DB0MUC — 3 neue Nachrichten</span>\n'
            f'<span style="color:{hdr};">[14:21:05] DL1ABC&gt;APRS VIA WIDE1-1 &lt;UI&gt;:</span>\n'
            f'<span style="color:{rx};">  !4812.34N/01622.71E-  73 de Franz</span>\n'
            f'</pre>'
        )
        self.rx_display.setHtml(html)
        self.tx_input.setPlainText("73 und vy tnx fer qso, bis bald de OE3GAS")


# ---------------------------------------------------------------------------
# Thin subclasses — keep the launcher / MainWindow registration working
# ---------------------------------------------------------------------------

class HFPacketScreen(PacketScreen):
    def __init__(self, parent=None):
        super().__init__(band="hf", parent=parent)


class VHFPacketScreen(PacketScreen):
    def __init__(self, parent=None):
        super().__init__(band="vhf", parent=parent)


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

class _TestWindow(QMainWindow):
    def __init__(self, mode: str = "hf"):
        super().__init__()
        self.setWindowTitle(f"PK232PY — Packet Screen Mockup ({mode.upper()})")
        self.resize(1020, 700)
        self.setCentralWidget(PacketScreen(band=mode))


def main() -> None:
    theme, mode, shot = "dark", "hf", ""
    for arg in sys.argv[1:]:
        if arg.startswith("--theme="):
            theme = arg.split("=", 1)[1]
        elif arg.startswith("--mode="):
            mode = arg.split("=", 1)[1]
        elif arg.startswith("--shot="):
            shot = arg.split("=", 1)[1]

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    apply_app_style(app, theme)
    win = _TestWindow(mode=mode)
    win.show()

    if shot:
        # Dev helper: render the window to PNG and quit
        def _grab():
            win.grab().save(shot)
            app.quit()
        QTimer.singleShot(600, _grab)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()