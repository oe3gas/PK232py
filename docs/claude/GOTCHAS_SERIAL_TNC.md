# PK232PY - Gotchas: Serial/Host Mode und TNC-Firmware

> Hardware-/Protokoll-Fallstricke, Messungen je Geraet (A/B/C).
> Ausgelagert aus CLAUDE.md (unveraendert uebernommen, Stand 2026-09-29).

## Known Gotchas & Pitfalls

A running collection of "you must know this or you'll break something" facts.
Grows over time.

### Serial / Host Mode

- **Direct serial I/O only — never a queue/worker for Host Mode frames.** The
  single most important constraint in the project. See §3.
- **The app's own port configuration, not the TNC, can be the actual
  fault — a terminal-program counter-test is part of diagnosis, not an
  afterthought (P54, 2026-09-26).** After `Ctrl+D`/`Ctrl+T`
  (disconnect/reconnect), the detection chain got nothing but echoes,
  never `cmd:` — looked identical to a dead TNC or a stuck Host Mode
  session. The operator's own counter-test settled it: quit the app,
  open PuTTY on the same COM port at the same baud with flow control
  set to **none**, press Enter once — `cmd:` appeared immediately, no
  `Ctrl-C` needed. **Same physical TNC, same stimulus, different
  result — the difference has to be in how the two programs open and
  configure the port, not the TNC itself.** Root cause found:
  `connect_port()` used to clear DTR/RTS (`rts = False`, `dtr = False`
  after construction); PuTTY leaves them asserted. Fixed to set both
  explicitly `True` instead, and to log every parameter that affects
  behaviour (`xonxoff`/`rtscts`/`dsrdtr`/`dtr`/`rts`/`timeout`/
  `write_timeout`) right after `open()` and again after this app's own
  post-open adjustments (`"Port config on open: ..."` /
  `"Port config after reset: ..."`) — the old log line
  (`"Port COM6 opened at 9600 baud"`) named nothing a hardware run
  could actually compare against a working counter-test with. **Rule:**
  when a TNC behaves differently under this app than under a plain
  terminal program on the same port/baud, the fault is in the app's own
  port setup until proven otherwise — run the counter-test before
  assuming a hardware or firmware problem.
- **The PK-232 uses SOFTWARE flow control (XON `$11` / XOFF `$13`) —
  a stopped TNC keeps echoing but sends nothing it generates itself,
  identical to Converse mode's symptom shape (P54.3, 2026-09-26).** The
  boot banner itself proves the scheme is in use: `... 0d 0a 11 41 45
  41 ...` — that `$11` right before the `"AEA"` banner text is a
  self-generated XON (TRM ch.12: `CMDTIME`/`TRFLOW`/`XFLOW`/`START`/
  `STOP` all govern it). A TNC halted by a stray XOFF (e.g. a Host Mode
  frame byte `$13` that leaked through) still echoes every character
  typed at it, but sends no prompt and no banner — exactly what
  Converse mode (P53) also looks like from a bare wakeup/CR probe, and
  exactly what the 26.09.2026 capture showed (steps 1/2/2b all echo,
  never `cmd:`). The detection chain's new step 2c (`$11`, wait, `CR`,
  then a second bare `CR` if that alone did not work) is defense in
  depth for this — two bytes, harmless if the TNC was never stopped —
  layered on top of, not instead of, the P54 port-configuration fix
  above (which the 26.09.2026 counter-test suggests may already be the
  primary repair for THIS specific incident). **Manual knowledge:**
  `TRANSPARENT` mode needs **three** COMMAND characters within
  `CMDTIME` to escape back to command mode; `CONVERSE` needs only one.
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
- **In Converse the TNC echoes Host Mode frames too — any check that
  waits for bytes it itself just sent is worthless there (P66,
  2026-09-28).** Not just plain text: a genuinely BINARY Host Mode
  frame (`HPOLL_Y`, an OPMODE query, anything) written while the TNC is
  in Converse comes back byte-for-byte identical, exactly like typed
  text does (P52.2 already established this for the P43 detection
  chain's own HPOLL query step; P66's root-cause finding, B.1/B.2, is
  the same mechanism hitting `pk232_hostmode_sub.py::enter_host_mode()`
  itself — the OLD version accepted `HPOLL_Y` in the response as
  success, which is EXACTLY what an echo reproduces). **Rule: a
  success check must look for something the TNC could only have sent
  ITSELF — a genuine answer carries information the query never had
  (a value byte after the mnemonic — see the corrected `HP Y`/`HP $00`
  entry above), never just "the expected bytes came back", since
  "came back" is exactly what an echo does too.** `escape_converse()`
  (`comm/pk232_hostmode_sub.py`) sends the TNC's own COMMAND character
  first, before anything else, specifically to get OUT of Converse
  before a check like this is even attempted — shared by
  `enter_host_mode()` (Teil A), the app's own detection-chain step 2b
  (`SerialManager._init_tnc_thread()`), and `tools/hw_check.py`'s
  `link_carry` (Teil C), so there is exactly one implementation of
  "send the COMMAND character and check for cmd:", not three.
