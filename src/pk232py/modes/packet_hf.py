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
from pk232py.modes.base_mode import BaseMode

if TYPE_CHECKING:
    from pk232py.comm.frame import HostFrame

logger = logging.getLogger(__name__)

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
    """

    name         = "HF Packet"
    host_command = b'PA'

    def __init__(self) -> None:
        super().__init__()
        # Callbacks — set by the UI or mode manager
        self.on_data_received: Optional[Callable[[int, bytes], None]] = None
        self.on_monitor_frame: Optional[Callable[[bytes], None]]      = None
        self.on_link_message:  Optional[Callable[[int, str], None]]   = None
        self.on_data_ack:      Optional[Callable[[int], None]]        = None

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

        Currently enables the frame monitor (MONITOR ON).
        Override or extend in subclasses / configuration to add more
        parameters (HBAUD, FRACK, MAXFRAME, UNPROTO, etc.).
        """
        return [
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