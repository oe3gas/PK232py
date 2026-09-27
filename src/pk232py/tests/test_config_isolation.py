# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""P48.3 - proof that conftest.py's autouse isolate_config_path fixture
actually protects the operator's real ~/.pk232py/pk232py.ini from a full
MainWindow() lifecycle, not just from the one field the P47 incident
happened to touch.

Deliberately does NOT mock ConfigManager, MainWindow, or closeEvent() -
it exercises the exact same real path the P47 incident did (build a
MainWindow, mutate AppConfig, close it - closeEvent() auto-saves
unconditionally) and relies entirely on the autouse fixture (never
disabled here) to keep the real file safe. Verified by hand while
writing this file that disabling the fixture turns this test red (per
P48's own Definition of Done) - not re-verified on every run, since
"prove the fixture is required" and "run the fixture disabled" cannot
both be true of the checked-in test.

Needs a QApplication; forced to the offscreen platform (see
test_packet_screen.py for why this is done at module level, before any
PyQt6 import).
"""

from __future__ import annotations

import hashlib
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from pk232py.config import CONFIG_FILE
from pk232py.ui.main_window import MainWindow

_app = QApplication.instance() or QApplication([])


def _real_config_fingerprint() -> tuple[bool, bytes | None]:
    """(exists, sha256-of-contents-or-None) for the REAL config file -
    read-only, never written here."""
    if not CONFIG_FILE.exists():
        return False, None
    return True, hashlib.sha256(CONFIG_FILE.read_bytes()).digest()


class TestRealConfigFileIsNeverTouched:
    """P48.3 - a full MainWindow() lifecycle (build, mutate a setting,
    close - closeEvent() auto-saves unconditionally) must never change
    the real config file on disk, regardless of whether it already
    exists on this machine."""

    def test_full_mainwindow_lifecycle_leaves_the_real_file_untouched(self):
        existed_before, fingerprint_before = _real_config_fingerprint()

        w = MainWindow()
        try:
            # Mutate a setting, exactly like the P47 incident did - this
            # proves the isolation holds even when a test changes
            # AppConfig, not just when everything stays at its defaults.
            # A fresh MainWindow()'s SerialManager is never connected, so
            # closeEvent() never pops the "TNC is still connected?"
            # dialog here - nothing to stub.
            w._app_config.hf_packet.show_link_messages_in_ui_channel = True
            w.close()  # closeEvent() -> self._config_mgr.save()
        finally:
            QApplication.instance().removeEventFilter(w)
            w.deleteLater()
            QApplication.instance().processEvents()

        existed_after, fingerprint_after = _real_config_fingerprint()

        if not existed_before:
            assert not existed_after, (
                "the real config file did not exist before this test and "
                "must not exist after it either"
            )
        else:
            assert existed_after, "the real config file must still exist"
            assert fingerprint_after == fingerprint_before, (
                "the real config file's contents changed - the "
                "isolate_config_path autouse fixture did not take effect"
            )


class TestQSettingsIsolation:
    """P61, Teil B - QSettings("OE3GAS", APP_TITLE) (main_window.py's
    _save_window_geometry()/_restore_window_geometry(), window
    position/size and splitter sizes) is the SAME class of gap P48
    closed for the INI config file, at a SECOND storage location:
    isolate_config_path only ever redirected ConfigManager's default
    path, never QSettings, which resolves to the real Windows registry
    (NativeFormat/UserScope) with no isolation of its own at all - every
    test that calls MainWindow.close() (closeEvent() -> _save_window_
    geometry(), unconditional) has been writing there the whole time.

    Deliberately calls `main_window.QSettings(...)` - the module's own
    attribute, resolved fresh at call time - rather than importing
    QSettings directly from PyQt6.QtCore: that is exactly the lookup
    _save_window_geometry() itself performs, and exactly what the
    isolate_qsettings autouse fixture (conftest.py) monkeypatches; a
    fresh `from PyQt6.QtCore import QSettings` here would silently miss
    the redirect and always resolve to the real, unpatched class."""

    def test_qsettings_filename_is_under_tmp_path(self, tmp_path):
        from pk232py.ui import main_window

        s = main_window.QSettings("OE3GAS", main_window.APP_TITLE)
        # QSettings.fileName() always uses forward slashes, even on
        # Windows - compare via as_posix() rather than a raw substring
        # check against tmp_path's own (backslash, on Windows) str().
        assert tmp_path.as_posix() in s.fileName(), (
            f"QSettings resolved to {s.fileName()!r}, not under this "
            f"test's own tmp_path ({tmp_path}) - the isolate_qsettings "
            f"autouse fixture did not take effect"
        )
