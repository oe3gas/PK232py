# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Wiring round-trip audit for the six Parameter dialogs (P12).

This is the test that would have caught the USERS bug (self._sb_users
existed as a widget but neither read from nor written back to config
- see the "HF packet params dialog: USERS spinbox" commit). Rather than
review ~100 widgets by hand, this test mechanically proves every one of
them is actually connected in both directions.

Scope: the six dialogs under the &Parameters menu (HF Packet, PACTOR,
AMTOR/NAVTEX/TDM, BAUDOT/ASCII/CW, Misc, MailDrop). TncConfigDialog and
AppearanceDialog are separate &Configure dialogs, not part of this family,
and are out of scope.

The dialogs have TWO different APIs:
  - PacketParamsDialog / PACTORParamsDialog: own a config object passed
    into __init__, load it via _populate() and write it back via
    apply_to(config).
  - AMTORParamsDialog / BaudotParamsDialog / MiscParamsDialog /
    MailDropParamsDialog: take no config; MainWindow maps fields to/from
    their set_values(**kw) / get_values() -> dict. Neither dialog API is
    changed here - _DialogSpec below is the adapter the spec asked for,
    not a refactor of the dialogs.

Four tests, run once per dialog (A-C) or per config section (D):
  A. test_widget_writes_back_to_config - read direction. Every QSpinBox/
     QDoubleSpinBox/QCheckBox/QLineEdit/QComboBox found via findChildren()
     must change SOME config field when its value changes. This needs no
     name mapping at all, which is exactly why it catches an unwired
     widget that "looks" fine.
  B. test_config_field_reaches_dialog_and_back - write direction. Every
     field of the dialog's config dataclass must round-trip: change it,
     _load() it into a fresh dialog, _read() it back out, compare.
  C. test_ini_roundtrip - every field of every one of these six configs
     must survive ConfigManager.save()/load() through a real (temporary)
     INI file - a field can be correctly wired to the dialog but still
     get lost on restart if ConfigManager's _apply_*()/_build_*() forgot
     it (this is exactly the class of bug found for HFPacketConfig.aerpack/
     alfpack/txsmt - see the "Config: ..." fix commit alongside this one).
  D. test_field_reaches_upload (P13) - a field can pass A, B and C and
     still never reach the TNC: ParamsUploader._build_commands() reads
     ONLY the config dataclasses, never the dialog widgets, and it turns
     out to have its own, independent gaps (found for HFPacketConfig.
     resptime/txsmt/aerpack - see the "Params uploader: ..." fix commit).
     Same mechanism as Test A: bump one field, diff the built command
     list, no command-name mapping needed. AppConfig.tnc is excluded as a
     whole section (PC-side connection settings, not TNC parameters) -
     a section decision, not a name filter.

