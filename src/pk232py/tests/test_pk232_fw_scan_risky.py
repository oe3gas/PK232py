# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""P89 - tools/pk232_fw_scan.py --all: every command is probed, also the ones that change the
operating mode, key the transmitter or break the session. The TNC has no radio connected (the
operator confirms it, twice), so the interesting part is what each command DOES and how the
command mode is reached again. The table of ways back (RECOVERY) is the thing being measured.

Mock TNCs with the behaviour of each kind and a simulated clock: the transparent mode that only a
paced 3 x Ctrl-C leaves, CALIBRATE that returns on Q or after 60 s, a command after which the TNC
stays silent until the operator power-cycles it. tools/ is not a package - see test_hw_check.py."""

from __future__ import annotations

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


class Clock:
    """The simulated time: reads of the mock and the scanner's pauses advance it."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(scan, "_clock", c)
    monkeypatch.setattr(scan, "_sleep", c.advance)
    monkeypatch.setattr(scan.time, "sleep", lambda seconds: None)
    return c


def _cmd(name):
    e = cm.entry(name)
    return scan.Cmd(name, scan.GROUP_OF.get(name, "other"), e.kind, e.abbrev)


def _probe(t, name, **kw):
    return scan.probe_risky(t, _cmd(name), mycall=kw.pop("mycall", "OE3GAS"),
                            confirm_power_cycle=kw.pop("confirm", lambda: None), **kw)


# ---------------------------------------------------------------- Teil A

class TestOperatorCheck:

    def test_both_confirmations_are_needed_one_by_one(self):
        asked = []

        def ask(prompt):
            asked.append(prompt)
            return "yes"
        assert scan.operator_checks(ask) is True
        assert len(asked) == 2
        assert "radio" in asked[0].lower() and "power-cycle" in asked[1].lower()

    def test_a_no_stops_at_once(self):
        asked = []

        def ask(prompt):
            asked.append(prompt)
            return "no"
        assert scan.operator_checks(ask) is False
        assert len(asked) == 1                               # the second is not even asked

    def test_only_the_word_yes_counts(self):
        for answer in ("", "y", "ok", "YES please", "1"):
            assert scan.operator_checks(lambda p, a=answer: a) is False

    def test_all_without_the_confirmations_exits_5_and_never_opens_the_port(self, monkeypatch, capsys):
        def boom(*a, **k):
            raise AssertionError("the port must not be opened")
        monkeypatch.setattr(scan, "SerialTransport", boom)
        monkeypatch.setattr(scan, "_ask", lambda prompt: "no")
        assert scan.main(["--port", "COM99", "--all"]) == 5
        assert "radio" in capsys.readouterr().err.lower()

    def test_the_mock_needs_no_confirmation(self, clock):
        assert scan.main(["--selftest", "1991", "--all"]) == 0


# ---------------------------------------------------------------- the plan and the table

class TestRiskyPlan:

    def test_every_command_that_was_never_sent_is_in_it(self):
        planned = {c.name for c in scan.risky_plan()}
        never = {n for n, _why in scan.never_probed()}
        assert planned == never and {"TRANS", "CALIBRATE", "RESTART", "RESET", "REINIT"} <= planned

    def test_from_the_harmless_to_the_most_delicate(self):
        names = [c.name for c in scan.risky_plan()]
        kinds = [cm.kind(n) for n in names]
        modes = [i for i, k in enumerate(kinds) if k == "mode"]
        actions = [i for i, k in enumerate(kinds) if k == "action_tx"]
        assert max(modes) < min(actions)                      # mode switches first, then the transmitting ones
        assert names[-6:] == ["MEMORY", "TRANS", "CALIBRATE", "RESTART", "RESET", "REINIT"]

    def test_plan_all_leaves_nothing_out(self, capsys):
        assert scan.main(["--plan", "--all"]) == 0
        out = capsys.readouterr().out
        assert "omitted" not in out.lower() and "never sent" not in out.lower()
        for name in ("TRANS", "CALIBRATE", "RESTART", "XMIT", "BAUDOT"):
            assert name in out

    def test_the_plan_without_all_still_lists_what_is_not_sent(self, capsys):
        scan.main(["--plan"])
        assert "never sent" in capsys.readouterr().out.lower()


