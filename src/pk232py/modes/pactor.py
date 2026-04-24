# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""PACTOR I operating mode (ARQ + FEC/Unproto).

PACTOR I is supported by PK-232MBX firmware v7.0 and later.

Key differences from Packet mode
---------------------------------
- Callsign is set via MYPTCALL (mnemonic MK), NOT via MYCALL (ML).
- PACTOR uses channel 0 only (single-channel ARQ protocol).
- ARQ data uses CTL $30 (RX_DATA ch0); FEC/Unproto uses $3F (RX_MONITOR).
- Direction change (ISS↔IRS) is via the PTOVER character (default Ctrl-Z).
- Huffman compression is controlled by PTHUFF (mnemonic PH).
- Auto speed selection 100/200 baud is controlled by PT200 (flag).

Host Mode frame types used (TRM Section 4.3 / 4.4)
----------------------------------------------------
  Incoming (TNC -> Host):
    $30  RX_DATA ch0   — ARQ received data (Mode A, connected)
    $3F  RX_MONITOR    — FEC/Unproto received data (Mode B, PTSEND)
    $5x  LINK_MSG      — CONNECTED, DISCONNECTED, busy, ...
    $5F  STATUS_ERR    — data ACK ($00) or error

  Outgoing (Host -> TNC):
    $4F  build_command(b'PT')             — enter PACTOR standby
    $4F  build_command(b'MK', callsign)   — set MYPTCALL
    $2x  build_data(0, data)              — send ARQ data on ch0

PACTOR-specific Host Mode mnemonics (STABO manual, Ch. 12)
----------------------------------------------------------
  PT   PACTOR mode (standby)
  MK   MYPTCALL — PACTOR callsign
  PH   PTHUFF   — Huffman compression (Y/N)
  PV   PTOVER   — direction-change character (hex, default $1A = Ctrl-Z)
  PD   PTSEND   — start unproto FEC transmission
  PN   PTLIST   — PACTOR listen/receive mode
  Pr   PTROUND  — round-table mode after PTSEND (Y/N)
  PT200 flag    — allow 200 baud (set via b'P2', Y/N in Host Mode)
  AC   ARQTMO   — ARQ timeout in seconds
  AQ   ARQTOL   — ARQ tolerance
  PU   PTUP     — upgrade threshold
  PW   PTDOWN   — downgrade threshold

TODO (v0.3):
    - Full ARQ connect/disconnect flow with state machine
    - Huffman-compressed data frame detection and pass-through
    - PTOVER / direction-change handling
    - PTSEND (FEC unproto) outgoing support
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Optional

from pk232py.comm.frame import build_command, build_data, FrameKind
from pk232py.modes.base_mode import BaseMode

if TYPE_CHECKING:
    from pk232py.comm.frame import HostFrame

logger = logging.getLogger(__name__)

# PTOVER default: Ctrl-Z ($1A) — direction change character
PTOVER_DEFAULT = 0x1A

# Link message substrings
_MSG_CONNECTED    = "connected"
_MSG_DISCONNECTED = "disconnected"
_MSG_BUSY         = "busy"
_MSG_CONNECT_REQ  = "connect request"
_MSG_RETRY        = "retry"
_MSG_LINK_OOO     = "link out of order"


