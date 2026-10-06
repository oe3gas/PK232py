# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""P75 - verbose commands end with CR only, so ILFPACK OFF cannot break the app.

T155 (device B): with ILFPACK OFF the TNC keeps the LF of "CR LF" and it becomes
the first character of the NEXT command ("<LF>USERS" -> ?What?). T175 (devices B
and A, hw_logs/20261006_144428_eol_probe.log and 20261006_145938_eol_probe.log):
CR alone works with ILFPACK ON and OFF on both.

Needs a QApplication (offscreen, see conftest).
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
import re
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

import pk232py
from pk232py.comm import host_params
from pk232py.comm.param_applier import ParamApplier, SerialParamTransport
from pk232py.comm.params_uploader import ParamsUploader
from pk232py.comm.serial_manager import SerialManager
from pk232py.config import AppConfig

from .test_param_applier import A, B, FakeTransport, _cfg_pair

_app = QApplication.instance() or QApplication([])

CRLF = chr(13) + chr(10)
SRC = Path(pk232py.__file__).resolve().parent

# The line the TNC really answered on device A (T175, 20261006_145938_eol_probe.log,
# verbose "ILFPACK" with EXPERT OFF) - copied literally.
EXPERT_ANSWER_A = "ILFPACK\r\n?EXPERT command\r\ncmd:"


# ------------------------------------------------------------------ Teil A

class TestOnePlace:

    def test_verbose_line_is_text_plus_cr(self):
        from pk232py.comm.constants import verbose_line
        assert verbose_line("PACLEN 128") == b"PACLEN 128\r"
        assert verbose_line("MYCALL OE3GAS") == b"MYCALL OE3GAS\r"

    def test_no_lf_ever(self):
        from pk232py.comm.constants import verbose_line
        assert b"\n" not in verbose_line("HELP")


# Where "CR LF" is NOT a command end (file, function). Everything else in
# comm/, modes/, maildrop/ and main_window.py must not contain a CR LF literal.
_ALLOWED = {
    # reading paths: the TNC's own answers end with CR LF
    ("comm/pk232_hostmode_sub.py", "enter_host_mode"),
    ("maildrop/protocol.py", "split_after_echo"),
    ("maildrop/protocol.py", "parse_list"),
    ("maildrop/protocol.py", "parse_read"),
    ("maildrop/session.py", "_parse_error_after_echo"),
    # data lines that go out on the air / macro text, not commands
    ("ui/main_window.py", "_on_baudot_send_char"),
    ("ui/main_window.py", "_on_rtty_char_ready"),
    ("ui/main_window.py", "_insert_macro_plain"),
    ("ui/main_window.py", "_on_macro_clicked"),
}


def _crlf_literals(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes))):
            continue
        text = node.value.decode("latin1") if isinstance(node.value, bytes) else node.value
        if CRLF not in text:
            continue
        parent = parents.get(node)
        if isinstance(parent, ast.Expr):            # a docstring
            continue
        func = "<module>"
        cur = node
        while cur in parents:
            cur = parents[cur]
            if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func = cur.name
                break
        yield func, node.lineno


def _scanned_files():
    for sub in ("comm", "modes", "maildrop"):
        yield from sorted((SRC / sub).glob("*.py"))
    yield SRC / "ui" / "main_window.py"


class TestStaticScan:

    def test_no_command_literal_ends_with_cr_lf(self):
        offenders = []
        for path in _scanned_files():
            rel = path.relative_to(SRC).as_posix()
            for func, line in _crlf_literals(path):
                if (rel, func) not in _ALLOWED:
                    offenders.append(f"{rel}:{line} in {func}()")
        assert not offenders, "CR LF literal outside the allow list:\n" + "\n".join(offenders)

    def test_the_allow_list_has_no_stale_entries(self):
        seen = set()
        for path in _scanned_files():
            rel = path.relative_to(SRC).as_posix()
            for func, _line in _crlf_literals(path):
                seen.add((rel, func))
        assert _ALLOWED <= seen

    def test_rtty_tx_line_end_is_still_cr_lf(self):
        found = {func for func, _ in _crlf_literals(SRC / "ui" / "main_window.py")}
        assert {"_on_baudot_send_char", "_on_rtty_char_ready"} <= found


def _mode_classes():
    import pk232py.modes as modes_pkg
    for info in pkgutil.iter_modules(modes_pkg.__path__):
        module = importlib.import_module(f"pk232py.modes.{info.name}")
        for _n, cls in inspect.getmembers(module, inspect.isclass):
            if cls.__module__ == module.__name__ and getattr(cls, "verbose_command", None):
                yield cls


class TestModeCommands:

    def test_every_mode_command_ends_with_cr_only(self):
        classes = list(_mode_classes())
        assert len(classes) >= 8
        for cls in classes:
            cmd = cls.verbose_command
            assert cmd.endswith(b"\r") and b"\n" not in cmd, cls.__name__


# ---------------------------------------------------------------- Teil C

