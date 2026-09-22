# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Unit tests for pk232py.modes.signal_analysis (P18.2).

Fixtures are the REAL frames captured during T113 (hardware, 2026-09-22,
docs/P18_HF_Init_SIAM_Spec.md), in exactly the order they were received:

    $50 ch0  "0.12: 248 baud, "      $50 ch0  "Baudot, RXRev OFF\\r\\n"
    $50 ch0  "0.32: 50 baud, "       $50 ch0  "Baudot, RXRev ON\\r\\n"
    $50 ch0  "0.73: 50 baud, "       $50 ch0  "Baudot, RXRev ON\\r\\n"
    $50 ch0  "0.33: 51 baud, "       (cut off when the 60s window ended)

Covers the P16.3 finding (any stray CMD_RESP treated as a SIAM result)
being closed for good: CMD_RESP now never reaches on_result()/
on_result_parsed(), not even the previous "ends in \\x00 is an ACK"
heuristic - LINK_MSG is the only source of results at all.
"""

from __future__ import annotations

from pk232py.comm.frame import FrameKind, HostFrame
from pk232py.modes.signal_analysis import SignalMode, SiamResult, parse_siam_result


def _link_msg(text: str) -> HostFrame:
    return HostFrame(ctl=0x50, channel=0, data=text.encode("ascii"), kind=FrameKind.LINK_MSG)


def _cmd_resp(data: bytes) -> HostFrame:
    return HostFrame(ctl=0x4F, channel=15, data=data, kind=FrameKind.CMD_RESP)


class TestParseSiamResult:
    def test_hardware_example(self):
        r = parse_siam_result("0.73: 50 baud, Baudot, RXRev ON")
        assert r == SiamResult(confidence=0.73, baud=50, mode="Baudot", rxrev=True,
                                raw="0.73: 50 baud, Baudot, RXRev ON")

    def test_rxrev_off(self):
        r = parse_siam_result("0.12: 248 baud, Baudot, RXRev OFF")
        assert r.rxrev is False
        assert r.baud == 248

    def test_case_insensitive_rxrev(self):
        r = parse_siam_result("0.5: 45 baud, ASCII, rxrev on")
        assert r is not None
        assert r.rxrev is True

    def test_non_matching_text_returns_none(self):
        assert parse_siam_result("UNKNOWN") is None
        assert parse_siam_result("BAUDOT 45 170") is None
        assert parse_siam_result("") is None


class TestSignalModeCmdRespNeverAResult:
    """P16.3/P18.2: closes the finding for good - CMD_RESP must never
    reach on_result() or on_result_parsed(), regardless of its payload."""

    def test_stray_cmd_resp_frames_are_ignored(self):
        mode = SignalMode()
        results: list = []
        parsed: list = []
        mode.on_result = results.append
        mode.on_result_parsed = parsed.append

        for data in (b"HP\x00", b"PXN", b"SI\x00"):
            mode.handle_frame(_cmd_resp(data))

        assert results == []
        assert parsed == []


class TestSignalModeFragmentAssembly:
    def test_two_fragments_join_into_one_result(self):
        mode = SignalMode()
        results: list = []
        mode.on_result = results.append

        mode.handle_frame(_link_msg("0.12: 248 baud, "))
        assert results == []  # first fragment alone must not fire

        mode.handle_frame(_link_msg("Baudot, RXRev OFF\r\n"))
        assert results == ["0.12: 248 baud, Baudot, RXRev OFF"]

    def test_parsed_result_fields_match_hardware_example(self):
        mode = SignalMode()
        parsed: list = []
        mode.on_result_parsed = parsed.append

        mode.handle_frame(_link_msg("0.73: 50 baud, "))
        mode.handle_frame(_link_msg("Baudot, RXRev ON\r\n"))

        assert len(parsed) == 1
        r = parsed[0]
        assert (r.confidence, r.baud, r.mode, r.rxrev) == (0.73, 50, "Baudot", True)

    def test_full_t113_sequence_yields_three_results_no_fourth(self):
        mode = SignalMode()
        results: list = []
        mode.on_result = results.append

        fragments = [
            "0.12: 248 baud, ", "Baudot, RXRev OFF\r\n",
            "0.32: 50 baud, ",  "Baudot, RXRev ON\r\n",
            "0.73: 50 baud, ",  "Baudot, RXRev ON\r\n",
            "0.33: 51 baud, ",  # cut off - no closing fragment arrives
        ]
        for frag in fragments:
            mode.handle_frame(_link_msg(frag))

        assert results == [
            "0.12: 248 baud, Baudot, RXRev OFF",
            "0.32: 50 baud, Baudot, RXRev ON",
            "0.73: 50 baud, Baudot, RXRev ON",
        ]

    def test_truncated_last_fragment_does_not_fire(self):
        mode = SignalMode()
        results: list = []
        mode.on_result = results.append

        mode.handle_frame(_link_msg("0.33: 51 baud, "))

        assert results == []

    def test_unrecognised_format_only_fires_on_result(self):
        mode = SignalMode()
        results: list = []
        parsed: list = []
        mode.on_result = results.append
        mode.on_result_parsed = parsed.append

        mode.handle_frame(_link_msg("UNKNOWN\r\n"))

        assert results == ["UNKNOWN"]
        assert parsed == []

    def test_oversized_buffer_without_line_ending_is_discarded(self):
        mode = SignalMode()
        results: list = []
        mode.on_result = results.append

        mode.handle_frame(_link_msg("x" * 250))

        assert results == []
        assert mode._siam_buffer == ""

    def test_get_activate_frames_resets_the_buffer(self):
        mode = SignalMode()
        mode.handle_frame(_link_msg("0.12: 248 baud, "))
        assert mode._siam_buffer != ""

        mode.get_activate_frames()

        assert mode._siam_buffer == ""
