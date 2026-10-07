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

ALLE BEFEHLE (P89, --all)
=========================
Der Scanner laeuft IMMER an einem TNC ohne Funkgeraet (der Betreiber bestaetigt das, siehe
operator_checks()). Mit --all werden deshalb auch die Befehle abgesetzt, die sonst nie gesendet
werden (kind mode / action_tx / danger, CALIBRATE, TRANS): nach den normalen Abfragen, jeder einzeln,
vom harmlosen zum heikelsten, danach der Rueckweg in den Befehlsmodus aus der Tabelle RECOVERY
(Messgegenstand: welcher Rueckweg wirkte), dann OPMODE und MYCALL. Klappt kein Rueckweg, bittet der
Scanner den Betreiber um ein Aus-/Einschalten (needs_power_cycle) und weckt den TNC danach wie die App.

SICHERHEIT ZUERST (ohne --all)
==============================
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
  python tools/pk232_fw_scan.py --port COM16 --all --update-matrix   # ALLE Befehle (P89), kein Funkgeraet!
  python tools/pk232_fw_scan.py --plan                            # was wuerde gesendet / nie gesendet
  python tools/pk232_fw_scan.py --plan --all                      # dasselbe fuer --all
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
import shutil
import sys
import time
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

# True in der vom Kit-Bauer (tools/build_scan_kit.py) erzeugten, eigenstaendigen Fassung fuer externe
# Funkamateure: dort gibt es keine Matrix zum Fuellen (--update-matrix entfaellt), die Ergebnisse gehen
# immer in einen Ergebnisordner (scan_results) und ein ZIP.
_KIT = False

DEVICE_INFO_TEMPLATE = """# PK-232 scan - device information. Please fill in what you know and send this file back with the results.
# Model: PK-232 / PK-232MBX / with DSP
Model:
# EPROM label as printed on the chip
EPROM label:
# Board options: PACTOR, mailbox, 2400-baud modem
Board options:
# Battery backup (RAM battery): yes / no
Battery backup:
Remarks:

# Filled in by the scanner:
Release: {release}
Callsign: {call}
Date: {date}
Serial: {serial}
"""

# Zeit und Eingabe als Haken: die Tests ersetzen sie durch eine simulierte Uhr (kein echtes Warten
# von 65 s) und vorgegebene Antworten.
_clock = time.monotonic


def _real_sleep(seconds: float) -> None:
    time.sleep(seconds)                 # looked up at call time, so a patched time.sleep still works


_sleep = _real_sleep
_ask = input

# >>> pk232py imports (tools/build_scan_kit.py replaces this block by copies made at build time)
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from pk232py.comm import command_matrix as cm  # noqa: E402
from pk232py.comm.constants import verbose_line  # noqa: E402
from pk232py.comm.constants import FRAME_HOST_OFF  # noqa: E402
# P89b: the ONE function that says "factory state" (the banner line as observed) - the app's too
from pk232py.comm.constants import FACTORY_BANNER_LINES, is_factory_banner  # noqa: E402
from pk232py.comm.devices import KNOWN_DEVICES  # noqa: E402
from pk232py.comm.pk232_hostmode_sub import escape_converse  # noqa: E402
# the SAME wake-up byte and banner markers as the app's detection chain (SerialManager)
from pk232py.comm.serial_manager import _BANNER_MARKERS, _WAKEUP, _XON_BYTE  # noqa: E402
# <<< pk232py imports


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


DEFAULT_TARGET = "NOCALL"      # T186: dummy station for ARQ / SELFEC / PTCONN (--target)


@dataclass
class Cmd:
    name: str
    group: str
    kind: str
    abbrev: str = ""


def plan(entries: Optional[dict] = None, only_group: Optional[str] = None,
         immediate: bool = False, only: Optional[set] = None) -> list:
    """Die abzufragenden Befehle aus der Matrix, nach Betriebsart gruppiert und alphabetisch.
    kind danger / action_tx / mode und NEVER_AUTO sind nie dabei; 'immediate' nur auf Wunsch.
    *only* (P89a, --only): genau diese Namen (jede param/immediate-Art), sonst nichts."""
    entries = cm.all_entries() if entries is None else entries
    kinds = ("param", "immediate") if (immediate or only) else ("param",)
    out = []
    for name, e in entries.items():
        if name in NEVER_AUTO or e.kind not in kinds:
            continue
        if only is not None and name not in only:
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


