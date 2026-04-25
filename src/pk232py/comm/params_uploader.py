# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  Ã¢â‚¬â€  GPL v2
"""TNC Parameter Uploader Ã¢â‚¬â€ sends stored parameters in verbose mode.

Reads parameters from AppConfig (which is backed by pk232py.ini) and
sends them as ASCII verbose-mode commands to the TNC after initialisation.

All commands are sent as:  COMMAND value\\r\\n
and followed by a short delay to allow the TNC to process each one.

Parameter groups sent:
  1. General / identity  Ã¢â‚¬â€ MYCALL, MYPTCALL, MYSELCAL
  2. HF Packet           Ã¢â‚¬â€ PACLEN, TXDELAY, FRACK, RETRY, MAXFRAME, Ã¢â‚¬Â¦
  3. PACTOR              Ã¢â‚¬â€ ARQTMO, PTDOWN, PTUP, PT200, Ã¢â‚¬Â¦
  4. Misc                Ã¢â‚¬â€ CANLINE, SENDPAC, COMMAND char, Ã¢â‚¬Â¦

Usage::

    uploader = ParamsUploader(serial_manager, config_manager.app)
    uploader.upload()   # blocking Ã¢â‚¬â€ call from background thread only
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pk232py.comm.serial_manager import SerialManager
    from pk232py.config import AppConfig, AMTORConfig, BaudotConfig, MiscConfig, MailDropConfig

logger = logging.getLogger(__name__)

# Delay between verbose-mode parameter commands (seconds)
_PARAM_DELAY = 0.12


class ParamsUploader:
    """Sends TNC parameters as verbose-mode ASCII commands.

    Args:
        serial:  SerialManager instance (must be connected, verbose mode).
        config:  AppConfig with all parameter dataclasses.

    Call :meth:`upload` from a background thread Ã¢â‚¬â€ it blocks for
    the duration of the upload (several seconds for a full set).
    """

    def __init__(
        self,
        serial: "SerialManager",
        config: "AppConfig",
        echo_callback=None,
    ) -> None:
        self._serial = serial
        self._config = config
        # Optional callback(text, color) for UI display of sent commands
        self._echo = echo_callback

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upload(self) -> int:
        """Upload all parameters to the TNC in verbose mode.

        Sends each command and waits for the TNC "cmd:" prompt
        before sending the next one.

        Returns:
            Number of commands sent.
        """
        commands = self._build_commands()
        logger.info("ParamsUploader: uploading %d commands", len(commands))
        sent = 0
        for cmd in commands:
            logger.debug("Verbose param: %r", cmd)
            # Show sent command in UI (green)
            if self._echo:
                text = cmd.decode("ascii", errors="replace")
                self._echo(text, "#4ec94e")  # green
            ok = self._serial.write_verbose_wait(cmd, timeout=5.0)
            if not ok:
                logger.warning("ParamsUploader: no cmd: after %r, continuing",
                               cmd.rstrip())
            sent += 1
        logger.info("ParamsUploader: upload complete (%d commands)", sent)
        return sent

    def _build_commands(self) -> list[bytes]:
        """Build the full list of verbose-mode parameter commands."""
        cmds: list[bytes] = []
        cmds.append(self._cmd("EXPERT", "ON"))  # enable expert params

        tnc = self._config.tnc
        hf  = self._config.hf_packet
        pt  = self._config.pactor

        # Ã¢â€â‚¬Ã¢â€â‚¬ Identity Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
        if hf.mycall and hf.mycall != "NOCALL":
            cmds.append(self._cmd("MYCALL", hf.mycall.upper()))

        if pt.myptcall and pt.myptcall != "NOCALL":
            cmds.append(self._cmd("MYPTCALL", pt.myptcall.upper()))

        # Ã¢â€â‚¬Ã¢â€â‚¬ HF Packet Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
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
            self._bool("DAYSTAMP",  hf.dagstamp),
            self._bool("ILFPACK",   hf.ilfpack),
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

        # Ã¢â€â‚¬Ã¢â€â‚¬ PACTOR Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
        cmds += [
            # PACTOR parameters available in verbose mode
            self._bool("PTHUFF",  pt.pthuff),   # Huffman compression ON/OFF
            self._bool("PT200",   pt.pt200),    # auto speed selection ON/OFF
            self._cmd("PTOVER",  f"${pt.ptover:02X}"),  # changeover char
        ]

        # Ã¢â€â‚¬Ã¢â€â‚¬ AMTOR / NAVTEX / TDM Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
        am = self._config.amtor
        if am.myselcal:
            cmds.append(self._cmd("MYSELCAL", am.myselcal.upper()))
        if am.myaltcal:
            cmds.append(self._cmd("MYALTCAL", am.myaltcal.upper()))
        if am.myident:
            cmds.append(self._cmd("MYIDENT", am.myident.upper()))
        cmds += [
            self._cmd("ARQTMO",  str(am.arqtmo)),
            self._cmd("ARQTOL",  str(am.arqtol)),
            self._cmd("ADELAY",  str(am.adelay)),
            self._cmd("TDBAUD",  str(am.tdbaud)),
            self._cmd("TDCHAN",  str(am.tdchan)),
            self._bool("RFEC",     am.rfec),
            self._bool("RXREV",    am.rxrev),
            self._bool("TXREV",    am.txrev),
            self._bool("XMITOK",   am.xmitok),
        ]

        # Ã¢â€â‚¬Ã¢â€â‚¬ BAUDOT / ASCII / CW Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
        ba = self._config.baudot
        cmds += [
            self._cmd("MSPEED",  str(ba.mspeed)),
            self._cmd("MWEIGHT", str(ba.mweight)),
            self._cmd("CODE",    str(ba.code)),
            self._bool("ALFRTTY", ba.alfrtty),
            self._bool("DIDDLE",  ba.diddle),
            self._bool("MOPT",    ba.mopt),
            self._bool("RXREV",   ba.rxrev),
            self._bool("TXREV",   ba.txrev),
        ]
        if ba.aab:
            cmds.append(self._cmd("AAB", ba.aab))

        # Ã¢â€â‚¬Ã¢â€â‚¬ Misc Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
        mi = self._config.misc
        cmds += [
            self._cmd("CANLINE",  str(mi.canline)),
            self._cmd("CANPAC",   str(mi.canpac)),
            self._cmd("COMMAND",  f"${mi.command:02X}"),
            self._cmd("SENDPAC",  f"${mi.sendpac:02X}"),
        ]

        # Ã¢â€â‚¬Ã¢â€â‚¬ MailDrop Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
        md = self._config.maildrop
        if md.homebbs:
            cmds.append(self._cmd("HOMEBBS", md.homebbs.upper()))
        if md.mymail:
            cmds.append(self._cmd("MYMAIL", md.mymail.upper()))
        cmds += [
            self._bool("MAILDROP",  md.maildrop),
            self._bool("MDMON",     md.mdmon),
            self._bool("MMSG",      md.mmsg),
            self._bool("TMAIL",     md.tmail),
            self._bool("3RDPARTY",  md.third_party),
            self._bool("KILONFWD",  md.kilonfwd),
        ]
        if md.mtext:
            cmds.append(self._cmd("MTEXT", md.mtext))

        # Ã¢â€â‚¬Ã¢â€â‚¬ UTC time Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
        if tnc.utc_tnc_time:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            cmds.append(self._cmd(
                "DAYTIME",
                now.strftime("%y%m%d%H%M%S"),
            ))


        # Restore expert mode to default
        cmds.append(self._cmd("EXPERT", "OFF"))

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