# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""comm/param_applier.py - set the parameters that changed in a parameter
dialog in the TNC right away, and read every one back (P72).

ONE place for "OK in a parameter dialog -> value in the TNC":

    Host Mode        one Host frame per parameter (host_params.host_set_args),
                     read back with a Host query. ONLY for (parameter,
                     release) pairs listed in HostParam.verified_releases.
                     The Host Mode is never left, and there is NO fallback to
                     the verbose way (operator rule 30.09.2026).
    verbose, cmd:    the verbose command ParamsUploader builds, read back with
                     query_verbose_value().
    verbose, Converse  escape_converse() first, afterwards CONVERSE again only
                     if the I/O channel is connected (P67).
    not connected    nothing is sent.

Principle: what the dialog shows is in the TNC - or the operator sees which
value was not taken and why. Therefore EVERY parameter is read back and a
rejection is quoted verbatim; "ok" needs the TNC's own answer (rule 5/13).

ParamApplier is Qt-free and talks to a ParamTransport (protocol below);
SerialParamTransport is the adapter for the real SerialManager.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Optional, Protocol

from pk232py.comm.devices import infer_release
from pk232py.comm.frame import FrameKind
from pk232py.comm.host_params import (
    HostParam, host_error_code, host_query_args, host_set_args, norm_value,
    param_by_name, parse_host_answer,
)
from pk232py.comm.params_uploader import ParamsUploader
from pk232py.comm.pk232_hostmode_sub import escape_converse

# ILFPACK OFF makes the TNC treat the LF of the app's CR LF as the first
# character of the NEXT verbose command (T155 / P72 B.3): the Host Mode set
# works, but the verbose operation of the app breaks. Not set live until P75.
_NEVER_LIVE = {
    "ILFPACK": "ILFPACK is applied at the next initialisation (see P75)",
}


@dataclass
class ApplyResult:
    name: str
    wanted: str
    tnc_now: Optional[str]      # what the read-back showed (None = no read-back)
    ok: bool
    reason: str                 # "ok", the TNC's literal answer, or why nothing was sent
    was: Optional[str] = None   # the value before the change (for the message)
    sent: bool = field(default=False, compare=False)   # something went to the TNC
    # P73 B: a band value (MAXFRAME/SLOTTIME) of the band that is NOT active:
    # saved, applied when that band's Packet mode is selected - not an error.
    band: Optional[str] = None
    deferred: bool = False
    # P82a: the TNC refused because a link exists ($09 / "?not while connected"):
    # not an error - the caller defers the parameter until all channels are free.
    busy: bool = False


class ParamTransport(Protocol):
    """What ParamApplier needs from the serial side (Qt-free)."""

    def mode(self) -> str: ...                      # host | verbose | unconfirmed | disconnected
    def release(self) -> Optional[str]: ...
    def host_exchange(self, mnemonic: bytes, args: bytes) -> Optional[bytes]: ...
    def verbose_set(self, name: str, value: str) -> str: ...
    def verbose_query(self, name: str) -> Optional[str]: ...
    def verbose_query_text(self, command: str) -> str: ...
    def in_converse(self) -> bool: ...
    def io_channel_connected(self) -> bool: ...
    def escape_converse(self) -> bool: ...
    def return_to_converse(self) -> None: ...


def format_result(r: ApplyResult) -> str:
    """The one-line message of the spec (shown in MON / the verbose terminal)."""
    if r.deferred:
        return f"{r.name} ({r.band}) {r.reason}"
    if r.ok and r.reason == "already set":
        return f"{r.name}  {r.wanted}  already set in the TNC"
    if r.ok:
        arrow = f"{r.was} -> {r.wanted}" if r.was is not None else f"-> {r.wanted}"
        return f"{r.name}  {arrow}  ok"
    if not r.sent:
        return f"{r.name}  {r.reason} - saved, TNC unchanged"
    arrow = f"{r.was} -> {r.wanted}" if r.was is not None else f"-> {r.wanted}"
    tail = f"   (TNC still {r.tnc_now})" if r.tnc_now is not None else ""
    return f"{r.name}  {arrow}  {r.reason}{tail}"