class SimulatedClock:
    """Eine Uhr, die nur vorgeht, wenn gelesen oder gewartet wird: --selftest --all wartet so keine
    65 s (CALIBRATE) und die Tests koennen das Timing des Mocks (CMDTIME, 60 s) pruefen."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


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

    Geraet eines externen Betreibers (P90): ``opmode``, ``expert_on``, ``echo_on`` sind der Zustand, in
    dem es steht (Pufferbatterie); bei ``echo_on=False`` kommt kein Echo; ``sticky={"EXPERT OFF"}`` --
    diese Befehle werden angenommen, aendern aber nichts (der Zustand bleibt anders als vorher).

    Riskante Befehle (P89, ``risky=True``, Zeit aus ``clock`` bzw. scan._clock):
      * TRANS -> Transparentmodus: nur drei Ctrl-C innerhalb von CMDTIME (1 s) nach mindestens 1 s
        Ruhe verlassen ihn (STABO Kap. 4); hastiges Ctrl-C bewirkt nichts (der Juli-Lauf)
      * CALIBRATE -> kehrt bei ``Q`` zurueck (``calibrate_ignores_q``: erst nach 60 s von allein)
      * ``stuck={"XMIT": "RCVE"}`` -- nach XMIT hilft nur dieser eine Befehl, kein Ctrl-C
      * ``dead_after={"XMIT"}`` -- danach bleibt der TNC stumm bis ``power_cycle()``
      * RESTART setzt MYCALL auf den Werkszustand (PK232) zurueck; ``power_cycle()`` ebenso
    """

    _MODES = ("PACKET", "BAUDOT", "AMTOR", "MORSE", "FAX", "NAVTEX", "SIGNAL")
    FACTORY_MYCALL = "PK232"
    CMDTIME = 1.0
    _NEEDS_MYCALL = {"CONVERSE", "K", "ID", "TRANS", "ALIST", "AMTOR", "FEC", "ARQ", "SELFEC"}
    _NEEDS_SELCAL = {"ALIST", "AMTOR", "FEC", "ARQ", "SELFEC", "ACHG", "OVER"}
    _MODE_RULES = {"XMIT": "BAUDOT", "RCVE": "BAUDOT", "ACHG": "AMTOR", "OVER": "AMTOR"}
    MAILBOX_PROMPT = "(AEA PK-232M)  18536 free  (B,E,K,L,R,S) >"

    def __init__(self, release: str, entries: Optional[dict] = None,
                 debug: Optional["DebugLog"] = None, slow_in_signal: bool = False,
                 late: Optional[set] = None, silent: Optional[set] = None,
                 needs_star_first: bool = False, restart_needs_star: bool = False,
                 banner_late_reads: int = 0, ignores_star: bool = False,
                 in_converse: bool = False, deaf: bool = False,
                 clock=None, risky: bool = False, calibrate_ignores_q: bool = False,
                 stuck: Optional[dict] = None, dead_after: Optional[set] = None,
                 opmode: str = "PACKET", expert_on: bool = False, echo_on: bool = True,
                 sticky: Optional[set] = None, needs_mycall: bool = False, needs_selcal: bool = False,
                 memory_needs_expert: bool = False, mode_rules: bool = False, over_needs_link: bool = False,
                 needs_target: bool = False, fec_sticks: bool = False, keeps_settings_cycles: int = 0):
        self.release = release
        # T186/P89b, as measured: MYSELCAL takes a 4-letter word (also 'none' -> 'NONE'), anything else ('%', 'OFF')
        # answers ?callsign - nothing clears it (A, B); ARQ / SELFEC / PTCONN answer ?callsign without a target;
        # FEC leaves OPMODE at FEC after Ctrl-C and refuses every other mode but PACKET (device C); the first
        # *keeps_settings_cycles* power cycles keep the settings and print the banner WITHOUT the factory line
        self.needs_target, self.fec_sticks = needs_target, fec_sticks
        self.keeps_settings_cycles = keeps_settings_cycles
        self._factory_banner = True           # does the next power-on banner carry the factory line?
        self._boot_banner_pending = False     # a device that keeps its baud rate prints the banner at power-on
        self.needs_mycall, self.needs_selcal = needs_mycall, needs_selcal
        self.memory_needs_expert, self.mode_rules = memory_needs_expert, mode_rules
        self.over_needs_link = over_needs_link
        self.myselcal = "none"
        self.mailbox = False
        self.entries = cm.all_entries() if entries is None else entries
        self.debug = debug
        self.sent: list = []
        self._pending = ""
        self._late_reads = 0          # so many read_idle() calls return '' before the reply
        self.expert_on = expert_on
        self.echo_on = echo_on
        self.sticky = {x.upper() for x in (sticky or ())}
        self.opmode = opmode
        self.mycall = self.FACTORY_MYCALL
        self.slow_in_signal = slow_in_signal
        self.late = set(late or ())
        self.silent = set(silent or ())
        self.restart_needs_star = restart_needs_star
        self.banner_late_reads = banner_late_reads
        self.ignores_star = ignores_star
        self.in_converse = in_converse
        self.deaf = deaf
        self.clock = clock
        self.risky = risky
        self.calibrate_ignores_q = calibrate_ignores_q
        self.stuck = dict(stuck or {})
        self.dead_after = set(dead_after or ())
        self._needs_star_first = needs_star_first
        self._autobaud = needs_star_first     # waiting for the '*' that measures the baud rate
        self.transparent = False
        self.calibrating = False
        self._calibrate_since = 0.0
        self._stuck_until = None              # the one command that releases a stuck TNC
        self._ctrl_times: list = []
        self._last_other = 0.0
        self.since_power_cycle: list = []
        expert = self.entries.get("EXPERT")
        self.has_expert = expert is None or expert.fw.get(release) != "no"

    # -- time ----------------------------------------------------------------
    def _now(self) -> float:
        return (self.clock or _clock)()

    def _tick(self, seconds: float) -> None:
        c = self.clock or _clock
        if hasattr(c, "advance"):
            c.advance(seconds)

    def power_cycle(self) -> None:
        """The operator switches the TNC off and on: factory state, awake only for a first '*' when
        the device needs it (device C). The first *keeps_settings_cycles* cycles keep MYCALL / MYSELCAL and the
        banner has no factory line (P89b: a short pause kept the settings at device A)."""
        self.deaf = False
        self._autobaud = self._needs_star_first
        kept = self.keeps_settings_cycles > 0
        if kept:
            self.keeps_settings_cycles -= 1
        else:
            self.mycall = self.FACTORY_MYCALL
            self.myselcal = "none"
        self._factory_banner = not kept
        self._boot_banner_pending = not self._needs_star_first
        self.mailbox = False
        self.opmode = "PACKET"
        self.expert_on = False
        self.echo_on = True
        self.transparent = self.calibrating = self.in_converse = False
        self._stuck_until = None
        self.dead_after = set()
        self._pending = ""
        self._late_reads = 0
        self.since_power_cycle = []

    def _cell(self, name: str) -> str:
        e = self.entries.get(name)
        return e.fw.get(self.release, "?") if e else "?"

    def _reply(self, text: str, name: str = "") -> None:
        """Queue *text*; an undelivered earlier reply stays in front of it (the pipeline shift)."""
        if name in self.silent:
            return
        if not self.echo_on and name and text.upper().startswith(name.upper() + "\r\n"):
            text = text[len(name) + 2:]               # ECHO OFF: the typed characters are not echoed
        slow = self.slow_in_signal and self.opmode == "SIGNAL" and name not in self._MODES
        if slow:
            text += "noise\r\n"
        self._pending += text
        self._late_reads = 1 if (slow or name in self.late) else 0

    def _banner(self, factory: Optional[bool] = None) -> str:
        """The sign-on banner; the factory line only after a power-on at the factory state (RESTART keeps the
        settings and prints none - hw_logs/20261007_fw_only_*.log line 9)."""
        day, mon, yy = self.release.split(".")
        line = "PK-232M is using default values.\r\n" if (self._factory_banner if factory is None else factory) else ""
        return (f"\r\n{line}"
                "AEA PK-232M Data Controller\r\n"
                f"Release {day}.{mon}.{yy}\r\ncmd:")

    def _risky_state(self, data: bytes, now: float) -> bool:
        """The states of the risky commands; True if *data* was consumed by one of them."""
        if self.calibrating and now - self._calibrate_since >= 60.0:
            self.calibrating = False                  # CALIBRATE ends by itself after 60 s
            self._reply("cmd:")
        if self.mailbox:                              # only the mailbox's Bye leaves it (T182/T183)
            if data.strip().upper() == b"B":
                self.mailbox = False
                self._reply("B\r\ncmd:")
            return True
        if self.transparent:
            if data == CTRL_C:
                self._ctrl_times.append(now)
                last3 = self._ctrl_times[-3:]
                if (len(last3) == 3 and last3[2] - last3[0] <= self.CMDTIME
                        and last3[0] - self._last_other >= self.CMDTIME):
                    self.transparent = False          # three COMMAND characters within CMDTIME
                    self._ctrl_times = []
                    self._reply("cmd:")
            else:
                self._last_other = now
                self._ctrl_times = []
            return True
        if self.calibrating:
            if data == b"Q" and not self.calibrate_ignores_q:
                self.calibrating = False
                self._reply("cmd:")
            return True
        if self._stuck_until is not None:
            text = data.decode("latin-1").strip().upper()
            if text == self._stuck_until:
                self._stuck_until = None
                if text in self._MODES:
                    self.opmode = text
                self._reply("cmd:")
            return True
        return False

    def write(self, data: bytes) -> None:
        self.sent.append(bytes(data))
        self.since_power_cycle.append(bytes(data))
        if self.debug:
            self.debug.tx(data)
        if self.deaf:
            return
        now = self._now()
        if self._autobaud:
            # the first byte after power-on / RESTART measures the baud rate: only '*' does it,
            # anything else leaves the TNC deaf for good (T180, device C)
            if data == STAR:
                self._autobaud = False
                self._pending, self._late_reads = self._banner(), self.banner_late_reads
            else:
                self.deaf = True
            return
        if self.risky and self._risky_state(data, now):
            return
        if data == CTRL_C or data == CTRL_C + b"\r":
            self._pending = ""                      # Ctrl-C clears whatever was still on its way
            self._late_reads = 0
            self.in_converse = False
            self._reply("cmd:")
            return
        if data == STAR:
            if self._boot_banner_pending:           # the banner a device that keeps its baud rate prints at power-on
                self._boot_banner_pending = False
                self._pending, self._late_reads = self._banner(), self.banner_late_reads
                return
            if not self.ignores_star and not self.in_converse:
                self._reply("*\\\r\ncmd:")           # a TNC at the prompt answers '*' with a prompt
            return
        if self.in_converse:                        # Converse echoes everything, shows no prompt
            self._pending += data.decode("latin-1")
            return
        line = data.decode("latin-1").strip()
        name = line.upper()
        if name in self.sticky:                     # accepted, but nothing changes
            self._reply(f"{name}\r\ncmd:", name)
            return
        if name == "RESTART":
            self._pending = ""
            self._late_reads = 0
            self.mycall = self.FACTORY_MYCALL
            self.myselcal = "none"
            if self.restart_needs_star:
                self._autobaud = True               # autobaud again, the banner comes after '*'
                return
            self._factory_banner = False            # RESTART keeps the settings: its banner has no factory line
            self._pending, self._late_reads = "RESTART\r\n" + self._banner(), self.banner_late_reads
            return                                  # (the opmode survives)
        if name == "OPMODE":
            self._reply(f"OPMODE\r\nOPMODE   {self.opmode}\r\ncmd:", name)
            return
        if name == "ECHO":
            self._reply(f"ECHO\r\nECHo      {'ON' if self.echo_on else 'OFF'}\r\ncmd:", name)
            return
        if name in ("ECHO ON", "ECHO OFF"):
            new = name.endswith("ON")
            old = "ON" if self.echo_on else "OFF"
            self._reply(f"{name}\r\nECHo      was {old}\r\nECHo      now {'ON' if new else 'OFF'}\r\ncmd:", name)
            self.echo_on = new                      # the echo of THIS line was decided by the old state
            return
        if name == "DISPLAY":
            self._reply("DISPLAY\r\n(See also DISPLAY A,B,C,F,I,L,M,R,T,Z)\r\n"
                        "Connect   Link state is: DISCONNECTED\r\n"
                        f"Opmode    {self.opmode}\r\n"
                        f"ECHo      {'ON' if self.echo_on else 'OFF'}\r\n"
                        f"EXPert    {'ON' if self.expert_on else 'OFF'}\r\n"
                        f"MYcall    {self.mycall}\r\n"
                        f"MYSelcal  {self.myselcal}\r\ncmd:", name)
            return
        if name.startswith("MYSELCAL"):
            arg = line[8:].strip()
            if arg:
                old = self.myselcal
                if not (len(arg) == 4 and arg.isalpha()):
                    self._reply(f"MYSELCAL {arg}\r\n?callsign\r\ncmd:", name)
                    return
                self.myselcal = arg.upper()
                self._reply(f"MYSELCAL {arg}\r\nMYSelcal  was {old}\r\nMYSelcal  now {self.myselcal}\r\ncmd:", name)
            else:
                self._reply(f"MYSELCAL\r\nMYSelcal  {self.myselcal}\r\ncmd:", name)
            return
        if name.startswith("MYCALL"):
            arg = line[6:].strip()
            if arg:
                old, self.mycall = self.mycall, arg.upper()
                self._reply(f"MYCALL {arg}\r\nMYcall    was {old}\r\nMYcall    now {self.mycall}\r\ncmd:", name)
            else:
                self._reply(f"MYCALL\r\nMYcall    {self.mycall}\r\ncmd:", name)
            return
        head, _, target = line.partition(" ")
        if self.needs_target and head.upper() in TARGET_CMDS:
            if not target.strip():
                self._reply(f"{head.upper()}\r\n?callsign\r\ncmd:", name)
            else:
                self._reply(f"{line}\r\n", name)     # calls the station: no prompt until Ctrl-C
            return
        if self.fec_sticks and self.opmode == "FEC" and name != "PACKET" and (
                name in self._MODES or name in self._MODE_RULES or name == "ID"):
            self._reply(f"{name}\r\n?not while in FEC      \r\ncmd:", name)
            return
        if self.fec_sticks and name == "FEC":
            old, self.opmode = self.opmode, "FEC"
            self._reply(f"FEC\r\nOPMODE   was {old}\r\nOPMODE   now FEC\r\n", name)
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
            return
        if self.needs_mycall and self.mycall == self.FACTORY_MYCALL and name in self._NEEDS_MYCALL:
            self._reply(f"{name}\r\n?need MYcall\r\ncmd:", name)
            return
        if self.needs_selcal and self.myselcal == "none" and name in self._NEEDS_SELCAL:
            self._reply(f"{name}\r\n?need MYSELCAL\r\ncmd:", name)
            return
        if self.memory_needs_expert and name == "MEMORY" and not self.expert_on:
            self._reply(f"{name}\r\n?EXPERT command\r\ncmd:", name)
            return
        if self.mode_rules and name in self._MODE_RULES:
            if self.opmode != self._MODE_RULES[name] or (name == "OVER" and self.over_needs_link):
                self._reply(f"{name}\r\n?not while in {self.opmode[:2]}{self.opmode[2:].lower()}\r\ncmd:", name)
                return
            if name == "XMIT":
                self._reply("XMIT\r\n", name)         # keys the transmitter: no prompt
                return
        if self.risky and name == "MDCHECK":
            self.mailbox = True
            self._reply(f"MDCHECK\r\n{self.MAILBOX_PROMPT}", name)
            return
        if self.risky and name == "TRANS":
            self.transparent, self._last_other, self._ctrl_times = True, now, []
            self._reply("TRANS\r\n", name)
            return
        if self.risky and name == "CALIBRATE":
            self.calibrating, self._calibrate_since = True, now
            self._reply("CALIBRATE\r\n", name)
            return
        if self.risky and name in self.stuck:
            self._stuck_until = self.stuck[name].upper()
            self._reply(f"{name}\r\n", name)
            return
        if self.risky and name in self.dead_after:
            self._reply(f"{name}\r\n", name)
            self.deaf = True                        # silent until the operator power-cycles it
            return
        if self.risky and name in ("CONVERSE", "K"):
            self.in_converse = True
            self._reply(f"{name}\r\n", name)
            return
        if cell == "expert" and not self.expert_on:
            self._reply(f"{name}\r\n?EXPERT command\r\ncmd:", name)
        else:
            self._reply(f"{name}\r\n{name} 0\r\ncmd:", name)

    def read_idle(self, idle_s: float = 0.25, max_s: float = 3.0) -> str:
        self._tick(0.2)                             # a quiet read takes time (the real port: ~0.4 s)
        if self.risky and not self.deaf and self.calibrating and \
                self._now() - self._calibrate_since >= 60.0:
            self.calibrating = False
            self._pending += "cmd:"
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
    echo_prior: Optional[str] = None     # ECHO vor dem Scan ('ON'/'OFF'); bei OFF wird es fuer den Scan eingeschaltet
    opmode_before: Optional[str] = None  # der Betriebsmodus, in dem das Geraet stand
    banner_raw: str = ""                 # das Einschaltbanner WOERTLICH (nichts normalisiert)
    settings_before: str = ""            # Ausgabe von DISPLAY vor dem Scan
    settings_after: str = ""             # ... und nachdem der Zustand wiederhergestellt wurde
    state_diff: list = field(default_factory=list)   # Zeilen, die nachher anders sind (leer = wie vorher)
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

    Das ERSTE Byte ist immer das '*': Geraet C (30.DEC.88) wartet nach dem Einschalten darauf
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
    _sleep(0.1)
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
    _sleep(0.3)
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


