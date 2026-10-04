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

    def __init__(self, links, tnc_values=None):
        super().__init__()
        self._links = links
        self.queries = 0
        self._tnc_values = tnc_values

    def query_verbose_value(self, name, timeout=3.0):
        return None if self._tnc_values is None else self._tnc_values.get(name)

    def send_channel_command(self, channel, command):
        pass

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


def _run(w, links, banner=False, tnc_values=None):
    stub = _LiveSerial(links, tnc_values)
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

    def test_values_the_tnc_already_has_are_not_deferred(self, win):
        win._app_config.hf_packet.ax25l2v2 = True
        stub = _run(win, build_live_links(CSTATUS, OPMODE, VHF_ON),
                    tnc_values={"MYCALL": "OE3GAS", "AX25L2V2": "ON"})
        names = [c.split()[0] for c in stub.sent]
        assert b"MYCALL" not in names and b"AX25L2V2" not in names    # still not sent
        assert win._deferred_params == set()
        assert win._tnc_unapplied == set()
        assert win._sb_differs.isHidden()

    def test_only_the_differing_value_is_deferred(self, win):
        win._app_config.hf_packet.ax25l2v2 = True
        _run(win, build_live_links(CSTATUS, OPMODE, VHF_ON),
             tnc_values={"MYCALL": "OE3GAS", "AX25L2V2": "OFF"})
        assert win._deferred_params == {"AX25L2V2"}

    def test_matches_config(self):
        cfg = AppConfig()
        cfg.hf_packet.mycall = "OE3GAS"
        cfg.hf_packet.ax25l2v2 = True
        m = ParamsUploader.matches_config
        assert m(cfg, "MYCALL", "oe3gas") and not m(cfg, "MYCALL", "OLD")
        assert m(cfg, "AX25L2V2", "ON") and m(cfg, "AX25L2V2", "Y")
        assert not m(cfg, "AX25L2V2", "OFF") and not m(cfg, "AX25L2V2", None)


class _FakeTransport:
    """ParamTransport on a dict: what the TNC 'holds' and what it refuses."""

    def __init__(self, host=True, values=None, busy=False):
        self.host = host
        self.values = dict(values or {})        # name -> verbose-style value
        self.busy = busy                        # refuse sets: $09 / ?not while connected
        self.sets: list = []
        self.exchanges: list = []

    def mode(self):
        return "host" if self.host else "verbose"

    def release(self):
        return "01.AUG.91"

    def host_exchange(self, mnemonic, args):
        self.exchanges.append((mnemonic, args))
        if mnemonic != b"AV":
            return None
        if args == b"":
            return b"AV" + (b"Y" if self.values.get("AX25L2V2") == "ON" else b"N")
        if self.busy:
            return b"AV\x09"
        self.sets.append(("AX25L2V2", args))
        self.values["AX25L2V2"] = "ON" if args == b"Y" else "OFF"
        return b"AV\x00"

    def verbose_set(self, name, value):
        self.sets.append((name, value))
        if self.busy:
            return "?not while connected\r\ncmd:"
        self.values[name] = value
        return f"{name} was ...\r\n{name} now {value}\r\ncmd:"

    def verbose_query(self, name):
        return self.values.get(name)

    def verbose_query_text(self, command):
        return ""

    def in_converse(self):
        return False

    def io_channel_connected(self):
        return False

    def escape_converse(self):
        return True

    def return_to_converse(self):
        pass


@pytest.fixture
def deferred_win(win, monkeypatch):
    """A window after an init that deferred MYCALL (TNC: OLD) and AX25L2V2
    (TNC: OFF, configuration ON); every link has ended."""
    win._app_config.hf_packet.ax25l2v2 = True
    _run(win, build_live_links(CSTATUS, OPMODE, VHF_ON),
         tnc_values={"MYCALL": "OLD", "AX25L2V2": "OFF"})
    win._link_table.reset()
    lines = []
    monkeypatch.setattr(win, "_log_monitor", lines.append)
    dialogs = []
    monkeypatch.setattr(win, "_show_params_not_taken",
                        lambda label, failed: dialogs.append(failed))
    win.lines, win.dialogs = lines, dialogs
    return win


