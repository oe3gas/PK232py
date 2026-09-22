# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Unit tests for tools/hw_check.py's pure-logic pieces (P14).

Covers only what needs no serial interface at all: frame/response
evaluation and the query -> set -> action -> restore pattern every test
in hw_check.py uses to leave the TNC exactly as it found it (hard rule #2
in docs/P14_HW_Solo_Check_Spec.md), including restoration when the action
raises.

tools/ has no __init__.py and is not part of the installed package, so it
is added to sys.path here rather than imported as a regular module.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pk232py.comm.frame import FrameKind, HostFrame

_TOOLS_DIR = Path(__file__).resolve().parents[3] / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import hw_check  # noqa: E402


def _cmd_resp(data: bytes) -> HostFrame:
    """A real CMD_RESP HostFrame ($4F, channel 15) - the shape every Host
    Mode query answer actually has."""
    return HostFrame(ctl=0x4F, channel=15, data=data, kind=FrameKind.CMD_RESP)


class TestEvaluateT17:
    def test_px_is_the_toggle(self):
        # PX (PASSALL) responds Y/N; PS (PASS) responds with a char/hex value.
        result = hw_check.evaluate_t17(px_response="PX Y", ps_response="PS $16")
        assert result["passall_mnemonic"] == "PX"

    def test_ps_is_the_toggle(self):
        result = hw_check.evaluate_t17(px_response="PX $16", ps_response="PS N")
        assert result["passall_mnemonic"] == "PS"

    def test_both_look_like_toggles_is_inconclusive(self):
        result = hw_check.evaluate_t17(px_response="PX Y", ps_response="PS N")
        assert result["passall_mnemonic"] is None

    def test_neither_looks_like_a_toggle_is_inconclusive(self):
        result = hw_check.evaluate_t17(px_response="?What?", ps_response="?What?")
        assert result["passall_mnemonic"] is None


class TestSelectResponseFrame:
    """P16.2: correlate a Host Mode response by mnemonic prefix, never by
    arrival order. Fixtures are the real 21.09.2026 T86 hardware sequence
    (hw_logs/), including the stale 'HP\\x00' poll-ack from Host Mode entry
    that was still in flight when the PX query went out and got mistaken
    for the answer, turning a clean PASS into INCONCLUSIVE."""

    def test_ignores_stale_hp_frame_and_finds_the_real_answer(self):
        stale_hp = _cmd_resp(b"HP\x00")
        real_px = _cmd_resp(b"PXN")

        result = hw_check.select_response_frame(b"PX", [stale_hp, real_px])

        assert result is real_px

    def test_returns_none_when_nothing_matches(self):
        stale_hp = _cmd_resp(b"HP\x00")
        assert hw_check.select_response_frame(b"PX", [stale_hp]) is None

    def test_returns_none_for_empty_frame_list(self):
        assert hw_check.select_response_frame(b"PX", []) is None

    def test_full_t86_sequence_yields_pass_for_px(self):
        # The exact real hardware sequence from 21.09.2026 (T86): PX's own
        # query still had the stale HP\x00 ahead of it, PS's did not.
        px_frames = [_cmd_resp(b"HP\x00"), _cmd_resp(b"PXN")]
        ps_frames = [_cmd_resp(b"PS$16")]

        px_frame = hw_check.select_response_frame(b"PX", px_frames)
        ps_frame = hw_check.select_response_frame(b"PS", ps_frames)

        assert px_frame is not None
        assert ps_frame is not None
        verdict = hw_check.evaluate_t17(px_frame.text, ps_frame.text)
        assert verdict["passall_mnemonic"] == "PX"


class TestParseQueryValue:
    """Fixtures are real PK-232 responses captured 21.09.2026 (hw_logs/),
    not idealised guesses (P15.1) - the 18 pre-P15 tests here all passed
    while missing every one of the four real hardware bugs, because they
    were written against responses the TNC does not actually send."""

    def test_users_query(self):
        resp = "USERS\r\nUSers     1\r\ncmd:"
        assert hw_check.parse_query_value("USERS", resp) == "1"

    def test_pthuff_query(self):
        resp = "PTHUFF\r\nPTHuff    0\r\ncmd:"
        assert hw_check.parse_query_value("PTHUFF", resp) == "0"

    def test_unproto_query(self):
        resp = "UNPROTO\r\nUnproto   CQ\r\ncmd:"
        assert hw_check.parse_query_value("UNPROTO", resp) == "CQ"

    def test_monitor_query_strips_explanation(self):
        resp = "MONITOR\r\nMonitor   6 (seq, P/F + all)\r\ncmd:"
        assert hw_check.parse_query_value("MONITOR", resp) == "6"

    def test_txdelay_query_strips_explanation(self):
        resp = "TXDELAY\r\nTXdelay   30 (300 msec.)\r\ncmd:"
        assert hw_check.parse_query_value("TXDELAY", resp) == "30"

    def test_canline_query_strips_explanation(self):
        resp = "CANLINE\r\nCANline   $18 (CTRL-X)\r\ncmd:"
        assert hw_check.parse_query_value("CANLINE", resp) == "$18"

    def test_multi_word_value_preserved(self):
        # A multi-word value must come back whole - only the trailing
        # parenthesised note is stripped, not everything after the first
        # word (P15.1).
        resp = "UNPROTO\r\nUnproto   CQ VIA WIDE1-1\r\ncmd:"
        assert hw_check.parse_query_value("UNPROTO", resp) == "CQ VIA WIDE1-1"

    def test_what_error_is_none(self):
        # The exact T17 failure from the hardware log: two-letter mnemonics
        # do not exist in verbose mode.
        resp = "PX\r\n?What?\r\ncmd:"
        assert hw_check.parse_query_value("PX", resp) is None

    def test_bad_error_is_none(self):
        # The exact garbage the un-parsed pre-P15 code sent and then choked
        # on (Befund 2/4: a stray 'cmd:' token mistaken for a value).
        resp = "PTHUFF cmd:\r\n?bad\r\ncmd:"
        assert hw_check.parse_query_value("PTHUFF", resp) is None

    def test_callsign_error_is_none(self):
        resp = "UNPROTO cmd:\r\n?callsign\r\ncmd:"
        assert hw_check.parse_query_value("UNPROTO", resp) is None

    def test_was_now_set_response_returns_now_value(self):
        resp = "USERS 1\r\nUSers     was 1\r\nUSers     now 1\r\ncmd:"
        assert hw_check.parse_query_value("USERS", resp) == "1"

    def test_multiline_value_returns_none(self):
        # MTEXT's two-line welcome message is not supported yet - returning
        # a truncated value would be worse than skipping the restore.
        resp = "MTEXT\r\nMText     PK232PY DE OE3GAS\r\nMText     73 AND CU\r\ncmd:"
        assert hw_check.parse_query_value("MTEXT", resp) is None

    def test_empty_response_is_none(self):
        assert hw_check.parse_query_value("USERS", "") is None


