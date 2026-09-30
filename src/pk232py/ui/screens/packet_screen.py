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
    │  RX window  (grows with the window,       │              │
    │   one QTextDocument per channel + ALL,    │              │
    │   P50)                                    │              │
    │ ══════════════ (drag handle, QSplitter) ══│              │
    │  TX window (~5 lines,     [Hold TX]       │              │
    │   height adjustable/saved) [Clear TX]     │              │
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

from PyQt6.QtCore import (
    Qt, QTimer, QEvent, pyqtSignal, QStringListModel,
    QVariantAnimation, QEasingCurve, QAbstractAnimation,
)
from PyQt6.QtGui import QFont, QColor, QTextDocument, QTextCursor, QTextCharFormat
from PyQt6.QtWidgets import (
    QApplication, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QLineEdit, QPushButton,
    QComboBox, QFrame, QSizePolicy,
    QScrollArea, QSplitter, QButtonGroup,
    QDialog, QFormLayout, QDialogButtonBox,
    QStackedLayout, QMenu, QCompleter,
)

from .opmode_rtty_base import (
    MacroStore, MacroEditDialog,
    make_toggle_button, make_help_button, add_hline,
    style_rx_widget, style_tx_widget,
    BTN_W, SPACING, MACRO_COUNT,
)
from .screen_focus_controller import is_keyboard_input_widget
from ...maildrop.protocol import validate_callsign


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
# P70: the monitor/unproto/system-message view is NOT a TNC channel - it has
# its own key, a str on purpose, so it can never be mistaken for (or
# indexed as) one of the TNC channels 0-9. Channel 0 is a regular channel.
MON_VIEW = "MON"

# P56.A: there is no module-level RX font constant any more (P55.C's
# _RX_FONT, removed) - the single source of truth for every RX
# QTextDocument's font is now MainWindow._apply_appearance(), the same
# place that already sets rx_display's own font from the operator's
# Appearance setting. _RX_FONT fixed the ALL-vs-CH font MISMATCH P55
# found, but introduced a second, independent font source: the ALL
# document (rx_display's own original document) kept following the
# Appearance setting (rx_display.setFont() propagates to whichever
# document is CURRENTLY attached), while every per-channel document
# was pinned to this constant forever, never updated on an Appearance
# change - reproduced 26.09.2026 (screenshot, maximized window): ALL
# view correctly showed "Cascadia Mono SemiBold 14pt", CH view did not.
# See _apply_appearance()'s own Packet-specific font push and
# PacketBaseScreen.apply_rx_font() below.

# Channel/chip states (P44 — named so both this module and its tests can
# refer to them instead of repeating the raw strings). CH_FAILED is a
# transient state only ChannelBar.set_channel_state() ever assigns itself
# (see its docstring) — nothing external sets it directly. CH_UNCONFIRMED
# (P67, Teil C.1) matches comm.link_table.STATE_UNCONFIRMED's own string
# value exactly, on purpose — MainWindow's LinkTable-subscribe callback
# passes link.state straight through to set_channel_state() with no
# translation table of its own to keep in sync.
CH_FREE        = "free"
CH_CALLING     = "calling"
CH_CONNECTED   = "connected"
CH_FAILED      = "failed"
CH_UNCONFIRMED = "unconfirmed"
# P70 (T146/T147 F6): the TNC reports CO state 4 for a moment after a DI.
# Matches comm.link_table.STATE_DISCONNECTING's string on purpose.
CH_DISCONNECTING = "disconnecting"

# Chip fill colour per state. CH_CALLING's amber is also the pulse
# animation's low value (_PULSE_LOW) — this is just what the chip shows
# for the instant between entering "calling" and the animation's first
# tick, or when the animation is disabled. CH_FAILED is red, shown only
# for _FAILED_FLASH_MS before ChannelBar reverts the chip to CH_FREE
# itself (P44 — a failed connect must be visible even on a single
# screenshot / without colour vision, not just "calling forever").
# CH_UNCONFIRMED (P67) reuses CH_CONNECTED's own green — a channel this
# table BELIEVES is connected, carried over from before a verbose<->Host
# Mode switch, not yet reconfirmed this round — distinguished from a
# plainly confirmed CH_CONNECTED chip only by its dashed border
# (_update_chip()), not a different colour language.
_CHIP_FILL = {
    CH_FREE:        "#5a5a5a",
    CH_CALLING:     "#8a6a1e",
    CH_CONNECTED:   "#3a9e3a",
    CH_FAILED:      "#b03a3a",
    CH_UNCONFIRMED: "#3a9e3a",
    CH_DISCONNECTING: "#6a4a8a",
}
_CHIP_BORDER_CURRENT = "#ffb400"   # amber, 2px — marks the current channel

# P44 — "calling" pulse animation (ONE QVariantAnimation for the whole
# ChannelBar, not one per chip, so every calling chip pulses in sync —
# see ChannelBar's own docstring for why a shared animation object).
_PULSE_LOW           = "#8a6a1e"
_PULSE_HIGH          = "#b08a2a"
_PULSE_PERIOD_MS     = 1200   # 0.83 Hz — well under the 3 Hz photosensitivity limit
_FAILED_FLASH_MS     = 1500   # how long CH_FAILED shows before reverting to CH_FREE
# The MON chip is no TNC channel and has no connection state a free/
# calling/connected fill could express - a fixed, separate colour.
_MON_CHIP_FILL = "#2a6496"

# ChannelChip editor border — amber while typing, red once an Enter with an
# invalid callsign leaves the field open for correction (P42.1).
_EDIT_STYLE_NORMAL = (
    "QLineEdit { background-color: #12303f; color: #ffffff;"
    " border: 2px solid #e8b23a; border-radius: 4px; }"
)
_EDIT_STYLE_INVALID = (
    "QLineEdit { background-color: #12303f; color: #ffffff;"
    " border: 2px solid #d05a5a; border-radius: 4px; }"
)


def _chip_style(fill: str, border: str, border_w: int, border_style: str = "solid") -> str:
    """Build a chip button's stylesheet (P44 — shared between
    ChannelBar._update_chip()'s normal render and _on_pulse_value()'s
    fast per-tick background-only update, so the two never drift apart
    on the border/text portion). *border_style* is Qt stylesheet syntax
    ('solid' or 'dashed', P67 — CH_UNCONFIRMED's own dashed border)."""
    return (
        "QPushButton {"
        f"  background-color: {fill}; color: white;"
        f"  border: {border_w}px {border_style} {border}; border-radius: 4px;"
        "}"
    )


