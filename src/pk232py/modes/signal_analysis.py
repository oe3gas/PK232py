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
- Reports: confidence, baud rate, probable mode, RXREV recommendation
- Useful before switching to TDM, RTTY, or other modes
- SAMPLE parameter controls analysis duration
- The TNC analyses continuously, sending a new result roughly every 10s
  (hardware-verified, Testplan T113, 2026-09-22) — it does not stop after
  one result.

Host Mode frame types
---------------------
  Incoming:
    $50  LINK_MSG    — SIAM analysis result text, on channel 0. EVERY
                        result is split across exactly two LINK_MSG
                        frames, the second one terminated with '\\r\\n'
                        (hardware-verified, T113). Results NEVER arrive
                        as CMD_RESP — see the P16.3/P18.2 note below.
    $5F  STATUS_ERR  — error

  Outgoing:
    $4F  build_command(b'SI')           — enter SIGNAL mode (mnemonic SI)
    $4F  build_command(b'SA', samples)  — SAMPLE count

Host Mode mnemonics (TRM)
--------------------------
  SI   SIGNAL  — enter signal analysis (SIAM) mode
  SA   SAMPLE  — number of samples for analysis (default varies)

SIAM output format (hardware-verified, T113, 2026-09-22 — matches the
signal_screen.py mockup, NOT the STABO manual's "BAUDOT 45 170" example,
which this module's docstring wrongly assumed before T113):
    "<confidence>: <baud> baud, <mode>, RXRev <ON|OFF>"
  e.g.:
    "0.73: 50 baud, Baudot, RXRev ON"

Frame type / result-recognition history (P16.3 / P18.2)
---------------------------------------------------------
Before T113 it was unknown whether SIAM results arrive as $4F CMD_RESP or
$50 LINK_MSG — this module's own docstring said CMD_RESP while
handle_frame() also treated LINK_MSG as a result, and P16.3 found that
ANY stray CMD_RESP arriving while Signal/SIAM was active (a delayed
HPOLL flush, an ACK/NAK for an unrelated command, ...) could be
misreported as a bogus SIAM result. T113 settled this on real hardware:
results are LINK_MSG only. handle_frame() therefore no longer calls
on_result()/on_result_parsed() for CMD_RESP frames at all — not "most"
of them, none.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Callable, Optional, TYPE_CHECKING

from pk232py.comm.constants import verbose_line
from pk232py.comm.frame import build_command, FrameKind
from pk232py.modes.base_mode import BaseMode

if TYPE_CHECKING:
    from pk232py.comm.frame import HostFrame

logger = logging.getLogger(__name__)

# A result buffer that never sees a line ending this long is not a SIAM
# result fragment gone slow - it is stray data, and holding onto it
# forever would let it bleed into whatever comes next. Comfortably above
# the longest real result seen in T113 (~40 chars).
_MAX_BUFFER_LEN = 200

_RESULT_RE = re.compile(
    r"^(?P<confidence>\d+\.\d+):\s*(?P<baud>\d+)\s+baud,\s*"
    r"(?P<mode>.+?),\s*RXRev\s+(?P<rxrev>ON|OFF)\s*$",
    re.IGNORECASE,
)


@dataclass
class SiamResult:
    """One parsed SIAM analysis result (T113 hardware format)."""
    confidence: float   # 0.73
    baud: int            # 50
    mode: str            # "Baudot"
    rxrev: bool          # True for "RXRev ON"
    raw: str             # the full assembled line, e.g.
                          # "0.73: 50 baud, Baudot, RXRev ON"


def parse_siam_result(text: str) -> Optional[SiamResult]:
    """Parse one assembled SIAM result line into a SiamResult.

    Returns None if *text* does not match the T113 hardware format — not
    an error: other signal types (TDM, AMTOR, "Noise", ...) may report in
    a different shape that has not been measured yet (P18.2).
    """
    m = _RESULT_RE.match(text.strip())
    if not m:
        return None
    return SiamResult(
        confidence=float(m.group("confidence")),
        baud=int(m.group("baud")),
        mode=m.group("mode").strip(),
        rxrev=m.group("rxrev").upper() == "ON",
        raw=text,
    )


class SignalMode(BaseMode):
    """Signal Analysis (SIAM) mode.

    Passive signal identification — the TNC analyses the received signal
    continuously and reports confidence, baud rate, probable mode and an
    RXREV recommendation as LINK_MSG text, split across two frames per
    result (T113).

    Typical workflow::

        sm = SignalMode()
        sm.on_result = lambda text: print("SIAM:", text)
        sm.on_result_parsed = lambda r: print("SIAM:", r.mode, r.baud)
        mode_manager.set_mode_instance(sm)
        # Tune to unknown signal, wait for results (one roughly every 10s)

    Callbacks
    ---------
    ``on_result``  : ``Callable[[str], None]``
        Called with the assembled SIAM result string once a complete
        line has arrived, whatever its format — kept for backward
        compatibility with callers that only want the raw text.
    ``on_result_parsed`` : ``Callable[[SiamResult], None]``
        Called with a :class:`SiamResult` when the assembled line matches
        the known T113 format. Not called when it does not match (see
        ``parse_siam_result()``) — ``on_result`` still fires either way.
    """

    name         = "Signal (SIAM)"
    host_command = b'SI'
    verbose_command = verbose_line("SIGNAL")

    def __init__(self, sample: int = 0) -> None:  # 0 = TNC default
        """
        Args:
            sample: Number of samples for analysis.
                    Range 0-65535.  Default 0 = TNC default.
        """
        super().__init__()
        self.sample = max(0, min(65535, sample))
        self.on_result: Optional[Callable[[str], None]] = None
        self.on_result_parsed: Optional[Callable[[SiamResult], None]] = None
        self._siam_buffer = ""

    def get_activate_frames(self) -> list[bytes]:
        # A fragment left over from a previous SIAM session must never
        # bleed into this one's first result (P18.2).
        self._siam_buffer = ""
        return [build_command(b'SI')]

    def get_init_frames(self) -> list[bytes]:
        # SA nur senden wenn sample > 0, sonst TNC-Default verwenden
        if self.sample > 0:
            return [self.sample_frame(self.sample)]
        return []

    def handle_frame(self, frame: "HostFrame") -> None:
        kind = frame.kind
        if kind == FrameKind.CMD_RESP:
            # SIAM results never arrive as CMD_RESP (T113, hardware-
            # verified 2026-09-22) - log for diagnostics only, never
            # treat this as a result (see the module docstring's P16.3/
            # P18.2 note).
            logger.debug("SIAM: CMD_RESP (not a result): %r", frame.data)
        elif kind == FrameKind.LINK_MSG:
            self._accumulate(frame.text)
        elif kind == FrameKind.STATUS_ERR:
            logger.warning("SIAM status error: %s", frame.data.hex())
        else:
            logger.debug("SIAM: unhandled frame %r", frame)

    def _accumulate(self, text: str) -> None:
        """Assemble SIAM results out of their LINK_MSG fragments (T113):
        every result is split across two frames, complete only once a
        '\\n' (bare or as part of '\\r\\n') has been seen."""
        self._siam_buffer += text
        while "\n" in self._siam_buffer:
            line, self._siam_buffer = self._siam_buffer.split("\n", 1)
            self._emit(line.rstrip("\r"))
        if len(self._siam_buffer) > _MAX_BUFFER_LEN:
            logger.warning(
                "SIAM: buffer exceeded %d chars without a line ending, "
                "discarding: %r", _MAX_BUFFER_LEN, self._siam_buffer
            )
            self._siam_buffer = ""

    def _emit(self, line: str) -> None:
        text = line.strip()
        if not text:
            return
        logger.info("SIAM result: %s", text)
        if self.on_result:
            self.on_result(text)
        parsed = parse_siam_result(text)
        if parsed is not None:
            if self.on_result_parsed:
                self.on_result_parsed(parsed)
        else:
            logger.info("SIAM result did not match the known format: %s", text)

    @staticmethod
    def sample_frame(count: int) -> bytes:
        """SAMPLE — number of analysis samples (mnemonic SA)."""
        return build_command(b'SA', str(max(0, min(65535, count))).encode('ascii'))
