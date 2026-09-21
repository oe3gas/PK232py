# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS - GPL v2
"""TNC Parameter Uploader - sends stored parameters in verbose mode.

Reads parameters from AppConfig (which is backed by pk232py.ini) and
sends them as ASCII verbose-mode commands to the TNC after initialisation.

All commands are sent as:  COMMAND value\\r\\n
and followed by a short delay to allow the TNC to process each one.

Parameter groups sent:
  1. General / identity  - MYCALL, MYPTCALL, MYSELCAL
  2. HF Packet           - PACLEN, TXDELAY, FRACK, RETRY, MAXFRAME, ...
  3. PACTOR              - ARQTMO, PTDOWN, PTUP, PT200, ...
  4. Misc                - CANLINE, SENDPAC, COMMAND char, ...

Usage::

    uploader = ParamsUploader(serial_manager, config_manager.app)
    uploader.upload()   # blocking - call from background thread only
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

    Call :meth:`upload` from a background thread - it blocks for
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
        has_pactor = getattr(self._serial, 'has_pactor', True)
        if not has_pactor:
            logger.info(
                "ParamsUploader: TNC has no PACTOR - "
                "skipping PACTOR-specific commands"
            )
        commands = self._build_commands(has_pactor=has_pactor)
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

    def _build_commands(self, has_pactor: bool = True) -> list[bytes]:
        """Build the full list of verbose-mode parameter commands."""
        cmds: list[bytes] = []
        cmds.append(self._cmd("EXPERT", "ON"))  # enable expert params

        tnc = self._config.tnc
        hf  = self._config.hf_packet
        pt  = self._config.pactor

        # - Identity -
        if hf.mycall and hf.mycall != "NOCALL":
            cmds.append(self._cmd("MYCALL", hf.mycall.upper()))
        # MYPTCALL is PACTOR-only - sent inside the has_pactor block below

        # - HF Packet -
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
            # RESPTIME - confirmed against the TRM (RP RESPTIME command).
            self._cmd("RESPTIME", str(hf.resptime)),
            # USERS caps simultaneous AX.25 connections (P11) - verbose-mode
            # command name, NOT the Host Mode mnemonic UR (that one is not
            # used or built here; changing USERS at runtime in Host Mode is
            # out of scope). NOTE: the TNC rejects some parameter changes
            # with error $09 "not while connected" while a link is up (TRM
            # 4.3) - whether USERS is one of them is not confirmed (see
            # Testplan T104). This uploader only ever runs before Host Mode
            # is entered, so it is not yet a practical problem here.
            self._cmd("USERS",    str(hf.users)),
        ]

        # Boolean flags
        cmds += [
            self._bool("AX25L2V2",  hf.ax25l2v2),
            self._bool("HEADERLN",  hf.headerln),
            self._bool("CONSTAMP",  hf.constamp),
            self._bool("DAYSTAMP",  hf.dagstamp),
            self._bool("ILFPACK",   hf.ilfpack),
            # ACRPACK (mnemonic AK, TRM Host Mode command list) - renamed
            # from "aerpack", which does not exist as a PK-232 command (P13).
            self._bool("ACRPACK",   hf.acrpack),
            self._bool("ALFPACK",   hf.alfpack),
            self._bool("MRPT",      hf.mrpt),
            self._bool("PPERSIST",  hf.ppersist),
            self._bool("XMITOK",    hf.xmitok),
        ]

        # Message params
        # NOTE (P13): MYCALL used to be sent again here, unconditionally -
        # a duplicate of the "- Identity -" MYCALL above, which is the
        # correct one since it also guards against the "NOCALL" placeholder.
        # TXSMT is deliberately never sent: it does not appear anywhere in
        # the PK-232 TRM Host Mode command list (see UPLOAD_EXEMPT in
        # test_param_dialogs_roundtrip.py and the disabled dialog spinbox).
        if hf.unproto:
            cmds.append(self._cmd("UNPROTO", hf.unproto))
        if hf.btext:
            cmds.append(self._cmd("BTEXT",   hf.btext))
        if hf.ctext:
            cmds.append(self._cmd("CTEXT",   hf.ctext))

        # Access filters (P13.3, TRM mnemonics CF/DF/MF/MT)
        cmds += self._access_filter_cmds("CFROM", hf.cfrom_mode, hf.cfrom_calls)
        cmds += self._access_filter_cmds("DFROM", hf.dfrom_mode, hf.dfrom_calls)
        cmds += self._access_filter_cmds("MFROM", hf.mfrom_mode, hf.mfrom_calls)
        cmds += self._access_filter_cmds("MTO",   hf.mto_mode,   hf.mto_calls)

        # Individual flags (P13.3) - 8BITCONV (8B) and HID (HI) confirmed
        # against the TRM. MBELL is deliberately NOT sent: it is absent from
        # the TRM's 1987 Host Mode command list (see HFPacketConfig.mbell).
        cmds += [
            self._bool("8BITCONV", hf.bitconv8),
            self._bool("HID",      hf.hid),
        ]

        # - PACTOR -
        # PACTOR commands: only send when TNC has the PACTOR option.
        # On a PK-232MBX without PACTOR, these return ?What? errors.
        if has_pactor:
            # PACTOR callsign
            if pt.myptcall and pt.myptcall != "NOCALL":
                cmds.append(self._cmd("MYPTCALL", pt.myptcall.upper()))
            # PACTOR parameters
            cmds += [
                self._bool("PTHUFF",  pt.pthuff),
                self._bool("PT200",   pt.pt200),
                self._cmd("PTOVER",  f"${pt.ptover:02X}"),
            ]
            # AMTOR: ARQTOL only on PACTOR firmware
            cmds.append(self._cmd("ARQTOL",  str(self._config.amtor.arqtol)))
            # Baudot/CW: MOPT only on PACTOR firmware
            cmds.append(self._bool("MOPT", self._config.baudot.mopt))
        else:
            logger.debug(
                "Skipping PACTOR-only commands "
                "(MYPTCALL, ARQTOL, MOPT) - TNC has no PACTOR option"
            )

        # - AMTOR / NAVTEX / TDM -
        am = self._config.amtor
        if am.myselcal:
            cmds.append(self._cmd("MYSELCAL", am.myselcal.upper()))
        if am.myaltcal:
            cmds.append(self._cmd("MYALTCAL", am.myaltcal.upper()))
        if am.myident:
            cmds.append(self._cmd("MYIDENT", am.myident.upper()))
        cmds += [
            self._cmd("ARQTMO",  str(am.arqtmo)),
            # ARQTOL: PACTOR firmware only - sent in has_pactor block below
            self._cmd("ADELAY",  str(am.adelay)),
            self._cmd("TDBAUD",  str(am.tdbaud)),
            self._cmd("TDCHAN",  str(am.tdchan)),
            self._bool("RFEC",     am.rfec),
            self._bool("RXREV",    am.rxrev),
            self._bool("TXREV",    am.txrev),
            self._bool("XMITOK",   am.xmitok),
        ]

        # - BAUDOT / ASCII / CW -
        ba = self._config.baudot
        cmds += [
            self._cmd("MSPEED",  str(ba.mspeed)),
            self._cmd("MWEIGHT", str(ba.mweight)),
            self._cmd("CODE",    str(ba.code)),
            self._bool("ALFRTTY", ba.alfrtty),
            self._bool("DIDDLE",  ba.diddle),
            # MOPT (Morse Option): PACTOR firmware only - sent below
            self._bool("RXREV",   ba.rxrev),
            self._bool("TXREV",   ba.txrev),
        ]
        if ba.aab:
            cmds.append(self._cmd("AAB", ba.aab))

        # - Misc -
        mi = self._config.misc
        cmds += [
            self._cmd("CANLINE",  str(mi.canline)),
            self._cmd("CANPAC",   str(mi.canpac)),
            self._cmd("COMMAND",  f"${mi.command:02X}"),
            self._cmd("SENDPAC",  f"${mi.sendpac:02X}"),
        ]

        # - MailDrop -
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

        # - UTC time -
        if tnc.utc_tnc_time:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            cmds.append(self._cmd(
                "DAYTIME",
                now.strftime("%y%m%d%H%M%S"),
            ))


        # Restore expert mode to default
        # EXPERT OFF only for PACTOR-capable firmware
        # (non-PACTOR variants don't support EXPERT command)
        if has_pactor:
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

    def _access_filter_cmds(self, name: str, mode: str, calls: str) -> list[bytes]:
        """Build the command(s) for one access filter (CFROM/DFROM/MFROM/MTO,
        P13.3):
            ALL / NONE  -> "NAME ALL" / "NAME NONE"
            YES / NO    -> "NAME YES <calls>" / "NAME NO <calls>"
            YES/NO with no callsigns configured -> nothing is sent (a bare
            "NAME YES" with no list is ambiguous at best, so log a warning
            and skip rather than guess what the TNC would do with it).
        """
        mode = (mode or "").upper()
        if mode in ("ALL", "NONE"):
            return [self._cmd(name, mode)]
        if mode in ("YES", "NO"):
            if not calls:
                logger.warning(
                    "ParamsUploader: %s mode=%s but no callsigns configured "
                    "- skipping", name, mode
                )
                return []
            return [self._cmd(name, f"{mode} {calls}")]
        logger.warning("ParamsUploader: unknown %s mode %r - skipping", name, mode)
        return []