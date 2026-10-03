"""
opmode_rtty_base.py — Shared base class for RTTY-type opmode screens.

Used by:
    baudot_screen.py  → BaudotScreen(RttyBaseScreen)
    ascii_screen.py   → AsciiScreen(RttyBaseScreen)

What the base class provides:
    - Title label (left) + UTC clock (right)
    - RBAUD dropdown (overridable via class attributes)
    - Row 1: SEND / RECEIVE buttons (prominent, blinking)
    - Row 2: mode-specific buttons via _build_mode_buttons() — subclass implements
    - RX window (expands vertically)
    - TX window (5 lines, block cursor, initial focus)
    - Macro bar (6 macros + Edit Macros)
    - EventFilter: all keypresses redirect to TX window

What the subclass provides:
    - MODE_TITLE : str          e.g. "Baudot" or "ASCII RTTY"
    - _build_mode_buttons(layout: QHBoxLayout) — fills row 2

Refactored 2026-05-03:
    Theme system  → ui_theme.py
    MacroStore    → macro_store.py
    TX controller → tx_controller.py
"""

from __future__ import annotations

from datetime import datetime, timezone
from PyQt6.QtWidgets import (
    QWidget, QApplication,
    QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QPushButton,
    QComboBox, QSizePolicy, QFrame,
)
from PyQt6.QtCore import QMimeData
from PyQt6.QtCore import pyqtSignal, Qt, QTimer, QEvent
from PyQt6.QtGui import QFont, QKeyEvent, QTextCursor, QTextCharFormat, QColor

from .ui_theme import (
    get_theme, set_theme, apply_app_style,
    style_rx_widget, style_tx_widget,
    THEMES,
)
from .macro_store import (
    MacroStore, MacroEditDialog, MACRO_COUNT, add_hline, apply_macro_tooltips,
)
from .screen_focus_controller import is_keyboard_input_widget

# ---------------------------------------------------------------------------
# Layout constants (same across all RTTY screens)
# ---------------------------------------------------------------------------

BTN_W      = 90
SPACING    = 6
ROW2_TOTAL = 7 * BTN_W + 6 * SPACING
PROM_W     = (ROW2_TOTAL - SPACING) // 2

# RBAUD values for Baudot and ASCII
RBAUD_VALUES = ["45", "50", "75", "100", "110", "150", "200", "300"]

# ---------------------------------------------------------------------------
# Button styles
# ---------------------------------------------------------------------------

STYLE_PROM_INACTIVE = (
    "QPushButton {"
    "  background-color: #555555; color: #cccccc;"
    "  border: 2px solid #444444; border-radius: 6px;"
    "  font-size: 13pt; font-weight: bold; padding: 6px;"
    "}"
)
STYLE_SEND_ON = (
    "QPushButton {"
    "  background-color: #cc2222; color: white;"
    "  border: 2px solid #991111; border-radius: 6px;"
    "  font-size: 13pt; font-weight: bold; padding: 6px;"
    "}"
)
STYLE_SEND_BLINK = (
    "QPushButton {"
    "  background-color: #ff7777; color: white;"
    "  border: 2px solid #cc2222; border-radius: 6px;"
    "  font-size: 13pt; font-weight: bold; padding: 6px;"
    "}"
)
STYLE_RECEIVE_ON = (
    "QPushButton {"
    "  background-color: #3a9e3a; color: white;"
    "  border: 2px solid #2a7a2a; border-radius: 6px;"
    "  font-size: 13pt; font-weight: bold; padding: 6px;"
    "}"
)

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def make_toggle_button(label: str) -> QPushButton:
    """Small toggle button: green = ON, grey = OFF. NoFocus policy."""
    btn = QPushButton(label)
    btn.setCheckable(True)
    btn.setChecked(False)
    btn.setFixedWidth(BTN_W)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    _apply_toggle_style(btn)
    btn.toggled.connect(lambda _c, b=btn: _apply_toggle_style(b))
    return btn


def make_help_button(topic: str) -> QPushButton:
    """Small ``?`` button that opens the help viewer for *topic*.

    One shared factory used by every opmode screen, so the look and the
    NoFocus behaviour stay identical everywhere.

    Lernmodus
    ---------
    - The ``show_help`` import is **lazy** (done inside the click slot, not at
      module top). ``help_viewer`` lives in the same ``ui/screens`` package and
      imports screen helpers itself, so a top-level import here could create an
      import cycle. Importing on click avoids that entirely.
    - ``NoFocus`` matters: like every other button on these screens, a click on
      ``?`` must never steal keyboard focus away from the TX window.
    - ``btn.window()`` is passed as the dialog parent so the modal help viewer
      centres on the main window and stays on top of it.
    """
    btn = QPushButton("?")
    btn.setFixedWidth(28)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    btn.setToolTip("Open the help page for this operating mode.")

    def _open() -> None:
        from .help_viewer import show_help
        show_help(topic, parent=btn.window())

    btn.clicked.connect(_open)
    return btn


