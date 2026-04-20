# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""CW / Morse operating mode.

The PK-232MBX supports both sending and receiving Morse code (CW).
The TNC handles all encoding/decoding internally.

Key characteristics
-------------------
- Speed range: 5–99 WPM (MSPEED)
- Auto speed tracking on receive (LOCK command)
- Weight adjustment: 10–90% (MWEIGHT, default 10 = standard ratio)
- EAS (Echo As Sent): shows confirmed sent characters ($2F frames)
- WORDOUT: send only complete words (buffer until SPACE)
- Special Morse characters supported (SK, AR, BT, KN, etc.)
- CW ID interval via MID (Morse ID)

Host Mode frame types (TRM Section 4.3 / 4.4)
----------------------------------------------
  Incoming:
    $30  RX_DATA ch0  — decoded Morse characters (ASCII)
    $2F  RX_ECHO      — echoed TX characters (EAS ON)
    $5F  STATUS_ERR   — data ACK or error

  Outgoing:
    $4F  build_command(b'MO')              — enter Morse mode
    $2x  build_data(0, data)              — send text (TNC encodes to CW)

Host Mode mnemonics (TRM Section 4.2.2)
----------------------------------------
  MO   MORSE    — enter Morse mode (mnemonic MO)
  MP   MSPEED   — send/receive speed in WPM (5-99)
  MW   MWEIGHT  — dit/dah weight ratio (10-90, default 10)
  MI   MID      — Morse ID interval in minutes (0=off)
  EA   EAS      — echo as sent (Y/N)
  WO   WORDOUT  — send only complete words (Y/N)
  LO   LOCK     — lock receive speed to current signal (direct cmd)
  XO   XMITOK   — transmit enable (Y/N)

