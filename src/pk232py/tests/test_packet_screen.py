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

from PyQt6.QtCore import Qt, QAbstractAnimation
from PyQt6.QtWidgets import QApplication

from pk232py.ui.screens.packet_screen import (
    HFPacketScreen, MON_VIEW, CHANNEL_COUNT,
    CH_FREE, CH_CALLING, CH_CONNECTED, CH_FAILED,
    _CHIP_FILL,
)

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
        screen.channel_bar.set_current(5)
        screen.tx_input.setPlainText("stale draft")

        screen.reset_channels()

        assert screen._tx_buffers == {}
        assert screen.tx_input.toPlainText() == ""

    def test_reset_does_not_wipe_channel_bar_state(self):
        """P67, Teil C: reset_channels() used to also call
        channel_bar.reset(), wiping every chip back to free - LinkTable
        is now the one source of truth for connection state (reconciled
        independently on Host Mode entry), so a channel this screen
        already shows connected must survive a reset_channels() call
        exactly as it survives the Host Mode exit path (see
        test_main_window_packet.py::TestLinkTableHostModeCarryOver)."""
        screen = _make_screen()
        screen.channel_bar.set_channel_state(2, "connected", "OE1ABC")

        screen.reset_channels()

        assert screen.channel_bar.state(2) == "connected"
        assert screen.channel_bar.partner(2) == "OE1ABC"


class TestUiChannelZero:
    """P10.1, superseded by P70: channel 0 is a regular TNC channel; the
    monitor/unproto view is the separate MON chip (see
    TestMonChipAndRegularChannelZero below)."""

    def test_chip_zero_label_is_its_number(self):
        screen = _make_screen()
        assert screen.channel_bar._chips[0]._lbl_num.text() == "0"

    def test_channel_zero_state_sticks(self):
        screen = _make_screen()
        screen.channel_bar.set_channel_state(0, "connected", "OE1ABC")
        assert screen.channel_bar.state(0) == "connected"
        assert screen.channel_bar.partner(0) == "OE1ABC"

    def test_channel_zero_included_in_channel_map(self):
        screen = _make_screen()
        screen.channel_bar.set_channel_state(0, "connected", "OE1ABC")
        screen.channel_bar.set_channel_state(3, "connected", "OE1XYZ")
        cmap = screen.channel_bar.channel_map()
        assert cmap == {"OE1ABC": 0, "OE1XYZ": 3}

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

    def test_monitor_data_shown_in_ch_view_on_mon_view(self):
        screen = _make_screen()
        screen.set_view_all(False)
        screen.channel_bar.set_current(MON_VIEW)
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

    def test_channels_below_limit_get_no_extra_tooltip(self):
        # P70: incoming calls land on the LOWEST free channel, so USERS n
        # accepts exactly channels 0 .. n-1 (T147 F3/F4).
        screen = _make_screen()
        screen.channel_bar.set_user_limit(2)
        assert "USERS is set to" not in screen.channel_bar._chips[0].button.toolTip()
        assert "USERS is set to" not in screen.channel_bar._chips[1].button.toolTip()
        assert "USERS is set to 2" in screen.channel_bar._chips[2].button.toolTip()

    def test_channels_above_limit_get_the_warning_line(self):
        screen = _make_screen()
        screen.channel_bar.set_user_limit(1)
        for ch in range(1, 10):
            tip = screen.channel_bar._chips[ch].button.toolTip()
            assert "USERS is set to 1" in tip
            assert "channels 0 to 0" in tip
            assert "USERS 0 = any free channel" in tip

    def test_users_zero_means_any_channel_so_no_warning(self):
        screen = _make_screen()
        screen.channel_bar.set_user_limit(0)
        for ch in range(10):
            assert "USERS is set to" not in screen.channel_bar._chips[ch].button.toolTip()

    def test_mon_chip_never_gets_the_warning_line(self):
        screen = _make_screen()
        screen.channel_bar.set_user_limit(0)
        assert "USERS" not in screen.channel_bar._chips[MON_VIEW].button.toolTip()

    def test_no_lock_or_style_change_above_the_limit(self):
        screen = _make_screen()
        screen.channel_bar.set_user_limit(1)
        chip = screen.channel_bar._chips[5]
        assert chip.button.isEnabled()
        assert chip.button.isCheckable()
        # Still selectable and usable exactly like any other chip.
        screen.channel_bar.set_current(5)
        assert screen.channel_bar.current() == 5


