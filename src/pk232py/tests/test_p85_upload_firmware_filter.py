# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""P85 - the init upload only sends commands the firmware knows.

Measured (docs/P85_Upload_Firmware_Filter_Spec.md): firmware 01.AUG.91
(device B) answers ``?What?`` to EXPERT, MYPTCALL, PTHUFF, PT200, PTOVER,
ARQTOL and MOPT; 13.SEP.95 (device A) knows all of them; 30.12.1988
(device C) is unmeasured, so it gets everything.

Needs a QApplication for the dialog tests (offscreen, see conftest).
"""

from __future__ import annotations

from PyQt6.QtWidgets import QApplication

from pk232py.comm import devices
from pk232py.comm.params_uploader import ParamsUploader
from pk232py.config import AppConfig, PACTORConfig
from pk232py.ui.dialogs.params_amtor import AMTORParamsDialog
from pk232py.ui.dialogs.params_baudot import BaudotParamsDialog
from pk232py.ui.dialogs.params_pactor import PACTORParamsDialog

_app = QApplication.instance() or QApplication([])

RELEASE_B = "01.AUG.91"
RELEASE_A = "13.SEP.95"
RELEASE_C = "30.12.1988"

# The seven names device B refuses (T155, T160, T168).
B_UNKNOWN = {"EXPERT", "MYPTCALL", "PTHUFF", "PT200", "PTOVER", "ARQTOL", "MOPT"}


class _Serial:
    """Verbose-mode stand-in that records every command written."""

    is_host_mode = False
    verbose_confirmed = True
    has_pactor = True      # no banner -> permissive True, as on the real port

    def __init__(self, release):
        self.tnc_release = release
        self.tnc_release_source = "banner" if release else None
        self.written: list[bytes] = []
        self.queried: list[str] = []

    def write_verbose_wait(self, cmd, timeout=5.0):
        self.written.append(cmd)
        return True

    def detect_maildrop(self):
        return True

    def query_verbose_value(self, name):
        self.queried.append(name)
        hf = _config().hf_packet
        return {"MYCALL": "OE3GAS", "PACLEN": str(hf.paclen),
                "MAXFRAME": str(hf.maxframe)}.get(name)


def _config() -> AppConfig:
    cfg = AppConfig()
    cfg.hf_packet.mycall = "OE3GAS"
    cfg.pactor.myptcall = "OE3GAS"      # otherwise MYPTCALL is not built at all
    return cfg


def _names(cmds) -> list[str]:
    return [c.decode("ascii").split()[0].upper() for c in cmds]


def _upload(release):
    serial = _Serial(release)
    echoed: list[str] = []
    up = ParamsUploader(serial, _config(), echo_callback=lambda t, c: echoed.append(t))
    up.upload()
    return up, serial, echoed


# ---------------------------------------------------------------- Teil A

class TestDeviceTable:

    def test_device_b_lists_the_seven_refused_names(self):
        assert devices.unknown_commands(RELEASE_B) == frozenset(B_UNKNOWN)

    def test_device_a_knows_everything(self):
        assert devices.unknown_commands(RELEASE_A) == frozenset()

    def test_device_c_is_unmeasured(self):
        assert devices.unknown_commands(RELEASE_C) is None

    def test_unknown_or_missing_release_is_none(self):
        assert devices.unknown_commands(None) is None
        assert devices.unknown_commands("99.XXX.99") is None


# ---------------------------------------------------------------- Teil B

class TestUploadFilter:

    def test_b_sends_none_of_the_refused_commands(self):
        _up, serial, _echo = _upload(RELEASE_B)
        assert not (set(_names(serial.written)) & B_UNKNOWN)

    def test_b_still_sends_what_it_knows(self):
        _up, serial, _echo = _upload(RELEASE_B)
        sent = _names(serial.written)
        for name in ("MYCALL", "PACLEN", "MAXFRAME", "UBIT"):
            assert name in sent

    def test_b_terminal_line_counts_eight_commands(self):
        # EXPERT ON + EXPERT OFF + MYPTCALL + PTHUFF + PT200 + PTOVER + ARQTOL + MOPT
        _up, _serial, echoed = _upload(RELEASE_B)
        lines = [t for t in echoed if "commands skipped" in t]
        assert len(lines) == 1
        assert lines[0].startswith(
            "[SYS] 8 commands skipped - not supported by 01.AUG.91 (EXPERT, MYPTCALL")

    def test_a_list_is_unchanged(self):
        up = ParamsUploader(_Serial(RELEASE_A), _config())
        expected = up._build_commands(has_pactor=True)
        _up, serial, echoed = _upload(RELEASE_A)
        assert serial.written == expected
        assert not any("skipped" in t for t in echoed)

    def test_unmeasured_and_missing_release_send_everything(self):
        up = ParamsUploader(_Serial(None), _config())
        expected = up._build_commands(has_pactor=True)
        for release in (None, RELEASE_C):
            _up, serial, echoed = _upload(release)
            assert serial.written == expected
            assert not any("skipped" in t for t in echoed)

    def test_command_outside_the_table_is_not_filtered(self):
        # A new "?What?" must stay visible as a new finding, never be hidden.
        assert "PACLEN" not in (devices.unknown_commands(RELEASE_B) or ())
        assert b"PACLEN" in b" ".join(_upload(RELEASE_B)[1].written)

    def test_verify_never_asks_for_a_skipped_command(self):
        up, serial, _echo = _upload(RELEASE_B)
        assert up.verify() == (3, 3)
        assert not (set(serial.queried) & B_UNKNOWN)

    def test_deferral_lists_only_commands_that_were_sent(self):
        serial = _Serial(RELEASE_B)
        up = ParamsUploader(serial, _config())
        up.upload(defer=("MYCALL", "MYPTCALL"))
        assert up.deferred_names == ["MYCALL"]


# ---------------------------------------------------------------- Teil C

class TestParameterMasks:

    def test_amtor_arqtol_greyed_on_b_with_tooltip(self):
        dlg = AMTORParamsDialog()
        dlg.set_values(arqtol=4)
        dlg.apply_firmware_limits(RELEASE_B)
        assert not dlg._sb_arqtol.isEnabled()
        assert "Not supported by firmware 01.AUG.91" in dlg._sb_arqtol.toolTip()
        assert dlg.get_values()["arqtol"] == 4      # value stays in the configuration

    def test_amtor_arqtol_stays_enabled_on_a_unmeasured_and_unknown(self):
        for release in (RELEASE_A, RELEASE_C, None):
            dlg = AMTORParamsDialog()
            dlg.apply_firmware_limits(release)
            assert dlg._sb_arqtol.isEnabled()

    def test_baudot_mopt_greyed_on_b(self):
        dlg = BaudotParamsDialog()
        dlg.apply_firmware_limits(RELEASE_B)
        assert not dlg._chk_mopt.isEnabled()
        assert "Not supported by firmware 01.AUG.91" in dlg._chk_mopt.toolTip()

    def test_baudot_mopt_stays_enabled_on_a(self):
        dlg = BaudotParamsDialog()
        dlg.apply_firmware_limits(RELEASE_A)
        assert dlg._chk_mopt.isEnabled()

    def test_pactor_fields_greyed_on_b_and_enabled_on_a(self):
        dlg = PACTORParamsDialog(PACTORConfig())
        dlg.apply_firmware_limits(RELEASE_B)
        for w in (dlg._le_myptcall, dlg._chk_pt200, dlg._hx_ptover):
            assert not w.isEnabled()
        dlg = PACTORParamsDialog(PACTORConfig())
        dlg.apply_firmware_limits(RELEASE_A)
        for w in (dlg._le_myptcall, dlg._chk_pt200, dlg._hx_ptover):
            assert w.isEnabled()
