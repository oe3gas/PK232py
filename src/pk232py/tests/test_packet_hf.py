# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Unit tests for pk232py.modes.packet_hf.

Covers:
  - _extract_partner()      — callsign extraction from $5x link-message text,
                               including the colon-before-callsign variant
  - HFPacketMode.on_channel_state — channel-scoped state derived from the
                               same $5x messages on_link_message already sees
"""

from __future__ import annotations

from pk232py.comm.frame import FrameKind
from pk232py.modes.packet_hf import HFPacketMode, _extract_partner


class _FakeFrame:
    """Minimal stand-in for a decoded HostFrame LINK_MSG."""

    def __init__(self, channel: int, text: str):
        self.channel = channel
        self.text = text
        self.kind = FrameKind.LINK_MSG


# ---------------------------------------------------------------------------
# _extract_partner() — TRM 4.4.4 form vs the colon-before-callsign variant
# (STABO manual chapter 12), each with and without a " via " digipeater path.
# ---------------------------------------------------------------------------

class TestExtractPartner:

    def test_trm_form_no_via(self):
        assert _extract_partner("CONNECTED to OE1XYZ-5") == "OE1XYZ-5"

    def test_trm_form_with_via(self):
        assert _extract_partner(
            "CONNECTED to OE1XYZ-5 via OE1ABC-8"
        ) == "OE1XYZ-5"

    def test_colon_form_no_via(self):
        assert _extract_partner("CONNECTED to: OE1XYZ-5") == "OE1XYZ-5"

    def test_colon_form_with_via(self):
        assert _extract_partner(
            "CONNECTED to: OE1XYZ-5 via OE1ABC-8"
        ) == "OE1XYZ-5"

    def test_colon_form_no_space_after_colon(self):
        # Defensive: some firmware may omit the space after the colon too.
        assert _extract_partner("CONNECTED to:OE1XYZ-5") == "OE1XYZ-5"

    def test_connect_request_colon_marker(self):
        assert _extract_partner("Connect request: OE1XYZ") == "OE1XYZ"


# ---------------------------------------------------------------------------
# on_channel_state — "Connect request" must map to "calling", not "connected"
# ---------------------------------------------------------------------------

class TestOnChannelState:

    def _mode_with_spy(self):
        mode = HFPacketMode()
        calls = []
        mode.on_channel_state = lambda ch, state, partner: calls.append(
            (ch, state, partner)
        )
        return mode, calls

    def test_connected_to_maps_connected(self):
        mode, calls = self._mode_with_spy()
        mode._handle_link_msg(_FakeFrame(4, "CONNECTED to OE1XYZ-5"))
        assert calls == [(4, "connected", "OE1XYZ-5")]

    def test_connect_request_maps_calling_not_connected(self):
        mode, calls = self._mode_with_spy()
        mode._handle_link_msg(_FakeFrame(3, "Connect request: OE1XYZ"))
        assert calls == [(3, "calling", "OE1XYZ")]

    def test_disconnected_frees_channel(self):
        mode, calls = self._mode_with_spy()
        mode._handle_link_msg(_FakeFrame(4, "DISCONNECTED"))
        assert calls == [(4, "free", "")]

    def test_busy_frees_channel(self):
        mode, calls = self._mode_with_spy()
        mode._handle_link_msg(_FakeFrame(2, "OE1XYZ busy"))
        assert calls == [(2, "free", "")]

    def test_colon_connected_form_extracts_partner(self):
        mode, calls = self._mode_with_spy()
        mode._handle_link_msg(_FakeFrame(4, "CONNECTED to: OE1XYZ-5"))
        assert calls == [(4, "connected", "OE1XYZ-5")]