Needs a QApplication; forced to the offscreen platform (see
test_packet_screen.py for why this is done at module level, before any
PyQt6 import).
"""

from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass
from typing import Any, Callable

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import (
    QAbstractSpinBox, QApplication, QCheckBox, QComboBox, QDoubleSpinBox,
    QFormLayout, QLineEdit, QSpinBox,
)

from pk232py.comm.params_uploader import ParamsUploader
from pk232py.config import (
    AMTORConfig, AppConfig, BaudotConfig, ConfigManager, HFPacketConfig,
    MailDropConfig, MiscConfig, PACTORConfig,
)
from pk232py.ui.dialogs.params_amtor import AMTORParamsDialog
from pk232py.ui.dialogs.params_baudot import BaudotParamsDialog
from pk232py.ui.dialogs.params_hf import PacketParamsDialog
from pk232py.ui.dialogs.params_maildrop import MailDropParamsDialog
from pk232py.ui.dialogs.params_misc import MiscParamsDialog
from pk232py.ui.dialogs.params_pactor import PACTORParamsDialog

_app = QApplication.instance() or QApplication([])

WIDGET_TYPES = (QSpinBox, QDoubleSpinBox, QCheckBox, QLineEdit, QComboBox)


# ---------------------------------------------------------------------------
# Exceptions -- every entry needs a reason. An exception with no reason is a
# hidden wiring problem wearing a disguise; that is the whole point of this
# file, so do not add a pattern-based filter here, ever.
# ---------------------------------------------------------------------------

# Widgets that Test A finds but that deliberately do not write back to any
# config field. Keyed by (DialogClassName, attribute name as found via
# vars(dlg) -- see _widget_name()).
UNWIRED_OK: dict[tuple[str, str], str] = {
    # --- read-only TNC query results: never settable, so never in config ---
    ("PacketParamsDialog", "_sb_qhpacket"): "read-only, TNC query result",
    ("PacketParamsDialog", "_sb_qvpacket"): "read-only, TNC query result",
    ("PACTORParamsDialog", "_sb_qptor"): "read-only, TNC query result",
    ("AMTORParamsDialog", "_sb_qtdm"): "read-only, TNC query result",
    ("AMTORParamsDialog", "_sb_qtor"): "read-only, TNC query result",
    ("BaudotParamsDialog", "_sb_qmorse"): "read-only, TNC query result",
    ("BaudotParamsDialog", "_sb_qrtty"): "read-only, TNC query result",
    ("BaudotParamsDialog", "_sb_qwide"): "read-only, TNC query result",
    ("MiscParamsDialog", "_sb_bright"): "read-only, TNC query result",
    ("MiscParamsDialog", "_sb_bargraph"): "read-only, TNC query result",
    ("MiscParamsDialog", "_sb_threshold"): "read-only, TNC query result",

    # --- HF Packet: widgets with no HFPacketConfig field -- see Backlog.md ---
    # (8BITCONV, HID, MBELL and the CFROM/DFROM/MFROM/MTO filters were wired
    # in P13.3, MDIGI/MPROTO/MSTAMP/PASSALL/BBSMSGS in P73 C - no
    # longer exceptions here.)
    ("PacketParamsDialog", "_le_mbx"): "no config field yet — see Backlog",

    # --- PACTOR: no PACTORConfig field -- see Backlog.md ---
    ("PACTORParamsDialog", "_chk_8bitconv"): "no config field yet — see Backlog",
    ("PACTORParamsDialog", "_chk_afilter"): "no config field yet — see Backlog",
    ("PACTORParamsDialog", "_chk_xgateway"): "no config field yet — see Backlog",

    # --- AMTOR/NAVTEX/TDM: no AMTORConfig field -- see Backlog.md ---
    ("AMTORParamsDialog", "_le_aab"): "no config field yet — see Backlog",
    ("AMTORParamsDialog", "_sb_code"): "no config field yet — see Backlog",
    ("AMTORParamsDialog", "_hx_errchar"): "no config field yet — see Backlog",
    ("AMTORParamsDialog", "_sb_gusers"): "no config field yet — see Backlog",
    ("AMTORParamsDialog", "_sb_mid"): "no config field yet — see Backlog",
    ("AMTORParamsDialog", "_sb_mweight"): "no config field yet — see Backlog",
    ("AMTORParamsDialog", "_le_navmsg"): "no config field yet — see Backlog",
    ("AMTORParamsDialog", "_le_navstn"): "no config field yet — see Backlog",
    ("AMTORParamsDialog", "_chk_afilter"): "no config field yet — see Backlog",
    ("AMTORParamsDialog", "_chk_marsdisp"): "no config field yet — see Backlog",

    # --- BAUDOT/ASCII/CW: no BaudotConfig field -- see Backlog.md ---
    ("BaudotParamsDialog", "_sb_acrtty"): "no config field yet — see Backlog",
    ("BaudotParamsDialog", "_sb_atxrtty"): "no config field yet — see Backlog",
    ("BaudotParamsDialog", "_sb_audelay"): "no config field yet — see Backlog",
    ("BaudotParamsDialog", "_hx_errchar"): "no config field yet — see Backlog",
    ("BaudotParamsDialog", "_chk_afilter"): "no config field yet — see Backlog",
    ("BaudotParamsDialog", "_chk_cradd"): "no config field yet — see Backlog",
    ("BaudotParamsDialog", "_chk_marsdisp"): "no config field yet — see Backlog",
    ("BaudotParamsDialog", "_chk_rframe"): "no config field yet — see Backlog",
    ("BaudotParamsDialog", "_chk_wru"): "no config field yet — see Backlog",

    # --- Misc: no MiscConfig field -- see Backlog.md ---
    ("MiscParamsDialog", "_hx_bitinv"): "no config field yet — see Backlog",
    ("MiscParamsDialog", "_hx_cwid"): "no config field yet — see Backlog",
    ("MiscParamsDialog", "_hx_hereis"): "no config field yet — see Backlog",
    ("MiscParamsDialog", "_hx_receive"): "no config field yet — see Backlog",
    ("MiscParamsDialog", "_hx_redispla"): "no config field yet — see Backlog",
    ("MiscParamsDialog", "_hx_time"): "no config field yet — see Backlog",
    ("MiscParamsDialog", "_le_modem"): "no config field yet — see Backlog",

    # --- MailDrop: no MailDropConfig field -- see Backlog.md ---
    ("MailDropParamsDialog", "_sb_lastmsg"): "no config field yet — see Backlog",
    ("MailDropParamsDialog", "_le_mdprompt"): "no config field yet — see Backlog",
    ("MailDropParamsDialog", "_le_tmprompt"): "no config field yet — see Backlog",
}

# The reverse case: a config field that deliberately has no widget in THIS
# dialog. Keyed by (DialogClassName, field name).
FIELD_HAS_NO_WIDGET: dict[tuple[str, str], str] = {
    ("BaudotParamsDialog", "mid"): (
        "handled live on the Morse operating screen (MorseScreen.sb_mid via "
        "main_window._on_morse_mid_changed), not in this setup dialog"
    ),
}

# Config fields that deliberately never produce an upload command (P13,
# Test D). Keyed by (config section attribute on AppConfig, field name).
UPLOAD_EXEMPT: dict[tuple[str, str], str] = {
    # hf_packet.resptime and .acrpack (renamed from .aerpack) are now sent
    # (see the "Params uploader: RESPTIME, verified flag names, single
    # MYCALL" commit) and need no exemption.
    ("hf_packet", "txsmt"): (
        "TXSMT does not appear in the PK-232 TRM Host Mode command list - "
        "likely a command from a different AEA product. Field/INI kept for "
        "compatibility, dialog spinbox disabled, never uploaded."
    ),
    ("hf_packet", "vhf_maxframe"): (
        "P73 B: the init upload sends the HF band's value; the VHF value "
        "goes out with VHF Packet's activation frames (VHFPacketMode) and "
        "live through ParamApplier when VHF Packet is the active mode."
    ),
    ("hf_packet", "vhf_slottime"): (
        "P73 B: the init upload sends the HF band's value; the VHF value "
        "goes out with VHF Packet's activation frames (VHFPacketMode) and "
        "live through ParamApplier when VHF Packet is the active mode."
    ),
    ("hf_packet", "show_link_messages_in_ui_channel"): (
        "display setting, not a TNC parameter (P47) - controls whether "
        "link messages are mirrored into the UI channel on this PC, has "
        "no corresponding TNC command at all."
    ),
    ("hf_packet", "show_timestamps"): (
        "display setting, not a TNC parameter (P50) - controls whether "
        "the RX view prepends a timestamp; no corresponding TNC command."
    ),
    ("hf_packet", "rx_max_lines_per_channel"): (
        "display setting, not a TNC parameter (P50) - PC-side "
        "QTextDocument.setMaximumBlockCount() cap; no corresponding TNC "
        "command."
    ),
    # The four *_calls fields only affect the upload when their paired
    # *_mode field is YES/NO (_access_filter_cmds ignores calls entirely for
    # ALL/NONE, P13.3). Test D bumps exactly one field at a time, so bumping
    # a *_calls field alone while mode stays at its ALL/NONE default cannot
    # change the built command list - not a wiring gap, a structural
    # consequence of the two fields being coupled by design (confirmed by
    # the *_mode fields themselves passing Test D on their own).
    ("hf_packet", "cfrom_calls"): "only takes effect when cfrom_mode is YES/NO",
    ("hf_packet", "dfrom_calls"): "only takes effect when dfrom_mode is YES/NO",
    ("hf_packet", "mfrom_calls"): "only takes effect when mfrom_mode is YES/NO",
    ("hf_packet", "mto_calls"):   "only takes effect when mto_mode is YES/NO",

    # --- PACTOR: none of these are sent yet. Not fixed in this session --
    # verifying 9 more command names against the TRM / pk232_mnemonic_
    # table.txt is out of scope for P13 (which only closes the HF Packet
    # and access-filter/flag gaps); see Backlog.md "Upload coverage —
    # PACTOR/AMTOR/Baudot/Misc" for the follow-up. ---
    ("pactor", "arqtmo"): "not yet audited for upload — see Backlog",
    ("pactor", "adelay"): "not yet audited for upload — see Backlog",
    ("pactor", "ptdown"): "not yet audited for upload — see Backlog",
    ("pactor", "ptup"): "not yet audited for upload — see Backlog",
    ("pactor", "ptsum"): "not yet audited for upload — see Backlog",
    ("pactor", "pttries"): "not yet audited for upload — see Backlog",
    ("pactor", "ptsend"): "not yet audited for upload — see Backlog",
    ("pactor", "ptround"): "not yet audited for upload — see Backlog",
    ("pactor", "xmitok"): "not yet audited for upload — see Backlog",

    # --- AMTOR: same follow-up ---
    ("amtor", "xlength"): "not yet audited for upload — see Backlog",
    ("amtor", "srxall"): "not yet audited for upload — see Backlog",
    ("amtor", "usos"): "not yet audited for upload — see Backlog",
    ("amtor", "wideshft"): "not yet audited for upload — see Backlog",

    # --- Baudot/ASCII/CW: same follow-up, except mid (see its own reason) ---
    ("baudot", "mid"): (
        "sent live via main_window._on_morse_mid_changed while operating, "
        "not part of the startup upload — see FIELD_HAS_NO_WIDGET above "
        "for the same reasoning on the dialog side"
    ),
    ("baudot", "xlength"): "not yet audited for upload — see Backlog",
    ("baudot", "xbaud"): "not yet audited for upload — see Backlog",
    ("baudot", "usos"): "not yet audited for upload — see Backlog",
    ("baudot", "wideshft"): "not yet audited for upload — see Backlog",
    ("baudot", "xmitok"): "not yet audited for upload — see Backlog",

    # --- Misc: same follow-up ---
    ("misc", "mark"): "not yet audited for upload — see Backlog",
    ("misc", "space"): "not yet audited for upload — see Backlog",

    # --- MailDrop: local archive settings (P38) - PC-side bookkeeping,
    # never a TNC parameter, so they can never appear in an upload command
    # by design, not because of a follow-up. ---
    ("maildrop", "archive_enabled"): "local archive setting, not a TNC parameter",
    ("maildrop", "archive_path"): "local archive setting, not a TNC parameter",
    ("maildrop", "archive_sync"): "local archive setting, not a TNC parameter",
    ("maildrop", "archive_restore"): "local archive setting, not a TNC parameter",
    ("maildrop", "archive_restore_scope"): "local archive setting, not a TNC parameter",
}


# ---------------------------------------------------------------------------
# Per-dialog adapters -- _load()/_read() unify the two APIs without changing
# either of them (P12.1: "keine Änderung an den Dialog-APIs").
# ---------------------------------------------------------------------------

@dataclass
class _DialogSpec:
    dialog_cls: type
    config_cls: type
    make: Callable[[], Any]              # () -> dialog, defaults populated
    load: Callable[[Any, Any], None]     # (dialog, config) -> None
    read: Callable[[Any], Any]           # (dialog) -> fresh config instance


def _bound_spec(dialog_cls: type, config_cls: type) -> _DialogSpec:
    """PacketParamsDialog / PACTORParamsDialog: dialog owns a config
    object, loaded via _populate() and written back via apply_to()."""
    def make():
        return dialog_cls(config_cls())

    def load(dlg, cfg):
        dlg._config = cfg
        dlg._populate()

    def read(dlg):
        out = config_cls()
        dlg.apply_to(out)
        return out

    return _DialogSpec(dialog_cls, config_cls, make, load, read)


def _dict_spec(dialog_cls: type, config_cls: type) -> _DialogSpec:
    """AMTORParamsDialog / BaudotParamsDialog / MiscParamsDialog /
    MailDropParamsDialog: no config object; set_values(**kw) / get_values()
    are the only surface. MainWindow does this same filtering itself (see
    e.g. _on_params_amtor) when mapping to/from the real AppConfig."""
    field_names = {f.name for f in dataclasses.fields(config_cls)}

    def make():
        return dialog_cls()

    def load(dlg, cfg):
        dlg.set_values(**dataclasses.asdict(cfg))

    def read(dlg):
        values = dlg.get_values()
        return config_cls(**{k: v for k, v in values.items() if k in field_names})

    return _DialogSpec(dialog_cls, config_cls, make, load, read)


DIALOG_SPECS: list[_DialogSpec] = [
    _bound_spec(PacketParamsDialog, HFPacketConfig),
    _bound_spec(PACTORParamsDialog, PACTORConfig),
    _dict_spec(AMTORParamsDialog, AMTORConfig),
    _dict_spec(BaudotParamsDialog, BaudotConfig),
    _dict_spec(MiscParamsDialog, MiscConfig),
    _dict_spec(MailDropParamsDialog, MailDropConfig),
]


# ---------------------------------------------------------------------------
# Widget introspection helpers
# ---------------------------------------------------------------------------

def _widget_name(dlg, widget) -> str:
    """objectName() if set, else the attribute name resolved backwards
    through vars(dlg) (none of these widgets call setObjectName() today)."""
    name = widget.objectName()
    if name:
        return name
    for attr, value in vars(dlg).items():
        if value is widget:
            return attr
    return repr(widget)


def _form_label(dlg, widget) -> str:
    """The QFormLayout row label text for *widget*, if it is in one."""
    for layout in dlg.findChildren(QFormLayout):
        label = layout.labelForField(widget)
        if label is not None:
            return label.text()
    return ""


def _bump_widget(widget):
    """Change *widget*'s value in place.

    Returns True if the value actually changed, False if the widget's
    range is degenerate (only one valid value) and should be reported and
    skipped rather than failed, or None if the widget should be skipped
    silently (a read-only QLineEdit).
    """
    if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
        before = widget.value()
        step = widget.singleStep() or 1
        candidate = before + step
        if candidate > widget.maximum():
            candidate = before - step
        widget.setValue(candidate)   # Qt clamps to [minimum, maximum]
        return widget.value() != before
    if isinstance(widget, QCheckBox):
        widget.setChecked(not widget.isChecked())
        return True
    if isinstance(widget, QLineEdit):
        if widget.isReadOnly():
            return None
        widget.setText(widget.text() + "X")
        return True
    if isinstance(widget, QComboBox):
        if widget.count() < 2:
            return False
        widget.setCurrentIndex((widget.currentIndex() + 1) % widget.count())
        return True
    return None


def _restore_widget(widget, before) -> None:
    if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
        widget.setValue(before)
    elif isinstance(widget, QCheckBox):
        widget.setChecked(before)
    elif isinstance(widget, QLineEdit):
        widget.setText(before)
    elif isinstance(widget, QComboBox):
        widget.setCurrentIndex(before)


def _snapshot(widget):
    if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
        return widget.value()
    if isinstance(widget, QCheckBox):
        return widget.isChecked()
    if isinstance(widget, QLineEdit):
        return widget.text()
    if isinstance(widget, QComboBox):
        return widget.currentIndex()
    return None


# Fields whose legal values are a small fixed set (a QComboBox with a
# closed item list, not free text) -- bumping them the generic string way
# ("ALL" -> "ALLTEST") produces a value the combobox cannot represent, so
# setCurrentText() silently does nothing and the round-trip looks broken
# even though the wiring is fine. Rotate through the real choices instead.
_ENUM_FIELDS: dict[str, list[str]] = {
    "cfrom_mode": ["ALL", "NONE", "YES", "NO"],
    "dfrom_mode": ["ALL", "NONE", "YES", "NO"],
    "mfrom_mode": ["ALL", "NONE", "YES", "NO"],
    "mto_mode":   ["ALL", "NONE", "YES", "NO"],
    # P38 - local MailDrop archive settings, QComboBox with a closed item
    # list, same reasoning as the *_mode fields above.
    "archive_sync":          ["manual", "on_session_end"],
    "archive_restore":       ["never", "ask", "auto"],
    "archive_restore_scope": ["unread", "all", "none"],
}


def _bump_field_value(value, field_name: str | None = None):
    """Change a config field's value per its type (P12.1 Test B)."""
    if field_name in _ENUM_FIELDS:
        choices = _ENUM_FIELDS[field_name]
        idx = choices.index(value) if value in choices else -1
        return choices[(idx + 1) % len(choices)]
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, float):
        return round(value + 0.1, 2)
    if isinstance(value, str):
        # Already uppercase and free of surrounding whitespace, so it
        # survives a dialog's .upper()/.strip() normalisation unchanged -
        # the point is to test wiring, not string formatting.
        return ((value or "X") + "TEST").upper()
    raise TypeError(f"don't know how to bump a value of type {type(value)!r}")


