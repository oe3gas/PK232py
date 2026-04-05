# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Abstract base class for all PK-232 operating modes."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pk232py.comm.hostmode import HostFrame

logger = logging.getLogger(__name__)


class BaseMode(ABC):
    """Abstract base class for all PK-232 operating modes.

    Subclasses implement the mode-specific Host Mode command sequences
    and handle incoming frames from the TNC.

    The ``name`` and ``host_command`` class attributes must be set
    by each subclass.
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
        """Called when the user switches to this mode.

        Returns the Host Mode command bytes to send to the TNC.
        Override to add mode-specific initialisation.
        """
        self._active = True
        logger.info("Mode activated: %s", self.name)

    def deactivate(self) -> None:
        """Called when the user switches away from this mode."""
        self._active = False
        logger.info("Mode deactivated: %s", self.name)

    @abstractmethod
    def handle_frame(self, frame: "HostFrame") -> None:
        """Process an incoming Host Mode frame addressed to this mode.

        Args:
            frame: Decoded Host Mode frame from the TNC.
        """

    @abstractmethod
    def get_activate_frames(self) -> list[bytes]:
        """Return the sequence of raw frame bytes needed to activate this mode.

        Returns:
            List of complete Host Mode frames to send to the TNC.
        """

    def get_parameter_frames(self) -> list[bytes]:
        """Return Host Mode frames to upload mode-specific parameters.

        Override in subclasses to upload parameters after activation.
        Default implementation returns an empty list.

        Returns:
            List of complete Host Mode frames to send to the TNC.
        """
        return []

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} active={self._active}>"
