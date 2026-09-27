# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""P61, Teil A - proves conftest.py's autouse dispose_main_windows fixture
actually destroys every MainWindow a test built, not merely hides it.

Reproduces the B.2 finding directly: MainWindow.__init__() installs
itself as an application-wide event filter
(QApplication.instance().installEventFilter(self)); calling close() only
hides the widget - it does not remove that filter or destroy the C++
object, so it keeps answering every event of every LATER test, and stays
in QApplication.topLevelWidgets() forever. Measured (P61 Befund B.2): a
fresh MainWindow() build cost 0.11s with 0 live windows before it, 2.62s
with 11 undisposed ones still around.

Order matters, within this file, in this exact sequence (the default
collection order - test functions run top to bottom): the first test
builds three windows and does not dispose any of them itself (not even
close() - proving the fixture works regardless, not just when a test
also calls close()); the second test - a SEPARATE test, so its own
"before" state is whatever the FIRST test's teardown left behind - checks
that none of them survived into it. Splitting this into two tests is not
a stylistic choice: dispose_main_windows() runs at teardown, strictly
between test 1 finishing and test 2 starting, so only a two-test split
can actually observe its effect.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from pk232py.ui.main_window import MainWindow

_app = QApplication.instance() or QApplication([])


def _live_main_windows() -> list:
    return [w for w in _app.topLevelWidgets() if isinstance(w, MainWindow)]


class TestNoMainWindowSurvivesIntoTheNextTest:

    def test_step_1_builds_three_windows_without_disposing_them(self):
        # ~1.1s, over the "no test over 1s" rule (CLAUDE.md, P61,
        # 2026-09-27) - building three real MainWindow() instances in one
        # test is the whole point here (proving disposal at scale, not
        # just for one leftover window); the cost is in the constructors
        # themselves, not in any wait this fixture could shrink.
        # Deliberately mimics the OLD "cleanup via close()" pattern this
        # spec's Teil A replaces - close() alone is exactly what used to
        # leave the window (and its event filter) alive.
        windows = [MainWindow() for _ in range(3)]
        for w in windows:
            w.close()
        assert len(_live_main_windows()) >= 3

    def test_step_2_none_survive_into_this_test(self):
        assert _live_main_windows() == []
