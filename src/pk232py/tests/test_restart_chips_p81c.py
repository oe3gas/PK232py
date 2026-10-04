# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""P81c (T169) - after a restart the chips of the links found by CSTATUS must end
up CONFIRMED (solid), not unconfirmed (dashed).

Two paths can confirm: CSTATUS itself (verbose, at the init) and the CO round at
the Host Mode entry. CSTATUS is the TNC's own answer and stays "connected"; the
Host Mode entry then marks every link unconfirmed and asks CO on all channels.
On a restart no Packet mode is active yet: ModeManager activates it on its own
timer, and ModeManager.on_frame() DROPS every frame while no mode is active - the
CO answers (which come back within milliseconds) were lost, so nothing confirmed
the links. The CO round now waits for the mode activation.

Real restart path: fresh MainWindow, links found, first Host Mode entry; the
stub TNC answers every CO query at once, through the real frame signal.
"""

from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from pk232py.comm.frame import FrameKind, HostFrame
from pk232py.comm.link_status import build_live_links
from pk232py.ui.main_window import MainWindow

_app = QApplication.instance() or QApplication([])

CSTATUS = (
    "CSTATUS\r\n"
    "Ch. 0 - IO CONNECTED to OE3GAS-2; v2\r\n"
    "Ch. 1 - CONNECTED to OE3GAS-1; v2\r\n"
    "cmd:"
)
VHF_ON = "VHF\r\nVHf       ON\r\ncmd:"

# CO answers as measured (T142): connected "CO41000<partner>", free "CO00000".
CO_ANSWERS = {0: b"CO41000OE3GAS-2", 1: b"CO41000OE3GAS-1"}


class _TncStub:
    """A TNC in Host Mode that answers every CO query at once."""
    is_connected = True
    is_host_mode = True
    has_pactor = False
    verbose_confirmed = False

    def __init__(self, frame_signal):
        self._emit = frame_signal.emit
        self.co_asked: list[int] = []
        self.mode_when_asked: list[str] = []
        self.mode_probe = lambda: ""

    def consume_fresh_boot_defaults(self):
        return False

    def send_command(self, *a, **k):
        pass

    def send_channel_command(self, channel, command):
        if command == b"CO":
            self.co_asked.append(channel)
            self.mode_when_asked.append(self.mode_probe())
            data = CO_ANSWERS.get(channel, b"CO00000")
            self._emit(HostFrame(0x40 | channel, channel, data, FrameKind.LINK_STATUS))


def _restart_to_host_mode():
    w = MainWindow()
    tnc = _TncStub(w._serial.frame_received)     # the real signal ModeManager listens to
    tnc.mode_probe = lambda: w._modes.current_mode_name
    w._serial = tnc
    w._modes._serial = tnc
    w.resize(1100, 760)
    w.show()
    _app.processEvents()
    # init: CSTATUS found the links (verbose), then the first Host Mode entry
    w._on_live_links_found(build_live_links(CSTATUS, "", VHF_ON))
    w._update_host_mode_ui(True)
    deadline = time.monotonic() + 3.0
    while w._modes.current_mode_name != "VHF Packet" and time.monotonic() < deadline:
        _app.processEvents()
    for _ in range(20):
        _app.processEvents()
    return w, tnc


def test_cstatus_alone_gives_confirmed_chips():
    w = MainWindow()
    w._on_live_links_found(build_live_links(CSTATUS, "", VHF_ON))
    for name in ("HF Packet", "VHF Packet"):
        bar = w._opmode_screens[name].channel_bar
        assert (bar.state(0), bar.state(1)) == ("connected", "connected")


def test_after_the_first_host_mode_entry_the_links_are_confirmed():
    w, _tnc = _restart_to_host_mode()
    states = [w._link_table.channels[0].state, w._link_table.channels[1].state]
    assert states == ["connected", "connected"], states
    for name in ("HF Packet", "VHF Packet"):
        bar = w._opmode_screens[name].channel_bar
        assert (bar.state(0), bar.state(1)) == ("connected", "connected")


def test_the_co_round_is_asked_once_the_mode_is_active():
    w, tnc = _restart_to_host_mode()
    assert sorted(tnc.co_asked) == list(range(10))
    assert set(tnc.mode_when_asked) == {"VHF Packet"}      # never while no mode is active


def test_an_already_active_mode_asks_at_once():
    w, tnc = _restart_to_host_mode()
    tnc.co_asked.clear()
    w._update_host_mode_ui(True)                  # e.g. a later Ctrl+H, mode still active
    assert sorted(tnc.co_asked) == list(range(10))
    assert w._link_table.channels[1].state == "connected"
