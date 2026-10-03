# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""comm/host_params.py - the ONE mapping from a verbose parameter name
(as ParamsUploader._build_commands() sends it) to its Host Mode mnemonic
(P71, Teil A). Qt-free.

Every mnemonic below is a HYPOTHESIS taken from
docs/PK232_firmware_matrix.md section 4 (confidence M/L, "matrix line N"
= the row of that file) UNLESS the release is listed in its
`verified_releases` (P72, Teil A: measured by T151/T152/T156 - see the
`_VERIFIED_*` blocks below, one block per measurement). Only a verified
(parameter, release) pair may be set in Host Mode by the application
(ParamApplier); everything else is reported as "not verified". Where the
matrix has no row the mnemonic is b"" ("not in matrix") and nothing is
ever sent for that row.

The matrix gives two names one mnemonic (ARQTMO and ARQTOL are both AO;
MYALTCAL and MDCHECK are both MK) - exactly the kind of wrong assignment
the probe's verbose cross-check exposes: T151 showed AO is ARQTMO, so
ARQTOL has no mnemonic here. Every mnemonic in the table is unique.

`kind` says what the probe may do with a parameter: "int"/"bool" are set
to a test value; "text" is only queried (except BTEXT); "call" and "char"
(callsigns, control characters) are NEVER set - a wrong control-character
setting can cut the connection.
"ubit" (P74) is an indexed flag (UBIT 0); never set by the probe either.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Optional

# Releases exactly as printed in the boot banner (SerialManager.tnc_release).
RELEASE_B = "01.AUG.91"     # device B
RELEASE_A = "13.SEP.95"     # device A (docs/DEVICES.md, P72 Teil F)


@dataclass(frozen=True)
class HostParam:
    name: str                 # verbose name as in ParamsUploader
    mnemonic: bytes           # e.g. b"UR"; b"" = not in matrix
    kind: str                 # "int" | "bool" | "text" | "call" | "char"
    lo: Optional[int] = None  # int range, from the parameter dialogs
    hi: Optional[int] = None
    verified_releases: tuple = ()   # P72: releases where T151/T152/T156 verified it


