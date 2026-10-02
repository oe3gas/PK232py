# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""comm/link_table.py - LinkTable, the app-side mirror of the TNC's own
per-channel connection state (P64/P67, Teil B).

Qt-free, pure Python - no serial I/O, no widget refs. Fed by BOTH
verbose-mode text and Host Mode frames (via the small, documented set
of on_*() methods below), so a verbose<->Host Mode switch never loses
track of what channel is actually connected to whom - closing the gap
P64 first reported and P66/P66b measured the real mechanism of.

MainWindow owns exactly one instance and translates its subscribe()
callback into Qt-side widget updates (ChannelBar chips, etc.) - this
module itself never touches Qt, so it is fully unit-testable without a
QApplication.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional

from .link_status import LinkStatus, extract_partner, split_channel_prefix

CHANNEL_COUNT = 10

STATE_FREE        = "free"
STATE_CALLING     = "calling"
STATE_CONNECTED   = "connected"
STATE_UNCONFIRMED = "unconfirmed"
# P70 (T146/T147 F6): after a DI the TNC reports CO state 4 for a moment
# (disconnect in progress) before the channel is free again.
STATE_DISCONNECTING = "disconnecting"

# CO state number (decode_link_status().state) that means "disconnecting".
_CO_STATE_DISCONNECTING = 4


@dataclass
class ChannelLink:
    """One channel's own state in the table - mirrors ChannelBar's
    existing CH_FREE/CH_CALLING/CH_CONNECTED chip states (packet_
    screen.py) plus the new CH_UNCONFIRMED one (P67, Teil C.1)."""
    state: str = STATE_FREE
    partner: str = ""
    since: float = 0.0


