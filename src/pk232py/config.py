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
class AMTORConfig:
    """AMTOR / NAVTEX / TDM operating parameters."""
    myselcal:  str   = ""
    myaltcal:  str   = ""
    myident:   str   = ""
    arqtmo:    int   = 60
    arqtol:    int   = 3
    adelay:    int   = 2
    tdbaud:    int   = 96
    tdchan:    int   = 0
    xlength:   int   = 64
    rfec:      bool  = True
    rxrev:     bool  = False
    srxall:    bool  = False
    txrev:     bool  = False
    usos:      bool  = False
    wideshft:  bool  = False
    xmitok:    bool  = True


@dataclass
class BaudotConfig:
    """BAUDOT / ASCII / CW operating parameters."""
    mspeed:    int   = 20
    mweight:   int   = 10
    code:      int   = 0
    xlength:   int   = 64
    xbaud:     int   = 0
    aab:       str   = ""
    alfrtty:   bool  = True
    diddle:    bool  = True
    mopt:      bool  = True
    rxrev:     bool  = False
    txrev:     bool  = False
    usos:      bool  = False
    wideshft:  bool  = False
    xmitok:    bool  = True


@dataclass
class MiscConfig:
    """Miscellaneous TNC parameters."""
    canline:   int   = 0x18
    canpac:    int   = 0x19
    command:   int   = 0x03
    sendpac:   int   = 0x0D
    mark:      int   = 2125
    space:     int   = 2295


@dataclass
class MailDropConfig:
    """MailDrop parameters."""
    homebbs:     str  = ""
    mymail:      str  = ""
    mtext:       str  = "Welcome To My Personal Mail Box."
    kilonfwd:    bool = True
    maildrop:    bool = False
    mdmon:       bool = False
    mmsg:        bool = True
    tmail:       bool = False
    third_party: bool = False


@dataclass
class AppearanceConfig:
    """Display appearance settings."""
    font_family:  str  = "Courier New"
    font_size:    int  = 10
    bg_color:     str  = "#1e1e1e"   # RX/TX display background
    fg_color:     str  = "#d4d4d4"   # RX/TX display foreground


