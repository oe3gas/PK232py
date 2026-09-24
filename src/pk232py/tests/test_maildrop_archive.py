# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Unit tests for pk232py.maildrop.archive (P38).

No Qt, no serial I/O - pure SQLite storage, so these run without any
hardware or PyQt6 import. Fixture values are the real personal message
from hw_logs/20260924_181446_maildrop_session.log (T119, Device B).
"""

from __future__ import annotations

from pk232py.config import MailDropConfig
from pk232py.maildrop.archive import MailDropArchive, open_archive
from pk232py.maildrop.protocol import MailDropEntry

_PERSONAL = MailDropEntry(
    number=1, mtype="P", read=False, size=61,
    to="OE3GAS", frm="PK232", bbs="", stamp=None,
    title="T119 personal",
)
_PERSONAL_BODY = "hello from the maildrop_session harness"

_FOREIGN = MailDropEntry(
    number=2, mtype="P", read=False, size=43,
    to="OE3GAS", frm="DL1ABC", bbs="", stamp=None,
    title="T119 foreign from",
)
_FOREIGN_BODY = "foreign FROM test"


class TestAdd:

    def test_new_message_is_new(self, tmp_path):
        with MailDropArchive(tmp_path / "archive.db") as archive:
            archive_id, is_new = archive.add(_PERSONAL, _PERSONAL_BODY, device="01.AUG.91")
            assert is_new is True
            assert archive_id > 0

    def test_adding_the_same_message_twice_is_not_new(self, tmp_path):
        with MailDropArchive(tmp_path / "archive.db") as archive:
            id1, new1 = archive.add(_PERSONAL, _PERSONAL_BODY)
            id2, new2 = archive.add(_PERSONAL, _PERSONAL_BODY)
            assert new1 is True
            assert new2 is False
            assert id1 == id2
            assert archive.count() == 1

    def test_a_different_tnc_stamp_still_deduplicates(self, tmp_path):
        # The TNC stamp is set at store time and would differ after a
        # restore-then-collect round trip (P38) - it must not defeat
        # duplicate detection.
        restamped = MailDropEntry(
            number=_PERSONAL.number, mtype=_PERSONAL.mtype,
            read=_PERSONAL.read, size=_PERSONAL.size, to=_PERSONAL.to,
            frm=_PERSONAL.frm, bbs=_PERSONAL.bbs,
            stamp="24-Sep-26  18:14", title=_PERSONAL.title,
        )
        with MailDropArchive(tmp_path / "archive.db") as archive:
            id1, _ = archive.add(_PERSONAL, _PERSONAL_BODY)
            id2, is_new = archive.add(restamped, _PERSONAL_BODY)
            assert is_new is False
            assert id1 == id2

    def test_different_messages_both_stored(self, tmp_path):
        with MailDropArchive(tmp_path / "archive.db") as archive:
            archive.add(_PERSONAL, _PERSONAL_BODY)
            archive.add(_FOREIGN, _FOREIGN_BODY)
            assert archive.count() == 2

    def test_stored_fields_match_the_entry(self, tmp_path):
        with MailDropArchive(tmp_path / "archive.db") as archive:
            archive.add(_PERSONAL, _PERSONAL_BODY, device="01.AUG.91")
            [msg] = archive.all()
            assert msg.mtype == "P"
            assert msg.read_flag is False
            assert msg.to_call == "OE3GAS"
            assert msg.from_call == "PK232"
            assert msg.bbs == ""
            assert msg.tnc_stamp is None
            assert msg.size == 61
            assert msg.subject == "T119 personal"
            assert msg.body == _PERSONAL_BODY
            assert msg.tnc_number == 1
            assert msg.device == "01.AUG.91"


class TestReadDeleteMarkRead:

    def test_mark_read(self, tmp_path):
        with MailDropArchive(tmp_path / "archive.db") as archive:
            archive_id, _ = archive.add(_PERSONAL, _PERSONAL_BODY)
            archive.mark_read(archive_id)
            [msg] = archive.all()
            assert msg.read_flag is True

    def test_delete(self, tmp_path):
        with MailDropArchive(tmp_path / "archive.db") as archive:
            archive_id, _ = archive.add(_PERSONAL, _PERSONAL_BODY)
            archive.delete(archive_id)
            assert archive.count() == 0

    def test_count(self, tmp_path):
        with MailDropArchive(tmp_path / "archive.db") as archive:
            assert archive.count() == 0
            archive.add(_PERSONAL, _PERSONAL_BODY)
            assert archive.count() == 1


class TestMissingInTnc:

    def test_message_gone_from_the_tnc_is_reported(self, tmp_path):
        with MailDropArchive(tmp_path / "archive.db") as archive:
            archive.add(_PERSONAL, _PERSONAL_BODY)
            archive.add(_FOREIGN, _FOREIGN_BODY)
            # Only the foreign one is still in the (simulated) mailbox -
            # the personal one was killed on the TNC.
            missing = archive.missing_in_tnc([(_FOREIGN, _FOREIGN_BODY)])
            assert [m.subject for m in missing] == ["T119 personal"]

    def test_nothing_missing_when_everything_still_present(self, tmp_path):
        with MailDropArchive(tmp_path / "archive.db") as archive:
            archive.add(_PERSONAL, _PERSONAL_BODY)
            missing = archive.missing_in_tnc([(_PERSONAL, _PERSONAL_BODY)])
            assert missing == []

    def test_renumbering_after_a_power_cycle_does_not_confuse_the_match(self, tmp_path):
        # Same message, but the TNC would hand out message number 1
        # again after a power-cycle (CLAUDE.md) - comparison must go by
        # fingerprint, never by tnc_number.
        renumbered = MailDropEntry(
            number=1, mtype=_FOREIGN.mtype, read=_FOREIGN.read,
            size=_FOREIGN.size, to=_FOREIGN.to, frm=_FOREIGN.frm,
            bbs=_FOREIGN.bbs, stamp=_FOREIGN.stamp, title=_FOREIGN.title,
        )
        with MailDropArchive(tmp_path / "archive.db") as archive:
            archive.add(_FOREIGN, _FOREIGN_BODY)
            missing = archive.missing_in_tnc([(renumbered, _FOREIGN_BODY)])
            assert missing == []


class TestOpenArchive:

    def test_disabled_creates_no_file(self, tmp_path):
        db_path = tmp_path / "archive.db"
        config = MailDropConfig(archive_enabled=False, archive_path=str(db_path))
        archive = open_archive(config)
        assert archive is None
        assert not db_path.exists()

    def test_enabled_creates_the_file(self, tmp_path):
        db_path = tmp_path / "archive.db"
        config = MailDropConfig(archive_enabled=True, archive_path=str(db_path))
        archive = open_archive(config)
        try:
            assert archive is not None
            assert db_path.exists()
        finally:
            archive.close()

    def test_enabled_expands_user_path(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        config = MailDropConfig(archive_enabled=True, archive_path="~/archive.db")
        archive = open_archive(config)
        try:
            assert (tmp_path / "archive.db").exists()
        finally:
            archive.close()
