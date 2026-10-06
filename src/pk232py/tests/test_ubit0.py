# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""P74: UBIT 0 as a Packet parameter (default OFF).

Covers config default / INI, the verbose upload command, the checkbox in
the Packet dialog (tooltip, round trip) and the removal of the unused
free-text UBIT fields from the AMTOR and Baudot dialogs.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from pk232py.comm.host_params import param_by_name
from pk232py.comm.params_uploader import ParamsUploader
from pk232py.config import AppConfig, ConfigManager, HFPacketConfig
from pk232py.ui.dialogs.params_amtor import AMTORParamsDialog
from pk232py.ui.dialogs.params_baudot import BaudotParamsDialog
from pk232py.ui.dialogs.params_hf import PacketParamsDialog

_app = QApplication.instance() or QApplication([])


class TestConfig:
    def test_default_is_off(self):
        assert HFPacketConfig().ubit0 is False

    def test_ini_without_key_is_false(self, tmp_path):
        ini = tmp_path / "pk232py.ini"
        ini.write_text("[HF_Packet]\nusers = 4\n", encoding="utf-8")
        mgr = ConfigManager(ini)
        mgr.load()
        assert mgr.app.hf_packet.ubit0 is False

    def test_ini_true_is_read(self, tmp_path):
        ini = tmp_path / "pk232py.ini"
        ini.write_text("[HF_Packet]\nubit0 = true\n", encoding="utf-8")
        mgr = ConfigManager(ini)
        mgr.load()
        assert mgr.app.hf_packet.ubit0 is True


class TestUpload:
    def _cmds(self, **kw):
        cfg = AppConfig()
        for k, v in kw.items():
            setattr(cfg.hf_packet, k, v)
        return ParamsUploader(serial=None, config=cfg)._build_commands(has_pactor=True)

    def test_default_uploads_ubit0_off(self):
        assert b"UBIT 0 OFF\r" in self._cmds()

    def test_ubit0_true_uploads_on(self):
        cmds = self._cmds(ubit0=True)
        assert b"UBIT 0 ON\r" in cmds
        assert b"UBIT 0 OFF\r" not in cmds


class TestHostParamsRow:
    def test_row_is_the_t156_measurement(self):
        row = param_by_name("UBIT")
        assert row is not None and row.kind == "ubit"
        # T156: set "UB0 N", query "UB0" -> "UBN" - device A (13.SEP.95) and
        # device B (01.AUG.91, 19:46 log) measured the same form.
        assert row.mnemonic == b"UB"
        assert row.verified_releases == ("01.AUG.91", "13.SEP.95")


class TestPacketDialog:
    def test_checkbox_and_tooltip(self):
        dlg = PacketParamsDialog(HFPacketConfig())
        tip = dlg._chk_ubit0.toolTip()
        assert "recommended" in tip and "below threshold" in tip
        assert dlg._chk_ubit0.text() == "UBIT 0 (DCD gate)"
        assert dlg._chk_ubit0.isChecked() is False

    def test_round_trip(self):
        dlg = PacketParamsDialog(HFPacketConfig(ubit0=True))
        assert dlg._chk_ubit0.isChecked() is True
        dlg._chk_ubit0.setChecked(False)
        out = HFPacketConfig(ubit0=True)
        dlg.apply_to(out)
        assert out.ubit0 is False
        dlg._chk_ubit0.setChecked(True)
        dlg.apply_to(out)
        assert out.ubit0 is True


class TestOtherDialogsHaveNoUbitField:
    def test_amtor_and_baudot(self):
        for dlg in (AMTORParamsDialog(),
                    BaudotParamsDialog()):
            assert not hasattr(dlg, "_le_ubit")
