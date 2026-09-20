# CLAUDE.md — PK232PY Project Context

> This file is the single entry point for Claude Code to understand the
> PK232PY project. Read it completely before touching any source file.
> Last updated: 2026-09-20

---

## Project Name

**PK232PY** — A modern Python/PyQt6 terminal application for controlling an
AEA PK-232MBX multi-mode TNC (Terminal Node Controller) for amateur radio
digital mode operation.

- Repository: `github.com/oe3gas/PK232py`
- Local path: `E:\PK232\pk232py_repo`
- License: GPL v2
- Developer: OE3GAS (Gerhard)

---

## Purpose

PCPackRatt (the original Windows 9x software for the PK-232MBX) is no longer
maintained and barely runs on modern Windows. PK232PY replaces it with a clean
PyQt6 desktop application that supports all operating modes of the PK-232MBX:
Baudot RTTY, ASCII RTTY, AMTOR, CW/Morse, PACTOR I, NAVTEX, Signal/SIAM,
HF FAX, HF Packet (AX.25), and VHF Packet (AX.25/APRS).

Target milestone: **Beta release**.

---

## Current Status (v16 — 2026-06-16)

### What is done

All 10 opmode screens are implemented and integrated into `MainWindow` via
`QStackedWidget`:

| Screen        | File                    | TX | Macros | Notes                       |
|---------------|-------------------------|----|--------|-----------------------------|
| Baudot RTTY   | `baudot_screen.py`      | ✓  | ✓      | ITA-2, 5-bit, full TX ctrl  |
| ASCII RTTY    | `ascii_screen.py`       | ✓  | ✓      | 7-bit                       |
| AMTOR         | `amtor_screen.py`       | ✓  | ✓      | ARQ + FEC/SELFEC             |
| CW / Morse    | `morse_screen.py`       | ✓  | ✓      | 5–99 WPM                    |
| PACTOR I      | `pactor_screen.py`      | ✓  | ✓      | ARQ + FEC/Unproto            |
| NAVTEX        | `navtex_screen.py`      | —  | —      | Receive only                |
| Signal/SIAM   | `signal_screen.py`      | —  | —      | Receive only                |
| HF FAX        | `fax_screen.py`         | —  | —      | Receive only, image display |
| HF Packet     | `packet_screen.py`      | ✓  | —      | AX.25, APRS decode          |
| VHF Packet    | `packet_screen.py`      | ✓  | —      | AX.25, APRS, MHEARD panel   |

### Active/recently completed work

- **Packet channel model / ChannelBar sprint (2026-09-20, software/headless-
  verified):** `ChannelBar` (10-chip multi-channel selector), `cb_dest`
  history combo (replaces `le_dest` on Packet screens only), ALL/CH RX
  filtering, Capture, MHEARD channel column, `HFPacketMode.on_channel_state`.
  MainWindow's Packet connect/disconnect/TX no longer hardcode channel 1. See
  §"Channel model" under Known Gotchas / Packet, and Backlog.md's "Completed
  (2026-09-20 — Packet channel model / ChannelBar sprint)" block.
