# PK232PY - Status, Sprint-Historie, offene Punkte

> Sprint-Chronik (v16, P-Nummern), Open/Next-Listen.
> Ausgelagert aus CLAUDE.md (unveraendert uebernommen, Stand 2026-09-29).

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
- **Echo detection and prompt-terminated reads (P52, 2026-09-25, unit-
  verified).** A console capture (25.09.2026, 23:30) proved the actual
  trigger behind a fresh app restart failing to reconnect: (1) step 3's
  HPOLL query got its own byte-identical echo back (verbose mode echoes
  every byte, even binary frames) and mistook it for a genuine Host Mode
  answer, sending a needless `HOST OFF`; (2) the detection chain's own
  `read_until()` re-armed a short per-iteration deadline on every chunk
  of new data, so a response split across more than one chunk (normal at
  9600 Bd) could be cut off before its `cmd:` prompt ever completed —
  explaining both the 4-instead-of-8-byte step 1 truncation in the same
  capture and why `ParamsUploader.verify()`'s spot-check was getting "no
  answer" for MYCALL/PACLEN/MAXFRAME even though the TNC was reachable
  throughout. Fixed with `_read_until_prompt()`, one shared marker/idle/
  timeout implementation now used by both the detection chain and
  `write_verbose_wait()`, plus `is_hpoll_echo()` rejecting a byte-
  identical reflection (a genuine answer is 6 bytes with a value byte,
  not 5). `ParamsUploader.verify()`'s no-answer/mismatch cases and
  `MainWindow`'s overall "verified (n/n)" summary now also reach the
  verbose terminal, not just the log. See the "echoes everything" and
  "don't read until the first pause" gotchas under Known Gotchas /
  TNC-firmware for the full writeup.
- **Converse-mode detection and a corrected read-path diagnosis (P53,
  2026-09-25, unit-verified).** Two independent findings from a real
  console capture and screenshot, 26.09.2026, 13:13–13:16. (1)
  `ParamsUploader.verify()` reported "no answer verifying MYCALL" even
  though the verbose terminal showed the TNC's correct reply to the very
  same query — investigated past the spec's own first framing ("the
  verification reads directly from the port") to the actual mechanism: a
  20/20-reproducible race between `query_verbose_value()`/
  `detect_maildrop()`'s transient `raw_data_received.connect()`/
  `disconnect()` pair and Qt's queued cross-thread delivery, which drops
  the call outright if disconnected before the receiving thread's event
  loop processes it. Fixed by reading the response
  `write_verbose_wait()`'s own new internal helper
  (`_write_verbose_wait_text()`) already assembled, directly — no
  signal-based capture in the loop at all. (2) A fresh reconnect failed
  with steps 1 and 2 both getting only an echo, never `cmd:` — the TNC
  was in Converse (Baudot RTTY had been the active mode before the
  disconnect, and `HOST OFF` returns to the last-active mode, not the
  command prompt), which the old chain could not tell apart from a
  genuinely dead TNC. New step 2b (COMMAND char + CR,
  `SerialManager.command_char`, mirrors `AppConfig.misc.command`) closes
  this, and `exit_host_mode()` now sends the same byte immediately after
  leaving Host Mode itself so the terminal is usable right away and the
  next connect cycle never needs step 2b at all. See the four new
  gotchas under Known Gotchas / TNC-firmware for the full writeup.
- **Port configuration and software flow control (P54, 2026-09-26,
  unit-verified).** After `Ctrl+D`/`Ctrl+T` (close then reconnect),
  steps 1/2/2b all got only an echo, never `cmd:` — but the operator's
  own counter-test settled it: PuTTY, same COM port/baud, no flow
  control configured, got a prompt with a single Enter on the identical
  physical TNC. **The TNC was fine — the app's own port configuration
  was not the same as PuTTY's.** `connect_port()` used to clear DTR/RTS
  (`rts = False`, `dtr = False`); PuTTY leaves them asserted. Fixed to
  assert both explicitly (`True`), and to log every parameter that
  affects behaviour (`xonxoff`/`rtscts`/`dsrdtr`/`dtr`/`rts`/`timeout`/
  `write_timeout`) right after open and again after this app's own
  post-open adjustments — the previous log line
  (`"Port COM6 opened at 9600 baud"`) gave a hardware run nothing to
  compare against. Independently: the PK-232 uses SOFTWARE flow control
  (its own boot banner proves it — see the dedicated gotcha below), so
  the detection chain also gained step 2c (XON, then CR, then a second
  CR) as defense in depth for a TNC a stray XOFF left generating
  nothing of its own while still echoing everything typed at it — the
  identical symptom shape Converse mode (P53) produces. See the two new
  gotchas under Known Gotchas / Serial-Host Mode for the full writeup.
