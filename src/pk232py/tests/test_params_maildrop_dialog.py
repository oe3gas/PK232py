# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Unit tests for MailDropParamsDialog.set_locked() (P37 Teil D.3).

Needs a QApplication; forced to the offscreen platform (see
test_packet_screen.py for why this is done at module level, before any
PyQt6 import).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from pk232py.ui.dialogs.params_maildrop import MailDropParamsDialog

_app = QApplication.instance() or QApplication([])


class TestSetLocked:

    def test_default_unlocked(self):
        dlg = MailDropParamsDialog()
        assert dlg._le_homebbs.isEnabled()
        assert dlg._chk_maildrop.isEnabled()

    def test_locked_disables_every_field_never_hides(self):
        dlg = MailDropParamsDialog()
        dlg.set_locked(True, "This firmware has no MailDrop")
        for w in [
            dlg._le_homebbs, dlg._le_mymail, dlg._sb_lastmsg,
            dlg._le_mdprompt, dlg._le_tmprompt, dlg._te_mtext,
            dlg._chk_third_party, dlg._chk_kilonfwd, dlg._chk_maildrop,
            dlg._chk_mdmon, dlg._chk_mmsg, dlg._chk_tmail,
        ]:
            assert not w.isEnabled()
            # Locking must never hide a field - set_locked() only ever
            # touches setEnabled()/setToolTip(), so hidden() stays False.
            assert not w.isHidden()
            assert w.toolTip() == "This firmware has no MailDrop"

    def test_unlock_restores_fields_and_clears_tooltip(self):
        dlg = MailDropParamsDialog()
        dlg.set_locked(True, "This firmware has no MailDrop")
        dlg.set_locked(False)
        assert dlg._le_homebbs.isEnabled()
        assert dlg._chk_maildrop.isEnabled()
        assert dlg._le_homebbs.toolTip() == ""
