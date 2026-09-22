# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""MailDrop Controller — manages the PK-232MBX personal mailbox.

The PK-232MBX has a built-in personal MailDrop (mailbox) that allows
other stations to leave messages when the operator is absent.  The
MailDrop supports a subset of the W0RLI/WA7MBL PBBS commands.

This module provides the host-side controller for interacting with the
TNC MailDrop via Host Mode commands.

MailDrop Host Mode mnemonics (STABO manual Ch. 12) — UNVERIFIED (P24.1,
2026-09-22): NONE of the mnemonics below have been confirmed against
real hardware. `MD` is documented in the TRM as MDIGI, not MDPROMPT —
the exact same class of error as `MI` (believed to be MailDrop login,
hardware-confirmed 22.09.2026 to actually be MFILTER, see T115 in
Testplan.md and CLAUDE.md's "Hardware-confirmed Host Mode mnemonics"
table). Do not trust this table for anything that sends a frame; verify
each mnemonic with `tools/hw_check.py` or the TRM before relying on it,
and add it to CLAUDE.md's confirmed table once measured.
---------------------------------------------------------------------
  HB   HOMEBBS      — home BBS callsign
  MY   MYMAIL       — mailbox callsign (usually = MYCALL)
  LM   LASTMSG      — last message number
  MD   MDPROMPT     — MailDrop prompt character
  TP   TMPROMPT     — temporary message prompt
  MT   MTEXT        — MailDrop welcome text
  TL   TMAIL        — enable MailDrop (Y/N)
  3P   3RDPARTY     — allow 3rd party messages (Y/N)
  KF   KILONFWD     — delete after forwarding (Y/N)
  MM   MMSG         — monitor MailDrop messages (Y/N)
  DM   MDMON        — MailDrop monitor (Y/N)

MailDrop interaction (command protocol)
----------------------------------------
When a station connects to your MailDrop, the TNC handles the session
automatically.  The host can monitor traffic via MDMON and receive
notification frames.

This module handles:
  1. Sending MailDrop configuration parameters to the TNC
  2. Monitoring incoming MailDrop sessions (LINK_MSG frames)
  3. Interface to the local message store (MessageStore)
