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
import threading
import time

from PyQt6.QtCore import Qt

from pk232py.comm.constants import FRAME_HOST_OFF, FRAME_RECOVERY
from pk232py.comm.frame import build_command
from pk232py.comm.params_uploader import ParamsUploader
from pk232py.comm.serial_manager import (
    SerialManager,
    _ReaderThread,
    _classify_maildrop_response,
    _parse_defaults_flag,
    _parse_release,
    _parse_verbose_query_value,
    _read_until_prompt,
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

    def reset_output_buffer(self) -> None:
        pass

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
        # P54: gated on the HPOLL query having been sent (not a bare CR
        # count) - step 2c now sends its own CRs before step 3 ever
        # runs, so only a CR sent AFTER the HPOLL query may succeed
        # here, isolating step 3's own post-exit retry specifically.
        hpoll_sent = {"yes": False}

        def responder(data):
            if data == _HPOLL_QUERY:
                hpoll_sent["yes"] = True
                return _HPOLL_ANSWER
            if data == b"\r":
                return b"\r\ncmd:" if hpoll_sent["yes"] else b""
            return b""  # '*' unanswered, FRAME_HOST_OFF gets no reply

        sm, port, _messages = _run_detection(responder)

        assert sm.verbose_confirmed is True
        assert sm.is_host_mode is False
        assert _HPOLL_QUERY in port.writes
        assert FRAME_HOST_OFF in port.writes

    def test_step3b_recovery_sequence_confirms_verbose_after_half_frame_hang(self):
        # P44.C1 - the HPOLL query itself gets NOTHING back (the scenario
        # observed 25.09.2026 after killing the app mid-frame in Host
        # Mode: the TNC's own frame parser is stuck waiting for an ETB
        # and discards everything further, including a fresh SOH), but
        # the recovery sequence (double-SOH + GG, then HOST OFF) reaches
        # it and a repeated CR confirms verbose mode afterwards.
        # P54: gated on FRAME_RECOVERY having been sent (not a bare CR
        # count) - step 2c now sends its own CRs before step 3/3b ever
        # run, so only a CR sent AFTER the recovery sequence may
        # succeed here.
        recovery_sent = {"yes": False}

        def responder(data):
            if data == FRAME_RECOVERY:
                recovery_sent["yes"] = True
                return b""
            if data == b"\r":
                return b"\r\ncmd:" if recovery_sent["yes"] else b""
            return b""  # '*', the HPOLL query, and both recovery frames unanswered

        sm, port, _messages = _run_detection(responder)

        assert sm.verbose_confirmed is True
        assert sm.is_host_mode is False
        assert _HPOLL_QUERY in port.writes       # step 3 was tried first
        assert FRAME_RECOVERY in port.writes      # step 3b's own frame
        assert FRAME_HOST_OFF in port.writes      # part of the recovery sequence

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
        # P54: gated on the HPOLL query (not a bare CR count) - see the
        # equivalent fix in TestTncStateDetectionChain for why.
        hpoll_sent = {"yes": False}

        def responder(data):
            if data == _HPOLL_QUERY:
                hpoll_sent["yes"] = True
                return _HPOLL_ANSWER
            if data == b"\r":
                return b"\r\ncmd:" if hpoll_sent["yes"] else b""
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


def _run_again(sm: SerialManager, responder, recovery: bool = False) -> "_FakePort":
    """Re-run the detection chain (or recovery) on an EXISTING
    SerialManager instance with a fresh _FakePort - simulates a LATER
    reconnect/recovery in the same process (P59.A: proving
    fresh_boot_defaults resets every run while tnc_defaults/tnc_release/
    has_pactor stay sticky, B.3)."""
    if sm._reader:
        sm._reader.stop()
        sm._reader.join(timeout=1.0)
        sm._reader = None
    port = _FakePort(responder)
    sm._serial = port
    try:
        if recovery:
            sm._recovery_thread()
        else:
            sm._init_tnc_thread()
    finally:
        if sm._reader:
            sm._reader.stop()
            sm._reader.join(timeout=1.0)
    return port


class TestFreshBootDefaults:
    """P59.A - fresh_boot_defaults is an EVENT flag (reset at the start
    of every _init_tnc_thread()/_recovery_thread() run), never the
    sticky tnc_defaults STATE flag it is derived from - the whole point
    being that a restore trigger checking it can never fire twice for
    the same power-on, and never fires at all for a later reconnect/
    recovery against a TNC that has been running fine the whole time."""

    def test_true_after_init_with_defaults_banner(self):
        def responder(data):
            if data == b"*":
                return _DEVICE_B_BANNER
            return b""

        sm, _port, _messages = _run_detection(responder)

        assert sm.fresh_boot_defaults is True
        assert sm.tnc_defaults is True

    def test_false_after_a_later_init_with_no_banner_state_stays_sticky(self):
        def responder1(data):
            if data == b"*":
                return _DEVICE_B_BANNER
            return b""

        sm, _port, _m = _run_detection(responder1)
        assert sm.fresh_boot_defaults is True

        # A later reconnect on the SAME instance: the TNC is already
        # awake, answers a bare CR with cmd:, no banner at all this time.
        def responder2(data):
            if data == b"\r":
                return b"\r\ncmd:"
            return b""

        _run_again(sm, responder2)

        assert sm.fresh_boot_defaults is False   # B.3: the event resets
        assert sm.tnc_defaults is True            # B.3: the state is sticky

    def test_banner_without_defaults_phrase_is_false(self):
        def responder(data):
            if data == b"*":
                return b"AEA PK-232 ...\r\nRelease 11.SEP.95\r\n\r\ncmd:"
            return b""

        sm, _port, _m = _run_detection(responder)

        assert sm.fresh_boot_defaults is False
        assert sm.tnc_defaults is False

    def test_no_banner_at_all_is_false(self):
        def responder(data):
            if data == b"\r":
                return b"\r\ncmd:"
            return b""

        sm, _port, _m = _run_detection(responder)

        assert sm.fresh_boot_defaults is False
        assert sm.tnc_defaults is None

    def test_recovery_resets_the_flag_too(self):
        def responder1(data):
            if data == b"*":
                return _DEVICE_B_BANNER
            return b""

        sm, _port, _m = _run_detection(responder1)
        assert sm.fresh_boot_defaults is True

        # Recovery afterwards gets no banner at all - the flag must not
        # still read True from the earlier init just because tnc_defaults
        # itself (sticky) still does.
        def responder2(data):
            if data == b"*":
                return b"cmd:"
            return b""

        _run_again(sm, responder2, recovery=True)

        assert sm.fresh_boot_defaults is False
        assert sm.tnc_defaults is True


class TestConsumeFreshBootDefaults:
    """P60, A.1 - consume_fresh_boot_defaults() reads fresh_boot_defaults
    and clears it in one step, so a later host_mode_changed(True) in the
    same power cycle (leaving a MailDrop session, "Enter Host Mode" from
    the menu - neither of which runs _init_tnc_thread() again) reads
    False instead of re-arming an automatic archive restore (P60,
    B.1)."""

    def test_true_once_then_false_but_tnc_defaults_stays_sticky(self):
        def responder(data):
            if data == b"*":
                return _DEVICE_B_BANNER
            return b""

        sm, _port, _m = _run_detection(responder)

        assert sm.consume_fresh_boot_defaults() is True
        assert sm.consume_fresh_boot_defaults() is False
        assert sm.tnc_defaults is True   # sticky state, untouched by consume

    def test_true_again_after_a_new_init_with_a_fresh_banner(self):
        def responder(data):
            if data == b"*":
                return _DEVICE_B_BANNER
            return b""

        sm, _port, _m = _run_detection(responder)
        assert sm.consume_fresh_boot_defaults() is True

        _run_again(sm, responder)   # a genuinely new power-on/init run

        assert sm.consume_fresh_boot_defaults() is True


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


class TestReadUntilPrompt:
    """P52.1/P52.4 - _read_until_prompt() tested directly, with a plain
    read_more() stand-in - no port or threading needed, since the
    function's whole job is the marker/idle/timeout state machine, not
    how bytes actually arrive."""

    def test_response_split_across_two_chunks_from_real_capture(self):
        # Real bytes, hw capture 25.09.2026 23:30:43 (step 1, the
        # successful 23.09.2026 run at the same point): '*\' CRLF
        # arrives first, 'cmd:' a moment later - two chunks, one marker.
        chunks = [bytes.fromhex("2a 5c 0d 0a"), bytes.fromhex("63 6d 64 3a")]

        def read_more(_max_wait):
            if chunks:
                return chunks.pop(0)
            return b""

        data, found = _read_until_prompt(
            read_more, b"cmd:", timeout=1.0, idle_after_marker=0.02
        )

        assert found is True
        assert data == bytes.fromhex("2a 5c 0d 0a 63 6d 64 3a")

    def test_marker_never_appears_exhausts_the_full_timeout(self):
        def read_more(_max_wait):
            return b""

        start = time.monotonic()
        data, found = _read_until_prompt(read_more, b"cmd:", timeout=0.15)
        elapsed = time.monotonic() - start

        assert found is False
        assert data == b""
        assert elapsed >= 0.15

    def test_full_timeout_honoured_despite_a_pause_after_partial_data(self):
        # P52.1 regression, modelling Fehler 2 exactly: a first chunk
        # arrives (no match yet), then a pause with NO new data at all
        # for longer than the old bug's re-armed 0.15s per-chunk deadline
        # (the 25.09.2026 capture: step 1 returned after 184 ms with only
        # 4 of the expected 8 bytes - 'cmd:' was still in transit). Only
        # honouring the caller's FULL timeout - not one silently re-armed
        # by the first chunk's own arrival - can still catch the marker
        # once it shows up after the pause. Manually reverting P52.1's
        # fix (re-adding "deadline = now + 0.15" on every chunk) makes
        # this fail - cross-checked during implementation.
        calls = {"n": 0}
        sent_marker = {"yes": False}
        start = time.monotonic()

        def read_more(max_wait):
            calls["n"] += 1
            if calls["n"] == 1:
                return bytes.fromhex("2a 5c 0d 0a")  # first chunk, no match
            if sent_marker["yes"] or time.monotonic() - start < 0.25:
                time.sleep(max_wait)  # pause - longer than the old shrunk deadline
                return b""
            sent_marker["yes"] = True
            return bytes.fromhex("63 6d 64 3a")  # 'cmd:' finally arrives, once

        data, found = _read_until_prompt(
            read_more, b"cmd:", timeout=1.0, idle_after_marker=0.02
        )

        assert found is True
        assert data == bytes.fromhex("2a 5c 0d 0a 63 6d 64 3a")

    def test_predicate_marker_rejects_echo_containing_cmd_substring(self):
        # write_verbose_wait()'s own stricter rule (SerialManager.
        # _is_cmd_prompt): 'cmd:' only counts at buffer start or right
        # after a newline - not a bare substring match, which would also
        # fire on an echoed command that happens to spell "cmd:" inside
        # itself with no newline in front of it.
        def predicate(buf: bytes) -> bool:
            return buf.startswith(b"cmd:") or b"\ncmd:" in buf

        assert (
            _read_until_prompt(
                lambda _w: b"MYCALL\r\ncmd:", predicate, timeout=0.5,
                idle_after_marker=0.02,
            )[1]
            is True
        )

        chunks = [b"somecmd:notreal", b""]

        def read_more(_max_wait):
            if chunks:
                return chunks.pop(0)
            return b""

        data, found = _read_until_prompt(
            read_more, predicate, timeout=0.15, idle_after_marker=0.02
        )
        assert found is False
        assert data == b"somecmd:notreal"


class _DelayedPort:
    """Like _FakePort, but a write()'s response only becomes readable
    after a real elapsed delay - for testing write_verbose_wait()/
    query_verbose_value() against a genuinely staggered response instead
    of one queued instantly (P52.4). *responder(data)* returns a list of
    (delay_seconds, chunk) pairs to schedule."""

    def __init__(self, responder):
        self._responder = responder
        self._pending: list[tuple[float, bytes]] = []
        self.port = "COM_TEST"
        self.baudrate = 9600
        self.writes: list[bytes] = []
        self.is_open = True

    def write(self, data: bytes) -> int:
        self.writes.append(bytes(data))
        now = time.monotonic()
        for delay, chunk in self._responder(bytes(data)):
            self._pending.append((now + delay, chunk))
        return len(data)

    def flush(self) -> None:
        pass

    def reset_input_buffer(self) -> None:
        self._pending.clear()

    @property
    def in_waiting(self) -> int:
        now = time.monotonic()
        return sum(len(c) for t, c in self._pending if t <= now)

    def read(self, n: int = 1) -> bytes:
        now = time.monotonic()
        for i, (t, chunk) in enumerate(self._pending):
            if t <= now:
                self._pending.pop(i)
                return chunk
        time.sleep(0.005)
        return b""

    def open(self) -> None:
        self.is_open = True

    def close(self) -> None:
        self.is_open = False


class TestWriteVerboseWaitTiming:
    """P52.1/P52.4 - write_verbose_wait() against a real _ReaderThread and
    a response delayed well past the old per-iteration deadline, using
    the exact upload-verification example from the spec: 'MYcall
    OE3GAS' arriving ~400 ms after the query. query_verbose_value()'s
    own text extraction is exercised separately and directly by
    TestParseVerboseQueryValue - it depends on raw_data_received, a Qt
    signal queued cross-thread from the reader thread to whichever
    thread owns the SerialManager, which needs a live Qt event loop to
    ever get delivered (true in the real app, not in a plain synchronous
    test); write_verbose_wait()'s own boolean result does not, since it
    reads straight off _rx_buf under a lock/Event, so it is what is
    tested here against real elapsed time."""

    def test_delayed_cmd_prompt_is_still_found_within_the_timeout(self):
        def responder(data):
            if data == b"MYCALL\r\n":
                return [(0.4, b"MYCALL\r\nMYcall    OE3GAS\r\ncmd:")]
            return []

        sm = SerialManager()
        port = _DelayedPort(responder)
        sm._serial = port
        sm._reader = _ReaderThread(
            port, sm._on_frame_received, raw_callback=sm._on_raw_data,
            host_mode_flag=lambda: sm._in_host_mode,
        )
        sm._reader.start()
        try:
            start = time.monotonic()
            ok = sm.write_verbose_wait(b"MYCALL\r\n", timeout=1.0)
            elapsed = time.monotonic() - start
        finally:
            sm._reader.stop()
            sm._reader.join(timeout=1.0)

        assert ok is True
        # Found shortly after the 0.4 s delay (plus the _IDLE_S idle
        # confirmation) - not by exhausting the full 1.0 s budget.
        assert elapsed < 0.9

    def test_answer_that_never_comes_exhausts_the_timeout_and_fails(self):
        def responder(_data):
            return []

        sm = SerialManager()
        port = _DelayedPort(responder)
        sm._serial = port
        sm._reader = _ReaderThread(
            port, sm._on_frame_received, raw_callback=sm._on_raw_data,
            host_mode_flag=lambda: sm._in_host_mode,
        )
        sm._reader.start()
        try:
            ok = sm.write_verbose_wait(b"MYCALL\r\n", timeout=0.2)
        finally:
            sm._reader.stop()
            sm._reader.join(timeout=1.0)

        assert ok is False


class TestStep3EchoDetection:
    """P52.2/P52.4 - the detection chain's step 3 must not mistake the
    verbose-mode echo of its own HPOLL query for a genuine Host Mode
    answer. Real bytes, hw capture 25.09.2026 23:30:43: query
    '01 4f 48 50 17' (5 B, no value byte) answered with the identical
    5 bytes right back - an echo, not the 6-byte '01 4f 48 50 00 17'
    form a real answer carries (same capture, 23:30:09)."""

    def test_echo_of_own_query_falls_through_to_recovery_not_host_mode_exit(self):
        # Crafted so the two interpretations diverge in outcome, not just
        # in a log line: if the echo were mistaken for a genuine answer,
        # the chain takes the Host-Mode-exit branch and never sends
        # FRAME_RECOVERY at all - the post-exit CR (answered only once
        # recovery has actually been sent, per this responder) then gets
        # no reply, and the whole chain aborts at step 4 ("No PK-232
        # responding"). With the echo correctly rejected, the chain falls
        # through to step 3b, sends FRAME_RECOVERY, and the following CR
        # succeeds.
        recovery_sent = {"yes": False}

        def responder(data):
            if data == FRAME_RECOVERY:
                recovery_sent["yes"] = True
                return b""
            if data == _HPOLL_QUERY:
                return _HPOLL_QUERY  # byte-identical echo, no value byte
            if data == b"\r":
                return b"\r\ncmd:" if recovery_sent["yes"] else b""
            return b""

        sm, port, messages = _run_detection(responder)

        assert sm.verbose_confirmed is True
        assert sm.is_host_mode is False
        assert FRAME_RECOVERY in port.writes
        assert not any("No PK-232 responding" in m for m in messages)

    def test_genuine_six_byte_answer_with_value_byte_is_host_mode(self):
        # Not a new behaviour (the existing test3_hpoll_frame... case
        # already covers a 6-byte answer with value 'Y') - kept here
        # alongside the echo test, value byte $00 as in the capture's
        # own genuine-answer example, so both P52.4 examples from the
        # spec live next to each other.
        # P54: gated on the HPOLL query (not a bare CR count) - see the
        # equivalent fix in TestTncStateDetectionChain for why.
        hpoll_sent = {"yes": False}
        genuine_answer = bytes([0x01, 0x4F, ord('H'), ord('P'), 0x00, 0x17])

        def responder(data):
            if data == _HPOLL_QUERY:
                hpoll_sent["yes"] = True
                return genuine_answer
            if data == b"\r":
                return b"\r\ncmd:" if hpoll_sent["yes"] else b""
            return b""

        sm, port, _messages = _run_detection(responder)

        assert sm.verbose_confirmed is True
        assert sm.is_host_mode is False
        assert FRAME_HOST_OFF in port.writes
        assert FRAME_RECOVERY not in port.writes


class TestParamsUploaderVerifyEcho:
    """P52.3 - verify()'s failures (no answer / mismatch) must also reach
    the verbose terminal via echo_callback, not just the log."""

    def test_no_answer_is_echoed_in_red(self):
        from pk232py.config import AppConfig

        echoed: list[tuple[str, str]] = []

        class _StubSerial:
            verbose_confirmed = True
            is_host_mode = False
            has_pactor = True

            @staticmethod
            def query_verbose_value(name, timeout=3.0):
                return None

        config = AppConfig()
        config.hf_packet.mycall = "OE3GAS"
        uploader = ParamsUploader(
            serial=_StubSerial(), config=config,
            echo_callback=lambda text, color: echoed.append((text, color)),
        )

        matched, applicable = uploader.verify()

        assert matched == 0
        assert applicable == 3
        assert echoed, "verify() must echo the no-answer case to the terminal"
        assert all(color == "#f44747" for _text, color in echoed)
        assert any("MYCALL" in text for text, _c in echoed)

    def test_mismatch_names_both_expected_and_actual(self):
        from pk232py.config import AppConfig

        echoed: list[tuple[str, str]] = []

        class _StubSerial:
            verbose_confirmed = True
            is_host_mode = False
            has_pactor = True

            @staticmethod
            def query_verbose_value(name, timeout=3.0):
                return {"MYCALL": "OE3GAS", "PACLEN": "999", "MAXFRAME": "1"}.get(name)

        config = AppConfig()
        config.hf_packet.mycall = "OE3GAS"
        config.hf_packet.paclen = 128
        config.hf_packet.maxframe = 1
        uploader = ParamsUploader(
            serial=_StubSerial(), config=config,
            echo_callback=lambda text, color: echoed.append((text, color)),
        )

        matched, applicable = uploader.verify()

        assert matched == 2
        assert applicable == 3
        assert any("PACLEN" in text and "999" in text and "128" in text for text, _c in echoed)


class TestVerboseQueryReadPath:
    """P53.A - query_verbose_value()/detect_maildrop() used to read their
    response through a SEPARATE, transient raw_data_received.connect()/
    disconnect() pair wrapped around write_verbose_wait() - a real race
    against Qt's queued cross-thread delivery (raw_data_received crosses
    from the ReaderThread into whichever thread constructed
    SerialManager - the GUI thread in production), which the disconnect()
    reliably loses if nothing pumps that thread's event loop in between.
    Confirmed 26.09.2026: the verbose terminal (a PERSISTENT
    raw_data_received connection, never torn down around one command)
    showed the TNC's correct answer to MYCALL while
    ParamsUploader.verify() reported "no answer" for the very same
    query. Fixed by having query_verbose_value()/detect_maildrop() read
    the response _write_verbose_wait_text() already assembled directly,
    with no signal-based capture in the loop at all."""

    def test_old_transient_connect_disconnect_pattern_loses_the_signal(self):
        # Reproduces the actual mechanism directly against a real
        # SerialManager.raw_data_received signal, with no event loop
        # pumping at all - the exact condition a plain pytest run
        # provides, and the worst case a momentarily busy GUI thread
        # approximates in production. This documents the bug
        # query_verbose_value()/detect_maildrop() used to have; it is
        # deliberately NOT how either reads any more (see the next test).
        sm = SerialManager()
        captured: list[bytes] = []

        def _capture(data: bytes) -> None:
            captured.append(data)

        def reader() -> None:
            sm.raw_data_received.emit(b"MYcall    OE3GAS\r\ncmd:")

        sm.raw_data_received.connect(_capture)
        t = threading.Thread(target=reader)
        t.start()
        t.join(timeout=1.0)
        sm.raw_data_received.disconnect(_capture)

        assert captured == []  # the queued delivery was dropped

    def test_query_verbose_value_no_longer_depends_on_the_signal_at_all(self):
        def responder(data):
            if data == b"MYCALL\r\n":
                return [(0.05, b"MYCALL\r\nMYcall    OE3GAS\r\ncmd:")]
            return []

        sm = SerialManager()
        port = _DelayedPort(responder)
        sm._serial = port
        sm._reader = _ReaderThread(
            port, sm._on_frame_received, raw_callback=sm._on_raw_data,
            host_mode_flag=lambda: sm._in_host_mode,
        )
        sm._reader.start()
        result: dict[str, object] = {}
        try:
            def worker() -> None:
                # Deliberately no app.processEvents() anywhere around
                # this call - if query_verbose_value() still depended on
                # a queued Qt signal, this would reproduce the same drop
                # as the test above.
                result["value"] = sm.query_verbose_value("MYCALL", timeout=1.0)

            t = threading.Thread(target=worker)
            t.start()
            t.join(timeout=2.0)
        finally:
            sm._reader.stop()
            sm._reader.join(timeout=1.0)

        assert result.get("value") == "OE3GAS"

    def test_detect_maildrop_no_longer_depends_on_the_signal_at_all(self):
        def responder(data):
            if data == b"MAILDROP\r\n":
                return [(0.05, b"MAILDROP\r\nMAildrop  ON\r\ncmd:")]
            return []

        sm = SerialManager()
        port = _DelayedPort(responder)
        sm._serial = port
        sm._reader = _ReaderThread(
            port, sm._on_frame_received, raw_callback=sm._on_raw_data,
            host_mode_flag=lambda: sm._in_host_mode,
        )
        sm._reader.start()
        result: dict[str, object] = {}
        try:
            def worker() -> None:
                result["value"] = sm.detect_maildrop(timeout=1.0)

            t = threading.Thread(target=worker)
            t.start()
            t.join(timeout=2.0)
        finally:
            sm._reader.stop()
            sm._reader.join(timeout=1.0)

        assert result.get("value") is True


class TestConverseModeDetection:
    """P53.B - HOST OFF returns the TNC to whichever operating mode was
    active before Host Mode was entered, not to the command prompt -
    Baudot/AMTOR/PACTOR all have a Converse idle state there that echoes
    every character and shows no cmd: prompt at all. Steps 1/2 alone see
    exactly the same "echo, no cmd:" shape a genuinely unresponsive TNC
    would produce - real console capture, 26.09.2026, 13:13-13:16."""

    def test_step2b_command_char_confirms_verbose_after_converse_mode(self):
        # Real bytes from the capture: '*' -> echo only, CR -> echo only,
        # neither ever reaching cmd: - only the COMMAND char (+ CR)
        # actually escapes Converse.
        def responder(data):
            if data == b"*":
                return bytes.fromhex("2a 5c 0d 0a")
            if data == b"\r":
                return bytes.fromhex("0d 0a")
            if data == bytes([0x03]) + b"\r":
                return b"\x03\r\ncmd:"
            return b""

        sm, port, _messages = _run_detection(responder)

        assert sm.verbose_confirmed is True
        assert sm.is_host_mode is False
        assert port.writes == [b"*", b"\r", bytes([0x03]) + b"\r"]
        assert _HPOLL_QUERY not in port.writes  # never needed step 3 at all

    def test_configured_command_char_is_used_instead_of_the_default(self):
        sm = SerialManager()
        sm.command_char = 0x18  # a non-default COMMAND char

        def responder(data):
            if data == bytes([0x18]) + b"\r":
                return b"\x18\r\ncmd:"
            return b""  # '*' and bare CR unanswered

        port = _FakePort(responder)
        sm._serial = port
        try:
            sm._init_tnc_thread()
        finally:
            if sm._reader:
                sm._reader.stop()
                sm._reader.join(timeout=1.0)

        assert sm.verbose_confirmed is True
        assert bytes([0x18]) + b"\r" in port.writes
        assert bytes([0x03]) + b"\r" not in port.writes

    def test_verify_reaches_the_tnc_answer_end_to_end(self):
        # P53.A+B combined, the spec's own example: verify() must
        # actually see 'MYcall    OE3GAS' via the fixed read path
        # (P53.A), not just the terminal - full verified (3/3).
        def responder(data):
            if data == b"MYCALL\r\n":
                return b"MYCALL\r\nMYcall    OE3GAS\r\ncmd:"
            if data == b"PACLEN\r\n":
                return b"PACLEN\r\nPAclen    128\r\ncmd:"
            if data == b"MAXFRAME\r\n":
                return b"MAXFRAME\r\nMAXframe  1\r\ncmd:"
            return b""

        sm = SerialManager()
        port = _FakePort(responder)
        sm._serial = port
        sm._reader = _ReaderThread(
            port, sm._on_frame_received, raw_callback=sm._on_raw_data,
            host_mode_flag=lambda: sm._in_host_mode,
        )
        sm._reader.start()

        config = AppConfig()
        config.hf_packet.mycall = "OE3GAS"
        config.hf_packet.paclen = 128
        config.hf_packet.maxframe = 1
        uploader = ParamsUploader(serial=sm, config=config)

        try:
            matched, applicable = uploader.verify()
        finally:
            sm._reader.stop()
            sm._reader.join(timeout=1.0)

        assert (matched, applicable) == (3, 3)

    def test_exit_host_mode_sends_command_char_and_logs_the_result(self, caplog):
        def responder(data):
            if data == bytes([0x03]) + b"\r":
                return b"\x03\r\ncmd:"
            return b""

        sm = SerialManager()
        sm._serial = _FakePort(responder)
        sm._in_host_mode = True
        try:
            with caplog.at_level(logging.INFO, logger="pk232py.comm.serial_manager"):
                sm.exit_host_mode()

            assert sm.is_host_mode is False
            assert bytes([0x03]) + b"\r" in sm._serial.writes
            assert any(
                "COMMAND char resync" in r.message for r in caplog.records
            )
        finally:
            if sm._reader:
                sm._reader.stop()
                sm._reader.join(timeout=1.0)


class TestXonFlowControlDetection:
    """P54.3/P54.4 - the PK-232 uses software flow control (its own boot
    banner proves it: '... 0d 0a 11 41 45 41 ...', that $11 right before
    the banner text is a self-generated XON). A TNC stopped by a stray
    XOFF ($13) keeps echoing every character but sends nothing it
    generates itself - the identical "echo, no cmd:" shape steps 1/2/2b
    already see. Real console capture, 26.09.2026, 13:13-13:16: steps
    1/2/2b all got only an echo."""

    def test_step2c_xon_then_cr_releases_a_stopped_tnc(self):
        xon_sent = {"yes": False}

        def responder(data):
            if data == bytes([0x11]):
                xon_sent["yes"] = True
                return b""
            if data == b"\r":
                return b"\r\ncmd:" if xon_sent["yes"] else b""
            return b""

        sm, port, _messages = _run_detection(responder)

        assert sm.verbose_confirmed is True
        assert bytes([0x11]) in port.writes
        assert _HPOLL_QUERY not in port.writes  # never needed step 3 at all

    def test_step2c_second_cr_reaches_cmd_when_the_first_attempt_does_not(self):
        # P54.4 - only the THIRD bare CR overall (step 2's own, then
        # step 2c's post-XON CR, then step 2c's own second CR) succeeds,
        # isolating that the second-CR logic specifically is what closes
        # this case, not an earlier CR getting lucky.
        calls = {"n": 0}

        def responder(data):
            if data == b"\r":
                calls["n"] += 1
                if calls["n"] >= 3:
                    return b"\r\ncmd:"
                return b""
            return b""

        sm, port, _messages = _run_detection(responder)

        assert sm.verbose_confirmed is True
        assert port.writes.count(b"\r") == 3

    def test_all_steps_silent_still_aborts_at_step_4_with_xon_attempted(self):
        def responder(_data):
            return b""

        sm, port, messages = _run_detection(responder)

        assert sm.verbose_confirmed is False
        assert bytes([0x11]) in port.writes  # step 2c's XON was tried
        assert any("No PK-232 responding" in m for m in messages)


class _ConfigCapturePort:
    """Duck-typed serial.Serial stand-in that just remembers what
    connect_port() configured (P54.5) - accepts the same keyword
    arguments serial.Serial does (via SerialManager.set_port_factory()),
    so connect_port()'s own real implementation runs end-to-end, no
    second copy of its logic needed in the test."""

    def __init__(self, **kwargs):
        self.port           = kwargs.get("port")
        self.baudrate        = kwargs.get("baudrate")
        self.bytesize        = kwargs.get("bytesize")
        self.parity          = kwargs.get("parity")
        self.stopbits        = kwargs.get("stopbits")
        self.timeout         = kwargs.get("timeout")
        self.write_timeout   = kwargs.get("write_timeout")
        self.xonxoff         = kwargs.get("xonxoff")
        self.rtscts          = kwargs.get("rtscts")
        self.dsrdtr          = kwargs.get("dsrdtr")
        self.dtr             = False
        self.rts             = False
        self.is_open         = True
        self.reset_calls: list[str] = []

    def reset_input_buffer(self) -> None:
        self.reset_calls.append("input")

    def reset_output_buffer(self) -> None:
        self.reset_calls.append("output")

    def read(self, n: int = 1) -> bytes:
        time.sleep(0.02)
        return b""

    def write(self, data: bytes) -> int:
        return len(data)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.is_open = False


class TestPortConfiguration:
    """P54.1/P54.2/P54.5 - connect_port() must open with the same known-
    working configuration a PuTTY session used on the same port/baud
    (26.09.2026: PuTTY got a prompt with one Enter; the app, with dtr/
    rts both False, did not, on the identical physical TNC), and must
    log every parameter that affects behaviour - the pre-P54 log line
    ('Port COM6 opened at 9600 baud') gave a hardware run nothing to
    compare against."""

    def test_connect_port_asserts_dtr_rts_and_resets_both_buffers(self):
        sm = SerialManager()
        sm.set_port_factory(lambda **kwargs: _ConfigCapturePort(**kwargs))
        try:
            ok = sm.connect_port("COM_TEST", baudrate=9600)
            assert ok is True
            port = sm._serial
            assert port.dtr is True
            assert port.rts is True
            assert port.xonxoff is False
            assert port.rtscts is False
            assert port.dsrdtr is False
            assert "input" in port.reset_calls
            assert "output" in port.reset_calls
        finally:
            if sm._reader:
                sm._reader.stop()
                sm._reader.join(timeout=1.0)

    def test_port_config_log_lines_name_every_field(self, caplog):
        sm = SerialManager()
        sm.set_port_factory(lambda **kwargs: _ConfigCapturePort(**kwargs))
        try:
            with caplog.at_level(logging.INFO, logger="pk232py.comm.serial_manager"):
                sm.connect_port("COM_TEST", baudrate=9600)
            messages = [r.message for r in caplog.records]
            on_open = next(m for m in messages if m.startswith("Port config on open:"))
            after_reset = next(
                m for m in messages if m.startswith("Port config after reset:")
            )
            for line in (on_open, after_reset):
                for field in (
                    "xonxoff=", "rtscts=", "dsrdtr=",
                    "dtr=", "rts=", "timeout=", "write_timeout=",
                ):
                    assert field in line, f"{field!r} missing from {line!r}"
            # The "after reset" line is the configuration the connection
            # actually runs with - it must show the P54.2 values, not
            # whatever the bare constructor call happened to leave dtr/
            # rts at.
            assert "dtr=True" in after_reset
            assert "rts=True" in after_reset
        finally:
            if sm._reader:
                sm._reader.stop()
                sm._reader.join(timeout=1.0)

    def test_disconnect_port_logs_the_end_state(self, caplog):
        sm = SerialManager()
        sm.set_port_factory(lambda **kwargs: _ConfigCapturePort(**kwargs))
        sm.connect_port("COM_TEST", baudrate=9600)
        with caplog.at_level(logging.INFO, logger="pk232py.comm.serial_manager"):
            sm.disconnect_port()

        messages = [r.message for r in caplog.records]
        at_close = next(m for m in messages if m.startswith("Port config at close:"))
        for field in (
            "xonxoff=", "rtscts=", "dsrdtr=",
            "dtr=", "rts=", "timeout=", "write_timeout=",
        ):
            assert field in at_close, f"{field!r} missing from {at_close!r}"
