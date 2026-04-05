# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""AEA Host Mode protocol implementation.

Frame format (AEA Technical Reference Manual, Chapter 4):

    SOH  LEN  CH  CMD  DATA...  ETB
    0x01  n   id  2B   n bytes  0x17

SOH = 0x01 (Start of Heading)
LEN = number of bytes following SOH up to and including ETB
CH  = channel/stream identifier (0x00 = control)
CMD = 2 ASCII bytes mnemonic (e.g. b'CO' for CONNECT)
ETB = 0x17 (End of Transmission Block)

Host polling sequence (HPOLL ON mode):
    Host → TNC:  SOH 0x4F H O N Ctrl-W  (request data)
    TNC  → Host: SOH LEN CH CMD DATA ETB (response)
"""

from __future__ import annotations

import logging
from enum import IntEnum
from typing import Callable, NamedTuple

logger = logging.getLogger(__name__)

# Frame delimiters
SOH = 0x01
ETB = 0x17

# Control channel
CTRL_CHANNEL = 0x00

# Polling frame: SOH 0x4F 'H' 'O' 'N' Ctrl-W
POLL_FRAME = bytes([SOH, 0x4F, ord('H'), ord('O'), ord('N'), 0x17])


class HostFrame(NamedTuple):
    """A decoded AEA Host Mode frame."""

    channel: int
    command: bytes     # 2-byte mnemonic, e.g. b'CO'
    data: bytes


class ParseState(IntEnum):
    IDLE = 0
    LENGTH = 1
    PAYLOAD = 2


class HostModeProtocol:
    """Parses and builds AEA Host Mode frames.

    This class is stateful — feed it raw bytes via ``feed()`` and it
    calls ``frame_callback`` for each complete frame received.

    Args:
        frame_callback: Called with a ``HostFrame`` for each decoded frame.
    """

    def __init__(self, frame_callback: Callable[[HostFrame], None]) -> None:
        self._frame_callback = frame_callback
        self._state = ParseState.IDLE
        self._expected_len = 0
        self._buf = bytearray()

    # ------------------------------------------------------------------
    # Incoming data
    # ------------------------------------------------------------------

    def feed(self, data: bytes) -> None:
        """Process raw bytes arriving from the serial port.

        Args:
            data: Raw bytes from the TNC.
        """
        for byte in data:
            self._process_byte(byte)

    def _process_byte(self, byte: int) -> None:
        if self._state == ParseState.IDLE:
            if byte == SOH:
                self._buf.clear()
                self._state = ParseState.LENGTH

        elif self._state == ParseState.LENGTH:
            self._expected_len = byte
            self._buf.clear()
            self._state = ParseState.PAYLOAD

        elif self._state == ParseState.PAYLOAD:
            self._buf.append(byte)
            if len(self._buf) == self._expected_len:
                self._decode_frame()
                self._state = ParseState.IDLE

    def _decode_frame(self) -> None:
        """Attempt to decode the buffered payload into a HostFrame."""
        payload = bytes(self._buf)
        # Minimum: channel(1) + cmd(2) + ETB(1) = 4 bytes
        if len(payload) < 4:
            logger.warning("Frame too short: %s", payload.hex())
            return
        if payload[-1] != ETB:
            logger.warning("Missing ETB in frame: %s", payload.hex())
            return

        channel = payload[0]
        command = payload[1:3]
        data = payload[3:-1]  # between CMD and ETB

        frame = HostFrame(channel=channel, command=command, data=data)
        logger.debug("RX frame ch=%02X cmd=%s data=%s", channel, command, data.hex())
        self._frame_callback(frame)

    # ------------------------------------------------------------------
    # Outgoing frames
    # ------------------------------------------------------------------

    @staticmethod
    def build_frame(channel: int, command: bytes, data: bytes = b"") -> bytes:
        """Build a Host Mode frame ready to send.

        Args:
            channel: Stream/channel number (0 = control).
            command: 2-byte ASCII mnemonic, e.g. ``b'CO'``.
            data: Optional data payload.

        Returns:
            Complete frame bytes including SOH and ETB.
        """
        if len(command) != 2:
            raise ValueError(f"Command must be exactly 2 bytes, got {len(command)}")
        payload = bytes([channel]) + command + data + bytes([ETB])
        length = len(payload)
        frame = bytes([SOH, length]) + payload
        logger.debug("TX frame ch=%02X cmd=%s data=%s", channel, command, data.hex())
        return frame

    @staticmethod
    def build_poll() -> bytes:
        """Return the standard Host Mode polling frame."""
        return POLL_FRAME

    # ------------------------------------------------------------------
    # Convenience frame builders for common commands
    # ------------------------------------------------------------------

    @staticmethod
    def cmd_host_on() -> bytes:
        """HOST ON — activate Host Mode."""
        return HostModeProtocol.build_frame(CTRL_CHANNEL, b'HO', b'\x01')

    @staticmethod
    def cmd_restart() -> bytes:
        """RESTART — reset TNC and re-read firmware version."""
        return HostModeProtocol.build_frame(CTRL_CHANNEL, b'RS')

    @staticmethod
    def cmd_mycall(callsign: str) -> bytes:
        """MYCALL — set the station callsign."""
        return HostModeProtocol.build_frame(
            CTRL_CHANNEL, b'ML', callsign.upper().encode('ascii')
        )

    @staticmethod
    def cmd_connect(callsign: str, channel: int = 1) -> bytes:
        """CONNECT — initiate a packet connection."""
        return HostModeProtocol.build_frame(
            channel, b'CO', callsign.upper().encode('ascii')
        )

    @staticmethod
    def cmd_disconnect(channel: int = 1) -> bytes:
        """DISCONNECT — terminate a packet connection."""
        return HostModeProtocol.build_frame(channel, b'DI')
