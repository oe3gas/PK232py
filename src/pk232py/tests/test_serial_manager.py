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

from pk232py.comm.serial_manager import _wakeup_log_message


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
