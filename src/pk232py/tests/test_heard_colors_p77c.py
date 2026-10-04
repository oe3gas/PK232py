# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""P77c (screenshot, theme Air) - the fixed text colours of the Packet screen's
MHEARD list and status line come from the theme and reach 4.5 : 1 in EVERY theme.

Measured on the real widgets (the label's style sheet after the theme was
selected), against both backgrounds a label can sit on: the display background
and the widget palette's window colour.
"""

from __future__ import annotations

import os
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication, QLabel

from pk232py.colors import MIN_CONTRAST, THEME_ROLE_COLORS, contrast_ratio
from pk232py.ui.main_window import MainWindow
from pk232py.ui.screens import ui_theme
from pk232py.ui.screens.packet_screen import STATUS_STYLES
from pk232py.ui.themes import THEME_ORDER

_app = QApplication.instance() or QApplication([])

_COLOR_RE = re.compile(r"(?<![-\w])color:\s*(#[0-9a-fA-F]{6})")


def sheet_color(widget) -> str:
    m = _COLOR_RE.search(widget.styleSheet())
    assert m, f"no colour in {widget.styleSheet()!r}"
    return m.group(1)


@pytest.fixture
def win():
    return MainWindow()


def backgrounds(win):
    a = win._app_config.appearance
    return {"display": a.bg_color, "window": ui_theme.get_theme()["bg_window"]}


def mheard_labels(screen):
    """{kind: callsign label} of three rows: direct, via digi, connected."""
    panel = screen.mheard_panel
    panel.clear()
    panel.add_entry("OE3AAA", "12:00", direct=True)
    panel.add_entry("OE3BBB", "12:01", direct=False)
    panel.add_entry("OE3CCC", "12:02", direct=False)
    panel.set_channel_map({"OE3CCC": 2})
    rows = [panel._list_layout.itemAt(i).widget() for i in range(3)]
    by_call = {}
    for row in rows:
        label = row.findChildren(QLabel)[0]
        for call, kind in (("OE3AAA", "direct"), ("OE3BBB", "digi"), ("OE3CCC", "connected")):
            if call in label.text():
                by_call[kind] = label
    return by_call


class TestRolesExist:
    @pytest.mark.parametrize("key", THEME_ORDER)
    def test_the_theme_has_both_heard_colors(self, key):
        roles = THEME_ROLE_COLORS[key]
        for name in ("heard_direct_color", "heard_digi_color", "panel_ok_color",
                     "panel_sys_color", "panel_err_color", "panel_dim_color"):
            assert getattr(roles, name).startswith("#"), name

    def test_get_theme_carries_them(self, win):
        t = ui_theme.get_theme()
        assert "heard_direct_color" in t and "heard_digi_color" in t


class TestMheardRows:
    @pytest.mark.parametrize("key", THEME_ORDER)
    def test_every_callsign_colour_is_readable(self, win, key):
        win._on_theme_selected(key)
        screen = win._opmode_screens["HF Packet"]
        labels = mheard_labels(screen)
        assert set(labels) == {"direct", "digi", "connected"}
        too_low = {}
        for kind, label in labels.items():
            for bg_name, bg in backgrounds(win).items():
                ratio = contrast_ratio(sheet_color(label), bg)
                if ratio < MIN_CONTRAST:
                    too_low[f"{kind} on {bg_name} {bg}"] = round(ratio, 2)
        assert not too_low, f"theme {key}: {too_low}"

    def test_air_does_not_use_the_old_fixed_colours(self, win):
        win._on_theme_selected("air")
        labels = mheard_labels(win._opmode_screens["HF Packet"])
        assert sheet_color(labels["direct"]).lower() != "#66ee66"
        assert sheet_color(labels["digi"]).lower() != "#88ccff"

    def test_dark_keeps_the_colours_it_always_had(self, win):
        win._on_theme_selected("dark")
        labels = mheard_labels(win._opmode_screens["HF Packet"])
        assert sheet_color(labels["direct"]).lower() == "#66ee66"
        assert sheet_color(labels["digi"]).lower() == "#88ccff"

    @pytest.mark.parametrize("key", ["air", "dark"])
    def test_rows_that_exist_are_recoloured_when_the_theme_changes(self, win, key):
        other = "dark" if key == "air" else "air"
        win._on_theme_selected(other)
        screen = win._opmode_screens["HF Packet"]
        mheard_labels(screen)                                   # rows exist in the other theme
        win._on_theme_selected(key)
        labels = mheard_labels_existing(screen)
        for kind, label in labels.items():
            for bg in backgrounds(win).values():
                assert contrast_ratio(sheet_color(label), bg) >= MIN_CONTRAST, kind


def mheard_labels_existing(screen):
    panel = screen.mheard_panel
    out = {}
    for i in range(3):
        label = panel._list_layout.itemAt(i).widget().findChildren(QLabel)[0]
        for call, kind in (("OE3AAA", "direct"), ("OE3BBB", "digi"), ("OE3CCC", "connected")):
            if call in label.text():
                out[kind] = label
    return out


class TestStatusLineAndHint:
    @pytest.mark.parametrize("key", THEME_ORDER)
    def test_every_status_state_is_readable(self, win, key):
        win._on_theme_selected(key)
        screen = win._opmode_screens["HF Packet"]
        too_low = {}
        for state in STATUS_STYLES:
            screen._set_status(state)
            for bg_name, bg in backgrounds(win).items():
                ratio = contrast_ratio(sheet_color(screen.lbl_status), bg)
                if ratio < MIN_CONTRAST:
                    too_low[f"{state} on {bg_name} {bg}"] = round(ratio, 2)
        assert not too_low, f"theme {key}: {too_low}"

    @pytest.mark.parametrize("key", THEME_ORDER)
    def test_the_parameter_hint_is_readable(self, win, key):
        win._on_theme_selected(key)
        screen = win._opmode_screens["HF Packet"]
        for bg in backgrounds(win).values():
            assert contrast_ratio(sheet_color(screen.lbl_param_hint), bg) >= MIN_CONTRAST

    def test_the_status_text_is_kept_when_the_theme_changes(self, win):
        screen = win._opmode_screens["HF Packet"]
        screen._set_status("CONNECTED")
        win._on_theme_selected("air")
        assert "CONNECTED" in screen.lbl_status.text()
        assert contrast_ratio(sheet_color(screen.lbl_status),
                              ui_theme.get_theme()["bg_window"]) >= MIN_CONTRAST

    def test_states_keep_their_meaning_in_the_dark_theme(self, win):
        win._on_theme_selected("dark")
        screen = win._opmode_screens["HF Packet"]
        screen._set_status("CONNECTED")
        assert sheet_color(screen.lbl_status).lower() == THEME_ROLE_COLORS["dark"].panel_ok_color.lower()
        screen._set_status("DISCONNECTED")
        assert sheet_color(screen.lbl_status).lower() == THEME_ROLE_COLORS["dark"].panel_err_color.lower()
