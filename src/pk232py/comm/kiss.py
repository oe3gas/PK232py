# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""KISS TNC protocol implementation for the AEA PK-232 / PK-232MBX.

The KISS ("Keep It Simple, Stupid") protocol was developed by Phil Karn KA9Q
and is specified in TRM Appendix B.  It is an ALTERNATIVE to Host Mode —
both cannot be active simultaneously.

KISS vs Host Mode
-----------------
  Host Mode   Full AEA protocol (SOH/CTL/ETB).  TNC handles AX.25.
              Supports all operating modes (Packet, PACTOR, AMTOR, …).
  KISS        Minimal framing (FEND/CTL).  Host handles ALL AX.25.
              Packet (AX.25) only.  Host must supply complete headers.

Use KISS when PK232PY is acting as a network interface (e.g. for APRS
clients, Winlink, or Linux ax25 stack via kissattach).  Use Host Mode
for the primary interactive terminal.

Wire format (TRM Appendix B, Section 2)
----------------------------------------
  FEND  TYPE  [data]  FEND
  $C0   1B    N bytes  $C0

  FEND = $C0  (frame delimiter — also sent as leading sync byte)
  TYPE = port nibble (high) | command nibble (low)
         port 0 = only port on single-TNC systems

Transparency / escaping (TRM Appendix B, Section 3)
----------------------------------------------------
  FEND ($C0) in data  →  FESC TFEND  ($DB $DC)
  FESC ($DB) in data  →  FESC TFESC  ($DB $DD)
  TFEND/TFESC not in escape sequence: pass through unchanged.

Commands (TRM Appendix B, Section 4)
--------------------------------------
  $00  DATA        AX.25 frame (with full header) to/from HDLC channel
  $01  TXDELAY     Tx keyup delay in 10 ms units  (default 50 = 500 ms)
  $02  PERSISTENCE p-persistence parameter 0-255  (default 63)
  $03  SLOTTIME    Slot interval in 10 ms units   (default 10 = 100 ms)
  $04  TXTAIL      Tx tail in 10 ms units          (deprecated, keep 0)
  $05  FULLDUP     $00 = half-duplex, $01 = full-duplex
  $FF  HOST_OFF    Exit KISS, return to verbose/Host Mode

PK-232MBX extended KISS modes (STABO manual, Chapter 12)
---------------------------------------------------------
  KISS $00  Standard KISS OFF
  KISS $01  Standard KISS  (= KISS ON)
  KISS $03  Extended KISS
  KISS $07  Extended KISS + KISS-Polling ($xE command)
  KISS $0B  Extended KISS + Checksum
  KISS $0F  Extended KISS + Polling + Checksum

  Extended commands (port nibble = x, must match KISSADDR):
    $xC  Send data with 2-byte frame-ID; TNC confirms with $xC reply
    $xE  Poll command (equivalent to Host Mode "GG")

Initialisation sequence (TRM Section 4.7.1, verbose mode)
----------------------------------------------------------
  AWLEN 8 / PARITY 0 / RESTART / CONMODE TRANS / TRACE OFF /
  HID OFF / BEACON EVERY 0 / PACKET / RAWHDLC ON / HPOLL OFF /
  PPERSIST ON / KISS ON / HOST ON