class TestChipConnectFlow:
    """P42.4 — connect/disconnect happen through the channel chips
    themselves, with no separate Connect/Dest/…/Disconnect row."""

    def test_click_on_other_chip_only_switches(self):
        screen = _make_screen()
        screen.channel_bar.set_current(1)
        screen.channel_bar._on_chip_clicked(3)
        assert screen.channel_bar.current() == 3
        assert not screen.channel_bar.is_editing()

    def test_second_click_on_current_free_chip_opens_editor(self):
        screen = _make_screen()
        screen.channel_bar.set_current(3)
        screen.channel_bar._on_chip_clicked(3)
        assert screen.channel_bar._chips[3].is_editing()

    def test_busy_chip_does_not_open_editor(self):
        screen = _make_screen()
        screen.channel_bar.set_channel_state(4, "connected", "OE1XYZ")
        screen.channel_bar.set_current(4)
        screen.channel_bar._on_chip_clicked(4)
        assert not screen.channel_bar.is_editing()

    def test_mon_chip_does_not_open_editor(self):
        screen = _make_screen()
        screen.channel_bar.set_current(MON_VIEW)
        screen.channel_bar._on_chip_clicked(MON_VIEW)
        assert not screen.channel_bar.is_editing()

    def test_enter_with_valid_callsign_emits_connect_requested_on_that_channel(self):
        screen = _make_screen()
        received: list[tuple[int, str]] = []
        screen.channel_bar.connect_requested.connect(
            lambda ch, call: received.append((ch, call))
        )
        screen.channel_bar.start_edit(3)
        chip = screen.channel_bar._chips[3]
        chip.editor.setText("oe3xyz-9")
        chip.editor.returnPressed.emit()

        assert received == [(3, "OE3XYZ-9")]
        assert not chip.is_editing()

    def test_invalid_callsign_keeps_field_open_and_emits_nothing(self):
        screen = _make_screen()
        received: list[tuple[int, str]] = []
        screen.channel_bar.connect_requested.connect(
            lambda ch, call: received.append((ch, call))
        )
        screen.channel_bar.start_edit(3)
        chip = screen.channel_bar._chips[3]
        chip.editor.setText("!!not valid!!")
        chip.editor.returnPressed.emit()

        assert received == []
        assert chip.is_editing()

    def test_escape_closes_without_a_signal(self):
        screen = _make_screen()
        received: list[tuple[int, str]] = []
        screen.channel_bar.connect_requested.connect(
            lambda ch, call: received.append((ch, call))
        )
        screen.channel_bar.start_edit(3, "OE3XYZ")
        chip = screen.channel_bar._chips[3]

        chip.cancel_edit()

        assert received == []
        assert not chip.is_editing()

    def test_mheard_double_click_prefills_the_first_free_chip(self):
        screen = _make_screen()
        screen.channel_bar.set_channel_state(0, "connected", "DL1ABC")
        screen.channel_bar.set_channel_state(1, "connected", "DL1DEF")

        screen.mheard_panel.connect_requested.emit("OE3XYZ")

        assert screen.channel_bar.current() == 2   # channels 0 and 1 are busy
        chip = screen.channel_bar._chips[2]
        assert chip.is_editing()
        assert chip.editor.text() == "OE3XYZ"

    def test_ctrl_k_disconnects_the_busy_current_channel(self):
        # P46.C.2: moved off Ctrl+D (now the TNC menu's "Disconnect +
        # Close Serial Port") to Ctrl+K, so the two different
        # "disconnect" actions (station link vs. serial port) no longer
        # share one shortcut.
        from PyQt6.QtCore import QEvent
        from PyQt6.QtGui import QKeyEvent

        screen = _make_screen()
        received: list[int] = []
        screen.channel_bar.disconnect_requested.connect(received.append)
        screen.channel_bar.set_channel_state(4, "connected", "OE1XYZ")
        screen.channel_bar.set_current(4)

        ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_K,
                        Qt.KeyboardModifier.ControlModifier)
        screen.eventFilter(screen.tx_input, ev)

        assert received == [4]

    def test_ctrl_k_on_a_free_channel_does_nothing(self):
        from PyQt6.QtCore import QEvent
        from PyQt6.QtGui import QKeyEvent

        screen = _make_screen()
        received: list[int] = []
        screen.channel_bar.disconnect_requested.connect(received.append)
        screen.channel_bar.set_current(3)

        ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_K,
                        Qt.KeyboardModifier.ControlModifier)
        screen.eventFilter(screen.tx_input, ev)

        assert received == []

    def test_ctrl_d_no_longer_disconnects_the_channel(self):
        # P46.C.2 - Ctrl+D must fall through untouched now (it belongs to
        # the TNC menu's "Disconnect + Close Serial Port" instead).
        from PyQt6.QtCore import QEvent
        from PyQt6.QtGui import QKeyEvent

        screen = _make_screen()
        received: list[int] = []
        screen.channel_bar.disconnect_requested.connect(received.append)
        screen.channel_bar.set_channel_state(4, "connected", "OE1XYZ")
        screen.channel_bar.set_current(4)

        ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_D,
                        Qt.KeyboardModifier.ControlModifier)
        screen.eventFilter(screen.tx_input, ev)

        assert received == []


