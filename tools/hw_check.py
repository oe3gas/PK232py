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
    all     t17 + t103 + pthuff. Deliberately NOT t101 (it transmits and
            needs a second receiver), NOT siam/t111/t112 (siam needs a
            tuned receiver and an operator comparison; t111/t112 are run
            and recorded individually), and NOT
            mi/maildrop/maildrop_host/mdcheck_scan (mi is fine alone but
            grouped with its guided counterpart; maildrop, maildrop_host
            and mdcheck_scan are interactive/exploratory), so each must be
            run on its own.

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
import dataclasses
import datetime
import re
import sys
import time
from pathlib import Path
from typing import Callable, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from PyQt6.QtCore import QCoreApplication  # noqa: E402

from pk232py.comm.serial_manager import SerialManager  # noqa: E402
from pk232py.comm.params_uploader import ParamsUploader  # noqa: E402
from pk232py.comm.frame import build_command, _dle_escape  # noqa: E402
from pk232py.comm.constants import SOH, ETB  # noqa: E402
from pk232py.config import AppConfig, ConfigManager  # noqa: E402
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

# The mnemonic the app's MailDrop button sends - must always equal whatever
# main_window.py's _on_packet_maildrop() actually builds, or the probe
# measures a different command than the one the app sends (P17.2 pattern).
# TestMiProbeMnemonic in test_hw_check.py enforces this against the real
# source file.
MI_PROBE_MNEMONIC = b'MI'

_MAILDROP_BUTTON_FUNC_RE = re.compile(
    r"def _on_packet_maildrop\(self\).*?(?=\n    def )", re.DOTALL
)
_BUILD_COMMAND_RE = re.compile(r"build_command\(b'([A-Za-z]{2})'\)")


def extract_maildrop_button_mnemonic(main_window_source: str) -> Optional[str]:
    """Pull the mnemonic _on_packet_maildrop() actually sends out of
    main_window.py's SOURCE TEXT (P20 Teil C) - reading the file as text
    rather than importing main_window.py, which would pull the entire
    PyQt6 widget tree in just to compare two bytes literals (same
    approach as extract_passall_toggle_mnemonic(), P17.2). Returns None
    if the function or its build_command() call is not found (source
    reshaped)."""
    func_match = _MAILDROP_BUTTON_FUNC_RE.search(main_window_source)
    if not func_match:
        return None
    cmd_match = _BUILD_COMMAND_RE.search(func_match.group(0))
    return cmd_match.group(1) if cmd_match else None


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
    # MYCALL is deliberately NOT here - session.normalize() (P21.2)
    # already queries/resets it; querying it again here would send it
    # twice for no reason.
    "MAILDROP", "MYMAIL", "MTEXT", "MMSG",
    "3RDPARTY", "KILONFWD", "TMAIL", "MDMON", "XMITOK",
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


# ===========================================================================
# Session - the one place that touches SerialManager
# ===========================================================================

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

    def connect(self) -> None:
        if not self.sm.connect_port(self.port_name, baudrate=self.baud):
            raise HWCheckError(
                f"Port busy - is pk232py running? ({self.port_name})"
            )
        self.log.line(f"Opened {self.port_name} @ {self.baud} Bd")
        self.sm.init_tnc()
        if not self._wait_until(
            lambda: self.sm.is_verbose_mode or self.sm.is_host_mode, timeout=8.0
        ):
            raise HWCheckError(
                "TNC did not respond to wakeup - check port, baud rate and cable"
            )
        if self.sm.is_host_mode:
            raise HWCheckError(
                "TNC is already in Host Mode. hw_check needs to start from "
                "verbose mode - power-cycle the TNC (or exit Host Mode in "
                "the application first) and try again."
            )
        self.log.line("TNC in verbose mode")

    def disconnect(self) -> None:
        if not self.sm.is_connected:
            return
        if self.sm.is_host_mode:
            self.sm.exit_host_mode()
            self._wait_until(lambda: not self.sm.is_host_mode, timeout=5.0)
        self.sm.disconnect_port()
        self.log.line("Disconnected")

    def enter_host_mode(self) -> None:
        if self.sm.is_host_mode:
            return
        self.sm.enter_host_mode()
        if not self._wait_until(lambda: self.sm.is_host_mode, timeout=10.0):
            raise HWCheckError("Could not enter Host Mode")
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
        """Bring the TNC to a known, quiet verbose-mode state (P21.2).

        Called at the START of every hardware subcommand that assumes a
        clean verbose-mode state (t17/t111/t112/mi/siam/maildrop), and
        again after any operator-driven power-cycle within a session -
        found necessary 22.09.2026, when a still-running SIAM session
        wrote asynchronous results into the middle of unrelated
        responses (XMITOK, mailbox output) with no warning at all.

        1. Ctrl-C ($03, the verbose-mode COMMAND character) then CR -
           drops back to the top-level command interpreter regardless of
           what was running, via the idle-gap read (its prompt is not
           assumed).
        2. PACKET - leaves whichever operating mode was active WITHOUT
           entering Host Mode. SIAM in particular does NOT stop analysing
           on its own; only selecting a different mode does.
        3. Reads for 2s watching for further asynchronous output - a mode
           that ignored steps 1/2 would still show up here. Logged as a
           warning, never fatal (this is diagnostic, not a hard gate).
        4. Queries MYCALL. The PK-232 has no RAM buffer battery
           (CLAUDE.md) and resets to the factory value 'PK232' on every
           power-off; if seen, MYCALL is set back from the loaded
           AppConfig and the factory-state finding is logged.
        """
        if self.dry_run:
            self.log.line(
                "[dry-run] would normalize: Ctrl-C + CR, PACKET, watch 2s "
                "for async output, check MYCALL (factory 'PK232' -> reset "
                "from config)"
            )
            return

        self.log.line("Normalizing TNC state (P21.2)")
        self.send_and_read_until_idle(b"\x03\r", note="Ctrl-C + CR (normalize)")
        self.verbose("PACKET")

        del self._raw_buf[:]
        extra = self.read_until_idle(idle=2.0, max_total=2.0)
        if extra:
            self.log.line(
                f"WARNING: asynchronous output continued after PACKET -- "
                f"a mode may still be running: {extra!r}"
            )

        mycall = parse_query_value("MYCALL", self.query("MYCALL"))
        self.log.line(f"MYCALL: {mycall!r}")
        if mycall is not None and mycall.strip().upper() == "PK232":
            self.log.line("factory state detected -- no RAM battery")
            configured = self.app_config.hf_packet.mycall
            if configured and configured.upper() != "NOCALL":
                self.set_verbose("MYCALL", configured.upper())
                self.log.line(f"MYCALL set to {configured.upper()!r} from config")

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