# ----------------------------------------------------------------------------
# 4a. Das Geraet so zuruecklassen, wie es war (P90): Geraete externer Betreiber haben eine Pufferbatterie
# und damit eigene Einstellungen (EXPERT ON, ECHO OFF, ein anderer Betriebsmodus ...)
# ----------------------------------------------------------------------------
MODE_COMMANDS = ("PACKET", "BAUDOT", "ASCII", "AMTOR", "MORSE", "FAX", "NAVTEX", "SIGNAL", "TDM", "PACTOR")
_OPMODE_RE = re.compile(r"Opmode[ \t]+(\w+)", re.IGNORECASE)       # 'Opmode    PAcket' (same line!)
_ECHO_RE = re.compile(r"\bECHo?[ \t]+(ON|OFF)\b", re.IGNORECASE)    # 'ECHo      ON'


@dataclass
class DeviceState:
    opmode: Optional[str] = None
    echo: Optional[str] = None
    display: str = ""


def query_text(t, name: str, reads: int = _STEP_READS) -> str:
    """Eine Abfrage; die Antwort OHNE Echo und Prompt. Auch bei ECHO OFF (dann gibt es kein Echo)."""
    t.write(verbose_line(name))
    resp = read_until(t, ("cmd:",), reads=reads)
    got = answer_to(name, resp)
    return got[0] if got else resp.split("cmd:", 1)[0]


def read_opmode(t) -> Optional[str]:
    m = _OPMODE_RE.search(query_text(t, "OPMODE"))
    return m.group(1).upper() if m else None


def read_echo(t) -> Optional[str]:
    m = _ECHO_RE.search(query_text(t, "ECHO"))
    return m.group(1).upper() if m else None


def read_display(t) -> str:
    """Die Ausgabe von DISPLAY roh (alle Parameter, die der TNC zeigt)."""
    t.write(verbose_line("DISPLAY"))
    return read_until(t, ("cmd:",), reads=3 * _STEP_READS)


def display_lines(text: str) -> list:
    lines = (ln.strip() for ln in re.split(r"[\r\n]+", text.replace("cmd:", "\n")))
    return [ln for ln in lines if ln and ln.upper() != "DISPLAY"]


def settings_diff(before: str, after: str) -> list:
    """Die Zeilen, die vorher da waren und nachher fehlen ('- ...'), und umgekehrt ('+ ...')."""
    b, a = set(display_lines(before)), set(display_lines(after))
    return sorted(f"- {ln}" for ln in b - a) + sorted(f"+ {ln}" for ln in a - b)


def capture_state(t) -> DeviceState:
    """Vor dem Scan lesen, was der Scan beruehrt (ECHO, Betriebsmodus) und alle Einstellungen (DISPLAY)."""
    state = DeviceState()
    state.echo = read_echo(t)
    state.opmode = read_opmode(t)
    state.display = read_display(t)
    return state


def restore_state(t, state: DeviceState, rep: "Report") -> None:
    """Betriebsmodus, EXPERT und ECHO wie vorher; danach DISPLAY noch einmal und der Vergleich."""
    enter_mode(t, state.opmode if state.opmode in MODE_COMMANDS else "PACKET")
    restore_expert(t, rep.expert_prior)
    if rep.echo_prior == "OFF":
        t.write(verbose_line("ECHO OFF"))
        read_until(t, ("cmd:",))
    rep.settings_after = read_display(t)
    rep.state_diff = settings_diff(rep.settings_before, rep.settings_after)


