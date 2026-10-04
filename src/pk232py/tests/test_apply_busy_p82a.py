# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""P82a (T169) - ParamApplier after OK in a parameter dialog.

* The TNC's value is READ before anything is sent; equal -> ok, nothing sent.
* The starting value in every message is the TNC's real one (picture: "AX25L2V2
  OFF -> ON rejected by TNC: $09 (TNC still Y)" while the TNC held Y).
* $09 / "?not while connected" is not an error: the caller defers the parameter
  like P81 (notice in MON and status bar, "TNC differs", catch-up after a CO
  round reports every channel free).
"""

from __future__ import annotations

import copy
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from pk232py.comm.param_applier import ApplyResult, ParamApplier, format_result
from pk232py.config import AppConfig
from pk232py.ui.main_window import MainWindow

_app = QApplication.instance() or QApplication([])

B = "01.AUG.91"


class Tnc:
    """ParamTransport on a dict: the TNC's values, and 'busy' = refuses sets."""

    def __init__(self, mode="host", values=None, busy=False):
        self._mode = mode
        self.values = dict(values or {})        # verbose style: "ON"/"OFF"/"10"
        self.busy = busy
        self.sent: list = []

    def mode(self):
        return self._mode

    def release(self):
        return B

    def host_exchange(self, mnemonic, args):
        if mnemonic != b"AV":
            return None
        if args == b"":
            return b"AV" + (b"Y" if self.values.get("AX25L2V2") == "ON" else b"N")
        self.sent.append(("host", mnemonic, args))
        if self.busy:
            return b"AV\x09"
        self.values["AX25L2V2"] = "ON" if args == b"Y" else "OFF"
        return b"AV\x00"

    def verbose_set(self, name, value):
        self.sent.append(("vset", name, value))
        if self.busy:
            return "?not while connected\r\ncmd:"
        self.values[name] = value
        return f"{name} now {value}\r\ncmd:"

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


def ax25_pair(before_value: bool, after_value: bool):
    before = AppConfig()
    after = copy.deepcopy(before)
    before.hf_packet.ax25l2v2 = before_value
    after.hf_packet.ax25l2v2 = after_value
    return before, after


class TestApplierReadsFirst:
    def test_host_value_already_right_sends_nothing(self):
        t = Tnc(values={"AX25L2V2": "ON"})
        (r,) = ParamApplier(t).apply(*ax25_pair(False, True))
        assert t.sent == []
        assert r.ok and r.reason == "already set" and not r.sent
        assert format_result(r) == "AX25L2V2  ON  already set in the TNC"

    def test_verbose_value_already_right_sends_nothing(self):
        t = Tnc(mode="verbose", values={"AX25L2V2": "ON"})
        (r,) = ParamApplier(t).apply(*ax25_pair(False, True))
        assert t.sent == [] and r.ok and r.reason == "already set"

    def test_the_starting_value_is_what_the_tnc_holds(self):
        t = Tnc(values={"AX25L2V2": "OFF"})
        (r,) = ParamApplier(t).apply(*ax25_pair(False, True))
        assert r.ok and r.was == "OFF"
        assert format_result(r) == "AX25L2V2  OFF -> ON  ok"

    def test_the_starting_value_is_the_tnc_value_even_if_the_old_config_said_otherwise(self):
        # configuration: USERS 1 -> 10, but the TNC really holds 3
        t = Tnc(mode="verbose", values={"USERS": "3"})
        before = AppConfig()
        after = copy.deepcopy(before)
        before.hf_packet.users, after.hf_packet.users = 1, 10
        (r,) = ParamApplier(t).apply(before, after)
        assert r.ok and r.was == "3"
        assert format_result(r) == "USERS  3 -> 10  ok"

    def test_a_refusal_quotes_the_tnc_value_as_it_is(self):
        t = Tnc(values={"AX25L2V2": "OFF"}, busy=True)
        (r,) = ParamApplier(t).apply(*ax25_pair(False, True))
        assert not r.ok and r.busy
        assert format_result(r) == "AX25L2V2  OFF -> ON  rejected by TNC: $09   (TNC still N)"


