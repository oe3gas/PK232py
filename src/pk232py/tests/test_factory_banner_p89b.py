# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""P89b - power-cycling does NOT always restore the factory state (hand test at device A and the MYSELCAL
finding at A and B, 07.10.2026):

* off and on again: banner WITHOUT an extra line, MYSELCAL stayed NONE - the memory survived the short pause;
  off for longer: first ``PK-232M is using default values.``, then MYSELCAL ``none``;
* so "the TNC is at the factory state" is true only when that line came before the banner - ONE function
  (comm/constants.is_factory_banner) for the app and the scanner, the text exactly as observed;
* the scanner asks the operator to switch off for a while ONLY for a TNC that no longer answers (P89 part B.4)
  and, when the banner comes without the line, says so and repeats the step - three tries, then it says
  ``TNC keeps its settings (RAM battery?) - factory state not reached`` and the run goes on (a scan-kit device
  of someone else may have a RAM battery: the line never comes, and switching off must not be demanded again);
* no command clears MYSELCAL at A and B (hand tests, operator, 07.10.2026, each line a separate test at both:
  ``MYSELCAL %`` -> ``?callsign``, ``MYSELCAL &`` -> ``?callsign``, ``MYSELCAL OFF`` -> ``?callsign``,
  ``MYSELCAL NONE`` -> ``now NONE``). So an UNSET MYSELCAL (``none``) is only queried and never set, there is
  no power cycle to give it back; a set value is written back as before.

The banners below are copied from hw_logs/20261006_fw_scan_C.log and hw_logs/20261007_fw_only_{A,B,C}.log
unchanged. tools/ is not a package - see test_hw_check.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pk232py.comm import command_matrix as cm
from pk232py.comm import constants
from pk232py.comm.serial_manager import _parse_defaults_flag

_TOOLS = Path(__file__).resolve().parents[3] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import pk232_fw_scan as scan  # noqa: E402

A, B, C = "13.SEP.95", "01.AUG.91", "30.DEC.88"

# power-on, with the line (hw_logs/20261007_fw_only_A.log line 6, _B.log line 6, 20261006_fw_scan_C.log)
POWER_ON_A = ("\x00\x00\x00\x00\x00\r\n\r\n\r\nPK-232M is using default values.\r\n  \r\n\r\n\r\n\x11AEA PK-232M Data Controller\r\n"
              "Copyright (C) 1986-1995 by\r\nAdvanced Electronic Applications, Inc.\r\nRelease 13.SEP.95\r\nVer. 7.1\r\n"
              "PACTOR s/n 26902 \r\n\r\ncmd:")
POWER_ON_B = ("\x00\x00\x00\x00\x00\r\n\r\n\r\nPK-232M is using default values.\r\n  \r\n\r\n\r\n\x11AEA PK-232M Data Controller\r\n"
              "Copyright (C) 1986-1991 by\r\nAdvanced Electronic Applications, Inc.\r\nRelease 01.AUG.91\r\n\r\ncmd:")
POWER_ON_C = ("\x00\r\n\r\n\r\nPK-232 is using default values.\r\n  \r\n\r\n\r\n\x11AEA PK-232 Data Controller\r\n"
              "Copyright (C) 1986, 1987, 1988 by\r\nAdvanced Electronic Applications, Inc.\r\nRelease 30.DEC.88\r\nChecksum $80\r\ncmd:")
# RESTART keeps the settings: banner without the line (hw_logs/20261007_fw_only_{A,B,C}.log line 9)
RESTART_A = ("RESTART\r\n  \r\n\r\n\r\n\x11AEA PK-232M Data Controller\r\nCopyright (C) 1986-1995 by\r\n"
             "Advanced Electronic Applications, Inc.\r\nRelease 13.SEP.95\r\nVer. 7.1\r\nPACTOR s/n 26902 \r\n\r\ncmd:")
RESTART_B = ("RESTART\r\n  \r\n\r\n\r\n\x11AEA PK-232M Data Controller\r\nCopyright (C) 1986-1991 by\r\n"
             "Advanced Electronic Applications, Inc.\r\nRelease 01.AUG.91\r\n\r\ncmd:")
RESTART_C = ("RESTART\r\n\x00  \r\n\r\n\r\n\x11AEA PK-232 Data Controller\r\nCopyright (C) 1986, 1987, 1988 by\r\n"
             "Advanced Electronic Applications, Inc.\r\nRelease 30.DEC.88\r\nChecksum $80\r\ncmd:")


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


# ---------------------------------------------------------------- ONE function, the text as observed

