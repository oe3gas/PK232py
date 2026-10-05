# PK232PY - Gotchas: UI/PyQt6, FAX, Param-Dialoge, Repo/Tests, Cleanup, Help

> PyQt6-Fallen, FAX-Decode, Parameterdialoge, Testumgebung.
> Ausgelagert aus CLAUDE.md (unveraendert uebernommen, Stand 2026-09-29).

### UI / PyQt6

- **Background threads talk to the window ONLY through signals (P83, 2026-10-05; CLAUDE.md rule 3).**
  A widget touched from a `threading.Thread` does not fail at once - it corrupts the display or crashes
  sporadically. The parameter upload thread (`PK232-ParamUpload`) used to call `_vt_append`,
  `_log_monitor`, `_update_maildrop_gate_ui` and `_vt_input.setFocus()` directly, and through
  `ParamsUploader`'s `echo_callback`. Pattern now: the thread `emit()`s (`_upload_vt_line`,
  `_upload_monitor_line`, `_upload_finished(UploadResult)`), a slot in the GUI thread writes - signals of
  one sender arrive in the order sent, so the output order is unchanged. Whatever happens AFTER the thread
  (messages, focus, MailDrop gate, `enter_host_mode()`) is decided by the slot, not by the thread. A
  callback that a background thread calls (`echo_callback`) must itself only emit. Check: every widget
  method a thread could reach starts with `ui/thread_guard.assert_gui_thread("where")`; the test suite
  sets `PK232_THREAD_GUARD=raise` and `conftest.py` fails any test during which it fired. A new thread
  that reaches a widget method fails the suite instead of crashing on the operator's machine.

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
- **The firmware release label was parsed from `SerialManager.tnc_banner`
  (frozen at the P43 detection chain's own capture) instead of the
  fully-collected P49 banner buffer — reproduced as "TNC-Firmware:
  unknown" despite a correctly-logged banner capture (P55.D,
  2026-09-26).** `SerialManager._tnc_banner` is set exactly once, from
  whatever `_finish_verbose_init()`'s own step captured at that moment —
  it is never updated with straggler bytes that arrive afterward via the
  `ReaderThread`. `MainWindow._banner_buffer` (P49 Teil B) DOES collect
  those stragglers (`_on_raw_data_received()` re-arms the quiet-window
  timer on every further byte while collecting), so a `"Release ..."`
  line split across that boundary could complete in the buffer the
  terminal displays while never reaching `_tnc_banner` at all — the
  terminal showed the banner correctly, the header did not, from the
  SAME underlying data. Fixed by parsing the release from
  `self._banner_buffer` itself, inside `_finish_banner_collection()`
  (reusing `serial_manager.py`'s own `_parse_release()`, not a second
  regex) — moved out of `_on_verbose_mode_ready()`'s own immediate,
  synchronous block entirely. Left UNCHANGED (not reset to "unknown")
  when a given round's buffer has no release line at all — a bare CR/
  COMMAND-char/XON reconnect (P53/P54's own steps 2b/2c) carries no
  banner, and the physical TNC has not actually changed just because
  that particular reconnect's own response happened to be silent about
  it.
- **`apply_tooltips()` also asserts `Expanding` size policy on the
  screen it is called on — the one place every opmode screen's
  `__init__()` already reaches exactly once (P55.E, 2026-09-26).**
  Investigated a reported "the opmode mask doesn't fill the window —
  empty area below the macro buttons" (screenshot, 26.09.2026): every
  screen's own top-level `QVBoxLayout` already gives `rx_display` (or,
  for Packet, the RX/TX splitter) `stretch=1`, and measuring the real
  `MainWindow` + `BaudotScreen` end to end (`_opmode_stack` →
  `QSplitter` → `host_layout` → `host_page`) showed the layout already
  filling correctly in every configuration tried — **no code-level bug
  was actually reproduced.** A plain `QWidget` still defaults to
  `Preferred`/`Preferred`, though, which is not a guarantee of filling
  its container the way `Expanding` is — so `apply_tooltips()` now also
  sets `Expanding` in both directions on `widget` itself, as defensive
  hardening for whatever configuration the screenshot was actually taken
  in, piggybacked onto the ONE call every screen (RttyBaseScreen/
  AmtorScreen/PactorScreen/MorseScreen/PacketBaseScreen/NavtexScreen/
  SignalScreen/FaxScreen) already makes at the end of its own
  `__init__()`, per the spec's own explicit ask for a single touch
  point — not a second, near-identical call added to all eight files.
