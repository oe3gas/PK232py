# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""P72 Teil D: MainWindow applies the changed parameters right after OK in
a parameter dialog, shows the result, and keeps ONE "TNC differs" state.

The dialog itself is replaced by a function that changes the config and
returns Accepted (the dialogs are tested in their own files); the serial
side is a stub that records every byte written, like test_param_applier.py.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication, QDialog

from pk232py.comm.frame import FrameKind, HostFrame, build_command
from pk232py.ui.dialogs.params_hf import PacketParamsDialog
from pk232py.ui.main_window import MainWindow

_app = QApplication.instance() or QApplication([])


class _Serial(QObject):
    frame_received = pyqtSignal(object)
    is_connected = True
    is_host_mode = True
    verbose_confirmed = False
    has_pactor = False
    has_maildrop = True
    command_char = 3
    fresh_boot_defaults = False

    def __init__(self, answers, release="01.AUG.91"):
        super().__init__()
        self.tnc_release = release
        self.answers = answers
        self.writes: list = []

    def consume_fresh_boot_defaults(self):
        return False

    def send_command(self, mnemonic, args=b""):
        self.writes.append(build_command(mnemonic, args))
        reply = self.answers.get((mnemonic, args))
        if reply is not None:
            self.frame_received.emit(HostFrame(0x4F, 0xF, reply, FrameKind.CMD_RESP))
        return True

    def write_verbose(self, data):
        self.writes.append(data)
        return True

    def send_verbose_command(self, data, timeout=3.0):
        self.writes.append(data)
        return True, b""

    def query_verbose_value(self, name, timeout=3.0):
        self.writes.append(f"{name}".encode())
        return None

    def exit_host_mode(self, io_channel=None):
        self.writes.append(b"HOST OFF")


@pytest.fixture
def win(monkeypatch):
    w = MainWindow()
    w._serial = _Serial({(b"UR", b"10"): b"UR\x00", (b"UR", b""): b"UR10"})
    w.log: list = []
    w.problems: list = []
    monkeypatch.setattr(w, "_log_monitor", lambda text, raw=b"": w.log.append(text))
    monkeypatch.setattr(w, "_show_params_not_taken",
                        lambda label, lines: w.problems.append((label, lines)))
    w._app_config.hf_packet.users = 1

    def fake_exec(dlg):
        dlg._config.users = 10
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(PacketParamsDialog, "exec", fake_exec)
    return w


class TestApplyRightAfterOk:
    def test_host_mode_writes_one_host_frame_and_the_query_only(self, win):
        win._on_params_hf_packet()
        assert win._serial.writes == [bytes.fromhex("01 4F 55 52 31 30 17"),
                                      bytes.fromhex("01 4F 55 52 17")]
        assert "[SYS] USERS  1 -> 10  ok" in win.log
        assert win.problems == []
        assert win._tnc_unapplied == set()
        assert win._sb_differs.isHidden()

    def test_old_message_is_gone(self, win):
        win._on_params_hf_packet()
        assert not [m for m in win.log if "next initialisation" in m]

    def test_nothing_changed_sends_nothing(self, win, monkeypatch):
        monkeypatch.setattr(PacketParamsDialog, "exec",
                            lambda dlg: QDialog.DialogCode.Accepted)
        win._on_params_hf_packet()
        assert win._serial.writes == []


