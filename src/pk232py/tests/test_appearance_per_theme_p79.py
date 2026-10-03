# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""P79: every theme remembers its own font, colours and RX/TX colour.

Before: one set of values in [Appearance]; a theme switch overwrote them with
the theme's defaults, so fonts chosen under different themes were lost (T163).
Now: AppearanceConfig.overrides[theme] holds only the DEVIATIONS from the
theme's defaults; AppearanceConfig.effective(theme) is the one place that
combines default and override.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication, QDialog

from pk232py.config import AppearanceConfig, ConfigManager
from pk232py.ui.appearance_dialog import AppearanceDialog
from pk232py.ui.main_window import MainWindow

_app = QApplication.instance() or QApplication([])


@pytest.fixture
def win():
    return MainWindow()


def _edit(win, monkeypatch, **colors_and_font):
    """Run the Font & Colors dialog on the current theme, setting some fields."""
    def fake_exec(dlg):
        if "family" in colors_and_font:
            from PyQt6.QtGui import QFont
            dlg._font_combo.setCurrentFont(QFont(colors_and_font["family"]))
            # Headless Qt has no fonts (the combo falls back); what a real pick
            # sets via currentFontChanged is the remembered family name.
            dlg._family_name = colors_and_font["family"]
        if "size" in colors_and_font:
            dlg._font_size.setValue(colors_and_font["size"])
        if "tx" in colors_and_font:
            dlg._tx_btn.set_color(colors_and_font["tx"])
        dlg._on_accept()
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(AppearanceDialog, "exec", fake_exec)
    win._on_appearance()


class TestEffective:
    def test_without_overrides_it_is_the_theme_default(self):
        a = AppearanceConfig()
        eff = a.effective("air")
        assert (eff["font_family"], eff["font_size"], eff["bg_color"]) == ("Segoe UI", 11, "#ffffff")
        assert (eff["rx_color"], eff["tx_color"]) == ("#000080", "#006600")

    def test_an_override_wins_for_its_theme_only(self):
        a = AppearanceConfig(overrides={"air": {"font_family": "Consolas", "font_size": 12}})
        assert a.effective("air")["font_family"] == "Consolas"
        assert a.effective("dark")["font_family"] == "Cascadia Mono SemiBold"

    def test_custom_is_a_theme_of_its_own_with_dark_defaults(self):
        assert AppearanceConfig().effective("custom") == AppearanceConfig().effective("dark")


class TestSwitching:
    def test_air_font_survives_a_trip_to_dark(self, win, monkeypatch):
        win._on_theme_selected("air")
        _edit(win, monkeypatch, family="Consolas", size=12)
        win._on_theme_selected("dark")
        win._on_theme_selected("air")
        a = win._app_config.appearance
        assert (a.font_family, a.font_size) == ("Consolas", 12)

    def test_retro_tx_color_leaves_air_and_dark_alone(self, win, monkeypatch):
        win._on_theme_selected("retro")
        _edit(win, monkeypatch, tx="#123456")
        a = win._app_config.appearance
        assert a.tx_color == "#123456" and a.theme == "retro"
        win._on_theme_selected("air")
        assert a.tx_color == "#006600"
        win._on_theme_selected("dark")
        assert a.tx_color == "#ffee88"
        assert set(a.overrides) == {"retro"}

    def test_a_value_equal_to_the_default_is_not_stored(self, win, monkeypatch):
        win._on_theme_selected("air")
        _edit(win, monkeypatch, tx="#006600")          # = Air default
        assert win._app_config.appearance.overrides == {}

    def test_changing_back_to_the_default_removes_the_override(self, win, monkeypatch):
        win._on_theme_selected("air")
        _edit(win, monkeypatch, tx="#aa0000")
        assert win._app_config.appearance.overrides == {"air": {"tx_color": "#aa0000"}}
        _edit(win, monkeypatch, tx="#006600")
        assert win._app_config.appearance.overrides == {}


