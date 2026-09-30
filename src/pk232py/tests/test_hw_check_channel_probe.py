# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Unit tests for tools/hw_check.py's channel_probe measurement (P69):
the pure decoder-paste evaluation and the --dry-run path (no port
opened, nothing sent) - the same "measures only" boundary as the rest of
hw_check.py.

tools/ has no __init__.py and is not part of the installed package - see
test_hw_check.py's own docstring for why sys.path is extended here
instead of a regular import.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from PyQt6.QtWidgets import QApplication

from pk232py.config import AppConfig

_TOOLS_DIR = Path(__file__).resolve().parents[3] / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import hw_check  # noqa: E402

_APP = QApplication.instance() or QApplication(sys.argv[:1])

_TEXT = "P69 B1 ch3 12:00:00"


def _dry_run_session() -> tuple["hw_check.Session", "hw_check.RunLog"]:
    log = hw_check.RunLog(None)
    session = hw_check.Session("DRYRUN", 9600, True, log, AppConfig())
    return session, log


class TestClassifyDecoderLine:
    def test_ui_line_with_text_is_ui(self):
        pasted = f"[0.4] OE3GAS>P69TST:{_TEXT}<0x0d>"
        assert hw_check.classify_decoder_line(
            pasted, "OE3GAS", "P69TST", _TEXT) == "ui"

    def test_missing_text_is_absent(self):
        pasted = "[0.4] OE3GAS>P69TST:something else"
        assert hw_check.classify_decoder_line(
            pasted, "OE3GAS", "P69TST", _TEXT) == "absent"

    def test_empty_paste_is_absent(self):
        assert hw_check.classify_decoder_line("", "OE3GAS", "P69TST", _TEXT) == "absent"

    def test_unknown_format_is_unknown(self):
        pasted = f"garbage without a header {_TEXT}"
        assert hw_check.classify_decoder_line(
            pasted, "OE3GAS", "P69TST", _TEXT) == "unknown"

    def test_learned_iframe_marker_is_connected(self):
        pasted = (
            "Fm OE3GAS To OE3GAS-1 <I S0 R0 pid=F0 Len=1 >\n"
            f"[0.4] OE3GAS>OE3GAS-1:{_TEXT}"
        )
        marker = hw_check.learn_iframe_marker(pasted)
        assert marker == "<I "
        assert hw_check.classify_decoder_line(
            pasted, "OE3GAS", "P69TST", _TEXT, marker) == "connected"

    def test_ui_notation_is_not_learned_as_iframe(self):
        assert hw_check.learn_iframe_marker("Fm A To B <UI pid=F0 Len=1 >") is None

    def test_blank_line_separates_packets(self):
        # The I-frame marker of ANOTHER packet must not turn this UI
        # packet into 'connected'.
        pasted = (
            "Fm OE3GAS To OE3GAS-1 <I S0 R0 pid=F0 Len=1 >\n"
            "[0.4] OE3GAS>OE3GAS-1:\n\n"
            f"[0.5] OE3GAS>P69TST:{_TEXT}"
        )
        assert hw_check.classify_decoder_line(
            pasted, "OE3GAS", "P69TST", _TEXT, "<I ") == "ui"


class TestIncomingChannelAndLinks:
    def test_incoming_channel_from_connected_link_message(self):
        frames = [
            SimpleNamespace(ctl=0x30, channel=0, text="hello"),
            SimpleNamespace(ctl=0x53, channel=3, text="*** CONNECTED to OE3GAS-2"),
        ]
        assert hw_check.find_incoming_channel(frames) == 3

    def test_no_link_message_is_none(self):
        assert hw_check.find_incoming_channel(
            [SimpleNamespace(ctl=0x30, channel=0, text="CONNECTED to X")]) is None

    def test_links_line_shows_free_and_connected(self):
        LS = hw_check.LinkStatus
        line = hw_check.format_links_line({
            0: LS(channel=0, state=1),
            1: LS(channel=1, state=5, connected=True, partner="OE3GAS-1"),
            2: LS(channel=2, unparsed=True),
        })
        assert line == "links: 0=free 1=connected:OE3GAS-1 2=?"


class TestChannelProbeDryRun:
    def test_dry_run_touches_no_port(self):
        session, log = _dry_run_session()
        hw_check.test_channel_probe(session, log)
        assert session.sm.is_connected is False
        assert ("T146", "INFO", "dry-run, nothing sent") in log.findings
        assert ("T147", "INFO", "dry-run, nothing sent") in log.findings

    def test_dry_run_shows_the_planned_frames(self, capsys):
        session, log = _dry_run_session()
        hw_check.test_channel_probe(session, log)
        out = capsys.readouterr().out
        assert "UN P69TST" in out
        assert hw_check.HostModeProtocol.cmd_unproto("P69TST").hex(" ").upper() in out
        assert "$23" in out and "$29" in out
        connect = hw_check.HostModeProtocol.cmd_connect("OE3GAS-1", channel=0)
        assert connect.hex(" ").upper() in out
        assert "USERS 10" in out
        assert "confirm_tx()" in out


