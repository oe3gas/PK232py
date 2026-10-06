# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""P87 - the parameter masks list their fields alphabetically.

The order a mask SHOWS is read from the real widget geometry after show() and
processEvents() (CLAUDE.md rule 14), column by column, top to bottom, and compared
with the sorted list: digits before letters, case ignored ('8BITCONV' before
'ACRPACK', 'UBIT 0' under U). Blocks that belong together by meaning keep their own
order and are named in EXCEPTIONS below - each one is tested separately.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QGroupBox, QLabel, QTabWidget, QWidget,
)

from pk232py.config import AppConfig, PACTORConfig
from pk232py.ui.dialogs.param_order import sort_key, split_columns, sorted_labels
from pk232py.ui.dialogs.params_amtor import AMTORParamsDialog
from pk232py.ui.dialogs.params_baudot import BaudotParamsDialog
from pk232py.ui.dialogs.params_hf import PacketParamsDialog
from pk232py.ui.dialogs.params_maildrop import MailDropParamsDialog
from pk232py.ui.dialogs.params_misc import MiscParamsDialog
from pk232py.ui.dialogs.params_pactor import PACTORParamsDialog

_app = QApplication.instance() or QApplication([])

_COLUMN_GAP = 40        # px: two columns of one group start further apart than this


def _container(widget: QWidget, dialog: QDialog) -> str:
    """The title of the group box (or the tab) a control sits in."""
    w = widget.parentWidget()
    while w is not None and w is not dialog:
        if isinstance(w, QGroupBox):
            return w.title()
        w = w.parentWidget()
    return ""


def displayed(dialog: QDialog) -> dict:
    """{(tab, group): [column, ...]} - the label of every switch (its text) and every
    labelled field (the form label), each column top to bottom. Measured on the
    shown dialog, one tab after the other."""
    dialog.show()
    _app.processEvents()
    tabs = dialog.findChildren(QTabWidget)
    pages = [(tabs[0].tabText(i), i) for i in range(tabs[0].count())] if tabs else [("", None)]
    result: dict = {}
    for tab_name, index in pages:
        if index is not None:
            tabs[0].setCurrentIndex(index)
            _app.processEvents()
        found: dict = {}
        for w in dialog.findChildren(QWidget):
            if not w.isVisible():
                continue
            if isinstance(w, QCheckBox):
                label, is_form_label = w.text(), False
            elif isinstance(w, QLabel) and w.buddy() is not None:
                label, is_form_label = w.text(), True
            else:
                continue
            pos = w.mapTo(dialog, QPoint(0, 0))
            found.setdefault(_container(w, dialog), []).append(
                (pos.x(), pos.y(), label, is_form_label))
        for group, entries in found.items():
            # A group with a form (right-aligned labels of different widths) is one
            # column; a group of switches only is split by the x of the switches.
            one_column = any(e[3] for e in entries)
            columns: list = []
            for x, y, label, _form in sorted(entries):
                if columns and (one_column or x - columns[-1][0] <= _COLUMN_GAP):
                    columns[-1][1].append((y, label))
                else:
                    columns.append([x, [(y, label)]])
            result[(tab_name, group)] = [[lab for _y, lab in sorted(col[1])] for col in columns]
    dialog.close()
    return result


def _strip(labels):
    return [lab.rstrip(":") for lab in labels]


def _is_sorted(labels) -> bool:
    return list(labels) == sorted(labels, key=sort_key)


class TestSortRule:

    def test_digits_before_letters_and_ubit_under_u(self):
        assert sorted_labels(["ACRPACK", "8BITCONV", "UBIT 0 (DCD gate)", "TXDELAY", "USERS"]) == [
            "8BITCONV", "ACRPACK", "TXDELAY", "UBIT 0 (DCD gate)", "USERS"]

    def test_case_and_colon_are_ignored(self):
        assert sorted_labels(["b:", "A", "c"]) == ["A", "b:", "c"]

    def test_columns_are_filled_top_to_bottom(self):
        assert split_columns(list("ABCDEFGHIJKLMNOPQRS"), 2) == [list("ABCDEFGHIJ"), list("KLMNOPQRS")]
        assert split_columns(list("ABCDEF"), 2) == [list("ABC"), list("DEF")]


