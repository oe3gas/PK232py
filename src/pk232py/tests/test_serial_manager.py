# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Unit tests for pk232py.comm.serial_manager (P35.4).

Only _wakeup_log_message() — the pure decision behind the wakeup log
line — is covered here; the rest of _init_tnc_thread() needs a real (or
fully mocked) serial.Serial and background thread, out of scope for a
unit test.
"""

from __future__ import annotations

import logging

from pk232py.comm.serial_manager import (
    _classify_maildrop_response,
    _parse_defaults_flag,
    _parse_release,
    _parse_verbose_query_value,
    _wakeup_log_message,
)

# Real fixture, hw_logs/20260924_181446_maildrop_session.log (Device B,
# MBX, 01.08.1991) -- the exact 176-byte wakeup response, banner included.
_DEVICE_B_BANNER = bytes.fromhex(
    "00 00 00 00 00 0d 0a 0d 0a 0d 0a 50 4b 2d 32 33 32 4d 20 69 73 20 75 "
    "73 69 6e 67 20 64 65 66 61 75 6c 74 20 76 61 6c 75 65 73 2e 0d 0a 20 "
    "20 0d 0a 0d 0a 0d 0a 11 41 45 41 20 50 4b 2d 32 33 32 4d 20 44 61 74 "
    "61 20 43 6f 6e 74 72 6f 6c 6c 65 72 0d 0a 43 6f 70 79 72 69 67 68 74 "
    "20 28 43 29 20 31 39 38 36 2d 31 39 39 31 20 62 79 0d 0a 41 64 76 61 "
    "6e 63 65 64 20 45 6c 65 63 74 72 6f 6e 69 63 20 41 70 70 6c 69 63 61 "
    "74 69 6f 6e 73 2c 20 49 6e 63 2e 0d 0a 52 65 6c 65 61 73 65 20 30 31 "
    "2e 41 55 47 2e 39 31 0d 0a 0d 0a 63 6d 64 3a"
)


class TestWakeupLogMessage:
    def test_prompt_present_logs_info(self):
        level, message = _wakeup_log_message(b"AEA PK-232MBX Ver. 7.1\r\ncmd:")
        assert level == logging.INFO
        assert message == "TNC at cmd: prompt"

    def test_no_prompt_logs_warning_with_raw_bytes(self):
        # Real fixture, hw_logs/20260923_204041_maildrop_session.log:
        # wakeup '*' got back '*\' + CR + LF -- no 'cmd:' at all, but the
        # code used to log "TNC at cmd: prompt" regardless (P35 finding).
        resp = bytes([0x2A, 0x5C, 0x0D, 0x0A])
        level, message = _wakeup_log_message(resp)
        assert level == logging.WARNING
        assert message == (
            "wakeup answered without prompt (4 bytes) -- continuing: "
            "2a 5c 0d 0a"
        )

    def test_empty_response_logs_warning_not_a_false_prompt(self):
        level, message = _wakeup_log_message(b"")
        assert level == logging.WARNING
        assert "without prompt (0 bytes)" in message


class TestBannerProvenance:
    """P37 - firmware release date and 'using defaults' flag, both read
    straight off the boot banner (docs/PK232_firmware_matrix.md §1)."""

    def test_release_extracted_from_real_device_b_banner(self):
        assert _parse_release(_DEVICE_B_BANNER) == "01.AUG.91"

    def test_defaults_flag_true_on_real_device_b_banner(self):
        assert _parse_defaults_flag(_DEVICE_B_BANNER) is True

    def test_no_banner_captured_gives_none_not_a_guess(self):
        # P37: "nichts erfinden" - an empty banner (TNC already at cmd:
        # at connect time) must not be reported as any particular release
        # or defaults state.
        assert _parse_release(b"") is None
        assert _parse_defaults_flag(b"") is None

    def test_defaults_flag_false_when_banner_lacks_the_phrase(self):
        banner = b"AEA PK-232 ...\r\nRelease 11.SEP.95\r\n\r\ncmd:"
        assert _parse_release(banner) == "11.SEP.95"
        assert _parse_defaults_flag(banner) is False


class TestClassifyMaildropResponse:
    """P37 Teil D - MailDrop capability detection via a verbose-mode
    'MAILDROP' query, never MDCHECK."""

    def test_on_answers_true(self):
        assert _classify_maildrop_response(
            "MAILDROP\r\nMAildrop  ON\r\ncmd:"
        ) is True

    def test_off_still_answers_true_the_command_exists(self):
        assert _classify_maildrop_response(
            "MAILDROP\r\nMAildrop  OFF\r\ncmd:"
        ) is True

    def test_what_error_answers_false(self):
        assert _classify_maildrop_response(
            "MAILDROP\r\n?What?\r\ncmd:"
        ) is False

    def test_empty_or_garbled_answers_none_not_a_guess(self):
        assert _classify_maildrop_response("") is None
        assert _classify_maildrop_response("cmd:") is None


class TestParseVerboseQueryValue:
    """P40.3 - upload-verification queries (MYCALL/PACLEN/MAXFRAME),
    same '<echo>\\r\\n<Name mixed-case> <value>\\r\\ncmd:' format
    confirmed by P15 for parse_query_value()-style responses."""

    def test_extracts_the_value_skipping_the_echo(self):
        assert _parse_verbose_query_value(
            "MYCALL", "MYCALL\r\nMYcall    OE3GAS\r\ncmd:"
        ) == "OE3GAS"

    def test_numeric_value(self):
        assert _parse_verbose_query_value(
            "PACLEN", "PACLEN\r\nPAclen    128\r\ncmd:"
        ) == "128"

    def test_what_error_answers_none(self):
        assert _parse_verbose_query_value(
            "MAXFRAME", "MAXFRAME\r\n?What?\r\ncmd:"
        ) is None

    def test_empty_or_garbled_answers_none_not_a_guess(self):
        assert _parse_verbose_query_value("MYCALL", "") is None
        assert _parse_verbose_query_value("MYCALL", "cmd:") is None

    def test_only_the_echo_with_no_answer_line_is_none(self):
        # The echo alone (token == name.upper() exactly) must never be
        # mistaken for the TNC's own answer line.
        assert _parse_verbose_query_value("MYCALL", "MYCALL\r\ncmd:") is None
