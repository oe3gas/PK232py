# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Unit tests for MainWindow's connection-state honesty and Recovery
feedback (P45/P46).

Covers:
  - P45.1 — _on_recovery() locks the button immediately;
    _on_recovery_finished() reports success/failure visibly (status bar,
    verbose terminal, and a dialog on failure) and always re-enables the
    button afterwards.
  - P45.2 — a failed init (SerialManager.init_failed) must not leave the
    app looking connected: the mode indicator goes to "error", the mode
    combo and "Enter Host Mode" toolbar button are disabled, but Connect
    and Recovery both stay enabled (the operator's way out). Also:
    _update_connection_ui(True) sets "connecting", never "verbose"
    outright - only a confirmed verbose_mode_ready may do that.
  - P46.B — Recovery ("Emergency Reconnect") is never gated on
    is_connected, not even in _update_connection_ui() - it is the one
    action that must work from ANY state, including no connection at
    all. MainWindow passes the saved AppConfig.tnc port/baud through so
    SerialManager.recovery() can open the port itself when needed.

Needs a QApplication; forced to the offscreen platform (see
test_packet_screen.py for why this is done at module level, before any
PyQt6 import).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

from pk232py.ui.main_window import MainWindow

_app = QApplication.instance() or QApplication([])


class _StubSerial:
    """Minimal stand-in - only what the methods under test touch.

    write_verbose_wait()/has_pactor/detect_maildrop are only here so that
    _on_verbose_mode_ready()'s background parameter-upload thread (started
    as a side effect of some tests below) has something harmless to call
    instead of raising AttributeError in a daemon thread pytest then
    reports as an unhandled-thread-exception warning.
    """

    is_connected = True
    is_host_mode = False
    has_pactor = True
    fresh_boot_defaults = False

    def __init__(self):
        self.writes: list[bytes] = []
        self.recovery_called = False

    def recovery(self, port_name=None, baudrate=None) -> bool:
        self.recovery_called = True
        self.recovery_args = (port_name, baudrate)
        return True

    def consume_fresh_boot_defaults(self) -> bool:
        """P60, A.1 - _on_recovery_finished(True, ...) calls
        MainWindow._check_archive_restore_trigger(), which now consumes
        this event unconditionally on every call."""
        fresh = self.fresh_boot_defaults
        self.fresh_boot_defaults = False
        return fresh

    def write_verbose_wait(self, *args, **kwargs) -> bool:
        return True

    def detect_maildrop(self) -> bool:
        return True


@pytest.fixture
def wired_window(monkeypatch):
    # A real QMessageBox.warning()/critical() would block forever under
    # the offscreen platform with nothing to click it - stub it out for
    # every test in this file, same as test_main_window_packet.py does
    # for its own dialog-triggering paths.
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))

    w = MainWindow()
    w._serial = _StubSerial()
    yield w, w._serial
    # Teardown mirrors test_main_window_packet.py's wired_vhf fixture
    # (P41/P42): remove the app-wide event filter, and flip is_connected
    # to False before close() - closeEvent() otherwise pops a real
    # QMessageBox.question() that nothing can click under the offscreen
    # QPA platform, hanging the whole pytest process.
    QApplication.instance().removeEventFilter(w)
    w._serial.is_connected = False
    w.close()
    w.deleteLater()
    QApplication.instance().processEvents()


class TestConnectingIndicatorNotVerbose:
    """P45.2 - a freshly opened port is "connecting", never "verbose"
    outright - only a confirmed verbose_mode_ready may claim that."""

    def test_update_connection_ui_true_sets_connecting_not_verbose(self, wired_window):
        w, _serial = wired_window

        w._update_connection_ui(True)

        assert w._mode_indicator.text().strip() == "CONNECTING..."

    def test_verbose_mode_ready_upgrades_to_verbose(self, wired_window):
        w, serial = wired_window
        w._update_connection_ui(True)
        assert w._mode_indicator.text().strip() == "CONNECTING..."

        w._on_verbose_mode_ready()

        assert w._mode_indicator.text().strip() == "VERBOSE MODE"


