# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Baudot/RTTY operating mode (ITA-2, 5-bit).

Baudot RTTY uses the ITA-2 (5-bit) character set and is the most common
RTTY mode on HF amateur bands (primarily 14.080–14.100 MHz).

Key characteristics
-------------------
- 5-bit ITA-2 code (no lower case, limited punctuation)
- Two shift states: LETTERS (LTRS) and FIGURES (FIGS)
- Standard speeds: 45, 50, 75, 100 baud (45 most common on HF)
- DIDDLE: sends LTRS/idle character when no data to send
- CODE parameter selects character set:
    0 = ITA-2 (standard, default)
    2 = Cyrillic
    7 = Extended (MBX v7.x)
    8 = Extended (MBX v7.x alternate)

Host Mode frame types (TRM Section 4.3 / 4.4)
----------------------------------------------
  Incoming:
    $30  RX_DATA ch0   — received Baudot characters (decoded to ASCII by TNC)
    $2F  RX_ECHO       — echoed TX characters
    $5F  STATUS_ERR    — data ACK or error

  Outgoing:
    $4F  build_command(b'BA')           — enter Baudot mode
    $2x  build_data(0, data)            — send data (TNC encodes to Baudot)

Host Mode mnemonics (TRM Section 4.2.2)
----------------------------------------
  BA   BAUDOT       — enter Baudot mode
  RB   RBAUD        — receive baud rate
  CI   CODE         — character set (0=ITA2, 2=Cyrillic)
  AT   ACRRTTY      — auto CR on RTTY
  AR   ALFRTTY      — auto LF on RTTY (mnemonic AR per TRM)
  DI_  DIDDLE flag  — idle character (mnemonic DI conflicts with DISCONNECT)
                      use full name: b'DI' with Y/N — NOTE: in Baudot context
                      DIDDLE is set via Host mnemonic (see STABO Ch.12)
  AU   AUDELAY      — auto-unproto delay
  XB   XBAUD        — extra baud rate offset
  XL   XLENGTH      — line length
  EE   ERRCHAR      — error replacement character
  8B   8BITCONV      — 8-bit conversion
  WR   WRU          — auto answer-back on WRU request
  AB   AAB (AU)     — auto answer-back text (mnemonic AU per TRM mnemonic list)
  AF   AFILTER       — audio filter
  RX   RXREV        — RX polarity reverse
  TX   TXREV        — TX polarity reverse
  US   USOS         — unshift on space
  WI   WIDESHFT      — wide shift (850 Hz)
  XO   XMITOK       — transmit enable

Note on DIDDLE mnemonic: The TRM mnemonic list shows 'DI' for DISCONNE
(DISCONNECT) and does not list a separate DIDDLE mnemonic.  The STABO
manual Ch.12 lists DIDDLE as a flag parameter in the Baudot dialog.
In Host Mode the DIDDLE flag is likely set via the parameter name directly.
This needs verification on real hardware — marked TODO.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from pk232py.comm.frame import build_command, build_data, FrameKind
from pk232py.modes.base_mode import BaseMode

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from pk232py.comm.frame import HostFrame

logger = logging.getLogger(__name__)

# Supported Baudot RBAUD values (receive baud rate)
RBAUD_VALUES = [45, 50, 75, 100, 110, 150, 200, 300]

# CODE parameter values
CODE_ITA2     = 0   # ITA-2 (standard)
CODE_CYRILLIC = 2   # Cyrillic
CODE_EXT7     = 7   # Extended (MBX v7.x)
CODE_EXT8     = 8   # Extended alternate