_ROWS: tuple = (
    HostParam("EXPERT", b"EX", "bool"),   # matrix line 233, confidence L
    HostParam("MYCALL", b"ML", "call"),   # matrix line 327, confidence M
    HostParam("PACLEN", b"PL", "int", 1, 255),   # matrix line 328, confidence M
    HostParam("TXDELAY", b"TD", "int", 0, 255),   # matrix line 362, confidence M
    HostParam("MAXFRAME", b"MX", "int", 1, 7),   # matrix line 320, confidence M
    HostParam("FRACK", b"FR", "int", 0, 250),   # matrix line 313, confidence M
    HostParam("RETRY", b"RY", "int", 0, 15),   # matrix line 336, confidence M
    HostParam("PERSIST", b"PE", "int", 0, 255),   # matrix line 331, confidence M
    HostParam("SLOTTIME", b"SL", "int", 0, 250),   # matrix line 338, confidence M
    HostParam("DWAIT", b"DW", "int", 0, 250),   # matrix line 312, confidence M
    HostParam("CHECK", b"CK", "int", 0, 250),   # matrix line 303, confidence M
    HostParam("MONITOR", b"MN", "int", 0, 6),   # matrix line 324, confidence M
    HostParam("RESPTIME", b"RP", "int", 0, 250),   # matrix line 335, confidence M
    HostParam("USERS", b"UR", "int", 1, 10),   # matrix line 283, confidence L
    HostParam("AX25L2V2", b"AV", "bool"),   # matrix line 294, confidence M
    HostParam("HEADERLN", b"HD", "bool"),   # matrix line 316, confidence M
    HostParam("CONSTAMP", b"CG", "bool"),   # matrix line 308, confidence M
    HostParam("DAYSTAMP", b"DS", "bool"),   # matrix line 229, confidence M
    HostParam("ILFPACK", b"IL", "bool"),   # matrix line 318, confidence M
    HostParam("ACRPACK", b"AK", "bool"),   # matrix line 292, confidence M
    HostParam("ALFPACK", b"AP", "bool"),   # matrix line 293, confidence M
    HostParam("MRPT", b"MR", "bool"),   # matrix line 325, confidence M
    HostParam("PPERSIST", b"PP", "bool"),   # matrix line 332, confidence M
    HostParam("XMITOK", b"XO", "bool"),   # matrix line 257, confidence M
    HostParam("UNPROTO", b"UN", "text"),   # matrix line 342, confidence M
    HostParam("BTEXT", b"BT", "text"),   # matrix line 298, confidence M
    HostParam("CTEXT", b"CT", "text"),   # matrix line 263, confidence L
    HostParam("CFROM", b"CF", "text"),   # matrix line 300, confidence M
    HostParam("DFROM", b"DF", "text"),   # matrix line 310, confidence M
    HostParam("MFROM", b"MF", "text"),   # matrix line 322, confidence M
    HostParam("MTO", b"MT", "text"),   # matrix line 326, confidence M
    HostParam("8BITCONV", b"8B", "bool"),   # matrix line 353, confidence M
    HostParam("HID", b"", "bool"),   # not in matrix
    # P73 C: the Packet monitor flags. The mnemonics are matrix hypotheses that
    # T160 (device B) and T161 (device A) verified - see _PACKET_MONITOR_FLAGS.
    # FULLDP is not in the matrix and unknown to the TNC (removed again).
    HostParam("MBELL", b"ME", "bool"),      # confidence L
    HostParam("MDIGI", b"MD", "bool"),      # confidence L
    HostParam("MPROTO", b"MQ", "bool"),     # confidence L
    HostParam("MSTAMP", b"MS", "bool"),     # confidence L
    HostParam("PASSALL", b"PX", "bool"),    # confidence M (CLAUDE.md rule 6: PASSALL = PX)
    HostParam("BBSMSGS", b"BB", "bool"),    # confidence L
    HostParam("FULLDP", b"", "bool"),       # not in matrix
    # UBIT 0 (P74/P72): mnemonic UB per manual (matrix: confidence L, not BASE);
    # the Host Mode form was measured by T156 on device A: set "UB0 N|Y" (with a
    # space), query "UB0" -> "UBN"/"UBY" (see host_set_args / parse_host_answer).
    # Named "UBIT" like the verbose command (the coverage test compares first tokens).
    HostParam("UBIT", b"UB", "ubit"),
    HostParam("MYPTCALL", b"", "call"),   # not in matrix
    HostParam("PTHUFF", b"PH", "bool"),   # matrix section 3 text (generation marker), no table row; also modes/pactor.py
    HostParam("PT200", b"PB", "bool"),   # matrix line 347, confidence L
    HostParam("PTOVER", b"PV", "char"),   # matrix line 350, confidence L
    # matrix lists AO, but AO answers ARQTMO's value; ARQTOL is ?What? on 01.AUG.91 (T151)
    HostParam("ARQTOL", b"", "int", 1, 5),
    HostParam("MOPT", b"", "bool"),   # not in matrix
    HostParam("MYSELCAL", b"MG", "call"),   # matrix line 190, confidence M
    HostParam("MYALTCAL", b"MK", "call"),   # matrix line 189, confidence M
    HostParam("MYIDENT", b"", "call"),   # not in matrix
    HostParam("ARQTMO", b"AO", "int", 0, 250),   # matrix line 181, confidence M
    HostParam("ADELAY", b"AD", "int", 0, 250),   # matrix line 178, confidence M
    HostParam("TDBAUD", b"TU", "int", 0, 200),   # matrix line 367, confidence L
    HostParam("TDCHAN", b"TN", "int", 0, 3),   # matrix line 368, confidence L
    HostParam("RFEC", b"RF", "bool"),   # matrix line 192, confidence M
    HostParam("RXREV", b"RX", "bool"),   # matrix line 193, confidence M
    HostParam("TXREV", b"TX", "bool"),   # matrix line 196, confidence M
    HostParam("MSPEED", b"MP", "int", 5, 99),   # matrix line 286, confidence M
    HostParam("MWEIGHT", b"", "int", 10, 90),   # not in matrix
    HostParam("CODE", b"", "int", 0, 8),   # not in matrix
    HostParam("ALFRTTY", b"AR", "bool"),   # matrix line 356, confidence M
    HostParam("DIDDLE", b"DD", "bool"),   # matrix line 359, confidence M
    HostParam("AAB", b"AU", "text"),   # matrix line 176, confidence M
    HostParam("CANLINE", b"CL", "char"),   # matrix line 226, confidence M
    HostParam("CANPAC", b"", "char"),   # not in matrix
    HostParam("COMMAND", b"CN", "char"),   # matrix line 228, confidence M
    HostParam("SENDPAC", b"SP", "char"),   # matrix line 337, confidence M
    HostParam("HOMEBBS", b"HM", "call"),   # matrix line 267, confidence L
    HostParam("MYMAIL", b"", "call"),   # not in matrix
    HostParam("MAILDROP", b"MV", "bool"),   # matrix line 270, confidence L
    HostParam("MDMON", b"", "bool"),   # not in matrix
    HostParam("MMSG", b"MU", "bool"),   # matrix line 276, confidence L
    HostParam("TMAIL", b"TL", "bool"),   # matrix line 281, confidence L
    HostParam("3RDPARTY", b"3R", "bool"),   # matrix line 260, confidence L
    HostParam("KILONFWD", b"KL", "bool"),   # matrix line 268, confidence L
    HostParam("MTEXT", b"", "text"),   # not in matrix
    HostParam("DAYTIME", b"DA", "text"),   # matrix line 230, confidence M
)

