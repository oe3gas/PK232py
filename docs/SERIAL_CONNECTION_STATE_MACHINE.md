# PK232PY — Serial Connection State Machine Reference

** Explanation of document sections in german **
Abschnitt 1–2 — 8 Zustände (C0–C7) mit vollständiger Übergangstabelle. Besonders wichtig: C5 "SWITCHING" ist ein eigener Zustand, der im Code implizit existiert aber nirgendwo explizit dokumentiert war.
Abschnitt 3 — Die drei Thread-Typen und die kritische Regel: nur ein Thread darf den Port gleichzeitig besitzen. Das war die Ursache vergangener Bugs.
Abschnitt 4–5 — Die exakten Byte-Sequenzen für Entry und Exit, inklusive des kritischen Hinweises: HOST OFF als Text funktioniert in Binary Host Mode nicht — nur der binäre Frame $01 $4F $48 $4F $4E $17.
Abschnitt 6 — Alle Qt Signals mit ihrer Wirkung auf MainWindow — das ist die Schnittstelle zwischen SerialManager und der UI.
Abschnitt 7 — UI-Zustandstabelle: welche Controls sind in welchem Zustand enabled/disabled. Das verhindert Fehler bei neuen Menüeinträgen oder Buttons.
Abschnitt 10–11 — _connect_mode Erklärung und alle Timing-Konstanten an einem Ort.
Abschnitt 14 — P40 (2026-09-25): Parameter-Upload verweigert sich im Host Mode statt 68x 5s stumm zu verstreichen, plus Stichprobenverifikation nach dem Upload.


**Scope:** `SerialManager` + `MainWindow` connection lifecycle.
Covers all states from port closed to Host Mode active.

**Key files:**
- `src/pk232py/comm/serial_manager.py` — state owner
- `src/pk232py/comm/pk232_hostmode_sub.py` — subprocess for Host Mode entry
- `src/pk232py/ui/main_window.py` — UI reactions via Qt Signals

**Last updated:** 2026-09-25 (P40 — upload-before-Host-Mode guard, see §14)

---

## 1. States

| State ID | Name | `is_connected` | `is_host_mode` | `is_verbose_mode` |
|---|---|:---:|:---:|:---:|
| `C0` | **OFFLINE** | False | False | False |
| `C1` | **PORT OPEN** | True | False | False |
| `C2` | **INITIALISING** | True | False | False |
| `C3` | **VERBOSE** | True | False | True |
| `C4` | **UPLOADING PARAMS** | True | False | True |
| `C5` | **SWITCHING TO HOST** | True | False | False |
| `C6` | **HOST MODE** | True | True | False |
| `C7` | **ERROR** | True/False | False | False |

> **Note on C5:** During Host Mode entry, `_in_host_mode` is not yet
> True, but `_verbose_ready` is also cleared. The indicator shows
> "SWITCHING" (orange). No opmode screens are usable in this state.

---

## 2. State Transition Table