class ChannelChip(QWidget):
    """One channel chip: a button that turns into an inline callsign
    field (P42).

    Why the chip and not a separate Connect/Dest row: the channel is the
    place a connection is made — typing the callsign directly into the
    chip you are looking at means a connect can never land on a channel
    other than the one you see, and it removes the P41 failure class
    (an input field living in its own row, one keyboard-redirect
    exception away from swallowing every keystroke) by construction —
    there is no other row left to get that exception wrong on.

    Free chip  -> a click (while already current), a double-click, or the
                  "Connect…" context-menu entry opens the inline editor;
                  typing a callsign and pressing Enter connects on THIS
                  channel. Escape or losing focus cancels.
    Busy chip  -> shows the partner callsign; no editor, "Disconnect" and
                  "Copy callsign" instead.
    Failed chip (CH_FAILED, P44) -> a failed connect attempt (retry count
                  exceeded, busy, or disconnected while still calling)
                  shows red for _FAILED_FLASH_MS before ChannelBar reverts
                  it to free on its own; counts as free for interaction
                  (editor/context menu) in the meantime — a chip that just
                  failed is exactly where a retry is most likely.
    MON chip (P70) -> no editor, no context menu entries — it is the
                  monitor/unproto view, not a TNC channel; there is
                  nothing to connect to there.

    ChannelBar owns the aggregate state (styling, "current" tracking,
    channel_map()); this class only owns its own button/editor stack and
    the interactions listed above, so ChannelBar._update_chip() reaches
    into `.button`/`.editor` directly rather than duplicating state here.
    """

    # The channel is an int 0-9, or MON_VIEW (a str) for the MON chip (P70).
    clicked               = pyqtSignal(object)      # plain click
    double_clicked        = pyqtSignal(object)      # double click
    edit_requested        = pyqtSignal(object)      # "Connect…" (context menu)
    connect_via_requested = pyqtSignal(int)         # "Connect via…" (never MON)
    disconnect_requested  = pyqtSignal(int)         # "Disconnect" (never MON)
    connect_requested     = pyqtSignal(int, str)    # Enter, valid callsign

    def __init__(self, channel: "int | str", parent=None):
        super().__init__(parent)
        self._channel = channel
        self._state = CH_FREE
        self._partner = ""

        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)

        self.button = QPushButton()
        self.button.setCheckable(True)
        # NoFocus: chips must never steal keyboard focus from tx_input
        # (CLAUDE.md §5 — applies to every QPushButton in the app).
        self.button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.button.setMinimumWidth(CHIP_MIN_W)
        self.button.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.button.setFixedHeight(34)
        lay = QVBoxLayout(self.button)
        lay.setContentsMargins(2, 1, 2, 1)
        lay.setSpacing(0)
        self._lbl_num = QLabel(str(channel))
        self._lbl_num.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self._lbl_num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_call = QLabel("")
        self._lbl_call.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._lbl_call.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._lbl_num)
        lay.addWidget(self._lbl_call)
        self.button.clicked.connect(lambda: self.clicked.emit(self._channel))
        # Double-click and right-click on a QPushButton do not reliably
        # propagate to the parent widget's own event handlers (unlike
        # unhandled key/context-menu events on some other widget types) —
        # installing directly on the button, rather than overriding
        # mouseDoubleClickEvent()/contextMenuEvent() on this wrapper,
        # avoids relying on that propagation at all.
        self.button.installEventFilter(self)

        self.editor = QLineEdit()
        self.editor.setFixedHeight(34)
        self.editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.editor.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        self.editor.setPlaceholderText("call")
        self.editor.setMaxLength(20)
        self.editor.setStyleSheet(_EDIT_STYLE_NORMAL)
        self.editor.returnPressed.connect(self._commit)
        self.editor.installEventFilter(self)   # Escape / focus-out

        self._stack.addWidget(self.button)
        self._stack.addWidget(self.editor)
        self._stack.setCurrentIndex(0)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def channel(self) -> "int | str":
        return self._channel

    def is_editing(self) -> bool:
        return self._stack.currentIndex() == 1

    def set_display(self, num_text: str, call_text: str, checked: bool,
                     style: str, tooltip: str) -> None:
        """Apply ChannelBar's per-state rendering to this chip's button.
        ChannelBar computes colours/state text (it already owns the
        theme-aware fill/border logic); this just applies it, and stores
        state/partner for this chip's OWN context-menu logic below."""
        self._lbl_num.setText(num_text)
        self._lbl_call.setText(call_text)
        self.button.blockSignals(True)
        self.button.setChecked(checked)
        self.button.blockSignals(False)
        self.button.setStyleSheet(style)
        self.button.setToolTip(tooltip)

    def set_state(self, state: str, partner: str) -> None:
        self._state = state
        self._partner = partner

    def start_edit(self, prefill: str = "") -> None:
        # CH_FAILED counts as free for interaction purposes (P44) - it is
        # a free channel that is only shown red for _FAILED_FLASH_MS for
        # visibility; blocking a retry click during that window would be
        # exactly the wrong moment to make the operator wait.
        if self._channel == MON_VIEW or self._state not in (CH_FREE, CH_FAILED):
            return
        self.editor.setStyleSheet(_EDIT_STYLE_NORMAL)
        self.editor.setToolTip("")
        self.editor.setText(prefill)
        self._stack.setCurrentIndex(1)
        self.editor.setFocus()
        self.editor.selectAll()

    def cancel_edit(self) -> None:
        self._stack.setCurrentIndex(0)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event) -> bool:
        if obj is self.button:
            if event.type() == QEvent.Type.MouseButtonDblClick:
                self.double_clicked.emit(self._channel)
                return True
            if event.type() == QEvent.Type.ContextMenu:
                self._show_menu(event.globalPos())
                return True
        elif obj is self.editor:
            if (event.type() == QEvent.Type.KeyPress
                    and event.key() == Qt.Key.Key_Escape):
                self.cancel_edit()
                return True
            if event.type() == QEvent.Type.FocusOut and self.is_editing():
                # Losing focus without pressing Enter behaves like Esc
                # (P42.1) - do not consume the event itself, Qt still
                # needs to deliver the real focus-out.
                self.cancel_edit()
        return super().eventFilter(obj, event)

    def _commit(self) -> None:
        call = self.editor.text().strip().upper()
        if not validate_callsign(call):
            self.editor.setStyleSheet(_EDIT_STYLE_INVALID)
            self.editor.setToolTip(
                "Enter a valid callsign: letters and digits, optional "
                "'-SSID' (e.g. OE3XYZ-9)."
            )
            return
        self._stack.setCurrentIndex(0)
        self.connect_requested.emit(self._channel, call)

    def _show_menu(self, global_pos) -> None:
        if self._channel == MON_VIEW:
            return   # P70: no context menu on the MON chip
        menu = QMenu(self)
        if self._state in (CH_FREE, CH_FAILED):
            act = menu.addAction("Connect…")
            act.triggered.connect(lambda: self.edit_requested.emit(self._channel))
            act = menu.addAction("Connect via…")
            act.triggered.connect(
                lambda: self.connect_via_requested.emit(self._channel)
            )
        else:
            if self._state != CH_DISCONNECTING:   # already on its way down
                act = menu.addAction("Disconnect")
                act.triggered.connect(
                    lambda: self.disconnect_requested.emit(self._channel)
                )
            act = menu.addAction("Copy callsign")
            act.triggered.connect(self._copy_callsign)
        menu.exec(global_pos)

    def _copy_callsign(self) -> None:
        if self._partner:
            QApplication.clipboard().setText(self._partner)


