# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.

"""Configuration management — reads and writes pk232py.ini.

The INI file is stored at:
  Windows : %USERPROFILE%\\.pk232py\\pk232py.ini
  Linux   : ~/.pk232py/pk232py.ini
  macOS   : ~/.pk232py/pk232py.ini

Each dataclass maps 1:1 to an INI section.  Parameters that are not
yet persisted (e.g. flags not shown in the dialog) are intentionally
omitted from _apply()/_build() and keep their dataclass defaults.
"""

from __future__ import annotations

import configparser
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_FILE = Path.home() / ".pk232py" / "pk232py.ini"


# ---------------------------------------------------------------------------
# TNC connection settings
# ---------------------------------------------------------------------------

@dataclass
class TNCConfig:
    """TNC connection and initialisation settings.

    Matches the PCPackRatt 'TNC Configuration' dialog.
    """
    model:                          str  = "PK232MBX"
    port:                           str  = ""
    tbaud:                          int  = 9600
    # Checkboxes from TNC Configuration dialog
    echo_packets:                   bool = False
    echo_port2_packets:             bool = False
    utc_tnc_time:                   bool = True
    utc_port2_time:                 bool = False
    fast_init:                      bool = True
    host_mode_on_exit:              bool = True
    save_restore_maildrop:          bool = False
    dumb_term_init:                 bool = False
    show_unknown_cmd_errors:        bool = True
    show_not_while_connected_errors: bool = False
    auto_qso_check:                 bool = False


# ---------------------------------------------------------------------------
# HF Packet parameters
# ---------------------------------------------------------------------------

@dataclass
class HFPacketConfig:
    """HF Packet operating parameters (300 baud AX.25).

    Matches the PCPackRatt 'HF Packet Parameters' dialog.
    Only the most commonly changed parameters are persisted;
    all others keep their TNC firmware defaults on each start.
    """
    # Message parameters (HF Packet Msg Params dialog)
    mycall:     str = "NOCALL"   # MGCALL — gateway/station callsign
    btext:      str = ""         # BTEXT  — beacon text
    ctext:      str = "%"        # CTEXT  — connect text
    unproto:    str = "CQ"       # UNPROTO path

    # Numeric parameters
    paclen:     int = 64
    txdelay:    int = 30
    maxframe:   int = 1
    frack:      int = 7
    retry:      int = 10
    persist:    int = 63
    slottime:   int = 30
    dwait:      int = 16
    check:      int = 30
    monitor:    int = 4
    resptime:   int = 0
    txsmt:      int = 50

    # Boolean flags
    ax25l2v2:   bool = True
    headerln:   bool = True
    constamp:   bool = True
    dagstamp:   bool = True   # Note: spec uses DAGSTAMP not DAYSTAMP
    ilfpack:    bool = True
    aerpack:    bool = True
    alfpack:    bool = True
    mrpt:       bool = True
    ppersist:   bool = True
    xmitok:     bool = True


# ---------------------------------------------------------------------------
# PACTOR parameters
# ---------------------------------------------------------------------------

@dataclass
class PACTORConfig:
    """PACTOR I operating parameters.

    Matches the PCPackRatt 'PACTOR Parameters' dialog.
    Note: PACTOR callsign is MYPTCALL (mnemonic MK), NOT MYCALL (ML).
    """
    myptcall:   str   = "NOCALL"
    arqtmo:     int   = 60      # ARQ timeout in seconds
    adelay:     int   = 2       # ARQ delay
    ptdown:     int   = 6       # downgrade threshold
    ptup:       int   = 3       # upgrade threshold
    pthuff:     int   = 0       # Huffman compression (0=off)
    ptover:     int   = 0x1A    # direction-change char (Ctrl-Z)
    ptsum:      int   = 5       # checksum
    pttries:    int   = 2       # connection tries
    # Float parameter
    ptsend:     float = 1.2     # unproto send delay (seconds)
    # Boolean flags
    pt200:      bool  = True    # allow 200 baud
    ptround:    bool  = False   # round-table mode after PTSEND
    xmitok:     bool  = True


# ---------------------------------------------------------------------------
# Application-level config
# ---------------------------------------------------------------------------

@dataclass
class AppConfig:
    """Top-level application configuration container."""
    tnc:       TNCConfig       = field(default_factory=TNCConfig)
    hf_packet: HFPacketConfig  = field(default_factory=HFPacketConfig)
    pactor:    PACTORConfig    = field(default_factory=PACTORConfig)


