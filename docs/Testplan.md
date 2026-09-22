# PK232PY — Test Plan
**Updated: 2026-09-21 — +T110 (P14 solo hardware check tool); links T17/T86, T101, T103 to tools/hw_check.py**
**Previous stand: 2026-09-20 — Packet channel model (ChannelBar) sprint, +T87–T93 (incl. the _make_host_frame() channel-nibble bugfix); +T94–T97 (P9 per-channel TX buffer); +T98–T101 (P10 channel 0 = UI channel); +T102 (link-message button gating bugfix); +T103–T105 (P11 USERS parameter); +T106 (P12 parameter dialog wiring audit); +T107–T109 (P13 upload coverage)**

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
1. VHF Packet, Dest empty → click **Connect**

**Expected result:** Warning dialog "Packet Connect"

**Status:** ✅ PASS (2026-06-19, mock)
**Note:** Warning dialog fires correctly when Dest empty.

---

### T34 — Connect: CO frame sent
1. VHF Packet, Dest = "OE3XYZ-9" → click **Connect**

**Expected result:**
- Connect button pressed (blue)
- Serial: `01 40 01 43 4F ...` (CH_CMD ch=1, CO, callsign bytes)
- Status: **● CALLING**

**Status:** ✅ PASS (2026-06-19, mock)
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
Hardware test against real second station still outstanding.

---

### T36 — DATA frame TX
1. VHF Packet, connected → type text, press Enter

**Expected result:**
- Serial: DATA frame on channel 1 with text content
- Echo appears in RX display (TX yellow)

**Status:** ✅ PASS (2026-06-19, mock)
**Note:** L / R 2 / R 4 / D sent and echoed correctly (TX yellow).
BBS responses appear in RX display.

---

### T37 — Disconnect: DI frame + status pill
1. VHF Packet, connected → click **Disconnect**

**Expected result:**
- Serial: `01 40 01 44 49 17` (CH_CMD ch=1, DI)
- Status pill → **● STBY**

**Status:** ✅ PASS (2026-06-19, mock)
**Note:** Both directions verified:
(a) Disconnect button → $41 DI → ● DISCONNECTED
(b) Remote disconnect via BBS "D" command → ● DISCONNECTED
Hardware test against real second station still outstanding.

---

### T83 — Mock-TNC BBS: Connect-button gating
Prerequisite: `python tools/mock_tnc_bbs.py --trace`

1. Initial: Connect enabled, Disconnect disabled
2. Click **Connect** (Dest: OE1XYZ) → CALLING
3. After CONNECTED: Connect DISABLED (no double CO possible), Disconnect ENABLED
4. Click **Disconnect** → DISCONNECTED
5. Connect ENABLED again + uncheckable, Disconnect DISABLED
6. Re-connect possible

**Expected result:** Button gating correct in every state.

**Status:** ✅ PASS (2026-06-19, mock — commits packet_screen.py + main_window.py)

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
1. Unproto ON → Connect button greyed
2. Connect/CALLING/CONNECTED → Unproto button greyed
3. Unproto OFF (link idle) → Connect re-enabled; link down → Unproto re-enabled

**Status:** ✅ PASS (2026-06-22, code-verified) — `set_link_state()` greys/restores
`btn_unproto` on connected/calling/idle; `_on_packet_unproto()` greys/restores
`btn_connect` (link-busy proxy = `btn_disconnect.isEnabled()`). Mutual exclusion
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
1. Packet screen (Host Mode) — click channel chip 4 in the ChannelBar
2. Enter a Dest callsign → click **Connect**

**Expected result:** CO goes out with CTL=$44 (channel 4), not $41; chip 4
shows the amber "calling" fill immediately.

**Status:** ✅ PASS (2026-09-20, headless — stub `_serial`, see
`_on_packet_connect`/`ChannelBar.set_channel_state`). Interactive mock-GUI
re-click and hardware re-test pending.

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

1. Packet screen (Host Mode via the mock) — select channel 3 in the
   ChannelBar, Dest = OE1XYZ, click **Connect**
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
1. Select channel 3, type text, do not send
2. Turn Unproto on
3. **Expected result:** the `UI` chip is active, the TX window shows the
   Unproto draft (empty at first), Connect and Disconnect are locked
4. Select chip 3 → Unproto turns off, the text from step 1 is back

**Status:** ✅ PASS (2026-09-20, headless — full app against the real
`tools/mock_tnc_bbs.py` `LoopbackTNC`, plus `TestUnprotoUsesChannelZero` in
`test_main_window_packet.py`). Interactive manual click-through and
hardware re-test still open, as with the rest of this sprint's Packet
tests.

### T99 — Connect on channel 0 is rejected
1. Select the `UI` chip, enter a callsign in Dest, press Connect
2. **Expected result:** no `CO` frame goes out, a warning dialog appears,
   the button un-checks

**Status:** ✅ PASS (2026-09-20, headless — full app against the real
`LoopbackTNC` [`_serial.calls`/trace shows no `CO`], plus
`TestConnectRejectedOnChannelZero` in `test_main_window_packet.py`).

### T100 — Monitor traffic in the CH view
1. View set to `CH`, chip 3 active → monitored frames do **not** appear
2. Select the `UI` chip → monitored frames appear
3. View set to `ALL` → monitor traffic appears regardless of the chip

**Status:** ✅ PASS (2026-09-20, headless — `TestUiChannelZero` in
`test_packet_screen.py`: `append_monitor_data()` now shares
`append_channel_data()`'s ALL/CH filter, gated on `UI_CHANNEL`).

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

1. Connect on channel 4
2. Switch to the `UI` chip
3. Trigger a link message for channel 4 (mock)

**Expected result:** Disconnect stays locked, Unproto stays unlocked, chip
4 stays green (ChannelBar itself is a separate, always-on consumer of the
same message and is unaffected). Switching back to chip 4 re-enables
Disconnect.

**Status:** ✅ PASS (2026-09-20, headless — full app against the real
`tools/mock_tnc_bbs.py` `LoopbackTNC`, plus
`TestLinkMessageGatedByVisibleChannel` in `test_main_window_packet.py`).

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

**Status:** 🟡 Partial result (22.09.2026, first run, before the P21
fixes): mailbox prompt confirmed
(`` (AEA PK-232M)  18536 free  (B,E,K,L,R,S) > ``, round brackets, double
spaces — differs from the TRM's `[AEA PK-232M] ... >` example); SysOp
command set confirmed as `B,E,K,L,R,S` only (`H` → `*** What?`, help is
for other users, not the SysOp); `B` confirmed to close the mailbox and
return straight to `cmd:`. **A safety issue in the tool itself** (typed
input after `B` reached the TNC command interpreter, where `K` = CONVERSE)
stopped the run before `S`/`R`/`K`/`L` and the message format could be
exercised — fixed in P21.3. ⬜ Still OPEN: repeat with the fixed tool and
the corrected sequence above to get the real command set, message-list
format, and `S`/`R`/`K` results. Needs real hardware and real operator
time (this is an open-ended protocol measurement, not a quick pass/fail
check). See `docs/HW_Solo_Tests.md`, `docs/P20_MailDrop_Measure_Spec.md`
and `docs/P21_MailDrop_Recorder_Fix_Spec.md`.

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
| Medium | MailDrop protocol measurement — FAIL-stopped by a tool safety bug on the first run (fixed P21.3), repeat with the fixed tool and corrected sequence, needs real hardware and operator time, tool: `hw_check.py maildrop` | T116 |

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