# ------------------------------------------------------------------ Packet

class TestPacketMask:

    @pytest.fixture
    def shown(self):
        return displayed(PacketParamsDialog(AppConfig().hf_packet))

    def test_link_column(self, shown):
        (col,) = shown[("Parameters", "Link")]
        assert _strip(col) == ["CHECK", "DWAIT", "FRACK", "MONITOR", "PACLEN", "PERSIST",
                               "RESPTIME", "RETRY", "TXDELAY", "USERS"]
        assert _is_sorted(col)

    def test_status_values_under_the_band_table(self, shown):
        (col,) = shown[("Parameters", "Band && Status")]
        assert _strip(col) == ["QHPACKET (r/o)", "QVPACKET (r/o)", "TXSMT"]
        assert _is_sorted(col)

    def test_flags_two_columns_top_to_bottom(self, shown):
        first, second = shown[("Parameters", "Flags")]
        assert first == ["8BITCONV", "ACRPACK", "ALFPACK", "AX25L2V2", "BBSMSGS", "CONSTAMP",
                         "DAGSTAMP", "HEADERLN", "HID", "ILFPACK"]
        assert second == ["MBELL", "MDIGI", "MPROTO", "MRPT", "MSTAMP", "PASSALL", "PPERSIST",
                          "UBIT 0 (DCD gate)", "XMITOK"]
        assert _is_sorted(first + second)

    def test_message_tab_plain_fields_then_the_access_filter_block(self, shown):
        (col,) = shown[("Message Params", "")]
        plain, filters = _strip(col)[:5], _strip(col)[5:]
        assert plain == ["BTEXT", "CTEXT", "MBX", "MYCALL", "UNPROTO"] and _is_sorted(plain)
        assert filters == ["CFROM", "DFROM", "MFROM", "MTO"] and _is_sorted(filters)

    def test_display_tab(self, shown):
        (col,) = shown[("Display", "")]
        assert col == ["Max. RX lines per channel:", "Show timestamps in the RX view",
                       "Show TNC link messages in the MON view"]
        assert _is_sorted(col)

    def test_hf_vhf_table_keeps_its_block_order(self):
        """EXCEPTION: the HF | VHF table is one block (alphabetical anyway)."""
        dlg = PacketParamsDialog(AppConfig().hf_packet)
        dlg.show()
        _app.processEvents()
        rows = sorted(
            (w.mapTo(dlg, QPoint(0, 0)).y(), w.text()) for w in dlg.findChildren(QLabel)
            if w.isVisible() and w.text() in ("HBAUD:", "MAXFRAME:", "SLOTTIME:"))
        dlg.close()
        assert [t for _y, t in rows] == ["HBAUD:", "MAXFRAME:", "SLOTTIME:"]


# ------------------------------------------------------------------- AMTOR

class TestAmtorMask:

    @pytest.fixture
    def shown(self):
        return displayed(AMTORParamsDialog())

    def test_parameters_then_the_read_only_block(self, shown):
        (col,) = shown[("", "Parameters")]
        col = _strip(col)
        inputs, read_only = col[:-2], col[-2:]
        assert inputs == ["AAB", "ADELAY", "ARQTMO", "ARQTOL", "CODE", "ERRCHAR", "GUSERS", "MID",
                          "MWEIGHT", "MYALTCAL", "MYIDENT", "MYSELCAL", "NAVMSG", "NAVSTN",
                          "TDBAUD", "TDCHAN", "XLENGTH"]
        assert _is_sorted(inputs)
        assert read_only == ["QTDM (r/o)", "QTOR (r/o)"]

    def test_flags(self, shown):
        (col,) = shown[("", "Flags")]
        assert col == ["AFILTER", "MARSDISP", "RFEC", "RXREV", "SRXALL", "TXREV", "USOS",
                       "WIDESHFT", "XMITOK"]
        assert _is_sorted(col)


# ------------------------------------------------------------------ Baudot