class TestEveryTransmissionIsGated:
    """The two helpers are the ONLY places channel_probe transmits."""

    def _session(self):
        sent = []
        return SimpleNamespace(
            send_data_channel=lambda ch, text: sent.append(("data", ch, text)),
            send_channel_frame=lambda ch, frame, note="": sent.append(("frame", ch)),
        ), sent

    def test_declined_data_frame_is_not_sent(self, monkeypatch):
        monkeypatch.setattr(hw_check, "confirm_tx", lambda prompt: False)
        session, sent = self._session()
        log = hw_check.RunLog(None)
        assert hw_check._probe_transmit(session, log, "p", 3, "x") is False
        assert sent == []

    def test_confirmed_data_frame_is_sent(self, monkeypatch):
        monkeypatch.setattr(hw_check, "confirm_tx", lambda prompt: True)
        session, sent = self._session()
        log = hw_check.RunLog(None)
        assert hw_check._probe_transmit(session, log, "p", 3, "x") is True
        assert sent == [("data", 3, "x")]

    def test_declined_connect_is_not_sent(self, monkeypatch):
        monkeypatch.setattr(hw_check, "confirm_tx", lambda prompt: False)
        session, sent = self._session()
        log = hw_check.RunLog(None)
        assert hw_check._probe_connect(session, log, "OE3GAS-1", 0) is False
        assert sent == []


# ---------------------------------------------------------------------------
# P69a - operator guidance, part selection, paste split, ensure_vhf_1200
# ---------------------------------------------------------------------------

import re  # noqa: E402

import pytest  # noqa: E402


def _headers(out: str) -> list[tuple[int, int]]:
    return [(int(n), int(t)) for n, t in re.findall(r"^STEP (\d+) of (\d+) ", out, re.M)]


class TestOperatorStep:
    def _run(self, where=None):
        step = hw_check.ProbeStep(
            "T146 B.3 demo", where or hw_check.WHERE_PC2, 2,
            ["Look at the Direwolf window.", "Nothing to type there."],
            "go back to PC 1 and press ENTER here.",
        )
        return hw_check.StepRun([step]), step

    def test_output_has_number_where_do_and_then(self, capsys):
        run, s = self._run()
        hw_check.operator_step(run, s.title, s.where, s.do, s.then)
        out = capsys.readouterr().out
        assert "STEP 1 of 1   T146 B.3 demo   (about 2 minutes)" in out
        assert out.count("WHERE: ") == 1
        assert f"WHERE: {hw_check.WHERE_PC2}" in out
        assert "  1. Look at the Direwolf window." in out
        assert "  2. Nothing to type there." in out
        assert "THEN: go back to PC 1 and press ENTER here." in out

    def test_only_the_two_fixed_where_texts_are_accepted(self):
        run, s = self._run()
        with pytest.raises(ValueError):
            hw_check.operator_step(run, s.title, "PC 3 - somewhere", s.do, s.then)

    def test_step_beyond_the_plan_is_an_error(self):
        run, s = self._run()
        hw_check.operator_step(run, s.title, s.where, s.do, s.then)
        with pytest.raises(hw_check.HWCheckError):
            hw_check.operator_step(run, s.title, s.where, s.do, s.then)

    def test_step_title_is_logged(self):
        log = hw_check.RunLog(None)
        step = hw_check.ProbeStep("T1 x", hw_check.WHERE_PC1, 1, ["a"], "b")
        run = hw_check.StepRun([step], log)
        hw_check.operator_step(run, step.title, step.where, step.do, step.then)
        assert run.n == 1 and run.current is step


class TestPartSelection:
    @pytest.mark.parametrize("part,total", [("B", 4), ("C", 11), ("all", 15)])
    def test_n_matches_printed_steps(self, part, total, capsys):
        session, log = _dry_run_session()
        hw_check.test_channel_probe(session, log, part)
        heads = _headers(capsys.readouterr().out)
        assert [n for n, _ in heads] == list(range(1, total + 1))
        assert {t for _, t in heads} == {total}

    def test_part_b_has_no_part_c_step(self, capsys):
        session, log = _dry_run_session()
        hw_check.test_channel_probe(session, log, "B")
        out = capsys.readouterr().out
        assert not re.search(r"^STEP \d+ of \d+ +T147", out, re.M)

    def test_part_c_has_no_part_b_step(self, capsys):
        session, log = _dry_run_session()
        hw_check.test_channel_probe(session, log, "C")
        assert not re.search(r"^STEP \d+ of \d+ +T146", capsys.readouterr().out, re.M)

    def test_every_dry_run_step_has_where_do_then(self, capsys):
        session, log = _dry_run_session()
        hw_check.test_channel_probe(session, log, "all")
        out = capsys.readouterr().out
        assert out.count("WHERE: ") == out.count("DO:") == out.count("THEN: ") == 15