def confirm_tx(prompt: str) -> bool:
    """The one gate every actual transmission must pass (hard rule #3)."""
    print()
    print("*** THIS WILL KEY THE TRANSMITTER ***")
    print(prompt)
    answer = input("Proceed? [y/N] ").strip().lower()
    return answer == "y"


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
    (comm/params_uploader.py) rather than rebuilding the command."""
    now = datetime.datetime.now(datetime.timezone.utc)
    cmd = ParamsUploader._cmd("DAYTIME", now.strftime("%y%m%d%H%M%S"))
    resp = session.verbose_bytes(cmd)
    log.line(f"DAYTIME set to {now:%y%m%d%H%M%S} (UTC): {resp!r}")


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
            log.line(f"{cmd}: error {err!r} (raw: {resp!r})")
            values[cmd] = None
        else:
            value = parse_query_value(cmd, resp)
            values[cmd] = value
            log.line(f"{cmd}: {value!r} (raw: {resp!r})")

    xmitok = values.get("XMITOK")
    if xmitok is not None and xmitok.strip().upper() == "ON":
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
            "[dry-run] would query XMITOK, create a test message over the "
            "known verbose path (MDCHECK/S/subject/text/EX/L/B), verbose-"
            "query HOST, enter Host Mode, confirm y/N, then probe with "
            "these frames (probe B only runs if probe A got nothing; "
            "R<n> only if a list came back):"
        )
        for probe_data in (b"L\r", b"MDCHECK\r", b"L\r", b"R 1\r", b"B\r"):
            session.send_maildrop_host_frame(probe_data)
        log.result("MAILDROP_HOST", "INFO", "dry-run, nothing sent")
        return

    xmitok = parse_query_value("XMITOK", session.query("XMITOK"))
    log.line(f"XMITOK: {xmitok!r}")
    if xmitok is not None and xmitok.strip().upper() == "ON":
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
    session.send_and_read_until_idle(b"MDCHECK\r\n")
    session.send_and_read_until_idle(b"S OE3GAS\r")
    session.send_and_read_until_idle(b"Host Mode Test\r")
    session.send_and_read_until_idle(b"created for the maildrop_host probe\r")
    store_resp = session.send_and_read_until_idle(MAILBOX_ABANDON_ENTRY_COMMAND)
    store_text = store_resp.decode("ascii", errors="replace")
    msg_number = parse_stored_message_number(store_text)
    log.line(f"Test message stored as # {msg_number}")
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
            f"path (MDCHECK/S/subject/text/EX/L/B, like maildrop_host), "
            f"verbose-query XMITOK, enter Host Mode, confirm y/N, then try "
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

    xmitok = parse_query_value("XMITOK", session.query("XMITOK"))
    log.line(f"XMITOK: {xmitok!r}")
    if xmitok is not None and xmitok.strip().upper() == "ON":
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
    session.send_and_read_until_idle(b"MDCHECK\r\n")
    session.send_and_read_until_idle(b"S OE3GAS\r")
    session.send_and_read_until_idle(b"mdcheck_scan test\r")
    session.send_and_read_until_idle(b"created for the mdcheck_scan probe\r")
    store_resp = session.send_and_read_until_idle(MAILBOX_ABANDON_ENTRY_COMMAND)
    msg_number = parse_stored_message_number(
        store_resp.decode("ascii", errors="replace")
    )
    log.line(f"Test message stored as # {msg_number}")
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
            "are read-only Host Mode probes; t101 TRANSMITS and needs a "
            "second receiver."
        ),
    )
    p.add_argument(
        "test",
        choices=[
            "t17", "t103", "pthuff", "t101", "siam", "t111", "t112",
            "mi", "maildrop", "maildrop_host", "mdcheck_scan", "all",
        ],
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
        "all":    [
            lambda s, l: test_t17(s, l),
            lambda s, l: test_t103(s, l, app_config),
            lambda s, l: test_pthuff(s, l, app_config),
        ],
    }

    exit_code = 0
    try:
        if not args.dry_run:
            session.connect()
        for fn in test_fns[args.test]:
            fn(session, log)
    except HWCheckError as exc:
        log.line(f"ERROR: {exc}")
        log.result(args.test, "FAIL", str(exc))
        exit_code = 1
    except KeyboardInterrupt:
        log.line("ERROR: interrupted by operator")
        exit_code = 1
    finally:
        try:
            session.disconnect()
        except Exception as exc:  # pragma: no cover - best-effort cleanup
            log.line(f"(cleanup warning: {exc})")
        log.summary()
        log.close()

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
