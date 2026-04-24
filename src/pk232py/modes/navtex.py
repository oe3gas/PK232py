# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""NAVTEX receive mode (518 kHz, AMTOR Mode B / SITOR).

NAVTEX (NAVigational TEleX) is an international system for broadcasting
navigational and meteorological warnings to ships at sea, operating on
518 kHz using AMTOR Mode B (FEC/SITOR).

In amateur radio the same mode is called AMTEX and is used by ARRL
for information broadcasts.

Key characteristics
-------------------
- Receive only (no transmit in NAVTEX mode)
- 518 kHz standard frequency (100 Hz shift, 100 baud)
- AMTOR Mode B (FEC) framing: SOH/ETX/ZCZC markers
- Message format: ZCZC + 4-char header (station ID + msg class + serial)
- Duplicate suppression: TNC remembers last 200 message headers
- Selective receive via NAVMSG (message class) and NAVSTN (station ID)
- Message classes A, B, D are mandatory (cannot be suppressed)

Host Mode frame types (TRM Section 4.4.3)
------------------------------------------
  Incoming:
    $3F  RX_MONITOR  — NAVTEX message text (FEC/Mode B data)
    $5F  STATUS_ERR  — error

  Outgoing:
    $4F  build_command(b'NE')              — enter NAVTEX mode (mnemonic NE)
    $4F  build_command(b'NM', filter)      — NAVMSG filter
    $4F  build_command(b'NS', filter)      — NAVSTN filter

Host Mode mnemonics (TRM / STABO manual)
-----------------------------------------
  NE   NEWMODE / NAVTEX — enter NAVTEX receive mode (mnemonic NE per TRM)
  NA   NAVTEX           — also documented as direct command (mnemonic NA)
  NM   NAVMSG          — message class filter (ALL / NONE / YES list / NO list)
  NS   NAVSTN           — station ID filter   (ALL / NONE / YES list / NO list)

Note: Both NA and NE appear in the TRM mnemonic list.
  NA = NAVTEX (direct command)
  NE = NEWMODE (ON/OFF) — but also used as NAVTEX activate in some firmware
The STABO manual uses NAVTEX as the command name (Host: NA).
We use b'NA' as the primary activate mnemonic per the mnemonic table.

NAVTEX message classes (STABO manual Ch. 7):
  A  Navigational warnings        (mandatory)
  B  Meteorological warnings      (mandatory)
  C  Ice warnings
  D  Search and rescue info       (mandatory)
  E  Weather forecasts
  F  Pilot service messages
  G  DECCA system info
  H  LORAN-C info
  I  Omega system messages
  J  SATNAV messages
  K-Z Reserved for future use
