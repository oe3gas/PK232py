# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Host Mode protocol constants for the AEA PK-232 / PK-232MBX.

Source: AEA PK-232 Technical Reference Manual, Chapter 4 (Host Mode).

IMPORTANT — This is NOT the WA8DED/DL3ECD "Hostmode" protocol used by
other TNCs (e.g. TF/G TNC-2, Kantronics).  That protocol encodes port and
frame-type in the nibbles of the CTL byte.  The AEA PK-232 Host Mode uses
a completely different, range-based CTL encoding described below.

CTL byte semantics (TRM Section 4.2 / 4.3)
-------------------------------------------
The CTL byte directly encodes BOTH the direction/type AND the channel
number as a single hex value in a range:

  Host -> TNC (outgoing):
    $2x   data to channel x          (x = 0-9)
    $4x   command to channel x       (CONNECT, DISCONNECT)
    $4F   command, no channel change (all other commands)

  TNC -> Host (incoming):
    $2F   echoed TX data (Morse, Baudot, AMTOR)
    $3x   received data from channel x
    $3F   monitored frames (UNPROTO / traffic monitor)
    $4x   link status from channel x (response to CONNECT)
    $4F   response to command
    $5x   link messages from channel x
    $5F   status errors / data acknowledgement

There is no separate "port" nibble in the AEA protocol.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Frame delimiters
# ---------------------------------------------------------------------------

SOH = 0x01   # Start of Header  — begins every frame
ETB = 0x17   # End of Transmission Block — ends every frame
DLE = 0x10   # Data Link Escape — escape prefix for special bytes in data

# Bytes that must be DLE-escaped when they appear in the data field
# (TRM Section 4.1.5: applies in both directions, host->TNC and TNC->host)
ESCAPE_CHARS: frozenset[int] = frozenset({SOH, DLE, ETB})


# ---------------------------------------------------------------------------
# CTL byte values — Host -> TNC (outgoing)
# ---------------------------------------------------------------------------

# $2x: send data to channel x (x = 0-9)
CTL_TX_DATA_BASE  = 0x20   # OR with channel number: 0x20 | ch

# $4x: channel-specific commands (CONNECT, DISCONNECT) to channel x
CTL_TX_CMD_CH_BASE = 0x40  # OR with channel number: 0x40 | ch

# $4F: all other commands (no channel change)
CTL_TX_CMD        = 0x4F


# ---------------------------------------------------------------------------
# CTL byte values — TNC -> Host (incoming)
# ---------------------------------------------------------------------------

# $2F: echoed TX characters (Morse, Baudot, AMTOR only)
CTL_RX_ECHO       = 0x2F

# $3x: received data from channel x (Packet ARQ data, AMTOR ARQ)
CTL_RX_DATA_BASE  = 0x30   # OR with channel: 0x30 | ch

# $3F: monitored frames (UNPROTO / traffic monitor / AMTOR FEC+SELFEC)
CTL_RX_MONITOR    = 0x3F

# $4x: link status from channel x (response to CONNECT command)
CTL_RX_LINK_BASE  = 0x40   # OR with channel: 0x40 | ch

# $4F: command response (ACK/NAK, query reply)
CTL_RX_CMD_RESP   = 0x4F

# $5x: link messages from channel x (CONNECTED, DISCONNECTED, ...)
CTL_RX_MSG_BASE   = 0x50   # OR with channel: 0x50 | ch

# $5F: status errors and data acknowledgement
CTL_RX_STATUS     = 0x5F


# ---------------------------------------------------------------------------
# Command response codes  (TRM Section 4.3, third byte after mnemonic)
# ---------------------------------------------------------------------------

class CmdError:
    """Error codes returned by the TNC in a $4F command-response frame.

    Frame format:  SOH $4F <mnemonic 2 bytes> <code> ETB
    Code $00 means success (acknowledge, no error).
    """
    OK                   = 0x00  # acknowledge, no error
    BAD                  = 0x01  # bad argument
    TOO_MANY             = 0x02
    NOT_ENOUGH           = 0x03
    TOO_LONG             = 0x04
    RANGE                = 0x05  # value out of range
    CALLSIGN             = 0x06  # invalid callsign
    UNKNOWN_COMMAND      = 0x07
    VIA                  = 0x08  # digipeater path error
    NOT_WHILE_CONNECTED  = 0x09
    NEED_MYCALL          = 0x0A
    NEED_MYSELCAL        = 0x0B  # AMTOR: MYSELCAL not set
    ALREADY_CONNECTED    = 0x0C
    NOT_WHILE_DISCONNECTED = 0x0D
    DIFFERENT_CONNECTS   = 0x0E
    TOO_MANY_OUTSTANDING = 0x0F  # too many unACKed packets
    CLOCK_NOT_SET        = 0x10
    NEED_ALL_NONE_YES_NO = 0x11
    NOT_IN_THIS_MODE     = 0x15


# ---------------------------------------------------------------------------
# Special ready-to-send frames
# ---------------------------------------------------------------------------

# Poll frame: SOH $4F 'G' 'G' ETB
# Host sends this to ask TNC for pending data (HPOLL ON mode).
# TNC replies: SOH $4F 'G' 'G' $00 ETB  (nothing pending)
#           or: one response block per poll when data is waiting.
# (TRM Section 4.4.1)
FRAME_POLL = bytes([SOH, CTL_TX_CMD, ord('G'), ord('G'), ETB])

