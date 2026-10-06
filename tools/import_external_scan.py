# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""P90: merge the results of an external operator (the zip of the scan kit) into the command matrix.

    python tools/import_external_scan.py results_<call>_<date>.zip [--dry-run]
                                         [--matrix PATH] [--raw-dir PATH]

* A release the matrix does not have yet (banner format DD.MMM.YY) becomes new fw_ / ev_ / fx_ columns.
* Only ``?`` cells are filled, with the evidence ``ext <call> <date> <folder>/scan.csv``; a cell that is
  already set - by us or by another device of the same release - is never changed.
* The SAME release with ANOTHER result than ours (or than another device) writes NOTHING and lists the
  difference (a hardware variant or a measurement error - to be judged by a person).
* The raw files go unchanged to docs/reference/external/<call>/<folder>/ and the device_info form becomes
  one line in docs/reference/external/devices.md. The device is named ``ext:<call>:<serial|n#>`` and is NOT
  added to docs/DEVICES.md (that stays our inventory).

NOT part of the shipped application. The matching side is the scan kit (tools/build_scan_kit.py).
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tools"))

from pk232py.comm import command_matrix as cm  # noqa: E402
import pk232_fw_scan as scan  # noqa: E402

RAW_ROOT = REPO / "docs" / "reference" / "external"
_ZIP_NAME = re.compile(r"^results_(?P<call>.+)_(?P<date>\d{4}-\d{2}-\d{2})\.zip$")
_RELEASE = re.compile(r"Release\s+(\S+)")
DEVICES_HEADER = """\
# External devices (P90)

Devices scanned by other radio amateurs with the scan kit (`tools/build_scan_kit.py`), imported by
`tools/import_external_scan.py`. This is **not** our inventory - `docs/DEVICES.md` stays that. The raw files
of each device are in `docs/reference/external/<call>/<folder>/`; the data came with the operator's consent.

| Device | Release | Date | Model | EPROM label | Board options | Battery backup | Remarks | Folder |
|---|---|---|---|---|---|---|---|---|
"""


class ImportErrorExternal(Exception):
    """The zip is not a result zip of the scan kit, or its content disagrees with itself."""


@dataclass
class ExternalDevice:
    call: str
    folder: str
    release: str
    serial: str
    date: str
    rows: list
    info: dict
    files: dict            # name -> bytes, exactly as sent

    @property
    def device_id(self) -> str:
        return f"ext:{self.call}:{self.serial}"


@dataclass
class ImportResult:
    filled: int = 0
    new_releases: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    devices: list = field(default_factory=list)
    written: list = field(default_factory=list)


def _parse_info(text: str) -> dict:
    info = {}
    for line in text.splitlines():
        if line.lstrip().startswith("#") or ":" not in line:
            continue
        key, _sep, value = line.partition(":")
        info[key.strip()] = value.strip()
    return info


def read_results(zip_path) -> list:
    """The devices in a result zip (one ``scan_*`` folder each)."""
    zip_path = Path(zip_path)
    m = _ZIP_NAME.match(zip_path.name)
    if not m:
        raise ImportErrorExternal(f"{zip_path.name}: not a result zip (expected results_<call>_<date>.zip)")
    if not zip_path.exists():
        raise ImportErrorExternal(f"{zip_path}: not found")
    call, zip_date = m.group("call"), m.group("date")
    devices = []
    with zipfile.ZipFile(zip_path) as z:
        folders: dict = {}
        for name in z.namelist():
            top, _sep, rest = name.partition("/")
            if _sep and top.startswith("scan_") and rest:
                folders.setdefault(top, {})[rest] = z.read(name)
    if not folders:
        raise ImportErrorExternal(f"{zip_path.name}: no scan_* folder inside")
    for folder in sorted(folders):
        files = folders[folder]
        for needed in ("banner.txt", "scan.csv"):
            if needed not in files:
                raise ImportErrorExternal(f"{folder}: {needed} is missing")
        banner = _RELEASE.search(files["banner.txt"].decode("latin-1"))
        if not banner:
            raise ImportErrorExternal(f"{folder}: no 'Release ...' in banner.txt")
        release = banner.group(1).upper()
        rows = list(csv.DictReader(io.StringIO(files["scan.csv"].decode("utf-8"), newline="")))
        in_csv = {r.get("release", "") for r in rows}
        if in_csv != {release}:
            raise ImportErrorExternal(
                f"{folder}: the banner says release {release}, scan.csv says {sorted(in_csv)}")
        date = (rows[0].get("date") or zip_date) if rows else zip_date
        info = _parse_info(files.get("device_info.txt", b"").decode("utf-8", errors="replace"))
        serial = folder.split("_", 2)[2] if folder.count("_") >= 2 else "n"
        devices.append(ExternalDevice(call, folder, release, serial, date, rows, info, files))
    return devices


