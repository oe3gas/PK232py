# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""The ONE place that orders the fields of the parameter dialogs (alphabetical).

Every field and switch of a group (or column) is listed here by its label and
placed by sorted(): digits before letters, case ignored, a trailing colon and
the "(r/o)" tail do not matter ("8BITCONV" before "ACRPACK", "UBIT 0 (DCD gate)"
under U). Nothing is placed by hand; a mask that has a block which belongs
together by meaning (the HF/VHF table of the Packet mask, the read-only values,
the access filters, the local archive) keeps that block in its own order and
says so where it builds it.

Lernmodus: the widgets keep their attribute names (rule 10 / the P12 round-trip
audit); only the ORDER in which they are added to a layout comes from here.
"""

from __future__ import annotations

from typing import Iterable

from PyQt6.QtWidgets import QCheckBox, QFormLayout, QLayout, QVBoxLayout, QWidget


def sort_key(label: str) -> str:
    """Digits sort before letters (ASCII), the case and a trailing colon are
    ignored: '8BITCONV' < 'ACRPACK', 'UBIT 0 (DCD gate)' stays under U."""
    return label.strip().rstrip(":").strip().upper()


def sorted_labels(labels: Iterable[str]) -> list:
    return sorted(labels, key=sort_key)


def _row_label(row: tuple) -> str:
    label, widget = row
    return label if label is not None else widget.text()


def add_form_rows(form: QFormLayout, rows: Iterable[tuple]) -> list:
    """Add (label, widget) rows to *form*, sorted by label; returns the labels in
    the order they were added. (None, QCheckBox) is a switch that carries its own
    text: it is sorted by that text and added without a separate label."""
    ordered = sorted(rows, key=lambda r: sort_key(_row_label(r)))
    for label, widget in ordered:
        if label is None:
            form.addRow(widget)
        else:
            form.addRow(label, widget)
    return [_row_label(r) for r in ordered]


def sorted_flags(boxes: Iterable[QCheckBox]) -> list:
    return sorted(boxes, key=lambda c: sort_key(c.text()))


def add_flags(layout: QLayout, boxes: Iterable[QCheckBox]) -> list:
    """Add the switches to a box layout, sorted by their text, top to bottom."""
    ordered = sorted_flags(boxes)
    for box in ordered:
        layout.addWidget(box)
    return ordered


def split_columns(items: list, columns: int) -> list:
    """The sorted *items* in *columns* columns, filled column by column from top to
    bottom (the first columns get the extra item): 19 items, 2 columns -> 10 + 9."""
    per_col = -(-len(items) // columns)
    return [items[i:i + per_col] for i in range(0, len(items), per_col)]
