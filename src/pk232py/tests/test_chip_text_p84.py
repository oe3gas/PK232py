# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""P84 - the text of the channel chips (MON, 0-9) is white in every theme.

The chip fills are theme-independent (_CHIP_FILL, _MON_CHIP_FILL), so the text
must be too (operator rule). Measured on the palette the label is actually
drawn with (label.palette() after polish), not on a stylesheet string: the bug
was a QLabel with NO colour of its own, which took WindowText from the
application palette and so changed with every theme.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

from pk232py.ui.main_window import MainWindow
from pk232py.ui.screens.packet_screen import CH_CALLING, CH_CONNECTED
from pk232py.ui.themes import THEME_ORDER

_app = QApplication.instance() or QApplication([])

WHITE = QColor("#ffffff")


@pytest.fixture
def win():
    return MainWindow()


def painted_text_colors(bar) -> dict:
    """{'MON.num': QColor, ...} - the colour each chip label is drawn with."""
    out = {}
    for channel, chip in bar._chips.items():
        for name, label in (("num", chip._lbl_num), ("call", chip._lbl_call)):
            label.ensurePolished()
            out[f"{channel}.{name}"] = label.palette().color(QPalette.ColorRole.WindowText)
    return out


def not_white(bar) -> dict:
    return {k: c.name() for k, c in painted_text_colors(bar).items() if c != WHITE}


@pytest.mark.parametrize("key", THEME_ORDER)
def test_chip_text_is_white_in_every_theme(win, key):
    bar = win._opmode_screens["HF Packet"].channel_bar
    win._on_theme_selected(key)
    assert not_white(bar) == {}, f"theme {key}"


def test_chip_text_stays_white_through_all_themes_and_back(win):
    """Takes about 1 s on purpose: 8 real theme switches, and every switch
    re-styles the whole MainWindow (that is exactly what is being measured)."""
    bar = win._opmode_screens["HF Packet"].channel_bar
    sequence = list(THEME_ORDER) + list(reversed(THEME_ORDER))
    for key in sequence:
        win._on_theme_selected(key)
        assert not_white(bar) == {}, f"after switching to {key}"


def test_chip_text_stays_white_for_busy_chips(win):
    bar = win._opmode_screens["HF Packet"].channel_bar
    bar.set_channel_state(1, CH_CONNECTED, "OE3AAA")
    bar.set_channel_state(2, CH_CALLING, "OE3BBB")
    for key in THEME_ORDER:
        win._on_theme_selected(key)
        assert not_white(bar) == {}, f"theme {key}"