class TestParseQueryValueFindsLineByContent:
    """P21.1: fixtures from the real 22.09.2026 maildrop/mi console
    transcripts, where position-based parsing (first line = echo, last =
    'cmd:') broke - a stray leftover fragment before the echo, and a
    SIAM result asynchronously interleaved into the middle of an
    unrelated response (SIAM keeps analysing until a different mode is
    selected, it does not stop on its own)."""

    def test_stray_leading_fragment_is_ignored(self):
        resp = "d:\\\r\nMAILDROP\r\nMAildrop  OFF\r\ncmd:"
        assert hw_check.parse_query_value("MAILDROP", resp) == "OFF"

    def test_interleaved_siam_line_is_ignored(self):
        resp = "XMITOK\r\nBaudot, RXRev OFF\r\nXMITOk    ON\r\ncmd:"
        assert hw_check.parse_query_value("XMITOK", resp) == "ON"

    def test_mfilter_value(self):
        resp = "MFILTER\r\nMFIlter   $80\r\ncmd:"
        assert hw_check.parse_query_value("MFILTER", resp) == "$80"

    def test_expert_command_error_returns_none(self):
        resp = "KILONFWD\r\n?EXPERT command\r\ncmd:"
        assert hw_check.parse_query_value("KILONFWD", resp) is None


class TestQueryError:
    def test_expert_command(self):
        resp = "KILONFWD\r\n?EXPERT command\r\ncmd:"
        assert hw_check.query_error(resp) == "?EXPERT command"

    def test_what_error(self):
        resp = "PX\r\n?What?\r\ncmd:"
        assert hw_check.query_error(resp) == "?What?"

    def test_no_error_returns_none(self):
        resp = "USERS\r\nUSers     1\r\ncmd:"
        assert hw_check.query_error(resp) is None

    def test_empty_response_returns_none(self):
        assert hw_check.query_error("") is None


class TestScanForTncErrors:
    def test_finds_what_error(self):
        lines = ["cmd:", "?What?", "OK"]
        assert hw_check.scan_for_tnc_errors(lines) == ["?What?"]

    def test_finds_multiple_error_kinds(self):
        lines = ["?bad parameter", "fine", "?too many callsigns"]
        assert hw_check.scan_for_tnc_errors(lines) == [
            "?bad parameter", "?too many callsigns"
        ]

    def test_no_errors(self):
        assert hw_check.scan_for_tnc_errors(["cmd:", "OK", "PACLEN 64"]) == []

    def test_detects_despite_leading_whitespace(self):
        # Returns the original line, not a stripped copy - matching is
        # whitespace-tolerant, the returned value is verbatim for logging.
        assert hw_check.scan_for_tnc_errors(["  ?What?  "]) == ["  ?What?  "]


class TestDetectPthuffFormat:
    def test_on_off(self):
        assert hw_check.detect_pthuff_format("PTHUFF ON") == "on_off"
        assert hw_check.detect_pthuff_format("PTHUFF OFF") == "on_off"

    def test_numeric(self):
        assert hw_check.detect_pthuff_format("PTHUFF 5") == "numeric"

    def test_unknown(self):
        assert hw_check.detect_pthuff_format("?What?") == "unknown"


class TestHostQueryValue:
    """P17.2: strip the mnemonic echo from a Host Mode response so t111 can
    compare the actual Y/N (or masking-character) value, not the whole
    'PXN'/'PS$16' string."""

    def test_strips_yn_toggle_prefix(self):
        assert hw_check.host_query_value(_cmd_resp(b"PXN"), b"PX") == "N"

    def test_strips_hex_value_prefix(self):
        assert hw_check.host_query_value(_cmd_resp(b"PS$16"), b"PS") == "$16"

    def test_none_frame_returns_none(self):
        assert hw_check.host_query_value(None, b"PX") is None

    def test_falls_back_to_full_text_without_matching_prefix(self):
        assert hw_check.host_query_value(_cmd_resp(b"XX?"), b"PX") == "XX?"


class TestT111Mnemonic:
    """P17.2: t111 must send the SAME mnemonic as the app's own PASSALL
    button, or the tool measures a different command than the one the
    application actually sends."""

    def test_matches_main_window_toggle_map(self):
        main_window_py = (
            Path(__file__).resolve().parents[1] / "ui" / "main_window.py"
        )
        source = main_window_py.read_text(encoding="utf-8")
        extracted = hw_check.extract_passall_toggle_mnemonic(source)

        assert extracted is not None
        assert extracted.encode("ascii") == hw_check.PASSALL_TOGGLE_MNEMONIC


class TestLooksLikeSiamResult:
    """P17.1/P17.4: classify captured text against both documented output
    shapes (module docstring vs. mockup screen) - the whole point of the
    measurement is that nobody yet knows which one (or neither) is real."""

    def test_docstring_baudot_example(self):
        assert hw_check.looks_like_siam_result("BAUDOT 45 170") is True

    def test_docstring_tdm_example(self):
        assert hw_check.looks_like_siam_result("TDM ARQ-B:4") is True

    def test_docstring_unknown_example(self):
        assert hw_check.looks_like_siam_result("UNKNOWN") is True

    def test_mockup_example(self):
        text = "0.47: 50 Baud, Baudot, RXREV OFF"
        assert hw_check.looks_like_siam_result(text) is True

    def test_plain_ack_does_not_match(self):
        assert hw_check.looks_like_siam_result("PXN") is False

    def test_empty_text_does_not_match(self):
        assert hw_check.looks_like_siam_result("") is False