class ChannelBar(QWidget):
    """Row of chips - MON, then channels 0-9 one to one as in the PK-232 (P70).

    MON is no TNC channel: it is the monitor/unproto/system-message view
    (key MON_VIEW). Channels 0-9 are all treated alike.

    A chip shows the channel number while free, and the partner callsign once
    a connect attempt is under way or a link is up. Chip fill colour encodes
    state — grey (CH_FREE), pulsing amber (CH_CALLING), green (CH_CONNECTED),
    red for _FAILED_FLASH_MS then back to grey (CH_FAILED, P44) — the same
    semantics as MHEARD's own connected-station colour (P44.A3: one colour
    logic for the whole window, not amber in one place and green in another.
    A 2px amber border marks the *current* channel, independent of fill.
    Since P42, the chip is also where a connect happens — see ChannelChip.

    Lernmodus — why a local model and not a TNC query: the PK-232 Host Mode
    has no CSTATUS command; the channel is only ever known from the CTL
    nibble of frames that already went by (CONNECT/DISCONNECT/data/link-msg).
    So ChannelBar simply remembers what HFPacketMode.on_channel_state told it.
    """

    # int 0-9, or MON_VIEW (a str) for the MON chip (P70)
    channel_changed  = pyqtSignal(object)
    connect_requested    = pyqtSignal(int, str)   # channel, callsign (P42)
    connect_via_requested = pyqtSignal(int)       # "Connect via…" (P42)
    disconnect_requested = pyqtSignal(int)        # context menu / Ctrl+K (P42, P46.C.2)

    # Recently used callsigns, shared by every chip's inline editor via one
    # QCompleter (P42 — replaces the old cb_dest QComboBox history).
    _HISTORY_MAX = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current: "int | str" = 1
        self._state: dict[int, str] = {ch: CH_FREE for ch in range(CHANNEL_COUNT)}
        self._partner: dict[int, str] = {ch: "" for ch in range(CHANNEL_COUNT)}
        self._chips: "dict[int | str, ChannelChip]" = {}
        # USERS (P11.5) — advisory only, see set_user_limit().
        self._user_limit: int = CHANNEL_COUNT

        # P44 — one shared pulse animation for every CH_CALLING chip (not
        # one per chip: a single animation object keeps every calling
        # chip pulsing in perfect sync, which reads as intentional rather
        # than several independent, visibly-drifting timers). Low->high
        # via a mid-cycle keyframe, not start/end alone, so the loop is a
        # smooth oscillation rather than a sawtooth snap-back to the low
        # value at the end of every 1.2s cycle.
        self._pulse = QVariantAnimation(self)
        self._pulse.setStartValue(QColor(_PULSE_LOW))
        self._pulse.setKeyValueAt(0.5, QColor(_PULSE_HIGH))
        self._pulse.setEndValue(QColor(_PULSE_LOW))
        self._pulse.setDuration(_PULSE_PERIOD_MS)
        self._pulse.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._pulse.setLoopCount(-1)
        self._pulse.valueChanged.connect(self._on_pulse_value)

        # P44 — one QTimer(self) per channel that is currently showing
        # CH_FAILED, created on demand and reused; see
        # _schedule_failed_clear() for why these must be parented to
        # self rather than free-floating QTimer.singleShot() calls.
        self._failed_timers: dict[int, "QTimer"] = {}

        self._history: list[str] = []
        self._history_model = QStringListModel([])
        self._completer = QCompleter(self._history_model, self)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)

        # MON first, visually set off from the ten TNC channels (P70 C).
        for ch in (MON_VIEW, *range(CHANNEL_COUNT)):
            chip = ChannelChip(ch)
            chip.editor.setCompleter(self._completer)
            chip.clicked.connect(self._on_chip_clicked)
            chip.double_clicked.connect(self._on_chip_double_clicked)
            chip.edit_requested.connect(self._on_chip_edit_requested)
            chip.connect_requested.connect(self._on_chip_connect_requested)
            chip.connect_via_requested.connect(self.connect_via_requested)
            chip.disconnect_requested.connect(self.disconnect_requested)

            # QButtonGroup ids are ints: MON gets -2 (-1 means "auto").
            self._group.addButton(chip.button, -2 if ch == MON_VIEW else ch)
            self._chips[ch] = chip
            row.addWidget(chip, 1)
            if ch == MON_VIEW:
                row.addSpacing(10)

        self._select(self._current, emit=False)

    # -- history (P42, replaces the old cb_dest combo history) ----------

    def add_history(self, callsign: str) -> None:
        callsign = callsign.strip().upper()
        if not callsign:
            return
        if callsign in self._history:
            self._history.remove(callsign)
        self._history.insert(0, callsign)
        del self._history[self._HISTORY_MAX:]
        self._history_model.setStringList(self._history)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_channel_state(self, ch: int, state: str, partner: str = "") -> None:
        """Update chip *ch* to *state* (CH_FREE/CH_CALLING/CH_CONNECTED).

        Channel 0 is a regular channel (P70). MON_VIEW (or any other key
        that is not a TNC channel) is ignored: the MON chip has no state.

        P44 — a CALLING channel that is told to become FREE has, by
        definition, failed to connect (retry count exceeded, busy, or a
        DISCONNECTED that arrived before ever reaching CONNECTED — see
        HFPacketMode._handle_link_msg()). Rather than snap straight back
        to a plain free chip, this shows CH_FAILED (red) for
        _FAILED_FLASH_MS first — a screenshot or a colour-blind operator
        must be able to tell "that attempt just failed" apart from
        "nothing has ever been tried here", which a chip that goes
        straight from amber to grey cannot. A channel that was already
        CONNECTED (a normal, successful hangup) skips this entirely and
        goes straight to free, same as before — there is nothing that
        failed there. This is still entirely driven through
        set_channel_state() (P18/P16's existing channel-state path) - no
        new callback route.
        """
        if ch not in self._state:
            return
        prior = self._state[ch]
        if state == CH_FREE and prior == CH_CALLING:
            self._state[ch] = CH_FAILED
            self._partner[ch] = ""
            self._update_chip(ch)
            self._sync_pulse_animation()
            self._schedule_failed_clear(ch)
            return
        self._state[ch] = state if state in _CHIP_FILL else CH_FREE
        self._partner[ch] = partner if state != CH_FREE else ""
        self._update_chip(ch)
        self._sync_pulse_animation()

    def _schedule_failed_clear(self, ch: int) -> None:
        """Start (or restart) the QTimer that reverts chip *ch* from
        CH_FAILED back to CH_FREE after _FAILED_FLASH_MS.

        Deliberately a QTimer(self) PARENTED to this ChannelBar and kept
        in self._failed_timers, never the free-floating
        QTimer.singleShot(ms, callback) classmethod: that timer is owned
        by the global Qt event loop, not by any widget, so it still fires
        (and still calls into self._clear_failed(), touching widgets
        that may already be gone) even after this ChannelBar's C++
        object has been destroyed - found via a real crash (RuntimeError:
        wrapped C/C++ object of type QLabel has been deleted) that only
        showed up running the FULL test suite, never a single test file
        in isolation: a test's ChannelBar went out of scope and was
        garbage-collected long before its pending 1.5s singleShot fired,
        and when it did, it corrupted an unrelated LATER test's own
        pytest-qt exception capture - the exact same class of collateral
        damage the P41 stale-event-filter finding hit (see CLAUDE.md). A
        timer parented to self is destroyed by Qt along with it, so a
        dead ChannelBar simply never fires this callback at all instead
        of firing it against freed memory.
        """
        timer = self._failed_timers.get(ch)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda: self._clear_failed(ch))
            self._failed_timers[ch] = timer
        timer.start(_FAILED_FLASH_MS)

    def _clear_failed(self, ch: int) -> None:
        """Revert chip *ch* from CH_FAILED back to CH_FREE after
        _FAILED_FLASH_MS (P44). Only acts if the chip is STILL showing
        CH_FAILED - a fresh connect attempt (or any other state change)
        in the meantime already moved it on, and must not be undone by
        this stale timer firing late."""
        if self._state.get(ch) == CH_FAILED:
            self._state[ch] = CH_FREE
            self._partner[ch] = ""
            self._update_chip(ch)

    def set_current(self, ch: "int | str") -> None:
        """Select *ch* (0-9 or MON_VIEW) as the current channel (used by
        Connect/TX)."""
        if ch not in self._chips:
            return
        self._select(ch, emit=True)

    def current(self) -> "int | str":
        """The selected chip: a TNC channel 0-9, or MON_VIEW."""
        return self._current

    def partner(self, ch: "int | str | None" = None) -> str:
        return self._partner.get(self._current if ch is None else ch, "")

    def state(self, ch: "int | str | None" = None) -> str:
        return self._state.get(self._current if ch is None else ch, CH_FREE)

    def channel_map(self) -> dict[str, int]:
        """Return {callsign: channel} for every channel that is currently
        connected or calling. Feeds MheardPanel.set_channel_map().

        Channel 0 is included like any other (P70); the MON chip has no
        partner and never appears.
        """
        return {
            call: ch
            for ch, call in self._partner.items()
            if call and self._state.get(ch) in (CH_CONNECTED, CH_CALLING)
        }

    # -- pulse animation (P44) ------------------------------------------

    def _sync_pulse_animation(self) -> None:
        """Start the shared pulse animation the instant any chip becomes
        CH_CALLING, stop it the instant none are - never a permanent
        timer running on the notebook while the screen is just sitting
        idle."""
        calling = any(s == CH_CALLING for s in self._state.values())
        running = self._pulse.state() == QAbstractAnimation.State.Running
        if calling and not running:
            self._pulse.start()
        elif not calling and running:
            self._pulse.stop()

    def _on_pulse_value(self, value: QColor) -> None:
        """Apply the animation's current interpolated colour to every
        CALLING chip's background only - text colour and border stay
        fixed, so the label reads steadily while the fill breathes."""
        fill = value.name()
        for ch, chip in self._chips.items():
            if self._state.get(ch) != CH_CALLING:
                continue
            is_current = ch == self._current
            border   = _CHIP_BORDER_CURRENT if is_current else "#333333"
            border_w = 2 if is_current else 1
            chip.button.setStyleSheet(_chip_style(fill, border, border_w))

    def step(self, delta: int) -> None:
        """Move the selection by *delta* through MON, 0, 1 ... 9, wrapping
        (P70: MON is the first of eleven positions)."""
        positions = [MON_VIEW, *range(CHANNEL_COUNT)]
        idx = positions.index(self._current)
        self._select(positions[(idx + delta) % len(positions)], emit=True)

    def reset(self) -> None:
        """Set every chip back to 'free' with no partner.

        Called on mode activation and on leaving Host Mode — otherwise a
        stale CONNECTED/CALLING chip from an earlier session (or from a
        connection that was never explicitly torn down before the TNC
        dropped out of Host Mode) would sit there with no frame left to
        clear it. Does NOT change which channel is current.

        P57.1: also closes any open chip editor first - a mode switch
        or leaving Host Mode makes any in-progress connect attempt
        meaningless (PacketBaseScreen.reset_channels() is what actually
        calls this, on both triggers).
        """
        self.close_open_editor()
        for ch in range(CHANNEL_COUNT):
            self._state[ch] = CH_FREE
            self._partner[ch] = ""
            self._update_chip(ch)
        self._sync_pulse_animation()

    def set_user_limit(self, limit: int) -> None:
        """Number of simultaneous connections the TNC accepts (USERS, P11.5).

        Advisory only — adds a tooltip line to chips above the limit, never
        a lock, greying-out or colour change. USERS is documented as
        limiting *accepted* (incoming) connections; whether it also blocks
        *outgoing* connects on higher channels is not confirmed, so a hard
        lock could prevent operation that would actually have worked. An
        incorrect tooltip costs nothing; a locked chip that would have
        worked costs the operator a QSO.
        """
        self._user_limit = limit
        for ch in range(CHANNEL_COUNT):
            self._update_chip(ch)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_chip_clicked(self, ch: "int | str") -> None:
        """A click selects — UNLESS the clicked chip is already the
        current, free channel, in which case it opens that chip's
        inline editor instead (P42.1's table: 'Klick auf den bereits
        gewählten freien Chip öffnet die Eingabe')."""
        if (ch == self._current and ch != MON_VIEW
                and self._state[ch] in (CH_FREE, CH_FAILED)):
            self._chips[ch].start_edit()
            return
        self._select(ch, emit=True)

    def _on_chip_double_clicked(self, ch: "int | str") -> None:
        """Double-click always opens the editor on a free chip,
        regardless of which channel was current before (P42.1)."""
        self._select(ch, emit=True)
        self._chips[ch].start_edit()

    def _on_chip_edit_requested(self, ch: int) -> None:
        """'Connect…' context-menu entry — same as a double-click."""
        self._on_chip_double_clicked(ch)

    def _on_chip_connect_requested(self, ch: int, callsign: str) -> None:
        self.request_connect(ch, callsign)

    def request_connect(self, ch: int, callsign: str) -> None:
        """Record *callsign* in history and emit connect_requested(ch, callsign).

        Public (not just the chip's own Enter-to-connect callback) because
        the "Connect via…" dialog also reaches this same path — it bypasses
        the chip's inline editor entirely (it can add a digipeater path),
        but still needs the same history bookkeeping (P42.2).
        """
        self.add_history(callsign)
        self.connect_requested.emit(ch, callsign)

    def start_edit_first_free(self, prefill: str = "") -> None:
        """Open the editor on the first free channel, prefilled (P42 —
        MHEARD double-click on an unconnected station: 'the first free
        chip', not necessarily the one currently selected). Channel 0
        counts like any other since P70."""
        for ch in range(CHANNEL_COUNT):
            if self._state[ch] in (CH_FREE, CH_FAILED):
                self.start_edit(ch, prefill)
                return

    def start_edit(self, ch: "int | str", prefill: str = "") -> None:
        """Select *ch* and open its editor, prefilled (P42 — used by the
        MHEARD double-click handler in PacketBaseScreen). No-op for a
        busy chip or the MON chip; ChannelChip.start_edit() enforces
        that itself, this just also makes sure *ch* becomes current."""
        if ch == MON_VIEW or self._state.get(ch) not in (CH_FREE, CH_FAILED):
            return
        self._select(ch, emit=True)
        self._chips[ch].start_edit(prefill)

    def start_edit_current(self) -> None:
        """Open the editor on whichever channel is current, if it is
        free (P42.1 — Enter pressed while focus is outside the TX
        window, e.g. in the via/Monitor/HBAUD fields)."""
        self._chips[self._current].start_edit()

    def is_editing(self) -> bool:
        """True while any chip's inline editor is open (P42.3 — used to
        suppress Ctrl+Up/Ctrl+Down channel stepping while typing)."""
        return any(chip.is_editing() for chip in self._chips.values())

    def close_open_editor(self) -> None:
        """Cancel whichever chip's inline editor is currently open, if
        any (P57.1) — discarding, exactly like Esc; nothing is sent.

        Chips are NoFocus (so the keyboard stays in tx_input, P41) —
        clicking a DIFFERENT chip therefore never fires the editing
        chip's own focusOutEvent at all, so the P42.1 "losing focus
        cancels like Esc" rule (ChannelChip.eventFilter()'s own
        FocusOut branch) never triggers for this case. Reproduced
        26.09.2026 (screenshot): the cursor stayed in channel 3's
        editor while channel 4 carried the active frame, and keystrokes
        kept landing in channel 3's field. ChannelBar is the one place
        that knows which of its ten chips is editing — the rule
        belongs here, called from every place a channel can change or
        the whole bar can reset (_select(), reset()), not duplicated in
        each chip or each caller.
        """
        for chip in self._chips.values():
            if chip.is_editing():
                chip.cancel_edit()
                return

    def _select(self, ch: "int | str", emit: bool) -> None:
        # P57.1: close any OTHER chip's open editor before switching -
        # the click/call that changes the channel keeps its normal
        # effect (it still switches), it just also closes whatever was
        # left open elsewhere. Never the chip about to become current
        # itself: _select(ch) is only ever called for a chip whose
        # BUTTON is visible (double-click, a plain click, set_current(),
        # step()) - a chip currently editing shows its editor instead,
        # so it can never be the *ch* this method was called with.
        self.close_open_editor()
        changed = ch != self._current
        self._current = ch
        self._group.blockSignals(True)
        self._chips[ch].button.setChecked(True)
        self._group.blockSignals(False)
        for c in self._chips:
            self._update_chip(c)
        if emit and changed:
            self.channel_changed.emit(ch)

    def _update_chip(self, ch: "int | str") -> None:
        """Render chip *ch*. The MON chip (P70) branches off here and
        nowhere else in this class: a fixed colour, no state, no partner."""
        chip = self._chips[ch]
        is_current = ch == self._current
        border = _CHIP_BORDER_CURRENT if is_current else "#333333"
        border_w = 2 if is_current else 1
        if ch == MON_VIEW:
            chip.set_state(CH_FREE, "")
            chip.set_display(
                "MON", "", is_current,
                _chip_style(_MON_CHIP_FILL, border, border_w),
                "MON - monitor, unproto and system messages.\n"
                "Not a TNC channel: nothing can be connected here. Text "
                "typed here is sent as a UI frame along the UNPROTO path, "
                "via the lowest free channel.\n"
                "Click to select, or Ctrl+Up / Ctrl+Down steps through it too."
            )
            return

        state = self._state[ch]
        partner = self._partner[ch]
        chip.set_state(state, partner)

        fill = _CHIP_FILL.get(state, _CHIP_FILL[CH_FREE])
        # P67: CH_UNCONFIRMED's own dashed border — a channel carried
        # over from before a verbose<->Host Mode switch, not yet
        # reconfirmed this round, must not look identical to a plainly
        # confirmed CH_CONNECTED chip (same green fill otherwise).
        border_style = "dashed" if state == CH_UNCONFIRMED else "solid"
        style = _chip_style(fill, border, border_w, border_style)
        tip = (
            f"Channel {ch}\n"
            f"State: {state}\n"
            f"Partner: {partner or '—'}\n"
            "Click to select; click again (or double-click, or "
            "right-click → Connect…) to type a callsign.\n"
            "Ctrl+Up / Ctrl+Down steps through channels."
        )
        if state == CH_UNCONFIRMED:
            tip += "\ncarried over from verbose - waiting for confirmation"
        if ch >= self._user_limit:
            tip += (
                f"\nUSERS is set to {self._user_limit} — incoming "
                "connects on this channel will not be accepted."
            )
        # CH_CALLING gets a trailing ellipsis (P44) - the state must be
        # readable even without colour (a screenshot, colour-blindness),
        # and "OE3TEC" alone looks identical whether calling or connected.
        call_text = partner if partner else ""
        if state == CH_CALLING and call_text:
            call_text += " …"
        chip.set_display(str(ch), call_text, is_current, style, tip)


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
            # P44 — one colour semantics for the whole window: connected
            # means CH_CONNECTED's green everywhere, not amber here and
            # green on the chip (the chip already uses amber for CALLING,
            # so amber here used to contradict it).
            lbl_c.setStyleSheet(f"color: {_CHIP_FILL[CH_CONNECTED]};")
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
               f"Double-click to open a connect field prefilled with "
               f"“{callsign}” on the first free channel.")
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
        connect_requested(str)     — double-click on an unconnected station;
                                     PacketBaseScreen wires this straight to
                                     ChannelBar.start_edit_first_free() (P42)
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

        lbl_legend = QLabel("* = direct (no digi)  |  green = connected")
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

    def add_entry_if_new(self, callsign: str, time_str: str, direct: bool = False) -> None:
        """Add *callsign* only if it is not already in the list (P50
        Teil E) - called from a live link message (CONNECTED/
        DISCONNECTED/busy/Connect request) so a connection partner
        appears in MHEARD immediately, without waiting for a manual
        Refresh. Unlike add_entry(), never duplicates or updates an
        existing row - a station repeatedly mentioned in link messages
        (e.g. several DATA exchanges on one QSO) must not accumulate
        the same callsign over and over."""
        if any(c == callsign for c, _t, _d in self._entries):
            return
        self.add_entry(callsign, time_str, direct)

    def set_channel_map(self, mapping: dict[str, int]) -> None:
        """Update which callsigns are currently connected on which channel.

        Called whenever ChannelBar state changes so MHEARD rows for those
        callsigns show the channel column and render green (T87; amber
        until P44, when the chip/MHEARD colour semantics were unified).
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
# PacketConnectDialog — "Connect via…" chip context-menu entry
# ---------------------------------------------------------------------------

class PacketConnectDialog(QDialog):
    """Advanced connect dialog: callsign + digipeater path, fixed channel.

    P42: the channel is no longer an editable field here — it comes from
    whichever chip's "Connect via…" context-menu entry opened the dialog,
    so a mismatch between the dialog and the chip that launched it can no
    longer happen (there is no field left to disagree with the chip on).

    v0.1: no persistence across sessions (Backlog Priority 2 item
    "Connect-Dialog-Persistenz"). Returns (callsign, path) via
    exec()/callsign()/path(); channel() echoes back the fixed channel.
    """

    def __init__(self, channel: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Packet Connect — advanced (channel {channel})")
        self._channel = channel
        form = QFormLayout(self)

        form.addRow("Channel:", QLabel(str(channel)))

        self.le_call = QLineEdit()
        self.le_call.setPlaceholderText("e.g. OE3XYZ-9")
        self.le_call.setMaxLength(20)
        form.addRow("Callsign:", self.le_call)

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
        return self._channel

    def callsign(self) -> str:
        return self.le_call.text().strip().upper()

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
        btn_unproto, btn_maildrop, btn_aprs
        btn_eas, btn_passall, btn_mrpt, btn_mid, btn_squelch
        combo_hbaud, combo_monitor, rx_display, tx_input, macro_buttons
        set_mycall(), set_link_state(), on_unproto_toggled(), _set_status()

    Channel model (P10 sprint), connect-in-chip (P42 — Connect/Dest/…/
    Disconnect row removed; a callsign is typed directly into the free
    channel chip you want to connect on):
        channel_bar          ChannelBar — channel_bar.connect_requested(ch,
                              callsign), .connect_via_requested(ch),
                              .disconnect_requested(ch) are what MainWindow
                              wires instead of button clicks
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

    # P50 Teil B: sentinel key for the merged ALL RX document in
    # _rx_scroll/_rx_current_key - distinct from any real channel number
    # (0-9) so the two can share one dict without collision.
    _ALL_DOC_KEY = "ALL"

    # Signals connected automatically by MainWindow._wire_mode_callbacks().
    # Declared on the base class → HF and VHF Packet inherit them.
    clear_tx_req = pyqtSignal()
    clear_rx_req = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._view_all = True   # ALL vs CH RX filter (P1.4; P50: now a
                                 # DOCUMENT switch, not an append-time
                                 # filter - see _sync_rx_document())

        # Per-channel RX document buffer (P50 Teil B) - one QTextDocument
        # per channel (0-9) plus a merged ALL document that receives
        # every line too, in arrival order. Switching the visible channel
        # or the ALL/CH view just re-attaches rx_display to the right
        # document (_sync_rx_document()) - no more append-time filtering,
        # so a channel's FULL history is there the moment you switch to
        # it, not just what arrives from then on. _rx_scroll remembers
        # each document's own scroll position across switches.
        self._rx_docs: "dict[int | str, QTextDocument]" = {
            ch: QTextDocument(self) for ch in (MON_VIEW, *range(CHANNEL_COUNT))
        }
        self._rx_doc_all = QTextDocument(self)
        for _doc in list(self._rx_docs.values()) + [self._rx_doc_all]:
            _doc.setMaximumBlockCount(5000)   # overwritten by
                                               # apply_display_settings()
        # P56.A: no font is set here - Qt's own generic default holds
        # only until MainWindow._apply_appearance() runs (always, right
        # after _build_central() completes, both at startup and on
        # every later Appearance change) and calls apply_rx_font() below
        # with the operator's actual font. A screen built standalone
        # (e.g. in a test, with no MainWindow) simply keeps Qt's default
        # on every document AND on rx_display itself, consistently -
        # never a mismatch between the two, which is the one property
        # that actually matters here.
        self._rx_scroll: dict[object, int] = {}
        self._rx_current_key: object = self._ALL_DOC_KEY
        self._show_timestamps = False   # P50 Teil C - set via
                                         # apply_display_settings()

        # Per-channel TX draft buffer (P9). ch -> (text, cursor_pos).
        # _tx_channel is populated once self.channel_bar exists (see
        # _build_ui() below, right after the ChannelBar is constructed).
        self._tx_buffers: dict[int, tuple[str, int]] = {}
        self._tx_channel: int = 0

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
        # A chip's own inline callsign editor needs NO registration here —
        # is_keyboard_input_widget() (P41) recognises any QLineEdit/QComboBox/
        # etc. by type as it walks the parent chain, so it is exempted from
        # the TX-window redirect regardless of registration. le_unproto is
        # still registered because ScreenFocusController is also how
        # MainWindow's Level-1 filter decides is_active() (see eventFilter()
        # docstring there); lbl_mycall is a QLabel — no focus tracking needed.
        from .screen_focus_controller import ScreenFocusController
        self.focus_ctrl = ScreenFocusController(
            fields=[self.le_unproto],
            parent=self,
        )

        # Pure UI wiring (no TNC frame, so no MainWindow round-trip needed):
        # double-clicking an MHEARD row on an unconnected station opens the
        # first free chip's inline editor, prefilled (P42); on a connected
        # one it just switches to that channel.
        self.mheard_panel.connect_requested.connect(
            self.channel_bar.start_edit_first_free
        )
        self.mheard_panel.channel_requested.connect(self.channel_bar.set_current)

        # "Connect via…" chip context-menu entry — advanced dialog with a
        # digipeater path field (P42.2). Pure UI (no TNC frame) until the
        # dialog is accepted, at which point it re-enters the same
        # ChannelBar.request_connect() path a plain chip Enter would use.
        self.channel_bar.connect_via_requested.connect(self._on_connect_via_requested)

        # Enter in one of these fields, while no chip editor is already
        # open, opens the current chip's editor instead of doing nothing
        # (P42.1's "Enter bei gewähltem freien Chip, Fokus nicht im
        # TX-Fenster" row) — none of them has a returnPressed handler of
        # its own, so this cannot shadow any existing behaviour.
        for _fld in (self.le_unproto, self.combo_monitor, self.combo_hbaud):
            _fld.installEventFilter(self)

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
        # P57.1: a click into any of the fields this filter already
        # watches (tx_input, le_unproto, combo_monitor, combo_hbaud)
        # closes an open chip editor first - the "click elsewhere in
        # the mask" row of P57's own table. No new filter/installEvent
        # Filter() call needed: this method is already installed on
        # every one of those widgets (below), so extending it here is
        # the one place this rule needs to live, exactly as the spec
        # asks. Never consumed - the click must still reach its real
        # target (e.g. actually focus tx_input) after closing the editor.
        if (event.type() == QEvent.Type.MouseButtonPress
                and self.channel_bar.is_editing()):
            self.channel_bar.close_open_editor()
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
            # Ctrl+K disconnects the CURRENT channel (P42.2; moved from
            # Ctrl+D to Ctrl+K in P46.C.2) — Packet has no TxController/
            # [^D] EOT concept (see the Hold-TX comment above), so this key
            # was free to mean "disconnect" here, unlike on the
            # character-ACK modes. Moved off Ctrl+D because that shortcut
            # now unambiguously means the TNC menu's "Disconnect + Close
            # Serial Port" (Ctrl+D) - two different "disconnect" actions
            # (station link vs. serial port) sharing one key was exactly
            # the "Connect"/"Disconnect" ambiguity P46 set out to remove.
            # Also available from the chip's own context menu regardless.
            if (event.key() == _Qt.Key.Key_K and
                    event.modifiers() & _Qt.KeyboardModifier.ControlModifier):
                ch = self.channel_bar.current()
                if (ch != MON_VIEW
                        and self.channel_bar.state(ch) not in (CH_FREE, CH_FAILED)
                        and self.channel_bar.state(ch) != CH_DISCONNECTING):
                    self.channel_bar.disconnect_requested.emit(ch)
                return True
        # Enter in one of the non-TX fields registered in __init__, while no
        # chip editor is already open, opens the CURRENT chip's editor
        # (P42.1 — "Enter bei gewähltem freien Chip, Fokus nicht im
        # TX-Fenster"). ChannelBar.start_edit_current() is itself a no-op
        # on a busy chip or channel 0, so this is safe to call unconditionally.
        if (event.type() == QEvent.Type.KeyPress
                and obj in (getattr(self, 'le_unproto', None),
                            getattr(self, 'combo_monitor', None),
                            getattr(self, 'combo_hbaud', None))
                and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and not self.channel_bar.is_editing()):
            self.channel_bar.start_edit_current()
            return True
        if event.type() == QEvent.Type.KeyPress:
            # is_keyboard_input_widget() walks the parent chain and
            # covers every keyboard-input widget type, including
            # QComboBox (Dest, Monitor, HBAUD) and QAbstractSpinBox —
            # not just QLineEdit/QTextEdit (P41: an editable QComboBox's
            # own widget, not its inner lineEdit(), is what actually
            # receives focus/events, so the old QLineEdit-only check
            # never matched it).
            if (is_keyboard_input_widget(self.focusWidget())
                    or is_keyboard_input_widget(obj)):
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
    # Connect via… (P42.2) — the chip's context-menu entry for the advanced
    # dialog (callsign + optional digipeater path). A plain connect never
    # goes through here at all: it comes straight from ChannelChip's own
    # inline editor via ChannelBar.request_connect().
    # ------------------------------------------------------------------

    def _on_connect_via_requested(self, channel: int) -> None:
        """'Connect via…' chip context-menu entry.

        Right-click works on any free chip regardless of which channel is
        currently selected, so this also switches the ChannelBar to
        *channel* before requesting the connect — the same "become current"
        step a plain chip Enter-to-connect already gets for free (its
        editor cannot even open without the chip becoming current first).
        """
        dlg = PacketConnectDialog(channel, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            call = dlg.callsign()
            if not call:
                return
            path = dlg.path()
            full = f"{call} VIA {path}" if path else call
            self.channel_bar.set_current(channel)
            self.channel_bar.request_connect(channel, full)

    # ------------------------------------------------------------------
    # Channel-bound RX (P1.4) — filtering happens at append time, not by
    # rebuilding the buffer: switching channel or ALL/CH does NOT redraw
    # history (deliberate v0.1 simplification, see module docstring / P1.4).
    # ------------------------------------------------------------------

    def current_channel(self) -> "int | str":
        """The selected chip: a TNC channel 0-9, or MON_VIEW (P70)."""
        return self.channel_bar.current()

    def reset_channels(self) -> None:
        """Clear every per-channel TX draft (P9.3) and RX document (P50
        Teil B). Called by MainWindow when the mode is (re)activated
        (see _switch_opmode() in main_window.py) — without this, a
        stale TX draft or a previous session's RX history would linger
        with no frame ever left to clear it.

        Deliberately does NOT touch channel_bar's chip state or
        mheard_panel's channel map any more (P67, Teil C - correcting a
        regression the CO-reconciliation race exposed): LinkTable is
        now the one source of truth for connection state, reconciled
        independently on every fresh Host Mode entry (mark_unconfirmed()
        + a CO probe of every channel, MainWindow.
        _update_host_mode_ui(True)) - a blanket channel_bar.reset()
        here could run AFTER a CO answer had already confirmed a
        carried-over channel (the mode-activation timer and the TNC's
        own CO response race each other), silently wiping a connection
        the LinkTable still correctly remembers as connected. Confirmed
        via a real repro: without this fix, a CO answer confirming ch1
        arrives, the chip shows connected, then reset_channels() (fired
        300ms later by the SAME Host Mode entry's own mode-activation
        timer) wipes it back to free while LinkTable.channels[1] still
        says connected.
        """
        # P57.1: still closes any open chip editor - an in-progress
        # connect attempt is meaningless after a reactivation
        # regardless of what LinkTable does or does not remember.
        self.channel_bar.close_open_editor()
        self._tx_buffers.clear()
        self.tx_input.blockSignals(True)
        self.tx_input.clear()
        self.tx_input.blockSignals(False)
        for doc in self._rx_docs.values():
            doc.clear()
        self._rx_doc_all.clear()
        self._rx_scroll.clear()
        self._sync_rx_document()

    # ------------------------------------------------------------------
    # Per-channel TX draft buffer (P9) — text typed on one channel must
    # survive any number of channel switches, whichever way the channel
    # changed (chip click, Ctrl+Up/Down, MHEARD double-click, the Connect
    # dialog's channel picker, or a programmatic channel_bar.set_current()).
    # All of those funnel through ChannelBar.channel_changed, which this
    # class connects to _on_tx_channel_switch in _build_ui() — see the
    # comment there for why that connection must be made in the screen's
    # own constructor rather than by MainWindow.
    # ------------------------------------------------------------------

    def tx_text(self) -> str:
        """Currently visible TX text (for the channel in `_tx_channel`)."""
        return self.tx_input.toPlainText()

    def clear_tx(self, channel: int | None = None) -> None:
        """Clear the TX widget AND discard the buffered draft for *channel*
        (the currently visible channel if None). Only that one channel is
        affected — never all of them. If *channel* is not the channel
        currently shown in the widget, only its buffer entry is dropped;
        the visible text (belonging to a different channel) is untouched.
        """
        ch = self.current_channel() if channel is None else channel
        self._tx_buffers.pop(ch, None)
        if ch == self._tx_channel:
            self.tx_input.clear()

    def _on_tx_channel_switch(self, new_ch: int) -> None:
        """Save the outgoing channel's TX draft (text + cursor position)
        under `_tx_channel` — the channel the visible text still belongs to,
        NOT `new_ch` (channel_changed only carries the channel being
        switched TO) — then load `new_ch`'s draft, or a blank buffer if it
        has none yet. blockSignals prevents setPlainText()/setTextCursor()
        from firing textChanged and triggering any send logic.
        """
        cursor = self.tx_input.textCursor()
        self._tx_buffers[self._tx_channel] = (
            self.tx_input.toPlainText(), cursor.position()
        )
        self._tx_channel = new_ch
        text, pos = self._tx_buffers.get(new_ch, ("", 0))
        self.tx_input.blockSignals(True)
        self.tx_input.setPlainText(text)
        new_cursor = self.tx_input.textCursor()
        new_cursor.setPosition(min(max(pos, 0), len(text)))
        self.tx_input.setTextCursor(new_cursor)
        self.tx_input.blockSignals(False)

    # Muted colour for the optional timestamp and the ALL-view "n|" tag
    # (P50 Teil C) - never the line's own content colour, so a system
    # message's eye-catching colour (link messages, etc.) still stands
    # out against it.
    _MUTED_RX_COLOR = "#6a6a6a"

    def apply_display_settings(self, show_timestamps: bool, rx_max_lines: int) -> None:
        """Apply PC-side RX display settings (P50 Teil C) - called once on
        mode activation and again immediately whenever the HF Packet
        Parameters dialog is accepted (HF and VHF Packet share
        HFPacketConfig, so MainWindow calls this on both screens)."""
        self._show_timestamps = show_timestamps
        for doc in list(self._rx_docs.values()) + [self._rx_doc_all]:
            doc.setMaximumBlockCount(rx_max_lines)

    def _all_view_tag(self, channel: "int | str") -> str:
        """Compact ALL-view channel tag (P50 Teil C): "MON" for the
        monitor view (matching the chip's own label, P70), the plain
        digit for a TNC channel."""
        return "MON" if channel == MON_VIEW else str(channel)

    def apply_rx_font(self, font: QFont) -> None:
        """Push *font* onto every RX document - each channel's own AND
        the merged ALL document (P56.A) - called by MainWindow.
        _apply_appearance() with the operator's Appearance font,
        alongside the existing generic rx_display.setFont(font) every
        screen already gets.

        rx_display.setFont() alone only ever touches whichever ONE
        document happens to be attached at that moment - never the
        other nine documents this screen also owns. Without this, only
        the document visible when Appearance was last applied (usually
        ALL, since it is the default view) ever gets the operator's own
        font; every per-channel document keeps whatever font it was
        left at, INCLUDING one not currently visible at all - exactly
        the ALL-vs-CH mismatch a screenshot showed 26.09.2026.
        """
        for doc in list(self._rx_docs.values()) + [self._rx_doc_all]:
            doc.setDefaultFont(font)

    def _sync_rx_document(self) -> None:
        """Attach rx_display to whichever document the current ALL/CH +
        channel selection implies (P50 Teil B) - ALL always shows
        _rx_doc_all; CH shows the current channel's own document. Saves
        the OUTGOING document's scroll position and restores the
        INCOMING one's (defaulting to the bottom for a document that has
        never been scrolled), so switching back and forth does not reset
        your reading position each time."""
        self._rx_scroll[self._rx_current_key] = self.rx_display.verticalScrollBar().value()
        new_key = self._ALL_DOC_KEY if self._view_all else self.current_channel()
        new_doc = (
            self._rx_doc_all if new_key == self._ALL_DOC_KEY
            else self._rx_docs[new_key]
        )
        self._rx_current_key = new_key
        if self.rx_display.document() is not new_doc:
            self.rx_display.setDocument(new_doc)
        self.rx_display.verticalScrollBar().setValue(
            self._rx_scroll.get(new_key, self.rx_display.verticalScrollBar().maximum())
        )

    def _on_rx_channel_switch(self, _new_ch: int) -> None:
        """ChannelBar.channel_changed - re-sync the visible RX document
        (P50 Teil B). ChannelBar itself updates current() BEFORE emitting
        this signal, so _sync_rx_document() reading current_channel()
        fresh already sees the new channel; _new_ch is not needed."""
        self._sync_rx_document()

    def set_view_all(self, show_all: bool) -> None:
        self._view_all = show_all
        self._sync_rx_document()

    def append_channel_data(self, channel: "int | str", text: str, color: str = "#66ccff") -> None:
        """Append received connected-channel data - or, via an explicit
        *color* override, a channel-scoped system/link message (P47) -
        to *channel*'s own RX document AND the merged ALL document (P50
        Teil B). Every line lives in both, so switching to a channel
        later shows its FULL history, not just what arrives from then
        on; the ALL/CH filter (T100) is now a matter of which document
        rx_display is showing (_sync_rx_document()), not whether a line
        gets written at all.
        """
        self._rx_append(channel, text, is_html=False, color=color)

    def append_monitor_data(self, text: str, is_html: bool = False,
                             ts: str = "") -> None:
        """Append a monitored/unproto frame to the MON view's own RX
        document AND the merged ALL document (P50 Teil B). Monitor frames
        carry no channel of their own ($3F, TRM 4.3) — they belong to the
        MON view (P70), not to any TNC channel.

        `ts` is optional and only used by
        MainWindow._packet_rx_redraw()/append_monitor_data_local_only()
        to replay a HISTORICAL timestamp when the user toggles APRS
        decode on/off (T59/T60). Live callers omit it and get the
        current UTC time, same as append_channel_data().
        """
        self._rx_append(MON_VIEW, text, is_html=is_html, color="#aaaaaa", ts=ts)

    def append_monitor_data_local_only(self, text: str, is_html: bool = False,
                                        ts: str = "") -> None:
        """Same rendering as append_monitor_data(), but writes ONLY into
        the MON view's own document, never ALL (P50 Teil B/APRS
        interplay) - used exclusively by
        MainWindow._packet_rx_redraw()/clear_monitor_channel() when the
        APRS decode toggle changes. See clear_monitor_channel()'s own
        docstring for why ALL is deliberately left untouched by that
        redraw."""
        if not ts:
            ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self._rx_write_line(self._rx_docs[MON_VIEW], None, text, is_html, "#aaaaaa", ts)
        if self.rx_display.document() is self._rx_docs[MON_VIEW]:
            self.rx_display.moveCursor(QTextCursor.MoveOperation.End)
            self.rx_display.ensureCursorVisible()

    def clear_monitor_channel(self) -> None:
        """Clear ONLY the MON view's own RX document - called by
        MainWindow._packet_rx_redraw() right before replaying
        _packet_raw_frames through append_monitor_data_local_only(),
        when the APRS decode toggle changes (T59/T60).

        Deliberately does NOT touch the merged ALL document (P50 Teil B):
        ALL is a chronological log of everything that has already
        arrived, from every channel. Rebuilding it here would either
        duplicate every historical monitor line (replayed through the
        normal dual-write append_monitor_data()) or silently drop every
        QSO-channel line recorded since (if cleared outright) - neither
        of which an APRS raw<->decoded toggle should do. Only the CH view
        of the MON view (which, by construction, ever receives monitor
        frames and nothing else) reflects the new decode mode; ALL keeps
        its already-rendered history exactly as it was.
        """
        self._rx_docs[MON_VIEW].clear()

    def _rx_write_line(self, doc, tag: str | None, text: str, is_html: bool,
                        color: str, ts: str) -> None:
        """Write ONE formatted line into *doc* - the shared primitive
        both _rx_append() (writes to a channel's own doc + ALL) and
        append_monitor_data_local_only() (writes to the MON view's own
        doc only) use.

        *tag* is the compact ALL-view channel tag (P50 Teil C, e.g.
        "2|"); pass None for a channel's own document, where the channel
        is already implied by which chip/view is selected, not repeated
        on every line. The optional timestamp (self._show_timestamps)
        and the tag are always rendered in the muted colour, never the
        line's own *color* - a system message's eye-catching colour (an
        explicit non-default *color* from a link/status message, P47)
        still stands out against them.
        """
        cursor = QTextCursor(doc)
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if self._show_timestamps:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(self._MUTED_RX_COLOR))
            cursor.setCharFormat(fmt)
            cursor.insertText(f"[{ts}] ")
        if tag is not None:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(self._MUTED_RX_COLOR))
            cursor.setCharFormat(fmt)
            cursor.insertText(f"{tag}│")
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
            cursor.insertText(f"{lines[0]}\n")
            for line in lines[1:]:
                cursor.insertText(f"         {line}\n")
            cursor.insertText("\n")

    def _rx_append(self, channel: "int | str", text: str, is_html: bool, color: str,
                    ts: str = "") -> None:
        """Write one line into *channel*'s own document (no prefix - the
        channel is already named by which chip/view is selected) and the
        merged ALL document (compact "n|" tag, P50 Teil B/C)."""
        if not ts:
            ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self._rx_write_line(self._rx_docs[channel], None, text, is_html, color, ts)
        self._rx_write_line(
            self._rx_doc_all, self._all_view_tag(channel), text, is_html, color, ts
        )
        if self.rx_display.document() in (self._rx_docs[channel], self._rx_doc_all):
            self.rx_display.moveCursor(QTextCursor.MoveOperation.End)
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

        # P42: the old "Connect · Dest · ... · Disconnect" row is gone —
        # a callsign is typed directly into the free channel chip you want
        # to connect on (see ChannelChip/ChannelBar above and CLAUDE.md's
        # channel-model section). "Connect via…" (digipeater path) is a
        # chip context-menu entry, wired to PacketConnectDialog.

        # 4. Unproto row: Unproto · via · Monitor ───────────────────────
        unproto_row = QHBoxLayout()
        unproto_row.setSpacing(SPACING)

        self.btn_unproto = _no_focus_btn("Unproto", BTN_W)
        self.btn_unproto.setCheckable(True)
        self.btn_unproto.setStyleSheet(_STYLE_UNPROTO_OFF)
        self.btn_unproto.setToolTip(
            "Switch to the MON view and set the UNPROTO path.\n"
            "Text typed in the MON view goes out as unconnected UI frames\n"
            "(no ARQ, no acknowledge) via the lowest free channel.\n"
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

        # MailDrop session dialog (P39) — opens maildrop_dialog.py's
        # MailDropDialog, wired in main_window.py's
        # _on_open_maildrop_dialog(). Never sends a Host Mode frame of
        # its own (that was the P21.5 bug: 'MI' is MFILTER, not a
        # MailDrop login — MDCHECK has no Host Mode mnemonic at all,
        # CLAUDE.md). Starts disabled; MainWindow._update_maildrop_
        # gate_ui() enables it and sets the real tooltip once the four
        # gate conditions (connection, mode, channel, has_maildrop) are
        # known — this default is only what shows before that first runs.
        self.btn_maildrop = _no_focus_btn("MailDrop", BTN_W)
        self.btn_maildrop.setEnabled(False)
        self.btn_maildrop.setToolTip("connect to the TNC first")
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
        self.btn_passall.setToolTip("PASSALL (PX) — receive all frames regardless of CRC.")
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

        # P9: per-channel TX buffer swap. Connected here, in the screen
        # itself, immediately after the ChannelBar is built — NOT in
        # MainWindow. Qt calls a signal's slots in connection order; the
        # screen connects during __init__/_build_ui(), MainWindow only
        # later in _wire_packet_buttons() (itself only run on a mode
        # switch). Connecting here first guarantees the buffer swap has
        # already happened by the time any MainWindow slot on the same
        # channel_changed signal touches tx_input.
        self._tx_channel = self.channel_bar.current()
        self.channel_bar.channel_changed.connect(self._on_tx_channel_switch)
        # P50 Teil B: RX document swap, same "connect here first" reasoning
        # as the TX buffer swap above.
        self.channel_bar.channel_changed.connect(self._on_rx_channel_switch)

        add_hline(root)

        # 8+9. RX/TX as a vertical splitter (P50 Teil D) — RX grows with
        # the window; TX height is adjustable by dragging the splitter
        # handle instead of a fixed five-line height (which stays only as
        # the STARTING size, not a hard constraint). The handle itself
        # replaces the hline that used to sit between them.
        self._rxtx_splitter = QSplitter(Qt.Orientation.Vertical)

        self.rx_display = QTextEdit()
        self.rx_display.setReadOnly(True)
        # P56.A: no explicit font here - MainWindow._apply_appearance()
        # sets it (and every RX document's, via apply_rx_font() below),
        # both at startup and on every later Appearance change. Setting
        # one here too would just be a second, temporary source that
        # _apply_appearance() immediately overwrites in production
        # anyway - removing it entirely is what keeps this screen and
        # its documents from ever disagreeing on font again.
        self.rx_display.setPlaceholderText(
            "RX — received and monitored AX.25 frames appear here …\n\n"
            "Connected data:   $3x frames (channel data)\n"
            "Monitored frames: $3F frames (unproto / UI)"
        )
        self.rx_display.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.rx_display.setMinimumHeight(80)   # never fully squeezed away
        style_rx_widget(self.rx_display)
        self.rx_display.setDocument(self._rx_doc_all)   # _view_all defaults True
        self._rxtx_splitter.addWidget(self.rx_display)

        tx_container = QWidget()
        tx_container.setMinimumHeight(60)   # never fully squeezed away
        tx_row = QHBoxLayout(tx_container)
        tx_row.setContentsMargins(0, 0, 0, 0)
        tx_row.setSpacing(SPACING)

        self.tx_input = QTextEdit()
        self.tx_input.setFont(QFont("Courier New", 10))
        self.tx_input.setPlaceholderText("TX — type here …")
        self.tx_input.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        fm = self.tx_input.fontMetrics()
        mc = self.tx_input.contentsMargins()
        _tx_start_height = fm.lineSpacing() * 5 + mc.top() + mc.bottom() + 8
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

        # addStretch() keeps the button column top-anchored at its
        # natural size — it must NOT grow when the splitter handle is
        # dragged to give the TX pane more height (P50 Teil D).
        tx_btn_col.addStretch()
        tx_row.addLayout(tx_btn_col)

        self._rxtx_splitter.addWidget(tx_container)
        self._rxtx_splitter.setStretchFactor(0, 1)   # RX takes any extra space
        self._rxtx_splitter.setStretchFactor(1, 0)   # TX stays put unless dragged
        self._rxtx_splitter.setSizes([400, _tx_start_height])
        root.addWidget(self._rxtx_splitter, stretch=1)

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
        outer.addWidget(splitter, stretch=1)

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

    def _update_status_bar(self, ch: "int | str") -> None:
        partner = self.channel_bar.partner(ch)
        self.lbl_sb_channel.setText("MON" if ch == MON_VIEW else f"Ch {ch}")
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
        """Kept for MainWindow's callers; no longer touches anything.

        Until P70 this greyed btn_unproto while a channel was connected/
        calling (T39, Connect <-> Unproto mutually exclusive). Device B
        (T146 F1/F2) showed Unproto on a FREE channel works with another
        channel connected, and Unproto now goes out on the lowest free
        channel (MainWindow._on_packet_tx_enter()), so a connection never
        locks the button any more.
        """

    def on_unproto_toggled(self, checked: bool) -> None:
        """Visual feedback for Unproto button toggle."""
        if checked:
            self.btn_unproto.setStyleSheet(_STYLE_UNPROTO_ON)
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
