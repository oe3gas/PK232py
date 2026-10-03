# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""P77: ONE colour source (AppearanceConfig) for every display.

Operator screenshots 03.10.2026: on a white background the Baudot TX input was
yellow (#ffee88 came from ui_theme's separate DARK palette) and the verbose
terminal's TNC output light grey (#cccccc, fixed). Now rx_color / tx_color live
in AppearanceConfig; the themes only supply defaults.
"""

from __future__ import annotations

import os
import pathlib

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication, QDialog

from pk232py.colors import (
    THEME_TEXT_COLORS, contrast_ratio, default_text_colors,
    low_contrast_warnings,
)
from pk232py.config import AppearanceConfig, ConfigManager
from pk232py.ui.appearance_dialog import AppearanceDialog
from pk232py.ui.main_window import MainWindow
from pk232py.ui.screens import ui_theme
from pk232py.ui.screens.opmode_rtty_base import TxInputWidget

_app = QApplication.instance() or QApplication([])

UI_DIR = pathlib.Path(__file__).resolve().parent.parent / "ui"


def _first_fragment_color(text_edit) -> str:
    """Foreground colour of the first fragment with visible text (the terminal
    starts with an empty block, whose separator fragment carries no text)."""
    block = text_edit.document().begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid() and frag.text().strip():
                return frag.charFormat().foreground().color().name()
            it += 1
        block = block.next()
    raise AssertionError("no text in the widget")


@pytest.fixture
def win():
    return MainWindow()


# ---------------------------------------------------------------------------
# Config: defaults per theme, INI
# ---------------------------------------------------------------------------

class TestConfig:
    def test_dark_defaults_are_the_old_colors(self):
        a = AppearanceConfig()
        assert (a.rx_color, a.tx_color) == ("#88ccff", "#ffee88")

    def test_air_defaults_are_dark_colors(self):
        assert THEME_TEXT_COLORS["air"] == ("#000080", "#006600")

    def test_every_theme_text_color_is_readable_on_its_own_background(self):
        from pk232py.ui.themes import THEMES
        for key, theme in THEMES.items():
            assert low_contrast_warnings(theme.bg, theme.fg, theme.rx, theme.tx) == [], key

    def test_ini_without_the_keys_takes_the_stored_themes_defaults(self, tmp_path):
        ini = tmp_path / "pk232py.ini"
        ini.write_text("[Appearance]\ntheme = air\nbg_color = #ffffff\n", encoding="utf-8")
        mgr = ConfigManager(ini)
        mgr.load()
        assert (mgr.app.appearance.rx_color, mgr.app.appearance.tx_color) == ("#000080", "#006600")

    def test_custom_theme_without_keys_is_judged_by_the_background(self):
        assert default_text_colors("custom", "#ffffff") == THEME_TEXT_COLORS["air"]
        assert default_text_colors("custom", "#101010") == THEME_TEXT_COLORS["dark"]

    def test_keys_are_saved_and_read_back(self, tmp_path):
        mgr = ConfigManager(tmp_path / "pk232py.ini")
        mgr.app.appearance.rx_color = "#112233"
        mgr.app.appearance.tx_color = "#445566"
        mgr.save()
        again = ConfigManager(tmp_path / "pk232py.ini")
        again.load()
        assert (again.app.appearance.rx_color, again.app.appearance.tx_color) == ("#112233", "#445566")


# ---------------------------------------------------------------------------
# Contrast function and warning
# ---------------------------------------------------------------------------

class TestContrast:
    def test_the_operators_yellow_on_white_is_too_low(self):
        assert contrast_ratio("#ffee88", "#ffffff") < 4.5

    def test_navy_on_white_is_fine(self):
        assert contrast_ratio("#000080", "#ffffff") >= 4.5

    def test_extremes_and_symmetry(self):
        assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0)
        assert contrast_ratio("#ffffff", "#ffffff") == pytest.approx(1.0)
        assert contrast_ratio("#123456", "#abcdef") == contrast_ratio("#abcdef", "#123456")

    def test_warning_text_names_the_colour_and_the_ratio(self):
        (line,) = low_contrast_warnings("#ffffff", "#000000", "#000080", "#ffee88")
        assert line.startswith("Low contrast: TX text on background (")
        assert line.endswith(" : 1)")

    def test_no_warning_for_good_colors(self):
        assert low_contrast_warnings("#ffffff", "#1a1a1a", "#000080", "#006600") == []


class TestDialogWarning:
    def _dlg(self, **kw):
        cfg = AppearanceConfig(bg_color="#ffffff", fg_color="#1a1a1a",
                               rx_color="#000080", tx_color="#006600")
        for k, v in kw.items():
            setattr(cfg, k, v)
        return AppearanceDialog(cfg)

    def test_warning_appears_for_a_bad_tx_color_and_goes_again(self):
        dlg = self._dlg()
        dlg.show()
        _app.processEvents()
        assert not dlg._warning.isVisible()
        dlg._tx_btn.set_color("#ffffcc")                       # pale yellow on white
        assert dlg._warning.isVisible()
        assert "Low contrast: TX text on background (" in dlg._warning.text()
        dlg._tx_btn.set_color("#006600")
        assert not dlg._warning.isVisible()
        dlg.close()

    def test_saving_stays_possible_with_a_warning(self):
        dlg = self._dlg(tx_color="#ffffcc")
        out = AppearanceConfig()
        dlg.apply_to(out)
        assert out.tx_color == "#ffffcc"

    def test_preview_has_an_rx_and_a_tx_line_in_the_chosen_colors(self):
        dlg = self._dlg(rx_color="#112233", tx_color="#445566")
        text = dlg._preview.text()
        assert "#112233" in text and "#445566" in text

    def test_reset_restores_the_themes_rx_and_tx(self):
        dlg = self._dlg(theme="air", rx_color="#aaaaaa", tx_color="#bbbbbb")
        dlg._on_reset()
        assert (dlg._rx_btn.color(), dlg._tx_btn.color()) == ("#000080", "#006600")


# ---------------------------------------------------------------------------
# One source for every display
# ---------------------------------------------------------------------------

class TestOneColorSource:
    def test_air_baudot_tx_color_is_not_the_dark_palettes_yellow(self, win):
        win._on_theme_selected("air")                      # Air: background #ffffff
        a = win._app_config.appearance
        assert a.bg_color == "#ffffff"
        tx = win._opmode_screens["Baudot RTTY"].tx_input
        assert tx._tx_fg_color == a.tx_color != "#ffee88"
        assert tx.currentCharFormat().foreground().color().name() == a.tx_color
        assert ui_theme.get_theme()["tx_color"] == a.tx_color

    def test_dark_theme_is_unchanged(self, win):
        win._on_theme_selected("dark")
        tx = win._opmode_screens["Baudot RTTY"].tx_input
        assert tx._tx_fg_color == "#ffee88"
        assert ui_theme.get_theme()["rx_color"] == "#88ccff"

    def test_widget_palette_follows_the_background_brightness(self, win):
        win._on_theme_selected("air")
        assert ui_theme.get_theme()["bg_input"] == ui_theme.THEMES["light"]["bg_input"]
        win._on_theme_selected("dark")
        assert ui_theme.get_theme()["bg_input"] == ui_theme.THEMES["dark"]["bg_input"]

    def test_no_palette_in_ui_theme_defines_rx_or_tx(self):
        for name, palette in ui_theme.THEMES.items():
            assert "rx_color" not in palette and "tx_color" not in palette, name

    def test_verbose_terminal_shows_tnc_output_in_rx_color_not_grey(self, win):
        win._on_theme_selected("air")
        win._on_vt_rx_data(b"cmd:")
        color = _first_fragment_color(win._vt_display)
        assert color == win._app_config.appearance.rx_color == "#000080"
        assert color != "#cccccc"

    def test_verbose_terminal_own_command_uses_tx_color(self, win):
        win._on_theme_selected("air")
        win._vt_input.setPlainText("MYCALL")
        win._on_vt_send()                    # not connected: echo + error line
        assert _first_fragment_color(win._vt_display) == win._app_config.appearance.tx_color

    def test_verbose_terminal_background_is_bg_color(self, win):
        win._on_theme_selected("air")
        assert "background-color:#ffffff" in win._vt_display.styleSheet()
        assert "#0c0c0c" not in win._vt_display.styleSheet()

    def test_main_window_has_no_fixed_light_grey(self):
        assert "#cccccc" not in (UI_DIR / "main_window.py").read_text(encoding="utf-8")

    def test_dialog_change_reaches_config_theme_and_displays(self, win, monkeypatch):
        def fake_exec(dlg):
            dlg._tx_btn.set_color("#aa0000")
            dlg._rx_btn.set_color("#0000aa")
            dlg._on_accept()
            return QDialog.DialogCode.Accepted
        monkeypatch.setattr(AppearanceDialog, "exec", fake_exec)
        win._on_theme_selected("air")
        win._on_appearance()
        a = win._app_config.appearance
        assert (a.tx_color, a.rx_color) == ("#aa0000", "#0000aa")
        assert a.theme == "custom"
        tx = win._opmode_screens["Baudot RTTY"].tx_input
        assert tx._tx_fg_color == "#aa0000"
        assert "#aa0000" in win._vt_input.styleSheet()
        assert "#0000aa" in win._vt_display.styleSheet()
        assert ui_theme.get_theme()["tx_color"] == "#aa0000"

    def test_text_already_in_the_terminal_is_recolored(self, win):
        win._on_theme_selected("dark")
        win._on_vt_rx_data(b"cmd:")
        assert _first_fragment_color(win._vt_display) == "#88ccff"
        win._on_theme_selected("air")
        assert _first_fragment_color(win._vt_display) == "#000080"


# ---------------------------------------------------------------------------
# Sent-character highlight
# ---------------------------------------------------------------------------

class TestSentHighlight:
    def test_inverse_is_tx_color_background_with_bg_color_text(self):
        w = TxInputWidget()
        w.set_theme_colors("#006600", "#ffffff")
        w.insertPlainText("A")
        w.set_cycle_anchor(0, 0)
        w.colour_at(0, sent=True)
        fmt = w.document().begin().begin().fragment().charFormat()
        assert fmt.background().color().name() == "#006600"     # tx_color
        assert fmt.foreground().color().name() == "#ffffff"     # bg_color
        assert "#ddaa00" not in (UI_DIR / "screens" / "opmode_rtty_base.py").read_text(encoding="utf-8")