| From | Event / Trigger | Action | Next |
|---|---|---|---|
| `C0` | User: Connect + Verbose | `connect_port()` opens serial port | `C1` |
| `C0` | User: Connect + Host Mode | `connect_port()` opens serial port | `C1` |
| `C1` | Port open OK | `init_tnc()` → background thread starts | `C2` |
| `C1` | Port open failed | Error message; port remains closed | `C0` |
| `C2` | Wakeup `*` → TNC responds `cmd:` | `_verbose_ready = True`; emit `verbose_mode_ready` | `C3` |
| `C2` | Wakeup → SOH byte detected | TNC already in Host Mode; start Worker | `C6` |
| `C2` | Timeout / no response | Emit error; start ReaderThread as fallback | `C7` |
| `C3` | `verbose_mode_ready` emitted | `ParamsUploader.upload()` starts in thread | `C4` |
| `C4` | Upload complete | `ParamsUploader.verify()` spot-checks MYCALL/PACLEN/MAXFRAME against `AppConfig`, still in `C4` (P40, informational only — never blocks the transition below) | `C4` |
| `C4` | Verify complete, `_connect_mode == "verbose"` | Stay in verbose terminal | `C3` |
| `C4` | Verify complete, `_connect_mode == "host"` | `enter_host_mode()` → background thread | `C5` |
| `C4` | TNC rebooted during upload | Emit `params_upload_required`; re-upload | `C4` |
| Any | `ParamsUploader.upload()` called while `is_host_mode` is true | **Refused (P40.2):** logs `ERROR`, sends nothing, returns `0` — this must never legitimately happen (upload only ever runs in `C4`, i.e. verbose mode), so hitting it means a caller violated the state machine | (unchanged) |
| `C5` | Subprocess returns `"OK"` | Reopen port; start `HostModeWorker`; send HPOLL N | `C6` |
| `C5` | Subprocess returns `"FAIL:..."` | Reopen port; start ReaderThread; error msg | `C7` |
| `C5` | Subprocess timeout (>15 s) | Exception caught; fallback to verbose | `C7` |
| `C6` | User: Leave Host Mode | Send `HOST OFF` frame; stop Worker; start ReaderThread | `C3` |
| `C6` | User: Recovery | Send double-SOH frame; call `exit_host_mode()` | `C3` |
| `C6` | User: Disconnect | Stop Worker; close port | `C0` |
| `C3` | User: Disconnect | Stop ReaderThread; close port | `C0` |
| `C7` | User: Disconnect | Close port if open | `C0` |
| Any | Serial exception / port lost | `disconnect_port()`; emit `connection_changed(False)` | `C0` |

---

## 3. Background Threads

Three thread types are used — never more than one of each at a time.

| Thread | Class | Active in states | Purpose |
|---|---|---|---|
| Init thread | `threading.Thread` (`PK232-Init`) | `C2` | Wakeup sequence, reads `cmd:` prompt |
| Reader thread | `_ReaderThread` | `C3`, `C4`, fallback | Reads raw bytes; dispatches to verbose terminal |
| Host Mode Worker | `HostModeWorker` (`pk232_hostmode_sub.py`) | `C6` | Full-duplex binary frame TX/RX |

**Critical rule:** Only one thread may own the serial port at a time.
Before starting a new thread, the previous one must be stopped and joined.
The sequence for C5 entry is:

```
1. _reader.stop() + join(timeout=2.0)
2. _serial.close()
3. subprocess.run(pk232_hostmode_sub.py)   ← subprocess owns the port
4. new_port = serial.Serial(...)           ← fresh object, no reuse
5. _worker = HostModeWorker(new_port)
6. _worker.start()
```

> **Why a fresh Serial object?** pyserial does not reliably reset internal
> state after close()/open() on Windows. A new object avoids buffer
> contamination from the subprocess phase.

---

## 4. Host Mode Entry — Detailed Sequence

### Phase 1: Wakeup (in `_init_tnc_thread`)

```
SerialManager                    TNC (PK-232MBX)
     │                                │
     │── write b"*" ─────────────────>│  autobaud trigger
     │<── "Ver. 7.1  cmd: " ──────────│  firmware banner + prompt
     │                                │
     │  if SOH found in response:     │  TNC already in Host Mode
     │    → skip to C6               │
     │  if "cmd:" found:             │
     │    → _verbose_ready = True    │
     │    → emit verbose_mode_ready  │
```

### Phase 2: Parameter Upload (in `ParamsUploader.upload`)

```
SerialManager                    TNC
     │                                │
     │── "MYCALL OE3GAS\r" ──────────>│
     │<── "cmd: " ────────────────────│
     │── "MYPTCALL OE3GAS-1\r" ──────>│
     │<── "cmd: " ────────────────────│
     │   ... (all parameters) ...     │
     │── last command ───────────────>│
     │<── "cmd: " ────────────────────│
     │    emit: upload done           │
```

Delay between commands: `_PARAM_DELAY = 0.12 s`
If TNC sends banner instead of `cmd:` → TNC rebooted → emit `params_upload_required`

