# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Mode Manager — coordinates operating mode switching and frame dispatch.

The ModeManager sits between SerialManager and the Mode classes:

  SerialManager                ModeManager               Active Mode
  ─────────────                ───────────               ───────────
  frame_received ──signal────► on_frame()  ──────────► handle_frame()
  is_host_mode   ◄─────────── send_frames()◄─────────── get_activate_frames()
                                                          get_init_frames()

Responsibilities
----------------
1. Track which mode is currently active (``current_mode``).
2. Switch modes: deactivate old mode, send activate + init frames,
   wait for ACK, call activate() on new mode.
3. Dispatch incoming HostFrames to the active mode's handle_frame().
4. Emit Qt signals for the UI: mode_changed, status_message.

Mode switching sequence (per BaseMode lifecycle)
-------------------------------------------------
  1. Call ``current_mode.deactivate()`` (if any mode active).
  2. Send ``new_mode.get_activate_frames()`` via SerialManager.
  3. Wait for CMD_RESP ACK from TNC.
  4. Send ``new_mode.get_init_frames()`` via SerialManager.
  5. Call ``new_mode.activate()``.
  6. Emit ``mode_changed(new_mode.name)``.

In v0.1 the ACK wait is a simple timeout (no blocking).  A proper
ACK-wait state machine is planned for v0.2.
"""

from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from .modes import ALL_MODES, MODE_BY_NAME, BaseMode
from .comm.frame import HostFrame, FrameKind


logger = logging.getLogger(__name__)

# Delay (ms) between sending activate frames and sending init frames.
# Gives the TNC time to switch modes before parameter upload.
_ACTIVATE_DELAY_MS = 300


class ModeManager(QObject):
    """Manages the active operating mode and dispatches incoming frames.

    Args:
        serial: The application's :class:`~comm.serial_manager.SerialManager`
                instance.  ModeManager calls ``send_command()``,
                ``send_channel_command()`` and ``send_data()`` on it.
        parent: Optional Qt parent.

    Qt Signals
    ----------
    mode_changed(str)
        Emitted when a mode switch completes successfully.
        Carries the new mode's ``name`` string.

    mode_switch_failed(str)
        Emitted when a mode switch fails (e.g. not connected).
        Carries an error description string.

    status_message(str)
        Human-readable status string for the status bar.

    Typical usage::

        mm = ModeManager(serial_manager, parent=self)
        mm.mode_changed.connect(on_mode_changed)
        mm.set_mode("HF Packet")
    """

    mode_changed      = pyqtSignal(str)    # new mode name
    mode_switch_failed = pyqtSignal(str)   # error description
    status_message    = pyqtSignal(str)

    def __init__(
        self,
        serial: "SerialManager",
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._serial       = serial
        self._active_mode: Optional[BaseMode] = None
        self._pending_mode: Optional[BaseMode] = None
        self._init_timer   = QTimer(self)
        self._init_timer.setSingleShot(True)
        self._init_timer.timeout.connect(self._send_init_frames)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def current_mode(self) -> Optional[BaseMode]:
        """The currently active :class:`~modes.BaseMode` instance, or None."""
        return self._active_mode

    @property
    def current_mode_name(self) -> str:
        """Name of the active mode, or empty string if no mode is active."""
        return self._active_mode.name if self._active_mode else ""

    def available_modes(self) -> list[str]:
        """Return a list of all available mode names in display order."""
        return [name for name, _ in ALL_MODES]

    def set_mode(self, name: str, mode_instance: Optional[BaseMode] = None) -> bool:
        """Switch the TNC to the named operating mode.

        If *mode_instance* is provided it is used directly (allows passing
        a pre-configured instance, e.g. with custom MYSELCAL or callbacks).
        Otherwise a fresh instance with default parameters is created.

        The switch is asynchronous:
          1. Activate frames are sent immediately.
          2. After ``_ACTIVATE_DELAY_MS`` the init frames are sent.
          3. ``mode_changed`` is emitted and ``activate()`` called.

        Args:
            name:          Mode name, e.g. ``"HF Packet"`` or ``"AMTOR"``.
            mode_instance: Optional pre-configured mode instance.

        Returns:
            True if the switch was initiated, False if preconditions
            failed (not connected, unknown mode name, etc.).
        """
        if not self._serial.is_connected:
            msg = "Cannot switch mode: TNC not connected"
            logger.warning(msg)
            self.mode_switch_failed.emit(msg)
            return False

        # Modes with verbose_command can be activated in verbose mode too
        cls_check = MODE_BY_NAME.get(name)
        needs_host = not (cls_check and getattr(cls_check, 'verbose_command', None))
        if needs_host and not self._serial.is_host_mode:
            msg = "Cannot switch mode: Host Mode not active"
            logger.warning(msg)
            self.mode_switch_failed.emit(msg)
            return False

        if name not in MODE_BY_NAME:
            msg = f"Unknown mode: {name!r}"
            logger.error(msg)
            self.mode_switch_failed.emit(msg)
            return False

        cls = MODE_BY_NAME[name]
        new_mode = mode_instance if mode_instance is not None else cls()

        # Deactivate current mode
        if self._active_mode is not None:
            logger.info("Deactivating mode: %s", self._active_mode.name)
            self._active_mode.deactivate()
            self._active_mode = None

        # Send activate frames
        logger.info("Switching to mode: %s", name)
        self.status_message.emit(f"Switching to {name}…")
        self._pending_mode = new_mode
 
        activate_frames = new_mode.get_activate_frames()
        verbose_cmd = getattr(new_mode, 'verbose_command', None)
 
        if activate_frames and self._serial.is_host_mode:
            # Normal Host Mode activation
            for frame in activate_frames:
                self._serial.send_command(
                    frame[2:4],
                    frame[4:-1],
                )
        elif verbose_cmd:
            # Verbose Mode activation (e.g. PACTOR)
            if self._serial.is_host_mode:
                # In Host Mode: exit first, send verbose cmd, re-enter
                logger.info("Verbose-only mode %s: exiting Host Mode first", name)
                self._serial.exit_host_mode()
                import time as _t
                _t.sleep(0.5)
                self._serial.write_verbose(verbose_cmd)
                logger.info("Verbose cmd sent: %r", verbose_cmd)
            else:
                # Already in verbose mode
                self._serial.write_verbose(verbose_cmd)
                logger.info("Verbose cmd sent: %r", verbose_cmd)
 
        # Schedule init frame upload after short delay
        self._init_timer.start(_ACTIVATE_DELAY_MS)
        return True

    def set_mode_instance(self, mode: BaseMode) -> bool:
        """Switch to a pre-configured mode instance.

        Convenience wrapper for ``set_mode(mode.name, mode)``.
        """
        return self.set_mode(mode.name, mode_instance=mode)

    # ------------------------------------------------------------------
    # Frame dispatch
    # ------------------------------------------------------------------

    def on_frame(self, frame: HostFrame) -> None:
        """Receive a decoded HostFrame from SerialManager and dispatch it.

        Connect SerialManager.frame_received to this slot.

        CMD_RESP frames ($4F) are always handled here (for mode-switch
        ACK detection).  All other frames are forwarded to the active mode.

        Args:
            frame: Decoded :class:`~comm.frame.HostFrame` from the TNC.
        """
        if frame.kind == FrameKind.CMD_RESP:
            self._handle_cmd_resp(frame)
            return

        if self._active_mode is not None:
            try:
                self._active_mode.handle_frame(frame)
            except Exception as exc:
                logger.error(
                    "Mode %s raised in handle_frame: %s",
                    self._active_mode.name, exc
                )
        else:
            logger.debug("ModeManager: no active mode, frame dropped: %r", frame)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _send_init_frames(self) -> None:
        """Send init frames for the pending mode (called by timer)."""
        if self._pending_mode is None:
            return

        mode = self._pending_mode
        self._pending_mode = None

        init_frames = mode.get_init_frames()
        for frame in init_frames:
            if len(frame) >= 5:
                mnemonic = frame[2:4]
                args     = frame[4:-1]
                self._serial.send_command(mnemonic, args)

        # Activate mode
        mode.activate()
        self._active_mode = mode
        self.mode_changed.emit(mode.name)
        self.status_message.emit(f"Mode: {mode.name}")
        logger.info("Mode active: %s", mode.name)

    def _handle_cmd_resp(self, frame: HostFrame) -> None:
        """Handle CMD_RESP ($4F) frames.

        In v0.1: log ACK/NAK and forward to active mode if present.
        In v0.2: use this to implement proper ACK-wait state machine.
        """
        if frame.is_ack:
            logger.debug("CMD ACK: %s", frame.mnemonic)
        elif frame.cmd_error is not None:
            logger.warning(
                "CMD NAK: mnemonic=%s error=0x%02X",
                frame.mnemonic, frame.cmd_error
            )

        # Also forward to active mode (e.g. OPMODE response)
        if self._active_mode is not None:
            try:
                self._active_mode.handle_frame(frame)
            except Exception as exc:
                logger.error(
                    "Mode %s raised handling CMD_RESP: %s",
                    self._active_mode.name, exc
                )