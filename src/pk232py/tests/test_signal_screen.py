# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Unit tests for SignalScreen's live SIAM wiring (P19.4).

Fixtures are the REAL frames captured during T113 (hardware, 2026-09-22,
docs/P18_HF_Init_SIAM_Spec.md), fed through the real SignalMode exactly
as MainWindow._wire_mode_callbacks() wires it (mode.on_result_parsed ->
screen.on_mode_result) - not a screen-internal parser (there is none;
SignalScreen never had its own).

Needs a QApplication; forced to the offscreen platform (see
test_packet_screen.py for why this is done at module level, before any
PyQt6 import).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from pk232py.comm.frame import FrameKind, HostFrame
from pk232py.modes.signal_analysis import SignalMode
from pk232py.ui.screens.signal_screen import SignalScreen

_app = QApplication.instance() or QApplication([])


def _link_msg(text: str) -> HostFrame:
    return HostFrame(ctl=0x50, channel=0, data=text.encode("ascii"), kind=FrameKind.LINK_MSG)


def _wired():
    """A SignalScreen wired to a real SignalMode the way MainWindow does."""
    screen = SignalScreen()
    mode = SignalMode()
    mode.on_result_parsed = screen.on_mode_result
    return screen, mode


# The exact T113 hardware sequence, in the order the frames were received.
_T113_FRAGMENTS = [
    "0.12: 248 baud, ", "Baudot, RXRev OFF\r\n",
    "0.32: 50 baud, ",  "Baudot, RXRev ON\r\n",
    "0.73: 50 baud, ",  "Baudot, RXRev ON\r\n",
    "0.33: 51 baud, ",   # cut off - no closing fragment ever arrives
]


class TestSignalScreenLiveWiring:

    def test_latest_result_shown_after_t113_sequence(self):
        screen, mode = _wired()
        for frag in _T113_FRAGMENTS:
            mode.handle_frame(_link_msg(frag))

        # The last COMPLETE result (0.73) is the latest shown - the
        # trailing truncated fragment never completes and must not
        # overwrite it.
        assert screen.lbl_conf_val.text() == "0.73"
        assert screen.lbl_baud.text() == "50 Baud"
        assert screen.lbl_mode.text() == "Baudot"
        assert screen.lbl_rxrev.text() == "ON"

    def test_best_so_far_is_073_after_t113_sequence(self):
        screen, mode = _wired()
        for frag in _T113_FRAGMENTS:
            mode.handle_frame(_link_msg(frag))

        assert "0.73" in screen.lbl_best.text()

    def test_all_three_complete_results_appear_once_each_in_the_log(self):
        screen, mode = _wired()
        for frag in _T113_FRAGMENTS:
            mode.handle_frame(_link_msg(frag))

        log = screen.rx_log.toPlainText()
        # Each result appears fully assembled, on its own - never split
        # into two half-lines (T114's hardware expectation).
        assert log.count("0.12: 248 baud, Baudot, RXRev OFF") == 1
        assert log.count("0.32: 50 baud, Baudot, RXRev ON") == 1
        assert log.count("0.73: 50 baud, Baudot, RXRev ON") == 1
        # The truncated fourth fragment never completes, so it must not
        # appear at all.
        assert "0.33" not in log

    def test_best_so_far_survives_a_lower_confidence_result(self):
        screen, mode = _wired()
        for frag in _T113_FRAGMENTS:
            mode.handle_frame(_link_msg(frag))
        assert "0.73" in screen.lbl_best.text()

        # A weaker result arrives in the next SIAM session (get_activate_
        # frames() resets the fragment buffer, same as a real re-entry
        # into Signal/SIAM mode) - best-so-far must not regress to it,
        # since New Analysis/Cancel were never clicked.
        mode.get_activate_frames()
        mode.handle_frame(_link_msg("0.20: 45 baud, "))
        mode.handle_frame(_link_msg("ASCII, RXRev OFF\r\n"))

        assert "0.73" in screen.lbl_best.text()
        assert screen.lbl_conf_val.text() == "0.20"   # latest still updates

    def test_new_analysis_resets_best_so_far(self):
        screen, mode = _wired()
        for frag in _T113_FRAGMENTS:
            mode.handle_frame(_link_msg(frag))
        assert "0.73" in screen.lbl_best.text()

        screen._on_neue_analyse()

        assert screen.lbl_best.text() == "–"


class TestMainWindowWiresSignalMode:
    """P19.4: MainWindow._wire_mode_callbacks() must connect
    SignalMode.on_result_parsed to the Signal (SIAM) screen's
    on_mode_result - never on_result, which would double-handle every
    successfully parsed line (SignalScreen has no parser to feed)."""

    def test_wire_mode_callbacks_connects_on_result_parsed(self):
        from pk232py.ui.main_window import MainWindow

        w = MainWindow()
        mode = SignalMode()
        # Bypass set_mode()/ModeManager entirely (no serial needed) - same
        # approach as test_main_window_packet.py's wired_vhf fixture.
        w._modes._active_mode = mode
        w._opmode_stack.setCurrentWidget(w._opmode_screens["Signal (SIAM)"])

        w._wire_mode_callbacks()

        screen = w._opmode_screens["Signal (SIAM)"]
        assert mode.on_result_parsed == screen.on_mode_result
        assert mode.on_result is None