class FakeTnc:
    """A TNC with ILFPACK OFF: the LF stays in the line buffer and becomes
    part of the next command name (T155)."""

    KNOWN = {"EXPERT", "MAILDROP", "CONVERSE", "CSTATUS", "OPMODE", "VHF", "HELP",
             "PACLEN", "USERS", "MAXFRAME", "MYCALL"}

    def __init__(self, extra=()):
        self.known = self.KNOWN | set(extra)
        self.buf = ""
        self.what = []              # command lines answered "?What?"

    def feed(self, data: bytes) -> str:
        out = []
        for ch in data.decode("ascii"):
            if ch == "\r":
                words = self.buf.split(" ")      # NOT split(): that would eat the LF
                if words[0].upper() in self.known:
                    out.append(f"{self.buf}\r\n{words[0]} ok\r\ncmd:")
                else:
                    self.what.append(self.buf)
                    out.append(f"{self.buf}\r\n?What?\r\ncmd:")
                self.buf = ""
            else:
                self.buf += ch      # LF is NOT ignored
        return "".join(out)


def _all_names(cfg) -> set:
    cmds = ParamsUploader(None, cfg)._build_commands(has_pactor=True)
    return {c.decode("ascii").split()[0].upper() for c in cmds}


class _Stub:
    is_host_mode = False
    verbose_confirmed = True
    has_pactor = True
    tnc_release = None

    def __init__(self, tnc):
        self.tnc = tnc
        self.written = []

    def write_verbose_wait(self, cmd, timeout=5.0):
        self.written.append(cmd)
        self.tnc.feed(cmd)
        return True

    def detect_maildrop(self):
        return True


class TestUploadAgainstIlfpackOff:

    def test_every_command_ends_with_cr_only(self):
        for cmd in ParamsUploader(None, AppConfig())._build_commands(has_pactor=True):
            assert cmd.endswith(b"\r") and not cmd.endswith(CRLF.encode()), cmd

    def test_upload_write_log_has_no_lf(self):
        stub = _Stub(FakeTnc(_all_names(AppConfig())))
        ParamsUploader(stub, AppConfig()).upload()
        assert stub.written and all(b"\n" not in c for c in stub.written)

    def test_ilfpack_off_tnc_answers_every_command(self):
        cfg = AppConfig()
        tnc = FakeTnc(_all_names(cfg))
        ParamsUploader(_Stub(tnc), cfg).upload()
        assert tnc.what == []        # heute: ab dem zweiten Befehl "?What?"


class _Sm:
    """SerialManager stand-in for SerialParamTransport (verbose side only)."""

    def __init__(self, tnc):
        self.tnc = tnc
        self.written = []
        self.command_char = 3

    def send_verbose_command(self, data, timeout=3.0):
        self.written.append(data)
        return True, self.tnc.feed(data).encode("ascii")

    def write_verbose(self, data):
        self.written.append(data)
        self.tnc.feed(data)

    def query_verbose_value(self, name):
        return None


class TestApplierAgainstIlfpackOff:

    def _transport(self, tnc):
        sm = _Sm(tnc)
        return SerialParamTransport(sm, lambda: False, lambda: False), sm

    def test_set_and_query_end_with_cr_only_and_stay_answered(self):
        tnc = FakeTnc({"PACLEN", "USERS"})
        t, sm = self._transport(tnc)
        t.verbose_set("PACLEN", "128")
        t.verbose_query_text("USERS")
        t.verbose_query_text("HELP")
        assert tnc.what == []
        assert all(b"\n" not in d for d in sm.written)

    def test_return_to_converse_is_cr_only(self):
        tnc = FakeTnc()
        t, sm = self._transport(tnc)
        t.return_to_converse()
        assert sm.written == [b"CONVERSE\r"]


class TestSerialManagerCommands:

    def _manager(self, monkeypatch):
        sm = SerialManager()
        sent = []
        monkeypatch.setattr(SerialManager, "is_connected", property(lambda s: True))
        monkeypatch.setattr(
            sm, "_write_verbose_wait_text",
            lambda data, timeout=5.0: (sent.append(data) or (True, b"cmd:")))
        return sm, sent

    def test_queries_end_with_cr_only(self, monkeypatch):
        sm, sent = self._manager(monkeypatch)
        sm.query_verbose_value("PACLEN")
        sm.probe_release_verbose()
        sm.detect_maildrop()
        sm.query_live_links()
        assert sent
        for data in sent:
            assert data.endswith(b"\r") and b"\n" not in data, data

    def test_init_command_constants_are_cr_only(self):
        from pk232py.comm import serial_manager as m
        for name in ("_CMD_AWLEN", "_CMD_PARITY", "_CMD_8BITCONV", "_CMD_RESTART"):
            value = getattr(m, name)
            assert value.endswith(b"\r") and b"\n" not in value, name


# ------------------------------------------------------------------ Teil B