class TestSummarizeSiamFrames:
    def test_counts_by_kind_and_flags_candidates(self):
        stale_ack = _cmd_resp(b"HP\x00")
        result_like = _cmd_resp(b"BAUDOT 45 170")
        link_result_like = HostFrame(
            ctl=0x5F, channel=15, data=b"UNKNOWN", kind=FrameKind.LINK_MSG
        )

        summary = hw_check.summarize_siam_frames(
            [stale_ack, result_like, link_result_like]
        )

        assert summary["counts"] == {"CMD_RESP": 2, "LINK_MSG": 1}
        assert summary["candidates"] == [result_like, link_result_like]

    def test_no_candidates_when_nothing_looks_like_a_result(self):
        frames = [_cmd_resp(b"HP\x00"), _cmd_resp(b"PXN")]
        summary = hw_check.summarize_siam_frames(frames)
        assert summary["candidates"] == []


class TestEvaluateT112Param:
    """P18.3: MAXFRAME and SLOTTIME are judged separately - the first
    hardware run's combined verdict had hidden MAXFRAME's own result
    behind SLOTTIME's (MAXFRAME already equalled VHF's value before the
    test even started)."""

    def test_pass_when_hf_value_read_back(self):
        verdict = hw_check.evaluate_t112_param("1", hf_value="1", vhf_value="4")
        assert verdict == "PASS"

    def test_fail_when_vhf_value_leaked(self):
        verdict = hw_check.evaluate_t112_param("4", hf_value="1", vhf_value="4")
        assert verdict == "FAIL"

    def test_inconclusive_on_unexpected_value(self):
        verdict = hw_check.evaluate_t112_param("7", hf_value="1", vhf_value="4")
        assert verdict == "INCONCLUSIVE"

    def test_inconclusive_when_unparseable(self):
        verdict = hw_check.evaluate_t112_param(None, hf_value="1", vhf_value="4")
        assert verdict == "INCONCLUSIVE"


class TestT112FrameSequence:
    """P17.4/P18.3: the frame sequence must be BUILT from the real mode
    classes, never hand-reconstructed, so a future change to either
    mode's frames is picked up automatically instead of silently going
    stale here."""

    def test_matches_the_real_mode_classes_with_default_hf_values(self):
        from pk232py.modes.packet_hf import HFPacketMode
        from pk232py.modes.packet_vhf import VHFPacketMode

        vhf = VHFPacketMode()
        hf = HFPacketMode()
        expected = (
            vhf.get_activate_frames()
            + vhf.get_init_frames()
            + [VHFPacketMode.vhf_off_frame()]
            + hf.get_activate_frames()
            + hf.get_init_frames()
        )

        assert hw_check.build_t112_frame_sequence() == expected

    def test_threads_through_the_configured_hf_values(self):
        from pk232py.comm.frame import build_command

        frames = hw_check.build_t112_frame_sequence(
            hf_maxframe=2, hf_slottime=20
        )
        assert build_command(b'MX', b'2') in frames
        assert build_command(b'SL', b'20') in frames
        assert build_command(b'MX', b'1') not in frames
        assert build_command(b'SL', b'30') not in frames

    def test_sequence_ends_with_hf_monitor_on(self):
        from pk232py.comm.frame import build_command

        frames = hw_check.build_t112_frame_sequence()
        assert frames
        assert frames[-1] == build_command(b'MN', b'Y')


class TestEvaluateT101:
    def test_pass_when_target_follows_unproto_path(self):
        assert hw_check.evaluate_t101("TEST1", "TEST2") == "PASS"

    def test_fail_when_target_does_not_change(self):
        assert hw_check.evaluate_t101("TEST1", "TEST1") == "FAIL"

    def test_inconclusive_when_nothing_seen(self):
        assert hw_check.evaluate_t101(None, None) == "INCONCLUSIVE"
        assert hw_check.evaluate_t101("TEST1", None) == "INCONCLUSIVE"

    def test_inconclusive_when_neither_matches_expected_path(self):
        assert hw_check.evaluate_t101("TEST1", "SOMETHINGELSE") == "INCONCLUSIVE"


class TestRunWithRestore:
    """P15.2: query -> action -> restore -> VERIFY. No set before action,
    SKIPPED (not changed) when the original value can't be parsed, and a
    failed restore must never claim success."""

    def test_action_runs_before_any_restore_call(self):
        # P15.2 rule 2 (Befund 4): the old code sent a garbage restore-token
        # write before the real test action ever ran. Order must now be
        # strictly action-then-restore, nothing before action.
        order: list[tuple] = []

        def query():
            return "USERS\r\nUSers     1\r\ncmd:"

        def restore(v):
            order.append(("restore", v))

        def action():
            order.append(("action",))

        log = hw_check.RunLog(None)
        original = hw_check.run_with_restore("USERS", query, restore, action, log)

        assert original == "1"
        assert order == [("action",), ("restore", "1")]

    def test_restore_runs_even_if_action_raises(self):
        order: list[tuple] = []

        def query():
            return "USERS\r\nUSers     1\r\ncmd:"

        def restore(v):
            order.append(("restore", v))

        def action():
            order.append(("action",))
            raise RuntimeError("simulated failure mid-test")

        log = hw_check.RunLog(None)
        with pytest.raises(RuntimeError, match="simulated failure"):
            hw_check.run_with_restore("USERS", query, restore, action, log)

        assert order == [("action",), ("restore", "1")]

    def test_skips_without_changing_anything_when_original_unparseable(self):
        # P15.2 rule 1: no safe original value -> SKIPPED, action() and
        # restore() never run at all.
        calls: list[str] = []

        def query():
            return "?What?"

        def restore(v):
            calls.append(v)

        def action():
            calls.append("action")

        log = hw_check.RunLog(None)
        result = hw_check.run_with_restore("USERS", query, restore, action, log)

        assert result is None
        assert calls == []
        assert log.findings[0][0] == "USERS"
        assert log.findings[0][1] == "SKIPPED"

    def test_verified_restore_reports_restored(self, capsys):
        state = {"value": "1"}

        def query():
            return f"USERS\r\nUSers     {state['value']}\r\ncmd:"

        def restore(v):
            state["value"] = v

        def action():
            state["value"] = "4"

        log = hw_check.RunLog(None)
        hw_check.run_with_restore("USERS", query, restore, action, log)

        out = capsys.readouterr().out
        assert "USERS restored to '1'" in out
        assert "FAIL" not in out

    def test_failed_restore_never_says_restored(self, capsys):
        # The DoD proof: a restore that does not actually stick must NEVER
        # be reported as "restored" - it must be a clearly flagged FAIL
        # naming the manual fix-up command instead (P15.2).
        state = {"value": "1"}

        def query():
            return f"USERS\r\nUSers     {state['value']}\r\ncmd:"

        def restore(v):
            pass  # simulates a restore command the TNC silently rejected

        def action():
            state["value"] = "4"

        log = hw_check.RunLog(None)
        hw_check.run_with_restore("USERS", query, restore, action, log)

        out = capsys.readouterr().out
        assert "restored" not in out
        assert "FAIL: USERS" in out
        assert "restore of USERS failed" in out
        assert "expected '1'" in out


