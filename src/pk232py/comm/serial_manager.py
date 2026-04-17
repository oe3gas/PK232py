# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Serial port manager for the AEA PK-232 / PK-232MBX.

Responsibilities
----------------
  1. Open / close the serial port (via AutobaudDetector or fixed baud rate).
  2. Manage the verbose-mode → Host Mode initialisation sequence.
  3. Send frames (thread-safe write).
  4. Receive frames in a background reader thread (serial.read → FrameParser).
  5. Deliver decoded frames to the UI via Qt signals (thread-safe).

Threading model
---------------
  ┌─────────────────┐   Qt signal/slot   ┌──────────────────────────┐
  │  Qt UI / Modes  │ ←──────────────── │  SerialManager           │
  │  (Main Thread)  │                    │  (Main Thread)           │
  └─────────────────┘                    └──────────────────────────┘
                                                    ↑ emit() [thread-safe]
                                         ┌──────────────────────────┐
                                         │  _ReaderThread (daemon)  │
                                         │  serial.read(64)         │
                                         │  → FrameParser           │
                                         │  → frame_received.emit() │
                                         └──────────────────────────┘

Qt signal emit() from a non-main thread is safe: Qt queues the call and
delivers it to connected slots in the main thread via the event loop.

Host Mode initialisation (TRM Section 4.1.3)
--------------------------------------------
The TNC starts in verbose/terminal mode.  Before Host Mode can be used
the following ASCII commands must be sent:

  AWLEN 8      — 8-bit word length
  PARITY 0     — no parity
  8BITCONV ON  — 8-bit transparent conversion
  RESTART      — apply AWLEN/PARITY (TNC resets, re-sends banner)
  HOST Y       — activate Host Mode

After HOST Y the TNC switches to binary Host Mode framing (SOH/CTL/ETB).
To verify Host Mode is active, send a GG poll and wait for the ACK.

Leaving Host Mode (TRM Section 4.1.4)
--------------------------------------
Send the binary frame:  SOH $4F 'H' 'O' 'N' ETB
(plain ASCII "HOST OFF\\r" would NOT be understood in Host Mode.)
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
    HOSTMODE_INIT_CMDS,
    FRAME_POLL,
    FRAME_RECOVERY,
    FRAME_HOST_OFF,
    CTL_TX_DATA_BASE,
)
from .frame import (
    HostFrame,
    FrameKind,
    FrameParser,
    build_command,
    build_ch_cmd,
    build_data,
)

logger = logging.getLogger(__name__)

# Delays used during initialisation (seconds)
_CMD_DELAY     = 0.05   # pause between verbose-mode commands
_RESTART_DELAY = 1.5    # wait after RESTART for TNC banner
_HOSTMODE_DELAY = 0.3   # wait after HOST Y before sending first poll
_POLL_TIMEOUT   = 2.0   # seconds to wait for GG poll ACK


# ---------------------------------------------------------------------------
# Background reader thread
# ---------------------------------------------------------------------------

class _ReaderThread(threading.Thread):
    """Reads raw bytes from the serial port and feeds them to FrameParser.

    Runs as a daemon thread — terminated automatically when the main
    process exits.  Delivers complete HostFrames via *frame_callback*.

    Args:
        port:           Open pyserial Serial instance.
        frame_callback: Called with each decoded HostFrame.
    """

    def __init__(
        self,
        port: "serial.Serial",
        frame_callback,
    ) -> None:
        super().__init__(daemon=True, name="PK232-Reader")
        self._port     = port
        self._callback = frame_callback
        self._stop_event = threading.Event()
        self._parser     = FrameParser(self._on_frame)

    def stop(self) -> None:
        """Signal the thread to stop on its next iteration."""
        self._stop_event.set()

    def run(self) -> None:
        logger.debug("ReaderThread started")
        while not self._stop_event.is_set():
            try:
                raw = self._port.read(64)   # non-blocking due to port timeout
                if raw:
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
        """Discard any partial parser state (call after port re-open)."""
        self._parser.reset()


# ---------------------------------------------------------------------------
# SerialManager
# ---------------------------------------------------------------------------

