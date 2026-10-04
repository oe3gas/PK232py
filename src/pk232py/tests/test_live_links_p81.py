# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""P81 (D) - links the TNC already holds when the application starts.

The CSTATUS / VHF texts follow the real answers of T168 (device B, 04.10.2026):
channel 0 = OE3GAS-2 (QtTermTCP calling in), channel 1 = OE3GAS-1 (TinyBox).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from pk232py.comm.link_status import build_live_links
from pk232py.comm.link_table import LinkTable
from pk232py.comm.params_uploader import ParamsUploader
from pk232py.config import AppConfig
from pk232py.ui.main_window import MainWindow

_app = QApplication.instance() or QApplication([])

CSTATUS = (
    "CSTATUS\r\n"
    "Ch. 0 - IO CONNECTED to OE3GAS-2; v2\r\n"
    "Ch. 1 - CONNECTED to OE3GAS-1; v2\r\n"
    "Ch. 2 - \r\n"
    "Ch. 3 - \r\n"
    "cmd:"
)
CSTATUS_NONE = "CSTATUS\r\nCh. 0 - IO\r\nCh. 1 - \r\ncmd:"
VHF_ON = "VHF\r\nVHf       ON\r\ncmd:"
VHF_OFF = "VHF\r\nVHf       OFF\r\ncmd:"
OPMODE = "OPMODE\r\nOPmode now PACKET\r\ncmd:"


class TestBuildLiveLinks:
    def test_two_connections_on_vhf(self):
        links = build_live_links(CSTATUS, OPMODE, VHF_ON)
        assert links.connections == {0: "OE3GAS-2", 1: "OE3GAS-1"}
        assert links.mode_name == "VHF Packet"
        assert links.summary() == (
            "2 active connections found: ch0 OE3GAS-2, ch1 OE3GAS-1 (VHF Packet)")

    def test_hf_when_vhf_is_off(self):
        links = build_live_links(CSTATUS, OPMODE, VHF_OFF)
        assert links.mode_name == "HF Packet"

    def test_band_is_not_guessed_when_vhf_is_unreadable(self):
        links = build_live_links(CSTATUS, OPMODE, "VHF\r\n?What?\r\ncmd:")
        assert links.mode_name is None
        assert "(" not in links.summary()

    def test_no_connections(self):
        links = build_live_links(CSTATUS_NONE, OPMODE, VHF_ON)
        assert links.connections == {}
        assert links.mode_name is None
        assert links.summary() == "no active connections"

    def test_one_connection_is_singular(self):
        text = "Ch. 0 - IO CONNECTED to OE3GAS-2; v2\r\n"
        assert build_live_links(text, "", VHF_ON).summary().startswith(
            "1 active connection found:")


class TestSerialManagerQuery:
    def test_query_live_links_asks_the_three_queries(self, monkeypatch):
        from pk232py.comm.serial_manager import SerialManager
        sm = SerialManager()
        monkeypatch.setattr(SerialManager, "is_connected", property(lambda s: True))
        asked = []
        answers = {b"CSTATUS\r\n": CSTATUS, b"OPMODE\r\n": OPMODE, b"VHF\r\n": VHF_ON}

        def fake(data, timeout=5.0):
            asked.append(data)
            return True, answers[data].encode()

        monkeypatch.setattr(sm, "_write_verbose_wait_text", fake)
        links = sm.query_live_links()
        assert asked == [b"CSTATUS\r\n", b"OPMODE\r\n", b"VHF\r\n"]
        assert links.mode_name == "VHF Packet"

    def test_banner_flag_is_public(self):
        from pk232py.comm.serial_manager import SerialManager
        sm = SerialManager()
        assert sm.banner_seen_this_init is False
        sm._banner_this_init = True
        assert sm.banner_seen_this_init is True


class TestLinkTableClosedEvent:
    def _table(self):
        t = LinkTable()
        events = []
        t.subscribe_events(lambda ch, ev, partner: events.append(ev))
        t.on_verbose_cstatus({0: (True, "", "A-1"), 1: (False, "", "B-1")})
        return t, events

    def test_fires_when_the_last_connection_ends(self):
        t, events = self._table()
        t.on_host_link_message(0, "*** DISCONNECTED: A-1 ***")
        assert "closed" not in events          # channel 1 still up
        t.on_host_link_message(1, "*** DISCONNECTED: B-1 ***")
        assert events == ["closed"]

    def test_reconciliation_is_not_a_connect_event(self):
        _t, events = self._table()
        assert "connected" not in events        # no bell for found links (P76)

    def test_reset_is_silent(self):
        t, events = self._table()
        t.reset()
        assert events == []