# ---------------------------------------------------------------------------
# ConfigManager
# ---------------------------------------------------------------------------

class ConfigManager:
    """Reads and writes the INI configuration file.

    Usage::

        cfg = ConfigManager()
        cfg.load()                    # load from disk (defaults if missing)
        port = cfg.app.tnc.port       # read a value
        cfg.app.tnc.port = "COM3"     # modify
        cfg.save()                    # persist to disk
    """

    def __init__(self, path: Path = CONFIG_FILE) -> None:
        self._path   = path
        self._config = configparser.RawConfigParser()
        self.app     = AppConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load configuration from file.  Missing file → use defaults."""
        if not self._path.exists():
            logger.info("Config file not found, using defaults: %s", self._path)
            return
        self._config.read(self._path, encoding="utf-8")
        self._apply()
        logger.info("Configuration loaded from %s", self._path)

    def save(self) -> None:
        """Persist current configuration to file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._build()
        with open(self._path, "w", encoding="utf-8") as fh:
            self._config.write(fh)
        logger.info("Configuration saved to %s", self._path)

    # ------------------------------------------------------------------
    # Internal: INI → dataclasses
    # ------------------------------------------------------------------

    def _apply(self) -> None:
        """Map INI sections → dataclass fields."""
        self._apply_tnc()
        self._apply_hf_packet()
        self._apply_pactor()

    def _apply_tnc(self) -> None:
        if not self._config.has_section("TNC"):
            return
        s   = self._config["TNC"]
        tnc = self.app.tnc
        tnc.model                           = s.get("model",     tnc.model)
        tnc.port                            = s.get("port",      tnc.port)
        tnc.tbaud                           = s.getint("tbaud",  tnc.tbaud)
        tnc.echo_packets                    = s.getboolean("echo_packets",                    tnc.echo_packets)
        tnc.utc_tnc_time                    = s.getboolean("utc_tnc_time",                    tnc.utc_tnc_time)
        tnc.fast_init                       = s.getboolean("fast_init",                       tnc.fast_init)
        tnc.host_mode_on_exit               = s.getboolean("host_mode_on_exit",               tnc.host_mode_on_exit)
        tnc.save_restore_maildrop           = s.getboolean("save_restore_maildrop",           tnc.save_restore_maildrop)
        tnc.dumb_term_init                  = s.getboolean("dumb_term_init",                  tnc.dumb_term_init)
        tnc.show_unknown_cmd_errors         = s.getboolean("show_unknown_cmd_errors",         tnc.show_unknown_cmd_errors)
        tnc.show_not_while_connected_errors = s.getboolean("show_not_while_connected_errors", tnc.show_not_while_connected_errors)
        tnc.auto_qso_check                  = s.getboolean("auto_qso_check",                  tnc.auto_qso_check)

    def _apply_hf_packet(self) -> None:
        if not self._config.has_section("HF_Packet"):
            return
        s  = self._config["HF_Packet"]
        hf = self.app.hf_packet
        hf.mycall    = s.get("mycall",    hf.mycall)
        hf.btext     = s.get("btext",     hf.btext)
        hf.ctext     = s.get("ctext",     hf.ctext)
        hf.unproto   = s.get("unproto",   hf.unproto)
        hf.paclen    = s.getint("paclen",    hf.paclen)
        hf.txdelay   = s.getint("txdelay",   hf.txdelay)
        hf.maxframe  = s.getint("maxframe",  hf.maxframe)
        hf.frack     = s.getint("frack",     hf.frack)
        hf.retry     = s.getint("retry",     hf.retry)
        hf.persist   = s.getint("persist",   hf.persist)
        hf.slottime  = s.getint("slottime",  hf.slottime)
        hf.dwait     = s.getint("dwait",     hf.dwait)
        hf.check     = s.getint("check",     hf.check)
        hf.monitor   = s.getint("monitor",   hf.monitor)
        hf.resptime  = s.getint("resptime",  hf.resptime)
        hf.ax25l2v2  = s.getboolean("ax25l2v2",  hf.ax25l2v2)
        hf.headerln  = s.getboolean("headerln",  hf.headerln)
        hf.constamp  = s.getboolean("constamp",  hf.constamp)
        hf.dagstamp  = s.getboolean("dagstamp",  hf.dagstamp)
        hf.ilfpack   = s.getboolean("ilfpack",   hf.ilfpack)
        hf.mrpt      = s.getboolean("mrpt",      hf.mrpt)
        hf.ppersist  = s.getboolean("ppersist",  hf.ppersist)
        hf.xmitok    = s.getboolean("xmitok",    hf.xmitok)

    def _apply_pactor(self) -> None:
        if not self._config.has_section("PACTOR"):
            return
        s  = self._config["PACTOR"]
        pt = self.app.pactor
        pt.myptcall  = s.get("myptcall",   pt.myptcall)
        pt.arqtmo    = s.getint("arqtmo",    pt.arqtmo)
        pt.adelay    = s.getint("adelay",    pt.adelay)
        pt.ptdown    = s.getint("ptdown",    pt.ptdown)
        pt.ptup      = s.getint("ptup",      pt.ptup)
        pt.pthuff    = s.getint("pthuff",    pt.pthuff)
        pt.ptover    = s.getint("ptover",    pt.ptover)
        pt.ptsum     = s.getint("ptsum",     pt.ptsum)
        pt.pttries   = s.getint("pttries",   pt.pttries)
        pt.ptsend    = s.getfloat("ptsend",  pt.ptsend)
        pt.pt200     = s.getboolean("pt200",    pt.pt200)
        pt.ptround   = s.getboolean("ptround",  pt.ptround)
        pt.xmitok    = s.getboolean("xmitok",   pt.xmitok)

    # ------------------------------------------------------------------
    # Internal: dataclasses → INI
    # ------------------------------------------------------------------

    def _build(self) -> None:
        """Map dataclass fields → INI sections."""
        self._build_tnc()
        self._build_hf_packet()
        self._build_pactor()

    def _build_tnc(self) -> None:
        tnc = self.app.tnc
        self._config["TNC"] = {
            "model":                            tnc.model,
            "port":                             tnc.port,
            "tbaud":                            str(tnc.tbaud),
            "echo_packets":                     str(tnc.echo_packets).lower(),
            "utc_tnc_time":                     str(tnc.utc_tnc_time).lower(),
            "fast_init":                        str(tnc.fast_init).lower(),
            "host_mode_on_exit":                str(tnc.host_mode_on_exit).lower(),
            "save_restore_maildrop":            str(tnc.save_restore_maildrop).lower(),
            "dumb_term_init":                   str(tnc.dumb_term_init).lower(),
            "show_unknown_cmd_errors":          str(tnc.show_unknown_cmd_errors).lower(),
            "show_not_while_connected_errors":  str(tnc.show_not_while_connected_errors).lower(),
            "auto_qso_check":                   str(tnc.auto_qso_check).lower(),
        }

    def _build_hf_packet(self) -> None:
        hf = self.app.hf_packet
        self._config["HF_Packet"] = {
            "mycall":   hf.mycall,
            "btext":    hf.btext,
            "ctext":    hf.ctext,
            "unproto":  hf.unproto,
            "paclen":   str(hf.paclen),
            "txdelay":  str(hf.txdelay),
            "maxframe": str(hf.maxframe),
            "frack":    str(hf.frack),
            "retry":    str(hf.retry),
            "persist":  str(hf.persist),
            "slottime": str(hf.slottime),
            "dwait":    str(hf.dwait),
            "check":    str(hf.check),
            "monitor":  str(hf.monitor),
            "resptime": str(hf.resptime),
            "ax25l2v2": str(hf.ax25l2v2).lower(),
            "headerln": str(hf.headerln).lower(),
            "constamp": str(hf.constamp).lower(),
            "dagstamp": str(hf.dagstamp).lower(),
            "ilfpack":  str(hf.ilfpack).lower(),
            "mrpt":     str(hf.mrpt).lower(),
            "ppersist": str(hf.ppersist).lower(),
            "xmitok":   str(hf.xmitok).lower(),
        }

    def _build_pactor(self) -> None:
        pt = self.app.pactor
        self._config["PACTOR"] = {
            "myptcall": pt.myptcall,
            "arqtmo":   str(pt.arqtmo),
            "adelay":   str(pt.adelay),
            "ptdown":   str(pt.ptdown),
            "ptup":     str(pt.ptup),
            "pthuff":   str(pt.pthuff),
            "ptover":   str(pt.ptover),
            "ptsum":    str(pt.ptsum),
            "pttries":  str(pt.pttries),
            "ptsend":   str(pt.ptsend),
            "pt200":    str(pt.pt200).lower(),
            "ptround":  str(pt.ptround).lower(),
            "xmitok":   str(pt.xmitok).lower(),
        }