# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Unit tests for MainWindow's Packet MON/channel wiring (P10.2, P70)
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
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox

from pk232py.comm.frame import FrameKind
from pk232py.ui.main_window import MainWindow
from pk232py.modes.packet_vhf import VHFPacketMode
from pk232py.ui.screens.packet_screen import MON_VIEW

_app = QApplication.instance() or QApplication([])


class _FakeLinkMsgFrame:
    def __init__(self, channel: int, text: str):
        self.channel = channel
        self.text = text
        self.kind = FrameKind.LINK_MSG


class _StubSerial:
    is_connected = True
    is_host_mode = True
    fresh_boot_defaults = False

    def __init__(self):
        self.calls: list[tuple] = []

    def consume_fresh_boot_defaults(self) -> bool:
        """P60, A.1 - mirrors the real SerialManager: read the event and
        clear it in one step, so a test's own direct
        `w._serial.fresh_boot_defaults = True` still behaves as a
        one-shot event once consumed, exactly like the real property/
        _banner_this_init pair."""
        fresh = self.fresh_boot_defaults
        self.fresh_boot_defaults = False
        return fresh

    def send_channel_command(self, ch, mnemonic, args=b""):
        self.calls.append(("ch_cmd", ch, mnemonic, args))
        return True

    def send_data(self, data, channel=0):
        self.calls.append(("data", channel, data))
        return True

    def send_command(self, mnemonic, args=b""):
        self.calls.append(("cmd", mnemonic, args))
        return True

    def exit_host_mode(self, io_channel=None):
        self.calls.append(("exit_host_mode", io_channel))

    def write_verbose(self, data):
        self.calls.append(("write_verbose", data))
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
    yield w, screen
    # P61: teardown used to remove the event filter and call close()/
    # deleteLater()/processEvents() here itself (P41/P42 - see git
    # history for the two separate incidents that added each of those
    # calls). The conftest.py-wide dispose_main_windows autouse fixture
    # now does this generically for every MainWindow any test built,
    # never via close() (which would run closeEvent(), popping a real,
    # unclickable QMessageBox.question() since _StubSerial.is_connected
    # is a class attribute hardcoded to True).


class TestUnprotoUsesMonView:
    """T98, rebased by P70 (MON view instead of channel 0).

    P42 note: Connect/Disconnect no longer have buttons of their own, so
    the old "locks buttons" assertion here is now covered instead by
    TestConnectRejectedOnMon (the MON chip refuses to
    open its inline connect editor at all). This class keeps the parts of
    T98 that are still meaningful: the channel-0 switch itself and
    Unproto's own enable/disable state.
    """

    def test_unproto_on_switches_to_mon_view(self, wired_vhf):
        w, screen = wired_vhf
        screen.channel_bar.set_current(3)
        screen.tx_input.setPlainText("draft on ch3")

        screen.btn_unproto.setChecked(True)

        assert screen.current_channel() == MON_VIEW

    def test_unproto_off_does_not_auto_jump_channel(self, wired_vhf):
        w, screen = wired_vhf
        screen.channel_bar.set_current(3)
        screen.btn_unproto.setChecked(True)
        assert screen.current_channel() == MON_VIEW

        screen.btn_unproto.setChecked(False)
        assert screen.current_channel() == MON_VIEW   # operator must pick a chip

    def test_selecting_qso_channel_turns_unproto_off(self, wired_vhf):
        w, screen = wired_vhf
        screen.channel_bar.set_current(3)
        screen.tx_input.setPlainText("draft on ch3")
        screen.btn_unproto.setChecked(True)
        assert screen.current_channel() == MON_VIEW

        screen.channel_bar.set_current(3)

        assert not screen.btn_unproto.isChecked()
        assert screen.tx_input.toPlainText() == "draft on ch3"   # P9 preserved

    def test_connected_channel_does_not_lock_unproto(self, wired_vhf):
        # P70 D: Unproto goes out on the lowest FREE channel (T146 F1/F2),
        # so a connection - on any channel - never locks the button.
        w, screen = wired_vhf
        screen.channel_bar.set_current(5)
        w._link_table.on_host_link_message(5, "CONNECTED to OE3GAS-5")
        assert screen.btn_unproto.isEnabled()

        screen.channel_bar.set_current(MON_VIEW)
        assert screen.btn_unproto.isEnabled()


class TestConnectRejectedOnMon:
    """T99, rebased by P70 - the MON chip (no TNC channel) can never hold
    a connection.

    Under the old Connect/Dest row this was enforced in MainWindow (a
    warning dialog + un-checking btn_connect). P42 moved the guard to the
    source instead: ChannelChip.start_edit() refuses to open its inline
    editor at all for channel 0, so connect_requested can never even be
    emitted for it - MainWindow's _on_chip_connect_requested() is never
    reached, and no serial frame is ever built.
    """

    def test_mon_chip_refuses_to_open_its_editor(self, wired_vhf):
        w, screen = wired_vhf
        screen.channel_bar.set_current(MON_VIEW)

        screen.channel_bar.start_edit_current()

        assert not screen.channel_bar.is_editing()
        assert w._serial.calls == []
        assert screen.channel_bar.state(MON_VIEW) == "free"

    def test_mon_never_emits_connect_requested(self, wired_vhf):
        w, screen = wired_vhf
        received: list[tuple[int, str]] = []
        screen.channel_bar.connect_requested.connect(
            lambda ch, call: received.append((ch, call))
        )

        screen.channel_bar.start_edit(MON_VIEW, "OE1XYZ")

        assert not screen.channel_bar.is_editing()
        assert received == []
        assert w._serial.calls == []


class TestLinkMessageGatedByVisibleChannel:
    """T102 — a link message for a channel other than the visible one must
    not touch Unproto's enabled state (P42: Connect/Disconnect no longer
    have buttons to gate; P70 removed the Unproto lock too);
    ChannelBar itself still updates (it is a separate,
    always-on, per-channel consumer of the same message)."""

    def test_message_for_other_channel_does_not_change_unproto(self, wired_vhf):
        w, screen = wired_vhf
        mode = w._modes.current_mode

        # Channel 4 connects while it is the visible channel.
        screen.channel_bar.set_current(4)
        mode.handle_frame(_FakeLinkMsgFrame(4, "CONNECTED to OE1XYZ"))
        # P70: a connection never locks Unproto any more.
        assert screen.btn_unproto.isEnabled()

        screen.channel_bar.set_current(MON_VIEW)
        assert screen.btn_unproto.isEnabled()

        # A link message for channel 4 arrives while channel 0 is visible.
        mode.handle_frame(_FakeLinkMsgFrame(4, "CONNECTED to OE1XYZ"))

        # Unproto must stay exactly as the visible channel (0) dictates.
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
        assert screen.btn_unproto.isEnabled()