- **Correction to the P55.E entry above — the real bug existed, but
  only on Packet screens, and only showed up on a MAXIMIZED window
  (P56.B, 2026-09-26).** P55's own measurement used a non-maximized
  `BaudotScreen`, which is exactly why it found nothing — `PacketBase
  Screen._build_ui()`'s top-level layout adds its RX/TX splitter AND its
  status bar with NEITHER given an explicit stretch factor
  (`outer.addWidget(splitter)` / `outer.addWidget(self._status_bar)`);
  with both at the layout default (stretch=0) and neither's
  `maximumSize()` constrained, Qt split the leftover height between
  them roughly evenly instead of giving it all to the splitter —
  measured directly on a real `MainWindow` at 2560×1440 (matching the
  screenshot): the status bar (six small `QLabel`s in a thin `QFrame`)
  came out **683px tall**, and the macro row nested inside the
  under-sized splitter landed near the middle of the screen instead of
  at the bottom — exactly the reported symptom. Every OTHER screen
  (Baudot/ASCII/AMTOR/PACTOR/Morse/NAVTEX/Signal) has only ONE major
  stretchy item competing for space (`rx_display`, already `stretch=1`)
  and nothing else large enough to compete with it — verified the same
  way, at the same window size, and none of them showed this. Fixed
  with one added `stretch=1` on the splitter
  (`outer.addWidget(splitter, stretch=1)`) — the status bar's own small
  `sizeHint()` is all it needs once it is no longer treated as an equal
  competitor for the remaining space. **Rule, restated:** two sibling
  layout items that are BOTH left at the default stretch (0) with
  neither's height bounded is a real ambiguity Qt can resolve either
  way, not a "one will obviously win" situation — always give the item
  that should absorb extra space an explicit `stretch=1` rather than
  relying on the other one being "obviously small."