class TestRecoveryTable:

    @staticmethod
    def _labels(kind):
        return [s.label for s in scan.RECOVERY[kind]]

    def test_one_table_in_the_order_of_the_spec(self):
        assert self._labels("mode") == ["PACKET", "Ctrl-C"]
        assert self._labels("action_tx") == ["Ctrl-C", "RCVE", "DISCONNE", "PACKET"]
        assert self._labels("TRANS") == ["3xCtrl-C/CMDTIME"]
        assert self._labels("CALIBRATE") == ["Q", "Ctrl-C", "wait 65s"]
        assert self._labels("CONVERSE") == ["Ctrl-C"]
        assert self._labels("RESTART") == ["banner/*"]
        assert self._labels("danger") == ["Ctrl-C", "CR"]

    def test_transs_manual_sequence(self):
        # STABO ch. 4: pause, three COMMAND characters within CMDTIME (default 1 s), pause, then Ctrl-C
        (step,) = scan.RECOVERY["TRANS"]
        assert step.actions == (("sleep", 1.5), ("tx", scan.CTRL_C), ("sleep", 0.2), ("tx", scan.CTRL_C),
                                ("sleep", 0.2), ("tx", scan.CTRL_C), ("sleep", 1.5), ("tx", scan.CTRL_C))

    def test_every_risky_command_has_a_way_back(self):
        for c in scan.risky_plan():
            assert scan.recovery_kind(c.name, c.kind) in scan.RECOVERY, c.name

    def test_the_kinds(self):
        assert scan.recovery_kind("TRANS", "danger") == "TRANS"
        assert scan.recovery_kind("CALIBRATE", "danger") == "CALIBRATE"
        assert scan.recovery_kind("CONVERSE", "mode") == "CONVERSE"
        assert scan.recovery_kind("K", "mode") == "CONVERSE"
        for n in ("RESTART", "RESET", "REINIT"):
            assert scan.recovery_kind(n, "danger") == "RESTART"
        assert scan.recovery_kind("BAUDOT", "mode") == "mode"
        assert scan.recovery_kind("XMIT", "action_tx") == "action_tx"
        assert scan.recovery_kind("MDCHECK", "danger") == "danger"


# ---------------------------------------------------------------- Teil B / E: the probing

class TestOneCommandAtATime:

    def test_baudot_changes_the_opmode_and_packet_brings_it_back(self, clock):
        t = scan.MockTransport(B, clock=clock, risky=True)
        b = _probe(t, "BAUDOT")
        assert b.exists == "yes" and "OPMODE" in b.effect and "BAUDOT" in b.effect
        assert b.recovery == "PACKET" and b.steps == [("PACKET", True)]
        assert t.opmode == "PACKET"

    def test_the_three_seconds_after_the_command_are_recorded_raw(self, clock):
        t = scan.MockTransport(B, clock=clock, risky=True)
        b = _probe(t, "BAUDOT")
        assert b.raw and all(isinstance(ts, float) for ts, _text in b.raw)
        assert "BAUDOT" in "".join(text for _ts, text in b.raw)
        assert b.recorded_s >= 3.0                            # the recording ran its 3 s

    def test_a_command_the_firmware_does_not_know_is_no(self, clock):
        t = scan.MockTransport(C, clock=clock, risky=True)
        b = _probe(t, "ARQE")
        e = cm.entry("ARQE")
        assert b.exists == ("no" if e.fw[C] == "no" else "yes")
        assert b.recovery in ("none needed", "Ctrl-C", "PACKET")

    def test_opmode_and_mycall_are_asked_after_every_risky_command(self, clock):
        t = scan.MockTransport(B, clock=clock, risky=True)
        b = _probe(t, "BAUDOT")
        tail = [d.decode("latin-1").strip() for d in t.sent[-4:]]
        assert "OPMODE" in tail and "MYCALL" in tail
        assert b.opmode and b.mycall

    def test_every_recovery_step_is_logged(self, clock, tmp_path):
        log = scan.DebugLog(str(tmp_path / "scan.log"))
        t = scan.MockTransport(B, clock=clock, risky=True, debug=log)
        _probe(t, "BAUDOT")
        log.close()
        text = (tmp_path / "scan.log").read_text(encoding="utf-8")
        assert "RISKY BAUDOT" in text and "recovery step PACKET" in text


