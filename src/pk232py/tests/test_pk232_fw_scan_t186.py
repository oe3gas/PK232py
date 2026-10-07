# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""T186 (hw_logs/20261007_fw_only_{A,B,C}.log) - what the second --all run at the devices showed:

* device C: after FEC the prompt was back (Ctrl-C) but OPMODE stayed FEC, ID and XMIT were refused
  '?not while in FEC'; A and B ended in FEC / AMTOR the same way -> FEC ends with an explicit PACKET;
* ARQ and SELFEC answered '?callsign' -> a dummy target (--target, default NOCALL), way back
  Ctrl-C, DISCONNE, PACKET;
* a command with NEEDS_MODE is only sent when OPMODE says the mode was reached;
* A and B: 'MYSELCAL none' made the VALID selcal NONE - the restore of an unset MYSELCAL moved to P89b (no command
  clears it, a power cycle does: test_factory_banner_p89b.py).

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

B, C = "01.AUG.91", "30.DEC.88"


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


def _risky(t, **kw):
    kw.setdefault("mycall", "OE3GAS")
    kw.setdefault("confirm_power_cycle", getattr(t, "power_cycle", None))
    kw.setdefault("progress", False)
    return scan.run_risky(t, cm.all_entries(), **kw)


def _row(rows, name):
    return next(r for r in rows if r["name"] == name)


def _probe(t, name, kind="action_tx"):
    return scan.probe_risky(t, scan.Cmd(name, "other", kind), mycall="OE3GAS", confirm_power_cycle=t.power_cycle)


def _stuck_in_fec(clock):
    t = scan.MockTransport(C, clock=clock, risky=True, mode_rules=True, fec_sticks=True)
    t.write(scan.verbose_line("FEC"))
    t.read_idle()
    assert t.opmode == "FEC"
    return t


class TestFecAndTheLinkCommandsComeBackToPacket:

    def test_the_way_back_of_fec_ends_with_an_explicit_packet(self):
        first = scan.RECOVERY[scan.recovery_kind("FEC", "action_tx")][0]
        assert first.label == "Ctrl-C+PACKET"
        assert [a[1] for a in first.actions if a[0] == "tx"] == [scan.CTRL_C, scan.verbose_line("PACKET")]

    @pytest.mark.parametrize("name", ["ARQ", "SELFEC", "PTCONN"])
    def test_the_way_back_of_a_calling_command_is_ctrl_c_disconne_packet(self, name):
        first = scan.RECOVERY[scan.recovery_kind(name, "action_tx")][0]
        assert first.label == "Ctrl-C+DISCONNE+PACKET"
        assert [a[1] for a in first.actions if a[0] == "tx"] == \
            [scan.CTRL_C, scan.verbose_line("DISCONNE"), scan.verbose_line("PACKET")]

    def test_the_old_single_steps_stay_behind_as_fallbacks(self):
        assert [s.label for s in scan.RECOVERY["FEC"]][1:] == [s.label for s in scan.RECOVERY["action_tx"]]
        assert [s.label for s in scan.RECOVERY["link"]][1:] == [s.label for s in scan.RECOVERY["action_tx"]]

    def test_other_action_commands_keep_their_way_back(self):
        assert scan.recovery_kind("XMIT", "action_tx") == "action_tx"
        assert scan.recovery_kind("ID", "action_tx") == "action_tx"

    def test_the_mock_reproduces_the_measurement_ctrl_c_alone_leaves_fec(self, clock):
        t = _stuck_in_fec(clock)
        t.write(scan.CTRL_C)
        assert "cmd:" in t.read_idle() and t.opmode == "FEC"

    def test_after_fec_the_tnc_is_in_packet_and_the_next_commands_are_not_refused(self, clock):
        t = scan.MockTransport(C, clock=clock, risky=True, mode_rules=True, fec_sticks=True)
        rows = _risky(t)
        fec, ident, xmit = _row(rows, "FEC"), _row(rows, "ID"), _row(rows, "XMIT")
        assert fec["recovery"] == "Ctrl-C+PACKET" and fec["opmode"] == "OPMODE PACKET"
        assert "FEC" not in ident["precondition"]
        assert xmit["precondition"] == "" and xmit["fx"].startswith("in BAUDOT: ")
        assert t.opmode == "PACKET"

    def test_a_way_back_that_leaves_the_mode_is_reported(self, clock, capsys):
        t = scan.MockTransport(C, clock=clock, risky=True, mode_rules=True, fec_sticks=True)
        # make the new step a no-op for the mock: only Ctrl-C reaches it
        saved = scan.RECOVERY["FEC"]
        scan.RECOVERY["FEC"] = (scan._tx("Ctrl-C", scan.CTRL_C),)
        try:
            _risky(t, only={"FEC"}, progress=False)
        finally:
            scan.RECOVERY["FEC"] = saved
        assert "still in" in capsys.readouterr().err


