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

    # P40.4: abort rather than wait out 5 s x every remaining command once
    # more than this many in a row got no "cmd:" response - a real TNC
    # answers every command in well under a second (T103, hardware-
    # confirmed), so several in a row this slow means something is
    # actually wrong (Host Mode active, TNC hung, wrong port state), not
    # an occasional slow response.
    _MAX_CONSECUTIVE_SILENT = 3

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
            Number of commands sent (0 if refused - see below).
        """
        # P40.2: there is no "cmd:" prompt in Host Mode at all - the TNC
        # expects SOH-framed binary frames there, and plain ASCII text is
        # never executed as a command. Sending the whole parameter set
        # into Host Mode by mistake does not fail fast: write_verbose_wait()
        # just times out on every single command (its own 5 s timeout,
        # observed 24.09.2026: 68 commands x 5 s = ~6 minutes, and none of
        # them actually reached the TNC). Checked ONCE, before the first
        # command, not per-command - MainWindow._on_verbose_mode_ready()
        # already calls this only in verbose mode (Phase 2, before Phase 3
        # Host Mode entry - see serial_manager.py's own module docstring
        # and SERIAL_CONNECTION_STATE_MACHINE.md's C3/C4/C5/C6 states), so
        # this is defense-in-depth against any other/future caller, not a
        # fix to that call site.
        if getattr(self._serial, 'is_host_mode', False):
            logger.error(
                "ParamsUploader: refusing to upload parameters in Host "
                "Mode - verbose text is not executed there"
            )
            return 0
        # P43.2: is_host_mode alone is not enough - it is the SOFTWARE's
        # own belief, and a fresh connection cycle starts it at False
        # regardless of what the physical TNC is actually doing (P43's
        # own finding: a TNC left in Host Mode from a previous session
        # is not noticed by is_host_mode at all). verbose_confirmed is
        # only ever set True by SerialManager's active detection chain
        # (_init_tnc_thread(), P43.1) once it has POSITIVE evidence of a
        # verbose prompt this session - defaults to True here (permissive,
        # same convention as has_pactor below) so a duck-typed test double
        # that predates P43 and never heard of this attribute is not
        # penalised for it; a real SerialManager always has the attribute
        # and starts every connection cycle at False.
        if not getattr(self._serial, 'verbose_confirmed', True):
            logger.error(
                "ParamsUploader: refusing to upload: the verbose prompt "
                "was never confirmed in this session"
            )
            return 0
        has_pactor = getattr(self._serial, 'has_pactor', True)
        if not has_pactor:
            logger.info(
                "ParamsUploader: TNC has no PACTOR - "
                "skipping PACTOR-specific commands"
            )
        # MailDrop capability has no boot-banner marker (unlike PACTOR),
        # so it is queried here, in verbose mode, right before the
        # upload (P37) - detect_maildrop() never sends MDCHECK. A
        # detection failure (None) must not lock out an existing
        # feature, so only an explicit False skips the MailDrop block.
        detect_maildrop = getattr(self._serial, 'detect_maildrop', None)
        has_maildrop = detect_maildrop() if detect_maildrop else True
        if has_maildrop is False:
            logger.info(
                "ParamsUploader: TNC has no MailDrop - "
                "skipping MailDrop commands"
            )
        commands = self._build_commands(
            has_pactor=has_pactor, has_maildrop=(has_maildrop is not False),
        )
        logger.info("ParamsUploader: uploading %d commands", len(commands))
        sent = 0
        consecutive_silent = 0
        for cmd in commands:
            logger.debug("Verbose param: %r", cmd)
            # Show sent command in UI (green)
            if self._echo:
                text = cmd.decode("ascii", errors="replace")
                self._echo(text, "#4ec94e")  # green
            ok = self._serial.write_verbose_wait(cmd, timeout=5.0)
            sent += 1
            if not ok:
                consecutive_silent += 1
                # P40.4: "no cmd:" is not a harmless hiccup - it means the
                # command almost certainly never reached the TNC as a
                # real command at all (exactly the 24.09.2026 Host Mode
                # finding - every single one of 68 commands hit this and
                # NONE were executed). Sharpened from the old "continuing"
                # wording, which understated that.
                logger.warning(
                    "ParamsUploader: no cmd: after %r - "
                    "command probably NOT executed",
                    cmd.rstrip(),
                )
                if consecutive_silent > self._MAX_CONSECUTIVE_SILENT:
                    logger.error(
                        "ParamsUploader: %d commands in a row with no "
                        "response - aborting upload, check TNC state",
                        consecutive_silent,
                    )
                    break
            else:
                consecutive_silent = 0
        logger.info("ParamsUploader: upload complete (%d commands)", sent)
        return sent

    # Three parameters confirmed (24.09.2026) to reliably answer a bare
    # verbose-mode query - see verify().
    _VERIFY_SAMPLE = ("MYCALL", "PACLEN", "MAXFRAME")

    def verify(self) -> tuple[int, int]:
        """P40.3: spot-check a small sample of just-uploaded parameters
        against the configured values, while still in verbose mode.

        write_verbose_wait() alone only confirms a "cmd:" prompt came
        back after each upload command - it does not confirm the TNC
        actually accepted or even parsed that command (exactly the gap
        that let the 24.09.2026 Host Mode upload run silently "succeed"
        for 6 minutes with nothing reaching the TNC at all). This reads
        MYCALL/PACLEN/MAXFRAME back and compares them to AppConfig -
        under a second, and it would have made that failure visible
        immediately instead of only on the next real QSO attempt.

        Never blocks or aborts the connection sequence - only logs.

        Returns:
            (matched, applicable) - applicable excludes a parameter with
            nothing configured to compare against (MYCALL left as the
            NOCALL placeholder, never uploaded in the first place), so a
            clean run reports matched == applicable, not always out of 3.
        """
        query = getattr(self._serial, 'query_verbose_value', None)
        if query is None:
            return (0, 0)
        hf = self._config.hf_packet
        expected: dict[str, str | None] = {
            "MYCALL": hf.mycall.upper() if hf.mycall and hf.mycall != "NOCALL" else None,
            "PACLEN": str(hf.paclen),
            "MAXFRAME": str(hf.maxframe),
        }
        applicable = {name: want for name, want in expected.items() if want is not None}
        matched = 0
        for name, want in applicable.items():
            got = query(name)
            if got is None:
                logger.warning(
                    "ParamsUploader: no answer verifying %s (expected %r)",
                    name, want,
                )
                continue
            if got.upper() == want.upper():
                matched += 1
            else:
                logger.warning(
                    "ParamsUploader: %s mismatch after upload - "
                    "expected %r, TNC says %r",
                    name, want, got,
                )
        if applicable and matched == len(applicable):
            logger.info(
                "ParamsUploader: parameter upload verified (%d/%d)",
                matched, len(applicable),
            )
        return (matched, len(applicable))

    def _build_commands(
        self, has_pactor: bool = True, has_maildrop: bool = True,
    ) -> list[bytes]:
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
        # Skipped entirely on firmware without MailDrop (P37, Device C /
        # docs/DEVICES.md) - every command below would otherwise come
        # back '?What?' (one log line here instead of seven error
        # responses from the TNC).
        if has_maildrop:
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
        else:
            logger.debug(
                "Skipping MailDrop commands - TNC has no MailDrop option"
            )

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