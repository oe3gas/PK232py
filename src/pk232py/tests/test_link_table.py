# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Unit tests for pk232py.comm.link_table.LinkTable (P67, Teil B/E).

Qt-free - no QApplication needed, unlike most of this project's tests.
"""

from __future__ import annotations

from pk232py.comm.link_status import LinkStatus
from pk232py.comm.link_table import (
    STATE_CONNECTED,
    STATE_FREE,
    STATE_UNCONFIRMED,
    ChannelLink,
    LinkTable,
)


class TestOnVerboseLine:
    def test_connected_sets_channel_and_converse_true(self):
        table = LinkTable()
        table.on_verbose_line("*** CONNECTED to OE3GAS-1 ***")

        assert table.channels[table.io_channel].state == STATE_CONNECTED
        assert table.channels[table.io_channel].partner == "OE3GAS-1"
        assert table.converse is True

    def test_cmd_prompt_clears_converse_but_keeps_the_connection(self):
        table = LinkTable()
        table.on_verbose_line("*** CONNECTED to OE3GAS-1 ***")
        table.on_verbose_line("cmd:")

        assert table.converse is False
        assert table.channels[table.io_channel].state == STATE_CONNECTED
        assert table.channels[table.io_channel].partner == "OE3GAS-1"

    def test_channel_prefix_names_a_channel_other_than_io_channel(self):
        table = LinkTable()
        table.io_channel = 9
        table.on_verbose_line("\x000: ?already connected …")

        # The prefix names channel 0 - io_channel (9) must be untouched.
        assert table.channels[9].state == STATE_FREE

    def test_disconnected_frees_the_channel(self):
        table = LinkTable()
        table.on_verbose_line("*** CONNECTED to OE3GAS-1 ***")
        table.on_verbose_line("*** DISCONNECTED: OE3GAS-1 ***")

        assert table.channels[table.io_channel].state == STATE_FREE


class TestMarkUnconfirmedAndReconcile:
    def test_mark_unconfirmed_then_co_free_frees_the_channel(self):
        table = LinkTable()
        table.on_link_status(LinkStatus(channel=1, connected=True, partner="OE3GAS-1"))
        assert table.channels[1].state == STATE_CONNECTED

        table.mark_unconfirmed()
        assert table.channels[1].state == STATE_UNCONFIRMED

        table.on_link_status(LinkStatus(channel=1, connected=False))
        assert table.channels[1].state == STATE_FREE

    def test_mark_unconfirmed_then_co_connected_reconfirms(self):
        table = LinkTable()
        table.on_link_status(LinkStatus(channel=1, connected=True, partner="OE3GAS-1"))

        table.mark_unconfirmed()
        assert table.channels[1].state == STATE_UNCONFIRMED

        table.on_link_status(LinkStatus(channel=1, connected=True, partner="OE3GAS-1"))
        assert table.channels[1].state == STATE_CONNECTED
        assert table.channels[1].partner == "OE3GAS-1"

    def test_mark_unconfirmed_leaves_free_channels_untouched(self):
        table = LinkTable()
        table.mark_unconfirmed()
        assert table.channels[5].state == STATE_FREE

    def test_unparsed_or_error_code_link_status_is_ignored(self):
        table = LinkTable()
        table.on_link_status(LinkStatus(channel=2, connected=True, partner="X"))
        table.on_link_status(LinkStatus(channel=2, unparsed=True))
        # unparsed proves nothing - the channel's prior state stands.
        assert table.channels[2].state == STATE_CONNECTED

        table.on_link_status(LinkStatus(channel=2, error_code=0x0C))
        assert table.channels[2].state == STATE_CONNECTED


class TestObserver:
    def test_observer_called_exactly_once_per_change(self):
        table = LinkTable()
        events: list[tuple[int, str, str]] = []
        table.subscribe(lambda ch, link: events.append((ch, link.state, link.partner)))

        table.on_verbose_line("*** CONNECTED to OE3GAS-1 ***")

        assert events == [(0, STATE_CONNECTED, "OE3GAS-1")]

    def test_no_notification_when_state_is_unchanged(self):
        table = LinkTable()
        events: list[tuple[int, str]] = []
        table.on_link_status(LinkStatus(channel=1, connected=True, partner="OE3GAS-1"))
        table.subscribe(lambda ch, link: events.append((ch, link.state)))

        # Same state, same partner - re-confirming must not re-notify.
        table.on_link_status(LinkStatus(channel=1, connected=True, partner="OE3GAS-1"))

        assert events == []

    def test_multiple_channel_changes_each_notify_once(self):
        table = LinkTable()
        events: list[int] = []
        table.subscribe(lambda ch, link: events.append(ch))

        table.on_link_status(LinkStatus(channel=0, connected=True, partner="A"))
        table.on_link_status(LinkStatus(channel=1, connected=True, partner="B"))
        table.mark_unconfirmed()

        assert events == [0, 1, 0, 1]


class TestOnHostLinkMessage:
    def test_connected_to(self):
        table = LinkTable()
        table.on_host_link_message(1, "CONNECTED to OE3GAS-1")
        assert table.channels[1].state == STATE_CONNECTED
        assert table.channels[1].partner == "OE3GAS-1"

    def test_disconnected(self):
        table = LinkTable()
        table.on_link_status(LinkStatus(channel=1, connected=True, partner="X"))
        table.on_host_link_message(1, "DISCONNECTED: OE3GAS-1")
        assert table.channels[1].state == STATE_FREE

    def test_busy(self):
        table = LinkTable()
        table.on_host_link_message(2, "OE3GAS-1 busy")
        assert table.channels[2].state == STATE_FREE

    def test_retry_count_exceeded_has_no_callsign_and_frees_the_channel(self):
        table = LinkTable()
        table.on_link_status(LinkStatus(channel=3, connected=True, partner="X"))
        table.on_host_link_message(3, "Retry count exceeded")
        assert table.channels[3].state == STATE_FREE


class TestOnVerboseCstatus:
    def test_io_marker_sets_io_channel(self):
        table = LinkTable()
        table.on_verbose_cstatus({9: (True, "IO", "")})
        assert table.io_channel == 9

    def test_partner_confirms_connected(self):
        table = LinkTable()
        table.on_verbose_cstatus({0: (True, "IO CONNECTED to OE3GAS-1", "OE3GAS-1")})
        assert table.channels[0].state == STATE_CONNECTED
        assert table.channels[0].partner == "OE3GAS-1"


class TestReset:
    def test_reset_frees_every_channel_and_clears_converse(self):
        table = LinkTable()
        table.on_link_status(LinkStatus(channel=1, connected=True, partner="X"))
        table.converse = True
        table.io_channel = 5

        table.reset()

        assert all(link.state == STATE_FREE for link in table.channels)
        assert table.converse is False
        assert table.io_channel == 0

    def test_reset_does_not_touch_mode_name(self):
        table = LinkTable()
        table.mode_name = "VHF Packet"

        table.reset()

        assert table.mode_name == "VHF Packet"


class TestChannelLinkDefaults:
    def test_default_state_is_free(self):
        link = ChannelLink()
        assert link.state == STATE_FREE
        assert link.partner == ""
