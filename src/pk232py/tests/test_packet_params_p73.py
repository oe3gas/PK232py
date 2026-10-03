# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""P73: the "Packet" parameter dialog - band values, monitor flags, layout.

  B   MAXFRAME/SLOTTIME exist once per band; a live change only reaches the
      TNC for the band whose Packet mode is active.
  C   the six Packet monitor flags (MBELL MDIGI MPROTO MSTAMP PASSALL
      BBSMSGS) reach the config AND the TNC upload - no dead switch.
  D   three columns, no scroll area, the menu entry is "Packet...".

(Teil A, MONITOR instead of MN Y, is tested in test_packet_hf.py.)
"""

from __future__ import annotations

import copy
import dataclasses
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QGroupBox, QScrollArea, QSpinBox,
)

from pk232py.comm.frame import build_command
from pk232py.comm.host_params import (
    BAND_HF, BAND_VHF, band_of_mode, band_value, param_by_name,
)
from pk232py.comm.param_applier import ParamApplier, format_result
from pk232py.comm.params_uploader import ParamsUploader
from pk232py.config import AppConfig, ConfigManager, HFPacketConfig
from pk232py.modes.packet_hf import HFPacketMode
from pk232py.modes.packet_vhf import VHFPacketMode
from pk232py.ui.dialogs.params_hf import PacketParamsDialog
from pk232py.tests.test_param_applier import FakeTransport

_app = QApplication.instance() or QApplication([])

B = "01.AUG.91"   # MAXFRAME / SLOTTIME verified for Host Mode (T151)

NEW_FLAGS = ("MBELL", "MDIGI", "MPROTO", "MSTAMP", "PASSALL", "BBSMSGS")


def _pair(**changes):
    before = AppConfig()
    after = copy.deepcopy(before)
    for k, v in changes.items():
        setattr(after.hf_packet, k, v)
    return before, after


# ---------------------------------------------------------------------------
# B - band values
# ---------------------------------------------------------------------------

class TestBandValuesInTheModes:
    def test_vhf_maxframe_and_slottime_come_from_the_config_values(self):
        frames = VHFPacketMode(maxframe=7, slottime=20).get_init_frames()
        assert build_command(b'MX', b'7') in frames
        assert build_command(b'SL', b'20') in frames

    def test_without_new_ini_keys_vhf_still_sends_mx4_sl10(self):
        cfg = HFPacketConfig()
        assert (cfg.vhf_maxframe, cfg.vhf_slottime) == (4, 10)
        frames = VHFPacketMode().get_init_frames()
        assert build_command(b'MX', b'4') in frames
        assert build_command(b'SL', b'10') in frames

    def test_hf_still_uses_the_hf_values(self):
        cfg = HFPacketConfig()
        frames = HFPacketMode(
            maxframe=band_value(cfg, "MAXFRAME", BAND_HF),
            slottime=band_value(cfg, "SLOTTIME", BAND_HF)).get_init_frames()
        assert build_command(b'MX', b'1') in frames
        assert build_command(b'SL', b'30') in frames

    def test_one_table_assigns_config_attributes_to_bands(self):
        cfg = HFPacketConfig(maxframe=2, slottime=20, vhf_maxframe=5, vhf_slottime=8)
        assert band_value(cfg, "MAXFRAME", BAND_HF) == 2
        assert band_value(cfg, "MAXFRAME", BAND_VHF) == 5
        assert band_value(cfg, "SLOTTIME", BAND_HF) == 20
        assert band_value(cfg, "SLOTTIME", BAND_VHF) == 8

    def test_band_of_mode(self):
        assert band_of_mode("HF Packet") == BAND_HF
        assert band_of_mode("VHF Packet") == BAND_VHF
        assert band_of_mode("Baudot RTTY") is None
        assert band_of_mode(None) is None


class TestIniKeys:
    def test_vhf_values_survive_save_and_load(self, tmp_path):
        mgr = ConfigManager(tmp_path / "pk232py.ini")
        mgr.app.hf_packet.vhf_maxframe = 6
        mgr.app.hf_packet.vhf_slottime = 15
        mgr.save()
        again = ConfigManager(tmp_path / "pk232py.ini")
        again.load()
        assert again.app.hf_packet.vhf_maxframe == 6
        assert again.app.hf_packet.vhf_slottime == 15

    def test_missing_keys_give_the_old_fixed_values(self, tmp_path):
        ini = tmp_path / "pk232py.ini"
        ini.write_text("[HF_Packet]\nmaxframe = 2\n", encoding="utf-8")
        mgr = ConfigManager(ini)
        mgr.load()
        assert (mgr.app.hf_packet.vhf_maxframe, mgr.app.hf_packet.vhf_slottime) == (4, 10)


class TestParamApplierBands:
    """P72 with the band rule: never overwrite the other band's value."""

    def test_hf_maxframe_changed_in_vhf_mode_sends_nothing_and_says_so(self):
        t = FakeTransport(release=B)
        before, after = _pair(maxframe=3)
        (r,) = ParamApplier(t).apply(before, after, band=BAND_VHF)
        assert t.log == []                                   # no MX frame at all
        assert r.deferred and not r.ok
        assert format_result(r) == \
            "MAXFRAME (HF) saved - applies when HF Packet is selected"

    def test_vhf_maxframe_changed_in_vhf_mode_is_sent_and_read_back(self):
        t = FakeTransport(release=B, host_answers={
            (b"MX", b"7"): b"MX\x00", (b"MX", b""): b"MX7"})
        before, after = _pair(vhf_maxframe=7)
        (r,) = ParamApplier(t).apply(before, after, band=BAND_VHF)
        assert t.log == [("host", b"MX", b"7"), ("host", b"MX", b"")]
        assert r.ok and not r.deferred

    def test_vhf_maxframe_changed_in_hf_mode_is_deferred(self):
        t = FakeTransport(release=B)
        before, after = _pair(vhf_maxframe=7)
        (r,) = ParamApplier(t).apply(before, after, band=BAND_HF)
        assert t.log == []
        assert format_result(r) == \
            "MAXFRAME (VHF) saved - applies when VHF Packet is selected"

    def test_hf_slottime_changed_in_hf_mode_is_sent(self):
        t = FakeTransport(release=B, host_answers={
            (b"SL", b"12"): b"SL\x00", (b"SL", b""): b"SL12"})
        before, after = _pair(slottime=12)
        (r,) = ParamApplier(t).apply(before, after, band=BAND_HF)
        assert r.ok and t.log[0] == ("host", b"SL", b"12")

    def test_no_packet_mode_active_sends_no_band_value(self):
        t = FakeTransport(release=B)
        before, after = _pair(maxframe=3, vhf_maxframe=7)
        results = ParamApplier(t).apply(before, after, band=None)
        assert t.log == []
        assert [r.deferred for r in results] == [True, True]

    def test_changed_values_follow_the_same_rule(self):
        before, after = _pair(maxframe=3, vhf_maxframe=7)
        assert ParamsUploader.changed_values(before, after, band=BAND_HF) == [("MAXFRAME", "3")]
        assert ParamsUploader.changed_values(before, after, band=BAND_VHF) == [("MAXFRAME", "7")]

    def test_other_parameters_are_not_affected_by_the_band(self):
        t = FakeTransport(release=B, host_answers={
            (b"PL", b"100"): b"PL\x00", (b"PL", b""): b"PL100"})
        before, after = _pair(paclen=100)
        (r,) = ParamApplier(t).apply(before, after, band=BAND_VHF)
        assert r.ok