class TestLinkMessageAppearsInItsOwnChannel:
    """P47 — a $5x link message must appear in the channel it actually
    happened on, never wherever the operator's screen happens to be
    pointed. Reproduced 25.09.2026 (screenshot): a channel-1 "Retry count
    exceeded ... DISCONNECTED: OE3XTC" appeared on the UI chip (channel 0)
    because that was the visible channel at the time the message arrived.
    Never attributed by callsign — "Retry count exceeded" carries none.

    wired_vhf builds a REAL MainWindow(), whose ConfigManager reads/writes
    the operator's actual ~/.pk232py/pk232py.ini (MainWindow.closeEvent()
    auto-saves it on close, and the fixture's teardown calls w.close()) -
    there is no test-isolated config here. Every test below therefore sets
    show_link_messages_in_ui_channel EXPLICITLY at the start (never assumes
    it is already at some default) and restores it to False in a finally
    block before returning if it changed it — found the hard way
    (25.09.2026): an earlier version of this class set it True with no
    reset, and the fixture's own close()-triggered save wrote
    "show_link_messages_in_ui_channel = true" into the real INI file,
    which then leaked into every later MainWindow() in the SAME pytest
    run (including other test files) reading that same real path."""

    def test_message_for_channel_1_appears_while_viewing_channel_1(self, wired_vhf):
        w, screen = wired_vhf
        mode = w._modes.current_mode
        w._app_config.hf_packet.show_link_messages_in_ui_channel = False
        screen.channel_bar.set_current(1)

        mode.handle_frame(_FakeLinkMsgFrame(1, "DISCONNECTED: OE3XTC"))

        assert "*** DISCONNECTED: OE3XTC ***" in screen.rx_display.toPlainText()

    def test_same_message_does_not_appear_on_mon_view_in_ch_view(self, wired_vhf):
        w, screen = wired_vhf
        mode = w._modes.current_mode
        w._app_config.hf_packet.show_link_messages_in_ui_channel = False
        screen.channel_bar.set_current(MON_VIEW)
        screen.set_view_all(False)

        mode.handle_frame(_FakeLinkMsgFrame(1, "DISCONNECTED: OE3XTC"))

        assert "OE3XTC" not in screen.rx_display.toPlainText()

    def test_all_view_shows_the_message_with_its_channel_tag(self, wired_vhf):
        w, screen = wired_vhf
        mode = w._modes.current_mode
        w._app_config.hf_packet.show_link_messages_in_ui_channel = False
        screen.channel_bar.set_current(MON_VIEW)
        screen.set_view_all(True)

        mode.handle_frame(_FakeLinkMsgFrame(1, "DISCONNECTED: OE3XTC"))

        text = screen.rx_display.toPlainText()
        # P50 Teil C: the compact ALL-view tag is "1|", not the old "[CH1]".
        assert "1│" in text
        assert "*** DISCONNECTED: OE3XTC ***" in text

    def test_channel_15_always_appears_in_mon_view(self, wired_vhf):
        # $5F is not channel-scoped at all (e.g. the generic data ack) -
        # there is nowhere else for it to belong, regardless of the
        # mirror setting (explicitly off here).
        w, screen = wired_vhf
        mode = w._modes.current_mode
        w._app_config.hf_packet.show_link_messages_in_ui_channel = False
        screen.channel_bar.set_current(MON_VIEW)
        screen.set_view_all(False)

        mode.on_link_message(15, "some generic status")

        assert "some generic status" in screen.rx_display.toPlainText()

    def test_mirror_setting_off_does_not_leak_into_mon_view(self, wired_vhf):
        w, screen = wired_vhf
        mode = w._modes.current_mode
        w._app_config.hf_packet.show_link_messages_in_ui_channel = False
        screen.channel_bar.set_current(MON_VIEW)
        screen.set_view_all(False)

        mode.handle_frame(_FakeLinkMsgFrame(1, "DISCONNECTED: OE3XTC"))

        assert "OE3XTC" not in screen.rx_display.toPlainText()

    def test_mirror_setting_on_duplicates_into_mon_view_with_a_tag(self, wired_vhf):
        w, screen = wired_vhf
        mode = w._modes.current_mode
        w._app_config.hf_packet.show_link_messages_in_ui_channel = True
        try:
            screen.channel_bar.set_current(MON_VIEW)
            screen.set_view_all(False)

            mode.handle_frame(_FakeLinkMsgFrame(1, "DISCONNECTED: OE3XTC"))

            assert "[ch1] *** DISCONNECTED: OE3XTC ***" in screen.rx_display.toPlainText()
        finally:
            # See the class docstring — must not leak into the real INI
            # file via the fixture's close()-triggered auto-save.
            w._app_config.hf_packet.show_link_messages_in_ui_channel = False

    def test_mirror_setting_does_not_duplicate_a_mon_message(self, wired_vhf):
        # channel 15 already goes to the MON view itself -
        # mirroring it into itself would just double it.
        w, screen = wired_vhf
        mode = w._modes.current_mode
        w._app_config.hf_packet.show_link_messages_in_ui_channel = True
        try:
            screen.channel_bar.set_current(MON_VIEW)
            screen.set_view_all(False)

            mode.on_link_message(15, "some generic status")

            text = screen.rx_display.toPlainText()
            assert text.count("some generic status") == 1
        finally:
            w._app_config.hf_packet.show_link_messages_in_ui_channel = False

    def test_single_arg_call_channel_none_is_unaffected_by_p47(self, wired_vhf):
        # AMTOR/PACTOR call on_link_message(msg) with no channel argument -
        # _make_link_handler() must still route these through
        # _on_mode_link_message() exactly as before P47 (unrelated to
        # append_channel_data()/UI-channel routing entirely).
        w, screen = wired_vhf
        mode = w._modes.current_mode

        mode.on_link_message("CONNECTED")

        assert "*** CONNECTED ***" in w._rx_display.toPlainText()

    def test_set_status_still_fires_regardless_of_visible_channel(self, wired_vhf):
        w, screen = wired_vhf
        mode = w._modes.current_mode
        screen.channel_bar.set_current(MON_VIEW)

        mode.handle_frame(_FakeLinkMsgFrame(1, "DISCONNECTED: OE1XYZ"))

        assert "DISCONNECTED" in screen.lbl_status.text()


