# PK232PY — Serial Connection State Machine Reference

** Explanation of document sections in german **
Abschnitt 1–2 — 8 Zustände (C0–C7) mit vollständiger Übergangstabelle. Besonders wichtig: C5 "SWITCHING" ist ein eigener Zustand, der im Code implizit existiert aber nirgendwo explizit dokumentiert war.
Abschnitt 3 — Die drei Thread-Typen und die kritische Regel: nur ein Thread darf den Port gleichzeitig besitzen. Das war die Ursache vergangener Bugs.
Abschnitt 4–5 — Die exakten Byte-Sequenzen für Entry und Exit, inklusive des kritischen Hinweises: HOST OFF als Text funktioniert in Binary Host Mode nicht — nur der binäre Frame $01 $4F $48 $4F $4E $17.
Abschnitt 6 — Alle Qt Signals mit ihrer Wirkung auf MainWindow — das ist die Schnittstelle zwischen SerialManager und der UI.
Abschnitt 7 — UI-Zustandstabelle: welche Controls sind in welchem Zustand enabled/disabled. Das verhindert Fehler bei neuen Menüeinträgen oder Buttons.
Abschnitt 10–11 — _connect_mode Erklärung und alle Timing-Konstanten an einem Ort.
Abschnitt 14 — P40 (2026-09-25): Parameter-Upload verweigert sich im Host Mode statt 68x 5s stumm zu verstreichen, plus Stichprobenverifikation nach dem Upload.
Abschnitt 4 (Phase 1) — P43 (2026-09-25): der Wakeup ist jetzt eine aktive Fünf-Schritt-Kette statt eines passiven SOH-Byte-Checks, weil is_host_mode nach einem Neustart der Anwendung nichts über den tatsächlichen Gerätezustand aussagt. P44 ergänzt Stufe 3b (Rückholsequenz), deren Begründung P45 von einem Befund zu einer Vermutung korrigiert.
Abschnitt 15 — P45 (2026-09-25): Recovery meldet jetzt, was sie getan hat, und endet in einem definierten Zustand (verbose, bestätigt, oder der bekannte Fehlerfall) statt stillschweigend nichts zu tun; ein gescheiterter Init zeigt sich nicht mehr als verbunden.
Abschnitt 16 — P46 (2026-09-25): Recovery übernimmt jetzt den Lesepfad VOR dem eigenen Sendevorgang (nicht erst vor der Kette) und wird zur "Emergency Reconnect" — sie funktioniert aus jedem Zustand, öffnet den Port selbst und ist nie gesperrt. TNC-Aktionen (Connect/Disconnect/Host Mode/Recovery) leben jetzt nur noch im TNC-Menü, nicht mehr in der Werkzeugleiste.


**Scope:** `SerialManager` + `MainWindow` connection lifecycle.
Covers all states from port closed to Host Mode active.

**Key files:**
- `src/pk232py/comm/serial_manager.py` — state owner
- `src/pk232py/comm/pk232_hostmode_sub.py` — subprocess for Host Mode entry
- `src/pk232py/ui/main_window.py` — UI reactions via Qt Signals