# ---------------------------------------------------------------------------
# C - the six monitor flags
# ---------------------------------------------------------------------------

def _flag_checkboxes(dlg):
    box = next(g for g in dlg.findChildren(QGroupBox) if g.title() == "Flags")
    return box.findChildren(QCheckBox)


class TestMonitorFlags:
    def test_every_flag_checkbox_reaches_config_and_upload(self):
        """The list comes from the dialog: a switch added later that is not
        wired shows up here at once."""
        base_cmds = ParamsUploader(None, AppConfig())._build_commands(has_pactor=True)
        base_cfg = dataclasses.asdict(HFPacketConfig())
        first = PacketParamsDialog(HFPacketConfig())
        count = len(_flag_checkboxes(first))
        assert count >= 19
        failures = []
        for i in range(count):
            dlg = PacketParamsDialog(HFPacketConfig())
            box = _flag_checkboxes(dlg)[i]
            box.setChecked(not box.isChecked())
            cfg = HFPacketConfig()
            dlg.apply_to(cfg)
            diff = [k for k, v in dataclasses.asdict(cfg).items() if v != base_cfg[k]]
            if len(diff) != 1:
                failures.append(f"{box.text()}: config fields changed = {diff}")
                continue
            app = AppConfig()
            app.hf_packet = cfg
            if ParamsUploader(None, app)._build_commands(has_pactor=True) == base_cmds:
                failures.append(f"{box.text()}: no upload command changed")
        assert not failures, "\n".join(failures)

    def test_the_six_are_all_in_the_dialog(self):
        dlg = PacketParamsDialog(HFPacketConfig())   # keep it alive: Qt deletes the children with it
        names = {b.text() for b in _flag_checkboxes(dlg)}
        assert set(NEW_FLAGS) <= names

    def test_upload_sends_each_as_a_verbose_switch(self):
        app = AppConfig()
        for attr in ("mbell", "mdigi", "mproto", "mstamp", "passall", "bbsmsgs"):
            setattr(app.hf_packet, attr, True)
        cmds = ParamsUploader(None, app)._build_commands(has_pactor=True)
        for name in NEW_FLAGS:
            assert f"{name} ON\r\n".encode() in cmds
        off = ParamsUploader(None, AppConfig())._build_commands(has_pactor=True)
        for name in NEW_FLAGS:
            assert f"{name} OFF\r\n".encode() in off

    def test_flags_survive_the_ini(self, tmp_path):
        mgr = ConfigManager(tmp_path / "pk232py.ini")
        for attr in ("mdigi", "mproto", "mstamp", "passall", "bbsmsgs"):
            setattr(mgr.app.hf_packet, attr, True)
        mgr.save()
        again = ConfigManager(tmp_path / "pk232py.ini")
        again.load()
        for attr in ("mdigi", "mproto", "mstamp", "passall", "bbsmsgs"):
            assert getattr(again.app.hf_packet, attr) is True

    def test_host_rows_exist_with_the_matrix_mnemonics_and_are_verified_on_both(self):
        expected = {"MBELL": b"ME", "MDIGI": b"MD", "MPROTO": b"MQ", "MSTAMP": b"MS",
                    "PASSALL": b"PX", "BBSMSGS": b"BB"}
        for name, mn in expected.items():
            row = param_by_name(name)
            assert row is not None and row.mnemonic == mn, name
            # T160 (device B, 01.AUG.91) and T161 (device A, 13.SEP.95).
            assert row.verified_releases == ("01.AUG.91", "13.SEP.95"), name
        assert param_by_name("FULLDP") is None      # ?What? on both devices

    def test_live_change_of_a_flag_is_set_in_host_mode_and_read_back(self):
        t = FakeTransport(release=B, host_answers={
            (b"PX", b"Y"): b"PX\x00", (b"PX", b""): b"PXY"})
        before, after = _pair(passall=True)
        (r,) = ParamApplier(t).apply(before, after, band=BAND_HF)
        assert t.log == [("host", b"PX", b"Y"), ("host", b"PX", b"")]
        assert r.ok


