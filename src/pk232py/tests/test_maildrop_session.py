# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Unit tests for pk232py.maildrop.session.MailDropSession (P27.2/P27.4).

Drives the real state machine (real worker threads, real Qt signals)
against a FAKE serial channel that plays back response shapes taken from
the hw_logs/ MailDrop transcripts (22./23.09.2026) - no real port, no
SerialManager, no Qt event loop pumping beyond what QCoreApplication.
processEvents() needs to deliver a cross-thread queued signal (the same
approach tools/hw_check.py's own Session-based tests already use for the
same underlying reason: pyqtSignal.emit() from a worker thread queues
delivery until the receiver's thread processes events).

Every test instance shrinks MailDropSession's timing constants (class
attributes, not module constants - see session.py) so the real idle-gap
polling loop settles in milliseconds instead of the production 1.5s/
5-15s defaults.
"""

from __future__ import annotations

import sys
import threading
import time

from PyQt6.QtWidgets import QApplication

from pk232py.maildrop.session import MailDropSession

# A full QApplication, not a bare QCoreApplication - test_main_window_
# packet.py's own `QApplication.instance() or QApplication([])` would
# otherwise find this module's QCoreApplication already installed as
# the singleton (whichever test module python imports first) and be
# unable to upgrade it, breaking every widget-creating test that runs
# afterwards. A QApplication is a strict superset, so either order works.
_APP = QApplication.instance() or QApplication(sys.argv[:1])


def _pump_until(condition, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _APP.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return condition()


class FakeChannel:
    """Plays back a scripted request/response transcript (P27.4). No
    serial port, no Qt, no thread of its own - MailDropSession's own
    worker thread and idle-gap polling run for real against this."""

    def __init__(self, script: dict) -> None:
        self._script = dict(script)
        self._pending = bytearray()
        self._lock = threading.Lock()
        self._host_mode = True
        self.writes: list = []
        self.enter_calls = 0
        self.exit_calls = 0

    def write(self, data: bytes) -> None:
        self.writes.append(data)
        with self._lock:
            self._pending.extend(self._script.get(data, b""))

    def read_new(self) -> bytes:
        with self._lock:
            data = bytes(self._pending)
            self._pending.clear()
        return data

    def exit_host_mode(self) -> None:
        self.exit_calls += 1
        self._host_mode = False

    def enter_host_mode(self) -> None:
        self.enter_calls += 1
        self._host_mode = True

    @property
    def is_host_mode(self) -> bool:
        return self._host_mode


def _fast(session: MailDropSession) -> MailDropSession:
    """Shrink the idle/timeout class attributes on this ONE instance
    (session.py exposes them as class attributes precisely so tests can
    do this without touching the real defaults)."""
    session.IDLE_S = 0.02
    session.CMD_TIMEOUT_S = 1.0
    session.OPEN_TIMEOUT_S = 1.0
    session.CMDPROMPT_TIMEOUT_S = 1.0
    session.HOST_MODE_TIMEOUT_S = 1.0
    return session


class _Recorder:
    """Collects every emission of the signals it is connected to, in
    order, for later assertion."""

    def __init__(self) -> None:
        self.state_changes: list = []
        self.prompts: list = []
        self.listings: list = []
        self.reads: list = []
        self.stored: list = []
        self.killed: list = []
        self.failures: list = []

    def connect(self, session: MailDropSession) -> "_Recorder":
        session.state_changed.connect(self.state_changes.append)
        session.prompt_info.connect(self.prompts.append)
        session.listing.connect(self.listings.append)
        session.message_read.connect(lambda e, b: self.reads.append((e, b)))
        session.stored.connect(self.stored.append)
        session.killed.connect(self.killed.append)
        session.failed.connect(self.failures.append)
        return self


# A single, real-shaped happy-path transcript covering open -> send ->
# list -> read -> kill -> leave, built from the exact bytes
# MailDropSession sends and response shapes hw_logs/ recorded for each.
_HAPPY_SCRIPT = {
    b"\x03\r": b"\r\ncmd:cmd:",
    b"MDCHECK\r": b"MDCHECK\r\n(AEA PK-232M)  18536 free  (B,E,K,L,R,S) >\r\n",
    b"S OE3GAS\r": b"S OE3GAS\r\nSubject:\r\n",
    b"Test Subjekt\r": b"Test Subjekt\r\nEnter message, ^Z (CTRL-Z) or /EX to end\r\n\r\n",
    b"hello world\r": b"hello world\r\n",
    b"/EX\r": b"/EX\r\nMessage stored as # 1\r\n(AEA PK-232M)  18452 free  (B,E,K,L,R,S) >\r\n",
    b"L\r": (
        b"L\r\nMsg#    Size To     From   @ BBS  Date       Time   Title\r\n"
        b"  1 PN    36 OE3GAS OE3GAS        22-Sep-26  18:00  Test Subjekt\r\n"
        b"(AEA PK-232M)  18452 free  (B,E,K,L,R,S) >\r\n"
    ),
    b"R 1\r": (
        b"R 1\r\nMsg#    Size To     From   @ BBS  Date       Time   Title\r\n"
        b"  1 PN    36 OE3GAS OE3GAS        22-Sep-26  18:00  Test Subjekt\r\n"
        b"\r\nhello world\r\n\r\n"
        b"(AEA PK-232M)  18452 free  (B,E,K,L,R,S) >\r\n"
    ),
    b"K 1\r": b"K 1\r\n*** Done.\r\n(AEA PK-232M)  18536 free  (B,E,K,L,R,S) >\r\n",
    b"B\r": b"B\r\ncmd:",
}


def _can_open_yes():
    return True, ""


class TestHappyPathLifecycle:
    def test_open_list_read_send_kill_leave(self):
        channel = FakeChannel(_HAPPY_SCRIPT)
        session = _fast(MailDropSession(channel, _can_open_yes))
        rec = _Recorder().connect(session)

        session.open()
        # Waits on the SIGNAL-delivered result (rec.prompts/rec.failures),
        # not on session.state -- session.state is a plain attribute the
        # worker thread sets BEFORE its final signal emit()s and BEFORE
        # releasing its own busy flag, so polling it alone can observe
        # "done" a hair before rec.prompts/the next _claim() is actually
        # safe to rely on (found via a real flake, P36/Backlog.md).
        assert _pump_until(lambda: rec.prompts or rec.failures)
        assert session.state == "ACTIVE"
        assert rec.prompts and rec.prompts[0].free == 18536
        assert channel.exit_calls == 1

        session.send("oe3gas", "", "", "P", "Test Subjekt", "hello world")
        assert _pump_until(lambda: rec.stored)
        assert rec.stored == [1]

        session.list()
        assert _pump_until(lambda: rec.listings)
        assert len(rec.listings[0]) == 1
        assert rec.listings[0][0].title == "Test Subjekt"

        session.read(1)
        assert _pump_until(lambda: rec.reads)
        entry, body = rec.reads[0]
        assert entry.number == 1
        assert body == "hello world"

        session.kill(1)
        assert _pump_until(lambda: rec.killed)
        assert rec.killed == [1]

        session.leave()
        assert _pump_until(
            lambda: rec.state_changes and rec.state_changes[-1] in ("CLOSED", "FAILED")
        )
        assert session.state == "CLOSED"
        assert channel.enter_calls == 1

        assert rec.failures == []
        assert "ACTIVE" in rec.state_changes
        assert rec.state_changes[-1] == "CLOSED"


class TestOpenGuards:
    def test_can_open_false_never_touches_the_channel(self):
        channel = FakeChannel(_HAPPY_SCRIPT)
        session = _fast(MailDropSession(channel, lambda: (False, "channel busy")))
        rec = _Recorder().connect(session)

        session.open()
        assert _pump_until(lambda: rec.failures)
        assert rec.failures == ["channel busy"]
        assert channel.exit_calls == 0
        assert session.state == "CLOSED"

    def test_command_rejected_when_not_active(self):
        channel = FakeChannel(_HAPPY_SCRIPT)
        session = _fast(MailDropSession(channel, _can_open_yes))
        rec = _Recorder().connect(session)

        session.list()  # never opened

        assert rec.failures
        assert channel.writes == []  # no I/O happened at all


class TestSendGuards:
    def test_body_with_ex_line_never_touches_the_channel(self):
        channel = FakeChannel(_HAPPY_SCRIPT)
        session = _fast(MailDropSession(channel, _can_open_yes))
        rec = _Recorder().connect(session)

        session.open()
        assert _pump_until(lambda: rec.prompts or rec.failures)
        channel.writes.clear()

        session.send("oe3gas", "", "", "P", "subject", "line one\n/EX\nline two")
        assert _pump_until(lambda: rec.failures)
        assert channel.writes == []  # rejected before any command was sent


class TestAbortRecoversWithoutFalseSuccess:
    """P27.4: 'ein Abbruchfall, in dem der Prompt ausbleibt' - the
    recovery path runs and NO success is ever reported (P15's lesson,
    CLAUDE.md)."""

    def test_no_prompt_after_mdcheck_recovers_to_closed(self):
        script = {
            b"\x03\r": b"\r\ncmd:cmd:",
            b"MDCHECK\r": b"MDCHECK\r\n",  # no prompt at all - fault injected
            b"/EX\r": b"",
            b"B\r": b"",
        }
        channel = FakeChannel(script)
        session = _fast(MailDropSession(channel, _can_open_yes))
        rec = _Recorder().connect(session)

        session.open()
        assert _pump_until(
            lambda: rec.state_changes and rec.state_changes[-1] in ("CLOSED", "FAILED")
        )

        assert session.state == "CLOSED"          # recovery succeeded
        assert "ACTIVE" not in rec.state_changes   # never claimed success
        assert rec.prompts == []
        assert rec.listings == []
        assert rec.stored == []
        assert rec.failures                        # the failure WAS reported
        assert channel.enter_calls == 1             # Host Mode re-entered

    def test_no_prompt_and_no_cmd_ends_in_failed(self):
        script = {
            b"\x03\r": b"\r\ncmd:cmd:",
            b"MDCHECK\r": b"MDCHECK\r\n",  # no prompt - fault injected
            b"/EX\r": b"",
            b"B\r": b"",
            # Note: no b"\x03\r" -> "cmd:" response is scripted for the
            # RECOVERY's own Ctrl-C probe below - simulate a TNC that
            # never answers on ^C+CR by shadowing the module-level
            # default with an explicit empty second attempt.
        }
        channel = FakeChannel(script)
        session = _fast(MailDropSession(channel, _can_open_yes))

        # Recovery re-sends '\x03\r' too - the FIRST probe (open()'s own,
        # which must succeed so the worker proceeds to MDCHECK) gets the
        # scripted 'cmd:cmd:' answer; every probe after that gets
        # silence, simulating a TNC that never answers again.
        original_write = channel.write
        calls = {"ctrl_c": 0}

        def write_with_one_time_ctrlc(data: bytes) -> None:
            if data == b"\x03\r":
                calls["ctrl_c"] += 1
                if calls["ctrl_c"] > 1:
                    channel._script[b"\x03\r"] = b""
            original_write(data)

        channel.write = write_with_one_time_ctrlc
        rec = _Recorder().connect(session)

        session.open()
        assert _pump_until(
            lambda: rec.state_changes and rec.state_changes[-1] in ("CLOSED", "FAILED")
        )

        assert session.state == "FAILED"
        assert "ACTIVE" not in rec.state_changes
        assert channel.enter_calls == 0   # recovery never reached Host Mode
        assert rec.failures


class _NonConfirmingChannel(FakeChannel):
    """enter_host_mode() is called but never actually confirms (P31.2:
    "bleibt die Bestaetigung aus") - is_host_mode stays False forever, so
    _enter_host_mode_or_fail()'s own wait must time out and report
    FAILED, never CLOSED."""

    def enter_host_mode(self) -> None:
        self.enter_calls += 1
        # Deliberately does NOT set self._host_mode = True.


class TestRecoveryPath:
    """P31.2: the recovery path (P27.2) has six steps - /EX, B, Ctrl-C+CR,
    confirm cmd:, re-enter Host Mode, confirm THAT. All six must run, and
    the session must never report CLOSED without a confirmed Host Mode
    (P15's rule)."""

    _NO_PROMPT_SCRIPT = {
        b"\x03\r": b"\r\ncmd:cmd:",
        b"MDCHECK\r": b"MDCHECK\r\n",  # no prompt at all - triggers _recover()
        b"/EX\r": b"",
        b"B\r": b"",
    }

    def test_all_six_steps_run_and_end_in_closed(self):
        channel = FakeChannel(self._NO_PROMPT_SCRIPT)
        session = _fast(MailDropSession(channel, _can_open_yes))
        rec = _Recorder().connect(session)

        session.open()
        assert _pump_until(
            lambda: rec.state_changes and rec.state_changes[-1] in ("CLOSED", "FAILED")
        )

        # 1: open()'s own attempt (\x03\r, MDCHECK\r), then recovery's
        # own steps 1-4 (/EX, B, \x03\r again for its OWN cmd: check).
        assert channel.writes == [
            b"\x03\r", b"MDCHECK\r", b"/EX\r", b"B\r", b"\x03\r",
        ]
        assert channel.enter_calls == 1        # step 5
        assert session.state == "CLOSED"       # step 6 confirmed it
        assert "ACTIVE" not in rec.state_changes

    def test_ends_in_failed_when_host_mode_never_confirms(self):
        # P36 (Backlog.md): this test used to poll session.state alone,
        # a plain attribute the worker thread sets BEFORE emitting its
        # OWN failed() signal -- state could already read "FAILED" while
        # the earlier open() failure ("no mailbox prompt after MDCHECK")
        # was still the last thing rec.failures had seen, making
        # rec.failures[-1] flaky. Waiting on the exact content being
        # asserted removes the race by construction: this can only
        # return True once the SECOND failure has actually landed.
        channel = _NonConfirmingChannel(self._NO_PROMPT_SCRIPT)
        session = _fast(MailDropSession(channel, _can_open_yes))
        rec = _Recorder().connect(session)

        session.open()
        assert _pump_until(
            lambda: rec.failures and "verbose mode" in rec.failures[-1],
            timeout=3.0,
        )

        assert session.state == "FAILED"       # never CLOSED without proof
        assert channel.enter_calls == 1        # step 5 WAS attempted
        assert rec.failures
        assert "verbose mode" in rec.failures[-1]


class TestClaimGuardsAgainstOverlap:
    def test_second_claim_rejected_until_the_first_releases(self):
        channel = FakeChannel({})
        session = _fast(MailDropSession(channel, _can_open_yes))
        assert session._claim() is True
        assert session._claim() is False
        session._busy = False
        assert session._claim() is True


class TestTraceCallback:
    """P35.1: an optional raw trace callback -- tx before every send, rx
    after every read (even an empty one), discard when stale bytes were
    dropped before a command. Every OTHER test in this file passes no
    trace at all (the default, None) and its behaviour is unchanged
    under P35 -- that itself is evidence for the "no callback -> no
    change" half of the Definition of Done."""

    def test_tx_and_rx_traced_for_open(self):
        channel = FakeChannel(_HAPPY_SCRIPT)
        events: list = []
        session = _fast(
            MailDropSession(
                channel, _can_open_yes,
                trace=lambda kind, data: events.append((kind, data)),
            )
        )
        rec = _Recorder().connect(session)

        session.open()
        assert _pump_until(lambda: rec.prompts or rec.failures)

        assert ("tx", b"\x03\r") in events
        assert ("tx", b"MDCHECK\r") in events
        assert any(
            kind == "rx" and b"18536 free" in data for kind, data in events
        )

    def test_discard_traced_when_stale_bytes_were_pending(self):
        channel = FakeChannel(_HAPPY_SCRIPT)
        events: list = []
        session = _fast(
            MailDropSession(
                channel, _can_open_yes,
                trace=lambda kind, data: events.append((kind, data)),
            )
        )
        rec = _Recorder().connect(session)

        session.open()
        assert _pump_until(lambda: rec.prompts or rec.failures)

        # Simulate a leftover fragment still in flight from a prior
        # exchange (the P35 finding) sitting in the channel's buffer
        # right before the next command is sent.
        channel._pending.extend(b"stray leftover bytes")

        session.list()
        assert _pump_until(lambda: rec.listings or rec.failures)

        assert ("discard", b"stray leftover bytes") in events

    def test_no_trace_callback_means_no_behaviour_change(self):
        channel = FakeChannel(_HAPPY_SCRIPT)
        session = _fast(MailDropSession(channel, _can_open_yes))  # trace=None
        rec = _Recorder().connect(session)

        session.open()
        assert _pump_until(lambda: rec.prompts or rec.failures)
        assert rec.prompts and rec.prompts[0].free == 18536


class TestErrorAttributionAfterEcho:
    """P35.3: parse_error() must only look at what came after the ECHO
    of the command actually sent -- not the whole response buffer, which
    (hw_logs/20260923_204041_maildrop_session.log, P35) can contain a
    stray leftover fragment from a PRIOR command bleeding into this
    one's own read window."""

    def test_merged_buffer_error_not_attributed_to_list(self):
        # An artificially merged buffer recreating the suspected shape:
        # MDCHECK's own tail, a stray '*** What?' + reprinted prompt (the
        # orphaned-LF artifact), THEN 'L's own real echo+response, all
        # landing in ONE read window for list().
        merged = (
            b"You have mail.\r\n"
            b"(AEA PK-232M)  18340 free  (B,E,K,L,R,S) >\r\n"
            b"*** What?\r\n"
            b"(AEA PK-232M)  18340 free  (B,E,K,L,R,S) >\r\n"
            b"L\r\nMsg#    Size To     From   @ BBS  Date       Time   Title\r\n"
            b"  1 PN    36 OE3GAS OE3GAS        22-Sep-26  18:00  Test\r\n"
            b"(AEA PK-232M)  18340 free  (B,E,K,L,R,S) >\r\n"
        )
        script = dict(_HAPPY_SCRIPT)
        script[b"L\r"] = merged
        channel = FakeChannel(script)
        session = _fast(MailDropSession(channel, _can_open_yes))
        rec = _Recorder().connect(session)

        session.open()
        assert _pump_until(lambda: rec.prompts or rec.failures)

        session.list()
        assert _pump_until(lambda: rec.listings or rec.failures)

        assert rec.failures == []       # the stray '*** What?' must NOT surface
        assert len(rec.listings) == 1
        assert rec.listings[0][0].title == "Test"

    def test_missing_echo_falls_back_to_whole_response_and_logs(self, caplog):
        script = dict(_HAPPY_SCRIPT)
        # No 'L\r\n' echo anywhere in this response at all.
        script[b"L\r"] = b"*** What?\r\n(AEA PK-232M)  18340 free  (B,E,K,L,R,S) >\r\n"
        channel = FakeChannel(script)
        session = _fast(MailDropSession(channel, _can_open_yes))
        rec = _Recorder().connect(session)

        session.open()
        assert _pump_until(lambda: rec.prompts or rec.failures)

        with caplog.at_level("WARNING"):
            session.list()
            assert _pump_until(lambda: rec.failures)

        assert rec.failures == ["*** What?"]
        assert any("no echo of" in r.message for r in caplog.records)
