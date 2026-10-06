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

B, A, C = "01.AUG.91", "13.SEP.95", "30.DEC.88"
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


def _unknown(entries, release, *names):
    """entries with these cells set back to ? (the shipped matrix fills up as devices are scanned)."""
    out = dict(entries)
    for name in names:
        e = out[name]
        out[name] = dataclasses.replace(
            e, fw={**e.fw, release: "?"}, ev={**e.ev, release: ""})
    return out


class TestUpdateMatrix:

    @staticmethod
    def _rows(**results):
        return [{"name": n, "result": r} for n, r in results.items()]

    def test_only_unknown_cells_are_filled_and_evidence_is_written(self):
        entries = _unknown(cm.all_entries(), C, "XLENGTH")
        new, filled, conflicts = scan.apply_to_matrix(
            entries, self._rows(XLENGTH="SUPPORTED", MAILDROP="UNSUPPORTED"), C, "2026-10-08", "C", "x.csv")
        assert not conflicts and filled == 1                  # MAILDROP on C is already no
        assert new["XLENGTH"].fw[C] == "yes"
        assert "fw_scan 20261008" in new["XLENGTH"].ev[C] and "Release 30.DEC.88" in new["XLENGTH"].ev[C]

    def test_an_existing_cell_and_its_evidence_are_never_overwritten(self):
        entries = cm.all_entries()
        before = entries["ARQTOL"]                            # no on B (T155), yes on A
        new, filled, conflicts = scan.apply_to_matrix(
            entries, self._rows(ARQTOL="SUPPORTED"), A, "2026-10-08", "A", "x.csv")
        assert filled == 0 and not conflicts
        assert new["ARQTOL"] == before

    def test_a_contradiction_aborts_with_a_list_and_changes_nothing(self):
        entries = _unknown(cm.all_entries(), B, "XLENGTH")
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
            _unknown(cm.all_entries(), C, "XLENGTH", "MARK"), self._rows(XLENGTH="ERROR", MARK="NOT_PROBED"), C, "2026-10-08", "C", "x.csv")
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


# ---------------------------------------------------------------------------
# T179 (device B, 06.10.2026, hw_logs/20261006_fw_scan_B*.log): from the moment the scan
# switched to SIGNAL, 24 probes per run ended as ERROR and the late reply landed in the NEXT
# command's read. RESTART does not leave SIGNAL (the opmode survives it), so the resync did not
# help, and a '?What?' of a neighbour could be taken for the answer of a command that exists.
# ---------------------------------------------------------------------------

def _expected(release, name):
    cell = cm.exists(name, release)
    return "UNSUPPORTED" if cell == "no" else "SUPPORTED"      # EXPERT is unlocked by the scan


class TestSignalMode:

    def test_the_modeless_groups_are_not_probed_in_signal(self):
        t = scan.MockTransport(B, slow_in_signal=True)
        scan.run_scan(t, "MOCK", progress=False)
        opmode = None
        for data in t.sent:
            name = data.decode("latin-1").strip().upper()
            if name in scan.MODE_ENTRY.values():
                opmode = name
            elif opmode is not None and name in {
                    c.name for c in scan.plan() if c.group in ("global", "maildrop", "pactor", "other")}:
                assert opmode == "PACKET", f"{name} was probed in {opmode}"

    def test_no_error_and_every_answer_right_with_a_slow_signal_mode(self):
        t = scan.MockTransport(B, slow_in_signal=True)
        rep = scan.run_scan(t, "MOCK", progress=False)
        assert [r["name"] for r in rep.rows if r["result"] == "ERROR"] == []
        wrong = [(r["name"], r["result"]) for r in rep.rows if r["result"] != _expected(B, r["name"])]
        assert wrong == []

    def test_the_scan_goes_back_to_packet_at_the_end(self):
        t = scan.MockTransport(B, slow_in_signal=True)
        scan.run_scan(t, "MOCK", progress=False)
        assert t.opmode == "PACKET"


