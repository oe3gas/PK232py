"""
macro_store.py — Macro persistence and edit dialog for PK232PY.

Provides:
    MacroStore      — load/save 6 macros from/to Macro.txt
    MacroEditDialog — modal dialog for editing macros

Used by RttyBaseScreen (opmode_rtty_base.py).

Usage:
    from .macro_store import MacroStore, MacroEditDialog
"""

from __future__ import annotations

import os
from PyQt6.QtWidgets import (
    QDialog, QScrollArea, QFrame, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QLineEdit, QPushButton, QMessageBox,
)
from PyQt6.QtGui import QFont, QKeyEvent, QTextCharFormat, QColor
from PyQt6.QtCore import Qt

from .ui_theme import get_theme

# Help viewer imported lazily to avoid circular imports
# from .help_viewer import show_help  (called at runtime)


class MacroTextEdit(QTextEdit):
    """QTextEdit for macro text with CTRL+D and CTRL+T support.

    CTRL+D inserts "[^D]" (4 chars) with orange inverse styling.
    CTRL+T opens a dialog for n (1–10), inserts "[^T:n]" (6–7 chars)
    with purple inverse styling.
    Backspace detects cursor right after any marker and deletes it
    atomically — _eot_positions stores {pos, len} dicts.

    No private-use Unicode — works on all Windows fonts.
    Stored as "[^D]" / "[^T:n]" in Macro.txt (human-readable).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._eot_positions: list[dict] = []  # {'pos': int, 'len': int}

    def keyPressEvent(self, ev: QKeyEvent) -> None:
        key  = ev.key()
        mods = ev.modifiers()

        # CTRL+D — insert [^D] orange marker (switch to RECEIVE)
        if mods == Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_D:
            f_eot = QTextCharFormat()
            f_eot.setForeground(QColor(get_theme()["bg_color"]))   # P77a: inverse of sys_color
            f_eot.setBackground(QColor(get_theme()["sys_color"]))
            f_eot.setFontWeight(700)
            f_normal = QTextCharFormat()
            c = self.textCursor()
            pos = c.position()
            c.setCharFormat(f_eot)
            c.insertText("[^D]")
            c.setCharFormat(f_normal)
            self.setTextCursor(c)
            self._eot_positions.append({'pos': pos, 'len': 4})
            return

        # CTRL+T — open n dialog, insert [^T:n] purple marker (timed RECEIVE)
        if mods == Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_T:
            from PyQt6.QtWidgets import QInputDialog
            n, ok = QInputDialog.getInt(
                self, "Timed Marker",
                "Wait time in seconds (1–10):",
                value=5, min=1, max=10
            )
            if not ok:
                return
            marker = f"[^T:{n}]"
            marker_len = len(marker)
            f_tmr = QTextCharFormat()
            f_tmr.setForeground(QColor(get_theme()["bg_color"]))   # P77a: inverse of dim_color
            f_tmr.setBackground(QColor(get_theme()["dim_color"]))
            f_tmr.setFontWeight(700)
            f_normal = QTextCharFormat()
            c = self.textCursor()
            pos = c.position()
            c.setCharFormat(f_tmr)
            c.insertText(marker)
            c.setCharFormat(f_normal)
            self.setTextCursor(c)
            self._eot_positions.append({'pos': pos, 'len': marker_len})
            return

        # Backspace — atomic delete of any marker if cursor is right after it
        if key == Qt.Key.Key_Backspace:
            c = self.textCursor()
            pos = c.position()
            for entry in list(self._eot_positions):
                p   = entry['pos']
                mlen = entry['len']
                if pos == p + mlen:
                    c.setPosition(p)
                    c.setPosition(p + mlen, QTextCursor.MoveMode.KeepAnchor)
                    c.removeSelectedText()
                    self._eot_positions.remove(entry)
                    self._eot_positions = [
                        {'pos': e['pos'] - mlen, 'len': e['len']}
                        if e['pos'] > p else e
                        for e in self._eot_positions
                    ]
                    return
            # Normal backspace — shift tracked positions
            if not c.hasSelection():
                self._eot_positions = [
                    {'pos': e['pos'] - 1, 'len': e['len']}
                    if e['pos'] >= pos else e
                    for e in self._eot_positions
                ]
            super().keyPressEvent(ev)
            return

        super().keyPressEvent(ev)

    def get_macro_text(self) -> str:
        """Return plain text — [^D] stored as literal 4-char sequence."""
        return self.toPlainText()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MACRO_COUNT    = 6
MACRO_NAME_MAX = 10    # characters
MACRO_TEXT_MAX = 200   # characters
MACRO_FILE     = "Macro.txt"


# ---------------------------------------------------------------------------
# Helper (shared with opmode_rtty_base)
# ---------------------------------------------------------------------------

def add_hline(layout) -> None:
    """Insert a horizontal separator line into a QVBoxLayout."""
    from PyQt6.QtWidgets import QFrame
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    layout.addWidget(line)


# ---------------------------------------------------------------------------
# MacroStore
# ---------------------------------------------------------------------------

class MacroStore:
    """Manages 6 macros (name + text) and their persistence in Macro.txt.

    File format (plain text, user-editable):
        # Comment lines start with #
        NAME|TEXT
        ...

    Escape rules (so each data line is always exactly one file line):
        Character in text  →  stored as
        \\n  (LF)           →  \\n   (backslash + n)
        \\r  (CR)           →  \\r   (backslash + r)
        \\   (backslash)    →  \\\\  (double backslash)
        |                  →  /    (avoid separator conflict)
    """

    def __init__(self, path: str = MACRO_FILE):
        self.path  = path
        self.names = [f"Macro {i}" for i in range(1, MACRO_COUNT + 1)]
        self.texts = [""] * MACRO_COUNT

    def load(self) -> str:
        """Load macros from file. Returns '' on success, error message otherwise."""
        if not os.path.isfile(self.path):
            return f"File '{self.path}' not found — using defaults."
        try:
            with open(self.path, encoding="utf-8") as fh:
                lines = fh.readlines()
        except OSError as exc:
            return f"Read error: {exc}"

        data = [
            ln.rstrip("\n") for ln in lines
            if ln.strip() and not ln.startswith("#")
        ]
        for idx in range(MACRO_COUNT):
            if idx >= len(data):
                break
            parts = data[idx].split("|", maxsplit=1)
            self.names[idx] = self._unescape(parts[0])[:MACRO_NAME_MAX]
            self.texts[idx] = self._unescape(
                parts[1] if len(parts) > 1 else ""
            )[:MACRO_TEXT_MAX]
        return ""

    def save(self) -> str:
        """Save macros to file. Returns '' on success, error message otherwise."""
        header = (
            "# PK232PY Macros\n"
            f"# Format: NAME|TEXT  "
            f"(Name max. {MACRO_NAME_MAX}, Text max. {MACRO_TEXT_MAX} chars)\n"
            "# Line breaks in text are stored as \\n.\n"
            "# This file can be edited directly with a text editor.\n#\n"
        )
        try:
            with open(self.path, "w", encoding="utf-8") as fh:
                fh.write(header)
                for name, text in zip(self.names, self.texts):
                    fh.write(f"{self._escape(name)}|{self._escape(text)}\n")
        except OSError as exc:
            return f"Write error: {exc}"
        return ""

    @staticmethod
    def _escape(value: str) -> str:
        value = value.replace("\\", "\\\\")
        value = value.replace("\r", "\\r")
        value = value.replace("\n", "\\n")
        value = value.replace("|",  "/")
        return value

    @staticmethod
    def _unescape(value: str) -> str:
        value = value.replace("\\\\", "\x00")
        value = value.replace("\\r",  "\r")
        value = value.replace("\\n",  "\n")
        value = value.replace("\x00", "\\")
        return value


def apply_macro_tooltips(buttons: list, store: "MacroStore") -> None:
    """Mirror each macro button's hover tooltip onto its stored text.

    Called after the macro row is built and again whenever the edit
    dialog closes, so the tooltip never drifts from the real content.
    An empty macro gets a neutral hint instead of an invisible blank tooltip.
    """
    for i, btn in enumerate(buttons):
        text = store.texts[i] if i < len(store.texts) else ""
        btn.setToolTip(text.strip() or "(empty — define via Edit Macros)")


# ---------------------------------------------------------------------------
# MacroEditDialog
# ---------------------------------------------------------------------------

class MacroEditDialog(QDialog):
    """Modal dialog: edit, save and load 6 macros."""

    def __init__(self, store: MacroStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("Edit Macros")
        self.setMinimumWidth(620)
        self.setModal(True)
        self._build_ui()
        self._populate()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(12, 12, 12, 12)

        hdr = QLabel("Macro Editor")
        hdr.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        root.addWidget(hdr)
        add_hline(root)

        # Column headers
        hrow = QHBoxLayout()
        for text, width in (("Name", 110),
                            (f"Text  (max. {MACRO_TEXT_MAX} chars)", None)):
            lbl = QLabel(text)
            lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            if width:
                lbl.setFixedWidth(width)
            hrow.addWidget(lbl)
        root.addLayout(hrow)

        # Scroll area with 6 macro rows
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setSpacing(6)
        inner_layout.setContentsMargins(0, 0, 0, 0)

        self._name_edits: list[QLineEdit] = []
        self._text_edits: list[QTextEdit] = []
        mono = QFont("Courier New", 10)

        for i in range(MACRO_COUNT):
            row = QHBoxLayout()
            row.setSpacing(8)

            ne = QLineEdit()
            ne.setFont(mono)
            ne.setMaxLength(MACRO_NAME_MAX)
            ne.setFixedWidth(110)
            ne.setPlaceholderText(f"Macro {i+1}")
            row.addWidget(ne)
            self._name_edits.append(ne)

            te = MacroTextEdit()
            te.setFont(mono)
            te.setAcceptRichText(False)
            fm = te.fontMetrics()
            mc = te.contentsMargins()
            te.setFixedHeight(fm.lineSpacing() * 3 + mc.top() + mc.bottom() + 8)
            te.textChanged.connect(lambda edit=te: self._limit_text(edit))
            row.addWidget(te)
            self._text_edits.append(te)

            inner_layout.addLayout(row)

        inner_layout.addStretch()
        scroll.setWidget(inner)
        root.addWidget(scroll)
        add_hline(root)

        # Save / Load / Help / Close buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        for label, slot in (("Save", self._on_save), ("Load", self._on_load)):
            b = QPushButton(label)
            b.setFixedWidth(100)
            b.clicked.connect(slot)
            btn_row.addWidget(b)
        btn_row.addStretch()
        help_btn = QPushButton("Help")
        help_btn.setFixedWidth(80)
        help_btn.setStyleSheet(
            "QPushButton { border: 1px solid #445566; border-radius: 4px;"
            " padding: 4px; color: #88ccff; }"
        )
        help_btn.clicked.connect(self._on_help)
        btn_row.addWidget(help_btn)
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

    def _populate(self) -> None:
        for i in range(MACRO_COUNT):
            self._name_edits[i].setText(self.store.names[i])
            self._text_edits[i].blockSignals(True)
            self._set_formatted_text(self._text_edits[i], self.store.texts[i])
            self._text_edits[i].blockSignals(False)

    @staticmethod
    def _set_formatted_text(te: QTextEdit, text: str) -> None:
        """Set text with [^D] markers shown in orange inverse formatting."""
        from PyQt6.QtGui import QTextCharFormat, QColor, QTextCursor
        te.clear()
        if not text:
            return
        cursor = te.textCursor()
        f_normal = QTextCharFormat()
        f_eot = QTextCharFormat()
        f_eot.setForeground(QColor(get_theme()["bg_color"]))   # P77a: inverse of sys_color
        f_eot.setBackground(QColor(get_theme()["sys_color"]))
        f_eot.setFontWeight(700)
        f_tmr = QTextCharFormat()
        f_tmr.setForeground(QColor(get_theme()["bg_color"]))   # P77a: inverse of dim_color
        f_tmr.setBackground(QColor(get_theme()["dim_color"]))
        f_tmr.setFontWeight(700)
        i = 0
        while i < len(text):
            if text[i:i+4] == '[^D]':
                cursor.setCharFormat(f_eot)
                cursor.insertText('[^D]')   # 4 orange chars
                cursor.setCharFormat(f_normal)
                i += 4
            elif text[i:i+4] == '[^T:':
                # Read [^T:n] or [^T:10]
                j = i + 4
                while j < len(text) and text[j].isdigit():
                    j += 1
                if j < len(text) and text[j] == ']':
                    marker = text[i:j+1]
                    cursor.setCharFormat(f_tmr)
                    cursor.insertText(marker)   # purple chars
                    cursor.setCharFormat(f_normal)
                    i = j + 1
                else:
                    cursor.setCharFormat(f_normal)
                    cursor.insertText(text[i])
                    i += 1
            elif text[i] == '\n':
                cursor.setCharFormat(f_normal)
                cursor.insertBlock()
                i += 1
            else:
                cursor.setCharFormat(f_normal)
                cursor.insertText(text[i])
                i += 1
        te.setTextCursor(cursor)

    def _collect(self) -> None:
        for i in range(MACRO_COUNT):
            self.store.names[i] = self._name_edits[i].text()
            te = self._text_edits[i]
            if hasattr(te, 'get_macro_text'):
                self.store.texts[i] = te.get_macro_text()[:MACRO_TEXT_MAX]
            else:
                self.store.texts[i] = te.toPlainText()[:MACRO_TEXT_MAX]

    @staticmethod
    def _limit_text(te: QTextEdit) -> None:
        text = te.toPlainText()
        if len(text) > MACRO_TEXT_MAX:
            cur = te.textCursor()
            pos = cur.position()
            te.blockSignals(True)
            te.setPlainText(text[:MACRO_TEXT_MAX])
            cur.setPosition(min(pos, MACRO_TEXT_MAX))
            te.setTextCursor(cur)
            te.blockSignals(False)

    def _on_help(self) -> None:
        """Open help viewer at the Macros section."""
        try:
            from .help_viewer import show_help
            show_help("macros", parent=self)
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "Help",
                "Help file: help/help_baudot.md\n"
                "Section: Macros\n\n"
                f"(Help viewer not available: {e})"
            )

    def _on_save(self) -> None:
        self._collect()
        err = self.store.save()
        if err:
            QMessageBox.warning(self, "Save failed", err)
        else:
            QMessageBox.information(self, "Saved",
                                    f"Macros saved to '{self.store.path}'.")

    def _on_load(self) -> None:
        err = self.store.load()
        if err:
            QMessageBox.warning(self, "Load failed", err)
        else:
            self._populate()
            QMessageBox.information(self, "Loaded",
                                    f"Macros loaded from '{self.store.path}'.")