def run_scan(t, port: str, only_group: Optional[str] = None, progress: bool = True,
             immediate: bool = False, entries: Optional[dict] = None, risky: bool = False,
             mycall: Optional[str] = None, confirm_power_cycle=None, myselcal: Optional[str] = None,
             only: Optional[set] = None, target: str = DEFAULT_TARGET) -> Report:
    entries = cm.all_entries() if entries is None else entries
    banner = capture_banner(t)
    release = banner_release(banner)
    if progress:
        if release:
            _status(f"[*] Release erkannt: {release}  (Geraet {device_of(release)})")
        else:
            _status("[!] Keine Release im Banner gefunden (Scan laeuft trotzdem weiter, "
                    "ohne Bezug zur Matrix).")
    rep = Report(port=port, release=release, banner=banner.strip(), banner_raw=banner)

    # P90: what the device had before - settings of a device with a battery stay as they were
    state = capture_state(t)
    rep.settings_before, rep.opmode_before, rep.echo_prior = state.display, state.opmode, state.echo
    if progress:
        _status(f"[*] Zustand vorher: Opmode {state.opmode}, ECHO {state.echo} (DISPLAY gesichert)")
    if state.echo == "OFF":
        _dbg_note(t, "ECHO is OFF: switched ON for the scan (every answer is read after its echo), restored at the end")
        t.write(verbose_line("ECHO ON"))
        read_until(t, ("cmd:",))

    if _dbg(t):
        _dbg(t).note(f"BANNER geparst: release={release}")
        _dbg(t).note("Phase: EXPERT entsperren")
    rep.expert_prior = unlock_expert(t)
    if progress:
        _status(f"[*] EXPERT: {rep.expert_prior or 'in dieser Firmware nicht vorhanden'}")

    todo = plan(entries, only_group=only_group, immediate=immediate, only=only)
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
            _sleep(0.03)      # dem TNC Luft lassen

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
        if risky:
            # P89: every command that is otherwise never sent, one by one, after all normal queries
            risky_rows = run_risky(t, entries, mycall=mycall, confirm_power_cycle=confirm_power_cycle,
                                   progress=progress, myselcal=myselcal,
                                   expert=rep.expert_prior is not None, only=only, target=target)
            for row in risky_rows:
                e = entries.get(row["name"])
                row["matrix"] = e.fw.get(release, "?") if (e and release) else "?"
            rep.rows.extend(risky_rows)
    finally:
        if progress:
            _status("")                       # Zeilenumbruch nach der \r-Laufzeile
            _status("[*] Abfrage fertig. Stelle Betriebsmodus, EXPERT und ECHO wieder her ...")
        restore_state(t, state, rep)
    if progress:
        _status("[*] Scan abgeschlossen.\n")
    return rep


# ----------------------------------------------------------------------------
# 4b. Riskante Befehle (P89, --all)
# ----------------------------------------------------------------------------
OPERATOR_CHECKS = (
    "No radio is connected to the TNC (or only a dummy load).",
    "I am at the TNC and can power-cycle it when asked.",
)


def operator_step(title: str, do: list, then: str) -> None:
    """Eine Schrittanweisung fuer den Betreiber (dieselbe Form wie hw_check.operator_step)."""
    print()
    print("=" * 62)
    print(title)
    print("DO:")
    for i, action in enumerate(do, 1):
        print(f"  {i}. {action}")
    print(f"THEN: {then}")
    print("=" * 62)


# P89b: switching off and on again does NOT always give the factory state (hand test at device A, 07.10.2026:
# after a short pause the banner came without an extra line and MYSELCAL stayed NONE; after a longer one the line
# 'PK-232M is using default values.' came first and MYSELCAL was 'none'). The factory state is what
# is_factory_banner() says about the banner - not the fact that the operator switched the TNC off.
POWER_OFF_SECONDS = 10
POWER_OFF_NOTE = (f"the {POWER_OFF_SECONDS} s is a starting value, NOT measured (P89b): a short pause kept the settings "
                  "at device A, a longer one gave the factory state - how long is needed is open")
POWER_CYCLE_INSTRUCTION = f"Switch the TNC off, wait at least {POWER_OFF_SECONDS} seconds, switch it on."
POWER_CYCLE_TRIES = 3
KEPT_SETTINGS_TEXT = "TNC kept its settings - switch off longer and repeat"


def power_cycle_and_check(t, title: str, confirm, tries: int = POWER_CYCLE_TRIES) -> bool:
    """The ONE operator step for a power cycle: show it, let the operator do it (*confirm*), wake the TNC like the
    app and read the banner to the prompt. True once the banner has the factory line (is_factory_banner); without
    it the TNC kept its settings: say so and show the step again, up to *tries* times, then False (the caller
    goes on - it sets what it needs anyway - and the report says it)."""
    for attempt in range(1, tries + 1):
        operator_step(title, [POWER_CYCLE_INSTRUCTION], "press ENTER here when it is on again")
        confirm()
        banner = wake(t)
        if "cmd:" not in banner:
            banner += read_until(t, ("cmd:",))
        factory = is_factory_banner(banner)
        _dbg_note(t, f"power cycle {attempt}/{tries}: banner has the factory line: {factory}")
        if factory:
            return True
        _status(f"[!] {KEPT_SETTINGS_TEXT} (attempt {attempt} of {tries})")
    return False


def operator_checks(ask=None) -> bool:
    """Vorbedingung von --all, nicht abschaltbar: der Betreiber bestaetigt EINZELN, dass kein Funkgeraet
    angeschlossen ist und dass er am TNC ist und ihn aus- und einschalten kann. Nur das Wort ``yes``
    zaehlt; bei der ersten Absage wird nicht weiter gefragt."""
    ask = ask or _ask
    operator_step("--all: every command is sent, also those that key the transmitter, switch the "
                  "mode or break the session", list(OPERATOR_CHECKS),
                  "answer both questions with the word yes; anything else stops the run")
    for text in OPERATOR_CHECKS:
        if ask(f"{text}  Type yes to confirm: ").strip().lower() != "yes":
            return False
    return True


@dataclass(frozen=True)
class Step:
    """Ein Rueckweg: eine Folge von Aktionen, danach wird auf 'cmd:' gewartet.
    Aktionen: ("tx", Bytes) | ("sleep", Sekunden) | ("wait", Sekunden) | ("banner",)."""
    label: str
    actions: tuple


def _tx(label: str, data: bytes) -> Step:
    return Step(label, (("tx", data),))


# EINE Tabelle Art -> Rueckwege in der Reihenfolge, in der sie probiert werden. Sie ist Messgegenstand:
# welcher Rueckweg je Befehl und Firmware wirkte, steht danach in der Matrix (fx_). Zwischen den
# Aktionen eines Rueckwegs wird NICHT gelesen: TRANS verlangt drei COMMAND-Zeichen innerhalb CMDTIME.
RECOVERY: dict = {
    "mode": (_tx("PACKET", verbose_line("PACKET")), _tx("Ctrl-C", CTRL_C)),
    "action_tx": (_tx("Ctrl-C", CTRL_C), _tx("RCVE", verbose_line("RCVE")),
                  _tx("DISCONNE", verbose_line("DISCONNE")), _tx("PACKET", verbose_line("PACKET"))),
    # STABO Kap. 4: Pause, dreimal das COMMAND-Zeichen innerhalb CMDTIME (Default 1 s), Pause; der
    # Juli-Lauf sandte Ctrl-C ohne Pause davor - das genuegte nicht
    "TRANS": (Step("3xCtrl-C/CMDTIME", (
        ("sleep", 1.5), ("tx", CTRL_C), ("sleep", 0.2), ("tx", CTRL_C), ("sleep", 0.2),
        ("tx", CTRL_C), ("sleep", 1.5), ("tx", CTRL_C))),),
    # STABO Kap. 3: K tastet, Leertaste wechselt Mark/Space, nach 60 s automatisch zurueck auf Empfang
    "CALIBRATE": (_tx("Q", b"Q"), _tx("Ctrl-C", CTRL_C), Step("wait 65s", (("wait", 65.0), ("tx", CTRL_C)))),
    "CONVERSE": (_tx("Ctrl-C", CTRL_C),),                      # wie escape_converse() der App
    "RESTART": (Step("banner/*", (("banner",),)),),            # RESTART, RESET, REINIT
    "HOST": (_tx("HOST OFF", FRAME_HOST_OFF),),                # wie die App (HOST OFF-Frame)
    "danger": (_tx("Ctrl-C", CTRL_C), _tx("CR", b"\r")),
    # MDCHECK opens the MailDrop mailbox (T182/T183: '(AEA PK-232M)  18536 free  (B,E,K,L,R,S) >'); Ctrl-C does
    # NOT leave it - the Bye of the mailbox does, as in the app (MailDropSession): 'B' returns straight to cmd:
    "MDCHECK": (_tx("B", b"B\r"), _tx("Ctrl-C", CTRL_C)),
}


