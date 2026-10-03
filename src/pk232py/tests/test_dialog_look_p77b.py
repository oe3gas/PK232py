# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""P77b (findings of the T163 visual check):

  1. Dialogs keep the standard look - the display theme (Retro/Air/...) applies
     to the DISPLAY surfaces only (RX, TX, verbose terminal, Packet channels,
     MON).  The theme palette used to be set on the whole QApplication, so the
     Appearance dialog and the QColorDialog inherited it (unreadable).
  2. The colour picker is the platform dialog (no DontUseNativeDialog).
  3. The contrast shown next to each text colour depends on the font: WCAG asks
     3 : 1 for large text (>= 18 pt, or >= 14 pt bold), else 4.5 : 1.
"""

from __future__ import annotations

import os
import pathlib

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QApplication, QColorDialog, QMessageBox, QStyleFactory

from pk232py.colors import contrast_ratio, font_is_bold, required_contrast
from pk232py.config import AppearanceConfig
from pk232py.ui.appearance_dialog import AppearanceDialog
from pk232py.ui.main_window import MainWindow

_app = QApplication.instance() or QApplication([])

UI_DIR = pathlib.Path(__file__).resolve().parent.parent / "ui"
ROLES = (QPalette.ColorRole.Window, QPalette.ColorRole.WindowText,
         QPalette.ColorRole.Base, QPalette.ColorRole.Text,
         QPalette.ColorRole.Button, QPalette.ColorRole.ButtonText,
         QPalette.ColorRole.Highlight, QPalette.ColorRole.HighlightedText)


def _colors(palette: QPalette) -> list[str]:
    return [palette.color(role).name() for role in ROLES]


@pytest.fixture
def win():
    return MainWindow()


def _standard(win) -> list[str]:
    return _colors(QStyleFactory.create(win._system_style_name).standardPalette())


# ---------------------------------------------------------------------------
# 1. Dialogs keep the standard look
# ---------------------------------------------------------------------------

class TestDialogsKeepTheStandardLook:
    @pytest.mark.parametrize("theme", ["retro", "air", "dark", "mono"])
    def test_appearance_dialog_palette_is_the_standard_palette(self, win, theme):
        win._on_theme_selected(theme)
        dlg = AppearanceDialog(win._app_config.appearance, parent=win)
        dlg.show()
        _app.processEvents()
        try:
            assert _colors(dlg.palette()) == _standard(win)
            # ... and its children inherit it
            assert _colors(dlg._font_size.palette()) == _standard(win)
        finally:
            dlg.close()

    def test_the_theme_is_really_applied_elsewhere_so_the_test_means_something(self, win):
        win._on_theme_selected("retro")
        assert _colors(win.palette()) != _standard(win)           # main window: themed
        assert _colors(QApplication.palette()) != _standard(win)

    @pytest.mark.parametrize("theme", ["retro", "air"])
    def test_color_picker_and_message_box_keep_the_standard_look(self, win, theme):
        win._on_theme_selected(theme)
        for dlg in (QColorDialog(win), QMessageBox(win)):
            dlg.show()
            _app.processEvents()
            try:
                assert _colors(dlg.palette()) == _standard(win), type(dlg).__name__
            finally:
                dlg.close()

    def test_the_main_window_keeps_its_theme(self, win):
        win._on_theme_selected("retro")
        assert win.palette().color(QPalette.ColorRole.Window).name() != _standard(win)[0]


# ---------------------------------------------------------------------------
# 2. The colour picker is the platform dialog
# ---------------------------------------------------------------------------

class TestNativeColorPicker:
    def test_picker_is_not_forced_to_the_qt_dialog(self):
        text = (UI_DIR / "appearance_dialog.py").read_text(encoding="utf-8")
        assert "DontUseNativeDialog" not in text
        assert "QColorDialog.getColor" in text


# ---------------------------------------------------------------------------
# 3. Contrast depends on the font
# ---------------------------------------------------------------------------

class TestRequiredContrast:
    def test_large_text_needs_3(self):
        assert required_contrast(18, bold=False) == 3.0
        assert required_contrast(14, bold=True) == 3.0

    def test_normal_text_needs_4_5(self):
        assert required_contrast(14, bold=False) == 4.5
        assert required_contrast(11, bold=False) == 4.5
        assert required_contrast(13.9, bold=True) == 4.5

    def test_semibold_counts_as_bold(self):
        assert font_is_bold("Cascadia Mono SemiBold")
        assert font_is_bold("Segoe UI Bold")
        assert font_is_bold("Arial", weight=700)
        assert font_is_bold("Segoe UI", weight=600)
        assert not font_is_bold("Courier New")
        assert not font_is_bold("Cascadia Mono Light")


class TestContrastNextToTheColorFields:
    TEAL = "#00aa7f"            # about 3.0 : 1 on white

    def _dlg(self, family, size):
        cfg = AppearanceConfig(font_family=family, font_size=size, bg_color="#ffffff",
                               fg_color=self.TEAL, rx_color=self.TEAL, tx_color=self.TEAL)
        dlg = AppearanceDialog(cfg)
        dlg.show()
        _app.processEvents()
        return dlg

    def test_the_value_is_shown_next_to_each_of_the_three_fields(self):
        dlg = self._dlg("Cascadia Mono SemiBold", 14)
        try:
            expected = f"{contrast_ratio(self.TEAL, '#ffffff'):.1f} : 1"
            assert expected == "3.0 : 1"
            for label in (dlg._fg_ratio, dlg._rx_ratio, dlg._tx_ratio):
                assert label.text() == expected
        finally:
            dlg.close()

    def test_semibold_14pt_is_not_red(self):
        dlg = self._dlg("Cascadia Mono SemiBold", 14)
        try:
            for label in (dlg._fg_ratio, dlg._rx_ratio, dlg._tx_ratio):
                assert "c0392b" not in label.styleSheet().lower()
            assert not dlg._warning.isVisible()
        finally:
            dlg.close()

    def test_normal_11pt_is_red(self):
        dlg = self._dlg("Courier New", 11)
        try:
            for label in (dlg._fg_ratio, dlg._rx_ratio, dlg._tx_ratio):
                assert "c0392b" in label.styleSheet().lower()
            assert dlg._warning.isVisible()
        finally:
            dlg.close()

    def test_changing_the_size_updates_the_color(self):
        dlg = self._dlg("Courier New", 11)
        try:
            assert "c0392b" in dlg._tx_ratio.styleSheet().lower()
            dlg._font_size.setValue(18)                      # large text: 3 : 1
            assert "c0392b" not in dlg._tx_ratio.styleSheet().lower()
        finally:
            dlg.close()

    def test_only_the_failing_field_is_red(self):
        cfg = AppearanceConfig(font_family="Courier New", font_size=11, bg_color="#ffffff",
                               fg_color="#000000", rx_color="#000080", tx_color="#ffee88")
        dlg = AppearanceDialog(cfg)
        dlg.show()
        _app.processEvents()
        try:
            assert "c0392b" not in dlg._fg_ratio.styleSheet().lower()
            assert "c0392b" not in dlg._rx_ratio.styleSheet().lower()
            assert "c0392b" in dlg._tx_ratio.styleSheet().lower()
        finally:
            dlg.close()
