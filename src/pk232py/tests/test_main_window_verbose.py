# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Unit tests for MainWindow's verbose terminal (P44 Teil B).

Covers:
  - B.1 — an empty Enter sends a bare CR instead of doing nothing
  - B.2 is covered by SerialManager.last_verbose_init_response's own
    plumbing (test_serial_manager.py); the UI-side mirror itself needs a
    live connect sequence and is left to the operator's hardware re-test
    (Testplan.md).

Needs a QApplication; forced to the offscreen platform (see
test_packet_screen.py for why this is done at module level, before any
PyQt6 import).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from pk232py.ui.main_window import MainWindow

_app = QApplication.instance() or QApplication([])


class _StubSerial:
    """Minimal stand-in - only what _on_vt_send()/_vt_send_raw() touch."""

    is_connected = True
    is_host_mode = False

    def __init__(self):
        self.writes: list[bytes] = []

    def write_verbose(self, data: bytes) -> bool:
        self.writes.append(data)
        return True


@pytest.fixture
def wired_window():
    w = MainWindow()
    w._serial = _StubSerial()
    yield w, w._serial
    # P61: teardown used to call close()/deleteLater()/processEvents()
    # here itself - now the conftest.py-wide dispose_main_windows autouse
    # fixture does this generically for every MainWindow any test built,
    # never via close() (which would run closeEvent(), popping a real,
    # unclickable QMessageBox.question() under the offscreen QPA
    # platform whenever a stub's is_connected happens to read True).


class TestVerboseTerminalBareEnter:
    """P44.B1 - Enter on an empty verbose-terminal field sends a bare CR,
    the usual harmless way to fetch the cmd: prompt again, instead of
    doing nothing at all (the old behaviour)."""

    def test_empty_enter_sends_exactly_one_bare_cr(self, wired_window):
        w, serial = wired_window
        w._vt_input.clear()

        w._on_vt_send()

        assert serial.writes == [b"\r"]

    def test_whitespace_only_enter_also_sends_bare_cr(self, wired_window):
        w, serial = wired_window
        w._vt_input.setPlainText("   ")

        w._on_vt_send()

        assert serial.writes == [b"\r"]

    def test_nonempty_enter_still_sends_the_command_with_cr_only(self, wired_window):
        w, serial = wired_window
        w._vt_input.setPlainText("MYCALL")

        w._on_vt_send()

        assert serial.writes == [b"MYCALL\r"]


class TestInputFollowsTheTncPrompt:
    """The TNC's own prompt is already on screen when the operator types
    (Device A screenshot, 06.10.2026: from the second input on the display
    read 'cmd:cmd:ilfpack'). The typed line must continue that prompt."""

    @staticmethod
    def _text(w) -> str:
        return w._vt_display.toPlainText()

    @staticmethod
    def _type(w, text: str) -> None:
        w._vt_input.setPlainText(text)
        w._on_vt_send()

    def test_input_continues_the_prompt_the_tnc_showed(self, wired_window):
        w, _serial = wired_window
        w._on_vt_rx_data(b"\r\nILfpack   ON\r\ncmd:")
        self._type(w, "ilfpack")
        assert w._vt_display.document().lastBlock().previous().text() == "cmd:ilfpack"
        assert "cmd:cmd:" not in self._text(w)

    def test_second_and_third_input_never_double_the_prompt(self, wired_window):
        w, _serial = wired_window
        w._on_vt_rx_data(b"cmd:")
        self._type(w, "ilfpack")
        w._on_vt_rx_data(b"ilfpack\r\nILfpack   ON\r\ncmd:")
        self._type(w, "users")
        w._on_vt_rx_data(b"users\r\nUSers     1\r\ncmd:")
        self._type(w, "paclen")
        assert "cmd:cmd:" not in self._text(w)
        lines = self._text(w).splitlines()
        assert [ln for ln in lines if ln.startswith("cmd:") and len(ln) > 4] == [
            "cmd:ilfpack", "cmd:users", "cmd:paclen"]

    def test_without_a_prompt_on_screen_the_line_still_shows_one(self, wired_window):
        # first input of a cleared display: nothing from the TNC yet
        w, _serial = wired_window
        w._vt_display.clear()
        self._type(w, "ilfpack")
        assert self._text(w).splitlines()[0] == "cmd:ilfpack"

    def test_what_is_sent_is_unchanged(self, wired_window):
        w, serial = wired_window
        w._on_vt_rx_data(b"cmd:")
        self._type(w, "ilfpack")
        assert serial.writes == [b"ilfpack\r"]