# ---------------------------------------------------------------------------
# Test A — read direction: every widget must reach some config field
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("spec", DIALOG_SPECS, ids=lambda s: s.dialog_cls.__name__)
def test_widget_writes_back_to_config(spec: _DialogSpec):
    dlg = spec.make()
    widgets = dlg.findChildren(WIDGET_TYPES)
    assert widgets, f"{spec.dialog_cls.__name__}: findChildren() found nothing"

    degenerate: list[str] = []
    failures: list[str] = []
    exercised = 0

    for widget in widgets:
        # QSpinBox/QDoubleSpinBox build an internal QLineEdit
        # ("qt_spinbox_lineedit") to display their value -- a Qt
        # implementation detail findChildren() also picks up, not one of
        # the dialog's own ~100 parameter widgets. Not a UNWIRED_OK case:
        # it belongs to no dialog author's widget list at all.
        if isinstance(widget.parent(), QAbstractSpinBox):
            continue
        name = _widget_name(dlg, widget)
        label = _form_label(dlg, widget)
        before_value = _snapshot(widget)

        before_cfg = spec.read(dlg)
        changed = _bump_widget(widget)
        if changed is None:
            continue   # read-only QLineEdit: not a wiring question
        if changed is False:
            degenerate.append(f"{name} ({label!r})")
            continue
        after_cfg = spec.read(dlg)
        _restore_widget(widget, before_value)

        key = (spec.dialog_cls.__name__, name)
        if key in UNWIRED_OK:
            continue

        exercised += 1
        if after_cfg == before_cfg:
            failures.append(
                f'{name} (form label {label!r}) -- add '
                f'("{spec.dialog_cls.__name__}", "{name}") to UNWIRED_OK '
                f'if this is deliberate'
            )

    assert exercised > 0, (
        f"{spec.dialog_cls.__name__}: every widget is degenerate or in "
        f"UNWIRED_OK -- nothing was actually tested"
    )
    if degenerate:
        print(f"{spec.dialog_cls.__name__}: degenerate-range widgets "
              f"(single valid value, skipped): {degenerate}")
    assert not failures, (
        f"{spec.dialog_cls.__name__}: {len(failures)} widget(s) changed "
        f"value but no config field reflects it:\n  " + "\n  ".join(failures)
    )