class TestOneFunctionForTheFactoryState:

    @pytest.mark.parametrize("banner", [POWER_ON_A, POWER_ON_B, POWER_ON_C])
    def test_a_power_on_banner_with_the_line_is_the_factory_state(self, banner):
        assert constants.is_factory_banner(banner) is True

    @pytest.mark.parametrize("banner", [RESTART_A, RESTART_B, RESTART_C])
    def test_a_banner_without_the_line_is_not(self, banner):
        assert constants.is_factory_banner(banner) is False

    def test_the_text_is_exactly_as_observed_two_spellings(self):
        # A and B print PK-232M, device C prints PK-232 (no M) - both observed, nothing else is accepted
        assert constants.FACTORY_BANNER_LINES == ("PK-232M is using default values.", "PK-232 is using default values.")

    @pytest.mark.parametrize("text", [
        "PK-232M is using default values",                   # no full stop
        "pk-232m is using default values.",                  # case
        "AEA PK-232M is using default values. Release 1",    # not a line of its own
        "PK-232MBX is using default values.",                # not observed
        "", "cmd:",
    ])
    def test_nothing_that_was_not_observed_counts(self, text):
        assert constants.is_factory_banner(text) is False

    def test_bytes_and_text_give_the_same_answer(self):
        assert constants.is_factory_banner(POWER_ON_B.encode("latin-1")) is True
        assert constants.is_factory_banner(RESTART_B.encode("latin-1")) is False

    def test_the_app_and_the_scanner_use_that_one_function(self):
        assert scan.is_factory_banner is constants.is_factory_banner
        assert _parse_defaults_flag(POWER_ON_C.encode("latin-1")) is True
        assert _parse_defaults_flag(RESTART_C.encode("latin-1")) is False
        assert _parse_defaults_flag(b"") is None


class TestTheAppDoesNotTakeAKeptBannerForTheFactoryState:
    """The two consumers of 'the TNC came up at the factory state': MainWindow's archive restore (P59/P60, through
    fresh_boot_defaults) and - by a different question - the live-link check of P81 (banner_seen_this_init)."""

    def test_a_banner_without_the_line_is_not_fresh_boot_defaults(self):
        from pk232py.tests.test_serial_manager import _run_detection

        def responder(data):
            return RESTART_B.encode("latin-1") if data == b"*" else b""

        sm, _port, _m = _run_detection(responder)
        assert sm.fresh_boot_defaults is False and sm.tnc_defaults is False
        assert sm.banner_seen_this_init is True                  # a banner: the TNC woke up (links are gone) ...
        assert sm.consume_fresh_boot_defaults() is False         # ... but that is no factory state: no restore

    def test_a_kept_banner_after_a_factory_banner_resets_both_flags(self):
        from pk232py.tests.test_serial_manager import _run_again, _run_detection

        sm, _port, _m = _run_detection(lambda data: POWER_ON_A.encode("latin-1") if data == b"*" else b"")
        assert sm.fresh_boot_defaults is True

        _run_again(sm, lambda data: RESTART_A.encode("latin-1") if data == b"*" else b"")
        assert sm.fresh_boot_defaults is False
        assert sm.tnc_defaults is False                          # the latest banner decides, not the first


# ---------------------------------------------------------------- the operator step and its check

