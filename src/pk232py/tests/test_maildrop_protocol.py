# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Unit tests for pk232py.maildrop.protocol (P27.1/P27.4).

Fixtures are copied verbatim from the real MailDrop hardware transcripts
in hw_logs/ (22./23.09.2026 — 20260922_184337_maildrop.log = round 1,
20260922_191657_maildrop.log = round 2, 20260922_200013_maildrop.log =
round 3), converting each `text=` rendering's <CR>/<LF> markers back to
'\\r\\n'. No fixture was invented — where a shape is documented in
CLAUDE.md but never actually seen on this hardware (e.g. '*** No free
memory'), that is noted on the fixture itself.
"""

from __future__ import annotations

from pk232py.maildrop import protocol


# ===========================================================================
# find_prompt
# ===========================================================================

class TestFindPrompt:
    def test_prompt_with_no_mail(self):
        # hw_logs/20260922_184337_maildrop.log, MDCHECK response.
        text = (
            "MDCHECK\r\n(AEA PK-232M)  18536 free  (B,E,K,L,R,S) >\r\n"
        )
        info = protocol.find_prompt(text)
        assert info is not None
        assert info.free == 18536
        assert info.commands == "B,E,K,L,R,S"
        assert info.have_mail is False

    def test_prompt_with_mail_waiting(self):
        # hw_logs/20260922_191657_maildrop.log, round 2 MDCHECK response.
        text = (
            "MDCHECK\r\nYou have mail.\r\n"
            "(AEA PK-232M)  18452 free  (B,E,K,L,R,S) >\r\n"
        )
        info = protocol.find_prompt(text)
        assert info is not None
        assert info.free == 18452
        assert info.have_mail is True

    def test_prompt_with_interleaved_siam_line(self):
        # hw_logs/20260922_154026_maildrop.log: a SIAM result fragment
        # trailed the prompt in the same response (SIAM keeps analysing
        # continuously and writes into whatever else is happening,
        # CLAUDE.md P21) - find_prompt() must not be thrown off by it.
        text = (
            "h\r\n*** What?\r\n(AEA PK-232M)  18536 free  (B,E,K,L,R,S) >\r\n"
            "0.78: 50 baud, "
        )
        info = protocol.find_prompt(text)
        assert info is not None
        assert info.free == 18536

    def test_no_prompt_returns_none(self):
        assert protocol.find_prompt("Subject:\r\n") is None
        assert protocol.find_prompt("") is None


# ===========================================================================
# classify
# ===========================================================================

class TestClassify:
    def test_cmd_prompt(self):
        assert protocol.classify("b\r\ncmd:") == "cmd"

    def test_mailbox_prompt(self):
        text = "l\r\n*** Message not found.\r\n(AEA PK-232M)  18536 free  (B,E,K,L,R,S) >\r\n"
        assert protocol.classify(text) == "prompt"

    def test_subject_prompt(self):
        text = "s oe3gas#\r\nSubject:\r\n"
        assert protocol.classify(text) == "subject"

    def test_body_prompt(self):
        text = (
            "test 1\r\nEnter message, ^Z (CTRL-Z) or /EX to end\r\n\r\n"
        )
        assert protocol.classify(text) == "body"

    def test_error(self):
        assert protocol.classify("r2\r\n*** Not enough\r\n") == "error"

    def test_unknown(self):
        assert protocol.classify("erste test-nachricht.\r\n") == "unknown"


# ===========================================================================
# parse_error
# ===========================================================================

class TestParseError:
    def test_what(self):
        # hw_logs/20260922_154026_maildrop.log
        text = "h\r\n*** What?\r\n(AEA PK-232M)  18536 free  (B,E,K,L,R,S) >\r\n"
        assert protocol.parse_error(text) == "*** What?"

    def test_not_enough(self):
        # hw_logs/20260922_200013_maildrop.log ('r2' without a space)
        text = "r2\r\n*** Not enough\r\n(AEA PK-232M)  18284 free  (B,E,K,L,R,S) >\r\n"
        assert protocol.parse_error(text) == "*** Not enough"

    def test_no_free_memory(self):
        # Never triggered on real hardware - documented STABO/TRM error
        # text (CLAUDE.md), same '*** ' shape as the other two above.
        text = "s oe3gas\r\n*** No free memory\r\n(AEA PK-232M)  0 free  (B,E,K,L,R,S) >\r\n"
        assert protocol.parse_error(text) == "*** No free memory"

    def test_done_is_success_not_an_error(self):
        # hw_logs/20260922_184337_maildrop.log ('K 1')
        text = "K 1\r\n*** Done.\r\n(AEA PK-232M)  18452 free  (B,E,K,L,R,S) >\r\n"
        assert protocol.parse_error(text) is None

    def test_no_error_at_all(self):
        text = "l\r\n*** Message not found.\r\n(AEA PK-232M)  18536 free  (B,E,K,L,R,S) >\r\n"
        # Not one of the KNOWN errors - parse_list() handles this shape.
        assert protocol.parse_error(text) is None


# ===========================================================================
# parse_list
# ===========================================================================

class TestParseList:
    def test_empty_mailbox(self):
        # hw_logs/20260922_184337_maildrop.log
        text = "l\r\n*** Message not found.\r\n(AEA PK-232M)  18536 free  (B,E,K,L,R,S) >\r\n"
        assert protocol.parse_list(text) == []

    def test_single_unset_clock_row(self):
        # hw_logs/20260922_184337_maildrop.log
        text = (
            "l\r\nMsg#    Size To     From   @ BBS  Date       Time   Title\r\n"
            "  1 PN    36 OE3GAS OE3GAS        .........  .....  test 1\r\n"
            "(AEA PK-232M)  18452 free  (B,E,K,L,R,S) >\r\n"
        )
        entries = protocol.parse_list(text)
        assert len(entries) == 1
        e = entries[0]
        assert e.number == 1
        assert e.mtype == "P"
        assert e.read is False
        assert e.size == 36
        assert e.to == "OE3GAS"
        assert e.frm == "OE3GAS"
        assert e.bbs == ""
        assert e.stamp is None          # dot-rows -> unset clock
        assert e.title == "test 1"

    def test_two_rows_read_status(self):
        # hw_logs/20260922_184337_maildrop.log - message 1 was read (PY)
        # after message 2 was added (PN), newest first.
        text = (
            "l\r\nMsg#    Size To     From   @ BBS  Date       Time   Title\r\n"
            "  2 PN    35 OE3GAS OE3GAS        .........  .....  Test 2\r\n"
            "  1 PY    36 OE3GAS OE3GAS        .........  .....  test 1\r\n"
            "(AEA PK-232M)  18368 free  (B,E,K,L,R,S) >\r\n"
        )
        entries = protocol.parse_list(text)
        assert [e.number for e in entries] == [2, 1]
        assert entries[0].read is False
        assert entries[1].read is True

    def test_bbs_types_and_real_dates(self):
        # hw_logs/20260922_191657_maildrop.log (round 2): @BBS set, real
        # dates/times, and all three message types P/T/B.
        text = (
            "l\r\nMsg#    Size To     From   @ BBS  Date       Time   Title\r\n"
            "  6 TN    33 OE3GAS OE3GAS        22-Sep-26  17:20  test traffic\r\n"
            "  5 BN    52 ALL    OE3GAS        22-Sep-26  17:19  Test Bulletin\r\n"
            "  4 PN    41 OE1XYZ OE3GAS DB0MUC 22-Sep-26  17:18  ein @ test\r\n"
            "  3 PN    37 OE3GAS OE3GAS        22-Sep-26  17:17  From Test 1\r\n"
            "  2 PN    35 OE3GAS OE3GAS        .........  .....  Test 2\r\n"
            "(AEA PK-232M)  18088 free  (B,E,K,L,R,S) >\r\n"
        )
        entries = {e.number: e for e in protocol.parse_list(text)}

        assert entries[6].mtype == "T"
        assert entries[6].stamp == "22-Sep-26  17:20"
        assert entries[6].title == "test traffic"

        assert entries[5].mtype == "B"
        assert entries[5].to == "ALL"

        assert entries[4].mtype == "P"
        assert entries[4].bbs == "DB0MUC"
        assert entries[4].title == "ein @ test"   # '@' inside the TITLE,
        # not mistaken for the BBS column separator - fixed-width slicing
        # only, never a naive '@' search.

        assert entries[2].stamp is None

    def test_foreign_from(self):
        # hw_logs/20260922_200013_maildrop.log (round 3): 'S OE3GAS < DL1ABC'.
        text = (
            "l\r\nMsg#    Size To     From   @ BBS  Date       Time   Title\r\n"
            "  1 PN    44 OE3GAS DL1ABC        22-Sep-26  18:00  Test Subjekt\r\n"
            "(AEA PK-232M)  18284 free  (B,E,K,L,R,S) >\r\n"
        )
        entries = protocol.parse_list(text)
        assert entries[0].to == "OE3GAS"
        assert entries[0].frm == "DL1ABC"


# ===========================================================================
# parse_read
# ===========================================================================

class TestParseRead:
    def test_with_trailing_e_line(self):
        # hw_logs/20260922_184337_maildrop.log ('r 1') - the one-off '/E'
        # trailer CLAUDE.md documents as tolerated, never required.
        text = (
            "r 1\r\nMsg#    Size To     From   @ BBS  Date       Time   Title\r\n"
            "  1 PN    36 OE3GAS OE3GAS        .........  .....  test 1\r\n"
            "\r\nerste test-nachricht.\r\n/E\r\n"
            "(AEA PK-232M)  18452 free  (B,E,K,L,R,S) >\r\n"
        )
        entry, body = protocol.parse_read(text)
        assert entry is not None
        assert entry.number == 1
        assert body == "erste test-nachricht."

    def test_without_trailing_e_line(self):
        # hw_logs/20260922_200013_maildrop.log ('r 2') - round 3 confirmed
        # the '/E' trailer is NOT general; this response ends cleanly.
        text = (
            "r 2\r\nMsg#    Size To     From   @ BBS  Date       Time   Title\r\n"
            "  2 PN    33 OE3GAS OE3GAS        22-Sep-26  18:01  Test CTRL-Z\r\n"
            "\r\nende mit ctrl-z\r\n\r\n"
            "(AEA PK-232M)  18284 free  (B,E,K,L,R,S) >\r\n"
        )
        entry, body = protocol.parse_read(text)
        assert entry is not None
        assert entry.number == 2
        assert entry.stamp == "22-Sep-26  18:01"
        assert body == "ende mit ctrl-z"

    def test_multi_line_body(self):
        # hw_logs/20260922_200013_maildrop.log ('r 3') - a two-line body.
        text = (
            "r 3\r\nMsg#    Size To     From   @ BBS  Date       Time   Title\r\n"
            "  3 PN    30 OE3GAS OE3GAS        22-Sep-26  18:02  2. ctrl-z test\r\n"
            "\r\nblabla\r\n^z\r\n\r\n"
            "(AEA PK-232M)  18284 free  (B,E,K,L,R,S) >\r\n"
        )
        entry, body = protocol.parse_read(text)
        assert entry.number == 3
        assert body == "blabla\n^z"

    def test_no_list_row_found(self):
        entry, body = protocol.parse_read("garbage\r\nmore garbage\r\n")
        assert entry is None
        assert "garbage" in body


# ===========================================================================
# check_body
# ===========================================================================

class TestCheckBody:
    def test_line_is_exactly_ex(self):
        reasons = protocol.check_body("hello\n/EX\nworld")
        assert len(reasons) == 1

    def test_line_is_ex_with_surrounding_whitespace_and_case(self):
        reasons = protocol.check_body("  /ex  \n")
        assert len(reasons) == 1

    def test_harmless_text_containing_e_is_not_flagged(self):
        # A line merely CONTAINING '/E' but not starting with it is fine.
        reasons = protocol.check_body("see /Extra notes below\nnormal line")
        assert reasons == []

    def test_clean_body_has_no_reasons(self):
        assert protocol.check_body("just a normal message\nsecond line") == []


# ===========================================================================
# sanitize_body
# ===========================================================================

class TestSanitizeBody:
    def test_fuer_becomes_fuer_ascii(self):
        # hw_logs/20260922_200013_maildrop.log: raw 'für' arrived at the
        # TNC as 'f?r' (tool's own ASCII-only encoding, CLAUDE.md) -
        # sanitize_body() must transliterate instead of losing the umlaut.
        clean, changes = protocol.sanitize_body("für")
        assert clean == "fuer"
        assert len(changes) == 1

    def test_all_umlauts_and_eszett(self):
        clean, changes = protocol.sanitize_body("äöüÄÖÜß")
        assert clean == "aeoeueAeOeUess"
        assert len(changes) == 7

    def test_other_non_ascii_becomes_question_mark(self):
        clean, changes = protocol.sanitize_body("café")
        assert clean == "caf?"
        assert len(changes) == 1

    def test_pure_ascii_is_unchanged(self):
        clean, changes = protocol.sanitize_body("plain ascii text")
        assert clean == "plain ascii text"
        assert changes == []


# ===========================================================================
# build_send_command
# ===========================================================================

class TestBuildSendCommand:
    def test_plain_personal(self):
        # hw_logs/20260922_184337_maildrop.log ('s oe3gas')
        assert protocol.build_send_command("oe3gas", "", "", "P") == "S OE3GAS"

    def test_with_bbs(self):
        # hw_logs/20260922_191657_maildrop.log ('s oe1xyz @ db0muc')
        cmd = protocol.build_send_command("oe1xyz", "db0muc", "", "P")
        assert cmd == "S OE1XYZ @ DB0MUC"

    def test_with_foreign_from(self):
        # hw_logs/20260922_200013_maildrop.log ('s oe3gas < dl1abc')
        cmd = protocol.build_send_command("oe3gas", "", "dl1abc", "P")
        assert cmd == "S OE3GAS < DL1ABC"

    def test_bulletin_all(self):
        # hw_logs/20260922_191657_maildrop.log ('sb all')
        assert protocol.build_send_command("all", "", "", "B") == "SB ALL"

    def test_traffic(self):
        # hw_logs/20260922_191657_maildrop.log ('st oe3gas')
        assert protocol.build_send_command("oe3gas", "", "", "T") == "ST OE3GAS"

    def test_bbs_and_foreign_from_together(self):
        cmd = protocol.build_send_command("oe1xyz", "db0muc", "dl1abc", "P")
        assert cmd == "S OE1XYZ @ DB0MUC < DL1ABC"

    def test_invalid_recipient_raises(self):
        try:
            protocol.build_send_command("not a call!", "", "", "P")
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError")

    def test_invalid_mtype_raises(self):
        try:
            protocol.build_send_command("oe3gas", "", "", "X")
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError")


class TestValidateCallsign:
    def test_plain_callsign(self):
        assert protocol.validate_callsign("oe3gas") is True

    def test_callsign_with_ssid(self):
        assert protocol.validate_callsign("OE3GAS-5") is True

    def test_bulletin_destination_all(self):
        assert protocol.validate_callsign("ALL") is True

    def test_rejects_nonsense(self):
        assert protocol.validate_callsign("not a call!") is False
        assert protocol.validate_callsign("") is False