class TestInitFailedDoesNotLookConnected:
    """P45.2 - reproduced 25.09.2026: a failed init left the Host Mode
    button enabled/green-looking and the firmware label "unknown" with no
    other indication anything had gone wrong. init_failed() must reset
    the UI state without needing the port to actually close (Recovery
    needs it to stay open)."""

    def test_mode_indicator_goes_to_error(self, wired_window):
        w, _serial = wired_window
        w._update_connection_ui(True)

        w._on_init_failed()

        assert w._mode_indicator.text().strip() == "ERROR"

    def test_mode_combo_is_disabled(self, wired_window):
        w, _serial = wired_window
        w._update_connection_ui(True)

        w._on_init_failed()

        assert not w._mode_combo.isEnabled()

    def test_connect_actions_stay_enabled(self, wired_window):
        w, _serial = wired_window
        w._update_connection_ui(True)

        w._on_init_failed()

        assert w._act_connect_verbose.isEnabled()
        assert w._act_connect_host.isEnabled()

    def test_recovery_stays_enabled(self, wired_window):
        w, _serial = wired_window
        w._update_connection_ui(True)

        w._on_init_failed()

        assert w._act_recovery.isEnabled()

    def test_connect_again_retries_on_the_still_open_port(self, wired_window):
        # P45.2 - connect_port()'s own "already open" guard used to make
        # a second Connect press silently do nothing at all once the
        # first attempt's port stayed open. _on_connect_verbose()/
        # _on_connect_host() must notice is_connected is already True and
        # retry init_tnc() directly instead of going through the dialog.
        w, serial = wired_window
        w._update_connection_ui(True)
        w._on_init_failed()
        calls = []
        serial.init_tnc = lambda: calls.append(True)

        w._on_connect_verbose()

        assert calls == [True]


class TestRecoveryFeedback:
    """P45.1 - Recovery used to give no visible reaction at all; now it
    locks the button immediately and always reports an outcome."""

    def test_on_recovery_locks_the_button_immediately(self, wired_window):
        w, serial = wired_window

        w._on_recovery()

        assert serial.recovery_called is True
        assert not w._act_recovery.isEnabled()
        assert "running" in w._act_recovery.text().lower()

    def test_on_recovery_works_even_when_not_connected(self, wired_window):
        # P46.B - Recovery is the emergency reconnect: it is the way out
        # of ANY state, so unlike every other TNC action it must never be
        # gated on is_connected. SerialManager.recovery() itself is the
        # one that opens the port (from the saved config) when needed.
        w, serial = wired_window
        serial.is_connected = False

        w._on_recovery()

        assert serial.recovery_called is True

    def test_on_recovery_passes_the_saved_port_and_baudrate(self, wired_window):
        # P46.B - "Port und Baudrate aus der Konfiguration": MainWindow is
        # the one holding AppConfig, so it passes the saved TNC port/baud
        # through to SerialManager.recovery(), which is the one that opens
        # the port if it is not already open.
        w, serial = wired_window
        w._app_config.tnc.port  = "COM7"
        w._app_config.tnc.tbaud = 9600

        w._on_recovery()

        assert serial.recovery_args == ("COM7", 9600)

    def test_recovery_finished_success_reenables_and_shows_message(self, wired_window):
        w, _serial = wired_window
        w._on_recovery()  # lock it first, as the real flow would

        w._on_recovery_finished(True, "Recovery successful - test")

        assert w._act_recovery.isEnabled()
        assert "Reconnect" in w._act_recovery.text()
        assert "Recovery successful - test" in w._vt_display.toPlainText()

    def test_recovery_finished_failure_reenables_and_shows_message(self, wired_window):
        w, _serial = wired_window
        w._on_recovery()

        w._on_recovery_finished(False, "Recovery did not reach the TNC.")

        assert w._act_recovery.isEnabled()
        assert "Recovery did not reach the TNC." in w._vt_display.toPlainText()


