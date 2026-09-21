# PK232PY — Development Backlog

**Last updated:** 2026-09-20 (Packet channel model sprint)
**Current version:** v0.1 (development)

---

## Priority 1 — Next implementation sprint

### `SignalMode.handle_frame()` reports any CMD_RESP as a SIAM result — open

Found 21.09.2026 (P16.3, investigation only — no code changed) while
checking the codebase for the same class of bug as T86's stale-`HP\x00`
frame (a Host Mode response mistaken for the answer to a different query
because it was matched by arrival order/type, not by mnemonic — see the
CLAUDE.md Host Mode gotcha).

- `src/pk232py/modes/signal_analysis.py::SignalMode.handle_frame()`
  (~lines 97–104): on any `FrameKind.CMD_RESP` frame, if
  `frame.text.strip()` is non-empty and does not end in `\x00`, it is
  logged and passed to `on_result()` as a SIAM signal-identification
  string — **without checking `frame.mnemonic`/`frame.data` against
  anything Signal mode itself queried.**
- `ModeManager` forwards every `CMD_RESP` to whichever mode is currently
  active (`mode_manager.py::_handle_cmd_resp()` → `_active_mode.handle_frame()`),
  so any stray CMD_RESP arriving while Signal/SIAM is the active mode — a
  delayed `HP\x00` HPOLL flush from Host Mode entry, an ACK/NAK for some
  other in-flight command, or an attribute-query echo like `PXN` — gets
  surfaced as a bogus SIAM result. The `not text.endswith('\x00')` check
  happens to filter out plain ACK frames ending in the `$00` OK byte (like
  `HP\x00`) but nothing else — a response such as `PXN` would pass through
  untouched.
- Fix once confirmed: verify the frame is actually a SIAM analysis result
  (distinguish it from other CMD_RESP frames — check with the TRM whether
  SIAM results carry their own recognisable prefix) before calling
  `on_result()`. Not fixed here — P16.3 was investigation only.

**Landmine, not yet a live bug:** `mode_manager.py::_handle_cmd_resp()`
(~lines 263–285) only logs "CMD ACK"/"CMD NAK" per CMD_RESP today — the
opmode-switch sequence itself is timer-based (`_ACTIVATE_DELAY_MS`, 300 ms),
not gated on receiving a specific ACK, so this logging cannot misdirect
control flow yet. The module's own docstring says a proper ACK-wait state
machine is planned for v0.2 — when that lands, it must filter by
`frame.mnemonic` against the mnemonic it actually sent, not take the next/
first CMD_RESP, or it will inherit the same T86-class bug.

**Confirmed safe (P16.3):** the MHEARD poll (`packet_hf.py::_handle_cmd_resp()`,
`main_window.py::_on_packet_mheard()`) already filters every CMD_RESP on
`frame.mnemonic == b'MH'` before treating it as an MHEARD line — a stray
frame in that window is dropped, not misattributed.

### `_make_host_frame()` misclassifies LINK_STATUS ($40–$4E) as CMD_RESP — open

Discovered 2026-09-20 while fixing the channel-nibble bug (see the
"Fix channel nibble extraction for 4x and 5x frames" commit and the
Completed block below) — **not fixed in that commit**, deliberately left
alone since it is a different bug with a different blast radius:

- `_make_host_frame()`'s `elif` chain (`serial_manager.py`) has explicit
  branches for `$4F` (CMD_RESP), `$3F` (RX_MONITOR), `$30–$39` (RX_DATA),
  `$5F` (STATUS_ERR) and `$50–$5E` (LINK_MSG) — but **none for `$40–$4E`**
  (LINK_STATUS, "response to a CONNECT query" per `HFPacketMode.handle_frame()`
  §"LINK_STATUS"). Those frames fall through to the `else` branch and are
  built as `FrameKind.CMD_RESP` instead of `FrameKind.LINK_STATUS`.
- Impact: `HFPacketMode.handle_frame()` routes them into `_handle_cmd_resp()`
  (MHEARD-line parsing) instead of the (currently log-only)
  `FrameKind.LINK_STATUS` branch, and `ModeManager.on_frame()` / mode-switch
  ACK detection may see a CMD_RESP where it does not expect one.
- **Possibly the same root cause as** the existing "Known issues" entry
  `HFPacket/VHFPacket: CMD_RESP reaches mode | Minor | handle_frame() logs
  "unhandled frame" for ACKs — harmless" — that note is about general `$4F`
  ACKs, not `$40–$4E` specifically, so it may be a related-but-distinct
  symptom rather than the identical bug. **Needs a hardware test** (or at
  least a byte-level trace of a real CONNECT-query LINK_STATUS reply) to
  confirm before touching the elif chain — do not guess-fix this one.

### Tech debt — two parallel Host Mode frame decoders

`comm/frame.py::FrameParser` (used by `tools/mock_tnc_bbs.py` and the
Host Mode subprocess path) and `comm/serial_manager.py::_make_host_frame()`
(used by `SerialManager`'s reader thread — the actual runtime path for a
connected TNC) are two independent re-implementations of the same
CTL-byte-to-`FrameKind`/channel mapping, with different bugs (see the
channel-nibble fix above, which only touched one of the two). Consolidate
onto one decoder in a later session — out of scope for the channel-model
sprint (hard constraint: no serial-layer changes beyond the one-line
channel-nibble fix).

### Packet — Channel model (ChannelBar) — ✅ DONE (2026-09-20, software/headless)

- ✅ `ChannelBar` (10 chips, free/calling/connected state + partner callsign,
  Ctrl+Up/Down stepping) replaces the implicit "always channel 1" model.
  `PacketBaseScreen` rows regrouped (header/identity/connect/unproto/tool/
  options/channel-bar/RX/TX/macro); `le_dest` → `cb_dest` history combo
  (`dest_callsign()`/`set_dest_callsign()`/`add_dest_history()`).
- ✅ `HFPacketMode.on_channel_state(channel, state, partner)` — derives
  per-channel state from the same $5x link messages `on_link_message`
  already parses (`_extract_partner()` best-effort callsign extraction).
  `VHFPacketMode` inherits it unchanged (no override to add).
- ✅ MainWindow: `_on_packet_connect`/`_on_packet_disconnect`/
  `_on_packet_tx_enter` now read `screen.current_channel()`/
  `dest_callsign()` instead of hardcoding channel 1 / `le_dest.text()` —
  verified end-to-end headless against a stub `_serial` (channel 4, incl. a
  simulated CONNECTED reply and disconnect).
- ✅ RX filtering: `append_channel_data()`/`append_monitor_data()`/
  `set_view_all()` — ALL/CH filter applied at append time, no buffer
  rebuild on channel switch (deliberate v0.1 simplification).
- ✅ Capture (`btn_capture` → `_on_packet_capture`): records every channel's
  traffic to a file regardless of the ALL/CH view.
- ✅ MHEARD channel column + amber "connected" colouring
  (`set_channel_map()`), double-click to fill Dest or switch channel.
- **New, unverified-mnemonic placeholders** (built + wired, no frame sent —
  see "Offene Mnemonics" below): CONPERM, MAILDROP (options-row toggle,
  distinct from the working MailDrop-login button), MDMON, LITE.
- **Open (Priority 2):** interactive mock-GUI re-click (`tools/
  mock_tnc_bbs.py`) and hardware re-test for T87–T92 (Testplan.md); Connect
  dialog ("…" next to Dest) has no persistence across sessions yet; Files/
  QSO Log stay disabled placeholders; Band indicator in the header is
  read-only in v0.1 (the screen cannot itself trigger a ModeManager switch).

### Offene Mnemonics (unverified — no TRM / pk232_mnemonic_table.txt
available in this session; per the "never guess a mnemonic" rule these send
NOTHING to the TNC yet)

| Function | Candidate | Status |
|---|---|---|
| CONPERM | `CY` | Button built, `# TODO mnemonic unverified`, no frame sent. |
| MAILDROP on/off (options row) | unresolved | Button built, no frame sent. Distinct from the working `btn_maildrop` MDCHECK-login button (mnemonic `MI`, already T47-verified) — do not conflate the two. |
| MDMON | unresolved | Button built, no frame sent. |
| LITE | unresolved | Button built, no frame sent. |
| MailDrop-Login / MID | `MI` (both) | Pre-existing, documented conflict — `MI` used for both MDCHECK login and the MID (Morse ID) toggle. Behaviour intentionally left unchanged; see CLAUDE.md "Known bug" history and the code comment in `packet_screen.py`. |