- PACTOR capability detection: `b"PACTOR"` in boot banner → `SerialManager.has_pactor = True`
- `write_verbose_wait()` race condition fixed: 120 ms idle detection (`_IDLE_S = 0.12`)
- APRS decoder: Mic-E, Position, Telemetry, Weather (T# / WX chips confirmed OK)
- RTTY TX fully reimplemented with `char_ready = pyqtSignal(str)` in `RttyBaseScreen`
- `ScreenFocusController`: installed on individual QLineEdit fields (le_dest, le_unproto)
- Identity fields (`lbl_mycall`, `lbl_myptcall`, etc.) are QLabel, not QLineEdit
- Clear TX / Clear RX buttons on all opmode screens (TX-capable: `clear_tx_req`/
  `clear_rx_req` signal pattern wired by `MainWindow`; receive-only Signal/NAVTEX:
  local Clear RX slot; FAX: local "Clear Image" slot)
- **Clear TX clears the *full* TX buffer, not just the screen** (fixed
  2026-06-18): if SEND is active it first sends a mode-appropriate stop command
  (`_CLEAR_TX_STOP_CMD` in `main_window.py`: Baudot/ASCII/Morse → `RC`,
  AMTOR → `AM`) so the TNC aborts/flushes its own keyed TX buffer, then clears
  `_tx_ctrl` + screen and drops the UI to RECEIVE. Frame-based Packet and
  out-of-Host-Mode PACTOR have no keyed buffer → local clear only (no stop cmd).
- FAX closed-loop test tooling under `tools/` (`fax_wav_generator.py` +
  `fax_decoder_test.py`); decoder is test-only and never shipped
- **FAX live image decode implemented (2026-06-18, hardware-verified T82):**
  `EpsonFaxParser` decodes the `$3F` Epson 9-pin printer-graphics stream into
  grayscale rows; display pixel-aspect fix (`PIXEL_ASPECT = 120/72`);
  non-destructive smoothing slider; LOCK (force receive) + Stop (freeze)
  buttons; FAXNEG as display-only invert; `fax_wav_generator.py --target tnc`
  bench WAVs. See §4 and the FAX Gotchas subsection.

### Active/recently completed work (continued)

- **Packet toggle/button sprint T38–T51 done (2026-06-22, frame/code-verified):**
  T38 Unproto UN frame, T39 Connect↔Unproto mutual exclusion (both directions),
  T43 EAS, T44 PASSALL (**mnemonic bugfix `PA`→`PS`** — `PA` is PACKET activation,
  not PASSALL), T45 HBAUD, T46 Monitor, T47 MailDrop, T48/T32 HF+VHF init frames
  (HF now emits `VH N`+`HB 300`+`MN Y`; VHF builds its own list, no HF inherit),
  T49 NoFocus (already correct), T50 fields (already correct), T51 `VH N` on
  leaving VHF Packet. T43/T45/T46/T47 were already implemented. See Backlog.md
  "Completed (2026-06-22 — Sprint T38–T51)" and the Packet Gotchas subsection.
- **Packet MHEARD T41/T42 done (2026-06-22, mock end-to-end):** Refresh polls
  `MH0`..`MH17` line-by-line (TRM §4.11, fire-and-forget) → CMD_RESP `MH` lines
  → `_parse_mheard_line()` → `MheardPanel`; Clear is a local `panel.clear()`.
  See the MHEARD gotcha under "TNC / firmware v7.1".

### Open / next sprint

- ~~Help-System — `help_viewer`, Help-Dateien, Help-Buttons~~ ✅ DONE
  2026-06-22 (Help-System-Sprint; see Backlog.md Completed-Block).
- ~~APRS auf HF-Packet-Screen~~ ✅ DONE 2026-06-22 (`APRS_CAPABLE = True` in
  `HFPacketScreen` — eine Zeile, Decode-Logik bereits mode-agnostisch).
- ~~Help-System Bugfixes (toter `controls`-Anker, fehlende Tooltips,
  Status-Bar-Tooltips, Dead-Code `TNCConfigDialog`)~~ ✅ DONE 2026-06-23
  (Help-Bugfix-Sprint; see Backlog.md Completed-Block).
- 🧹 Cleanup (nicht Beta-kritisch, jederzeit): `main_window.py:4170–4191`
  §10-Append-Artefakt entfernen (No-op-String — siehe Gotcha).
- Offen (Help-System Folge, v0.2): `help_amtor.md` Gegenlesen (CC-Neufassung
  vs. freigegebene Chat-Version); eigene `help_shortcuts.md` / `help_macros.md`
  statt Anchors in `help_baudot.md` (`controls` ist bereits ausgelagert);
  Help-Buttons in Dialogen, Kontext-F1, First-Run-Dialog, Verbose-Terminal-Help.
- Packet hardware re-tests (need a real AX.25 second station): T35/T37
  Connect/Disconnect, T38/T39 mutual exclusion (+interactive mock GUI re-click),
  T41/T42 MHEARD (+live-GUI Refresh click). All software/mock-verified.
- Packet MHEARD: HBAUD-110 mid-poll consistency workaround (v0.2, Backlog).
- PACTOR/AMTOR: identity, focus tests (T52–T58)
- APRS: buffer cleared on mode switch (T65)
- CTRL+D EOT Paket 2b (AMTOR): implementiert (8087564) — Hardware-Test
  T73–T79 ausstehend (T73 CONNECTED-Text zuerst, braucht zweite Station).
- Paket 3 (Stop Sending): ✅ DONE 2026-06-22 (software/mock). RC/AM/none für
  alle Modes verifiziert; AMTOR `_send_active`-Bug gefixt (siehe Gotcha unten).
  TxController-Zyklus Paket 1–3 abgeschlossen. Hardware-Retests T17/T85 (AMTOR
  `AM`-Flush on-air, Morse `RC`-Regression) noch offen.
- Hardware-Test Paket 2a (Morse): T69/T70/T72 ✅ PASS (2026-06-18, inkl.
  Space-Echo + CR/LF-Stall behoben, neuer T80 CR/LF PASS); T71 (Macro [^D])
  noch ausstehend.
- AMTOR TX-Aktivierung: KEIN btn_send / XM-Frame. TxController startet
  wenn `_make_link_handler()` "connected" im Link-Message-Text erkennt
  → `on_send_start()`. CRITICAL: T73 verifiziert, dass der TNC tatsächlich
  diesen Text schickt — falls nicht, `_make_link_handler()` anpassen.

---

## Technology Stack

| Layer | Technology |
|-------|------------|
| Language | Python 3.10+ (CI: 3.10 / 3.11 / 3.12) |
| UI framework | PyQt6 |
| Serial communication | pyserial |
| Config persistence | INI file via `configparser` |
| QSO log | SQLite |
| IDE | VS Code |
| Shell | PowerShell (Windows 11) |
| Version control | Git (branch: main) |
| Virtual environment | venv at repo root |

**Hardware:** AEA PK-232MBX, firmware v7.1 (PACTOR-extended), COM16,
Prolific USB-Serial adapter, 9600 baud.

---

## Repository Structure

```
src/pk232py/
  config.py              AppConfig dataclasses + INI read/write
  main.py                Entry point
  mode_manager.py        Mode switching state machine
  comm/
    constants.py         Protocol magic numbers (SOH / ETB / CTL ranges)
    frame.py             HostFrame model, builder functions, FrameParser
    hostmode.py          High-level Host Mode command API
    serial_manager.py    SerialManager — owns the port + all threads
    pk232_hostmode_sub.py  Subprocess for Host Mode entry
  modes/
    base_mode.py         BaseMode lifecycle contract
    rtty_baudot.py / rtty_ascii.py / amtor.py / morse.py / pactor.py
    navtex.py / signal_analysis.py / fax.py / aprs_decoder.py / maildrop_mode.py
    packet_hf.py / packet_vhf.py
  ui/
    main_window.py       MainWindow — QStackedWidget, menus, mode switching
    screens/
      opmode_rtty_base.py   RttyBaseScreen, MacroStore, theme helpers
      tx_controller.py      TxController — pure ACK-driven TX state machine for
                            character-ACK modes (Baudot, ASCII, Morse, AMTOR ARQ/FEC).
                            Was baudot_tx_controller.py until Paket 1
                            (cc2adff); no serial I/O, no widget refs.
      baudot_screen.py / ascii_screen.py / amtor_screen.py / morse_screen.py
      pactor_screen.py / navtex_screen.py / signal_screen.py / fax_screen.py
      packet_screen.py     PacketBaseScreen + HFPacketScreen + VHFPacketScreen
      screen_focus_controller.py
  help/                  Markdown help files
  log/                   QSO log (SQLite)
  macros/                Macro system
  maildrop/              MailDrop (TNC mailbox)

tools/                   Standalone dev/test tools (NOT part of the shipped app)
  fax_wav_generator.py   WEFAX test-WAV generator (GPL v2)
  fax_decoder_test.py    Standalone WEFAX audio decoder, test-only (GPL v3)
  README.md              Scope + licence note for tools/
```

---

## Important Conventions

### 1. Source of truth

**`pk232py_sources.txt`** (generated by `Sources2Text.ps1`) is the single
authoritative source for all code. All code analysis and verification runs
against this file. Git branch/hash are irrelevant to the working process.

The export now covers `src/pk232py/**/*.py` (production code first) **and**
`tools/**/*.py` (standalone tools, listed after). Markdown is still exported
only from `src/pk232py/help/` — so `tools/README.md` is not included, which
is fine. The project docs (`CLAUDE.md`, `docs/Backlog.md`, `docs/Testplan.md`,
the state-machine `.md` files) are **NOT** in the export — they are uploaded to
the Claude project knowledge separately.

### 2. Workflow

```
1. Discuss + analyse in Claude.ai project context
2. Make file changes directly via Claude Code terminal:
   cd E:\PK232\pk232py_repo  →  claude
3. After changes: run Sources2Text.ps1
4. Upload pk232py_sources.txt to Claude project knowledge
5. Report "sources aktualisiert"
```

No patch scripts. No intermediate copies. One file per module per commit.

### 3. Serial communication — CRITICAL

**ALWAYS use direct serial I/O** (`port.write()` / `read_until()`).
**NEVER use a worker thread or queue for Host Mode frames.**

The Windows Prolific USB driver only delivers ACKs when `read()` is called
directly on the port. Queue/worker delays ACKs until port close.
This is a proven hardware constraint — not negotiable.

**Proof (historical prototypes):** the direct-read approach (`pk232_hostmode.py`)
worked; the worker-queue approach (`baudot_tx_test.py`) did NOT — ACKs only
arrived on port close. These prototypes are not in the repo; the lesson is
baked into `SerialManager` (which owns the port and reads directly). Anyone
who reintroduces a queue/worker for Host Mode frames breaks the ACK path.

After the Host Mode subprocess exits, always create a **fresh `serial.Serial()`
object**. Reusing the old object causes 20–35 second buffering delays.

### 4. TNC Protocol facts (firmware v7.1)

- Commands without PACTOR option → `?What?`: `MYPTCALL`, `PT200`, `PTOVER`,
  `PTHUFF`, `ARQTOL`, `MOPT`, `EXPERT OFF`
- Verbose mode commands require `\r\n` (CR+LF) termination
- Wakeup: single `$2A` (`*`) byte, no CR needed
- Host Mode exit binary sequence: `$01 $4F $48 $4F $4E $17` (NOT text `HOST OFF\r`)
- Both `HP Y` and `HP $00` are valid success responses
- `MOPT` = Morse Option (CW); `ARQTOL` = AMTOR ARQ tolerance
- `PT` mnemonic = PACTIME, not PACTOR. PACTOR activation = verbose `PACTOR\r\n`
- FAX mode stays in Host Mode (FA command); does not exit it — there is **no
  verbose_command path for FAX** (unlike PACTOR, which leaves Host Mode)
- **FAX demodulation is done by the TNC itself:** the PK-232 demodulates the
  FAX audio and streams the image over `$3F` as an **Epson 9-pin
  printer-graphics stream** — `ESC L n_lo n_hi` (double-density bit image,
  `N = n_lo + 256·n_hi` columns, 8 vertical pixels/byte, **D7 = top, bit set =
  black**) plus `ESC A` band separators — NOT a grayscale scan line. The app's
  `EpsonFaxParser` (`modes/fax.py`) decodes this into grayscale rows live
  (hardware-verified, Testplan T82). The `tools/` WEFAX *audio* decoder is a
  separate *closed-loop test* substitute for the TNC's demodulator (generator →
  WAV → decoder, no radio/hardware) and is **never integrated into `pk232py`**
  (it is GPL v3; the app is GPL v2)

