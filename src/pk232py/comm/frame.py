# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""AEA Host Mode frame model and builder/parser.

This module provides:

  HostFrame       — immutable value object representing one decoded frame.
  FrameKind       — classification of an incoming frame by its CTL range.
  build_command() — build an outgoing command frame  (CTL = $4F).
  build_ch_cmd()  — build a channel command frame    (CTL = $4x).
  build_data()    — build an outgoing data frame      (CTL = $2x).
  FrameParser     — stateful byte-stream parser; emits HostFrames.

Relationship to other modules
------------------------------
  constants.py  — all protocol magic numbers (SOH, ETB, CTL_* ranges, …)
  hostmode.py   — higher-level protocol logic (init sequence, polling loop)
  serial_.py    — (future) asyncio serial transport

Frame wire format (TRM Chapter 4)
-----------------------------------
  SOH  CTL  [data bytes]  ETB
  0x01  1B   0-N bytes    0x17

DLE escaping (TRM Section 4.1.5)
---------------------------------
  Any occurrence of SOH, DLE or ETB inside the data field is preceded by
  a DLE byte.  This applies in BOTH directions.  The FrameParser strips
  DLE prefixes automatically; build_*() functions insert them.
"""

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Callable, NamedTuple

from .constants import (
    SOH, ETB, DLE, ESCAPE_CHARS,
    CTL_TX_DATA_BASE, CTL_TX_CMD_CH_BASE, CTL_TX_CMD,
    CTL_RX_ECHO, CTL_RX_DATA_BASE, CTL_RX_MONITOR,
    CTL_RX_LINK_BASE, CTL_RX_CMD_RESP, CTL_RX_MSG_BASE, CTL_RX_STATUS,
    CmdError, MAX_DATA_LEN,
    ctl_channel, ctl_type_range,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Frame classification
# ---------------------------------------------------------------------------

class FrameKind(Enum):
    """Classification of an incoming (TNC -> Host) frame by CTL range.

    Use HostFrame.kind to dispatch on frame type instead of comparing raw
    CTL bytes directly.
    """
    # TNC -> Host
    ECHO        = auto()  # $2F  echoed TX chars (Morse/Baudot/AMTOR)
    RX_DATA     = auto()  # $3x  received channel data
    RX_MONITOR  = auto()  # $3F  monitored / unproto frames
    LINK_STATUS = auto()  # $4x  link status (response to CONNECT query)
    CMD_RESP    = auto()  # $4F  command response (ACK/NAK/query reply)
    LINK_MSG    = auto()  # $5x  link messages (CONNECTED, DISCONNECTED …)
    STATUS_ERR  = auto()  # $5F  status errors / data acknowledgement
    UNKNOWN     = auto()  # anything else (should not occur with a healthy TNC)


def _classify(ctl: int) -> FrameKind:
    """Map a raw CTL byte to a FrameKind."""
    if ctl == CTL_RX_ECHO:
        return FrameKind.ECHO
    if ctl == CTL_RX_MONITOR:
        return FrameKind.RX_MONITOR
    if ctl == CTL_RX_CMD_RESP:
        return FrameKind.CMD_RESP
    if ctl == CTL_RX_STATUS:
        return FrameKind.STATUS_ERR
    r = ctl_type_range(ctl)
    if r == CTL_RX_DATA_BASE:
        return FrameKind.RX_DATA
    if r == CTL_RX_LINK_BASE:
        return FrameKind.LINK_STATUS
    if r == CTL_RX_MSG_BASE:
        return FrameKind.LINK_MSG
    return FrameKind.UNKNOWN


# ---------------------------------------------------------------------------
# Frame value object
# ---------------------------------------------------------------------------

class HostFrame(NamedTuple):
    """An immutable, decoded AEA Host Mode frame.

    Attributes:
        ctl:     Raw CTL byte as received from the TNC.
        channel: Logical channel 0-9 (lower nibble of CTL).
                 Meaningful only for RX_DATA, LINK_STATUS, LINK_MSG frames.
                 For CMD_RESP, ECHO, RX_MONITOR, STATUS_ERR this is 0xF or
                 0x0 and should be ignored.
        data:    Payload bytes, already DLE-unescaped, without the trailing
                 ETB.
        kind:    FrameKind classification derived from CTL.

    Convenience properties
    ----------------------
    .mnemonic   — first 2 bytes of data as bytes (CMD_RESP frames).
    .cmd_error  — third data byte as int (CMD_RESP frames), or None.
    .is_ack     — True if CMD_RESP with error code 0x00.
    .is_poll_ok — True if CMD_RESP 'GG' with code 0x00 (nothing pending).
    .text       — data decoded as ASCII (best-effort, errors='replace').
    """
    ctl:     int
    channel: int
    data:    bytes
    kind:    FrameKind

    # -- CMD_RESP helpers ---------------------------------------------------

    @property
    def mnemonic(self) -> bytes:
        """First 2 payload bytes (the command mnemonic echo in CMD_RESP)."""
        return self.data[:2]

    @property
    def cmd_error(self) -> int | None:
        """Third payload byte as error code, or None if data is too short."""
        if len(self.data) >= 3:
            return self.data[2]
        return None

    @property
    def is_ack(self) -> bool:
        """True if this is a successful command acknowledgement ($4F … $00)."""
        return (
            self.kind == FrameKind.CMD_RESP
            and len(self.data) >= 3
            and self.data[2] == CmdError.OK
        )

    @property
    def is_poll_ok(self) -> bool:
        """True if TNC replied 'nothing pending' to a GG poll."""
        return (
            self.kind == FrameKind.CMD_RESP
            and self.mnemonic == b'GG'
            and self.cmd_error == CmdError.OK
        )

    # -- Data helpers -------------------------------------------------------

    @property
    def text(self) -> str:
        """Payload decoded as ASCII (replacement char for invalid bytes)."""
        return self.data.decode('ascii', errors='replace')

    # -- Factory ------------------------------------------------------------

    @classmethod
    def from_raw(cls, ctl: int, data: bytes) -> "HostFrame":
        """Construct a HostFrame from a raw CTL byte and unescaped payload.

        Args:
            ctl:  Raw CTL byte.
            data: Already DLE-unescaped payload (no trailing ETB).
        """
        return cls(
            ctl=ctl,
            channel=ctl_channel(ctl),
            data=data,
            kind=_classify(ctl),
        )

    def __repr__(self) -> str:
        return (
            f"HostFrame(kind={self.kind.name}, ctl=0x{self.ctl:02X}, "
            f"ch={self.channel}, data={self.data!r})"
        )


# ---------------------------------------------------------------------------
# DLE escaping / unescaping
# ---------------------------------------------------------------------------

def _dle_escape(data: bytes) -> bytes:
    """Insert a DLE byte before every SOH, DLE or ETB in *data*.

    Required by TRM Section 4.1.5 for all outgoing data fields.
    """
    out = bytearray()
    for byte in data:
        if byte in ESCAPE_CHARS:
            out.append(DLE)
        out.append(byte)
    return bytes(out)


def _dle_unescape(data: bytes) -> bytes:
    """Remove DLE prefix bytes from *data* (inverse of _dle_escape).

    Used by FrameParser after collecting raw payload bytes.
    """
    out  = bytearray()
    skip = False
    for byte in data:
        if skip:
            out.append(byte)
            skip = False
        elif byte == DLE:
            skip = True
        else:
            out.append(byte)
    return bytes(out)


# ---------------------------------------------------------------------------
# Outgoing frame builders
# ---------------------------------------------------------------------------

def build_command(mnemonic: bytes, args: bytes = b"") -> bytes:
    """Build a Host Mode command frame  (CTL = $4F).

    This is the standard form for ALL parameter/control commands
    (TRM Section 4.2):  SOH $4F <2-byte mnemonic> <args> ETB

    Args:
        mnemonic: Exactly 2 ASCII bytes, e.g. ``b'HO'``.
        args:     Optional argument bytes (ASCII).  No leading space.
                  On/Off: b'Y' or b'N'.  Numbers: ASCII digits.

    Returns:
        Complete frame bytes including SOH and ETB.

    Raises:
        ValueError: If mnemonic is not exactly 2 bytes.

    Examples:
        >>> build_command(b'HO', b'Y')          # HOST ON
        b'\\x01\\x4fHOY\\x17'
        >>> build_command(b'ML', b'OE3GAS')     # MYCALL OE3GAS
        >>> build_command(b'GG')                # poll
    """
    if len(mnemonic) != 2:
        raise ValueError(
            f"Host Mode mnemonic must be exactly 2 bytes, got {len(mnemonic)!r}"
        )
    payload = mnemonic + _dle_escape(args)
    return bytes([SOH, CTL_TX_CMD]) + payload + bytes([ETB])


def build_ch_cmd(channel: int, mnemonic: bytes, args: bytes = b"") -> bytes:
    """Build a channel-specific command frame  (CTL = $4x).

    Used for CONNECT and DISCONNECT (TRM Section 4.2.3).

    Args:
        channel:  Packet channel 0-9.
        mnemonic: Exactly 2 ASCII bytes.
        args:     Optional argument bytes.

    Returns:
        Complete frame bytes.

    Raises:
        ValueError: If channel is out of range or mnemonic wrong length.
    """
    if not 0 <= channel <= 9:
        raise ValueError(f"Channel must be 0-9, got {channel}")
    if len(mnemonic) != 2:
        raise ValueError(
            f"Host Mode mnemonic must be exactly 2 bytes, got {len(mnemonic)!r}"
        )
    ctl     = CTL_TX_CMD_CH_BASE | channel
    payload = mnemonic + _dle_escape(args)
    return bytes([SOH, ctl]) + payload + bytes([ETB])


def build_data(channel: int, data: bytes) -> bytes:
    """Build an outgoing data frame  (CTL = $2x).

    Sends user data to the TNC for transmission on *channel*
    (TRM Section 4.4):  SOH $2x <data> ETB

    Args:
        channel: Channel 0-9.  Use 0 for all non-Packet modes.
        data:    Raw data bytes.  DLE-escaping is applied automatically.

    Returns:
        Complete frame bytes.

    Raises:
        ValueError: If channel is out of range or data exceeds MAX_DATA_LEN.
    """
    if not 0 <= channel <= 9:
        raise ValueError(f"Channel must be 0-9, got {channel}")
    if len(data) > MAX_DATA_LEN:
        raise ValueError(
            f"Data length {len(data)} exceeds MAX_DATA_LEN {MAX_DATA_LEN}"
        )
    ctl = CTL_TX_DATA_BASE | channel
    return bytes([SOH, ctl]) + _dle_escape(data) + bytes([ETB])


# ---------------------------------------------------------------------------
# Stateful frame parser
# ---------------------------------------------------------------------------

class _ParseState(Enum):
    IDLE    = auto()   # waiting for SOH
    CTL     = auto()   # next byte is CTL
    PAYLOAD = auto()   # accumulating payload until ETB (with DLE awareness)


class FrameParser:
    """Stateful, byte-by-byte parser for the AEA Host Mode byte stream.

    Feed raw bytes from the serial port via :meth:`feed`.  For each
    complete, valid frame the *frame_callback* is called with a
    :class:`HostFrame`.

    The parser handles:
      - DLE unescaping of SOH, DLE, ETB in the payload.
      - Unexpected-SOH resync (discards partial frame, logs warning).
      - Double-SOH recovery frames from the TNC (logged, not emitted).

    Args:
        frame_callback: Called with each fully decoded :class:`HostFrame`.

    Example::

        frames = []
        parser = FrameParser(frames.append)
        parser.feed(bytes_from_serial_port)
        for frame in frames:
            handle(frame)
    """

    def __init__(self, frame_callback: Callable[[HostFrame], None]) -> None:
        self._cb      = frame_callback
        self._state   = _ParseState.IDLE
        self._ctl     = 0
        self._buf     = bytearray()   # raw bytes incl. DLE prefixes
        self._escaped = False         # True when last byte was DLE

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def feed(self, data: bytes) -> None:
        """Process raw bytes from the serial port.

        May be called with any chunk size (single bytes or large buffers).

        Args:
            data: Raw bytes as received from the serial port.
        """
        for byte in data:
            self._step(byte)

    def reset(self) -> None:
        """Discard any partial frame state (e.g. after a port reset)."""
        self._state   = _ParseState.IDLE
        self._ctl     = 0
        self._buf.clear()
        self._escaped = False
        logger.debug("FrameParser reset")

    # ------------------------------------------------------------------
    # Internal state machine
    # ------------------------------------------------------------------

    def _step(self, byte: int) -> None:

        # ---- PAYLOAD: DLE-aware accumulation until ETB -----------------
        if self._state == _ParseState.PAYLOAD:
            if self._escaped:
                # Literal byte following a DLE — always accumulate.
                self._buf.append(byte)
                self._escaped = False
                return
            if byte == DLE:
                self._escaped = True
                return                      # consume DLE, don't store it
            if byte == ETB:
                self._emit()
                self._state = _ParseState.IDLE
                return
            if byte == SOH:
                # Unexpected SOH mid-payload → resync
                logger.warning(
                    "FrameParser: unexpected SOH inside payload "
                    "(ctl=0x%02X, %d bytes buffered) — resyncing",
                    self._ctl, len(self._buf)
                )
                self._buf.clear()
                self._escaped = False
                self._state   = _ParseState.CTL
                return
            self._buf.append(byte)
            return

        # ---- IDLE: wait for SOH ----------------------------------------
        if self._state == _ParseState.IDLE:
            if byte == SOH:
                self._buf.clear()
                self._escaped = False
                self._state   = _ParseState.CTL

        # ---- CTL: one-byte header after SOH ----------------------------
        elif self._state == _ParseState.CTL:
            if byte == SOH:
                # Double-SOH: TRM Section 4.1.6 recovery frame.
                # The TNC (or host) sent this to resync.  Stay in CTL
                # and wait for the real CTL byte.
                logger.debug("FrameParser: double-SOH (recovery/resync) received")
            else:
                self._ctl   = byte
                self._buf.clear()
                self._state = _ParseState.PAYLOAD

    def _emit(self) -> None:
        """Unescape buffered payload and fire the callback."""
        raw_payload = bytes(self._buf)
        data        = _dle_unescape(raw_payload)
        frame       = HostFrame.from_raw(self._ctl, data)
        logger.debug(
            "RX %r  raw_payload=%s",
            frame, raw_payload.hex()
        )
        self._cb(frame)
        self._buf.clear()