"""

from __future__ import annotations

import logging
from enum import IntEnum
from typing import Callable, NamedTuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocol constants
# ---------------------------------------------------------------------------

FEND  = 0xC0   # Frame End — delimits every frame (leading + trailing)
FESC  = 0xDB   # Frame Escape
TFEND = 0xDC   # Transposed Frame End
TFESC = 0xDD   # Transposed Frame Escape


# ---------------------------------------------------------------------------
# Command type codes (lower nibble of TYPE byte)
# ---------------------------------------------------------------------------

class KissCmd(IntEnum):
    """KISS command codes (lower nibble of the TYPE byte).

    The upper nibble is the port number (0 for single-port systems).
    """
    DATA        = 0x00  # AX.25 frame data
    TXDELAY     = 0x01  # Transmitter keyup delay (10 ms units)
    PERSISTENCE = 0x02  # p-persistence parameter (0-255)
    SLOTTIME    = 0x03  # Slot interval (10 ms units)
    TXTAIL      = 0x04  # Tx tail (deprecated)
    FULLDUP     = 0x05  # Full-duplex flag
    HOST_OFF    = 0xFF  # Exit KISS, return to verbose/Host Mode

    # PK-232MBX extended KISS (G8BPQ MultiDrop, STABO Ch. 12)
    EXT_DATA    = 0x0C  # Extended data with 2-byte frame-ID
    EXT_POLL    = 0x0E  # Extended poll (equivalent to Host Mode "GG")


# ---------------------------------------------------------------------------
# KISS mode values for the KISS parameter command (STABO Ch. 12)
# ---------------------------------------------------------------------------

class KissMode(IntEnum):
    """Values for the KISS parameter in verbose mode (0x00-0x0F)."""
    OFF                    = 0x00  # KISS disabled
    STANDARD               = 0x01  # Standard KISS (= KISS ON)
    EXTENDED               = 0x03  # Extended KISS
    EXTENDED_POLL          = 0x07  # Extended + Polling
    EXTENDED_CHECKSUM      = 0x0B  # Extended + Checksum
    EXTENDED_POLL_CHECKSUM = 0x0F  # Extended + Polling + Checksum


# ---------------------------------------------------------------------------
# Frame value object
# ---------------------------------------------------------------------------

class KissFrame(NamedTuple):
    """A decoded KISS frame.

    Attributes:
        port:    TNC port number (upper nibble of TYPE, 0 for single-port).
        cmd:     Command code (lower nibble of TYPE).
        data:    Payload bytes, already FESC-unescaped.
    """
    port: int
    cmd:  int
    data: bytes

    @property
    def is_data(self) -> bool:
        """True if this is a DATA frame (cmd == 0x00)."""
        return self.cmd == KissCmd.DATA

    @property
    def type_byte(self) -> int:
        """Reconstructed TYPE byte: (port << 4) | cmd."""
        return (self.port << 4) | (self.cmd & 0x0F)

    def __repr__(self) -> str:
        cmd_name = KissCmd(self.cmd).name if self.cmd in KissCmd._value2member_map_ else f"0x{self.cmd:02X}"
        return (
            f"KissFrame(port={self.port}, cmd={cmd_name}, "
            f"len={len(self.data)}, data={self.data[:16]!r}"
            f"{'...' if len(self.data) > 16 else ''})"
        )


# ---------------------------------------------------------------------------
# Escaping / unescaping
# ---------------------------------------------------------------------------

def _kiss_escape(data: bytes) -> bytes:
    """Replace FEND and FESC bytes with their two-byte escape sequences.

    TRM Appendix B, Section 3:
      FEND ($C0) → FESC TFEND ($DB $DC)
      FESC ($DB) → FESC TFESC ($DB $DD)
    """
    out = bytearray()
    for byte in data:
        if byte == FEND:
            out.append(FESC)
            out.append(TFEND)
        elif byte == FESC:
            out.append(FESC)
            out.append(TFESC)
        else:
            out.append(byte)
    return bytes(out)


def _kiss_unescape(data: bytes) -> bytes:
    """Reverse KISS escape sequences in *data*.

    FESC TFEND → FEND
    FESC TFESC → FESC
    Any other byte following FESC: error — skip FESC, keep byte (TRM B §3).
    TFEND / TFESC not in escape context: keep unchanged (TRM B §3).
    """
    out     = bytearray()
    escaped = False
    for byte in data:
        if escaped:
            if byte == TFEND:
                out.append(FEND)
            elif byte == TFESC:
                out.append(FESC)
            else:
                # Invalid escape sequence — keep the byte (TRM: no action,
                # frame assembly continues)
                logger.warning(
                    "KISS: invalid escape sequence FESC 0x%02X — keeping byte",
                    byte
                )
                out.append(byte)
            escaped = False
        elif byte == FESC:
            escaped = True
        else:
            out.append(byte)
    return bytes(out)


# ---------------------------------------------------------------------------
# Frame builders
# ---------------------------------------------------------------------------

def build_frame(port: int, cmd: int, data: bytes = b"") -> bytes:
    """Build a KISS frame ready to send.

    Args:
        port: TNC port number 0-15 (0 for single-port PK-232MBX).
        cmd:  Command code (KissCmd value or raw int).
              HOST_OFF ($FF) is a special case: the full TYPE byte is $FF
              regardless of port (TRM Section 4.7.4.6).
        data: Payload bytes.  FESC-escaping is applied automatically.

    Returns:
        Complete KISS frame: FEND TYPE <escaped data> FEND

    Raises:
        ValueError: If port or cmd is out of range.
    """
    if not 0 <= port <= 15:
        raise ValueError(f"KISS port must be 0-15, got {port}")
    if not 0 <= cmd <= 0xFF:
        raise ValueError(f"KISS cmd must be 0x00-0xFF, got {cmd:#04x}")
    # HOST_OFF uses the full byte $FF as TYPE (TRM Section 4.7.4.6)
    if cmd == KissCmd.HOST_OFF:
        type_byte = 0xFF
    else:
        type_byte = (port << 4) | (cmd & 0x0F)
    return bytes([FEND, type_byte]) + _kiss_escape(data) + bytes([FEND])


def build_data(data: bytes, port: int = 0) -> bytes:
    """Build a KISS DATA frame (TYPE = $00).

    The caller must supply the complete AX.25 frame including all headers.
    TRM Appendix B, Section 4.7.4.7.

    Args:
        data: Complete AX.25 frame bytes (without HDLC flags or FCS).
        port: TNC port (default 0).
    """
    return build_frame(port, KissCmd.DATA, data)


def build_txdelay(value: int, port: int = 0) -> bytes:
    """Build a TXDELAY command frame.

    Args:
        value: Delay in 10 ms units (0-255).  Default TNC value: 50 (500 ms).
        port:  TNC port (default 0).
    """
    if not 0 <= value <= 255:
        raise ValueError(f"TXDELAY must be 0-255, got {value}")
    return build_frame(port, KissCmd.TXDELAY, bytes([value]))


def build_persistence(value: int, port: int = 0) -> bytes:
    """Build a PERSISTENCE (p) command frame.

    Args:
        value: p-persistence 0-255.  Default: 63 (p ≈ 0.25).
               Formula: P = p × 256 - 1.
        port:  TNC port (default 0).
    """
    if not 0 <= value <= 255:
        raise ValueError(f"Persistence must be 0-255, got {value}")
    return build_frame(port, KissCmd.PERSISTENCE, bytes([value]))


def build_slottime(value: int, port: int = 0) -> bytes:
    """Build a SLOTTIME command frame.

    Args:
        value: Slot interval in 10 ms units (0-255).  Default: 10 (100 ms).
        port:  TNC port (default 0).
    """
    if not 0 <= value <= 255:
        raise ValueError(f"SlotTime must be 0-255, got {value}")
    return build_frame(port, KissCmd.SLOTTIME, bytes([value]))


def build_txtail(value: int, port: int = 0) -> bytes:
    """Build a TXTAIL command frame (deprecated, use 0).

    Args:
        value: Tx tail in 10 ms units.
        port:  TNC port (default 0).
    """
    return build_frame(port, KissCmd.TXTAIL, bytes([value]))


def build_fulldup(enabled: bool, port: int = 0) -> bytes:
    """Build a FULLDUP command frame.

    Args:
        enabled: True = full-duplex, False = half-duplex (default).
        port:    TNC port (default 0).
    """
    return build_frame(port, KissCmd.FULLDUP, bytes([0x01 if enabled else 0x00]))


def build_host_off(port: int = 0) -> bytes:
    """Build a HOST OFF frame — exits KISS and returns to verbose/Host Mode.

    TRM Section 4.7.4.6:  FEND $FF FEND
    """
    return build_frame(port, KissCmd.HOST_OFF)


# ---------------------------------------------------------------------------
# Initialisation sequence
# ---------------------------------------------------------------------------

KISS_INIT_CMDS: list[bytes] = [
    b"AWLEN 8\r",
    b"PARITY 0\r",
    b"RESTART\r",        # apply AWLEN/PARITY
    b"CONMODE TRANS\r",
    b"TRACE OFF\r",
    b"HID OFF\r",
    b"BEACON EVERY 0\r",
    b"PACKET\r",
    b"RAWHDLC ON\r",
    b"HPOLL OFF\r",
    b"PPERSIST ON\r",
    b"KISS ON\r",        # standard KISS ($01)
    b"HOST ON\r",
]
"""Verbose-mode commands to enter standard KISS mode.

