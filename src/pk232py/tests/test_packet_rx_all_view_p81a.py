# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""P81a (T169 finding 1) - a prompt without CR must be visible in the ALL view.

The suspicion was that _rx_write_line() treats a started line differently for
the ALL document than for the channel document. It does not: both documents
get the same text (first test below, green from the start). The real fault was
the restored scroll position: leaving a view at its bottom and coming back
after lines had arrived elsewhere put the scrollbar at the OLD bottom, so the
new lines were below the visible area (found with a real show()/resize(),
CLAUDE.md rule 14).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from pk232py.ui.screens.packet_screen import HFPacketScreen

_app = QApplication.instance() or QApplication([])


@pytest.fixture
def screen():
    s = HFPacketScreen()
    s.resize(900, 500)
    s.show()
    _app.processEvents()
    yield s
    s.close()


def _bar(s):
    return s.rx_display.verticalScrollBar()


def test_prompt_without_cr_is_in_both_documents(screen):
    screen.append_channel_data(1, "TinyBox>")
    assert screen._rx_docs[1].toPlainText().strip() == "TinyBox>"
    assert screen._rx_doc_all.toPlainText().strip().endswith("TinyBox>")


def test_all_view_shows_the_prompt_after_a_trip_through_the_ch_view(screen):
    for i in range(40):
        screen.append_channel_data("MON", f"monitor {i}")
    _app.processEvents()
    screen.set_view_all(False)                       # CH view of channel 0
    _app.processEvents()
    screen.append_channel_data(1, "TinyBox>")        # no CR, as the TNC sends it
    for i in range(40):
        screen.append_channel_data("MON", f"monitor again {i}")
    screen.set_view_all(True)
    _app.processEvents()
    assert _bar(screen).value() == _bar(screen).maximum()


def test_a_view_the_operator_scrolled_up_stays_where_it_was(screen):
    for i in range(80):
        screen.append_channel_data("MON", f"monitor {i}")
    _app.processEvents()
    _bar(screen).setValue(100)
    screen.set_view_all(False)
    screen.set_view_all(True)
    _app.processEvents()
    assert _bar(screen).value() == 100
