# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""P83 D - the parameter upload thread touches no widget.

_run_param_upload() runs in a real threading.Thread with a fake serial, the
thread guard is strict (tests/conftest.py). What reaches the terminal and the
monitor is compared with a list recorded BEFORE the change from the old,
synchronous implementation (tests/data/upload_baseline_p83.json): the order and
the text must be identical. enter_host_mode() must be called in the GUI thread.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from pk232py.ui import thread_guard
from pk232py.ui.main_window import MainWindow

_app = QApplication.instance() or QApplication([])

BASELINE = json.loads(
    (pathlib.Path(__file__).parent / "data" / "upload_baseline_p83.json").read_text(encoding="utf-8"))


def normal(text: str) -> str:
    """DAYTIME carries the clock - the one line that differs between runs."""
    return re.sub(r"DAYTIME \d+", "DAYTIME <t>", text)


class FakeSerial:
    is_connected = True
    is_host_mode = False
    verbose_confirmed = True
    has_pactor = False
    fresh_boot_defaults = False
    banner_seen_this_init = True            # no live-link check in these tests

    def __init__(self, has_maildrop=True, tnc_value=None):
        self.sent = []
        self.has_maildrop = has_maildrop
        self.tnc_value = tnc_value
        self.host_calls: list[str] = []     # name of the thread that called enter_host_mode()

    def write_verbose_wait(self, data, timeout=5.0):
        self.sent.append(data)
        return True

    def detect_maildrop(self):
        return self.has_maildrop

    def query_verbose_value(self, name, timeout=3.0):
        if self.tnc_value is not None:
            return self.tnc_value
        return {"MYCALL": "OE3GAS", "PACLEN": "128", "MAXFRAME": "1"}.get(name)

    def enter_host_mode(self):
        self.host_calls.append(threading.current_thread().name)
        return True

    def consume_fresh_boot_defaults(self):
        return False


def build_window(monkeypatch, scenario: str):
    mode, fast, bad_verify, no_maildrop = {
        "verbose": ("verbose", False, False, False),
        "host": ("host", False, False, False),
        "fast_verbose": ("verbose", True, False, False),
        "fast_host": ("host", True, False, False),
        "verify_bad": ("verbose", False, True, False),
        "nomaildrop": ("verbose", False, False, True),
    }[scenario]
    w = MainWindow()
    cfg = w._app_config.hf_packet
    cfg.mycall, cfg.paclen, cfg.maxframe = "OE3GAS", 128, 1
    w._serial = FakeSerial(has_maildrop=not no_maildrop, tnc_value="WRONG" if bad_verify else None)
    w._config.fast_init = fast
    w._connect_mode = mode
    w.monitor_lines = []
    real = w._log_monitor
    monkeypatch.setattr(w, "_log_monitor",
                        lambda text, raw=b"": (w.monitor_lines.append(text), real(text, raw))[1])
    return w


def run_in_thread(w) -> list:
    """_run_param_upload() in a real thread; then deliver the queued signals in
    the GUI thread. Returns the exceptions the thread died of."""
    errors = []
    previous = threading.excepthook
    threading.excepthook = lambda args: errors.append(args.exc_value)
    try:
        t = threading.Thread(target=w._run_param_upload, name="PK232-ParamUpload")
        t.start()
        t.join(10)
        assert not t.is_alive()
    finally:
        threading.excepthook = previous
    for _ in range(5):
        _app.processEvents()
    return errors


SCENARIOS = ["verbose", "host", "fast_verbose", "fast_host", "verify_bad", "nomaildrop"]


class TestNoWidgetAccessFromTheThread:
    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_the_thread_raises_nothing_and_the_guard_stays_silent(self, monkeypatch, scenario):
        w = build_window(monkeypatch, scenario)
        errors = run_in_thread(w)
        assert errors == []
        assert thread_guard.violations() == []

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_terminal_and_monitor_are_what_they_were_before(self, monkeypatch, scenario):
        w = build_window(monkeypatch, scenario)
        run_in_thread(w)
        expected = BASELINE[scenario]
        assert normal(w._vt_display.toPlainText()) == normal(expected["vt"])
        assert [normal(m) for m in w.monitor_lines] == [normal(m) for m in expected["mon"]]


class TestHostModeEntryInTheGuiThread:
    @pytest.mark.parametrize("scenario", ["host", "fast_host"])
    def test_enter_host_mode_is_called_in_the_gui_thread(self, monkeypatch, scenario):
        w = build_window(monkeypatch, scenario)
        run_in_thread(w)
        assert w._serial.host_calls == [threading.main_thread().name]

    @pytest.mark.parametrize("scenario", ["verbose", "fast_verbose", "verify_bad", "nomaildrop"])
    def test_verbose_mode_never_enters_host_mode(self, monkeypatch, scenario):
        w = build_window(monkeypatch, scenario)
        run_in_thread(w)
        assert w._serial.host_calls == []


class TestTheEchoCallback:
    def test_the_uploader_echo_goes_through_a_signal(self, monkeypatch):
        w = build_window(monkeypatch, "verbose")
        run_in_thread(w)
        assert "MYCALL OE3GAS\n" in w._vt_display.toPlainText()
        assert thread_guard.violations() == []