class TestMenuOnlyTncActions:
    """P46.C - Connect/Disconnect/Host Mode/Recovery live in the TNC menu
    only; the toolbar keeps just the mode selector, firmware label and
    mode indicator. "Connect" used to be ambiguous (TNC serial connection
    here vs. AX.25/PACTOR/AMTOR station connection on the opmode screens)
    - removing it from the toolbar removes that collision from view."""

    def test_toolbar_has_no_tnc_action_buttons(self, wired_window):
        from PyQt6.QtWidgets import QToolBar

        w, _serial = wired_window
        toolbars = w.findChildren(QToolBar)
        assert toolbars, "expected at least one toolbar"
        banned = {"connect", "disconnect", "host mode", "recovery"}
        for tb in toolbars:
            for act in tb.actions():
                text = act.text().strip().lower()
                assert text not in banned, f"toolbar still has a {text!r} action"

    def test_tnc_menu_has_the_emergency_reconnect_entry(self, wired_window):
        w, _serial = wired_window
        assert w._act_recovery.shortcut().toString() == "Ctrl+R"
        assert "Emergency" in w._act_recovery.text()
        assert "Reconnect" in w._act_recovery.text()

    def test_tnc_menu_shortcuts_are_all_distinct(self, wired_window):
        w, _serial = wired_window
        tnc_actions = [
            w._act_connect_verbose, w._act_connect_host,
            w._act_enter_host_mode, w._act_host_off,
            w._act_disconnect, w._act_recovery,
        ]
        shortcuts = [a.shortcut().toString() for a in tnc_actions if a.shortcut().toString()]
        assert len(shortcuts) == len(set(shortcuts)), (
            f"duplicate shortcut among TNC menu actions: {shortcuts}"
        )

    def test_tnc_menu_disconnect_shortcut_does_not_collide_with_packet_channel_disconnect(
        self, wired_window
    ):
        # P46.C.2 - the TNC menu's Ctrl+D ("Disconnect + Close Serial
        # Port") must not be the same key as the Packet screen's own
        # channel-disconnect shortcut (moved to Ctrl+K - see
        # packet_screen.py's eventFilter()).
        w, _serial = wired_window
        assert w._act_disconnect.shortcut().toString() == "Ctrl+D"


class TestTncMenuGating:
    """P49.A.1 - Connect/Enter-Host-Mode/Leave-Host-Mode are gated
    strictly by the live connection sub-state, not just `connected`.
    Before this fix, "Leave Host Mode + Return to Terminal" was enabled
    whenever merely connected, even in verbose mode (where
    exit_host_mode() is a harmless no-op) - exactly the kind of "enabled
    but pointless" control this project has hit before."""

    def test_disconnected_only_connect_actions_are_enabled(self, wired_window):
        w, serial = wired_window
        serial.is_connected = False
        serial.is_verbose_mode = False
        serial.is_host_mode = False

        w._update_tnc_menu_gating()

        assert w._act_connect_verbose.isEnabled()
        assert w._act_connect_host.isEnabled()
        assert not w._act_enter_host_mode.isEnabled()
        assert not w._act_host_off.isEnabled()

    def test_connected_verbose_enables_enter_host_mode_only(self, wired_window):
        w, serial = wired_window
        serial.is_connected = True
        serial.is_verbose_mode = True
        serial.is_host_mode = False

        w._update_tnc_menu_gating()

        assert not w._act_connect_verbose.isEnabled()
        assert not w._act_connect_host.isEnabled()
        assert w._act_enter_host_mode.isEnabled()
        assert not w._act_host_off.isEnabled()

    def test_connected_host_mode_enables_leave_host_mode_only(self, wired_window):
        w, serial = wired_window
        serial.is_connected = True
        serial.is_verbose_mode = False
        serial.is_host_mode = True

        w._update_tnc_menu_gating()

        assert not w._act_connect_verbose.isEnabled()
        assert not w._act_connect_host.isEnabled()
        assert not w._act_enter_host_mode.isEnabled()
        assert w._act_host_off.isEnabled()

    def test_disabled_enter_host_mode_explains_why_in_its_tooltip(self, wired_window):
        w, serial = wired_window
        serial.is_connected = True
        serial.is_verbose_mode = False
        serial.is_host_mode = True

        w._update_tnc_menu_gating()

        assert "Host Mode" in w._act_enter_host_mode.toolTip()


