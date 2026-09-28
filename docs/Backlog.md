# PK232PY — Development Backlog

**Last updated:** 2026-09-26 (P58 — backlog audit: T122 PASS, P51 marked
superseded, P55/P56 corrections recorded, hardware confirmations from
2026-09-25/26 added, completeness pass against docs/P40 onward)
**Current version:** v0.1 (development)

**`docs/P51_Pruefdurchgang_Befunde_Spec.md` was never implemented — do
not act on it (P58, 2026-09-26).** Its Teil A (echo/read-timing,
Ctrl-C/read-path, DTR/RTS) was superseded before ever being executed,
by the more precise diagnoses in P52 (`docs/P52_Echo_And_Read_Timing_
Spec.md`), P53 (`docs/P53_CtrlC_And_Verify_Readpath_Spec.md`) and P54
(`docs/P54_Port_Settings_Flow_Control_Spec.md`); its Teile B–I were
superseded the same way by P55 (`docs/P55_UI_Befunde_Spec.md`). The
file itself is not tracked in this repo (`docs/P51*.md` does not
exist) — this note exists purely so nobody goes looking for it, or
tries to execute it, expecting it to describe current work.

---

## Priority 1 — Next implementation sprint

### `maildrop/maildrop.py`'s mnemonic table is unverified and CAN be sent — open (P24.1, 2026-09-22)

`MailDropController`'s module docstring lists a "MailDrop Host Mode
mnemonics (STABO manual Ch. 12)" table (`HB`/`MY`/`LM`/`MD`/`TP`/`MT`/
`TL`/`3P`/`KF`/`MM`/`DM`) that has **never been confirmed against real
hardware** — the exact same class of error as `MI` (believed to be
MailDrop login, hardware-confirmed 22.09.2026 to actually be MFILTER,
T115). `MD` in particular is documented in the TRM as MDIGI, not
MDPROMPT. Marked `UNVERIFIED` in the docstring itself (P24.1) — nothing
renamed or corrected, per the "never guess a mnemonic" rule; that needs
its own measurement package, not a guess-fix.

**This is not hypothetical — the code CAN send all eight of these right
now:** `MailDropController.upload_config()` (`maildrop.py`) calls
`self._serial.send_command(mnemonic, args)` for every frame
`_build_config_frames()` builds (`TL`, `3P`, `KF`, `DM`, `MM`, and
conditionally `HB`, `MY`, `MT`) — eight unverified mnemonics sent in one
call, the moment something calls `upload_config()`. The seven
`*_frame()` static methods (`tmail_frame`, `homebbs_frame`,
`mymail_frame`, `mtext_frame`, `third_party_frame`, `kilonfwd_frame`,
`mdmon_frame`) build the same frames individually for any other caller.
**Currently NOT wired into the running app** — `MailDropController` is
exported from `maildrop/__init__.py` but never instantiated anywhere in
`main_window.py`/`mode_manager.py`, so none of this runs today. That
makes it dead code, not a live bug — but the moment any future MailDrop
feature wires this controller in (see the "MailDrop management dialog"
entry elsewhere in this file), it would send eight unverified mnemonics
with no measurement behind any of them. Verify each one with
`tools/hw_check.py` (or the TRM) before wiring `MailDropController` into
anything, and add each confirmed mnemonic to CLAUDE.md's "Hardware-
confirmed Host Mode mnemonics" table as it is measured.

**`.gitignore` finding above — ✅ FIXED (P25, 2026-09-22):** the bare
`maildrop/` line was removed (`Fix gitignore: anchored data dir
patterns, maildrop source was excluded`) and
`src/pk232py/maildrop/` (`maildrop.py`, `message_store.py`,
`__init__.py`) is now tracked in git (`Track maildrop module
(unverified mnemonics, to be rewritten after T117)`). Git archaeology
found no evidence the line ever guarded a real data directory — the
very same initial commit (15f9a4f) both added the `maildrop/` line
*and* documented `src/pk232py/maildrop/` as a source directory in
README.md, and `message_store.py` has always stored its SQLite file
at `~/.pk232py/maildrop.db`, outside the repo. Most likely an
unverified, unnoticed mistake from day one. See CLAUDE.md's "Repo /
tooling" gotchas for the general lesson (unanchored `.gitignore`
patterns match at any depth).

**Confirmed while checking it in (P25.2):** `MailDropController` and
`MessageStore` are exported from `maildrop/__init__.py` but are not
imported anywhere else in `src/pk232py/` (checked `main_window.py`,
`mode_manager.py`, every other module — no `from .maildrop import`,
no `from pk232py.maildrop`, no bare `MailDropController`/
`MessageStore` reference outside the package itself). The module is
dead code today, not a live bug — the unverified-mnemonics risk above
only becomes real the moment something wires it in. **Plan:** leave
it unwired until T117 (MailDrop over Host Mode, `docs/Testplan.md`)
is measured on real hardware; then replace this module's guessed
mnemonic table with a version built on the measured `$60`/`$70`
protocol, rather than fixing individual mnemonics piecemeal.

**✅ SUPERSEDED (P27, 2026-09-23):** the plan above assumed MDCHECK
would eventually be reachable over the `$60`/`$70` Host Mode channel.
`mdcheck_scan` (T118) found no Host Mode mnemonic for it at all, so
there is no `$60`/`$70` protocol to build a replacement table on.
`maildrop.py` (the geraten mnemonics, `upload_config()`) is **deleted**;
`protocol.py`/`session.py` replace it entirely on the verbose-mode
link. This item is closed — see the "MailDrop session" CLAUDE.md
section and T119.

### MDCHECK's Host Mode mnemonic is unknown — search in progress (P26, 2026-09-23)

The TRM's own Host Mode mnemonic table (ch.12) is internally
contradictory: it lists `MI` for both `MDCheck` and `MFIlter`. T115
already measured `MI` = MFILTER on real hardware, so the manual's
MDCHECK entry is simply wrong — the real mnemonic (if MDCHECK has one at
all) is unmeasured. `tools/hw_check.py mdcheck_scan` (P26.2, T118)
searches the remaining 23 `M?` mnemonics for one that answers with the
mailbox prompt, stopping at the first hit.

**Decision point once T118 has run (per the spec, `docs/
P26_MDCHECK_Mnemonic_Spec.md`):** a hit gives a real mnemonic to add to
CLAUDE.md's hardware-confirmed table and to the `$60`/`$70`-based
mnemonic table this section's plan (above) already calls for. **A "no
hit" result is equally decisive, not a failure:** it would mean MDCHECK
is not reachable as a two-letter Host Mode mnemonic at all, so any
future MailDrop dialog must open the mailbox over the verbose path
(`MDCHECK\r\n`, as `maildrop`/`maildrop_host` already do) even while the
rest of the session runs in Host Mode — not guess at a mnemonic that
does not exist. Either outcome, record it here and close this item.

Separately, T117's first hardware run (2026-09-22 21:13) found no `$70`
frame at all — only the generic `$5F` acknowledgement — but the run
itself exposed a tool bug (`maildrop_host` mistook that ack for a real
response and skipped Probe B, fixed P26.1) rather than answering the
question. T117 needs a **re-run** with the fixed tool before the
"leave it unwired until T117 is measured" plan above can be acted on.

**✅ RESOLVED (P27, 2026-09-23):** `mdcheck_scan` ran conceptually to
completion in the P26/P27 work — 23 candidates, no hit — settling this
item: MDCHECK is not reachable as a two-letter Host Mode mnemonic.
(T117's own re-run, above, is still open and separate — it measures the
`$60`/`$70` channel itself, which P27's `MailDropSession` does not use
at all, since it never needed to.)

### MailDrop session mask (UI) — ✅ DONE (P39, 2026-09-24; hardware run ✅ PASS, T122, 2026-09-25)

`MailDropSession`/`protocol.py` (P27) built the state machine with no UI
of its own by design; P38 built the storage half
(`maildrop/archive.py`). P39 built the mask itself:
`ui/dialogs/maildrop_dialog.py`'s `MailDropDialog` — a modal dialog, not
an opmode ComboBox entry (see CLAUDE.md's MailDrop section for why).
- `can_open()` is wired to the real channel model: the active Packet
  screen's `ChannelBar.channel_map()`, injected at dialog-construction
  time, never re-derived.
- `listing`/`message_read` fill a real `QTreeWidget` + reader pane;
  `send()` is driven from `MailComposeDialog`, which reuses
  `check_body()`/`sanitize_body()` rather than reimplementing either
  rule, and shows the sanitization preview before sending.
- `prompt_info.free` and `failed()` text both show in the dialog (header
  free-byte count, status line).
- `frm` "differs from MYCALL" is decided at the UI layer exactly as
  flagged: `_advance_restore()` blanks `frm` when it equals the
  operator's own MYCALL, passing it through unchanged (a genuine
  foreign FROM) otherwise.
- `archive_sync`/`archive_restore`/`archive_restore_scope` were still
  only SAVED settings at the time P39 shipped (P38.3) — the manual
  "Sync to archive"/"Restore to TNC" toolbar buttons were the only
  working path. **Superseded by P59 (2026-09-26, see the dedicated
  item below):** `on_session_end`/`ask`/`auto`/the restore scope are
  now all wired up — this bullet is left here as history, not as the
  current state.

**Hardware confirmation — ✅ PASS (T122, Testplan.md, 2026-09-25, Device
B, Release 01.AUG.91):** the operator ran the full dialog against real
hardware — gate page, opening a session, writing/reading/killing a
message, and closing the window via the title-bar close button (X)
with the confirmation prompt and visible leaving-Host-Mode progress
shown, Packet operation available again afterward. Everything worked
as designed. (Software coverage from before this run stays valid
alongside it: `test_maildrop_dialog.py` against a fake
`MailDropSession`, `test_main_window_packet.py::TestMaildropGate` for
the four-condition button/menu gate.)

### MailDrop dialog — Header.../EDIT locked, unmeasured (P39, 2026-09-24)

`btn_header` in `maildrop_dialog.py` is permanently disabled with the
tooltip "EDIT not measured yet" — the mailbox's `E` (EDIT) command
(status/callsign editing per the STABO handbook) has never been run
against real hardware, so its exact syntax and response shape are
unknown. Needs a `tools/hw_check.py` probe (read-only where possible,
same caution as every other MailDrop command measurement in this
project) before `Header...` can do anything.

