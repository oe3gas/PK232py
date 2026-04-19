# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Communication layer — serial port, Host Mode protocol, KISS."""

from .serial_manager import SerialManager
from .frame import HostFrame, FrameKind, FrameParser, build_command, build_data
from .constants import SerialDefaults, HOSTMODE_INIT_CMDS, HOSTMODE_PREAMBLE

__all__ = [
    "SerialManager",
    "HostFrame",
    "FrameKind",
    "FrameParser",
    "build_command",
    "build_data",
    "SerialDefaults",
    "HOSTMODE_INIT_CMDS",
    "HOSTMODE_PREAMBLE",
]