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
        trace: Optional[Callable[[str, bytes], None]] = None,
    ) -> None:
        """*channel* is a SerialManagerChannel (or, in tests, a fake with
        the same write()/read_new()/enter_host_mode()/exit_host_mode()/
        is_host_mode shape). *can_open* is injected so this class never
        has to know the channel model — it just asks "is now OK?" and
        gets (bool, reason).

        *trace* (P35.1), when given, is called as trace(kind, data) with
        the RAW bytes of every outgoing write ("tx"), every completed
        idle-gap read ("rx", possibly empty on a timeout), and any stale
        bytes dropped before a command is sent ("discard") — this class
        keeps no record of its own traffic otherwise, which made the
        23.09.2026 'L' -> '*** What?' finding (P35) impossible to
        diagnose from the log alone. None (the default) means no tracing
        at all — behaviour is unchanged from before P35."""
        super().__init__(parent)
        self._channel = channel
        self._can_open = can_open
        self._trace = trace
        self._state = "CLOSED"
        self._busy = False
        self._busy_lock = threading.Lock()
        self._abort_requested = threading.Event()

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
        `cmd:` and cannot be waited for that way. Traces the raw bytes
        collected as "rx" (P35.1), even if empty (a timeout with nothing
        received is itself useful evidence, not a gap to leave silent)."""
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
        raw = bytes(buf)
        if self._trace is not None:
            self._trace("rx", raw)
        return raw.decode("ascii", errors="replace")

    def _send(
        self, data: bytes, idle: Optional[float] = None, max_total: Optional[float] = None,
    ) -> str:
        # Drop anything stale before sending (P35.3) — and make it
        # visible when there WAS something: a byte still in flight from a
        # PRIOR command's own trailing response (e.g. an orphaned LF
        # processed by the mailbox as its own empty command, P35 finding)
        # landing here instead of in that command's own read window is
        # exactly the kind of gap that made 'L' -> '*** What?' impossible
        # to diagnose from the log alone.
        discarded = self._channel.read_new()
        if discarded:
            logger.info(
                "MailDropSession: discarded %d byte(s) before sending %r: %r",
                len(discarded), data, discarded,
            )
            if self._trace is not None:
                self._trace("discard", discarded)
        if self._trace is not None:
            self._trace("tx", data)
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

            # 'MDCHECK\r' (P35.2) — the TRM terminates commands with CR;
            # the '\r\n' this used to send worked on every successful
            # Device A (PACTOR, 1995) run, so this is not a retroactive
            # bugfix for that device, just alignment with the manual. On
            # Device B (MBX, 1991) the trailing LF is suspected (P35,
            # unconfirmed without the trace above) of being processed by
            # the mailbox as its own empty command line, producing a
            # stray '*** What?' that then bled into the next command's
            # response window.
            resp = self._send(b"MDCHECK\r", idle=self.IDLE_S, max_total=self.OPEN_TIMEOUT_S)
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

    def _parse_error_after_echo(self, sent: bytes, resp: str) -> Optional[str]:
        """P35.3: parse_error() returns the FIRST error line found
        anywhere in *resp* — correct only once *resp* has been narrowed
        to what came back for THIS command. Splits off *sent*'s own
        echoed line (protocol.split_after_echo()) first, so a stray
        leftover fragment sitting in front of the real echo (from a
        PRIOR command's response window bleeding into this one, the
        23.09.2026 'L' -> '*** What?' finding, P35) cannot be
        misattributed to this command. Falls back to evaluating the
        whole response — logged, not silent — if the echo cannot be
        found at all."""
        command_text = sent.decode("ascii", errors="replace").rstrip("\r\n")
        remainder, echo_found = protocol.split_after_echo(command_text, resp)
        if not echo_found:
            logger.warning(
                "MailDropSession: no echo of %r found in the response -- "
                "evaluating the whole response for an error: %r",
                command_text, resp,
            )
            return protocol.parse_error(resp)
        return protocol.parse_error(remainder)

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
            cmd = b"L\r"
            resp = self._send(cmd)
            self._report_prompt(resp)
            err = self._parse_error_after_echo(cmd, resp)
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
            cmd = f"R {number}\r".encode("ascii")
            resp = self._send(cmd)
            self._report_prompt(resp)
            err = self._parse_error_after_echo(cmd, resp)
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
            cmd = f"K {number}\r".encode("ascii")
            resp = self._send(cmd)
            self._report_prompt(resp)
            if "*** Done." in resp:
                self.killed.emit(number)
                return
            err = self._parse_error_after_echo(cmd, resp) or f"unexpected response: {resp!r}"
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

            if self._abort_requested.is_set():
                self._abort_requested.clear()
                self.failed.emit("send aborted after subject (abort() called)")
                self._abort_send()
                return

            for line in (clean_body.splitlines() or [""]):
                self._send((line + "\r").encode("ascii"))

            # '/EX' — every hw_logs/*_maildrop*.log message ends its text
            # entry this way ('^Z' does NOT end a message, CLAUDE.md).
            cmd = b"/EX\r"
            resp = self._send(cmd, max_total=self.CMD_TIMEOUT_S)
            self._report_prompt(resp)
            m = _STORED_RE.search(resp)
            if not m:
                err = self._parse_error_after_echo(cmd, resp) or f"no confirmation: {resp!r}"
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

    def abort(self) -> None:
        """Request that an in-flight send() stop as soon as it safely can
        (P28: the maildrop_session harness's --abort-test, the hardware
        probe for a failure path unit tests can only fake). Checked once,
        right after the subject is accepted and before any body line is
        sent — the earliest point a half-typed message can still be
        abandoned with a plain /EX (CLAUDE.md: /EX is the only reliable
        way to end message entry; ^Z does not). No effect on any other
        command, and no effect at all if nothing is running."""
        self._abort_requested.set()

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
        """Steps 5+6 of the recovery path (P31.2): re-enter Host Mode over
        the existing SerialManager path (step 5), then CONFIRM it before
        ever reporting CLOSED (step 6) -- is_host_mode only flips True
        once SerialManager's own Host Mode entry has actually completed
        a real round trip with the TNC (the HOST 3 handshake's HPOLL ACK,
        SERIAL_CONNECTION_STATE_MACHINE.md), so this is real evidence,
        not a hopeful flag check (P15's "no reported success without
        proof", CLAUDE.md).

        Called only after the TNC was already confirmed at a working
        cmd: prompt (leave()'s own 'B' -> cmd:, or _recover()'s Ctrl-C+CR
        -> cmd:) -- so a failure here specifically means the TNC is
        sitting in verbose mode, not that it is unresponsive."""
        self._channel.enter_host_mode()
        if not self._wait_for(lambda: self._channel.is_host_mode, self.HOST_MODE_TIMEOUT_S):
            self._set_state("FAILED")
            self.failed.emit(
                "TNC is in verbose mode -- Host Mode re-entry did not "
                "complete; reconnect the application"
            )
            return
        self._set_state("CLOSED")

    def _recover(self) -> None:
        """The one recovery path, reachable from ACTIVE, OPENING or
        FAILED (P27.2): /EX (in case text entry is open), B, Ctrl-C+CR,
        confirm cmd:, re-enter Host Mode, confirm THAT too
        (_enter_host_mode_or_fail(), steps 5+6). Never silently reports
        success — that is the lesson from P15 (CLAUDE.md)."""
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
            # The TNC did not even answer Ctrl-C+CR - unlike a failed
            # Host Mode re-entry (see _enter_host_mode_or_fail()), this
            # means the TNC itself is not responding to anything, the
            # PK-232 hang CLAUDE.md/P30 documented, not a mode mismatch.
            self._set_state("FAILED")
            self.failed.emit(
                "TNC did not respond to Ctrl-C after a MailDrop error -- "
                "it may be hung; power-cycle the TNC and reconnect"
            )
            return

        self._enter_host_mode_or_fail()
