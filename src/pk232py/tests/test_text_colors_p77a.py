# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""P77a (inventory from P77 report): the remaining fixed text colours of the
display surfaces come from the theme (colors.py role colours sys/ok/err/dim and
the configured rx/tx), and EVERY text colour of EVERY theme is readable on its
background (WCAG contrast >= 4.5 : 1).

Menu chrome, status bar and buttons are deliberately not covered.
"""

from __future__ import annotations

import os
import pathlib

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from pk232py.colors import MIN_CONTRAST, contrast_ratio
from pk232py.ui.main_window import MainWindow
from pk232py.ui.screens import ui_theme
from pk232py.ui.themes import THEME_ORDER, THEMES

_app = QApplication.instance() or QApplication([])

UI_DIR = pathlib.Path(__file__).resolve().parent.parent / "ui"
ROLES = ("sys_color", "ok_color", "err_color", "dim_color")
# P77c: the side panel / status line colours sit on the WIDGET window colour as
# well as on the display background - both are checked.
PANEL_ROLES = ("heard_direct_color", "heard_digi_color", "panel_ok_color",
               "panel_sys_color", "panel_err_color", "panel_dim_color")


def _fragment_color(doc, needle: str) -> str:
    """Foreground colour of the first fragment of *doc* that contains *needle*."""
    block = doc.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid() and needle in frag.text():
                return frag.charFormat().foreground().color().name()
            it += 1
        block = block.next()
    raise AssertionError(f"{needle!r} not found in the document")


@pytest.fixture
def win():
    return MainWindow()


# ---------------------------------------------------------------------------
# Every text colour of every theme against its background
# ---------------------------------------------------------------------------

class TestEveryThemeIsReadable:
    @pytest.mark.parametrize("key", THEME_ORDER)
    def test_all_text_colors_reach_4_5_to_1(self, win, key):
        win._on_theme_selected(key)
        a = win._app_config.appearance
        t = ui_theme.get_theme()
        colors = {
            "fg": a.fg_color, "rx": a.rx_color, "tx": a.tx_color,
            **{role: t[role] for role in ROLES},
            **{name: hexcol for name, hexcol in win._semantic_colors.items()},
        }
        too_low = {
            name: round(contrast_ratio(col, a.bg_color), 2)
            for name, col in colors.items()
            if contrast_ratio(col, a.bg_color) < MIN_CONTRAST
        }
        assert not too_low, f"theme {key} (bg {a.bg_color}): {too_low}"

    @pytest.mark.parametrize("key", THEME_ORDER)
    def test_panel_colors_reach_4_5_to_1_on_display_and_window_background(self, win, key):
        win._on_theme_selected(key)
        a = win._app_config.appearance
        t = ui_theme.get_theme()
        backgrounds = {"display": a.bg_color, "window": t["bg_window"]}
        too_low = {
            f"{role} on {name}": round(contrast_ratio(t[role], bg), 2)
            for role in PANEL_ROLES for name, bg in backgrounds.items()
            if contrast_ratio(t[role], bg) < MIN_CONTRAST
        }
        assert not too_low, f"theme {key}: {too_low}"

    def test_the_four_presets_are_the_ones_checked(self):
        assert set(THEME_ORDER) == set(THEMES) == {"dark", "mono", "retro", "air"}


# ---------------------------------------------------------------------------
# Packet screens
# ---------------------------------------------------------------------------

class TestPacketScreen:
    def test_channel_text_uses_rx_color(self, win):
        win._on_theme_selected("air")
        screen = win._opmode_screens["VHF Packet"]
        screen.append_channel_data(1, "hello channel")
        color = _fragment_color(screen._rx_docs[1], "hello channel")
        assert color == win._app_config.appearance.rx_color
        assert color != "#66ccff"

    def test_monitor_text_uses_dim_color(self, win):
        win._on_theme_selected("air")
        screen = win._opmode_screens["VHF Packet"]
        screen.append_monitor_data("OE3XYZ>CQ: monitored")
        color = _fragment_color(screen._rx_docs["MON"], "monitored")
        assert color == ui_theme.get_theme()["dim_color"]
        assert color != "#aaaaaa"

    def test_text_already_in_a_hidden_channel_is_recolored(self, win):
        win._on_theme_selected("dark")
        screen = win._opmode_screens["VHF Packet"]
        screen.append_channel_data(2, "old line")
        assert _fragment_color(screen._rx_docs[2], "old line") == "#88ccff"
        win._on_theme_selected("air")
        assert _fragment_color(screen._rx_docs[2], "old line") == "#000080"


# ---------------------------------------------------------------------------
# MainWindow: system messages, status lines, [CR] echo, command row, markers
# ---------------------------------------------------------------------------

class TestMainWindow:
    def test_system_message_color_is_the_themes_sys_color(self, win):
        win._on_theme_selected("air")
        assert win._sys_color() == ui_theme.get_theme()["sys_color"] != "#ffaa00"
        win._on_theme_selected("dark")
        assert win._sys_color() == "#ffaa00"                # Dark unchanged

    def test_verbose_cr_echo_is_dim_and_error_line_is_err(self, win):
        win._on_theme_selected("air")
        win._vt_input.clear()
        win._on_vt_send()                      # empty -> [CR] echo, not connected -> error
        t = ui_theme.get_theme()
        assert _fragment_color(win._vt_display.document(), "[CR]") == t["dim_color"]
        assert _fragment_color(win._vt_display.document(), "Not connected") == t["err_color"]

    def test_verbose_command_row_uses_bg_and_tx_color(self, win):
        win._on_theme_selected("air")
        a = win._app_config.appearance
        assert a.bg_color in win._vt_cmd_row.styleSheet()
        assert a.tx_color in win._vt_prompt.styleSheet()

    def test_dark_theme_keeps_the_old_status_colors(self, win):
        win._on_theme_selected("dark")
        t = ui_theme.get_theme()
        assert (t["ok_color"], t["err_color"]) == ("#3a9e3a", "#f44747")


class TestNoFixedDisplayColorsLeft:
    @pytest.mark.parametrize("path,literals", [
        ("screens/packet_screen.py", ["#66ccff", '"#aaaaaa"', "#6a6a6a"]),
        # (#888888 stays in main_window.py as the OFFLINE badge / READY chip and
        # #f44747 as the status bar's "TNC differs" label: chrome, deliberately
        # untouched.)
        ("main_window.py", ["_SYSTEM_MSG_COLOR", "#569cd6", "#d4d4d4", "#3a9e3a"]),
        ("screens/opmode_rtty_base.py", ["#cc4400", "#8800cc"]),
        ("screens/macro_store.py", ["#cc4400", "#8800cc"]),
    ])
    def test_literals_are_gone(self, path, literals):
        text = (UI_DIR / path).read_text(encoding="utf-8")
        found = [lit for lit in literals if lit in text]
        assert not found, f"{path} still has {found}"
