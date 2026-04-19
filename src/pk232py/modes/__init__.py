# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Mode registry — all supported operating modes.

``ALL_MODES`` is an ordered list of (name, class) tuples covering every
supported operating mode.  The order defines how modes appear in the UI.
"""

from __future__ import annotations

from .base_mode     import BaseMode
from .packet_hf     import HFPacketMode
from .packet_vhf    import VHFPacketMode
from .pactor        import PACTORMode
from .amtor         import AMTORMode
from .rtty_baudot   import BaudotRTTYMode
from .rtty_ascii    import ASCIIRTTYMode
from .morse         import MorseMode
from .navtex        import NAVTEXMode
from .tdm           import TDMMode
from .fax           import FAXMode
from .signal_analysis import SignalMode

__all__ = [
    "BaseMode",
    "HFPacketMode",
    "VHFPacketMode",
    "PACTORMode",
    "AMTORMode",
    "BaudotRTTYMode",
    "ASCIIRTTYMode",
    "MorseMode",
    "NAVTEXMode",
    "TDMMode",
    "FAXMode",
    "SignalMode",
    "ALL_MODES",
    "MODE_BY_NAME",
    "MODE_BY_COMMAND",
]

ALL_MODES: list[tuple[str, type[BaseMode]]] = [
    ("HF Packet",      HFPacketMode),
    ("VHF Packet",     VHFPacketMode),
    ("PACTOR",         PACTORMode),
    ("AMTOR",          AMTORMode),
    ("Baudot RTTY",    BaudotRTTYMode),
    ("ASCII RTTY",     ASCIIRTTYMode),
    ("CW / Morse",     MorseMode),
    ("NAVTEX",         NAVTEXMode),
    ("TDM",            TDMMode),
    ("FAX",            FAXMode),
    ("Signal",         SignalMode),
]

#: Lookup by mode name → class
MODE_BY_NAME: dict[str, type[BaseMode]] = {
    name: cls for name, cls in ALL_MODES
}

#: Lookup by TNC mnemonic → class
#: Note: HF Packet and VHF Packet share mnemonic b'PA';
#: VHF Packet is registered last so MODE_BY_COMMAND[b'PA'] returns VHFPacketMode.
#: Use MODE_BY_NAME for unambiguous lookup.
MODE_BY_COMMAND: dict[bytes, type[BaseMode]] = {}
for _name, _cls in reversed(ALL_MODES):
    if hasattr(_cls, 'mnemonic') and _cls.mnemonic:
        MODE_BY_COMMAND[_cls.mnemonic] = _cls