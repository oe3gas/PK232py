# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""P81e - frames that arrive while the first mode is being activated are held,
not dropped, and handed to the new mode in their original order.

ModeManager activates a mode on a 300 ms timer after set_mode(); until then
on_frame() has nobody to give data ($3x), monitor ($3F) and status-error ($5F)
frames to and dropped them: the greeting of a station that connected in that
window was lost (P81d already hands the link messages to the LinkTable).
Buffering applies only to the FIRST activation (no mode active when set_mode()
is called); a switch from an active mode behaves as before. Upper limit 200.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from pk232py.comm.frame import FrameKind, HostFrame
from pk232py.mode_manager import ModeManager
from pk232py.ui.main_window import MainWindow

_app = QApplication.instance() or QApplication([])


def rx_data(channel: int, text: str) -> HostFrame:
    return HostFrame(0x30 | channel, channel, text.encode("ascii"), FrameKind.RX_DATA)


def monitor(text: str) -> HostFrame:
    return HostFrame(0x3F, 15, text.encode("ascii"), FrameKind.RX_MONITOR)


def link_msg(channel: int, text: str) -> HostFrame:
    return HostFrame(0x50 | channel, channel, text.encode("ascii"), FrameKind.LINK_MSG)


class _Tnc:
    is_connected = True
    is_host_mode = True
    has_pactor = False
    verbose_confirmed = False

    def consume_fresh_boot_defaults(self):
        return False

    def send_command(self, *a, **k):
        pass

    def send_channel_command(self, *a, **k):
        pass


@pytest.fixture
def win():
    w = MainWindow()
    w.signal = w._serial.frame_received
    w._serial = _Tnc()
    w._modes._serial = w._serial
    return w


def activate_vhf(w):
    w._link_table.mode_name = "VHF Packet"
    w._update_host_mode_ui(True)                  # set_mode() started, 300 ms to go
    assert w._modes.current_mode_name == ""


class TestGreetingAfterTheActivation:
    def test_the_greeting_of_a_connect_in_the_window_is_shown_in_channel_and_all(self, win):
        activate_vhf(win)
        win.signal.emit(link_msg(0, "*** CONNECTED to OE3GAS-2"))
        win.signal.emit(rx_data(0, "Welcome to the OE3G"))          # packet boundary mid-word
        win.signal.emit(rx_data(0, "AS-2 node\r"))
        win._modes._send_init_frames()                              # the 300 ms activation
        screen = win._opmode_screens["VHF Packet"]
        assert win._modes.current_mode_name == "VHF Packet"
        assert screen._rx_docs[0].toPlainText() == "Welcome to the OE3GAS-2 node\n"
        assert screen._rx_doc_all.toPlainText() == "0│Welcome to the OE3GAS-2 node\n"
        assert win._link_table.channels[0].partner == "OE3GAS-2"

    def test_monitor_frames_are_held_too(self, win):
        activate_vhf(win)
        win.signal.emit(monitor("OE3GAS-1>APRS:hello"))
        win._modes._send_init_frames()
        screen = win._opmode_screens["VHF Packet"]
        assert "OE3GAS-1" in screen._rx_docs["MON"].toPlainText()

    def test_nothing_is_delivered_twice(self, win):
        activate_vhf(win)
        win.signal.emit(rx_data(0, "once\r"))
        win._modes._send_init_frames()
        screen = win._opmode_screens["VHF Packet"]
        win.signal.emit(rx_data(0, "after\r"))
        assert screen._rx_docs[0].toPlainText() == "once\nafter\n"


class TestTheBuffer:

    def test_order_is_kept_and_the_limit_is_200(self, win):
        activate_vhf(win)
        for i in range(250):
            win.signal.emit(rx_data(0, f"line {i}\r"))
        win._modes._send_init_frames()
        lines = win._opmode_screens["VHF Packet"]._rx_docs[0].toPlainText().split("\n")[:-1]
        assert len(lines) == 200
        assert lines[0] == "line 50" and lines[-1] == "line 249"      # the oldest 50 went

    def test_the_buffer_is_emptied_by_the_activation(self, win):
        activate_vhf(win)
        win.signal.emit(rx_data(0, "x\r"))
        win._modes._send_init_frames()
        assert len(win._modes._early_frames) == 0 and not win._modes._buffer_early

    def test_frames_before_any_set_mode_are_still_dropped(self, win):
        win.signal.emit(rx_data(0, "nobody listens\r"))
        assert len(win._modes._early_frames) == 0


class TestActiveModesUnchanged:
    def test_a_switch_from_an_active_mode_does_not_buffer(self, win):
        from pk232py.modes.rtty_baudot import BaudotRTTYMode
        win._modes._active_mode = BaudotRTTYMode()
        win._modes.set_mode("VHF Packet")               # Baudot is deactivated, packet pending
        win.signal.emit(rx_data(0, "stale\r"))
        assert len(win._modes._early_frames) == 0

    def test_an_active_mode_gets_its_frames_at_once(self, win):
        seen = []

        class Probe:
            name = "Probe"
            def handle_frame(self, frame):
                seen.append(frame)

        win._modes._active_mode = Probe()
        win.signal.emit(rx_data(0, "direct\r"))
        assert len(seen) == 1
