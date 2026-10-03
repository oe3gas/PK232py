# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""comm/mnemonic_registry.py - every Host Mode mnemonic the application sends,
with what it means and the evidence per firmware release (P80). Qt-free.

CLAUDE.md rule 6: never guess a mnemonic. This module is where the guessing is
made visible: a mnemonic WITHOUT evidence (``evidence == {}``) has only a
hypothesis behind it (the firmware matrix, docs/PK232_firmware_matrix.md,
"every row is a hypothesis"). tests/test_mnemonic_registry.py scans the source
for every mnemonic the application sends and fails when one is missing here,
so a NEW mnemonic cannot enter the code without an entry. docs/MNEMONIC_AUDIT.md
is generated from this table (tools/gen_mnemonic_audit.py).

``evidence`` maps a release (as printed in the boot banner) to the measurement:
  * for parameters in comm/host_params.py it is TAKEN from there
    (host_params.verified_sources) - never retyped;
  * for the rest it names the Testplan entry (``T112 (...)``);
  * a measurement without a known device is attributed to 13.SEP.95, because
    everything measured before device B (P37) came from device A (matrix 2a).
``meaning`` says what the matrix calls it; where the application USES the
mnemonic for something else, the text says so ("conflict") - those are the
first candidates for the measurement package (P80 Teil D).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pk232py.comm.host_params import HOST_PARAMS, verified_sources

# The columns of docs/MNEMONIC_AUDIT.md, as printed in the boot banner.
RELEASES = ("01.AUG.91", "13.SEP.95", "30.12.1988")


@dataclass(frozen=True)
class MnemonicEntry:
    mnemonic: bytes
    meaning: str              # e.g. "PACKET (global); matrix line 332, confidence M"
    kind: str                 # "mode" | "param" | "query" | "action" | "channel"
    evidence: dict = field(default_factory=dict)   # release -> "T151, T152"
    transmits: bool = False   # keys the transmitter (XM, CQ, ARQ call, connect ...)
    sent: bool = True         # False = the app does NOT send it (any more); kept to
                              # document a refuted assignment (P80a: MI, Ao)


# P80a: documented but no longer sent by the application.
_NOT_SENT = frozenset({"MI", "Ao", "PT", "NE", "XL", "EE", "MW", "CI", "MY"})

