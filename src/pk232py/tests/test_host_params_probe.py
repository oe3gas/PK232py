# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""Tests for comm/host_params.py and tools/hw_check.py's host_params_probe
(P71): table coverage of ParamsUploader, evaluation of the probe's
answers, and the --dry-run frame lists. No port, nothing sent.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QApplication

from pk232py.comm.host_params import HOST_PARAMS, HostParam, param_by_name
from pk232py.comm.params_uploader import ParamsUploader
from pk232py.config import AppConfig

_TOOLS_DIR = Path(__file__).resolve().parents[3] / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import hw_check  # noqa: E402

_APP = QApplication.instance() or QApplication(sys.argv[:1])


def _full_config() -> AppConfig:
    """A config for which _build_commands() emits EVERY optional command."""
    cfg = AppConfig()
    cfg.tnc.utc_tnc_time = True
    hf = cfg.hf_packet
    hf.mycall = "OE3GAS"
    hf.unproto, hf.btext, hf.ctext = "CQ", "b", "c"
    for f in ("cfrom", "dfrom", "mfrom", "mto"):
        setattr(hf, f + "_mode", "ALL")
    cfg.pactor.myptcall = "OE3GAS"
    cfg.amtor.myselcal, cfg.amtor.myaltcal, cfg.amtor.myident = "ABCD", "EFGH", "OE3G"
    cfg.baudot.aab = "ON"
    cfg.maildrop.homebbs, cfg.maildrop.mymail, cfg.maildrop.mtext = "OE3XBB", "OE3GAS", "t"
    return cfg


class TestTableCoversTheUploader:
    def test_name_sets_are_equal(self):
        commands = ParamsUploader(serial=None, config=_full_config())._build_commands(
            has_pactor=True, has_maildrop=True)
        built = {c.decode().split()[0] for c in commands}
        assert built == {p.name for p in HOST_PARAMS}

    def test_names_are_unique(self):
        names = [p.name for p in HOST_PARAMS]
        assert len(names) == len(set(names))

    def test_mnemonics_are_empty_or_two_chars(self):
        assert all(p.mnemonic == b"" or len(p.mnemonic) == 2 for p in HOST_PARAMS)

    def test_int_rows_have_a_range_and_nothing_is_verified_yet(self):
        for p in HOST_PARAMS:
            if p.kind == "int":
                assert p.lo is not None and p.hi is not None and p.lo < p.hi
            assert p.verified_releases == ()

    def test_lookup(self):
        assert param_by_name("users").mnemonic == b"UR"
        assert param_by_name("NOSUCH") is None


class TestClassifyHostParam:
    """Bytes are raw Host Mode payloads: mnemonic + value."""

    def test_verified(self):
        assert hw_check.classify_host_param(
            "USERS", b"UR10", b"UR\x00", b"UR5", "5", "5") == "verified"

    def test_bool_verified_with_on_off_in_verbose(self):
        assert hw_check.classify_host_param(
            "MRPT", b"MRN", b"MR\x00", b"MRY", "ON", "Y") == "verified"

    def test_set_ok_but_second_query_unparsed(self):
        assert hw_check.classify_host_param(
            "USERS", b"UR10", b"UR\x00", b"URx?", "5", "5") == "set_ok_query_unparsed"
        assert hw_check.classify_host_param(
            "USERS", b"UR10", b"UR\x00", None, "5", "5") == "set_ok_query_unparsed"

    def test_query_only_with_a_value(self):
        assert hw_check.classify_host_param(
            "MYCALL", b"MLOE3GAS", None, None, None, None) == "query_only"

    def test_rejected_reports_the_error_byte(self):
        assert hw_check.classify_host_param(
            "USERS", b"UR10", b"\x09", b"UR10", "10", "5") == "rejected"
        assert hw_check.rejected_code(b"\x09") == 0x09
        assert hw_check.rejected_code(b"UR\x09") == 0x09

    def test_ack_is_not_a_rejection(self):
        assert hw_check.rejected_code(b"UR\x00") is None
        assert hw_check.rejected_code(b"UR5") is None
        assert hw_check.rejected_code(None) is None

    def test_no_answer(self):
        assert hw_check.classify_host_param(
            "USERS", None, None, None, "10", "5") == "no_answer"
        assert hw_check.classify_host_param(
            "MYCALL", None, None, None, None, None) == "no_answer"

    def test_wrong_param_when_verbose_shows_another_value(self):
        assert hw_check.classify_host_param(
            "USERS", b"UR10", b"UR\x00", b"UR5", "10", "5") == "wrong_param"

    def test_unparsed_keeps_raw_bytes_out_of_the_verdict(self):
        # answer that does not start with the mnemonic - never guessed
        assert hw_check.classify_host_param(
            "MYCALL", b"\x01\x02", None, None, None, None) == "unparsed"
        assert hw_check.classify_host_param(
            "USERS", b"UR10", b"UR\x00", b"UR5", None, "5") == "unparsed"


