# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""P89a - what T182 to T184 (--all at devices A, B, C, hw_logs/20261006_fw_all_*.log) taught:

* a refusal for a missing precondition (?need MYcall, ?need MYSELCAL, ?not while in ..., ?EXPERT command) is
  NOT an effect: the scan sets MYCALL / MYSELCAL / EXPERT before the risky part, puts everything back after,
  tries XMIT and RCVE in BAUDOT and ACHG and OVER in AMTOR, and writes what is still refused as
  ``precondition: ...`` instead of an effect;
* MDCHECK opens the MailDrop mailbox - Ctrl-C does not leave it, ``B`` does (the "(AEA PK-232M)" prompt was
  read as the banner);
* --only NAME,... runs just those commands again.

tools/ is not a package - see test_hw_check.py."""

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


def _entries():
    return cm.all_entries()


def _risky(t, **kw):
    kw.setdefault("mycall", "OE3GAS")
    kw.setdefault("confirm_power_cycle", getattr(t, "power_cycle", None))
    kw.setdefault("progress", False)
    return scan.run_risky(t, _entries(), **kw)


def _row(rows, name):
    return next(r for r in rows if r["name"] == name)


# ---------------------------------------------------------------- the tables

class TestTables:

    def test_the_modes_the_commands_need_are_in_one_table(self):
        assert scan.NEEDS_MODE == {"XMIT": "BAUDOT", "RCVE": "BAUDOT", "ACHG": "AMTOR", "OVER": "AMTOR"}

    def test_mdcheck_has_its_own_way_back_the_bye_of_the_mailbox(self):
        assert [s.label for s in scan.RECOVERY["MDCHECK"]] == ["B", "Ctrl-C"]
        assert scan.RECOVERY["MDCHECK"][0].actions == (("tx", b"B\r"),)
        assert scan.recovery_kind("MDCHECK", "danger") == "MDCHECK"

    def test_a_selcal_is_derived_from_the_callsign(self):
        assert scan.derive_selcal("OE3GAS") == "OEAS"
        assert scan.derive_selcal("DL1ABC") == "DLBC"
        assert scan.derive_selcal("NOCALL") is None and scan.derive_selcal("") is None

    def test_the_factory_callsign_counts_as_not_set(self):
        assert scan.usable_call("OE3GAS") == "OE3GAS"
        for bad in (None, "", "NOCALL", "PK232", "pk232"):
            assert scan.usable_call(bad) is None


class TestDescribing:

    def test_the_mailbox_prompt_is_not_a_banner(self):
        text = "MDCHECK\r\n(AEA PK-232M)  18536 free  (B,E,K,L,R,S) >\r\n"      # hw_logs ..._fw_all_A.log
        assert "mailbox" in scan.describe_effect("MDCHECK", text).lower()
        assert "banner" not in scan.describe_effect("MDCHECK", text).lower()

    def test_a_real_banner_still_is_one(self):
        text = "RESTART\r\n\r\nAEA PK-232M Data Controller\r\nRelease 01.AUG.91\r\n\r\ncmd:"
        assert "banner" in scan.describe_effect("RESTART", text).lower()

    @pytest.mark.parametrize("line", [
        "?need MYcall", "?need MYSELCAL", "?not while in PAcket", "?EXPERT command", "?callsign", "?not enough"])
    def test_a_refusal_is_a_precondition_and_no_effect(self, line):
        text = f"X\r\n{line}\r\ncmd:"
        assert scan.precondition_of(text) == line
        assert scan.describe_effect("X", text) == ""

    def test_what_is_not_a_precondition(self):
        assert scan.precondition_of("X\r\n?What?\r\ncmd:") == ""

    def test_the_effect_text_names_the_mode_it_was_measured_in(self):
        assert scan.fx_text("starts the transmission", "Ctrl-C", mode="BAUDOT") == \
            "in BAUDOT: starts the transmission; exit Ctrl-C"
        assert scan.fx_text("", "Ctrl-C") == ""            # no effect, no text


# ---------------------------------------------------------------- the preconditions of the risky part

class TestPreconditionsAreSetAndGivenBack:

    def test_mycall_is_set_so_that_the_commands_that_need_it_work(self, clock):
        # (MYSELCAL: an UNSET one is left alone since P89b - test_factory_banner_p89b.py; the commands that need
        # a selcal then say ?need MYSELCAL and are recorded as preconditions)
        t = scan.MockTransport(C, clock=clock, risky=True, needs_mycall=True, needs_selcal=True)
        rows = _risky(t, myselcal=None)
        for name in ("CONVERSE", "K", "ID", "TRANS"):
            assert not _row(rows, name)["precondition"], name

    def test_everything_is_given_back_afterwards(self, clock):
        t = scan.MockTransport(C, clock=clock, risky=True, needs_mycall=True, needs_selcal=True)
        before = (t.mycall, t.myselcal)
        assert before == ("PK232", "none")
        _risky(t)
        assert (t.mycall, t.myselcal) == before

    def test_a_run_without_a_callsign_records_the_refusals_as_preconditions(self, clock):
        t = scan.MockTransport(C, clock=clock, risky=True, needs_mycall=True)
        rows = _risky(t, mycall=None)
        row = _row(rows, "CONVERSE")
        assert row["precondition"] == "?need MYcall" and row["effect"] == "" and row["fx"] == ""
        assert t.mycall == "PK232"

    def test_expert_stays_on_for_the_whole_risky_part_also_after_a_power_cycle(self, clock):
        t = scan.MockTransport(A, clock=clock, risky=True, memory_needs_expert=True, needs_star_first=True,
                               dead_after={"CALIBRATE"})
        t.write(scan.STAR)
        t.expert_on = True
        rows = _risky(t, expert=True)
        assert _row(rows, "MEMORY")["precondition"] == ""
        assert "prints a value" in _row(rows, "MEMORY")["effect"]


class TestTheRightModeForTheCommand:

    def test_xmit_and_rcve_are_tried_in_baudot_achg_and_over_in_amtor(self, clock):
        t = scan.MockTransport(B, clock=clock, risky=True, mode_rules=True)
        rows = _risky(t)
        for name, mode in scan.NEEDS_MODE.items():
            row = _row(rows, name)
            assert row["mode"] == mode, name
            assert row["precondition"] == "", (name, row["precondition"])
        assert t.opmode == "PACKET"                           # and back

    def test_the_effect_is_stored_with_its_mode(self, clock):
        t = scan.MockTransport(B, clock=clock, risky=True, mode_rules=True)
        row = _row(_risky(t), "XMIT")
        assert row["fx"].startswith("in BAUDOT: ")

    def test_a_command_that_is_still_refused_in_its_mode_gets_no_effect(self, clock):
        # OVER needs a running link: refused even in AMTOR -> precondition, not an effect
        t = scan.MockTransport(A, clock=clock, risky=True, mode_rules=True, over_needs_link=True)
        row = _row(_risky(t), "OVER")
        assert row["precondition"].startswith("?not while in") and row["effect"] == "" and row["fx"] == ""
        assert row["result"] == "SUPPORTED"                  # the command exists

    def test_without_the_rule_xmit_in_packet_is_refused(self, clock):
        t = scan.MockTransport(B, clock=clock, risky=True, mode_rules=True)
        t.write(scan.verbose_line("XMIT"))
        assert "?not while in" in t.read_idle()


class TestMdcheck:

    def test_the_mailbox_is_left_with_b_not_with_ctrl_c(self, clock):
        t = scan.MockTransport(B, clock=clock, risky=True)
        b = scan.probe_risky(t, scan.Cmd("MDCHECK", "maildrop", "danger"), mycall="OE3GAS",
                             confirm_power_cycle=t.power_cycle)
        assert b.recovery == "B" and b.steps == [("B", True)]
        assert "mailbox" in b.effect.lower()

    def test_ctrl_c_alone_does_not_leave_the_mailbox_in_the_mock(self, clock):
        t = scan.MockTransport(B, clock=clock, risky=True)
        t.write(scan.verbose_line("MDCHECK"))
        t.read_idle()
        t.write(scan.CTRL_C)
        assert "cmd:" not in t.read_idle() and t.mailbox


# ---------------------------------------------------------------- --only

class TestOnly:

    def test_only_the_named_commands_run(self, clock):
        t = scan.MockTransport(B, clock=clock, risky=True, mode_rules=True)
        rep = scan.run_scan(t, "MOCK", progress=False, risky=True, mycall="OE3GAS",
                            confirm_power_cycle=t.power_cycle, only={"XMIT", "RCVE", "MYCALL"})
        assert sorted(r["name"] for r in rep.rows) == ["MYCALL", "RCVE", "XMIT"]

    def test_nothing_else_is_sent_to_the_tnc(self, clock):
        t = scan.MockTransport(B, clock=clock, risky=True, mode_rules=True)
        scan.run_scan(t, "MOCK", progress=False, risky=True, mycall="OE3GAS",
                      confirm_power_cycle=t.power_cycle, only={"XMIT"})
        lines = {d.decode("latin-1").strip().upper() for d in t.sent}
        assert "XMIT" in lines and "PACLEN" not in lines and "TRANS" not in lines and "CALIBRATE" not in lines

    def test_main_refuses_an_unknown_name(self, capsys):
        assert scan.main(["--selftest", "1991", "--only", "NOSUCHCMD"]) == 2
        assert "NOSUCHCMD" in capsys.readouterr().err

    def test_main_refuses_a_risky_name_without_all(self, capsys):
        assert scan.main(["--selftest", "1991", "--only", "XMIT"]) == 2
        assert "--all" in capsys.readouterr().err

    def test_main_runs_only_with_all(self, clock, capsys):
        assert scan.main(["--selftest", "1991", "--all", "--only", "XMIT,RCVE"]) == 0
        out = capsys.readouterr().out
        assert "XMIT" in out and "PACLEN" not in out


# ---------------------------------------------------------------- the matrix

class TestMatrixAndCsv:

    def test_a_precondition_row_fills_the_cell_but_never_an_effect(self):
        entries = _entries()
        e = entries["OVER"]
        entries["OVER"] = dataclasses.replace(e, fw={**e.fw, B: "?"}, ev={**e.ev, B: ""}, fx={**e.fx, B: ""})
        rows = [{"name": "OVER", "result": "SUPPORTED", "effect": "", "fx": "", "precondition": "?not while in AMtor",
                 "recovery": "Ctrl-C"}]
        new, filled, conflicts = scan.apply_to_matrix(entries, rows, B, "2026-10-08", "B", "x.csv")
        assert filled == 1 and not conflicts
        assert new["OVER"].fx[B] == ""
        assert "precondition: ?not while in AMtor" in new["OVER"].ev[B]

    def test_the_csv_has_the_precondition_and_mode_columns(self, clock, tmp_path):
        t = scan.MockTransport(B, clock=clock, risky=True, mode_rules=True)
        rep = scan.run_scan(t, "MOCK", progress=False, risky=True, mycall="OE3GAS", confirm_power_cycle=t.power_cycle)
        path = tmp_path / "scan.csv"
        scan.write_csv(rep, str(path))
        assert {"precondition", "mode"} <= set(path.read_text(encoding="utf-8").splitlines()[0].split(","))

    def test_the_shipped_matrix_has_no_fx_that_is_only_a_refusal(self):
        for name, e in cm.all_entries().items():
            for rel, fx in e.fx.items():
                assert not fx.startswith("refused"), (name, rel, fx)
                assert "prints banner" not in fx or name in ("RESTART", "RESET", "REINIT"), (name, rel, fx)

    def test_a_cleaned_cell_says_so_in_its_evidence(self):
        e = cm.entry("ACHG")
        for rel in (A, B, C):
            assert "fx cleared" in e.ev[rel] and "precondition" in e.ev[rel], rel
        assert "MailDrop prompt" in cm.entry("MDCHECK").ev[A]
