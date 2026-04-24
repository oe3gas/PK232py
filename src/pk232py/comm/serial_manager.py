# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Serial port manager for the AEA PK-232 / PK-232MBX.

Initialisation flow (3 phases):
  Phase 1 — init_tnc():
      Sends '*', detects TNC state (fresh boot / already active / Host Mode),
      sends AWLEN + PARITY + RESTART if needed.
      Emits verbose_mode_ready when TNC is at cmd: prompt.

  Phase 2 — ParamsUploader.upload():
      Sends all stored parameters as verbose-mode ASCII commands.
      Called externally after verbose_mode_ready.

  Phase 3 — enter_host_mode():
      Sends HOST 3 (XON + CANLINE + COMMAND + HOST Y).
      Emits host_mode_changed(True) when complete.

This separation allows running in verbose mode only (for diagnostics)
and gives the user control over when to switch to Host Mode.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

try:
    import serial
    import serial.tools.list_ports
    PYSERIAL_AVAILABLE = True
except ImportError:
    PYSERIAL_AVAILABLE = False

from PyQt6.QtCore import QObject, pyqtSignal

from .constants import (
    SerialDefaults,
    FRAME_POLL,
    FRAME_RECOVERY,
    FRAME_HOST_OFF,
    CTL_TX_DATA_BASE,
)
from .pk232_hostmode_sub import HostModeWorker as _HostModeWorker
from .frame import (
    HostFrame,
    FrameKind,
    FrameParser,
    build_command,
    build_ch_cmd,
    build_data,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Timing constants (seconds) — tuned against real PK-232MBX v7.1
# ---------------------------------------------------------------------------
_WAKEUP_TIMEOUT  = 3.0   # max wait for TNC response to '*'
_CMD_DELAY       = 0.15  # pause between verbose-mode commands
_RESTART_DELAY   = 3.0   # wait after RESTART for TNC banner + cmd:
_HOSTMODE_DELAY  = 0.8   # wait after HOST Y before GG poll
_GG_MAX_RETRIES  = 5     # max GG poll retries
_GG_RETRY_DELAY  = 0.5   # delay between retries
_POLL_TIMEOUT    = 3.0   # wait for GG poll ACK

# Byte sequences
_WAKEUP       = b"*"                               # no CR — autobaud trigger
_CMD_AWLEN    = b"AWLEN 8\r\n"
_CMD_PARITY   = b"PARITY 0\r\n"
_CMD_8BITCONV = b"8BITCONV ON\r\n"
_CMD_RESTART  = b"RESTART\r\n"
# PCPackRatt-verified: "HOST 3" activates Host Mode with poll level 3
# (not "HOST Y" — "HOST 3" is an undocumented/expert command)
_CMD_HOST_3   = b"HOST 3\r"
_CMD_HPOLL_Y  = bytes([0x01, 0x4F, ord('H'), ord('P'), ord('Y'), 0x17])
_HPOLL_ACK    = bytes([0x01, 0x4F, ord('H'), ord('P'), 0x00, 0x17])

# TNC response classifiers
_BANNER_MARKERS = (b"AEA", b"Ver.", b"PK-232", b"Copyright")
_PROMPT_MARKER  = b"cmd:"
_SOH_BYTE       = 0x01


# ---------------------------------------------------------------------------
# Background reader thread
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Host Mode frame extraction — proven in pk232_hostmode.py
# Handles DLE escaping per AEA TRM Section 4.4
# ---------------------------------------------------------------------------
_SOH_BYTE = 0x01
_ETB_BYTE = 0x17
_DLE_BYTE = 0x10
_CTL_BYTE = 0x4F

def _extract_frames(buf: bytearray):
    """Extract complete Host Mode frames from a bytearray.

    Returns (list_of_HostFrame_tuples, remaining_buf).
    Each tuple is (ctl: int, payload: bytes).
    Handles DLE-escaped bytes inside payload.
    """
    frames    = []
    remaining = buf
    while True:
        soh_pos = next((i for i, b in enumerate(remaining) if b == _SOH_BYTE), -1)
        if soh_pos < 0:
            remaining = bytearray()
            break
        etb_pos = -1
        i = soh_pos + 2          # skip SOH + CTL
        while i < len(remaining):
            if remaining[i] == _DLE_BYTE:
                i += 2
                continue
            if remaining[i] == _ETB_BYTE:
                etb_pos = i
                break
            i += 1
        if etb_pos < 0:
            remaining = remaining[soh_pos:]
            break
        raw       = bytes(remaining[soh_pos:etb_pos + 1])
        remaining = remaining[etb_pos + 1:]
        ctl       = raw[1] if len(raw) > 1 else 0
        payload   = bytearray()
        j = 2
        while j < len(raw) - 1:
            if raw[j] == _DLE_BYTE and j + 1 < len(raw) - 1:
                payload.append(raw[j + 1])
                j += 2
            else:
                payload.append(raw[j])
                j += 1
        frames.append((ctl, bytes(payload)))
    return frames, remaining


def _make_host_frame(ctl: int, payload: bytes):
    """Map (ctl, payload) to a HostFrame object."""
    from .frame import HostFrame, FrameKind
    if ctl == 0x4F:
        kind = FrameKind.CMD_RESP
    elif ctl == 0x3F:
        kind = FrameKind.RX_MONITOR
    elif 0x30 <= ctl <= 0x39:
        kind = FrameKind.RX_DATA
    elif ctl == 0x2F:
        kind = FrameKind.ECHO
    elif ctl == 0x5F:
        kind = FrameKind.STATUS_ERR
    elif 0x50 <= ctl <= 0x5E:
        kind = FrameKind.LINK_MSG
    else:
        kind = FrameKind.CMD_RESP
    ch = (ctl - 0x30) if 0x30 <= ctl <= 0x39 else 15
    return HostFrame(kind=kind, ctl=ctl, channel=ch, data=payload)



class _ReaderThread(threading.Thread):
    def __init__(self, port, frame_callback, raw_callback=None,
                 host_mode_flag=None) -> None:
        super().__init__(daemon=True, name="PK232-Reader")
        self._port           = port
        self._callback       = frame_callback
        self._raw_callback   = raw_callback
        self._host_mode_flag = host_mode_flag or (lambda: False)
        self._stop_event     = threading.Event()
        self._parser         = FrameParser(self._on_frame)

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        logger.debug("ReaderThread started")
        _buf = bytearray()
        while not self._stop_event.is_set():
            try:
                raw = self._port.read(64)
                if raw:
                    if self._raw_callback:
                        self._raw_callback(raw)
                    if self._host_mode_flag():
                        # Use _extract_frames — proven DLE-aware parser
                        _buf.extend(raw)
                        frames, _buf = _extract_frames(_buf)
                        for ctl, payload in frames:
                            try:
                                frame = _make_host_frame(ctl, payload)
                                logger.debug("RX %r", frame)
                                self._callback(frame)
                            except Exception as exc:
                                logger.error("Frame dispatch: %s", exc)
                    else:
                        # Verbose mode: use legacy parser
                        self._parser.feed(raw)
            except Exception as exc:
                if not self._stop_event.is_set():
                    logger.error("Serial read error: %s", exc)
                break
        logger.debug("ReaderThread stopped")

    def _on_frame(self, frame: HostFrame) -> None:
        try:
            self._callback(frame)
        except Exception as exc:
            logger.error("Frame callback raised: %s", exc)

    def reset_parser(self) -> None:
        self._parser.reset()


# ---------------------------------------------------------------------------
# SerialManager
# ---------------------------------------------------------------------------

class SerialManager(QObject):
    """Manages the serial connection to the PK-232 / PK-232MBX.

    Qt Signals
    ----------
    frame_received(HostFrame)
        Every complete Host Mode frame from the TNC.

    connection_changed(bool)
        True = port opened, False = port closed.

    verbose_mode_ready()
        TNC is in verbose COMMAND mode — ready for parameter upload.

    host_mode_changed(bool)
        True = Host Mode active, False = Host Mode left.

    params_upload_required()
        TNC rebooted (RESTART) — parameters must be re-uploaded.

    status_message(str)
        Human-readable status for the status bar.
    """

    frame_received         = pyqtSignal(object)  # HostFrame
    raw_data_received      = pyqtSignal(bytes)   # verbose mode raw bytes
    connection_changed     = pyqtSignal(bool)
    verbose_mode_ready     = pyqtSignal()
    host_mode_changed      = pyqtSignal(bool)
    params_upload_required = pyqtSignal()
    status_message         = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._serial:          Optional["serial.Serial"] = None
        self._reader:          Optional[_ReaderThread]   = None
        self._in_host_mode     = False
        self._verbose_ready    = False
        self._poll_active      = False
        self._poll_thread      = None
        self._worker           = None  # _HostModeWorker in Host Mode
        self._write_lock       = threading.Lock()
        # Shared buffer: ReaderThread writes here, _read_raw_until reads here
        self._rx_buf           = bytearray()
        self._rx_buf_lock      = threading.Lock()
        self._rx_buf_event     = threading.Event()

    # ------------------------------------------------------------------
    # Port management
    # ------------------------------------------------------------------

    def connect_port(self, port_name: str, baudrate: int = SerialDefaults.BAUDRATE) -> bool:
        """Open the serial port.

        xonxoff=False: XON ($11) must pass through unfiltered for HOST 3.
        rtscts=False:  PK-232 uses XON/XOFF flow control, not hardware handshaking.
        """
        if not PYSERIAL_AVAILABLE:
            self.status_message.emit("Error: pyserial not installed")
            return False
        if self.is_connected:
            logger.warning("Port already open")
            return False
        try:
            self._serial = serial.Serial(
                port     = port_name,
                baudrate = baudrate,
                bytesize = serial.EIGHTBITS,
                parity   = serial.PARITY_NONE,
                stopbits = serial.STOPBITS_ONE,
                timeout  = SerialDefaults.TIMEOUT,
                xonxoff  = False,
                rtscts   = False,
                dsrdtr   = False,
            )
            self._serial.rts = False
            self._serial.dtr = False
            logger.info("Port %s opened at %d baud", port_name, baudrate)
            self.status_message.emit(f"Connected: {port_name} @ {baudrate} Bd")
            self._reader = _ReaderThread(
                self._serial,
                self._on_frame_received,
                raw_callback=self._on_raw_data,
                host_mode_flag=lambda: self._in_host_mode,
            )
            self._reader.start()
            self.connection_changed.emit(True)
            return True
        except Exception as exc:
            logger.error("Cannot open %s: %s", port_name, exc)
            self.status_message.emit(f"Connection error: {exc}")
            self._serial = None
            return False

    def disconnect_port(self) -> None:
        # Step 1: leave host mode cleanly (sends HOST OFF, stops ReaderThread)
        if self._in_host_mode:
            try:
                if self._reader:
                    self._reader.stop()
                    self._reader.join(timeout=1.0)
                    self._reader = None
                if self._serial and self._serial.is_open:
                    self._serial.write(FRAME_HOST_OFF)
                    self._serial.flush()
                    time.sleep(0.2)
                self._in_host_mode = False
            except Exception as exc:
                logger.warning("exit host mode during disconnect: %s", exc)

        # Step 2: stop HostModeWorker if running
        if self._worker:
            self._worker.stop()
            self._worker.join(timeout=1.0)
            self._worker = None
        self._poll_active = False
        if self._poll_thread:
            self._poll_thread.join(timeout=1.0)
            self._poll_thread = None

        # Step 3: stop ReaderThread if still running
        if self._reader:
            self._reader.stop()
            self._reader.join(timeout=1.0)
            self._reader = None

        # Step 3: close port
        if self._serial:
            try:
                if self._serial.is_open:
                    self._serial.close()
                    logger.info("Serial port closed")
            except Exception as exc:
                logger.warning("Port close error: %s", exc)
            finally:
                self._serial = None

        self._in_host_mode  = False
        self._verbose_ready = False
        with self._rx_buf_lock:
            self._rx_buf.clear()
        self._rx_buf_event.clear()
        self.connection_changed.emit(False)
        self.status_message.emit("Disconnected")

    @property
    def is_connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    @property
    def is_host_mode(self) -> bool:
        return self._in_host_mode

    @property
    def is_verbose_mode(self) -> bool:
        """True if connected and in verbose mode (not Host Mode)."""
        return self.is_connected and self._verbose_ready and not self._in_host_mode

    # ------------------------------------------------------------------
    # Phase 1 — TNC initialisation → verbose mode
    # ------------------------------------------------------------------

    def init_tnc(self) -> bool:
        """Phase 1: Initialise TNC into verbose COMMAND mode.

        Runs in a background thread. When complete, emits verbose_mode_ready.
        If TNC rebooted (RESTART sent), also emits params_upload_required.
        """
        if not self.is_connected:
            logger.error("init_tnc: not connected")
            return False
        if self._in_host_mode:
            logger.warning("Already in Host Mode")
            return True

        self._verbose_ready = False
        self.status_message.emit("Initialising TNC...")
        t = threading.Thread(target=self._init_tnc_thread, daemon=True, name="PK232-Init")
        t.start()
        return True

    def _init_tnc_thread(self) -> None:
        """Background init — direct serial like pk232_hostmode.py script."""
        try:
            port = self._serial

            # Stop ReaderThread — we do everything directly
            if self._reader:
                self._reader.stop()
                self._reader.join(timeout=2.0)
                self._reader = None

            port.reset_input_buffer()

            # ── Read until marker ──────────────────────────────────────
            def read_until(marker, timeout=3.0):
                buf = bytearray()
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    n = port.in_waiting
                    if n:
                        buf.extend(port.read(n))
                        if isinstance(marker, (list, tuple)):
                            if any(m in buf for m in marker):
                                return bytes(buf)
                        elif marker in buf:
                            return bytes(buf)
                        deadline = time.monotonic() + 0.15
                    else:
                        time.sleep(0.02)
                return bytes(buf)

            # ── STEP 1: Wakeup ─────────────────────────────────────────
            self.status_message.emit("TNC: wakeup...")
            logger.info("Init: sending wakeup '*'")
            port.write(_WAKEUP)
            port.flush()
            resp = read_until(b"cmd:", timeout=_WAKEUP_TIMEOUT)
            logger.debug("Wakeup response (%d B): %s", len(resp), resp.hex(' '))

            if not resp:
                raise RuntimeError("TNC did not respond — check port and baud")

            if _SOH_BYTE in resp:
                logger.info("TNC already in Host Mode")
                self._in_host_mode = True
                self._reader = _ReaderThread(
                    port, self._on_frame_received,
                    raw_callback=self._on_raw_data,
                    host_mode_flag=lambda: self._in_host_mode,
                )
                self._reader.start()
                self.host_mode_changed.emit(True)
                return

            logger.info("TNC at cmd: prompt")
            self._verbose_ready = True
            self.status_message.emit("TNC ready (verbose)")
            logger.info("Init complete — TNC in verbose mode")

            # Restart ReaderThread for verbose mode
            self._reader = _ReaderThread(
                port, self._on_frame_received,
                raw_callback=self._on_raw_data,
                host_mode_flag=lambda: self._in_host_mode,
            )
            self._reader.start()
            self.verbose_mode_ready.emit()

        except Exception as exc:
            logger.error("init_tnc failed: %s", exc)
            self.status_message.emit(f"TNC init error: {exc}")
            if self._reader is None and self._serial and self._serial.is_open:
                self._reader = _ReaderThread(
                    self._serial, self._on_frame_received,
                    raw_callback=self._on_raw_data,
                    host_mode_flag=lambda: self._in_host_mode,
                )
                self._reader.start()


    def _full_init(self) -> None:
        """No-op: PCPackRatt sends nothing before HOST 3 after wakeup.
        AWLEN/PARITY skipped — TNC uses default values which are correct."""
        logger.info("Init: skipping verbose config (PCPackRatt-style)")

    def _short_init(self) -> None:
        """No-op: PCPackRatt sends nothing before HOST 3."""
        logger.info("Init: skipping verbose config (PCPackRatt-style)")

    # ------------------------------------------------------------------
    # Phase 3 — switch to Host Mode
    # ------------------------------------------------------------------

    def enter_host_mode(self) -> bool:
        """Phase 3: Send HOST 3 — switch TNC to binary Host Mode.

        PCPackRatt-verified sequence:
          1. Send "HOST 3\r" in verbose mode
          2. Send HPOLL Y as first Host Mode frame
          3. Wait for HPOLL ACK to confirm Host Mode is active

        Call after Phase 2 (parameter upload) is complete.
        Runs in a background thread.
        """
        if not self.is_connected:
            logger.error("enter_host_mode: not connected")
            return False
        if self._in_host_mode:
            logger.warning("Host Mode already active")
            return True

        t = threading.Thread(
            target=self._enter_host_mode_thread,
            daemon=True,
            name="PK232-HostModeEnter",
        )
        t.start()
        return True

    def _enter_host_mode_thread(self) -> None:
        """Enter Host Mode — exakt wie pk232_minimal_qt.py.

        Bewiesene Sequenz:
          1. ReaderThread stoppen + Port schliessen
          2. Subprocess: HOST 3 + HPOLL Y → OK
          3. Port neu öffnen (frisches Serial Objekt!)
          4. Worker starten
          5. HP N senden + 500ms warten
          6. host_mode_changed emittieren
        """
        import subprocess, sys, os

        try:
            logger.info("Entering Host Mode via subprocess...")
            self.status_message.emit("Entering Host Mode...")

            port_name = self._serial.port
            baudrate  = self._serial.baudrate

            sub_script = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "pk232_hostmode_sub.py"
            )
            if not os.path.exists(sub_script):
                raise FileNotFoundError(f"Not found: {sub_script}")

            # Stop ReaderThread and close port
            if self._reader:
                self._reader.stop()
                self._reader.join(timeout=2.0)
                self._reader = None
            self._serial.close()
            logger.debug("Port closed for subprocess")
            time.sleep(0.3)

            # Run subprocess — proven Host Mode entry sequence
            result = subprocess.run(
                [sys.executable, sub_script, port_name, str(baudrate)],
                capture_output=True, text=True, timeout=15
            )
            output = result.stdout.strip()
            stderr = result.stderr.strip()
            logger.info("Subprocess stdout: %r", output)
            if stderr:
                logger.error("Subprocess stderr: %s", stderr)

            if output != "OK":
                logger.error("Subprocess failed: %r / %s", output, stderr)
                self._serial.open()
                self._reader = _ReaderThread(
                    self._serial, self._on_frame_received,
                    raw_callback=self._on_raw_data,
                    host_mode_flag=lambda: self._in_host_mode,
                )
                self._reader.start()
                self.status_message.emit(f"Host Mode error: {output or stderr}")
                return

            # Reopen port — new Serial object like pk232_minimal_qt.py
            time.sleep(0.3)
            import serial as _serial
            new_port = _serial.Serial(
                port     = port_name,
                baudrate = baudrate,
                bytesize = 8,
                parity   = 'N',
                stopbits = 1,
                timeout  = 0.1,
                xonxoff  = False,
                rtscts   = False,
            )
            # Replace the internal serial object with the fresh one
            self._serial = new_port
            logger.debug("Port reopened (fresh object)")

            self._in_host_mode  = True
            self._verbose_ready = False

            # Frame adapter: (ctl, payload) → HostFrame → Qt Signal
            def _frame_adapter(ctl, payload):
                try:
                    frame = _make_host_frame(ctl, payload)
                    self._on_frame_received(frame)
                except Exception as exc:
                    logger.error("Frame adapter: %s", exc)

            # Start Worker — exakt wie pk232_minimal_qt.py
            from .pk232_hostmode_sub import HostModeWorker as _HMW, HPOLL_OFF
            self._worker = _HMW(
                self._serial, _frame_adapter,
                raw_callback=self._on_raw_data,
            )
            self._worker.start()

            # HP N senden + 500ms warten — bewiesene Sequenz
            self._worker.send(HPOLL_OFF)
            time.sleep(0.5)
            logger.info("HPOLL OFF sent — TNC pushes data spontaneously")

            self.host_mode_changed.emit(True)
            self.status_message.emit("Host Mode active ✓")
            logger.info("Host Mode active!")

        except Exception as exc:
            logger.error("enter_host_mode failed: %s", exc)
            self.status_message.emit(f"Host Mode error: {exc}")
            try:
                if not self._serial.is_open:
                    self._serial.open()
                if self._reader is None:
                    self._reader = _ReaderThread(
                        self._serial, self._on_frame_received,
                        raw_callback=self._on_raw_data,
                        host_mode_flag=lambda: self._in_host_mode,
                    )
                    self._reader.start()
            except Exception:
                pass


    def exit_host_mode(self) -> None:
        """Send HOST OFF binary frame — return TNC to verbose mode."""
        if not self.is_connected or not self._in_host_mode:
            return
        try:
            # Send HOST OFF via Worker — guarantees serialization after pending TX
            if self._worker and self._worker.is_alive():
                self._worker.send(FRAME_HOST_OFF)
                time.sleep(0.5)  # let worker send HOST OFF and read response

            # Stop Worker
            if self._worker:
                self._worker.stop()
                self._worker.join(timeout=1.0)
                self._worker = None

            self._in_host_mode  = False
            self._verbose_ready = False
            time.sleep(0.2)  # wait for TNC to switch back to verbose

            # Start fresh ReaderThread for verbose mode
            self._reader = _ReaderThread(
                self._serial, self._on_frame_received,
                raw_callback=self._on_raw_data,
                host_mode_flag=lambda: self._in_host_mode,
            )
            self._reader.start()

            self.host_mode_changed.emit(False)
            self.status_message.emit("Host Mode off — verbose mode")
            logger.info("Host Mode deactivated")
        except Exception as exc:
            logger.error("exit_host_mode: %s", exc)

    def recovery(self) -> None:
        """Send double-SOH recovery frame (TRM 4.1.6)."""
        if not self.is_connected:
            return
        try:
            self._write_raw(FRAME_RECOVERY)
            time.sleep(0.2)
            self.exit_host_mode()
            self.status_message.emit("Recovery sent")
            logger.info("Recovery frame sent")
        except Exception as exc:
            logger.error("recovery: %s", exc)

    # ------------------------------------------------------------------
    # Sending frames (Host Mode)
    # ------------------------------------------------------------------

    def send_command(self, mnemonic: bytes, args: bytes = b"") -> bool:
        """Send a Host Mode command frame via HostModeWorker queue.

        The worker sends each frame and reads the response before
        processing the next — exactly like pk232_hostmode.py.
        """
        if not self._check_ready():
            return False
        if self._worker and self._worker.is_alive():
            self._worker.send(build_command(mnemonic, args))
            return True
        return self._write_raw(build_command(mnemonic, args))

    def send_channel_command(self, channel: int, mnemonic: bytes, args: bytes = b"") -> bool:
        """Send a channel command frame (CTL=$4x, for CONNECT/DISCONNECT)."""
        if not self._check_ready():
            return False
        return self._write_raw(build_ch_cmd(channel, mnemonic, args))

    def send_data(self, data: bytes, channel: int = 0) -> bool:
        """Send a data frame (CTL=$2x)."""
        if not self._check_ready():
            return False
        return self._write_raw(build_data(channel, data))

    def _poll_loop(self) -> None:
        """GG poll loop — per TRM 4.4.1 (HPOLL ON mode).

        CRITICAL: holds _write_lock for the entire poll+read cycle.
        This prevents _write_raw() from interleaving bytes with our poll.
        The Prolific USB chip coalesces writes — interleaving corrupts frames.
        """
        port = self._serial
        if port is None or not port.is_open:
            return

        logger.debug("GG poll loop started")
        _buf = bytearray()

        while self._poll_active and self._in_host_mode:
            if port is None or not port.is_open:
                break

            try:
                # Hold lock for entire poll+read cycle — no interleaving allowed
                with self._write_lock:
                    port.write(FRAME_POLL)
                    port.flush()

                    # Read response immediately — TNC responds to each poll
                    deadline = time.monotonic() + 0.15
                    while time.monotonic() < deadline:
                        try:
                            n = port.in_waiting
                        except Exception:
                            break
                        if n:
                            chunk = port.read(n)
                            _buf.extend(chunk)
                            logger.debug("GG poll RX %d B: %s", len(chunk), chunk.hex())
                            if 0x17 in chunk:
                                break
                            deadline = time.monotonic() + 0.05
                        else:
                            time.sleep(0.005)

            except Exception as exc:
                logger.error("Poll error: %s", exc)
                break

            # Parse and dispatch complete frames (outside lock)
            frames, _buf = _extract_frames(_buf)
            for ctl, payload in frames:
                # Skip GG $00 — nothing waiting
                if ctl == 0x4F and (payload[:2] == b'GG' and len(payload) == 3 and payload[2] == 0):
                    continue
                try:
                    frame = _make_host_frame(ctl, payload)
                    logger.debug("RX poll frame: ctl=0x%02X payload=%s", ctl, payload.hex())
                    self._on_frame_received(frame)
                except Exception as exc:
                    logger.error("Frame dispatch: %s", exc)

            time.sleep(0.1)

        logger.debug("GG poll loop stopped")


    def send_poll(self) -> bool:
        """Send HPOLL GG poll frame."""
        if not self._check_ready():
            return False
        return self._write_raw(FRAME_POLL)

    def write_verbose(self, data: bytes) -> bool:
        """Write raw ASCII bytes in verbose mode (for ParamsUploader).

        Args:
            data: e.g. b'MYCALL OE3GAS\\r\\n'
        """
        if not self.is_connected:
            logger.warning("write_verbose: not connected")
            return False
        return self._write_raw(data)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_raw_until(self, markers: tuple, timeout: float) -> bytes:
        """Wait for marker in shared rx buffer (filled by ReaderThread).

        Does NOT clear the buffer — caller must clear it before sending
        the command (with self._rx_buf_lock: self._rx_buf.clear()).
        This ensures responses already in the buffer are not lost.
        """
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            # Check current buffer first (response may already be there)
            with self._rx_buf_lock:
                buf_copy = bytes(self._rx_buf)
            for marker in markers:
                if marker in buf_copy:
                    logger.debug("_read_raw_until: found %r in %d bytes",
                                 marker, len(buf_copy))
                    return buf_copy
            # Wait for new data from ReaderThread
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            self._rx_buf_event.wait(timeout=min(0.1, remaining))
            self._rx_buf_event.clear()

        # Timeout
        with self._rx_buf_lock:
            result = bytes(self._rx_buf)
        logger.debug("_read_raw_until: timeout after %.1fs, got %d bytes",
                     timeout, len(result))
        return result

    def _write_raw(self, data: bytes) -> bool:
        try:
            with self._write_lock:
                self._serial.write(data)
            logger.debug("TX (%d B): %s", len(data), data.hex(' '))
            return True
        except Exception as exc:
            logger.error("Serial write error: %s", exc)
            self.status_message.emit(f"Send error: {exc}")
            return False

    def _check_ready(self) -> bool:
        if not self.is_connected:
            logger.warning("send: not connected")
            return False
        if not self._in_host_mode:
            logger.warning("send: not in Host Mode")
            return False
        return True

    def _on_frame_received(self, frame: HostFrame) -> None:
        if self._in_host_mode:
            logger.debug("RX %r", frame)
        self.frame_received.emit(frame)

    def _on_raw_data(self, data: bytes) -> None:
        """Store raw bytes in shared buffer and forward to UI."""
        if self._in_host_mode:
            logger.debug("RX (%d B): %s", len(data), data.hex(' '))
        with self._rx_buf_lock:
            self._rx_buf.extend(data)
        self._rx_buf_event.set()
        if not self._in_host_mode:
            self.raw_data_received.emit(data)

    @staticmethod
    def list_ports() -> list[str]:
        if not PYSERIAL_AVAILABLE:
            return []
        return [p.device for p in serial.tools.list_ports.comports()]