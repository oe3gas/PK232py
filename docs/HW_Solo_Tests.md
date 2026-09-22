# PK232PY — Solo Hardware Test Guide (hw_check.py)

Printable operator guide for running the `tools/hw_check.py` checks against
a real PK-232MBX. See `docs/P14_HW_Solo_Check_Spec.md` for the original four
checks and `docs/P17_HW_Measure_Spec.md` for `siam`/`t111`/`t112`; `CLAUDE.md`
/ `Backlog.md` have background on each finding.

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

## 2. Order

1. Run `all` first — it covers T17, T103 and PTHUFF in one go and needs no
   second receiver.
2. Run `t101` separately, afterwards, once the second receiver is ready.
3. Run `t111` and `t112` on their own whenever convenient — both only
   query/set parameters, no second receiver needed.
4. Run `siam` on its own once a known FSK signal is tuned in — it is
   deliberately not part of `all` (see `docs/P17_HW_Measure_Spec.md`).

```
python tools/hw_check.py --port COM3 all
python tools/hw_check.py --port COM3 t101
python tools/hw_check.py --port COM6 t111
python tools/hw_check.py --port COM6 t112
python tools/hw_check.py --port COM6 siam
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