class TestMheardColumnMapping:
    """P55.A — MHEARD's Callsign/Channel/Time columns showed a DAYSTAMP
    date and/or a timestamp fragment instead of the real callsign
    (26.09.2026 screenshot). _extract_partner()'s own colon-split fix is
    covered separately in test_packet_hf.py::TestExtractPartner; this
    covers the OTHER contributing source, MainWindow._parse_mheard_line()
    (the MH-poll response format), plus an end-to-end check that a live
    link message fills the panel correctly through the real pipeline."""

    def test_mh_line_with_daystamp_date_prefix(self):
        # Real MH line shape once DAYSTAMP is ON (the upload default) -
        # a leading "DD-Mon-YY" date token ahead of the time/callsign
        # this parser already handled correctly.
        callsign, time_str, direct = MainWindow._parse_mheard_line(
            "25-Sep-26 00:05:23 OE3TEC-1*"
        )
        assert callsign == "OE3TEC-1"
        assert time_str == "00:05"
        assert direct is True

    def test_mh_line_without_daystamp_still_works(self):
        # Pre-existing, already-correct case - must not regress.
        callsign, time_str, direct = MainWindow._parse_mheard_line(
            "18:06:27 OE3GAS*"
        )
        assert callsign == "OE3GAS"
        assert time_str == "18:06"
        assert direct is True

    def test_mh_line_bare_callsign_no_date_no_time(self):
        callsign, time_str, direct = MainWindow._parse_mheard_line("OE1XYZ")
        assert callsign == "OE1XYZ"
        assert time_str == ""
        assert direct is False

    def test_mh_line_daystamp_prefix_with_no_direct_marker(self):
        callsign, time_str, direct = MainWindow._parse_mheard_line(
            "25-Sep-26 00:05:23 DB0MUC"
        )
        assert callsign == "DB0MUC"
        assert time_str == "00:05"
        assert direct is False

    def test_disconnected_with_tnc_own_timestamp_fills_callsign_column_correctly(
        self, wired_vhf
    ):
        # End-to-end through the real pipeline: HFPacketMode.handle_frame()
        # -> on_channel_state() -> MainWindow._make_channel_state_handler()
        # -> MheardPanel.add_entry_if_new(). CONSTAMP/DAGSTAMP both ON is
        # the upload default, so a real DISCONNECTED carries this exact
        # date+time prefix.
        w, screen = wired_vhf
        mode = w._modes.current_mode

        mode.handle_frame(_FakeLinkMsgFrame(
            3, "*** 25-Sep-26 21:04:36 DISCONNECTED: OE3TEC-1 ***"
        ))

        entries = screen.mheard_panel._entries
        assert entries
        callsign, _time_str, _direct = entries[0]
        assert callsign == "OE3TEC-1"


class TestTxEchoAppearsInChannelDocumentToo:
    """P55.B — the TX echo used to write directly into whichever ONE RX
    document rx_display happened to be showing at send time (ALL or the
    current channel's own), via its own manual cursor manipulation,
    instead of through append_channel_data() (P50 Teil B), which writes
    into BOTH. Reproduced 26.09.2026: '> ch1 just testing' appeared in
    ALL view but not in CH view of the very channel it was sent on."""

    def test_tx_echo_lands_in_both_the_channel_document_and_all(self, wired_vhf):
        w, screen = wired_vhf
        screen.channel_bar.set_channel_state(1, "connected", "OE3TEC")
        screen.channel_bar.set_current(1)
        screen.tx_input.setPlainText("just testing")

        w._on_packet_tx_enter()

        assert "just testing" in screen._rx_docs[1].toPlainText()
        assert "just testing" in screen._rx_doc_all.toPlainText()


class TestAppearanceFontReachesEveryRxDocument:
    """P56.A - P55's _RX_FONT fixed the ALL-vs-CH font mismatch by
    pinning every RX document to a hardcoded constant, but that
    introduced a SECOND font source independent of the operator's own
    Appearance setting - reproduced 26.09.2026 (screenshot, maximized
    window): ALL view correctly showed "Cascadia Mono SemiBold 14pt",
    CH view did not. _RX_FONT is gone; MainWindow._apply_appearance()
    is now the one place every RX document's font comes from, via the
    new PacketBaseScreen.apply_rx_font()."""

    def test_appearance_change_reaches_a_channel_document_never_shown(self, wired_vhf):
        # Channel 3 is never the currently-attached document (the
        # default view is ALL) - exactly the case P55's rx_display.
        # setFont() alone could never reach.
        w, screen = wired_vhf
        w._app_config.appearance.theme = "custom"
        w._app_config.appearance.font_family = "Cascadia Mono SemiBold"
        w._app_config.appearance.font_size = 14

        w._apply_appearance()

        expected = QFont("Cascadia Mono SemiBold", 14)
        assert screen._rx_docs[3].defaultFont() == expected
        assert screen._rx_doc_all.defaultFont() == expected
        assert screen.rx_display.font() == expected

    def test_a_document_created_before_the_change_gets_the_new_font_too(self, wired_vhf):
        w, screen = wired_vhf
        before = QFont(screen._rx_docs[5].defaultFont())

        w._app_config.appearance.theme = "custom"
        w._app_config.appearance.font_family = "Consolas"
        w._app_config.appearance.font_size = 18
        w._apply_appearance()

        after = screen._rx_docs[5].defaultFont()
        assert after != before
        assert after == QFont("Consolas", 18)


class TestPacketRxTxSplitterPersistence:
    """P50 Teil D - the Packet screen's own RX/TX splitter size is saved
    and restored alongside the window geometry.

    Uses a REDIRECTED QSettings (never the real one) - QSettings("OE3GAS",
    APP_TITLE) writes to the OS-native persistent store (Windows registry
    equivalent), the same class of risk P48 closed for ConfigManager's
    INI file, just for a different persistence mechanism.
    """

    def test_splitter_sizes_round_trip_through_settings(self, wired_vhf, monkeypatch):
        # Checks the SAVE/RESTORE WIRING (right QSettings key written, the
        # SAME values read back and handed to setSizes()) rather than the
        # splitter's own final .sizes() - QSplitter renormalizes requested
        # sizes against the widget's actual on-screen width, which is not
        # meaningful under the offscreen QPA platform with no real
        # show()/resize(), so pixel-exact round-tripping is not something
        # this test can (or needs to) assert.
        w, screen = wired_vhf
        store: dict = {}

        class _FakeQSettings:
            def __init__(self, *_a, **_k):
                pass

            def setValue(self, key, value):
                store[key] = value

            def value(self, key, default=None):
                return store.get(key, default)

        import pk232py.ui.main_window as mw
        monkeypatch.setattr(mw, "QSettings", _FakeQSettings)

        screen._rxtx_splitter.setSizes([300, 120])
        w._save_window_geometry()

        saved = list(store["vhfPacketRxTxSplitterSizes"])
        assert saved == list(screen._rxtx_splitter.sizes())

        restore_calls: list[list[int]] = []
        orig_set_sizes = screen._rxtx_splitter.setSizes
        monkeypatch.setattr(
            screen._rxtx_splitter, "setSizes",
            lambda sizes: (restore_calls.append(list(sizes)), orig_set_sizes(sizes))[1],
        )

        w._restore_window_geometry()

        assert restore_calls and [int(x) for x in restore_calls[0]] == saved


