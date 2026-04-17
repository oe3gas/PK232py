# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Macro Manager — keyboard macro system for TNC command sequences.

Macros are named text templates that expand variable placeholders and
are sent to the TNC as one or more commands.  They are stored in an
INI file and can be assigned to function keys F1-F12.

Macro file location: ~/.pk232py/macros.ini

Macro format
------------
Each macro is a name-value pair in the INI file:

    [macros]
    cq       = CQ CQ CQ DE {mycall} {mycall} K
    qsl      = TU {callsign} 73 DE {mycall} SK
    f1       = CQ CQ DE {mycall} PSE K
    f2       = QRZ? DE {mycall}

Variable substitution
---------------------
The following variables are expanded at send time:

    {mycall}    — own callsign (from config)
    {callsign}  — last worked / current contact callsign
    {time}      — current UTC time (HH:MM)
    {date}      — current UTC date (YYYY-MM-DD)
    {freq}      — current frequency (kHz, if known)
    {mode}      — current operating mode name
    {rst}       — RST sent (default 599)

Function key mapping
--------------------
Macros named f1-f12 are automatically mapped to F1-F12.
Any other name can be triggered by name via execute().
"""

from __future__ import annotations

import configparser
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MACRO_FILE = Path.home() / ".pk232py" / "macros.ini"

# Variable pattern: {variable_name}
_VAR_RE = re.compile(r'\{(\w+)\}')

# Valid function key names
_FKEY_NAMES = {f"f{i}" for i in range(1, 13)}

# Default macros (sensible CW/RTTY/Packet defaults)
_DEFAULT_MACROS = {
    "cq":    "CQ CQ CQ DE {mycall} {mycall} {mycall} K",
    "qsl":   "TU {callsign} 73 DE {mycall} SK",
    "qrz":   "QRZ? DE {mycall} K",
    "bcn":   "DE {mycall} / {mycall}",
    "f1":    "CQ CQ DE {mycall} PSE K",
    "f2":    "QRZ? DE {mycall}",
    "f3":    "TU 73 DE {mycall} SK",
}


class MacroManager:
    """Manages named macros with variable substitution.

    Macros are stored in ``~/.pk232py/macros.ini`` and loaded on
    :meth:`load`.  Changes are persisted with :meth:`save`.

    Variable substitution context is provided at execution time via
    :meth:`execute`.

    Usage::

        mm = MacroManager()
        mm.load()
        text = mm.execute('cq', mycall='OE3GAS')
        # → "CQ CQ CQ DE OE3GAS OE3GAS OE3GAS K"

        mm.set_macro('f1', 'CQ DE {mycall} K')
        mm.save()
    """

    def __init__(self, path: Path = MACRO_FILE) -> None:
        self._path   = path
        self._macros: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load macros from file.  Missing file → load defaults."""
        if not self._path.exists():
            logger.info("Macro file not found, using defaults: %s", self._path)
            self._macros = dict(_DEFAULT_MACROS)
            return

        cfg = configparser.RawConfigParser()
        cfg.read(self._path, encoding="utf-8")

        self._macros = {}
        if cfg.has_section("macros"):
            for key, value in cfg.items("macros"):
                self._macros[key.lower()] = value

        logger.info("Macros loaded: %d entries from %s",
                    len(self._macros), self._path)

    def save(self) -> None:
        """Persist current macros to file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        cfg = configparser.RawConfigParser()
        cfg["macros"] = {k: v for k, v in sorted(self._macros.items())}
        with open(self._path, "w", encoding="utf-8") as fh:
            fh.write("# PK232PY Macro file\n")
            fh.write("# Variables: {mycall} {callsign} {time} {date} "
                     "{freq} {mode} {rst}\n\n")
            cfg.write(fh)
        logger.info("Macros saved: %d entries to %s",
                    len(self._macros), self._path)

    # ------------------------------------------------------------------
    # Macro management
    # ------------------------------------------------------------------

    def set_macro(self, name: str, text: str) -> None:
        """Add or update a macro.

        Args:
            name: Macro name (case-insensitive, e.g. ``"cq"`` or ``"f1"``).
            text: Macro text with optional ``{variable}`` placeholders.
        """
        self._macros[name.lower()] = text

    def get_macro(self, name: str) -> Optional[str]:
        """Return the raw (unexpanded) macro text, or None if not found."""
        return self._macros.get(name.lower())

    def delete_macro(self, name: str) -> bool:
        """Delete a macro by name.

        Returns:
            True if the macro existed and was deleted, False otherwise.
        """
        key = name.lower()
        if key in self._macros:
            del self._macros[key]
            return True
        return False

    def list_macros(self) -> dict[str, str]:
        """Return a copy of all macros as {name: text}."""
        return dict(self._macros)

    def fkey_macros(self) -> dict[str, str]:
        """Return only the F1-F12 macros as {name: text}."""
        return {k: v for k, v in self._macros.items() if k in _FKEY_NAMES}

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(
        self,
        name: str,
        mycall:   str = "",
        callsign: str = "",
        freq:     Optional[float] = None,
        mode:     str = "",
        rst:      str = "599",
    ) -> Optional[str]:
        """Expand and return the macro text for a given name.

        Variable substitution is performed using the provided context.
        Unknown variables are left as-is (not replaced).

        Args:
            name:     Macro name (case-insensitive).
            mycall:   Own callsign for ``{mycall}``.
            callsign: Contact callsign for ``{callsign}``.
            freq:     Frequency in kHz for ``{freq}``.
            mode:     Operating mode for ``{mode}``.
            rst:      RST sent for ``{rst}``.

        Returns:
            Expanded macro text, or ``None`` if macro not found.
        """
        template = self._macros.get(name.lower())
        if template is None:
            logger.warning("Macro not found: %r", name)
            return None

        now = datetime.now(timezone.utc)
        context = {
            "mycall":   mycall.upper(),
            "callsign": callsign.upper(),
            "time":     now.strftime("%H:%M"),
            "date":     now.strftime("%Y-%m-%d"),
            "freq":     f"{freq:.1f}" if freq is not None else "",
            "mode":     mode,
            "rst":      rst,
        }

        def replace(m: re.Match) -> str:
            var = m.group(1).lower()
            return context.get(var, m.group(0))   # keep original if unknown

        result = _VAR_RE.sub(replace, template)
        logger.debug("Macro %r → %r", name, result)
        return result

    def execute_fkey(
        self,
        fkey_num: int,
        **kwargs,
    ) -> Optional[str]:
        """Execute the macro assigned to a function key F1-F12.

        Args:
            fkey_num: Function key number 1-12.
            **kwargs: Context variables passed to :meth:`execute`.

        Returns:
            Expanded macro text, or ``None`` if no macro is assigned.
        """
        if not 1 <= fkey_num <= 12:
            logger.warning("Invalid function key number: %d", fkey_num)
            return None
        return self.execute(f"f{fkey_num}", **kwargs)

    def variables_in(self, name: str) -> list[str]:
        """Return a list of variable names used in a macro.

        Args:
            name: Macro name.

        Returns:
            List of variable names (without braces), or empty list.
        """
        template = self._macros.get(name.lower(), "")
        return [m.group(1).lower() for m in _VAR_RE.finditer(template)]