def _seq(label: str, *parts) -> Step:
    """One recovery step of several actions in a row (bytes = send, number = pause); nothing is read in
    between, 'cmd:' is awaited after the last one (like every step)."""
    actions = []
    for i, part in enumerate(parts):
        if i:
            actions.append(("sleep", 0.5))
        actions.append(("tx", part))
    return Step(label, tuple(actions))


# P89a/T186: Ctrl-C brought the prompt back but NOT the operating mode: device C stayed in FEC and refused ID and
# XMIT afterwards ('?not while in FEC'), A and B stayed in FEC / AMTOR. So these two end with an explicit PACKET;
# the older single steps stay behind them as fallbacks (a label in the matrix says which one worked).
RECOVERY["FEC"] = (_seq("Ctrl-C+PACKET", CTRL_C, verbose_line("PACKET")),) + RECOVERY["action_tx"]
# ARQ / SELFEC / PTCONN call a (dummy) station: break off, disconnect, back to PACKET
RECOVERY["link"] = (_seq("Ctrl-C+DISCONNE+PACKET", CTRL_C, verbose_line("DISCONNE"), verbose_line("PACKET")),) \
                   + RECOVERY["action_tx"]

# P89a: the operating mode a command only works in (T182-T184: ?not while in PACKET). ONE place, next to
# RECOVERY; the command is tried there and the scan goes back to PACKET afterwards.
NEEDS_MODE: dict = {"XMIT": "BAUDOT", "RCVE": "BAUDOT", "ACHG": "AMTOR", "OVER": "AMTOR"}

# T186: these answered '?callsign' without an argument; they get a dummy target (--target, default NOCALL).
TARGET_CMDS = ("ARQ", "SELFEC", "PTCONN")        # DEFAULT_TARGET: top of the file (run_scan needs it earlier)


def opmode_word(text: str) -> str:
    """The operating mode in an OPMODE answer, upper case: 'OPMODE   FEC  IDLE SEND' -> 'FEC',
    'Opmode AMtor STBY RCVE' -> 'AMTOR' ('' if there is none)."""
    m = re.search(r"opmode\s+(\w+)", text, re.IGNORECASE)
    return m.group(1).upper() if m else ""


def recovery_kind(name: str, kind: str) -> str:
    """Welche Zeile der Tabelle RECOVERY fuer diesen Befehl gilt."""
    if name in ("TRANS", "CALIBRATE", "HOST", "FEC"):
        return name
    if name in TARGET_CMDS:
        return "link"
    if name in ("CONVERSE", "K"):
        return "CONVERSE"
    if name in ("RESTART", "RESET", "REINIT"):
        return "RESTART"
    if name == "MDCHECK":
        return "MDCHECK"
    return kind if kind in ("mode", "action_tx") else "danger"


def usable_call(call: Optional[str]) -> Optional[str]:
    """A callsign the TNC accepts as 'set': the factory MYCALL (PK232) and NOCALL are not (T182: the TNC answers
    ?need MYcall while MYCALL is still PK232)."""
    call = (call or "").strip().upper()
    return None if call in ("", "NOCALL", "PK232") else call


def derive_selcal(call: Optional[str]) -> Optional[str]:
    """A 4-letter AMTOR SELCAL from a callsign: the first two and the last two letters (OE3GAS -> OEAS)."""
    letters = re.sub(r"[^A-Z]", "", (call or "").upper())
    return letters[:2] + letters[-2:] if len(letters) >= 4 and call and usable_call(call) else None


# Vom harmlosen zum heikelsten: erst die Moduswechsel, dann die tastenden Befehle, dann der Rest; ganz
# am Ende die, die die Sitzung brechen oder den TNC neu starten.
_RISK_TAIL = ["MEMORY", "TRANS", "CALIBRATE", "RESTART", "RESET", "REINIT"]
_KIND_RANK = {"mode": 0, "action_tx": 1, "danger": 2}


def risky_plan(entries: Optional[dict] = None, only: Optional[set] = None) -> list:
    """Alle Befehle, die ohne --all nie gesendet werden, vom harmlosen zum heikelsten
    (mit *only*: nur die genannten)."""
    entries = cm.all_entries() if entries is None else entries
    out = []
    for name, _why in never_probed(entries):
        if only is not None and name not in only:
            continue
        e = entries[name]
        out.append(Cmd(name, GROUP_OF.get(name, "other"), e.kind, e.abbrev))

    def rank(c):
        if c.name in _RISK_TAIL:
            return (3 + _RISK_TAIL.index(c.name), c.name)
        return (_KIND_RANK.get(c.kind, 2), c.name)

    return sorted(out, key=rank)


@dataclass
class Behaviour:
    """Was ein riskanter Befehl bewirkt hat (P89): ob er existiert, was er tat, welcher Rueckweg wirkte."""
    name: str
    kind: str
    exists: Optional[str] = None          # "yes" / "no" / None = keine eigene Antwort
    effect: str = ""
    recovery: str = ""                    # Label des wirkenden Rueckwegs, "none needed" oder "needs_power_cycle"
    steps: list = field(default_factory=list)      # [(Label, hat geklappt)]
    raw: list = field(default_factory=list)        # [(Sekunden seit dem Senden, Text)]
    recorded_s: float = 0.0
    opmode: str = ""
    mycall: str = ""
    precondition: str = ""                # P89a: the refusal for a missing precondition (NOT an effect)
    mode: str = ""                        # the operating mode the command was tried in (NEEDS_MODE)


_EFFECT_NO_PROMPT = {
    "TRANS": "enters transparent mode",
    "CALIBRATE": "starts the AFSK calibration (keys the tones)",
    "XMIT": "starts the transmission",
    "FEC": "starts an AMTOR FEC transmission",
    "ARQ": "starts an AMTOR ARQ call",
    "SELFEC": "starts a selective FEC call",
    "CONVERSE": "enters converse mode",
    "K": "enters converse mode",
}
_OPMODE_NOW = re.compile(r"Opmode\s+now\s+(\w+)", re.IGNORECASE)
_BANNER_TEXT = re.compile(r"Release\s+\S+|is using default values", re.IGNORECASE)
_MAILBOX_PROMPT = re.compile(r"[(\[]\s*AEA\s+PK-232\w*\s*[)\]]\s+\d+\s+free", re.IGNORECASE)


def precondition_of(text: str) -> str:
    """The TNC's refusal for a missing precondition - ?need MYcall, ?need MYSELCAL, ?not while in ...,
    ?EXPERT command, ?callsign - or '' (T182-T184). ?What? is not one: that is 'unknown command'."""
    for ln in text.splitlines():
        ln = ln.strip()
        if ln.startswith(("?", "***")) and not WHAT_RE.search(ln):
            return ln
    return ""


def describe_effect(name: str, text: str) -> str:
    """Was der Befehl laut seiner Antwort bewirkt hat - in einem kurzen, zeitfreien Satz. Eine Ablehnung wegen
    fehlender Voraussetzung ist KEINE Wirkung: dann ''; sie steht in precondition_of()."""
    if WHAT_RE.search(text):
        return "unknown command"
    if _MAILBOX_PROMPT.search(text):
        return "enters the MailDrop mailbox session"
    if _BANNER_TEXT.search(text):
        return "prints banner (restart)"
    m = _OPMODE_NOW.search(text)
    if m:
        return f"changes OPMODE to {m.group(1).upper()}"
    if precondition_of(text):
        return ""
    if "cmd:" not in text:
        return _EFFECT_NO_PROMPT.get(name, "no prompt returned")
    answer = answer_to(name, text)
    return "no output" if answer is None or not answer[0].strip() else "prints a value"


def fx_text(effect: str, recovery: str, mode: str = "") -> str:
    """Wirkung und Rueckweg in Kurzform fuer die Matrix (fx_<release>); ohne Wirkung gibt es keinen Text."""
    if not effect:
        return ""
    if mode:
        effect = f"in {mode}: {effect}"
    if recovery == "needs_power_cycle":
        return f"{effect}; power-cycle needed"
    return f"{effect}; exit {recovery}" if recovery else effect


def ensure_prompt(t) -> None:
    """Ausgangszustand: 'cmd:' erreichbar - sonst aufwecken wie die App."""
    t.write(b"\r")
    if "cmd:" not in read_until(t, ("cmd:",)):
        wake(t)


def record(t, seconds: float, t0: float) -> list:
    """Alles mitschreiben, was der TNC in *seconds* sendet: [(Sekunden seit t0, Text)]."""
    out = []
    while _clock() - t0 < seconds:
        chunk = t.read_idle(0.2, 0.5)
        if chunk:
            out.append((round(_clock() - t0, 3), chunk))
    return out


