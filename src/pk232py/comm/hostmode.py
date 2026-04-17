# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""AEA Host Mode protocol — high-level command layer.

This module provides the :class:`HostModeProtocol` class, which is the
primary interface for all Host Mode communication with the PK-232MBX.

Architecture
------------
The comm layer is split into three levels of abstraction:

  constants.py      Protocol magic numbers (SOH/ETB/CTL ranges/…)
  frame.py          Frame model (HostFrame), builder functions, FrameParser
  hostmode.py  ←    This file: high-level command API + init/poll logic

HostModeProtocol wraps a :class:`~frame.FrameParser` for incoming bytes
and delegates all frame building to the functions in :mod:`frame`.
It exposes:
  - Convenience command methods (cmd_host_on, cmd_mycall, …)
  - Initialisation sequence helper (init_sequence)
  - Poll frame / recovery frame access via constants

Usage example::

    from pk232py.comm.hostmode import HostModeProtocol
    from pk232py.comm.frame    import FrameKind

    def on_frame(frame):
        if frame.kind == FrameKind.LINK_MSG:
            print("Link:", frame.text)
        elif frame.is_ack:
            print("ACK:", frame.mnemonic)

    hm = HostModeProtocol(on_frame)

    # Feed raw bytes from serial port
    hm.feed(serial_port.read(256))

    # Build frames to send
    serial_port.write(hm.cmd_host_on())
    serial_port.write(hm.cmd_mycall('OE3GAS'))
    serial_port.write(hm.poll())