# --- P72 Teil A: measured releases ------------------------------------------
# T151 (device B, 01.10.2026 20:55, hw_logs/20261001_205535_host_params_probe.log,
# `host_params_probe --part A --exclude IL`; the log has no banner - the device
# is the operator's statement; `--reevaluate` of that log gives exactly these 37
# as `verified`: set, ACK `<mn> $00`, read back, verbose cross-check with the
# test value). ILFPACK is NOT in the list (only `verified_query`, T155/B.3).
_VERIFIED_B_T151 = frozenset({
    "PACLEN", "TXDELAY", "MAXFRAME", "FRACK", "RETRY", "PERSIST", "SLOTTIME",
    "DWAIT", "CHECK", "MONITOR", "RESPTIME", "USERS", "AX25L2V2", "HEADERLN",
    "CONSTAMP", "DAYSTAMP", "ACRPACK", "ALFPACK", "MRPT", "PPERSIST", "XMITOK",
    "8BITCONV", "ARQTMO", "ADELAY", "TDBAUD", "TDCHAN", "RFEC", "RXREV",
    "TXREV", "MSPEED", "ALFRTTY", "DIDDLE", "MAILDROP", "MMSG", "TMAIL",
    "3RDPARTY", "KILONFWD",
})
# T138 A.3 / A.5 (device B, 27.09.2026): UN and CF set in Host Mode and
# confirmed in verbose mode.
_VERIFIED_B_T138 = frozenset({"UNPROTO", "CFROM"})
# T151 on device A (01.10.2026 22:07, hw_logs/20261001_220703_host_params_probe.log,
# banner `release=13.SEP.95 pactor=yes`; `--reevaluate` gives verified=39): the same
# 37 as on device B plus PTHUFF and PT200 (PACTOR firmware). UNPROTO/CFROM were
# measured on B only (T138); ILFPACK stays verified_query.
_VERIFIED_A_T151 = _VERIFIED_B_T151 | frozenset({"PTHUFF", "PT200"})
# T152 (device A, 02.10.2026, hw_logs/20261002_172135_host_params_probe.log):
# set, ACK, read back = test value, WHILE CONNECTED, link unchanged afterwards.
_VERIFIED_A_T152 = frozenset({
    "USERS", "MAXFRAME", "PACLEN", "FRACK", "RETRY", "MONITOR", "TXDELAY",
})
# T156 (device A, 02.10.2026 16:28, hw_logs/20261002_162823_ubit_probe.log, no
# banner - device A per the operator): UBIT 0 set "UB0 N", query "UB0" -> "UBN",
# verbose confirmed, survives the VHF mode-switch frames.
_VERIFIED_A_T156 = frozenset({"UBIT"})
# T156 on device B (02.10.2026 19:46, hw_logs/20261002_194624_ubit_probe.log,
# banner `release=01.AUG.91`): `UB0 N` -> `UB $00`, query `UB0` -> `UBN`, verbose
# `UBIT 0` = OFF, survives the VHF mode-switch frames. Same form as on device A.
_VERIFIED_B_T156 = frozenset({"UBIT"})
# T160 (device B, 03.10.2026 14:41, hw_logs/20261003_144153_host_params_probe.log,
# banner `release=01.AUG.91`) and T161 (device A, 03.10.2026 14:50,
# hw_logs/20261003_145006_host_params_probe.log, banner `release=13.SEP.95`):
# the Packet monitor flags (P73 C). Per row on both devices: query `<mn>N`, set
# `<mn> $00`, query `<mn>Y`, verbose cross-check ON, restored to OFF.
_PACKET_MONITOR_FLAGS = frozenset({
    "MBELL", "MDIGI", "MPROTO", "MSTAMP", "PASSALL", "BBSMSGS",
})
_VERIFIED_B_T160 = _PACKET_MONITOR_FLAGS
_VERIFIED_A_T161 = _PACKET_MONITOR_FLAGS


