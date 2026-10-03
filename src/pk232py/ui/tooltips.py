# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Central tooltip registry for all PK232PY screens.

Usage:
    from pk232py.ui.tooltips import apply_tooltips
    apply_tooltips(self)   # at the end of __init__, after all widgets are built

apply_tooltips() maps widget *attribute names* (e.g. self.btn_send) to tooltip
texts. Unknown attributes are silently skipped — safe to call on any screen,
including screens that only have a subset of the listed widgets.

------------------------------------------------------------------------------
LERNMODUS — three non-obvious design points
------------------------------------------------------------------------------

1. WHY hasattr/isinstance INSTEAD OF A BARE getattr.
   apply_tooltips() walks a dict of attribute names and only calls setToolTip()
   when getattr() returns a real QWidget. Screens share one registry but each
   has only a subset of the widgets, so most keys miss on any given screen.
   isinstance(w, QWidget) makes those misses harmless without try/except, and
   also guards against an attribute that happens to be a non-widget value.

2. WHY MACRO BUTTONS ARE NOT IN THE REGISTRY.
   Macro buttons carry dynamic, user-defined text and get their tooltips from
   apply_macro_tooltips() in opmode_rtty_base.py. There is no fixed attribute
   name to key them on (they live in a list, screen.macro_buttons[i]), so the
   central registry deliberately leaves them alone — the two systems do not
   overlap and apply_tooltips() never overwrites a macro tooltip.

3. WHY SOME WIDGETS LIVE IN SCREEN_TOOLTIPS, NOT THE GLOBAL DICT.
   A few attribute names are REUSED across screens with DIFFERENT meanings —
   e.g. btn_rxrev reverses RTTY mark/space tones but flips the FAX image;
   btn_lock is Morse sync vs FAX start; btn_clear clears the FAX image vs the
   MHEARD list. A single flat dict keyed by attribute name cannot tell them
   apart, so those collisions are resolved in SCREEN_TOOLTIPS, keyed by the
   widget's class name. The global pass runs first; the per-class pass runs
   second and overrides the colliding keys with the screen-correct text.
   (btn_connect/btn_disconnect used to be exactly this kind of collision,
   AX.25 Packet vs PACTOR — P42 removed Packet's Connect/Disconnect buttons
   entirely, so PactorScreen is now the sole owner of these two names and
   its SCREEN_TOOLTIPS entry is the only one ever actually applied; no
   global fallback for them is needed any more.)

   (The AMTOR screen has NO btn_wideshft / btn_mopt: WIDESHFT is an FSK-only
   control for Baudot/ASCII RTTY, and AMTOR runs at a fixed 100 Bd, so neither
   key applies there — they are simply absent and skipped.)
