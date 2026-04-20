# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""AMTOR operating mode — ARQ (Mode A) and FEC/SELFEC (Mode B).

AMTOR (Amateur Teleprinting Over Radio) is a 7-bit error-correcting
digital mode derived from the commercial SITOR system (CCIR 476-2/476-3).

Two sub-modes
-------------
Mode A — ARQ (Automatic ReQuest for reception)
  - Two-station handshaking protocol
  - Near error-free transmission even under poor conditions
  - Requires 4-character SELCAL of both stations
  - Characteristic "chirp chirp" sound

Mode B — FEC (Forward Error Correction) / SELFEC
  - Broadcast mode, no handshaking
  - FEC:    general broadcast (like calling CQ)
  - SELFEC: selective FEC — only received by station with matching SELCAL

SELCAL
------
AMTOR requires a 4-character SELCAL derived from the callsign.
The TNC derives it automatically from the callsign entered via MYSELCAL.
Example: MYSELCAL DL1GMC → DGMC

MYIDENT is a 7-character CCIR-625 identifier (optional).
MYALTCAL is an alternative SELCAL (optional).

Host Mode frame types (TRM Section 4.3 / 4.4)
----------------------------------------------
  Incoming (TNC -> Host):
    $30  RX_DATA ch0   — ARQ connected data (Mode A)
    $3F  RX_MONITOR    — FEC/SELFEC received data (Mode B)
    $2F  RX_ECHO       — echoed TX characters (EAS mode)
    $5x  LINK_MSG      — CONNECTED, DISCONNECTED, link messages
    $5F  STATUS_ERR    — data ACK ($00) or error

  Outgoing (Host -> TNC):
    $4F  build_command(b'AM')              — enter AMTOR standby
    $4F  build_command(b'AC', selcal)      — ARQ call (start Mode A)
    $4F  build_command(b'FE')              — FEC broadcast (Mode B)
    $4F  build_command(b'SE', selcal)      — SELFEC selective FEC
    $4F  build_command(b'AL')              — ALIST (Mode A listen)
    $2x  build_data(0, data)               — send data on ch0

Host Mode mnemonics (TRM Section 4.2.2)
----------------------------------------
  AM   AMOTR    — enter AMTOR standby
  AC   ARQ      — start ARQ call (= ARQ {selcal})
  FE   FEC      — start FEC broadcast
  SE   SELFEC   — start selective FEC
  AL   ALIST    — AMTOR listen mode
  MG   MYSELCAL — 4-char SELCAL (derived from callsign)
  MK   MYALTCAL — alternative SELCAL
  MY   MYIDENT  — 7-char CCIR-625 ident
  AO   ARQTMO   — ARQ timeout (seconds)
  Ao   ARQTOL   — ARQ bit-jitter tolerance (1-5)
  AD   ADELAY   — ARQ delay
  AG   ACHG     — ARQ changeover character
  AT   ACRRTTY  — auto CR
  AR   ALFRTTY  — auto LF
  RF   RFEC     — receive FEC in ARQ standby
  SR   SRXALL   — receive all SELFEC (not just own SELCAL)
  EE   ERRCHAR  — error replacement character
  EA   EAS      — echo as sent
  RX   RXREV    — RX polarity reverse
  TX   TXREV    — TX polarity reverse
  XO   XMITOK   — transmit enable
  XL   XLENGTH  — line length
  WI   WIDESHFT — wide shift (850 Hz)
