# PK232PY — Solo Hardware Test Guide (hw_check.py)

Printable operator guide for running the `tools/hw_check.py` checks against
a real PK-232MBX. See `docs/P14_HW_Solo_Check_Spec.md` for the original four
checks, `docs/P17_HW_Measure_Spec.md` for `siam`/`t111`/`t112`,
`docs/P20_MailDrop_Measure_Spec.md` for `mi`/`maildrop`,
`docs/P24_MailDrop_HostMode_Spec.md` for `maildrop_host`,
`docs/P26_MDCHECK_Mnemonic_Spec.md` for `mdcheck_scan`, and
`docs/P28_MailDrop_Session_Harness_Spec.md` for `maildrop_session`;
`CLAUDE.md` / `Backlog.md` have background on each finding.

---

## 1. Preparation

- **Quit pk232py first.** The COM port is exclusive — if the application is
  connected, `hw_check.py` will fail to open the port with a plain
  `Port busy — is pk232py running?` message.
- Note which COM port and baud rate the TNC uses (same as in the
  application's TNC Configuration — `hw_check.py` reads them from
  `pk232py.ini` by default; override with `--port` / `--baud` if needed).
- Make sure the TNC is powered on and **not already in Host Mode** — power-
  cycle it if unsure. `hw_check.py` starts from verbose mode and stops with
  a clear error if the TNC answers the wakeup already in Host Mode.
- **Only for T101** (it transmits):
  - Connect the transmitter to a dummy load, or set power very low if
    transmitting into an antenna.
  - Set up a **second receiver** with an AX.25 decoder (an SDR running
    Direwolf, multimon-ng, or similar) tuned to the TNC's frequency, and
    have its decoder running *before* you start the test — you will be
    asked what it shows in real time.
- **Only for `siam`:** tune a second receiver to a **known** FSK signal
  before you start (Amateur RTTY 45 Bd / 170 Hz shift is the simplest
  case) and know its operating mode, baud rate and shift — the tool asks
  for these up front so the captured frames can be compared against a
  known-good answer.
- **Only for `maildrop`:** this is fully interactive and open-ended — set
  aside real time (not a quick check), have a notepad ready for what the
  mailbox's own `H` (help) shows, and expect to type at its `md>` prompt
  yourself. No second receiver needed (it never transmits — the session
  runs over the serial link, not radio).
- **Only for `maildrop_host`:** run `maildrop` first at least once (this
  test relies on the same known-safe verbose commands to create one test
  message). It is read-only in Host Mode — it never sends `S`/`K`/`E` and
  never transmits — but it does send unknown, previously-unmeasured Host
  Mode frames, so you get exactly one `y/N` confirmation before that
  happens. No second receiver needed.
- **Only for `mdcheck_scan`:** same preparation as `maildrop_host` (it
  creates its own test message the same way). It only sends Host Mode
  *queries* (no argument) — nothing writes, kills, or transmits — but up
  to 23 of them, so you get one `y/N` confirmation naming the count and
  the three mnemonics it will never send. No second receiver needed.
- **Only for `maildrop_session`:** this drives the real
  `pk232py.maildrop.MailDropSession` end to end — it opens the mailbox,
  sends three real test messages, reads one, kills one, then leaves.
  **No confirmation prompt** (unlike `maildrop_host`/`mdcheck_scan`,
  every command it sends is the SAME public API the running application
  would eventually use, not an unmeasured probe) — but it does leave two
  real messages in your mailbox afterwards (the foreign-FROM and
  bulletin test messages; the personal one is killed as part of the
  sequence itself), so expect that on your next `L`. No second receiver
  needed. `--abort-test` additionally opens the mailbox a second time,
  starts a message, and aborts it mid-flight — confirming the recovery
  path actually works on real hardware, not just against a fake channel.

## 2. Order

1. Run `all` first — it covers T17, T103 and PTHUFF in one go and needs no
   second receiver.
2. Run `t101` separately, afterwards, once the second receiver is ready.
3. Run `t111`, `t112` and `mi` on their own whenever convenient — all
   three only query/set parameters, no second receiver needed.
4. Run `siam` on its own once a known FSK signal is tuned in — it is
   deliberately not part of `all` (see `docs/P17_HW_Measure_Spec.md`).
5. Run `maildrop` last, on its own, once you have time for the
   interactive session (see `docs/P20_MailDrop_Measure_Spec.md`).