class SerialManager(QObject):
    """Manages the serial connection to the PK-232 / PK-232MBX.

    Qt Signals
    ----------
    frame_received(HostFrame)
        Emitted for every complete Host Mode frame received from the TNC.
        Connected slots receive the frame in the main (UI) thread.

    connection_changed(bool)
        True  = serial port opened successfully.
        False = port closed / disconnected.

    host_mode_changed(bool)
        True  = Host Mode is now active.
        False = Host Mode has been left (or was never entered).

    status_message(str)
        Human-readable status string for the status bar.

    Typical usage::

        mgr = SerialManager()
        mgr.frame_received.connect(on_frame)
        mgr.status_message.connect(status_bar.showMessage)

        mgr.connect_port("/dev/ttyUSB0", baudrate=9600)
        if mgr.enter_host_mode():
            mgr.send_command(b'ML', b'OE3GAS')   # MYCALL
            mgr.send_command(b'PA')               # PACKET
    """

    # Qt signals
    frame_received    = pyqtSignal(object)   # HostFrame
    connection_changed = pyqtSignal(bool)
    host_mode_changed  = pyqtSignal(bool)
    status_message     = pyqtSignal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._serial:   Optional["serial.Serial"] = None
        self._reader:   Optional[_ReaderThread]   = None
        self._in_host_mode = False
        self._write_lock   = threading.Lock()

    # ------------------------------------------------------------------
    # Port management
    # ------------------------------------------------------------------

    def connect_port(
        self,
        port_name: str,
        baudrate:  int  = SerialDefaults.BAUDRATE,
        rtscts:    bool = SerialDefaults.RTSCTS,
    ) -> bool:
        """Open the serial port and start the reader thread.

        Does NOT enter Host Mode — call :meth:`enter_host_mode` separately.

        Args:
            port_name: e.g. ``'COM3'`` or ``'/dev/ttyUSB0'``.
            baudrate:  Baud rate (default 9600).
            rtscts:    Hardware RTS/CTS handshake (recommended: True).

        Returns:
            True on success, False on failure.
        """
        if not PYSERIAL_AVAILABLE:
            self.status_message.emit("Error: pyserial not installed")
            return False

        if self.is_connected:
            logger.warning("Port already open — disconnect first")
            return False

        try:
            self._serial = serial.Serial(
                port     = port_name,
                baudrate = baudrate,
                bytesize = SerialDefaults.BYTESIZE,
                parity   = SerialDefaults.PARITY,
                stopbits = SerialDefaults.STOPBITS,
                timeout  = SerialDefaults.TIMEOUT,
                xonxoff  = SerialDefaults.XONXOFF,
                rtscts   = rtscts,
            )
            logger.info("Port %s opened at %d baud", port_name, baudrate)
            self.status_message.emit(f"Connected: {port_name} @ {baudrate} Bd")

            self._reader = _ReaderThread(self._serial, self._on_frame_received)
            self._reader.start()
            self.connection_changed.emit(True)
            return True

        except Exception as exc:
            logger.error("Cannot open %s: %s", port_name, exc)
            self.status_message.emit(f"Connection error: {exc}")
            self._serial = None
            return False

    def disconnect_port(self) -> None:
        """Leave Host Mode (if active), stop reader thread, close port."""
        if self._in_host_mode:
            self.exit_host_mode()

        if self._reader:
            self._reader.stop()
            self._reader.join(timeout=2.0)
            self._reader = None

        if self._serial and self._serial.is_open:
            self._serial.close()
            logger.info("Serial port closed")

        self._serial       = None
        self._in_host_mode = False
        self.connection_changed.emit(False)
        self.status_message.emit("Disconnected")

    @property
    def is_connected(self) -> bool:
        """True if the serial port is open."""
        return self._serial is not None and self._serial.is_open

    @property
    def is_host_mode(self) -> bool:
        """True if Host Mode is currently active."""
        return self._in_host_mode

    # ------------------------------------------------------------------
    # Host Mode control
    # ------------------------------------------------------------------

    def enter_host_mode(self, verify: bool = True) -> bool:
        """Send the verbose-mode init sequence and activate Host Mode.

        Sequence (TRM Section 4.1.3):
          1. Send AWLEN 8, PARITY 0, 8BITCONV ON as ASCII commands.
          2. Send RESTART — TNC resets; wait for banner.
          3. Send HOST Y — TNC switches to binary Host Mode.
          4. Optionally verify with a GG poll.

        Args:
            verify: If True, send a GG poll and wait for the ACK to
                    confirm Host Mode is active (recommended).

        Returns:
            True if Host Mode was successfully entered.
        """
        if not self.is_connected:
            logger.error("enter_host_mode: no port connected")
            return False
        if self._in_host_mode:
            logger.warning("Host Mode already active")
            return True

        logger.info("Entering Host Mode...")
        try:
            for cmd in HOSTMODE_INIT_CMDS:
                self._write_raw(cmd)
                if cmd == b"RESTART\r":
                    # Wait for TNC to reboot and re-send banner
                    time.sleep(_RESTART_DELAY)
                else:
                    time.sleep(_CMD_DELAY)

            # Give TNC time to switch modes
            time.sleep(_HOSTMODE_DELAY)
            self._in_host_mode = True
            self.host_mode_changed.emit(True)
            self.status_message.emit("Host Mode active")
            logger.info("Host Mode activated")

            if verify:
                return self._verify_host_mode()
            return True

        except Exception as exc:
            logger.error("enter_host_mode failed: %s", exc)
            self.status_message.emit(f"Host Mode error: {exc}")
            self._in_host_mode = False
            return False

    def exit_host_mode(self) -> None:
        """Send the HOST OFF frame and return TNC to verbose mode.

        TRM Section 4.1.4:  SOH $4F 'H' 'O' 'N' ETB
        Note: plain ASCII "HOST OFF\\r" is NOT valid in Host Mode —
        the binary frame must be used.
        """
        if not self.is_connected or not self._in_host_mode:
            return
        try:
            self._write_raw(FRAME_HOST_OFF)
            time.sleep(0.1)
            self._in_host_mode = False
            self.host_mode_changed.emit(False)
            self.status_message.emit("Host Mode off")
            logger.info("Host Mode deactivated")
        except Exception as exc:
            logger.error("exit_host_mode: %s", exc)

    def recovery(self) -> None:
        """Send the double-SOH recovery frame and then exit Host Mode.

        Use when the TNC appears to be stuck.
        TRM Section 4.1.6:  SOH SOH $4F 'G' 'G' ETB
        """
        if not self.is_connected:
            return
        try:
            self._write_raw(FRAME_RECOVERY)
            time.sleep(0.2)
            self.exit_host_mode()
            self.status_message.emit("Recovery sent")
            logger.info("Host Mode recovery frame sent")
        except Exception as exc:
            logger.error("recovery: %s", exc)

    def _verify_host_mode(self) -> bool:
        """Send a GG poll and wait up to _POLL_TIMEOUT s for the ACK.

        Returns True if the TNC acknowledged the poll.
        """
        logger.debug("Verifying Host Mode with GG poll...")
        ack_event = threading.Event()

        def _check(frame: HostFrame) -> None:
            if frame.is_poll_ok:
                ack_event.set()

        # Temporarily hook a one-shot check into the callback chain.
        # We re-use the existing reader thread; _on_frame_received already
        # calls frame_received.emit(), so we add our check inline here by
        # connecting to the signal momentarily.
        self.frame_received.connect(_check)
        try:
            self._write_raw(FRAME_POLL)
            got_ack = ack_event.wait(timeout=_POLL_TIMEOUT)
        finally:
            self.frame_received.disconnect(_check)

        if got_ack:
            logger.info("Host Mode verified (GG poll ACK received)")
        else:
            logger.warning(
                "Host Mode verification timed out — TNC may not be in Host Mode"
            )
        return got_ack

    # ------------------------------------------------------------------
    # Sending frames
    # ------------------------------------------------------------------

    def send_command(self, mnemonic: bytes, args: bytes = b"") -> bool:
        """Send a Host Mode command frame (CTL = $4F).

        Args:
            mnemonic: 2-byte ASCII mnemonic, e.g. ``b'ML'``.
            args:     Optional argument bytes, e.g. ``b'OE3GAS'``.

        Returns:
            True if the bytes were written to the port.

        Example::

            mgr.send_command(b'ML', b'OE3GAS')  # MYCALL OE3GAS
            mgr.send_command(b'HP', b'Y')        # HPOLL ON
            mgr.send_command(b'PA')              # PACKET mode
        """
        if not self._check_ready():
            return False
        return self._write_raw(build_command(mnemonic, args))

    def send_channel_command(
        self, channel: int, mnemonic: bytes, args: bytes = b""
    ) -> bool:
        """Send a channel-specific command frame (CTL = $4x).

        Used for CONNECT and DISCONNECT (TRM Section 4.2.3).

        Args:
            channel:  Packet channel 1-9.
            mnemonic: e.g. ``b'CO'`` or ``b'DI'``.
            args:     e.g. destination callsign bytes.
        """
        if not self._check_ready():
            return False
        return self._write_raw(build_ch_cmd(channel, mnemonic, args))

    def send_data(self, data: bytes, channel: int = 0) -> bool:
        """Send a data frame to the TNC (CTL = $2x).

        The host must wait for a data-ACK ($5F response) before sending
        the next data block (TRM Section 4.4).

        Args:
            data:    Raw bytes to transmit.
            channel: Packet channel 0-9.  Use 0 for non-Packet modes.
        """
        if not self._check_ready():
            return False
        return self._write_raw(build_data(channel, data))

    def send_poll(self) -> bool:
        """Send the HPOLL data-poll frame (SOH $4F 'G' 'G' ETB).

        Only needed when HPOLL is ON.
        """
        if not self._check_ready():
            return False
        return self._write_raw(FRAME_POLL)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write_raw(self, data: bytes) -> bool:
        """Thread-safe write to the serial port."""
        try:
            with self._write_lock:
                self._serial.write(data)
            return True
        except Exception as exc:
            logger.error("Serial write error: %s", exc)
            self.status_message.emit(f"Send error: {exc}")
            return False

    def _check_ready(self) -> bool:
        """Return True if port is open AND Host Mode is active."""
        if not self.is_connected:
            logger.warning("send attempted with no port open")
            return False
        if not self._in_host_mode:
            logger.warning("send attempted outside Host Mode")
            return False
        return True

    def _on_frame_received(self, frame: HostFrame) -> None:
        """Called by _ReaderThread for each decoded frame."""
        logger.debug("RX %r", frame)
        self.frame_received.emit(frame)   # delivers to main thread via Qt

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def list_ports() -> list[str]:
        """Return a list of available serial port names.

        Suitable for populating a port-selection ComboBox in the UI.

        Returns:
            List of port name strings, e.g.
            ``['COM1', 'COM3']`` on Windows or
            ``['/dev/ttyUSB0', '/dev/ttyS0']`` on Linux.
        """
        if not PYSERIAL_AVAILABLE:
            return []
        return [p.device for p in serial.tools.list_ports.comports()]