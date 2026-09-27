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


class TestEndSessionSync:
    """P59, C.2/C.4 - _end_session() is the ONE path out of an ACTIVE
    session; when archive_sync is 'on_session_end' it collects every
    TNC-only message first, then leaves - via btn_end OR a confirmed
    window-close gesture, so the two can never disagree."""

    def _make_on_session_end(self, tmp_path):
        session = FakeSession()
        config = MailDropConfig(
            archive_enabled=True, archive_path=str(tmp_path / "archive.db"),
            archive_sync="on_session_end",
        )
        dlg = MailDropDialog(
            FakeSerial(), FakeChannelBar(), "OE3GAS", config, session=session,
        )
        session.state_changed.emit("ACTIVE")
        session.listing.emit([_ENTRY_1, _ENTRY_2])   # both TNC-only
        return dlg, session

    def test_btn_end_reads_every_tnc_only_message_then_leaves(self, tmp_path):
        dlg, session = self._make_on_session_end(tmp_path)
        dlg.btn_end.click()
        assert ("read", 1) in session.calls
        session.message_read.emit(_ENTRY_1, "body one")
        assert ("read", 2) in session.calls
        session.message_read.emit(_ENTRY_2, "body two")
        # Order matters: both reads before the leave, never after.
        tail = [c for c in session.calls if c[0] in ("read", "leave")]
        assert tail == [("read", 1), ("read", 2), ("leave",)]

    def test_confirmed_close_gesture_takes_the_same_path(self, tmp_path, monkeypatch):
        dlg, session = self._make_on_session_end(tmp_path)
        monkeypatch.setattr(
            QMessageBox, "question",
            staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
        )
        dlg.reject()
        session.message_read.emit(_ENTRY_1, "body one")
        session.message_read.emit(_ENTRY_2, "body two")
        tail = [c for c in session.calls if c[0] in ("read", "leave")]
        assert tail == [("read", 1), ("read", 2), ("leave",)]

    def test_manual_sync_setting_skips_the_collection(self, tmp_path):
        # Default MailDropConfig.archive_sync is "manual" - P59 must not
        # change this default's behaviour at all.
        session = FakeSession()
        config = MailDropConfig(
            archive_enabled=True, archive_path=str(tmp_path / "archive.db"),
        )
        assert config.archive_sync == "manual"
        dlg = MailDropDialog(
            FakeSerial(), FakeChannelBar(), "OE3GAS", config, session=session,
        )
        session.state_changed.emit("ACTIVE")
        session.listing.emit([_ENTRY_1, _ENTRY_2])
        dlg.btn_end.click()
        assert [c for c in session.calls if c[0] == "read"] == []
        assert ("leave",) in session.calls

    def test_sync_failure_mid_queue_still_leaves(self, tmp_path):
        dlg, session = self._make_on_session_end(tmp_path)
        dlg.btn_end.click()
        session.message_read.emit(_ENTRY_1, "body one")   # 1 of 2 archived
        session.failed.emit("TNC did not answer R 2")
        assert ("leave",) in session.calls
        assert "Sync incomplete: 1 of 2 archived" in dlg.lbl_status.text()


class TestManualRestoreScope:
    """P59, C.3 - the manual "Restore to TNC" button is filtered by
    archive_restore_scope, the same filter_restore_scope() the automatic
    trigger uses."""

    def _make_with_archive_only(self, tmp_path, scope: str):
        session = FakeSession()
        config = MailDropConfig(
            archive_enabled=True, archive_path=str(tmp_path / "archive.db"),
            archive_restore_scope=scope,
        )
        dlg = MailDropDialog(
            FakeSerial(), FakeChannelBar(), "OE3GAS", config, session=session,
        )
        # Two archive-only messages, one already read at archiving time.
        dlg._archive.add(_ENTRY_1, "body one")
        read_entry = MailDropEntry(
            number=_ENTRY_2.number, mtype=_ENTRY_2.mtype, read=True,
            size=_ENTRY_2.size, to=_ENTRY_2.to, frm=_ENTRY_2.frm,
            bbs=_ENTRY_2.bbs, stamp=_ENTRY_2.stamp, title=_ENTRY_2.title,
        )
        dlg._archive.add(read_entry, "body two")
        session.state_changed.emit("ACTIVE")
        session.listing.emit([])   # nothing in the TNC - both archive-only
        return dlg, session

    def test_unread_scope_never_restores_the_already_read_message(self, tmp_path):
        dlg, session = self._make_with_archive_only(tmp_path, "unread")
        dlg.btn_restore.click()
        assert [c[5] for c in session.calls if c[0] == "send"] == ["T119 personal"]
        session.stored.emit(999)   # let the (one-item) queue drain
        # No SECOND send for the already-read message once the queue is
        # empty - proves it was excluded, not merely sent later.
        assert [c[5] for c in session.calls if c[0] == "send"] == ["T119 personal"]
        assert dlg._pending_op is None

    def test_none_scope_locks_the_button(self, tmp_path):
        dlg, _session = self._make_with_archive_only(tmp_path, "none")
        assert not dlg.btn_restore.isEnabled()
        assert "none" in dlg.btn_restore.toolTip()


