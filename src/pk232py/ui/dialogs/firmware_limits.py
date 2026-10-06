# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""P85 C - grey out the settings a firmware does not support.

Disabled, never hidden (same idea as MailDropParamsDialog.set_locked): the
layout stays put and the value stays in the configuration. The names come from
comm/devices.py, the one table of what each firmware refuses.
"""

from __future__ import annotations

from pk232py.comm.devices import unknown_commands, unsupported_note


def apply_firmware_limits(release, widgets: dict) -> None:
    """Disable the widgets of every command *release* does not know.

    *widgets* maps a verbose command name (upper case) to its widget. An
    unknown or unmeasured release (None) changes nothing; a widget of a known
    command is also re-enabled and its tooltip cleared, so calling this again
    for another release leaves no stale state.
    """
    unknown = unknown_commands(release) or frozenset()
    for name, widget in widgets.items():
        blocked = name in unknown
        widget.setEnabled(not blocked)
        widget.setToolTip(unsupported_note(release) if blocked else "")