class TestTncDiffers:
    def test_rejection_sets_the_state_the_label_and_the_dialog(self, win):
        win._serial.answers = {(b"UR", b"10"): b"UR\x07", (b"UR", b""): b"UR1"}
        win._on_params_hf_packet()
        assert "[SYS] USERS  1 -> 10  rejected by TNC: $07   (TNC still 1)" in win.log
        assert win._tnc_unapplied == {"USERS"}
        assert not win._sb_differs.isHidden()
        assert "USERS" in win._sb_differs.toolTip()
        assert len(win.problems) == 1 and "rejected by TNC" in win.problems[0][1][0]
        # The value stays in the configuration.
        assert win._app_config.hf_packet.users == 10

    def test_not_verified_for_this_release_is_reported_and_marks_differs(self, win, monkeypatch):
        win._serial.tnc_release = "13.SEP.95"        # UNPROTO is verified on B only

        def fake_exec(dlg):
            dlg._config.unproto = "APRS"
            return QDialog.DialogCode.Accepted
        monkeypatch.setattr(PacketParamsDialog, "exec", fake_exec)
        win._app_config.hf_packet.users = 10
        win._on_params_hf_packet()
        assert win._serial.writes == []
        assert any("UNPROTO  not verified for Host Mode on 13.SEP.95"
                   " - saved, TNC unchanged" in m for m in win.log)
        assert win._tnc_unapplied == {"UNPROTO"}

    def test_a_later_successful_attempt_clears_that_parameter(self, win):
        win._serial.answers = {(b"UR", b"10"): b"UR\x07", (b"UR", b""): b"UR1"}
        win._on_params_hf_packet()
        assert win._tnc_unapplied == {"USERS"}
        # The operator opens the dialog again and changes USERS once more.
        win._app_config.hf_packet.users = 9
        win._serial.answers = {(b"UR", b"10"): b"UR\x00", (b"UR", b""): b"UR10"}
        win._on_params_hf_packet()
        assert win._tnc_unapplied == set()
        assert win._sb_differs.isHidden()


class TestWriteLogOnly:
    """Behaviour test with NO P72 helper in the fixture (only the stub serial
    and a dialog that changes USERS): what leaves the app after OK?"""

    def test_host_mode_users_1_to_10_writes_exactly_the_set_and_query_frame(
            self, monkeypatch):
        w = MainWindow()
        sm = _Serial({(b"UR", b"10"): b"UR\x00", (b"UR", b""): b"UR10"})
        w._serial = sm
        w._app_config.hf_packet.users = 1

        def fake_exec(dlg):
            dlg._config.users = 10
            return QDialog.DialogCode.Accepted
        monkeypatch.setattr(PacketParamsDialog, "exec", fake_exec)

        w._on_params_hf_packet()

        assert sm.writes, "no frame written (the value never reaches the TNC)"
        assert sm.writes == [bytes.fromhex("01 4F 55 52 31 30 17"),
                             bytes.fromhex("01 4F 55 52 17")]


class TestActiveBand:
    """P73 B: MainWindow hands the band of the ACTIVE Packet mode to the
    applier - MAXFRAME/SLOTTIME of the other band are saved, never sent."""

    def _set_mode(self, win, monkeypatch, name):
        monkeypatch.setattr(type(win._modes), "current_mode_name",
                            property(lambda self: name))

    def _change(self, monkeypatch, **fields):
        def fake_exec(dlg):
            for k, v in fields.items():
                setattr(dlg._config, k, v)
            return QDialog.DialogCode.Accepted
        monkeypatch.setattr(PacketParamsDialog, "exec", fake_exec)

    def test_hf_maxframe_in_vhf_mode_is_not_sent(self, win, monkeypatch):
        self._set_mode(win, monkeypatch, "VHF Packet")
        win._app_config.hf_packet.users = 10
        self._change(monkeypatch, maxframe=3)
        win._on_params_hf_packet()
        assert win._serial.writes == []                       # no MX frame
        assert "[SYS] MAXFRAME (HF) saved - applies when HF Packet is selected" in win.log
        assert win._tnc_unapplied == set()                    # intended, not "TNC differs"
        assert win.problems == []
        assert win._app_config.hf_packet.maxframe == 3        # but saved

    def test_vhf_maxframe_in_vhf_mode_is_sent(self, win, monkeypatch):
        self._set_mode(win, monkeypatch, "VHF Packet")
        win._app_config.hf_packet.users = 10
        win._serial.answers = {(b"MX", b"7"): b"MX\x00", (b"MX", b""): b"MX7"}
        self._change(monkeypatch, vhf_maxframe=7)
        win._on_params_hf_packet()
        assert win._serial.writes == [build_command(b"MX", b"7"), build_command(b"MX", b"")]
        assert "[SYS] MAXFRAME  4 -> 7  ok" in win.log