class TestPassallMnemonic:
    """T86 (P16, hardware-verified 21.09.2026): PASSALL is host mnemonic
    PX, not PS. PS is PASS, a masking character - not a toggle; sending
    'PS Y'/'PS N' would overwrite the masking character with the letter Y
    or N instead of switching PASSALL. The 2026-06-22 fix (PA -> PS) was
    itself wrong; corrected here to PA -> PX (packet activation vs the
    real PASSALL toggle)."""

    def test_passall_toggle_sends_px(self, wired_vhf):
        w, screen = wired_vhf
        screen.btn_passall.setChecked(True)

        cmds = [c for c in w._serial.calls if c[0] == "cmd"]
        assert ("cmd", b'PX', b'Y') in cmds

        screen.btn_passall.setChecked(False)
        cmds = [c for c in w._serial.calls if c[0] == "cmd"]
        assert ("cmd", b'PX', b'N') in cmds

    def test_no_packet_screen_button_sends_ps(self, wired_vhf):
        w, screen = wired_vhf
        for btn in (
            screen.btn_eas, screen.btn_passall, screen.btn_mrpt,
            screen.btn_mid, screen.btn_squelch,
        ):
            btn.setChecked(True)
            btn.setChecked(False)

        assert not any(
            c[0] == "cmd" and c[1] == b'PS' for c in w._serial.calls
        )


class TestModeInstanceFactory:
    """P19.2: _build_mode_instance() is the ONE place a mode instance is
    built with configured values - every real activation path in
    main_window.py must route through it, or a call site that forgets to
    pass mode_instance silently falls back to ModeManager's cls()
    (constructor defaults, not the operator's configuration).

    Values are deliberately NOT the defaults (1/30) - a test using the
    defaults would pass even without the P18.1/P19.2 fix, since
    HFPacketMode()'s own constructor defaults happen to match them.
    """

    @pytest.fixture
    def window(self):
        w = MainWindow()
        stub = _StubSerial()
        w._serial = stub
        # ModeManager captured its own reference to the real SerialManager
        # at construction time - swap it too, or set_mode() sees the real
        # (unconnected) serial, fails with "TNC not connected", and
        # _on_mode_switch_failed() pops a blocking QMessageBox.warning()
        # that hangs headless tests forever.
        w._modes._serial = stub
        w._app_config.hf_packet.maxframe = 2
        w._app_config.hf_packet.slottime = 20
        return w

    def _mx_sl_commands(self, w):
        return [c for c in w._serial.calls if c[0] == "cmd" and c[1] in (b'MX', b'SL')]

    def test_on_mode_selected_hf_packet_carries_configured_values(self, window):
        w = window
        assert w._modes.current_mode_name != "HF Packet"

        w._on_mode_selected("HF Packet")
        w._modes._send_init_frames()   # fire the 300ms init-frame timer now

        cmds = self._mx_sl_commands(w)
        assert ("cmd", b'MX', b'2') in cmds
        assert ("cmd", b'SL', b'20') in cmds
        # Neither HFPacketMode's own defaults nor VHF's hardcoded values
        # must sneak in.
        assert ("cmd", b'MX', b'1') not in cmds
        assert ("cmd", b'SL', b'30') not in cmds
        assert ("cmd", b'MX', b'4') not in cmds
        assert ("cmd", b'SL', b'10') not in cmds

    def test_host_mode_entry_default_activation_still_works(self, window):
        # _update_host_mode_ui(True) is the OTHER real set_mode() call site
        # in main_window.py (P19.1) - it always activates Baudot RTTY, so
        # it carries no HF-specific values, but it must keep working with
        # mode_instance routed through the same factory (returns None here).
        w = window
        assert not w._modes.current_mode_name

        w._update_host_mode_ui(True)
        w._modes._send_init_frames()

        assert w._modes.current_mode_name == "Baudot RTTY"
        assert self._mx_sl_commands(w) == []


