# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Unit tests for the Packet screen's per-channel TX draft buffer (P9) and
the channel-0 UI/unproto/monitor channel (P10).

Covers:
  - T94 — text typed on one channel survives any number of channel
          switches and never appears on / is cleared from another channel
  - T95 — an MHEARD double-click channel switch behaves the same way as a
          chip click (both go through ChannelBar.channel_changed)
  - T96 — reset_channels() discards every buffered draft, not just the
          visible one
  - Chip 0 special-casing (P10.1): label "UI", fixed fill colour, state
    changes ignored, excluded from channel_map(), still reachable via
    step(); append_monitor_data() filtered like append_channel_data()
  - set_user_limit() (P11.5): advisory tooltip only on chips above the
    USERS limit, never a lock/grey-out/colour change

Needs a QApplication; forced to the offscreen platform so this runs in a
headless CI/dev environment with no real display (module-level setdefault,
before importing anything from PyQt6, so it never overrides a value the
runner deliberately set).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from pk232py.ui.screens.packet_screen import HFPacketScreen, UI_CHANNEL

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


class TestUiChannelZero:
    """P10.1 — channel 0 is the UI/unproto/monitor channel, not a QSO chip."""

    def test_chip_zero_label_is_ui(self):
        screen = _make_screen()
        assert screen.channel_bar._chips[0]._lbl_num.text() == "UI"

    def test_channel_zero_state_never_sticks(self):
        screen = _make_screen()
        screen.channel_bar.set_channel_state(0, "connected", "SHOULDNOTSTICK")
        assert screen.channel_bar.state(0) == "free"
        assert screen.channel_bar.partner(0) == ""

    def test_channel_zero_excluded_from_channel_map(self):
        screen = _make_screen()
        screen.channel_bar.set_channel_state(0, "connected", "SHOULDNOTSTICK")
        screen.channel_bar.set_channel_state(3, "connected", "OE1XYZ")
        cmap = screen.channel_bar.channel_map()
        assert "SHOULDNOTSTICK" not in cmap
        assert cmap == {"OE1XYZ": 3}

    def test_step_still_reaches_channel_zero(self):
        screen = _make_screen()
        screen.channel_bar.set_current(1)
        screen.channel_bar.step(-1)
        assert screen.channel_bar.current() == 0

    def test_reset_does_not_change_current_channel(self):
        screen = _make_screen()
        screen.channel_bar.set_current(4)
        screen.reset_channels()
        assert screen.channel_bar.current() == 4

    def test_monitor_data_hidden_in_ch_view_on_qso_channel(self):
        screen = _make_screen()
        screen.set_view_all(False)
        screen.channel_bar.set_current(3)
        screen.append_monitor_data("heard something")
        assert screen.rx_display.toPlainText() == ""

    def test_monitor_data_shown_in_ch_view_on_ui_channel(self):
        screen = _make_screen()
        screen.set_view_all(False)
        screen.channel_bar.set_current(UI_CHANNEL)
        screen.append_monitor_data("heard something")
        assert "heard something" in screen.rx_display.toPlainText()

    def test_monitor_data_always_shown_in_all_view(self):
        screen = _make_screen()
        screen.set_view_all(True)
        screen.channel_bar.set_current(3)
        screen.append_monitor_data("heard something")
        assert "heard something" in screen.rx_display.toPlainText()


class TestUserLimitTooltipOnly:
    """P11.5 — set_user_limit() is advisory only: a tooltip line, never a
    lock, grey-out or colour change."""

    def test_channels_at_or_below_limit_get_no_extra_tooltip(self):
        screen = _make_screen()
        screen.channel_bar.set_user_limit(1)
        assert "USERS is set to" not in screen.channel_bar._chips[1].toolTip()

    def test_channels_above_limit_get_the_warning_line(self):
        screen = _make_screen()
        screen.channel_bar.set_user_limit(1)
        for ch in range(2, 10):
            tip = screen.channel_bar._chips[ch].toolTip()
            assert "USERS is set to 1" in tip
            assert "will not be accepted" in tip

    def test_ui_channel_never_gets_the_warning_line(self):
        screen = _make_screen()
        screen.channel_bar.set_user_limit(0)
        assert "USERS" not in screen.channel_bar._chips[UI_CHANNEL].toolTip()

    def test_no_lock_or_style_change_above_the_limit(self):
        screen = _make_screen()
        screen.channel_bar.set_user_limit(1)
        chip = screen.channel_bar._chips[5]
        assert chip.isEnabled()
        assert chip.isCheckable()
        # Still selectable and usable exactly like any other chip.
        screen.channel_bar.set_current(5)
        assert screen.channel_bar.current() == 5
