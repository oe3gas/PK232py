#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ORIGIN: handed over by the operator on 06.10.2026 (chat "PK232 Befehle nach Firmware-Version
# testen", July 2026). P88 Teil D brought it up to date: the command list comes from the command
# matrix (src/pk232py/data/command_matrix.csv), commands of kind danger / action_tx / mode are
# never sent, AMOTR is gone, every command line ends with CR only (verbose_line), the CSV names
# release / device / date and --update-matrix fills the ? cells of the matrix.
"""
pk232_fw_scan.py  --  PK-232(MBX) firmware capability scanner

WAS DIESES TOOL MACHT
=====================
Es verbindet sich mit einem PK-232 (Verbose-/Command-Mode, NICHT Host Mode), liest den
Firmware-Release aus dem Einschalt-Banner ("Release DD.MON.YY") und fragt Befehl fuer Befehl
ab, ob die eingebaute Firmware ihn kennt. Die Befehlsliste ist die COMMAND MATRIX des Projekts
(P88): eine Datendatei, die einzige Wahrheit ueber "welcher Befehl existiert auf welcher
Firmware". Der Scan fuellt nur ihre ?-Zellen (--update-matrix), nie ein vorhandenes Ergebnis.

SICHERHEIT ZUERST
=================
Die Matrix kennt je Befehl eine ``kind``:
  param       Parameter. Nacktes Absetzen zeigt nur den Wert -> wird abgefragt.
  immediate   Sofortbefehl ohne Folgen fuer Sender/Speicher (CSTATUS, LOCK, NUMS ...) -> nur mit
              --immediate abgefragt.
  mode        wechselt die Betriebsart (BAUDOT, PACKET, ...)          -> NIE abgesetzt
  action_tx   tastet den Sender (CONNECT, XMIT, ARQ, FEC, ID ...)      -> NIE abgesetzt
  danger      RESET, REINIT, MEMORY, CALIBRATE, TRANS, MDCHECK ...     -> NIE abgesetzt
Zusaetzlich sperrt NEVER_AUTO = {CALIBRATE, TRANS} hart, egal was in der Matrix steht
(CALIBRATE: Dauerton, das Geraet reagiert danach auf nichts mehr; TRANS verlaesst den
Command-Mode, danach antworten TRFLOW/XFLOW mit ERROR - beides im Juli-Lauf erlebt).
Die Zellen dieser Befehle bleiben ? bis sie ein Mensch am Geraet belegt.

Ausnahme, die das Werkzeug selbst braucht: RESTART (Sign-on-Banner holen) und der Wechsel in
den Betriebsmodus einer Gruppe (siehe MODE_ENTRY). Kein Funkgeraet anschliessen.

ABLAUF
======
  0. Aufwecken wie die App (Erkennungskette, SerialManager._init_tnc_thread): das ERSTE Byte ist
     immer ein '*' ohne CR (Geraet C wartet nach dem Einschalten auf '*' fuer die Autobaud-Messung
     und bleibt bei jedem anderen ersten Zeichen stumm - T180), dann auf Banner oder 'cmd:'
     warten; erst danach CR, COMMAND-Zeichen (Ctrl-C), XON
  1. RESTART -> auf das Banner WARTEN (kein fester Wert), nur wenn es nicht kommt ein '*'
     -> Release (genau wie gedruckt, z.B. 13.SEP.95)
  2. EXPERT entsperren (merken, am Ende zuruecksetzen); '?EXPERT command' -> EXPERT_GATED
  3. nach Betriebsart gruppiert abfragen (MODE_ENTRY); die Gruppen ohne eigene Betriebsart
     (global, maildrop, pactor, ...) in PACKET, NIE im Kontext der letzten Gruppe (SIGNAL gibt
     laufend Analysedaten aus und antwortet verspaetet, T179); danach PACKET und EXPERT wie vorher
  4. Report + optional CSV (Spalten release, device, date, ...) + optional --update-matrix

BEDIENUNG
=========
  python tools/pk232_fw_scan.py --port COM16 --csv out.csv        # echter Scan
  python tools/pk232_fw_scan.py --port COM16 --update-matrix      # + ?-Zellen der Matrix fuellen
  python tools/pk232_fw_scan.py --port COM16 --immediate          # auch Sofortbefehle abfragen
  python tools/pk232_fw_scan.py --plan                            # was wuerde gesendet / nie gesendet
  python tools/pk232_fw_scan.py --selftest 1991                   # Trockenlauf gegen einen Mock
Der Mock ist nur ein Selbsttest: --update-matrix mit --selftest wird abgelehnt.

Standard: 9600 Baud, 8N1, xonxoff=False (siehe SerialManager-Konventionen).
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import datetime as _dt
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from pk232py.comm import command_matrix as cm  # noqa: E402
from pk232py.comm.constants import verbose_line  # noqa: E402
from pk232py.comm.devices import KNOWN_DEVICES  # noqa: E402
from pk232py.comm.pk232_hostmode_sub import escape_converse  # noqa: E402
# the SAME wake-up byte and banner markers as the app's detection chain (SerialManager)
from pk232py.comm.serial_manager import _BANNER_MARKERS, _WAKEUP, _XON_BYTE  # noqa: E402


# ----------------------------------------------------------------------------
# 1. Gruppen (Betriebskontext) und der Plan aus der Matrix
# ----------------------------------------------------------------------------
# Die Matrix kennt keine Gruppe: der Betriebskontext, in dem ein Befehl abgefragt werden muss,
# ist Wissen des Scanners, nicht der Firmware. Diese Tabelle stammt aus dem Juli-Stand des
# Scanners (Namen ausserhalb der Matrix sind entfallen); was hier fehlt, landet in 'other' und
# wird im zuletzt aktiven Kontext abgefragt.
_GROUP_TEXT = {
    "packet": (
        "ACKPRIOR ACRPACK ALFPACK AX25L2V2 AXDELAY AXHANG BEACON BTEXT CANPAC CASEDISP CFROM "
        "CHCALL CHDOUBLE CHECK CHSWITCH CONMODE CONOK CONPERM CONSTAMP CPACTIME CSTATUS DFROM "
        "DIGIPEAT DWAIT FRACK FULLDUP HBAUD HEADERLN HID HPOLL ILFPACK KISS KISSADDR MAXFRAME "
        "MCON MFROM MHEARD MONITOR MRPT MTO MYCALL PACLEN PACTIME PASSALL PERSIST PPERSIST "
        "RAWHDLC RELINK RESPTIME RETRY RFRAME SENDPAC SLOTTIME SQUELCH TRIES TXFLOW UNPROTO "
        "VHF WHYNOT"),
    "rtty": ("8BITCONV ABAUD ACRRTTY ALFRTTY BITINV CCITT CRADD DIDDLE PASS RBAUD TXDELAY "
             "USOS WIDESHFT WRU XBAUD"),
    "amtor": ("AAB ADELAY ARQTMO ARQTOL ARXTOR ATXRTTY CBELL DCDCONN EAS MARSDISP MYALTCAL "
              "MYSELCAL RFEC RXREV SRXALL TXREV WORDOUT"),
    "morse": "MSPEED MWEIGHT",
    "fax": ("ASPECT AUDELAY CWID FAXNEG FSPEED GRAPHICS JUSTIFY LEFTRITE LOCK PRFAX PRTYPE "
            "TRACE"),
    "navtex": "ERRCHAR NAVMSG NAVSTN",
    "signal": "ALTMODEM CODE CUSTOM NUMS OK TDBAUD TDCHAN",
    "global": ("ACRDISP ADDRESS AFILTER ALFDISP AUTOBAUD AWLEN BKONDEL CANLINE CMDTIME COMMAND "
               "DAYSTAMP DAYTIME DISPLAY ECHO ESCAPE EXPERT FLOW FRICK HELP HOST HOSTKEY IO "
               "LITE MOPTT NUCR NULF NULLS OPMODE PARITY PRCON PROUT REDISPLAY START STOP "
               "TBAUD TCLEAR TIME TRFLOW XFLOW XMITOK XOFF XON"),
    "maildrop": ("3RDPARTY BBSMSGS CMSG CTEXT DELETE FREE HEREIS HOMEBBS KILONFWD LASTMSG "
                 "MAILDROP MBELL MBX MDIGI MDMON MDPROMPT MID MMSG MPROTO MSTAMP MTEXT MXMIT "
                 "MYALIAS MYGATE MYIDENT MYMAIL NOMODE TMAIL TMPROMPT UBIT USERS"),
    "pactor": "MFILTER MYPTCALL NEWMODE PT200 PTDOWN PTHUFF PTOVER PTROUND PTUP UCMD",
    "gps": "GUSERS",
    "misc": "RECEIVE",
}
GROUP_OF = {name: group for group, text in _GROUP_TEXT.items() for name in text.split()}

# Reihenfolge, in der Gruppen abgearbeitet werden. PACKET zuerst (Zustand nach RESTART), dann
# die uebrigen Betriebsarten, dann die modusunabhaengigen Gruppen.
GROUP_ORDER = ["packet", "rtty", "amtor", "morse", "fax", "navtex", "signal",
               "global", "maildrop", "pactor", "gps", "misc", "other"]

# WARUM NOETIG: der PK-232 gated manche Abfragen nach dem aktiven Betriebsmodus (OPMODE), z.B.
# antworten NUMS und OK im Packet-Kontext mit '?not while in PAcket' obwohl sie existieren. Vor
# jeder Gruppe wird deshalb der Modus-Direktbefehl gesendet, dann Ctrl-C zurueck zum cmd:-Prompt
# (das Geraet bleibt im gewaehlten Betriebskontext). Gruppen ohne Eintrag bleiben im letzten.
MODE_ENTRY: dict[str, str] = {
    "packet": "PACKET",
    "rtty": "BAUDOT",
    "amtor": "AMTOR",
    "morse": "MORSE",
    "fax": "FAX",
    "navtex": "NAVTEX",
    "signal": "SIGNAL",
}

def mode_for(group: str) -> str:
    """Der Betriebskontext, in dem eine Gruppe abgefragt wird. Gruppen ohne eigenen Eintrag
    (global, maildrop, pactor, gps, misc, other) laufen in PACKET: T179 (Geraet B, 06.10.2026)
    zeigte, dass ALLE 24 ERROR in der SIGNAL-Phase auftraten - dort antwortet der TNC spaeter als
    das Lesefenster, und SIGNAL ueberlebt einen RESTART (der Opmode bleibt), die Resync half nie."""
    return MODE_ENTRY.get(group, "PACKET")


# Nie automatisch gesendet, egal was die Matrix als kind sagt (siehe Moduldoku).
NEVER_AUTO = {"CALIBRATE", "TRANS"}
PROBED_KINDS = ("param", "immediate")


@dataclass
class Cmd:
    name: str
    group: str
    kind: str
    abbrev: str = ""


def plan(entries: Optional[dict] = None, only_group: Optional[str] = None,
         immediate: bool = False) -> list:
    """Die abzufragenden Befehle aus der Matrix, nach Betriebsart gruppiert und alphabetisch.
    kind danger / action_tx / mode und NEVER_AUTO sind nie dabei; 'immediate' nur auf Wunsch."""
    entries = cm.all_entries() if entries is None else entries
    kinds = ("param", "immediate") if immediate else ("param",)
    out = []
    for name, e in entries.items():
        if name in NEVER_AUTO or e.kind not in kinds:
            continue
        group = GROUP_OF.get(name, "other")
        if only_group and group != only_group:
            continue
        out.append(Cmd(name, group, e.kind, e.abbrev))
    out.sort(key=lambda c: (GROUP_ORDER.index(c.group), c.name))
    return out


def never_probed(entries: Optional[dict] = None) -> list:
    """Die Befehle der Matrix, die dieses Werkzeug nie absetzt (Name, Grund)."""
    entries = cm.all_entries() if entries is None else entries
    out = []
    for name, e in sorted(entries.items()):
        if name in NEVER_AUTO:
            out.append((name, "NEVER_AUTO"))
        elif e.kind in ("danger", "action_tx", "mode"):
            out.append((name, e.kind))
    return out


# ----------------------------------------------------------------------------
# 2. Release aus dem Banner, Geraet aus der Release
# ----------------------------------------------------------------------------
# Der PK-232 gibt den Monat als 3-Buchstaben-ENGLISCH aus ("Release 13.SEP.95"). Die Matrix
# fuehrt die Release genau so wie das Banner sie druckt (docs/DEVICES.md).
_RELEASE_RE = re.compile(r"Release\s+(\d{1,2}\.[A-Za-z]{3}\.\d{2}|\d{1,2}\.\d{1,2}\.\d{4})",
                         re.IGNORECASE)


def banner_release(banner: str) -> Optional[str]:
    """'Release 13.SEP.95' -> '13.SEP.95' (Gross-/Kleinschreibung des Monats normalisiert)."""
    m = _RELEASE_RE.search(banner)
    return m.group(1).upper() if m else None


def device_of(release: Optional[str]) -> str:
    return next((d.label for d in KNOWN_DEVICES if d.release == release), "?")


# ----------------------------------------------------------------------------
# 3. Serieller Transport (echt) und Mock (Selftest)
# ----------------------------------------------------------------------------
CTRL_C = b"\x03"          # zurueck zum cmd:-Prompt
STAR = b"*"               # Autobaud-Ausloeser nach RESTART


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
        """Schliesst das Log VOLLSTAENDIG: Endemarke, flush, fsync. Mehrfaches Schliessen ist ok."""
        if self.fh.closed:
            return
        try:
            self.fh.write(f"\n# end of log -- {_dt.datetime.now().isoformat(timespec='seconds')}\n")
            self.fh.flush()
            os.fsync(self.fh.fileno())
        except Exception:
            pass
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


_MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


class MockTransport:
    """Simuliert einen PK-232 einer bekannten Release -- nur fuer --selftest und die Tests.

    Er antwortet je nach Zelle der Matrix fuer seine Release: ``no`` -> '?What?',
    ``expert`` -> '?EXPERT command' solange EXPERT OFF ist, alles andere (auch ?) wie ein
    unterstuetzter Befehl mit Wert-Echo. ``sent`` merkt jedes geschriebene Byte-Paket -- so
    pruefen die Tests, dass nie etwas Gefaehrliches abgesetzt wird. Seine Antworten sind
    ERFUNDEN und duerfen nie in die Matrix.

    Verhalten, das T179 am echten Geraet gezeigt hat (Optionen):
      * ``slow_in_signal`` -- im Opmode SIGNAL kommt die Antwort erst nach dem ersten Lesefenster
        und hinter dem Prompt steht Analysetext ("noise"); der Opmode ueberlebt RESTART.
      * ``late``   -- diese Befehle werden erst im naechsten Lesefenster beantwortet
      * ``silent`` -- diese Befehle werden nie beantwortet
      * ``needs_star_first`` -- Geraet C (T180): nach dem Einschalten wartet der TNC auf ein
        '*' (Autobaud); jedes andere erste Zeichen macht ihn dauerhaft stumm
      * ``restart_needs_star`` -- dasselbe nach jedem RESTART
      * ``banner_late_reads`` -- das Banner kommt erst im n-ten Lesefenster
      * ``ignores_star`` / ``in_converse`` / ``deaf`` -- die Schritte der Erkennungskette
    """

    _MODES = ("PACKET", "BAUDOT", "AMTOR", "MORSE", "FAX", "NAVTEX", "SIGNAL")

    def __init__(self, release: str, entries: Optional[dict] = None,
                 debug: Optional["DebugLog"] = None, slow_in_signal: bool = False,
                 late: Optional[set] = None, silent: Optional[set] = None,
                 needs_star_first: bool = False, restart_needs_star: bool = False,
                 banner_late_reads: int = 0, ignores_star: bool = False,
                 in_converse: bool = False, deaf: bool = False):
        self.release = release
        self.entries = cm.all_entries() if entries is None else entries
        self.debug = debug
        self.sent: list = []
        self._pending = ""
        self._late_reads = 0          # so many read_idle() calls return '' before the reply
        self.expert_on = False
        self.opmode = "PACKET"
        self.slow_in_signal = slow_in_signal
        self.late = set(late or ())
        self.silent = set(silent or ())
        self.restart_needs_star = restart_needs_star
        self.banner_late_reads = banner_late_reads
        self.ignores_star = ignores_star
        self.in_converse = in_converse
        self.deaf = deaf
        self._autobaud = needs_star_first     # waiting for the '*' that measures the baud rate
        expert = self.entries.get("EXPERT")
        self.has_expert = expert is None or expert.fw.get(release) != "no"

    def _cell(self, name: str) -> str:
        e = self.entries.get(name)
        return e.fw.get(self.release, "?") if e else "?"

    def _reply(self, text: str, name: str = "") -> None:
        """Queue *text*; an undelivered earlier reply stays in front of it (the pipeline shift)."""
        if name in self.silent:
            return
        slow = self.slow_in_signal and self.opmode == "SIGNAL" and name not in self._MODES
        if slow:
            text += "noise\r\n"
        self._pending += text
        self._late_reads = 1 if (slow or name in self.late) else 0

    def _banner(self) -> str:
        day, mon, yy = self.release.split(".")
        return ("\r\nPK-232M is using default values.\r\n"
                "AEA PK-232M Data Controller\r\n"
                f"Release {day}.{mon}.{yy}\r\ncmd:")

    def write(self, data: bytes) -> None:
        self.sent.append(bytes(data))
        if self.debug:
            self.debug.tx(data)
        if self.deaf:
            return
        if self._autobaud:
            # the first byte after power-on / RESTART measures the baud rate: only '*' does it,
            # anything else leaves the TNC deaf for good (T180, device C)
            if data == STAR:
                self._autobaud = False
                self._pending, self._late_reads = self._banner(), self.banner_late_reads
            else:
                self.deaf = True
            return
        if data == CTRL_C or data == CTRL_C + b"\r":
            self._pending = ""                      # Ctrl-C clears whatever was still on its way
            self._late_reads = 0
            self.in_converse = False
            self._reply("cmd:")
            return
        if data == STAR:
            if not self.ignores_star and not self.in_converse:
                self._reply("*\\\r\ncmd:")           # a TNC at the prompt answers '*' with a prompt
            return
        if self.in_converse:                        # Converse echoes everything, shows no prompt
            self._pending += data.decode("latin-1")
            return
        name = data.decode("latin-1").strip().upper()
        if name == "RESTART":
            self._pending = ""
            self._late_reads = 0
            if self.restart_needs_star:
                self._autobaud = True               # autobaud again, the banner comes after '*'
                return
            self._pending, self._late_reads = self._banner(), self.banner_late_reads  # opmode survives
            return
        if name in self._MODES:
            old, self.opmode = self.opmode, name
            self._reply(f"{name}\r\nOpmode   was {old}\r\nOpmode   now {name}\r\ncmd:", name)
            return
        if name.startswith("EXPERT"):
            if not self.has_expert:
                self._reply(f"{name}\r\n?What?\r\ncmd:", name)
                return
            arg = name[6:].strip()
            if arg == "ON":
                self.expert_on = True
                self._reply("EXPERT ON\r\nEXPert was OFF\r\nEXPert now ON\r\ncmd:", name)
            elif arg == "OFF":
                self.expert_on = False
                self._reply("EXPERT OFF\r\nEXPert was ON\r\nEXPert now OFF\r\ncmd:", name)
            else:
                self._reply(f"EXPERT\r\nEXPert {'ON' if self.expert_on else 'OFF'}\r\ncmd:", name)
            return
        cell = self._cell(name)
        if cell == "no":
            self._reply(f"{name}\r\n?What?\r\ncmd:", name)
        elif cell == "expert" and not self.expert_on:
            self._reply(f"{name}\r\n?EXPERT command\r\ncmd:", name)
        else:
            self._reply(f"{name}\r\n{name} 0\r\ncmd:", name)

    def read_idle(self, idle_s: float = 0.25, max_s: float = 3.0) -> str:
        if self._late_reads > 0:
            self._late_reads -= 1
            out = ""
        else:
            out, self._pending = self._pending, ""
        if self.debug:
            self.debug.rx(out, 0.0)
        return out

    def close(self) -> None:
        pass


# ----------------------------------------------------------------------------
# 4. Scan-Ablauf
# ----------------------------------------------------------------------------
WHAT_RE = re.compile(r"\bwhat\?", re.IGNORECASE)   # '*** What?' / '?What?' -> unbekannt
EXPERT_RE = re.compile(r"\?expert", re.IGNORECASE) # '?EXPERT command' -> vorhanden, aber gesperrt


class Result(str, Enum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    EXPERT_GATED = "EXPERT_GATED"  # vorhanden, EXPERT-Sperre aktiv
    NOT_PROBED = "NOT_PROBED"      # nie abgesetzt (kind / NEVER_AUTO)
    ERROR = "ERROR"                # keine/unklare Antwort


# Was eine Antwort fuer die Matrix bedeutet. ERROR und NOT_PROBED sagen nichts.
RESULT_TO_CELL = {"SUPPORTED": "yes", "UNSUPPORTED": "no", "EXPERT_GATED": "expert"}


def classify(resp: str) -> str:
    """Eine Antwort auf einen nackt abgesetzten Befehl -> Result-Name."""
    if WHAT_RE.search(resp):
        return Result.UNSUPPORTED.value        # '*** What?' / '?What?' -> unbekannt
    if EXPERT_RE.search(resp):
        return Result.EXPERT_GATED.value       # '?EXPERT command' -> vorhanden, gesperrt
    if resp.strip():
        return Result.SUPPORTED.value          # irgendeine nicht-Fehler-Antwort
    return Result.ERROR.value                  # LEER -> vermutlich Timing (siehe Log)


@dataclass
class Report:
    port: str
    release: Optional[str]
    banner: str
    expert_prior: Optional[str] = None   # Zustand von EXPERT vor dem Scan ('ON'/'OFF'/None=nicht vorhanden)
    rows: list = field(default_factory=list)
    ts: str = field(default_factory=lambda: _dt.datetime.now().isoformat(timespec="seconds"))

    @property
    def device(self) -> str:
        return device_of(self.release)

    @property
    def date(self) -> str:
        return self.ts[:10]


def _status(msg: str, end: str = "\n") -> None:
    """Aktivitaets-/Fortschrittsausgabe auf stderr: stdout (der Report) bleibt sauber, der
    Anwender sieht trotzdem live, dass sich etwas tut (flush gegen PowerShell-Pufferung)."""
    sys.stderr.write(msg + end)
    sys.stderr.flush()


def enter_command_mode(t) -> None:
    """Ctrl-C bringt den PK-232 aus jeder Betriebsart zurueck zum cmd:-Prompt."""
    t.write(CTRL_C)
    t.read_idle()


class ScanError(RuntimeError):
    """Das Geraet ist nicht erreichbar (kein PK-232 am Port / falsche Baudrate / haengt)."""


# Wie die App: pro Schritt hoechstens ~1,5 s (_TNC_STATE_STEP_TIMEOUT). Hier in Leseaufrufen
# gezaehlt: ein read_idle() wartet am Port bis ~0,4 s, im Mock kommt er sofort zurueck.
_STEP_READS = 4
_BANNER_STR = tuple(m.decode("ascii") for m in _BANNER_MARKERS)
_WAKE_MARKERS = ("cmd:",) + _BANNER_STR


def read_until(t, markers, reads: int = _STEP_READS) -> str:
    """Liest, bis einer der *markers* auftaucht (danach noch ein kurzes Idle, P52.1) oder die
    Lesefenster aufgebraucht sind. Nicht bis zur ersten Pause: Banner und Prompt kommen bei
    9600 Bd in Stuecken."""
    buf = ""
    for _ in range(reads):
        buf += t.read_idle(0.15, 0.5)
        if any(m in buf for m in markers):
            return buf + t.read_idle(0.12, 0.3)
    return buf


def wake(t) -> str:
    """Den TNC aufwecken und seinen Zustand bestaetigen - in der Reihenfolge der Erkennungskette
    der App (SerialManager._init_tnc_thread, Schritte 1, 2, 2b, 2c):

      1.  '*' OHNE CR            -> Banner oder 'cmd:'  (frisch eingeschaltet / wartet auf Autobaud)
      2.  CR                     -> 'cmd:'              (schon wach)
      2b. COMMAND-Zeichen + CR   -> 'cmd:'              (Converse), bis zu 3x, gemeinsame escape_converse()
      2c. XON, CR, CR            -> 'cmd:'              (vom Flow-Control gestoppt)

    Das ERSTE Byte ist immer das '*': Geraet C (30.12.1988) wartet nach dem Einschalten darauf
    und bleibt bei jedem anderen ersten Zeichen stumm (T180, 06.10.2026: der alte Scanner begann
    mit Ctrl-C und bekam nie einen Sync). Der Host-Mode-Schritt 3 der App entfaellt: der Scanner
    arbeitet nur im Verbose-Modus. Rueckgabe: der empfangene Text; ScanError, wenn nichts antwortet."""
    _dbg_note(t, "wake step 1: '*' without CR")
    t.write(_WAKEUP)
    resp = read_until(t, _WAKE_MARKERS)
    if any(m in resp for m in _WAKE_MARKERS):
        return resp

    _dbg_note(t, "wake step 2: CR")
    t.write(b"\r")
    resp = read_until(t, ("cmd:",))
    if "cmd:" in resp:
        return resp

    _dbg_note(t, "wake step 2b: COMMAND character + CR (Converse?)")

    def send_and_wait(data: bytes, timeout: float) -> bytes:
        t.write(data)
        return read_until(t, ("cmd:",)).encode("latin-1")

    found, raw = escape_converse(send_and_wait, CTRL_C)
    if found:
        return raw.decode("latin-1")

    _dbg_note(t, "wake step 2c: XON, CR, CR (flow-stopped?)")
    t.write(bytes([_XON_BYTE]))
    time.sleep(0.1)
    for _ in range(2):
        t.write(b"\r")
        resp = read_until(t, ("cmd:",))
        if "cmd:" in resp:
            return resp
    raise ScanError("no PK-232 reachable: no banner and no cmd: after '*', CR, the COMMAND "
                    "character and XON - wrong port or baud rate, or the TNC is hung "
                    "(power-cycle it and try again)")


def _dbg_note(t, msg: str) -> None:
    if _dbg(t):
        _dbg(t).note(msg)


def restart_for_banner(t) -> str:
    """RESTART absetzen und auf das Banner WARTEN (nicht eine feste Pause). Nur wenn es nicht von
    allein kommt, ein '*' (nach einem RESTART macht Geraet C wieder Autobaud und wartet darauf),
    dann bis zum Prompt weiterlesen. Rueckgabe: der Banner-Text."""
    t.write(verbose_line("RESTART"))
    banner = read_until(t, _BANNER_STR)
    if not any(m in banner for m in _BANNER_STR):
        _dbg_note(t, "no banner after RESTART: '*' for the autobaud")
        t.write(_WAKEUP)
        banner += read_until(t, _WAKE_MARKERS, reads=3 * _STEP_READS)
    if "cmd:" not in banner:
        banner += read_until(t, ("cmd:",), reads=2 * _STEP_READS)
    return banner


def capture_banner(t) -> str:
    """Aufwecken wie die App, dann RESTART und das Sign-on-Banner einsammeln.

    RESTART ist NICHT-DESTRUKTIV (im Gegensatz zu RESET): es initialisiert nur frisch und behaelt
    alle bbRAM-Einstellungen (auch den Opmode, siehe SIGNAL!), trennt aber Verbindungen."""
    _status("[*] Wecke den TNC ('*' zuerst, wie die App) ...")
    wake(t)
    _status("[*] Lese Sign-on-Banner (RESTART) ...")
    banner = restart_for_banner(t)
    enter_command_mode(t)         # erst jetzt Ctrl-C: sicher wieder am Prompt
    return banner


def unlock_expert(t) -> Optional[str]:
    """Schaltet EXPERT ON, damit die Expertenebene sichtbar wird.

    Bei EXPERT OFF (Werkseinstellung!) antworten viele Parameter mit '?EXPERT command'. Ohne
    den Unlock wuerde der Scan sie als gesperrt melden statt ihren Wert zu zeigen.

    Rueckgabe: der VORHERIGE Zustand ('ON'/'OFF'), damit er am Ende wieder hergestellt wird --
    oder None, wenn die Firmware EXPERT gar nicht kennt (dann gibt es nichts zu entsperren).
    """
    t.write(verbose_line("EXPERT"))
    resp = t.read_idle(0.2, 2.0)
    if WHAT_RE.search(resp):
        return None                       # keine EXPERT-Sperre in dieser Firmware
    prior = "ON" if re.search(r"expert\s+on", resp, re.IGNORECASE) else "OFF"
    if prior == "OFF":
        t.write(verbose_line("EXPERT ON"))
        t.read_idle(0.2, 2.0)
    return prior


def restore_expert(t, prior: Optional[str]) -> None:
    """Stellt den vorherigen EXPERT-Zustand wieder her (minimalinvasiv)."""
    if prior == "OFF":
        t.write(verbose_line("EXPERT OFF"))
        t.read_idle(0.2, 2.0)


_SIAM_LINE = re.compile(r"^(?:noise|\d+\.\d+:.*)$", re.IGNORECASE)


def answer_to(name: str, resp: str):
    """(text after the echo of *name*, prompt reached) - or None if *resp* does not START with the
    TNC's echo of exactly this command.

    Der PK-232 echot den Befehl und antwortet dann; im Modus SIGNAL kommen verspaetete Antworten
    des VORHERIGEN Befehls und Analysezeilen dazwischen (T179). Vor dem eigenen Echo duerfen nur
    uebrig gebliebene Prompts und Analysezeilen stehen - alles andere gehoert einem anderen
    Befehl, und dessen '?What?' darf nie als Antwort dieses Befehls gelten."""
    text = resp.replace("\x11", "")
    while True:
        head = text.lstrip(" \r\n\x00")
        if head.lower().startswith("cmd:"):
            text = head[4:]
            continue
        line, sep, tail = head.partition("\n")
        if sep and _SIAM_LINE.match(line.strip()):
            text = tail
            continue
        text = head
        break
    if not text.upper().startswith(name.upper()):
        return None
    rest = text[len(name):]
    if not rest.startswith(("\r", "\n")):
        return None
    reached = "cmd:" in rest
    return rest.split("cmd:", 1)[0], reached


def classify_answer(answer: str) -> str:
    """Die Antwort NACH dem Echo -> Result-Name (der Prompt wurde erreicht)."""
    if WHAT_RE.search(answer):
        return Result.UNSUPPORTED.value
    if EXPERT_RE.search(answer):
        return Result.EXPERT_GATED.value
    return Result.SUPPORTED.value


def drain(t) -> None:
    """Ctrl-C und lesen, bis Ruhe ist: raeumt Antworten weg, die noch unterwegs sind."""
    t.write(CTRL_C)
    t.read_idle(0.5, 2.0)
    t.read_idle(0.5, 1.0)


def ask(t, name: str, attempts: int = 2) -> str:
    """Einen Befehl nackt absetzen; Result-Name. Gewertet wird NUR die Antwort, die mit dem
    eigenen Echo beginnt UND den Prompt erreicht hat. Kommt zu frueh (leer/unvollstaendig)
    zurueck, wird einmal laenger gewartet (TNC ist beschaeftigt); gehoert die Antwort einem
    anderen Befehl, wird weggeraeumt und wiederholt; bleibt es unklar -> ERROR (nie
    UNSUPPORTED aus einer fremden Antwort)."""
    for _ in range(attempts):
        t.write(verbose_line(name))
        resp = t.read_idle(0.2, 2.0)
        got = answer_to(name, resp)
        if got is None and not resp.strip():
            resp += t.read_idle(0.5, 3.0)              # nur zu frueh gelesen
            got = answer_to(name, resp)
        elif got is not None and not got[1]:
            resp += t.read_idle(0.5, 3.0)              # Antwort angefangen, Prompt fehlt noch
            got = answer_to(name, resp)
        if got is not None and got[1]:
            return classify_answer(got[0])
        drain(t)
    return Result.ERROR.value


def probe(t, cmd: Cmd) -> Result:
    """Einen Befehl nackt abfragen und die Antwort klassifizieren. Nur fuer kind param /
    immediate (siehe plan()); der Aufrufer sorgt dafuer, dass nichts anderes hier ankommt."""
    assert cmd.name not in NEVER_AUTO and cmd.kind in PROBED_KINDS, cmd
    result = Result(ask(t, cmd.name))
    if _dbg(t):
        _dbg(t).note(f"DECIDE {cmd.name} ({cmd.kind}) = {result.value}")
    if cmd.kind == "immediate":
        resync_cmd_mode(t)                 # ein Sofortbefehl kann den Prompt verlassen
    return result


def enter_mode(t, mode_cmd: Optional[str]) -> None:
    """Wechselt den Betriebskontext, indem der Modus-Direktbefehl gesendet und danach robust
    zum cmd:-Prompt zurueckgekehrt wird. mode_cmd=None -> no-op."""
    if mode_cmd is None:
        return
    if _dbg(t):
        _dbg(t).note(f"MODE ENTER {mode_cmd}")
    t.write(verbose_line(mode_cmd))
    time.sleep(0.3)
    resync_cmd_mode(t)


def resync_cmd_mode(t, tries: int = 3) -> None:
    """Robust zurueck zum cmd:-Prompt -- noetig nach Modus-/Sofortbefehlen.

    Ctrl-C holt den PK-232 aus (fast) jeder ASCII-Betriebsart zurueck. Wir versuchen es
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


