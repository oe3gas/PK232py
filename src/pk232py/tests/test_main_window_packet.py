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
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
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
    yield w, screen
    # Teardown (P41): MainWindow.__init__() installs itself as an
    # app-wide event filter (QApplication.instance().installEventFilter(
    # self)) - every filter installed on the QApplication singleton stays
    # active until explicitly removed, regardless of whether the Python
    # object that owns it is later garbage-collected. Without this,
    # every test using this fixture leaves one more stale MainWindow
    # answering EVERY keypress event for the rest of the pytest session;
    # by the time enough of them pile up, one of their eventFilter()
    # calls can throw against its own now-stale state (e.g. a screen a
    # later test switched away from), which pytest-qt's exception
    # capturing surfaces as a failure in a LATER, unrelated test -
    # exactly what made TestKeyboardFocusHandling flaky depending on how
    # many earlier tests in the full suite had already used this fixture.
    QApplication.instance().removeEventFilter(w)
    # closeEvent() asks "TNC is still connected. Exit anyway?" via
    # QMessageBox.question() whenever _serial.is_connected is True -
    # _StubSerial.is_connected is a class attribute hardcoded to True (the
    # test bodies need that to exercise the "connected" TNC commands), so
    # w.close() would otherwise pop a real modal dialog that never gets a
    # button click under the offscreen QPA platform - the whole pytest
    # process hangs forever. Flip it to False for the teardown-only close;
    # by now the test body is done with it.
    w._serial.is_connected = False
    w.close()
    # deleteLater() + processEvents(), not just close()/hide(): several
    # TestKeyboardFocusHandling tests call show()/activateWindow() on a
    # FRESH MainWindow (needed so QTest.keyClick() exercises the real
    # app-wide event filter under realistic focus/activation state, see
    # that class's docstring). A merely closed-but-not-destroyed MainWindow
    # leaves its top-level QWidget (and its running QTimers, e.g. the
    # Packet screen's UTC clock) alive under the offscreen QPA platform;
    # once enough of them pile up across the full test run,
    # qWaitForWindowActive() on a later test's fresh window hangs forever
    # instead of returning quickly - reproduced 25.09.2026 running this
    # file's full suite (test 25 of 28 hung; passed in isolation).
    w.deleteLater()
    QApplication.instance().processEvents()


class TestUnprotoUsesChannelZero:
    """T98.

    P42 note: Connect/Disconnect no longer have buttons of their own, so
    the old "locks buttons" assertion here is now covered instead by
    TestConnectRejectedOnChannelZero (the UI channel's chip refuses to
    open its inline connect editor at all). This class keeps the parts of
    T98 that are still meaningful: the channel-0 switch itself and
    Unproto's own enable/disable state.
    """

    def test_unproto_on_switches_to_channel_zero(self, wired_vhf):
        w, screen = wired_vhf
        screen.channel_bar.set_current(3)
        screen.tx_input.setPlainText("draft on ch3")

        screen.btn_unproto.setChecked(True)

        assert screen.current_channel() == 0

    def test_unproto_off_does_not_auto_jump_channel(self, wired_vhf):
        w, screen = wired_vhf
        screen.channel_bar.set_current(3)
        screen.btn_unproto.setChecked(True)
        assert screen.current_channel() == 0

        screen.btn_unproto.setChecked(False)
        assert screen.current_channel() == 0   # operator must pick a chip

    def test_selecting_qso_channel_turns_unproto_off(self, wired_vhf):
        w, screen = wired_vhf
        screen.channel_bar.set_current(3)
        screen.tx_input.setPlainText("draft on ch3")
        screen.btn_unproto.setChecked(True)
        assert screen.current_channel() == 0

        screen.channel_bar.set_current(3)

        assert not screen.btn_unproto.isChecked()
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
    """T99 - channel 0 (UI channel) can never hold a connection.

    Under the old Connect/Dest row this was enforced in MainWindow (a
    warning dialog + un-checking btn_connect). P42 moved the guard to the
    source instead: ChannelChip.start_edit() refuses to open its inline
    editor at all for channel 0, so connect_requested can never even be
    emitted for it - MainWindow's _on_chip_connect_requested() is never
    reached, and no serial frame is ever built.
    """

    def test_channel_zero_chip_refuses_to_open_its_editor(self, wired_vhf):
        w, screen = wired_vhf
        screen.channel_bar.set_current(0)

        screen.channel_bar.start_edit_current()

        assert not screen.channel_bar.is_editing()
        assert w._serial.calls == []
        assert screen.channel_bar.state(0) == "free"

    def test_channel_zero_never_emits_connect_requested(self, wired_vhf):
        w, screen = wired_vhf
        received: list[tuple[int, str]] = []
        screen.channel_bar.connect_requested.connect(
            lambda ch, call: received.append((ch, call))
        )

        screen.channel_bar.start_edit(0, "OE1XYZ")

        assert not screen.channel_bar.is_editing()
        assert received == []
        assert w._serial.calls == []


