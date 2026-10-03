# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""P72: parameters applied right after OK - in Host Mode WITHOUT leaving it.

Two layers are tested:
  * ParamApplier (Qt-free) against a recording FakeTransport;
  * SerialParamTransport against a fake SerialManager that records every
    byte written, so "exactly one Host frame, no verbose byte, no HOST OFF"
    is checked on the write log itself.
"""

from __future__ import annotations

import copy
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

from pk232py.comm.frame import FrameKind, HostFrame, build_command
from pk232py.comm.param_applier import (
    ApplyResult, ParamApplier, SerialParamTransport, format_result,
)
from pk232py.config import AppConfig

_app = QApplication.instance() or QApplication([])

B = "01.AUG.91"
A = "13.SEP.95"


def _cfg_pair(mutate):
    before = AppConfig()
    after = copy.deepcopy(before)
    mutate(before, after)
    return before, after


class FakeTransport:
    """Recording ParamTransport. host_answers: {(mnemonic, args): bytes}."""

    def __init__(self, mode="host", release=B, host_answers=None,
                 verbose_values=None, verbose_reply="", converse=False,
                 io_connected=False, escapes=True):
        self._mode, self._release = mode, release
        self.host_answers = host_answers or {}
        self.verbose_values = dict(verbose_values or {})
        self.verbose_reply = verbose_reply
        self._converse, self._io, self._escapes = converse, io_connected, escapes
        self.log: list = []

    def mode(self):
        return self._mode

    def release(self):
        return self._release

    def host_exchange(self, mnemonic, args):
        self.log.append(("host", mnemonic, args))
        return self.host_answers.get((mnemonic, args))

    def verbose_set(self, name, value):
        self.log.append(("vset", name, value))
        self.verbose_values[name] = value
        return self.verbose_reply

    def verbose_query(self, name):
        self.log.append(("vquery", name))
        return self.verbose_values.get(name)

    def verbose_query_text(self, command):
        self.log.append(("vtext", command))
        return self.verbose_values.get(command, "")

    def in_converse(self):
        return self._converse

    def io_channel_connected(self):
        return self._io

    def escape_converse(self):
        self.log.append(("escape",))
        return self._escapes

    def return_to_converse(self):
        self.log.append(("converse",))


def _users_1_to_10():
    return _cfg_pair(lambda b, a: (setattr(b.hf_packet, "users", 1),
                                   setattr(a.hf_packet, "users", 10)))


class TestHostMode:
    def test_users_is_set_and_read_back_with_two_host_frames_only(self):
        t = FakeTransport(host_answers={
            (b"UR", b"10"): b"UR\x00", (b"UR", b""): b"UR10"})
        before, after = _users_1_to_10()
        results = ParamApplier(t).apply(before, after)
        assert t.log == [("host", b"UR", b"10"), ("host", b"UR", b"")]
        assert results == [ApplyResult("USERS", "10", "10", True, "ok", was="1")]

    def test_ubit_off_on_device_a(self):
        t = FakeTransport(release=A, host_answers={
            (b"UB", b"0 N"): b"UB\x00", (b"UB", b"0"): b"UBN"})
        before, after = _cfg_pair(lambda b, a: setattr(a.hf_packet, "ubit0", False)
                                  or setattr(b.hf_packet, "ubit0", True))
        (r,) = ParamApplier(t).apply(before, after)
        assert t.log[0] == ("host", b"UB", b"0 N")
        assert r.ok and r.tnc_now == "OFF"

    def test_not_verified_for_the_release_sends_nothing(self):
        t = FakeTransport(release=A)       # UNPROTO is verified on B only
        before, after = _cfg_pair(lambda b, a: setattr(a.hf_packet, "unproto", "APRS"))
        (r,) = ParamApplier(t).apply(before, after)
        assert t.log == []
        assert not r.ok
        assert r.reason == "not verified for Host Mode on 13.SEP.95"

    def test_unknown_release_counts_as_not_verified(self):
        t = FakeTransport(release=None)
        before, after = _users_1_to_10()
        (r,) = ParamApplier(t).apply(before, after)
        assert t.log == [] and not r.ok
        assert "not verified for Host Mode on unknown" in r.reason

    def test_no_fallback_to_verbose(self):
        t = FakeTransport(release=A)
        before, after = _cfg_pair(lambda b, a: setattr(a.hf_packet, "ax25l2v2", False))
        ParamApplier(t).apply(before, after)
        assert not [e for e in t.log if e[0] in ("vset", "vquery", "escape")]

    def test_ilfpack_is_never_set_live(self):
        t = FakeTransport()
        before, after = _cfg_pair(lambda b, a: setattr(a.hf_packet, "ilfpack", False))
        (r,) = ParamApplier(t).apply(before, after)
        assert t.log == [] and not r.ok
        assert r.reason == "ILFPACK is applied at the next initialisation (see P75)"

    def test_rejected_answer_reports_the_code_and_what_the_tnc_has(self):
        t = FakeTransport(host_answers={
            (b"MX", b"7"): b"MX\x07", (b"MX", b""): b"MX4"})
        before, after = _cfg_pair(lambda b, a: (setattr(b.hf_packet, "maxframe", 4),
                                                setattr(a.hf_packet, "maxframe", 7)))
        (r,) = ParamApplier(t).apply(before, after, band="HF")
        assert not r.ok
        assert r.reason == "rejected by TNC: $07"
        assert r.tnc_now == "4"
        assert format_result(r).endswith("(TNC still 4)")

    def test_ack_but_readback_differs_is_not_ok(self):
        t = FakeTransport(host_answers={
            (b"UR", b"10"): b"UR\x00", (b"UR", b""): b"UR1"})
        before, after = _users_1_to_10()
        (r,) = ParamApplier(t).apply(before, after)
        assert not r.ok and r.tnc_now == "1"

    def test_no_answer_is_reported(self):
        t = FakeTransport()                # nothing answers
        before, after = _users_1_to_10()
        (r,) = ParamApplier(t).apply(before, after)
        assert not r.ok and "no answer" in r.reason


class TestOtherStates:
    def test_disconnected_sends_nothing(self):
        t = FakeTransport(mode="disconnected")
        before, after = _users_1_to_10()
        (r,) = ParamApplier(t).apply(before, after)
        assert t.log == [] and not r.ok
        assert r.reason == "not connected"

    def test_unconfirmed_verbose_sends_nothing(self):
        t = FakeTransport(mode="unconfirmed")
        before, after = _users_1_to_10()
        (r,) = ParamApplier(t).apply(before, after)
        assert t.log == [] and not r.ok
        assert "cmd:" in r.reason

    def test_verbose_command_then_readback(self):
        t = FakeTransport(mode="verbose")
        before, after = _users_1_to_10()
        (r,) = ParamApplier(t).apply(before, after)
        assert t.log == [("vset", "USERS", "10"), ("vquery", "USERS")]
        assert r.ok and r.tnc_now == "10"

    def test_verbose_error_line_is_quoted(self):
        t = FakeTransport(mode="verbose", verbose_reply="USERS 10\r\n?Bad\r\ncmd:",
                          verbose_values={"USERS": "1"})
        t.verbose_set = lambda n, v: (t.log.append(("vset", n, v)) or "?Bad")
        before, after = _users_1_to_10()
        (r,) = ParamApplier(t).apply(before, after)
        assert not r.ok and "?Bad" in r.reason and r.tnc_now == "1"

    def test_converse_is_escaped_and_restored_only_with_a_connected_io_channel(self):
        before, after = _users_1_to_10()
        t = FakeTransport(mode="verbose", converse=True, io_connected=True)
        ParamApplier(t).apply(before, after)
        assert t.log[0] == ("escape",) and t.log[-1] == ("converse",)
        t = FakeTransport(mode="verbose", converse=True, io_connected=False)
        ParamApplier(t).apply(before, after)
        assert ("converse",) not in t.log

    def test_converse_that_cannot_be_escaped_sends_nothing(self):
        t = FakeTransport(mode="verbose", converse=True, escapes=False)
        before, after = _users_1_to_10()
        (r,) = ParamApplier(t).apply(before, after)
        assert not r.ok and [e for e in t.log if e[0] == "vset"] == []

    def test_nothing_changed_nothing_sent(self):
        t = FakeTransport()
        assert ParamApplier(t).apply(AppConfig(), AppConfig()) == []
        assert t.log == []


class TestFormat:
    def test_lines_match_the_spec(self):
        ok = ApplyResult("USERS", "10", "10", True, "ok", was="1")
        assert format_result(ok) == "USERS  1 -> 10  ok"
        nv = ApplyResult("CODE", "3", None, False,
                         "not verified for Host Mode on 01.AUG.91")
        assert format_result(nv) == ("CODE  not verified for Host Mode on "
                                     "01.AUG.91 - saved, TNC unchanged")


# ---------------------------------------------------------------------------
# SerialParamTransport against a fake SerialManager: the WRITE LOG
# ---------------------------------------------------------------------------

class FakeSerialManager(QObject):
    frame_received = pyqtSignal(object)

    def __init__(self, answers, host=True, release=B):
        super().__init__()
        self.is_connected = True
        self.is_host_mode = host
        self.verbose_confirmed = not host
        self.tnc_release = release
        self.command_char = 0x03
        self.writes: list = []           # every byte string that left the app
        self._answers = answers

    def send_command(self, mnemonic, args=b""):
        self.writes.append(build_command(mnemonic, args))
        reply = self._answers.get((mnemonic, args))
        if reply is not None:
            self.frame_received.emit(HostFrame(0x4F, 0xF, reply, FrameKind.CMD_RESP))
        return True

    def write_verbose(self, data):
        self.writes.append(data)
        return True

    def send_verbose_command(self, data, timeout=3.0):
        self.writes.append(data)
        return True, b""

    def query_verbose_value(self, name, timeout=3.0):
        self.writes.append(f"{name}\r\n".encode())
        return None

    def exit_host_mode(self, io_channel=None):
        self.writes.append(b"HOST OFF")


class TestWriteLogInHostMode:
    def test_exactly_the_set_and_the_query_frame_nothing_else(self):
        sm = FakeSerialManager({(b"UR", b"10"): b"UR\x00", (b"UR", b""): b"UR10"})
        transport = SerialParamTransport(sm, in_converse=lambda: False,
                                         io_channel_connected=lambda: False)
        before, after = _users_1_to_10()
        (r,) = ParamApplier(transport).apply(before, after)
        assert sm.writes == [bytes.fromhex("01 4F 55 52 31 30 17"),
                             bytes.fromhex("01 4F 55 52 17")]
        assert r.ok and r.tnc_now == "10"

    def test_no_answer_times_out_and_still_writes_no_verbose_byte(self):
        sm = FakeSerialManager({})
        transport = SerialParamTransport(sm, in_converse=lambda: False,
                                         io_channel_connected=lambda: False,
                                         timeout=0.05)
        before, after = _users_1_to_10()
        (r,) = ParamApplier(transport).apply(before, after)
        assert not r.ok
        assert all(w.startswith(b"\x01\x4f") for w in sm.writes)
        assert b"HOST OFF" not in sm.writes

    def test_mode_comes_from_the_serial_manager(self):
        sm = FakeSerialManager({}, host=False)
        t = SerialParamTransport(sm, in_converse=lambda: False,
                                 io_channel_connected=lambda: False)
        assert t.mode() == "verbose"
        sm.verbose_confirmed = False
        assert t.mode() == "unconfirmed"
        sm.is_connected = False
        assert t.mode() == "disconnected"
