# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""comm/host_params.py - the ONE mapping from a verbose parameter name
(as ParamsUploader._build_commands() sends it) to its Host Mode mnemonic
(P71, Teil A). Qt-free.

EVERY mnemonic below is a HYPOTHESIS taken from
docs/PK232_firmware_matrix.md section 4 (confidence M/L, "matrix line N"
= the row of that file) - nothing here is measured. `hw_check.py
host_params_probe` (T151/T152) measures it; P72 then fills
`verified_releases`. Where the matrix has no row the mnemonic is b""
("not in matrix") and the probe never sends anything for that row.

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

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class HostParam:
    name: str                 # verbose name as in ParamsUploader
    mnemonic: bytes           # e.g. b"UR"; b"" = not in matrix
    kind: str                 # "int" | "bool" | "text" | "call" | "char"
    lo: Optional[int] = None  # int range, from the parameter dialogs
    hi: Optional[int] = None
    verified_releases: tuple = ()   # filled after T151 (P72)


HOST_PARAMS: tuple = (
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
    # UBIT 0 (P74): manual gives mnemonic UB (matrix: confidence L, not BASE), but the
    # argument form (0 N / 0N / 0 OFF / ...) is unmeasured until T156 - so b"" = the
    # probe and P72 send nothing. Fill in the mnemonic + form here, in ONE place.
    # Named "UBIT" like the verbose command (the coverage test compares first tokens).
    HostParam("UBIT", b"", "ubit"),
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

_BY_NAME = {p.name: p for p in HOST_PARAMS}


def param_by_name(name: str) -> Optional[HostParam]:
    """The table row for verbose *name*, or None."""
    return _BY_NAME.get(name.upper())