6. Run `maildrop_host` afterwards, on its own (see
   `docs/P24_MailDrop_HostMode_Spec.md`).
7. Run `mdcheck_scan` afterwards, on its own, once `maildrop_host` has
   already run at least once (see `docs/P26_MDCHECK_Mnemonic_Spec.md`).
8. Run `maildrop_session` last, on its own (see
   `docs/P28_MailDrop_Session_Harness_Spec.md`) — it needs no prior
   `maildrop`/`maildrop_host` run, but leaves real messages behind, so
   run it after you are done exploring with those.

```
python tools/hw_check.py --port COM3 all
python tools/hw_check.py --port COM3 t101
python tools/hw_check.py --port COM6 t111
python tools/hw_check.py --port COM6 t112
python tools/hw_check.py --port COM6 siam
python tools/hw_check.py --port COM6 mi
python tools/hw_check.py --port COM6 maildrop
python tools/hw_check.py --port COM6 maildrop_host
python tools/hw_check.py --port COM6 mdcheck_scan
python tools/hw_check.py --port COM6 maildrop_session
python tools/hw_check.py --port COM6 maildrop_session --abort-test
```

Add `--dry-run` to any command first if you just want to see what each
test *would* do without touching the TNC at all — it never opens the port.

## 3. Per-test walkthrough

### `t17` — is PASSALL `PS` or `PX`?
- **What happens:** two verbose queries (`PX`, `PS`), nothing is changed.
- **No confirmation prompts** — this test never transmits or writes.
- **PASS** if the tool reports "PASSALL is PS — the app's toggle is
  correct". **FAIL** if it reports "PASSALL is PX, not PS" (the
  application's PASSALL button would need fixing). **INCONCLUSIVE** if
  neither response looks like a plain Y/N toggle — check the printed raw
  responses and note them for `Testplan.md`.

### `t103` — does `USERS` reach the TNC?
- **What happens:** queries `USERS`, then sends the application's **entire**
  real parameter upload with only `USERS` changed to `4`, queries `USERS`
  again, then restores `USERS` to your actual configured value. No
  confirmation prompt (nothing is transmitted; the TNC ends up with your
  own saved configuration either way, exactly as it would after a normal
  program start).
- **PASS** if `USERS` reads back `4` after the upload. Also watch for any
  `FAIL: upload command error` lines — each one is a command from the P13
  sprint (`RESPTIME`, `ACRPACK`, `8BITCONV`, `HID`, `CFROM`/`DFROM`/`MFROM`/
  `MTO`, or any other) that the TNC rejected with a `?` error.

### `pthuff` — what does the TNC do with `PTHUFF ON`/`OFF`?
- **What happens:** queries `PTHUFF`, sends exactly what the real uploader
  sends (`PTHUFF ON` or `PTHUFF OFF`), queries again, restores the original
  value as best it can (the TNC's own format is not known until this test
  runs — check the log if the restore looks wrong).
- Skipped with `INFO: no PACTOR option` if the TNC has no PACTOR hardware.
- **FAIL** ("type mismatch confirmed") if the TNC reports a *numeric* value
  before the test — meaning the application sends the wrong kind of command
  for this parameter. **PASS** if the TNC's own format is already ON/OFF.

### `t101` — UI frame on the unconnected channel 0
- **What happens:** two consultation prompts before you even connect
  (confirm the second receiver is running), then for each of two rounds
  (`TEST1`, `TEST2`): sets `UNPROTO`, enters Host Mode, asks
  `Proceed? [y/N]` naming the exact text about to be transmitted, sends it,
  waits 2 seconds, then asks what the second receiver's decoder showed.
  `UNPROTO`/`MONITOR` are restored at the end regardless of how far the test
  got.
- Answer **`n`** to the transmit confirmation at any point to abort that
  round without transmitting.
- **PASS** if the decoder showed `TEST1` in round A and `TEST2` in round B.
  **FAIL** if it showed the same destination both times. **INCONCLUSIVE** if
  the decoder saw nothing either time (check its setup and frequency, then
  repeat).

### `siam` — unfiltered Signal Analysis (SIAM) capture
- **What happens:** asks for the known mode/baud/shift of the signal your
  second receiver is already tuned to, then a `Ready to continue? [y/N]`
  confirmation, then enters Host Mode, sends `SignalMode`'s real activation
  frames, and logs **every** incoming frame for 60 seconds (change with
  `--seconds`) with no filtering at all — printing a running "n frames so
  far" line every 10 seconds. Nothing is transmitted; this is receive-only.
