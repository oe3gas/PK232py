# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""ui/thread_guard.py - detect widget access outside the GUI thread (P83).

Qt allows widget access only in the GUI thread; a violation does not fail
at once, it corrupts the display or crashes sporadically (CLAUDE.md rule 3).
assert_gui_thread() is called at the top of the methods that touch widgets
and that a background thread could reach. It never changes behaviour in
production: a violation is logged (logger.error with place and thread name)
and recorded. With the environment variable PK232_THREAD_GUARD=raise (the
test suite sets it, tests/conftest.py) it raises GuiThreadViolation as well.

Lernmodus: threading.Thread objects are not QThreads. QThread.currentThread()
still works in them - Qt wraps the foreign thread in an adopted QThread
object - and differs from QCoreApplication.thread(), the GUI thread.
"""

from __future__ import annotations

import logging
import os
import threading

from PyQt6.QtCore import QCoreApplication, QThread

logger = logging.getLogger(__name__)

ENV_VAR = "PK232_THREAD_GUARD"

_violations: list[str] = []


class GuiThreadViolation(RuntimeError):
    """Widget access from a thread other than the GUI thread."""


def assert_gui_thread(where: str) -> None:
    """Record (and, in strict mode, raise) if the caller is not the GUI thread."""
    app = QCoreApplication.instance()
    if app is None or QThread.currentThread() == app.thread():
        return
    message = (f"widget access outside the GUI thread: {where} "
               f"(thread {threading.current_thread().name!r})")
    logger.error(message)
    _violations.append(message)
    if os.environ.get(ENV_VAR) == "raise":
        raise GuiThreadViolation(message)


def violations() -> list[str]:
    """Every violation recorded since the last clear_violations()."""
    return list(_violations)


def clear_violations() -> None:
    _violations.clear()
