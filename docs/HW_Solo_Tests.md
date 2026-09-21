# PK232PY — Solo Hardware Test Guide (hw_check.py)

Printable operator guide for running the four `tools/hw_check.py` checks
against a real PK-232MBX. See `docs/P14_HW_Solo_Check_Spec.md` for the full
technical spec and `CLAUDE.md` / `Backlog.md` for background on each finding.

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

## 2. Order

1. Run `all` first — it covers T17, T103 and PTHUFF in one go and needs no
   second receiver.
2. Run `t101` separately, afterwards, once the second receiver is ready.

```
python tools/hw_check.py --port COM3 all
python tools/hw_check.py --port COM3 t101
```

Add `--dry-run` to either command first if you just want to see what each
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

## 4. Checklist

| Test | Date | Result | Notes |
|------|------|--------|-------|
| T17 |  |  |  |
| T103 |  |  |  |
| PTHUFF |  |  |  |
| T101 |  |  |  |

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
