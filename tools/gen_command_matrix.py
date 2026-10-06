# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""P88: write docs/COMMAND_MATRIX.md from src/pk232py/data/command_matrix.csv.

    python tools/gen_command_matrix.py            # check: exit 1 if the file is stale
    python tools/gen_command_matrix.py --update   # rewrite docs/COMMAND_MATRIX.md

NOT part of the shipped application. The data file is the ONE truth; the markdown is a
generated view of it (like docs/MNEMONIC_AUDIT.md). tests/test_command_matrix.py imports
render() from here, so the test and the file can never disagree.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from pk232py.comm import command_matrix as cm  # noqa: E402
from pk232py.comm.devices import KNOWN_DEVICES  # noqa: E402

VIEW_FILE = REPO / "docs" / "COMMAND_MATRIX.md"


def _label(release: str) -> str:
    return next((d.label for d in KNOWN_DEVICES if d.release == release), "?")


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render(entries: dict) -> str:
    """The markdown view of *entries* (a dict as cm.load() returns it)."""
    lines = [
        "# Command / firmware matrix",
        "",
        "> GENERATED from `src/pk232py/data/command_matrix.csv` by `tools/gen_command_matrix.py --update` -",
        "> do not edit. The CSV is the ONE truth about which command exists on which firmware (P88).",
        "> `yes` present, `no` answers `?What?`, `expert` present but needs EXPERT ON, `?` not measured.",
        "> A cell that is not `?` has its evidence in the last column (`A` = 13.SEP.95, `B` = 01.AUG.91,",
        "> `C` = 30.DEC.88, docs/DEVICES.md).",
        "",
        "## Cells per firmware",
        "",
        "| Release | Device | yes | no | expert | ? |",
        "|---|---|---|---|---|---|",
    ]
    for release in cm.RELEASES:
        counts = {v: sum(1 for e in entries.values() if e.fw[release] == v) for v in cm.CELL_VALUES}
        lines.append(f"| {release} | {_label(release)} | {counts['yes']} | {counts['no']} | "
                     f"{counts['expert']} | {counts['?']} |")
    lines += [
        "",
        f"{len(entries)} commands.",
        "",
        "## Commands",
        "",
        "| Name | Abbrev | Host | Kind | " + " | ".join(cm.RELEASES) + " | Default | Function | Evidence |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name in sorted(entries):
        e = entries[name]
        evidence = "; ".join(f"{_label(r)}: {e.ev[r]}" for r in cm.RELEASES if e.ev[r])
        note = f" ({e.note})" if e.note else ""
        lines.append(
            f"| {_cell(e.name)} | {_cell(e.abbrev)} | {_cell(e.host)} | {e.kind} | "
            + " | ".join(e.fw[r] for r in cm.RELEASES)
            + f" | {_cell(e.default)} | {_cell(e.function)}{_cell(note)} | {_cell(evidence)} |"
        )
    effects = [(n, entries[n]) for n in sorted(entries) if any(entries[n].fx.get(r) for r in cm.RELEASES)]
    if effects:
        lines += [
            "",
            "## Effect and way back of risky commands (P89)",
            "",
            "> What the command did on the device and how the command mode was reached again "
            "(`tools/pk232_fw_scan.py --all`, no radio connected).",
            "",
            "| Name | Kind | " + " | ".join(cm.RELEASES) + " |",
            "|---|---|---|---|---|",
        ]
        for name, e in effects:
            lines.append(f"| {_cell(name)} | {e.kind} | "
                         + " | ".join(_cell(e.fx.get(r, "")) for r in cm.RELEASES) + " |")
    return "\n".join(lines) + "\n"


def main(argv: list) -> int:
    text = render(cm.load())
    if "--update" in argv:
        VIEW_FILE.write_text(text, encoding="utf-8", newline="")
        print(f"written: {VIEW_FILE}")
        return 0
    current = VIEW_FILE.read_text(encoding="utf-8").replace("\r\n", "\n") if VIEW_FILE.exists() else ""
    if current != text:
        print("docs/COMMAND_MATRIX.md is stale - run: python tools/gen_command_matrix.py --update")
        return 1
    print("docs/COMMAND_MATRIX.md is up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