class _UploadSerial:
    is_host_mode = False
    verbose_confirmed = True
    has_pactor = True

    def __init__(self):
        self.sent: list[bytes] = []

    def write_verbose_wait(self, data, timeout=5.0):
        self.sent.append(data)
        return True

    def detect_maildrop(self):
        return True


class TestUploaderDefer:
    def _config(self):
        cfg = AppConfig()
        cfg.hf_packet.mycall = "OE3GAS"
        return cfg

    def test_defer_holds_back_exactly_the_named_commands(self):
        serial = _UploadSerial()
        up = ParamsUploader(serial, self._config())
        up.upload(defer=("MYCALL", "AX25L2V2"))
        names = [c.split()[0] for c in serial.sent]
        assert b"MYCALL" not in names and b"AX25L2V2" not in names
        assert b"PACLEN" in names and b"USERS" in names
        assert up.deferred_names == ["MYCALL", "AX25L2V2"]

    def test_default_uploads_everything(self):
        serial = _UploadSerial()
        up = ParamsUploader(serial, self._config())
        up.upload()
        names = [c.split()[0] for c in serial.sent]
        assert b"MYCALL" in names and b"AX25L2V2" in names
        assert up.deferred_names == []

    def test_nocall_has_nothing_to_defer(self):
        serial = _UploadSerial()
        up = ParamsUploader(serial, AppConfig())    # MYCALL stays NOCALL
        up.upload(defer=("MYCALL", "AX25L2V2"))
        assert up.deferred_names == ["AX25L2V2"]

    def test_verify_skips_a_deferred_mycall(self):
        class Q(_UploadSerial):
            def query_verbose_value(self, name, timeout=3.0):
                return {"MYCALL": "OLDCALL", "PACLEN": "128", "MAXFRAME": "1"}.get(name)
        cfg = self._config()
        cfg.hf_packet.paclen, cfg.hf_packet.maxframe = 128, 1
        up = ParamsUploader(Q(), cfg)
        up.upload(defer=("MYCALL",))
        assert up.verify() == (2, 2)     # MYCALL is not applicable while deferred


class _LiveSerial(_UploadSerial):
    """Stub SerialManager for MainWindow._run_param_upload()."""
    is_connected = True
    fresh_boot_defaults = False
    banner_seen_this_init = False

    def __init__(self, links):
        super().__init__()
        self._links = links
        self.queries = 0

    def query_live_links(self):
        self.queries += 1
        return self._links

    def consume_fresh_boot_defaults(self):
        return False


@pytest.fixture
def win(monkeypatch):
    w = MainWindow()
    w._app_config.hf_packet.mycall = "OE3GAS"
    w._config.fast_init = False
    w._connect_mode = "verbose"
    beeps = []
    monkeypatch.setattr(QApplication, "beep", staticmethod(lambda: beeps.append(1)))
    w.beeps = beeps
    yield w


def _run(w, links, banner=False):
    stub = _LiveSerial(links)
    stub.banner_seen_this_init = banner
    w._serial = stub
    w._live_link_check_pending = True
    w._run_param_upload()
    return stub


