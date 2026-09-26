# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Unit tests for pk232py.ui.tooltips.apply_tooltips() (P55.E).

Covers the size-policy assertion piggybacked onto apply_tooltips() -
every opmode screen's __init__() calls this exactly once, making it the
one shared place a fix reaches all of them without a second call site
in each screen's own file (see the function's own docstring for the
full reasoning and the "empty area below the macro buttons" this
defends against).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QSizePolicy, QWidget

from pk232py.ui.tooltips import apply_tooltips

_app = QApplication.instance() or QApplication([])


class TestApplyTooltipsSizePolicy:

    def test_sets_expanding_in_both_directions_on_a_plain_widget(self):
        w = QWidget()
        assert w.sizePolicy().verticalPolicy() != QSizePolicy.Policy.Expanding

        apply_tooltips(w)

        policy = w.sizePolicy()
        assert policy.verticalPolicy() == QSizePolicy.Policy.Expanding
        assert policy.horizontalPolicy() == QSizePolicy.Policy.Expanding

    def test_every_opmode_screen_ends_up_expanding(self):
        from pk232py.ui.screens.baudot_screen import BaudotScreen
        from pk232py.ui.screens.ascii_screen import AsciiScreen
        from pk232py.ui.screens.amtor_screen import AmtorScreen
        from pk232py.ui.screens.pactor_screen import PactorScreen
        from pk232py.ui.screens.morse_screen import MorseScreen
        from pk232py.ui.screens.navtex_screen import NavtexScreen
        from pk232py.ui.screens.signal_screen import SignalScreen
        from pk232py.ui.screens.fax_screen import FaxScreen
        from pk232py.ui.screens.packet_screen import HFPacketScreen, VHFPacketScreen

        for cls in (
            BaudotScreen, AsciiScreen, AmtorScreen, PactorScreen,
            MorseScreen, NavtexScreen, SignalScreen, FaxScreen,
            HFPacketScreen, VHFPacketScreen,
        ):
            screen = cls()
            policy = screen.sizePolicy()
            assert policy.verticalPolicy() == QSizePolicy.Policy.Expanding, cls.__name__
            assert policy.horizontalPolicy() == QSizePolicy.Policy.Expanding, cls.__name__