class TestSplitPasteByMarker:
    M = {"B.1": "P69 B1 ch3 10:00:00", "B.2": "P69 B2 ch9 10:00:05",
         "B.3": "P69 B3 ch3 10:00:10"}

    PASTE = (
        "noise before\n\n"
        "Fm OE3GAS To P69TST <UI pid=F0>\n[0.4] OE3GAS>P69TST:P69 B1 ch3 10:00:00\n\n"
        "Fm OE3GAS To P69TST <UI pid=F0>\n[0.4] OE3GAS>P69TST:P69 B2 ch9 10:00:05\n\n"
        "Fm OE3GAS To P69TST <UI pid=F0>\n[0.4] OE3GAS>P69TST:P69 B3 ch3 10:00:10\n\n"
        "Fm OE3GAS To OE3GAS-1 <I S0 R0 pid=F0>\n[0.4] OE3GAS>OE3GAS-1:\n"
    )

    def test_segments_are_assigned_to_their_steps(self):
        seg, missing = hw_check.split_paste_by_marker(self.PASTE, self.M)
        assert missing == []
        assert self.M["B.1"] in seg["B.1"] and self.M["B.2"] not in seg["B.1"]
        assert self.M["B.2"] in seg["B.2"] and self.M["B.3"] not in seg["B.2"]
        assert self.M["B.3"] in seg["B.3"] and "<I S0" in seg["B.3"]
        assert "noise before" not in seg["B.1"]

    def test_missing_marker_is_reported(self):
        seg, missing = hw_check.split_paste_by_marker(
            self.PASTE.replace(self.M["B.2"], "other"), self.M)
        assert missing == ["B.2"] and "B.2" not in seg
        assert self.M["B.1"] in seg["B.1"]


class TestEnsureVhf1200Prompt:
    def _call(self, monkeypatch, answer):
        monkeypatch.setattr("builtins.input", lambda prompt="": answer)
        sets = []
        session = SimpleNamespace(set_verbose=lambda c, v: sets.append((c, v)))
        log = hw_check.RunLog(None)
        ok = hw_check.ensure_vhf_1200(
            session, log, "T146", {"VHF": "OFF", "HBAUD": "300"})
        return ok, sets, log

    def test_y_sets_vhf_and_hbaud(self, monkeypatch):
        ok, sets, _ = self._call(monkeypatch, "y")
        assert ok is True and sets == [("VHF", "ON"), ("HBAUD", "1200")]

    def test_n_aborts_with_info(self, monkeypatch):
        ok, sets, log = self._call(monkeypatch, "n")
        assert ok is False and sets == []
        assert log.findings[-1][:2] == ("T146", "INFO")

    def test_already_1200_does_not_ask(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda p="": pytest.fail("asked"))
        session = SimpleNamespace(set_verbose=lambda c, v: pytest.fail("set"))
        assert hw_check.ensure_vhf_1200(
            session, hw_check.RunLog(None), "T", {"VHF": "ON", "HBAUD": "1200"})


class TestWaitForEnter:
    def test_enter_ends_the_wait_and_pumps_meanwhile(self):
        pumped, keys = [], iter([False, False, True])
        ok = hw_check.wait_for_enter(
            lambda s: pumped.append(s), 120.0,
            key_ready=lambda: next(keys), read_line=lambda: "",
        )
        assert ok is True and len(pumped) == 2

    def test_times_out_after_max_seconds(self, capsys):
        now = [0.0]

        def pump(s):
            now[0] += s

        ok = hw_check.wait_for_enter(
            pump, 1.0, key_ready=lambda: False, read_line=lambda: "",
            clock=lambda: now[0],
        )
        assert ok is False
        assert "continuing by itself" in capsys.readouterr().out


class TestChecklist:
    def test_part_b_has_no_qtermtcp_item(self):
        items = hw_check.channel_probe_checklist("B", "OE3GAS-1")
        assert not any("QtTermTCP" in i for i in items)
        assert any("TinyBox OE3GAS-1" in i for i in items)

    def test_part_c_needs_both_sessions_disconnected(self):
        items = hw_check.channel_probe_checklist("C", "OE3GAS-1")
        assert any("OE3GAS-2" in i and "OE3GAS-3" in i and "disconnected" in i
                   for i in items)