### Packet — Connect/Disconnect & MHEARD

- ✅ Connect/Disconnect flow (T33–T37) **software-verified via the mock TNC**
  (`tools/mock_tnc_bbs.py`) — the mock replaces the second AX.25 station for
  software tests. Connect/CONNECTED/DATA/Disconnect logic confirmed.
- ✅ Toggle/button tests (T38, T39, T43–T51) **frame/code-verified** — see the
  Completed block "2026-06-22 — Sprint T38–T51".
- ✅ MHEARD Refresh/Clear (T41/T42) **mock end-to-end verified** — see the
  Completed block "2026-06-22 — Sprint T41/T42 MHEARD".
- **Open:** T35/T37 hardware re-test: real AX.25 second station (the mock
  proves the software logic; on-air behaviour still needs a real TNC + station)
- **Open:** T38/T39 interactive mock GUI re-click + hardware re-test
  (frame-level PASS, live UI-click verification still pending)
- **Open:** T41/T42 live-GUI Refresh click + hardware re-test (real station —
  the mock proves the MH0..MH17 poll/parse logic)
- **Open (v0.2):** MHEARD HBAUD-110 mid-poll consistency workaround
  (TRM §4.11 — deliberately skipped in v0.1; see Priority 2)
- **Open:** T101 (P10) — hardware check whether v7.1 actually transmits text
  sent in over `$20` on the unconnected channel 0 as a UI frame along the
  configured UNPROTO path. Standard AX.25 behaviour, but not documented for
  v7.1's Host Mode; the whole "channel 0 = UI/unproto channel" assignment
  (`docs/P10_UI_Channel_Spec.md`) rests on this. If it turns out not to hold,
  log the error frame and record the finding in CLAUDE.md before relying on
  it further.
- **Open:** T104 (P11) — hardware check whether the TNC accepts a `USERS`
  change while a connection is up, or rejects it with error `$09` "not
  while connected" (TRM 4.3). If rejected, skip the `USERS` upload while
  connected instead of raising an error; record the result in CLAUDE.md.
- **Open:** T105 (P11) — the actual proof that the multi-channel model
  holds up: raise `USERS` to 2+, connect on channel 1, have a second
  station connect on channel 2, confirm both chips go green with the
  right callsign, data routes to the right channel view, and TX buffers
  (P9) stay separate. Needs a real PK-232 **and** a second AX.25 station.
- **Open:** T108 (P13) — access filters on real hardware: `CFROM YES
  <station>`, confirm that station's connect is accepted and a different
  station's is rejected, then reset to `CFROM ALL`. Needs a real PK-232
  **and** a second AX.25 station.

*Note: monitoring on 144.800 MHz has replaced most RX-only tests.
The T35/T37 + T38/T39 + T41/T42 + T101 + T104 hardware re-tests still need
a real station (T101/T104 need no second station, just a real PK-232);
T105 and T108 additionally need a second AX.25 station.*

### Beta Release (v0.1-beta) — GitHub distribution
- [ ] Windows build reproducible (decide: Nuitka onefile vs PyInstaller --onedir)
- [ ] GitHub Actions build workflow, triggered on release tags (v*)
- [ ] GitHub Release with attached Windows binary
- [ ] SHA-256 checksum published alongside the binary
- [ ] Unsigned-EXE tester note (SmartScreen/Defender workaround in README)
- [ ] Issue template for testers (firmware, COM/adapter, log excerpt)
- [ ] LICENSE / CONTRIBUTING.md / CHANGELOG.md present and referenced by README
- [ ] README "Download & Run the Beta" section for non-developers

---

## Priority 2 — Improvements

### Parameter dialogs — widgets with no config field yet (P12 audit, 2026-09-20)

Found by `test_param_dialogs_roundtrip.py` (Test A) — each one is a widget
the dialog builds and (for the `set_values`/`get_values` dialogs) already
reads/writes internally, but that has no corresponding field in the
project's own config dataclasses, so it never reaches `AppConfig`/the INI
file. Per the "never guess" rule these are **not** wired to a newly invented
field — logged here for a future session to decide whether each one is
worth adding to config, and each is listed in `UNWIRED_OK` in the test file
with the reason `"no config field yet — see Backlog"` so the audit stays
green in the meantime.

| Dialog | Widgets |
|--------|---------|
| HF Packet | `MDIGI`, `MPROTO`, `MSTAMP`, `PASSALL`, `BBSMSGS`, `FULLDP` flags; `MBX` (`8BITCONV`, `HID`, `MBELL` flags and the `CFROM`/`DFROM`/`MFROM`/`MTO` filters were wired in P13.3, 2026-09-20 — see the "Config: packet access filters and flags" / "HF packet params dialog: wire access filters and flags" commits) |
| PACTOR | `8BITCONV`, `AFILTER`, `XGATEWAY` flags |
| AMTOR/NAVTEX/TDM | `AAB`, `CODE`, `ERRCHAR`, `GUSERS`, `MID`, `MWEIGHT`, `UBIT`, `NAVMSG`, `NAVSTN`; `AFILTER`, `MARSDISP` flags |
| BAUDOT/ASCII/CW | `ACRTTY`, `ATXRTTY`, `AUDELAY`, `ERRCHAR`, `UBIT`; `AFILTER`, `CRADD`, `MARSDISP`, `RFRAME`, `WRU` flags |
| Misc | `BITINV`, `CWID`, `HEREIS`, `RECEIVE`, `REDISPLA`, `TIME`, `MODEM` |
| MailDrop | `LASTMSG`, `MDPROMPT`, `TMPROMPT` |

Also read-only TNC-query fields (`QHPACKET`, `QVPACKET`, `QPTOR`, `QTDM`,
`QTOR`, `QMORSE`, `QRTTY`, `QWIDE`, `BRIGHT`, `BARGRAPH`, `THRESHOLD`) —
these are deliberately never settable, not a gap, listed in `UNWIRED_OK`
with reason `"read-only, TNC query result"`.

**Not covered by Test A at all:** `MailDropParamsDialog._te_mtext` is a
`QTextEdit`, outside the five widget types
(`QSpinBox`/`QDoubleSpinBox`/`QCheckBox`/`QLineEdit`/`QComboBox`) the audit
scans — it is correctly wired (verified by Test B/C), just not exercised by
Test A's mechanical widget walk.

