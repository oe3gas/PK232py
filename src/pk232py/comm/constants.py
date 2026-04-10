"""
pk232py.comm.constants
======================
Host Mode Protokoll-Konstanten für den AEA PK-232/PK-232MBX.

Quelle: AEA PK-232 Technical Reference Manual, Kapitel 4 (Host Mode)
        sowie DL3ECD Hostmode-Dokumentation.

Alle numerischen Werte sind Hex-Werte wie im Manual angegeben.
"""

# ---------------------------------------------------------------------------
# Frame-Delimiter
# ---------------------------------------------------------------------------

SOH = 0x01   # Start of Header  – beginnt jeden Frame
ETB = 0x17   # End of Transmission Block – beendet jeden Frame
DLE = 0x10   # Data Link Escape – Escape-Präfix für Sonderzeichen in DATA

# Zeichen, die im DATA-Feld escaped werden müssen:
ESCAPE_CHARS = {SOH, ETB, DLE}


# ---------------------------------------------------------------------------
# Frame-Typen (untere 4 Bits des CTL-Bytes)
# ---------------------------------------------------------------------------

class FrameType:
    """
    Frame-Typ-Konstanten.

    Das CTL-Byte eines Host-Mode-Frames ist aufgeteilt in:
      Bits 7-4: Port-Nummer (0 = Port 1, 1 = Port 2)
      Bits 3-0: Frame-Typ

    Beispiel: CTL = 0x20 → Port 2, Typ CONSTAT_RESPONSE
    """
    CMD_RESPONSE   = 0x00  # Befehl an TNC / Antwort vom TNC
    LINK_DATA      = 0x01  # Unverbundene Monitordaten vom TNC
    CONNECT_DATA   = 0x02  # Daten aus aktiver Verbindung
    DISCONNECT     = 0x03  # Verbindung getrennt (Notification)
    CONNECT_STATUS = 0x04  # Verbindungsstatus-Änderung
    DATA_RECEIVED  = 0x05  # Daten für den Host (vom TNC gepusht)
    CONSTAT_RESP   = 0x06  # Antwort auf CONSTAT-Kommando


# ---------------------------------------------------------------------------
# Port-Nummern (obere 4 Bits des CTL-Bytes, geshiftet)
# ---------------------------------------------------------------------------

class Port:
    """TNC-Port-Nummern (Bits 7-4 im CTL-Byte)."""
    PORT1 = 0x00   # Standard-Port (Radio 1)
    PORT2 = 0x10   # Zweiter Port (Radio 2, falls vorhanden)


# ---------------------------------------------------------------------------
# Häufig verwendete vollständige CTL-Werte
# ---------------------------------------------------------------------------

CTL_CMD_PORT1  = Port.PORT1 | FrameType.CMD_RESPONSE   # 0x00
CTL_CMD_PORT2  = Port.PORT2 | FrameType.CMD_RESPONSE   # 0x10
CTL_DATA_PORT1 = Port.PORT1 | FrameType.CONNECT_DATA   # 0x02
CTL_DATA_PORT2 = Port.PORT2 | FrameType.CONNECT_DATA   # 0x12


# ---------------------------------------------------------------------------
# Host Mode Ein-/Ausschalten
# ---------------------------------------------------------------------------

# Sequenz zum Einschalten des Host Mode (als ASCII-Text über Terminal):
# Erst den TNC in einen definierten Zustand bringen, dann HOST Y\r
HOSTMODE_ENTER_CMDS = [
    b"\x13",          # XOFF: sicherstellen, dass kein Datenstrom läuft
    b"CANLINE\r",     # laufende Eingabe abbrechen
    b"COMMAND\r",     # sicherstellen, dass TNC im CMD-Modus ist
    b"HOST Y\r",      # Host Mode aktivieren
]

# Frame zum Ausschalten des Host Mode (binärer Frame, nicht ASCII!):
# SOH $4F H O N ETB  → "HON" = Host OFF
HOSTMODE_EXIT_FRAME = bytes([SOH, 0x4F, ord('H'), ord('O'), ord('N'), ETB])

# Frame für HPOLL (Daten abfragen, wenn HPOLL ON):
# SOH $4F G G ETB
HOSTMODE_POLL_FRAME = bytes([SOH, 0x4F, ord('G'), ord('G'), ETB])

# Recovery-Frame (bei hängendem Host Mode):
# SOH SOH $4F G G ETB
HOSTMODE_RECOVERY_FRAME = bytes([SOH, SOH, 0x4F, ord('G'), ord('G'), ETB])


# ---------------------------------------------------------------------------
# Serielle Verbindungsparameter (Defaults)
# ---------------------------------------------------------------------------

class SerialDefaults:
    """Standard-Parameter für die serielle Verbindung zum PK-232MBX."""
    BAUDRATE    = 9600    # Typisch für Host Mode; auch 4800, 19200 möglich
    BYTESIZE    = 8       # 8 Datenbits (im Host Mode immer 8-bit!)
    PARITY      = 'N'     # Keine Parität (PARITY 0 am TNC)
    STOPBITS    = 1
    TIMEOUT     = 0.1     # Sekunden – kurz halten für reaktive Read-Schleife
    XONXOFF     = False   # Kein Software-Handshake im Host Mode
    RTSCTS      = True    # Hardware-Handshake (RTS/CTS) wird empfohlen


# ---------------------------------------------------------------------------
# Maximale Frame-Größen
# ---------------------------------------------------------------------------

MAX_DATA_LEN = 256   # Maximale Nutzdatenlänge pro Frame (MBX-Limit)
