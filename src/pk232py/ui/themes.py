# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Theme presets and QPalette construction for the appearance system.

A *theme* is a named bundle of font + colours. Three of the four presets
(Dark / Mono / Retro) drive a full custom :class:`QPalette`; the fourth
(Air) keeps the native system look.

------------------------------------------------------------------------------
LERNMODUS — why a QPalette, and why a style switch
------------------------------------------------------------------------------

1. WHY A PALETTE AT ALL.
   PK232PY styles its RX/TX text panels directly with stylesheets, but
   everything Qt draws for us — menus, dialogs, message boxes, the OK/Cancel
   buttons, spin boxes, combo-box popups — takes its colours from the
   *application* QPalette. If we only set the panel stylesheets and leave the
   palette at the OS default, a dark window gets dark dialogs with *dark*
   button text → unreadable. Setting every relevant ColorRole fixes that.

2. WHY THE STYLE MATTERS (native vs Fusion).
   The native Windows style ("windowsvista") draws push-buttons via the OS
   theme engine and largely IGNORES QPalette.ButtonText — so a custom palette
   alone does NOT fix the unreadable-button bug. The Fusion style honours the
   palette completely. So themed presets switch the app to Fusion; Air switches
   back to the captured system style so it looks truly native.

3. WHY AIR USES system_palette INSTEAD OF LIGHT COLOURS.
   We could fake a light theme by setting white-ish palette roles, but native
   widgets (scrollbars, buttons, the menu chrome) would still be drawn by
   Fusion and look subtly foreign. Restoring the system style + its
   standardPalette() keeps those widgets 100 % native — no visual break.

------------------------------------------------------------------------------
How the ColorRoles map (Dark / Mono / Retro)
------------------------------------------------------------------------------
  Window / WindowText        = bg          / fg
  Base / Text                = bg darker   / fg     (text-entry backgrounds)
  AlternateBase              = bg lighter           (alternating rows)
  Button / ButtonText        = bg lighter  / fg     (push buttons — the fix)
  ToolTipBase / ToolTipText  = bg lighter  / fg
  Highlight / HighlightedText= accent      / bg     (selection)
  PlaceholderText            = fg/bg blend
  Disabled {Text,ButtonText,WindowText} = greyed fg/bg blend
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtGui import QColor, QPalette

from pk232py.colors import THEME_TEXT_COLORS, role_colors


@dataclass(frozen=True)
class Theme:
    """A named appearance preset.

    Attributes:
        key:            stable INI/identifier key ("dark", "mono", ...).
        name:           human-readable menu label ("Dark", "Mono", ...).
        font_family:    display font family.
        font_size:      display font point size.
        bg / fg:        background / foreground hex colours. Ignored for the
                        palette when ``system_palette`` is True, but still used
                        for the RX/TX text panels.
        system_palette: True → keep the native system palette/style (Air).
                        False → build and apply a full custom QPalette (Fusion).
        rx / tx:        text colours for received / typed text (P77). Presets
                        take them from colors.THEME_TEXT_COLORS; they are only
                        DEFAULTS - AppearanceConfig.rx_color / tx_color are
                        what the displays really use.
    """
    key:            str
    name:           str
    font_family:    str
    font_size:      int
    bg:             str
    fg:             str
    system_palette: bool
    rx:             str = "#88ccff"
    tx:             str = "#ffee88"


THEMES: dict[str, Theme] = {
    "dark": Theme(
        key="dark", name="Dark",
        font_family="Cascadia Mono SemiBold", font_size=14,
        bg="#1e1e1e", fg="#ffffff", system_palette=False,
        rx=THEME_TEXT_COLORS["dark"][0], tx=THEME_TEXT_COLORS["dark"][1],
    ),
    # Mono = classic light paper-white terminal — deliberately NO colour.
    # White background, near-black text; build_palette derives every other role
    # as a grey shade of bg/fg (luminance-aware, so the buttons go DARKER than
    # the white window instead of clamping to white).
    "mono": Theme(
        key="mono", name="Mono",
        font_family="Courier New", font_size=14,
        bg="#ffffff", fg="#1a1a1a", system_palette=False,
        rx=THEME_TEXT_COLORS["mono"][0], tx=THEME_TEXT_COLORS["mono"][1],
    ),
    "retro": Theme(
        key="retro", name="Retro",
        font_family="Courier New", font_size=14,
        bg="#0d0800", fg="#ffb000", system_palette=False,
        rx=THEME_TEXT_COLORS["retro"][0], tx=THEME_TEXT_COLORS["retro"][1],
    ),
    # Air keeps the native look; bg/fg are light values used ONLY for the
    # RX/TX text panels (the global palette stays the system default).
    "air": Theme(
        key="air", name="Air",
        font_family="Segoe UI", font_size=11,
        bg="#ffffff", fg="#1a1a1a", system_palette=True,
        rx=THEME_TEXT_COLORS["air"][0], tx=THEME_TEXT_COLORS["air"][1],
    ),
}

# Order shown in the Configure → Appearance submenu.
THEME_ORDER: tuple[str, ...] = ("dark", "mono", "retro", "air")


# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

def _shift(c: QColor, delta: int) -> QColor:
    """Lighten (delta>0) / darken (delta<0) by an ADDITIVE per-channel offset.

    Additive (not QColor.lighter()) so it still works on pure black: a
    multiplicative lighten leaves #000000 black, whereas Mono's button needs to
    be visibly lighter than its black background.
    """
    def clamp(v: int) -> int:
        return max(0, min(255, v))
    return QColor(clamp(c.red() + delta), clamp(c.green() + delta),
                  clamp(c.blue() + delta))


