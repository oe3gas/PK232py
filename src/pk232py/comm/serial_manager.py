# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Serial port manager for the AEA PK-232 / PK-232MBX.

Initialisation flow (3 phases):
  Phase 1 — init_tnc():
      Sends '*', detects TNC state (fresh boot / already active / Host Mode),
      sends AWLEN + PARITY + RESTART if needed.
      Emits verbose_mode_ready when TNC is at cmd: prompt.

  Phase 2 — ParamsUploader.upload():
      Sends all stored parameters as verbose-mode ASCII commands.
      Called externally after verbose_mode_ready.

  Phase 3 — enter_host_mode():
      Sends HOST 3 (XON + CANLINE + COMMAND + HOST Y).
      Emits host_mode_changed(True) when complete.

This separation allows running in verbose mode only (for diagnostics)
and gives the user control over when to switch to Host Mode.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Optional

try:
    import serial
    import serial.tools.list_ports
    PYSERIAL_AVAILABLE = True
except ImportError:
    PYSERIAL_AVAILABLE = False

from PyQt6.QtCore import QObject, pyqtSignal

from .constants import (
    SerialDefaults,
    FRAME_POLL,
    FRAME_RECOVERY,
    FRAME_HOST_OFF,
    CTL_TX_DATA_BASE,
    ctl_channel,
)
from .pk232_hostmode_sub import HostModeWorker as _HostModeWorker
from .frame import (
    HostFrame,
    FrameKind,
    FrameParser,
    build_command,
    build_ch_cmd,
    build_data,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Timing constants (seconds) — tuned against real PK-232MBX v7.1
# ---------------------------------------------------------------------------
_WAKEUP_TIMEOUT  = 3.0   # max wait for TNC response to '*'
_CMD_DELAY       = 0.15  # pause between verbose-mode commands
_RESTART_DELAY   = 3.0   # wait after RESTART for TNC banner + cmd:
_HOSTMODE_DELAY  = 0.8   # wait after HOST Y before GG poll
_GG_MAX_RETRIES  = 5     # max GG poll retries
_GG_RETRY_DELAY  = 0.5   # delay between retries
_POLL_TIMEOUT    = 3.0   # wait for GG poll ACK
# P43: each step of the active TNC-state detection chain in
# _init_tnc_thread() gets this short a timeout - the detection itself
# must not take longer than the failure mode it prevents (24.09.2026:
# 68 x 5s = ~6 minutes of silent, unexecuted parameter uploads).
_TNC_STATE_STEP_TIMEOUT = 1.5

# Byte sequences
_WAKEUP       = b"*"                               # no CR — autobaud trigger
_CMD_AWLEN    = b"AWLEN 8\r\n"
_CMD_PARITY   = b"PARITY 0\r\n"
_CMD_8BITCONV = b"8BITCONV ON\r\n"
_CMD_RESTART  = b"RESTART\r\n"
# PCPackRatt-verified. HOST is a bit field (TRM ch.12), not a plain on/off
# toggle: bit 0 = Host Mode on/off, bit 1 = local MailDrop login (moves the
# MailDrop data channel from $2x/$2F to $60/$70), bit 2 = extended Host
# Mode. "HOST 3" sets bits 0+1 — this app has always run with the
# MailDrop-login bit set, though nothing currently uses the $60/$70
# channel it enables (see CLAUDE.md, P24/P26).
_CMD_HOST_3   = b"HOST 3\r"
_CMD_HPOLL_Y  = bytes([0x01, 0x4F, ord('H'), ord('P'), ord('Y'), 0x17])
_HPOLL_ACK    = bytes([0x01, 0x4F, ord('H'), ord('P'), 0x00, 0x17])
# P54.3: the PK-232 uses SOFTWARE flow control (XON $11 / XOFF $13) - the
# boot banner's own leading bytes prove it sends XON there
# ('... 0d 0a 11 41 45 41 ...', hw capture). A TNC stopped by a stray
# $13 (e.g. a frame byte that leaked through during Host Mode) keeps
# echoing every character but stops sending anything it generates
# itself (a prompt, a banner) - indistinguishable from "not responding"
# by steps 1/2 alone. $11 releases it.
_XON_BYTE     = 0x11

# TNC response classifiers
_BANNER_MARKERS  = (b"AEA", b"Ver.", b"PK-232", b"Copyright")
_PROMPT_MARKER   = b"cmd:"
_SOH_BYTE        = 0x01
# P37: firmware release date and "using defaults" flag, both read straight
# off the boot banner (docs/PK232_firmware_matrix.md §1) - the release date
# format itself varies by firmware generation ('01.AUG.91' seen on Device B,
# hw_logs/20260924_181446_maildrop_session.log), so this is captured
# verbatim and never normalised into a canonical date.
_RELEASE_RE      = re.compile(rb"Release\s+(\S+)")
_DEFAULTS_MARKER = b"is using default values"


def _parse_release(banner: bytes) -> Optional[str]:
    """Firmware release date exactly as printed in the boot banner, or
    None if no banner was captured at all (P37 - nothing here invents a
    value; see SerialManager.tnc_release)."""
    if not banner:
        return None
    m = _RELEASE_RE.search(banner)
    return m.group(1).decode('ascii', errors='replace') if m else None


def _parse_defaults_flag(banner: bytes) -> Optional[bool]:
    """True if the boot banner said 'is using default values' (bbRAM
    reset to factory config, CLAUDE.md - no RAM buffer battery), False if
    a banner was captured without that phrase, None if no banner was
    captured at all (P37 - see SerialManager.tnc_defaults)."""
    if not banner:
        return None
    return _DEFAULTS_MARKER in banner


def _classify_maildrop_response(text: str) -> Optional[bool]:
    """Classify a verbose-mode 'MAILDROP' (no argument) query response
    (P37, docs/P37_T119_Provenance_Capability_Spec.md Teil D).

    Unlike PACTOR, MailDrop capability has no boot-banner marker - the
    only way to know is to ask, in verbose mode, before the parameter
    upload. This never sends MDCHECK: MDCHECK logs into the mailbox and
    halts packet operation, which a capability probe must never do.

    Returns:
        True  - a line named MAILDROP answered (its ON/OFF state does
                not matter, only that the command exists).
        False - an error line ('?What?', '?bad', ...) - the command
                does not exist on this firmware (e.g. the 1988 BASE
                generation, docs/DEVICES.md Device C).
        None  - no clear answer (empty/garbled/no matching line) - a
                detection failure, which callers must treat as "unknown,
                assume capable", never as "no MailDrop" (an existing
                feature must not be locked out by a flaky probe).
    """
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("?"):
            return False
        token = line.split()[0]
        # The TNC answers in its own mixed-case abbreviated form
        # ('MAildrop'), never in the exact uppercase we sent - skip our
        # own echoed command line (same "echo vs. real answer" rule as
        # tools/hw_check.py::parse_query_value(), P21.1).
        if token.upper() == "MAILDROP" and token != "MAILDROP":
            return True
    return None


def _parse_verbose_query_value(name: str, text: str) -> Optional[str]:
    """Extract the value from a verbose-mode query response for *name*
    (P40.3). Format confirmed against real hardware (P15):
    '<echo>\\r\\n<Name mixed-case>   <value>[ (<explanation>)]\\r\\ncmd:'
    - the TNC answers in its own mixed-case abbreviated form ('MYcall',
    'PAclen', ...), never in the exact uppercase *name* we sent, so the
    echoed command line is skipped the same way
    _classify_maildrop_response() already does for MAILDROP. Returns None
    on an error line ('?What?', ...) or when no matching line is found at
    all (e.g. no response, or a garbled one).
    """
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("?"):
            return None
        tokens = line.split()
        token = tokens[0]
        if token.upper() == name.upper() and token != name.upper():
            return tokens[1] if len(tokens) > 1 else None
    return None


def _wakeup_log_message(resp: bytes) -> tuple[int, str]:
    """P35.4: what to log after the wakeup read, and at what level.

    Pulled out as its own pure function so the truthfulness of the log
    line can be unit-tested without a real serial port. Used to log
    "TNC at cmd: prompt" unconditionally — even when *resp* never
    actually contained 'cmd:' at all (23.09.2026,
    hw_logs/20260923_204041_maildrop_session.log: wakeup got back
    '*\\<CR><LF>', no 'cmd:', and the log still claimed the prompt was
    seen). This only changes what gets logged, not what happens next —
    the existing fallthrough logic (setting _verbose_ready etc.) is
    unchanged; the wakeup's own CR-fallback behaviour is P29's separate
    item."""
    if _PROMPT_MARKER in resp:
        return logging.INFO, "TNC at cmd: prompt"
    return (
        logging.WARNING,
        f"wakeup answered without prompt ({len(resp)} bytes) -- "
        f"continuing: {resp.hex(' ')}",
    )


def _port_config_line(port, port_name: str, baudrate: int) -> str:
    """One line naming every port parameter that affects behaviour
    (P54.1) - logged right after open(), again after this app's own
    post-open adjustments (P54.2's dtr/rts/buffer resets - line states
    can change during and after opening), and once more right before
    close(). Without this, a hardware run has nothing to compare
    against besides "Port COM6 opened at 9600 baud" - not enough to
    tell a genuine TNC problem apart from a difference in how THIS app
    opens the port versus a terminal program that works (26.09.2026:
    PuTTY got a prompt on the same port/baud with one Enter, the app did
    not - the difference had to be in the port configuration, not the
    TNC, and there was nothing in the log to actually show what that
    configuration was).

    getattr() throughout: some duck-typed test doubles do not define
    every one of these attributes, and a missing value should show as
    '?' in the log, never raise."""
    bytesize = getattr(port, 'bytesize', '?')
    parity   = getattr(port, 'parity', '?')
    stopbits = getattr(port, 'stopbits', '?')
    return (
        f"port {port_name} @ {baudrate} Bd {bytesize}{parity}{stopbits}: "
        f"xonxoff={getattr(port, 'xonxoff', '?')}, "
        f"rtscts={getattr(port, 'rtscts', '?')}, "
        f"dsrdtr={getattr(port, 'dsrdtr', '?')}, "
        f"dtr={getattr(port, 'dtr', '?')}, "
        f"rts={getattr(port, 'rts', '?')}, "
        f"timeout={getattr(port, 'timeout', '?')}, "
        f"write_timeout={getattr(port, 'write_timeout', '?')}"
    )


def _read_until_prompt(
    read_more,
    marker,
    timeout: float,
    idle_after_marker: float = 0.12,
) -> tuple[bytes, bool]:
    """Accumulate bytes from *read_more(max_wait)* until *marker* appears
    AND a further *idle_after_marker* seconds pass with nothing new — not
    until the first pause, and not the instant the marker is seen (P52.1).

    *marker* is bytes, a tuple of byte-string alternatives, or a
    predicate ``callable(bytes) -> bool`` for a match rule plainer
    substring containment cannot express (write_verbose_wait()'s own
    "cmd: at buffer start, or preceded by a newline" rule, so an echoed
    command that merely CONTAINS "cmd:" mid-word is not mistaken for the
    real prompt).

    *read_more(max_wait)* is called repeatedly; each call waits AT MOST
    max_wait seconds for new bytes and returns whatever arrived (b"" if
    none did within that window) — callers own their own efficient wait
    (a threading.Event, or a plain sleep); this function only owns the
    marker/idle/timeout state machine, so ONE implementation serves both
    a direct synchronous port read (the P43 detection chain) and an
    Event-driven buffer read (write_verbose_wait()) without either
    reimplementing the other's timing logic.

    Returns (all bytes accumulated so far, whether the marker was
    actually seen) — "found" stays True even if *timeout* then runs out
    during the idle-confirmation wait, since the marker DID appear; only
    the caller's own timeout budget decides how long that confirmation
    gets before giving up on it.

    P52.1 — the bug this replaces: the P43 detection chain's own
    per-step read used to OVERWRITE its deadline (``deadline = now +
    0.15``) on every iteration that received data without yet matching
    the full marker. That can only ever SHRINK the remaining budget, not
    extend it, so a response arriving in more than one chunk (`cmd:`
    split from its own banner — normal at 9600 Bd) could be cut off
    before the marker ever completed. Confirmed by a real console
    capture, 25.09.2026, 23:30:43: step 1 returned after 184 ms with
    just `2a 5c 0d 0a` (4 bytes), while a working run at the same step
    saw `2a 5c 0d 0a 63 6d 64 3a` (8 bytes, ending in "cmd:") — the
    trailing `cmd:` was simply still in flight when the shrunk deadline
    expired. The full *timeout* is now always honoured; only a short,
    fixed idle window runs AFTER the marker is confirmed, exactly
    mirroring write_verbose_wait()'s own already-correct
    prompt-then-idle design (used successfully by tools/hw_check.py's
    Session.verbose_bytes() today) — extracted here so the detection
    chain shares it instead of a second, independently-written (and
    buggy) version.
    """
    import time as _t

    def _matches(data: bytes) -> bool:
        if callable(marker):
            return marker(data)
        if isinstance(marker, (list, tuple)):
            return any(m in data for m in marker)
        return marker in data

    buf = bytearray()
    deadline = _t.monotonic() + timeout
    found = False
    idle_since = None
    while True:
        remaining = deadline - _t.monotonic()
        if remaining <= 0:
            break
        chunk = read_more(min(0.05, remaining))
        if chunk:
            buf.extend(chunk)
            idle_since = None
            if not found and _matches(bytes(buf)):
                found = True
                idle_since = _t.monotonic()
        else:
            if found:
                if idle_since is None:
                    idle_since = _t.monotonic()
                elif _t.monotonic() - idle_since >= idle_after_marker:
                    return bytes(buf), True
    return bytes(buf), found


# ---------------------------------------------------------------------------
# Background reader thread
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Host Mode frame extraction — proven in pk232_hostmode.py
# Handles DLE escaping per AEA TRM Section 4.4
# ---------------------------------------------------------------------------
_SOH_BYTE = 0x01
_ETB_BYTE = 0x17
_DLE_BYTE = 0x10
_CTL_BYTE = 0x4F

def _extract_frames(buf: bytearray):
    """Extract complete Host Mode frames from a bytearray.

    Returns (list_of_HostFrame_tuples, remaining_buf).
    Each tuple is (ctl: int, payload: bytes).
    Handles DLE-escaped bytes inside payload.
    """
    frames    = []
    remaining = buf
    while True:
        soh_pos = next((i for i, b in enumerate(remaining) if b == _SOH_BYTE), -1)
        if soh_pos < 0:
            remaining = bytearray()
            break
        etb_pos = -1
        i = soh_pos + 2          # skip SOH + CTL
        while i < len(remaining):
            if remaining[i] == _DLE_BYTE:
                i += 2
                continue
            if remaining[i] == _ETB_BYTE:
                etb_pos = i
                break
            i += 1
        if etb_pos < 0:
            remaining = remaining[soh_pos:]
            break
        raw       = bytes(remaining[soh_pos:etb_pos + 1])
        remaining = remaining[etb_pos + 1:]
        ctl       = raw[1] if len(raw) > 1 else 0
        payload   = bytearray()
        j = 2
        while j < len(raw) - 1:
            if raw[j] == _DLE_BYTE and j + 1 < len(raw) - 1:
                payload.append(raw[j + 1])
                j += 2
            else:
                payload.append(raw[j])
                j += 1
        frames.append((ctl, bytes(payload)))
    return frames, remaining


def _make_host_frame(ctl: int, payload: bytes):
    """Map (ctl, payload) to a HostFrame object."""
    from .frame import HostFrame, FrameKind
    if ctl == 0x4F:
        kind = FrameKind.CMD_RESP
    elif ctl == 0x3F:
        kind = FrameKind.RX_MONITOR
    elif 0x30 <= ctl <= 0x39:
        kind = FrameKind.RX_DATA
    elif ctl == 0x2F:
        kind = FrameKind.ECHO
    elif ctl == 0x5F:
        kind = FrameKind.STATUS_ERR
    elif 0x50 <= ctl <= 0x5E:
        kind = FrameKind.LINK_MSG
    else:
        kind = FrameKind.CMD_RESP
    ch = ctl_channel(ctl)
    return HostFrame(kind=kind, ctl=ctl, channel=ch, data=payload)



class _ReaderThread(threading.Thread):
    def __init__(self, port, frame_callback, raw_callback=None,
                 host_mode_flag=None) -> None:
        super().__init__(daemon=True, name="PK232-Reader")
        self._port           = port
        self._callback       = frame_callback
        self._raw_callback   = raw_callback
        self._host_mode_flag = host_mode_flag or (lambda: False)
        self._stop_event     = threading.Event()
        self._parser         = FrameParser(self._on_frame)

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        logger.debug("ReaderThread started")
        _buf = bytearray()
        while not self._stop_event.is_set():
            try:
                raw = self._port.read(64)
                if raw:
                    if self._raw_callback:
                        self._raw_callback(raw)
                    if self._host_mode_flag():
                        # Use _extract_frames — proven DLE-aware parser
                        _buf.extend(raw)
                        frames, _buf = _extract_frames(_buf)
                        for ctl, payload in frames:
                            try:
                                frame = _make_host_frame(ctl, payload)
                                logger.debug("RX %r", frame)
                                self._callback(frame)
                            except Exception as exc:
                                logger.error("Frame dispatch: %s", exc)
                    else:
                        # Verbose mode: use legacy parser
                        self._parser.feed(raw)
            except Exception as exc:
                if not self._stop_event.is_set():
                    logger.error("Serial read error: %s", exc)
                break
        logger.debug("ReaderThread stopped")

    def _on_frame(self, frame: HostFrame) -> None:
        try:
            self._callback(frame)
        except Exception as exc:
            logger.error("Frame callback raised: %s", exc)

    def reset_parser(self) -> None:
        self._parser.reset()


# ---------------------------------------------------------------------------
# SerialManager
# ---------------------------------------------------------------------------

class SerialManager(QObject):
    """Manages the serial connection to the PK-232 / PK-232MBX.

    Qt Signals
    ----------
    frame_received(HostFrame)
        Every complete Host Mode frame from the TNC.

    connection_changed(bool)
        True = port opened, False = port closed.

    verbose_mode_ready()
        TNC is in verbose COMMAND mode — ready for parameter upload.

    host_mode_changed(bool)
        True = Host Mode active, False = Host Mode left.

    params_upload_required()
        TNC rebooted (RESTART) — parameters must be re-uploaded.

    status_message(str)
        Human-readable status for the status bar.

    init_failed() (P45.2)
        The P43/P44 detection chain in _init_tnc_thread() could not
        confirm any TNC state (its step 4). connection_changed(True) may
        already have fired when the port opened — this tells the UI that
        turned out not to mean anything and it must not keep looking
        connected. The port itself is deliberately left open (Recovery
        needs it) — see MainWindow._on_init_failed().

    recovery_finished(bool, str) (P45.1)
        Emitted when recovery() completes: (success, human-readable
        message). success mirrors verbose_confirmed at that point.
    """

    frame_received         = pyqtSignal(object)  # HostFrame
    raw_data_received      = pyqtSignal(bytes)   # verbose mode raw bytes
    connection_changed     = pyqtSignal(bool)
    verbose_mode_ready     = pyqtSignal()
    host_mode_changed      = pyqtSignal(bool)
    params_upload_required = pyqtSignal()
    status_message         = pyqtSignal(str)
    init_failed             = pyqtSignal()          # P45.2
    recovery_finished       = pyqtSignal(bool, str)  # P45.1

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._serial:          Optional["serial.Serial"] = None
        self._reader:          Optional[_ReaderThread]   = None
        self._in_host_mode     = False
        self._verbose_ready    = False
        # P43: True only once the TNC-state detection chain in
        # _init_tnc_thread() has ACTIVELY confirmed a verbose prompt this
        # session - is_host_mode/is_verbose_mode are the software's own
        # belief and can be wrong on a fresh instance (e.g. the app quit
        # while the physical TNC stayed in Host Mode); this flag is never
        # set without positive evidence. Reset at the start of every
        # _init_tnc_thread() run, cleared again on successful Host Mode
        # entry (enter_host_mode()).
        self._verbose_confirmed = False
        # P44.B2: raw bytes captured by whichever detection-chain step
        # actually confirmed verbose mode this session - the prompt the
        # chain consumed to confirm it never otherwise reached the
        # verbose terminal display at all. See _finish_verbose_init().
        self._last_verbose_init_resp: bytes = b""
        self._poll_active      = False
        self._poll_thread      = None
        self._worker           = None  # _HostModeWorker in Host Mode
        self._write_lock       = threading.Lock()
        # Port factory (generic seam). None → real serial.Serial. A dev tool may
        # inject a duck-typed stand-in via set_port_factory(); SerialManager
        # itself knows nothing about any mock.
        self._port_factory     = None
        # TNC boot banner — captured during init for capability detection
        self._tnc_banner: bytes = b""
        # MailDrop capability — unlike has_pactor, not in the banner, so
        # this stays None until detect_maildrop() actively queries it
        # (P37). None means "not yet detected", never "no MailDrop".
        self._has_maildrop: Optional[bool] = None
        # Shared buffer: ReaderThread writes here, write_verbose_wait()
        # (via _read_until_prompt(), P52.1) reads here
        self._rx_buf           = bytearray()
        self._rx_buf_lock      = threading.Lock()
        self._rx_buf_event     = threading.Event()
        # P53.B: the TNC's COMMAND character (default $03, Ctrl-C) - the
        # one byte that pulls a Converse-mode TNC back to its cmd: prompt
        # (TRM: every operating mode has a Converse state that echoes
        # every character and shows no prompt at all). This is a PC-side
        # mirror of AppConfig.misc.command, kept in sync by MainWindow
        # (constructor, Misc Parameters dialog, Load Settings) - it is
        # the only value ParamsUploader actually uploads as the real
        # COMMAND parameter, so this is a best-effort "what we believe
        # the TNC currently has", not a guarantee (the TNC may still be
        # at its own factory default if nothing has been uploaded to it
        # yet this session). Defaults to $03 so a duck-typed test double
        # or a SerialManager built before any config exists still gets
        # the documented factory value.
        self.command_char: int = 0x03

    # ------------------------------------------------------------------
    # TNC capability detection
    # ------------------------------------------------------------------

    @property
    def has_pactor(self) -> bool:
        """True if the TNC boot banner contains 'PACTOR'.

        The PK-232MBX comes in two variants — with and without the
        PACTOR hardware/firmware option.  The boot banner reliably
        identifies which variant is connected.

        Returns True (permissive default) when no banner was captured,
        e.g. when the TNC was already in Host Mode at connect time.
        """
        if not self._tnc_banner:
            return True   # no banner captured — assume PACTOR capable
        return b"PACTOR" in self._tnc_banner

    @property
    def tnc_banner(self) -> str:
        """TNC boot banner as a decoded string (for logging/display)."""
        return self._tnc_banner.decode('ascii', errors='replace').strip()

    @property
    def tnc_release(self) -> Optional[str]:
        """Firmware release date exactly as printed in the boot banner
        (e.g. '01.AUG.91'), or None if no banner was captured, e.g. when
        the TNC was already at the cmd: prompt at connect time (P37) -
        nothing here invents a value or normalises the date format."""
        return _parse_release(self._tnc_banner)

    @property
    def tnc_defaults(self) -> Optional[bool]:
        """True if the boot banner said 'is using default values', False
        if a banner was captured without that phrase, None if no banner
        was captured at all (P37)."""
        return _parse_defaults_flag(self._tnc_banner)

    @property
    def has_maildrop(self) -> Optional[bool]:
        """MailDrop capability, as last determined by detect_maildrop()
        (P37). None until detect_maildrop() has actually been called, or
        if its query gave no clear answer - callers must treat None as
        "unknown, assume capable", never as "no MailDrop"."""
        return self._has_maildrop

    def detect_maildrop(self, timeout: float = 3.0) -> Optional[bool]:
        """Actively query MAILDROP (no argument) in verbose mode (P37) and
        cache the result in has_maildrop. Must be called while already in
        verbose mode (e.g. from ParamsUploader.upload(), before Host Mode
        entry) - built like has_pactor, but via a query instead of a
        passive banner read, since MailDrop capability has no banner
        marker. Never sends MDCHECK - see _classify_maildrop_response().

        P53.A: reads the response via _write_verbose_wait_text() directly
        instead of a transient raw_data_received.connect()/disconnect()
        pair - see that method's own docstring for the race this used to
        lose against (the exact same pattern query_verbose_value() had).
        """
        if not self.is_connected:
            return self._has_maildrop
        _found, raw = self._write_verbose_wait_text(b"MAILDROP\r\n", timeout=timeout)
        text = raw.decode("ascii", errors="replace")
        self._has_maildrop = _classify_maildrop_response(text)
        return self._has_maildrop

    def query_verbose_value(self, name: str, timeout: float = 3.0) -> Optional[str]:
        """Query one parameter's current value in verbose mode (P40.3 -
        used by ParamsUploader to spot-check that an upload actually
        reached the TNC, since write_verbose_wait() alone only confirms a
        cmd: prompt came back, not that the TNC accepted or even parsed
        the command). Must be called while already in verbose mode - same
        caller discipline as detect_maildrop(), which this mirrors.

        P53.A: reads the response via _write_verbose_wait_text() directly
        instead of a transient raw_data_received.connect()/disconnect()
        pair - the connect/disconnect version reliably lost a real race
        against Qt's queued cross-thread delivery (26.09.2026: the
        verbose terminal showed the TNC's correct answer to 'MYCALL'
        while this method reported "no answer" for the very same query -
        see _write_verbose_wait_text()'s own docstring for the confirmed
        mechanism). MainWindow's own terminal display is unaffected - it
        is a PERSISTENT raw_data_received connection, never torn down
        around a single command, so it was never exposed to this race.

        Returns:
            The value string as answered by the TNC, or None if there was
            no clear answer (error line, no response, or not connected).
        """
        if not self.is_connected:
            return None
        _found, raw = self._write_verbose_wait_text(
            f"{name}\r\n".encode("ascii"), timeout=timeout
        )
        text = raw.decode("ascii", errors="replace")
        return _parse_verbose_query_value(name, text)

    # ------------------------------------------------------------------
    # Port factory seam (generic; default = real serial.Serial)
    # ------------------------------------------------------------------

    def set_port_factory(self, factory) -> None:
        """Inject the callable used to create the port object.

        The factory is called with the same keyword arguments as
        ``serial.Serial`` (port, baudrate, bytesize, parity, …) and must return
        an object that duck-types the serial.Serial methods this manager uses.
        Default (None) uses the real ``serial.Serial``. This is the single,
        generic seam a dev-only mock plugs into; production never references it.
        """
        self._port_factory = factory

    # ------------------------------------------------------------------
    # Port management
    # ------------------------------------------------------------------

    def connect_port(self, port_name: str, baudrate: int = SerialDefaults.BAUDRATE) -> bool:
        """Open the serial port.

        xonxoff=False: XON ($11) must pass through unfiltered for HOST 3.
        rtscts=False:  PK-232 uses XON/XOFF flow control, not hardware handshaking.

        P54.2: dtr/rts are now explicitly asserted HIGH (True), not left
        clear (False, the pre-P54 setting) - the known-working
        configuration a PuTTY session used on the same port/baud
        (26.09.2026: PuTTY got a prompt with one Enter; the app, with
        dtr/rts both False, did not, on the identical physical TNC).
        This is this app's OWN port configuration, asserted the same way
        every time - it does not by itself prove anything about the
        TNC's state (see P54.3's XON stage for that).
        """
        if not PYSERIAL_AVAILABLE:
            self.status_message.emit("Error: pyserial not installed")
            return False
        if self.is_connected:
            logger.warning("Port already open")
            return False
        try:
            factory = self._port_factory or serial.Serial
            self._serial = factory(
                port     = port_name,
                baudrate = baudrate,
                bytesize = serial.EIGHTBITS,
                parity   = serial.PARITY_NONE,
                stopbits = serial.STOPBITS_ONE,
                timeout  = SerialDefaults.TIMEOUT,
                xonxoff  = False,
                rtscts   = False,
                dsrdtr   = False,
            )
            # P54.1: state right after open(), before this app's own
            # further adjustments below.
            logger.info(
                "Port config on open: %s",
                _port_config_line(self._serial, port_name, baudrate),
            )
            self._serial.dtr = True
            self._serial.rts = True
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
            # P54.1: state after this app's own adjustments - the line
            # states above can change during/after opening, so this is
            # the configuration the connection actually runs with.
            logger.info(
                "Port config after reset: %s",
                _port_config_line(self._serial, port_name, baudrate),
            )
            logger.info("Port %s opened at %d baud", port_name, baudrate)
            self.status_message.emit(f"Connected: {port_name} @ {baudrate} Bd")
            self._reader = _ReaderThread(
                self._serial,
                self._on_frame_received,
                raw_callback=self._on_raw_data,
                host_mode_flag=lambda: self._in_host_mode,
            )
            self._reader.start()
            self.connection_changed.emit(True)
            return True
        except Exception as exc:
            logger.error("Cannot open %s: %s", port_name, exc)
            self.status_message.emit(f"Connection error: {exc}")
            self._serial = None
            return False

    def disconnect_port(self) -> None:
        # P43.3: this is the intended, and already-correct, "what state
        # does the TNC end up in on exit" answer — confirmed unchanged
        # since commit ff17aa0. MainWindow.closeEvent() calls
        # disconnect_port() (via a confirmation dialog) whenever the app
        # is connected, so a CLEAN shutdown always sends HOST OFF first,
        # leaving the physical TNC in verbose mode, not Host Mode. The
        # 24.09.2026 reproduction ("TNC im Host Mode nach dem Beenden")
        # is best explained by an exit that never reached this method at
        # all (a force-kill, a crash, or the process ending before the
        # close/confirm flow completed) — no code path can run cleanup
        # after that. This is deliberately not "fixed" by adding a second
        # exit mechanism: the P43.1 detection chain in _init_tnc_thread()
        # already covers the resulting state on the NEXT connect,
        # regardless of why the TNC ended up there.
        # Step 1: leave host mode cleanly (sends HOST OFF, stops ReaderThread)
        if self._in_host_mode:
            try:
                if self._reader:
                    self._reader.stop()
                    self._reader.join(timeout=1.0)
                    self._reader = None
                if self._serial and self._serial.is_open:
                    self._serial.write(FRAME_HOST_OFF)
                    self._serial.flush()
                    time.sleep(0.2)
                self._in_host_mode = False
            except Exception as exc:
                logger.warning("exit host mode during disconnect: %s", exc)

        # Step 2: stop HostModeWorker if running
        if self._worker:
            self._worker.stop()
            self._worker.join(timeout=1.0)
            self._worker = None
        self._poll_active = False
        if self._poll_thread:
            self._poll_thread.join(timeout=1.0)
            self._poll_thread = None

        # Step 3: stop ReaderThread if still running
        if self._reader:
            self._reader.stop()
            self._reader.join(timeout=1.0)
            self._reader = None

        # Step 3: close port
        if self._serial:
            try:
                if self._serial.is_open:
                    # P54.1: the end-of-life configuration - completes
                    # the "on open" / "after reset" pair connect_port()
                    # already logs, so a hardware run has the port's
                    # configuration at every stage, not just at open.
                    logger.info(
                        "Port config at close: %s",
                        _port_config_line(
                            self._serial,
                            getattr(self._serial, 'port', '?'),
                            getattr(self._serial, 'baudrate', '?'),
                        ),
                    )
                    self._serial.close()
                    logger.info("Serial port closed")
            except Exception as exc:
                logger.warning("Port close error: %s", exc)
            finally:
                self._serial = None

        self._in_host_mode  = False
        self._verbose_ready = False
        with self._rx_buf_lock:
            self._rx_buf.clear()
        self._rx_buf_event.clear()
        self.connection_changed.emit(False)
        self.status_message.emit("Disconnected")

    @property
    def is_connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    @property
    def is_host_mode(self) -> bool:
        return self._in_host_mode

    @property
    def is_verbose_mode(self) -> bool:
        """True if connected and in verbose mode (not Host Mode)."""
        return self.is_connected and self._verbose_ready and not self._in_host_mode

    @property
    def verbose_confirmed(self) -> bool:
        """True once the P43 detection chain has ACTIVELY confirmed a
        verbose prompt this session - see the attribute's own docstring
        in __init__ for why this differs from is_verbose_mode (which is
        the software's unverified belief, not evidence)."""
        return self._verbose_confirmed

    @property
    def last_verbose_init_response(self) -> bytes:
        """Raw bytes captured by whichever detection-chain step actually
        confirmed verbose mode this session (P44.B2). MainWindow mirrors
        this into the verbose terminal right after init - the prompt (and
        banner, if the TNC had just booted) it represents was already
        consumed inside the chain and never otherwise reaches the UI."""
        return self._last_verbose_init_resp

    # ------------------------------------------------------------------
    # Phase 1 — TNC initialisation → verbose mode
    # ------------------------------------------------------------------

    def init_tnc(self) -> bool:
        """Phase 1: Initialise TNC into verbose COMMAND mode.

        Runs in a background thread. When complete, emits verbose_mode_ready.
        If TNC rebooted (RESTART sent), also emits params_upload_required.
        """
        if not self.is_connected:
            logger.error("init_tnc: not connected")
            return False
        if self._in_host_mode:
            logger.warning("Already in Host Mode")
            return True

        self._verbose_ready = False
        self.status_message.emit("Initialising TNC...")
        t = threading.Thread(target=self._init_tnc_thread, daemon=True, name="PK232-Init")
        t.start()
        return True

    def _take_over_read_path(self) -> None:
        """Stop the ReaderThread and clear the input buffer so a direct,
        synchronous read is guaranteed to see the TNC's next bytes itself
        (P46.A.1) — the one place both _init_tnc_thread() and
        _recovery_thread() hand the read path from the background reader
        to a direct-read detection sequence, instead of two independently
        written copies of the same handover (this project has drifted
        that way more than once — see CLAUDE.md).

        Root cause this fixes: _recovery_thread() used to write its own
        FRAME_RECOVERY/FRAME_HOST_OFF bytes via _write_raw() while
        ReaderThread was still running, so the TNC's response was consumed
        there — dumped into the verbose terminal as raw framed bytes (the
        25.09.2026 screenshot: "␁␁OGG␁␁␁OHONO[SYS] Recovery did not reach
        the TNC.") — instead of being visible to the detection chain's own
        direct reads, which is why Recovery reported failure even when the
        TNC had actually answered. Calling this before ANY write —
        recovery's own preamble included, not just the chain's steps —
        closes that gap. Idempotent: calling it again with no reader
        running (the chain's own call, right after _recovery_thread()'s)
        just re-clears the buffer, which is exactly what is wanted —
        acks/echoes of a preamble already served their purpose and must
        not be mistaken for the chain's own step 1 response.
        """
        if self._reader:
            self._reader.stop()
            self._reader.join(timeout=2.0)
            self._reader = None
        self._serial.reset_input_buffer()
        self._verbose_confirmed = False

    def _init_tnc_thread(self) -> None:
        """Background init — active TNC-state detection (P43).

        is_host_mode is the SOFTWARE's own belief, not the device's real
        state — a fresh SerialManager instance always starts with
        _in_host_mode=False, regardless of what the physical TNC is
        actually doing (e.g. left in Host Mode when the app last quit,
        operator reproduced 24.09.2026: a fresh connect's parameter
        upload ran into 68 x 5s timeouts with nothing reaching the TNC,
        because it was genuinely in Host Mode and the old passive check —
        "does a stray SOH byte happen to show up in the wakeup response"—
        never actually saw one). This method instead ACTIVELY confirms
        which state the TNC is in, via a chain of short steps
        (_TNC_STATE_STEP_TIMEOUT each) so detection itself can never take
        longer than the failure mode it exists to prevent:

          1. '*'  -> banner or 'cmd:'  -> verbose, freshly booted -> done.
          2. CR   -> 'cmd:'            -> verbose, already awake -> done.
             (tried before step 3: the already-awake, verbose TNC is the
             more common case and is settled by a single CR)
          2b. (P53.B) COMMAND char (self.command_char, default $03/
             Ctrl-C) + CR -> 'cmd:' -> verbose, was in Converse mode.
             Real console capture, 26.09.2026, 13:13-13:16: steps 1 and 2
             both got only an ECHO of what was sent, no 'cmd:' either
             time - the TNC was in the Converse state of whichever
             operating mode (Baudot RTTY, that run) was active before
             this disconnect, since HOST OFF returns the TNC to its
             LAST active mode, not to the command prompt (TRM); Converse
             echoes every character and shows no prompt at all, which
             steps 1/2 alone cannot tell apart from "TNC not responding"
             - only the COMMAND character actually escapes it. Matches
             what tools/hw_check.py's Session.normalize() has done since
             P21 for exactly this reason.
          2c. (P54.3) XON ($11) + CR, then a second bare CR if that
             alone did not reach 'cmd:' (P54.4) -> 'cmd:' -> verbose,
             was stopped by software flow control (XOFF). The PK-232
             uses XON/XOFF (its own boot banner proves it, see
             _XON_BYTE's own comment) - a TNC stopped by a stray XOFF
             keeps echoing every character but sends nothing it
             generates itself, the identical "echo, no cmd:" shape
             steps 1/2/2b already see. Confirmed 26.09.2026: PuTTY got
             a prompt with one Enter on the same TNC/port/baud with no
             XON needed at all - this step is defense in depth for
             whatever P54.2's own dtr/rts correction does not already
             fix, not the primary repair.
          3. An HPOLL query frame (build_command(b'HP'), no argument) ->
             any $4F-CTL frame back -> Host Mode confirmed. Step 3 must
             ACTIVELY ask: in Host Mode the TNC sends nothing on its own
             while HPOLL is ON (factory default), and '*' is not a valid
             frame there either — it simply does not answer a passive
             wakeup at all. Runs the documented exit (writing
             FRAME_HOST_OFF directly, same bytes exit_host_mode() sends
             via the worker — there is no worker yet at this point in the
             connection sequence, so this reuses the byte sequence, not
             that method), then repeats step 2: if THAT sees 'cmd:', the
             TNC is confirmed back in verbose mode.
          3b. (P44) If step 3 saw no 0x4F frame at ALL — not even that —
             try the documented recovery sequence (double-SOH + GG, TRM
             4.1.6, the same FRAME_RECOVERY bytes the "Recovery" menu
             action sends) before giving up: an application killed
             abruptly while in Host Mode (Ctrl-C in the console,
             observed 25.09.2026) can leave the TNC's own frame parser
             mid-frame, waiting for an ETB that will never come and
             discarding everything further — including a fresh SOH, so
             even step 3's HPOLL query gets nothing back. Sends
             FRAME_RECOVERY then FRAME_HOST_OFF directly (not via
             recovery()/exit_host_mode(), which assume a running
             HostModeWorker that does not exist yet here — see step 3's
             own note on this), then repeats step 2 once more.
          4. None of the above answered anything usable -> no PK-232
             reachable at all. A wrong port/baud rate and a hung TNC look
             identical from here (see CLAUDE.md's "PK-232 can hang"
             gotcha) - the abort message names both.

        Every step logs both the bytes it sent and whatever it received,
        in hex, at DEBUG level (P44.C2) — costs nothing when 0 bytes come
        back, and saves a repeat hardware run the next time this needs
        diagnosing.

        On success, sets both _verbose_ready (existing) and
        _verbose_confirmed (P43 — see its own docstring in __init__) and
        emits verbose_mode_ready exactly as before. On failure, raises
        (caught by the except block below, same fallback as ever) — no
        upload is attempted from this connection cycle.
        """
        try:
            port = self._serial
            self._take_over_read_path()

            # ── Read until marker (P52.1) ────────────────────────────────
            # Delegates to the shared _read_until_prompt() - see its own
            # docstring for the exact deadline-shrinking bug this
            # replaces (confirmed via a real console capture,
            # 25.09.2026). read_direct() is the "read whatever showed up,
            # or wait a bit" primitive _read_until_prompt() needs; the
            # marker/idle/timeout state machine itself now lives in ONE
            # place, shared with write_verbose_wait().
            def read_direct(max_wait: float) -> bytes:
                n = port.in_waiting
                if n:
                    return port.read(n)
                time.sleep(max_wait)
                return b""

            def read_until(marker, timeout=_TNC_STATE_STEP_TIMEOUT):
                data, _found = _read_until_prompt(read_direct, marker, timeout)
                return data

            # ── STEP 1: Wakeup '*' — banner or cmd: means "already verbose,
            # freshly booted" (the common case right after power-on). ──
            self.status_message.emit("TNC: wakeup...")
            logger.info("Init: step 1 - wakeup '*'")
            logger.debug("Init: step 1 TX: %s", _WAKEUP.hex(' '))
            port.write(_WAKEUP)
            port.flush()
            step1_markers = (b"cmd:",) + _BANNER_MARKERS
            resp = read_until(step1_markers, timeout=_TNC_STATE_STEP_TIMEOUT)
            logger.debug("Init: step 1 response (%d B): %s", len(resp), resp.hex(' '))
            if resp and any(m in resp for m in step1_markers):
                logger.info("Init: step 1 confirmed verbose (banner/cmd:)")
                self._finish_verbose_init(resp)
                return

            # ── STEP 2: bare CR — the TNC may already be awake and simply
            # did not answer '*' the way step 1 expected. ──────────────
            logger.info("Init: step 2 - CR (already awake?)")
            logger.debug("Init: step 2 TX: %s", b"\r".hex(' '))
            port.write(b"\r")
            port.flush()
            resp2 = read_until(b"cmd:", timeout=_TNC_STATE_STEP_TIMEOUT)
            logger.debug("Init: step 2 response (%d B): %s", len(resp2), resp2.hex(' '))
            if b"cmd:" in resp2:
                logger.info("Init: step 2 confirmed verbose (cmd: after CR)")
                self._finish_verbose_init(resp2)
                return

            # ── STEP 2b (P53.B): COMMAND char — the TNC may be in
            # Converse mode, not silent or Host Mode. Every operating
            # mode has a Converse state that echoes every character typed
            # at it and shows no cmd: prompt at all — steps 1/2 alone see
            # exactly the same "echo, no cmd:" shape a genuinely
            # unresponsive TNC would produce for a byte it does not
            # recognise, so this step is the only way to tell them apart.
            # Confirmed by a real console capture, 26.09.2026: HOST OFF
            # returns the TNC to whichever operating mode was active
            # before Host Mode was entered (Baudot RTTY, that run), not
            # to the command prompt — and Converse is that mode's normal
            # idle state (TRM). self.command_char defaults to $03/Ctrl-C
            # and mirrors AppConfig.misc.command (P53.B) — the one value
            # ParamsUploader actually uploads as the real COMMAND
            # parameter, so this is "what we currently believe the TNC
            # has", not a guaranteed value. ─────────────────────────────
            logger.info(
                "Init: step 2b - COMMAND char (Ctrl-C) - "
                "TNC may be in converse mode"
            )
            command_bytes = bytes([self.command_char]) + b"\r"
            logger.debug("Init: step 2b TX: %s", command_bytes.hex(' '))
            port.write(command_bytes)
            port.flush()
            resp2b = read_until(b"cmd:", timeout=_TNC_STATE_STEP_TIMEOUT)
            logger.debug("Init: step 2b response (%d B): %s", len(resp2b), resp2b.hex(' '))
            if b"cmd:" in resp2b:
                logger.info(
                    "Init: step 2b confirmed verbose (cmd: after COMMAND "
                    "char) - TNC was in converse mode"
                )
                self._finish_verbose_init(resp2b)
                return

            # ── STEP 2c (P54.3): XON — the TNC uses SOFTWARE flow
            # control (its own boot banner proves it: '... 0d 0a 11 41
            # 45 41 ...', that $11 right before the "AEA" banner text is
            # a self-generated XON). A TNC stopped by a stray XOFF
            # ($13) - e.g. a Host Mode frame byte that leaked through -
            # keeps echoing every typed character but sends nothing it
            # generates itself (a prompt, a banner): exactly the same
            # "echo, no cmd:" shape steps 1/2/2b already saw, and the
            # SAME shape a genuinely stuck or Converse-mode TNC
            # produces - only actually sending XON can tell this case
            # apart from those. Confirmed 26.09.2026: PuTTY, on the same
            # physical TNC/port/baud with the app's own dtr/rts left
            # False (the pre-P54.2 setting), got a prompt with a single
            # Enter and no XON at all - so this step is defense, not the
            # only fix (see P54.2's own dtr/rts correction, which alone
            # may already prevent this). Two bytes, harmless if the TNC
            # was never stopped. ─────────────────────────────────────
            logger.info("Init: step 2c - XON, then CR (TNC may be flow-stopped)")
            port.write(bytes([_XON_BYTE]))
            port.flush()
            time.sleep(0.1)
            port.write(b"\r")
            port.flush()
            resp2c = read_until(b"cmd:", timeout=_TNC_STATE_STEP_TIMEOUT)
            logger.debug("Init: step 2c response (%d B): %s", len(resp2c), resp2c.hex(' '))
            if b"cmd:" in resp2c:
                logger.info("Init: step 2c - XON released a stopped TNC")
                self._finish_verbose_init(resp2c)
                return

            # P54.4: a second bare CR - cheap, and covers the case that
            # the first CR only completed an incomplete input line
            # rather than actually requesting a fresh prompt. No own
            # XON resend; if the first one was going to help, it already
            # would have by now.
            port.write(b"\r")
            port.flush()
            resp2c2 = read_until(b"cmd:", timeout=_TNC_STATE_STEP_TIMEOUT)
            logger.debug(
                "Init: step 2c second CR response (%d B): %s",
                len(resp2c2), resp2c2.hex(' '),
            )
            if b"cmd:" in resp2c2:
                logger.info("Init: step 2c - second CR reached cmd: after XON")
                self._finish_verbose_init(resp2c2)
                return

            # ── STEP 3: HPOLL query frame — the only way to reach a TNC
            # that is genuinely in Host Mode with HPOLL ON, since it does
            # not answer anything unsolicited there. ───────────────────
            #
            # P52.2: in verbose COMMAND mode the PK-232 echoes every
            # character sent, including binary frame bytes - so a TNC
            # that is actually in VERBOSE mode answers this query with
            # its own bytes right back, byte-for-byte, which
            # _extract_frames() happily parses as a well-formed-looking
            # $4F frame (SOH/CTL/ETB all line up). Confirmed by a real
            # console capture, 25.09.2026, 23:30:43: TX "01 4f 48 50 17"
            # (5 bytes, no value byte - our own query has none), "response"
            # "01 4f 48 50 17" - identical. A genuine $4F response has a
            # VALUE byte the query itself never carries: SOH $4F <m1> <m2>
            # <value> ETB, 6 bytes total (same capture, 23:30:09: TX "01
            # 4f 48 50 4e 17", RX "01 4f 48 50 00 17" - a real answer,
            # value byte $00). is_hpoll_echo() below rejects a frame whose
            # payload is exactly the query's own 2-byte mnemonic with no
            # value byte - length and content both checked, not just one.
            logger.info("Init: step 3 - HPOLL query frame")
            hpoll_query = build_command(b'HP')
            hpoll_mnemonic_only = hpoll_query[2:-1]   # b'HP' - no value byte

            def is_hpoll_echo(payload: bytes) -> bool:
                return payload == hpoll_mnemonic_only

            logger.debug("Init: step 3 TX: %s", hpoll_query.hex(' '))
            port.write(hpoll_query)
            port.flush()
            raw = bytearray()
            frames: list = []
            saw_echo = False
            deadline = time.monotonic() + _TNC_STATE_STEP_TIMEOUT
            while time.monotonic() < deadline:
                n = port.in_waiting
                if n:
                    raw.extend(port.read(n))
                    frames, _remaining = _extract_frames(bytearray(raw))
                    if any(ctl == _CTL_BYTE and is_hpoll_echo(payload)
                           for ctl, payload in frames):
                        saw_echo = True
                    if any(ctl == _CTL_BYTE and not is_hpoll_echo(payload)
                           for ctl, payload in frames):
                        break  # got a genuine answer - no need to wait out the timeout
                else:
                    time.sleep(0.02)
            logger.debug(
                "Init: step 3 raw (%d B): %s -- %d frame(s)",
                len(raw), bytes(raw).hex(' '), len(frames),
            )
            if saw_echo and not any(
                ctl == _CTL_BYTE and not is_hpoll_echo(payload)
                for ctl, payload in frames
            ):
                logger.info(
                    "Init: step 3: response equals the frame we sent "
                    "(echo) - TNC is in verbose mode, not Host Mode"
                )
            if any(ctl == _CTL_BYTE and not is_hpoll_echo(payload)
                   for ctl, payload in frames):
                logger.info(
                    "Init: step 3 confirmed Host Mode (0x4F frame) - "
                    "exiting to verbose"
                )
                # P45.1: visible progress, not just a log line - this is
                # exactly the moment recovery()/Connect knows FOR CERTAIN
                # the TNC is alive and in Host Mode (not just silent),
                # worth telling the operator while the exit-and-recheck
                # below is still running.
                self.status_message.emit(
                    "TNC responds in Host Mode - leaving Host Mode..."
                )
                self._in_host_mode = True
                logger.debug("Init: step 3 exit TX: %s", FRAME_HOST_OFF.hex(' '))
                port.write(FRAME_HOST_OFF)
                port.flush()
                time.sleep(0.2)
                self._in_host_mode = False
                logger.info("Init: repeating step 2 after Host Mode exit")
                logger.debug("Init: step 3 post-exit TX: %s", b"\r".hex(' '))
                port.write(b"\r")
                port.flush()
                resp3 = read_until(b"cmd:", timeout=_TNC_STATE_STEP_TIMEOUT)
                logger.debug(
                    "Init: post-exit response (%d B): %s",
                    len(resp3), resp3.hex(' '),
                )
                if b"cmd:" in resp3:
                    logger.info("Init: verbose confirmed after Host Mode exit")
                    self._finish_verbose_init(resp3)
                    return
                logger.error(
                    "Init: Host Mode exit did not reach cmd: - falling "
                    "through to step 4"
                )
            else:
                if saw_echo:
                    logger.info(
                        "Init: step 3 saw only its own echo, no genuine "
                        "0x4F frame"
                    )
                else:
                    logger.info("Init: step 3 saw no 0x4F frame either")

                # ── STEP 3b (P44.C1): recovery sequence — a process killed
                # abruptly while in Host Mode can leave the TNC's frame
                # parser mid-frame, waiting for an ETB that never comes and
                # discarding everything further, including a fresh SOH (so
                # step 3's own HPOLL query above got nothing back either).
                # Reuses FRAME_RECOVERY, the exact bytes the "Recovery" menu
                # action already sends (recovery()) — not calling that
                # method itself, since it calls the worker-based
                # exit_host_mode(), and there is no HostModeWorker running
                # yet at this point in the connection sequence (same reason
                # step 3 above writes FRAME_HOST_OFF directly rather than
                # via exit_host_mode()). Harmless if no TNC is attached at
                # all — a few bytes go out into nothing.
                logger.info("Init: step 3b - recovery sequence (double-SOH + GG)")
                logger.debug("Init: step 3b TX: %s", FRAME_RECOVERY.hex(' '))
                port.write(FRAME_RECOVERY)
                port.flush()
                time.sleep(0.2)
                logger.debug("Init: step 3b exit TX: %s", FRAME_HOST_OFF.hex(' '))
                port.write(FRAME_HOST_OFF)
                port.flush()
                time.sleep(0.2)
                self._in_host_mode = False
                logger.info("Init: repeating step 2 after recovery sequence")
                logger.debug("Init: step 3b post-recovery TX: %s", b"\r".hex(' '))
                port.write(b"\r")
                port.flush()
                resp3b = read_until(b"cmd:", timeout=_TNC_STATE_STEP_TIMEOUT)
                logger.debug(
                    "Init: post-recovery response (%d B): %s",
                    len(resp3b), resp3b.hex(' '),
                )
                if b"cmd:" in resp3b:
                    logger.info("Init: verbose confirmed after recovery sequence")
                    self._finish_verbose_init(resp3b)
                    return
                logger.error(
                    "Init: recovery sequence did not reach cmd: either - "
                    "falling through to step 4"
                )

            # ── STEP 4: nothing answered at all. ────────────────────────
            port_name = getattr(port, 'port', '?')
            baudrate  = getattr(port, 'baudrate', '?')
            raise RuntimeError(
                f"No PK-232 responding on {port_name} at {baudrate}: no "
                f"banner, no cmd: prompt and no Host Mode frame. Check "
                f"port and baud rate, or power-cycle the TNC - it may be "
                f"stuck (see the troubleshooting note in CLAUDE.md)."
            )

        except Exception as exc:
            logger.error("init_tnc failed: %s", exc)
            self.status_message.emit(f"TNC init error: {exc}")
            # P45.2: connection_changed(True) already fired when the port
            # opened, well before this detection chain ran - the UI must
            # not go on looking connected just because that earlier
            # signal said so. The port itself is deliberately left open
            # (not disconnect_port()) - Recovery needs it, and this is
            # exactly the "it is the way out" case. See
            # MainWindow._on_init_failed().
            self.init_failed.emit()
            if self._reader is None and self._serial and self._serial.is_open:
                self._reader = _ReaderThread(
                    self._serial, self._on_frame_received,
                    raw_callback=self._on_raw_data,
                    host_mode_flag=lambda: self._in_host_mode,
                )
                self._reader.start()

    def _finish_verbose_init(self, resp: bytes) -> None:
        """Common tail once _init_tnc_thread() has actively confirmed a
        verbose prompt (P43, any of steps 1/2/3-then-2) - banner capture,
        flags, reader thread, signal. *resp* is whatever was captured on
        the step that succeeded; banner markers are looked for in it
        regardless of which step matched, same as the original single-step
        wakeup did."""
        if any(m in resp for m in _BANNER_MARKERS):
            self._tnc_banner = resp
            logger.info(
                "TNC banner captured: PACTOR=%s (%d bytes)",
                b"PACTOR" in resp, len(resp),
            )
        self._last_verbose_init_resp = resp
        level, message = _wakeup_log_message(resp)
        logger.log(level, message)
        self._verbose_ready     = True
        self._verbose_confirmed = True
        self.status_message.emit("TNC ready (verbose)")
        logger.info("Init complete — TNC in verbose mode")
        self._reader = _ReaderThread(
            self._serial, self._on_frame_received,
            raw_callback=self._on_raw_data,
            host_mode_flag=lambda: self._in_host_mode,
        )
        self._reader.start()
        self.verbose_mode_ready.emit()

    def _full_init(self) -> None:
        """No-op: PCPackRatt sends nothing before HOST 3 after wakeup.
        AWLEN/PARITY skipped — TNC uses default values which are correct."""
        logger.info("Init: skipping verbose config (PCPackRatt-style)")

    def _short_init(self) -> None:
        """No-op: PCPackRatt sends nothing before HOST 3."""
        logger.info("Init: skipping verbose config (PCPackRatt-style)")

    # ------------------------------------------------------------------
    # Phase 3 — switch to Host Mode
    # ------------------------------------------------------------------

    def enter_host_mode(self) -> bool:
        """Phase 3: Send HOST 3 — switch TNC to binary Host Mode.

        PCPackRatt-verified sequence:
          1. Send "HOST 3\r" in verbose mode
          2. Send HPOLL Y as first Host Mode frame
          3. Wait for HPOLL ACK to confirm Host Mode is active

        Call after Phase 2 (parameter upload) is complete.
        Runs in a background thread.
        """
        if not self.is_connected:
            logger.error("enter_host_mode: not connected")
            return False
        if self._in_host_mode:
            logger.warning("Host Mode already active")
            return True

        t = threading.Thread(
            target=self._enter_host_mode_thread,
            daemon=True,
            name="PK232-HostModeEnter",
        )
        t.start()
        return True

    def _enter_host_mode_thread(self) -> None:
        """Enter Host Mode — exakt wie pk232_minimal_qt.py.

        Bewiesene Sequenz:
          1. ReaderThread stoppen + Port schliessen
          2. Subprocess: HOST 3 + HPOLL Y → OK
          3. Port neu öffnen (frisches Serial Objekt!)
          4. Worker starten
          5. HP N senden + 500ms warten
          6. host_mode_changed emittieren
        """
        import subprocess, sys, os

        try:
            logger.info("Entering Host Mode via subprocess...")
            self.status_message.emit("Entering Host Mode...")

            port_name = self._serial.port
            baudrate  = self._serial.baudrate

            # Nuitka --onefile has no python.exe to spawn pk232_hostmode_sub.py
            # as a script, and sys.executable is the app EXE itself — so spawning
            # would re-launch the GUI. Detect the compiled build and run the
            # SAME handshake in-process instead. A normal interpreter keeps the
            # proven subprocess path unchanged.
            try:
                __compiled__          # noqa: F821  (Nuitka injects this when compiled)
                _is_compiled = True
            except NameError:
                _is_compiled = False

            sub_script = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "pk232_hostmode_sub.py"
            )
            if not _is_compiled and not os.path.exists(sub_script):
                raise FileNotFoundError(f"Not found: {sub_script}")

            # Stop ReaderThread and close port
            if self._reader:
                self._reader.stop()
                self._reader.join(timeout=2.0)
                self._reader = None
            self._serial.close()
            logger.debug("Port closed for Host Mode entry")
            time.sleep(0.3)

            # Run the proven Host Mode entry sequence.
            if _is_compiled:
                # In-process: same byte sequence, fresh Serial object (CLAUDE.md §3).
                from .pk232_hostmode_sub import enter_host_mode
                logger.info("Host Mode entry in-process (compiled build)")
                ok, raw = enter_host_mode(port_name, baudrate)
                output = "OK" if ok else "FAIL:" + raw.hex()
                stderr = ""
            else:
                result = subprocess.run(
                    [sys.executable, sub_script, port_name, str(baudrate)],
                    capture_output=True, text=True, timeout=15
                )
                output = result.stdout.strip()
                stderr = result.stderr.strip()
            logger.info("Host Mode entry result: %r", output)
            if stderr:
                logger.error("Subprocess stderr: %s", stderr)

            if output != "OK":
                logger.error("Subprocess failed: %r / %s", output, stderr)
                self._serial.open()
                self._reader = _ReaderThread(
                    self._serial, self._on_frame_received,
                    raw_callback=self._on_raw_data,
                    host_mode_flag=lambda: self._in_host_mode,
                )
                self._reader.start()
                self.status_message.emit(f"Host Mode error: {output or stderr}")
                return

            # Reopen port — new Serial object like pk232_minimal_qt.py
            time.sleep(0.3)
            import serial as _serial
            new_port = _serial.Serial(
                port     = port_name,
                baudrate = baudrate,
                bytesize = 8,
                parity   = 'N',
                stopbits = 1,
                timeout  = 0.1,
                xonxoff  = False,
                rtscts   = False,
            )
            # Replace the internal serial object with the fresh one
            self._serial = new_port
            logger.debug("Port reopened (fresh object)")

            self._in_host_mode  = True
            self._verbose_ready = False
            # P43: verbose_confirmed only ever attests to the CURRENT
            # verbose session - it says nothing about the Host Mode
            # session that is about to start.
            self._verbose_confirmed = False

            # Frame adapter: (ctl, payload) → HostFrame → Qt Signal
            def _frame_adapter(ctl, payload):
                try:
                    frame = _make_host_frame(ctl, payload)
                    self._on_frame_received(frame)
                except Exception as exc:
                    logger.error("Frame adapter: %s", exc)

            # Start Worker — exakt wie pk232_minimal_qt.py
            from .pk232_hostmode_sub import HostModeWorker as _HMW, HPOLL_OFF
            self._worker = _HMW(
                self._serial, _frame_adapter,
                raw_callback=self._on_raw_data,
            )
            self._worker.start()

            # HP N senden + 500ms warten — bewiesene Sequenz
            self._worker.send(HPOLL_OFF)
            time.sleep(0.5)
            logger.info("HPOLL OFF sent — TNC pushes data spontaneously")

            self.host_mode_changed.emit(True)
            self.status_message.emit("Host Mode active ✓")
            logger.info("Host Mode active!")

        except Exception as exc:
            logger.error("enter_host_mode failed: %s", exc)
            self.status_message.emit(f"Host Mode error: {exc}")
            try:
                if not self._serial.is_open:
                    self._serial.open()
                if self._reader is None:
                    self._reader = _ReaderThread(
                        self._serial, self._on_frame_received,
                        raw_callback=self._on_raw_data,
                        host_mode_flag=lambda: self._in_host_mode,
                    )
                    self._reader.start()
            except Exception:
                pass


    def exit_host_mode(self) -> None:
        """Send HOST OFF binary frame — return TNC to verbose mode."""
        if not self.is_connected or not self._in_host_mode:
            return
        try:
            # Send HOST OFF via Worker — guarantees serialization after pending TX
            if self._worker and self._worker.is_alive():
                self._worker.send(FRAME_HOST_OFF)
                time.sleep(0.5)  # let worker send HOST OFF and read response

            # Stop Worker
            if self._worker:
                self._worker.stop()
                self._worker.join(timeout=1.0)
                self._worker = None

            self._in_host_mode  = False
            self._verbose_ready = False
            time.sleep(0.2)  # wait for TNC to switch back to verbose

            # Start fresh ReaderThread for verbose mode
            self._reader = _ReaderThread(
                self._serial, self._on_frame_received,
                raw_callback=self._on_raw_data,
                host_mode_flag=lambda: self._in_host_mode,
            )
            self._reader.start()

            self.host_mode_changed.emit(False)
            self.status_message.emit("Host Mode off — verbose mode")
            logger.info("Host Mode deactivated")

            # P53.B.2: HOST OFF returns the TNC to whichever operating
            # mode was active before Host Mode was entered, not to the
            # command prompt - for Baudot/AMTOR/PACTOR that mode's normal
            # idle state is Converse, which echoes every character and
            # shows no prompt at all (confirmed by a real console
            # capture, 26.09.2026 - the same finding step 2b above
            # exists for). Sending the COMMAND character right away here
            # makes the verbose terminal immediately usable instead of
            # just echoing, and spares the NEXT connect cycle its own
            # step 2b - write_verbose_wait() already works over the
            # ReaderThread just (re)started above, no read-path
            # takeover needed.
            command_bytes = bytes([self.command_char]) + b"\r"
            ok = self.write_verbose_wait(command_bytes, timeout=1.5)
            logger.info(
                "Host Mode exit: COMMAND char resync %s",
                "reached cmd: (TNC was in converse mode)" if ok
                else "got no cmd: (TNC may already be at the prompt)",
            )
        except Exception as exc:
            logger.error("exit_host_mode: %s", exc)

    def recovery(self, port_name: str = None, baudrate: int = None) -> bool:
        """P45.1 / P46.B: the emergency reconnect. Works from ANY state —
        no connection, mid-error, stuck in Host Mode — because it is the
        one action nothing may lock out (P46 Teil B). If the port is not
        currently open, opens it first using *port_name*/*baudrate* (the
        caller's saved config — MainWindow passes AppConfig.tnc.port/
        tbaud); with no port open and none given, there is nothing to
        recover, so this returns False without starting anything.

        Once a port exists, sends the documented recovery sequence
        (double-SOH + GG, TRM 4.1.6, then HOST OFF — the same
        FRAME_RECOVERY/FRAME_HOST_OFF bytes _init_tnc_thread()'s own step
        3b already sends), then determines and reports the resulting TNC
        state via the EXISTING P43/P44 detection chain (_init_tnc_thread()
        itself — no second version of it is built here).

        Runs in a background thread — the detection chain alone can take
        several seconds (up to five 1.5s steps), so never call this from
        the GUI thread expecting an immediate result. Emits
        recovery_finished(success, message) when done;
        MainWindow._on_recovery_finished() is the sole consumer — the old
        behaviour (send the sequence, emit a generic "Recovery sent" and
        stop) left the operator with no way to tell whether anything had
        actually worked (found 25.09.2026: Recovery pressed, no visible
        reaction, only a later "Host Mode" button press revealed it had).
        """
        if not self.is_connected:
            if not port_name:
                logger.error("Recovery: no open port and no port configured")
                return False
            if not self.connect_port(port_name, baudrate=baudrate or SerialDefaults.BAUDRATE):
                return False
        t = threading.Thread(
            target=self._recovery_thread, daemon=True, name="PK232-Recovery"
        )
        t.start()
        return True

    def _recovery_thread(self) -> None:
        try:
            # P46.A.1: take over the read path BEFORE sending anything —
            # including this method's own preamble below, not just the
            # chain's steps. See _take_over_read_path()'s own docstring
            # for the exact bug this closes.
            logger.info("Recovery: taking over the read path")
            self._take_over_read_path()

            logger.info("Recovery: sending recovery sequence")
            self.status_message.emit("Recovery: sending recovery frames...")
            self._write_raw(FRAME_RECOVERY)
            time.sleep(0.2)
            self._write_raw(FRAME_HOST_OFF)
            time.sleep(0.2)
            self._in_host_mode = False

            self.status_message.emit("Recovery: determining TNC state...")
            # Reuses the existing chain outright - it already implements
            # "CR -> cmd:; else HPOLL frame; else the recovery sequence
            # again" as its own steps 2/3/3b, plus a step 1 ('*') that is
            # harmless to try again here. It calls _take_over_read_path()
            # itself too - a harmless no-op re-clear at this point (the
            # reader is already stopped), which is exactly what is wanted:
            # any ack/echo of THIS method's own preamble must not be
            # mistaken for the chain's own step 1 response.
            self._init_tnc_thread()

            if self._verbose_confirmed:
                msg = (
                    "Connection recovered - TNC is at the command prompt "
                    "(verbose mode)."
                )
                logger.info("Recovery: %s", msg)
                self.recovery_finished.emit(True, msg)
            else:
                msg = "Recovery did not reach the TNC. Power-cycle it and reconnect."
                logger.error("Recovery: %s", msg)
                self.recovery_finished.emit(False, msg)
        except Exception as exc:
            msg = (
                f"Recovery did not reach the TNC. Power-cycle it and "
                f"reconnect. ({exc})"
            )
            logger.error("recovery: %s", exc)
            self.recovery_finished.emit(False, msg)

    # ------------------------------------------------------------------
    # Sending frames (Host Mode)
    # ------------------------------------------------------------------

    def send_command(self, mnemonic: bytes, args: bytes = b"") -> bool:
        """Send a Host Mode command frame via HostModeWorker queue.

        The worker sends each frame and reads the response before
        processing the next — exactly like pk232_hostmode.py.
        """
        if not self._check_ready():
            return False
        if self._worker and self._worker.is_alive():
            self._worker.send(build_command(mnemonic, args))
            return True
        return self._write_raw(build_command(mnemonic, args))

    def send_channel_command(self, channel: int, mnemonic: bytes, args: bytes = b"") -> bool:
        """Send a channel command frame (CTL=$4x, for CONNECT/DISCONNECT).

        P50 Teil A: logs the requested channel right next to the actual
        CTL byte that goes out, in one line - so a hardware capture can
        directly confirm build_ch_cmd() encoded the channel the operator
        actually selected, without having to cross-reference a separate
        hex dump. `_write_raw()` already hex-logs every write (unchanged,
        not duplicated here); this is specifically for CONNECT/DISCONNECT,
        the frames the 25.09.2026 channel-offset report (chip 1 green,
        all incoming data/link messages tagged [CH2]) needs measured
        against a real TNC to settle - see CLAUDE.md's own note on this.
        """
        if not self._check_ready():
            return False
        frame = build_ch_cmd(channel, mnemonic, args)
        logger.debug(
            "TX channel cmd: channel=%d ctl=0x%02X mnemonic=%s frame=%s",
            channel, frame[1], mnemonic, frame.hex(' '),
        )
        return self._write_raw(frame)

    def send_data(self, data: bytes, channel: int = 0) -> bool:
        """Send a data frame (CTL=$2x)."""
        if not self._check_ready():
            return False
        return self._write_raw(build_data(channel, data))

    def _poll_loop(self) -> None:
        """GG poll loop — per TRM 4.4.1 (HPOLL ON mode).

        CRITICAL: holds _write_lock for the entire poll+read cycle.
        This prevents _write_raw() from interleaving bytes with our poll.
        The Prolific USB chip coalesces writes — interleaving corrupts frames.
        """
        port = self._serial
        if port is None or not port.is_open:
            return

        logger.debug("GG poll loop started")
        _buf = bytearray()

        while self._poll_active and self._in_host_mode:
            if port is None or not port.is_open:
                break

            try:
                # Hold lock for entire poll+read cycle — no interleaving allowed
                with self._write_lock:
                    port.write(FRAME_POLL)
                    port.flush()

                    # Read response immediately — TNC responds to each poll
                    deadline = time.monotonic() + 0.15
                    while time.monotonic() < deadline:
                        try:
                            n = port.in_waiting
                        except Exception:
                            break
                        if n:
                            chunk = port.read(n)
                            _buf.extend(chunk)
                            logger.debug("GG poll RX %d B: %s", len(chunk), chunk.hex())
                            if 0x17 in chunk:
                                break
                            deadline = time.monotonic() + 0.05
                        else:
                            time.sleep(0.005)

            except Exception as exc:
                logger.error("Poll error: %s", exc)
                break

            # Parse and dispatch complete frames (outside lock)
            frames, _buf = _extract_frames(_buf)
            for ctl, payload in frames:
                # Skip GG $00 — nothing waiting
                if ctl == 0x4F and (payload[:2] == b'GG' and len(payload) == 3 and payload[2] == 0):
                    continue
                try:
                    frame = _make_host_frame(ctl, payload)
                    logger.debug("RX poll frame: ctl=0x%02X payload=%s", ctl, payload.hex())
                    self._on_frame_received(frame)
                except Exception as exc:
                    logger.error("Frame dispatch: %s", exc)

            time.sleep(0.1)

        logger.debug("GG poll loop stopped")


    def send_poll(self) -> bool:
        """Send HPOLL GG poll frame."""
        if not self._check_ready():
            return False
        return self._write_raw(FRAME_POLL)

    def write_verbose(self, data: bytes) -> bool:
        """Write raw ASCII bytes in verbose mode (for ParamsUploader).

        Args:
            data: e.g. b'MYCALL OE3GAS\\r\\n'
        """
        if not self.is_connected:
            logger.warning("write_verbose: not connected")
            return False
        return self._write_raw(data)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------


    @staticmethod
    def _is_cmd_prompt(buf: bytes) -> bool:
        """The 'cmd:' match rule write_verbose_wait() has always used:
        at the very start of the buffer, or preceded by a newline - never
        a bare substring match, which would also fire on an ECHOED
        command that merely contains the letters "cmd:" somewhere inside
        it (P52.1 - kept exactly as it was, callable() form for
        _read_until_prompt() below)."""
        return buf.startswith(b'cmd:') or b'\ncmd:' in buf

    def write_verbose_wait(self, data: bytes, timeout: float = 5.0) -> bool:
        """Send a verbose-mode command and wait for TNC cmd: prompt.

        Sends the command, then accumulates incoming bytes until
        'cmd:' is detected (preceded by newline, or at chunk start), plus
        a further short idle window (TNC has genuinely finished writing,
        not just paused mid-response - simply returning on 'cmd:' alone
        causes the next command to interleave with the TNC's still-running
        response output).

        Args:
            data:    ASCII command e.g. b'MYCALL OE3GAS\r\n'
            timeout: Max seconds to wait (default 5.0)

        Returns:
            True if cmd: received, False on timeout.
        """
        found, _text = self._write_verbose_wait_text(data, timeout=timeout)
        return found

    def _write_verbose_wait_text(
        self, data: bytes, timeout: float = 5.0,
    ) -> tuple[bool, bytes]:
        """Same send-and-wait as write_verbose_wait(), but also returns
        every byte read while waiting (P53.A) - the accumulated response
        _read_until_prompt() already assembled internally to decide
        *found*, which the public write_verbose_wait() used to just
        throw away.

        Why this exists: query_verbose_value() and detect_maildrop() used
        to get their own copy of the response through a SEPARATE,
        transient raw_data_received.connect()/disconnect() pair wrapped
        around a plain write_verbose_wait() call - reproduced as a real
        race, not a suspicion (P53.A, 2026-09-25): raw_data_received is a
        Qt signal crossing from the ReaderThread into whatever thread
        constructed SerialManager (the GUI thread in production), which
        needs THAT thread's event loop to actually pump the queued
        delivery before it is seen. write_verbose_wait()'s own "found"
        result never needed that signal at all - it reads _rx_buf/
        _rx_buf_event directly, both filled by a plain synchronous call
        from the reader (no Qt involved) - so it can return the instant
        the idle window after 'cmd:' elapses. The transient listener's
        disconnect() then ran on the CALLING thread microseconds later,
        and Qt drops a queued delivery outright if the connection is torn
        down before the receiver's event loop ever got to process it - a
        20/20 reproduction with a real QCoreApplication actively pumping
        (see test_serial_manager.py::TestVerboseQueryReadPath) confirmed
        this drops the response every single time once the two race,
        while a caller with no transient connect/disconnect (MainWindow's
        own persistent terminal listener, MailDropSession's own
        connect-at-open/disconnect-at-close) never loses anything - which
        is exactly why the operator's terminal showed 'MYcall OE3GAS' in
        the 26.09.2026 capture while ParamsUploader.verify() reported "no
        answer" for the very same query. Handing back the SAME bytes
        write_verbose_wait() already has removes the second, racy
        consumer instead of trying to win the race some other way (a
        direct port read while the ReaderThread is stopped would still
        need its own new consumer and would cost a multi-command upload
        the terminal's live display for however long it took - see the
        commit message for why that alternative was not chosen).
        """
        if not self.is_connected:
            return False, b""
        if not self._write_raw(data):
            return False, b""
        import time as _t

        _IDLE_S = 0.12   # 120 ms idle = TNC has finished writing
        _t.sleep(0.05)   # give TNC time to start responding

        def read_buffered(max_wait: float) -> bytes:
            with self._rx_buf_lock:
                chunk = bytes(self._rx_buf)
                self._rx_buf.clear()
            self._rx_buf_event.clear()
            if chunk:
                return chunk
            self._rx_buf_event.wait(timeout=max_wait)
            with self._rx_buf_lock:
                chunk = bytes(self._rx_buf)
                self._rx_buf.clear()
            self._rx_buf_event.clear()
            return chunk

        # P52.1: shares _read_until_prompt() with the P43 detection
        # chain's own read_until() (_init_tnc_thread()) - ONE
        # marker/idle/timeout state machine, two data sources (this one
        # reads the ReaderThread-fed _rx_buf via an Event; the detection
        # chain reads the port directly, since it stops the ReaderThread
        # first). Behaviour is unchanged from before this refactor - only
        # the state machine moved.
        resp, found = _read_until_prompt(
            read_buffered, self._is_cmd_prompt, timeout, idle_after_marker=_IDLE_S
        )
        return found, resp

    def _write_raw(self, data: bytes) -> bool:
        try:
            with self._write_lock:
                self._serial.write(data)
            logger.debug("TX (%d B): %s", len(data), data.hex(' '))
            return True
        except Exception as exc:
            logger.error("Serial write error: %s", exc)
            self.status_message.emit(f"Send error: {exc}")
            return False

    def _check_ready(self) -> bool:
        if not self.is_connected:
            logger.warning("send: not connected")
            return False
        if not self._in_host_mode:
            logger.warning("send: not in Host Mode")
            return False
        return True

    def _on_frame_received(self, frame: HostFrame) -> None:
        if self._in_host_mode:
            logger.debug("RX %r", frame)
        self.frame_received.emit(frame)

    def _on_raw_data(self, data: bytes) -> None:
        """Store raw bytes in shared buffer and forward to UI."""
        if self._in_host_mode:
            logger.debug("RX (%d B): %s", len(data), data.hex(' '))
        with self._rx_buf_lock:
            self._rx_buf.extend(data)
        self._rx_buf_event.set()
        if not self._in_host_mode:
            self.raw_data_received.emit(data)

    @staticmethod
    def list_ports() -> list[str]:
        if not PYSERIAL_AVAILABLE:
            return []
        return [p.device for p in serial.tools.list_ports.comports()]