# ---------------------------------------------------------------------------
# Test B — write direction: every config field must reach the dialog and back
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("spec", DIALOG_SPECS, ids=lambda s: s.dialog_cls.__name__)
def test_config_field_reaches_dialog_and_back(spec: _DialogSpec):
    failures: list[str] = []

    for f in dataclasses.fields(spec.config_cls):
        key = (spec.dialog_cls.__name__, f.name)
        if key in FIELD_HAS_NO_WIDGET:
            continue

        cfg = spec.config_cls()
        original = getattr(cfg, f.name)
        changed_value = _bump_field_value(original, f.name)
        setattr(cfg, f.name, changed_value)

        dlg = spec.make()
        spec.load(dlg, cfg)
        back = spec.read(dlg)
        got = getattr(back, f.name)

        if got == original and isinstance(changed_value, int) and not isinstance(changed_value, bool):
            # +1 may have clamped to the same value at a spinbox's upper
            # bound; retry with -1 before failing (P12.1: keeps the test
            # independent of range limits that may change later).
            changed_value = original - 1
            cfg2 = spec.config_cls()
            setattr(cfg2, f.name, changed_value)
            dlg2 = spec.make()
            spec.load(dlg2, cfg2)
            got = getattr(spec.read(dlg2), f.name)

        if got != changed_value:
            failures.append(
                f"{f.name!r}: set to {changed_value!r}, loaded into the "
                f"dialog, but read back as {got!r} (default was "
                f"{original!r}) -- add (\"{spec.dialog_cls.__name__}\", "
                f'"{f.name}") to FIELD_HAS_NO_WIDGET if this is deliberate'
            )

    assert not failures, (
        f"{spec.dialog_cls.__name__}: {len(failures)} config field(s) did "
        f"not round-trip through the dialog:\n  " + "\n  ".join(failures)
    )


