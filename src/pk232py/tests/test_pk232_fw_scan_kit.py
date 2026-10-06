# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""P90 - the scanner for other radio amateurs: it leaves the device as it found it, copes with the
settings of a device with a battery (EXPERT ON, ECHO OFF, another operating mode), writes one result
folder per device with everything verbatim and packs the folders into results_<call>_<date>.zip.

tools/ is not a package - see test_hw_check.py."""

from __future__ import annotations

import dataclasses
import sys
import zipfile
from pathlib import Path

import pytest

from pk232py.comm import command_matrix as cm

_TOOLS = Path(__file__).resolve().parents[3] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import pk232_fw_scan as scan  # noqa: E402

B, A, C = "01.AUG.91", "13.SEP.95", "30.DEC.88"


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(scan, "_clock", c)
    monkeypatch.setattr(scan, "_sleep", c.advance)
    monkeypatch.setattr(scan.time, "sleep", lambda seconds: None)
    return c


def _state(t):
    return (t.opmode, t.expert_on, t.echo_on)


class TestTheDeviceIsLeftAsItWas:
    """A device with a battery has its own settings: the scan must give them back."""

    def test_opmode_expert_and_echo_are_restored(self, clock):
        t = scan.MockTransport(B, clock=clock, opmode="BAUDOT", expert_on=True, echo_on=False)
        before = _state(t)
        rep = scan.run_scan(t, "MOCK", progress=False)
        assert _state(t) == before == ("BAUDOT", True, False)
        assert rep.state_diff == []

    def test_a_scan_with_echo_off_still_finds_the_release_and_no_error(self, clock):
        t = scan.MockTransport(B, clock=clock, echo_on=False)
        rep = scan.run_scan(t, "MOCK", progress=False)
        assert rep.release == B
        assert not [r for r in rep.rows if r["result"] == "ERROR"]
        wrong = [r["name"] for r in rep.rows
                 if r["result"] != ("UNSUPPORTED" if cm.exists(r["name"], B) == "no" else "SUPPORTED")]
        assert wrong == []

    def test_expert_that_was_on_stays_on(self, clock):
        t = scan.MockTransport(A, clock=clock, expert_on=True)
        scan.run_scan(t, "MOCK", progress=False)
        assert t.expert_on is True

    def test_the_settings_before_and_after_are_recorded_raw(self, clock):
        t = scan.MockTransport(B, clock=clock, opmode="BAUDOT")
        rep = scan.run_scan(t, "MOCK", progress=False)
        assert "BAUDOT" in rep.settings_before.upper() and "BAUDOT" in rep.settings_after.upper()
        assert rep.settings_before == rep.settings_after

    def test_a_difference_after_the_scan_is_reported_clearly(self, clock, capsys):
        t = scan.MockTransport(A, clock=clock, sticky={"EXPERT OFF"})   # EXPERT OFF is accepted but ignored
        rep = scan.run_scan(t, "MOCK", progress=False)
        assert rep.state_diff, "the device was left in another state"
        scan.print_report(rep)
        assert "DEVICE STATE DIFFERS" in capsys.readouterr().out

    def test_the_safe_run_never_sets_mycall_and_never_resets(self, clock):
        t = scan.MockTransport(B, clock=clock)
        scan.run_scan(t, "MOCK", progress=False)
        lines = [d.decode("latin-1").strip().upper() for d in t.sent]
        assert not [ln for ln in lines if ln.startswith("MYCALL ")]
        assert not {"RESET", "REINIT"} & set(lines)
        assert t.mycall == t.FACTORY_MYCALL


class TestResultFolder:

    def _run(self, tmp_path, *extra, year="1991"):
        return scan.main(["--selftest", year, "--results", str(tmp_path), "--call", "OE3GAS", *extra])

    def test_one_folder_per_device_with_every_file(self, clock, tmp_path):
        assert self._run(tmp_path) == 0
        (folder,) = [p for p in tmp_path.iterdir() if p.is_dir()]
        assert folder.name == "scan_01.AUG.91_n1"
        names = {p.name for p in folder.iterdir()}
        assert {"banner.txt", "scan.csv", "debug.log", "settings_before.txt", "settings_after.txt",
                "device_info.txt"} <= names

    def test_the_banner_is_written_verbatim(self, clock, tmp_path):
        self._run(tmp_path)
        folder = next(p for p in tmp_path.iterdir() if p.is_dir())
        raw = (folder / "banner.txt").read_bytes()
        assert b"Release 01.AUG.91" in raw and b"\r\n" in raw             # not normalised

    def test_the_csv_names_release_and_date(self, clock, tmp_path):
        self._run(tmp_path)
        folder = next(p for p in tmp_path.iterdir() if p.is_dir())
        head, first = (folder / "scan.csv").read_text(encoding="utf-8").splitlines()[:2]
        assert head.startswith("release,device,date,name")
        assert first.startswith("01.AUG.91,")

    def test_the_debug_log_is_in_the_folder_and_complete(self, clock, tmp_path):
        self._run(tmp_path)
        folder = next(p for p in tmp_path.iterdir() if p.is_dir())
        text = (folder / "debug.log").read_text(encoding="utf-8")
        assert text.splitlines()[-1].startswith("# end of log")
        assert not list(tmp_path.glob("_running*"))                      # the temporary log was moved

    def test_device_info_is_a_form_with_the_scan_facts_filled_in(self, clock, tmp_path):
        self._run(tmp_path)
        folder = next(p for p in tmp_path.iterdir() if p.is_dir())
        info = (folder / "device_info.txt").read_text(encoding="utf-8")
        for key in ("Model:", "EPROM label:", "Board options:", "Battery backup:", "Remarks:"):
            assert key in info
        assert "Release: 01.AUG.91" in info and "Callsign: OE3GAS" in info and "Date:" in info

    def test_a_second_device_of_the_same_release_gets_the_next_number(self, clock, tmp_path):
        self._run(tmp_path)
        self._run(tmp_path)
        assert sorted(p.name for p in tmp_path.iterdir() if p.is_dir()) == [
            "scan_01.AUG.91_n1", "scan_01.AUG.91_n2"]

    def test_the_serial_number_of_the_banner_names_the_folder(self, clock, tmp_path, monkeypatch):
        orig = scan.MockTransport._banner
        monkeypatch.setattr(scan.MockTransport, "_banner",
                            lambda self: orig(self).replace("\r\ncmd:", "\r\nPACTOR s/n 12345\r\ncmd:"))
        self._run(tmp_path, year="1995")
        assert (tmp_path / "scan_13.SEP.95_12345").is_dir()

    def test_everything_is_packed_into_results_call_date_zip(self, clock, tmp_path):
        self._run(tmp_path)
        self._run(tmp_path, year="1995")
        (zpath,) = list(tmp_path.glob("results_OE3GAS_*.zip"))
        with zipfile.ZipFile(zpath) as z:
            names = z.namelist()
        assert any(n.startswith("scan_01.AUG.91_n1/") for n in names)
        assert any(n.startswith("scan_13.SEP.95_n1/") for n in names)
        assert "scan_01.AUG.91_n1/banner.txt" in names

    def test_results_need_a_callsign(self, clock, tmp_path, capsys):
        assert scan.main(["--selftest", "1991", "--results", str(tmp_path)]) == 2
        assert "--call" in capsys.readouterr().err


class TestKitMode:

    def test_update_matrix_does_not_exist_in_the_kit(self, monkeypatch, capsys):
        monkeypatch.setattr(scan, "_KIT", True)
        assert scan.main(["--selftest", "1991", "--update-matrix"]) == 2
        assert "kit" in capsys.readouterr().err.lower()

    def test_the_kit_writes_its_results_to_scan_results_of_the_working_directory(self, clock, tmp_path, monkeypatch):
        monkeypatch.setattr(scan, "_KIT", True)
        monkeypatch.chdir(tmp_path)
        assert scan.main(["--selftest", "1991", "--call", "OE3GAS"]) == 0
        assert (tmp_path / "scan_results" / "scan_01.AUG.91_n1" / "scan.csv").exists()

    def test_the_kit_still_asks_before_all(self, monkeypatch):
        monkeypatch.setattr(scan, "_KIT", True)
        monkeypatch.setattr(scan, "_ask", lambda prompt: "no")
        assert scan.main(["--port", "COM99", "--all", "--call", "OE3GAS"]) == 5


class TestEvidenceOfAnExternalImport:

    def test_apply_to_matrix_takes_the_evidence_it_is_given(self):
        entries = cm.all_entries()
        e = entries["XLENGTH"]
        entries["XLENGTH"] = dataclasses.replace(e, fw={**e.fw, C: "?"}, ev={**e.ev, C: ""})
        new, filled, conflicts = scan.apply_to_matrix(
            entries, [{"name": "XLENGTH", "result": "SUPPORTED"}], C, "2026-10-08", "ext:OE3XX:1", "scan.csv",
            evidence="ext OE3XX 2026-10-08 scan.csv")
        assert filled == 1 and not conflicts
        assert new["XLENGTH"].ev[C] == "ext OE3XX 2026-10-08 scan.csv"
