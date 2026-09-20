# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Unit tests for pk232py.comm.params_uploader (USERS, P11.4).

Covers:
  - T103 (upload half) — USERS is included in the built command list, using
    the verbose-mode command name (not the Host Mode mnemonic UR).
"""

from __future__ import annotations

from pk232py.comm.params_uploader import ParamsUploader
from pk232py.config import AppConfig


class TestUsersUploaded:

    def test_users_command_present_with_configured_value(self):
        config = AppConfig()
        config.hf_packet.users = 4
        uploader = ParamsUploader(serial=None, config=config)
        commands = uploader._build_commands(has_pactor=True)
        assert b"USERS 4\r\n" in commands

    def test_users_default_is_one(self):
        config = AppConfig()
        uploader = ParamsUploader(serial=None, config=config)
        commands = uploader._build_commands(has_pactor=True)
        assert b"USERS 1\r\n" in commands
