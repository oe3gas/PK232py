# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""P90 Teil D - tools/import_external_scan.py merges the results of an external operator into the command
matrix: new releases become new columns, only ? cells are filled (evidence "ext <call> <date> <file>"), a
contradiction writes NOTHING and lists it, existing evidence is never overwritten, the raw files are kept
unchanged and the device_info form becomes one line in docs/reference/external/devices.md.

The result zips are made with the scanner itself against a mock TNC. tools/ is not a package."""

from __future__ import annotations

import dataclasses
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

from pk232py.comm import command_matrix as cm

_TOOLS = Path(__file__).resolve().parents[3] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import import_external_scan as imp  # noqa: E402
import pk232_fw_scan as scan  # noqa: E402

B, A = "01.AUG.91", "13.SEP.95"
NEW = "12.MAR.93"


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


@pytest.fixture
def world(tmp_path):
    """A copy of the matrix and empty docs/reference/external to import into."""
    matrix = tmp_path / "matrix.csv"
    shutil.copyfile(cm.DATA_FILE, matrix)
    return matrix, tmp_path / "external"


def _scan_device(clock, release, results_dir, call="OE3XX", entries=None, banner_extra=None, monkeypatch=None):
    t = scan.MockTransport(release, clock=clock, entries=entries)
    if banner_extra:
        orig = t._banner
        t._banner = lambda: orig().replace("\r\ncmd:", f"\r\n{banner_extra}\r\ncmd:")
    rep = scan.run_scan(t, "MOCK", progress=False)
    scan.write_results(rep, results_dir, call, None)
    return rep


def _zip(clock, results_dir, call="OE3XX"):
    return scan.build_results_zip(results_dir, call, scan.Report("p", None, "").date)


def _matrix_bytes(path):
    return Path(path).read_bytes()


class TestNewRelease:

    def test_a_new_release_becomes_new_columns_and_only_unknown_cells_are_filled(self, clock, tmp_path, world):
        matrix, raw = world
        _scan_device(clock, NEW, tmp_path / "res")
        z = _zip(clock, tmp_path / "res")
        before = cm.parse(_matrix_bytes(matrix).decode("utf-8"))
        result = imp.import_zip(z, matrix_path=matrix, raw_root=raw)
        after = cm.load(matrix)
        assert result.new_releases == [NEW] and not result.conflicts and result.filled > 100
        assert NEW in cm.releases_of(after) and NEW not in cm.releases_of(before)
        for name, e in after.items():
            for rel in cm.releases_of(before):
                assert e.fw[rel] == before[name].fw[rel] and e.ev[rel] == before[name].ev[rel]
        filled = [e for e in after.values() if e.fw[NEW] != "?"]
        assert len(filled) > 100
        assert all(e.ev[NEW].startswith("ext OE3XX ") and "scan_12.MAR.93_n1/scan.csv" in e.ev[NEW] for e in filled)

    def test_the_evidence_names_the_callsign_the_date_and_the_file(self, clock, tmp_path, world):
        matrix, raw = world
        rep = _scan_device(clock, NEW, tmp_path / "res")
        imp.import_zip(_zip(clock, tmp_path / "res"), matrix_path=matrix, raw_root=raw)
        e = cm.load(matrix)["ILFPACK"]
        assert e.ev[NEW] == f"ext OE3XX {rep.date} scan_12.MAR.93_n1/scan.csv"

    def test_the_raw_files_are_kept_unchanged(self, clock, tmp_path, world):
        matrix, raw = world
        _scan_device(clock, NEW, tmp_path / "res")
        imp.import_zip(_zip(clock, tmp_path / "res"), matrix_path=matrix, raw_root=raw)
        src = tmp_path / "res" / "scan_12.MAR.93_n1"
        dst = raw / "OE3XX" / "scan_12.MAR.93_n1"
        names = {p.name for p in src.iterdir()}
        assert names == {p.name for p in dst.iterdir()} and "banner.txt" in names
        for name in names:
            assert (src / name).read_bytes() == (dst / name).read_bytes()

    def test_the_device_info_becomes_one_line_in_devices_md_not_in_devices_inventory(self, clock, tmp_path, world):
        matrix, raw = world
        res = tmp_path / "res"
        _scan_device(clock, NEW, res)
        info = res / "scan_12.MAR.93_n1" / "device_info.txt"
        info.write_text(info.read_text(encoding="utf-8")
                        .replace("Model:", "Model: PK-232MBX").replace("Battery backup:", "Battery backup: yes"),
                        encoding="utf-8")
        imp.import_zip(_zip(clock, res), matrix_path=matrix, raw_root=raw)
        text = (raw / "devices.md").read_text(encoding="utf-8")
        row = [ln for ln in text.splitlines() if "ext:OE3XX:n1" in ln]
        assert len(row) == 1 and NEW in row[0] and "PK-232MBX" in row[0] and "yes" in row[0]
        assert not (raw.parent / "DEVICES.md").exists()

    def test_a_second_import_of_the_same_zip_changes_nothing(self, clock, tmp_path, world):
        matrix, raw = world
        _scan_device(clock, NEW, tmp_path / "res")
        z = _zip(clock, tmp_path / "res")
        imp.import_zip(z, matrix_path=matrix, raw_root=raw)
        once = _matrix_bytes(matrix)
        again = imp.import_zip(z, matrix_path=matrix, raw_root=raw)
        assert again.filled == 0 and not again.conflicts and again.new_releases == []
        assert _matrix_bytes(matrix) == once
        assert (raw / "devices.md").read_text(encoding="utf-8").count("ext:OE3XX:n1") == 1


class TestKnownRelease:

    def test_a_known_release_fills_only_unknown_cells_and_never_overwrites_evidence(self, clock, tmp_path, world):
        matrix, raw = world
        before = cm.load(matrix)
        _scan_device(clock, A, tmp_path / "res")           # the mock answers like the matrix says
        result = imp.import_zip(_zip(clock, tmp_path / "res"), matrix_path=matrix, raw_root=raw)
        after = cm.load(matrix)
        assert not result.conflicts and result.new_releases == []
        for name, e in before.items():
            if e.fw[A] != "?":
                assert after[name].fw[A] == e.fw[A] and after[name].ev[A] == e.ev[A], name

    def test_a_contradiction_writes_nothing_and_lists_it(self, clock, tmp_path, world):
        matrix, raw = world
        entries = cm.all_entries()
        e = entries["PACLEN"]
        assert e.fw[B] == "yes"
        entries["PACLEN"] = dataclasses.replace(e, fw={**e.fw, B: "no"})     # THIS device does not know PACLEN
        _scan_device(clock, B, tmp_path / "res", entries=entries)
        z = _zip(clock, tmp_path / "res")
        before = _matrix_bytes(matrix)
        result = imp.import_zip(z, matrix_path=matrix, raw_root=raw)
        assert _matrix_bytes(matrix) == before
        assert any("PACLEN" in c and B in c for c in result.conflicts)
        assert not raw.exists() or not any(raw.rglob("*"))                 # no raw file either

    def test_two_devices_of_one_release_that_disagree_are_a_contradiction(self, clock, tmp_path, world):
        matrix, raw = world
        res = tmp_path / "res"
        _scan_device(clock, NEW, res)
        entries = cm.all_entries()
        e = entries["PACLEN"]
        entries["PACLEN"] = dataclasses.replace(e, fw={**e.fw, NEW: "no"})
        _scan_device(clock, NEW, res, entries=entries)
        before = _matrix_bytes(matrix)
        result = imp.import_zip(_zip(clock, res), matrix_path=matrix, raw_root=raw)
        assert _matrix_bytes(matrix) == before
        assert any("PACLEN" in c and "n2" in c for c in result.conflicts)


class TestBadInput:

    def test_a_dry_run_writes_nothing(self, clock, tmp_path, world):
        matrix, raw = world
        _scan_device(clock, NEW, tmp_path / "res")
        before = _matrix_bytes(matrix)
        result = imp.import_zip(_zip(clock, tmp_path / "res"), matrix_path=matrix, raw_root=raw, dry_run=True)
        assert result.filled > 100 and _matrix_bytes(matrix) == before and not raw.exists()

    def test_a_release_in_the_banner_that_differs_from_the_csv_is_refused(self, clock, tmp_path, world):
        matrix, raw = world
        res = tmp_path / "res"
        _scan_device(clock, NEW, res)
        folder = res / "scan_12.MAR.93_n1"
        csv_path = folder / "scan.csv"
        csv_path.write_text(csv_path.read_text(encoding="utf-8").replace(f"{NEW},", "13.MAR.93,"), encoding="utf-8")
        with pytest.raises(imp.ImportErrorExternal, match="banner"):
            imp.import_zip(_zip(clock, res), matrix_path=matrix, raw_root=raw)

    def test_a_zip_without_the_expected_name_is_refused(self, tmp_path, world):
        matrix, raw = world
        z = tmp_path / "stuff.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("x.txt", "x")
        with pytest.raises(imp.ImportErrorExternal, match="results_"):
            imp.import_zip(z, matrix_path=matrix, raw_root=raw)

    def test_main_returns_3_for_a_contradiction_and_0_for_a_good_import(self, clock, tmp_path, world, capsys):
        matrix, raw = world
        _scan_device(clock, NEW, tmp_path / "res")
        z = _zip(clock, tmp_path / "res")
        assert imp.main([str(z), "--matrix", str(matrix), "--raw-dir", str(raw)]) == 0
        out = capsys.readouterr().out
        assert "consent" in out.lower()
        assert imp.main(["nonsense.zip", "--matrix", str(matrix), "--raw-dir", str(raw)]) == 2
