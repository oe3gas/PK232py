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

_TOOLS_DIR = Path(__file__).resolve().parents[3] / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import hw_check  # noqa: E402


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
    def test_restores_original_value_after_normal_action(self):
        calls: list[str] = []

        def query():
            return "1"

        def set_value(v):
            calls.append(v)

        def action():
            calls.append("action")

        original = hw_check.run_with_restore(query, set_value, "4", action)

        assert original == "1"
        assert calls == ["4", "action", "1"]

    def test_restores_original_value_even_if_action_raises(self):
        calls: list[str] = []

        def query():
            return "0"

        def set_value(v):
            calls.append(v)

        def action():
            calls.append("action")
            raise RuntimeError("simulated failure mid-test")

        with pytest.raises(RuntimeError, match="simulated failure"):
            hw_check.run_with_restore(query, set_value, "9", action)

        # The set-to-new-value and the restore-to-original must both have
        # happened, in order, despite the exception.
        assert calls == ["9", "action", "0"]

    def test_restores_even_if_set_value_itself_flakes_only_the_first_time(self):
        # Documents that set_value's OWN failures are not swallowed - only
        # action()'s are guaranteed a restore attempt afterwards.
        state = {"n": 0}

        def query():
            return "orig"

        def set_value(v):
            state["n"] += 1

        def action():
            pass

        hw_check.run_with_restore(query, set_value, "new", action)
        assert state["n"] == 2  # once for "new", once for the restore