class BaudotRTTYMode(BaseMode):
    """Baudot/RTTY mode (ITA-2, 5-bit).

    Handles incoming Host Mode frames and builds outgoing command frames
    for the Baudot RTTY operating mode of the PK-232MBX.

    The TNC handles all ITA-2 encoding/decoding internally.  The host
    receives decoded ASCII text and sends ASCII text for transmission.

    Callbacks
    ---------
    ``on_data_received``  : ``Callable[[bytes], None]``
        Called with received Baudot data decoded to ASCII by the TNC.

    ``on_echo_received``  : ``Callable[[bytes], None]``
        Called with echoed TX characters ($2F frames).

    ``on_data_ack``       : ``Callable[[], None]``
        Called when the TNC acknowledges a sent data block.
    """

    name         = "Baudot RTTY"
    host_command = b'BA'

    def __init__(
        self,
        rbaud:    int  = 45,
        code:     int  = CODE_ITA2,
        diddle:   bool = True,
        alfrtty:  bool = True,
        usos:     bool = True,
        rxrev:    bool = False,
        txrev:    bool = False,
        xmitok:   bool = True,
        xlength:  int  = 64,
        errchar:  int  = 0x5F,   # '_'
    ) -> None:
        super().__init__()
        self.rbaud   = rbaud
        self.code    = code
        self.diddle  = diddle
        self.alfrtty = alfrtty
        self.usos    = usos
        self.rxrev   = rxrev
        self.txrev   = txrev
        self.xmitok  = xmitok
        self.xlength = xlength
        self.errchar = errchar

        # Callbacks
        self.on_data_received: Optional[Callable[[bytes], None]] = None
        self.on_echo_received: Optional[Callable[[bytes], None]] = None
        self.on_data_ack:      Optional[Callable[[],      None]] = None

    # ------------------------------------------------------------------
    # BaseMode interface
    # ------------------------------------------------------------------

    def get_activate_frames(self) -> list[bytes]:
        """Return the frame to switch the TNC into Baudot RTTY mode.

        Mnemonic BA (TRM Section 4.2.2).
        """
        return [build_command(b'BA')]

    def get_init_frames(self) -> list[bytes]:
        """Return parameter frames sent after Baudot mode is confirmed."""
        frames = [
            self.rbaud_frame(self.rbaud),
            self.code_frame(self.code),
            self.alfrtty_frame(self.alfrtty),
            self.usos_frame(self.usos),
            self.xlength_frame(self.xlength),
            self.errchar_frame(self.errchar),
            self.rxrev_frame(self.rxrev),
            self.txrev_frame(self.txrev),
            self.xmitok_frame(self.xmitok),
        ]
        return frames

    def handle_frame(self, frame: "HostFrame") -> None:
        """Dispatch an incoming Host Mode frame.

        Frame types for Baudot mode:
          RX_DATA ($30)  — received characters (ASCII-decoded by TNC)
          RX_ECHO ($2F)  — echoed TX characters
          STATUS_ERR($5F)— data ACK or error

        Args:
            frame: Decoded HostFrame from the TNC.
        """
        kind = frame.kind

        if kind == FrameKind.RX_DATA:
            logger.debug("Baudot RX %d bytes", len(frame.data))
            if self.on_data_received:
                self.on_data_received(frame.data)

        elif kind == FrameKind.ECHO:
            # $2F — echoed TX characters (Morse, Baudot, AMTOR)
            logger.debug("Baudot ECHO %d bytes", len(frame.data))
            if self.on_echo_received:
                self.on_echo_received(frame.data)

        elif kind == FrameKind.STATUS_ERR:
            if len(frame.data) >= 3 and frame.data[2] == 0x00:
                logger.debug("Baudot data ACK")
                if self.on_data_ack:
                    self.on_data_ack()
            else:
                logger.warning("Baudot status error: %s", frame.data.hex())

        elif kind == FrameKind.CMD_RESP:
            logger.debug("Baudot CMD_RESP: %s", frame.data.hex())

        else:
            logger.debug("Baudot: unhandled frame %r", frame)

    # ------------------------------------------------------------------
    # Outgoing data
    # ------------------------------------------------------------------

    @staticmethod
    def data_frame(text: str) -> bytes:
        """Build a data frame for Baudot transmission (CTL = $20).

        The TNC encodes the ASCII text to ITA-2 Baudot internally.
        Use upper-case text — Baudot has no lower case.

        Args:
            text: ASCII text to transmit (upper-case recommended).
        """
        return build_data(0, text.upper().encode('ascii', errors='replace'))

    # ------------------------------------------------------------------
    # Parameter frame builders
    # ------------------------------------------------------------------

    @staticmethod
    def rbaud_frame(baud: int) -> bytes:
        """RBAUD — set receive baud rate (mnemonic RB).

        Common values: 45 (HF standard), 50 (European), 75, 100.
        """
        return build_command(b'RB', str(baud).encode('ascii'))

    @staticmethod
    def code_frame(code: int) -> bytes:
        """CODE — select character set (mnemonic CI).

        0=ITA-2, 2=Cyrillic, 7/8=Extended (MBX).
        """
        return build_command(b'CI', str(code).encode('ascii'))

    @staticmethod
    def alfrtty_frame(enabled: bool) -> bytes:
        """ALFRTTY — auto linefeed on RTTY (mnemonic AR)."""
        return build_command(b'AR', b'Y' if enabled else b'N')

    @staticmethod
    def usos_frame(enabled: bool) -> bytes:
        """USOS — unshift on space (mnemonic US).

        When ON, a SPACE character forces a shift to LETTERS.
        """
        return build_command(b'US', b'Y' if enabled else b'N')

    @staticmethod
    def rxrev_frame(enabled: bool) -> bytes:
        """RXREV — reverse RX polarity (mnemonic RX)."""
        return build_command(b'RX', b'Y' if enabled else b'N')

    @staticmethod
    def txrev_frame(enabled: bool) -> bytes:
        """TXREV — reverse TX polarity (mnemonic TX)."""
        return build_command(b'TX', b'Y' if enabled else b'N')

    @staticmethod
    def xmitok_frame(enabled: bool) -> bytes:
        """XMITOK — enable/disable transmit (mnemonic XO)."""
        return build_command(b'XO', b'Y' if enabled else b'N')

    @staticmethod
    def xlength_frame(length: int) -> bytes:
        """XLENGTH — line length in characters (mnemonic XL)."""
        return build_command(b'XL', str(length).encode('ascii'))

    @staticmethod
    def errchar_frame(char: int) -> bytes:
        """ERRCHAR — error replacement character (mnemonic EE).

        Args:
            char: ASCII code of replacement char (default 0x5F = '_').
        """
        return build_command(b'EE', f"${char:02X}".encode('ascii'))

    @staticmethod
    def aab_frame(text: str) -> bytes:
        """AAB — auto answer-back string (mnemonic AU).

        Sent in response to a WRU (Who aRe yoU) request.
        """
        return build_command(b'AU', text.encode('ascii', errors='replace'))

    @staticmethod
    def wideshft_frame(enabled: bool) -> bytes:
        """WIDESHFT — use 850 Hz shift instead of 170 Hz (mnemonic WI)."""
        return build_command(b'WI', b'Y' if enabled else b'N')