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

    def test_every_mnemonic_occurs_at_most_once(self):
        # P71a E: AO was listed for ARQTMO and ARQTOL; T151 showed it is ARQTMO's
        mnemonics = [p.mnemonic for p in HOST_PARAMS if p.mnemonic]
        assert len(mnemonics) == len(set(mnemonics))
        assert param_by_name("ARQTOL").mnemonic == b""
        assert param_by_name("ARQTMO").mnemonic == b"AO"

    def test_lookup(self):
        assert param_by_name("users").mnemonic == b"UR"
        assert param_by_name("NOSUCH") is None


class TestClassifyHostParam:
    """Bytes are raw Host Mode payloads: mnemonic + value. verbose_before
    is the Pass 0 value (P71a B)."""

    def test_verified_number(self):
        # real T151 bytes, device B (01.AUG.91)
        assert hw_check.classify_host_param(
            "PACLEN", b"PL128", b"PL\x00", b"PL129", "128", "129") == "verified"

    def test_switch_without_pass_2_is_weak(self):
        assert hw_check.classify_host_param(
            "AX25L2V2", b"AVY", b"AV\x00", b"AVN", "ON", "N") == "verified_weak"

    def test_switch_with_a_matching_verbose_cross_check_is_verified(self):
        assert hw_check.classify_host_param(
            "AX25L2V2", b"AVY", b"AV\x00", b"AVN", "ON", "N",
            verbose_test="OFF") == "verified"

    def test_switch_whose_verbose_value_is_not_the_test_value_is_wrong_param(self):
        assert hw_check.classify_host_param(
            "AX25L2V2", b"AVY", b"AV\x00", b"AVN", "ON", "N",
            verbose_test="ON") == "wrong_param"

    def test_verbose_rejects_but_host_answers_is_host_only(self):
        assert hw_check.classify_host_param(
            "ARQTOL", b"AO60", None, None, None, None,
            verbose_rejected=True, mnemonic=b"AO") == "host_only"

    def test_rejected_query_shows_the_code(self):
        assert hw_check.classify_host_param(
            "EXPERT", b"EX\x07", None, None, None, None,
            verbose_rejected=True) == "rejected (0x07)"
        assert hw_check.classify_host_param(
            "DAYTIME", b"DA\x10", None, None, None, None) == "rejected (0x10)"

    def test_rejected_set_reports_the_error_byte(self):
        assert hw_check.classify_host_param(
            "USERS", b"UR10", b"\x09", b"UR10", "10", "5") == "rejected (0x09)"
        assert hw_check.rejected_code(b"\x09") == 0x09
        assert hw_check.rejected_code(b"UR\x09") == 0x09

    def test_ack_is_not_a_rejection(self):
        assert hw_check.rejected_code(b"UR\x00") is None
        assert hw_check.rejected_code(b"UR5") is None
        assert hw_check.rejected_code(None) is None

    def test_empty_text_answer_is_not_an_error_code(self):
        # 'BT\r' = empty BTEXT (T151), not error $0D
        assert hw_check.rejected_code(b"BT\r") is None
        assert hw_check.classify_host_param(
            "BTEXT", b"BT\r", None, None, "", None) == "verified_query"

    def test_query_only_text_matching_verbose_is_verified(self):
        assert hw_check.classify_host_param(
            "MYCALL", b"MLOE3GAS", None, None, "OE3GAS", None) == "verified_query"

    def test_hex_control_character_compares_unchanged(self):
        assert hw_check.classify_host_param(
            "COMMAND", b"CN$03", None, None, "$03", None) == "verified_query"

    def test_no_answer(self):
        assert hw_check.classify_host_param(
            "USERS", None, None, None, "10", "5") == "no_answer"

    def test_wrong_param_when_q1_differs_from_verbose_before(self):
        assert hw_check.classify_host_param(
            "USERS", b"UR10", b"UR\x00", b"UR5", "1", "5") == "wrong_param"

    def test_unparsed_without_a_reference_or_a_mnemonic_match(self):
        assert hw_check.classify_host_param(
            "MYCALL", b"\x01\x02", None, None, "X", None) == "unparsed"
        assert hw_check.classify_host_param(
            "USERS", b"UR10", b"UR\x00", b"UR5", None, "5") == "unparsed"

    def test_set_not_acked_and_q2_mismatch(self):
        assert hw_check.classify_host_param(
            "USERS", b"UR10", None, b"UR5", "10", "5") == "set_not_acked"
        assert hw_check.classify_host_param(
            "USERS", b"UR10", b"UR\x00", b"UR10", "10", "5") == "set_ok_query_unparsed"


class TestVerboseParserLongNames:
    def test_kilonfwd_line_is_read(self):
        # the exact line of T151 (name too long to be abbreviated)
        assert hw_check.parse_query_value(
            "KILONFWD", "KILONFWD\r\nKILONFWD  ON\r\ncmd:") == "ON"

    def test_echo_of_a_set_is_still_ignored(self):
        assert hw_check.parse_query_value("KILONFWD", "KILONFWD ON\r\n?What?\r\ncmd:") is None

    def test_empty_text_value(self):
        assert hw_check._hp_verbose_before("BTEXT", "BTEXT\r\nBText     \r\ncmd:") == ""
        assert hw_check._hp_verbose_before("BTEXT", "BTEXT\r\n?What?\r\ncmd:") is None


