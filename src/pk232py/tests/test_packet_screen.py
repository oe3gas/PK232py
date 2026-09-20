# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Unit tests for the Packet screen's per-channel TX draft buffer (P9).

Covers:
  - T94 — text typed on one channel survives any number of channel
          switches and never appears on / is cleared from another channel
  - T95 — an MHEARD double-click channel switch behaves the same way as a
          chip click (both go through ChannelBar.channel_changed)
  - T96 — reset_channels() discards every buffered draft, not just the
          visible one

Needs a QApplication; forced to the offscreen platform so this runs in a
headless CI/dev environment with no real display (module-level setdefault,
before importing anything from PyQt6, so it never overrides a value the
runner deliberately set).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from pk232py.ui.screens.packet_screen import HFPacketScreen

_app = QApplication.instance() or QApplication([])


def _make_screen() -> HFPacketScreen:
    return HFPacketScreen()


class TestPerChannelTxBuffer:
    """T94 — TX draft is per-channel and survives switches either way."""

    def test_draft_survives_round_trip(self):
        screen = _make_screen()
        screen.channel_bar.set_current(1)
        screen.tx_input.setPlainText("test eins")

        screen.channel_bar.set_current(3)
        assert screen.tx_input.toPlainText() == ""

        screen.tx_input.setPlainText("test drei")

        screen.channel_bar.set_current(1)
        assert screen.tx_input.toPlainText() == "test eins"

        screen.channel_bar.set_current(3)
        assert screen.tx_input.toPlainText() == "test drei"

    def test_sending_clears_only_the_sent_channel(self):
        screen = _make_screen()
        screen.channel_bar.set_current(1)
        screen.tx_input.setPlainText("test eins")
        screen.channel_bar.set_current(3)
        screen.tx_input.setPlainText("test drei")

        # Simulate what main_window._on_packet_tx_enter() does at the end:
        # clear_tx(channel) for the channel actually sent on.
        screen.clear_tx(3)
        assert screen.tx_input.toPlainText() == ""

        screen.channel_bar.set_current(1)
        assert screen.tx_input.toPlainText() == "test eins"

    def test_tx_channel_tracks_visible_text_not_channel_bar_current(self):
        # _tx_channel must be a separate variable from channel_bar.current():
        # channel_changed only ever carries the NEW channel, so the outgoing
        # text has to be filed under the OLD tracked channel, not re-derived
        # from channel_bar (which has already moved on by the time the
        # signal handler runs).
        screen = _make_screen()
        screen.channel_bar.set_current(2)
        screen.tx_input.setPlainText("draft two")
        assert screen._tx_channel == 2
        screen.channel_bar.set_current(7)
        assert screen._tx_channel == 7
        assert screen._tx_buffers[2][0] == "draft two"

    def test_clear_tx_default_channel_is_current(self):
        screen = _make_screen()
        screen.channel_bar.set_current(5)
        screen.tx_input.setPlainText("clear me")
        screen.clear_tx()   # no arg -> current channel only
        assert screen.tx_input.toPlainText() == ""
        assert 5 not in screen._tx_buffers

    def test_clear_tx_other_channel_does_not_touch_visible_text(self):
        screen = _make_screen()
        screen.channel_bar.set_current(1)
        screen.tx_input.setPlainText("visible on ch1")
        screen.channel_bar.set_current(2)
        screen.tx_input.setPlainText("buffered on ch2")
        screen.channel_bar.set_current(1)

        screen.clear_tx(2)   # not the visible channel
        assert screen.tx_input.toPlainText() == "visible on ch1"
        assert 2 not in screen._tx_buffers


class TestMheardChannelSwitchKeepsText:
    """T95 — MHEARD double-click switch behaves like a chip click."""

    def test_channel_requested_preserves_other_channel_draft(self):
        screen = _make_screen()
        screen.channel_bar.set_current(1)
        screen.tx_input.setPlainText("draft on ch1")

        screen.channel_bar.set_channel_state(4, "connected", "OE1XYZ-9")
        screen.mheard_panel.add_entry("OE1XYZ-9", "12:00", False)
        screen.mheard_panel.set_channel_map(screen.channel_bar.channel_map())
        row = screen.mheard_panel._list_layout.itemAt(0).widget()
        row.activated.emit("OE1XYZ-9", True)

        assert screen.current_channel() == 4
        assert screen.tx_input.toPlainText() == ""

        screen.channel_bar.set_current(1)
        assert screen.tx_input.toPlainText() == "draft on ch1"


class TestResetChannelsClearsAllBuffers:
    """T96 — reset_channels() discards every draft, not just the visible one."""

    def test_reset_clears_buffers_and_widget(self):
        screen = _make_screen()
        screen.channel_bar.set_current(2)
        screen.channel_bar.set_channel_state(2, "connected", "OE1ABC")
        screen.channel_bar.set_current(5)
        screen.tx_input.setPlainText("stale draft")

        screen.reset_channels()

        assert screen._tx_buffers == {}
        assert screen.tx_input.toPlainText() == ""
        for ch in range(10):
            assert screen.channel_bar.state(ch) == "free"
            assert screen.channel_bar.partner(ch) == ""