def _use(win, monkeypatch, transport):
    win._serial.is_host_mode = transport.host
    win._serial.send_channel_command = lambda ch, cmd: None
    monkeypatch.setattr(win, "_param_transport", lambda: transport)


class TestCatchUp:
    def test_host_mode_value_already_right_is_done_without_a_set(self, deferred_win, monkeypatch):
        win = deferred_win
        t = _FakeTransport(host=True, values={"AX25L2V2": "ON"})
        _use(win, monkeypatch, t)
        win._co_pending.clear()
        win._apply_deferred_params()
        assert t.sets == []
        assert "AX25L2V2" not in win._deferred_params

    def test_dialog_and_result_show_the_value_the_tnc_really_had(self, deferred_win, monkeypatch):
        win = deferred_win
        t = _FakeTransport(host=True, values={"AX25L2V2": "OFF"})
        _use(win, monkeypatch, t)
        win._apply_deferred_params()
        assert t.sets == [("AX25L2V2", b"Y")]
        assert any("AX25L2V2  OFF -> ON  ok" in line for line in win.lines)
        assert "AX25L2V2" not in win._deferred_params

    def test_the_old_value_is_the_tnc_value_not_the_inverted_config(self, deferred_win, monkeypatch):
        # T169 picture 2 said "OFF -> ON" although the TNC held Y.
        win = deferred_win
        seen = []
        monkeypatch.setattr(win, "_apply_changed_params",
                            lambda before, label, retry_on_busy=False: seen.append(before))
        _use(win, monkeypatch, _FakeTransport(host=True, values={"AX25L2V2": "OFF"}))
        win._apply_deferred_params()
        assert seen[0].hf_packet.ax25l2v2 is False          # what the TNC had
        win2_cfg = win._app_config.hf_packet
        assert win2_cfg.ax25l2v2 is True

    def test_refused_while_connected_stays_deferred_without_a_dialog(self, deferred_win, monkeypatch):
        win = deferred_win
        t = _FakeTransport(host=True, values={"AX25L2V2": "OFF"}, busy=True)
        _use(win, monkeypatch, t)
        win._apply_deferred_params()
        assert "AX25L2V2" in win._deferred_params
        assert "AX25L2V2" in win._tnc_unapplied
        assert win.dialogs == []
        t.busy = False                                     # the next confirmed "all free"
        win._apply_deferred_params()
        assert "AX25L2V2" not in win._deferred_params

    def test_mycall_waits_for_the_next_init_in_host_mode(self, deferred_win, monkeypatch):
        win = deferred_win
        t = _FakeTransport(host=True, values={"AX25L2V2": "ON"})
        _use(win, monkeypatch, t)
        win._apply_deferred_params()
        assert win._deferred_params == {"MYCALL"}
        assert all(m != b"ML" for m, _a in t.exchanges)      # ML is never touched
        notes = [line for line in win.lines if "MYCALL stays deferred" in line]
        assert len(notes) == 1 and "next initialisation" in notes[0]
        win._apply_deferred_params()
        assert len([line for line in win.lines if "MYCALL stays deferred" in line]) == 1

    def test_mycall_is_set_in_verbose_mode(self, deferred_win, monkeypatch):
        win = deferred_win
        win._app_config.hf_packet.mycall = "OE3GAS"
        t = _FakeTransport(host=False, values={"MYCALL": "OLD", "AX25L2V2": "ON"})
        _use(win, monkeypatch, t)
        win._serial._links = build_live_links(CSTATUS_NONE, OPMODE, VHF_ON)   # CSTATUS: free
        win._apply_deferred_params()
        assert ("MYCALL", "OE3GAS") in t.sets
        assert win._deferred_params == set()