class TestReset:
    def test_reset_in_air_keeps_the_overrides_of_dark(self, win, monkeypatch):
        win._on_theme_selected("dark")
        _edit(win, monkeypatch, tx="#111111")
        win._on_theme_selected("air")
        _edit(win, monkeypatch, tx="#222222")

        def reset_exec(dlg):
            dlg._on_reset()
            dlg._on_accept()
            return QDialog.DialogCode.Accepted
        monkeypatch.setattr(AppearanceDialog, "exec", reset_exec)
        win._on_appearance()
        a = win._app_config.appearance
        assert a.tx_color == "#006600"
        assert a.overrides == {"dark": {"tx_color": "#111111"}}

    def test_dialog_title_names_the_edited_theme(self):
        dlg = AppearanceDialog(AppearanceConfig(theme="air"))
        assert dlg.windowTitle() == "Appearance — Air"


class TestIni:
    def test_round_trip_of_three_themes(self, tmp_path):
        path = tmp_path / "pk232py.ini"
        mgr = ConfigManager(path)
        a = mgr.app.appearance
        a.theme = "retro"
        a.overrides = {
            "air":   {"font_family": "Consolas", "font_size": 12},
            "dark":  {"font_family": "Courier New"},
            "retro": {"tx_color": "#00ff00"},
        }
        a.load_effective()
        mgr.save()
        text = path.read_text(encoding="utf-8")
        assert "[Appearance.air]" in text and "[Appearance.retro]" in text
        again = ConfigManager(path)
        again.load()
        b = again.app.appearance
        assert b.overrides == a.overrides
        assert b.theme == "retro" and b.tx_color == "#00ff00"
        assert b.effective("air")["font_size"] == 12

    def test_an_override_removed_before_saving_leaves_no_section(self, tmp_path):
        path = tmp_path / "pk232py.ini"
        mgr = ConfigManager(path)
        mgr.app.appearance.overrides = {"air": {"font_size": 12}}
        mgr.save()
        mgr2 = ConfigManager(path)
        mgr2.load()
        mgr2.app.appearance.overrides = {}
        mgr2.app.appearance.load_effective()
        mgr2.save()
        assert "[Appearance.air]" not in path.read_text(encoding="utf-8")

    def test_old_keys_are_not_written_any_more(self, tmp_path):
        path = tmp_path / "pk232py.ini"
        mgr = ConfigManager(path)
        mgr.save()
        text = path.read_text(encoding="utf-8")
        assert "font_family" not in text and "rx_color" not in text


class TestMigration:
    def test_old_custom_goes_to_the_custom_slot(self, tmp_path):
        path = tmp_path / "pk232py.ini"
        path.write_text("[Appearance]\ntheme = custom\nfont_family = Consolas\n"
                        "font_size = 14\nbg_color = #1e1e1e\n", encoding="utf-8")
        mgr = ConfigManager(path)
        mgr.load()
        a = mgr.app.appearance
        assert a.theme == "custom"
        assert a.overrides == {"custom": {"font_family": "Consolas"}}
        assert a.font_family == "Consolas"

    def test_old_air_with_a_different_font_goes_to_air(self, tmp_path):
        path = tmp_path / "pk232py.ini"
        path.write_text("[Appearance]\ntheme = air\nfont_family = Consolas\n"
                        "font_size = 12\nbg_color = #ffffff\n", encoding="utf-8")
        mgr = ConfigManager(path)
        mgr.load()
        a = mgr.app.appearance
        assert a.overrides == {"air": {"font_family": "Consolas", "font_size": 12}}
        assert (a.font_family, a.font_size) == ("Consolas", 12)
        mgr.save()
        assert "font_family = Consolas" in path.read_text(encoding="utf-8")
        assert "[Appearance]\ntheme = air" in path.read_text(encoding="utf-8").replace("\r\n", "\n")
