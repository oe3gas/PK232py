# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""MailDrop verbose-mode protocol — pure parsing and command building (P27.1).

No I/O, no Qt dependency. Every shape parsed or built here is taken from
the real hardware transcripts in ``hw_logs/`` (22./23.09.2026 MailDrop
sessions, `tools/hw_check.py maildrop`/`maildrop_host`) or from the
mnemonic/protocol facts already recorded in CLAUDE.md — never guessed.
MDCHECK itself has no Host Mode mnemonic (`mdcheck_scan`, P26, 23
candidates, no hit), so this whole module operates on the verbose-mode
serial link, not Host Mode frames.

Real, hardware-confirmed response shapes this module parses (CLAUDE.md's
MailDrop facts, and see the docstrings below for exact citations):

    prompt      '(AEA PK-232M)  18536 free  (B,E,K,L,R,S) >'
    have mail   'You have mail.' just before the prompt
    empty list  '*** Message not found.'
    list header 'Msg#    Size To     From   @ BBS  Date       Time   Title'
    list row    '  1 PN    36 OE3GAS OE3GAS        22-Sep-26  18:00  test 1'
    read        header + list row + blank line + body text + blank line
    send        'S <to> [@ <bbs>] [< <from>]' -> 'Subject:' -> subject ->
                'Enter message, ^Z (CTRL-Z) or /EX to end' -> lines ->
                '/EX' -> 'Message stored as # <n>'
    kill        'K <n>' -> '*** Done.'
    bad args    '*** Not enough' (e.g. 'R2' instead of 'R 2')
    full        '*** No free memory'
    unknown cmd '*** What?'
    leave       'B' -> 'cmd:'
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# ===========================================================================
# Data shapes
# ===========================================================================


@dataclass(frozen=True)
class MailDropEntry:
    """One row of a MailDrop 'L' listing, or the header row of an 'R'
    response (CLAUDE.md's fixed-width list format, hardware-confirmed
    22.09.2026)."""
    number: int
    mtype:  str            # "P" | "T" | "B"
    read:   bool           # from the row's second status letter, N/Y
    size:   int
    to:     str
    frm:    str
    bbs:    str             # "" when the '@ BBS' column is empty
    stamp:  Optional[str]   # "22-Sep-26  18:00", None for an unset clock's dots
    title:  str


@dataclass(frozen=True)
class PromptInfo:
    """The mailbox prompt line, parsed (CLAUDE.md: hardware-confirmed as
    '(AEA PK-232M)  18536 free  (B,E,K,L,R,S) >' on 22.09.2026 (three
    rounds) AND as '[AEA PK-232M]  18340 free  (B,E,K,L,R,S) >' on
    23.09.2026, after the TNC had hung and been power-cycled — BOTH
    bracket forms are hardware-confirmed; the cause of the switch is
    unknown, see CLAUDE.md/Backlog.md (P31))."""
    free:       int
    commands:   str         # "B,E,K,L,R,S"
    have_mail:  bool        # a 'You have mail.' line preceded the prompt
    bracket:    str         # "round" or "square" - which form THIS prompt used


# ===========================================================================
# Prompt / response classification
# ===========================================================================

# Hardware-confirmed shapes (CLAUDE.md, P31): the device-name bracket is
# EITHER round '(...)' or square '[...]' (never mixed - '(...]' is not a
# match) - the command-set parenthesis after 'free' stays round in BOTH
# measurements, so it is not made bracket-tolerant. Device name tolerant
# of 'PK-232', 'PK-232M', 'PK-232MBX' - only 'PK-232M' has been measured
# so far, but the others are the same TRM-documented product family and
# cost nothing to accept. Whitespace runs are never hardcoded to a fixed
# count anywhere in this pattern.
_PROMPT_RE = re.compile(
    r"(\(\s*AEA\s+PK-232M?(?:BX)?\s*\)|\[\s*AEA\s+PK-232M?(?:BX)?\s*\])"
    r"\s+(\d+)\s+free\s+\(([A-Z,]+)\)\s*>"
)

_HAVE_MAIL_TEXT = "You have mail."
_SUBJECT_PROMPT = "Subject:"
_BODY_PROMPT    = "Enter message, ^Z (CTRL-Z) or /EX to end"