def _verified_releases(name: str) -> tuple:
    releases = []
    if name in _VERIFIED_B_T151 or name in _VERIFIED_B_T138 or name in _VERIFIED_B_T156 \
            or name in _VERIFIED_B_T160:
        releases.append(RELEASE_B)
    if name in _VERIFIED_A_T151 or name in _VERIFIED_A_T152 or name in _VERIFIED_A_T156 \
            or name in _VERIFIED_A_T161:
        releases.append(RELEASE_A)
    return tuple(releases)


# ---------------------------------------------------------------------------
# P73 B: parameters with ONE value per band. The TNC holds one MAXFRAME and one
# SLOTTIME; the configuration holds an HF and a VHF value. This table is the
# ONE place that says which config attribute belongs to which band - the mode
# frames (HF/VHF Packet activation) and ParamsUploader's "what changed" both
# read it, so a live change can never overwrite the other band's value.
# ---------------------------------------------------------------------------

BAND_HF = "HF"
BAND_VHF = "VHF"

BAND_PARAMS: dict = {
    "MAXFRAME": {BAND_HF: "maxframe", BAND_VHF: "vhf_maxframe"},
    "SLOTTIME": {BAND_HF: "slottime", BAND_VHF: "vhf_slottime"},
}

# Operating mode name (ModeManager) -> band; every other mode has no band.
_MODE_BANDS = {"HF Packet": BAND_HF, "VHF Packet": BAND_VHF}


def band_of_mode(mode_name: Optional[str]) -> Optional[str]:
    """The band a ModeManager mode name stands for, or None (not a Packet mode)."""
    return _MODE_BANDS.get(mode_name or "")


def band_value(hf_config, name: str, band: str) -> int:
    """The configured value of band-dependent parameter *name* for *band*
    (*hf_config* is an HFPacketConfig)."""
    return getattr(hf_config, BAND_PARAMS[name][band])


HOST_PARAMS: tuple = tuple(
    replace(row, verified_releases=_verified_releases(row.name)) for row in _ROWS
)

