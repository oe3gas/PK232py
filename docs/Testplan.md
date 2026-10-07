# PK232PY — Test Plan
**Updated: 2026-09-26 — P58 backlog/testplan audit: T122 PASS on Device B (MailDrop session dialog); T130/T134/T135 hardware-confirmed; T127/T132 hardware findings added (chip states, recovery stage, MHEARD, channel-tag offset resolved); T131 firmware-label addendum**
**Previous stand: 2026-09-24 — T119 PASS on Device B (P37): 10/10 steps, LF cause confirmed as the P35 fix, /E trailer reclassified as regular**

---

## Change History

| Version | Files | Content |
|---------|-------|---------|
| v3 | `modes/morse.py`, `modes/amtor.py`, `modes/signal_analysis.py` | Mode name fixes |
| v4 | `main_window.py` | TX window yellow, `_flush_tx_buffer`, RX colour, Fast Init |
| v5 | `main_window.py` | Removed duplicate methods |
| v6 | `main_window.py` | No RC for Baudot/ASCII/Morse |
| v7 | `main_window.py` | `QApplication.instance().installEventFilter(self)` |
| v8 | `main_window.py` | Full TX logic in app-wide `eventFilter` |
| v9 | `main_window.py` | Buffer flush on SEND toggle |
| **v10** | `baudot_tx_controller.py` *(new)* | `BaudotTxController` — rate-limited TX, DATA_ACK, EOT |
| **v10** | `ui_theme.py`, `macro_store.py` *(new)* | Theme + macro extraction |
| **v10** | `opmode_rtty_base.py` | `TxInputWidget` |
| **v10b** | multiple | TX_MAX=512, paste fix, Help viewer |
| **v11** | `packet_screen.py` *(new)* | `HFPacketScreen`, `VHFPacketScreen`, `MheardPanel` |
| **v11** | `main_window.py` | Packet integration: `_wire_packet_buttons()` |
| **v12** | `screen_focus_controller.py` *(new)* | `ScreenFocusController` |
| **v12** | `main_window.py` | eventFilter fixes, identity label population, PACTOR screen guard |
| **v15** | `main_window.py` | Bug: CO/DI channel 0→1; `on_connect_toggled` naming fix |
| **v15** | `aprs_decoder.py` *(new)* | APRS decoder v3: Mic-E, Position, WX, Telemetry, HTML cards |
| **v15** | `packet_screen.py` | `btn_aprs` toggle, `APRS_CAPABLE`, `_STYLE_APRS_ON/OFF` |
| **v15** | `main_window.py` | `_packet_raw_frames` buffer, `decode_html()` path, dual-buffer redraw |
| **v16** | `tx_controller.py` *(renamed)* | `BaudotTxController` → `TxController`; `set_mspeed_ms()` added (cc2adff) |
| **v16** | `morse_screen.py`, `main_window.py` | Morse on TxController: `TxInputWidget`, `[^D]` EOT → RC, ACK-paced; `_is_txctrl_mode()` helper, `_MORSE_TXCTRL_MS=50` (437e8a1) |
| **v16** | `tx_controller.py`, `morse_screen.py`, `amtor_screen.py`, `main_window.py` | TxController: Morse (Paket 2a) + AMTOR (Paket 2b); CONNECTED triggers `on_send_start()`; PTOVER for ARQ EOT (8087564) |
| **2026-09-20** | `packet_screen.py`, `main_window.py`, `packet_hf.py`, `serial_manager.py` | Packet channel model: `ChannelBar` (10 chips), `cb_dest` history combo, ALL/CH RX filter, Capture, MHEARD channel column, `HFPacketMode.on_channel_state`; fixed `_make_host_frame()` channel-nibble bug (was hardcoded 15 for $4x/$5x); +T87–T93 |
| **2026-09-20** | `packet_screen.py`, `main_window.py` | P9 per-channel TX draft buffer (`_tx_buffers`/`_tx_channel`, `tx_text()`/`clear_tx()`); +T94–T97 |
| **2026-09-20** | `packet_screen.py`, `main_window.py` | P10: channel 0 reserved as the UI/unproto/monitor channel (`UI_CHANNEL`), Connect/Disconnect/Unproto now driven by channel selection; +T98–T101 |
| **2026-09-20** | `main_window.py` | Bugfix: `_make_link_handler()` gated `set_link_state()` to the visible channel only, not every link message; +T102 |
| **2026-09-20** | `config.py`, `params_hf.py`, `params_uploader.py`, `packet_screen.py`, `main_window.py` | P11: `USERS` parameter (max. simultaneous AX.25 connections) added to config, params dialog, upload, and `ChannelBar` advisory tooltips; +T103–T105 |
| **2026-09-20** | `test_param_dialogs_roundtrip.py` *(new)*, `params_hf.py`, `config.py` | P12: mechanical wiring audit for all six `&Parameters` dialogs; found and fixed `HFPacketConfig.txsmt` (dialog-unwired) and `.aerpack`/`.alfpack` (INI-unwired); +T106 |
| **2026-09-20** | `test_param_dialogs_roundtrip.py`, `params_uploader.py`, `config.py`, `params_hf.py`, `main_window.py` | P13: fourth wiring-chain link (upload) audited via Test D; sent `RESPTIME`, renamed `aerpack`→`acrpack`, disabled `TXSMT` (not a PK-232 command); closed the chain for `CFROM`/`DFROM`/`MFROM`/`MTO` access filters and `8BITCONV`/`HID`; corrected the post-dialog log message; +T107–T109 |
| **2026-09-21** | `tools/hw_check.py` *(new)* | P14: solo hardware CLI tool (T17/T86, T103, PTHUFF, T101), reuses `pk232py.comm` entirely; +T110 |
| **2026-09-21** | `tools/hw_check.py`, `test_hw_check.py` | P15: first real hardware run found the tool's own bugs — T86 queried verbose mode instead of Host Mode, and the restore logic mistook a stray `cmd:` prompt for a value. Added `parse_query_value()` against real captured responses and a restore that verifies itself; results recorded at T86/T101/T103/T110 |
| **2026-09-21** | `main_window.py`, `packet_screen.py`, `tools/hw_check.py` | P16: T86 second run found `hw_check.py` matching Host Mode responses by arrival order, so a stale `HP\x00` poll-ack was mistaken for the PX answer. Fixed with `select_response_frame()` (mnemonic-prefix match); real result: PASSALL is `PX`, not `PS` — the 2026-06-22 fix was itself wrong. `main_window._wire_packet_buttons()` toggle_map corrected; +T111/T112 |
| **2026-09-22** | `tools/hw_check.py`, `test_hw_check.py` | P17: measurement-only subcommands `siam` (60s unfiltered Host Mode frame capture, no assumption about SIAM's frame type or output format), `t111` (PASSALL toggles, PASS unaffected — same mnemonic as the app's toggle_map), `t112` (VHF→HF Packet MAXFRAME/SLOTTIME carry-over, replays the real mode-class frame sequence); no `src/pk232py/` changes; +T113 |
| **2026-09-22** | `packet_hf.py`, `main_window.py`, `signal_analysis.py`, `tools/hw_check.py` | P18: hardware results T111 PASS, T112 FAIL (SLOTTIME confirmed), T113 measurement complete (SIAM = `$50` LINK_MSG on ch0, split across two frames). `HFPacketMode.get_init_frames()` now resets `MX`/`SL` from HF's own config (constructor args, wired via `ModeManager.set_mode(mode_instance=...)`); `SignalMode` assembles the two-frame results and never treats CMD_RESP as one; `hw_check.py t112` pre-sets neutral MAXFRAME/SLOTTIME and judges them separately; +T114 |
| **2026-09-22** | `main_window.py`, `packet_hf.py`, `packet_vhf.py`, `signal_screen.py` | P19: found a SECOND `set_mode()` call site (`_update_host_mode_ui()`'s Host-Mode-entry default) that P18.1 had missed — a future config-carrying mode there would have silently gotten constructor defaults. `MainWindow._build_mode_instance()` is now the one place any mode instance is built with configuration; `HFPacketMode`'s own defaults now derive from `HFPacketConfig` instead of repeating the numbers; `SignalScreen` wired to `SignalMode.on_result_parsed` (was never wired to anything), shows latest + best-so-far result; T114 concretized with the wiring now in place |
| **2026-09-22** | `tools/hw_check.py`, `test_hw_check.py` | P20: corrected `pk232_mnemonic_table.txt`'s status (a failed 676-combination scan misdescribed as hardware evidence in P13/P14, see `docs/MNEMONIC_TABLE_NOTE.md`); new subcommands `mi` (query-only, does the MailDrop button's `MI` actually read back the same as `MFILTER`?) and `maildrop` (guided, mitschreib-style local MailDrop recording terminal — protocol unknown, so no script); no `src/pk232py/` changes; +T115/T116 |
| **2026-09-22** | `tools/hw_check.py`, `test_hw_check.py`, `main_window.py`, `packet_screen.py` | P21: real hardware run (T115/T116) found MI = MFILTER confirmed (FAIL) and a tool safety bug — after MailDrop's `B` silently closed the mailbox, typed input reached the TNC command interpreter, where `K` = CONVERSE. `parse_query_value()` now finds the value line by content, not position (async SIAM output interleaves into other responses); `Session.normalize()` runs before every hardware subcommand; the mailbox terminal is a MAILBOX/ENTRY/CMD state machine that stops the instant `cmd:` is seen; `btn_maildrop` disabled, `_on_packet_maildrop()` is a no-op |
| **2026-09-22** | `tools/hw_check.py`, `test_hw_check.py` | P22: first full MailDrop hardware run (18:43, fixed tool) — T116 PASS for `L`/`S`/`R`/`K`/`B`, list format, numbering, memory accounting; all recorded in CLAUDE.md. Power-cycle confirmation reworked to a `done`/`skip` loop (a blank Enter used to be silently read as skip); recorder now sets `DAYTIME` (reusing `ParamsUploader._cmd()`) before `MDCHECK` so the list shows real dates; suggested sequence replaced with round-2's foreign-FROM/@BBS/bulletin/traffic-type/EDIT questions; added tool-only `parse_maildrop_list()`/`maildrop_response_has_e_trailer()` |
| **2026-09-22** | `tools/hw_check.py`, `test_hw_check.py` | P23: round-2 hardware run (19:16) confirmed `@BBS`, `SB`/`ST`, the date/time format and the power-cycle test - T116 PASS extended; the P22 "size + ~48 bytes" memory formula withdrawn (7 messages show 84 or 112 bytes, unrelated to size). Found and fixed two tool bugs the run itself exposed: `SB`/`ST` left the state machine at MAILBOX because ENTRY was detected from the typed command, not the response (now response-based, P23.2); a real Ctrl-Z keypress produces an `EOFError` on a Windows console, so `^Z` was never actually sent - `EOFError` in ENTRY now sends `$1A` instead of closing the terminal (P23.3). Round 3 sequence targets the two still-open questions (foreign FROM, `^Z` message end); `--skip-power-cycle` added since round 2 already passed it |
| **2026-09-22** | `tools/hw_check.py`, `test_hw_check.py`, `src/pk232py/maildrop/maildrop.py` (docstring only), `CLAUDE.md`, `Backlog.md` | P24: round-3 hardware run (20:00) closed T116 (foreign FROM confirmed, `^Z` confirmed NOT ending a message, `/E` trailer corrected to non-general, R-needs-a-space and non-ASCII-is-the-tool's-own-encoding findings); `maildrop.py`'s MailDrop Host Mode mnemonic table marked UNVERIFIED (same class of error as `MI`/T47 — nothing renamed, a future package's job) and filed as a Backlog Priority 1 (it is dead code today, but the 8 mnemonics it would send were never measured); new read-only `maildrop_host` subcommand (P24.2) probes the `$60`/`$70` MailDrop-login Host Mode data channel implied by `HOST 3`'s bit 1, never sends `S`/`K`/`E`, one `y/N` confirmation before any unknown frame goes out; +T117 (OPEN — not yet run) |
| **2026-09-23** | `serial_manager.py` (comment only), `tools/hw_check.py`, `test_hw_check.py`, `CLAUDE.md` | P26: T117's first hardware run (21:13) exposed a tool bug — `maildrop_host` mistook a bare `$5F` data acknowledgement for a real mailbox response and skipped Probe B; fixed with `has_mailbox_data_frame()` (P26.1). Corrected `serial_manager.py`'s wrong `HOST 3` comment ("undocumented poll level" → the real bit-field meaning; the byte sequence itself is unchanged). New read-only `mdcheck_scan` subcommand (P26.2) searches all 23 non-denylisted `M?` mnemonics for the one that answers with the mailbox prompt, since the TRM's own `MI` entry for MDCHECK contradicts T115's hardware-confirmed `MI` = MFILTER; stops at the first hit. No other `src/pk232py/` changes; +T118, T117 updated |
| **2026-09-23** | `maildrop/protocol.py` *(new)*, `maildrop/session.py` *(new)*, `maildrop/__init__.py`, `maildrop/maildrop.py` *(deleted)*, `test_maildrop_protocol.py` *(new)*, `test_maildrop_session.py` *(new)* | P27: MailDrop moves entirely to the verbose-mode link — MDCHECK has no Host Mode mnemonic (T118). `protocol.py` (pure parsing/command-building, fixtures from the real hw_logs/ transcripts) + `session.py` (`MailDropSession`, CLOSED/OPENING/ACTIVE/CLOSING/CLOSED + FAILED, background worker thread, Qt-signal-only results) replace the old `maildrop.py` (geraten/unverified Host Mode mnemonics, dead code). Both Host Mode transitions reuse `SerialManager.exit_host_mode()`/`enter_host_mode()` unchanged. `message_store.py`'s schema found NOT to cover a real archive's needs (no TNC message number/BBS/type, local not TNC timestamp) — left unchanged, recorded as a Backlog follow-up rather than migrated under this package; +T119 (OPEN — no UI yet, needs a script/prompt run) |
| **2026-09-23** | `tools/hw_check.py`, `src/pk232py/maildrop/session.py`, `test_hw_check.py` | P28: `maildrop_session` harness for T119 — drives the real `MailDropSession` end to end (open/list/send x3/list/read/kill/list/leave, plus an `--abort-test` probe for the recovery path), calling only its public API and reacting only to its signals, no protocol logic of its own. `MaildropSessionRunner` is the small step-sequencer (`MaildropStep` + validators against already-parsed `MailDropEntry` objects, never raw text). Added a small, targeted `MailDropSession.abort()` (checked once, right after a send()'s subject is accepted) so the harness's error-path probe has something real to call instead of fighting the busy-guard. T119 updated to point at the harness. |

---

## Test Environment

- TNC: AEA PK-232MBX, Firmware v7.1
- Software: PK232PY v0.1, Python 3, PyQt6
- OS: Windows 11
- Serial capture: AirDrive USB Logger
- APRS test signal: 144.800 MHz (OE3XWJ-10 digipeater area)

---

## Test Block 1 — Connection & Initialization

### T01 — Normal Connect + Host Mode
**Status:** ✅ OK (since v7/v8)

### T02 — Fast Initialization
**Status:** ✅ OK (since v4)

---

## Test Block 2 — Baudot RTTY TX/RX

### T03 — Focus without mouse click
**Status:** ✅ OK (since v7/v8)

### T04 — Receive (RECEIVE active)
**Status:** ✅ OK (since v4)

### T05 — Pre-type during RECEIVE then SEND
**Status:** ✅ OK (v10)

### T06 — Live typing during active SEND
**Status:** ✅ OK (v10)

### T07 — SEND → RECEIVE transition
**Status:** ✅ OK (v10)

### T08 — "Still to transmit" warning
**Status:** ✅ OK (v10)

### T09 — SEND button second click → RECEIVE
**Status:** ✅ OK (v10)

### T10 — ALT+X / ALT+R keyboard shortcuts
**Status:** ✅ OK (v10)

### T11 — CTRL+D EOT marker
**Status:** ✅ OK (v10)

### T12 — CTRL+D Backspace (atomic delete)
**Status:** ✅ OK (v10)

### T13 — Edit protection for sent chars
**Status:** ✅ OK (v10)

### T14 — Edit with Backspace in unsent zone
**Status:** ✅ OK (v10)

### T15 — Paste (CTRL+V)
**Status:** ✅ OK (v10b)

### T16 — TX buffer full
**Status:** ✅ OK (v10b)

### T17 — Clear TX during SEND
**Status:** ✅ PASS (2026-06-22, mock — software) — Clear TX during SEND sends the
mode stop command (`RC` for Baudot/ASCII/Morse, `AM` for AMTOR ARQ/FEC), empties
the TX window, calls `TxController.clear()` and drops the UI to RECEIVE. **Bugfix
2026-06-22 (Paket 3):** AMTOR now sends `AM` even though `_send_active` is never
set for it (no SEND/RECEIVE button — ARQ TX is CONNECTED-triggered, not
button-triggered); `_on_clear_tx()` sends `AM` unconditionally for AMTOR while
keeping the `_send_active` guard for the button modes. Hardware verify (incl. the
Morse-regression check below) still pending.

**Bugfix 2026-08-08 (UI-Repaint):** `btn_send` blieb nach Clear TX
optisch rot/aktiv (inkl. weiterlaufendem Blink-Timer), obwohl
`isChecked()` bereits korrekt auf RECEIVE stand. Ursache:
`blockSignals()` beim Umschalten in `_on_clear_tx()` unterdrückt
`_on_receive_toggled()` — genau dort (nicht am Checked-Zustand) hängt
die Stylesheet-Umschaltung und der `_blink_timer.stop()`. Fix: beides
in `_on_clear_tx()` explizit nachgezogen (STYLE_PROM_INACTIVE /
STYLE_RECEIVE_ON aus opmode_rtty_base importiert, blink_timer per
getattr() gestoppt bevor die Stylesheets gesetzt werden).
Betrifft Baudot RTTY, ASCII RTTY, CW/Morse (die einzigen Screens mit
btn_send/_blink_timer). AMTOR hat kein btn_send → getattr-Guard greift
korrekt ins Leere.

Verify on hardware: during SEND, type a long line, press **Clear TX** →
TNC must stop keying immediately (TX §7.2), window blanks, UI returns to
RECEIVE. Check per mode: Baudot/ASCII/Morse (`RC`), AMTOR (`AM` flush).
**Morse regression (the 2026-06-18 finding):** after Clear TX, go RECEIVE →
SEND again — **no** leftover characters may resume. With echo-pacing (§17.1)
the TNC holds ≤ 1 char, so at most one stray char is acceptable; a whole
buffered message resuming = fail. Also confirm Morse still keys smoothly
(no audible inter-character gaps from `_EAS_WINDOW=1`); if gaps appear, bump
`_EAS_WINDOW` to 2.
Verify visually on all three RTTY/Morse screens (Baudot, ASCII,
Morse — each has its own `_blink_timer` instance): after Clear TX
during active SEND, `btn_send` must show `STYLE_PROM_INACTIVE` (grey,
not blinking) and `btn_receive` `STYLE_RECEIVE_ON` immediately, with
no further colour flicker.

### T85 — Stop Sending via RECEIVE button (Paket 3)
Prerequisite: `python tools/mock_tnc_bbs.py --trace`

The RECEIVE button is the ergonomic TX stop for the button-driven modes
(Baudot/ASCII/Morse) — distinct from T17, which stops via **Clear TX**. AMTOR
has no RECEIVE button (its only stop path is Clear TX → T17).

1. Baudot/ASCII/Morse (Host Mode): press **SEND** (`XM` out), type text
2. Press **RECEIVE** while SEND is active

**Expected result:**
- `--trace` shows `RC` going out (`_on_screen_receive(True)` → `_on_screen_send(False)`)
- `_send_active` cleared; UI shows RECEIVE; unsent-text warning in the status bar
  if rate-limited chars remained
- AMTOR: N/A (no RECEIVE button — use Clear TX, T17 → `AM`)

**Status:** ✅ PASS (2026-06-22, mock — software) — RECEIVE during SEND sends `RC`
and returns the UI to receive; the `_send_active` guard prevents a second `RC`
from the blockSignals UI sync. Hardware verify pending.

### T86 — PASSALL mnemonic: verify correct frame byte on TNC (PS vs PX)
The PASSALL toggle sent `build_command(b'PS', …)` since the 2026-06-22 fix.
A Host Mode command-table reading suggests `PS` = PASS and **`PX` =
PASSALL** — i.e. the toggle needed `PX`, not `PS`.

1. HF/VHF Packet (Host Mode) → toggle **PASSALL** ON, then OFF
2. Observe on a real PK-232 whether PASSALL actually engages (receive bad-CRC
   frames) with `PS`; if not, retry with `PX`.

**Expected result:** the byte that actually toggles PASSALL is identified;
`main_window._wire_packet_buttons()` toggle_map is set to it.

**Preferred method (P14/P15/P16, 21.09.2026):** `python tools/hw_check.py
--port COM6 t17` — queries `PX` and `PS` in Host Mode (`SOH $4F PX ETB` /
`SOH $4F PS ETB`; no write, no on-air observation needed) and classifies
which one looks like a Y/N toggle. See `docs/HW_Solo_Tests.md`.

**Status:** ✅ PASS, 21.09.2026. Raw Host Mode frames: `PX` -> `PXN` (a
Y/N toggle), `PS` -> `PS$16` (the PASS masking character, factory default
`$16`/Ctrl-V) — **`PX` = PASSALL**, matching TRM 4.2.2. Two invalid runs
came before this result, same day: the first queried verbose mode, where
two-letter mnemonics do not exist (`?What?` for both, fixed in P15 to
query Host Mode); the second came back INCONCLUSIVE because a stale
`HP\x00` poll-ack from Host Mode entry was mistaken for the PX answer
(fixed in P16 — responses are now matched by mnemonic prefix, not arrival
order). `main_window._wire_packet_buttons()` toggle_map now sends `PX`
for `btn_passall` (was `PS`, itself a 2026-06-22 mistake — see the
correction note in Backlog.md's "Known bug — fixed" section).

### T18 — Multi-cycle colour test
**Status:** ⬜ OPEN

---

## Test Block 2b — CW/Morse TxController (Paket 2a / 437e8a1)

### T69 — Morse SEND: ACK-Färbung + genau 1 [TX] pro Zeichen
1. Host Mode aktiv → ComboBox → **CW / Morse** → **SEND**
2. Einige Buchstaben tippen (z.B. "CQ CQ")

**Expected result:**
- Jedes Zeichen erscheint nach DATA_ACK grün/ACK-gefärbt im TX-Fenster
  (identisches Verhalten wie Baudot RTTY)
- Im Monitor: genau EIN `[TX]`-Eintrag pro Tastendruck — kein Doppelsenden
- Sendefluss flüssig; stockt er → `_MORSE_TXCTRL_MS` in `main_window.py`
  senken (derzeit 50 ms)

**Diagnose bei Fehler:**
- Doppelsenden → `char_ready`-Guard in `_wire_mode_callbacks` prüfen
- Zeichen nicht gefärbt → `char_typed`-Verbindung zu `TxController` prüfen

**Status:** ✅ PASS (2026-06-18) — EAS-Färbung zeitkorrekt; Space-Echo
(668c903) und CR/LF-Stall (5dce1c0) behoben. Echo-Strom-Zeichenklassen
siehe TX_STATE_MACHINE.md §17.2.

---

### T70 — Morse CTRL+D EOT: wartet auf letztes Zeichen
1. SEND aktiv → Text "599" tippen → **CTRL+D** drücken
   ([^D] erscheint orange im TX-Fenster)
2. Nichts weiter tun — warten

**Expected result:**
- TNC sendet "599" vollständig aus
- ERST nach DATA_ACK des letzten Zeichens schaltet App auf RECEIVE (RC)
- Kein vorzeitiges Umschalten mittendrin

**Diagnose bei Fehler:**
- Schaltet zu früh → `_ack_idx`-zu-`_eot_positions`-Zuordnung in
  `tx_controller.py` prüfen

**Status:** ✅ PASS (2026-06-18) — CTRL+D wartet auf den echo-bestätigten
letzten Zeichen-Echo, dann RC.

---

### T71 — Morse Macro mit eingebettetem [^D]
1. Macro anlegen: Text + [^D] am Ende (z.B. "73 DE OE3GAS [^D]")
2. SEND → Macro-Button klicken

**Expected result:**
- Macro vollständig gesendet, danach RECEIVE
- Umschaltung erst nach letztem bestätigtem Zeichen — nicht mittendrin
- Kein Crash (war vorher latenter Bug: Macro-Pfad emittiert `char_typed`,
  das alte Plain-QTextEdit hatte dieses Signal nicht)

**Status:** ⬜ OPEN (Hardware-Test ausstehend)

---

### T72 — Morse WPM-Tempo: Software interferiert nicht
1. MSPEED-Spinbox auf verschiedene WPM-Werte setzen (z.B. 10, 20, 40 WPM)
2. Text senden, Tempo beobachten

**Expected result:**
- Sendetempo ausschließlich vom TNC (MSPEED-Einstellung) gesteuert
- Software-Timer (`_MORSE_TXCTRL_MS = 50`) bremst den Fluss nicht und
  läuft dem TNC nicht vor
- Kein BUFFER_FULL-Dialog bei normalem Text

**Status:** ✅ PASS (2026-06-18) — Tempo ausschließlich TNC-gesteuert
(echo-paced, §17.1); Software-Timer ist nur Sicherheitsnetz.

---

### T80 — Morse CR/LF im SEND: flüssiges Signal durch Zeilenumbruch
1. SEND aktiv → Text mit Zeilenumbruch tippen (z.B. "test" → **Enter** → "ende")
2. Morse-Signal und TX-Färbung beobachten

**Expected result:**
- Signal läuft **flüssig** durch den Zeilenumbruch — KEINE 4-s-Pause pro
  Folgezeichen (war der Stall-Bug: `\r\n` als echo-erwartend gezählt)
- Färbung bleibt synchron, kein +1-Versatz nach dem `\r\n`
- RX-Fenster zeigt den Zeilenumbruch
- Hintergrund: `\r\n` wird gesendet (2 Bytes `0d 0a`), aber vom TNC NICHT
  getastet und NICHT mit `$2F` geechot → aus dem Echo-Pacing ausgeschlossen
  (`_is_unkeyed`), im Echo-Scan übersprungen. Siehe TX_STATE_MACHINE.md §17.2.

**Status:** ✅ PASS (2026-06-18, commit 5dce1c0) — Hardware-verifiziert,
zusätzlich headless ("te\r\nst": emit t,e,\r\n,s,t; colour 0,1,2,3,4; rx
t,e,\n,s,t; inflight balanced).

---

## Test Block 2c — AMTOR TxController (Paket 2b / 8087564)

### T73 — AMTOR Link-Message-Text: CONNECTED erkennbar
**KRITISCH — muss als erster AMTOR-Test durchgeführt werden.**
Paket 2b aktiviert den TxController beim Empfang des Link-Message-Texts
"connected". Dieser Test verifiziert, dass der TNC tatsächlich diesen
Text schickt.

1. Host Mode aktiv → ComboBox → **AMTOR**
2. Monitor-Fenster öffnen (alle Frames sichtbar)
3. ARQ-Call zu einer zweiten AMTOR-Station aufbauen
   (btn_arq → Ziel-SELCAL eingeben → Verbindung abwarten)
4. Monitor beobachten während des Verbindungsaufbaus

**Expected result:**
- Im Monitor erscheint ein Link-Message-Frame mit dem Text
  "CONNECTED" (Groß-/Kleinschreibung egal, da `msg.lower()` verwendet)
- Unmittelbar danach im Monitor:
  `[AMTOR] CONNECTED → TxController started`
- Status-Pill auf AmtorScreen zeigt **● CONNECTED** (grün)

**Diagnose bei Fehler — CONNECTED-Text fehlt oder anders:**
- Monitor zeigt anderen Text (z.B. "LINK ESTABLISHED", "ARQ LINK UP"
  oder ähnliches) → `_make_link_handler()` in `main_window.py` anpassen:
  den `"connected" in m`-Check um den tatsächlichen TNC-Text erweitern.
  Exakten Text aus Monitor-Log entnehmen und in CC melden.
- `[AMTOR] CONNECTED → TxController started` fehlt →
  `on_link_message`-Route in `_wire_mode_callbacks` prüfen

**Status:** ⬜ OPEN (Hardware-Test ausstehend, zweite AMTOR-Station
benötigt)

---

### T74 — AMTOR ARQ TX: ACK-Färbung + 1 [TX] pro Zeichen
*Voraussetzung: T73 bestanden (CONNECTED erkannt, TxController gestartet)*

1. AMTOR, ARQ-Verbindung steht (● CONNECTED) → Zeichen tippen

**Expected result:**
- Jedes Zeichen erscheint nach DATA_ACK grün/ACK-gefärbt im TX-Fenster
- Im Monitor: genau EIN `[TX]`-Eintrag pro Zeichen
- Sendefluss flüssig (3-Zeichen-ARQ-Blöcke, TNC steuert 100-Bd-Timing)

**Diagnose bei Fehler:**
- Zeichen werden nicht gesendet → TxController nicht gestartet (T73-Diagnose)
- Doppelsenden → `char_ready`-Guard in `_wire_mode_callbacks` prüfen

**Status:** ⬜ OPEN (Hardware-Test ausstehend, zweite AMTOR-Station
benötigt)

---

### T75 — AMTOR ARQ CTRL+D EOT: PTOVER-Rollentausch
*Voraussetzung: T74 bestanden*

1. ARQ-Verbindung steht → Text "599 DE OE3GAS" tippen → **CTRL+D**
2. Warten bis alle Zeichen gesendet

**Expected result:**
- Nach DATA_ACK des letzten Zeichens erscheint im Monitor:
  `[AMTOR] EOT — PTOVER (\x1A) sent, ARQ turnaround`
- ARQ-Verbindung bleibt aktiv (kein DISCONNECT)
- ISS↔IRS-Rollentausch: Gegenstation wird zur sendenden Station
- NICHT: sofortiger Link-Abbruch oder RC-Befehl

**Diagnose bei Fehler:**
- Link bricht ab → fälschlicherweise OV-Befehl statt \x1A gesendet
- Kein Rollentausch → PTOVER-Zeichen nicht als $1A vom TNC erkannt
  (Betriebsart prüfen: nur in AMTOR-ARQ, nicht in FEC)

**Status:** ⬜ OPEN (Hardware-Test ausstehend, zweite AMTOR-Station
benötigt)

---

### T76 — AMTOR ARQ CTRL+D in Macro
*Voraussetzung: T75 bestanden*

1. Macro mit eingebettetem [^D] anlegen (z.B. "599 [^D]")
2. ARQ-Verbindung steht → Macro abspielen

**Expected result:**
- Macro vollständig gesendet, dann PTOVER-Rollentausch
- Kein vorzeitiges Umschalten — erst nach letztem ACK

**Status:** ⬜ OPEN (Hardware-Test ausstehend, zweite AMTOR-Station
benötigt)

---

### T77 — AMTOR FEC TX: Zeichen fließen, kein PTOVER
*FEC braucht keine zweite Station — Rundspruch ohne ARQ-Verbindung.*

1. ComboBox → AMTOR → **btn_fec** drücken (FEC-Modus aktivieren)
2. Text senden
3. CTRL+D drücken

**Expected result:**
- Zeichen werden gesendet und ACK-gefärbt
- Bei [^D]: `on_send_stop()` wird aufgerufen (kein PTOVER \x1A)
- Monitor zeigt: `[AMTOR] EOT — FEC TX done, controller stopped`
- KEIN Link-Abbruch (es gab keine ARQ-Verbindung)

**Diagnose bei Fehler:**
- PTOVER wird in FEC gesendet → btn_fec.isChecked()-Abfrage in
  `_on_baudot_eot()` prüfen

**Status:** ⬜ OPEN (Hardware-Test ausstehend)

---

### T78 — AMTOR DISCONNECT: TxController gestoppt
*Voraussetzung: ARQ-Verbindung aktiv*

1. ARQ-Verbindung steht, Text im TX-Fenster → Verbindung trennen
   (btn_stby oder Gegenstation bricht ab)

**Expected result:**
- Monitor zeigt: `[AMTOR] DISCONNECTED → TxController stopped`
- Status-Pill → **● STBY**
- Kein weiterer TX-Versuch nach Disconnect

**Status:** ⬜ OPEN (Hardware-Test ausstehend, zweite AMTOR-Station
benötigt für Gegenstation-Abbruch; STBY-Button allein testbar)

---

### T79 — AMTOR TxController: kein Doppelsenden nach Mode-Switch
1. Baudot RTTY → AMTOR → zurück zu Baudot → wieder AMTOR
   (mehrfacher Mode-Switch)
2. Nach jedem Wechsel: Text senden

**Expected result:**
- Pro Zeichen immer genau EIN [TX] im Monitor
- Keine gestapelten Signal-Verbindungen durch wiederholtes _wire_mode_callbacks

**Status:** ⬜ OPEN (Hardware-Test ausstehend)

---

## Test Block 3 — Macros

### T19–T22 — Macro buttons, edit dialog, CTRL+D in macro, paste
**Status:** ⬜ OPEN (partial — basic macro send confirmed manually)

---

## Test Block 4 — CTRL+T timed marker (v13)

### T23 — CTRL+T:n insert
### T24 — CTRL+T:n timing
### T25 — CTRL+T:n Backspace
### T26 — CTRL+T:n in macro
**Status:** ✅ OK (v13)

---

## Test Block 5 — Help System

### T27 — Help button in MacroEditDialog
### T28 — Help Viewer content
**Status:** ⬜ OPEN

---

## Test Block 6 — HF/VHF Packet

### T29 — HF Packet screen visible
1. Host Mode active → ComboBox → **HF Packet**

**Expected result:**
- HF Packet screen with Connect/Disconnect/Unproto/MailDrop/APRS(hidden) buttons
- HBAUD default 300, Monitor default 4

**Status:** ✅ OK (v11)

---

### T30 — VHF Packet screen visible
1. Host Mode active → ComboBox → **VHF Packet**

**Expected result:**
- VHF Packet screen with APRS button visible (hidden in HF Packet)
- HBAUD default 1200

**Status:** ✅ OK (v11/v15)

---

### T31 — VHF Packet init frames
1. Host Mode active → ComboBox → **VHF Packet** → check serial monitor

**Expected result:**
- `PA`, `VH Y`, `HB 1200`, `MX 4`, `SL 10`, `MN Y` frames sent and ACKed

**Status:** ✅ OK (v15 — confirmed 2026-05-17)

---

### T32 — HF Packet init frames
1. ComboBox → **HF Packet** → check serial monitor

**Expected result:**
- `PA`, `VH N`, `HB 300`, `MN Y`

**Status:** ✅ PASS (2026-06-22, frame-verified) — `HFPacketMode.get_init_frames()`
now emits `VH N`, `HB 300`, `MN Y` after the `PA` activate frame. VHF no longer
inherits `VH N` (would have undone its own `VH Y`). Hardware re-test pending.

---

### T33 — Connect: empty Dest warning
**UI note (P42, 2026-09-24):** the Connect button and Dest field this test
was written against no longer exist — a callsign is now typed directly
into a free channel chip's own inline editor, which cannot be submitted
empty at all (`ChannelChip._commit()` only ever emits `connect_requested`
for a non-empty, valid callsign; an empty field pressing Enter is a no-op,
no warning dialog). Original steps/result kept below as history; the
software-verified equivalent is `TestChipConnectFlow` in
`test_packet_screen.py` (an invalid/empty callsign keeps the editor open
with no signal, rather than popping a warning dialog).

1. ~~VHF Packet, Dest empty → click **Connect**~~

**Expected result (historical):** Warning dialog "Packet Connect"

**Status:** ✅ PASS (2026-06-19, mock) — superseded by P42's UI redesign,
see the note above.
**Note:** Warning dialog fires correctly when Dest empty.

---

### T34 — Connect: CO frame sent
**UI note (P42, 2026-09-24):** rewritten for the connect-in-chip UI — type
the callsign into channel 1's own chip editor (click the current free chip
again, or double-click it, to open it), then press Enter.

1. VHF Packet, channel 1 selected — click chip 1 again (or double-click
   it) to open its editor, type "OE3XYZ-9", press Enter

**Expected result:**
- Chip 1 immediately shows "OE3XYZ-9" (amber "calling" fill)
- Serial: `01 40 01 43 4F ...` (CH_CMD ch=1, CO, callsign bytes)
- Status: **● CALLING**

**Status:** ✅ PASS (2026-06-19, mock; UI updated 2026-09-24 for P42 — see
`TestChipConnectFlow::test_enter_with_valid_callsign_emits_connect_requested_on_that_channel`
in `test_packet_screen.py` and `MainWindow._on_chip_connect_requested()`).
**Note:** CTL=$41 channel frame confirmed (bugfix 47f5845 — was $4F).
TX: `01 41 43 4F 4F 45 31 58 59 5A 17`

---

### T35 — CONNECTED status pill
1. TNC confirms AX.25 connection (second station)

**Expected result:**
- $50 LINK_MSG frame received
- Status pill → **● CONNECTED** (green)

**Status:** ✅ PASS (2026-06-19, mock)
**Note:** $51 LINK_MSG "CONNECTED to OE1XYZ" → ● CONNECTED (green).
Hardware test against real second station still outstanding. Unaffected
by the P42 UI redesign — this is the RX/status-label side, not Connect
itself.

---

### T36 — DATA frame TX
1. VHF Packet, connected → type text, press Enter

**Expected result:**
- Serial: DATA frame on channel 1 with text content
- Echo appears in RX display (TX yellow)

**Status:** ✅ PASS (2026-06-19, mock)
**Note:** L / R 2 / R 4 / D sent and echoed correctly (TX yellow).
BBS responses appear in RX display. Unaffected by the P42 UI redesign —
this exercises `tx_input`, not Connect.

---

### T37 — Disconnect: DI frame + status pill
**UI note (P42, 2026-09-24):** the Disconnect button this test was written
against no longer exists — disconnect now comes from the busy chip's own
context-menu "Disconnect" entry, or Ctrl+D while that channel is current.

1. VHF Packet, connected on channel 1 — right-click chip 1 → "Disconnect"
   (or select chip 1 and press Ctrl+D)

**Expected result:**
- Serial: `01 40 01 44 49 17` (CH_CMD ch=1, DI)
- Status pill → **● STBY**

**Status:** ✅ PASS (2026-06-19, mock; UI updated 2026-09-24 for P42 — see
`TestChipConnectFlow::test_ctrl_d_disconnects_the_busy_current_channel` in
`test_packet_screen.py` and `MainWindow._on_chip_disconnect_requested()`).
**Note:** Both directions verified:
(a) Disconnect (button, historically) → $41 DI → ● DISCONNECTED
(b) Remote disconnect via BBS "D" command → ● DISCONNECTED
Hardware test against real second station still outstanding.

---

### T83 — Mock-TNC BBS: Connect-button gating
**UI note (P42, 2026-09-24):** rewritten for the connect-in-chip UI — there
is no Connect/Disconnect button pair to gate any more; gating now means
"does the chip's editor open at all".
Prerequisite: `python tools/mock_tnc_bbs.py --trace`

1. Initial: chip 1 free → opens its editor (click again, or double-click)
2. Type "OE1XYZ" + Enter → CALLING (editor closes, chip shows the callsign)
3. After CONNECTED: clicking chip 1 again just re-selects it, no editor
   opens (busy chip) — right-click offers "Disconnect", not "Connect…"
4. Right-click chip 1 → "Disconnect" (or Ctrl+D) → DISCONNECTED
5. Chip 1 is free again — clicking it again opens its editor
6. Re-connect possible

**Expected result:** Editor-open/context-menu gating correct in every state
(the direct equivalent of the old button gating).

**Status:** ✅ PASS (2026-06-19, mock — commits packet_screen.py +
main_window.py; UI updated 2026-09-24 for P42, see `TestChipConnectFlow`
in `test_packet_screen.py`)

---

### T84 — Mock-TNC BBS: full BBS session
Prerequisite: `python tools/mock_tnc_bbs.py --trace`

1. Connect → OE1XYZ → CONNECTED + banner in the RX window
2. "L" + Enter → List of Messages (#1–#4)
3. "R 2" + Enter → "#2: The Quick Brown Fox"
4. "R 4" + Enter → "#4: Don't mess with Texas"
5. Unknown command → menu repeated
6. "D" + Enter → "Goodbye! OE1XYZ BBS" + DISCONNECTED

**Expected result:** all steps correct, status pill follows the link state.

**Status:** ✅ PASS (2026-06-19, mock)

---

### T38 — Unproto with digipeater path
1. UNPROTO via = "CQ VIA OE3XNR-8" → click **Unproto**

**Expected result:** Serial: `UN CQ VIA OE3XNR-8`

**Status:** ✅ PASS (2026-06-22, frame-verified) — `btn_unproto` → `_on_packet_unproto()`
sends `build_command(b'UN', le_unproto.text())`. Trace: `ctl=0x4F data=b'UNCQ VIA OE3XNR-8'`.

---

### T39 — Connect and Unproto mutual exclusion
**UI note (P42, 2026-09-24):** there is no `btn_connect`/`btn_disconnect`
to grey any more — a busy channel's chip simply refuses to open its own
inline editor (see T99), which is the connect-in-chip equivalent of
"Connect greyed". The Unproto side of the exclusion is unchanged.

1. Unproto ON (UI chip selected) → the UI chip's own context menu is empty
   (P10, no connect possible there) either way
2. Connect/CALLING/CONNECTED on a QSO channel → Unproto button greyed
3. Unproto OFF (link idle) → link down → Unproto re-enabled

**Status:** ✅ PASS (2026-06-22, code-verified; UI updated 2026-09-24 for
P42) — `set_link_state()` greys/restores `btn_unproto` on
connected/calling/idle (now its ONLY job, see `set_link_state()`'s own
docstring); `ChannelChip.start_edit()`/`_show_menu()` refuse to open on a
busy channel or channel 0, which is what replaces the old
`_on_packet_unproto()` button-greying half of this test. Mutual exclusion
both directions. Interactive mock re-click pending.

---

### T40 — RX display: monitored frames (VHF/APRS)
1. VHF Packet, Monitor = 4/6, TNC tuned to 144.800 MHz
2. APRS button OFF (raw mode)

**Expected result:**
- Monitored frames in RX window with UTC timestamp `[HH:MM:SS]`
- Format: `[HH:MM:SS] SOURCE>PATH>APRS_ID <UI>:\n  PAYLOAD`
- Grey text on dark background

**Status:** ✅ OK (v15 — confirmed 2026-05-17, OE3XWJ-10 area)

---

### T41 — MHEARD Refresh
Prerequisite: `python tools/mock_tnc_bbs.py --trace`
1. Packet screen (Host Mode) → click **Refresh** in the MHEARD panel

**Expected result:**
- `--trace` shows MH0..MH17 going out; mock replies MH0..MH2 + end-marker
- MHEARD panel fills with `OE3GAS *` (direct, green), `OE1XYZ`, `DB0MUC`

**Status:** ✅ PASS (2026-06-22, mock end-to-end) — `_on_packet_mheard()` polls
MH0..MH17 (line-by-line, TRM §4.11, fire-and-forget); CMD_RESP `MH` lines →
`HFPacketMode.on_mheard_entry` → `_parse_mheard_line()` → `MheardPanel.add_entry()`.
End-marker (`MH` + `$00`) and plain ACKs ignored. Decoded chain verified headless
(MH0..MH4 → 3 stations). Live-GUI click + hardware re-test pending.

### T42 — MHEARD Clear
1. With entries present → click **Clear** in the MHEARD panel

**Expected result:** panel emptied (local `MheardPanel.clear()`)

**Status:** ✅ PASS (2026-06-22) — `btn_clear` wired to `MheardPanel.clear()`;
Refresh also clears before re-polling so the list never doubles.

### T43 — Toggle EAS
**Status:** ✅ PASS (2026-06-22, frame-verified) — `btn_eas` → `EA Y` / `EA N`
(toggle_map, mnemonic `EA`). Guarded by is_connected + is_host_mode.

### T44 — Toggle PASSALL
**Status:** ✅ PASS (2026-06-22, frame-verified) — **mnemonic fixed `PA` → `PS`**.
`PA` is the PACKET-mode activation command, so the old `PA Y` would have
re-entered Packet mode instead of toggling PASSALL. `btn_passall` → `PS Y` / `PS N`.
**Correction (21.09.2026, P16, T86 hardware-verified):** `PS` was itself
wrong — PASSALL is `PX`; `PS` is PASS, a masking character. `btn_passall`
now sends `PX Y` / `PX N`. History kept for the record; see T86 and
Backlog.md.

### T45 — HBAUD change
**Status:** ✅ PASS (2026-06-22, frame-verified) — `combo_hbaud` change →
`_on_packet_hbaud_changed()` → `HB <value>` (mnemonic `HB`).

### T46 — Monitor level change
**Status:** ✅ PASS (2026-06-22, frame-verified) — `combo_monitor` (0–6) change →
`_on_packet_monitor_changed()` → `MN <level>` (mnemonic `MN`).

### T47 — MailDrop button
**Status:** ✅ PASS (2026-06-22, frame-verified) — `btn_maildrop` →
`_on_packet_maildrop()` → `MI` (mnemonic `MI`).

**Correction (P21, hardware-confirmed 22.09.2026, T115):** this PASS only
ever meant "the TNC accepted the frame" — it never verified what `MI`
does. Host Mode `MI` reads back the same value as verbose `MFILTER`
(`MI$80` / `MFIlter $80`): `MI` is MFILTER, not MailDrop login, so the
button never logged in to the mailbox at all. Fixed in P21.5:
`btn_maildrop` is disabled ("MailDrop dialog not implemented yet") and
`_on_packet_maildrop()` is a no-op until a real MailDrop dialog exists.

### T48 — VHF vs HF Packet init frames
**Status:** ✅ PASS (2026-06-22, frame-verified) — HF emits `VH N`, VHF emits
`VH Y`; VHF init no longer inherits the HF `VH N`. See T31/T32.

### T49 — Keyboard focus after button click
**Status:** ✅ PASS (2026-06-22, code-verified) — all packet buttons use
`make_toggle_button()` / `_no_focus_btn()`, both set `Qt.FocusPolicy.NoFocus`,
so toggle clicks never steal focus from `tx_input`.

### T50 — Dest and UNPROTO fields accept input
**Status:** ✅ PASS (2026-06-22, code-verified) — `le_dest` / `le_unproto` are
editable QLineEdit (default `CQ`), both registered with `ScreenFocusController`.

### T51 — Mode switch away from Packet: VHF OFF
**Status:** ✅ PASS (2026-06-22, frame-verified) — `_on_mode_selected()` sends
`VH N` (`VHFPacketMode.vhf_off_frame()`) when the outgoing mode is VHF Packet,
restoring the 300 Bd HF modem for the next mode.

---

## Test Block 6b — Packet Channel Model (ChannelBar sprint)

Numbered T87–T92, not T83–T88 as in the original sprint sketch —
T83–T86 were already taken (Mock-TNC BBS gating/session, Stop Sending via
RECEIVE, PASSALL mnemonic). Software/mock-checked headlessly against a stub
`_serial` (channel 4, not 1) in this sprint — see the "Packet screen: channel
bar…" / "MainWindow: packet channel routing…" commits; interactive
mock-GUI (`tools/mock_tnc_bbs.py`) and hardware re-tests still open.

### T87 — Channel selection via chip click
**UI note (P42, 2026-09-24):** step 2 rewritten — the Dest field/Connect
button it named no longer exist; the callsign now goes directly into
chip 4's own editor.

1. Packet screen (Host Mode) — click channel chip 4 in the ChannelBar
2. Click chip 4 again (now current and free) to open its editor, type a
   callsign, press Enter

**Expected result:** CO goes out with CTL=$44 (channel 4), not $41; chip 4
shows the amber "calling" fill immediately.

**Status:** ✅ PASS (2026-09-20, headless — stub `_serial`, see
`_on_packet_connect`/`ChannelBar.set_channel_state`; UI updated 2026-09-24
for P42, see `_on_chip_connect_requested`). Interactive mock-GUI re-click
and hardware re-test pending.

### T88 — Channel stepping via Ctrl+Up / Ctrl+Down
1. Packet screen, focus in `tx_input` — press **Ctrl+Down** three times

**Expected result:** current channel advances 1→2→3→4, wrapping
9→0. Plain Up/Down (no Ctrl) are NOT intercepted — they still move the
text cursor inside `tx_input` (chosen specifically to avoid regressing TX
message composition; the original "Pfeiltaste hoch/runter" sketch did not
specify a modifier).

**Status:** ✅ PASS (2026-09-20, headless — `ChannelBar.step()` unit-checked
via the eventFilter Ctrl+Up/Down branch). Live-GUI keyboard re-test pending.

### T89 — Chip shows callsign after CONNECTED, number after DISCONNECTED
1. Connect on channel 4 — chip shows "4" only (grey/amber)
2. TNC replies `LINK_MSG` "CONNECTED to OE1XYZ-5" on channel 4
3. Disconnect — TNC replies "DISCONNECTED" (or local DI path)

**Expected result:** chip 4 shows "OE1XYZ-5" (green) after step 2, reverts to
just "4" (grey) after step 3; `ChannelBar.channel_map()` contains
`{"OE1XYZ-5": 4}` after step 2 and is empty after step 3.

**Status:** ✅ PASS (2026-09-20, headless — `HFPacketMode.on_channel_state`
end-to-end through a synthetic `LINK_MSG` frame into `ChannelBar`, AND
re-confirmed against the real `tools/mock_tnc_bbs.py` `LoopbackTNC` after
the `_make_host_frame()` channel-nibble bugfix below — see T93).

### T90 — ALL/CH view filters RX correctly
1. `btn_view_ch` active, current channel = 4 — data arrives on channel 4 and
   channel 5
2. Switch `btn_view_all` on

**Expected result:** step 1 shows only the channel-4 line; the channel-5 line
never appears retroactively when switching to ALL in step 2 (filtering
happens at append time, not by rebuilding the RX buffer — v0.1 decision,
see `PacketBaseScreen.append_channel_data()`).

**Status:** ✅ PASS (2026-09-20, headless —
`append_channel_data()`/`set_view_all()` unit-checked).

### T91 — MHEARD shows the channel number for connected stations
1. Channel 4 connects to OE1XYZ-5 — MHEARD Refresh already lists OE1XYZ-5
   from an earlier heard frame

**Expected result:** the OE1XYZ-5 row shows "4 OE1XYZ-5" in amber; every other
row shows two leading spaces before the callsign.

**Status:** ✅ PASS (2026-09-20, headless —
`MheardPanel.set_channel_map()` + `_render()` unit-checked).

### T92 — Capture records every channel regardless of the ALL/CH view
1. `btn_view_ch` active on channel 1 — start **Capture**
2. Data arrives on channel 3 and as a monitored frame

**Expected result:** the capture file contains both lines (with UTC
timestamps) even though channel 3 is not the currently viewed channel.

**Status:** ✅ PASS (2026-09-20, headless — `QFileDialog.getSaveFileName`
stubbed, `_on_packet_data_received`/`_on_packet_monitor_frame` write via
`_packet_capture_write()` regardless of the screen's view filter).

### T93 — CONNECTED on channel 3 against tools/mock_tnc_bbs.py
Numbered T93, not T90 as first sketched — T90 above was already taken by
"ALL/CH view filters RX correctly" (added earlier in this same sprint).

Prerequisite: `python tools/mock_tnc_bbs.py --trace`

**UI note (P42, 2026-09-24):** step 1 rewritten — Dest/Connect no longer
exist; the callsign now goes into chip 3's own editor.

1. Packet screen (Host Mode via the mock) — select channel 3 in the
   ChannelBar, click it again to open its editor, type OE1XYZ, press Enter
2. Observe the `CO` frame's CTL byte and the mock's `CONNECTED to OE1XYZ`
   reply

**Expected result:** `CO` goes out with CTL=$43 (channel 3); the mock's
`CONNECTED to OE1XYZ` reply carries CTL=$53 and chip 3 turns green and shows
"OE1XYZ" — this specifically exercises the real `SerialManager` frame
decode path (`_make_host_frame()`), not a synthetic/direct-call frame like
T89. Before the channel-nibble bugfix ("Fix channel nibble extraction for
4x and 5x frames"), `_make_host_frame()` reported channel 15 for every $5x
LINK_MSG frame, so the chip never updated — this test is the regression
guard for that fix at the application level (the unit-level guard is
`TestMakeHostFrame` in `test_hostmode.py`).

**Status:** ✅ PASS (2026-09-20, headless — full app against the real
`LoopbackTNC`: `connect_port("MOCK")` → `init_tnc()` → mode switch to VHF
Packet → Connect on channel 4 → `CO` with CTL=$44 confirmed in the trace
→ mock replies `CONNECTED to OE1XYZ` with CTL=$54 → chip 4 shows
"connected OE1XYZ"; TX data (`L`) sent and BBS reply routed into the RX
display via `append_channel_data()`; Disconnect sends `DI` on channel 4 and
frees the chip). Interactive mock-GUI click and hardware re-test pending.

---

## Test Block 6c — Packet TX Buffer per Channel (P9)

From `docs/P9_TX_Buffer_Spec.md`. Continues the existing numbering —
T87–T93 above are unchanged.

### T94 — TX buffer per channel
1. Select channel 1, type `test eins`, do **not** send
2. Select channel 3 → TX window is empty
3. Type `test drei`, do **not** send
4. Back to channel 1 → `test eins` is there again, cursor at the end
5. Back to channel 3 → `test drei` is there
6. Send on channel 3 → only channel 3 is empty, channel 1 still holds
   `test eins`

**Expected result:** no text loss, no text on the wrong channel.

**Status:** ✅ PASS (2026-09-20, headless — full app against the real
`tools/mock_tnc_bbs.py` `LoopbackTNC`, plus `TestPerChannelTxBuffer` in
`test_packet_screen.py`). Interactive manual click-through and hardware
re-test still open (see Definition of Done below).

### T95 — MHEARD double-click switches channel without losing text
1. Type text on channel 1, do not send
2. Double-click a station connected on channel 4 in the MHEARD list
3. **Expected result:** switches to channel 4, TX window shows channel 4's
   text (or empty), channel 1 keeps its text

**Status:** ✅ PASS (2026-09-20, headless — `TestMheardChannelSwitchKeepsText`
in `test_packet_screen.py`: `MheardPanel.channel_requested` and a chip click
both go through the same `ChannelBar.channel_changed` signal, so the P9
buffer swap in `PacketBaseScreen._on_tx_channel_switch()` applies identically
either way).

### T96 — reset_channels() on mode switch
1. Connect on channel 2, type text on channel 5
2. Switch operating mode to Baudot, then back to HF Packet
3. **Expected result:** every chip is `free`, no partner callsigns, TX
   buffer empty

**Status:** ✅ PASS (2026-09-20, headless — full app: `connect_port` →
`init_tnc` → VHF Packet → connect ch2 + draft on ch5 → mode switch to
Baudot RTTY → back to VHF Packet → every chip `free`, `_tx_buffers == {}`,
`tx_input` empty; also `TestResetChannelsClearsAllBuffers` in
`test_packet_screen.py`).

### T97 — "CONNECTED to:" with a colon
Check against `tools/mock_tnc_bbs.py` with both message forms; the chip
shows the callsign in both cases, never `":"`.

**Status:** ✅ PASS (2026-09-20 — unit-level: `TestExtractPartner` +
`TestOnChannelState` in `test_packet_hf.py` cover both the TRM form
"CONNECTED to OE1XYZ-5" and the colon form "CONNECTED to: OE1XYZ-5", with
and without a trailing " via " path; extended in this pass to also feed
both forms through `HFPacketMode._handle_link_msg()` end to end (see the
smoke check in the "Packet screen: per-channel TX buffers" commit).
`tools/mock_tnc_bbs.py` itself only ever sends the no-colon TRM form, so
the colon form is not independently exercised against the mock — it is a
firmware variant per the STABO manual, reproduced synthetically here.

---

## Test Block 6d — Channel 0 is the UI Channel (P10)

From `docs/P10_UI_Channel_Spec.md`. Continues the existing numbering —
T87–T97 above are unchanged.

### T98 — Unproto switches to the UI channel
**UI note (P42, 2026-09-24):** step 3's "Connect and Disconnect are
locked" no longer applies literally (those buttons are gone) — its
connect-in-chip equivalent is T99 (the UI chip's editor never opens at
all). Steps 1/2/4 and the channel-switch/TX-draft behaviour are unchanged.

1. Select channel 3, type text, do not send
2. Turn Unproto on
3. **Expected result:** the `UI` chip is active, the TX window shows the
   Unproto draft (empty at first)
4. Select chip 3 → Unproto turns off, the text from step 1 is back

**Status:** ✅ PASS (2026-09-20, headless — full app against the real
`tools/mock_tnc_bbs.py` `LoopbackTNC`, plus `TestUnprotoUsesChannelZero` in
`test_main_window_packet.py`; rewritten 2026-09-24 for P42 — the
Connect/Disconnect-button assertions moved to `TestConnectRejectedOnChannelZero`,
see T99). Interactive manual click-through and hardware re-test still
open, as with the rest of this sprint's Packet tests.

### T99 — Connect on channel 0 is rejected
**UI note (P42, 2026-09-24):** rewritten — there is no Dest field, Connect
button, or warning dialog any more. The guard moved to the source:
`ChannelChip.start_edit()` refuses to open its editor at all for the UI
channel, so `connect_requested` can never even be emitted for it.

1. Select the `UI` chip, try to open its inline editor (click it again,
   double-click it, or try the context menu)
2. **Expected result:** no editor opens (no context menu at all, per P10),
   no `connect_requested` signal fires, no `CO` frame goes out

**Status:** ✅ PASS (2026-09-20, headless — full app against the real
`LoopbackTNC` [`_serial.calls`/trace shows no `CO`], plus
`TestConnectRejectedOnChannelZero` in `test_main_window_packet.py`;
rewritten 2026-09-24 for P42, see also
`TestChipConnectFlow::test_ui_channel_does_not_open_editor` in
`test_packet_screen.py`).

### T100 — Monitor traffic in the CH view
1. View set to `CH`, chip 3 active → monitored frames do **not** appear
2. Select the `UI` chip → monitored frames appear
3. View set to `ALL` → monitor traffic appears regardless of the chip

**Status:** ✅ PASS (2026-09-20, headless — `TestUiChannelZero` in
`test_packet_screen.py`: `append_monitor_data()` now shares
`append_channel_data()`'s ALL/CH filter, gated on `UI_CHANNEL`).

**Rewritten P50 (2026-09-25) — filtering became a document switch, not
an append-time decision:** the mechanism changed (one `QTextDocument`
per channel plus a merged ALL document, `_sync_rx_document()` re-attaches
`rx_display` to the right one instead of `append_channel_data()`/
`append_monitor_data()` deciding whether to write a line at all), but
the three steps above and their expected result are unchanged — "does
not appear" now means "not in the currently-attached document", not
"was never written anywhere". Also now true, which the old append-time
filter could not offer: switching to chip 3 in CH view shows chip 3's
**complete** history, not just monitor/data that arrives from the
switch onward — see T132 below.

**Status (P50):** ✅ PASS (2026-09-25, headless — `TestUiChannelZero`
still passes unchanged against the new document-switch mechanism;
`TestPerChannelRxDocuments` in `test_packet_screen.py` covers the new
full-history behaviour).

### T101 — Hardware check: UI frame on an unconnected channel
To confirm: does v7.1 actually transmit text that comes in over `$20` on
the unconnected channel 0 as a UI frame along the configured UNPROTO path?
This is standard AX.25 behaviour, but is not documented for v7.1's Host
Mode.

**Tool (P14, 21.09.2026):** `python tools/hw_check.py --port COM3 t101` —
runs the two-round UNPROTO-path check (TEST1/TEST2) described above,
transmitting under an explicit y/N confirmation each time. Needs a second
receiver with an AX.25 decoder; see `docs/HW_Solo_Tests.md`. Excluded from
`hw_check.py all` since it is the only one of the four checks that
transmits.

**Status:** ✅ PASS (21.09.2026, second run — `PK232PY T101 A ...` decoded
with destination `TEST1`, `PK232PY T101 B ...` with destination `TEST2`,
unambiguous). The first run's round A came back negative (destination not
seen); the operator assessed this as a receiver effect (decoder/SDR not
yet settled), not a TNC behaviour — all four transmissions in both runs
produced an identical TNC response (`ctl=0x5F ch=15 data=b'XX\x00'`, see
the CLAUDE.md note on this response). The same run also confirmed the PK-232
does **not** echo its own transmissions as a `$3F` monitor frame in Host
Mode, even at `MONITOR 6` — 0 monitor frames seen in every round.

### T102 — Link message for a channel that is not visible does not touch the buttons
Bugfix (2026-09-20): `_make_link_handler()` used to call `set_link_state()`
for every link message regardless of channel, so a CONNECTED on one channel
could enable Disconnect while a different chip was on screen — pressing
that Disconnect would then send `DI` on the wrong channel.

**UI note (P42, 2026-09-24):** there is no Disconnect button left to
enable/disable — `set_link_state()` now only ever gates Unproto (see its
docstring), so this test's observable now checks Unproto instead. Chip 4
disconnecting is unaffected — the chip's own context-menu "Disconnect"/
Ctrl+D are already channel-scoped by construction (T37), which is exactly
what this bug was never about in the first place.

1. Connect on channel 4
2. Switch to the `UI` chip → Unproto unlocked (channel 0 is never busy)
3. Trigger a link message for channel 4 (mock)

**Expected result:** Unproto stays unlocked, chip 4 stays green (ChannelBar
itself is a separate, always-on consumer of the same message and is
unaffected). Switching back to chip 4 shows Unproto locked again (that
channel's own real state).

**Status:** ✅ PASS (2026-09-20, headless — full app against the real
`tools/mock_tnc_bbs.py` `LoopbackTNC`, plus
`TestLinkMessageGatedByVisibleChannel` in `test_main_window_packet.py`;
rewritten 2026-09-24 for P42, test renamed to
`test_message_for_other_channel_does_not_change_unproto`).

---

## Test Block 6e — USERS (P11)

From `docs/P11_USERS_Spec.md`. Continues the existing numbering — T87–T102
above are unchanged.

### T103 — USERS is uploaded
1. Open the HF Packet Parameters dialog, set `USERS` to 4, click OK
2. Trigger a parameter upload
3. **Expected result:** `USERS 4` appears in the monitor, the TNC
   acknowledges without error
4. The value survives an application restart (INI)

**Status:** ✅ PASS (2026-09-20 — unit-level: `TestUsersRoundTrip` in
`test_params_hf_dialog.py` covers steps 1/4 [dialog ↔ `HFPacketConfig`,
`_apply_hf_packet()`/`_build_hf_packet()` round-trip through the INI],
`TestUsersUploaded` in `test_params_uploader.py` covers steps 2/3
[`USERS 4\r\n` present in `_build_commands()`'s output]. Live-GUI
click-through against a real TNC monitor still open.

**Hardware confirmation (P14, 21.09.2026):** `python tools/hw_check.py
--port COM3 t103` — queries `USERS`, runs the real
`ParamsUploader._build_commands()` against a copy of the saved
configuration with `USERS=4`, queries again, restores the real value, and
as a side effect scans every single upload response for a `?` error (the
first hardware exercise of every P13 command). See `docs/HW_Solo_Tests.md`.

**Hardware result:** ✅ PASS — `USERS` read back `4` after the upload,
restored to `1` afterwards and verified. All 68 upload commands were
acknowledged with no `?` error response, confirming `RESPTIME`, `ACRPACK`,
`CFROM`, `DFROM`, `MFROM`, `MTO`, `8BITCONV`, `HID` (the P13 sprint) on the
real TNC; the `AERPACK`→`ACRPACK` rename from P13 was confirmed correct
(`ACRPack was ON` / `ACRPack now ON`).

### T104 — USERS while a connection is up (hardware, OPEN)
1. Connect on channel 1
2. Change `USERS` in the dialog and upload
3. **Expected result open:** does the TNC accept the change, or reply with
   `$09` "not while connected"? Record the result in CLAUDE.md; if
   rejected, skip the `USERS` upload while connected instead of raising an
   error.

**Status:** ⬜ OPEN — needs real hardware.

### T105 — a second simultaneous connection (hardware, OPEN)
1. Set `USERS` to 2 or higher and upload
2. Connect on channel 1
3. Let a second station connect on channel 2
4. **Expected result:** both chips green with their own callsign, data
   routes into the correct channel view, TX buffers stay separate (P9)

**Status:** ⬜ OPEN — needs real hardware and a second AX.25 station. This
is the actual proof that the multi-channel model holds up beyond one QSO.

---

## Test Block 6f — Parameter Dialog Wiring Audit (P12)

### T106 — Parameter dialog wiring
Automatic, via `src/pk232py/tests/test_param_dialogs_roundtrip.py`
(`python -m pytest src/pk232py/tests/test_param_dialogs_roundtrip.py`). Not a
manual test case — status follows the test run.

Covers all six `&Parameters` dialogs (HF Packet, PACTOR, AMTOR/NAVTEX/TDM,
BAUDOT/ASCII/CW, Misc, MailDrop): every widget must reach a config field
(Test A), every config field must reach the dialog and back (Test B), every
field of all six configs must survive an INI save/load round trip (Test C).

**First-run findings (2026-09-20, all fixed in the same sprint):**
- `HFPacketParamsDialog._sb_txsmt` — built but unwired in both directions
  (Test A/B) — fixed in "HF params dialog: wire TXSMT in populate/apply_to".
- `HFPacketConfig.txsmt` / `.aerpack` / `.alfpack` — wired to the dialog but
  missing from `ConfigManager._apply_hf_packet()`/`_build_hf_packet()`, so
  lost on restart (Test C) — fixed in "Config: persist TXSMT/AERPACK/ALFPACK
  to INI".

**Documented, deliberate exceptions** (see `UNWIRED_OK`/`FIELD_HAS_NO_WIDGET`
in the test file for the full itemised list with reasons): ~60 widgets across
all six dialogs with no corresponding config field yet (filed in Backlog.md),
~11 read-only TNC-query spinboxes, and `BaudotConfig.mid` (handled live on
the Morse operating screen, not in the shared setup dialog).

**Status:** ✅ PASS (2026-09-20 — all three checks green across all six
dialogs after the TXSMT/AERPACK/ALFPACK fixes).

**P38 update (2026-09-24):** the five new local MailDrop archive fields
(`archive_enabled`/`archive_path`/`archive_sync`/`archive_restore`/
`archive_restore_scope`, `MailDropParamsDialog`'s new "Local archive
(PC side)" section) pass Tests A/B/C automatically — no new test code
needed beyond registering the three combo-box fields in
`_ENUM_FIELDS` (same mechanism as `cfrom_mode` etc.), since the audit
iterates `dataclasses.fields()` generically.

### T107 — Upload coverage
Automatic, via `test_param_dialogs_roundtrip.py::test_field_reaches_upload`
(Test D — see "P12 checks" note in T106; this is the fourth link in the
same chain: widget → config → INI → `ParamsUploader._build_commands()` →
TNC). Not a manual test case — status follows the test run.

**First-run findings (2026-09-20):**
- `HFPacketConfig.resptime` / `.txsmt` / `.aerpack` — wired all the way to
  the INI (T106/Test C passes) but never uploaded. `resptime` and `aerpack`
  (renamed `acrpack`) are now sent; `txsmt` is not (see CLAUDE.md — absent
  from the TRM command list).
- 21 further fields never reach the TNC either, independently of the HF
  findings above: PACTOR `arqtmo`/`adelay`/`ptdown`/`ptup`/`ptsum`/
  `pttries`/`ptsend`/`ptround`/`xmitok` (9), AMTOR `xlength`/`srxall`/
  `usos`/`wideshft` (4), Baudot `xlength`/`xbaud`/`usos`/`wideshft`/
  `xmitok` (5, plus `mid` which is sent live from the Morse screen instead
  and is not a gap), Misc `mark`/`space` (2). Exempted with a Backlog
  pointer rather than fixed blind — verifying 20 more command names against
  the TRM / `pk232_mnemonic_table.txt` is its own follow-up session (see
  Backlog.md "Upload coverage — PACTOR/AMTOR/Baudot/Misc").
- Also found and removed: `MYCALL` was sent twice per upload (Identity
  block + an unconditional duplicate in Message params).

**Status:** ✅ PASS (2026-09-20 — HF Packet's three named findings fixed;
everything else formally exempted with a cited reason, not silently
ignored).

**P38 update (2026-09-24):** the five new local MailDrop archive fields
are exempted by design, not a follow-up gap — they are PC-side settings
(`UPLOAD_EXEMPT`, reason "local archive setting, not a TNC parameter")
and must never appear in an upload command at all.

### T108 — Access filters on real hardware (hardware, OPEN)
1. Set `CFROM YES <a station you control>`, initialise
2. Connect from that station → accepted
3. Connect from a different station → rejected
4. Reset `CFROM ALL`

**Status:** ⬜ OPEN — needs real hardware and a second AX.25 station.

### T109 — Log message after a parameter dialog
1. Change a parameter in any `&Parameters` dialog, click OK
2. **Expected result:** the monitor log names the *next initialisation* as
   when the TNC will see the change, not "updated" (which implied
   immediately)

**Status:** ✅ PASS (2026-09-20 — code-verified: all six dialogs' OK
handlers in `main_window.py` now log "parameters saved — sent to TNC on
next initialisation"). Live-GUI click-through still open.

---

## Test Block 6g — Solo Hardware Checks (P14)

From `docs/P14_HW_Solo_Check_Spec.md` / `docs/HW_Solo_Tests.md`.

### T110 — PTHUFF: does the TNC's own format match what the uploader sends?
`PACTORConfig.pthuff` is an `int` (dialog range 0–10, a compression level)
but `ParamsUploader._build_commands()` sends it with `self._bool(...)`, i.e.
as `PTHUFF ON`/`PTHUFF OFF` (found during the P13 upload-coverage audit,
Backlog.md "Upload coverage" note).

1. `python tools/hw_check.py --port COM3 pthuff`
2. Tool queries `PTHUFF`, sends exactly what the uploader would send, queries
   again, restores the original value
3. Skipped with `INFO: no PACTOR option` if the TNC has no PACTOR hardware

**Expected result:** the TNC's own response format (numeric vs ON/OFF)
settles whether `PACTORConfig.pthuff` needs to become a bool or the
uploader needs to send a level instead.

**Status:** ❌ FAIL (type), 21.09.2026 — the TNC reports `PTHUFF` as
**numeric** (`PTHuff 0`), confirming the P13-documented type mismatch:
the uploader sends `PTHUFF ON`/`PTHUFF OFF`. The TNC accepts `PTHUFF OFF`
without a `?` error and leaves the value at `0` — it does not reject the
wrong type, it silently misinterprets it. `PTHUFF ON` untested. See the
Backlog.md item to change `PACTORConfig.pthuff` to a number with a real
value range from the manual.

### T111 — PASSALL button on the TNC, after the P16 fix (hardware, OPEN)
Follow-up to T86 (PASS, hardware-verified via `hw_check.py t17`): confirm
the actual button in the running app, not just the query tool.

1. HF/VHF Packet (Host Mode) → click **PASSALL** ON, then OFF
2. In a verbose-mode terminal, query `PASSALL` and `PASS`

**Expected result:** `PASSALL` toggles with the button; `PASS` stays at
its value (`$16` unless changed elsewhere) — the button must never move
`PASS`.

**Preferred method (P17, 2026-09-22):** `python tools/hw_check.py
--port COM6 t111` — sends the exact mnemonic `main_window.py`'s PASSALL
toggle uses (a unit test keeps the two in sync, see `test_hw_check.py`
`TestT111Mnemonic`), confirms `PX` changes and `PS` does not, then
restores `PX`. This exercises the real Host Mode command in isolation,
not the button — the GUI click-through below is still needed and stays
OPEN. See `docs/HW_Solo_Tests.md`.

**Status:** ✅ PASS (via `hw_check.py t111`, 2026-09-22) — `PX Y` toggled
PASSALL (`PXN` → `PXY`), `PS` stayed `$16` throughout, restore to `N`
confirmed. The P16 fix (`PX`, not `PS`) is proven at the Host Mode
command level. The GUI click-through (the button itself, in the running
app) is still OPEN — needs real hardware with the app running, not just
`hw_check.py`. (See Backlog.md renumbering note: this was T110 in
`docs/P16_PASSALL_Fix_Spec.md`, renumbered to avoid colliding with the
existing PTHUFF T110 above.)

### T112 — VHF → HF Packet parameter carry-over (hardware, OPEN)
Suspected gap, derived from the code and not yet measured (see
Backlog.md's VHF/HF correction note): `VHFPacketMode` sends `MX 4` + `SL 10`
on activation; leaving VHF for HF Packet only sends `VH N` + `HB 300` +
`MN Y` (`HFPacketMode.get_init_frames()`) — no `MAXFRAME`/`SLOTTIME` reset.

1. Activate VHF Packet (Host Mode)
2. Switch to HF Packet
3. In a verbose-mode terminal, query `MAXFRAME` and `SLOTTIME`

**Expected result:** both read back HF Packet's own configured values, not
VHF's `MAXFRAME 4` / `SLOTTIME 10`.

**Preferred method (P17, 2026-09-22):** `python tools/hw_check.py
--port COM6 t112` — queries `MAXFRAME`/`SLOTTIME`/`VHF`/`HBAUD`, replays
the real VHF→HF Packet frame sequence (built from `VHFPacketMode`/
`HFPacketMode` directly, same order as `_on_mode_selected()`), queries
`MAXFRAME`/`SLOTTIME` again, and restores all four. See
`docs/HW_Solo_Tests.md`.

**Status:** ❌ FAIL, confirmed gap (via `hw_check.py t112`, 2026-09-22) —
after the real VHF activate+init → VHF OFF → HF activate+init frame
sequence, `SLOTTIME` read back **10** (VHF's value), not HF's configured
`30`. **Only SLOTTIME is proof**: `MAXFRAME` already stood at `4` (VHF's
value) *before* this run even started, so its post-switch `4` proved
nothing about HF Packet's own init frames — the mnemonic `MX` was not
actually exercised. Side finding: `VH N` is sent twice (leaving VHF, then
HF's own init) — harmless, left as is. Fixed in P18.1
(`HFPacketMode.get_init_frames()` now also sends `MX`/`SL` from HF
Packet's own config) and `hw_check.py t112` reworked in P18.3 to pre-set
both parameters to a neutral value (neither HF's nor VHF's own) so each
is judged separately — retest with the fixed tool and code is the
Backlog.md follow-up.

### T113 — SIAM: unfiltered Host Mode frame capture (hardware, done)
`SignalMode.handle_frame()` (Backlog.md Priority 1 item) accepts both `$4F`
CMD_RESP and `$50` LINK_MSG as a SIAM result, contradicting its own module
docstring; the mockup screen's output format also does not match the
docstring's STABO-manual example. Neither can be fixed without first
seeing what the TNC actually sends.

1. Tune a second receiver to a **known** FSK signal (Amateur RTTY 45 Bd /
   170 Hz shift is the simplest case); note its mode, baud rate and shift
2. `python tools/hw_check.py --port COM6 siam` (or `--seconds N` for a
   longer/shorter capture) — enters Host Mode, sends `SignalMode`'s real
   activation frames, logs every incoming frame unfiltered for 60 s with a
   running frame count every 10 s, then exits Host Mode
3. Compare the printed frame-kind counts and any frame flagged as "looks
   like an analysis result" against the known signal from step 1

**Expected result:** the measurement settles which `FrameKind` a SIAM
result actually arrives as and what its text looks like, so
`SignalMode.handle_frame()` can be fixed to recognise it specifically
instead of accepting any CMD_RESP/LINK_MSG.

**Status:** ✅ Measurement complete (via `hw_check.py siam`, 2026-09-22,
reference signal RTTY 50 Bd / 450 Hz shift). Findings:
- Results arrive as **`$50` LINK_MSG on channel 0**, **never** as `$4F`
  CMD_RESP.
- **Every result is split across exactly two LINK_MSG frames**, e.g.
  `"0.73: 50 baud, "` + `"Baudot, RXRev ON\r\n"`, terminated by the
  second fragment's `\r\n`.
- Format: `"<confidence>: <baud> baud, <mode>, RXRev <ON|OFF>"` — matches
  the `signal_screen.py` mockup, **not** the module docstring's old
  STABO-manual example (`"BAUDOT 45 170"`).
- The TNC analyses **continuously**, producing a new result roughly every
  10s — it does not stop after the first one.
- Recognition was correct for the reference signal: 50 Bd Baudot, best
  confidence 0.73, at 450 Hz shift (without WIDESHFT).
- `SignalMode` fixed accordingly in P18.2 (`docs/P18_HF_Init_SIAM_Spec.md`):
  fragment assembly, CMD_RESP never treated as a result, module docstring
  corrected. See CLAUDE.md's SIAM gotcha under "TNC / firmware v7.1".

### T114 — SIAM screen shows one assembled result, not two halves (hardware, OPEN)
Follow-up to T113/P18.2: confirm the fix in the actual running app, not
just `SignalMode`'s/`SignalScreen`'s unit tests (`test_signal_analysis.py`,
`test_signal_screen.py`). The wiring itself is done (P19.4):
`MainWindow._wire_mode_callbacks()` connects `SignalMode.on_result_parsed`
to `SignalScreen.on_mode_result()`; software-verified by replaying the
real T113 frame sequence through both classes together (not just
`SignalMode` in isolation) — this hardware run is what is still missing.

1. Signal (SIAM), Host Mode → tune a known FSK signal (any FSK signal a
   second receiver can identify works; does not need to repeat exactly
   the RTTY 50 Bd / 450 Hz shift signal from T113)
2. Observe the Analysis Result box and the Analysis Log over at least
   three result cycles (~30s+, TNC analyses roughly every 10s)

**Expected result:**
- Each result appears in the Analysis Log **once per line**, fully
  assembled (e.g. `"14:23:11  0.73: 50 baud, Baudot, RXRev ON"`) — never
  as two separate half-lines, and never missing/duplicated.
- The Analysis Result box (Konfidenz/Baudrate/Mode/RXREV/TNC-Text) always
  reflects the **latest** result, updating roughly every 10s without
  manual interaction.
- The **"Best so far"** field shows the highest-confidence result seen
  since the last New Analysis/Cancel click — it must not regress to a
  later, lower-confidence result, and must reset to `–` after New
  Analysis or Cancel.
- No garbled/concatenated line ever appears (would indicate the fragment
  buffer was not reset between sessions, or a stray CMD_RESP/other frame
  interleaved with LINK_MSG fragments — see CLAUDE.md's SIAM gotcha).

**Status:** ⬜ OPEN — needs real hardware. Software/mock-verified: see
`test_signal_screen.py::TestSignalScreenLiveWiring` (T113 fixture replay,
latest/best/log-once-per-result) and
`TestMainWindowWiresSignalMode` (the `on_result_parsed` wiring itself).

### T115 — MI probe: is the MailDrop button actually querying MFILTER? (hardware, OPEN)
`pk232_mnemonic_table.txt`'s name-to-mnemonic mapping lists `MI` as
MFILTER, not MailDrop login — but that file is not hardware evidence (see
`docs/MNEMONIC_TABLE_NOTE.md` and CLAUDE.md's mnemonic-table correction).
T47 only confirmed that `_on_packet_maildrop()`'s `build_command(b'MI')`
frame is accepted by the TNC, never what `MI` actually means.

1. `python tools/hw_check.py --port COM6 mi` — Host Mode query `MI` (no
   argument), exit Host Mode, verbose query `MFILTER`
2. Compare the two values

**Expected result:** if `MI` and `MFILTER` read back the same value, `MI`
is confirmed as MFILTER and the MailDrop button
(`main_window._on_packet_maildrop()`) sends the wrong command; if they
differ, there is no evidence for the mnemonic-table claim.

**Status:** ❌ FAIL, confirmed (22.09.2026, second `hw_check.py mi` run) —
Host Mode `MI` read back `$80`, verbose `MFILTER` read back `$80` (`MI$80`
/ `MFIlter $80`). **`MI` is MFILTER, not MailDrop login** — the mnemonic-
table name-list entry is confirmed, and `main_window._on_packet_maildrop()`
sent the wrong command. Fixed in P21.5 (`btn_maildrop` disabled, handler
is a no-op); see T47's correction note. See `docs/HW_Solo_Tests.md` and
`docs/P20_MailDrop_Measure_Spec.md`.

### T116 — MailDrop protocol measurement (hardware, OPEN)
The real MailDrop command set, prompts, and message-termination sequence
are not known — `tools/hw_check.py maildrop` (P20 Teil B, reworked in
P21.3) is a guided, mitschreib-style recording terminal, not a script,
since a script would have to guess all of that.

1. `python tools/hw_check.py --port COM6 maildrop`
2. Follow (or diverge from, as needed) the tool's suggested sequence:
   `L` (list), `S` (send a test message to yourself, end with `/EX` on
   its own line), `L`, `R` (read it), `S` (a second message), `L`, `K`
   (kill the first), `L`, then `B` to leave the mailbox
3. Type `/quit` to leave the tool's interactive prompt (only needed if
   the terminal has not already stopped itself at a `cmd:` prompt)
4. Optional: confirm on power-cycle that the mailbox content is lost
   (expected, see CLAUDE.md's "no RAM buffer battery" finding)

**Expected result:** a full record of the real message-list format (from
`L`), confirmation that `S`/`R`/`K` work as expected, and — if the
optional step is run — confirmation that the mailbox is empty again
after a power-cycle.

**Status:** ✅ PASS for `L`/`S`/`R`/`K`/`B`, the list format, numbering,
`@BBS`, bulletins (`SB`), traffic (`ST`), the date/time format, and the
power-cycle test (22.09.2026 18:43 + 19:16 —
`hw_logs/20260922_184337_maildrop.log`,
`hw_logs/20260922_191657_maildrop.log`). Round 2 confirmed: `S <to> @
<bbs>` populates the list's `@ BBS` column; `SB`/`ST` post bulletins/
traffic directly as SysOp (status `BN`/`TN`); dates show as
`DD-Mon-YY  HH:MM` (UTC, stamped at store time — a message saved before
`DAYTIME` was ever set keeps showing dots forever, even in later
listings); `MDCHECK` adds `You have mail.` before the prompt when unread
mail exists; **the P22 "size + ~48 bytes" memory formula is WITHDRAWN**
— seven messages show 84 or 112 bytes with no relation to size, only
(unconfirmed) to whether `@BBS` was given, see CLAUDE.md's corrected
table. The power-cycle test itself PASSED this round (six messages
stored, `*** Message not found.` + `18536` free + `MYCALL PK232` after
off/on). All findings recorded in CLAUDE.md's MailDrop facts;
`tools/hw_check.py`'s `parse_maildrop_list()`/
`maildrop_response_has_e_trailer()` handle the confirmed format.

**Round 3 (22.09.2026 20:00, `hw_logs/20260922_200013_maildrop.log`,
`docs/P24_MailDrop_HostMode_Spec.md`) closed both remaining questions:**
- **Foreign FROM confirmed working:** `S OE3GAS < DL1ABC` listed as
  `To=OE3GAS From=DL1ABC` — the earlier two mistyped (`>`) attempts had
  never actually tested this.
- **`^Z` ($1A) does NOT end a message on this firmware.** Sent three
  times (the P23.3 console-EOFError recovery worked exactly as designed
  twice, plus once by typing the two literal characters) — every time
  the mailbox just echoed `$1A` back and stayed in message entry; only
  `/EX` ever ended any of the three messages. Not investigated further
  (unconfirmed hypothesis: a missing trailing `CR`) since `/EX` is
  reliable and is what any real dialog will use.
- **Correction: the stray `/E` trailer is NOT a general format
  element.** Round 1 saw it exactly once; round 3's two `R` responses
  both ended cleanly with no `/E` at all. `maildrop_response_has_e_trailer()`
  already only detects it without assuming it, so no tool change was
  needed — only the P22/P23 documentation claiming it was general is
  corrected (see CLAUDE.md).
- **New finding:** a mailbox command needs a space before its argument
  (`R2` → `*** Not enough`; `R 2` works).
- **New finding:** non-ASCII input ("für") arrives at the TNC as `f?r`
  — but this is `tools/hw_check.py`'s OWN ASCII-only encoding replacing
  the character before it is ever sent, not a TNC limitation that was
  actually measured. Whether the TNC accepts real 8-bit/Latin-1 text
  depends on `8BITCONV` and remains unmeasured.

All findings and their design consequences (validate before sending,
transliterate umlauts until `8BITCONV` is measured, what a restore
feature can and cannot preserve) are recorded in CLAUDE.md's MailDrop
facts. **T116 is now closed** — round 4 would only be needed if a
future `8BITCONV` or Host Mode measurement opens new questions (see
T117 for the Host Mode side, `docs/P24_MailDrop_HostMode_Spec.md`).

### T117 — MailDrop over Host Mode ($60/$70 data channel), OPEN
`T116` measured MailDrop entirely over the verbose-mode serial link.
`HOST 3` (the mode pk232py already enters with) sets bit 1 of the `HOST`
command, which the TRM's Host Mode bit table documents as switching the
MailDrop-login data channel from `$2x`/`$2F` to `$60`/`$70` — but nothing
in the app has ever used that channel, so whether it actually works, and
what it looks like, is unmeasured. `tools/hw_check.py maildrop_host`
(P24.2) is a read-only probe (no `S`/`K`/`E`, no transmission): it creates
one test message via the same known-safe verbose path as `maildrop`, then
in Host Mode sends a bare `L` as a `$60`-CTL frame (Probe A), only sends
`MDCHECK` first if Probe A got nothing (Probe B), reads the noted message
number with `R <n>` if a list came back, sends `B`, and leaves Host Mode.

1. `python tools/hw_check.py --port COM6 maildrop_host`
2. Confirm the single `y/N` prompt (unknown, read-only Host Mode frames
   about to be sent)
3. Let Probe A (and B/C if needed) run to completion

**Expected result:** the printed summary answers, for `Testplan.md`:
1. Which frame type carried the response — `$70`, another `$7x`, or none?
2. Is the mailbox prompt/banner identical to the verbose-mode version?
3. Was a login needed — did the bare `L` (Probe A) work, or only after
   `MDCHECK` (Probe B)?
4. Does the list/read output match the verbose-mode path byte-for-byte?

**First hardware run (2026-09-22, 21:13,
`hw_logs/20260922_211322_maildrop_host.log`):** Probe A (`L`, no login)
got back exactly one frame — `ctl=0x5F` `data=b'XX\x00'`, the generic
Host Mode data acknowledgement every write gets (T101), not mailbox
content. **No `$70` frame at all.** The tool's verdict logic at the time
treated "Probe A got any frame" as "login not needed" and reported that,
so Probe B (`MDCHECK` login, then `L` again) never ran — a false
conclusion, not a real measurement of whether login is needed. **Fixed
P26.1:** `has_mailbox_data_frame()` now requires a frame that is not
`$4F`/`$5F`; `should_run_maildrop_host_probe_b()` and the verdict logic
both use it, so a bare `$5F` ack no longer counts and Probe B runs
whenever Probe A got only acks. This also settled the TRM's own
contradiction about the `MI` mnemonic (ch.12 lists it for both `MDCheck`
and `MFIlter`) — T115 already measured `MI` = MFILTER, so `MI` is not
the answer either, and the real MDCHECK mnemonic is unknown; see T118 /
`mdcheck_scan`.

**Status:** 🔶 PARTIAL — real hardware run done, but the run itself
exposed a tool bug (see above) rather than answering questions 1–4;
needs a **re-run** with the fixed tool. Not closed.

---

### T118 — mdcheck_scan: find the Host Mode mnemonic for MDCHECK, OPEN
The TRM's own Host Mode mnemonic table (ch.12) is internally
contradictory: it lists `MI` for both `MDCheck` and `MFIlter`. T115
already measured `MI` = MFILTER by hardware (`MI` → `$80`, verbose
`MFILTER` → `$80`), so the manual's MDCHECK entry is simply wrong and the
real Host Mode mnemonic for MDCHECK — if one even exists — is unknown.
`tools/hw_check.py mdcheck_scan` (P26.2) searches for it without
guessing: it creates one test message the same way `maildrop_host` does,
then in Host Mode queries every `M?` mnemonic (A–Z) with no argument,
except the denylisted `MO` (MORSE), `MI` (MFILTER, already identified)
and `MM` (MEMORY, has a read side effect) — 23 candidates — stopping at
the first response containing the mailbox prompt's own text.

1. `python tools/hw_check.py --port COM6 mdcheck_scan`
2. Confirm the single `y/N` prompt (up to 23 read-only Host Mode queries,
   naming the three mnemonics that will never be sent)
3. Let the scan run to completion (stops early on a hit)

**Expected result:** either a single mnemonic is reported as a hit
(record it, the exact frame text, and add it to CLAUDE.md's
hardware-confirmed mnemonic table), or the scan reports no hit at all
among the 23 candidates — itself a complete, useful result: it would mean
MDCHECK is not reachable as a two-letter Host Mode mnemonic, and any
future MailDrop dialog must drive the mailbox over the verbose path
instead (record as a `Backlog.md` decision point, not a failure).

**Result, Device A (11.09.1995, PACTOR generation), P26:** no hit among
the 23 candidates — MDCHECK is not reachable as a two-letter Host Mode
mnemonic on this firmware generation.

**Result, Device B (01.08.1991, MBX generation), 23.09.2026, P34
(`hw_logs/20260923_203256_mdcheck_scan.log`):** also no hit among the
same 23 candidates — the Host Mode queries themselves ran normally
(`MAnone`, `MC0`, `MX4`, …), so the scan result is valid. Together with
Device A, the finding now holds across two firmware generations (MBX and
PACTOR); the BASE generation (Device C, 1988) remains untested for this.
**Caveat on this same run:** the verbose phase *before* the scan
(`PACKET`/`MYCALL`/`XMITOK`/the test-message creation) was invalid — the
TNC only echoed each line back, never answering `cmd:` at all (most
likely Converse) — see CLAUDE.md's "Echo without execution" gotcha (P34).
The tool reported "Test message stored as # None" because no message was
ever actually created; the scan's own result (no hit) is unaffected,
since `mdcheck_scan` does not depend on that test message existing.
Fixed under P34 (`tools/hw_check.py::confirm_command_prompt()`) so a
future run either confirms `cmd:` first or aborts cleanly instead of
sending into an unconfirmed state.

**Status:** ✅ ANSWERED (no hit, two generations) — MDCHECK confirmed not
reachable as a two-letter Host Mode mnemonic on Device A and Device B;
Device C (BASE, 1988) not yet tested. See `docs/PK232_firmware_matrix.md`
§2a for the same finding recorded against the device/generation table.

---

### T119 — MailDropSession against real hardware, via the maildrop_session harness (P27/P28), OPEN
`src/pk232py/maildrop/session.py`'s `MailDropSession` replaces the old,
unverified `maildrop.py` — it drives the MDCHECK mailbox entirely over
the verbose-mode link (T118/`mdcheck_scan` found MDCHECK has no Host
Mode mnemonic at all). Software/mock-verified against the real hw_logs/
transcripts (`test_maildrop_protocol.py`, `test_maildrop_session.py`,
`.venv\Scripts\python.exe -m pytest`); `tools/hw_check.py
maildrop_session` (P28, `docs/P28_MailDrop_Session_Harness_Spec.md`) is
the hardware confirmation — a harness with no protocol logic of its
own, calling only `open()`/`list()`/`send()`/`read()`/`kill()`/`leave()`
and reacting to their signals (`MaildropSessionRunner`,
`test_hw_check.py`'s own sequencing tests cover the flow logic without
hardware).

```
python tools/hw_check.py --port COM6 maildrop_session
python tools/hw_check.py --port COM6 maildrop_session --abort-test
```

Expectation list (the harness's own step sequence, `docs/
HW_Solo_Tests.md`'s `maildrop_session` walkthrough has the full detail):

1. `open()` → `ACTIVE`, `prompt_info` with the real free-byte count
2. `list()` → whatever is already in the mailbox
3. `send()` a personal message (subject `T119 personal`) → `stored`
4. `send()` with a foreign FROM (`< DL1ABC`) → `stored`
5. `send()` a bulletin to `ALL` → `stored`, type `B`
6. `list()` → all three present, personal=P, foreign frm=DL1ABC,
   bulletin mtype=B/to=ALL (checked against the remembered message
   numbers, not by re-parsing)
7. `read()` the personal message → body matches what was sent
8. `kill()` the personal message → `killed`, free-byte count rises
9. `list()` → the killed message gone, the other two intact
10. `leave()` → `CLOSED`, then an `HPOLL` query confirms Host Mode is
    active again
11–13. (`--abort-test` only) reopen, `send()` + `abort()` right after
    the subject is accepted → `failed` (success for THIS step — proves
    the recovery path runs and never reports a false success), leave

**Expected result:** all steps PASS in order; a step that fails or times
out (20s) stops the run there, and the harness's own cleanup calls
`leave()` if the mailbox was still open, so the TNC ends back in Host
Mode either way — the closing `HPOLL` query is what actually confirms
that on real hardware. Two test messages (foreign-FROM, bulletin) are
left in the mailbox afterwards by design (only the personal one is
killed) — note that in the log.

**Partial result, 23.09.2026** (P31,
`hw_logs/20260923_184302_maildrop_session.log`): wakeup, Host Mode entry,
the harness's own port handover, `Ctrl-C`, and `MDCHECK` all confirmed
working end to end — P30's byte-level init-phase logging made this
traceable. Aborted before step 1 could complete: the real mailbox prompt
that day used the **square**-bracket device-name form
(`[AEA PK-232M]  18340 free  (B,E,K,L,R,S) >`, not the round form seen on
22.09.2026 — the TNC had hung and been power-cycled since, with a
different EPROM installed, see CLAUDE.md's "MailDrop facts"), which
`find_prompt()` did not recognise yet (only the round form was known at
the time) — so `open()` never produced a `prompt_info`, and the harness's
own Host-Mode-active check then ran too early, misreading the session's
still-in-progress internal recovery as a second, unrelated failure.
Both gaps are fixed under P31 (`protocol.py` now accepts both bracket
forms; the harness waits for `MailDropSession.state` to reach `CLOSED`/
`FAILED` before checking) — steps 2–13 are still unexercised.

**Partial result, 23.09.2026, Device B (MBX, 01.08.1991)** (P35,
`hw_logs/20260923_204041_maildrop_session.log`): step 1 (`open`)
**PASS** — Host Mode left, `Ctrl-C` confirmed, `MDCHECK` recognised
(`bracket='square'`, `free=18340`). Step 2 (`list_empty`) **FAIL** —
`L` got `*** What?` back instead of a listing; cause not yet settled,
see CLAUDE.md's "Mailbox commands terminate with CR only" gotcha for the
three candidate explanations. The recovery/rückweg from P31 ran to
completion and is fully confirmed: `leave()` → Host Mode re-entered →
`HPOLL` answered → session state `CLOSED`. Fixed under P35 (MDCHECK now
sent with `\r` not `\r\n`; `parse_error()` scoped to what comes after a
command's own echo; `MailDropSession` now traces every raw block sent/
received when a trace callback is wired, which `maildrop_session` now
does) — steps 2–13 still unexercised, re-run needed with the trace
active to see what actually came back after `MDCHECK` and after `L`.

**Full result, 24.09.2026, Device B (MBX, 01.08.1991)** (P37,
`hw_logs/20260924_181446_maildrop_session.log`): **10 of 10 steps PASS**
— open, list (empty), send personal, send with a foreign FROM, send a
bulletin, list (three entries), read, kill, list (after kill), leave —
plus the closing `HPOLL` query confirming Host Mode active again. The
P35 fix (MDCHECK sent with `\r`, not `\r\n`) was the actual cause of the
23.09.2026 `L` → `*** What?` failure: with the extra LF gone, `MDCHECK`
produces a clean prompt and `L` answers `*** Message not found.`
normally — a software bug, not a firmware difference between Device A
and Device B. The `/E` trailer after a read message's text
(`...harness\r\n/E\r\n`) reappeared here, same as the single P31
occurrence — `parse_read()` already strips it correctly, so this is
purely a re-classification: no longer "observed once" but "occurs
regularly, and is discarded", see CLAUDE.md. The P22/P23 memory-cost
hypothesis is further undermined: this run's three messages went
61→112, 43→84, 35→84 bytes — the same 112-byte jump seen on Device A
only for a *smaller* message that *did* specify `@BBS`, so size and
`@BBS` presence together still explain nothing; free memory continues
to be read only from the mailbox prompt, never computed.
`Größe = Betreff + Text + 9` and the foreign-FROM `<` syntax both hold
unchanged on this firmware. See `docs/PK232_firmware_matrix.md` §2a for
the same finding recorded against the device/generation table.

**Status:** ✅ PASS — all 10 steps confirmed on Device B, 24.09.2026.

---

### T120 — MailDrop capability detection on Device C (BASE, 1988), OPEN
Device C (`docs/DEVICES.md`) has no MailDrop at all (operator-confirmed
via PuTTY, 23.09.2026). P37 added `SerialManager.detect_maildrop()` (a
verbose-mode `MAILDROP` query, never `MDCHECK`) so the app itself can
tell, and wired the result into `ParamsUploader.upload()` (skips the
whole MailDrop command block) and the UI (`btn_maildrop` tooltip,
`MailDropParamsDialog.set_locked()`). Software/mock-verified only so
far (`test_serial_manager.py::TestClassifyMaildropResponse`,
`test_params_uploader.py::TestMaildropCapabilitySkip`,
`test_params_maildrop_dialog.py`) — never run against Device C itself.

1. Connect the app to Device C and let it initialise normally (verbose
   mode → parameter upload → Host Mode, whichever `connect_mode` is
   configured).
2. Watch the verbose-mode traffic (or the log) during the upload.

**Expected result:** the `MAILDROP` capability query answers `?What?`;
none of `MAILDROP`/`MDMON`/`MMSG`/`TMAIL`/`3RDPARTY`/`KILONFWD`/`MTEXT`
are sent afterwards (no `?What?` from any of those seven); the Packet
screens' MailDrop button shows the tooltip "This firmware has no
MailDrop"; opening `Parameters → MailDrop...` shows every field disabled
with the same tooltip, none hidden.

**Status:** ⬜ OPEN — needs a real run with Device C connected.

---

### T121 — Local MailDrop archive: disabled by default creates no file
`MailDropArchive`/`open_archive()` (P38, `maildrop/archive.py`) is
PK232PY's own local record of MailDrop messages — deliberately optional
(`MailDropConfig.archive_enabled = False` by default) since collecting/
restoring costs real time and suspends packet operation for the whole
session (measured 24.09.2026, Device B, T119: ~4s open, ~6–7s per
message, ~3s leave). This test only checks the "off means off" contract,
software-verified (`test_maildrop_archive.py::TestOpenArchive`); no
hardware or UI wiring involved yet (this package builds no session-mask
wiring at all — Backlog.md).

1. `open_archive(MailDropConfig(archive_enabled=False, archive_path=<any path>))`
2. **Expected result:** returns `None`; no file exists at `archive_path`
   afterwards.
3. `open_archive(MailDropConfig(archive_enabled=True, archive_path=<path>))`
4. **Expected result:** returns a `MailDropArchive`; the file now exists.

**Status:** ✅ PASS (2026-09-24, software-verified —
`test_maildrop_archive.py::TestOpenArchive::test_disabled_creates_no_file`/
`test_enabled_creates_the_file`).

---

### T122 — MailDrop session dialog on real hardware, OPEN
`ui/dialogs/maildrop_dialog.py`'s `MailDropDialog` (P39) — software/
mock-verified against a fake `MailDropSession`
(`test_maildrop_dialog.py`) and the four-condition button/menu gate
(`test_main_window_packet.py::TestMaildropGate`); never run against a
real TNC.

1. Connect to the TNC (HF or VHF Packet, Host Mode), no channel
   connected. `btn_maildrop` / `TNC → MailDrop…` should be enabled.
2. Open the dialog — gate page shows the three-check list, click "Open
   MailDrop session".
3. **Expected:** progress shown while `OPENING`, then the session page
   with the real mailbox listing and free-byte count.
4. Write a new message (`New...`), send it — confirm it appears in the
   list and, once selected, its body matches what was typed.
5. Read the message back (select it, or after a restart of the
   dialog) — body must match.
6. Kill it — confirm the kill dialog names where it will be deleted
   (TNC/archive/both correctly), then confirm it is gone from the list.
7. Click "End session" — confirm the dialog returns to the gate page,
   not closed, and a subsequent `HPOLL`-style check shows Host Mode
   active again (same confirmation `MailDropSession` already does
   internally).
8. Re-open the dialog, connect a packet channel from another station,
   then try to open the gate's session button again.
   **Expected:** the entry point (button/menu) is already disabled with
   "disconnect channel N first" once a channel connects — confirm this
   reflects live without needing to reopen the dialog.
9. With a session ACTIVE, close the dialog window (X or Esc).
   **Expected:** confirmation prompt; `Cancel` leaves the session
   running; confirming sends `B`, shows the leaving-Host-Mode progress
   text, and the window only actually closes once Host Mode is
   confirmed active again.

**Status:** ✅ PASS (2026-09-25, Device B, Release 01.AUG.91) — the
operator ran the full dialog against real hardware: gate page with its
three-check list, opened the session, wrote a message, read it back,
killed it, closed the window via the title-bar close button (X) with
the confirmation prompt and visible leaving-Host-Mode progress text
shown, and confirmed Packet operation was available again afterward.
Everything worked as designed.

---

### T123 — Typing into every Packet-screen input field, live GUI
`is_keyboard_input_widget()` (P41) — software-verified against the real
app-wide event filter with `QTest.keyClick()`
(`test_main_window_packet.py::TestKeyboardFocusHandling`); the Dest-field
case reproduces hardware-confirmed 24.09.2026 (typing a callsign landed
in the TX window instead). Never run through the actual live GUI.

**UI note (P42, 2026-09-24):** steps 2 and 7 rewritten — the separate Dest
field they were written against no longer exists; the same QLineEdit-type
regression is now exercised through a channel chip's own inline editor
instead (`ChannelChip.editor`), which needs the exact same
`is_keyboard_input_widget()` exemption `cb_dest` needed a workaround for,
but requires **no** `ScreenFocusController` registration to get it (see
CLAUDE.md §6).

1. Connect to the TNC, activate HF or VHF Packet, enter Host Mode.
2. Open a free chip's inline editor (click the current chip again, or
   double-click any free chip), type a callsign.
   **Expected:** the callsign appears in the chip's editor, not the TX
   window.
3. Click into **via**, type a path.
   **Expected:** appears in via (already worked before P41 — the
   control case).
4. Click into **Monitor**, press a digit key.
   **Expected:** the Monitor selection changes; TX window stays
   unaffected.
5. Click into **HBAUD**, press a key matching one of its values.
   **Expected:** same as Monitor.
6. Click a button (e.g. Unproto) or a channel-bar chip (without opening
   its editor), then type.
   **Expected:** unchanged existing behaviour — characters land in the
   TX window, since buttons/chips are `Qt.FocusPolicy.NoFocus` and never
   actually keep keyboard focus.
7. With a chip's editor open, press `Ctrl+Up`/`Ctrl+Down`.
   **Expected:** no channel change; plain arrow keys still move the
   cursor within the field.

**Status:** ⬜ OPEN — needs a live-GUI click-through; software-verified
already covers all seven steps
(`test_main_window_packet.py::TestKeyboardFocusHandling`, updated
2026-09-24 for P42's chip editor), including Monitor and HBAUD actually
changing value (not just staying at their default) without leaking into
the TX window.

---

### T124 — Connect-in-chip interaction (P42), software-verified
`test_packet_screen.py::TestChipConnectFlow` and
`test_main_window_packet.py::TestConnectRejectedOnChannelZero`. Never run
through the actual live GUI.

1. Click a different chip → switches the current channel only, no editor
   opens.
2. Click the already-current free chip a second time (or double-click any
   free chip, or "Connect…" from its context menu) → opens that chip's
   inline editor.
3. A busy chip, or the `UI` chip → none of the above ever opens an editor.
4. Enter a valid callsign in an open editor → `connect_requested(ch,
   callsign)` fires for THAT channel; `CO` goes out on it (T34/T87/T93).
5. Enter an invalid callsign → editor stays open, red border + tooltip, no
   signal.
6. `Esc`, or losing focus, while editing → closes the editor, no signal.
7. Double-click an unconnected MHEARD row → opens the FIRST free chip's
   editor (not necessarily the currently selected one), prefilled with the
   heard callsign.
8. Typing in an open chip editor never leaks into the TX window (T123).
9. `Ctrl+Up`/`Ctrl+Down` while a chip editor is open does not change the
   channel (T123 step 7).
10. `Ctrl+D` while a busy channel is current → disconnects it (T37); on a
    free channel → does nothing.
11. "Connect via…" on a free chip's context menu → `PacketConnectDialog`
    (callsign + optional digipeater path), channel fixed to the chip that
    opened it, not editable in the dialog.

**Status:** ✅ PASS (2026-09-24, headless — `TestChipConnectFlow` (9 cases)
in `test_packet_screen.py`, plus `TestConnectRejectedOnChannelZero`'s two
cases in `test_main_window_packet.py` for step 3's UI-channel case).
Interactive manual click-through and hardware re-test open (see the
Definition of Done in `docs/P42_Connect_In_Chip_Spec.md`).

---

### T125 — Upload-before-Host-Mode guard and verification (P40)

Bugfix (24.09.2026, 21:27): 68 parameter-upload commands each hit
`write_verbose_wait()`'s 5 s timeout (~6 minutes total) because the TNC
was in Host Mode the entire time — there is no `cmd:` prompt there, so
none of the 68 commands actually reached it.

**Unit-verified (`test_params_uploader.py`, `test_serial_manager.py`):**
1. `ParamsUploader.upload()` with a stub serial reporting
   `is_host_mode = True` → sends nothing (`0` returned), logs an `ERROR`
   naming Host Mode as the reason.
2. Same, but `is_host_mode = False` → uploads normally (sample-tested
   against `TestRefusesUploadInHostMode::
   test_upload_proceeds_normally_when_not_in_host_mode`).
3. A stub that answers `cmd:` for the first 5 commands then goes silent
   → upload aborts after `_MAX_CONSECUTIVE_SILENT` (3) consecutive
   silent commands (5 + 3 + 1 = 9 sent, not the full command list),
   logs an `ERROR` naming "aborting upload". An isolated single miss
   (every other command silent) does **not** abort — only consecutive
   silence counts.
4. `ParamsUploader.verify()` with a stub answering MYCALL/PACLEN/
   MAXFRAME correctly → `(3, 3)`, logs `INFO "parameter upload verified
   (3/3)"`. A mismatch or a missing answer logs a `WARNING` naming the
   parameter and is not counted; MYCALL left as the `NOCALL` placeholder
   (never uploaded in the first place) is skipped, not treated as a
   mismatch.
5. `SerialManager._parse_verbose_query_value()` (pure function) correctly
   extracts the value from a real verbose-mode response shape (confirmed
   P15) and skips the command's own echoed line, the same technique
   `_classify_maildrop_response()` already uses for MAILDROP.

**Still open (needs real hardware):** a live connection showing the
`"parameter upload verified (3/3)"` line in the log and no `no cmd:`
warning at all, with the whole connect sequence completing in under a
minute as before (not the ~6 minutes the bug produced).

**Status:** ✅ PASS (2026-09-25, unit-verified — 15 new/updated tests in
`test_params_uploader.py`, 5 new tests in `test_serial_manager.py`, full
suite 524 passed). Live hardware re-test open.

---

### T126 — TNC-state detection chain and confirmed-verbose gate (P43)

Bugfix (24.09.2026, reproduced on the device): the app leaves the TNC
in Host Mode when it quits (or an unclean exit — crash, force-kill —
never reaches the documented HOST-OFF-on-disconnect path at all); on the
next app start, `SerialManager.is_host_mode` starts `False` regardless
(the software's own belief, not the device's real state), and the old
passive wakeup check never saw the stray SOH byte it was hoping for,
since a TNC in Host Mode answers `*` with nothing at all. Result: T125's
68-command silent upload.

**Unit-verified (`test_serial_manager.py::TestTncStateDetectionChain`,
against `_FakePort`, a fully synchronous in-memory stand-in for
`serial.Serial`):**
1. `*` → banner + `cmd:` → step 1 confirms verbose; no `CR`, no HPOLL
   query frame ever sent.
2. `*` silent, `CR` → `cmd:` → step 2 confirms verbose; no HPOLL query
   frame sent.
3. `*` and the first `CR` silent, HPOLL query frame (`build_command(b'HP')`)
   → a `$4F`-CTL frame → Host Mode confirmed; `FRAME_HOST_OFF` written
   directly, `CR` repeated → `cmd:` → verbose confirmed after the exit.
4. All three (steps 1-3) silent → abort; `SerialManager.verbose_confirmed`
   stays `False`; the abort message names the port and baud rate.
   **DoD-critical:** a `ParamsUploader` built against this same
   `SerialManager` afterwards sends exactly zero parameters.
5. The HPOLL query answers (Host Mode confirmed), but the post-exit `CR`
   retry never sees `cmd:` → abort the same way as case 4, not a silent
   "assume it worked".
6. `ParamsUploader.upload()` refuses when `verbose_confirmed` is `False`
   even though `is_host_mode` also reads `False` — the P43.2 gate is
   strictly additional to P40.2's, not a replacement
   (`TestRequiresConfirmedVerbosePrompt` in `test_params_uploader.py`,
   including that a legacy test double which never defines
   `verbose_confirmed` at all still uploads normally — the permissive
   `getattr` default only ever matters for real `SerialManager` instances).

**Timing:** each of the three probing steps is capped at
`_TNC_STATE_STEP_TIMEOUT` (1.5 s); the worst case (case 4, all three
silent) totals under 5 s, measured directly by the unit test itself
(no mocked-out sleep — the whole test file runs in ~14 s for exactly
this reason).

**Still open (needs real hardware):** quit the app, then immediately
reconnect WITHOUT power-cycling the TNC — expect the connect sequence to
complete in well under a minute either way (freshly-verbose or
recovered-from-Host-Mode), with `"parameter upload verified (3/3)"` in
the log and no `no cmd:` warning at all.

**Status:** ✅ PASS (2026-09-25, unit-verified — 8 new tests across
`test_serial_manager.py` and `test_params_uploader.py`, full suite 532
passed). Live hardware re-test open.

---

### T127 — Chip failed state, verbose terminal, recovery stage (P44)

Three findings from the same 25.09.2026 operator session.

**A — chip states (screenshot: chip 1 amber on OE3TEC, status pill
already DISCONNECTED):**
1. A channel that is CALLING and receives "Retry count exceeded",
   "`<call>` busy", or a DISCONNECTED before ever reaching CONNECTED →
   the chip shows CH_FAILED (red) for 1.5s, then reverts to CH_FREE on
   its own — not a silent snap straight back to grey.
2. A channel that IS CONNECTED and then DISCONNECTED (normal hangup) →
   straight to CH_FREE, no red flash — nothing failed there.
3. A CALLING chip shows a trailing ellipsis (`OE3TEC ...`) and pulses
   amber (one shared animation for the whole bar, 1.2s cycle,
   `InOutSine`, starts/stops with the first/last calling channel).
4. MHEARD's connected-station colour is green (`_CHIP_FILL[CH_CONNECTED]`),
   matching the chip; the legend says "green = connected", not "amber".

**B — verbose terminal:**
1. Enter on an empty verbose-terminal field sends a bare CR (previously
   sent nothing at all).
2. After a successful connect, the terminal shows what the TNC actually
   sent during init (banner + `cmd:`, or just `cmd:`) — previously the
   RX window stayed empty because the P43 detection chain consumed that
   response internally and nothing mirrored it into the UI.

**C — recovery stage in the detection chain (console: app killed with
`Ctrl-C` while in Host Mode, next connect got 0 bytes back on all three
of the original steps, including the HPOLL query):**
1. A new step 3b sends the documented recovery sequence (double-SOH +
   GG, then HOST OFF — the same bytes the "Recovery" menu action sends)
   before giving up, for exactly this "TNC mid-frame after an abrupt
   kill" case.

**Unit-verified:**
- `test_packet_screen.py::TestChipCallingFailedStates` (8 cases: ellipsis,
  plain callsign when connected, retry/busy/disconnected-while-calling
  all through CH_FAILED, a normal hangup skipping it, a stale timer not
  undoing a fresh state change, a failed chip still being interactive).
- `test_packet_screen.py::TestPulseAnimation` (5 cases: starts/stops with
  the first/last calling channel, keeps running while any other channel
  still calls, a pulse tick only touches calling chips' background,
  `reset()` stops it).
- `test_packet_screen.py::TestMheardColourSemantics` (2 cases: the
  connected-station colour matches the chip's green, the legend text).
- `test_packet_hf.py::TestOnChannelState::test_retry_count_exceeded_frees_channel`
  — "Retry count exceeded" now reaches `on_channel_state(ch, "free", "")`,
  where it used to reach neither `on_link_message` nor this channel path.
- `test_main_window_verbose.py::TestVerboseTerminalBareEnter` (3 cases:
  empty Enter sends exactly one bare CR, whitespace-only same, a real
  command still sends `<text>\r\n` as before).
- `test_serial_manager.py::TestTncStateDetectionChain::
  test_step3b_recovery_sequence_confirms_verbose_after_half_frame_hang`
  — HPOLL query silent → recovery sequence sent → repeated CR confirms
  verbose; `test_all_three_silent_aborts_and_sends_nothing_to_the_uploader`
  extended to confirm the recovery sequence is attempted even in the
  full-abort case, not skipped straight to step 4.

**Also found and fixed finishing this sprint:** a real cross-test crash
(`RuntimeError: wrapped C/C++ object of type QLabel has been deleted`) —
the failed-flash timer used a free-floating `QTimer.singleShot()`, which
kept firing 1.5s later even after its owning screen had been garbage
collected in an EARLIER test, corrupting an unrelated LATER test's own
exception capture (only visible running the full suite, never a single
test file — the same shape as the P41 stale-event-filter finding). Fixed
by parenting the timer to `ChannelBar` instead (`_schedule_failed_clear()`).

**Hardware-confirmed (2026-09-25/26, Device B):** the chip colour states
(A above) were seen live — pulsation while calling, the red CH_FAILED
flash on a failed attempt, and the automatic revert to free afterward,
all matching the design. Killing the app and reconnecting without a
power-cycle (C above) also completed the connect sequence successfully
via the recovery stage during this same test pass.

**Still open (needs real hardware):** attempt a Connect to an
unreachable callsign specifically and confirm the chip flashes red
before reverting to free (a failed-attempt-by-rejection case,
distinct from the app-killed/recovery-stage case already confirmed
above).

**Status:** ✅ PASS (2026-09-25, unit-verified — 20 new tests across
`test_packet_screen.py`, `test_packet_hf.py`, `test_main_window_verbose.py`
(new file) and `test_serial_manager.py`; full suite 552 passed;
hardware-confirmed 2026-09-25/26, Device B, for the chip-state and
recovery-stage findings above). One narrower hardware case (failed
connect to an unreachable callsign) still open.

---

### T128 — Recovery feedback, honest connection state after a failed init (P45, menu wording updated P46)

Bugfix (25.09.2026, operator at the device): TNC in Host Mode → app
started → Connect → the detection chain's own error → the app still
showed itself as connected (Host Mode button enabled, firmware still
"unknown") → Recovery pressed → no visible reaction at all → "Host Mode"
pressed → SWITCHING → Baudot screen (TNC was in fact reachable).

**Menu note (P46):** Connect/Disconnect/Host Mode/Recovery no longer
have their own toolbar buttons - all of them moved into the **TNC**
menu (or its shortcuts) as part of P46's "TNC actions live in the menu
only" change. The steps below use the menu wording; the underlying
actions and their behaviour are unchanged.

**Live sequence to run:**
1. Kill the app with `Ctrl-C` while it is in Host Mode (leaves the TNC
   possibly stuck, per P44's step 3b — see the note below).
2. Start the app again, **TNC → Connect + Enter Terminal Mode...**
   (Ctrl+T).
   **Expected (if the chain cannot confirm anything):** the connect
   sequence's own error appears as a dialog AND in the status bar; the
   mode indicator reads "ERROR", not "VERBOSE MODE" or "HOST MODE"; the
   mode combo is disabled; **Connect + Enter Terminal/Host Mode...** and
   **Emergency Reconnect (Host Mode Recovery)** all stay enabled in the
   TNC menu.
3. **TNC → Emergency Reconnect (Host Mode Recovery)** (Ctrl+R).
   **Expected:** the menu entry locks and reads "Recovery running..."
   immediately; when it finishes, a message appears in BOTH the status
   bar and the verbose terminal's RX window, and the entry returns to
   normal. One of:
   - `"Connection recovered - TNC is at the command prompt (verbose mode)."`
     — proceed to connect normally (parameter upload runs automatically).
   - `"Recovery did not reach the TNC. Power-cycle it and reconnect."`
     — also shown as a dialog.
4. If Recovery succeeded, connect normally (Host Mode entry, parameter
   upload) and confirm it behaves exactly as any other successful
   connect — no separate code path.

**Note on step 1:** P44 suspected killing the app mid-frame leaves the
TNC's parser stuck, explaining why the chain's HPOLL query (step 3) can
get nothing back. P45 corrected this to a suspicion, not a measured
finding — a healthy TNC in Host Mode is ALSO silent in a plain terminal
program, so this step may or may not actually reproduce a stuck TNC;
either way, steps 2-4 above are what this test case is really checking.

**Unit-verified:**
- `test_serial_manager.py::TestRecoverySequence` (3 cases) — `cmd:`
  confirmed after the sequence reports success and sets
  `verbose_confirmed`; only the HPOLL query answering still ends in
  success after the chain's own exit-and-recheck; silence throughout
  reports the power-cycle message and leaves `verbose_confirmed` False.
- `test_main_window_connection.py` (new file, 11 cases; P46 removed the
  toolbar's own "Enter Host Mode"/"Connect"/"Recovery" buttons - see
  T129 below, assertions now read the TNC menu actions instead) —
  `_update_connection_ui(True)` sets "CONNECTING...", never "VERBOSE
  MODE" outright; `_on_init_failed()` sets "ERROR", disables the mode
  combo, and explicitly keeps Connect and Recovery enabled; pressing
  Connect again after a failed init retries `init_tnc()` on the
  still-open port instead of silently doing nothing; `_on_recovery()`
  locks the menu entry immediately; `_on_recovery_finished()` always
  re-enables it and shows the message in the verbose terminal, plus a
  dialog on failure.

**Status:** ✅ PASS (2026-09-25, unit-verified — 14 new tests across a
new `test_main_window_connection.py` and `test_serial_manager.py`'s
`TestRecoverySequence`; full suite 566 passed). Live hardware re-test
open (the full sequence above, once, per the Definition of Done).

---

### T129 — Emergency Reconnect works from any state, and the toolbar has no TNC buttons (P46)

P46 turned Recovery into the "Emergency Reconnect (Host Mode Recovery)"
entry: it must work from literally ANY state, not just after a failed
init (T128's scenario) - including with no connection attempted at all
in this app run, opening the port itself from the saved config. This
case also covers the Teil A fix (Recovery no longer leaks its own
detection frames into the RX window) and the Teil C toolbar/menu move.

**Live sequence to run:**
1. Start the app fresh - do NOT connect at all.
2. **TNC → Emergency Reconnect (Host Mode Recovery)** (Ctrl+R).
   **Expected:** the entry is enabled (never greyed out just because
   nothing is connected yet); the port opens using the last-saved
   port/baud from Settings; the same detection chain runs; on success,
   `"Connection recovered - TNC is at the command prompt (verbose
   mode)."` appears and the app ends up in verbose mode exactly as a
   normal Connect would (parameter upload/Host Mode entry then follow
   the usual path).
3. Repeat with the TNC deliberately left in Host Mode beforehand (kill
   the app with Ctrl-C while in Host Mode, restart, do NOT press Connect
   first - go straight to Emergency Reconnect).
   **Expected:** same successful outcome; the verbose terminal's RX
   window shows only the `[SYS] Recovery: ...` lines, never raw framed
   bytes (the 25.09.2026 screenshot bug this package fixed).
4. Check the toolbar: no `Connect`/`Disconnect`/`Host Mode`/`Recovery`
   button anywhere - only the mode selector, the TNC-Firmware label and
   the mode indicator remain. All four actions are reachable from the
   **TNC** menu instead.

**Unit-verified:**
- `test_serial_manager.py::TestRecoveryTakesOverTheReadPath` (2 cases) —
  no write happens while a (real or stubbed) reader is still "running";
  `raw_data_received` never fires during a full recovery run.
- `test_serial_manager.py::TestRecoveryEmergencyReconnect` (2 cases) —
  `recovery(port_name, baudrate)` opens the port via the injected port
  factory when not connected and reports success; with no port and
  nothing configured it does nothing.
- `test_main_window_connection.py::TestMenuOnlyTncActions` (4 cases) —
  the toolbar has no TNC action buttons; the Emergency Reconnect entry
  has the Ctrl+R shortcut and the new wording; every TNC menu shortcut
  is distinct; the menu's Ctrl+D (serial disconnect) does not collide
  with the Packet screen's own channel-disconnect shortcut (moved to
  Ctrl+K, `test_packet_screen.py`'s renamed Ctrl+K tests plus a new
  regression test confirming Ctrl+D no longer disconnects a channel).

**Status:** ✅ PASS (2026-09-25, unit-verified — full suite 576 passed).
Live hardware re-test open (steps 1-4 above, per the Definition of Done).

---

### T130 — Link message appears in its own channel, not the visible one (P47)

Bugfix (25.09.2026, screenshot): the UI chip (channel 0) showed
`*** Retry count exceeded *** ... DISCONNECTED: OE3XTC ***` — that
message belongs to channel 1, where the connect was running.
`HFPacketMode._handle_link_msg()` already reads the channel from the
`$5x` frame's own CTL nibble and calls `on_link_message(ch, text)`; two
consumers already used it (ChannelBar/MHEARD, Unproto gating, T102) but
the RX-window display (`_on_mode_link_message()`) ignored it and always
wrote into whichever channel/screen happened to be visible. Analogous to
T100 (the same ALL/CH filter, now reused for link messages instead of
reimplemented).

**Live sequence to run:**
1. Connect to an unreachable callsign on channel 1, while channel 0 (UI)
   is the visible chip.
   **Expected:** the message does **not** appear on the UI chip's RX
   window.
2. Switch to channel 1.
   **Expected:** the message is there, exactly as it happened
   ("*** ... ***" format, unchanged colour semantics).
3. Switch view to `ALL` (still on any channel).
   **Expected:** the message appears with its channel noted, e.g.
   `[CH1] *** DISCONNECTED: OE3XTC ***` — the same tag `append_channel_data()`
   already uses for ordinary channel data (T100).
4. Open **HF/VHF Packet Parameters → Display → "Show TNC link messages
   in the UI channel"**, turn it on. Repeat step 1's connect attempt.
   **Expected:** the message now ALSO appears on the UI chip, tagged
   `[ch1] *** ... ***` in the text itself (not just the ALL-view tag,
   since the UI channel is not necessarily in ALL view).
5. Confirm AMTOR/PACTOR link messages (CONNECTED/DISCONN/...) still
   appear exactly as before — these calls carry no channel argument at
   all and are unaffected by this fix.

**Unit-verified:**
- `test_main_window_packet.py::TestLinkMessageAppearsInItsOwnChannel`
  (9 cases) — a channel-1 message appears while channel 1 is visible;
  the same message does not appear on the UI chip in `CH` view; `ALL`
  view shows it with the `[CH1]` tag; channel 15 (`$5F`, not
  channel-scoped — e.g. the generic data ack) always lands in the UI
  channel regardless of the mirror setting, and is never duplicated by
  it; the mirror setting is off by default (no leak into the UI
  channel) and, when turned on, adds a second, `[ch1]`-tagged line in
  the UI channel; a single-argument `on_link_message(msg)` call
  (AMTOR/PACTOR, channel is `None`) is routed exactly as before P47;
  `_set_status()` keeps firing regardless of the visible channel (T102's
  own rule, unchanged).
- `test_param_dialogs_roundtrip.py` — the new
  `HFPacketConfig.show_link_messages_in_ui_channel` field passes Tests
  A-C (widget↔config↔INI wiring) and is listed in `UPLOAD_EXEMPT` for
  Test D ("display setting, not a TNC parameter" — it has no
  corresponding TNC command at all).

**Status:** ✅ PASS (2026-09-25, unit-verified — full suite green;
hardware-confirmed 2026-09-25/26, Device B — link messages stayed in
their own channel throughout the operator's test pass, steps 1-3
above).

---

### T131 — Enter Host Mode from an existing verbose connection; banner as one block (P49)

Two independent findings from the same operator session, 25.09.2026.

**Finding A:** the TNC menu had `Leave Host Mode + Return to Terminal`
but no way back IN from an existing verbose connection - "Connect +
Enter Host Mode..." only ever reaches Host Mode from a fresh connect
and greys out once connected, so an operator who connected via
"Connect + Enter Terminal Mode..." had no way to switch at all.

**Finding B (screenshot):**
```
PK-232M is u[SYS] TNC ready in verbose mode
[SYS] Fast Init — parameter upload skipped
[SYS] Verbose terminal ready (fast init)
sing default values.
```
The word "using" torn apart by the app's own `[SYS]` lines, plus boxes
(unfiltered control bytes) at the start of some lines.

**Live sequence to run:**
1. **TNC → Connect + Enter Terminal Mode...** (Ctrl+T).
   **Expected:** the banner appears as ONE continuous block in the RX
   window, with no boxes at the start of any line, followed by the
   `[SYS] TNC ready in verbose mode` line - never interleaved with it.
2. Check the TNC menu: **Enter Host Mode** (Ctrl+H) is enabled;
   **Leave Host Mode + Return to Terminal** is disabled.
3. **TNC → Enter Host Mode** (Ctrl+H), with Fast Init OFF (Settings).
   **Expected:** parameters upload (visible in the RX window), then the
   TNC switches to Host Mode; the mode indicator ends on "HOST MODE".
4. Leave Host Mode (Ctrl+L), then **Enter Host Mode** again (Ctrl+H)
   without disconnecting in between.
   **Expected:** no second upload runs - a single `[SYS] parameters
   already uploaded` line, straight to Host Mode.
5. Disconnect, reconnect via **Connect + Enter Terminal Mode...**, this
   time with Fast Init ON (Settings), then **Enter Host Mode** (Ctrl+H).
   **Expected:** a dialog appears: "Fast Init skipped the parameter
   upload. The TNC is running on its stored values and cannot be
   configured once Host Mode is active. Upload parameters now?" with
   `Upload and switch` / `Switch without upload` / `Cancel`.
   - `Switch without upload` → Host Mode immediately, no upload.
   - `Cancel` → stays in verbose mode, nothing happens.
   - (repeat once more) `Upload and switch` → parameters upload, then
     Host Mode.

**Unit-verified:**
- `test_main_window_connection.py::TestTncMenuGating` (4 cases) - only
  the Connect actions are enabled while disconnected; only `Enter Host
  Mode` is enabled while connected+verbose; only `Leave Host Mode` is
  enabled while connected+Host Mode; a disabled `Enter Host Mode`'s
  tooltip names the reason.
- `test_main_window_connection.py::TestEnterHostModeFromVerbose`
  (8 cases) - not connected/not verbose does nothing; already uploaded
  this session skips straight to Host Mode; upload outstanding with
  Fast Init off uploads first; Fast Init on asks, and each of the three
  choices (upload/skip/cancel) does exactly what it says; a new
  connection resets the "uploaded this session" flag.
- `test_main_window_connection.py::TestBannerCollection` (4 cases) - a
  banner arriving in two fragments (one already captured, one
  straggling in afterward) is still shown as one continuous block,
  before the `[SYS]` line; raw data is buffered, not displayed, while a
  collection is in progress; control characters are filtered from the
  display; no banner bytes at all still shows the `[SYS]` line.
- `test_main_window_connection.py::TestMenuOnlyTncActions` - the new
  `Enter Host Mode` (Ctrl+H) shortcut does not collide with any other
  TNC menu shortcut.

**Status:** ✅ PASS (2026-09-25, unit-verified — full suite green). Live
hardware re-test open (steps 1-5 above).

**Addendum, hardware-confirmed (2026-09-25/26, Device B):** the
firmware release label in the header (populated from this same
collected banner, see P55.D/`_finish_banner_collection()`) showed the
correct `Release 01.AUG.91` after connecting — the "TNC-Firmware:
unknown" symptom that motivated P55.D did not reproduce here.

---

### T132 — Per-channel RX documents, compact prefixes, resizable TX, MHEARD auto-population (P50)

Four independent findings from one operator session, 25.09.2026.

**Finding A (channel offset) — ✅ RESOLVED, no offset (2026-09-25/26,
Device B):** screenshot 19:07 — chip 1 green with `OE3TEC` ("Ch 1
Partner: OE3TEC"), but every received line and the eventual
`*** DISCONNECTED: OE3TEC-1 ***` tagged channel 2 (the old `[CH2]`
format). Audited the full channel path in code
(`build_ch_cmd()`/`ctl_channel()`/`_make_host_frame()`/`ChannelBar`'s
dict-keyed state) — **no code-level offset found**; `SerialManager.
send_channel_command()` gained a DEBUG log of the requested channel
next to the actual CTL byte for every CONNECT/DISCONNECT frame, next to
the existing RX-side `ch=%d`/`ch%d` logging, so a hardware capture
could compare both directly. The repeat run confirms it: in the ALL
view the compact tag reads `1│` for channel 1's own traffic, matching
chip 1 — no offset on real hardware either. The original screenshot's
appearance is best explained by the pre-P50 `[CHn]` tag format/display
logic itself (already superseded), not a channel-numbering bug in the
protocol layer.

**Live sequence to run (to settle Finding A):**
1. Connect to a real station on channel 1.
2. Capture the DEBUG log for the whole session (both the `TX channel
   cmd: channel=1 ctl=0x41 ...` line and every subsequent `ch=1`/`ch1`
   RX line).
3. **Expected, if the report reproduces:** the TX line shows `channel=1
   ctl=0x41` (confirming the CO frame itself was correct) while later RX
   lines show a DIFFERENT channel — settling that the TNC itself, not
   pk232py, changed the channel. **If the RX lines also say channel=1
   throughout** and only the CHIP/RX-window display disagreed, that
   would point back at a display bug worth re-opening with the log
   attached.

**Findings B-E, live sequence to run:**
4. Connect on channel 1, type text, switch to channel 3, switch back to
   channel 1.
   **Expected:** channel 1's full conversation history is still there —
   not just what arrived after switching back (T100's own steps confirm
   the ALL/CH document switch itself).
5. Switch to `ALL` view.
   **Expected:** both channels' data appear in arrival order, each RX
   line from a QSO channel tagged with a compact `n│` (e.g. `1│`), no
   prefix at all in `CH` view.
6. Open **HF/VHF Packet Parameters → Display → "Show timestamps in the
   RX view"**, turn it on.
   **Expected:** every RX line now also shows `[HH:MM:SS]` in a muted
   colour, ahead of the channel tag (ALL view) or the text (CH view).
7. Drag the handle between the RX and TX windows.
   **Expected:** RX/TX heights change accordingly; RX also grows when
   the whole application window is made taller. Restart the app.
   **Expected:** the dragged split is still there.
8. Connect to a station on an unconnected channel, without pressing
   MHEARD's Refresh button.
   **Expected:** the station appears in MHEARD immediately, with its
   channel number and in green. Disconnect.
   **Expected:** the station stays in the MHEARD list, but loses the
   channel number and the green colour (it was still heard).

**Unit-verified:**
- `test_packet_screen.py::TestPerChannelRxDocuments` (9 cases) —
  channel 1's history survives switching away and back; ALL contains
  both channels in arrival order; CH view has no prefix, ALL view has
  the compact tag; timestamps off by default and on when enabled; scroll
  position is remembered per channel; `reset_channels()` clears every
  document; a system message's colour override is applied in the
  document.
- `test_packet_screen.py::TestMheardAutoPopulation` (3 cases) —
  CONNECTED adds the partner with its channel; `add_entry_if_new()`
  never duplicates; a disconnected station stays in the list but loses
  its channel/colour.
- `test_main_window_packet.py::TestPacketRxTxSplitterPersistence` (1
  case) — the RX/TX splitter's sizes are saved to (and read back from)
  `QSettings` under the right per-screen key, redirected to a fake store
  so the test never touches the operator's real settings (same isolation
  principle as P48's config-path fixture, applied to the registry-backed
  `QSettings` store instead of the INI file).
- `test_main_window_packet.py::TestLinkMessageAppearsInItsOwnChannel` —
  updated for the new `n│` ALL-view tag format (was `[CHn]`).
- `test_packet_hf.py::TestOnChannelState` — `DISCONNECTED`/busy now pass
  the extracted partner through (needed for the MHEARD hook); `Retry
  count exceeded` still passes `""` (P47's own rule: it carries no
  callsign, and the extraction fallback would otherwise misread the
  message text itself as one).

**Status:** ✅ PASS (2026-09-25, unit-verified — full suite green;
hardware-confirmed 2026-09-25/26, Device B). Finding A resolved (no
offset — see above). Steps 4 and 8 confirmed live: channel 1's
conversation history was still fully there after switching away and
back (step 4), and MHEARD gained a partner's callsign, channel number
and time with no manual Refresh needed (step 8). Steps 6-7 (timestamp
toggle, splitter drag-and-persist) not specifically exercised in this
pass — left open.

---

### T133 — Disconnect and immediately reconnect; no false "No PK-232 responding" (P52)

A console capture (25.09.2026, 23:30) showed a fresh reconnect fail with
`Init: Host Mode exit did not reach cmd:` even though the TNC was
reachable the whole time — two root causes, both fixed under P52: step
3's HPOLL query mistook its own verbose-mode echo for a genuine Host
Mode answer (Fehler 1), and the detection chain's reads could be cut
short before a multi-chunk `cmd:` response finished arriving (Fehler 2).

**Live sequence to run:**
1. Connect normally (Connect + Enter Terminal Mode, or + Enter Host
   Mode) and confirm the TNC responds.
2. Disconnect, then immediately reconnect (same session, no app
   restart, no power-cycle).
3. **Expected:** the reconnect succeeds — TNC reaches verbose mode
   (or Host Mode, if that path was chosen) — with no "No PK-232
   responding" error, and no misleading "TNC responds in Host Mode"
   status message when the TNC was in fact still in verbose mode the
   whole time.
4. Repeat starting from Host Mode (Connect + Enter Host Mode, then
   disconnect and reconnect) — same expectation.

**Unit-verified:** `test_serial_manager.py::TestReadUntilPrompt` (4
cases, `_read_until_prompt()` in isolation with the real byte sequences
from the 25.09.2026 capture — a chunked `cmd:` response is still found,
a missing one exhausts the full timeout, a pause after partial data does
not shrink the timeout budget, and the stricter predicate-marker form
used by `write_verbose_wait()` rejects an echoed "cmd:" substring with
no newline in front of it); `TestStep3EchoDetection` (2 cases — a
byte-identical 5-byte echo of the HPOLL query is not mistaken for Host
Mode and the chain correctly falls through to step 3b instead of
aborting at step 4; a genuine 6-byte answer with a value byte is still
detected as Host Mode); `TestWriteVerboseWaitTiming` (2 cases —
`write_verbose_wait()` against a real `_ReaderThread` finds a `cmd:`
delayed ~400ms within its timeout, and correctly times out when no
answer ever comes); `TestParamsUploaderVerifyEcho` (2 cases — `verify()`'s
no-answer and mismatch cases reach the verbose terminal, not just the
log). Both fixes cross-checked red-without-the-fix during implementation
(manually reverting each one in turn made its own new test fail, then
restored).

**Status:** ✅ PASS (2026-09-25, unit-verified — full suite green,
39/39 in `test_serial_manager.py`; hardware-confirmed 2026-09-25/26,
Device B — disconnect/reconnect succeeded in every state tried,
including after Host Mode and after killing the app, with no false
"No PK-232 responding" error).

---

### T134 — Disconnect from Host Mode with Baudot active; converse-mode resync and a correctly-read verification (P53)

A console capture and screenshot (26.09.2026, 13:13–13:16) showed two
independent findings from one operator session. (1) `ParamsUploader.
verify()` reported "no answer verifying MYCALL" even though the verbose
terminal showed the TNC's correct reply to the identical query in the
same session — traced to a real, 20/20-reproducible race between
`query_verbose_value()`/`detect_maildrop()`'s own transient
`raw_data_received.connect()`/`disconnect()` pair and Qt's queued
cross-thread delivery (not, as first suspected, a second reader
competing for the port — code audit found none). (2) A reconnect after
disconnecting from Host Mode with Baudot RTTY active failed: `*` and a
bare `CR` both got only an echo, never `cmd:` — the TNC was in Baudot's
Converse state (`HOST OFF` returns to the last-active operating mode,
not the command prompt), which the old chain could not tell apart from
a dead TNC.

**Live sequence to run:**
1. Connect, select Baudot RTTY, enter Host Mode.
2. Disconnect (or leave Host Mode via the TNC menu).
3. **Expected (Finding 2's fix, in `exit_host_mode()` itself):** the
   verbose terminal is immediately usable — typing produces a `cmd:`
   response, not just an echo of what was typed. Check the log for
   `Host Mode exit: COMMAND char resync ...`.
4. Reconnect (same session, no app restart).
5. **Expected:** reconnect succeeds via step 1 or 2 of the detection
   chain (step 2b should not even be needed, since step 3 above already
   left the TNC at the prompt) — no "No PK-232 responding" error.
6. Repeat steps 1-2, but kill the app (or physically power-cycle the
   TNC) between leaving Host Mode and reconnecting, so `exit_host_mode()`
   never gets to run its own resync. Reconnect.
7. **Expected:** the detection chain's own step 2b catches this instead
   — log shows `Init: step 2b - COMMAND char (Ctrl-C) - TNC may be in
   converse mode` followed by `step 2b confirmed verbose`. Reconnect
   still succeeds, no error dialog.
8. Upload parameters (Fast Init off) and check the verbose terminal.
9. **Expected:** `[SYS] parameter upload verified (3/3)` appears in the
   verbose terminal itself (not only the Monitor panel/log) — matching
   whatever the terminal already showed for the MYCALL/PACLEN/MAXFRAME
   spot-check queries just above it.

**Unit-verified:** `test_serial_manager.py::TestVerboseQueryReadPath`
(3 cases — the old transient connect/disconnect pattern reproducibly
loses the signal with a real, actively-pumping `QCoreApplication`;
`query_verbose_value()`/`detect_maildrop()` no longer depend on it at
all, proven by calling each from a background thread with no event-loop
pumping whatsoever); `TestConverseModeDetection` (4 cases — step 2b
confirms verbose mode using the real byte sequences from the
26.09.2026 capture, with no HPOLL frame sent at all; a non-default
configured COMMAND character is used instead of `$03`; `verify()`
reaches the TNC's answer end-to-end for a full 3/3; `exit_host_mode()`
sends the COMMAND-char resync and logs the result). Both P53 fixes
cross-checked red-without-the-fix during implementation (reverting
`query_verbose_value()` to the old signal pattern, and disabling step
2b, each made its own new test fail, then restored).

**Status:** ✅ PASS (2026-09-26, unit-verified — full suite green,
632 passed; hardware-confirmed 2026-09-25/26, Device B — connection
succeeded after Host Mode, after a plain disconnect, and after killing
the app (steps 1-7), and `[SYS] parameter upload verified (3/3)`
appeared in the verbose terminal as expected (steps 8-9)).

---

### T135 — Connect, Host Mode, back to verbose, disconnect, reconnect — no error (P54)

A console capture (26.09.2026, 15:25–15:27) and a counter-test with
PuTTY showed the app failing to reconnect on a TNC that PuTTY reached
with a single Enter, no flow control, on the same port/baud — the
difference was the app's own port configuration (`connect_port()`
cleared DTR/RTS; PuTTY leaves them asserted), not the TNC. Fixed by
asserting DTR/RTS explicitly, logging every port parameter at each
stage of the connection's lifetime, and adding a defense-in-depth XON
stage (step 2c) for the PK-232's own software flow control (confirmed
by its boot banner).

**Live sequence to run:**
1. Connect (Connect + Enter Terminal Mode).
2. Enter Host Mode (Ctrl+H).
3. Leave Host Mode (back to the verbose terminal).
4. Disconnect (`Ctrl+D`).
5. Reconnect (`Ctrl+T`).
6. **Expected:** the reconnect succeeds with no error dialog and no "No
   PK-232 responding" message — step 1 or 2 of the detection chain
   should suffice (steps 2b/2c should not even be needed, since the
   TNC is left at its own `cmd:` prompt by steps 2-4 above).
7. Capture the console log for the whole sequence.
8. **Expected:** the log shows `Port config on open: ...` and
   `Port config after reset: ...` lines with `dtr=True`/`rts=True` for
   the reconnect in step 5, and a `Port config at close: ...` line for
   the disconnect in step 4 — this is the actual measurement the spec
   asks for, not just "it worked".

**Unit-verified:** `test_serial_manager.py::TestXonFlowControlDetection`
(3 cases — step 2c releases a TNC stopped by software flow control
using the real byte pattern from the capture, with no HPOLL frame sent
at all; the second-CR retry specifically closes the case the first
XON+CR attempt does not; a fully silent TNC still reaches step 4, XON
having been tried along the way); `TestPortConfiguration` (3 cases —
`connect_port()` asserts DTR/RTS and resets both buffers; the "on
open"/"after reset" log lines name every field the spec asks for;
`disconnect_port()` logs the end-of-life configuration). Cross-checked
red-without-the-fix during implementation (disabling step 2c's own
success conditions made both of its new tests fail, then restored).

**Status:** ✅ PASS (2026-09-26, unit-verified — full suite green;
hardware-confirmed 2026-09-25/26, Device B, for the connection sequence
itself — steps 1-6 succeeded with no error dialog, matching the same
"connects in every state tried" finding recorded under T133/T134).
Steps 7-8 (a console capture specifically confirming the new
`Port config on open/after reset/at close` log lines) still open.

---

### T136 — Sync beim Verlassen (`on_session_end`, P59)

`SerialManager.fresh_boot_defaults` (an EVENT flag, reset every init/
recovery run, unlike the sticky `tnc_defaults`) and
`MailDropDialog._end_session()` (the one path out of an ACTIVE
session, P59 C.2) are unit-verified against a fake session
(`test_serial_manager.py::TestFreshBootDefaults`,
`test_maildrop_dialog.py::TestEndSessionSync`). Not yet run against
real hardware.

1. Archive on, `archive_sync = on_session_end`.
2. Open a MailDrop session, write two messages, `End session`.
3. **Expected:** status line "Collecting 2 message(s)...", then a
   normal return to Host Mode; both messages show as `TNC + archive`
   in the next dialog open.
4. **Measure:** the duration of each `read` from the log timestamps —
   closes the B.6 gap (P59 spec) that "message read (Sync) duration"
   was never measured.

**Status:** ⬜ OPEN (Device B).

---

### T137 — Restore nach dem Einschalten (`ask`, P59; re-entry steps P60)

`MainWindow._check_archive_restore_trigger()`/`_update_maildrop_gate_ui()`
(D.1/D.2) and `MailDropDialog(..., auto_restore=True)` (C.4) are
unit-verified against a fake session/stub serial
(`test_main_window_packet.py::TestArchiveRestoreTrigger`,
`test_maildrop_dialog.py::TestAutoRestore`). The re-entry regression
(steps 3a/3b below) and the auto-restore failure path are also
unit-verified
(`test_serial_manager.py::TestConsumeFreshBootDefaults`,
`test_main_window_packet.py::TestArchiveRestoreTrigger::
test_second_host_mode_changed_in_same_power_cycle_does_not_rearm` /
`test_auto_restore_dialog_opens_exactly_once_even_if_its_own_exec_refires_host_mode_changed`,
`test_maildrop_dialog.py::TestRestoreFailurePath`). Not yet run against
real hardware.

**Precondition:** run this test with `archive_restore = ask` first.
Only move on to `auto` once steps 3a/3b have PASSED with `ask` — before
P60, `auto` looped MailDrop sessions endlessly on real hardware (see
`docs/P60_Archive_Restore_Oneshot_Fix_Spec.md`, B.1).

1. Archive with >= 2 messages (from T136), `archive_restore = ask`,
   scope `all`.
2. Power-cycle the TNC, connect the application, select HF Packet.
3. **Expected:** exactly one confirmation naming the count and a time
   estimate; after Yes the dialog runs on its own, closes itself,
   packet operation resumes; the messages show as `TNC + archive` in
   the next manual dialog open.
3a. After the successful restore, open the MailDrop session
    **manually** and end it again. **Expected:** no renewed
    confirmation, no renewed restore (P60).
3b. TNC menu → Leave Host Mode, then Enter Host Mode. **Expected:**
    likewise no confirmation (P60).
4. **Counter-check:** disconnect and reconnect the application
   **without** power-cycling the TNC → **no** confirmation.
5. **Measure:** actual duration against the estimate
   (`n * 7 + 7` seconds, P38/T119 measurement).

Device A and C: explicitly out of scope for this package; findings do
not transfer (`docs/DEVICES.md`).

**Status:** ⬜ OPEN (Device B).

---

### T138 — APRS query: UNPROTO/VIA and `UN`/`CF` in Host Mode (P62)

`tools/hw_check.py aprs_query` — query-only, no transmission at all.
Measures what P63 (the future APRS mode) needs to know and does not:
whether a VIA digipeater path survives a verbose UNPROTO set/query
round-trip, whether the SAME path can be set via the Host Mode `UN`
frame (`HostModeProtocol.cmd_unproto()`, existing, never called from
production code before this), whether `UN` can be read back in Host
Mode at all, and how `CF NONE`/`CF ALL` (`HostModeProtocol.
build_command(b"CF", ...)`) round-trip through `CFROM`. See
`docs/P62_APRS_Measure_Spec.md`, Teil A, for the exact step list
(A.1–A.6).

Run: `python tools/hw_check.py --port COMx aprs_query`

| Device | Result |
|---|---|
| A | ⬜ OPEN |
| B | ✅ 27.09.2026 — see below (A.6 measurement invalid, see P62a) |
| C | ⬜ OPEN (optional — see Teil E) |

**Device B, 27.09.2026** — `device: unknown (no banner - TNC was
already awake)`; the device attribution itself is the operator's own
statement, not read from the log's own `device:` line (P37's own rule:
believe the `device:` line, never guess — there was none here, so this
is flagged as operator-supplied, not measured):

| Step | Result | Finding |
|---|---|---|
| A.2 | PASS | `UNPROTO APZ232 VIA WIDE1-1,WIDE2-1` accepted verbose |
| A.3 | PASS | same path set via the Host Mode `UN` frame, confirmed verbose |
| A.4 | INFO | Host Mode query of `UN` returns `UNAPZ232 via WIDE1-1, WIDE2-1` — **lowercase `via`, a space after the comma** (the TNC reformats the path on readback) |
| A.5 | PASS | `CF NONE`/`CF ALL` in Host Mode both effective |
| A.6 | **not evaluable** | after the 9-digipeater attempt, the query showed the PREVIOUS step's 8 digis — truncated vs. rejected cannot be told apart this way; a measurement defect in the P62 spec itself, fixed in P62a Teil B.1 (set UNPROTO to `CQ` first, log the SET response too) |

**Status:** ✅ (Device B) / ⬜ OPEN (A, C).

---

### T139 — APRS TX: five UI rounds (P62)

`tools/hw_check.py aprs_tx` — **TRANSMITS ON THE AIR.** Needs a second
receiver with an AX.25 decoder (Direwolf or similar) and, per the
tool's own printed warning, a simplex frequency with no APRS
infrastructure (WIDEn-N paths are repeated by real digipeaters and
gated to APRS-IS) — low power or a dummy load. Five rounds: plain UI
frame (R1, repeats T101 per device), a VIA digipeater path (R2), a
full-printable-ASCII-charset probe (R3 — also answers whether the TNC
appends a CR to the info field), a 200-character length probe (R4 —
does an over-PACLEN info field split into more than one UI frame?),
and one round with `CFROM NONE` active (R5). See
`docs/P62_APRS_Measure_Spec.md`, Teil B, for the exact info-field text
of each round.

Run: `python tools/hw_check.py --port COMx aprs_tx`

| Device | R1 | R2 | R3 | R4 | R5 |
|---|---|---|---|---|---|
| A | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| B | ✅ PASS | ✅ PASS | ⬜ invalid (see below) | ✅ finding (see below) | ⬜ skipped (see below) |

**Device B, 27.09.2026, `PACLEN 64`:**

- **R1:** PASS — destination `APZ232`, info field exact, **no CR
  appended** by the TNC.
- **R2:** PASS — path `WIDE1-1,WIDE2-1` exact, H-bits unset (Direwolf
  shown with no `*`).
- **R3:** **invalid run** — the charset probe is 106 characters,
  longer than this device's `PACLEN 64`, so it went out as 2 frames;
  the pasted decoder text was accidentally R2's lines, not R3's.
  Character-exactness is still **unmeasured**. Fixed in P62a C.2
  (R3 sets `PACLEN 128` itself, restored afterwards, so it always fits
  in one frame regardless of the device's own configured value).
- **R4:** **finding** — 204 characters produced **4 UI frames: 64 + 64
  + 64 + 12 bytes**, split exactly at PACLEN. Confirmed by the pasted
  Direwolf lines (the continuation frames start `6789…`, `0123…`,
  `45678901 END`; Direwolf itself: "Unknown APRS Data Type Indicator"
  for the continuation frames, since they no longer start with a valid
  APRS data type character). **This is the key finding for P63:** data
  sent on channel 0 is split into UI frames of at most PACLEN bytes
  each; one APRS message needs exactly one frame, so the APRS mode
  must own PACLEN (query and set it) the same way it owns UNPROTO.
- **R5:** skipped — the rest of the R4 paste overran into the frame-
  count question and then the R5 confirmation prompt (P62a Teil A
  fixes the paste-input termination this exposed).

Side finding (Direwolf, not a TNC finding): `>PK232PY …` is
misinterpreted as a status report with an embedded Maidenhead locator
(`PK23` + overlay `2` + symbol `P`), hence "Found 'Y' instead of
space". Noted for P63: an info field whose first four characters are
two letters then two digits gets misread this way by Direwolf; P62a
C.4 changes the affected rounds' prefix to `>Test PK232PY …`.

**Status:** ✅ partial (Device B: R1/R2 PASS, R3 invalid, R4 a real
finding, R5 skipped) / ⬜ OPEN (Device A; Device B re-run of R3/R5 plus
the new R6, P62a).

---

### T140 — APRS reject: incoming connect under `CFROM NONE` (P62)

`tools/hw_check.py aprs_reject` — no transmission of this tool's own; a
**second station of the operator's choosing** calls this TNC's MYCALL
first with `CFROM ALL` (C.1, baseline, 60s capture) and then with
`CFROM NONE` (C.2, 90s capture). Records every Host Mode frame
verbatim in both phases and asks the operator what the CALLING station
saw and whether this TNC's own PTT/SEND LED lit up — INFO only, no
PASS/FAIL (the question is what `CFROM NONE` actually does from both
sides, not a predicted answer). See `docs/P62_APRS_Measure_Spec.md`,
Teil C.

Run: `python tools/hw_check.py --port COMx aprs_reject` (needs a second
station/device — record which one in the log, the tool asks).

| Device | Second station | C.1 (`CFROM ALL`) | C.2 (`CFROM NONE`) |
|---|---|---|---|
| A | | ⬜ | ⬜ |
| B | | ⬜ | ⬜ |

**Status:** ⬜ OPEN.

---

### T141 — Link carry: verbose connect survives Host Mode, CO and OP queries (P65)

`tools/hw_check.py link_carry` — connects to a real counterpart from the
tool's own verbose `CONNECT` prompt, takes a verbose baseline
(`OPMODE`/`CSTATUS`/`CONNECT`), enters Host Mode and records 3s of
unsolicited traffic, queries `OPMODE` (Host Mode `OP`) and TRM 4.3.3
link status on every channel 0–9 (`HostModeProtocol.cmd_link_status()`,
never called by production code), sends a single `\r` data frame on
whichever channel looks connected, re-sends `VHFPacketMode`'s own
`get_activate_frames()`/`get_init_frames()` and re-checks link status,
leaves Host Mode and re-checks the verbose baseline, then offers to
disconnect. See `docs/P65_Link_Carryover_Measure_Spec.md`, Teil A.
Follows on from the P64 Backlog observation (Betreiber, 27.09.2026):
BBS connection survived an `Enter Host Mode` round trip in the app
itself, unconfirmed whether the operating mode did too.

Run: `python tools/hw_check.py --port COMx link_carry` (needs a real
counterpart station — a BBS, or Direwolf/QtTermTCP over AGW as in
T140 — record which one in the log, the tool asks).

| Device | Counterpart | A.6 (link status) | A.8 (survives mode-switch frames) | A.9 (verbose sees it again) |
|---|---|---|---|---|
| A | | ⬜ | ⬜ | ⬜ |
| B | TinyBox BBS | ✅ PASS (14:57) | ✅ PASS (14:57) | ✅ PASS (14:57) |

**Device B, 28.09.2026 09:40 (`20260928_094001_link_carry.log`) — run
marked INVALID, not FAIL:** after the verbose `CONNECT`, the TNC was in
Converse, not the command prompt — `enter_host_mode()`'s old handshake
(pre-P66) mistook Converse's own echo of `HOST 3`/`HPOLL Y` for a real
Host Mode entry, so A.4 onward ran against a TNC that was never
actually in Host Mode at all (see `docs/P66_HostMode_Entry_From_
Converse_Spec.md`, B.1/B.2).

**Re-run, 28.09.2026 13:35 (after P66's own fix, before P66b) — real
FAIL, and a new finding (`docs/P66b_HostEntry_Lag_And_IO_Channel_Spec
.md`, B.1):** A.3 now works (Ctrl-C → `cmd:`; `OPMODE` → `PAcket`;
`CSTATUS` → `Ch. 0 - IO CONNECTED to OE3GAS-1; v2`), but the handshake
itself still reported failure — and then went into Host Mode ANYWAY, a
few seconds later: the delayed response to the EARLIER `XFLOW OFF`
arrived only after the `HPOLL_Y` echo had already been read (the
command interpreter lagging seconds behind the immediate character
echo while a connection is active), and `HOST 3` then ran once the
interpreter caught up — after the handshake's own OPMODE check had
already given up. P66b's retried OPMODE check (up to 3 attempts, 1.5s
apart) is meant to catch exactly this; the same-session T143 app test
(Ctrl+H, same starting state) succeeded, confirming the behaviour is
TIME-DEPENDENT, not a hard failure. **Re-run needed after P66b, three
times**, to see whether the retry actually catches the late entry and
how much the timing varies run to run.

**Re-run, 28.09.2026 14:57 (P67 basis run,
`docs/P67_Link_Table_Packet_Spec.md`, M1) — PASS:** Host Mode
entry from Converse with the connection already up succeeds cleanly —
`HP $00`, `OPPA`, no late-entry lag this time (P66b's own retry logic
never needed to fire). A.6 confirmed the connection on channel 0
(`CO41000OE3GAS-1`); A.7/A.8 (data frame, VHF mode-switch frames while
connected) both PASS, matching M4/M5.

**Same session, 14:59/15:00 — limited validity, tool bug (H.1, fixed
P67 Teil D):** A.10's own verbose `DISCONNECT` disconnected the
active/IO channel (9, left there by A.6/A.8's own 0–9 probe loop), not
the actually-connected channel 0 — so runs 2 and 3 both got
`?already connected` back on their own A.2 CONNECT attempt instead of
testing a fresh Converse-connect at all. Only the 14:57 run is a real
Converse-carry measurement; 14:59/15:00 tested "connect to an already-
connected station" by accident, not Converse. Fixed in `tools/
hw_check.py`: A.10 now disconnects via Host Mode `DI` on the connected
channel from the last `CO` query (like `link_carry_host`'s own
cleanup), and A.2 now FAILs fast on `?already connected` instead of
continuing into a run that measures the wrong thing.

**Status:** ✅ PASS (Device B, 14:57 run) for Host-Mode-entry-from-
Converse with an existing connection. 14:59/15:00 INVALID (tool bug,
H.1) — no longer possible to repeat now that the fix is in place,
since A.10 correctly cleans up after itself. Still unmeasured on A/C.

---

### T142 — Link carry (Host → verbose): Host Mode connect seen from verbose (P65)

`tools/hw_check.py link_carry_host` — mirror of T141: connects **in Host
Mode** on channel 1 via `HostModeProtocol.cmd_connect()` (the same call
production code makes), waits for the `$5x` `CONNECTED to` link
message, checks `OPMODE`/link status there, leaves Host Mode and
queries verbose `OPMODE`/`CSTATUS`/`CONNECT` to see whether — and on
which channel — the connection is visible from that side, then
re-enters Host Mode to confirm it is still on channel 1 before
cleaning up with a Host Mode `DI`. See
`docs/P65_Link_Carryover_Measure_Spec.md`, Teil B.

Run: `python tools/hw_check.py --port COMx link_carry_host` (needs a
real counterpart station).

| Device | Counterpart | Connect seen (Host) | Verbose shows same channel | Still ch1 after re-entry |
|---|---|---|---|---|
| A | | ⬜ | ⬜ | ⬜ |
| B | TinyBox BBS | ✅ PASS | ✅ PASS | ✅ PASS |

**Device B, 28.09.2026 (`20260928_094231_link_carry_host.log`) — PASS.**
Connecting IN Host Mode and querying `OP`/`CO` there both work exactly
as TRM 4.3.2/4.3.3 document (`OP` → `OPPA`; `CO` on the connected
channel → `CO41000OE3GAS-1`, a free channel → `CO00000` — see
`docs/P66_HostMode_Entry_From_Converse_Spec.md`, B.3, for the byte
layout `decode_link_status()` now decodes). Leaving Host Mode via
`exit_host_mode()` (which sends the COMMAND character itself, P53.B)
and querying verbose `CSTATUS` shows the same connection; re-entering
Host Mode confirms it is still on channel 1 — **a connection survives
the switch in both directions, provided the TNC is in the command
mode (not Converse) at the moment of the switch.** This settles
`CLAUDE.md`'s pre-P66 "no CSTATUS poll in Host Mode" claim as
superseded for Device B — TRM 4.3.3's Link Status query works.
**B.4 (open, then confirmed):** the same run's `CSTATUS` after leaving
Host Mode showed the ACTIVE channel as 9, not the connected channel 1
— the last channel a `$4x` frame had been sent to.

**Re-runs, 28.09.2026 13:38 and 13:40 (P66's own D.1/D.2 additions;
`docs/P66b_HostEntry_Lag_And_IO_Channel_Spec.md`) — PASS, B.4/B.3
CONFIRMED:** both runs sent `CO` on channel 3 as the last `$4x` frame
before `HOST OFF`; verbose `CSTATUS` showed `Ch. 3 - IO` both times
(without the D.1 probe, the earlier run's own last `CO` had been
channel 9, and `CSTATUS` called THAT channel IO) — **the active
verbose channel after `HOST OFF` is the channel of the last `$4x`
frame sent, confirmed for Device B.** Also found: `CHSWITCH` reads
`$00` on Device B (no channel-switch character set, B.4 of P66b) —
`CONVERSE` on the free probe channel (3) sent nothing but got echoed,
no prompt, no error (B.5) — the TNC transmits UNPROTO UI frames there
per TRM, so D.2.1 needed `confirm_tx()` (added, P66b). D.2.3 (the
CHSWITCH channel-switch attempt) is **INVALID for this run** — it ran
before P66a's fix and sent the literal text `$001CONVERSE` instead of
a real channel-switch command, so it never tested anything real;
CHSWITCH being `$00` on this device means D.2.3 has nothing to test
here regardless (P66a's own `chswitch_byte()` now correctly returns
`None` for `$00`). Cleanup disconnected the WRONG channel (3, the
active one) — the real connection on channel 1 stayed up until the
counterpart's own timeout (B.6, fixed by P66b: cleanup now uses the
connected channel from the last CO recheck, via a Host Mode `DI`, not
a verbose `DISCONNECT` on the active channel).

**Re-run, 28.09.2026 15:02 (P67 basis run,
`docs/P67_Link_Table_Packet_Spec.md`, M6/M7) — D.1/D.3 PASS,
Connect portion INVALID (pre-existing connection from the T141 14:57
run, never cleaned up before this run started):** this run's own B
step ("Connect to target, from Host Mode") got `?already connected`
back instead of a fresh `CONNECTED to` link message — the counterpart
was still connected from T141's own 14:57 session, so B/B-recheck's
own PASS/INCONCLUSIVE verdicts are not meaningful here (same tool bug
as T141's H.1/H.2, fixed P67 Teil D — B now decodes a CO-shaped error
response explicitly instead of reporting "inconclusive", and A.9/B's
own verbose check now uses `parse_cstatus()` for the connected channel
instead of a bare `CONNECT` query). D.1 and D.3 do NOT depend on the
Connect step's own verdict, only on there BEING a connection somewhere
— confirmed PASS: D.1 (last `CO` on a free probe channel becomes the
active/IO channel afterward) and D.3 (`CO` on the CONNECTED channel as
the last `$4x` frame makes verbose `CSTATUS` show `IO` there, and
`CONVERSE` on it gets the counterpart's own prompt back) both matched
B.3/B.4/M7 again, on the pre-existing connection. D.3's own `CONVERSE`
response needed the widened 10s idle window (H.4, fixed P67 Teil D) —
the 2s window used until now would have missed the TinyBox's reply.

**Status:** ✅ PASS (Device B) for the base connect/survive/re-entry
measurement (13:38/13:40 runs), B.3/B.4 (active channel follows the
last `$4x` frame), and now D.3 (15:02 run, CO-then-CONVERSE technique
confirmed end to end). D.2.3 invalid for this device (CHSWITCH `$00`).
Still open on A/C.

---

### T143 — Ctrl+H after a verbose connect actually enters Host Mode (P66)

The original P64 case, in the application itself, not `hw_check.py`:
verbose, VHF Packet, connect to a BBS, then `TNC → Enter Host Mode`
(Ctrl+H). Expected, after P66's fix: the handshake escapes Converse
(the state a verbose `CONNECT` can leave the TNC in, B.1) and Host
Mode is genuinely entered — confirmed by a real OPMODE answer, not an
echo. The connection ITSELF should carry over (T142 confirms the
protocol allows this on Device B), but the app's own connection-table
display is **not** expected to show it yet — that is P67's job, built
on this package's findings, not this one's.

| Device | Entry | Connection preserved | Connection display |
|---|---|---|---|
| A | ⬜ OPEN | ⬜ OPEN | ⬜ OPEN |
| B | ✅ PASS | ✅ PASS | ⬜ OPEN (P67) |

**Device B, 28.09.2026 (same session as T141 13:35/T142 13:38-13:40;
`docs/P66b_HostEntry_Lag_And_IO_Channel_Spec.md`, B.7) — Entry and
connection preservation PASS:** after Ctrl+H (same starting state as
T141: verbose, VHF Packet, connected to the BBS), the VHF Packet mask
appeared with **no** connection display, even though the TNC was
genuinely connected — after `Leave Host Mode`, verbose `CSTATUS`
still showed channel 0 `CONNECTED to OE3GAS-1`, confirming Host Mode
was genuinely entered (not the T141-shaped false entry) and the
connection itself survived the whole round trip. **Connection
display is still open — expected, that is P67's job**, not this
package's.

**Status:** ✅ PASS (Device B) for entry and connection preservation.
Display: OPEN, tracked as P67. Still unmeasured on A/C.

---

### T144 — LinkTable carry-over end to end, in the application (P67)

Closes T143's own "Display: OPEN (P67)" — the same starting state, now
checking the connection DISPLAY, not just that Host Mode was genuinely
entered. App-level, Device B, needs a real counterpart (TinyBox BBS or
equivalent).

Steps (`docs/P67_Link_Table_Packet_Spec.md`, Teil F):
1. Verbose, VHF Packet, `CONNECT OE3GAS-1`, wait for the counterpart's
   own prompt.
2. Ctrl+H → **expected:** VHF Packet mask, chip 0 dashed
   (`unconfirmed`) at first, then "connected OE3GAS-1" once the CO
   reconciliation round answers; typing `H` into channel 0's TX
   window reaches the counterpart and its own help text comes back.
3. Leave Host Mode → **expected:** verbose terminal, typing `H` gets
   an answer from the counterpart directly (Converse on channel 0,
   no extra step needed).
4. Ctrl+H again → chip 0 shows connected again; "Disconnect" in the
   chip's context menu → chip goes free.
5. Counter-check: with no connection at all, Ctrl+H then Leave Host
   Mode → verbose stays at the command prompt (`cmd:`), and **no**
   `CONVERSE` is sent (the free-channel case — P66b B.5 — must never
   fire here).
6. Re-run `link_carry` once, after the Teil D fixes (H.1–H.4) — a
   genuine Converse-carry measurement with clean cleanup, not another
   "already connected" false start.

| Device | Step 2 (chip shows connected) | Step 3 (Converse without extra step) | Step 4 (re-entry + disconnect) | Step 5 (no CONVERSE on free channel) | Step 6 (clean link_carry re-run) |
|---|---|---|---|---|---|
| A | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| B | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |

**Status:** ⬜ OPEN — needs a real hardware session on Device B; the
unit-level equivalent of steps 2/4/5 (mode-name/CO-probe/no-reset-on-
exit/write-order/CONVERSE-only-if-was-converse) is covered by
`test_main_window_packet.py::TestLinkTableHostModeCarryOver`
(software-verified, P67 Teil E).

---

### T145 — Enter Host Mode enabled again after Leave Host Mode (P68)

Closes T144's own side observation (2026-09-29, Device B): after
`TNC -> Leave Host Mode` the `Enter Host Mode` action (Ctrl+H) stayed
greyed out until a reconnect. App-level, Device B.

Steps (`docs/P68_Enter_Host_Mode_After_Exit_Spec.md`):
1. Connect verbose, Ctrl+H (Host Mode entered).
2. `TNC -> Leave Host Mode` → **expected:** verbose terminal usable.
3. Ctrl+H again, **without** reconnecting → **expected:** the menu
   entry is enabled and the second entry into Host Mode succeeds.

| Device | Step 3 (second entry without reconnect) |
|---|---|
| B | ✅ |

**Status:** ✅ PASS (Device B, reported by the operator 2026-09-29);
also software-verified by `test_serial_manager.py::TestExitHostModeVerboseResumed` and
`test_main_window_connection.py::TestEnterHostModeEnabledAfterLeaving`.

---

### T146 — `channel_probe` B: Unproto on free channels (P69)

`python tools/hw_check.py --port COM6 channel_probe --part B` (P69a: 4 steps, one decoder paste at the end). Device B,
VHF 1200 Bd, Direwolf on the FT-818 decoding ALL frames, TinyBox
(`OE3GAS-1`) as counterpart. UNPROTO `P69TST`.

| Step | Question | Expected / measured |
|---|---|---|
| B.1 | Data on free channel 3 (`$23`), all channels free → UI frame? | ✅ PASS — UI frame |
| B.2 | Data on free channel 9 (`$29`), all channels free → UI frame? | ✅ PASS — UI frame |
| B.3 | Same on ch3 while ch0 is connected to the TinyBox; CR on `$20` teaches Direwolf's I-frame notation | ✅ PASS — UI frame; ch0 connection kept running (`\r` → prompt on `$30`) |

**Status:** ✅ PASS (Device B, Release 01.AUG.91, 30.09.2026, log
`20260930_210627_channel_probe.log`). Findings F1/F2 in
`docs/claude/GOTCHAS_PACKET.md`.

---

### T147 — `channel_probe` C: channel of an incoming connect (P69)

`python tools/hw_check.py --port COM6 channel_probe --part C` (P69a: 11 steps).
QtTermTCP (`OE3GAS-2`, `OE3GAS-3`) calls the PK-232's MYCALL; recording runs
from before the instruction until ENTER on PC 1 (max 120 s). `USERS` is logged first.

| Phase | Question | incoming_channel / accepted |
|---|---|---|
| C.1 | All free, USERS as found (1): which channel? | ℹ️ channel 0 (`$50 CONNECTED to OE3GAS-2`) |
| C.2 | ch0 occupied, second caller (`OE3GAS-3`): accepted? channel? QtTermTCP shows? | ℹ️ rejected (`DM` on the air); host got `$50 "Connect request: OE3GAS-3"` |
| C.3 | Same as C.1/C.2 with `USERS 10` | ℹ️ first caller channel 0, second caller channel 1 |

**Status:** ℹ️ INFO (measurement, no pass/fail) — Device B, 30.09.2026, log
`20260930_212141_channel_probe.log`. F3/F4 feed P70 (channel bar MON · 0–9).

---

### T148 — Channel bar MON · 0–9 in the application (P70)

Device B, App in Host Mode, VHF Packet. Two PCs: PC 1 = app + PK-232,
PC 2 = Direwolf, QtTermTCP (`OE3GAS-2`, `OE3GAS-3`), TinyBox `OE3GAS-1`.
USERS 10 (new default) unless step 3b.

| Step | Where | Action | Expected | Result |
|---|---|---|---|---|
| 1 | PC 2 | QtTermTCP `OE3GAS-2` calls `OE3GAS` | chip 0 connected, partner OE3GAS-2 | ⬜ |
| 2 | PC 1 | MON chip, send an unproto text | MON shows `[via ch1]`; PC 2 Direwolf shows a UI frame | ⬜ |
| 3 | PC 2 | QtTermTCP `OE3GAS-3` calls | chip 1 connected, partner OE3GAS-3; chip 0 still OE3GAS-2 | ⬜ |
| 3b | both | optional: USERS 1 in the parameters, upload again, disconnect both, call with OE3GAS-2 then OE3GAS-3 | "Incoming call from OE3GAS-3 rejected by the TNC (USERS 1)"; afterwards USERS back to 10 | ⬜ |
| 4 | PC 1 | chip 0 → Disconnect | briefly "disconnecting", then free | ⬜ |
| 5 | PC 1 | verbose, `CONNECT OE3GAS-1`, Ctrl+H | chip 0 connected with OE3GAS-1 (the open point of T144 step 3) | ⬜ |

**Status:** ✅ PASS (device B, 03.10.2026, operator decision; steps not recorded
one by one, so no step is ticked). Observations:
- An incoming call lands on chip 0 (OE3XTC), an own connect on chip 1 (OE3GAS-1),
  as measured in T147.
- Unproto from MON goes out as a UI frame over a free channel; Direwolf on PC 2
  confirms destination and frame type.
- QtTermTCP showing the UI frame in the window of the connected session is
  QtTermTCP's own display, not a finding.
- The radio link with many retries (DCD) is the operator's to solve.

Software covered by `test_packet_screen.py`, `test_link_table.py`,
`test_main_window_packet.py`.

---

### T151 — `host_params_probe` A: ask and set parameters in Host Mode (P71)

`python tools/hw_check.py --port COM6 host_params_probe --part A` (PC 1
only, nothing transmitted). Device B. Pass 1 in Host Mode: query every row
of `comm/host_params.py` that has a mnemonic (all hypotheses from
`docs/PK232_firmware_matrix.md`), set a test value for `int`/`bool` rows
and BTEXT (`P71`), query again — raw answers logged. Callsigns and control
characters are only queried. Pass 2 in verbose mode: every set parameter is
asked by its verbose name; a mismatch is `wrong_param` (the mnemonic belongs
to another parameter - any parameter that changed by mistake is reported
as `COLLATERAL CHANGE` and restored). Verdicts: `verified`,
`set_ok_query_unparsed`, `query_only`, `rejected`, `no_answer`,
`wrong_param`, `unparsed`.

| What | Result |
|---|---|
| Answer format of a Host Mode query (value as ASCII?) | ⬜ |
| Answer to a set (ACK `$00`? error code?) | ⬜ |
| Verdict count per result; list of `wrong_param` rows | ⬜ |

**Result (01.10.2026, device B, release 01.AUG.91,
`hw_logs/20261001_185959_host_params_probe.log`):** Answer format, set ACK
and error codes measured (see `docs/claude/GOTCHAS_SERIAL_TNC.md`, "Host Mode
parameter answers on device B"). All 38 set parameters: query, set (`<mn>
$00`), query again behave. `$07` = unknown command (EX, PH, PB, PV), `$10` on
DA (meaning unmeasured). Pass 2 failed (see limitation) - the verdicts of the
run itself were all `unparsed`; the re-evaluation against the Pass 0 verbose
values (`--reevaluate`, P71a) gives `verified=17` (numbers: set, ACK, read back), `verified_query=16` (read-only match), `verified_weak=20`
(switches without Pass 2), `host_only=1` (ARQTOL), `rejected` 5.
`AO` = ARQTMO, not ARQTOL.

**Limitation (P71a B.4):** one of the Pass 1 test values switches the
verbose command interpreter off - every verbose query after Pass 1 gave
`?What?`, so Pass 2 verified nothing and nothing was restored. The TNC had
to be power-cycled. Parts A (restore in Host Mode) and C (T155) of P71a
address this.

**Status:** ✅ PASS with the limitation above. Feeds P72
(`verified_releases`). Software: `test_host_params_probe.py`.

---

### T155 — `host_params_probe` C: which parameter breaks the verbose commands (P71a)

`python tools/hw_check.py --port COM6 host_params_probe --part C` (PC 1 only,
nothing transmitted, never part of `all`). Groups of test values are set in
Host Mode (packet numbers, packet switches, RTTY/AMTOR/Morse, MailDrop
switches, `8BITCONV`+`XMITOK`), then verbose `PACLEN` and `USERS` are asked.
`?What?` = the group holds the trigger: restore in Host Mode, halve the
group, continue. Result: the single parameter (or a combination), plus the
verbose answer to `HELP` in that state. If the Host Mode restore fails the
program says to power-cycle the TNC.

| What | Result |
|---|---|
| Triggering parameter / combination | ⬜ |
| Verbose `HELP` answer in the broken state | ⬜ |

**Status:** ⬜ OPEN — hardware session on Device B. Software:
`test_host_params_probe.py` (`bisect_trigger`).

---

### T156 — `ubit_probe`: Host Mode form of `UBIT 0` (P74)

`python tools/hw_check.py --port COM6 ubit_probe` (PC 1 only, nothing
transmitted, never part of `all`; `--dry-run` shows the frames). Reads
verbose `UBIT 0` (if it is OFF it is set ON first, so a candidate proves
something), then in Host Mode tries `UB0 N`, `UB0N`, `UB0 OFF`, `UB0OFF`
(each followed by the query `UB0`, raw answers logged) until one answers
`$00`; checks it in verbose mode (`UBIT 0` must show OFF), sends VHF Packet's
own mode frames and asks again, then restores. Result line:
`host_form=..., query_answer=..., survives_mode_frames=...`. Devices: B
first, then A; C only after consulting the operator (first `hw_check`
contact).

| What | Result |
|---|---|
| Host Mode form (device B) | ✅ `host_form=0 N` (set `UB0 N` -> `UB $00`) |
| Query answer (raw) | ✅ `UBN` (`55 42 4e`) on device B |
| Survives mode frames | ✅ True on device B |
| Device A | ✅ `host_form=0 N` (set `UB0 N`, with a space), `query_answer=UBN` (`55 42 4e`), `survives_mode_frames=True` |

**Result, device A, 02.10.2026 16:28**
(`hw_logs/20261002_162823_ubit_probe.log`, `device: unknown (no banner)` - device A
per the operator): PASS. The original `UBIT 0 OFF` was restored.

**Result, device B, 02.10.2026 19:46**
(`hw_logs/20261002_194624_ubit_probe.log`, banner `release=01.AUG.91`): PASS -
`host_form=0 N`, `query_answer=b'UBN'`, verbose `UBIT 0` = OFF after the set and
after the VHF mode-switch frames (`survives_mode_frames=True`). Same form as
on device A. Device C: not measured.

**Status:** ✅ PASS (device A and B); device C ⬜ not measured. Software:
`test_ubit_probe.py`. Feeds `comm/host_params.py` (`UBIT` row, verified
releases `01.AUG.91`, `13.SEP.95`).

---

### T158 — `host_params_probe --part A --expert-off`: what does EXPERT OFF refuse? (P72)

`python tools/hw_check.py --port COM6 host_params_probe --part A --expert-off`
(PC 1 only, nothing transmitted). Device A (`13.SEP.95`, the init upload ends
with `EXPERT OFF` there). Pass 0 with EXPERT ON as before, then verbose
`EXPERT OFF` (read back), Host pass, verbose `EXPERT ON` for the cross-check,
restore as before. The log line `T158 rejected with EXPERT OFF: ...` lists the
parameters refused in the Host pass.

| What | Result |
|---|---|
| Parameters refused with EXPERT OFF on 13.SEP.95 | none - all 39 accepted; only DAYTIME answers `$10`, exactly as with EXPERT ON |

**Result (02.10.2026, device A, `hw_logs/20261002_192301_host_params_probe.log`):**
`T158 rejected with EXPERT OFF: DAYTIME ($10)`; `T151 summary ... verified=39`.
Two evaluation defects of that run (fixed afterwards, tests with the real
lines): the EXPERT row was judged `wrong_param` (the Host query says OFF by
design under `--expert-off`; now `expected_off`) and UBIT was judged
`wrong_param` (verbose `0 ON` vs Host `Y`; now asked as `UBIT 0` and `0 ON`
normalises to ON). `--reevaluate` of that log gives `expected_off=1`,
`verified=39`, `verified_query=18`, no `wrong_param`.

**Status:** ✅ PASS. ParamApplier stays unchanged. Software:
`test_host_params_probe.py` (`TestExpertOff`, `TestT158Evaluation`).

---

### T159 — App: bell on a new connect (P76)

Any device, VHF Packet; PC 1 runs PK232PY, PC 2 QtTermTCP (`OE3GAS-2`).
Software: `test_connect_bell.py`. The bell is `QApplication.beep()` - if the
Windows sound "Default Beep" is muted, nothing is heard (not an app setting).

| # | Where | Do | Expected | Result |
|---|---|---|---|---|
| 1 | PC 1 | Host Mode, VHF Packet, channel 1: connect `OE3GAS-1` (TinyBox) | one beep at "connected" | ⬜ |
| 2 | PC 2 | QtTermTCP `OE3GAS-2` calls `OE3GAS` | one beep | ⬜ |
| 3 | PC 1 | leave Host Mode, Ctrl+H | chips connected, NO beep (reconciliation) | ⬜ |
| 4 | PC 1 | Configure -> Appearance -> Connect bell off; connect again | NO beep | ⬜ |
| 5 | PC 1 | switch Connect bell on again | - | ⬜ |

**Status:** ✅ PASS (device B, 03.10.2026, operator observation; steps not recorded one by one).

---

### T163 — Appearance: RX and TX text colors (P77)

Visual check, any device or none (the verbose terminal needs a connection for
real TNC output). Software: `test_appearance_colors_p77.py`.

| # | Do | Expected | Result |
|---|---|---|---|
| 1 | Configure -> Appearance -> theme Air; open the Baudot window and type | TX input dark green on white, easy to read; verbose terminal: TNC output navy on white (no light grey) | ⬜ |
| 2 | Configure -> Appearance... (Font & Colors): change "TX text" | at once in the Baudot TX field and in the verbose terminal's input line; text already in the terminal is recoloured | ⬜ |
| 3 | Theme Dark | unchanged: RX light blue, TX gold, terminal on the dark background | ⬜ |
| 4 | Dialog: pick pale yellow for "TX text" on white | warning "Low contrast: TX text on background (x.x : 1)" under the preview; OK still works | ⬜ |
| 5 | Baudot: send a few characters (SEND) | sent characters inverse: background = TX colour, text = background colour; readable on Air and on Dark | ⬜ |
| 6 | (P77a) Theme Air, VHF Packet: receive a connection / monitor traffic | channel text in the RX colour, MON text and timestamps grey (dim), link messages (`*** CONNECTED ***`) dark amber - all readable on white | ⬜ |
| 7 | (P77a) Theme Air, verbose terminal: press Enter on an empty line while not connected | `[CR]` grey, `[ERROR] Not connected` dark red; the command row at the bottom is white with the "cmd:" prompt and typed text in the TX colour | ⬜ |
| 8 | (P77a) Baudot: Ctrl+D and Ctrl+T in the TX field | `[^D]` inverse on amber, `[^T:n]` inverse on grey; readable on Air and Dark | ⬜ |
| 9 | (P77a) Switch Air <-> Dark with text already in a Packet channel you are not looking at | its text follows the new colours when you switch to that channel | ⬜ |

| 10 | (P77b) Theme Retro: Configure -> Appearance... | the dialog looks like every other dialog (standard palette, readable), not orange on black | ⬜ |
| 11 | (P77b) In the dialog press a colour button (e.g. TX text) | the colour picker is readable (platform dialog, or Qt's own with the standard palette) - on Retro and on Air | ⬜ |
| 12 | (P77b) Dialog: Cascadia Mono SemiBold 14 pt, TX text `#00aa7f` on `#ffffff` | "3.0 : 1" next to the field, NOT red; font Courier New 11 pt: the same value in red | ⬜ |
| 13 | (P77b) Other settings dialogs (TNC configuration, Parameters) on Retro | standard look; the main window, RX/TX areas and terminal stay themed | ⬜ |

P77b (findings of the T163 visual check): dialogs keep the standard look
(`MainWindow._give_dialog_standard_look()`), the colour picker is the default
platform dialog, the contrast limit follows the font (3 : 1 large text, else
4.5 : 1). Software: `test_dialog_look_p77b.py`. Step 11 cannot be proven
offscreen - whether Windows shows its native picker is for the operator to see.

P77a (inventory from the P77 report) is covered in software by
`test_text_colors_p77a.py`: every text colour of every theme reaches 4.5 : 1
against its background (WCAG). Menu chrome, status bar and buttons are unchanged.

**Status:** ⬜ OPEN — visual check by the operator.

---

### T160 — `host_params_probe --part A --exclude IL`, device B: the Packet monitor flags (P73)

`python tools/hw_check.py --port COM6 host_params_probe --part A --exclude IL`
(PC 1 only, nothing transmitted). Device B, banner `release=01.AUG.91`. The new
rows ran automatically: MBELL `ME`, MDIGI `MD`, MPROTO `MQ`, MSTAMP `MS`,
PASSALL `PX`, BBSMSGS `BB`; FULLDP has no mnemonic.

| Row | verdict | Note |
|---|---|---|
| MBELL / MDIGI / MPROTO / MSTAMP / PASSALL / BBSMSGS | ✅ verified | query `<mn>N`, set `<mn> $00`, query `<mn>Y`, verbose `ON`, restored to `OFF` |
| FULLDP | ✅ unknown | verbose `FULLDP` answers `?What?` - the command does not exist on 01.AUG.91 |

**Result (03.10.2026 14:41, `hw_logs/20261003_144153_host_params_probe.log`):**
`T151 summary: no_mnemonic=12, rejected (0x07)=4, rejected (0x10)=1,
verified=43, verified_query=17`.

**Status:** ✅ PASS. The six flags are in `comm/host_params.py` for `01.AUG.91`;
FULLDP was removed from config, upload, host_params and the dialog.

---

### T161 — `host_params_probe --part A --exclude IL`, device A: the Packet monitor flags (P73)

Same as T160 on device A, banner `release=13.SEP.95` (PACTOR firmware).

| Row | verdict | Note |
|---|---|---|
| MBELL / MDIGI / MPROTO / MSTAMP / PASSALL / BBSMSGS | ✅ verified | same sequence as T160 |
| FULLDP | ✅ unknown | verbose `FULLDP` answers `?What?` - the command does not exist on 13.SEP.95 |

**Result (03.10.2026 14:50, `hw_logs/20261003_145006_host_params_probe.log`):**
`T151 summary: no_mnemonic=12, rejected (0x10)=1, verified=45,
verified_query=19`.

**Status:** ✅ PASS. The six flags are in `comm/host_params.py` for `13.SEP.95`.

---

### T162 — App: MONITOR and the band values survive a mode switch (P73)

Device B, PK232PY in Host Mode, nothing transmitted. Software:
`test_packet_params_p73.py`, `test_packet_hf.py` (`TestMonitorFromConfig`).

| # | Do | Expected | Result |
|---|---|---|---|
| 1 | Parameters -> Packet...: MONITOR 6, OK; select VHF Packet; leave Host Mode; verbose `MONITOR` | `6` (before P73: `4`, because `MN Y` set it) | ⬜ |
| 2 | Parameters -> Packet...: VHF MAXFRAME 5, OK (VHF Packet active) | MON: `MAXFRAME  4 -> 5  ok` | ⬜ |
| 3 | change the HF MAXFRAME while VHF Packet is active, OK | MON: `MAXFRAME (HF) saved - applies when HF Packet is selected`; no `MX` frame; no "TNC differs" label | ⬜ |
| 4 | select HF Packet, then VHF Packet again; leave Host Mode; verbose `MAXFRAME` | `5` | ⬜ |
| 5 | the Parameters tab at 100 %: three columns, no scrollbar | as stated | ⬜ |

**Result (03.10.2026, device B, operator, screenshots): ❌ FAIL.** The TNC was
already awake when the app connected, so there was no boot banner and
`tnc_release` stayed `None` (toolbar "TNC-Firmware: —"):
1. Host Mode, VHF Packet, MONITOR 4 -> 6, OK: "MONITOR not verified for Host Mode
   on **unknown** - saved, TNC unchanged"; a MAXFRAME change likewise had no effect.
2. The same change through the Monitor selector of the VHF Packet screen worked
   at once (verbose afterwards: 6) - it sent `MN6` directly, bypassing ParamApplier
   and the configuration.
3. verbose `MONITOR 3`, back into Host Mode: selector and TNC showed 6 again (the
   configuration was never told about the verbose change).
4. The hint dialog was still titled "HF Packet parameters not taken...".
Fixed by P78 (release fingerprint, verbose was/now sync, one way for MONITOR);
re-checked by T164.

**Status:** ❌ FAIL (device B, 03.10.2026) - see T164.

---

### T164 — App without a banner: release fingerprint, verbose sync, MONITOR (P78)

Device B first, then A. The TNC stays powered the whole time: **do not switch it
off and on** (that would print the banner and hide exactly what is tested).
Software: `test_p78_devices_parse.py`, `test_p78_release_and_sync.py`.

| # | Do | Expected | Result |
|---|---|---|---|
| 1 | Connect the app while the TNC is already running | toolbar "Release 01.AUG.91 (inferred)" (device A: "Release 13.SEP.95 (inferred)") | ⬜ |
| 2 | Host Mode, VHF Packet, Parameters -> Packet...: MONITOR 4 -> 6, OK | MON: `MONITOR  4 -> 6  ok` | ⬜ |
| 3 | VHF MAXFRAME 4 -> 5, OK; Leave Host Mode; verbose `MAXFRAME` | `ok`; `5` | ⬜ |
| 4 | verbose `MONITOR 3` | terminal: `[SYS] MONITOR 3 taken into the parameters`; Ctrl+H: the selector shows 3; Leave Host Mode, `MONITOR` -> 3 | ⬜ |
| 5 | Change the Monitor selector in the VHF Packet screen | MON: `MONITOR  3 -> n  ok` (through ParamApplier, one set + one read-back); the parameter mask shows n | ⬜ |
| 6 | Repeat 1-5 on device A | as above (step 1: "13.SEP.95 (inferred)") | ⬜ |

**Status:** ⬜ OPEN — hardware session (device B, then A).

---

### T166 / T167 — `mnemonic_probe`: the unproven Host Mode mnemonics (P80 Teil D)

`python tools/hw_check.py mnemonic_probe --part A|B|C|all` — T166 on device B,
T167 on device A (the tool picks the number by `has_pactor`); PC 1 only, nothing
is transmitted, no dummy load needed. Software: `test_hw_check_mnemonic_probe.py`.
Switch the TNC off and on before each device's run. **Never** sends a
transmitting mnemonic (XM, AC, FE, SE, CO, DI, PD) or any `action` kind.

| Part | What | Expected in the log |
|---|---|---|
| A | mode switches BA AS MO AM PT FA SI TV NA NE, each followed by `OP`, back to `PA` | `T16x mode <mn> … changed_and_returned` (or `unchanged` / `not_returned`); PT only on device A; `T16x mode NA vs NE … same/DIFFERENT` |
| B | unproven parameters (EA WI SR US WO FN SQ XL AY MW RB FS CI EE MY NM NS) through the `host_params_probe` engine, then the MID scan (verbose `MID` 7, harmless `M?` queries) | `T16x <NAME> (<mn>) … verdict` per parameter, `T16x MID scan … hits=[…]` |
| C | queries `MH` and (device A) `PN` | `T16x query MH/PN … frames=[…]` |

After the run: `python tools/hw_check.py mnemonic_probe --reevaluate <log>` prints
the evidence to enter in `comm/mnemonic_registry.py` (parameter rows: also
`host_params_probe --reevaluate` on the same log). Nothing is typed from the log by hand.

**Status:** ✅ PASS (03.10.2026; device B `01.AUG.91` = T166, `hw_logs/20261003_213830_mnemonic_probe.log`;
device A `13.SEP.95` = T167, `hw_logs/20261003_214801_mnemonic_probe.log`). Results equal on both devices unless noted.

- **Modes confirmed** (ACK `$00`, OP answer, back to `PA` checked): `BA` OPBAR, `AS` OPASR, `MO` OPMOR.., `AM` OPAM0R, `FA` OPFA0R,
  `SI` OPSI, `TV` OPTV0R, `NA` OPNA0; device A also `PN` -> OPPN1R1000 (PTLIST, one mode).
- **Parameters confirmed** (set, ACK, read back, verbose cross-check, restored): `EA` EAS, `WI` WIDESHFT, `SR` SRXALL, `US` USOS,
  `WO` WORDOUT, `FN` FAXNEG, `SQ` SQUELCH, `AY` ASPECT. Query only, answer = verbose value: `RB` RBAUD, `FS` FSPEED, `NM` NAVMSG, `NS` NAVSTN.
- **Refuted / not what the app assumed:** `NE` answers `NEY`, OPMODE stays `PA` (NEWMODE, a parameter - NAVTEX is `NA`); `PT` answers
  `PTA 10`, OPMODE stays `PA` (PACTIME, device A); `XL`, `EE` `$07`; `MW` answers `MWN` (a switch), setting 11 gives `$01`; `CI` answers
  `CIN` (a switch, verbose CODE is 0); `MY` `$07` (B) / `MYnone` (A) - ambiguous. MID scan `MA MB MC MJ MZ`: no hit.
- **Open:** bare `MH` answers only `MH$01` (B) / `MH$03` (A), no list - the app polls `MH0`..`MH17`, not bare `MH` (P80b report).
- The tool rated the parameters `unparsed` (no row, so no mnemonic/kind); fixed in P80b: `--reevaluate` on both logs gives `verified` for the eight set rows.

---

### T168 — `restart_probe`: the app's init with live links (P81, Teil 0)

`python tools/hw_check.py restart_probe --part A|B0|B|C|all` (PC 1 =
PK232PY tool + PK-232, PC 2 = TinyBox `OE3GAS-1` + QtTermTCP `OE3GAS-2`).
Software: `test_hw_check_restart_probe.py`. Simulates the crash (port closed
WITHOUT HOST OFF / DISCONNECT), then runs the app's own init
(`connect_port()` + `init_tnc()`) and `ParamsUploader.upload()`, every
answer in the log. The upload overwrites the TNC parameters (that is the
measurement); VHF/HBAUD are restored afterwards.

| # | Variant | TNC when the port is closed | Expected in the log |
|---|---|---|---|
| A | `--part A` | verbose command mode, links on ch0 (OE3GAS-2) and ch1 (OE3GAS-1) | `links_before` / `links_init` / `links_after`, rejected commands, PC 2 link alive? |
| B0 | `--part B0` | Host Mode, NO connection (no PC 2 step) | same without links; separates Host Mode from the links |
| B | `--part B` | Host Mode, links on ch0/ch1 | same; `RESTART init:` line says whether the init left Host Mode and after how many seconds |
| C | `--part C` | Converse (verbose `CONNECT`) | same; `links_before` is `{}` (not measurable in Converse) |

Result per variant: `T168 <v> INFO links_before=… links_init=… links_after=… rejected=[…] silent=[…] pc2_link_alive=… -- <verdict>`.
P81 parts A-C are built from these lines (parts B/D take the test cases from
the real log lines).

**Detection chain (added after the first run):** the log now carries the byte-level
capture of every restart (`LoggingSerialPort`, `>> hex=… text=…` / `<< …`), the
`pk232py.comm` DEBUG lines of the detection chain (`Init: step …`) and
`RESTART init: answered=… after N s`; the wait is 60 s (was 8 s). A failed init stops
the run (power-cycle the TNC, then run the remaining parts separately).
Every question is a framed, counted operator step (`start`, per variant `connect`, `call`,
`check`, `cleanup`; 13 steps for `--part all`); the `pk232py.comm` DEBUG lines go to the
log FILE only, so nothing is printed between a question and its answer.

**First run 03.10.2026 22:06 (`hw_logs/20261003_220612_restart_probe.log`, banner
`release=01.AUG.91  pactor=no` = device B).** (The shorter log `..._220341_...` is an
aborted start on device A, `13.SEP.95`, nothing measured.)
- **A** (verbose command mode): init found both links, the upload kept them. The TNC
  rejected 10 commands: `?not while connected` for `MYCALL OE3GAS` and `AX25L2V2 ON`
  (these two really need no link); `?What?` for `EXPERT ON/OFF`, `MYPTCALL`, `PTHUFF`,
  `PT200`, `PTOVER`, `ARQTOL`, `MOPT` (this device has no PACTOR, and `EXPERT` is unknown
  on 01.AUG.91; the restarted app had no banner, so the upload assumed PACTOR - see
  Backlog: filter the upload per firmware).
- **B** (Host Mode, 2 links): `FAIL` - no answer within 8 s; the TNC stayed in Host Mode
  with both links (the run was not stopped, so C started in a wrong state).
- **C**: not a clean Converse run (the TNC still held B's links: `?already connected`),
  but the upload again kept both links.
- Open question for B: did the detection chain simply need longer than 8 s? -> rerun
  `--part B0`, then `--part B` with the 60 s wait and the chain capture.

**Second round 03.10.2026 (device B, per the operator):**
- **B0** (`..._225739_...`) and **B** (`..._225902_...`): INVALID. The chain correctly detected
  Host Mode in step 3 (`HPN`), left it (HOST N, CR) and went on in verbose mode, but
  `restart_probe` read `host=True` at the moment step 3 reported Host Mode (23:04:11) and gave
  up. Fixed: the run now waits for the END of the init - `verbose_mode_ready` (ready) or
  `init_failed`, the same signals the app waits for - not for the first state.
- **C** (`..._230503_...`): PASS. Init and upload keep the link on channel 0. The second call
  (QtTermTCP) was refused because USERS was 1 after the power cycle (channel 0 busy, T147).
  Fixed: the run sets USERS 10 (verbose) before the calls and restores it afterwards.
- Rerun needed: B0, then B.

**Final result 04.10.2026 (device B, all logs with banner):** A `20261003_220612`,
B0 `20261004_121932`, B `20261004_124240`, C `20261004_122301`.

| Variant | Links kept by init + upload | Init | MYCALL / AX25L2V2 |
|---|---|---|---|
| A (verbose, 2 links) | yes | - | `?not while connected` |
| B0 (Host Mode, no links) | - | chain 11.3 s, ends verbose ready | accepted |
| B (Host Mode, 2 links) | yes | chain 11.3 s, ends verbose ready | `?not while connected` |
| C (Converse, ch0) | yes | 3.3 s (`20261003_230503`), 3.5 s (`20261004_122301`) | `?not while connected` |

In every variant with links the app's init (detection chain + upload) keeps the
connections. Only `MYCALL` and `AX25L2V2` are refused, and only while a link exists
(B0 without links: accepted). P81 B therefore holds back exactly these two.

**Status:** ✅ PASS (device B, 04.10.2026).

---

### T170 — Packet RX as a data stream (P82)  ✅ PASS (device B, 04.10.2026, operator screenshots)

Device B, TinyBox help in the ALL and CH views. `test_packet_rx_stream_p82.py` replays the packet
boundaries of the T169 screenshot. Expected on the device: words are not cut at packet
boundaries, no blank line or indent between frames, the prompt without CR is visible at once, ALL
shows timestamp (if on) and channel tag at the start of a line only, "Partner" changes when the
connect completes, "RX: n lines" follows the shown document. Result: ✅ PASS (device B, 04.10.2026).

---

### T171 — Parameter upload without widget access from the thread (P83)

Device B. Software: `test_upload_thread_p83.py`, `test_thread_guard_p83.py`.

| # | Do | Expected | Result |
|---|---|---|---|
| 1 | Normal start with upload, connection type verbose, then once with Host Mode | terminal output complete and in order (`[SYS] Uploading parameters...`, every command, `[SYS] parameter upload verified (3/3)`, `[SYS] n parameters uploaded -- ...`), Host Mode entered after the upload | ⬜ |
| 2 | Restart with two links (as T169) | output, deferral and Host Mode entry unchanged | ⬜ |
| 3 | App log (`DEBUG`) after 1 and 2 | NO line "widget access outside the GUI thread" | ⬜ |

**Status:** ⬜ OPEN — software done, hardware run pending.

---

### T172 — Chip text white in every theme; log file (P84)

Any device. Software: `test_chip_text_p84.py`, `test_logging_p84.py`.

| # | Do | Expected | Result |
|---|---|---|---|
| 1 | HF Packet: switch Dark -> Mono -> Retro -> Air -> back, look at MON and 0-9 (free, calling, connected) | chip text white in every theme and after every switch back | ⬜ |
| 2 | Start the app; Help -> Open log folder | the folder `%USERPROFILE%\.pk232py\logs` opens; `pk232py.log` exists | ⬜ |
| 3 | Open `pk232py.log` | first line: `PK232PY v..., commit ..., Python ..., Qt ..., PyQt ...`; DEBUG lines follow | ⬜ |
| 4 | Start the app twice | the file gets a second header line, no second file, nothing lost | ⬜ |

**Status:** ⬜ OPEN — software done, run on the PC pending.

---

### T173 — Upload only sends commands the firmware knows (P85)

Software: `test_p85_upload_firmware_filter.py`. Needs devices B and A (hardware pending).
Refused on 01.AUG.91: EXPERT, MYPTCALL, PTHUFF, PT200, PTOVER, ARQTOL, MOPT (8 commands with EXPERT ON and OFF).

| # | Do | Expected | Result |
|---|---|---|---|
| 1 | Device B, start WITH banner | terminal: `[SYS] 1 commands skipped ... (EXPERT)` (banner says pactor=no, so the PACTOR commands are not even built); NO `?What?` in the upload part of `pk232py.log` | ✅ |
| 2 | Device B, restart WITHOUT banner (release `inferred`) | `8 commands skipped`, no `?What?` | ✅ |
| 3 | Device A, start with banner | no command skipped, no `?What?` | ✅ |
| 4 | Device B: Parameters -> AMTOR and Baudot | ARQTOL / MOPT greyed, tooltip `Not supported by firmware 01.AUG.91 (T155, T160, T168)`, values kept | ✅ |

**Status:** ✅ PASS (device B with and without banner, device A; 06.10.2026, operator observation). Without banner `has_pactor` was assumed True (the 8 skipped) - P85a now takes it from `KNOWN_DEVICES` for an inferred release, so a re-run should show fewer commands built; not yet re-measured.


---

### T175 — CR-only verbose commands with ILFPACK ON and OFF (P75 Teil 0)

PC 1, device B and device A, verbose command mode, ILFPACK ON, no connection. Nothing is sent on the air.
Run: `tools\hw_check.py eol_probe` (`--dry-run` shows the plan). Software: `test_hw_check_eol_probe.py`.
Logs: B `20261006_144428_eol_probe.log`, A `20261006_145938_eol_probe.log`.

| # | Step | Expected | Result B (01.AUG.91) | Result A (13.SEP.95) |
|---|---|---|---|---|
| 1 | ILFPACK ON, five queries with CR only | all right | ✅ | ✅ |
| 2 | ILFPACK ON, same with CR LF | all right | ✅ | ✅ |
| 3 | Host Mode: `IL N`, query; leave; verbose `ILFPACK` | OFF | ✅ verbose `ILfpack   OFF` | ⚠️ host `IL` read back `N`; verbose `ILFPACK` answers `?EXPERT command` (EXPERT is OFF after power-on on 13.SEP.95) - no verbose cross-check |
| 4 | ILFPACK OFF, five queries with CR only | **all five right** (the question) | ✅ | ✅ |
| 5 | ILFPACK OFF, same with CR LF | as T155: first right, then `?What?` | ✅ reproduces T155 | ⚠️ no `?What?` with CR LF either (cannot be compared: the verbose value was not readable) |
| 6 | `MAILDROP` query with CR only | answered | ✅ | ✅ |
| 7 | `CONVERSE` with CR only, then COMMAND char | `cmd:` again | ✅ | ✅ |
| 8 | Restore: Host Mode `IL Y`, verbose `ILFPACK` | ON | ✅ `ILfpack   ON` | ⚠️ host `IL` read back `Y`; verbose check again `?EXPERT command` |

**Status:** ✅ PASS device B (all steps). Device A: CR-only works in every step; `IL` set and read back via Host Mode, but
the verbose cross-check is missing (`?EXPERT command`) - redo it with EXPERT ON (Backlog). Operator observation 06.10.2026.

---

### T176 — ILFPACK applied live, CR-only commands in the app (P75 Teil D, device B)

Software: `test_verbose_cr_only_p75.py` (done). PC 1, device B (01.AUG.91), verbose command mode.
The terminal lines and every upload command now end with CR only.

| # | Do | Expected | Result |
|---|---|---|---|
| 1 | Packet mask: ILFPACK off -> OK; leave Host Mode; terminal `PACLEN`, `USERS`, `HELP` | applied at once (`ILFPACK  ON -> OFF  ok`); all three answered right (no `?What?`) | ⬜ |
| 2 | Restart PK232PY (TNC still ILFPACK OFF): init, upload, Host Mode entry | no `?What?` in `pk232py.log` | ⬜ |
| 3 | ILFPACK on again (mask -> OK) | ON; terminal `ILFPACK` shows ON | ⬜ |
| 4 | Device A, verbose command mode (EXPERT OFF): mask ILFPACK off -> OK | message `ILFPACK  ON -> OFF  ok (needed EXPERT ON, set back to OFF)`; verbose `EXPERT` shows OFF afterwards | ⬜ |

**Status:** ⬜ OPEN — software done, hardware run pending (step 4 is the `?EXPERT command` path on device A).

---

### T177 — Parameter masks alphabetical (P87)

Any device, no connection needed (Parameters menu). Software: `test_param_order_p87.py` (the order is read from the real
geometry of the shown dialogs).

| # | Do | Expected | Result |
|---|---|---|---|
| 1 | Packet (all three tabs), AMTOR, Baudot/ASCII/CW, PACTOR, Misc, MailDrop | every group / column alphabetical, top to bottom, digits first (`8BITCONV` before `ACRPACK`, `UBIT 0` under U); exceptions as listed in the report: HF/VHF table, read-only values at the end, access filters (Message Params), local archive (MailDrop) | ⬜ |
| 2 | Change a value in each mask, OK, reopen | value kept (the widgets are the same, only their place changed) | ⬜ |

**Status:** ⬜ OPEN — software done, visual check pending.

---

### T178 — Terminal input continues the TNC prompt (device A, 06.10.2026 screenshot)

Software: `TestInputFollowsTheTncPrompt` in `test_main_window_verbose.py`.

| # | Do | Expected | Result |
|---|---|---|---|
| 1 | Verbose terminal: type `ilfpack` + Enter, then `users`, then `paclen` | each line reads `cmd:ilfpack`, never `cmd:cmd:ilfpack` | ⬜ |
| 2 | Clear the display (new connect), type a first line | the line shows one `cmd:` of its own | ⬜ |

**Status:** ⬜ OPEN — software done, hardware run pending.

---

### T179 / T180 / T181 — firmware scan with the command matrix (P88 Teil D)

Software: `test_pk232_fw_scan.py`, `test_command_matrix*.py`. PC 1, **no radio connected**, no connection on the TNC,
verbose command mode. The tool sends only `param` commands (and, with `--immediate`, the `immediate` ones); `mode`, `action_tx`,
`danger` and CALIBRATE/TRANS are never sent (`python tools\pk232_fw_scan.py --plan` lists them). It ends every line with CR.
It starts with RESTART (banner) - the TNC drops live links, so run it with none.

Per device:
1. `.venv\Scripts\python.exe tools\pk232_fw_scan.py --port COMx --csv hw_logs\<date>_fw_scan_<device>.csv --debug hw_logs\<date>_fw_scan_<device>.log`
2. Read "DIFFERENT FROM THE MATRIX" in the report: it must be empty (else: a contradiction to settle, nothing is written).
3. Only then add `--update-matrix` (same command) - it fills the `?` cells for the banner release; then
   `.venv\Scripts\python.exe tools\gen_command_matrix.py --update`.
4. Optional second run with `--immediate`.
5. Afterwards: `ILFPACK`, `EXPERT` and the packet mode as before (the tool restores EXPERT and PACKET).

| # | Device | Expected | Result |
|---|---|---|---|
| T179 | B (01.AUG.91) | no contradiction; the `?` cells of 01.AUG.91 filled | ✅ PASS (runs 1, 2, 3 and the `--immediate` run, see below) |
| T180 | C (30.DEC.88) | first contact of device C with this software - **ask the operator first**; the matrix has one cell for C (MAILDROP no). **First try 06.10.2026: no sync** - cause: the wake-up order in the scanner (first byte Ctrl-C; device C waits after power-on for a lone `*` for the autobaud measurement and stays deaf for anything else; the app does it right, step 1 of the detection chain). The scanner now wakes like the app (`*` without CR first, then wait for banner or `cmd:`, only then CR / Ctrl-C / XON) and waits for the banner after RESTART instead of a fixed 0.6 s; the second try is pending. **Run 1 and 2 (06.10.2026, `hw_logs/20261006_fw_scan_C.*` and `..._C_update.*`):** sync with `*` works; both runs 146 SUPPORTED, 63 UNSUPPORTED, 0 ERROR, no flip, no difference to the matrix (EXPERT and MAILDROP unsupported). The banner prints `Release 30.DEC.88` (not `30.12.1988`): the scanner said "device ?", the first `--update-matrix` correctly refused ("not a column of the matrix", nothing written). Release keys are the banner text now; **the matrix update for 30.DEC.88 is still to be done** (repeat the run with `--update-matrix`) | ⬜ |
| T181 | A (13.SEP.95), optional | confirms the 176 yes of the 28.07.2026 run; fills the Q values etc. | ⬜ |

**T179 result (device B, 06.10.2026, `hw_logs/20261006_fw_scan_B.*` without and `..._B_update.*` with `--update-matrix`):**
no contradiction with the matrix, no SUPPORTED/UNSUPPORTED flip between the runs (151/34/24 and 155/30/24 SUPPORTED/UNSUPPORTED/ERROR).
`--update-matrix` wrote 116 cells, every one `?` -> `yes` (97, from SUPPORTED) or `?` -> `no` (19, from UNSUPPORTED); none from an
ERROR row (the 24 ERROR rows are untouched), no other release changed. Three of them (DELETE, PTUP, TRFLOW) were taken back to `?`:
their answers came in one batch with the neighbours'. Matrix 01.AUG.91 now: 164 yes, 33 no, 63 `?`.
**The 24 ERROR per run:** all of them from the SIGNAL phase on (0 ERROR in the 104 probes of packet, rtty, amtor, morse, fax, navtex;
first ERROR AFILTER / AUTOBAUD, the first modeless command after the signal group). Cause (log): the TNC answers later than the read
window (0.4 s), the reply lands in the next command's read (`AUTOBAUD` got the echoes and answers of AFILTER, ALFDISP, AUTOBAUD);
SIGNAL survives RESTART (analysis lines keep coming after the resync; the final `PACKET` answers `Opmode was SIgnal`), so the resync
never helped. Fixed in `pk232_fw_scan.py`: modeless groups run in PACKET, a result needs the command's own echo and the prompt.
**Third run (device B), only what is still `?`:** `... pk232_fw_scan.py --port COMx --immediate --csv hw_logs...C.csv --debug ...`
(21 parameters: AUTOBAUD AWLEN BKONDEL CMSG CTEXT DELETE ECHO ESCAPE MDMON MDPROMPT PARITY PRCON PROUT PTROUND PTSUM PTTRIES PTUP TBAUD TIME
TMPROMPT TRFLOW, and 14 immediate commands); the other 28 `?` cells are mode / action_tx / danger commands that are never sent.

**Run 3 and the `--immediate` run (`hw_logs/20261006_fw_scan_B_run3.*`, `..._B_imm.*`):** run 3: 172 SUPPORTED, 37 UNSUPPORTED, 0 ERROR (209 probes),
no difference to the matrix. `..._B_imm.*`: 223 probes (the 209 and the 14 immediate commands), 184 SUPPORTED, 39 UNSUPPORTED, 0 ERROR. Every cell
they wrote is backed by an answer that starts with its own echo and reaches the prompt (checked with `answer_to()` against both logs). Together
they filled the 35 cells that were still open: 21 parameters (AUTOBAUD AWLEN BKONDEL CMSG CTEXT DELETE ECHO ESCAPE MDMON MDPROMPT PARITY PRCON
PROUT PTROUND PTSUM PTTRIES PTUP TBAUD TIME TMPROMPT TRFLOW: 17 yes, 4 no) and 14 immediate commands (12 yes, 2 no). **Matrix 01.AUG.91 now: 193 yes,
39 no, 28 `?`** - the 28 are mode / action_tx / danger commands that are never sent.
**"0 cells filled" in the run 3 report:** not a counter bug. The surviving run 3 started with the 21 parameter cells already set (its MATRIX column
shows yes/no for all 209 rows): an earlier call with the same `--csv` path had written them (the evidence names `..._run3.csv`; its files were
overwritten by the repeat). Applying the surviving run 3 CSV to the previous matrix fills exactly these 21 cells with exactly this evidence;
a repeated call counts 0 (`TestFilledCounter`).

**Status:** ✅ PASS for device B (T179). T180 (device C, ask the operator first) and the optional T181 (device A) pending.

---

### T182 / T183 / T184 — scan of ALL commands with `--all` (P89 Teil F)

Software: `test_pk232_fw_scan_risky.py` (mock TNCs: the transparent mode only a paced 3 x Ctrl-C leaves, CALIBRATE that returns on `Q` or after
60 s, a command after which the TNC stays silent until it is power-cycled). **Operator at the TNC, NO RADIO connected (or a dummy load).**
The tool asks for both confirmations (exit code 5 without them) before it opens the port. It runs the normal queries first, then every command that
was never sent (37), one by one from the harmless to the most delicate: baseline `cmd:`, send, 3 s of raw recording, way back from the table `RECOVERY`
(each step logged with its result), `OPMODE` and `MYCALL` afterwards; if no way back works it asks you to power-cycle the TNC (`needs_power_cycle`)
and wakes it like the app (`*` first), then sets MYCALL again. RESTART / RESET / REINIT wait for the banner.

`.venv\Scripts\python.exe tools\pk232_fw_scan.py --port COMx --all --csv hw_logs\<date>_fw_scan_all_<device>.csv --debug hw_logs\<date>_fw_scan_all_<device>.log`
(`--plan --all` lists the order and the ways back; add `--update-matrix` only after reading "DIFFERENT FROM THE MATRIX" - it fills the `fw_` cells and, if
empty, the new `fx_` cells with effect and way back, e.g. `enters transparent mode; exit 3xCtrl-C/CMDTIME`.)

| # | Device | Expected | Result |
|---|---|---|---|
| T182 | A (13.SEP.95) | every risky command measured with its effect and way back; the July finding (TRANS / CALIBRATE not left with a hurried Ctrl-C) explained by the paced 3 x Ctrl-C / `Q` / 60 s | ⬜ |
| T183 | B (01.AUG.91) | same | ⬜ |
| T184 | C (30.DEC.88) | same (wakes only on a first `*`; RESTART may need a `*` again) | ⬜ |

**Status:** ⬜ OPEN — tool done, runs pending.

---

### T186 — the risky part again with preconditions, only the affected commands (P89a)

Software: `test_pk232_fw_scan_p89a.py`. **Operator at the TNC, no radio connected**, once per device (A, B, C):
`.venv\Scripts\python.exe tools\pk232_fw_scan.py --port COMx --all --only ACHG,ALIST,AMTOR,ARQ,CONVERSE,FEC,ID,K,MDCHECK,MEMORY,OVER,PTCONN,RCVE,SAMPLE,SELFEC,TRANS,XMIT --mycall <your call> --csv hw_logs\<date>_fw_only_<dev>.csv --debug hw_logs\<date>_fw_only_<dev>.log`
(the port is `--port`, not positional; add `--update-matrix` after a run that looks right). Expected: MYCALL/MYSELCAL set, XMIT/RCVE tried in BAUDOT, ACHG/OVER in AMTOR, MDCHECK left with `B`, no `fx_` that is only a refusal,
MYCALL/MYSELCAL back to the old values at the end.

Run 2026-10-07, no power cycle needed (`hw_logs/20261007_fw_only_{A,B,C}.csv/.log`):

| # | Device | Expected | Result |
|---|---|---|---|
| 1 | A | see above; MEMORY with EXPERT ON answers a value | ✅ PASS - MEMORY `prints a value`; but MYSELCAL was NOT given back (see findings) |
| 2 | B | see above | ✅ PASS - same MYSELCAL finding; the TNC stayed in `FEc IDLE SEND` after FEC and in `AMtor STBY RCVE` after ID / SELFEC |
| 3 | C | see above (no MDCHECK, no OVER) | ✅ PASS with an open point: FEC / XMIT (see findings) |

**Findings (all fixed in the scanner, to be measured again in T187):**
1. **FEC** (C, and A / B): Ctrl-C brought `cmd:` back but OPMODE stayed `FEC IDLE SEND`; ID and XMIT afterwards answered `?not while in FEC` (C) - the `fx_30.DEC.88` cell `exit Ctrl-C`
   for FEC was cleared (note in `ev_`). Way back now `Ctrl-C+PACKET`; every command with `NEEDS_MODE` is only sent when OPMODE shows the mode (`mode not reached`, not sent, no cell); the report
   warns when the TNC is not in PACKET after a way back.
2. **ARQ / SELFEC** answered `?callsign` (C): they get a dummy target (`--target`, default `NOCALL`), way back `Ctrl-C+DISCONNE+PACKET`; PTCONN is treated the same.
3. **MYSELCAL** (A, B): the restore sent `MYSELCAL none`, the firmware took it as the VALID selcal: `MYSelcal  was OEAS` / `MYSelcal  now NONE`. **A and B still hold `NONE`** until a power cycle with
   the factory banner line. Hand test at A (07.10.2026): `%` (reported as `&`) and `OFF` answer `?callsign`, `NONE` answers `now NONE` - **no command clears it at A and B** (an earlier plan with `MYSELCAL %`
   is dead). The scanner now gives an unset MYSELCAL back by a power cycle (P89b, T188). Device C showed `OEAS` before the run (origin unknown), so it was restored to `OEAS`.
4. **Power cycle** (hand test at A, 07.10.2026): off and on after a short pause kept the settings (banner without an extra line, `MYSELCAL` still `NONE`); after a longer pause the line
   `PK-232M is using default values.` came first and `MYSELCAL` was `none`. "Switching off gives the factory state" is wrong; the factory state is the banner line (P89b, T188).
5. `--update-matrix`: C filled 7 `fx_` cells (ALIST, AMTOR, CONVERSE, FEC, K, RCVE, TRANS; TRANS is the first effect ever measured at C), A 6, B 5 - 18 cells, no `fw_` cell (all were known). A second
   `--update-matrix` on the same CSV fills 0 (the cells exist, same text, no conflict) - that is the "0 cells filled for 30.DEC.88".

**Status:** ✅ A, B PASS; C PASS with the open point FEC / XMIT -> T187.

---

### T187 — FEC, ID, XMIT, ARQ, SELFEC, PTCONN again, and the way to clear MYSELCAL (T186 findings)

Software: `test_pk232_fw_scan_t186.py`, `test_factory_banner_p89b.py`. **Operator at the TNC, no radio connected**, per device. A and B hold `NONE` in MYSELCAL: switch the TNC off for longer
(see T188 - the scanner asks for it at the end when MYSELCAL was unset) before or after the run.
`.venv\Scripts\python.exe tools\pk232_fw_scan.py --port COMx --all --only FEC,ID,XMIT,ARQ,SELFEC,PTCONN --mycall <your call> --target NOCALL --csv hw_logs\<date>_fw_only2_<dev>.csv --debug hw_logs\<date>_fw_only2_<dev>.log`

| # | Device | Expected | Result |
|---|---|---|---|
| 1 | A | FEC way back `Ctrl-C+PACKET`, OPMODE PACKET after it; ID / XMIT no `?not while in FEC`; ARQ / SELFEC / PTCONN no `?callsign`; at the end the scanner asks for the power cycle (T188) and `MYSELCAL` shows `none` | ⬜ |
| 2 | B | same | ⬜ |
| 3 | C | same (C showed `OEAS` before T186 - a set value is put back by setting it, no power cycle) | ⬜ |

**Status:** ⬜ OPEN (add `--update-matrix` only after a run that looks right; the cleared FEC cell of C is filled again then).

---

### T188 — power cycle: factory state only with the banner line, and how long "off" must be (P89b)

Software: `test_factory_banner_p89b.py` (banners copied from the logs). **Operator at the TNC.** What the scanner does now: at every power cycle it shows
`Switch the TNC off, wait at least 10 seconds, switch it on.` (**10 s = starting value, NOT measured**), wakes the TNC, reads the banner; without the line `PK-232M is using default values.`
(device C: `PK-232 is using ...`) it says `TNC kept its settings - switch off longer and repeat` and shows the step again (3 tries). At the end of a `--all` run with an unset MYSELCAL it asks for exactly that.

| # | Device | Do | Expected | Result |
|---|---|---|---|---|
| 1 | A | run T187 (MYSELCAL is `NONE` now); at the end do the step as shown; note the seconds you really waited and what the banner looked like | banner with the line, `MYSELCAL` `none`; if not: the message and the step again | ⬜ |
| 2 | B | same | same | ⬜ |
| 3 | C | a power cycle (e.g. `--all --only MEMORY` with the TNC hung, or by hand) - device C needs the `*` first | its banner has `PK-232 is using default values.` (no M) and the scanner takes it as the factory state | ⬜ |
| 4 | A or B | at the step of row 1 first wait only about 2 s, press ENTER | the banner has NO line: `TNC kept its settings - switch off longer and repeat`, the step is shown again (the hand test, now in the tool) | ⬜ |
| 5 | A or B | find the shortest pause that gives the line (try 3, 5, 10 s) | the measured value replaces the starting value 10 s in `POWER_OFF_SECONDS` | ⬜ |

**Status:** ⬜ OPEN.

---

### T185 — scan kit rehearsal at device B with our own setup (P90)

Software: `test_scan_kit_p90.py` (builds the kit, runs the embedded scanner in an empty interpreter), `test_pk232_fw_scan_kit.py`,
`test_import_external_scan_p90.py`. **Operator at the TNC, no radio connected.** Rehearse exactly what an external operator will do:

1. `.venv\Scripts\python.exe tools\build_scan_kit.py` -> `dist\pk232_scan_kit_<date>.zip`; unpack it into an EMPTY folder (not the repo) and use a Python
   that has only `pyserial` (a fresh venv).
2. Run `run_scan.bat` (port, 9600, your callsign): the safe run. Before it, put device B into a state of its own to test the restore: for instance
   `EXPERT ON`, `ECHO OFF` and another operating mode (BAUDOT).
3. At the end the report must say `Device state : restored (DISPLAY before = after)`; check `settings_before.txt` against `settings_after.txt` and that
   `EXPERT`, `ECHO` and the operating mode are as you left them. `scan_results\scan_01.AUG.91_n1\` holds banner.txt (verbatim), scan.csv, debug.log,
   settings_before/after.txt, device_info.txt; `scan_results\results_<call>_<date>.zip` holds the folder.
4. Fill in `device_info.txt`, then on our side `.venv\Scripts\python.exe tools\import_external_scan.py <zip> --dry-run`: no contradiction with our own
   measurements of device B (T179); a real import would change nothing (all cells are known).

| # | Do | Expected | Result |
|---|---|---|---|
| 1 | steps 1-3 with ECHO OFF / EXPERT ON / BAUDOT beforehand | scan without ERROR, device state restored | ⬜ |
| 2 | step 4 `--dry-run` | 0 cells filled, no contradiction | ⬜ |

**Status:** ⬜ OPEN — kit, restore and import done, rehearsal pending.

---

### T174 — Macros in Packet; crashes in the log file (P86)

Any device (macros are only inserted, nothing is sent). Software: `test_macros_packet_p86.py`,
`test_crash_log_p86.py`. (T173 is P85.)

| # | Do | Expected | Result |
|---|---|---|---|
| 1 | HF Packet, MON chip: press each of the six macro buttons | text appears in the input field (end, TX colour), nothing is sent, no crash | ✅ |

**Status:** ✅ PASS (device B, 06.10.2026, operator observation).
| 2 | Same on a free and on a connected channel; switch channel and back | the text belongs to that channel's input only | ⬜ |
| 3 | Same in VHF Packet; a macro containing `[^D]` or `[^T:5]` | markers removed, one `[SYS]` note in the monitor and one line in the log file | ⬜ |
| 4 | Baudot / ASCII RTTY / Morse / AMTOR: macro buttons | unchanged (`[^D]` and `[^T:n]` still work) | ⬜ |
| 5 | PACTOR: macro button | text inserted, no crash | ⬜ |
| 6 | Provoke an exception (a development build with a deliberately failing slot) | box "Internal error - the last action may be incomplete. Details in the log file." with "Open log folder"; at most once per 10 s; traceback in `pk232py.log` (CRITICAL) and on the console; the app keeps running | ⬜ |

**Status:** ⬜ OPEN — software done, run on the PC pending.

---

### T169 — App: live links found at start-up (P81, after T168)  ✅ PASS

Device B. Needs P81 parts A-C (built 04.10.2026, `test_live_links_p81.py`). First run 04.10.2026
aborted after step 3 with four findings, fixed as P81a (see Backlog): ALL view scroll position,
deferral only for a real difference (real TNC value shown as the starting value), the deferred
notice in MON and the status bar after the switch to Host Mode, the "Waking up the TNC..." notice.
Rerun: also check the notice (blinking, seconds, stage) during a slow wake-up and that the
prompt of the TinyBox appears in the ALL view after the connect on chip 1. Second report 04.10.2026: the prompt was still missing in ALL with ALL active the whole time (CH click shows it). `test_packet_all_view_prompt_p81b.py` replays that sequence (real show()/resize(), measured cursor rectangle) and is GREEN - not reproduced, nothing changed. Rerun with DEBUG logging: the `RX append ch=… shown=… bar before=… after=… stack_current=… visible=…` lines (`pk232py.ui.screens.packet_screen`) tell whether the line does not arrive or is only not scrolled into view. **Cause found (third report: only the FIRST appearance of the VHF mask in Host Mode):** `MainWindow._switch_opmode()` pushed the previous screen's RX document (`_shared_rx_doc`) into the incoming Packet screen, replacing its ALL document - lines went to `_rx_doc_all`, the widget showed another document. Fixed (P81b): a Packet screen attaches its own document through `_sync_rx_document()` at build and at every activation, and never hands it on; DEBUG line now has `doc_is_all=`. Recheck in T169.

**T169 findings, round 3 (04.10.2026):** (a) Chips dashed after a restart: CSTATUS gave
"connected" (solid); the Host Mode entry then marked the links unconfirmed and asked CO - but
on a restart no Packet mode is active yet, ModeManager activates it on its own timer and
`ModeManager.on_frame()` drops every frame while none is active, so the CO answers were lost.
Fixed (P81c): the CO round waits for the mode activation (`test_restart_chips_p81c.py`, red first).
(b) Parameter dialog while a link exists: `ParamApplier` now reads the TNC value first (equal ->
"already set", nothing sent), shows the TNC's real value as starting value and reports `$09` /
"?not while connected" as `busy` - deferred like P81 (MON, status bar, "TNC differs", catch-up after a
CO round reports all channels free) instead of an error dialog (P82a, `test_apply_busy_p82a.py`).
(c) NOT an application finding: the disconnect from OE3GAS-1 did not complete and the chip stayed in
the disconnecting state - the radio path (DISC repetitions) did not deliver the UA.
Step 1 also checks part B: the `[SYS]` line "2 parameters deferred until all connections
are closed: MYCALL, AX25L2V2" and the red status field "TNC differs from parameters"; after
the last link ends (DI on both channels) `MYCALL` and `AX25L2V2` are set (monitor line
"all connections closed - applying deferred parameters") and the field disappears.

| # | Do | Expected | Result |
|---|---|---|---|
| 1 | Two links as in T168; end PK232PY in the Task Manager; start it again | both chips connected, `[SYS]` line "2 active connections found: …", NO bell | ⬜ |
| 2 | Same, but end PK232PY normally | as 1 | ⬜ |
| 1b | After step 1: disconnect both channels (chip menu) | deferred parameters applied, "TNC differs from parameters" gone, `MYCALL` reads back | ⬜ |
| 3 | Control: TNC off/on, start PK232PY | no check (banner), no links | ⬜ |

**Status:** ✅ PASS (retest 04.10.2026, device B: chips confirmed after a restart; AX25L2V2 deferred while
a link existed and caught up after the disconnect).

---

### T165 — Appearance: every theme keeps its own settings (P79)

Software: `test_appearance_per_theme_p79.py`. No TNC needed.

| # | Do | Expected | Result |
|---|---|---|---|
| 1 | Theme Air: Font & Colors -> font A, TX text green. Theme Dark: font B. Theme Retro: font C | each OK; the title reads "Appearance — Air" / "— Dark" / "— Retro" | ⬜ |
| 2 | Switch between Air, Dark, Retro | each theme shows its own font/colour | ⬜ |
| 3 | Quit PK232PY, start it again | all three themes still have their own settings; the old theme is selected | ⬜ |
| 4 | Air -> Font & Colors -> Reset -> OK | Air shows its defaults; Dark and Retro unchanged | ⬜ |
| 5 | Open an old `pk232py.ini` (one `[Appearance]` section with a font) | the font appears under the stored theme; after saving the INI has `[Appearance.<theme>]` | ⬜ |

**Status:** ✅ PASS (03.10.2026, operator decision; steps not recorded one by one).

---

### T157 — App: parameters right after OK (P72)

Device B, VHF Packet, 144.800 MHz with a dummy load or minimum power; PC 1
runs PK232PY, PC 2 QtTermTCP (`OE3GAS-2`). Software: `test_param_applier.py`,
`test_main_window_params_apply.py`.

| # | Where | Do | Expected | Result |
|---|---|---|---|---|
| 1 | PC 1 | Host Mode, VHF Packet: USERS 10 -> 9, OK | MON: `[SYS] USERS  10 -> 9  ok`; Host Mode stays; no verbose byte in the log | ✅ |
| 2 | PC 1 | AX25L2V2 toggled, OK | `ok` | ✅ |
| 3 | PC 2 | QtTermTCP `OE3GAS-2` connects | connected | ✅ |
| 3 | PC 1 | MAXFRAME changed, OK | `ok`, the connection stays | ✅ |
| 4 | PC 1 | CTEXT changed, OK | `CTEXT  not verified for Host Mode on 01.AUG.91 - saved, TNC unchanged`, status field "TNC differs from parameters" | ✅ |
| 5 | PC 1 | leave Host Mode (verbose), PACLEN changed, OK | `ok` | ✅ |

**Result (02.10.2026, device B, operator observation):** all steps as in the
table.

**Status:** ✅ PASS (device B, 02.10.2026, operator observation).

---

### T152 — `host_params_probe` B: set parameters while connected (P71)

`python tools/hw_check.py --port COM6 host_params_probe --part B`. Two PCs:
QtTermTCP `OE3GAS-2` connects to the TNC (lands on channel 0, T147). In Host
Mode USERS, MAXFRAME, PACLEN, FRACK, RETRY, MONITOR, TXDELAY are each set,
asked, set back; after each one `CO` on the connected channel. Then one
line from QtTermTCP must arrive on `$30`; `DI` behind `confirm_tx()`.

**Result, device A (`13.SEP.95`), 02.10.2026, two runs.** Run 1
`hw_logs/20261002_163032_host_params_probe.log`: B.3 (one line from QtTermTCP)
without a line arriving (`line_seen_on_ch0=False`). Run 2
`hw_logs/20261002_172135_host_params_probe.log`: with the line
(`line_seen_on_ch0=True`). Both: all seven set (`<mn> $00`), read back, link
unchanged (`link_after=True`). Not yet run on device B (not needed for P72:
it reads back after every set).

| Parameter | accepted / rejected (code) | link_after |
|---|---|---|
| USERS | accepted (`UR$00`, query `UR2`) | True |
| MAXFRAME | accepted (`MX$00`, `MX5`) | True |
| PACLEN | accepted (`PL$00`, `PL129`) | True |
| FRACK | accepted (`FR$00`, `FR5`) | True |
| RETRY | accepted (`RY$00`, `RY11`) | True |
| MONITOR | accepted (`MN$00`, `MN5`) | True |
| TXDELAY | accepted (`TD$00`, `TD31`) | True |

**Status:** ✅ PASS (device A, `13.SEP.95`); device B ⬜ OPEN. Feeds P72.

---

## Test Block 7 — PACTOR / AMTOR Identity Labels (v12)

### T52–T58
**Status:** ⬜ OPEN

---

## Test Block 8 — APRS Decoder (v15)

### T59 — APRS button toggle
1. VHF Packet, frames already received → click **APRS** button

**Expected result:**
- Button turns amber/orange
- RX display re-renders all buffered frames as HTML cards
- Frame types correctly colour-coded:
  - Mic-E → orange, 🚐 icon
  - Position/Position+Time → blue, 📡 icon
  - Telemetry → yellow, 📊 icon
  - Weather → green, 🌦 icon
  - Message/Telem-config → pink, 📨 icon
  - Third-party → light grey, 🌐 icon

**Status:** ✅ OK (v15 — confirmed 2026-05-17)

---

### T60 — APRS toggle OFF: raw restored
1. APRS ON (HTML cards displayed) → click APRS again

**Expected result:**
- Button returns to inactive style
- RX display re-renders all frames as plain text with timestamps
- Original content fully restored, no data loss

**Status:** ✅ OK (v15 — confirmed 2026-05-17)

---

### T61 — Mic-E position decode
1. APRS ON, receive Mic-E frame (APRS-ID = TXxxxx, TWxxxx etc.)

**Expected result:**
- Latitude decoded from destination field (e.g. TXQU09 → 48.2515°N)
- Longitude decoded from info bytes (e.g. `,]kX` → 16.0965°E)
- Values geographically plausible for OE3 area
- Comment shown after `—` separator if present (e.g. frequency info)

**Status:** ✅ OK (v15 — OE3PDB-2: 48.25°N / 16.10°E confirmed)

---

### T62 — Position+Time decode
1. APRS ON, receive `@` position frame

**Expected result:**
- UTC timestamp shown (e.g. `UTC 12:13 (day 17)`)
- Lat/lon in decimal degrees
- Symbol name shown (e.g. `Digi`, `IGate`, `WX-Station`)
- Comment on second line

**Status:** ✅ OK (v15 — OE3SZA-15 Hochkogel Digipeater confirmed)

---

### T63 — Telemetry chip display
1. APRS ON, receive `T#` frame

**Expected result:**
- Seq number + digital byte on first line
- A1–A5 values as individual chips

**Status:** ✅ OK (v15 — OE1SCS-4 T#221 confirmed)

---

### T64 — Weather data chips
1. APRS ON, receive WX station frame (APEWX*, symbol `_`)

**Expected result:**
- Position decoded
- Weather chips: wind, gust, temp (°F), baro (mb), humidity (%)

**Status:** ✅ OK (v15 — OK1VCF-5 confirmed)

---

### T65 — APRS buffer cleared on mode switch
1. VHF Packet, frames received → switch to Baudot RTTY → switch back to VHF Packet

**Expected result:**
- RX display empty on return
- `_packet_raw_frames` buffer cleared
- APRS button resets to inactive

**Status:** ⬜ OPEN

---

## FAX closed-loop decode (tools/) — T66–T68

Closed-loop test path: `tools/fax_wav_generator.py` → WAV →
`tools/fax_decoder_test.py`. No TNC, radio or live audio. Generator and
decoder verified 2026-06-14; both decoder bugs (line-drift slant, header
detection) fixed in the same session.

### T66 — FAX closed-loop: weather chart
The source image is the committed, copyright-free fixture
`tools/synthetic_weatherchart.png` (deterministically generated by
`tools/make_synthetic_weatherchart.py` — regenerate with
`python tools/make_synthetic_weatherchart.py` if it is ever deleted). The real
DWD chart (`tools/Wetterkarte.jpg`, © Deutscher Wetterdienst) is gitignored and
must not be committed; it is only a local fallback.

1. From repo root: `python tools/fax_wav_generator.py`
   (generates all three WAVs into the current directory; the console must print
   `weather chart: using '…/tools/synthetic_weatherchart.png'`)
2. `python tools/fax_decoder_test.py tools/fax_test_wetterkarte.wav`
3. Mode = **Auto-detect headers**, LPM 120, IOC 576 → **Decode**

**Expected result:**
- Decode succeeds (no "No image lines decoded" error)
- Synthetic chart fully rendered, recognisable (concentric isobars, H/T pressure
  markers, coastline strokes, station plots, faint grayscale gradients)
- Status line: `Start line` set (small value), `Stop line` set,
  `Phasing offset` small (~0), `image_height` ≈ 600
- Width ≈ 905 px (IOC-576 derived — narrower than the 1152 px source; expected,
  not a defect)

**Status:** ⬜ OPEN (needs local run)

---

### T67 — FAX closed-loop: geometry/resolution pattern
1. `python tools/fax_decoder_test.py tools/fax_test_pattern.wav`
2. Decode once with **Auto-detect headers**, once with **Skip header detection**

**Expected result:**
- Circle is **round**, centred — NOT an ellipse and NOT a slanted/sheared
  parallelogram (verifies fractional-line-length fix: drift ≤ 0.02 px/line)
- Vertical lines straight (no horizontal shear top-to-bottom)
- Horizontal lines straight; thickness bars (1/2/4/8/16/32 px) individually
  distinguishable down to the resolution limit
- DIAGNOSIS POINTER: if the circle appears as an **ellipse**, LPM/IOC mismatch
  (check both set to 120 / 576); if it appears as a **parallelogram**, the
  line-drift slant has regressed (fractional line bounds in decode_wav)

**Status:** ⬜ OPEN (needs local run)

---

### T68 — FAX closed-loop: text page (slant regression check)
1. `python tools/fax_decoder_test.py tools/fax_test_text.wav`
2. Decode with **Skip header detection** first, then **Auto-detect headers**

**Expected result:**
- Lorem-Ipsum text legible, Arial metric intact
- Skip-header mode: first and last text line start in the **same column**
  (left-margin drift ≈ 0, measured ~0.0124 px/line — no parallelogram)
- Auto-detect mode: top phasing band and trailing black bar are **trimmed**
  (only the clean text block remains) — confirms header start/stop detection
- Status line: `Start line` set, `Stop line` set, `Phasing offset` small

**Status:** ⬜ OPEN (needs local run)

---

### T81 — FAX hardware: WAV-Direkteinspeisung in den TNC (Bargraph-Sync)
Verifiziert den realen TNC-Demodulationspfad — NICHT den Software-Decoder. Die
TNC-getaktete WAV (Mitte 1700 Hz, Shift 1000, schwarz 1200 / weiß 2200) muss am
PK-232 sauberen Mark/Space-Hub am Diskriminator-Bargraph erzeugen.

Vorbereitung:
- `python tools/fax_wav_generator.py --target tnc` (erzeugt *_tnc.wav)
- TNC in FAX-Opmode (`FAX` → `Opmode now FAX`, `OPMODE` → `FAX STBY RCVE`)
- THRESHOLD-Regler voll im Uhrzeigersinn (rechter Anschlag) — sonst kein Slicer-Output
- Audiopegel so einstellen, dass die DCD-LED gerade aufleuchtet

Ablauf:
1. `fax_test_wetterkarte_tnc.wav` direkt in den RADIO-Audioeingang des TNC
   spielen (Loopback/Kabel)
2. 10-Segment-Bargraph (HF-Tuning-Indikator) beobachten
3. Optional `LOCK` eingeben, um den Bilddruck/-empfang ohne Warten auf das
   Phasing zu forcieren

Expected result:
- Bargraph schwingt DEUTLICH zwischen Mark und Space (nicht nur Zittern) im Takt
  der Schwarz/Weiß-Pixel
- TNC erkennt das Phasing-Signal und verlässt STBY RCVE Richtung Empfang
- Bild kommt erkennbar an (mit `LOCK` ggf. horizontal versetzt — via `JUSTIFY n`
  in ½-Zoll-Schritten korrigierbar)

Diagnose bei Fehler:
- Bargraph zittert nur / kein Sync → Tonlage passt nicht: versehentlich die
  SW-WAV (1500/2300, ohne _tnc-Suffix) erwischt, ODER der Audiotreiber resampled
  die 11025-Hz-Datei (LPM verschoben). Mit _tnc-WAV und ohne Resampling testen.
- Zu wenig DCD-Reaktion → Pegel zu niedrig oder THRESHOLD nicht am rechten Anschlag
- Bild invertiert → am TNC `FAXNEG` togglen

KRITISCH: NIE eine SW-WAV (1500/2300) für diesen Test verwenden — die rastet am
TNC nicht ein. Umgekehrt eine *_tnc.wav NICHT in fax_decoder_test.py öffnen.

**Status:** ⬜ OPEN (Hardware-Test ausstehend)

---

### T82 — FAX hardware: vollständiger Live-Bilddecode (Epson → Bild)
Verifiziert den realen Decode-Pfad: $3F-Frames (Epson 9-Pin ESC-L-Druckergrafik)
→ EpsonFaxParser → 8-Zeilen-Bänder → FaxImageWidget.

Vorbereitung:
- python tools/fax_wav_generator.py --target tnc
- FAX-Opmode, FSPEED 2 (120 LPM), ASPECT 2 (IOC 576)

Ablauf:
1. Clear → fax_test_pattern_tnc.wav einspielen → LOCK (Force Receive)
2. Bildaufbau beobachten, dann Stop am Ende
3. fax_test_wetterkarte_tnc.wav analog

Expected result:
- Log zeigt [FAX] line n, Zeilenzähler steigt; KEIN Schrägraster, KEINE
  Vertikalnaht (= Parser ok)
- Testmuster: Kreis RUND (nicht liegend-oval = PIXEL_ASPECT ok), Vertikalbalken
  trennbar, Text „SYNTHETIC WEFAX TEST CHART …" lesbar
- FAXNEG: Umschalten kippt das GANZE Bild gleichmäßig (keine Streifen =
  Polaritäts-Bugfix ok). RXREV ON + FAXNEG ON (oder beide OFF) = korrekte Polarität
- Smoothing-Regler: 0 = scharfe Roh-Dots (Original erhalten); steigend → Dither
  löst sich in Grau auf; Sweet Spot = Körnigkeit weg, dünne Linien/Ziffern noch
  lesbar
- Stop: friert Bild ein, weitere Daten ignoriert; LOCK/Clear nimmt wieder auf

Diagnose bei Fehler:
- Schrägraster/Vertikalnaht → Parser-Regression (Rohbytes als Graustufe)
- Kreis oval → PIXEL_ASPECT-Regression
- Gebänderte Polarität → FAXNEG sendet wieder FN an den TNC (Regression)

**Status:** ⬜ OPEN (Hardware-Test ausstehend)

---

## Open Items Summary

| Priority | Topic | Tests |
|----------|-------|-------|
| High | Packet Connect/Disconnect (2nd station) | T33–T39 |
| High | Packet MHEARD | T41–T42 |
| Medium | Packet toggles/buttons | T43–T51 |
| Medium | PACTOR/AMTOR identity, focus | T52–T58 |
| Low | APRS buffer on mode switch | T65 |
| Medium | FAX closed-loop decode (tools/) — steps written, local run pending | T66–T68 |
| Medium | FAX hardware: WAV→TNC bargraph sync (tnc-WAV direkt) | T81 |
| Medium | FAX hardware: full live image decode (Epson→Bild) | T82 |
| Low | Multi-cycle RTTY colour | T18 |
| Low | Macro full integration | T19–T22 |
| Low | Help Viewer | T27–T28 |
| Medium | CW/Morse TxController (Paket 2a) | T69–T72 |
| Medium | AMTOR TxController (Paket 2b) — T73 zuerst! | T73–T79 |
| Medium | Packet channel model — interactive mock-GUI + hardware re-test (software/mock PASS) | T87–T100, T102, T103 |
| High | UI-channel unproto behaviour — needs real hardware, tool: `hw_check.py t101` | T101 |
| High | USERS while connected / second simultaneous connection — needs real hardware (+ 2nd station for T105) | T104, T105 |
| Medium | PACTOR PTHUFF type mismatch (int vs ON/OFF) — needs real PACTOR hardware, tool: `hw_check.py pthuff` | T110 |
| High | PASSALL button click-through in the running app (Host-Mode-command level PASS via `hw_check.py t111`) — needs real hardware | T111 |
| Medium | VHF→HF Packet MAXFRAME/SLOTTIME carry-over — FAIL confirmed for SLOTTIME, retest MAXFRAME after P18.1/P18.3 fix, tool: `hw_check.py t112` | T112 |
| Medium | SIAM screen shows one assembled result (fix in P18.2, measurement done at T113) — needs real hardware | T114 |
| Medium | MailDrop over Host Mode ($60/$70 data channel) — needs real hardware, tool: `hw_check.py maildrop_host` | T117 |

---

## Serial Capture — Reference Frames

| Frame (hex) | Meaning |
|-------------|---------|
| `01 4F 58 4D 17` | XM — PTT ON / DIDDLE start |
| `01 4F 52 43 17` | RC — switch to RECEIVE |
| `01 20 xx 17` | DATA — one character `xx` to TNC |
| `01 5F 58 58 00 17` | DATA-ACK from TNC |
| `01 40 01 43 4F xx... 17` | CH_CMD ch=1 CO callsign — AX.25 Connect |
| `01 40 01 44 49 17` | CH_CMD ch=1 DI — AX.25 Disconnect |
| `01 3F xx... 17` | Monitor frame ($3F) — APRS/AX.25 received |
| `01 50 xx... 17` | LINK_MSG ($50) — CONNECTED / DISCONNECTED |
| `01 4F 48 4F 4E 17` | HOST OFF — exit Host Mode |
| `01 4F 4D 4E xx 17` | MN — set Monitor level |
| `01 4F 48 42 xx 17` | HB — set HBAUD |
| `01 4F 56 48 xx 17` | VH — VHF ON (Y) or OFF (N) |
| `01 4F 55 4E xx 17` | UN — set UNPROTO path |

---

*Created: 2026-05-01 | Updated: 2026-06-16 (v16) | OE3GAS | PK232PY Project*