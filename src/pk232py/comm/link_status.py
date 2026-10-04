# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""comm/link_status.py - the ONE place that decodes TRM 4.3.3 Link
Status (Host Mode CO) responses, verbose CSTATUS text, and the
channel-number prefix a verbose line can carry (P67, Teil A).

Qt-free, pure functions/dataclasses - no serial I/O, no widget refs -
importable from both tools/hw_check.py and the application itself, so
there is exactly one decoder for each of these three things instead of
hw_check's own copy (P65/P66) plus a second one the application would
otherwise grow.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .constants import ctl_channel


@dataclass
class LinkStatus:
    """Decoded response to a TRM 4.3.3 Link Status query (Host Mode
    CO): SOH $4x 'C' 'O' a b c d e <path> ETB. *channel* and *raw* are
    always set; exactly one of the other cases applies:

      - unparsed=True: the payload was not CO-prefixed, or too short
        to be either of the two recognised shapes below (never
        guessed - hw_check rule 6).
      - error_code is not None: a one-byte CO error code (P67, H.3 -
        hardware-observed, e.g. $0C answering a CONNECT to an already-
        connected station). The MEANING of a given code is not
        recorded here - only the TRM/a future measurement can say what
        $0C means; this stores the raw code, never a guess.
      - state/connected/v2/unacked/retries/conperm/partner/digis: the
        full five-status-byte shape (state = (a & 0x0F) + 1, TRM's own
        4.3.3 example; connected = state == 5, T142's own real
        capture). v2/conperm are single-bit flags -> bool; unacked/
        retries are counts -> int. *partner*/*digis* split the path
        text on ' via ' (TRM's own separator between a callsign and
        any digipeaters, e.g. 'W6CUS-1 via K6LLK, WD6CMU-1') - a path
        with no ' via ' (T142's own real capture, 'OE3GAS-1') has an
        empty *digis*.
    """
    channel: int
    raw: bytes = b""
    unparsed: bool = False
    error_code: Optional[int] = None
    state: int = 0
    connected: bool = False
    v2: bool = False
    unacked: int = 0
    retries: int = 0
    conperm: bool = False
    partner: str = ""
    digis: str = ""


def decode_link_status(ctl: int, data: bytes) -> LinkStatus:
    """Decode a TRM 4.3.3 Link Status response (P65 A.6, corrected P66
    B.5, moved here and given the P67 H.3 error-code case).

    *ctl* is the frame's own CTL byte - the channel comes from its low
    nibble (ctl_channel(), P16.2's own rule: never assumed from send
    order, always read back off the response itself). *data* is the
    frame's payload exactly as _make_host_frame() delivers it.

    Measured against real hardware (T142, Device B, 28.09.2026,
    20260928_094231_link_carry_host.log - channel 1 connected:
    'CO41000OE3GAS-1'; a free channel: 'CO00000') and P67's own H.3
    finding (a one-byte error response, 'CO' + $0C, on a CONNECT to an
    already-connected station).
    """
    channel = ctl_channel(ctl)
    if not data.startswith(b"CO"):
        return LinkStatus(channel=channel, raw=data, unparsed=True)
    if len(data) == 3:
        return LinkStatus(channel=channel, raw=data, error_code=data[2])
    if len(data) < 7:
        return LinkStatus(channel=channel, raw=data, unparsed=True)
    a, b, c, d, e = data[2], data[3], data[4], data[5], data[6]
    path = data[7:].decode("ascii", errors="replace")
    if " via " in path:
        partner, digis = path.split(" via ", 1)
    else:
        partner, digis = path, ""
    state = (a & 0x0F) + 1
    return LinkStatus(
        channel=channel,
        raw=data,
        state=state,
        connected=(state == 5),
        v2=bool(b & 0x0F),
        unacked=c & 0x0F,
        retries=d & 0x0F,
        conperm=bool(e & 0x0F),
        partner=partner,
        digis=digis,
    )


_CSTATUS_LINE_RE = re.compile(r"Ch\.\s*(\d+)\s*-\s*(IO)?\s*(.*)")
_CSTATUS_PARTNER_RE = re.compile(r"CONNECTED to ([\w-]+)")


def parse_cstatus(text: str) -> dict[int, tuple[bool, str, str]]:
    """Parse a verbose CSTATUS response into
    ``{channel: (io, state_text, partner)}`` - one entry per
    ``'Ch. N - ...'`` line found (P66/P66b/P67 M2/M6 - real examples:
    ``'Ch. 0 - IO CONNECTED to OE3GAS-1; v2'``, ``'Ch. 9 - IO'``,
    ``'Ch. 1 - CONNECTED to OE3GAS-1; v2'`` with no IO marker at all).

    *io* is whether this line carried the 'IO' marker - the TNC's own
    active/current channel (CLAUDE.md's "IO channel follows the last
    $4x frame sent" gotcha, P66b B.3/B.4). *partner* is the callsign
    after 'CONNECTED to ', or '' if the line names none. A channel
    with no line in *text* at all is simply absent from the result -
    never guessed as free or anything else.
    """
    result: dict[int, tuple[bool, str, str]] = {}
    for line in text.splitlines():
        m = _CSTATUS_LINE_RE.search(line)
        if not m:
            continue
        channel = int(m.group(1))
        io = m.group(2) is not None
        state_text = m.group(3).strip()
        partner_m = _CSTATUS_PARTNER_RE.search(state_text)
        partner = partner_m.group(1) if partner_m else ""
        result[channel] = (io, state_text, partner)
    return result


_CHANNEL_PREFIX_RE = re.compile(r"^\x00(\d):\s?(.*)$")