def hard_resync(t) -> bool:
    """Harte Resynchronisation nach vermutetem Verbindungsverlust (mehrere komplett leere
    Antworten in Folge). Derselbe RESTART-Weg wie beim Banner (laedt nur die bbRAM-Einstellungen
    neu). Rueckgabe: True, wenn danach wieder ein 'cmd:'-Prompt zu sehen war."""
    if _dbg(t):
        _dbg(t).note("HARD-RESYNC: vermuteter Verbindungsverlust, sende RESTART")
    for _ in range(2):
        t.write(CTRL_C)
        t.read_idle(0.2, 1.0)
    resp = restart_for_banner(t)
    t.write(CTRL_C)
    resp += t.read_idle(0.2, 1.2)
    return "cmd:" in resp.lower()


def run_scan(t, port: str, only_group: Optional[str] = None, progress: bool = True,
             immediate: bool = False, entries: Optional[dict] = None) -> Report:
    entries = cm.all_entries() if entries is None else entries
    banner = capture_banner(t)
    release = banner_release(banner)
    if progress:
        if release:
            _status(f"[*] Release erkannt: {release}  (Geraet {device_of(release)})")
        else:
            _status("[!] Keine Release im Banner gefunden (Scan laeuft trotzdem weiter, "
                    "ohne Bezug zur Matrix).")
    rep = Report(port=port, release=release, banner=banner.strip())

    if _dbg(t):
        _dbg(t).note(f"BANNER geparst: release={release}")
        _dbg(t).note("Phase: EXPERT entsperren")
    rep.expert_prior = unlock_expert(t)
    if progress:
        _status(f"[*] EXPERT: {rep.expert_prior or 'in dieser Firmware nicht vorhanden'}")

    todo = plan(entries, only_group=only_group, immediate=immediate)
    skipped = never_probed(entries)
    if progress:
        _status(f"[*] Frage {len(todo)} Befehle ab; {len(skipped)} Befehle (danger / action_tx / "
                f"mode / NEVER_AUTO) werden nie gesendet. Grobe Dauer ~{max(1, len(todo)//2)}s.")
    tally = {r.value: 0 for r in Result}
    STALL_THRESHOLD = 3          # komplett leere Antworten in Folge -> harte Resync
    stall_count = 0
    current_group = None
    current_mode = None          # unbekannt: das Geraet kann aus einem frueheren Lauf in SIGNAL stehen

    try:
        for i, cmd in enumerate(todo, 1):
            if cmd.group != current_group:
                current_group = cmd.group
                mode_cmd = mode_for(cmd.group)
                if mode_cmd != current_mode:
                    if progress:
                        _status(f"\n[*] Wechsle in Modus {mode_cmd} (Gruppe {cmd.group}) ...")
                    enter_mode(t, mode_cmd)
                    current_mode = mode_cmd
            if _dbg(t):
                _dbg(t).note(f"=== [{i}/{len(todo)}] {cmd.name}  (kind={cmd.kind}) ===")
            result = probe(t, cmd)
            time.sleep(0.03)      # dem TNC Luft lassen

            stall_count = stall_count + 1 if result is Result.ERROR else 0
            if stall_count >= STALL_THRESHOLD:
                if progress:
                    _status(f"\n[!] {stall_count} Befehle in Folge ohne Antwort -- "
                            f"vermuteter Verbindungsverlust. Versuche Resynchronisation ...")
                ok = hard_resync(t)
                if progress:
                    _status(f"[{'*' if ok else '!'}] Resync {'erfolgreich' if ok else 'FEHLGESCHLAGEN'}.")
                rep.expert_prior = unlock_expert(t)
                current_group = None               # Modus nach Resync neu setzen (RESTART
                current_mode = None                # laesst den Opmode stehen, T179)
                stall_count = 0
                if not ok:
                    if progress:
                        _status("[!] Abbruch: Geraet antwortet nicht mehr. "
                                "Bisherige Ergebnisse werden gespeichert.")
                    break

            tally[result.value] += 1
            if progress:
                _status(f"\r  [{i:>3}/{len(todo)}] {cmd.name:<10.10} {result.value:<11} "
                        f"ok={tally['SUPPORTED']:<3} no={tally['UNSUPPORTED']:<3} "
                        f"gated={tally['EXPERT_GATED']:<3}   ", end="")
            e = entries.get(cmd.name)
            rep.rows.append({
                "name": cmd.name, "group": cmd.group, "kind": cmd.kind,
                "result": result.value,
                "matrix": e.fw.get(release, "?") if (e and release) else "?",
                "note": "",
            })
    finally:
        if progress:
            _status("")                       # Zeilenumbruch nach der \r-Laufzeile
            _status("[*] Abfrage fertig. Stelle Betriebsmodus (PACKET) und EXPERT wieder her ...")
        enter_mode(t, "PACKET")
        restore_expert(t, rep.expert_prior)
    if progress:
        _status("[*] Scan abgeschlossen.\n")
    return rep


