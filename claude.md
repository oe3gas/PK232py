# CLAUDE.md — PK232PY Project Context

> This file is the single entry point for Claude Code to understand the
> PK232PY project. Read it completely before touching any source file.
> Last updated: 2026-09-25

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
  verified):** `ChannelBar` (10-chip multi-channel selector), a `cb_dest`
  history combo (replaced `le_dest` on Packet screens only — itself later
  removed entirely, P42, 2026-09-24, see below), ALL/CH RX filtering,
  Capture, MHEARD channel column, `HFPacketMode.on_channel_state`.
  MainWindow's Packet connect/disconnect/TX no longer hardcode channel 1. See
  §"Channel model" under Known Gotchas / Packet, and Backlog.md's "Completed
  (2026-09-20 — Packet channel model / ChannelBar sprint)" block.
- **Connect-in-chip sprint (P42, 2026-09-24, software-verified):** the
  Connect/Dest/…/Disconnect row is gone — a callsign is typed directly into
  a free `ChannelChip`'s own inline editor. See the "Connect happens IN the
  chip" bullet under Known Gotchas / Packet for the full operation table,
  and the P41 fixture-teardown gotchas under Known Gotchas / Repo-tooling
  (found finishing this sprint's first full-suite run).
- **Upload-before-Host-Mode sprint (P40, 2026-09-25, unit-verified):**
  `ParamsUploader.upload()` now refuses outright (logs `ERROR`, returns
  `0`, sends nothing) when `SerialManager.is_host_mode` is true instead
  of silently timing out on every command (24.09.2026: 68 commands × 5 s
  = ~6 minutes, none executed — there is no `cmd:` prompt in Host Mode at
  all). Also aborts after 3 consecutive silent commands instead of
  waiting out the rest, and `ParamsUploader.verify()` /
  `SerialManager.query_verbose_value()` spot-check MYCALL/PACLEN/MAXFRAME
  against `AppConfig` right after upload, logging "parameter upload
  verified (N/N)". See the "There is no `cmd:` prompt in Host Mode"
  gotcha under Known Gotchas / TNC-firmware for the full writeup —
  including that the suspected order-reversal in `main_window.py` was
  investigated and NOT found; the code there was already correct.
- **TNC-state detection sprint (P43, 2026-09-25, unit-verified):** the
  operator reproduced P40's actual trigger on the device — a fresh app
  restart with the physical TNC left in Host Mode from the previous
  session, which the old passive wakeup check could never catch (`*`
  gets no answer at all in Host Mode). `SerialManager._init_tnc_thread()`
  now runs a four-step active detection chain (`*` → CR → HPOLL query
  frame → give up) and only sets the new `SerialManager.verbose_confirmed`
  property once one of them has positive evidence; `ParamsUploader.upload()`
  now requires it in addition to P40.2's `is_host_mode` check. Closes
  Backlog.md's P29 (wakeup CR-fallback) — the app now has its own. See
  the "`is_host_mode` is the SOFTWARE's belief" gotcha under Known
  Gotchas / TNC-firmware for the full writeup.
- **Chip states / verbose terminal / recovery stage sprint (P44,
  2026-09-25, unit-verified):** three independent findings from the same
  operator session. (1) A failed Packet connect (retry count exceeded,
  busy, or a DISCONNECTED that arrives while still calling) used to leave
  the channel chip stuck amber ("calling") forever — `ChannelBar.
  set_channel_state()` now flashes a new `CH_FAILED` (red) state for 1.5s
  before reverting to free, `CH_CALLING` gets a synchronized pulse
  animation (one shared `QVariantAnimation`, not one per chip) and a
  trailing ellipsis so the state reads even without colour, and MHEARD's
  own connected-station colour was unified to the same green as the chip
  (was amber, contradicting the chip's own amber-means-calling). (2) The
  verbose terminal's Enter key did nothing at all on an empty field —
  fixed to send a bare CR, the harmless way to fetch the prompt; the
  prompt received during init is now also mirrored into the terminal
  (it was silently consumed by the P43 detection chain and never
  reached the UI otherwise). (3) `SerialManager._init_tnc_thread()`
  gained a "step 3b" recovery stage (double-SOH + GG, then HOST OFF —
  the same bytes the "Recovery" menu action sends) for a TNC that
  answers nothing at all, not even the HPOLL query step 3 already tries
  — suspected cause is a process abruptly killed mid-frame leaving the
  TNC's own frame parser stuck (P44), corrected P45: **this is a
  suspicion, not a measured finding** — a healthy TNC in Host Mode also
  answers nothing in a plain terminal program, so silence alone cannot
  tell "stuck" apart from "working normally"; see the "P44's half-frame
  theory" gotcha for the full picture. See the
  "Packet chip colour states" and the recovery-stage gotchas under Known
  Gotchas for the full writeup. Also fixed a real cross-test crash found
  finishing this sprint: a bare `QTimer.singleShot()` for the failed-flash
  timer kept firing after its owning screen was garbage-collected,
  corrupting unrelated later tests — the same class of collateral damage
  as the P41 stale-event-filter finding; fixed by parenting the timer to
  `ChannelBar` instead.
- **Recovery feedback / honest connection state sprint (P45, 2026-09-25,
  unit-verified):** the operator reproduced a connect failure that left
  the app claiming to be connected (Host Mode button enabled, firmware
  still "unknown") and a Recovery press with no visible reaction at all.
  `SerialManager.recovery()` now runs the documented sequence, THEN calls
  the existing `_init_tnc_thread()` detection chain itself to determine
  the result (no second version of it), and reports success/failure via
  a new `recovery_finished` signal — status bar, verbose terminal, and a
  dialog on failure; the button is locked and relabelled "Recovery
  running..." meanwhile. `_update_connection_ui(True)` no longer jumps
  straight to a "verbose" indicator on port-open alone (a new
  "connecting" state is honest until confirmed); a new `init_failed`
  signal resets the UI to an "error" state without needing to close the
  port (Recovery still needs it) while explicitly keeping Connect and
  Recovery themselves usable. Also corrected P44's own half-frame
  explanation for step 3b from a stated finding to a labelled suspicion —
  a healthy Host Mode TNC is silent in a plain terminal too, so silence
  alone never proves anything is actually stuck. See the "A failed init
  must not leave the app looking connected" and "Recovery reports what
  it did" gotchas under Known Gotchas / TNC-firmware for the full
  writeup.
- **Recovery becomes Emergency Reconnect; TNC actions move into the menu
  (P46, 2026-09-25, unit-verified):** a screenshot showed the RX window
  displaying `SerialManager.recovery()`'s own frame bytes as garbled text
  right before "did not reach the TNC" — `_recovery_thread()` was
  writing its preamble while `ReaderThread` was still running, so the
  TNC's response was consumed there instead of by the detection chain.
  Fixed with a new shared `_take_over_read_path()` helper both
  `_init_tnc_thread()` and `_recovery_thread()` call before any write.
  `recovery()` also lost its `is_connected` requirement — it opens the
  port itself (from the caller's saved config) and is never gated on
  connection state, since it is the one action that must work from ANY
  state ("Emergency Reconnect (Host Mode Recovery)", Ctrl+R). Separately,
  Connect/Disconnect/Host Mode/Recovery were removed from the toolbar
  entirely (the toolbar now only shows the mode selector, firmware label
  and mode indicator) — "Connect" was ambiguous there, duplicating the
  opmode screens' own station-connect concept. The Packet screen's
  channel-disconnect shortcut moved from Ctrl+D to Ctrl+K to stop
  colliding with the TNC menu's own Ctrl+D. See the "Every detection
  needs the read path exclusively" gotcha under Known Gotchas / Serial-
  Host Mode and "'Connect' is ambiguous" under UI/PyQt6 for the full
  writeup.
- **Enter Host Mode from verbose; banner rendered as one block (P49,
  2026-09-25, unit-verified):** the TNC menu had no way back into Host
  Mode from an existing verbose connection ("Connect + Enter Host
  Mode..." only works from a fresh connect) — new `Enter Host Mode`
  action (Ctrl+H) closes this and is also the last chance to upload
  parameters, since none of that is possible once inside Host Mode
  (P40/P43): already uploaded this session → straight to Host Mode;
  outstanding, Fast Init off → upload first; outstanding, Fast Init on →
  ask (`Upload and switch` / `Switch without upload` / `Cancel`).
  Separately, a screenshot showed the mirrored TNC banner torn in half
  by the app's own `[SYS]` lines and stray control-character boxes at
  line starts — fixed with a short quiet-window buffer
  (`_start_banner_collection()`/`_finish_banner_collection()`) that
  inserts the complete banner as one block before any `[SYS]` message,
  plus `_filter_control_chars()` stripping non-CR/LF/TAB control bytes
  from what is displayed (raw bytes stay in the DEBUG hex log
  unaffected). See the "last chance to upload parameters", "a raw-bytes
  mirror... can be torn apart", and "stray control bytes... must be
  filtered" gotchas for the full writeup.
- **Per-channel RX documents, compact prefixes, resizable TX, MHEARD
  auto-population (P50, 2026-09-25, unit-verified):** four independent
  findings from one screenshot. (1) A suspected channel offset (chip 1
  green/connected, but every received line and the eventual DISCONNECTED
  tagged channel 2) could not be reproduced anywhere in code after
  auditing the full TX/RX channel path (`build_ch_cmd()`/`ctl_channel()`/
  `_make_host_frame()`/`ChannelBar`'s dict-keyed state) — root cause
  still open, needs a real hardware capture; the measurement infra it
  needs already existed (RX side) and gained one more explicit line (TX
  side, `send_channel_command()`). (2) The single-`QTextEdit`, append-
  time ALL/CH filter (v0.1) meant switching to a channel only showed
  what arrived AFTER the switch — replaced with one `QTextDocument` per
  channel plus a merged ALL log, so a channel's full history is there
  the moment you switch to it. (3) The old `[HH:MM:SS] [CHn] ` prefix
  cost about a third of the line width — CH view now has no prefix at
  all (the chip already names the channel), ALL view gets a compact
  `n│` tag, and timestamps are optional (default off). (4) RX/TX is now
  a vertical `QSplitter` — RX grows with the window, TX height is
  adjustable and persisted, instead of a fixed five-line TX box leaving
  a large empty area below RX. (5) MHEARD now gains connection partners
  from live link messages immediately, not only from a manual Refresh.
  See the four new Packet gotchas ("channel-offset report", "every
  channel has its own RX document", "RX/TX is a QSplitter now", "MHEARD
  gains connection partners from live link messages") for the full
  writeup.
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
- **`HOST` is a bit field, not a plain on/off toggle (TRM, cited P24):**
  bit 0 = Host Mode on/off; bit 1 = local MailDrop login — when set, the
  MailDrop-login data channel moves from the normal `$2x` (outgoing)/`$2F`
  (echo/monitored MXMIT) CTL bytes to `$60` (outgoing)/`$70` (incoming),
  with monitored MXMIT staying at `$2F` regardless; bit 2 = extended Host
  Mode. pk232py enters Host Mode with `HOST 3` (bits 0+1 set), so the
  MailDrop-login bit is already on — but nothing in the app has ever sent
  or read a `$60`/`$70` frame; `tools/hw_check.py maildrop_host` (P24.2,
  read-only) is the first thing that probes this channel, hardware result
  still OPEN (T117).
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
- `PacketBaseScreen` → `le_unproto` (its `cb_dest` history combo — added
  in the 2026-09-20 ChannelBar sprint, briefly registered here as
  `cb_dest.lineEdit()` after the P41 fix, 2026-09-24 — is GONE entirely:
  P42, 2026-09-24, removed the whole Connect/Dest/…/Disconnect row. A
  connect callsign is now typed into a channel chip's own inline
  `QLineEdit` editor, which needs **no** `ScreenFocusController`
  registration at all — see the note just below.)

QLabel identity fields (`lbl_mycall`, `lbl_myptcall`, …) are display-only and
are **NOT** registered — they are labels, not input fields.

**A field does not need to be registered here at all if it only needs the
keyboard-redirect exemption (P41, 2026-09-24) — see the "keyboard
redirection and combo boxes" gotcha under "UI / PyQt6" below.**
`ScreenFocusController` tracks FocusIn/FocusOut on the exact object it is
installed on; for an editable `QComboBox` such as the old `cb_dest`, Qt
delivers `FocusIn` (and `QWidget.focusWidget()` afterwards) to the
**combo box itself**, not to its inner `lineEdit()` — hardware-confirmed,
not merely a docs mismatch, and this is exactly the class of bug P41
fixed. `MainWindow.eventFilter()` now ALSO checks
`screen_focus_controller.is_keyboard_input_widget()` as a
registration-free fallback that recognises every keyboard-input widget
type generically by walking the parent chain — this is why a channel
chip's inline editor (P42) needed no registration here to get the same
exemption `cb_dest` needed a workaround for; `ScreenFocusController`
itself was left in place rather than retired, since MainWindow's
Level-1 filter also still checks its `is_active()`.

### 7. Opmode switch state machine

Four states: `M0` NO MODE → `M1` ACTIVATING → `M2` ACTIVE → `M3` SWITCHING.
The 300 ms `_ACTIVATE_DELAY_MS` timer fires `_send_init_frames()`.
Path B (PACTOR) temporarily exits Host Mode — see `OPMODE_SWITCH_STATE_MACHINE.md`.
**Mode instances carrying configuration are built in exactly one place:**
`MainWindow._build_mode_instance(mm_name)` (P19.2). Every
`self._modes.set_mode(...)` call in `main_window.py` passes its result as
`mode_instance` — even when it's `None`. A direct `set_mode(name)` call with
no `mode_instance` makes `ModeManager` build a fresh `cls()`, which only
ever has the mode's constructor **defaults**, never the operator's actual
configuration — see the "UI / PyQt6" gotcha below for the bug this caused.

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
- **Every detection needs the read path exclusively (P46, 25.09.2026).**
  If `ReaderThread` keeps running while something else tries a direct,
  synchronous read of the same port, the answers land in `ReaderThread`
  (and whatever it feeds — the verbose terminal's RX window, via
  `raw_data_received`) and the direct-read side sees nothing at all.
  Found via Recovery (`SerialManager._recovery_thread()`): it wrote its
  own `FRAME_RECOVERY`/`FRAME_HOST_OFF` preamble via `_write_raw()`
  while `ReaderThread` was still running, so the TNC's response was
  consumed there — dumped into the RX window as raw framed bytes
  (`␁␁OGG␁␁␁OHONO[SYS] Recovery did not reach the TNC.`, `$4F` = `'O'`)
  — instead of being visible to the detection chain's own reads
  afterward, so Recovery reported failure even when the TNC had
  actually answered. `_init_tnc_thread()` always got this right (stops
  `ReaderThread`, joins, clears the input buffer, *then* reads); the fix
  was `_take_over_read_path()`, a small shared helper both
  `_init_tnc_thread()` and `_recovery_thread()` now call — **before any
  write**, not just before the chain's own steps. *Rule:* any code about
  to do its own synchronous port reads must take over the read path
  first (stop the background reader, clear the buffer) — never assume
  "I'll read after this write" is safe just because nothing else is
  *supposed* to be listening.
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

- **A measurement finding is valid for the device it was measured on —
  attribute by device, not just by date (P37, 2026-09-24;
  `docs/DEVICES.md` is the inventory).** Every finding below dated up to
  and including 22.09.2026 was measured on **Device A** (11.09.1995,
  PACTOR generation, round prompt bracket); every hardware run from
  23.09.2026 onward (P29 and later) was measured on **Device B**
  (01.AUG.91 / 01.08.1991, MBX generation, square prompt bracket) unless
  the entry says otherwise (Device C, 30.12.1988, BASE generation, has
  never been connected through the app or `hw_check.py` at all — see
  `docs/DEVICES.md`). **Rule: where behaviour diverges between two runs,
  check the firmware/device first — via the `device:` line every
  `hw_check.py` log/summary now carries (`SerialManager.tnc_release`/
  `has_pactor`/`tnc_defaults`) — before assuming the code changed or an
  earlier run was wrong.** This is exactly what settled the 23.09.2026
  `L` → `*** What?` mystery on Device B (see the "Mailbox commands
  terminate with CR only" gotcha below): it looked like it might be a
  genuine MBX-vs-PACTOR difference until the 24.09.2026 re-run showed it
  was a software artefact all along, present on Device B only because
  that was the device on hand that week, not because of anything
  firmware-specific.
- **PACTOR-only commands → `?What?` without the PACTOR option:** `MYPTCALL`,
  `ARQTOL`, `MOPT`, `EXPERT OFF`, `PTHUFF`, `PT200`, `PTOVER`. Gate them behind
  `SerialManager.has_pactor`. See §9.
- **There is no `cmd:` prompt in Host Mode at all — plain verbose text
  sent there is never executed as a command (P40, 2026-09-25).** Observed
  24.09.2026, 21:27: 68 parameter-upload commands, each hitting
  `write_verbose_wait()`'s own 5 s timeout (`no cmd: after ...`), ~6
  minutes total, and — because the TNC was in Host Mode the entire
  time — **none of them reached the TNC at all**. Host Mode expects
  SOH-framed binary frames (§3/§4); a bare `b'MYCALL OE3GAS\r\n'` sent
  there is not a command the TNC recognises, it is just bytes with
  nowhere to go. Parameters are uploaded **exclusively** in verbose mode,
  before Host Mode entry (`SerialManager`'s own module docstring: Phase 1
  `init_tnc()` → Phase 2 `ParamsUploader.upload()` → Phase 3
  `enter_host_mode()`; `SERIAL_CONNECTION_STATE_MACHINE.md`'s C3
  VERBOSE/C4 UPLOADING states, both before C5 SWITCHING/C6 HOST MODE).
  **Investigated, not found in `main_window.py`:** git history and the
  current code both show `_on_verbose_mode_ready()` has called
  `uploader.upload()` before `self._serial.enter_host_mode()` since the
  function's original implementation (commit 1257114) — that call site
  was never the defect. What was actually missing: nothing anywhere
  refused to run the upload if some other/future caller ever invoked it
  while already in Host Mode. `ParamsUploader.upload()` now checks
  `serial.is_host_mode` itself, once, before the first command, and logs
  an `ERROR` + returns `0` instead of silently timing out 68 times — the
  reusable component enforces its own precondition rather than trusting
  every caller to get it right.
  **Also added (same investigation):** `upload()` now aborts after
  `_MAX_CONSECUTIVE_SILENT` (3) commands in a row get no `cmd:` response
  at all, instead of waiting out the full 5 s timeout for every remaining
  command — a real TNC answers every command in well under a second
  (T103), so several in a row this slow means something is genuinely
  wrong, not an occasional fluke. And `ParamsUploader.verify()` /
  `SerialManager.query_verbose_value()` spot-check MYCALL/PACLEN/MAXFRAME
  back against `AppConfig` right after the upload, still in verbose mode
  — cheap (under a second) and would have surfaced this exact failure
  immediately instead of on the next real QSO attempt. Logs `INFO
  "parameter upload verified (N/N)"` on a full match, `WARNING` with the
  expected vs. actual value on a mismatch or no answer — purely
  informational, never aborts the connection sequence.
  **Follow-up (P43, 2026-09-25):** the operator reproduced the actual
  trigger on the device — a fresh app restart with the physical TNC left
  in Host Mode from the previous session. See the next gotcha for why
  `is_host_mode` could not have caught this and what replaces it.
- **The switch to Host Mode is the LAST chance to upload parameters
  (P49, 2026-09-25) — after that it is impossible (no `cmd:` prompt at
  all, see the gotcha above).** Found 25.09.2026: the TNC menu had
  `Leave Host Mode + Return to Terminal` but no way BACK in from an
  existing verbose connection — "Connect + Enter Host Mode..." only
  ever reaches Host Mode from a fresh connect and is greyed out once
  connected, so an operator who connected via "Connect + Enter Terminal
  Mode..." had no way to switch at all. New TNC menu action, `Enter Host
  Mode` (Ctrl+H, `MainWindow._on_enter_host_mode()`), closes this and is
  also the one place that has to decide what to do about a still-
  outstanding upload: already uploaded this session (tracked by the ONE
  flag `_params_uploaded_this_session`, set in `_run_param_upload()`,
  reset on every new connection) → straight to Host Mode; outstanding
  with Fast Init off → upload runs first; outstanding with **Fast Init
  on** → ask (`_ask_fast_init_upload_choice()`), since Fast Init already
  deliberately skipped it once and switching silently would commit to
  whatever the TNC is currently running on with no way back. **Fast Init
  skips the upload — the TNC then runs on its stored values, which on a
  TNC with no RAM buffer battery (see that gotcha below) means whatever
  it had at power-on, i.e. its factory defaults**, not necessarily
  anything the operator configured.
- **`is_host_mode` is the SOFTWARE's belief, not the device's real state
  — never trust it without evidence from THIS session (P43, 2026-09-25,
  same rule P34 already established for `tools/hw_check.py`, now also in
  the application).** A fresh `SerialManager` instance always starts
  `_in_host_mode = False`, regardless of what the physical TNC is
  actually doing — reproduced on the device 24.09.2026: the app leaves
  the TNC in Host Mode when it quits (or is force-killed/crashes before
  its clean-exit path runs — see `disconnect_port()`'s own P43.3 comment,
  which confirms the clean-exit path has always sent `HOST OFF`
  correctly since commit ff17aa0), then a fresh app restart connects
  with `_in_host_mode` starting False, and the old passive wakeup check
  (does a stray SOH byte happen to show up in the response to `*`) never
  actually saw one — **in Host Mode the TNC answers `*` with nothing at
  all**, since it is not a valid frame and the TNC sends nothing
  unsolicited while HPOLL is ON (factory default). Result: 68 parameter
  commands, 5 s timeout each, none executed (the P40 finding above).
  **Fix:** `SerialManager._init_tnc_thread()` now runs a five-step ACTIVE
  detection chain (four steps as of P43, plus P44's step 3b below), each
  step capped at `_TNC_STATE_STEP_TIMEOUT` (1.5 s, so detection itself
  can never take longer than the failure mode it prevents — worst case,
  nothing responds at all, is under 5 s):
  1. `*` → banner or `cmd:` → verbose, freshly booted → done.
  2. bare `CR` → `cmd:` → verbose, already awake → done (tried before
     step 3 deliberately: the already-awake, verbose TNC is the more
     common case and is settled by a single `CR`; this is also what
     closes Backlog.md's P29 CR-fallback item — the app now has its own).
  3. An HPOLL query frame (`build_command(b'HP')`, no argument — reused
     from the existing Host Mode entry code, not rebuilt) → any `$4F`-CTL
     frame back → Host Mode confirmed. This is the only step that can
     reach a TNC genuinely in Host Mode, because it actively asks in
     frame language instead of waiting for something that never comes.
     On a match, writes `FRAME_HOST_OFF` directly (there is no
     `HostModeWorker` running yet at this point in the connection
     sequence, so this reuses the same bytes `exit_host_mode()` sends via
     the worker, not that method itself) and repeats step 2 — if THAT
     sees `cmd:`, verbose is confirmed after all.
  3b. **(P44, 2026-09-25)** If step 3's HPOLL query got NOTHING back at
     all — not even a malformed frame — try the documented recovery
     sequence (double-SOH + GG, TRM 4.1.6, then `HOST OFF`; the exact
     `FRAME_RECOVERY` bytes the "Recovery" menu action already sends)
     before giving up. **Why this might help is a suspicion, not a
     measured finding (corrected P45, 2026-09-25) — see the "P44's
     half-frame theory" gotcha.** The step itself stands regardless:
     sends `FRAME_RECOVERY` then `FRAME_HOST_OFF` directly (same
     reasoning as step 3: no `HostModeWorker` exists yet, so `recovery()`/
     `exit_host_mode()` cannot be called as-is), then repeats step 2 once
     more. Harmless if no TNC is attached at all — a few bytes go
     nowhere.
  4. None of the above answered anything usable → no PK-232 reachable at
     all. A wrong port/baud rate and a hung TNC (see the "PK-232 can
     hang" gotcha) look identical from software, so the abort message
     names both possibilities and includes the port and baud rate.
  **New property `SerialManager.verbose_confirmed`** — True only once
  this chain has ACTIVELY confirmed a verbose prompt this session, never
  merely assumed; reset to `False` at the start of every
  `_init_tnc_thread()` run and cleared again on a successful Host Mode
  entry. `ParamsUploader.upload()` now requires it in addition to the
  existing `is_host_mode` check (P40.2) — refuses with "the verbose
  prompt was never confirmed in this session" if it is missing, even
  when `is_host_mode` happens to read `False`. Defaults permissively to
  `True` via `getattr()` for any duck-typed test double that predates
  P43 and does not define the attribute at all (same convention as
  `has_pactor`) — only a real `SerialManager`, which always has it and
  starts every connection cycle at `False`, actually enforces this gate.
- **A healthy TNC in Host Mode answers nothing in a plain terminal
  program either — silence alone never distinguishes "normal" from
  "stuck" (P45, 2026-09-25).** In Host Mode the TNC only processes
  SOH-framed binary frames; a terminal program like PuTTY sends and shows
  plain text, so a TNC sitting there completely normally, mid-session,
  looks byte-for-byte identical in that terminal to one that is
  genuinely wedged. **P44's "half-frame theory" — that an application
  killed abruptly mid-frame (`Ctrl-C` in the console) leaves the TNC's
  parser stuck waiting for an `ETB`, explaining why step 3's HPOLL query
  got nothing back — is therefore a suspicion, not a measured finding.**
  It was never verified against a TNC known to be in this exact state by
  another means; it is simply consistent with the observed silence,
  which a perfectly normal Host Mode TNC would also produce. The step 3b
  recovery stage this theory motivated (CLAUDE.md's TNC-state-detection
  gotcha above, §4 Phase 1 in `SERIAL_CONNECTION_STATE_MACHINE.md`)
  remains in place regardless — it is harmless to try and demonstrably
  helps in practice — but do not cite the half-frame explanation itself
  as confirmed. A framed query (HPOLL, or the recovery sequence) is the
  *only* way to tell the two cases apart; a silent terminal never can.
- **Recovery reports what it did and always ends in a defined state
  (P45.1, 2026-09-25).** The old `SerialManager.recovery()` sent the
  double-SOH + GG + `HOST OFF` sequence and then stopped — no report of
  whether it worked. Reproduced 25.09.2026: Recovery pressed, no visible
  reaction at all; only pressing "Host Mode" afterwards (and watching it
  actually work) revealed that Recovery HAD done something. `recovery()`
  now runs in a background thread and, after sending the sequence, calls
  `_init_tnc_thread()` itself — the exact same P43/P44 detection chain a
  normal connect uses, not a second version of it — to determine the
  result, then emits `recovery_finished(success, message)`:
  `"Recovery successful - TNC is at the command prompt (verbose mode)."`
  on success (ending in `C3`, `verbose_confirmed` set — parameter upload
  and Host Mode entry proceed exactly as after any other successful
  connect, via the existing paths, no special-casing), or
  `"Recovery did not reach the TNC. Power-cycle it and reconnect."` on
  failure. `MainWindow._on_recovery_finished()` shows the message in the
  status bar and the verbose terminal's RX window (`[SYS] ...`, so it is
  still there in a later capture, not just a transient status-bar line),
  plus a warning dialog on failure. The Recovery button/menu action is
  disabled and relabelled "Recovery running..." for the whole duration.
- **A failed init must not leave the app looking connected (P45.2,
  2026-09-25).** `connection_changed(True)` fires the instant
  `connect_port()` opens the serial port — well before `init_tnc()`'s
  detection chain has confirmed anything about the actual device.
  Reproduced 25.09.2026: TNC in Host Mode, app started, Connect failed
  with the detection chain's own error — and the app still showed itself
  as connected (Host Mode button enabled/green-looking, firmware still
  "unknown"). Root cause was a single, findable source: `_update_connection_ui(True)`
  used to jump straight to the `"verbose"` mode-indicator state on
  port-open alone. Fixed: it now sets a new, honest `"connecting"` state
  instead, which only ever resolves to `"verbose"` (via the existing
  `verbose_mode_ready` → `_on_verbose_mode_ready()` path) or to a new
  `"error"` state via `SerialManager.init_failed` (emitted from
  `_init_tnc_thread()`'s except block) → `MainWindow._on_init_failed()`.
  The serial port itself is deliberately left open on this path (no
  `disconnect_port()` call) — Recovery needs a real port object to write
  to, and the spec explicitly requires both Recovery and Connect to stay
  usable as the way out; `_on_init_failed()` disables the mode combo and
  "Enter Host Mode" (nothing there is actually usable) but explicitly
  re-enables Connect and Recovery. `_on_connect_verbose()`/
  `_on_connect_host()` now also notice `is_connected` is already `True`
  and retry `init_tnc()` directly on the same open port instead of going
  through `connect_port()` again — that method's own "already open"
  guard used to make a second Connect press silently do nothing at all.
  The init-failure error text itself reaches the user via the existing
  `status_message` → `_on_status_message()` path, which used to show an
  error message ONLY as a dialog (an if/else — the status-bar branch
  never ran for an error) — now every error also lands in the status bar
  alongside the dialog.
- **The 1988 BASE-generation firmware has no MailDrop at all (Device C,
  `docs/DEVICES.md`) — detected via a query, not the banner (P37,
  2026-09-24).** Unlike PACTOR, MailDrop capability leaves no marker in
  the boot banner, so `SerialManager.detect_maildrop()` sends a bare
  `MAILDROP` in verbose mode, before the parameter upload, and
  classifies the response (`MAildrop  ON|OFF` → capable, `?What?` → not
  capable, no/unclear answer → unknown, treated as capable so a flaky
  probe can never lock out an existing feature) — cached as
  `has_maildrop`. **`MDCHECK` must never appear in this detection path**
  — it logs into the mailbox and halts packet operation, which a
  capability probe must not do. `ParamsUploader.upload()` calls this
  right before building commands and skips the whole MailDrop block
  (`MAILDROP`/`MDMON`/`MMSG`/`TMAIL`/`3RDPARTY`/`KILONFWD`/`MTEXT`) with
  one log line when it comes back `False`, instead of seven `?What?`
  responses. `btn_maildrop` (Packet screens) and every field in the
  MailDrop Parameters dialog (`MailDropParamsDialog.set_locked()`) stay
  disabled — never hidden — with a tooltip naming the reason.
- **FAX never leaves Host Mode** (no verbose path); the TNC decodes the audio
  and streams ESC-L pixels. See §4.
- **`MOPT` = Morse Option, `ARQTOL` = AMTOR ARQ tolerance** — both are
  PACTOR-firmware-only, despite the names suggesting CW/AMTOR.
- **Host Mode mnemonics are a fixed table, NOT first-two-letters.** MYCALL=`ML`,
  MYSELCAL=`MG`, MYPTCALL=`MK`, PACKET=`PA`, **PASSALL=`PX`, PASS=`PS`**
  (hardware-verified 21.09.2026, Testplan T86: raw Host Mode responses
  `PXN` for `PX`, `PS$16` for `PS` — matches TRM 4.2.2). Verify every new
  mnemonic against the TRM Host Mode command table — never guess. *Bug fixed
  2026-06-22:* the PASSALL toggle was wired as `PA` (= PACKET activation), so a
  click would have re-entered Packet mode instead of toggling PASSALL.
  *Correction 21.09.2026 (P16):* that 2026-06-22 fix replaced `PA` with `PS`
  instead of `PX`, without a TRM citation — so PASSALL sent `PS Y`/`PS N`
  for three months, overwriting the PASS masking character with the letter
  `Y`/`N` instead of toggling PASSALL. **"Never guess" applies to fixes too,
  not just new code** — a correction needs the same TRM citation as new code,
  or it can just as easily introduce a new wrong mnemonic.
- **`pk232_mnemonic_table.txt` is a NAME LIST, not a hardware scan —
  correction, P20, 2026-09-22.** The file's own heading ("Host Mode
  Mnemonic Scan") and P13/P14's description of it ("Scan des realen
  Geräts, v7.1") both overstate what it is: of 676 mnemonic combinations
  queried, only `AC` and `AD` ever answered — both with an error code. The
  "KNOWN NAME" column is a name-to-mnemonic mapping (most likely
  transcribed from TRM 4.2.2), not something the TNC confirmed. This was
  a **specification error**, not an implementation one — the P13 command
  names it was checked against are independently confirmed on real
  hardware anyway (T103's verbose upload, "was"/"now" responses). Evidence
  order for any mnemonic claim, strongest first: **(1)** a real
  `tools/hw_check.py` run against the TNC, **(2)** TRM 4.2.2, **(3)**
  `pk232_mnemonic_table.txt` only as a transcript of the TRM, never as its
  own evidence. See `docs/MNEMONIC_TABLE_NOTE.md` for what the file
  actually is; the file's own header is left untouched (historical
  artefact).

  **Hardware-confirmed Host Mode mnemonics** (add every new hardware
  finding to this table, source in the third column):

  | Mnemonic | Meaning | Evidence |
  |---|---|---|
  | `PX` | PASSALL | T86, T111 (`PXN`/`PXY`) |
  | `PS` | PASS | T86, T111 (`PS$16`) |
  | `SL` | SLOTTIME | T112 (`30` → `10`) |
  | `VH` | VHF | T112 (restore reports `Vhf was OFF`) |
  | `HB` | HBAUD | T112 (restore reports `HBaud was 300`) |
  | `HP` | HPOLL | late response frame after Host Mode entry (T86) |
  | `MX` | MAXFRAME | **open** — needs the T112 retest (P18.1/P18.3 fix) |
  | `MI` | MFILTER, **not** MailDrop login | T115 (`MI$80` / verbose `MFIlter $80`, 22.09.2026) |
- **The TRM itself is internally contradictory about `MI` — measurement
  decides, not the manual (P26, 2026-09-23).** TRM ch.12 lists `MI` as the
  Host Mode mnemonic for BOTH `MDCheck` and `MFIlter` (default `$80`) in
  the same command table. T115's measurement (`MI` → `$80`, verbose
  `MFILTER` → `$80`) settles it: `MI` = MFILTER; the MDCHECK entry in the
  manual is simply wrong. **The Host Mode mnemonic for MDCHECK is still
  unknown** — do not assume it exists as a two-letter mnemonic at all; see
  `mdcheck_scan` in `tools/hw_check.py`, which searches for it without
  guessing. **General rule: when the TRM contradicts itself (or contradicts
  a real measurement) about a mnemonic, the measurement wins, never the
  manual** — the same "never guess, verify against the TRM" principle above
  still applies, but only after confirming the TRM's own entry isn't itself
  the thing in error.
- **`maildrop_host`'s first hardware run (2026-09-22 21:13,
  `hw_logs/20260922_211322_maildrop_host.log`) misjudged its own result —
  fixed P26.1.** Probe A (`L` with no login) got back exactly one frame:
  `ctl=0x5F` `data=b'XX\x00'` — the generic Host Mode data acknowledgement
  every write gets (T101), not mailbox content. The tool's old verdict
  logic treated "probe A got any frame at all" as "login not needed", so
  it reported a false "login not needed" and never ran probe B (MDCHECK
  login, then a second `L`). Fixed: a real "response" for this probe means
  a frame that is NOT `$4F` (CMD_RESP) or `$5F` (STATUS_ERR/ack) — ideally
  `$70` (documented MailDrop read data). `should_run_maildrop_host_probe_b()`
  / `has_mailbox_data_frame()` in `tools/hw_check.py` implement this; a
  bare `$5F` ack no longer counts as a mailbox response, and probe B now
  runs whenever probe A got nothing but acks.
- **A stale response frame from a PRIOR command can still be queued when the
  next query goes out — never correlate a Host Mode response by arrival
  order, always by its mnemonic prefix (`frame.data[:2]` /
  `frame.mnemonic`).** Hardware-observed 21.09.2026 (T86): entering Host
  Mode leaves a trailing `HP\x00` (HPOLL) response frame that arrives late
  and was still in flight when the very next query's frame arrived,
  masquerading as that query's answer (`tools/hw_check.py::query_host()` had
  exactly this bug — fixed by `select_response_frame()`, P16.2). Any code
  that sends a Host Mode query and reads "the next frame" instead of
  filtering by mnemonic is exposed to the same failure mode.
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
- **SIAM results arrive as `$50` LINK_MSG on channel 0, split across
  exactly two frames — never as `$4F` CMD_RESP** (hardware-verified
  22.09.2026, Testplan T113, `tools/hw_check.py siam`; corrects
  `signal_analysis.py`'s own module docstring, which wrongly claimed
  CMD_RESP before this measurement). Format:
  `'<confidence>: <baud> baud, <mode>, RXRev <ON|OFF>'`, e.g.
  `'0.73: 50 baud, Baudot, RXRev ON'` — matches the `signal_screen.py`
  mockup, **not** the STABO manual's `'BAUDOT 45 170'` example. The TNC
  analyses **continuously**, sending a new result roughly every 10s; it
  does not stop after the first one. `SignalMode` (P18.2) assembles the
  two-frame fragments in `_siam_buffer` until a line ending is seen,
  clears the buffer on `get_activate_frames()`, and never calls
  `on_result()`/`on_result_parsed()` for a CMD_RESP frame at all — this
  closes the P16.3 finding (a stray CMD_RESP mistaken for a SIAM result)
  completely, not just for frames ending in `$00`. `SignalScreen` (P19.4)
  is wired to `on_result_parsed` only (never `on_result` — it has no
  parser of its own to feed, and wiring both would double-handle every
  successfully parsed line); it shows the latest result plus the highest
  confidence seen so far ("Best so far", reset only by New Analysis/
  Cancel, not by every incoming result, since the TNC keeps analysing
  continuously within one Signal/SIAM session).
- **SIAM keeps running until a DIFFERENT mode is explicitly selected —
  it does not stop on its own, and writes its results asynchronously
  into whatever else is happening** (hardware-confirmed 22.09.2026,
  P21). Observed interleaved into an unrelated `XMITOK` verbose response,
  into the plain command-mode prompt, and right after a MailDrop prompt —
  there is no operating-mode boundary that blocks it once SIAM is active
  in verbose mode. Any verbose-mode parser (`parse_query_value()`,
  anything reading raw serial responses) must tolerate an unrelated line
  landing in the middle of its own response; never assume a response is
  exactly what was asked for just because it arrived right after the
  matching command was sent. `tools/hw_check.py`'s `Session.normalize()`
  (P21.2) sends `PACKET` at the start of every hardware subcommand
  specifically to stop this before it can happen.
- **MailDrop facts, hardware-confirmed 22.09.2026 (P21; STABO handbook
  ch.5, p.56–63):**
  - Real prompt: `` (AEA PK-232M)  18536 free  (B,E,K,L,R,S) > `` — round
    brackets, double spaces before the free-byte count and before the
    command-set parenthesis. Differs from the TRM's `[AEA PK-232M] ... >`
    example — do not assume the TRM's bracket style is literal.
  - **Both bracket forms are hardware-confirmed — the device-name bracket
    depends on the EPROM, not a fixed shape (P31, 2026-09-23).** 22.09.2026
    (three rounds, P21–P24): round, `` (AEA PK-232M)  18536 free
    (B,E,K,L,R,S) > `` — the operator confirms the **11.09.1995 EPROM**
    (Gen. 3 / PACTOR, see `docs/PK232_firware_matrrix.md` §2) was installed
    for those rounds. 23.09.2026, 18:43 (P31,
    `hw_logs/20260923_184302_maildrop_session.log`), after the TNC had
    hung and been power-cycled: square, `` [AEA PK-232M]  18340 free
    (B,E,K,L,R,S) > `` — the operator confirms the **01.08.1991 EPROM**
    (Gen. 2 / MBX) was installed at that point, i.e. the bracket actually
    tracks a real EPROM swap between the two sessions, not a firmware
    fluke on the same chip. The command-set parenthesis after `free`
    stays round in **both** measurements — only the device-name bracket
    varies. `MailDropEntry`'s `PromptInfo.bracket` (`protocol.py`) records
    which form a given prompt used, `"round"` or `"square"`, for exactly
    this reason: whether the 1988 BASE EPROM uses a third form is still
    unmeasured, so treat `bracket` as an open data point, not a closed
    question, and log it on every future MailDrop hardware run.
  - SysOp command set is **`B`, `E`, `K`, `L`, `R`, `S` only.** `H`/`?`
    help is for OTHER users logging in, **not** the SysOp — sending `H`
    as SysOp answers `*** What?` (still followed by the mailbox prompt,
    not an error state).
  - `B` (bye) closes the mailbox and returns **straight to `cmd:`**, with
    no other message.
  - `MDCHECK` opens the mailbox even with the TNC at factory defaults
    (`MYCALL PK232`, `MAILDROP OFF`) — it does not require MailDrop to be
    turned on first.
  - `KILONFWD` is an **EXPERT-mode command** (`?EXPERT command` if
    `EXPERT` is off) — explains the `EXPERT ON` bracket already present
    in `ParamsUploader`.
  - At the plain TNC command level (not inside the mailbox): `E` →
    `?EXPERT command`; `K` → `?need MYcall` — `K` there is **CONVERSE**,
    a completely different command than mailbox `K` (kill message). This
    is exactly why an interactive tool phase must never let typed input
    reach the command interpreter unnoticed (see the safety rule below).
  - **Command/response shapes, hardware-confirmed 22.09.2026, 18:43
    (P22, `hw_logs/20260922_184337_maildrop.log`):** `L` on an empty
    mailbox → `*** Message not found.` + prompt; `S <call>` → `Subject:`;
    the subject line → `Enter message, ^Z (CTRL-Z) or /EX to end` + a
    blank line, then every further typed line is echoed with no prompt
    until `/EX` (confirmed reliable — see the `^Z` finding below) →
    `Message stored as # <n>` + prompt; `R <n>` (note the required space
    before `<n>`, see below) → the list header + that message's list
    row, a blank line, the message text, then the prompt directly — a
    stray **`/E`** line before the prompt was seen exactly once, in
    round 1, and is not general (see below). `K <n>` → `*** Done.` +
    prompt. Lowercase input is accepted;
    `S oe3gas#` stores `OE3GAS` as the recipient (non-alphanumeric
    characters in the callsign are dropped).
  - **`S` accepts a foreign FROM and a BBS route.** `S <to> @ <bbs>`
    (confirmed 22.09.2026 19:16, P23, e.g. `S OE1XYZ @ DB0MUC`) puts
    `<bbs>` in the list's `@ BBS` column. `S <to> < <from>` (a **foreign
    FROM**, less-than sign, matching the STABO handbook) is confirmed
    working 22.09.2026 20:00 (P24, round 3,
    `hw_logs/20260922_200013_maildrop.log`): `S OE3GAS < DL1ABC` listed
    as `To=OE3GAS From=DL1ABC` — two earlier hardware attempts (P23) had
    mistyped `>` instead of `<` and never actually tested this. **The
    TNC does not validate or report unknown/malformed extras in the `S`
    command at all** (confirmed by those same mistyped attempts: the
    line was silently accepted up to the mistyped character, with no
    error) — any dialog built on this must validate the recipient,
    `@BBS` and foreign-FROM syntax itself before sending; do not rely on
    the TNC to reject a mistake.
  - **SysOp can post directly as `SB <to>` (bulletin) and `ST <to>`
    (traffic), confirmed 22.09.2026 19:16** — same `Subject:`/text flow
    as plain `S`, just a different two-letter command; the resulting
    list rows show status `BN`/`TN` (type `B`/`T`, unread) instead of
    `PN`. `SB ALL` posted an actual `ALL`-addressed bulletin.
  - **Date format, confirmed 22.09.2026 19:16:** `DD-Mon-YY  HH:MM`
    (e.g. `22-Sep-26  17:20`), UTC, matching whatever `DAYTIME` was last
    set to. **The date is stamped at STORE time, not display time** — a
    message saved before `DAYTIME` was ever set keeps showing dots
    forever, even after the clock is set afterwards and later messages
    get real timestamps (confirmed: round 1's message 2 still showed
    dots in round 2's listing, after `tools/hw_check.py maildrop` had
    since started setting `DAYTIME` on every run, P22.3).
  - **`MDCHECK` with unread mail present adds a `You have mail.` line**
    before the mailbox prompt (confirmed 22.09.2026 19:16) — additional
    text before the prompt, not a different prompt shape.
  - **List format is FIXED-WIDTH columns, newest message first:**
    ```
    Msg#    Size To     From   @ BBS  Date       Time   Title
      2 PN    35 OE3GAS OE3GAS        .........  .....  Test 2
      1 PY    36 OE3GAS OE3GAS        .........  .....  test 1
    ```
    Status is two fixed characters: **type** (`P` seen; TRM also lists
    `T`, `B`) + **read status** (`N` unread, `Y` read — reading message 1
    flipped its own row from `PN` to `PY`, in place). `@ BBS` is blank
    (still occupying its column) when no BBS was given. Date/Time show as
    dot-runs (`.........` / `.....`) whenever the TNC clock has never been
    set — **not** a format quirk, just the RAM-buffer-battery finding
    (below) showing up here too; `tools/hw_check.py maildrop` sets
    `DAYTIME` before opening the mailbox specifically so these columns
    show real values (P22.3). `tools/hw_check.py::parse_maildrop_list()`
    parses this format (tool-only, not used by the app yet).
  - **TNC message numbers are NOT reassigned after a kill, and are only
    unique within one power-on period.** Killing message 1 left message 2
    at number 2 (not renumbered to 1); numbering restarts after a
    power-cycle. **Design consequence for any future archive:** the
    archive's own record key must be its own durable ID, never the TNC's
    message number — that number is only a transient attribute of the
    live mailbox.
  - **Memory cost per message is NOT a fixed `size + 48` — that P22
    formula was withdrawn 22.09.2026 (P23), derived from only two data
    points that happened to agree by coincidence.** Seven messages now
    measured:

    | # | Size | Bytes used | `@BBS`? |
    |---|---|---|---|
    | 1 | 36 | 84 | – |
    | 2 | 35 | 84 | – |
    | 3 | 37 | 84 | – |
    | 4 | 41 | 112 | `DB0MUC` |
    | 5 | 52 | 84 | – |
    | 6 | 33 | 84 | – |
    | 7 | 30 | 112 | `DB0MUC` |

    `Size` itself still reliably equals `len(subject) + len(text) + 9`
    (confirmed for all seven, and again on Device B, P37). But bytes-used
    does **not** scale with `Size` at all — messages of very different
    sizes (30 through 52) all cost 84 bytes unless `@BBS` was given, in
    which case it jumps to 112 regardless of size. **The "BBS costs one
    block more" guess is withdrawn (P37, 2026-09-24, T119, Device B,
    `hw_logs/20260924_181446_maildrop_session.log`):** a 24.09.2026 run
    with three messages and no `@BBS` involved at all still showed sizes
    61→112, 43→84, 35→84 bytes — the 112-byte jump tracked the larger
    message, not a BBS field. There is no rule connecting size, `@BBS`
    and bytes-used visible from either device's data so far.
    **Design consequence, independent of the exact mechanism:** never
    precompute whether a message will fit, and never derive free space
    from size/`@BBS`. Always re-read the free-byte count from the
    mailbox prompt after writing each message and stop before
    `*** No free memory` — the prompt is the only reliable source of
    remaining space, on both devices measured so far.
  - **A stray `/E` line after a read message's text occurs regularly and
    is discarded — reclassified 24.09.2026 (P37, T119, Device B,
    `hw_logs/20260924_181446_maildrop_session.log`), correcting the
    22.09.2026 P24 call that a single occurrence (round 1) was an
    isolated fluke.** Round 3 (P24) happened to show two clean `R`
    responses with no `/E`; the 24.09.2026 Device B run showed it again
    (`...harness\r\n/E\r\n`), so "einmalig beobachtet" understated it —
    it recurs, just not on every single `R`. `parse_read()` already
    strips it correctly and requires no change. **Design consequence,
    unchanged:** a reader must TOLERATE a trailing `/E` line when
    present, but must NOT require one — `tools/hw_check.py::
    maildrop_response_has_e_trailer()` already only detects it
    (tool-only), never assumed one was always there.
  - **Foreign FROM confirmed working, 22.09.2026 round 3:** `S <to> <
    <from>` (less-than sign, matching the STABO handbook — round 1/2 both
    mistyped `>`) sets the message's From field to `<from>` while To
    stays `<to>` — e.g. `S OE3GAS < DL1ABC` listed as
    `To=OE3GAS From=DL1ABC`. The SysOp can set an arbitrary FROM this
    way, with no validation (see the "TNC never validates `S` extras"
    finding, P23) — a real dialog must check the value itself.
  - **`^Z` ($1A) does NOT end a message on this firmware — confirmed
    22.09.2026 round 3, after P23.3 finally made the tool send the real
    byte.** Sent three times (twice via the console-EOFError recovery,
    once by typing the two literal characters), every time the mailbox
    just echoed `$1A` back and stayed in message entry; only `/EX` ever
    ended any of the three test messages. Unconfirmed hypothesis: a
    trailing `CR` might be missing after `$1A` — **not investigated
    further**, since `/EX` is reliable and is what any real dialog will
    use; `^Z` support is not worth pursuing unless a future measurement
    specifically needs it.
  - **A mailbox command needs a space before its argument:** `R2` (no
    space) answered `*** Not enough`; `R 2` (with a space) worked.
  - **Non-ASCII input is lost — but by the TOOL, not necessarily the
    TNC.** Typing "für" arrived at the TNC as `f?r`, because
    `classify_maildrop_input()` encodes with `errors='replace'`
    (ASCII-only) before ever sending a byte — so whether the TNC itself
    would accept real 8-bit/Latin-1 text is **still unmeasured**; it
    depends on `8BITCONV`, which round 3 did not test.
  - **Design consequences for a future MailDrop dialog** (not yet
    implemented, still tool-only measurements): (1) validate that no
    line of message text begins with `/EX` before sending it, or a
    real message body containing that string aborts transmission
    mid-text; (2) transliterate umlauts (`ue`/`oe`/`ae`/`ss`) rather than
    sending them raw, until `8BITCONV` is actually measured; (3) a
    restore/recovery feature can preserve sender (`<`), BBS (`@`) and
    type (`SB`/`ST`) when re-creating a message, but **not** its
    original date/time — the TNC always stamps that at store time, not
    from anything the dialog could supply.
- **MailDrop session (P27, implemented 2026-09-23).** `src/pk232py/
  maildrop/protocol.py` (pure parsing/command-building, no I/O) +
  `session.py` (`MailDropSession`, the state machine) replace the old
  `maildrop.py` (geraten/unverified Host Mode mnemonics, dead code,
  deleted). **MDCHECK has no Host Mode mnemonic at all** —
  `mdcheck_scan` tried all 23 non-denylisted `M?` candidates against real
  hardware and found no hit (docs/P26_MDCHECK_Mnemonic_Spec.md) — so the
  whole module operates on the verbose-mode serial link, never Host Mode
  frames. Lifecycle:
  ```
  Host Mode --> verbose --> MDCHECK --> [session] --> B --> Host Mode
  ```
  Both Host Mode transitions reuse `SerialManager.exit_host_mode()`/
  `enter_host_mode()` exactly as Path B (PACTOR) already does in
  OPMODE_SWITCH_STATE_MACHINE.md — this module rebuilds neither. States:
  `CLOSED -> OPENING -> ACTIVE -> CLOSING -> CLOSED`, plus `FAILED`;
  every transition fires `state_changed`, every result reaches the
  caller only through a Qt signal (`prompt_info`/`listing`/`message_read`/
  `stored`/`killed`/`failed`) — the blocking read/write exchanges run on
  a background `threading.Thread` per command
  (`MailDropSession._start()`), never on the GUI thread; this is a
  **different** rule from CLAUDE.md SS3's "no worker thread for Host Mode
  frames" — this thread never touches the serial port itself, only
  `SerialManagerChannel` does, via `SerialManager`'s own already-proven
  `write_verbose()`/`raw_data_received`.
  **Exclusivity (TRM/STABO handbook, not yet hardware-measured):** MDCHECK
  only works when no Packet or AMTOR station is currently connected to
  the TNC, and while the local session is open, a foreign station trying
  to connect gets a BUSY frame instead. `MailDropSession` does not know
  the channel model at all — `open()` takes an injected `can_open() ->
  (bool, reason)` callback for this precondition, to be supplied by
  whatever future code DOES know it (the channel bar, `ModeManager`, …).
  **Rückweg (recovery path), reachable from any failure:** `/EX` (in case
  text entry is open) -> `B` -> Ctrl-C+CR -> confirm `cmd:` -> re-enter
  Host Mode; ending in `FAILED` (never a silently-claimed success — the
  lesson from P15) if `cmd:` or Host Mode re-entry cannot be confirmed.
  `is_verbose_mode` is **not** trustworthy right after
  `exit_host_mode()` — it stays `False` until the next full `init_tnc()`
  wakeup, since `exit_host_mode()` itself sets `_verbose_ready = False`
  and nothing else sets it back to `True`; use an ACTIVE Ctrl-C+CR probe
  (matching `tools/hw_check.py`'s own `normalize()`) to confirm `cmd:`
  instead of polling that property. `message_store.py`'s schema did
  **not** cover what a real archive needs (own durable ID ✓, read status
  ✓, sender ✓ — but no TNC message number, no `@ BBS`, no P/T/B type,
  and `received_at` was the LOCAL receipt timestamp, not the TNC's own
  store-time stamp) — left unchanged under P27.3 at the time (a future
  archive package's job, not a schema migration bolted onto this one);
  **replaced outright by `maildrop/archive.py` under P38** (see the
  dedicated bullet below) — `message_store.py` is deleted.
- **MailDrop local archive — optional, off by default (P38, 2026-09-24).**
  `maildrop/archive.py`'s `MailDropArchive` is PK232PY's own durable
  record of MailDrop messages, entirely separate from the TNC's volatile
  mailbox. **Deliberately optional and defaults to OFF**
  (`MailDropConfig.archive_enabled = False`) — collecting/restoring
  costs real time and suspends packet operation for the whole session
  (measured 24.09.2026, Device B, T119): opening the session ~4s,
  **each message ~6–7s**, leaving ~3s — 20 messages is a good two
  minutes with the TNC unreachable to other stations (BUSY). Nothing in
  this package collects or restores anything automatically; that is
  explicitly the next package's job (the session mask, Backlog.md) —
  `archive_sync`/`archive_restore`/`archive_restore_scope` are saved
  settings with no effect yet, and the dialog says so
  ("takes effect once the MailDrop session window is available").
  **Key is a content fingerprint, never the TNC message number** — SHA-256
  over `mtype|to_call|from_call|bbs|subject|body` (deliberately excluding
  the TNC timestamp, which is set at store time and would differ after a
  restore-then-collect round trip) — consistent with the existing "TNC
  message numbers are not durable across a power-cycle" rule elsewhere
  in this file. `open_archive(config)` is the only place a
  `MailDropConfig` becomes a `MailDropArchive` instance, and returns
  `None` **without ever creating a database file** when
  `archive_enabled` is `False` — "nothing happens automatically unless
  the user turned it on" is the whole point of this package, not just
  its UI copy.
- **The MailDrop session window is a modal dialog, never a ComboBox
  opmode entry (P39, 2026-09-24).** `ui/dialogs/maildrop_dialog.py`'s
  `MailDropDialog` — see the module's own docstring for the fuller
  reasoning, kept as a comment in the file per the spec. MailDrop is not
  a TNC operating mode; MDCHECK logs the TNC into its own mailbox
  *within* Packet operation, it does not switch modes (`OPMODE_SWITCH_
  STATE_MACHINE.md` never sees it). Giving it a ComboBox entry would
  burden the mode-switch state machine with something that is not a
  mode, and raise the meaningless question of what a mode switch means
  while a mailbox session is running.
  **Two entry points, one gate:** `btn_maildrop` (Packet screens) and
  the `TNC → MailDrop…` menu action both open the same dialog and are
  both governed by `MainWindow._maildrop_gate()` — the single place all
  four blocking conditions are computed, so the two entry points can
  never disagree: `has_maildrop is False` → "this firmware has no
  MailDrop"; a channel connected on the active Packet screen →
  "disconnect channel N first"; current mode not HF/VHF Packet →
  "switch to HF or VHF Packet first"; not connected/not Host Mode →
  "connect to the TNC first". The channel information comes from the
  active screen's own `ChannelBar.channel_map()` and the mode from
  `ModeManager.current_mode_name` — neither is re-derived. This
  supersedes P21.5's permanently-disabled button (it used to send
  `build_command(b'MI')` on the mistaken belief `MI` was a MailDrop
  login, CLAUDE.md's mnemonic-table gotcha) — the button now sends no
  Host Mode frame of its own at all, only opens the dialog.
  **The dialog itself never polls `MailDropSession.state`** (this
  file's "two truths" Qt gotcha) — every redraw is driven by the
  `state_changed` signal's own delivered value, cached only for
  rendering. A window-close gesture (X/Esc/Close) while a session is
  ACTIVE asks for confirmation and only actually closes the `QDialog`
  once `CLOSED` arrives — never merely once `leave()` was called, and
  never at all while `FAILED` (which offers Retry — rebuilding a fresh
  `MailDropSession`/`SerialManagerChannel`, since the old session object
  cannot itself recover from `FAILED` — and Close). The "Where" column
  (`TNC only`/`archive only`/`TNC + archive`) is a header-field match
  against the local archive, deliberately NOT `archive.py`'s own
  duplicate-detection fingerprint — a listing has no body text, so an
  exact fingerprint match is only possible once a message has actually
  been read.
- **P31 (2026-09-23) hardened the above against the first real hardware
  run of the full session harness.** Two gaps the first `maildrop_session`
  run against real hardware (`hw_logs/20260923_184302_maildrop_session.log`)
  exposed, both fixed: (1) `find_prompt()` only matched the round-bracket
  prompt form, so a genuinely different EPROM's square-bracket prompt was
  silently not recognised as a prompt at all — see the bracket-form bullet
  above under "MailDrop facts" for the two confirmed forms; (2) the
  `maildrop_session` test harness (`tools/hw_check.py`) ran its own HPOLL
  confirmation check *before* the session's own internal `_recover()` had
  reached a terminal state, so a still-in-flight recovery's own
  "not in Host Mode" response was misread as a fresh, separate failure —
  the harness now waits for `MailDropSession.state` to reach `CLOSED` or
  `FAILED` first, and skips its own check (deferring to the session's own
  `failed()` message) when the session itself reports `FAILED`. Neither
  gap was in `MailDropSession`'s own recovery logic, which already did
  confirm Host Mode re-entry before reporting `CLOSED` as designed — both
  were in the surrounding layers (parsing, test harness) that fed it real
  data for the first time.
- **Safety rule for interactive tool phases (P21.3):** any interactive
  phase that runs inside a TNC sub-state (currently: the local MailDrop
  terminal in `tools/hw_check.py maildrop`; potentially others later)
  must stop the INSTANT the TNC reports its top-level `cmd:` prompt
  again, before reading or sending anything further. At the plain
  command level, single letters are commands with their own, different
  meanings (`K` = CONVERSE) — with `MYCALL` set and `XMITOK ON`, blindly
  continuing to send typed lines there could transmit on the air. Found
  the hard way 22.09.2026: after `B` silently closed the mailbox, the
  recorder's prompt stayed up and kept forwarding input to the command
  interpreter. See `tools/hw_check.py::run_maildrop_interactive()`.
- **Echo without execution — the TNC can be in a state (most likely
  Converse) that echoes every line typed at it but executes nothing,
  with no `cmd:` prompt to notice by (P34, observed 23.09.2026,
  `hw_logs/20260923_203256_mdcheck_scan.log`).** A `mdcheck_scan` run's
  entire verbose phase — `PACKET`, `MYCALL`, `XMITOK`, `MDCHECK`, `S
  OE3GAS`, the subject, the body, `/EX`, `B` — got nothing back but each
  line's own echo; `Session.normalize()` did not treat the missing
  `cmd:` as an error and kept going regardless, ending with the tool
  reporting "Test message stored as # None". Entering and leaving Host
  Mode cleared the state again afterwards, so it is not a hardware fault,
  just an unconfirmed starting state. **Safety-relevant:** `XMITOK` was
  unknown for the very same reason (its own query got only an echo) — had
  it been `ON`, as in every prior run, typed lines in Converse are echoed
  *and* queued for transmission, so this could have gone out over the
  air. `tools/hw_check.py`'s "never transmits on the air" promise must
  not depend on the TNC happening to already be in the right state.
  **Tool rule (P34.1, `hw_check.py::confirm_command_prompt()`):** no
  verbose command is sent unless the `cmd:` prompt has been confirmed in
  the same session first — `Ctrl-C`+`CR`, then (only if that fails) a
  bare `CR` resync, then (only if that also fails) the documented Host
  Mode recovery/resync frame (TRM 4.1.6, `SerialManager.recovery()`)
  followed by `Ctrl-C`+`CR` again; still no `cmd:` after all three aborts
  the whole subcommand with nothing further sent. The same "state query,
  not an ordinary parameter" rule now applies to `normalize()`'s own
  `MYCALL`/`XMITOK` queries too (`require_query_value()`) — an
  unanswered one aborts instead of being logged and quietly continued
  past, the same class of fix as P15's "no reported success without
  proof".
- **Mailbox commands (and `MDCHECK`) terminate with CR only, not
  CR+LF (P35, 2026-09-23).** The TRM terminates commands with a bare
  CR; the trailing LF `MailDropSession` used to send was a software
  addition, not a protocol requirement. `MailDropSession._send()` now
  sends `\r` for every mailbox command including `MDCHECK` — the one
  place in that module still using `\r\n` before this. **Not a
  retroactive bugfix:** every successful MailDrop run to date (P20–P24,
  P27–P31) used the `\r\n` form and worked fine on Device A (PACTOR,
  11.09.1995) — this is alignment with the manual, not a claim that
  `\r\n` was broken there. **`L` on Device B (MBX, 01.08.1991) — resolved
  2026-09-24 (P37, T119, `hw_logs/20260924_181446_maildrop_session.log`):
  hypothesis (1), a software artefact, not the firmware.** The
  23.09.2026 run (`hw_logs/20260923_204041_maildrop_session.log`) had
  `open()` PASS (Host Mode left, `MDCHECK` recognised, `bracket
  ='square'`, `free=18340`), then `L` got `*** What?` back; three
  indistinguishable-from-that-log hypotheses were on the table: (1) the
  orphaned LF from `MDCHECK\r\n` got processed by the mailbox as its own
  empty command, and that stray response bled into `L`'s read window;
  (2) a genuine MBX-generation firmware difference; (3) the two
  responses were simply concatenated in one buffer with no protocol
  cause at all. `MailDropSession` gained an optional raw trace callback
  right after this fix (`trace: Callable[[str, bytes], None]`,
  `("tx"|"rx"|"discard", data)`, P35.1 — `None` by default, no behaviour
  change unless a caller wires it; `tools/hw_check.py`'s
  `maildrop_session` subcommand does), and the very next hardware run
  settled it: with `MDCHECK\r` alone, the prompt comes back clean and
  `L` answers normally — **10/10 `maildrop_session` steps PASS**, full
  MailDrop protocol (`L`/`S`/`SB`/`R`/`K`/`B`/`<`-foreign-FROM) confirmed
  identical on MBX and PACTOR generations. Independently of that:
  `parse_error()`
  now only looks at what comes after a command's own echoed line
  (`protocol.split_after_echo()`, matched on `<command>\r\n` as a whole
  unit — a bare substring search would wrongly match `L` inside the
  prompt's own `(B,E,K,L,R,S)` command list) — a stray leftover fragment
  in front of the real echo can no longer be misattributed to the
  following command's result.
- **A Windows console turns a typed Ctrl-Z into an `EOFError`, not the
  two literal characters `^`/`Z` (found 22.09.2026, P23).** An operator
  trying to end a MailDrop message with the real Ctrl-Z key closed the
  whole console input instead of sending `$1A` — the tool ended up
  finishing the message with `/EX` in its cleanup path, so `$1A` was
  never actually exercised that round. Any interactive tool prompt that
  wants to offer `^Z` as an in-band control character must (1) tell the
  operator to type the two literal characters instead of pressing the
  key, and (2) still treat a genuine console `EOFError` gracefully if it
  happens anyway — `tools/hw_check.py`'s mailbox terminal now reads an
  `EOFError` while inside message entry as "end the message" (sends
  `$1A`) rather than as "close the terminal", falling back to the normal
  close behaviour only if the console's `input()` stays broken
  afterwards.
- **Verbose-mode response format, confirmed against real hardware
  21.09.2026** (P15, `hw_logs/`): a query answers
  `'<echo>\r\n<Name mixed-case>   <value>[ (<explanation>)]\r\ncmd:'`
  (e.g. `'USERS\r\nUSers     1\r\ncmd:'`); a set answers
  `'<echo>\r\n<Name>   was <old>\r\n<Name>   now <new>\r\ncmd:'`; an error is
  any line starting with `?` (`?What?`, `?bad`, `?callsign`). `tools/
  hw_check.py::parse_query_value()` is the single place that parses this —
  do not re-derive it ad hoc (`str.split()[-1]`-style parsing on the raw,
  multi-line response was the root cause of three of the four bugs found in
  the first hardware run, see Backlog.md/P15 history).
- **Every Host Mode data frame answers `ctl=0x5F ch=15 data=b'XX\x00'`**
  (observed 21.09.2026, T101). Not an error frame — meaning pending a TRM
  §4.4 check.
- **No `$3F` self-echo of the app's own transmissions, even at `MONITOR
  6`** (observed 21.09.2026, T101) — the PK-232 does not show frames it
  transmitted itself back through the Host Mode monitor path, so code must
  not wait for a `$3F` echo of its own TX as a "sent" confirmation.
- **68 P13 upload commands hardware-confirmed, zero `?` errors (T103,
  21.09.2026):** `USERS`, `RESPTIME`, `ACRPACK`, `CFROM`, `DFROM`, `MFROM`,
  `MTO`, `8BITCONV`, `HID`, plus every other command
  `ParamsUploader._build_commands()` sends. `ACRPack was ON` / `ACRPack
  now ON` confirms the P13 `AERPACK`→`ACRPACK` rename was correct.
- **The TNC has no RAM buffer battery at all (confirmed by the operator,
  22.09.2026)** — it resets to factory defaults (`MYCALL PK232`,
  `EXPERT OFF`, `PACLEN 128`, `MAXFRAME 4`, `FRACK 4`, the stock AEA
  `MTEXT`, an empty MailDrop mailbox) on **every** power-off, not just
  occasionally. This confirms and closes the "likely cause" guess from
  the 21.09.2026 hardware run (`MYCALL` reading back `PK232` after a
  power cycle was the tell). Consequences: the app's own init sequence
  (`ParamsUploader` + each mode's `get_activate_frames()`/
  `get_init_frames()`) is the **only** source of TNC configuration —
  nothing the operator sets by hand on the TNC survives a power-off, and
  MailDrop content is lost every time too (Backlog.md: saving/reloading
  the mailbox is a required feature, not a nice-to-have, because of this).
- **The PK-232 can hang and stop responding to anything at all, even the
  wakeup `*` — this is a hardware fault, not a software bug (P31,
  observed 23.09.2026).** The 18:01 wakeup failure that day was traced to
  exactly this: the TNC itself was locked up, not `SerialManager`'s wakeup
  logic. **Triage order:** before suspecting the app or its serial code,
  open a plain terminal program (PuTTY or similar) on the same COM port
  and check whether the device answers `*` at all, independent of
  pk232py. If it doesn't, the app cannot fix it either — **the only known
  remedy is a power-cycle** (off, then on). Do not spend time debugging
  `SerialManager`/Host-Mode code against a hung TNC; confirm the hardware
  is alive first.

### Packet (HF / VHF)

- **PASSALL = `PX`, not `PA` and not `PS`** — see the mnemonic-table note above.
- **HF/VHF init-frame inheritance trap.** `HFPacketMode.get_init_frames()` now
  emits `VH N` + `HB 300` + `MX <maxframe>` + `SL <slottime>` + `MN Y` (selects
  the 300 Bd HF FSK modem and resets MAXFRAME/SLOTTIME to HF Packet's own
  configured values — `maxframe`/`slottime` constructor args, defaulting to
  `HFPacketConfig`'s own defaults, 1/30, P18.1/P19.3). `main_window.py`
  builds it with the real configured values in `_build_mode_instance()`,
  the ONE place that happens (P19.2 — see §7 and the "UI / PyQt6" gotcha
  on why every `set_mode()` call must route through it).
  `VHFPacketMode` therefore must **NOT** call `super().get_init_frames()` — that
  `VH N` would immediately undo the `VH Y` it sends in `get_activate_frames()`
  and drop VHF back to the HF modem. VHF builds its own list (`HB 1200`, `MX 4`,
  `SL 10`, `MN Y`). Leaving VHF Packet also sends `VH N`
  (`_on_mode_selected` → `VHFPacketMode.vhf_off_frame()`, T51).
- **Rule: any parameter one band sets on activation, the other band must
  set too — otherwise it keeps whichever value the last-active band left
  behind.** Found via `SLOTTIME` (T112, hardware-confirmed 2026-09-22):
  VHF Packet sets `MX 4` / `SL 10` on activation; HF Packet did not reset
  them on its own activation, so a VHF → HF switch left HF Packet running
  with VHF's `SLOTTIME 10` instead of its own configured value. Fixed in
  P18.1 (`HFPacketMode.get_init_frames()` now sends `MX`/`SL` too) — but
  the rule is general, not specific to these two mnemonics: any future
  parameter one band's `get_init_frames()`/`get_activate_frames()` sets
  needs the same reset on the other band, or it inherits a silent
  cross-band leak like this one. `MAXFRAME`'s own T112 result was
  INCONCLUSIVE on the first run (it already equalled VHF's value before
  the test started) — `tools/hw_check.py t112` now pre-sets both to a
  neutral value first so this can't happen again (P18.3).
- **Connect ↔ Unproto are mutually exclusive (T39).** `set_link_state()` greys
  `btn_unproto` while connected/calling; `_on_packet_unproto()` greys
  `btn_connect` while Unproto is on (link-busy proxy = `btn_disconnect.isEnabled()`).
- **Two parallel Host Mode frame decoders — `comm/frame.py::FrameParser` vs
  `comm/serial_manager.py::_make_host_frame()`.** `FrameParser` is used by
  `tools/mock_tnc_bbs.py` and the Host Mode subprocess path; `_make_host_frame()`
  is what `SerialManager`'s reader thread actually builds `HostFrame`s with
  for a **connected TNC at runtime** — the one that matters for the real app.
  They re-implement the same CTL-byte mapping independently and can drift:
  `_make_host_frame()` hardcoded `channel=15` for every CTL byte except `$3x`
  until the 2026-09-20 fix ("Fix channel nibble extraction for 4x and 5x
  frames") — a pre-existing bug (commit ff17aa01, 2026-04-24) that was
  invisible until the ChannelBar sprint became the first code to actually use
  the channel of a $5x LINK_MSG frame. **Still open, deliberately not
  touched:** `_make_host_frame()`'s `elif` chain has no branch for `$40–$4E`
  (LINK_STATUS) — those frames fall through to `else` and are built as
  `CMD_RESP` instead, possibly the same root cause as the "HFPacket/VHFPacket:
  CMD_RESP reaches mode" item further down — needs a hardware test before
  fixing (see Backlog.md Priority 1). Consolidating the two decoders into one
  is filed as tech debt, not done in this sprint (serial-layer changes were
  explicitly out of scope beyond the one-line channel-nibble fix).
- **Channel model (2026-09-20, ChannelBar sprint).** There is **no CSTATUS
  poll in Host Mode** — the PK-232 never tells the host "channel N is
  connected to X" on demand. The channel a frame belongs to lives only in the
  low nibble of that frame's CTL byte (`ctl_channel()` in `comm/constants.py`
  — see the two-decoders gotcha above for where that nibble is actually
  extracted at runtime). So the UI's channel model is purely local
  bookkeeping, built entirely from frames that already went by:
  `HFPacketMode.on_channel_state(channel, state, partner)` derives
  free/calling/connected from the same $5x link messages `on_link_message`
  already parses (`_extract_partner()` does best-effort callsign extraction
  from strings like `"CONNECTED to OE1XYZ-5"`), and feeds
  `ChannelBar.set_channel_state()` in `packet_screen.py`. `ChannelBar` (10
  chips, channels 0–9) is the single source of truth for "which channel do
  Connect/Disconnect/TX act on right now" — `PacketBaseScreen.current_channel()`
  is a thin proxy to `channel_bar.current()`. MainWindow no longer hardcodes
  channel 1 anywhere in the Packet connect/disconnect/TX path — see
  `_on_chip_connect_requested`/`_on_chip_disconnect_requested`/`_on_packet_tx_enter`
  (P42, 2026-09-24, renamed from `_on_packet_connect`/`_on_packet_disconnect`
  — see the "connect in the chip" bullet below).
- **Every `$5x` link message carries its own channel number in the CTL
  nibble — three consumers now use it, not two (P47, 2026-09-25).**
  `HFPacketMode._handle_link_msg()` reads `frame.channel` and calls
  `on_link_message(ch, text)`. Two consumers were already channel-aware:
  `_make_channel_state_handler()` (chips/MHEARD) and the Unproto-gating
  logic inside `_make_link_handler()` (T102). A third consumer,
  `_on_mode_link_message()`'s RX-window display, used to ignore the
  channel entirely and always write into whichever screen/channel the
  operator happened to have open — reproduced 25.09.2026 (screenshot): a
  channel-1 "Retry count exceeded ... DISCONNECTED: OE3XTC" appeared on
  the UI chip (channel 0). Fixed: `_make_link_handler()` now routes a
  channel-bearing call through `MainWindow._route_packet_link_message()`
  → `screen.append_channel_data(channel, text)` (reusing the existing
  ALL/CH document-per-channel model and its compact `n│` tag, P50,
  rather than reimplementing it — see the next bullet for the tag's
  current format, changed from the original `[CHn]`);
  channel 15 (`$5F`, not channel-scoped — e.g. the generic data ack) and
  AMTOR/PACTOR's single-argument calls (channel is `None`, no channel
  concept at all) are unaffected. **Never attribute a link message by
  callsign** — "Retry count exceeded" carries none, and the same station
  can be connected on two different channels at once; the CTL-nibble
  channel number is the only reliable source. Optional mirror into the
  UI channel: `HFPacketConfig.show_link_messages_in_ui_channel` (default
  off) — see the "PC-side display settings" gotcha under Parameter
  dialogs.
- **A channel-offset report could not be reproduced in code — verified,
  not guessed, and the measurement path was strengthened either way
  (P50 Teil A, 2026-09-25).** Screenshot, 25.09.2026 19:07: chip 1 green
  with `OE3TEC` ("Ch 1 Partner: OE3TEC"), but every received line and
  the eventual `*** DISCONNECTED: OE3TEC-1 ***` tagged `[CH2]` (the old
  ALL-view tag format at the time). Audited every step of the channel
  path end to end: `HFPacketMode.connect_frame()` →
  `SerialManager.send_channel_command()` → `build_ch_cmd()` (`ctl = 0x40
  | channel`) on the way out; `_make_host_frame()` → `ctl_channel()`
  (`ctl & 0x0F`) on the way in; `ChannelBar._chips`/`_state`/`_partner`
  are plain `dict[int, ...]` keyed directly by channel number, no
  positional/0-based indexing anywhere. All of it symmetric — **no
  code-level offset found**. This does not rule out a genuine TNC-side
  behaviour (e.g. the PK-232 itself reassigning or reporting a different
  channel than requested) — that can only be settled by measuring a real
  device, which this investigation could not do. What WAS already true:
  the exact measurement the spec asked for — the sent CO frame's CTL
  byte, and the channel of every incoming `$3x`/`$5x` frame — was already
  fully available via existing DEBUG logging
  (`_ReaderThread.run()`'s `logger.debug("RX %r", frame)`, whose
  `HostFrame` repr includes `channel`; `HFPacketMode._handle_rx_data()`/
  `_handle_link_msg()`'s own `ch=%d`/`ch%d` lines). Added one more,
  purely for convenience: `SerialManager.send_channel_command()` now logs
  the requested channel right next to the actual CTL byte it puts on the
  wire, in one line, for CONNECT/DISCONNECT specifically — so a hardware
  capture does not need to cross-reference a separate hex dump to confirm
  `build_ch_cmd()` encoded the right channel. **Root cause of the
  25.09.2026 report is still open — needs a real hardware capture**, not
  a guess.
- **Channel 0 is the UI/unproto/monitor channel, not a QSO channel (P10,
  2026-09-20).** AEA Host Mode only has `$2x` for outgoing data with
  `x` = 0–9 — there is no `$2F`. So Unproto is not its own channel; it is the
  state of a channel with no connection, and the TNC sends whatever goes out
  on it along the configured UNPROTO path. Receive side already draws this
  line: `$3x` is connected-station data on channel x, `$3F` is monitored
  traffic with no channel of its own. Consequence: channel 0 is reserved as
  the UI channel (`UI_CHANNEL` in `packet_screen.py`), channels 1–9 stay QSO
  channels — `CHANNEL_COUNT` is still 10, there is no eleventh channel.
  `ChannelBar.set_channel_state(0, …)` is a no-op (channel 0 can never become
  calling/connected) and `channel_map()` never includes it; its chip shows
  `"UI"` instead of `"0"` with its own fixed fill colour, all in
  `_update_chip()` (one place, not scattered). `_on_packet_unproto()`
  (`main_window.py`) just calls `channel_bar.set_current(0)` — turning
  Unproto on/off no longer touches Connect/Disconnect directly; that is
  `_on_packet_channel_changed()`'s job now (`set_link_state(channel_bar.state(
  channel))`, which also turns Unproto back off if it was still on when
  moving to a QSO channel — the T39 mutual exclusion, rebased onto channel
  selection instead of a direct button lock; P42, 2026-09-24: since there
  are no more Connect/Disconnect buttons at all, `set_link_state()` now
  only ever touches Unproto's own enabled state — see the "connect in the
  chip" bullet below). This is also consistent with the rest of the app:
  every non-Packet operating mode already only ever uses channel 0 (TRM 4.3).
- **Connect happens IN the chip, not in a separate row (P42, 2026-09-24).**
  The old `Connect · Dest · … · Disconnect` row is gone — `btn_connect`,
  `btn_disconnect`, `cb_dest`, `btn_connect_dialog`, `dest_callsign()`,
  `set_dest_callsign()`, `add_dest_history()` no longer exist anywhere in
  the Packet code path. Reasoning: the channel is the place a connection is
  made, so a connect can never land on a channel other than the one being
  looked at — and it removes the P41 failure class (an input field living
  in its own row, one keyboard-redirect exception away from swallowing
  every keystroke) by construction, since there is no other row left to get
  that exception wrong on (see `ChannelChip`'s own docstring in
  `packet_screen.py`). Operation:

  | Action | Result |
  |---|---|
  | Click a different chip | switches the current channel only |
  | Click the already-current free chip, or double-click any free chip, or "Connect…" in its context menu | opens that chip's inline callsign editor |
  | Enter with a valid callsign in the editor | `ChannelBar.request_connect()` → `connect_requested(ch, callsign)` → `MainWindow._on_chip_connect_requested()` sends `CO` on that channel |
  | Enter with an invalid callsign | editor stays open, red border + tooltip, no signal |
  | Esc, or losing focus, while editing | closes the editor, no signal |
  | "Connect via…" in a free chip's context menu | `PacketConnectDialog` (callsign + optional digipeater path, channel fixed to the chip that opened it) |
  | "Disconnect" in a busy chip's context menu, or Ctrl+D while that channel is current | `disconnect_requested(ch)` → `MainWindow._on_chip_disconnect_requested()` sends `DI` on that channel |
  | Double-click an unconnected MHEARD row | `ChannelBar.start_edit_first_free()` — opens the FIRST free chip's editor, prefilled with the heard callsign (not necessarily the currently selected chip) |
  | Enter in `le_unproto`/`combo_monitor`/`combo_hbaud` while no chip editor is open | opens the current chip's editor (`ChannelBar.start_edit_current()`) — none of those three fields had a `returnPressed` behaviour of their own to shadow |

  Channel 0 (UI channel) and any busy chip never open an editor at all —
  enforced once, in `ChannelChip.start_edit()`/`_show_menu()` — so
  `_on_chip_connect_requested()` needs no channel-0 guard of its own
  (defense-in-depth was deliberately NOT added there; there is no code path
  left that could reach it with channel 0). `PacketConnectDialog` no longer
  has an editable channel field (it used to be a `QSpinBox`) — the channel
  always comes from whichever chip's "Connect via..." entry opened it.
- **Chip colour states, and the same semantics for MHEARD (P44,
  2026-09-25).** Four states, one meaning everywhere in the Packet screen
  (chip fill AND MHEARD's connected-station colour):

  | State | Colour | Label | Notes |
  |---|---|---|---|
  | `CH_FREE` | grey | channel number | -- |
  | `CH_CALLING` | pulsing amber | `<callsign> ...` (ellipsis) | pulse: one shared `QVariantAnimation` for the whole bar (not one per chip, so every calling chip pulses in sync), 1.2s cycle, `InOutSine`, low-high `#8a6a1e`/`#b08a2a` via a mid-cycle keyframe (not start/end alone -- that would sawtooth-snap at the loop point instead of oscillating); starts the instant any chip becomes calling, stops the instant none are; text colour stays fixed so the label reads steadily |
  | `CH_CONNECTED` | green | callsign | MHEARD's own connected-station colour uses this exact value (`_CHIP_FILL[CH_CONNECTED]`) -- legend says "green = connected", not "amber", which is what it said before this fix (contradicting the chip's own amber-means-calling) |
  | `CH_FAILED` | red, `_FAILED_FLASH_MS` (1.5s) | channel number | transient -- `ChannelBar` reverts it to `CH_FREE` on its own; a `set_channel_state(ch, CH_FREE, ...)` call while the channel was `CH_CALLING` becomes this instead of snapping straight to free (a calling-to-free transition is, by definition, a failed attempt: retry count exceeded, busy, or a DISCONNECTED that arrived before ever reaching CONNECTED -- `HFPacketMode._handle_link_msg()` already routes all three through `on_channel_state(ch, "free", "")`; "Retry count exceeded" only gained this in P44, it used to reach neither `on_link_message` nor `on_channel_state`'s free branch and left the chip calling forever); a channel that WAS `CH_CONNECTED` (a normal, successful hangup) skips this and goes straight to free -- there is nothing that failed there. Counts as free for interaction (its context menu, opening the inline editor) -- a chip that just failed is exactly where a retry is most likely, so it is never locked out for the flash's duration. |

  Still entirely driven through `set_channel_state()` (P18/P16's existing
  channel-state path) -- P44 added no new callback route, only new
  behaviour inside that one method. See the QTimer-parenting gotcha under
  UI/PyQt6 for a real bug this feature's own timer hit and how it was fixed.
- **The channel bar always shows ten chips, but `USERS` decides how many
  actually work (P11, 2026-09-20).** `ChannelBar` can display channels 0–9
  regardless of hardware capability — but the PK-232 itself only accepts as
  many simultaneous AX.25 connections as its `USERS` parameter allows
  (default **1**). Without raising `USERS`, chips 2–9 stay dead in real
  operation; that is expected TNC behaviour, not a UI bug. `USERS` lives in
  `HFPacketConfig.users` (shared by VHF Packet — there is no separate
  `VHFPacketConfig`), is set via the HF Packet Parameters dialog
  (`self._sb_users`, range 1–10) and uploaded in verbose mode as the
  `USERS` command (`comm/params_uploader.py`) — **not** the Host Mode
  mnemonic `UR`; changing `USERS` at runtime in Host Mode is out of scope.
  `ChannelBar.set_user_limit()` only ever adds a tooltip line to chips above
  the limit — deliberately no lock/grey-out/colour change, since it is
  unconfirmed whether `USERS` also blocks *outgoing* connects on higher
  channels (it is documented as limiting *accepted*, i.e. incoming, ones) —
  see Testplan T104/T105 for what is still open on real hardware.
- **Every channel has its own RX document; ALL/CH switches the document,
  it does not filter at append time (P50, 2026-09-25 — supersedes the
  v0.1 "append-time filter" design).** The old model kept everything in
  ONE `QTextEdit` and `append_channel_data()`/`append_monitor_data()`
  decided per line whether to write it at all — switching to a channel
  in CH view therefore only ever showed what arrived AFTER the switch,
  never its prior history. `PacketBaseScreen._rx_docs: dict[int,
  QTextDocument]` (one per channel, 0–9) plus `_rx_doc_all` (a merged,
  chronological log of everything) replace this: every line is written
  into BOTH its own channel's document and `_rx_doc_all` — costs memory,
  buys back the channel's full history on every switch.
  `_sync_rx_document()` just re-attaches `rx_display` to whichever
  document `_view_all`/`current_channel()` implies (called from
  `set_view_all()` and `ChannelBar.channel_changed` via
  `_on_rx_channel_switch()`), saving/restoring each document's own
  scroll position (`_rx_scroll`) so switching back and forth does not
  reset your reading position. `reset_channels()` clears every document.
  Each document is capped via `QTextDocument.setMaximumBlockCount()`
  (`HFPacketConfig.rx_max_lines_per_channel`, default 5000,
  PC-side/`UPLOAD_EXEMPT` like `show_link_messages_in_ui_channel`).
  **Display formatting changed alongside this:** a channel's own
  document gets NO channel prefix at all (the channel is already named
  by which chip/view is selected); `_rx_doc_all` gets a compact `n│`
  tag (channel digit + thin separator, `"UI│"` for the UI channel,
  matching the chip's own "UI" label) in a muted colour, replacing the
  old `[CHn]` bracket form. A timestamp (`[HH:MM:SS]`, also muted) is
  now OFF by default (`HFPacketConfig.show_timestamps`) — costs a third
  of the line width when always on. A system/link message keeps (or
  gains) its own eye-catching colour (`_SYSTEM_MSG_COLOR`, amber) via an
  explicit `color=` override to `append_channel_data()`, distinct from
  plain channel data (blue) and monitor traffic (grey) — never muted
  like the tag/timestamp.
  **The pre-existing `_packet_raw_frames` buffer + `_packet_rx_redraw()`
  (APRS raw↔decoded toggle, T59/T60) still exists, but now only rebuilds
  the UI channel's OWN document** (`PacketBaseScreen.
  clear_monitor_channel()`/`append_monitor_data_local_only()`) — never
  `_rx_doc_all`, which is a chronological log of everything that has
  already arrived from every channel; rebuilding it on an APRS toggle
  would either duplicate every historical monitor line (through the
  normal dual-write path) or drop every QSO-channel line recorded since
  (if cleared outright). This is a deliberate scoping decision, not an
  oversight — see `clear_monitor_channel()`'s own docstring.
- **RX/TX is a `QSplitter` now, not a fixed five-line TX height (P50
  Teil D, 2026-09-25).** The RX window used to be added with
  `stretch=1` directly into the screen's own `QVBoxLayout` and the TX
  row right after it at a hard `setFixedHeight()` — RX therefore never
  grew to fill extra window height (a big empty area below it in the
  25.09.2026 screenshot), and the operator had no way to make the TX
  area taller or shorter. `PacketBaseScreen._rxtx_splitter`
  (`QSplitter(Qt.Orientation.Vertical)`) now holds both — RX has
  `setStretchFactor(0, 1)` (takes any extra space on a window resize),
  TX has `setStretchFactor(1, 0)` (stays put unless the handle itself is
  dragged) and keeps its old five-line height only as the STARTING
  `setSizes()` value, not a hard constraint; both panes have a
  `setMinimumHeight()` so neither can be dragged away entirely. Saved/
  restored in `MainWindow._save_window_geometry()`/
  `_restore_window_geometry()` alongside the window geometry itself, one
  `QSettings` key per Packet screen (`hfPacketRxTxSplitterSizes`/
  `vhfPacketRxTxSplitterSizes` — `_PACKET_RXTX_SPLITTER_KEYS`) — the
  Hold TX/Clear TX/Clear RX button column stays a fixed-size sibling
  layout inside the TX pane (`addStretch()` keeps it top-anchored), it
  does not grow when the handle is dragged.
- **MHEARD gains connection partners from live link messages, not just
  a manual Refresh (P50 Teil E, 2026-09-25).** Previously the list only
  ever grew from an `MH` poll (`MainWindow._on_packet_mheard()`), which
  only runs on a button click — a station you just connected to would
  not appear until you remembered to press Refresh. Now
  `_make_channel_state_handler()`'s callback (already fed channel+state+
  partner by `HFPacketMode._handle_link_msg()` for every CONNECTED/
  CALLING("connect request")/FREE(DISCONNECTED, busy) transition) calls
  `MheardPanel.add_entry_if_new(partner, now)` whenever `partner` is
  non-empty — never for "Retry count exceeded" (`_handle_link_msg()`
  splits that into its own `elif`, passing `""`, precisely because it
  carries no callsign at all and `_extract_partner()`'s bare-first-token
  fallback would otherwise misread the message text itself as one).
  `add_entry_if_new()` is deliberately NOT `add_entry()` with a dedup
  check bolted on — it never updates an existing row either, so a
  station mentioned repeatedly (several DATA exchanges on one QSO) does
  not accumulate duplicate entries. Channel number and green colour
  still come from the existing `set_channel_map()` call, unchanged. A
  real CONNECTED, or a genuine DISCONNECTED of a link that was actually
  up (checked via the chip's OWN prior state, `screen.channel_bar.
  state(channel)`, read BEFORE `set_channel_state()` updates it — a
  CALLING→FREE failed-attempt transition is deliberately NOT this),
  additionally fires ONE `_on_packet_mheard()` poll so the list also
  catches up on any OTHER stations heard in the meantime — reusing the
  existing Refresh implementation outright, not a second one.

### UI / PyQt6

- **"Connect" is ambiguous — TNC serial connection vs. station
  connection (P46, 2026-09-25).** The toolbar used to have its own
  `Connect`/`Disconnect` for the serial link to the TNC, sitting right
  above opmode screens (Packet's chip-based connect, PACTOR/AMTOR's own
  connect flows) that ALSO show a "Connect" — two different things, both
  visible on screen at once. Fixed by removing Connect/Disconnect/Host
  Mode/Recovery from the toolbar entirely — they live only in the TNC
  menu now, never duplicated as a toolbar button. *Rule:* any future
  control for "connect" must say what it connects (TNC serial port vs.
  AX.25/PACTOR/AMTOR station) either in its own label or by construction
  (e.g. it only ever appears on one screen) — never rely on position or
  context alone to disambiguate two different "Connect" buttons.
- **A raw-bytes mirror written synchronously can be torn apart by an
  async delivery of the REST of the same data arriving later (P49,
  2026-09-25).** `_on_verbose_mode_ready()` used to mirror
  `SerialManager.last_verbose_init_response` into the verbose terminal
  with one synchronous `_on_vt_rx_data()` call, then immediately append
  its own `[SYS] ...` lines. Reproduced 25.09.2026 (screenshot):
  `"PK-232M is u[SYS] TNC ready in verbose mode\n[SYS] Fast Init —
  parameter upload skipped\n[SYS] Verbose terminal ready (fast
  init)\nsing default values."` — the banner word "using" torn in half.
  Cause: the TNC's boot banner can arrive in more than one chunk, wider
  apart than the ~150ms trailing-quiet window `_init_tnc_thread()`'s own
  `read_until()` already waits out before returning
  `last_verbose_init_response` — the SECOND fragment then arrives via the
  freshly-(re)started `ReaderThread` (`raw_data_received` →
  `_on_raw_data_received()`) sometime AFTER the app's own synchronous
  `[SYS]` appends have already run. Fixed with a short buffering window:
  `_start_banner_collection()` seeds a buffer from
  `last_verbose_init_response` and arms a single-shot `_banner_timer`
  (300ms, deliberately more generous than SerialManager's own 150ms);
  `_on_raw_data_received()` re-arms it on every further byte while
  collecting instead of displaying immediately; `_finish_banner_collection()`
  (fires once nothing new has arrived for the whole window) inserts
  everything collected as ONE block, THEN appends `[SYS] TNC ready...`
  and starts the parameter upload — never interleaved. *Rule:* mirroring
  something that might still be arriving in pieces needs a quiet-window
  buffer, not a single synchronous read, or a later fragment can land
  in between whatever the caller does next.
- **Stray control bytes (`$00`-`$1F` except CR/LF/TAB, and `$7F`) must
  be filtered before display, not just logged (P49.B.2, 2026-09-25).**
  Same screenshot: boxes at the start of a line, from an unfiltered
  stray `SOH` (Host Mode framing byte) leaking into the mirrored banner
  text. `_filter_control_chars()` (module-level in `main_window.py`,
  right before the `MainWindow` class) is the ONE filter for verbose-
  terminal output, called from `_on_vt_rx_data()` — the single place raw
  TNC bytes become displayed text there. The raw bytes are unaffected —
  still logged in hex at `DEBUG` by `SerialManager` itself; this only
  changes what is DISPLAYED.
- **A free-floating `QTimer.singleShot(ms, callback)` can fire against
  widgets Qt has already destroyed — parent the timer to the widget it
  touches instead (P44, 2026-09-25, found via a real crash).** Chip's
  failed-connect flash (`ChannelBar._schedule_failed_clear()`, see the
  Packet chip-colour-states gotcha below) originally scheduled its
  1.5s revert with the bare classmethod `QTimer.singleShot(ms, lambda:
  self._clear_failed(ch))`. That timer belongs to the global Qt event
  loop, not to any widget — so it keeps `self` (the `ChannelBar`) alive
  as a *Python* object via the closure, but does nothing to keep its
  *C++* object tree alive. Running a single test file, a short-lived
  `HFPacketScreen` built by a test and then dropped was never around
  long enough for the callback to matter before pytest moved on; running
  the FULL suite, the screen's C++ objects got torn down while the
  pending 1.5s Python-side timer was still ticking, and when it fired,
  `self._lbl_num.setText(...)` raised `RuntimeError: wrapped C/C++
  object of type QLabel has been deleted` — inside a completely
  unrelated LATER test, corrupting its own pytest-qt exception capture
  (the exact same collateral-damage shape as the P41 stale-event-filter
  finding — a single test file never showed the failure, only the full
  suite did). **Fix:** a real `QTimer(self)`, parented to the widget
  whose state the callback touches and kept in an instance dict, reused
  per channel rather than a fresh one each time. Qt destroys a parented
  QTimer along with its parent's C++ object tree, so a dead `ChannelBar`
  simply never fires the callback at all, instead of firing it against
  freed memory. **Rule:** any `QTimer.singleShot()` whose callback
  touches `self`'s own widgets needs to ask whether `self` might not
  outlive the delay — if the answer isn't a clear no, use a parented
  `QTimer` instance instead.
- **Keyboard redirection to the TX window must exempt EVERY
  keyboard-input widget type, not just `QLineEdit`/`QTextEdit`
  (P41, 2026-09-24, hardware-confirmed).** Every opmode screen with a
  TX window redirects keypresses there so typing works without a prior
  click (§5/§6's EventFilter architecture) — the exception check that
  stops this from stealing focus from a real input field used to only
  recognise `QLineEdit`/`QTextEdit`. Found on the VHF Packet screen:
  clicking into **Dest** (`cb_dest`, an editable `QComboBox`) and typing
  a callsign put the characters in the TX window instead. **Root cause,
  confirmed by direct testing, not just code reading:** for an editable
  `QComboBox`, Qt delivers `FocusIn` and `QWidget.focusWidget()` results
  to the **combo box widget itself**, never to its inner `lineEdit()` —
  even when `.setFocus()` is called directly on that inner `lineEdit()`.
  `ScreenFocusController` (§6 Level 3) had `cb_dest.lineEdit()`
  registered, exactly as intended, and it still never saw a `FocusIn`
  event, because Qt never sent one to that object. A plain, non-editable
  `QComboBox` (Monitor, HBAUD on the Packet screen) has the same
  problem for a different reason — it was never registered with
  `ScreenFocusController` at all, since that class's own docstring only
  ever mentions `QLineEdit`. Morse's `sb_mspeed`/`sb_mweight`/`sb_mid`
  `QSpinBox` fields had the identical gap (no focus-controller at all
  on that screen). **Fix:** `screen_focus_controller.
  is_keyboard_input_widget(widget)` — a registration-free, parent-chain-
  walking check against `QLineEdit`, `QTextEdit`, `QPlainTextEdit`,
  `QComboBox`, and `QAbstractSpinBox` — is now consulted by
  `MainWindow.eventFilter()` ALONGSIDE (not instead of)
  `screen.focus_ctrl.is_active()`, and by each opmode screen's own
  Level-2 fallback filter (`amtor_screen.py`, `morse_screen.py`,
  `opmode_rtty_base.py` — shared by Baudot/ASCII, `packet_screen.py`,
  `pactor_screen.py`; NAVTEX/Signal/FAX have no TX window and no such
  filter at all). `ScreenFocusController` itself was kept, not retired —
  see §6 for the fuller reasoning. **NoFocus buttons and the channel
  bar's chips are deliberately excluded** (§5: `Qt.FocusPolicy.NoFocus`
  on every `QPushButton`) — focusing one of those must still redirect to
  the TX window exactly as before; `is_keyboard_input_widget()`'s type
  list does not include `QPushButton`/`QAbstractButton`, so this is
  unaffected. As a direct consequence, Ctrl+Up/Ctrl+Down channel
  stepping (bound to `tx_input`'s own keypresses) no longer fires while
  a Packet-screen input field has focus either — that bug was a
  side-effect of the same misrouting, not a separate fix.
- **A `set_mode(name)` call with no `mode_instance` silently loses
  configuration (P19, 2026-09-22).** `ModeManager.set_mode()` builds a
  fresh `cls()` whenever `mode_instance` is `None` — that instance only
  ever has the mode's constructor DEFAULTS, never `AppConfig`. P18.1 fixed
  this for exactly one call site (`_on_mode_selected()` picking "HF
  Packet"); the P19.1 investigation found a second real call site in
  `main_window.py` (`_update_host_mode_ui()`'s Host-Mode-entry default
  activation of "Baudot RTTY") that had never been fixed and would have
  silently done the same thing to any future mode needing configuration.
  Fix (P19.2): `MainWindow._build_mode_instance(mm_name)` is now the ONE
  place a configured mode instance is built; **every**
  `self._modes.set_mode(...)` call in `main_window.py` must route its
  `mode_instance` through it, even when the result is `None` — see §7.
  `tools/hw_check.py t112` cannot catch this class of bug: it builds its
  replay frames straight from config, bypassing the application's own
  mode-instantiation path entirely.
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
- **A signal-emitting QObject has two truths — the directly-set attribute and
  the value delivered through the signal queue — and they are not
  simultaneous (P36, 2026-09-24).** A method like `MailDropSession._set_state()`
  writes `self._state` as a plain Python attribute and only THEN calls
  `self.state_changed.emit(...)` — the attribute becomes visible to another
  thread (no Qt marshalling needed for a plain attribute) strictly *before*
  the signal is even queued, let alone delivered via `processEvents()`. Any
  test or application code that polls the plain attribute and then
  immediately asserts on or branches on a value some LATER signal (from the
  same worker function) delivers is exposed to a TOCTOU race — the attribute
  can already show the new state while the signal-carried data (e.g. the
  `failed`/`prompt_info` payload) hasn't arrived yet. **Rule: wait on the
  signal-delivered value you are about to use next, never on the plain
  attribute.** Confirmed root cause of a ~1-in-10 flaky failure in
  `test_maildrop_session.py` (`TestRecoveryPath::
  test_ends_in_failed_when_host_mode_never_confirms` polled `session.state`
  then asserted on `rec.failures[-1]`, populated by the `failed` signal one
  line later in `_enter_host_mode_or_fail()`) — fixed by waiting on the
  `rec.*` signal-recorder data instead; see Backlog.md "Flaky test found and
  fixed" (P36) for the full writeup. **Same pattern found outside the tests,
  not yet fixed:** `tools/hw_check.py`'s `maildrop_session` subcommand polls
  `md_session.state` directly (lines ~3364, 3368, 3376, 3391) after the
  `MaildropSessionRunner` finishes, to decide whether to run the HPOLL
  confirmation check — the surrounding `MaildropSessionRunner` itself
  already does this correctly (connects `state_changed`/`failed` and reacts
  to the signal, see `_on_state_changed`/`_on_failed`); only this later,
  separate wait loop reads the raw attribute. Low real-world impact (worst
  case: the "see its own failed() message above" log line prints before that
  message has actually been flushed), so left as-is — flagged here for the
  next time that code is touched.

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

### Parameter dialogs

- **A dialog widget must be wired in BOTH directions, or it silently discards
  input while looking fully functional (found via `USERS`, 2026-09-20).**
  `HFPacketParamsDialog`/`PACTORParamsDialog` load from and save to their
  config object via `_populate()`/`apply_to()`; `AMTORParamsDialog`/
  `BaudotParamsDialog`/`MiscParamsDialog`/`MailDropParamsDialog` take no
  config at all — `MainWindow` maps fields to/from their
  `set_values(**kw)`/`get_values() -> dict`. Either way, a widget that is
  built in `_build_ui()` but left out of the load method, the save method, or
  the `MainWindow` mapping (for the `set_values`/`get_values` dialogs) just
  keeps showing whatever it was constructed with — `USERS` did exactly this
  for months (range 0–26, hardcoded to `1` on every open, every change
  discarded). `src/pk232py/tests/test_param_dialogs_roundtrip.py` checks this
  mechanically for all six `&Parameters` dialogs (~100 widgets): every widget
  found via `findChildren()` must move some config field (Test A), every
  config field must round-trip through the dialog (Test B), and every field
  of all six configs must survive an INI save/load (Test C) — a field can be
  wired to the dialog and still vanish on restart if `ConfigManager`'s
  `_apply_*()`/`_build_*()` forgot it (found for `HFPacketConfig.txsmt`/
  `aerpack`/`alfpack`, 2026-09-20). A new widget with only half the wiring
  fails this test immediately instead of shipping silently broken.
- **The wiring chain has a FOURTH link the P12 audit above does not check
  (P13, 2026-09-20): widget → config field → INI file → `_build_commands()`
  → TNC.** `ParamsUploader._build_commands()` reads only the config
  dataclasses, never the dialog widgets, and turns out to have its own,
  independent gaps — a field can pass Tests A, B and C and still never
  reach the TNC. `test_param_dialogs_roundtrip.py`'s Test D checks this the
  same way as Test A (bump one config field, diff the built command list,
  no command-name mapping needed); `AppConfig.tnc` is excluded as a whole
  section (PC-side connection settings, not TNC parameters), not a
  per-field filter. First run found `HFPacketConfig.resptime`/`txsmt`/
  `aerpack` unsent, plus independent gaps in PACTOR (9 fields), AMTOR (4),
  Baudot (5) and Misc (2) that are exempted with a Backlog pointer rather
  than fixed blind — see Backlog.md "Upload coverage" for that follow-up.
  **`AERPACK` does not exist as a PK-232 command** — the TRM Host Mode list
  has `ACRPACK` (mnemonic `AK`) instead, so the field/dialog checkbox/
  upload command were renamed to `acrpack`/`ACRPACK` (INI still accepts the
  old `aerpack` key as a read fallback). **`TXSMT` does not appear in the
  PK-232 TRM command list at all** — possibly a different AEA product (PK-
  900, DSP-2232); the dialog spinbox is disabled with a tooltip explaining
  this, the field/INI entry stay for compatibility, and it is never
  uploaded. **`MBELL`** is absent from the TRM's 1987 list (may exist only
  on later MBX firmware) — wired to the dialog/INI, not uploaded until
  confirmed. Every new command name in `_build_commands()` needs a cited
  source (TRM section or `pk232_mnemonic_table.txt`) in its commit message
  — see the "never guess a mnemonic" rule elsewhere in this file, which
  applies just as much to verbose-mode command *names* as to Host Mode
  mnemonics.
- **A parameter dialog's "parameters updated" log message used to imply the
  TNC had just been reconfigured — it only saves the local config.**
  `ParamsUploader` only runs before Host Mode is entered; a change made
  through any `&Parameters` dialog reaches the TNC on the *next*
  initialisation, not immediately. All six now log "parameters saved — sent
  to TNC on next initialisation" instead.
- **PC-side display settings live in the same config dataclasses as real
  TNC parameters, wired the same way, just exempted at the upload step
  (P47, 2026-09-25).** `HFPacketConfig.show_link_messages_in_ui_channel`
  (HF Packet Parameters → Display tab) has no TNC command at all — it
  only controls whether `MainWindow._route_packet_link_message()` mirrors
  a link message into the UI channel. It still goes through the full P12
  wiring chain (widget ↔ config field ↔ INI) like any other field, and is
  listed in `test_param_dialogs_roundtrip.py`'s `UPLOAD_EXEMPT` with the
  reason "display setting, not a TNC parameter" so Test D does not expect
  it to change `ParamsUploader._build_commands()`'s output. *Rule:* a
  display-only setting is not a special case requiring its own storage
  mechanism — it is a normal config field that happens to be exempt from
  exactly one of the four wiring-chain tests.

### Repo / tooling

- **`CLAUDE.md` is tracked by git as lowercase `claude.md`** on the
  case-insensitive Windows filesystem. `git add CLAUDE.md` may not stage it —
  use `git add claude.md`.
- **Project docs are not in `pk232py_sources.txt`** — upload them to the Claude
  project knowledge separately. See §1.
- **A `.gitignore` pattern with no leading slash matches at every depth,
  not just the repo root** (found P25, 2026-09-22): a bare `maildrop/`
  line, added in the very first commit alongside genuine runtime-data
  exclusions (`pk232py.ini`, `qso_log.db`), silently matched
  `src/pk232py/maildrop/` too and excluded that whole source module from
  git from day one — with no error, no warning, nothing to notice short
  of `git log --all -- <path>` coming back empty. Any new `.gitignore`
  entry meant for a specific data directory must be anchored (`/name/`),
  never a bare directory name, or it can just as easily swallow a future
  source directory that happens to share the name.
- **Tests run via `.venv\Scripts\python.exe`, not the bare `python` on
  PATH** (found P25, 2026-09-22): this machine's plain `python` resolves
  to a system Python 3.14 install with no PyQt6 DLLs, so `python -m
  pytest` fails at collection with `ImportError: DLL load failed while
  importing QtCore` for every module that touches `comm/serial_manager.py`
  — a red herring that looks like a code regression. Always run
  `.venv\Scripts\python.exe -m pytest` (or activate the venv first).
- **The `Sources2Text.ps1` export is not evidence that a file is
  tracked by git — it reads the filesystem, not git.** A module can be
  fully present in `pk232py_sources.txt` and in the Claude project
  knowledge while never having been committed at all (exactly what
  happened to `src/pk232py/maildrop/`, above) — export coverage and git
  history are two independent questions; always check the latter with
  `git log --all -- <path>` / `git ls-files <path>` before trusting that
  a module's history exists.
- **A test that calls `MainWindow.close()` can hang the whole pytest
  process forever, not just fail (P42, 2026-09-24, found running
  `test_main_window_packet.py`'s full file for the first time after the
  P41 fixture-teardown fix was added).** `MainWindow.closeEvent()` calls
  `QMessageBox.question()` ("TNC is still connected. Exit anyway?")
  whenever `self._serial.is_connected` is true — and `test_main_window_
  packet.py`'s `_StubSerial.is_connected` is a class attribute hardcoded
  to `True` (the test bodies need that to exercise "connected TNC"
  commands). Under the `QT_QPA_PLATFORM=offscreen` platform used for
  headless test runs, a real modal `QMessageBox` still calls `exec()` and
  blocks — there is no display for a human to click a button on, and
  nothing auto-dismisses it, so the process hangs indefinitely rather
  than erroring. The `wired_vhf` fixture's teardown now sets
  `w._serial.is_connected = False` immediately before `w.close()` for
  exactly this reason. **General rule:** before calling `.close()` (or
  triggering any other path that can reach `closeEvent()`) on a
  `MainWindow` built with a stub/fake serial object in a test, check
  whether that stub reports "connected" — if so, flip it to disconnected
  first, or the close can silently hang the whole test run instead of
  failing loudly.
- **A `MainWindow` that is merely `.close()`d, not destroyed, still costs
  something in a long headless test run (P42, 2026-09-24).** Closing hides
  the window but does not delete the Qt object or stop its running
  `QTimer`s (e.g. the Packet screen's UTC clock, `_utc_timer`). A test file
  that builds many `MainWindow` instances via a function-scoped fixture
  (here, 28 uses of `wired_vhf` in one file) without destroying each one
  measurably slowed down later tests that call `show()`/`activateWindow()`/
  `QTest.qWaitForWindowActive()` under the offscreen platform — easy to
  mistake for a hang if only the first sign (a very long-running `pytest`
  process with near-zero measured CPU time) is checked, rather than letting
  it run to completion. The fixture teardown now also calls `w.deleteLater()`
  + `QApplication.instance().processEvents()` after `w.close()`.
- **A test that mutates `MainWindow._app_config` can silently overwrite
  the OPERATOR'S REAL settings file on disk (P47, 2026-09-25; closed for
  good by P48, 2026-09-25 — see below).**
  `ConfigManager()` with no path override — exactly what every plain
  `MainWindow()` in the test suite constructs — reads AND writes the
  real `~/.pk232py/pk232py.ini`, not an isolated test copy; `MainWindow.
  closeEvent()` auto-saves it unconditionally
  (`self._config_mgr.save()`), and every `wired_vhf`-style fixture calls
  `w.close()` in its teardown. A `TestLinkMessageAppearsInItsOwnChannel`
  test that set `w._app_config.hf_packet.show_link_messages_in_ui_channel
  = True` with no reset therefore wrote that value into the real INI
  file the instant the test finished — confirmed on disk
  (`show_link_messages_in_ui_channel = true` in the operator's actual
  `pk232py.ini`, port `COM7`, real callsigns) — and it then leaked into
  every LATER `MainWindow()` in the same pytest run (including other
  test files), failing three unrelated-looking tests in a full-suite run
  that had all passed individually. That specific case was fixed by hand
  (`try`/`finally` reset, explicit set at the start of each test) — but
  the root cause (every test seeing the real path at all) was still
  open, so the next incident might not be caught by luck the way this
  one was (only three tests happened to notice).
  **P48 closes the root cause: `tests/conftest.py`'s autouse
  `isolate_config_path` fixture now redirects EVERY `ConfigManager()`'s
  default path (`ConfigManager.__init__()` reads the
  `PK232PY_CONFIG_PATH` env var, P48.1) to a throwaway file under that
  test's own `tmp_path`, for every test in the suite, whether or not it
  touches a `MainWindow`/`ConfigManager` at all.** Isolation is now a
  property of the test environment, not the test author's memory —
  `test_config_isolation.py::TestRealConfigFileIsNeverTouched` (P48.3)
  builds a full `MainWindow()` lifecycle (construct, mutate a setting,
  close) and proves the real file is byte-for-byte unchanged afterward;
  confirmed by hand that removing `conftest.py` turns that test red. A
  test that still passes an explicit `path=` to `ConfigManager()` is
  unaffected — that always wins over the env var.

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