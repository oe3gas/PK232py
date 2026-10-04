# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""P81b (T169, second report) - the TinyBox prompt is not visible in the ALL view
although ALL was active the whole time (no CH -> ALL switch); a click on CH shows it.

This replays exactly that sequence through MainWindow with a real show()/resize()
and MEASURES: is the cursor rectangle of the last line inside the viewport? The
fix of P81a (restoring the scroll position on a view switch) cannot explain this
case. If these tests are green, the fault is not reproduced here and nothing is
"repaired" - the DEBUG line in PacketBaseScreen._rx_append() tells the next
hardware run whether the line does not arrive or only is not scrolled into view.
"""

from __future__ import annotations

import logging
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QApplication

from pk232py.modes.packet_vhf import VHFPacketMode
from pk232py.ui.main_window import MainWindow

_app = QApplication.instance() or QApplication([])

PROMPT = b"TinyBox (A,B,H,J,K,L,R,S,V,?) > "      # no CR, trailing space as sent


class _Stub:
    is_connected = True
    is_host_mode = True
    has_pactor = False
    verbose_confirmed = False
    fresh_boot_defaults = False

    def consume_fresh_boot_defaults(self):
        return False

    def send_channel_command(self, *a, **k):
        pass

    def send_command(self, *a, **k):
        pass


@pytest.fixture
def vhf_window():
    w = MainWindow()
    w._serial = _Stub()
    w._modes._active_mode = VHFPacketMode()
    screen = w._opmode_screens["VHF Packet"]
    w._opmode_stack.setCurrentWidget(screen)
    w._stack.setCurrentIndex(0)
    w._wire_mode_callbacks()
    w.resize(1100, 760)
    w.show()
    _app.processEvents()
    yield w, screen


def _last_line_rect_in_viewport(screen, needle: str):
    """(cursor rectangle of the last occurrence of *needle*, viewport rect)."""
    edit = screen.rx_display
    cursor = edit.document().find(needle, edit.document().characterCount() - 1,
                                  edit.document().FindFlag.FindBackward)
    assert not cursor.isNull(), f"{needle!r} is not in the shown document"
    cursor.setPosition(cursor.selectionStart())
    return edit.cursorRect(cursor), edit.viewport().rect()


def _replay(w, screen):
    assert screen.btn_view_all.isChecked() and screen._view_all   # ALL, all the time
    screen.channel_bar.set_current(1)
    _app.processEvents()
    w._route_packet_link_message(screen, 1, "*** CONNECTED to OE3GAS-1")
    for i in range(30):                      # enough lines to need scrolling
        w._on_packet_data_received(1, f"Welcome line {i}\r".encode())
    w._on_packet_data_received(1, PROMPT)
    _app.processEvents()


def test_prompt_without_cr_is_inside_the_viewport_in_the_all_view(vhf_window):
    w, screen = vhf_window
    _replay(w, screen)
    assert screen.rx_display.document() is screen._rx_doc_all       # ALL is what is shown
    rect, viewport = _last_line_rect_in_viewport(screen, "TinyBox")
    assert viewport.contains(rect), f"prompt line at {rect}, viewport {viewport}"


def test_prompt_is_inside_the_viewport_in_the_ch_view_too(vhf_window):
    w, screen = vhf_window
    _replay(w, screen)
    screen.btn_view_ch.click()
    _app.processEvents()
    assert screen.rx_display.document() is screen._rx_docs[1]
    rect, viewport = _last_line_rect_in_viewport(screen, "TinyBox")
    assert viewport.contains(rect)


def test_the_mask_is_the_current_one_of_the_stack(vhf_window):
    w, screen = vhf_window
    assert w._opmode_stack.currentWidget() is screen and screen.isVisible()


def test_the_debug_line_says_what_happened(vhf_window, caplog):
    w, screen = vhf_window
    with caplog.at_level(logging.DEBUG, logger="pk232py.ui.screens.packet_screen"):
        w._on_packet_data_received(1, PROMPT)
    line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("RX append"))
    for part in ("ch=1", "shown='ALL'", "bar before=", "after=", "stack_current=True",
                 "visible=True", "TinyBox"):
        assert part in line, (part, line)


def test_control_the_measurement_can_fail(vhf_window):
    """Scrolled to the top, the prompt line must be OUTSIDE the viewport -
    otherwise the measurement above would prove nothing."""
    w, screen = vhf_window
    _replay(w, screen)
    screen.rx_display.verticalScrollBar().setValue(0)
    _app.processEvents()
    rect, viewport = _last_line_rect_in_viewport(screen, "TinyBox")
    assert not viewport.contains(rect)


# --- P81b second finding: only the FIRST appearance of the mask is wrong ------

def _fresh_window_first_host_mode_entry():
    """The real path: a fresh MainWindow, connected, the first Host Mode entry
    with VHF Packet remembered by the LinkTable. ModeManager activates the mode
    on its own 300 ms timer; the mask only becomes current after that."""
    import time
    w = MainWindow()
    w._serial = _Stub()
    w._modes._serial = w._serial
    w.resize(1100, 760)
    w.show()
    _app.processEvents()
    w._link_table.mode_name = "VHF Packet"
    w._update_host_mode_ui(True)
    deadline = time.monotonic() + 3.0
    while w._modes.current_mode_name != "VHF Packet" and time.monotonic() < deadline:
        _app.processEvents()
    for _ in range(20):
        _app.processEvents()
    return w, w._opmode_screens["VHF Packet"]


def test_first_appearance_of_the_mask_shows_the_all_document():
    w, screen = _fresh_window_first_host_mode_entry()
    assert w._opmode_stack.currentWidget() is screen
    assert screen.rx_display.document() is screen._rx_doc_all


def test_first_connect_prompt_is_inside_the_viewport_in_all():
    w, screen = _fresh_window_first_host_mode_entry()
    screen.channel_bar.set_current(1)
    _app.processEvents()
    w._route_packet_link_message(screen, 1, "*** CONNECTED to OE3GAS-1")
    for i in range(30):
        w._on_packet_data_received(1, f"Welcome line {i}\r".encode())
    w._on_packet_data_received(1, PROMPT)
    _app.processEvents()
    assert screen.rx_display.document() is screen._rx_doc_all
    rect, viewport = _last_line_rect_in_viewport(screen, "TinyBox")
    assert viewport.contains(rect)


def test_every_later_activation_keeps_the_all_document():
    """Leave for another mask and come back, both ways round."""
    w, screen = _fresh_window_first_host_mode_entry()
    w._switch_opmode("Baudot RTTY")
    w._switch_opmode("VHF Packet")
    assert screen.rx_display.document() is screen._rx_doc_all
    w._switch_opmode("HF Packet")
    hf = w._opmode_screens["HF Packet"]
    assert hf.rx_display.document() is hf._rx_doc_all
    w._switch_opmode("VHF Packet")
    assert screen.rx_display.document() is screen._rx_doc_all


def test_a_non_packet_mask_does_not_receive_a_packet_document():
    w, screen = _fresh_window_first_host_mode_entry()
    w._switch_opmode("Baudot RTTY")
    baudot = w._opmode_screens["Baudot RTTY"]
    assert baudot.rx_display.document() not in (screen._rx_doc_all, *screen._rx_docs.values())


def test_the_debug_line_carries_the_identity(caplog):
    w, screen = _fresh_window_first_host_mode_entry()
    with caplog.at_level(logging.DEBUG, logger="pk232py.ui.screens.packet_screen"):
        w._on_packet_data_received(1, PROMPT)
    line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("RX append"))
    assert "doc_is_all=True" in line, line