class TestWhenTheCatchUpStarts:
    def test_disconnected_alone_does_not_start_it_in_host_mode(self, deferred_win, monkeypatch):
        win = deferred_win
        sent = []
        win._serial.is_host_mode = True
        win._serial.send_channel_command = lambda ch, cmd: sent.append((ch, cmd))
        win._link_table.on_verbose_cstatus({0: (True, "", "A-1")})
        win._link_table.on_host_link_message(0, "*** DISCONNECTED: A-1 ***")
        assert [ch for ch, _c in sent] == list(range(10))     # a CO round, no catch-up
        assert not win._deferred_timer.isActive()

    def test_the_last_co_answer_starts_it(self, deferred_win):
        win = deferred_win
        win._serial.send_channel_command = lambda ch, cmd: None
        win._begin_co_round()
        for ch in range(9):
            win._on_mode_link_status(0x40 | ch, b"CO00000")
        assert not win._deferred_timer.isActive()
        win._on_mode_link_status(0x40 | 9, b"CO00000")
        assert win._deferred_timer.isActive()

    def test_verbose_closed_event_uses_the_timer(self, deferred_win):
        win = deferred_win
        win._serial.is_host_mode = False
        win._link_table.on_verbose_cstatus({0: (True, "", "A-1")})
        win._link_table.on_host_link_message(0, "*** DISCONNECTED: A-1 ***")
        assert win._deferred_timer.isActive()


class TestNoticeAfterTheSwitchToHostMode:
    def test_text_goes_to_mon_and_the_status_bar(self, deferred_win):
        win = deferred_win
        win._show_deferred_notice("VHF Packet")
        mon = win._opmode_screens["VHF Packet"]._rx_docs["MON"].toPlainText()
        assert "2 parameters deferred until all connections are closed" in mon
        assert "2 parameters deferred" in win.statusBar().currentMessage()

    def test_not_in_a_non_packet_mode(self, deferred_win):
        win = deferred_win
        win._show_deferred_notice("Baudot RTTY")
        assert "deferred" not in win._opmode_screens["VHF Packet"]._rx_docs["MON"].toPlainText()

    def test_nothing_deferred_nothing_shown(self, win):
        win._show_deferred_notice("VHF Packet")
        assert "deferred" not in win._opmode_screens["VHF Packet"]._rx_docs["MON"].toPlainText()

    def test_the_host_mode_entry_calls_it(self, deferred_win, monkeypatch):
        win = deferred_win
        shown = []
        monkeypatch.setattr(win, "_show_deferred_notice", shown.append)
        monkeypatch.setattr(win._modes, "set_mode", lambda *a, **k: None)
        monkeypatch.setattr(win, "_wire_mode_callbacks", lambda *a, **k: None)
        monkeypatch.setattr(win, "_check_archive_restore_trigger", lambda *a, **k: None)
        win._serial.send_channel_command = lambda ch, cmd: None
        win._link_table.mode_name = "VHF Packet"
        win._update_host_mode_ui(True)
        assert shown == ["VHF Packet"]


class TestWakeOverlay:
    def test_hidden_for_a_quick_answer(self, win):
        win._on_init_stage("step 1: wake-up character")
        win._tick_wake_overlay(elapsed=0.3)
        assert win._wake_label.isHidden()

    def test_shown_with_seconds_and_stage_and_blinking(self, win):
        win._on_init_stage("step 2b: command character (leaving Converse?)")
        win._tick_wake_overlay(elapsed=3.2)
        label = win._wake_label
        assert not label.isHidden()
        assert "Waking up the TNC" in label.text()
        assert "3 s" in label.text()
        assert "step 2b" in label.text()
        first = label.styleSheet()
        win._tick_wake_overlay(elapsed=3.7)
        assert label.styleSheet() != first                    # the other blink phase

    def test_gone_when_the_init_is_ready_or_fails(self, win):
        win._on_init_stage("step 1: wake-up character")
        win._tick_wake_overlay(elapsed=5.0)
        win._on_verbose_mode_ready()
        assert win._wake_label.isHidden() and not win._wake_timer.isActive()
        win._on_init_stage("step 2: carriage return")
        win._tick_wake_overlay(elapsed=5.0)
        win._on_init_failed()
        assert win._wake_label.isHidden() and not win._wake_timer.isActive()

    def test_centred_inside_the_real_window(self, win):
        win.resize(1100, 760)
        win.show()
        _app.processEvents()
        win._on_init_stage("step 3: asking for Host Mode")
        win._tick_wake_overlay(elapsed=4.0)
        _app.processEvents()
        area = win.centralWidget().rect()
        geo = win._wake_label.geometry()
        assert area.contains(geo)
        assert abs(geo.center().x() - area.center().x()) <= 2
        assert abs(geo.center().y() - area.center().y()) <= 2