def _blend(a: QColor, b: QColor, t: float) -> QColor:
    """Linear blend: t=0 → a, t=1 → b."""
    return QColor(
        round(a.red()   * (1 - t) + b.red()   * t),
        round(a.green() * (1 - t) + b.green() * t),
        round(a.blue()  * (1 - t) + b.blue()  * t),
    )


def _luma(c: QColor) -> float:
    """Perceived brightness 0..255 (Rec. 601)."""
    return 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()


def build_palette(theme: Theme) -> QPalette | None:
    """Return a full custom QPalette for *theme*, or None for a system theme.

    None signals the caller to restore the native style + standardPalette()
    (Air). For Dark/Mono/Retro, every ColorRole that Qt-drawn widgets read is
    set explicitly so dialogs, menus and push-buttons are readable.

    Luminance-aware: on a DARK background the derived roles (button, base, …)
    go *lighter* than the window; on a LIGHT background (e.g. the inverted Mono
    theme) they go *darker* — otherwise "lighter than white" would clamp to
    white and the buttons would vanish into the window.
    """
    if theme.system_palette:
        return None

    bg = QColor(theme.bg)
    fg = QColor(theme.fg)

    if _luma(bg) > 140:               # LIGHT theme → derive darker shades
        window    = _shift(bg, -12)   # window slightly off-white
        base      = bg                # inputs = the pure (lightest) bg
        alt_base  = _shift(bg, -10)
        button    = _shift(bg, -28)   # push-button face, clearly darker
        tip_bg    = _shift(bg, -16)
        highlight = _blend(fg, bg, 0.25)   # selection: dark, toward fg
    else:                             # DARK theme → derive lighter shades
        window    = bg
        base      = _shift(bg, -8)    # text-entry background, slightly darker
        alt_base  = _shift(bg, +6)
        button    = _shift(bg, +28)   # push-button face, clearly lighter
        tip_bg    = _shift(bg, +28)
        highlight = _blend(fg, bg, 0.45)   # selection: accent toward fg
    disabled  = _blend(fg, bg, 0.55)   # greyed-out text

    pal = QPalette()
    R = QPalette.ColorRole
    G = QPalette.ColorGroup

    pal.setColor(R.Window,          window)
    pal.setColor(R.WindowText,      fg)
    pal.setColor(R.Base,            base)
    pal.setColor(R.AlternateBase,   alt_base)
    pal.setColor(R.Text,            fg)
    pal.setColor(R.Button,          button)
    pal.setColor(R.ButtonText,      fg)        # ← the unreadable-button fix
    pal.setColor(R.BrightText,      QColor("#ff5555"))
    pal.setColor(R.ToolTipBase,     tip_bg)
    pal.setColor(R.ToolTipText,     fg)
    pal.setColor(R.PlaceholderText, _blend(fg, bg, 0.5))
    pal.setColor(R.Highlight,       highlight)
    pal.setColor(R.HighlightedText, bg)
    pal.setColor(R.Link,            highlight)

    # Disabled group: dim the text-ish roles so inactive widgets read greyed.
    for role in (R.Text, R.ButtonText, R.WindowText):
        pal.setColor(G.Disabled, role, disabled)

    return pal


# ---------------------------------------------------------------------------
# RX highlight colour roles
# ---------------------------------------------------------------------------

# LERNMODUS — why luma-based (light/dark bucket) instead of one fixed colour
# set per theme.key: a per-key lookup ("dark" -> these three hex values,
# "mono" -> those, ...) has to be hand-extended every time a new preset is
# added, and silently falls back to something wrong if someone forgets. Luma
# only cares whether theme.bg is visually light or dark, so it classifies any
# future/custom theme (a user-picked bg/fg pair, not just the four built-in
# presets) automatically -- the same two-bucket logic that already decides
# button/window shading in build_palette() above, reused here for the RX
# panel's semantic highlight colours instead of full palette roles.
def semantic_colors(theme: Theme) -> dict[str, str]:
    """RX highlight colours (received / echo / warning) for *theme*.

    Bucketed by background luma rather than by theme.key, so a future custom
    theme gets readable RX colours without a hand-added case here. Threshold
    128 splits at roughly perceptual middle grey.

    P77: rx_received is the configured RX colour (theme.rx); the contrast
    figures below describe the luma-bucketed echo/warning colours and the
    old fixed rx_received values.

    Contrast check (rough luma distance to theme.bg, target > 80):
      Dark bucket   (bg luma ~9-30 for Retro/Dark):
        rx_received #88ccff (luma ~190) -> diff ~160-181
        rx_echo      #ffaa00 (luma ~176) -> diff ~146-167
        rx_warning   #ff9900 (luma ~166) -> diff ~136-157
      Light bucket  (bg luma ~255 for Mono/Air):
        rx_received #0055aa (luma ~69)  -> diff ~186
        rx_echo      #b36b00 (luma ~116) -> diff ~139
        rx_warning   #b34700 (luma ~95)  -> diff ~160
      All comfortably clear the 80 target.
    """
    dark_bg = _luma(QColor(theme.bg)) < 128
    return {
        # P77: the received-text colour is the configured RX colour (the
        # Theme carries AppearanceConfig.rx_color); echo/warning stay luma-bucketed.
        "rx_received": theme.rx,
        # P77a: the echo colour IS the theme's system colour (one source;
        # the old light value #b36b00 reached only 4.2 : 1 on white).
        "rx_echo":     role_colors(theme.key, theme.bg).sys_color,
        "rx_warning":  "#ff9900" if dark_bg else "#b34700",
    }
