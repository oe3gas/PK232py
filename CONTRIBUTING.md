# Contributing to PK232PY

Thank you for your interest in contributing to PK232PY! This document explains
how to get involved.

---

## Ways to Contribute

- **Bug reports** — open an issue using the Bug Report template
- **Feature requests** — open an issue using the Feature Request template
- **Code contributions** — submit a pull request (see below)
- **Hardware testing** — test with your PK-232 / PK-232MBX and report results
- **Documentation** — improve the wiki, README, or code comments
- **Translations** — help translate the UI (Qt `.ts` files)

---

## Hardware Testers Needed

PK232PY is especially looking for testers who own:

- AEA PK-232MBX (any firmware version)
- AEA PK-232 (non-MBX, firmware v7.0+)

If you can test and report results, please open an issue with label `hardware-test`.

---

## Development Workflow

### 1. Fork and clone

```bash
git clone https://github.com/YOUR_USERNAME/pk232py.git
cd pk232py
```

### 2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate    # Linux/macOS
.venv\Scripts\activate       # Windows
pip install -e ".[dev]"
```

### 3. Create a feature branch

```bash
git checkout -b feature/my-feature-name
# or
git checkout -b fix/issue-123-description
```

Branch naming convention:
- `feature/` — new functionality
- `fix/` — bug fixes
- `docs/` — documentation only
- `refactor/` — code refactoring without behaviour change
- `test/` — adding or improving tests

### 4. Make your changes

- Follow the code style (see below)
- Add or update tests for your changes
- Update documentation if needed

### 5. Run tests

```bash
pytest
```

All tests must pass before submitting a pull request.

### 6. Submit a pull request

- Target the `main` branch
- Write a clear PR description explaining what and why
- Reference any related issues (`Closes #123`)

---

## Code Style

- **Formatter:** `black` with line length 100
- **Linter:** `ruff`
- **Type hints:** encouraged, required for public APIs
- **Docstrings:** Google style

Run before committing:
```bash
black src/
ruff check src/
```

---

## Commit Messages

Follow the [Conventional Commits](https://www.conventionalcommits.org/) format:

```
type(scope): short description

Longer explanation if needed.

Closes #123
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

Examples:
```
feat(hostmode): implement CONNECT/DISCONNECT frame parsing
fix(serial): handle port not found on Windows
docs(readme): add hardware compatibility table
test(packet): add unit tests for AX.25 frame decoder
```

---

## Adding a New Operating Mode

1. Create `src/pk232py/modes/your_mode.py`
2. Subclass `BaseMode` from `modes/base_mode.py`
3. Implement the required abstract methods
4. Register the mode in `modes/__init__.py`
5. Add the corresponding parameter dialog in `ui/dialogs/`
6. Add tests in `tests/test_modes.py`

---

## Reporting Bugs

Please include:
- Operating system and version
- Python version (`python --version`)
- PK232PY version
- TNC model and firmware version (shown at startup: `Release DD-MM-YY`)
- Serial port and baud rate used
- Steps to reproduce
- Full error message / traceback

---

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md).
By participating, you agree to abide by its terms.

---

## License

By contributing to PK232PY, you agree that your contributions will be licensed
under the GNU General Public License v2.