def _apply_toggle_style(btn: QPushButton) -> None:
    if btn.isChecked():
        btn.setStyleSheet(
            "QPushButton { background-color: #3a9e3a; color: white;"
            " border: 1px solid #2a7a2a; border-radius: 4px; padding: 4px; }"
        )
    else:
        btn.setStyleSheet(
            "QPushButton { background-color: #888888; color: white;"
            " border: 1px solid #555555; border-radius: 4px; padding: 4px; }"
        )



# ---------------------------------------------------------------------------
# TxInputWidget — TX input field with edit protection and ACK colouring
# ---------------------------------------------------------------------------

class TxInputWidget(QTextEdit):
    """TX input QTextEdit with char-level ACK tracking.

    Extends QTextEdit with:
    - char_typed signal — fired on every printable keystroke and paste
    - colour_at()       — inverse-colours one char after DATA_ACK
    - set_cycle_anchor() — updates doc position anchor for colour_at()
    - Edit protection   — already-sent chars (inverse) cannot be modified
    - CTRL+D            — inserts [^D] EOT marker (char = \x04)
    - CTRL+T            — opens n dialog, inserts [^T:n] timed marker (char = \x1b + str(n))
    - insertFromMimeData — paste fires char_typed per character

    Colour conventions (theme-aware):
        Unsent  : the TX colour (AppearanceConfig.tx_color)
        ACK'd   : inverse - background tx_color, text bg_color (P77)
        EOT [^D]: white text on orange background
    """

    # Emitted on every printable keystroke and paste.
    # Connected by MainWindow to TxController.on_char_typed().
    char_typed = pyqtSignal(str, str, int)   # (char, display, doc_pos)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._doc_offset  = 0   # doc position of cycle start
        self._cycle_start = 0   # _arr index of cycle start
        self._doc_extra   = 0   # extra doc chars vs _arr entries (e.g. [^D] = 4 doc, 1 arr → +3)
        # Dynamic edit-protection boundary. _doc_offset only moves at cycle
        # end (set_cycle_anchor on RECEIVE), so it cannot protect chars sent
        # WITHIN the current SEND cycle. _sent_boundary advances every time a
        # char is confirmed sent (colour_at sent=True / immediate space in
        # SEND), so already-transmitted chars lock as soon as they are sent.
        self._sent_boundary = 0   # doc position just past the last sent char

        # Fallbacks (the Dark defaults) until set_theme_colors() is called by
        # MainWindow with AppearanceConfig.tx_color / bg_color.
        self._tx_fg_color: str = "#ffee88"
        self._tx_bg_color: str = "#1e1e1e"

    def set_theme_colors(self, fg: str, bg: str) -> None:
        """Update the per-character colours used for unsent TX text.

        Called by MainWindow on every theme change so the char-level
        QTextCharFormat colouring in colour_at() and the space-insert path
        (keyPressEvent) follows the currently active theme, independent of
        the old ui_theme.get_theme() system.
        """
        self._tx_fg_color = fg
        self._tx_bg_color = bg

    def clear(self) -> None:
        """Clear the document, then restore the theme-aware default format.

        QTextEdit.clear() resets the cursor's current character format to the
        document's built-in default, discarding whatever set_theme_colors()
        last applied. Without this override, text typed after Clear TX (or any
        other clear() caller) reverts to a stale colour until the next
        _apply_appearance() theme refresh happens to run. Overriding clear()
        here — instead of patching every call site individually — means the
        fix applies uniformly no matter who calls clear().
        """
        super().clear()
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(self._tx_fg_color))
        self.setCurrentCharFormat(fmt)

    def set_cycle_anchor(self, doc_offset: int, cycle_start: int) -> None:
        """Update anchors for colour_at() positioning.

        doc_offset must be the actual document character position
        (tx.document().characterCount() - 1), NOT the _arr index.
        This correctly accounts for multi-char visual markers like [^D].
        """
        import logging as _log
        _log.getLogger('pk232py.ui.screens.opmode_rtty_base').debug(
            "set_cycle_anchor: doc_offset=%d cycle_start=%d doc_chars=%d",
            doc_offset, cycle_start,
            self.document().characterCount() - 1
        )
        self._doc_offset  = doc_offset
        self._cycle_start = cycle_start
        self._doc_extra   = 0   # reset for next cycle
        # Re-anchor the dynamic protection boundary to the new cycle start.
        # Everything before doc_offset is already transmitted (protected);
        # the next cycle's chars will advance _sent_boundary as they send.
        self._sent_boundary = doc_offset

    def colour_at(self, arr_idx: int, sent: bool = True) -> None:
        """Colour one character at arr_idx.

        sent=True  → inverse: background tx_color, text bg_color (ACK'd)
        sent=False → normal TX colour (unsent)
        """
        doc_pos = self._doc_offset + (arr_idx - self._cycle_start)
        if doc_pos < 0:
            return
        doc = self.document()
        # Valid positions: 0 .. characterCount()-2
        # characterCount()-1 is the block terminator — never addressable
        if doc_pos >= doc.characterCount() - 1:
            return
        try:
            c = QTextCursor(doc)
            c.setPosition(doc_pos)
            c.movePosition(QTextCursor.MoveOperation.Right,
                           QTextCursor.MoveMode.KeepAnchor, 1)
            if not c.hasSelection():
                return
        except Exception:
            return
        f = QTextCharFormat()
        if sent:
            # Inverse (P77): background = TX colour, text = display background
            # - readable on every theme, unlike the old fixed black on gold.
            f.setForeground(QColor(self._tx_bg_color))
            f.setBackground(QColor(self._tx_fg_color))
            # Lock this just-sent char: advance the edit-protection boundary
            # so the cursor can no longer be moved back into it mid-SEND.
            if doc_pos + 1 > self._sent_boundary:
                self._sent_boundary = doc_pos + 1
        else:
            # Normal unsent: theme TX colour
            t = get_theme()
            f.setForeground(QColor(self._tx_fg_color))
            f.setBackground(QColor(t["bg_input_tx"]))
        c.setCharFormat(f)

    # ── Edit protection ───────────────────────────────────────────────

    def _edit_boundary(self) -> int:
        """Doc position of the first editable character.

        Everything before this is protected (already transmitted). The
        boundary is the cycle-start anchor (_doc_offset) advanced by
        _sent_boundary, which grows each time a char is confirmed sent. Using
        the max guards against either one trailing behind the other; in
        practice _sent_boundary >= _doc_offset always once a cycle starts.
        """
        return max(self._doc_offset, self._sent_boundary)

    def _selection_touches_protected(self) -> bool:
        """True if cursor or selection overlaps the protected (sent) zone."""
        boundary = self._edit_boundary()
        c = self.textCursor()
        if not c.hasSelection():
            # Backspace deletes char BEFORE cursor — protect if cursor
            # is AT or BEFORE the boundary (would delete into sent zone)
            return c.position() <= boundary
        return min(c.position(), c.anchor()) < boundary

    def _push_cursor_to_boundary(self) -> None:
        """Move cursor to _doc_offset if it drifted into the protected zone.

        Two cases:
        (a) Absolute position before _doc_offset — sent text; push forward.
        (b) Cursor sits in an EARLIER block (line) than the one containing
            _doc_offset — e.g. Up-Arrow into a fully-sent earlier line. Push
            to _doc_offset so editing there is blocked.

        Case (b) compares against the start of _doc_offset's OWN block, NOT
        against _doc_offset itself. Comparing against _doc_offset directly
        would also snap the cursor whenever the user edits the unsent tail of
        the same line whose sent head lies before _doc_offset — i.e. the normal
        "keep typing on one line after RECEIVE" case, which must stay freely
        editable. (In practice (a) already catches earlier-line positions since
        they are < _doc_offset; (b) is a defensive guard for that intent.)
        """
        c = self.textCursor()
        boundary = self._edit_boundary()
        offset_block_start = self.document().findBlock(boundary).position()
        needs_push = (
            c.position() < boundary
            or c.block().position() < offset_block_start
        )
        if needs_push:
            c.setPosition(boundary)
            self.setTextCursor(c)

    # ── Paste handling ────────────────────────────────────────────────

    def insertFromMimeData(self, source: QMimeData) -> None:
        """Handle paste — emit char_typed for each pasted character.

        Pre-truncates text at available buffer space before iterating.
        This ensures BUFFER_FULL is emitted at most ONCE per paste,
        regardless of how many characters exceed the limit.
        """
        if self._selection_touches_protected():
            return
        text = source.text()
        if not text and source.hasHtml():
            import re as _re
            html = source.html()
            text = _re.sub(r'<[^>]+>', '', html)
            text = (text.replace('&amp;', '&').replace('&lt;', '<')
                        .replace('&gt;', '>').replace('&nbsp;', ' ')
                        .replace('&#13;', '\r').replace('&#10;', '\n'))
        if not text:
            return
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        paste_chars = [ch for ch in text if ch == '\n' or ch.isprintable()]
        if not paste_chars:
            return

        # Find TxController — stored directly on widget if wired,
        # otherwise search parent chain as fallback.
        ctrl = getattr(self, '_ctrl_ref', None)
        if ctrl is None:
            p = self.parent()
            while p is not None:
                c = getattr(p, '_tx_ctrl', None)
                if c is not None:
                    ctrl = c
                    self._ctrl_ref = ctrl   # cache for next paste
                    break
                try:
                    p = p.parent()
                except Exception:
                    break

        # Pre-truncate to available buffer space — emit BUFFER_FULL once
        if ctrl is not None:
            try:
                pending = len(ctrl._arr) - ctrl._tx_sent_idx
            except Exception:
                pending = 0
            space = ctrl.TX_MAX - max(0, pending)
            if space <= 0:
                ctrl.warning.emit("BUFFER_FULL")
                return
            if len(paste_chars) > space:
                paste_chars = paste_chars[:space]
                ctrl.warning.emit("BUFFER_FULL")

        if not paste_chars:
            return

        t = get_theme()
        f = QTextCharFormat()
        f.setForeground(QColor(t['tx_color']))
        for ch in paste_chars:
            if ch == '\n':
                self.setCurrentCharFormat(f)
                c = self.textCursor()
                doc_pos = c.position()   # position BEFORE the block break
                c.insertBlock()
                self.setTextCursor(c)
                self.char_typed.emit('\r\n', '<CR/LF>\n', doc_pos)
            else:
                self.setCurrentCharFormat(f)
                cur = self.textCursor()
                doc_pos = cur.position()   # position BEFORE inserting ch
                cur.insertText(ch)
                self.char_typed.emit(ch, ch, doc_pos)

    # ── Keystroke handling ────────────────────────────────────────────

    def keyPressEvent(self, ev: QKeyEvent) -> None:
        """Handle keypresses with edit protection and EOT marker support.

        Protection: cursor/selection in sent zone (pos < _doc_offset)
            → collapse to end, block Backspace/Delete.

        CTRL+D: insert visible [^D] orange marker, emit char_typed(\x04).

        All other printable keys: emit char_typed(char, char).
        """
        key  = ev.key()
        text = ev.text()
        mods = ev.modifiers()
        Ctrl = Qt.KeyboardModifier.ControlModifier
        t    = get_theme()

        # Normal TX char format
        f_normal = QTextCharFormat()
        f_normal.setForeground(QColor(t['tx_color']))

        # ── Cursor movement — allow but clamp to boundary ─────────────
        # All directions run through _push_cursor_to_boundary() as a
        # defensive post-correction. Left/Home/Up/PageUp can land in the
        # protected zone directly; Right/End/Down/PageDown cannot, but the
        # clamp is harmless and keeps the boundary invariant in one place.
        if key in (Qt.Key.Key_Left,  Qt.Key.Key_Right,
                   Qt.Key.Key_Home,  Qt.Key.Key_End,
                   Qt.Key.Key_Up,    Qt.Key.Key_Down,
                   Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
            super().keyPressEvent(ev)
            self._push_cursor_to_boundary()
            return

        # CTRL+D: insert [^D] EOT marker (switch to RECEIVE when reached)
        if mods == Ctrl and key == Qt.Key.Key_D:
            f_eot = QTextCharFormat()
            f_eot.setForeground(QColor(get_theme()["bg_color"]))   # P77a: inverse of sys_color
            f_eot.setBackground(QColor(get_theme()["sys_color"]))
            f_eot.setFontWeight(700)
            c = self.textCursor()
            eot_doc_pos = c.position()
            c.setCharFormat(f_eot)
            c.insertText("[^D]")
            c.setCharFormat(f_normal)
            self.setTextCursor(c)
            if not hasattr(self, "_eot_positions"):
                self._eot_positions: list[dict] = []
            self._eot_positions.append({'pos': eot_doc_pos, 'len': 4})
            # [^D] = 4 doc chars but 1 _arr entry → 3 extra doc positions
            self._doc_extra += 3
            self.char_typed.emit("\x04", "[^D]", eot_doc_pos)
            return

        # CTRL+T: open n-dialog, insert [^T:n] timed marker
        # (RECEIVE, wait n seconds, SEND)
        if mods == Ctrl and key == Qt.Key.Key_T:
            from PyQt6.QtWidgets import QInputDialog
            n, ok = QInputDialog.getInt(
                self, "Timed Marker",
                "Wait time in seconds (1–10):",
                value=5, min=1, max=10
            )
            if not ok:
                return
            marker = f"[^T:{n}]"          # e.g. "[^T:5]" = 6 chars
            marker_len = len(marker)       # 6 for n=1..9, 7 for n=10
            f_tmr = QTextCharFormat()
            f_tmr.setForeground(QColor(get_theme()["bg_color"]))   # P77a: inverse of dim_color
            f_tmr.setBackground(QColor(get_theme()["dim_color"]))
            f_tmr.setFontWeight(700)
            c = self.textCursor()
            tmr_doc_pos = c.position()
            c.setCharFormat(f_tmr)
            c.insertText(marker)
            c.setCharFormat(f_normal)
            self.setTextCursor(c)
            if not hasattr(self, "_eot_positions"):
                self._eot_positions: list[dict] = []
            self._eot_positions.append({'pos': tmr_doc_pos, 'len': marker_len})
            # marker_len doc chars but 1 _arr entry → (marker_len-1) extra
            self._doc_extra += marker_len - 1
            # Sentinel: ESC + decimal n  (e.g. "\x1b5" or "\x1b10")
            self.char_typed.emit(f"\x1b{n}", marker, tmr_doc_pos)
            return

        # ── Any key touching protected zone ───────────────────────────
        if self._selection_touches_protected():
            if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete,
                       Qt.Key.Key_Return, Qt.Key.Key_Enter) or (
                       text and text.isprintable()):
                # Move cursor to boundary (first editable position)
                # and block destructive keys
                c = self.textCursor()
                c.setPosition(self._edit_boundary())
                self.setTextCursor(c)
                if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
                    return
            else:
                super().keyPressEvent(ev)
                return

        # ── Backspace / Delete (outside protected zone) ───────────────
        if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            c = self.textCursor()
            pos = c.position()
            eot_positions = getattr(self, "_eot_positions", [])
            # Check if cursor is right after any marker.
            # Each entry: {'pos': int, 'len': int}
            # Marker at doc_pos p with length L occupies p..p+L-1,
            # cursor sits at p+L after the marker.
            eot_hit = None
            for entry in eot_positions:
                # Support both old int entries and new dict entries
                if isinstance(entry, dict):
                    p, mlen = entry['pos'], entry['len']
                else:
                    p, mlen = entry, 4   # legacy: [^D] was always 4
                if pos == p + mlen:
                    eot_hit = (p, mlen, entry)
                    break
            if eot_hit is not None:
                p, mlen, entry_ref = eot_hit
                # Delete all marker chars atomically
                c.setPosition(p)
                c.setPosition(p + mlen, QTextCursor.MoveMode.KeepAnchor)
                c.removeSelectedText()
                self._eot_positions.remove(entry_ref)
                # Shift positions of markers that come after this one
                new_list = []
                for e in self._eot_positions:
                    if isinstance(e, dict):
                        if e['pos'] > p:
                            new_list.append({'pos': e['pos'] - mlen, 'len': e['len']})
                        else:
                            new_list.append(e)
                    else:
                        new_list.append(e - mlen if e > p else e)
                self._eot_positions = new_list
                # Restore the extra doc positions for this marker
                self._doc_extra = max(0, self._doc_extra - (mlen - 1))
                # Notify controller: BS sentinel — 1 _arr entry removed
                # (doc_pos irrelevant for the delete sentinel → -1)
                self.char_typed.emit('\x08', '', -1)
            else:
                # Normal backspace — notify controller then delete
                self.char_typed.emit('\x08', '', -1)
                super().keyPressEvent(ev)
                # Shift marker positions after the deleted char
                new_list = []
                for e in getattr(self, "_eot_positions", []):
                    if isinstance(e, dict):
                        if e['pos'] >= pos:
                            new_list.append({'pos': e['pos'] - 1, 'len': e['len']})
                        else:
                            new_list.append(e)
                    else:
                        new_list.append(e - 1 if e >= pos else e)
                self._eot_positions = new_list
            return

        # ── Space: send immediately and colour as sent in SEND mode ──────
        # In Morse, a space produces a word gap (no $2F echo). In EAS mode
        # the space would therefore never be coloured. To avoid this and
        # prevent bypassing edit protection with uncoloured spaces, we
        # colour the space immediately when SEND is active.
        # In RECEIVE mode (pre-type), space keeps the normal TX colour.
        if text == ' ':
            # Resolve TxController via cached ref or parent-chain walk
            # (same pattern as insertFromMimeData).
            ctrl = getattr(self, '_ctrl_ref', None)
            if ctrl is None:
                p = self.parent()
                while p is not None:
                    c2 = getattr(p, '_tx_ctrl', None)
                    if c2 is not None:
                        ctrl = c2
                        self._ctrl_ref = ctrl
                        break
                    try:
                        p = p.parent()
                    except Exception:
                        break
            send_active = getattr(ctrl, 'send_active', False) if ctrl else False

            # Insert the space in normal TX colour
            f_tx = QTextCharFormat()
            f_tx.setForeground(QColor(self._tx_fg_color))
            cur = self.textCursor()
            space_doc_pos = cur.position()
            cur.setCharFormat(f_tx)
            cur.insertText(' ')
            self.setTextCursor(cur)
            self.char_typed.emit(' ', ' ', space_doc_pos)

            if send_active:
                # Immediately colour as sent (inverse: tx colour / bg colour).
                f_sent = QTextCharFormat()
                f_sent.setForeground(QColor(self._tx_bg_color))
                f_sent.setBackground(QColor(self._tx_fg_color))
                cur2 = self.textCursor()
                cur2.setPosition(space_doc_pos)
                cur2.movePosition(
                    QTextCursor.MoveOperation.Right,
                    QTextCursor.MoveMode.KeepAnchor, 1)
                cur2.setCharFormat(f_sent)
                cur2.setPosition(space_doc_pos + 1)  # restore cursor to end
                self.setTextCursor(cur2)
                # Lock the just-sent space too — same boundary advance as
                # colour_at() does for ACK'd chars (space has no $5F ACK path).
                if space_doc_pos + 1 > self._sent_boundary:
                    self._sent_boundary = space_doc_pos + 1
            return

        # ── Enter / printable characters ──────────────────────────────
        # doc_pos = cursor position BEFORE the insert (where the char lands).
        # Must be read before super().keyPressEvent(), which advances the cursor.
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.setCurrentCharFormat(f_normal)
            doc_pos = self.textCursor().position()
            super().keyPressEvent(ev)
            self.char_typed.emit('\r\n', '<CR/LF>\n', doc_pos)
        elif text and text.isprintable():
            self.setCurrentCharFormat(f_normal)
            doc_pos = self.textCursor().position()
            super().keyPressEvent(ev)
            self.char_typed.emit(text, text, doc_pos)
        else:
            super().keyPressEvent(ev)

