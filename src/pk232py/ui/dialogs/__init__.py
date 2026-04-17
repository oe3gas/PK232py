# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""pk232py.ui.dialogs — Configuration dialogs."""

from .tnc_config     import TNCConfigDialog
from .params_hf      import HFPacketParamsDialog
from .params_misc    import MiscParamsDialog
from .params_pactor  import PACTORParamsDialog
from .params_amtor   import AMTORParamsDialog
from .params_baudot  import BaudotParamsDialog
from .params_maildrop import MailDropParamsDialog

__all__ = [
    "TNCConfigDialog",
    "HFPacketParamsDialog",
    "MiscParamsDialog",
    "PACTORParamsDialog",
    "AMTORParamsDialog",
    "BaudotParamsDialog",
    "MailDropParamsDialog",
]