- Ctrl-C at any point still leaves Host Mode cleanly before exiting.
- **No PASS/FAIL** — this is a measurement, not a verdict (the code that
  would need fixing has two different, contradictory ideas of what a SIAM
  result even looks like; see `docs/P17_HW_Measure_Spec.md` and the
  Backlog.md SIAM entry). Read the printed summary: the frame-count-by-kind
  table, then every frame flagged as "looks like an analysis result".
  Compare those against the mode/baud/shift you entered at the start and
  write the comparison into `Testplan.md` yourself — including which
  `FrameKind` ($4F CMD_RESP or $50 LINK_MSG) it actually arrived as.

### `t111` — does the PASSALL button's mnemonic (`PX`) actually toggle PASSALL?
- **What happens:** queries `PX`/`PS` in Host Mode, sends `PX Y` (the exact
  mnemonic `main_window.py`'s PASSALL toggle uses — a unit test keeps the
  two in sync), queries both again, then restores `PX` to its original
  value.
- **PASS** if `PX` changed and `PS` did not. **FAIL** if `PS` changed too
  (the mnemonic is masking PASS, not toggling PASSALL) or if `PX` did not
  change at all. **INCONCLUSIVE** if either query came back with no
  matching response.

### `t112` — does HF Packet keep VHF's MAXFRAME/SLOTTIME after a VHF→HF switch?
- **What happens:** queries `MAXFRAME`/`SLOTTIME`/`VHF`/`HBAUD`, enters Host
  Mode, sends the exact frame sequence the app sends for a VHF→HF Packet
  switch (built from the real `VHFPacketMode`/`HFPacketMode` classes, same
  order as `_on_mode_selected()`), exits Host Mode, queries `MAXFRAME`/
  `SLOTTIME` again, then restores all four original values.
- **PASS** if `MAXFRAME`/`SLOTTIME` read back HF Packet's own configured
  values afterwards (close the matching Backlog.md item). **FAIL** if they
  read back VHF's hardcoded `4`/`10` (the suspected gap is confirmed).
  **INCONCLUSIVE** for anything else, or if an original value could not be
  parsed (test is then `SKIPPED` and nothing is touched).

### `mi` — is the MailDrop button's `MI` actually `MFILTER`?
- **What happens:** enters Host Mode, queries `MI` with no argument (the
  exact frame `main_window.py`'s MailDrop button sends — a unit test keeps
  the two in sync), exits Host Mode, then verbose-queries `MFILTER`. No
  writes at all.
- **FAIL** if `MI` reads back the same value as `MFILTER` — confirms the
  mnemonic-table's name-list entry and means the app's MailDrop button
  sends the wrong command (it should log in to the mailbox, not query a
  filter). **PASS** if the two values differ (no evidence for the
  MI=MFILTER claim). **INCONCLUSIVE** if either query fails.

### `maildrop` — guided local MailDrop recording terminal
- **What happens:** first queries and logs `MAILDROP`, `MYMAIL`, `MYCALL`,
  `MTEXT`, `MMSG`, `3RDPARTY`, `KILONFWD`, `TMAIL`, `MDMON`, `XMITOK`
  (a `?What?` for any of these is itself a finding, not a failure) and
  warns if `XMITOK` is `ON`. Sends `MDCHECK` to open the mailbox and shows
  the raw response. Then prints a **suggested** (not mandatory) command
  sequence and hands you an `md>` prompt: whatever you type is sent with a
  trailing CR and the response is read until the mailbox goes quiet for
  1.5 seconds (the mailbox's prompt is not `cmd:`, so the tool cannot wait
  for that). Type `^Z`, `^D` or `^C` to send that exact control byte
  instead of the three literal characters.
- **Ending the session:** type `/quit` (a tool-local command, never sent
  to the TNC) to leave the interactive prompt. The tool then reads for one
  more second and reports whether a `cmd:` prompt appeared — if not, **the
  mailbox is probably still open** (no command to leave it is known) and
  you must exit it yourself in a normal terminal before doing anything
  else on this port. The summary names the last input that was sent, to
  help you pick up where you left off.
