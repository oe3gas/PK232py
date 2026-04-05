# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Autobaud detection and firmware version parsing.

The PK-232MBX uses autobaud detection on power-up:
  1. Send a '*' (0x2A) character — no newline.
  2. The TNC detects the baud rate and responds with the startup banner.

Startup banner example (firmware v7.1):
    AEA PK-232M Data Controller
    Copyright (C) 1986 - 1990 by
    Advanced Electronic Applications, Inc.
    Release 13-09-95
    cmd:

The date in 'Release DD-MM-YY' identifies the firmware version:
    13-09-95  →  v7.1  (AEA, September 1995)
    10-08-98  →  v7.2  (Timewave, August 1998)
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

AUTOBAUD_CHAR = b'*'

# Regex to extract the release date from the startup banner
_RELEASE_RE = re.compile(
    r'Release\s+(\d{2})-(\d{2})-(\d{2,4})', re.IGNORECASE
)

# Known firmware release dates → version strings
_KNOWN_VERSIONS: dict[str, str] = {
    "13-09-95": "7.1",
    "10-08-98": "7.2",
    "05-03-93": "7.0",
}


def parse_firmware_version(banner: str) -> str | None:
    """Extract the firmware version string from a startup banner.

    Args:
        banner: The raw text received from the TNC after power-up.

    Returns:
        A version string like ``"7.1"`` or ``"7.2"``, or ``None`` if
        the release date could not be parsed.

    Example:
        >>> parse_firmware_version("... Release 13-09-95 ...")
        '7.1'
    """
    match = _RELEASE_RE.search(banner)
    if not match:
        logger.warning("Could not find 'Release' date in banner")
        return None

    day, month, year = match.group(1), match.group(2), match.group(3)
    # Normalise 2-digit year
    if len(year) == 2:
        year = f"19{year}" if int(year) > 50 else f"20{year}"

    date_key = f"{day}-{month}-{year[2:]}"  # back to DD-MM-YY for lookup
    version = _KNOWN_VERSIONS.get(date_key)

    if version:
        logger.info("Firmware version: v%s (Release %s-%s-%s)", version, day, month, year)
    else:
        logger.warning("Unknown firmware release date: %s-%s-%s", day, month, year)

    return version


def is_cmd_prompt(text: str) -> bool:
    """Return True if the text contains the TNC command prompt 'cmd:'."""
    return "cmd:" in text.lower()
