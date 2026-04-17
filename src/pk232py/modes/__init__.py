# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Operating mode layer — one module per TNC operating mode."""

from __future__ import annotations

from .base_mode        import BaseMode
from .packet_hf        import HFPacketMode
from .packet_vhf       import VHFPacketMode
from .pactor           import PACTORMode
from .amtor            import AMTORMode
from .rtty_baudot      import BaudotRTTYMode
from .rtty_ascii       import ASCIIRTTYMode
from .morse            import MorseMode
from .navtex           import NAVTEXMode
from .tdm              import TDMMode
from .fax              import FAXMode
from .signal_analysis  import SignalMode

__all__ = [
    "BaseMode",
    "HFPacketMode", "VHFPacketMode",
    "PACTORMode", "AMTORMode",
    "BaudotRTTYMode", "ASCIIRTTYMode",
    "MorseMode", "NAVTEXMode",
    "TDMMode", "FAXMode", "SignalMode",
    "ALL_MODES", "MODE_BY_NAME", "MODE_BY_COMMAND",
]

ALL_MODES: list[tuple[str, type[BaseMode]]] = [
    # v1.0
    ("HF Packet",   HFPacketMode),
    ("VHF Packet",  VHFPacketMode),
    ("PACTOR",      PACTORMode),
    ("AMTOR",       AMTORMode),
    ("Baudot RTTY", BaudotRTTYMode),
    ("ASCII RTTY",  ASCIIRTTYMode),
    # v1.1
    ("CW/Morse",    MorseMode),
    ("NAVTEX",      NAVTEXMode),
    # v1.2
    ("TDM",         TDMMode),
    ("FAX",         FAXMode),
    ("Signal",      SignalMode),
]

MODE_BY_NAME: dict[str, type[BaseMode]] = {
    name: cls for name, cls in ALL_MODES
}

# HF Packet wins for b'PA' (more common than VHF Packet)
MODE_BY_COMMAND: dict[bytes, type[BaseMode]] = {}
for _name, _cls in reversed(ALL_MODES):
    MODE_BY_COMMAND[_cls.host_command] = _cls