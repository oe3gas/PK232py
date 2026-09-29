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
