# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""pk232_hostmode_sub.py — Host Mode entry subprocess + HostModeWorker.

Subprocess (called via subprocess.run):
    python pk232_hostmode_sub.py PORT BAUD
    Prints "OK" or "FAIL:hexdata"

HostModeWorker (imported by serial_manager.py):
    Single thread, owns serial port in Host Mode.
    Full-duplex: TX and RX run independently.
    Loop: send pending frames, read available bytes, parse, dispatch.
"""

import logging
import queue
import sys
import threading
import time
from typing import Callable

logger = logging.getLogger(__name__)

SOH = 0x01
ETB = 0x17
DLE = 0x10

HPOLL_Y   = bytes([SOH, 0x4F, ord('H'), ord('P'), ord('Y'), ETB])
HPOLL_ACK = bytes([SOH, 0x4F, ord('H'), ord('P'), 0x00,     ETB])
HPOLL_OFF = bytes([SOH, 0x4F, ord('H'), ord('P'), ord('N'), ETB])
HOST_OFF  = bytes([SOH, 0x4F, ord('H'), ord('O'), ord('N'), ETB])
# P66, Teil A.2: OPMODE query (TRM 4.3.2) - a genuine Host Mode answer
# carries a value byte after the mnemonic (e.g. 'OPPA' for Packet); the
# query itself never does, so a byte-identical echo (Converse, P52.2's
# rule applied here) is distinguishable from a real answer by length
# alone, same as the P43 detection chain's own is_hpoll_echo().
OPMODE_QUERY = bytes([SOH, 0x4F, ord('O'), ord('P'), ETB])

# P66, Teil A: literal timeouts named as module constants (P61's own
# convention - see serial_manager.py's _FAST_TIMING_CONSTANTS) so tests
# can scale every one of them down via monkeypatch instead of paying
# real hardware wait times.
_PRE_HANDSHAKE_SETTLE   = 0.3   # after opening the port, before the first write
_ESCAPE_CONVERSE_TIMEOUT = 2.0  # per COMMAND-char attempt in escape_converse()
_HOST3_SETTLE_TIMEOUT   = 2.0   # waiting for 'cmd:cmd:' after HOST 3
_CR_SETTLE_TIMEOUT      = 1.0   # waiting for '\r\n' after the follow-up CR
_HPOLL_TIMEOUT          = 2.0   # waiting for HPOLL_ACK/HPOLL_Y after HPOLL_Y
_OPMODE_TIMEOUT         = 2.0   # waiting for the OPMODE query's own answer

# P66b, Teil B: a real hardware run (T141, 28.09.2026, Device B,
# 13:35, "20260928_133500_link_carry.log") found the command
# interpreter can lag SECONDS behind the immediate character echo
# while a connection is active (B.1: the XFLOW OFF response arrived
# only after the HPOLL_Y echo had already been read) - HOST 3 can
# still take effect AFTER the OPMODE check above already gave up. An
# echo proves the TNC was NOT YET in Host Mode at that instant, not
# that it never will be, so a failed check is retried a few times
# before concluding failure - this "late entry" retry only ever runs
# on the failure path, never slowing down the normal (already
# succeeded) case. Named here, not hardcoded, so a future hardware
# measurement (P66b, Teil E) can retune them.
_LATE_ENTRY_RETRIES  = 3
_LATE_ENTRY_INTERVAL = 1.5


# ---------------------------------------------------------------------------
# Serial helpers
# ---------------------------------------------------------------------------

def read_until(port, marker, timeout=3.0):
    buf = bytearray()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        n = port.in_waiting
        if n:
            buf.extend(port.read(n))
            markers = marker if isinstance(marker, (list, tuple)) else [marker]
            if any(m in buf for m in markers):
                return bytes(buf)
            deadline = time.monotonic() + 0.15
        else:
            time.sleep(0.02)
    return bytes(buf)


def extract_frames(buf):
    """Parse buffer into (ctl, payload) tuples. Returns (frames, remaining)."""
    frames = []
    remaining = buf
    while True:
        soh = next((i for i, b in enumerate(remaining) if b == SOH), -1)
        if soh < 0:
            remaining = bytearray()
            break
        etb = -1
        i = soh + 2
        while i < len(remaining):
            if remaining[i] == DLE:
                i += 2
                continue
            if remaining[i] == ETB:
                etb = i
                break
            i += 1
        if etb < 0:
            remaining = remaining[soh:]
            break
        raw = bytes(remaining[soh:etb + 1])
        remaining = remaining[etb + 1:]
        ctl = raw[1] if len(raw) > 1 else 0
        payload = bytearray()
        j = 2
        while j < len(raw) - 1:
            if raw[j] == DLE and j + 1 < len(raw) - 1:
                payload.append(raw[j + 1])
                j += 2
            else:
                payload.append(raw[j])
                j += 1
        frames.append((ctl, bytes(payload)))
    return frames, remaining


# ---------------------------------------------------------------------------
# Converse escape (P66, Teil A.1; corrected P66a B.2 - Converse only)
# ---------------------------------------------------------------------------

def escape_converse(
    send_and_wait: Callable[[bytes, float], bytes],
    command_char: bytes,
    attempts: int = 3,
    timeout: float = _ESCAPE_CONVERSE_TIMEOUT,
) -> tuple[bool, bytes]:
    """Send the TNC's own COMMAND character (plus CR) up to *attempts*
    times to escape back to the 'cmd:' prompt from Converse (needs one
    - TRM; CLAUDE.md P53.B) before anything else is sent.

    Converse only. Transparent needs three COMMAND characters within
    CMDTIME with no other bytes in between - this function sends a CR
    after each one and waits between attempts, so it cannot leave
    Transparent. See Backlog (P66a, B.2) - not a fix here, since
    pk232py switches into Transparent nowhere today.

    *send_and_wait(data, timeout)* is the caller's own write-then-read
    primitive - a raw pyserial port for
    pk232_hostmode_sub.enter_host_mode() (Teil A), the detection chain's
    own direct-read closure for SerialManager._init_tnc_thread()'s step
    2b, or Session's write_verbose()/read_until_idle() combo for
    tools/hw_check.py's link_carry (Teil C) - so this stays a pure
    decision function with no port/Qt dependency of its own, callable
    from all three without three separate implementations of "send the
    COMMAND character and check for cmd:".

    Returns (cmd_prompt_seen, all_bytes_seen_across_every_attempt) -
    'found' is True the instant one attempt's response contains 'cmd:',
    without trying further attempts; False only once every attempt has
    been tried and none saw it.
    """
    raw = bytearray()
    for _ in range(attempts):
        resp = send_and_wait(command_char + b"\r", timeout)
        raw.extend(resp)
        if b"cmd:" in resp:
            return True, bytes(raw)
    return False, bytes(raw)


# ---------------------------------------------------------------------------
# HostModeWorker
# ---------------------------------------------------------------------------

class HostModeWorker(threading.Thread):
    """Single thread owning the serial port in Host Mode.

    Full-duplex loop:
      - Send pending TX frames from queue (non-blocking)
      - Read all available RX bytes
      - Parse complete frames and dispatch
      - Repeat every 10ms
    """

    def __init__(self, port, frame_callback, raw_callback=None):
        super().__init__(daemon=True, name="PK232-HostWorker")
        self._port     = port
        self._on_frame = frame_callback   # called with (ctl, payload)
        self._on_raw   = raw_callback     # called with raw bytes (optional)
        self._queue    = queue.Queue()
        self._stop     = threading.Event()
        self._buf      = bytearray()

    def send(self, data: bytes) -> None:
        """Queue frame for sending. Thread-safe."""
        self._queue.put(data)

    def stop(self) -> None:
        self._stop.set()
        self._queue.put(None)

    def wait_for_ack(self, mnemonic: bytes, timeout: float = 2.0) -> bool:
        """Block until a CMD_RESP ACK for mnemonic is received, or timeout.
        Used by serial_manager to wait for HP N ACK before proceeding.
        """
        import threading as _t
        event = _t.Event()
        original_cb = self._on_frame

        def _watch(ctl, payload):
            original_cb(ctl, payload)
            if ctl == 0x4F and payload[:2] == mnemonic:
                event.set()

        self._on_frame = _watch
        result = event.wait(timeout=timeout)
        self._on_frame = original_cb
        return result

    def run(self) -> None:
        logger.debug("HostModeWorker started")
        port = self._port

        while not self._stop.is_set():

            # --- TX: send one pending frame (non-blocking) ---
            try:
                data = self._queue.get_nowait()
                if data is None:
                    break
                port.write(data)
                port.flush()
                logger.debug("TX (%d B): %s", len(data), data.hex(' '))
            except queue.Empty:
                pass
            except Exception as exc:
                if not self._stop.is_set():
                    logger.error("HostModeWorker TX: %s", exc)
                break

            # --- RX: read all available bytes ---
            try:
                n = port.in_waiting
                if n:
                    chunk = port.read(n)
                    if self._on_raw:
                        self._on_raw(chunk)
                    self._buf.extend(chunk)
                    # Parse and dispatch complete frames
                    frames, self._buf = extract_frames(self._buf)
                    for ctl, payload in frames:
                        logger.debug("HW frame ctl=0x%02X payload=%s",
                                     ctl, payload.hex())
                        try:
                            self._on_frame(ctl, payload)
                        except Exception as exc:
                            logger.error("HostModeWorker dispatch: %s", exc)
            except Exception as exc:
                if not self._stop.is_set():
                    logger.error("HostModeWorker RX: %s", exc)
                break

            time.sleep(0.01)

        logger.debug("HostModeWorker stopped")


# ---------------------------------------------------------------------------
# Subprocess entry point
# ---------------------------------------------------------------------------

def enter_host_mode(
    port_name: str, baud: int, command_char: bytes = b"\x03",
) -> tuple[bool, bytes]:
    """Run the proven Host Mode entry handshake on a freshly opened port.

    Opens its OWN ``serial.Serial`` object, runs the exact byte sequence
    (``HOST 3`` + ``HPOLL Y``), closes it again, and returns
    ``(success, raw_response)``.

    This is the SAME sequence the ``__main__`` subprocess runs, factored out so
    that ``serial_manager`` can call it **in-process** when the app is a Nuitka
    ``--onefile`` build: a onefile binary contains no ``python.exe`` to spawn
    this file as a script, and ``sys.executable`` points at the app EXE. In a
    normal interpreter, ``serial_manager`` still spawns ``__main__`` as a
    subprocess (unchanged, proven). The handshake uses direct ``port.read()``
    so the Prolific ACK path is unaffected (CLAUDE.md §3).

    P66, Teil A: the previous version assumed the TNC was already at the
    'cmd:' prompt and treated HPOLL_Y in the response as success on its
    own. Confirmed wrong by a real hardware run (T141, 28.09.2026, Device
    B, 20260928_094001_link_carry.log): after a verbose CONNECT the TNC
    was in Converse, not the command prompt - HOST 3 was never seen by
    the command interpreter at all, and every "response" below (HPOLL_Y
    included) was Converse echoing the exact bytes just sent back
    verbatim (CLAUDE.md, "In Converse echot der TNC auch Host-Frames").
    Two independent fixes:

      A.1 - escape_converse() sends *command_char* first and waits for a
      real 'cmd:' prompt before HOST 3 is sent at all. Its own result is
      not itself required for success below (an already-idle TNC may
      answer nothing recognisable to a bare COMMAND char either) - HOST
      3 is sent regardless, and A.2's OPMODE check is what actually
      proves something happened.

      A.2 - HPOLL_Y/HPOLL_ACK in the response is no longer sufficient:
      Converse echoes those bytes back exactly, HPOLL_Y included. An
      OPMODE query (TRM 4.3.2) is sent as a THIRD check - a real Host
      Mode answer carries a value byte the query itself never has (e.g.
      'OPPA'), so an echo is distinguishable from a genuine answer by
      length alone (see OPMODE_QUERY's own comment). Success now
      requires BOTH HPOLL_ACK (HP $00) - HPOLL_Y alone is no longer
      accepted, since that is exactly the byte sequence an echo
      reproduces - AND a genuine OPMODE answer.

    P66b, Teil A/B: a real hardware run (T141, 28.09.2026, Device B)
    found the A.2 OPMODE check can itself see only an echo, then HOST 3
    takes effect ANYWAY a few seconds later - the command interpreter
    can lag seconds behind the immediate character echo while a
    connection is active (B.1: the delayed 'XFlow was ON' answer to the
    EARLIER 'XFLOW OFF' arrived only after the HPOLL_Y echo had already
    been read). So a failed OPMODE check is retried up to
    _LATE_ENTRY_RETRIES times, _LATE_ENTRY_INTERVAL s apart, before
    concluding failure - a success on a retry is a genuine "late
    entry", logged as such with its attempt number, never guessed as
    the first check's own result. Every step (escape_converse, HOST 3,
    the follow-up CR, HPOLL_Y, the OPMODE check and each of its
    retries) is timestamped (monotonic, ms since the handshake started)
    with what was sent and everything that was read for it - on
    success this goes to logger.debug (cheap, usually discarded); on
    failure it is written to stderr in full, one line per step, since
    B.1 could not otherwise be resolved from the FAIL: summary alone
    (Teil B.2's own finding - that summary only ever held the LAST few
    steps' bytes, with no timing information at all).
    """
    import serial

    t0 = time.monotonic()
    steps: list[tuple[float, str, bytes, bytes]] = []

    def _record(label: str, sent: bytes, received: bytes) -> None:
        steps.append((time.monotonic() - t0, label, sent, received))

    def _log_steps(success: bool) -> None:
        for elapsed, label, sent, received in steps:
            line = (
                f"enter_host_mode step {label!r} +{elapsed * 1000:.0f}ms "
                f"tx={sent.hex(' ')} rx={received.hex(' ')} "
                f"rx_text={received.decode('ascii', errors='replace')!r}"
            )
            if success:
                logger.debug(line)
            else:
                print(line, file=sys.stderr)

    port = serial.Serial(port_name, baud, bytesize=8, parity='N', stopbits=1,
                         timeout=0.1, xonxoff=False, rtscts=False)
    try:
        time.sleep(_PRE_HANDSHAKE_SETTLE)
        port.reset_input_buffer()

        # A.1: leave Converse before HOST 3 is even sent (P66a, B.2:
        # not Transparent - see escape_converse()'s own docstring).
        def _send_and_wait(data: bytes, timeout: float) -> bytes:
            port.write(data)
            port.flush()
            return read_until(port, b"cmd:", timeout)

        _escaped, escape_raw = escape_converse(_send_and_wait, command_char)
        _record("escape_converse", command_char + b"\r", escape_raw)

        host3_cmd = b"\rXFLOW OFF\r\rHOST 3"
        port.write(host3_cmd)
        port.flush()
        host3_resp = read_until(port, b"cmd:cmd:", timeout=_HOST3_SETTLE_TIMEOUT)
        _record("host3", host3_cmd, host3_resp)

        port.write(b"\r")
        port.flush()
        cr_resp = read_until(port, b"\r\n", timeout=_CR_SETTLE_TIMEOUT)
        _record("cr", b"\r", cr_resp)

        port.write(HPOLL_Y)
        port.flush()
        r = read_until(port, [HPOLL_ACK, HPOLL_Y], timeout=_HPOLL_TIMEOUT)
        _record("hpoll", HPOLL_Y, r)

        # A.2: HP $00 stays required; HP Y alone is no longer accepted
        # (it is exactly what an echo reproduces - see the docstring).
        port.write(OPMODE_QUERY)
        port.flush()
        op_raw = read_until(port, bytes([ETB]), timeout=_OPMODE_TIMEOUT)
        _record("opmode", OPMODE_QUERY, op_raw)
        op_frames, _remaining = extract_frames(bytearray(op_raw))
        got_real_opmode_answer = any(
            ctl == 0x4F and payload[:2] == b'OP' and len(payload) > 2
            for ctl, payload in op_frames
        )

        success = (HPOLL_ACK in r) and got_real_opmode_answer
        raw_all = r + op_raw

        # Teil B (P66b, B.1): HOST 3 may take effect AFTER this check
        # already gave up - retry the OPMODE query itself a few times
        # before concluding failure. Only the failure path pays for
        # this; a normal (already-succeeded) entry is unaffected.
        late_entry_attempt = 0
        while not success and late_entry_attempt < _LATE_ENTRY_RETRIES:
            late_entry_attempt += 1
            time.sleep(_LATE_ENTRY_INTERVAL)
            port.write(OPMODE_QUERY)
            port.flush()
            retry_raw = read_until(port, bytes([ETB]), timeout=_OPMODE_TIMEOUT)
            _record(f"opmode retry {late_entry_attempt}", OPMODE_QUERY, retry_raw)
            raw_all += retry_raw
            retry_frames, _remaining2 = extract_frames(bytearray(retry_raw))
            if any(
                ctl == 0x4F and payload[:2] == b'OP' and len(payload) > 2
                for ctl, payload in retry_frames
            ):
                success = True

        if not success:
            logger.warning(
                "enter_host_mode: echo instead of Host Mode response - "
                "TNC probably in Converse/Transparent (hpoll_ack=%s "
                "opmode_raw=%s)",
                HPOLL_ACK in r, op_raw.hex(),
            )
        elif late_entry_attempt:
            logger.info(
                "enter_host_mode: late entry - HOST 3 took effect after "
                "OPMODE retry attempt %d (P66b, B.1)",
                late_entry_attempt,
            )

        _log_steps(success)
        return success, raw_all
    finally:
        port.close()


if __name__ == "__main__":
    import sys

    _command_char = bytes([int(sys.argv[3])]) if len(sys.argv) > 3 else b"\x03"
    ok, resp = enter_host_mode(sys.argv[1], int(sys.argv[2]), _command_char)
    print(("OK:" if ok else "FAIL:") + resp.hex())