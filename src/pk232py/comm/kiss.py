# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""KISS TNC protocol implementation (RFC 1055 / TAPR spec).

KISS is a simple framing protocol used to pass AX.25 frames between
a host computer and a TNC over a serial link.

Special bytes:
    FEND  = 0xC0  Frame End marker
    FESC  = 0xDB  Frame Escape
    TFEND = 0xDC  Transposed FEND
    TFESC = 0xDD  Transposed FESC

Frame format:
    FEND  TYPE  DATA  FEND

TYPE byte (first byte of frame):
    Bits 7-4: port number (0 for single-port TNC)
    Bits 3-0: command
        0x00 = Data frame
        0x01 = TX delay
        0x02 = Persistence
        0x03 = Slot time
        0x06 = Set hardware
        0xFF = Return from KISS mode

To enter KISS mode on PK-232MBX (firmware v7.x):
    Send: KISS ON  (in terminal mode)
To exit KISS mode:
    Send: FEND 0xFF FEND  (special exit sequence)
    Then: Ctrl-C Ctrl-C Ctrl-C
"""

from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)

FEND  = 0xC0
FESC  = 0xDB
TFEND = 0xDC
TFESC = 0xDD

CMD_DATA      = 0x00
CMD_TXDELAY   = 0x01
CMD_PERSIST   = 0x02
CMD_SLOTTIME  = 0x03
CMD_SETHW     = 0x06
CMD_EXIT_KISS = 0xFF

KISS_ON_CMD  = b"KISS ON\r"
KISS_EXIT    = bytes([FEND, CMD_EXIT_KISS, FEND])


def encode_frame(data: bytes, port: int = 0, command: int = CMD_DATA) -> bytes:
    """Encode a data frame in KISS format.

    Args:
        data: Raw AX.25 frame bytes.
        port: TNC port number (0 for single-port TNC).
        command: KISS command nibble (default 0 = data frame).

    Returns:
        KISS-encoded frame including FEND delimiters.
    """
    type_byte = ((port & 0x0F) << 4) | (command & 0x0F)
    payload = bytes([type_byte])
    for byte in data:
        if byte == FEND:
            payload += bytes([FESC, TFEND])
        elif byte == FESC:
            payload += bytes([FESC, TFESC])
        else:
            payload += bytes([byte])
    return bytes([FEND]) + payload + bytes([FEND])


def decode_frame(raw: bytes) -> bytes | None:
    """Decode a KISS frame, reversing byte stuffing.

    Args:
        raw: Raw bytes of a single KISS frame (without FEND delimiters).

    Returns:
        Decoded payload bytes, or ``None`` if the frame is malformed.
    """
    if len(raw) < 1:
        return None
    result = bytearray()
    escaped = False
    for byte in raw[1:]:  # skip type byte
        if escaped:
            if byte == TFEND:
                result.append(FEND)
            elif byte == TFESC:
                result.append(FESC)
            else:
                logger.warning("Invalid KISS escape sequence: 0x%02X", byte)
            escaped = False
        elif byte == FESC:
            escaped = True
        else:
            result.append(byte)
    return bytes(result)


class KISSProtocol:
    """Stateful KISS frame parser.

    Feed raw bytes from the serial port via ``feed()``.
    Complete decoded frames are passed to ``frame_callback``.

    Args:
        frame_callback: Called with decoded ``bytes`` for each complete frame.
    """

    def __init__(self, frame_callback: Callable[[bytes], None]) -> None:
        self._callback = frame_callback
        self._buf = bytearray()
        self._in_frame = False

    def feed(self, data: bytes) -> None:
        """Process raw incoming bytes from the serial port.

        Args:
            data: Raw bytes from the TNC in KISS mode.
        """
        for byte in data:
            if byte == FEND:
                if self._in_frame and len(self._buf) > 0:
                    decoded = decode_frame(bytes(self._buf))
                    if decoded is not None:
                        self._callback(decoded)
                    self._buf.clear()
                self._in_frame = True
            elif self._in_frame:
                self._buf.append(byte)
