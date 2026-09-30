# PK232PY - Gotchas: Packet (HF/VHF)

> Channel-Modell, ChannelBar, LinkTable, MHEARD, RX-Dokumente.
> Ausgelagert aus CLAUDE.md (unveraendert uebernommen, Stand 2026-09-29).

### Packet (HF / VHF)

- **Channel model since P70 (30.09.2026): `UI_CHANNEL` no longer exists —
  the monitor is `MON_VIEW`, channel 0 is an ordinary TNC channel.** The
  channel bar is `[ MON ] [ 0 ] [ 1 ] … [ 9 ]`. `MON_VIEW = "MON"`
  (`packet_screen.py`, a `str` on purpose so it can never be mistaken for a
  TNC channel 0–9) is the key of the monitor/unproto/system-message view:
  `_rx_docs[MON_VIEW]`, monitor frames (`$3F`), own unproto lines, `$5F`
  and the optional link-message mirror (config key
  `show_link_messages_in_ui_channel`, name unchanged) all go there. The MON
  chip has no state, no editor, no context menu; `ChannelBar.current()` is
  `int | "MON"`, `channel_changed` carries `object`, Ctrl+Up/Down steps
  through eleven positions (MON, 0 … 9). Channels 0–9 are treated alike:
  free / calling / connected / unconfirmed (P67) / **disconnecting** (new,
  CO state 4) / failed. `LinkTable` is the only source of chip states;
  `MainWindow._apply_link_to_chips()` is the only caller of
  `set_channel_state()`; mode activation repaints the chips from the table
  (`_repaint_chips_from_link_table()`), `reset_channels()` is not called
  there any more. **Unproto** (text typed in the MON view) goes out as a
  `$2n` data frame on `LinkTable.lowest_free_channel()` (state exactly
  `free`); with all ten busy nothing is sent, the text stays and MON shows
  "all 10 channels are connected - no free channel for unproto". The MON
  view echoes `> text  [via chN]`. The UN path is sent before the first MON
  frame and whenever the via field changed (`_unproto_path_sent`). The
  Unproto button now only selects MON and sends the path; a connection never
  locks it (`set_link_state()` is a documented no-op). `USERS n` accepts
  exactly channels 0 … n−1, so the chip tooltip warns for `ch >= USERS`.
  `USERS` defaults to 10 (config and dialog); a stored INI value is kept.
- **Known Facts, Device B, P69/P70 (T146/T147, 30.09.2026, Release
  01.AUG.91; logs `20260930_210627_channel_probe.log`,
  `20260930_212141_channel_probe.log`).** F1 Data on a free channel 3 and 9
  goes out as a UI frame over the UNPROTO path (T146 B.1/B.2 PASS). F2 The
  same on channel 3 while channel 0 is connected to the TinyBox works, and
  the connection on channel 0 keeps running (`\r` → prompt on `$30`; B.3
  PASS). F3 An incoming connection lands on the **lowest free** channel:
  first caller channel 0, second caller (USERS 10) channel 1. F4 With
  `USERS 1` the second caller is rejected (`DM` on the air, Direwolf
  capture); the host gets `$50 "Connect request: OE3GAS-3"` — and only for
  a rejected call: an accepted call shows just `CONNECTED to <call>`. F5
  `USERS` was 1 (`HFPacketConfig.users` old default). F6 After `DI`, `CO`
  reports state 4 (disconnecting) for a moment, then free. Not measured on
  Device A/C.
- **PASSALL = `PX`, not `PA` and not `PS`** — see the mnemonic-table note above.
- **Data sent on channel 0 is split into UI frames of at most PACLEN
  bytes each — hardware-confirmed, Device B, 27.09.2026 (P62/P62a,
  T139 R4).** 204 characters sent in one `send_data()` call, with
  `PACLEN` at its then-current value of 64, arrived as **4 separate UI
  frames: 64 + 64 + 64 + 12 bytes**, split exactly at the PACLEN
  boundary (confirmed via a real AX.25 decoder capture — the
  continuation frames no longer start with a valid APRS data type
  character, so Direwolf logs "Unknown APRS Data Type Indicator" for
  each, but still shows one frame per split). **Consequence for the
  future APRS mode (P63): APRS needs exactly ONE frame per message, so
  the mode must own PACLEN — query and set it — the same way it
  already owns UNPROTO** (`tools/hw_check.py aprs_query`'s A.7/A.8 probe
  the verbose range and the Host Mode `PL` mnemonic for this reason;
  `aprs_tx`'s R3/R6 rounds measure character-fidelity and single-frame
  behaviour separately, at PACLEN 128 and at a probed-safe maximum,
  never at whatever value happens to be configured for something
  else). Not yet measured on Device A or C.
- **The Host Mode `UN` query reformats the UNPROTO path it echoes back
  — hardware-confirmed, Device B, 27.09.2026 (P62, T138 A.4).** Setting
  `UNPROTO APZ232 VIA WIDE1-1,WIDE2-1` verbose, then querying `UN` in
  Host Mode, returned `UNAPZ232 via WIDE1-1, WIDE2-1` — lowercase
  `via`, and a space inserted after the comma between digipeaters —
  not a byte-for-byte echo of what was sent. Any future code that
  reads `UN` back in Host Mode (P63) must parse this tolerant of case
  and whitespace, never compare it against the exact string that was
  set.
