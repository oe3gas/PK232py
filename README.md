# PK232PY

[![CI](https://github.com/OE3GAS/pk232py/actions/workflows/ci.yml/badge.svg)](https://github.com/OE3GAS/pk232py/actions)
[![PyPI version](https://badge.fury.io/py/pk232py.svg)](https://badge.fury.io/py/pk232py)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: GPL v2](https://img.shields.io/badge/License-GPL_v2-blue.svg)](https://www.gnu.org/licenses/old-licenses/gpl-2.0.en.html)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)](https://github.com/OE3GAS/pk232py)

**PK232PY** is a modern, cross-platform multimode terminal program for the
**AEA PK-232 / PK-232MBX** Terminal Node Controller (TNC). It offers functionality 
of the well known legacy PCPackRatt software which no longer runs on 64-bit Windows 10/11 or Linux,
and implements the full AEA Host Mode protocol stack in Python.
The Host Mode is the hidden gem in the PK232, which enables a higher performance in working with the
TNC, hence there is a continous communication between TNC and host. Aside from the possibilities 
provided by modern software development and programming languages, the PK232 still offers great 
performance as specialized appliance for classic digital modes such as RTTY (Baudot/ASCII) and AMTOR (ARQ/FEC). 
It also offers a build in signal analysis option which works well on RTTY signals.
With this project I hope to support a revival of the PK232 (MBX) on the bands.


> **Status:** Pre-Alpha — active development. Not yet suitable for production use.

---

## Features

- Full **AEA Host Mode** implementation (firmware v7.0 / v7.1 / v7.2)
- Supported operating modes:
  - HF Packet (AX.25, 300 Bd) and VHF Packet (1200 Bd)
  - PACTOR I (ARQ)
  - AMTOR (ARQ + FEC/SELFEC)
  - Baudot/RTTY, ASCII-RTTY
  - CW / Morse
  - NAVTEX receive
  - TDM, FAX receive, Signal Analysis (SIAM)
- MailDrop management
- QSO logging
- Macro system
- Modern PyQt6 GUI with MDI windowing
- Cross-platform: **Windows 10/11**, **Linux**, **macOS**

## Supported Hardware

| Model | Firmware | Support |
|-------|----------|---------|
| AEA PK-232MBX | v7.1 (Sep 1995) | ✅ Primary reference |
| AEA PK-232MBX | v7.2 (Aug 1998) | ✅ Supported |
| AEA PK-232MBX | v7.0 | ✅ Supported |
| AEA PK-232 (non-MBX) | any | ⚠️ Limited (no PACTOR/MailDrop) |

> **Not supported:** PK-232SC, PK-232SC+ (different firmware architecture)

---

## Installation

### From PyPI (recommended)

```bash
pip install pk232py
pk232py
```

### From source

```bash
git clone https://github.com/OE3GAS/pk232py.git
cd pk232py
pip install -e ".[dev]"
pk232py
```

### Requirements

- Python 3.10 or newer
- PyQt6
- pyserial
- A USB-to-serial adapter if your PC has no RS-232 port
  (the PK-232 requires 9600 baud, 7E1 for firmware v7.x)

---

## Quick Start

1. Connect your PK-232MBX to a serial port (or USB-serial adapter)
2. Launch PK232PY: `pk232py`
3. Go to **Configure → TNC Configuration**
4. Select TNC Model: `PK232MBX`, set your COM port and baud rate
5. Click **OK** — the program will initialise the TNC and enter Host Mode
6. Set your callsign via **Parameters → HF Packet Params → MGCALL**
7. Select an operating mode and start working!

---

## Development Setup

```bash
git clone https://github.com/OE3GAS/pk232py.git
cd pk232py
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
.venv\Scripts\activate           # Windows
pip install -e ".[dev]"
pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to contribute.

---

## Project Structure

```
pk232py/
├── src/pk232py/
│   ├── comm/          # Serial port, Host Mode protocol, KISS
│   ├── modes/         # Operating modes (Packet, PACTOR, AMTOR, ...)
│   ├── ui/            # PyQt6 GUI (main window, dialogs, widgets)
│   ├── maildrop/      # MailDrop controller and message store
│   ├── log/           # QSO log
│   ├── macros/        # Macro system
│   └── tests/         # Unit tests
├── pyproject.toml
├── CHANGELOG.md
├── CONTRIBUTING.md
└── LICENSE
```

---

## Roadmap

| Version | Milestone |
|---------|-----------|
| v0.1 | Serial connection, Host Mode protocol, basic terminal window |
| v0.2 | HF/VHF Packet, parameter dialogs, monitor window |
| v0.3 | PACTOR I, AMTOR, Baudot/ASCII RTTY |
| v0.5 | MailDrop, macros, QSO log, full menu structure |
| v0.8 | CW/Morse, NAVTEX, Windows + Linux installer |
| v1.0 | TDM, FAX, signal analysis, full documentation |

---

## Contributing

Contributions are very welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md)
before submitting a pull request. If you own a PK-232 / PK-232MBX and can help
with testing, please open an issue — testers are especially needed!

## License

PK232PY is free software: you can redistribute it and/or modify it under the
terms of the **GNU General Public License version 2** as published by the
Free Software Foundation.

See [LICENSE](LICENSE) for the full license text.

---

## Background

The AEA PK-232MBX is a legendary multi-mode TNC from the late 1980s/early 1990s.
Thousands of units are still in the hands of amateur radio operators worldwide.
The only software that ever supported its full Host Mode capability — PCPackRatt
for Windows — is a 32-bit Windows XP-era application that no longer runs on
modern 64-bit operating systems, and has never been available for Linux or macOS.

PK232PY aims to fill that gap.

---

*73 de OE3GAS*
