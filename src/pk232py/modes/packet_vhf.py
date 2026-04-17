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

from pk232py.comm.frame import build_command
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
    """

    name         = "VHF Packet"
    host_command = b'PA'   # same mnemonic as HF Packet

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

        Inherits monitor ON from HFPacketMode.get_init_frames() and
        adds VHF-optimised defaults: HBAUD 1200, MAXFRAME 4, SLOTTIME 10.
        """
        frames = super().get_init_frames()   # includes MONITOR ON
        frames += [
            build_command(b'HB', b'1200'),  # HBAUD 1200
            build_command(b'MX', b'4'),     # MAXFRAME 4
            build_command(b'SL', b'10'),    # SLOTTIME 10 (10ms units = 100ms)
        ]
        return frames

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