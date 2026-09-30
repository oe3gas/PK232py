# tools/

Development and test tooling for PK232PY. **These tools are not part of the
shipped application** and may carry their own licences (see the table below).

## Tools

| File | Purpose | Licence |
|------|---------|---------|
| `fax_wav_generator.py` | Generates three WEFAX test WAVs (weather chart, geometry/resolution pattern, Arial-16 pt text page) for closed-loop FAX decode testing without hardware. | GPL v2 (project) |
| `make_synthetic_weatherchart.py` | Deterministically generates `synthetic_weatherchart.png` (1152×600, copyright-free) — the committed weather-chart fixture used by `fax_wav_generator.py` for T66. Replaces the copyrighted DWD chart. | GPL v2 (project) |
| `fax_decoder_test.py` | Standalone WEFAX audio decoder (PyQt6 GUI + live audio) used ONLY to verify generated WAVs. Never integrated into pk232py. | GPL v3 (ported from weatherfax_pi) |
| `mock_tnc_bbs.py` | In-process mock PK-232 running a mini-BBS. Launches the real app with a `LoopbackTNC` injected in place of the serial port, so the Packet *connected* mode (T33–T39) can be exercised with no TNC, radio or second station. `python tools/mock_tnc_bbs.py [--trace]`. | GPL v2 (project) |
| `hw_check.py` | Solo hardware verification against a REAL PK-232MBX (P14 and onward) — one subcommand per measurement (`t17`, `t111`, `t112`, `maildrop`, `aprs_query`, `link_carry`, ...). MEASURES ONLY (never fixes/changes production code); `--dry-run` opens no port and never sends. See the module's own docstring for the full subcommand list — `aprs_query`/`aprs_tx`/`aprs_reject` (P62) measure UNPROTO/CFROM and the future APRS mode's Host Mode frames; `link_carry`/`link_carry_host` (P65) measure whether an AX.25 Packet connection and the active operating mode survive the verbose↔Host Mode switch; `channel_probe` (P69) measures Unproto on free channels 3/9 and which channel an incoming connect lands on (needs Direwolf + QtTermTCP); `aprs_tx`/`aprs_reject`/`link_carry`/`link_carry_host`/`channel_probe` transmit or need a second station and are therefore never part of `all`. | GPL v2 (project) |

## Scope / licence note

PK232PY **never decodes FAX audio itself.** In real operation the AEA
PK-232MBX performs the FAX demodulation in hardware and delivers ready-made
pixel bytes (Epson ESC L column format) to pk232py over Host Mode. The
application only renders those pixels.

These tools are therefore pure **test scaffolding** for a closed loop
(`fax_wav_generator.py` → WAV → `fax_decoder_test.py`), exercised without any
TNC, radio or live audio.

`mock_tnc_bbs.py` is likewise **dev-only test scaffolding** and is never
shipped. It duck-types `serial.Serial` with a synchronous in-process
`LoopbackTNC` (no threads/queues — it *is* the port, so CLAUDE.md §3 holds) and
is plugged in through `SerialManager.set_port_factory()`, a generic seam that
defaults to the real `serial.Serial`. Production code never imports `tools/`.
It is GPL v2 because it imports the project's GPL-v2 comm layer.

Because `fax_decoder_test.py` ports DSP algorithms from the GPL-v3
[weatherfax_pi](https://github.com/seandepagnier/weatherfax_pi) project, it is
itself GPL v3. This is **uncritical**: it is a separate standalone tool and is
never linked into or shipped with the GPL-v2 main application, so there is no
licence conflict. (Were it ever reused inside pk232py — it will not be — the
project licence would have to be relaxed to "GPL v2 or later".)

## channel_probe - what you do where

Two PCs: **PC 1** runs `hw_check.py` with the PK-232 (Device B) at the
TS-790E; **PC 2** runs Direwolf (FT-818), the TinyBox `OE3GAS-1` and
QtTermTCP. Every step prints `STEP n of N`, `WHERE`, `DO`, `THEN`.

```bash
python tools/hw_check.py --port COM6 channel_probe --part B   # T146, 4 steps, ~9 min
python tools/hw_check.py --port COM6 channel_probe --part C   # T147, 11 steps, ~15 min
python tools/hw_check.py --port COM6 channel_probe            # both, 15 steps
python tools/hw_check.py --dry-run channel_probe --part C     # shows every step, sends nothing
```

**Part B (T146)** - all transmissions first, ONE decoder paste at the end:

| Step | Where | What |
|---|---|---|
| B.1 | PC 1 | answer y: UNPROTO frame on free channel 3 |
| B.2 | PC 1 | answer y: UNPROTO frame on free channel 9 |
| B.3 | PC 1 | answer y: connect ch0 to the TinyBox, frame on ch3, CR on ch0, disconnect |
| B.4 | PC 2 -> PC 1 | copy the Direwolf window from the line with `P69 B1` to the end, paste on PC 1, finish with a line `.` |

**Part C (T147)** - no countdown: recording runs from before the
instruction until you press ENTER on PC 1 (or 120 s):

| Step | Where | What |
|---|---|---|
| C.1 call / what QtTermTCP shows | PC 2 | session `OE3GAS-2` connects to the TNC; note connected / busy / nothing |
| C.2 occupy / call / what QtTermTCP shows | PC 1, PC 2, PC 2 | TNC ch0 connects to the TinyBox; session `OE3GAS-3` calls |
| C.3 free both sessions | PC 2 | disconnect `OE3GAS-2` and `OE3GAS-3` in QtTermTCP |
| C.3.1, C.3.2 | as C.1, C.2 | same again with `USERS 10` |

Ctrl-C at any point restores UNPROTO/USERS/VHF/HBAUD, disconnects channels
still connected (asks first) and prints `Stopped at STEP n of N (...). Next
run: --part X`.

## Usage

Run from the repository root:

```bash
python tools/make_synthetic_weatherchart.py  # (re)generate the chart fixture PNG
python tools/fax_wav_generator.py             # generates the 3 test WAVs
python tools/fax_decoder_test.py [wav]        # GUI; optional WAV path as argument
python tools/mock_tnc_bbs.py [--trace]        # launch app against a mock PK-232 + BBS
```

For the mock: start it, in the app choose **Connect (Host)** with port **MOCK**,
switch to a **Packet** screen and **Connect** to e.g. `OE1XYZ`, then type
`L` / `R 2` / `D`. `--trace` logs every frame in/out to stderr.

The generated WAVs are gitignored (regenerable artefacts). The synthetic chart
PNG **is** committed (it is the reproducible T66 fixture). The copyrighted DWD
charts (`Wetterkarte*.jpg`, `wetterkarte_decoded.png`) are gitignored and must
never be committed.