- **HF/VHF init-frame inheritance trap.** `HFPacketMode.get_init_frames()` now
  emits `VH N` + `HB 300` + `MX <maxframe>` + `SL <slottime>` + `MN Y` (selects
  the 300 Bd HF FSK modem and resets MAXFRAME/SLOTTIME to HF Packet's own
  configured values — `maxframe`/`slottime` constructor args, defaulting to
  `HFPacketConfig`'s own defaults, 1/30, P18.1/P19.3). `main_window.py`
  builds it with the real configured values in `_build_mode_instance()`,
  the ONE place that happens (P19.2 — see §7 and the "UI / PyQt6" gotcha
  on why every `set_mode()` call must route through it).
  `VHFPacketMode` therefore must **NOT** call `super().get_init_frames()` — that
  `VH N` would immediately undo the `VH Y` it sends in `get_activate_frames()`
  and drop VHF back to the HF modem. VHF builds its own list (`HB 1200`, `MX 4`,
  `SL 10`, `MN Y`). Leaving VHF Packet also sends `VH N`
  (`_on_mode_selected` → `VHFPacketMode.vhf_off_frame()`, T51).
- **Rule: any parameter one band sets on activation, the other band must
  set too — otherwise it keeps whichever value the last-active band left
  behind.** Found via `SLOTTIME` (T112, hardware-confirmed 2026-09-22):
  VHF Packet sets `MX 4` / `SL 10` on activation; HF Packet did not reset
  them on its own activation, so a VHF → HF switch left HF Packet running
  with VHF's `SLOTTIME 10` instead of its own configured value. Fixed in
  P18.1 (`HFPacketMode.get_init_frames()` now sends `MX`/`SL` too) — but
  the rule is general, not specific to these two mnemonics: any future
  parameter one band's `get_init_frames()`/`get_activate_frames()` sets
  needs the same reset on the other band, or it inherits a silent
  cross-band leak like this one. `MAXFRAME`'s own T112 result was
  INCONCLUSIVE on the first run (it already equalled VHF's value before
  the test started) — `tools/hw_check.py t112` now pre-sets both to a
  neutral value first so this can't happen again (P18.3).
- **Connect ↔ Unproto are mutually exclusive (T39).** `set_link_state()` greys
  `btn_unproto` while connected/calling; `_on_packet_unproto()` greys
  `btn_connect` while Unproto is on (link-busy proxy = `btn_disconnect.isEnabled()`).
- **Two parallel Host Mode frame decoders — `comm/frame.py::FrameParser` vs
  `comm/serial_manager.py::_make_host_frame()`.** `FrameParser` is used by
  `tools/mock_tnc_bbs.py` and the Host Mode subprocess path; `_make_host_frame()`
  is what `SerialManager`'s reader thread actually builds `HostFrame`s with
  for a **connected TNC at runtime** — the one that matters for the real app.
  They re-implement the same CTL-byte mapping independently and can drift:
  `_make_host_frame()` hardcoded `channel=15` for every CTL byte except `$3x`
  until the 2026-09-20 fix ("Fix channel nibble extraction for 4x and 5x
  frames") — a pre-existing bug (commit ff17aa01, 2026-04-24) that was
  invisible until the ChannelBar sprint became the first code to actually use
  the channel of a $5x LINK_MSG frame. **Still open, deliberately not
  touched:** `_make_host_frame()`'s `elif` chain has no branch for `$40–$4E`
  (LINK_STATUS) — those frames fall through to `else` and are built as
  `CMD_RESP` instead, possibly the same root cause as the "HFPacket/VHFPacket:
  CMD_RESP reaches mode" item further down — needs a hardware test before
  fixing (see Backlog.md Priority 1). Consolidating the two decoders into one
  is filed as tech debt, not done in this sprint (serial-layer changes were
  explicitly out of scope beyond the one-line channel-nibble fix).
- **Channel model (2026-09-20, ChannelBar sprint). Correction, Device B,
  P66/T142 (2026-09-28): "no CSTATUS poll in Host Mode" is WRONG — TRM
  4.3.3's per-channel CO (Link Status) query works exactly as
  documented.** The original claim ("the PK-232 never tells the host
  'channel N is connected to X' on demand") stood flagged as unmeasured
  since P65; `tools/hw_check.py link_carry_host` (T142,
  `20260928_094231_link_carry_host.log`) measured it directly:
  `HostModeProtocol.cmd_link_status(ch)` (`comm/hostmode.py`, built long
  before this but never called by production code) sent per channel,
  channel 1 (connected to OE3GAS-1) answered `CO41000OE3GAS-1`, a free
  channel answered `CO00000` — TRM 4.3.3's own byte layout (`SOH $4x
  'C' 'O' a b c d e <path> ETB`, five status bytes each "value OR'd
  with $30", path with NO separator) confirmed exactly.
  `tools/hw_check.py::decode_link_status()` decodes this (P65 A.6,
  corrected P66 B.5 — all five status bytes masked `& 0x0F`, not
  returned raw; v2/conperm as `bool`). **Still unmeasured on Device
  A/C** — treat as confirmed for Device B (MBX, 01.08.1991) only until
  a run on the other devices says otherwise (P37's own device-
  attribution rule). P67 will use this query as the connection table's
  own reconciliation point at every verbose↔Host Mode switch. The
  channel a frame belongs to lives only in the
  low nibble of that frame's CTL byte (`ctl_channel()` in `comm/constants.py`
  — see the two-decoders gotcha above for where that nibble is actually
  extracted at runtime). **Superseded by the Link table (P67, see the
  dedicated section below) — `HFPacketMode.on_channel_state()` and
  `MainWindow._make_channel_state_handler()` no longer exist.** The
  channel model is still local bookkeeping built entirely from frames
  that already went by, but it now goes through ONE object
  (`comm/link_table.py::LinkTable`), fed from $5x link messages AND
  Host Mode CO (Link Status) answers AND verbose-mode text, not just
  the $5x messages alone — because P66/P66b proved CO answers reliably
  (the "no CSTATUS poll" premise this bullet's own P65 correction above
  already retracted) and a verbose↔Host Mode switch needs to survive on
  BOTH sides of it, not just within one Host Mode session.
  `ChannelBar` (10 chips, channels 0–9, `packet_screen.py`) is still the
  single source of truth for "which channel do Connect/Disconnect/TX
  act on right now" — `PacketBaseScreen.current_channel()` is a thin
  proxy to `channel_bar.current()` — but its chip STATE (free/calling/
  connected/unconfirmed) is now driven exclusively by LinkTable's own
  `subscribe()` callback, never set directly by a mode or by MainWindow
  itself. MainWindow no longer hardcodes channel 1 anywhere in the
  Packet connect/disconnect/TX path — see
  `_on_chip_connect_requested`/`_on_chip_disconnect_requested`/`_on_packet_tx_enter`
  (P42, 2026-09-24, renamed from `_on_packet_connect`/`_on_packet_disconnect`
  — see the "connect in the chip" bullet below).
- **Link table (P67, 2026-09-28) — one table, its inputs, who resets
  it.** `MainWindow` owns exactly one `comm/link_table.py::LinkTable`
  (Qt-free, unit-testable without a `QApplication`) and one
  `subscribe()` callback (`MainWindow._on_link_table_change()`) — the
  ONLY place `ChannelBar.set_channel_state()` is ever called, for
  BOTH Packet screens (only one is visible at a time, but keeping both
  in sync means switching HF↔VHF never shows a stale chip). Inputs,
  each its own method, never called from outside `comm/link_table.py`
  except by name:
  - `on_host_link_message(ch, text)` — a $5x link message, channel from
    its own CTL nibble (never guessed from callsign, P47).
  - `on_link_status(status)` — a Host Mode CO (TRM 4.3.3) answer,
    decoded via `comm/link_status.py::decode_link_status()` — the
    only input that marks a channel CONFIRMED, paired with
    `mark_unconfirmed()` below.
  - `on_verbose_line(line)` / `on_verbose_cstatus(parsed)` — verbose-
    mode text (`MainWindow._on_vt_rx_data()` feeds every received line
    through one or the other, never both for the same line: a
    `parse_cstatus()`-shaped line goes through `on_verbose_cstatus()`
    for its own exact partner extraction — no trailing punctuation
    like a `;` after a callsign — everything else through
    `on_verbose_line()`).
  - `on_local_connect_attempt(ch, callsign)` / `on_local_disconnect_
    request(ch)` — the operator's OWN action (typing a callsign into a
    chip's editor, or "Disconnect" in its context menu) — optimistic
    local state (CALLING/FREE) shown immediately, before any TNC
    answer; confirmed or corrected by the next real input above.
  - `mark_unconfirmed()` — every channel the table currently believes
    CONNECTED becomes UNCONFIRMED (dashed chip border, P67 Teil C.1) —
    called once at the START of every verbose→Host Mode reconciliation
    round (`MainWindow._update_host_mode_ui(True)`), immediately
    followed by a Host Mode CO probe of channels 0–9 whose answers
    (via `on_link_status()`) confirm or correct each one.
  - `reset()` — clears every channel to FREE. Called ONLY on a genuine
    loss of basis for believing anything at all: a TNC disconnect, a
    fresh boot banner (`fresh_boot_defaults`), or a Recovery run with
    nothing to reconcile against. **Never** on an ordinary verbose↔Host
    Mode switch, and **never** from `PacketBaseScreen.reset_channels()`
    on a mode (re)activation either (P67, Teil C — see that method's
    own docstring for a real race this used to lose to: a CO answer
    confirming a carried-over channel can arrive on the SAME Host Mode
    entry BEFORE the 300ms mode-activation timer that used to wipe it
    straight back to free). `mark_unconfirmed()` + reconciliation is
    what a verbose↔Host Mode switch uses instead, precisely so a real
    connection is never forgotten just because the app briefly could
    not confirm it.
  `SerialManager.exit_host_mode(io_channel=...)` sends a Link Status
  `CO` on `io_channel` as the LAST `$4x` frame, itself, before `HOST
  OFF` (P66b's own finding, next bullet) — `MainWindow._on_host_mode_
  exit()` decides which channel (the Packet screen's own visible
  channel, if `LinkTable` confirms it CONNECTED) and whether to follow
  up with a verbose `CONVERSE` (only if the table's own `.converse` was
  `True` before Host Mode was entered AND that channel is still
  connected — never on a free channel, which sends every further line
  as an UNPROTO UI frame instead, P66b B.5).
- **Known Facts, Device B, P67 (28.09.2026 14:57–15:04, Release
  01.AUG.91 — full detail: `docs/P67_Link_Table_Packet_Spec.md`).**
  M1 a Host Mode entry from Converse with a connection already up
  succeeds with no late-entry handshake needed. M2 Host Mode `CO` per
  channel reliably reports state and partner: connected
  `CO41000OE3GAS-1`, free `CO00000` (see `decode_link_status()`). M3 A
  verbose-built connection lands on the SAME channel (0) once in Host
  Mode. M4 Data flows on the connected channel's own `$3n` (a `\r` on
  channel 0 got a counterpart-terminal prompt back on `$30`). M5 VHF
  Packet's own activation/init frames (`PA`, `VH Y`, `HB 1200`, `MX 4`,
  `SL 10`, `MN Y`) do not disturb an existing connection; OPMODE stays
  `PA` throughout. M6 After `HOST OFF`, the verbose I/O channel is the
  channel of the LAST `$4x` frame sent (see the dedicated bullet
  above). M7 Sending `CO` on the connected channel as that last `$4x`
  frame makes verbose `CSTATUS` show `IO` there, and `CONVERSE` + `CR`
  gets the counterpart's prompt back. M8 The connection survives a
  Host→verbose→Host round trip. M9 `CHSWITCH` reads `$00` (see the
  dedicated bullet above). M10 A channel-scoped verbose line can carry
  a `\x00<digit>: ` prefix (`split_channel_prefix()`), e.g. `\x000:
  ?already connected …`, `\x009: cmd:` — when exactly this prefix
  appears is NOT measured (only with several active channels? only for
  a channel other than the I/O one?); `on_verbose_line()` handles both
  the prefixed and unprefixed forms. Not yet measured on Device A/C.
- **The active verbose channel after `HOST OFF` is the channel of the
  LAST `$4x` frame sent, not necessarily the connected one — confirmed
  for Device B, P66b, B.3/B.4 (2026-09-28).** T142's own D.1 probe
  proved this directly: sending `CO` on a known-free channel (3) as
  the very last `$4x` frame before `HOST OFF` made verbose `CSTATUS`
  call channel 3 — not the actually-connected channel 1 — the active
  ("IO") one afterwards; a run without that final probe left channel 9
  (the last channel `_probe_all_channel_links()` had queried) as the
  active one instead. **Rule for any future code that returns to
  verbose expecting to land on a specific channel (P67's own
  connection table): send a `$4x` frame (e.g. `CO`, the harmless
  Link Status query) on the TARGET channel as the LAST Host Mode frame
  before leaving Host Mode — this is the only known way to choose the
  active verbose channel, since `CHSWITCH` is often not usable (next
  bullet).** Still unmeasured on Device A/C.
- **`CHSWITCH` reads `$00` on Device B — no channel-switch character is
  set, so a verbose-mode channel switch by typing a character is not
  possible there at all (P66b, B.4, 2026-09-28).** Not tracked anywhere
  in `SerialManager`/`AppConfig` (pk232py never uploads it); confirmed
  by querying it directly, twice, in the same hardware session
  (`docs/P66b_HostEntry_Lag_And_IO_Channel_Spec.md`). `tools/hw_check.py
  ::chswitch_byte()` (P66a) already treats `$00` as "not set" and
  refuses to guess a character for it — this is the hardware finding
  that confirms `$00` is a real, expected value on this device, not
  just a defensive edge case. **Consequence:** the "last `$4x` frame"
  technique above (B.3) is the only verbose-side channel-selection
  method known to work on Device B — a `CHSWITCH`-character approach
  cannot be relied on in general.
- **`CONVERSE` on a channel with no connection sends every input line
  as an UNPROTO UI frame — confirmed for Device B, P66b, B.5
  (2026-09-28).** Sending `CONVERSE` on a free channel, then a bare
  `CR`, produced only an echo — no prompt, no error message — which
  looks harmless but is not: per the TRM, `CONVERSE` on an unconnected
  channel is exactly the UI/UNPROTO mode, and anything typed there
  goes out over the air along the configured `UNPROTO` path.
  **Rule:** any code (the app or `tools/hw_check.py`) that sends
  `CONVERSE` must know whether the target channel is actually
  connected — on an unconnected channel this is a real transmission
  and needs the same `confirm_tx()`-style gate as any other TX, not
  just the queries around it (`tools/hw_check.py`'s own D.2.1 needed
  this fix, P66b).
- **Every `$5x` link message carries its own channel number in the CTL
  nibble — three consumers now use it, not two (P47, 2026-09-25).**
  `HFPacketMode._handle_link_msg()` reads `frame.channel` and calls
  `on_link_message(ch, text)`. Two consumers were already channel-aware:
  `_make_channel_state_handler()` (chips/MHEARD) and the Unproto-gating
  logic inside `_make_link_handler()` (T102). A third consumer,
  `_on_mode_link_message()`'s RX-window display, used to ignore the
  channel entirely and always write into whichever screen/channel the
  operator happened to have open — reproduced 25.09.2026 (screenshot): a
  channel-1 "Retry count exceeded ... DISCONNECTED: OE3XTC" appeared on
  the UI chip (channel 0). Fixed: `_make_link_handler()` now routes a
  channel-bearing call through `MainWindow._route_packet_link_message()`
  → `screen.append_channel_data(channel, text)` (reusing the existing
  ALL/CH document-per-channel model and its compact `n│` tag, P50,
  rather than reimplementing it — see the next bullet for the tag's
  current format, changed from the original `[CHn]`);
  channel 15 (`$5F`, not channel-scoped — e.g. the generic data ack) and
  AMTOR/PACTOR's single-argument calls (channel is `None`, no channel
  concept at all) are unaffected. **Never attribute a link message by
  callsign** — "Retry count exceeded" carries none, and the same station
  can be connected on two different channels at once; the CTL-nibble
  channel number is the only reliable source. Optional mirror into the
  UI channel: `HFPacketConfig.show_link_messages_in_ui_channel` (default
  off) — see the "PC-side display settings" gotcha under Parameter
  dialogs.
- **A channel-offset report could not be reproduced in code — verified,
  not guessed, and the measurement path was strengthened either way
  (P50 Teil A, 2026-09-25).** Screenshot, 25.09.2026 19:07: chip 1 green
  with `OE3TEC` ("Ch 1 Partner: OE3TEC"), but every received line and
  the eventual `*** DISCONNECTED: OE3TEC-1 ***` tagged `[CH2]` (the old
  ALL-view tag format at the time). Audited every step of the channel
  path end to end: `HFPacketMode.connect_frame()` →
  `SerialManager.send_channel_command()` → `build_ch_cmd()` (`ctl = 0x40
  | channel`) on the way out; `_make_host_frame()` → `ctl_channel()`
  (`ctl & 0x0F`) on the way in; `ChannelBar._chips`/`_state`/`_partner`
  are plain `dict[int, ...]` keyed directly by channel number, no
  positional/0-based indexing anywhere. All of it symmetric — **no
  code-level offset found**. This does not rule out a genuine TNC-side
  behaviour (e.g. the PK-232 itself reassigning or reporting a different
  channel than requested) — that can only be settled by measuring a real
  device, which this investigation could not do. What WAS already true:
  the exact measurement the spec asked for — the sent CO frame's CTL
  byte, and the channel of every incoming `$3x`/`$5x` frame — was already
  fully available via existing DEBUG logging
  (`_ReaderThread.run()`'s `logger.debug("RX %r", frame)`, whose
  `HostFrame` repr includes `channel`; `HFPacketMode._handle_rx_data()`/
  `_handle_link_msg()`'s own `ch=%d`/`ch%d` lines). Added one more,
  purely for convenience: `SerialManager.send_channel_command()` now logs
  the requested channel right next to the actual CTL byte it puts on the
  wire, in one line, for CONNECT/DISCONNECT specifically — so a hardware
  capture does not need to cross-reference a separate hex dump to confirm
  `build_ch_cmd()` encoded the right channel. **Root cause of the
  25.09.2026 report is still open — needs a real hardware capture**, not
  a guess.
- **Channel 0 is the UI/unproto/monitor channel, not a QSO channel (P10,
  2026-09-20).** AEA Host Mode only has `$2x` for outgoing data with
  `x` = 0–9 — there is no `$2F`. So Unproto is not its own channel; it is the
  state of a channel with no connection, and the TNC sends whatever goes out
  on it along the configured UNPROTO path. Receive side already draws this
  line: `$3x` is connected-station data on channel x, `$3F` is monitored
  traffic with no channel of its own. Consequence: channel 0 is reserved as
  the UI channel (`UI_CHANNEL` in `packet_screen.py`), channels 1–9 stay QSO
  channels — `CHANNEL_COUNT` is still 10, there is no eleventh channel.
  `ChannelBar.set_channel_state(0, …)` is a no-op (channel 0 can never become
  calling/connected) and `channel_map()` never includes it; its chip shows
  `"UI"` instead of `"0"` with its own fixed fill colour, all in
  `_update_chip()` (one place, not scattered). `_on_packet_unproto()`
  (`main_window.py`) just calls `channel_bar.set_current(0)` — turning
  Unproto on/off no longer touches Connect/Disconnect directly; that is
  `_on_packet_channel_changed()`'s job now (`set_link_state(channel_bar.state(
  channel))`, which also turns Unproto back off if it was still on when
  moving to a QSO channel — the T39 mutual exclusion, rebased onto channel
  selection instead of a direct button lock; P42, 2026-09-24: since there
  are no more Connect/Disconnect buttons at all, `set_link_state()` now
  only ever touches Unproto's own enabled state — see the "connect in the
  chip" bullet below). This is also consistent with the rest of the app:
  every non-Packet operating mode already only ever uses channel 0 (TRM 4.3).
- **Connect happens IN the chip, not in a separate row (P42, 2026-09-24).**
  The old `Connect · Dest · … · Disconnect` row is gone — `btn_connect`,
  `btn_disconnect`, `cb_dest`, `btn_connect_dialog`, `dest_callsign()`,
  `set_dest_callsign()`, `add_dest_history()` no longer exist anywhere in
  the Packet code path. Reasoning: the channel is the place a connection is
  made, so a connect can never land on a channel other than the one being
  looked at — and it removes the P41 failure class (an input field living
  in its own row, one keyboard-redirect exception away from swallowing
  every keystroke) by construction, since there is no other row left to get
  that exception wrong on (see `ChannelChip`'s own docstring in
  `packet_screen.py`). Operation:

  | Action | Result |
  |---|---|
  | Click a different chip | switches the current channel (and closes any OTHER chip's open editor first — P57.1, see below) |
  | Click the already-current free chip, or double-click any free chip, or "Connect…" in its context menu | opens that chip's inline callsign editor |
  | Enter with a valid callsign in the editor | `ChannelBar.request_connect()` → `connect_requested(ch, callsign)` → `MainWindow._on_chip_connect_requested()` sends `CO` on that channel |
  | Enter with an invalid callsign | editor stays open, red border + tooltip, no signal |
  | Esc while editing | closes the editor, no signal |
  | "Connect via…" in a free chip's context menu | `PacketConnectDialog` (callsign + optional digipeater path, channel fixed to the chip that opened it) |
  | "Disconnect" in a busy chip's context menu, or Ctrl+D while that channel is current | `disconnect_requested(ch)` → `MainWindow._on_chip_disconnect_requested()` sends `DI` on that channel |
  | Double-click an unconnected MHEARD row | `ChannelBar.start_edit_first_free()` — opens the FIRST free chip's editor, prefilled with the heard callsign (not necessarily the currently selected chip) |
  | Enter in `le_unproto`/`combo_monitor`/`combo_hbaud` while no chip editor is open | opens the current chip's editor (`ChannelBar.start_edit_current()`) — none of those three fields had a `returnPressed` behaviour of their own to shadow |

  Channel 0 (UI channel) and any busy chip never open an editor at all —
  enforced once, in `ChannelChip.start_edit()`/`_show_menu()` — so
  `_on_chip_connect_requested()` needs no channel-0 guard of its own
  (defense-in-depth was deliberately NOT added there; there is no code path
  left that could reach it with channel 0). `PacketConnectDialog` no longer
  has an editable channel field (it used to be a `QSpinBox`) — the channel
  always comes from whichever chip's "Connect via..." entry opened it.
- **Chips are `NoFocus` (P41), so a click on a DIFFERENT chip never
  closes an open editor via `focusOut` — `ChannelBar` closes it
  explicitly instead (P57.1, 2026-09-26).** The P42.1 "losing focus
  cancels like Esc" rule (`ChannelChip.eventFilter()`'s own `FocusOut`
  branch) only ever fires when Qt actually delivers a focus-out event
  to the editor — and a click on a chip BUTTON never does that, since
  every `QPushButton` in this app is `NoFocus` by design (so the
  keyboard stays in `tx_input`, CLAUDE.md §5). Reproduced 26.09.2026
  (screenshot): channel 3's editor stayed open and focused while
  channel 4 carried the active frame, and keystrokes kept landing in
  channel 3's field. Fixed with `ChannelBar.close_open_editor()` —
  cancels whichever of its ten chips is editing, discarding exactly
  like Esc — called from every place a channel can change or the bar
  can reset, since `ChannelBar` is the one place that actually knows
  which chip is open:

  | Trigger | Where the close is wired in |
  |---|---|
  | Click on a different chip | `ChannelBar._select()` (also reached by `set_current()`/`step()` below) |
  | `set_current()` from outside (MHEARD double-click, Unproto, program) | same `_select()` — this is the ONE method every channel change already goes through |
  | Mode (re)activation, leaving Host Mode | `PacketBaseScreen.reset_channels()` → `ChannelBar.reset()` |
  | Click into `tx_input` (or `le_unproto`/`combo_monitor`/`combo_hbaud`) | `PacketBaseScreen.eventFilter()`'s existing `MouseButtonPress` handling — no new filter, no new `installEventFilter()` call; this method is already installed on all four widgets |

  **Rule: a `QLineEdit` embedded inside a `NoFocus` widget (or shown
  via a `QStackedLayout` alongside one) cannot rely on `focusOutEvent`
  to notice it has been "clicked away from" — whatever owns the
  aggregate state must close it explicitly on every path that changes
  what is selected/visible.** The click that triggers the close keeps
  its own normal effect (e.g. still switches channels) — closing is a
  side effect of the SAME call, never a separate "first click only
  closes" step. **A second finding from the same screenshot — the open
  editor's amber border looked missing — was investigated (static
  review AND pixel-level `QWidget.grab()` rendering, including
  reproducing the exact click-away sequence) and could not be
  reproduced: the border (`#e8b23a`, 2px, matching the selected chip's
  own border width) rendered correctly in every case tried.** No code
  change was made for that part; see `test_packet_screen.py::
  TestChipEditorBorder` for the pixel-level regression guard kept in
  its place.
- **Chip colour states, and the same semantics for MHEARD (P44,
  2026-09-25).** Four states, one meaning everywhere in the Packet screen
  (chip fill AND MHEARD's connected-station colour):

  | State | Colour | Label | Notes |
  |---|---|---|---|
  | `CH_FREE` | grey | channel number | -- |
  | `CH_CALLING` | pulsing amber | `<callsign> ...` (ellipsis) | pulse: one shared `QVariantAnimation` for the whole bar (not one per chip, so every calling chip pulses in sync), 1.2s cycle, `InOutSine`, low-high `#8a6a1e`/`#b08a2a` via a mid-cycle keyframe (not start/end alone -- that would sawtooth-snap at the loop point instead of oscillating); starts the instant any chip becomes calling, stops the instant none are; text colour stays fixed so the label reads steadily |
  | `CH_CONNECTED` | green | callsign | MHEARD's own connected-station colour uses this exact value (`_CHIP_FILL[CH_CONNECTED]`) -- legend says "green = connected", not "amber", which is what it said before this fix (contradicting the chip's own amber-means-calling) |
  | `CH_FAILED` | red, `_FAILED_FLASH_MS` (1.5s) | channel number | transient -- `ChannelBar` reverts it to `CH_FREE` on its own; a `set_channel_state(ch, CH_FREE, ...)` call while the channel was `CH_CALLING` becomes this instead of snapping straight to free (a calling-to-free transition is, by definition, a failed attempt: retry count exceeded, busy, or a DISCONNECTED that arrived before ever reaching CONNECTED -- `HFPacketMode._handle_link_msg()` already routes all three through `on_channel_state(ch, "free", "")`; "Retry count exceeded" only gained this in P44, it used to reach neither `on_link_message` nor `on_channel_state`'s free branch and left the chip calling forever); a channel that WAS `CH_CONNECTED` (a normal, successful hangup) skips this and goes straight to free -- there is nothing that failed there. Counts as free for interaction (its context menu, opening the inline editor) -- a chip that just failed is exactly where a retry is most likely, so it is never locked out for the flash's duration. |

  Still entirely driven through `set_channel_state()` (P18/P16's existing
  channel-state path) -- P44 added no new callback route, only new
  behaviour inside that one method. See the QTimer-parenting gotcha under
  UI/PyQt6 for a real bug this feature's own timer hit and how it was fixed.
- **The channel bar always shows ten chips, but `USERS` decides how many
  actually work (P11, 2026-09-20).** `ChannelBar` can display channels 0–9
  regardless of hardware capability — but the PK-232 itself only accepts as
  many simultaneous AX.25 connections as its `USERS` parameter allows
  (default **1**). Without raising `USERS`, chips 2–9 stay dead in real
  operation; that is expected TNC behaviour, not a UI bug. `USERS` lives in
  `HFPacketConfig.users` (shared by VHF Packet — there is no separate
  `VHFPacketConfig`), is set via the HF Packet Parameters dialog
  (`self._sb_users`, range 1–10) and uploaded in verbose mode as the
  `USERS` command (`comm/params_uploader.py`) — **not** the Host Mode
  mnemonic `UR`; changing `USERS` at runtime in Host Mode is out of scope.
  `ChannelBar.set_user_limit()` only ever adds a tooltip line to chips above
  the limit — deliberately no lock/grey-out/colour change, since it is
  unconfirmed whether `USERS` also blocks *outgoing* connects on higher
  channels (it is documented as limiting *accepted*, i.e. incoming, ones) —
  see Testplan T104/T105 for what is still open on real hardware.
- **Every channel has its own RX document; ALL/CH switches the document,
  it does not filter at append time (P50, 2026-09-25 — supersedes the
  v0.1 "append-time filter" design).** The old model kept everything in
  ONE `QTextEdit` and `append_channel_data()`/`append_monitor_data()`
  decided per line whether to write it at all — switching to a channel
  in CH view therefore only ever showed what arrived AFTER the switch,
  never its prior history. `PacketBaseScreen._rx_docs: dict[int,
  QTextDocument]` (one per channel, 0–9) plus `_rx_doc_all` (a merged,
  chronological log of everything) replace this: every line is written
  into BOTH its own channel's document and `_rx_doc_all` — costs memory,
  buys back the channel's full history on every switch.
  `_sync_rx_document()` just re-attaches `rx_display` to whichever
  document `_view_all`/`current_channel()` implies (called from
  `set_view_all()` and `ChannelBar.channel_changed` via
  `_on_rx_channel_switch()`), saving/restoring each document's own
  scroll position (`_rx_scroll`) so switching back and forth does not
  reset your reading position. `reset_channels()` clears every document.
  Each document is capped via `QTextDocument.setMaximumBlockCount()`
  (`HFPacketConfig.rx_max_lines_per_channel`, default 5000,
  PC-side/`UPLOAD_EXEMPT` like `show_link_messages_in_ui_channel`).
  **Display formatting changed alongside this:** a channel's own
  document gets NO channel prefix at all (the channel is already named
  by which chip/view is selected); `_rx_doc_all` gets a compact `n│`
  tag (channel digit + thin separator, `"UI│"` for the UI channel,
  matching the chip's own "UI" label) in a muted colour, replacing the
  old `[CHn]` bracket form. A timestamp (`[HH:MM:SS]`, also muted) is
  now OFF by default (`HFPacketConfig.show_timestamps`) — costs a third
  of the line width when always on. A system/link message keeps (or
  gains) its own eye-catching colour (`_SYSTEM_MSG_COLOR`, amber) via an
  explicit `color=` override to `append_channel_data()`, distinct from
  plain channel data (blue) and monitor traffic (grey) — never muted
  like the tag/timestamp.
  **The pre-existing `_packet_raw_frames` buffer + `_packet_rx_redraw()`
  (APRS raw↔decoded toggle, T59/T60) still exists, but now only rebuilds
  the UI channel's OWN document** (`PacketBaseScreen.
  clear_monitor_channel()`/`append_monitor_data_local_only()`) — never
  `_rx_doc_all`, which is a chronological log of everything that has
  already arrived from every channel; rebuilding it on an APRS toggle
  would either duplicate every historical monitor line (through the
  normal dual-write path) or drop every QSO-channel line recorded since
  (if cleared outright). This is a deliberate scoping decision, not an
  oversight — see `clear_monitor_channel()`'s own docstring.
- **RX/TX is a `QSplitter` now, not a fixed five-line TX height (P50
  Teil D, 2026-09-25).** The RX window used to be added with
  `stretch=1` directly into the screen's own `QVBoxLayout` and the TX
  row right after it at a hard `setFixedHeight()` — RX therefore never
  grew to fill extra window height (a big empty area below it in the
  25.09.2026 screenshot), and the operator had no way to make the TX
  area taller or shorter. `PacketBaseScreen._rxtx_splitter`
  (`QSplitter(Qt.Orientation.Vertical)`) now holds both — RX has
  `setStretchFactor(0, 1)` (takes any extra space on a window resize),
  TX has `setStretchFactor(1, 0)` (stays put unless the handle itself is
  dragged) and keeps its old five-line height only as the STARTING
  `setSizes()` value, not a hard constraint; both panes have a
  `setMinimumHeight()` so neither can be dragged away entirely. Saved/
  restored in `MainWindow._save_window_geometry()`/
  `_restore_window_geometry()` alongside the window geometry itself, one
  `QSettings` key per Packet screen (`hfPacketRxTxSplitterSizes`/
  `vhfPacketRxTxSplitterSizes` — `_PACKET_RXTX_SPLITTER_KEYS`) — the
  Hold TX/Clear TX/Clear RX button column stays a fixed-size sibling
  layout inside the TX pane (`addStretch()` keeps it top-anchored), it
  does not grow when the handle is dragged.
- **MHEARD gains connection partners from live link messages, not just
  a manual Refresh (P50 Teil E, 2026-09-25).** Previously the list only
  ever grew from an `MH` poll (`MainWindow._on_packet_mheard()`), which
  only runs on a button click — a station you just connected to would
  not appear until you remembered to press Refresh. Now
  `_make_channel_state_handler()`'s callback (already fed channel+state+
  partner by `HFPacketMode._handle_link_msg()` for every CONNECTED/
  CALLING("connect request")/FREE(DISCONNECTED, busy) transition) calls
  `MheardPanel.add_entry_if_new(partner, now)` whenever `partner` is
  non-empty — never for "Retry count exceeded" (`_handle_link_msg()`
  splits that into its own `elif`, passing `""`, precisely because it
  carries no callsign at all and `_extract_partner()`'s bare-first-token
  fallback would otherwise misread the message text itself as one).
  `add_entry_if_new()` is deliberately NOT `add_entry()` with a dedup
  check bolted on — it never updates an existing row either, so a
  station mentioned repeatedly (several DATA exchanges on one QSO) does
  not accumulate duplicate entries. Channel number and green colour
  still come from the existing `set_channel_map()` call, unchanged. A
  real CONNECTED, or a genuine DISCONNECTED of a link that was actually
  up (checked via the chip's OWN prior state, `screen.channel_bar.
  state(channel)`, read BEFORE `set_channel_state()` updates it — a
  CALLING→FREE failed-attempt transition is deliberately NOT this),
  additionally fires ONE `_on_packet_mheard()` poll so the list also
  catches up on any OTHER stations heard in the meantime — reusing the
  existing Refresh implementation outright, not a second one.
- **`_extract_partner()` used to split on the FIRST colon in the whole
  string — with CONSTAMP/DAGSTAMP both ON (the upload default), that
  colon is INSIDE the TNC's own embedded timestamp, not the callsign
  marker (P55.A, 2026-09-26).** A real message looks like `"*** 25-Sep-26
  21:04:36 DISCONNECTED: OE3TEC-1 ***"` once both are enabled — the
  `"21:04:36"` timestamp alone contributes two colons, both ahead of the
  one that actually marks the callsign after `DISCONNECTED`. Reproduced
  via a screenshot (26.09.2026): MHEARD's Callsign column showed a
  fragment of the embedded time instead of the real callsign. Fixed by
  `rsplit(":", 1)` (split on the LAST colon) instead of `split(":", 1)`
  — nothing legitimate ever follows a real callsign with a colon of its
  own, so the last one is always the right marker. The `" to "` branch
  (CONNECTED) was never affected by this, since it never reaches the
  colon-splitting code at all.
- **`MainWindow._parse_mheard_line()` never accounted for a leading
  DAYSTAMP date token either — same finding, same screenshot, a second
  independent source (P55.A, 2026-09-26).** With DAYSTAMP ON, a real
  `MH` poll response line is `"25-Sep-26 00:05:23 OE3TEC-1*"`, not just
  `"00:05:23 OE3TEC-1*"` — the old parser's own docstring admitted this
  ("too complex for v0.1") and read the date token itself as the
  callsign whenever DAYSTAMP happened to be on. Fixed by stripping a
  leading token that contains `'-'` with no `':'` (unambiguous against
  both a `HH:MM(:SS)` time token and a bare callsign, since AX.25
  callsigns never contain `-`) before the existing time/callsign split.
  Not yet confirmed against a raw hardware capture of an actual `MH`
  line — see the P55 Testplan entry.
- **The TX echo used to write directly into `rx_display`'s cursor,
  landing in only whichever ONE document (ALL or the current channel's
  own) happened to be attached at send time — not through
  `append_channel_data()` (P55.B, 2026-09-26).** P50 made every RX line
  write into BOTH a channel's own document and the merged ALL document,
  but `MainWindow._on_packet_tx_enter()`'s own TX-echo block was never
  migrated onto that path — it kept manipulating `screen.rx_display`'s
  `QTextCursor` directly, exactly as before P50, so the echo only ever
  reached whichever document was currently VISIBLE. Reproduced
  26.09.2026: `"> ch1 just testing"` showed up in ALL view but not in CH
  view of channel 1 itself. Fixed by routing the echo through
  `append_channel_data(channel, f"> {text}", color=...)`, the same path
  a received line or a link message already uses — the manual
  `"ch{channel}"` prefix text was also dropped as redundant, since the
  ALL view's own compact `"n│"` tag and the CH view's channel selection
  already say which channel a line belongs to.
- **A `QTextDocument` created with no `setDefaultFont()` uses Qt's own
  generic default, not whatever font `rx_display` is showing — switching
  ALL/CH visibly changed the font (P55.C, 2026-09-26).** P50's per-
  channel/ALL documents (`_rx_docs`/`_rx_doc_all`) were constructed with
  a bare `QTextDocument(self)`; `rx_display.setFont()` only ever applies
  to the ONE document attached at the moment it is called, never to a
  document created (or later swapped in via `setDocument()`) afterward.
  Fixed with a single module-level constant, `_RX_FONT`
  (`packet_screen.py`), applied via `setDefaultFont()` to every document
  at construction AND via `setFont()` to `rx_display` itself — one
  value, so the two can never drift apart again. Character formats
  inserted by `_rx_write_line()` only ever set `setForeground()`
  (colour), never a font of their own, so fixing the document's default
  font was sufficient — no per-line format change was needed.
- **Correction to the P55.C entry above — `_RX_FONT` fixed one font
  mismatch by introducing a second one (P56.A, 2026-09-26).** Font
  really does come from exactly ONE place now:
  `MainWindow._apply_appearance()`, the operator's own Appearance
  setting (theme/font family/size) — the same place that has always set
  `rx_display`'s font, and every OTHER screen's `rx_display`/`tx_input`.
  `_RX_FONT` pinned every Packet RX document to a hardcoded `"Courier
  New" 10pt`, independent of Appearance — the ALL document (being
  `rx_display`'s own original document) kept tracking Appearance
  correctly since `rx_display.setFont()` propagates to whichever
  document is CURRENTLY attached, while every per-channel document
  stayed on the constant forever. Reproduced 26.09.2026 (screenshot,
  maximized window): ALL view showed `"Cascadia Mono SemiBold 14pt"`
  correctly, CH view did not. `_RX_FONT` is deleted; a new
  `PacketBaseScreen.apply_rx_font(font)` pushes `setDefaultFont()` onto
  every RX document (all ten channels plus the merged ALL one, visible
  or not), called from `_apply_appearance()` right alongside the
  existing `rx_display.setFont(font)` — both at startup and on every
  later Appearance change, so a document created before a later change
  gets the new font too. `tx_input` was checked and already hangs off
  the same `_apply_appearance()` source (unconditional for every
  screen) — no fix needed there. **MHEARD's own fonts
  (`QFont("Segoe UI", ...)`/`QFont("Courier New", 9)` in
  `MheardPanel`/`_MheardRowWidget`) are hardcoded and NOT wired to
  Appearance at all** — named here because the spec explicitly asked
  to check, not because it was fixed; left alone deliberately (not
  asked for).