### 5. UI conventions

- All UI text in **English**
- `Qt.FocusPolicy.NoFocus` on **all** QPushButtons (never steal TX focus)
- `QTimer.singleShot(0)` for initial TX window focus after widget construction
- Block cursor via `setCursorWidth(averageCharWidth())` in `style_tx_widget()`
- `QTextEdit.insertPlainText()` — not `append()` — for streaming characters
- Filter `\r` characters before display
- Mode name keys in screen dict must exactly match `ModeManager.ALL_MODES` constants
- Identity fields are `QLabel` (not `QLineEdit`), populated from `AppConfig`
- `ScreenFocusController` installed only on editable `QLineEdit` fields

### 6. EventFilter architecture (two levels + controller)

**Level 1 — MainWindow (app-wide):** `QApplication.instance().installEventFilter(self)`
Intercepts all keypresses. Redirects to `tx_input` unless: modal dialog open,
ALT+X/ALT+R shortcut, `screen.focus_ctrl.is_active() == True`, or `obj is tx_input`.

**Level 2 — Opmode screen (widget-scoped):** `self.installEventFilter(self)`
Fallback for cases where Level 1 doesn't redirect. Uses parent-chain walk
because `obj` may be an internal Qt child widget.

**Level 3 — ScreenFocusController:** `QObject` installed directly on individual
QLineEdit fields. Reliable FocusIn/FocusOut tracking at field scope.