Note on special Morse characters (STABO manual Ch. 8):
  *  or <  →  SK  (end of contact)
  &        →  AS  (please wait)
  +        →  AR  (end of message)
  (        →  KN  (go only)
  =        →  BT  (break / pause)
  >  or %  →  KA  (attention)
  !        →  SN  (understood)
"""

from __future__ import annotations

import logging
from typing import Callable, Optional, TYPE_CHECKING

from pk232py.comm.frame import build_command, build_data, FrameKind
from pk232py.modes.base_mode import BaseMode

if TYPE_CHECKING:
    from pk232py.comm.frame import HostFrame

logger = logging.getLogger(__name__)

# Speed limits
MSPEED_MIN = 5
MSPEED_MAX = 99

# Weight limits (10 = standard ratio, higher = heavier dashes)
MWEIGHT_MIN = 10
MWEIGHT_MAX = 90


class MorseMode(BaseMode):
    """CW / Morse operating mode.

    The TNC handles all Morse encoding and decoding.  The host sends
    plain ASCII text and the TNC converts it to CW.  Received CW is
    decoded to ASCII and delivered as RX_DATA frames.

    Special Morse characters are sent using their ASCII substitutes
    as documented in the STABO manual (e.g. '*' for SK, '+' for AR).

    Callbacks
    ---------
    ``on_data_received``  : ``Callable[[bytes], None]``
        Called with decoded Morse text ($30 frames).

    ``on_echo_received``  : ``Callable[[bytes], None]``
        Called with echoed TX characters ($2F, EAS mode).

    ``on_data_ack``       : ``Callable[[], None]``
        Called when TNC acknowledges a sent data block.
    """

    name         = "CW/Morse"
    host_command = b'MO'

    def __init__(
        self,
        mspeed:  int  = 20,     # send speed WPM
        mweight: int  = 10,     # dit/dah weight (10=standard)
        mid:     int  = 0,      # Morse ID interval minutes (0=off)
        eas:     bool = False,  # echo as sent
        wordout: bool = False,  # send only complete words
        xmitok:  bool = True,
    ) -> None:
        super().__init__()
        self.mspeed  = max(MSPEED_MIN,  min(MSPEED_MAX,  mspeed))
        self.mweight = max(MWEIGHT_MIN, min(MWEIGHT_MAX, mweight))
        self.mid     = mid
        self.eas     = eas
        self.wordout = wordout
        self.xmitok  = xmitok

        # Callbacks
        self.on_data_received: Optional[Callable[[bytes], None]] = None
        self.on_echo_received: Optional[Callable[[bytes], None]] = None
        self.on_data_ack:      Optional[Callable[[],      None]] = None

    # ------------------------------------------------------------------
    # BaseMode interface
    # ------------------------------------------------------------------

    def get_activate_frames(self) -> list[bytes]:
        """Return the frame to switch TNC to Morse mode (mnemonic MO)."""
        return [build_command(b'MO')]

    def get_init_frames(self) -> list[bytes]:
        """Return parameter frames sent after Morse mode is confirmed."""
        return [
            self.mspeed_frame(self.mspeed),
            self.mweight_frame(self.mweight),
            self.mid_frame(self.mid),
            self.eas_frame(self.eas),
            self.wordout_frame(self.wordout),
            self.xmitok_frame(self.xmitok),
        ]

    def handle_frame(self, frame: "HostFrame") -> None:
        """Dispatch an incoming Host Mode frame for Morse mode.

        Frame types:
          RX_DATA ($30)  — decoded Morse characters (ASCII text)
          RX_ECHO ($2F)  — echoed TX chars (EAS ON)
          STATUS_ERR($5F)— data ACK or error

        Args:
            frame: Decoded HostFrame from the TNC.
        """
        kind = frame.kind

        if kind in (FrameKind.RX_DATA, FrameKind.RX_MONITOR):
            logger.debug("Morse RX %d bytes", len(frame.data))
            if self.on_data_received:
                self.on_data_received(frame.data)

        elif kind == FrameKind.ECHO:
            # $2F — echoed TX characters (EAS mode)
            logger.debug("Morse ECHO %d bytes", len(frame.data))
            if self.on_echo_received:
                self.on_echo_received(frame.data)

        elif kind == FrameKind.STATUS_ERR:
            if len(frame.data) >= 3 and frame.data[2] == 0x00:
                logger.debug("Morse data ACK")
                if self.on_data_ack:
                    self.on_data_ack()
            else:
                logger.warning("Morse status error: %s", frame.data.hex())

        elif kind == FrameKind.CMD_RESP:
            logger.debug("Morse CMD_RESP: %s", frame.data.hex())

        else:
            logger.debug("Morse: unhandled frame %r", frame)

    # ------------------------------------------------------------------
    # Outgoing data
    # ------------------------------------------------------------------

    @staticmethod
    def data_frame(text: str) -> bytes:
        """Build a data frame for Morse transmission (CTL = $20, ch0).

        The TNC encodes the ASCII text to Morse code internally.
        Text is uppercased automatically.

        Special character substitutions (STABO manual Ch. 8):
          *  →  SK (end of contact)
          +  →  AR (end of message)
          =  →  BT (break/pause)
          (  →  KN (go only)
          &  →  AS (please wait)

        Args:
            text: Text to transmit.  Use upper case for best results.
        """
        return build_data(0, text.upper().encode('ascii', errors='replace'))

    # ------------------------------------------------------------------
    # Parameter frame builders
    # ------------------------------------------------------------------

    @staticmethod
    def mspeed_frame(wpm: int) -> bytes:
        """MSPEED — set Morse send speed in WPM (mnemonic MP).

        Range: 5–99 WPM.  Default: 20 WPM.
        The TNC automatically tracks receive speed; this sets TX speed.
        """
        wpm = max(MSPEED_MIN, min(MSPEED_MAX, wpm))
        return build_command(b'MP', str(wpm).encode('ascii'))

    @staticmethod
    def mweight_frame(weight: int) -> bytes:
        """MWEIGHT — dit/dah weight ratio (mnemonic MW).

        Range: 10–90.  Default: 10 (standard 1:3 ratio).
        Higher values produce heavier (longer dash) keying.
        """
        weight = max(MWEIGHT_MIN, min(MWEIGHT_MAX, weight))
        return build_command(b'MW', str(weight).encode('ascii'))

    @staticmethod
    def mid_frame(minutes: int) -> bytes:
        """MID — Morse ID interval in minutes (mnemonic MI).

        0 = disabled.  When set, TNC sends MYCALL in Morse at interval.
        """
        return build_command(b'MI', str(minutes).encode('ascii'))

    @staticmethod
    def eas_frame(enabled: bool) -> bytes:
        """EAS — echo as sent (mnemonic EA).

        When ON, TNC echoes confirmed sent characters ($2F frames).
        Useful to verify what is actually being transmitted.
        """
        return build_command(b'EA', b'Y' if enabled else b'N')

    @staticmethod
    def wordout_frame(enabled: bool) -> bytes:
        """WORDOUT — send only complete words (mnemonic WO).

        When ON, the TNC buffers characters until SPACE is received,
        then sends the complete word.  Allows correction before sending.
        """
        return build_command(b'WO', b'Y' if enabled else b'N')

    @staticmethod
    def xmitok_frame(enabled: bool) -> bytes:
        """XMITOK — enable/disable transmit (mnemonic XO)."""
        return build_command(b'XO', b'Y' if enabled else b'N')

    @staticmethod
    def lock_frame() -> bytes:
        """LOCK — lock receive speed to current signal (mnemonic LO).

        Tells TNC to synchronise RX speed to the incoming signal.
        Send 'R' or 'MO' command to unlock.
        """
        return build_command(b'LO')