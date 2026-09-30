#!/usr/bin/env python3
# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS - GPL v2
#
# This is a DEV-ONLY hardware verification tool. It is never shipped with
# the application. GPL v2, same as the rest of tools/ (see tools/README.md).
"""hw_check.py - solo hardware checks for a real PK-232MBX (P14/P17/P20).

Checks an operator can run alone, with the real TNC, no second station
required except for T101:

    t17     Is PASSALL the Host Mode mnemonic PS or PX? (query only)
    t103    Does USERS actually reach the TNC via ParamsUploader? (query +
            a real upload + query)
    pthuff  How does the TNC respond to what the uploader sends for
            PTHUFF (a bool ON/OFF, though the field is documented as a
            0-10 level)? (query + set + query)
    t101    Does data sent on the unconnected channel 0 go out as a UI
            frame along the UNPROTO path? TRANSMITS ON THE AIR - needs a
            second receiver with an AX.25 decoder (Direwolf, multimon-ng,
            ...) tuned to the TNC's frequency.
    siam    Receive-only, 60s (default) unfiltered capture of every Host
            Mode frame the TNC sends after SignalMode's real activation
            frames go out. No filtering, no assumption about frame type or
            output format (see docs/P17_HW_Measure_Spec.md - the module
            docstring and handle_frame() disagree on both). Needs a
            receiver tuned to a KNOWN FSK signal beforehand.
    t111    Does PX toggle PASSALL while PS (PASS) stays untouched? Sends
            the same mnemonic as the app's PASSALL button (P17.2).
    t112    Does a VHF Packet -> HF Packet switch leave MAXFRAME/SLOTTIME
            at HF Packet's own values, or at VHF's? Pre-sets both to a
            neutral value (neither HF's nor VHF's own) so each is judged
            separately, then replays the real frames _on_mode_selected()
            sends, in the same order.
    mi      Does the app's MailDrop button (mnemonic MI) actually query
            MFILTER instead? Host Mode query only, no writes.
    maildrop
            Guided, mitschreib-style local MailDrop terminal (verbose
            mode, serial only - never transmits on the air). The real
            mailbox command set/prompts/message-end sequence are NOT
            known in advance; this records every byte in both directions
            while the operator drives an interactive md> prompt. See
            docs/P20_MailDrop_Measure_Spec.md and docs/HW_Solo_Tests.md.
    maildrop_host
            Read-only probe of MailDrop over Host Mode (the CTL $60/$70
            data channel the TRM's HOST command bit 1 documents - pk232py
            already runs with this bit set via 'HOST 3', but nothing in
            the app uses it). Creates one test message over the known-
            safe verbose path first, then sends only L/MDCHECK/R as raw
            $60 frames and logs every frame that comes back, unfiltered.
            No write/kill mailbox commands, no transmission. See
            docs/P24_MailDrop_HostMode_Spec.md.
    mdcheck_scan
            Read-only search for the Host Mode mnemonic MDCHECK actually
            uses (P26.2) - the TRM's own 'MI' entry for it contradicts the
            hardware-confirmed 'MI' = MFILTER (T115), so the real mnemonic
            is unknown and this finds it by measurement instead of
            guessing. Creates one test message over the verbose path
            (like maildrop_host), then queries every 'M?' mnemonic (A-Z)
            except the denylisted MO/MI/MM, stopping at the first response
            that contains the mailbox prompt text. Query-only - no
            candidate writes, kills, or transmits. See
            docs/P26_MDCHECK_Mnemonic_Spec.md.
    maildrop_session
            Drives the real pk232py.maildrop.MailDropSession against
            hardware for T119 (P28) - a harness, not a second protocol
            implementation: it only calls open()/list()/send()/read()/
            kill()/leave() and logs the signals they fire. Runs the full
            open -> list -> send (personal/foreign-FROM/bulletin) -> list
            -> read -> kill -> list -> leave sequence, then confirms Host
            Mode is active again with an HPOLL query. --abort-test adds an
            extra probe: reopen, start a send(), abort() it right after
            the subject is accepted, confirm the recovery path runs and
            reports failure, never success. See
            docs/P28_MailDrop_Session_Harness_Spec.md.
    aprs_query
            Query-only measurement for the future APRS mode (P62/P63) -
            UNPROTO with a VIA digipeater path, verbose AND via the
            Host Mode 'UN' frame (HostModeProtocol.cmd_unproto(), never
            called anywhere in production code), CFROM via the Host
            Mode 'CF' frame, and a verbose 8-/9-digipeater UNPROTO
            length probe. No transmission at all. See
            docs/P62_APRS_Measure_Spec.md.
    aprs_tx TRANSMITS ON THE AIR - five UI-frame rounds on the
            unconnected channel 0 (plain, a VIA path, a full-ASCII-
            charset probe, a 200-character length probe, and one with
            CFROM NONE active), each needs a second receiver with an
            AX.25 decoder (Direwolf or similar) and the operator to
            paste back what it showed. See docs/P62_APRS_Measure_Spec.md.
    aprs_reject
            Records this TNC's own Host Mode frames while a SECOND
            station (of the operator's choosing) tries to connect,
            first with CFROM ALL (baseline) then CFROM NONE - no
            transmission of this tool's own. INFO only, no PASS/FAIL:
            the question is what CFROM NONE actually does, not a
            predicted answer. See docs/P62_APRS_Measure_Spec.md.
    link_carry
            Does a verbose-mode AX.25 Packet connection, and Packet as
            the active operating mode, survive a verbose -> Host Mode
            -> verbose round trip (P64/P65, T141)? Connects from THIS
            program's own verbose CONNECT prompt, queries OPMODE
            (Host Mode 'OP') and TRM 4.3.3 link status on every channel
            (HostModeProtocol.cmd_link_status(), never called by
            production code) before and after re-sending VHFPacketMode's
            own activate+init frames, then checks the connection is
            still visible in verbose OPMODE/CSTATUS/CONNECT. Needs a
            real counterpart station (a BBS, or Direwolf/QtTermTCP over
            AGW as in aprs_reject). See
            docs/P65_Link_Carryover_Measure_Spec.md.
    link_carry_host
            Mirror image of link_carry: connects IN Host Mode
            (HostModeProtocol.cmd_connect(), channel 1, the same call
            production code makes), waits for the '$5x' CONNECTED link
            message, then leaves Host Mode and checks whether verbose
            OPMODE/CSTATUS/CONNECT shows the same connection on the
            same channel. Needs a real counterpart station. See
            docs/P65_Link_Carryover_Measure_Spec.md.
    channel_probe
            P69 (T146/T147): does the TNC send Unproto data on a FREE
            channel other than 0 (3, 9 - also while another channel is
            connected) as a UI frame, and on which channel does an
            INCOMING connect land (USERS as found, then USERS 10)?
            Transmits and needs Direwolf (all frames, incl. I-frames)
            plus a QtTermTCP caller; every transmission sits behind
            confirm_tx(). MEASURES ONLY - P70 (channel bar MON + 0-9)
            builds on it. Not part of 'all'. See
            docs/P69_Channel_Probe_Measure_Spec.md.
    all     t17 + t103 + pthuff. Deliberately NOT t101 (it transmits and
            needs a second receiver), NOT siam/t111/t112 (siam needs a
            tuned receiver and an operator comparison; t111/t112 are run
            and recorded individually), and NOT
            mi/maildrop/maildrop_host/mdcheck_scan/maildrop_session/
            aprs_query/aprs_tx/aprs_reject/link_carry/link_carry_host/
            channel_probe
            (mi is fine alone but grouped with its guided counterpart;
            maildrop, maildrop_host, mdcheck_scan and maildrop_session
            are interactive/exploratory; aprs_tx/aprs_reject/
            link_carry/link_carry_host transmit or need a second
            station), so each must be run on its own.

Usage::

    python tools/hw_check.py --port COM3 t17
    python tools/hw_check.py --port COM3 all
    python tools/hw_check.py --port COM3 t101
    python tools/hw_check.py --port COM6 siam
    python tools/hw_check.py --port COM6 siam --seconds 120
    python tools/hw_check.py --port COM6 t111
    python tools/hw_check.py --port COM6 t112
    python tools/hw_check.py --port COM6 mi
    python tools/hw_check.py --port COM6 maildrop
    python tools/hw_check.py --port COM6 maildrop_host
    python tools/hw_check.py --port COM6 mdcheck_scan
    python tools/hw_check.py --dry-run mdcheck_scan
    python tools/hw_check.py --port COM6 maildrop_session
    python tools/hw_check.py --port COM6 maildrop_session --abort-test
    python tools/hw_check.py --dry-run maildrop_session
    python tools/hw_check.py --port COM6 aprs_query
    python tools/hw_check.py --port COM6 aprs_tx
    python tools/hw_check.py --port COM6 aprs_reject
    python tools/hw_check.py --dry-run aprs_query
    python tools/hw_check.py --dry-run all      # no port opened at all

------------------------------------------------------------------------------
Hard rules this tool follows (P14_HW_Solo_Check_Spec.md)
------------------------------------------------------------------------------
1. Reuses pk232py.comm (SerialManager, frame builders, ParamsUploader) for
   every byte sent or read. No second serial implementation - the Host
   Mode entry/exit quirks are hard-won and documented in CLAUDE.md; this
   tool does not reinvent them.
2. Every parameter a test changes is queried first and restored afterwards,
   in a try/finally, so it survives an exception or Ctrl-C mid-test.
3. No transmission without an explicit y/N confirmation (default No) naming
   the frequency/mode/text about to go out. Only T101 transmits; T17/T103/
   PTHUFF never key the TNC's transmitter.
4. --dry-run prints exactly what each test would send and never opens the
   port.
5. The application (pk232py itself) must not be connected to the same port
   at the same time - the COM port is exclusive. A failed port open prints
   a plain "Port busy" message, not a traceback.
6. This tool MEASURES; it does not correct the application. Findings go
   into Testplan.md / Backlog.md. Fixing main-line code based on a finding
   is a separate, later change.
7. SAFETY (P21.3): an interactive phase running inside a TNC sub-state
   (currently: MailDrop) stops the INSTANT the TNC reports its top-level
   'cmd:' prompt again, before reading or sending anything else. Found
   necessary 22.09.2026: after 'B' silently closed the mailbox, further
   typed input kept going to the TNC's own command interpreter, where
   single letters mean something else entirely ('K' = CONVERSE) - with
   MYCALL set and XMITOK ON, that would have transmitted on the air.
   See run_maildrop_interactive().

Log files land in hw_logs/YYYYMMDD_HHMMSS_<test>.log (gitignored - the
summary printed at the end of each run is what gets copied into
Testplan.md; the raw per-byte log stays local).
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime
import logging
import re
import select
import sys
import time
from pathlib import Path
from typing import Callable, Optional

try:
    import msvcrt  # Windows: non-blocking key check for wait_for_enter()
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None

import serial  # only for the maildrop_session port-factory injection (P30.2)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from PyQt6.QtCore import QCoreApplication, QObject, QTimer, pyqtSignal  # noqa: E402

from pk232py.comm.serial_manager import SerialManager  # noqa: E402
from pk232py.comm.pk232_hostmode_sub import escape_converse  # noqa: E402
from pk232py.comm.link_status import (  # noqa: E402
    LinkStatus, decode_link_status, parse_cstatus, split_channel_prefix,
)
from pk232py.comm.params_uploader import ParamsUploader  # noqa: E402
from pk232py.comm.frame import build_command, _dle_escape  # noqa: E402
from pk232py.comm.hostmode import HostModeProtocol  # noqa: E402
from pk232py.comm.constants import SOH, ETB  # noqa: E402
from pk232py.config import AppConfig, ConfigManager  # noqa: E402
from pk232py.maildrop import MailDropSession, SerialManagerChannel  # noqa: E402
from pk232py.maildrop.protocol import find_prompt  # noqa: E402
from pk232py.modes.signal_analysis import SignalMode  # noqa: E402
from pk232py.modes.packet_hf import HFPacketMode  # noqa: E402
from pk232py.modes.packet_vhf import VHFPacketMode  # noqa: E402
from pk232py.ui.screens.signal_screen import KNOWN_MODES  # noqa: E402


class HWCheckError(RuntimeError):
    """Raised for anything that stops a test/run from continuing."""


# ===========================================================================
# Logging - console + one log file per run
# ===========================================================================

class RunLog:
    """Timestamped console + file log, plus a PASS/FAIL/INFO tally for the
    end-of-run summary that gets copied into Testplan.md by hand."""

    def __init__(self, path: Optional[Path]):
        self._fh = open(path, "w", encoding="utf-8") if path else None
        self.findings: list[tuple[str, str, str]] = []
        # P37: set by Session.connect() once the banner is known (or
        # known absent) -- repeated as the first line of summary() too,
        # so device provenance survives a "just read the tail" skim.
        self.device_line: Optional[str] = None

    def line(self, text: str = "") -> None:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        msg = f"[{ts}] {text}" if text else ""
        print(msg)
        if self._fh:
            self._fh.write(msg + "\n")
            self._fh.flush()

    def result(self, label: str, verdict: str, detail: str = "") -> None:
        tail = f" -- {detail}" if detail else ""
        self.line(f"{verdict}: {label}{tail}")
        self.findings.append((label, verdict, detail))

    def summary(self) -> None:
        self.line()
        self.line("=== SUMMARY (copy into Testplan.md) ===")
        if self.device_line:
            self.line(self.device_line)
        if not self.findings:
            self.line("(nothing recorded)")
        for label, verdict, detail in self.findings:
            tail = f"  ({detail})" if detail else ""
            self.line(f"{verdict:12s} {label}{tail}")

    def close(self) -> None:
        if self._fh:
            self._fh.close()


# ===========================================================================
# Pure logic - unit-testable without any serial interface at all
# ===========================================================================

def format_device_line(
    release: Optional[str], pactor: bool, defaults: Optional[bool],
) -> str:
    """P37: the 'device: ...' line every hw_check log opens with (once
    the banner is known) and every summary() repeats, built from
    SerialManager's banner-derived tnc_release/has_pactor/tnc_defaults.

    release is None only when no banner was captured at all - the TNC
    was already at the cmd: prompt when this session connected. That is
    the ONLY case reported as 'unknown': nothing here guesses a device
    identity from anything but the banner itself.
    """
    if release is None:
        return "device: unknown (no banner - TNC was already awake)"
    return (
        f"device: release={release}  pactor={'yes' if pactor else 'no'}  "
        f"defaults={'yes' if defaults else 'no'}  (source: banner)"
    )

def evaluate_t17(px_response: str, ps_response: str) -> dict:
    """Classify the PX/PS query responses (T17).

    TRM mnemonic table (4.2.2): PS = PASS, a masking CHARACTER (default
    $16, Ctrl-V) - not a toggle. PX = PASSALL, a Y/N toggle. Hardware-
    confirmed 21.09.2026 (Testplan T86): raw Host Mode responses 'PXN'
    (PX) and 'PS$16' (PS) - the app's PASSALL toggle sends 'PX'. This
    function only classifies which response LOOKS like a Y/N toggle - it
    does not assume which one is right, so a future firmware surprise
    would still show up as a real INCONCLUSIVE/mismatch, not a silent miss.
    """
    def looks_like_toggle(resp: str) -> bool:
        body = resp.upper()
        has_yn = ("Y" in body) or ("N" in body)
        has_other_digit_or_hex = any(
            c.isdigit() or c == "$" for c in body
        )
        return has_yn and not has_other_digit_or_hex

    px_is_toggle = looks_like_toggle(px_response)
    ps_is_toggle = looks_like_toggle(ps_response)

    if px_is_toggle and not ps_is_toggle:
        passall_mnemonic = "PX"
    elif ps_is_toggle and not px_is_toggle:
        passall_mnemonic = "PS"
    else:
        passall_mnemonic = None

    return {
        "px_response": px_response,
        "ps_response": ps_response,
        "px_is_toggle": px_is_toggle,
        "ps_is_toggle": ps_is_toggle,
        "passall_mnemonic": passall_mnemonic,
    }


def select_response_frame(mnemonic: bytes, frames: list) -> Optional[object]:
    """Return the first captured Host Mode frame whose payload actually
    starts with *mnemonic*, ignoring every other frame seen in the same
    window (P16.2).

    Host Mode responses must never be matched by arrival order - a stale
    'HP\\x00' poll-ack from Host Mode entry can still be in flight when the
    first real query goes out (hardware-observed 21.09.2026, T86) and was
    mistaken for the answer to that query, turning a clean PASS into an
    INCONCLUSIVE. Frames are plain HostFrame-like objects with a `.data`
    attribute, so this needs no serial interface and is unit-testable with
    the real captured bytes.
    """
    for f in frames:
        if f.data.startswith(mnemonic):
            return f
    return None


_EXPLANATION_RE = re.compile(r"\s*\([^()]*\)\s*$")


def parse_query_value(command: str, response: str) -> Optional[str]:
    """Extract the value from a real PK-232 verbose-mode response.

    Real shape, confirmed against the TNC on 21.09.2026 (hw_logs/):
        query   '<ECHO>\\r\\n<Name>   <Value>[ (<note>)]\\r\\ncmd:'
        set     '<ECHO>\\r\\n<Name>   was <old>\\r\\n<Name>   now <new>\\r\\ncmd:'
        error   any line starting with '?' ('?What?', '?bad', '?callsign')

    Examples (command -> response -> result), all from the 21.09.2026 log::
        'USERS'   'USERS\\r\\nUSers     1\\r\\ncmd:'                    -> '1'
        'PTHUFF'  'PTHUFF\\r\\nPTHuff    0\\r\\ncmd:'                   -> '0'
        'UNPROTO' 'UNPROTO\\r\\nUnproto   CQ\\r\\ncmd:'                 -> 'CQ'
        'MONITOR' 'MONITOR\\r\\nMonitor   6 (seq, P/F + all)\\r\\ncmd:' -> '6'
        'TXDELAY' 'TXDELAY\\r\\nTXdelay   30 (300 msec.)\\r\\ncmd:'     -> '30'
        'CANLINE' 'CANLINE\\r\\nCANline   $18 (CTRL-X)\\r\\ncmd:'       -> '$18'

    Finds the value line BY CONTENT, never by position (P21.1, the
    verbose-mode counterpart of the Host Mode T86 rule: never correlate
    a response by arrival order/position, always by what it actually
    says). A genuine TNC response line names the parameter in the TNC's
    own mixed-case abbreviated form ('USers', 'MAildrop', 'XMITOk') - a
    PREFIX of the command word, but never in the exact (uppercase) case
    this tool sent it in. Every other line is ignored: the echo of the
    command we sent, a stray leftover fragment from a prior truncated
    response ('d:\\' - the tail end of an earlier 'cmd:'), an error line,
    or an unrelated line entirely (e.g. an asynchronous SIAM result
    interleaved mid-response while SIAM keeps analysing in the
    background, P21 22.09.2026 finding - SIAM does not stop until a
    different mode is selected).

    Returns None for an error response (see query_error() for its text),
    an empty/unrecognised response, or a genuinely multi-line value (e.g.
    MTEXT's two-line welcome message) - returning a truncated value there
    would be worse than skipping the test (P15.1).
    """
    if not response:
        return None
    lines = [ln.strip() for ln in response.splitlines() if ln.strip()]
    if not lines:
        return None

    cmd_word = command.strip().split()[0].upper()
    now_value: Optional[str] = None
    plain_values: list[str] = []
    for line in lines:
        if line.lower() == "cmd:" or line.startswith("?"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        name = parts[0]
        if not cmd_word.startswith(name.upper()) or name == cmd_word:
            # Either unrelated to this command entirely, or the exact
            # (uppercase) echo of what we sent - not the TNC's own
            # mixed-case rendering of it.
            continue
        keyword_and_rest = parts[1:]
        keyword = keyword_and_rest[0].lower()
        if keyword == "now":
            now_value = " ".join(keyword_and_rest[1:])
        elif keyword == "was":
            continue
        else:
            plain_values.append(" ".join(keyword_and_rest))

    if now_value is not None:
        return _EXPLANATION_RE.sub("", now_value).strip()
    if len(plain_values) == 1:
        return _EXPLANATION_RE.sub("", plain_values[0]).strip()
    # Zero or more-than-one plain value line: nothing to parse, or a
    # multi-line value (MTEXT) we do not attempt to reconstruct.
    return None


def chswitch_byte(value: Optional[str]) -> Optional[bytes]:
    """Decode a verbose CHSWITCH query's value - parse_query_value()'s
    own '$xx' hex text (e.g. CANLINE's 'CANline   $18 (CTRL-X)' ->
    '$18', confirmed shape) - into the actual byte the TNC expects on
    the wire: '$7C' -> b'|'. P66a, B.1: the pre-fix code sent the
    THREE CHARACTERS '$', '7', 'C' instead - `chswitch_char.encode() +
    b"1CONVERSE"` looked plausible but was never a valid channel-switch
    command, so D.2.3 measured a broken tool, not the TNC.

    '$00' means the channel-switch character is not set at all - no
    verbose channel switch by character is possible then, so this
    returns None rather than a guessed byte (chr(0) is not "no
    character"). Anything that is not exactly a two-hex-digit '$xx'
    value (including an unanswered query, *value* is None) is
    likewise None - never guessed."""
    if value is None:
        return None
    value = value.strip()
    if not (value.startswith("$") and len(value) == 3):
        return None
    try:
        n = int(value[1:], 16)
    except ValueError:
        return None
    if n == 0:
        return None
    return bytes([n])


def query_error(response: str) -> Optional[str]:
    """Return the TNC's error text ('?What?', '?bad', '?EXPERT command',
    ...) if *response* contains one, else None (P21.1). Verbose-side
    counterpart of scan_for_tnc_errors() for callers that want just the
    first error's text rather than the whole list - e.g. to tell a
    genuinely unsupported command (KILONFWD -> '?EXPERT command',
    22.09.2026) apart from a response parse_query_value() simply could
    not make sense of."""
    if not response:
        return None
    for line in response.splitlines():
        stripped = line.strip()
        if stripped.startswith("?"):
            return stripped
    return None


def host_query_value(frame: Optional[object], mnemonic: bytes) -> Optional[str]:
    """Strip the mnemonic echo from a Host Mode query response's text
    (P17.2), e.g. a frame with ``data=b'PXN'`` for mnemonic ``b'PX'`` ->
    ``'N'``, or ``data=b'PS$16'`` for ``b'PS'`` -> ``'$16'`` (the exact
    T86 hardware shapes). Falls back to the frame's full text if it does
    not start with the mnemonic - better to hand back something to log
    than raise on an unexpected reply. Returns None for no frame."""
    if frame is None:
        return None
    prefix = mnemonic.decode("ascii")
    text = frame.text
    return text[len(prefix):] if text.startswith(prefix) else text


_PASSALL_TOGGLE_RE = re.compile(
    r"\(\s*screen\.btn_passall\s*,\s*b'([A-Za-z]{2})'\s*\)"
)

# The mnemonic t111 sends to toggle PASSALL - must always equal whatever
# main_window.py's packet toggle_map actually wires to btn_passall, or the
# tool measures a different command than the one the app sends (P17.2).
# TestT111Mnemonic in test_hw_check.py enforces this against the real
# source file.
PASSALL_TOGGLE_MNEMONIC = b'PX'


def extract_passall_toggle_mnemonic(main_window_source: str) -> Optional[str]:
    """Pull the ``(screen.btn_passall, b'XX')`` mnemonic out of
    main_window.py's packet toggle_map SOURCE TEXT (P17.2) - reading the
    file as text rather than importing main_window.py, which would pull
    the entire PyQt6 widget tree in just to compare two bytes literals.
    Returns None if the tuple is not found (source reshaped)."""
    m = _PASSALL_TOGGLE_RE.search(main_window_source)
    return m.group(1) if m else None


def looks_like_siam_result(text: str, known_modes: Optional[list[str]] = None) -> bool:
    """Classify one captured frame's text as "looks like a SIAM analysis
    result" (P17.1) - a loose heuristic, not a decision: the module
    docstring (STABO manual) and the mockup screen disagree on the exact
    output shape (``'BAUDOT 45 170'`` vs. ``'0.47: 50 Baud, Baudot, RXREV
    OFF'``), so this only flags candidates for the operator to compare
    against the known signal, matching either "Baud" (covers "BAUDOT" too -
    it contains "baud" as a substring) or one of the mode names the mockup
    already lists (KNOWN_MODES in ui/screens/signal_screen.py)."""
    if known_modes is None:
        known_modes = KNOWN_MODES
    lower = text.lower()
    if "baud" in lower:
        return True
    return any(mode.lower() in lower for mode in known_modes)


def summarize_siam_frames(frames: list) -> dict:
    """Pure summary of a SIAM capture window (P17.1): a count per
    FrameKind, plus every frame that looks_like_siam_result(). No other
    filtering - this is a measurement, not a decision, see
    docs/P17_HW_Measure_Spec.md."""
    counts: dict[str, int] = {}
    candidates: list = []
    for f in frames:
        counts[f.kind.name] = counts.get(f.kind.name, 0) + 1
        if looks_like_siam_result(f.text):
            candidates.append(f)
    return {"counts": counts, "candidates": candidates}


_VHF_MAXFRAME = "4"
_VHF_SLOTTIME = "10"

# Neither of these matches HF Packet's own defaults (1/30) nor VHF's
# hardcoded values (4/10) - t112 pre-sets MAXFRAME/SLOTTIME to these
# before the switch (P18.3), so each parameter's result is meaningful on
# its own. The first hardware run's MAXFRAME result proved nothing: it
# already happened to equal VHF's value (4) before the test even started.
_T112_NEUTRAL_MAXFRAME = "2"
_T112_NEUTRAL_SLOTTIME = "20"


def evaluate_t112_param(
    value_after: Optional[str], hf_value: str, vhf_value: str
) -> str:
    """Judge ONE parameter (MAXFRAME or SLOTTIME) after t112's VHF -> HF
    Packet switch (P18.3, docs/P18_HF_Init_SIAM_Spec.md): starting from a
    neutral pre-set value that matches NEITHER HF's nor VHF's own value
    (see _T112_NEUTRAL_MAXFRAME/_T112_NEUTRAL_SLOTTIME) makes each of the
    two possible causes visible on its own, instead of a combined verdict
    hiding one parameter's result behind the other's."""
    if value_after is None:
        return "INCONCLUSIVE"
    if value_after == hf_value:
        return "PASS"
    if value_after == vhf_value:
        return "FAIL"
    return "INCONCLUSIVE"


def build_t112_frame_sequence(
    hf_maxframe: int = 1, hf_slottime: int = 30
) -> list[bytes]:
    """The exact frame sequence _on_mode_selected() (main_window.py) sends
    for a VHF Packet -> HF Packet switch, built from the REAL mode classes,
    never hand-reconstructed (P17.3): VHF's activate + init frames, then
    VHFPacketMode.vhf_off_frame() (T51, leaving VHF), then HF Packet's
    activate + init frames -- HF Packet's MX/SL now carry *hf_maxframe*/
    *hf_slottime* (P18.1/P18.3), the same values main_window.py passes to
    HFPacketMode when the app itself switches to HF Packet, so replaying
    this sequence measures what the app actually sends, not just the
    class defaults. TestT112FrameSequence in test_hw_check.py pins this
    order against the mode classes directly."""
    vhf = VHFPacketMode()
    hf = HFPacketMode(maxframe=hf_maxframe, slottime=hf_slottime)
    return (
        vhf.get_activate_frames()
        + vhf.get_init_frames()
        + [VHFPacketMode.vhf_off_frame()]
        + hf.get_activate_frames()
        + hf.get_init_frames()
    )


# ---------------------------------------------------------------------------
# P20 Teil C -- MI probe (does the MailDrop button actually send MFILTER?)
# ---------------------------------------------------------------------------

# The mnemonic probed to confirm T115's MI = MFILTER finding (P20 Teil C).
# Used to cross-check against the app's own MailDrop button before P39 -
# that button sent build_command(b'MI') as its (wrong) idea of a MailDrop
# login. P39 replaced the button with a real dialog that sends no Host
# Mode frame of its own at all ("P21.5 (Knopf sendete MI) ist damit
# abgeloest: kein Frame mehr, sondern ein Dialog"), so there is no longer
# a button-sent mnemonic to cross-check this probe against - the finding
# T115 already confirmed (MI = MFILTER) stands regardless.
MI_PROBE_MNEMONIC = b'MI'


def evaluate_mi_probe(
    mi_value: Optional[str], mfilter_value: Optional[str]
) -> str:
    """P20 Teil C's decision: does Host Mode query MI read back the same
    value as verbose query MFILTER? FAIL confirms the mnemonic-table claim
    (MI = MFILTER, not MailDrop login) and that the app's MailDrop button
    sends the wrong command; PASS means no evidence for that; INCONCLUSIVE
    if either query failed."""
    if mi_value is None or mfilter_value is None:
        return "INCONCLUSIVE"
    return "FAIL" if mi_value == mfilter_value else "PASS"


# ---------------------------------------------------------------------------
# P20 Teil B -- MailDrop recorder (guided, mitschreib-style terminal)
# ---------------------------------------------------------------------------

_MAILDROP_QUERY_COMMANDS = [
    # MYCALL and XMITOK are deliberately NOT here - session.normalize()
    # (P21.2/P34.2) already queries/aborts-if-unanswered on both;
    # querying either again here would send it twice for no reason.
    "MAILDROP", "MYMAIL", "MTEXT", "MMSG",
    "3RDPARTY", "KILONFWD", "TMAIL", "MDMON",
]

_MAILDROP_SUGGESTED_SEQUENCE = """\
Round 3 - two open questions (rounds 1+2, 22.09.2026, already confirmed
L/S/R/K/B, @BBS, bulletins (SB), traffic (ST), the list format/date-time,
and the power-cycle test - see CLAUDE.md's MailDrop facts):

  S OE3GAS < DL1ABC      foreign FROM - note: '<' (less-than), not '>'
  (subject, text, /EX)   (round 2 typo'd '>' and the TNC silently
                         accepted the line up to it, so this is still
                         unanswered)
  S OE3GAS               end the text with ^Z - type the TWO CHARACTERS
  (subject, text)        '^' and 'Z'. Do NOT press Ctrl-Z: on Windows
  ^Z                     that ends console input (EOFError), not a
                         literal ^Z - the terminal now recovers from
                         that automatically if it happens anyway.
  L                      is FROM = DL1ABC for the first one?
  R <n>                  read the ^Z message - the tool reports whether
                         it also ends with a stray '/E' line
  R <n>                  read the /EX message - same check, for
                         comparison (round 1 found '/E' after '/EX')
  B                      the terminal ends at cmd:
"""

# ^Z/^D/^C typed at the md> prompt are sent as the matching single
# control byte, not as literal text.
_MAILDROP_CTRL_TOKENS = {"^Z": b"\x1a", "^D": b"\x04", "^C": b"\x03"}

_CONTROL_CHAR_LABELS = {
    0x03: "<^C>", 0x04: "<^D>", 0x0A: "<LF>", 0x0D: "<CR>", 0x1A: "<^Z>",
}


def classify_maildrop_input(line: str) -> tuple[str, Optional[bytes]]:
    """Classify one line typed at the maildrop recorder's md> prompt
    (P20 Teil B). Returns (kind, payload):

      ("quit", None)       - the tool's own exit command, never sent
      ("control", b'...')  - ^Z/^D/^C, sent as the single matching byte
      ("text", b'...\\r')   - a plain line, sent with a trailing CR
    """
    stripped = line.strip()
    if stripped == "/quit":
        return ("quit", None)
    if stripped in _MAILDROP_CTRL_TOKENS:
        return ("control", _MAILDROP_CTRL_TOKENS[stripped])
    return ("text", (line + "\r").encode("ascii", errors="replace"))


def format_bytes_with_controls(data: bytes) -> str:
    """Render *data* as text with control bytes shown as visible labels
    (<CR>, <LF>, <^Z>, ...) instead of invisible or garbled characters -
    the maildrop recorder's protocol format (P20 Teil B)."""
    out = []
    for b in data:
        if b in _CONTROL_CHAR_LABELS:
            out.append(_CONTROL_CHAR_LABELS[b])
        elif 0x20 <= b < 0x7F:
            out.append(chr(b))
        else:
            out.append(f"<${b:02X}>")
    return "".join(out)


def maildrop_session_left(tail_text: str) -> bool:
    """True if a verbose-mode 'cmd:' prompt appears anywhere in
    *tail_text* - the only observable signal that the local MailDrop
    session was left (P20 Teil B step 5). No Host Mode/verbose command is
    known to exit MailDrop, so this is a detection, not a control."""
    return "cmd:" in tail_text


# ---------------------------------------------------------------------------
# P21.3 -- mailbox terminal state machine (MAILBOX / ENTRY / CMD)
# ---------------------------------------------------------------------------

# Real prompt, hardware-confirmed 22.09.2026: '(AEA PK-232M)  18536 free
# (B,E,K,L,R,S) >' - round brackets, double spaces, differs from the TRM's
# '[AEA PK-232M] ... >' example. Searched ANYWHERE in the response, not
# anchored to the last line: SIAM can still interleave a result line right
# after the prompt even with normalize() run first (defence in depth,
# 22.09.2026 finding).
_MAILBOX_PROMPT_RE = re.compile(
    r"\(AEA PK-232M?\)\s+(\d+)\s+free\s+\(([A-Z,]+)\)\s*>"
)

# SysOp mailbox commands confirmed against the TRM/STABO handbook ch.5
# and real hardware 22.09.2026: B (bye), E (edit, not used this round),
# K (kill), L (list), R (read), S (send). 'H'/'?' are for OTHER users
# logging in, not the SysOp - confirmed: 'H' answers '*** What?'.
MAILBOX_EXIT_COMMAND = b"B\r"
MAILBOX_ABANDON_ENTRY_COMMAND = b"/EX\r"


def extract_mailbox_free(response_text: str) -> Optional[int]:
    """Return the free-byte count from a mailbox prompt in
    *response_text*, or None if no prompt is present (P21.3) - logged on
    every response so the operator can see how much space one message
    used."""
    m = _MAILBOX_PROMPT_RE.search(response_text)
    return int(m.group(1)) if m else None


_MAILDROP_SUBJECT_PROMPT = "Subject:"
_MAILDROP_TEXT_PROMPT = "Enter message, ^Z (CTRL-Z) or /EX to end"


def classify_maildrop_response(
    response_text: str, previous_state: str,
) -> tuple[str, bool]:
    """Redetermine the mailbox terminal's state from ONE response
    (P21.3, reworked P23.2). Returns (new_state, recognised).

    P23.2: the ENTRY transition is detected from the TNC's OWN response
    text now, never from what was typed to trigger it. Hardware-found
    22.09.2026 19:16: 'SB ALL' and 'ST OE3GAS' both got a real 'Subject:'
    prompt, but the old input-based check only recognised a literal
    'S ...' command, so the state stayed MAILBOX ("unrecognised
    response") for both. Had the operator stopped there, cleanup would
    have sent 'B' as a bare command instead of '/EX' - 'B' would have
    become a text LINE inside the still-open message body instead of
    leaving the mailbox.

    States:
      MAILBOX - the '(...)  <n> free  (...) >' prompt was seen
      ENTRY   - the mailbox is asking for a subject ('Subject:') or a
                message body ('Enter message, ^Z (CTRL-Z) or /EX to
                end'), or an earlier response already put it there and
                this one is just a plain text echo with no prompt of
                its own - free-form subject/text prompts here are the
                NORM, not a warning-worthy anomaly
      CMD     - a 'cmd:' prompt was seen. SAFETY: the caller must stop
                the interactive phase immediately when this is returned
                - once the TNC is back at its own command interpreter, a
                bare single-letter mailbox command means something
                completely different there (e.g. 'K' = CONVERSE,
                22.09.2026 finding).

    'recognised' is False only when the response matches nothing above
    AND there was no ENTRY state to fall back on - i.e. in MAILBOX
    state, where exactly one of the known prompts is always expected.
    """
    if maildrop_session_left(response_text):
        return "CMD", True
    if _MAILBOX_PROMPT_RE.search(response_text):
        return "MAILBOX", True
    stripped = response_text.rstrip()
    if stripped.endswith(_MAILDROP_SUBJECT_PROMPT):
        return "ENTRY", True
    if stripped.endswith(_MAILDROP_TEXT_PROMPT):
        return "ENTRY", True
    if previous_state == "ENTRY":
        return "ENTRY", True
    return previous_state, False


# ---------------------------------------------------------------------------
# P22 -- MailDrop protocol facts from the first full hardware run
# (hw_logs/20260922_184337_maildrop.log, tool-only helpers, not used by the
# application yet - there is no MailDrop dialog, see Backlog.md)
# ---------------------------------------------------------------------------

def parse_maildrop_list_row(line: str) -> Optional[dict]:
    """Parse one data row of a MailDrop 'L' listing into its fixed-width
    columns (P22.5). Hardware-confirmed 22.09.2026: columns are FIXED
    WIDTH regardless of content - an empty '@ BBS' still occupies its own
    blank columns, so this slices by position rather than splitting on
    whitespace (which would misalign once a field is empty).

    Column layout (0-indexed, confirmed against three real listings):
      [0:3]   Msg# (right-aligned)      [34:43]  Date (or dots)
      [4:6]   status: type + read       [45:50]  Time (or dots)
      [6:12]  Size                      [52:]    Title (rest of line)
      [13:19] To            [20:26] From          [26:34] @ BBS

    Date/Time show as dots ('.........'/'.....') until the TNC clock is
    set (no RAM buffer battery, CLAUDE.md) - returned as None, not the
    literal dots, since they are not a real date/time.

    Returns None if *line* is not a data row (too short, or its first
    field is not a number - e.g. the header line or the mailbox prompt).
    """
    if len(line) < 58:
        return None
    msg_no_text = line[0:3].strip()
    if not msg_no_text.isdigit():
        return None

    def _dots_to_none(value: str) -> Optional[str]:
        return None if value and set(value) <= {"."} else (value or None)

    status = line[4:6].strip()
    size_text = line[6:12].strip()
    return {
        "number": int(msg_no_text),
        "type": status[0] if status else "",
        "read": status[1] if len(status) > 1 else "",
        "size": int(size_text) if size_text.isdigit() else None,
        "to": line[13:19].strip(),
        "from": line[20:26].strip(),
        "bbs": line[26:34].strip() or None,
        "date": _dots_to_none(line[34:43].strip()),
        "time": _dots_to_none(line[45:50].strip()),
        "title": line[52:].strip(),
    }


def parse_maildrop_list(response_text: str) -> list[dict]:
    """Parse every data row out of one 'L' response's raw text (P22.5) -
    skips the echo, the header line, the mailbox prompt, and anything
    else that is not a data row (parse_maildrop_list_row() returns None
    for those). Tool-only measurement helper."""
    rows = []
    for line in response_text.replace("\r\n", "\n").split("\n"):
        parsed = parse_maildrop_list_row(line)
        if parsed is not None:
            rows.append(parsed)
    return rows


def maildrop_response_has_e_trailer(response_text: str) -> bool:
    """True if a MailDrop response ends with the firmware's own stray
    '/E' line just before the mailbox prompt (P22.1 finding, confirmed on
    'R <n>' responses 22.09.2026) - a remnant of the '/EX' end-of-message
    marker. Not part of the real message text; strip it before archiving
    the message."""
    lines = [
        ln for ln in response_text.replace("\r\n", "\n").split("\n") if ln != ""
    ]
    if not lines:
        return False
    if _MAILBOX_PROMPT_RE.search(lines[-1]):
        lines = lines[:-1]
    return bool(lines) and lines[-1].strip() == "/E"


_STORED_MESSAGE_RE = re.compile(r"Message stored as #\s*(\d+)")


def parse_stored_message_number(response_text: str) -> Optional[int]:
    """Return the message number from a 'Message stored as # <n>'
    response (P23.4), or None if the response does not contain one -
    used to remember whether a message was ended with '/EX' or with
    '^Z' ($1A), so a later 'R <n>' can report the '/E' trailer finding
    against the right ending method."""
    m = _STORED_MESSAGE_RE.search(response_text)
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# P24.2/P24.3 -- MailDrop over Host Mode (HOST bit 1: local login)
# ---------------------------------------------------------------------------

# TRM's HOST command bit table: bit 0 = Host Mode on/off, bit 1 = local
# MailDrop login (0 -> TX data $2x / RX echo $2F; 1 -> TX data $60 / RX
# data $70, monitored MXMIT traffic stays $2F), bit 2 = extended Host
# Mode. pk232py enters Host Mode with 'HOST 3' (bit 0 + bit 1 set), so
# the app already runs in the $60/$70 variant - whether anything actually
# uses that channel is what P24.2 measures.
MAILDROP_HOST_CTL = 0x60


def build_maildrop_host_frame(data: bytes) -> bytes:
    """Build a Host Mode data frame with CTL $60 - the MailDrop-login
    data channel (P24.2). No existing build_*() in comm/frame.py targets
    this CTL byte (it is not one of the $2x/$4x/$4F/$5x ranges they
    cover), so this assembles the frame directly - but reuses
    frame.py's own _dle_escape() for the payload, the same escaping
    every other outgoing frame uses, rather than reinventing it."""
    return bytes([SOH, MAILDROP_HOST_CTL]) + _dle_escape(data) + bytes([ETB])


def classify_maildrop_host_ctl(ctl: int) -> str:
    """Label a captured frame's CTL byte for the maildrop_host probe
    (P24.2/P24.3), per the TRM's HOST-bit-1 frame table: $70 = MailDrop
    read data, $2F = monitored MXMIT traffic (unaffected by the
    MailDrop-login bit), $4F/$5F = the same CMD_RESP/STATUS_ERR frames
    every other Host Mode command already uses. Anything else is
    genuinely unknown - this measurement makes no assumption about it."""
    if ctl == 0x70:
        return "MailDrop read data ($70)"
    if ctl == 0x2F:
        return "monitored MXMIT data ($2F)"
    if ctl == 0x4F:
        return "CMD_RESP ($4F)"
    if ctl == 0x5F:
        return "STATUS_ERR ($5F)"
    return f"unknown (${ctl:02X})"


def has_mailbox_data_frame(frames: list) -> bool:
    """True if *frames* contains a genuine mailbox response, not just the
    generic Host Mode data acknowledgement (P26.1 fix).

    Hardware-observed 21.09.2026 (T101): every Host Mode data frame gets a
    ctl=0x5F ('XX\\x00') acknowledgement regardless of whether anything
    downstream understood it. The maildrop_host probe's first hardware run
    (hw_logs/20260922_211322_maildrop_host.log) captured exactly one such
    ack for probe A and the old check (`bool(captured_a)`) mistook that ack
    for a real mailbox response, reporting "login not needed" when the
    mailbox had said nothing at all. A real response is $70 (the
    documented MailDrop read-data CTL) or, failing that, anything that is
    not $4F (CMD_RESP) or $5F (STATUS_ERR/ack) - the exact CTL a genuine
    mailbox reply would use over this channel was unmeasured before this
    probe, so this stays permissive about what counts, strict only about
    what does not."""
    return any(f.ctl not in (0x4F, 0x5F) for f in frames)


def should_run_maildrop_host_probe_b(captured_a: list) -> bool:
    """Probe B (MDCHECK login, then 'L' again) runs unless probe A already
    got a genuine mailbox response (P24.2/P24.3, fixed P26.1) - a bare
    '$5F' data acknowledgement is not a mailbox response (see
    has_mailbox_data_frame()); only real mailbox content means logging in
    first was not needed, and there is no reason to send more frames than
    necessary to answer that question."""
    return not has_mailbox_data_frame(captured_a)


# ---------------------------------------------------------------------------
# P26.2 -- mdcheck_scan: find the Host Mode mnemonic for MDCHECK
# ---------------------------------------------------------------------------

# 'M?' mnemonics mdcheck_scan never sends, with the TRM-cited reason each
# is a real command with its own meaning/side effect, not a MDCHECK
# candidate (P26.2). MI is additionally excluded because it is already
# identified (T115: MI = MFILTER, hardware-confirmed) - sending it again
# here would tell us nothing new.
MDCHECK_SCAN_DENYLIST: dict = {
    b"MO": "MORSE -- operating-mode switch",
    b"MI": "MFILTER -- already identified (T115), not a candidate",
    b"MM": "MEMORY -- reads memory and increments the ADDRESS counter",
}


def mdcheck_scan_candidates() -> list:
    """The 23 'M?' mnemonics mdcheck_scan actually queries (P26.2): every
    letter A-Z except the three in MDCHECK_SCAN_DENYLIST. The rest are, per
    the TRM, parameter queries or harmless direct commands (MH MHEARD
    prints a list, MV MAILDROP, MD MDIGI, MC MCON, ME MBELL, MF MFROM, MT
    MTO, MN MONITOR, MX MAXFRAME, MW MARSDISP, ...) - none writes, kills,
    or transmits."""
    return [
        bytes([ord('M'), letter])
        for letter in range(ord('A'), ord('Z') + 1)
        if bytes([ord('M'), letter]) not in MDCHECK_SCAN_DENYLIST
    ]


# The two fixed markers of the real mailbox prompt (hardware-confirmed
# 22.09.2026: '(AEA PK-232M)  18536 free  (B,E,K,L,R,S) >') - a hit is
# text containing BOTH, regardless of which Host Mode frame type carried
# it, since a real hit is prompt TEXT, never a recognised command echo
# (P26.2/P26.3).
_MDCHECK_HIT_MARKERS = ("(AEA PK-232M", "free")


def is_mdcheck_scan_hit(frames: list) -> bool:
    """True if any frame in *frames* looks like the mailbox login prompt
    (P26.2/P26.3). A plain $4F mnemonic echo (e.g. 'MV' + a value) or the
    generic $5F data acknowledgement ('XX\\x00') contains neither marker
    and is correctly NOT a hit."""
    return any(
        all(marker in f.text for marker in _MDCHECK_HIT_MARKERS)
        for f in frames
    )


def scan_for_mdcheck_mnemonic(
    candidates: list, probe: Callable[[bytes], list],
) -> Optional[bytes]:
    """Try *candidates* in order, calling ``probe(mnemonic)`` for each and
    returning the frames it captured, stopping at the FIRST hit (P26.2) -
    the search must not send more query frames than needed to find the
    answer. Returns the winning mnemonic, or None if nothing in the whole
    list hit. Pure orchestration - *probe* does the actual I/O, so this is
    unit-testable with a fake probe and no serial interface at all."""
    for mnemonic in candidates:
        frames = probe(mnemonic)
        if is_mdcheck_scan_hit(frames):
            return mnemonic
    return None


# ---------------------------------------------------------------------------
# P28 -- maildrop_session harness: drives the real MailDropSession for T119
# ---------------------------------------------------------------------------
#
# This harness contains NO protocol parsing and builds NO mailbox command
# of its own (P28's hard rule) - it only calls MailDropSession's public
# open()/list()/read()/kill()/send()/leave() and reacts to the signals it
# already fires. Anything that looks like validation below (checking a
# MailDropEntry's .mtype/.frm/.to) inspects data pk232py.maildrop.protocol
# already parsed - it is not a second parser of raw TNC text.

_MAILDROP_STEP_TIMEOUT_MS = 20_000  # one command's worth of real hardware time
_MAILDROP_CLEANUP_TIMEOUT_MS = 30_000  # leave() + Host Mode re-entry, generous


class MaildropStep:
    """One step of the maildrop_session sequence (P28): *action* calls
    exactly one MailDropSession method, *signal_name* names the signal
    that completes it, *expect* (only for "state_changed") the state
    value that counts as success, *validate* an optional
    ``(payload, ctx) -> (bool, detail)`` check against the ALREADY-PARSED
    object the signal carried (a MailDropEntry/list of them, never raw
    text)."""

    def __init__(self, name, action, signal_name, expect=None, validate=None):
        self.name = name
        self.action = action
        self.signal_name = signal_name
        self.expect = expect
        self.validate = validate


def _validate_list_three(entries: list, ctx: dict) -> tuple:
    numbers = {e.number: e for e in entries}
    wanted = {
        "send_personal": ctx.get("send_personal"),
        "send_foreign_from": ctx.get("send_foreign_from"),
        "send_bulletin": ctx.get("send_bulletin"),
    }
    missing = {k: n for k, n in wanted.items() if n not in numbers}
    if missing:
        return False, f"missing message(s) {missing} in listing {sorted(numbers)}"

    personal = numbers[wanted["send_personal"]]
    foreign = numbers[wanted["send_foreign_from"]]
    bulletin = numbers[wanted["send_bulletin"]]
    problems = []
    if personal.mtype != "P":
        problems.append(f"#{personal.number} mtype={personal.mtype!r}, expected P")
    if foreign.frm != "DL1ABC":
        problems.append(f"#{foreign.number} frm={foreign.frm!r}, expected DL1ABC")
    if bulletin.mtype != "B":
        problems.append(f"#{bulletin.number} mtype={bulletin.mtype!r}, expected B")
    if bulletin.to != "ALL":
        problems.append(f"#{bulletin.number} to={bulletin.to!r}, expected ALL")
    if problems:
        return False, "; ".join(problems)
    return True, (
        f"personal=#{personal.number} foreign=#{foreign.number} "
        f"bulletin=#{bulletin.number}"
    )


def _validate_read_first(payload: tuple, ctx: dict) -> tuple:
    entry, body = payload
    expected_num = ctx.get("send_personal")
    if entry.number != expected_num:
        return False, f"read #{entry.number}, expected #{expected_num}"
    if _MAILDROP_SESSION_BODY_TEXT not in body:
        return False, f"body does not match what was sent: {body!r}"
    return True, f"#{entry.number} body matches: {body!r}"


def _validate_list_after_kill(entries: list, ctx: dict) -> tuple:
    numbers = {e.number for e in entries}
    killed_num = ctx.get("send_personal")
    if killed_num in numbers:
        return False, f"killed message #{killed_num} still present: {sorted(numbers)}"
    still_expected = {ctx.get("send_foreign_from"), ctx.get("send_bulletin")}
    missing = still_expected - numbers
    if missing:
        return False, f"message(s) {missing} missing after kill: {sorted(numbers)}"
    return True, f"#{killed_num} gone, others intact: {sorted(numbers)}"


_MAILDROP_SESSION_BODY_TEXT = "hello from the maildrop_session harness"


def _start_abort_send(session, ctx: dict) -> None:
    """send(), then immediately abort() (P28's --abort-test). The subject
    exchange alone takes over a second (idle-gap detection), so abort()
    - called synchronously right after send() spawns its worker thread -
    is certain to run before the worker reaches the post-subject check."""
    session.send(
        "OE3GAS", "", "", "P", "T119 abort test", "this must never be sent",
    )
    session.abort()


def build_maildrop_session_steps(mycall: str, abort_test: bool) -> list:
    """The T119 step sequence (P28.1's table), plus the optional
    --abort-test probe. Pure data/orchestration - no I/O, unit-testable
    without a session at all."""
    steps = [
        MaildropStep(
            "open", lambda s, ctx: s.open(), "state_changed", expect="ACTIVE",
        ),
        MaildropStep("list_empty", lambda s, ctx: s.list(), "listing"),
        MaildropStep(
            "send_personal",
            lambda s, ctx: s.send(
                mycall, "", "", "P", "T119 personal", _MAILDROP_SESSION_BODY_TEXT,
            ),
            "stored",
        ),
        MaildropStep(
            "send_foreign_from",
            lambda s, ctx: s.send(
                mycall, "", "DL1ABC", "P", "T119 foreign from",
                "foreign FROM test",
            ),
            "stored",
        ),
        MaildropStep(
            "send_bulletin",
            lambda s, ctx: s.send("ALL", "", "", "B", "T119 bulletin", "bulletin test"),
            "stored",
        ),
        MaildropStep(
            "list_three", lambda s, ctx: s.list(), "listing",
            validate=_validate_list_three,
        ),
        MaildropStep(
            "read_first", lambda s, ctx: s.read(ctx["send_personal"]),
            "message_read", validate=_validate_read_first,
        ),
        MaildropStep(
            "kill_first", lambda s, ctx: s.kill(ctx["send_personal"]), "killed",
        ),
        MaildropStep(
            "list_after_kill", lambda s, ctx: s.list(), "listing",
            validate=_validate_list_after_kill,
        ),
        MaildropStep(
            "leave", lambda s, ctx: s.leave(), "state_changed", expect="CLOSED",
        ),
    ]
    if abort_test:
        steps += [
            MaildropStep(
                "reopen_for_abort", lambda s, ctx: s.open(), "state_changed",
                expect="ACTIVE",
            ),
            MaildropStep("send_then_abort", _start_abort_send, "failed"),
            MaildropStep(
                "leave_after_abort", lambda s, ctx: s.leave(), "state_changed",
                expect="CLOSED",
            ),
        ]
    return steps


class MaildropSessionRunner(QObject):
    """Drives a MailDropSession-shaped object through an ordered
    MaildropStep sequence (P28), calling only ITS public API and acting
    only on the signals it fires - see the module-level note above this
    class for why that is a hard rule, not a style choice.

    *session* needs the same six signals (state_changed/prompt_info/
    listing/message_read/stored/killed/failed) and six methods (open/
    list/read/kill/send/leave) as the real MailDropSession - tests pass a
    lightweight fake with the same shape, no serial interface at all.
    *on_finished(ok: bool)* is called exactly once, after any required
    cleanup (see _finish()).
    """

    def __init__(self, session, log: "RunLog", steps: list, on_finished) -> None:
        super().__init__()
        self.session = session
        self.log = log
        self.steps = steps
        self.on_finished = on_finished
        self.index = 0
        self.ctx: dict = {}
        self.results: list = []   # list[(name, "PASS"/"FAIL", detail)]
        self.last_bracket: Optional[str] = None  # P31.3: which prompt form was last seen
        self._stopped = False
        self._cleanup_ok = False
        self._timer: Optional[QTimer] = None

        session.state_changed.connect(self._on_state_changed)
        session.prompt_info.connect(self._on_prompt_info)
        session.listing.connect(self._on_listing)
        session.message_read.connect(self._on_message_read)
        session.stored.connect(self._on_stored)
        session.killed.connect(self._on_killed)
        session.failed.connect(self._on_failed)

    def start(self) -> None:
        self._run_current()

    def _current(self) -> Optional[MaildropStep]:
        if self._stopped or self.index >= len(self.steps):
            return None
        return self.steps[self.index]

    def _run_current(self) -> None:
        step = self._current()
        if step is None:
            self._finish(True)
            return
        self.log.line(f"--- step {self.index + 1}/{len(self.steps)}: {step.name} ---")
        self._arm_timeout(step)
        step.action(self.session, self.ctx)

    def _arm_timeout(self, step: MaildropStep) -> None:
        self._cancel_timeout()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self._on_timeout(step))
        self._timer.start(_MAILDROP_STEP_TIMEOUT_MS)

    def _cancel_timeout(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    def _on_timeout(self, step: MaildropStep) -> None:
        if self._current() is not step:
            return
        self._fail_step(
            step,
            f"timed out after {_MAILDROP_STEP_TIMEOUT_MS / 1000:.0f}s "
            f"waiting for {step.signal_name!r}",
        )

    def _pass_step(self, step: MaildropStep, detail: str = "") -> None:
        if self._current() is not step:
            return
        self._cancel_timeout()
        self.results.append((step.name, "PASS", detail))
        self.log.result(step.name, "PASS", detail)
        self.index += 1
        self._run_current()

    def _fail_step(self, step: MaildropStep, detail: str) -> None:
        if self._current() is not step:
            return
        self._cancel_timeout()
        self.results.append((step.name, "FAIL", detail))
        self.log.result(step.name, "FAIL", detail)
        self._finish(False)

    def _finish(self, ok: bool) -> None:
        """Runs exactly once. If the mailbox is still open (a mid-sequence
        command failed without the session's own open()/leave() recovery
        ever running), calls leave() as cleanup before reporting done -
        this IS 'den Ruckweg der Sitzung anstossen' from the spec, done
        entirely through the public API (P28.1 step 6)."""
        if self._stopped:
            return
        self._stopped = True
        self._cancel_timeout()
        self._cleanup_ok = ok
        if getattr(self.session, "state", None) == "ACTIVE":
            self.log.line(
                "finally: session state is 'ACTIVE', not CLOSED -- "
                "calling leave() as cleanup"
            )
            self.session.state_changed.connect(self._on_cleanup_state)
            self._arm_cleanup_timeout()
            self.session.leave()
        else:
            self.on_finished(ok)

    def _arm_cleanup_timeout(self) -> None:
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self._on_cleanup_state("TIMEOUT"))
        self._timer.start(_MAILDROP_CLEANUP_TIMEOUT_MS)

    def _on_cleanup_state(self, state: str) -> None:
        if state not in ("CLOSED", "FAILED", "TIMEOUT"):
            return
        self._cancel_timeout()
        try:
            self.session.state_changed.disconnect(self._on_cleanup_state)
        except Exception:
            pass
        self.log.line(f"finally: session state is now {state!r}")
        self.on_finished(self._cleanup_ok)

    # -- signal handlers: log EVERY signal unconditionally, act only when
    # it is what the current step is waiting for ------------------------

    def _on_state_changed(self, state: str) -> None:
        self.log.line(f"state_changed: {state}")
        step = self._current()
        if step and step.signal_name == "state_changed" and state == step.expect:
            self._pass_step(step, f"state={state}")

    def _on_prompt_info(self, info) -> None:
        self.last_bracket = getattr(info, "bracket", None)
        self.log.line(
            f"prompt_info: free={info.free} commands={info.commands} "
            f"have_mail={info.have_mail} bracket={self.last_bracket!r}"
        )
        step = self._current()
        if step and step.signal_name == "prompt_info":
            self._pass_step(step, f"free={info.free}")

    def _on_listing(self, entries: list) -> None:
        self.log.line(f"listing: {len(entries)} entry/ies")
        for e in entries:
            self.log.line(
                f"    #{e.number} {e.mtype}{'Y' if e.read else 'N'} "
                f"to={e.to} from={e.frm} bbs={e.bbs!r} stamp={e.stamp!r} "
                f"title={e.title!r}"
            )
        step = self._current()
        if step and step.signal_name == "listing":
            ok, detail = step.validate(entries, self.ctx) if step.validate else (True, f"{len(entries)} entries")
            (self._pass_step if ok else self._fail_step)(step, detail)

    def _on_message_read(self, entry, body: str) -> None:
        self.log.line(f"message_read: #{entry.number} body={body!r}")
        step = self._current()
        if step and step.signal_name == "message_read":
            ok, detail = step.validate((entry, body), self.ctx) if step.validate else (True, "")
            (self._pass_step if ok else self._fail_step)(step, detail)

    def _on_stored(self, number: int) -> None:
        self.log.line(f"stored: #{number}")
        step = self._current()
        if step and step.signal_name == "stored":
            self.ctx[step.name] = number
            self._pass_step(step, f"#{number}")

    def _on_killed(self, number: int) -> None:
        self.log.line(f"killed: #{number}")
        step = self._current()
        if step and step.signal_name == "killed":
            self._pass_step(step, f"#{number}")

    def _on_failed(self, text: str) -> None:
        self.log.line(f"failed: {text}")
        step = self._current()
        if step is None:
            return
        if step.signal_name == "failed":
            # This step EXPECTS a failure - the --abort-test probe.
            self._pass_step(step, text)
        else:
            self._fail_step(step, text)


def run_maildrop_interactive(
    initial_state: str,
    initial_free: Optional[int],
    read_line: Callable[[str, Optional[int]], Optional[str]],
    send: Callable[[bytes, str], bytes],
    log: "RunLog",
) -> tuple[str, Optional[bytes], bool]:
    """Drive the mailbox terminal's interactive loop (P21.3). Pure of any
    real I/O - *read_line(state, free)* returns the next typed line (or
    None on EOF), *send(payload, note)* writes it and returns the raw
    response bytes. Returns (final_state, last_sent_payload,
    message_stored) - the third value is True if any response during
    this session contained 'Message stored as #' (P22.2: the power-cycle
    test's PASS needs to know at least one real message existed before
    the cycle, not just that 'L' comes back empty afterwards, which an
    already-empty mailbox would also show).

    SAFETY (the reason this function exists as a single, testable unit):
    the moment a response's state becomes CMD, this returns IMMEDIATELY,
    without calling read_line() or send() again. Found necessary
    22.09.2026: after 'B' silently closed the mailbox, the md> prompt
    stayed up and further typed input reached the TNC's own command
    interpreter, where single letters mean something else entirely ('K'
    = CONVERSE) - with MYCALL set and XMITOK ON, that would have
    transmitted.

    P23.3: a Windows console turns a typed Ctrl-Z into an EOFError, not
    the two literal characters '^'/'Z' - read_line() reports that the
    same way as a real "input closed" (returns None), so this function
    tells them apart by STATE: None while in ENTRY is read as "the
    operator meant to end the message" and sends $1A instead of
    stopping; None anywhere else is still a real EOF, same as before.

    P23.4: tracks which ending method (('/EX' or '^Z') each stored
    message used, so a later 'R <n>' typed by the operator can report
    the maildrop_response_has_e_trailer() finding against the right one
    in the run's summary (log.result()), separately for each method.
    """
    state = initial_state
    free = initial_free
    last_sent: Optional[bytes] = None
    message_stored = False
    end_method_by_number: dict[int, str] = {}
    pending_end_method: Optional[str] = None

    while True:
        line = read_line(state, free)
        if line is None:
            if state != "ENTRY":
                log.line("INFO: input closed (EOF) - leaving the terminal")
                return state, last_sent, message_stored
            log.line(
                "INFO: console Ctrl-Z interpreted as message end "
                "(EOFError in ENTRY state)"
            )
            payload = b"\x1a"
            note = f"[{state}] console Ctrl-Z (EOF)"
            pending_end_method = "^Z"
        else:
            kind, payload = classify_maildrop_input(line)
            if kind == "quit":
                log.line("INFO: operator typed /quit - leaving the terminal")
                return state, last_sent, message_stored
            note = f"[{state}] {line.strip()!r}"
            if payload == b"\x1a":
                pending_end_method = "^Z"
            elif line.strip().upper() == "/EX":
                pending_end_method = "/EX"

        last_sent = payload
        resp_bytes = send(payload, note)
        resp_text = resp_bytes.decode("ascii", errors="replace")

        if "*** No free memory" in resp_text:
            log.line("WARNING: mailbox reports *** No free memory")
        stored_number = parse_stored_message_number(resp_text)
        if stored_number is not None:
            message_stored = True
            if pending_end_method is not None:
                end_method_by_number[stored_number] = pending_end_method
            pending_end_method = None

        if line is not None and line.strip().upper().split()[:1] == ["R"]:
            parts = line.strip().split()
            msg_num = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
            has_trailer = maildrop_response_has_e_trailer(resp_text)
            method = end_method_by_number.get(msg_num, "unknown")
            log.result(
                f"MAILDROP R{msg_num if msg_num is not None else '?'}", "INFO",
                f"/E trailer={has_trailer} (message ended via {method})"
            )

        new_state, recognised = classify_maildrop_response(resp_text, state)
        if not recognised:
            log.line(
                f"WARNING: unrecognised response (state stays {state!r}): "
                f"hex={resp_bytes.hex(' ').upper()}"
            )
        state = new_state

        maybe_free = extract_mailbox_free(resp_text)
        if maybe_free is not None:
            free = maybe_free
            log.line(f"Mailbox free memory: {free}")

        if state == "CMD":
            log.line(
                "INFO: 'cmd:' prompt seen - interactive phase stopped "
                "immediately (safety rule, P21.3)"
            )
            return state, last_sent, message_stored


def read_power_cycle_confirmation(read_line: Callable[[], str]) -> bool:
    """Repeatedly call *read_line()* until it answers 'done' or 'skip'
    (case-insensitive, whitespace-tolerant) - P22.2. Returns True for
    'done' (proceed with the power-cycle check), False for 'skip'.
    Anything else re-asks: an earlier run's blank Enter was silently
    read as "not yes" and skipped the test before this confirm loop
    existed, before the operator had actually power-cycled the TNC."""
    while True:
        answer = read_line().strip().lower()
        if answer == "done":
            return True
        if answer == "skip":
            return False


def evaluate_power_cycle_loss(
    had_message_before: bool, list_response_after: str
) -> str:
    """P22.2's power-cycle decision: PASS only if a message genuinely
    existed before the cycle AND 'L' now reports the mailbox empty
    ('*** Message not found.') - an already-empty mailbox reporting
    empty again would prove nothing. INCONCLUSIVE otherwise."""
    if had_message_before and "Message not found" in list_response_after:
        return "PASS"
    return "INCONCLUSIVE"


def scan_for_tnc_errors(lines: list[str]) -> list[str]:
    """Return every response line that looks like a TNC error message
    ('?What?', '?bad', '?too many', or any other line starting with '?')."""
    return [ln for ln in lines if ln.strip().startswith("?")]


def detect_pthuff_format(response: str) -> str:
    """Classify a PTHUFF query response as 'numeric', 'on_off', or 'unknown'."""
    body = response.upper()
    if "ON" in body or "OFF" in body:
        return "on_off"
    if any(c.isdigit() for c in body):
        return "numeric"
    return "unknown"


def evaluate_t101(target_a: Optional[str], target_b: Optional[str]) -> str:
    """T101's decision table (see the docstring's operator questions):
    did the decoded UI frame's destination follow the UNPROTO path we
    set (TEST1 then TEST2), stay fixed regardless, or not arrive at all?
    """
    if target_a is None or target_b is None:
        return "INCONCLUSIVE"
    if target_a == "TEST1" and target_b == "TEST2":
        return "PASS"
    if target_a == target_b:
        return "FAIL"
    return "INCONCLUSIVE"


# ===========================================================================
# P62 -- APRS measurement pure logic (evaluate_aprs_round + the two fixed
# test payloads aprs_tx sends). No serial interface, unit-testable directly.
# ===========================================================================

# Punctuation-only fragment from docs/P62_APRS_Measure_Spec.md's own R3
# example, kept verbatim (it deliberately exercises characters an AX.25/
# APRS parser could choke on: backslash, backtick, brace, tilde, ...).
# The spec's own literal example text does NOT by itself cover every
# printable ASCII character (no digits, almost no letters) despite its
# own Teil D asking for exactly that coverage - digits and both letter
# cases are appended below so the actual R3 payload satisfies its own
# test (test_hw_check_aprs.py::TestBuildAprsR3Info), not just resembles it.
_APRS_R3_PUNCTUATION = "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
_APRS_R3_DIGITS = "0123456789"
_APRS_R3_UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_APRS_R3_LOWER = "abcdefghijklmnopqrstuvwxyz"
_APRS_R3_CHARSET = (
    _APRS_R3_PUNCTUATION + _APRS_R3_DIGITS + _APRS_R3_UPPER + _APRS_R3_LOWER
)

_APRS_R4_PREFIX = ">P62 R4 "
_APRS_R4_DIGITS = "0123456789"
_APRS_R4_BODY_LEN = 200


def build_aprs_r3_info() -> str:
    """R3's character-set probe info field (P62, Teil B) - one UI frame
    carrying every printable ASCII character 0x21-0x7E at least once, so
    a byte a naive parser chokes on (backslash, backtick, a brace) shows
    up here rather than silently mangling a later real APRS position/
    status report."""
    return ">P62 R3 " + _APRS_R3_CHARSET + " END"


def build_aprs_r4_info(body_len: int = _APRS_R4_BODY_LEN) -> str:
    """R4's length probe info field (P62, Teil B): the prefix plus a
    repeating digit sequence, trimmed to exactly *body_len* characters,
    with ' END' appended afterwards as an unambiguous end marker for the
    operator pasting the decoder's line back in - APRS needs the whole
    payload in ONE UI frame, so 'END' must never be split off by
    PACLEN-driven fragmentation for this to mean anything."""
    body = _APRS_R4_PREFIX
    while len(body) < body_len:
        body += _APRS_R4_DIGITS
    return body[:body_len] + " END"


# Direwolf/AGW-style monitor line: '[<channel>] <SRC>><DST>...:<info>'
# - e.g. '[0.5] OE3GAS>APZ232,WIDE1-1,WIDE2-1:>PK232PY P62 R2 12:00:00'.
# Matched at the START of a line only, so an info field that happens to
# contain a similar-looking substring (R3's own charset probe has colons
# and angle brackets in it) is never miscounted as a second frame
# header (P62a, Teil A - the operator no longer counts frames by hand).
_APRS_FRAME_HEADER_RE = re.compile(r"^\[[^\]]*\]\s*\S+>\S+.*:")


def count_aprs_frames(pasted: str) -> int:
    """How many separate AX.25 frame headers appear in a decoder paste
    (P62a, Teil A) - replaces asking the operator to count by hand,
    itself a real error source on real hardware (T139 R4, 27.09.2026:
    the operator-typed count was the SECOND thing that went wrong in
    that round, after the paste itself got cut off)."""
    return sum(
        1 for line in pasted.splitlines() if _APRS_FRAME_HEADER_RE.match(line)
    )


def classify_unproto_digi_limit(parsed: Optional[str]) -> str:
    """P62a, Teil B.1 - aprs_query's A.6 resets UNPROTO to CQ before
    attempting a 9th digipeater, so this classification is unambiguous
    (Device B, 27.09.2026: without that reset, the query after a
    9-digi attempt still showed the PREVIOUS step's 8 digis, and
    'truncated to 8' vs. 'rejected, still showing the old 8-digi value'
    could not be told apart). *parsed* is the UNPROTO value AFTER the
    9-digi set attempt, via parse_query_value(). Three answers, plus a
    defensive 'unknown' for anything that matches none of them:
      'rejected'  - still CQ, the whole set was refused.
      'truncated' - 8 digis present, the 9th (D9) is not.
      'accepted'  - all 9 digis, including D9, are present.
    """
    if parsed is None:
        return "unknown"
    upper = parsed.strip().upper()
    if upper == "CQ":
        return "rejected"
    if "D9" in upper:
        return "accepted"
    if "D8" in upper:
        return "truncated"
    return "unknown"


def evaluate_aprs_round(
    sent_info: str, sent_path: Optional[str], pasted: str,
) -> dict:
    """Compare what a second station's AX.25 decoder actually showed for
    one aprs_tx round against what was sent (P62, Teil B/D; P62a Teil A
    - frame count is now derived from *pasted* itself via
    count_aprs_frames(), never a separate operator-typed number). Pure -
    no serial interface, so this is unit-testable without hardware.

    *sent_path*, when given, is the comma-separated VIA digipeater list
    (e.g. 'WIDE1-1,WIDE2-1') - only R2 passes one; every other round
    passes None, and path_ok then stays None too (nothing to check).

    Reports each check SEPARATELY rather than folding everything into
    one opaque boolean, so a FAIL names exactly what did not match:
      info_exact  - sent_info appears verbatim, byte-for-byte, in pasted.
      trailing_cr - pasted shows a Direwolf-style '<0x0d>' control-byte
                    marker - whether the TNC appends a CR to the info
                    field is exactly what R3 exists to answer.
      path_ok     - every digipeater callsign in sent_path appears in
                    pasted, or None if sent_path itself was None.
      frames      - count_aprs_frames(pasted) (APRS needs exactly one
                    frame per message).

    An empty/whitespace-only *pasted* means the round was skipped (the
    operator entered '.' immediately, with nothing pasted in between) -
    verdict is 'INFO', never a silently-wrong PASS or FAIL with no
    evidence behind it.
    """
    if not pasted.strip():
        return {
            "verdict": "INFO", "info_exact": None, "trailing_cr": None,
            "path_ok": None, "frames": 0,
        }

    frames = count_aprs_frames(pasted)
    info_exact = sent_info in pasted
    trailing_cr = "<0x0d>" in pasted

    if sent_path is not None:
        digis = [
            d.strip() for d in sent_path.split("VIA", 1)[-1].split(",")
            if d.strip()
        ]
        path_ok = all(d in pasted for d in digis)
    else:
        path_ok = None

    ok = info_exact and frames == 1 and (path_ok is None or path_ok)
    return {
        "verdict": "PASS" if ok else "FAIL",
        "info_exact": info_exact, "trailing_cr": trailing_cr,
        "path_ok": path_ok, "frames": frames,
    }


# ===========================================================================
# P65/P66/P67 -- link/mode carry-over measurement pure logic. No serial
# interface, unit-testable directly. decode_link_status()/LinkStatus and
# parse_cstatus() now live in comm/link_status.py (P67, Teil A) - the
# SAME decoder the app's own LinkTable uses; this file no longer keeps
# its own copy.
# ===========================================================================

def parse_cstatus_io_channel(text: str) -> Optional[int]:
    """Which channel a verbose CSTATUS response marks as the TNC's own
    active ('I/O') channel, distinct from any channel a CONNECTED line
    names (P66, B.4) - e.g. a line reading 'Ch. 9 - IO' -> 9. None if no
    such line is present (measured, never guessed). Thin wrapper around
    comm.link_status.parse_cstatus() (P67, Teil A)."""
    for channel, (io, _state_text, _partner) in parse_cstatus(text).items():
        if io:
            return channel
    return None


def verify_restore(
    command: str,
    query: Callable[[], str],
    restore: Callable[[str], None],
    original: str,
    log: "RunLog",
) -> None:
    """Restore *command* to *original* and confirm it stuck (P15.2) - the
    common tail of run_with_restore(), pulled out so a test that must
    restore SEVERAL parameters around ONE action (T112: MAXFRAME, SLOTTIME,
    VHF, HBAUD around a single mode-switch action) can call this once per
    parameter instead of nesting run_with_restore() several times around
    the same action."""
    restore(original)
    verified = parse_query_value(command, query())
    if verified == original:
        log.line(f"{command} restored to {original!r}")
    else:
        log.result(
            command, "FAIL",
            f"restore of {command} failed -- TNC now reports {verified!r}, "
            f"expected {original!r} -- set it by hand: {command} {original}"
        )


def run_with_restore(
    command: str,
    query: Callable[[], str],
    restore: Callable[[str], None],
    action: Callable[[], None],
    log: "RunLog",
) -> Optional[str]:
    """Read *command*'s original value, run *action*, then restore and
    VERIFY it (P15.2) - even if *action* raises (hard rule #2).

    - If the original value can't be parsed via parse_query_value(), the
      test is SKIPPED and *action* never runs - no safe value to go back
      to (P15.2 rule 1).
    - *action* is solely responsible for whatever the test needs to change;
      this function never sends a set command before it runs (P15.2 rule 2 -
      the old code's premature restore-token write, e.g. 'PTHUFF cmd:', is
      exactly what this rule forbids).
    - After *action*, *restore* is called with the ORIGINAL value, then the
      parameter is queried again and compared. Only a verified match is
      ever logged as "restored"; a mismatch is a clearly flagged FAIL naming
      the manual fix-up command, never silently claimed as success.

    Pure orchestration apart from parse_query_value() and log calls, so it
    stays unit-testable with fakes, no serial interface involved.
    """
    original = parse_query_value(command, query())
    if original is None:
        log.result(
            command, "SKIPPED",
            "original value not parseable via parse_query_value() - not touching it"
        )
        return None
    try:
        action()
    finally:
        verify_restore(command, query, restore, original, log)
    return original


def ensure_vhf_1200(
    session: "Session", log: "RunLog", tag: str, originals: dict,
) -> bool:
    """The ONE VHF/HBAUD 1200 Bd check for every subcommand that needs
    the TNC on VHF Packet at 1200 Bd (aprs_tx, aprs_reject, link_carry,
    link_carry_host, channel_probe). *originals* holds the already
    queried, parsed 'VHF'/'HBAUD' values (the caller restores them
    afterwards). If the TNC is not at VHF 1200 Bd the operator is asked
    before VHF ON / HBAUD 1200 are set for this run. Returns False - after
    logging an INFO result under *tag* - if the operator declines and the
    run must stop; True to continue."""
    log.line(
        f"VHF (current): {originals['VHF']!r}, "
        f"HBAUD (current): {originals['HBAUD']!r}"
    )
    vhf_ok = originals["VHF"].strip().upper() in ("Y", "ON", "1")
    hbaud_ok = originals["HBAUD"].strip() == "1200"
    if not (vhf_ok and hbaud_ok):
        answer = input(
            f"TNC is not on VHF 1200 Bd (VHF={originals['VHF']!r}, "
            f"HBAUD={originals['HBAUD']!r}). Set VHF ON and HBAUD 1200 "
            f"for this run? [y/N] "
        ).strip().lower()
        if answer != "y":
            log.result(tag, "INFO", "aborted - TNC not on VHF 1200 Bd")
            return False
        session.set_verbose("VHF", "ON")
        session.set_verbose("HBAUD", "1200")
    return True


# ===========================================================================
# P30 -- port ownership logging and byte-level init-phase capture
# ===========================================================================
#
# maildrop_session's own reported failure (P30): wakeup times out even
# right after a power-cycle, with no byte-level evidence in the log at
# all, since the init phase runs entirely inside SerialManager, which has
# no equivalent of the other subcommands' own protocol logging. The
# pieces below add that visibility without rebuilding or monkeypatching
# SerialManager - set_port_factory() is an existing, generic seam.

def release_leftover_port(sm, log: "RunLog") -> bool:
    """P30.1: if *sm* already thinks a port is open before
    Session.connect() ever calls connect_port(), that is a leftover from
    something earlier in this same process - release it and say so,
    rather than silently trying to open a second port on top of it.
    Returns True if a leftover port was found and released, False if
    there was nothing to release. Pure enough to unit-test against a
    fake with just .is_connected/.disconnect_port()."""
    if not sm.is_connected:
        return False
    log.line(
        "WARNING: harness still held an open port before this run -- "
        "releasing it first (see docs/P30_Session_Harness_Logging_Spec.md)"
    )
    sm.disconnect_port()
    return True


class LoggingSerialPort:
    """Thin pass-through wrapper around a real serial.Serial object
    (P30.2). Logs write()/read()/reset_input_buffer()/close() with a
    timestamp, hex AND text (control characters visible, matching every
    other subcommand's own protocol log format) and keeps a running total
    of every byte sent/received for the end-of-run summary; everything
    else (in_waiting, is_open, rts, dtr, port, baudrate, flush(),
    open(), ...) passes straight through unchanged via
    __getattr__/__setattr__.

    Injected ONLY for maildrop_session, via SerialManager's existing
    set_port_factory() seam - chosen deliberately over monkeypatching:
    the seam already exists for exactly this (a dev-only mock plugging
    into a generic factory), so there is nothing smaller to build.
    """

    def __init__(self, real_port, log: "RunLog") -> None:
        object.__setattr__(self, "_real_port", real_port)
        object.__setattr__(self, "_log", log)
        object.__setattr__(self, "sent_total", bytearray())
        object.__setattr__(self, "received_total", bytearray())

    def write(self, data: bytes):
        self.sent_total.extend(data)
        self._log.line(
            f">> hex={data.hex(' ').upper()} text={format_bytes_with_controls(data)}"
        )
        return self._real_port.write(data)

    def read(self, size: int = 1) -> bytes:
        data = self._real_port.read(size)
        if data:
            self.received_total.extend(data)
            self._log.line(
                f"<< hex={data.hex(' ').upper()} text={format_bytes_with_controls(data)}"
            )
        return data

    def reset_input_buffer(self) -> None:
        self._log.line("-- reset_input_buffer()")
        self._real_port.reset_input_buffer()

    def close(self) -> None:
        self._log.line("-- close() (port released)")
        self._real_port.close()

    def __getattr__(self, name):
        return getattr(self._real_port, name)

    def __setattr__(self, name, value):
        setattr(self._real_port, name, value)


_INIT_PHASE_SOH = 0x01


def classify_init_phase(sent: bytes, received: bytes) -> str:
    """Turn the init phase's raw bytes into a plain-language hint for the
    operator (P30.3) - a HELP, not a verdict; the raw bytes are always
    logged above it regardless, so a wrong guess here costs nothing."""
    if not received:
        return "no data at all -- port held elsewhere or wrong port"
    if _INIT_PHASE_SOH in received:
        return "TNC still in Host Mode"
    if received.strip(b"\r\n") == sent.strip(b"\r\n"):
        return "TNC already awake -- needs CR (see P29)"
    if b"cmd:" not in received:
        return "banner truncated -- timeout too short"
    return "wakeup answered normally"


class _RunLogHandler(logging.Handler):
    """Forwards Python logging records into the same RunLog/log file the
    harness already writes to (P30.2's "raise pk232py.comm to DEBUG and
    write to the same file") - so serial_manager.py's own
    ``logger.debug("Wakeup response (%d B): %s", ...)`` (and everything
    else at DEBUG level) lands in hw_logs/..._maildrop_session.log
    alongside the harness's own lines, instead of nowhere."""

    def __init__(self, log: "RunLog") -> None:
        super().__init__()
        self._log = log

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._log.line(f"[{record.name}] {self.format(record)}")
        except Exception:
            self.handleError(record)


def _log_init_phase_summary(log: "RunLog", wrapper: "LoggingSerialPort") -> None:
    """P30.3: a plain-language hint at the end of the run, from whatever
    the init phase actually sent/received - never a replacement for the
    raw bytes already logged above it."""
    sent = bytes(wrapper.sent_total)
    received = bytes(wrapper.received_total)
    hint = classify_init_phase(sent, received)
    log.line(
        f"init phase summary: sent {len(sent)} B, received {len(received)} B "
        f"-- {hint}"
    )
    log.result("MAILDROP_SESSION", "INFO", f"init phase: {hint}")


# ===========================================================================
# Session - the one place that touches SerialManager
# ===========================================================================


def confirm_command_prompt(
    send: Callable[[bytes, str], bytes],
    recover: Callable[[], None],
    log: "RunLog",
) -> None:
    """P34.1: verify the TNC answers with a verbose 'cmd:' prompt before
    normalize() -- or anything else -- sends a single further verbose
    command. Pure of any real I/O: *send(payload, note)* writes and
    returns the raw response bytes, *recover()* runs the documented Host
    Mode recovery/resync (SerialManager.recovery(): the double-SOH
    recovery frame, TRM 4.1.6, then the binary HOST OFF frame -- see
    SERIAL_CONNECTION_STATE_MACHINE.md's "Recovery" section) -- existing
    machinery, nothing rebuilt here.

    Found necessary 23.09.2026 (P34, hw_logs/20260923_203256_mdcheck_scan
    .log): a run's verbose phase sent PACKET/MYCALL/XMITOK/MDCHECK/S/
    subject/text/EX/B into a TNC that only ever echoed each line back,
    never once answering 'cmd:' -- most likely Converse, where typed
    text is echoed and queued for transmission. XMITOK was unknown at
    the time for the very same reason; had it been ON as in every prior
    run, those lines would have gone out over the air. This is the hard
    gate the rest of normalize() -- and everything that runs after it --
    depends on: kein verbose-Befehl wird gesendet, solange der cmd:-
    Prompt nicht in derselben Sitzung bestaetigt wurde.

    Tries, in order: (1) Ctrl-C + CR, (2) CR alone (resync stage 1), (3)
    the Host Mode recovery frame followed by Ctrl-C + CR again (resync
    stage 2). Raises HWCheckError -- and sends NOTHING further itself --
    the instant all three have failed to produce a 'cmd:' prompt.
    """
    resp = send(b"\x03\r", "Ctrl-C + CR (normalize)")
    if b"cmd:" in resp:
        return
    log.line(
        "WARNING: no cmd: prompt after Ctrl-C + CR -- resync stage 1 (CR)"
    )
    resp = send(b"\r", "resync stage 1: CR alone")
    if b"cmd:" in resp:
        return
    log.line(
        "WARNING: no cmd: prompt after CR alone -- resync stage 2 "
        "(Host Mode recovery frame)"
    )
    recover()
    resp = send(b"\x03\r", "resync stage 2: Ctrl-C + CR after recovery")
    if b"cmd:" in resp:
        return
    raise HWCheckError(
        "TNC is not at the command prompt (echo only). Nothing was sent. "
        "Check with a terminal program; power-cycle the TNC if it stays "
        "unresponsive."
    )


def require_query_value(
    value: Optional[str], cmd: str, consequence: str = "",
) -> str:
    """P34.2: normalize()'s MYCALL/XMITOK queries confirm STATE the rest
    of the run depends on, unlike an ordinary single parameter query --
    an unanswered one (None) aborts here instead of being logged and
    continued past (CLAUDE.md's "never guess state" rule, same class as
    P15's "no reported success without proof"). *consequence*, when
    given, is appended to the abort message so it says what specifically
    can no longer be guaranteed -- XMITOK unknown means the "never
    transmits on the air" promise cannot be honoured.
    """
    if value is not None:
        return value
    suffix = f" -- {consequence}" if consequence else ""
    raise HWCheckError(f"{cmd} query went unanswered{suffix}")


def create_mdcheck_test_message(
    send: Callable[[bytes, str], bytes],
    subject: bytes,
    body: bytes,
    log: "RunLog",
) -> tuple[bool, Optional[int]]:
    """P34.3: create one MailDrop test message (maildrop_host/
    mdcheck_scan share this), but only after MDCHECK's own response is
    recognised as the real mailbox prompt (find_prompt(), protocol.py --
    both bracket forms, P31). 23.09.2026 found the TNC can answer
    MDCHECK with nothing but its own echo (P34, most likely Converse) --
    typing 'S OE3GAS' etc. straight afterwards would then send those
    lines into an unconfirmed context instead of into the mailbox.

    Pure of any real I/O: *send(payload, note)* writes and returns the
    raw response bytes. Returns (entered, msg_number):
      - entered=False, msg_number=None: MDCHECK's response was not
        recognised -- nothing past MDCHECK itself was sent. Callers must
        not run 'L'/'B' either (not confirmed to be inside the mailbox);
        this only skips the test message, the scan/probe does not need
        it to proceed.
      - entered=True, msg_number=None: the mailbox was entered but the
        final store response could not be parsed for a message number --
        logged here as its own WARNING, never silently as 'stored as
        # None' (the exact thing the 23.09.2026 run produced).
      - entered=True, msg_number=<int>: normal success.
    """
    mdcheck_resp = send(b"MDCHECK\r\n", "MDCHECK (test message gate, P34.3)")
    if find_prompt(mdcheck_resp.decode("ascii", errors="replace")) is None:
        log.line(
            "INFO: MDCHECK did not answer with a recognised mailbox "
            "prompt -- skipping the test message; nothing past MDCHECK "
            "itself was sent"
        )
        return False, None
    send(b"S OE3GAS\r", "start message")
    send(subject + b"\r", "subject")
    send(body + b"\r", "body")
    store_resp = send(MAILBOX_ABANDON_ENTRY_COMMAND, "store (/EX)")
    msg_number = parse_stored_message_number(
        store_resp.decode("ascii", errors="replace")
    )
    if msg_number is not None:
        log.line(f"Test message stored as # {msg_number}")
    else:
        log.line(
            f"WARNING: could not parse a message number from the store "
            f"response (raw: {store_resp!r})"
        )
    return True, msg_number


class Session:
    """Owns the serial connection and the small amount of Qt plumbing
    SerialManager needs (it is a QObject; its background threads emit
    pyqtSignal, so a QCoreApplication must exist for those to be delivered -
    see CLAUDE.md's Host Mode entry/exit notes for why this all runs on
    background threads in the first place)."""

    def __init__(
        self, port: str, baud: int, dry_run: bool, log: RunLog,
        app_config: AppConfig,
    ):
        self.port_name = port
        self.baud = baud
        self.dry_run = dry_run
        self.log = log
        self.app_config = app_config
        self._app = QCoreApplication.instance() or QCoreApplication(sys.argv[:1])
        self.sm = SerialManager()
        self._raw_buf = bytearray()
        self.sm.raw_data_received.connect(self._on_raw)
        self.xmitok: Optional[str] = None  # set by normalize() (P34.2)

    def _on_raw(self, data: bytes) -> None:
        self._raw_buf.extend(data)

    def _pump(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self._app.processEvents()
            time.sleep(0.01)

    def _wait_until(self, condition: Callable[[], bool], timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._app.processEvents()
            if condition():
                return True
            time.sleep(0.02)
        return condition()

    # -- Connection lifecycle ----------------------------------------------

    def _log_port_owner(self, owner: str, note: str = "") -> None:
        """P30.1: a visible line for every port-ownership transition -
        'harness' (this Session/hw_check.py process itself), 'SerialManager'
        (the normal owner while connected), or 'hostmode subprocess' (brief
        ownership during the HOST 3 handshake, see serial_manager.py)."""
        self.log.line(f"port owner: {owner}{note}")

    def connect(self) -> None:
        if release_leftover_port(self.sm, self.log):
            self._log_port_owner("none", " (leftover released)")
        self._log_port_owner("none", " (about to open)")
        if not self.sm.connect_port(self.port_name, baudrate=self.baud):
            raise HWCheckError(
                f"Port busy - is pk232py running? ({self.port_name})"
            )
        self._log_port_owner("SerialManager")
        self.log.line(f"Opened {self.port_name} @ {self.baud} Bd")
        self.sm.init_tnc()
        if not self._wait_until(
            lambda: self.sm.is_verbose_mode or self.sm.is_host_mode, timeout=8.0
        ):
            raise HWCheckError(
                "TNC did not respond to wakeup -- the port itself opened "
                "OK, so this could be: the port still held/shared "
                "elsewhere (a previous hw_check.py left running, or "
                "pk232py itself connected?), the wrong baud rate, or a "
                "bad cable/TNC power state -- check port, baud rate and "
                "cable"
            )
        if self.sm.is_host_mode:
            raise HWCheckError(
                "TNC is already in Host Mode. hw_check needs to start from "
                "verbose mode - power-cycle the TNC (or exit Host Mode in "
                "the application first) and try again."
            )
        self.log.line("TNC in verbose mode")
        device_line = format_device_line(
            self.sm.tnc_release, self.sm.has_pactor, self.sm.tnc_defaults,
        )
        self.log.device_line = device_line
        self.log.line(device_line)

    def disconnect(self) -> None:
        if not self.sm.is_connected:
            return
        if self.sm.is_host_mode:
            self.sm.exit_host_mode()
            self._wait_until(lambda: not self.sm.is_host_mode, timeout=5.0)
        self.sm.disconnect_port()
        self._log_port_owner("none", " (released)")
        self.log.line("Disconnected")

    def enter_host_mode(self) -> None:
        if self.sm.is_host_mode:
            return
        self._log_port_owner(
            "hostmode subprocess",
            " (SerialManager handing off for the HOST 3 handshake)",
        )
        self.sm.enter_host_mode()
        if not self._wait_until(lambda: self.sm.is_host_mode, timeout=10.0):
            raise HWCheckError("Could not enter Host Mode")
        self._log_port_owner(
            "SerialManager", " (fresh port object after Host Mode entry)"
        )
        self.log.line("Host Mode entered")

    def exit_host_mode(self) -> None:
        if not self.sm.is_connected or not self.sm.is_host_mode:
            return
        self.sm.exit_host_mode()
        self._wait_until(lambda: not self.sm.is_host_mode, timeout=5.0)
        self.log.line("Host Mode exited")

    # -- Verbose-mode command/response --------------------------------------

    def verbose_bytes(self, cmd: bytes, timeout: float = 3.0) -> str:
        """Send exact bytes in verbose mode, return the TNC's raw response
        text. Used both for plain queries and for replaying an exact
        ParamsUploader-built command."""
        if self.dry_run:
            self.log.line(f"[dry-run] >> {cmd!r}")
            return ""
        del self._raw_buf[:]
        self.log.line(f">> {cmd!r}")
        self.sm.write_verbose_wait(cmd, timeout=timeout)
        self._pump(0.2)
        resp = bytes(self._raw_buf).decode("ascii", errors="replace")
        self.log.line(f"<< {resp!r}")
        return resp

    def verbose(self, text: str, timeout: float = 3.0) -> str:
        """Send one verbose-mode line, e.g. "PTHUFF" or "PTHUFF ON"."""
        return self.verbose_bytes(f"{text}\r\n".encode("ascii"), timeout=timeout)

    def query(self, name: str, timeout: float = 3.0) -> str:
        return self.verbose(name, timeout=timeout)

    def set_verbose(self, name: str, value: str, timeout: float = 3.0) -> str:
        return self.verbose(f"{name} {value}", timeout=timeout)

    def read_until_idle(self, idle: float = 1.5, max_total: float = 10.0) -> bytes:
        """Read from the same raw_data_received-fed _raw_buf as
        verbose_bytes(), but stop on an IDLE GAP instead of the normal
        'cmd:' prompt (P20 Teil B). The local MailDrop session uses its
        own prompt, unknown in advance - write_verbose_wait() would wait
        for 'cmd:' forever. Does NOT clear the buffer first, so callers
        control when a fresh read window starts (send_and_read_until_idle()
        below does that for the normal case)."""
        if self.dry_run:
            return b""
        deadline = time.monotonic() + max_total
        last_len = len(self._raw_buf)
        idle_since = time.monotonic()
        while time.monotonic() < deadline:
            self._pump(0.05)
            cur_len = len(self._raw_buf)
            if cur_len != last_len:
                last_len = cur_len
                idle_since = time.monotonic()
            elif time.monotonic() - idle_since >= idle:
                break
        return bytes(self._raw_buf)

    def send_and_read_until_idle(
        self, data: bytes, note: str = "",
        idle: float = 1.5, max_total: float = 10.0,
    ) -> bytes:
        """Write raw bytes with write_verbose() (no 'cmd:' wait) and read
        the response with read_until_idle() (P20 Teil B) - the MailDrop
        recorder's one send/receive primitive. Logs hex + text-with-
        visible-controls in both directions, matching the protocol format
        Teil B asks for."""
        label = f"  ({note})" if note else ""
        if self.dry_run:
            self.log.line(
                f"[dry-run] >> hex={data.hex(' ').upper()} "
                f"text={format_bytes_with_controls(data)}{label}"
            )
            return b""
        del self._raw_buf[:]
        self.log.line(
            f">> hex={data.hex(' ').upper()} "
            f"text={format_bytes_with_controls(data)}{label}"
        )
        self.sm.write_verbose(data)
        resp = self.read_until_idle(idle=idle, max_total=max_total)
        self.log.line(
            f"<< hex={resp.hex(' ').upper()} "
            f"text={format_bytes_with_controls(resp)}"
        )
        return resp

    def normalize(self) -> None:
        """Bring the TNC to a known, quiet verbose-mode state (P21.2/P34).

        Called at the START of every hardware subcommand that assumes a
        clean verbose-mode state (t17/t111/t112/mi/siam/maildrop), and
        again after any operator-driven power-cycle within a session -
        found necessary 22.09.2026, when a still-running SIAM session
        wrote asynchronous results into the middle of unrelated
        responses (XMITOK, mailbox output) with no warning at all.

        0. confirm_command_prompt() (P34.1): verifies a 'cmd:' prompt,
           with two resync stages, before anything else in here (or in
           any caller) sends a single further verbose command. Raises
           HWCheckError - aborting the whole subcommand - if the TNC
           still hasn't answered 'cmd:' after both resyncs.
        1. Ctrl-C ($03, the verbose-mode COMMAND character) then CR -
           drops back to the top-level command interpreter regardless of
           what was running, via the idle-gap read (its prompt is not
           assumed). (Folded into step 0 above - the same Ctrl-C+CR IS
           confirm_command_prompt()'s first attempt.)
        2. PACKET - leaves whichever operating mode was active WITHOUT
           entering Host Mode. SIAM in particular does NOT stop analysing
           on its own; only selecting a different mode does.
        3. Reads for 2s watching for further asynchronous output - a mode
           that ignored steps 1/2 would still show up here. Logged as a
           warning, never fatal (this is diagnostic, not a hard gate).
        4. Queries MYCALL. The PK-232 has no RAM buffer battery
           (CLAUDE.md) and resets to the factory value 'PK232' on every
           power-off; if seen, MYCALL is set back from the loaded
           AppConfig and the factory-state finding is logged. None (the
           query went unanswered) now aborts (P34.2, require_query_value())
           rather than silently skipping the reset - a state query, not
           an ordinary parameter.
        5. Queries XMITOK, same None-aborts rule (P34.2) - this used to
           be queried separately by each subcommand AFTER normalize();
           it belongs here because the "never transmits on the air"
           promise every subcommand makes depends on actually knowing
           it, not on guessing. Stored as self.xmitok for callers that
           want to warn if it is ON.
        """
        if self.dry_run:
            self.log.line(
                "[dry-run] would normalize: confirm cmd: (Ctrl-C+CR, with "
                "up to two resync stages), PACKET, watch 2s for async "
                "output, check MYCALL (factory 'PK232' -> reset from "
                "config) and XMITOK - aborting if either goes unanswered"
            )
            return

        self.log.line("Normalizing TNC state (P21.2/P34.1)")
        confirm_command_prompt(
            lambda data, note: self.send_and_read_until_idle(data, note=note),
            self.sm.recovery,
            self.log,
        )
        self.verbose("PACKET")

        del self._raw_buf[:]
        extra = self.read_until_idle(idle=2.0, max_total=2.0)
        if extra:
            self.log.line(
                f"WARNING: asynchronous output continued after PACKET -- "
                f"a mode may still be running: {extra!r}"
            )

        mycall = require_query_value(
            parse_query_value("MYCALL", self.query("MYCALL")), "MYCALL",
        )
        self.log.line(f"MYCALL: {mycall!r}")
        if mycall.strip().upper() == "PK232":
            self.log.line("factory state detected -- no RAM battery")
            configured = self.app_config.hf_packet.mycall
            if configured and configured.upper() != "NOCALL":
                self.set_verbose("MYCALL", configured.upper())
                self.log.line(f"MYCALL set to {configured.upper()!r} from config")

        self.xmitok = require_query_value(
            parse_query_value("XMITOK", self.query("XMITOK")), "XMITOK",
            "the 'never transmits on the air' promise cannot be verified "
            "without it",
        )
        self.log.line(f"XMITOK: {self.xmitok!r}")

    # -- Host-mode frames ----------------------------------------------------

    def drain_pending_frames(self, settle: float = 0.3) -> None:
        """Log and discard any frames already queued before the first real
        query (P16.2) - e.g. the stale 'HP\\x00' poll-ack from Host Mode
        entry that made T17 misread its own PX/PS responses on 21.09.2026.
        """
        if self.dry_run:
            return
        captured: list = []
        self.sm.frame_received.connect(captured.append)
        try:
            self._pump(settle)
        finally:
            self.sm.frame_received.disconnect(captured.append)
        for f in captured:
            self.log.line(
                f"INFO: discarded pending frame ctl=0x{f.ctl:02X} "
                f"ch={f.channel} data={f.data!r} text={f.text!r}"
            )

    def query_host(self, mnemonic: bytes, timeout: float = 2.0):
        """Send a Host Mode query (mnemonic, no args) and return the ONE
        frame whose payload starts with *mnemonic* - not just the first
        frame to arrive (P16.2 - see select_response_frame()). Returns None
        if no matching frame showed up inside *timeout*."""
        if self.dry_run:
            self.log.line(f"[dry-run] would send Host Mode query {mnemonic!r}")
            return None
        captured: list = []
        self.sm.frame_received.connect(captured.append)
        try:
            self.log.line(f">> HOST query {mnemonic!r}")
            self.sm.send_command(mnemonic, b"")
            self._pump(timeout)
        finally:
            self.sm.frame_received.disconnect(captured.append)
        for f in captured:
            self.log.line(
                f"<< ctl=0x{f.ctl:02X} ch={f.channel} data={f.data!r} "
                f"text={f.text!r}"
            )
        match = select_response_frame(mnemonic, captured)
        for f in captured:
            if f is not match:
                self.log.line(f"INFO: unrelated frame {f.data.hex()}")
        return match

    def probe_mdcheck_mnemonic(self, mnemonic: bytes, seconds: float = 1.5) -> list:
        """Send one bare 'M?' Host Mode query (mdcheck_scan, P26.2) and
        return EVERY frame captured for *seconds*.

        Unlike query_host(), this does NOT filter to frames whose payload
        starts with *mnemonic* - a genuine MDCHECK hit is the mailbox
        login prompt's own text, which looks nothing like a mnemonic
        echo, so is_mdcheck_scan_hit() needs the full, unfiltered capture.
        """
        if self.dry_run:
            frame_bytes = build_command(mnemonic, b"")
            self.log.line(
                f"[dry-run] >> {frame_bytes.hex(' ').upper()}  "
                f"(mdcheck_scan: {mnemonic!r})"
            )
            return []
        captured: list = []
        self.sm.frame_received.connect(captured.append)
        try:
            self.log.line(f">> HOST query {mnemonic!r} (mdcheck_scan)")
            self.sm.send_command(mnemonic, b"")
            self._pump(seconds)
        finally:
            self.sm.frame_received.disconnect(captured.append)
        for f in captured:
            self.log.line(
                f"<< ctl=0x{f.ctl:02X} ch={f.channel} data={f.data!r} "
                f"text={f.text!r}"
            )
        return captured

    def send_frame(self, frame: bytes, note: str = "") -> None:
        """Send one already-built Host Mode frame exactly as the app would.

        mode_manager.py sends every frame from get_activate_frames() /
        get_init_frames() as ``send_command(frame[2:4], frame[4:-1])`` (see
        ModeManager.set_mode() / _send_init_frames()) - this mirrors that,
        so siam/t112 replay the REAL frames the mode classes build, never
        reconstructed ones (P17.1/P17.3).
        """
        label = f"  ({note})" if note else ""
        if self.dry_run:
            self.log.line(f"[dry-run] >> {frame.hex(' ').upper()}{label}")
            return
        self.log.line(f">> HOST frame {frame.hex(' ').upper()}{label}")
        self.sm.send_command(frame[2:4], frame[4:-1])

    def send_channel_frame(self, channel: int, frame: bytes, note: str = "") -> None:
        """Like send_frame(), for a channel-specific ($4x) frame built
        by e.g. HostModeProtocol.cmd_link_status()/.cmd_connect() (P65)
        - dispatches via SerialManager.send_channel_command(), the
        channel-aware counterpart send_command() (send_frame()'s own
        target) has no use for. Same frame[2:4]/frame[4:-1] split as
        send_frame() - the channel itself is already encoded in the
        frame's own CTL byte, but send_channel_command() needs it
        again as a plain int to rebuild that same CTL byte itself.
        """
        label = f"  ({note})" if note else ""
        if self.dry_run:
            self.log.line(f"[dry-run] >> {frame.hex(' ').upper()}{label}")
            return
        self.log.line(f">> HOST frame {frame.hex(' ').upper()}{label}")
        self.sm.send_channel_command(channel, frame[2:4], frame[4:-1])

    def query_channel_frame(
        self, channel: int, frame: bytes, note: str = "", timeout: float = 1.0,
    ) -> list:
        """Send an already-built channel-specific frame (P65's
        cmd_link_status()) and return EVERY frame captured for
        *timeout* seconds, unfiltered - LINK_STATUS responses ($40-$4E)
        are misclassified as CMD_RESP by _make_host_frame() (Backlog:
        '_make_host_frame() misclassifies LINK_STATUS as CMD_RESP'),
        so this must never filter by .kind, only log the raw bytes for
        decode_link_status() to work with afterwards."""
        if self.dry_run:
            self.send_channel_frame(channel, frame, note=note)
            return []
        captured: list = []
        self.sm.frame_received.connect(captured.append)
        try:
            self.send_channel_frame(channel, frame, note=note)
            self._pump(timeout)
        finally:
            self.sm.frame_received.disconnect(captured.append)
        for f in captured:
            self.log.line(
                f"<< ctl=0x{f.ctl:02X} ch={f.channel} data={f.data!r} "
                f"text={f.text!r}"
            )
        return captured

    def send_maildrop_host_frame(self, data: bytes, seconds: float = 3.0) -> list:
        """Send one MailDrop-over-Host-Mode data frame (CTL $60, P24.2)
        and capture every frame the reader thread decodes for *seconds*.

        Uses write_verbose() to write the already-built frame's exact
        bytes - despite its name, that method has no verbose-mode-
        specific logic at all (just a connectivity check before a raw
        write), and SerialManager has no send_*() that builds a $60
        frame; send_frame()'s frame[2:4]/frame[4:-1] split assumes a
        $4F-style mnemonic+args frame, which this is not. The frame
        TYPE the response comes back as is exactly what this measures -
        capture and log everything, never filter.
        """
        frame = build_maildrop_host_frame(data)
        if self.dry_run:
            self.log.line(
                f"[dry-run] >> {frame.hex(' ').upper()}  (maildrop_host: {data!r})"
            )
            return []
        self.log.line(f">> {frame.hex(' ').upper()}  (maildrop_host: {data!r})")
        captured: list = []
        self.sm.frame_received.connect(captured.append)
        try:
            self.sm.write_verbose(frame)
            self._pump(seconds)
        finally:
            self.sm.frame_received.disconnect(captured.append)
        for f in captured:
            self.log.line(
                f"<< ctl=0x{f.ctl:02X} ({classify_maildrop_host_ctl(f.ctl)}) "
                f"ch={f.channel} data={f.data!r} text={f.text!r}"
            )
        return captured

    def send_data_channel0(self, text: str) -> None:
        if self.dry_run:
            self.log.line(f"[dry-run] would TRANSMIT on channel 0: {text!r}")
            return
        self.log.line(f">> TX ch0: {text!r}")
        self.sm.send_data(text.encode("ascii", errors="replace"), channel=0)

    def send_data_channel(self, channel: int, text: str) -> None:
        """Like send_data_channel0(), any channel - P65's A.7 sends on
        whichever channel actually carries the connection, not always
        channel 0 (which is reserved for UI/unproto frames, CLAUDE.md's
        own 'channel 0 is the UI channel' rule - a real Packet
        connection is never on it)."""
        if self.dry_run:
            self.log.line(
                f"[dry-run] would TRANSMIT on channel {channel}: {text!r}"
            )
            return
        self.log.line(f">> TX ch{channel}: {text!r}")
        self.sm.send_data(text.encode("ascii", errors="replace"), channel=channel)


def confirm_tx(prompt: str, read_line: Callable[[str], str] = input) -> bool:
    """The one gate every actual transmission must pass (hard rule #3).

    P62a: re-asks until the answer is exactly 'y', 'n', or empty,
    instead of silently treating anything else as "no" - found
    necessary 27.09.2026 (Device B): a paste that ran past its own
    terminator (fixed at the root by read_pasted_block() below) left a
    stray decoder line sitting in the input buffer, which a single
    input() call here would have silently read as the y/N answer to
    the NEXT round's transmit confirmation.

    *read_line* is injectable (same reasoning as read_pasted_block()
    below) so this is unit-testable without mocking input() itself.
    """
    print()
    print("*** THIS WILL KEY THE TRANSMITTER ***")
    print(prompt)
    while True:
        answer = read_line("Proceed? [y/N] ").strip().lower()
        if answer in ("y", "n", ""):
            return answer == "y"
        print(f"Please answer y or n (got {answer!r}) - asking again.")


def read_pasted_block(
    prompt: str, read_line: Callable[[], str] = input,
) -> str:
    """The ONE place in this file that reads a multi-line decoder paste
    (P62a, Teil A). Ends on a line containing exactly '.', never a
    blank line - Direwolf inserts blank lines of its own between
    decoded packets, so a blank-line-terminated read (the original P62
    design) truncates a multi-frame paste mid-block: exactly what
    happened to T139 R4/R5 on real hardware (27.09.2026, Device B) -
    the rest of the paste ran on into the next question, the next
    confirm_tx() prompt, and finally into the shell itself. Blank
    lines are content, not a terminator.

    *read_line* is injectable (same reasoning as run_maildrop_
    interactive()'s own read_line callable) so this is unit-testable
    without mocking input() itself.
    """
    print(prompt)
    lines: list[str] = []
    while True:
        line = read_line()
        if line == ".":
            break
        lines.append(line)
    return "\n".join(lines)


# ===========================================================================
# The four tests
# ===========================================================================

def test_t17(session: Session, log: RunLog) -> None:
    log.line("--- T17: PASSALL mnemonic (PS vs PX) -- Host Mode query only ---")
    session.normalize()
    log.line(
        "Two-letter mnemonics only exist in Host Mode (P15 finding: 'PX' and "
        "'PS' both answer '?What?' in verbose mode)"
    )
    if session.dry_run:
        log.line("[dry-run] would enter Host Mode, send these query frames, "
                  "log the raw response frames, then exit Host Mode:")
        for mnemonic in (b"PX", b"PS"):
            frame_bytes = build_command(mnemonic, b"")
            log.line(
                f"[dry-run]   >> {frame_bytes.hex(' ').upper()}  "
                f"(SOH $4F {mnemonic.decode()} ETB)"
            )
        log.result("T17", "INFO", "dry-run, nothing sent")
        return

    session.enter_host_mode()
    try:
        # A stale 'HP\x00' poll-ack from Host Mode entry can still be queued
        # here (T86, 21.09.2026) - drop it before the first real query so it
        # can never be mistaken for the PX/PS answer.
        session.drain_pending_frames()
        px_frame = session.query_host(b"PX")
        ps_frame = session.query_host(b"PS")
    finally:
        session.exit_host_mode()

    px_text = px_frame.text if px_frame else "<no matching response>"
    ps_text = ps_frame.text if ps_frame else "<no matching response>"

    if px_frame is None or ps_frame is None:
        log.result(
            "T17", "INCONCLUSIVE",
            f"no matching response frame in Host Mode -- PX={px_text!r}, "
            f"PS={ps_text!r}"
        )
        return

    verdict = evaluate_t17(px_text, ps_text)
    if verdict["passall_mnemonic"] == "PX":
        log.result(
            "T17", "PASS",
            f"PASSALL is PX (PX={px_text!r}, PS={ps_text!r}) - matches the "
            f"app's toggle (packet_screen.py toggle_map, fixed P16/T86)"
        )
    elif verdict["passall_mnemonic"] == "PS":
        log.result(
            "T17", "FAIL",
            f"PASSALL is PS, not PX (PX={px_text!r}, PS={ps_text!r}) - the "
            f"app's PASSALL toggle sends the wrong mnemonic, see "
            f"packet_screen.py toggle_map / Backlog.md"
        )
    else:
        log.result(
            "T17", "INCONCLUSIVE",
            f"could not classify from responses (PX={px_text!r}, PS={ps_text!r})"
        )


def test_t103(session: Session, log: RunLog, app_config: AppConfig) -> None:
    log.line("--- T103: does USERS reach the TNC via the uploader? ---")
    real_users = app_config.hf_packet.users

    test_cfg = dataclasses.replace(app_config)
    test_cfg.hf_packet = dataclasses.replace(app_config.hf_packet, users=4)
    commands = ParamsUploader(
        serial=None, config=test_cfg
    )._build_commands(has_pactor=True)

    if session.dry_run:
        log.line("[dry-run] would send the full parameter upload with USERS=4:")
        for c in commands:
            log.line(f"  {c!r}")
        log.line(f"[dry-run] would then restore USERS to {real_users}")
        log.result("T103", "INFO", "dry-run, nothing sent")
        return

    log.line(
        f"Sending the full parameter upload (USERS=4, everything else "
        f"matches the saved configuration) - {len(commands)} commands"
    )

    def do_upload() -> None:
        error_lines: list[str] = []
        has_pactor = session.sm.has_pactor
        for cmd in commands:
            resp = session.verbose_bytes(cmd)
            for err in scan_for_tnc_errors(resp.splitlines()):
                error_lines.append(f"{cmd!r} -> {err!r}")
        after = parse_query_value("USERS", session.query("USERS"))
        log.line(f"USERS after upload: {after!r}")
        if after == "4":
            log.result("T103", "PASS", "USERS 4 confirmed after upload")
        else:
            log.result("T103", "FAIL", f"expected USERS to read back 4, got {after!r}")
        if error_lines:
            for e in error_lines:
                log.result("upload command error", "FAIL", e)
        else:
            log.line(
                f"All {len(commands)} upload commands acknowledged without "
                f"a '?' error response"
            )
        if not has_pactor:
            log.line("Note: TNC reports no PACTOR option - PACTOR-only "
                      "commands were skipped by the uploader")

    run_with_restore(
        command="USERS",
        query=lambda: session.query("USERS"),
        restore=lambda v: session.set_verbose("USERS", v),
        action=do_upload,
        log=log,
    )


def test_pthuff(session: Session, log: RunLog, app_config: AppConfig) -> None:
    log.line("--- PTHUFF: response to what the uploader actually sends ---")
    sent_cmd = ParamsUploader._bool("PTHUFF", app_config.pactor.pthuff)

    if session.dry_run:
        log.line(f"[dry-run] would query PTHUFF, send {sent_cmd!r}, query again")
        log.result("PTHUFF", "INFO", "dry-run, nothing sent")
        return

    if not session.sm.has_pactor:
        log.result("PTHUFF", "INFO", "no PACTOR option")
        return

    before_response = session.query("PTHUFF")
    fmt = detect_pthuff_format(before_response)
    log.line(f"PTHUFF before: {before_response!r} (looks like: {fmt})")

    def do_set() -> None:
        session.verbose_bytes(sent_cmd)
        after = parse_query_value("PTHUFF", session.query("PTHUFF"))
        log.line(f"PTHUFF after {sent_cmd!r}: {after!r}")
        if fmt == "numeric":
            log.result(
                "PTHUFF", "FAIL",
                f"TNC reports a numeric value ({before_response!r}) but the "
                f"uploader sends ON/OFF ({sent_cmd!r}) - type mismatch "
                f"confirmed (see PACTORConfig.pthuff / Backlog.md)"
            )
        elif fmt == "on_off":
            log.result("PTHUFF", "PASS", "TNC's own format is ON/OFF, matches the uploader")
        else:
            log.result(
                "PTHUFF", "INCONCLUSIVE",
                f"could not classify response {before_response!r}"
            )

    run_with_restore(
        command="PTHUFF",
        query=lambda: session.query("PTHUFF"),
        restore=lambda v: session.set_verbose("PTHUFF", v),
        action=do_set,
        log=log,
    )


def test_t101(session: Session, log: RunLog) -> None:
    log.line("--- T101: UI frame on unconnected channel 0 ---")
    print()
    print("T101 TRANSMITS on the air. Before continuing:")
    print("  - Tune a second receiver (SDR + Direwolf/multimon-ng or similar)")
    print("    to the TNC's current frequency and start its AX.25 decoder.")
    print("  - Use low transmit power, or a dummy load.")

    if session.dry_run:
        log.line(
            "[dry-run] would query UNPROTO/MONITOR, set UNPROTO TEST1, enter "
            "Host Mode, ask to confirm, TRANSMIT a UI frame on channel 0, "
            "ask the operator what the decoder showed, repeat with TEST2, "
            "then verify UNPROTO was restored (MONITOR is only read, never "
            "changed)"
        )
        log.result("T101", "INFO", "dry-run, nothing sent")
        return

    if input("Ready to continue? [y/N] ").strip().lower() != "y":
        log.result("T101", "INFO", "skipped by operator")
        return

    # MONITOR is only read for context here - this test never changes it,
    # so there is nothing to restore.
    log.line(
        f"MONITOR (unchanged): "
        f"{parse_query_value('MONITOR', session.query('MONITOR'))!r}"
    )

    targets_seen: dict[str, Optional[str]] = {"A": None, "B": None}

    def run_rounds() -> None:
        for round_name, path in (("A", "TEST1"), ("B", "TEST2")):
            session.verbose(f"UNPROTO {path}")
            session.enter_host_mode()
            try:
                text = (
                    f"PK232PY T101 {round_name} "
                    f"{datetime.datetime.now():%H:%M:%S}"
                )
                if not confirm_tx(
                    f"Round {round_name}: transmit a UI frame on the "
                    f"unconnected channel 0, UNPROTO path '{path}'.\n"
                    f"Text: {text!r}"
                ):
                    log.result("T101", "INFO", f"round {round_name} skipped by operator")
                    return
                session.send_data_channel0(text)
                captured: list = []
                session.sm.frame_received.connect(captured.append)
                try:
                    session._pump(2.0)
                finally:
                    session.sm.frame_received.disconnect(captured.append)
                for f in captured:
                    log.line(
                        f"<< ctl=0x{f.ctl:02X} ch={f.channel} "
                        f"data={f.data!r} text={f.text!r}"
                    )
                monitor_echoes = [f for f in captured if f.kind.name == "RX_MONITOR"]
                error_frames = [
                    f for f in captured
                    if f.kind.name in ("STATUS_ERR",) and f.cmd_error not in (0, None)
                ]
                log.line(
                    f"Round {round_name}: {len(monitor_echoes)} monitor "
                    f"($3F) frame(s), {len(error_frames)} error frame(s) seen"
                )
                answer = input(
                    f"Did the second decoder show a UI frame with "
                    f"destination '{path}'? [y/n] "
                ).strip().lower()
                targets_seen[round_name] = path if answer == "y" else None
            finally:
                session.exit_host_mode()

    # run_rounds() enters/exits Host Mode per round and always exits it in
    # its own finally block before returning or raising, so by the time
    # run_with_restore() restores UNPROTO the TNC is already back in
    # verbose mode.
    run_with_restore(
        command="UNPROTO",
        query=lambda: session.query("UNPROTO"),
        restore=lambda v: session.set_verbose("UNPROTO", v),
        action=run_rounds,
        log=log,
    )

    verdict = evaluate_t101(targets_seen["A"], targets_seen["B"])
    log.result(
        "T101", verdict,
        f"round A destination seen={targets_seen['A']!r}, "
        f"round B destination seen={targets_seen['B']!r}"
    )


def test_siam(session: Session, log: RunLog, seconds: float = 60.0) -> None:
    log.line("--- SIAM: unfiltered Host Mode frame capture (P17.1) ---")
    session.normalize()
    log.line(
        "Module docstring vs. handle_frame() disagree on frame type ($4F "
        "CMD_RESP vs. $50 LINK_MSG) and output format (STABO manual vs. "
        "mockup) - this test logs EVERYTHING unfiltered, no assumption."
    )
    mode = SignalMode()
    frames = mode.get_activate_frames() + mode.get_init_frames()

    if session.dry_run:
        log.line(
            "[dry-run] would ask the operator to tune a known FSK signal "
            "and record its mode/baud/shift, enter Host Mode, send the "
            "real SignalMode activation frames, then log every incoming "
            f"frame unfiltered for {seconds:.0f}s:"
        )
        for frame in frames:
            session.send_frame(frame, note="SignalMode")
        log.result("SIAM", "INFO", "dry-run, nothing sent")
        return

    print()
    print("SIAM measurement -- receive only, nothing is transmitted.")
    print(
        "Tune the receiver to a KNOWN FSK signal first (Amateur RTTY "
        "45 Bd / 170 Hz shift is the simplest case) so the result is "
        "comparable."
    )
    known_mode  = input("Known operating mode of the tuned signal: ").strip()
    known_baud  = input("Known baud rate: ").strip()
    known_shift = input("Known shift (Hz): ").strip()
    log.line(
        f"Operator-reported reference signal: mode={known_mode!r} "
        f"baud={known_baud!r} shift={known_shift!r}"
    )
    if input("Ready to continue? [y/N] ").strip().lower() != "y":
        log.result("SIAM", "INFO", "skipped by operator")
        return

    captured: list = []
    session.enter_host_mode()
    try:
        session.drain_pending_frames()
        for frame in frames:
            session.send_frame(frame, note="SignalMode")

        session.sm.frame_received.connect(captured.append)
        try:
            elapsed = 0.0
            while elapsed < seconds:
                step = min(10.0, seconds - elapsed)
                session._pump(step)
                elapsed += step
                log.line(
                    f"... {len(captured)} frame(s) so far "
                    f"({elapsed:.0f}/{seconds:.0f}s)"
                )
        finally:
            session.sm.frame_received.disconnect(captured.append)
    finally:
        # Ctrl-C during the capture loop still lands here before the
        # KeyboardInterrupt propagates - Host Mode is always left cleanly.
        session.exit_host_mode()

    summary = summarize_siam_frames(captured)
    log.line("Frame counts by kind:")
    for kind_name, count in sorted(summary["counts"].items()):
        log.line(f"  {kind_name}: {count}")
    if summary["candidates"]:
        log.line("Frames that look like an analysis result:")
        for f in summary["candidates"]:
            log.line(
                f"  ctl=0x{f.ctl:02X} kind={f.kind.name} ch={f.channel} "
                f"hex={f.data.hex(' ').upper()} text={f.text!r}"
            )
    else:
        log.line(
            "No frame looked like an analysis result (no 'Baud' / known "
            "mode text in any captured frame)"
        )
    log.result(
        "SIAM", "INFO",
        f"{len(captured)} frame(s) captured in {seconds:.0f}s -- compare "
        f"the summary above against the known reference signal "
        f"(mode={known_mode!r} baud={known_baud!r} shift={known_shift!r}) "
        f"and record the comparison in Testplan.md"
    )


def test_t111(session: Session, log: RunLog) -> None:
    log.line("--- T111: does PX toggle PASSALL while PS (PASS) stays put? ---")
    session.normalize()
    mnemonic = PASSALL_TOGGLE_MNEMONIC

    if session.dry_run:
        log.line(
            f"[dry-run] would query PX and PS, send {mnemonic.decode()} Y, "
            f"query PX and PS again, then restore PX to its original value:"
        )
        for m in (b'PX', b'PS'):
            log.line(f"[dry-run]   >> {build_command(m).hex(' ').upper()}")
        log.line(
            f"[dry-run]   >> {build_command(mnemonic, b'Y').hex(' ').upper()}"
            f"  ({mnemonic.decode()} Y)"
        )
        log.result("T111", "INFO", "dry-run, nothing sent")
        return

    session.enter_host_mode()
    try:
        session.drain_pending_frames()
        px_before = host_query_value(session.query_host(b'PX'), b'PX')
        ps_before = host_query_value(session.query_host(b'PS'), b'PS')
        log.line(f"Before: PX={px_before!r} PS={ps_before!r}")

        if px_before is None or ps_before is None:
            log.result(
                "T111", "INCONCLUSIVE",
                f"no matching PX/PS response before the toggle -- "
                f"PX={px_before!r} PS={ps_before!r}"
            )
            return

        try:
            session.log.line(f">> HOST set {mnemonic!r} Y")
            session.sm.send_command(mnemonic, b'Y')
            session._pump(0.3)

            px_after = host_query_value(session.query_host(b'PX'), b'PX')
            ps_after = host_query_value(session.query_host(b'PS'), b'PS')
            log.line(
                f"After {mnemonic.decode()} Y: PX={px_after!r} "
                f"PS={ps_after!r}"
            )

            if px_after is None or ps_after is None:
                log.result(
                    "T111", "INCONCLUSIVE",
                    f"no matching PX/PS response after the toggle -- "
                    f"PX={px_after!r} PS={ps_after!r}"
                )
                return

            if px_after != px_before and ps_after == ps_before:
                log.result(
                    "T111", "PASS",
                    f"PASSALL toggled ({px_before!r} -> {px_after!r}), "
                    f"PASS unchanged ({ps_after!r})"
                )
            elif ps_after != ps_before:
                log.result(
                    "T111", "FAIL",
                    f"PASS changed too ({ps_before!r} -> {ps_after!r}) -- "
                    f"{mnemonic.decode()} is masking PASS, not toggling "
                    f"PASSALL"
                )
            else:
                log.result(
                    "T111", "FAIL",
                    f"PX did not change ({px_before!r} -> {px_after!r})"
                )
        finally:
            session.log.line(f">> HOST restore {mnemonic!r} {px_before}")
            session.sm.send_command(mnemonic, px_before.encode("ascii"))
            session._pump(0.3)
            px_restored = host_query_value(session.query_host(b'PX'), b'PX')
            if px_restored == px_before:
                log.line(f"PX restored to {px_before!r}")
            else:
                log.result(
                    "T111", "FAIL",
                    f"restore of PX failed -- TNC now reports "
                    f"{px_restored!r}, expected {px_before!r} -- set it by "
                    f"hand: PX {px_before}"
                )
    finally:
        session.exit_host_mode()


def test_t112(session: Session, log: RunLog, app_config: AppConfig) -> None:
    log.line("--- T112: VHF -> HF Packet parameter carry-over ---")
    session.normalize()
    hf_maxframe = str(app_config.hf_packet.maxframe)
    hf_slottime = str(app_config.hf_packet.slottime)
    frames = build_t112_frame_sequence(
        app_config.hf_packet.maxframe, app_config.hf_packet.slottime
    )

    if session.dry_run:
        log.line(
            "[dry-run] would query MAXFRAME/SLOTTIME/VHF/HBAUD, pre-set "
            f"MAXFRAME {_T112_NEUTRAL_MAXFRAME} / SLOTTIME "
            f"{_T112_NEUTRAL_SLOTTIME} (matches neither HF nor VHF, so "
            "each parameter's result is meaningful on its own -- P18.3), "
            "enter Host Mode, send this exact frame sequence (order taken "
            "from _on_mode_selected() in main_window.py: VHF activate+init, "
            "VHF OFF, HF activate+init), exit Host Mode, query MAXFRAME/"
            "SLOTTIME again, then restore all four:"
        )
        for frame in frames:
            session.send_frame(frame)
        log.result("T112", "INFO", "dry-run, nothing sent")
        return

    commands = ["MAXFRAME", "SLOTTIME", "VHF", "HBAUD"]
    originals: dict[str, Optional[str]] = {
        cmd: parse_query_value(cmd, session.query(cmd)) for cmd in commands
    }
    missing = [c for c in commands if originals[c] is None]
    if missing:
        log.result(
            "T112", "SKIPPED",
            f"original value(s) not parseable via parse_query_value() -- "
            f"not touching them: {missing}"
        )
        return

    log.line(f"Originals: {originals}")
    log.line(
        f"HF Packet config (reference values): MAXFRAME={hf_maxframe} "
        f"SLOTTIME={hf_slottime}"
    )

    try:
        # Start from values that match NEITHER HF nor VHF (P18.3) - the
        # first hardware run's MAXFRAME result proved nothing, because it
        # already happened to equal VHF's own value (4) before the switch.
        log.line(
            f"Pre-setting MAXFRAME {_T112_NEUTRAL_MAXFRAME} / SLOTTIME "
            f"{_T112_NEUTRAL_SLOTTIME} (neutral -- matches neither HF nor VHF)"
        )
        session.set_verbose("MAXFRAME", _T112_NEUTRAL_MAXFRAME)
        session.set_verbose("SLOTTIME", _T112_NEUTRAL_SLOTTIME)

        session.enter_host_mode()
        try:
            session.drain_pending_frames()
            for frame in frames:
                session.send_frame(frame)
            session._pump(0.5)
        finally:
            session.exit_host_mode()

        maxframe_after = parse_query_value("MAXFRAME", session.query("MAXFRAME"))
        slottime_after = parse_query_value("SLOTTIME", session.query("SLOTTIME"))
        log.line(
            f"After VHF->HF switch: MAXFRAME={maxframe_after!r} "
            f"SLOTTIME={slottime_after!r}"
        )

        # Judged separately (P18.3) - a combined verdict had hidden
        # MAXFRAME's own result behind SLOTTIME's in the first run.
        for label, value_after, hf_value, vhf_value in (
            ("MAXFRAME", maxframe_after, hf_maxframe, _VHF_MAXFRAME),
            ("SLOTTIME", slottime_after, hf_slottime, _VHF_SLOTTIME),
        ):
            verdict = evaluate_t112_param(value_after, hf_value, vhf_value)
            if verdict == "PASS":
                log.result(
                    f"T112 {label}", "PASS",
                    f"{label}={value_after!r} matches HF Packet's own "
                    f"config -- no gap"
                )
            elif verdict == "FAIL":
                log.result(
                    f"T112 {label}", "FAIL",
                    f"{label}={value_after!r} -- VHF's value ({vhf_value}) "
                    f"leaked into HF Packet, gap confirmed"
                )
            else:
                log.result(
                    f"T112 {label}", "INCONCLUSIVE",
                    f"{label}={value_after!r} (neither HF's {hf_value!r} "
                    f"nor VHF's {vhf_value!r})"
                )
    finally:
        for cmd in commands:
            verify_restore(
                cmd,
                lambda c=cmd: session.query(c),
                lambda v, c=cmd: session.set_verbose(c, v),
                originals[cmd],
                log,
            )


def test_mi(session: Session, log: RunLog) -> None:
    log.line("--- MI: does the MailDrop button actually query MFILTER? ---")
    session.normalize()
    mnemonic = MI_PROBE_MNEMONIC

    if session.dry_run:
        log.line(
            f"[dry-run] would enter Host Mode, query {mnemonic.decode()} "
            f"(no argument), exit Host Mode, then verbose-query MFILTER:"
        )
        log.line(f"[dry-run]   >> {build_command(mnemonic).hex(' ').upper()}")
        log.result("MI", "INFO", "dry-run, nothing sent")
        return

    session.enter_host_mode()
    try:
        session.drain_pending_frames()
        mi_frame = session.query_host(mnemonic)
    finally:
        session.exit_host_mode()

    mi_value = host_query_value(mi_frame, mnemonic)
    log.line(f"{mnemonic.decode()} (Host Mode): {mi_value!r}")

    mfilter_value = parse_query_value("MFILTER", session.query("MFILTER"))
    log.line(f"MFILTER (verbose): {mfilter_value!r}")

    verdict = evaluate_mi_probe(mi_value, mfilter_value)
    if verdict == "PASS":
        log.result(
            "MI", "PASS",
            f"MI ({mi_value!r}) does not match MFILTER ({mfilter_value!r}) "
            f"-- no evidence MI is actually MFILTER"
        )
    elif verdict == "FAIL":
        log.result(
            "MI", "FAIL",
            f"MI ({mi_value!r}) matches MFILTER ({mfilter_value!r}) -- MI "
            f"is MFILTER, not MailDrop login; "
            f"main_window._on_packet_maildrop() sends the wrong command "
            f"for the MailDrop button"
        )
    else:
        log.result(
            "MI", "INCONCLUSIVE",
            f"MI={mi_value!r} MFILTER={mfilter_value!r} -- one of the two "
            f"queries did not return a usable value"
        )


def _maildrop_console_prompt(state: str, free: Optional[int]) -> str:
    if state == "ENTRY":
        return "md-text> "
    if state == "MAILBOX":
        return f"md[{free} free]> " if free is not None else "md[mailbox]> "
    return "md> "


def _maildrop_read_line(state: str, free: Optional[int]) -> Optional[str]:
    try:
        return input(_maildrop_console_prompt(state, free))
    except EOFError:
        return None


def _maildrop_leave_mailbox(
    session: Session, log: RunLog, final_state: str, last_sent: Optional[bytes]
) -> None:
    """Close out the mailbox terminal (P21.3 'finally'): if the
    interactive phase ended already at CMD (the safety stop), there is
    nothing to do - the mailbox is already closed. Otherwise send /EX
    first if still in ENTRY (abandon the in-progress message), then B
    (leave the mailbox) - both hardware-confirmed 22.09.2026 ('B' ->
    'cmd:' immediately). Verifies 'cmd:' afterwards; a clear warning if
    that fails, same as before."""
    if final_state == "CMD":
        log.result(
            "MAILDROP", "INFO",
            "interactive phase already ended at cmd: -- mailbox left cleanly"
        )
        return

    if final_state == "ENTRY":
        resp = session.send_and_read_until_idle(
            MAILBOX_ABANDON_ENTRY_COMMAND, note="abandon entry (cleanup)"
        )
        print(resp.decode("ascii", errors="replace"))

    b_resp = session.send_and_read_until_idle(
        MAILBOX_EXIT_COMMAND, note="leave mailbox (cleanup)"
    )
    print(b_resp.decode("ascii", errors="replace"))
    b_text = b_resp.decode("ascii", errors="replace")
    if maildrop_session_left(b_text):
        log.result("MAILDROP", "INFO", "mailbox left cleanly (cmd: confirmed)")
    else:
        log.result(
            "MAILDROP", "INFO",
            f"could not confirm the mailbox was left -- last input sent: "
            f"{last_sent!r} -- leave it manually in a normal terminal "
            f"before running anything else on this port"
        )


def _maildrop_confirm_loss_on_power_cycle(
    session: Session, log: RunLog, had_message_before: bool
) -> None:
    """Re-open the connection after the operator power-cycled the TNC
    (confirmed via read_power_cycle_confirmation() in the caller),
    re-run normalize() (resets MYCALL from config), then MDCHECK/L/B to
    see whether the mailbox survived (P22.2). *had_message_before* comes
    from run_maildrop_interactive()'s tracking of this same session -
    'L' reporting empty proves nothing if the mailbox was already empty
    beforehand."""
    log.line("--- MailDrop: confirming loss on power-cycle ---")
    session.disconnect()
    session.connect()
    session.normalize()  # re-sets MYCALL from config (P21.2)

    resp = session.send_and_read_until_idle(b"MDCHECK\r\n")
    print(resp.decode("ascii", errors="replace"))
    list_resp = session.send_and_read_until_idle(b"L\r")
    print(list_resp.decode("ascii", errors="replace"))
    list_text = list_resp.decode("ascii", errors="replace")
    b_resp = session.send_and_read_until_idle(MAILBOX_EXIT_COMMAND)
    print(b_resp.decode("ascii", errors="replace"))

    verdict = evaluate_power_cycle_loss(had_message_before, list_text)
    log.result(
        "MAILDROP", verdict,
        f"a message was stored during this session: {had_message_before} "
        f"-- post-power-cycle 'L': {list_text!r}"
    )


def _maildrop_set_daytime(session: Session, log: RunLog) -> None:
    """Set the TNC clock (DAYTIME) before opening the mailbox (P22.3) -
    with no RAM buffer battery, DAYTIME reads back as all dots after
    every power-on (CLAUDE.md), so the mailbox's own date/time column
    would too. Not part of normalize(): every OTHER hardware subcommand
    has no use for the clock, only maildrop's own 'L' listing does.

    Reuses ParamsUploader._cmd() and its exact 'yymmddHHMMSS' UTC format
    (comm/params_uploader.py) rather than rebuilding the command.

    P37: aborts the run (dry-run exempt) if the set is not confirmed in
    the response - DAYTIME being set is the entire reason a caller reaches
    for this function (real dates/senders in the mailbox listing instead
    of dot-runs), so a silent failure here is the same class of bug as
    P34's 'no reported success without proof', not an ordinary parameter
    that can be logged and continued past."""
    now = datetime.datetime.now(datetime.timezone.utc)
    cmd = ParamsUploader._cmd("DAYTIME", now.strftime("%y%m%d%H%M%S"))
    resp = session.verbose_bytes(cmd)
    log.line(f"DAYTIME set to {now:%y%m%d%H%M%S} (UTC): {resp!r}")
    if not session.dry_run and parse_query_value("DAYTIME", resp) is None:
        raise HWCheckError(f"DAYTIME set not confirmed -- response: {resp!r}")


def test_maildrop(
    session: Session, log: RunLog, skip_power_cycle: bool = False,
) -> None:
    log.line("--- MailDrop: guided recording terminal (P20 Teil B / P21.3) ---")
    session.normalize()
    log.line(
        "Local MailDrop session over the serial link, verbose mode only "
        "- never transmits on the air."
    )

    if session.dry_run:
        log.line(
            "[dry-run] would query " + ", ".join(_MAILDROP_QUERY_COMMANDS)
            + ", warn if XMITOK is ON, set the TNC clock (DAYTIME, UTC, "
              "same format as ParamsUploader) so the mailbox list shows "
              "real date/time values (P22.3), send MDCHECK, then open an "
              "interactive md>/md-text> terminal that tracks MAILBOX/ENTRY "
              "state from the TNC's OWN response text (P23.2) and stops "
              "the instant a 'cmd:' prompt is seen (P21.3), then the "
              "round-3 sequence and (unless --skip-power-cycle) the "
              "power-cycle test - nothing is sent in dry-run, the "
              "interactive phase never starts."
        )
        _maildrop_set_daytime(session, log)
        log.line(_MAILDROP_SUGGESTED_SEQUENCE)
        log.result("MAILDROP", "INFO", "dry-run, nothing sent")
        return

    log.line("Step 1: querying MailDrop-related parameters")
    values: dict[str, Optional[str]] = {}
    for cmd in _MAILDROP_QUERY_COMMANDS:
        resp = session.query(cmd)
        err = query_error(resp)
        if err is not None:
            log.line(f"WARNING: {cmd} unanswered -- error {err!r} (raw: {resp!r})")
            values[cmd] = None
            continue
        value = parse_query_value(cmd, resp)
        values[cmd] = value
        if value is None:
            # P34.2: still tolerated here (these are ordinary single
            # parameters, not the normalize()-level state queries that
            # abort the whole run) but logged loudly, not quietly.
            log.line(f"WARNING: {cmd} unanswered (raw: {resp!r})")
        else:
            log.line(f"{cmd}: {value!r} (raw: {resp!r})")

    xmitok = session.xmitok  # confirmed non-None by normalize() (P34.2)
    if xmitok.strip().upper() == "ON":
        print()
        print("*** XMITOK is ON ***")
        print(
            "This session stays on the serial link, not radio - but if "
            "the mailbox unexpectedly transmits (e.g. auto-forwarding), "
            "XMITOK ON means the TNC would key the transmitter."
        )
        log.line("WARNING: XMITOK is ON")

    _maildrop_set_daytime(session, log)

    print()
    print("Opening the local MailDrop with MDCHECK.")
    resp = session.send_and_read_until_idle(b"MDCHECK\r\n")
    resp_text = resp.decode("ascii", errors="replace")
    print(resp_text)

    if maildrop_session_left(resp_text):
        log.result(
            "MAILDROP", "INFO",
            "MDCHECK returned straight to cmd: -- mailbox did not open"
        )
        return
    if not _MAILBOX_PROMPT_RE.search(resp_text):
        log.line(
            f"WARNING: unrecognised MDCHECK response: "
            f"hex={resp.hex(' ').upper()}"
        )
    state = "MAILBOX"
    free = extract_mailbox_free(resp_text)
    if free is not None:
        log.line(f"Mailbox free memory: {free}")

    print()
    print(_MAILDROP_SUGGESTED_SEQUENCE)
    print(
        "Type mailbox commands at the prompt below (not a requirement, "
        "just a starting point). To end a message with ^Z: type the TWO "
        "CHARACTERS '^' and 'Z' -- do NOT press the real Ctrl-Z key, on "
        "Windows that ends console input instead of sending the "
        "character (the terminal now recovers automatically if it "
        "happens anyway, P23.3). ^D/^C are sent as their matching "
        "control byte. Type /quit to leave this terminal (this does NOT "
        "itself log out of the mailbox). The terminal stops on its own "
        "the instant the mailbox reports 'cmd:' -- see the safety note "
        "in the module docstring."
    )

    def _send(payload: bytes, note: str) -> bytes:
        resp = session.send_and_read_until_idle(payload, note=note)
        print(resp.decode("ascii", errors="replace"))
        return resp

    final_state, last_sent, message_stored = run_maildrop_interactive(
        state, free, _maildrop_read_line, _send, log
    )
    if final_state == "CMD":
        print(
            "Mailbox closed (cmd: prompt). Interactive phase ended: "
            "further input would reach the TNC command interpreter, "
            "where 'K' means CONVERSE."
        )

    _maildrop_leave_mailbox(session, log, final_state, last_sent)

    if skip_power_cycle:
        log.result(
            "MAILDROP", "INFO",
            "power-cycle test skipped (--skip-power-cycle) -- already "
            "PASSed in round 2, see Testplan T116"
        )
        return

    print()
    print("Power-cycle test.")
    print("  1. Switch the TNC OFF now.")
    print("  2. Wait 5 seconds.")
    print("  3. Switch it back ON.")
    proceed = read_power_cycle_confirmation(
        lambda: input(
            "Type 'done' when the TNC is back on (or 'skip' to skip "
            "this test): "
        )
    )
    if proceed:
        _maildrop_confirm_loss_on_power_cycle(session, log, message_stored)
    else:
        log.result("MAILDROP", "INFO", "power-cycle test skipped by operator")


def test_maildrop_host(session: Session, log: RunLog) -> None:
    log.line(
        "--- MailDrop over Host Mode (P24.2) -- read-only probe, HOST bit 1 ---"
    )
    session.normalize()

    if session.dry_run:
        log.line(
            "[dry-run] would create a test message over the known verbose "
            "path (MDCHECK/S/subject/text/EX/L/B, only after MDCHECK's "
            "own response is a recognised mailbox prompt, P34.3), "
            "verbose-query HOST, enter Host Mode, confirm y/N, then probe "
            "with these frames (probe B only runs if probe A got nothing; "
            "R<n> only if a list came back):"
        )
        for probe_data in (b"L\r", b"MDCHECK\r", b"L\r", b"R 1\r", b"B\r"):
            session.send_maildrop_host_frame(probe_data)
        log.result("MAILDROP_HOST", "INFO", "dry-run, nothing sent")
        return

    if session.xmitok.strip().upper() == "ON":
        print()
        print("*** XMITOK is ON ***")
        print(
            "This probe stays on the serial link, not radio - but if the "
            "mailbox unexpectedly transmits, XMITOK ON means the TNC "
            "would key the transmitter."
        )
        log.line("WARNING: XMITOK is ON")

    log.line(
        "Step 3: creating a test message over the known-safe verbose path"
    )
    entered, _msg_number = create_mdcheck_test_message(
        session.send_and_read_until_idle,
        b"Host Mode Test", b"created for the maildrop_host probe",
        log,
    )
    if entered:
        list_resp = session.send_and_read_until_idle(b"L\r")
        log.line(f"L (verbose, for later comparison): {list_resp!r}")
        session.send_and_read_until_idle(MAILBOX_EXIT_COMMAND)

    host_before = parse_query_value("HOST", session.query("HOST"))
    log.line(f"HOST (verbose, before): {host_before!r}")

    session.enter_host_mode()
    captured_a: list = []
    captured_b: list = []
    try:
        session.drain_pending_frames()

        print()
        print(
            "About to send unknown frame types into the MailDrop-login "
            "Host Mode data channel (CTL $60). Only read-only mailbox "
            "commands (L, MDCHECK, R) are sent - nothing that writes, "
            "kills, or transmits."
        )
        if input("Proceed? [y/N] ").strip().lower() != "y":
            log.result("MAILDROP_HOST", "INFO", "probe skipped by operator")
            return

        log.line("Probe A: L (assumes no login needed)")
        captured_a = session.send_maildrop_host_frame(b"L\r")

        if should_run_maildrop_host_probe_b(captured_a):
            log.line("Probe A got nothing -- trying probe B (MDCHECK, then L)")
            session.send_maildrop_host_frame(b"MDCHECK\r")
            captured_b = session.send_maildrop_host_frame(b"L\r")

        all_captured = captured_a + captured_b
        got_list = any("Msg#" in f.text for f in all_captured)

        if got_list and msg_number is not None:
            log.line(f"List seen -- reading message # {msg_number}")
            session.send_maildrop_host_frame(f"R {msg_number}\r".encode("ascii"))
        elif msg_number is not None:
            log.line("No list seen in probe A/B -- skipping R (nothing to read)")

        log.line("Leaving the mailbox (B)")
        session.send_maildrop_host_frame(MAILBOX_EXIT_COMMAND)
    finally:
        session.exit_host_mode()

    if not captured_a and not captured_b:
        log.line(
            "Probe C: neither A nor B got anything -- confirming the "
            "MailDrop-login bit is still set"
        )

    host_after_resp = session.query("HOST")
    host_after = parse_query_value("HOST", host_after_resp)
    log.line(f"HOST (verbose, after): {host_after!r}")
    if "cmd:" not in host_after_resp:
        log.line(
            f"WARNING: no 'cmd:' prompt seen after leaving Host Mode -- "
            f"raw response: {host_after_resp!r}"
        )

    all_captured = captured_a + captured_b
    frame_types = sorted({classify_maildrop_host_ctl(f.ctl) for f in all_captured})
    log.result(
        "MAILDROP_HOST", "INFO",
        f"response frame type(s): {frame_types or 'none captured'}"
    )
    if has_mailbox_data_frame(captured_a):
        log.result("MAILDROP_HOST", "INFO", "login not needed -- probe A alone got a mailbox data frame")
    elif has_mailbox_data_frame(captured_b):
        log.result("MAILDROP_HOST", "INFO", "login needed -- only probe B (after MDCHECK) got a mailbox data frame")
    elif captured_a or captured_b:
        log.result("MAILDROP_HOST", "INFO", "no mailbox response -- only ack/CMD_RESP frames captured (P26.1)")
    else:
        log.result("MAILDROP_HOST", "INFO", "neither probe A nor B got any response")
    log.result(
        "MAILDROP_HOST", "INFO",
        f"compare the captured text above against the verbose 'L' logged "
        f"earlier ({list_resp!r}) -- is the mailbox prompt/list format "
        f"byte-identical over Host Mode?"
    )


def test_mdcheck_scan(session: Session, log: RunLog) -> None:
    log.line(
        "--- mdcheck_scan (P26.2) -- find the Host Mode mnemonic for MDCHECK ---"
    )
    session.normalize()
    candidates = mdcheck_scan_candidates()

    if session.dry_run:
        log.line(
            f"[dry-run] would create a test message over the known verbose "
            f"path (MDCHECK/S/subject/text/EX/L/B, like maildrop_host, "
            f"only after MDCHECK's own response is a recognised mailbox "
            f"prompt, P34.3), enter Host Mode, confirm y/N, then try "
            f"these {len(candidates)} candidates in order (stopping at the "
            f"first hit), then leave Host Mode and normalize() again:"
        )
        for mnemonic in candidates:
            frame_bytes = build_command(mnemonic, b"")
            log.line(
                f"[dry-run]   >> {frame_bytes.hex(' ').upper()}  "
                f"({mnemonic.decode()})"
            )
        log.line(f"[dry-run] denylisted, never sent ({len(MDCHECK_SCAN_DENYLIST)}):")
        for mnemonic, reason in MDCHECK_SCAN_DENYLIST.items():
            log.line(f"[dry-run]   -- {mnemonic.decode()}: {reason}")
        log.result("MDCHECK_SCAN", "INFO", "dry-run, nothing sent")
        return

    if session.xmitok.strip().upper() == "ON":
        print()
        print("*** XMITOK is ON ***")
        print(
            "mdcheck_scan only sends Host Mode QUERIES -- none of the "
            f"{len(candidates)} candidates writes, kills, or transmits -- "
            "but XMITOK ON means the TNC would key the transmitter if "
            "anything unexpected did."
        )
        log.line("WARNING: XMITOK is ON")

    log.line("Step 1: creating a test message over the known-safe verbose path")
    entered, _msg_number = create_mdcheck_test_message(
        session.send_and_read_until_idle,
        b"mdcheck_scan test", b"created for the mdcheck_scan probe",
        log,
    )
    if entered:
        session.send_and_read_until_idle(MAILBOX_EXIT_COMMAND)

    session.enter_host_mode()
    hit: Optional[bytes] = None
    try:
        session.drain_pending_frames()

        print()
        print(
            f"About to send up to {len(candidates)} Host Mode query frames "
            f"('M?' with no argument, A-Z) looking for the MDCHECK "
            f"mnemonic. Denylisted, never sent: "
            f"{[m.decode() for m in MDCHECK_SCAN_DENYLIST]}."
        )
        print(
            "Every candidate is a query only -- nothing writes, kills, or "
            "transmits."
        )
        if input("Proceed? [y/N] ").strip().lower() != "y":
            log.result("MDCHECK_SCAN", "INFO", "scan skipped by operator")
            return

        hit = scan_for_mdcheck_mnemonic(candidates, session.probe_mdcheck_mnemonic)

        if hit is not None:
            log.line(
                f"HIT: {hit.decode()} -- confirming with L, then leaving "
                f"the mailbox"
            )
            session.send_maildrop_host_frame(b"L\r")
            session.send_maildrop_host_frame(MAILBOX_EXIT_COMMAND)
    finally:
        session.exit_host_mode()

    host_after_resp = session.query("HOST")
    if "cmd:" not in host_after_resp:
        log.line(
            f"WARNING: no 'cmd:' prompt seen after leaving Host Mode -- "
            f"raw response: {host_after_resp!r}"
        )
    session.normalize()

    if hit is not None:
        log.result(
            "MDCHECK_SCAN", "INFO",
            f"{hit.decode()} looks like the MDCHECK mnemonic -- its "
            f"response contained the mailbox prompt text"
        )
    else:
        log.result(
            "MDCHECK_SCAN", "INFO",
            f"no hit among {len(candidates)} candidates -- MDCHECK may not "
            f"be reachable as a two-letter Host Mode mnemonic at all; a "
            f"MailDrop dialog would then have to drive the mailbox over "
            f"the verbose path instead (see Backlog.md)"
        )


def test_maildrop_session(
    session: Session, log: RunLog, app_config: AppConfig, abort_test: bool,
) -> None:
    log.line(
        "--- maildrop_session (P28) -- drives the real MailDropSession, T119 ---"
    )
    mycall = (app_config.hf_packet.mycall or "NOCALL").upper()
    steps = build_maildrop_session_steps(mycall, abort_test)

    if session.dry_run:
        log.line(
            f"[dry-run] would set MYCALL (via normalize(), from config, "
            f"only if the TNC is at the factory default) and DAYTIME "
            f"(via _maildrop_set_daytime(), same as the maildrop "
            f"recorder), then enter Host Mode (existing SerialManager "
            f"path, not rebuilt here), then run these {len(steps)} steps "
            f"against the real MailDropSession, calling only its public "
            f"API:"
        )
        for i, step in enumerate(steps, start=1):
            expect = f" -> {step.expect}" if step.expect else ""
            log.line(f"[dry-run]   {i}. {step.name} (waits for {step.signal_name!r}{expect})")
        log.result("MAILDROP_SESSION", "INFO", "dry-run, nothing sent")
        return

    # Step 0 (P37): set MYCALL and DAYTIME while still in verbose mode,
    # before Host Mode entry -- without this, every message the steps
    # below store carries the factory 'PK232' as sender and dot-run
    # date/time columns (CLAUDE.md: no RAM buffer battery, both reset on
    # every power-off). normalize() is the existing MYCALL-from-config
    # path (reused, not reimplemented) and also confirms cmd:/PACKET/
    # MYCALL/XMITOK first; _maildrop_set_daytime() is the same DAYTIME
    # call the maildrop recorder already uses. Both abort the whole run
    # on failure (P34 rule: state a later step depends on must be
    # confirmed, never guessed) rather than continuing into a session
    # that would silently show PK232/dot-runs again.
    session.normalize()
    _maildrop_set_daytime(session, log)

    # Step 1 (P28.1): build the connection exactly like the app does --
    # connect + wakeup already happened in main() via session.connect();
    # parameter upload is skipped (--skip-upload, on by default: the
    # parameters are already verified by other subcommands and the
    # upload costs about a minute); enter Host Mode over the existing,
    # already-proven path.
    #
    # P30.1 point 4, checked (P37 update): unlike maildrop/maildrop_host/
    # mdcheck_scan, this function builds no test message of its own over
    # the verbose path -- but as of P37 it does call normalize() and set
    # DAYTIME (Step 0 above) before handing the port to Host Mode, so the
    # "none of its own verbose-mode work" claim from P28 no longer holds;
    # both calls finish and leave the port idle before enter_host_mode()
    # below needs it.
    session.enter_host_mode()

    # P35.1: MailDropSession keeps no record of its own traffic unless
    # given a trace callback -- without one, the 23.09.2026 'L' -> '***
    # What?' finding (P35) was impossible to diagnose from the log
    # alone. Mirrors Session.send_and_read_until_idle()'s own '>> hex=...
    # text=...' / '<< hex=... text=...' format (P20 Teil B) so every
    # maildrop_session run now shows exactly what MailDropSession itself
    # sent and received, not just the harness's own step-level log lines.
    def _trace_maildrop_session(kind: str, data: bytes) -> None:
        if kind == "tx":
            log.line(
                f">> hex={data.hex(' ').upper()} "
                f"text={format_bytes_with_controls(data)}"
            )
        elif kind == "rx":
            log.line(
                f"<< hex={data.hex(' ').upper()} "
                f"text={format_bytes_with_controls(data)}"
            )
        else:  # "discard" (P35.3)
            log.line(
                f"INFO: discarded {len(data)} byte(s) before command: "
                f"hex={data.hex(' ').upper()} "
                f"text={format_bytes_with_controls(data)}"
            )

    channel = SerialManagerChannel(session.sm)
    md_session = MailDropSession(
        channel,
        # can_open(): this harness runs solo with no channel ever
        # connected, so always yes. In the running application, this
        # callback is the channel-connected precondition check
        # (CLAUDE.md's "MailDrop session" gotcha) -- MailDropSession
        # itself does not know the channel model at all.
        can_open=lambda: (True, ""),
        trace=_trace_maildrop_session,
    )

    app = QCoreApplication.instance()
    outcome: dict = {}

    def on_finished(ok: bool) -> None:
        outcome["ok"] = ok
        app.quit()

    runner = MaildropSessionRunner(md_session, log, steps, on_finished)
    runner.start()
    app.exec()

    # P31.3: on_finished() can fire before the session's OWN internal
    # recovery (session.py's _recover(), triggered inside open()/leave()
    # on failure) has actually reached a terminal state - the runner has
    # no visibility into that in-flight recovery at all. Wait for the
    # session itself to report CLOSED or FAILED before doing anything
    # else, so the Host Mode check below is never run mid-recovery (P31
    # finding: it was, and its own "not in Host Mode" response got
    # misread as a fresh failure instead of "recovery is still running").
    _TERMINAL_STATES = ("CLOSED", "FAILED")
    deadline = time.monotonic() + 60.0
    while md_session.state not in _TERMINAL_STATES and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.05)

    if md_session.state == "FAILED":
        # The session's own failed() message (already logged above, from
        # _on_failed()) names the actual problem - inventing a second,
        # independent diagnosis here would just be noise on top of it.
        log.line(
            "Skipping the Host Mode check -- the session itself reported "
            "FAILED (see its own failed() message above for the reason)"
        )
    elif md_session.state == "CLOSED":
        log.line("Confirming Host Mode is active again (HPOLL query)")
        hp_frame = session.query_host(b"HP")
        if hp_frame is not None:
            log.result(
                "MAILDROP_SESSION", "INFO",
                f"HPOLL answered -- Host Mode confirmed active: {hp_frame.text!r}"
            )
        else:
            log.result(
                "MAILDROP_SESSION", "INFO",
                "no HPOLL response -- Host Mode state unclear, check the log"
            )
    else:
        log.line(
            f"WARNING: session state is still {md_session.state!r} after "
            f"60s -- recovery may still be running; skipping the Host "
            f"Mode check"
        )

    log.result(
        "MAILDROP_SESSION", "INFO",
        f"prompt bracket form seen: {runner.last_bracket!r}"
    )
    passed = sum(1 for _, verdict, _ in runner.results if verdict == "PASS")
    log.result(
        "MAILDROP_SESSION", "PASS" if outcome.get("ok") else "FAIL",
        f"{passed}/{len(steps)} steps passed"
    )
    for name, verdict, detail in runner.results:
        log.line(f"    {verdict:4s} {name}: {detail}")


# ===========================================================================
# P62 -- APRS measurement (aprs_query/aprs_tx/aprs_reject). MEASURES ONLY
# (hw_check rule 6) - the APRS mode itself is P63's job, built on these
# findings, not this package's. No new frame builder anywhere below: UN
# comes from HostModeProtocol.cmd_unproto(), CF from HostModeProtocol.
# build_command() - both existing, both otherwise unused in production.
# ===========================================================================

def test_aprs_query(session: Session, log: RunLog) -> None:
    log.line(
        "--- APRS query: UNPROTO/CFROM verbose and Host Mode, no TX ---"
    )

    via_path = "APZ232 VIA WIDE1-1,WIDE2-1"
    # Built ONCE, referenced by both the dry-run preview below and the
    # real A.3/A.5 sends further down - a single source of truth, so the
    # preview can never silently diverge from what actually gets sent
    # (test_hw_check_aprs.py::TestUnFrameComesFromHostModeProtocol).
    un_frame = HostModeProtocol.cmd_unproto(via_path)
    cf_none_frame = HostModeProtocol.build_command(b"CF", b"NONE")
    cf_all_frame = HostModeProtocol.build_command(b"CF", b"ALL")
    # P62a B.3 - PL is a hypothesis (Konfidenz M,
    # docs/PK232_firmware_matrix.md), not confirmed; A.8 below IS the
    # confirmation attempt.
    pl_frame = HostModeProtocol.build_command(b"PL", b"128")

    if session.dry_run:
        log.line(
            "[dry-run] would query UNPROTO/CFROM/PACLEN/VHF/HBAUD/MONITOR "
            "verbose, set UNPROTO with a VIA path verbose and query it "
            "back (A.2), set UNPROTO CQ then send UN with the same VIA "
            "path in Host Mode and verbose-query it afterwards (A.3), "
            "query UN in Host Mode (A.4), set CF NONE then CF ALL in "
            "Host Mode and verbose-query CFROM after each (A.5), probe "
            "an 8- and a 9-digipeater UNPROTO path verbose, resetting to "
            "CQ first so the 9-digi outcome is unambiguous (A.6), probe "
            "the PACLEN range 128/255/256/0 verbose (A.7), set PACLEN "
            "128 via the Host Mode PL frame and verbose-query it back, "
            "then query PL in Host Mode too (A.8), then restore "
            "UNPROTO/CFROM/PACLEN:"
        )
        session.send_frame(un_frame, note="A.3 UN")
        session.send_frame(cf_none_frame, note="A.5 CF NONE")
        session.send_frame(cf_all_frame, note="A.5 CF ALL")
        session.send_frame(pl_frame, note="A.8 PL 128")
        log.result("T138", "INFO", "dry-run, nothing sent")
        return

    session.normalize()

    commands = ["UNPROTO", "CFROM", "PACLEN"]
    originals: dict[str, Optional[str]] = {}
    for cmd in commands:
        originals[cmd] = parse_query_value(cmd, session.query(cmd))
        log.line(f"{cmd} (original): {originals[cmd]!r}")
    missing = [c for c in commands if originals[c] is None]
    if missing:
        log.result(
            "T138", "SKIPPED",
            f"original value(s) not parseable via parse_query_value() -- "
            f"not touching them: {missing}"
        )
        return

    try:
        # A.1 (PACLEN is now in `commands` above - logged there already)
        for cmd in ("VHF", "HBAUD", "MONITOR"):
            log.line(
                f"{cmd} (unchanged): "
                f"{parse_query_value(cmd, session.query(cmd))!r}"
            )

        # A.2
        session.set_verbose("UNPROTO", via_path)
        a2_query = session.query("UNPROTO")
        a2_parsed = parse_query_value("UNPROTO", a2_query)
        log.line(f"A.2 UNPROTO query after VIA set: {a2_query!r}")
        a2_pass = (
            a2_parsed is not None
            and "APZ232" in a2_parsed
            and "WIDE1-1" in a2_parsed and "WIDE2-1" in a2_parsed
        )
        log.result(
            "T138 A.2", "PASS" if a2_pass else "FAIL", f"parsed={a2_parsed!r}"
        )

        # A.3
        session.set_verbose("UNPROTO", "CQ")
        session.enter_host_mode()
        try:
            session.drain_pending_frames()
            captured: list = []
            session.sm.frame_received.connect(captured.append)
            try:
                session.send_frame(un_frame, note="A.3 UN")
                session._pump(2.0)
            finally:
                session.sm.frame_received.disconnect(captured.append)
            for f in captured:
                log.line(
                    f"A.3 << ctl=0x{f.ctl:02X} ch={f.channel} "
                    f"data={f.data!r} text={f.text!r}"
                )
        finally:
            session.exit_host_mode()
        a3_query = session.query("UNPROTO")
        a3_parsed = parse_query_value("UNPROTO", a3_query)
        log.line(f"A.3 UNPROTO verbose query after Host Mode UN: {a3_query!r}")
        a3_pass = (
            a3_parsed is not None
            and "APZ232" in a3_parsed
            and "WIDE1-1" in a3_parsed and "WIDE2-1" in a3_parsed
        )
        log.result(
            "T138 A.3", "PASS" if a3_pass else "FAIL", f"parsed={a3_parsed!r}"
        )

        # A.4
        session.enter_host_mode()
        try:
            session.drain_pending_frames()
            un_frame = session.query_host(b"UN")
        finally:
            session.exit_host_mode()
        un_text = un_frame.text if un_frame else "<no matching response>"
        log.line(f"A.4 UN Host Mode query result: {un_text!r}")
        log.result("T138 A.4", "INFO", f"raw={un_text!r}")

        # A.5
        session.enter_host_mode()
        try:
            session.drain_pending_frames()
            session.send_frame(cf_none_frame, note="A.5 CF NONE")
            session._pump(0.5)
        finally:
            session.exit_host_mode()
        cf_query_none = session.query("CFROM")
        cf_parsed_none = parse_query_value("CFROM", cf_query_none)
        log.line(
            f"A.5 CFROM verbose query after Host Mode CF NONE: "
            f"{cf_query_none!r}"
        )
        a5_none_pass = (
            cf_parsed_none is not None and "NONE" in cf_parsed_none.upper()
        )
        log.result(
            "T138 A.5 NONE", "PASS" if a5_none_pass else "FAIL",
            f"parsed={cf_parsed_none!r}"
        )

        session.enter_host_mode()
        try:
            session.drain_pending_frames()
            session.send_frame(cf_all_frame, note="A.5 CF ALL")
            session._pump(0.5)
        finally:
            session.exit_host_mode()
        cf_query_all = session.query("CFROM")
        cf_parsed_all = parse_query_value("CFROM", cf_query_all)
        log.line(
            f"A.5 CFROM verbose query after Host Mode CF ALL: "
            f"{cf_query_all!r}"
        )
        a5_all_pass = (
            cf_parsed_all is not None and "ALL" in cf_parsed_all.upper()
        )
        log.result(
            "T138 A.5 ALL", "PASS" if a5_all_pass else "FAIL",
            f"parsed={cf_parsed_all!r}"
        )

        # A.6 -- report only, per spec ("keine Bewertung nötig")
        eight_digis = "APZ232 VIA D1,D2,D3,D4,D5,D6,D7,D8"
        session.set_verbose("UNPROTO", eight_digis)
        q8 = session.query("UNPROTO")
        log.line(f"A.6 UNPROTO 8-digi query: {q8!r}")
        log.result("T138 A.6 8-digi", "INFO", f"raw={q8!r}")

        # P62a B.1: reset to CQ FIRST, so the 9-digi attempt's own
        # outcome is unambiguous. Device B, 27.09.2026, without this
        # reset the query after the 9-digi attempt still showed the
        # PREVIOUS step's 8 digis - truncated-to-8 and rejected-still-
        # showing-the-old-value could not be told apart. The SET
        # response (not just the query) is logged too.
        session.set_verbose("UNPROTO", "CQ")
        nine_digis = "APZ232 VIA D1,D2,D3,D4,D5,D6,D7,D8,D9"
        set_resp_9 = session.set_verbose("UNPROTO", nine_digis)
        log.line(f"A.6 UNPROTO 9-digi set response: {set_resp_9!r}")
        q9 = session.query("UNPROTO")
        q9_parsed = parse_query_value("UNPROTO", q9)
        log.line(f"A.6 UNPROTO 9-digi query: {q9!r}")
        log.result(
            "T138 A.6 9-digi", "INFO",
            f"{classify_unproto_digi_limit(q9_parsed)} -- raw={q9!r}"
        )

        # A.7 (P62a B.2): PACLEN range probe - exploratory, INFO only.
        # What is the real upper bound, and what does 0 mean?
        for value in ("128", "255", "256", "0"):
            set_resp = session.set_verbose("PACLEN", value)
            query_resp = session.query("PACLEN")
            parsed = parse_query_value("PACLEN", query_resp)
            log.line(
                f"A.7 PACLEN {value} -- set response: {set_resp!r} -- "
                f"query: {query_resp!r}"
            )
            log.result(f"T138 A.7 PACLEN {value}", "INFO", f"parsed={parsed!r}")

        # A.8 (P62a B.3): PACLEN in Host Mode, same pattern as A.5's CF -
        # P63 needs this since the mode switch itself happens there.
        session.set_verbose("PACLEN", "128")
        session.enter_host_mode()
        try:
            session.drain_pending_frames()
            session.send_frame(pl_frame, note="A.8 PL 128")
            session._pump(0.5)
        finally:
            session.exit_host_mode()
        a8_query = session.query("PACLEN")
        a8_parsed = parse_query_value("PACLEN", a8_query)
        log.line(
            f"A.8 PACLEN verbose query after Host Mode PL 128: {a8_query!r}"
        )
        log.result(
            "T138 A.8 PL set", "PASS" if a8_parsed == "128" else "FAIL",
            f"parsed={a8_parsed!r}"
        )

        session.enter_host_mode()
        try:
            session.drain_pending_frames()
            pl_response = session.query_host(b"PL")
        finally:
            session.exit_host_mode()
        pl_text = pl_response.text if pl_response else "<no matching response>"
        log.line(f"A.8 PL Host Mode query result: {pl_text!r}")
        log.result("T138 A.8 PL query", "INFO", f"raw={pl_text!r}")
    finally:
        for cmd in commands:
            verify_restore(
                cmd,
                lambda c=cmd: session.query(c),
                lambda v, c=cmd: session.set_verbose(c, v),
                originals[cmd],
                log,
            )


def _aprs_tx_round_spec(round_name: str) -> tuple[str, str, Optional[str]]:
    """Returns (unproto_path, info_field, via_digis_or_None) for one
    aprs_tx round (P62, Teil B's table; P62a Teil C.3 adds R6). A
    function, not a static table, because R1/R2/R5's info fields carry
    the current time (matching T101's own PK232PY T101 <round>
    HH:MM:SS convention).

    P62a C.4: R1/R2/R5 (the plain timestamp rounds) start with
    '>Test PK232PY ...', not '>PK232PY ...' - Direwolf misread the
    latter as a status report with an embedded Maidenhead locator
    ('PK23' + overlay '2' + symbol 'P', hence "Found 'Y' instead of
    space", T139, 27.09.2026): an info field whose first four
    characters are two letters then two digits gets misread this way.
    R3/R4/R6 do not start with that shape and are unaffected."""
    now = f"{datetime.datetime.now():%H:%M:%S}"
    if round_name == "R1":
        return "APZ232", f">Test PK232PY P62 R1 {now}", None
    if round_name == "R2":
        return (
            "APZ232 VIA WIDE1-1,WIDE2-1", f">Test PK232PY P62 R2 {now}",
            "WIDE1-1,WIDE2-1",
        )
    if round_name == "R3":
        return "APZ232", build_aprs_r3_info(), None
    if round_name == "R4":
        return "APZ232", build_aprs_r4_info(), None
    if round_name == "R5":
        return "APZ232", f">Test PK232PY P62 R5 {now}", None
    if round_name == "R6":
        # P62a C.3: reuses R4's own info field verbatim - R6 measures
        # whether a HIGHER PACLEN keeps the same payload in ONE frame,
        # not a new payload.
        return "APZ232", build_aprs_r4_info(), None
    raise ValueError(round_name)


_APRS_TX_ROUNDS = ("R1", "R2", "R3", "R4", "R5", "R6")


def test_aprs_tx(session: Session, log: RunLog) -> None:
    log.line(
        "--- APRS TX: five UI rounds incl. VIA path, charset, length, "
        "CFROM ---"
    )
    print()
    print("T139 TRANSMITS on the air. Before continuing:")
    print(
        "  - Do NOT run this on 144.800 MHz or any APRS frequency. Test "
        "frames with"
    )
    print(
        "    WIDEn-N paths are repeated by digipeaters and gated to "
        "APRS-IS. Use a"
    )
    print(
        "    simplex frequency with no APRS infrastructure, low power "
        "or a dummy load."
    )
    print(
        "  - Tune a second receiver running an AX.25 decoder (Direwolf) "
        "to that frequency."
    )

    # Built ONCE per round, referenced by both the dry-run preview below
    # and the real per-round send further down - a single source of
    # truth per round, so the preview can never silently diverge from
    # what actually gets sent
    # (test_hw_check_aprs.py::TestUnFrameComesFromHostModeProtocol).
    # Only the path (never the info field's own timestamp) is fixed here -
    # the real loop below re-derives info fresh each round.
    un_frames = {
        name: HostModeProtocol.cmd_unproto(_aprs_tx_round_spec(name)[0])
        for name in _APRS_TX_ROUNDS
    }
    cf_none_frame = HostModeProtocol.build_command(b"CF", b"NONE")

    if session.dry_run:
        log.line(
            "[dry-run] would normalize(), check VHF/HBAUD are 1200 Bd "
            "(offering to set them for this run), set UNPROTO via UN "
            "in Host Mode for each round, TRANSMIT a UI frame on "
            "channel 0 (R3 with PACLEN 128 for itself, R6 with the "
            "operator-given max PACLEN for itself, both restored right "
            "after), read the decoder output back as one pasted block, "
            "then restore UNPROTO/CFROM/VHF/HBAUD:"
        )
        for round_name in _APRS_TX_ROUNDS:
            _path, info, _via = _aprs_tx_round_spec(round_name)
            if round_name == "R5":
                session.send_frame(cf_none_frame, note="R5 CF NONE")
            session.send_frame(un_frames[round_name], note=f"{round_name} UN")
            log.line(
                f"[dry-run] would TRANSMIT on channel 0 ({round_name}): "
                f"{info!r}"
            )
        log.result("T139", "INFO", "dry-run, nothing sent")
        return

    # P62a C.1: aprs_tx used to skip normalize() entirely - after a
    # fresh power-on (no RAM battery, CLAUDE.md) MYCALL would still be
    # the factory default PK232, transmitting with no real callsign at
    # all. normalize() also sets MYCALL from AppConfig when it detects
    # this (see its own docstring).
    session.normalize()

    if input("Ready to continue? [y/N] ").strip().lower() != "y":
        log.result("T139", "INFO", "skipped by operator")
        return

    commands = ["UNPROTO", "CFROM", "VHF", "HBAUD"]
    originals: dict[str, Optional[str]] = {
        cmd: parse_query_value(cmd, session.query(cmd)) for cmd in commands
    }
    missing = [c for c in commands if originals[c] is None]
    if missing:
        log.result(
            "T139", "SKIPPED",
            f"original value(s) not parseable via parse_query_value() -- "
            f"not touching them: {missing}"
        )
        return

    if not ensure_vhf_1200(session, log, "T139", originals):
        return

    log.line(f"PACLEN (unchanged): {parse_query_value('PACLEN', session.query('PACLEN'))!r}")

    try:
        for round_name in _APRS_TX_ROUNDS:
            path, info, via_digis = _aprs_tx_round_spec(round_name)

            if round_name == "R5":
                session.enter_host_mode()
                try:
                    session.drain_pending_frames()
                    session.send_frame(cf_none_frame, note="R5 CF NONE")
                    session._pump(0.5)
                finally:
                    session.exit_host_mode()

            # P62a C.2: R3 sets PACLEN 128 for ITSELF ONLY (restored
            # right after, via run_with_restore) so it measures
            # character-fidelity alone, never mixed up with whatever
            # this device's own configured PACLEN happens to be - the
            # bug that invalidated the first real R3 run (27.09.2026,
            # Device B, PACLEN 64: the 106-char probe itself split
            # into 2 frames). R4 deliberately stays at the device's OWN
            # PACLEN - it measures the split, so changing PACLEN out
            # from under it would defeat the point of R4 itself.
            if round_name == "R3":
                run_with_restore(
                    command="PACLEN",
                    query=lambda: session.query("PACLEN"),
                    restore=lambda v: session.set_verbose("PACLEN", v),
                    action=lambda: session.set_verbose("PACLEN", "128"),
                    log=log,
                )

            # P62a C.3: R6 needs the largest PACLEN A.7 (aprs_query)
            # found actually accepted, in THIS power-on session - but
            # aprs_query and aprs_tx are separate process invocations,
            # so there is no reliable way for this one to know whether
            # (or what) an earlier aprs_query run found; always asking
            # is the honest fallback the spec itself describes for
            # exactly that case, applied unconditionally rather than
            # attempting to guess session continuity.
            if round_name == "R6":
                paclen_max = input(
                    "R6 needs the largest PACLEN value A.7 (aprs_query) "
                    "found accepted in this power-on session. If "
                    "unknown, run aprs_query first, or answer with a "
                    "known-safe value. PACLEN for R6? [128] "
                ).strip() or "128"
                run_with_restore(
                    command="PACLEN",
                    query=lambda: session.query("PACLEN"),
                    restore=lambda v: session.set_verbose("PACLEN", v),
                    action=lambda v=paclen_max: session.set_verbose("PACLEN", v),
                    log=log,
                )

            session.enter_host_mode()
            try:
                session.drain_pending_frames()
                session.send_frame(un_frames[round_name], note=f"{round_name} UN")
                session._pump(0.5)

                if not confirm_tx(
                    f"Round {round_name}: transmit a UI frame on the "
                    f"unconnected channel 0, UNPROTO path {path!r}.\n"
                    f"Info field: {info!r}"
                ):
                    log.result(
                        f"T139 {round_name}", "INFO", "skipped by operator"
                    )
                    continue

                session.send_data_channel0(info)
                captured: list = []
                session.sm.frame_received.connect(captured.append)
                try:
                    session._pump(2.0)
                finally:
                    session.sm.frame_received.disconnect(captured.append)
                for f in captured:
                    log.line(
                        f"<< ctl=0x{f.ctl:02X} ch={f.channel} "
                        f"data={f.data!r} text={f.text!r}"
                    )
            finally:
                session.exit_host_mode()

            pasted = read_pasted_block(
                "Paste the decoder output (Direwolf's own non-"
                "printable-byte notation included - blank lines "
                "between frames are part of the paste, not a "
                'terminator; leave empty and just enter "." if the '
                'decoder showed nothing), then a line with a single '
                '"." to finish:'
            )

            outcome = evaluate_aprs_round(info, via_digis, pasted)
            log.result(
                f"T139 {round_name}", outcome["verdict"],
                f"info_exact={outcome['info_exact']} "
                f"trailing_cr={outcome['trailing_cr']} "
                f"path_ok={outcome['path_ok']} frames={outcome['frames']}"
            )
    finally:
        for cmd in commands:
            verify_restore(
                cmd,
                lambda c=cmd: session.query(c),
                lambda v, c=cmd: session.set_verbose(c, v),
                originals[cmd],
                log,
            )


def test_aprs_reject(session: Session, log: RunLog) -> None:
    log.line(
        "--- APRS reject: incoming connect with CFROM ALL vs NONE ---"
    )
    print()
    print(
        "Calling station: Direwolf on the second radio, connected mode "
        "via AGW."
    )
    print(
        "  - direwolf.conf needs PTT configured (Direwolf must "
        "transmit),"
    )
    print(
        "    MYCALL different from this TNC (e.g. OE3GAS-1), AGWPORT "
        "8000."
    )
    print("  - Terminal (e.g. QtTermTCP) connected to localhost:8000.")

    # Single source of truth for both the dry-run preview and the real
    # C.2 send below (test_hw_check_aprs.py::
    # TestUnFrameComesFromHostModeProtocol).
    cf_none_frame = HostModeProtocol.build_command(b"CF", b"NONE")

    if session.dry_run:
        log.line(
            "[dry-run] would normalize(), check VHF/HBAUD are 1200 Bd "
            "(offering to set them for this run), ask for the calling "
            "station's callsign and software (Direwolf/AGW), record "
            "all Host Mode frames "
            "for 60s while it connects and disconnects (CFROM ALL "
            "baseline, C.1), ask the operator what the calling station "
            "and this TNC's own PTT/SEND LED showed, set CF NONE in "
            "Host Mode, record 90s while the second station calls "
            "again (C.2), ask the same questions, then restore "
            "CFROM/VHF/HBAUD:"
        )
        session.send_frame(cf_none_frame, note="C.2 CF NONE")
        log.result("T140", "INFO", "dry-run, nothing sent")
        return

    # P62a C.1: same reasoning as aprs_tx - a fresh power-on TNC has no
    # real callsign set until normalize() puts one there.
    session.normalize()

    if input("Ready to continue? [y/N] ").strip().lower() != "y":
        log.result("T140", "INFO", "skipped by operator")
        return

    commands = ["CFROM", "VHF", "HBAUD"]
    originals: dict[str, Optional[str]] = {
        cmd: parse_query_value(cmd, session.query(cmd)) for cmd in commands
    }
    missing = [c for c in commands if originals[c] is None]
    if missing:
        log.result(
            "T140", "SKIPPED",
            f"original value(s) not parseable via parse_query_value() -- "
            f"not touching them: {missing}"
        )
        return

    if not ensure_vhf_1200(session, log, "T140", originals):
        return

    # P62a Teil D: the operator has only one physical PK-232, so the
    # calling station is Direwolf via AGW, not a second device - MYCALL
    # comes from the SAME query normalize() itself just ran (P43/P34.2's
    # own MYCALL check), never hardcoded, so the printed instruction is
    # always correct even if the TNC's own MYCALL differs from what
    # AppConfig has configured.
    mycall = parse_query_value("MYCALL", session.query("MYCALL")) or "MYCALL"
    other_station = input("Calling station's callsign? ").strip()
    other_software = input(
        "Calling station software (e.g. Direwolf 1.7 + QtTermTCP)? "
    ).strip()
    log.line(
        f"Second station: {other_station!r} "
        f"(software {other_software!r})"
    )

    def record_phase(label: str, seconds: float) -> list:
        session.enter_host_mode()
        try:
            session.drain_pending_frames()
            captured: list = []
            session.sm.frame_received.connect(captured.append)
            try:
                print(f"{label}: recording for {seconds:.0f}s ...")
                session._pump(seconds)
            finally:
                session.sm.frame_received.disconnect(captured.append)
        finally:
            session.exit_host_mode()
        for f in captured:
            log.line(
                f"{label} << ctl=0x{f.ctl:02X} ch={f.channel} "
                f"data={f.data!r} text={f.text!r}"
            )
        return captured

    def ask_operator(label: str) -> dict:
        # P62a Teil D: read_pasted_block() (Teil A), not a single
        # input() line - the terminal's own connect attempt/reply can
        # itself be multi-line (e.g. QtTermTCP echoing several lines).
        calling_text = read_pasted_block(
            f'{label}: paste what the CALLING station showed (e.g. '
            f'"*** busy", "Retry count exceeded", nothing), then a '
            f'line with a single "." to finish:'
        )
        ptt_lit = input(
            f"{label}: did this TNC's own PTT/SEND LED light up? [y/n] "
        ).strip().lower()
        log.line(
            f"{label} operator: calling station showed {calling_text!r}, "
            f"PTT lit={ptt_lit!r}"
        )
        return {"calling": calling_text, "ptt": ptt_lit}

    results: dict = {}

    def action() -> None:
        log.line("C.1 baseline: CFROM ALL (unchanged)")
        print(f"From the terminal, connect to {mycall} now, then disconnect immediately.")
        record_phase("C.1", 60.0)
        results["c1"] = ask_operator("C.1")

        session.enter_host_mode()
        try:
            session.drain_pending_frames()
            session.send_frame(cf_none_frame, note="C.2 CF NONE")
            session._pump(0.5)
        finally:
            session.exit_host_mode()

        log.line("C.2: CFROM NONE")
        print(f"From the terminal, connect to {mycall} now.")
        record_phase("C.2", 90.0)
        results["c2"] = ask_operator("C.2")

    try:
        action()
    finally:
        for cmd in commands:
            verify_restore(
                cmd,
                lambda c=cmd: session.query(c),
                lambda v, c=cmd: session.set_verbose(c, v),
                originals[cmd],
                log,
            )

    log.result(
        "T140", "INFO",
        f"second station={other_station!r} ({other_software!r}) -- "
        f"C.1(ALL) operator={results.get('c1')}; "
        f"C.2(NONE) operator={results.get('c2')}"
    )


# ===========================================================================
# P65 -- link/mode carry-over measurement (link_carry/link_carry_host).
# MEASURES ONLY (hw_check rule 6) - the implementation (an internal
# connection table, carried across the verbose<->Host Mode switch) is P66's
# job, built on these findings, not this package's. No new frame builder
# anywhere below: link status is HostModeProtocol.cmd_link_status(), Host
# Mode connect is HostModeProtocol.cmd_connect(), the mode-switch frames are
# VHFPacketMode's own get_activate_frames()/get_init_frames().
# ===========================================================================

def _probe_all_channel_links(
    session: Session, link_status_frames: dict[int, bytes], label: str,
    log: RunLog,
) -> dict[int, LinkStatus]:
    """Query TRM 4.3.3 link status on every channel (0-9) and decode
    each via comm.link_status.decode_link_status() (P65, A.6/B; moved
    to comm/link_status.py, P67 Teil A - the SAME decoder the app's own
    LinkTable.on_link_status() now uses) - shared by link_carry/
    link_carry_host so both measure the exact same way. Logs every
    decoded result, labelled, for the raw hardware capture - never just
    the summary."""
    results: dict[int, LinkStatus] = {}
    for ch in range(10):
        captured = session.query_channel_frame(
            ch, link_status_frames[ch], note=f"{label} CO ch{ch}",
        )
        match = next(
            (f for f in captured if f.channel == ch and f.data.startswith(b"CO")),
            None,
        )
        if match is not None:
            results[ch] = decode_link_status(match.ctl, match.data)
        else:
            results[ch] = LinkStatus(channel=ch, unparsed=True)
        log.line(f"{label} ch{ch} decoded: {results[ch]!r}")
    return results


def _channels_connected_to(
    results: dict[int, LinkStatus], target_call: str,
) -> list[int]:
    """Which channels' decoded link status (see above) shows
    *target_call* in the partner/digis text - the measurement's own
    stand-in for "connected", since the numeric link-state value's
    exact meaning per state is not documented in what this tool has
    measured so far (only that state = (a & 0x0F) + 1, and that
    state == 5 means connected - T142's own real capture). Never
    guesses beyond that."""
    call = target_call.strip().upper()
    if not call:
        return []
    return [
        ch for ch, r in results.items()
        if not r.unparsed and r.error_code is None
        and call in f"{r.partner} {r.digis}".upper()
    ]


def _confirm_command_prompt_light(session: Session, label: str, log: RunLog) -> bool:
    """P66, Teil C: send the TNC's own COMMAND character (up to three
    times, escape_converse() - the SAME shared function Teil A's
    enter_host_mode() fix and the app's own detection-chain step 2b use,
    command_char has exactly one source: session.sm.command_char) and
    report whether 'cmd:' was actually seen.

    Unlike confirm_command_prompt() (P34.1, normalize()'s own hard
    gate), this NEVER raises - a caller here wants to skip only its OWN
    next block of verbose queries when the TNC turns out to still be in
    Converse (B.1: a verbose CONNECT can leave it there), not abort the
    rest of the subcommand, which still has real Host Mode work to do
    regardless of whether this particular verbose check succeeds.
    """
    def _send_and_wait(data: bytes, timeout: float) -> bytes:
        del session._raw_buf[:]
        session.sm.write_verbose(data)
        return session.read_until_idle(idle=1.0, max_total=timeout)

    found, raw = escape_converse(_send_and_wait, bytes([session.sm.command_char]))
    log.line(f"{label} command-prompt check: found_cmd={found} raw={raw!r}")
    return found


def test_link_carry(session: Session, log: RunLog) -> None:
    log.line(
        "--- Link carry: verbose connect survives Host Mode, CO and "
        "OP queries ---"
    )

    # Built ONCE, referenced by both the dry-run preview below and the
    # real sends further down (test_hw_check_link_carry.py::
    # TestLinkCarryDryRunFramesComeFromRealBuilders).
    link_status_frames = {ch: HostModeProtocol.cmd_link_status(ch) for ch in range(10)}
    vhf = VHFPacketMode()
    mode_switch_frames = vhf.get_activate_frames() + vhf.get_init_frames()

    if session.dry_run:
        log.line(
            "[dry-run] would normalize(), check VHF/HBAUD, ask the "
            "operator to connect to a counterpart from this program's "
            "own CONNECT prompt, query OPMODE/CSTATUS/CONNECT verbose "
            "(A.3), enter Host Mode and record 3s of unsolicited "
            "traffic (A.4), query OPMODE in Host Mode (A.5), query "
            "link status on channels 0-9 (A.6), send a data frame on "
            "the channel that looks connected (A.7), re-send VHF "
            "Packet's own activate+init frames and re-check link "
            "status (A.8), leave Host Mode and re-check verbose (A.9), "
            "then offer to disconnect (A.10):"
        )
        for ch in range(10):
            session.send_channel_frame(
                ch, link_status_frames[ch], note=f"A.6 CO ch{ch}"
            )
        for frame in mode_switch_frames:
            session.send_frame(frame, note="A.8 VHF mode switch")
        log.result("T141", "INFO", "dry-run, nothing sent")
        return

    session.normalize()

    if input("Ready to continue? [y/N] ").strip().lower() != "y":
        log.result("T141", "INFO", "skipped by operator")
        return

    commands = ["VHF", "HBAUD"]
    originals: dict[str, Optional[str]] = {
        cmd: parse_query_value(cmd, session.query(cmd)) for cmd in commands
    }
    missing = [c for c in commands if originals[c] is None]
    if missing:
        log.result(
            "T141", "SKIPPED",
            f"original value(s) not parseable via parse_query_value() -- "
            f"not touching them: {missing}"
        )
        return

    if not ensure_vhf_1200(session, log, "T141", originals):
        return

    try:
        # A.2
        print("Connect to the counterpart now from THIS program's prompt:")
        target_call = input("Target callsign? ").strip()
        connect_echo = session.verbose(f"CONNECT {target_call}")
        log.line(f"A.2 CONNECT command echo: {connect_echo!r}")
        connect_wait = session.read_until_idle(idle=2.0, max_total=30.0)
        connect_text = connect_wait.decode("ascii", errors="replace")
        log.line(f"A.2 waiting for *** CONNECTED: {connect_text!r}")
        # P67, Teil D H.1/A.2: '?already connected' means the TNC is
        # already linked to this counterpart on some channel - not the
        # Converse-connect state this test measures. Fail fast here
        # rather than let later steps (A.3 onward) silently measure the
        # wrong thing.
        if "already connected" in (connect_echo + connect_text).lower():
            log.result(
                "T141 A.2", "FAIL",
                "TNC answered '?already connected' - disconnect the "
                "counterpart first"
            )
            return

        # A.3 (P66, Teil C): verify the command prompt BEFORE sending
        # anything else - a verbose CONNECT can leave the TNC in
        # Converse (B.1), and queries sent there go to the counterpart,
        # not the TNC.
        if not _confirm_command_prompt_light(session, "A.3", log):
            log.result("T141 A.3", "FAIL", "still in Converse - no queries sent")
        else:
            for cmd in ("OPMODE", "CSTATUS"):
                log.line(f"A.3 {cmd}: {session.query(cmd)!r}")
            a3_connect = session.query("CONNECT")
            log.line(f"A.3 CONNECT (bare): {a3_connect!r}")

        session.enter_host_mode()
        try:
            # A.4a (P66): did the Teil-A handshake's own OPMODE check
            # actually pass, not just "is_host_mode is now True"?
            log.result(
                "T141 A.4a", "INFO",
                f"handshake OPMODE check raw={session.sm.last_enter_host_mode_raw!r}"
            )

            # A.4
            captured_a4: list = []
            session.sm.frame_received.connect(captured_a4.append)
            try:
                session._pump(3.0)
            finally:
                session.sm.frame_received.disconnect(captured_a4.append)
            for f in captured_a4:
                log.line(
                    f"A.4 << ctl=0x{f.ctl:02X} ch={f.channel} "
                    f"data={f.data!r} text={f.text!r}"
                )
            log.result(
                "T141 A.4", "INFO",
                f"{len(captured_a4)} unsolicited frame(s) seen"
            )

            # A.5
            op_frame = session.query_host(b"OP")
            op_text = op_frame.text if op_frame else "<no matching response>"
            log.line(f"A.5 OPMODE Host Mode query: {op_text!r}")
            log.result("T141 A.5", "INFO", f"raw={op_text!r}")

            # A.6
            a6_results = _probe_all_channel_links(
                session, link_status_frames, "A.6", log
            )
            connected_channels = _channels_connected_to(a6_results, target_call)
            log.result(
                "T141 A.6",
                "PASS" if len(connected_channels) == 1 else "INCONCLUSIVE",
                f"connected_channels={connected_channels} "
                f"target={target_call!r}"
            )

            # A.7
            carry_channel = connected_channels[0] if connected_channels else 0
            if confirm_tx(
                f"Send a single CR data frame on channel {carry_channel} "
                f"so the counterpart's own terminal shows a prompt - "
                f"type a short reply there."
            ):
                session.send_data_channel(carry_channel, "\r")
                captured_a7: list = []
                session.sm.frame_received.connect(captured_a7.append)
                try:
                    session._pump(10.0)
                finally:
                    session.sm.frame_received.disconnect(captured_a7.append)
                for f in captured_a7:
                    log.line(
                        f"A.7 << ctl=0x{f.ctl:02X} ch={f.channel} "
                        f"data={f.data!r} text={f.text!r}"
                    )
                answer_channels = sorted({
                    f.channel for f in captured_a7 if 0x30 <= f.ctl <= 0x39
                })
                log.result(
                    "T141 A.7", "INFO",
                    f"data answer seen on channel(s)={answer_channels}"
                )
            else:
                log.result("T141 A.7", "INFO", "skipped by operator")

            # A.8
            if confirm_tx(
                "Re-send VHF Packet's own activate+init frames while "
                "the link may still be up (Host Mode settings only, "
                "nothing new on the air)."
            ):
                for frame in mode_switch_frames:
                    session.send_frame(frame, note="A.8 VHF mode switch")
                    session._pump(0.3)

                op_frame_after = session.query_host(b"OP")
                op_text_after = (
                    op_frame_after.text if op_frame_after
                    else "<no matching response>"
                )
                log.line(
                    f"A.8 OPMODE after mode-switch frames: {op_text_after!r}"
                )

                a8_results = _probe_all_channel_links(
                    session, link_status_frames, "A.8", log
                )
                a8_connected = _channels_connected_to(a8_results, target_call)
                a8_pass = bool(a8_connected) and a8_connected == connected_channels
                log.result(
                    "T141 A.8", "PASS" if a8_pass else "FAIL",
                    f"before={connected_channels} after={a8_connected} "
                    f"opmode={op_text_after!r}"
                )
                # P67, Teil D H.1: track the most recently confirmed
                # connected channel(s) from the LAST CO query actually
                # sent (A.8's, when it ran) - A.9/A.10 below use this,
                # never an assumption about which channel is "active".
                if a8_connected:
                    connected_channels = a8_connected
            else:
                log.result("T141 A.8", "INFO", "skipped by operator")
        finally:
            session.exit_host_mode()

        # A.9 (P66, Teil C): same command-prompt check as A.3 - leaving
        # Host Mode can itself land back in Converse (P53.B) if the exit
        # sequence's own COMMAND-char resync did not take, e.g. because
        # the wrong channel was active.
        if not _confirm_command_prompt_light(session, "A.9", log):
            log.result("T141 A.9", "FAIL", "still in Converse - no queries sent")
        else:
            log.line(f"A.9 OPMODE: {session.query('OPMODE')!r}")
            # P67, Teil D H.2: CSTATUS parsed for the channel(s) A.6/
            # A.8 actually found connected - a bare CONNECT query shows
            # the I/O channel, which A.6's own probe loop (0-9) leaves
            # at channel 9, not necessarily the connected one.
            a9_cstatus_raw = session.query("CSTATUS")
            log.line(f"A.9 CSTATUS: {a9_cstatus_raw!r}")
            a9_parsed = parse_cstatus(a9_cstatus_raw)
            a9_channels = connected_channels or [carry_channel]
            a9_pass = any(
                ch in a9_parsed and target_call.upper() in a9_parsed[ch][2].upper()
                for ch in a9_channels
            )
            log.result(
                "T141 A.9", "PASS" if a9_pass else "INCONCLUSIVE",
                f"checked_channels={a9_channels} parsed={a9_parsed!r}"
            )

        # A.10 (P67, Teil D H.1): disconnect via Host Mode DI on the
        # CONNECTED channel from the last CO query - like
        # link_carry_host's own cleanup, never a verbose DISCONNECT on
        # whatever the active/IO channel happens to be (A.6's probe
        # loop leaves that at channel 9, not necessarily where the real
        # connection is - exactly what made the 28.09.2026 runs 2/3
        # answer '?already connected' instead of testing Converse).
        disconnect_channel = connected_channels[0] if connected_channels else carry_channel
        if input(f"Disconnect channel {disconnect_channel} now? [Y/n] ").strip().lower() in ("", "y"):
            session.enter_host_mode()
            try:
                session.send_channel_frame(
                    disconnect_channel,
                    HostModeProtocol.cmd_disconnect(disconnect_channel),
                    note=f"A.10 DI ch{disconnect_channel}",
                )
                session._pump(0.3)
            finally:
                session.exit_host_mode()
            log.line(f"A.10: sent Host Mode DI on channel {disconnect_channel}")
        else:
            log.result("T141 A.10", "INFO", "left connected by operator choice")
    finally:
        for cmd in commands:
            verify_restore(
                cmd,
                lambda c=cmd: session.query(c),
                lambda v, c=cmd: session.set_verbose(c, v),
                originals[cmd],
                log,
            )


def test_link_carry_host(session: Session, log: RunLog) -> None:
    log.line(
        "--- Link carry (Host -> verbose): Host Mode connect seen "
        "from verbose ---"
    )

    link_status_frames = {ch: HostModeProtocol.cmd_link_status(ch) for ch in range(10)}
    preview_connect_frame = HostModeProtocol.cmd_connect("OE3GAS-1", channel=1)
    preview_disconnect_frame = HostModeProtocol.cmd_disconnect(1)
    vhf = VHFPacketMode()

    if session.dry_run:
        log.line(
            "[dry-run] would normalize(), check VHF/HBAUD, connect on "
            "channel 1 in Host Mode (HostModeProtocol.cmd_connect()), "
            "wait for a CONNECTED link message, query OPMODE and link "
            "status on channels 0-9, leave Host Mode and query "
            "OPMODE/CSTATUS/CONNECT verbose, re-enter Host Mode and "
            "re-check link status on channel 1 (D.1: probe channel 3, "
            "then leave Host Mode and see which channel verbose CSTATUS "
            "now calls the active/IO channel), then measure CONVERSE "
            "and a channel switch after Host -> verbose (D.2), then "
            "D.3: re-enter Host Mode, send CO on the CONNECTED channel "
            "as the last $4x frame, HOST OFF, check CSTATUS now calls "
            "that channel IO, CONVERSE there - then clean up by "
            "disconnecting the CONNECTED channel via Host Mode DI "
            "before HOST OFF (never a verbose DISCONNECT on whatever "
            "the active channel happens to be, P66b B.6):"
        )
        for frame in vhf.get_activate_frames() + vhf.get_init_frames():
            session.send_frame(frame, note="activate VHF Packet")
        session.send_channel_frame(1, preview_connect_frame, note="B connect ch1")
        for ch in range(10):
            session.send_channel_frame(
                ch, link_status_frames[ch], note=f"B CO ch{ch}"
            )
        session.send_channel_frame(
            1, link_status_frames[1],
            note="D.3 CO ch1 (last $4x before HOST OFF)",
        )
        session.send_channel_frame(1, preview_disconnect_frame, note="cleanup DI ch1")
        # D.2.3 (P66a): CHSWITCH's own query value ('$xx', a hex STRING)
        # is decoded into the actual byte before it is sent - worked
        # example, no port needed, so --dry-run itself shows the fix
        # (previously the three literal characters '$'/'7'/'C', never a
        # valid channel-switch command):
        _example_send = chswitch_byte("$7C") + b"1" + b"CONVERSE\r\n\r"
        log.line(
            f"[dry-run] D.2.3 example (CHSWITCH='$7C'): would send "
            f"{_example_send.hex(' ').upper()}"
        )
        log.result("T142", "INFO", "dry-run, nothing sent")
        return

    session.normalize()

    if input("Ready to continue? [y/N] ").strip().lower() != "y":
        log.result("T142", "INFO", "skipped by operator")
        return

    commands = ["VHF", "HBAUD"]
    originals: dict[str, Optional[str]] = {
        cmd: parse_query_value(cmd, session.query(cmd)) for cmd in commands
    }
    missing = [c for c in commands if originals[c] is None]
    if missing:
        log.result(
            "T142", "SKIPPED",
            f"original value(s) not parseable via parse_query_value() -- "
            f"not touching them: {missing}"
        )
        return

    if not ensure_vhf_1200(session, log, "T142", originals):
        return

    target_call = input("Counterpart callsign to CONNECT (Host Mode)? ").strip()

    try:
        session.enter_host_mode()
        try:
            session.drain_pending_frames()

            for frame in vhf.get_activate_frames() + vhf.get_init_frames():
                session.send_frame(frame, note="B activate VHF Packet")
                session._pump(0.3)

            if not confirm_tx(
                f"Connect to {target_call!r} on channel 1, from Host "
                f"Mode (HostModeProtocol.cmd_connect())."
            ):
                log.result("T142", "INFO", "skipped by operator")
                return

            connect_frame = HostModeProtocol.cmd_connect(target_call, channel=1)
            captured: list = []
            session.sm.frame_received.connect(captured.append)
            try:
                session.send_channel_frame(1, connect_frame, note="B connect ch1")
                session._pump(30.0)
            finally:
                session.sm.frame_received.disconnect(captured.append)
            connect_error: Optional[LinkStatus] = None
            for f in captured:
                log.line(
                    f"B << ctl=0x{f.ctl:02X} ch={f.channel} "
                    f"data={f.data!r} text={f.text!r}"
                )
                # P67, Teil D H.3: a CO-shaped frame here is the TNC's
                # own error answer to the connect attempt (e.g. "already
                # connected"), not link-message text - decode it via
                # comm.link_status the same way _probe_all_channel_links
                # does, and log a one-byte error_code explicitly instead
                # of letting it fall through as an unrecognised frame.
                if f.data.startswith(b"CO"):
                    status = decode_link_status(f.ctl, f.data)
                    if status.error_code is not None:
                        connect_error = status
                        log.line(
                            f"B << CO error_code=0x{status.error_code:02X} "
                            f"ch={status.channel} (meaning not guessed)"
                        )
            connected_seen = any(
                f.channel == 1 and "connect" in (f.text or "").lower()
                for f in captured
            )
            if connect_error is not None:
                log.result(
                    "T142 connect", "FAIL",
                    f"CO error_code=0x{connect_error.error_code:02X} on "
                    f"ch{connect_error.channel} - not a CONNECTED link "
                    f"message (H.3)"
                )
            else:
                log.result(
                    "T142 connect", "INFO" if connected_seen else "INCONCLUSIVE",
                    f"CONNECTED-shaped link message seen on channel 1={connected_seen}"
                )

            op_frame = session.query_host(b"OP")
            log.line(
                f"B OPMODE Host Mode: "
                f"{op_frame.text if op_frame else '<no matching response>'!r}"
            )

            b_results = _probe_all_channel_links(
                session, link_status_frames, "B", log
            )
        finally:
            session.exit_host_mode()

        log.line(f"B (verbose) OPMODE: {session.query('OPMODE')!r}")
        # P67, Teil D H.2: CSTATUS parsed for the channel this test
        # itself connected (1), not a bare CONNECT query - bare CONNECT
        # shows the I/O channel, which need not be the connected one.
        cstatus_b_raw = session.query("CSTATUS")
        log.line(f"B (verbose) CSTATUS: {cstatus_b_raw!r}")
        cstatus_b_parsed = parse_cstatus(cstatus_b_raw)
        b_verbose_shows_it = (
            bool(target_call) and 1 in cstatus_b_parsed
            and target_call.upper() in cstatus_b_parsed[1][2].upper()
        )
        log.result(
            "T142 verbose", "INFO",
            f"verbose CSTATUS shows target on ch1={b_verbose_shows_it} "
            f"parsed={cstatus_b_parsed!r}"
        )

        session.enter_host_mode()
        try:
            recheck = _probe_all_channel_links(
                session, link_status_frames, "B recheck", log
            )
            still_ch1 = 1 in _channels_connected_to(recheck, target_call)
            log.result(
                "T142", "PASS" if still_ch1 else "INCONCLUSIVE",
                f"still on channel 1={still_ch1}"
            )

            # P66b, B.6: the channel to disconnect at cleanup, and the
            # channel D.3 probes, is the CONNECTED one from THIS CO
            # recheck - never assumed to be channel 1, and never
            # whatever the active channel happens to be later (D.1/D.2
            # deliberately move the active channel elsewhere).
            connected_channels_now = _channels_connected_to(recheck, target_call)
            connected_channel = connected_channels_now[0] if connected_channels_now else 1
            log.line(f"connected_channel (from CO recheck) = {connected_channel}")

            # D.1 (P66, B.4 hypothesis): does the LAST $4x frame sent
            # decide the TNC's own "active channel" concept? Send
            # exactly one more CO query, on a channel known to be free
            # (3), and nothing else on $4x before leaving Host Mode.
            session.send_channel_frame(
                3, link_status_frames[3],
                note="D.1 CO ch3 (active-channel probe)",
            )
        finally:
            session.exit_host_mode()

        cstatus_after_d1 = session.query("CSTATUS")
        io_channel = parse_cstatus_io_channel(cstatus_after_d1)
        log.result(
            "T142 D.1", "INFO",
            f"io_channel_after_exit={io_channel} last_co_channel=3 "
            f"raw={cstatus_after_d1!r}"
        )

        # D.2 (P66): the operator's own observation, 28.09.2026 - after
        # Host -> verbose, getting back to Converse on the CONNECTED
        # channel needs an explicit channel switch, not just CONVERSE.
        # The connection on channel 1 is still up throughout D.1/D.2 -
        # nothing here disconnects it; cleanup happens only at the end.

        # D.2.1: CONVERSE on whatever the active channel is right now
        # (D.1's own result - channel 3, NOT connected), then a bare CR
        # to elicit a response. P66b, B.5: on an unconnected channel
        # the TNC sends every line typed in Converse as an UNPROTO UI
        # frame (TRM) - this transmits, so it needs confirm_tx() like
        # any other transmission, not just the queries around it.
        if confirm_tx(
            "Send CONVERSE + CR on the current (unconnected) active "
            "channel - may transmit an UNPROTO frame."
        ):
            d21_resp = session.send_and_read_until_idle(
                b"CONVERSE\r\n\r",
                note="D.2.1 CONVERSE (active channel), then CR",
                idle=2.0, max_total=10.0,
            )
            log.result("T142 D.2.1", "INFO", f"raw={d21_resp!r}")
        else:
            log.result("T142 D.2.1", "INFO", "skipped by operator")

        # D.2.2: COMMAND char, wait for cmd:.
        _confirm_command_prompt_light(session, "D.2.2", log)

        # D.2.3: switch to channel 1 with the TNC's own CHSWITCH
        # character - not tracked anywhere in SerialManager/AppConfig,
        # so measure it instead of guessing (CLAUDE.md's "never guess"
        # rule), then CONVERSE there. CHSWITCH's own query value is a
        # '$xx' hex string (parse_query_value()'s own format) - decoded
        # via chswitch_byte() into the real byte to send (P66a, B.1:
        # sending the three literal characters '$'/'7'/'C' instead of
        # the byte $7C was never a valid channel-switch command).
        chswitch_raw = session.query("CHSWITCH")
        chswitch_value = parse_query_value("CHSWITCH", chswitch_raw)
        chswitch_char = chswitch_byte(chswitch_value)
        log.line(
            f"D.2.3 CHSWITCH queried: {chswitch_value!r} -> "
            f"{chswitch_char!r} (raw={chswitch_raw!r})"
        )
        if chswitch_char is not None:
            d23_resp = session.send_and_read_until_idle(
                chswitch_char + b"1" + b"CONVERSE\r\n\r",
                note="D.2.3 CHSWITCH+1, CONVERSE, then CR",
                idle=2.0, max_total=10.0,
            )
            log.result("T142 D.2.3", "INFO", f"raw={d23_resp!r}")
        elif chswitch_value is None:
            log.result("T142 D.2.3", "SKIPPED", "CHSWITCH did not answer - not guessed")
        elif chswitch_value.strip() == "$00":
            log.result("T142 D.2.3", "SKIPPED", "CHSWITCH is $00 (not set)")
        else:
            log.result("T142 D.2.3", "SKIPPED", f"unparsed value {chswitch_value!r}")

        # D.2.4: COMMAND char, cmd:; log CSTATUS.
        _confirm_command_prompt_light(session, "D.2.4", log)
        cstatus_after_d2 = session.query("CSTATUS")
        log.result("T142 D.2.4", "INFO", f"CSTATUS={cstatus_after_d2!r}")

        # D.3 (P66b, B.3 technique check): does sending CO on the
        # CONNECTED channel as the LAST $4x frame before HOST OFF make
        # verbose CSTATUS call that channel IO afterwards - the P67
        # candidate technique for "back to the connected channel"?
        session.enter_host_mode()
        try:
            session.send_channel_frame(
                connected_channel, link_status_frames[connected_channel],
                note=f"D.3 CO ch{connected_channel} (last $4x before HOST OFF)",
            )
        finally:
            session.exit_host_mode()

        cstatus_after_d3 = session.query("CSTATUS")
        io_channel_d3 = parse_cstatus_io_channel(cstatus_after_d3)
        log.result(
            "T142 D.3",
            "PASS" if io_channel_d3 == connected_channel else "INCONCLUSIVE",
            f"io_channel={io_channel_d3} connected_channel={connected_channel} "
            f"raw={cstatus_after_d3!r}"
        )

        if confirm_tx(
            f"Send CONVERSE + CR on channel {connected_channel} (now "
            f"the active/IO channel, D.3) - may transmit on the air if "
            f"it turns out not to actually be connected."
        ):
            # P67, Teil D H.4: the 28.09.2026 run's own TinyBox reply
            # arrived after the old 2s idle window had already closed
            # the read (visible only in the following cmd: check) -
            # widened to 10s idle / 20s max_total.
            d3_converse_resp = session.send_and_read_until_idle(
                b"CONVERSE\r\n\r",
                note=f"D.3 CONVERSE (ch{connected_channel}), then CR",
                idle=10.0, max_total=20.0,
            )
            log.result("T142 D.3 CONVERSE", "INFO", f"raw={d3_converse_resp!r}")
        else:
            log.result("T142 D.3 CONVERSE", "INFO", "skipped by operator")

        _confirm_command_prompt_light(session, "D.3 recovery", log)

        # Cleanup (P66b, B.6): disconnect the CONNECTED channel via a
        # Host Mode DI, before HOST OFF - never a verbose DISCONNECT on
        # whatever channel happens to be active (B.6's own finding: that
        # was channel 3, a free probe channel from D.1, while the real
        # connection on channel 1 stayed up until the counterpart's own
        # timeout).
        if input(
            f"Disconnect channel {connected_channel} now? [Y/n] "
        ).strip().lower() in ("", "y"):
            session.enter_host_mode()
            try:
                session.send_channel_frame(
                    connected_channel,
                    HostModeProtocol.cmd_disconnect(connected_channel),
                    note=f"cleanup DI ch{connected_channel}",
                )
                session._pump(0.3)
            finally:
                session.exit_host_mode()
            log.line(f"cleanup: sent DI on channel {connected_channel}")
        else:
            log.result("T142 cleanup", "INFO", "left connected by operator choice")
    finally:
        for cmd in commands:
            verify_restore(
                cmd,
                lambda c=cmd: session.query(c),
                lambda v, c=cmd: session.set_verbose(c, v),
                originals[cmd],
                log,
            )


# ===========================================================================
# P69 -- channel_probe measurement (unproto on free channels 3/9, which
# channel an incoming connect lands on). MEASURES ONLY (hw_check rule 6) -
# P70 (channel bar MON + 0-9) is built on these findings, not this
# package's job. No new frame builder: cmd_unproto()/cmd_connect()/
# cmd_disconnect()/cmd_link_status() are the app's own; data frames go
# through Session.send_data_channel(). Every transmission goes through
# confirm_tx() via the helpers below.
# ===========================================================================

_CHANNEL_PROBE_PATH = "P69TST"
_CHANNEL_PROBE_TARGET = "OE3GAS-1"   # TinyBox, the same counterpart as T141/T142


# ---------------------------------------------------------------------------
# P69a Teil A -- operator_step(): the ONE place channel_probe tells the
# operator what to do, and on WHICH of the two PCs (PC 1 = this program and
# the PK-232, PC 2 = Direwolf / TinyBox / QtTermTCP; docs/DEVICES.md).
# ---------------------------------------------------------------------------

WHERE_PC1 = "PC 1  - this program / PK-232"
WHERE_PC2 = "PC 2  - Direwolf / TinyBox / QtTermTCP"
_OPERATOR_STEP_RULE = "=" * 62


@dataclasses.dataclass(frozen=True)
class ProbeStep:
    """One planned operator step. The whole plan exists BEFORE the first
    transmission, so 'STEP n of N' is counted, not estimated."""
    title: str
    where: str
    minutes: int
    do: list
    then: str


class StepRun:
    """Counts the operator steps of one run against its planned list."""

    def __init__(self, steps: list, log: Optional["RunLog"] = None):
        self.steps = list(steps)
        self.log = log
        self.n = 0

    @property
    def total(self) -> int:
        return len(self.steps)

    @property
    def current(self) -> Optional[ProbeStep]:
        return self.steps[self.n - 1] if self.n else None

    def advance(self, title: str) -> ProbeStep:
        """Move to the next planned step; it must be the one named *title*
        (a plan and a run that drift apart would show a wrong 'of N')."""
        if self.n >= self.total:
            raise HWCheckError(f"operator step {title!r} is not in the plan")
        step = self.steps[self.n]
        if step.title != title:
            raise HWCheckError(
                f"operator step {title!r} does not match the plan ({step.title!r})"
            )
        self.n += 1
        return step


def operator_step(
    run: "StepRun", title: str, where: str, do: list, then: str,
) -> None:
    """Print one operator instruction block (always the same shape) and
    log its number and title. *where* is exactly one of WHERE_PC1/WHERE_PC2."""
    if where not in (WHERE_PC1, WHERE_PC2):
        raise ValueError(f"where must be WHERE_PC1 or WHERE_PC2, got {where!r}")
    step = run.advance(title)
    print()
    print(_OPERATOR_STEP_RULE)
    unit = "minute" if step.minutes == 1 else "minutes"
    print(f"STEP {run.n} of {run.total}   {title}   (about {step.minutes} {unit})")
    print(f"WHERE: {where}")
    print("DO:")
    for i, action in enumerate(do, 1):
        print(f"  {i}. {action}")
    print(f"THEN: {then}")
    print(_OPERATOR_STEP_RULE)
    if run.log is not None:
        run.log.line(f"STEP {run.n} of {run.total}: {title} [{where.split()[0]} {where.split()[1]}]")


def _split_blocks(pasted: str) -> list[str]:
    """Direwolf separates decoded packets by blank lines - one block is
    one packet (its header line plus the detail lines around it)."""
    return [b for b in re.split(r"\n\s*\n", pasted) if b.strip()]


def learn_iframe_marker(pasted: str) -> Optional[str]:
    """Direwolf's own frame-type notation for an I-frame ('<I S0 R0 ...>',
    as opposed to '<UI ...>') found in *pasted*, or None. B.3's CR on
    $20 is a known I-frame to the TinyBox, so this is LEARNED from that
    paste, never hard-coded (P69 Teil B) - the caller logs what it found."""
    m = re.search(r"<I[ >]", pasted)
    return m.group(0) if m else None


def classify_decoder_line(
    pasted: str, src: str, dest: str, text: str,
    iframe_marker: Optional[str] = None,
) -> str:
    """What a second station's decoder shows for one transmitted data
    frame (P69 Teil B). Pure - no serial interface. Results:
      'ui'        - a packet block has 'SRC>DEST' and *text* (and no
                    I-frame marking): sent as an UNPROTO UI frame.
      'connected' - the block with *text* carries *iframe_marker*
                    (learned via learn_iframe_marker()): an I-frame on
                    a connection.
      'absent'    - *text* is nowhere in *pasted* (or nothing pasted).
      'unknown'   - *text* is there, but in a format that is neither
                    (e.g. no marker learned yet and not addressed to
                    *dest*).
    """
    if not text or text not in pasted:
        return "absent"
    header = re.compile(re.escape(src) + r">" + re.escape(dest) + r"(?![\w-])", re.I)
    for block in _split_blocks(pasted):
        if text not in block:
            continue
        if iframe_marker and iframe_marker in block:
            return "connected"
        if header.search(block):
            return "ui"
    return "unknown"


def find_incoming_channel(frames: list) -> Optional[int]:
    """The channel of the first '$5n ... CONNECTED to ...' link message
    (TRM 4.3.2: CTL $50-$59) in *frames*, or None. The channel comes off
    the frame's own CTL byte via .channel, never from send order."""
    for f in frames:
        if 0x50 <= f.ctl <= 0x59 and "connected to" in (f.text or "").lower():
            return f.channel
    return None


def format_links_line(results: dict) -> str:
    """'links: 0=free 1=connected:OE3GAS-1 ...' from
    _probe_all_channel_links() results. 'free' only for a decoded,
    error-free, partner-less channel - anything else says what it is,
    never guessed as free."""
    parts = []
    for ch in sorted(results):
        r = results[ch]
        if r.unparsed:
            what = "?"
        elif r.error_code is not None:
            what = f"err{r.error_code:02X}"
        elif r.connected:
            what = f"connected:{r.partner}"
        elif r.partner:
            what = f"state{r.state}:{r.partner}"
        else:
            what = "free"
        parts.append(f"{ch}={what}")
    return "links: " + " ".join(parts)


def _probe_links(session: Session, frames: dict, label: str, log: RunLog) -> dict:
    """CO on channels 0-9 plus the one-line summary the spec asks for
    after EVERY step in Host Mode."""
    results = _probe_all_channel_links(session, frames, label, log)
    log.line(f"{label} {format_links_line(results)}")
    return results


def _probe_transmit(
    session: Session, log: RunLog, prompt: str, channel: int, text: str,
) -> bool:
    """The only data-frame transmission in channel_probe: confirm_tx()
    first, then the frame ($2n on *channel*). False if declined."""
    if not confirm_tx(prompt):
        log.line(f"skipped by operator: data on ch{channel} {text!r}")
        return False
    session.send_data_channel(channel, text)
    return True


def _probe_connect(
    session: Session, log: RunLog, target: str, channel: int,
) -> bool:
    """The only connect in channel_probe (Host Mode CO frame from
    HostModeProtocol.cmd_connect()), behind confirm_tx()."""
    if not confirm_tx(f"Connect to {target!r} on channel {channel}, from Host Mode."):
        log.line(f"skipped by operator: connect {target!r} on ch{channel}")
        return False
    session.send_channel_frame(
        channel, HostModeProtocol.cmd_connect(target, channel=channel),
        note=f"connect ch{channel}",
    )
    return True


def _pump_capture(session: Session, seconds: float, log: RunLog, label: str) -> list:
    """Pump the Qt loop for *seconds*, log and return every frame seen."""
    captured: list = []
    session.sm.frame_received.connect(captured.append)
    try:
        session._pump(seconds)
    finally:
        session.sm.frame_received.disconnect(captured.append)
    for f in captured:
        log.line(
            f"{label} << ctl=0x{f.ctl:02X} ch={f.channel} "
            f"data={f.data!r} text={f.text!r}"
        )
    return captured


def _probe_disconnect_all(
    session: Session, log: RunLog, frames: dict, label: str,
) -> None:
    """In Host Mode: DI (behind confirm_tx()) on every channel whose CO
    shows a connection, then re-check. Never assumes which channel."""
    results = _probe_links(session, frames, f"{label} before DI", log)
    busy = [
        ch for ch, r in sorted(results.items())
        if not r.unparsed and r.error_code is None and (r.connected or r.partner)
    ]
    for ch in busy:
        if confirm_tx(f"{label}: disconnect channel {ch} (Host Mode DI)."):
            session.send_channel_frame(
                ch, HostModeProtocol.cmd_disconnect(ch), note=f"{label} DI ch{ch}",
            )
            session._pump(0.5)
        else:
            log.line(f"{label}: left ch{ch} connected by operator choice")
    if busy:
        _probe_links(session, frames, f"{label} after DI", log)


def _channel_probe_vhf_check(session: Session, log: RunLog, tag: str) -> Optional[dict]:
    """Query VHF/HBAUD and run ensure_vhf_1200(). Returns the originals
    to restore, or None if the run must stop."""
    originals = {c: parse_query_value(c, session.query(c)) for c in ("VHF", "HBAUD")}
    missing = [c for c, v in originals.items() if v is None]
    if missing:
        log.result(tag, "SKIPPED", f"original value(s) not parseable -- not touching: {missing}")
        return None
    return originals if ensure_vhf_1200(session, log, tag, originals) else None


def split_paste_by_marker(
    pasted: str, markers: dict,
) -> tuple[dict, list]:
    """P69a Teil C: assign ONE long decoder paste to the steps that caused
    it. *markers* maps a step key to the unique text that step sent. A
    step's segment runs from the packet block holding its marker up to the
    block holding the next step's marker (the last one runs to the end, so
    B.3's CR I-frame belongs to B.3). Returns (segments, missing): steps
    whose marker is nowhere in the paste are listed in *missing* and get no
    segment. Pure - no serial interface."""
    blocks = _split_blocks(pasted)
    first_block: dict = {}
    for key, text in markers.items():
        for i, block in enumerate(blocks):
            if text and text in block:
                first_block[key] = i
                break
    missing = [k for k in markers if k not in first_block]
    order = sorted(first_block, key=first_block.get)
    segments: dict = {}
    for j, key in enumerate(order):
        start = first_block[key]
        end = first_block[order[j + 1]] if j + 1 < len(order) else len(blocks)
        segments[key] = "\n\n".join(blocks[start:max(end, start + 1)])
    return segments, missing


def channel_probe_steps(part: str, mycall: str, target: str) -> list:
    """The complete, ordered operator plan for *part* ('B', 'C' or 'all'),
    as (key, ProbeStep) pairs. Built before the first transmission, so
    'STEP n of N' is a count. The ONLY place channel_probe words its
    instructions; printing goes through operator_step()."""
    me = mycall or "<TNC MYCALL>"
    plan: list = []

    def add(key, title, where, minutes, do, then):
        plan.append((key, ProbeStep(title, where, minutes, do, then)))

    answer_tx = (
        "answer each question on this screen with y (send) or n (skip), "
        "then press ENTER. The next step follows by itself."
    )
    if part in ("B", "all"):
        add("B.1", "T146 B.1  UNPROTO frame on the free channel 3", WHERE_PC1, 2,
            [f"Answer y to the question on this screen: this program sends ONE "
             f"frame from {me} to {_CHANNEL_PROBE_PATH} on channel 3."],
            answer_tx)
        add("B.2", "T146 B.2  UNPROTO frame on the free channel 9", WHERE_PC1, 2,
            [f"Answer y to the question on this screen: this program sends ONE "
             f"frame from {me} to {_CHANNEL_PROBE_PATH} on channel 9."],
            answer_tx)
        add("B.3", "T146 B.3  free channel 3 while channel 0 is connected",
            WHERE_PC1, 3,
            [f"Answer y to connect channel 0 of the TNC ({me}) to {target}; "
             f"the TinyBox answers by itself.",
             "Answer y to send ONE frame on channel 3.",
             f"Answer y to send one empty line (CR) to {target} on channel 0.",
             "Answer y to disconnect again."],
            answer_tx)
        add("B.4", "T146 B.4  copy the decoder output", WHERE_PC2, 2,
            [f"In the Direwolf window, find the line containing 'P69 B1' "
             f"(sent by {me}).",
             "Select everything from that line down to the last line and copy it."],
            'go back to PC 1, paste it here, then type a line with a single "." '
            "and press ENTER.")
    if part in ("C", "all"):
        for label, pair in (("C", ("C.1", "C.2")), ("C.3", ("C.3.1", "C.3.2"))):
            caller_1, caller_2 = "OE3GAS-2", "OE3GAS-3"
            if label == "C.3":
                add("C.3.free", "T147 C.3  free both QtTermTCP sessions",
                    WHERE_PC2, 1,
                    ["In QtTermTCP, disconnect BOTH sessions (OE3GAS-2 and OE3GAS-3).",
                     "Check that both sessions show 'disconnected'."],
                    "go back to PC 1 and press ENTER here. The test then sets "
                    "USERS 10 and repeats the calls.")
            first, second = pair
            add(f"{label}.1.call", f"T147 {first}  first incoming call",
                WHERE_PC2, 2,
                [f"In QtTermTCP, use the session with callsign {caller_1}.",
                 f"Connect to {me}.",
                 "Wait until QtTermTCP shows it is connected - or 30 seconds pass.",
                 "Leave this connection OPEN."],
                "go back to PC 1 and press ENTER here (recording also ends by "
                "itself after 120 seconds).")
            add(f"{label}.1.saw", f"T147 {first}  what QtTermTCP shows",
                WHERE_PC2, 1,
                [f"Look at the QtTermTCP session with callsign {caller_1}.",
                 f"What does QtTermTCP show for {caller_1}? "
                 f"(connected / busy / nothing)"],
                "go back to PC 1, type the answer and press ENTER.")
            add(f"{label}.2.occupy", f"T147 {second}  occupy channel 0",
                WHERE_PC1, 1,
                [f"Answer y to connect channel 0 of the TNC to {target}; the "
                 f"TinyBox answers by itself.",
                 "Wait about 30 seconds until the next step appears."],
                "answer y (connect) or n (skip) and press ENTER.")
            add(f"{label}.2.call", f"T147 {second}  second incoming call",
                WHERE_PC2, 2,
                [f"In QtTermTCP, use the session with callsign {caller_2} "
                 f"(a DIFFERENT callsign than before).",
                 f"Connect to {me}.",
                 "Wait until QtTermTCP shows it is connected, busy, or 30 "
                 "seconds pass.",
                 "Leave this connection OPEN."],
                "go back to PC 1 and press ENTER here (recording also ends by "
                "itself after 120 seconds).")
            add(f"{label}.2.saw", f"T147 {second}  what QtTermTCP shows",
                WHERE_PC2, 1,
                [f"Look at the QtTermTCP session with callsign {caller_2}.",
                 f"What does QtTermTCP show for {caller_2}? "
                 f"(connected / busy / nothing)"],
                "go back to PC 1, type the answer and press ENTER.")
    return plan


class ProbePlan:
    """The operator plan of one run: steps by key plus the StepRun that
    counts them. show()/skip() are the only ways a step is consumed."""

    def __init__(self, part: str, mycall: str, target: str,
                 log: Optional["RunLog"] = None):
        keyed = channel_probe_steps(part, mycall, target)
        self.by_key = dict(keyed)
        self.run = StepRun([step for _, step in keyed], log)
        self.log = log

    def show(self, key: str) -> None:
        s = self.by_key[key]
        operator_step(self.run, s.title, s.where, s.do, s.then)

    def skip(self, key: str) -> None:
        """A step the operator's own 'n' made pointless: counted, not shown."""
        title = self.by_key[key].title
        self.run.advance(title)
        if self.log is not None:
            self.log.line(f"STEP {self.run.n} of {self.run.total}: {title} - skipped")


def channel_probe_checklist(part: str, target: str) -> list:
    """Preparation items, each confirmed with ENTER (P69a Teil B)."""
    items = ["PC 2: Direwolf is running and shows decoded packets."]
    # The TinyBox is also the counterpart of C.2's channel-0 occupation.
    items.append(f"PC 2: the TinyBox {target} is running.")
    if part in ("C", "all"):
        items.append(
            "PC 2: QtTermTCP has two sessions with the callsigns OE3GAS-2 "
            "and OE3GAS-3, BOTH disconnected."
        )
    items.append(
        "PC 1 + PC 2: both stations are on the same APRS-free frequency, "
        "dummy load or minimum power."
    )
    items.append("PC 1: PK232PY is closed.")
    return items


def _print_overview(plan: ProbePlan, part: str) -> None:
    print()
    print(f"channel_probe --part {part}: {plan.run.total} steps, about "
          f"{sum(s.minutes for s in plan.run.steps)} minutes")
    for i, step in enumerate(plan.run.steps, 1):
        print(f"  {i:2d}. {step.where.split()[0]} {step.where.split()[1]}  "
              f"{step.title}  (~{step.minutes} min)")


def _preparation_checklist(
    part: str, target: str, read_line: Callable[[str], str] = input,
    ask: bool = True,
) -> None:
    items = channel_probe_checklist(part, target)
    print()
    print("Before we start - check each item:")
    for i, item in enumerate(items, 1):
        if ask:
            read_line(f"  [{i}/{len(items)}] {item}  ENTER when done: ")
        else:
            print(f"  [{i}/{len(items)}] {item}")


def _key_ready() -> bool:
    """True if the operator has typed something (non-blocking)."""
    if msvcrt is not None:
        return msvcrt.kbhit()
    return bool(select.select([sys.stdin], [], [], 0)[0])


def wait_for_enter(
    pump: Callable[[float], None], max_seconds: float,
    key_ready: Callable[[], bool] = _key_ready,
    read_line: Callable[[], str] = input,
    clock: Callable[[], float] = time.monotonic,
) -> bool:
    """Wait for the operator's ENTER WITHOUT blocking the Qt loop: pump in
    short slices so frames are delivered while the operator works at PC 2.
    True on ENTER; False (after a notice) once *max_seconds* pass."""
    deadline = clock() + max_seconds
    while clock() < deadline:
        if key_ready():
            read_line()
            return True
        pump(0.1)
    print(f"No ENTER after {max_seconds:.0f} seconds - continuing by itself.")
    return False


@contextlib.contextmanager
def _host_mode_guard(session: Session, log: RunLog, frames: dict, label: str):
    """Host Mode for a block of steps. Ctrl-C inside it first disconnects
    whatever the last CO query shows connected (behind confirm_tx()), and
    Host Mode is left in every case (P69a Teil F)."""
    session.enter_host_mode()
    try:
        yield
    except KeyboardInterrupt:
        try:
            _probe_disconnect_all(session, log, frames, f"{label} stop")
        except (Exception, KeyboardInterrupt) as exc:  # best effort
            log.line(f"{label}: cleanup on stop incomplete ({exc!r})")
        raise
    finally:
        session.exit_host_mode()


def _channel_probe_b(
    session: Session, log: RunLog, mycall: str, target: str, frames: dict,
    un_frame: bytes, plan: ProbePlan,
) -> None:
    def stamp() -> str:
        return datetime.datetime.now().strftime("%H:%M:%S")

    sent: dict = {}   # step key -> the unique text that went out

    def free_channel_round(step: str, channel: int) -> None:
        plan.show(step)
        text = f"P69 {step.replace('.', '')} ch{channel} {stamp()}"
        with _host_mode_guard(session, log, frames, step):
            session.drain_pending_frames()
            session.send_frame(un_frame, note=f"{step} UN {_CHANNEL_PROBE_PATH}")
            session._pump(0.5)
            _probe_links(session, frames, f"{step} pre", log)
            ok = _probe_transmit(
                session, log,
                f"{step}: data frame ${0x20 + channel:02X} on the FREE channel "
                f"{channel}, UNPROTO {_CHANNEL_PROBE_PATH} - should go out as "
                f"a UI frame.\nText: {text!r}",
                channel, text,
            )
            _pump_capture(session, 2.0, log, step)
            _probe_links(session, frames, f"{step} post", log)
        if ok:
            sent[step] = text
        else:
            log.result(f"T146 {step}", "INFO", "skipped by operator")

    free_channel_round("B.1", 3)
    free_channel_round("B.2", 9)

    # B.3: connection on channel 0, data on free channel 3, then CR on $20.
    plan.show("B.3")
    text3 = f"P69 B3 ch3 {stamp()}"
    sent3 = False
    with _host_mode_guard(session, log, frames, "B.3"):
        session.drain_pending_frames()
        session.send_frame(un_frame, note=f"B.3 UN {_CHANNEL_PROBE_PATH}")
        session._pump(0.5)
        if _probe_connect(session, log, target, 0):
            _pump_capture(session, 30.0, log, "B.3 connect")
            _probe_links(session, frames, "B.3 connected", log)
            sent3 = _probe_transmit(
                session, log,
                f"B.3: data frame $23 on channel 3 while channel 0 is "
                f"connected to {target}.\nText: {text3!r}",
                3, text3,
            )
            _pump_capture(session, 2.0, log, "B.3 ch3")
            _probe_links(session, frames, "B.3 after ch3", log)
            if _probe_transmit(
                session, log,
                f"B.3: a single CR on channel 0 (an I-frame to {target}; "
                f"its own prompt comes back) - used to LEARN how the "
                f"decoder marks I-frames.",
                0, "\r",
            ):
                _pump_capture(session, 10.0, log, "B.3 CR")
        _probe_disconnect_all(session, log, frames, "B.3 cleanup")
    _confirm_command_prompt_light(session, "B.3", log)
    if sent3:
        sent["B.3"] = text3
    else:
        log.result("T146 B.3", "INFO", "skipped by operator")

    # B.4: ONE paste for everything that went out.
    if not sent:
        plan.skip("B.4")
        return
    plan.show("B.4")
    pasted = read_pasted_block(
        'Paste the decoder (Direwolf) output, then a line with a single ".":'
    )
    segments, missing = split_paste_by_marker(pasted, sent)
    for step in sent:
        if step in missing:
            log.result(
                f"T146 {step}", "FAIL",
                f"not found in the pasted decoder output (text={sent[step]!r})",
            )
            continue
        marker = None
        if step == "B.3":
            marker = learn_iframe_marker(segments[step])
            log.line(f"B.3 I-frame notation learned from the paste: {marker!r}")
        verdict = classify_decoder_line(
            segments[step], mycall, _CHANNEL_PROBE_PATH, sent[step], marker,
        )
        log.result(
            f"T146 {step}", "PASS" if verdict == "ui" else "FAIL",
            f"classification={verdict} text={sent[step]!r}"
            + (f" marker={marker!r}" if step == "B.3" else ""),
        )


def _channel_probe_incoming_round(
    session: Session, log: RunLog, frames: dict, target: str, label: str,
    plan: ProbePlan,
) -> None:
    """One first call plus a second call with channel 0 occupied (C.1 and
    C.2, repeated as C.3.1/C.3.2 with USERS 10). Enters and leaves Host
    Mode itself.

    The capture is connected BEFORE the operator is told to call and stays
    connected until ENTER (max 120 s): SerialManager emits frame_received
    from its reader/poll thread, Qt queues it for this thread, and
    wait_for_enter() pumps in 0.1 s slices - so nothing arrives unseen
    while the operator works at PC 2."""
    with _host_mode_guard(session, log, frames, label):
        session.drain_pending_frames()
        for k, who in ((1, "first"), (2, "second")):
            phase = f"{label}.{k}"
            if k == 2:
                results = _probe_links(session, frames, f"{phase} pre", log)
                if not (0 in results and (results[0].connected or results[0].partner)):
                    plan.show(f"{label}.2.occupy")
                    if _probe_connect(session, log, target, 0):
                        _pump_capture(session, 30.0, log, f"{phase} occupy ch0")
                    _probe_links(session, frames, f"{phase} ch0 occupied", log)
                else:
                    plan.skip(f"{label}.2.occupy")
            if not confirm_tx(
                f"{phase}: the TNC will ANSWER the {who} incoming connect on "
                f"the air (this keys the transmitter). The next step is at PC 2."
            ):
                log.result(f"T147 {phase}", "INFO", "skipped by operator")
                plan.skip(f"{label}.{k}.call")
                plan.skip(f"{label}.{k}.saw")
                continue
            captured: list = []
            session.sm.frame_received.connect(captured.append)
            try:
                plan.show(f"{label}.{k}.call")
                wait_for_enter(session._pump, 120.0)
                session._pump(0.3)
            finally:
                session.sm.frame_received.disconnect(captured.append)
            for f in captured:
                log.line(
                    f"{phase} << ctl=0x{f.ctl:02X} ch={f.channel} "
                    f"data={f.data!r} text={f.text!r}"
                )
            channel = find_incoming_channel(captured)
            _probe_links(session, frames, f"{phase} post", log)
            plan.show(f"{label}.{k}.saw")
            seen = input("Your answer (connected / busy / nothing): ").strip()
            log.result(
                f"T147 {phase}", "INFO",
                f"incoming_channel={channel} accepted={channel is not None} "
                f"operator={seen!r}",
            )
        _probe_disconnect_all(session, log, frames, f"{label} cleanup")
    _confirm_command_prompt_light(session, f"{label} end", log)


def _channel_probe_c(
    session: Session, log: RunLog, frames: dict, target: str, plan: ProbePlan,
) -> None:
    _channel_probe_incoming_round(session, log, frames, target, "C", plan)
    plan.show("C.3.free")
    input("(ENTER to continue) ")
    log.line("C.3: USERS 10 (verbose), then the same two calls again")
    session.set_verbose("USERS", "10")
    _channel_probe_incoming_round(session, log, frames, target, "C.3", plan)


def _channel_probe_dry_run(
    session: Session, log: RunLog, part: str, frames: dict, un_frame: bytes,
    plan: ProbePlan, target: str,
) -> None:
    log.line(
        "[dry-run] would normalize(), check VHF/HBAUD 1200, query and "
        "log UNPROTO/USERS/MYCALL (UNPROTO/USERS restored at the end). "
        "EVERY transmission below sits behind confirm_tx(); after every "
        "Host Mode step CO on channels 0-9 is logged as 'links: ...'."
    )
    _print_overview(plan, part)
    _preparation_checklist(part, target, ask=False)
    if part in ("B", "all"):
        log.line(f"[dry-run] Part B: UN {_CHANNEL_PROBE_PATH}")
        session.send_frame(un_frame, note=f"UN {_CHANNEL_PROBE_PATH}")
        for step, ch in (("B.1", 3), ("B.2", 9)):
            plan.show(step)
            text = f"P69 {step.replace('.', '')} ch{ch} HH:MM:SS"
            log.line(
                f"[dry-run] {step}: data frame ${0x20 + ch:02X} on free "
                f"channel {ch}: {text!r}"
            )
            session.send_data_channel(ch, text)
        plan.show("B.3")
        session.send_channel_frame(
            0, HostModeProtocol.cmd_connect(target, channel=0),
            note="B.3 connect ch0",
        )
        log.line("[dry-run] B.3: data frame $23 on channel 3 while ch0 is connected")
        session.send_data_channel(3, "P69 B3 ch3 HH:MM:SS")
        log.line("[dry-run] B.3: CR on $20 (I-frame; learns the decoder's I-frame notation)")
        session.send_data_channel(0, "\r")
        log.line("[dry-run] B.3: DI on ch0")
        session.send_channel_frame(
            0, HostModeProtocol.cmd_disconnect(0), note="B.3 DI ch0"
        )
        plan.show("B.4")
        log.line("[dry-run] B.4: ONE decoder paste, split per step by its unique text")
        log.result("T146", "INFO", "dry-run, nothing sent")
    if part in ("C", "all"):
        log.line(
            "[dry-run] Part C: recording from before the instruction until "
            "ENTER (max 120 s) per call, then DI on all connected channels"
        )
        for label in ("C", "C.3"):
            if label == "C.3":
                plan.show("C.3.free")
                log.line("[dry-run] C.3: set USERS 10 (verbose), repeat the calls, restore USERS")
            plan.show(f"{label}.1.call")
            plan.show(f"{label}.1.saw")
            plan.show(f"{label}.2.occupy")
            plan.show(f"{label}.2.call")
            plan.show(f"{label}.2.saw")
        for ch in range(10):
            session.send_channel_frame(ch, frames[ch], note=f"CO ch{ch}")
        log.result("T147", "INFO", "dry-run, nothing sent")


def test_channel_probe(session: Session, log: RunLog, part: str = "all") -> None:
    if part not in ("B", "C", "all"):
        raise ValueError(f"part must be B, C or all, got {part!r}")
    log.line(
        "--- Channel probe: UNPROTO on free channels 3/9, channel of an "
        f"incoming connect (part {part}) ---"
    )
    un_frame = HostModeProtocol.cmd_unproto(_CHANNEL_PROBE_PATH)
    frames = {ch: HostModeProtocol.cmd_link_status(ch) for ch in range(10)}
    tag = "T146" if part != "C" else "T147"

    if session.dry_run:
        plan = ProbePlan(part, "<TNC MYCALL>", _CHANNEL_PROBE_TARGET, log)
        _channel_probe_dry_run(
            session, log, part, frames, un_frame, plan, _CHANNEL_PROBE_TARGET,
        )
        return

    session.normalize()
    raw = {c: session.query(c) for c in ("UNPROTO", "USERS", "MYCALL")}
    for cmd, value in raw.items():
        log.line(f"{cmd} (found): {value!r}")
    originals = {c: parse_query_value(c, raw[c]) for c in ("UNPROTO", "USERS")}
    mycall = parse_query_value("MYCALL", raw["MYCALL"]) or ""
    if not mycall or any(v is None for v in originals.values()):
        log.result(
            tag, "SKIPPED",
            f"MYCALL/UNPROTO/USERS not parseable -- not touching them "
            f"(mycall={mycall!r} originals={originals!r})",
        )
        return
    target = input(
        f"Counterpart callsign for the connect on channel 0 [{_CHANNEL_PROBE_TARGET}]? "
    ).strip() or _CHANNEL_PROBE_TARGET

    plan = ProbePlan(part, mycall, target, log)
    _print_overview(plan, part)
    _preparation_checklist(part, target)
    if input("Ready to continue? [y/N] ").strip().lower() != "y":
        log.result(tag, "INFO", "skipped by operator")
        return

    vhf_originals: dict = {}
    stopped = False
    try:
        got = _channel_probe_vhf_check(session, log, tag)
        if got is None:
            return
        vhf_originals = got
        if part in ("B", "all"):
            _channel_probe_b(session, log, mycall, target, frames, un_frame, plan)
        if part in ("C", "all"):
            _channel_probe_c(session, log, frames, target, plan)
    except KeyboardInterrupt:
        stopped = True
    finally:
        for cmd, value in {**originals, **vhf_originals}.items():
            if value is None:
                continue
            verify_restore(
                cmd, lambda c=cmd: session.query(c),
                lambda v, c=cmd: session.set_verbose(c, v), value, log,
            )
    if stopped:
        step = plan.run.current
        if step is None:
            where = f"before STEP 1 of {plan.run.total}"
            next_part = part
        else:
            where = f"at STEP {plan.run.n} of {plan.run.total} ({step.title})"
            next_part = "B" if step.title.startswith("T146") else "C"
        log.line(f"Stopped {where}. Next run: --part {next_part}")
        log.result(tag, "INFO", "stopped by operator")


# ===========================================================================
# CLI
# ===========================================================================

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="hw_check.py",
        description=(
            "Solo hardware verification for a real PK-232MBX "
            "(P14/P17/P20/P24). t17/t103/pthuff/t111/t112/mi only query/"
            "set parameters; siam is receive-only but needs a tuned "
            "receiver; maildrop is an interactive local (serial, not "
            "radio) recording terminal; maildrop_host and mdcheck_scan "
            "are read-only Host Mode probes; maildrop_session drives the "
            "real MailDropSession end to end (T119); t101 TRANSMITS and "
            "needs a second receiver; link_carry and link_carry_host "
            "(P65, T141/T142) measure whether an AX.25 Packet connection "
            "and the active operating mode survive the verbose<->Host "
            "Mode switch -- both need a real counterpart station and are "
            "deliberately not part of 'all'."
        ),
    )
    p.add_argument(
        "test",
        choices=[
            "t17", "t103", "pthuff", "t101", "siam", "t111", "t112",
            "mi", "maildrop", "maildrop_host", "mdcheck_scan",
            "maildrop_session", "aprs_query", "aprs_tx", "aprs_reject",
            "link_carry", "link_carry_host", "channel_probe",
            "all",
        ],
    )
    p.add_argument(
        "--part", choices=["B", "C", "all"], default="all",
        help="channel_probe only: B = free-channel UNPROTO frames (T146), "
             "C = incoming connects (T147), all = both (default)"
    )
    p.add_argument("--port", help="Serial port, e.g. COM3 (default: pk232py.ini)")
    p.add_argument("--baud", type=int, help="Baud rate (default: pk232py.ini)")
    p.add_argument(
        "--dry-run", action="store_true",
        help="Show what each test would send; never opens the port"
    )
    p.add_argument(
        "--seconds", type=float, default=60.0,
        help="siam only: capture duration in seconds (default: 60)"
    )
    p.add_argument(
        "--skip-power-cycle", action="store_true",
        help="maildrop only: skip the power-cycle test (already PASSed "
             "in an earlier round, Testplan T116)"
    )
    p.add_argument(
        "--skip-upload", action="store_true", default=True,
        help="maildrop_session only: skip ParamsUploader before entering "
             "Host Mode (default: skipped -- parameters are already "
             "verified via other subcommands, and a full upload costs "
             "about a minute)"
    )
    p.add_argument(
        "--abort-test", action="store_true",
        help="maildrop_session only: add the --abort-test probe (reopen, "
             "start a send(), abort() it after the subject, confirm the "
             "recovery path runs and reports failure, never success)"
    )
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)

    cfg_mgr = ConfigManager()
    cfg_mgr.load()
    app_config = cfg_mgr.app

    port = args.port or app_config.tnc.port
    baud = args.baud or app_config.tnc.tbaud
    if not args.dry_run and not port:
        print(
            "No port given and none configured in pk232py.ini - use --port COM3",
            file=sys.stderr,
        )
        return 2

    log_path = None
    if not args.dry_run:
        log_dir = _REPO_ROOT / "hw_logs"
        log_dir.mkdir(exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = log_dir / f"{stamp}_{args.test}.log"

    log = RunLog(log_path)
    log.line(
        f"hw_check.py {args.test} -- port={port!r} baud={baud} "
        f"dry_run={args.dry_run}"
    )

    session = Session(port or "DRYRUN", baud or 9600, args.dry_run, log, app_config)

    # P30.2: maildrop_session gets byte-level capture of the init phase
    # (SerialManager's own set_port_factory() seam, no monkeypatching) and
    # pk232py.comm raised to DEBUG, written into the same log file - both
    # scoped to this one subcommand, since it is the one with a reported,
    # otherwise-invisible wakeup failure (P30).
    capture_box: dict = {}
    comm_log_handler: Optional[_RunLogHandler] = None
    comm_logger = logging.getLogger("pk232py.comm")
    if args.test == "maildrop_session" and not args.dry_run:
        def _capturing_port_factory(**kw):
            wrapper = LoggingSerialPort(serial.Serial(**kw), log)
            capture_box["port"] = wrapper
            return wrapper

        session.sm.set_port_factory(_capturing_port_factory)

        comm_log_handler = _RunLogHandler(log)
        comm_log_handler.setLevel(logging.DEBUG)
        comm_logger.addHandler(comm_log_handler)
        comm_logger.setLevel(logging.DEBUG)

    test_fns: dict[str, list] = {
        "t17":    [lambda s, l: test_t17(s, l)],
        "t103":   [lambda s, l: test_t103(s, l, app_config)],
        "pthuff": [lambda s, l: test_pthuff(s, l, app_config)],
        "t101":   [lambda s, l: test_t101(s, l)],
        "siam":   [lambda s, l: test_siam(s, l, args.seconds)],
        "t111":   [lambda s, l: test_t111(s, l)],
        "t112":   [lambda s, l: test_t112(s, l, app_config)],
        "mi":       [lambda s, l: test_mi(s, l)],
        "maildrop": [lambda s, l: test_maildrop(s, l, args.skip_power_cycle)],
        "maildrop_host": [lambda s, l: test_maildrop_host(s, l)],
        "mdcheck_scan": [lambda s, l: test_mdcheck_scan(s, l)],
        "maildrop_session": [
            lambda s, l: test_maildrop_session(s, l, app_config, args.abort_test)
        ],
        "aprs_query":  [lambda s, l: test_aprs_query(s, l)],
        "aprs_tx":     [lambda s, l: test_aprs_tx(s, l)],
        "aprs_reject": [lambda s, l: test_aprs_reject(s, l)],
        "link_carry":      [lambda s, l: test_link_carry(s, l)],
        "link_carry_host": [lambda s, l: test_link_carry_host(s, l)],
        "channel_probe":   [lambda s, l: test_channel_probe(s, l, args.part)],
        "all":    [
            lambda s, l: test_t17(s, l),
            lambda s, l: test_t103(s, l, app_config),
            lambda s, l: test_pthuff(s, l, app_config),
        ],
    }

    exit_code = 0
    init_phase_summarized = False
    try:
        if not args.dry_run:
            session.connect()
            if "port" in capture_box:
                _log_init_phase_summary(log, capture_box["port"])
                init_phase_summarized = True
        for fn in test_fns[args.test]:
            fn(session, log)
    except HWCheckError as exc:
        log.line(f"ERROR: {exc}")
        log.result(args.test, "FAIL", str(exc))
        exit_code = 1
        if "port" in capture_box and not init_phase_summarized:
            _log_init_phase_summary(log, capture_box["port"])
    except KeyboardInterrupt:
        log.line("ERROR: interrupted by operator")
        exit_code = 1
    finally:
        try:
            session.disconnect()
        except Exception as exc:  # pragma: no cover - best-effort cleanup
            log.line(f"(cleanup warning: {exc})")
        if comm_log_handler is not None:
            comm_logger.removeHandler(comm_log_handler)
            comm_logger.setLevel(logging.NOTSET)
        log.summary()
        log.close()

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
