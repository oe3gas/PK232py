# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""Unit tests for tools/hw_check.py's mnemonic_probe (P80 Teil D, T166/T167):
the scope rules (NO transmitting mnemonic, PACTOR-only items), the pure
evaluation helpers, the dry run and the log re-evaluation.

tools/ is not a package - see test_hw_check.py for why sys.path is extended.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from pk232py.comm.host_params import HOST_PARAMS
from pk232py.comm.hostmode import HostModeProtocol
from pk232py.comm.mnemonic_registry import REGISTRY
from pk232py.config import AppConfig

_TOOLS_DIR = Path(__file__).resolve().parents[3] / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import hw_check  # noqa: E402

_APP = QApplication.instance() or QApplication(sys.argv[:1])


def _modes():
    return hw_check.mnemonic_probe_mode_frames()


class TestScope:
    def test_exactly_the_requested_mode_switches_in_order(self):
        assert tuple(mn for mn, *_ in _modes()) == hw_check._MP_MODE_ORDER == (
            "BA", "AS", "MO", "AM", "PT", "FA", "SI", "TV", "NA", "NE")

    def test_pt_is_the_only_pactor_only_mode(self):
        assert [mn for mn, _l, _f, needs in _modes() if needs] == ["PT"]

    def test_both_navtex_candidates_are_tried(self):
        mns = [mn for mn, *_ in _modes()]
        assert "NA" in mns and "NE" in mns

    def test_mode_frames_are_the_apps_own(self):
        by = {mn: frame for mn, _l, frame, _n in _modes()}
        assert by["BA"] == HostModeProtocol.cmd_baudot()
        # NE and PT are literals since P80b (T166/T167: both are parameters)
        assert by["NE"][2:4] == b"NE" and by["PT"][2:4] == b"PT"

    def test_no_transmitting_or_action_mnemonic_is_ever_sent(self):
        """The whole probe: modes, candidate parameters, MID scan candidates,
        queries. No registry entry with transmits=True and no kind 'action'
        (those get their own package with confirm_tx)."""
        sent = {frame[2:4] for _mn, _l, frame, _n in _modes()}
        sent |= {p.mnemonic for p in hw_check.mnemonic_probe_candidates()}
        sent |= set(hw_check.mid_scan_candidates())
        sent |= {b"MH", b"PN"}
        for mn in sent:
            entry = REGISTRY.get(mn)
            if entry is None:
                continue                      # a scan candidate nobody uses yet
            assert not entry.transmits, mn
            assert entry.kind != "action", mn

    def test_mi_is_not_probed_as_a_parameter(self):
        mns = {p.mnemonic for p in hw_check.mnemonic_probe_candidates()}
        assert b"MI" not in mns

    def test_only_int_and_bool_candidates_can_be_set(self):
        for p in hw_check.mnemonic_probe_candidates():
            value = hw_check.choose_test_value(p, "1" if p.kind == "int" else "ON")
            if p.kind in ("text", "char", "call"):
                assert value is None, p.name

    def test_mid_scan_skips_every_known_mnemonic(self):
        cand = set(hw_check.mid_scan_candidates())
        known = {p.mnemonic for p in HOST_PARAMS if p.mnemonic} | set(REGISTRY)
        assert not cand & known
        assert all(len(m) == 2 and m.startswith(b"M") for m in cand)


class TestPureHelpers:
    def test_mode_switch_classification(self):
        c = hw_check.classify_mode_switch
        assert c("OPPA", "OPBA", "OPPA") == "changed_and_returned"
        assert c("OPPA", "OPPA", "OPPA") == "unchanged"
        assert c("OPPA", "OPBA", "OPBA") == "not_returned"
        assert c("OPPA", "", "") == "no_answer"

    def test_mid_scan_hits_need_the_exact_value(self):
        answers = {b"MA": b"MA 7", b"MB": b"MB 70", b"MC": None, b"MJ": b"XX 7"}
        assert hw_check.mid_scan_hits(answers, "7") == ["MA"]

    def test_tag_follows_the_device(self):
        class S:
            class sm:
                has_pactor = True
        assert hw_check._mp_tag(S) == "T167"
        S.sm.has_pactor = False
        assert hw_check._mp_tag(S) == "T166"


class TestDryRun:
    def test_dry_run_sends_nothing_and_walks_the_five_steps(self, capsys):
        log = hw_check.RunLog(None)
        session = hw_check.Session("DRYRUN", 9600, True, log, AppConfig())
        hw_check.test_mnemonic_probe(session, log, "all")
        out = capsys.readouterr().out
        assert "STEP 5 of 5" in out and "(mode NE NAVTEX" in out
        assert not session.sm.is_connected


class TestReevaluate:
    def test_log_lines_become_registry_evidence_lines(self, tmp_path):
        log = tmp_path / "x.log"
        log.write_text(
            "[1] device: release=01.AUG.91  pactor=no  defaults=no  (source: banner)\n"
            "[2] INFO: T166 mode BA -- changed_and_returned -- BAUDOT op='OPBA'\n"
            "[3] SKIPPED: T166 mode PT -- PACTOR: this device has no PACTOR\n"
            "[4] INFO: T166 query MH -- frames=[b'MH']\n", encoding="utf-8")
        lines: list = []
        verdicts = hw_check.reevaluate_mnemonic_log(log, out=lines.append)
        assert verdicts == {"BA": "changed_and_returned", "MH": "answered"}
        assert any("release 01.AUG.91" in ln for ln in lines)