class TestMiProbeMnemonic:
    """P20 Teil C: mi must query the SAME mnemonic as the app's own
    MailDrop button (main_window._on_packet_maildrop()), or the tool
    measures a different command than the one the application actually
    sends (same pattern as TestT111Mnemonic, P17.2)."""

    def test_matches_main_window_maildrop_button(self):
        main_window_py = (
            Path(__file__).resolve().parents[1] / "ui" / "main_window.py"
        )
        source = main_window_py.read_text(encoding="utf-8")
        extracted = hw_check.extract_maildrop_button_mnemonic(source)

        assert extracted is not None
        assert extracted.encode("ascii") == hw_check.MI_PROBE_MNEMONIC


class TestEvaluateMiProbe:
    def test_pass_when_values_differ(self):
        assert hw_check.evaluate_mi_probe("Y", "N") == "PASS"

    def test_fail_when_values_match(self):
        assert hw_check.evaluate_mi_probe("Y", "Y") == "FAIL"

    def test_inconclusive_when_mi_missing(self):
        assert hw_check.evaluate_mi_probe(None, "Y") == "INCONCLUSIVE"

    def test_inconclusive_when_mfilter_missing(self):
        assert hw_check.evaluate_mi_probe("Y", None) == "INCONCLUSIVE"


class TestClassifyMaildropInput:
    """P20 Teil B: the md> prompt's three input classes - the tool's own
    /quit (never sent), ^Z/^D/^C control bytes, and plain text lines
    (sent with a trailing CR, not CRLF - matches a real terminal's Enter
    key into a modem/BBS-style prompt)."""

    def test_quit_is_never_sent(self):
        assert hw_check.classify_maildrop_input("/quit") == ("quit", None)

    def test_quit_tolerates_surrounding_whitespace(self):
        assert hw_check.classify_maildrop_input("  /quit  ") == ("quit", None)

    def test_ctrl_z_sent_as_single_byte(self):
        assert hw_check.classify_maildrop_input("^Z") == ("control", b"\x1a")

    def test_ctrl_d_sent_as_single_byte(self):
        assert hw_check.classify_maildrop_input("^D") == ("control", b"\x04")

    def test_ctrl_c_sent_as_single_byte(self):
        assert hw_check.classify_maildrop_input("^C") == ("control", b"\x03")

    def test_plain_text_gets_trailing_cr(self):
        assert hw_check.classify_maildrop_input("L") == ("text", b"L\r")

    def test_plain_text_with_arguments(self):
        result = hw_check.classify_maildrop_input("S OE3GAS")
        assert result == ("text", b"S OE3GAS\r")

    def test_empty_line_is_still_sent_as_text(self):
        # Pressing Enter with nothing typed is a valid mailbox interaction
        # (e.g. paging through a prompt) - must not be silently dropped.
        assert hw_check.classify_maildrop_input("") == ("text", b"\r")


class TestFormatBytesWithControls:
    def test_printable_ascii_passes_through(self):
        assert hw_check.format_bytes_with_controls(b"L") == "L"
        assert hw_check.format_bytes_with_controls(b"S OE3GAS") == "S OE3GAS"

    def test_cr_lf_shown_as_labels(self):
        assert hw_check.format_bytes_with_controls(b"\r\n") == "<CR><LF>"

    def test_control_bytes_shown_as_labels(self):
        assert hw_check.format_bytes_with_controls(b"\x1a") == "<^Z>"
        assert hw_check.format_bytes_with_controls(b"\x04") == "<^D>"
        assert hw_check.format_bytes_with_controls(b"\x03") == "<^C>"

    def test_unlabelled_non_printable_byte_shown_as_hex(self):
        assert hw_check.format_bytes_with_controls(b"\x01") == "<$01>"

    def test_mixed_line(self):
        text = hw_check.format_bytes_with_controls(b"L\r\n")
        assert text == "L<CR><LF>"


class TestMaildropSessionLeft:
    def test_detects_cmd_prompt(self):
        assert hw_check.maildrop_session_left("some text\r\ncmd:") is True

    def test_no_cmd_prompt(self):
        assert hw_check.maildrop_session_left("Bye.\r\nmd>") is False

    def test_empty_text(self):
        assert hw_check.maildrop_session_left("") is False