class TestAutoRestore:
    """P59, C.4 - MainWindow opens this dialog with auto_restore=True
    after detecting the TNC came up at factory defaults."""

    def _make_auto(self, tmp_path, scope: str = "all"):
        session = FakeSession()
        config = MailDropConfig(
            archive_enabled=True, archive_path=str(tmp_path / "archive.db"),
            archive_restore_scope=scope,
        )
        dlg = MailDropDialog(
            FakeSerial(), FakeChannelBar(), "OE3GAS", config, session=session,
            auto_restore=True,
        )
        return dlg, session

    def test_opens_the_session_itself_without_any_click(self, tmp_path):
        dlg, session = self._make_auto(tmp_path)
        assert ("open",) in session.calls

    def test_sends_every_candidate_then_leaves_no_sync(self, tmp_path):
        dlg, session = self._make_auto(tmp_path)
        dlg._archive.add(_ENTRY_1, "body one")
        dlg._archive.add(_ENTRY_2, "body two")
        session.state_changed.emit("ACTIVE")
        session.listing.emit([])   # TNC is empty - both are candidates

        sent = [c for c in session.calls if c[0] == "send"]
        assert len(sent) == 1
        session.stored.emit(101)
        sent = [c for c in session.calls if c[0] == "send"]
        assert len(sent) == 2
        session.stored.emit(102)

        assert ("leave",) in session.calls
        assert [c for c in session.calls if c[0] == "read"] == []
        assert dlg._closing_confirmed is True

    def test_empty_candidate_list_ends_immediately(self, tmp_path):
        dlg, session = self._make_auto(tmp_path)   # empty archive
        session.state_changed.emit("ACTIVE")
        session.listing.emit([])
        assert [c for c in session.calls if c[0] == "send"] == []
        assert ("leave",) in session.calls

    def test_closing_mid_restore_finishes_current_then_leaves(
        self, tmp_path, monkeypatch,
    ):
        dlg, session = self._make_auto(tmp_path)
        dlg._archive.add(_ENTRY_1, "body one")
        dlg._archive.add(_ENTRY_2, "body two")
        session.state_changed.emit("ACTIVE")
        session.listing.emit([])
        assert len([c for c in session.calls if c[0] == "send"]) == 1

        monkeypatch.setattr(
            QMessageBox, "question",
            staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
        )
        dlg.reject()   # Esc/X during the restore
        # The in-flight send is not aborted (no session.abort() call).
        assert ("abort",) not in session.calls
        session.stored.emit(101)   # the in-flight message finishes...
        # ...but no SECOND send follows - the queue was cleared.
        assert len([c for c in session.calls if c[0] == "send"]) == 1
        assert ("leave",) in session.calls


class TestRestoreFailurePath:
    """P60, B.2 - a restore's continuation must run on FAILURE exactly
    when it is the way OUT of the session (auto-restore, or a stopped
    auto-restore whose continuation _request_close() switched to
    _end_session), and must NOT run for a manual restore - unchanged
    from before P59 ever introduced continuations at all. Regresses the
    dead by-identity comparison against the leave continuation that
    docs/P60_Archive_Restore_Oneshot_Fix_Spec.md B.2 found (neither
    _end_session() nor auto-restore ever passes literally that bound
    method, so the old check never actually fired for either)."""

    def _make_auto(self, tmp_path, scope: str = "all"):
        session = FakeSession()
        config = MailDropConfig(
            archive_enabled=True, archive_path=str(tmp_path / "archive.db"),
            archive_restore_scope=scope,
        )
        dlg = MailDropDialog(
            FakeSerial(), FakeChannelBar(), "OE3GAS", config, session=session,
            auto_restore=True,
        )
        return dlg, session

    def _make_with_archive_only(self, tmp_path, scope: str = "all"):
        session = FakeSession()
        config = MailDropConfig(
            archive_enabled=True, archive_path=str(tmp_path / "archive.db"),
            archive_restore_scope=scope,
        )
        dlg = MailDropDialog(
            FakeSerial(), FakeChannelBar(), "OE3GAS", config, session=session,
        )
        dlg._archive.add(_ENTRY_1, "body one")
        dlg._archive.add(_ENTRY_2, "body two")
        session.state_changed.emit("ACTIVE")
        session.listing.emit([])   # nothing in the TNC - both archive-only
        return dlg, session

    def test_auto_restore_first_send_failure_calls_leave_with_incomplete_status(
        self, tmp_path,
    ):
        dlg, session = self._make_auto(tmp_path)
        dlg._archive.add(_ENTRY_1, "body one")
        dlg._archive.add(_ENTRY_2, "body two")
        session.state_changed.emit("ACTIVE")
        session.listing.emit([])   # both are candidates
        assert len([c for c in session.calls if c[0] == "send"]) == 1

        session.failed.emit("mailbox full")

        assert ("leave",) in session.calls
        # No second send once the queue was cleared on failure.
        assert len([c for c in session.calls if c[0] == "send"]) == 1
        assert "Restore incomplete: 0 of 2 restored" in dlg.lbl_status.text()

    def test_closing_mid_auto_restore_then_failed_still_calls_leave(
        self, tmp_path, monkeypatch,
    ):
        dlg, session = self._make_auto(tmp_path)
        dlg._archive.add(_ENTRY_1, "body one")
        dlg._archive.add(_ENTRY_2, "body two")
        session.state_changed.emit("ACTIVE")
        session.listing.emit([])
        assert len([c for c in session.calls if c[0] == "send"]) == 1

        monkeypatch.setattr(
            QMessageBox, "question",
            staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
        )
        dlg.reject()   # Esc/X during the restore -> continuation becomes
                       # _end_session, not the original _finish_auto_restore

        session.failed.emit("mailbox full")

        assert ("leave",) in session.calls
        assert len([c for c in session.calls if c[0] == "send"]) == 1

    def test_manual_restore_failure_does_not_call_leave(self, tmp_path):
        dlg, session = self._make_with_archive_only(tmp_path)
        dlg.btn_restore.click()
        assert len([c for c in session.calls if c[0] == "send"]) == 1

        session.failed.emit("mailbox full")

        # Unchanged from before P59/P60: a manual restore's failure never
        # ends the session on its own - the operator is right there.
        assert ("leave",) not in session.calls


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