# '*** Done.' is deliberately NOT in here — it is a SUCCESS confirmation
# (K <n> kill), not an error; see parse_error()'s docstring.
_KNOWN_ERRORS = (
    "*** What?",
    "*** Not enough",
    "*** No free memory",
)

_DONE_TEXT = "*** Done."


def find_prompt(text: str) -> Optional[PromptInfo]:
    """Find the mailbox prompt anywhere in *text* (P27.1).

    Tolerates whatever precedes it: nothing, a 'You have mail.' line
    (hardware-confirmed: MDCHECK with unread mail adds this line before
    the prompt), or an unrelated line SIAM interleaved mid-response (SIAM
    keeps analysing continuously and writes into whatever else is
    happening, CLAUDE.md P21 finding — this searches, never anchors to
    the last line, for the same reason).
    """
    m = _PROMPT_RE.search(text)
    if m is None:
        return None
    return PromptInfo(
        free=int(m.group(2)),
        commands=m.group(3),
        have_mail=_HAVE_MAIL_TEXT in text,
        bracket="round" if m.group(1).startswith("(") else "square",
    )


def classify(text: str) -> str:
    """Classify one raw response's terminal state (P27.1).

    Returns one of "prompt" | "cmd" | "subject" | "body" | "error" |
    "unknown". "cmd" as soon as the response ends in 'cmd:' (leaving the
    mailbox) — checked before "prompt", since a genuine 'B' -> 'cmd:'
    response never also contains the mailbox prompt.
    """
    stripped = text.rstrip()
    if stripped.lower().endswith("cmd:"):
        return "cmd"
    if find_prompt(text) is not None:
        return "prompt"
    if stripped.endswith(_SUBJECT_PROMPT):
        return "subject"
    if stripped.endswith(_BODY_PROMPT):
        return "body"
    if parse_error(text) is not None:
        return "error"
    return "unknown"


