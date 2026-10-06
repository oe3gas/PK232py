# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""VHF Packet operating mode (AX.25, 1200 baud).

VHF Packet is functionally identical to HF Packet but uses different
default parameters optimised for VHF/UHF FM operation:

  HBAUD  1200    (vs 300 on HF)
  TXDELAY 30     (vs 30 — same, but shorter acceptable on VHF)
  FRACK  7       (same)
  MAXFRAME 4     (vs 1 on HF — VHF links are more reliable)
  PERSIST 63     (same)
  SLOTTIME 10    (vs 30 on HF — VHF channels are faster)
  RETRY  10      (same)
  VHF    ON      — must be set to select 1200 baud modem

Host Mode mnemonic to activate: PA (same as HF Packet)
VHF flag set via:  build_command(b'VH', b'Y')
HBAUD set via:     build_command(b'HB', str(1200).encode())

The PK-232MBX automatically uses the 1200 baud Bell 202 modem when
VHF is ON.  HF Packet uses the 300 baud modem (VHF OFF, HBAUD 300).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pk232py.comm.constants import verbose_line
from pk232py.comm.frame import build_command
from pk232py.config import HFPacketConfig
from pk232py.modes.packet_hf import HFPacketMode

if TYPE_CHECKING:
    from pk232py.comm.frame import HostFrame

logger = logging.getLogger(__name__)


class VHFPacketMode(HFPacketMode):
    """AX.25 VHF/UHF Packet mode (1200 baud, Bell 202).

    Subclass of :class:`~pk232py.modes.packet_hf.HFPacketMode` — all
    frame handling and callbacks are inherited unchanged.  Only the
    activation sequence and default parameters differ.

    The key difference from HF Packet:
      - VHF ON  sets the 1200 baud Bell 202 modem
      - HBAUD 1200 sets the host baud rate
      - MAXFRAME 4 is appropriate for reliable VHF links
      - SLOTTIME 10 (shorter than HF) for faster channel access

    P73 B: ``maxframe``/``slottime`` are the VHF values from
    ``HFPacketConfig.vhf_maxframe`` / ``vhf_slottime``.  They used to be the
    fixed numbers 4 and 10 (P19.3); the defaults are those numbers, so an
    old INI changes nothing.  MainWindow._build_mode_instance() passes the
    configured values in; which config attribute belongs to which band is
    defined once, in comm/host_params.py (BAND_PARAMS).
    """

    name         = "VHF Packet"
    host_command = b'PA'   # same mnemonic as HF Packet
    verbose_command = verbose_line("VHF")

    def __init__(
        self,
        maxframe: int = HFPacketConfig.vhf_maxframe,
        slottime: int = HFPacketConfig.vhf_slottime,
        monitor: int = HFPacketConfig.monitor,
    ) -> None:
        """Same parameters as HFPacketMode, but the defaults are the VHF
        values (one source of truth: HFPacketConfig, as in P19.3)."""
        super().__init__(maxframe=maxframe, slottime=slottime, monitor=monitor)

    def get_activate_frames(self) -> list[bytes]:
        """Return frames to switch TNC to VHF Packet mode.

        Sends PA (PACKET) then sets VHF ON to select the 1200 baud modem.
        """
        return [
            build_command(b'PA'),          # enter Packet mode
            build_command(b'VH', b'Y'),    # VHF ON — select 1200 baud modem
        ]

    def get_init_frames(self) -> list[bytes]:
        """Return VHF-specific parameter frames.

        Sequence (Testplan T31): HB 1200, MX, SL, MN <monitor>.  ``VH Y`` is
        already sent in get_activate_frames().

        Lernmodus: this deliberately does NOT call super().get_init_frames().
        The HF base now emits ``VH N`` (VHF OFF) to select the 300 Bd modem;
        inheriting that here would immediately undo the ``VH Y`` we just sent
        and drop VHF Packet back to the HF modem.  So VHF builds its own list.
        """
        return [
            build_command(b'HB', b'1200'),  # HBAUD 1200
            build_command(b'MX', str(self.maxframe).encode('ascii')),  # MAXFRAME (VHF value)
            build_command(b'SL', str(self.slottime).encode('ascii')),  # SLOTTIME (VHF value, 10 ms units)
            build_command(b'MN', str(self.monitor).encode('ascii')),  # MONITOR (P73 A)
        ]

    def deactivate(self) -> None:
        """Mark mode as inactive.

        Note: VHF OFF should be sent when leaving VHF Packet mode to
        restore the HF 300 baud modem for other modes.  The caller
        (mode manager) is responsible for sending build_command(b'VH', b'N').
        """
        super().deactivate()

    @staticmethod
    def vhf_off_frame() -> bytes:
        """Build a VHF OFF frame to restore HF 300 baud modem.

        Send this when switching away from VHF Packet to any HF mode.
        """
        return build_command(b'VH', b'N')

    @staticmethod
    def hbaud_frame(baud: int) -> bytes:
        """Build an HBAUD frame (mnemonic HB).

        Args:
            baud: 300 (HF) or 1200 (VHF).
        """
        return build_command(b'HB', str(baud).encode('ascii'))