*Why field-scoped, not app-wide:* `isinstance(obj, QLineEdit)` in the app-wide
Level-1 filter is unreliable — `obj` may be an internal Qt child widget, not the
QLineEdit itself. Installing the controller directly on each field avoids that.

*Registered fields (editable QLineEdit only):*
- `PactorScreen` → `le_dest`
- `AmtorScreen` → `le_dest`
- `PacketBaseScreen` → `le_dest`, `le_unproto`

QLabel identity fields (`lbl_mycall`, `lbl_myptcall`, …) are display-only and
are **NOT** registered — they are labels, not input fields.

### 7. Opmode switch state machine

Four states: `M0` NO MODE → `M1` ACTIVATING → `M2` ACTIVE → `M3` SWITCHING.
The 300 ms `_ACTIVATE_DELAY_MS` timer fires `_send_init_frames()`.
Path B (PACTOR) temporarily exits Host Mode — see `OPMODE_SWITCH_STATE_MACHINE.md`.

### 8. Connection state machine

Eight states: `C0` OFFLINE → `C1` PORT OPEN → `C2` INITIALISING →
`C3` VERBOSE → `C4` UPLOADING → `C5` SWITCHING → `C6` HOST MODE → `C7` ERROR.
See `SERIAL_CONNECTION_STATE_MACHINE.md` for full detail.

### 9. PACTOR capability detection

`b"PACTOR"` in boot banner → `SerialManager.has_pactor = True`.
Default is `True` when no banner is present (permissive).
When `False`: PACTOR ComboBox and Parameters menu are disabled; upload
commands (`MYPTCALL`, `ARQTOL`, `MOPT`, `EXPERT OFF`, `PTHUFF`, `PT200`,
`PTOVER`) are skipped.

### 10. File encoding

Python-generated files must not be deployed via PowerShell copy
(encoding corruption risk). Use patch scripts with explicit UTF-8 or
Windows `copy` command. `main_window.py` is prone to corruption at ~line 1503
(second file appended) — check for this and delete manually if needed.

### 11. TxController architecture

`TxController` (`tx_controller.py`, renamed from `BaudotTxController` in
Paket 1 / cc2adff) is the **mode-agnostic** ACK-driven TX/RX state machine —
no serial I/O, no widget refs. Key learnings from the 2026-06-16 session:

- `_is_txctrl_mode(mode)` in `main_window.py` is the **single source of truth**
  for which modes are driven by `TxController`. Currently
  `("Baudot RTTY", "ASCII RTTY", "CW / Morse", "AMTOR ARQ", "AMTOR FEC")`
  (Paket 2b / commit 8087564 — AMTOR added 2026-06-16).
- **Morse is echo-paced** (fixed 2026-06-18) — in EAS mode `TxController` hands
  the TNC the next char only after the previous char's `$2F` echo (= keyed on
  air), so the TNC never buffers more than `_EAS_WINDOW` (=1) char ahead.
  *Why:* the old 50 ms timer (`_MORSE_TXCTRL_MS`) dumped the whole message into
  the TNC far faster than it keyed at WPM; the TNC then piled it up in its own
  transmit buffer, which `RC` cannot flush — so Clear TX/RECEIVE looked like it
  worked but the leftover resumed on the next SEND. `_EAS_SAFETY_MS` (=4000) is
  a lost-echo fallback so TX can never lock up. `_MORSE_TXCTRL_MS = 50` is still
  passed via `set_mspeed_ms()` but is unused while EAS is on. Echo-pacing lives
  in `_pump_eas()` / `_emit_to_tnc()` (`tx_controller.py`); non-EAS modes
  (Baudot/ASCII/AMTOR) stay Baud-rate timer-paced, unchanged.
- **EAS echo stream has three character classes** (hardware-verified
  2026-06-18) — Normal and **Space** are keyed and DO send a `$2F` echo (space
  echoes `$2F 0x20`); **Newline** (`\r\n`) is transmitted but NOT keyed and
  sends NO echo, so it is excluded from echo-pacing (`_is_unkeyed`) and skipped
  in `on_echo_char`'s scans (commit 5dce1c0); **Markers** (`\x04`/`\x1b…`) are
  never sent to the TNC. Wrong assumptions caused a +1-per-space offset
  (668c903) then a 4 s-per-char newline stall (5dce1c0). Authoritative table:
  TX_STATE_MACHINE.md §17.2.
