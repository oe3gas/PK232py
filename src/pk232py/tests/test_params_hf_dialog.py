# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Unit tests for the HF Packet Parameters dialog's USERS field (P11.2).

Covers:
  - T103 (dialog half) — USERS round-trips through the dialog: config ->
    _populate() -> spinbox -> apply_to() -> config

Needs a QApplication; forced to the offscreen platform (see
test_packet_screen.py for why this is done at module level, before any
PyQt6 import).

Note: the P11 spec calls the dialog's load/save methods "set_values()" and
"get_values()" — this dialog's actual methods are "_populate()" (config ->
widgets) and "apply_to()" (widgets -> config); the test below uses the real
names.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from pk232py.config import HFPacketConfig
from pk232py.ui.dialogs.params_hf import PacketParamsDialog

_app = QApplication.instance() or QApplication([])


class TestUsersRoundTrip:

    def test_default_value_populates_and_applies(self):
        cfg = HFPacketConfig()
        assert cfg.users == 10   # P70 E2: operator decision 30.09.2026
        dlg = PacketParamsDialog(cfg)
        assert dlg._sb_users.value() == 10
        out = HFPacketConfig()
        dlg.apply_to(out)
        assert out.users == 10

    def test_changed_value_round_trips(self):
        cfg = HFPacketConfig(users=4)
        dlg = PacketParamsDialog(cfg)
        assert dlg._sb_users.value() == 4   # _populate() picked it up

        dlg._sb_users.setValue(7)
        out = HFPacketConfig()
        dlg.apply_to(out)
        assert out.users == 7

    def test_spinbox_range_is_1_to_10(self):
        cfg = HFPacketConfig()
        dlg = PacketParamsDialog(cfg)
        assert dlg._sb_users.minimum() == 1
        assert dlg._sb_users.maximum() == 10