def _run_step(t, step: Step, recorded_text: str) -> tuple:
    """Eine Rueckweg-Stufe ausfuehren; (hat 'cmd:' erreicht, was dabei empfangen wurde)."""
    seen = ""
    for action in step.actions:
        op = action[0]
        if op == "tx":
            t.write(action[1])
        elif op == "sleep":
            _sleep(action[1])
        elif op == "wait":
            start = _clock()
            while _clock() - start < action[1] and "cmd:" not in seen:
                seen += t.read_idle(0.2, 0.5)
        elif op == "banner":
            seen += recorded_text
            if not any(m in seen for m in _BANNER_STR):
                t.write(_WAKEUP)                  # kein Banner gekommen: '*' (Autobaud)
            seen += read_until(t, _WAKE_MARKERS, reads=3 * _STEP_READS)
    seen += read_until(t, ("cmd:",))
    return "cmd:" in seen, seen


def _value(t, name: str) -> str:
    """Eine Abfrage (OPMODE / MYCALL): die Antwort nach dem Echo, einzeilig."""
    t.write(verbose_line(name))
    resp = read_until(t, ("cmd:",))
    got = answer_to(name, resp)
    return " ".join(got[0].split()) if got else ""


@dataclass
class RiskyContext:
    """What the risky part sets before it starts and sets again after every reset (P89a)."""
    mycall: Optional[str] = None
    myselcal: Optional[str] = None
    expert: bool = False


def reestablish(t, ctx: RiskyContext) -> None:
    """After a restart / power cycle the preconditions are gone: EXPERT ON, MYCALL, MYSELCAL again."""
    if ctx.expert:
        t.write(verbose_line("EXPERT ON"))
        read_until(t, ("cmd:",))
    for name, value in (("MYCALL", ctx.mycall), ("MYSELCAL", ctx.myselcal)):
        if value:
            t.write(verbose_line(f"{name} {value}"))
            read_until(t, ("cmd:",))


def probe_risky(t, cmd: Cmd, *, mycall: Optional[str], confirm_power_cycle, record_s: float = 3.0,
                ctx: Optional[RiskyContext] = None, target: str = DEFAULT_TARGET) -> Behaviour:
    """Einen riskanten Befehl einzeln absetzen (P89 Teil B): Ausgangszustand pruefen, senden, 3 s
    alles mitschreiben, zurueck in den Befehlsmodus nach der Tabelle RECOVERY (jeder Schritt mit
    Ergebnis im Log), bei Misserfolg Aus-/Einschalten durch den Betreiber, danach OPMODE und MYCALL.

    T186: a command with NEEDS_MODE is only sent when OPMODE says the mode was really reached - otherwise it is
    not sent at all (precondition 'mode not reached', no effect, no matrix cell). ARQ / SELFEC / PTCONN get *target*."""
    ctx = ctx or RiskyContext(mycall=usable_call(mycall))
    b = Behaviour(cmd.name, cmd.kind, mode=NEEDS_MODE.get(cmd.name, ""))
    line = f"{cmd.name} {target}" if cmd.name in TARGET_CMDS else cmd.name
    _dbg_note(t, f"RISKY {cmd.name} (kind={cmd.kind}): baseline, send {line!r}, record {record_s:.0f} s"
                 f"{' in ' + b.mode if b.mode else ''}")
    if b.mode:
        enter_mode(t, b.mode)                 # P89a: this command only works in its own mode
        ensure_prompt(t)
        reached = _value(t, "OPMODE")
        if opmode_word(reached) != b.mode:
            b.precondition = f"mode not reached: wanted {b.mode}, {reached or 'no OPMODE answer'}"
            b.recovery = "not sent"
            _dbg_note(t, f"RISKY {cmd.name}: {b.precondition} - not sent")
            _status(f"    [!] {cmd.name}: {b.precondition} - the command is NOT sent")
            enter_mode(t, "PACKET")
            b.opmode = _value(t, "OPMODE")
            b.mycall = _value(t, "MYCALL")
            return b
    ensure_prompt(t)
    t0 = _clock()
    t.write(verbose_line(line))
    b.raw = record(t, record_s, t0)
    b.recorded_s = round(_clock() - t0, 3)
    text = "".join(chunk for _ts, chunk in b.raw)
    got = answer_to(line, text)
    b.exists = None if got is None else ("no" if WHAT_RE.search(got[0]) else "yes")
    b.effect = describe_effect(cmd.name, text)
    b.precondition = precondition_of(text)

    reset = recovery_kind(cmd.name, cmd.kind) == "RESTART"
    if b.exists == "no":
        b.recovery = "none needed"
    else:
        for step in RECOVERY[recovery_kind(cmd.name, cmd.kind)]:
            ok, seen = _run_step(t, step, text)
            if reset and b.exists is None and any(m in text + seen for m in _BANNER_STR):
                b.exists = "yes"                    # a restart that waited for '*': the banner is its answer
                b.effect = "prints banner (restart)"
            b.steps.append((step.label, ok))
            _dbg_note(t, f"recovery step {step.label}: {'cmd: reached' if ok else 'no prompt'}")
            if ok:
                b.recovery = step.label
                break
        else:
            b.recovery = "needs_power_cycle"
            _dbg_note(t, f"no way back for {cmd.name}: the operator power-cycles the TNC")
            power_cycle_and_check(t, f"{cmd.name}: the TNC does not come back", confirm_power_cycle)
            reset = True
    if reset:
        reestablish(t, ctx)                              # the factory values came back: set them again
    if b.mode:
        enter_mode(t, "PACKET")
    b.opmode = _value(t, "OPMODE")
    b.mycall = _value(t, "MYCALL")
    _dbg_note(t, f"RISKY {cmd.name}: exists={b.exists} effect={b.effect!r} recovery={b.recovery} "
                 f"opmode={b.opmode!r} mycall={b.mycall!r}")
    return b


def _operator_power_cycle() -> None:
    _ask("")                                              # ENTER


