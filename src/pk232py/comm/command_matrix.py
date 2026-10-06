# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""comm/command_matrix.py - which command exists on which firmware (P88). Qt-free.

The ONE reader of ``data/command_matrix.csv``: the firmware knowledge that used to
be spread over devices.py, host_params.py, the mnemonic registry, the hypothesis
matrix and the test plan. A cell is ``yes`` / ``no`` / ``expert`` (present, needs
EXPERT ON) / ``?`` (not measured). ``?`` is the normal case: **never** set
``yes``/``no`` from a hypothesis. Every cell that is not ``?`` carries its evidence
(a test number + log, ``fw_scan 20260728``, ``operator 2026-10-06`` ...); a cell
only changes with a new piece of evidence (the old one stays in the git history).

Lernmodus: the file is validated while it is LOADED, so a row without evidence or a
misspelled value stops the application's tests at once instead of silently reading
as "unknown". Public interface (the only one the rest of the code may use):

    exists(name, release) -> "yes" | "no" | "expert" | "?"
    host(name)            -> the measured Host Mode mnemonic or None
    evidence(name, release) -> str
    kind(name)            -> "param" | "immediate" | "mode" | "action_tx" | "danger" | None
    entry(name)           -> MatrixEntry | None
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "command_matrix.csv"

# The firmware releases exactly as the boot banner prints them (docs/DEVICES.md).
RELEASES = ("01.AUG.91", "13.SEP.95", "30.DEC.88")
CELL_VALUES = ("yes", "no", "expert", "?")
KINDS = ("param", "immediate", "mode", "action_tx", "danger")

COLUMNS = (
    "name", "abbrev", "host", "kind", "default", "function", "src_desc",
    *(f"fw_{r}" for r in RELEASES),
    *(f"ev_{r}" for r in RELEASES),
    "note",
)


@dataclass(frozen=True)
class MatrixEntry:
    name: str
    abbrev: str
    host: str               # "" = not measured
    kind: str
    default: str
    function: str
    src_desc: str
    fw: dict = field(default_factory=dict)     # release -> yes/no/expert/?
    ev: dict = field(default_factory=dict)     # release -> evidence text
    note: str = ""


class MatrixError(ValueError):
    """The data file breaks one of the rules above."""


def _entry_from_row(row: dict, line: int) -> MatrixEntry:
    name = (row.get("name") or "").strip()
    where = f"line {line} ({name or '?'})"
    if not name or name != name.upper():
        raise MatrixError(f"{where}: the name must be upper case")
    kind = (row.get("kind") or "").strip()
    if kind not in KINDS:
        raise MatrixError(f"{where}: kind {kind!r} is not one of {KINDS}")
    fw, ev = {}, {}
    for release in RELEASES:
        cell = (row.get(f"fw_{release}") or "").strip()
        evidence = (row.get(f"ev_{release}") or "").strip()
        if cell not in CELL_VALUES:
            raise MatrixError(f"{where}: fw_{release} {cell!r} is not one of {CELL_VALUES}")
        if cell != "?" and not evidence:
            raise MatrixError(f"{where}: fw_{release} = {cell} has no evidence")
        fw[release], ev[release] = cell, evidence
    return MatrixEntry(
        name=name, abbrev=(row.get("abbrev") or "").strip(),
        host=(row.get("host") or "").strip(), kind=kind,
        default=(row.get("default") or "").strip(),
        function=(row.get("function") or "").strip(),
        src_desc=(row.get("src_desc") or "").strip(),
        fw=fw, ev=ev, note=(row.get("note") or "").strip(),
    )


def parse(text: str) -> dict:
    """{NAME: MatrixEntry} from CSV text. Checks the rules (columns, one row per name,
    sorted by name, evidence for every cell that is not ?)."""
    reader = csv.DictReader(io.StringIO(text))
    if tuple(reader.fieldnames or ()) != COLUMNS:
        raise MatrixError(f"columns {tuple(reader.fieldnames or ())} differ from {COLUMNS}")
    entries: dict = {}
    previous = ""
    for row in reader:
        entry = _entry_from_row(row, reader.line_num)
        if entry.name in entries:
            raise MatrixError(f"{entry.name}: listed twice")
        if entry.name < previous:
            raise MatrixError(f"{entry.name}: not sorted by name (after {previous})")
        entries[entry.name] = entry
        previous = entry.name
    return entries


def load(path: Optional[Path] = None) -> dict:
    return parse(Path(path or DATA_FILE).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _matrix() -> dict:
    return load()


def reload() -> None:
    """Forget the cached file (tests that point DATA_FILE elsewhere)."""
    _matrix.cache_clear()


def all_entries() -> dict:
    return dict(_matrix())


def entry(name: str) -> Optional[MatrixEntry]:
    return _matrix().get((name or "").strip().upper())


def exists(name: str, release: Optional[str]) -> str:
    """yes / no / expert / ? - and ? for an unknown name or release."""
    e = entry(name)
    if e is None or release not in RELEASES:
        return "?"
    return e.fw[release]


def host(name: str) -> Optional[str]:
    e = entry(name)
    return e.host or None if e else None


def evidence(name: str, release: Optional[str]) -> str:
    e = entry(name)
    if e is None or release not in RELEASES:
        return ""
    return e.ev[release]


def kind(name: str) -> Optional[str]:
    e = entry(name)
    return e.kind if e else None


def to_csv(entries: dict) -> str:
    """The data file for *entries*: sorted by name, UTF-8, LF, the fixed columns."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(COLUMNS)
    for name in sorted(entries):
        e = entries[name]
        writer.writerow([
            e.name, e.abbrev, e.host, e.kind, e.default, e.function, e.src_desc,
            *(e.fw[r] for r in RELEASES), *(e.ev[r] for r in RELEASES), e.note,
        ])
    return out.getvalue()


def save(entries: dict, path: Optional[Path] = None) -> None:
    Path(path or DATA_FILE).write_text(to_csv(entries), encoding="utf-8", newline="")
    reload()
