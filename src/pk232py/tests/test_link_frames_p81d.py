# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""P81d - $5x link messages and $4x link status always reach the LinkTable.

Found with P81c: ModeManager.on_frame() hands every frame except CMD_RESP to the
ACTIVE mode only and DROPS it while no mode is active (ECHO, RX_DATA, RX_MONITOR,
LINK_STATUS, LINK_MSG, STATUS_ERR, UNKNOWN alike). The mode is activated on a
300 ms timer after the Host Mode entry, so an incoming connect in that window
("*** CONNECTED to OE3GAS-2") never reached the LinkTable. The same holds for a
non-Packet mode, which ignores link frames. Link frames are therefore given to the
LinkTable by MainWindow whenever the active mode is not a Packet mode; a Packet
mode keeps feeding it itself (no double feed, no second connect event).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from pk232py.comm.frame import FrameKind, HostFrame
from pk232py.ui.main_window import MainWindow

_app = QApplication.instance() or QApplication([])


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


def link_msg(channel: int, text: str) -> HostFrame:
    return HostFrame(0x50 | channel, channel, text.encode("ascii"), FrameKind.LINK_MSG)


def link_status(channel: int, data: bytes) -> HostFrame:
    return HostFrame(0x40 | channel, channel, data, FrameKind.LINK_STATUS)


@pytest.fixture
def win(monkeypatch):
    w = MainWindow()
    w.signal = w._serial.frame_received          # the real signal ModeManager listens to
    w._serial = _Tnc()
    w._modes._serial = w._serial
    w.beeps = []
    monkeypatch.setattr(QApplication, "beep", staticmethod(lambda: w.beeps.append(1)))
    w._app_config.appearance.connect_bell = True
    w.events = []
    w._link_table.subscribe_events(lambda ch, ev, partner: w.events.append((ch, ev, partner)))
    return w


class TestNoModeActiveYet:
    def test_the_window_has_no_active_mode(self, win):
        assert win._modes.current_mode is None

    def test_an_incoming_connect_reaches_the_link_table(self, win):
        win.signal.emit(link_msg(0, "*** CONNECTED to OE3GAS-2"))
        link = win._link_table.channels[0]
        assert (link.state, link.partner) == ("connected", "OE3GAS-2")
        assert win.events == [(0, "connected", "OE3GAS-2")]        # a real, new connect
        assert win.beeps == [1]

    def test_the_chips_follow(self, win):
        win.signal.emit(link_msg(1, "*** CONNECTED to OE3GAS-1"))
        for name in ("HF Packet", "VHF Packet"):
            bar = win._opmode_screens[name].channel_bar
            assert (bar.state(1), bar.partner(1)) == ("connected", "OE3GAS-1")

    def test_a_disconnect_reaches_it_too(self, win):
        win._link_table.on_host_link_message(0, "*** CONNECTED to OE3GAS-2")
        assert win._link_table.channels[0].state == "connected"
        win.signal.emit(link_msg(0, "*** DISCONNECTED: OE3GAS-2 ***"))
        assert win._link_table.channels[0].state == "free"

    def test_a_link_status_answer_reaches_it(self, win):
        win.signal.emit(link_status(1, b"CO41000OE3GAS-1"))
        link = win._link_table.channels[1]
        assert (link.state, link.partner) == ("connected", "OE3GAS-1")
        assert win.beeps == []                                      # reconciliation: no bell

    def test_the_message_is_logged(self, win, monkeypatch):
        lines = []
        monkeypatch.setattr(win, "_log_monitor", lines.append)
        win.signal.emit(link_msg(0, "*** CONNECTED to OE3GAS-2"))
        assert any("CONNECTED to OE3GAS-2" in line and "no Packet mode" in line for line in lines)

    def test_status_errors_and_channel_15_are_not_link_messages(self, win):
        win.signal.emit(HostFrame(0x5F, 15, b"XX\x00", FrameKind.STATUS_ERR))
        win.signal.emit(link_msg(15, "*** CONNECTED to X"))
        assert all(link.state == "free" for link in win._link_table.channels)


class TestInTheActivationWindow:
    def test_a_connect_between_the_host_mode_entry_and_the_activation(self, win):
        """The reported case: the first 300 ms after the Host Mode entry."""
        win._link_table.mode_name = "VHF Packet"
        win._update_host_mode_ui(True)                    # set_mode() started, not active yet
        assert win._modes.current_mode_name == ""
        win.signal.emit(link_msg(0, "*** CONNECTED to OE3GAS-2"))
        assert win._link_table.channels[0].state == "connected"
        win._modes._send_init_frames()                    # now the mode becomes active
        assert win._modes.current_mode_name == "VHF Packet"
        assert win._link_table.channels[0].partner == "OE3GAS-2"


class TestActiveModes:
    def test_a_packet_mode_feeds_the_table_itself_once(self, win):
        win._link_table.mode_name = "VHF Packet"
        win._update_host_mode_ui(True)
        win._modes._send_init_frames()
        assert win._modes.current_mode_name == "VHF Packet"
        win.events.clear()
        sink = []
        win._modes.link_frame_sink = sink.append          # must NOT be used now
        win.signal.emit(link_msg(2, "*** CONNECTED to OE3GAS-3"))
        assert sink == []
        assert win._link_table.channels[2].state == "connected"
        assert win.events == [(2, "connected", "OE3GAS-3")]   # one event, not two

    def test_a_non_packet_mode_does_not_swallow_link_messages(self, win):
        from pk232py.modes.rtty_baudot import BaudotRTTYMode
        win._modes._active_mode = BaudotRTTYMode()
        win.signal.emit(link_msg(0, "*** CONNECTED to OE3GAS-2"))
        assert win._link_table.channels[0].state == "connected"
