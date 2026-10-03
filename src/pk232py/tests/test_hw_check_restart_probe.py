# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""Unit tests for tools/hw_check.py's restart_probe measurement (P81, T168):
the pure evaluation helpers, the operator plan, the --dry-run path (no port
opened, nothing sent) and the "crash" that must close the port WITHOUT the
clean shutdown (no HOST OFF).

tools/ is not a package - see test_hw_check.py for why sys.path is extended.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from pk232py.config import AppConfig

_TOOLS_DIR = Path(__file__).resolve().parents[3] / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import hw_check  # noqa: E402

_APP = QApplication.instance() or QApplication(sys.argv[:1])

_CSTATUS = (
    "cmd:CSTATUS\r\n"
    "Ch. 0 - IO CONNECTED to OE3GAS-2; v2\r\n"
    "Ch. 1 - CONNECTED to OE3GAS-1; v2\r\n"
    "Ch. 2 - DISCONNECTED\r\n"
)


class TestClassifyUploadAnswer:
    def test_a_was_now_answer_is_ok(self):
        assert hw_check.classify_upload_answer(
            "MAXFRAME 4", True, b"MAXFRAME 4\r\nMAXFRAME was 7\r\ncmd:") == "ok"

    def test_not_while_connected_is_rejected(self):
        assert hw_check.classify_upload_answer(
            "MYCALL OE3GAS", True, b"MYCALL OE3GAS\r\n?not while connected\r\ncmd:") == "rejected"

    def test_what_is_rejected(self):
        assert hw_check.classify_upload_answer(
            "FOO 1", True, b"FOO 1\r\n*** What?\r\ncmd:") == "rejected"

    def test_no_prompt_is_silent(self):
        assert hw_check.classify_upload_answer("PACKET", False, b"") == "silent"

    def test_the_echoed_command_is_not_an_error_text(self):
        # "WHAT" inside a command echo must not count as 'what?'
        assert hw_check.classify_upload_answer(
            "MYTEXT what", True, b"MYTEXT what\r\ncmd:") == "ok"


class TestLinksAndVerdict:
    def test_links_from_cstatus_keeps_only_channels_with_a_partner(self):
        assert hw_check.links_from_cstatus(_CSTATUS) == {0: "OE3GAS-2", 1: "OE3GAS-1"}

    def test_verdict_names_a_lost_link_and_rejections(self):
        text = hw_check.restart_probe_verdict(
            {0: "A", 1: "B"}, {1: "B"}, ["MYCALL OE3GAS"])
        assert "upload LOST ch0" in text and "1 command(s) rejected" in text

    def test_verdict_when_all_is_kept(self):
        text = hw_check.restart_probe_verdict({0: "A"}, {0: "A"}, [])
        assert "init kept links" in text and "upload kept the links" in text
        assert "no command rejected" in text

    def test_verdict_does_not_guess_when_not_measurable(self):
        assert "not measurable" in hw_check.restart_probe_verdict(None, None, [])

    def test_no_links_found_is_said_so(self):
        assert "NO links found" in hw_check.restart_probe_verdict({}, {}, [])


class TestPlan:
    def test_variants(self):
        assert hw_check.restart_probe_variants("all") == ["A", "B0", "B", "C"]
        assert hw_check.restart_probe_variants("B") == ["B"]
        assert hw_check.restart_probe_variants("B0") == ["B0"]
        with pytest.raises(ValueError):
            hw_check.restart_probe_variants("D")

    def test_b0_has_no_step_of_its_own_it_involves_no_connection(self):
        keys = [k for k, _ in hw_check.restart_probe_steps("B0", "OE3GAS")]
        assert keys == ["start"]               # only the preparation questions

    def test_every_question_is_a_planned_framed_step(self):
        """T168 B, 22:59:18: a question vanished between log lines. Every
        question belongs to a step: start (callsign, ready), connect (y/n),
        check (alive?), cleanup (DI y/n per channel); the call step ends with ENTER."""
        keys = [k for k, _ in hw_check.restart_probe_steps("A", "OE3GAS")]
        assert keys == ["start", "A.connect", "A.call", "A.check", "A.cleanup"]
        steps = hw_check.restart_probe_steps("all", "OE3GAS")
        assert len(steps) == 1 + 3 * 4
        assert all(step.do and step.then for _, step in steps)
        assert steps[0][1].where == hw_check.WHERE_PC1

    def test_a_step_is_shown_only_after_the_queued_log_lines_settled(self, monkeypatch):
        log = hw_check.RunLog(None)
        session = hw_check.Session("DRYRUN", 9600, True, log, AppConfig())
        plan = hw_check._rp_plan("A", "OE3GAS", log)
        order: list = []
        monkeypatch.setattr(session, "_pump", lambda seconds: order.append(("pump", seconds)))
        monkeypatch.setattr(plan, "show", lambda key: order.append(("show", key)))
        hw_check._rp_show(session, plan, "start")
        assert order == [("pump", 0.5), ("show", "start")]