class TestLinkMessageGatedByVisibleChannel:
    """T102 — a link message for a channel other than the visible one must
    not touch Unproto's enabled state (P42: Connect/Disconnect no longer
    have buttons to gate — set_link_state() only owns Unproto now, see its
    docstring); ChannelBar itself still updates (it is a separate,
    always-on, per-channel consumer of the same message)."""

    def test_message_for_other_channel_does_not_change_unproto(self, wired_vhf):
        w, screen = wired_vhf
        mode = w._modes.current_mode

        # Channel 4 connects while it is the visible channel.
        screen.channel_bar.set_current(4)
        mode.handle_frame(_FakeLinkMsgFrame(4, "CONNECTED to OE1XYZ"))
        assert not screen.btn_unproto.isEnabled()

        # Switch away to the UI channel — Unproto re-enables (channel 0
        # can never itself be busy).
        screen.channel_bar.set_current(0)
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
        assert not screen.btn_unproto.isEnabled()


class TestLinkMessageAppearsInItsOwnChannel:
    """P47 — a $5x link message must appear in the channel it actually
    happened on, never wherever the operator's screen happens to be
    pointed. Reproduced 25.09.2026 (screenshot): a channel-1 "Retry count
    exceeded ... DISCONNECTED: OE3XTC" appeared on the UI chip (channel 0)
    because that was the visible channel at the time the message arrived.
    Never attributed by callsign — "Retry count exceeded" carries none."""

    def test_message_for_channel_1_appears_while_viewing_channel_1(self, wired_vhf):
        w, screen = wired_vhf
        mode = w._modes.current_mode
        screen.channel_bar.set_current(1)

        mode.handle_frame(_FakeLinkMsgFrame(1, "DISCONNECTED: OE3XTC"))

        assert "*** DISCONNECTED: OE3XTC ***" in screen.rx_display.toPlainText()

    def test_same_message_does_not_appear_on_ui_channel_in_ch_view(self, wired_vhf):
        w, screen = wired_vhf
        mode = w._modes.current_mode
        screen.channel_bar.set_current(0)
        screen.set_view_all(False)

        mode.handle_frame(_FakeLinkMsgFrame(1, "DISCONNECTED: OE3XTC"))

        assert "OE3XTC" not in screen.rx_display.toPlainText()

    def test_all_view_shows_the_message_with_its_channel_tag(self, wired_vhf):
        w, screen = wired_vhf
        mode = w._modes.current_mode
        screen.channel_bar.set_current(0)
        screen.set_view_all(True)

        mode.handle_frame(_FakeLinkMsgFrame(1, "DISCONNECTED: OE3XTC"))

        text = screen.rx_display.toPlainText()
        assert "[CH1]" in text
        assert "*** DISCONNECTED: OE3XTC ***" in text

    def test_channel_15_always_appears_in_the_ui_channel(self, wired_vhf):
        # $5F is not channel-scoped at all (e.g. the generic data ack) -
        # there is nowhere else for it to belong, regardless of the
        # mirror setting (off by default here).
        w, screen = wired_vhf
        mode = w._modes.current_mode
        screen.channel_bar.set_current(0)
        screen.set_view_all(False)
        assert w._app_config.hf_packet.show_link_messages_in_ui_channel is False

        mode.on_link_message(15, "some generic status")

        assert "some generic status" in screen.rx_display.toPlainText()

    def test_mirror_setting_off_by_default_does_not_leak_into_ui_channel(self, wired_vhf):
        w, screen = wired_vhf
        mode = w._modes.current_mode
        screen.channel_bar.set_current(0)
        screen.set_view_all(False)

        mode.handle_frame(_FakeLinkMsgFrame(1, "DISCONNECTED: OE3XTC"))

        assert "OE3XTC" not in screen.rx_display.toPlainText()

    def test_mirror_setting_on_duplicates_into_the_ui_channel_with_a_tag(self, wired_vhf):
        w, screen = wired_vhf
        mode = w._modes.current_mode
        w._app_config.hf_packet.show_link_messages_in_ui_channel = True
        screen.channel_bar.set_current(0)
        screen.set_view_all(False)

        mode.handle_frame(_FakeLinkMsgFrame(1, "DISCONNECTED: OE3XTC"))

        assert "[ch1] *** DISCONNECTED: OE3XTC ***" in screen.rx_display.toPlainText()

    def test_mirror_setting_does_not_duplicate_a_ui_channel_message(self, wired_vhf):
        # channel == UI_CHANNEL already means "this IS the UI channel" -
        # mirroring it into itself would just double it.
        w, screen = wired_vhf
        mode = w._modes.current_mode
        w._app_config.hf_packet.show_link_messages_in_ui_channel = True
        screen.channel_bar.set_current(0)
        screen.set_view_all(False)

        mode.on_link_message(15, "some generic status")

        text = screen.rx_display.toPlainText()
        assert text.count("some generic status") == 1

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
        screen.channel_bar.set_current(0)

        mode.handle_frame(_FakeLinkMsgFrame(1, "DISCONNECTED: OE1XYZ"))

        assert "DISCONNECTED" in screen.lbl_status.text()


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
