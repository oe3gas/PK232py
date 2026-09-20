# PK232PY — Test Plan
**Updated: 2026-09-20 — Packet channel model (ChannelBar) sprint, +T87–T92**
**Previous stand: 2026-06-16 (v16) — Paket 2a/2b TxController (Morse + AMTOR), T69–T79; FAX closed-loop T66–T68; clear buttons; +T81 (FAX hardware, WAV→TNC); +T82 (FAX hardware, live Epson decode); +T33–T37 PASS & +T83–T84 (mock-TNC BBS sprint)**

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
| **2026-09-20** | `packet_screen.py`, `main_window.py`, `packet_hf.py` | Packet channel model: `ChannelBar` (10 chips), `cb_dest` history combo, ALL/CH RX filter, Capture, MHEARD channel column, `HFPacketMode.on_channel_state`; +T87–T92 |

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
The PASSALL toggle currently sends `build_command(b'PS', …)`. A Host Mode
command-table reading suggests `PS` = PASS and **`PX` = PASSALL** — i.e. the
toggle might need `PX`, not `PS`. This is NOT confirmed: AEA may map PASSALL to
`PS` regardless. **No code change without hardware verification** — `b'PS'` is
left in place until a real TNC confirms which byte toggles PASSALL.

1. HF/VHF Packet (Host Mode) → toggle **PASSALL** ON, then OFF
2. Observe on a real PK-232 whether PASSALL actually engages (receive bad-CRC
   frames) with `PS`; if not, retry with `PX`.

**Expected result:** the byte that actually toggles PASSALL is identified;
`main_window._wire_packet_buttons()` toggle_map is set to it.

**Status:** ⬜ OPEN (requires hardware verification — see CLAUDE.md mnemonic note)

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

### T45 — HBAUD change
**Status:** ✅ PASS (2026-06-22, frame-verified) — `combo_hbaud` change →
`_on_packet_hbaud_changed()` → `HB <value>` (mnemonic `HB`).

### T46 — Monitor level change
**Status:** ✅ PASS (2026-06-22, frame-verified) — `combo_monitor` (0–6) change →
`_on_packet_monitor_changed()` → `MN <level>` (mnemonic `MN`).

### T47 — MailDrop button
**Status:** ✅ PASS (2026-06-22, frame-verified) — `btn_maildrop` →
`_on_packet_maildrop()` → `MI` (mnemonic `MI`).

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
end-to-end through a synthetic `LINK_MSG` frame into `ChannelBar`).

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
| Medium | Packet channel model — interactive mock-GUI + hardware re-test (software/mock PASS) | T87–T92 |

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