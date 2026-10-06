#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ORIGIN (P88 Teil A): handed over by the operator on 06.10.2026, taken from the chat
# "PK232 Befehle nach Firmware-Version testen" (July 2026). OLDER VERSION: it still contains
# AMOTR (a typo, measured UNSUPPORTED) and probes TRANS, which breaks the session (afterwards
# TRFLOW/XFLOW answer ERROR). Content unchanged apart from this comment; it is brought up to
# date in P88 Teil D (command list from the matrix, never probes danger commands, CR only).
"""
pk232_fw_scan.py  --  PK-232(MBX) firmware capability scanner / validator

WAS DIESES TOOL MACHT
=====================
Es verbindet sich mit einem PK-232 (Verbose-/Command-Mode, NICHT Host Mode),
liest den Firmware-Release-Stempel aus dem Einschalt-Banner ("Release DD.MM.YY")
und prueft anschliessend Befehl fuer Befehl, ob die tatsaechlich eingebaute
Firmware den jeweiligen Befehl kennt. Am Ende steht ein Abgleich zwischen
"erwartet laut Firmware-Generation" und "vom Geraet tatsaechlich bestaetigt".

WARUM SO (Lernmodus)
====================
Ein sauberer "welcher Befehl kam mit welchem EPROM"-Verlauf ist aus den alten
AEA/Timewave-Unterlagen nicht luecklos belegbar. Deshalb ist die statische
Matrix in COMMAND_DB nur eine *Hypothese* mit Konfidenz-Kennzeichnung. Die
Wahrheit liefert dieses Skript direkt am Geraet. Wer es auf mehreren EPROMs
laufen laesst (bei OE3GAS: 30.12.1988 / 01.08.1991 / 11.09.1995) und die
CSV-Reports vergleicht, bekommt die *empirische* Matrix geschenkt.

SICHERHEIT ZUERST
=================
Ein naiver Scan, der jeden Zwei-Buchstaben-Mnemonic blind absetzt, ist
gefaehrlich:
  * RESET  loescht das batteriegepufferte RAM (alle Einstellungen weg).
  * REINT  setzt die meisten Parameter auf Default zurueck.
  * XMIT / CONNECT / ARQ / FEC / SENDPAC ... TASTEN DEN SENDER (on air!).
  * BAUDOT / ASCII / MORSE / FAX / PACKET / NAVTEX ... verlassen den
    Command-Mode und schalten die Betriebsart um.
Deshalb wird jeder Befehl in COMMAND_DB als eine von zwei Proben eingestuft:
  Probe.QUERY : Parameter-Befehl. Nacktes Absetzen zeigt nur den Wert an
                -> voellig ungefaehrlich, wird automatisch geprueft.
  Probe.SKIP  : Aktions-/Modus-/Zerstoerbefehl. Wird NIE automatisch
                abgesetzt; seine Verfuegbarkeit wird aus Banner-Datum +
                den (sicheren) Generations-Markern abgeleitet.

Das genuegt fuer das Ziel: die grosse Mehrheit sind Parameter-Befehle und
damit sicher pruefbar; die wenigen Aktions-Befehle werden ueber die
Generation bestimmt. Kein Byte geht dabei ungewollt auf die Antenne.

BEDIENUNG
=========
  python pk232_fw_scan.py --port COM16                # echter Scan
  python pk232_fw_scan.py --port COM16 --csv out.csv  # + CSV-Report
  python pk232_fw_scan.py --port COM16 --probe-all    # ALLES aktiv testen*
  python pk232_fw_scan.py --port COM16 --debug log.txt # + Debug-Log (TX/RX)
  python pk232_fw_scan.py --selftest 1991             # Trockenlauf (Mock)
  python pk232_fw_scan.py --matrix                    # Markdown-Matrix drucken

  * --probe-all setzt AUCH Sende-, Modus- und RESET-Befehle ab (sonst
    NOT_PROBED). Nur mit abgezogenem Funkgeraet und gesicherten Einstellungen!
    Reboot-Befehle (RESET/REINIT/RESTART) werden zuletzt geprueft, danach wird
    EXPERT neu entsperrt.

Standard: 9600 Baud, 8N1, xonxoff=False (siehe SerialManager-Konventionen).
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import re
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ----------------------------------------------------------------------------
# 1. Firmware-Generationen
# ----------------------------------------------------------------------------
# Wir modellieren drei grobe Generationen. Die Grenzen entsprechen den
# belegten AEA-Meilensteinen:
#   GEN_BASE  : Ur-PK-232 (1986..) -- RTTY/ASCII/AMTOR/CW/Packet/FAX, KISS
#   GEN_MBX   : PK-232MBX (Ende 1989/1990) -- Mailbox/MailDrop, NAVTEX
#   GEN_PACTOR: PACTOR + Gateway (ab 1993, v7.x) -- PT*-Familie, MFILTER, ...
#
# Merke: "gen" eines Befehls = FRUEHESTE Generation, die ihn kennt. Ein
# GEN_BASE-Befehl ist folglich in ALLEN drei Generationen vorhanden.

class Gen(int, Enum):
    BASE = 1     # 1988er-Klasse
    MBX = 2      # 1991er-Klasse (Mailbox)
    PACTOR = 3   # 1995er-Klasse (PACTOR/Gateway)


GEN_LABEL = {
    Gen.BASE:   "BASE (>=1988, Ur-PK-232)",
    Gen.MBX:    "MBX  (>=1990, Mailbox/NAVTEX)",
    Gen.PACTOR: "PACT (>=1993, PACTOR/Gateway)",
}

# Zuordnung der bekannten Release-Daten des Benutzers zu einer Generation.
# (Reihenfolge: Grenzdatum -> Generation. Wird per <= geprueft.)
KNOWN_RELEASES = [
    ("1988-12-30", Gen.BASE),    # 30.12.1988 -> Ur-Klasse (kein MBX, kein PACTOR)
    ("1991-08-01", Gen.MBX),     # 01.08.1991 -> Mailbox, aber vor PACTOR
    ("1995-09-11", Gen.PACTOR),  # 11.09.1995 -> PACTOR/Gateway vorhanden
]


# ----------------------------------------------------------------------------
# 2. Proben-Typen und Konfidenz
# ----------------------------------------------------------------------------
class Probe(str, Enum):
    QUERY = "Q"   # sicher: nacktes Absetzen zeigt nur den Wert
    SKIP = "S"    # Aktion/Modus/zerstoerend: nie automatisch absetzen


class Conf(str, Enum):
    H = "H"       # gut belegt
    M = "M"       # plausibel
    L = "L"       # unsicher -- der Scan soll das aufklaeren


@dataclass
class Cmd:
    mnem: str          # 2-Buchstaben-Mnemonic (Host-Mode-Kuerzel)
    name: str          # voller Verbose-Befehlsname
    group: str         # funktionale Gruppe (nur zur Gliederung)
    gen: Gen           # frueheste Generation (Hypothese)
    probe: Probe       # QUERY oder SKIP
    conf: Conf = Conf.M
    note: str = ""


# ----------------------------------------------------------------------------
# 3. Die Befehls-Datenbank (Hypothese)
# ----------------------------------------------------------------------------
# Quelle der Namen: Host-Mode-Mnemonic-Scan der v7.1 (superset). Die
# gen/probe/conf-Spalten sind kuratiert -- bei Unsicherheit Conf.L, damit der
# empirische Scan die Luecken schliesst. Kompakt als Tupel, unten expandiert.
#
#   (mnem, name, group, gen, probe, conf[, note])
# _RAW: vollstaendiger Befehlssatz aus der STABO-Befehlszusammenfassung
# (Superset der juengsten Firmware) -- 194 Befehle. Autogeneriert,
# gen/probe/conf teils kuratiert, sonst heuristisch (Conf.L = vom Scan zu klaeren).
# _RAW: vollstaendiger Befehlssatz = UNION aus STABO-Befehlszusammenfassung
# UND der v7.1-Hardware-Mnemonic-Tabelle -- 205 Befehle. Autogeneriert;
# gen/probe/conf teils kuratiert, sonst heuristisch (Conf.L = vom Scan zu klaeren).
_RAW = [
    # --- amtor ---
    ("AU", "AAB", "amtor", Gen.BASE, Probe.QUERY, Conf.M),
    ("AG", "ACHG", "amtor", Gen.BASE, Probe.SKIP, Conf.M, "direct"),
    ("AD", "ADELAY", "amtor", Gen.BASE, Probe.QUERY, Conf.M),
    ("AL", "ALIST", "amtor", Gen.BASE, Probe.SKIP, Conf.M, "read-only list"),
    ("AM", "AMOTR", "amtor", Gen.BASE, Probe.QUERY, Conf.L),
    ("AC", "ARQ", "amtor", Gen.BASE, Probe.SKIP, Conf.M, "direct"),
    ("AO", "ARQTMO", "amtor", Gen.BASE, Probe.QUERY, Conf.M),
    ("AO", "ARQTOL", "amtor", Gen.BASE, Probe.QUERY, Conf.M),
    ("CU", "CBELL", "amtor", Gen.BASE, Probe.QUERY, Conf.M),
    ("DC", "DCDCONN", "amtor", Gen.BASE, Probe.QUERY, Conf.M),
    ("EA", "EAS", "amtor", Gen.BASE, Probe.QUERY, Conf.M),
    ("FE", "FEC", "amtor", Gen.BASE, Probe.SKIP, Conf.M, "direct"),
    ("ID", "ID", "amtor", Gen.BASE, Probe.SKIP, Conf.M, "direct"),
    ("MW", "MARSDISP", "amtor", Gen.BASE, Probe.QUERY, Conf.M),
    ("MK", "MYALTCAL", "amtor", Gen.BASE, Probe.QUERY, Conf.M),
    ("MG", "MYSELCAL", "amtor", Gen.BASE, Probe.QUERY, Conf.M),
    ("OV", "OVER", "amtor", Gen.BASE, Probe.SKIP, Conf.M, "AMTOR/PACTOR changeover"),
    ("RF", "RFEC", "amtor", Gen.BASE, Probe.QUERY, Conf.M),
    ("RX", "RXREV", "amtor", Gen.BASE, Probe.QUERY, Conf.M),
    ("SE", "SELFEC", "amtor", Gen.BASE, Probe.SKIP, Conf.M, "direct"),
    ("SR", "SRXALL", "amtor", Gen.BASE, Probe.QUERY, Conf.M),
    ("TX", "TXREV", "amtor", Gen.BASE, Probe.QUERY, Conf.M),
    ("WO", "WORDOUT", "amtor", Gen.BASE, Probe.QUERY, Conf.M),
    # --- danger ---
    ("RI", "REINIT", "danger", Gen.MBX, Probe.SKIP, Conf.H, "resets most params"),
    ("RS", "RESET", "danger", Gen.BASE, Probe.SKIP, Conf.H, "WIPES bbRAM"),
    ("RT", "RESTART", "danger", Gen.BASE, Probe.SKIP, Conf.H, "reboot (tool uses it)"),
    # --- fax ---
    ("AY", "ASPECT", "fax", Gen.BASE, Probe.QUERY, Conf.M),
    ("AQ", "AUDELAY", "fax", Gen.BASE, Probe.QUERY, Conf.M),
    ("CW", "CWID", "fax", Gen.BASE, Probe.QUERY, Conf.M),
    ("FN", "FAXNEG", "fax", Gen.BASE, Probe.QUERY, Conf.M),
    ("FS", "FSPEED", "fax", Gen.BASE, Probe.QUERY, Conf.M),
    ("GR", "GRAPHICS", "fax", Gen.BASE, Probe.QUERY, Conf.M),
    ("JU", "JUSTIFY", "fax", Gen.BASE, Probe.SKIP, Conf.M, "direct"),
    ("LR", "LEFTRITE", "fax", Gen.BASE, Probe.QUERY, Conf.M),
    ("LO", "LOCK", "fax", Gen.BASE, Probe.SKIP, Conf.M, "direct"),
    ("PF", "PRFAX", "fax", Gen.BASE, Probe.QUERY, Conf.M),
    ("PY", "PRTYPE", "fax", Gen.BASE, Probe.QUERY, Conf.M),
    ("RC", "RCVE", "fax", Gen.BASE, Probe.SKIP, Conf.M, "direct"),
    ("TR", "TRACE", "fax", Gen.BASE, Probe.QUERY, Conf.M),
    ("XM", "XMIT", "fax", Gen.BASE, Probe.SKIP, Conf.M, "direct"),
    # --- global ---
    ("5B", "5BIT", "global", Gen.BASE, Probe.SKIP, Conf.M, "direct"),
    ("6B", "6BIT", "global", Gen.BASE, Probe.SKIP, Conf.M, "direct"),
    ("AA", "ACRDISP", "global", Gen.BASE, Probe.QUERY, Conf.M),
    ("AE", "ADDRESS", "global", Gen.BASE, Probe.QUERY, Conf.M),
    ("AZ", "AFILTER", "global", Gen.BASE, Probe.QUERY, Conf.M),
    ("AI", "ALFDISP", "global", Gen.BASE, Probe.QUERY, Conf.M),
    ("AM", "AMTOR", "global", Gen.BASE, Probe.SKIP, Conf.M, "direct"),
    ("AS", "ASCII", "global", Gen.BASE, Probe.SKIP, Conf.M, "direct"),
    ("AW", "AWLEN", "global", Gen.BASE, Probe.QUERY, Conf.M),
    ("BA", "BAUDOT", "global", Gen.BASE, Probe.SKIP, Conf.M, "direct"),
    ("BK", "BKONDEL", "global", Gen.BASE, Probe.QUERY, Conf.M),
    ("CL", "CANLINE", "global", Gen.BASE, Probe.QUERY, Conf.M),
    ("CQ", "CMDTIME", "global", Gen.BASE, Probe.QUERY, Conf.M),
    ("CN", "COMMAND", "global", Gen.BASE, Probe.QUERY, Conf.M),
    ("DS", "DAYSTAMP", "global", Gen.BASE, Probe.QUERY, Conf.M),
    ("DA", "DAYTIME", "global", Gen.BASE, Probe.QUERY, Conf.M),
    ("EC", "ECHO", "global", Gen.BASE, Probe.QUERY, Conf.M),
    ("ES", "ESCAPE", "global", Gen.BASE, Probe.QUERY, Conf.M),
    ("EX", "EXPERT", "global", Gen.MBX, Probe.QUERY, Conf.L, "unlocks expert cmds; verbose-only"),
    ("FA", "FAX", "global", Gen.BASE, Probe.SKIP, Conf.M, "direct"),
    ("FL", "FLOW", "global", Gen.BASE, Probe.QUERY, Conf.M),
    ("HO", "HOST", "global", Gen.BASE, Probe.QUERY, Conf.M),
    ("IO", "IO", "global", Gen.BASE, Probe.QUERY, Conf.M),
    ("MO", "MORSE", "global", Gen.BASE, Probe.SKIP, Conf.M, "direct"),
    ("NR", "NUCR", "global", Gen.BASE, Probe.QUERY, Conf.M),
    ("NF", "NULF", "global", Gen.BASE, Probe.QUERY, Conf.M),
    ("NU", "NULLS", "global", Gen.BASE, Probe.QUERY, Conf.M),
    ("OP", "OPMODE", "global", Gen.PACTOR, Probe.QUERY, Conf.M, "safe: queries opmode"),
    ("PA", "PACKET", "global", Gen.BASE, Probe.SKIP, Conf.M, "direct"),
    ("PR", "PARITY", "global", Gen.BASE, Probe.QUERY, Conf.M),
    ("PC", "PRCON", "global", Gen.BASE, Probe.QUERY, Conf.M),
    ("PO", "PROUT", "global", Gen.BASE, Probe.QUERY, Conf.M),
    ("RD", "REDISPLAY", "global", Gen.BASE, Probe.QUERY, Conf.M),
    ("SA", "SAMPLE", "global", Gen.BASE, Probe.SKIP, Conf.M, "direct"),
    ("SI", "SIGNAL", "global", Gen.BASE, Probe.SKIP, Conf.M, "direct"),
    ("ST", "START", "global", Gen.BASE, Probe.QUERY, Conf.M),
    ("SO", "STOP", "global", Gen.BASE, Probe.QUERY, Conf.M),
    ("TB", "TBAUD", "global", Gen.BASE, Probe.QUERY, Conf.M),
    ("TC", "TCLEAR", "global", Gen.BASE, Probe.SKIP, Conf.M, "direct"),
    ("TM", "TIME", "global", Gen.BASE, Probe.QUERY, Conf.M),
    ("TW", "TRFLOW", "global", Gen.BASE, Probe.QUERY, Conf.M),
    ("XW", "XFLOW", "global", Gen.BASE, Probe.QUERY, Conf.M),
    ("XO", "XMITOK", "global", Gen.BASE, Probe.QUERY, Conf.M),
    ("XF", "XOFF", "global", Gen.BASE, Probe.QUERY, Conf.M),
    ("XN", "XON", "global", Gen.BASE, Probe.QUERY, Conf.M),
    # --- maildrop ---
    ("3R", "3RDPARTY", "maildrop", Gen.MBX, Probe.QUERY, Conf.L),
    ("BB", "BBSMSGS", "maildrop", Gen.MBX, Probe.QUERY, Conf.L),
    ("CM", "CMSG", "maildrop", Gen.MBX, Probe.QUERY, Conf.L),
    ("CT", "CTEXT", "maildrop", Gen.MBX, Probe.QUERY, Conf.L),
    ("DL", "DELETE", "maildrop", Gen.MBX, Probe.QUERY, Conf.L),
    ("FZ", "FREE", "maildrop", Gen.MBX, Probe.SKIP, Conf.L, "direct"),
    ("HR", "HEREIS", "maildrop", Gen.MBX, Probe.QUERY, Conf.L),
    ("HM", "HOMEBBS", "maildrop", Gen.MBX, Probe.QUERY, Conf.L),
    ("KL", "KILONFWD", "maildrop", Gen.MBX, Probe.QUERY, Conf.L),
    ("LM", "LASTMSG", "maildrop", Gen.MBX, Probe.QUERY, Conf.L),
    ("MV", "MAILDROP", "maildrop", Gen.MBX, Probe.QUERY, Conf.L),
    ("ME", "MBELL", "maildrop", Gen.MBX, Probe.QUERY, Conf.L),
    ("MB", "MBX", "maildrop", Gen.MBX, Probe.QUERY, Conf.H, "GEN-MARKER MBX"),
    ("MK", "MDCHECK", "maildrop", Gen.MBX, Probe.SKIP, Conf.L, "direct"),
    ("MD", "MDIGI", "maildrop", Gen.MBX, Probe.QUERY, Conf.L),
    ("MM", "MEMORY", "maildrop", Gen.MBX, Probe.QUERY, Conf.M, "verify read-only"),
    ("MU", "MMSG", "maildrop", Gen.MBX, Probe.QUERY, Conf.L),
    ("MQ", "MPROTO", "maildrop", Gen.MBX, Probe.QUERY, Conf.L),
    ("MS", "MSTAMP", "maildrop", Gen.MBX, Probe.QUERY, Conf.L),
    ("MA", "MYALIAS", "maildrop", Gen.MBX, Probe.QUERY, Conf.L),
    ("MY", "MYGATE", "maildrop", Gen.MBX, Probe.QUERY, Conf.L),
    ("NO", "NOMODE", "maildrop", Gen.MBX, Probe.QUERY, Conf.L),
    ("TL", "TMAIL", "maildrop", Gen.MBX, Probe.QUERY, Conf.L),
    ("UB", "UBIT", "maildrop", Gen.MBX, Probe.QUERY, Conf.L),
    ("UR", "USERS", "maildrop", Gen.MBX, Probe.QUERY, Conf.L),
    # --- misc ---
    ("RE", "RECEIVE", "misc", Gen.BASE, Probe.SKIP, Conf.M, "name implies action"),
    # --- morse ---
    ("MP", "MSPEED", "morse", Gen.BASE, Probe.QUERY, Conf.M),
    # --- navtex ---
    ("ER", "ERRCHAR", "navtex", Gen.MBX, Probe.QUERY, Conf.L),
    ("NM", "NAVMSG", "navtex", Gen.MBX, Probe.QUERY, Conf.L),
    ("NS", "NAVSTN", "navtex", Gen.MBX, Probe.QUERY, Conf.L),
    ("NA", "NAVTEX", "navtex", Gen.MBX, Probe.SKIP, Conf.L, "direct"),
    # --- packet ---
    ("AN", "ACKPRIOR", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("AK", "ACRPACK", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("AP", "ALFPACK", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("AV", "AX25L2V2", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("AX", "AXDELAY", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("AH", "AXHANG", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("BE", "BEACON", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("BT", "BTEXT", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("CP", "CANPAC", "packet", Gen.BASE, Probe.SKIP, Conf.M, "direct"),
    ("CX", "CASEDISP", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("CF", "CFROM", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("CB", "CHCALL", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("CD", "CHDOUBLE", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("CK", "CHECK", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("CH", "CHSWITCH", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("CE", "CONMODE", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("CO", "CONNECT", "packet", Gen.BASE, Probe.SKIP, Conf.M, "direct"),
    ("CY", "CONPERM", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("CG", "CONSTAMP", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("CI", "CPACTIME", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("DF", "DFROM", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("DI", "DISCONNECT", "packet", Gen.BASE, Probe.SKIP, Conf.M, "direct"),
    ("DW", "DWAIT", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("FR", "FRACK", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("FU", "FULLDUP", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("HB", "HBAUD", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("HD", "HEADERLN", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("HI", "HID", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("HP", "HPOLL", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("IL", "ILFPACK", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("KI", "KISS", "packet", Gen.BASE, Probe.QUERY, Conf.H, "param; KISS ON enters KISS"),
    ("KA", "KISSADDR", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("MX", "MAXFRAME", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("MC", "MCON", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("MF", "MFROM", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("MH", "MHEARD", "packet", Gen.BASE, Probe.SKIP, Conf.M, "read-only list"),
    ("MN", "MONITOR", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("MR", "MRPT", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("MT", "MTO", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("ML", "MYCALL", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("PL", "PACLEN", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("PT", "PACTIME", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("PX", "PASSALL", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("PE", "PERSIST", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("PP", "PPERSIST", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("RW", "RAWHDLC", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("RL", "RELINK", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("RP", "RESPTIME", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("RY", "RETRY", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("SP", "SENDPAC", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("SL", "SLOTTIME", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("SQ", "SQUELCH", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("71", "TRIES", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("TF", "TXFLOW", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("UN", "UNPROTO", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("VH", "VHF", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    ("WN", "WHYNOT", "packet", Gen.BASE, Probe.QUERY, Conf.M),
    # --- pactor ---
    ("MI", "MFILTER", "pactor", Gen.PACTOR, Probe.QUERY, Conf.L),
    ("NE", "NEWMODE", "pactor", Gen.PACTOR, Probe.QUERY, Conf.L),
    ("PB", "PT200", "pactor", Gen.PACTOR, Probe.QUERY, Conf.L),
    ("PG", "PTCON", "pactor", Gen.PACTOR, Probe.SKIP, Conf.L, "direct"),
    ("PW", "PTDOWN", "pactor", Gen.PACTOR, Probe.SKIP, Conf.M, "direct"),
    ("PH", "PTHUFF", "pactor", Gen.PACTOR, Probe.QUERY, Conf.H, "GEN-MARKER PACTOR"),
    ("PN", "PTLIST", "pactor", Gen.PACTOR, Probe.SKIP, Conf.M, "read-only list"),
    ("PV", "PTOVER", "pactor", Gen.PACTOR, Probe.QUERY, Conf.L),
    ("PD", "PTSEND", "pactor", Gen.PACTOR, Probe.QUERY, Conf.L),
    ("PU", "PTUP", "pactor", Gen.PACTOR, Probe.SKIP, Conf.M, "direct"),
    ("UC", "UCMD", "pactor", Gen.PACTOR, Probe.QUERY, Conf.L),
    # --- rtty ---
    ("8B", "8BITCONV", "rtty", Gen.BASE, Probe.QUERY, Conf.M),
    ("AB", "ABAUD", "rtty", Gen.BASE, Probe.QUERY, Conf.M),
    ("AT", "ACRRTTY", "rtty", Gen.BASE, Probe.QUERY, Conf.M),
    ("AR", "ALFRTTY", "rtty", Gen.BASE, Probe.QUERY, Conf.M),
    ("BI", "BITINV", "rtty", Gen.BASE, Probe.QUERY, Conf.M),
    ("CC", "CCITT", "rtty", Gen.BASE, Probe.QUERY, Conf.M),
    ("CR", "CRADD", "rtty", Gen.BASE, Probe.QUERY, Conf.M),
    ("DD", "DIDDLE", "rtty", Gen.BASE, Probe.QUERY, Conf.M),
    ("PS", "PASS", "rtty", Gen.BASE, Probe.QUERY, Conf.M),
    ("RB", "RBAUD", "rtty", Gen.BASE, Probe.QUERY, Conf.M),
    ("TD", "TXDELAY", "rtty", Gen.BASE, Probe.QUERY, Conf.M),
    ("US", "USOS", "rtty", Gen.BASE, Probe.QUERY, Conf.M),
    ("WI", "WIDESHFT", "rtty", Gen.BASE, Probe.QUERY, Conf.H),
    ("WR", "WRU", "rtty", Gen.BASE, Probe.QUERY, Conf.M),
    ("XB", "XBAUD", "rtty", Gen.BASE, Probe.QUERY, Conf.M),
    # --- signal ---
    ("CI", "CODE", "signal", Gen.BASE, Probe.QUERY, Conf.M),
    ("NX", "NUMS", "signal", Gen.MBX, Probe.SKIP, Conf.L, "direct"),
    ("OK", "OK", "signal", Gen.BASE, Probe.SKIP, Conf.M, "direct"),
    ("TU", "TDBAUD", "signal", Gen.MBX, Probe.QUERY, Conf.L),
    ("TN", "TDCHAN", "signal", Gen.MBX, Probe.QUERY, Conf.L),
    ("TV", "TDM", "signal", Gen.MBX, Probe.SKIP, Conf.L, "direct"),
    # --- discovered from ROM extraction (04.MAR.87 image) ---
    ("K",  "CONVERSE", "global", Gen.BASE, Probe.SKIP, Conf.M, "enters converse mode"),
    ("T",  "TRANS",    "global", Gen.BASE, Probe.SKIP, Conf.M, "enters transparent mode"),
    ("CS", "CSTATUS",  "packet", Gen.BASE, Probe.SKIP, Conf.M, "read-only link status"),
    ("DI", "DISPLAY",  "global", Gen.BASE, Probe.SKIP, Conf.M, "dumps all params (direct)"),
    ("CA", "CALIBRATE","danger", Gen.BASE, Probe.SKIP, Conf.M, "keys TX tones -- never auto"),
    # --- GPS/APRS commands (v7.x, verified: GPS Operation Addendum #040-187-1 + ROM) ---
    ("GE", "GENDCHAR", "gps", Gen.PACTOR, Probe.QUERY, Conf.H, "string end char (def $0D)"),
    ("GI", "GINITEXT", "gps", Gen.PACTOR, Probe.QUERY, Conf.H, "GPS init string"),
    ("GL", "GLOCTX", "gps", Gen.PACTOR, Probe.QUERY, Conf.H, "location TX timer 0-2500s/10"),
    ("GN", "GNMEA1", "gps", Gen.PACTOR, Probe.QUERY, Conf.H, "1st NMEA sentence (def GPGLL)"),
    ("GM", "GNMEA2", "gps", Gen.PACTOR, Probe.QUERY, Conf.H, "2nd NMEA sentence"),
    ("GP", "GPOLLCAL", "gps", Gen.PACTOR, Probe.QUERY, Conf.H, "polling callsign"),
    ("GS", "GPSAUTO", "gps", Gen.PACTOR, Probe.QUERY, Conf.H, "auto-detect GPS on power-up"),
    ("G0", "GPSMODE", "gps", Gen.PACTOR, Probe.QUERY, Conf.H, "GPS mode 0-3"),
    ("GG", "GREMPROG", "gps", Gen.PACTOR, Probe.QUERY, Conf.H, "remote programming in GPS mode"),
    ("GY", "GSYMCHAR", "gps", Gen.PACTOR, Probe.QUERY, Conf.H, "APRS symbol char 0-255"),
    ("GU", "GUNSTART", "gps", Gen.PACTOR, Probe.QUERY, Conf.H, "power up in CONVERSE mode"),
    # --- live-confirmed extras (v7.1 hardware scan) ---
    ("HY", "HOSTKEY", "global", Gen.PACTOR, Probe.QUERY, Conf.H, "hex value $0000; host-mode key; live-confirmed (not in disp gps)"),
    ("GT", "GTRES", "gps", Gen.PACTOR, Probe.QUERY, Conf.H, "ON/OFF; UNDOCUMENTED; in GPS block, live-confirmed"),
    # --- from full v7.1 'disp z' dump (hardware-confirmed parameters) ---
    ("LT", "ALTMODEM", "signal", Gen.MBX, Probe.QUERY, Conf.H, "alternate modem select"),
    ("ARX", "ARXTOR", "amtor", Gen.MBX, Probe.QUERY, Conf.H, "AMTOR auto-RX"),
    ("ATX", "ATXRTTY", "amtor", Gen.MBX, Probe.QUERY, Conf.H, "AMTOR-to-RTTY TX delay"),
    ("UT", "AUTOBAUD", "global", Gen.MBX, Probe.QUERY, Conf.H, "terminal autobaud"),
    ("CUS", "CUSTOM", "signal", Gen.MBX, Probe.QUERY, Conf.H, "custom modem value"),
    ("FI", "FRICK", "global", Gen.MBX, Probe.QUERY, Conf.H, "keying/timing delay"),
    ("GUS", "GUSERS", "gps", Gen.PACTOR, Probe.QUERY, Conf.H, "GPS users count"),
    ("LI", "LITE", "global", Gen.MBX, Probe.QUERY, Conf.H, "lite mode"),
    ("DM", "MDMON", "maildrop", Gen.MBX, Probe.QUERY, Conf.H, "maildrop monitor"),
    ("DP", "MDPROMPT", "maildrop", Gen.MBX, Probe.QUERY, Conf.H, "maildrop prompt text"),
    ("MID", "MID", "maildrop", Gen.MBX, Probe.QUERY, Conf.H, "mailbox ID timer"),
    ("MOP", "MOPTT", "global", Gen.MBX, Probe.QUERY, Conf.H, "modem PTT option"),
    ("TE", "MTEXT", "maildrop", Gen.MBX, Probe.QUERY, Conf.H, "mailbox welcome text"),
    ("WE", "MWEIGHT", "morse", Gen.MBX, Probe.QUERY, Conf.H, "CW keying weight"),
    ("MXM", "MXMIT", "maildrop", Gen.BASE, Probe.QUERY, Conf.H, "maildrop xmit"),
    ("YI", "MYIDENT", "maildrop", Gen.MBX, Probe.QUERY, Conf.H, "mailbox ident"),
    ("YM", "MYMAIL", "maildrop", Gen.MBX, Probe.QUERY, Conf.H, "mailbox forward call"),
    ("YP", "MYPTCALL", "pactor", Gen.PACTOR, Probe.QUERY, Conf.H, "my PACTOR callsign"),
    ("PTR", "PTROUND", "pactor", Gen.PACTOR, Probe.QUERY, Conf.H, "PACTOR round toggle"),
    ("RR", "RFRAME", "packet", Gen.MBX, Probe.QUERY, Conf.H, "receive-frame toggle"),
    ("TP", "TMPROMPT", "maildrop", Gen.MBX, Probe.QUERY, Conf.H, "TMail prompt text"),
    # --- from PK232 Command Summary v1.0 (4-30-91) ---
    ("CON", "CONOK", "packet", Gen.BASE, Probe.QUERY, Conf.H, "legacy TAPR; use CFROM instead"),
    ("DG", "DIGIPEAT", "packet", Gen.BASE, Probe.QUERY, Conf.H, "TAPR-compat digipeat toggle"),
    ("HE", "HELP", "global", Gen.BASE, Probe.SKIP, Conf.H, "displays important commands (direct)"),
]
def _build_db() -> dict[str, Cmd]:
    db: dict[str, Cmd] = {}
    for row in _RAW:
        mnem, name, group, gen, probe, conf = row[:6]
        note = row[6] if len(row) > 6 else ""
        db[name] = Cmd(mnem, name, group, gen, probe, conf, note)
    return db


COMMAND_DB: dict[str, Cmd] = _build_db()


# ----------------------------------------------------------------------------
# 4. Firmware-Datum -> Generation
# ----------------------------------------------------------------------------
def release_to_gen(release_iso: str) -> Optional[Gen]:
    """Bildet ein ISO-Datum (YYYY-MM-DD) auf die passende Generation ab.

    Logik: das kleinste Generations-Grenzdatum, das >= dem Release ist, gewinnt
    nicht -- wir nehmen die Generation des naechst-passenden bekannten Standes.
    Praktisch reicht ein einfacher Schwellenwert-Vergleich, weil die drei
    bekannten Staende sauber getrennt sind.
    """
    try:
        d = _dt.date.fromisoformat(release_iso)
    except ValueError:
        return None
    # Schwellen: < 1990-01 -> BASE ; < 1993-01 -> MBX ; sonst PACTOR
    if d < _dt.date(1990, 1, 1):
        return Gen.BASE
    if d < _dt.date(1993, 1, 1):
        return Gen.MBX
    return Gen.PACTOR


# Banner-Datum robust nach ISO wandeln. Der PK-232 gibt den Monat als
# 3-Buchstaben-ENGLISCH aus ("Release 13.SEP.95") -- NICHT numerisch. Aeltere
# Staende/Dokumente nutzen teils numerisch ("11.09.95"), daher beide zulassen.
_MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
     "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], start=1)}
# Bevorzugt am Wort 'Release' verankert (vermeidet Fehltreffer wie 'Ver. 7.1'),
# Monat als 3-Buchstaben-Name ODER 1-2 Ziffern.
_REL_RE = re.compile(
    r"Release\s+(\d{1,2})[.\-/]([A-Za-z]{3}|\d{1,2})[.\-/](\d{2,4})", re.IGNORECASE)
# Fallback ohne Anker, falls die Formatierung abweicht.
_REL_RE_FALLBACK = re.compile(
    r"\b(\d{1,2})[.\-/]([A-Za-z]{3}|\d{1,2})[.\-/](\d{2,4})\b", re.IGNORECASE)


def _parse_month(tok: str) -> Optional[int]:
    """'SEP'/'sep' -> 9, '09'/'9' -> 9. None, wenn unbekannt."""
    if tok.isdigit():
        return int(tok)
    return _MONTHS.get(tok[:3].upper())


def parse_release_date(banner: str) -> Optional[str]:
    """Extrahiert das Release-Datum aus dem Sign-on-Banner als ISO-String.

    Der Banner enthaelt eine Zeile wie 'Release 13.SEP.95'. Wir suchen zuerst
    an 'Release' verankert, sonst grosszuegig; der Monat darf als englischer
    3-Buchstaben-Name (JAN..DEC) ODER numerisch stehen.
    """
    m = _REL_RE.search(banner) or _REL_RE_FALLBACK.search(banner)
    if not m:
        return None
    dd = int(m.group(1))
    mm = _parse_month(m.group(2))
    yy = int(m.group(3))
    if mm is None:
        return None
    if yy < 100:                      # zweistellig -> 19xx (PK-232-Aera)
        yy += 1900 if yy >= 80 else 2000
    try:
        return _dt.date(yy, mm, dd).isoformat()
    except ValueError:
        return None


# ----------------------------------------------------------------------------
# 5. Serieller Transport (echt) und Mock (Selftest)
# ----------------------------------------------------------------------------
CTRL_C = b"\x03"          # zurueck zum cmd:-Prompt
STAR = b"*"               # Autobaud-Ausloeser nach RESTART
CR = b"\r"


class DebugLog:
    """Schreibt jeden gesendeten Befehl UND jede TNC-Antwort mit Zeitstempel.

    Steuerzeichen werden via repr() sichtbar ('\\r', '\\x03', ...). Die
    Antwort-Zeile enthaelt zusaetzlich die gemessene Wartezeit -- so sieht man
    sofort, ob ein 'ERROR' an einer leeren oder einer zu spaeten Antwort liegt.
    Alles wird sofort geflusht (kein Datenverlust bei Strg-C).
    """

    def __init__(self, path: str):
        self.fh = open(path, "w", encoding="utf-8")
        self.path = path
        self.t0 = time.time()
        self.fh.write(f"# PK-232 scan debug log -- "
                      f"{_dt.datetime.now().isoformat(timespec='seconds')}\n")
        self.fh.write("# [t+sec] TAG: data   "
                      "(TX=gesendet | RX=empfangen mit Wartezeit | --=Notiz)\n\n")
        self.fh.flush()

    def _ts(self) -> float:
        return time.time() - self.t0

    def tx(self, data: bytes) -> None:
        self.fh.write(f"[{self._ts():7.3f}] TX: "
                      f"{bytes(data).decode('latin-1', 'replace')!r}\n")
        self.fh.flush()

    def rx(self, text: str, waited: float) -> None:
        self.fh.write(f"[{self._ts():7.3f}] RX ({waited:5.3f}s): {text!r}\n")
        self.fh.flush()

    def note(self, msg: str) -> None:
        self.fh.write(f"[{self._ts():7.3f}] -- {msg}\n")
        self.fh.flush()

    def close(self) -> None:
        try:
            self.fh.close()
        except Exception:
            pass


def _dbg(t):
    """Hilfsfunktion: liefert das DebugLog eines Transports (oder None)."""
    return getattr(t, "debug", None)


class SerialTransport:
    """Duenne Huelle um pyserial mit den Projekt-Konventionen.

    WICHTIG (aus SerialManager-Erfahrung):
      * xonxoff=False  -- sonst verschluckt pyserial das $11-XON-Byte.
      * frisches Serial-Objekt -- hier unkritisch, weil wir keinen
        Host-Mode-Subprozess davor haben.
    """

    def __init__(self, port: str, baud: int = 9600, timeout: float = 0.4,
                 debug: Optional["DebugLog"] = None):
        import serial  # lokal importiert, damit --selftest ohne pyserial laeuft
        self.debug = debug
        self.ser = serial.Serial(
            port=port, baudrate=baud, bytesize=8,
            parity=serial.PARITY_NONE, stopbits=1,
            timeout=timeout, xonxoff=False, rtscts=False, dsrdtr=False,
        )

    def write(self, data: bytes) -> None:
        if self.debug:
            self.debug.tx(data)
        self.ser.write(data)
        self.ser.flush()

    def read_idle(self, idle_s: float = 0.25, max_s: float = 3.0) -> str:
        """Liest, bis idle_s lang nichts mehr kommt (oder max_s erreicht ist).

        Das ist derselbe Idle-Detection-Trick wie write_verbose_wait(): der
        PK-232 kennt kein sauberes End-Token, also warten wir auf Sende-Stille.
        """
        buf = bytearray()
        t_start = time.time()
        t_end = t_start + max_s
        last = time.time()
        while time.time() < t_end:
            chunk = self.ser.read(256)
            if chunk:
                buf.extend(chunk)
                last = time.time()
            elif time.time() - last >= idle_s:
                break
        text = buf.decode("latin-1", errors="replace")
        if self.debug:
            self.debug.rx(text, time.time() - t_start)
        return text

    def close(self) -> None:
        try:
            self.ser.close()
        except Exception:
            pass


class MockTransport:
    """Simuliert einen PK-232 einer bestimmten Generation -- fuer --selftest.

    Nur so schlau wie noetig: er kennt seinen Release-Banner und antwortet auf
    Parameter-Abfragen entweder mit einem Wert-Echo (unterstuetzt) oder mit
    '*** What?' (unbekannt), je nachdem ob der Befehl in seiner Generation
    existiert.
    """

    def __init__(self, gen: Gen, release_iso: str,
                 debug: Optional["DebugLog"] = None):
        self.gen = gen
        self.release = _dt.date.fromisoformat(release_iso)
        self.debug = debug
        self._pending = ""
        self._last_cmd = ""
        # EXPERT existiert erst ab MBX. Default OFF -> Expertenebene gesperrt.
        self.has_expert = gen >= Gen.MBX
        self.expert_on = False

    # Befehle, die auch bei EXPERT OFF erreichbar bleiben muessen (Anfaenger-
    # Ebene). EXPERT selbst MUSS zugaenglich sein, sonst koennte man es nie
    # einschalten. (Direkte Befehle sind ohnehin SKIP und werden nicht abgefragt.)
    _BEGINNER = {"EXPERT", "MYCALL", "HBAUD", "VHF", "MONITOR"}

    def write(self, data: bytes) -> None:
        if self.debug:
            self.debug.tx(data)
        text = data.decode("latin-1")
        if data == CTRL_C:
            self._pending = "cmd:"
            return
        if data == STAR:
            return
        if text.strip().upper().startswith("RESTART"):
            # Echtes Geraeteformat nachbilden: 'Release 13.SEP.95' (Monat als
            # englische 3-Buchstaben-Abkuerzung), damit der Selftest den
            # tatsaechlichen Parser-Pfad prueft.
            mon = next(k for k, v in _MONTHS.items() if v == self.release.month)
            d = f"{self.release.day:02d}.{mon}.{self.release.strftime('%y')}"
            self._pending = (
                "\r\nPK-232M is using default values.\r\n"
                "AEA PK-232M Data Controller\r\n"
                "Copyright (C) 1986-1994 by\r\n"
                "Advanced Electronic Applications, Inc.\r\n"
                f"Release {d}\r\ncmd:"
            )
            return

        name = text.strip().upper()
        self._last_cmd = name

        # EXPERT ON/OFF/Abfrage nachbilden
        if name.startswith("EXPERT"):
            if not self.has_expert:
                self._pending = "*** What?\r\ncmd:"       # Ur-Firmware kennt EXPERT nicht
                return
            arg = name[6:].strip()
            if arg == "ON":
                self.expert_on = True
                self._pending = "EXPert was OFF\r\nEXPert now ON\r\ncmd:"
            elif arg == "OFF":
                self.expert_on = False
                self._pending = "EXPert was ON\r\nEXPert now OFF\r\ncmd:"
            else:  # reine Abfrage
                self._pending = f"EXPert {'ON' if self.expert_on else 'OFF'}\r\ncmd:"
            return

        cmd = COMMAND_DB.get(name)
        if cmd is None or cmd.gen > self.gen:
            self._pending = "*** What?\r\ncmd:"           # Befehl unbekannt
        elif self.has_expert and not self.expert_on and name not in self._BEGINNER:
            self._pending = "?EXPERT command\r\ncmd:"     # vorhanden, aber gesperrt
        else:
            self._pending = f"{cmd.name} 0\r\ncmd:"       # unterstuetzt -> Wert-Echo

    def read_idle(self, idle_s: float = 0.25, max_s: float = 3.0) -> str:
        out, self._pending = self._pending, ""
        if self.debug:
            self.debug.rx(out, 0.0)
        return out

    def close(self) -> None:
        pass


# ----------------------------------------------------------------------------
# 6. Scan-Ablauf
# ----------------------------------------------------------------------------
WHAT_RE = re.compile(r"\bwhat\?", re.IGNORECASE)   # '*** What?' -> unbekannt
EXPERT_RE = re.compile(r"\?expert", re.IGNORECASE) # '?EXPERT command' -> vorhanden, aber gesperrt


class Result(str, Enum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    EXPERT_GATED = "EXPERT_GATED"  # vorhanden, aber EXPERT-Sperre aktiv (sollte nach Unlock nicht auftreten)
    NOT_PROBED = "NOT_PROBED"     # SKIP-Befehl, nicht automatisch getestet
    ERROR = "ERROR"               # keine/unklare Antwort


@dataclass
class Report:
    port: str
    release_iso: Optional[str]
    detected_gen: Optional[Gen]
    banner: str
    expert_prior: Optional[str] = None   # Zustand von EXPERT vor dem Scan ('ON'/'OFF'/None=nicht vorhanden)
    rows: list[dict] = field(default_factory=list)
    ts: str = field(default_factory=lambda: _dt.datetime.now().isoformat(timespec="seconds"))


def _status(msg: str, end: str = "\n") -> None:
    """Aktivitaets-/Fortschrittsausgabe.

    Bewusst auf stderr: so bleibt stdout (der eigentliche Report) und eine evtl.
    Umleitung sauber, waehrend der Anwender im Terminal trotzdem live sieht, dass
    sich etwas tut. sys.stderr.flush() erzwingt sofortige Anzeige (sonst puffert
    Windows/PowerShell und es wirkt wie 'haengt').
    """
    sys.stderr.write(msg + end)
    sys.stderr.flush()


def enter_command_mode(t) -> None:
    """Ctrl-C bringt den PK-232 aus jeder Betriebsart zurueck zum cmd:-Prompt."""
    t.write(CTRL_C)
    t.read_idle()


def capture_banner(t) -> str:
    """RESTART absetzen und den Sign-on-Banner einsammeln.

    RESTART ist NICHT-DESTRUKTIV (im Gegensatz zu RESET): es initialisiert nur
    frisch und behaelt alle bbRAM-Einstellungen. Danach ggf. '*' fuer die
    Autobaud-Routine (falls ABAUD=ON), dann den Banner lesen.
    """
    _status("[*] Lese Sign-on-Banner (RESTART, ~1 s) ...")
    enter_command_mode(t)
    t.write(b"RESTART" + CR)
    time.sleep(0.6)               # dem Prozessor Zeit zum Neustart geben
    t.write(STAR)                 # Autobaud befriedigen (schadet sonst nicht)
    banner = t.read_idle(0.4, 4.0)
    enter_command_mode(t)         # sicher wieder am Prompt
    return banner


def unlock_expert(t) -> Optional[str]:
    """Schaltet EXPERT ON, damit die Expertenebene (inkl. PASSALL) sichtbar wird.

    WARUM NOETIG (Lernmodus): Bei EXPERT OFF (Werkseinstellung!) sind ueber die
    Haelfte aller Befehle im Verbose-Modus gesperrt. Eine Abfrage liefert dann
    NICHT den Wert, sondern '?EXPERT command'. Ohne diesen Unlock wuerde der Scan
    die halbe Befehlsliste falsch klassifizieren.

    Rueckgabe: der VORHERIGE Zustand ('ON'/'OFF'), damit wir ihn am Ende wieder
    herstellen koennen -- oder None, wenn die Firmware EXPERT gar nicht kennt
    (Ur-Firmware ohne Expertenebene; dann gibt es auch nichts zu entsperren).
    """
    t.write(b"EXPERT" + CR)
    resp = t.read_idle(0.2, 2.0)
    if WHAT_RE.search(resp):
        return None                       # keine EXPERT-Sperre in dieser Firmware
    prior = "ON" if re.search(r"expert\s+on", resp, re.IGNORECASE) else "OFF"
    if prior == "OFF":
        t.write(b"EXPERT ON" + CR)
        t.read_idle(0.2, 2.0)
    return prior


def restore_expert(t, prior: Optional[str]) -> None:
    """Stellt den vorherigen EXPERT-Zustand wieder her (minimalinvasiv)."""
    if prior == "OFF":
        t.write(b"EXPERT OFF" + CR)
        t.read_idle(0.2, 2.0)


def probe_query(t, cmd: Cmd) -> Result:
    """Einen Parameter-Befehl nackt abfragen und die Antwort klassifizieren."""
    t.write(cmd.name.encode("ascii") + CR)
    resp = t.read_idle(0.2, 2.0)
    if WHAT_RE.search(resp):
        result = Result.UNSUPPORTED        # '*** What?' / '?What?' -> unbekannt
    elif EXPERT_RE.search(resp):
        result = Result.EXPERT_GATED       # '?EXPERT command' -> vorhanden, gesperrt
    elif resp.strip():
        result = Result.SUPPORTED          # irgendeine nicht-Fehler-Antwort
    else:
        result = Result.ERROR              # LEER -> vermutlich Timing (siehe Log)
    if _dbg(t):
        _dbg(t).note(f"DECIDE {cmd.name} (Q) = {result.value}")
    return result


# Namen der Befehle, die das Geraet neu starten / Parameter zuruecksetzen.
# Werden im --probe-all-Modus ZULETZT geprueft (sonst wuerden sie EXPERT auf OFF
# zuruecksetzen und alle folgenden Abfragen verfaelschen).
REBOOT_CMDS = {"RESET", "REINIT", "RESTART"}

# Befehle, die AUCH bei --probe-all NIE automatisch abgesetzt werden. CALIBRATE
# startet die Modem-Kalibrierroutine (Sender-Dauerton); ein Test am 26.07.2026
# zeigte, dass das Geraet danach auf KEINEN Befehl mehr reagiert (jede RX-Zeile
# leer, exakt beim Timeout) -- vermutlich haengt es im Kalibriermodus fest, aus
# dem Ctrl-C nicht herausfuehrt. Deshalb hart ausgeschlossen, unabhaengig vom
# Notiztext in der DB.
NEVER_AUTO = {"CALIBRATE"}


def _is_never_auto(cmd: Cmd) -> bool:
    return cmd.name in NEVER_AUTO or "never auto" in (cmd.note or "").lower()


# ----------------------------------------------------------------------------
# 6a. Modus-gruppiertes Testen
# ----------------------------------------------------------------------------
# WARUM NOETIG: der PK-232 gated manche Parameter-Abfragen nach dem aktuell
# aktiven Betriebsmodus (OPMODE). Beispiel aus der Praxis: 'NUMS' und 'OK'
# (Gruppe 'signal') antworten mit '?not while in PAcket', wenn das Geraet im
# Packet-Kontext steckt -- obwohl die Befehle existieren. Ein rein alphabe-
# tischer Scan mischt Gruppen wahllos durch und produziert dadurch massenhaft
# falsche UNSUPPORTED/ERROR-Ergebnisse. Abhilfe: vor jeder Gruppe den passenden
# Modus-Direktbefehl senden, dann per Ctrl-C zurueck zum cmd:-Prompt (das
# Geraet bleibt danach im gewaehlten Betriebskontext, auch wenn man wieder am
# Prompt ist -- das ist exakt der Unterschied zwischen 'im Command-Mode sein'
# und 'welcher OPMODE gerade aktiv ist').
#
# Gruppen ohne Eintrag (global/maildrop/misc/pactor/gps/danger) sind nach
# Beobachtung nicht modusabhaengig und werden im zuletzt aktiven Kontext
# (Default: PACKET) getestet.
MODE_ENTRY: dict[str, str] = {
    "packet": "PACKET",
    "rtty": "BAUDOT",
    "amtor": "AMTOR",
    "morse": "MORSE",
    "fax": "FAX",
    "navtex": "NAVTEX",
    "signal": "SIGNAL",
}

# Reihenfolge, in der Gruppen abgearbeitet werden. PACKET zuerst (Default-
# Zustand nach RESTART), dann die uebrigen Moden, dann modusunabhaengige
# Gruppen, dann 'danger' (enthaelt REBOOT_CMDS, die ohnehin ans Ende sortiert
# werden, und CALIBRATE, das per NEVER_AUTO nie gesendet wird).
GROUP_ORDER = ["packet", "rtty", "amtor", "morse", "fax", "navtex", "signal",
              "global", "maildrop", "pactor", "gps", "misc", "danger"]


def enter_mode(t, mode_cmd: Optional[str]) -> None:
    """Wechselt den Betriebskontext, indem der Modus-Direktbefehl gesendet und
    danach robust zum cmd:-Prompt zurueckgekehrt wird. mode_cmd=None -> no-op
    (Gruppe ohne bekannten Modus-Befehl; bleibt im zuletzt aktiven Kontext)."""
    if mode_cmd is None or mode_cmd not in COMMAND_DB:
        return
    if _dbg(t):
        _dbg(t).note(f"MODE ENTER {mode_cmd}")
    t.write(mode_cmd.encode("ascii") + CR)
    time.sleep(0.3)
    resync_cmd_mode(t)


def resync_cmd_mode(t, tries: int = 3) -> None:
    """Robust zurueck zum cmd:-Prompt -- noetig nach Aktions-/Modus-Befehlen.

    Ein Befehl wie BAUDOT/CONVERSE/TRANS verlaesst den Command-Mode. Ctrl-C
    holt den PK-232 aus (fast) jeder ASCII-Betriebsart zurueck. Wir versuchen es
    mehrfach und akzeptieren, sobald der 'cmd:'-Prompt wieder auftaucht.
    """
    for _ in range(tries):
        t.write(CTRL_C)
        resp = t.read_idle(0.2, 1.2)
        if "cmd:" in resp.lower():
            return
    # Zur Sicherheit ein '*' (Autobaud) + Ctrl-C -- hilft nach Reboots.
    t.write(STAR)
    t.write(CTRL_C)
    t.read_idle(0.2, 1.2)


def probe_action(t, cmd: Cmd) -> Result:
    """Aktions-/Modus-/Reset-Befehl AKTIV testen (nur im --probe-all-Modus).

    Vorsicht: dieser Befehl kann senden, die Betriebsart wechseln oder Parameter
    zuruecksetzen. Der Aufrufer hat das Risiko bewusst freigegeben (kein Funk-
    geraet angeschlossen, Einstellungen kommen aus dem INI zurueck).

    Klassifikation wie bei probe_query, ABER: ein erkannter Aktionsbefehl echot
    oft NICHTS (er handelt nur). Fehlt '*** What?', werten wir das daher als
    SUPPORTED -- die Abwesenheit des Fehlers ist hier das Praesenz-Signal.
    Danach IMMER zurueck zum cmd:-Prompt.
    """
    t.write(cmd.name.encode("ascii") + CR)
    resp = t.read_idle(0.3, 3.0)           # Reboots/Modewechsel brauchen laenger
    if WHAT_RE.search(resp):
        result = Result.UNSUPPORTED
    elif EXPERT_RE.search(resp):
        result = Result.EXPERT_GATED
    elif resp.strip():
        result = Result.SUPPORTED          # kein Fehler, Antwort da -> existiert
    else:
        result = Result.ERROR              # LEER -> vermutlich Verbindungsproblem,
                                            # NICHT automatisch als SUPPORTED werten
                                            # (siehe hard_resync/Health-Check)
    if cmd.name in REBOOT_CMDS:
        time.sleep(0.8)                    # dem Neustart Zeit geben
        t.write(STAR)                      # evtl. Autobaud nach Reboot
    resync_cmd_mode(t)
    if _dbg(t):
        _dbg(t).note(f"DECIDE {cmd.name} (S) = {result.value}")
    return result


def hard_resync(t) -> bool:
    """Harte Resynchronisation nach vermutetem Verbindungsverlust.

    Wird ausgeloest, wenn mehrere Befehle hintereinander KOMPLETT leer
    antworten (siehe STALL_THRESHOLD in run_scan) -- das Muster, das nach
    CALIBRATE beobachtet wurde: das Geraet reagiert auf nichts mehr, auch
    nicht auf Ctrl-C. Wir versuchen den selben RESTART-Weg wie beim initialen
    Banner-Einlesen (nicht-destruktiv: laedt nur die bbRAM-Einstellungen neu).

    Rueckgabe: True, wenn danach wieder ein 'cmd:'-Prompt zu sehen war.
    """
    if _dbg(t):
        _dbg(t).note("HARD-RESYNC: vermuteter Verbindungsverlust, sende RESTART")
    for _ in range(2):
        t.write(CTRL_C)
        t.read_idle(0.2, 1.0)
    t.write(b"RESTART" + CR)
    time.sleep(0.6)
    t.write(STAR)
    resp = t.read_idle(0.4, 4.0)
    t.write(CTRL_C)
    resp2 = t.read_idle(0.2, 1.5)
    ok = "cmd:" in (resp + resp2).lower()
    if _dbg(t):
        _dbg(t).note(f"HARD-RESYNC {'erfolgreich' if ok else 'FEHLGESCHLAGEN'}")
    return ok


def run_scan(t, port: str, only_group: Optional[str] = None,
             progress: bool = True, probe_all: bool = False) -> Report:
    banner = capture_banner(t)
    release = parse_release_date(banner)
    gen = release_to_gen(release) if release else None

    if progress:
        if release:
            _status(f"[*] Release erkannt: {release}  ->  "
                    f"{GEN_LABEL.get(gen, '?')}")
        else:
            _status("[!] Kein Release-Datum im Banner gefunden "
                    "(Scan laeuft trotzdem weiter).")

    rep = Report(port=port, release_iso=release, detected_gen=gen, banner=banner.strip())

    # EXPERT ON, damit die Expertenebene (PASSALL & ~die Haelfte der Befehle)
    # ueberhaupt abfragbar ist. prior merken, um am Ende zu restaurieren.
    if _dbg(t):
        _dbg(t).note(f"BANNER geparst: release={release} gen={gen}")
        _dbg(t).note("Phase: EXPERT entsperren")
    rep.expert_prior = unlock_expert(t)
    if progress:
        _status(f"[*] EXPERT: {rep.expert_prior or 'in dieser Firmware nicht vorhanden'}")

    # Zu pruefende Befehle vorab bestimmen und in drei Eimer sortieren:
    #   1. never_auto  -- NIE gesendet (z.B. CALIBRATE), immer NOT_PROBED
    #   2. rest        -- nach Betriebsmodus-Gruppe sortiert (siehe MODE_ENTRY),
    #                     damit Modus-gegatete Befehle im richtigen Kontext
    #                     abgefragt werden
    #   3. reboot      -- RESET/REINIT/RESTART, IMMER zuletzt (siehe REBOOT_CMDS)
    all_cmds = [(n, c) for n, c in COMMAND_DB.items()
                if not (only_group and c.group != only_group)]
    never_auto = [(n, c) for n, c in all_cmds if _is_never_auto(c)]
    reboot = [(n, c) for n, c in all_cmds if n in REBOOT_CMDS]
    rest = [(n, c) for n, c in all_cmds
            if n not in REBOOT_CMDS and not _is_never_auto(c)]

    def _group_rank(nc):
        g = nc[1].group
        return GROUP_ORDER.index(g) if g in GROUP_ORDER else len(GROUP_ORDER)

    rest.sort(key=lambda nc: (_group_rank(nc), nc[0]))
    rest_names = {n for n, _ in rest}
    todo = never_auto + rest + reboot

    total = len(todo)
    if probe_all:
        n_active = len(rest) + len(reboot)   # never_auto zaehlt nicht als aktiv
        if progress:
            _status("[!] --probe-all: JEDER Befehl (ausser fest gesperrten) wird "
                    "aktiv abgesetzt, gruppiert nach Betriebsmodus. "
                    "Reboot-Befehle zuletzt.")
    else:
        n_active = sum(1 for _, c in rest if c.probe is Probe.QUERY)
    if never_auto and progress:
        names = ", ".join(n for n, _ in never_auto)
        _status(f"[!] Fest gesperrt (nie automatisch gesendet): {names}")
    if progress:
        _status(f"[*] Pruefe {total} Befehle ({n_active} werden aktiv abgefragt"
                f"{'' if probe_all else ', Rest per Generation abgeleitet'}). "
                f"Grobe Dauer ~{max(1, n_active//2)}s.")
    tally = {"SUPPORTED": 0, "UNSUPPORTED": 0, "EXPERT_GATED": 0,
             "NOT_PROBED": 0, "ERROR": 0}

    # Health-Check-Zustand: zaehlt komplett leere Antworten in Folge. Nach
    # CALIBRATE reagierte das Geraet auf GAR NICHTS mehr -- dieses Muster
    # (mehrere Leerantworten hintereinander) loest eine harte Resync aus,
    # statt stillschweigend 40+ Befehle als ERROR zu verbrennen.
    STALL_THRESHOLD = 3
    stall_count = 0
    current_group = None

    try:
        for i, (name, cmd) in enumerate(todo, 1):
            # Gruppenwechsel: Betriebsmodus umschalten (nur fuer die 'rest'-
            # Befehle relevant; never_auto wird nie gesendet, reboot braucht
            # keinen Modus-Wechsel).
            if name in rest_names and cmd.group != current_group:
                current_group = cmd.group
                mode_cmd = MODE_ENTRY.get(cmd.group)
                if mode_cmd:
                    if progress:
                        _status(f"\n[*] Wechsle in Modus {mode_cmd} "
                                f"(Gruppe {cmd.group}) ...")
                    enter_mode(t, mode_cmd)

            if _dbg(t):
                _dbg(t).note(f"=== [{i}/{total}] {name}  (probe={cmd.probe.value}) ===")

            if _is_never_auto(cmd):
                result = Result.NOT_PROBED
            elif cmd.probe is Probe.SKIP and not probe_all:
                result = Result.NOT_PROBED
            elif cmd.probe is Probe.SKIP:          # probe_all: Aktion aktiv testen
                result = probe_action(t, cmd)
                time.sleep(0.03)
                if name in REBOOT_CMDS:
                    # Geraet kann rebootet/Parameter zurueckgesetzt haben ->
                    # EXPERT ist evtl. wieder OFF. Fuer saubere Restaurierung
                    # am Ende neu ermitteln/entsperren.
                    rep.expert_prior = unlock_expert(t)
                    current_group = None           # Modus danach neu bestimmen
            else:
                result = probe_query(t, cmd)
                time.sleep(0.03)      # dem TNC Luft lassen

            # Health-Check: komplett leere Antworten deuten auf Verbindungs-
            # verlust hin (z.B. Geraet haengt nach einem problematischen
            # Befehl). Mehrere in Folge -> harte Resync statt weiter blind
            # durchzuscannen.
            if result is Result.ERROR:
                stall_count += 1
            else:
                stall_count = 0
            if stall_count >= STALL_THRESHOLD:
                if progress:
                    _status(f"\n[!] {stall_count} Befehle in Folge ohne Antwort "
                            f"-- vermuteter Verbindungsverlust. Versuche "
                            f"Resynchronisation ...")
                ok = hard_resync(t)
                if progress:
                    _status(f"[{'*' if ok else '!'}] Resync "
                            f"{'erfolgreich' if ok else 'FEHLGESCHLAGEN'}.")
                rep.expert_prior = unlock_expert(t)
                current_group = None               # Modus nach Resync neu setzen
                stall_count = 0
                if not ok:
                    # Geraet reagiert gar nicht mehr -- Rest des Scans wuerde nur
                    # weitere Fehlresultate produzieren. Abbrechen und das bisher
                    # Gesammelte zurueckgeben, statt falsche Daten zu erzeugen.
                    if progress:
                        _status("[!] Abbruch: Geraet antwortet nicht mehr. "
                                "Bisherige Ergebnisse werden gespeichert.")
                    break

            tally[result.value] = tally.get(result.value, 0) + 1
            if progress:
                # Live-Zeile, die sich selbst ueberschreibt (\r). Auf feste Breite
                # aufgefuellt, damit Reste laengerer Namen sauber ueberschrieben werden.
                _status(f"\r  [{i:>3}/{total}] {name:<10.10} {result.value:<11} "
                        f"ok={tally['SUPPORTED']:<3} no={tally['UNSUPPORTED']:<3} "
                        f"skip={tally['NOT_PROBED']:<3}   ", end="")

            # EXPERT_GATED zaehlt fuer die Praesenz-Frage wie SUPPORTED
            present = result in (Result.SUPPORTED, Result.EXPERT_GATED)
            expected = (gen is not None and cmd.gen <= gen)
            anomaly = ""
            if present and gen is not None and not expected:
                anomaly = "unexpected-present"     # da, obwohl Hypothese 'zu neu'
            elif result is Result.UNSUPPORTED and expected:
                anomaly = "unexpected-absent"      # fehlt, obwohl Hypothese 'sollte da sein'

            rep.rows.append({
                "mnem": cmd.mnem,
                "name": cmd.name,
                "group": cmd.group,
                "gen_hyp": int(cmd.gen),
                "conf": cmd.conf.value,
                "probe": cmd.probe.value,
                "expected": "yes" if (gen is not None and expected) else ("no" if gen is not None else "?"),
                "result": result.value,
                "anomaly": anomaly,
                "note": cmd.note,
            })
    finally:
        if progress:
            _status("")                       # Zeilenumbruch nach der \r-Laufzeile
            _status("[*] Abfrage fertig. Stelle Betriebsmodus (PACKET) und "
                    "EXPERT wieder her ...")
        enter_mode(t, "PACKET")
        restore_expert(t, rep.expert_prior)
    if progress:
        _status("[*] Scan abgeschlossen.\n")
    return rep


# ----------------------------------------------------------------------------
# 7. Ausgabe
# ----------------------------------------------------------------------------
def print_report(rep: Report) -> None:
    print("=" * 74)
    print(f"PK-232 firmware scan  --  port {rep.port}  --  {rep.ts}")
    print("-" * 74)
    if rep.release_iso:
        gl = GEN_LABEL.get(rep.detected_gen, "?") if rep.detected_gen else "?"
        print(f"Release date : {rep.release_iso}   ->  generation: {gl}")
    else:
        print("Release date : NOT FOUND in banner (see raw banner below)")
    if rep.expert_prior is None:
        print("EXPERT       : not present in this firmware (no expert gating)")
    else:
        print(f"EXPERT       : was {rep.expert_prior}; set ON for scan, restored afterwards")
    print("-" * 74)

    # Zusammenfassung je Ergebnis
    counts: dict[str, int] = {}
    for r in rep.rows:
        counts[r["result"]] = counts.get(r["result"], 0) + 1
    summary = "  ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    print(f"Summary      : {summary}")

    anomalies = [r for r in rep.rows if r["anomaly"]]
    if anomalies:
        print("-" * 74)
        print(f"ANOMALIES ({len(anomalies)}) -- device disagrees with hypothesis:")
        for r in anomalies:
            print(f"  {r['mnem']} {r['name']:<9} {r['result']:<12} "
                  f"({r['anomaly']}, hyp gen {r['gen_hyp']}, conf {r['conf']})")

    print("-" * 74)
    print(f"{'MN':<3}{'NAME':<10}{'GRP':<10}{'HYP':<4}{'EXP':<4}{'RESULT':<12}NOTE")
    for r in rep.rows:
        print(f"{r['mnem']:<3}{r['name']:<10}{r['group']:<10}"
              f"{r['gen_hyp']:<4}{r['expected']:<4}{r['result']:<12}{r['note']}")
    print("=" * 74)
    if not rep.release_iso:
        print("RAW BANNER:")
        print(rep.banner)


def write_csv(rep: Report, path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        fields = ["mnem", "name", "group", "gen_hyp", "conf", "probe",
                  "expected", "result", "anomaly", "note"]
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rep.rows:
            w.writerow(r)


def write_json(rep: Report, path: str) -> None:
    payload = {
        "port": rep.port, "timestamp": rep.ts,
        "release_iso": rep.release_iso,
        "detected_gen": int(rep.detected_gen) if rep.detected_gen else None,
        "expert_prior": rep.expert_prior,
        "banner": rep.banner, "rows": rep.rows,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)


def print_matrix() -> None:
    """Gibt die statische Hypothesen-Matrix als Markdown aus (kein Geraet noetig)."""
    groups: dict[str, list[Cmd]] = {}
    for cmd in COMMAND_DB.values():
        groups.setdefault(cmd.group, []).append(cmd)

    print("# PK-232 Befehle x Firmware-Generation (Hypothese)\n")
    print("Legende Generation: 1=BASE (>=1988) | 2=MBX (>=1990) | "
          "3=PACTOR (>=1993).  Konfidenz: H/M/L.  "
          "Probe: Q=sicher abfragbar, S=Aktion/Modus (nicht auto-getestet).\n")
    print("| MN | Befehl | Gruppe | 1988 | 1991 | 1995 | Konf | Probe | Anm. |")
    print("|----|--------|--------|:----:|:----:|:----:|:----:|:-----:|------|")
    for group in sorted(groups):
        for cmd in sorted(groups[group], key=lambda c: c.name):
            c88 = "x" if cmd.gen <= Gen.BASE else ""
            c91 = "x" if cmd.gen <= Gen.MBX else ""
            c95 = "x" if cmd.gen <= Gen.PACTOR else ""
            print(f"| {cmd.mnem} | {cmd.name} | {cmd.group} | {c88:^4} | "
                  f"{c91:^4} | {c95:^4} | {cmd.conf.value} | {cmd.probe.value} | "
                  f"{cmd.note} |")


# ----------------------------------------------------------------------------
# 8. main
# ----------------------------------------------------------------------------
def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="PK-232 firmware capability scanner")
    ap.add_argument("--port", help="serial port, e.g. COM16 or /dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--group", help="restrict scan to one functional group")
    ap.add_argument("--csv", help="write CSV report to this path")
    ap.add_argument("--json", help="write JSON report to this path")
    ap.add_argument("--matrix", action="store_true",
                    help="print the static hypothesis matrix as Markdown and exit")
    ap.add_argument("--selftest", metavar="YEAR",
                    help="dry-run against a mock firmware of the given year "
                         "(1988|1991|1995) -- no hardware needed")
    ap.add_argument("--probe-all", action="store_true",
                    help="AKTIV JEDEN Befehl absetzen -- auch Sende-, Modus- und "
                         "RESET-Befehle (sonst NOT_PROBED). NUR mit abgezogenem "
                         "Funkgeraet und gesicherten Einstellungen verwenden! "
                         "Reboot-Befehle werden zuletzt geprueft.")
    ap.add_argument("--debug", metavar="LOGFILE", nargs="?",
                    const="pk232_scan_debug.log", default=None,
                    help="jeden gesendeten Befehl und die TNC-Antwort in ein "
                         "Log schreiben (Default-Datei: pk232_scan_debug.log). "
                         "Zeigt bei 'ERROR' die Wartezeit/leere Antwort.")
    args = ap.parse_args(argv)

    if args.matrix:
        print_matrix()
        return 0

    # Debug-Log (optional) -- wird an den Transport uebergeben.
    dbg = DebugLog(args.debug) if args.debug else None
    if dbg:
        _status(f"[*] Debug-Log: {dbg.path}")

    # Transport waehlen: echt oder Mock
    if args.selftest:
        gen_map = {"1988": (Gen.BASE, "1988-12-30"),
                   "1991": (Gen.MBX, "1991-08-01"),
                   "1995": (Gen.PACTOR, "1995-09-11")}
        if args.selftest not in gen_map:
            print("selftest year must be one of 1988 / 1991 / 1995", file=sys.stderr)
            return 2
        gen, rel = gen_map[args.selftest]
        t = MockTransport(gen, rel, debug=dbg)
        port = f"MOCK:{args.selftest}"
    else:
        if not args.port:
            ap.error("--port is required (or use --selftest / --matrix)")
        _status(f"[*] Oeffne {args.port} @ {args.baud} Baud 8N1 ...")
        t = SerialTransport(args.port, args.baud, debug=dbg)
        port = args.port
        _status(f"[*] {args.port} offen. Starte Scan (Fortschritt unten; "
                "Abbruch mit Strg-C) ...")

    if args.probe_all and not args.selftest:
        _status("[!] WARNUNG --probe-all: es werden AUCH Sende-, Modus- und "
                "RESET-Befehle abgesetzt. Nur ohne Funkgeraet ausfuehren!")

    try:
        rep = run_scan(t, port, only_group=args.group, probe_all=args.probe_all)
    finally:
        t.close()
        if dbg:
            dbg.close()
            _status(f"[*] Debug-Log geschrieben: {dbg.path}")

    print_report(rep)
    if args.csv:
        write_csv(rep, args.csv)
        print(f"[+] CSV written: {args.csv}")
    if args.json:
        write_json(rep, args.json)
        print(f"[+] JSON written: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())