# ----------------------------------------------------------------------------
# 5. Die Matrix aktualisieren: nur ?-Zellen, vorhandene Belege nie anfassen
# ----------------------------------------------------------------------------
def apply_to_matrix(entries: dict, rows: list, release: str, date: str, device: str,
                    source: str) -> tuple:
    """(neue Matrix, Zahl der gefuellten Zellen, Widersprueche).

    * Zelle ``?``      -> wird mit dem Ergebnis und einem Beleg gefuellt
    * gleiche Aussage  -> bleibt, samt ihrem Beleg
    * expert <-> yes   -> KEIN Widerspruch (der Scan entsperrt EXPERT zuerst)
    * sonst            -> Widerspruch; dann wird NICHTS gefuellt (die alte Matrix kommt zurueck)
    """
    if release not in cm.RELEASES:
        raise ValueError(f"release {release!r} is not a column of the matrix {cm.RELEASES}")
    evidence = (f"fw_scan {date.replace('-', '')} (device {device}, banner Release {release}; "
                f"{source})")
    new = dict(entries)
    filled = 0
    conflicts = []
    for row in rows:
        value = RESULT_TO_CELL.get(row["result"])
        e = new.get(row["name"])
        if value is None or e is None:
            continue
        cell = e.fw[release]
        if cell == "?":
            fw, ev = dict(e.fw), dict(e.ev)
            fw[release], ev[release] = value, evidence
            new[e.name] = dataclasses.replace(e, fw=fw, ev=ev)
            filled += 1
        elif cell != value and {cell, value} != {"yes", "expert"}:
            conflicts.append(f"{e.name} {release}: matrix says {cell} ({e.ev[release][:70]}), "
                             f"this scan says {value}")
    if conflicts:
        return dict(entries), 0, conflicts
    return new, filled, []


