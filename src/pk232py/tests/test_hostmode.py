# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Unit tests for the AEA Host Mode protocol parser."""

import pytest
from pk232py.comm.hostmode import HostModeProtocol, HostFrame, SOH, ETB


class TestFrameBuilding:
    """Tests for HostModeProtocol.build_frame()."""

    def test_basic_frame(self):
        frame = HostModeProtocol.build_frame(0x00, b'CO', b'OE3GAS')
        assert frame[0] == SOH
        assert frame[-1] == ETB
        assert b'CO' in frame
        assert b'OE3GAS' in frame

    def test_command_must_be_two_bytes(self):
        with pytest.raises(ValueError):
            HostModeProtocol.build_frame(0x00, b'C')   # too short
        with pytest.raises(ValueError):
            HostModeProtocol.build_frame(0x00, b'CON') # too long

    def test_empty_data(self):
        frame = HostModeProtocol.build_frame(0x00, b'DI')
        assert frame[0] == SOH
        assert frame[-1] == ETB

    def test_length_byte_correct(self):
        data = b'OE3GAS'
        frame = HostModeProtocol.build_frame(0x00, b'CO', data)
        # payload = channel(1) + cmd(2) + data(n) + ETB(1)
        expected_len = 1 + 2 + len(data) + 1
        assert frame[1] == expected_len


class TestFrameParsing:
    """Tests for HostModeProtocol.feed() / frame parsing."""

    def _collect_frames(self, raw: bytes) -> list[HostFrame]:
        frames = []
        proto = HostModeProtocol(frames.append)
        proto.feed(raw)
        return frames

    def test_roundtrip_single_frame(self):
        raw = HostModeProtocol.build_frame(0x01, b'DT', b'Hello')
        frames = self._collect_frames(raw)
        assert len(frames) == 1
        assert frames[0].channel == 0x01
        assert frames[0].command == b'DT'
        assert frames[0].data == b'Hello'

    def test_two_frames_in_sequence(self):
        f1 = HostModeProtocol.build_frame(0x00, b'CO', b'OE3GAS')
        f2 = HostModeProtocol.build_frame(0x01, b'DT', b'73')
        frames = self._collect_frames(f1 + f2)
        assert len(frames) == 2
        assert frames[0].command == b'CO'
        assert frames[1].command == b'DT'

    def test_incremental_feed(self):
        raw = HostModeProtocol.build_frame(0x00, b'ST', b'\x00\x01')
        frames = []
        proto = HostModeProtocol(frames.append)
        for byte in raw:
            proto.feed(bytes([byte]))
        assert len(frames) == 1
        assert frames[0].command == b'ST'

    def test_empty_data_frame(self):
        raw = HostModeProtocol.build_frame(0x00, b'DI')
        frames = self._collect_frames(raw)
        assert len(frames) == 1
        assert frames[0].data == b''

    def test_convenience_cmd_restart(self):
        frame = HostModeProtocol.cmd_restart()
        assert SOH == frame[0]
        assert b'RS' in frame

    def test_convenience_cmd_mycall(self):
        frame = HostModeProtocol.cmd_mycall("oe3gas")
        assert b'OE3GAS' in frame
        assert b'ML' in frame


class TestAutobaud:
    """Tests for firmware version parsing."""

    def test_parse_v71(self):
        from pk232py.comm.autobaud import parse_firmware_version
        banner = (
            "AEA PK-232M Data Controller\r\n"
            "Copyright (C) 1986 - 1990 by\r\n"
            "Advanced Electronic Applications, Inc.\r\n"
            "Release 13-09-95\r\n"
            "cmd:\r\n"
        )
        assert parse_firmware_version(banner) == "7.1"

    def test_parse_v72(self):
        from pk232py.comm.autobaud import parse_firmware_version
        banner = "AEA PK-232M ... Release 10-08-98\ncmd:"
        assert parse_firmware_version(banner) == "7.2"

    def test_parse_unknown(self):
        from pk232py.comm.autobaud import parse_firmware_version
        banner = "Release 01-01-00\ncmd:"
        result = parse_firmware_version(banner)
        # Should return None for unknown version (date not in lookup table)
        assert result is None

    def test_no_release_line(self):
        from pk232py.comm.autobaud import parse_firmware_version
        assert parse_firmware_version("garbled text") is None

    def test_cmd_prompt_detection(self):
        from pk232py.comm.autobaud import is_cmd_prompt
        assert is_cmd_prompt("cmd:") is True
        assert is_cmd_prompt("CMD:") is True
        assert is_cmd_prompt("some text cmd: more") is True
        assert is_cmd_prompt("no prompt here") is False


class TestKISS:
    """Tests for the KISS protocol encoder/decoder."""

    def test_encode_basic_frame(self):
        from pk232py.comm.kiss import encode_frame, FEND
        data = b'\x00\x01\x02'
        encoded = encode_frame(data)
        assert encoded[0] == FEND
        assert encoded[-1] == FEND

    def test_encode_decode_roundtrip(self):
        from pk232py.comm.kiss import encode_frame, FEND, decode_frame
        data = b'AX.25 test frame data'
        encoded = encode_frame(data)
        # Strip FEND delimiters for decode_frame
        inner = encoded[1:-1]
        decoded = decode_frame(inner)
        assert decoded == data

    def test_byte_stuffing_fend(self):
        from pk232py.comm.kiss import encode_frame, FEND, FESC, TFEND
        data = bytes([FEND])
        encoded = encode_frame(data)
        # FEND in data must be escaped as FESC + TFEND
        inner = encoded[1:-1]  # strip outer FENDs
        assert FESC in inner
        assert TFEND in inner

    def test_kiss_protocol_parser(self):
        from pk232py.comm.kiss import encode_frame, KISSProtocol
        received = []
        proto = KISSProtocol(received.append)
        data = b'test AX.25 frame'
        proto.feed(encode_frame(data))
        assert len(received) == 1
        assert received[0] == data