# Three real 'L' responses from hw_logs/20260922_184337_maildrop.log
# (P22, first full hardware run), verbatim.
_MAILDROP_LIST_1_MSG = (
    "l\r\nMsg#    Size To     From   @ BBS  Date       Time   Title\r\n"
    "  1 PN    36 OE3GAS OE3GAS        .........  .....  test 1\r\n"
    "(AEA PK-232M)  18452 free  (B,E,K,L,R,S) >\r\n"
)
_MAILDROP_LIST_2_MSGS = (
    "l\r\nMsg#    Size To     From   @ BBS  Date       Time   Title\r\n"
    "  2 PN    35 OE3GAS OE3GAS        .........  .....  Test 2\r\n"
    "  1 PY    36 OE3GAS OE3GAS        .........  .....  test 1\r\n"
    "(AEA PK-232M)  18368 free  (B,E,K,L,R,S) >\r\n"
)
_MAILDROP_LIST_AFTER_KILL = (
    "l\r\nMsg#    Size To     From   @ BBS  Date       Time   Title\r\n"
    "  2 PN    35 OE3GAS OE3GAS        .........  .....  Test 2\r\n"
    "(AEA PK-232M)  18452 free  (B,E,K,L,R,S) >\r\n"
)
# Real 'R 1' response, same log - message text ends with the firmware's
# own stray '/E' line before the mailbox prompt.
_MAILDROP_READ_RESPONSE = (
    "r 1\r\nMsg#    Size To     From   @ BBS  Date       Time   Title\r\n"
    "  1 PN    36 OE3GAS OE3GAS        .........  .....  test 1\r\n"
    "\r\nerste test-nachricht.\r\n/E\r\n"
    "(AEA PK-232M)  18452 free  (B,E,K,L,R,S) >\r\n"
)


class TestParseMaildropListRow:
    def test_single_message_row(self):
        row = hw_check.parse_maildrop_list_row(
            "  1 PN    36 OE3GAS OE3GAS        .........  .....  test 1"
        )
        assert row == {
            "number": 1, "type": "P", "read": "N", "size": 36,
            "to": "OE3GAS", "from": "OE3GAS", "bbs": None,
            "date": None, "time": None, "title": "test 1",
        }

    def test_read_status_y(self):
        row = hw_check.parse_maildrop_list_row(
            "  1 PY    36 OE3GAS OE3GAS        .........  .....  test 1"
        )
        assert row["type"] == "P"
        assert row["read"] == "Y"

    def test_header_line_returns_none(self):
        header = "Msg#    Size To     From   @ BBS  Date       Time   Title"
        assert hw_check.parse_maildrop_list_row(header) is None

    def test_mailbox_prompt_line_returns_none(self):
        assert hw_check.parse_maildrop_list_row(_MAILBOX_PROMPT) is None

    def test_short_line_returns_none(self):
        assert hw_check.parse_maildrop_list_row("*** Message not found.") is None


class TestParseMaildropList:
    """P22.5: the three real listings from the 22.09.2026 transcript."""

    def test_list_with_one_message(self):
        rows = hw_check.parse_maildrop_list(_MAILDROP_LIST_1_MSG)
        assert len(rows) == 1
        assert rows[0]["number"] == 1
        assert rows[0]["read"] == "N"
        assert rows[0]["date"] is None
        assert rows[0]["time"] is None

    def test_list_with_two_messages_newest_first(self):
        rows = hw_check.parse_maildrop_list(_MAILDROP_LIST_2_MSGS)
        assert [r["number"] for r in rows] == [2, 1]
        assert rows[0]["title"] == "Test 2"
        assert rows[0]["read"] == "N"
        # Reading message 1 earlier flipped its status N -> Y - the TNC
        # number is NOT reassigned, and stays 1.
        assert rows[1]["number"] == 1
        assert rows[1]["read"] == "Y"

    def test_list_after_kill_keeps_surviving_number(self):
        rows = hw_check.parse_maildrop_list(_MAILDROP_LIST_AFTER_KILL)
        # Message 1 was killed; message 2 keeps its own number, it is
        # NOT renumbered to 1.
        assert [r["number"] for r in rows] == [2]

    def test_empty_mailbox_yields_no_rows(self):
        resp = "l\r\n*** Message not found.\r\n(AEA PK-232M)  18536 free  (B,E,K,L,R,S) >\r\n"
        assert hw_check.parse_maildrop_list(resp) == []


class TestMaildropResponseHasETrailer:
    def test_real_read_response_has_trailer(self):
        assert hw_check.maildrop_response_has_e_trailer(_MAILDROP_READ_RESPONSE) is True

    def test_response_without_trailer(self):
        resp = "hello\r\n(AEA PK-232M)  18452 free  (B,E,K,L,R,S) >\r\n"
        assert hw_check.maildrop_response_has_e_trailer(resp) is False

    def test_empty_response(self):
        assert hw_check.maildrop_response_has_e_trailer("") is False


class TestReadPowerCycleConfirmation:
    """P22.2: only 'done'/'skip' are accepted; anything else re-asks -
    an earlier run's blank Enter was silently read as skip before this
    confirm loop existed."""

    def test_done_proceeds(self):
        answers = iter(["done"])
        assert hw_check.read_power_cycle_confirmation(lambda: next(answers)) is True

    def test_skip_declines(self):
        answers = iter(["skip"])
        assert hw_check.read_power_cycle_confirmation(lambda: next(answers)) is False

    def test_case_and_whitespace_tolerant(self):
        answers = iter(["  DONE  "])
        assert hw_check.read_power_cycle_confirmation(lambda: next(answers)) is True

    def test_blank_enter_re_asks_instead_of_defaulting_to_skip(self):
        answers = iter(["", "y", "done"])
        assert hw_check.read_power_cycle_confirmation(lambda: next(answers)) is True

    def test_garbage_re_asks_until_skip(self):
        answers = iter(["maybe", "later", "skip"])
        assert hw_check.read_power_cycle_confirmation(lambda: next(answers)) is False


class TestEvaluatePowerCycleLoss:
    def test_pass_when_message_existed_and_now_empty(self):
        verdict = hw_check.evaluate_power_cycle_loss(
            True, "l\r\n*** Message not found.\r\ncmd:"
        )
        assert verdict == "PASS"

    def test_inconclusive_when_no_message_existed_before(self):
        verdict = hw_check.evaluate_power_cycle_loss(
            False, "l\r\n*** Message not found.\r\ncmd:"
        )
        assert verdict == "INCONCLUSIVE"

    def test_inconclusive_when_mailbox_still_has_a_message(self):
        verdict = hw_check.evaluate_power_cycle_loss(True, _MAILDROP_LIST_1_MSG)
        assert verdict == "INCONCLUSIVE"


# Real mailbox prompt, hardware-confirmed 22.09.2026 - round brackets,
# double spaces, differs from the TRM's '[AEA PK-232M] ... >' example.
_MAILBOX_PROMPT = "(AEA PK-232M)  18536 free  (B,E,K,L,R,S) >"