class TestLinkTableHostModeCarryOver:
    """P67, Teil C.2/C.3/E: the LinkTable-driven mode-name and channel
    carry-over across a verbose<->Host Mode switch, at the MainWindow
    level (comm/link_table.py and comm/link_status.py have their own
    unit tests - this checks MainWindow's own wiring of them)."""

    @pytest.fixture
    def window(self):
        w = MainWindow()
        stub = _StubSerial()
        w._serial = stub
        w._modes._serial = stub
        return w

    def test_host_entry_restores_last_packet_mode_not_baudot(self, window):
        w = window
        w._link_table.mode_name = "VHF Packet"
        assert not w._modes.current_mode_name

        w._update_host_mode_ui(True)
        w._modes._send_init_frames()

        assert w._modes.current_mode_name == "VHF Packet"
        cmds = [c for c in w._serial.calls if c[0] == "cmd"]
        assert ("cmd", b'PA', b'') in cmds
        assert ("cmd", b'BA', b'') not in cmds

    def test_host_entry_queries_link_status_on_every_channel(self, window):
        w = window
        w._link_table.mode_name = "VHF Packet"

        w._update_host_mode_ui(True)

        ch_cmds = [c for c in w._serial.calls if c[0] == "ch_cmd" and c[2] == b'CO']
        assert sorted(c[1] for c in ch_cmds) == list(range(10))

    def test_co_confirmation_survives_the_delayed_mode_activation(self, window):
        """A real race: the CO answer confirming a carried-over channel
        can arrive on the SAME Host Mode entry BEFORE the 300ms mode-
        activation timer fires _send_init_frames() -> _on_mode_changed()
        -> _switch_opmode() -> screen.reset_channels() - which used to
        unconditionally wipe the chip back to free right after LinkTable
        had just confirmed it connected (found via direct repro, fixed
        by removing reset_channels()'s own channel_bar.reset() call -
        see PacketBaseScreen.reset_channels()'s docstring)."""
        w = window
        w._link_table.mode_name = "VHF Packet"
        w._update_host_mode_ui(True)
        w._on_mode_link_status(0x41, b"CO41000OE3GAS-1")
        screen = w._opmode_screens["VHF Packet"]
        assert screen.channel_bar.state(1) == "connected"

        w._modes._send_init_frames()   # fires the 300ms activation timer now

        assert screen.channel_bar.state(1) == "connected"
        assert screen.channel_bar.partner(1) == "OE3GAS-1"
        assert w._link_table.channels[1].state == "connected"

    def test_co_response_confirms_channel_and_reaches_the_chip(self, window):
        w = window
        w._link_table.mode_name = "VHF Packet"
        w._update_host_mode_ui(True)

        # ctl=0x41 -> channel 1 (P10's own
        # TestUiChannelZero::test_channel_zero_state_never_sticks
        # deliberately keeps chip 0 free no matter what set_channel_
        # state() is told, so a LinkTable-driven confirmation is
        # exercised on an ordinary QSO channel instead). Data shape
        # ("CO41000OE3GAS-1") is the real hardware answer from P67 M2.
        w._on_mode_link_status(0x41, b"CO41000OE3GAS-1")

        link1 = w._link_table.channels[1]
        assert link1.state == "connected"
        assert link1.partner == "OE3GAS-1"

        screen = w._opmode_screens["VHF Packet"]
        assert screen.channel_bar.state(1) == "connected"
        assert screen.channel_bar.partner(1) == "OE3GAS-1"

    def test_user_exit_does_not_reset_channels_chip_survives(self, window):
        w = window
        w._link_table.mode_name = "VHF Packet"
        w._update_host_mode_ui(True)
        w._modes._send_init_frames()
        w._on_mode_link_status(0x41, b"CO41000OE3GAS-1")
        screen = w._opmode_screens["VHF Packet"]
        assert screen.channel_bar.state(1) == "connected"

        w._on_host_mode_exit()
        w._update_host_mode_ui(False)

        # P67, Teil C.3: reset_channels() no longer runs on a user
        # exit - the chip must still show the carried-over connection.
        assert screen.channel_bar.state(1) == "connected"
        assert screen.channel_bar.partner(1) == "OE3GAS-1"

    def test_exit_with_connected_visible_channel_sends_co_via_exit_host_mode(self, window):
        w = window
        w._link_table.mode_name = "VHF Packet"
        w._update_host_mode_ui(True)
        w._modes._send_init_frames()
        w._on_mode_link_status(0x41, b"CO41000OE3GAS-1")
        screen = w._opmode_screens["VHF Packet"]
        screen.channel_bar.set_current(1)
        w._link_table.converse = True

        w._on_host_mode_exit()

        # exit_host_mode() itself is responsible for the actual write
        # ORDER (CO on io_channel before HOST OFF - see
        # test_serial_manager.py::TestExitHostModeIoChannel); this is
        # MainWindow's own responsibility - passing the right channel.
        assert ("exit_host_mode", 1) in w._serial.calls
        assert w._link_table.io_channel == 1
        # was_converse was True and the channel is connected -> CONVERSE
        # is sent to return to it.
        assert ("write_verbose", b"CONVERSE\r\n") in w._serial.calls

    def test_exit_with_free_channel_never_sends_converse(self, window):
        w = window
        w._link_table.mode_name = "VHF Packet"
        w._update_host_mode_ui(True)
        w._modes._send_init_frames()
        # No CO response arrives - channel 1 stays free.
        screen = w._opmode_screens["VHF Packet"]
        screen.channel_bar.set_current(1)
        w._link_table.converse = True

        w._on_host_mode_exit()

        assert ("exit_host_mode", None) in w._serial.calls
        assert not any(c[0] == "write_verbose" for c in w._serial.calls)

    def test_exit_without_prior_converse_never_sends_converse(self, window):
        w = window
        w._link_table.mode_name = "VHF Packet"
        w._update_host_mode_ui(True)
        w._modes._send_init_frames()
        w._on_mode_link_status(0x41, b"CO41000OE3GAS-1")
        screen = w._opmode_screens["VHF Packet"]
        screen.channel_bar.set_current(1)
        w._link_table.converse = False

        w._on_host_mode_exit()

        assert ("exit_host_mode", 1) in w._serial.calls
        assert not any(c[0] == "write_verbose" for c in w._serial.calls)


class TestMaildropGate:
    """P39: _maildrop_gate() is the ONE place all four blocking
    conditions are computed; both btn_maildrop (Packet screens) and the
    TNC -> MailDrop... menu action read it via _update_maildrop_gate_ui(),
    so they can never disagree. Supersedes the old P21.5-era
    TestMaildropButtonDisabled, which tested a button that unconditionally
    sent a (wrong) Host Mode frame - P39 replaced that with a real dialog
    that sends no frame of its own at all."""

    def test_all_conditions_met_is_open(self, wired_vhf):
        w, _screen = wired_vhf
        can_open, reason = w._maildrop_gate()
        assert can_open is True
        assert reason == ""

    def test_not_connected_blocks(self, wired_vhf):
        w, _screen = wired_vhf
        w._serial.is_connected = False
        can_open, reason = w._maildrop_gate()
        assert can_open is False
        assert reason == "connect to the TNC first"

    def test_not_host_mode_blocks(self, wired_vhf):
        w, _screen = wired_vhf
        w._serial.is_host_mode = False
        can_open, reason = w._maildrop_gate()
        assert can_open is False
        assert reason == "connect to the TNC first"

    def test_wrong_mode_blocks(self, wired_vhf):
        w, _screen = wired_vhf
        w._modes._active_mode = None
        can_open, reason = w._maildrop_gate()
        assert can_open is False
        assert reason == "switch to HF or VHF Packet first"

    def test_connected_channel_blocks_and_names_it(self, wired_vhf):
        w, screen = wired_vhf
        screen.channel_bar.set_channel_state(3, "connected", "OE3XYZ-9")
        can_open, reason = w._maildrop_gate()
        assert can_open is False
        assert reason == "disconnect channel 3 first"

    def test_calling_channel_also_blocks(self, wired_vhf):
        w, screen = wired_vhf
        screen.channel_bar.set_channel_state(5, "calling", "DL1ABC")
        can_open, reason = w._maildrop_gate()
        assert can_open is False
        assert reason == "disconnect channel 5 first"

    def test_has_maildrop_false_blocks(self, wired_vhf):
        w, _screen = wired_vhf
        w._serial.has_maildrop = False
        can_open, reason = w._maildrop_gate()
        assert can_open is False
        assert reason == "this firmware has no MailDrop"

    def test_has_maildrop_unknown_does_not_block(self, wired_vhf):
        # _StubSerial has no has_maildrop attribute at all - a detection
        # failure/unknown must not lock out the dialog (P37/P39: "assume
        # capable" is the rule for every has_maildrop consumer).
        w, _screen = wired_vhf
        assert not hasattr(w._serial, "has_maildrop")
        can_open, _reason = w._maildrop_gate()
        assert can_open is True

    def test_update_gate_ui_enables_button_and_menu(self, wired_vhf):
        w, screen = wired_vhf
        w._update_maildrop_gate_ui()
        assert screen.btn_maildrop.isEnabled()
        assert screen.btn_maildrop.toolTip() == ""
        assert w._act_maildrop.isEnabled()

    def test_update_gate_ui_disables_with_tooltip(self, wired_vhf):
        w, screen = wired_vhf
        screen.channel_bar.set_channel_state(5, "connected", "DL1ABC")
        w._update_maildrop_gate_ui()
        assert not screen.btn_maildrop.isEnabled()
        assert screen.btn_maildrop.toolTip() == "disconnect channel 5 first"
        assert not w._act_maildrop.isEnabled()
        assert w._act_maildrop.toolTip() == "disconnect channel 5 first"