class TestPowerCycleAndCheck:

    def test_the_instruction_names_the_pause_and_marks_it_as_a_starting_value(self):
        assert scan.POWER_CYCLE_INSTRUCTION == "Switch the TNC off, wait at least 10 seconds, switch it on."
        assert scan.POWER_OFF_SECONDS == 10
        assert "NOT measured" in scan.POWER_OFF_NOTE             # the 10 s is a starting value (P89b)

    @pytest.mark.parametrize("release, autobaud", [(B, False), (A, False), (C, True)])
    def test_a_banner_with_the_line_ends_the_step(self, clock, capsys, release, autobaud):
        t = scan.MockTransport(release, clock=clock, risky=True, needs_star_first=autobaud)
        cycles = []
        ok = scan.power_cycle_and_check(t, "XMIT: the TNC does not come back", lambda: (cycles.append(1), t.power_cycle()))
        out = capsys.readouterr()
        assert ok is True and len(cycles) == 1
        assert out.out.count(scan.POWER_CYCLE_INSTRUCTION) == 1
        assert "kept its settings" not in out.err + out.out

    def test_a_banner_without_the_line_says_so_and_repeats_the_step(self, clock, capsys):
        t = scan.MockTransport(B, clock=clock, risky=True, keeps_settings_cycles=1)
        cycles = []
        ok = scan.power_cycle_and_check(t, "XMIT: the TNC does not come back", lambda: (cycles.append(1), t.power_cycle()))
        out = capsys.readouterr()
        assert ok is True and len(cycles) == 2                   # the second attempt got the line
        assert out.out.count(scan.POWER_CYCLE_INSTRUCTION) == 2  # the step was shown again
        assert "TNC kept its settings - switch off longer and repeat" in out.err + out.out

    def test_three_banners_without_the_line_end_with_a_message_and_no_fourth_try(self, clock, capsys):
        t = scan.MockTransport(B, clock=clock, risky=True, keeps_settings_cycles=99)
        cycles = []
        ok = scan.power_cycle_and_check(t, "t", lambda: (cycles.append(1), t.power_cycle()))
        out = capsys.readouterr()
        assert scan.POWER_CYCLE_TRIES == 3
        assert ok is False and len(cycles) == 3                  # no fourth attempt
        assert out.out.count(scan.POWER_CYCLE_INSTRUCTION) == 3
        assert out.err.count("TNC kept its settings - switch off longer and repeat") == 2   # tries 1 and 2 ask again
        assert out.err.count("TNC keeps its settings (RAM battery?) - factory state not reached") == 1

    def test_the_result_is_in_the_log(self, clock, tmp_path):
        t = scan.MockTransport(B, clock=clock, risky=True, keeps_settings_cycles=99)
        t.debug = scan.DebugLog(str(tmp_path / "d.log"))
        scan.power_cycle_and_check(t, "t", t.power_cycle)
        t.debug.fh.flush()
        log = (tmp_path / "d.log").read_text(encoding="utf-8")
        assert "factory state not reached" in log and "RAM battery" in log

    def test_the_mock_keeps_mycall_and_myselcal_when_the_cycle_keeps_the_settings(self, clock):
        t = scan.MockTransport(B, clock=clock, risky=True, keeps_settings_cycles=1)
        t.mycall, t.myselcal = "OE3GAS", "NONE"
        t.power_cycle()
        assert (t.mycall, t.myselcal) == ("OE3GAS", "NONE")
        t.power_cycle()
        assert (t.mycall, t.myselcal) == ("PK232", "none")


class TestAHungTnCComesBackThroughTheSameStep:

    def test_the_power_cycle_of_a_hung_tnc_is_checked_too(self, clock, capsys):
        t = scan.MockTransport(B, clock=clock, risky=True, dead_after={"MEMORY"}, keeps_settings_cycles=1)
        rows = scan.run_risky(t, cm.all_entries(), mycall="OE3GAS", confirm_power_cycle=t.power_cycle,
                              progress=False, only={"MEMORY"})
        assert rows[0]["recovery"] == "needs_power_cycle"
        out = capsys.readouterr()
        assert out.out.count("MEMORY: the TNC does not come back") == 2   # shown again: the first cycle kept the settings
        assert "TNC kept its settings" in out.err + out.out

    def test_a_device_that_never_gets_the_line_does_not_stop_the_run(self, clock, capsys):
        # a scan-kit device with a RAM battery: the factory line never comes - the scan goes on
        t = scan.MockTransport(B, clock=clock, risky=True, dead_after={"MEMORY"}, keeps_settings_cycles=99)
        rows = scan.run_risky(t, cm.all_entries(), mycall="OE3GAS", confirm_power_cycle=t.power_cycle,
                              progress=False, only={"MEMORY", "RCVE"})
        assert {r["name"] for r in rows} == {"MEMORY", "RCVE"}
        out = capsys.readouterr()
        assert out.out.count("MEMORY: the TNC does not come back") == 3                  # three tries, no fourth
        assert "TNC keeps its settings (RAM battery?) - factory state not reached" in out.err + out.out


# ---------------------------------------------------------------- MYSELCAL: an unset one is only queried

