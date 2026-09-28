# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Unit tests for pk232py.comm.link_status (P67, Teil A/E).

decode_link_status()/LinkStatus moved here from tools/hw_check.py
(P65/P66); parse_cstatus() and split_channel_prefix() are new (P67).
"""

from __future__ import annotations

from pk232py.comm.link_status import (
    LinkStatus,
    decode_link_status,
    extract_partner,
    parse_cstatus,
    split_channel_prefix,
)


class TestDecodeLinkStatus:
    """TRM 4.3.3's Link Status response, SOH $4x 'C' 'O' a b c d e
    <path> ETB (P65, A.6; moved here P67, Teil A)."""

    def test_trm_example_state_5_with_path(self):
        # TRM 4.3.3's own worked example: ctl byte $34 -> link state
        # S05 (state 5), path "W6CUS-1 via K6LLK, WD6CMU-1".
        data = b"CO" + bytes([0x34, 0, 0, 0, 0]) + b"W6CUS-1 via K6LLK, WD6CMU-1"
        result = decode_link_status(0x41, data)
        assert result.state == 5
        assert result.connected is True
        assert result.partner == "W6CUS-1"
        assert result.digis == "K6LLK, WD6CMU-1"
        assert result.unparsed is False

    def test_channel_comes_from_the_ctl_nibble_not_send_order(self):
        data = b"CO" + bytes([0x34, 0, 0, 0, 0])
        assert decode_link_status(0x43, data).channel == 3
        assert decode_link_status(0x40, data).channel == 0
        assert decode_link_status(0x49, data).channel == 9

    def test_free_channel_has_an_empty_partner_and_digis(self):
        # A well-shaped response (7+ bytes, CO-prefixed) with no
        # partner callsign following the five status bytes - still
        # decodes cleanly, just with empty partner/digis.
        data = b"CO" + bytes([0x30, 0, 0, 0, 0])
        result = decode_link_status(0x40, data)
        assert result.partner == ""
        assert result.digis == ""
        assert result.connected is False
        assert result.unparsed is False

    def test_too_short_is_unparsed(self):
        result = decode_link_status(0x41, b"CO")
        assert result.unparsed is True
        assert result.channel == 1
        assert result.raw == b"CO"

    def test_wrong_mnemonic_prefix_is_unparsed(self):
        result = decode_link_status(0x41, b"XX" + bytes(5))
        assert result.unparsed is True

    def test_v2_unacked_retries_conperm_are_masked_and_typed(self):
        # P66, B.5 - all five status bytes are "value OR $30" (TRM),
        # not raw byte values; v2/conperm are single-bit flags -> bool,
        # unacked/retries stay counts -> int.
        data = b"CO" + bytes([0x31, 0x31, 0x32, 0x33, 0x31])
        result = decode_link_status(0x41, data)
        assert result.v2 is True
        assert result.unacked == 2
        assert result.retries == 3
        assert result.conperm is True

    def test_t142_real_bytes_connected_channel_1(self):
        # Real capture, T142, Device B, 28.09.2026,
        # 20260928_094231_link_carry_host.log: channel 1 connected to
        # OE3GAS-1 -> 'CO41000OE3GAS-1', path with NO separator.
        result = decode_link_status(0x41, b"CO41000OE3GAS-1")
        assert result.channel == 1
        assert result.state == 5
        assert result.connected is True
        assert result.v2 is True
        assert result.unacked == 0
        assert result.retries == 0
        assert result.conperm is False
        assert result.partner == "OE3GAS-1"
        assert result.digis == ""
        assert result.unparsed is False

    def test_t142_real_bytes_free_channel(self):
        # Same capture, a free channel: 'CO00000'.
        result = decode_link_status(0x43, b"CO00000")
        assert result.channel == 3
        assert result.state == 1
        assert result.connected is False
        assert result.v2 is False
        assert result.unacked == 0
        assert result.retries == 0
        assert result.conperm is False
        assert result.partner == ""
        assert result.digis == ""

    def test_one_byte_error_code_is_recognised_not_guessed(self):
        # P67, H.3: a real hardware run's CO answer to a CONNECT
        # targeting an already-connected station was a single error
        # byte, 'CO' + $0C - not the five-status-byte shape at all.
        # The MEANING of $0C is not recorded - only that it IS an
        # error code, distinct from 'unparsed'.
        result = decode_link_status(0x41, b"CO" + bytes([0x0C]))
        assert result.error_code == 0x0C
        assert result.unparsed is False
        assert result.connected is False


class TestExtractPartner:
    """extract_partner() - moved here from modes/packet_hf.py's own
    _extract_partner() (P67, Teil B), re-exported there unchanged."""

    def test_connected_to_form(self):
        assert extract_partner("CONNECTED to OE1XYZ-5") == "OE1XYZ-5"

    def test_connect_request_colon_form(self):
        assert extract_partner("Connect request: OE1XYZ") == "OE1XYZ"

    def test_last_colon_wins_over_an_embedded_timestamp(self):
        # P55.A: CONSTAMP/DAYSTAMP both ON prefixes a real message with
        # the TNC's own date/time, whose own 'HH:MM:SS' contributes two
        # colons ahead of the real callsign marker.
        text = "*** 25-Sep-26 21:04:36 DISCONNECTED: OE3TEC-1 ***"
        assert extract_partner(text) == "OE3TEC-1"


class TestParseCstatus:
    """Verbose CSTATUS response parsing (P67, M2/M6 - real examples
    from the P66/P66b/P67 hardware logs)."""

    def test_io_channel_with_connected_partner(self):
        # T142/P66b: 'Ch. 0 - IO CONNECTED to OE3GAS-1; v2'
        result = parse_cstatus("Ch. 0 - IO CONNECTED to OE3GAS-1; v2")
        io, state_text, partner = result[0]
        assert io is True
        assert partner == "OE3GAS-1"
        assert "CONNECTED to OE3GAS-1" in state_text

    def test_io_channel_with_no_connection(self):
        # P66b, B.4: 'Ch. 9 - IO' alone (no connection on that channel).
        result = parse_cstatus("Ch. 9 - IO")
        io, _state_text, partner = result[9]
        assert io is True
        assert partner == ""

    def test_connected_channel_without_io_marker(self):
        # T141/P67 M3: 'Ch. 1 - CONNECTED to OE3GAS-1; v2', not the
        # active/IO channel.
        result = parse_cstatus("Ch. 1 - CONNECTED to OE3GAS-1; v2")
        io, _state_text, partner = result[1]
        assert io is False
        assert partner == "OE3GAS-1"

    def test_multiple_channels_in_one_response(self):
        text = "Ch. 0 - IO CONNECTED to OE3GAS-1; v2\nCh. 3 - IO\n"
        result = parse_cstatus(text)
        assert set(result.keys()) == {0, 3}
        assert result[0][0] is True
        assert result[3][0] is True


class TestSplitChannelPrefix:
    """The M10 verbose channel-number prefix (P67 - hardware-observed,
    Device B, 28.09.2026)."""

    def test_already_connected_prefix(self):
        channel, text = split_channel_prefix("\x000: ?already connected …")
        assert channel == 0
        assert text == "?already connected …"

    def test_cmd_prompt_prefix(self):
        channel, text = split_channel_prefix("\x009: cmd:")
        assert channel == 9
        assert text == "cmd:"

    def test_no_prefix_returns_none_and_the_line_unchanged(self):
        channel, text = split_channel_prefix("cmd:")
        assert channel is None
        assert text == "cmd:"
