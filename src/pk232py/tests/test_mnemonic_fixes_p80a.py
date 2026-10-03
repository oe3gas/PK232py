# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""P80a: three wrong or unverified Host Mode mnemonics the audit (P80) found.

* RXREV (FAX button) sent RV, PT200 sent P2, PACTOR ARQTMO sent AC. Where
  comm/host_params.py has a row WITH a measurement, the mnemonic comes from
  there (verified_mnemonic) - one place: RX, PB, AO (T151).
* ARQTOL ("Ao") is not sent any more: no Host Mode command is known for it
  (T151, ?What? on 01.AUG.91).
* MI is MFILTER (T115), not Morse ID: the Packet "MID" button and the Morse
  ID spin box send nothing and are greyed out.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from pk232py.comm.frame import build_command
from pk232py.comm.host_params import verified_mnemonic
from pk232py.comm.mnemonic_registry import REGISTRY
from pk232py.modes.amtor import AMTORMode
from pk232py.modes.morse import MorseMode
from pk232py.modes.pactor import PACTORMode
from pk232py.ui.main_window import MainWindow
from pk232py.tests.test_main_window_packet import _StubSerial

MI_TIP = "Host mnemonic unverified - MI is MFILTER (T115)"


def _mnemonic(frame: bytes) -> bytes:
    return frame[2:4]


@pytest.fixture
def win():
    w = MainWindow()
    w._serial = _StubSerial()
    return w


def _cmds(w):
    return [c for c in w._serial.calls if c[0] == "cmd"]


class TestOneSourceForMeasuredMnemonics:
    def test_verified_mnemonic_reads_host_params(self):
        assert verified_mnemonic("RXREV") == b"RX"
        assert verified_mnemonic("PT200") == b"PB"
        assert verified_mnemonic("ARQTMO") == b"AO"

    def test_an_unverified_row_is_refused(self):
        with pytest.raises(LookupError):
            verified_mnemonic("HID")          # no mnemonic, no measurement
        with pytest.raises(LookupError):
            verified_mnemonic("NO_SUCH_PARAMETER")


class TestRxrevPt200Arqtmo:
    def test_fax_rxrev_button_sends_rx_not_rv(self, win):
        win._on_fax_rxrev_toggled(True)
        assert _cmds(win) == [("cmd", b"RX", b"Y")]

    def test_pt200_frame_is_pb(self):
        assert _mnemonic(PACTORMode.pt200_frame(True)) == b"PB"

    def test_pactor_arqtmo_frame_is_ao_not_ac(self):
        assert _mnemonic(PACTORMode.arqtmo_frame(60)) == b"AO"


class TestArqtolIsNotSent:
    def test_amtor_init_frames_have_no_ao(self):
        mnemonics = [_mnemonic(f) for f in AMTORMode().get_init_frames()]
        assert b"Ao" not in mnemonics
        assert b"AO" in mnemonics             # ARQTMO is still sent

    def test_there_is_no_arqtol_frame_builder_any_more(self):
        assert not hasattr(AMTORMode, "arqtol_frame")


class TestMiIsNotSent:
    def test_morse_init_frames_have_no_mi(self):
        assert b"MI" not in [_mnemonic(f) for f in MorseMode().get_init_frames()]

    def test_morse_mid_spin_box_is_not_wired_to_the_tnc(self, win):
        win._opmode_screens["CW / Morse"].sb_mid.setValue(5)
        assert _cmds(win) == []
        assert not hasattr(win, "_on_morse_mid_changed")

    def test_there_is_no_mid_frame_builder_any_more(self):
        assert not hasattr(MorseMode, "mid_frame")

    def test_packet_mid_button_sends_nothing_and_is_greyed_out(self, win):
        from pk232py.modes.packet_vhf import VHFPacketMode
        win._modes._active_mode = VHFPacketMode()
        win._opmode_stack.setCurrentWidget(win._opmode_screens["VHF Packet"])
        win._wire_mode_callbacks()
        screen = win._opmode_screens["VHF Packet"]
        screen.btn_mid.setChecked(True)
        screen.btn_mid.setChecked(False)
        assert not any(c[1] == b"MI" for c in _cmds(win))
        assert not screen.btn_mid.isEnabled()
        assert screen.btn_mid.toolTip() == MI_TIP

    def test_morse_id_controls_are_greyed_out_with_the_tooltip(self, win):
        screen = win._opmode_screens["CW / Morse"]
        for name in ("sb_mid", "btn_mid_down", "btn_mid_up"):
            widget = getattr(screen, name)
            assert not widget.isEnabled(), name
            assert widget.toolTip() == MI_TIP, name

    def test_registry_says_mi_is_mfilter_with_t115(self):
        entry = REGISTRY[b"MI"]
        assert "MFILTER" in entry.meaning
        assert "T115" in entry.evidence.get("13.SEP.95", "")
        assert not entry.sent
