# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.

"""Configuration management — reads and writes pk232py.ini."""

from __future__ import annotations

import configparser
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_FILE = Path.home() / ".pk232py" / "pk232py.ini"


@dataclass
class TNCConfig:
    """TNC connection and initialisation settings."""

    model: str = "PK232MBX"
    port: str = ""
    tbaud: int = 9600
    host_mode_on_exit: bool = True
    utc_time: bool = True
    fast_init: bool = True
    echo_packets: bool = False
    save_restore_maildrop: bool = False
    dumb_term_init: bool = False
    show_unknown_cmd_errors: bool = True
    show_not_while_connected_errors: bool = False
    auto_qso_check: bool = False


@dataclass
class HFPacketConfig:
    """HF Packet operating parameters."""

    mycall: str = "NOCALL"
    paclen: int = 64
    txdelay: int = 30
    maxframe: int = 1
    frack: int = 7
    retry: int = 10
    persist: int = 63
    slottime: int = 30
    monitor: int = 4
    # Boolean flags
    ax25l2v2: bool = True
    headerln: bool = True
    constamp: bool = True
    dagstamp: bool = True
    ilfpack: bool = True
    aerpack: bool = True
    alfpack: bool = True
    mrpt: bool = True
    ppersist: bool = True
    xmitok: bool = True


@dataclass
class PACTORConfig:
    """PACTOR operating parameters."""

    myptcall: str = "NOCALL"
    pt200: bool = True
    ptdown: int = 6
    ptup: int = 3
    pthuff: int = 0
    ptsend: float = 1.2
    ptsum: int = 5
    pttries: int = 2
    arqtmo: int = 60
    adelay: int = 2
    xmitok: bool = True
    ptround: bool = False


@dataclass
class AppConfig:
    """Top-level application configuration."""

    tnc: TNCConfig = field(default_factory=TNCConfig)
    hf_packet: HFPacketConfig = field(default_factory=HFPacketConfig)
    pactor: PACTORConfig = field(default_factory=PACTORConfig)


class ConfigManager:
    """Reads and writes the INI configuration file."""

    def __init__(self, path: Path = CONFIG_FILE) -> None:
        self._path = path
        self._config = configparser.ConfigParser()
        self.app = AppConfig()

    def load(self) -> None:
        """Load configuration from file. Missing file → use defaults."""
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
        with open(self._path, "w", encoding="utf-8") as f:
            self._config.write(f)
        logger.info("Configuration saved to %s", self._path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply(self) -> None:
        """Map INI sections → dataclass fields."""
        tnc = self.app.tnc
        if self._config.has_section("TNC"):
            s = self._config["TNC"]
            tnc.model = s.get("model", tnc.model)
            tnc.port = s.get("port", tnc.port)
            tnc.tbaud = s.getint("tbaud", tnc.tbaud)
            tnc.host_mode_on_exit = s.getboolean("host_mode_on_exit", tnc.host_mode_on_exit)
            tnc.utc_time = s.getboolean("utc_time", tnc.utc_time)
            tnc.fast_init = s.getboolean("fast_init", tnc.fast_init)

        hf = self.app.hf_packet
        if self._config.has_section("HF_Packet"):
            s = self._config["HF_Packet"]
            hf.mycall = s.get("mycall", hf.mycall)
            hf.paclen = s.getint("paclen", hf.paclen)
            hf.txdelay = s.getint("txdelay", hf.txdelay)
            hf.maxframe = s.getint("maxframe", hf.maxframe)
            hf.frack = s.getint("frack", hf.frack)
            hf.retry = s.getint("retry", hf.retry)

        pt = self.app.pactor
        if self._config.has_section("PACTOR"):
            s = self._config["PACTOR"]
            pt.myptcall = s.get("myptcall", pt.myptcall)
            pt.pt200 = s.getboolean("pt200", pt.pt200)
            pt.arqtmo = s.getint("arqtmo", pt.arqtmo)

    def _build(self) -> None:
        """Map dataclass fields → INI sections."""
        tnc = self.app.tnc
        self._config["TNC"] = {
            "model": tnc.model,
            "port": tnc.port,
            "tbaud": str(tnc.tbaud),
            "host_mode_on_exit": str(tnc.host_mode_on_exit).lower(),
            "utc_time": str(tnc.utc_time).lower(),
            "fast_init": str(tnc.fast_init).lower(),
        }
        hf = self.app.hf_packet
        self._config["HF_Packet"] = {
            "mycall": hf.mycall,
            "paclen": str(hf.paclen),
            "txdelay": str(hf.txdelay),
            "maxframe": str(hf.maxframe),
            "frack": str(hf.frack),
            "retry": str(hf.retry),
        }
        pt = self.app.pactor
        self._config["PACTOR"] = {
            "myptcall": pt.myptcall,
            "pt200": str(pt.pt200).lower(),
            "arqtmo": str(pt.arqtmo),
        }
