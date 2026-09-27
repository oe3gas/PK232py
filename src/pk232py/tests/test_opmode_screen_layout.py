# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Unit tests for P56.B - every opmode screen must fill the window's
available height, with its last row (macro row, or the Packet screens'
status bar) landing near the bottom edge.

Measures actual geometry after a real resize()/show()/processEvents()
cycle, on a REAL MainWindow with the REAL widget nesting
(_opmode_stack -> QSplitter -> host_layout -> host_page) - P55 Teil E's
own lesson: a test that only checks whether a QSizePolicy is SET proves
nothing about the actual result. Reproduced 26.09.2026 (screenshot,
maximized window, 2560x1440): PacketBaseScreen's own top-level layout
gave its status bar HALF the available height (both it and the RX/TX
splitter had stretch=0, no tie-breaker) instead of the status bar's own
small natural size - the macro row, nested inside the splitter, ended
up near the middle of the screen instead of at the bottom. Fixed with
one added stretch=1 on the splitter. Every OTHER screen (Baudot/ASCII/
AMTOR/PACTOR/Morse/NAVTEX/Signal) already filled correctly - verified
below the same way, not assumed.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from pk232py.ui.main_window import MainWindow

_app = QApplication.instance() or QApplication([])

# A few pixels of margin/spacing below the last row is expected and
# fine - this is not asserting pixel-perfect zero gap, just that the
# screen's content actually reaches the bottom instead of stopping
# partway with a large empty area below it. For the Packet screens,
# the macro row is legitimately followed by the status bar (spec B.2:
# "the status line stays below it") - a ~20-30px gap there is that
# small bar's own natural height, not a bug; the original 26.09.2026
# regression left several HUNDRED pixels unaccounted for.
_MAX_GAP_PX = 40


def _last_row_bottom(screen) -> int:
    # macro_buttons[0] (present on every screen with a macro row -
    # Baudot/ASCII/AMTOR/PACTOR/Morse/Packet) is checked directly, not
    # just "whatever the top-level layout's last item happens to be" -
    # for the Packet screens specifically, the layout's own last item
    # is the STATUS BAR, which still reaches the window's bottom edge
    # even when oversized (P56.B's actual bug), so it would not have
    # caught this by itself. NAVTEX/Signal have no macro row at all
    # (receive-only) - fall back to the top-level layout's last item
    # for those two.
    buttons = getattr(screen, "macro_buttons", None)
    if buttons:
        geom = buttons[0].geometry()
        parent = buttons[0].parentWidget()
        # macro_buttons live in a nested QHBoxLayout inside a child
        # widget for Packet screens (tx_container) - map to screen
        # coordinates so the comparison against screen.height() is
        # meaningful regardless of nesting depth.
        top_left = parent.mapTo(screen, geom.topLeft()) if parent else geom.topLeft()
        return top_left.y() + geom.height()
    layout = screen.layout()
    last_item = layout.itemAt(layout.count() - 1)
    widget = last_item.widget()
    geom = widget.geometry() if widget else last_item.layout().geometry()
    return geom.y() + geom.height()


@pytest.mark.parametrize("mode_name", [
    "Baudot RTTY", "ASCII RTTY", "AMTOR ARQ", "PACTOR",
    "CW / Morse", "NAVTEX", "Signal (SIAM)",
    "HF Packet", "VHF Packet",
])
def test_screen_fills_the_window_last_row_near_the_bottom(mode_name):
    # P61: no manual removeEventFilter()/close()/deleteLater() here
    # anymore - conftest.py's dispose_main_windows autouse fixture does
    # this generically for every MainWindow any test built.
    w = MainWindow()
    w.resize(1600, 1200)
    w.show()
    _app.processEvents()
    _app.processEvents()
    w._stack.setCurrentIndex(0)  # Host Mode page (opmode screens live here)
    w._opmode_stack.setCurrentWidget(w._opmode_screens[mode_name])
    _app.processEvents()
    _app.processEvents()

    screen = w._opmode_screens[mode_name]
    bottom = _last_row_bottom(screen)
    gap = screen.height() - bottom

    assert gap <= _MAX_GAP_PX, (
        f"{mode_name}: last row bottom={bottom}, "
        f"screen height={screen.height()}, gap={gap}px"
    )


def test_packet_screen_status_bar_keeps_its_own_small_height():
    # The specific regression this closes: the status bar must NOT
    # absorb the splitter's own extra space - its own natural height,
    # not a share of the leftover window height.
    w = MainWindow()
    w.resize(1600, 1200)
    w.show()
    _app.processEvents()
    _app.processEvents()
    w._stack.setCurrentIndex(0)
    w._opmode_stack.setCurrentWidget(w._opmode_screens["HF Packet"])
    _app.processEvents()
    _app.processEvents()

    screen = w._opmode_screens["HF Packet"]
    assert screen._status_bar.height() < 60, (
        f"status bar height={screen._status_bar.height()}px "
        "- absorbed extra space instead of staying at its own "
        "small natural height"
    )