# Recovery frame: SOH SOH $4F 'G' 'G' ETB
# Send after a serial link error to resynchronise the TNC.
# (TRM Section 4.1.6)
FRAME_RECOVERY = bytes([SOH, SOH, CTL_TX_CMD, ord('G'), ord('G'), ETB])

# HOST OFF frame: SOH $4F 'H' 'O' 'N' ETB
# Leaves Host Mode and returns TNC to verbose/human mode.
# (TRM Section 4.1.4)
FRAME_HOST_OFF = bytes([SOH, CTL_TX_CMD, ord('H'), ord('O'), ord('N'), ETB])


# ---------------------------------------------------------------------------
# Initialisation — command sequence BEFORE entering Host Mode
# (sent as plain ASCII text in verbose/terminal mode)
# ---------------------------------------------------------------------------

# Verbose-mode commands to prepare the TNC for Host Mode.
# (TRM Section 4.1.3 + DL3ECD implementation notes)
#
# Full correct sequence:
#   1. Send XON ($11)         — re-enable TNC output if XOFFed
#   2. Send CANLINE ($18)     — cancel any partial input line
#   3. Send COMMAND ($03)     — force TNC into COMMAND mode (Ctrl-C)
#   4. Send "* CR"            — autobaud trigger (TNC echoes banner)
#   5. Send "AWLEN 8 CR"      — 8-bit word length
#   6. Send "PARITY 0 CR"     — no parity
#   7. Send "RESTART CR"      — apply word-length/parity, TNC reboots
#   8. (wait _RESTART_DELAY)  — let TNC print banner after restart
#   9. Send XON + CANLINE + COMMAND again (TNC is back in verbose mode)
#  10. Send "HOST Y CR"       — switch to binary Host Mode
#
# Steps 1-3 are sent as raw bytes (not via this list) in serial_manager.
# This list covers steps 4-10 (the ASCII command phase).
HOSTMODE_INIT_CMDS: list[bytes] = [
    b"*",             # autobaud trigger — NO CR, just asterisk
                      # TNC responds with firmware banner (Ver. 7.1 etc.)
    b"AWLEN 8\r",     # 8-bit word length (required for Host Mode)
    b"PARITY 0\r",    # no parity
    b"RESTART\r",     # apply AWLEN/PARITY changes — TNC reboots
    b"HOST Y\r",      # activate Host Mode
]

# Raw control bytes sent BEFORE HOSTMODE_INIT_CMDS to put TNC in
# a defined state (flush input, force COMMAND mode)
HOSTMODE_PREAMBLE: bytes = (
    b"\x11"   # XON  — re-enable output
    b"\x18"   # CANLINE ($18 default) — cancel partial line
    b"\x03"   # COMMAND ($03 default) — Ctrl-C → COMMAND mode
)

# Optional: enable polling (TNC waits for FRAME_POLL before sending data)
HOSTMODE_HPOLL_ON  = b"HPOLL Y\r"
HOSTMODE_HPOLL_OFF = b"HPOLL N\r"


# ---------------------------------------------------------------------------
# Serial port defaults
# ---------------------------------------------------------------------------

class SerialDefaults:
    """Default serial port parameters for the PK-232MBX in Host Mode.

    The TNC supports 110, 300, 600, 1200, 2400, 4800, 9600 baud.
    Host Mode requires 8-bit, no-parity (AWLEN 8, PARITY 0).
    Hardware flow control (RTS/CTS) is recommended by the TRM.
    XON/XOFF must be disabled in Host Mode.
    """
    BAUD_RATES  = [9600, 4800, 2400, 1200, 600, 300, 110]  # fastest first
    BAUDRATE    = 9600
    BYTESIZE    = 8
    PARITY      = 'N'    # must match TNC PARITY 0 setting
    STOPBITS    = 1
    TIMEOUT     = 0.1    # seconds — keep short for responsive read loop
    XONXOFF     = False  # must be OFF in Host Mode
    RTSCTS      = True   # hardware handshake recommended by TRM


# ---------------------------------------------------------------------------
# Frame size limit
# ---------------------------------------------------------------------------

# Maximum data payload per frame (practical limit for PK-232MBX).
# The AX.25 I-field maximum is 256 bytes (TRM Appendix A).
MAX_DATA_LEN = 256


# ---------------------------------------------------------------------------
# Convenience: channel extraction from CTL byte
# ---------------------------------------------------------------------------

def ctl_channel(ctl: int) -> int:
    """Extract the channel number (0-9) from a TNC->host CTL byte.

    For $3x, $4x, $5x frames the lower nibble is the channel.
    For $4F, $3F, $2F, $5F frames the channel is not meaningful.

    Args:
        ctl: The raw CTL byte from a received frame.

    Returns:
        Channel number 0-15 (lower nibble of CTL).
    """
    return ctl & 0x0F


def ctl_type_range(ctl: int) -> int:
    """Return the upper nibble of CTL (the range identifier).

    E.g. 0x35 -> 0x30, 0x4F -> 0x40.

    Args:
        ctl: The raw CTL byte.

    Returns:
        Upper nibble as integer (0x20, 0x30, 0x40, or 0x50).
    """
    return ctl & 0xF0