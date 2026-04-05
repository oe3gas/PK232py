# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""PACTOR I operating mode.

PACTOR I is supported by PK-232MBX firmware v7.0 and later.
The callsign for PACTOR must be set via MYPTCALL (not MYCALL).

TODO (v0.3):
    - Implement ARQ connect/disconnect
    - Handle Huffman-compressed data frames
    - Implement PTOVER (direction change, default Ctrl-Z)
    - Implement PTSEND (FEC/unproto mode)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pk232py.comm.hostmode import HostModeProtocol
from pk232py.modes.base_mode import BaseMode

if TYPE_CHECKING:
    from pk232py.comm.hostmode import HostFrame

logger = logging.getLogger(__name__)


class PACTORMode(BaseMode):
    """PACTOR I ARQ mode."""

    name = "PACTOR"
    host_command = b'PT'   # PACTOR command mnemonic

    def get_activate_frames(self) -> list[bytes]:
        """Return the Host Mode frame to switch TNC to PACTOR mode."""
        return [HostModeProtocol.build_frame(0x00, b'PT')]

    def handle_frame(self, frame: "HostFrame") -> None:
        """Handle an incoming Host Mode frame in PACTOR mode.

        Args:
            frame: Decoded frame from the TNC.
        """
        cmd = frame.command
        if cmd == b'CO':
            logger.info("PACTOR connected: %s", frame.data.decode('ascii', errors='replace'))
        elif cmd == b'DI':
            logger.info("PACTOR disconnected")
        elif cmd == b'DT':
            logger.debug("PACTOR data received (%d bytes)", len(frame.data))
        elif cmd == b'ST':
            logger.debug("PACTOR status: %s", frame.data.hex())
        else:
            logger.debug("Unhandled PACTOR frame: cmd=%s", cmd)