- **Optional last step:** you'll be asked whether to power-cycle the TNC
  to confirm the mailbox is lost (expected — see CLAUDE.md's "no RAM
  buffer battery" finding). Say `y`, power-cycle when prompted, and the
  tool reconnects, queries `MYCALL` (should read back the factory
  `PK232`) and reopens the mailbox for a single `L` (list) to show it is
  empty again.
- **No PASS/FAIL** — this is a measurement of an unknown protocol, not a
  verdict. Write up what the mailbox's own `H` (help) showed, the message
  format from `L`, and whatever else you found into `Testplan.md`
  yourself.

### `maildrop_host` — is there a MailDrop data channel in Host Mode?
- **What happens:** queries and warns on `XMITOK`, then creates one test
  message via the same known-safe verbose path `maildrop` uses (`MDCHECK`,
  `S OE3GAS`, subject `Host Mode Test`, one text line, `/EX`, `L` to note
  its number, `B` to leave the mailbox), then verbose-queries `HOST` and
  logs it. It enters Host Mode via the app's own connection path and drains
  any pending frames, then asks **one** `y/N` confirmation naming exactly
  what is about to be sent (unknown, read-only mailbox commands: no
  transmission, no `S`/`K`/`E`). **Probe A** sends a bare `L` (list) as a
  `$60`-CTL Host Mode frame and logs everything that arrives for 3 seconds.
  **Probe B** (only if Probe A got nothing at all) sends `MDCHECK` first,
  then `L` again, same logging. If a message list came back, it sends
  `R <n>` for the number noted earlier, then always sends `B`, then leaves
  Host Mode. **Probe C**, only if A and B both got nothing, re-queries
  verbose `HOST` afterwards (no guessed mnemonic — just the same `HOST`
  query as before, to see if leaving Host Mode changed anything observable).
  `finally` always leaves Host Mode and verbose-checks for a `cmd:` prompt.
  **Fixed P26.1 (2026-09-23):** "got a response" means a genuine mailbox
  data frame (anything that is not `$4F`/`$5F`), not just any frame at
  all — the first hardware run's Probe A got back only the generic `$5F`
  data-acknowledgement byte pair and the tool wrongly called that "login
  not needed", skipping Probe B. A bare `$5F` ack no longer counts.
- **No PASS/FAIL** — like `siam`/`maildrop`, this is a measurement of an
  unmeasured protocol area, not a verdict. The printed summary answers four
  questions — copy all four into `Testplan.md`:
  1. Which frame type carried the response — `$70`, some other `$7x`, or
     something else entirely (or nothing at all)?
  2. Is the mailbox prompt/banner identical to the verbose-mode version, or
     different?
  3. Was a login needed — did Probe A's bare `L` already work, or was
     `MDCHECK` (Probe B) required first?
  4. Does the list/read output match the verbose-mode path byte-for-byte,
     or does the framing/format differ?
- Add `--dry-run` first to see all five planned frames (`L`, `MDCHECK`,
  `L`, `R <n>`, `B`) in hex without touching the TNC.

### `mdcheck_scan` — which Host Mode mnemonic is MDCHECK?
- **Why:** the TRM's own Host Mode mnemonic table is self-contradictory —
  it lists `MI` for both `MDCheck` and `MFIlter`, and `mi`/T115 already
  confirmed by measurement that `MI` is really MFILTER. So the real
  MDCHECK mnemonic (if it has one at all) is unknown, and this searches
  for it instead of guessing.
- **What happens:** creates one test message via the same known-safe
  verbose path `maildrop_host` uses, verbose-queries and warns on
  `XMITOK`, enters Host Mode and drains pending frames, then asks **one**
  `y/N` confirmation naming the up-to-23 candidates and the three
  denylisted mnemonics (`MO` MORSE, `MI` MFILTER — already identified,
  `MM` MEMORY — has a read side effect). Then queries each remaining `M?`
  mnemonic (A–Z) with no argument, one at a time, stopping at the very
  first response that contains the mailbox prompt's own text
  (`(AEA PK-232M` and `free`) — in whichever frame type it arrives as. On
  a hit, confirms with a `$60`-CTL `L` (list) and leaves the mailbox with
  `B`. `finally` always leaves Host Mode; afterwards verbose-checks for a
  `cmd:` prompt and normalizes again.
- **No PASS/FAIL** — this is a search, not a verdict. If a candidate hits,
  record the mnemonic and the exact frame captured in `Testplan.md`, then
  add it to CLAUDE.md's hardware-confirmed mnemonic table. **A "no hit"
  result is itself a complete, useful answer** — it means MDCHECK is not
  reachable as a two-letter Host Mode mnemonic at all, and any future
  MailDrop dialog must drive the mailbox over the verbose path instead;
  record that as a `Backlog.md` decision point, not as a failed test.
- Add `--dry-run` first to see all 23 candidate frames in hex and the
  three denylisted mnemonics, without touching the TNC.

### `maildrop_session` — MailDropSession end to end (T119)
- **Why:** `MailDropSession`/`protocol.py` (P27) are fully unit-tested
  against played-back hardware transcripts, but never against the real
  TNC. This harness is the hardware confirmation for T119 — it contains
  no protocol logic of its own (no parsing, no mailbox command it built
  itself); it only calls `open()`/`list()`/`send()`/`read()`/`kill()`/
  `leave()` and reacts to the signals they fire.
- **What happens:** enters Host Mode over the existing, already-proven
  `SerialManager` path (parameter upload skipped by default — see
  `--skip-upload`), then runs ten steps against the real session, each
  logged with a PASS/FAIL line:
  1. `open()` → `ACTIVE`, mailbox prompt with the free-byte count
  2. `list()` → whatever is already in the mailbox (empty is fine)
  3. `send()` a personal message to your own callsign, subject
     `T119 personal` → `stored` with a message number
  4. `send()` with a foreign FROM (`< DL1ABC`) → `stored`
  5. `send()` a bulletin to `ALL` → `stored`, type `B`
  6. `list()` → all three messages present, with the right type/sender
     each (checked against the message NUMBERS remembered from steps
     3–5, not by re-parsing anything — see the Definition of Done)
  7. `read()` the personal message → text matches what was sent
  8. `kill()` the personal message → `killed`, free-byte count rises
  9. `list()` → the killed message gone, the other two still there
  10. `leave()` → `CLOSED`, then an `HPOLL` query confirms Host Mode is
      really active again
- **No confirmation prompt** — every command sent is the same public API
  the running application will eventually use, not an unmeasured probe.
  **Leaves the foreign-FROM and bulletin test messages in your mailbox**
  (only the personal one is killed as part of the sequence) — expect
  those on your next `L`.
- **PASS/FAIL per step**, plus an overall `N/10 steps passed` line. A
  step that fails (or times out after 20s waiting for its signal) stops
  the whole run there — later steps are not attempted with a session
  that already misbehaved. If the mailbox was still open when the run
  stopped, the harness calls `leave()` itself as cleanup before
  finishing, so the TNC should always end back in Host Mode either way;
  the final `HPOLL` query is what actually confirms that.
- **`--abort-test`** adds three more steps: reopen the mailbox, start a
  `send()`, call `abort()` right after the subject is accepted (before
  any body line goes out), and leave again. Expect the abort step to
  PASS by way of a `failed` signal (that IS success for this probe — it
  proves the recovery path runs and reports failure, never a false
  success) and the TNC to end back in Host Mode, same as the main run.
- Add `--dry-run` first to see the full step list (13 with
  `--abort-test`) without touching the TNC at all.

## 4. Checklist

| Test | Date | Result | Notes |
|------|------|--------|-------|
| T17 |  |  |  |
| T103 |  |  |  |
| PTHUFF |  |  |  |
| T101 |  |  |  |
| SIAM |  |  |  |
| T111 |  |  |  |
| T112 |  |  |  |
| MI |  |  |  |
| MAILDROP |  |  |  |
| MAILDROP_HOST |  |  |  |
| MDCHECK_SCAN |  |  |  |
| MAILDROP_SESSION (T119) |  |  |  |
| MAILDROP_SESSION --abort-test |  |  |  |

## 5. Where results go

- The console prints a `=== SUMMARY ===` block at the end of every run —
  copy it directly into the matching test case in `Testplan.md`.
- The full byte-level protocol (every command sent, every raw response) is
  saved to `hw_logs/YYYYMMDD_HHMMSS_<test>.log`. These files are
  git-ignored and stay on this machine — keep them for your own reference,
  but only the summary needs to go into the tracked docs.
- If a finding changes application behaviour (e.g. T17 confirms `PX` is the
  real PASSALL mnemonic), record it as its own `Backlog.md` item — `hw_check.py`
  only measures, it never changes `src/pk232py/`.