class TestKeyboardFocusHandling:
    """P41: MainWindow.eventFilter() must not redirect keystrokes away
    from a focused input field just because it is a QComboBox
    (editable or not) rather than a QLineEdit - hardware-confirmed
    24.09.2026 (typing into the VHF Packet screen's Dest field landed
    in the TX window instead). The Dest field itself was an editable
    QComboBox (cb_dest) at the time of that finding; P42 removed it
    entirely in favour of a callsign typed directly into a channel chip's
    own inline QLineEdit editor (ChannelChip.editor) - the test below now
    exercises that editor instead, still covering the exact same
    QLineEdit-type-field regression the P41 fix was for. Reproduces the
    bug through the REAL
    app-wide event filter (MainWindow.eventFilter, installed on
    QApplication itself) with QTest.keyClick(), not by calling any
    screen's own eventFilter() directly - that is not the code path a
    real keystroke actually takes for these fields (see the
    is_keyboard_input_widget() docstring in screen_focus_controller.py
    for why).

    QTest.keyClick(TARGET, ...) is always given the specific widget to
    click, never QApplication.focusWidget() - a whole pytest session
    creates many MainWindow instances across many test files without
    ever closing one (a pre-existing pattern in this fixture, not
    introduced here), so QApplication-wide "current focus widget"
    tracking is not reliable enough to use as the click TARGET once
    other tests have run first; it is only used, via setFocus() below,
    to put the app-wide event filter into the real state a genuine
    keystroke would find it in (self.focusWidget() inside eventFilter()
    is one of two conditions checked - the other, obj itself, is exactly
    what QTest.keyClick()'s target becomes).
    """

    def _settle(self, w):
        w.show()
        w.activateWindow()
        QTest.qWaitForWindowActive(w)
        _app.processEvents()

    def test_chip_editor_keeps_typed_text_out_of_tx_window(self, wired_vhf):
        w, screen = wired_vhf
        self._settle(w)
        screen.tx_input.clear()
        screen.channel_bar.start_edit_current()   # opens the current chip's editor
        field = screen.channel_bar._chips[screen.channel_bar.current()].editor
        field.clear()
        field.setFocus()
        _app.processEvents()

        QTest.keyClick(field, Qt.Key.Key_O)
        _app.processEvents()

        assert field.text() == "o"
        assert screen.tx_input.toPlainText() == ""

    def test_via_field_still_works(self, wired_vhf):
        # The "via" field (le_unproto) is a plain QLineEdit and already
        # worked before P41 - the control/negative test from the spec.
        w, screen = wired_vhf
        self._settle(w)
        screen.tx_input.clear()
        screen.le_unproto.clear()
        screen.le_unproto.setFocus()
        _app.processEvents()

        QTest.keyClick(screen.le_unproto, Qt.Key.Key_C)
        _app.processEvents()

        assert screen.le_unproto.text() == "c"
        assert screen.tx_input.toPlainText() == ""

    def test_button_focus_still_redirects_to_tx_window(self, wired_vhf):
        # Existing behaviour must not regress: a NoFocus button never
        # actually keeps keyboard focus, but simulate the channel bar/
        # button case by focusing a button-like widget directly and
        # confirm a keystroke still lands in tx_input.
        w, screen = wired_vhf
        self._settle(w)
        screen.tx_input.clear()
        screen.btn_unproto.setFocus()
        _app.processEvents()

        QTest.keyClick(screen.btn_unproto, Qt.Key.Key_Z)
        _app.processEvents()

        assert screen.tx_input.toPlainText() == "z"

    def test_monitor_combo_changes_value_without_leaking_into_tx_window(
        self, wired_vhf,
    ):
        w, screen = wired_vhf
        self._settle(w)
        assert screen.combo_monitor.currentText() == screen.MONITOR_DEFAULT
        screen.tx_input.clear()
        screen.combo_monitor.setFocus()
        _app.processEvents()

        # A digit other than the default proves the combo actually
        # reacted, not merely that it stayed unchanged.
        QTest.keyClick(screen.combo_monitor, Qt.Key.Key_2)
        _app.processEvents()

        assert screen.combo_monitor.currentText() == "2"
        assert screen.tx_input.toPlainText() == ""

    def test_hbaud_combo_changes_value_without_leaking_into_tx_window(
        self, wired_vhf,
    ):
        w, screen = wired_vhf
        self._settle(w)
        assert screen.combo_hbaud.currentText() == screen.HBAUD_DEFAULT
        screen.tx_input.clear()
        screen.combo_hbaud.setFocus()
        _app.processEvents()

        # Qt's non-editable QComboBox type-ahead jumps to the item
        # starting with the typed character - "9" -> "9600".
        QTest.keyClick(screen.combo_hbaud, Qt.Key.Key_9)
        _app.processEvents()

        assert screen.combo_hbaud.currentText() == "9600"
        assert screen.tx_input.toPlainText() == ""

    def test_ctrl_up_in_open_chip_editor_does_not_step_channel(self, wired_vhf):
        w, screen = wired_vhf
        self._settle(w)
        screen.channel_bar.set_current(2)
        screen.channel_bar.start_edit_current()
        field = screen.channel_bar._chips[2].editor
        field.setFocus()
        _app.processEvents()

        QTest.keyClick(
            field, Qt.Key.Key_Up, Qt.KeyboardModifier.ControlModifier,
        )
        _app.processEvents()

        assert screen.channel_bar.current() == 2


