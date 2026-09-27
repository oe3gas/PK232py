# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Shared pytest fixtures for the whole suite (P48).

Test config isolation is a PROPERTY OF THE TEST ENVIRONMENT here, not a
habit an individual test author has to remember (P48, 2026-09-25,
following directly from a P47 incident): a plain MainWindow()/
ConfigManager() call with no explicit path resolves to the operator's
real ~/.pk232py/pk232py.ini, and MainWindow.closeEvent() auto-saves it
unconditionally. Two P47 tests that mutated AppConfig with no reset had
written test values into that real file - confirmed on disk (port COM7,
real callsigns) - and the mutation then leaked into every LATER
MainWindow() built in the same pytest run. Fixed there per-test; fixed
here for good.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtWidgets import QApplication

from pk232py.config import CONFIG_PATH_ENV_VAR
from pk232py.ui.main_window import MainWindow


@pytest.fixture(autouse=True)
def dispose_main_windows():
    """P61, Teil A - every MainWindow a test built is destroyed at
    teardown, not merely hidden.

    MainWindow.__init__() installs itself as an application-wide event
    filter (QApplication.instance().installEventFilter(self)) - a window
    that is only close()d keeps that filter active forever (no
    WA_DeleteOnClose, and signal connections/closures keep the Python
    object reachable too), so it goes on filtering EVERY event of EVERY
    later test. Measured (P61 Befund B.2): building a fresh MainWindow()
    cost 0.11s with no other live window around, 2.62s with 11
    undisposed ones still there - a real, measured quadratic cost, not a
    theoretical one. Loops over topLevelWidgets() (not a per-fixture
    reference) so it catches every MainWindow regardless of which
    fixture or test body built it - including one built with no fixture
    at all, or a fixture using `return` instead of `yield` (no teardown
    of its own whatsoever).

    Never calls close(): that would run closeEvent(), which pops a real,
    unclickable QMessageBox.question() under the offscreen QPA platform
    whenever _serial.is_connected happens to be True on whatever stub a
    test wired up - exactly the hang test_main_window_packet.py's own
    wired_vhf fixture already had to work around once (P42). Going
    straight to removeEventFilter()+deleteLater() skips that path
    entirely; test_config_isolation.py's own test of closeEvent()'s
    save-on-close behaviour still calls close() explicitly in its own
    test body, which this fixture does not interfere with.
    """
    yield
    app = QApplication.instance()
    if app is None:
        return
    for w in [w for w in app.topLevelWidgets() if isinstance(w, MainWindow)]:
        app.removeEventFilter(w)
        w.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)


@pytest.fixture(autouse=True)
def isolate_config_path(tmp_path, monkeypatch):
    """Redirect every ConfigManager() default (including every plain
    MainWindow()) to a throwaway file under this test's own tmp_path.

    monkeypatch.setenv() reverts automatically at teardown, so this
    never leaks into a later test either. Tests that construct
    ConfigManager(path=...) explicitly are unaffected - an explicit path
    always wins over the environment variable (see ConfigManager.
    __init__()) - so this fixture costs those tests nothing and does not
    change their behaviour; it only matters for the (common) case of no
    path being given at all.
    """
    monkeypatch.setenv(CONFIG_PATH_ENV_VAR, str(tmp_path / "pk232py.ini"))
