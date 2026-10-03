# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""P80b: what T166 (device B, 01.AUG.91) and T167 (device A, 13.SEP.95) refuted.

NE answers NEY and OPMODE stays PA (NEWMODE, a parameter - NAVTEX is NA); PT
answers "PTA 10" and OPMODE stays PA (PACTIME, not PACTOR standby); XL and EE
answer $07; MW answers MWN and refuses 11 ($01); CI answers CIN (a switch, the
verbose CODE is 0); MY is $07 / "MYnone". None of them is sent any more and the
registry says so (sent=False), so the registry test protects the decision.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from pathlib import Path

import pytest

from pk232py.comm.host_params import HOST_PARAMS, param_by_name
from pk232py.comm.hostmode import HostModeProtocol
from pk232py.comm.mnemonic_registry import REGISTRY
from pk232py.modes.amtor import AMTORMode
from pk232py.modes.morse import MorseMode
from pk232py.modes.navtex import NAVTEXMode
from pk232py.modes.rtty_ascii import ASCIIRTTYMode
from pk232py.modes.rtty_baudot import BaudotRTTYMode
from pk232py.tests.test_main_window_packet import _StubSerial
from pk232py.ui.main_window import MainWindow

_TOOLS_DIR = Path(__file__).resolve().parents[3] / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))
import hw_check  # noqa: E402

REFUTED = (b"NE", b"PT", b"XL", b"EE", b"MW", b"CI", b"MY")


def _mns(frames):
    return [f[2:4] for f in frames]


@pytest.fixture
def win():
    w = MainWindow()
    w._serial = _StubSerial()
    return w


class TestNotSentAnyMore:
    def test_cmd_navtex_and_cmd_pactor_are_gone(self):
        assert not hasattr(HostModeProtocol, "cmd_navtex")
        assert not hasattr(HostModeProtocol, "cmd_pactor")

    def test_navtex_is_activated_by_na(self):
        assert _mns(NAVTEXMode().get_activate_frames()) == [b"NA"]

    def test_amtor_init_has_no_my_ee_xl(self):
        mns = _mns(AMTORMode(myident="ABCDEFG").get_init_frames())
        assert not {b"MY", b"EE", b"XL"} & set(mns)

    def test_ascii_and_baudot_init_have_no_xl_ee_ci(self):
        for mode in (ASCIIRTTYMode(), BaudotRTTYMode()):
            assert not {b"XL", b"EE", b"CI"} & set(_mns(mode.get_init_frames()))
        assert not hasattr(BaudotRTTYMode, "code_frame")

    def test_morse_init_has_no_mw(self):
        assert b"MW" not in _mns(MorseMode().get_init_frames())

    def test_no_builder_is_left_for_the_refuted_ones(self):
        for cls, names in ((AMTORMode, ("myident_frame", "errchar_frame", "xlength_frame")),
                           (ASCIIRTTYMode, ("xlength_frame", "errchar_frame")),
                           (BaudotRTTYMode, ("xlength_frame", "errchar_frame")),
                           (MorseMode, ("mweight_frame",))):
            for name in names:
                assert not hasattr(cls, name), f"{cls.__name__}.{name}"

    def test_the_registry_marks_every_refuted_mnemonic_not_sent_with_a_reason(self):
        for mn in REFUTED:
            entry = REGISTRY[mn]
            assert not entry.sent, mn
            assert "T166" in entry.meaning or "T167" in entry.meaning, mn


class TestPactorStandby:
    def test_stby_button_is_greyed_out_with_the_reason(self, win):
        screen = win._opmode_screens["PACTOR"]
        assert not screen.btn_stby.isEnabled()
        assert screen.btn_stby.toolTip() == (
            "No Host Mode PACTOR standby command verified (PT is PACTIME, T167)")

    def test_stby_sends_nothing(self, win):
        assert not hasattr(win, "_on_pactor_stby")

    def test_connect_sends_the_arq_call_without_pt(self, win):
        screen = win._opmode_screens["PACTOR"]
        win._opmode_stack.setCurrentWidget(screen)
        screen.le_dest.setText("OE3XYZ")
        win._on_pactor_connect()
        cmds = [c for c in win._serial.calls if c[0] == "cmd"]
        assert cmds == [("cmd", b"AC", b"OE3XYZ")]