class TestArchiveRestoreTrigger:
    """P59, D - _check_archive_restore_trigger() (wired to
    host_mode_changed(True)/recovery_finished(True, ...)) flags a
    pending automatic MailDrop archive restore; _update_maildrop_gate_ui()
    (D.2) fires it exactly once the gate is actually open.
    _offer_archive_restore() itself is stubbed here — its real behaviour
    (candidate counting, the ask/auto question, opening the dialog in
    auto_restore mode) is exercised by test_maildrop_dialog.py's
    TestAutoRestore instead, against a fake session."""

    @staticmethod
    def _armed(w, restore="ask", scope="all"):
        w._serial.fresh_boot_defaults = True
        w._serial.has_maildrop = None
        w._app_config.maildrop.archive_enabled = True
        w._app_config.maildrop.archive_restore = restore
        w._app_config.maildrop.archive_restore_scope = scope

    def test_gate_open_offers_exactly_once(self, wired_vhf):
        w, _screen = wired_vhf
        self._armed(w)
        calls = []
        w._offer_archive_restore = lambda: calls.append(1)

        w._check_archive_restore_trigger()
        assert w._archive_restore_pending is True

        w._update_maildrop_gate_ui()   # gate is already open (wired_vhf)
        _app.processEvents()
        assert calls == [1]
        assert w._archive_restore_pending is False

        # A later, unrelated gate update must not offer a second time.
        w._update_maildrop_gate_ui()
        _app.processEvents()
        assert calls == [1]

    def test_gate_closed_hints_once_then_offers_after_switching_to_packet(
        self, wired_vhf,
    ):
        w, _screen = wired_vhf
        self._armed(w)
        w._modes._active_mode = None   # not a Packet mode - gate closed
        calls = []
        w._offer_archive_restore = lambda: calls.append(1)
        before = len(w._monitor.toPlainText())

        w._check_archive_restore_trigger()
        assert w._archive_restore_pending is True
        hint = w._monitor.toPlainText()[before:]
        assert hint.count("switch to HF/VHF Packet") == 1
        assert calls == []

        # A second gate update while still closed must not repeat the hint.
        w._update_maildrop_gate_ui()
        _app.processEvents()
        assert w._monitor.toPlainText()[before:].count(
            "switch to HF/VHF Packet"
        ) == 1
        assert calls == []

        w._modes._active_mode = VHFPacketMode()
        w._update_maildrop_gate_ui()
        _app.processEvents()
        assert calls == [1]

    def test_never_does_not_arm(self, wired_vhf):
        w, _screen = wired_vhf
        self._armed(w, restore="never")
        w._check_archive_restore_trigger()
        assert w._archive_restore_pending is False

    def test_scope_none_does_not_arm(self, wired_vhf):
        w, _screen = wired_vhf
        self._armed(w, scope="none")
        w._check_archive_restore_trigger()
        assert w._archive_restore_pending is False

    def test_has_maildrop_false_does_not_arm(self, wired_vhf):
        w, _screen = wired_vhf
        self._armed(w)
        w._serial.has_maildrop = False
        w._check_archive_restore_trigger()
        assert w._archive_restore_pending is False

    def test_archive_disabled_does_not_arm(self, wired_vhf):
        w, _screen = wired_vhf
        self._armed(w)
        w._app_config.maildrop.archive_enabled = False
        w._check_archive_restore_trigger()
        assert w._archive_restore_pending is False

    def test_disconnect_clears_the_pending_flag(self, wired_vhf):
        w, _screen = wired_vhf
        self._armed(w)
        w._check_archive_restore_trigger()
        assert w._archive_restore_pending is True

        w._update_connection_ui(False)
        assert w._archive_restore_pending is False

    def test_second_host_mode_changed_in_same_power_cycle_does_not_rearm(
        self, wired_vhf,
    ):
        """P60, B.1 regression - leaving a MailDrop session, or "Enter
        Host Mode" from the TNC menu, re-fires host_mode_changed(True)
        via SerialManager._enter_host_mode_thread() without ever running
        _init_tnc_thread() again. Before P60 this re-armed the trigger
        every time, because _check_archive_restore_trigger() re-read the
        live fresh_boot_defaults property (never consumed) instead of a
        one-shot event - the exact endless MailDrop-session loop
        docs/P60_Archive_Restore_Oneshot_Fix_Spec.md B.1 describes."""
        w, _screen = wired_vhf
        self._armed(w)
        calls = []
        w._offer_archive_restore = lambda: calls.append(1)

        w._check_archive_restore_trigger()
        assert w._archive_restore_pending is True
        w._update_maildrop_gate_ui()
        _app.processEvents()
        assert calls == [1]
        assert w._archive_restore_pending is False

        # Simulates leaving a MailDrop session (or "Enter Host Mode" from
        # the menu): host_mode_changed(True) fires again with NO new
        # init/recovery run in between, so the physical banner was never
        # re-read.
        w._check_archive_restore_trigger()
        assert w._archive_restore_pending is False
        w._update_maildrop_gate_ui()
        _app.processEvents()
        assert calls == [1]   # still exactly one offer for this power cycle

    def test_auto_restore_dialog_opens_exactly_once_even_if_its_own_exec_refires_host_mode_changed(
        self, wired_vhf, monkeypatch,
    ):
        """Same regression as above, but against the REAL
        _offer_archive_restore() and a fake MailDropDialog whose exec()
        does what the real dialog's auto-restore does on the device -
        ends the session, which re-enters Host Mode and re-fires
        host_mode_changed(True) with no new init in between (P60,
        B.1)."""
        w, _screen = wired_vhf
        self._armed(w, restore="auto")

        class _FakeArchivedMessage:
            def __init__(self):
                self.read_flag = False

        class _FakeArchive:
            def all(self):
                return [_FakeArchivedMessage()]

            def close(self):
                pass

        monkeypatch.setattr(
            "pk232py.maildrop.open_archive", lambda cfg: _FakeArchive(),
        )

        dialogs = []

        class _FakeAutoDialog:
            def __init__(self, *a, **kw):
                dialogs.append(self)
                self.last_have_mail = None

            def exec(self):
                # What leaving a real auto-restore session does on the
                # device: enter_host_mode() -> host_mode_changed(True),
                # never through _init_tnc_thread().
                w._check_archive_restore_trigger()

        monkeypatch.setattr(
            "pk232py.ui.dialogs.maildrop_dialog.MailDropDialog",
            _FakeAutoDialog,
        )

        w._check_archive_restore_trigger()
        assert w._archive_restore_pending is True
        w._update_maildrop_gate_ui()
        # Drain the event queue fully, not just once - a still-buggy
        # trigger re-arms _archive_restore_pending from INSIDE the first
        # dialog's exec(), which only schedules its own follow-up offer
        # via QTimer.singleShot(0, ...) once _offer_archive_restore()
        # itself gets back to _update_maildrop_gate_ui() - that follow-up
        # event needs a LATER processEvents() call to fire, so a single
        # call here would pass even against the unfixed code.
        for _ in range(10):
            _app.processEvents()

        assert len(dialogs) == 1

    def test_never_then_switched_to_ask_does_not_retroactively_arm(
        self, wired_vhf,
    ):
        """P60, A.2 - the event must be consumed the FIRST time
        _check_archive_restore_trigger() runs, even if 'never' means no
        restore is armed that time - otherwise switching the setting to
        'ask'/'auto' later in the same power cycle would arm a restore
        for a power-on that has already been and gone."""
        w, _screen = wired_vhf
        self._armed(w, restore="never")
        calls = []
        w._offer_archive_restore = lambda: calls.append(1)

        w._check_archive_restore_trigger()
        assert w._archive_restore_pending is False

        w._app_config.maildrop.archive_restore = "ask"
        w._check_archive_restore_trigger()
        assert w._archive_restore_pending is False
        w._update_maildrop_gate_ui()
        _app.processEvents()
        assert calls == []


