# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Unit tests for pk232py.comm.serial_manager (P35.4, P43).

_wakeup_log_message() and the other pure classifier functions are
covered directly. TestTncStateDetectionChain (P43.4) exercises the full
_init_tnc_thread() detection chain against a fully mocked, synchronous
serial.Serial stand-in (_FakePort) - no real timing dependency, since a
canned response is queued the instant the triggering write() returns.
"""

from __future__ import annotations

import logging
import time

from PyQt6.QtCore import Qt

from pk232py.comm.constants import FRAME_HOST_OFF, FRAME_RECOVERY
from pk232py.comm.frame import build_command
from pk232py.comm.params_uploader import ParamsUploader
from pk232py.comm.serial_manager import (
    SerialManager,
    _classify_maildrop_response,
    _parse_defaults_flag,
    _parse_release,
    _parse_verbose_query_value,
    _wakeup_log_message,
)
from pk232py.config import AppConfig

# Real fixture, hw_logs/20260924_181446_maildrop_session.log (Device B,
# MBX, 01.08.1991) -- the exact 176-byte wakeup response, banner included.
_DEVICE_B_BANNER = bytes.fromhex(
    "00 00 00 00 00 0d 0a 0d 0a 0d 0a 50 4b 2d 32 33 32 4d 20 69 73 20 75 "
    "73 69 6e 67 20 64 65 66 61 75 6c 74 20 76 61 6c 75 65 73 2e 0d 0a 20 "
    "20 0d 0a 0d 0a 0d 0a 11 41 45 41 20 50 4b 2d 32 33 32 4d 20 44 61 74 "
    "61 20 43 6f 6e 74 72 6f 6c 6c 65 72 0d 0a 43 6f 70 79 72 69 67 68 74 "
    "20 28 43 29 20 31 39 38 36 2d 31 39 39 31 20 62 79 0d 0a 41 64 76 61 "
    "6e 63 65 64 20 45 6c 65 63 74 72 6f 6e 69 63 20 41 70 70 6c 69 63 61 "
    "74 69 6f 6e 73 2c 20 49 6e 63 2e 0d 0a 52 65 6c 65 61 73 65 20 30 31 "
    "2e 41 55 47 2e 39 31 0d 0a 0d 0a 63 6d 64 3a"
)


class TestWakeupLogMessage:
    def test_prompt_present_logs_info(self):
        level, message = _wakeup_log_message(b"AEA PK-232MBX Ver. 7.1\r\ncmd:")
        assert level == logging.INFO
        assert message == "TNC at cmd: prompt"

    def test_no_prompt_logs_warning_with_raw_bytes(self):
        # Real fixture, hw_logs/20260923_204041_maildrop_session.log:
        # wakeup '*' got back '*\' + CR + LF -- no 'cmd:' at all, but the
        # code used to log "TNC at cmd: prompt" regardless (P35 finding).
        resp = bytes([0x2A, 0x5C, 0x0D, 0x0A])
        level, message = _wakeup_log_message(resp)
        assert level == logging.WARNING
        assert message == (
            "wakeup answered without prompt (4 bytes) -- continuing: "
            "2a 5c 0d 0a"
        )

    def test_empty_response_logs_warning_not_a_false_prompt(self):
        level, message = _wakeup_log_message(b"")
        assert level == logging.WARNING
        assert "without prompt (0 bytes)" in message


class TestBannerProvenance:
    """P37 - firmware release date and 'using defaults' flag, both read
    straight off the boot banner (docs/PK232_firmware_matrix.md §1)."""

    def test_release_extracted_from_real_device_b_banner(self):
        assert _parse_release(_DEVICE_B_BANNER) == "01.AUG.91"

    def test_defaults_flag_true_on_real_device_b_banner(self):
        assert _parse_defaults_flag(_DEVICE_B_BANNER) is True

    def test_no_banner_captured_gives_none_not_a_guess(self):
        # P37: "nichts erfinden" - an empty banner (TNC already at cmd:
        # at connect time) must not be reported as any particular release
        # or defaults state.
        assert _parse_release(b"") is None
        assert _parse_defaults_flag(b"") is None

    def test_defaults_flag_false_when_banner_lacks_the_phrase(self):
        banner = b"AEA PK-232 ...\r\nRelease 11.SEP.95\r\n\r\ncmd:"
        assert _parse_release(banner) == "11.SEP.95"
        assert _parse_defaults_flag(banner) is False


class TestClassifyMaildropResponse:
    """P37 Teil D - MailDrop capability detection via a verbose-mode
    'MAILDROP' query, never MDCHECK."""

    def test_on_answers_true(self):
        assert _classify_maildrop_response(
            "MAILDROP\r\nMAildrop  ON\r\ncmd:"
        ) is True

    def test_off_still_answers_true_the_command_exists(self):
        assert _classify_maildrop_response(
            "MAILDROP\r\nMAildrop  OFF\r\ncmd:"
        ) is True

    def test_what_error_answers_false(self):
        assert _classify_maildrop_response(
            "MAILDROP\r\n?What?\r\ncmd:"
        ) is False

    def test_empty_or_garbled_answers_none_not_a_guess(self):
        assert _classify_maildrop_response("") is None
        assert _classify_maildrop_response("cmd:") is None


class TestParseVerboseQueryValue:
    """P40.3 - upload-verification queries (MYCALL/PACLEN/MAXFRAME),
    same '<echo>\\r\\n<Name mixed-case> <value>\\r\\ncmd:' format
    confirmed by P15 for parse_query_value()-style responses."""

    def test_extracts_the_value_skipping_the_echo(self):
        assert _parse_verbose_query_value(
            "MYCALL", "MYCALL\r\nMYcall    OE3GAS\r\ncmd:"
        ) == "OE3GAS"

    def test_numeric_value(self):
        assert _parse_verbose_query_value(
            "PACLEN", "PACLEN\r\nPAclen    128\r\ncmd:"
        ) == "128"

    def test_what_error_answers_none(self):
        assert _parse_verbose_query_value(
            "MAXFRAME", "MAXFRAME\r\n?What?\r\ncmd:"
        ) is None

    def test_empty_or_garbled_answers_none_not_a_guess(self):
        assert _parse_verbose_query_value("MYCALL", "") is None
        assert _parse_verbose_query_value("MYCALL", "cmd:") is None

    def test_only_the_echo_with_no_answer_line_is_none(self):
        # The echo alone (token == name.upper() exactly) must never be
        # mistaken for the TNC's own answer line.
        assert _parse_verbose_query_value("MYCALL", "MYCALL\r\ncmd:") is None


_HPOLL_QUERY  = build_command(b'HP')  # SOH $4F H P ETB - step 3's stimulus
_HPOLL_ANSWER = bytes([0x01, 0x4F, ord('H'), ord('P'), ord('Y'), 0x17])


class _FakePort:
    """Duck-typed stand-in for serial.Serial - synchronous and in-memory.
    A canned response is queued the instant the triggering write() call
    returns, so the real polling loops in _init_tnc_thread() pick it up
    on their very first pass; no test needs to sleep for real hardware
    timing. *responder(data) -> bytes* decides what (if anything) comes
    back for each write."""

    def __init__(self, responder):
        self._responder = responder
        self._buf = bytearray()
        self.port = "COM_TEST"
        self.baudrate = 9600
        self.writes: list[bytes] = []
        self.is_open = True

    def write(self, data: bytes) -> int:
        self.writes.append(bytes(data))
        self._buf.extend(self._responder(bytes(data)))
        return len(data)

    def flush(self) -> None:
        pass

    def reset_input_buffer(self) -> None:
        self._buf.clear()

    @property
    def in_waiting(self) -> int:
        return len(self._buf)

    def read(self, n: int = 1) -> bytes:
        if not self._buf:
            time.sleep(0.001)  # never a tight busy-loop in _ReaderThread
            return b""
        n = min(n, len(self._buf))
        data = bytes(self._buf[:n])
        del self._buf[:n]
        return data

    def open(self) -> None:
        self.is_open = True

    def close(self) -> None:
        self.is_open = False


def _run_detection(responder) -> tuple[SerialManager, _FakePort, list[str]]:
    """Build a SerialManager wired to a _FakePort(responder), run the
    P43.1 detection chain synchronously (never via the real init_tnc()
    background thread - deterministic for a test), and clean up any
    _ReaderThread it started."""
    sm = SerialManager()
    port = _FakePort(responder)
    sm._serial = port
    messages: list[str] = []
    sm.status_message.connect(messages.append)
    try:
        sm._init_tnc_thread()
    finally:
        if sm._reader:
            sm._reader.stop()
            sm._reader.join(timeout=1.0)
    return sm, port, messages


class TestTncStateDetectionChain:
    """P43.4/P44.D - one case per branch of the four-step (now five-step,
    with P44's 3b recovery stage) chain, against _FakePort. is_host_mode
    alone (the software's own belief) cannot catch a TNC left in Host
    Mode from a previous session on a fresh SerialManager instance - only
    actively asking (steps 1-3) can."""

    def test_step1_banner_and_cmd_confirms_verbose(self):
        def responder(data):
            if data == b"*":
                return b"AEA PK-232MBX Ver. 7.1\r\ncmd:"
            return b""

        sm, port, _messages = _run_detection(responder)

        assert sm.verbose_confirmed is True
        assert sm.is_host_mode is False
        assert port.writes == [b"*"]  # no CR, no HPOLL query needed

    def test_step2_cr_confirms_verbose_when_star_is_silent(self):
        def responder(data):
            if data == b"\r":
                return b"\r\ncmd:"
            return b""  # '*' unanswered

        sm, port, _messages = _run_detection(responder)

        assert sm.verbose_confirmed is True
        assert sm.is_host_mode is False
        assert port.writes == [b"*", b"\r"]
        assert _HPOLL_QUERY not in port.writes

    def test_step3_hpoll_frame_confirms_host_mode_then_exits_to_verbose(self):
        cr_count = {"n": 0}

        def responder(data):
            if data == _HPOLL_QUERY:
                return _HPOLL_ANSWER
            if data == b"\r":
                cr_count["n"] += 1
                if cr_count["n"] >= 2:  # only the retry AFTER the exit answers
                    return b"\r\ncmd:"
                return b""
            return b""  # '*' unanswered, FRAME_HOST_OFF gets no reply

        sm, port, _messages = _run_detection(responder)

        assert sm.verbose_confirmed is True
        assert sm.is_host_mode is False
        assert _HPOLL_QUERY in port.writes
        assert FRAME_HOST_OFF in port.writes
        assert port.writes.count(b"\r") == 2

    def test_step3b_recovery_sequence_confirms_verbose_after_half_frame_hang(self):
        # P44.C1 - the HPOLL query itself gets NOTHING back (the scenario
        # observed 25.09.2026 after killing the app mid-frame in Host
        # Mode: the TNC's own frame parser is stuck waiting for an ETB
        # and discards everything further, including a fresh SOH), but
        # the recovery sequence (double-SOH + GG, then HOST OFF) reaches
        # it and a repeated CR confirms verbose mode afterwards.
        cr_count = {"n": 0}

        def responder(data):
            if data == b"\r":
                cr_count["n"] += 1
                if cr_count["n"] >= 2:  # only the retry AFTER recovery answers
                    return b"\r\ncmd:"
                return b""
            return b""  # '*', the HPOLL query, and both recovery frames unanswered

        sm, port, _messages = _run_detection(responder)

        assert sm.verbose_confirmed is True
        assert sm.is_host_mode is False
        assert _HPOLL_QUERY in port.writes       # step 3 was tried first
        assert FRAME_RECOVERY in port.writes      # step 3b's own frame
        assert FRAME_HOST_OFF in port.writes      # part of the recovery sequence
        assert port.writes.count(b"\r") == 2

    def test_all_three_silent_aborts_and_sends_nothing_to_the_uploader(self):
        def responder(_data):
            return b""

        sm, port, messages = _run_detection(responder)

        assert sm.verbose_confirmed is False
        assert any("COM_TEST" in m and "9600" in m for m in messages)
        # The recovery stage (3b) must still have been attempted before
        # giving up - not skipped straight to step 4.
        assert FRAME_RECOVERY in port.writes

        # DoD: the abort must also stop ParamsUploader from ever sending
        # a single parameter - not just fail the detection itself.
        uploader = ParamsUploader(serial=sm, config=AppConfig())
        sent = uploader.upload()
        assert sent == 0

    def test_hpoll_answers_but_exit_does_not_reach_cmd_aborts(self):
        def responder(data):
            if data == _HPOLL_QUERY:
                return _HPOLL_ANSWER
            return b""  # every CR, including the post-exit retry, silent

        sm, _port, messages = _run_detection(responder)

        assert sm.verbose_confirmed is False
        assert any("COM_TEST" in m and "9600" in m for m in messages)


def _run_recovery(responder) -> "tuple[SerialManager, _FakePort, list[tuple[bool, str]]]":
    """Build a SerialManager wired to a _FakePort(responder) and run
    recovery() synchronously (_recovery_thread() directly, never via the
    real background-thread spawn recovery() itself uses) - deterministic
    for a test, same pattern as _run_detection() above."""
    sm = SerialManager()
    port = _FakePort(responder)
    sm._serial = port
    results: list[tuple[bool, str]] = []
    sm.recovery_finished.connect(lambda ok, msg: results.append((ok, msg)))
    try:
        sm._recovery_thread()
    finally:
        if sm._reader:
            sm._reader.stop()
            sm._reader.join(timeout=1.0)
    return sm, port, results


class TestRecoverySequence:
    """P45.1/P45.3 - recovery() sends the documented sequence, then
    determines and reports the resulting state via the EXISTING P43/P44
    detection chain (no second version of it)."""

    def test_cmd_confirmed_reports_success(self):
        # The recovery bytes themselves get no direct reply, but the
        # chain's own step 1 ('*') sees cmd: right away afterwards.
        def responder(data):
            if data == b"*":
                return b"cmd:"
            return b""

        sm, port, results = _run_recovery(responder)

        assert sm.verbose_confirmed is True
        assert len(results) == 1
        success, msg = results[0]
        assert success is True
        assert "Connection recovered" in msg
        assert FRAME_RECOVERY in port.writes
        assert FRAME_HOST_OFF in port.writes

    def test_only_hpoll_answers_still_reports_success_after_exit(self):
        cr_count = {"n": 0}

        def responder(data):
            if data == _HPOLL_QUERY:
                return _HPOLL_ANSWER
            if data == b"\r":
                cr_count["n"] += 1
                if cr_count["n"] >= 2:  # only the retry after the exit answers
                    return b"\r\ncmd:"
                return b""
            return b""  # '*' and both HOST_OFF writes get no direct reply

        sm, port, results = _run_recovery(responder)

        assert sm.verbose_confirmed is True
        success, msg = results[0]
        assert success is True
        assert "Connection recovered" in msg
        assert _HPOLL_QUERY in port.writes

    def test_silence_throughout_reports_failure_and_power_cycle_hint(self):
        def responder(_data):
            return b""

        sm, port, results = _run_recovery(responder)

        assert sm.verbose_confirmed is False
        success, msg = results[0]
        assert success is False
        assert "power-cycle" in msg.lower()
        assert FRAME_RECOVERY in port.writes


class _StubReader:
    """Records stop()/join() without any real thread - lets a test assert
    ordering (was the reader stopped BEFORE a given write?) without racing
    a genuine background thread (P46.A.1)."""

    def __init__(self):
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True

    def join(self, timeout=None) -> None:
        pass


class TestRecoveryTakesOverTheReadPath:
    """P46.A.1/A.2 - reproduces the 25.09.2026 screenshot bug
    ("_OGG__OHONO[SYS] Recovery did not reach the TNC.") at the unit
    level: _recovery_thread() used to write its own FRAME_RECOVERY/
    FRAME_HOST_OFF preamble via _write_raw() while a ReaderThread was
    still running, so the TNC's response was consumed there (dumped into
    the RX window as raw framed bytes) instead of being visible to the
    chain's own direct reads. The fix (_take_over_read_path(), shared by
    _init_tnc_thread() and _recovery_thread()) must stop the reader
    BEFORE the very first byte goes out - not just before the chain's own
    steps."""

    def test_no_write_happens_while_the_reader_is_still_running(self):
        def responder(data):
            if data == b"*":
                return b"cmd:"
            return b""

        sm = SerialManager()
        port = _FakePort(responder)
        sm._serial = port
        stub = _StubReader()
        sm._reader = stub

        write_log: list[tuple[bytes, bool]] = []
        orig_write = port.write

        def spy_write(data):
            write_log.append((bytes(data), stub.stopped))
            return orig_write(data)

        port.write = spy_write

        results: list[tuple[bool, str]] = []
        sm.recovery_finished.connect(lambda ok, msg: results.append((ok, msg)))
        try:
            sm._recovery_thread()
        finally:
            if sm._reader:
                sm._reader.stop()
                sm._reader.join(timeout=1.0)

        assert write_log, "expected at least one write during recovery"
        assert all(stopped for _data, stopped in write_log), (
            "a write happened before the ReaderThread was stopped - "
            "exactly the ordering bug the screenshot showed"
        )
        assert stub.stopped is True
        assert results and results[0][0] is True

    def test_raw_data_received_never_fires_during_recovery(self):
        # P46.A.2 - with a REAL ReaderThread running at the start (the
        # ordinary case), no recovery-phase byte may ever reach the RX
        # window via raw_data_received - it must all go through the
        # chain's own direct reads instead.
        from pk232py.comm.serial_manager import _ReaderThread

        def responder(data):
            if data == b"*":
                return b"cmd:"
            return b""

        sm = SerialManager()
        port = _FakePort(responder)
        sm._serial = port
        raw_events: list[bytes] = []
        # DirectConnection: raw_data_received is emitted from the
        # ReaderThread's own background thread, and this process has no
        # running Qt event loop to ever deliver a queued connection -
        # without this, the assertion below would pass trivially (an
        # undelivered signal looks identical to "never emitted").
        sm.raw_data_received.connect(raw_events.append, Qt.ConnectionType.DirectConnection)

        sm._reader = _ReaderThread(
            port, sm._on_frame_received, raw_callback=sm._on_raw_data,
            host_mode_flag=lambda: sm._in_host_mode,
        )
        sm._reader.start()
        try:
            sm._recovery_thread()
        finally:
            if sm._reader:
                sm._reader.stop()
                sm._reader.join(timeout=1.0)

        assert sm.verbose_confirmed is True
        assert raw_events == []


class TestRecoveryEmergencyReconnect:
    """P46.B - Recovery is the emergency reconnect: it must work with NO
    connection at all, opening the port itself from the caller's saved
    config (port_name/baudrate) before running the same chain."""

    def test_opens_the_port_when_not_connected(self):
        def responder(data):
            if data == b"*":
                return b"cmd:"
            return b""

        opened: dict = {}

        def factory(**kwargs):
            opened.update(kwargs)
            return _FakePort(responder)

        sm = SerialManager()
        sm.set_port_factory(factory)
        assert sm.is_connected is False

        results: list[tuple[bool, str]] = []
        # DirectConnection: recovery() runs its detection chain on a real
        # background thread here (unlike _run_recovery()'s synchronous
        # call elsewhere in this file) - without this, the signal would
        # be silently queued forever, since nothing in this test process
        # runs a Qt event loop to deliver it.
        sm.recovery_finished.connect(
            lambda ok, msg: results.append((ok, msg)),
            Qt.ConnectionType.DirectConnection,
        )
        try:
            ok = sm.recovery(port_name="COM_TEST", baudrate=9600)
            assert ok is True
            assert sm.is_connected is True
            assert opened.get("port") == "COM_TEST"
            assert opened.get("baudrate") == 9600

            deadline = time.monotonic() + 2.0
            while not results and time.monotonic() < deadline:
                time.sleep(0.01)

            assert results, "recovery_finished never fired"
            success, msg = results[0]
            assert success is True
            assert "Connection recovered" in msg
            assert sm.verbose_confirmed is True
        finally:
            if sm._reader:
                sm._reader.stop()
                sm._reader.join(timeout=1.0)

    def test_no_port_and_nothing_configured_does_nothing(self):
        sm = SerialManager()
        assert sm.is_connected is False
        assert sm.recovery() is False
