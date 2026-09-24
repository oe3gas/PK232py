# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Unit tests for pk232py.ui.dialogs.maildrop_dialog (P39.6).

Drives MailDropDialog against a FAKE MailDropSession (a QObject with the
same signal names, per the spec: "Sitzung gegen eine Attrappe von
MailDropSession") — no real serial channel, no worker thread. The
four-condition button/menu gate itself (has_maildrop/channel/mode/
connection) is tested in test_main_window_packet.py's TestMaildropGate,
since that gate lives in MainWindow, not this dialog.

Needs a QApplication; forced to the offscreen platform (see
test_packet_screen.py for why this is done at module level, before any
PyQt6 import).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox

from pk232py.config import MailDropConfig
from pk232py.maildrop.protocol import MailDropEntry
from pk232py.ui.dialogs.maildrop_dialog import MailDropDialog

_APP = QApplication.instance() or QApplication([])


class FakeSession(QObject):
    """A stand-in MailDropSession (P39.6) — same signal names, instrumented
    methods that just record the call instead of touching any channel."""

    state_changed = pyqtSignal(str)
    prompt_info = pyqtSignal(object)
    listing = pyqtSignal(list)
    message_read = pyqtSignal(object, str)
    stored = pyqtSignal(int)
    killed = pyqtSignal(int)
    failed = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple] = []

    def open(self) -> None:
        self.calls.append(("open",))

    def list(self) -> None:
        self.calls.append(("list",))

    def read(self, number: int) -> None:
        self.calls.append(("read", number))

    def kill(self, number: int) -> None:
        self.calls.append(("kill", number))

    def send(self, to, bbs, frm, mtype, subject, body) -> None:
        self.calls.append(("send", to, bbs, frm, mtype, subject, body))

    def leave(self) -> None:
        self.calls.append(("leave",))

    def abort(self) -> None:
        self.calls.append(("abort",))


class FakeSerial:
    is_connected = True
    is_host_mode = True
    tnc_release = "01.AUG.91"


class FakeChannelBar:
    def __init__(self) -> None:
        self._map: dict = {}

    def channel_map(self) -> dict:
        return self._map


_ENTRY_1 = MailDropEntry(
    number=1, mtype="P", read=False, size=61, to="OE3GAS", frm="PK232",
    bbs="", stamp=None, title="T119 personal",
)
_ENTRY_2 = MailDropEntry(
    number=2, mtype="P", read=False, size=43, to="OE3GAS", frm="DL1ABC",
    bbs="", stamp=None, title="T119 foreign from",
)


def _make_dialog(tmp_path, archive_enabled: bool = False) -> tuple:
    session = FakeSession()
    config = MailDropConfig(
        archive_enabled=archive_enabled,
        archive_path=str(tmp_path / "archive.db"),
    )
    dlg = MailDropDialog(
        FakeSerial(), FakeChannelBar(), "OE3GAS", config,
        session=session,
    )
    return dlg, session


class TestListingFillsTheList:

    def test_listing_populates_rows_and_tree(self, tmp_path):
        dlg, session = _make_dialog(tmp_path)
        session.listing.emit([_ENTRY_1, _ENTRY_2])
        assert len(dlg._rows) == 2
        assert dlg.tree.topLevelItemCount() == 2


class TestStoredTriggersRelist:

    def test_stored_calls_list_when_not_restoring(self, tmp_path):
        dlg, session = _make_dialog(tmp_path)
        session.stored.emit(3)
        assert ("list",) in session.calls


class TestFailedShowsStatusAndStaysOpen:

    def test_failed_sets_status_line(self, tmp_path):
        dlg, session = _make_dialog(tmp_path)
        session.failed.emit("no mailbox prompt after MDCHECK")
        assert dlg.lbl_status.text() == "no mailbox prompt after MDCHECK"

    def test_failed_does_not_close_the_dialog(self, tmp_path):
        dlg, session = _make_dialog(tmp_path)
        closed = []
        dlg.close = lambda: closed.append(True)  # type: ignore[method-assign]
        session.failed.emit("boom")
        assert closed == []
        assert dlg.result() != QDialog.DialogCode.Accepted


class TestCloseConfirmation:

    def test_cancel_keeps_session_open(self, tmp_path, monkeypatch):
        dlg, session = _make_dialog(tmp_path)
        session.state_changed.emit("ACTIVE")
        monkeypatch.setattr(
            QMessageBox, "question",
            staticmethod(lambda *a, **k: QMessageBox.StandardButton.No),
        )
        dlg.reject()
        assert ("leave",) not in session.calls
        assert dlg.result() != QDialog.DialogCode.Accepted

    def test_confirm_calls_leave_and_closes_only_after_closed(
        self, tmp_path, monkeypatch,
    ):
        dlg, session = _make_dialog(tmp_path)
        session.state_changed.emit("ACTIVE")
        monkeypatch.setattr(
            QMessageBox, "question",
            staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
        )
        dlg.reject()
        assert ("leave",) in session.calls
        # leave() has been asked for, but the session has not reported
        # CLOSED yet - the dialog must still be open.
        assert dlg.result() != QDialog.DialogCode.Accepted

        session.state_changed.emit("CLOSING")
        assert dlg.result() != QDialog.DialogCode.Accepted

        session.state_changed.emit("CLOSED")
        assert dlg.result() == QDialog.DialogCode.Accepted

    def test_failed_while_ending_leaves_dialog_open_with_text(
        self, tmp_path, monkeypatch,
    ):
        dlg, session = _make_dialog(tmp_path)
        session.state_changed.emit("ACTIVE")
        monkeypatch.setattr(
            QMessageBox, "question",
            staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
        )
        dlg.reject()
        session.failed.emit(
            "TNC is in verbose mode -- Host Mode re-entry did not complete"
        )
        session.state_changed.emit("FAILED")
        assert dlg.result() != QDialog.DialogCode.Accepted
        assert "Host Mode re-entry" in dlg.lbl_status.text()
        # The dialog is never shown in this test, so isVisible() always
        # reads False regardless of setVisible() - isHidden() reflects
        # the widget's own explicit visibility flag instead.
        assert not dlg.btn_retry.isHidden()


class TestArchiveGating:

    def test_empty_archive_shows_hint_and_locks_restore(self, tmp_path):
        dlg, session = _make_dialog(tmp_path, archive_enabled=True)
        session.state_changed.emit("ACTIVE")
        session.listing.emit([_ENTRY_1])
        assert dlg.lbl_archive_hint.text() != ""
        assert not dlg.btn_restore.isEnabled()

    def test_archive_disabled_locks_both_buttons_with_hint(self, tmp_path):
        dlg, session = _make_dialog(tmp_path, archive_enabled=False)
        session.state_changed.emit("ACTIVE")
        session.listing.emit([_ENTRY_1])
        assert dlg._archive is None
        assert not dlg.btn_sync.isEnabled()
        assert not dlg.btn_restore.isEnabled()
        assert "Parameters" in dlg.btn_sync.toolTip()
        assert "Parameters" in dlg.btn_restore.toolTip()