def _compare_value(param: Optional[HostParam], value: str) -> str:
    """The part of a verbose value that a read-back can show: UBIT "0 ON" ->
    ON; otherwise the first word (query_verbose_value() returns one token)."""
    words = (value or "").split()
    if not words:
        return ""
    if param is not None and param.kind == "ubit":
        return words[-1]
    return words[0]


def _shown(param: Optional[HostParam], value: Optional[str]) -> Optional[str]:
    """A switch the TNC answered as Y/N is shown as ON/OFF in messages."""
    if value is not None and param is not None and param.kind in ("bool", "ubit"):
        return {"Y": "ON", "N": "OFF"}.get(value.upper(), value)
    return value


def _first_error_line(text: str) -> Optional[str]:
    for line in (text or "").splitlines():
        line = line.strip()
        if line.startswith("?"):
            return line
    return None


class ParamApplier:
    """Apply the difference of two configuration snapshots to the TNC."""

    def __init__(self, transport: ParamTransport) -> None:
        self._t = transport

    def apply(
        self, before, after, has_pactor: bool = True, has_maildrop: bool = True,
        needs_expert: bool = False, band: Optional[str] = None,
    ) -> list[ApplyResult]:
        """One ApplyResult per changed parameter (empty list: nothing
        changed). *needs_expert*: wrap the verbose commands in EXPERT ON/OFF
        like the init upload does on PACTOR firmware.

        *band* ("HF" / "VHF" / None) is the band of the active Packet mode
        (P73 B): MAXFRAME and SLOTTIME exist once in the TNC, so only the
        active band's value is applied; a change of the other band's value is
        answered with a "saved - applies when ... is selected" result and
        nothing is sent."""
        deferred = [
            ApplyResult(n, v, None, False,
                        f"saved - applies when {b} Packet is selected", o,
                        band=b, deferred=True)
            for n, b, v, o in ParamsUploader.deferred_band_changes(before, after, band)
        ]
        changes = ParamsUploader.changed_with_old(
            before, after, has_pactor=has_pactor, has_maildrop=has_maildrop,
            band=band)
        if not changes:
            return deferred
        mode = self._t.mode()
        if mode == "disconnected":
            return self._unsent(changes, "not connected") + deferred
        if mode == "unconfirmed":
            return self._unsent(
                changes, "TNC state not confirmed (no cmd: prompt seen this session)"
            ) + deferred
        results: list[ApplyResult] = list(deferred)
        live = []
        for name, value, old in changes:
            if name in _NEVER_LIVE:
                results.append(ApplyResult(name, value, None, False, _NEVER_LIVE[name], old))
            else:
                live.append((name, value, old))
        if mode == "host":
            results += [self._apply_host(n, v, o) for n, v, o in live]
        else:
            results += self._apply_verbose(live, needs_expert)
        return results

    # ------------------------------------------------------------------

    @staticmethod
    def _unsent(changes, reason: str) -> list[ApplyResult]:
        return [ApplyResult(n, v, None, False, reason, o) for n, v, o in changes]

    def _apply_host(self, name: str, value: str, old: Optional[str]) -> ApplyResult:
        release = self._t.release()
        p = param_by_name(name)
        if p is None or not p.mnemonic or release is None \
                or release not in p.verified_releases:
            return ApplyResult(
                name, value, None, False,
                f"not verified for Host Mode on {release or 'unknown'}", old)
        # P82a: read the TNC's value FIRST. Equal -> nothing is sent; otherwise the
        # starting value in every message is what the TNC really holds.
        before = parse_host_answer(
            p, self._t.host_exchange(p.mnemonic, host_query_args(p)))
        wanted = _compare_value(p, value) if p.kind == "ubit" else value
        if before is not None and norm_value(before, p.kind) == norm_value(wanted, p.kind):
            return ApplyResult(name, value, before, True, "already set", _shown(p, before))
        if before is not None:
            old = _shown(p, before)
        reply = self._t.host_exchange(p.mnemonic, host_set_args(p, value))
        if reply is None:
            return ApplyResult(name, value, None, False, "no answer from TNC", old, sent=True)
        code = host_error_code(reply)
        acked = reply in (p.mnemonic + b"\x00", b"\x00")
        if code is not None:
            reason = f"rejected by TNC: ${code:02X}"
        elif not acked:
            reason = f"unexpected answer from TNC: {reply!r}"
        else:
            reason = "ok"
        # Read back in every case: a rejection must say what the TNC has now.
        now = parse_host_answer(
            p, self._t.host_exchange(p.mnemonic, host_query_args(p)))
        same = now is not None and norm_value(now, p.kind) == norm_value(
            _compare_value(p, value) if p.kind == "ubit" else value, p.kind)
        if acked and not same:
            reason = ("read-back differs after ACK" if now is not None
                      else "no readable answer to the read-back")
        return ApplyResult(name, value, now, acked and same, reason, old, sent=True,
                           busy=(code == 0x09))

    def _apply_verbose(self, live, needs_expert: bool) -> list[ApplyResult]:
        if not live:
            return []
        was_converse = self._t.in_converse()
        if was_converse and not self._t.escape_converse():
            return [ApplyResult(n, v, None, False,
                                "cannot leave Converse (no cmd: prompt)", o)
                    for n, v, o in live]
        results = []
        try:
            if needs_expert:
                self._t.verbose_set("EXPERT", "ON")
            for name, value, old in live:
                results.append(self._apply_verbose_one(name, value, old))
            if needs_expert:
                self._t.verbose_set("EXPERT", "OFF")
        finally:
            # Converse again only on a CONNECTED I/O channel (P67, B.5): on a
            # free channel every further line would go out as an UNPROTO frame.
            if was_converse and self._t.io_channel_connected():
                self._t.return_to_converse()
        return results

    def _read_verbose(self, name: str, p: Optional[HostParam]) -> Optional[str]:
        """The TNC's value of *name* now (UBIT: the index-0 flag)."""
        if p is not None and p.kind == "ubit":
            m = re.findall(r"\b(ON|OFF)\b", self._t.verbose_query_text("UBIT 0") or "", re.I)
            return m[-1].upper() if m else None
        return self._t.verbose_query(name)

    def _apply_verbose_one(self, name: str, value: str, old: Optional[str]) -> ApplyResult:
        p = param_by_name(name)
        kind = p.kind if p is not None else "text"
        # P82a: read the TNC's value FIRST (see _apply_host).
        before = self._read_verbose(name, p)
        if before is not None and norm_value(before, kind) == norm_value(
                _compare_value(p, value), kind):
            return ApplyResult(name, value, before, True, "already set", before)
        if before is not None:
            old = before
        reply = self._t.verbose_set(name, value)
        err = _first_error_line(reply)
        now = self._read_verbose(name, p)
        same = now is not None and norm_value(now, kind) == norm_value(
            _compare_value(p, value), kind)
        if err is not None:
            return ApplyResult(name, value, now, False, f"rejected by TNC: {err}", old,
                               sent=True, busy="not while connected" in err.lower())
        if now is None:
            return ApplyResult(name, value, None, False,
                               "no readable answer to the read-back", old, sent=True)
        if not same:
            return ApplyResult(name, value, now, False, "read-back differs", old, sent=True)
        return ApplyResult(name, value, now, True, "ok", old, sent=True)