- **Lösung-A migration in progress** (colour_at coordinate-mixing bug): Phase 1
  — `doc_pos` capture per `_arr` entry — is committed (5dcaf7e); Phase 2 —
  switching `colour_at` to absolute `doc_pos` and retiring
  `_doc_offset`/`_cycle_start`/`_doc_extra` — is open. See TX_STATE_MACHINE.md §7.3.
- **AMTOR EOT ≠ RC** (verified against the Technical Reference Manual):
  AMTOR-ARQ `[^D]` → PTOVER character `\x1A` (Ctrl-Z) sent into the now-empty
  TX stream — polite ISS↔IRS turnaround, link stays up. NOT the `OV` host
  command (fires immediately, does not wait for buffer drain — TRM p.179).
  AMTOR-FEC `[^D]` → `on_send_stop()` (no connection concept, no TNC command).
  ARQ vs FEC derived from `btn_fec.isChecked()` / `btn_selfec.isChecked()` —
  NEVER from `mode.name` (ModeManager only ever produces "AMTOR ARQ").
- **Packet uses NO TxController and NO `[^D]`.** AX.25 packetises at the ETB
  character and has no character-by-character ACK, so the EOT-marker concept
  does not fit. Packet needs a Stop-button instead of an EOT marker.
- **Stop Sending** (Paket 3, ✅ DONE 2026-06-22, software/mock): AMTOR → `AM`
  (mnemonic; standby + flush TNC TX buffer — NOT `R`, which does not flush);
  Baudot/ASCII/Morse → `RC` + flush the local `TxController` buffer
  (`on_send_stop()` + `clear()`). No new "Stop TX" button was needed — the
  RECEIVE button (Baudot/ASCII/Morse) and Clear TX (all modes) already cover it.
  AMTOR has no RECEIVE button, so Clear TX is its only stop path; `_on_clear_tx()`
  sends `AM` unconditionally for AMTOR (see the `_send_active` trap under Known
  Gotchas). Packet/PACTOR send no stop command (frame-based / out of Host Mode).
  Verified for every mode; TxController cycle Paket 1–3 closed. Hardware pending.
- `char_ready` guard in `_wire_mode_callbacks`: only wire it when
  `not hasattr(tx, 'char_typed')`. A `TxInputWidget` already emits `char_typed`,
  so wiring `char_ready` as well would double-send.

See `Backlog.md` (TxController section) and `TX_STATE_MACHINE.md` for detail.

---

## Reference Documents in Project Knowledge

| File | Purpose |
|------|---------|
| `UI_DESIGN.md` | Authoritative UI design decisions (screen hierarchy, theme, buttons) |
| `MOCKUP_STATUS.md` | Screen implementation status and roadmap |
| `SERIAL_CONNECTION_STATE_MACHINE.md` | 8-state connection FSM, init sequence detail |
| `OPMODE_SWITCH_STATE_MACHINE.md` | Mode switch FSM, Path A vs Path B |
| `TX_STATE_MACHINE.md` | TX character flow, paste handling, backspace sentinel |
| `Eventfilter_architecture.md` | Three-level event filter architecture |
| `Backlog.md` | Prioritised open work items |
| `Testplan.md` | Test cases T01–T82 with pass/fail status |
| `pk232py_sources.txt` | Complete source code export (authoritative) |
| `AEA-PK-232-TechnicalReferenceManual.pdf` | Hardware reference (Host Mode protocol) |
| `PPWIN.HLP` | PCPackRatt help file (reference for UI feature parity) |

---

## Open Questions / Next Steps

### Immediate (next session)

1. **Packet Connect/Disconnect** — CO/DI frames + CONNECTED pill software-verified
   via mock (T33–T39); hardware re-test needs a second AX.25 station on
   144.800 MHz. T38/T39 also need an interactive mock GUI re-click.
2. **Packet MHEARD** — parse MH frame into MheardPanel (T41–T42)
3. ~~**Packet toggle/button tests** (T43–T51)~~ — **done 2026-06-22**
   (frame/code-verified; PASSALL `PA`→`PS` bugfix). See Backlog.md.

### Medium term

4. **CTRL+D EOT — Paket 2b (AMTOR):** ARQ → `OV`, FEC → `RC`; add AMTOR to
   `_is_txctrl_mode()`. CW/Morse (Paket 2a) is done — hardware test pending.
5. ~~**Stop Sending — Paket 3**~~ ✅ DONE 2026-06-22 (software/mock). No new
   button needed: RECEIVE (RTTY/Morse → `RC`) + Clear TX (all; AMTOR → `AM`)
   cover it; Packet/PACTOR send none. See §11 + the `_send_active` Gotcha.
6. **Theme persistence** — `[UI]` section in INI, `Configure → Appearance` dialog
7. ~~**Tooltip system** — central `tooltips.py`~~ ✅ DONE 2026-06-22. Global
   `TOOLTIPS` + per-class `SCREEN_TOOLTIPS` overrides; wired into all 10 screens.
   See the tooltip Gotcha under Known Gotchas. Follow-up: T86 PASSALL `PS`/`PX`
   hardware verification.
