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

    def test_users_default_is_ten(self):
        # P70 E2 (operator decision 30.09.2026): a fresh config uploads USERS 10.
        config = AppConfig()
        uploader = ParamsUploader(serial=None, config=config)
        commands = uploader._build_commands(has_pactor=True)
        assert b"USERS 10\r\n" in commands

    def test_saved_users_one_is_kept(self, tmp_path):
        # P70 E2: no migration - a stored users = 1 may be a deliberate choice.
        from pk232py.config import ConfigManager
        ini = tmp_path / "pk232py.ini"
        ini.write_text("[HF_Packet]\nusers = 1\n", encoding="utf-8")
        mgr = ConfigManager(ini)
        mgr.load()
        assert mgr.app.hf_packet.users == 1


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


class _HostModeStubSerial:
    """Minimal stand-in for a SerialManager that is in Host Mode. Any
    attempt to actually write raises - the whole point of P40.2 is that
    upload() must never get that far."""

    is_host_mode = True
    has_pactor = True

    def write_verbose_wait(self, *args, **kwargs):
        raise AssertionError(
            "write_verbose_wait() must not be called while in Host Mode"
        )

    def detect_maildrop(self):
        raise AssertionError(
            "detect_maildrop() must not be called while in Host Mode"
        )


class TestRefusesUploadInHostMode:
    """P40.2 - there is no cmd: prompt in Host Mode at all, so verbose
    text sent there is never executed (see CLAUDE.md's Host-Mode-has-no-
    cmd:-prompt gotcha, and the 24.09.2026 hardware finding: 68 commands,
    5 s timeout each, none actually reached the TNC). upload() must
    refuse outright rather than silently time out 68 times."""

    def test_upload_sends_nothing_while_in_host_mode(self):
        config = AppConfig()
        uploader = ParamsUploader(serial=_HostModeStubSerial(), config=config)
        sent = uploader.upload()
        assert sent == 0

    def test_upload_logs_an_error_while_in_host_mode(self, caplog):
        import logging
        config = AppConfig()
        uploader = ParamsUploader(serial=_HostModeStubSerial(), config=config)
        with caplog.at_level(logging.ERROR, logger="pk232py.comm.params_uploader"):
            uploader.upload()
        assert any("Host Mode" in r.message for r in caplog.records)

    def test_upload_proceeds_normally_when_not_in_host_mode(self):
        class _VerboseStubSerial(_HostModeStubSerial):
            is_host_mode = False
            verbose_confirmed = True

            def write_verbose_wait(self, *args, **kwargs):
                return True

            def detect_maildrop(self):
                return True

        config = AppConfig()
        uploader = ParamsUploader(serial=_VerboseStubSerial(), config=config)
        sent = uploader.upload()
        assert sent > 0


class TestRequiresConfirmedVerbosePrompt:
    """P43.2 - is_host_mode=False alone is not enough: is_host_mode is
    the software's own belief, and a fresh connection cycle starts it
    False regardless of what the physical TNC is actually doing (a TNC
    left in Host Mode from a previous session is not noticed by
    is_host_mode at all - see P43's finding). upload() also requires
    verbose_confirmed, set only by SerialManager's active P43.1
    detection chain once it has positive evidence of a verbose prompt."""

    class _NotConfirmedStubSerial:
        is_host_mode = False
        has_pactor = True
        verbose_confirmed = False

        def write_verbose_wait(self, *args, **kwargs):
            raise AssertionError(
                "write_verbose_wait() must not be called without a "
                "confirmed prompt"
            )

        def detect_maildrop(self):
            raise AssertionError(
                "detect_maildrop() must not be called without a "
                "confirmed prompt"
            )

    def test_upload_refused_without_verbose_confirmed(self):
        config = AppConfig()
        uploader = ParamsUploader(
            serial=self._NotConfirmedStubSerial(), config=config
        )
        sent = uploader.upload()
        assert sent == 0

    def test_upload_logs_an_error_naming_the_reason(self, caplog):
        import logging
        config = AppConfig()
        uploader = ParamsUploader(
            serial=self._NotConfirmedStubSerial(), config=config
        )
        with caplog.at_level(logging.ERROR, logger="pk232py.comm.params_uploader"):
            uploader.upload()
        assert any("verbose prompt" in r.message for r in caplog.records)

    def test_missing_attribute_defaults_to_confirmed(self):
        # A duck-typed test double that predates P43 and never defines
        # verbose_confirmed at all must not be penalised for it - only a
        # real SerialManager, which always has the attribute, enforces
        # this gate in practice.
        class _LegacyStubSerial(_HostModeStubSerial):
            is_host_mode = False

            def write_verbose_wait(self, *args, **kwargs):
                return True

            def detect_maildrop(self):
                return True

        config = AppConfig()
        uploader = ParamsUploader(serial=_LegacyStubSerial(), config=config)
        sent = uploader.upload()
        assert sent > 0