- **UI findings from the test run (P55, 2026-09-26, unit-verified).**
  Six independent findings from one operator session, replacing
  `P51_Pruefdurchgang_Befunde_Spec.md`'s Teil A (superseded by P52-P54).
  (1) MHEARD's Callsign/Time columns showed a date/timestamp fragment
  instead of the real callsign — two sources: `_extract_partner()`
  split on the FIRST colon in a message, landing inside the TNC's own
  embedded `HH:MM:SS` (CONSTAMP/DAGSTAMP both ON by default); and
  `_parse_mheard_line()` never accounted for a DAYSTAMP date token
  ahead of the time/callsign. (2) The TX echo wrote directly into
  `rx_display`'s cursor instead of through `append_channel_data()`
  (P50), so it only reached whichever ONE document was visible at send
  time, never the channel's own document if ALL was showing (or vice
  versa). (3) Every RX `QTextDocument` visibly changed font when
  switching ALL/CH, since none had `setDefaultFont()` called on it —
  fixed with one shared `_RX_FONT` constant. (4) The firmware release
  header stayed "unknown" despite a correctly-logged banner capture —
  it was parsed from `SerialManager.tnc_banner` (frozen at the
  detection chain's own read) instead of the fully-collected P49 banner
  buffer, which can contain a `"Release ..."` line the chain's own read
  never saw complete. (5) A reported "opmode mask doesn't fill the
  window" could not be reproduced in code (measured against a real
  `MainWindow` + `BaudotScreen`, filled correctly in every configuration
  tried) — `apply_tooltips()` (the one call every screen's `__init__()`
  already makes) now also asserts `Expanding` size policy as defensive
  hardening regardless. (6) CONSTAMP/DAGSTAMP (the TNC's own link-
  message timestamp) and `show_timestamps` (PK232PY's own added prefix)
  documented as the two independent sources they are, in both the
  Display tab's tooltip and here. See the six new gotchas under Known
  Gotchas / Packet and UI-PyQt6 for the full writeup.
- **One font source, screen fills the window (P56, 2026-09-26, unit-
  verified).** Two corrections to P55's own findings above, both from
  the same three screenshots (maximized window, 2560×1440). (1) P55.C's
  `_RX_FONT` constant fixed the ALL-vs-CH font mismatch by introducing
  a SECOND font source, independent of the operator's Appearance
  setting — ALL view correctly showed `"Cascadia Mono SemiBold 14pt"`,
  CH view stayed on the hardcoded constant. `_RX_FONT` is deleted; a
  new `PacketBaseScreen.apply_rx_font()` pushes the Appearance font
  onto every RX document (visible or not), called from
  `MainWindow._apply_appearance()` — the ONE place any RX font now
  comes from. (2) P55.E's `Expanding` size-policy hardening did not
  actually fix the reported "opmode mask doesn't fill the window" —
  measured directly against a real `MainWindow` at 2560×1440: only the
  Packet screens (`PacketBaseScreen._build_ui()`) had a genuine bug —
  its RX/TX splitter and its status bar were BOTH added to the same
  layout at the stretch-factor default (0), an ambiguity Qt resolved by
  giving the status bar roughly HALF the window (683px, for six small
  labels) instead of the splitter getting the rest — fixed with one
  added `stretch=1` on the splitter. Every other screen (Baudot/ASCII/
  AMTOR/PACTOR/Morse/NAVTEX/Signal) was verified, the same way, to
  never have had this. New `test_opmode_screen_layout.py` measures
  actual geometry after a real resize()/show()/processEvents() cycle —
  P55 Teil E's own `QSizePolicy`-only check would have stayed green
  throughout a manually-confirmed 514px regression. See the four new/
  corrected gotchas under Known Gotchas / Packet and UI-PyQt6.
- **Chip editor closes on channel switch (P57, 2026-09-26, unit-
  verified).** Reproduced via a screenshot: with channel 3's inline
  callsign editor open, a click on channel 4 switched the current
  channel but left channel 3's editor open and focused, so keystrokes
  kept landing there instead of the TX window. Root cause: chips are
  `NoFocus` (P41), so a click on a different chip never fires the
  editing chip's own `focusOutEvent`, and the existing "losing focus
  cancels like Esc" rule never triggers. New
  `ChannelBar.close_open_editor()` cancels whichever chip is editing,
  called from `_select()` (covers a chip click, `set_current()` from
  outside, and `step()`), `reset()` (mode switch, leaving Host Mode),
  and the existing `PacketBaseScreen.eventFilter()`'s `MouseButtonPress`
  handling (a click into `tx_input`/`le_unproto`/`combo_monitor`/
  `combo_hbaud` — no new filter installed). A second finding from the
  same screenshot (the open editor's amber border looked missing) was
  investigated with pixel-level rendering and could not be reproduced —
  no code change made for that part. See the new gotcha under Known
  Gotchas / Packet.
- **MailDrop archive sync/restore automation (P59, 2026-09-26, unit-
  verified).** Closes the P39.3/Backlog "on_session_end/ask/auto not
  wired up yet" gap. New `SerialManager.fresh_boot_defaults` — an EVENT
  flag (reset every init/recovery run), never the sticky `tnc_defaults`
  it is derived from, since a trigger checking the sticky flag would
  fire on every later reconnect too, not just the one that actually
  followed a power-on. `MailDropDialog._end_session()` is now the ONE
  path out of an ACTIVE session (`btn_end` and a confirmed close
  gesture both call it) — collects TNC-only messages into the archive
  first when `archive_sync == "on_session_end"`, then leaves either
  way. `maildrop/archive.py::filter_restore_scope()` is the ONE scope
  filter (`all`/`unread`/`none`) shared by the manual "Restore to TNC"
  button and the new automatic trigger. `MainWindow.
  _check_archive_restore_trigger()` (wired to `host_mode_changed(True)`/
  `recovery_finished(True, ...)`) flags a restore as pending;
  `_update_maildrop_gate_ui()` fires the actual offer
  (`_offer_archive_restore()`, via `QTimer.singleShot(0, ...)`) the
  moment the MailDrop gate is actually open — which can be well after
  the TNC came up, if the operator was not in Packet mode yet.
  `MailDropDialog(..., auto_restore=True)` opens the session itself,
  restores every in-scope candidate after the first listing, and ends
  the session (closing itself) once that queue is empty — including
  immediately if there was nothing to restore. See the two new
  gotchas under Known Gotchas / TNC-firmware and / Packet for the full
  writeup. Hardware test cases T136/T137 (Testplan.md) are OPEN —
  needs Device B.
- **Archive restore trigger — one-shot fix (P60, 2026-09-27, unit-
  verified).** Review of P59 found `fresh_boot_defaults` was read but
  never consumed: `host_mode_changed(True)` also fires from
  `SerialManager._enter_host_mode_thread()` (leaving a MailDrop
  session, "Enter Host Mode" from the menu — neither runs
  `_init_tnc_thread()` again), so with `archive_restore = "auto"` the
  trigger re-armed itself every time a restore session ended, looping
  MailDrop sessions endlessly on real hardware (`docs/
  P60_Archive_Restore_Oneshot_Fix_Spec.md`, B.1 — **not yet reproduced
  on real hardware, found by review and confirmed by a unit test that
  fires the signal twice within one simulated power cycle**). New
  `SerialManager.consume_fresh_boot_defaults()` reads and clears the
  event in one call; `MainWindow._check_archive_restore_trigger()` now
  calls it unconditionally, first, before checking whether the current
  settings even want a restore. Also fixed: `MailDropDialog._on_failed()`'s
  restore branch compared its continuation against `self.session.leave`
  by identity — dead code, since neither call site ever passes exactly
  that method — replaced with an explicit `ends_session: bool` kwarg on
  `_start_sync()`/`_start_restore()`, so a restore that is itself the
  way OUT of the session (auto-restore, or a stopped auto-restore) now
  actually ends the session on failure too, instead of leaving it stuck
  ACTIVE. `filter_restore_scope()`'s docstring corrected (`unread` was
  never a no-op — `read_flag` is a real filter from the TNC's own N/Y
  at archiving time). See the new gotcha under Known Gotchas /
  TNC-firmware for the full writeup. Testplan.md T137 gained steps
  3a/3b (re-entry after a successful restore must not re-offer) — run
  with `ask` first, only move to `auto` once those pass.
- **APRS measurement package (P62, 2026-09-27; follow-up P62a,
  2026-09-27, unit-verified).** `tools/hw_check.py` gained three
  MEASURE-ONLY subcommands (`aprs_query`, `aprs_tx`, `aprs_reject`) for
  the future APRS TX mode (P63) — no shipped code changed. First real
  hardware run (Device B) found the actual key finding for P63: data
  sent on channel 0 splits into UI frames of at most PACLEN bytes each
  (T139 R4), so the APRS mode must own PACLEN the same way it owns
  UNPROTO — see the two new gotchas under Known Gotchas / Packet
  (HF/VHF). P62a fixed two measurement-tool defects the same run
  exposed: a blank-line-terminated decoder paste truncated a real
  multi-frame paste (`read_pasted_block()` now ends only on a line
  containing exactly `.`; frame counts are derived from the paste
  itself, `count_aprs_frames()`, never operator-typed), and A.6's
  9-digipeater probe couldn't tell "truncated" from "rejected" without
  first resetting UNPROTO to `CQ`. Added `aprs_query` A.7 (verbose
  PACLEN range probe)/A.8 (`PL` in Host Mode) and `aprs_tx` R6 (single
  frame at a probed-safe PACLEN); `aprs_reject` now assumes Direwolf/
  AGW as the calling station (the operator has one physical PK-232),
  not a second device. See `docs/P62_APRS_Measure_Spec.md` and
  `docs/P62a_APRS_Measure_Followup_Spec.md`; Testplan T138/T139/T140.
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