**P40 (2026-09-25):** `upload()` refuses to run at all if
`SerialManager.is_host_mode` is already true (checked once, before the
first command) — there is no `cmd:` prompt in Host Mode, so every command
would otherwise silently time out (5 s each; 68 commands measured
24.09.2026, ~6 minutes, none reached the TNC). It also aborts after 3
consecutive commands with no `cmd:` response at all, rather than waiting
out the remaining timeouts one by one. Immediately after the last
command, `ParamsUploader.verify()` queries MYCALL/PACLEN/MAXFRAME back
(`SerialManager.query_verbose_value()`, same request/response shape as
above) and compares them to `AppConfig` — still in verbose mode, still
`C4` — logging `"parameter upload verified (N/N)"` on a match. See §14.

### Phase 3: Host Mode Entry (subprocess `pk232_hostmode_sub.py`)

```
Subprocess                       TNC
     │                                │
     │── "HOST 3\r" ─────────────────>│  switch to binary mode
     │<── SOH $4F H P $00 ETB ────────│  HPOLL ACK (confirms Host Mode)
     │    print("OK")                 │
     │    exit(0)                     │
```

After subprocess exits:
```
SerialManager
     │
     ├── reopen port (new Serial object)
     ├── _in_host_mode = True
     ├── start HostModeWorker
     ├── worker.send(HPOLL_OFF)    ← TNC pushes data spontaneously
     ├── sleep(0.5)
     └── emit host_mode_changed(True)
```

---

## 5. Host Mode Exit — Detailed Sequence

### Normal exit (User: "Leave Host Mode")

```
SerialManager                    TNC
     │                                │
     │── worker.send(HOST_OFF) ──────>│  SOH $4F H O N ETB
     │   sleep(0.5)                   │
     │   worker.stop() + join         │
     │   _in_host_mode = False        │
     │   sleep(0.2)                   │
     │── start _ReaderThread ─────────│  back to verbose mode
     │── emit host_mode_changed(False)│
```

### Recovery (stuck Host Mode)

```
SerialManager                    TNC
     │                                │
     │── write FRAME_RECOVERY ───────>│  SOH SOH $4F G G ETB
     │   sleep(0.2)                   │  (double-SOH resync)
     │── exit_host_mode() ────────────│  → normal exit sequence
```

> **Critical:** `HOST OFF` in verbose mode as text (`HOST OFF\r`) does NOT
> work inside binary Host Mode. Only the binary frame works:
> `SOH $4F H O N ETB`  (`$01 $4F $48 $4F $4E $17`)

---

## 6. Qt Signals Emitted by SerialManager

| Signal | When emitted | Payload | MainWindow reaction |
|---|---|---|---|
| `connection_changed` | Port open/close | `bool` | Enable/disable Connect/Disconnect menu |
| `verbose_mode_ready` | C2 → C3 | — | Show verbose terminal; start param upload |
| `params_upload_required` | TNC rebooted during init | — | Re-run `_on_verbose_mode_ready()` |
| `host_mode_changed` | C5 → C6 or C6 → C3 | `bool` | Switch stack to opmode screens; update indicator |
| `status_message` | Any state change | `str` | Show in status bar |
| `frame_received` | C6, per frame | `HostFrame` | Dispatch to `ModeManager.on_frame()` |
| `raw_data_received` | C3/C4, per chunk | `bytes` | Show in verbose terminal |

---

## 7. UI State per Connection State

| State | Mode Indicator | Mode Combo | SEND/RECEIVE | Opmode Screen |
|---|---|---|---|---|
| `C0` OFFLINE | grey "OFFLINE" | disabled | disabled | — |
| `C1` PORT OPEN | grey "OFFLINE" | disabled | disabled | — |
| `C2` INITIALISING | orange "INIT…" | disabled | disabled | verbose terminal |
| `C3` VERBOSE | green "VERBOSE" | enabled | disabled | verbose terminal |
| `C4` UPLOADING | green "VERBOSE" | disabled | disabled | verbose terminal |
| `C5` SWITCHING | orange "SWITCHING" | disabled | disabled | verbose terminal |
| `C6` HOST MODE | blue "HOST MODE" | enabled | enabled | opmode screen |
| `C7` ERROR | red "ERROR" | disabled | disabled | verbose terminal |

