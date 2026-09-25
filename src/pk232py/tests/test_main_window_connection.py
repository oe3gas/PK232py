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

    def __init__(self):
        self.writes: list[bytes] = []
        self.recovery_called = False

    def recovery(self, port_name=None, baudrate=None) -> bool:
        self.recovery_called = True
        self.recovery_args = (port_name, baudrate)
        return True

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

    def test_host_mode_entry_and_mode_combo_are_disabled(self, wired_window):
        w, _serial = wired_window
        w._update_connection_ui(True)

        w._on_init_failed()

        assert not w._tb_host_on.isEnabled()
        assert not w._mode_combo.isEnabled()

    def test_connect_actions_stay_enabled(self, wired_window):
        w, _serial = wired_window
        w._update_connection_ui(True)

        w._on_init_failed()

        assert w._act_connect_verbose.isEnabled()
        assert w._act_connect_host.isEnabled()
        assert w._tb_connect.isEnabled()

    def test_recovery_stays_enabled(self, wired_window):
        w, _serial = wired_window
        w._update_connection_ui(True)

        w._on_init_failed()

        assert w._act_recovery.isEnabled()
        assert w._tb_recovery.isEnabled()

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
        assert not w._tb_recovery.isEnabled()
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
        assert w._tb_recovery.isEnabled()
        assert "Recovery" in w._act_recovery.text()
        assert "Recovery successful - test" in w._vt_display.toPlainText()

    def test_recovery_finished_failure_reenables_and_shows_message(self, wired_window):
        w, _serial = wired_window
        w._on_recovery()

        w._on_recovery_finished(False, "Recovery did not reach the TNC.")

        assert w._act_recovery.isEnabled()
        assert w._tb_recovery.isEnabled()
        assert "Recovery did not reach the TNC." in w._vt_display.toPlainText()