class TestChooseTestValue:
    def test_int_is_valid_and_differs(self):
        p = param_by_name("MAXFRAME")
        v = int(hw_check.choose_test_value(p, "3"))
        assert p.lo <= v <= p.hi and v != 3

    def test_int_at_upper_bound_goes_down(self):
        p = param_by_name("MAXFRAME")
        assert hw_check.choose_test_value(p, "7") == "6"

    def test_bool_is_inverted(self):
        p = param_by_name("MRPT")
        assert hw_check.choose_test_value(p, "ON") == "N"
        assert hw_check.choose_test_value(p, "OFF") == "Y"

    def test_btext_gets_the_marker_text(self):
        assert hw_check.choose_test_value(param_by_name("BTEXT"), "hello") == "P71"

    def test_no_original_means_nothing_is_set(self):
        assert hw_check.choose_test_value(param_by_name("USERS"), None) is None

    @pytest.mark.parametrize("name", ["MYCALL", "MYPTCALL", "MYSELCAL", "COMMAND",
                                      "CANLINE", "CANPAC", "SENDPAC", "UNPROTO",
                                      "EXPERT", "CFROM"])
    def test_never_set(self, name):
        assert hw_check.choose_test_value(param_by_name(name), "1") is None


class TestDryRunFrames:
    def test_part_a_has_a_query_for_every_row_with_a_mnemonic(self):
        frames = hw_check.host_params_probe_frames()
        queried = {n for n, kind, _ in frames if kind == "query"}
        assert queried == {p.name for p in HOST_PARAMS if p.mnemonic}

    def test_call_and_char_rows_never_get_a_set_frame(self):
        frames = hw_check.host_params_probe_frames()
        no_set = {p.name for p in HOST_PARAMS if p.kind in ("call", "char")}
        assert no_set
        assert not {n for n, kind, _ in frames if kind == "set"} & no_set

    def test_only_int_bool_and_btext_get_set_frames(self):
        frames = hw_check.host_params_probe_frames()
        for n, kind, _ in frames:
            if kind == "set":
                p = param_by_name(n)
                assert p.kind in ("int", "bool") or n == "BTEXT"

    def test_frames_come_from_the_one_frame_builder(self):
        frames = hw_check.host_params_probe_frames()
        name, kind, frame = next(f for f in frames if f[0] == "USERS" and f[1] == "query")
        assert frame == hw_check.HostModeProtocol.build_command(b"UR", b"")

    def _run(self, part, capsys):
        log = hw_check.RunLog(None)
        session = hw_check.Session("DRYRUN", 9600, True, log, AppConfig())
        hw_check.test_host_params_probe(session, log, part)
        assert session.sm.is_connected is False
        return capsys.readouterr().out, log

    def test_dry_run_part_a_prints_steps_and_sends_nothing(self, capsys):
        out, log = self._run("A", capsys)
        assert re.search(r"^STEP 1 of 2 ", out, re.M)
        assert "WHERE: " + hw_check.WHERE_PC2 not in out
        assert ("T151", "INFO", "dry-run, nothing sent") in log.findings

    def test_dry_run_part_b_has_pc2_steps_for_the_connection(self, capsys):
        out, log = self._run("B", capsys)
        heads = re.findall(r"^STEP (\d+) of (\d+) ", out, re.M)
        assert [int(n) for n, _ in heads] == list(range(1, len(heads) + 1))
        assert "WHERE: " + hw_check.WHERE_PC2 in out
        assert "OE3GAS-2" in out
        assert ("T152", "INFO", "dry-run, nothing sent") in log.findings
        for name in ("USERS", "MAXFRAME", "PACLEN", "FRACK", "RETRY", "MONITOR", "TXDELAY"):
            assert name in out