def split_channel_prefix(line: str) -> tuple[Optional[int], str]:
    """Split a verbose line's channel-number prefix from its text
    (P67, M10 - hardware-observed, Device B, 28.09.2026:
    ``'\\x000: ?already connected ...'``, ``'\\x009: cmd:'``).

    Returns ``(None, line)`` unchanged if no such prefix is present -
    WHEN this prefix appears is still unmeasured (only that it exists
    and must be tolerated), so this never assumes one is always
    there, and never guesses a channel for a line that does not carry
    one.
    """
    m = _CHANNEL_PREFIX_RE.match(line)
    if not m:
        return None, line
    return int(m.group(1)), m.group(2)


def extract_partner(text: str) -> str:
    """Best-effort far-end callsign extraction from a link-message
    string (P67, Teil B: moved here from modes/packet_hf.py so
    comm/link_table.py can use the SAME extraction LinkTable's own
    on_host_link_message()/on_verbose_line() need, instead of growing
    a second copy or making comm/ depend on modes/ - packet_hf.py
    re-exports this under its old name, _extract_partner, unchanged).

    Handles the two message shapes seen in the TRM / mock TNC:
      "CONNECTED to OE1XYZ-5"   -> "OE1XYZ-5"   (" to " marker)
      "Connect request: OE1XYZ" -> "OE1XYZ"     (":" marker)
    Falls back to the first whitespace-separated token, e.g. "OE1XYZ busy".
    Returns "" if nothing usable is found — callers must tolerate that.

    P55.A: with CONSTAMP/DAYSTAMP both ON (the default, params_uploader.py
    uploads both) a real message is prefixed with the TNC's own date/time,
    e.g. "*** 25-Sep-26 21:04:36 DISCONNECTED: OE3TEC-1 ***" - and that
    stamp's own "HH:MM:SS" contributes TWO colons of its own, both ahead
    of the ':' that actually marks the callsign. Splitting on the FIRST
    colon in the whole string (the old `text.split(":", 1)`) landed
    inside the timestamp instead - e.g. "04:36" read as the partner
    callsign, reproducing the MHEARD screenshot's date/time-shaped
    entries. rsplit() on the LAST colon is what the callsign marker
    itself actually needs, since nothing legitimate ever follows a real
    callsign with a colon.
    """
    lower = text.lower()
    if " to " in lower:
        tail = text[lower.index(" to ") + 4:].strip()
        # Some firmware variants send "CONNECTED to: OE1XYZ-5" (colon before
        # the callsign, per the STABO manual chapter 12) instead of the TRM
        # 4.4.4 "CONNECTED to OE1XYZ-5" form. Strip one optional leading ':'
        # (and the whitespace around it) before taking the first token, or
        # the colon itself gets misread as the callsign. A trailing
        # " via ..." digipeater path is already dropped by split()[0] either
        # way, with or without the colon.
        if tail.startswith(":"):
            tail = tail[1:].strip()
        return tail.split()[0] if tail else ""
    if ":" in text:
        tail = text.rsplit(":", 1)[1].strip()
        return tail.split()[0] if tail else ""
    tokens = text.strip().split()
    return tokens[0] if tokens else ""


# ---------------------------------------------------------------------------
# P81 A - links the TNC already holds when the application connects
# ---------------------------------------------------------------------------

def _verbose_value(name: str, text: str) -> Optional[str]:
    """First value token of the verbose answer line '<Name>  <value>' (the TNC
    answers in its own mixed case, 'VHf  ON'; the echoed command line is all
    upper case and is skipped). None for an error line or no matching line."""
    for line in (text or "").splitlines():
        tokens = line.strip().split()
        if not tokens:
            continue
        if tokens[0].startswith("?"):
            return None
        if tokens[0].upper() == name.upper() and tokens[0] != name.upper():
            return tokens[1] if len(tokens) > 1 else None
    return None


@dataclass
class LiveLinks:
    """What verbose CSTATUS / OPMODE / VHF said right after the detection
    chain (P81 A). *cstatus* is parse_cstatus() of the answer; *vhf* is None
    when VHF was not readable (the band is then not named, never guessed)."""
    cstatus: dict
    opmode: str = ""
    vhf: Optional[bool] = None

    @property
    def connections(self) -> dict:
        """{channel: partner} of every channel CSTATUS shows connected."""
        return {ch: partner for ch, (_io, _text, partner) in sorted(self.cstatus.items())
                if partner}

    @property
    def mode_name(self) -> Optional[str]:
        """The Packet mode the links belong to; None without links or without
        a readable VHF answer. Only Packet has channels that CSTATUS can show
        connected, so the links themselves prove the Packet opmode."""
        if not self.connections or self.vhf is None:
            return None
        return "VHF Packet" if self.vhf else "HF Packet"

    def summary(self) -> str:
        conns = self.connections
        if not conns:
            return "no active connections"
        n = len(conns)
        listing = ", ".join(f"ch{ch} {partner}" for ch, partner in conns.items())
        band = f" ({self.mode_name})" if self.mode_name else ""
        return f"{n} active connection{'s' if n != 1 else ''} found: {listing}{band}"


def build_live_links(cstatus_text: str, opmode_text: str = "", vhf_text: str = "") -> LiveLinks:
    """LiveLinks from the raw answers of the three verbose queries."""
    value = _verbose_value("VHF", vhf_text)
    vhf = None if value is None else value.upper() in ("ON", "Y", "YES", "1")
    # The echoed command line is exactly 'OPMODE'; the answer is mixed case.
    opmode = " ".join(
        line.strip() for line in (opmode_text or "").splitlines()
        if line.strip() and line.strip() != "OPMODE" and not line.strip().startswith("cmd:")
    )
    return LiveLinks(cstatus=parse_cstatus(cstatus_text), opmode=opmode, vhf=vhf)
