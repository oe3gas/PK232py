# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""Unit tests for tools/hw_check.py's eol_probe (P75 Teil 0, T175): the pure
verdict helpers, the dry run and the safety rule (nothing transmitting).

tools/ is not a package - see test_hw_check.py for why sys.path is extended.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from pk232py.config import AppConfig

_TOOLS_DIR = Path(__file__).resolve().parents[3] / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import hw_check  # noqa: E402

_APP = QApplication.instance() or QApplication(sys.argv[:1])

# T155 (device B, 20261001_202242_host_params_probe.log), copied literally.
T155 = [("PACLEN", "PACLEN\rPACLen 128\r\ncmd:"),
        ("USERS", "USERS\r?What?\r\ncmd:"),
        ("HELP", "HELP\r?What?\r\ncmd:")]


class TestVerdict:
    def test_a_normal_answer_is_ok(self):
        assert hw_check.eol_answer_ok("PACLEN\rPACLen 128\r\ncmd:")

    def test_what_and_silence_are_not_ok(self):
        assert not hw_check.eol_answer_ok("USERS\r?What?\r\ncmd:")
        assert not hw_check.eol_answer_ok("")
        assert not hw_check.eol_answer_ok("  \r\n")

    def test_sequence_names_the_failed_commands(self):
        ok, failed = hw_check.eol_sequence_verdict(T155)
        assert not ok and failed == ["USERS", "HELP"]

    def test_t155_picture_is_recognised(self):
        assert hw_check.eol_matches_t155(T155)

    def test_all_right_is_not_the_t155_picture(self):
        assert not hw_check.eol_matches_t155([(n, "x\rok") for n, _ in T155])
        assert not hw_check.eol_matches_t155([])


class TestScope:
    def test_the_five_questions_of_the_spec(self):
        assert hw_check.EOL_QUERIES == ("PACLEN", "USERS", "MAXFRAME", "MYCALL", "HELP")

    def test_il_is_the_registered_host_mnemonic(self):
        from pk232py.comm.host_params import HOST_PARAMS
        assert hw_check.EOL_IL_MNEMONIC == b"IL"
        assert any(p.name == "ILFPACK" and p.mnemonic == b"IL" for p in HOST_PARAMS)

    def test_nothing_transmitting_is_ever_sent(self):
        # CLAUDE.md rule 8: never CALIBRATE, never TRANS / CONMODE TRANS.
        src = inspect.getsource(hw_check.test_eol_probe)
        for forbidden in ("CALIBRATE", "TRANS", "CONNECT", "UNPROTO"):
            assert forbidden not in src

    def test_every_verbose_command_of_the_probe_is_cr_terminated_on_purpose(self):
        src = inspect.getsource(hw_check.test_eol_probe)
        bs = chr(92)                      # a backslash, as written in the source
        assert f'b"ILFPACK{bs}r"' in src and f'b"CONVERSE{bs}r"' in src


class TestDryRun:
    def test_dry_run_sends_nothing_and_walks_the_plan(self, capsys):
        log = hw_check.RunLog(None)
        session = hw_check.Session("DRYRUN", 9600, True, log, AppConfig())
        hw_check.test_eol_probe(session, log)
        out = capsys.readouterr().out
        assert "STEP 1 of 2" in out and "STEP 2 of 2" in out
        assert not session.sm.is_connected
        assert ("T175", "INFO", "dry-run, nothing sent") in log.findings

    def test_the_command_line_accepts_eol_probe(self):
        src = inspect.getsource(hw_check.main)
        assert '"eol_probe"' in src