# (mnemonic, meaning, kind, transmits, evidence outside host_params)
_TABLE: tuple = (
    ('3R', '3RDPARTY (maildrop); matrix line 260, confidence L',
     'param', False, {}),
    ('8B', '8BITCONV (rtty); matrix line 353, confidence M',
     'param', False, {}),
    ('AC', 'ARQ call (amtor, main_window.py PACTOR connect); matrix line 180, confidence M',
     'action', True, {}),
    ('AD', 'ADELAY (amtor); matrix line 178, confidence M',
     'param', False, {}),
    ('AG', 'ACHG (amtor); matrix line 177, confidence M',
     'action', False, {}),
    ('AK', 'ACRPACK (packet); matrix line 292, confidence M',
     'param', False, {}),
    ('AL', 'ALIST (amtor); matrix line 179, confidence M',
     'action', False, {}),
    ('AM', 'AMTOR (global); matrix line 221, confidence M',
     'mode', False, {'01.AUG.91': 'T166 (ACK $00, OPAM0R, back to PA)', '13.SEP.95': 'T167 (ACK $00, OP OPAM0R, back to PA)'}),
    ('AO', 'ARQTMO; T151: AO answers the ARQTMO value, not ARQTOL [matrix line 181, confidence M]',
     'param', False, {}),
    ('AP', 'ALFPACK (packet); matrix line 293, confidence M',
     'param', False, {}),
    ('AR', 'ALFRTTY (rtty); matrix line 356, confidence M',
     'param', False, {}),
    ('AS', 'ASCII (global); matrix line 222, confidence M',
     'mode', False, {'01.AUG.91': 'T166 (ACK $00, OPASR, back to PA)', '13.SEP.95': 'T167 (ACK $00, OP OPASR, back to PA)'}),
    ('AU', 'AAB (amtor); matrix line 176, confidence M',
     'param', False, {}),
    ('AV', 'AX25L2V2 (packet); matrix line 294, confidence M',
     'param', False, {}),
    ('AY', 'ASPECT (fax); matrix line 201, confidence M',
     'param', False, {}),
    ('Ao', 'NOT SENT since P80a: ARQTOL has no known Host Mode command (T151: the verbose ARQTOL is ?What? on 01.AUG.91); the mixed-case spelling was a guess - not in matrix',
     'param', False, {}),
    ('BA', 'BAUDOT (global); matrix line 224, confidence M',
     'mode', False, {'01.AUG.91': 'T166 (ACK $00, OPBAR, back to PA)', '13.SEP.95': 'T167 (ACK $00, OP OPBAR, back to PA)'}),
    ('BB', 'BBSMSGS (maildrop); matrix line 261, confidence L',
     'param', False, {}),
    ('BT', 'BTEXT (packet); matrix line 298, confidence M',
     'param', False, {}),
    ('CF', 'CFROM (packet); matrix line 300, confidence M',
     'param', False, {}),
    ('CG', 'CONSTAMP (packet); matrix line 308, confidence M',
     'param', False, {}),
    ('CI', 'NOT SENT since P80b: CI is not CODE - the query answers CIN (a switch; matrix: CPACTIME) while the verbose CODE is 0 (T166/T167); the verbose upload is unchanged',
     'param', False, {}),
    ('CK', 'CHECK (packet); matrix line 303, confidence M',
     'param', False, {}),
    ('CL', 'CANLINE (global); matrix line 226, confidence M',
     'param', False, {}),
    ('CN', 'COMMAND (global); matrix line 228, confidence M',
     'param', False, {}),
    ('CO', 'CONNECT (packet); matrix line 306, confidence M',
     'channel', True, {'01.AUG.91': 'T148 (own connect lands on chip 1, observed)'}),
    ('CT', 'CTEXT (maildrop); matrix line 263, confidence L',
     'param', False, {}),
    ('DA', 'DAYTIME (global); matrix line 230, confidence M',
     'param', False, {}),
    ('DD', 'DIDDLE (rtty); matrix line 359, confidence M',
     'param', False, {}),
    ('DF', 'DFROM (packet); matrix line 310, confidence M',
     'param', False, {}),
    ('DI', 'DISCONNECT (packet); matrix line 311, confidence M',
     'channel', True, {}),
    ('DS', 'DAYSTAMP (global); matrix line 229, confidence M',
     'param', False, {}),
    ('DW', 'DWAIT (packet); matrix line 312, confidence M',
     'param', False, {}),
    ('EA', 'EAS (amtor); matrix line 185, confidence M',
     'param', False, {}),
    ('EE', 'NOT SENT since P80b: ERRCHAR has no Host Mode command under EE - $07 (unknown) on both devices (T166/T167); the verbose upload is unchanged. Matrix: ER for ERRCHAR (line 287), not measured',
     'param', False, {}),
    ('EX', 'EXPERT (global); matrix line 233, confidence L',
     'param', False, {}),
    ('FA', 'FAX (global); matrix line 234, confidence M',
     'mode', False, {'01.AUG.91': 'T166 (ACK $00, OPFA0R, back to PA)', '13.SEP.95': 'T167 (ACK $00, OP OPFA0R, back to PA)'}),
    ('FE', 'FEC (amtor); matrix line 186, confidence M',
     'action', True, {}),
    ('FN', 'FAXNEG (fax); matrix line 204, confidence M',
     'param', False, {}),
    ('FR', 'FRACK (packet); matrix line 313, confidence M',
     'param', False, {}),
    ('FS', 'FSPEED (fax); matrix line 205, confidence M',
     'param', False, {'01.AUG.91': 'T166 (query = verbose value; query only, not verified for setting)', '13.SEP.95': 'T167 (query = verbose value; query only, not verified for setting)'}),
    ('HB', 'HBAUD (packet); matrix line 315, confidence M',
     'param', False, {'13.SEP.95': 'T112 (restore reports HBaud was 300)'}),
    ('HD', 'HEADERLN (packet); matrix line 316, confidence M',
     'param', False, {}),
    ('HM', 'HOMEBBS (maildrop); matrix line 267, confidence L',
     'param', False, {}),
    ('HO', 'HOST (global); matrix line 236, confidence M',
     'action', False, {}),
    ('HP', 'HPOLL (packet); matrix line 317, confidence M',
     'param', False, {'13.SEP.95': 'T86 (late response frame after Host Mode entry)'}),
    ('IL', 'ILFPACK (packet); matrix line 318, confidence M',
     'param', False, {}),
    ('KL', 'KILONFWD (maildrop); matrix line 268, confidence L',
     'param', False, {}),
    ('LO', 'LOCK (fax); matrix line 209, confidence M',
     'action', False, {}),
    ('MD', 'MDIGI (T160/T161); the app has no MDPROMPT [matrix line 274, confidence L]',
     'param', False, {}),
    ('ME', 'MBELL (maildrop); matrix line 271, confidence L',
     'param', False, {}),
    ('MF', 'MFROM (packet); matrix line 322, confidence M',
     'param', False, {}),
    ('MG', 'MYSELCAL (amtor); matrix line 190, confidence M',
     'param', False, {}),
    ('MH', 'MHEARD (packet); matrix line 323, confidence M; T166/T167: a BARE MH answers only MH$01 (B) / MH$03 (A), no list - the app polls MH0..MH17 (main_window._on_packet_mheard), not bare MH',
     'query', False, {}),
    ('MI', 'MFILTER (measured: MI$80 = verbose MFILTER $80, T115). NOT SENT since P80a: the Packet MID button and the Morse ID spin box were wired to it by mistake; they are greyed out. No Morse ID mnemonic is known [matrix line 345, confidence L]',
     'param', False, {'13.SEP.95': 'T115 (MI$80 = verbose MFILTER $80)'}),
    ('MK', 'MYALTCAL; pactor.py also sends it as MYPTCALL; the matrix MDCHECK row is refuted (no MDCHECK mnemonic, T118) [matrix line 189, confidence M]',
     'param', False, {}),
    ('ML', 'MYCALL (packet); matrix line 327, confidence M',
     'param', False, {}),
    ('MN', 'MONITOR (packet); matrix line 324, confidence M',
     'param', False, {'13.SEP.95': 'T31 (ACK only)'}),
    ('MO', 'MORSE (global); matrix line 238, confidence M',
     'mode', False, {'01.AUG.91': 'T166 (ACK $00, OPMOR22, back to PA)', '13.SEP.95': 'T167 (ACK $00, OPMOR20, back to PA)'}),
    ('MP', 'MSPEED (morse); matrix line 286, confidence M',
     'param', False, {}),
    ('MQ', 'MPROTO (maildrop); matrix line 277, confidence L',
     'param', False, {}),
    ('MR', 'MRPT (packet); matrix line 325, confidence M',
     'param', False, {}),
    ('MS', 'MSTAMP (maildrop); matrix line 278, confidence L',
     'param', False, {}),
    ('MT', 'MTO (packet); matrix line 326, confidence M',
     'param', False, {}),
    ('MU', 'MMSG (maildrop); matrix line 276, confidence L',
     'param', False, {}),
    ('MV', 'MAILDROP (maildrop); matrix line 270, confidence L',
     'param', False, {}),
    ('MW', 'NOT SENT since P80b: MW is not MWEIGHT - the query answers MWN (a switch; matrix: MARSDISP) and a set of 11 gets $01 (T166/T167); the verbose upload is unchanged',
     'param', False, {}),
    ('MX', 'MAXFRAME (packet); matrix line 320, confidence M',
     'param', False, {'13.SEP.95': 'T31 (ACK only)'}),
    ('MY', 'NOT SENT since P80b: MYIDENT mapping unproven - $07 on device B, "MYnone" on device A (T166/T167, ambiguous; matrix: MYGATE); the verbose upload is unchanged',
     'param', False, {}),
    ('NA', 'NAVTEX (navtex); matrix line 290, confidence L',
     'mode', False, {'01.AUG.91': 'T166 (ACK $00, OPNA0, back to PA)', '13.SEP.95': 'T167 (ACK $00, OP OPNA0, back to PA)'}),
    ('NE', 'NEWMODE (pactor; matrix line 346). NOT SENT since P80b: the app used it as NAVTEX mode switch (hostmode.cmd_navtex, removed); T166/T167: the answer is NEY and OPMODE stays PA - a parameter, NAVTEX is NA',
     'param', False, {'01.AUG.91': 'T166 (query: NEY, OPMODE stays PA)', '13.SEP.95': 'T167 (query: NEY, OPMODE stays PA)'}),
    ('NM', 'NAVMSG (navtex); matrix line 288, confidence L',
     'param', False, {'01.AUG.91': 'T166 (query = verbose value; query only, not verified for setting)', '13.SEP.95': 'T167 (query = verbose value; query only, not verified for setting)'}),
    ('NS', 'NAVSTN (navtex); matrix line 289, confidence L',
     'param', False, {'01.AUG.91': 'T166 (query = verbose value; query only, not verified for setting)', '13.SEP.95': 'T167 (query = verbose value; query only, not verified for setting)'}),
    ('OP', 'OPMODE (global); matrix line 242, confidence M',
     'query', False, {'13.SEP.95': 'T141 (OP queried in Host Mode)'}),
    ('PA', 'PACKET (global); matrix line 243, confidence M',
     'mode', False, {'13.SEP.95': 'T31 (init frames ACKed, 2026-05-17, ACK only)'}),
    ('PB', 'PT200 (matrix line 347) [matrix line 347, confidence L]',
     'param', False, {}),
    ('PD', 'PTSEND; main_window.py sends it with "1,2" [matrix line 351, confidence L]',
     'action', True, {}),
    ('PE', 'PERSIST (packet); matrix line 331, confidence M',
     'param', False, {}),
    ('PH', 'PTHUFF (matrix section 3 text, no table row)',
     'param', False, {}),
    ('PL', 'PACLEN (packet); matrix line 328, confidence M',
     'param', False, {}),
    ('PN', 'PTLIST (pactor): enters the PTLIST mode (matrix line 349, confidence M)',
     'mode', False, {'13.SEP.95': 'T167 (ACK $00, OPPN1R1000, back to PA)'}),
    ('PP', 'PPERSIST (packet); matrix line 332, confidence M',
     'param', False, {}),
    ('PT', 'PACTIME (packet; matrix line 329). NOT SENT since P80b: the app used it as PACTOR standby, but T167 shows the answer "PTA 10" and OPMODE stays PA - a parameter, not a mode (T167)',
     'param', False, {'13.SEP.95': 'T167 (query: PTA 10, OPMODE stays PA)'}),
    ('PV', 'PTOVER (pactor); matrix line 350, confidence L',
     'param', False, {}),
    ('PX', 'PASSALL (packet); matrix line 330, confidence M',
     'param', False, {'13.SEP.95': 'T86, T111 (PXN/PXY)'}),
    ('Pr', 'PTROUND (pactor.py), mixed-case form - not in matrix',
     'param', False, {}),
    ('RB', 'RBAUD (rtty); matrix line 361, confidence M',
     'param', False, {'01.AUG.91': 'T166 (query = verbose value; query only, not verified for setting)', '13.SEP.95': 'T167 (query = verbose value; query only, not verified for setting)'}),
    ('RC', 'RCVE (return to receive) [matrix line 212, confidence M]',
     'action', False, {}),
    ('RF', 'RFEC (amtor); matrix line 192, confidence M',
     'param', False, {}),
    ('RP', 'RESPTIME (packet); matrix line 335, confidence M',
     'param', False, {}),
    ('RT', 'RESTART (danger); matrix line 200, confidence H',
     'action', False, {}),
    ('RX', 'RXREV (amtor); matrix line 193, confidence M',
     'param', False, {}),
    ('RY', 'RETRY (packet); matrix line 336, confidence M',
     'param', False, {}),
    ('SA', 'SAMPLE (global); matrix line 248, confidence M',
     'action', False, {}),
    ('SE', 'SELFEC (amtor); matrix line 194, confidence M',
     'action', True, {}),
    ('SI', 'SIGNAL (global); matrix line 249, confidence M',
     'mode', False, {'01.AUG.91': 'T166 (ACK $00, OPSI, back to PA)', '13.SEP.95': 'T167 (ACK $00, OP OPSI, back to PA)'}),
    ('SL', 'SLOTTIME (packet); matrix line 338, confidence M',
     'param', False, {'13.SEP.95': 'T112 (30 -> 10)'}),
    ('SP', 'SENDPAC (packet); matrix line 337, confidence M',
     'param', False, {}),
    ('SQ', 'SQUELCH toggle (main_window.py) [matrix line 339, confidence M]',
     'param', False, {}),
    ('SR', 'SRXALL (amtor); matrix line 195, confidence M',
     'param', False, {}),
    ('TD', 'TXDELAY (rtty); matrix line 362, confidence M',
     'param', False, {}),
    ('TL', 'TMAIL (maildrop); matrix line 281, confidence L',
     'param', False, {}),
    ('TN', 'TDCHAN (signal); matrix line 368, confidence L',
     'param', False, {}),
    ('TU', 'TDBAUD (signal); matrix line 367, confidence L',
     'param', False, {}),
    ('TV', 'TDM (signal); matrix line 369, confidence L',
     'mode', False, {'01.AUG.91': 'T166 (ACK $00, OPTV0R, back to PA)', '13.SEP.95': 'T167 (ACK $00, OP OPTV0R, back to PA)'}),
    ('TX', 'TXREV (amtor); matrix line 196, confidence M',
     'param', False, {}),
    ('UB', 'UBIT (maildrop); matrix line 282, confidence L',
     'param', False, {}),
    ('UN', 'UNPROTO (packet); matrix line 342, confidence M',
     'param', False, {'13.SEP.95': 'T101 (UI frame sent with the UNPROTO path)'}),
    ('UR', 'USERS (maildrop); matrix line 283, confidence L',
     'param', False, {}),
    ('US', 'USOS (rtty); matrix line 363, confidence M',
     'param', False, {}),
    ('VH', 'VHF (packet); matrix line 343, confidence M',
     'param', False, {'13.SEP.95': 'T112 (restore reports Vhf was OFF)'}),
    ('WI', 'WIDESHFT (amtor.py, rtty_baudot.py) - not in matrix',
     'param', False, {}),
    ('WO', 'WORDOUT (amtor); matrix line 197, confidence M',
     'param', False, {}),
    ('XL', 'NOT SENT since P80b: XLENGTH has no Host Mode command under XL - $07 (unknown) on both devices (T166/T167); the verbose upload is unchanged',
     'param', False, {}),
    ('XM', 'XMIT (fax); matrix line 214, confidence M',
     'action', True, {}),
    ('XO', 'XMITOK (global); matrix line 257, confidence M',
     'param', False, {}),
)


def _build() -> dict:
    registry: dict = {}
    for mnemonic, meaning, kind, transmits, evidence in _TABLE:
        registry[mnemonic.encode("ascii")] = MnemonicEntry(
            mnemonic.encode("ascii"), meaning, kind, dict(evidence), transmits,
            sent=mnemonic not in _NOT_SENT)
    # Parameters measured through host_params: take the evidence from there.
    for row in HOST_PARAMS:
        entry = registry.get(row.mnemonic)
        if entry is not None:
            entry.evidence.update(verified_sources(row.name))
    return dict(sorted(registry.items()))


REGISTRY: dict = _build()
