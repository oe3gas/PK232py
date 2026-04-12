# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Autobaud detection and firmware version parsing.

Background
----------
The PK-232MBX has two startup scenarios:

Scenario A — TNC baud rate is UNKNOWN (autobaud active)
    This happens on first power-up with no battery backup, or when
    AUTOBAUD ON is set, or after the battery jumper was removed.
    The TNC waits silently until it receives a '*' character, then
    locks its baud rate to match and prints the startup banner.

Scenario B — TNC baud rate is ALREADY SET (battery-backed RAM)
    The TNC starts immediately at the stored TBAUD rate and either:
      - sends the startup banner right away, or
      - sits at the 'cmd:' prompt waiting for commands.
    In this case a '*' may not produce a banner at all.

Detection sequence (implemented in AutobaudDetector)
-----------------------------------------------------
The sequence tries baud rates from BAUD_RATES (fastest first) until
the TNC responds.  For each candidate rate:

  1. Open serial port at this baud rate (8N1).
  2. Send '*' — triggers autobaud if active, harmless otherwise.
  3. Wait BANNER_TIMEOUT seconds for any response.
  4a. Response received and contains banner/prompt -> success.
  4b. No response -> send '\r' (newline).
       Wait PROMPT_TIMEOUT seconds.
       Response received -> success (TNC was already at this rate).
       No response -> close port, try next baud rate.

Startup banner example (firmware v7.1, AEA):
    PK-232M is using default values.
    AEA PK-232M Data Controller
    Copyright (C) 1986-1990 by
    Advanced Electronic Applications, Inc.
    Release 13.09.95
    cmd:

Note: The release date uses DOTS as separators (DD.MM.YY), as shown
in the PK-232MBX manual (STABO edition, p. 12).  Firmware versions:
    Release 13.09.95  ->  v7.1  (AEA,      September 1995)
    Release 10.08.98  ->  v7.2  (Timewave, August    1998)
