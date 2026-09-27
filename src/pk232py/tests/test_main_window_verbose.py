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

    def test_nonempty_enter_still_sends_the_command_with_crlf(self, wired_window):
        w, serial = wired_window
        w._vt_input.setPlainText("MYCALL")

        w._on_vt_send()

        assert serial.writes == [b"MYCALL\r\n"]