"""

from __future__ import annotations

import logging
from typing import Callable

from .constants import (
    FRAME_POLL,
    FRAME_RECOVERY,
    FRAME_HOST_OFF,
)
from .frame import (
    HostFrame,
    FrameKind,
    FrameParser,
    build_command,
    build_ch_cmd,
    build_data,
)

logger = logging.getLogger(__name__)


class HostModeProtocol:
    """High-level AEA Host Mode command interface.

    Wraps a :class:`~frame.FrameParser` for the incoming byte stream and
    provides named methods for every common outgoing command.  All frame
    building is delegated to :mod:`frame`; all protocol constants come
    from :mod:`constants`.

    Args:
        frame_callback: Called with each fully decoded :class:`~frame.HostFrame`
                        received from the TNC.

    Example::

        hm = HostModeProtocol(my_handler)
        serial.write(hm.cmd_host_on())
        serial.write(hm.cmd_hpoll_on())
        # … in read loop:
        hm.feed(serial.read(256))
    """

    def __init__(self, frame_callback: Callable[[HostFrame], None]) -> None:
        self._parser = FrameParser(frame_callback)

    # ------------------------------------------------------------------
    # Incoming data
    # ------------------------------------------------------------------

    def feed(self, data: bytes) -> None:
        """Feed raw bytes from the serial port into the frame parser.

        May be called with any chunk size.  Decoded frames are delivered
        to *frame_callback* synchronously during this call.

        Args:
            data: Raw bytes as received from the serial port.
        """
        self._parser.feed(data)

    def reset_parser(self) -> None:
        """Discard any partial frame state (call after a port reset)."""
        self._parser.reset()

    # ------------------------------------------------------------------
    # Special frames (ready-made bytes from constants)
    # ------------------------------------------------------------------

    @staticmethod
    def poll() -> bytes:
        """Return the HPOLL data-poll frame.

        Send this when HPOLL is ON to ask the TNC for any pending data.
        TRM Section 4.4.1:  SOH $4F 'G' 'G' ETB
        """
        return FRAME_POLL

    @staticmethod
    def recovery() -> bytes:
        """Return the Host Mode recovery / resync frame.

        Send after a serial link error.
        TRM Section 4.1.6:  SOH SOH $4F 'G' 'G' ETB
        """
        return FRAME_RECOVERY

    @staticmethod
    def host_off_frame() -> bytes:
        """Return the HOST OFF frame (leaves Host Mode).

        TRM Section 4.1.4:  SOH $4F 'H' 'O' 'N' ETB
        """
        return FRAME_HOST_OFF

    # ------------------------------------------------------------------
    # Generic frame builders (thin wrappers kept for backwards compat)
    # ------------------------------------------------------------------

    @staticmethod
    def build_command(mnemonic: bytes, args: bytes = b"") -> bytes:
        """Build a generic command frame (CTL = $4F).

        Delegates to :func:`frame.build_command`.
        """
        return build_command(mnemonic, args)

    @staticmethod
    def build_channel_command(channel: int, mnemonic: bytes,
                              args: bytes = b"") -> bytes:
        """Build a channel-specific command frame (CTL = $4x).

        Delegates to :func:`frame.build_ch_cmd`.
        """
        return build_ch_cmd(channel, mnemonic, args)

    @staticmethod
    def build_data(channel: int, data: bytes) -> bytes:
        """Build a data frame (CTL = $2x).

        Delegates to :func:`frame.build_data`.
        """
        return build_data(channel, data)

    # ------------------------------------------------------------------
    # Host Mode control
    # ------------------------------------------------------------------

    @staticmethod
    def cmd_host_on() -> bytes:
        """HOST ON — activate Host Mode (mnemonic HO, argument Y).

        TRM Section 4.1.3.
        """
        return build_command(b'HO', b'Y')

    @staticmethod
    def cmd_host_off() -> bytes:
        """HOST OFF — leave Host Mode, return to verbose/human mode.

        TRM Section 4.1.4.  Same wire bytes as FRAME_HOST_OFF.
        """
        return build_command(b'HO', b'N')

    @staticmethod
    def cmd_hpoll_on() -> bytes:
        """HPOLL ON — host must poll for data (mnemonic HP, argument Y)."""
        return build_command(b'HP', b'Y')

    @staticmethod
    def cmd_hpoll_off() -> bytes:
        """HPOLL OFF — TNC pushes data without waiting for poll."""
        return build_command(b'HP', b'N')

    # ------------------------------------------------------------------
    # TNC reset / mode queries
    # ------------------------------------------------------------------

    @staticmethod
    def cmd_restart() -> bytes:
        """RESTART — reset TNC and re-read firmware (mnemonic RT)."""
        return build_command(b'RT')

    @staticmethod
    def cmd_opmode() -> bytes:
        """OPMODE query — ask TNC for current operating mode (mnemonic OP).

        TRM Section 4.3.2.  TNC replies with e.g.:
          SOH $4F 'O' 'P' 'P' 'A' ETB  (Packet mode)
        """
        return build_command(b'OP')

    # ------------------------------------------------------------------
    # Station identification
    # ------------------------------------------------------------------

    @staticmethod
    def cmd_mycall(callsign: str) -> bytes:
        """MYCALL — set the station callsign (mnemonic ML).

        Args:
            callsign: e.g. ``'OE3GAS'`` or ``'OE3GAS-1'``.
        """
        return build_command(b'ML', callsign.upper().encode('ascii'))

    @staticmethod
    def cmd_myselcal(selcal: str) -> bytes:
        """MYSELCAL — set the 4-character AMTOR SELCAL (mnemonic MG).

        Args:
            selcal: Exactly 4 ASCII characters, e.g. ``'OGAS'``.
        """
        return build_command(b'MG', selcal.upper().encode('ascii'))

    @staticmethod
    def cmd_myptcall(callsign: str) -> bytes:
        """MYPTCALL — set the PACTOR callsign (mnemonic MK).

        Args:
            callsign: e.g. ``'OE3GAS'``.
        """
        return build_command(b'MK', callsign.upper().encode('ascii'))

    # ------------------------------------------------------------------
    # Operating modes
    # ------------------------------------------------------------------

    @staticmethod
    def cmd_packet() -> bytes:
        """PACKET — switch TNC to Packet / AX.25 mode (mnemonic PA)."""
        return build_command(b'PA')

    @staticmethod
    def cmd_pactor() -> bytes:
        """PACTOR — switch TNC to PACTOR I ARQ mode (mnemonic PT)."""
        return build_command(b'PT')

    @staticmethod
    def cmd_amtor() -> bytes:
        """AMTOR — switch TNC to AMTOR standby (mnemonic AM)."""
        return build_command(b'AM')

    @staticmethod
    def cmd_baudot() -> bytes:
        """BAUDOT — switch TNC to Baudot/RTTY mode (mnemonic BA)."""
        return build_command(b'BA')

    @staticmethod
    def cmd_ascii_rtty() -> bytes:
        """ASCII — switch TNC to ASCII RTTY mode (mnemonic AS)."""
        return build_command(b'AS')

    @staticmethod
    def cmd_morse() -> bytes:
        """MORSE — switch TNC to CW/Morse mode (mnemonic MO)."""
        return build_command(b'MO')

    @staticmethod
    def cmd_navtex() -> bytes:
        """NAVTEX — switch TNC to NAVTEX receive mode (mnemonic NE)."""
        return build_command(b'NE')

    # ------------------------------------------------------------------
    # Packet connect / disconnect
    # ------------------------------------------------------------------

    @staticmethod
    def cmd_connect(callsign: str, channel: int = 1) -> bytes:
        """CONNECT — initiate a Packet connection on *channel* (CTL = $4x).

        TRM Section 4.2.3.

        Args:
            callsign: Destination callsign, e.g. ``'OE3XYZ'``.
            channel:  AX.25 channel 1–9 (default 1).
        """
        return build_ch_cmd(channel, b'CO', callsign.upper().encode('ascii'))

    @staticmethod
    def cmd_disconnect(channel: int = 1) -> bytes:
        """DISCONNECT — terminate a Packet connection (CTL = $4x).

        TRM Section 4.2.3.
        """
        return build_ch_cmd(channel, b'DI')

    @staticmethod
    def cmd_link_status(channel: int = 1) -> bytes:
        """Query link state of *channel* (CTL = $4x + mnemonic CO).

        TRM Section 4.3.3.  TNC replies:
          SOH $4x 'C' 'O' a b c d e <path> ETB
        """
        return build_ch_cmd(channel, b'CO')

    # ------------------------------------------------------------------
    # Commonly used parameters
    # ------------------------------------------------------------------

    @staticmethod
    def cmd_mheard() -> bytes:
        """MHEARD — query list of heard stations (mnemonic MH)."""
        return build_command(b'MH')

    @staticmethod
    def cmd_unproto(path: str) -> bytes:
        """UNPROTO — set unproto destination / path (mnemonic UN).

        Args:
            path: e.g. ``'CQ'`` or ``'CQ VIA OE1XAB'``.
        """
        return build_command(b'UN', path.upper().encode('ascii'))

    @staticmethod
    def cmd_monitor(value: bool) -> bytes:
        """MONITOR ON/OFF — enable or disable frame monitor (mnemonic MN)."""
        return build_command(b'MN', b'Y' if value else b'N')

    @staticmethod
    def cmd_txdelay(value: int) -> bytes:
        """TXDELAY — set transmitter key-up delay in 10 ms units (mnemonic TD).

        Args:
            value: Integer 0–120 (e.g. 30 = 300 ms).
        """
        return build_command(b'TD', str(value).encode('ascii'))

    @staticmethod
    def cmd_send_data(channel: int, data: bytes) -> bytes:
        """Send data to the TNC for transmission on *channel* (CTL = $2x).

        TRM Section 4.4.  The host must wait for a data-ACK ($5F … $00)
        before sending the next block.

        Args:
            channel: Channel 0–9.  Use 0 for non-Packet modes.
            data:    Raw bytes to transmit.
        """
        return build_data(channel, data)

    # ------------------------------------------------------------------
    # Initialisation sequence helper
    # ------------------------------------------------------------------

    @staticmethod
    def init_sequence() -> list[bytes]:
        """Return the verbose-mode initialisation command list.

        These ASCII commands must be sent to the TNC BEFORE entering
        Host Mode (i.e. while still in terminal/verbose mode).
        Send each item followed by a short delay; wait for 'cmd:' between
        commands that trigger a RESTART.

        TRM Section 4.1.3.

        Returns:
            List of byte strings ready to write to the serial port.
        """
        from .constants import HOSTMODE_INIT_CMDS
        return list(HOSTMODE_INIT_CMDS)