class TestExtractMailboxFree:
    def test_extracts_free_bytes(self):
        assert hw_check.extract_mailbox_free(_MAILBOX_PROMPT) == 18536

    def test_none_when_no_prompt(self):
        assert hw_check.extract_mailbox_free("cmd:") is None


class TestClassifyMaildropResponse:
    """P21.4 fixtures from the real 22.09.2026 maildrop transcript."""

    def test_mailbox_prompt_with_round_brackets_and_double_spaces(self):
        state, recognised = hw_check.classify_maildrop_response(
            _MAILBOX_PROMPT, previous_state="MAILBOX"
        )
        assert (state, recognised) == ("MAILBOX", True)

    def test_cmd_prompt_ends_interactive_phase(self):
        state, recognised = hw_check.classify_maildrop_response(
            "b\r\ncmd:", previous_state="MAILBOX"
        )
        assert (state, recognised) == ("CMD", True)

    def test_h_in_sysop_mode_is_not_an_error_state(self):
        # SysOp command set is B,E,K,L,R,S only - 'H'/'?' are for other
        # users logging in. The mailbox answers '*** What?' but still
        # reprints its own prompt, so this must NOT be flagged.
        resp = f"h\r\n*** What?\r\n{_MAILBOX_PROMPT}"
        state, recognised = hw_check.classify_maildrop_response(
            resp, previous_state="MAILBOX"
        )
        assert (state, recognised) == ("MAILBOX", True)

    def test_siam_line_interleaved_after_prompt_stays_mailbox(self):
        # SIAM keeps analysing until a different mode is picked and can
        # still interleave a result even after normalize() (P21.2) - the
        # prompt is searched anywhere, not just as the last line.
        resp = f"{_MAILBOX_PROMPT}\r\n0.78: 50 baud, Baudot, RXRev ON\r\n"
        state, recognised = hw_check.classify_maildrop_response(
            resp, previous_state="MAILBOX"
        )
        assert (state, recognised) == ("MAILBOX", True)

    def test_subject_prompt_enters_text_entry(self):
        # P23.2: detected from the RESPONSE ('Subject:'), not from
        # having typed a literal 'S ...' command.
        state, recognised = hw_check.classify_maildrop_response(
            "s oe3gas\r\nSubject:\r\n", previous_state="MAILBOX"
        )
        assert (state, recognised) == ("ENTRY", True)

    def test_sb_bulletin_prompt_enters_text_entry(self):
        # P23.2 hardware finding, 22.09.2026 19:16: 'sb all' got a real
        # 'Subject:' prompt, but the old input-only check (looking only
        # for 'S ...') left the state at MAILBOX and flagged it as
        # unrecognised - fixed by reading the response instead.
        state, recognised = hw_check.classify_maildrop_response(
            "sb all\r\nSubject:\r\n", previous_state="MAILBOX"
        )
        assert (state, recognised) == ("ENTRY", True)

    def test_st_traffic_prompt_enters_text_entry(self):
        state, recognised = hw_check.classify_maildrop_response(
            "st oe3gas\r\nSubject:\r\n", previous_state="MAILBOX"
        )
        assert (state, recognised) == ("ENTRY", True)

    def test_text_body_prompt_enters_text_entry(self):
        resp = (
            "Test Bulletin\r\nEnter message, ^Z (CTRL-Z) or /EX to "
            "end\r\n\r\n"
        )
        state, recognised = hw_check.classify_maildrop_response(
            resp, previous_state="ENTRY"
        )
        assert (state, recognised) == ("ENTRY", True)

    def test_free_form_prompt_inside_entry_is_not_flagged(self):
        state, recognised = hw_check.classify_maildrop_response(
            "Text: ", previous_state="ENTRY"
        )
        assert (state, recognised) == ("ENTRY", True)

    def test_mailbox_prompt_returns_from_entry(self):
        state, recognised = hw_check.classify_maildrop_response(
            _MAILBOX_PROMPT, previous_state="ENTRY"
        )
        assert (state, recognised) == ("MAILBOX", True)

    def test_unrecognised_response_in_mailbox_state_is_flagged(self):
        state, recognised = hw_check.classify_maildrop_response(
            "???garbled???", previous_state="MAILBOX"
        )
        assert (state, recognised) == ("MAILBOX", False)

    def test_you_have_mail_before_prompt_is_mailbox_and_free_memory_parsed(self):
        # P23.5: real MDCHECK response, 22.09.2026 19:16, unread mail
        # present.
        resp = (
            "MDCHECK\r\nYou have mail.\r\n"
            "(AEA PK-232M)  18452 free  (B,E,K,L,R,S) >\r\n"
        )
        state, recognised = hw_check.classify_maildrop_response(
            resp, previous_state="MAILBOX"
        )
        assert (state, recognised) == ("MAILBOX", True)
        assert hw_check.extract_mailbox_free(resp) == 18452