@dataclass
class AppConfig:
    """Top-level application configuration container."""
    tnc:       TNCConfig       = field(default_factory=TNCConfig)
    hf_packet: HFPacketConfig  = field(default_factory=HFPacketConfig)
    pactor:    PACTORConfig    = field(default_factory=PACTORConfig)
    amtor:     AMTORConfig     = field(default_factory=AMTORConfig)
    baudot:    BaudotConfig    = field(default_factory=BaudotConfig)
    misc:      MiscConfig      = field(default_factory=MiscConfig)
    maildrop:   MailDropConfig   = field(default_factory=MailDropConfig)
    appearance: AppearanceConfig = field(default_factory=AppearanceConfig)


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
        self._apply_amtor()
        self._apply_baudot()
        self._apply_misc()
        self._apply_maildrop()
        self._apply_appearance()

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
        self._build_amtor()
        self._build_baudot()
        self._build_misc()
        self._build_maildrop()
        self._build_appearance()

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

    def _apply_amtor(self) -> None:
        if not self._config.has_section("AMTOR"):
            return
        s = self._config["AMTOR"]
        a = self.app.amtor
        a.myselcal  = s.get("myselcal",  a.myselcal)
        a.myaltcal  = s.get("myaltcal",  a.myaltcal)
        a.myident   = s.get("myident",   a.myident)
        a.arqtmo    = s.getint("arqtmo",   a.arqtmo)
        a.arqtol    = s.getint("arqtol",   a.arqtol)
        a.adelay    = s.getint("adelay",   a.adelay)
        a.tdbaud    = s.getint("tdbaud",   a.tdbaud)
        a.tdchan    = s.getint("tdchan",   a.tdchan)
        a.xlength   = s.getint("xlength",  a.xlength)
        a.rfec      = s.getboolean("rfec",      a.rfec)
        a.rxrev     = s.getboolean("rxrev",     a.rxrev)
        a.srxall    = s.getboolean("srxall",    a.srxall)
        a.txrev     = s.getboolean("txrev",     a.txrev)
        a.usos      = s.getboolean("usos",      a.usos)
        a.wideshft  = s.getboolean("wideshft",  a.wideshft)
        a.xmitok    = s.getboolean("xmitok",    a.xmitok)

    def _apply_baudot(self) -> None:
        if not self._config.has_section("Baudot"):
            return
        s = self._config["Baudot"]
        b = self.app.baudot
        b.mspeed   = s.getint("mspeed",   b.mspeed)
        b.mweight  = s.getint("mweight",  b.mweight)
        b.code     = s.getint("code",     b.code)
        b.xlength  = s.getint("xlength",  b.xlength)
        b.xbaud    = s.getint("xbaud",    b.xbaud)
        b.aab      = s.get("aab",         b.aab)
        b.alfrtty  = s.getboolean("alfrtty",  b.alfrtty)
        b.diddle   = s.getboolean("diddle",   b.diddle)
        b.mopt     = s.getboolean("mopt",     b.mopt)
        b.rxrev    = s.getboolean("rxrev",    b.rxrev)
        b.txrev    = s.getboolean("txrev",    b.txrev)
        b.usos     = s.getboolean("usos",     b.usos)
        b.wideshft = s.getboolean("wideshft", b.wideshft)
        b.xmitok   = s.getboolean("xmitok",   b.xmitok)

    def _apply_misc(self) -> None:
        if not self._config.has_section("Misc"):
            return
        s = self._config["Misc"]
        m = self.app.misc
        m.canline  = s.getint("canline",  m.canline)
        m.canpac   = s.getint("canpac",   m.canpac)
        m.command  = s.getint("command",  m.command)
        m.sendpac  = s.getint("sendpac",  m.sendpac)
        m.mark     = s.getint("mark",     m.mark)
        m.space    = s.getint("space",    m.space)

    def _apply_maildrop(self) -> None:
        if not self._config.has_section("MailDrop"):
            return
        s = self._config["MailDrop"]
        d = self.app.maildrop
        d.homebbs     = s.get("homebbs",     d.homebbs)
        d.mymail      = s.get("mymail",      d.mymail)
        d.mtext       = s.get("mtext",       d.mtext)
        d.kilonfwd    = s.getboolean("kilonfwd",    d.kilonfwd)
        d.maildrop    = s.getboolean("maildrop",    d.maildrop)
        d.mdmon       = s.getboolean("mdmon",       d.mdmon)
        d.mmsg        = s.getboolean("mmsg",        d.mmsg)
        d.tmail       = s.getboolean("tmail",       d.tmail)
        d.third_party = s.getboolean("third_party", d.third_party)

    def _build_amtor(self) -> None:
        a = self.app.amtor
        self._config["AMTOR"] = {
            "myselcal": a.myselcal, "myaltcal": a.myaltcal,
            "myident": a.myident, "arqtmo": str(a.arqtmo),
            "arqtol": str(a.arqtol), "adelay": str(a.adelay),
            "tdbaud": str(a.tdbaud), "tdchan": str(a.tdchan),
            "xlength": str(a.xlength), "rfec": str(a.rfec).lower(),
            "rxrev": str(a.rxrev).lower(), "srxall": str(a.srxall).lower(),
            "txrev": str(a.txrev).lower(), "usos": str(a.usos).lower(),
            "wideshft": str(a.wideshft).lower(), "xmitok": str(a.xmitok).lower(),
        }

    def _build_baudot(self) -> None:
        b = self.app.baudot
        self._config["Baudot"] = {
            "mspeed": str(b.mspeed), "mweight": str(b.mweight),
            "code": str(b.code), "xlength": str(b.xlength),
            "xbaud": str(b.xbaud), "aab": b.aab,
            "alfrtty": str(b.alfrtty).lower(), "diddle": str(b.diddle).lower(),
            "mopt": str(b.mopt).lower(), "rxrev": str(b.rxrev).lower(),
            "txrev": str(b.txrev).lower(), "usos": str(b.usos).lower(),
            "wideshft": str(b.wideshft).lower(), "xmitok": str(b.xmitok).lower(),
        }

    def _build_misc(self) -> None:
        m = self.app.misc
        self._config["Misc"] = {
            "canline": str(m.canline), "canpac": str(m.canpac),
            "command": str(m.command), "sendpac": str(m.sendpac),
            "mark": str(m.mark), "space": str(m.space),
        }

    def _build_maildrop(self) -> None:
        d = self.app.maildrop
        self._config["MailDrop"] = {
            "homebbs": d.homebbs, "mymail": d.mymail, "mtext": d.mtext,
            "kilonfwd": str(d.kilonfwd).lower(), "maildrop": str(d.maildrop).lower(),
            "mdmon": str(d.mdmon).lower(), "mmsg": str(d.mmsg).lower(),
            "tmail": str(d.tmail).lower(), "third_party": str(d.third_party).lower(),
        }

    def _apply_appearance(self) -> None:
        if not self._config.has_section("Appearance"):
            return
        s = self._config["Appearance"]
        a = self.app.appearance
        a.font_family = s.get("font_family", a.font_family)
        a.font_size   = s.getint("font_size", a.font_size)
        a.bg_color    = s.get("bg_color",    a.bg_color)
        a.fg_color    = s.get("fg_color",    a.fg_color)

    def _build_appearance(self) -> None:
        a = self.app.appearance
        self._config["Appearance"] = {
            "font_family": a.font_family,
            "font_size":   str(a.font_size),
            "bg_color":    a.bg_color,
            "fg_color":    a.fg_color,
        }