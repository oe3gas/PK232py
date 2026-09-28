# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Unit tests for tools/hw_check.py's link/mode carry-over measurement
package (P65).

Covers the pure-logic piece (decode_link_status) and the two new
subcommands' --dry-run path (no port opened, nothing sent) - the same
"measures only" boundary the rest of hw_check.py already has
(docs/P14_HW_Solo_Check_Spec.md hard rule #4/#6).

tools/ has no __init__.py and is not part of the installed package -
see test_hw_check.py's own docstring for why sys.path is extended here
instead of a regular import.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from pk232py.config import AppConfig

_TOOLS_DIR = Path(__file__).resolve().parents[3] / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import hw_check  # noqa: E402

# Same reasoning as test_hw_check.py: a full QApplication, not a bare
# QCoreApplication - whichever test module imports first installs the
# singleton other modules' QApplication.instance() later finds.
_APP = QApplication.instance() or QApplication(sys.argv[:1])


def _dry_run_session() -> tuple["hw_check.Session", "hw_check.RunLog"]:
    log = hw_check.RunLog(None)
    session = hw_check.Session("DRYRUN", 9600, True, log, AppConfig())
    return session, log


class TestDecodeLinkStatus:
    """P65, Teil A.6/C - TRM 4.3.3's Link Status response,
    SOH $4x 'C' 'O' a b c d e <path> ETB."""

    def test_trm_example_state_5_with_path(self):
        # TRM 4.3.3's own worked example: ctl byte $34 -> link state
        # S05 (state 5), path "W6CUS-1 via K6LLK, WD6CMU-1".
        data = b"CO" + bytes([0x34, 0, 0, 0, 0]) + b"W6CUS-1 via K6LLK, WD6CMU-1"
        result = hw_check.decode_link_status(0x41, data)
        assert result["state"] == 5
        assert result["path"] == "W6CUS-1 via K6LLK, WD6CMU-1"
        assert "unparsed" not in result

    def test_channel_comes_from_the_ctl_nibble_not_send_order(self):
        data = b"CO" + bytes([0x34, 0, 0, 0, 0])
        assert hw_check.decode_link_status(0x43, data)["channel"] == 3
        assert hw_check.decode_link_status(0x40, data)["channel"] == 0
        assert hw_check.decode_link_status(0x49, data)["channel"] == 9

    def test_free_channel_has_an_empty_path(self):
        # A well-shaped response (7+ bytes, CO-prefixed) with no
        # partner callsign following the five status bytes - still
        # decodes cleanly, just with an empty path.
        data = b"CO" + bytes([0x30, 0, 0, 0, 0])
        result = hw_check.decode_link_status(0x40, data)
        assert result["path"] == ""
        assert "unparsed" not in result

    def test_too_short_is_unparsed(self):
        result = hw_check.decode_link_status(0x41, b"CO")
        assert result["unparsed"] is True
        assert result["channel"] == 1
        assert result["raw"] == b"CO"

    def test_wrong_mnemonic_prefix_is_unparsed(self):
        result = hw_check.decode_link_status(0x41, b"XX" + bytes(5))
        assert result["unparsed"] is True

    def test_v2_unacked_retries_conperm_are_raw_byte_values(self):
        data = b"CO" + bytes([0x31, 1, 2, 3, 4])
        result = hw_check.decode_link_status(0x41, data)
        assert result["v2"] == 1
        assert result["unacked"] == 2
        assert result["retries"] == 3
        assert result["conperm"] == 4


class TestLinkCarryDryRun:
    """P65, Definition of Done - --dry-run opens no port and sends
    nothing for both new subcommands."""

    def test_link_carry_dry_run_touches_no_port(self):
        session, log = _dry_run_session()
        hw_check.test_link_carry(session, log)
        assert session.sm.is_connected is False
        assert ("T141", "INFO", "dry-run, nothing sent") in log.findings

    def test_link_carry_host_dry_run_touches_no_port(self):
        session, log = _dry_run_session()
        hw_check.test_link_carry_host(session, log)
        assert session.sm.is_connected is False
        assert ("T142", "INFO", "dry-run, nothing sent") in log.findings


class TestLinkCarryDryRunFramesComeFromRealBuilders:
    """P65, Teil C - no new frame builder anywhere: the A.6 link-status
    query is HostModeProtocol.cmd_link_status()'s own bytes, A.8's
    mode-switch frames are VHFPacketMode's own get_activate_frames()/
    get_init_frames(), and Teil B's connect frame is
    HostModeProtocol.cmd_connect()'s own bytes - compared directly
    against those builders, never a hand-copied expectation."""

    def test_link_carry_preview_includes_cmd_link_status_frames(self, capsys):
        session, log = _dry_run_session()
        hw_check.test_link_carry(session, log)
        out = capsys.readouterr().out
        for ch in range(10):
            frame = hw_check.HostModeProtocol.cmd_link_status(ch)
            assert frame.hex(" ").upper() in out, f"channel {ch} CO query missing"

    def test_link_carry_preview_includes_vhf_mode_switch_frames(self, capsys):
        session, log = _dry_run_session()
        hw_check.test_link_carry(session, log)
        out = capsys.readouterr().out
        vhf = hw_check.VHFPacketMode()
        for frame in vhf.get_activate_frames() + vhf.get_init_frames():
            assert frame.hex(" ").upper() in out

    def test_link_carry_host_preview_includes_cmd_connect_frame(self, capsys):
        session, log = _dry_run_session()
        hw_check.test_link_carry_host(session, log)
        out = capsys.readouterr().out
        frame = hw_check.HostModeProtocol.cmd_connect("OE3GAS-1", channel=1)
        assert frame.hex(" ").upper() in out
