# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Unit tests for MainWindow's Packet channel-0 (UI channel) wiring (P10.2)
and the per-channel link-message button gating fix (T102).

Covers:
  - T98 — Unproto switches to channel 0; Connect/Disconnect disable there;
          selecting a QSO channel turns Unproto back off and re-enables them
  - T99 — Connect on channel 0 is rejected: no CO frame, button un-checked
  - T102 — a link message for a channel that is NOT currently visible must
           not change Connect/Disconnect/Unproto; ChannelBar (a separate,
           channel-scoped consumer of the same message) still updates

Uses a stub `_serial` (records calls, no real I/O) rather than the mock TNC
in tools/mock_tnc_bbs.py, since this is UI/wiring logic that does not need
real frame decoding — see test_packet_hf.py / test_packet_screen.py for the
mode-layer and screen-layer pieces, and the "Packet screen: channel 0..."
commit's manual smoke check for a full mock-TNC end-to-end pass.

Needs a QApplication; forced to the offscreen platform (see
test_packet_screen.py for why this is done at module level, before any
PyQt6 import).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

from pk232py.comm.frame import FrameKind
from pk232py.ui.main_window import MainWindow
from pk232py.modes.packet_vhf import VHFPacketMode

_app = QApplication.instance() or QApplication([])


class _FakeLinkMsgFrame:
    def __init__(self, channel: int, text: str):
        self.channel = channel
        self.text = text
        self.kind = FrameKind.LINK_MSG


class _StubSerial:
    is_connected = True
    is_host_mode = True

    def __init__(self):
        self.calls: list[tuple] = []

    def send_channel_command(self, ch, mnemonic, args=b""):
        self.calls.append(("ch_cmd", ch, mnemonic, args))
        return True

    def send_data(self, data, channel=0):
        self.calls.append(("data", channel, data))
        return True

    def send_command(self, mnemonic, args=b""):
        self.calls.append(("cmd", mnemonic, args))
        return True


@pytest.fixture
def wired_vhf():
    """A MainWindow with VHF Packet made active and wired, stub serial.

    Uses VHFPacketMode (name == "VHF Packet"), matching the screen made
    current below -- _wire_mode_callbacks() looks the screen up by
    mode.name for on_link_message/on_channel_state, so an HFPacketMode
    here would silently wire those two callbacks to the HF Packet screen
    instead of this fixture's screen (T98/T99 never noticed, since they
    only exercise signals wired via the currentWidget-based
    _wire_screen_buttons() path, not mode.name lookups).
    """
    w = MainWindow()
    w._serial = _StubSerial()
    mode = VHFPacketMode()
    w._modes._active_mode = mode
    w._opmode_stack.setCurrentWidget(w._opmode_screens["VHF Packet"])
    w._wire_mode_callbacks()
    screen = w._opmode_screens["VHF Packet"]
    return w, screen


class TestUnprotoUsesChannelZero:
    """T98."""

    def test_unproto_on_switches_to_channel_zero_and_locks_buttons(self, wired_vhf):
        w, screen = wired_vhf
        screen.channel_bar.set_current(3)
        screen.tx_input.setPlainText("draft on ch3")

        screen.btn_unproto.setChecked(True)

        assert screen.current_channel() == 0
        assert not screen.btn_connect.isEnabled()
        assert not screen.btn_disconnect.isEnabled()

    def test_unproto_off_does_not_auto_jump_channel(self, wired_vhf):
        w, screen = wired_vhf
        screen.channel_bar.set_current(3)
        screen.btn_unproto.setChecked(True)
        assert screen.current_channel() == 0

        screen.btn_unproto.setChecked(False)
        assert screen.current_channel() == 0   # operator must pick a chip

    def test_selecting_qso_channel_turns_unproto_off_and_unlocks(self, wired_vhf):
        w, screen = wired_vhf
        screen.channel_bar.set_current(3)
        screen.tx_input.setPlainText("draft on ch3")
        screen.btn_unproto.setChecked(True)
        assert screen.current_channel() == 0

        screen.channel_bar.set_current(3)

        assert not screen.btn_unproto.isChecked()
        assert screen.btn_connect.isEnabled()
        assert screen.tx_input.toPlainText() == "draft on ch3"   # P9 preserved

    def test_channel_zero_state_change_reenables_unproto(self, wired_vhf):
        # A previously CONNECTED QSO channel leaves btn_unproto disabled
        # (set_link_state('connected')); switching to channel 0 must
        # re-enable it regardless, since channel 0 can never be busy itself.
        w, screen = wired_vhf
        screen.channel_bar.set_current(5)
        screen.set_link_state("connected")
        assert not screen.btn_unproto.isEnabled()

        screen.channel_bar.set_current(0)
        assert screen.btn_unproto.isEnabled()


class TestConnectRejectedOnChannelZero:
    """T99."""

    def test_connect_on_channel_zero_sends_no_frame(self, wired_vhf, monkeypatch):
        w, screen = wired_vhf
        monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))

        screen.channel_bar.set_current(0)
        screen.set_dest_callsign("OE1XYZ")
        screen.btn_connect.setChecked(True)

        assert w._serial.calls == []
        assert not screen.btn_connect.isChecked()
        assert screen.channel_bar.state(0) == "free"


class TestLinkMessageGatedByVisibleChannel:
    """T102 — a link message for a channel other than the visible one must
    not touch Connect/Disconnect/Unproto; ChannelBar itself still updates
    (it is a separate, always-on, per-channel consumer of the same message)."""

    def test_message_for_other_channel_does_not_change_buttons(self, wired_vhf):
        w, screen = wired_vhf
        mode = w._modes.current_mode

        # Channel 4 connects while it is the visible channel.
        screen.channel_bar.set_current(4)
        mode.handle_frame(_FakeLinkMsgFrame(4, "CONNECTED to OE1XYZ"))
        assert screen.btn_disconnect.isEnabled()

        # Switch away to the UI channel.
        screen.channel_bar.set_current(0)
        assert not screen.btn_connect.isEnabled()
        assert not screen.btn_disconnect.isEnabled()
        assert screen.btn_unproto.isEnabled()

        # A link message for channel 4 arrives while channel 0 is visible.
        mode.handle_frame(_FakeLinkMsgFrame(4, "CONNECTED to OE1XYZ"))

        # Buttons must stay exactly as the visible channel (0) dictates.
        assert not screen.btn_disconnect.isEnabled()
        assert screen.btn_unproto.isEnabled()
        # ChannelBar itself is unaffected by this fix -- channel 4 still
        # shows connected, since that consumer is not channel-gated.
        assert screen.channel_bar.state(4) == "connected"

    def test_switching_back_reveals_the_other_channels_true_state(self, wired_vhf):
        w, screen = wired_vhf
        mode = w._modes.current_mode

        screen.channel_bar.set_current(4)
        mode.handle_frame(_FakeLinkMsgFrame(4, "CONNECTED to OE1XYZ"))
        screen.channel_bar.set_current(0)
        mode.handle_frame(_FakeLinkMsgFrame(4, "CONNECTED to OE1XYZ"))

        screen.channel_bar.set_current(4)
        assert screen.btn_disconnect.isEnabled()