class TestAnswerBelongsToTheCommand:

    def test_a_late_reply_is_waited_for(self):
        t = scan.MockTransport(A, late={"ECHO", "USERS"})
        rep = scan.run_scan(t, "MOCK", progress=False)
        by = {r["name"]: r["result"] for r in rep.rows}
        assert by["ECHO"] == by["USERS"] == "SUPPORTED"

    def test_a_reply_that_never_comes_is_error_never_unsupported(self):
        t = scan.MockTransport(A, silent={"ECHO"})
        rep = scan.run_scan(t, "MOCK", progress=False)
        assert {r["name"]: r["result"] for r in rep.rows}["ECHO"] == "ERROR"

    def test_a_neighbours_what_is_not_taken_for_the_answer(self):
        # PTOVER does not exist on B; its late '?What?' must never make PTUP... or the next
        # command that does exist look unsupported.
        t = scan.MockTransport(B, late={"PTOVER"}, silent={"XLENGTH"})
        rep = scan.run_scan(t, "MOCK", progress=False)
        for r in rep.rows:
            assert r["result"] in (_expected(B, r["name"]), "ERROR"), (r["name"], r["result"])

    def test_answer_to_needs_the_own_echo_first(self):
        assert scan.answer_to("USERS", "USERS\r\nUSers     1\r\ncmd:") == ("\r\nUSers     1\r\n", True)
        assert scan.answer_to("PTUP", "PTOVER\r\nPTROUND\r\nPTUP\r\n?What?\r\ncmd:?What?\r\ncmd:?What?\r\ncmd:") is None
        assert scan.answer_to("USERS", "") is None
        # stale prompts and SIAM output in front of the echo belong to nobody
        assert scan.answer_to("CODE", "cmd:noise\r\n0.42: 193 baud, \r\nCODE\r\nCODe 0\r\ncmd:")[1] is True

    def test_an_answer_without_the_prompt_is_not_complete(self):
        assert scan.answer_to("USERS", "USERS\r\nUSers     1\r\n") == ("\r\nUSers     1\r\n", False)


class TestDebugLogIsComplete:

    def test_main_closes_the_log_with_an_end_marker(self, tmp_path):
        log = tmp_path / "scan.log"
        assert scan.main(["--selftest", "1991", "--debug", str(log)]) == 0
        lines = log.read_text(encoding="utf-8").splitlines()
        assert lines[-1].startswith("# end of log")
        assert sum("DECIDE" in ln for ln in lines) == len(scan.plan())

    def test_a_failure_still_closes_the_log(self, tmp_path, monkeypatch):
        log = tmp_path / "scan.log"

        def boom(*a, **k):
            raise OSError("port busy")

        monkeypatch.setattr(scan, "SerialTransport", boom)
        with pytest.raises(OSError):
            scan.main(["--port", "COM99", "--debug", str(log)])
        assert log.read_text(encoding="utf-8").splitlines()[-1].startswith("# end of log")


class TestFilledCounter:
    """T179 run 3: the report said '0 cells filled' although the matrix cells were set - the
    cells had been filled by an earlier call with the same CSV (its MATRIX column already showed
    them). The counter counts what THIS call changed; a repeated call counts 0."""

    @staticmethod
    def _rows(**results):
        return [{"name": n, "result": r} for n, r in results.items()]

    def test_the_first_call_counts_what_it_filled_and_a_repeat_counts_zero(self):
        entries = _unknown(cm.all_entries(), B, "AUTOBAUD", "AWLEN", "TRFLOW")
        rows = self._rows(AUTOBAUD="SUPPORTED", AWLEN="SUPPORTED", TRFLOW="UNSUPPORTED")
        once, filled, conflicts = scan.apply_to_matrix(entries, rows, B, "2026-10-06", "B", "run3.csv")
        assert (filled, conflicts) == (3, [])
        twice, filled_again, conflicts = scan.apply_to_matrix(once, rows, B, "2026-10-06", "B", "run3.csv")
        assert (filled_again, conflicts) == (0, [])
        assert twice == once                                   # evidence untouched, nothing written twice


