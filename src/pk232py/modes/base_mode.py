# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Abstract base class for all PK-232 operating modes."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pk232py.comm.frame import HostFrame   # HostFrame lives in frame.py

logger = logging.getLogger(__name__)


class BaseMode(ABC):
    """Abstract base class for all PK-232 operating modes.

    Subclasses implement the mode-specific Host Mode command sequences
    and handle incoming frames from the TNC.

    The ``name`` and ``host_command`` class attributes must be set
    by each subclass.

    Lifecycle
    ---------
    1. UI calls ``get_activate_frames()`` → sends frames to TNC.
    2. UI calls ``get_init_frames()``     → sends parameter frames.
    3. UI calls ``activate()``            → marks mode as active.
    4. Incoming frames are dispatched via ``handle_frame()``.
    5. UI calls ``deactivate()``          → marks mode as inactive.
    """

    #: Human-readable mode name, e.g. "HF Packet"
    name: str = "Unknown"

    #: 2-byte Host Mode mnemonic to activate this mode, e.g. b'PA'
    host_command: bytes = b''

    def __init__(self) -> None:
        self._active = False

    @property
    def is_active(self) -> bool:
        """True if this mode is currently active on the TNC."""
        return self._active

    def activate(self) -> None:
        """Mark this mode as active.

        Called by the mode manager AFTER the activate and init frames
        have been sent to the TNC and acknowledged.  Override to perform
        any in-memory state reset needed when entering the mode.
        """
        self._active = True
        logger.info("Mode activated: %s", self.name)

    def deactivate(self) -> None:
        """Mark this mode as inactive.

        Called by the mode manager when the user switches away.
        Override to clean up any mode-specific state.
        """
        self._active = False
        logger.info("Mode deactivated: %s", self.name)

    @abstractmethod
    def handle_frame(self, frame: "HostFrame") -> None:
        """Process an incoming Host Mode frame addressed to this mode.

        Called by the mode manager for every frame whose CTL range
        matches this mode (RX_DATA, LINK_MSG, ECHO, etc.).

        Args:
            frame: Decoded Host Mode frame from the TNC.
        """

    @abstractmethod
    def get_activate_frames(self) -> list[bytes]:
        """Return the frame sequence needed to switch the TNC into this mode.

        Typically a single mode-switch command, e.g.::

            return [build_command(b'PA')]   # PACKET

        Returns:
            List of complete, ready-to-send Host Mode frame bytes.
        """

    def get_init_frames(self) -> list[bytes]:
        """Return frames to upload mode-specific parameters after activation.

        Sent immediately after ``get_activate_frames()`` has been
        acknowledged.  Override in subclasses to upload parameters
        (e.g. MYCALL, TXDELAY, FRACK, …).

        Default implementation returns an empty list.

        Returns:
            List of complete, ready-to-send Host Mode frame bytes.
        """
        return []

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} active={self._active}>"