class TestIlfpackLive:

    def test_il_is_verified_on_b_only_with_the_t175_proof(self):
        assert host_params.verified_sources("ILFPACK") == {B: "T175"}
        p = host_params.param_by_name("ILFPACK")
        assert B in p.verified_releases and A not in p.verified_releases

    def test_on_b_ilfpack_is_set_in_host_mode_like_any_other_switch(self):
        p = host_params.param_by_name("ILFPACK")
        q = host_params.host_query_args(p)
        s = host_params.host_set_args(p, "OFF")
        t = FakeTransport(release=B, host_answers={
            (p.mnemonic, q): [p.mnemonic + b"Y", p.mnemonic + b"N"],
            (p.mnemonic, s): p.mnemonic + b"\x00"})
        before, after = _cfg_pair(lambda b, a: setattr(a.hf_packet, "ilfpack", False))
        (r,) = ParamApplier(t).apply(before, after)
        assert r.ok and r.sent and r.reason == "ok"
        assert ("host", p.mnemonic, s) in t.log

    def test_on_a_host_mode_it_stays_unverified(self):
        t = FakeTransport(release=A)
        before, after = _cfg_pair(lambda b, a: setattr(a.hf_packet, "ilfpack", False))
        (r,) = ParamApplier(t).apply(before, after)
        assert t.log == [] and not r.ok and not r.sent
        assert r.reason == "not verified for Host Mode on 13.SEP.95"

    def test_the_never_live_rule_is_gone(self):
        from pk232py.comm import param_applier
        assert not hasattr(param_applier, "_NEVER_LIVE")


# ----------------------------------------------------- ?EXPERT command

class ExpertTransport(FakeTransport):
    """Verbose side of device A: EXPERT is OFF after power-on, so ILFPACK
    answers '?EXPERT command' until EXPERT is ON."""

    def __init__(self, **kw):
        super().__init__(mode="verbose", release=A, **kw)
        self.expert = False
        self.ilfpack = "ON"

    def verbose_set(self, name, value):
        self.log.append(("vset", name, value))
        if name == "EXPERT":
            self.expert = (value == "ON")
            return f"EXPERT {value}\r\ncmd:"
        if name == "ILFPACK":
            if not self.expert:
                return EXPERT_ANSWER_A
            self.ilfpack = value
            return f"ILFPACK {value}\r\ncmd:"
        return ""

    def verbose_query(self, name):
        self.log.append(("vquery", name))
        if name == "ILFPACK":
            return self.ilfpack if self.expert else None
        return None


class TestExpertCommandAnswer:

    def _apply(self, t):
        before, after = _cfg_pair(lambda b, a: setattr(a.hf_packet, "ilfpack", False))
        return ParamApplier(t).apply(before, after)

    def test_expert_on_repeat_read_back_expert_off_and_report(self):
        t = ExpertTransport()
        (r,) = self._apply(t)
        sets = [e[1:] for e in t.log if e[0] == "vset"]
        assert sets == [("ILFPACK", "OFF"), ("EXPERT", "ON"),
                        ("ILFPACK", "OFF"), ("EXPERT", "OFF")]
        assert r.ok and r.sent and t.ilfpack == "OFF" and not t.expert
        assert "EXPERT" in r.reason          # the result says it was needed

    def test_the_read_back_happens_while_expert_is_on(self):
        t = ExpertTransport()
        self._apply(t)
        names = [(e[0], e[1]) for e in t.log]
        last_read = max(i for i, e in enumerate(names) if e == ("vquery", "ILFPACK"))
        off = max(i for i, e in enumerate(t.log) if e[:3] == ("vset", "EXPERT", "OFF"))
        assert last_read < off

    def test_no_expert_dance_for_any_other_answer(self):
        class Rejects(FakeTransport):
            pass
        t = Rejects(mode="verbose", release=B, verbose_reply="?not while connected\r\ncmd:")
        before, after = _cfg_pair(lambda b, a: setattr(a.hf_packet, "users", 3))
        (r,) = ParamApplier(t).apply(before, after)
        assert not [e for e in t.log if e[:2] == ("vset", "EXPERT")]
        assert r.busy

    def test_no_expert_dance_when_the_command_just_works(self):
        t = FakeTransport(mode="verbose", release=B, verbose_values={"USERS": "1"})
        before, after = _cfg_pair(lambda b, a: setattr(a.hf_packet, "users", 3))
        ParamApplier(t).apply(before, after)
        assert not [e for e in t.log if e[:2] == ("vset", "EXPERT")]

    def test_a_second_expert_answer_is_reported_not_repeated_forever(self):
        class Stubborn(ExpertTransport):
            def verbose_set(self, name, value):
                self.log.append(("vset", name, value))
                return EXPERT_ANSWER_A if name == "ILFPACK" else ""
        t = Stubborn()
        (r,) = self._apply(t)
        assert not r.ok
        assert [e[1:] for e in t.log if e[0] == "vset"].count(("ILFPACK", "OFF")) == 2
        assert [e[1:] for e in t.log if e[0] == "vset"][-1] == ("EXPERT", "OFF")


def test_the_real_answer_line_is_what_the_log_shows():
    log = SRC.parents[1] / "hw_logs" / "20261006_145938_eol_probe.log"
    if log.exists():                 # hw_logs/ is not versioned
        assert re.search(r"\?EXPERT command", log.read_text(encoding="utf-8"))