# ---------------------------------------------------------------------------
# RttyBaseScreen — abstract base class
# ---------------------------------------------------------------------------

class RttyBaseScreen(QWidget):
    """Shared layout for Baudot and ASCII RTTY screens.

    Subclasses MUST set:
        MODE_TITLE : str

    Subclasses MUST implement:
        _build_mode_buttons(layout: QHBoxLayout) -> None
            Fills row 2 with mode-specific buttons.
            Must call layout.addStretch() at the end.
    """

    MODE_TITLE:  str       = "RTTY"
    HELP_TOPIC:  str       = "baudot"   # overridden by AsciiScreen → "ascii"
    BAUD_LABEL:  str       = "RBAUD (Speed):"
    BAUD_VALUES: list[str] = RBAUD_VALUES

    # Signals connected by MainWindow
    char_ready   = pyqtSignal(str)   # keypress while SEND active
    clear_tx_req = pyqtSignal()
    clear_rx_req = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._macro_store = MacroStore()
        err = self._macro_store.load()
        if err:
            print(f"[MacroStore] {err}")

        self._blink_phase = False
        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(400)
        self._blink_timer.timeout.connect(self._on_blink_tick)

        self._utc_timer = QTimer(self)
        self._utc_timer.setInterval(1000)
        self._utc_timer.timeout.connect(self._update_utc)
        self._utc_timer.start()

        self._build_ui()
        self.installEventFilter(self)
        QTimer.singleShot(0, lambda: self.tx_input.setFocus())

        # Central tooltips — applied after _build_ui() (which calls the
        # subclass's _build_mode_buttons), so every button exists. Covers all
        # RttyBaseScreen subclasses (Baudot, ASCII).
        from pk232py.ui.tooltips import apply_tooltips
        apply_tooltips(self)

    # ------------------------------------------------------------------
    # NoFocus button helper
    # ------------------------------------------------------------------

    @staticmethod
    def _no_focus_btn(label: str, width: int | None = None,
                      height: int | None = None,
                      checkable: bool = False) -> QPushButton:
        """Create a QPushButton with NoFocus policy.

        NoFocus means: a mouse click activates the button but does NOT
        steal keyboard focus from the TX window.
        """
        btn = QPushButton(label)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setCheckable(checkable)
        if width is not None:
            btn.setFixedWidth(width)
        if height is not None:
            btn.setFixedHeight(height)
        return btn

    # ------------------------------------------------------------------
    # EventFilter: redirect all keypresses to TX window
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.KeyPress:
            # is_keyboard_input_widget() walks the parent chain and
            # covers every keyboard-input widget type, including
            # QComboBox and QAbstractSpinBox (P41) — not just
            # QLineEdit/QTextEdit. Shared with the other opmode screens
            # instead of a locally copied type check (P41.2).
            if (is_keyboard_input_widget(self.focusWidget())
                    or is_keyboard_input_widget(obj)):
                return super().eventFilter(obj, event)
            if hasattr(self, 'tx_input') and self.tx_input is not None:
                self.tx_input.setFocus()
                QApplication.sendEvent(self.tx_input, event)
                return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # UI build
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(6)
        root.setContentsMargins(8, 8, 8, 8)

        # Title row: mode name left, UTC clock right
        title_row = QHBoxLayout()
        title = QLabel(self.MODE_TITLE)
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        title_row.addWidget(title)
        title_row.addStretch()
        self.lbl_utc = QLabel()
        self.lbl_utc.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self.lbl_utc.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._update_utc()
        title_row.addWidget(self.lbl_utc)
        title_row.addWidget(make_help_button(self.HELP_TOPIC))
        root.addLayout(title_row)

        add_hline(root)

        # Baud parameter row
        param_row = QHBoxLayout()
        param_row.setSpacing(8)
        lbl = QLabel(self.BAUD_LABEL)
        lbl.setFixedWidth(110)
        param_row.addWidget(lbl)
        self.combo_rbaud = QComboBox()
        self.combo_rbaud.addItems(self.BAUD_VALUES)
        self.combo_rbaud.setCurrentText("45")
        self.combo_rbaud.setFixedWidth(80)
        param_row.addWidget(self.combo_rbaud)
        param_row.addStretch()
        root.addLayout(param_row)

        add_hline(root)

        # Row 1: SEND / RECEIVE (prominent)
        row1 = QHBoxLayout()
        row1.setSpacing(SPACING)

        self.btn_send = QPushButton("Send  [ALT+X]")
        self.btn_send.setFixedWidth(PROM_W)
        self.btn_send.setFixedHeight(46)
        self.btn_send.setCheckable(True)
        self.btn_send.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_send.setStyleSheet(STYLE_PROM_INACTIVE)
        self.btn_send.toggled.connect(self._on_send_toggled)

        self.btn_receive = QPushButton("Receive  [ALT+R]")
        self.btn_receive.setFixedWidth(PROM_W)
        self.btn_receive.setFixedHeight(46)
        self.btn_receive.setCheckable(True)
        self.btn_receive.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_receive.setStyleSheet(STYLE_PROM_INACTIVE)
        self.btn_receive.toggled.connect(self._on_receive_toggled)

        row1.addWidget(self.btn_send)
        row1.addWidget(self.btn_receive)
        row1.addStretch()
        root.addLayout(row1)

        # Row 2: mode-specific buttons — filled by subclass
        row2 = QHBoxLayout()
        row2.setSpacing(SPACING)
        self._build_mode_buttons(row2)
        root.addLayout(row2)

        add_hline(root)

        # RX window
        self.rx_display = QTextEdit()
        self.rx_display.setReadOnly(True)
        self.rx_display.setFont(QFont("Courier New", 10))
        self.rx_display.setPlaceholderText("RX — received characters appear here …")
        self.rx_display.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        style_rx_widget(self.rx_display)
        root.addWidget(self.rx_display, stretch=1)

        add_hline(root)

        # TX window (5 lines) — TxInputWidget for char-level ACK tracking
        self.tx_input = TxInputWidget()
        self.tx_input.setFont(QFont("Courier New", 10))
        self.tx_input.setPlaceholderText("TX — type here …")
        fm = self.tx_input.fontMetrics()
        mc = self.tx_input.contentsMargins()
        self.tx_input.setFixedHeight(
            fm.lineSpacing() * 5 + mc.top() + mc.bottom() + 8
        )
        style_tx_widget(self.tx_input)
        root.addWidget(self.tx_input)

        add_hline(root)

        # Macro bar
        macro_row = QHBoxLayout()
        macro_row.setSpacing(SPACING)

        self.macro_buttons: list[QPushButton] = []
        for i in range(MACRO_COUNT):
            btn = QPushButton(self._macro_store.names[i])
            btn.setFixedWidth(BTN_W)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            macro_row.addWidget(btn)
            self.macro_buttons.append(btn)

        apply_macro_tooltips(self.macro_buttons, self._macro_store)

        macro_row.addStretch()

        # Clear TX / Clear RX / Edit Macros: NO stylesheet → fully palette-
        # driven (Fusion + the theme QPalette). Hardcoded text colours here
        # (orange/blue/border-only) were unreadable on the Air/light theme;
        # the SEND/RECEIVE and toggle buttons keep their semantic colours.
        self.btn_clear_tx = QPushButton("Clear TX")
        self.btn_clear_tx.setFixedWidth(BTN_W)
        self.btn_clear_tx.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_clear_tx.clicked.connect(self.clear_tx_req.emit)
        macro_row.addWidget(self.btn_clear_tx)

        self.btn_clear_rx = QPushButton("Clear RX")
        self.btn_clear_rx.setFixedWidth(BTN_W)
        self.btn_clear_rx.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_clear_rx.clicked.connect(self.clear_rx_req.emit)
        macro_row.addWidget(self.btn_clear_rx)

        self.btn_edit_macros = QPushButton("Edit Macros")
        self.btn_edit_macros.setFixedWidth(BTN_W + 20)
        self.btn_edit_macros.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_edit_macros.clicked.connect(self._on_edit_macros)
        macro_row.addWidget(self.btn_edit_macros)
        root.addLayout(macro_row)

    # ------------------------------------------------------------------
    # Abstract method — subclass MUST override
    # ------------------------------------------------------------------

    def _build_mode_buttons(self, layout: QHBoxLayout) -> None:
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _build_mode_buttons()."
        )

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_send_toggled(self, checked: bool) -> None:
        if checked:
            # SEND activated — deactivate RECEIVE visually
            self.btn_receive.blockSignals(True)
            self.btn_receive.setChecked(False)
            self.btn_receive.blockSignals(False)
            self.btn_receive.setStyleSheet(STYLE_PROM_INACTIVE)
            self._blink_phase = True
            self.btn_send.setStyleSheet(STYLE_SEND_ON)
            self._blink_timer.start()
        else:
            # SEND deactivated (second click on SEND) → switch to RECEIVE
            self._blink_timer.stop()
            self.btn_send.setStyleSheet(STYLE_PROM_INACTIVE)
            self.btn_receive.blockSignals(True)
            self.btn_receive.setChecked(True)
            self.btn_receive.blockSignals(False)
            self.btn_receive.setStyleSheet(STYLE_RECEIVE_ON)

    def _on_receive_toggled(self, checked: bool) -> None:
        if not checked:
            return
        self._blink_timer.stop()
        self.btn_send.blockSignals(True)
        self.btn_send.setChecked(False)
        self.btn_send.blockSignals(False)
        self.btn_send.setStyleSheet(STYLE_PROM_INACTIVE)
        self.btn_receive.setStyleSheet(STYLE_RECEIVE_ON)

    def _on_blink_tick(self) -> None:
        self._blink_phase = not self._blink_phase
        self.btn_send.setStyleSheet(
            STYLE_SEND_BLINK if self._blink_phase else STYLE_SEND_ON
        )

    def _update_utc(self) -> None:
        now = datetime.now(timezone.utc)
        self.lbl_utc.setText(now.strftime("UTC  %H:%M:%S"))

    def _on_edit_macros(self) -> None:
        dlg = MacroEditDialog(self._macro_store, parent=self)
        dlg.exec()
        for i, btn in enumerate(self.macro_buttons):
            btn.setText(self._macro_store.names[i])
        apply_macro_tooltips(self.macro_buttons, self._macro_store)