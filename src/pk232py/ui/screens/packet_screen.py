# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""
packet_screen.py  –  HF Packet and VHF Packet opmode screens

Contains:
    ChannelBar         10-chip multi-channel selector/indicator
    MheardPanel        MHEARD list with per-channel column
    PacketBaseScreen   shared base widget — all common UI elements
    HFPacketScreen     subclass: "HF Packet (300 Bd)", HBAUD default 300
    VHFPacketScreen    subclass: "VHF Packet (1200 Bd)", HBAUD default 1200

The two screens share all logic; the only differences are the title,
the HBAUD dropdown default, and the TNC init parameters sent on activation.

Layout (left panel via QSplitter, right panel = MHEARD):

    ┌──────────────────────────────────────────┬──────────────┐
    │ HF Packet   [HF|VHF]  params…   UTC HH:MM│   MHEARD     │
    ├──────────────────────────────────────────┤   Ch Callsign│
    │ MYCALL: [OE3GAS]                 ● STBY  │   Time       │
    ├──────────────────────────────────────────┤   ─────────  │
    │ [Connect][Dest v][…][Disconnect]          │   [Refresh]  │
    │ [Unproto] via:[CQ  ] Monitor:[4]          │   [Clear]    │
    ├──────────────────────────────────────────┤              │
    │ [MailDrop][Files…][Capture][QSOLog] [ALL|CH] HBAUD:[300] [⚙]│
    ├──────────────────────────────────────────┤              │
    │ (hidden) [CONPERM][MAILDROP][MDMON][LITE] │              │
    │          [EAS][PASSALL][MRPT][MID][SQUELCH]│              │
    ├──────────────────────────────────────────┤              │
    │ [0][1][2][3][4][5][6][7][8][9]  ← ChannelBar             │
    ├──────────────────────────────────────────┤              │
    │  RX window  (expands)                     │              │
    ├──────────────────────────────────────────┤              │
    │  TX window (5 lines)      [Hold TX]       │              │
    │                            [Clear TX]     │              │
    │                            [Clear RX]     │              │
    ├──────────────────────────────────────────┤              │
    │  [M1][M2][M3][M4][M5][M6]  [Edit Macros]  │              │
    └──────────────────────────────────────────┴──────────────┘

MainWindow integration notes:
    - Registered as "HF Packet" and "VHF Packet" in _opmode_screens
    - No btn_send / btn_receive — Packet uses Connect/Disconnect instead
    - _wire_screen_buttons() calls _wire_packet_buttons(screen)
    - _make_link_handler() handles "connected"/"disconnect" text → _set_status
    - MYCALL field: set via set_mycall() on mode switch from AppConfig
    - MHEARD Refresh button wired in _wire_packet_buttons()
    - MailDrop button wired in _wire_packet_buttons()
    - Channel routing: MainWindow reads screen.current_channel() instead of
      hardcoding channel 1 (see main_window._on_packet_connect/_disconnect/
      _on_packet_tx_enter).

v0.1 channel model (see CLAUDE.md "Channel model"):
    There is NO CSTATUS poll in Host Mode — the channel a link/data frame
    belongs to is carried in the low nibble of the frame's CTL byte
    (``HostFrame.channel``, already decoded by comm/frame.py). ChannelBar is
    purely a *local* UI concept: it remembers, per channel 0-9, whether we
    last saw that channel free/calling/connected and who the partner is,
    driven entirely by HFPacketMode.on_channel_state (P3). Channel 0 is the
    only channel used outside Packet mode (unproto/monitor default).