### Upload coverage — PACTOR/AMTOR/Baudot/Misc (P13 Test D, 2026-09-20)

`test_param_dialogs_roundtrip.py::test_field_reaches_upload` (Test D) found
21 config fields that are correctly wired to their dialog AND survive an
INI round trip, but are never sent to the TNC by
`ParamsUploader._build_commands()` — independent of the three HF Packet
findings (`resptime`/`txsmt`/`aerpack`) fixed in this sprint. Each is listed
in `UPLOAD_EXEMPT` with `"not yet audited for upload — see Backlog"`, since
verifying 20 more command names against the TRM / `pk232_mnemonic_table.txt`
(neither fully available in this session for every field) is its own
follow-up, not something to guess at:

| Section | Fields |
|---------|--------|
| PACTOR | `arqtmo`, `adelay`, `ptdown`, `ptup`, `ptsum`, `pttries`, `ptsend`, `ptround`, `xmitok` |
| AMTOR/NAVTEX/TDM | `xlength`, `srxall`, `usos`, `wideshft` |
| BAUDOT/ASCII/CW | `xlength`, `xbaud`, `usos`, `wideshft`, `xmitok` |
| Misc | `mark`, `space` |

`BaudotConfig.mid` is NOT in this list — it is sent live via
`main_window._on_morse_mid_changed()` while operating, not part of the
startup upload, so there is nothing to fix.

**Also found, separately from HF's `aerpack`/`txsmt`:** `PACTORConfig.pthuff`
is an `int` (compression level, dialog range 0–10) but
`ParamsUploader._build_commands()` sends it with `self._bool(...)`, i.e. as
an ON/OFF flag — Test D does not catch this because *some* change in value
still changes the ON/OFF output at the zero/non-zero boundary. Needs the
TRM's actual `PTHUFF` command syntax before it can be fixed correctly.

**Confirmed on real hardware, 21.09.2026 (Testplan T110, FAIL):** the TNC
reports `PTHUFF` as numeric (`PTHuff 0`), not ON/OFF. It accepts `PTHUFF
OFF` without a `?` error and just leaves the value at `0` — it does not
reject the wrong type, so the mismatch was invisible until this test read
the value back. `PTHUFF ON` is still untested. Fix: change
`PACTORConfig.pthuff` to a number and make `ParamsUploader` send it as one,
using the real value range from the manual — do not guess the range.

**MYALTCAL truncation (found 21.09.2026, same hardware run):** sending
`MYALTCAL OE3GAS` came back as `MYALTcal now OGAS` — the TNC silently
truncated it to 4 characters. `MYALTCAL` is a 4-character AMTOR SELCAL, not
a callsign; the config field and its dialog should validate/format it as
one instead of accepting a full callsign that then gets mangled on upload.

**VHF/HF parameter values — corrected 21.09.2026 (P16):** the P15 note here
claimed the upload sent HF values (`PACLEN 128`, `MAXFRAME 4`, `FRACK 4`)
while VHF was selected. That reading was wrong — the TNC was at **factory
defaults** for that whole run (see the CLAUDE.md hardware note, RAM buffer
battery), so those numbers were the stock AEA defaults, not proof of an
HF-values-on-VHF bug. The suspected gap, derived from the code and NOT yet
measured: `VHFPacketMode` sends `MX 4` + `SL 10` on activation, but leaving
VHF for HF Packet only sends `VH N` + `HB 300` + `MN Y`
(`HFPacketMode.get_init_frames()`) — no `MAXFRAME`/`SLOTTIME` reset. So HF
Packet could keep running with VHF's `MAXFRAME 4` / `SLOTTIME 10` after a
VHF→HF switch instead of its own values. Verify: activate VHF, switch back
to HF, query `MAXFRAME` and `SLOTTIME` in the terminal (Testplan T111).
Needs its own package to fix the PR/Packet parameter module once confirmed
— not done as part of P15/P16 (query-only hardware checks, no
`src/pk232py/` parameter-module change).

**MTEXT overwritten by config defaults on init (found 21.09.2026, same
hardware run):** the parameter upload sent the two-line `MTEXT` welcome
message from the saved config even where the TNC already had its own text
set on the device. Open question, not yet a confirmed bug: should the
uploader skip sending default/empty text fields at all, so a station's own
`MTEXT` (and similar free-text parameters) survives an app-driven init
unless the operator has explicitly set one in the dialog?

**Operator note (P16, 21.09.2026):** check/replace the PK-232's RAM buffer
battery — the TNC came up at factory defaults for the whole 21.09.2026
hardware run (`MYCALL PK232`, `EXPERT OFF`, `PACLEN 128`, `MAXFRAME 4`,
`FRACK 4`, stock `MTEXT`). Power the TNC off and back on, then query
`MYCALL` in the terminal: reading back `PK232` (the factory value, not a
real callsign) means the configuration was lost, not just unusual.

### Runtime parameter upload in Host Mode

Parameter dialogs only ever affect the *next* initialisation
(`ParamsUploader` runs solely in verbose mode, before Host Mode) — see the
"MainWindow: parameter dialogs report when changes reach the TNC" commit,
2026-09-20. Whether changes should also be pushable into an *already
running* Host Mode session via the equivalent Host Mode mnemonics is an
open design question, not started.

### Packet — v0.2 follow-ups from the channel-model sprint

| Item | Notes |
|------|-------|
| Connect-dialog persistence | The "…" advanced-connect dialog (channel + digipeater path) does not remember its last values across sessions. |
| File transfer (`btn_files`) | Disabled placeholder in v0.1 — no protocol implementation yet. |
| QSO-Log integration (`btn_qsolog`) | Disabled placeholder in v0.1 — depends on the planned SQLite QSO log (see Priority 3). |
| MailDrop management dialog | The tool-row `btn_maildrop` only sends MDCHECK login (`MI`, T47-verified); browsing/composing MailDrop messages is not implemented. |
| CONPERM / MAILDROP / MDMON / LITE mnemonics | Confirm against the TRM / `pk232_mnemonic_table.txt` (neither was available in this session) before wiring real frames. |
| Interactive mock-GUI + hardware re-test | T87–T92 (Testplan.md) are software/headless-verified only. |

### APRS — Phase 2

| Item | Notes |
|------|-------|
| MHEARD panel: show APRS stations | Populate from received Mic-E + Position frames |
| Beacon TX | UNPROTO APRS VIA WIDE1-1,WIDE2-1; periodic timer |
| Beacon config UI | Position (lat/lon from INI), symbol, comment, interval |
| Mic-E lon decode verify | Test with west-of-0° and lon > 100° stations |

### MHEARD — HBAUD-110 mid-poll consistency workaround (v0.2)

TRM §4.11 CAUTION: if a Packet frame arrives while the MHEARD list is being
polled (`MH0`..`MH17`), the returned entries can become garbled/inconsistent.
TRM's suggested fix: set `HBAUD 110` before the poll and restore the previous
HBAUD afterwards. Deliberately **not** implemented in v0.1 (the save/restore +
modem re-key adds state-machine complexity for a rare race). Revisit for v0.2
once the basic MHEARD flow is hardware-confirmed.

### FAX closed-loop test tooling — formalise tests

- `tools/fax_wav_generator.py` + `tools/fax_decoder_test.py` provide a
  closed-loop WEFAX test path (generator → WAV → decoder). Working.
