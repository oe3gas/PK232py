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
import threading
import time

logger = logging.getLogger(__name__)

SOH = 0x01
ETB = 0x17
DLE = 0x10

HPOLL_Y   = bytes([SOH, 0x4F, ord('H'), ord('P'), ord('Y'), ETB])
HPOLL_ACK = bytes([SOH, 0x4F, ord('H'), ord('P'), 0x00,     ETB])
HPOLL_OFF = bytes([SOH, 0x4F, ord('H'), ord('P'), ord('N'), ETB])
HOST_OFF  = bytes([SOH, 0x4F, ord('H'), ord('O'), ord('N'), ETB])


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

if __name__ == "__main__":
    import serial
    import sys

    PORT = sys.argv[1]
    BAUD = int(sys.argv[2])

    port = serial.Serial(PORT, BAUD, bytesize=8, parity='N', stopbits=1,
                         timeout=0.1, xonxoff=False, rtscts=False)
    time.sleep(0.3)
    port.reset_input_buffer()

    port.write(b"\rXFLOW OFF\r\rHOST 3")
    port.flush()
    read_until(port, b"cmd:cmd:", timeout=2.0)

    port.write(b"\r")
    port.flush()
    read_until(port, b"\r\n", timeout=1.0)

    port.write(HPOLL_Y)
    port.flush()
    r = read_until(port, [HPOLL_ACK, HPOLL_Y], timeout=2.0)

    # Accept both HP /bin/sh0 (ACK) and HP Y (already in HPOLL ON) as success
    if HPOLL_ACK in r or HPOLL_Y in r:
        print("OK")
    else:
        print("FAIL:" + r.hex())
    port.close()