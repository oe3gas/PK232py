"""
screen_focus_controller.py — Focus controller for opmode screens with input fields

Screens that have QLineEdit input fields (PACTOR, AMTOR, HF/VHF Packet) need
to intercept keyboard focus so that typing in a callsign field does NOT get
redirected to the TX window by MainWindow.eventFilter.

Design
------
ScreenFocusController is a QObject that installs itself as an event filter
directly on each QLineEdit field of a screen.  When a field receives focus
(FocusIn), the controller sets _active = True.  When focus leaves all fields
(FocusOut), _active is reset to False.

MainWindow.eventFilter checks screen.focus_ctrl.is_active() before redirecting
keypresses to tx_input.  If active, the keypress is passed through untouched.

This approach is field-scoped (not app-wide, not screen-scoped):
  - installEventFilter on the QLineEdit itself → Qt calls eventFilter with
    obj = the QLineEdit, not an internal child widget.
  - FocusIn/FocusOut events are delivered to the QLineEdit directly → reliable.
  - No dependency on focusWidget() timing or parent-chain walking.

Usage in a screen __init__:
    from .screen_focus_controller import ScreenFocusController
    self.focus_ctrl = ScreenFocusController(
        fields=[self.le_myptcall, self.le_dest],
        parent=self,
    )

Usage in MainWindow.eventFilter (before TX redirect):
    screen = self._opmode_stack.currentWidget()
    ctrl = getattr(screen, 'focus_ctrl', None)
    if ctrl is not None and ctrl.is_active():
        return super().eventFilter(obj, event)

is_keyboard_input_widget() (P41, 2026-09-24)
---------------------------------------------
ScreenFocusController alone missed editable QComboBox fields (Dest) and
plain QComboBox/QAbstractSpinBox fields (Monitor, HBAUD, Morse's speed/
weight/MID spinboxes) that were never registered with it at all —
hardware-confirmed 24.09.2026: typing into the Packet screen's Dest
field landed in the TX window instead, because Qt delivers FocusIn (and
the eventFilter's own `obj`) to an editable QComboBox's OWN widget, not
to its inner lineEdit() — even though installEventFilter() was called on
that inner lineEdit(). is_keyboard_input_widget() is the generic,
registration-free fallback: given an event's `obj` or
QWidget.focusWidget(), it walks the parent chain checking against every
widget type that expects keyboard text input (QLineEdit, QTextEdit,
QPlainTextEdit, QComboBox, QAbstractSpinBox). Parent-chain walking
covers the ORIGINAL reason ScreenFocusController was field-scoped in the
first place (an internal Qt child, e.g. a QTextEdit's viewport, as
`obj`) — and covers the combo-box direction too, since the combo box
itself is now in the type list, not just QLineEdit.

MainWindow.eventFilter() checks BOTH `screen.focus_ctrl.is_active()` AND
`is_keyboard_input_widget(...)` — either exempts the keypress from TX
redirection. ScreenFocusController itself is left in place rather than
retired: removing an existing, working mechanism in favour of the new
one is a larger refactor than this bug fix calls for, and running both
is harmless (redundant coverage of the same QLineEdit fields, never
conflicting).
"""

from __future__ import annotations

import logging
from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtWidgets import (
    QAbstractSpinBox, QComboBox, QLineEdit, QPlainTextEdit, QTextEdit,
)

logger = logging.getLogger(__name__)

# Every widget type that expects keyboard TEXT input (P41) — not buttons
# or the channel bar's chips, which are deliberately Qt.FocusPolicy.
# NoFocus (CLAUDE.md SS5) and must keep redirecting to the TX window.
_INPUT_WIDGET_TYPES = (
    QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QAbstractSpinBox,
)


def is_keyboard_input_widget(widget) -> bool:
    """True if *widget* — or an ancestor found by walking widget.parent()
    — expects keyboard text input (P41).

    *widget* is typically an eventFilter's own `obj` or a
    QWidget.focusWidget() result, either of which may be an internal Qt
    child of a compound widget rather than the widget itself (the
    original reason ScreenFocusController installs directly on each
    field instead of relying on a type check alone) — walking the parent
    chain here covers that case exactly like the opmode screens' own
    per-screen keyboard-redirect filters already do (P41.2), so this one
    function is the shared place both use instead of five separate
    copies of the same tuple.
    """
    w = widget
    while w is not None:
        if isinstance(w, _INPUT_WIDGET_TYPES):
            return True
        w = w.parent()
    return False


class ScreenFocusController(QObject):
    """Event filter installed on QLineEdit fields of an opmode screen.

    Tracks whether any input field currently has keyboard focus.
    MainWindow.eventFilter consults is_active() to decide whether
    to redirect keypresses to the TX window.

    Parameters
    ----------
    fields : list[QLineEdit]
        The QLineEdit widgets to watch.  Read-only fields (setReadOnly(True))
        are included so that tab-navigation works, but they won't receive
        meaningful input anyway.
    parent : QObject, optional
        Parent widget (the screen itself).
    """

    def __init__(self, fields: list[QLineEdit], parent=None) -> None:
        super().__init__(parent)
        self._active = False
        self._fields: list[QLineEdit] = []
        for field in fields:
            if field is not None:
                self._fields.append(field)
                field.installEventFilter(self)
        logger.debug(
            "ScreenFocusController: watching %d field(s) on %s",
            len(self._fields),
            type(parent).__name__,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_active(self) -> bool:
        """Return True if any watched QLineEdit currently has focus."""
        return self._active

    def add_field(self, field: QLineEdit) -> None:
        """Add an additional field after construction."""
        if field is not None and field not in self._fields:
            self._fields.append(field)
            field.installEventFilter(self)

    # ------------------------------------------------------------------
    # EventFilter — installed on each QLineEdit directly
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event) -> bool:
        """Track FocusIn / FocusOut on watched QLineEdit fields.

        obj here is always the QLineEdit itself (not an internal child)
        because installEventFilter was called on the QLineEdit directly.
        """
        t = event.type()
        if t == QEvent.Type.FocusIn:
            if obj in self._fields:
                self._active = True
                logger.debug(
                    "ScreenFocusController: FocusIn on %s",
                    obj.objectName() or type(obj).__name__,
                )
        elif t == QEvent.Type.FocusOut:
            if obj in self._fields:
                # Check if focus moved to another watched field.
                # If so, keep _active = True to avoid a brief False gap
                # that would allow one keypress to slip through to tx_input.
                from PyQt6.QtWidgets import QApplication
                new_focus = QApplication.focusWidget()
                if new_focus not in self._fields:
                    self._active = False
                    logger.debug("ScreenFocusController: all fields lost focus")
        return super().eventFilter(obj, event)