class PACTORMode(BaseMode):
    """PACTOR I ARQ/FEC mode.

    Handles incoming Host Mode frames and builds outgoing command frames
    for the PACTOR I operating mode of the PK-232MBX.

    Important: set MYPTCALL before activating this mode, either via
    ``get_init_frames()`` (by setting ``myptcall`` on the instance) or
    by calling ``myptcall_frame()`` separately.

    Callbacks
    ---------
    ``on_data_received``  : ``Callable[[bytes], None]``
        Called with ARQ received data (channel 0, $30 frames).

    ``on_fec_received``   : ``Callable[[bytes], None]``
        Called with FEC/unproto received data ($3F frames, PTSEND/listen).

    ``on_link_message``   : ``Callable[[str], None]``
        Called with link state change text (CONNECTED, DISCONNECTED, …).

    ``on_data_ack``       : ``Callable[[], None]``
        Called when the TNC acknowledges a sent data block ($5F $00).
    """

    name            = "PACTOR"
    host_command    = b''              # kein Host Mode Mnemonic auf PK-232MBX v7.1
    verbose_command = b"PACTOR\r\n"   # Aktivierung nur im Verbose Mode

    def __init__(self, myptcall: str = "") -> None:
        """
        Args:
            myptcall: PACTOR callsign (MYPTCALL).  If set, it is included
                      in ``get_init_frames()``.  Can also be set later via
                      ``myptcall_frame()``.
        """
        super().__init__()
        self.myptcall = myptcall.upper()

        # Callbacks
        self.on_data_received: Optional[Callable[[bytes], None]] = None
        self.on_fec_received:  Optional[Callable[[bytes], None]] = None
        self.on_link_message:  Optional[Callable[[str],   None]] = None
        self.on_data_ack:      Optional[Callable[[],      None]] = None

    # ------------------------------------------------------------------
    # BaseMode interface
    # ------------------------------------------------------------------

    def get_activate_frames(self) -> list[bytes]:
        """PACTOR has no Host Mode mnemonic on PK-232MBX v7.1.
 
        Activation via verbose_command = b"PACTOR\\r\\n".
        ModeManager handles verbose activation separately.
        """
        return []

    def get_init_frames(self) -> list[bytes]:
        """Return parameter frames sent after PACTOR mode is confirmed.

        Includes MYPTCALL if set on the instance.
        """
        frames = []
        if self.myptcall:
            frames.append(self.myptcall_frame(self.myptcall))
        return frames

    def handle_frame(self, frame: "HostFrame") -> None:
        """Dispatch an incoming Host Mode frame to the appropriate handler.

        PACTOR frame types (TRM Section 4.3 / 4.4 / STABO Ch. 11):
          RX_DATA ($30)   — ARQ connected data from remote station
          RX_MONITOR ($3F)— FEC/Unproto data (PTSEND / PTLIST mode)
          LINK_MSG ($5x)  — CONNECTED, DISCONNECTED, busy, ...
          STATUS_ERR ($5F)— data ACK or error

        Args:
            frame: Decoded HostFrame from the TNC.
        """
        kind = frame.kind

        if kind == FrameKind.RX_DATA:
            # ARQ data: TRM Section 4.4.3 — "Mode A (ARQ), block type $30"
            self._handle_arq_data(frame)

        elif kind == FrameKind.RX_MONITOR:
            # FEC/Unproto: TRM Section 4.4.3 — "Mode B (FEC), block type $3F"
            self._handle_fec_data(frame)

        elif kind == FrameKind.LINK_MSG:
            self._handle_link_msg(frame)

        elif kind == FrameKind.STATUS_ERR:
            self._handle_status_err(frame)

        elif kind == FrameKind.CMD_RESP:
            # OPMODE response or parameter ACK — log only at this stage
            logger.debug("PACTOR CMD_RESP: %s", frame.data.hex())

        else:
            logger.debug("PACTOR: unhandled frame %r", frame)

    # ------------------------------------------------------------------
    # Outgoing command helpers
    # ------------------------------------------------------------------

    @staticmethod
    def myptcall_frame(callsign: str) -> bytes:
        """Build a MYPTCALL frame (mnemonic MK).

        PACTOR requires a separate callsign from MYCALL.
        STABO manual Ch. 12: Host mnemonic MK.

        Args:
            callsign: e.g. ``'OE3GAS'``.
        """
        return build_command(b'MK', callsign.upper().encode('ascii'))

    @staticmethod
    def pthuff_frame(enabled: bool) -> bytes:
        """Build a PTHUFF ON/OFF frame (mnemonic PH).

        Enable Huffman compression for text traffic.
        Disable for binary file transfers (7-bit data only).
        STABO Ch. 12: Host mnemonic PH.
        """
        return build_command(b'PH', b'Y' if enabled else b'N')

    @staticmethod
    def pt200_frame(enabled: bool) -> bytes:
        """Build a PT200 ON/OFF frame (mnemonic P2).

        Controls automatic 100/200 baud speed selection.
        STABO Ch. 12 / PACTOR Parameters dialog.
        """
        return build_command(b'P2', b'Y' if enabled else b'N')

    @staticmethod
    def ptround_frame(enabled: bool) -> bytes:
        """Build a PTROUND ON/OFF frame (mnemonic Pr).

        Controls behaviour after a PTSEND FEC transmission:
        ON  = return to PTLIST (listen) after transmission.
        OFF = return to PACTOR standby after transmission.
        """
        return build_command(b'Pr', b'Y' if enabled else b'N')

    @staticmethod
    def ptlist_frame() -> bytes:
        """Build a PTLIST frame — enter PACTOR listen/receive mode.

        Mnemonic PN.  Allows monitoring connected and unproto PACTOR traffic.
        """
        return build_command(b'PN')

    @staticmethod
    def arqtmo_frame(seconds: int) -> bytes:
        """Build an ARQTMO frame — set ARQ timeout (mnemonic AC).

        Args:
            seconds: Timeout 1-255 (default 60).
        """
        return build_command(b'AC', str(seconds).encode('ascii'))

    @staticmethod
    def data_frame(data: bytes) -> bytes:
        """Build a data frame to send on channel 0 (CTL = $20).

        PACTOR uses channel 0 only.  Wait for data-ACK before
        sending the next block (TRM Section 4.4).

        Args:
            data: Bytes to transmit (7-bit ASCII for Huffman-compressed
                  traffic; raw bytes otherwise).
        """
        return build_data(0, data)

    # ------------------------------------------------------------------
    # Private frame handlers
    # ------------------------------------------------------------------

    def _handle_arq_data(self, frame: "HostFrame") -> None:
        """Handle $30 — ARQ connected data from remote station."""
        logger.debug("PACTOR ARQ RX %d bytes", len(frame.data))
        if self.on_data_received:
            self.on_data_received(frame.data)

    def _handle_fec_data(self, frame: "HostFrame") -> None:
        """Handle $3F — FEC/Unproto data (PTSEND or PTLIST mode)."""
        logger.debug("PACTOR FEC RX %d bytes", len(frame.data))
        if self.on_fec_received:
            self.on_fec_received(frame.data)

    def _handle_link_msg(self, frame: "HostFrame") -> None:
        """Handle $5x — link messages (TRM Section 4.4.4)."""
        text  = frame.text.strip()
        lower = text.lower()

        if _MSG_CONNECTED in lower and _MSG_DISCONNECTED not in lower:
            logger.info("PACTOR: %s", text)
        elif _MSG_DISCONNECTED in lower:
            logger.info("PACTOR: %s", text)
        elif _MSG_CONNECT_REQ in lower:
            logger.info("PACTOR incoming: %s", text)
        elif _MSG_BUSY in lower:
            logger.info("PACTOR: %s", text)
        elif _MSG_RETRY in lower:
            logger.warning("PACTOR: %s", text)
        elif _MSG_LINK_OOO in lower:
            logger.error("PACTOR: %s", text)
        else:
            logger.debug("PACTOR link msg: %s", text)

        if self.on_link_message:
            self.on_link_message(text)

    def _handle_status_err(self, frame: "HostFrame") -> None:
        """Handle $5F — data ACK ($00) or status error."""
        if len(frame.data) >= 3 and frame.data[2] == 0x00:
            logger.debug("PACTOR data ACK")
            if self.on_data_ack:
                self.on_data_ack()
        else:
            logger.warning("PACTOR status error: %s", frame.data.hex())