class TestTheModeIsCheckedBeforeTheCommandIsSent:

    def test_opmode_word(self):
        assert scan.opmode_word("OPMODE FEC IDLE SEND") == "FEC"
        assert scan.opmode_word("Opmode AMtor STBY RCVE") == "AMTOR"
        assert scan.opmode_word("") == ""

    def test_a_mode_that_was_not_reached_stops_the_command_with_a_message(self, clock, capsys):
        t = _stuck_in_fec(clock)
        b = _probe(t, "XMIT")
        assert b.precondition.startswith("mode not reached: wanted BAUDOT")
        assert b.effect == "" and b.exists is None and b.recovery == "not sent"
        assert scan.verbose_line("XMIT") not in t.sent
        assert "NOT sent" in capsys.readouterr().err

    def test_the_tnc_is_back_in_packet_afterwards(self, clock):
        t = _stuck_in_fec(clock)
        b = _probe(t, "RCVE", kind="mode")
        assert b.recovery == "not sent"
        assert b.opmode == "OPMODE PACKET" and t.opmode == "PACKET"     # the abort still ends in PACKET

    def test_such_a_command_fills_no_matrix_cell(self, clock):
        t = _stuck_in_fec(clock)
        b = _probe(t, "XMIT")
        row = {"name": "XMIT", "result": "ERROR", "effect": b.effect, "fx": "", "precondition": b.precondition,
               "recovery": b.recovery}
        _new, filled, conflicts = scan.apply_to_matrix(cm.all_entries(), [row], C, "2026-10-07", "C", "x.csv")
        assert filled == 0 and not conflicts

    def test_a_mode_that_was_reached_is_sent_as_before(self, clock):
        t = scan.MockTransport(B, clock=clock, risky=True, mode_rules=True)
        b = _probe(t, "RCVE", kind="mode")
        assert b.precondition == "" and b.mode == "BAUDOT" and b.exists == "yes"


class TestTheCallingCommandsGetADummyTarget:

    def test_without_a_target_the_mock_answers_callsign_like_the_device(self, clock):
        t = scan.MockTransport(C, clock=clock, risky=True, needs_target=True)
        t.write(scan.verbose_line("ARQ"))
        assert "?callsign" in t.read_idle()

    @pytest.mark.parametrize("name", ["ARQ", "SELFEC", "PTCONN"])
    def test_the_default_target_is_nocall_and_the_answer_is_no_refusal(self, clock, name):
        t = scan.MockTransport(C, clock=clock, risky=True, needs_target=True)
        b = _probe(t, name)
        assert scan.verbose_line(f"{name} NOCALL") in t.sent
        assert b.precondition == "" and b.exists == "yes"
        assert b.recovery == "Ctrl-C+DISCONNE+PACKET"
        assert scan.verbose_line("DISCONNE") in t.sent and t.opmode == "PACKET"

    def test_the_target_is_an_option(self, clock):
        t = scan.MockTransport(C, clock=clock, risky=True, needs_target=True)
        rows = _risky(t, only={"ARQ"}, target="DL1ABC")
        assert scan.verbose_line("ARQ DL1ABC") in t.sent and _row(rows, "ARQ")["precondition"] == ""

    def test_other_commands_get_no_target(self, clock):
        t = scan.MockTransport(C, clock=clock, risky=True, needs_target=True, mode_rules=True)
        _risky(t, only={"ID", "XMIT"})
        assert not [d for d in t.sent if b"NOCALL" in d]

    def test_main_accepts_target(self, clock, capsys):
        assert scan.main(["--selftest", "1991", "--all", "--only", "ARQ", "--target", "DL1ABC"]) == 0
        assert "ARQ" in capsys.readouterr().out
