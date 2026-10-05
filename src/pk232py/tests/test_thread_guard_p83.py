# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""P83 A - the thread guard itself."""

from __future__ import annotations

import logging
import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from pk232py.ui import thread_guard
from pk232py.ui.main_window import MainWindow
from pk232py.ui.thread_guard import GuiThreadViolation, assert_gui_thread

_app = QApplication.instance() or QApplication([])


def run_in_thread(fn):
    """Run *fn* in a real threading.Thread; return (result, exception)."""
    out = {}

    def target():
        try:
            out["result"] = fn()
        except BaseException as exc:          # noqa: BLE001 - the test inspects it
            out["error"] = exc

    t = threading.Thread(target=target, name="Probe-Thread")
    t.start()
    t.join(5)
    return out.get("result"), out.get("error")


@pytest.fixture(autouse=True)
def forget_the_provoked_violations():
    yield
    thread_guard.clear_violations()


class TestAssertGuiThread:
    def test_the_gui_thread_passes(self):
        assert_gui_thread("here")
        assert thread_guard.violations() == []

    def test_another_thread_is_recorded_and_logged(self, caplog):
        with caplog.at_level(logging.ERROR, logger="pk232py.ui.thread_guard"):
            _result, _error = run_in_thread(lambda: assert_gui_thread("somewhere"))
        (line,) = thread_guard.violations()
        assert "somewhere" in line and "Probe-Thread" in line
        assert any("somewhere" in r.getMessage() for r in caplog.records)

    def test_strict_mode_raises(self, monkeypatch):
        monkeypatch.setenv("PK232_THREAD_GUARD", "raise")
        _result, error = run_in_thread(lambda: assert_gui_thread("somewhere"))
        assert isinstance(error, GuiThreadViolation)

    def test_without_strict_mode_it_only_records(self, monkeypatch):
        monkeypatch.delenv("PK232_THREAD_GUARD", raising=False)
        _result, error = run_in_thread(lambda: assert_gui_thread("somewhere"))
        assert error is None and len(thread_guard.violations()) == 1


class TestTheWidgetMethodsAreGuarded:
    @pytest.mark.parametrize("call", [
        lambda w: w._vt_append("x"),
        lambda w: w._log_monitor("x"),
        lambda w: w._log_terminal("x"),
        lambda w: w._update_maildrop_gate_ui(),
    ])
    def test_a_call_from_a_thread_is_caught(self, call):
        w = MainWindow()
        _result, error = run_in_thread(lambda: call(w))
        assert isinstance(error, GuiThreadViolation)
        assert len(thread_guard.violations()) == 1

    def test_the_same_calls_in_the_gui_thread_are_fine(self):
        w = MainWindow()
        w._vt_append("x")
        w._log_monitor("x")
        w._log_terminal("x")
        w._update_maildrop_gate_ui()
        assert thread_guard.violations() == []