- **Open:** formal test cases T66–T68 (FAX closed-loop decode for
  weather/pattern/text) still to be added to `Testplan.md`.
- **Open:** `make_weather_image()` — the real weather-chart path is not
  resolvable locally; `WEATHER_IMAGE_CANDIDATES` does not match the actual
  file (e.g. `tools/Wetterkarte.jpg`), so it falls back to
  `wetterkarte_decoded.png`. Extend the candidate list.

### Testing tools (dev-only)

- `mock_tnc_bbs.py`: dev-only mock TNC + mini-BBS for Packet connected-mode
  tests (T33–T37, T83–T84) with no real TNC, radio or second station.
  Start: `python tools/mock_tnc_bbs.py [--trace]`.

### TxController — CTRL+D EOT (Status nach Paket 2a/2b)

**Paket 1 — Umbenennung (erledigt, cc2adff):**
`BaudotTxController` → `TxController`, Datei `tx_controller.py`,
Attribut `self._tx_ctrl`. Neue Methode `set_mspeed_ms(ms)` für Modes
ohne sinnvolle Baudrate.

**Paket 2a — CW/Morse (erledigt, 437e8a1):**
`morse_screen.py`: `tx_input` auf `TxInputWidget` umgestellt.
`[^D]` EOT → RC (wie Baudot). ACK-getaktet, `_MORSE_TXCTRL_MS = 50`.
Hardware-Tests T69–T72 ausstehend.

**Paket 2b — AMTOR (erledigt, 8087564):**
`amtor_screen.py`: `tx_input` auf `TxInputWidget` umgestellt.
TX-Aktivierung: KEIN btn_send / XM-Frame. CONNECTED-Link-Message →
`on_send_start()` in `_make_link_handler()`. ARQ-EOT → PTOVER `\x1A`
(Ctrl-Z, eingebettet im Datenstrom, wartet auf Puffer-leer). FEC-EOT
→ `on_send_stop()`. ARQ/FEC-Unterscheidung via `btn_fec.isChecked()`,
NIE via `mode.name`. `_AMTOR_TXCTRL_MS = 50`.
Hardware-Tests T73–T79 ausstehend (T73 zuerst!).
CRITICAL CAVEAT: `_make_link_handler()` triggert auf "connected" im
Link-Message-Text. Falls der TNC anderen Text schickt → Handler anpassen.

**Paket 3 — Stop Sending (✅ DONE 2026-06-22, software/mock):**
Kein neuer "Stop TX"-Button nötig — die vorhandenen Pfade decken alle Modes ab:
- Baudot/ASCII/Morse → `RC` (RECEIVE-Button **und** Clear TX).
- AMTOR ARQ/FEC → `AM` (nur Clear TX — AMTOR hat keinen RECEIVE-Button;
  ARQ-TX ist CONNECTED-getriggert).
- Packet → kein Stop-Cmd (frame-basiert). PACTOR → kein Stop-Cmd (außerhalb
  Host Mode). By design bestätigt.
- **Bugfix:** `_on_clear_tx()` sendete `AM` nicht für AMTOR, weil `_send_active`
  nie gesetzt wird (nur `_on_screen_send(True)` setzt es — den SEND-Button-Pfad,
  den AMTOR nicht hat). Fix: `AM` für AMTOR ARQ/FEC unconditional; der
  `_send_active`-Guard bleibt nur für die Button-Modes.
- T17 PASS (Clear-TX-Pfad), T85 neu (RECEIVE-Button-Pfad) — beide software/mock.
  Hardware-Verifikation (AMTOR `AM`-Flush, Morse `RC`-Regression) ausstehend.
- **TxController-Zyklus Paket 1–3 abgeschlossen.**

### Help system — ✅ DONE (2026-06-22 — Help-System-Sprint)
- `help_viewer.py` + `HelpViewer` + `show_help()` + `HELP_TOPICS`: ✅ complete
  (all modes + common topics, default `index`, internal topic-link navigation).
- `help_index.md` (top-level Contents page): ✅ created, approved.
- `help_amtor.md`: ✅ CC re-authored — **proof-read pending** (CC version vs.
  approved chat version).
- `help_baudot/ascii/morse/pactor/packet/navtex/fax/signal.md`: ✅ all created,
  approved (OE3GAS review 2026-06-22).
- Help button (`?`) on all 10 screens: ✅ `make_help_button()` in
  `opmode_rtty_base.py`.
- Help → Contents (F1) in the main menu: ✅
- Internal topic-link handler (`_on_link_clicked`): ✅
- APRS on HF Packet screen: ✅ `APRS_CAPABLE = True` in `HFPacketScreen`.
- **Bugfix-Sprint 2026-06-23 — all closed:**
  - ❌→✅ Dead `controls` anchor: `help_controls.md` created,
    `HELP_TOPICS["controls"]` re-pointed at it (was the dead
    `help_baudot.md#control-characters`).
  - ⚠️→✅ Missing tooltips: `btn_wordout` (Morse), `btn_hold` +
    `btn_pactor_listen` (AMTOR).
  - ⚠️→✅ Status-bar tooltips: Port / Baud / Mode / UTC.
  - ⚠️→✅ Dead-code `TNCConfigDialog`: `dialogs/tnc_config.py` deleted,
    `dialogs/__init__.py` + `check_repo.sh` references cleaned.
- **Content correction (done in the same sprint):** `help_controls.md` lists
  ONLY `[^D]` (Ctrl-D) and `[^T:n]` (Ctrl-T) — the only typeable TX control
  markers. Ctrl-E (WRU) / Ctrl-B (AAB) were dropped from the draft: they do NOT
  exist as TX control characters in PK232PY, only as TNC parameters
  (auto-answerback) in `params_baudot` / `params_amtor`.
- **New cleanup item (not Beta-critical):**
  - 🧹 `main_window.py:4170–4191`: appended §10 corruption artefact — a
    mangled `tnc_config_dialog.py` fragment (copyright + module docstring with
    mojibake), a functionless no-op string. No duplicate `class` def, no defect.
    Remove the lines when convenient (one commit).
- **Open (v0.2, unchanged):**
  - `help_amtor.md` proof-read (CC re-authored vs. approved chat version).
  - Keyboard Shortcuts / Macros still anchors in `help_baudot.md` — own
    `help_shortcuts.md` / `help_macros.md` (controls already split out).
  - Add Help buttons to Params / Config / Appearance dialogs.
  - Context-sensitive F1 (topic = active screen instead of always `index`).
  - Getting-Started first-run dialog; Verbose-terminal help; `QWhatsThis`
    (right-click); tidy the unused `rbaud` anchor.

### TX_STATE_MACHINE.md §8 — Control Characters update
- Update §8 table: `[^T:n]` als implemented eintragen
- `[^S]` aus Planned entfernen (entschieden: nicht implementieren)
- Sentinel-Encoding dokumentieren: `\x1b` + str(n)
- Backspace-Handling (dict-basiert, variable Länge) dokumentieren

### Tooltip system — ✅ DONE (2026-06-22)
- `tooltips.py`: global `TOOLTIPS` (by attribute name) + per-class
  `SCREEN_TOOLTIPS` overrides; `apply_tooltips(widget)` applies global then
  class-specific. Wired into all 10 screens (RttyBaseScreen covers Baudot+ASCII).