_BY_NAME = {p.name: p for p in HOST_PARAMS}


def param_by_name(name: str) -> Optional[HostParam]:
    """The table row for verbose *name*, or None."""
    return _BY_NAME.get(name.upper())


# ---------------------------------------------------------------------------
# Answer / argument formats (T151, T152, T156) - the ONE place, both
# directions. Used by ParamApplier and tools/hw_check.py.
# ---------------------------------------------------------------------------

def host_error_code(set_resp: Optional[bytes]) -> Optional[int]:
    """The error code if *set_resp* is an error answer: a lone byte, or
    a 2-letter mnemonic plus ONE byte, in $01-$1F (TRM 4.3 - e.g. $09 'not
    while connected'; measured: $07 = command unknown on this device).
    $00 is the plain acknowledge; $0D alone is an empty text, not an error."""
    if not set_resp:
        return None
    body = set_resp
    if len(body) == 3 and body[:2].isalnum():
        body = body[2:]
    if len(body) == 1 and 0x01 <= body[0] <= 0x1F and body[0] != 0x0D:
        return body[0]
    return None


def host_set_args(param: HostParam, value: str) -> bytes:
    """Host Mode argument bytes for setting *param* to the verbose-style
    *value* (what ParamsUploader sends after the name): numbers as ASCII
    decimal, switches Y/N, text literal, empty text as CR, UBIT 0 as
    "0 N" (OFF) / "0 Y" (ON) - with the space, T156."""
    v = (value or "").strip()
    if param.kind == "ubit":
        on = v.split()[-1].upper() in ("ON", "Y", "YES", "1") if v else False
        return b"0 Y" if on else b"0 N"
    if param.kind == "bool":
        return b"Y" if v.upper() in ("ON", "Y", "YES", "1", "TRUE") else b"N"
    if param.kind == "int":
        return str(int(v)).encode("ascii")
    if not v:
        return b"\r"
    return v.encode("ascii", errors="replace")


def host_query_args(param: HostParam) -> bytes:
    """Argument bytes of the Host Mode query: none, except UBIT (index 0)."""
    return b"0" if param.kind == "ubit" else b""


def parse_host_answer(param: HostParam, data: Optional[bytes]) -> Optional[str]:
    """The value in a Host Mode answer (the bytes after the mnemonic), or
    None if *data* is missing, is an error byte, or does not start with the
    mnemonic - never guessed (rule 6). UBIT: "UBN" -> "OFF", "UBY" -> "ON".
    Empty text (a lone CR) gives ""."""
    if not data or not param.mnemonic or not data.startswith(param.mnemonic):
        return None
    if host_error_code(data) is not None:
        return None
    rest = data[len(param.mnemonic):].decode("ascii", errors="replace").strip()
    if param.kind == "ubit":
        return {"N": "OFF", "Y": "ON"}.get(rest.upper())
    return rest


def norm_value(value: Optional[str], kind: str) -> str:
    """Comparable form of a parameter value (P71a, moved here by P72):
    bools Y/N (ON/OFF/YES/NO/1/0 folded; UBIT likewise), ints as their
    number, text upper-cased with the TNC's own reformatting of lists
    removed (T138 A.4: "UN APZ232 VIA A,B" comes back as
    "APZ232 via A, B")."""
    text = (value or "").strip().upper()
    if kind == "ubit" and text:
        text = text.split()[-1]       # verbose "0 ON" / "0  OFF" -> ON / OFF
    if kind in ("bool", "ubit"):
        if text in ("Y", "YES", "ON", "1"):
            return "Y"
        if text in ("N", "NO", "OFF", "0"):
            return "N"
    if kind == "int" and re.fullmatch(r"-?\d+", text):
        return str(int(text))
    if kind in ("text", "call", "char"):
        return re.sub(r"\s*,\s*", ",", re.sub(r"\s+", " ", text))
    return text
