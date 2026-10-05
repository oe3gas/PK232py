# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""log_setup.py - the application log (P84).

Console output as before, plus a rotating file next to the INI
(%USERPROFILE%\\.pk232py\\logs\\pk232py.log): 5 files of 2 MB, level DEBUG.
Every session starts with one header line (version, commit, Python, Qt).

Lernmodus: handlers hang on the ROOT logger, so every module's
`logging.getLogger(__name__)` - including ui/thread_guard.py's violation
messages - reaches the file with no change of its own. The file handler is
optional on purpose: a read-only profile folder must never keep the TNC
program from starting, so a failure is reported on the console and skipped.
"""

from __future__ import annotations

import faulthandler
import logging
import os
import platform
import subprocess
import sys
import threading
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from pk232py import __version__
from pk232py.config import CONFIG_FILE, CONFIG_PATH_ENV_VAR

logger = logging.getLogger(__name__)

LOG_FILE_NAME = "pk232py.log"
LOG_MAX_BYTES = 2 * 1024 * 1024
LOG_BACKUP_COUNT = 4          # the current file + 4 backups = 5 files
LOG_FORMAT = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"


def log_dir() -> Path:
    """Folder of the log files: 'logs' next to the INI.

    Follows the INI path override (PK232PY_CONFIG_PATH) so that tests, which
    redirect the INI, never write into the operator's real folder.
    """
    env_path = os.environ.get(CONFIG_PATH_ENV_VAR)
    base = Path(env_path).parent if env_path else CONFIG_FILE.parent
    return base / "logs"


def git_commit() -> str:
    """Short commit hash of the checkout, or 'unknown' (no git, no checkout,
    frozen build). Never raises: a log header must not break the start."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True, text=True, timeout=3, check=True,
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def session_header() -> str:
    from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR
    return (f"PK232PY v{__version__}, commit {git_commit()}, "
            f"Python {platform.python_version()}, "
            f"Qt {QT_VERSION_STR}, PyQt {PYQT_VERSION_STR}")


def setup_logging(directory: Path | None = None) -> Path | None:
    """Configure the root logger; return the log file path (None: no file).

    Safe to call twice: a second call adds no second handler.
    """
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    formatter = logging.Formatter(LOG_FORMAT)

    if not any(type(h) is logging.StreamHandler for h in root.handlers):
        console = logging.StreamHandler()              # stderr, as basicConfig did
        console.setFormatter(formatter)
        root.addHandler(console)

    directory = Path(directory) if directory is not None else log_dir()
    path = directory / LOG_FILE_NAME
    existing = [h for h in root.handlers
                if isinstance(h, RotatingFileHandler)
                and Path(h.baseFilename) == path.resolve()]
    if existing:
        return path
    try:
        directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("no log file (%s): %s", path, exc)
        return None
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(formatter)
    root.addHandler(handler)
    logger.info(session_header())
    return path


# ---------------------------------------------------------------------------
# Crashes (P86)
# ---------------------------------------------------------------------------

CRASH_FILE_NAME = "pk232py_crash.log"
CRASH_FILE_MAX_BYTES = 1024 * 1024    # start a fresh file above this size

NOTICE_INTERVAL_S = 10    # at most one operator notice per this many seconds

_previous_sys_hook = None
_previous_thread_hook = None
_crash_file = None
_error_notifier = None
_last_notice = None


def _now() -> float:
    return time.monotonic()


def set_error_notifier(callback) -> None:
    """Register what tells the operator about an uncaught GUI-thread
    exception (the main window's show_internal_error), or None to unregister.
    The hook calls it in the GUI thread only, at most once per
    NOTICE_INTERVAL_S."""
    global _error_notifier, _last_notice
    _error_notifier = callback
    _last_notice = None


def _notify_operator() -> None:
    """Call the registered notifier - GUI thread only, rate-limited, and
    never allowed to raise out of the exception hook."""
    global _last_notice
    if _error_notifier is None:
        return
    from PyQt6.QtCore import QCoreApplication, QThread
    app = QCoreApplication.instance()
    if app is None or QThread.currentThread() != app.thread():
        return          # CLAUDE.md rule 3: widgets only in the GUI thread
    now = _now()
    if _last_notice is not None and now - _last_notice < NOTICE_INTERVAL_S:
        return
    _last_notice = now
    try:
        _error_notifier()
    except Exception:
        logger.exception("could not show the internal-error notice")


def install_crash_hooks(directory: Path | None = None) -> None:
    """Send every uncaught exception to the log (CRITICAL) and native crashes
    to pk232py_crash.log. Safe to call twice.

    Lernmodus: three different failure paths, three hooks.
    - sys.excepthook: an exception nobody caught in the main thread. This
      includes an exception inside a Qt slot - PyQt6 passes it to
      sys.excepthook, and with only the DEFAULT hook in place it aborts the
      whole application (qFatal); that is how the P86 macro bug killed the
      app. With our hook installed the traceback goes to the log first and
      the application then carries on.
    - threading.excepthook: the same for any threading.Thread.
    - faulthandler: for crashes Python cannot catch (segfault in Qt, abort);
      it writes the Python stack of every thread straight to a file
      descriptor, so the file must stay open for the life of the process.
    The previous hooks are still called, so the console traceback stays.
    """
    global _previous_sys_hook, _previous_thread_hook, _crash_file
    if _previous_sys_hook is not None:
        return
    directory = Path(directory) if directory is not None else log_dir()

    _previous_sys_hook = sys.excepthook
    _previous_thread_hook = threading.excepthook

    def sys_hook(exc_type, exc, tb):
        if not issubclass(exc_type, KeyboardInterrupt):
            logger.critical("Uncaught exception", exc_info=(exc_type, exc, tb))
            _notify_operator()
        _previous_sys_hook(exc_type, exc, tb)

    def thread_hook(args):
        if args.exc_type is not SystemExit:
            name = args.thread.name if args.thread is not None else "?"
            logger.critical(
                "Uncaught exception in thread %r", name,
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )
        _previous_thread_hook(args)

    sys.excepthook = sys_hook
    threading.excepthook = thread_hook

    try:
        directory.mkdir(parents=True, exist_ok=True)
        crash_path = directory / CRASH_FILE_NAME
        too_big = (crash_path.exists()
                   and crash_path.stat().st_size > CRASH_FILE_MAX_BYTES)
        _crash_file = open(crash_path, "w" if too_big else "a", encoding="utf-8")
        _crash_file.write(f"--- session {datetime.now().isoformat(timespec='seconds')}"
                          f" ---\n")
        _crash_file.flush()
        faulthandler.enable(file=_crash_file, all_threads=True)
    except OSError as exc:
        _crash_file = None
        logger.warning("no crash log in %s: %s", directory, exc)


def uninstall_crash_hooks() -> None:
    """Undo install_crash_hooks() (used by the tests; the app never does)."""
    global _previous_sys_hook, _previous_thread_hook, _crash_file
    if _previous_sys_hook is None:
        return
    sys.excepthook = _previous_sys_hook
    threading.excepthook = _previous_thread_hook
    _previous_sys_hook = _previous_thread_hook = None
    if _crash_file is not None:
        faulthandler.disable()
        _crash_file.close()
        _crash_file = None