class TestRunMaildropInteractiveSafety:
    """P21.4's safety test: once a response puts the terminal into CMD
    state, NOTHING typed afterwards may ever be sent - on real hardware,
    'K' at the TNC command interpreter means CONVERSE, not kill-message."""

    def test_stops_immediately_after_cmd_response_never_sends_next_line(self):
        lines = iter(["B", "k"])
        sent_payloads: list[bytes] = []

        def read_line(state, free):
            return next(lines, None)

        def send(payload, note):
            sent_payloads.append(payload)
            return b"cmd:"

        log = hw_check.RunLog(None)
        final_state, last_sent, message_stored = hw_check.run_maildrop_interactive(
            "MAILBOX", 18536, read_line, send, log
        )

        assert final_state == "CMD"
        assert last_sent == b"B\r"
        assert sent_payloads == [b"B\r"]
        assert message_stored is False

    def test_quit_never_sends_anything(self):
        def read_line(state, free):
            return "/quit"

        def send(payload, note):
            raise AssertionError("must never send after /quit")

        log = hw_check.RunLog(None)
        final_state, last_sent, message_stored = hw_check.run_maildrop_interactive(
            "MAILBOX", 18536, read_line, send, log
        )

        assert final_state == "MAILBOX"
        assert last_sent is None
        assert message_stored is False

    def test_eof_stops_without_sending(self):
        def read_line(state, free):
            return None

        def send(payload, note):
            raise AssertionError("must never send on EOF")

        log = hw_check.RunLog(None)
        final_state, last_sent, message_stored = hw_check.run_maildrop_interactive(
            "MAILBOX", 18536, read_line, send, log
        )

        assert final_state == "MAILBOX"
        assert last_sent is None
        assert message_stored is False

    def test_full_sequence_tracks_state_through_entry_and_back(self):
        exchanges = iter([
            ("L", _MAILBOX_PROMPT),
            ("S OE3GAS", "Subject: "),
            ("Test", "Text: "),
            ("hello", ""),
            ("^Z", f"Message stored as # 3\r\n{_MAILBOX_PROMPT}"),
        ])
        typed = iter(["L", "S OE3GAS", "Test", "hello", "^Z"])
        sent_payloads: list[bytes] = []

        def read_line(state, free):
            return next(typed, None)

        def send(payload, note):
            sent_payloads.append(payload)
            _, resp = next(exchanges)
            return resp.encode("ascii")

        log = hw_check.RunLog(None)
        final_state, last_sent, message_stored = hw_check.run_maildrop_interactive(
            "MAILBOX", 18536, read_line, send, log
        )

        assert final_state == "MAILBOX"
        assert last_sent == b"\x1a"
        assert message_stored is True
        assert sent_payloads == [
            b"L\r", b"S OE3GAS\r", b"Test\r", b"hello\r", b"\x1a",
        ]

    def test_ctrl_z_in_entry_returns_to_mailbox_once_prompt_seen(self):
        # P22.4: ^Z is sent as $1A - the state machine already handles
        # the ENTRY -> MAILBOX transition once the mailbox prompt comes
        # back, regardless of what was typed to trigger it.
        typed = iter(["^Z"])

        def read_line(state, free):
            return next(typed, None)

        def send(payload, note):
            assert payload == b"\x1a"
            return _MAILBOX_PROMPT.encode("ascii")

        log = hw_check.RunLog(None)
        final_state, last_sent, message_stored = hw_check.run_maildrop_interactive(
            "ENTRY", 18452, read_line, send, log
        )

        assert final_state == "MAILBOX"
        assert last_sent == b"\x1a"


class TestParseStoredMessageNumber:
    def test_extracts_number(self):
        assert hw_check.parse_stored_message_number(
            "Message stored as # 7\r\n"
        ) == 7

    def test_none_when_absent(self):
        assert hw_check.parse_stored_message_number("no message here") is None


class TestRunMaildropInteractiveCtrlZEof:
    """P23.3: a Windows console turns a typed Ctrl-Z into an EOFError
    (found 22.09.2026, 19:16 - the operator's real attempt at ^Z closed
    the whole terminal instead of ending the message). An EOFError while
    in ENTRY is now read as "end the message" and sends $1A instead of
    stopping; outside ENTRY it is still treated as a real EOF."""

    def test_eof_in_entry_sends_ctrl_z_and_continues_reading(self):
        calls = iter([None, "/quit"])
        sent_payloads: list[bytes] = []

        def read_line(state, free):
            return next(calls)

        def send(payload, note):
            sent_payloads.append(payload)
            return f"Message stored as # 7\r\n{_MAILBOX_PROMPT}".encode("ascii")

        log = hw_check.RunLog(None)
        final_state, last_sent, message_stored = hw_check.run_maildrop_interactive(
            "ENTRY", 17976, read_line, send, log
        )

        assert sent_payloads == [b"\x1a"]
        assert last_sent == b"\x1a"
        assert message_stored is True
        assert final_state == "MAILBOX"

    def test_eof_outside_entry_still_stops_without_sending(self):
        def read_line(state, free):
            return None

        def send(payload, note):
            raise AssertionError("must never send on a real EOF")

        log = hw_check.RunLog(None)
        final_state, last_sent, message_stored = hw_check.run_maildrop_interactive(
            "MAILBOX", 18536, read_line, send, log
        )

        assert final_state == "MAILBOX"
        assert last_sent is None
        assert message_stored is False

    def test_eof_in_entry_then_input_still_broken_stops_cleanly(self):
        # If input() never recovers after the console EOFError, the next
        # read_line() call also returns None - but by then the state has
        # already moved to MAILBOX, so the ordinary "real EOF" path
        # applies and the terminal ends cleanly instead of looping.
        calls = iter([None, None])

        def read_line(state, free):
            return next(calls)

        def send(payload, note):
            return f"Message stored as # 7\r\n{_MAILBOX_PROMPT}".encode("ascii")

        log = hw_check.RunLog(None)
        final_state, last_sent, message_stored = hw_check.run_maildrop_interactive(
            "ENTRY", 17976, read_line, send, log
        )

        assert final_state == "MAILBOX"
        assert last_sent == b"\x1a"


class TestMaildropReadTrailerTracking:
    """P23.4: after 'R <n>' is typed, the run records (via
    log.result(), so it lands in the summary) whether the response has
    an '/E' trailer, and which ending method ('/EX' or '^Z') that
    message was originally stored with."""

    def test_reports_trailer_and_ex_end_method(self):
        typed = iter(["/EX", "R 1", "/quit"])
        responses = iter([
            f"Message stored as # 1\r\n{_MAILBOX_PROMPT}",
            f"some text\r\n/E\r\n{_MAILBOX_PROMPT}",
        ])

        def read_line(state, free):
            return next(typed, None)

        def send(payload, note):
            return next(responses).encode("ascii")

        log = hw_check.RunLog(None)
        hw_check.run_maildrop_interactive("ENTRY", 18452, read_line, send, log)

        matches = [f for f in log.findings if f[0] == "MAILDROP R1"]
        assert len(matches) == 1
        _, verdict, detail = matches[0]
        assert verdict == "INFO"
        assert "trailer=True" in detail
        assert "/EX" in detail

    def test_reports_no_trailer_and_ctrl_z_end_method(self):
        typed = iter(["^Z", "R 7", "/quit"])
        responses = iter([
            f"Message stored as # 7\r\n{_MAILBOX_PROMPT}",
            f"some text\r\n{_MAILBOX_PROMPT}",
        ])

        def read_line(state, free):
            return next(typed, None)

        def send(payload, note):
            return next(responses).encode("ascii")

        log = hw_check.RunLog(None)
        hw_check.run_maildrop_interactive("ENTRY", 17976, read_line, send, log)

        matches = [f for f in log.findings if f[0] == "MAILDROP R7"]
        assert len(matches) == 1
        _, verdict, detail = matches[0]
        assert "trailer=False" in detail
        assert "^Z" in detail


