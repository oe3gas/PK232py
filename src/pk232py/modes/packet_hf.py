# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""HF Packet operating mode (AX.25, 300 baud).

TODO (v0.2):
    - Implement full connect/disconnect flow
    - Handle multi-stream connections (channels 1-26)
    - Parse MHEARD responses
    - Implement digipeater path support
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pk232py.comm.hostmode import HostModeProtocol
from pk232py.modes.base_mode import BaseMode

if TYPE_CHECKING:
    from pk232py.comm.hostmode import HostFrame

logger = logging.getLogger(__name__)


class HFPacketMode(BaseMode):
    """AX.25 HF Packet mode (300 baud)."""

    name = "HF Packet"
    host_command = b'PA'   # PACKET command mnemonic

    def get_activate_frames(self) -> list[bytes]:
        """Return the Host Mode frame to switch TNC to Packet mode."""
        return [HostModeProtocol.build_frame(0x00, b'PA')]

    def handle_frame(self, frame: "HostFrame") -> None:
        """Handle an incoming Host Mode frame in Packet mode.

        Args:
            frame: Decoded frame from the TNC.
        """
        cmd = frame.command
        if cmd == b'CO':
            logger.info("Connected to: %s", frame.data.decode('ascii', errors='replace'))
        elif cmd == b'DI':
            logger.info("Disconnected from: %s", frame.data.decode('ascii', errors='replace'))
        elif cmd == b'DT':
            # Received data frame
            logger.debug("Data received (%d bytes)", len(frame.data))
        elif cmd == b'ST':
            # Status frame
            logger.debug("Status: %s", frame.data.hex())
        else:
            logger.debug("Unhandled Packet frame: cmd=%s data=%s", cmd, frame.data.hex())
