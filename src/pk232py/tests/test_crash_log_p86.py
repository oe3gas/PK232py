# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""P86 - uncaught exceptions end up in the log file, not only on the console.

The macro crash of P86 left its traceback ONLY on the console. Now
sys.excepthook and threading.excepthook write every uncaught exception with
its traceback to the log file (CRITICAL), and faulthandler writes native
crashes (segfault, Qt abort) to pk232py_crash.log in the log folder.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

from pk232py import log_setup

_app = QApplication.instance() or QApplication([])


@pytest.fixture
def hooks(tmp_path, monkeypatch):
    """Log file in tmp_path, crash hooks installed; everything restored after.

    faulthandler.enable/disable are replaced by recorders: pytest runs its
    own faulthandler and a real disable() here would switch that off for the
    rest of the run.
    """
    fh_calls: list = []
    monkeypatch.setattr(log_setup.faulthandler, "enable",
                        lambda file=None, **kw: fh_calls.append(file))
    monkeypatch.setattr(log_setup.faulthandler, "disable", lambda: None)
    root = logging.getLogger()
    before, level = list(root.handlers), root.level
    prev_sys, prev_thread = sys.excepthook, threading.excepthook
    seen_by_previous: list = []
    sys.excepthook = lambda *a: seen_by_previous.append(a)       # stands in for the default
    threading.excepthook = lambda args: None    # pytest's own would warn about the probe
    log_path = log_setup.setup_logging(tmp_path)
    log_setup.install_crash_hooks(tmp_path)
    yield tmp_path, log_path, fh_calls, seen_by_previous
    log_setup.uninstall_crash_hooks()
    sys.excepthook, threading.excepthook = prev_sys, prev_thread
    for h in list(root.handlers):
        if h not in before:
            root.removeHandler(h)
            h.close()
    root.setLevel(level)


def log_text(path: Path) -> str:
    for h in logging.getLogger().handlers:
        h.flush()
    return path.read_text(encoding="utf-8")


def test_uncaught_exception_is_logged_critical_with_traceback(hooks):
    _, log_path, _, _ = hooks
    try:
        raise ValueError("boom-main")
    except ValueError:
        sys.excepthook(*sys.exc_info())
    text = log_text(log_path)
    assert "CRITICAL" in text
    assert "Traceback (most recent call last)" in text
    assert "ValueError: boom-main" in text


def test_the_previous_hook_still_runs_so_the_console_keeps_its_traceback(hooks):
    _, _, _, seen_by_previous = hooks
    try:
        raise ValueError("boom-console")
    except ValueError:
        sys.excepthook(*sys.exc_info())
    assert len(seen_by_previous) == 1


def test_exception_in_a_qt_slot_is_logged(hooks):
    _, log_path, _, _ = hooks

    class Emitter(QObject):
        fired = pyqtSignal()

    def bad_slot():
        raise AttributeError("no char_typed here")

    emitter = Emitter()
    emitter.fired.connect(bad_slot)
    emitter.fired.emit()                       # PyQt6 hands the exception to sys.excepthook
    text = log_text(log_path)
    assert "CRITICAL" in text
    assert "AttributeError: no char_typed here" in text
    assert "bad_slot" in text                  # the traceback names the slot


def test_exception_in_a_thread_is_logged_with_the_thread_name(hooks):
    _, log_path, _, _ = hooks

    def worker():
        raise RuntimeError("boom-thread")

    t = threading.Thread(target=worker, name="p86-worker")
    t.start()
    t.join()
    text = log_text(log_path)
    assert "CRITICAL" in text
    assert "p86-worker" in text
    assert "RuntimeError: boom-thread" in text
    assert "Traceback (most recent call last)" in text


def test_faulthandler_writes_to_the_crash_log_in_the_log_folder(hooks):
    folder, _, fh_calls, _ = hooks
    (crash_file,) = fh_calls
    assert Path(crash_file.name) == folder / "pk232py_crash.log"
    assert (folder / "pk232py_crash.log").exists()


def test_installing_twice_does_not_log_an_exception_twice(hooks):
    folder, log_path, _, _ = hooks
    log_setup.install_crash_hooks(folder)
    try:
        raise ValueError("boom-once")
    except ValueError:
        sys.excepthook(*sys.exc_info())
    assert log_text(log_path).count("ValueError: boom-once") == 1


