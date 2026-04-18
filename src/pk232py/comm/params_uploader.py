# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""TNC Parameter Uploader — sends stored parameters in verbose mode.

Reads parameters from AppConfig (which is backed by pk232py.ini) and
sends them as ASCII verbose-mode commands to the TNC after initialisation.

All commands are sent as:  COMMAND value\\r\\n
and followed by a short delay to allow the TNC to process each one.

Parameter groups sent:
  1. General / identity  — MYCALL, MYPTCALL, MYSELCAL
  2. HF Packet           — PACLEN, TXDELAY, FRACK, RETRY, MAXFRAME, …
  3. PACTOR              — ARQTMO, PTDOWN, PTUP, PT200, …
  4. Misc                — CANLINE, SENDPAC, COMMAND char, …

Usage::

    uploader = ParamsUploader(serial_manager, config_manager.app)
    uploader.upload()   # blocking — call from background thread only
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pk232py.comm.serial_manager import SerialManager
    from pk232py.config import AppConfig

logger = logging.getLogger(__name__)

# Delay between verbose-mode parameter commands (seconds)
_PARAM_DELAY = 0.12


class ParamsUploader:
    """Sends TNC parameters as verbose-mode ASCII commands.

    Args:
        serial:  SerialManager instance (must be connected, verbose mode).
        config:  AppConfig with all parameter dataclasses.

    Call :meth:`upload` from a background thread — it blocks for
    the duration of the upload (several seconds for a full set).
    """

    def __init__(
        self,
        serial: "SerialManager",
        config: "AppConfig",
    ) -> None:
        self._serial = serial
        self._config = config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upload(self) -> int:
        """Upload all parameters to the TNC in verbose mode.

        Returns:
            Number of commands sent.
        """
        commands = self._build_commands()
        logger.info("ParamsUploader: uploading %d commands", len(commands))
        sent = 0
        for cmd in commands:
            logger.debug("Verbose param: %r", cmd)
            self._serial.write_verbose(cmd)
            time.sleep(_PARAM_DELAY)
            sent += 1
        logger.info("ParamsUploader: upload complete (%d commands)", sent)
        return sent

    # ------------------------------------------------------------------
    # Build command list
    # ------------------------------------------------------------------

    def _build_commands(self) -> list[bytes]:
        """Build the full list of verbose-mode parameter commands."""
        cmds: list[bytes] = []
        tnc = self._config.tnc
        hf  = self._config.hf_packet
        pt  = self._config.pactor

        # ── Identity ──────────────────────────────────────────────────
        if hf.mycall and hf.mycall != "NOCALL":
            cmds.append(self._cmd("MYCALL", hf.mycall.upper()))

        if pt.myptcall and pt.myptcall != "NOCALL":
            cmds.append(self._cmd("MYPTCALL", pt.myptcall.upper()))

        # ── HF Packet ─────────────────────────────────────────────────
        cmds += [
            self._cmd("PACLEN",   str(hf.paclen)),
            self._cmd("TXDELAY",  str(hf.txdelay)),
            self._cmd("MAXFRAME", str(hf.maxframe)),
            self._cmd("FRACK",    str(hf.frack)),
            self._cmd("RETRY",    str(hf.retry)),
            self._cmd("PERSIST",  str(hf.persist)),
            self._cmd("SLOTTIME", str(hf.slottime)),
            self._cmd("DWAIT",    str(hf.dwait)),
            self._cmd("CHECK",    str(hf.check)),
            self._cmd("MONITOR",  str(hf.monitor)),
        ]

        # Boolean flags
        cmds += [
            self._bool("AX25L2V2",  hf.ax25l2v2),
            self._bool("HEADERLN",  hf.headerln),
            self._bool("CONSTAMP",  hf.constamp),
            self._bool("DAGSTAMP",  hf.dagstamp),
            self._bool("ILFPACK",   hf.ilfpack),
            self._bool("AERPACK",   hf.aerpack),
            self._bool("ALFPACK",   hf.alfpack),
            self._bool("MRPT",      hf.mrpt),
            self._bool("PPERSIST",  hf.ppersist),
            self._bool("XMITOK",    hf.xmitok),
        ]

        # Message params
        if hf.mycall:
            cmds.append(self._cmd("MYCALL",  hf.mycall.upper()))
        if hf.unproto:
            cmds.append(self._cmd("UNPROTO", hf.unproto))
        if hf.btext:
            cmds.append(self._cmd("BTEXT",   hf.btext))
        if hf.ctext:
            cmds.append(self._cmd("CTEXT",   hf.ctext))

        # ── PACTOR ────────────────────────────────────────────────────
        cmds += [
            self._cmd("ARQTMO",  str(pt.arqtmo)),
            self._cmd("ADELAY",  str(pt.adelay)),
            self._cmd("PTDOWN",  str(pt.ptdown)),
            self._cmd("PTUP",    str(pt.ptup)),
            self._cmd("PTHUFF",  str(pt.pthuff)),
            self._cmd("PTSUM",   str(pt.ptsum)),
            self._cmd("PTTRIES", str(pt.pttries)),
            self._cmd("PTSEND",  f"{pt.ptsend:.1f}"),
            self._bool("PT200",   pt.pt200),
            self._bool("PTROUND", pt.ptround),
        ]

        # ── UTC time ──────────────────────────────────────────────────
        if tnc.utc_tnc_time:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            cmds.append(self._cmd(
                "DAYTIME",
                now.strftime("%H:%M:%S %d/%m/%y"),
            ))

        return cmds

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _cmd(name: str, value: str) -> bytes:
        """Build a verbose-mode command: b'NAME value\\r\\n'"""
        return f"{name} {value}\r\n".encode('ascii', errors='replace')

    @staticmethod
    def _bool(name: str, value: bool) -> bytes:
        """Build a verbose-mode boolean command: b'NAME ON\\r\\n'"""
        return f"{name} {'ON' if value else 'OFF'}\r\n".encode('ascii')