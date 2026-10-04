# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""P76: a bell when a connection is established (switchable under
Configure -> Appearance).

The CONNECTED *event* is not the CONNECTED *state*: only a link message
($5n / '*** CONNECTED to') rings, never the reconciliation that follows a
verbose<->Host Mode switch (CO answers, CSTATUS)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from pk232py.comm.link_status import LinkStatus
from pk232py.comm.link_table import LinkTable
from pk232py.config import AppConfig, AppearanceConfig, ConfigManager
from pk232py.ui.main_window import MainWindow

_app = QApplication.instance() or QApplication([])


def _table():
    t = LinkTable()
    events: list = []
    t.subscribe_events(lambda ch, ev, partner: events.append((ch, ev, partner)))
    return t, events


class TestLinkTableEvent:
    def test_host_link_message_gives_one_connected_event(self):
        t, events = _table()
        t.on_host_link_message(1, "*** CONNECTED to OE3GAS-1")
        assert events == [(1, "connected", "OE3GAS-1")]

    def test_verbose_line_gives_one_event(self):
        t, events = _table()
        t.on_verbose_line("*** CONNECTED to OE3GAS-1")
        assert events == [(0, "connected", "OE3GAS-1")]

    def test_outgoing_call_then_connected_rings(self):
        t, events = _table()
        t.on_local_connect_attempt(2, "OE3GAS-1")      # CALLING is not a connect
        assert events == []
        t.on_host_link_message(2, "*** CONNECTED to OE3GAS-1")
        assert events == [(2, "connected", "OE3GAS-1")]

    def test_reconciliation_never_rings(self):
        t, events = _table()
        t.on_link_status(LinkStatus(channel=1, connected=True, partner="OE3GAS-1"))
        t.on_verbose_cstatus({0: (True, "IO CONNECTED to X", "X")})
        assert events == []
        # ... and the table still knows the channels are connected.
        assert t.channels[1].state == "connected"
        assert t.channels[0].state == "connected"

    def test_known_channel_after_a_mode_switch_is_silent(self):
        t, events = _table()
        t.on_host_link_message(1, "*** CONNECTED to OE3GAS-1")
        events.clear()
        t.mark_unconfirmed()
        t.on_link_status(LinkStatus(channel=1, connected=True, partner="OE3GAS-1"))
        assert events == []

    def test_second_connected_message_for_a_connected_channel_is_silent(self):
        t, events = _table()
        t.on_host_link_message(1, "*** CONNECTED to OE3GAS-1")
        t.on_host_link_message(1, "*** CONNECTED to OE3GAS-1")
        assert len(events) == 1

    def test_connected_message_while_unconfirmed_is_silent(self):
        t, events = _table()
        t.on_host_link_message(1, "*** CONNECTED to OE3GAS-1")
        events.clear()
        t.mark_unconfirmed()
        t.on_host_link_message(1, "*** CONNECTED to OE3GAS-1")
        assert events == []

    def test_reconnect_after_disconnect_rings_again(self):
        t, events = _table()
        t.on_host_link_message(1, "*** CONNECTED to OE3GAS-1")
        t.on_host_link_message(1, "*** DISCONNECTED")
        t.on_host_link_message(1, "*** CONNECTED to OE3GAS-1")
        # P81 added the "closed" event; the bell only cares about "connected".
        assert len([e for e in events if e[1] == "connected"]) == 2


class TestConfig:
    def test_default_is_on(self):
        assert AppearanceConfig().connect_bell is True

    def test_ini_without_key_is_true(self, tmp_path):
        ini = tmp_path / "pk232py.ini"
        ini.write_text("[Appearance]\ntheme = dark\n", encoding="utf-8")
        mgr = ConfigManager(ini)
        mgr.load()
        assert mgr.app.appearance.connect_bell is True

    def test_ini_roundtrip(self, tmp_path):
        ini = tmp_path / "pk232py.ini"
        mgr = ConfigManager(ini)
        mgr.app.appearance.connect_bell = False
        mgr.save()
        again = ConfigManager(ini)
        again.load()
        assert again.app.appearance.connect_bell is False


@pytest.fixture
def win(monkeypatch):
    w = MainWindow()
    w.rings = 0

    def count():
        w.rings += 1
    monkeypatch.setattr(w, "_ring_connect_bell", count)
    return w


class TestMainWindow:
    def test_new_connect_rings_once(self, win):
        win._link_table.on_host_link_message(1, "*** CONNECTED to OE3GAS-1")
        assert win.rings == 1

    def test_verbose_connect_rings_once(self, win):
        win._link_table.on_verbose_line("*** CONNECTED to OE3GAS-1")
        assert win.rings == 1

    def test_co_reconciliation_is_silent(self, win):
        win._link_table.on_link_status(
            LinkStatus(channel=1, connected=True, partner="OE3GAS-1"))
        win._link_table.on_verbose_cstatus({0: (True, "IO", "OE3GAS-1")})
        assert win.rings == 0

    def test_second_message_does_not_ring_again(self, win):
        win._link_table.on_host_link_message(1, "*** CONNECTED to OE3GAS-1")
        win._link_table.on_host_link_message(1, "*** CONNECTED to OE3GAS-1")
        assert win.rings == 1

    def test_switched_off_is_silent(self, win):
        win._app_config.appearance.connect_bell = False
        win._link_table.on_host_link_message(1, "*** CONNECTED to OE3GAS-1")
        assert win.rings == 0

    def test_menu_entry_is_checkable_and_mirrors_the_config(self, win):
        act = win._act_connect_bell
        assert act.isCheckable() and act.text() == "Connect bell"
        assert act.statusTip() == "Sound a bell when a connection is established"
        assert act.isChecked() is win._app_config.appearance.connect_bell

    def test_toggle_applies_at_once_and_saves(self, win, monkeypatch):
        saves: list = []
        monkeypatch.setattr(win._config_mgr, "save", lambda: saves.append(1))
        win._act_connect_bell.setChecked(True)
        win._act_connect_bell.trigger()          # -> off
        assert win._app_config.appearance.connect_bell is False
        assert saves == [1]
        win._link_table.on_host_link_message(1, "*** CONNECTED to OE3GAS-1")
        assert win.rings == 0
        win._act_connect_bell.trigger()          # -> on
        assert win._app_config.appearance.connect_bell is True

    def test_the_bell_itself_is_application_beep(self, monkeypatch):
        w = MainWindow()
        beeps: list = []
        monkeypatch.setattr(QApplication, "beep", staticmethod(lambda: beeps.append(1)))
        w._ring_connect_bell()
        assert beeps == [1]