# ---------------------------------------------------------------------------
# Test C — INI round trip: every field must survive save() + load()
# ---------------------------------------------------------------------------

_INI_SECTIONS: list[tuple[str, type]] = [
    ("hf_packet", HFPacketConfig),
    ("pactor", PACTORConfig),
    ("amtor", AMTORConfig),
    ("baudot", BaudotConfig),
    ("misc", MiscConfig),
    ("maildrop", MailDropConfig),
]


def test_ini_roundtrip(tmp_path):
    ini_path = tmp_path / "pk232_roundtrip_test.ini"
    mgr = ConfigManager(path=ini_path)

    for attr, config_cls in _INI_SECTIONS:
        cfg = getattr(mgr.app, attr)
        for f in dataclasses.fields(config_cls):
            setattr(cfg, f.name, _bump_field_value(getattr(cfg, f.name), f.name))

    mgr.save()

    reloaded = ConfigManager(path=ini_path)
    reloaded.load()

    failures: list[str] = []
    for attr, config_cls in _INI_SECTIONS:
        original = getattr(mgr.app, attr)
        got = getattr(reloaded.app, attr)
        for f in dataclasses.fields(config_cls):
            before, after = getattr(original, f.name), getattr(got, f.name)
            if before != after:
                failures.append(
                    f"{config_cls.__name__}.{f.name}: saved {before!r}, "
                    f"reloaded as {after!r} -- ConfigManager._apply_{attr}()/"
                    f"_build_{attr}() forgot this field"
                )

    assert not failures, (
        f"{len(failures)} field(s) did not survive an INI save()/load() "
        f"round trip:\n  " + "\n  ".join(failures)
    )