---

## 8. SerialManager Properties (Guard Conditions)

All methods that send TNC frames must check these before proceeding:

```python
# Minimum guard for any operation:
if not self._serial.is_connected:
    return

# For Host Mode operations:
if not self._serial.is_host_mode:
    return

# For verbose mode operations:
if not self._serial.is_verbose_mode:
    return
```

The three boolean properties map to states as follows:

| Property | True in states |
|---|---|
| `is_connected` | C1, C2, C3, C4, C5, C6, C7 |
| `is_host_mode` | C6 only |
| `is_verbose_mode` | C3, C4 only |

---

## 9. Error Handling

| Error condition | Recovery action |
|---|---|
| Port open failed | Show error dialog; stay in C0 |
| TNC no response on wakeup | Emit error; start ReaderThread; → C7 |
| Subprocess timeout | Reopen port; start ReaderThread; → C7 |
| Serial exception in Worker | Worker thread exits; `disconnect_port()`; → C0 |
| Stuck in Host Mode (no response) | User: TNC → Recovery; sends double-SOH |
| `params_upload_required` | Automatic: re-call `_on_verbose_mode_ready()` |

---

## 10. Connection Modes (`_connect_mode`)

`MainWindow` sets `self._connect_mode` before calling `init_tnc()`.
This flag controls what happens after parameter upload completes.

| `_connect_mode` | Set by | After upload |
|---|---|---|
| `"verbose"` | `_on_connect_verbose()` (Ctrl+T) | Stay in C3 (verbose terminal) |
| `"host"` | `_on_connect_host()` | Proceed to C5 → C6 (Host Mode) |

---

## 11. Known Timing Constants

| Constant | Value | Purpose |
|---|---|---|
| `_WAKEUP_TIMEOUT` | 3.0 s | Max wait for `cmd:` after sending `*` |
| `_RESTART_DELAY` | ~2.0 s | Wait after TNC RESTART before re-sending preamble |
| `_PARAM_DELAY` | 0.12 s | Delay between each verbose parameter command |
| `subprocess timeout` | 15 s | Max time for `pk232_hostmode_sub.py` |
| `HPOLL N delay` | 0.5 s | Wait after sending HPOLL N before emitting `host_mode_changed` |
| `exit_host_mode delay` | 0.5 s | Wait after HOST OFF before stopping Worker |
| `verbose settle` | 0.2 s | Wait after exit before starting ReaderThread |
---

## 12. CRITICAL RULE: Direct Serial Communication — No Worker/Queue

**Applies to:** all new modules, test scripts, and standalone tools.

### Rule

All communication with the PK-232MBX in Host Mode **must be direct and
synchronous** on the serial port:

```python
# CORRECT — direct, synchronous:
port.write(frame); port.flush()
response = read_until(port, marker, timeout)

# WRONG — worker thread with queue:
worker.send(frame)   # ACK is delayed until port close
queue.put(frame)     # ACK never arrives during the session
```

### Root Cause

The Windows USB driver (Prolific PL2303) buffers incoming frames and
delivers ACKs **only** when a direct `port.read()` is actively waiting
on the port. A worker thread writing via a queue has incorrect timing —
ACKs are withheld until the port is closed.

### Proven on 2026-05-02

| Approach | Result |
|----------|--------|
| `pk232_hostmode.py` — direct `port.write` / `read_until` | ✅ works |
| `pk232_hostmode_works.py` — direct `port.write` / `read_until` | ✅ works |
| `baudot_tx_test.py` with `HostModeWorker` + Queue | ❌ ACKs never arrive |

### Exception

The `HostModeWorker` in the main PK232PY project works because the
**subprocess** (`pk232_hostmode_sub.py`) completes the HPOLL ON/OFF
handshake **before** the worker starts — directly and synchronously on
the port.