_T151_EXCERPT = r"""[19:00:15] >> b'EXPERT\r\n'
[19:00:15] << 'EXPERT\r\n?What?\r\ncmd:'
[19:00:16] >> b'PACLEN\r\n'
[19:00:16] << 'PACLEN\r\nPACLen    128\r\ncmd:'
[19:00:35] >> b'ARQTOL\r\n'
[19:00:35] << 'ARQTOL\r\n?What?\r\ncmd:'
[19:00:38] >> b'ARQTMO\r\n'
[19:00:38] << 'ARQTMO\r\nARQTmo    60 (60 sec.)\r\ncmd:'
[19:00:50] >> b'KILONFWD\r\n'
[19:00:50] << 'KILONFWD\r\nKILONFWD  ON\r\ncmd:'
[19:00:50] >> b'AX25L2V2\r\n'
[19:00:50] << 'AX25L2V2\r\nAX25l2v2  ON\r\ncmd:'
[19:00:51] STEP 1 of 2: T151 A.1  ask and set the parameters in Host Mode [PC 1]
[19:03:12] INFO: T151 EXPERT (EX) -- query_only q1=b'EX\x07' (45 58 07) set=none q2=none test=None verbose=None
[19:03:12] INFO: T151 PACLEN (PL) -- unparsed q1=b'PL128' (50 4c 31 32 38) set=b'PL\x00' (50 4c 00) q2=b'PL129' (50 4c 31 32 39) test='129' verbose=None
[19:03:12] INFO: T151 AX25L2V2 (AV) -- unparsed q1=b'AVY' (41 56 59) set=b'AV\x00' (41 56 00) q2=b'AVN' (41 56 4e) test='N' verbose=None
[19:03:12] INFO: T151 ARQTOL (AO) -- query_only q1=b'AO60' (41 4f 36 30) set=none q2=none test=None verbose=None
[19:03:12] INFO: T151 ARQTMO (AO) -- unparsed q1=b'AO60' (41 4f 36 30) set=b'AO\x00' (41 4f 00) q2=b'AO61' (41 4f 36 31) test='61' verbose=None
[19:03:12] INFO: T151 KILONFWD (KL) -- query_only q1=b'KLY' (4b 4c 59) set=none q2=none test=None verbose=None
[19:03:12] INFO: T151 HID (-) -- no_mnemonic
[19:03:12] === SUMMARY (copy into Testplan.md) ===
[19:03:12] INFO         T151 EXPERT (EX)  (query_only q1=b'EX\x07' (45 58 07) set=none q2=none test=None verbose=None)
"""


class TestReevaluate:
    def test_t151_excerpt(self, tmp_path):
        log = tmp_path / "t151.log"
        log.write_text(_T151_EXCERPT, encoding="utf-8")
        lines: list = []
        counts = hw_check.reevaluate_host_params_log(log, out=lines.append)
        assert counts == {
            "rejected (0x07)": 1, "verified": 2, "host_only": 1, "verified_weak": 1, "verified_query": 1,
        }
        text = "\n".join(lines)
        assert "PACLEN (PL): verified" in text
        assert "ARQTOL (AO): host_only" in text
        assert "KILONFWD (KL): verified_query" in text
        assert "AX25L2V2 (AV): verified_weak" in text

    _REAL_LOG = (Path(__file__).resolve().parents[3] / "hw_logs"
                 / "20261001_185959_host_params_probe.log")

    @pytest.mark.skipif(not _REAL_LOG.exists(),
                        reason="the real T151 log is not in this checkout")
    def test_real_t151_log_counts(self):
        counts = hw_check.reevaluate_host_params_log(self._REAL_LOG, out=lambda _l: None)
        assert counts.get("verified", 0) == 17 and counts.get("verified_weak", 0) == 20
        assert counts.get("verified_query", 0) >= 15


class TestBisectTrigger:
    def test_finds_the_single_trigger(self):
        assert hw_check.bisect_trigger(tuple("ABCDEFGH"), lambda ns: "F" in ns) == [("F",)]

    def test_nothing_breaks(self):
        assert hw_check.bisect_trigger(("A", "B"), lambda ns: False) == []

    def test_a_combination_is_reported_as_one_tuple(self):
        # halves (A,B) and (C,D) are fine alone, the whole set is not
        names = ("A", "B", "C", "D")
        assert hw_check.bisect_trigger(names, lambda ns: {"B", "C"} <= set(ns)) == [names]

    def test_two_triggers(self):
        trial = lambda ns: "B" in ns or "G" in ns   # noqa: E731
        assert hw_check.bisect_trigger(tuple("ABCDEFGH"), trial) == [("B",), ("G",)]

    def test_groups_only_name_table_rows_that_can_be_set(self):
        for _title, names in hw_check._HP_C_GROUPS:
            for n in names:
                p = param_by_name(n)
                assert p is not None and p.mnemonic and p.kind in ("int", "bool")


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

    def test_restore_frames_follow_every_set_frame(self):
        frames = hw_check.host_params_probe_frames()
        kinds = [k for _n, k, _f in frames]
        assert "restore" in kinds
        assert kinds.index("restore") > max(i for i, k in enumerate(kinds) if k == "set")
        sets = {n for n, k, _f in frames if k == "set"}
        assert {n for n, k, _f in frames if k == "restore"} == sets

    def test_dry_run_sets_leaves_host_mode_then_restores(self, capsys):
        out, _log = self._run("A", capsys)
        assert (out.index("(PACLEN set)") < out.index("leave Host Mode, verbose")
                < out.index("(PACLEN restore)") < out.rindex("leave Host Mode"))

    def test_excluded_mnemonics_get_neither_set_nor_restore(self):
        frames = hw_check.host_params_probe_frames(exclude={"UR"})
        assert not [f for f in frames if f[0] == "USERS" and f[1] != "query"]
        assert [f for f in frames if f[0] == "MAXFRAME" and f[1] == "set"]

    def test_exclude_option_rejects_an_unknown_mnemonic(self):
        with pytest.raises(SystemExit):
            hw_check.main(["host_params_probe", "--dry-run", "--exclude", "ZZ"])

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
