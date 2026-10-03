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
import os
from dataclasses import dataclass, field
from pathlib import Path

from pk232py.colors import THEME_DISPLAY, THEME_TEXT_COLORS

logger = logging.getLogger(__name__)

CONFIG_FILE = Path.home() / ".pk232py" / "pk232py.ini"

# P48.1: the smallest possible opening to redirect ConfigManager's default
# path away from the operator's real ~/.pk232py/pk232py.ini - read only
# when actually set, so production behaviour (no env var present) is
# unchanged. An env var was chosen over widening MainWindow's own
# constructor: every existing MainWindow()/ConfigManager() call site (test
# or production) keeps working unmodified, and the P48.2 autouse fixture
# (tests/conftest.py) can redirect every test's config path without any
# test needing to know ConfigManager exists at all. An explicit `path=`
# argument to ConfigManager() still always wins - this only affects the
# default. Not underscore-prefixed: the test suite imports it by name.
CONFIG_PATH_ENV_VAR = "PK232PY_CONFIG_PATH"


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
    maxframe:   int = 1    # HF value (P73: the VHF value is vhf_maxframe below)
    frack:      int = 7
    retry:      int = 10
    persist:    int = 63
    slottime:   int = 30   # HF value (P73: the VHF value is vhf_slottime below)
    dwait:      int = 16
    check:      int = 30
    monitor:    int = 4
    resptime:   int = 0
    users:      int = 10  # USERS — max. simultaneous AX.25 connections (1-10).
                          # Operator decision 30.09.2026 (P70 E2, T147 F3/F4): with 1 the
                          # TNC rejects the second caller; an existing INI value is kept.
    txsmt:      int = 50

    # VHF values of the two parameters that differ per band (P73 B). They are
    # the values VHF Packet used to send as fixed numbers (MX 4 / SL 10), so
    # an INI without these keys changes nothing. Only the active band's value
    # reaches the TNC (comm/host_params.py BAND_PARAMS).
    vhf_maxframe: int = 4
    vhf_slottime: int = 10

    # Boolean flags
    ax25l2v2:   bool = True
    headerln:   bool = True
    constamp:   bool = True
    dagstamp:   bool = True   # Note: spec uses DAGSTAMP not DAYSTAMP
    ilfpack:    bool = True
    # Renamed from "aerpack" (P13): the TRM Host Mode command list has no
    # such command, but does have ACRPACK (mnemonic AK) - "aerpack" was
    # almost certainly a typo in an earlier specification. INI reads still
    # fall back to the old "aerpack" key (see _apply_hf_packet()); only
    # "acrpack" is ever written from here on.
    acrpack:    bool = True
    alfpack:    bool = True
    mrpt:       bool = True
    ppersist:   bool = True
    xmitok:     bool = True

    # Access filters (P13.3, TRM mnemonics CF/DF/MF/MT). mode is one of
    # "ALL"/"NONE"/"YES"/"NO"; *_calls is a comma-separated list of up to
    # 8 callsigns, used only when mode is "YES" or "NO".
    cfrom_mode:  str = "ALL"
    cfrom_calls: str = ""
    dfrom_mode:  str = "ALL"
    dfrom_calls: str = ""
    mfrom_mode:  str = "ALL"
    mfrom_calls: str = ""
    mto_mode:    str = "NONE"
    mto_calls:   str = ""

    # Individual flags (P13.3). "bitconv8" because a Python identifier
    # cannot start with a digit — the TNC command name is "8BITCONV".
    bitconv8: bool = False
    hid:      bool = False
    # MBELL is not in the TRM's 1987 Host Mode command list (may exist only
    # on later MBX firmware) - wired to the dialog/INI like the others, but
    # never uploaded until confirmed (see ParamsUploader / UPLOAD_EXEMPT).
    mbell:    bool = False

    # Packet monitor flags (P73 C). They were checkboxes in the dialog that
    # neither reached the INI nor the TNC. Defaults = the old checkbox
    # pre-setting (all off). Matrix mnemonics: MDIGI MD, MPROTO MQ, MSTAMP MS,
    # PASSALL PX, BBSMSGS BB (verified T160/T161). There is no FULLDP: the TNC
    # answers ?What? on both devices.
    mdigi:    bool = False
    mproto:   bool = False
    mstamp:   bool = False
    passall:  bool = False
    bbsmsgs:  bool = False

    # UBIT 0 (CUSTOM bit 0, P74). False = "UBIT 0 OFF": every packet with a
    # correct CRC is processed. The factory default UBIT 0 ON silently drops
    # packets too weak to light the DCD LED (WHYNOT ON then reports "packet
    # received below threshold"; found 01.10.2026, device B). The TNC has no
    # backup battery, so it starts with ON every time and the app must set
    # the value on every init. Applies to ALL modes, not only Packet.
    ubit0:    bool = False

    # Display-only setting (P47) - never uploaded, see UPLOAD_EXEMPT in
    # test_param_dialogs_roundtrip.py. When on, every link message
    # (CONNECTED/DISCONNECTED/Retry count exceeded/...) also appears in
    # the MON view (MON chip, P70), tagged with the channel it actually
    # happened on, so it stays visible even while looking at a different
    # channel. Off by default.
    show_link_messages_in_ui_channel: bool = False

    # Display-only settings (P50) - never uploaded, see UPLOAD_EXEMPT.
    # show_timestamps: prepend "[HH:MM:SS] " (muted colour) to every RX
    # line. Off by default - the compact "[CHn]"-free CH view and the
    # "n|" ALL-view tag already cost enough width without it.
    show_timestamps: bool = False
    # rx_max_lines_per_channel: QTextDocument.setMaximumBlockCount() for
    # each of the ten per-channel RX documents AND the merged ALL
    # document (PacketBaseScreen._rx_docs/_rx_doc_all) - keeps a long
    # operating day from growing memory without bound. 5000 matches the
    # spec's own suggested default.
    rx_max_lines_per_channel: int = 5000


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
    mid:       int   = 0
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

    # -- Local archive (PC side, P38) --------------------------------
    # These never go to the TNC (UPLOAD_EXEMPT in
    # test_param_dialogs_roundtrip.py) - they only control PK232PY's own
    # local copy of MailDrop messages. This package (P38) builds only the
    # storage and these settings, no session-mask wiring yet - see
    # maildrop/archive.py and docs/P38_MailDrop_Archive_Spec.md.
    archive_enabled:       bool = False
    archive_path:          str  = "~/.pk232py/maildrop_archive.db"
    archive_sync:          str  = "manual"          # manual | on_session_end
    archive_restore:       str  = "never"           # never | ask | auto
    archive_restore_scope: str  = "unread"          # all | unread | none