# ---------------------------------------------------------------------------
# D - the dialog
# ---------------------------------------------------------------------------

class TestDialogLayout:
    def _shown(self):
        dlg = PacketParamsDialog(HFPacketConfig())
        dlg.show()
        _app.processEvents()
        return dlg

    def test_title_and_class_name(self):
        dlg = PacketParamsDialog(HFPacketConfig())
        assert dlg.windowTitle() == "Packet Parameters"

    def test_no_scroll_area_in_the_parameters_tab(self):
        dlg = PacketParamsDialog(HFPacketConfig())
        link = next(g for g in dlg.findChildren(QGroupBox) if g.title() == "Link")
        tab = link.parentWidget()               # the Parameters page itself
        assert tab.findChildren(QScrollArea) == []
        assert not isinstance(tab, QScrollArea)

    def test_three_columns_side_by_side(self):
        dlg = self._shown()
        try:
            titles = {g.title(): g for g in dlg.findChildren(QGroupBox)}
            # "&&" is how a literal "&" is written in a Qt title
            cols = [titles["Link"], titles["Band && Status"], titles["Flags"]]
            tab = cols[0].parentWidget()
            xs = [c.mapTo(tab, QPoint(0, 0)).x() for c in cols]
            ys = [c.mapTo(tab, QPoint(0, 0)).y() for c in cols]
            assert xs == sorted(xs) and len(set(xs)) == 3     # left to right
            assert len(set(ys)) == 1                          # same top edge
        finally:
            dlg.close()

    def test_every_widget_is_inside_the_visible_page_at_100_percent(self):
        """Measured on the real, shown dialog (rule 14): no widget is cut off,
        so nothing could need a scrollbar."""
        dlg = self._shown()
        try:
            titles = {g.title(): g for g in dlg.findChildren(QGroupBox)}
            tab = titles["Link"].parentWidget()
            page = tab.rect()
            outside = []
            for w in tab.findChildren((QSpinBox, QCheckBox)):
                top_left = w.mapTo(tab, QPoint(0, 0))
                r = w.rect().translated(top_left)
                if not w.isVisibleTo(tab) or not page.contains(r):
                    outside.append((w.objectName() or w.metaObject().className(), r, page))
            assert not outside, outside
            screen = dlg.screen().availableGeometry()
            assert dlg.height() <= screen.height()
            assert dlg.width() <= screen.width()
        finally:
            dlg.close()

    def test_hf_and_vhf_values_roundtrip_through_the_dialog(self):
        cfg = HFPacketConfig(maxframe=2, slottime=20, vhf_maxframe=6, vhf_slottime=8)
        dlg = PacketParamsDialog(cfg)
        out = HFPacketConfig()
        dlg.apply_to(out)
        assert (out.maxframe, out.slottime, out.vhf_maxframe, out.vhf_slottime) == (2, 20, 6, 8)


class TestMenuEntry:
    def test_menu_says_packet_not_hf_packet(self):
        from pk232py.ui.main_window import MainWindow
        win = MainWindow()
        texts = {a.text().replace("&", "") for a in win.findChildren(QAction)}
        assert "Packet..." in texts
        assert "HF Packet..." not in texts


class TestFulldpIsGone:
    """FULLDP answers ?What? on 01.AUG.91 and 13.SEP.95 (T160/T161)."""

    def test_not_in_config_upload_or_dialog(self):
        assert not hasattr(HFPacketConfig(), "fulldp")
        cmds = ParamsUploader(None, AppConfig())._build_commands(has_pactor=True)
        assert not [c for c in cmds if b"FULLDP" in c]
        dlg = PacketParamsDialog(HFPacketConfig())
        assert "FULLDP" not in {b.text() for b in _flag_checkboxes(dlg)}

    def test_an_old_ini_with_fulldp_still_loads(self, tmp_path):
        ini = tmp_path / "pk232py.ini"
        ini.write_text("[HF_Packet]\nfulldp = true\nmdigi = true\n", encoding="utf-8")
        mgr = ConfigManager(ini)
        mgr.load()
        assert mgr.app.hf_packet.mdigi is True