- PACTOR inline tooltips migrated + removed.
- Name collisions resolved via SCREEN_TOOLTIPS (btn_connect AX.25↔PACTOR,
  btn_rxrev RTTY↔FAX, btn_lock Morse↔FAX, btn_stby AMTOR↔PACTOR,
  btn_clear FAX image↔MHEARD list).
- **Done (21.09.2026, P16):** T86 PASSALL mnemonic `PS` vs `PX` — hardware
  verification. Per the TRM mnemonic table (4.2.2), `PS` = PASS (a masking
  character, not a toggle) and `PX` = PASSALL. `python tools/hw_check.py
  --port COM3 t17` (P14/P15/P16; query-only, no on-air observation needed —
  see `docs/HW_Solo_Tests.md`). Two invalid runs before the real result:
  the first queried `PX`/`PS` in verbose mode, where two-letter mnemonics
  do not exist (`?What?` for both, fixed in P15 to query Host Mode); the
  second (still 21.09.2026) came back INCONCLUSIVE because a stale `HP\x00`
  poll-ack from Host Mode entry was mistaken for the PX answer (fixed in
  P16 — responses are now matched by mnemonic prefix, not arrival order,
  see the Host Mode gotcha in CLAUDE.md). Third run: raw frames `PXN` (PX)
  and `PS$16` (PS) confirm `PX` = PASSALL, matching the app's toggle after
  the P16 fix. See the "Known bug — fixed (2026-06-22)" section's
  21.09.2026 correction note above.

### MSPEED from TNC config
- Auto-set `TxController.set_mspeed()` / `set_mspeed_ms()` from `PK232.INI` MSPEED
  parameter on Host Mode activation (currently hardcoded to 50 Baud default)
- Config dialog already has MSPEED field for Morse — extend to Baudot/ASCII

### Macro control characters in dialog
- `MacroTextEdit` supports CTRL+D and CTRL+T:n
- Verify CTRL+T:n dialog works correctly inside MacroEditDialog

### T18 — Multi-cycle colour test
- Formal test: 3x SEND→RECEIVE→SEND without macros
- Verify no colour drift after each cycle

### AMTOR Dest (le_dest) Autofill
- AMTOR le_dest (Ziel-SELCAL) is editable but not pre-filled
- Consider populating from last used callsign or history list

---

## Priority 3 — Future / v0.2+

### ASCII RTTY — full TX/RX integration
- Same TxController integration as Baudot
- Currently wired but untested

### AMTOR ARQ TX integration — ✅ Erledigt (Paket 2b, 8087564)
AMTOR nutzt TxController. TX startet bei ARQ CONNECTED
(kein btn_send, kein XM-Frame — TNC managed 100 Bd ARQ timing).

### PACTOR I TX integration
- Similar to AMTOR

### QSO Log
- SQLite-based log (`log/` directory already planned)

### MailDrop
- TNC mailbox functionality (`maildrop/` directory planned)

---

## Completed (2026-09-20 — Packet channel model / ChannelBar sprint)

