# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""MailDrop verbose-mode session state machine (P27.2).

Lifecycle (CLAUDE.md "MailDrop session"; MDCHECK has no Host Mode
mnemonic at all, see docs/P26_MDCHECK_Mnemonic_Spec.md / `mdcheck_scan`):

    Host Mode --> verbose --> MDCHECK --> [session] --> B --> Host Mode

Both Host Mode transitions are the SAME proven `SerialManager` paths the
rest of the app already uses (`exit_host_mode()`/`enter_host_mode()`,
Path B in OPMODE_SWITCH_STATE_MACHINE.md) — this module does not rebuild
Host Mode entry/exit, and sends no Host Mode frame of its own. Everything
below the "verbose" line in the diagram is plain ASCII text at the
mailbox's own prompt, exchanged the same way `tools/hw_check.py`'s
`maildrop`/`maildrop_host` subcommands already proved out by hand.

CLAUDE.md's Qt rule for this module: all blocking exchanges run on a
background worker thread (`threading.Thread`, matching `SerialManager`'s
own `_ReaderThread`/init-thread pattern — not a new queue on the Host
Mode ACK path, which CLAUDE.md SS3 forbids; this thread never touches the
serial port directly, only `SerialManagerChannel` below does, via
`SerialManager`'s already-proven `write_verbose()`/`raw_data_received`).
Every result reaches the caller exclusively through the Qt signals below.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Callable, Optional

from PyQt6.QtCore import QObject, pyqtSignal

from . import protocol

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Timing constants (P27.2) — each with its own reason, not guessed:
# ---------------------------------------------------------------------------
_IDLE_S             = 1.5   # matches tools/hw_check.py's own read_until_idle()
_CMD_TIMEOUT_S      = 15.0  # a listing can be long
_OPEN_TIMEOUT_S     = 8.0   # MDCHECK specifically (P27 spec)
_CMDPROMPT_TIMEOUT_S = 5.0  # waiting for cmd: after leaving Host Mode / on recovery
_HOST_MODE_TIMEOUT_S = 10.0  # matches tools/hw_check.py's own enter_host_mode wait

_STORED_RE = re.compile(r"Message stored as #\s*(\d+)")


class SerialManagerChannel:
    """Adapts an already-connected `SerialManager` for `MailDropSession`'s
    verbose-mode read/write needs (P27.2) — the ONLY code in this module
    that touches `SerialManager` directly, so the state machine itself
    needs no serial port and no thread of its own to be unit-tested (see
    the fake channel in test_maildrop_session.py).

    Buffers `raw_data_received` non-destructively (SerialManager's own
    `write_verbose_wait()` reads a SEPARATE internal buffer for its own
    purposes — see serial_manager.py's `_on_raw_data()`, which feeds both
    without either consuming the other)."""

    def __init__(self, serial_manager) -> None:
        self._sm = serial_manager
        self._buf = bytearray()
        self._lock = threading.Lock()
        self._sm.raw_data_received.connect(self._on_raw)

    def _on_raw(self, data: bytes) -> None:
        with self._lock:
            self._buf.extend(data)

    def write(self, data: bytes) -> None:
        self._sm.write_verbose(data)

    def read_new(self) -> bytes:
        """Pop and return every byte received since the last call."""
        with self._lock:
            data = bytes(self._buf)
            self._buf.clear()
        return data

    def enter_host_mode(self) -> None:
        self._sm.enter_host_mode()

    def exit_host_mode(self) -> None:
        self._sm.exit_host_mode()

    @property
    def is_host_mode(self) -> bool:
        return self._sm.is_host_mode


class MailDropSession(QObject):
    """Drives one MDCHECK mailbox session over the verbose-mode serial
    link (P27.2). States: CLOSED -> OPENING -> ACTIVE -> CLOSING ->
    CLOSED, plus FAILED. Builds no UI — a future session mask wires the
    signals below to widgets.
    """

    state_changed = pyqtSignal(str)
    prompt_info   = pyqtSignal(object)   # PromptInfo, after every response
    listing       = pyqtSignal(list)     # list[MailDropEntry]
    message_read  = pyqtSignal(object, str)  # MailDropEntry, body text
    stored        = pyqtSignal(int)      # "Message stored as # n"
    killed        = pyqtSignal(int)
    failed        = pyqtSignal(str)      # plain text for the status line

    # Class attributes (not module constants) so tests can shrink them on
    # an instance for speed, without changing the real defaults above.
    IDLE_S              = _IDLE_S
    CMD_TIMEOUT_S       = _CMD_TIMEOUT_S
    OPEN_TIMEOUT_S      = _OPEN_TIMEOUT_S
    CMDPROMPT_TIMEOUT_S = _CMDPROMPT_TIMEOUT_S
    HOST_MODE_TIMEOUT_S = _HOST_MODE_TIMEOUT_S

    def __init__(
        self, channel, can_open: Callable[[], tuple], parent=None,
    ) -> None:
        """*channel* is a SerialManagerChannel (or, in tests, a fake with
        the same write()/read_new()/enter_host_mode()/exit_host_mode()/
        is_host_mode shape). *can_open* is injected so this class never
        has to know the channel model — it just asks "is now OK?" and
        gets (bool, reason)."""
        super().__init__(parent)
        self._channel = channel
        self._can_open = can_open
        self._state = "CLOSED"
        self._busy = False
        self._busy_lock = threading.Lock()

    @property
    def state(self) -> str:
        return self._state

    def _set_state(self, state: str) -> None:
        self._state = state
        logger.info("MailDropSession: %s", state)
        self.state_changed.emit(state)

    # -- worker plumbing -----------------------------------------------

    def _start(self, target: Callable[[], None]) -> None:
        def run() -> None:
            try:
                target()
            finally:
                with self._busy_lock:
                    self._busy = False
        threading.Thread(target=run, daemon=True).start()

    def _claim(self) -> bool:
        """True if no other command is currently running; marks this one
        as running until its worker function returns."""
        with self._busy_lock:
            if self._busy:
                return False
            self._busy = True
            return True

    def _read_until_idle(
        self, idle: Optional[float] = None, max_total: Optional[float] = None,
    ) -> str:
        """Read from the channel until it goes quiet for *idle* seconds,
        or *max_total* elapses — the same idle-gap approach
        `tools/hw_check.py`'s `Session.read_until_idle()` already proved
        against real hardware, since the mailbox's own prompt is not
        `cmd:` and cannot be waited for that way."""
        idle = self.IDLE_S if idle is None else idle
        max_total = self.CMD_TIMEOUT_S if max_total is None else max_total
        deadline = time.monotonic() + max_total
        buf = bytearray()
        idle_since = time.monotonic()
        while time.monotonic() < deadline:
            chunk = self._channel.read_new()
            if chunk:
                buf.extend(chunk)
                idle_since = time.monotonic()
            elif time.monotonic() - idle_since >= idle:
                break
            time.sleep(0.05)
        return bytes(buf).decode("ascii", errors="replace")

    def _send(
        self, data: bytes, idle: Optional[float] = None, max_total: Optional[float] = None,
    ) -> str:
        self._channel.read_new()  # drop anything stale before sending
        self._channel.write(data)
        return self._read_until_idle(idle=idle, max_total=max_total)

    def _report_prompt(self, resp: str) -> None:
        info = protocol.find_prompt(resp)
        if info is not None:
            self.prompt_info.emit(info)

    def _wait_for(self, condition: Callable[[], bool], timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if condition():
                return True
            time.sleep(0.05)
        return condition()

    # -- opening ----------------------------------------------------------

    def open(self) -> None:
        """Leave Host Mode, open the mailbox with MDCHECK (P27.2 step by
        step). No-op if not CLOSED or already busy."""
        if self._state != "CLOSED":
            self.failed.emit(f"cannot open: session is {self._state}")
            return
        ok, reason = self._can_open()
        if not ok:
            self.failed.emit(reason)
            return
        if not self._claim():
            self.failed.emit("session busy")
            return
        self._set_state("OPENING")
        self._start(self._open_worker)

    def _open_worker(self) -> None:
        try:
            logger.info("MailDropSession.open: leaving Host Mode")
            self._channel.exit_host_mode()

            # "auf cmd: warten" (spec) — the TNC does not spontaneously
            # print cmd: on Host Mode exit, so this ACTIVELY forces one,
            # the same recipe tools/hw_check.py's Session.normalize()
            # already uses for the same reason.
            resp = self._send(b"\x03\r", idle=self.IDLE_S, max_total=self.CMDPROMPT_TIMEOUT_S)
            if "cmd:" not in resp:
                self.failed.emit(
                    f"TNC did not return to cmd: after leaving Host Mode: {resp!r}"
                )
                self._recover()
                return

            # 'MDCHECK\r\n' — the exact bytes hw_logs/*_maildrop*.log show
            # opening the mailbox from the top-level cmd: prompt.
            resp = self._send(b"MDCHECK\r\n", idle=self.IDLE_S, max_total=self.OPEN_TIMEOUT_S)
            info = protocol.find_prompt(resp)
            if info is None:
                self.failed.emit(f"no mailbox prompt after MDCHECK: {resp!r}")
                self._recover()
                return

            self._set_state("ACTIVE")
            self.prompt_info.emit(info)
        except Exception as exc:
            logger.exception("MailDropSession.open failed")
            self.failed.emit(str(exc))
            self._recover()

    # -- commands in ACTIVE ----------------------------------------------

    def _run_command(self, worker: Callable[[], None]) -> None:
        if self._state != "ACTIVE":
            self.failed.emit(f"mailbox is not open (state={self._state})")
            return
        if not self._claim():
            self.failed.emit("session busy")
            return
        self._start(worker)

    def list(self) -> None:
        self._run_command(self._list_worker)

    def _list_worker(self) -> None:
        try:
            # 'L' — hw_logs/*_maildrop*.log, the mailbox's own list command.
            resp = self._send(b"L\r")
            self._report_prompt(resp)
            err = protocol.parse_error(resp)
            if err is not None:
                self.failed.emit(err)
                return
            self.listing.emit(protocol.parse_list(resp))
        except Exception as exc:
            logger.exception("MailDropSession.list failed")
            self.failed.emit(str(exc))

    def read(self, number: int) -> None:
        self._run_command(lambda: self._read_worker(number))

    def _read_worker(self, number: int) -> None:
        try:
            # A space before the argument is required (CLAUDE.md: 'R2'
            # -> '*** Not enough', 'R 2' works).
            resp = self._send(f"R {number}\r".encode("ascii"))
            self._report_prompt(resp)
            err = protocol.parse_error(resp)
            if err is not None:
                self.failed.emit(err)
                return
            entry, body = protocol.parse_read(resp)
            if entry is None:
                self.failed.emit(f"could not parse message #{number}: {resp!r}")
                return
            self.message_read.emit(entry, body)
        except Exception as exc:
            logger.exception("MailDropSession.read failed")
            self.failed.emit(str(exc))

    def kill(self, number: int) -> None:
        self._run_command(lambda: self._kill_worker(number))

    def _kill_worker(self, number: int) -> None:
        try:
            # 'K <n>' — hw_logs/20260922_184337_maildrop.log ('K 1' -> '*** Done.').
            resp = self._send(f"K {number}\r".encode("ascii"))
            self._report_prompt(resp)
            if "*** Done." in resp:
                self.killed.emit(number)
                return
            err = protocol.parse_error(resp) or f"unexpected response: {resp!r}"
            self.failed.emit(err)
        except Exception as exc:
            logger.exception("MailDropSession.kill failed")
            self.failed.emit(str(exc))

    def send(
        self, to: str, bbs: str, frm: str, mtype: str, subject: str, body: str,
    ) -> None:
        self._run_command(
            lambda: self._send_worker(to, bbs, frm, mtype, subject, body)
        )

    def _send_worker(
        self, to: str, bbs: str, frm: str, mtype: str, subject: str, body: str,
    ) -> None:
        try:
            cmd = protocol.build_send_command(to, bbs, frm, mtype)
        except ValueError as exc:
            self.failed.emit(str(exc))
            return

        reasons = protocol.check_body(body)
        if reasons:
            self.failed.emit("message body rejected: " + "; ".join(reasons))
            return
        clean_body, changes = protocol.sanitize_body(body)
        if changes:
            logger.info(
                "MailDropSession.send: sanitized body (%d change(s))", len(changes)
            )

        try:
            resp = self._send((cmd + "\r").encode("ascii"))
            if protocol.classify(resp) != "subject":
                self.failed.emit(f"no Subject: prompt after {cmd!r}: {resp!r}")
                self._abort_send()
                return

            resp = self._send((subject + "\r").encode("ascii"))
            if protocol.classify(resp) != "body":
                self.failed.emit(f"no message-entry prompt after subject: {resp!r}")
                self._abort_send()
                return

            for line in (clean_body.splitlines() or [""]):
                self._send((line + "\r").encode("ascii"))

            # '/EX' — every hw_logs/*_maildrop*.log message ends its text
            # entry this way ('^Z' does NOT end a message, CLAUDE.md).
            resp = self._send(b"/EX\r", max_total=self.CMD_TIMEOUT_S)
            self._report_prompt(resp)
            m = _STORED_RE.search(resp)
            if not m:
                err = protocol.parse_error(resp) or f"no confirmation: {resp!r}"
                self.failed.emit(err)
                return
            self.stored.emit(int(m.group(1)))
        except Exception as exc:
            logger.exception("MailDropSession.send failed")
            self.failed.emit(str(exc))
            self._abort_send()

    def _abort_send(self) -> None:
        """Leave a half-finished text-entry mode safely (P27.2: a broken
        step always sends /EX before reporting failure)."""
        try:
            self._send(b"/EX\r", max_total=self.CMD_TIMEOUT_S)
        except Exception:
            logger.warning("MailDropSession: /EX abort itself failed")

    # -- leaving / recovery ------------------------------------------------

    def leave(self) -> None:
        if self._state != "ACTIVE":
            self.failed.emit(f"cannot leave: session is {self._state}")
            return
        if not self._claim():
            self.failed.emit("session busy")
            return
        self._set_state("CLOSING")
        self._start(self._leave_worker)

    def _leave_worker(self) -> None:
        try:
            # 'B' — hw_logs/*_maildrop*.log, leaves the mailbox back to cmd:.
            resp = self._send(b"B\r", max_total=self.CMD_TIMEOUT_S)
            if "cmd:" not in resp:
                self.failed.emit(f"unexpected response leaving the mailbox: {resp!r}")
                self._recover()
                return
            self._enter_host_mode_or_fail()
        except Exception as exc:
            logger.exception("MailDropSession.leave failed")
            self.failed.emit(str(exc))
            self._recover()

    def _enter_host_mode_or_fail(self) -> None:
        self._channel.enter_host_mode()
        if not self._wait_for(lambda: self._channel.is_host_mode, self.HOST_MODE_TIMEOUT_S):
            self._set_state("FAILED")
            self.failed.emit(
                "left the mailbox but could not re-enter Host Mode -- "
                "power-cycle the TNC and reconnect"
            )
            return
        self._set_state("CLOSED")

    def _recover(self) -> None:
        """The one recovery path, reachable from ACTIVE, OPENING or
        FAILED (P27.2): /EX (in case text entry is open), B, Ctrl-C+CR,
        confirm cmd:, re-enter Host Mode. Never silently reports success
        — that is the lesson from P15 (CLAUDE.md)."""
        logger.info("MailDropSession: running the recovery path")
        try:
            self._send(b"/EX\r", max_total=self.CMD_TIMEOUT_S)
        except Exception:
            logger.warning("recovery: /EX step failed", exc_info=True)
        try:
            self._send(b"B\r", max_total=self.CMD_TIMEOUT_S)
        except Exception:
            logger.warning("recovery: B step failed", exc_info=True)

        resp = ""
        try:
            resp = self._send(b"\x03\r", max_total=self.CMDPROMPT_TIMEOUT_S)
        except Exception:
            logger.warning("recovery: Ctrl-C step failed", exc_info=True)

        if "cmd:" not in resp:
            self._set_state("FAILED")
            self.failed.emit(
                "could not confirm the TNC returned to cmd: after a "
                "MailDrop error -- power-cycle the TNC and reconnect"
            )
            return

        self._enter_host_mode_or_fail()