class TestVerify:
    """P40.3 - spot-checks MYCALL/PACLEN/MAXFRAME against AppConfig,
    still in verbose mode."""

    class _QueryStubSerial:
        def __init__(self, answers: dict[str, str | None]):
            self._answers = answers

        def query_verbose_value(self, name: str, timeout: float = 3.0):
            return self._answers.get(name)

    def test_all_three_match_reports_verified(self):
        config = AppConfig()
        config.hf_packet.mycall = "OE3GAS"
        config.hf_packet.paclen = 128
        config.hf_packet.maxframe = 4
        serial = self._QueryStubSerial({
            "MYCALL": "OE3GAS", "PACLEN": "128", "MAXFRAME": "4",
        })
        uploader = ParamsUploader(serial=serial, config=config)
        matched, applicable = uploader.verify()
        assert (matched, applicable) == (3, 3)

    def test_one_mismatch_is_reported_and_not_counted(self, caplog):
        import logging
        config = AppConfig()
        config.hf_packet.mycall = "OE3GAS"
        config.hf_packet.paclen = 128
        config.hf_packet.maxframe = 4
        serial = self._QueryStubSerial({
            "MYCALL": "OE3GAS", "PACLEN": "64", "MAXFRAME": "4",
        })
        uploader = ParamsUploader(serial=serial, config=config)
        with caplog.at_level(logging.WARNING, logger="pk232py.comm.params_uploader"):
            matched, applicable = uploader.verify()
        assert (matched, applicable) == (2, 3)
        assert any("PACLEN" in r.message and "mismatch" in r.message
                   for r in caplog.records)

    def test_no_answer_is_reported_and_not_counted(self, caplog):
        import logging
        config = AppConfig()
        config.hf_packet.mycall = "OE3GAS"
        config.hf_packet.paclen = 128
        config.hf_packet.maxframe = 4
        serial = self._QueryStubSerial({"MYCALL": "OE3GAS", "PACLEN": "128"})
        uploader = ParamsUploader(serial=serial, config=config)
        with caplog.at_level(logging.WARNING, logger="pk232py.comm.params_uploader"):
            matched, applicable = uploader.verify()
        assert (matched, applicable) == (2, 3)
        assert any("MAXFRAME" in r.message and "no answer" in r.message
                   for r in caplog.records)

    def test_mycall_nocall_placeholder_is_skipped_not_a_mismatch(self):
        config = AppConfig()
        config.hf_packet.mycall = "NOCALL"
        config.hf_packet.paclen = 128
        config.hf_packet.maxframe = 4
        serial = self._QueryStubSerial({"PACLEN": "128", "MAXFRAME": "4"})
        uploader = ParamsUploader(serial=serial, config=config)
        matched, applicable = uploader.verify()
        assert (matched, applicable) == (2, 2)

    def test_serial_without_query_support_returns_zero(self):
        config = AppConfig()
        uploader = ParamsUploader(serial=object(), config=config)
        assert uploader.verify() == (0, 0)


class _CountingSilentAfterStubSerial:
    """Answers True (cmd: seen) for the first *ok_count* writes, then
    False (silence) for every one after that - P40.4's abort test."""

    is_host_mode = False
    has_pactor = True

    def __init__(self, ok_count: int):
        self._ok_count = ok_count
        self.calls = 0

    def write_verbose_wait(self, *args, **kwargs):
        self.calls += 1
        return self.calls <= self._ok_count

    def detect_maildrop(self):
        return True