8. ~~**Help system** — split `help_baudot.md` into topic files, add Help buttons~~
   ✅ DONE 2026-06-22. `help_viewer.py` `HELP_TOPICS` covers all 10 modes +
   common topics (default `index`, internal topic-link navigation); 10 reviewed
   help files (`vhf` → `help_packet.md`, shared); `make_help_button()` (`?`) on
   all 10 screens; Help menu (Contents = F1, About). See the HelpViewer Gotcha.
   Follow-up: `help_amtor.md` proof-read; `help_shortcuts.md` / `help_controls.md`
   as own files (v0.2).

### Before beta

9. **APRS Phase 2** — beacon TX, beacon config UI, MHEARD APRS stations
10. **PACTOR/AMTOR identity** — wire parameter dialogs to TNC commands (T52–T58)
11. **Parameter integration** — load/save screen parameters from AppConfig on mode switch

---

## Known Gotchas & Pitfalls

A running collection of "you must know this or you'll break something" facts.
Grows over time.

### Serial / Host Mode

- **Direct serial I/O only — never a queue/worker for Host Mode frames.** The
  single most important constraint in the project. See §3.
- **Fresh `serial.Serial()` after the Host Mode subprocess exits.** Reusing the
  old object → 20–35 s buffering delays. See §3.
- **`write_verbose_wait()` race condition (fixed).** Lives in
  `serial_manager.py` (`_IDLE_S = 0.12`), used by `params_uploader.py` during
  the C4 upload phase.
  - *Symptom:* parameter uploads intermittently returned `?What?`.
  - *Cause:* the method returned immediately when the `cmd:` prompt appeared,
    but the TNC was still writing — the next command overlapped the unfinished
    response, corrupting it.
  - *Fix:* after the `cmd:` prompt is seen, wait for **120 ms of idle** (no new
    byte in the buffer) before returning. An `idle_since` timer is reset on
    every new byte; the method returns only after `_IDLE_S = 0.12` s without
    fresh data.

### TNC / firmware v7.1

- **PACTOR-only commands → `?What?` without the PACTOR option:** `MYPTCALL`,
  `ARQTOL`, `MOPT`, `EXPERT OFF`, `PTHUFF`, `PT200`, `PTOVER`. Gate them behind
  `SerialManager.has_pactor`. See §9.
- **FAX never leaves Host Mode** (no verbose path); the TNC decodes the audio
  and streams ESC-L pixels. See §4.
- **`MOPT` = Morse Option, `ARQTOL` = AMTOR ARQ tolerance** — both are
  PACTOR-firmware-only, despite the names suggesting CW/AMTOR.
- **Host Mode mnemonics are a fixed table, NOT first-two-letters.** MYCALL=`ML`,
  MYSELCAL=`MG`, MYPTCALL=`MK`, PACKET=`PA`, **PASSALL=`PS`**. Verify every new
  mnemonic against the TRM Host Mode command table — never guess. *Bug fixed
  2026-06-22:* the PASSALL toggle was wired as `PA` (= PACKET activation), so a
  click would have re-entered Packet mode instead of toggling PASSALL.
- **MHEARD in Host Mode = line-by-line poll, NOT a single `MH` frame** (TRM
  §4.11). `build_command(b'MH')` returns an empty response (the verbose list is
  too long for the small Host Mode response buffer). Instead poll `MH0`…`MH17`
  (`SOH $4F b'MH' + str(i).encode() ETB`) until the TNC replies `b'MH' + $00`
  (end marker) or `MH17` is reached — up to 18 entries (lines 0–17). Each line
  comes back as a CMD_RESP whose payload is `b'MH'` + the line text. **Mnemonic
  encoding: `str(i).encode('ascii')` → `b'0'`..`b'17'`** — `bytes([0x30+i])`
  breaks for `i>=10` (the hex `$3A` trap). The poll is fire-and-forget (don't
  block the GUI thread; SerialManager is async). CAUTION: a Packet frame
  arriving mid-poll can garble the list — HBAUD-110 workaround deferred to v0.2.

### Packet (HF / VHF)

- **PASSALL = `PS`, not `PA`** — see the mnemonic-table note above.
- **HF/VHF init-frame inheritance trap.** `HFPacketMode.get_init_frames()` now
  emits `VH N` + `HB 300` + `MN Y` (selects the 300 Bd HF FSK modem).
  `VHFPacketMode` therefore must **NOT** call `super().get_init_frames()` — that
  `VH N` would immediately undo the `VH Y` it sends in `get_activate_frames()`
  and drop VHF back to the HF modem. VHF builds its own list (`HB 1200`, `MX 4`,
  `SL 10`, `MN Y`). Leaving VHF Packet also sends `VH N`
  (`_on_mode_selected` → `VHFPacketMode.vhf_off_frame()`, T51).
- **Connect ↔ Unproto are mutually exclusive (T39).** `set_link_state()` greys
  `btn_unproto` while connected/calling; `_on_packet_unproto()` greys
  `btn_connect` while Unproto is on (link-busy proxy = `btn_disconnect.isEnabled()`).
