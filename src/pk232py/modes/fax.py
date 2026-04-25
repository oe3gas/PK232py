# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""FAX receive mode (HF weather-chart facsimile).

The PK-232MBX can receive HF weather-chart facsimile (WEFAX) broadcasts.
FAX is receive-only in practice; the TNC outputs received pixel data
which must be rendered by the host application.

Key characteristics
-------------------
- Receive-only (weather charts, satellite images)
- Standard HF FAX frequencies: 4, 8, 12, 16, 22 MHz bands
- FSPEED: drum speed in RPM (default varies; common: 60, 90, 120, 240)
- ASPECT: line density control (1-6, affects image proportions)
- FAXNEG: negative image (invert black/white)
- GRAPHICS: print density (dot-matrix printer output, legacy)

Host Mode frame types
---------------------
  Incoming:
    $3F  RX_MONITOR  — FAX pixel/line data
    $5F  STATUS_ERR  — sync lost or other error

  Outgoing:
    $4F  build_command(b'FA')         — enter FAX mode (mnemonic FA)
    $4F  build_command(b'FS', speed)  — FSPEED drum RPM
    $4F  build_command(b'AY', aspect) — ASPECT line density
    $4F  build_command(b'FN', yn)     — FAXNEG (Y/N)

Host Mode mnemonics (TRM)
--------------------------
  FA   FAX     — enter FAX receive mode
  FS   FSPEED  — drum rotation speed (RPM)
  AY   ASPECT  — aspect ratio / line density (1-6, default 2=576 lpi)
  FN   FAXNEG  — negative image (Y/N)
  GR   GRAPHICS— print dot density (legacy printer output)
"""

from __future__ import annotations

import logging
from typing import Callable, Optional, TYPE_CHECKING

from pk232py.comm.frame import build_command, FrameKind
from pk232py.modes.base_mode import BaseMode

if TYPE_CHECKING:
    from pk232py.comm.frame import HostFrame

logger = logging.getLogger(__name__)

# Common HF FAX drum speeds (RPM)
FSPEED_60  = 60
FSPEED_90  = 90
FSPEED_120 = 120
FSPEED_240 = 240


class FAXMode(BaseMode):
    """HF Weather-chart FAX receive mode.

    Receive-only mode for HF facsimile broadcasts (WEFAX).
    Pixel data is delivered as RX_MONITOR ($3F) frames.

    Note: Rendering of pixel data into an image is the responsibility
    of the host application (not implemented in v1.2).

    Callbacks
    ---------
    ``on_data_received``  : ``Callable[[bytes], None]``
        Called with raw FAX pixel/line data ($3F frames).
    """

    name         = "FAX"
    host_command = b'FA'
    verbose_command = b"FAX\r\n"

    def __init__(
        self,
        fspeed: int  = 120,   # drum speed RPM
        aspect: int  = 2,     # line density 1-6 (2=576 lpi standard)
        faxneg: bool = False,  # negative image
    ) -> None:
        super().__init__()
        self.fspeed = fspeed
        self.aspect = max(1, min(6, aspect))
        self.faxneg = faxneg

        self.on_data_received: Optional[Callable[[bytes], None]] = None

    def get_activate_frames(self) -> list[bytes]:
        return [build_command(b'FA')]

    def get_init_frames(self) -> list[bytes]:
        return [
            self.fspeed_frame(self.fspeed),
            self.aspect_frame(self.aspect),
            self.faxneg_frame(self.faxneg),
        ]

    def handle_frame(self, frame: "HostFrame") -> None:
        kind = frame.kind
        if kind == FrameKind.RX_MONITOR:
            logger.debug("FAX RX %d bytes", len(frame.data))
            if self.on_data_received:
                self.on_data_received(frame.data)
        elif kind == FrameKind.STATUS_ERR:
            logger.warning("FAX status error: %s", frame.data.hex())
        elif kind == FrameKind.CMD_RESP:
            logger.debug("FAX CMD_RESP: %s", frame.data.hex())
        else:
            logger.debug("FAX: unhandled frame %r", frame)

    @staticmethod
    def fspeed_frame(rpm: int) -> bytes:
        """FSPEED — drum rotation speed in RPM (mnemonic FS).

        Common values: 60, 90, 120, 240 RPM.
        Standard HF weather FAX uses 120 RPM.
        """
        return build_command(b'FS', str(rpm).encode('ascii'))

    @staticmethod
    def aspect_frame(value: int) -> bytes:
        """ASPECT — line density / aspect ratio (mnemonic AY).

        Range 1-6.  Default 2 (576 lines per inch, standard WEFAX).
        Higher values stretch the image vertically.
        """
        return build_command(b'AY', str(max(1, min(6, value))).encode('ascii'))

    @staticmethod
    def faxneg_frame(enabled: bool) -> bytes:
        """FAXNEG — invert image (negative), mnemonic FN."""
        return build_command(b'FN', b'Y' if enabled else b'N')