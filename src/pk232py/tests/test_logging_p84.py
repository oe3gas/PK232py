# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""P84 - rotating log file next to the INI, session header, Help menu entry."""

from __future__ import annotations

import logging
import os
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QApplication

from pk232py import __version__, log_setup
from pk232py.config import CONFIG_FILE, CONFIG_PATH_ENV_VAR

_app = QApplication.instance() or QApplication([])


@pytest.fixture
def clean_root():
    """setup_logging() changes the ROOT logger: put it back afterwards."""
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield root
    for h in list(root.handlers):
        if h not in handlers:
            root.removeHandler(h)
            h.close()
    root.setLevel(level)


def file_handlers(root):
    return [h for h in root.handlers if isinstance(h, RotatingFileHandler)]


def flush(root):
    for h in root.handlers:
        h.flush()


class TestLocation:
    def test_default_is_logs_next_to_the_ini(self, monkeypatch):
        monkeypatch.delenv(CONFIG_PATH_ENV_VAR, raising=False)
        assert log_setup.log_dir() == CONFIG_FILE.parent / "logs"

    def test_follows_the_ini_when_its_path_is_redirected(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CONFIG_PATH_ENV_VAR, str(tmp_path / "x" / "my.ini"))
        assert log_setup.log_dir() == tmp_path / "x" / "logs"


class TestFileHandler:
    def test_rotating_5_files_of_2_mb_debug(self, tmp_path, clean_root):
        path = log_setup.setup_logging(tmp_path)
        assert path == tmp_path / "pk232py.log"
        (h,) = file_handlers(clean_root)
        assert h.maxBytes == 2 * 1024 * 1024
        assert h.backupCount == 4                     # current + 4 = 5 files
        assert h.level == logging.DEBUG
        assert Path(h.baseFilename) == path

    def test_debug_goes_to_the_file(self, tmp_path, clean_root):
        path = log_setup.setup_logging(tmp_path)
        logging.getLogger("some.module").debug("hello %s", "file")
        flush(clean_root)
        assert "hello file" in path.read_text(encoding="utf-8")

    def test_console_handler_is_kept(self, tmp_path, clean_root):
        log_setup.setup_logging(tmp_path)
        consoles = [h for h in clean_root.handlers
                    if type(h) is logging.StreamHandler]
        assert consoles

    def test_second_call_adds_no_second_file_handler(self, tmp_path, clean_root):
        log_setup.setup_logging(tmp_path)
        log_setup.setup_logging(tmp_path)
        assert len(file_handlers(clean_root)) == 1

    def test_unwritable_folder_does_not_stop_the_app(self, tmp_path, clean_root):
        blocker = tmp_path / "file"
        blocker.write_text("x")                       # a FILE where a folder is needed
        assert log_setup.setup_logging(blocker / "logs") is None
        assert file_handlers(clean_root) == []


class TestSessionHeader:
    def test_first_line_names_version_commit_python_and_qt(self, tmp_path, clean_root):
        import platform
        from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR
        path = log_setup.setup_logging(tmp_path)
        flush(clean_root)
        first = path.read_text(encoding="utf-8").splitlines()[0]
        assert f"PK232PY v{__version__}" in first
        assert "commit " in first
        assert f"Python {platform.python_version()}" in first
        assert f"Qt {QT_VERSION_STR}" in first
        assert f"PyQt {PYQT_VERSION_STR}" in first

    def test_commit_hash_comes_from_git_in_a_checkout(self):
        commit = log_setup.git_commit()
        assert commit == "unknown" or all(c in "0123456789abcdef" for c in commit.rstrip("+"))

    def test_commit_is_unknown_without_git(self, monkeypatch):
        def boom(*a, **k):
            raise FileNotFoundError("git")
        monkeypatch.setattr(log_setup.subprocess, "run", boom)
        assert log_setup.git_commit() == "unknown"


class TestThreadGuardReachesTheFile:
    def test_a_violation_is_in_the_log_file(self, tmp_path, clean_root):
        from pk232py.ui import thread_guard
        path = log_setup.setup_logging(tmp_path)
        t = threading.Thread(
            target=lambda: thread_guard.assert_gui_thread("p84-probe"),
            name="probe-thread")
        os.environ["PK232_THREAD_GUARD"] = "log"       # record, do not raise in the thread
        try:
            t.start()
            t.join()
        finally:
            os.environ["PK232_THREAD_GUARD"] = "raise"
        flush(clean_root)
        text = path.read_text(encoding="utf-8")
        assert "widget access outside the GUI thread: p84-probe" in text
        thread_guard.clear_violations()                # provoked on purpose


class TestHelpMenuEntry:
    def test_open_log_folder_opens_the_log_dir(self, tmp_path, monkeypatch):
        from pk232py.ui import main_window as mw
        monkeypatch.setenv(CONFIG_PATH_ENV_VAR, str(tmp_path / "pk232py.ini"))
        opened = []
        monkeypatch.setattr(mw.QDesktopServices, "openUrl",
                            lambda url: opened.append(url) or True)
        win = mw.MainWindow()
        help_menu = next(a.menu() for a in win.menuBar().actions()
                         if a.text() == "&Help")
        (action,) = [a for a in help_menu.actions() if a.text() == "Open &log folder"]
        action.trigger()
        assert opened == [QUrl.fromLocalFile(str(tmp_path / "logs"))]
        assert (tmp_path / "logs").is_dir()            # created if it did not exist yet