class LinkTable:
    """App-side mirror of the TNC's own per-channel connection state.

    Each on_*() method below is the ONE place a particular kind of
    evidence enters the table - never call _set() (or otherwise touch
    .channels directly) from outside this class. Every state change
    notifies subscribe()'d observers with (channel, ChannelLink), so a
    UI never needs to poll.
    """

    def __init__(self) -> None:
        self.channels: list[ChannelLink] = [
            ChannelLink() for _ in range(CHANNEL_COUNT)
        ]
        self.io_channel: int = 0
        self.converse: bool = False
        self.mode_name: Optional[str] = None
        self._observers: list[Callable[[int, ChannelLink], None]] = []
        self._event_observers: list[Callable[[int, str, str], None]] = []

    # -- Observation -----------------------------------------------------

    def subscribe_events(self, callback: Callable[[int, str, str], None]) -> None:
        """Register *callback(channel, event, partner)* for EVENTS (P76) -
        distinct from subscribe(), which reports STATES. The one event so
        far is "connected": a link message said a connection was just made.
        The same state change also arises from reconciliation
        (on_link_status() after a CO query, on_verbose_cstatus(), e.g.
        after every Host Mode entry) - that is NOT a new connection and
        never produces an event, which is why a state callback could not
        be used for a bell."""
        self._event_observers.append(callback)

    def _emit_connected(self, channel: int, was: str, partner: str) -> None:
        """Fire "connected" if the channel was neither connected nor
        unconfirmed (= believed connected) before this link message."""
        if not (0 <= channel < CHANNEL_COUNT):
            return
        if was in (STATE_CONNECTED, STATE_UNCONFIRMED):
            return
        if self.channels[channel].state != STATE_CONNECTED:
            return
        for callback in self._event_observers:
            callback(channel, "connected", partner)

    def subscribe(self, callback: Callable[[int, ChannelLink], None]) -> None:
        """Register *callback(channel, link)*, called once per state
        change - including ones already applied before this call, if a
        caller wants that, it re-subscribes after re-building the
        table; this method itself does NOT replay existing state."""
        self._observers.append(callback)

    def _notify(self, channel: int) -> None:
        link = self.channels[channel]
        for callback in self._observers:
            callback(channel, link)

    def _set(self, channel: int, state: str, partner: str = "") -> None:
        if not (0 <= channel < CHANNEL_COUNT):
            return
        current = self.channels[channel]
        if current.state == state and current.partner == partner:
            return
        self.channels[channel] = ChannelLink(
            state=state, partner=partner, since=time.time(),
        )
        self._notify(channel)

    # -- Inputs (P67, Teil B.2) ------------------------------------------

    def on_host_link_message(self, channel: int, text: str) -> None:
        """A $5x link message's TEXT, already channel-attributed by its
        own CTL nibble (never by callsign - CLAUDE.md's P47 gotcha).
        Classifies the known shapes (CONNECTED to/DISCONNECTED/busy/
        Retry count exceeded) - an unrecognised text leaves the channel
        untouched rather than guessing.

        'Connect request: <call>' deliberately changes NOTHING (P70 E,
        Device B T147 F4): with USERS too low the TNC sends it for a call
        it then rejects on the air (DM), so it proves no link at all.
        MainWindow reports it to the operator instead."""
        lower = text.lower()
        if "connected to" in lower and "disconnect" not in lower:
            was = self.channels[channel].state if 0 <= channel < CHANNEL_COUNT else ""
            partner = extract_partner(text)
            self._set(channel, STATE_CONNECTED, partner)
            self._emit_connected(channel, was, partner)
        elif "disconnected" in lower or "busy" in lower:
            self._set(channel, STATE_FREE)
        elif "retry count exceeded" in lower:
            self._set(channel, STATE_FREE)

    def on_link_status(self, status: LinkStatus) -> None:
        """A TRM 4.3.3 CO answer (Host Mode) - the one input that marks
        a channel CONFIRMED (never 'unconfirmed'), which is exactly
        what mark_unconfirmed() + a fresh round of these calls is for.
        An unparsed response or a one-byte error code proves nothing
        about the channel's real state, so it is ignored here rather
        than guessed."""
        if status.unparsed or status.error_code is not None:
            return
        if status.connected:
            self._set(status.channel, STATE_CONNECTED, status.partner)
        elif status.state == _CO_STATE_DISCONNECTING:
            self._set(status.channel, STATE_DISCONNECTING, status.partner)
        else:
            self._set(status.channel, STATE_FREE)

    def on_verbose_line(self, line: str) -> None:
        """One line of verbose-mode text. A channel-number prefix (P67
        M10, split_channel_prefix()) names the channel if present;
        otherwise the line is attributed to the current io_channel -
        the TNC's own active channel in verbose mode (P66b, B.3/B.4).
        A line ending in 'cmd:' means the TNC is back at the command
        prompt (converse = False); '*** CONNECTED to X' sets converse
        = True (the TNC only shows this while the just-connected
        channel is live in Converse, TRM); '*** DISCONNECTED: X' frees
        the channel without changing converse (a DISCONNECTED can
        arrive while a DIFFERENT channel or the command prompt itself
        is what is actually shown)."""
        channel_hint, text = split_channel_prefix(line)
        channel = channel_hint if channel_hint is not None else self.io_channel
        lower = text.lower()
        if "connected to" in lower and "disconnect" not in lower:
            was = self.channels[channel].state if 0 <= channel < CHANNEL_COUNT else ""
            partner = extract_partner(text)
            self._set(channel, STATE_CONNECTED, partner)
            self.converse = True
            self._emit_connected(channel, was, partner)
        elif "disconnected" in lower:
            self._set(channel, STATE_FREE)
        elif text.rstrip().endswith("cmd:"):
            self.converse = False

    def on_verbose_cstatus(self, parsed: dict[int, tuple[bool, str, str]]) -> None:
        """A parsed verbose CSTATUS response (comm.link_status.
        parse_cstatus()) - the reconciliation point after a Host ->
        verbose switch (P66b, B.3/B.6). Sets io_channel from whichever
        line carried the 'IO' marker; a line naming a partner confirms
        that channel connected. A channel CSTATUS calls free (no
        partner, not IO) is left as-is here - CSTATUS's own free-
        channel text shape is not yet measured well enough to
        classify confidently (hw_check rule 6); on_link_status()
        (Host Mode CO) is the confirmed way to mark a channel free."""
        for channel, (io, _state_text, partner) in parsed.items():
            if io:
                self.io_channel = channel
            if partner:
                self._set(channel, STATE_CONNECTED, partner)

    def lowest_free_channel(self) -> Optional[int]:
        """The lowest channel whose state is exactly 'free' (not calling,
        unconfirmed or disconnecting), or None if all ten are busy. The
        channel Unproto goes out on (P70 D, T146 F1/F2)."""
        for channel, link in enumerate(self.channels):
            if link.state == STATE_FREE:
                return channel
        return None

    def on_local_connect_attempt(self, channel: int, callsign: str) -> None:
        """The operator just committed a callsign into a channel chip's
        own inline editor and a CO frame went out (P42) - optimistic
        local state, shown as CALLING immediately rather than waiting
        for the TNC's own CONNECTED/failed link message. Confirmed or
        corrected the same way any other CALLING transition is, by the
        next on_host_link_message()/on_link_status() call for this
        channel."""
        self._set(channel, STATE_CALLING, callsign)

    def on_local_disconnect_request(self, channel: int) -> None:
        """The operator asked to disconnect a channel (chip context
        menu or Ctrl+K) and a DI frame went out (P42) - optimistic
        local state, shown as FREE immediately rather than waiting for
        the TNC's own DISCONNECTED link message."""
        self._set(channel, STATE_FREE)

    def mark_unconfirmed(self) -> None:
        """Call before every reconciliation round (a verbose<->Host
        Mode switch) - every currently 'connected' channel becomes
        'unconfirmed' until the round's own on_link_status()/
        on_verbose_cstatus() calls confirm it again. A channel that
        was never connected is untouched - 'unconfirmed' only ever
        means "this table BELIEVED it was connected, not proven yet
        this round", never "unknown in general"."""
        for channel, link in enumerate(self.channels):
            if link.state == STATE_CONNECTED:
                self._set(channel, STATE_UNCONFIRMED, link.partner)

    def reset(self) -> None:
        """Clear every channel back to free - ONLY for a genuine loss
        of the table's own basis for believing anything (disconnect
        from the TNC, a fresh boot banner/fresh_boot_defaults, or a
        Recovery run with nothing to reconcile against). Never called
        on an ordinary verbose<->Host Mode switch - mark_unconfirmed()
        plus reconciliation is what that path uses instead, precisely
        so a real connection is not forgotten just because the app
        briefly could not confirm it. mode_name is NOT reset - the
        operator's last chosen operating mode is not invalidated by
        the TNC dropping out from under it."""
        for channel in range(CHANNEL_COUNT):
            self._set(channel, STATE_FREE)
        self.io_channel = 0
        self.converse = False