"""

from __future__ import annotations

import logging
from typing import Callable, Optional, TYPE_CHECKING

from pk232py.comm.frame import build_command, FrameKind
from pk232py.modes.base_mode import BaseMode

if TYPE_CHECKING:
    from pk232py.comm.frame import HostFrame

logger = logging.getLogger(__name__)

# Mandatory message classes — cannot be suppressed per NAVTEX spec
MANDATORY_CLASSES = frozenset("ABD")

# NAVMSG / NAVSTN filter argument constants
FILTER_ALL  = b'ALL'
FILTER_NONE = b'NONE'


class NAVTEXMode(BaseMode):
    """NAVTEX receive mode (518 kHz, AMTOR Mode B / FEC).

    Receive-only mode — NAVTEX has no transmit capability.
    The TNC delivers decoded NAVTEX messages as RX_MONITOR ($3F) frames.

    Filtering
    ---------
    ``navmsg``:  Message class filter string passed to NAVMSG command.
                 ``"ALL"`` (default), ``"NONE"``, or letter list e.g. ``"A,B,E"``.
    ``navstn``:  Station ID filter string passed to NAVSTN command.
                 ``"ALL"`` (default), ``"NONE"``, or letter list e.g. ``"A,P"``.

    Note: Classes A, B and D are mandatory and will always be shown
    regardless of the NAVMSG setting (enforced by TNC firmware).

    Callbacks
    ---------
    ``on_message_received``  : ``Callable[[bytes], None]``
        Called with each received NAVTEX message ($3F frames).
        Messages start with ZCZC followed by the 4-char header.
    """

    name         = "NAVTEX"
    host_command = b'NA'    # NAVTEX direct command per TRM mnemonic table
    verbose_command = b"NAVTEX\r\n"

    def __init__(
        self,
        navmsg: str = "ALL",   # message class filter
        navstn: str = "ALL",   # station ID filter
    ) -> None:
        super().__init__()
        self.navmsg = navmsg.upper()
        self.navstn = navstn.upper()

        # Callbacks
        self.on_message_received: Optional[Callable[[bytes], None]] = None

    # ------------------------------------------------------------------
    # BaseMode interface
    # ------------------------------------------------------------------

    def get_activate_frames(self) -> list[bytes]:
        """Return the frame to switch TNC to NAVTEX receive (mnemonic NA)."""
        return [build_command(b'NA')]

    def get_init_frames(self) -> list[bytes]:
        """Return NAVMSG and NAVSTN filter frames."""
        return [
            self.navmsg_frame(self.navmsg),
            self.navstn_frame(self.navstn),
        ]

    def handle_frame(self, frame: "HostFrame") -> None:
        """Dispatch an incoming Host Mode frame for NAVTEX mode.

        NAVTEX uses FEC (Mode B) framing — all received data arrives
        as RX_MONITOR ($3F) frames, identical to AMTOR FEC.

        Args:
            frame: Decoded HostFrame from the TNC.
        """
        kind = frame.kind

        if kind == FrameKind.RX_MONITOR:
            logger.debug("NAVTEX RX %d bytes", len(frame.data))
            if self.on_message_received:
                self.on_message_received(frame.data)

        elif kind == FrameKind.CMD_RESP:
            logger.debug("NAVTEX CMD_RESP: %s", frame.data.hex())

        elif kind == FrameKind.STATUS_ERR:
            logger.warning("NAVTEX status error: %s", frame.data.hex())

        else:
            logger.debug("NAVTEX: unhandled frame %r", frame)

    # ------------------------------------------------------------------
    # Parameter frame builders
    # ------------------------------------------------------------------

    @staticmethod
    def navmsg_frame(filter_str: str) -> bytes:
        """NAVMSG — set message class filter (mnemonic NM).

        Args:
            filter_str: ``"ALL"``, ``"NONE"``, or comma-separated class
                        letters e.g. ``"A,B,E"`` or ``"YES A,B"`` /
                        ``"NO C,F"``.
                        Classes A, B, D are always shown (mandatory).
        """
        return build_command(b'NM', filter_str.upper().encode('ascii'))

    @staticmethod
    def navstn_frame(filter_str: str) -> bytes:
        """NAVSTN — set station ID filter (mnemonic NS).

        Args:
            filter_str: ``"ALL"``, ``"NONE"``, or comma-separated station
                        ID letters e.g. ``"A,P,S"``.
        """
        return build_command(b'NS', filter_str.upper().encode('ascii'))

    @staticmethod
    def parse_header(data: bytes) -> Optional[tuple[str, str, str]]:
        """Parse a NAVTEX message header from received data.

        NAVTEX messages begin with ``ZCZC`` followed by a 4-character
        header: station_id + message_class + serial_2digits.

        Example: ``ZCZC PA99`` → station='P', class='A', serial='99'

        Args:
            data: Raw message bytes as received from the TNC.

        Returns:
            Tuple ``(station_id, message_class, serial)`` if a valid
            ZCZC header is found, or ``None`` if not found.
        """
        text = data.decode('ascii', errors='replace')
        idx  = text.find('ZCZC')
        if idx < 0:
            return None
        header = text[idx + 4:].lstrip()
        if len(header) < 4:
            return None
        station  = header[0].upper()
        msg_class = header[1].upper()
        serial   = header[2:4]
        return station, msg_class, serial

    @staticmethod
    def is_mandatory_class(msg_class: str) -> bool:
        """Return True if the message class is mandatory (A, B or D)."""
        return msg_class.upper() in MANDATORY_CLASSES