# P79: the settings every theme keeps for itself.
APPEARANCE_OVERRIDE_KEYS = ("font_family", "font_size", "bg_color", "fg_color",
                            "rx_color", "tx_color")


@dataclass
class AppearanceConfig:
    """Display appearance settings.

    P79: every theme has its OWN font, colours and RX/TX colours. ``overrides``
    holds, per theme key ("dark"/"mono"/"retro"/"air"/"custom"), only the
    DEVIATIONS from that theme's defaults. The single fields below
    (font_family ... tx_color) stay the EFFECTIVE values of the current
    ``theme`` - every reader keeps using them - and are computed in ONE place,
    effective(): default of the theme, overlaid by its override.
    The defaults of the fields match the Dark theme.
    """
    theme:        str  = "dark"
    font_family:  str  = "Cascadia Mono SemiBold"
    font_size:    int  = 14
    bg_color:     str  = "#1e1e1e"   # RX/TX display background
    fg_color:     str  = "#ffffff"   # RX/TX display foreground
    # P77: the ONE source of the text colours of every display (RX windows, TX
    # input, verbose terminal, Packet channels, MON). rx = received text / TNC
    # output, tx = typed text / own commands.
    rx_color:     str  = "#88ccff"
    tx_color:     str  = "#ffee88"
    # P76: ring a bell when a connection is established (Configure ->
    # Appearance -> Connect bell). On by default; a missing INI key = on.
    connect_bell: bool = True
    # P79: theme key -> {field: value}, only values that differ from the default.
    overrides:    dict = field(default_factory=dict)

    @staticmethod
    def defaults(theme: str) -> dict:
        """The preset values of *theme* (an unknown key counts as Dark)."""
        family, size, bg, fg = THEME_DISPLAY.get(theme, THEME_DISPLAY["dark"])
        rx, tx = THEME_TEXT_COLORS.get(theme, THEME_TEXT_COLORS["dark"])
        return {"font_family": family, "font_size": size, "bg_color": bg,
                "fg_color": fg, "rx_color": rx, "tx_color": tx}

    def effective(self, theme: str) -> dict:
        """THE place where default and override meet: default(theme) + overrides[theme]."""
        values = self.defaults(theme)
        values.update(self.overrides.get(theme, {}))
        return values

    def load_effective(self) -> None:
        """Copy effective(self.theme) into the single fields."""
        for key, value in self.effective(self.theme).items():
            setattr(self, key, value)

    def store_overrides(self) -> None:
        """Remember the single fields as the override of the CURRENT theme:
        only values that differ from the default are kept, so an override
        equal to the default disappears (no dead overrides)."""
        defaults = self.defaults(self.theme)
        diff = {k: getattr(self, k) for k in APPEARANCE_OVERRIDE_KEYS
                if getattr(self, k) != defaults[k]}
        if diff:
            self.overrides[self.theme] = diff
        else:
            self.overrides.pop(self.theme, None)

    def switch_theme(self, theme: str) -> None:
        """Make *theme* current: keep what the old theme was edited to, then
        restore the new theme's own settings."""
        self.store_overrides()
        self.theme = theme
        self.load_effective()

    def clear_overrides(self, theme: str | None = None) -> None:
        """Forget the overrides of *theme* (default: the current one)."""
        self.overrides.pop(theme or self.theme, None)


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

    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            env_path = os.environ.get(CONFIG_PATH_ENV_VAR)
            path = Path(env_path) if env_path else CONFIG_FILE
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
        hf.users     = s.getint("users",     hf.users)
        hf.txsmt     = s.getint("txsmt",     hf.txsmt)
        hf.vhf_maxframe = s.getint("vhf_maxframe", hf.vhf_maxframe)
        hf.vhf_slottime = s.getint("vhf_slottime", hf.vhf_slottime)
        hf.ax25l2v2  = s.getboolean("ax25l2v2",  hf.ax25l2v2)
        hf.headerln  = s.getboolean("headerln",  hf.headerln)
        hf.constamp  = s.getboolean("constamp",  hf.constamp)
        hf.dagstamp  = s.getboolean("dagstamp",  hf.dagstamp)
        hf.ilfpack   = s.getboolean("ilfpack",   hf.ilfpack)
        # Read the old "aerpack" key as a fallback for INI files written
        # before the ACRPACK rename (P13); only "acrpack" is ever written.
        hf.acrpack   = s.getboolean("acrpack",   s.getboolean("aerpack", hf.acrpack))
        hf.alfpack   = s.getboolean("alfpack",   hf.alfpack)
        hf.mrpt      = s.getboolean("mrpt",      hf.mrpt)
        hf.ppersist  = s.getboolean("ppersist",  hf.ppersist)
        hf.xmitok    = s.getboolean("xmitok",    hf.xmitok)
        hf.cfrom_mode  = s.get("cfrom_mode",  hf.cfrom_mode)
        hf.cfrom_calls = s.get("cfrom_calls", hf.cfrom_calls)
        hf.dfrom_mode  = s.get("dfrom_mode",  hf.dfrom_mode)
        hf.dfrom_calls = s.get("dfrom_calls", hf.dfrom_calls)
        hf.mfrom_mode  = s.get("mfrom_mode",  hf.mfrom_mode)
        hf.mfrom_calls = s.get("mfrom_calls", hf.mfrom_calls)
        hf.mto_mode    = s.get("mto_mode",    hf.mto_mode)
        hf.mto_calls   = s.get("mto_calls",   hf.mto_calls)
        hf.bitconv8  = s.getboolean("bitconv8", hf.bitconv8)
        hf.hid       = s.getboolean("hid",      hf.hid)
        hf.mbell     = s.getboolean("mbell",    hf.mbell)
        hf.mdigi     = s.getboolean("mdigi",    hf.mdigi)
        hf.mproto    = s.getboolean("mproto",   hf.mproto)
        hf.mstamp    = s.getboolean("mstamp",   hf.mstamp)
        hf.passall   = s.getboolean("passall",  hf.passall)
        hf.bbsmsgs   = s.getboolean("bbsmsgs",  hf.bbsmsgs)
        hf.ubit0     = s.getboolean("ubit0",    hf.ubit0)
        hf.show_link_messages_in_ui_channel = s.getboolean(
            "show_link_messages_in_ui_channel",
            hf.show_link_messages_in_ui_channel,
        )
        hf.show_timestamps = s.getboolean(
            "show_timestamps", hf.show_timestamps
        )
        hf.rx_max_lines_per_channel = s.getint(
            "rx_max_lines_per_channel", hf.rx_max_lines_per_channel
        )

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
            "users":    str(hf.users),
            "txsmt":    str(hf.txsmt),
            "vhf_maxframe": str(hf.vhf_maxframe),
            "vhf_slottime": str(hf.vhf_slottime),
            "ax25l2v2": str(hf.ax25l2v2).lower(),
            "headerln": str(hf.headerln).lower(),
            "constamp": str(hf.constamp).lower(),
            "dagstamp": str(hf.dagstamp).lower(),
            "ilfpack":  str(hf.ilfpack).lower(),
            "acrpack":  str(hf.acrpack).lower(),
            "alfpack":  str(hf.alfpack).lower(),
            "mrpt":     str(hf.mrpt).lower(),
            "ppersist": str(hf.ppersist).lower(),
            "xmitok":   str(hf.xmitok).lower(),
            "cfrom_mode":  hf.cfrom_mode,
            "cfrom_calls": hf.cfrom_calls,
            "dfrom_mode":  hf.dfrom_mode,
            "dfrom_calls": hf.dfrom_calls,
            "mfrom_mode":  hf.mfrom_mode,
            "mfrom_calls": hf.mfrom_calls,
            "mto_mode":    hf.mto_mode,
            "mto_calls":   hf.mto_calls,
            "bitconv8": str(hf.bitconv8).lower(),
            "hid":      str(hf.hid).lower(),
            "mbell":    str(hf.mbell).lower(),
            "mdigi":    str(hf.mdigi).lower(),
            "mproto":   str(hf.mproto).lower(),
            "mstamp":   str(hf.mstamp).lower(),
            "passall":  str(hf.passall).lower(),
            "bbsmsgs":  str(hf.bbsmsgs).lower(),
            "ubit0":    str(hf.ubit0).lower(),
            "show_link_messages_in_ui_channel":
                str(hf.show_link_messages_in_ui_channel).lower(),
            "show_timestamps": str(hf.show_timestamps).lower(),
            "rx_max_lines_per_channel": str(hf.rx_max_lines_per_channel),
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
        b.mid      = s.getint("mid",      b.mid)
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
        d.archive_enabled       = s.getboolean("archive_enabled",       d.archive_enabled)
        d.archive_path          = s.get("archive_path",                 d.archive_path)
        d.archive_sync          = s.get("archive_sync",                 d.archive_sync)
        d.archive_restore       = s.get("archive_restore",              d.archive_restore)
        d.archive_restore_scope = s.get("archive_restore_scope",        d.archive_restore_scope)

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
            "mid": str(b.mid),
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
            "archive_enabled": str(d.archive_enabled).lower(),
            "archive_path": d.archive_path,
            "archive_sync": d.archive_sync,
            "archive_restore": d.archive_restore,
            "archive_restore_scope": d.archive_restore_scope,
        }

    def _apply_appearance(self) -> None:
        if not self._config.has_section("Appearance"):
            return
        s = self._config["Appearance"]
        a = self.app.appearance
        a.theme        = s.get("theme", a.theme)
        a.connect_bell = s.getboolean("connect_bell", a.connect_bell)
        a.overrides    = {}

        # P79 migration: before, [Appearance] held ONE set of values. Whatever
        # deviates from the stored theme's default becomes that theme's override
        # (theme = custom -> slot "custom"); the old keys are never written again.
        defaults = a.defaults(a.theme)
        legacy = {}
        for key in APPEARANCE_OVERRIDE_KEYS:
            if key in s:
                value = self._typed_appearance_value(key, s[key])
                if value is not None and value != defaults[key]:
                    legacy[key] = value
        if legacy:
            a.overrides[a.theme] = legacy

        # One section per theme with overrides: [Appearance.air] ...
        for name in self._config.sections():
            if not name.startswith("Appearance."):
                continue
            theme = name.split(".", 1)[1]
            found = {}
            for key in APPEARANCE_OVERRIDE_KEYS:
                if key in self._config[name]:
                    value = self._typed_appearance_value(key, self._config[name][key])
                    if value is not None:
                        found[key] = value
            if found:
                a.overrides.setdefault(theme, {}).update(found)

        a.load_effective()

    @staticmethod
    def _typed_appearance_value(key: str, raw: str):
        """INI text -> field type; None for an unreadable value (ignored)."""
        if key == "font_size":
            try:
                return int(raw)
            except ValueError:
                return None
        return raw

    def _build_appearance(self) -> None:
        a = self.app.appearance
        a.store_overrides()            # the single fields are the current theme's truth
        for name in [n for n in self._config.sections() if n.startswith("Appearance.")]:
            self._config.remove_section(name)      # no stale theme sections
        self._config["Appearance"] = {
            "theme":        a.theme,
            "connect_bell": str(a.connect_bell).lower(),
        }
        for theme, values in a.overrides.items():
            if values:
                self._config[f"Appearance.{theme}"] = {
                    k: str(v) for k, v in values.items()}
