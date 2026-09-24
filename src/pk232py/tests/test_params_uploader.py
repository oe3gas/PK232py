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


class TestMaildropCapabilitySkip:
    """P37 Teil D - firmware without MailDrop (docs/DEVICES.md Device C)
    must never receive the MailDrop commands, since every one of them
    would come back '?What?'."""

    _MAILDROP_COMMAND_NAMES = (
        b"MAILDROP", b"MDMON", b"MMSG", b"TMAIL", b"3RDPARTY",
        b"KILONFWD", b"MTEXT",
    )

    def test_has_maildrop_false_skips_all_seven_commands(self):
        config = AppConfig()
        uploader = ParamsUploader(serial=None, config=config)
        commands = uploader._build_commands(has_pactor=True, has_maildrop=False)
        for name in self._MAILDROP_COMMAND_NAMES:
            assert not any(cmd.startswith(name + b" ") for cmd in commands), (
                f"{name!r} must not be sent when has_maildrop=False"
            )

    def test_has_maildrop_true_sends_all_seven_commands_by_default(self):
        config = AppConfig()
        uploader = ParamsUploader(serial=None, config=config)
        commands = uploader._build_commands(has_pactor=True, has_maildrop=True)
        for name in self._MAILDROP_COMMAND_NAMES:
            assert any(cmd.startswith(name + b" ") for cmd in commands), (
                f"{name!r} expected with the default MailDropConfig"
            )

    def test_has_maildrop_defaults_to_true(self):
        # A caller that never passes has_maildrop (e.g. old test code, or
        # a future call site that forgets it) must not silently lose the
        # MailDrop block.
        config = AppConfig()
        uploader = ParamsUploader(serial=None, config=config)
        commands = uploader._build_commands(has_pactor=True)
        assert any(cmd.startswith(b"MAILDROP ") for cmd in commands)