Send each line to the TNC while in terminal/verbose mode.
Wait for 'cmd:' prompt between commands that trigger a RESTART.
TRM Section 4.7.1.
"""


# ---------------------------------------------------------------------------
# Stateful frame parser
# ---------------------------------------------------------------------------

class _ParseState(IntEnum):
    IDLE    = 0   # waiting for leading FEND
    TYPE    = 1   # next byte is TYPE
    PAYLOAD = 2   # accumulating payload until trailing FEND


class KissParser:
    """Stateful, byte-by-byte parser for the KISS byte stream.

    Feed raw bytes from the serial port via :meth:`feed`.  For each
    complete, unescaped KISS frame the *frame_callback* is called with
    a :class:`KissFrame`.

    The parser handles:
      - FESC unescaping of FEND and FESC in the payload.
      - Back-to-back FEND characters (treated as empty frame → discarded).
      - Invalid escape sequences (logged, byte kept, assembly continues).

    Args:
        frame_callback: Called with each decoded :class:`KissFrame`.

    Example::

        frames = []
        parser = KissParser(frames.append)
        parser.feed(bytes_from_serial_port)
        for frame in frames:
            if frame.is_data:
                handle_ax25(frame.data)
    """

    def __init__(self, frame_callback: Callable[[KissFrame], None]) -> None:
        self._cb      = frame_callback
        self._state   = _ParseState.IDLE
        self._type    = 0
        self._buf     = bytearray()   # raw (still escaped) payload bytes
        self._escaped = False

    def feed(self, data: bytes) -> None:
        """Process raw bytes from the serial port.

        Args:
            data: Raw bytes as received from the serial port.
        """
        for byte in data:
            self._step(byte)

    def reset(self) -> None:
        """Discard any partial frame state."""
        self._state   = _ParseState.IDLE
        self._type    = 0
        self._buf.clear()
        self._escaped = False
        logger.debug("KissParser reset")

    def _step(self, byte: int) -> None:

        # ---- PAYLOAD: accumulate until FEND, handle FESC ---------------
        if self._state == _ParseState.PAYLOAD:
            if self._escaped:
                if byte == TFEND:
                    self._buf.append(FEND)
                elif byte == TFESC:
                    self._buf.append(FESC)
                else:
                    logger.warning(
                        "KissParser: invalid escape FESC 0x%02X — keeping byte",
                        byte
                    )
                    self._buf.append(byte)
                self._escaped = False
                return
            if byte == FESC:
                self._escaped = True
                return
            if byte == FEND:
                # Trailing FEND — frame complete
                self._emit()
                self._state = _ParseState.IDLE
                return
            self._buf.append(byte)
            return

        # ---- IDLE: wait for leading FEND --------------------------------
        if self._state == _ParseState.IDLE:
            if byte == FEND:
                self._buf.clear()
                self._escaped = False
                self._state   = _ParseState.TYPE

        # ---- TYPE: one byte after leading FEND --------------------------
        elif self._state == _ParseState.TYPE:
            if byte == FEND:
                # Back-to-back FENDs: empty frame — stay in TYPE
                # (TRM B §2: "two FENDs in a row should not be interpreted
                # as delimiting an empty frame")
                logger.debug("KissParser: back-to-back FEND (ignored)")
            else:
                self._type  = byte
                self._buf.clear()
                self._state = _ParseState.PAYLOAD

    def _emit(self) -> None:
        """Construct and fire the callback with the decoded frame."""
        port = (self._type >> 4) & 0x0F
        cmd  = self._type & 0x0F
        # Handle HOST_OFF ($FF type byte) — lower nibble = 0xF
        if self._type == 0xFF:
            cmd = KissCmd.HOST_OFF

        data  = bytes(self._buf)
        frame = KissFrame(port=port, cmd=cmd, data=data)
        logger.debug("RX %r", frame)
        self._cb(frame)
        self._buf.clear()