def test_an_unwritable_folder_still_installs_the_hooks(tmp_path, monkeypatch):
    monkeypatch.setattr(log_setup.faulthandler, "enable", lambda **kw: None)
    monkeypatch.setattr(log_setup.faulthandler, "disable", lambda: None)
    blocker = tmp_path / "file"
    blocker.write_text("x")
    prev_sys, prev_thread = sys.excepthook, threading.excepthook
    try:
        log_setup.install_crash_hooks(blocker / "logs")
        assert sys.excepthook is not prev_sys
    finally:
        log_setup.uninstall_crash_hooks()
        sys.excepthook, threading.excepthook = prev_sys, prev_thread


# --- notice to the operator (P86 addendum) ---------------------------------

NOTICE_TEXT = ("Internal error - the last action may be incomplete. "
               "Details in the log file.")


def raise_in_hook():
    try:
        raise ValueError("boom-notice")
    except ValueError:
        sys.excepthook(*sys.exc_info())


@pytest.fixture
def notifier(hooks, monkeypatch):
    calls: list = []
    clock = [1000.0]
    monkeypatch.setattr(log_setup, "_now", lambda: clock[0])
    log_setup.set_error_notifier(lambda: calls.append(1))
    yield calls, clock
    log_setup.set_error_notifier(None)


def test_an_exception_in_the_gui_thread_notifies_the_operator(notifier):
    calls, _ = notifier
    raise_in_hook()
    assert calls == [1]


def test_at_most_one_notice_per_10_seconds(notifier):
    calls, clock = notifier
    raise_in_hook()
    clock[0] += 9.9
    raise_in_hook()
    assert calls == [1]                        # second one swallowed...
    clock[0] += 0.2                            # ...10.1 s after the first
    raise_in_hook()
    assert calls == [1, 1]


def test_every_exception_is_still_logged_even_when_the_notice_is_held_back(notifier, hooks):
    _, log_path, _, _ = hooks
    raise_in_hook()
    raise_in_hook()
    assert log_text(log_path).count("ValueError: boom-notice") == 2


def test_an_exception_in_a_thread_never_touches_the_gui(notifier):
    calls, _ = notifier

    def worker():
        sys.excepthook(*_exc_info())

    def _exc_info():
        try:
            raise ValueError("from-thread")
        except ValueError:
            return sys.exc_info()

    t = threading.Thread(target=worker)
    t.start()
    t.join()
    assert calls == []                         # rule 3: widgets only in the GUI thread


def test_a_failing_notifier_does_not_break_the_hook(hooks, monkeypatch):
    _, log_path, _, seen_by_previous = hooks
    monkeypatch.setattr(log_setup, "_now", lambda: 5000.0)

    def broken():
        raise RuntimeError("notifier broke")

    log_setup.set_error_notifier(broken)
    try:
        raise_in_hook()
    finally:
        log_setup.set_error_notifier(None)
    assert len(seen_by_previous) == 1          # the console traceback still happened
    assert "ValueError: boom-notice" in log_text(log_path)


def test_the_window_shows_a_non_blocking_notice_with_a_log_folder_button(tmp_path, monkeypatch):
    from pk232py.config import CONFIG_PATH_ENV_VAR
    from pk232py.ui import main_window as mw
    from PyQt6.QtCore import QUrl
    from PyQt6.QtWidgets import QMessageBox
    monkeypatch.setenv(CONFIG_PATH_ENV_VAR, str(tmp_path / "pk232py.ini"))
    opened = []
    monkeypatch.setattr(mw.QDesktopServices, "openUrl",
                        lambda url: opened.append(url) or True)
    win = mw.MainWindow()
    win.show_internal_error()                  # must RETURN (not exec) - this call is the test
    box = win._internal_error_box
    assert box.text() == NOTICE_TEXT
    assert not box.isModal()
    labels = [b.text() for b in box.buttons()]
    assert "Open log folder" in labels
    button = next(b for b in box.buttons() if b.text() == "Open log folder")
    button.click()
    assert opened == [QUrl.fromLocalFile(str(tmp_path / "logs"))]
    box.close()


def test_a_second_notice_does_not_stack_a_second_box(tmp_path, monkeypatch):
    from pk232py.config import CONFIG_PATH_ENV_VAR
    from pk232py.ui import main_window as mw
    monkeypatch.setenv(CONFIG_PATH_ENV_VAR, str(tmp_path / "pk232py.ini"))
    win = mw.MainWindow()
    win.show_internal_error()
    first = win._internal_error_box
    win.show_internal_error()
    assert win._internal_error_box is first
    first.close()
