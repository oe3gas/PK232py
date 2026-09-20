# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Unit tests for pk232py.modes.packet_hf.

Covers:
  - _extract_partner() — callsign extraction from $5x link-message text,
                          including the colon-before-callsign variant
"""

from __future__ import annotations

from pk232py.modes.packet_hf import _extract_partner


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