def value_of(text: str) -> str:
    """The value of a one-line answer: 'MYcall    PK232' -> 'PK232'."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return lines[0].split()[-1] if lines else ""


# T186/P89b: 'none' in lower case is how an UNSET MYSELCAL is DISPLAYED, it is not a value to enter - the firmware
# takes 'MYSELCAL none' as the VALID selcal NONE ('MYSelcal  was OEAS / now NONE', T186 at A and B). Hand test at
# A (07.10.2026): '%' and 'OFF' answer '?callsign', NONE -> 'now NONE': NO command clears MYSELCAL at A and B.
# An unset MYSELCAL is therefore given back by a power cycle (the factory state, checked by the banner line).
UNSET_DISPLAY = "none"          # exactly this spelling, case-sensitive ("NONE" is a selcal)


def restore_value(t, name: str, before: str) -> bool:
    """Set *name* back to what the device showed before the risky part and read it back, case-sensitive.
    True if the device shows *before* again. (An unset MYSELCAL cannot be set - see give_back_myselcal.)"""
    t.write(verbose_line(f"{name} {before}"))
    read_until(t, ("cmd:",))
    now = value_of(query_text(t, name))
    ok = now == before
    _dbg_note(t, f"restore {name}: set {before!r}; device shows {now!r}, wanted {before!r}: {'ok' if ok else 'MISMATCH'}")
    if not ok:
        _status(f"[!] {name}: the device shows {now!r}, it showed {before!r} before the scan - set it by hand")
    return ok


def give_back_myselcal(t, before: str, confirm) -> bool:
    """Put MYSELCAL back to *before*. A set value is entered; an unset one ('none') needs a power cycle, because no
    command clears it (P89b) - so the factory state is checked by the banner line and the step repeated if the TNC
    kept its settings. A power cycle also loses MYCALL: the caller sets that AFTER this."""
    if before != UNSET_DISPLAY:
        return restore_value(t, "MYSELCAL", before)
    now = value_of(query_text(t, "MYSELCAL"))
    if now == before:
        return True
    _status(f"    MYSELCAL shows {now!r}, it was unset ('none') before; no command clears it - power cycle")
    if confirm is None:
        _status("[!] MYSELCAL: not given back (the run was aborted) - switch the TNC off for a while and on again "
                "to get 'none'")
        return False
    got_factory = power_cycle_and_check(t, "MYSELCAL cannot be cleared by a command - back to 'not set'", confirm)
    now = value_of(query_text(t, "MYSELCAL"))
    ok = now == before
    _dbg_note(t, f"give back MYSELCAL by power cycle: factory banner {got_factory}; device shows {now!r}, wanted {before!r}")
    if not ok:
        _status(f"[!] MYSELCAL: the device shows {now!r}, it showed {before!r} before the scan - set it by hand "
                f"(no command clears it; switch off for longer)")
    return ok


def run_risky(t, entries: dict, *, mycall: Optional[str], confirm_power_cycle=None,
              progress: bool = True, myselcal: Optional[str] = None, expert: bool = False,
              only: Optional[set] = None, target: str = DEFAULT_TARGET) -> list:
    """Alle riskanten Befehle einzeln, vom harmlosen zum heikelsten. Rueckgabe: Report-Zeilen.

    P89a: vorher MYCALL (echtes Rufzeichen), MYSELCAL und - wenn das Geraet EXPERT kennt - EXPERT ON setzen,
    nach jedem Reset neu setzen, am Ende MYCALL und MYSELCAL auf ihre alten Werte zurueck (EXPERT, ECHO und
    Betriebsmodus stellt run_scan wieder her)."""
    confirm = confirm_power_cycle or _operator_power_cycle
    call = usable_call(mycall)
    ctx = RiskyContext(mycall=call, myselcal=usable_call(myselcal) or derive_selcal(call), expert=expert)
    if not call and progress:
        _status("[!] no usable callsign (--mycall or the configuration): the commands that need MYCALL will be "
                "refused and recorded as preconditions")
    before = {"MYCALL": value_of(query_text(t, "MYCALL")), "MYSELCAL": value_of(query_text(t, "MYSELCAL"))}
    reestablish(t, ctx)
    rows = []
    todo = risky_plan(entries, only=only)
    try:
        for i, cmd in enumerate(todo, 1):
            if progress:
                _status(f"\n[*] riskant [{i}/{len(todo)}] {cmd.name} ({cmd.kind}) ...")
            b = probe_risky(t, cmd, mycall=mycall, confirm_power_cycle=confirm, ctx=ctx, target=target)
            result = {"yes": Result.SUPPORTED, "no": Result.UNSUPPORTED}.get(b.exists, Result.ERROR).value
            if progress:
                what = b.effect or (f"precondition {b.precondition}" if b.precondition else "")
                _status(f"    -> {result}; {what}; way back: {b.recovery}")
            if opmode_word(b.opmode) not in ("PACKET", ""):
                # T186: a way back that reaches 'cmd:' but leaves the mode (FEC) spoils every command after it
                _dbg_note(t, f"{cmd.name}: still in {b.opmode!r} after the way back")
                _status(f"    [!] {cmd.name}: the TNC is still in {b.opmode!r} after the way back")
            rows.append({
                "name": cmd.name, "group": cmd.group, "kind": cmd.kind, "result": result,
                "matrix": "?", "note": "",
                "effect": b.effect, "recovery": b.recovery, "precondition": b.precondition, "mode": b.mode,
                "fx": fx_text(b.effect, b.recovery, b.mode) if result == Result.SUPPORTED.value else "",
                "raw": repr("".join(chunk for _ts, chunk in b.raw))[:600],
                "opmode": b.opmode, "mycall": b.mycall,
            })
    finally:
        ensure_prompt(t)
        # MYSELCAL first: giving back an unset one is a power cycle, which also loses MYCALL (P89b)
        if ctx.myselcal and before["MYSELCAL"]:
            # a run that is being aborted does not ask the operator for a power cycle (it only says so)
            give_back_myselcal(t, before["MYSELCAL"], None if sys.exc_info()[0] else confirm)
        if ctx.mycall and before["MYCALL"]:
            restore_value(t, "MYCALL", before["MYCALL"])               # back to what the device had
    return rows


# ----------------------------------------------------------------------------
# 5. Die Matrix aktualisieren: nur ?-Zellen, vorhandene Belege nie anfassen
# ----------------------------------------------------------------------------
def apply_to_matrix(entries: dict, rows: list, release: str, date: str, device: str,
                    source: str, evidence: Optional[str] = None) -> tuple:
    """(neue Matrix, Zahl der gefuellten Zellen, Widersprueche).

    * Zelle ``?``      -> wird mit dem Ergebnis und einem Beleg gefuellt
    * gleiche Aussage  -> bleibt, samt ihrem Beleg
    * expert <-> yes   -> KEIN Widerspruch (der Scan entsperrt EXPERT zuerst)
    * sonst            -> Widerspruch; dann wird NICHTS gefuellt (die alte Matrix kommt zurueck)
    Zeilen riskanter Befehle (P89) tragen ``fx`` (Wirkung + Rueckweg): die fx-Zelle wird nur
    gefuellt, wenn sie leer ist und die fw-Zelle gemessen ist; ein anderer Text ist ein Widerspruch.
    Gezaehlt werden Zellen (fw und fx).
    """
    columns = cm.releases_of(entries)
    if release not in columns:
        raise ValueError(f"release {release!r} is not a column of the matrix {columns}")
    evidence = evidence or (f"fw_scan {date.replace('-', '')} (device {device}, banner Release {release}; "
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
            fw[release] = value
            ev[release] = evidence + (f"; precondition: {row['precondition']}" if row.get("precondition") else "")
            new[e.name] = e = dataclasses.replace(e, fw=fw, ev=ev)
            filled += 1
        elif cell != value and {cell, value} != {"yes", "expert"}:
            conflicts.append(f"{e.name} {release}: matrix says {cell} ({e.ev[release][:70]}), "
                             f"this scan says {value}")
            continue
        effect = row.get("fx") or (fx_text(row["effect"], row.get("recovery", ""))
                                   if row.get("effect") and value != "no" else "")
        have = e.fx.get(release, "")
        if effect and not have:
            new[e.name] = dataclasses.replace(e, fx={**e.fx, release: effect})
            filled += 1
        elif effect and have != effect:
            conflicts.append(f"{e.name} {release}: effect cell says {have!r}, this scan says {effect!r}")
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
    print(f"State before : Opmode {rep.opmode_before}, ECHO {rep.echo_prior}")
    if rep.settings_after:
        if rep.state_diff:
            print("!" * 74)
            print("DEVICE STATE DIFFERS from before the scan (DISPLAY before / after):")
            for line in rep.state_diff:
                print(f"  {line}")
            print("!" * 74)
        else:
            print("Device state : restored (DISPLAY before = after)")
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


CSV_FIELDS = ["release", "device", "date", "name", "group", "kind", "result", "matrix", "note",
              "effect", "recovery", "precondition", "mode", "raw"]


def write_csv(rep: Report, path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        w.writeheader()
        for r in rep.rows:
            w.writerow({"release": rep.release or "", "device": rep.device, "date": rep.date,
                        **{k: r.get(k, "") for k in CSV_FIELDS[3:]}})


def write_json(rep: Report, path: str) -> None:
    payload = {"port": rep.port, "timestamp": rep.ts, "release": rep.release,
               "device": rep.device, "expert_prior": rep.expert_prior,
               "banner": rep.banner, "rows": rep.rows}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)


# ----------------------------------------------------------------------------
# 6a. Ergebnisordner je Geraet und ZIP zum Zurueckschicken (P90)
# ----------------------------------------------------------------------------
_SERIAL_RE = re.compile(r"(?:s/n|serial(?:\s+number)?)\W{0,3}([A-Za-z0-9][A-Za-z0-9-]{2,})", re.IGNORECASE)


def folder_name(results_dir: Path, release: Optional[str], banner_raw: str) -> str:
    """scan_<release>_<seriennr> - ohne Seriennummer im Banner scan_<release>_n<k> (k = naechste freie Zahl)."""
    rel = release or "unknown"
    m = _SERIAL_RE.search(banner_raw or "")
    if m:
        name, k = f"scan_{rel}_{m.group(1)}", 2
        while (results_dir / name).exists():
            name, k = f"scan_{rel}_{m.group(1)}-{k}", k + 1
        return name
    k = 1
    while (results_dir / f"scan_{rel}_n{k}").exists():
        k += 1
    return f"scan_{rel}_n{k}"


def write_results(rep: "Report", results_dir: Path, call: str, debug_path: Optional[str],
                  copy_debug: bool = False) -> Path:
    """Den Ergebnisordner dieses Geraets schreiben: banner.txt (woertlich), scan.csv, debug.log,
    settings_before.txt / settings_after.txt (DISPLAY) und device_info.txt (Formular)."""
    results_dir.mkdir(parents=True, exist_ok=True)
    name = folder_name(results_dir, rep.release, rep.banner_raw)
    folder = results_dir / name
    folder.mkdir()
    (folder / "banner.txt").write_bytes(rep.banner_raw.encode("latin-1", errors="replace"))
    write_csv(rep, str(folder / "scan.csv"))
    (folder / "settings_before.txt").write_text(rep.settings_before, encoding="latin-1", errors="replace", newline="")
    (folder / "settings_after.txt").write_text(rep.settings_after, encoding="latin-1", errors="replace", newline="")
    if rep.state_diff:
        (folder / "settings_diff.txt").write_text("\n".join(rep.state_diff) + "\n", encoding="utf-8")
    serial = name.split("_", 2)[2]
    (folder / "device_info.txt").write_text(
        DEVICE_INFO_TEMPLATE.format(release=rep.release or "?", call=call, date=rep.date, serial=serial),
        encoding="utf-8")
    if debug_path and Path(debug_path).exists():
        (shutil.copyfile if copy_debug else shutil.move)(str(debug_path), str(folder / "debug.log"))
    return folder


def build_results_zip(results_dir: Path, call: str, date: str) -> Path:
    """results_<call>_<date>.zip mit ALLEN scan_*-Ordnern des Ergebnisverzeichnisses."""
    zpath = results_dir / f"results_{call}_{date}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for folder in sorted(p for p in results_dir.iterdir() if p.is_dir() and p.name.startswith("scan_")):
            for f in sorted(folder.iterdir()):
                z.write(f, f"{folder.name}/{f.name}")
    return zpath


def print_plan(immediate: bool = False, all_commands: bool = False) -> None:
    """Was dieses Werkzeug abfragen wuerde und was es NIE sendet (kein Geraet noetig)."""
    if all_commands:
        immediate = True
    todo = plan(immediate=immediate)
    print(f"# Would probe {len(todo)} commands"
          f"{' (incl. immediate commands)' if immediate else ' (parameters only; --immediate adds the immediate ones)'}")
    for group in GROUP_ORDER:
        names = [c.name for c in todo if c.group == group]
        if names:
            mode = MODE_ENTRY.get(group)
            print(f"\n[{group}]{' after ' + mode if mode else ''}: {' '.join(names)}")
    if all_commands:
        risky = risky_plan()
        print(f"\n# --all: {len(risky)} risky commands, one by one after the queries above, "
              f"from the harmless to the most delicate (way back in brackets)")
        print(' '.join(f"{c.name}[{'/'.join(st.label for st in RECOVERY[recovery_kind(c.name, c.kind)])}]"
                       for c in risky))
        return
    never = never_probed()
    print(f"\n# Never sent ({len(never)}): kind danger / action_tx / mode, and NEVER_AUTO = "
          f"{', '.join(sorted(NEVER_AUTO))}")
    print(' '.join(f"{n}[{why}]" for n, why in never))


# ----------------------------------------------------------------------------
# 7. main
# ----------------------------------------------------------------------------
_SELFTEST_RELEASE = {"1988": "30.DEC.88", "1991": "01.AUG.91", "1995": "13.SEP.95"}


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
    ap.add_argument("--all", action="store_true",
                    help="P89: probe EVERY command, also mode / action_tx / danger ones (TRANS, CALIBRATE, "
                         "RESTART, XMIT ...), one by one after the normal queries, with the way back and the "
                         "effect noted. ONLY at a TNC with no radio connected, with you at it: two "
                         "confirmations are required (exit code 5 without them)")
    ap.add_argument("--mycall", help="callsign MYCALL is set to during the risky part of --all (the factory MYCALL "
                                      "PK232 counts as 'not set': the TNC refuses CONVERSE, ID, TRANS ...); "
                                      "default: the configuration's MYCALL. Put back afterwards")
    ap.add_argument("--myselcal", help="4-letter AMTOR SELCAL for the risky part (default: derived from the "
                                        "callsign, OE3GAS -> OEAS). Put back afterwards")
    ap.add_argument("--target", default=DEFAULT_TARGET, metavar="CALL",
                    help="dummy station for the calling commands of --all (ARQ, SELFEC, PTCONN answer ?callsign "
                         f"without one); default {DEFAULT_TARGET}. Nothing answers - there is no radio")
    ap.add_argument("--only", metavar="NAME,...",
                    help="probe just these commands (a risky one needs --all); everything else is skipped")
    ap.add_argument("--results", metavar="DIR",
                    help="P90: one result folder per device (banner, csv, debug log, DISPLAY before/after, "
                         "device_info form) in DIR and results_<call>_<date>.zip; needs --call "
                         "(the scan kit always writes to ./scan_results)")
    ap.add_argument("--call", help="your callsign (named in the results zip and as the source of the data)")
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
        print_plan(args.immediate, args.all)
        return 0
    if args.update_matrix and _KIT:
        print("--update-matrix does not exist in the scan kit: send the results zip back instead.",
              file=sys.stderr)
        return 2
    if args.update_matrix and args.selftest:
        print("--update-matrix is refused with --selftest: the mock's answers are invented and "
              "must never enter the matrix.", file=sys.stderr)
        return 2
    only = None
    if args.only:
        only = {n.strip().upper() for n in args.only.split(",") if n.strip()}
        known = cm.all_entries()
        unknown = sorted(n for n in only if n not in known)
        if unknown:
            print(f"--only: not a command of the matrix: {', '.join(unknown)}", file=sys.stderr)
            return 2
        risky_names = sorted(only & {n for n, _why in never_probed()})
        if risky_names and not args.all:
            print(f"--only names risky commands ({', '.join(risky_names)}): that needs --all", file=sys.stderr)
            return 2
    args.only_set = only
    results_dir = Path(args.results or ("scan_results" if _KIT else "")) if (args.results or _KIT) else None
    if results_dir is not None and not args.call:
        print("--call CALLSIGN is required with --results (it names the results zip and the source "
              "of the data).", file=sys.stderr)
        return 2

    debug_path = args.debug
    temp_log = None
    if results_dir is not None and not debug_path:
        results_dir.mkdir(parents=True, exist_ok=True)
        debug_path = temp_log = str(results_dir / f"_running_{os.getpid()}.log")
    dbg = DebugLog(debug_path) if debug_path else None
    if dbg:
        _status(f"[*] Debug-Log: {dbg.path}")
    reports: list = []
    try:
        rc = _run(args, ap, dbg, reports)
    finally:
        if dbg:
            dbg.close()             # vollstaendig schreiben, auch bei Fehler / Strg-C (T179)
            _status(f"[*] Debug-Log geschrieben: {dbg.path}")
    if results_dir is not None:
        if reports:
            folder = write_results(reports[0], results_dir, args.call, debug_path, copy_debug=temp_log is None)
            zpath = build_results_zip(results_dir, args.call, reports[0].date)
            print(f"[+] results: {folder}\n[+] zip: {zpath}  (send this file back)")
        elif temp_log and Path(temp_log).exists():
            Path(temp_log).unlink()          # nothing was scanned: no half-written log is left behind
    return rc


def _config_mycall() -> Optional[str]:
    """MYCALL of the configuration (what the app uploads), None if there is none."""
    try:
        import importlib
        mgr = importlib.import_module("pk232py.config").ConfigManager()    # not there in the scan kit
        mgr.load()
        return mgr.app.hf_packet.mycall
    except Exception:
        return None


def _run(args, ap, dbg, reports: Optional[list] = None) -> int:
    global _clock, _sleep
    if args.all and not args.selftest and not operator_checks():
        # before anything is opened or sent: P89 Teil A, not switchable
        print("--all needs both confirmations (no radio connected to the TNC; you are at the TNC and can "
              "power-cycle it). Nothing was sent.", file=sys.stderr)
        return 5
    saved_hooks = (_clock, _sleep)
    confirm = None
    if args.selftest:
        if args.selftest not in _SELFTEST_RELEASE:
            print("selftest year must be one of 1988 / 1991 / 1995", file=sys.stderr)
            return 2
        sim = SimulatedClock()                      # the mock needs no real 65 s
        _clock, _sleep = sim, sim.advance
        t = MockTransport(_SELFTEST_RELEASE[args.selftest], debug=dbg, clock=sim, risky=args.all)
        confirm = t.power_cycle
        port = f"MOCK:{args.selftest}"
    else:
        if not args.port:
            ap.error("--port is required (or use --selftest / --plan)")
        _status(f"[*] Oeffne {args.port} @ {args.baud} Baud 8N1 ...")
        t = SerialTransport(args.port, args.baud, debug=dbg)
        port = args.port
        _status(f"[*] {args.port} offen. Starte Scan (Abbruch mit Strg-C) ...")

    try:
        rep = run_scan(t, port, only_group=args.group, immediate=args.immediate or args.all,
                       risky=args.all, mycall=args.mycall or _config_mycall(),
                       confirm_power_cycle=confirm, myselcal=args.myselcal, only=args.only_set,
                       target=args.target)
    except ScanError as exc:
        print(f"[!] {exc}", file=sys.stderr)
        return 4
    finally:
        t.close()
        _clock, _sleep = saved_hooks

    if reports is not None:
        reports.append(rep)
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
