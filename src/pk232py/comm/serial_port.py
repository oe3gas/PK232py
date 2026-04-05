# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Serial port management for PK-232 / PK-232MBX.

The PK-232MBX communicates at 1200 baud, 7E1 (7 data bits, even parity,
1 stop bit) for firmware v7.x in terminal/command mode.
After switching to Host Mode, 8N1 is used at the configured TBaud rate.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable

import serial
import serial.tools.list_ports

logger = logging.getLogger(__name__)

# Default serial parameters for PK-232MBX firmware v7.x (terminal mode)
DEFAULT_BAUD = 1200
DEFAULT_BYTESIZE = serial.SEVENBITS
DEFAULT_PARITY = serial.PARITY_EVEN
DEFAULT_STOPBITS = serial.STOPBITS_ONE
DEFAULT_TIMEOUT = 0.1  # seconds


def list_ports() -> list[str]:
    """Return a list of available serial port names on this system."""
    return sorted(p.device for p in serial.tools.list_ports.comports())


class SerialPort:
    """Thread-safe wrapper around pyserial for TNC communication.

    Spawns a background reader thread that calls ``data_callback``
    whenever bytes arrive from the TNC.

    Args:
        data_callback: Called with ``bytes`` from the TNC (reader thread context).
    """

    def __init__(self, data_callback: Callable[[bytes], None]) -> None:
        self._port: serial.Serial | None = None
        self._data_callback = data_callback
        self._reader_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def is_open(self) -> bool:
        """True if the serial port is currently open."""
        return self._port is not None and self._port.is_open

    def open(
        self,
        port: str,
        baudrate: int = DEFAULT_BAUD,
        bytesize: int = DEFAULT_BYTESIZE,
        parity: str = DEFAULT_PARITY,
        stopbits: float = DEFAULT_STOPBITS,
    ) -> None:
        """Open the serial port and start the reader thread.

        Args:
            port: Port name, e.g. ``"COM3"`` or ``"/dev/ttyUSB0"``.
            baudrate: Baud rate (default 1200 for PK-232MBX terminal mode).
            bytesize: Data bits (default 7).
            parity: Parity (default 'E' = even).
            stopbits: Stop bits (default 1).

        Raises:
            serial.SerialException: If the port cannot be opened.
        """
        if self.is_open:
            logger.warning("Port already open — closing first")
            self.close()

        logger.info(
            "Opening %s @ %d baud %d%s%s",
            port, baudrate, bytesize, parity, stopbits,
        )
        self._port = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=bytesize,
            parity=parity,
            stopbits=stopbits,
            timeout=DEFAULT_TIMEOUT,
        )
        self._stop_event.clear()
        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            name="SerialReader",
            daemon=True,
        )
        self._reader_thread.start()
        logger.info("Serial port %s opened", port)

    def close(self) -> None:
        """Close the serial port and stop the reader thread."""
        self._stop_event.set()
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=2.0)
            self._reader_thread = None
        if self._port is not None and self._port.is_open:
            self._port.close()
            logger.info("Serial port closed")
        self._port = None

    def write(self, data: bytes) -> None:
        """Send bytes to the TNC.

        Args:
            data: Raw bytes to transmit.

        Raises:
            RuntimeError: If the port is not open.
        """
        if not self.is_open:
            raise RuntimeError("Serial port is not open")
        with self._lock:
            self._port.write(data)  # type: ignore[union-attr]

    def reconfigure(
        self,
        baudrate: int,
        bytesize: int = serial.EIGHTBITS,
        parity: str = serial.PARITY_NONE,
        stopbits: float = serial.STOPBITS_ONE,
    ) -> None:
        """Change serial parameters on the fly (e.g. after Host Mode activation).

        Args:
            baudrate: New baud rate.
            bytesize: New data bits (default 8 for Host Mode).
            parity: New parity (default none for Host Mode).
            stopbits: New stop bits.
        """
        if not self.is_open:
            raise RuntimeError("Serial port is not open")
        with self._lock:
            self._port.baudrate = baudrate  # type: ignore[union-attr]
            self._port.bytesize = bytesize  # type: ignore[union-attr]
            self._port.parity = parity      # type: ignore[union-attr]
            self._port.stopbits = stopbits  # type: ignore[union-attr]
        logger.info("Serial reconfigured: %d baud %d%s%s", baudrate, bytesize, parity, stopbits)

    # ------------------------------------------------------------------
    # Background reader
    # ------------------------------------------------------------------

    def _reader_loop(self) -> None:
        """Background thread: continuously read from the serial port."""
        logger.debug("Reader thread started")
        while not self._stop_event.is_set():
            try:
                if self._port and self._port.in_waiting:
                    data = self._port.read(self._port.in_waiting)
                    if data:
                        self._data_callback(data)
                else:
                    # Short sleep to avoid busy-waiting
                    self._stop_event.wait(timeout=0.01)
            except serial.SerialException as exc:
                logger.error("Serial read error: %s", exc)
                break
        logger.debug("Reader thread stopped")
