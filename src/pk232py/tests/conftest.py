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

import pytest

from pk232py.config import CONFIG_PATH_ENV_VAR


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