# ---------------------------------------------------------------------------
# Adapter for the real SerialManager
# ---------------------------------------------------------------------------

class SerialParamTransport:
    """ParamTransport on a SerialManager.

    Host exchange: connect to frame_received, send ONE frame with
    send_command() (the same path the application uses for every Host
    command) and wait for the answer by pumping the Qt event loop - the
    signal comes from the reader thread and is queued to the GUI thread.
    Nothing here leaves Host Mode or writes a verbose byte.
    """

    def __init__(self, serial, in_converse, io_channel_connected,
                 timeout: float = 1.0) -> None:
        self._sm = serial
        self._in_converse = in_converse
        self._io_connected = io_channel_connected
        self._timeout = timeout

    # -- state ---------------------------------------------------------
    def mode(self) -> str:
        sm = self._sm
        if not sm.is_connected:
            return "disconnected"
        if sm.is_host_mode:
            return "host"
        return "verbose" if sm.verbose_confirmed else "unconfirmed"

    def release(self) -> Optional[str]:
        """The TNC release: from the banner, else inferred (P78 A).

        An INFERRED release counts exactly like a banner one. That is only
        sound while docs/DEVICES.md lists one unit per firmware generation
        (comm/devices.py): a second unit of the same generation would make the
        EXPERT fingerprint ambiguous, and infer_release() then answers None.

        With no release known in Host Mode, ONE ``EX`` query is made here
        (once per connection) and its answer fingerprinted - without it
        nothing could be set in Host Mode on a TNC that was already awake
        when the app connected (T162).
        """
        sm = self._sm
        if (sm.tnc_release is None and not getattr(sm, "release_probe_attempted", False)
                and self.mode() == "host"):
            sm.release_probe_attempted = True
            found = infer_release(self.host_exchange(b"EX", b""))
            if found:
                sm.set_inferred_release(*found)
        return sm.tnc_release

    def in_converse(self) -> bool:
        return bool(self._in_converse())

    def io_channel_connected(self) -> bool:
        return bool(self._io_connected())

    # -- Host Mode -------------------------------------------------------
    def host_exchange(self, mnemonic: bytes, args: bytes) -> Optional[bytes]:
        from PyQt6.QtCore import QCoreApplication, QEventLoop

        got: list = []
        self._sm.frame_received.connect(got.append)
        try:
            if not self._sm.send_command(mnemonic, args):
                return None
            deadline = time.monotonic() + self._timeout
            while time.monotonic() < deadline:
                answer = self._pick(mnemonic, got)
                if answer is not None:
                    return answer
                QCoreApplication.processEvents(
                    QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents, 10)
                time.sleep(0.005)
            return self._pick(mnemonic, got)
        finally:
            self._sm.frame_received.disconnect(got.append)

    @staticmethod
    def _pick(mnemonic: bytes, frames: list) -> Optional[bytes]:
        """The answer to our frame: the one starting with the mnemonic, or a
        bare error byte; never RX data, monitor or link frames."""
        for f in frames:
            if f.kind in (FrameKind.CMD_RESP, FrameKind.STATUS_ERR) and (
                    f.data.startswith(mnemonic) or host_error_code(f.data) is not None):
                return f.data
        return None

    # -- verbose -----------------------------------------------------------
    def verbose_set(self, name: str, value: str) -> str:
        _found, raw = self._sm.send_verbose_command(f"{name} {value}\r\n".encode("ascii"))
        return raw.decode("ascii", errors="replace")

    def verbose_query(self, name: str) -> Optional[str]:
        return self._sm.query_verbose_value(name)

    def verbose_query_text(self, command: str) -> str:
        _found, raw = self._sm.send_verbose_command(f"{command}\r\n".encode("ascii"))
        return raw.decode("ascii", errors="replace")

    def escape_converse(self) -> bool:
        def send_and_wait(data: bytes, timeout: float) -> bytes:
            return self._sm.send_verbose_command(data, timeout)[1]
        found, _raw = escape_converse(send_and_wait, bytes([self._sm.command_char]))
        return found

    def return_to_converse(self) -> None:
        self._sm.write_verbose(b"CONVERSE\r\n")
