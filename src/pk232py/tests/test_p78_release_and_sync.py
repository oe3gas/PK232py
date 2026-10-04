# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""P78: the release without a banner, verbose changes into the configuration,
one way for MONITOR (behaviour tests; they only use modules that existed before
P78, so against the old code they fail by assertion).

Operator finding T162 (device B, 03.10.2026): Host Mode, VHF Packet, MONITOR 4 -> 6
in the parameter mask gave "MONITOR not verified for Host Mode on unknown" (the
TNC was already awake, no banner); verbose `MONITOR 3` was overwritten by the
configuration's 6 at the next Host Mode entry.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication, QDialog

from pk232py.comm.frame import build_command
from pk232py.comm.serial_manager import SerialManager
from pk232py.tests.test_main_window_params_apply import _Serial
from pk232py.ui.dialogs.params_hf import PacketParamsDialog
from pk232py.ui.main_window import MainWindow

_app = QApplication.instance() or QApplication([])


class _AwakeSerial(_Serial):
    """A TNC that was already awake: no banner, so no release yet."""

    def __init__(self, answers, ex_answer=b"EX\x07"):
        super().__init__(answers, release=None)
        self.answers[(b"EX", b"")] = ex_answer

    def set_inferred_release(self, release, source="inferred"):
        self.tnc_release = release
        self.tnc_release_source = source


@pytest.fixture
def win(monkeypatch):
    w = MainWindow()
    w.log = []
    w.problems = []
    monkeypatch.setattr(w, "_log_monitor", lambda text, raw=b"": w.log.append(text))
    monkeypatch.setattr(w, "_show_params_not_taken",
                        lambda label, lines: w.problems.append((label, lines)))
    return w


# ---------------------------------------------------------------------------
# A - release without a banner
# ---------------------------------------------------------------------------

class TestVerboseFingerprint:
    def _manager(self, monkeypatch, reply):
        sm = SerialManager()
        sent = []
        monkeypatch.setattr(SerialManager, "is_connected", property(lambda s: True))
        monkeypatch.setattr(
            sm, "_write_verbose_wait_text",
            lambda data, timeout=5.0: (sent.append(data) or (True, reply)))
        return sm, sent

    def test_what_answer_gives_01_aug_91_inferred(self, monkeypatch):
        sm, sent = self._manager(monkeypatch, b"EXPERT\r\n?What?\r\ncmd:")
        assert sm.tnc_release is None
        sm.probe_release_verbose()
        assert sm.tnc_release == "01.AUG.91"
        assert sm.tnc_release_source == "inferred"
        assert sent == [b"EXPERT\r\n"]                 # exactly ONE query

    def test_a_value_gives_13_sep_95(self, monkeypatch):
        sm, _ = self._manager(monkeypatch, b"EXPERT\r\nEXPert    OFF\r\ncmd:")
        sm.probe_release_verbose()
        assert (sm.tnc_release, sm.tnc_release_source) == ("13.SEP.95", "inferred")

    def test_the_banner_wins_and_nothing_is_sent(self, monkeypatch):
        sm, sent = self._manager(monkeypatch, b"?What?")
        sm._tnc_banner = b"AEA PK-232MBX  Release 30.12.1988  Ver. 7.1"
        sm.probe_release_verbose()
        assert (sm.tnc_release, sm.tnc_release_source) == ("30.12.1988", "banner")
        assert sent == []

    def test_unknown_answer_stays_unknown_and_is_asked_only_once(self, monkeypatch):
        sm, sent = self._manager(monkeypatch, b"cmd:")
        sm.probe_release_verbose()
        sm.probe_release_verbose()
        assert sm.tnc_release is None and len(sent) == 1


class TestHostModeParametersWithoutBanner:
    def test_monitor_6_is_sent_in_host_mode_although_no_banner_was_seen(self, win):
        win._serial = _AwakeSerial({(b"MN", b"6"): b"MN\x00", (b"MN", b""): [b"MN4", b"MN6"]})
        win._app_config.hf_packet.monitor = 4

        def fake_exec(dlg):
            dlg._config.monitor = 6
            return QDialog.DialogCode.Accepted
        PacketParamsDialog.exec = fake_exec
        try:
            win._on_params_hf_packet()
        finally:
            del PacketParamsDialog.exec
        sent = win._serial.writes
        assert build_command(b"MN", b"6") in sent
        assert win._serial.tnc_release == "01.AUG.91"
        assert "[SYS] MONITOR  4 -> 6  ok" in win.log
        assert win.problems == []

    def test_the_toolbar_shows_the_inferred_release(self, win):
        win._show_release("01.AUG.91", "inferred")
        assert win._lbl_firmware.text() == "Release 01.AUG.91 (inferred)"
        win._show_release("13.SEP.95", "banner")
        assert win._lbl_firmware.text() == "Release 13.SEP.95"


# ---------------------------------------------------------------------------
# B - verbose was/now answers update the configuration
# ---------------------------------------------------------------------------