### MailDrop button — MDMON as a second "mail waiting" source (P39, 2026-09-24)

`btn_maildrop`'s amber "mail waiting" colouring (P39.5) currently has
exactly one source: `PromptInfo.have_mail` from the LAST session that
was actually opened — nothing colours the button before a session has
ever run once, and nothing updates it live while Packet operation
continues afterwards. `MDMON` (already an uploaded `MailDropConfig`
field) is documented to announce mail activity from other stations'
sessions passing through, in principle observable without opening a
session at all — see the identical open question already filed under
"MDMON eavesdropped traffic" (P38.3 Backlog item) for archiving; the
same unmeasured signal would also answer this "second source" question.
Do not wire this without first measuring what `MDMON` actually announces.

### Device C (1988 BASE firmware) — MailDrop capability detection unmeasured (P37/T120, open)

`docs/DEVICES.md`'s Device C (30.12.1988, BASE generation) has never
been connected through the app or `tools/hw_check.py` at all — the
operator confirmed via a plain PuTTY session (23.09.2026) that it has
no MailDrop, but `SerialManager.detect_maildrop()` (P37, a verbose-mode
`MAILDROP` query) has only ever been exercised against Device C in
software/mock tests (`test_serial_manager.py::
TestClassifyMaildropResponse`, `test_params_uploader.py::
TestMaildropCapabilitySkip`, `test_params_maildrop_dialog.py`), never
against the real unit. See Testplan.md T120 for the exact live
sequence: connect, let the app initialise normally, and confirm the
`MAILDROP` query answers `?What?`, none of the seven MailDrop upload
commands are sent, and both `btn_maildrop` and every `Parameters →
MailDrop...` field show the "This firmware has no MailDrop" tooltip
(disabled, not hidden).

### MailDrop dialog — Sync/Restore auto-trigger — ✅ DONE (P59, 2026-09-26)

P39 built `MailDropConfig.archive_sync`/`archive_restore`/
`archive_restore_scope` as real, working USER-TRIGGERED toolbar buttons
("Sync to archive"/"Restore to TNC", `manual` behaviour only), leaving
the CONFIGURABLE automatic behaviour unwired. P59 closes this:
- `SerialManager.fresh_boot_defaults` (new) — an EVENT flag, reset at
  the start of every `_init_tnc_thread()`/`_recovery_thread()` run,
  true only when THAT run's own boot banner said "is using default
  values". Deliberately not derived from the existing `tnc_defaults`
  (sticky — it keeps the LAST banner ever seen and would still read
  True on a later reconnect/recovery against a TNC that has been
  running fine the whole time, B.3 in `docs/
  P59_MailDrop_Archive_Auto_Spec.md`).
- `MailDropDialog._end_session()` is now the ONE path out of an ACTIVE
  session (`btn_end` and a confirmed close gesture both call it) —
  when `archive_sync == "on_session_end"`, it reads every TNC-only
  message into the archive first, then leaves; a sync failure mid-
  queue still leaves afterwards (packet operation must resume even if
  the collection did not fully succeed).
- `maildrop/archive.py::filter_restore_scope()` — the ONE scope filter
  ("all"/"unread"/"none", unknown scope raises rather than falling
  back to "all") used by both the manual "Restore to TNC" button and
  the automatic trigger, so they can never disagree about what a scope
  means.
- `MainWindow._check_archive_restore_trigger()` (wired to
  `host_mode_changed(True)`/`recovery_finished(True, ...)`) flags a
  restore as pending when `fresh_boot_defaults` and the settings all
  agree; `_update_maildrop_gate_ui()` fires the actual offer
  (`_offer_archive_restore()`, `QTimer.singleShot(0, ...)` since a
  modal dialog cannot open from inside a gate-update call) the moment
  the gate — connected, Host Mode, HF/VHF Packet, no connected
  channel — is actually open, which may be well after the TNC came up
  if the operator was not in Packet mode yet.
- `MailDropDialog(..., auto_restore=True)` (C.4) opens the session
  itself, names what it is doing in the banner for the whole session,
  restores every in-scope archive-only candidate after the first
  listing, and ends the session (closing itself) once that queue is
  empty — including immediately, if there was nothing to restore.
  Stopping it mid-restore never aborts the in-flight message (no
  `abort()` — the `/EX` rule).
See Testplan.md T136 (sync)/T137 (restore) — both OPEN, need Device B.
**Follow-up: P60 (2026-09-27)** found and fixed a real bug in the D.1
trigger itself — see the next entry.

### MailDrop dialog — restore trigger one-shot fix — ✅ DONE (P60, 2026-09-27)

