# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""ASCII RTTY operating mode (7-bit ASCII).

ASCII RTTY uses the full 7-bit ASCII character set, providing upper and
lower case letters, digits, and all punctuation.  Less common than Baudot
on HF bands but provides a richer character set.

Key differences from Baudot
----------------------------
- 7-bit ASCII (128 characters vs 64 in ITA-2)
- Upper AND lower case available
- No shift states — each character is self-contained
- 8BITCONV flag enables 8-bit transparent mode
- Same speed range as Baudot (45–300 baud)
- Activated via 'ASCII' command (mnemonic AS)

Host Mode frame types
---------------------
Same as Baudot:
  $30  RX_DATA ch0  — received ASCII characters
  $2F  RX_ECHO      — echoed TX characters
  $5F  STATUS_ERR   — data ACK or error

Host Mode mnemonics
--------------------
  AS   ASCII        — enter ASCII RTTY mode
  RB   RBAUD        — receive baud rate
  8B   8BITCONV      — 8-bit transparent mode (mnemonic 8B)
  AT   ACRRTTY      — auto CR
  AR   ALFRTTY      — auto LF
  XL   XLENGTH      — line length
  EE   ERRCHAR      — error replacement character
  RX   RXREV        — RX polarity reverse
  TX   TXREV        — TX polarity reverse
  XO   XMITOK       — transmit enable
"""

from __future__ import annotations

import logging
from typing import Callable, Optional, TYPE_CHECKING

from pk232py.comm.frame import build_command, build_data, FrameKind
from pk232py.modes.base_mode import BaseMode

if TYPE_CHECKING:
    from pk232py.comm.frame import HostFrame

logger = logging.getLogger(__name__)


class ASCIIRTTYMode(BaseMode):
    """ASCII RTTY mode (7-bit).

    Functionally very similar to :class:`BaudotRTTYMode` but uses the
    full 7-bit ASCII character set and activates with mnemonic AS.

    Callbacks
    ---------
    ``on_data_received``  : ``Callable[[bytes], None]``
        Called with received ASCII data.

    ``on_echo_received``  : ``Callable[[bytes], None]``
        Called with echoed TX characters.

    ``on_data_ack``       : ``Callable[[], None]``
        Called when the TNC acknowledges a sent data block.
    """

    name         = "ASCII RTTY"
    host_command = b'AS'

    def __init__(
        self,
        rbaud:      int  = 45,
        bitconv8:   bool = False,  # 8BITCONV — 8-bit transparent mode
        alfrtty:    bool = True,
        rxrev:      bool = False,
        txrev:      bool = False,
        xmitok:     bool = True,
        xlength:    int  = 64,
        errchar:    int  = 0x5F,
    ) -> None:
        super().__init__()
        self.rbaud    = rbaud
        self.bitconv8 = bitconv8
        self.alfrtty  = alfrtty
        self.rxrev    = rxrev
        self.txrev    = txrev
        self.xmitok   = xmitok
        self.xlength  = xlength
        self.errchar  = errchar

        # Callbacks
        self.on_data_received: Optional[Callable[[bytes], None]] = None
        self.on_echo_received: Optional[Callable[[bytes], None]] = None
        self.on_data_ack:      Optional[Callable[[],      None]] = None

    # ------------------------------------------------------------------
    # BaseMode interface
    # ------------------------------------------------------------------

    def get_activate_frames(self) -> list[bytes]:
        """Return the frame to switch the TNC into ASCII RTTY mode (AS)."""
        return [build_command(b'AS')]

    def get_init_frames(self) -> list[bytes]:
        """Return parameter frames sent after ASCII mode is confirmed."""
        return [
            self.rbaud_frame(self.rbaud),
            self.bitconv8_frame(self.bitconv8),
            self.alfrtty_frame(self.alfrtty),
            self.xlength_frame(self.xlength),
            self.errchar_frame(self.errchar),
            self.rxrev_frame(self.rxrev),
            self.txrev_frame(self.txrev),
            self.xmitok_frame(self.xmitok),
        ]

    def handle_frame(self, frame: "HostFrame") -> None:
        """Dispatch incoming Host Mode frame for ASCII RTTY.

        Args:
            frame: Decoded HostFrame from the TNC.
        """
        kind = frame.kind

        if kind in (FrameKind.RX_DATA, FrameKind.RX_MONITOR):
            logger.debug("ASCII RTTY RX %d bytes", len(frame.data))
            if self.on_data_received:
                self.on_data_received(frame.data)

        elif kind == FrameKind.ECHO:
            logger.debug("ASCII RTTY ECHO %d bytes", len(frame.data))
            if self.on_echo_received:
                self.on_echo_received(frame.data)

        elif kind == FrameKind.STATUS_ERR:
            if len(frame.data) >= 3 and frame.data[2] == 0x00:
                logger.debug("ASCII RTTY data ACK")
                if self.on_data_ack:
                    self.on_data_ack()
            else:
                logger.warning("ASCII RTTY status error: %s", frame.data.hex())

        elif kind == FrameKind.CMD_RESP:
            logger.debug("ASCII RTTY CMD_RESP: %s", frame.data.hex())

        else:
            logger.debug("ASCII RTTY: unhandled frame %r", frame)

    # ------------------------------------------------------------------
    # Outgoing data
    # ------------------------------------------------------------------

    @staticmethod
    def data_frame(text: str) -> bytes:
        """Build a data frame for ASCII RTTY transmission (CTL = $20).

        Unlike Baudot, ASCII RTTY preserves lower case.

        Args:
            text: Text to transmit (full ASCII character set available).
        """
        return build_data(0, text.encode('ascii', errors='replace'))

    # ------------------------------------------------------------------
    # Parameter frame builders
    # ------------------------------------------------------------------

    @staticmethod
    def rbaud_frame(baud: int) -> bytes:
        """RBAUD — set receive baud rate (mnemonic RB)."""
        return build_command(b'RB', str(baud).encode('ascii'))

    @staticmethod
    def bitconv8_frame(enabled: bool) -> bytes:
        """8BITCONV — enable 8-bit transparent mode (mnemonic 8B).

        When ON, all 8 data bits are passed transparently.
        Required for binary data transfer over ASCII RTTY.
        """
        return build_command(b'8B', b'Y' if enabled else b'N')

    @staticmethod
    def alfrtty_frame(enabled: bool) -> bytes:
        """ALFRTTY — auto linefeed on RTTY (mnemonic AR)."""
        return build_command(b'AR', b'Y' if enabled else b'N')

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
        """ERRCHAR — error replacement character (mnemonic EE)."""
        return build_command(b'EE', f"${char:02X}".encode('ascii'))