class TestEnterHostModeFromVerbose:
    """P49.A.2 - "Enter Host Mode" is the last chance to upload
    parameters (no cmd: prompt exists in Host Mode at all, P40/P43)."""

    def test_not_connected_does_nothing(self, wired_window):
        w, serial = wired_window
        serial.is_connected = False
        calls = []
        w._enter_host_mode_now = lambda: calls.append("entered")
        w._start_param_upload_thread = lambda: calls.append("uploaded")

        w._on_enter_host_mode()

        assert calls == []

    def test_not_verbose_does_nothing(self, wired_window):
        w, serial = wired_window
        serial.is_connected = True
        serial.is_verbose_mode = False
        calls = []
        w._enter_host_mode_now = lambda: calls.append("entered")
        w._start_param_upload_thread = lambda: calls.append("uploaded")

        w._on_enter_host_mode()

        assert calls == []

    def test_already_uploaded_skips_straight_to_host_mode(self, wired_window):
        w, serial = wired_window
        serial.is_connected = True
        serial.is_verbose_mode = True
        w._params_uploaded_this_session = True
        calls = []
        w._enter_host_mode_now = lambda: calls.append("entered")
        w._start_param_upload_thread = lambda: calls.append("uploaded")

        w._on_enter_host_mode()

        assert calls == ["entered"]

    def test_upload_outstanding_fast_init_off_uploads_first(self, wired_window):
        w, serial = wired_window
        serial.is_connected = True
        serial.is_verbose_mode = True
        w._params_uploaded_this_session = False
        w._config.fast_init = False
        calls = []
        w._enter_host_mode_now = lambda: calls.append("entered")
        w._start_param_upload_thread = lambda: calls.append("uploaded")

        w._on_enter_host_mode()

        assert calls == ["uploaded"]
        assert w._connect_mode == "host"

    def test_fast_init_on_asks_and_upload_choice_uploads_first(self, wired_window):
        w, serial = wired_window
        serial.is_connected = True
        serial.is_verbose_mode = True
        w._params_uploaded_this_session = False
        w._config.fast_init = True
        calls = []
        w._enter_host_mode_now = lambda: calls.append("entered")
        w._start_param_upload_thread = lambda: calls.append("uploaded")
        w._ask_fast_init_upload_choice = lambda: "upload"

        w._on_enter_host_mode()

        assert calls == ["uploaded"]
        assert w._connect_mode == "host"

    def test_fast_init_on_skip_choice_switches_without_upload(self, wired_window):
        w, serial = wired_window
        serial.is_connected = True
        serial.is_verbose_mode = True
        w._params_uploaded_this_session = False
        w._config.fast_init = True
        calls = []
        w._enter_host_mode_now = lambda: calls.append("entered")
        w._start_param_upload_thread = lambda: calls.append("uploaded")
        w._ask_fast_init_upload_choice = lambda: "skip"

        w._on_enter_host_mode()

        assert calls == ["entered"]

    def test_fast_init_on_cancel_choice_does_nothing(self, wired_window):
        w, serial = wired_window
        serial.is_connected = True
        serial.is_verbose_mode = True
        w._params_uploaded_this_session = False
        w._config.fast_init = True
        calls = []
        w._enter_host_mode_now = lambda: calls.append("entered")
        w._start_param_upload_thread = lambda: calls.append("uploaded")
        w._ask_fast_init_upload_choice = lambda: "cancel"

        w._on_enter_host_mode()

        assert calls == []

    def test_new_connection_resets_the_uploaded_flag(self, wired_window):
        w, serial = wired_window
        w._params_uploaded_this_session = True

        w._update_connection_ui(True)

        assert w._params_uploaded_this_session is False