class TestAbortsAfterRepeatedSilence:
    """P40.4 - more than _MAX_CONSECUTIVE_SILENT commands in a row with
    no "cmd:" response abort the whole upload instead of waiting out the
    5 s timeout for every remaining command (24.09.2026: 68 x 5 s = ~6
    minutes, all silent)."""

    def test_aborts_after_max_consecutive_silent(self, caplog):
        import logging
        config = AppConfig()
        serial = _CountingSilentAfterStubSerial(ok_count=5)
        uploader = ParamsUploader(serial=serial, config=config)
        total_commands = len(uploader._build_commands())
        assert total_commands > 5 + ParamsUploader._MAX_CONSECUTIVE_SILENT + 1, (
            "test needs a command list long enough to actually trigger the abort"
        )

        with caplog.at_level(logging.ERROR, logger="pk232py.comm.params_uploader"):
            sent = uploader.upload()

        expected_sent = 5 + ParamsUploader._MAX_CONSECUTIVE_SILENT + 1
        assert sent == expected_sent
        assert serial.calls == expected_sent
        assert any("aborting upload" in r.message for r in caplog.records)

    def test_isolated_silent_commands_do_not_abort(self):
        # An occasional single miss must not trip the abort - only
        # CONSECUTIVE silence counts. Every 2nd command is silent, which
        # never reaches _MAX_CONSECUTIVE_SILENT+1 in a row.
        class _EveryOtherSilentSerial(_CountingSilentAfterStubSerial):
            def __init__(self):
                super().__init__(ok_count=0)

            def write_verbose_wait(self, *args, **kwargs):
                self.calls += 1
                return self.calls % 2 == 0

        config = AppConfig()
        serial = _EveryOtherSilentSerial()
        uploader = ParamsUploader(serial=serial, config=config)
        total_commands = len(uploader._build_commands())

        sent = uploader.upload()

        assert sent == total_commands
        assert serial.calls == total_commands


class TestChangedValues:
    """P72 Teil B: only the commands that differ between two snapshots."""

    @staticmethod
    def _diff(mutate, **kw):
        import copy
        before = AppConfig()
        after = copy.deepcopy(before)
        mutate(after)
        return ParamsUploader.changed_values(before, after, **kw)

    def test_users_1_to_10_is_exactly_one_pair(self):
        import copy
        before = AppConfig()
        before.hf_packet.users = 1
        after = copy.deepcopy(before)
        after.hf_packet.users = 10
        assert ParamsUploader.changed_values(before, after) == [("USERS", "10")]

    def test_nothing_changed_is_empty(self):
        assert self._diff(lambda c: None) == []

    def test_switch_and_ubit_values(self):
        assert self._diff(lambda c: setattr(c.hf_packet, "ax25l2v2", False)) == \
            [("AX25L2V2", "OFF")]
        assert self._diff(lambda c: setattr(c.hf_packet, "ubit0", True)) == \
            [("UBIT", "0 ON")]

    def test_clock_is_not_a_parameter(self):
        # DAYTIME is "now" - two snapshots always differ by it; never a change.
        def on(c):
            c.tnc.utc_tnc_time = True
        import copy
        before = AppConfig()
        before.tnc.utc_tnc_time = True
        after = copy.deepcopy(before)
        assert ParamsUploader.changed_values(before, after) == []

    def test_same_source_as_the_init_upload(self):
        # A newly set text parameter appears with the value _build_commands() sends.
        pairs = self._diff(lambda c: setattr(c.hf_packet, "unproto", "APRS"))
        assert pairs == [("UNPROTO", "APRS")]

    def test_with_old_values(self):
        import copy
        before = AppConfig()
        before.hf_packet.maxframe = 4
        after = copy.deepcopy(before)
        after.hf_packet.maxframe = 7
        assert ParamsUploader.changed_with_old(before, after) == [("MAXFRAME", "7", "4")]