class TestBaudotMask:

    @pytest.fixture
    def shown(self):
        return displayed(BaudotParamsDialog())

    def test_parameters_then_the_read_only_block(self, shown):
        (col,) = shown[("", "Parameters")]
        col = _strip(col)
        inputs, read_only = col[:-3], col[-3:]
        assert inputs == ["AAB", "ACRTTY", "ATXRTTY", "AUDELAY", "CODE", "ERRCHAR", "MSPEED",
                          "MWEIGHT", "XBAUD", "XLENGTH"]
        assert _is_sorted(inputs)
        assert read_only == ["QMORSE (r/o)", "QRTTY (r/o)", "QWIDE (r/o)"]

    def test_flags(self, shown):
        (col,) = shown[("", "Flags")]
        assert col == ["AFILTER", "ALFRTTY", "CRADD", "DIDDLE", "MARSDISP", "MOPT", "RFRAME",
                       "RXREV", "TXREV", "USOS", "WIDESHFT", "WRU", "XMITOK"]
        assert _is_sorted(col)


# ------------------------------------------------------------------ PACTOR

class TestPactorMask:

    @pytest.fixture
    def shown(self):
        return displayed(PACTORParamsDialog(PACTORConfig()))

    def test_parameters_then_the_read_only_block(self, shown):
        (col,) = shown[("", "Parameters")]
        col = _strip(col)
        inputs, read_only = col[:-1], col[-1:]
        assert inputs == ["ADELAY", "ARQTMO", "MYPTCALL", "PTDOWN", "PTHUFF", "PTOVER", "PTSEND",
                          "PTSUM", "PTTRIES", "PTUP"]
        assert _is_sorted(inputs)
        assert read_only == ["QPTOR (r/o)"]

    def test_flags(self, shown):
        (col,) = shown[("", "Flags")]
        assert col == ["8BITCONV", "AFILTER", "PT200", "PTROUND", "XGATEWAY", "XMITOK"]
        assert _is_sorted(col)


# -------------------------------------------------------------------- Misc

class TestMiscMask:

    @pytest.fixture
    def shown(self):
        return displayed(MiscParamsDialog())

    def test_control_characters(self, shown):
        (col,) = shown[("", "Control Characters")]
        assert _strip(col) == ["BITINV", "CANLINE", "CANPAC", "COMMAND", "CWID", "HEREIS",
                               "RECEIVE", "REDISPLA", "SENDPAC", "TIME"]
        assert _is_sorted(col)

    def test_tone_frequencies(self, shown):
        (col,) = shown[("", "Tone Frequencies")]
        assert _strip(col) == ["MARK", "SPACE"] and _is_sorted(col)

    def test_hardware_read_only_group(self, shown):
        (col,) = shown[("", "Hardware (read-only)")]
        assert _strip(col) == ["BARGRAPH", "BRIGHT", "THRESHOLD"] and _is_sorted(col)

    def test_modem(self, shown):
        (col,) = shown[("", "Modem")]
        assert _strip(col) == ["MODEM"]


# ---------------------------------------------------------------- MailDrop

class TestMailDropMask:

    @pytest.fixture
    def shown(self):
        return displayed(MailDropParamsDialog())

    def test_parameters(self, shown):
        (col,) = shown[("", "Parameters")]
        assert _strip(col) == ["HOMEBBS", "LASTMSG", "MDPROMPT", "MYMAIL", "TMPROMPT"]
        assert _is_sorted(col)

    def test_flags_two_columns(self, shown):
        first, second = shown[("", "Flags")]
        assert first == ["3RDPARTY", "KILONFWD", "MAILDROP"]
        assert second == ["MDMON", "MMSG", "TMAIL"]
        assert _is_sorted(first + second)

    def test_local_archive_block_keeps_its_own_order(self):
        """EXCEPTION: the PC-side archive is one block ordered by meaning
        (switch, path, sync, restore, scope)."""
        dlg = MailDropParamsDialog()
        dlg.show()
        _app.processEvents()
        widgets = [dlg._chk_archive_enabled, dlg._le_archive_path, dlg._cb_archive_sync,
                   dlg._cb_archive_restore, dlg._cb_archive_restore_scope]
        ys = [w.mapTo(dlg, QPoint(0, 0)).y() for w in widgets]
        dlg.close()
        assert ys == sorted(ys) and len(set(ys)) == 5