# ---------------------------------------------------------------------------
# T180, first try on device C (30.DEC.88), 06.10.2026: no sync. The scanner's first byte was
# Ctrl-C; device C waits after power-on for '*' (autobaud measurement) and stays deaf when
# anything else comes first (operator: PuTTY, a lone '*' wakes it). The app does it right: step 1
# of the detection chain is '*' without CR. The scanner now uses the same order.
# ---------------------------------------------------------------------------

class TestWakeLikeTheApp:

    def test_the_first_byte_is_a_lone_star_and_ctrl_c_comes_later(self):
        t = scan.MockTransport(C, needs_star_first=True)
        scan.capture_banner(t)
        assert t.sent[0] == b"*"
        assert b"\r" not in t.sent[0]                       # '*' without CR, as in the app

    def test_a_tnc_that_only_hears_a_first_star_is_scanned(self):
        t = scan.MockTransport(C, needs_star_first=True)
        rep = scan.run_scan(t, "MOCK", progress=False)
        assert rep.release == C
        assert [r["name"] for r in rep.rows if r["result"] == "ERROR"] == []
        assert {r["result"] for r in rep.rows} <= {"SUPPORTED", "UNSUPPORTED"}

    def test_the_old_order_would_have_failed_on_such_a_tnc(self):
        # the mock IS the T180 device: anything but '*' first makes it deaf for good
        t = scan.MockTransport(C, needs_star_first=True)
        t.write(scan.CTRL_C)
        t.write(scan.verbose_line("RESTART"))
        assert t.read_idle() == ""
        t.write(scan.STAR)
        assert t.read_idle() == ""

    def test_an_awake_tnc_at_the_prompt_is_found_with_the_star_too(self):
        t = scan.MockTransport(B)
        assert "cmd:" in scan.wake(t)
        assert t.sent[0] == b"*"

    def test_the_fallback_steps_follow_the_app_after_the_star(self):
        # a TNC that does not answer '*' but answers a CR: step 2 of the chain
        t = scan.MockTransport(B, ignores_star=True)
        assert "cmd:" in scan.wake(t)
        assert t.sent[:2] == [b"*", b"\r"]

    def test_converse_is_left_with_the_command_character_only_after_star_and_cr(self):
        t = scan.MockTransport(B, in_converse=True)
        assert "cmd:" in scan.wake(t)
        assert t.sent[:2] == [b"*", b"\r"]
        assert t.sent[2] == scan.CTRL_C + b"\r"             # step 2b: COMMAND char + CR

    def test_no_tnc_at_all_is_a_clear_error(self):
        with pytest.raises(scan.ScanError, match="PK-232"):
            scan.wake(scan.MockTransport(B, deaf=True))


class TestRestartWaitsForTheBanner:

    def test_a_slow_banner_is_waited_for_not_cut_at_a_fixed_pause(self):
        t = scan.MockTransport(B, banner_late_reads=2)
        assert scan.banner_release(scan.restart_for_banner(t)) == B

    def test_the_star_after_restart_is_sent_only_when_the_banner_does_not_come(self):
        quick = scan.MockTransport(B)
        scan.restart_for_banner(quick)
        assert scan.STAR not in quick.sent                  # banner came by itself

        needs = scan.MockTransport(C, restart_needs_star=True)
        banner = scan.restart_for_banner(needs)
        assert scan.banner_release(banner) == C
        assert needs.sent == [scan.verbose_line("RESTART"), scan.STAR]

    def test_the_whole_scan_survives_a_tnc_that_wants_a_star_after_restart(self):
        t = scan.MockTransport(C, needs_star_first=True, restart_needs_star=True)
        rep = scan.run_scan(t, "MOCK", progress=False)
        assert rep.release == C and not [r for r in rep.rows if r["result"] == "ERROR"]
