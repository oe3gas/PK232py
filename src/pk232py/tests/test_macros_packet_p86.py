# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""P86 - macro buttons in the Packet screens.

Before: MainWindow._on_macro_clicked() called tx.char_typed.emit() in every
screen. The Packet screens' tx_input is a plain QTextEdit without that signal
-> AttributeError inside the slot -> PyQt6 aborted the application. Every
macro button in HF/VHF Packet was affected.

Now: a tx_input WITHOUT char_typed (the capability, not a mode name) gets the
macro text inserted at the end, in the TX colour, NOT sent; the RTTY markers
[^D] and [^T:n] are removed with one note in the log. Screens whose tx_input
has char_typed (Baudot/ASCII/Morse/AMTOR) behave exactly as before.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import logging
from unittest.mock import MagicMock

import pytest
from PyQt6.QtGui import QColor, QTextCursor
from PyQt6.QtWidgets import QApplication

from pk232py.ui.main_window import MainWindow
from pk232py.ui.screens.packet_screen import CH_CONNECTED, MON_VIEW
from pk232py.ui.screens.ui_theme import get_theme

_app = QApplication.instance() or QApplication([])

# (macro text, what the Packet input must contain afterwards)
MACROS = [
    ("CQ CQ DE OE3GAS K",   "CQ CQ DE OE3GAS K"),
    ("QRZ?[^D]",            "QRZ?"),
    ("A[^T:5]B",            "AB"),
    ("L1\nL2",              "L1\nL2"),
    ("[^D]",                ""),
    ("X[^T:abc]Y",          "X[^T:abc]Y"),     # malformed marker: not a marker
]
PACKET_SCREENS = ["HF Packet", "VHF Packet"]
CHANNELS = ["mon", "free", "connected"]


def make_window(screen_name: str) -> tuple[MainWindow, object]:
    win = MainWindow()
    win._serial = MagicMock()
    screen = win._opmode_screens[screen_name]
    win._opmode_stack.setCurrentWidget(screen)
    win._wire_screen_buttons()
    for i, (text, _) in enumerate(MACROS):
        screen._macro_store.texts[i] = text
    return win, screen


def select(screen, where: str):
    bar = screen.channel_bar
    if where == "mon":
        bar.set_current(MON_VIEW)
    elif where == "free":
        bar.set_current(1)
    else:
        bar.set_channel_state(2, CH_CONNECTED, "OE3XYZ")
        bar.set_current(2)


def sent_anything(win) -> bool:
    names = ("send_data", "send_command", "send_channel_command", "write_verbose")
    return any(getattr(win._serial, n).called for n in names)


@pytest.mark.parametrize("where", CHANNELS)
@pytest.mark.parametrize("screen_name", PACKET_SCREENS)
@pytest.mark.parametrize("idx", range(len(MACROS)))
def test_macro_button_inserts_text_into_the_visible_input(screen_name, idx, where):
    win, screen = make_window(screen_name)
    select(screen, where)
    screen.macro_buttons[idx].click()          # the real path: clicked -> slot
    assert screen.tx_input.toPlainText() == MACROS[idx][1]
    assert not sent_anything(win)              # inserted, NOT sent


@pytest.mark.parametrize("screen_name", PACKET_SCREENS)
def test_text_is_appended_at_the_end_in_the_tx_colour(screen_name):
    win, screen = make_window(screen_name)
    tx = screen.tx_input
    tx.setPlainText("abc")
    cur = tx.textCursor()
    cur.setPosition(1)                         # cursor NOT at the end
    tx.setTextCursor(cur)
    screen.macro_buttons[0].click()
    assert tx.toPlainText() == "abc" + MACROS[0][1]
    assert tx.textCursor().position() == len(tx.toPlainText())
    probe = tx.textCursor()
    probe.setPosition(len("abc") + 1)          # inside the inserted text
    assert probe.charFormat().foreground().color() == QColor(get_theme()["tx_color"])


@pytest.mark.parametrize("screen_name", PACKET_SCREENS)
def test_macro_text_belongs_to_the_visible_channel_only(screen_name):
    win, screen = make_window(screen_name)
    select(screen, "free")                     # channel 1
    screen.macro_buttons[0].click()
    screen.channel_bar.set_current(MON_VIEW)
    assert screen.tx_input.toPlainText() == ""
    screen.channel_bar.set_current(1)
    assert screen.tx_input.toPlainText() == MACROS[0][1]


@pytest.mark.parametrize("screen_name", PACKET_SCREENS)
def test_removed_markers_leave_one_note_in_the_log(screen_name, caplog):
    win, screen = make_window(screen_name)
    with caplog.at_level(logging.INFO):
        screen.macro_buttons[2].click()        # "A[^T:5]B"
        screen.macro_buttons[0].click()        # no marker -> no note
    notes = [r for r in caplog.records if "removed" in r.getMessage()
             and "RTTY" in r.getMessage()]
    assert len(notes) == 1
    assert "[^T:5]" in notes[0].getMessage()


# --- the RTTY screens stay as they were ------------------------------------

def collect_char_typed(screen):
    seen = []
    screen.tx_input.char_typed.connect(lambda c, d, p: seen.append((c, d, p)))
    return seen


@pytest.mark.parametrize("screen_name", ["Baudot RTTY", "ASCII RTTY"])
def test_rtty_macro_still_emits_char_typed_with_markers(screen_name):
    win = MainWindow()
    screen = win._opmode_screens[screen_name]
    win._opmode_stack.setCurrentWidget(screen)
    win._wire_screen_buttons()
    screen._macro_store.texts[0] = "AB[^D]"
    seen = collect_char_typed(screen)
    screen.macro_buttons[0].click()
    assert seen == [("A", "A", 0), ("B", "B", 1), ("\x04", "[^D]", 2)]
    assert screen.tx_input.toPlainText() == "AB[^D]"


def test_rtty_timer_marker_still_emits_the_timer_code():
    win = MainWindow()
    screen = win._opmode_screens["Baudot RTTY"]
    win._opmode_stack.setCurrentWidget(screen)
    win._wire_screen_buttons()
    screen._macro_store.texts[0] = "A[^T:5]"
    seen = collect_char_typed(screen)
    screen.macro_buttons[0].click()
    assert seen == [("A", "A", 0), ("\x1b5", "[^T:5]", 1)]


def test_pactor_without_char_typed_does_not_crash_either():
    """PACTOR's tx_input is a plain QTextEdit too - same capability, same path."""
    win = MainWindow()
    name = next(k for k in win._opmode_screens if "PACTOR" in k.upper())
    screen = win._opmode_screens[name]
    assert not hasattr(screen.tx_input, "char_typed")
    win._opmode_stack.setCurrentWidget(screen)
    win._wire_screen_buttons()
    screen._macro_store.texts[0] = "CQ[^D]"
    screen.macro_buttons[0].click()
    assert screen.tx_input.toPlainText() == "CQ"
