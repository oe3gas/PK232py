# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Unit tests for tools/hw_check.py's APRS measurement package (P62).

Covers the pure-logic pieces (evaluate_aprs_round, the R3/R4 payload
builders) and the three new subcommands' --dry-run path (no port opened,
nothing sent) - the same "measures only" boundary the rest of hw_check.py
already has (docs/P14_HW_Solo_Check_Spec.md hard rule #4/#6).

tools/ has no __init__.py and is not part of the installed package - see
test_hw_check.py's own docstring for why sys.path is extended here
instead of a regular import.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from pk232py.config import AppConfig

_TOOLS_DIR = Path(__file__).resolve().parents[3] / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import hw_check  # noqa: E402

# Same reasoning as test_hw_check.py: a full QApplication, not a bare
# QCoreApplication - whichever test module imports first installs the
# singleton other modules' QApplication.instance() later finds.
_APP = QApplication.instance() or QApplication(sys.argv[:1])


def _dry_run_session() -> tuple["hw_check.Session", "hw_check.RunLog"]:
    log = hw_check.RunLog(None)
    session = hw_check.Session("DRYRUN", 9600, True, log, AppConfig())
    return session, log


class TestEvaluateAprsRound:
    """P62, Teil B/D - the pure comparison every aprs_tx round runs
    against what the operator pasted back from a real decoder."""

    def test_exact_match_one_frame_is_pass(self):
        sent = ">PK232PY P62 R1 12:00:00"
        result = hw_check.evaluate_aprs_round(sent, None, f"WB1ABC>APZ232:{sent}", 1)
        assert result["verdict"] == "PASS"
        assert result["info_exact"] is True
        assert result["frames"] == 1

    def test_missing_character_from_the_probe_is_not_exact(self):
        sent = hw_check.build_aprs_r3_info()
        pasted_missing_one_char = sent[:-5] + sent[-4:]  # drop one char near the end
        result = hw_check.evaluate_aprs_round(sent, None, pasted_missing_one_char, 1)
        assert result["info_exact"] is False
        assert result["verdict"] == "FAIL"

    def test_trailing_cr_marker_is_detected_independently_of_the_verdict(self):
        sent = ">PK232PY P62 R3 test"
        pasted = f"WB1ABC>APZ232:{sent}<0x0d>"
        result = hw_check.evaluate_aprs_round(sent, None, pasted, 1)
        assert result["trailing_cr"] is True
        assert result["info_exact"] is True
        assert result["verdict"] == "PASS"

    def test_no_trailing_cr_marker(self):
        sent = ">PK232PY P62 R1 12:00:00"
        result = hw_check.evaluate_aprs_round(sent, None, f"WB1ABC>APZ232:{sent}", 1)
        assert result["trailing_cr"] is False

    def test_two_frames_is_not_pass_even_with_exact_text(self):
        sent = ">PK232PY P62 R1 12:00:00"
        result = hw_check.evaluate_aprs_round(sent, None, f"WB1ABC>APZ232:{sent}", 2)
        assert result["verdict"] != "PASS"
        assert result["frames"] == 2

    def test_r2_path_missing_wide2_1_is_path_not_ok(self):
        sent = ">PK232PY P62 R2 12:00:00"
        pasted = f"WB1ABC>APZ232,WIDE1-1:{sent}"  # WIDE2-1 never made it in
        result = hw_check.evaluate_aprs_round(sent, "WIDE1-1,WIDE2-1", pasted, 1)
        assert result["path_ok"] is False
        assert result["verdict"] == "FAIL"

    def test_r2_path_with_both_digis_is_path_ok(self):
        sent = ">PK232PY P62 R2 12:00:00"
        pasted = f"WB1ABC>APZ232,WIDE1-1,WIDE2-1:{sent}"
        result = hw_check.evaluate_aprs_round(sent, "WIDE1-1,WIDE2-1", pasted, 1)
        assert result["path_ok"] is True
        assert result["verdict"] == "PASS"

    def test_no_path_check_requested_leaves_path_ok_none(self):
        sent = ">PK232PY P62 R1 12:00:00"
        result = hw_check.evaluate_aprs_round(sent, None, f"WB1ABC>APZ232:{sent}", 1)
        assert result["path_ok"] is None

    def test_empty_pasted_text_is_info_not_pass_or_fail(self):
        result = hw_check.evaluate_aprs_round(">PK232PY P62 R1 x", None, "", 0)
        assert result["verdict"] == "INFO"
        assert result["info_exact"] is None
        assert result["path_ok"] is None
        assert result["trailing_cr"] is None

    def test_whitespace_only_pasted_text_is_also_info(self):
        result = hw_check.evaluate_aprs_round(">PK232PY P62 R1 x", None, "   \n  ", 0)
        assert result["verdict"] == "INFO"


class TestBuildAprsR3Info:
    """P62, Teil D - the charset probe must cover every printable ASCII
    character, not just the punctuation the spec's own example text
    happens to show (that example alone omits digits and almost every
    letter - see build_aprs_r3_info()'s own docstring)."""

    def test_covers_every_printable_ascii_character(self):
        info = hw_check.build_aprs_r3_info()
        covered = set(info)
        expected = {chr(c) for c in range(0x21, 0x7F)}
        missing = expected - covered
        assert not missing, f"missing characters: {sorted(missing)}"

    def test_is_a_single_line_with_no_embedded_newline(self):
        info = hw_check.build_aprs_r3_info()
        assert "\n" not in info and "\r" not in info

    def test_starts_and_ends_as_specified(self):
        info = hw_check.build_aprs_r3_info()
        assert info.startswith(">P62 R3 ")
        assert info.endswith(" END")


class TestBuildAprsR4Info:
    """P62, Teil D - the length probe's body (everything before the
    ' END' end marker) must be exactly 200 characters."""

    def test_body_before_end_marker_is_exactly_200_chars(self):
        info = hw_check.build_aprs_r4_info()
        assert info.endswith(" END")
        body = info[: -len(" END")]
        assert len(body) == 200

    def test_custom_body_len_is_honoured(self):
        info = hw_check.build_aprs_r4_info(body_len=50)
        body = info[: -len(" END")]
        assert len(body) == 50

    def test_starts_with_the_specified_prefix(self):
        info = hw_check.build_aprs_r4_info()
        assert info.startswith(">P62 R4 ")


class TestAprsDryRun:
    """P62, Definition of Done - --dry-run opens no port and sends
    nothing for all three new subcommands."""

    def test_aprs_query_dry_run_touches_no_port(self):
        session, log = _dry_run_session()
        hw_check.test_aprs_query(session, log)
        assert session.sm.is_connected is False
        assert ("T138", "INFO", "dry-run, nothing sent") in log.findings

    def test_aprs_tx_dry_run_touches_no_port(self):
        session, log = _dry_run_session()
        hw_check.test_aprs_tx(session, log)
        assert session.sm.is_connected is False
        assert ("T139", "INFO", "dry-run, nothing sent") in log.findings

    def test_aprs_reject_dry_run_touches_no_port(self):
        session, log = _dry_run_session()
        hw_check.test_aprs_reject(session, log)
        assert session.sm.is_connected is False
        assert ("T140", "INFO", "dry-run, nothing sent") in log.findings


class TestUnFrameComesFromHostModeProtocol:
    """P62, Teil D - the UN frame aprs_query (A.3) and aprs_tx build must
    be HostModeProtocol.cmd_unproto()'s own bytes, never a second,
    independently-assembled copy of the same frame."""

    def test_aprs_query_a3_un_frame_matches_cmd_unproto(self):
        session, log = _dry_run_session()
        recorded: list = []
        session.send_frame = lambda frame, note="": recorded.append(frame)

        hw_check.test_aprs_query(session, log)

        expected = hw_check.HostModeProtocol.cmd_unproto(
            "APZ232 VIA WIDE1-1,WIDE2-1"
        )
        assert expected in recorded

    def test_aprs_tx_un_frames_match_cmd_unproto_for_every_round(self):
        session, log = _dry_run_session()
        recorded: list = []
        session.send_frame = lambda frame, note="": recorded.append(frame)

        hw_check.test_aprs_tx(session, log)

        for round_name in hw_check._APRS_TX_ROUNDS:
            path, _info, _via = hw_check._aprs_tx_round_spec(round_name)
            expected = hw_check.HostModeProtocol.cmd_unproto(path)
            assert expected in recorded, f"{round_name}: UN frame not found"

    def test_cf_frames_use_build_command_not_a_second_builder(self):
        session, log = _dry_run_session()
        recorded: list = []
        session.send_frame = lambda frame, note="": recorded.append(frame)

        hw_check.test_aprs_query(session, log)

        assert hw_check.HostModeProtocol.build_command(b"CF", b"NONE") in recorded
        assert hw_check.HostModeProtocol.build_command(b"CF", b"ALL") in recorded