"""

from __future__ import annotations

import logging
from typing import Callable, Optional, TYPE_CHECKING

from pk232py.comm.frame import build_command, FrameKind

if TYPE_CHECKING:
    from pk232py.comm.frame import HostFrame
    from pk232py.comm.serial_manager import SerialManager

logger = logging.getLogger(__name__)


class MailDropController:
    """Manages TNC MailDrop configuration and session monitoring.

    Sends MailDrop parameters to the TNC and monitors incoming
    MailDrop sessions via Host Mode link message frames.

    Args:
        serial: The application's SerialManager instance.

    Callbacks
    ---------
    ``on_session_start``  : ``Callable[[str], None]``
        Called with the connecting station's callsign when a MailDrop
        session begins.

    ``on_session_end``    : ``Callable[[str], None]``
        Called with the callsign when a MailDrop session ends.

    ``on_message_left``   : ``Callable[[str, str], None]``
        Called with (callsign, message_text) when a message is left.
    """

    def __init__(self, serial: "SerialManager") -> None:
        self._serial = serial

        # Configuration
        self.homebbs:    str  = ""      # home BBS callsign
        self.mymail:     str  = ""      # mailbox callsign
        self.mtext:      str  = ""      # welcome text
        self.tmail:      bool = False   # MailDrop enabled
        self.third_party: bool = False  # allow 3rd party messages
        self.kilonfwd:   bool = False   # delete after forwarding
        self.mdmon:      bool = True    # monitor MailDrop sessions
        self.mmsg:       bool = True    # monitor messages

        # Callbacks
        self.on_session_start: Optional[Callable[[str], None]] = None
        self.on_session_end:   Optional[Callable[[str], None]] = None
        self.on_message_left:  Optional[Callable[[str, str], None]] = None

    # ------------------------------------------------------------------
    # Configuration upload
    # ------------------------------------------------------------------

    def upload_config(self) -> None:
        """Send all MailDrop parameters to the TNC via Host Mode."""
        frames = self._build_config_frames()
        for mnemonic, args in frames:
            self._serial.send_command(mnemonic, args)
        logger.info("MailDrop config uploaded (%d frames)", len(frames))

    def _build_config_frames(self) -> list[tuple[bytes, bytes]]:
        """Build all MailDrop configuration frames."""
        frames = [
            (b'TL', b'Y' if self.tmail     else b'N'),
            (b'3P', b'Y' if self.third_party else b'N'),
            (b'KF', b'Y' if self.kilonfwd  else b'N'),
            (b'DM', b'Y' if self.mdmon     else b'N'),
            (b'MM', b'Y' if self.mmsg      else b'N'),
        ]
        if self.homebbs:
            frames.append((b'HB', self.homebbs.upper().encode('ascii')))
        if self.mymail:
            frames.append((b'MY', self.mymail.upper().encode('ascii')))
        if self.mtext:
            frames.append((b'MT', self.mtext.encode('ascii', errors='replace')))
        return frames

    # ------------------------------------------------------------------
    # Frame handling
    # ------------------------------------------------------------------

    def on_frame(self, frame: "HostFrame") -> None:
        """Process a Host Mode frame for MailDrop monitoring.

        Watches LINK_MSG ($5x) frames for MailDrop session events.
        Connect this to SerialManager.frame_received.

        Args:
            frame: Decoded HostFrame from the TNC.
        """
        if frame.kind != FrameKind.LINK_MSG:
            return

        text  = frame.text.strip()
        lower = text.lower()

        # Detect MailDrop session events from link messages
        if "connected" in lower and "maildrop" in lower:
            callsign = self._extract_callsign(text)
            logger.info("MailDrop session start: %s", callsign)
            if self.on_session_start:
                self.on_session_start(callsign)

        elif "disconnected" in lower or "disconnect" in lower:
            callsign = self._extract_callsign(text)
            logger.info("MailDrop session end: %s", callsign)
            if self.on_session_end:
                self.on_session_end(callsign)

    # ------------------------------------------------------------------
    # Parameter frame builders (static)
    # ------------------------------------------------------------------

    @staticmethod
    def tmail_frame(enabled: bool) -> bytes:
        """TMAIL — enable/disable MailDrop (mnemonic TL)."""
        return build_command(b'TL', b'Y' if enabled else b'N')

    @staticmethod
    def homebbs_frame(callsign: str) -> bytes:
        """HOMEBBS — set home BBS callsign (mnemonic HB)."""
        return build_command(b'HB', callsign.upper().encode('ascii'))

    @staticmethod
    def mymail_frame(callsign: str) -> bytes:
        """MYMAIL — set mailbox callsign (mnemonic MY)."""
        return build_command(b'MY', callsign.upper().encode('ascii'))

    @staticmethod
    def mtext_frame(text: str) -> bytes:
        """MTEXT — set MailDrop welcome text (mnemonic MT)."""
        return build_command(b'MT', text.encode('ascii', errors='replace'))

    @staticmethod
    def third_party_frame(enabled: bool) -> bytes:
        """3RDPARTY — allow 3rd party messages (mnemonic 3P)."""
        return build_command(b'3P', b'Y' if enabled else b'N')

    @staticmethod
    def kilonfwd_frame(enabled: bool) -> bytes:
        """KILONFWD — delete messages after forwarding (mnemonic KF)."""
        return build_command(b'KF', b'Y' if enabled else b'N')

    @staticmethod
    def mdmon_frame(enabled: bool) -> bytes:
        """MDMON — monitor MailDrop sessions (mnemonic DM)."""
        return build_command(b'DM', b'Y' if enabled else b'N')

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_callsign(text: str) -> str:
        """Try to extract a callsign from a link message string."""
        import re
        # Common pattern: "CONNECTED to W1AW" or "W1AW connected"
        match = re.search(
            r'\b([A-Z0-9]{3,7}(?:/[A-Z0-9]+)?)\b',
            text.upper()
        )
        if match:
            word = match.group(1)
            # Skip common non-callsign words
            if word not in ("CONNECTED", "DISCONNECTED", "MAILDROP",
                            "STATION", "LINK", "SYSTEM"):
                return word
        return "UNKNOWN"