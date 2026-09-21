#!/usr/bin/env python3
# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS - GPL v2
#
# This is a DEV-ONLY hardware verification tool. It is never shipped with
# the application. GPL v2, same as the rest of tools/ (see tools/README.md).
"""hw_check.py - solo hardware checks for a real PK-232MBX (P14).

Four checks an operator can run alone, with the real TNC, no second
station required except for T101:

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
    all     t17 + t103 + pthuff. Deliberately NOT t101 (it transmits and
            needs a second receiver, so it must be run on its own).

Usage::

    python tools/hw_check.py --port COM3 t17
    python tools/hw_check.py --port COM3 all
    python tools/hw_check.py --port COM3 t101
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

Log files land in hw_logs/YYYYMMDD_HHMMSS_<test>.log (gitignored - the
summary printed at the end of each run is what gets copied into
Testplan.md; the raw per-byte log stays local).
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
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
from pk232py.config import AppConfig, ConfigManager  # noqa: E402


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
    $16, Ctrl-V) - not a toggle. PX = PASSALL, a Y/N toggle. The
    application currently sends 'PS' for the PASSALL button; this
    function only classifies which response LOOKS like a Y/N toggle -
    it does not assume which one is right.
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


def run_with_restore(
    query: Callable[[], str],
    set_value: Callable[[str], None],
    new_value: str,
    action: Callable[[], None],
) -> str:
    """Query the current value, set *new_value*, run *action*, and ALWAYS
    restore the original value afterwards - even if *action* raises
    (hard rule #2). Returns the original value.

    Pure orchestration: query/set_value/action are plain callables, so this
    is unit-testable with fakes, no serial interface involved.
    """
    original = query()
    try:
        set_value(new_value)
        action()
    finally:
        set_value(original)
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

    def __init__(self, port: str, baud: int, dry_run: bool, log: RunLog):
        self.port_name = port
        self.baud = baud
        self.dry_run = dry_run
        self.log = log
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

    # -- Host-mode frames ----------------------------------------------------

    def query_host(self, mnemonic: bytes, timeout: float = 2.0) -> list:
        """Send a Host Mode query (mnemonic, no args) and return every frame
        the TNC replies with inside *timeout*."""
        if self.dry_run:
            self.log.line(f"[dry-run] would send Host Mode query {mnemonic!r}")
            return []
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
    log.line("--- T17: PASSALL mnemonic (PS vs PX) ---")
    if session.dry_run:
        log.line("[dry-run] would query PX, then PS, in verbose mode")
        log.result("T17", "INFO", "dry-run, nothing sent")
        return

    px = session.query("PX")
    ps = session.query("PS")
    verdict = evaluate_t17(px, ps)
    if verdict["passall_mnemonic"] == "PX":
        log.result(
            "T17", "FAIL",
            "PASSALL is PX, not PS - the app's PASSALL toggle sends the "
            "wrong mnemonic (see packet_screen.py toggle_map)"
        )
    elif verdict["passall_mnemonic"] == "PS":
        log.result("T17", "PASS", "PASSALL is PS - the app's toggle is correct")
    else:
        log.result(
            "T17", "INCONCLUSIVE",
            f"could not classify from responses (PX={px!r}, PS={ps!r})"
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

    before = session.query("USERS")
    log.line(f"USERS before: {before!r}")
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
        after = session.query("USERS")
        log.line(f"USERS after upload: {after!r}")
        if "4" in after:
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
        query=lambda: before,
        set_value=lambda v: session.set_verbose("USERS", str(real_users)),
        new_value="4",
        action=do_upload,
    )
    log.line(f"USERS restored to {real_users}")


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

    before = session.query("PTHUFF")
    fmt = detect_pthuff_format(before)
    log.line(f"PTHUFF before: {before!r} (looks like: {fmt})")

    # Best-effort restore value: the TNC's own reported format is not known
    # until this test runs, so the last whitespace-separated token of the
    # ORIGINAL response is replayed as-is. Logged clearly either way.
    restore_token = before.split()[-1] if before.split() else "0"

    def do_set() -> None:
        session.verbose_bytes(sent_cmd)
        after = session.query("PTHUFF")
        log.line(f"PTHUFF after {sent_cmd!r}: {after!r}")
        if fmt == "numeric":
            log.result(
                "PTHUFF", "FAIL",
                f"TNC reports a numeric value ({before!r}) but the uploader "
                f"sends ON/OFF ({sent_cmd!r}) - type mismatch confirmed "
                f"(see PACTORConfig.pthuff / Backlog.md)"
            )
        elif fmt == "on_off":
            log.result("PTHUFF", "PASS", "TNC's own format is ON/OFF, matches the uploader")
        else:
            log.result("PTHUFF", "INCONCLUSIVE", f"could not classify response {before!r}")

    run_with_restore(
        query=lambda: before,
        set_value=lambda v: session.set_verbose("PTHUFF", restore_token),
        new_value="",
        action=do_set,
    )
    log.line(f"PTHUFF restore attempted with {restore_token!r} (best effort - see log)")


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
            "then restore UNPROTO/MONITOR"
        )
        log.result("T101", "INFO", "dry-run, nothing sent")
        return

    if input("Ready to continue? [y/N] ").strip().lower() != "y":
        log.result("T101", "INFO", "skipped by operator")
        return

    orig_unproto = session.query("UNPROTO")
    orig_monitor = session.query("MONITOR")
    log.line(f"UNPROTO before: {orig_unproto!r}")
    log.line(f"MONITOR before: {orig_monitor!r}")
    restore_unproto = orig_unproto.split()[-1] if orig_unproto.split() else "CQ"
    restore_monitor = orig_monitor.split()[-1] if orig_monitor.split() else "4"

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

    try:
        run_rounds()
    finally:
        session.exit_host_mode()
        session.set_verbose("UNPROTO", restore_unproto)
        session.set_verbose("MONITOR", restore_monitor)
        log.line("UNPROTO/MONITOR restored")

    verdict = evaluate_t101(targets_seen["A"], targets_seen["B"])
    log.result(
        "T101", verdict,
        f"round A destination seen={targets_seen['A']!r}, "
        f"round B destination seen={targets_seen['B']!r}"
    )


# ===========================================================================
# CLI
# ===========================================================================

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="hw_check.py",
        description=(
            "Solo hardware verification for a real PK-232MBX (P14). "
            "t17/t103/pthuff only query/set parameters; t101 TRANSMITS "
            "and needs a second receiver."
        ),
    )
    p.add_argument("test", choices=["t17", "t103", "pthuff", "t101", "all"])
    p.add_argument("--port", help="Serial port, e.g. COM3 (default: pk232py.ini)")
    p.add_argument("--baud", type=int, help="Baud rate (default: pk232py.ini)")
    p.add_argument(
        "--dry-run", action="store_true",
        help="Show what each test would send; never opens the port"
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

    session = Session(port or "DRYRUN", baud or 9600, args.dry_run, log)

    test_fns: dict[str, list] = {
        "t17":    [lambda s, l: test_t17(s, l)],
        "t103":   [lambda s, l: test_t103(s, l, app_config)],
        "pthuff": [lambda s, l: test_pthuff(s, l, app_config)],
        "t101":   [lambda s, l: test_t101(s, l)],
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
