# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Mode registry — all supported operating modes."""

from __future__ import annotations

from .base_mode       import BaseMode
from .packet_hf       import HFPacketMode
from .packet_vhf      import VHFPacketMode
from .pactor          import PACTORMode
from .amtor           import AMTORMode, AMTORFECMode
from .rtty_baudot     import BaudotRTTYMode
from .rtty_ascii      import ASCIIRTTYMode
from .morse           import MorseMode
from .navtex          import NAVTEXMode
from .tdm             import TDMMode
from .fax             import FAXMode
from .signal_analysis import SignalMode
from .maildrop_mode   import MailDropMode

__all__ = [
    "BaseMode",
    "HFPacketMode", "VHFPacketMode",
    "PACTORMode",
    "AMTORMode", "AMTORFECMode",
    "BaudotRTTYMode", "ASCIIRTTYMode",
    "MorseMode", "NAVTEXMode",
    "TDMMode", "FAXMode", "SignalMode",
    "MailDropMode",
    "ALL_MODES", "MODE_BY_NAME", "MODE_BY_COMMAND",
]

ALL_MODES: list[tuple[str, type[BaseMode]]] = [
    ("HF Packet",     HFPacketMode),
    ("VHF Packet",    VHFPacketMode),
    ("PACTOR",        PACTORMode),
    ("AMTOR ARQ",     AMTORMode),
    ("AMTOR FEC",     AMTORFECMode),
    ("Baudot RTTY",   BaudotRTTYMode),
    ("ASCII RTTY",    ASCIIRTTYMode),
    ("CW / Morse",    MorseMode),
    ("NAVTEX",        NAVTEXMode),
    ("TDM",           TDMMode),
    ("FAX",           FAXMode),
    ("Signal (SIAM)", SignalMode),
    ("MailDrop",      MailDropMode),
]

MODE_BY_NAME: dict[str, type[BaseMode]] = {
    name: cls for name, cls in ALL_MODES
}

MODE_BY_COMMAND: dict[bytes, type[BaseMode]] = {}
for _name, _cls in reversed(ALL_MODES):
    if hasattr(_cls, 'host_command') and _cls.host_command:
        MODE_BY_COMMAND[_cls.host_command] = _cls