- **Channel model (2026-09-20, ChannelBar sprint).** There is **no CSTATUS
  poll in Host Mode** — the PK-232 never tells the host "channel N is
  connected to X" on demand. The channel a frame belongs to lives only in the
  low nibble of that frame's CTL byte, already decoded into
  `HostFrame.channel` by `comm/frame.py`. So the UI's channel model is purely
  local bookkeeping, built entirely from frames that already went by:
  `HFPacketMode.on_channel_state(channel, state, partner)` derives
  free/calling/connected from the same $5x link messages `on_link_message`
  already parses (`_extract_partner()` does best-effort callsign extraction
  from strings like `"CONNECTED to OE1XYZ-5"`), and feeds
  `ChannelBar.set_channel_state()` in `packet_screen.py`. `ChannelBar` (10
  chips, channels 0–9) is the single source of truth for "which channel do
  Connect/Disconnect/TX act on right now" — `PacketBaseScreen.current_channel()`
  is a thin proxy to `channel_bar.current()`. **Channel 0 is the only channel
  ever used outside Packet mode** (unproto/monitor default; `send_data(...,
  channel=0)` elsewhere in the app). MainWindow no longer hardcodes channel 1
  anywhere in the Packet connect/disconnect/TX path — see
  `_on_packet_connect`/`_on_packet_disconnect`/`_on_packet_tx_enter`.
