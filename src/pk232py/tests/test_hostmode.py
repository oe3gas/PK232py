# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Unit tests for the Host Mode protocol stack.

Covers:
  - frame.py    : build_command, build_ch_cmd, build_data, FrameParser,
                  HostFrame, FrameKind, DLE escaping
  - hostmode.py : HostModeProtocol convenience commands
  - autobaud.py : parse_firmware_version, is_cmd_prompt, AutobaudDetector
  - kiss.py     : frame builders, KissParser, escaping
"""

import pytest

from pk232py.comm.constants import SOH, ETB, DLE
from pk232py.comm.frame import (
    HostFrame, FrameKind, FrameParser,
    build_command, build_ch_cmd, build_data,
    _dle_escape, _dle_unescape,
)
from pk232py.comm.hostmode import HostModeProtocol


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse(raw: bytes) -> list[HostFrame]:
    """Feed *raw* into a fresh FrameParser and return all decoded frames."""
    frames: list[HostFrame] = []
    FrameParser(frames.append).feed(raw)
    return frames


# ===========================================================================
# Frame building  (frame.py)
# ===========================================================================

class TestBuildCommand:
    """build_command() — CTL = $4F, general commands."""

    def test_basic_structure(self):
        f = build_command(b'HO', b'Y')
        assert f[0] == SOH
        assert f[1] == 0x4F
        assert f[-1] == ETB

    def test_mnemonic_in_payload(self):
        f = build_command(b'ML', b'OE3GAS')
        assert b'ML' in f
        assert b'OE3GAS' in f

    def test_no_args(self):
        f = build_command(b'GG')
        assert f == bytes([SOH, 0x4F, ord('G'), ord('G'), ETB])

    def test_mnemonic_must_be_two_bytes(self):
        with pytest.raises(ValueError):
            build_command(b'H')        # too short
        with pytest.raises(ValueError):
            build_command(b'HOS')      # too long

    def test_dle_escaping_in_args(self):
        # If args contain SOH, DLE or ETB they must be escaped
        args_with_soh = bytes([SOH])
        f = build_command(b'TD', args_with_soh)
        # DLE must appear before SOH in the frame payload
        idx = f.index(DLE)
        assert f[idx + 1] == SOH

    def test_host_on(self):
        f = HostModeProtocol.cmd_host_on()
        assert f == bytes([SOH, 0x4F, ord('H'), ord('O'), ord('Y'), ETB])

    def test_host_off(self):
        f = HostModeProtocol.cmd_host_off()
        assert f == bytes([SOH, 0x4F, ord('H'), ord('O'), ord('N'), ETB])


class TestBuildChannelCommand:
    """build_ch_cmd() — CTL = $4x, CONNECT / DISCONNECT."""

    def test_connect_ch1(self):
        f = build_ch_cmd(1, b'CO', b'OE3GAS')
        assert f[0] == SOH
        assert f[1] == 0x41          # CTL = $41 = command to channel 1
        assert b'CO' in f
        assert b'OE3GAS' in f
        assert f[-1] == ETB

    def test_disconnect_ch2(self):
        f = build_ch_cmd(2, b'DI')
        assert f[1] == 0x42

    def test_channel_out_of_range(self):
        with pytest.raises(ValueError):
            build_ch_cmd(10, b'CO')
        with pytest.raises(ValueError):
            build_ch_cmd(-1, b'CO')

    def test_mnemonic_must_be_two_bytes(self):
        with pytest.raises(ValueError):
            build_ch_cmd(1, b'C')
        with pytest.raises(ValueError):
            build_ch_cmd(1, b'CON')


class TestBuildData:
    """build_data() — CTL = $2x, outgoing data frames."""

    def test_basic_structure(self):
        f = build_data(0, b'hello')
        assert f[0] == SOH
        assert f[1] == 0x20          # CTL = $20 = data to channel 0
        assert b'hello' in f
        assert f[-1] == ETB

    def test_channel_encoded_in_ctl(self):
        assert build_data(3, b'x')[1] == 0x23

    def test_dle_escaping(self):
        raw = bytes([0x04, SOH, 0x05, DLE, 0x12])
        f   = build_data(0, raw)
        expected = bytes([SOH, 0x20, 0x04, DLE, SOH, 0x05, DLE, DLE, 0x12, ETB])
        assert f == expected

    def test_channel_out_of_range(self):
        with pytest.raises(ValueError):
            build_data(10, b'x')

    def test_data_too_long(self):
        with pytest.raises(ValueError):
            build_data(0, b'x' * 257)


class TestDleEscaping:
    """_dle_escape / _dle_unescape round-trips."""

    def test_escape_soh(self):
        assert _dle_escape(bytes([SOH])) == bytes([DLE, SOH])

    def test_escape_etb(self):
        assert _dle_escape(bytes([ETB])) == bytes([DLE, ETB])

    def test_escape_dle(self):
        assert _dle_escape(bytes([DLE])) == bytes([DLE, DLE])

    def test_passthrough_normal_bytes(self):
        data = b'OE3GAS'
        assert _dle_escape(data) == data

    def test_roundtrip(self):
        raw = bytes([0x04, SOH, 0x05, DLE, 0x12, ETB, 0x99])
        assert _dle_unescape(_dle_escape(raw)) == raw


# ===========================================================================
# Frame parsing  (frame.py FrameParser)
# ===========================================================================

class TestFrameParser:
    """FrameParser — byte stream → HostFrame."""

    def test_cmd_resp_single(self):
        raw = bytes([SOH, 0x4F, ord('H'), ord('O'), 0x00, ETB])
        frames = _parse(raw)
        assert len(frames) == 1
        f = frames[0]
        assert f.kind     == FrameKind.CMD_RESP
        assert f.mnemonic == b'HO'
        assert f.cmd_error == 0x00
        assert f.is_ack

    def test_rx_data_channel(self):
        raw = bytes([SOH, 0x31, ord('H'), ord('i'), ETB])
        frames = _parse(raw)
        assert frames[0].kind    == FrameKind.RX_DATA
        assert frames[0].channel == 1
        assert frames[0].data    == b'Hi'

    def test_rx_monitor(self):
        raw = bytes([SOH, 0x3F]) + b'OE3GAS>CQ:Hello' + bytes([ETB])
        frames = _parse(raw)
        assert frames[0].kind == FrameKind.RX_MONITOR
        assert frames[0].text == 'OE3GAS>CQ:Hello'

    def test_link_msg(self):
        msg = b'CONNECTED to OE3XYZ'
        raw = bytes([SOH, 0x51]) + msg + bytes([ETB])
        frames = _parse(raw)
        assert frames[0].kind    == FrameKind.LINK_MSG
        assert frames[0].channel == 1
        assert frames[0].data    == msg

    def test_dle_unescape_in_payload(self):
        # TNC sends data containing an escaped SOH
        raw = bytes([SOH, 0x30, DLE, SOH, 0x05, ETB])
        frames = _parse(raw)
        assert frames[0].data == bytes([SOH, 0x05])

    def test_two_frames_in_one_feed(self):
        f1 = bytes([SOH, 0x30, ord('A'), ETB])
        f2 = bytes([SOH, 0x4F, ord('P'), ord('A'), 0x00, ETB])
        frames = _parse(f1 + f2)
        assert len(frames) == 2
        assert frames[0].kind == FrameKind.RX_DATA
        assert frames[1].kind == FrameKind.CMD_RESP

    def test_incremental_byte_by_byte(self):
        raw    = bytes([SOH, 0x4F, ord('R'), ord('T'), 0x00, ETB])
        frames: list[HostFrame] = []
        parser = FrameParser(frames.append)
        for byte in raw:
            parser.feed(bytes([byte]))
        assert len(frames) == 1
        assert frames[0].mnemonic == b'RT'

    def test_double_soh_recovery(self):
        # Double SOH followed by valid frame
        raw = bytes([SOH, SOH, 0x4F, ord('G'), ord('G'), 0x00, ETB])
        frames = _parse(raw)
        assert len(frames) == 1
        assert frames[0].is_poll_ok

    def test_poll_ok(self):
        raw = bytes([SOH, 0x4F, ord('G'), ord('G'), 0x00, ETB])
        frames = _parse(raw)
        assert frames[0].is_poll_ok

    def test_ch_cmd_frame_parsed(self):
        # build_ch_cmd(1, b'DI') -> SOH $41 b'DI' ETB
        # Parser: CTL=$41 -> LINK_STATUS, data=b'DI' (the mnemonic bytes).
        f = build_ch_cmd(1, b'DI')
        frames = _parse(f)
        assert len(frames) == 1
        assert frames[0].kind == FrameKind.LINK_STATUS
        assert frames[0].data == b'DI'

    def test_parser_reset(self):
        parser = FrameParser(lambda f: None)
        # Feed partial frame then reset
        parser.feed(bytes([SOH, 0x4F]))
        parser.reset()
        # After reset a complete frame must be parsed correctly
        frames: list[HostFrame] = []
        parser2 = FrameParser(frames.append)
        parser2.feed(bytes([SOH, 0x4F, ord('P'), ord('A'), 0x00, ETB]))
        assert frames[0].mnemonic == b'PA'


# ===========================================================================
# HostModeProtocol convenience commands  (hostmode.py)
# ===========================================================================

class TestHostModeProtocol:
    """HostModeProtocol — convenience command builders."""

    def test_cmd_restart(self):
        f = HostModeProtocol.cmd_restart()
        assert f[0] == SOH and f[1] == 0x4F
        assert b'RT' in f

    def test_cmd_mycall(self):
        f = HostModeProtocol.cmd_mycall('oe3gas')   # lowercase → uppercase
        assert b'ML' in f
        assert b'OE3GAS' in f

    def test_cmd_mycall_uppercase(self):
        f = HostModeProtocol.cmd_mycall('OE3GAS')
        assert b'OE3GAS' in f

    def test_cmd_connect(self):
        f = HostModeProtocol.cmd_connect('OE3XYZ', channel=1)
        assert f[1] == 0x41
        assert b'CO' in f
        assert b'OE3XYZ' in f

    def test_cmd_disconnect(self):
        f = HostModeProtocol.cmd_disconnect(channel=2)
        assert f[1] == 0x42
        assert b'DI' in f

    def test_poll_frame(self):
        assert HostModeProtocol.poll() == bytes([SOH, 0x4F, ord('G'), ord('G'), ETB])

    def test_recovery_frame(self):
        assert HostModeProtocol.recovery() == bytes([SOH, SOH, 0x4F, ord('G'), ord('G'), ETB])

    def test_hpoll_on(self):
        f = HostModeProtocol.cmd_hpoll_on()
        assert b'HP' in f and b'Y' in f

    def test_mode_commands(self):
        assert b'PA' in HostModeProtocol.cmd_packet()
        assert b'PT' in HostModeProtocol.cmd_pactor()
        assert b'AM' in HostModeProtocol.cmd_amtor()

    def test_feed_delivers_frame(self):
        frames: list[HostFrame] = []
        hm = HostModeProtocol(frames.append)
        hm.feed(bytes([SOH, 0x4F, ord('P'), ord('A'), 0x00, ETB]))
        assert len(frames) == 1
        assert frames[0].mnemonic == b'PA'

    def test_init_sequence(self):
        seq = HostModeProtocol.init_sequence()
        assert b'AWLEN 8\r'  in seq
        assert b'RESTART\r'  in seq
        assert b'HOST Y\r'   in seq


# ===========================================================================
# Autobaud  (autobaud.py)
# ===========================================================================

class TestAutobaud:
    """parse_firmware_version, is_cmd_prompt, AutobaudDetector."""

    def test_parse_v71_dots(self):
        from pk232py.comm.autobaud import parse_firmware_version
        banner = (
            "AEA PK-232M Data Controller\r\n"
            "Copyright (C) 1986-1990 by\r\n"
            "Advanced Electronic Applications, Inc.\r\n"
            "Release 13.09.95\r\n"
            "cmd:\r\n"
        )
        version, date = parse_firmware_version(banner)
        assert version == "7.1"
        assert date    == "13.09.95"

    def test_parse_v71_dashes(self):
        # Dash separator: fallback regex branch
        from pk232py.comm.autobaud import parse_firmware_version
        version, date = parse_firmware_version("Release 13-09-95\ncmd:")
        assert version == "7.1"

    def test_parse_v72(self):
        from pk232py.comm.autobaud import parse_firmware_version
        version, _ = parse_firmware_version("Release 10.08.98\ncmd:")
        assert version == "7.2"

    def test_parse_unknown_date_returns_none_version_but_date(self):
        from pk232py.comm.autobaud import parse_firmware_version
        version, date = parse_firmware_version("Release 01.01.97\ncmd:")
        assert version is None
        assert date == "01.01.97"   # date is still returned

    def test_no_release_line(self):
        from pk232py.comm.autobaud import parse_firmware_version
        version, date = parse_firmware_version("garbled text")
        assert version is None
        assert date    is None

    def test_cmd_prompt_detection(self):
        from pk232py.comm.autobaud import is_cmd_prompt
        assert is_cmd_prompt("cmd:")             is True
        assert is_cmd_prompt("CMD:")             is True
        assert is_cmd_prompt("some text cmd: x") is True
        assert is_cmd_prompt("no prompt here")   is False

    def test_autobaud_detector_scenario_a(self):
        """TNC responds to '*' with banner (autobaud active)."""
        import time
        from pk232py.comm.autobaud import AutobaudDetector

        BANNER = "AEA PK-232M Data Controller\nRelease 13.09.95\ncmd:"
        responses = iter([BANNER, ""])

        def open_port(baud): pass
        def close_port():    pass
        def write(data):     pass
        def read_until(t):
            try:    return next(responses)
            except: return ""

        info = AutobaudDetector(open_port, close_port, write, read_until).detect([9600])
        assert info is not None
        assert info.baud_rate   == 9600
        assert info.version     == "7.1"
        assert info.had_banner  is True

    def test_autobaud_detector_scenario_b(self):
        """TNC already running — responds to CR with cmd: prompt."""
        from pk232py.comm.autobaud import AutobaudDetector

        responses = iter(["", "cmd:"])

        def open_port(baud): pass
        def close_port():    pass
        def write(data):     pass
        def read_until(t):
            try:    return next(responses)
            except: return ""

        info = AutobaudDetector(open_port, close_port, write, read_until).detect([9600])
        assert info is not None
        assert info.baud_rate   == 9600
        assert info.had_banner  is False

    def test_autobaud_detector_no_response(self):
        from pk232py.comm.autobaud import AutobaudDetector

        def open_port(b): pass
        def close_port(): pass
        def write(d):     pass
        def read_until(t): return ""

        info = AutobaudDetector(open_port, close_port, write, read_until).detect([9600, 4800])
        assert info is None


# ===========================================================================
# KISS protocol  (kiss.py)
# ===========================================================================

class TestKISS:
    """KissParser, frame builders, FESC escaping."""

    def test_build_data_structure(self):
        from pk232py.comm.kiss import build_data, FEND
        f = build_data(b'AX.25 test frame')
        assert f[0]  == FEND
        assert f[1]  == 0x00    # TYPE = port 0, cmd DATA
        assert f[-1] == FEND

    def test_fend_escaping_in_data(self):
        from pk232py.comm.kiss import build_data, FEND, FESC, TFEND
        f = build_data(bytes([FEND]))
        inner = f[2:-1]    # strip leading FEND + TYPE byte + trailing FEND
        assert bytes([FESC, TFEND]) in inner

    def test_fesc_escaping_in_data(self):
        from pk232py.comm.kiss import build_data, FEND, FESC, TFESC
        f = build_data(bytes([FESC]))
        inner = f[2:-1]
        assert bytes([FESC, TFESC]) in inner

    def test_parser_roundtrip(self):
        from pk232py.comm.kiss import build_data, KissParser
        received = []
        parser   = KissParser(received.append)
        data     = b'AX.25 test frame data'
        parser.feed(build_data(data))
        assert len(received) == 1
        assert received[0].data == data
        assert received[0].is_data

    def test_parser_roundtrip_with_fend_in_payload(self):
        from pk232py.comm.kiss import build_data, KissParser, FEND
        received = []
        parser   = KissParser(received.append)
        data     = bytes([0x41, FEND, 0x42])
        parser.feed(build_data(data))
        assert received[0].data == data

    def test_txdelay(self):
        from pk232py.comm.kiss import build_txdelay, FEND
        f = build_txdelay(30)
        assert f == bytes([FEND, 0x01, 30, FEND])

    def test_host_off(self):
        from pk232py.comm.kiss import build_host_off, FEND
        assert build_host_off() == bytes([FEND, 0xFF, FEND])

    def test_back_to_back_fend_ignored(self):
        from pk232py.comm.kiss import KissParser, FEND
        received = []
        parser   = KissParser(received.append)
        # double FEND then valid data frame
        parser.feed(bytes([FEND, FEND, 0x00, ord('X'), FEND]))
        assert len(received) == 1
        assert received[0].data == b'X'

    def test_two_frames_in_one_feed(self):
        from pk232py.comm.kiss import build_data, build_txdelay, KissParser
        received = []
        parser   = KissParser(received.append)
        parser.feed(build_data(b'frame1') + build_txdelay(50))
        assert len(received) == 2
        assert received[0].data == b'frame1'
        assert received[1].data == bytes([50])