Review of P59 (`docs/P60_Archive_Restore_Oneshot_Fix_Spec.md`) found
that `fresh_boot_defaults` was an EVENT flag in name only —
`_check_archive_restore_trigger()` kept reading the live property
instead of consuming it, and `host_mode_changed(True)` fires from more
places than an init/recovery run (leaving a MailDrop session, "Enter
Host Mode" from the menu, both via
`SerialManager._enter_host_mode_thread()`, never
`_init_tnc_thread()`). With `archive_restore = "auto"` this meant an
**endless loop of MailDrop sessions** on real hardware — never caught
by P59's own tests, which never exercised a *second*
`host_mode_changed(True)` in the same power cycle. Two smaller findings
in the same review: a restore's failure path left the session stuck
ACTIVE forever if it was the way OUT of the session (auto-restore, or a
stopped auto-restore), because the old check compared the continuation
against `self.session.leave` by identity — dead code, since neither
call site ever passes literally that method; and
`filter_restore_scope()`'s own docstring wrongly claimed `unread`
"currently behaves like `all`" (it does not — `read_flag` is a real,
working filter, set from the TNC's own N/Y at archiving time).
- `SerialManager.consume_fresh_boot_defaults()` reads
  `fresh_boot_defaults` and clears it in the same call — the only place
  that ever does. `_check_archive_restore_trigger()` calls it FIRST,
  unconditionally, before checking whether the settings even want a
  restore — a later switch from `never` to `ask` mid-session must not
  retroactively arm a restore for a power-on that has already passed.
- `MailDropDialog._start_sync()`/`_start_restore()` gained an explicit
  `ends_session: bool` kwarg; `_on_failed()` now branches on that flag
  instead of comparing `then` against `self.session.leave` by identity.
- `filter_restore_scope()`'s docstring corrected.
See Testplan.md T137 steps 3a/3b (re-entry after a successful restore
must not re-offer) — **run with `ask` first; only move to `auto` once
3a/3b pass**, per the spec's own warning.

P27.3 found `message_store.py`'s `MailMessage`/SQLite schema did not
match what a real archive needs (own durable ID ✅, but no TNC message
number, no `@ BBS`, no P/T/B type, and `received_at` was the LOCAL
receipt timestamp, not the TNC's own store-time stamp). P38 replaced it
outright with `maildrop/archive.py`'s `MailDropArchive` — `message_store.py`
deleted, nothing else imported it. The new schema covers every field
from the P27.3 table (`tnc_number`, `bbs`, `mtype`, `tnc_stamp`,
`device`) plus a `fingerprint` column (hash of
`mtype|to_call|from_call|bbs|subject|body`, deliberately excluding the
TNC timestamp, which is set at store time and would differ after a
restore-then-collect round trip) as the real duplicate-detection key —
the TNC's own message numbers are **not** durable across a power-cycle
and are only unique within one power-on period, so `id`/`fingerprint`
are the archive's real keys, never `tnc_number` (kept only as a
"last-session hint" attribute, exactly as CLAUDE.md's existing warning
about this already said a future archive must do). See
`test_maildrop_archive.py` for the dedup/`missing_in_tnc()` coverage.
**Still open, deliberately, per P38.3's scope cut:** nothing calls
`archive.add()` yet — see the "MailDrop session mask" item above.

### Test suite speed — ✅ DONE (P61, 2026-09-27)

`docs/P61_Test_Suite_Speed_Spec.md`. Full suite: 618s -> 42s (measured
on the same machine, before/after, `--durations=15` both times — see
the session's own final report for the two full outputs), test count
708 -> 712 (four new tests, none removed).
- `conftest.py`'s new autouse `dispose_main_windows` destroys every
  `MainWindow` any test built at teardown (`removeEventFilter()` +
  `deleteLater()`, never `close()`) instead of leaving it merely
  hidden with its application-wide event filter still installed — the
  single biggest cost (a real, measured quadratic slowdown: 0.11s to
  build a fresh `MainWindow()` with none alive, 2.62s with 11
  undisposed ones still around). Caught two genuinely leaking fixtures
  in the process: `test_main_window_packet.py`'s `TestModeInstanceFactory.
  window` (`return w`, no teardown at all) and a bare `MainWindow()` in
  `test_signal_screen.py` with no cleanup whatsoever.
- `conftest.py`'s new autouse `isolate_qsettings` closes the SAME class
  of gap P48 closed for the INI config file, at QSettings's own
  window-geometry/splitter-size persistence — `QSettings("OE3GAS",
  APP_TITLE)`'s two-argument form always uses `NativeFormat` regardless
  of `setDefaultFormat()`, and on Windows that is the registry, which
  `setPath()` cannot redirect at all (confirmed by direct testing —
  the P61 spec's own recipe was measured on Linux, where it happens to
  work). Fixed by monkeypatching the name `QSettings` inside
  `pk232py.ui.main_window`'s own module namespace instead.
- `serial_manager.py`'s literal `time.sleep(<number>)` calls inside the
  detection chain (`_init_tnc_thread()`), recovery (`_recovery_thread()`),
  Host Mode entry (`_enter_host_mode_thread()`) and exit
  (`exit_host_mode()`) are now named module constants (same values).
  `test_serial_manager.py`'s new `fast_serial_timing` fixture
  (`pytestmark`, applied to `TestTncStateDetectionChain`/
  `TestRecoverySequence`/`TestXonFlowControlDetection`/
  `TestStep3EchoDetection`/`TestConverseModeDetection`/
  `TestFreshBootDefaults`) scales every one of them by one shared
  factor (1/30) via `monkeypatch.setattr` — verified, not assumed, that
  the fixture still catches a real regression: 14 of the 15 targeted
  tests were each deliberately broken in production code, one at a
  time, and confirmed red with the fixture active, then restored (the
  15th test's own class only has two tests total). One break (removing
  a redundant retry's own write, rather than disabling its recognition)
  did NOT go red on the first attempt — the chain's own fallback
  structure silently compensated via a different step; worth knowing
  as a general lesson about testing redundant/self-healing code, not a
  defect.
- `main_window.py`'s main `QToolBar` gained `setObjectName("mainToolBar")` -
  found as a side effect of profiling (`QMainWindow::saveState():
  'objectName' not set for QToolBar ... 'Main'`), unrelated to the
  speed work itself but free to fix alongside it.
**Noted, not fixed (out of scope — a different module, already has its
own scaling mechanism):** `test_maildrop_session.py`'s
`TestRecoveryPath::test_ends_in_failed_when_host_mode_never_confirms`
(1.26s) and `TestHappyPathLifecycle::test_open_list_read_send_kill_leave`
(0.52s) surfaced at the top of the "after" `--durations=15` output
purely because everything else got so much faster — they were already
this slow before P61. `maildrop/session.py`'s own `_fast()` test helper
already shrinks `MailDropSession`'s class-attribute timeouts to a 1.0s
floor per constant; lowering that floor further is a separate,
unrequested change to a module P61's own spec never named.

### MDMON eavesdropped traffic — could it be archived without a session at all? (P38.3, open, unmeasured)

`MDMON` (already a MailDropConfig field, sent during upload) makes the
TNC announce mail activity from OTHER stations' MailDrop sessions
passing through — in principle traffic pk232py could observe without
ever opening its OWN MDCHECK session (which suspends packet operation
for its whole duration, docs/P38_MailDrop_Archive_Spec.md "Warum
optional"). **Unmeasured:** what exactly `MDMON` announces (full
messages, or just activity notices?), on which Host Mode/verbose
channel, and whether it says anything `MailDropEntry`/`archive.add()`
could actually use. Worth a dedicated `tools/hw_check.py` probe before
building anything — do not assume the answer either way.

### `SignalMode.handle_frame()` reports any CMD_RESP as a SIAM result — ✅ FIXED (P18.2, 2026-09-22)

Found 21.09.2026 (P16.3, investigation only — no code changed at the
time) while checking the codebase for the same class of bug as T86's
stale-`HP\x00` frame (a Host Mode response mistaken for the answer to a
different query because it was matched by arrival order/type, not by
mnemonic — see the CLAUDE.md Host Mode gotcha).

- `src/pk232py/modes/signal_analysis.py::SignalMode.handle_frame()`
  used to call `on_result()` for any `FrameKind.CMD_RESP` frame whose
  text was non-empty and did not end in `\x00` — **without checking
  `frame.mnemonic`/`frame.data` against anything Signal mode itself
  queried.** `ModeManager` forwards every `CMD_RESP` to whichever mode is
  active, so a delayed `HP\x00` HPOLL flush, an ACK/NAK for an unrelated
  command, or an attribute-query echo like `PXN` could all be surfaced as
  a bogus SIAM result.
- Two more contradictions surfaced while scoping the fix (P17, still
  unresolved at the time): `handle_frame()` itself accepted BOTH `$4F`
  CMD_RESP and `$50` LINK_MSG as a result, and the two documented output
  formats did not match either (`BAUDOT 45 170` per the module docstring/
  STABO manual vs. `0.47: 50 Baud, Baudot, RXREV OFF` per the mockup). A
  filter could not be written without first measuring what the TNC
  actually sends.

**Measured and fixed (T113/P18.2, 2026-09-22):** `tools/hw_check.py siam`
settled it on real hardware — results are `$50` LINK_MSG on channel 0
ONLY, split across exactly two frames, in the mockup's format. `handle_frame()`
now never calls `on_result()`/`on_result_parsed()` for a CMD_RESP frame at
all (not "most of them" — none), and LINK_MSG fragments are assembled in
`_siam_buffer` until a line ending is seen. See CLAUDE.md's SIAM gotcha
and `test_signal_analysis.py` for the fixture-based tests (real T113
frames, in the order they were received).

**Follow-up — ✅ DONE for display (P19.4, 2026-09-22):** `SignalScreen` is
now wired to `SignalMode.on_result_parsed`, shows the latest result and
a "Best so far" (highest confidence this session). **Still open:** what
"OK — switch to the detected mode" itself acts on when several results
have arrived — the latest, or the best-so-far? The button's `can_switch`/
label logic (`_show_result()`) still only looks at whatever result was
shown last, not the tracked best. See Testplan T114 (hardware, still
OPEN) and `test_signal_screen.py`.

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

### Tech debt — keyboard-redirect eventFilter copied across five screens (P41, 2026-09-24)

Five opmode screens (`amtor_screen.py`, `morse_screen.py`,
`opmode_rtty_base.py` — shared by Baudot/ASCII, `packet_screen.py`,
`pactor_screen.py`) each carry their own, near-identical `eventFilter()`
that redirects keypresses to `tx_input`, plus MainWindow's OWN, larger
app-wide `eventFilter()` doing the same redirect for Host Mode generally
(the actual mechanism a real keystroke goes through — see the P41
gotcha in CLAUDE.md's UI section for why the per-screen copies are not
the live code path for most fields). P41 unified the "is this a
keyboard-input widget" CHECK into one shared function
(`screen_focus_controller.is_keyboard_input_widget()`), same pattern as
the frame-decoder and wakeup-message duplication this project has hit
before (see "Tech debt — two parallel Host Mode frame decoders" above)
— but the surrounding redirect LOGIC itself (the `if not is_input: ...
tx.setFocus(); sendEvent(tx, event); return True` shape) is still six
separate copies (five screens + MainWindow), not one. Consolidating
those into a single reusable filter class is a larger refactor than
P41's bug-fix scope — not done here, filed for a future session.

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
| MAILDROP on/off (options row) | unresolved | Button built, no frame sent. Was distinct from the (now-disabled) `btn_maildrop` MDCHECK button — no longer a conflation risk since `btn_maildrop` no longer sends `MI` at all (P21.5). |
| MDMON | unresolved | Button built, no frame sent. |
| LITE | unresolved | Button built, no frame sent. |
| MailDrop-Login / MID | `MI` (both) | **Resolved by measurement, not by choice (P21, 22.09.2026):** `MI` is MFILTER, not MailDrop login (`tools/hw_check.py mi`: Host Mode `MI$80` = verbose `MFIlter $80`) — there never was a real MailDrop-login-vs-MID conflict on `MI`, because the MailDrop side of it was never MailDrop login to begin with. `btn_maildrop` is now disabled (P21.5); `MID` (Morse ID toggle) is unaffected. See CLAUDE.md's mnemonic table and the `MailDrop dialog` entry below. |

**`MI` = MFILTER, not MailDrop login — CONFIRMED (P21, 22.09.2026):**
`pk232_mnemonic_table.txt`'s name-to-mnemonic mapping listed `MI` as
MFILTER (not hardware evidence on its own — see
`docs/MNEMONIC_TABLE_NOTE.md`); `tools/hw_check.py mi` then confirmed it
on real hardware (Host Mode `MI` → `$80`, verbose `MFILTER` → `$80`,
identical). `main_window._on_packet_maildrop()`'s `build_command(b'MI')`
was frame-verified (T47, 2026-06-22) but never meaning-verified, and
never actually logged in to the mailbox. Fixed in P21.5: `btn_maildrop`
disabled with tooltip "MailDrop dialog not implemented yet",
`_on_packet_maildrop()` is a no-op. A real MailDrop dialog/login path is
still needed — filed under "MailDrop management dialog" below.

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

### New Host Mode mnemonic scan (P20.A2, 2026-09-22)

`pk232_mnemonic_table.txt`'s scan failed (674/676 combinations got no
response at all — see `docs/MNEMONIC_TABLE_NOTE.md`); a proper re-scan is
now feasible with `tools/hw_check.py`'s working `query_host()` (mnemonic-
prefix correlation, pending-frame drain, P16.2). **Not a blind sweep of
all 676 combinations** — a bare mnemonic with no argument can still
trigger an immediate action on some TNCs (connect, disconnect, mode
switch, send, reset), not just answer with an error. Prerequisite before
writing the scan: a denylist of every action-triggering command in the
TRM, built from the manual, that the scanner skips outright — not
discovered by trial and error against the real hardware. Own package,
Priority 2, not started here.

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

**Higher stakes than "not yet audited" (P18, 2026-09-22):** the PK-232 has
no RAM buffer battery and resets to factory defaults on every power-off
(see CLAUDE.md's hardware gotcha) — so for every one of these 21 fields,
whatever value the TNC had before is gone the moment it is switched off,
regardless of whether the operator set it by hand at the terminal. There
is no "it'll keep the old value" fallback to fall back on. Auditing and
wiring each of these into `ParamsUploader._build_commands()` is therefore
not just cosmetic completeness — it is the only way any of these 21
settings ever reaches the TNC at all across a power cycle.

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

### MailDrop — persist mailbox to disk (REQUIRED for Beta, not optional, P18)

Confirmed 2026-09-22: the PK-232 has no RAM buffer battery and loses its
entire MailDrop mailbox on every power-off (see the "Operator finding"
note below). The `maildrop/` module currently has no save/reload path —
`btn_maildrop` only sends the MDCHECK login command (`MI`, T47-verified).
Without the app itself saving mailbox content to disk and reloading it
into the TNC at startup, MailDrop cannot survive a single power cycle,
which makes this a **Beta-blocking requirement**, not the "future/v0.2+"
nice-to-have it was filed as before this finding — see the old stub under
Priority 3 (Future / v0.2+), which now points back here.

**MYALTCAL truncation (found 21.09.2026, same hardware run):** sending
`MYALTCAL OE3GAS` came back as `MYALTcal now OGAS` — the TNC silently
truncated it to 4 characters. `MYALTCAL` is a 4-character AMTOR SELCAL, not
a callsign; the config field and its dialog should validate/format it as
one instead of accepting a full callsign that then gets mangled on upload.

**VHF/HF parameter values — confirmed and FIXED (P18, 2026-09-22):** the
suspected gap noted here after P16 (`VHFPacketMode` sends `MX 4` + `SL 10`
on activation; HF Packet's own `get_init_frames()` didn't reset them) is
now hardware-measured, not just derived from the code. `hw_check.py t112`
replayed the real VHF→HF Packet frame sequence: `SLOTTIME` read back `10`
(VHF's value) instead of HF's configured `30` — **confirmed**.
`MAXFRAME`'s own result was **inconclusive** on this run, because it
already equalled VHF's value (`4`) *before* the test started, so its
post-switch `4` proved nothing about `MX` specifically (Testplan T112).
Fixed in P18.1: `HFPacketMode.get_init_frames()` now also sends `MX`/`SL`
from HF Packet's own config (`docs/P18_HF_Init_SIAM_Spec.md`); `hw_check.py
t112` reworked in P18.3 to pre-set both parameters to a neutral value first
so a repeat run judges `MX` and `SL` separately, not conflated. Retest with
the fixed tool and code is still open (Testplan T112 status).
**General rule this confirms** (now in CLAUDE.md's Packet gotchas): any
parameter one band sets on activation, the other band must set too, or it
silently inherits whatever the last-active band left behind.

**MTEXT overwritten by config defaults on init — CLOSED, not a bug (P18,
2026-09-22):** the P15 finding (the parameter upload sent the saved
config's `MTEXT` even where the TNC already had its own text) raised the
question of whether the uploader should skip default/empty text fields so
a station's own on-device value survives an app-driven init. Now moot: the
TNC has no RAM buffer battery (confirmed by the operator, see below) and
loses ALL configuration on every power-off, so there is never a TNC-side
value worth preserving — always sending the saved config's `MTEXT` (and
every other field) is exactly correct.

**Operator finding, confirmed (P18, 2026-09-22): the PK-232 has NO RAM
buffer battery at all**, not an intermittently failing one. It resets to
factory defaults (`MYCALL PK232`, `EXPERT OFF`, `PACLEN 128`, `MAXFRAME 4`,
`FRACK 4`, stock `MTEXT`, an empty MailDrop mailbox) on **every**
power-off — this is normal operation for this unit, not something to
"check/replace" (superseding the 21.09.2026 operator note, which treated
it as a maybe-failing battery). Consequence: the app's own init sequence
is the TNC's only configuration source, and MailDrop content must be
saved/reloaded by the app itself or it is lost every time (see the
MailDrop entry under Priority 2).

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
| MailDrop management dialog | **Needed from scratch, not just extended (P21, 22.09.2026):** the tool-row `btn_maildrop` never sent a real MDCHECK login at all — `MI` is MFILTER (confirmed, see above), so `_on_packet_maildrop()` was querying a filter setting, not logging in. Disabled in P21.5 until a real dialog exists. A real MailDrop login must send `MDCHECK` in VERBOSE mode (the local terminal it opens has its own prompt, not `cmd:` — see `tools/hw_check.py`'s `Session.send_and_read_until_idle()`/`read_until_idle()` for the pattern), and needs the message-list/read/send/kill protocol that `tools/hw_check.py maildrop` (T116) is still measuring. Depends on that measurement completing first — see the MailDrop protocol layer note above. |
| CONPERM / MAILDROP / MDMON / LITE mnemonics | Confirm against the TRM / `pk232_mnemonic_table.txt` (neither was available in this session) before wiring real frames. |
| Interactive mock-GUI + hardware re-test | T87–T92 (Testplan.md) are software/headless-verified only. |
| No `VHFPacketConfig` (P19.3, 2026-09-22) | VHF Packet has no config-driven parameter set of its own — `VHFPacketMode.get_init_frames()` always sends the fixed `MX 4` / `SL 10` (and `HB 1200`), never anything from a dialog/INI. HF Packet's `HFPacketMode` gained config-driven `maxframe`/`slottime` constructor args in P18.1/P19.2; VHF's own docstring now states explicitly that it does NOT use those inherited parameters. Adding a real `VHFPacketConfig` (own dialog fields, own INI section, same wiring pattern as `HFPacketConfig`) is open — not attempted here, since it is a config/dialog feature, not a bugfix. |

**MailDrop protocol layer (P21, 2026-09-22):** depends on repeating the
T116 measurement with the fixed `tools/hw_check.py maildrop` (P21.3) — the
first run only got as far as confirming the mailbox prompt shape and the
SysOp command set before a tool-side safety bug cut it short (fixed).
Building a real MailDrop dialog/login path (see "MailDrop management
dialog" above) needs the real `S`/`R`/`K`/`L` command syntax and message
format from that repeat run, not guessed.

**Host Mode access to the mailbox (P21, 2026-09-22):** the STABO handbook
references Host Mode commands for `B` and `E`, but they were illegible in
the failed `pk232_mnemonic_table.txt` scan (see
`docs/MNEMONIC_TABLE_NOTE.md`) and have not been re-measured. All P21
MailDrop work used the VERBOSE-mode local terminal (`MDCHECK` at the
command prompt) — whether/how the mailbox is reachable from Host Mode is
a separate, later measurement.

### Betriebsart und Verbindung gehen beim Wechsel verbose <-> Host Mode verloren — open (P64, 2026-09-27)

**Beobachtung (Betreiber, 27.09.2026, Geraet unbekannt — beim Nachtest
festhalten):** Im verbose Modus mit VHF Packet eine BBS (TinyBox)
connected, dann `TNC -> Enter Host Mode` (Ctrl+H, P49).
1. Die App zeigt danach **nicht** die VHF-Packet-Maske, sondern Baudot
   RTTY.
2. Die bestehende Verbindung wird **nicht** erkannt — kein Kanal-Chip
   "connected", keine Partneranzeige.

**Ursache im Code (gelesen, nicht gemessen):**
- `_update_host_mode_ui(True)` aktiviert bei fehlendem aktivem Modus fest
  **Baudot RTTY** als Standard ("If no mode is active yet, activate Baudot
  as default"). Im verbose Modus fuehrt die App keinen ModeManager-Modus,
  also greift dieser Standard immer.
- Umgekehrt (Host -> verbose) setzt derselbe Slot beide Packet-Masken per
  `reset_channels()` zurueck und deaktiviert den aktiven Modus
  (`_modes._active_mode = None`). Beim naechsten Host-Eintritt ist die
  Information damit ebenfalls weg.
- Der Kanalzustand der Packet-Maske entsteht nur aus `$5x`-Link-Meldungen,
  die **nach** dem Host-Eintritt kommen. Eine Verbindung, die schon vorher
  bestand, meldet der TNC nicht erneut — die App erfaehrt nie davon.

**Gesichert (Betreiber, 27.09.2026):** Die AX.25-Verbindung bleibt beim
Umschalten bestehen — nach verbose -> Host -> verbose ging die Sitzung mit
der BBS normal weiter. Geraet beim naechsten Lauf festhalten
(`docs/DEVICES.md`).

**Soll — interne Verbindungstabelle (Vorgabe des Betreibers):**
Die App fuehrt eine eigene Tabelle der Verbindungen je Kanal (0-9:
Zustand free/calling/connected, Partnerrufzeichen, Pfad, seit wann) als
Parallelstatus zum TNC. Sie wird in **beiden** Modi fortgeschrieben und
bei jedem Wechsel mitgenommen:
- verbose: aus den Textmeldungen `*** CONNECTED to ...`,
  `*** DISCONNECTED: ...`, `*** ... busy`, `*** Retry count exceeded`
- Host Mode: aus den `$5x`-Link-Meldungen (heute schon ausgewertet, aber
  nur fuer die ChannelBar)
- Die ChannelBar und alle anderen Anzeigen lesen **nur** aus dieser
  Tabelle — eine Sache, eine Stelle; kein zweiter Zustand in der Maske.
- Die gewaehlte Betriebsart wird genauso gefuehrt und bei jedem Wechsel
  (verbose -> Host, Host -> verbose, Recovery) mitgenommen. Baudot RTTY nur
  noch, wenn nie eine Betriebsart gewaehlt wurde.
- `reset_channels()` beim Verlassen des Host Mode entfaellt; geleert wird
  die Tabelle nur bei echtem Verlust (Trennen vom TNC, TNC-Neustart /
  Banner, Recovery ohne Bestaetigung).

**Risiko: die Tabelle ist eine Annahme, der TNC ist die Wahrheit.**
Waehrend des Umschaltens (HOST 3 / Recovery) liest die App kurz nicht mit;
eine Trennung genau in diesem Fenster (Gegenstation trennt, Retry
exceeded) ginge verloren und die Tabelle zeigte "connected", obwohl der
Kanal frei ist. Deshalb:
- Bei jedem Wechsel einen **Abgleich** mit dem TNC, sofern eine
  Abfragemoeglichkeit existiert (siehe Messpunkte).
- Ohne gemessene Abfrage: Eintraege nach einem Wechsel als "unbestaetigt"
  kennzeichnen (sichtbar, z. B. gestrichelter Chip), bis eine Link-Meldung
  oder empfangene Daten sie bestaetigen.

**Unbekannt — zuerst messen (hw_check), nicht raten:**
1. Auf welchem Kanal liegt eine im verbose Modus aufgebaute Verbindung im
   Host Mode? (Annahme Kanal 0 — ungemessen.) Und umgekehrt: welcher
   Kanal ist nach Host -> verbose der aktive?
2. Wie fragt man den Verbindungszustand je Kanal ab? Kandidaten: im Host
   Mode Link-Status `$40`-`$4E` (siehe Backlog-Eintrag
   "`_make_host_frame()` misclassifies LINK_STATUS"), im verbose Modus
   `CONNECT` ohne Argument ("Link state is: ...") bzw. `CSTATUS` (STABO:
   "zeigt den Connect-Status von allen zehn Kanaelen"). Jeder Kandidat
   braucht einen Messnachweis je Geraet.
3. Welche Betriebsart ist im TNC nach `HOST 3` aktiv? Duerfen die
   Moduswechsel-Frames (`PA`, `VH`, `HB` ...) bei bestehender Verbindung
   erneut gesendet werden, ohne sie zu stoeren?
4. Wie sehen die verbose Meldungen bei mehreren Kanaelen aus (mit und ohne
   `CHCALL ON`) — steht die Kanalnummer im Text?

**Vorgehen:** zuerst ein Messpaket fuer `tools/hw_check.py` (Verbindung im
verbose Modus aufbauen lassen, umschalten, alle Frames aufzeichnen,
Kandidaten aus Punkt 2 abfragen, zurueckschalten), dann die Umsetzung:
Verbindungstabelle als Qt-freie Klasse mit eigenen Tests, danach
Anbindung an verbose-Textausgabe, Host-Link-Meldungen und ChannelBar.
Gegenstation: Direwolf + QtTermTCP ueber AGW (wie P62a Teil D) oder eine
erreichbare BBS.

**Reihenfolge:** nach P62a/P63 (APRS), sofern der Betreiber nichts anderes
festlegt.

**Messung ausgelagert nach P65 (2026-09-28):** Punkt 2 dieses Eintrags
(Verbindungszustand je Kanal abfragen) und Punkt 3 (Betriebsart, und ob
die Moduswechsel-Frames eine bestehende Verbindung stoeren) werden durch
`tools/hw_check.py link_carry`/`link_carry_host`
(`docs/P65_Link_Carryover_Measure_Spec.md`, Testplan T141/T142) konkret
gemessen — **noch offen (T141/T142 OPEN), keine Umsetzung in diesem
Schritt.** Neu gefundene Kandidaten fuer Punkt 2, bisher ungenutzt im
Code: TRM 4.3.3 Link Status Request (`HostModeProtocol.
cmd_link_status()`, baut den Frame schon, wird aber nirgends
aufgerufen) und TRM 4.3.2 `OPMODE` (`query_host(b"OP")`) fuer Punkt 3 —
beide jetzt Teil des Messpakets statt nur vermutet.

**Ursache gefunden, P66 (2026-09-28):** Der erste `link_carry`-Lauf
(T141, Geraet B) zeigte: die eigentliche Ursache fuer "Verbindung
nicht erkannt" (die urspruengliche Betreiberbeobachtung, B.1 oben) ist
**nicht** die Verbindungstabelle selbst, sondern dass der Host-Mode-
Eintritt (`pk232_hostmode_sub.py::enter_host_mode()`) nach einem
verbose `CONNECT` gar nie wirklich stattfand — der TNC stand in
Converse, `HOST 3`/`HPOLL Y` erreichten den Kommandointerpreter nie,
und der alte Erfolgstest akzeptierte das eigene Echo als Erfolg (siehe
`docs/P66_HostMode_Entry_From_Converse_Spec.md`, B.1/B.2). Behoben:
COMMAND-Zeichen vor `HOST 3` (escaped Converse/Transparent), Erfolg
erst mit echter OPMODE-Antwort. `link_carry_host` (T142, Geraet B)
bestaetigt danach: die Verbindung selbst uebersteht den Wechsel in
beide Richtungen, **sofern** der TNC beim Wechsel tatsaechlich im
Kommandomodus ist (nicht Converse) — genau das P66 jetzt sicherstellt.

**P67 = Verbindungstabelle mit CO-Abgleich**, aufbauend auf P66: die
interne Verbindungstabelle (Zustand/Partner je Kanal, siehe Soll oben)
wird jetzt gebaut, mit TRM 4.3.3 `CO` als Abgleichspunkt bei jedem
Wechsel (P66's eigener B.4-Befund — der aktive Kanal nach Host →
verbose folgt offenbar dem letzten `$4x`-Frame, noch nicht bestaetigt,
Teil D von P66 misst das) — nicht mehr "zuerst messen, dann bauen"
fuer Punkt 2/3 selbst, die sind jetzt gemessen; nur der aktive-Kanal-
Mechanismus (B.4) bleibt vor P67 offen.

### APRS mode (P63) — waiting on T138–T140 (P62, 2026-09-27)

The APRS TX mode itself (own screen, HF/VHF switch inside it, app-side
beacon `QTimer`, own UNPROTO ownership — decisions recorded at the top
of `docs/P62_APRS_Measure_Spec.md`) is **not started**. It needs Device
A and Device B measurements from `tools/hw_check.py aprs_query`/
`aprs_tx`/`aprs_reject` (Testplan T138–T140) first — VIA-path handling,
byte-exact info-field transmission, whether an over-PACLEN info field
splits into more than one UI frame, and how `CFROM NONE` actually
behaves from both sides, none of which were ever measured before this
package. Device C is optional (T138 only, per the spec's own Teil E).

**Key finding, Device B, 27.09.2026 (T139 R4, P62a):** confirmed — an
over-PACLEN info field DOES split into more than one UI frame (204
chars at PACLEN 64 → 4 frames, split exactly at the PACLEN boundary).
**The APRS mode must therefore own PACLEN, querying and setting it the
same way it already owns UNPROTO** — it cannot assume whatever value
the TNC happens to have configured for something else. Use the largest
value `tools/hw_check.py aprs_query`'s A.7 finds actually accepted
(from that run's own log — A.7 probes 128/255/256/0 verbose; A.8
probes the Host Mode `PL` mnemonic, still only Konfidenz M in the
firmware matrix) as the mode's own configured PACLEN, not a guessed
constant.

### CONOK comment in `packet_hf.py` is misleading (P62, 2026-09-27)

`modes/packet_hf.py:361`'s comment ("if CONOK is OFF (no auto-accept)")
implies the PK-232 has a CONOK parameter that gates auto-accepting
Packet connects. **It does not** — `CONOK` does not exist anywhere in
the PK-232 command set (checked against the full 194-command STABO
superset, `docs/PK232_firmware_matrix.md` §4; see P62's own "Korrektur
zur Chat-Vorarbeit"). Not fixed here (hw_check's own rule 6: measure,
don't correct main-line code from a measurement session) — correct the
comment once T140 (`aprs_reject`, this package) actually shows what
"Connect request" and a real incoming-connect attempt look like on
this firmware, rather than guessing a replacement explanation now.

### Tech debt — two `build_command()` implementations (P62, 2026-09-27)

`comm/hostmode.py:145` (`HostModeProtocol.build_command()`, a thin
static wrapper) and `comm/frame.py`'s own `build_command()` (which the
wrapper delegates to) are two names for the same frame-building
concept, in two files — found while adding `aprs_query`/`aprs_tx` to
`tools/hw_check.py` (P62), which deliberately reuses the existing
`HostModeProtocol.cmd_unproto()`/`.build_command()` surface rather than
adding a THIRD builder. Not fixed here — a real cleanup needs checking
every existing call site of both, which is its own package, not a side
effect of an APRS measurement session.

### APRS — Phase 2

| Item | Notes |
|------|-------|
| MHEARD panel: show APRS stations | Populate from received Mic-E + Position frames |
| ~~Beacon TX~~ | **SUPERSEDED (P62, 2026-09-27).** "UNPROTO APRS VIA WIDE1-1,WIDE2-1; periodic timer" bolted onto the Packet screen is replaced by a dedicated APRS mode design (own screen, HF/VHF switch inside it, an app-side `QTimer` beacon timer rather than TNC `BEACON`/`BTEXT`, UNPROTO owned by whichever mode is active) — see the operator decisions recorded at the top of `docs/P62_APRS_Measure_Spec.md`. The mode itself is P63, built on P62's measurements (`aprs_query`/`aprs_tx`/`aprs_reject`, Testplan T138–T140). |
| ~~Beacon config UI~~ | **SUPERSEDED (P62, 2026-09-27)** — same reason as Beacon TX; a beacon config UI belongs to the P63 APRS mode's own screen, not the Packet screen. |
| Mic-E lon decode verify | Test with west-of-0° and lon > 100° stations |
| Testplan T65 — APRS buffer cleared on mode switch | ⬜ OPEN. Switch VHF Packet → Baudot RTTY → back to VHF Packet; expect RX display empty, `_packet_raw_frames` cleared, APRS button reset to inactive. Not yet run. |

### Older Test Block items still open (P58 completeness pass, 2026-09-26)

Found while cross-checking every Testplan.md `⬜ OPEN` case against this
file (P58) — pre-P-numbered "Test Block" items that had never been
carried into the Backlog:

| Testplan case | Notes |
|---|---|
| T19–T22 (Test Block 3 — Macros) | Formal test of macro buttons, edit dialog, `[^D]` inside a macro, and paste — only "basic macro send confirmed manually" so far, no structured pass. |
| T28 (Help Viewer content) | Content review, not a code gap — see CLAUDE.md's own "Offen (Help-System Folge, v0.2)" note (`help_amtor.md` proof-read; `help_shortcuts.md`/`help_controls.md` as their own files). |
| T52–T58 (Test Block 7 — PACTOR / AMTOR Identity Labels) | Wiring the PACTOR/AMTOR parameter dialogs to real TNC commands — CLAUDE.md's "Before beta" item 10. Not started. |
| T123 (typing into every Packet-screen field, live GUI) | `is_keyboard_input_widget()` (P41) is software-verified against the real app-wide event filter (`QTest.keyClick()`) and reproduces the 24.09.2026 hardware finding (Dest-field typing landing in the TX window) — never run through the actual live GUI. Same "software proves the logic, hardware/live-GUI still needed" gap as the Packet Connect/Disconnect/MHEARD hardware retests above. |

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
- **Correction (P58, 2026-09-26):** T66–T68 (FAX closed-loop decode for
  weather/pattern/text) were already added to `Testplan.md` — this note
  was stale. All three are still `⬜ OPEN (needs local run)`, which is
  the actual remaining work here, not writing the test cases.
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

### MailDrop prompt — when does the device-name bracket switch? (P31, 2026-09-23)
- `PromptInfo.bracket` (`maildrop/protocol.py`, P31.1) now records whether a
  given mailbox prompt used the round `(...)` or square `[...]` device-name
  bracket. Both forms are hardware-confirmed (see CLAUDE.md's "MailDrop
  facts" section), and each one so far has lined up with a specific EPROM
  the operator had installed at the time (round = 11.09.1995/PACTOR-gen,
  square = 01.08.1991/MBX-gen) — but that is only two data points from two
  sessions, not a settled rule.
- Open: is the bracket form purely a function of the installed EPROM (in
  which case it would never change mid-session), or can it also depend on
  something else (a parameter, a code path, an as-yet-unidentified firmware
  state)? Log `bracket` on every future `maildrop_session` hardware run
  (already wired into `tools/hw_check.py`'s summary, P31.3) and collect
  anomalies before treating "bracket ⇔ EPROM" as confirmed.

### P29 — wakeup CR-fallback — CLOSED (P43, 2026-09-25)
- The wakeup logic's CR-fallback classification (`tools/hw_check.py`,
  `"TNC already awake -- needs CR (see P29)"`, exercised by
  `test_hw_check.py`) remains a reasonable thing to have — a TNC that is
  already past the `*` prompt and just needs a bare CR to re-sync is a real
  case worth classifying distinctly.
- **Priority lowered (2026-09-23):** P31's investigation of the 23.09.2026
  session failures found the actual root cause was **not** this code path
  at all — it was the TNC hardware hanging outright (see CLAUDE.md, "The
  PK-232 can hang and stop responding to anything at all"). The 18:01
  wakeup failure that originally motivated treating P29 as urgent is now
  explained by that hang, not by any gap in the CR-fallback classification
  itself.
- **Closed (2026-09-25):** the main application's own `_init_tnc_thread()`
  now has exactly this CR-fallback built in as step 2 of the P43 four-step
  TNC-state detection chain — a `*`-silent, already-awake TNC is confirmed
  verbose by a single bare CR, before ever trying the Host Mode probe
  (step 3). See CLAUDE.md's "There is no cmd: prompt in Host Mode" gotcha
  (P40) and the new P43 detection-chain gotcha for the full picture.
  `tools/hw_check.py`'s own CR-fallback classification stays as-is — it is
  a separate codebase from the app, and this closes only the "does the
  concept exist anywhere that needs it" question, not a request to unify
  the two.

### What state was the TNC in at the start of the 23.09.2026 mdcheck_scan run? (P34, open)
- The whole verbose phase of a `mdcheck_scan` run on Device B got nothing
  back but each line's own echo, never a `cmd:` prompt (see CLAUDE.md's
  "Echo without execution" gotcha) — `PACKET`, `MYCALL`, `XMITOK`,
  `MDCHECK`, the subject/body lines and `/EX`, `B` all just echoed.
  Entering and leaving Host Mode cleared it again, so this is a starting
  *state*, not a hardware fault (unlike the separate PK-232-hang finding).
- Open: what state was this — Converse (the best guess, since it fits
  "echoes typed text") or something else (Transparent mode, a leftover
  half-typed command)? Unknown, and not reproduced on purpose.
- If this happens again, measure it deliberately rather than just
  recovering past it again: before running `normalize()`'s resync, send a
  single distinguishing probe (e.g. a command only Converse answers a
  particular way to) and log the raw response, so the state can be
  identified with evidence instead of "most likely". `tools/hw_check.py`
  now recovers from this safely either way (P34,
  `confirm_command_prompt()`), so there is no urgency — this is a curiosity
  worth settling if it recurs, not a blocker.

### Flaky test found and fixed — Qt cross-thread signal race in test_maildrop_session.py (P36, 2026-09-23)
**Reproduced deterministically** (no `pytest-randomly` is installed — test
order is already fixed by collection order, so the flake is purely a
timing race, not order-dependence): looping `.venv\Scripts\python.exe -m
pytest -q -x` caught
`TestRecoveryPath::test_ends_in_failed_when_host_mode_never_confirms`
failing on run 1 of 20 (roughly 1 in 10, matching the earlier
in-session observation) with
```
assert 'verbose mode' in "no mailbox prompt after MDCHECK: 'MDCHECK\\r\\n'"
```
— `rec.failures[-1]` was the FIRST failure `open()` had already reported,
not the SECOND one the recovery path reports when Host Mode never
confirms.

**Root cause (confirmed, not guessed):** `MailDropSession._set_state()`
writes `self._state` as a plain Python attribute and THEN calls
`self.state_changed.emit(...)` — the attribute becomes visible to
another thread (no Qt marshalling needed) strictly *before* the signal
is even queued, let alone delivered. `_enter_host_mode_or_fail()`'s
failure branch does `self._set_state("FAILED")` immediately followed by
`self.failed.emit("...verbose mode...")` on the next line — two
DIFFERENT signals a hair apart on the worker thread. The test polled
`session.state` (the plain attribute, races ahead) and, the instant it
read `"FAILED"`, immediately asserted on `rec.failures[-1]` (populated
only once the `failed` signal has actually been delivered via
`QApplication.processEvents()`) — a classic TOCTOU gap between an
un-marshalled attribute and a queued signal for a LATER piece of state
from the SAME worker function. Confirmed empirically, not by "increasing
a timeout and hoping": `threading.active_count()` stayed at 1 after 30
scripted `open()` cycles with no explicit joins (see below) — ruling out
an actual leaked/lingering thread as the cause, isolating it to signal-
vs-attribute ordering instead.
- **Not a thread leak** (checked per the task): `MailDropSession._start()`
  spawns a `daemon=True` thread with no reference kept and no `.join()`
  anywhere, by design (fire-and-forget). Measured directly: 30 scripted
  `open()` cycles with no joins, `threading.active_count()` returns to 1
  (just MainThread) within half a second of settling. Worker threads
  finish correctly; they just don't finish *synchronously with* the
  observable a test was polling.
- **Not a wall-clock-dependent timeout being too short**, either — the
  failure's own assertion text proves the WRONG (but real, already-
  delivered) failure message was read, not that a wait timed out. The
  `_fast()`-shrunk class-attribute timeouts (`HOST_MODE_TIMEOUT_S = 1.0`
  etc.) remain necessary bounds against a genuinely hung worker and were
  left untouched — raising them would not have addressed this race at
  all, and per instruction they were not touched as a "fix".
- **Fix (isolates the actual race, `test_maildrop_session.py`):** every
  `_pump_until(lambda: session.state == ...)` wait in the file — 9 call
  sites — now waits on the Qt-signal-delivered `rec.*` data the test
  goes on to assert next (`rec.prompts or rec.failures`,
  `rec.state_changes and rec.state_changes[-1] in (...)`, or, for the
  one CONFIRMED flake, the exact content:
  `rec.failures and "verbose mode" in rec.failures[-1]`), instead of the
  plain `session.state` attribute. A signal only becomes observable to
  the test after an actual `processEvents()` round-trip, which — every
  case checked — always happens after the worker thread's own trailing
  work for that same signal (including releasing its busy flag) is
  already done; the plain attribute does not carry that guarantee.
  `session.state` is still asserted afterwards as a plain sanity check,
  now safe because the signal-based wait has already proven the worker
  is done. Verified: 60/60 repeated runs of the file green after the
  fix (`.venv\Scripts\python.exe -m pytest
  src/pk232py/tests/test_maildrop_session.py -q`, looped), versus a
  reproducible ~1-in-10 failure rate before it.
- **General lesson — Qt-Threading-Rennen sind wiederkehrende Kundschaft:**
  any test elsewhere that polls a `MailDropSession`/similar QObject's
  plain Python attribute (not a signal) as its ONLY synchronization
  point, then immediately asserts on a signal-delivered value the same
  worker function sets *later*, is exposed to the same class of race.
  Watch for this pattern in any future `MailDropSession`-mask (UI) work
  or other QObject-with-background-thread code — prefer waiting on the
  actual signal-delivered data over a plain attribute whenever a test's
  very next assertion depends on it.

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
- ~~TNC mailbox functionality (`maildrop/` directory planned)~~ — the
  save/reload-mailbox part of this is now a **Beta-blocking requirement**,
  not a v0.2+ nice-to-have; see "MailDrop — persist mailbox to disk" under
  Priority 2 (P18, 2026-09-22, no RAM buffer battery confirmed).

---

## Completed (2026-09-26 — P55–P57: UI findings from the test run, font/layout corrections, chip editor focus)

Three sessions of `docs/P55_UI_Befunde_Spec.md`,
`docs/P56_Font_And_Layout_Spec.md` and `docs/P57_Chip_Editor_Focus_Spec.md`,
all from operator screenshots on 25./26.09.2026. Full detail in
CLAUDE.md's Packet and UI-PyQt6 gotchas; no new Testplan entries beyond
what P52–P54 already added (P55–P57 are unit-verified UI fixes with no
dedicated hardware test case).

| Item | Notes |
|------|-------|
| P55.A — MHEARD showed a date/time instead of the callsign | Two independent causes: `_extract_partner()` split on the FIRST colon in a message, landing inside the TNC's own CONSTAMP/DAGSTAMP `HH:MM:SS` timestamp (fixed with `rsplit`); `_parse_mheard_line()` never accounted for a leading DAYSTAMP date token (fixed by stripping it). |
| P55.B — TX echo missing from the channel's own RX view | `_on_packet_tx_enter()` wrote directly into `rx_display`'s cursor instead of through `append_channel_data()` (P50) — fixed by routing it through that shared path. |
| P55.C — RX font changed switching ALL/CH | Introduced a module constant `_RX_FONT` for every RX `QTextDocument`. **Corrected in P56.A** (below) — the constant itself was a second, independent font source. |
| P55.D — firmware release label stuck at "unknown" | Was parsed from `SerialManager.tnc_banner` (frozen at the P43 detection chain's own read); fixed to parse from the fully-collected P49 banner buffer instead, inside `_finish_banner_collection()`. |
| P55.E — "opmode mask doesn't fill the window" | Investigated (measured a real `MainWindow` + `BaudotScreen`, non-maximized) — no bug reproduced; `apply_tooltips()` got a defensive `Expanding` size-policy assertion anyway. **Corrected in P56.B** (below) — the measurement itself was the gap; a real bug existed elsewhere. |
| P55.F — two timestamp sources | Documented that CONSTAMP/DAGSTAMP (TNC's own link-message stamp) and `show_timestamps` (PK232PY's own added prefix) are independent — both dialog tooltips now cross-reference this. |
| P56.A — **P55.C's own fix was itself a second font-source bug** | `_RX_FONT` fixed the ALL-vs-CH mismatch by pinning every per-channel document to a hardcoded constant, independent of the operator's Appearance setting — ALL view (rx_display's own original document) kept tracking Appearance correctly, every per-channel document did not. `_RX_FONT` deleted; a new `PacketBaseScreen.apply_rx_font()` pushes the Appearance font onto every RX document, called from `MainWindow._apply_appearance()` — now the one and only font source. |
| P56.B — **the P55.E "could not reproduce" finding was wrong** | P55's own measurement used a non-maximized `BaudotScreen`, which never had this bug. Measured against a real `MainWindow` at 2560×1440 (matching the screenshots): only the Packet screens had a genuine bug — `PacketBaseScreen._build_ui()` added its RX/TX splitter AND its status bar with neither given an explicit stretch factor, an ambiguity Qt resolved by giving the status bar ~683px instead of its ~19px natural height. Fixed with one added `stretch=1` on the splitter. Every other screen was checked the same way and never had this. **Lesson (also in CLAUDE.md now):** a test that only checks a declared `QSizePolicy` proves nothing about actual geometry — `test_opmode_screen_layout.py` measures real pixel positions after `resize()`/`show()`/`processEvents()` instead. |
| P57.1 — chip editor did not close on channel switch | Chips are `NoFocus` (P41), so a click on a different chip never fires the editing chip's own `focusOutEvent` — the existing "losing focus cancels like Esc" rule never triggered. New `ChannelBar.close_open_editor()`, wired into `_select()` (chip click, `set_current()`, `step()`), `reset()` (mode switch, Host Mode exit), and the existing `MouseButtonPress` handling in `PacketBaseScreen.eventFilter()` (click into `tx_input`/`le_unproto`/`combo_monitor`/`combo_hbaud`). |
| P57.2 — open editor's amber border looked missing | Investigated with pixel-level `QWidget.grab()` rendering, including reproducing the exact click-away sequence — the border (`#e8b23a`, 2px) rendered correctly in every case tried. No code change made; kept as a pixel-level regression test. |

**Verification:** full suite green throughout, growing to 674 passed by
the end of P57. All three sprints unit/pixel-verified only — no
real-hardware step was required for any of them (nothing here talks to
the TNC).

---

## Completed (2026-09-25/26 — P52–P54: echo detection, converse mode, port configuration)

Three sessions replacing `docs/P51_Pruefdurchgang_Befunde_Spec.md`'s
never-implemented Teil A (see the note at the top of this file) —
`docs/P52_Echo_And_Read_Timing_Spec.md`,
`docs/P53_CtrlC_And_Verify_Readpath_Spec.md`,
`docs/P54_Port_Settings_Flow_Control_Spec.md`. Full detail in CLAUDE.md's
"Serial / Host Mode" and "TNC / firmware v7.1" gotchas; Testplan.md
T133–T135.

| Item | Notes |
|------|-------|
| P52 — an echo is not a Host Mode response | The PK-232 echoes everything in verbose command mode, even binary Host Mode frame bytes — step 3's HPOLL query used to mistake its own byte-identical echo for a genuine `$4F` answer. Fixed with `is_hpoll_echo()` (checks length AND the mandatory value byte a real answer carries). |
| P52 — reads were cut short before the expected prompt | The detection chain's own `read_until()` re-armed a short per-iteration deadline on every chunk of new data, which can only shrink the remaining timeout, never extend it — a multi-chunk `cmd:` response (normal at 9600 Bd) could be cut off. Fixed with `_read_until_prompt()`, one shared marker/idle/timeout implementation now used by the detection chain and `write_verbose_wait()`. |
| P53.A — `ParamsUploader.verify()` reported "no answer" despite a correct reply | Corrected root cause, not the one first suspected: no second reader competes for the port. The actual mechanism is a real, 20/20-reproducible race between `query_verbose_value()`/`detect_maildrop()`'s own transient `raw_data_received.connect()`/`disconnect()` pair and Qt's queued cross-thread delivery. Fixed by reading the response a new `_write_verbose_wait_text()` helper already assembles directly — no signal-based capture in the loop at all. |
| P53.B — reconnect failed with Baudot RTTY active before Host Mode | `HOST OFF` returns the TNC to whichever mode was last active, not the command prompt — Baudot/AMTOR/PACTOR all have a Converse state there (echoes everything, no prompt). New detection-chain step 2b (COMMAND char + CR); `exit_host_mode()` also sends the same resync immediately after leaving Host Mode. |
| P54.1/.2 — the app's own port configuration, not the TNC, was the fault | Operator's own PuTTY counter-test (same port/baud, no flow control) got a prompt with one Enter; the app did not. `connect_port()` used to clear DTR/RTS — fixed to assert both `True`, matching PuTTY's working configuration. Every port parameter now logged on open/close. |
| P54.3/.4 — software flow control (XON) as defense in depth | The PK-232's own boot banner proves it uses XON/XOFF — new detection-chain step 2c (XON + CR, then a second CR) for a TNC a stray XOFF left silent but still echoing. |

**Verification:** full suite green throughout each sprint. Both fixes in
each sprint cross-checked red-without-the-fix during implementation,
then restored. Hardware re-test (T133–T135) still open — see
Testplan.md.

---

## Completed (2026-09-25 — P47–P50: Packet channel polish, config isolation, Host Mode re-entry, per-channel RX layout)

Four sessions: `docs/P47_Link_Message_Routing_Spec.md`,
`docs/P48_Test_Config_Isolation_Spec.md`,
`docs/P49_Enter_HostMode_Banner_Spec.md`,
`docs/P50_Channel_Buffers_Layout_Spec.md`. Full detail in CLAUDE.md's
"Packet (HF / VHF)" and "Repo / tooling" gotchas; Testplan.md
T130–T132.

| Item | Notes |
|------|-------|
| P47 — link message appeared in the wrong channel | A channel-1 "DISCONNECTED" used to appear on the UI chip because that was the visible channel when the frame arrived. Fixed: `_route_packet_link_message()` routes by the frame's own CTL-nibble channel, through `append_channel_data()`; optional mirror into the UI channel via `show_link_messages_in_ui_channel` (off by default). |
| P48 — a test could silently overwrite the operator's real `pk232py.ini` | `ConfigManager()` with no path override reads/writes the REAL settings file; a test that mutated `MainWindow._app_config` with no reset wrote a real value onto disk and leaked into later tests. Fixed for good: `tests/conftest.py`'s autouse `isolate_config_path` fixture redirects every `ConfigManager()`'s default path to a throwaway file, for every test, whether or not it touches config at all. |
| P49 — no way back into Host Mode from an existing verbose connection | New `Enter Host Mode` menu action (Ctrl+H) — decides upload-outstanding vs. already-uploaded vs. Fast-Init-skipped the same way a fresh connect would. Also fixed a torn boot banner (interleaved with the app's own `[SYS]` lines) with a short quiet-window collection buffer, and filtered stray control bytes from the mirrored display. |
| P50 — per-channel RX documents, resizable TX, MHEARD auto-population | Replaced the old single-document append-time ALL/CH filter with one `QTextDocument` per channel + a merged ALL document, so switching to a channel shows its FULL history, not just what arrives afterward. RX/TX is now a `QSplitter` (resizable, persisted). MHEARD gains partners from live link messages, not only a manual Refresh. Compact `"n│"` ALL-view tag replaces the old `[CHn]` form; timestamps optional, off by default. A suspected channel-offset report could not be reproduced in code — root cause still open, needs a real hardware capture (see Testplan T132 Finding A). |

**Verification:** full suite green throughout each sprint. T130–T132
cover P47/P50's own live-sequence steps; hardware re-test for the
channel-offset report (T132 Finding A) is still open.

---

## Completed (2026-09-25 — P40, P43–P46: connection-sequence hardening)

Five sessions covering the connection state machine end to end —
`docs/P40_Upload_Before_HostMode_Spec.md`,
`docs/P43_TNC_State_Detection_Spec.md`,
`docs/P44_Chip_States_Init_Recovery_Spec.md`,
`docs/P45_Recovery_Feedback_Spec.md`,
`docs/P46_Recovery_Emergency_Connect_Spec.md`. Full detail in
CLAUDE.md's "Serial / Host Mode" and "TNC / firmware v7.1" gotchas.

| Item | Notes |
|------|-------|
| P40 — parameter upload silently timed out 68 times in Host Mode | There is no `cmd:` prompt in Host Mode at all — `ParamsUploader.upload()` now refuses outright (checks `is_host_mode` once) instead of timing out on every command; aborts after 3 consecutive silent commands; `verify()` spot-checks MYCALL/PACLEN/MAXFRAME against `AppConfig` right after upload. |
| P43 — a TNC left in Host Mode from a previous session was never detected | `is_host_mode` is the software's own belief, always `False` on a fresh `SerialManager` — closes Backlog's own P29 item (below). New active detection chain (`*` → CR → HPOLL query → give up), each step capped at 1.5s; `SerialManager.verbose_confirmed` only ever set on positive evidence. |
| P44 — a failed connect left a chip stuck amber forever; verbose terminal Enter did nothing; a killed-mid-frame TNC answered nothing | `CH_FAILED` (red flash) state added; `CH_CALLING` gets a synchronized pulse; verbose terminal Enter now sends a bare CR; detection chain gained step 3b (recovery sequence) for a TNC answering nothing at all. Also fixed a real cross-test crash (a free-floating `QTimer.singleShot()` firing against destroyed widgets) by parenting the timer to `ChannelBar`. |
| P45 — a failed init left the app looking connected; Recovery gave no feedback | `_update_connection_ui(True)` no longer jumps straight to "verbose" on port-open alone (new "connecting"/"error" states); `recovery()` now runs the P43/P44 detection chain itself and reports success/failure via `recovery_finished`, with the button relabelled "Recovery running..." meanwhile. |
| P46 — Recovery's own preamble was consumed by the still-running ReaderThread; "Connect" was ambiguous | New shared `_take_over_read_path()` helper, called before ANY write in both `_init_tnc_thread()` and `_recovery_thread()`. Recovery renamed to "Emergency Reconnect" and opens the port itself from any state; Connect/Disconnect/Host Mode/Recovery removed from the toolbar entirely (TNC menu only) since "Connect" there was ambiguous against the opmode screens' own station-connect concept. |

**Verification:** full suite green throughout each sprint. Closes the
P29 backlog item below (wakeup CR-fallback — the app now has its own
active detection).

---

## Completed (2026-09-24 — P42 Connect-in-chip sprint)

From `docs/P42_Connect_In_Chip_Spec.md`. Full detail in CLAUDE.md's
"Connect happens IN the chip" gotcha (Packet section) and Testplan.md
T33–T39/T83/T87/T93/T98/T99/T102/T123–T124. Builds on the P41
keyboard-redirect fix (`is_keyboard_input_widget()`), which this sprint's
first full-suite run also hardened — see the two P42 gotchas under
Known Gotchas / Repo-tooling in CLAUDE.md.

| Item | Notes |
|------|-------|
| Connect/Dest/…/Disconnect row removed | `btn_connect`, `btn_disconnect`, `cb_dest`, `btn_connect_dialog`, `dest_callsign()`, `set_dest_callsign()`, `add_dest_history()`, `on_connect_toggled()` all deleted from `packet_screen.py` — no identifier of theirs remains anywhere in the Packet code path (grep-verified). |
| `ChannelChip` (`packet_screen.py`) | Each chip is now a `QStackedLayout` of a button page and an inline `QLineEdit` editor page. Opens on: a second click on the already-current free chip, a double-click on any free chip, or "Connect…" from its context menu. Never opens for a busy chip or channel 0 (`UI_CHANNEL`) — enforced once, in `start_edit()`/`_show_menu()`. `Esc` or losing focus cancels; `Enter` validates via `maildrop.protocol.validate_callsign()` (red border + tooltip if invalid) and emits `connect_requested(channel, callsign)`. |
| `ChannelBar.request_connect()` / `.start_edit_first_free()` | New public methods — the former is the one place history-bookkeeping + `connect_requested` emission happens (used by both a chip's own Enter and the "Connect via…" dialog); the latter opens the FIRST free, non-UI chip's editor, prefilled — wired straight to `MheardPanel.connect_requested`, replacing the old `set_dest_callsign` wiring. |
| `PacketConnectDialog` redesign | Channel is now a fixed, non-editable label (was a `QSpinBox` the operator could disagree with the calling chip on) — it always comes from whichever chip's "Connect via…" opened it. Gained its own callsign field (`cb_dest` used to supply that). |
| `MainWindow._on_chip_connect_requested`/`_on_chip_disconnect_requested` | Replace `_on_packet_connect`/`_on_packet_disconnect`. No channel-0 guard needed in either — `ChannelChip` already refuses to ever emit `connect_requested`/open a context menu for it, so the old warning-dialog path is gone entirely, not just moved. |
| `set_link_state()` narrowed | Now only gates `btn_unproto` (T39) — its former Connect/Disconnect button-enable role is gone along with those buttons. `_on_packet_channel_changed()`'s dead `UI_CHANNEL` branch (there was nothing left to disable there) removed accordingly. |
| `_on_packet_tx_enter()` connected-check | `channel_bar.state(channel) == "connected"` replaces `btn_connect.isChecked()`. |
| Ctrl+D disconnect, Enter-opens-edit | New: Ctrl+D disconnects the current busy channel (Packet has no `[^D]`/TxController concept to collide with); Enter in `le_unproto`/`combo_monitor`/`combo_hbaud` (none had a `returnPressed` behaviour of their own) opens the current chip's editor if none is already open. |
| Tests | `TestChipConnectFlow` (9 new cases, `test_packet_screen.py`); T98/T99/T102 rewritten in `test_main_window_packet.py` for the new UI (old button-based assertions replaced with chip/Unproto-state equivalents); two P41 `TestKeyboardFocusHandling` tests updated from `cb_dest.lineEdit()` to a chip's `.editor`. |
| `tooltips.py` | `btn_connect`/`btn_disconnect` global entries removed (PactorScreen's `SCREEN_TOOLTIPS` override was already the only one ever applied in practice — Packet no longer has these attributes at all). |
| P41 fixture-teardown hang found and fixed | `test_main_window_packet.py`'s `wired_vhf` fixture teardown (added in P41, never run against the file's full suite until this sprint) called `w.close()` on a `MainWindow` whose stub `_serial.is_connected` is hardcoded `True` — `closeEvent()` pops a real, un-clickable `QMessageBox` under the offscreen QPA platform, hanging the whole pytest process forever. Fixed: flip `is_connected = False` before `close()`, plus `deleteLater()` + `processEvents()` to stop the closed-but-undestroyed window's timers from slowing down later tests' `show()`/`activateWindow()` calls. See CLAUDE.md's two new Repo/tooling gotchas. |

**Verification:** full suite (`.venv\Scripts\python.exe -m pytest
src/pk232py/tests/`) — 509 passed, ~90s, including the newly-fixed
`test_main_window_packet.py` run to completion for what appears to be the
first time since P41 added the `wired_vhf` teardown. `docs/mockups/
packet_screen.py` + `pr_chip_normal.png`/`pr_chip_edit.png` (operator-
provided reference, not production code) committed alongside.
Hardware re-test (type a callsign into a free chip, Enter, verify
connection; then Ctrl+D) still open — left for the operator per the
spec's Definition of Done.

---

## Completed (2026-09-22 — P17/P18 hardware measurement + fixes)

Hardware results and code fixes from `docs/P17_HW_Measure_Spec.md` and
`docs/P18_HF_Init_SIAM_Spec.md`. Full detail in Testplan.md T111–T114 and
CLAUDE.md's "TNC / firmware v7.1" and "Packet (HF / VHF)" gotchas.

| Item | Notes |
|------|-------|
| T111 — PASSALL, Host-Mode-command level | ✅ PASS. `PX Y` toggles PASSALL, `PS` (PASS) unaffected, restore verified. GUI click-through in the running app stays open (Testplan T111). |
| T112 — VHF→HF Packet MAXFRAME/SLOTTIME | ❌ FAIL, confirmed for SLOTTIME (read back VHF's `10`, not HF's `30`); MAXFRAME's own first-run result was inconclusive (already `4` before the test started). Fixed: `HFPacketMode.get_init_frames()` now sends `MX`/`SL` from HF's own config (constructor args, wired via `ModeManager.set_mode(mode_instance=...)`, P18.1); `hw_check.py t112` now pre-sets a neutral value and judges `MX`/`SL` separately (P18.3). Retest still open. |
| T113 — SIAM frame type / format | ✅ Measurement complete. Results are `$50` LINK_MSG on channel 0, split across exactly two frames, format `"<confidence>: <baud> baud, <mode>, RXRev <ON|OFF>"` (matches the mockup, not the old STABO-manual docstring example); continuous analysis, ~10s cadence. |
| `SignalMode` — SIAM result handling | Fixed per T113 (P18.2): CMD_RESP never treated as a result any more (closes the P16.3 finding for good); LINK_MSG fragments assembled in `_siam_buffer` until a line ending; buffer cleared on `get_activate_frames()`, discarded with a warning past 200 chars unterminated. Added `SiamResult` dataclass + `on_result_parsed` callback via `parse_siam_result()`; `on_result` keeps firing with raw text either way. Module docstring corrected to the hardware facts. |
| No RAM buffer battery (operator-confirmed) | The PK-232 resets to factory defaults on **every** power-off, not intermittently — supersedes the 21.09.2026 "check/replace the battery" note. Closes the P15 MTEXT-overwrite question (nothing device-side to preserve). Elevates the 21 P13-deferred upload fields and MailDrop persistence in priority — see their respective Backlog entries. |

---

## Completed (2026-09-22 — P19 mode instance factory + SIAM screen wiring)

From `docs/P19_Mode_Factory_Spec.md`. Full detail in CLAUDE.md's §7 and
"UI / PyQt6" gotchas, Testplan.md T114.

### P19.1 investigation — every real mode-instance-construction call site

Searched the whole repo for `set_mode(`, `set_mode_instance(`,
`HFPacketMode(`, `VHFPacketMode(`, and `MODE_BY_NAME[...]()`/`cls()` in
`mode_manager.py`. Result:

| Site | When it runs | Carried config before P19? |
|------|---------------|------------------------------|
| `main_window.py::_on_mode_selected()` | User picks a mode from the toolbar ComboBox | Yes, for "HF Packet" only (P18.1) |
| `main_window.py::_update_host_mode_ui(active=True)` | Host Mode entered with no active mode yet — always defaults to "Baudot RTTY" | **No** — found by this investigation, fixed in P19.2 (was harmless in practice, since "Baudot RTTY" needs no config, but would have silently done the same to any future mode needing it) |
| `mode_manager.py`'s own `mm.set_mode("HF Packet")` | Never — it's a docstring usage example, not real code | N/A |
| `ModeManager.set_mode()`'s `cls()` fallback | Whenever `mode_instance` is `None` | By construction, never — this is exactly the gap the factory closes |

No other call sites exist anywhere in `src/pk232py/`.

| Item | Notes |
|------|-------|
| `MainWindow._build_mode_instance(mm_name)` | New single factory method; both real call sites now route `mode_instance` through it (P19.2). Unit test uses `maxframe=2/slottime=20` (not the 1/30 defaults, which would pass even without the fix) and exercises both call paths with a stub serial; manually verified red without the fix before restoring it. |
| `HFPacketMode` constructor defaults | Now derived from `HFPacketConfig.maxframe`/`.slottime` directly (no import cycle) instead of repeating the numbers 1/30 — one source of truth (P19.3). |
| `VHFPacketMode` docstring | States explicitly that the inherited `maxframe`/`slottime` parameters are unused — VHF always sends its own fixed `MX 4`/`SL 10`. No `VHFPacketConfig` exists yet (Backlog: Packet v0.2 follow-ups). |
| `SignalScreen` — SIAM wiring | Was never wired to `SignalMode` at all (pure UI mockup). `MainWindow._wire_mode_callbacks()` now connects `SignalMode.on_result_parsed` → `SignalScreen.on_mode_result()` (never `on_result` — no screen-side parser to feed, and wiring both would double-handle every parsed line). Screen shows the latest result plus a "Best so far" (highest confidence this session, reset only by New Analysis/Cancel) — the P19.4 v0.1 minimum. Verified against the real T113 frame sequence (`test_signal_screen.py`). |

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