- **A test that only checks whether a `QSizePolicy` is SET proves
  nothing about the actual result — measure geometry instead (P56.B,
  2026-09-26, correcting the lesson P55 Teil E almost drew).** The
  `Expanding` policy P55.E added is real and harmless, but it did not
  actually fix the reported bug — the ambiguous stretch-factor tie
  above did, and only a test that resizes a REAL `MainWindow` to a
  specific size, calls `show()`/`processEvents()`, and measures where
  the last row (or, for Packet, the status bar) actually ends up would
  ever have caught it (`test_opmode_screen_layout.py`, one
  parametrized test per screen, manually confirmed red without the
  `stretch=1` fix — a 514px gap on the affected screens, a `QSizePolicy`
  assertion alone would have stayed green throughout). **Rule:** a
  geometry or layout-filling claim gets a test that measures actual
  pixel positions after a real show()/resize()/processEvents() cycle,
  never a test that only checks a declared property.

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
- **Two independent sources of a timestamp can appear in the same RX
  line — CONSTAMP/DAGSTAMP (the TNC's own) and `show_timestamps` (this
  app's own) are not the same setting (P55.F, 2026-09-26).** A link
  message's own stamp, e.g. `"*** 25-Sep-26 21:04:36 CONNECTED to
  OE3TEC ***"`, comes from the TNC itself — `CONSTAMP`/`DAGSTAMP`
  (HF Packet Parameters → Parameters tab, both ON by default,
  uploaded as real `CONSTAMP`/`DAYSTAMP` commands) put it there, and it
  is part of the message TEXT, appearing regardless of any PC-side
  setting. `HFPacketConfig.show_timestamps` (Display tab, P50 Teil C,
  OFF by default) controls a SEPARATE, PK232PY-added `"[HH:MM:SS]"`
  prefix on every RX line (link messages included) — turning it on
  does not affect, and is not affected by, whether the TNC's own stamp
  is present. Investigated after a session where both were visible at
  once and easy to mistake for one setting doing double duty; both
  checkboxes' own tooltips (`ui/dialogs/params_hf.py`) now cross-
  reference this explicitly.

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
- **Test-run workflow (P61, 2026-09-27):** while working on one package,
  run only the affected file(s) (e.g. `.venv\Scripts\python.exe -m
  pytest src/pk232py/tests/test_maildrop_dialog.py`) — the full suite is
  for before a push. Before every push, run the full suite with
  `--durations=15` and put that output in the session's own final
  report. **Rule: no single test over 1 second without a docstring
  reason.** A test that legitimately needs more (a real subprocess, a
  real thread join with a generous timeout) documents why right there,
  rather than leaving a silent multi-second test for the next profiling
  pass to rediscover.
- **Every `MainWindow` a test builds is destroyed at teardown, never
  merely `close()`d, and this is conftest.py's job, not each test
  file's own (P61, 2026-09-27).** `MainWindow.__init__()` installs
  itself as an application-wide event filter
  (`QApplication.instance().installEventFilter(self)`, §6). `close()`
  alone only hides the widget — no `WA_DeleteOnClose`, and signal
  connections/closures keep the Python object reachable regardless — so
  it keeps filtering EVERY event of EVERY later test, and stays in
  `QApplication.topLevelWidgets()` forever. Measured: a fresh
  `MainWindow()` cost 0.11s with no other live window around, 2.62s
  with 11 undisposed ones still there (a real, quadratic cost — one
  leaked `MainWindow` per test fixture, not per file, and this repo had
  several: `test_main_window_packet.py`'s `TestModeInstanceFactory.
  window` fixture used `return w` instead of `yield w` — no teardown of
  any kind — and a bare `test_signal_screen.py::
  test_wire_mode_callbacks_connects_on_result_parsed` built one with no
  cleanup at all). `conftest.py`'s autouse `dispose_main_windows`
  fixture now catches every one of these generically, regardless of
  which fixture or test body built it, by looping over
  `topLevelWidgets()` at teardown — `removeEventFilter()` +
  `deleteLater()`, **never** `close()` (which would run `closeEvent()`,
  popping a real, unclickable `QMessageBox.question()` whenever a
  stub's `is_connected` happens to read `True`). The handful of
  fixtures that used to do this per-file (`wired_vhf`, the various
  `wired_window`s) had their now-redundant teardown code removed — one
  place, not N. `test_config_isolation.py`'s own test of `closeEvent()`'s
  save-on-close behaviour is unaffected — it still calls `close()`
  itself, inside the test body, to exercise exactly that.
- **QSettings("OE3GAS", APP_TITLE) needed the SAME isolation P48 gave
  the INI config file, at a SECOND storage location — and the obvious
  fix (`QSettings.setDefaultFormat()`/`setPath()`) silently does not
  work on Windows for this exact call shape (P61, 2026-09-27).**
  `main_window.py`'s `_save_window_geometry()`/`_restore_window_
  geometry()` call the TWO-ARGUMENT constructor,
  `QSettings(organization, application)` — confirmed by direct testing
  (not assumed) that this specific constructor always uses
  `QSettings::NativeFormat` regardless of `setDefaultFormat()`, and on
  Windows `NativeFormat` IS the registry, which `setPath()` cannot
  redirect at all (there is no filesystem path to redirect). The P61
  spec's own `setDefaultFormat()`/`setPath()` recipe was measured on
  Linux, where `NativeFormat`'s registry equivalent is itself just an
  INI-shaped file `setPath()` DOES redirect — it silently does nothing
  on Windows, so a fixture written against that recipe alone would
  report success (no exception) while still writing to the real
  registry. Fixed by monkeypatching the NAME `QSettings` inside
  `pk232py.ui.main_window`'s own module namespace (`conftest.py`'s
  `isolate_qsettings` fixture) — Python resolves a bare name at CALL
  time against the enclosing module's globals, so every
  `QSettings("OE3GAS", APP_TITLE)` call those two methods make is
  redirected to an explicit `Format.IniFormat`/`Scope.UserScope`
  instance under that test's own `tmp_path`, with `main_window.py`
  itself never edited — the same technique
  `test_main_window_packet.py::TestPacketRxTxSplitterPersistence`
  already used at the single-test level (`monkeypatch.setattr(mw,
  "QSettings", _FakeQSettings)`), just applied once, for every test.
  **Rule: verify a Qt persistence-isolation recipe by direct testing on
  the actual target platform before trusting it — "it didn't raise" is
  not "it wrote where I told it to."**
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

### Per-theme appearance (P79, 2026-10-03)

- **`AppearanceConfig.effective(theme)` is the ONLY place that combines a theme's
  default with its override.** The single fields (`font_family` ... `tx_color`)
  are the effective values of the CURRENT theme; every reader keeps using them.
  Never write a theme's preset values into them anywhere else (the old
  "self-healing" block in `MainWindow._apply_appearance()` is gone).
- **Field edits become overrides via `store_overrides()`** (diff against
  `defaults(theme)`; a value equal to the default is dropped). `switch_theme()`
  stores first, then loads the new theme; `ConfigManager._build_appearance()`
  stores too. Consequence: after assigning `overrides` by hand, call
  `load_effective()`, or the next save derives the overrides from stale fields.
- **Theme defaults live in `colors.THEME_DISPLAY` / `THEME_TEXT_COLORS`** (Qt-free,
  `config.py` must not import `ui`); `ui/themes.py` builds its `Theme` objects
  from them. `custom` is a theme of its own with Dark defaults, not reachable from
  the menu (only through an old INI).
- **The dialog writes `_family_name`, not `currentFont().family()`**: a font that
  is not installed is shown as the combo's fallback, OK must not replace it.
  Headless tests have no fonts at all - set `dlg._family_name` in tests.

### Display colors: one source (P77, 2026-10-03)

- **RX/TX text colors live in `AppearanceConfig.rx_color` / `tx_color` - nowhere
  else.** Themes (`ui/themes.py`, `colors.THEME_TEXT_COLORS`) only supply defaults;
  a theme selection copies them into the config, a hand change in the Appearance
  dialog was `custom` until P79 (now: per-theme overrides, see above). Before P77 `ui/screens/ui_theme.py` had its own
  `rx_color`/`tx_color` per dark/light palette and the app always used the DARK
  one - gold `#ffee88` on a white background (screenshots 03.10.2026).
- **`ui_theme.get_theme()` = widget palette + configured colors.**
  `MainWindow._apply_appearance()` calls `configure_display_colors(bg, rx, tx)`;
  the dark/light palette is chosen by `colors.is_light_background(bg)` (one
  function), no separate `_current_theme` switch. `set_theme()` remains only for
  the stand-alone screen mockups.
- **`colors.py` is Qt-free on purpose.** `config.py` needs the theme defaults to
  fill a missing INI key, and `config.py` must not import `pk232py.ui` (its
  `__init__` imports MainWindow, which imports config - a circle).
- **Verbose terminal:** `_vt_append(text, color=None)` = RX colour; own commands
  `cmd:...` use the TX colour; green/red status lines and the grey `[CR]` echo stay
  fixed. Text already in the terminal is recoloured on a colour change
  (`_recolor_existing_text`). The first fragment of the terminal document is an
  empty block's separator - tests must skip fragments without text.
- **Sent-character highlight:** background `tx_color`, text `bg_color`
  (`TxInputWidget.set_theme_colors(tx, bg)`), no longer black on `#ddaa00`.
- **Contrast:** `colors.contrast_ratio()` (WCAG 2.x); the dialog warns below
  `MIN_CONTRAST` 4.5 but never blocks saving.
- **Role colors (P77a, 2026-10-03).** `colors.RoleColors` / `THEME_ROLE_COLORS`:
  `sys_color` (link/system messages, `[^D]`), `ok_color`, `err_color`, `dim_color`
  (MON, timestamps, `[CR]` echo, `[^T]`). Per theme, NOT configurable in a dialog;
  Dark keeps its old values, the light themes are darker. Handed over with
  `configure_display_colors(bg, rx, tx, roles)`, read with
  `ui_theme.get_theme()["sys_color"]` etc.; `MainWindow._sys_color()` and friends
  are the shortcuts. `semantic_colors()["rx_echo"]` IS `sys_color` (one source;
  the old light echo `#b36b00` reached only 4.2 : 1 on white). Packet screens:
  channel text = `rx_color`, MON/timestamps = `dim_color`; the per-channel RX
  documents are recoloured by `PacketBaseScreen.recolor_rx_documents()` (the widget
  shows only one of eleven documents). `ui_theme.recolor_document()` is the single
  recolour implementation.
- **Rule: every theme text colour must reach 4.5 : 1.** `test_text_colors_p77a.py`
  checks fg/rx/tx/sys/ok/err/dim and the semantic colours for all four presets
  against their background - a new theme or role colour that fails shows up there.
- **Dialogs keep the standard look (P77b, 2026-10-03).** There is NO application
  stylesheet; the theme reaches the dialogs through `_apply_palette()`, which sets
  `QApplication.setStyle/setPalette` (needed for the main window's buttons, menus
  and status bar). Every dialog inherits the application palette, so Retro made the
  Appearance dialog and the QColorDialog unreadable. Fix, ONE place:
  `MainWindow.eventFilter` (installed on the QApplication) calls
  `_give_dialog_standard_look(dlg)` on the Show event of any QDialog; it sets
  `QStyleFactory.create(system_style).standardPalette()` on the dialog (palette
  propagates to its children). A parented dialog does NOT inherit its parent's
  palette on its own (no `WA_WindowPropagation`), and `QWidget.setStyle()` does not
  reach children - so palette-only, hooked on the dialog. A new dialog needs
  nothing. Test: `test_dialog_look_p77b.py`.
- **Colour picker:** `QColorDialog.getColor(...)` WITHOUT options - never the
  option that forces Qt's widget dialog; where Qt falls back to its own dialog
  the hook above still makes it readable.
- **Contrast depends on the font (P77b).** `colors.required_contrast(pt, bold)`:
  3 : 1 for >= 18 pt or >= 14 pt bold, else 4.5 : 1. `font_is_bold()` also reads
  the family NAME (Windows installs "Cascadia Mono SemiBold" as its own family
  and Qt reports a normal weight); SemiBold counts as bold. `meets_contrast()`
  compares the one-decimal value that is displayed (`#00aa7f` on white is 2.976,
  shown "3.0 : 1", must not be red against 3 : 1). The dialog judges bold-ness by
  the configured family name, not by the combo's fallback for a font that is not
  installed on this PC.
- **Chrome deliberately untouched:** menu, status bar (OFFLINE badge `#888888`,
  "TNC differs" `#f44747`), buttons, the READY chip, MailDrop dialog colours.
