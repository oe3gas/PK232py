# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""HF Packet operating mode (AX.25, 300 baud).

In Host Mode, Packet operation produces the following frame types
(TRM Section 4.3 / 4.4):

  Incoming (TNC -> Host):
    $3x  RX_DATA     — received data from channel x (ARQ I-frames)
    $3F  RX_MONITOR  — monitored/unproto frames
    $4x  LINK_STATUS — link status response to CONNECT query
    $5x  LINK_MSG    — link messages: CONNECTED, DISCONNECTED, ...
    $5F  STATUS_ERR  — data acknowledgement / error

  Outgoing (Host -> TNC):
    $4x  build_ch_cmd(ch, b'CO', callsign)  — CONNECT
    $4x  build_ch_cmd(ch, b'DI')            — DISCONNECT
    $2x  build_data(ch, data)               — send data on channel x
    $4F  build_command(b'PA')               — enter Packet mode
    $4F  build_command(b'MN', b'Y')         — MONITOR ON
    $4F  build_command(b'UN', b'CQ')        — UNPROTO CQ

TODO (v0.2):
    - Implement full connect/disconnect flow with channel tracking
    - Handle multi-stream connections (channels 1-9)
    - Parse MHEARD responses
    - Implement digipeater path support
    - MailDrop integration
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Optional

from pk232py.comm.frame import build_command, build_ch_cmd, build_data, FrameKind
from pk232py.config import HFPacketConfig
from pk232py.modes.base_mode import BaseMode

if TYPE_CHECKING:
    from pk232py.comm.frame import HostFrame

logger = logging.getLogger(__name__)


def _extract_partner(text: str) -> str:
    """Best-effort far-end callsign extraction from a link-message string.

    Handles the two message shapes seen in the TRM / mock TNC:
      "CONNECTED to OE1XYZ-5"   -> "OE1XYZ-5"   (" to " marker)
      "Connect request: OE1XYZ" -> "OE1XYZ"     (":" marker)
    Falls back to the first whitespace-separated token, e.g. "OE1XYZ busy".
    Returns "" if nothing usable is found — callers must tolerate that.
    """
    lower = text.lower()
    if " to " in lower:
        tail = text[lower.index(" to ") + 4:].strip()
        # Some firmware variants send "CONNECTED to: OE1XYZ-5" (colon before
        # the callsign, per the STABO manual chapter 12) instead of the TRM
        # 4.4.4 "CONNECTED to OE1XYZ-5" form. Strip one optional leading ':'
        # (and the whitespace around it) before taking the first token, or
        # the colon itself gets misread as the callsign. A trailing
        # " via ..." digipeater path is already dropped by split()[0] either
        # way, with or without the colon.
        if tail.startswith(":"):
            tail = tail[1:].strip()
        return tail.split()[0] if tail else ""
    if ":" in text:
        tail = text.split(":", 1)[1].strip()
        return tail.split()[0] if tail else ""
    tokens = text.strip().split()
    return tokens[0] if tokens else ""


# Link message substrings used to classify incoming $5x frames
_MSG_CONNECTED    = "connected"
_MSG_DISCONNECTED = "disconnected"
_MSG_BUSY         = "busy"
_MSG_CONNECT_REQ  = "connect request"
_MSG_RETRY        = "retry count"
_MSG_FRMR         = "frmr"
_MSG_LINK_OOO     = "link out of order"


