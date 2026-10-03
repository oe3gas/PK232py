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

from pk232py.comm.frame import FrameKind, build_command
from pk232py.modes.packet_hf import HFPacketMode, _extract_partner
from pk232py.modes.packet_vhf import VHFPacketMode


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

    # -----------------------------------------------------------------
    # P55.A — with CONSTAMP/DAGSTAMP both ON (params_uploader.py's
    # default), a real message is prefixed with the TNC's own
    # "DD-Mon-YY HH:MM:SS" - whose own two colons sit AHEAD of the one
    # that actually marks the callsign. Reproduced 26.09.2026: MHEARD's
    # Callsign column showed a fragment of the embedded timestamp
    # instead of the real callsign, because the old code split on the
    # FIRST colon in the whole string, landing inside "HH:MM:SS".
    # -----------------------------------------------------------------

    def test_disconnected_with_tnc_daystamp_and_constamp_prefix(self):
        assert _extract_partner(
            "*** 25-Sep-26 21:04:36 DISCONNECTED: OE3TEC-1 ***"
        ) == "OE3TEC-1"

    def test_connected_with_tnc_daystamp_and_constamp_prefix(self):
        # The " to " marker is found before any colon check runs, so
        # this shape was never actually broken - kept here anyway to
        # document that both message shapes are covered under the
        # same real-world prefix.
        assert _extract_partner(
            "*** 25-Sep-26 21:04:36 CONNECTED to OE3TEC ***"
        ) == "OE3TEC"

    def test_connect_request_with_tnc_daystamp_and_constamp_prefix(self):
        assert _extract_partner(
            "*** 25-Sep-26 21:04:36 Connect request: OE1XYZ ***"
        ) == "OE1XYZ"


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
        # P50 Teil E: DISCONNECTED now passes the extracted partner through
        # (ChannelBar.set_channel_state() already discards it when state
        # is "free" - this is for MainWindow's MHEARD hook). Real TRM
        # 4.4.4 form always has the callsign after "DISCONNECTED: ".
        mode, calls = self._mode_with_spy()
        mode._handle_link_msg(_FakeFrame(4, "DISCONNECTED: OE3TEC-1"))
        assert calls == [(4, "free", "OE3TEC-1")]

    def test_busy_frees_channel(self):
        # P50 Teil E: "<callsign> busy" carries a real callsign - now
        # passed through (see test_disconnected_frees_channel above).
        mode, calls = self._mode_with_spy()
        mode._handle_link_msg(_FakeFrame(2, "OE1XYZ busy"))
        assert calls == [(2, "free", "OE1XYZ")]

    def test_colon_connected_form_extracts_partner(self):
        mode, calls = self._mode_with_spy()
        mode._handle_link_msg(_FakeFrame(4, "CONNECTED to: OE1XYZ-5"))
        assert calls == [(4, "connected", "OE1XYZ-5")]

    def test_retry_count_exceeded_frees_channel(self):
        # P44 - this used to fall through to nothing at all: a chip left
        # CALLING with no TNC message ever freeing it again (observed on
        # the device 25.09.2026, chip stuck amber while the status pill
        # already read DISCONNECTED). ChannelBar.set_channel_state() is
        # what turns a CALLING->FREE transition into the brief CH_FAILED
        # flash (P44 Teil A); this only needs to confirm the message
        # reaches on_channel_state at all, same as busy/DISCONNECTED do.
        mode, calls = self._mode_with_spy()
        mode._handle_link_msg(_FakeFrame(3, "Retry count exceeded"))
        assert calls == [(3, "free", "")]


# ---------------------------------------------------------------------------
# get_init_frames() — MAXFRAME/SLOTTIME reset from the HF config (T112, P18.1)
# ---------------------------------------------------------------------------

class TestGetInitFrames:

    def test_default_maxframe_and_slottime(self):
        frames = HFPacketMode().get_init_frames()
        assert build_command(b'MX', b'1') in frames
        assert build_command(b'SL', b'30') in frames

    def test_constructor_defaults_derive_from_hf_packet_config(self):
        # P19.3: one source of truth - if HFPacketConfig's own defaults
        # ever change, this catches HFPacketMode silently going stale
        # instead of tracking them.
        from pk232py.config import HFPacketConfig

        mode = HFPacketMode()
        assert mode.maxframe == HFPacketConfig.maxframe
        assert mode.slottime == HFPacketConfig.slottime

    def test_configured_maxframe_and_slottime(self):
        frames = HFPacketMode(maxframe=2, slottime=20).get_init_frames()
        assert build_command(b'MX', b'2') in frames
        assert build_command(b'SL', b'20') in frames
        # Neither the default nor VHF's own values must sneak in.
        assert build_command(b'MX', b'1') not in frames
        assert build_command(b'MX', b'4') not in frames
        assert build_command(b'SL', b'10') not in frames
        assert build_command(b'SL', b'30') not in frames

    def test_vhf_sequence_unaffected(self):
        # VHFPacketMode deliberately does not inherit HFPacketMode's
        # get_init_frames() - confirm the VH Y / VH N split still holds
        # after the HF side gained MX/SL.
        vhf = VHFPacketMode()
        activate = vhf.get_activate_frames()
        init = vhf.get_init_frames()
        assert build_command(b'VH', b'Y') in activate
        assert build_command(b'VH', b'N') not in init
        assert build_command(b'MX', b'4') in init
        assert build_command(b'SL', b'10') in init


# ---------------------------------------------------------------------------
# P73 A - MONITOR from the configuration instead of "MN Y"
# ---------------------------------------------------------------------------

class TestMonitorFromConfig:
    """MN Y makes the TNC set MONITOR 4 (STABO manual, UBIT 1 OFF) - the
    operator's MONITOR 6 was lost after every mode switch."""

    def test_hf_sends_the_configured_monitor(self):
        frames = HFPacketMode(monitor=6).get_init_frames()
        assert build_command(b'MN', b'6') in frames
        assert build_command(b'MN', b'Y') not in frames

    def test_vhf_sends_the_configured_monitor(self):
        frames = VHFPacketMode(monitor=6).get_init_frames()
        assert build_command(b'MN', b'6') in frames
        assert build_command(b'MN', b'Y') not in frames

    def test_monitor_zero_is_sent_too(self):
        # 0 is a value, not "unset" - a falsy check would drop it.
        assert build_command(b'MN', b'0') in HFPacketMode(monitor=0).get_init_frames()

    def test_default_is_the_config_default(self):
        from pk232py.config import HFPacketConfig
        assert HFPacketMode().monitor == HFPacketConfig.monitor