class TestModes:

    def test_the_transparent_mode_is_only_left_with_a_paced_triple_ctrl_c(self, clock):
        t = scan.MockTransport(B, clock=clock, risky=True)
        # the control: a hurried Ctrl-C (the July run) does NOT leave it
        t.write(scan.verbose_line("TRANS"))
        t.read_idle()                                         # the echo of the command
        for _ in range(3):
            t.write(scan.CTRL_C)
        assert t.read_idle() == "" and t.transparent
        t2 = scan.MockTransport(B, clock=clock, risky=True)
        b = _probe(t2, "TRANS")
        assert b.exists == "yes" and "transparent" in b.effect.lower()
        assert b.recovery == "3xCtrl-C/CMDTIME" and b.steps == [("3xCtrl-C/CMDTIME", True)]
        assert not t2.transparent

    def test_calibrate_is_left_with_q(self, clock):
        t = scan.MockTransport(B, clock=clock, risky=True)
        b = _probe(t, "CALIBRATE")
        assert b.exists == "yes" and b.recovery == "Q" and b.steps == [("Q", True)]

    def test_calibrate_that_ignores_q_returns_by_itself_after_60_seconds(self, clock):
        t = scan.MockTransport(B, clock=clock, risky=True, calibrate_ignores_q=True)
        b = _probe(t, "CALIBRATE")
        assert b.steps == [("Q", False), ("Ctrl-C", False), ("wait 65s", True)]
        assert b.recovery == "wait 65s"
        assert clock.now - 1000.0 >= 60.0                     # it really waited

    def test_a_transmitting_command_that_ctrl_c_does_not_stop(self, clock):
        t = scan.MockTransport(B, clock=clock, risky=True, stuck={"XMIT": "RCVE"})
        b = _probe(t, "XMIT")
        assert b.steps == [("Ctrl-C", False), ("RCVE", True)]
        assert b.recovery == "RCVE"

    def test_the_way_back_is_tried_in_the_order_of_the_table(self, clock):
        t = scan.MockTransport(B, clock=clock, risky=True, stuck={"XMIT": "PACKET"})
        b = _probe(t, "XMIT")
        assert [label for label, _ok in b.steps] == ["Ctrl-C", "RCVE", "DISCONNE", "PACKET"]
        assert [ok for _label, ok in b.steps] == [False, False, False, True]


class TestNeedsPowerCycle:

    def test_a_silent_tnc_is_not_waited_for_forever(self, clock):
        t = scan.MockTransport(C, clock=clock, risky=True, needs_star_first=True, dead_after={"XMIT"})
        t.write(scan.STAR)                                    # woken as after power-on
        calls = []

        def confirm():
            calls.append(1)
            t.power_cycle()
        b = _probe(t, "XMIT", confirm=confirm)
        assert b.recovery == "needs_power_cycle" and len(calls) == 1
        assert [ok for _label, ok in b.steps] and not any(ok for _label, ok in b.steps)

    def test_after_the_power_cycle_the_tnc_is_woken_like_the_app_and_mycall_is_set_again(self, clock):
        t = scan.MockTransport(C, clock=clock, risky=True, needs_star_first=True, dead_after={"XMIT"})
        t.write(scan.STAR)
        before = len(t.sent)
        b = _probe(t, "XMIT", confirm=t.power_cycle, mycall="OE3GAS")
        after_cycle = t.sent[before:]
        assert scan.STAR in after_cycle                       # first byte after the power cycle: '*'
        assert t.mycall == "OE3GAS"                           # the power cycle gave the factory MYCALL back
        assert b.mycall.upper().endswith("OE3GAS")

    def test_a_tnc_that_waits_for_the_star_after_restart_still_exists_by_its_banner(self, clock):
        t = scan.MockTransport(C, clock=clock, risky=True, needs_star_first=True, restart_needs_star=True)
        t.write(scan.STAR)
        b = _probe(t, "RESTART")
        assert b.exists == "yes" and "banner" in b.effect.lower() and b.recovery == "banner/*"

    def test_restart_needs_no_operator_it_returns_with_its_banner(self, clock):
        t = scan.MockTransport(B, clock=clock, risky=True)
        calls = []
        b = _probe(t, "RESTART", confirm=lambda: calls.append(1))
        assert b.recovery == "banner/*" and not calls
        assert "banner" in b.effect.lower()
        assert t.mycall == "OE3GAS"                           # RESTART resets MYCALL, the scan sets it again

    def test_a_restart_that_waits_for_the_star_gets_it(self, clock):
        t = scan.MockTransport(C, clock=clock, risky=True, needs_star_first=True, restart_needs_star=True)
        t.write(scan.STAR)
        b = _probe(t, "RESTART")
        assert b.recovery == "banner/*" and scan.STAR in t.sent[-8:]


# ---------------------------------------------------------------- the whole run and the matrix