### Consequence for New Standalone Scripts

No `HostModeWorker`. Instead: a single thread that owns the port,
writes directly, and reads directly.

## 13. Inline Host Mode Entry (proven 2026-05-02)

For standalone scripts, Host Mode entry works without a subprocess.
All steps use direct synchronous `port.write()` + `read_until()` on the
same serial port object — no worker thread involved until Step 6.

```
Step 1:  port.write(b'\rXFLOW OFF\r\rHOST 3')
         read_until(port, b'cmd:cmd:')

Step 2:  port.write(b'\r')
         read_until(port, b'\r\n')

Step 3:  port.write(HPOLL_Y)
         read_until(port, [HPOLL_ACK, HPOLL_Y])
         → Binary Host Mode confirmed

Step 4:  port.write(HPOLL_OFF)          ← DIRECT, before worker starts!
         read_until(port, bytes([ETB]))  ← TNC responds immediately (HPOLL ON state)

Step 5:  port.write(build_cmd(b'BA'))   ← DIRECT, before worker starts!
         read_until(port, bytes([ETB]))

Step 6:  SerialThread(port).start()     ← Worker takes over port from here
```

**Critical:** Steps 4 and 5 MUST be sent directly on the port BEFORE
the SerialThread starts. If sent via the worker queue, the Prolific USB
driver buffers the ACKs and they never arrive during the session
(only released on port close). See §12 for the general rule.

This is equivalent to what the main PK232PY project achieves via the
subprocess (`pk232_hostmode_sub.py`) — the subprocess performs Steps 1–3,
closes the port, then `serial_manager` reopens it and sends HPOLL_OFF
directly before starting the HostModeWorker.

---

## 14. P40 — Upload-before-Host-Mode guard (2026-09-25)

**Finding (24.09.2026, 21:27):** a hardware run logged 68 parameter-upload
commands, each hitting `write_verbose_wait()`'s 5 s timeout (`no cmd:
after ...`) — ~6 minutes total, and because the TNC was in Host Mode the
whole time, none of the 68 commands actually reached it. Host Mode
expects SOH-framed binary frames (§4/§12); plain ASCII text sent there is
not a command the TNC recognises at all.

**Investigated and NOT found here:** this document's own §2/§10 and
Phase 2/Phase 3 split already state the correct order (upload in verbose
mode, C4, before Host Mode entry, C5→C6), and `main_window.py`'s
`_on_verbose_mode_ready()` has called `ParamsUploader.upload()` before
`enter_host_mode()` since that function's original implementation
(commit 1257114) — git history shows no point where this was ever
reversed. That call site was not the defect.

**What was actually missing:** nothing anywhere refused to run the
upload if some other or future caller ever invoked it while the TNC was
already in Host Mode — the state machine's C4-only precondition for
`ParamsUploader.upload()` existed only as documentation, never as a
runtime check. Fixed in `ParamsUploader.upload()` itself (not in
`main_window.py`): it now checks `SerialManager.is_host_mode` once,
before the first command, and refuses outright (`ERROR` log, sends
nothing, returns `0`) rather than silently timing out repeatedly — see
the transition table row above ("Any → refused"). It also aborts after 3
consecutive commands get no response at all, instead of waiting out
every remaining 5 s timeout individually.

**Also added:** `ParamsUploader.verify()` /
`SerialManager.query_verbose_value()` read MYCALL/PACLEN/MAXFRAME back
immediately after the upload (still C4, still verbose) and compare them
to `AppConfig` — this alone would have made the 24.09.2026 failure
visible in under a second instead of on the next real QSO attempt.
Purely informational: `INFO "parameter upload verified (N/N)"` on a
match, `WARNING` with expected-vs-actual on a mismatch or no answer,
never blocks the `C4 → C3`/`C4 → C5` transition.

See CLAUDE.md's "There is no `cmd:` prompt in Host Mode" gotcha (TNC /
firmware v7.1) for the full writeup, and Testplan.md for the
verification test case.