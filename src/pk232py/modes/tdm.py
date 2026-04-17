# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""TDM (Time Division Multiplexing) receive mode — CCIR 342 / Moore Code.

TDM is a receive-only mode for monitoring Time Division Multiplexed
signals, also known as Moore Code (CCIR recommendation 342).

Key characteristics
-------------------
- Receive-only (no transmit in TDM mode)
- 1-, 2-, or 4-channel multiplexed FSK signals
- Valid baud rates depend on channel count:
    1-channel:  48, 72, 96
    2-channel:  86, 96, 100
    4-channel: 171, 192, 200
  (Other values disable error detection; outside 0-200 resets to 96)
- TDCHAN selects which channel to display (0-3)
- TDM stations are mostly idle — allow 1-2 hours for synchronisation
- Use SIAM first to identify signal and determine baud rate

Host Mode frame types
---------------------
  Incoming:
    $3F  RX_MONITOR  — decoded TDM channel data
    $5F  STATUS_ERR  — error

  Outgoing:
    $4F  build_command(b'TV')       — enter TDM mode (mnemonic TV)
    $4F  build_command(b'TU', baud) — TDBAUD
    $4F  build_command(b'TN', chan) — TDCHAN

Host Mode mnemonics (TRM / STABO manual)
-----------------------------------------
  TV   TDm     — enter TDM receive mode
  TU   TDBAUD  — TDM signal baud rate (0-200, default 96)
  TN   TDCHAN  — channel selection (0-3)
"""

from __future__ import annotations

import logging
from typing import Callable, Optional, TYPE_CHECKING

from pk232py.comm.frame import build_command, FrameKind
from pk232py.modes.base_mode import BaseMode

if TYPE_CHECKING:
    from pk232py.comm.frame import HostFrame

logger = logging.getLogger(__name__)

# Valid baud rates per channel count
VALID_BAUDS_1CH = (48, 72, 96)
VALID_BAUDS_2CH = (86, 96, 100)
VALID_BAUDS_4CH = (171, 192, 200)
ALL_VALID_BAUDS = frozenset(VALID_BAUDS_1CH + VALID_BAUDS_2CH + VALID_BAUDS_4CH)


class TDMMode(BaseMode):
    """TDM (Time Division Multiplexing) receive mode — CCIR 342.

    Receive-only mode for monitoring multiplexed FSK signals.
    Use SIAM (SignalMode) first to identify the signal and baud rate.

    Callbacks
    ---------
    ``on_data_received``  : ``Callable[[bytes], None]``
        Called with decoded TDM channel data ($3F frames).
    """

    name         = "TDM"
    host_command = b'TV'

    def __init__(
        self,
        tdbaud: int = 96,   # TDM signal baud rate
        tdchan: int = 0,    # channel to display (0-3)
    ) -> None:
        super().__init__()
        self.tdbaud = tdbaud
        self.tdchan = max(0, min(3, tdchan))

        self.on_data_received: Optional[Callable[[bytes], None]] = None

    def get_activate_frames(self) -> list[bytes]:
        return [build_command(b'TV')]

    def get_init_frames(self) -> list[bytes]:
        return [
            self.tdbaud_frame(self.tdbaud),
            self.tdchan_frame(self.tdchan),
        ]

    def handle_frame(self, frame: "HostFrame") -> None:
        kind = frame.kind
        if kind == FrameKind.RX_MONITOR:
            logger.debug("TDM RX %d bytes ch%d", len(frame.data), frame.channel)
            if self.on_data_received:
                self.on_data_received(frame.data)
        elif kind == FrameKind.STATUS_ERR:
            logger.warning("TDM status error: %s", frame.data.hex())
        elif kind == FrameKind.CMD_RESP:
            logger.debug("TDM CMD_RESP: %s", frame.data.hex())
        else:
            logger.debug("TDM: unhandled frame %r", frame)

    @staticmethod
    def tdbaud_frame(baud: int) -> bytes:
        """TDBAUD — TDM signal baud rate (mnemonic TU, default 96).

        Valid values: 48/72/96 (1-ch), 86/96/100 (2-ch), 171/192/200 (4-ch).
        Other values disable error detection.
        """
        return build_command(b'TU', str(baud).encode('ascii'))

    @staticmethod
    def tdchan_frame(channel: int) -> bytes:
        """TDCHAN — select display channel 0-3 (mnemonic TN).

        Channel mapping depends on signal type:
          1-ch: no effect
          2-ch: 0/2=A, 1/3=B
          4-ch: 0=A, 1=B, 2=C, 3=D
        """
        return build_command(b'TN', str(max(0, min(3, channel))).encode('ascii'))

    @staticmethod
    def is_valid_baud(baud: int) -> bool:
        """Return True if baud rate is a known valid TDM rate."""
        return baud in ALL_VALID_BAUDS