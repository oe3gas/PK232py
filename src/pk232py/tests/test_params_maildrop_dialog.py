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

    def test_archive_widgets_never_locked_by_set_locked(self):
        # Archive settings are PC-side, independent of TNC MailDrop
        # capability (P38) - set_locked() must not touch them.
        dlg = MailDropParamsDialog()
        dlg.set_locked(True, "This firmware has no MailDrop")
        assert dlg._chk_archive_enabled.isEnabled()
        assert dlg._le_archive_path.isEnabled()


class TestArchiveSection:
    """P38.1 - local MailDrop archive settings section."""

    def test_defaults_match_config(self):
        dlg = MailDropParamsDialog()
        values = dlg.get_values()
        assert values["archive_enabled"] is False
        assert values["archive_path"] == "~/.pk232py/maildrop_archive.db"
        assert values["archive_sync"] == "manual"
        assert values["archive_restore"] == "never"
        assert values["archive_restore_scope"] == "unread"

    def test_round_trips_through_set_and_get_values(self):
        dlg = MailDropParamsDialog()
        dlg.set_values(
            archive_enabled=True,
            archive_path="/tmp/archive.db",
            archive_sync="on_session_end",
            archive_restore="auto",
            archive_restore_scope="all",
        )
        values = dlg.get_values()
        assert values["archive_enabled"] is True
        assert values["archive_path"] == "/tmp/archive.db"
        assert values["archive_sync"] == "on_session_end"
        assert values["archive_restore"] == "auto"
        assert values["archive_restore_scope"] == "all"

    def test_auto_warning_hidden_by_default_shown_for_auto(self):
        # The dialog is never shown in this test, so isVisible() would
        # always read False regardless of setVisible() (a real ancestor
        # chain is required for that) - isHidden() reflects the widget's
        # own explicit visibility flag instead.
        dlg = MailDropParamsDialog()
        assert dlg._lbl_archive_auto_warn.isHidden()
        dlg.set_values(archive_restore="auto")
        assert not dlg._lbl_archive_auto_warn.isHidden()
        dlg.set_values(archive_restore="never")
        assert dlg._lbl_archive_auto_warn.isHidden()