"""

from __future__ import annotations

import logging
import re
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AUTOBAUD_CHAR = b'*'
NEWLINE       = b'\r'

# Baud rates tried in order (fastest first)
BAUD_RATES: list[int] = [9600, 4800, 2400, 1200, 600, 300, 110]

# Timeouts (seconds)
BANNER_TIMEOUT: float = 2.0   # wait after '*' for banner
PROMPT_TIMEOUT: float = 1.0   # wait after '\r' for cmd: prompt

# ---------------------------------------------------------------------------
# Firmware version table
# Key format: "DD.MM.YY" (as printed on the TNC banner — dots, 2-digit year)
# ---------------------------------------------------------------------------
_KNOWN_VERSIONS: dict[str, str] = {
    "13.09.95": "7.1",   # AEA,      September 1995  (confirmed: STABO manual)
    "10.08.98": "7.2",   # Timewave, August    1998  (confirmed: Timewave docs)
}

# Regex: matches "Release DD.MM.YY" or "Release DD.MM.YYYY"
# Dots are the canonical separator per the PK-232MBX manual.
# Dashes/slashes accepted as fallback for robustness.
_RELEASE_RE = re.compile(
    r'Release\s+(\d{2})[.\-/](\d{2})[.\-/](\d{2,4})',
    re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

class FirmwareInfo:
    """Result of a successful autobaud / banner parse.

    Attributes:
        baud_rate:    The serial baud rate at which the TNC responded.
        version:      Known version string e.g. '7.1', or None if the
                      release date is not in the known-versions table.
        release_date: Raw release date as printed in the banner e.g.
                      '13.09.95', or None if no Release line was found.
        had_banner:   True if a full startup banner was received; False
                      if only a cmd: prompt was seen (TNC already running).
        raw_banner:   Full text received from the TNC during detection.
    """

    def __init__(
        self,
        baud_rate: int,
        version: Optional[str],
        release_date: Optional[str],
        had_banner: bool,
        raw_banner: str,
    ) -> None:
        self.baud_rate    = baud_rate
        self.version      = version
        self.release_date = release_date
        self.had_banner   = had_banner
        self.raw_banner   = raw_banner

    def __repr__(self) -> str:
        return (
            f"FirmwareInfo(baud={self.baud_rate}, version={self.version!r}, "
            f"release={self.release_date!r}, had_banner={self.had_banner})"
        )


# ---------------------------------------------------------------------------
# Banner / prompt parsing
# ---------------------------------------------------------------------------

def parse_firmware_version(banner: str) -> tuple[Optional[str], Optional[str]]:
    """Extract firmware version and release date from a startup banner.

    Args:
        banner: Raw text received from the TNC after power-up.

    Returns:
        Tuple (version, release_date) where:
          - version is e.g. '7.1', or None if date not in known table.
          - release_date is the raw 'DD.MM.YY' string from the banner,
            or None if no Release line was found at all.

    Examples:
        >>> parse_firmware_version("... Release 13.09.95 ...")
        ('7.1', '13.09.95')
        >>> parse_firmware_version("... Release 01.01.97 ...")
        (None, '01.01.97')
        >>> parse_firmware_version("cmd:")
        (None, None)
    """
    match = _RELEASE_RE.search(banner)
    if not match:
        logger.debug("No 'Release' date found in banner text")
        return None, None

    day, month, year_raw = match.group(1), match.group(2), match.group(3)

    # Canonical lookup key uses 2-digit year (as printed on TNC)
    year_2d  = year_raw[-2:]
    date_key = f"{day}.{month}.{year_2d}"

    version = _KNOWN_VERSIONS.get(date_key)
    if version:
        logger.info(
            "Firmware version: v%s  (Release %s.%s.%s)",
            version, day, month, year_raw
        )
    else:
        logger.warning(
            "Unrecognised firmware release date: %s.%s.%s "
            "(not in known-versions table)",
            day, month, year_raw
        )

    return version, date_key


def is_cmd_prompt(text: str) -> bool:
    """Return True if text contains the TNC command prompt 'cmd:'."""
    return "cmd:" in text.lower()


def has_banner(text: str) -> bool:
    """Return True if text looks like (part of) a startup banner."""
    keywords = ("release", "copyright", "data controller", "advanced electronic")
    lower = text.lower()
    return any(kw in lower for kw in keywords)


def is_useful_response(text: str) -> bool:
    """Return True if the TNC sent anything meaningful (banner OR prompt)."""
    return is_cmd_prompt(text) or has_banner(text)


# ---------------------------------------------------------------------------
# Autobaud detector
# ---------------------------------------------------------------------------

class AutobaudDetector:
    """Detects the active baud rate of the PK-232MBX and parses firmware info.

    Transport-agnostic: serial I/O is provided via three callables so that
    pyserial, asyncio, or test mocks can all be used without changes here.

    Args:
        open_port:  open_port(baud: int) -> None
                    Open the serial port at the given baud rate, 8N1.
        close_port: close_port() -> None
                    Close the currently open port.
        write:      write(data: bytes) -> None
                    Write bytes to the open port.
        read_until: read_until(timeout: float) -> str
                    Read for up to timeout seconds; return decoded string.

    Example (pyserial)::

        import serial, time

        ser = None

        def open_port(baud):
            global ser
            ser = serial.Serial('/dev/ttyUSB0', baudrate=baud,
                                bytesize=8, parity='N', stopbits=1,
                                timeout=0.1)

        def close_port():
            if ser and ser.is_open:
                ser.close()

        def write(data):
            ser.write(data)

        def read_until(timeout):
            deadline = time.monotonic() + timeout
            buf = bytearray()
            while time.monotonic() < deadline:
                buf.extend(ser.read(ser.in_waiting or 1))
            return buf.decode('ascii', errors='replace')

        detector = AutobaudDetector(open_port, close_port, write, read_until)
        info = detector.detect()
        if info:
            print(f"TNC ready at {info.baud_rate} baud, firmware v{info.version}")
    """

    def __init__(
        self,
        open_port:  Callable[[int], None],
        close_port: Callable[[], None],
        write:      Callable[[bytes], None],
        read_until: Callable[[float], str],
    ) -> None:
        self._open  = open_port
        self._close = close_port
        self._write = write
        self._read  = read_until

    def detect(
        self,
        baud_rates: list[int] = BAUD_RATES,
    ) -> Optional[FirmwareInfo]:
        """Try each baud rate in order until the TNC responds.

        Returns:
            FirmwareInfo on success, or None if no baud rate worked.
        """
        for baud in baud_rates:
            logger.info("Trying %d baud ...", baud)
            info = self._try_baud(baud)
            if info is not None:
                return info
        logger.error("Autobaud failed: TNC did not respond on any baud rate")
        return None

    def _try_baud(self, baud: int) -> Optional[FirmwareInfo]:
        """Run the full detection sequence for one baud rate.

        Steps
        -----
        1. Open port at baud.
        2. Send '*'  — triggers autobaud if active; harmless otherwise.
        3. Wait BANNER_TIMEOUT s.
           Got useful response -> parse & return FirmwareInfo.
        4. Send CR  — wakes a TNC that is already at cmd: prompt.
        5. Wait PROMPT_TIMEOUT s.
           Got useful response -> parse & return FirmwareInfo.
        6. Close port, return None (caller tries next baud rate).
        """
        try:
            self._open(baud)
        except Exception as exc:
            logger.warning("Could not open port at %d baud: %s", baud, exc)
            return None

        try:
            # Step 2
            self._write(AUTOBAUD_CHAR)
            logger.debug("[%d] Sent '*'", baud)

            # Step 3
            response = self._read(BANNER_TIMEOUT)
            if response and is_useful_response(response):
                logger.info("[%d] TNC responded after '*'", baud)
                return self._build_result(baud, response)

            # Step 4
            self._write(NEWLINE)
            logger.debug("[%d] No response to '*'; sent CR", baud)

            # Step 5
            response2 = self._read(PROMPT_TIMEOUT)
            combined  = response + response2
            if combined and is_useful_response(combined):
                logger.info("[%d] TNC responded after CR", baud)
                return self._build_result(baud, combined)

            logger.debug("[%d] No useful response, trying next baud rate", baud)
            return None

        finally:
            # Step 6 — always close before trying next rate
            self._close()

    @staticmethod
    def _build_result(baud: int, raw: str) -> FirmwareInfo:
        version, release_date = parse_firmware_version(raw)
        had_banner = has_banner(raw)
        return FirmwareInfo(
            baud_rate=baud,
            version=version,
            release_date=release_date,
            had_banner=had_banner,
            raw_banner=raw,
        )