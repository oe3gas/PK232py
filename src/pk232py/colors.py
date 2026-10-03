# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""Colour helpers that need no Qt (P77): the per-theme RX/TX text colours and
the WCAG contrast formula.

Qt-free on purpose: config.py needs the theme defaults to fill a missing INI
key, and config.py must not import anything from pk232py.ui (ui/__init__.py
imports MainWindow, which imports config - a circle).

Lernmodus: the contrast ratio is the WCAG 2.x formula
    (L_light + 0.05) / (L_dark + 0.05)
with L the relative luminance of the sRGB colour (channels linearised first -
a plain average of R, G, B would call pure blue "bright"). 4.5 : 1 is the WCAG
AA threshold for normal-size text.
"""

from __future__ import annotations

from dataclasses import dataclass

# Per-theme default text colours: theme key -> (rx_color, tx_color).
# rx = received text and TNC output; tx = typed/sent text and own commands.
# Dark keeps the colours the application always used (#88ccff / #ffee88); the
# light themes get dark colours (Air: the old Light palette's #000080 / #006600),
# so nothing is yellow-on-white any more.
THEME_TEXT_COLORS: dict[str, tuple[str, str]] = {
    "dark":  ("#88ccff", "#ffee88"),
    "mono":  ("#404040", "#000000"),    # deliberately no colour
    "retro": ("#ffb000", "#ffe08a"),    # amber on near-black
    "air":   ("#000080", "#006600"),
}

# P79: per-theme display defaults: theme key -> (font_family, font_size, bg, fg).
# Qt-free on purpose, so config.py can compute a theme's effective settings
# without importing the UI (ui/themes.py builds its Theme objects FROM this).
# "custom" is a fifth theme of its own with the Dark defaults.
THEME_DISPLAY: dict[str, tuple[str, int, str, str]] = {
    "dark":   ("Cascadia Mono SemiBold", 14, "#1e1e1e", "#ffffff"),
    "mono":   ("Courier New",            14, "#ffffff", "#1a1a1a"),
    "retro":  ("Courier New",            14, "#0d0800", "#ffb000"),
    "air":    ("Segoe UI",               11, "#ffffff", "#1a1a1a"),
    "custom": ("Cascadia Mono SemiBold", 14, "#1e1e1e", "#ffffff"),
}

# Contrast below this is reported by the Appearance dialog (WCAG AA, normal text).
MIN_CONTRAST = 4.5


def _rgb(color: str) -> tuple[int, int, int]:
    """(r, g, b) of a "#rrggbb" string (a missing "#" is accepted)."""
    h = color.strip().lstrip("#")
    if len(h) != 6:
        raise ValueError(f"not a #rrggbb colour: {color!r}")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def relative_luminance(color: str) -> float:
    """WCAG relative luminance, 0.0 (black) .. 1.0 (white)."""
    def lin(v: int) -> float:
        c = v / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(color)
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast_ratio(a: str, b: str) -> float:
    """WCAG contrast ratio of two colours, 1.0 .. 21.0 (order does not matter)."""
    la, lb = relative_luminance(a), relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def is_light_background(color: str) -> bool:
    """True if *color* is a light background (Rec. 601 luma >= 128).

    The ONE brightness test the display colours use: it picks the dark or
    light widget palette (ui_theme.py) and the text-colour defaults of a
    custom theme.  Same split themes.semantic_colors() always used.
    """
    r, g, b = _rgb(color)
    return (0.299 * r + 0.587 * g + 0.114 * b) >= 128


def default_text_colors(theme_key: str, bg_color: str) -> tuple[str, str]:
    """(rx_color, tx_color) for a theme.

    A preset gives its own pair; "custom" (or anything unknown) is judged by
    the background: light -> the Air pair, dark -> the Dark pair.
    """
    if theme_key in THEME_TEXT_COLORS:
        return THEME_TEXT_COLORS[theme_key]
    return THEME_TEXT_COLORS["air" if is_light_background(bg_color) else "dark"]


@dataclass(frozen=True)
class RoleColors:
    """Fixed-meaning text colours of a theme (P77a). Not configurable in a
    dialog - only the theme decides, so each one is readable on its theme's
    background (tests/test_text_colors_p77a.py).

    sys_color  link/system messages, warnings, the [^D] marker
    ok_color   success lines (green)
    err_color  error lines (red)
    dim_color  muted text: the MON view, timestamps, the [CR] echo, the [^T] marker
    """
    sys_color: str
    ok_color: str
    err_color: str
    dim_color: str


# Dark keeps the colours the application always used (nothing changes there);
# the light themes get darker variants (>= 4.5 : 1 on white), Retro stays amber.
THEME_ROLE_COLORS: dict[str, RoleColors] = {
    "dark":  RoleColors("#ffaa00", "#3a9e3a", "#f44747", "#aaaaaa"),
    "mono":  RoleColors("#a35f00", "#1e6b1e", "#a31515", "#595959"),
    "retro": RoleColors("#ffaa00", "#7fd34a", "#ff5a3c", "#a8803a"),
    "air":   RoleColors("#a35f00", "#1e6b1e", "#a31515", "#595959"),
}


def role_colors(theme_key: str, bg_color: str) -> RoleColors:
    """Role colours of a theme; "custom" (or unknown) is judged by the
    background, like default_text_colors()."""
    if theme_key in THEME_ROLE_COLORS:
        return THEME_ROLE_COLORS[theme_key]
    return THEME_ROLE_COLORS["air" if is_light_background(bg_color) else "dark"]


# WCAG relaxes the limit for LARGE text: >= 18 pt, or >= 14 pt and bold.
LARGE_TEXT_CONTRAST = 3.0

_BOLD_WORDS = ("semibold", "demibold", "bold", "black", "heavy")


def font_is_bold(family: str, weight: int = 400) -> bool:
    """True for a bold font: a weight of 600 (SemiBold/DemiBold) or more, or a
    family name that says so ("Cascadia Mono SemiBold", "Segoe UI Bold").

    The name check matters on Windows, where a font like "Cascadia Mono
    SemiBold" is installed as its own family and Qt reports a normal weight.
    SemiBold counts as bold (WCAG says 700, but the operator's own font is
    SemiBold and reads as bold).
    """
    name = family.lower()
    return weight >= 600 or any(word in name for word in _BOLD_WORDS)


def required_contrast(point_size: float, bold: bool) -> float:
    """The WCAG 2.x AA limit for text of this size: 3 : 1 for large text
    (>= 18 pt, or >= 14 pt bold), otherwise 4.5 : 1."""
    if point_size >= 18 or (bold and point_size >= 14):
        return LARGE_TEXT_CONTRAST
    return MIN_CONTRAST


def meets_contrast(color: str, bg: str, required: float = MIN_CONTRAST) -> bool:
    """True if the contrast of *color* on *bg* reaches *required*.

    Compared at the precision that is SHOWN (one decimal): a ratio the dialog
    displays as "3.0 : 1" is not marked red against a 3 : 1 limit, which would
    look like a bug (#00aa7f on white is 2.976).
    """
    return round(contrast_ratio(color, bg), 1) >= required


def low_contrast_warnings(bg: str, fg: str, rx: str, tx: str,
                          required: float = MIN_CONTRAST) -> list[str]:
    """One "Low contrast: <what> on background (2.1 : 1)" line per text colour
    whose contrast to *bg* is below *required* (default 4.5; the Appearance
    dialog passes the limit for its font, see required_contrast()). Empty list
    = all fine.

    A pure function, so the Appearance dialog's warning is testable without Qt.
    """
    out = []
    for label, color in (("Foreground text", fg), ("RX text", rx), ("TX text", tx)):
        if not meets_contrast(color, bg, required):
            out.append(
                f"Low contrast: {label} on background "
                f"({contrast_ratio(color, bg):.1f} : 1)")
    return out