def parse_error(text: str) -> Optional[str]:
    """Return the TNC's error text if *text* contains one (P27.1):
    '*** What?', '*** Not enough', '*** No free memory'.

    '*** Done.' (the K <n> kill confirmation) is explicitly marked as
    SUCCESS here, not an error — it returns None for it, same as for any
    response with no error at all, so callers never misreport a
    successful kill as a failure. A caller that needs to positively
    confirm a kill checks for '*** Done.' in the raw response itself.
    '*** Message not found.' (an empty list) is NOT an error either — see
    parse_list(), which turns it into an empty list.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == _DONE_TEXT:
            return None
        for known in _KNOWN_ERRORS:
            if stripped.startswith(known):
                return stripped
    return None


# ===========================================================================
# Listing / reading
# ===========================================================================

_NOT_FOUND_TEXT = "*** Message not found."

# Fixed-width column layout (0-indexed), hardware-confirmed 22.09.2026
# against three real listings (CLAUDE.md P22.5):
#   [0:3]   Msg# (right-aligned)      [34:43]  Date (or dots)
#   [4:6]   status: type + read       [45:50]  Time (or dots)
#   [6:12]  Size                      [52:]    Title (rest of line)
#   [13:19] To            [20:26] From          [26:34] @ BBS
_MIN_ROW_LEN = 58


def _dots_to_none(value: str) -> Optional[str]:
    return None if value and set(value) <= {"."} else (value or None)


def _stamp(date_text: str, time_text: str) -> Optional[str]:
    date_text = _dots_to_none(date_text)
    time_text = _dots_to_none(time_text)
    if date_text is None or time_text is None:
        return None
    return f"{date_text}  {time_text}"


def _parse_list_row_fixed(line: str) -> Optional[MailDropEntry]:
    if len(line) < _MIN_ROW_LEN:
        return None
    msg_no_text = line[0:3].strip()
    if not msg_no_text.isdigit():
        return None
    status = line[4:6].strip()
    if len(status) != 2 or not status[0].isalpha() or status[1] not in "NY":
        return None
    size_text = line[6:12].strip()
    if not size_text.isdigit():
        return None
    return MailDropEntry(
        number=int(msg_no_text),
        mtype=status[0],
        read=(status[1] == "Y"),
        size=int(size_text),
        to=line[13:19].strip(),
        frm=line[20:26].strip(),
        bbs=line[26:34].strip(),
        stamp=_stamp(line[34:43], line[45:50]),
        title=line[52:].rstrip("\r"),
    )


# Best-effort fallback for when the fixed-column slicing above does not
# match (P27.1: "mit Ruckfall auf Trennung an Leerzeichen, wenn die
# Spaltenbreiten nicht passen") - e.g. a firmware/response variant with
# different padding. Runs of 2+ whitespace are treated as column
# separators so a single-space-separated title survives; the leading
# Msg#/status/Size/To/From block is still whitespace-delimited internally
# on the real hardware, so that part is parsed with a plain split().
_DATE_RE = re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{2}$|^\.+$")
_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$|^\.+$")


def _parse_list_row_fallback(line: str) -> Optional[MailDropEntry]:
    parts = line.split()
    if len(parts) < 5:
        return None
    if not parts[0].isdigit():
        return None
    status = parts[1]
    if len(status) != 2 or not status[0].isalpha() or status[1] not in "NY":
        return None
    size_text = parts[2]
    if not size_text.isdigit():
        return None
    to, frm = parts[3], parts[4]
    rest = parts[5:]

    date_idx = next((i for i, p in enumerate(rest) if _DATE_RE.match(p)), None)
    if date_idx is None or date_idx + 1 >= len(rest) or not _TIME_RE.match(rest[date_idx + 1]):
        # No recognisable date/time pair at all - treat everything after
        # From as the title, no BBS, no stamp (best-effort only).
        return MailDropEntry(
            number=int(parts[0]), mtype=status[0], read=(status[1] == "Y"),
            size=int(size_text), to=to, frm=frm, bbs="", stamp=None,
            title=" ".join(rest),
        )

    bbs = " ".join(rest[:date_idx])
    stamp = _stamp(rest[date_idx], rest[date_idx + 1])
    title = " ".join(rest[date_idx + 2:])
    return MailDropEntry(
        number=int(parts[0]), mtype=status[0], read=(status[1] == "Y"),
        size=int(size_text), to=to, frm=frm, bbs=bbs, stamp=stamp, title=title,
    )


def _parse_list_row(line: str) -> Optional[MailDropEntry]:
    return _parse_list_row_fixed(line) or _parse_list_row_fallback(line)


def parse_list(text: str) -> list[MailDropEntry]:
    """Parse every data row out of one 'L' response (P27.1).

    Skips the echo, the header line, the mailbox prompt, and anything
    else that is not a data row. '*** Message not found.' (an empty
    mailbox, hardware-confirmed) becomes an empty list, not an error.
    """
    if _NOT_FOUND_TEXT in text:
        return []
    entries = []
    for line in text.replace("\r\n", "\n").split("\n"):
        entry = _parse_list_row(line)
        if entry is not None:
            entries.append(entry)
    return entries


def parse_read(text: str) -> tuple[Optional[MailDropEntry], str]:
    """Split one 'R <n>' response into (entry, body) (P27.1).

    Real shape (CLAUDE.md): header + list row for this message + blank
    line + body text + blank line, occasionally (one-off, not general —
    CLAUDE.md's P24 correction) a trailing '/E' line just before the
    prompt. Returns (None, text.strip()) if no list row could be found
    at all (malformed response).
    """
    lines = text.replace("\r\n", "\n").split("\n")

    entry = None
    body_start = None
    for i, line in enumerate(lines):
        parsed = _parse_list_row(line)
        if parsed is not None:
            entry = parsed
            body_start = i + 1
            break
    if body_start is None:
        return None, text.strip()

    if body_start < len(lines) and lines[body_start].strip() == "":
        body_start += 1
    body_lines = lines[body_start:]

    # Drop a trailing mailbox prompt, blank lines, and (if present) the
    # one-off '/E' trailer - tolerated, never required (CLAUDE.md P24).
    while body_lines and (
        body_lines[-1].strip() == "" or find_prompt(body_lines[-1]) is not None
    ):
        body_lines.pop()
    if body_lines and body_lines[-1].strip() == "/E":
        body_lines.pop()
    while body_lines and body_lines[-1].strip() == "":
        body_lines.pop()

    return entry, "\n".join(body_lines)


# ===========================================================================
# Composing a message
# ===========================================================================

# "eine Zeile, die nach strip() mit /EX beginnt, ist unzulaessig" - a
# message body containing this would abort transmission mid-text if sent
# raw (CLAUDE.md's MailDrop design-consequences list). Case-insensitive:
# the mailbox itself accepts lowercase input.
def check_body(text: str) -> list[str]:
    """Return rejection reasons for *text* as a MailDrop message body
    (P27.1). Empty list means the body is safe to send as-is."""
    reasons = []
    for i, line in enumerate(text.splitlines(), start=1):
        if line.strip().upper().startswith("/EX"):
            reasons.append(
                f"line {i} begins with /EX and would end the message "
                f"early: {line!r}"
            )
    return reasons


# ae/oe/ue/ss transliteration (CLAUDE.md design consequence: "transliterate
# umlauts rather than sending them raw, until 8BITCONV is actually
# measured" - non-ASCII is otherwise silently lost, confirmed 22.09.2026:
# 'fuer' -> 'f?r' when sent raw).
_UMLAUT_MAP = {
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "Ä": "Ae", "Ö": "Oe", "Ü": "Ue",
}


def sanitize_body(text: str) -> tuple[str, list[str]]:
    """Transliterate German umlauts and replace any other non-ASCII
    character with '?' (P27.1) - matches what the TNC would otherwise do
    to it silently (hardware-confirmed: 'für' arrived as 'f?r').

    Returns (clean_text, changes) - *changes* lists each substitution
    made, for display to the operator before sending.
    """
    changes: list[str] = []
    out: list[str] = []
    for ch in text:
        if ch in _UMLAUT_MAP:
            repl = _UMLAUT_MAP[ch]
            changes.append(f"{ch!r} -> {repl!r}")
            out.append(repl)
        elif ord(ch) < 128:
            out.append(ch)
        else:
            changes.append(f"{ch!r} -> '?'")
            out.append("?")
    return "".join(out), changes


# Generic syntax check only (letters, digits, optional '-SSID') - the TNC
# itself does not validate the 'S' command's callsign-shaped arguments at
# all (CLAUDE.md: mistyped '@'/'<' extras were silently accepted up to the
# typo), so software must catch nonsense before it is ever sent.
_CALLSIGN_RE = re.compile(r"^[A-Z0-9]{3,7}(-[0-9]{1,2})?$")


def validate_callsign(call: str) -> bool:
    """True if *call* has callsign-like syntax (P27.1) - letters, digits,
    an optional '-SSID'. Not a real callsign lookup; 'ALL' (the bulletin
    destination) and BBS names pass this the same as an operator call."""
    return bool(_CALLSIGN_RE.match(call.strip().upper()))


_SEND_COMMAND_WORDS = {"P": "S", "T": "ST", "B": "SB"}


def build_send_command(to: str, bbs: str, frm: str, mtype: str) -> str:
    """Build the mailbox command line to start a new message (P27.1).

    Hardware-confirmed shapes (CLAUDE.md): 'S <to>' (personal), 'ST <to>'
    (traffic), 'SB <to>' (bulletin, e.g. 'SB ALL'); '@ <bbs>' appended
    only when *bbs* is given; '< <frm>' appended only when *frm* is given
    (a foreign FROM) - this function does not know MYCALL, so the caller
    decides whether *frm* differs from it and passes '' when it does not.
    Raises ValueError for a syntactically invalid callsign in *to*, *bbs*
    or *frm* - the TNC will not reject one itself (CLAUDE.md).
    """
    cmd_word = _SEND_COMMAND_WORDS.get(mtype)
    if cmd_word is None:
        raise ValueError(f"unknown message type: {mtype!r}")

    to = to.strip().upper()
    if not validate_callsign(to):
        raise ValueError(f"invalid recipient callsign: {to!r}")

    parts = [cmd_word, to]

    if bbs:
        bbs = bbs.strip().upper()
        if not validate_callsign(bbs):
            raise ValueError(f"invalid BBS callsign: {bbs!r}")
        parts += ["@", bbs]

    if frm:
        frm = frm.strip().upper()
        if not validate_callsign(frm):
            raise ValueError(f"invalid FROM callsign: {frm!r}")
        parts += ["<", frm]

    return " ".join(parts)