class HFPacketMode(BaseMode):
    """AX.25 HF Packet mode (300 baud).

    Handles incoming Host Mode frames and builds outgoing command frames
    for the Packet operating mode of the PK-232MBX.

    Callbacks
    ---------
    Set these attributes to receive notifications from the mode:

    ``on_data_received``   : ``Callable[[int, bytes], None]``
        Called with (channel, data) when data arrives on a connected channel.

    ``on_monitor_frame``   : ``Callable[[bytes], None]``
        Called with raw bytes of a monitored (unproto) frame.

    ``on_link_message``    : ``Callable[[int, str], None]``
        Called with (channel, message_text) for link state changes
        (CONNECTED, DISCONNECTED, busy, connect request, etc.).

    ``on_data_ack``        : ``Callable[[int], None]``
        Called with channel when the TNC acknowledges a sent data block.

    ``on_channel_state``   : ``Callable[[int, str, str], None]``
        Called with (channel, state, partner) whenever a link message implies
        a channel state change. ``state`` is one of "free"/"calling"/
        "connected". This is a second, channel-scoped consumer of the same
        $5x frames already handled by ``on_link_message`` above — it feeds
        ChannelBar (packet_screen.py) rather than the screen-wide status
        label. There is no CSTATUS poll in Host Mode (see CLAUDE.md
        "Channel model"), so this is the only way the UI learns which
        channel a partner callsign belongs to.
    """

    name         = "HF Packet"
    host_command = b'PA'
    verbose_command = b"PACKET\r\n"

    def __init__(
        self,
        maxframe: int = HFPacketConfig.maxframe,
        slottime: int = HFPacketConfig.slottime,
    ) -> None:
        """
        Args:
            maxframe: MAXFRAME to send in get_init_frames() (mnemonic MX).
                      Defaults to HFPacketConfig's own default (P19.3) —
                      one source of truth, not a repeated number.
            slottime: SLOTTIME to send in get_init_frames() (mnemonic SL).
                      Defaults to HFPacketConfig's own default (P19.3).
                      Callers that know the real configured values (e.g.
                      main_window.py's _build_mode_instance()) should pass
                      them in here via ModeManager.set_mode(name,
                      mode_instance=...) — see T112 (P18.1): without this,
                      HF Packet kept whatever MAXFRAME/SLOTTIME VHF Packet
                      last set.
        """
        super().__init__()
        self.maxframe = maxframe
        self.slottime = slottime
        # Callbacks — set by the UI or mode manager
        self.on_data_received: Optional[Callable[[int, bytes], None]] = None
        self.on_monitor_frame: Optional[Callable[[bytes], None]]      = None
        self.on_link_message:  Optional[Callable[[int, str], None]]   = None
        self.on_data_ack:      Optional[Callable[[int], None]]        = None
        self.on_channel_state: Optional[Callable[[int, str, str], None]] = None
        # One MHEARD line per call (polled line-by-line, TRM §4.11). The raw
        # ASCII line text, e.g. "18:06 OE3GAS*"; end-of-list lines are filtered
        # out before this fires.
        self.on_mheard_entry:  Optional[Callable[[str], None]]        = None

    # ------------------------------------------------------------------
    # BaseMode interface
    # ------------------------------------------------------------------

    def get_activate_frames(self) -> list[bytes]:
        """Return the frame to switch the TNC into Packet mode.

        TRM Section 4.2.2, mnemonic PA.
        """
        return [build_command(b'PA')]

    def get_init_frames(self) -> list[bytes]:
        """Return parameter frames sent after Packet mode is confirmed.

        HF Packet selects the 300 Bd HF FSK modem (VHF OFF), resets
        MAXFRAME/SLOTTIME to its own configured values, and enables the
        frame monitor.  Sequence: VH N, HB 300, MX <maxframe>,
        SL <slottime>, MN Y.

        Lernmodus: ``VH N`` is essential here — without it, switching to HF
        Packet *after* VHF Packet would leave the TNC on the 1200 Bd Bell-202
        modem (VHF stays ON until explicitly cleared), so HF would never decode.
        ``MX``/``SL`` are the same rule applied to MAXFRAME/SLOTTIME
        (Testplan T112, hardware-confirmed for SLOTTIME 2026-09-22): VHF
        Packet sets MX 4 / SL 10 on activation, and without HF Packet
        resetting them here, HF Packet kept running with VHF's values after
        a VHF -> HF switch. VHFPacketMode deliberately does NOT inherit this
        list (it would undo its own ``VH Y``); it builds its own — see
        VHFPacketMode.get_init_frames().
        """
        return [
            build_command(b'VH', b'N'),   # VHF OFF — select 300 Bd HF FSK modem
            build_command(b'HB', b'300'), # HBAUD 300
            build_command(b'MX', str(self.maxframe).encode('ascii')),  # MAXFRAME
            build_command(b'SL', str(self.slottime).encode('ascii')),  # SLOTTIME
            build_command(b'MN', b'Y'),   # MONITOR ON — receive unproto frames
        ]

    def handle_frame(self, frame: "HostFrame") -> None:
        """Dispatch an incoming Host Mode frame to the appropriate handler.

        Frame types handled (TRM Section 4.3 / 4.4):
          RX_DATA     ($3x) — received channel data
          RX_MONITOR  ($3F) — monitored/unproto frames
          LINK_STATUS ($4x) — link status (response to CONNECT query)
          LINK_MSG    ($5x) — link messages (CONNECTED, DISCONNECTED, …)
          STATUS_ERR  ($5F) — data acknowledgement / error

        Args:
            frame: Decoded HostFrame from the TNC.
        """
        kind = frame.kind

        if kind == FrameKind.RX_DATA:
            self._handle_rx_data(frame)

        elif kind == FrameKind.RX_MONITOR:
            self._handle_monitor(frame)

        elif kind == FrameKind.LINK_STATUS:
            # Response to a CONNECT query (SOH $4x 'C' 'O' status ETB)
            # Logged only at this stage — full link-state parsing in v0.2
            logger.debug(
                "Link status ch=%d: %s", frame.channel, frame.data.hex()
            )

        elif kind == FrameKind.LINK_MSG:
            self._handle_link_msg(frame)

        elif kind == FrameKind.STATUS_ERR:
            self._handle_status_err(frame)

        elif kind == FrameKind.CMD_RESP:
            self._handle_cmd_resp(frame)

        else:
            logger.debug("HFPacket: unhandled frame %r", frame)

    # ------------------------------------------------------------------
    # Outgoing command helpers
    # ------------------------------------------------------------------

    def connect_frame(self, callsign: str, channel: int = 1) -> bytes:
        """Build a CONNECT frame for *callsign* on *channel* (CTL = $4x).

        TRM Section 4.2.3.

        Args:
            callsign: Destination callsign, e.g. ``'OE3XYZ'`` or
                      ``'OE3XYZ-1'`` or ``'OE3XYZ VIA OE1XAB'``.
            channel:  Packet channel 1-9 (default 1).
        """
        return build_ch_cmd(
            channel, b'CO', callsign.upper().encode('ascii')
        )

    def disconnect_frame(self, channel: int = 1) -> bytes:
        """Build a DISCONNECT frame for *channel* (CTL = $4x).

        TRM Section 4.2.3.
        """
        return build_ch_cmd(channel, b'DI')

    def data_frame(self, data: bytes, channel: int = 1) -> bytes:
        """Build a data frame to send on *channel* (CTL = $2x).

        TRM Section 4.4.  Wait for data-ACK before sending the next block.

        Args:
            data:    Bytes to send (will be packetized by the TNC).
            channel: Packet channel 1-9 (default 1).
        """
        return build_data(channel, data)

    def unproto_frame(self, path: str = "CQ") -> bytes:
        """Build an UNPROTO destination/path command frame.

        Args:
            path: e.g. ``'CQ'`` or ``'CQ VIA OE1XAB'``.
        """
        return build_command(b'UN', path.upper().encode('ascii'))

    def monitor_frame(self, enabled: bool) -> bytes:
        """Build a MONITOR ON/OFF command frame (mnemonic MN)."""
        return build_command(b'MN', b'Y' if enabled else b'N')

    # ------------------------------------------------------------------
    # Private frame handlers
    # ------------------------------------------------------------------

    def _handle_rx_data(self, frame: "HostFrame") -> None:
        """Handle $3x — received data from channel x."""
        logger.debug(
            "RX data ch=%d len=%d", frame.channel, len(frame.data)
        )
        if self.on_data_received:
            self.on_data_received(frame.channel, frame.data)

    def _handle_monitor(self, frame: "HostFrame") -> None:
        """Handle $3F — monitored / unproto frame."""
        logger.debug("Monitor frame len=%d", len(frame.data))
        if self.on_monitor_frame:
            self.on_monitor_frame(frame.data)

    def _handle_link_msg(self, frame: "HostFrame") -> None:
        """Handle $5x — link messages (TRM Section 4.4.4).

        Known messages:
          CONNECTED to <callsign>
          <callsign> busy
          Connect request: <callsign>
          DISCONNECTED: <callsign>
          Retry count exceeded
          FRMR sent/rcvd: xx yy zz
          LINK OUT OF ORDER, possible data loss
        """
        text = frame.text.strip()
        ch   = frame.channel
        lower = text.lower()

        if _MSG_CONNECTED in lower and _MSG_DISCONNECTED not in lower:
            logger.info("ch%d: %s", ch, text)
        elif _MSG_DISCONNECTED in lower:
            logger.info("ch%d: %s", ch, text)
        elif _MSG_CONNECT_REQ in lower:
            logger.info("ch%d incoming: %s", ch, text)
        elif _MSG_BUSY in lower:
            logger.info("ch%d: %s", ch, text)
        elif _MSG_RETRY in lower:
            logger.warning("ch%d: %s", ch, text)
        elif _MSG_FRMR in lower:
            logger.warning("ch%d FRMR: %s", ch, text)
        elif _MSG_LINK_OOO in lower:
            logger.error("ch%d: %s", ch, text)
        else:
            logger.debug("ch%d link msg: %s", ch, text)

        if self.on_link_message:
            self.on_link_message(ch, text)

        # Channel-scoped state for ChannelBar (P3) — a second consumer of the
        # same message, independent of on_link_message above. Retry/FRMR/
        # link-out-of-order are left alone here (they do not by themselves
        # mean the channel is free again — a DISCONNECTED usually follows).
        if self.on_channel_state:
            if _MSG_CONNECTED in lower and _MSG_DISCONNECTED not in lower:
                self.on_channel_state(ch, "connected", _extract_partner(text))
            elif _MSG_CONNECT_REQ in lower:
                # "Connect request: <call>" means the incoming call was heard
                # and understood, NOT that the link is up — per the TRM this
                # is the not-yet-accepted state, so it maps to "calling", the
                # same bucket _make_link_handler() already uses for the
                # screen-wide status label (keeps the two consumers of this
                # message consistent). CAUTION: if CONOK is OFF (no
                # auto-accept), no CONNECTED/DISCONNECTED may ever follow a
                # request that is not answered, so the chip can stay
                # "calling" indefinitely — Disconnect always frees it.
                self.on_channel_state(ch, "calling", _extract_partner(text))
            elif _MSG_DISCONNECTED in lower or _MSG_BUSY in lower:
                self.on_channel_state(ch, "free", "")

    def _handle_status_err(self, frame: "HostFrame") -> None:
        """Handle $5F — data ACK or status error (TRM Section 4.4.1).

        Data ACK:   SOH $5F X X $00 ETB  (third data byte = $00)
        Bad block:  SOH $5F X X 'W' ETB
        Bad CTL:    SOH $5F X X 'Y' ETB
        """
        if len(frame.data) >= 3 and frame.data[2] == 0x00:
            logger.debug("Data ACK ch=%d", frame.channel)
            if self.on_data_ack:
                self.on_data_ack(frame.channel)
        else:
            logger.warning(
                "Status error ch=%d data=%s", frame.channel, frame.data.hex()
            )

    def _handle_cmd_resp(self, frame: "HostFrame") -> None:
        """Handle $4F — command response.  Currently only MHEARD lines.

        The MHEARD list is polled line-by-line (MH0..MH17, TRM §4.11): each
        line arrives as a CMD_RESP whose payload is ``b'MH'`` + the line text,
        e.g. ``b'MH18:06 OE3GAS*'``.  "No more entries" is ``b'MH'`` + ``$00``
        (or just ``b'MH'``).  Forward each non-empty line to on_mheard_entry;
        plain command ACKs (EA/PS/HB/… → ``b'XX' + $00``) are ignored here.
        """
        if frame.mnemonic != b'MH':
            return
        line_data = frame.data[2:]   # strip the 'MH' echo → the line itself
        if line_data and line_data != b'\x00' and self.on_mheard_entry:
            self.on_mheard_entry(line_data.decode('ascii', errors='replace'))