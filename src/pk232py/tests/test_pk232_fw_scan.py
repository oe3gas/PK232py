# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""P88 Teil D - tools/pk232_fw_scan.py reads the command matrix, never probes a danger /
transmitting / mode command, ends every line with CR only and fills only the ? cells.

tools/ is not a package - see test_hw_check.py for why sys.path is extended."""

from __future__ import annotations

import csv
import dataclasses
import sys
from pathlib import Path

import pytest

from pk232py.comm import command_matrix as cm

_TOOLS = Path(__file__).resolve().parents[3] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import pk232_fw_scan as scan  # noqa: E402

B, A, C = "01.AUG.91", "13.SEP.95", "30.12.1988"
NOT_PROBED_KINDS = ("danger", "action_tx", "mode")


@pytest.fixture(autouse=True)
def _no_real_pauses(monkeypatch):
    """The scanner pauses for the TNC (0.03 s per command, 0.6 s after RESTART): not here."""
    monkeypatch.setattr(scan.time, "sleep", lambda seconds: None)


class TestPlan:

    def test_the_command_list_is_the_matrix(self):
        names = {c.name for c in scan.plan()}
        matrix = cm.all_entries()
        assert names <= set(matrix)
        assert {n for n, e in matrix.items() if e.kind == "param"} <= names

    def test_amotr_is_gone(self):
        assert "AMOTR" not in {c.name for c in scan.plan()}
        assert not hasattr(scan, "COMMAND_DB")

    def test_never_a_danger_transmitting_or_mode_command(self):
        for c in scan.plan(immediate=True):
            assert cm.kind(c.name) not in NOT_PROBED_KINDS, c.name
        assert {"CALIBRATE", "TRANS"} <= scan.NEVER_AUTO
        names = {c.name for c in scan.plan(immediate=True)}
        assert not names & scan.NEVER_AUTO

    def test_immediate_commands_only_on_request(self):
        assert not [c for c in scan.plan() if c.kind == "immediate"]
        assert [c for c in scan.plan(immediate=True) if c.kind == "immediate"]

    def test_grouped_by_operating_mode(self):
        plan = scan.plan()
        ranks = [scan.GROUP_ORDER.index(c.group) for c in plan]
        assert ranks == sorted(ranks)
        assert {c.group for c in plan} <= set(scan.GROUP_ORDER)

    def test_one_group_can_be_selected(self):
        assert {c.group for c in scan.plan(only_group="fax")} == {"fax"}


class TestMockRun:
    """The scan against the mock firmware: what is written to the 'port'."""

    @staticmethod
    def _run(release, **kw):
        t = scan.MockTransport(release)
        rep = scan.run_scan(t, f"MOCK:{release}", progress=False, **kw)
        return t, rep

    @pytest.mark.parametrize("release", cm.RELEASES)
    def test_nothing_dangerous_is_ever_written(self, release):
        t, _rep = self._run(release, immediate=True)
        lines = {d.decode("latin-1").strip() for d in t.sent}     # whole command lines
        for name in [n for n, e in cm.all_entries().items() if e.kind in NOT_PROBED_KINDS]:
            # RESTART (banner) and the mode switch of a group change are the tool's own
            if name in ("RESTART", "BAUDOT", "AMTOR", "MORSE", "FAX", "NAVTEX", "SIGNAL", "PACKET"):
                continue
            assert name not in lines, name
        assert not lines & scan.NEVER_AUTO

    @pytest.mark.parametrize("release", cm.RELEASES)
    def test_every_command_line_ends_with_cr_only(self, release):
        t, _rep = self._run(release)
        for data in t.sent:
            assert b"\n" not in data, data

    def test_the_csv_names_release_device_and_date(self, tmp_path):
        _t, rep = self._run(A)
        path = tmp_path / "scan.csv"
        scan.write_csv(rep, str(path))
        with open(path, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        assert rows and {"release", "device", "date"} <= set(rows[0])
        assert {r["release"] for r in rows} == {A}
        assert {r["device"] for r in rows} == {"A"}

    def test_a_gated_command_is_reported_expert_not_unknown(self):
        t = scan.MockTransport(A)
        rep = scan.run_scan(t, "MOCK", progress=False)
        by_name = {r["name"]: r["result"] for r in rep.rows}
        assert by_name["ILFPACK"] in ("SUPPORTED", "EXPERT_GATED")      # unlocked, then asked
        assert scan.classify("ILFPACK\r\n?EXPERT command\r\ncmd:") == "EXPERT_GATED"
        assert scan.classify("EXPERT\r\n?What?\r\ncmd:") == "UNSUPPORTED"
        assert scan.classify("") == "ERROR"


class TestUpdateMatrix:

    @staticmethod
    def _rows(**results):
        return [{"name": n, "result": r} for n, r in results.items()]

    def test_only_unknown_cells_are_filled_and_evidence_is_written(self):
        entries = cm.all_entries()
        assert entries["XLENGTH"].fw[C] == "?"
        new, filled, conflicts = scan.apply_to_matrix(
            entries, self._rows(XLENGTH="SUPPORTED", MAILDROP="UNSUPPORTED"), C, "2026-10-08", "C", "x.csv")
        assert not conflicts and filled == 1                  # MAILDROP on C is already no
        assert new["XLENGTH"].fw[C] == "yes"
        assert "fw_scan 20261008" in new["XLENGTH"].ev[C] and "Release 30.12.1988" in new["XLENGTH"].ev[C]

    def test_an_existing_cell_and_its_evidence_are_never_overwritten(self):
        entries = cm.all_entries()
        before = entries["ARQTOL"]                            # no on B (T155), yes on A
        new, filled, conflicts = scan.apply_to_matrix(
            entries, self._rows(ARQTOL="SUPPORTED"), A, "2026-10-08", "A", "x.csv")
        assert filled == 0 and not conflicts
        assert new["ARQTOL"] == before

    def test_a_contradiction_aborts_with_a_list_and_changes_nothing(self):
        entries = cm.all_entries()
        new, filled, conflicts = scan.apply_to_matrix(
            entries, self._rows(ARQTOL="SUPPORTED", XLENGTH="SUPPORTED"), B, "2026-10-08", "B", "x.csv")
        assert filled == 0 and len(conflicts) == 1 and "ARQTOL" in conflicts[0]
        assert new == entries                                  # XLENGTH was not filled either

    def test_expert_and_yes_are_not_a_contradiction(self):
        # the scan unlocks EXPERT first: a gated command then answers like any other
        entries = cm.all_entries()
        assert entries["ILFPACK"].fw[A] == "expert"
        _new, filled, conflicts = scan.apply_to_matrix(
            entries, self._rows(ILFPACK="SUPPORTED"), A, "2026-10-08", "A", "x.csv")
        assert filled == 0 and not conflicts

    def test_error_and_not_probed_are_ignored(self):
        _new, filled, conflicts = scan.apply_to_matrix(
            cm.all_entries(), self._rows(XLENGTH="ERROR", MARK="NOT_PROBED"), C, "2026-10-08", "C", "x.csv")
        assert filled == 0 and not conflicts

    def test_a_release_that_is_no_column_is_refused(self):
        with pytest.raises(ValueError, match="column"):
            scan.apply_to_matrix(cm.all_entries(), [], "99.XXX.99", "2026-10-08", "?", "x.csv")


class TestCommandLine:

    def test_update_matrix_never_runs_on_the_mock(self, capsys):
        assert scan.main(["--selftest", "1995", "--update-matrix"]) == 2
        assert "mock" in capsys.readouterr().err.lower()

    def test_plan_needs_no_device(self, capsys):
        assert scan.main(["--plan"]) == 0
        out = capsys.readouterr().out
        assert "CALIBRATE" in out and "never" in out.lower()

    def test_selftest_runs(self, capsys):
        assert scan.main(["--selftest", "1991"]) == 0
        assert "01.AUG.91" in capsys.readouterr().out