# ---------------------------------------------------------------------------
# Test D — upload direction: every config field must reach _build_commands()
# ---------------------------------------------------------------------------
#
# AppConfig.tnc is excluded as a WHOLE SECTION, not a per-field name filter:
# it holds PC-side connection settings (port, baud rate, echo, fast init,
# ...), not TNC operating parameters, so it has no business in the upload
# command list at all.

@pytest.mark.parametrize("attr,config_cls", _INI_SECTIONS, ids=[a for a, _ in _INI_SECTIONS])
def test_field_reaches_upload(attr, config_cls):
    failures: list[str] = []

    for f in dataclasses.fields(config_cls):
        key = (attr, f.name)
        if key in UPLOAD_EXEMPT:
            continue

        app = AppConfig()
        before = ParamsUploader(serial=None, config=app)._build_commands(has_pactor=True)

        cfg = getattr(app, attr)
        setattr(cfg, f.name, _bump_field_value(getattr(cfg, f.name), f.name))

        after = ParamsUploader(serial=None, config=app)._build_commands(has_pactor=True)

        if after == before:
            failures.append(
                f"{attr}.{f.name} -- changed but no command in "
                f"_build_commands() reflects it. Either send it, or add "
                f'("{attr}", "{f.name}") to UPLOAD_EXEMPT with a reason.'
            )

    assert not failures, (
        f"{config_cls.__name__} ({attr}): {len(failures)} field(s) never "
        f"reach the TNC:\n  " + "\n  ".join(failures)
    )
