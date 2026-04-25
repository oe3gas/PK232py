# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Signal Analysis (SIAM) mode — unknown signal identification.

SIAM (Signal Identification and Analysis Mode) is a special mode of
the PK-232MBX that attempts to identify unknown FSK signals and report
their characteristics: baud rate, shift, number of channels, and
probable mode.

Key characteristics
-------------------
- Passive receive-only analysis
- Reports: baud rate, frequency shift, channel count, mode guess
- Useful before switching to TDM, RTTY, or other modes
- SAMPLE parameter controls analysis duration
- Results delivered as CMD_RESP frames (text output)

Host Mode frame types
---------------------
  Incoming:
    $4F  CMD_RESP    — SIAM analysis result text
    $5F  STATUS_ERR  — error

  Outgoing:
    $4F  build_command(b'SI')           — enter SIGNAL mode (mnemonic SI)
    $4F  build_command(b'SA', samples)  — SAMPLE count

Host Mode mnemonics (TRM)
--------------------------
  SI   SIGNAL  — enter signal analysis (SIAM) mode
  SA   SAMPLE  — number of samples for analysis (default varies)

SIAM output format (from STABO manual Ch. 10):
  The TNC reports findings as text, e.g.:
    "BAUDOT 45 170"  → 45 baud Baudot, 170 Hz shift
    "TDM ARQ-B:4"    → TDM ARQ-B, 4-character repetition
    "UNKNOWN"        → signal not identified
"""

from __future__ import annotations

import logging
from typing import Callable, Optional, TYPE_CHECKING

from pk232py.comm.frame import build_command, FrameKind
from pk232py.modes.base_mode import BaseMode

if TYPE_CHECKING:
    from pk232py.comm.frame import HostFrame

logger = logging.getLogger(__name__)


class SignalMode(BaseMode):
    """Signal Analysis (SIAM) mode.

    Passive signal identification — the TNC analyses the received signal
    and reports baud rate, shift, channel count and probable mode as
    CMD_RESP text frames.

    Typical workflow::

        sm = SignalMode()
        sm.on_result = lambda text: print("SIAM:", text)
        mode_manager.set_mode_instance(sm)
        # Tune to unknown signal, wait for result

    Callbacks
    ---------
    ``on_result``  : ``Callable[[str], None]``
        Called with the SIAM analysis result string from the TNC.
    """

    name         = "Signal"
    host_command = b'SI'
    verbose_command = b"SIGNAL\r\n"

    def __init__(self, sample: int = 0) -> None:  # 0 = TNC default
        """
        Args:
            sample: Number of samples for analysis.
                    Range 0-65535.  Default 0 = TNC default.
        """
        super().__init__()
        self.sample = max(0, min(65535, sample))
        self.on_result: Optional[Callable[[str], None]] = None

    def get_activate_frames(self) -> list[bytes]:
        return [build_command(b'SI')]

    def get_init_frames(self) -> list[bytes]:
        # SA nur senden wenn sample > 0, sonst TNC-Default verwenden
        if self.sample > 0:
            return [self.sample_frame(self.sample)]
        return []

    def handle_frame(self, frame: "HostFrame") -> None:
        kind = frame.kind
        if kind == FrameKind.CMD_RESP:
            text = frame.text.strip()
            if text and not text.endswith('\x00'):
                logger.info("SIAM result: %s", text)
                if self.on_result:
                    self.on_result(text)
        elif kind == FrameKind.LINK_MSG:
            # SIAM liefert Ergebnisse als LINK_MSG ($50)
            text = frame.text.strip()
            if text:
                logger.info("SIAM result (LINK_MSG): %s", text)
                if self.on_result:
                    self.on_result(text)
        elif kind == FrameKind.STATUS_ERR:
            logger.warning("SIAM status error: %s", frame.data.hex())
        else:
            logger.debug("SIAM: unhandled frame %r", frame)

    @staticmethod
    def sample_frame(count: int) -> bytes:
        """SAMPLE — number of analysis samples (mnemonic SA)."""
        return build_command(b'SA', str(max(0, min(65535, count))).encode('ascii'))