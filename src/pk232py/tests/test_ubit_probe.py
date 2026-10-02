# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""Tests for tools/hw_check.py ubit_probe (P74 Teil A, T156): the pure
helpers and the --dry-run frame plan. No port, nothing sent."""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

_TOOLS_DIR = Path(__file__).resolve().parents[3] / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import hw_check  # noqa: E402

_APP = QApplication.instance() or QApplication(sys.argv[:1])


class TestCandidates:
    def test_order_is_as_in_the_spec(self):
        assert [c for c, _ in hw_check.UBIT_CANDIDATES] == [
            b"0 N", b"0N", b"0 OFF", b"0OFF"]

    def test_each_candidate_has_its_on_form(self):
        assert dict(hw_check.UBIT_CANDIDATES) == {
            b"0 N": b"0 Y", b"0N": b"0Y", b"0 OFF": b"0 ON", b"0OFF": b"0ON"}


class TestReplyAccepted:
    def test_lone_zero_byte(self):
        assert hw_check.ubit_reply_accepted(b"\x00")

    def test_mnemonic_plus_zero_byte(self):
        assert hw_check.ubit_reply_accepted(b"UB\x00")

    def test_error_or_missing_is_not_accepted(self):
        assert not hw_check.ubit_reply_accepted(b"\x09")
        assert not hw_check.ubit_reply_accepted(b"UB0 OFF")
        assert not hw_check.ubit_reply_accepted(None)


class TestParseVerbose:
    def test_off_and_on(self):
        assert hw_check.parse_ubit0_verbose("UBIT 0\r\nUBIT 0 OFF\r\ncmd:") == "OFF"
        assert hw_check.parse_ubit0_verbose("UBIT 0 ON\r\ncmd:") == "ON"

    def test_echo_only_or_error_is_none(self):
        assert hw_check.parse_ubit0_verbose("UBIT 0\r\ncmd:") is None
        assert hw_check.parse_ubit0_verbose("?What?\r\ncmd:") is None


class TestDryRun:
    def test_frames_use_the_one_frame_builder_in_candidate_order(self):
        frames = hw_check.ubit_probe_frames()
        sets = [f for n, kind, f in frames if kind == "set"]
        assert sets == [hw_check.HostModeProtocol.build_command(b"UB", c)
                        for c, _ in hw_check.UBIT_CANDIDATES]

    def test_every_candidate_is_followed_by_the_query(self):
        kinds = [kind for _, kind, _ in hw_check.ubit_probe_frames()]
        assert kinds == ["set", "query"] * len(hw_check.UBIT_CANDIDATES)

    def test_main_dry_run_succeeds(self, capsys):
        assert hw_check.main(["ubit_probe", "--dry-run"]) == 0
        assert "T156" in capsys.readouterr().out
