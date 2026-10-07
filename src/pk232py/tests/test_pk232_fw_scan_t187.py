# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""T187 (hw_logs/20261007_T187_{A,B}.log) - what the third --all run showed:

* device A (13.SEP.95): "State before" said ``ECHO None``. The log line 8-9: ``ECHO`` -> ``?EXPERT command`` - the
  firmware gates ECHO behind EXPERT, and the scanner read ECHO before it unlocked EXPERT. Not a format problem: the
  value was never there. So ECHO is read again after the unlock, and ECHO OFF is restored while EXPERT is still ON
  (``ECHO OFF`` is gated the same way);
* the FEC cells of A and B said ``exit Ctrl-C``, the log says Ctrl-C only brings ``cmd:`` and OPMODE stays ``FEc IDLE
  SEND``; ``Ctrl-C+PACKET`` is the way back that works: the two cells were corrected by hand (matrix test below).

tools/ is not a package - see test_hw_check.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pk232py.comm import command_matrix as cm

_TOOLS = Path(__file__).resolve().parents[3] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import pk232_fw_scan as scan  # noqa: E402

A, B, C = "13.SEP.95", "01.AUG.91", "30.DEC.88"


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


def _scan(t, **kw):
    return scan.run_scan(t, "MOCK", progress=False, only={"MYCALL"}, **kw)


class TestEchoIsReadAfterExpertIsUnlocked:

    def test_the_mock_gates_echo_like_the_log(self, clock):
        # hw_logs/20261007_T187_A.log line 8-9: 'ECHO\r\n?EXPERT command\r\ncmd:'
        t = scan.MockTransport(A, clock=clock, echo_needs_expert=True)
        t.write(scan.verbose_line("ECHO"))
        assert "?EXPERT command" in t.read_idle()

    def test_the_echo_of_a_gated_device_is_found_not_none(self, clock):
        t = scan.MockTransport(A, clock=clock, echo_needs_expert=True)
        rep = _scan(t)
        assert rep.echo_prior == "ON"                       # was None at A in T187
        assert rep.expert_prior == "OFF"

    def test_the_report_line_no_longer_says_none(self, clock, capsys):
        t = scan.MockTransport(A, clock=clock, echo_needs_expert=True)
        scan.print_report(_scan(t))
        assert "State before : Opmode PACKET, ECHO ON" in capsys.readouterr().out

    def test_echo_off_of_a_gated_device_is_switched_on_for_the_scan_and_put_back(self, clock):
        t = scan.MockTransport(A, clock=clock, echo_needs_expert=True, echo_on=False)
        rep = _scan(t)
        assert rep.echo_prior == "OFF"
        assert t.echo_on is False and t.expert_on is False  # ECHO OFF put back while EXPERT was still ON, then EXPERT OFF
        assert rep.state_diff == []                         # DISPLAY before = after

    def test_a_device_that_answers_at_once_is_read_once_as_before(self, clock):
        t = scan.MockTransport(B, clock=clock)
        rep = _scan(t)
        assert rep.echo_prior == "ON"
        reads = [d for d in t.sent if d == scan.verbose_line("ECHO")]
        assert len(reads) == 1                              # no second read when the first one worked

    def test_a_device_without_expert_keeps_none_when_it_cannot_say(self, clock):
        # nothing to unlock, nothing to read again: honest None, not a guess
        t = scan.MockTransport(C, clock=clock, silent={"ECHO"})
        assert _scan(t).echo_prior is None


class TestTheFecCellsOfAAndB:
    OLD = "changes OPMODE to FEC; exit Ctrl-C"
    NEW = "changes OPMODE to FEC; exit Ctrl-C+PACKET"

    @pytest.mark.parametrize("release, log", [(A, "20261007_T187_A.log"), (B, "20261007_T187_B.log")])
    def test_the_cell_names_the_way_back_that_worked(self, release, log):
        e = cm.entry("FEC")
        assert e.fx[release] == self.NEW
        assert log in e.ev[release] and self.OLD in e.ev[release]   # the old value stays in the evidence

    def test_the_scan_value_equals_the_cell_so_a_rerun_conflicts_with_nothing(self):
        row = {"name": "FEC", "result": "SUPPORTED", "effect": "changes OPMODE to FEC",
               "fx": scan.fx_text("changes OPMODE to FEC", "Ctrl-C+PACKET"), "precondition": "",
               "recovery": "Ctrl-C+PACKET"}
        for release in (A, B):
            _new, _filled, conflicts = scan.apply_to_matrix(cm.all_entries(), [row], release, "2026-10-07", "x", "t.csv")
            assert not conflicts, release

    def test_device_c_was_not_touched(self):
        assert cm.entry("FEC").fx.get(C, "") == ""
