# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""pk232py.ui.dialogs — Configuration dialogs."""

from .params_hf      import PacketParamsDialog
from .params_misc    import MiscParamsDialog
from .params_pactor  import PACTORParamsDialog
from .params_amtor   import AMTORParamsDialog
from .params_baudot  import BaudotParamsDialog
from .params_maildrop import MailDropParamsDialog

# NB: the active TNC-config dialog is `TncConfigDialog` in
# `pk232py/ui/tnc_config_dialog.py` (used by MainWindow). The old
# `dialogs/tnc_config.py::TNCConfigDialog` was a duplicate, never instantiated,
# and was removed 2026-06-23 — do not re-add it here.

__all__ = [
    "PacketParamsDialog",
    "MiscParamsDialog",
    "PACTORParamsDialog",
    "AMTORParamsDialog",
    "BaudotParamsDialog",
    "MailDropParamsDialog",
]