class TestDebugLinesStayInTheFile:
    def test_comm_debug_lines_are_not_printed_but_logged(self, tmp_path, capsys):
        import logging
        path = tmp_path / "run.log"
        log = hw_check.RunLog(path)
        handler = hw_check._RunLogHandler(log)
        record = logging.LogRecord("pk232py.comm", logging.DEBUG, __file__, 1,
                                   "Init: step 1 response", None, None)
        handler.emit(record)
        log.line("a normal line")
        log.close()
        out = capsys.readouterr().out
        assert "Init: step 1 response" not in out
        assert "a normal line" in out
        text = path.read_text(encoding="utf-8")
        assert "Init: step 1 response" in text and "a normal line" in text


class TestDryRun:
    def test_dry_run_sends_nothing_and_walks_the_plan(self, capsys):
        log = hw_check.RunLog(None)
        session = hw_check.Session("DRYRUN", 9600, True, log, AppConfig())
        hw_check.test_restart_probe(session, log, "all", AppConfig())
        out = capsys.readouterr().out
        assert "STEP 13 of 13" in out
        assert not session.sm.is_connected


class TestInitChainIsObserved:
    def test_the_wait_is_long_enough_for_the_whole_detection_chain(self):
        """T168 B: the first run waited 8 s and called a slow chain 'no answer'."""
        assert hw_check._RP_INIT_WAIT >= 30.0

    def test_the_restarted_app_keeps_the_byte_capture(self, monkeypatch):
        log = hw_check.RunLog(None)
        session = hw_check.Session("DRYRUN", 9600, True, log, AppConfig())
        factory = lambda **kw: None            # noqa: E731
        session.port_factory = factory
        monkeypatch.setattr(hw_check.time, "sleep", lambda s: None)
        old = session.sm
        hw_check._rp_simulate_crash(session, log)
        assert session.sm is not old
        assert session.sm._port_factory is factory

    def test_a_failed_init_stops_the_run_and_says_power_cycle(self, monkeypatch, capsys):
        log = hw_check.RunLog(None)
        session = hw_check.Session("DRYRUN", 9600, True, log, AppConfig())
        calls: list = []

        def fake_variant(sess, lg, v, *a):
            calls.append(v)
            return v != "B0"                   # B0 fails

        monkeypatch.setattr(hw_check, "_rp_variant", fake_variant)
        monkeypatch.setattr(hw_check, "parse_query_value", lambda *a: "VAL")
        monkeypatch.setattr(hw_check, "_channel_probe_vhf_check", lambda *a: {})
        monkeypatch.setattr(session, "normalize", lambda: None)
        monkeypatch.setattr(session, "query", lambda *a: "x")
        session.dry_run = False
        answers = iter(["", "y"])
        monkeypatch.setattr("builtins.input", lambda *a: next(answers))
        hw_check.test_restart_probe(session, log, "all", AppConfig())
        assert calls == ["A", "B0"]            # B and C never started
        assert "POWER-CYCLE" in capsys.readouterr().out


class TestCrashIsNotACleanShutdown:
    def test_port_is_closed_without_host_off(self, monkeypatch):
        written: list = []

        class Port:
            is_open = True
            closed = False

            def write(self, data):
                written.append(data)

            def close(self):
                self.closed = True
                self.is_open = False

        class Thread:
            stopped = False

            def stop(self):
                self.stopped = True

            def join(self, timeout=None):
                pass

        log = hw_check.RunLog(None)
        session = hw_check.Session("DRYRUN", 9600, True, log, AppConfig())
        old = session.sm
        port, reader = Port(), Thread()
        old._serial, old._reader = port, reader
        old._in_host_mode = True

        monkeypatch.setattr(hw_check.time, "sleep", lambda s: None)   # no real 1 s wait
        hw_check._rp_simulate_crash(session, log)

        assert port.closed and reader.stopped
        assert written == []                      # NO HOST OFF, no DISCONNECT
        assert session.sm is not old              # a fresh SerialManager: the restarted app