| Item | Notes |
|------|-------|
| `ChannelBar` (`packet_screen.py`) | 10 chips (0–9), free/calling/connected state + partner callsign, amber 2px border on the current channel, Ctrl+Up/Down stepping. `channel_map()` feeds `MheardPanel.set_channel_map()`. |
| `PacketBaseScreen` row regroup | header (title/band indicator/param hint/UTC) → identity → connect → unproto → tool row → hidden options row → ChannelBar → RX → TX+side buttons → macros; new status bar (channel/partner/capture/RX size/band). |
| `cb_dest` | Editable QComboBox with a 10-entry history, replaces `le_dest`; `dest_callsign()`/`set_dest_callsign()`/`add_dest_history()`. `PactorScreen.le_dest` untouched. |
| `append_channel_data()` / `append_monitor_data()` / `set_view_all()` | ALL/CH RX filter applied at append time — switching channel or view does NOT rebuild/redraw history (v0.1 decision). Monitor frames are never filtered (not channel-scoped). |
| `MheardPanel` channel column | `set_channel_map()`, amber colouring for connected stations, double-click → `connect_requested`/`channel_requested` (wired locally in `PacketBaseScreen.__init__`, no MainWindow round-trip needed — pure UI). |
| `HFPacketMode.on_channel_state` | New callback, second consumer of the existing $5x `on_link_message` frames; `_extract_partner()` best-effort callsign parsing. `VHFPacketMode` inherits unchanged. |
| MainWindow channel routing | `_on_packet_connect`/`_on_packet_disconnect`/`_on_packet_tx_enter` read `screen.current_channel()`/`dest_callsign()` instead of hardcoding channel 1 / `le_dest.text()`. |
| Capture (`btn_capture`) | `_on_packet_capture()` opens a file via `QFileDialog`, `_packet_capture_write()` records every channel's RX/TX + monitor traffic regardless of the ALL/CH view. |
| PacketConnectDialog | "…" button next to Dest — pick channel + optional digipeater path (no persistence yet, Priority 2). |
| Hold TX (`btn_hold_tx`) | Pure UI: while ON, Enter inserts a newline instead of sending — lets the user compose a multi-line message (Packet has no TxController/[^D] EOT concept). |
| Band indicator (`btn_band`) | Read-only in v0.1 — the screen cannot itself trigger a ModeManager mode switch; the real HF↔VHF switch stays on the opmode selector. |
| CONPERM / MAILDROP / MDMON / LITE | Built and wired but send no frame — mnemonics unverifiable in this session (no TRM / `pk232_mnemonic_table.txt` available). See "Offene Mnemonics" above. |
| Testplan T87–T93 | New (renumbered from the sprint sketch's T83–T88, which collided with existing tests). T87–T92 software/headless-verified against a stub `_serial`; T93 verified end-to-end against the real `tools/mock_tnc_bbs.py` `LoopbackTNC`. Interactive mock-GUI click + hardware re-test still open. |
| `_make_host_frame()` channel-nibble bugfix | Found *while* verifying this sprint against the real mock TNC (not the stub): `_make_host_frame()` (`serial_manager.py`) hardcoded `channel=15` for every CTL byte except `$3x`, so `on_channel_state` never got the real channel for a live LINK_MSG — the chip silently never updated outside synthetic tests. Fixed in its own commit ("Fix channel nibble extraction for 4x and 5x frames") using the canonical `ctl_channel()`. Pre-existing bug (commit ff17aa01, 2026-04-24), not introduced by this sprint. See the two new Priority 1 entries above (LINK_STATUS misclassification, parallel decoders) for what was deliberately *not* touched. |

**Verification:** 75 unit tests pass (70 + 5 new `TestMakeHostFrame` cases);
all touched files byte-compile. Headless (offscreen Qt) end-to-end check:
`HFPacketMode` wired into a live `MainWindow`/`PacketBaseScreen` pair —
first against a stub `_serial` (Connect on channel 4 sends `CO` with the
channel-4 CTL nibble, not channel 1; a synthetic `LINK_MSG` "CONNECTED to
OE1XYZ-5" on channel 4 updates the chip, `ChannelBar.channel_map()` and
`MheardPanel`'s channel column; TX data goes out on channel 4; Disconnect
sends `DI` on channel 4 and frees the chip; Capture and the ALL/CH filter
checked the same way), then a second time against the real
`tools/mock_tnc_bbs.py` `LoopbackTNC` end to end (`connect_port` →
`init_tnc` → mode switch → Connect/TX/Disconnect on channel 4) to catch
exactly the kind of runtime-only bug a stub can hide — which is how the
channel-nibble bug above was actually found (see Testplan T93).

---

## Completed (2026-06-22 — Tooltip system)

| Item | Notes |
|------|-------|
| `tooltips.py` | Global `TOOLTIPS` (by actual attribute name) + per-class `SCREEN_TOOLTIPS` overrides. `apply_tooltips(widget)` applies global then `SCREEN_TOOLTIPS[type(widget).__name__]`, skipping non-existent/non-widget attrs. |
| 10 screens wired | RttyBaseScreen (→ Baudot + ASCII), AmtorScreen, MorseScreen, PactorScreen, NavtexScreen, FaxScreen, SignalScreen, PacketBaseScreen + a second pass on MheardPanel. |
| Name collisions | Per-class overrides for btn_connect (AX.25↔PACTOR), btn_rxrev (RTTY↔FAX), btn_lock (Morse↔FAX), btn_stby (AMTOR↔PACTOR), btn_clear (FAX image↔MHEARD list). A flat dict could not disambiguate these. |
| Key reconciliation | Provided dict keys mapped to real attribute names (fax btn_fax_*→btn_lock/btn_stop/btn_clear(+image), sliders→_lh_slider/_smooth_slider; signal→btn_neue_analyse; pactor→btn_connect/disconnect/stby; figs→btn_figs/btn_chars; mheard→btn_refresh/btn_clear). |
| PACTOR inline tooltips | Removed (registry-driven now); lbl_myptcall inline kept. |
| `btn_mopt` | Does not exist anywhere (grep-confirmed) — no removal commit needed. |
| T86 | PASSALL `PS` vs `PX`: documented as OPEN; `b'PS'` left unchanged pending hardware. |

**Verification:** 70 unit tests pass; all files byte-compile. Headless
(offscreen Qt) instantiation of every screen confirmed each representative
tooltip applies, including the collision overrides (PACTOR connect, FAX rxrev/
lock, MHEARD clear) vs the global defaults (Packet connect = AX.25).

---

## Completed (2026-06-22 — Help-System-Sprint)

| Item | Notes |
|------|-------|
| `help_viewer.py` | `HELP_TOPICS` for all modes + common topics; default topic `index`; internal topic switch via `anchorClicked` (`setOpenLinks(False)` → `_on_link_clicked` branches on URL scheme). |
| 10 help files | `index` + 9 modes (`amtor/baudot/ascii/morse/pactor/packet/navtex/fax/signal`); OE3GAS-reviewed. `vhf` → `help_packet.md` (shared file, no duplication). `help_index.md` + `help_amtor.md` newly created. |
| Help button | `make_help_button()` factory in `opmode_rtty_base.py`; `?` button in the title row of all 10 screens (RttyBaseScreen covers Baudot+ASCII; Packet uses `HELP_TOPIC` so HF→`packet`, VHF→`vhf`). |
| Help menu | `MainWindow` `&Help` menu: Contents (F1 → `show_help("index")`) + About (reuses `_on_about`). |
| APRS on HF Packet | `APRS_CAPABLE = True` in `HFPacketScreen` — one line. Decode logic already mode-agnostic (`_is_packet` matches any `PacketBaseScreen`; `HFPacketMode` already calls `on_monitor_frame`), so `packet_hf.py` unchanged. |
| Morse toggle buttons | grep-confirmed: `btn_rxrev`/`btn_txrev`/`btn_usos`/`btn_wideshft` do **not** exist in `morse_screen.py` — no removal needed. |

**Verification:** 70 unit tests pass; sources export = 73 Python + 10 help
files. Headless (offscreen Qt) smoke test: all 10 screens instantiate; default
topic = `index`; clicking `[AMTOR](amtor)` / `[VHF](vhf)` switches the page; HF
and VHF Packet both expose `btn_aprs` with `APRS_CAPABLE = True`.

**Open:** `help_amtor.md` proof-read (CC re-authored vs. approved chat version);
own `help_shortcuts.md` / `help_macros.md` files instead of anchors (v0.2).

---

## Completed (2026-06-23 — Help-Bugfix-Sprint)

| Item | Notes |
|------|-------|
| `help_controls.md` | New file; documents ONLY `[^D]` (Ctrl-D) + `[^T:n]` (Ctrl-T) — verified against `TxInputWidget` (`opmode_rtty_base.py:389–447`). Ctrl-E (WRU)/Ctrl-B (AAB) dropped: not typeable TX control chars, only TNC params. |
| `controls` anchor fix | `HELP_TOPICS["controls"]` → `help_controls.md` (was the dead `help_baudot.md#control-characters`). No more dead internal links. |
| 3 tooltips | `btn_wordout` (Morse), `btn_hold` + `btn_pactor_listen` (AMTOR) added to `tooltips.py`. |
| 4 status-bar tooltips | `_sb_port` / `_sb_baud` / `_sb_mode` / `_sb_time` (`main_window.py:716–733`). |
| Dead-code `TNCConfigDialog` | `dialogs/tnc_config.py` deleted (−1 Python file); `dialogs/__init__.py` import + `__all__` and `check_repo.sh` entry removed. Active dialog stays `ui/tnc_config_dialog.py::TncConfigDialog`. grep `TNCConfigDialog` = 0 refs. |

**Verification:** 70 unit tests pass; sources export = 72 Python (−1) + 11 help
(+1) = 83. Headless smoke test: `controls` resolves to `help_controls.md` and
the link click switches topic; `btn_wordout`/`btn_hold`/`btn_pactor_listen`
tooltips non-empty; `dialogs` package imports without `TNCConfigDialog`.

**New finding (not fixed — out of scope):** 🧹 `main_window.py:4170–4191` is an
appended §10 corruption artefact (mangled `tnc_config_dialog.py` docstring
fragment, mojibake). It is a functionless no-op string — no duplicate `class`
def, no defect. Remove when convenient.

---

## Completed (2026-06-22 — Paket 3 Stop Sending)

| Item | Notes |
|------|-------|
| T17 Stop Sending — Clear TX | PASS (software/mock). Clear TX during SEND sends the mode stop cmd (`RC` RTTY/Morse, `AM` AMTOR), empties TX, `TxController.clear()`, UI → RECEIVE. AMTOR `AM` bug fixed. Hardware pending. |
| T85 Stop Sending — RECEIVE button | PASS (software/mock). RECEIVE during SEND → `RC` for Baudot/ASCII/Morse (`_on_screen_receive` → `_on_screen_send(False)`); AMTOR has no RECEIVE button (use Clear TX). |
| AMTOR Clear TX bug | `_on_clear_tx()` skipped `AM` because `_send_active` is never set for AMTOR (ARQ TX is CONNECTED-triggered, no SEND button). Fix: send `AM` unconditionally for AMTOR ARQ/FEC; keep the `_send_active` guard for the button-driven modes. |
| Paket 3 complete | RC / AM / none verified for every mode. TxController cycle (Paket 1 rename, 2a Morse, 2b AMTOR, 3 Stop) closed. |

**Verification:** 70 unit tests pass; `main_window.py` compiles. Stop-command
decision matrix confirmed headless — AMTOR ARQ/FEC → `AM` even with
`_send_active=False`; Baudot/Morse idle Clear TX → no command; Packet/PACTOR →
none. Live-GUI click + hardware re-test (AMTOR flush, Morse RC-regression) pending.

**Follow-up fix (2026-08-08):**

| Item | Notes |
|------|-------|
| Clear TX UI-Repaint bug | Fixed 2026-08-08. `_on_clear_tx()` setzte btn_send/btn_receive Checked-Zustand via blockSignals, ohne die zugehörigen Stylesheets/Blink-Timer nachzuziehen — btn_send blieb rot. Fix: STYLE_PROM_INACTIVE/STYLE_RECEIVE_ON + blink_timer.stop() explizit in _on_clear_tx() gesetzt. |

---

## Completed (2026-06-22 — Sprint T41/T42 MHEARD)

| Item | Notes |
|------|-------|
| T41 MHEARD Refresh | `_on_packet_mheard()` clears the panel, then fires `MH0`..`MH17` fire-and-forget (TRM §4.11 line-by-line poll). Replies arrive async as CMD_RESP `MH` lines. |
| T42 MHEARD Clear | `btn_clear` → `MheardPanel.clear()` (local only); Refresh also clears before re-polling so the list never doubles. |
| `packet_hf.py` `on_mheard_entry` callback | `handle_frame()` gained a CMD_RESP branch → `_handle_cmd_resp()`: forwards only non-empty `MH` lines; end-marker (`MH`+`$00`) and plain command ACKs ignored. |
| `_parse_mheard_line()` | Robust to DAYTIME on/off (time token detected by `:`), `*` direct marker, `HH:MM` truncation. DAYSTAMP date prefix ignored (v0.1). |
| `mock_tnc_bbs.py` MH responses | `MH0`→`OE3GAS*`, `MH1`→`OE1XYZ`, `MH2`→`DB0MUC`, `MH3+`→`MH`+`$00` (end-of-list). |

**Verification:** 70 unit tests pass; all files byte-compile. Parser unit-checked
(time/no-time, direct/non-direct, empty). Mode dispatch fires only for real lines.
Full chain headless (app→mock→mode): `MH0..MH4` decoded exactly the 3 stations,
end-markers dropped. Live-GUI click + hardware re-test pending.

---

## Completed (2026-06-22 — Sprint T38–T51 Packet toggle/button)

| Item | Notes |
|------|-------|
| T38 Unproto UN frame | `_on_packet_unproto()` → `build_command(b'UN', path)` — was already implemented; verified `ctl=0x4F data=b'UNCQ VIA OE3XNR-8'`. |
| T39 Mutual exclusion Connect↔Unproto | Both directions: `set_link_state()` greys `btn_unproto` while connected/calling; `_on_packet_unproto()` greys `btn_connect` (link-busy proxy = `btn_disconnect.isEnabled()`). |
| T43 EAS toggle `EA Y/N` | Was already implemented (toggle_map mnemonic `EA`). |
| **T44 PASSALL toggle — BUGFIX** | Mnemonic `PA` → `PS`. `PA` is the PACKET-mode activation command; `PA Y` would have re-entered Packet mode instead of toggling PASSALL. |
| T45 HBAUD change `HB` frame | Was already implemented (`_on_packet_hbaud_changed`). |
| T46 Monitor level `MN` frame | Was already implemented (`_on_packet_monitor_changed`, levels 0–6). |
| T47 MailDrop `MI` | Was already implemented (`_on_packet_maildrop`). |
| T48/T32 HF+VHF init frames | `HFPacketMode`: `VH N` + `HB 300` + `MN Y`; `VHFPacketMode`: own list `HB 1200` + `MX 4` + `SL 10` + `MN Y` (no longer inherits the HF `VH N`, which would undo its own `VH Y`). |
| T49 NoFocus buttons | `make_toggle_button` / `_no_focus_btn` already set `Qt.FocusPolicy.NoFocus` — verified, no change. |
| T50 `le_dest` / `le_unproto` | Editable QLineEdit (default `CQ`) + `ScreenFocusController` registered — verified, no change. |
| T51 VHF deactivate `VH N` | `_on_mode_selected()` sends `VHFPacketMode.vhf_off_frame()` when the outgoing mode is VHF Packet, restoring the 300 Bd HF modem. |

**Verification:** frame bytes confirmed headless (venv), 70 unit tests pass, all
changed files byte-compile. The mock ACKs any general command, so it confirms
*that* a frame goes out — not mnemonic correctness; mnemonics were checked
against the TRM Host Mode command table (see Known bug below). Interactive mock
GUI re-click and hardware re-test remain open (tracked in Priority 1).

---

## Completed (2026-06-19 — Mock-TNC BBS sprint)

| Item | Notes |
|------|-------|
| Mock TNC + mini-BBS (`tools/mock_tnc_bbs.py`) | In-process `LoopbackTNC` duck-types serial.Serial via `SerialManager.set_port_factory()`; mini-BBS answers CONNECT/L/R/D. Exercises Packet connected mode (T33–T37, T83–T84) without a TNC, radio or second station. Dev-only, GPL v2. |
| CO/DI frame CTL bug ($4F instead of $41) | `_on_packet_connect/_disconnect` built the channel frame but sent it via `send_command()` (forces CTL=$4F, channel lost). Now uses `send_channel_command()` → correct $41. Fixed 47f5845. |
| Connect-button gating (prevent double CO) | `PacketBaseScreen.set_link_state()` + gating in `_make_link_handler`/`_on_packet_connect`: Connect disabled while connected/calling, re-enabled (and released) on disconnect; Disconnect starts disabled. |
| Packet Connect/Disconnect software tests (T33–T37) | PASS against the mock; T83/T84 added to Testplan. Hardware re-test (real second station) tracked under Priority 1. |

---

## Completed (2026-06-18 — FAX live image decode + TX polish)

| Item | Notes |
|------|-------|
| FAX live decode — `EpsonFaxParser` | Length-driven, frame-overlapping parser for the `$3F` Epson 9-pin printer-graphics stream (ESC L bit image + ESC A band separators) → 8-row grayscale bands → `FaxImageWidget`. Hardware-verified (Testplan T82). Unit tests in `src/pk232py/tests/test_epson_fax_parser.py`. |
| FAX display pixel aspect | `PIXEL_ASPECT = 120/72` vertical stretch (ESC L 120 dpi H / ESC A 8 → 72 dpi V), smooth scaling — fixes the squashed image / oval circle. |
| FAX smoothing slider | Non-destructive inverse-halftoning (`scipy.ndimage.gaussian_filter`, anisotropic `σ=(σ, σ·PIXEL_ASPECT)`, throttled recompute). Slider 0 = exact raw bilevel preserved. |
| FAX LOCK button | Force Receive (mnemonic `LO`) + parser reset / `_fax_receiving`. |
| FAX Stop button | Freeze image + ignore further data + parser reset; LOCK/Clear re-enable. |
| FAX FAXNEG = display-only invert | No longer sends `FN` to the TNC (TNC-side FN only affected subsequent lines → banded polarity). |
| `fax_wav_generator.py --target tnc` | Bench WAVs at the PK-232 demod centre (1200/2200 Hz) vs `--target sw` (1500/2300 Hz). |
| Testplan T81 / T82 | T81 = WAV→TNC bargraph sync; T82 = full live Epson decode (aspect, smoothing, start/stop, polarity). |

---

## Completed (v16 — 2026-06-14)

| Item | Notes |
|------|-------|
| TxController — Paket 1 (Umbenennung) | `BaudotTxController` → `TxController`, Datei `tx_controller.py`, `set_mspeed_ms()` ergänzt. commit cc2adff |
| TxController — Paket 2a (Morse) | Morse auf TxController gehoben, `[^D]` EOT → RC, ACK-getaktet. commit 437e8a1 |
| TxController — Paket 2b (AMTOR) | `amtor_screen.py`: TxInputWidget, CONNECTED→start, PTOVER ARQ-EOT. commit 8087564 |
| Clear TX / Clear RX buttons — all opmode screens | Done. TX-capable screens (AMTOR, CW/Morse, HF Packet, VHF Packet) emit `clear_tx_req` / `clear_rx_req` (signal pattern, wired by `MainWindow`); receive-only Signal/SIAM + NAVTEX got a local `_on_clear_rx()` slot; FAX got a local `_on_clear_image()` slot ("Clear Image"). |
| FAX closed-loop test tooling (`tools/`) | `fax_wav_generator.py` (WEFAX test-WAV generator: weather/pattern/text) + `fax_decoder_test.py` standalone decoder. Generator GPL v2, decoder GPL v3 (test-only, never shipped). |
| `fax_decoder_test.py` — fractional line length | Fixes accumulating line drift / slant (parallelogram) for non-integer samples-per-line. |
| `fax_decoder_test.py` — header detection | Detects the keyed 300 Hz APT start on the demod stream + tolerant run-length tracking. |
| `Sources2Text.ps1` — export `tools/**/*.py` | Export now includes `tools/` Python files (production code first, tools after). |

## Completed (v15 — 2026-05-17)

| Item | Notes |
|------|-------|
| Bug: CO on channel 0 → channel 1 | `build_ch_cmd(1, b'CO', ...)` in `_on_packet_connect()` |
| Bug: DI on channel 0 → channel 1 | `build_ch_cmd(1, b'DI')` in `_on_packet_disconnect()` (Claude Code) |
| Bug: `on_connect_toggled` AttributeError | Naming fix in `_wire_packet_buttons()` and disconnect handler |
| T31 VHF Packet init frames | ✅ PA, VH Y, HB 1200, MX 4, SL 10, MN Y — confirmed on TNC |
| T40 Monitor frames on 144.800 MHz | ✅ $3F frames received, decoded, displayed with UTC timestamps |
| APRS decoder v3 (`aprs_decoder.py`) | Mic-E (lat/lon), Position, Position+Time, Telemetry, Weather, Message, Third-party, Item, Object |
| APRS HTML display | Colour-coded cards in QTextEdit: orange/blue/green/yellow/pink per type |
| APRS button + dual-buffer | Toggle re-renders full frame history; raw mode unchanged |
| Mic-E backtick prefix fix | Strip `` ` ``/`'` before lon decoding — fixes 68°E → 16°E |
| Claude Code workflow | Established for direct file changes; patch scripts only as fallback |

## Completed (v14 — 2026-05-08)

| Item | Version | Notes |
|------|---------|-------|
| FAX: ESC L Spalten-Decoder | v14 | 8-Pin Epson Format korrekt dekodiert |
| FAX: Stream-Parser in fax_test.py | v14 | Frame-übergreifender ESC L Parser |
| FAX: LOCK Button | v14 | Host-Mnemonic LO |
| FAX: ASPECT ComboBox | v14 | IOC-Tabelle statt SpinBox |
| FAX: FSPEED Index-Fix | v14 | FS sendet Index 0-4 statt RPM-Wert |
| Host Mode Exit → Verbose | v14 | `_exiting_host_mode_by_user` Flag |
| PACTOR capability detection | v14 | Banner-Erkennung, ComboBox/Menü disabled |
| params_uploader race condition | v14 | 120ms Idle-Detection in write_verbose_wait() |

## Completed (v13)

| Item | Version | Notes |
|------|---------|-------|
| CTRL+T `[^T:n]` timed marker | v13 | Purple marker, QInputDialog for n (1–10) |
| Bugfix: text after `[^T:n]` not sent | v13 | `_tx_queue.clear()` fix |
| `_eot_positions` → dict-Liste | v13 | Variable Marker-Länge |

## Completed (v11/v12)

| Item | Version | Notes |
|------|---------|-------|
| HF Packet screen | v11 | `HFPacketScreen` |
| VHF Packet screen | v11 | `VHFPacketScreen` |
| Packet integration in MainWindow | v11 | `_wire_packet_buttons()`, 8 slots |
| PACTOR/AMTOR/Packet QLineEdit focus fix | v12 | `ScreenFocusController` |
| PACTOR MYPTCALL → QLabel | v12 | Populated from AppConfig |
| AMTOR identity labels → QLabel | v12 | Display-only |

---

## Known issues (monitor)

| Issue | Severity | Notes |
|-------|----------|-------|
| `MSPEED 20 Baud → 150ms/char` in log | Minor | Falls back to 150ms — cosmetic log noise |
| `CMD NAK: mnemonic=b'XL' error=0x07` | Minor | XL not supported by v7.1 — expected |
| `CMD NAK: mnemonic=b'EE' error=0x07` | Minor | EE not supported — expected |
| HFPacket/VHFPacket: CMD_RESP reaches mode | Minor | `handle_frame()` logs "unhandled frame" for ACKs — harmless |
| T18 (multi-cycle colour) | Open | Not formally tested |
| T32 HF Packet init frames | ✅ Fixed | `HFPacketMode.get_init_frames()` now emits `VH N` + `HB 300` + `MN Y` (2026-06-22, frame-verified) |

---

## Known bug — fixed (2026-06-22)

**PASSALL Host Mode mnemonic was `PA`, must be `PS`.**
The AEA PK-232 Host Mode uses `PS` for PASSALL; `PA` is the **PACKET-mode
activation** command (`HFPacketMode.host_command`). The PASSALL toggle was
wired as `build_command(b'PA', b'Y'/'N')`, so a single click on PASSALL would
have re-entered Packet mode instead of toggling the PASSALL flag. Fixed in
`main_window._wire_packet_buttons()` toggle_map (`b'PA'` → `b'PS'`).

*Lesson:* AEA Host Mode tokens are a fixed table, not first-two-letters
(MYCALL=`ML`, MYSELCAL=`MG`, MYPTCALL=`MK`, PACKET=`PA`, PASSALL=`PS`). Verify
new mnemonics against the TRM Host Mode command table — never guess.

**Correction (21.09.2026, P16, T86 hardware-verified):** this fix was itself
wrong. `PS` is **PASS**, a masking character (factory default `$16`,
Ctrl-V) — not PASSALL, and not a toggle. Real Host Mode raw frames: `PX` ->
`PXN` (a Y/N toggle), `PS` -> `PS$16` (the masking character). PASSALL is
`PX`. The PASSALL button sent `PS Y`/`PS N` from 2026-06-22 until this
correction, overwriting the PASS character with the letter `Y`/`N` on every
click instead of toggling PASSALL. Fixed in
`main_window._wire_packet_buttons()` toggle_map (`b'PS'` -> `b'PX'`), see
Testplan T86. **The lesson above applies to fixes too, not just new
mnemonics** — this correction had no TRM citation when it was made, and
introduced a second wrong mnemonic instead of the right one.

---

*OE3GAS | PK232PY Project | 2026-06-22, corrected 21.09.2026*