class TestChannelZeroAndUnprotoChannelChoice:
    """P70 B/D/E: channel 0 is an ordinary TNC channel; Unproto goes out
    on the lowest free channel per the LinkTable; a rejected incoming
    call is reported, never turned into a chip state."""

    @staticmethod
    def _data_calls(w):
        return [c for c in w._serial.calls if c[0] == "data"]

    @staticmethod
    def _connect_all(w, upto: int):
        for ch in range(upto):
            w._link_table.on_host_link_message(ch, f"CONNECTED to OE3GAS-{ch}")

    def test_incoming_connection_on_channel_zero_shows_in_chip_zero(self, wired_vhf):
        w, screen = wired_vhf
        mode = w._modes.current_mode

        mode.handle_frame(_FakeLinkMsgFrame(0, "CONNECTED to OE3GAS-2"))

        assert screen.channel_bar.state(0) == "connected"
        assert screen.channel_bar.partner(0) == "OE3GAS-2"
        assert w._link_table.channels[0].state == "connected"

    def test_unproto_with_channel_zero_connected_goes_out_on_channel_one(self, wired_vhf):
        w, screen = wired_vhf
        self._connect_all(w, 1)
        screen.channel_bar.set_current(MON_VIEW)
        screen.set_view_all(False)
        screen.tx_input.setPlainText("CQ CQ de OE3GAS")

        w._on_packet_tx_enter()

        assert self._data_calls(w) == [("data", 1, b"CQ CQ de OE3GAS\r")]
        assert "[via ch1]" in screen.rx_display.toPlainText()
        assert screen.tx_input.toPlainText() == ""

    def test_unproto_with_nothing_connected_uses_channel_zero(self, wired_vhf):
        w, screen = wired_vhf
        screen.channel_bar.set_current(MON_VIEW)
        screen.tx_input.setPlainText("hello")

        w._on_packet_tx_enter()

        assert self._data_calls(w) == [("data", 0, b"hello\r")]

    def test_unproto_with_all_ten_connected_sends_nothing_and_keeps_text(self, wired_vhf):
        w, screen = wired_vhf
        self._connect_all(w, 10)
        screen.channel_bar.set_current(MON_VIEW)
        screen.set_view_all(False)
        screen.tx_input.setPlainText("hello")

        w._on_packet_tx_enter()

        assert self._data_calls(w) == []
        assert screen.tx_input.toPlainText() == "hello"
        assert "all 10 channels are connected - no free channel for unproto" in (
            screen.rx_display.toPlainText())

    def test_unproto_path_frame_goes_out_before_the_first_mon_frame(self, wired_vhf):
        w, screen = wired_vhf
        screen.le_unproto.setText("CQ VIA RELAY")
        screen.channel_bar.set_current(MON_VIEW)
        screen.tx_input.setPlainText("hello")

        w._on_packet_tx_enter()

        kinds = [c[0] for c in w._serial.calls]
        assert kinds.index("cmd") < kinds.index("data")

    def test_rejected_call_is_reported_in_mon_and_status_bar_only(self, wired_vhf):
        w, screen = wired_vhf
        mode = w._modes.current_mode
        w._app_config.hf_packet.users = 1
        screen.set_view_all(False)
        screen.channel_bar.set_current(MON_VIEW)
        before = [screen.channel_bar.state(ch) for ch in range(10)]

        mode.handle_frame(_FakeLinkMsgFrame(1, "Connect request: OE3GAS-3"))

        msg = "Incoming call from OE3GAS-3 rejected by the TNC (USERS 1)"
        assert msg in screen.rx_display.toPlainText()
        assert msg in w.statusBar().currentMessage()
        assert [screen.channel_bar.state(ch) for ch in range(10)] == before

    def test_other_link_messages_do_not_trigger_the_rejected_notice(self, wired_vhf):
        w, screen = wired_vhf
        mode = w._modes.current_mode
        screen.set_view_all(False)
        screen.channel_bar.set_current(MON_VIEW)

        mode.handle_frame(_FakeLinkMsgFrame(1, "CONNECTED to OE3GAS-3"))

        assert "rejected by the TNC" not in screen.rx_display.toPlainText()

    def test_activation_repaints_from_the_link_table_without_reset(self, wired_vhf, monkeypatch):
        w, screen = wired_vhf
        w._link_table.on_host_link_message(0, "CONNECTED to OE3GAS-2")
        monkeypatch.setattr(
            screen, "reset_channels",
            lambda: pytest.fail("reset_channels() must not run on activation"),
        )
        # Chip drifted away from the table (e.g. a stale widget state).
        screen.channel_bar.set_channel_state(0, "free", "")
        assert screen.channel_bar.state(0) == "free"

        w._switch_opmode("VHF Packet")

        assert screen.channel_bar.state(0) == "connected"
        assert screen.channel_bar.partner(0) == "OE3GAS-2"

    def test_co_state_4_shows_disconnecting_on_the_chip(self, wired_vhf):
        w, screen = wired_vhf
        w._link_table.on_host_link_message(0, "CONNECTED to OE3GAS-2")

        w._on_mode_link_status(0x40, b"CO31000OE3GAS-2")

        assert screen.channel_bar.state(0) == "disconnecting"
