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


class TestEvaluateT112:
    def test_pass_when_hf_values_read_back(self):
        verdict = hw_check.evaluate_t112(
            "1", "30", hf_maxframe="1", hf_slottime="30"
        )
        assert verdict == "PASS"

    def test_fail_when_vhf_values_leaked(self):
        verdict = hw_check.evaluate_t112(
            "4", "10", hf_maxframe="1", hf_slottime="30"
        )
        assert verdict == "FAIL"

    def test_inconclusive_on_unexpected_values(self):
        verdict = hw_check.evaluate_t112(
            "7", "7", hf_maxframe="1", hf_slottime="30"
        )
        assert verdict == "INCONCLUSIVE"

    def test_inconclusive_when_unparseable(self):
        verdict = hw_check.evaluate_t112(
            None, "30", hf_maxframe="1", hf_slottime="30"
        )
        assert verdict == "INCONCLUSIVE"


class TestT112FrameSequence:
    """P17.4: the frame sequence must be BUILT from the real mode classes,
    never hand-reconstructed, so a future change to either mode's frames
    is picked up automatically instead of silently going stale here."""

    def test_matches_the_real_mode_classes(self):
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
        assert "USERS 1" in out