- **P64/T141 root cause: the app's Host Mode entry never actually
  succeeded — the connection-table bug reported in P64 was a symptom,
  not the disease (P66, 2026-09-28).** The original observation
  (verbose, VHF Packet, connected to a BBS, `Enter Host Mode` (Ctrl+H)
  → app shows Baudot RTTY, connection "not recognised") looked like a
  UI/state-tracking bug and was provisionally planned as one (P64's own
  "internal connection table" proposal). The FIRST real hardware
  measurement of the actual mechanism (`tools/hw_check.py link_carry`,
  T141, Device B, 28.09.2026) found something upstream of all of that:
  after a verbose `CONNECT`, the TNC was in Converse, `HOST 3`/`HPOLL Y`
  never reached the command interpreter at all, and the OLD
  `enter_host_mode()` mistook Converse's own echo for success (see the
  two gotchas directly above) — so the app never entered Host Mode in
  the first place; everything downstream (mode activation, missing
  link messages, "connection not recognised") followed from that one
  false positive. **Lesson: when a bug looks like it's in the
  higher-level feature (a UI's connection display), measure the
  lower-level mechanism the feature depends on before designing the
  higher-level fix** — P64's own connection-table design was correct in
  spirit and remains the plan (now P67), but building it directly on
  top of a Host Mode entry that silently never happened would have
  fixed nothing.
- **With an active connection, the command interpreter can lag SECONDS
  behind the immediate character echo — `HOST 3` can take effect well
  after a handshake's own check already gave up (P66b, B.1, Device B,
  2026-09-28).** Real capture, T141 13:35: the delayed answer to an
  EARLIER `XFLOW OFF` command arrived only AFTER the `HPOLL_Y` echo
  that came after it had already been read — proof the interpreter was
  processing commands well behind real time, not instantly as every
  earlier measurement in this project assumed. `enter_host_mode()`'s
  own OPMODE check saw only an echo and reported failure, but `HOST 3`
  then ran anyway once the interpreter caught up, leaving the TNC in
  Host Mode while the app/tool still believed it was in verbose — the
  same class of state mismatch P66 fixed, just in the opposite
  direction. The SAME starting state reached Host Mode successfully in
  the app itself (T143, Ctrl+H) moments later — **this is timing-
  dependent, not a hard failure**, so a single measurement run cannot
  characterise it; treat as an open question needing several repeated
  runs, not a fixed constant. `enter_host_mode()`'s own OPMODE check
  now retries up to 3 times, 1.5s apart, specifically to give a lagging
  interpreter time to catch up before reporting failure (P66b, Teil B).

- **Live links at start-up (P81, 2026-10-04; T168 PASS on device B).** The app's init (detection
  chain + upload) does NOT drop connections the TNC already holds - not from verbose, Host Mode
  (chain 11.3 s, ends verbose ready) or Converse. Only `MYCALL` and `AX25L2V2` are refused
  (`?not while connected`), and only while a link exists. So: after the chain and before the
  upload, unless a banner was seen (`SerialManager.banner_seen_this_init`), the upload thread
  calls `SerialManager.query_live_links()` (verbose `CSTATUS`, `OPMODE`, `VHF`; direct reads).
  The result goes to the GUI thread by signal (`MainWindow._live_links_found`), never by touching
  widgets from the thread. `ParamsUploader.upload(defer=DEFER_WITH_LINKS)` holds back exactly
  those two; `LinkTable` fires the event `closed` when the last busy channel becomes free
  (`reset()` is silent), and `MainWindow._apply_deferred_params()` then sets them through
  `ParamApplier`. The found links are state, not an event: no connect bell (P76). The Packet
  mode is chosen from `VHF` only; an unreadable `VHF` names no band.
  **P81a:** a name is only deferred if the TNC value (verbose query at the init) really differs
  from the configuration; at the catch-up the value is read again (Host Mode `AV`, verbose) and
  the starting value of the result lines is that real value. The catch-up in Host Mode starts
  when a CO round (`MainWindow._begin_co_round()`) has all ten channels answered free - not on
  the DISCONNECTED message. `$09` / `?not while connected` keeps the name deferred, no dialog.
  `MYCALL` is never set in Host Mode (`ML` unmeasured): it waits for the next init.
  **P81c/P82a:** `ModeManager.on_frame()` DROPS every frame while no mode is active - a Host Mode
  query sent in the 300 ms between `set_mode()` and the activation is never answered to the app
  (the CO round of a restart waits for `mode_changed`). `ParamApplier` reads the TNC value before
  every set; `$09` / `?not while connected` sets `ApplyResult.busy` and the caller defers.
  **P81d:** for `$4x`/`$5x` frames this no longer matters: `ModeManager.link_frame_sink` hands them to
  the LinkTable whenever the active mode is not a Packet mode (`handles_link_frames`). Data, monitor,
  echo and status-error frames are still dropped while no mode is active.
  The detection chain announces each stage through `SerialManager.init_stage` ("step 2b: ...");
  `MainWindow` shows "Waking up the TNC..." (blinking, seconds, stage) when the chain takes
  more than 0.8 s, and removes it on `verbose_mode_ready`, `init_failed` or a lost connection.