# Real 'L' response with six messages, hw_logs/20260922_191657_maildrop.log
# (P23, round 2) - types P/B/T, a populated '@ BBS', and real dates/times
# now that DAYTIME has been set, alongside one message still showing dots
# (stored before the clock was set, round 1).
_MAILDROP_LIST_ROUND2 = (
    "l\r\nMsg#    Size To     From   @ BBS  Date       Time   Title\r\n"
    "  6 TN    33 OE3GAS OE3GAS        22-Sep-26  17:20  test traffic\r\n"
    "  5 BN    52 ALL    OE3GAS        22-Sep-26  17:19  Test Bulletin\r\n"
    "  4 PN    41 OE1XYZ OE3GAS DB0MUC 22-Sep-26  17:18  ein @ test\r\n"
    "  3 PN    37 OE3GAS OE3GAS        22-Sep-26  17:17  From Test 1\r\n"
    "  2 PN    35 OE3GAS OE3GAS        .........  .....  Test 2\r\n"
    "(AEA PK-232M)  18088 free  (B,E,K,L,R,S) >\r\n"
)


class TestParseMaildropListRound2:
    """P23.5: the round-2 full listing - traffic (T), bulletin (B) and
    personal (P) types, a populated '@ BBS' column, real dates/times now
    that DAYTIME has been set, and one still-dotted row from round 1
    (stored before the clock was set)."""

    def test_all_six_rows_in_newest_first_order(self):
        rows = hw_check.parse_maildrop_list(_MAILDROP_LIST_ROUND2)
        assert [r["number"] for r in rows] == [6, 5, 4, 3, 2]

    def test_traffic_type(self):
        rows = hw_check.parse_maildrop_list(_MAILDROP_LIST_ROUND2)
        traffic = next(r for r in rows if r["number"] == 6)
        assert traffic["type"] == "T"
        assert traffic["to"] == "OE3GAS"
        assert traffic["bbs"] is None

    def test_bulletin_type_and_all_recipient(self):
        rows = hw_check.parse_maildrop_list(_MAILDROP_LIST_ROUND2)
        bulletin = next(r for r in rows if r["number"] == 5)
        assert bulletin["type"] == "B"
        assert bulletin["to"] == "ALL"

    def test_bbs_column_populated(self):
        rows = hw_check.parse_maildrop_list(_MAILDROP_LIST_ROUND2)
        via_bbs = next(r for r in rows if r["number"] == 4)
        assert via_bbs["type"] == "P"
        assert via_bbs["to"] == "OE1XYZ"
        assert via_bbs["bbs"] == "DB0MUC"

    def test_real_date_and_time_format(self):
        rows = hw_check.parse_maildrop_list(_MAILDROP_LIST_ROUND2)
        msg3 = next(r for r in rows if r["number"] == 3)
        assert msg3["date"] == "22-Sep-26"
        assert msg3["time"] == "17:17"

    def test_dotted_row_from_before_daytime_still_none(self):
        rows = hw_check.parse_maildrop_list(_MAILDROP_LIST_ROUND2)
        msg2 = next(r for r in rows if r["number"] == 2)
        assert msg2["date"] is None
        assert msg2["time"] is None


class TestBuildMaildropHostFrame:
    """P24.3: the Sonde A/B frame is SOH $60 ... ETB, with the SAME
    DLE-stuffing frame.py's own build_*() functions use - not a
    reimplementation."""

    def test_frame_structure_no_stuffing_needed(self):
        frame = hw_check.build_maildrop_host_frame(b"L\r")
        assert frame == bytes([0x01, 0x60]) + b"L\r" + bytes([0x17])

    def test_ctl_byte_is_0x60(self):
        frame = hw_check.build_maildrop_host_frame(b"MDCHECK\r")
        assert frame[0] == 0x01
        assert frame[1] == 0x60
        assert frame[-1] == 0x17

    def test_stuffing_matches_the_existing_dle_escape_function(self):
        # Data containing a literal SOH/DLE/ETB byte must be escaped the
        # SAME way frame.py's own _dle_escape() escapes it for every
        # other outgoing frame - checked directly against that function,
        # not against a hand-picked expected byte sequence.
        from pk232py.comm.frame import _dle_escape

        data = b"R \x17 1\r"   # contains a literal ETB byte
        frame = hw_check.build_maildrop_host_frame(data)
        assert frame == bytes([0x01, 0x60]) + _dle_escape(data) + bytes([0x17])
        # And confirm stuffing actually happened (DLE inserted before ETB).
        assert b"\x10\x17" in frame


class TestClassifyMaildropHostCtl:
    def test_0x70_is_maildrop_read_data(self):
        assert "70" in hw_check.classify_maildrop_host_ctl(0x70)
        assert "MailDrop read data" in hw_check.classify_maildrop_host_ctl(0x70)

    def test_0x2f_is_monitored_mxmit_data(self):
        assert "MXMIT" in hw_check.classify_maildrop_host_ctl(0x2F)

    def test_0x4f_is_cmd_resp_as_usual(self):
        assert "CMD_RESP" in hw_check.classify_maildrop_host_ctl(0x4F)

    def test_0x5f_is_status_err_as_usual(self):
        assert "STATUS_ERR" in hw_check.classify_maildrop_host_ctl(0x5F)

    def test_unknown_ctl_is_labelled_unknown(self):
        label = hw_check.classify_maildrop_host_ctl(0x99)
        assert "unknown" in label
        assert "99" in label


class TestShouldRunMaildropHostProbeB:
    def test_runs_when_probe_a_got_nothing(self):
        assert hw_check.should_run_maildrop_host_probe_b([]) is True

    def test_does_not_run_when_probe_a_got_a_response(self):
        fake_frame = object()
        assert hw_check.should_run_maildrop_host_probe_b([fake_frame]) is False
