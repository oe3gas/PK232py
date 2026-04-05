# Changelog

All notable changes to PK232PY will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- Initial project structure
- `pyproject.toml` packaging configuration
- Repository skeleton with `src/` layout

---

## [0.1.0] - TBD

### Added
- Serial port connection management (`comm/serial_port.py`)
- AEA Host Mode protocol framing (`comm/hostmode.py`)
- Autobaud detection (`comm/autobaud.py`)
- KISS mode support (`comm/kiss.py`)
- Basic terminal window (PyQt6)
- TNC Configuration dialog
- Firmware version detection from startup message
- `RESTART` / `RESET` command support

---

[Unreleased]: https://github.com/OE3GAS/pk232py/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/OE3GAS/pk232py/releases/tag/v0.1.0