### TNC / firmware v7.1

- **A measurement finding is valid for the device it was measured on —
  attribute by device, not just by date (P37, 2026-09-24;
  `docs/DEVICES.md` is the inventory).** Every finding below dated up to
  and including 22.09.2026 was measured on **Device A** (13.SEP.95,
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
- **In verbose command mode the PK-232 echoes everything, even binary
  frames — an echo is not an answer (P52.2, 2026-09-25).** Answer
  frames are longer and carry a value byte: real capture, 25.09.2026
  23:30:43, step 3's HPOLL query `01 4f 48 50 17` (5 B, no value byte)
  was answered with the identical 5 bytes right back — a verbose-mode
  TNC reflecting the query, not a genuine `$4F` frame — and the old
  detection chain mistook it for Host Mode confirmed, then sent a
  needless `HOST OFF` (also just echoed) before giving up. A real
  answer is 6 bytes with a value byte (same capture, 23:30:09: query
  `01 4f 48 50 4e 17`, answer `01 4f 48 50 00 17`). Check length AND
  content, not just that something came back that looks frame-shaped.
- **Don't read until the first pause, read until the expected pattern
  (P52.1, 2026-09-25).** At 9600 Bd the `cmd:` prompt and the boot
  banner arrive in pieces; a 200ms pause does not mean the response is
  complete. Proven by the same 25.09.2026 23:30:43 capture: step 1
  returned after 184ms with only `2a 5c 0d 0a` (4 of the expected 8
  bytes) — a working run at the same step saw `2a 5c 0d 0a 63 6d 64 3a`
  (`cmd:` included) — because the detection chain's own read function
  re-armed its deadline on every chunk of new data, which can only ever
  shrink the remaining budget, never extend it. Fixed by
  `_read_until_prompt()` (`serial_manager.py`), which always honours
  the caller's full timeout regardless of how the response is chunked,
  shared by the detection chain and `write_verbose_wait()`.
- **After `HOST OFF` the TNC is in whichever operating mode was active
  before Host Mode was entered — not the command prompt (P53.B,
  2026-09-25).** For Baudot, AMTOR and PACTOR that means Converse: the
  TNC echoes every character and shows **no** prompt at all. Confirmed
  by a real console capture, 26.09.2026, 13:13–13:16: after a disconnect
  with Baudot RTTY active, both `*` and a bare `CR` got only an echo
  back, never `cmd:` — indistinguishable from a genuinely unresponsive
  TNC by that evidence alone. `Ctrl-C` (`$03`, the COMMAND character —
  `SerialManager.command_char`, mirrors `AppConfig.misc.command`) is
  what actually escapes Converse; `tools/hw_check.py`'s own
  `Session.normalize()` has sent it before every command since P21 for
  exactly this reason. Two fixes: the detection chain gained step 2b
  (COMMAND char + CR, tried between the bare-CR step and the HPOLL
  query) so a fresh reconnect can tell Converse apart from a truly dead
  TNC; `SerialManager.exit_host_mode()` now also sends it immediately
  after leaving Host Mode itself, so the verbose terminal is usable
  right away instead of just echoing, and the next connect cycle never
  needs step 2b at all.
- **Echo without a prompt means Converse, not "the TNC is stuck"
  (P53.B, 2026-09-25) — corrects the earlier read of an identical
  symptom.** The P44/P45 "half-frame theory" (a process killed abruptly
  mid-frame leaving the TNC's parser stuck) was floated for exactly this
  shape of evidence — everything echoed, nothing at `cmd:` — and left as
  an unconfirmed suspicion. The 26.09.2026 capture shows a second,
  now-confirmed explanation for the identical symptom: Converse mode
  after `HOST OFF` returns to a non-Host-Mode operating mode. Neither
  explanation is wrong in general — they are different TNC states that
  happen to look the same from a plain wakeup/CR probe — but "echoes
  everything, no prompt" is no longer evidence of being stuck by itself;
  try the COMMAND character before assuming the worse case.
- **The transient `raw_data_received.connect()`/`disconnect()` pattern
  loses the delivery if nothing pumps the receiver thread's event loop
  in between — a real, 20/20-reproducible race, not a suspicion (P53.A,
  2026-09-25).** `query_verbose_value()` and `detect_maildrop()` used to
  wrap a single command in `raw_data_received.connect(_capture)` /
  `write_verbose_wait(...)` / `raw_data_received.disconnect(_capture)`.
  `raw_data_received` crosses from the ReaderThread's own OS thread into
  whichever thread constructed `SerialManager` (the GUI thread in
  production) as a Qt queued connection, which is only delivered once
  that thread's event loop actually processes it — but
  `write_verbose_wait()`'s own "found" result never needed that signal
  at all (it reads `_rx_buf`/`_rx_buf_event` directly, filled by a plain
  synchronous call from the reader, no Qt involved), so it can return —
  and the `finally` block's `disconnect()` can run — before the queued
  delivery has been processed. Qt drops a queued call outright if the
  connection is torn down before it is processed, which
  `test_serial_manager.py::TestVerboseQueryReadPath` reproduces
  deterministically (20/20) with a real, actively-pumping
  `QCoreApplication`. Confirmed 26.09.2026: the verbose terminal (a
  **persistent** `raw_data_received` connection, never torn down around
  one command) showed the TNC's correct answer to `MYCALL` while
  `ParamsUploader.verify()` reported "no answer" for the very same
  query. **Correction to this spec's own first framing** ("the
  verification reads directly from the port, the ReaderThread takes the
  bytes for the terminal") — code audit found no second, competing
  direct port read anywhere in the upload/verify path; the actual
  mechanism is the connect/disconnect race above. Fixed by having
  `query_verbose_value()`/`detect_maildrop()` read the response
  `write_verbose_wait()`'s own internal helper
  (`_write_verbose_wait_text()`) already assembled, directly — no
  signal-based capture in the loop at all, so there is nothing left to
  race. A **persistent** `raw_data_received` connection (MainWindow's
  own terminal display, `MailDropSession`'s connect-at-open/disconnect-
  at-close) is never exposed to this — only a connect-then-disconnect
  wrapped tightly around one command is.
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

  **Refuted Host Mode mnemonics (P80b, T166 device B / T167 device A) - facts, do not send:**
  `NE` = NEWMODE (answers `NEY`, OPMODE stays `PA`; NAVTEX is `NA`); `PT` = PACTIME (device A:
  `PTA 10`, OPMODE stays `PA` - NOT a PACTOR standby); `XL` and `EE` answer `$07` (unknown); `MW`
  answers `MWN` (a switch) and refuses 11 with `$01` (MWEIGHT is not `MW`); `CI` answers `CIN` (a
  switch; verbose CODE is 0); `MY` is `$07` on B and `MYnone` on A (MYIDENT mapping unproven); a bare
  `MH` answers only `MH$01`/`MH$03` (the app polls `MH0`..`MH17`); no Morse-ID (MID) mnemonic among
  `MA MB MC MJ MZ`. Confirmed instead: modes `BA AS MO AM FA SI TV NA` (+ `PN` on device A), switches
  `EA WI SR US WO FN SQ`, `AY` (set), `RB FS NM NS` (query only). All are in
  `comm/mnemonic_registry.py` (`sent=False` for the refuted ones).

  **New Host Mode mnemonics only with a registry entry (P80).**
`comm/mnemonic_registry.py` has one `MnemonicEntry` per mnemonic the application
sends (meaning, kind, `transmits`, evidence per release);
`tests/test_mnemonic_registry.py` scans the source (`ast`, via
`tools/gen_mnemonic_audit.py`) and FAILS for a mnemonic that is not registered.
Evidence of `host_params` rows is taken from `host_params.verified_sources()`,
never retyped; everything else names the Testplan entry, or stays `{}`
(= hypothesis only). After a change run `python tools/gen_mnemonic_audit.py
--update` - the test also fails for a stale `docs/MNEMONIC_AUDIT.md`.

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
    (B,E,K,L,R,S) > `` — the operator confirms the **13.SEP.95 EPROM**
    (Gen. 3 / PACTOR, see `docs/PK232_firmware_matrix.md` §2) was installed
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
  `_verbose_ready` is set by init **and** by `exit_host_mode()` (P68:
  after its COMMAND-char resync, both outcomes; `_verbose_confirmed`
  only if `cmd:` was seen), which then emits `verbose_resumed` —
  **not** `verbose_mode_ready` (that one triggers banner collection and
  the parameter upload). Still confirm `cmd:` with an ACTIVE Ctrl-C+CR
  probe (matching `tools/hw_check.py`'s own `normalize()`) rather than
  trusting the property alone. `message_store.py`'s schema did
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
- **An EVENT ("the TNC was just powered on") must be its own flag, never
  derived from a STATE that never resets (P59, 2026-09-26).**
  `SerialManager.fresh_boot_defaults` is true only if THIS init/recovery
  run's own boot banner said "is using default values" —
  `self._banner_this_init` is reset to `False` at the start of every
  `_init_tnc_thread()`/`_recovery_thread()` run (`_recovery_thread()`
  calls `_init_tnc_thread()` directly, so one reset covers both) and
  only set `True` inside `_finish_verbose_init()`'s existing banner-
  marker branch — no second banner detector. The existing
  `tnc_defaults`/`tnc_release`/`has_pactor` properties are all derived
  from `self._tnc_banner`, which is set exactly once per SESSION and
  **never reset** (by design — the firmware does not change just
  because a later reconnect's own read happened to be silent). A
  restore-after-power-on trigger checking `tnc_defaults` alone would
  therefore fire on EVERY later reconnect or Recovery too, not just the
  one that actually followed a power-on — `fresh_boot_defaults` is the
  only one of the four that is safe to gate an automatic action on.
- **An EVENT must be CONSUMED, not just separated from a sticky state —
  P59 did the latter but not the former, and it cost a real endless
  loop on real hardware (P60, 2026-09-27).**
  `docs/P60_Archive_Restore_Oneshot_Fix_Spec.md`. `fresh_boot_defaults`
  (previous bullet) correctly resets every init/recovery run — but
  `MainWindow._check_archive_restore_trigger()` kept reading the LIVE
  property on every call instead of clearing it once read, and
  `host_mode_changed(True)` fires from more places than an init run:
  `SerialManager._enter_host_mode_thread()` (never
  `_init_tnc_thread()`) also emits it, and every MailDrop session
  `leave()` (`maildrop/session.py`) plus "Enter Host Mode" (P49) go
  through exactly that path. Result with `archive_restore = "auto"`:
  finishing the restore ends the session → re-enters Host Mode →
  `host_mode_changed(True)` fires again → the still-armed event
  re-triggers another restore offer → another session → forever, one
  MailDrop session after another, packet operation never actually
  resuming. **Merkregel: a signal like `host_mode_changed(True)` means
  "Host Mode is active now", never "the TNC was just powered on" — it
  has more than one source, and only ONE of them is preceded by a fresh
  banner read.** Fixed with `SerialManager.consume_fresh_boot_defaults()`
  — reads `fresh_boot_defaults` and clears the underlying
  `_banner_this_init` flag in the same call, the only place that ever
  does either. `_check_archive_restore_trigger()` calls it FIRST, before
  any of `archive_enabled`/`archive_restore`/`archive_restore_scope` are
  even looked at — the event is used up exactly once per power cycle
  regardless of whether the current settings want a restore, so a later
  switch from `never` to `ask` mid-session cannot retroactively arm a
  restore for a power-on that has already passed. No test in P59 caught
  this — every existing test called the trigger once per scenario;
  catching it needed a test that fires `host_mode_changed(True)` (or,
  end to end, a fake dialog's `exec()`) a SECOND time within the same
  simulated power cycle. Same review also found `MailDropDialog.
  _on_failed()`'s restore branch used a dead `then == self.session.leave`
  identity comparison (neither call site ever passes literally that
  method, so it never actually fired) — replaced with an explicit
  `ends_session: bool` kwarg on `_start_sync()`/`_start_restore()`.
- **MailDrop archive sync/restore automation (P59, 2026-09-26).**
  `docs/P59_MailDrop_Archive_Auto_Spec.md` closes the P39.3/Backlog
  "not wired up yet" gap for `MailDropConfig.archive_sync`/
  `archive_restore`/`archive_restore_scope`:
  - `MailDropDialog._end_session()` is now the ONE path out of an
    ACTIVE session — `btn_end.clicked` and a confirmed window-close
    gesture (X/Esc/Close) both call it, never `session.leave()`
    directly (`grep -rn "session.leave()"` in the file finds exactly
    one call site, inside this method). When
    `archive_sync == "on_session_end"` and TNC-only messages exist, it
    reads them all into the archive FIRST (`_start_sync(queue,
    then=self.session.leave)`), then leaves — a sync failure mid-queue
    still calls `then()` (leaves anyway, packet operation must resume)
    where a MANUAL sync's failure (`then=self.session.list`) does not,
    distinguished by comparing the stored continuation to
    `self.session.leave` (bound-method equality), not a separate flag.
  - `_start_sync()`/`_start_restore()` (`then: Callable[[], None]`)
    replace the old hardcoded `self.session.list()` at the end of the
    sync/restore queues — the ONE queue-draining implementation per
    direction now serves three different endings: the manual buttons
    (`then=self.session.list`, unchanged behaviour), `_end_session()`
    (`then=self.session.leave`), and auto-restore (`then=self.
    _finish_auto_restore`, C.4 below) — never three different queue
    implementations.
  - `maildrop/archive.py::filter_restore_scope()` (`all`/`unread`/
    `none`, unknown scope raises `ValueError` rather than silently
    becoming `all`) is the ONE scope filter — `MailDropDialog.
    _restore_candidates()` maps a `_Row` to its `ArchivedMessage` via
    `archive_id` (the SAME `_header_key`-matched id `_refresh_rows()`
    already computed, never a second comparison) and calls it, used by
    both the manual "Restore to TNC" button and the automatic trigger.
  - `MailDropDialog(..., auto_restore=True)` opens the session itself
    (`self.session.open()`, called from `__init__` — `MailDropSession.
    open()` is itself async, safe to call before the dialog is even
    shown), overrides the banner for the WHOLE session ("Restoring the
    local archive after TNC power-on..."), and on the FIRST `listing`
    while ACTIVE starts a restore of every in-scope archive-only
    candidate (`_start_restore(candidates, then=self.
    _finish_auto_restore)`) — an EMPTY candidate list ends the session
    immediately for free, since `_start_restore([], then)` already
    calls `then()` right away with no special-cased "nothing to do"
    branch. `_finish_auto_restore()` sets `_closing_confirmed = True`
    then calls `_end_session()` itself — the file's only
    `session.leave()` call site stays the one inside `_end_session()`,
    satisfied here because this trigger only ever fires right after
    the TNC came up at factory defaults (D.1): its mailbox is empty at
    that point, so `_end_session()`'s own `on_session_end` check finds
    no genuinely TNC-only row (the messages just restored stay marked
    archive-only in this stale, never-relisted `_rows`) and just
    leaves — it is never trying to re-collect what it just wrote back,
    without needing a second code path to guarantee that. Stopping the
    dialog mid-restore (a close
    gesture while `_pending_op == "restore"`) asks "Stop restoring and
    end the session?", clears the QUEUE but never calls `session.
    abort()` on the message currently being sent (the `/EX` rule: a
    mailbox `S`/`SB`/`ST` exchange is one atomic worker call, not
    something that can be interrupted mid-write) — the continuation is
    simply changed to `self._end_session` so the session still ends,
    honestly, once that one in-flight `send()` reports back.
  - `MainWindow._check_archive_restore_trigger()` — wired to
    `host_mode_changed(True)` and `recovery_finished(True, ...)`, the
    two moments a fresh init/recovery run's own `fresh_boot_defaults`
    is guaranteed current — sets `_archive_restore_pending = True` and
    logs a `[SYS]` line, but opens NOTHING: `_update_maildrop_gate_ui()`
    (already called from every relevant transition — connect, Host
    Mode, mode switch, channel state) fires the actual offer,
    `_offer_archive_restore()`, via `QTimer.singleShot(0, ...)` the
    moment `_maildrop_gate()` first reads open — a modal
    `QMessageBox`/`QDialog` must never open from inside the SAME call
    stack as a gate-update triggered by some OTHER signal handler
    still running. Right after the TNC came up at defaults, the app is
    not necessarily in Packet mode yet — the pending flag can sit for
    an arbitrary time (with a one-time status/monitor hint) until the
    operator switches there. Disconnecting clears the pending flag —
    the next connection decides `fresh_boot_defaults` fresh, never
    inheriting a stale offer from a different session/TNC.
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
  13.SEP.95) — this is alignment with the manual, not a claim that
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
- **Host Mode parameter answers on device B (01.AUG.91), T151, 01.10.2026**
  (rule 11: device B only):
  - Query `$4F <mn>` -> answer `<mn><value>`; set `<mn><value>` -> `<mn> $00`
    (ACK); a second query shows the new value. Format: numbers as ASCII
    decimal digits, switches `Y`/`N`, text literal (`UNCQ`, `CFall`,
    `MTnone`), control characters as `$hh` (`CN$03`, `CL$18`, `SP$0D`),
    empty text as `
` (`BT
`) - that `$0D` is **not** an error code.
  - `$07` as the answer to a query: command unknown on this device (`EX`,
    `PH`, `PB`, `PV`; verbose `EXPERT`/`PTHUFF` -> `?What?`). `$10` on `DA`
    (DAYTIME unset): meaning unmeasured.
  - 50 mnemonics are tied to their parameter by the Pass 0 verbose value
    (numbers: strong evidence; switches: only weak, equal values can be
    chance). **`AO` = ARQTMO**; ARQTOL is `?What?` here, the matrix row
    `AO ARQTOL` is wrong. `KILONFWD  ON` (padded uppercase name) needs the
    verbose parser's double-space rule.
  - One of the Pass 1 test values switches the verbose command interpreter
    off (every verbose query -> `?What?`, only power-cycling helps) -
    trigger unknown until T155. Restore **in Host Mode** before leaving it.
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
- **`UBIT 0 ON` (factory default) silently drops packets below the DCD
  threshold (P74, found 01.10.2026, device B per operator - confirm in
  log/Testplan).** Packet reception in VHF Packet was unreliable; with
  `WHYNOT ON` the TNC reported "packet received below threshold" for the
  discarded packets. After `UBIT 0 OFF` (verbose, by hand) every packet
  with a correct CRC is processed regardless of DCD and reception has been
  reliable. Manual (STABO ch. 12, UBIT / CUSTOM bit 0): `ON` suppresses a
  packet too weak to light the DCD LED, `OFF` shows it anyway; UBIT applies
  to **all** modes; Host mnemonic **`UB`**. The manual describes only the
  receive side - whether `UBIT 0` leaves TX channel-busy detection alone is
  not stated (T156 notes what it can). The TNC has no backup battery, so it
  starts with ON every time: the app uploads `UBIT 0 ON|OFF` on every init
  (`HFPacketConfig.ubit0`, default OFF, checkbox "UBIT 0 (DCD gate)" in the
  Packet dialog). **Unmeasured until T156** (`hw_check.py ubit_probe`): the
  Host Mode argument form (`0 N`, `0N`, `0 OFF`, `0OFF`?), the query answer,
  whether the value survives mode switches (`PA`, `VH`, `HB`), and the
  behaviour on devices A and C (firmware matrix: `UB UBIT` confidence L,
  not in the BASE generation = device C). Until then
  `host_params.py` has `UBIT` with an empty mnemonic: nothing is sent in
  Host Mode (rule 6).
- **Host Mode parameters per device (P72, 02.10.2026; rule 11 - which pair is
  measured, which is not).** Format (T151, T152, T156): set `SOH $4F <mn><value>
  ETB` -> `<mn> $00`; query `<mn>` -> `<mn><value>`; numbers ASCII decimal,
  switches `Y`/`N`, text literal, control characters as `$hh`, empty text as
  `\r`; an error is ONE byte (`$07` command unknown here, `$10` DAYTIME unset).
  `comm/host_params.py` is the table: a parameter may be set in Host Mode by the
  app only if the TNC's release is in its `verified_releases`.
  - **Device B, `01.AUG.91`:** 37 parameters `verified` by T151 (`--exclude IL`,
    `hw_logs/20261001_205535_host_params_probe.log`, no banner - the device is
    the operator's statement; `--reevaluate` reproduces exactly the 37): PACLEN,
    TXDELAY, MAXFRAME, FRACK, RETRY, PERSIST, SLOTTIME, DWAIT, CHECK, MONITOR,
    RESPTIME, USERS, AX25L2V2, HEADERLN, CONSTAMP, DAYSTAMP, ACRPACK, ALFPACK, MRPT,
    PPERSIST, XMITOK, 8BITCONV, ARQTMO, ADELAY, TDBAUD, TDCHAN, RFEC, RXREV, TXREV,
    MSPEED, ALFRTTY, DIDDLE, MAILDROP, MMSG, TMAIL, 3RDPARTY, KILONFWD; plus UN and
    CF (T138 A.3/A.5). UBIT: not measured on B.
  - **Device A, `13.SEP.95`:** T151 (01.10.2026 22:07,
    `hw_logs/20261001_220703_host_params_probe.log`, banner; `--reevaluate`:
    verified=39) = the same 37 as on B plus PTHUFF and PT200 (UNPROTO/CFROM:
    B only). T152 (`..._172135_host_params_probe.log`) USERS,
    MAXFRAME, PACLEN, FRACK, RETRY, MONITOR, TXDELAY - set, ACK, read back,
    WHILE CONNECTED, link unchanged. T156 (`20261002_162823_ubit_probe.log`, no
    banner, device A per the operator): UBIT 0 set `UB0 N`/`UB0 Y` (WITH a
    space), query `UB0` -> `UBN`/`UBY`, verbose confirmed, survives the VHF
    mode-switch frames. Everything else on A (MYCALL..., text and character
    parameters, `verified_query` rows): **not released.**
  - **Device C:** nothing measured.
  - **Log attribution:** `20261001_220703_host_params_probe.log` (22:07-22:11) has
    the banner `release=13.SEP.95` = device A, not B; it is NOT used for B.
  - **While connected (B.4):** none of the seven T152 parameters was refused with
    "not while connected" (device A). Unmeasured for the rest - therefore P72
    ALWAYS reads back and quotes a rejection word for word.
  - **ILFPACK OFF breaks the app's verbose commands (T155, P72 B.3):** the app
    ends commands with CR LF; with `ILFPACK OFF` the LF counts as the first
    character of the next command and every further verbose command gives
    `?What?`. Setting it in Host Mode works, so ParamApplier never sets it live
    (message "applied at the next initialisation", P75 fixes the line endings).
  - **EXPERT OFF does not hinder setting the released parameters in Host Mode on
    13.SEP.95 (T158, 02.10.2026, `hw_logs/20261002_192301_host_params_probe.log`):**
    with `EXPERT OFF` all 39 are accepted, only DAYTIME answers `$10` - as with
    EXPERT ON. ParamApplier needs no EXPERT handling in Host Mode (the verbose
    path keeps its EXPERT ON/OFF wrap on PACTOR firmware).

- **Release without a banner: the EXPERT fingerprint (P78 A, 03.10.2026).** The
  banner is the only direct source of `tnc_release`; a TNC that was already awake
  at connect time has none, and P72 then sets NOTHING in Host Mode ("not verified
  for Host Mode on unknown", T162, device B). The PK-232 has no local VERSION
  command and `RESTART` would drop links, so the release is INFERRED from one
  measured generation difference: **EXPERT is unknown on 01.AUG.91** (verbose
  `?What?`, Host `EX` -> error `$07`, T151/T155) **and known on 13.SEP.95** (a value;
  Host `EXY`/`EXN`, T151/T152/T158); device C is unmeasured. `comm/devices.py`
  (`KNOWN_DEVICES`, `infer_release()`) is the one place; the verbose probe is
  `SerialManager.probe_release_verbose()` (one query per connection, run by
  `ParamsUploader.upload()` next to `detect_maildrop()`), the Host Mode probe is
  `SerialParamTransport.release()` (one `EX` query when a Host set is attempted
  with no release). The banner always wins; `tnc_release_source` is `banner` or
  `inferred`; the toolbar says "(inferred)". **Valid only while DEVICES.md has one
  unit per generation** - a second unit makes it ambiguous and `infer_release()`
  answers `None`.
- **Verbose changes reach the configuration through ONE parser (P78 B).** The
  configuration is the source of the init upload and of the mode-switch frames
  (`MN<monitor>`, P73). A parameter changed in the verbose terminal used to be
  overwritten by the old configuration value at the next mode switch / Host Mode
  entry (T162 finding 3). The TNC confirms every taken change as
  `Name   was a` / `Name   now b` (capitals = shortest abbreviation: `MOnitor`,
  `UBit   0`, `DAYStamp`); `comm/verbose_parse.py` (`parse_was_now`, chunk-safe
  `VerboseSync`, `HF_PACKET_FIELDS`) parses it and `MainWindow._take_verbose_change()`
  writes `HFPacketConfig` - only when the value DIFFERS (the app's own upload and
  ParamApplier cause the same lines), text compared the way the TNC reformats it,
  band values (MAXFRAME/SLOTTIME) by the active band, parameters without a field
  only reported. **Rule: a verbose change lands in the configuration via the was/now
  parser, nowhere else.**
- **MONITOR has ONE write path (P78 C).** Parameter mask, Monitor selector of the
  Packet screens and the verbose parser all write `HFPacketConfig.monitor`; the TNC
  is set through ParamApplier (set + read-back). Before P78 the selector sent `MN<n>`
  directly (Host Mode only, no read-back, configuration untouched, and the selector
  was never filled from the configuration).