class TestStartupCheck:
    def test_links_reach_the_table_and_the_sys_line(self, win):
        stub = _run(win, build_live_links(CSTATUS, OPMODE, VHF_ON))
        ch = win._link_table.channels
        assert (ch[0].state, ch[0].partner) == ("connected", "OE3GAS-2")
        assert (ch[1].state, ch[1].partner) == ("connected", "OE3GAS-1")
        assert win._link_table.io_channel == 0
        assert "2 active connections found: ch0 OE3GAS-2, ch1 OE3GAS-1 (VHF Packet)" \
            in win._vt_display.toPlainText()
        assert stub.queries == 1

    def test_banner_means_no_check(self, win):
        stub = _run(win, build_live_links(CSTATUS, OPMODE, VHF_ON), banner=True)
        assert stub.queries == 0
        assert all(c.state == "free" for c in win._link_table.channels)

    def test_check_runs_once_per_init(self, win):
        stub = _run(win, build_live_links(CSTATUS_NONE, OPMODE, VHF_ON))
        win._run_param_upload()           # e.g. the Ctrl+H upload path
        assert stub.queries == 1
        assert "no active connections" in win._vt_display.toPlainText()

    def test_no_bell_for_found_links(self, win):
        win._app_config.appearance.connect_bell = True
        _run(win, build_live_links(CSTATUS, OPMODE, VHF_ON))
        assert win.beeps == []

    def test_packet_mode_follows_vhf_for_the_host_mode_entry(self, win):
        _run(win, build_live_links(CSTATUS, OPMODE, VHF_ON))
        assert win._link_table.mode_name == "VHF Packet"

    def test_hf_when_vhf_is_off(self, win):
        _run(win, build_live_links(CSTATUS, OPMODE, VHF_OFF))
        assert win._link_table.mode_name == "HF Packet"

    def test_io_channel_is_the_visible_one(self, win):
        text = ("Ch. 0 - CONNECTED to OE3GAS-2; v2\r\n"
                "Ch. 1 - IO CONNECTED to OE3GAS-1; v2\r\n")
        _run(win, build_live_links(text, OPMODE, VHF_ON))
        for name in ("HF Packet", "VHF Packet"):
            assert win._opmode_screens[name].channel_bar.current() == 1


class TestDeferredParams:
    def test_mycall_and_ax25l2v2_are_held_back(self, win):
        stub = _run(win, build_live_links(CSTATUS, OPMODE, VHF_ON))
        names = [c.split()[0] for c in stub.sent]
        assert b"MYCALL" not in names and b"AX25L2V2" not in names
        assert b"PACLEN" in names
        assert win._tnc_unapplied == {"MYCALL", "AX25L2V2"}
        assert not win._sb_differs.isHidden()
        text = win._vt_display.toPlainText()
        assert "2 parameters deferred until all connections are closed" in text

    def test_no_links_uploads_everything(self, win):
        stub = _run(win, build_live_links(CSTATUS_NONE, OPMODE, VHF_ON))
        names = [c.split()[0] for c in stub.sent]
        assert b"MYCALL" in names and b"AX25L2V2" in names
        assert win._tnc_unapplied == set()

    def test_caught_up_when_the_last_connection_ends(self, win, monkeypatch):
        _run(win, build_live_links(CSTATUS, OPMODE, VHF_ON))
        applied = []
        monkeypatch.setattr(win, "_apply_changed_params",
                            lambda before, label: applied.append((before, label)))
        win._link_table.on_host_link_message(0, "*** DISCONNECTED: OE3GAS-2 ***")
        win._apply_deferred_params()
        assert applied == []                       # channel 1 is still up
        win._link_table.on_host_link_message(1, "*** DISCONNECTED: OE3GAS-1 ***")
        win._deferred_timer.stop()
        win._apply_deferred_params()
        assert len(applied) == 1
        before, _label = applied[0]
        changed = ParamsUploader.changed_values(before, win._app_config)
        assert {n for n, _v in changed} == {"MYCALL", "AX25L2V2"}

    def test_the_last_closed_event_starts_the_catch_up_timer(self, win):
        _run(win, build_live_links(CSTATUS, OPMODE, VHF_ON))
        win._link_table.on_host_link_message(0, "*** DISCONNECTED: OE3GAS-2 ***")
        win._link_table.on_host_link_message(1, "*** DISCONNECTED: OE3GAS-1 ***")
        assert win._deferred_timer.isActive()

    def test_nothing_deferred_nothing_applied(self, win, monkeypatch):
        applied = []
        monkeypatch.setattr(win, "_apply_changed_params",
                            lambda before, label: applied.append(1))
        win._apply_deferred_params()
        assert applied == []

    def test_rejected_name_stays_deferred(self, win, monkeypatch):
        _run(win, build_live_links(CSTATUS, OPMODE, VHF_ON))
        win._link_table.reset()
        # the TNC took AX25L2V2 but still refused MYCALL
        monkeypatch.setattr(win, "_apply_changed_params",
                            lambda before, label: win._tnc_unapplied.discard("AX25L2V2"))
        win._apply_deferred_params()
        assert win._deferred_params == {"MYCALL"}