# ----------------------------------------------------------------------------
# 6. Ausgabe
# ----------------------------------------------------------------------------
def print_report(rep: Report) -> None:
    print("=" * 74)
    print(f"PK-232 firmware scan  --  port {rep.port}  --  {rep.ts}")
    print("-" * 74)
    print(f"Release      : {rep.release or 'NOT FOUND in banner (see raw banner below)'}"
          f"   device {rep.device}")
    if rep.expert_prior is None:
        print("EXPERT       : not present in this firmware (no expert gating)")
    else:
        print(f"EXPERT       : was {rep.expert_prior}; set ON for scan, restored afterwards")
    print("-" * 74)
    counts: dict = {}
    for r in rep.rows:
        counts[r["result"]] = counts.get(r["result"], 0) + 1
    print("Summary      : " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    differing = [r for r in rep.rows
                 if r["matrix"] != "?" and RESULT_TO_CELL.get(r["result"]) not in (None, r["matrix"])
                 and {r["matrix"], RESULT_TO_CELL.get(r["result"])} != {"yes", "expert"}]
    if differing:
        print("-" * 74)
        print(f"DIFFERENT FROM THE MATRIX ({len(differing)}):")
        for r in differing:
            print(f"  {r['name']:<10} scan {r['result']:<12} matrix {r['matrix']}")
    print("-" * 74)
    print(f"{'NAME':<11}{'GRP':<10}{'KIND':<10}{'MATRIX':<8}RESULT")
    for r in rep.rows:
        print(f"{r['name']:<11}{r['group']:<10}{r['kind']:<10}{r['matrix']:<8}{r['result']}")
    print("=" * 74)
    if not rep.release:
        print("RAW BANNER:")
        print(rep.banner)


CSV_FIELDS = ["release", "device", "date", "name", "group", "kind", "result", "matrix", "note"]


def write_csv(rep: Report, path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        w.writeheader()
        for r in rep.rows:
            w.writerow({"release": rep.release or "", "device": rep.device, "date": rep.date, **r})


def write_json(rep: Report, path: str) -> None:
    payload = {"port": rep.port, "timestamp": rep.ts, "release": rep.release,
               "device": rep.device, "expert_prior": rep.expert_prior,
               "banner": rep.banner, "rows": rep.rows}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)


def print_plan(immediate: bool = False) -> None:
    """Was dieses Werkzeug abfragen wuerde und was es NIE sendet (kein Geraet noetig)."""
    todo = plan(immediate=immediate)
    print(f"# Would probe {len(todo)} commands"
          f"{' (incl. immediate commands)' if immediate else ' (parameters only; --immediate adds the immediate ones)'}")
    for group in GROUP_ORDER:
        names = [c.name for c in todo if c.group == group]
        if names:
            mode = MODE_ENTRY.get(group)
            print(f"\n[{group}]{' after ' + mode if mode else ''}: {' '.join(names)}")
    never = never_probed()
    print(f"\n# Never sent ({len(never)}): kind danger / action_tx / mode, and NEVER_AUTO = "
          f"{', '.join(sorted(NEVER_AUTO))}")
    print(' '.join(f"{n}[{why}]" for n, why in never))


# ----------------------------------------------------------------------------
# 7. main
# ----------------------------------------------------------------------------
_SELFTEST_RELEASE = {"1988": "30.12.1988", "1991": "01.AUG.91", "1995": "13.SEP.95"}


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description="PK-232 firmware capability scanner (command matrix)")
    ap.add_argument("--port", help="serial port, e.g. COM16 or /dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--group", help="restrict the scan to one group (e.g. packet, fax, pactor)")
    ap.add_argument("--csv", help="write the CSV report (release, device, date, ...) to this path")
    ap.add_argument("--json", help="write the JSON report to this path")
    ap.add_argument("--immediate", action="store_true",
                    help="also probe the commands of kind 'immediate' (CSTATUS, LOCK, NUMS, ...); "
                         "danger / action_tx / mode commands are never sent")
    ap.add_argument("--update-matrix", action="store_true",
                    help="fill the ? cells of src/pk232py/data/command_matrix.csv for the scanned "
                         "release; an existing cell and its evidence are never changed, a "
                         "contradiction aborts with a list. Not with --selftest.")
    ap.add_argument("--plan", action="store_true",
                    help="print what would be probed and what is never sent, then exit")
    ap.add_argument("--selftest", metavar="YEAR",
                    help="dry run against a mock firmware (1988|1991|1995) -- no hardware")
    ap.add_argument("--debug", metavar="LOGFILE", nargs="?", const="pk232_scan_debug.log",
                    default=None, help="write every TX/RX to a log (default pk232_scan_debug.log)")
    args = ap.parse_args(argv)

    if args.plan:
        print_plan(args.immediate)
        return 0
    if args.update_matrix and args.selftest:
        print("--update-matrix is refused with --selftest: the mock's answers are invented and "
              "must never enter the matrix.", file=sys.stderr)
        return 2

    dbg = DebugLog(args.debug) if args.debug else None
    if dbg:
        _status(f"[*] Debug-Log: {dbg.path}")
    try:
        return _run(args, ap, dbg)
    finally:
        if dbg:
            dbg.close()             # vollstaendig schreiben, auch bei Fehler / Strg-C (T179)
            _status(f"[*] Debug-Log geschrieben: {dbg.path}")


