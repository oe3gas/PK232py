# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Unit tests for pk232py.comm.pk232_hostmode_sub (P66).

enter_host_mode() opens its own serial.Serial() internally, so
serial.Serial itself is monkeypatched to a fake class per test - the
same technique test_serial_manager.py's _ConfigCapturePort uses via
SerialManager.set_port_factory(), just at the module level since this
is a free function, not a class with an injectable seam of its own.

_FakePort mirrors test_serial_manager.py's own _FakePort(responder):
canned response is queued the instant the triggering write() call
returns, so read_until()'s own polling loop sees it on its very first
pass - no test needs to sleep for real hardware timing.
"""

from __future__ import annotations

import time

import pytest
import serial

import pk232py.comm.pk232_hostmode_sub as pk232_hostmode_sub
from pk232py.comm.pk232_hostmode_sub import (
    ETB,
    HPOLL_ACK,
    HPOLL_Y,
    OPMODE_QUERY,
    SOH,
    enter_host_mode,
    escape_converse,
)

_REAL_OPMODE_ANSWER = bytes([SOH, 0x4F, ord('O'), ord('P'), ord('P'), ord('A'), ETB])

# P66, Teil A: scales every named timeout in pk232_hostmode_sub down for
# the duration of one test (P61's own convention - see
# test_serial_manager.py's fast_serial_timing) - keeps every test well
# under 1s even for the one scenario (Converse-with-echo) where no
# write ever produces a real 'cmd:' match.
_FAST_TIMING_FACTOR = 1 / 30
_FAST_TIMING_CONSTANTS = (
    "_PRE_HANDSHAKE_SETTLE",
    "_ESCAPE_CONVERSE_TIMEOUT",
    "_HOST3_SETTLE_TIMEOUT",
    "_CR_SETTLE_TIMEOUT",
    "_HPOLL_TIMEOUT",
    "_OPMODE_TIMEOUT",
    "_LATE_ENTRY_INTERVAL",
)


@pytest.fixture(autouse=True)
def fast_handshake_timing(monkeypatch):
    for name in _FAST_TIMING_CONSTANTS:
        original = getattr(pk232_hostmode_sub, name)
        monkeypatch.setattr(pk232_hostmode_sub, name, original * _FAST_TIMING_FACTOR)


class _FakePort:
    """Duck-typed stand-in for serial.Serial - synchronous and
    in-memory. *responder(data) -> bytes* decides what (if anything)
    comes back for each write; every write is recorded in *writes* for
    order-of-operations assertions."""

    def __init__(self, responder):
        self._responder = responder
        self._buf = bytearray()
        self.writes: list[bytes] = []

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
            time.sleep(0.001)
            return b""
        n = min(n, len(self._buf))
        data = bytes(self._buf[:n])
        del self._buf[:n]
        return data

    def close(self) -> None:
        pass


def _echo_responder(data: bytes) -> bytes:
    """Converse (and Transparent) echo everything typed at them,
    including binary frame bytes (CLAUDE.md P52.2) - so every write
    comes straight back, byte for byte."""
    return data


def _make_command_mode_responder(command_char: bytes):
    """A TNC that is genuinely at the command interpreter: answers the
    COMMAND-char escape attempt, HOST 3, the follow-up CR, HPOLL_Y and
    the OPMODE query each with a real, distinct response - never an
    echo of what was sent."""
    escape_write = command_char + b"\r"

    def responder(data: bytes) -> bytes:
        if data == escape_write:
            return b"\r\ncmd:"
        if data == b"\rXFLOW OFF\r\rHOST 3":
            return b"cmd:cmd:"
        if data == b"\r":
            return b"\r\n"
        if data == HPOLL_Y:
            return HPOLL_ACK
        if data == OPMODE_QUERY:
            return _REAL_OPMODE_ANSWER
        return b""

    return responder


class TestEscapeConverse:
    """The pure decision function - no port at all, just the injected
    send_and_wait(data, timeout) primitive."""

    def test_returns_true_on_first_matching_attempt(self):
        calls: list[bytes] = []

        def send_and_wait(data: bytes, timeout: float) -> bytes:
            calls.append(data)
            return b"\r\ncmd:"

        found, raw = escape_converse(send_and_wait, b"\x03")
        assert found is True
        assert calls == [b"\x03\r"]  # only one attempt needed
        assert b"cmd:" in raw

    def test_returns_false_after_every_attempt_fails(self):
        calls: list[bytes] = []

        def send_and_wait(data: bytes, timeout: float) -> bytes:
            calls.append(data)
            return b""  # never a cmd: prompt

        found, raw = escape_converse(send_and_wait, b"\x03")
        assert found is False
        assert len(calls) == 3  # all three attempts tried
        assert raw == b""

    def test_succeeds_on_the_third_attempt_within_cmdtime(self):
        # TRANSPARENT needs three COMMAND characters (TRM; CLAUDE.md
        # P53.B) - the first two attempts here answer with nothing.
        responses = [b"", b"", b"\r\ncmd:"]

        def send_and_wait(data: bytes, timeout: float) -> bytes:
            return responses.pop(0)

        found, raw = escape_converse(send_and_wait, b"\x03")
        assert found is True
        assert b"cmd:" in raw


class TestEnterHostModeRejectsConverseEcho:
    """P66, B.2 - the actual root cause: a verbose CONNECT can leave
    the TNC in Converse, where HOST 3/HPOLL Y are never seen by the
    command interpreter at all and every 'response' is Converse
    echoing the exact bytes just sent back verbatim. Confirmed by a
    real hardware run, T141, 28.09.2026, Device B,
    20260928_094001_link_carry.log."""

    def test_pure_echo_is_rejected(self, monkeypatch):
        port = _FakePort(_echo_responder)
        monkeypatch.setattr(serial, "Serial", lambda *a, **kw: port)

        ok, raw = enter_host_mode("COM_TEST", 9600)

        # Before P66 this returned True - HPOLL_Y in the echoed response
        # was mistaken for HP Y (already in HPOLL ON).
        assert ok is False
        assert HPOLL_Y in raw  # the echo is IN the raw response...
        # ...but the OPMODE query's own echo carries no value byte, so
        # it is never mistaken for a genuine answer.
        assert _REAL_OPMODE_ANSWER not in raw


class TestEnterHostModeLateEntry:
    """P66b, Teil B - a real hardware run (T141, 28.09.2026, Device B,
    13:35) found HOST 3 can take effect AFTER the OPMODE check already
    saw only an echo - the command interpreter lagged seconds behind
    the character echo while a connection was active. A retried OPMODE
    check catches this instead of reporting a false failure."""

    def test_late_entry_on_a_later_opmode_attempt_succeeds(self, monkeypatch, caplog):
        base = _make_command_mode_responder(b"\x03")
        opmode_attempts = [0]

        def responder(data: bytes) -> bytes:
            if data == OPMODE_QUERY:
                opmode_attempts[0] += 1
                if opmode_attempts[0] < 3:
                    return data  # still just an echo - not yet in Host Mode
                return _REAL_OPMODE_ANSWER  # HOST 3 took effect meanwhile
            return base(data)

        port = _FakePort(responder)
        monkeypatch.setattr(serial, "Serial", lambda *a, **kw: port)

        with caplog.at_level("INFO", logger="pk232py.comm.pk232_hostmode_sub"):
            ok, raw = enter_host_mode("COM_TEST", 9600)

        assert ok is True
        assert opmode_attempts[0] == 3
        assert _REAL_OPMODE_ANSWER in raw
        assert any("late entry" in r.message for r in caplog.records)

    def test_persistent_echo_gives_up_after_one_initial_plus_three_retries(
        self, monkeypatch,
    ):
        port = _FakePort(_echo_responder)
        monkeypatch.setattr(serial, "Serial", lambda *a, **kw: port)

        ok, _raw = enter_host_mode("COM_TEST", 9600)

        assert ok is False
        assert port.writes.count(OPMODE_QUERY) == 4  # 1 initial + 3 retries

    def test_failure_writes_every_step_to_stderr_with_timestamps(
        self, monkeypatch, capsys,
    ):
        port = _FakePort(_echo_responder)
        monkeypatch.setattr(serial, "Serial", lambda *a, **kw: port)

        enter_host_mode("COM_TEST", 9600)

        err = capsys.readouterr().err
        for label in (
            "'escape_converse'", "'host3'", "'cr'", "'hpoll'", "'opmode'",
            "'opmode retry 1'", "'opmode retry 2'", "'opmode retry 3'",
        ):
            assert label in err, f"{label} missing from stderr log"
        assert "+0ms" in err or "ms tx=" in err  # every line carries a timestamp


class TestEnterHostModeAcceptsRealHostMode:
    def test_already_at_command_prompt_succeeds(self, monkeypatch):
        responder = _make_command_mode_responder(b"\x03")
        port = _FakePort(responder)
        monkeypatch.setattr(serial, "Serial", lambda *a, **kw: port)

        ok, raw = enter_host_mode("COM_TEST", 9600)

        assert ok is True
        assert HPOLL_ACK in raw
        assert _REAL_OPMODE_ANSWER in raw

    def test_converse_is_escaped_before_host_3_is_sent(self, monkeypatch):
        # Same responder as above - the point of this test is the
        # WRITE ORDER, not a different response shape: the COMMAND
        # character must reach the port before 'HOST 3' does, in every
        # case, since the TNC's own state is not known in advance.
        responder = _make_command_mode_responder(b"\x03")
        port = _FakePort(responder)
        monkeypatch.setattr(serial, "Serial", lambda *a, **kw: port)

        ok, _raw = enter_host_mode("COM_TEST", 9600)

        assert ok is True
        escape_index = port.writes.index(b"\x03\r")
        host3_index = next(
            i for i, w in enumerate(port.writes) if w == b"\rXFLOW OFF\r\rHOST 3"
        )
        assert escape_index < host3_index

    def test_command_char_is_passed_through_not_hardcoded(self, monkeypatch):
        custom_char = b"\x18"  # CAN - deliberately not the default $03
        responder = _make_command_mode_responder(custom_char)
        port = _FakePort(responder)
        monkeypatch.setattr(serial, "Serial", lambda *a, **kw: port)

        ok, _raw = enter_host_mode("COM_TEST", 9600, custom_char)

        assert ok is True
        assert port.writes[0] == custom_char + b"\r"
        assert b"\x03\r" not in port.writes