def _cell(text: str) -> str:
    return (text or "").replace("|", "/").replace("\n", " ").strip()


def _device_row(d: ExternalDevice) -> str:
    i = d.info
    return ("| " + " | ".join([
        d.device_id, d.release, d.date, _cell(i.get("Model", "")), _cell(i.get("EPROM label", "")),
        _cell(i.get("Board options", "")), _cell(i.get("Battery backup", "")), _cell(i.get("Remarks", "")),
        f"{d.call}/{d.folder}"]) + " |")


def _add_device_row(devices_md: Path, d: ExternalDevice) -> bool:
    text = devices_md.read_text(encoding="utf-8") if devices_md.exists() else DEVICES_HEADER
    key = f"| {d.device_id} |"
    if any(ln.startswith(key) and f"{d.call}/{d.folder}" in ln for ln in text.splitlines()):
        return False                                            # already there
    devices_md.parent.mkdir(parents=True, exist_ok=True)
    devices_md.write_text(text.rstrip("\n") + "\n" + _device_row(d) + "\n", encoding="utf-8")
    return True


def import_zip(zip_path, *, matrix_path=None, raw_root=None, devices_md=None, dry_run: bool = False) -> ImportResult:
    """Merge a result zip into the matrix (see the module docstring). Writes nothing when there is a
    contradiction or *dry_run* is set."""
    matrix_path = Path(matrix_path or cm.DATA_FILE)
    raw_root = Path(raw_root or RAW_ROOT)
    devices_md = Path(devices_md or raw_root / "devices.md")
    devices = read_results(zip_path)
    result = ImportResult(devices=devices)
    work = cm.load(matrix_path)
    for d in devices:
        if d.release not in cm.releases_of(work):
            try:
                work = cm.add_release(work, d.release)
            except cm.MatrixError as exc:
                raise ImportErrorExternal(f"{d.folder}: {exc}") from exc
            result.new_releases.append(d.release)
        source = f"{d.folder}/scan.csv"
        new, filled, conflicts = scan.apply_to_matrix(
            work, d.rows, d.release, d.date, d.device_id, source,
            evidence=f"ext {d.call} {d.date} {source}")
        if conflicts:
            result.conflicts += [f"[{d.device_id}] {c}" for c in conflicts]
        else:
            work, result.filled = new, result.filled + filled
    if result.conflicts or dry_run:
        return result
    if result.filled or result.new_releases:
        cm.save(work, matrix_path)
        result.written.append(str(matrix_path))
    for d in devices:
        for name, data in d.files.items():
            dest = raw_root / d.call / d.folder / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)                              # unchanged
            result.written.append(str(dest))
        if _add_device_row(devices_md, d):
            result.written.append(str(devices_md))
    return result


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description="Merge an external scan (results zip) into the command matrix")
    ap.add_argument("zip", help="results_<call>_<date>.zip from the scan kit")
    ap.add_argument("--matrix", help="the matrix data file (default: src/pk232py/data/command_matrix.csv)")
    ap.add_argument("--raw-dir", help="where the raw files go (default: docs/reference/external)")
    ap.add_argument("--dry-run", action="store_true", help="show what would happen, write nothing")
    args = ap.parse_args(argv)
    try:
        r = import_zip(args.zip, matrix_path=args.matrix, raw_root=args.raw_dir, dry_run=args.dry_run)
    except ImportErrorExternal as exc:
        print(f"[!] {exc}", file=sys.stderr)
        return 2
    for d in r.devices:
        print(f"[*] {d.device_id}: release {d.release}, {len(d.rows)} rows ({d.folder})")
    if r.conflicts:
        print("[!] CONTRADICTION - nothing was written. The same release gave another result than the matrix "
              "(or than another device): hardware variant or measurement error? To be judged by a person:",
              file=sys.stderr)
        for line in r.conflicts:
            print(f"    {line}", file=sys.stderr)
        return 3
    print(f"[+] {r.filled} cells {'would be ' if args.dry_run else ''}filled; new releases: "
          f"{', '.join(r.new_releases) or 'none'}")
    if not args.dry_run:
        print("[+] now run: python tools/gen_command_matrix.py --update")
        calls = sorted({d.call for d in r.devices})
        print("[!] Do NOT commit docs/reference/external/" + "/".join(calls) + " before the operator has given "
              "their consent (the README asks for it): the data goes into a public repository with the "
              "callsign as the source.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