class TestControls:
    def test_morse_weight_controls_are_greyed_out(self, win):
        screen = win._opmode_screens["CW / Morse"]
        for name in ("sb_mweight", "btn_weight_down", "btn_weight_up"):
            w = getattr(screen, name)
            assert not w.isEnabled(), name
            assert "MW" in w.toolTip() and "T166" in w.toolTip(), name

    def test_morse_weight_spin_box_sends_nothing(self, win):
        win._opmode_screens["CW / Morse"].sb_mweight.setValue(20)
        assert [c for c in win._serial.calls if c[0] == "cmd"] == []
        assert not hasattr(win, "_on_morse_mweight_changed")

    def test_myident_handler_is_gone(self, win):
        assert not hasattr(win, "_on_amtor_myident_changed")


class TestNewVerifiedRows:
    @pytest.mark.parametrize("name,mn", [
        ("EAS", b"EA"), ("WIDESHFT", b"WI"), ("SRXALL", b"SR"), ("USOS", b"US"),
        ("WORDOUT", b"WO"), ("FAXNEG", b"FN"), ("SQUELCH", b"SQ"), ("ASPECT", b"AY"),
    ])
    def test_set_and_verified_on_both_devices(self, name, mn):
        row = param_by_name(name)
        assert row.mnemonic == mn
        assert set(row.verified_releases) == {"01.AUG.91", "13.SEP.95"}

    @pytest.mark.parametrize("name,mn", [
        ("RBAUD", b"RB"), ("FSPEED", b"FS"), ("NAVMSG", b"NM"), ("NAVSTN", b"NS"),
    ])
    def test_query_only_rows_are_never_verified_for_setting(self, name, mn):
        row = param_by_name(name)
        assert row.mnemonic == mn and row.verified_releases == ()

    def test_mnemonics_stay_unique(self):
        mns = [p.mnemonic for p in HOST_PARAMS if p.mnemonic]
        assert len(mns) == len(set(mns))


_PASS0 = (
    "[21:39:46] >> b'EXPERT\\r\\n'\n"
    "[21:39:46] << 'EXPERT\\r\\n?What?\\r\\ncmd:'\n"
    "[21:39:47] >> b'EAS\\r\\n'\n"
    "[21:39:47] << 'EAS\\r\\nEAS       OFF\\r\\ncmd:'\n"
    "[21:39:47] original EAS = 'OFF'\n"
    "[21:39:51] >> b'XLENGTH\\r\\n'\n"
    "[21:39:51] << 'XLENGTH\\r\\n?What?\\r\\ncmd:'\n"
    "[21:39:51] original XLENGTH = None\n"
    "[21:39:52] >> b'ASPECT\\r\\n'\n"
    "[21:39:52] << 'ASPECT\\r\\nASPect    2 (576)\\r\\ncmd:'\n"
    "[21:39:52] original ASPECT = '2'\n"
    "[21:39:53] >> b'RBAUD\\r\\n'\n"
    "[21:39:53] << 'RBAUD\\r\\nRBaud     45\\r\\ncmd:'\n"
    "[21:39:53] original RBAUD = '45'\n"
    "\n"
    "==============================================================\n"
    "STEP 2 of 5   T166/T167 B.1  unproven parameters   (about 4 minutes)\n"
    "==============================================================\n"
)
_RESULTS = (
    "[21:40:59] INFO: T166 EAS (EA) -- unparsed q1=b'EAN' (45 41 4e) set=b'EA\\x00' "
    "(45 41 00) q2=b'EAY' (45 41 59) test='Y' verbose='ON' restore=restored after='OFF'\n"
    "[21:40:59] INFO: T166 XLENGTH (XL) -- rejected (0x07) q1=b'XL\\x07' (58 4c 07) "
    "set=none q2=none test=None verbose=None restore=None after=None\n"
    "[21:40:59] INFO: T166 ASPECT (AY) -- unparsed q1=b'AY2' (41 59 32) set=b'AY\\x00' "
    "(41 59 00) q2=b'AY3' (41 59 33) test='3' verbose='3' restore=restored after='2'\n"
    "[21:40:59] INFO: T166 RBAUD (RB) -- unparsed q1=b'RB45' (52 42 34 35) set=none "
    "q2=none test=None verbose=None restore=None after='45'\n"
)


class TestProbeEvaluation:
    def test_reevaluate_gives_verified_for_the_log_excerpt(self, tmp_path):
        log = tmp_path / "t166.log"
        log.write_text(_PASS0 + _RESULTS, encoding="utf-8")
        lines: list = []
        counts = hw_check.reevaluate_host_params_log(log, out=lines.append)
        text = "\n".join(lines)
        assert "EAS (EA): verified" in text
        assert "ASPECT (AY): verified" in text
        assert "RBAUD (RB): verified_query" in text
        assert "XLENGTH (XL): rejected (0x07)" in text
        assert "unparsed" not in text
        assert counts["verified"] == 2