class TestChipEditorClosesOnChannelSwitch:
    """P57.1 - chips are NoFocus (P41), so a click on a DIFFERENT chip
    never fires the editing chip's own focusOutEvent - the P42.1
    "losing focus cancels like Esc" rule never triggers for this case.
    Reproduced 26.09.2026 (screenshot): the cursor stayed in channel
    3's editor while channel 4 carried the active frame. ChannelBar
    now closes an open editor explicitly instead, from the one place
    (_select()/reset()) every channel-changing/resetting path already
    goes through - never a second, separate rule per caller."""

    def test_click_on_another_chip_closes_the_open_editor_and_still_switches(self):
        screen = _make_screen()
        received: list[tuple[int, str]] = []
        screen.channel_bar.connect_requested.connect(
            lambda ch, call: received.append((ch, call))
        )
        screen.channel_bar.start_edit(3)
        chip3 = screen.channel_bar._chips[3]
        assert chip3.is_editing()

        screen.channel_bar._on_chip_clicked(4)

        assert not chip3.is_editing()
        assert received == []  # discarded, not connected
        assert screen.channel_bar.current() == 4  # the click's normal effect still happened

    def test_set_current_from_outside_closes_the_open_editor(self):
        screen = _make_screen()
        screen.channel_bar.start_edit(3)
        chip3 = screen.channel_bar._chips[3]

        screen.channel_bar.set_current(5)

        assert not chip3.is_editing()
        assert screen.channel_bar.current() == 5

    def test_click_into_tx_field_closes_the_open_editor(self):
        from PyQt6.QtCore import QEvent, QPointF
        from PyQt6.QtGui import QMouseEvent

        screen = _make_screen()
        screen.channel_bar.start_edit(3)
        chip3 = screen.channel_bar._chips[3]
        assert chip3.is_editing()

        ev = QMouseEvent(
            QEvent.Type.MouseButtonPress, QPointF(5, 5),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        screen.eventFilter(screen.tx_input, ev)

        assert not chip3.is_editing()

    def test_reset_channels_closes_the_open_editor(self):
        screen = _make_screen()
        screen.channel_bar.start_edit(3)
        chip3 = screen.channel_bar._chips[3]

        screen.reset_channels()

        assert not chip3.is_editing()

    def test_escape_still_closes_the_editor_unchanged(self):
        screen = _make_screen()
        screen.channel_bar.start_edit(3)
        chip3 = screen.channel_bar._chips[3]

        chip3.cancel_edit()

        assert not chip3.is_editing()

    def test_enter_with_valid_callsign_still_connects_unchanged(self):
        screen = _make_screen()
        received: list[tuple[int, str]] = []
        screen.channel_bar.connect_requested.connect(
            lambda ch, call: received.append((ch, call))
        )
        screen.channel_bar.start_edit(3)
        chip3 = screen.channel_bar._chips[3]
        chip3.editor.setText("OE3XYZ")
        chip3.editor.returnPressed.emit()

        assert received == [(3, "OE3XYZ")]
        assert not chip3.is_editing()

    def test_two_double_clicks_in_a_row_leave_exactly_one_editor_open(self):
        screen = _make_screen()
        screen.channel_bar._on_chip_double_clicked(3)
        screen.channel_bar._on_chip_double_clicked(5)

        editing = [
            ch for ch, chip in screen.channel_bar._chips.items()
            if chip.is_editing()
        ]
        assert editing == [5]


class TestChipEditorBorder:
    """P57.2 - investigated the screenshot's second finding (the open
    editor showing a dark background with no amber border) via both
    static review and pixel-level rendering (QWidget.grab()), including
    reproducing the exact click-away sequence the screenshot showed -
    the border (#e8b23a, 2px, same width the selected chip's own
    border uses) rendered correctly in every case tried; no code-level
    defect was found. Kept as a pixel-level regression guard rather
    than a QSizePolicy-style check that would prove nothing (P56 Teil
    B's own lesson)."""

    def test_editor_border_pixels_are_the_specified_amber(self):
        screen = _make_screen()
        screen.show()
        _app.processEvents()
        screen.channel_bar.start_edit(3)
        _app.processEvents()

        chip3 = screen.channel_bar._chips[3]
        img = chip3.editor.grab().toImage()
        # Sample just inside the border on all four edges - antialiasing
        # makes the outermost pixel row/column unreliable.
        w, h = img.width(), img.height()
        samples = [
            img.pixelColor(1, h // 2).name(),
            img.pixelColor(w - 2, h // 2).name(),
            img.pixelColor(w // 2, 1).name(),
            img.pixelColor(w // 2, h - 2).name(),
        ]
        for color in samples:
            assert color.lower() in ("#e8b23a", "#e7b23a"), samples

    def test_border_still_amber_after_the_old_buggy_click_away_sequence(self):
        # Reproduces the exact pre-P57.1 sequence (channel switched to 4
        # WITHOUT closing chip 3's editor first) to confirm the border
        # was never actually the missing piece - this is what settled
        # that P57.2 needed no code fix.
        screen = _make_screen()
        screen.show()
        _app.processEvents()
        screen.channel_bar.start_edit(3)
        _app.processEvents()
        bar = screen.channel_bar
        bar._current = 4
        bar._chips[4].button.setChecked(True)
        for c in bar._chips:
            bar._update_chip(c)
        _app.processEvents()

        chip3 = bar._chips[3]
        assert chip3.is_editing()
        img = chip3.editor.grab().toImage()
        color = img.pixelColor(1, img.height() // 2).name()
        assert color.lower() in ("#e8b23a", "#e7b23a")


class TestChipCallingFailedStates(object):
    """P44 Teil A - a calling chip shows an ellipsis, and a failed
    connect attempt flashes CH_FAILED (red) before reverting to CH_FREE,
    rather than snapping straight back to a plain free chip."""

    def test_calling_chip_shows_ellipsis_suffix(self):
        screen = _make_screen()
        screen.channel_bar.set_channel_state(3, CH_CALLING, "OE3TEC")

        chip = screen.channel_bar._chips[3]
        assert chip._lbl_call.text() == "OE3TEC …"

    def test_connected_chip_shows_plain_callsign_no_ellipsis(self):
        screen = _make_screen()
        screen.channel_bar.set_channel_state(3, CH_CONNECTED, "OE3TEC")

        chip = screen.channel_bar._chips[3]
        assert chip._lbl_call.text() == "OE3TEC"

    def test_retry_count_exceeded_goes_through_failed_then_free(self):
        # HFPacketMode._handle_link_msg maps "Retry count exceeded" to
        # on_channel_state(ch, "free", "") - simulated directly here at
        # the ChannelBar level, which is what actually owns the
        # calling->failed->free transition (P44).
        screen = _make_screen()
        screen.channel_bar.set_channel_state(3, CH_CALLING, "OE3TEC")

        screen.channel_bar.set_channel_state(3, CH_FREE, "")

        assert screen.channel_bar.state(3) == CH_FAILED
        # The timer hasn't fired yet - directly exercise what it does,
        # without a real 1.5s wait in the test suite.
        screen.channel_bar._clear_failed(3)
        assert screen.channel_bar.state(3) == CH_FREE
        assert screen.channel_bar.partner(3) == ""

    def test_busy_goes_through_failed_then_free(self):
        screen = _make_screen()
        screen.channel_bar.set_channel_state(3, CH_CALLING, "OE3TEC")

        screen.channel_bar.set_channel_state(3, CH_FREE, "")  # "<call> busy"

        assert screen.channel_bar.state(3) == CH_FAILED

    def test_disconnected_while_calling_goes_through_failed_then_free(self):
        screen = _make_screen()
        screen.channel_bar.set_channel_state(3, CH_CALLING, "OE3TEC")

        screen.channel_bar.set_channel_state(3, CH_FREE, "")  # DISCONNECTED

        assert screen.channel_bar.state(3) == CH_FAILED

    def test_disconnect_from_connected_skips_failed_goes_straight_to_free(self):
        # A normal, successful hangup is not a failure - nothing to flash.
        screen = _make_screen()
        screen.channel_bar.set_channel_state(3, CH_CONNECTED, "OE3TEC")

        screen.channel_bar.set_channel_state(3, CH_FREE, "")

        assert screen.channel_bar.state(3) == CH_FREE

    def test_clear_failed_is_a_noop_if_state_already_moved_on(self):
        # A fresh connect attempt (or any other state change) in the
        # 1.5s window must not be undone by the stale timer firing late.
        screen = _make_screen()
        screen.channel_bar.set_channel_state(3, CH_CALLING, "OE3TEC")
        screen.channel_bar.set_channel_state(3, CH_FREE, "")
        assert screen.channel_bar.state(3) == CH_FAILED

        screen.channel_bar.set_channel_state(3, CH_CALLING, "OE1XYZ")
        screen.channel_bar._clear_failed(3)  # the old timer, firing late

        assert screen.channel_bar.state(3) == CH_CALLING
        assert screen.channel_bar.partner(3) == "OE1XYZ"

    def test_failed_chip_is_still_interactive_like_free(self):
        # A chip that just failed is exactly where a retry is most
        # likely - it must not be locked out for the flash's duration.
        screen = _make_screen()
        screen.channel_bar.set_channel_state(3, CH_CALLING, "OE3TEC")
        screen.channel_bar.set_channel_state(3, CH_FREE, "")
        assert screen.channel_bar.state(3) == CH_FAILED

        screen.channel_bar.start_edit(3, "OE1XYZ")

        assert screen.channel_bar._chips[3].is_editing()


class TestPulseAnimation(object):
    """P44 Teil A - one shared QVariantAnimation pulses every CALLING
    chip in sync; it runs only while at least one channel is calling."""

    def test_pulse_starts_when_a_channel_starts_calling(self):
        screen = _make_screen()
        assert screen.channel_bar._pulse.state() != QAbstractAnimation.State.Running

        screen.channel_bar.set_channel_state(3, CH_CALLING, "OE3TEC")

        assert screen.channel_bar._pulse.state() == QAbstractAnimation.State.Running

    def test_pulse_stops_when_no_channel_is_calling_any_more(self):
        screen = _make_screen()
        screen.channel_bar.set_channel_state(3, CH_CALLING, "OE3TEC")
        assert screen.channel_bar._pulse.state() == QAbstractAnimation.State.Running

        screen.channel_bar.set_channel_state(3, CH_CONNECTED, "OE3TEC")

        assert screen.channel_bar._pulse.state() != QAbstractAnimation.State.Running

    def test_pulse_keeps_running_while_at_least_one_channel_still_calls(self):
        screen = _make_screen()
        screen.channel_bar.set_channel_state(3, CH_CALLING, "OE3TEC")
        screen.channel_bar.set_channel_state(4, CH_CALLING, "DL1ABC")

        screen.channel_bar.set_channel_state(3, CH_CONNECTED, "OE3TEC")

        assert screen.channel_bar._pulse.state() == QAbstractAnimation.State.Running

    def test_pulse_tick_only_updates_calling_chips(self):
        from PyQt6.QtGui import QColor

        screen = _make_screen()
        screen.channel_bar.set_channel_state(3, CH_CALLING, "OE3TEC")
        screen.channel_bar.set_channel_state(4, CH_CONNECTED, "DL1ABC")

        before = screen.channel_bar._chips[4].button.styleSheet()
        screen.channel_bar._on_pulse_value(QColor("#a07020"))

        assert "#a07020" in screen.channel_bar._chips[3].button.styleSheet()
        assert screen.channel_bar._chips[4].button.styleSheet() == before

    def test_reset_stops_the_pulse(self):
        screen = _make_screen()
        screen.channel_bar.set_channel_state(3, CH_CALLING, "OE3TEC")
        assert screen.channel_bar._pulse.state() == QAbstractAnimation.State.Running

        screen.channel_bar.reset()

        assert screen.channel_bar._pulse.state() != QAbstractAnimation.State.Running


class TestMheardColourSemantics(object):
    """P44 Teil A.3 - one colour logic for the whole window: connected
    means CH_CONNECTED's green everywhere, not amber on MHEARD and green
    on the chip."""

    def test_mheard_connected_colour_matches_chip_connected_fill(self):
        from PyQt6.QtWidgets import QLabel
        from pk232py.ui.screens.packet_screen import _MheardRowWidget

        row = _MheardRowWidget("OE3TEC", "14:05", direct=False, channel=3)
        lbl = row.findChild(QLabel)

        assert lbl is not None
        # P77c: the label colour is the theme's green (readable as text on every
        # background); same hue family as the chip's fill, not necessarily the
        # identical hex (the chip fill is only 3.4 : 1 as text on white).
        from pk232py.ui.screens.ui_theme import get_theme
        assert get_theme()["panel_ok_color"] in lbl.styleSheet()
        for col in (_CHIP_FILL[CH_CONNECTED], get_theme()["panel_ok_color"]):
            r, g, b = int(col[1:3], 16), int(col[3:5], 16), int(col[5:7], 16)
            assert g > r and g > b, col                 # green in both

    def test_mheard_legend_says_green_not_amber(self):
        from PyQt6.QtWidgets import QLabel

        screen = _make_screen()
        legend_texts = [
            lbl.text() for lbl in screen.mheard_panel.findChildren(QLabel)
            if "direct (no digi)" in lbl.text()
        ]

        assert legend_texts, "legend label not found"
        assert "green = connected" in legend_texts[0]
        assert "amber" not in legend_texts[0]


class TestPerChannelRxDocuments:
    """P50 Teil B/C/F — one QTextDocument per channel plus a merged ALL
    document; the ALL/CH switch re-attaches rx_display to the right
    document instead of filtering at append time (T100, rewritten)."""

    def test_channel_history_survives_switching_away_and_back(self):
        screen = _make_screen()
        screen.set_view_all(False)
        screen.channel_bar.set_current(1)
        screen.append_channel_data(1, "hello from channel 1")

        screen.channel_bar.set_current(3)
        assert "hello from channel 1" not in screen.rx_display.toPlainText()

        screen.channel_bar.set_current(1)
        assert "hello from channel 1" in screen.rx_display.toPlainText()

    def test_all_view_contains_both_channels_in_arrival_order(self):
        screen = _make_screen()
        screen.set_view_all(True)
        screen.append_channel_data(1, "first")
        screen.append_channel_data(3, "second")

        text = screen.rx_display.toPlainText()
        assert text.index("first") < text.index("second")

    def test_ch_view_has_no_prefix(self):
        screen = _make_screen()
        screen.set_view_all(False)
        screen.channel_bar.set_current(2)
        screen.append_channel_data(2, "plain text")

        text = screen.rx_display.toPlainText()
        assert "plain text" in text
        assert "2│" not in text
        assert "[CH2]" not in text

    def test_all_view_has_the_compact_tag(self):
        screen = _make_screen()
        screen.set_view_all(True)
        screen.append_channel_data(2, "plain text")

        assert "2│plain text" in screen.rx_display.toPlainText()

    def test_timestamps_off_by_default(self):
        import re

        screen = _make_screen()
        screen.append_channel_data(1, "no clock please")

        text = screen.rx_display.toPlainText()
        assert "no clock please" in text
        assert re.search(r"\[\d{2}:\d{2}:\d{2}\]", text) is None

    def test_timestamps_on_when_enabled(self):
        import re

        screen = _make_screen()
        screen.set_view_all(False)
        screen.channel_bar.set_current(1)
        screen.apply_display_settings(show_timestamps=True, rx_max_lines=5000)
        screen.append_channel_data(1, "with a clock")

        text = screen.rx_display.toPlainText()
        assert re.search(r"\[\d{2}:\d{2}:\d{2}\] with a clock", text)

    def test_scroll_position_is_remembered_per_channel(self):
        screen = _make_screen()
        screen.set_view_all(False)
        screen.channel_bar.set_current(1)
        for i in range(200):
            screen.append_channel_data(1, f"line {i}")
        bar = screen.rx_display.verticalScrollBar()
        bar.setValue(bar.maximum() // 2)
        remembered = bar.value()

        screen.channel_bar.set_current(3)
        screen.channel_bar.set_current(1)

        assert screen.rx_display.verticalScrollBar().value() == remembered

    def test_reset_channels_clears_every_document(self):
        screen = _make_screen()
        screen.set_view_all(True)
        screen.append_channel_data(1, "will be gone")
        screen.append_monitor_data("also gone")

        screen.reset_channels()

        assert screen.rx_display.toPlainText().strip() == ""
        screen.channel_bar.set_current(1)
        screen.set_view_all(False)
        assert "will be gone" not in screen.rx_display.toPlainText()

    def test_system_message_color_override_is_applied(self):
        screen = _make_screen()
        screen.set_view_all(False)
        screen.channel_bar.set_current(1)
        screen.append_channel_data(1, "*** CONNECTED to OE3TEC ***", color="#ffaa00")

        doc = screen._rx_docs[1]
        # Walk the document's text blocks for a fragment matching our text
        # and confirm its foreground colour is the override, not the
        # plain channel-data blue.
        found = False
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid() and "CONNECTED" in frag.text():
                    assert frag.charFormat().foreground().color().name() == "#ffaa00"
                    found = True
                it += 1
            block = block.next()
        assert found, "system message fragment not found in the document"

    def test_every_rx_document_shares_rx_displays_font(self):
        # P55.C - a QTextDocument constructed with no setDefaultFont()
        # falls back to Qt's own generic default, not whatever font
        # rx_display happens to show - switching ALL/CH visibly changed
        # the font (26.09.2026) because rx_display.setFont() only ever
        # touched the ONE document attached when it was called, never a
        # document created (or swapped in later via setDocument())
        # afterward. Every per-channel document and the merged ALL
        # document must now share the exact font rx_display itself uses.
        screen = _make_screen()
        expected = screen.rx_display.font()
        for ch in range(CHANNEL_COUNT):
            assert screen._rx_docs[ch].defaultFont() == expected
        assert screen._rx_doc_all.defaultFont() == expected

    def test_font_stays_the_same_switching_between_all_and_a_channel(self):
        screen = _make_screen()
        expected = screen.rx_display.font()

        screen.set_view_all(True)
        assert screen.rx_display.document().defaultFont() == expected

        screen.channel_bar.set_current(2)
        screen.set_view_all(False)
        assert screen.rx_display.document().defaultFont() == expected

        screen.set_view_all(True)
        assert screen.rx_display.document().defaultFont() == expected


class TestMheardAutoPopulation:
    """P50 Teil E — MHEARD gains connection partners from live link
    messages, without waiting for a manual Refresh."""

    def test_connected_adds_partner_with_channel(self):
        screen = _make_screen()
        screen.channel_bar.set_channel_state(1, CH_CONNECTED, "OE3TEC")
        screen.mheard_panel.add_entry_if_new("OE3TEC", "12:00")
        screen.mheard_panel.set_channel_map(screen.channel_bar.channel_map())

        from PyQt6.QtWidgets import QLabel
        labels = [lbl.text() for lbl in screen.mheard_panel.findChildren(QLabel)]
        assert any("1 OE3TEC" in t for t in labels)

    def test_add_entry_if_new_does_not_duplicate(self):
        screen = _make_screen()
        screen.mheard_panel.add_entry_if_new("OE3TEC", "12:00")
        screen.mheard_panel.add_entry_if_new("OE3TEC", "12:05")

        matches = [e for e in screen.mheard_panel._entries if e[0] == "OE3TEC"]
        assert len(matches) == 1
        assert matches[0] == ("OE3TEC", "12:00", False)   # first write wins

    def test_disconnected_station_stays_but_loses_channel_and_colour(self):
        screen = _make_screen()
        screen.channel_bar.set_channel_state(1, CH_CONNECTED, "OE3TEC")
        screen.mheard_panel.add_entry_if_new("OE3TEC", "12:00")
        screen.mheard_panel.set_channel_map(screen.channel_bar.channel_map())

        screen.channel_bar.set_channel_state(1, CH_FREE, "")
        screen.mheard_panel.set_channel_map(screen.channel_bar.channel_map())

        assert any(e[0] == "OE3TEC" for e in screen.mheard_panel._entries)
        assert "OE3TEC" not in screen.channel_bar.channel_map()


class TestMonChipAndRegularChannelZero:
    """P70 A/B/C: MON is a separate, non-TNC view; channel 0 is a normal channel."""

    def test_channel_zero_opens_the_connect_editor(self):
        screen = _make_screen()
        screen.channel_bar.set_current(0)
        screen.channel_bar._on_chip_clicked(0)
        assert screen.channel_bar._chips[0].is_editing()

    def test_mon_chip_exists_before_channel_zero(self):
        screen = _make_screen()
        bar = screen.channel_bar
        assert MON_VIEW in bar._chips
        assert bar._chips[MON_VIEW]._lbl_num.text() == "MON"
        layout = bar.layout()
        order = [w for w in (layout.itemAt(i).widget() for i in range(layout.count()))
                 if w is not None]   # the spacer after MON has no widget
        assert order.index(bar._chips[MON_VIEW]) + 1 == order.index(bar._chips[0])

    def test_mon_chip_has_no_connect_editor_or_state(self):
        screen = _make_screen()
        bar = screen.channel_bar
        bar.set_current(MON_VIEW)
        bar._on_chip_clicked(MON_VIEW)
        assert not bar.is_editing()
        bar.set_channel_state(MON_VIEW, "connected", "X")
        assert bar.channel_map() == {}

    def test_mon_view_takes_monitor_lines(self):
        screen = _make_screen()
        screen.set_view_all(False)
        screen.channel_bar.set_current(MON_VIEW)
        screen.append_monitor_data("heard something")
        assert "heard something" in screen.rx_display.toPlainText()

    def test_monitor_lines_do_not_land_in_channel_zero(self):
        screen = _make_screen()
        screen.set_view_all(False)
        screen.channel_bar.set_current(0)
        screen.append_monitor_data("heard something")
        assert screen.rx_display.toPlainText() == ""

    def test_disconnecting_state_is_shown_and_counts_as_busy(self):
        screen = _make_screen()
        screen.channel_bar.set_channel_state(2, "disconnecting", "OE3GAS-2")
        assert screen.channel_bar.state(2) == "disconnecting"
        screen.channel_bar.set_current(2)
        screen.channel_bar._on_chip_clicked(2)
        assert not screen.channel_bar.is_editing()

    def test_step_includes_mon(self):
        screen = _make_screen()
        bar = screen.channel_bar
        bar.set_current(0)
        bar.step(-1)
        assert bar.current() == MON_VIEW
        bar.step(1)
        assert bar.current() == 0