class TestBusyFlag:
    def test_host_09_is_busy(self):
        (r,) = ParamApplier(Tnc(values={"AX25L2V2": "OFF"}, busy=True)).apply(*ax25_pair(False, True))
        assert r.busy

    def test_verbose_not_while_connected_is_busy(self):
        (r,) = ParamApplier(Tnc(mode="verbose", values={"AX25L2V2": "OFF"}, busy=True)).apply(
            *ax25_pair(False, True))
        assert r.busy and not r.ok

    def test_another_rejection_is_not_busy(self):
        t = Tnc(mode="verbose", values={"AX25L2V2": "OFF"})
        t.verbose_set = lambda n, v: "?Bad\r\ncmd:"
        (r,) = ParamApplier(t).apply(*ax25_pair(False, True))
        assert not r.ok and not r.busy


@pytest.fixture
def win(monkeypatch):
    w = MainWindow()
    w._serial.is_connected   # real SerialManager object, replaced below
    class Stub:
        is_connected = True
        is_host_mode = True
        has_pactor = False
        has_maildrop = True
    w._serial = Stub()
    w._modes._serial = w._serial
    w._serial.send_channel_command = lambda ch, cmd: None
    w.lines, w.dialogs = [], []
    monkeypatch.setattr(w, "_log_monitor", w.lines.append)
    monkeypatch.setattr(w, "_show_params_not_taken", lambda label, lines: w.dialogs.append(lines))
    w._app_config.hf_packet.ax25l2v2 = True
    return w


def use(win, monkeypatch, tnc):
    monkeypatch.setattr(win, "_param_transport", lambda: tnc)


def changed_before(win):
    before = copy.deepcopy(win._app_config)
    before.hf_packet.ax25l2v2 = False
    return before


class TestBusyIsDeferredLikeP81:
    def test_no_dialog_the_name_is_deferred_and_shown(self, win, monkeypatch):
        use(win, monkeypatch, Tnc(values={"AX25L2V2": "OFF"}, busy=True))
        win._apply_changed_params(changed_before(win), "Packet")
        assert win.dialogs == []
        assert win._deferred_params == {"AX25L2V2"}
        assert win._tnc_unapplied == {"AX25L2V2"}
        assert not win._sb_differs.isHidden()
        assert any("1 parameters deferred until all connections are closed: AX25L2V2" in l
                   for l in win.lines)

    def test_the_notice_reaches_mon_and_the_status_bar_in_a_packet_mode(self, win, monkeypatch):
        use(win, monkeypatch, Tnc(values={"AX25L2V2": "OFF"}, busy=True))
        monkeypatch.setattr(type(win._modes), "current_mode_name",
                            property(lambda self: "VHF Packet"))
        win._apply_changed_params(changed_before(win), "Packet")
        mon = win._opmode_screens["VHF Packet"]._rx_docs["MON"].toPlainText()
        assert "parameters deferred until all connections are closed: AX25L2V2" in mon
        assert "AX25L2V2" in win.statusBar().currentMessage()

    def test_a_real_error_still_opens_the_dialog(self, win, monkeypatch):
        t = Tnc(mode="verbose", values={"AX25L2V2": "OFF"})
        t.verbose_set = lambda n, v: "?Bad\r\ncmd:"
        win._serial.is_host_mode = False
        win._serial.verbose_confirmed = True
        use(win, monkeypatch, t)
        win._apply_changed_params(changed_before(win), "Packet")
        assert len(win.dialogs) == 1 and win._deferred_params == set()

    def test_caught_up_after_the_co_round_reports_all_free(self, win, monkeypatch):
        tnc = Tnc(values={"AX25L2V2": "OFF"}, busy=True)
        use(win, monkeypatch, tnc)
        win._link_table.on_verbose_cstatus({1: (False, "", "OE3GAS-1")})
        win._apply_changed_params(changed_before(win), "Packet")
        assert win._deferred_params == {"AX25L2V2"}
        # the link ends; the TNC accepts again; the CO round confirms
        tnc.busy = False
        win._link_table.on_host_link_message(1, "*** DISCONNECTED: OE3GAS-1 ***")
        assert not win._deferred_timer.isActive()           # CO first, not the message
        for ch in range(10):
            win._on_mode_link_status(0x40 | ch, b"CO00000")
        assert win._deferred_timer.isActive()
        win._deferred_timer.stop()
        win._apply_deferred_params()
        assert tnc.values["AX25L2V2"] == "ON"
        assert win._deferred_params == set() and win._tnc_unapplied == set()
        assert any("OFF -> ON  ok" in l for l in win.lines)