class TestAnUnsetMyselcalIsLeftAlone:
    """No command clears MYSELCAL at A and B and a power cycle must not be demanded of devices that are not ours
    (a scan-kit device with a RAM battery keeps its settings): an unset value is queried, never set."""

    def _run(self, t, **kw):
        kw.setdefault("mycall", "OE3GAS")
        kw.setdefault("confirm_power_cycle", t.power_cycle)
        kw.setdefault("progress", False)
        return scan.run_risky(t, cm.all_entries(), **kw)

    @pytest.mark.parametrize("arg, expect", [("%", "?callsign"), ("&", "?callsign"), ("OFF", "?callsign"),
                                             ("NONE", "now NONE")])
    def test_the_mock_answers_like_a_and_b_to_each_hand_test(self, clock, arg, expect):
        t = scan.MockTransport(B, clock=clock, risky=True)
        t.write(scan.verbose_line(f"MYSELCAL {arg}"))
        assert expect in t.read_idle()

    @pytest.mark.parametrize("release", [A, B, C])
    def test_an_unset_myselcal_is_not_set_and_not_restored(self, clock, capsys, release):
        t = scan.MockTransport(release, clock=clock, risky=True, needs_selcal=True)
        assert t.myselcal == "none"
        self._run(t, only={"ALIST", "FEC", "RCVE"})
        sent = [d.decode("latin-1").strip() for d in t.sent]
        assert [s for s in sent if s.upper().startswith("MYSELCAL")] == ["MYSELCAL"]     # the query, nothing else
        assert t.myselcal == "none"
        assert scan.POWER_CYCLE_INSTRUCTION not in capsys.readouterr().out               # no power cycle at the end

    def test_the_log_says_why(self, clock, tmp_path):
        t = scan.MockTransport(B, clock=clock, risky=True, needs_selcal=True)
        t.debug = scan.DebugLog(str(tmp_path / "d.log"))
        self._run(t, only={"ALIST"})
        t.debug.fh.flush()
        assert "MYSELCAL set/restore skipped: unset value cannot be restored" in (tmp_path / "d.log").read_text(encoding="utf-8")

    def test_the_commands_that_need_a_selcal_are_then_recorded_as_preconditions(self, clock):
        t = scan.MockTransport(B, clock=clock, risky=True, needs_selcal=True)
        row = next(r for r in self._run(t, only={"ALIST"}) if r["name"] == "ALIST")
        assert row["precondition"] == "?need MYSELCAL" and row["effect"] == "" and row["fx"] == ""

    def test_an_explicit_myselcal_option_does_not_change_that(self, clock):
        t = scan.MockTransport(B, clock=clock, risky=True, needs_selcal=True)
        self._run(t, only={"ALIST"}, myselcal="DLBC")
        assert t.myselcal == "none"

    def test_after_a_reset_inside_the_run_it_is_still_not_set(self, clock):
        t = scan.MockTransport(B, clock=clock, risky=True, needs_selcal=True)
        self._run(t, only={"RESTART"})
        sent = [d.decode("latin-1").strip() for d in t.sent]
        assert [s for s in sent if s.upper().startswith("MYSELCAL")] == ["MYSELCAL"]
        assert t.myselcal == "none"

    def test_mycall_is_still_set_and_put_back(self, clock):
        t = scan.MockTransport(B, clock=clock, risky=True, needs_mycall=True, needs_selcal=True)
        t.mycall = "OE1ABC"
        self._run(t, only={"CONVERSE"})
        assert t.mycall == "OE1ABC"

    def test_a_set_myselcal_is_put_back_by_setting_it_as_before(self, clock, capsys):
        t = scan.MockTransport(C, clock=clock, risky=True, needs_selcal=True)
        t.myselcal = "OEAS"                                      # device C showed OEAS before the run
        self._run(t, only={"ALIST"}, myselcal="DLBC")
        assert t.myselcal == "OEAS"
        assert scan.POWER_CYCLE_INSTRUCTION not in capsys.readouterr().out

    def test_the_comparison_stays_case_sensitive(self, clock):
        t = scan.MockTransport(B, clock=clock, risky=True)
        t.myselcal = "NONE"                                      # a VALID selcal, not "not set"
        assert scan.restore_value(t, "MYSELCAL", "NONE") is True
        assert scan.restore_value(t, "MYSELCAL", "none") is False

    def test_a_valid_selcal_that_reads_none_in_capitals_is_a_set_value(self, clock):
        # A and B hold NONE after T186: that is a set value, so it IS put back (as NONE)
        t = scan.MockTransport(B, clock=clock, risky=True, needs_selcal=True)
        t.myselcal = "NONE"
        self._run(t, only={"ALIST"})
        assert t.myselcal == "NONE"


# ---------------------------------------------------------------- the matrix

class TestTheMatrixSaysItCannotBeCleared:
    """The observation word for word, one line per hand test (operator, 07.10.2026, at A and at B)."""

    LINES = ("MYSELCAL % -> ?callsign", "MYSELCAL & -> ?callsign", "MYSELCAL OFF -> ?callsign",
             "MYSELCAL NONE -> now NONE (a valid selcal)")

    @pytest.mark.parametrize("release", [A, B])
    def test_myselcal_cannot_be_cleared_at_a_and_b(self, release):
        e = cm.entry("MYSELCAL")
        assert e.fx[release] == "cannot be cleared; power-cycle"
        for line in self.LINES:
            assert line in e.ev[release], (release, line)
        assert "reported as" not in e.ev[release]

    def test_device_c_is_not_claimed(self):
        assert cm.entry("MYSELCAL").fx.get(C, "") == ""          # nothing measured at C: no cell