"""

from __future__ import annotations

from datetime import datetime, timezone

from PyQt6.QtCore import Qt, QTimer, QEvent, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QLineEdit, QPushButton,
    QComboBox, QFrame, QSizePolicy,
    QScrollArea, QSplitter, QButtonGroup,
    QDialog, QFormLayout, QSpinBox, QDialogButtonBox,
)

from .opmode_rtty_base import (
    MacroStore, MacroEditDialog,
    make_toggle_button, make_help_button, add_hline,
    style_rx_widget, style_tx_widget,
    BTN_W, SPACING, MACRO_COUNT,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CALL_W = 100    # width of callsign QLineEdit/QComboBox fields (px)

# Status label states — dot prefix, same style as PactorScreen
STATUS_STYLES: dict[str, tuple[str, str]] = {
    "STBY":         ("●  STBY",           "#888888"),
    "CALLING":      ("●  CALLING …",      "#cc8800"),
    "CONNECTED":    ("●  CONNECTED",      "#3a9e3a"),
    "DISCONNECTED": ("●  DISCONNECTED",   "#cc4444"),
    "UNPROTO TX":   ("●  UNPROTO TX",     "#2266cc"),
}

# Band metadata for the header band indicator. HFPacketScreen/VHFPacketScreen
# only ever set BAND = "HF"/"VHF" — everything else (HBAUD choices, defaults,
# hint text) is derived from here, but see P1.6: the actual mode switch stays
# with the ModeManager combo box in MainWindow, this is display-only in v0.1.
BANDS: dict[str, dict] = {
    "HF":  {
        "label": "HF 300 Bd",
        "hint": "Params: Configure → HF Packet… (TXDELAY / FRACK / PERSIST)",
    },
    "VHF": {
        "label": "VHF 1200 Bd",
        "hint": "Params: Configure → VHF Packet… (TXDELAY / MAXFRAME / SLOTTIME)",
    },
}

_STYLE_CONNECT_OFF = (
    "QPushButton {"
    "  background-color: #445566; color: white;"
    "  border: 1px solid #334455; border-radius: 4px;"
    "  font-weight: bold; padding: 4px 8px;"
    "}"
    "QPushButton:hover { background-color: #556677; }"
)
_STYLE_CONNECT_ON = (
    "QPushButton {"
    "  background-color: #3a7a3a; color: white;"
    "  border: 2px solid #2a5a2a; border-radius: 4px;"
    "  font-weight: bold; padding: 4px 8px;"
    "}"
)
_STYLE_UNPROTO_OFF = (
    "QPushButton {"
    "  background-color: #445566; color: white;"
    "  border: 1px solid #334455; border-radius: 4px;"
    "  font-weight: bold; padding: 4px 8px;"
    "}"
    "QPushButton:hover { background-color: #556677; }"
)
_STYLE_UNPROTO_ON = (
    "QPushButton {"
    "  background-color: #1a4a7a; color: white;"
    "  border: 2px solid #0a2a5a; border-radius: 4px;"
    "  font-weight: bold; padding: 4px 8px;"
    "}"
)
# APRS decode toggle — amber/orange when active
_STYLE_APRS_OFF = (
    "QPushButton {"
    "  background-color: #445566; color: white;"
    "  border: 1px solid #334455; border-radius: 4px;"
    "  font-weight: bold; padding: 4px 8px;"
    "}"
    "QPushButton:hover { background-color: #556677; }"
)
_STYLE_APRS_ON = (
    "QPushButton {"
    "  background-color: #b06000; color: white;"
    "  border: 2px solid #804000; border-radius: 4px;"
    "  font-weight: bold; padding: 4px 8px;"
    "}"
)
_STYLE_VIEW_ON = (
    "QPushButton {"
    "  background-color: #2266cc; color: white;"
    "  border: 1px solid #1a4d99; border-radius: 3px;"
    "  font-weight: bold;"
    "}"
)
_STYLE_VIEW_OFF = (
    "QPushButton {"
    "  background-color: #445566; color: #cccccc;"
    "  border: 1px solid #334455; border-radius: 3px;"
    "}"
)


def _no_focus_btn(text: str, width: int = BTN_W) -> QPushButton:
    """Button that never steals keyboard focus from the TX window."""
    btn = QPushButton(text)
    btn.setFixedWidth(width)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return btn


# ---------------------------------------------------------------------------
# ChannelBar — 10-chip multi-channel selector (P1.1)
# ---------------------------------------------------------------------------

CHANNEL_COUNT = 10
CHIP_MIN_W = 56

# Chip fill colour per state — CH_FREE / CH_CALLING / CH_CONNECTED
_CHIP_FILL = {
    "free":      "#5a5a5a",
    "calling":   "#cc8800",
    "connected": "#3a9e3a",
}
_CHIP_BORDER_CURRENT = "#ffb400"   # amber, 2px — marks the current channel


class ChannelBar(QWidget):
    """Row of 10 channel chips (0-9) mirroring the PK-232's multi-channel model.

    A chip shows the channel number while free, and the partner callsign once
    a connect attempt is under way or a link is up. Chip fill colour encodes
    state (grey/amber/green); a 2px amber border marks the *current* channel
    — the one Connect/Disconnect/TX actions in PacketBaseScreen act on.

    Lernmodus — why a local model and not a TNC query: the PK-232 Host Mode
    has no CSTATUS command; the channel is only ever known from the CTL
    nibble of frames that already went by (CONNECT/DISCONNECT/data/link-msg).
    So ChannelBar simply remembers what HFPacketMode.on_channel_state told it.
    """

    channel_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current = 1
        self._state: dict[int, str] = {ch: "free" for ch in range(CHANNEL_COUNT)}
        self._partner: dict[int, str] = {ch: "" for ch in range(CHANNEL_COUNT)}
        self._chips: dict[int, QPushButton] = {}

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)

        for ch in range(CHANNEL_COUNT):
            chip = QPushButton()
            chip.setCheckable(True)
            # NoFocus: chips must never steal keyboard focus from tx_input
            # (CLAUDE.md §5 — applies to every QPushButton in the app).
            chip.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            chip.setMinimumWidth(CHIP_MIN_W)
            chip.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            chip.setFixedHeight(34)
            lay = QVBoxLayout(chip)
            lay.setContentsMargins(2, 1, 2, 1)
            lay.setSpacing(0)
            lbl_num = QLabel(str(ch))
            lbl_num.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
            lbl_num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_call = QLabel("")
            lbl_call.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
            lbl_call.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(lbl_num)
            lay.addWidget(lbl_call)
            chip._lbl_num = lbl_num     # stashed for _update_chip()
            chip._lbl_call = lbl_call

            self._group.addButton(chip, ch)
            self._chips[ch] = chip
            row.addWidget(chip, 1)

        self._group.idClicked.connect(self._on_chip_clicked)
        self._select(self._current, emit=False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_channel_state(self, ch: int, state: str, partner: str = "") -> None:
        """Update chip *ch* to *state* ('free'/'calling'/'connected')."""
        if ch not in self._state:
            return
        self._state[ch] = state if state in _CHIP_FILL else "free"
        self._partner[ch] = partner if state != "free" else ""
        self._update_chip(ch)

    def set_current(self, ch: int) -> None:
        """Select *ch* as the current channel (used by Connect/TX)."""
        if ch not in self._chips:
            return
        self._select(ch, emit=True)

    def current(self) -> int:
        return self._current

    def partner(self, ch: int | None = None) -> str:
        return self._partner.get(self._current if ch is None else ch, "")

    def state(self, ch: int | None = None) -> str:
        return self._state.get(self._current if ch is None else ch, "free")

    def channel_map(self) -> dict[str, int]:
        """Return {callsign: channel} for every channel that is currently
        connected or calling. Feeds MheardPanel.set_channel_map()."""
        return {
            call: ch
            for ch, call in self._partner.items()
            if call and self._state.get(ch) in ("connected", "calling")
        }

    def step(self, delta: int) -> None:
        """Move the current channel by *delta*, wrapping 0..9."""
        self._select((self._current + delta) % CHANNEL_COUNT, emit=True)

    def reset(self) -> None:
        """Set every chip back to 'free' with no partner.

        Called on mode activation and on leaving Host Mode — otherwise a
        stale CONNECTED/CALLING chip from an earlier session (or from a
        connection that was never explicitly torn down before the TNC
        dropped out of Host Mode) would sit there with no frame left to
        clear it. Does NOT change which channel is current.
        """
        for ch in range(CHANNEL_COUNT):
            self._state[ch] = "free"
            self._partner[ch] = ""
            self._update_chip(ch)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_chip_clicked(self, ch: int) -> None:
        self._select(ch, emit=True)

    def _select(self, ch: int, emit: bool) -> None:
        changed = ch != self._current
        self._current = ch
        self._group.blockSignals(True)
        self._chips[ch].setChecked(True)
        self._group.blockSignals(False)
        for c in self._chips:
            self._update_chip(c)
        if emit and changed:
            self.channel_changed.emit(ch)

    def _update_chip(self, ch: int) -> None:
        chip = self._chips[ch]
        state = self._state[ch]
        partner = self._partner[ch]
        is_current = ch == self._current

        chip._lbl_num.setText(str(ch))
        chip._lbl_call.setText(partner if partner else "")

        fill = _CHIP_FILL.get(state, _CHIP_FILL["free"])
        border = _CHIP_BORDER_CURRENT if is_current else "#333333"
        border_w = 2 if is_current else 1
        chip.setStyleSheet(
            "QPushButton {"
            f"  background-color: {fill}; color: white;"
            f"  border: {border_w}px solid {border}; border-radius: 4px;"
            "}"
        )
        chip.setToolTip(
            f"Channel {ch}\n"
            f"State: {state}\n"
            f"Partner: {partner or '—'}\n"
            "Click to select as the current channel for Connect/TX.\n"
            "Ctrl+Up / Ctrl+Down steps through channels."
        )


# ---------------------------------------------------------------------------
# MheardPanel
# ---------------------------------------------------------------------------

class _MheardRowWidget(QWidget):
    """One MHEARD row. Emits `activated(call, connected)` on double-click."""

    activated = pyqtSignal(str, bool)

    def __init__(self, callsign: str, time_str: str, direct: bool,
                 channel: int | None, parent=None):
        super().__init__(parent)
        self._callsign = callsign
        self._connected = channel is not None

        rl = QHBoxLayout(self)
        rl.setContentsMargins(4, 1, 4, 1)
        rl.setSpacing(4)

        # Channel column: channel number + space when connected, else two
        # spaces (T87) so callsigns still line up in the monospace font.
        ch_prefix = f"{channel}" if channel is not None else " "
        display = f"{ch_prefix} {callsign} *" if direct else f"{ch_prefix} {callsign}"
        lbl_c = QLabel(display)
        lbl_c.setFont(QFont("Courier New", 9))
        if self._connected:
            lbl_c.setStyleSheet("color: #ffb400;")   # amber = connected station
        else:
            lbl_c.setStyleSheet("color: #66ee66;" if direct else "color: #88ccff;")
        lbl_t = QLabel(time_str)
        lbl_t.setFont(QFont("Courier New", 9))
        lbl_t.setAlignment(Qt.AlignmentFlag.AlignRight)
        rl.addWidget(lbl_c)
        rl.addStretch()
        rl.addWidget(lbl_t)

        tip = (f"Connected on channel {channel} — double-click to switch to it."
               if self._connected else
               f"Double-click to fill “{callsign}” into Dest.")
        self.setToolTip(tip)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.activated.emit(self._callsign, self._connected)
        super().mouseDoubleClickEvent(event)


class MheardPanel(QWidget):
    """Scrollable list of heard AX.25 stations (MHEARD).

    Public API (called from MainWindow / PacketBaseScreen):
        add_entry(callsign, time_str, direct=False)
        set_channel_map(mapping)   — {callsign: channel} of connected stations
        clear()
        btn_refresh   — connect clicked to MainWindow._on_packet_mheard()
        connect_requested(str)     — double-click on an unconnected station
        channel_requested(int)     — double-click on a connected station
    """

    connect_requested = pyqtSignal(str)
    channel_requested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: list[tuple[str, str, bool]] = []
        self._channel_map: dict[str, int] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        lbl = QLabel("MHEARD")
        lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        root.addWidget(lbl)

        hdr = QHBoxLayout()
        hdr.setContentsMargins(4, 0, 4, 0)
        hdr_c = QLabel("Ch  Callsign")
        hdr_c.setFont(QFont("Segoe UI", 8))
        hdr_t = QLabel("Time")
        hdr_t.setFont(QFont("Segoe UI", 8))
        hdr_t.setAlignment(Qt.AlignmentFlag.AlignRight)
        hdr.addWidget(hdr_c)
        hdr.addWidget(hdr_t)
        root.addLayout(hdr)

        add_hline(root)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(1)
        self._list_layout.addStretch()
        scroll.setWidget(self._list_widget)
        root.addWidget(scroll, stretch=1)

        add_hline(root)

        lbl_legend = QLabel("* = direct (no digi)  |  amber = connected")
        lbl_legend.setFont(QFont("Segoe UI", 8))
        root.addWidget(lbl_legend)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        # Wired by MainWindow._wire_packet_buttons()
        self.btn_refresh = _no_focus_btn("Refresh", 64)
        self.btn_refresh.setToolTip("Request MHEARD list from TNC (mnemonic MH).")

        self.btn_clear = _no_focus_btn("Clear", 64)
        self.btn_clear.setToolTip("Clear the MHEARD list locally.")
        self.btn_clear.clicked.connect(self.clear)

        btn_row.addWidget(self.btn_refresh)
        btn_row.addWidget(self.btn_clear)
        root.addLayout(btn_row)

    def add_entry(self, callsign: str, time_str: str, direct: bool = False) -> None:
        """Add one entry at the top of the MHEARD list."""
        self._entries.insert(0, (callsign, time_str, direct))
        self._render()

    def set_channel_map(self, mapping: dict[str, int]) -> None:
        """Update which callsigns are currently connected on which channel.

        Called whenever ChannelBar state changes so MHEARD rows for those
        callsigns show the channel column and render amber (T87).
        """
        self._channel_map = dict(mapping)
        self._render()

    def clear(self) -> None:
        """Remove all entries from the list."""
        self._entries.clear()
        self._render()

    def _render(self) -> None:
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for callsign, time_str, direct in self._entries:
            channel = self._channel_map.get(callsign)
            row = _MheardRowWidget(callsign, time_str, direct, channel)
            row.activated.connect(self._on_row_activated)
            self._list_layout.insertWidget(self._list_layout.count() - 1, row)

    def _on_row_activated(self, callsign: str, connected: bool) -> None:
        if connected:
            ch = self._channel_map.get(callsign)
            if ch is not None:
                self.channel_requested.emit(ch)
        else:
            self.connect_requested.emit(callsign)


# ---------------------------------------------------------------------------
# PacketConnectDialog — "..." button next to Dest (advanced connect options)
# ---------------------------------------------------------------------------

class PacketConnectDialog(QDialog):
    """Minimal advanced-connect dialog: channel + digipeater path.

    v0.1: no persistence across sessions (Backlog Priority 2 item
    "Connect-Dialog-Persistenz"). Returns (channel, path) via exec()/fields().
    """

    def __init__(self, current_channel: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Packet Connect — advanced")
        form = QFormLayout(self)

        self.spin_channel = QSpinBox()
        self.spin_channel.setRange(0, CHANNEL_COUNT - 1)
        self.spin_channel.setValue(current_channel)
        form.addRow("Channel:", self.spin_channel)

        self.le_path = QLineEdit()
        self.le_path.setPlaceholderText("e.g. OE1ABC-8 (digipeater, optional)")
        form.addRow("Via:", self.le_path)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def channel(self) -> int:
        return self.spin_channel.value()

    def path(self) -> str:
        return self.le_path.text().strip().upper()


# ---------------------------------------------------------------------------
# PacketBaseScreen
# ---------------------------------------------------------------------------

class PacketBaseScreen(QWidget):
    """Shared base for HF Packet and VHF Packet screens.

    Subclasses override:
        MODE_TITLE      title label text
        BAND            "HF" or "VHF" — key into BANDS
        HBAUD_VALUES    HBAUD dropdown choices
        HBAUD_DEFAULT   pre-selected HBAUD value
        MONITOR_DEFAULT pre-selected Monitor level

    Attributes accessed by MainWindow (see CLAUDE.md hard constraints — these
    names must not change):
        mheard_panel, mheard_panel.btn_refresh, mheard_panel.btn_clear
        btn_connect, btn_disconnect, btn_unproto, btn_maildrop, btn_aprs
        btn_eas, btn_passall, btn_mrpt, btn_mid, btn_squelch
        combo_hbaud, combo_monitor, rx_display, tx_input, macro_buttons
        set_mycall(), set_link_state(), on_connect_toggled(),
        on_unproto_toggled(), _set_status()

    New in this sprint (channel model + regrouped rows):
        channel_bar, cb_dest, dest_callsign(), set_dest_callsign(),
        append_channel_data(), append_monitor_data(), set_view_all(),
        current_channel()
    """

    MODE_TITLE      = "Packet"
    MODE_SUFFIX     = ""
    HELP_TOPIC      = "packet"   # HF → "packet", VHF overrides to "vhf"
    BAND            = "HF"
    HBAUD_VALUES    = ["300", "1200"]
    HBAUD_DEFAULT   = "300"
    MONITOR_DEFAULT = "4"

    # Signals connected automatically by MainWindow._wire_mode_callbacks().
    # Declared on the base class → HF and VHF Packet inherit them.
    clear_tx_req = pyqtSignal()
    clear_rx_req = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._view_all = True   # ALL vs CH RX filter (P1.4)

        self._macro_store = MacroStore()
        err = self._macro_store.load()
        if err:
            import logging
            logging.getLogger(__name__).warning("MacroStore: %s", err)

        self._utc_timer = QTimer(self)
        self._utc_timer.setInterval(1000)
        self._utc_timer.timeout.connect(self._update_utc)
        self._utc_timer.start()

        self._build_ui()

        # ScreenFocusController: tracks focus on editable QLineEdit fields.
        # cb_dest is an editable QComboBox — its internal QLineEdit is what
        # actually receives focus, so that (not the QComboBox) is registered.
        # lbl_mycall is a QLabel — no focus tracking needed.
        from .screen_focus_controller import ScreenFocusController
        self.focus_ctrl = ScreenFocusController(
            fields=[self.cb_dest.lineEdit(), self.le_unproto],
            parent=self,
        )

        # Pure UI wiring (no TNC frame, so no MainWindow round-trip needed):
        # double-clicking an MHEARD row either fills Dest or switches channel.
        self.mheard_panel.connect_requested.connect(self.set_dest_callsign)
        self.mheard_panel.channel_requested.connect(self.channel_bar.set_current)

        # Intercept Enter in tx_input → send as AX.25 DATA frame.
        # _packet_send_slot is set by MainWindow._wire_mode_callbacks().
        self.tx_input._packet_send_slot = None
        self.tx_input.installEventFilter(self)
        QTimer.singleShot(0, lambda: self.tx_input.setFocus())

        # Central tooltips. The MHEARD panel is a separate QWidget with its own
        # buttons (btn_refresh / btn_clear), so it needs its own apply_tooltips
        # pass — those are in tooltips.SCREEN_TOOLTIPS["MheardPanel"].
        from pk232py.ui.tooltips import apply_tooltips
        apply_tooltips(self)
        apply_tooltips(self.mheard_panel)

    # ------------------------------------------------------------------
    # EventFilter — identical to PactorScreen / AmtorScreen, plus
    # Hold TX (suppress Enter-to-send) and Ctrl+Up/Down channel stepping.
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event) -> bool:
        # Enter / Return in tx_input → send as AX.25 DATA frame, unless
        # Hold TX is engaged (then let QTextEdit insert a literal newline —
        # Packet has no TxController/[^D] EOT concept, so "hold" just means
        # "compose a multi-line message before sending").
        if (event.type() == QEvent.Type.KeyPress
                and obj is getattr(self, 'tx_input', None)):
            from PyQt6.QtCore import Qt as _Qt
            if event.key() in (_Qt.Key.Key_Return, _Qt.Key.Key_Enter):
                if self.btn_hold_tx.isChecked():
                    return False
                slot = getattr(self.tx_input, '_packet_send_slot', None)
                if slot is not None:
                    slot()
                return True   # consume — do not insert newline
            # Ctrl+Up / Ctrl+Down steps the current channel (T84). Plain
            # Up/Down are left alone — tx_input needs them for cursor
            # movement while composing a message.
            if event.key() in (_Qt.Key.Key_Up, _Qt.Key.Key_Down) and \
                    event.modifiers() & _Qt.KeyboardModifier.ControlModifier:
                self.channel_bar.step(-1 if event.key() == _Qt.Key.Key_Up else 1)
                return True
        if event.type() == QEvent.Type.KeyPress:
            # Walk parent chain: in an app-wide filter obj may be an
            # internal child widget, not the QLineEdit/QTextEdit itself.
            def _is_input(w):
                while w is not None:
                    if isinstance(w, (QTextEdit, QLineEdit)):
                        return True
                    w = w.parent()
                return False
            if _is_input(self.focusWidget()) or _is_input(obj):
                return super().eventFilter(obj, event)
            if hasattr(self, "tx_input") and self.tx_input is not None:
                self.tx_input.setFocus()
                QApplication.sendEvent(self.tx_input, event)
                return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _update_utc(self) -> None:
        now = datetime.now(timezone.utc)
        self.lbl_utc.setText(now.strftime("UTC  %H:%M:%S"))

    def _set_status(self, state: str) -> None:
        """Update status label. Called by MainWindow._make_link_handler()."""
        text, color = STATUS_STYLES.get(state, (f"●  {state}", "#888888"))
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet(
            f"color: {color}; font-weight: bold; font-size: 10pt;"
        )

    def set_mycall(self, callsign: str) -> None:
        """Update the MYCALL display label. Called by MainWindow on mode switch."""
        self.lbl_mycall.setText(callsign.upper() if callsign else "---")

    # ------------------------------------------------------------------
    # Dest field (P1.3) — cb_dest is an editable QComboBox; MainWindow talks
    # to it only through these two methods, never .text()/.currentText().
    # ------------------------------------------------------------------

    def dest_callsign(self) -> str:
        """Return the trimmed, uppercased destination callsign (may include
        a ' VIA ...' digipeater path — connect_frame() accepts that as-is)."""
        return self.cb_dest.currentText().strip().upper()

    def set_dest_callsign(self, call: str) -> None:
        """Set the Dest field (e.g. from an MHEARD double-click)."""
        self.cb_dest.setCurrentText(call.strip().upper())

    def add_dest_history(self, callsign: str) -> None:
        """Remember *callsign* at the top of the Dest history (max 10)."""
        callsign = callsign.strip().upper()
        if not callsign:
            return
        idx = self.cb_dest.findText(callsign)
        if idx >= 0:
            self.cb_dest.removeItem(idx)
        self.cb_dest.insertItem(0, callsign)
        self.cb_dest.setCurrentIndex(0)
        while self.cb_dest.count() > 10:
            self.cb_dest.removeItem(self.cb_dest.count() - 1)

    def _on_connect_dialog(self) -> None:
        """'...' button next to Dest — pick channel + optional digi path."""
        dlg = PacketConnectDialog(self.channel_bar.current(), parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.channel_bar.set_current(dlg.channel())
            path = dlg.path()
            if path:
                base = self.dest_callsign()
                self.set_dest_callsign(f"{base} VIA {path}" if base else "")

    # ------------------------------------------------------------------
    # Channel-bound RX (P1.4) — filtering happens at append time, not by
    # rebuilding the buffer: switching channel or ALL/CH does NOT redraw
    # history (deliberate v0.1 simplification, see module docstring / P1.4).
    # ------------------------------------------------------------------

    def current_channel(self) -> int:
        return self.channel_bar.current()

    def reset_channels(self) -> None:
        """Clear all channel state — every chip back to free, MHEARD channel
        column cleared. Called by MainWindow when the mode is (re)activated
        and when leaving Host Mode (see _switch_opmode()/_update_host_mode_ui()
        in main_window.py) — without this, a CONNECTED/CALLING chip from a
        previous session would linger with no frame ever left to clear it.
        """
        self.channel_bar.reset()
        self.mheard_panel.set_channel_map({})

    def set_view_all(self, show_all: bool) -> None:
        self._view_all = show_all

    def append_channel_data(self, channel: int, text: str) -> None:
        """Append received connected-channel data, honouring the ALL/CH filter."""
        if not (self._view_all or channel == self.current_channel()):
            return
        prefix = f"[CH{channel}] " if self._view_all else ""
        self._rx_append(prefix + text, is_html=False, color="#66ccff")

    def append_monitor_data(self, text: str, is_html: bool = False,
                             ts: str = "") -> None:
        """Append a monitored/unproto frame. Not channel-scoped — unlike
        connected data, monitor traffic is always shown regardless of the
        ALL/CH filter (it never belonged to a specific connected channel).

        `ts` is optional and only used by MainWindow._packet_rx_redraw() to
        replay a HISTORICAL timestamp when the user toggles APRS decode
        on/off (T59/T60 — that redraw re-renders the whole buffer and must
        not relabel every old frame with "now"). Live callers omit it and
        get the current UTC time, same as append_channel_data().
        """
        self._rx_append(text, is_html=is_html, color="#aaaaaa", ts=ts)

    def _rx_append(self, text: str, is_html: bool, color: str,
                    ts: str = "") -> None:
        if not ts:
            ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        from PyQt6.QtGui import QTextCursor, QColor, QTextCharFormat
        cursor = self.rx_display.textCursor()
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
            lines = text.splitlines() or [""]
            cursor.insertText(f"[{ts}] {lines[0]}\n")
            for line in lines[1:]:
                cursor.insertText(f"         {line}\n")
            cursor.insertText("\n")
        self.rx_display.setTextCursor(cursor)
        self.rx_display.ensureCursorVisible()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # ── Left: communication area ───────────────────────────────────
        left = QWidget()
        root = QVBoxLayout(left)
        root.setSpacing(6)
        root.setContentsMargins(8, 8, 8, 8)

        # 1. Title row: title + band indicator + param hint + UTC ──────
        title_row = QHBoxLayout()
        lbl_title = QLabel(self.MODE_TITLE)
        lbl_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        lbl_title.setTextFormat(Qt.TextFormat.PlainText)
        title_row.addWidget(lbl_title)

        band_info = BANDS.get(self.BAND, BANDS["HF"])
        # v0.1: display-only (P1.6) — the screen cannot itself trigger a
        # ModeManager mode switch, so this button just shows which band this
        # screen instance is; the real switch stays on the opmode ComboBox.
        self.btn_band = QPushButton(band_info["label"])
        self.btn_band.setEnabled(False)
        self.btn_band.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_band.setToolTip(
            "Band indicator (read-only in v0.1).\n"
            "Switch HF ↔ VHF Packet via the operating-mode selector."
        )
        title_row.addSpacing(8)
        title_row.addWidget(self.btn_band)

        self.lbl_param_hint = QLabel(band_info["hint"])
        self.lbl_param_hint.setFont(QFont("Segoe UI", 8))
        self.lbl_param_hint.setStyleSheet("color: #888888;")
        title_row.addSpacing(8)
        title_row.addWidget(self.lbl_param_hint)

        title_row.addStretch()
        self.lbl_utc = QLabel()
        self.lbl_utc.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self.lbl_utc.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._update_utc()
        title_row.addWidget(self.lbl_utc)
        title_row.addWidget(make_help_button(self.HELP_TOPIC))
        root.addLayout(title_row)

        add_hline(root)

        # 2. Identity row: MYCALL … status ──────────────────────────────
        id_row = QHBoxLayout()
        id_row.setSpacing(8)

        lbl_mycall = QLabel("MYCALL:")
        lbl_mycall.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        id_row.addWidget(lbl_mycall)

        # Read-only — populated by MainWindow via set_mycall()
        self.lbl_mycall = QLabel("---")
        self.lbl_mycall.setFixedWidth(CALL_W)
        self.lbl_mycall.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self.lbl_mycall.setToolTip(
            "Your AX.25 callsign (MYCALL / mnemonic ML).\n"
            "Set via TNC → Configure → TNC Parameters."
        )
        id_row.addWidget(self.lbl_mycall)
        id_row.addStretch()

        self.lbl_status = QLabel()
        self.lbl_status.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self._set_status("STBY")
        id_row.addWidget(self.lbl_status)
        root.addLayout(id_row)

        add_hline(root)

        # 3. Connect row: Connect · Dest · ... · Disconnect ────────────
        connect_row = QHBoxLayout()
        connect_row.setSpacing(SPACING)

        self.btn_connect = _no_focus_btn("Connect", BTN_W)
        self.btn_connect.setCheckable(True)
        self.btn_connect.setStyleSheet(_STYLE_CONNECT_OFF)
        self.btn_connect.setToolTip(
            "Initiate AX.25 CONNECT to Dest callsign on the current channel\n"
            "(see the channel bar below). TNC mnemonic: CO (connect channel)"
        )
        connect_row.addWidget(self.btn_connect)

        self.cb_dest = QComboBox()
        self.cb_dest.setEditable(True)
        self.cb_dest.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.cb_dest.setFixedWidth(CALL_W + 20)
        self.cb_dest.lineEdit().setMaxLength(20)
        self.cb_dest.setFont(QFont("Courier New", 10))
        self.cb_dest.lineEdit().setPlaceholderText("e.g. OE3XYZ")
        self.cb_dest.setToolTip(
            "Destination callsign for AX.25 CONNECT.\n"
            "May include SSID and a digipeater path, e.g.\n"
            "OE3XYZ-9 or OE3XYZ-9 VIA OE1ABC-8.\n"
            "Dropdown remembers recently used callsigns."
        )
        connect_row.addWidget(self.cb_dest)

        self.btn_connect_dialog = _no_focus_btn("…", 28)
        self.btn_connect_dialog.setToolTip(
            "Advanced connect options: pick the channel and an optional\n"
            "digipeater path before connecting."
        )
        self.btn_connect_dialog.clicked.connect(self._on_connect_dialog)
        connect_row.addWidget(self.btn_connect_dialog)

        self.btn_disconnect = _no_focus_btn("Disconnect", BTN_W)
        self.btn_disconnect.setToolTip(
            "Send AX.25 DISCONNECT on the current channel.\n"
            "TNC mnemonic: DI (disconnect channel)"
        )
        self.btn_disconnect.setEnabled(False)
        connect_row.addWidget(self.btn_disconnect)
        connect_row.addStretch()
        root.addLayout(connect_row)

        # 4. Unproto row: Unproto · via · Monitor ───────────────────────
        unproto_row = QHBoxLayout()
        unproto_row.setSpacing(SPACING)

        self.btn_unproto = _no_focus_btn("Unproto", BTN_W)
        self.btn_unproto.setCheckable(True)
        self.btn_unproto.setStyleSheet(_STYLE_UNPROTO_OFF)
        self.btn_unproto.setToolTip(
            "Send unconnected UI frames (no ARQ, no acknowledge).\n"
            "Path set in the via field."
        )
        unproto_row.addWidget(self.btn_unproto)

        lbl_via = QLabel("via:")
        lbl_via.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        unproto_row.addWidget(lbl_via)

        self.le_unproto = QLineEdit("CQ")
        self.le_unproto.setMaxLength(40)
        self.le_unproto.setFixedWidth(120)
        self.le_unproto.setFont(QFont("Courier New", 10))
        self.le_unproto.setToolTip(
            "Unproto destination and digipeater path (mnemonic UN).\n"
            "Examples: CQ   CQ VIA RELAY   CQ VIA OE3XNR-8"
        )
        unproto_row.addWidget(self.le_unproto)
        unproto_row.addSpacing(12)

        lbl_mon = QLabel("Monitor:")
        lbl_mon.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        unproto_row.addWidget(lbl_mon)

        self.combo_monitor = QComboBox()
        self.combo_monitor.addItems(["0", "1", "2", "3", "4", "5", "6"])
        self.combo_monitor.setCurrentText(self.MONITOR_DEFAULT)
        self.combo_monitor.setFixedWidth(50)
        self.combo_monitor.setToolTip(
            "Monitor level (MONITOR / mnemonic MN):\n"
            "0=off  1=UI  2=+I  3=+C/D  4=default  5=+RR  6=+poll"
        )
        unproto_row.addWidget(self.combo_monitor)

        # APRS decode toggle — visible on any APRS_CAPABLE screen (HF + VHF;
        # kept on both, unchanged from the already-verified APRS-on-HF sprint
        # — see CLAUDE.md "APRS on HF Packet").
        self.btn_aprs = _no_focus_btn("APRS", BTN_W)
        self.btn_aprs.setCheckable(True)
        self.btn_aprs.setStyleSheet(_STYLE_APRS_OFF)
        self.btn_aprs.setToolTip(
            "APRS decode mode.\n"
            "ON: all monitored frames (including already received)\n"
            "    are decoded into human-readable APRS format.\n"
            "OFF: restores the original raw monitor display."
        )
        unproto_row.addWidget(self.btn_aprs)
        self.btn_aprs.setVisible(getattr(self, "APRS_CAPABLE", False))

        unproto_row.addStretch()
        root.addLayout(unproto_row)

        add_hline(root)

        # 5. Tool row: MailDrop / Files / Capture / QSO Log — ALL|CH / HBAUD / gear
        tool_row = QHBoxLayout()
        tool_row.setSpacing(SPACING)

        # MailDrop login (MDCHECK, mnemonic MI) — already hardware/mock
        # verified (T47 PASS), kept enabled. NOTE mnemonic conflict: MI is
        # ALSO used by btn_mid (Morse ID beacon) below — the mnemonic table
        # scan maps MI to MFILTER; this is a pre-existing, documented
        # ambiguity (see CLAUDE.md "Offene Mnemonics" / Backlog), behaviour
        # intentionally left unchanged.
        self.btn_maildrop = _no_focus_btn("MailDrop", BTN_W)
        self.btn_maildrop.setToolTip(
            "Log in to TNC MailDrop (MDCHECK).\n"
            "Only available when not connected."
        )
        tool_row.addWidget(self.btn_maildrop)

        # Files / QSO Log: not implemented in v0.1 (Backlog Priority 2) —
        # built and visible so the row layout matches the approved mockup,
        # but disabled rather than faked with a QMessageBox stub.
        self.btn_files = _no_focus_btn("Files…", BTN_W)
        self.btn_files.setEnabled(False)
        self.btn_files.setToolTip("File transfer — not implemented in v0.1.")
        tool_row.addWidget(self.btn_files)

        self.btn_capture = _no_focus_btn("Capture", BTN_W)
        self.btn_capture.setCheckable(True)
        self.btn_capture.setToolTip(
            "Capture — record all received traffic (every channel, "
            "independent of the ALL/CH view) to a text file."
        )
        tool_row.addWidget(self.btn_capture)

        self.btn_qsolog = _no_focus_btn("QSO Log", BTN_W)
        self.btn_qsolog.setEnabled(False)
        self.btn_qsolog.setToolTip("QSO Log — not implemented in v0.1.")
        tool_row.addWidget(self.btn_qsolog)

        tool_row.addStretch()

        # ALL / CH view switch — two exclusive buttons (P2.1 wires
        # btn_view_all.clicked / btn_view_ch.clicked separately).
        self.btn_view_all = _no_focus_btn("ALL", 44)
        self.btn_view_ch = _no_focus_btn("CH", 44)
        self.btn_view_all.setCheckable(True)
        self.btn_view_ch.setCheckable(True)
        self.btn_view_all.setChecked(True)
        self.btn_view_all.setStyleSheet(_STYLE_VIEW_ON)
        self.btn_view_ch.setStyleSheet(_STYLE_VIEW_OFF)
        self.btn_view_all.setToolTip("Show received data from every channel.")
        self.btn_view_ch.setToolTip("Show received data from the current channel only.")
        self._view_group = QButtonGroup(self)
        self._view_group.setExclusive(True)
        self._view_group.addButton(self.btn_view_all)
        self._view_group.addButton(self.btn_view_ch)
        self.btn_view_all.toggled.connect(self._on_view_toggled)
        tool_row.addWidget(self.btn_view_all)
        tool_row.addWidget(self.btn_view_ch)

        tool_row.addSpacing(8)
        lbl_hbaud = QLabel("HBAUD:")
        lbl_hbaud.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        tool_row.addWidget(lbl_hbaud)

        self.combo_hbaud = QComboBox()
        self.combo_hbaud.addItems(self.HBAUD_VALUES)
        self.combo_hbaud.setCurrentText(self.HBAUD_DEFAULT)
        self.combo_hbaud.setFixedWidth(68)
        self.combo_hbaud.setToolTip(
            "Host baud rate (HBAUD / mnemonic HB).\n"
            "HF Packet: 300   VHF Packet: 1200"
        )
        tool_row.addWidget(self.combo_hbaud)

        self.btn_options = _no_focus_btn("⚙", 28)
        self.btn_options.setCheckable(True)
        self.btn_options.setToolTip("Show/hide additional toggles (CONPERM, MAILDROP, …).")
        self.btn_options.toggled.connect(self._on_options_toggled)
        tool_row.addWidget(self.btn_options)

        root.addLayout(tool_row)

        # 6. Options row (hidden by default) ────────────────────────────
        self._options_container = QWidget()
        opt_root = QVBoxLayout(self._options_container)
        opt_root.setContentsMargins(0, 0, 0, 0)
        opt_root.setSpacing(4)

        opt_row1 = QHBoxLayout()
        opt_row1.setSpacing(SPACING)
        # These four mnemonics are NOT confirmed against the TRM / mnemonic
        # table in this sprint (no TRM/pk232_mnemonic_table.txt available) —
        # per the hard "never guess a mnemonic" rule, the buttons are built
        # and wired, but they only log a TODO and send NOTHING to the TNC.
        self.btn_conperm = make_toggle_button("CONPERM")
        self.btn_mailbox = make_toggle_button("MAILDROP")
        self.btn_mdmon   = make_toggle_button("MDMON")
        self.btn_lite    = make_toggle_button("LITE")
        self.btn_conperm.setToolTip(
            "CONPERM — permanent connect state on power-up.\n"
            "# TODO mnemonic unverified (candidate CY) — no frame sent."
        )
        self.btn_mailbox.setToolTip(
            "MAILDROP — enable/disable the mailbox feature.\n"
            "# TODO mnemonic unverified — no frame sent."
        )
        self.btn_mdmon.setToolTip(
            "MDMON — monitor MailDrop traffic.\n"
            "# TODO mnemonic unverified — no frame sent."
        )
        self.btn_lite.setToolTip(
            "LITE — (meaning to be confirmed against the TRM).\n"
            "# TODO mnemonic unverified — no frame sent."
        )
        for btn in (self.btn_conperm, self.btn_mailbox, self.btn_mdmon, self.btn_lite):
            opt_row1.addWidget(btn)
        opt_row1.addStretch()
        opt_root.addLayout(opt_row1)

        opt_row2 = QHBoxLayout()
        opt_row2.setSpacing(SPACING)
        self.btn_eas      = make_toggle_button("EAS")
        self.btn_passall  = make_toggle_button("PASSALL")
        self.btn_mrpt     = make_toggle_button("MRPT")
        self.btn_mid      = make_toggle_button("MID")
        self.btn_squelch  = make_toggle_button("SQUELCH")
        self.btn_eas.setToolTip("Echo As Sent (EA) — show confirmed TX chars in RX window.")
        self.btn_passall.setToolTip("PASSALL (PS) — receive all frames regardless of CRC.")
        self.btn_mrpt.setToolTip("Monitor Repeat (MR) — show digipeated frames.")
        self.btn_mid.setToolTip(
            "Morse ID beacon (MI) — enable periodic Morse ID.\n"
            "NOTE: shares mnemonic MI with the MailDrop login button above\n"
            "(documented TRM ambiguity — see CLAUDE.md)."
        )
        self.btn_squelch.setToolTip("SQUELCH (SQ) — suppress duplicate frames.")
        for btn in (self.btn_eas, self.btn_passall, self.btn_mrpt,
                    self.btn_mid, self.btn_squelch):
            opt_row2.addWidget(btn)
        opt_row2.addStretch()
        opt_root.addLayout(opt_row2)

        self._options_container.setVisible(False)
        root.addWidget(self._options_container)

        add_hline(root)

        # 7. ChannelBar ──────────────────────────────────────────────────
        self.channel_bar = ChannelBar()
        root.addWidget(self.channel_bar)

        add_hline(root)

        # 8. RX window ─────────────────────────────────────────────────
        self.rx_display = QTextEdit()
        self.rx_display.setReadOnly(True)
        self.rx_display.setFont(QFont("Courier New", 10))
        self.rx_display.setPlaceholderText(
            "RX — received and monitored AX.25 frames appear here …\n\n"
            "Connected data:   $3x frames (channel data)\n"
            "Monitored frames: $3F frames (unproto / UI)"
        )
        self.rx_display.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        style_rx_widget(self.rx_display)
        root.addWidget(self.rx_display, stretch=1)

        add_hline(root)

        # 9. TX window — 5 lines, block cursor + side button column ─────
        tx_row = QHBoxLayout()
        tx_row.setSpacing(SPACING)

        self.tx_input = QTextEdit()
        self.tx_input.setFont(QFont("Courier New", 10))
        self.tx_input.setPlaceholderText("TX — type here …")
        fm = self.tx_input.fontMetrics()
        mc = self.tx_input.contentsMargins()
        self.tx_input.setFixedHeight(
            fm.lineSpacing() * 5 + mc.top() + mc.bottom() + 8
        )
        style_tx_widget(self.tx_input)
        self.tx_input.setCursorWidth(
            self.tx_input.fontMetrics().averageCharWidth()
        )
        tx_row.addWidget(self.tx_input, stretch=1)

        tx_btn_col = QVBoxLayout()
        tx_btn_col.setSpacing(4)

        self.btn_hold_tx = _no_focus_btn("Hold TX", BTN_W)
        self.btn_hold_tx.setCheckable(True)
        self.btn_hold_tx.setToolTip(
            "Hold TX — while ON, Enter inserts a newline instead of\n"
            "sending (compose a multi-line message first). Packet has no\n"
            "TxController/[^D] EOT concept, so this is a pure UI convenience."
        )
        tx_btn_col.addWidget(self.btn_hold_tx)

        # Clear TX / Clear RX — emit signals handled by MainWindow.
        self.btn_clear_tx = _no_focus_btn("Clear TX", BTN_W)
        self.btn_clear_tx.clicked.connect(self.clear_tx_req.emit)
        tx_btn_col.addWidget(self.btn_clear_tx)

        self.btn_clear_rx = _no_focus_btn("Clear RX", BTN_W)
        self.btn_clear_rx.clicked.connect(self.clear_rx_req.emit)
        tx_btn_col.addWidget(self.btn_clear_rx)

        tx_btn_col.addStretch()
        tx_row.addLayout(tx_btn_col)
        root.addLayout(tx_row)

        add_hline(root)

        # 10. Macro bar ──────────────────────────────────────────────────
        macro_row = QHBoxLayout()
        macro_row.setSpacing(SPACING)
        self.macro_buttons: list[QPushButton] = []
        for i in range(MACRO_COUNT):
            btn = _no_focus_btn(self._macro_store.names[i], BTN_W)
            macro_row.addWidget(btn)
            self.macro_buttons.append(btn)
        macro_row.addStretch()

        self.btn_edit_macros = _no_focus_btn("Edit Macros", BTN_W + 20)
        # No stylesheet → palette-driven, readable in every theme.
        self.btn_edit_macros.clicked.connect(self._on_edit_macros)
        macro_row.addWidget(self.btn_edit_macros)
        root.addLayout(macro_row)

        # ── Right: MHEARD panel ────────────────────────────────────────
        self.mheard_panel = MheardPanel()
        self.mheard_panel.setMinimumWidth(150)
        self.mheard_panel.setMaximumWidth(240)

        splitter.addWidget(left)
        splitter.addWidget(self.mheard_panel)
        splitter.setSizes([540, 160])
        outer.addWidget(splitter)

        # Status bar (full width, below the splitter): channel, partner,
        # capture state, RX buffer size, band + last VHF mnemonic sent.
        self._status_bar = self._build_status_bar()
        outer.addWidget(self._status_bar)
        self.channel_bar.channel_changed.connect(self._update_status_bar)
        self._update_status_bar(self.channel_bar.current())

    def _build_status_bar(self) -> QWidget:
        bar = QFrame()
        bar.setFrameShape(QFrame.Shape.StyledPanel)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(8, 2, 8, 2)
        lay.setSpacing(16)
        small = QFont("Segoe UI", 8)

        self.lbl_sb_channel = QLabel()
        self.lbl_sb_channel.setFont(small)
        lay.addWidget(self.lbl_sb_channel)

        self.lbl_sb_partner = QLabel()
        self.lbl_sb_partner.setFont(small)
        lay.addWidget(self.lbl_sb_partner)

        self.lbl_sb_capture = QLabel("Capture: off")
        self.lbl_sb_capture.setFont(small)
        lay.addWidget(self.lbl_sb_capture)

        self.lbl_sb_rxsize = QLabel("RX: 0 lines")
        self.lbl_sb_rxsize.setFont(small)
        lay.addWidget(self.lbl_sb_rxsize)

        lay.addStretch()

        self.lbl_sb_band = QLabel(BANDS.get(self.BAND, BANDS["HF"])["label"])
        self.lbl_sb_band.setFont(small)
        lay.addWidget(self.lbl_sb_band)

        self.lbl_sb_last_frame = QLabel("")
        self.lbl_sb_last_frame.setFont(small)
        lay.addWidget(self.lbl_sb_last_frame)

        return bar

    def _update_status_bar(self, ch: int) -> None:
        partner = self.channel_bar.partner(ch)
        self.lbl_sb_channel.setText(f"Ch {ch}")
        self.lbl_sb_partner.setText(f"Partner: {partner}" if partner else "Partner: —")

    def note_last_frame(self, text: str) -> None:
        """Show the last VHF/HF mnemonic sent in the status bar (right side)."""
        self.lbl_sb_last_frame.setText(text)

    def note_capture_state(self, active: bool, path: str = "") -> None:
        self.lbl_sb_capture.setText(f"Capture: {'on — ' + path if active else 'off'}")

    # ------------------------------------------------------------------
    # Visual-only state updates (TNC commands sent by MainWindow)
    # ------------------------------------------------------------------

    def _on_view_toggled(self, checked: bool) -> None:
        """ALL/CH exclusive pair — pure UI, no TNC frame, so handled locally
        rather than round-tripping through MainWindow (P2.1 names this as a
        MainWindow wire-up target, but there is nothing for MainWindow to do
        here: set_view_all() only changes the local RX filter)."""
        self.btn_view_all.setStyleSheet(_STYLE_VIEW_ON if checked else _STYLE_VIEW_OFF)
        self.btn_view_ch.setStyleSheet(_STYLE_VIEW_OFF if checked else _STYLE_VIEW_ON)
        self.set_view_all(checked)

    def _on_options_toggled(self, checked: bool) -> None:
        self._options_container.setVisible(checked)

    def set_link_state(self, state: str) -> None:
        """Enable/disable the Connect/Disconnect buttons for an AX.25 link state.

        Called by MainWindow on link transitions so a second CONNECT cannot be
        sent while a link is up or pending (which would draw an
        ALREADY_CONNECTED error / undefined behaviour from a real TNC).

        state:
          'connected' / 'calling' — Connect disabled (no double CO), Disconnect
              enabled, Unproto disabled. CALLING keeps Connect pressed-but-
              disabled so it cannot be un-toggled into a half-aborted state; use
              Disconnect to abort.
          anything else (disconnected / idle) — Connect re-enabled and visually
              released, Disconnect disabled, Unproto re-enabled.

        T39: Connect and Unproto are mutually exclusive (like PTT modes) — a
        connected/pending AX.25 link must not also run UNPROTO UI frames, so the
        Unproto button is greyed while a link is up or calling and restored once
        the link is down.

        Does NOT touch the status pill (caller owns _set_status) and blocks
        signals while releasing Connect so it does not re-fire the toggle/CO.
        """
        if state.lower() in ("connected", "calling"):
            self.btn_connect.setEnabled(False)
            self.btn_disconnect.setEnabled(True)
            self.btn_unproto.setEnabled(False)   # T39: no UNPROTO while linked
        else:
            self.btn_connect.setEnabled(True)
            self.btn_connect.blockSignals(True)
            self.btn_connect.setChecked(False)
            self.btn_connect.blockSignals(False)
            self.btn_connect.setStyleSheet(_STYLE_CONNECT_OFF)
            self.btn_disconnect.setEnabled(False)
            self.btn_unproto.setEnabled(True)    # T39: UNPROTO available when idle

    def on_connect_toggled(self, checked: bool) -> None:
        """Visual feedback for Connect button toggle.

        Wired by MainWindow._wire_packet_buttons().
        Actual CO/DI frame is sent by MainWindow._on_packet_connect().
        """
        if checked:
            self.btn_connect.setStyleSheet(_STYLE_CONNECT_ON)
            self.btn_unproto.blockSignals(True)
            self.btn_unproto.setChecked(False)
            self.btn_unproto.blockSignals(False)
            self.btn_unproto.setStyleSheet(_STYLE_UNPROTO_OFF)
            self._set_status("CALLING")
        else:
            self.btn_connect.setStyleSheet(_STYLE_CONNECT_OFF)
            self._set_status("STBY")

    def on_unproto_toggled(self, checked: bool) -> None:
        """Visual feedback for Unproto button toggle."""
        if checked:
            self.btn_unproto.setStyleSheet(_STYLE_UNPROTO_ON)
            self.btn_connect.blockSignals(True)
            self.btn_connect.setChecked(False)
            self.btn_connect.blockSignals(False)
            self.btn_connect.setStyleSheet(_STYLE_CONNECT_OFF)
            self._set_status("UNPROTO TX")
        else:
            self.btn_unproto.setStyleSheet(_STYLE_UNPROTO_OFF)
            self._set_status("STBY")

    def on_aprs_toggled(self, checked: bool) -> None:
        """Visual feedback for APRS decode toggle.

        Only updates the button appearance — the actual re-decode
        of the RX buffer is handled by MainWindow._on_packet_aprs_toggled().
        """
        if checked:
            self.btn_aprs.setStyleSheet(_STYLE_APRS_ON)
        else:
            self.btn_aprs.setStyleSheet(_STYLE_APRS_OFF)

    # ------------------------------------------------------------------
    # Slot: Edit Macros
    # ------------------------------------------------------------------

    def _on_edit_macros(self) -> None:
        dlg = MacroEditDialog(self._macro_store, parent=self)
        dlg.exec()
        for i, btn in enumerate(self.macro_buttons):
            btn.setText(self._macro_store.names[i])


# ---------------------------------------------------------------------------
# Concrete subclasses — differ only in class attributes
# ---------------------------------------------------------------------------

class HFPacketScreen(PacketBaseScreen):
    """HF Packet — 300 Bd, VHF OFF.

    TNC init frames on activation (production — sent by HFPacketMode):
        PA     — enter Packet mode
        VH N   — VHF OFF → select 300 Bd HF FSK modem
        HB 300 — HBAUD 300
        MN Y   — Monitor ON
    """
    MODE_TITLE      = "HF Packet"
    HELP_TOPIC      = "packet"
    BAND            = "HF"
    HBAUD_VALUES    = ["300", "1200"]
    HBAUD_DEFAULT   = "300"
    MONITOR_DEFAULT = "4"
    # APRS exists on HF too (e.g. 10.151 MHz / 30 m), so the HF screen also
    # gets the APRS decode button + colour-coded data cards (same as VHF).
    APRS_CAPABLE    = True   # enables APRS decode button


class VHFPacketScreen(PacketBaseScreen):
    """VHF Packet — 1200 Bd, VHF ON.

    TNC init frames on activation (production — sent by VHFPacketMode):
        PA      — enter Packet mode
        VH Y    — VHF ON → select Bell 202 1200 Bd modem
        HB 1200 — HBAUD 1200
        MX 4    — MAXFRAME 4
        SL 10   — SLOTTIME 10 (×10ms = 100ms)
        MN Y    — Monitor ON
    """
    MODE_TITLE      = "VHF Packet"
    HELP_TOPIC      = "vhf"
    BAND            = "VHF"
    HBAUD_VALUES    = ["1200", "9600"]
    HBAUD_DEFAULT   = "1200"
    MONITOR_DEFAULT = "4"
    APRS_CAPABLE    = True   # enables APRS decode button