class TestBannerCollection:
    """P49.B - the mirrored init banner is collected in full and inserted
    as ONE block before any [SYS] message follows; stray control bytes
    are filtered from what is displayed. Reproduced 25.09.2026
    (screenshot): "PK-232M is u[SYS] TNC ready in verbose mode\\n[SYS]
    Fast Init...\\n[SYS] Verbose terminal ready...\\nsing default
    values." - the banner text torn apart by the app's own [SYS] lines,
    because a second, later-arriving fragment of it reached the display
    after those lines had already been appended."""

    def test_banner_collected_from_two_fragments_is_shown_as_one_block(self, wired_window):
        w, serial = wired_window
        serial.last_verbose_init_response = b"PK-232M is u"
        # Avoid spawning the real upload thread (touches Qt widgets from
        # a background thread) - this test only checks banner ordering.
        w._start_param_upload_thread = lambda: None

        w._start_banner_collection()
        # The straggling second fragment arrives before the quiet window
        # elapses - exactly the real-world race this closes.
        w._on_raw_data_received(b"sing default values.\r\ncmd:")
        w._finish_banner_collection()

        text = w._vt_display.toPlainText()
        banner_pos = text.find("PK-232M is using default values.")
        sys_pos = text.find("[SYS] TNC ready in verbose mode")
        assert banner_pos != -1, f"banner not shown as one block: {text!r}"
        assert sys_pos != -1
        assert banner_pos < sys_pos, "the [SYS] line must follow the banner, not interrupt it"

    def test_raw_data_is_buffered_not_displayed_while_collecting(self, wired_window):
        w, serial = wired_window
        serial.last_verbose_init_response = b""
        w._stack.setCurrentIndex(1)  # verbose terminal visible

        w._start_banner_collection()
        w._on_raw_data_received(b"straggler")

        assert "straggler" not in w._vt_display.toPlainText()
        assert bytes(w._banner_buffer) == b"straggler"
        # Left mid-collection deliberately (this test only checks
        # buffering) - stop the real timer rather than let it fire later.
        w._banner_timer.stop()

    def test_control_characters_are_filtered_from_the_display(self, wired_window):
        w, serial = wired_window
        serial.last_verbose_init_response = b"\x01\x01OGG\x01AEA PK-232\r\ncmd:"
        w._start_param_upload_thread = lambda: None

        w._start_banner_collection()
        w._finish_banner_collection()

        text = w._vt_display.toPlainText()
        assert "\x01" not in text
        assert "OGGAEA PK-232" in text.replace("\n", "").replace("\r", "")

    def test_no_banner_bytes_still_shows_the_sys_message(self, wired_window):
        w, serial = wired_window
        serial.last_verbose_init_response = b""
        w._start_param_upload_thread = lambda: None

        w._start_banner_collection()
        w._finish_banner_collection()

        assert "[SYS] TNC ready in verbose mode" in w._vt_display.toPlainText()

    def test_firmware_label_set_from_the_fully_collected_banner(self, wired_window):
        # P55.D - reproduced 26.09.2026: the header showed "TNC-Firmware:
        # unknown" despite the log's own "TNC banner captured" line and
        # the full banner visible in the terminal. Root cause:
        # SerialManager._tnc_banner is frozen at whatever the P43
        # detection chain's own read captured - never updated with
        # straggler bytes that only arrive afterward via the
        # ReaderThread, which is exactly what _banner_buffer collects
        # (this test's own two-fragment split puts the "Release ..."
        # line's tail in the SECOND fragment). The firmware label is now
        # parsed from THIS fully-collected buffer instead.
        w, serial = wired_window
        serial.last_verbose_init_response = b"AEA PK-232M\r\nRelease 01."
        w._start_param_upload_thread = lambda: None

        w._start_banner_collection()
        w._on_raw_data_received(b"AUG.91\r\n\r\ncmd:")
        w._finish_banner_collection()

        assert w._lbl_firmware.text() == "Release 01.AUG.91"

    def test_firmware_label_unchanged_when_this_round_has_no_banner(self, wired_window):
        # A bare CR/COMMAND-char/XON reconnect (P53/P54's own steps
        # 2b/2c) carries no banner at all - the label must stay whatever
        # it was, not reset to a blank/placeholder, since the physical
        # TNC has not actually changed.
        w, serial = wired_window
        w._lbl_firmware.setText("Release 01.AUG.91")
        serial.last_verbose_init_response = b"\r\ncmd:"
        w._start_param_upload_thread = lambda: None

        w._start_banner_collection()
        w._finish_banner_collection()

        assert w._lbl_firmware.text() == "Release 01.AUG.91"
