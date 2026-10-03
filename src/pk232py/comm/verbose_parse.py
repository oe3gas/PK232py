# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""comm/verbose_parse.py - the TNC's "was / now" confirmation of a verbose
parameter change, and which configuration field it belongs to (P78 B).

Qt-free. The TNC confirms every change it takes in the same way (real lines
from hw_logs, init upload and T151):

    MOnitor    was 4 (UA DM C D I UI)
    MOnitor    now 3 (UA DM C D I UI)
    UBit   0  was ON
    UBit   0  now OFF

The capital letters in the name mark the shortest abbreviation, so the name is
matched case-insensitively against the parameter names ParamsUploader sends.

Rule (P78 B, T162 finding 3): a parameter the operator changes in the verbose
terminal must reach the configuration - otherwise the next mode switch or Host
Mode entry sends the OLD configuration value over it. The configuration has one
writer for verbose changes: this parser, called by MainWindow for every verbose
output line.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

from pk232py.comm.host_params import BAND_PARAMS

# name -> (HFPacketConfig attribute | {band: attribute}, kind). The names are
# those of ParamsUploader._build_commands() (a test keeps the two in step).
HF_PACKET_FIELDS: dict = {
    "PACLEN":   ("paclen", "int"),
    "TXDELAY":  ("txdelay", "int"),
    "MAXFRAME": (BAND_PARAMS["MAXFRAME"], "int"),     # one value per band (P73)
    "FRACK":    ("frack", "int"),
    "RETRY":    ("retry", "int"),
    "PERSIST":  ("persist", "int"),
    "SLOTTIME": (BAND_PARAMS["SLOTTIME"], "int"),     # one value per band (P73)
    "DWAIT":    ("dwait", "int"),
    "CHECK":    ("check", "int"),
    "MONITOR":  ("monitor", "int"),
    "RESPTIME": ("resptime", "int"),
    "USERS":    ("users", "int"),
    "AX25L2V2": ("ax25l2v2", "bool"),
    "HEADERLN": ("headerln", "bool"),
    "CONSTAMP": ("constamp", "bool"),
    "DAYSTAMP": ("dagstamp", "bool"),
    "ILFPACK":  ("ilfpack", "bool"),
    "ACRPACK":  ("acrpack", "bool"),
    "ALFPACK":  ("alfpack", "bool"),
    "MRPT":     ("mrpt", "bool"),
    "PPERSIST": ("ppersist", "bool"),
    "XMITOK":   ("xmitok", "bool"),
    "8BITCONV": ("bitconv8", "bool"),
    "HID":      ("hid", "bool"),
    "MBELL":    ("mbell", "bool"),
    "MDIGI":    ("mdigi", "bool"),
    "MPROTO":   ("mproto", "bool"),
    "MSTAMP":   ("mstamp", "bool"),
    "PASSALL":  ("passall", "bool"),
    "BBSMSGS":  ("bbsmsgs", "bool"),
    "UBIT":     ("ubit0", "bool"),                    # index 0 only
    "UNPROTO":  ("unproto", "text"),
    "BTEXT":    ("btext", "text"),
    "CTEXT":    ("ctext", "text"),
    "MYCALL":   ("mycall", "text"),
}

_LINE_RE = re.compile(
    r"^\s*([A-Za-z0-9]+)(?:\s+(\d+))?\s+(was|now)\s+(.*?)\s*$")
_EXPLANATION_RE = re.compile(r"\s*\(.*\)\s*$")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _scan_line(line: str) -> Optional[tuple]:
    """(NAME, index, "was"|"now", value) of one line, or None."""
    m = _LINE_RE.match(line)
    if not m:
        return None
    name, index, word, value = m.groups()
    return name.upper(), index, word, _EXPLANATION_RE.sub("", value)


def _pairs(lines: Iterable[str]) -> list:
    """Every (NAME, old, new) whose "was" line is followed by the "now" line of
    the same parameter. UBIT is ours only with index 0."""
    pending: dict = {}
    out = []
    for line in lines:
        scanned = _scan_line(line)
        if scanned is None:
            continue
        name, index, word, value = scanned
        key = (name, index)
        if word == "was":
            pending[key] = value
        elif key in pending:
            old = pending.pop(key)
            if name == "UBIT" and index != "0":
                continue
            out.append((name, old, value))
    return out


def parse_was_now(lines: Iterable[str]) -> Optional[tuple]:
    """(NAME, old, new) of the first was/now pair in *lines*, or None.

    NAME is upper-case (the TNC's capitals only mark the abbreviation); the
    value loses a trailing explanation in parentheses ("30 (300 msec.)" ->
    "30"). A "was" without its "now", or the two of different parameters, give
    None."""
    found = _pairs(lines)
    return found[0] if found else None


class VerboseSync:
    """Feeds raw verbose output (arbitrary chunks) through parse_was_now().

    The TNC's answer may arrive split at any byte, so incomplete trailing text
    is kept until its line ends. feed() returns the (NAME, old, new) changes
    completed by this chunk."""

    def __init__(self) -> None:
        self._buffer = ""
        self._pending: dict = {}

    def feed(self, text: str) -> list:
        self._buffer += _CONTROL_RE.sub("", text.replace("\r", ""))
        *complete, self._buffer = self._buffer.split("\n")
        out = []
        for line in complete:
            scanned = _scan_line(line)
            if scanned is None:
                continue
            name, index, word, value = scanned
            key = (name, index)
            if word == "was":
                self._pending[key] = value
            elif key in self._pending:
                old = self._pending.pop(key)
                if name == "UBIT" and index != "0":
                    continue
                out.append((name, old, value))
        return out