class TestRunAll:

    def test_the_normal_queries_come_first_then_every_risky_command(self, clock):
        t = scan.MockTransport(B, clock=clock, risky=True)
        rep = scan.run_scan(t, "MOCK", progress=False, risky=True, mycall="OE3GAS",
                            confirm_power_cycle=t.power_cycle)
        names = [r["name"] for r in rep.rows]
        risky = [c.name for c in scan.risky_plan()]
        first_risky = names.index(risky[0])
        assert names[first_risky:] == risky
        assert not [r for r in rep.rows if r["result"] == "ERROR"]
        assert t.opmode == "PACKET" and not t.transparent

    def test_the_rows_carry_effect_recovery_and_raw_answer(self, clock):
        t = scan.MockTransport(B, clock=clock, risky=True)
        rep = scan.run_scan(t, "MOCK", progress=False, risky=True, mycall="OE3GAS",
                            confirm_power_cycle=t.power_cycle)
        row = next(r for r in rep.rows if r["name"] == "TRANS")
        assert row["recovery"] == "3xCtrl-C/CMDTIME" and "transparent" in row["effect"].lower() and row["raw"]

    def test_the_csv_has_the_new_columns(self, clock, tmp_path):
        t = scan.MockTransport(B, clock=clock, risky=True)
        rep = scan.run_scan(t, "MOCK", progress=False, risky=True, mycall="OE3GAS",
                            confirm_power_cycle=t.power_cycle)
        path = tmp_path / "scan.csv"
        scan.write_csv(rep, str(path))
        header = path.read_text(encoding="utf-8").splitlines()[0].split(",")
        assert {"effect", "recovery", "raw"} <= set(header)

    def test_the_selftest_with_all_runs(self, clock, capsys):
        assert scan.main(["--selftest", "1995", "--all"]) == 0
        assert "TRANS" in capsys.readouterr().out


def _unknown(entries, release, *names):
    out = dict(entries)
    for name in names:
        e = out[name]
        out[name] = dataclasses.replace(e, fw={**e.fw, release: "?"}, ev={**e.ev, release: ""},
                                        fx={**e.fx, release: ""})
    return out


class TestEffectCells:
    FX = "enters transparent mode; exit 3xCtrl-C/CMDTIME"

    @staticmethod
    def _rows(**kw):
        return [{"name": n, "result": "SUPPORTED", "fx": fx} for n, fx in kw.items()]

    def test_an_empty_effect_cell_is_filled_together_with_the_measured_cell(self):
        entries = _unknown(cm.all_entries(), B, "TRANS")
        new, filled, conflicts = scan.apply_to_matrix(entries, self._rows(TRANS=self.FX), B, "2026-10-08", "B", "x.csv")
        assert not conflicts and filled == 2                  # the measured cell and the effect cell
        assert new["TRANS"].fw[B] == "yes" and new["TRANS"].fx[B] == self.FX

    def test_an_existing_effect_is_never_overwritten(self):
        entries = _unknown(cm.all_entries(), B, "TRANS")
        once, _f, _c = scan.apply_to_matrix(entries, self._rows(TRANS=self.FX), B, "2026-10-08", "B", "x.csv")
        again, filled, conflicts = scan.apply_to_matrix(once, self._rows(TRANS=self.FX), B, "2026-10-08", "B", "x.csv")
        assert filled == 0 and not conflicts and again == once

    def test_a_different_effect_is_a_contradiction_and_nothing_is_written(self):
        entries = _unknown(cm.all_entries(), B, "TRANS", "CALIBRATE")
        once, _f, _c = scan.apply_to_matrix(entries, self._rows(TRANS=self.FX), B, "2026-10-08", "B", "x.csv")
        rows = self._rows(TRANS="prints banner; power-cycle needed", CALIBRATE="keys tones; exit Q")
        new, filled, conflicts = scan.apply_to_matrix(once, rows, B, "2026-10-08", "B", "x.csv")
        assert filled == 0 and len(conflicts) == 1 and "TRANS" in conflicts[0]
        assert new == once                                    # CALIBRATE was not filled either

    def test_a_row_without_an_effect_changes_no_effect_cell(self):
        entries = _unknown(cm.all_entries(), B, "XLENGTH")
        new, filled, _c = scan.apply_to_matrix(entries, [{"name": "XLENGTH", "result": "SUPPORTED"}], B,
                                               "2026-10-08", "B", "x.csv")
        assert filled == 1 and new["XLENGTH"].fx[B] == ""

    def test_the_effect_text_is_short_and_without_times(self):
        text = scan.fx_text("enters transparent mode", "3xCtrl-C/CMDTIME")
        assert text == self.FX
        assert scan.fx_text("prints banner", "needs_power_cycle") == "prints banner; power-cycle needed"