**Last updated:** 2026-09-25 (P46 — Recovery is the emergency reconnect: owns the read path before its own preamble, works from any state, opens the port itself; TNC actions moved from the toolbar into the TNC menu only, see §16; P45 — Recovery reports its outcome and ends in a defined state, honest connection state after a failed init, see §15; P44 — recovery stage 3b added to the detection chain, see §4 Phase 1; P43 — four-step active TNC-state detection; P40 — upload-before-Host-Mode guard, see §14)

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
| `C2` | Step 1/2 (`*` or CR) → `cmd:`/banner | `_verbose_ready = True`, `verbose_confirmed = True`; emit `verbose_mode_ready` | `C3` |
| `C2` | Step 3 (HPOLL query) → `$4F` frame | TNC genuinely in Host Mode — write `FRAME_HOST_OFF` directly, repeat step 2 | `C3` (if step-2 repeat sees `cmd:`) or step 3b (if not) |
| `C2` | Step 3b (P44, only if step 3 got NOTHING) → recovery sequence, then repeat step 2 → `cmd:` | Verbose confirmed after recovery | `C3` |
| `C2` | All five steps exhausted, nothing usable answered (P43/P44) | Raise/abort — no upload attempted; message names port, baud rate, both possible causes | `C7` |
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
| `C6` | User: Emergency Reconnect | `_take_over_read_path()` (P46 — BEFORE writing anything, see §16); write `FRAME_RECOVERY`/`FRAME_HOST_OFF` directly; run the P43/P44 detection chain (`_init_tnc_thread()`, not `exit_host_mode()` — corrected P45/P46, this row used to describe pre-P45 code) | `C3` on success, `C7` on failure |
| `C6` | User: Disconnect | Stop Worker; close port | `C0` |
| `C3` | User: Disconnect | Stop ReaderThread; close port | `C0` |
| `C7` | User: Disconnect | Close port if open | `C0` |
| `C7` | User: Emergency Reconnect | Same as the `C6` row above — the port is already open (left open on the C7 failure path, §15) | `C3` on success, stays `C7` on failure |
| `C0` | User: Emergency Reconnect (P46) | Opens the port itself (`connect_port()`, using the caller's saved port/baud), then same as the `C6` row above | `C3` on success, `C7` on failure |
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

### Phase 1: Wakeup (in `_init_tnc_thread`) — P43/P44 active detection chain

**Rewritten 2026-09-25 (P43):** the old single-step wakeup ("send `*`,
hope for `cmd:` or a stray SOH byte") could not detect a TNC left in Host
Mode from a previous app session — `is_host_mode` starts `False` on every
fresh `SerialManager` instance regardless of the physical device's real
state, and in Host Mode the TNC answers `*` with **nothing at all** (not
a valid frame there, and it sends nothing unsolicited while HPOLL is ON).
Reproduced on the device 24.09.2026: this is what let a full parameter
upload run into 68 x 5s timeouts with nothing reaching the TNC (P40).

Five steps now run in order (four as of P43, plus P44's step 3b), each
capped at `_TNC_STATE_STEP_TIMEOUT` (1.5 s) — detection itself must never
take longer than the failure mode it prevents (worst case, step 4, is
under 5 s total):

| # | Stimulus | Expected answer | Conclusion |
|---|---|---|---|
| 1 | `*` | banner or `cmd:` | verbose, freshly booted → done |
| 2 | bare `CR` | `cmd:` | verbose, was already awake → done |
| 3 | HPOLL query frame (`build_command(b'HP')`, SOH `$4F` H P ETB — no argument) | any `$4F`-CTL frame | **Host Mode confirmed** → write `FRAME_HOST_OFF` directly (no `HostModeWorker` running yet at this point, so this reuses the byte sequence `exit_host_mode()` sends via the worker, not that method), then repeat step 2 |
| 3b | (P44, only if step 3 got NOTHING at all) recovery sequence — `FRAME_RECOVERY` (double-SOH + GG, TRM 4.1.6), then `FRAME_HOST_OFF` — the same bytes the "Recovery" menu action sends | `cmd:` after a repeated step 2 | verbose confirmed after recovery |
| 4 | — | none of the above answered anything | no PK-232 reachable — abort, message names port, baud rate, and both possible causes (wrong port/baud vs. a hung TNC) |

Step 2 is tried **before** step 3 deliberately: the already-awake,
verbose TNC is the more common case and is settled by a single `CR`;
step 3 is the only one that can reach a genuinely-Host-Mode TNC, since it
actively asks in frame language instead of waiting for an unsolicited
answer that never comes. This is also what closes Backlog.md's P29
(wakeup CR-fallback) — the app now has this built in, where before it
only existed in `tools/hw_check.py`.

**Step 3b (P44, 2026-09-25; the "why" corrected P45, 2026-09-25):** if
step 3's HPOLL query itself got no response at all — not even a
malformed frame — the TNC may be a genuine Host Mode TNC that simply
cannot answer. P44 suspected an application killed abruptly while in
Host Mode (`Ctrl-C` in the console, observed 25.09.2026) leaving the
TNC's own frame parser mid-frame, waiting for an `ETB` that never comes
and discarding everything further, including a fresh `SOH`. **P45
corrected this to a suspicion, not a measured finding** — a healthy TNC
in Host Mode also answers nothing to a plain terminal program (it only
processes framed Host Mode data there), so observed silence cannot by
itself distinguish "stuck mid-frame" from "working normally" — see
CLAUDE.md's "P44's half-frame theory" gotcha. The step itself is
unaffected either way: step 3b sends the documented recovery sequence — the exact
`FRAME_RECOVERY` bytes the "Recovery" menu action already sends,
followed by `FRAME_HOST_OFF` — directly on the port (not via
`recovery()`/`exit_host_mode()`, for the same reason step 3 writes
`FRAME_HOST_OFF` directly: no `HostModeWorker` exists yet at this point
in the connection sequence), then repeats step 2 once more. Harmless if
no TNC is attached at all. Every step (1 through 3b) logs both the bytes
it sent and whatever it received, in hex, at `DEBUG` level — costs
nothing at 0 bytes and saves a repeat hardware run the next time this
needs diagnosing.

On success (any of steps 1, 2, or 3-then-2), `_finish_verbose_init()`
sets **both** `_verbose_ready` (existing) and the new
`SerialManager.verbose_confirmed` property, then emits
`verbose_mode_ready` exactly as before. `verbose_confirmed` is the
positive-evidence flag `ParamsUploader.upload()` now also requires
(P43.2, in addition to P40.2's `is_host_mode` check) — reset to `False`
at the start of every `_init_tnc_thread()` run, cleared again on a
successful Host Mode entry. See CLAUDE.md's "`is_host_mode` is the
SOFTWARE's belief" gotcha for the full picture, and §8 below (the
`is_host_mode`/`is_verbose_mode` guard-condition table) — `verbose_confirmed`
is a third, stricter guard alongside those two, never a replacement for
either.

On failure (step 4), the connection sequence aborts entirely — no
parameter upload is attempted from this connect cycle at all.

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

### Recovery (stuck Host Mode) — rewritten P45, read-path ordering fixed P46, see §15/§16 for the full picture

```
SerialManager                    TNC
     │                                │
     │── _take_over_read_path() ─────│  stop ReaderThread, join, clear
     │                                │  input buffer (P46.A - BEFORE any
     │                                │  write, not just before the chain)
     │── write FRAME_RECOVERY ───────>│  SOH SOH $4F G G ETB
     │   sleep(0.2)                   │  (double-SOH resync)
     │── write FRAME_HOST_OFF ───────>│  SOH $4F H O N ETB, direct write
     │   sleep(0.2)                   │  (not via exit_host_mode() - see §15,
     │                                │   same reasoning as step 3/3b in §4)
     │── _init_tnc_thread() ─────────>│  the EXISTING P43/P44 chain,
     │                                │  reused outright to determine
     │                                │  and report the result (§15) -
     │                                │  calls _take_over_read_path() itself
     │                                │  too, a harmless no-op re-clear
```

> **Critical:** `HOST OFF` in verbose mode as text (`HOST OFF\r`) does NOT
> work inside binary Host Mode. Only the binary frame works:
> `SOH $4F H O N ETB`  (`$01 $4F $48 $4F $4E $17`)

---

## 6. Qt Signals Emitted by SerialManager

| Signal | When emitted | Payload | MainWindow reaction |
|---|---|---|---|
| `connection_changed` | Port open/close | `bool` | Enable/disable Connect/Disconnect menu (TNC menu only, P46 — no toolbar equivalent anymore); `True` → indicator "connecting" (P45.2, NOT "verbose" — see §15) |
| `verbose_mode_ready` | C2 → C3 | — | Show verbose terminal; start param upload; indicator "verbose" |
| `params_upload_required` | TNC rebooted during init | — | Re-run `_on_verbose_mode_ready()` |
| `host_mode_changed` | C5 → C6 or C6 → C3 | `bool` | Switch stack to opmode screens; update indicator |
| `status_message` | Any state change | `str` | Show in status bar AND (if it matches an error keyword) a dialog (P45.2 — used to be either/or) |
| `init_failed` (P45.2) | C2 → C7, detection chain found nothing | — | Indicator → "error"; disable mode combo; keep Connect/Recovery enabled (§15) |
| `recovery_finished` (P45.1, P46) | `recovery()`'s background thread finishes | `bool, str` | Re-enable/relabel the "Emergency Reconnect" TNC menu entry; show the message in the status bar + verbose terminal, dialog on failure (§15/§16) |
| `frame_received` | C6, per frame | `HostFrame` | Dispatch to `ModeManager.on_frame()` |
| `raw_data_received` | C3/C4, per chunk | `bytes` | Show in verbose terminal |

---

## 7. UI State per Connection State

| State | Mode Indicator | Mode Combo | SEND/RECEIVE | Opmode Screen |
|---|---|---|---|---|
| `C0` OFFLINE | grey "OFFLINE" | disabled | disabled | — |
| `C1` PORT OPEN | blue "CONNECTING..." (P45.2) | disabled | disabled | — |
| `C2` INITIALISING | blue "CONNECTING..." (unchanged from C1 - nothing about the indicator changes until the chain resolves) | disabled | disabled | verbose terminal |
| `C3` VERBOSE | amber "VERBOSE MODE" | enabled | disabled | verbose terminal |
| `C4` UPLOADING | amber "VERBOSE MODE" | disabled | disabled | verbose terminal |
| `C5` SWITCHING | blue "SWITCHING..." | disabled | disabled | verbose terminal |
| `C6` HOST MODE | green "HOST MODE" | enabled | enabled | opmode screen |
| `C7` ERROR | red "ERROR" (P45.2) | disabled | Connect + Emergency Reconnect enabled in the TNC menu (P46 — no toolbar buttons to disable anymore) | verbose terminal |

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

# For the parameter uploader specifically (P43.2) — stricter than
# is_verbose_mode: requires ACTIVE confirmation this session, not just
# the software's belief that no Host Mode transition has happened yet.
if not self._serial.verbose_confirmed:
    return
```

The boolean properties map to states as follows:

| Property | True in states |
|---|---|
| `is_connected` | C1, C2, C3, C4, C5, C6, C7 |
| `is_host_mode` | C6 only |
| `is_verbose_mode` | C3, C4 only |
| `verbose_confirmed` (P43) | C3, C4 — but ONLY once `_init_tnc_thread()`'s detection chain (§4 Phase 1) has actively seen evidence this session; unlike the other two, this is never true merely because no Host Mode transition happened to run yet |

---

## 9. Error Handling

| Error condition | Recovery action |
|---|---|
| Port open failed | Show error dialog; stay in C0 |
| Detection chain exhausted (§4 Phase 1 step 4) | Emit `init_failed` + `status_message`; → C7; port stays OPEN (Connect/Recovery need it) — see §15 |
| Subprocess timeout | Reopen port; start ReaderThread; → C7 |
| Serial exception in Worker | Worker thread exits; `disconnect_port()`; → C0 |
| Any state at all — stuck in Host Mode, mid-error, or not connected yet | User: TNC → Emergency Reconnect (Host Mode Recovery), Ctrl+R; opens the port if needed, runs the full sequence + detection chain, reports the result (§15/§16, P46 — never gated on `is_connected`; P45 — used to send the sequence and nothing else) |
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

---

## 15. Recovery — report what happened, end in a defined state (P45, 2026-09-25)

**Finding (25.09.2026, operator at the device):** TNC in Host Mode → app
started → Connect → the detection chain's own error → **the app still
showed itself as connected** (Host Mode button enabled/green-looking,
firmware still "unknown") → Recovery pressed → **no visible reaction at
all** → "Host Mode" pressed → "SWITCHING" → Baudot screen → the TNC was
in fact reachable again. Two gaps: the connection state lied after a
failed init, and Recovery gave no feedback at all about whether it had
worked — that only became apparent by accident, via a completely
different button.

`SerialManager.recovery()` now runs in a background thread, in three
parts, each one reported:

1. **Send the recovery sequence** — `FRAME_RECOVERY` (double-SOH + GG,
   TRM 4.1.6) then `FRAME_HOST_OFF`, both via `_write_raw()` directly (it
   already hex-logs every TX at `DEBUG`) — not via `exit_host_mode()`,
   which assumes a running `HostModeWorker` that does not exist yet here
   (same reasoning as §4 Phase 1's steps 3/3b).
2. **Determine the state** — calls `_init_tnc_thread()` itself, the
   EXACT SAME P43/P44 detection chain a normal connect uses (§4 Phase 1)
   — no second version of it is built for Recovery. That chain already
   implements "CR → `cmd:`; else HPOLL frame; else the recovery sequence
   again" as its own steps 2/3/3b, plus a step 1 (`*`) that is harmless
   to try again here.
3. **Report the result** — emits `recovery_finished(success: bool,
   message: str)`:

   | Result | Message |
   |---|---|
   | `cmd:` confirmed | `"Connection recovered - TNC is at the command prompt (verbose mode)."` (P46 — was "Recovery successful - ..." under P45; renamed with the "Emergency Reconnect" framing, see §16) |
   | only HPOLL answers (step 3 of the chain) | intermediate: `"TNC responds in Host Mode - leaving Host Mode..."` (via `status_message`, from inside the chain itself), then step 3's own exit-and-recheck decides the FINAL outcome, one of the two rows above/below |
   | nothing answers | `"Recovery did not reach the TNC. Power-cycle it and reconnect."` |

   `MainWindow._on_recovery_finished()` shows the message in the status
   bar AND the verbose terminal's RX window (`[SYS] ...`, so it is still
   there in a later capture, not just a transient status-bar line), plus
   a warning dialog on failure. `_on_recovery()` disables and relabels
   the Recovery button/menu action ("Recovery running...") for the whole
   duration, restored by `_on_recovery_finished()` either way.

**End state on success:** `C3` VERBOSE, `verbose_confirmed` set. From
there the operator continues normally — parameter upload and Host Mode
entry run over the existing paths (`verbose_mode_ready` fires exactly as
after any other successful connect; no Recovery-specific handling).

**End state on failure:** whatever `_init_tnc_thread()`'s own step 4
already leaves behind (§2's "All five steps exhausted" row → `C7`) —
`verbose_confirmed` stays `False`, the port stays open.

### The connection-state half of the same finding (P45.2)

`connection_changed(True)` fires the instant `connect_port()` opens the
port — in `C1`, well before `init_tnc()` (`C2`) has confirmed anything.
`_update_connection_ui(True)` used to jump straight to the `"verbose"`
mode-indicator state on port-open alone; if `init_tnc()` then failed,
nothing ever corrected that, leaving the indicator reading VERBOSE (and
the "Enter Host Mode" button enabled) indefinitely. Fixed:

- `_update_connection_ui(True)` now sets a new, honest `"connecting"`
  indicator state instead — it only ever resolves forward, via
  `verbose_mode_ready` (success, → `"verbose"`) or the new
  `SerialManager.init_failed` signal (failure, → `"error"`,
  `MainWindow._on_init_failed()`).
- The serial port is deliberately left open on the failure path (no
  `disconnect_port()` call) — Recovery needs a real port object, and
  both Recovery and Connect must stay usable as the way out.
  `_on_init_failed()` disables the mode combo and "Enter Host Mode"
  (nothing there is actually usable without a confirmed device) but
  explicitly re-enables Connect and Recovery.
- `_on_connect_verbose()`/`_on_connect_host()` now check `is_connected`
  first and retry `init_tnc()` directly on the already-open port when
  it is already `True`, instead of going through `connect_port()` again
  — that method's own "port already open" guard used to make a second
  Connect press after a failed init silently do nothing at all.
- `_on_status_message()`'s error path used to be an if/else (dialog OR
  status bar, never both) — an error now always reaches the status bar
  as well as the dialog.

## 16. Recovery becomes Emergency Reconnect; TNC actions move into the menu (P46, 2026-09-25)

**Finding (25.09.2026, screenshot):** the RX window showed
`␁␁OGG␁␁␁OHONO[SYS] Recovery did not reach the TNC.` before the error
message — that garbled text IS `FRAME_RECOVERY`/`FRAME_HOST_OFF`'s own
bytes as raw text (`$4F` = `'O'`). `_recovery_thread()` (P45) wrote its
own preamble via `_write_raw()` while `ReaderThread` was STILL RUNNING —
the same thread `_init_tnc_thread()` always stops before its own direct
reads. The still-running reader consumed the TNC's response to the
preamble and dumped it into the verbose terminal (`raw_data_received` is
only ever emitted from `ReaderThread`), while the detection chain's own
direct reads — which only start once `_init_tnc_thread()` itself runs,
AFTER the preamble — saw nothing. Recovery reported failure even when
the TNC had actually answered.

### A. `_take_over_read_path()` — one shared handover, used before ANY write

A new `SerialManager._take_over_read_path()` (stop `ReaderThread`, join,
clear the input buffer, reset `_verbose_confirmed`) replaces the inline
block `_init_tnc_thread()` used to open with. Both `_init_tnc_thread()`
and `_recovery_thread()` call it — `_recovery_thread()` calls it FIRST,
before writing `FRAME_RECOVERY`/`FRAME_HOST_OFF` itself, not just before
calling `_init_tnc_thread()` afterward. `_init_tnc_thread()` still calls
it too, right where its old inline block was — a harmless no-op re-clear
in the Recovery case (the reader is already stopped), which is exactly
what is wanted: any ack/echo of Recovery's own preamble must not be
mistaken for the chain's own step 1 (`*`) response.

Since `raw_data_received` is only ever emitted from `ReaderThread`,
stopping it before every write automatically means no detection-phase
byte can reach the RX window during Recovery — no separate terminal-side
fix was needed for that half of the finding.

### B. Recovery is the emergency reconnect — works from ANY state

`SerialManager.recovery(port_name=None, baudrate=None)` no longer
requires `is_connected` up front. If the port is not open, it opens it
itself via `connect_port()`, using the port/baud the caller passes in
(`MainWindow` passes `AppConfig.tnc.port`/`tbaud` — the same saved
config `_open_connect_dialog()` already reads). With no port open and
nothing configured, it does nothing (`return False`) — there is
genuinely nothing to recover. Once a port exists, the rest is unchanged
from P45 (§15): send the sequence, run the shared detection chain,
report the result.

`MainWindow._update_connection_ui()` no longer gates the Emergency
Reconnect action on `connected` — every OTHER TNC action there
legitimately depends on connection state, but Recovery is the way out
of literally any state (no connection, mid-error, stuck in Host Mode)
and must never be locked out. Its success message changed to
`"Connection recovered - TNC is at the command prompt (verbose mode)."`
(was `"Recovery successful - ..."` under P45) to match the new framing.

### C. TNC actions live in the TNC menu only — "Connect" was ambiguous

The toolbar used to duplicate `Connect`/`Disconnect`/`Host Mode`/
`Recovery` from the TNC menu — and "Connect" there was genuinely
ambiguous: the serial connection to the TNC (toolbar) vs. the AX.25/
PACTOR/AMTOR station connection the opmode screens show their own
Connect for (Packet's chip-based connect, PACTOR/AMTOR's own connect
flows). Both meanings were visible on screen at once on the Packet/
PACTOR/AMTOR screens. Fix: the toolbar now only ever shows the
operating-mode selector, the TNC-Firmware label and the mode indicator.
All TNC connection actions live exclusively in the TNC menu:

```
Connect + Enter Terminal Mode...        Ctrl+T
Connect + Enter Host Mode...            Ctrl+M
Leave Host Mode + Return to Terminal    Ctrl+L
Disconnect + Close Serial Port          Ctrl+D
---
Emergency Reconnect (Host Mode Recovery)   Ctrl+R
---
MailDrop...
```

`_on_host_mode_enter()` (only ever reachable from the removed toolbar
"Host Mode" button — no menu entry ever called it) is retired. "Connect
+ Enter Host Mode..." already covers the same case: its own
`is_connected` retry branch re-runs the P43 detection chain on an
already-verbose connection (near-instant) and then the existing
upload + `enter_host_mode()` flow runs exactly as it always has via
`_on_verbose_mode_ready()` — more robust than the old direct shortcut,
since it re-confirms the TNC is actually still there first.

**Shortcut collision resolved:** the TNC menu's `Ctrl+D` ("Disconnect +
Close Serial Port") collided with the Packet screen's own channel-
disconnect shortcut (`Ctrl+D`, P42) — two different "disconnect"
actions (serial port vs. station link) sharing one key was exactly the
kind of "Connect"/"Disconnect" ambiguity this package set out to
remove. The Packet channel-disconnect shortcut moved to `Ctrl+K`
(checked: not bound to anything else anywhere in the app) — still also
reachable from the chip's own context menu regardless.

### A note on the step 3b "why" (P44 → corrected P45)

Step 3b (§4 Phase 1) was motivated by a suspicion — a process killed
abruptly mid-frame leaves the TNC's parser stuck waiting for an `ETB` —
that P45 downgraded from a stated finding to a labelled suspicion: **a
healthy TNC in Host Mode is silent in a plain terminal program too**
(it only processes framed binary data there), so observed silence alone
cannot distinguish "stuck" from "working normally". See CLAUDE.md's
"P44's half-frame theory" gotcha. Step 3b itself is unaffected — it
remains cheap and harmless to try regardless of which explanation (if
either) is eventually confirmed by a real measurement.