"""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QSizePolicy


# ---------------------------------------------------------------------------
# Global registry — keyed by the ACTUAL widget attribute name.
# Where a name is reused with a different meaning on another screen, this holds
# the majority/default meaning and SCREEN_TOOLTIPS overrides the minority.
# ---------------------------------------------------------------------------

# P80a: the controls of the Morse ID / MID (mnemonic MI) are greyed out; MI is
# MFILTER (Testplan T115), no Morse ID mnemonic is known.
_MI_UNVERIFIED = "Host mnemonic unverified - MI is MFILTER (T115)"

TOOLTIPS: dict[str, str] = {

    # ------------------------------------------------------------------
    # General — appear on multiple screens
    # ------------------------------------------------------------------
    "le_mycall":   "My callsign.\nUsed as the source address in all transmitted frames.",
    "le_dest":     "Destination callsign to connect to.\nEnter callsign with optional SSID, e.g. OE3XYZ or OE3XYZ-9.",
    "le_unproto":  "Unproto destination and digipeater path.\nExamples:  CQ   CQ VIA RELAY   CQ VIA OE3XNR-8",
    "lbl_status":  "Current link state: STBY / CALLING / CONNECTED / DISCONNECTED.",

    "btn_send":      "SEND — activate PTT.\nChars typed in the TX window are sent character by character.",
    "btn_receive":   "RECEIVE — drop PTT, return to receive.\nStops transmission and returns to receive mode.",
    "btn_clear_tx":  "Clear TX — abort transmission and discard the TX buffer.",
    "btn_clear_rx":  "Clear RX — erase the receive display.",
    "btn_edit_macros": "Edit Macros — open the macro editor to define shortcut texts.",

    # Shared toggle buttons (RTTY / Morse — NOT AMTOR for wideshft).
    # btn_rxrev here is the RTTY meaning; FaxScreen overrides it (see below).
    "btn_rxrev":    "RXREV — reverse RX polarity.\nSwaps mark/space tones on receive. Use when the received signal is inverted.",
    "btn_txrev":    "TXREV — reverse TX polarity.\nSwaps mark/space tones on transmit. Use when your transmitted signal appears inverted at the other end.",
    "btn_usos":     "USOS — Unshift On Space.\nWhen ON, a space character forces a return to LTRS (letters) mode.\nPrevents the teleprinter from getting stuck in FIGS after a missed LTRS shift.",
    "btn_wideshft": "WIDESHFT — wide shift mode.\nSwitches between standard 170 Hz RTTY shift and wide 850 Hz shift.\nUse 850 Hz for older/military RTTY stations that use wide shift.",
    "btn_eas":      "EAS — Echo As Sent.\nDisplays transmitted characters in the RX window only after they are confirmed sent.",

    # ITA-2 shift buttons (Baudot / AMTOR). Actual attrs: btn_figs / btn_chars.
    "btn_figs":  "Switch FIGS — force ITA-2 figure shift.\nSends the FIGS character to switch to numbers/symbols mode.",
    "btn_chars": "Switch LTRS — force ITA-2 letter shift.\nSends the LTRS character to switch back to letters mode.",

    # ------------------------------------------------------------------
    # Packet (HF Packet / VHF Packet)
    # P42: Connect/Disconnect have no buttons of their own any more — a
    # callsign is typed directly into a free channel chip (see ChannelChip
    # in packet_screen.py); btn_connect/btn_disconnect now belong to
    # PactorScreen alone (SCREEN_TOOLTIPS below).
    # ------------------------------------------------------------------
    "btn_unproto":    "Unproto — transmit UI frames without a connection (broadcast).\nSwitches to the MON view; text typed there goes out via the lowest free channel.",
    "btn_maildrop":   "MailDrop — access the TNC built-in mailbox.\nLogs in to the MailDrop node.",

    "combo_hbaud":   "HBAUD — set the packet modem baud rate.\n300 Bd = HF packet (Bell 103)  |  1200 Bd = VHF packet (Bell 202)  |  2400 Bd = high-speed VHF.",
    "combo_monitor": "Monitor level — which frame types are shown in the RX window.\n0=off  1=UI only  2=+I frames  3=+connect/disconnect  4=+ack  5=+raw  6=all",

    "btn_passall":   "PASSALL — receive all frames regardless of CRC errors.\nNormally the TNC discards frames with bad CRC. PASSALL passes them through for monitoring.",
    "btn_mrpt":      "MRPT — Monitor Repeat.\nAlso displays frames that have been digipeated (relayed) through intermediate stations.",
    "btn_mid":       _MI_UNVERIFIED,   # P80a: MI is MFILTER, nothing is sent
    "btn_squelch":   "SQUELCH — suppress duplicate frames in the monitor display.\nPrevents the same frame from appearing multiple times when heard via multiple paths.",

    "btn_aprs":      "APRS — toggle APRS decode mode.\nDisplays received UI frames as APRS: position, telemetry etc.\nDisplay-only function; raw mode is preserved in the buffer.",

    # ------------------------------------------------------------------
    # AMTOR
    # ------------------------------------------------------------------
    "btn_arq":    "ARQ — Mode A, Automatic ReQuest for reception.\nTwo-station handshaking.\nRequires the 4-character SELCAL of the destination station.",
    "btn_fec":    "FEC — Mode B, Forward Error Correction broadcast.\nSends to all stations; no handshaking, no error correction confirmation.\nUse for CQ calls or roundtables.",
    "btn_selfec": "SELFEC — Selective FEC broadcast.\nOnly received by stations whose SELCAL matches your MYSELCAL.\nUseful for directed broadcasts without establishing a full ARQ link.",
    "btn_alist":  "ALIST — AMTOR Listen mode (Mode A Listen).\nMonitors ongoing ARQ sessions between other stations without connecting.",
    # btn_stby here is the AMTOR meaning; PactorScreen overrides it.
    "btn_stby":   "STBY — return TNC to AMTOR standby.\nAborts transmission immediately; does NOT flush the TNC TX buffer (use Clear TX for that).",
    "btn_achg":   "ACHG — ARQ channel change / break-in.\nAs IRS (receiving station), forces a role swap so you can transmit.\nUse sparingly — interrupts the other station's transmission.",

    "btn_rfec":   "RFEC — receive FEC while in ARQ standby.\nWhen ON, the TNC also decodes FEC/SELFEC broadcasts while waiting for an ARQ connect request.",
    "btn_srxall": "SRxAll — receive all SELFEC frames regardless of SELCAL.\nNormally only SELFEC frames matching your SELCAL are shown. SRxAll disables this filter.",
    "btn_arxtor": "ARXTOR — automatic AMTOR/PACTOR mode detection.\nWhen ON, the TNC automatically recognises and switches between AMTOR and PACTOR modes.\n(Requires PACTOR firmware option.)",
    "btn_hold":   "HOLD — hold the TX buffer instead of releasing it on changeover.\nKeeps unsent text buffered across an ACHG role swap; release to continue sending.",
    "btn_pactor_listen": "PACTOR Listen — monitor PACTOR transmissions without connecting.\nAuto-detects and follows a PACTOR signal in listen mode.\n(Requires PACTOR firmware option.)",

    # ------------------------------------------------------------------
    # Baudot RTTY / ASCII RTTY
    # ------------------------------------------------------------------
    "combo_rbaud":    "RBAUD — receive baud rate.\nCommon values: 45 Bd (standard RTTY), 50 Bd (European).",

    # ------------------------------------------------------------------
    # CW / Morse
    # btn_lock here is the Morse meaning; FaxScreen overrides it.
    # ------------------------------------------------------------------
    "sb_mspeed":  "MSPEED — Morse sending speed in words per minute.\nRange: 5–99 WPM. The TNC keys at this speed regardless of typing speed.",
    "sb_mweight": "MWEIGHT — dot/dash weight.\nAdjusts the ratio of key-down to key-up time. 50 = standard; >50 = heavier dots/dashes.",
    "sb_mid":     _MI_UNVERIFIED,
    "btn_mid_down": _MI_UNVERIFIED,
    "btn_mid_up":   _MI_UNVERIFIED,
    "btn_lock":   "LOCK — force Morse receive synchronisation.\nOne-shot command: locks the TNC decoder to the incoming signal's timing.",
    "btn_wordout": "WORDOUT — send whole words instead of character by character.\nThe TNC buffers until a space, then keys the complete word at once.",

    # ------------------------------------------------------------------
    # PACTOR (unique attribute names — connect/disconnect/stby in SCREEN_TOOLTIPS)
    # ------------------------------------------------------------------
    "btn_ptlist":  "PTLIST — request the PACTOR BBS message list from the connected station.",
    "btn_ptsend":  "PTSEND — send a file/message to the connected PACTOR BBS.",
    "btn_pt200":   "PT200 — PACTOR Level 2 (200 Bd FSK) enable/disable.\nWhen ON, the TNC negotiates PACTOR-2 with compatible stations for higher throughput.\n(Requires PACTOR firmware option.)",
    "btn_pthuff":  "PTHUFF — PACTOR Huffman compression enable/disable.\nHuffman coding compresses ASCII text before transmission for higher effective throughput.\n(Requires PACTOR firmware option.)",
    "btn_ptround": "PTROUND — PACTOR round-trip time optimisation.\nAdjusts ARQ timing for long-path HF links where propagation delay is significant.",
    "le_myptcall": "MYPTCALL — my PACTOR callsign.\nThe callsign announced during PACTOR connects. Usually same as MYCALL.",

    # ------------------------------------------------------------------
    # NAVTEX
    # ------------------------------------------------------------------
    "le_navmsg": (
        "NAVMSG — NAVTEX message class filter.\n"
        "Filter which message classes are displayed.\n"
        "ALL = show all  |  NONE = suppress all  |  e.g. A,B,D\n"
        "Classes A, B, D are mandatory (safety of navigation)."
    ),
    "le_navstn": (
        "NAVSTN — NAVTEX station filter.\n"
        "Filter which transmitter station IDs are shown.\n"
        "ALL = show all  |  NONE = suppress all  |  e.g. A,P,S"
    ),

    # ------------------------------------------------------------------
    # Signal / SIAM   (actual analyse button attr: btn_neue_analyse)
    # ------------------------------------------------------------------
    "btn_neue_analyse": (
        "Analyse — capture a signal sample and identify the modulation type.\n"
        "The TNC analyses the audio and reports the most likely digital mode."
    ),
}


# ---------------------------------------------------------------------------
# Per-screen overrides — keyed by widget class name, then actual attribute name.
# These resolve attribute-name collisions: same name, different meaning per
# screen. Applied AFTER the global pass, so they win for the colliding keys.
# ---------------------------------------------------------------------------

SCREEN_TOOLTIPS: dict[str, dict[str, str]] = {

    "PactorScreen": {
        "btn_connect":    "Connect — initiate a PACTOR ARQ connection to the destination callsign.\nEnter the callsign in the Dest field first.",
        "btn_disconnect": "Disconnect — terminate the PACTOR connection and return to standby.",
        "btn_stby":       "STBY — return TNC to PACTOR standby without a formal disconnect.",
    },

    "FaxScreen": {
        # Actual attrs: btn_lock (Start/LOCK), btn_stop, btn_clear /
        # btn_clear_image, btn_rxrev, btn_faxneg, combo_fspeed, and the two
        # sliders _lh_slider (line spacing) / _smooth_slider (smoothing).
        "btn_lock":        "Start / LOCK — start FAX reception or force synchronisation.\nLOCK forces the decoder to lock onto the current signal phase.",
        "btn_stop":        "Stop — freeze the current image and stop accepting new pixel data.\nThe image remains on screen. Press Start or LOCK to resume reception.",
        "btn_clear":       "Clear Image — erase the current image and re-enable reception.",
        "btn_clear_image": "Clear Image — erase the current image and re-enable reception.",
        "btn_faxneg":      "FAXNEG — invert the displayed image (display-only, no TNC command).\nDoes NOT affect reception — toggles black/white for viewing convenience.",
        "btn_rxrev":       "RXREV — reverse the FAX signal polarity on receive.\nUse when the image appears as a white-on-black negative.",
        "combo_fspeed":    "FSPEED — FAX drum speed: lines per minute.\nStandard weather fax: 120 LPM. Some stations use 60 LPM or 240 LPM.",
        "_lh_slider":      "Line spacing — fine-tune the vertical pixel aspect ratio.\nDefault = 1.0 (120/72 dpi correction applied automatically).",
        "_smooth_slider":  "Smoothing — non-destructive anti-halftoning filter strength.\n0 = raw bilevel image  |  higher = progressively smoother.",
    },

    "MheardPanel": {
        "btn_refresh": "Refresh — request the MHEARD list from the TNC (mnemonic MH).",
        "btn_clear":   "Clear — erase the MHEARD list locally.",
    },
}


def apply_tooltips(widget: QWidget) -> None:
    """Apply all matching tooltips to *widget*'s attributes.

    Two passes:
      1. Global TOOLTIPS — keyed by attribute name.
      2. SCREEN_TOOLTIPS[type(widget).__name__] — per-class overrides that win
         over the global pass for collided attribute names.

    For each key, getattr(widget, key, None) is looked up and setToolTip() is
    called only if the attribute exists and is a QWidget. Unknown keys are
    silently skipped — safe to call on any screen.

    Call at the end of each screen's __init__(), after all widgets are built::

        from pk232py.ui.tooltips import apply_tooltips
        ...
        apply_tooltips(self)

    P55.E: also asserts an Expanding vertical (and horizontal) size
    policy on *widget* itself. This call is already the one place every
    opmode screen's __init__() reaches (RttyBaseScreen, AmtorScreen,
    PactorScreen, MorseScreen, PacketBaseScreen, NavtexScreen,
    SignalScreen, FaxScreen each call it exactly once) - piggybacking the
    size-policy fix onto it, per the spec's own explicit ask for a
    single touch point, avoids adding a second near-identical call to
    all eight files just to keep the two concerns in separate-looking
    functions. A plain QWidget defaults to Preferred/Preferred, which
    still happened to fill the whole window correctly in every
    configuration checked while investigating a reported "empty area
    below the macro buttons" (26.09.2026) - so this is defensive
    hardening for whatever configuration that screenshot was actually
    taken in, not a fix for a reproduced code bug: it guarantees the
    screen always claims whatever height _opmode_stack (a
    QStackedWidget) gives it, rather than only its sizeHint(), so each
    screen's own rx_display (or, for Packet, the RX/TX splitter)
    stretch=1 has the full available height to distribute and the
    macro row - the last, unstretched item in every screen's own
    QVBoxLayout - ends up anchored at the bottom rather than floating
    above unclaimed space.
    """
    widget.setSizePolicy(
        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
    )

    def _set(mapping: dict[str, str]) -> None:
        for attr, tip in mapping.items():
            w = getattr(widget, attr, None)
            if isinstance(w, QWidget):
                w.setToolTip(tip)

    _set(TOOLTIPS)
    _set(SCREEN_TOOLTIPS.get(type(widget).__name__, {}))