"""

from __future__ import annotations

import logging
from typing import Callable, Optional, TYPE_CHECKING

from pk232py.comm.frame import build_command, build_data, FrameKind
from pk232py.modes.base_mode import BaseMode

if TYPE_CHECKING:
    from pk232py.comm.frame import HostFrame

logger = logging.getLogger(__name__)

# Link message substrings
_MSG_CONNECTED    = "connected"
_MSG_DISCONNECTED = "disconnected"
_MSG_BUSY         = "busy"
_MSG_CONNECT_REQ  = "connect request"
_MSG_RETRY        = "retry"
_MSG_LINK_OOO     = "link out of order"


class AMTORMode(BaseMode):
    """AMTOR ARQ (Mode A) and FEC/SELFEC (Mode B) operating mode.

    Both sub-modes are handled by a single class since the PK-232MBX
    uses the same 'AM' command to enter AMTOR standby, from which
    either ARQ or FEC can be initiated.

    SELCAL requirement
    ------------------
    MYSELCAL must be set before ARQ or SELFEC can be used.  The TNC
    derives a 4-character SELCAL from the entered callsign automatically.
    Set ``myselcal`` in the constructor or call ``myselcal_frame()``
    explicitly before activating the mode.

    Callbacks
    ---------
    ``on_arq_data``     : ``Callable[[bytes], None]``
        Called with ARQ connected data ($30 frames, Mode A).

    ``on_fec_data``     : ``Callable[[bytes], None]``
        Called with FEC/SELFEC received data ($3F frames, Mode B).

    ``on_echo``         : ``Callable[[bytes], None]``
        Called with echoed TX characters ($2F, EAS mode).

    ``on_link_message`` : ``Callable[[str], None]``
        Called with link state change text (CONNECTED, DISCONNECTED, …).

    ``on_data_ack``     : ``Callable[[], None]``
        Called when TNC acknowledges a sent data block ($5F $00).
    """

    name         = "AMTOR"
    host_command = b'AM'

    def __init__(
        self,
        myselcal:  str   = "",      # 4-char SELCAL (derived from callsign by TNC)
        myaltcal:  str   = "",      # alternative SELCAL (optional)
        myident:   str   = "",      # 7-char CCIR-625 ident (optional)
        arqtmo:    int   = 60,      # ARQ timeout seconds
        arqtol:    int   = 3,       # ARQ bit-jitter tolerance 1-5
        adelay:    int   = 2,       # ARQ delay
        rfec:      bool  = True,    # receive FEC in ARQ standby
        srxall:    bool  = False,   # receive all SELFEC (not just own SELCAL)
        errchar:   int   = 0x5F,    # error replacement char (default '_')
        eas:       bool  = False,   # echo as sent
        rxrev:     bool  = False,
        txrev:     bool  = False,
        xmitok:    bool  = True,
        xlength:   int   = 64,
    ) -> None:
        super().__init__()
        self.myselcal = myselcal.upper()
        self.myaltcal = myaltcal.upper()
        self.myident  = myident.upper()
        self.arqtmo   = arqtmo
        self.arqtol   = arqtol
        self.adelay   = adelay
        self.rfec     = rfec
        self.srxall   = srxall
        self.errchar  = errchar
        self.eas      = eas
        self.rxrev    = rxrev
        self.txrev    = txrev
        self.xmitok   = xmitok
        self.xlength  = xlength

        # Callbacks
        self.on_arq_data:     Optional[Callable[[bytes], None]] = None
        self.on_fec_data:     Optional[Callable[[bytes], None]] = None
        self.on_echo:         Optional[Callable[[bytes], None]] = None
        self.on_link_message: Optional[Callable[[str],   None]] = None
        self.on_data_ack:     Optional[Callable[[],      None]] = None

    # ------------------------------------------------------------------
    # BaseMode interface
    # ------------------------------------------------------------------

    def get_activate_frames(self) -> list[bytes]:
        """Return the frame to switch TNC to AMTOR standby (mnemonic AM)."""
        return [build_command(b'AM')]

    def get_init_frames(self) -> list[bytes]:
        """Return parameter frames sent after AMTOR mode is confirmed.

        Always includes MYSELCAL if set (required for ARQ and SELFEC).
        """
        frames = []
        if self.myselcal:
            frames.append(self.myselcal_frame(self.myselcal))
        if self.myaltcal:
            frames.append(self.myaltcal_frame(self.myaltcal))
        if self.myident:
            frames.append(self.myident_frame(self.myident))
        frames += [
            self.arqtmo_frame(self.arqtmo),
            self.arqtol_frame(self.arqtol),
            self.adelay_frame(self.adelay),
            self.rfec_frame(self.rfec),
            self.srxall_frame(self.srxall),
            self.errchar_frame(self.errchar),
            self.eas_frame(self.eas),
            self.rxrev_frame(self.rxrev),
            self.txrev_frame(self.txrev),
            self.xmitok_frame(self.xmitok),
            self.xlength_frame(self.xlength),
        ]
        return frames

    def handle_frame(self, frame: "HostFrame") -> None:
        """Dispatch an incoming Host Mode frame for AMTOR.

        Frame types (TRM Section 4.4.3):
          RX_DATA ($30)   — ARQ connected data (Mode A)
          RX_MONITOR ($3F)— FEC/SELFEC data (Mode B)
          RX_ECHO ($2F)   — echoed TX chars (EAS)
          LINK_MSG ($5x)  — CONNECTED, DISCONNECTED, …
          STATUS_ERR ($5F)— data ACK or error

        Args:
            frame: Decoded HostFrame from the TNC.
        """
        kind = frame.kind

        if kind in (FrameKind.RX_DATA, FrameKind.RX_MONITOR):
            # Mode A (ARQ) — TRM Section 4.4.3
            logger.debug("AMTOR ARQ RX %d bytes", len(frame.data))
            if self.on_arq_data:
                self.on_arq_data(frame.data)

        elif kind == FrameKind.RX_MONITOR:
            # Mode B (FEC/SELFEC) — TRM Section 4.4.3
            logger.debug("AMTOR FEC RX %d bytes", len(frame.data))
            if self.on_fec_data:
                self.on_fec_data(frame.data)

        elif kind == FrameKind.ECHO:
            # $2F — echoed TX chars (active when EAS = ON)
            logger.debug("AMTOR ECHO %d bytes", len(frame.data))
            if self.on_echo:
                self.on_echo(frame.data)

        elif kind == FrameKind.LINK_MSG:
            self._handle_link_msg(frame)

        elif kind == FrameKind.STATUS_ERR:
            if len(frame.data) >= 3 and frame.data[2] == 0x00:
                logger.debug("AMTOR data ACK")
                if self.on_data_ack:
                    self.on_data_ack()
            else:
                logger.warning("AMTOR status error: %s", frame.data.hex())

        elif kind == FrameKind.CMD_RESP:
            logger.debug("AMTOR CMD_RESP: %s", frame.data.hex())

        else:
            logger.debug("AMTOR: unhandled frame %r", frame)

    # ------------------------------------------------------------------
    # Outgoing data
    # ------------------------------------------------------------------

    @staticmethod
    def data_frame(text: str) -> bytes:
        """Build a data frame for AMTOR transmission (CTL = $20, ch0).

        AMTOR uses the ITA-2 character set internally — upper case only.
        The TNC handles the encoding.

        Args:
            text: Text to transmit (will be uppercased).
        """
        return build_data(0, text.upper().encode('ascii', errors='replace'))

    # ------------------------------------------------------------------
    # Mode control frames
    # ------------------------------------------------------------------

    @staticmethod
    def arq_call_frame(selcal: str) -> bytes:
        """Build an ARQ call frame — initiate Mode A contact (mnemonic AC).

        Args:
            selcal: 4- or 7-character SELCAL of the destination station.
        """
        return build_command(b'AC', selcal.upper().encode('ascii'))

    @staticmethod
    def fec_frame() -> bytes:
        """Build a FEC broadcast frame — start Mode B transmission (mnemonic FE).

        FEC is a general broadcast: any station can receive it.
        """
        return build_command(b'FE')

    @staticmethod
    def selfec_frame(selcal: str) -> bytes:
        """Build a SELFEC frame — selective Mode B (mnemonic SE).

        Only the station with the matching SELCAL will receive this.

        Args:
            selcal: 4-character SELCAL of the destination station.
        """
        return build_command(b'SE', selcal.upper().encode('ascii'))

    @staticmethod
    def alist_frame() -> bytes:
        """Build an ALIST frame — enter Mode A listen (mnemonic AL).

        ALIST monitors ARQ traffic between other stations.
        """
        return build_command(b'AL')

    # ------------------------------------------------------------------
    # Parameter frame builders
    # ------------------------------------------------------------------

    @staticmethod
    def myselcal_frame(selcal: str) -> bytes:
        """MYSELCAL — set own 4-char SELCAL (mnemonic MG).

        The TNC derives a 4-char SELCAL from the entered callsign
        automatically per CCIR recommendation 491.

        Args:
            selcal: Callsign or explicit 4-char SELCAL, e.g. 'OE3GAS'.
                    TNC will derive SELCAL: OE3GAS → OGAS or similar.
        """
        return build_command(b'MG', selcal.upper().encode('ascii'))

    @staticmethod
    def myaltcal_frame(altcal: str) -> bytes:
        """MYALTCAL — alternative SELCAL (mnemonic MK).

        Used when two stations share the same derived SELCAL.
        """
        return build_command(b'MK', altcal.upper().encode('ascii'))

    @staticmethod
    def myident_frame(ident: str) -> bytes:
        """MYIDENT — 7-character CCIR-625 identifier (mnemonic MY).

        Used for SELFEC and CCIR-625 compatible stations.
        """
        return build_command(b'MY', ident.upper().encode('ascii'))

    @staticmethod
    def arqtmo_frame(seconds: int) -> bytes:
        """ARQTMO — ARQ call timeout in seconds (mnemonic AO).

        How long the TNC keeps calling before giving up (default 60s).
        """
        return build_command(b'AO', str(seconds).encode('ascii'))

    @staticmethod
    def arqtol_frame(tolerance: int) -> bytes:
        """ARQTOL — ARQ bit-jitter tolerance 1-5 (mnemonic Ao).

        1 = tight (fewer retransmissions, more errors accepted),
        5 = loose (more retransmissions, better for poor conditions).
        Default: 3.
        """
        return build_command(b'Ao', str(tolerance).encode('ascii'))

    @staticmethod
    def adelay_frame(delay: int) -> bytes:
        """ADELAY — ARQ delay (mnemonic AD)."""
        return build_command(b'AD', str(delay).encode('ascii'))

    @staticmethod
    def rfec_frame(enabled: bool) -> bytes:
        """RFEC — receive FEC while in ARQ standby (mnemonic RF).

        When ON, the TNC monitors FEC broadcasts while waiting for ARQ calls.
        """
        return build_command(b'RF', b'Y' if enabled else b'N')

    @staticmethod
    def srxall_frame(enabled: bool) -> bytes:
        """SRXALL — receive all SELFEC, not just own SELCAL (mnemonic SR)."""
        return build_command(b'SR', b'Y' if enabled else b'N')

    @staticmethod
    def eas_frame(enabled: bool) -> bytes:
        """EAS — echo as sent (mnemonic EA).

        When ON, TNC echoes confirmed sent characters ($2F frames).
        """
        return build_command(b'EA', b'Y' if enabled else b'N')

    @staticmethod
    def errchar_frame(char: int) -> bytes:
        """ERRCHAR — error replacement character (mnemonic EE).

        Args:
            char: ASCII code, default 0x5F ('_').
        """
        return build_command(b'EE', f"${char:02X}".encode('ascii'))

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
    def wideshft_frame(enabled: bool) -> bytes:
        """WIDESHFT — 850 Hz shift instead of 170 Hz (mnemonic WI)."""
        return build_command(b'WI', b'Y' if enabled else b'N')

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _handle_link_msg(self, frame: "HostFrame") -> None:
        """Handle $5x link messages (TRM Section 4.4.4)."""
        text  = frame.text.strip()
        lower = text.lower()

        if _MSG_CONNECTED in lower and _MSG_DISCONNECTED not in lower:
            logger.info("AMTOR: %s", text)
        elif _MSG_DISCONNECTED in lower:
            logger.info("AMTOR: %s", text)
        elif _MSG_CONNECT_REQ in lower:
            logger.info("AMTOR incoming: %s", text)
        elif _MSG_BUSY in lower:
            logger.info("AMTOR: %s", text)
        elif _MSG_RETRY in lower:
            logger.warning("AMTOR: %s", text)
        elif _MSG_LINK_OOO in lower:
            logger.error("AMTOR: %s", text)
        else:
            logger.debug("AMTOR link msg: %s", text)

        if self.on_link_message:
            self.on_link_message(text)


# ---------------------------------------------------------------------------
# AMTOR FEC (Mode B / SELFEC) — convenience subclass
# ---------------------------------------------------------------------------

class AMTORFECMode(AMTORMode):
    """AMTOR FEC (Mode B / SELFEC) — broadcast receive mode.

    Identical to AMTORMode but pre-configured for FEC receive:
    - srxall=True: receive all SELFEC broadcasts (not just own SELCAL)
    - rfec=True:   receive FEC in ARQ standby

    The TNC is switched to AMTOR standby via the same b'AM' command;
    FEC/SELFEC reception starts automatically when a signal is detected.
    Activating FEC transmit requires calling selfec_frame() explicitly.
    """

    name         = "AMTOR FEC"
    host_command = b'AM'          # same as ARQ — FEC is a sub-mode

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("srxall", True)
        kwargs.setdefault("rfec",   True)
        super().__init__(**kwargs)

    def activate_frame(self) -> bytes:
        """Build the Host Mode frame to enter AMTOR FEC standby."""
        # SELFEC: send SELFEC command after entering AMTOR standby
        from .amtor import AMTORMode
        return self.selfec_frame()