class TestVerboseAnswersReachTheConfiguration:
    def test_verbose_monitor_3_is_taken_and_survives_the_next_host_mode_entry(self, win):
        win._app_config.hf_packet.monitor = 6
        win._on_vt_rx_data(b"MOnitor    was 6 (seq, P/F + all)\r\n"
                           b"MOnitor    now 3 (UA DM C I UI)\r\ncmd:")
        assert win._app_config.hf_packet.monitor == 3
        text = win._vt_display.toPlainText()
        assert "[SYS] MONITOR 3 taken into the parameters" in text
        frames = win._build_mode_instance("VHF Packet").get_init_frames()
        assert build_command(b"MN", b"3") in frames          # (before P78: MN6)
        assert build_command(b"MN", b"6") not in frames

    def test_the_configuration_is_saved_once_and_not_again_for_the_same_value(
            self, win, monkeypatch):
        saves = []
        monkeypatch.setattr(win._config_mgr, "save", lambda: saves.append(1))
        win._app_config.hf_packet.monitor = 6
        chunk = (b"MOnitor    was 6 (x)\r\nMOnitor    now 3 (x)\r\ncmd:")
        win._on_vt_rx_data(chunk)
        win._on_vt_rx_data(chunk)                  # the same answer again
        assert len(saves) == 1

    def test_band_values_follow_the_active_band(self, win, monkeypatch):
        monkeypatch.setattr(type(win._modes), "current_mode_name",
                            property(lambda self: "VHF Packet"))
        win._on_vt_rx_data(b"MAXframe was 4\r\nMAXframe now 5\r\ncmd:")
        assert win._app_config.hf_packet.vhf_maxframe == 5
        assert win._app_config.hf_packet.maxframe == 1            # HF value untouched

    def test_a_parameter_without_a_config_field_is_only_reported(self, win):
        win._on_vt_rx_data(b"CFrom     was all\r\nCFrom     now none\r\ncmd:")
        assert any("CFROM" in line and "not taken" in line for line in win.log)

    def test_text_the_tnc_only_reformats_is_not_a_change(self, win, monkeypatch):
        saves = []
        monkeypatch.setattr(win._config_mgr, "save", lambda: saves.append(1))
        win._app_config.hf_packet.unproto = "APZ232 VIA A,B"
        win._on_vt_rx_data(b"Unproto   was CQ\r\nUnproto   now APZ232 via A, B\r\ncmd:")
        assert saves == []


# ---------------------------------------------------------------------------
# C - one way for MONITOR
# ---------------------------------------------------------------------------

class TestMonitorSelector:
    def _vhf(self, win):
        screen = win._opmode_screens["VHF Packet"]
        win._opmode_stack.setCurrentWidget(screen)
        return screen

    def test_selector_changes_the_config_and_goes_through_param_applier(self, win):
        win._serial = _Serial({(b"MN", b"6"): b"MN\x00", (b"MN", b""): [b"MN4", b"MN6"]})
        win._app_config.hf_packet.monitor = 4
        screen = self._vhf(win)
        screen.combo_monitor.blockSignals(True)
        screen.combo_monitor.setCurrentText("6")
        screen.combo_monitor.blockSignals(False)
        win._on_packet_monitor_changed(6)
        assert win._app_config.hf_packet.monitor == 6
        # ParamApplier's exchange (P82a): the TNC's value, ONE set, ONE read-back, nothing twice.
        assert win._serial.writes == [build_command(b"MN", b""), build_command(b"MN", b"6"),
                                      build_command(b"MN", b"")]
        assert "[SYS] MONITOR  4 -> 6  ok" in win.log

    def test_offline_the_value_is_saved_and_reported(self, win):
        win._serial = _Serial({})
        win._serial.is_connected = False
        win._app_config.hf_packet.monitor = 4
        screen = self._vhf(win)
        screen.combo_monitor.blockSignals(True)
        screen.combo_monitor.setCurrentText("5")
        screen.combo_monitor.blockSignals(False)
        win._on_packet_monitor_changed(5)
        assert win._app_config.hf_packet.monitor == 5
        assert win._serial.writes == []
        assert any("MONITOR" in line and "not connected" in line for line in win.log)

    def test_selector_shows_the_configured_value(self, win):
        win._app_config.hf_packet.monitor = 6
        win._sync_monitor_selectors()
        assert win._opmode_screens["VHF Packet"].combo_monitor.currentText() == "6"
        assert win._opmode_screens["HF Packet"].combo_monitor.currentText() == "6"


# ---------------------------------------------------------------------------
# D - the dialog title
# ---------------------------------------------------------------------------

class TestNotTakenDialogTitle:
    def test_title_says_packet(self, monkeypatch):
        w = MainWindow()
        titles = []
        monkeypatch.setattr(
            "pk232py.ui.main_window.QMessageBox.warning",
            lambda parent, title, text, *a, **k: titles.append(title))
        w._show_params_not_taken("Packet", ["X"])
        assert titles == ["Packet parameters not taken by the TNC"]

    def test_the_packet_dialog_passes_Packet_as_the_label(self, win, monkeypatch):
        labels = []
        monkeypatch.setattr(win, "_apply_changed_params",
                            lambda before, label: labels.append(label))
        monkeypatch.setattr(PacketParamsDialog, "exec",
                            lambda dlg: QDialog.DialogCode.Accepted)
        win._on_params_hf_packet()
        assert labels == ["Packet"]