- **ALL/CH RX filter is append-time, not a buffer rebuild.** Switching the
  current channel or toggling ALL/CH does **not** redraw RX history —
  `PacketBaseScreen.append_channel_data()` simply decides whether to write a
  given line when it arrives. This is a deliberate v0.1 simplification (see
  the method's docstring); monitor/unproto frames (`append_monitor_data()`)
  are never filtered by channel since they were never channel-scoped to begin
  with. This is unrelated to (and does not replace) the pre-existing
  `_packet_raw_frames` buffer + `_packet_rx_redraw()`, which still exists
  solely to re-render raw ↔ APRS-decoded on the APRS toggle (T59/T60).

### UI / PyQt6

- **Identity fields are `QLabel`, not `QLineEdit`** — only editable fields get a
  `ScreenFocusController`. See §5 / §6.
- **`char_ready` double-send trap:** wire `char_ready` only when
  `not hasattr(tx, 'char_typed')` — a `TxInputWidget` already emits `char_typed`,
  so wiring both double-sends every character. See §11.
- **`main_window.py` encoding corruption** at ~line 1503 (second file appended
  on PowerShell copy). See §10.
- **AMTOR `_send_active` trap (fixed 2026-06-22).** `self._send_active` is set
  ONLY by `_on_screen_send(True)` — the SEND-button path. AMTOR has no SEND/
  RECEIVE button: its ARQ TX starts via `_make_link_handler()` →
  `on_send_start()` (CONNECTED trigger). So any `if self._send_active:` guard
  silently skips AMTOR. This made Clear TX drop the `AM` flush for AMTOR. Fix:
  `_on_clear_tx()` sends `AM` unconditionally for AMTOR ARQ/FEC; the
  `_send_active` guard is kept only for the button-driven modes (Baudot/ASCII/
  Morse), where an idle Clear TX must not needlessly key the TNC with `RC`.
  *Rule:* never gate AMTOR behaviour on `_send_active` — derive AMTOR TX state
  from the link (CONNECTED) or the screen sub-state, never the SEND flag.
- **Tooltip name collisions — use `SCREEN_TOOLTIPS`, not a flat dict.** Several
  widget attribute names are reused with DIFFERENT meanings across screens:
  `btn_connect` (AX.25 Packet vs PACTOR), `btn_rxrev` (RTTY tone swap vs FAX
  polarity), `btn_lock` (Morse sync vs FAX start), `btn_stby` (AMTOR vs PACTOR),
  `btn_clear` (FAX image vs MHEARD list). A flat dict keyed by attribute name
  cannot tell them apart. `tooltips.py` therefore has a global `TOOLTIPS` plus
  per-class `SCREEN_TOOLTIPS`; `apply_tooltips()` applies global first, then the
  class-specific overrides. New screen with a colliding name → add it to
  `SCREEN_TOOLTIPS[ClassName]`, not the global dict. Call `apply_tooltips(self)`
  at the END of `__init__` (after every widget is built); Baudot/ASCII have no
  own `__init__`, so the call lives in `RttyBaseScreen.__init__`.
- **WIDESHFT does not apply to AMTOR.** AMTOR runs at a fixed 100 Bd with fixed
  shift; WIDESHFT (170/850 Hz) is FSK-only (Baudot/ASCII/Morse). `btn_wideshft`
  does not exist on `AmtorScreen` and must not be added there.
- **`btn_mopt` does not exist in the codebase** (grep-confirmed). MOPT is
  PACTOR-firmware-only; if it ever needs a UI control, gate it behind
  `SerialManager.has_pactor` (do not add a bare `btn_mopt` toggle). NB: Morse
  has a `btn_moptt` (MOPTT) — a different button, intentionally not tooltip'd.
- **HelpViewer internal topic links — URL-scheme detection.** `QTextBrowser`
  fires `anchorClicked(QUrl)` for every link click (`setOpenLinks(False)`).
  `_on_link_clicked()` branches on the QUrl:
  - `url.scheme() == ""` and the path is a key in `HELP_TOPICS` →
    `_load_topic()` (topic switch — this is what cross-links the help pages).
  - `#fragment` (same-page anchor) → `scrollToAnchor()`.
  - `url.scheme()` in (`http`, `https`) → `QDesktopServices.openUrl()` (browser).
  A Markdown link like `[AMTOR](amtor)` produces a scheme-less QUrl with
  `path="amtor"`. No base-URL or real file paths needed — `HELP_TOPICS` is the
  sole indirection layer (so `vhf` and `packet` can both map to
  `help_packet.md`). Help button factory: `make_help_button()` in
  `opmode_rtty_base.py`; default topic = `index`.
- **APRS on HF Packet — `APRS_CAPABLE` flag, not mode logic.** `btn_aprs` lives
  in `PacketBaseScreen` and its visibility is gated by the `APRS_CAPABLE` class
  attribute (set `True` on both `HFPacketScreen` and `VHFPacketScreen`). The
  decode path in `main_window.py` is already mode-agnostic — `_is_packet`
  matches any `PacketBaseScreen` subclass, and `HFPacketMode` already calls
  `on_monitor_frame` — so **no change to `packet_hf.py` is needed** to enable
  APRS on HF; flipping `APRS_CAPABLE = True` is the entire change.

### FAX (live image decode — implemented 2026-06-18, hardware-verified T82)

- **`$3F` is Epson 9-pin printer graphics, not grayscale.** `EpsonFaxParser`
  (`modes/fax.py`) MUST be **length-driven** and **frame-overlapping**: in the
  DATA state it consumes exactly `N` column bytes and **never scans for escapes**
  — `0x1B` is a valid data byte. `ESC L`/`ESC A` are recognised only in SCAN.
  Treating raw bytes as a grayscale line was the original bug (skew/seam).
- **Non-square raster → `PIXEL_ASPECT = 120/72`.** `ESC L` = 120 dpi horizontal,
  `ESC A 8` = 72 dpi vertical; the display stretches the **vertical** axis by
  120/72 (in `_apply_zoom`, smooth scaling). Without it a circle is a wide
  ellipse. The "Line spacing" slider is a manual fine-factor that *multiplies*
  with `PIXEL_ASPECT` (default 1 = neutral).
- **FAXNEG = display-only invert** (in `FaxImageWidget`). Do **NOT** send the
  `FN` frame: the TNC-side `FN` only affects *subsequent* lines, so toggling
  mid-reception bands the polarity. **RXREV** (`RV`) *is* a real TNC command
  (whole-stream polarity) — set it before/at the start of reception.
- **LOCK (`LO`) = force receive/start; Stop = freeze + parser reset.** Both set
  `MainWindow._fax_receiving`; Stop drops incoming rows and resets the parser so
  a half-finished `ESC L` block can't bleed into the next image; Clear/LOCK
  re-enable. The image stays on screen for viewing/saving.
- **Smoothing = non-destructive inverse-halftoning** (`scipy.ndimage`
  `gaussian_filter`, anisotropic `σ=(σ, σ·PIXEL_ASPECT)`, throttled recompute).
  Display-only — slider at 0 reproduces the exact raw bilevel; Save exports the
  currently displayed version.
- **Test-WAV tone profiles:** `fax_wav_generator.py --target tnc` = 1200/2200 Hz
  (PK-232 demod centre 1.7 kHz, for direct WAV→TNC) vs `--target sw` = 1500/2300
  Hz (on-air convention, for the software audio decoder). Never feed an `sw` WAV
  to the TNC or a `_tnc` WAV to `fax_decoder_test.py`.

### Repo / tooling

- **`CLAUDE.md` is tracked by git as lowercase `claude.md`** on the
  case-insensitive Windows filesystem. `git add CLAUDE.md` may not stage it —
  use `git add claude.md`.
- **Project docs are not in `pk232py_sources.txt`** — upload them to the Claude
  project knowledge separately. See §1.

### Dead Code / Cleanup

- **`main_window.py` §10 append artefact (2026-06-23).** Lines **4170–4191**
  hold an appended, mangled fragment of `tnc_config_dialog.py` (the `# === … ===`
  separator + copyright + module docstring, with mojibake `â€”`/`â€¦`). It is a
  bare module-level string expression — a **no-op**, NOT a duplicate `class`
  definition, so it shadows nothing and causes no defect. This is the §10
  PowerShell-copy corruption signature (here at line 4170, not the historical
  ~1503). Remove lines 4170–4191 in one commit when convenient; verify the file
  still ends cleanly at the real `_restore_window_geometry()` body.
- **Only ONE TNC-config dialog is live: `ui/tnc_config_dialog.py::TncConfigDialog`**
  (imported by `MainWindow`). The duplicate `ui/dialogs/tnc_config.py::`
  `TNCConfigDialog` was dead (only re-exported, never instantiated) and was
  **deleted 2026-06-23** — do not re-add it. Note the casing: `TncConfigDialog`
  (live) vs `TNCConfigDialog` (deleted).

### Help content

- **`help_controls.md` documents ONLY `[^D]` and `[^T:n]`.** Those are the only
  TX control markers `TxInputWidget` actually supports (Ctrl-D EOT, Ctrl-T timed
  — `opmode_rtty_base.py:389–447`). **WRU (Ctrl-E) and AAB (Ctrl-B) are NOT
  typeable TX control characters** — they exist only as TNC parameters
  (auto-answerback) set via `params_baudot` / `params_amtor`. Do not list them
  as control characters in the help.

---

## Learning Mode Note

The developer operates in **"Lernmodus"** — learning alongside the code.
Every non-trivial code block should be accompanied by a brief explanation of:
- **What** it does
- **Why** this approach was chosen over alternatives
- Any **traps or gotchas** specific to PyQt6 or the PK-232 protocol

Prefer simple, proven patterns over clever solutions.