def _run(args, ap, dbg) -> int:
    if args.selftest:
        if args.selftest not in _SELFTEST_RELEASE:
            print("selftest year must be one of 1988 / 1991 / 1995", file=sys.stderr)
            return 2
        t = MockTransport(_SELFTEST_RELEASE[args.selftest], debug=dbg)
        port = f"MOCK:{args.selftest}"
    else:
        if not args.port:
            ap.error("--port is required (or use --selftest / --plan)")
        _status(f"[*] Oeffne {args.port} @ {args.baud} Baud 8N1 ...")
        t = SerialTransport(args.port, args.baud, debug=dbg)
        port = args.port
        _status(f"[*] {args.port} offen. Starte Scan (Abbruch mit Strg-C) ...")

    try:
        rep = run_scan(t, port, only_group=args.group, immediate=args.immediate)
    except ScanError as exc:
        print(f"[!] {exc}", file=sys.stderr)
        return 4
    finally:
        t.close()

    print_report(rep)
    if args.csv:
        write_csv(rep, args.csv)
        print(f"[+] CSV written: {args.csv}")
    if args.json:
        write_json(rep, args.json)
        print(f"[+] JSON written: {args.json}")

    if args.update_matrix:
        if rep.release not in cm.RELEASES:
            print(f"[!] --update-matrix: release {rep.release!r} is not a column of the matrix "
                  f"{cm.RELEASES}; nothing written.", file=sys.stderr)
            return 3
        entries = cm.load()
        source = Path(args.csv).as_posix() if args.csv else "no csv written"
        new, filled, conflicts = apply_to_matrix(entries, rep.rows, rep.release, rep.date,
                                                 rep.device, source)
        if conflicts:
            print("[!] --update-matrix: the scan contradicts the matrix - NOTHING written:",
                  file=sys.stderr)
            for line in conflicts:
                print(f"    {line}", file=sys.stderr)
            return 3
        cm.save(new)
        print(f"[+] matrix: {filled} cells filled for {rep.release}; run "
              f"python tools/gen_command_matrix.py --update")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
