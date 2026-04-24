#!/usr/bin/env python3
"""
pk232_debug.py  –  Serielle Diagnose für AEA PK-232 / PK-232MBX
================================================================
Zeigt alle gesendeten und empfangenen Bytes als HEX + ASCII.
Erlaubt schrittweise Initialisierung mit konfigurierbaren Delays.

Verwendung:
    python pk232_debug.py

Voraussetzung:
    pip install pyserial
"""

import serial
import serial.tools.list_ports
import time
import sys
import threading


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def hex_dump(label: str, data: bytes) -> None:
    """Gibt Bytes als HEX + druckbaren ASCII-Zeichen aus."""
    if not data:
        return
    hex_part   = " ".join(f"{b:02X}" for b in data)
    ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {label:4s}  {hex_part:<48s}  |{ascii_part}|")


def list_ports() -> None:
    """Listet verfügbare COM-Ports."""
    ports = serial.tools.list_ports.comports()
    if not ports:
        print("  (keine Ports gefunden)")
        return
    for p in sorted(ports):
        print(f"  {p.device:15s}  {p.description}")


def ask(prompt: str, default: str) -> str:
    """Fragt den Benutzer, gibt Default zurück bei leerer Eingabe."""
    val = input(f"{prompt} [{default}]: ").strip()
    return val if val else default


def ask_bool(prompt: str, default: bool) -> bool:
    """Fragt nach einem Boolean-Wert (True/False)."""
    default_str = "True" if default else "False"
    val = ask(prompt, default_str).lower()
    return val in ("true", "1", "yes", "ja")


# ---------------------------------------------------------------------------
# Reader-Thread
# ---------------------------------------------------------------------------

class SerialReader(threading.Thread):
    """Liest kontinuierlich vom Port und gibt empfangene Bytes aus."""

    def __init__(self, ser: serial.Serial):
        super().__init__(daemon=True)
        self._ser    = ser
        self._active = True

    def stop(self):
        self._active = False

    def run(self):
        while self._active:
            try:
                waiting = self._ser.in_waiting
                if waiting:
                    data = self._ser.read(waiting)
                    hex_dump("RX", data)
                else:
                    time.sleep(0.05)
            except serial.SerialException:
                break


# ---------------------------------------------------------------------------
# Sende-Hilfsfunktionen
# ---------------------------------------------------------------------------

def send(ser: serial.Serial, data: bytes, label: str = "TX") -> None:
    """Sendet Bytes und gibt sie aus."""
    hex_dump(label, data)
    ser.write(data)
    ser.flush()


def send_text(ser: serial.Serial, text: str) -> None:
    """Sendet einen Text-String (ASCII)."""
    send(ser, text.encode("ascii"), "TX")


# ---------------------------------------------------------------------------
# Port öffnen
# ---------------------------------------------------------------------------

def open_port(port: str, baud: int, rts: bool, dtr: bool, xonxoff: bool) -> serial.Serial:
    """Öffnet den seriellen Port mit den angegebenen Einstellungen."""
    ser = serial.Serial(
        port     = port,
        baudrate = baud,
        bytesize = serial.EIGHTBITS,
        parity   = serial.PARITY_NONE,
        stopbits = serial.STOPBITS_ONE,
        timeout  = 0,        # non-blocking read
        xonxoff  = xonxoff,
        rtscts   = False,
        dsrdtr   = False,
    )
    # RTS/DTR NACH dem Öffnen explizit setzen
    ser.rts = rts
    ser.dtr = dtr
    return ser


# ---------------------------------------------------------------------------
# Initialisierungssequenzen
# ---------------------------------------------------------------------------

def init_verbose_mode(ser: serial.Serial, delay: float) -> None:
    """Sendet '*\\r' um das TNC-Banner zu erhalten (Verbose/Terminal-Mode)."""
    print("\n--- Sende '*\\r' (Banner-Anforderung) ---")
    send_text(ser, "*\r")
    time.sleep(delay)


def init_host_mode(ser: serial.Serial, delay: float) -> None:
    """
    Vollständige Host-Mode-Initialisierungssequenz laut AEA Technical Manual:
      XON + CANLINE + COMMAND + 'HOST Y\\r'
    """
    print("\n--- Host Mode Initialisierung ---")

    # Schritt 1: XON ($11) + CANLINE ($18) + COMMAND ($03) + 'HOST Y\r'
    print("Schritt 1: XON + CANLINE + COMMAND + 'HOST Y\\r'")
    preamble = bytes([0x11, 0x18, 0x03])
    host_cmd = b"HOST Y\r"
    send(ser, preamble + host_cmd)
    time.sleep(delay)

    # Schritt 2: SOH ($01) senden
    print("Schritt 2: SOH ($01) senden")
    send(ser, bytes([0x01]))
    time.sleep(delay)

    # Schritt 3: Recovery-Sequenz $01 $4F $47 $47 $17
    print("Schritt 3: Recovery-Sequenz $01 $4F $47 $47 $17")
    recovery = bytes([0x01, 0x4F, 0x47, 0x47, 0x17])
    send(ser, recovery)
    time.sleep(delay * 2)


def init_host_exit(ser: serial.Serial) -> None:
    """Verlässt den Host Mode: $01 $4F $48 $4F $4E $17"""
    print("\n--- Verlasse Host Mode ---")
    exit_seq = bytes([0x01, 0x4F, 0x48, 0x4F, 0x4E, 0x17])
    send(ser, exit_seq)


# ---------------------------------------------------------------------------
# Hauptmenü
# ---------------------------------------------------------------------------

MENU = """
╔══════════════════════════════════════════════╗
║         PK-232 Seriell-Diagnose              ║
╠══════════════════════════════════════════════╣
║  1  Sende '*\\r'  (Banner/Verbose-Test)       ║
║  2  Host-Mode Initialisierung                ║
║  3  Host-Mode verlassen                      ║
║  4  Manuell HEX-Bytes senden                 ║
║  5  Manuell Text senden                      ║
║  6  RTS/DTR/XON Status anzeigen              ║
║  7  Port neu öffnen (andere Einstellungen)   ║
║  8  Empfangspuffer leeren                    ║
║  q  Beenden                                  ║
╚══════════════════════════════════════════════╝
"""


def show_status(ser: serial.Serial) -> None:
    print(f"  RTS={ser.rts}  DTR={ser.dtr}  XON/XOFF={ser.xonxoff}")


def toggle_rts_dtr(ser: serial.Serial) -> None:
    show_status(ser)
    choice = input("  Was umschalten? [rts/dtr/beide/nichts]: ").strip().lower()
    if "rts" in choice or "beide" in choice:
        ser.rts = not ser.rts
        print(f"  RTS jetzt: {ser.rts}")
    if "dtr" in choice or "beide" in choice:
        ser.dtr = not ser.dtr
        print(f"  DTR jetzt: {ser.dtr}")


def reopen_port(ser: serial.Serial, reader: SerialReader) -> tuple:
    """Schließt und öffnet den Port neu mit neuen Einstellungen."""
    reader.stop()
    port = ser.port
    baud = ser.baudrate
    ser.close()
    print(f"\nPort {port} geschlossen.")

    new_rts     = ask_bool("  RTS beim Öffnen", False)
    new_dtr     = ask_bool("  DTR beim Öffnen", False)
    new_xon     = ask_bool("  XON/XOFF Flow Control", True)
    delay_after = float(ask("  Warten nach Open (Sek.)", "2.0"))

    new_ser = open_port(port, baud, new_rts, new_dtr, new_xon)
    print(f"Port {port} wieder geöffnet.  "
          f"RTS={new_ser.rts}  DTR={new_ser.dtr}  XON/XOFF={new_ser.xonxoff}")
    time.sleep(delay_after)

    new_reader = SerialReader(new_ser)
    new_reader.start()
    return new_ser, new_reader


def send_hex_manual(ser: serial.Serial) -> None:
    """Sendet manuell eingegebene HEX-Bytes."""
    raw = input("  HEX-Bytes eingeben (z.B. 01 4F 47 47 17): ").strip()
    if not raw:
        return
    try:
        data = bytes(int(x, 16) for x in raw.split())
        send(ser, data)
    except ValueError as e:
        print(f"  Fehler: {e}")


def send_text_manual(ser: serial.Serial) -> None:
    """Sendet manuell eingegebenen Text (\\r und \\n werden expandiert)."""
    text = input("  Text eingeben (\\r = CR, \\n = LF): ")
    text = text.replace("\\r", "\r").replace("\\n", "\n")
    send_text(ser, text)


# ---------------------------------------------------------------------------
# Einstiegspunkt
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  PK-232 Serielle Diagnose")
    print("=" * 60)

    # Port auswählen
    print("\nVerfügbare Ports:")
    list_ports()
    port = ask("\nCOM-Port", "COM16")
    if port.isdigit():
        port = f"COM{port}"
    baud = int(ask("Baudrate", "9600"))

    # Verbindungsparameter
    print("\nVerbindungsparameter:")
    print("  Hinweis: PuTTY verwendet XON/XOFF=True, RTS/DTR=False")
    rts        = ask_bool("  RTS beim Öffnen setzen", False)
    dtr        = ask_bool("  DTR beim Öffnen setzen", False)
    xon        = ask_bool("  XON/XOFF Flow Control (wie PuTTY)", True)
    delay_open = float(ask("  Warten nach Open (Sek.)", "2.0"))
    delay_cmd  = float(ask("  Delay zwischen Befehlen (Sek.)", "0.5"))

    # Port öffnen
    try:
        ser = open_port(port, baud, rts, dtr, xon)
    except serial.SerialException as e:
        print(f"\nFEHLER: Port konnte nicht geöffnet werden: {e}")
        sys.exit(1)

    print(f"\nPort {port} geöffnet.  "
          f"Baud={baud}  RTS={ser.rts}  DTR={ser.dtr}  XON/XOFF={ser.xonxoff}")
    print(f"Warte {delay_open:.1f}s nach dem Öffnen ...")
    time.sleep(delay_open)

    # Reader-Thread starten
    reader = SerialReader(ser)
    reader.start()

    print("\nEmpfang läuft. Alle RX-Daten werden als HEX angezeigt.")
    print("Drücke Enter für das Menü.\n")

    # Hauptschleife
    while True:
        print(MENU)
        choice = input("Wahl: ").strip().lower()

        if choice == "1":
            init_verbose_mode(ser, delay_cmd)

        elif choice == "2":
            init_host_mode(ser, delay_cmd)

        elif choice == "3":
            init_host_exit(ser)

        elif choice == "4":
            send_hex_manual(ser)

        elif choice == "5":
            send_text_manual(ser)

        elif choice == "6":
            show_status(ser)

        elif choice == "7":
            ser, reader = reopen_port(ser, reader)

        elif choice == "8":
            ser.reset_input_buffer()
            print("  Empfangspuffer geleert.")

        elif choice == "q":
            break

        else:
            print("  Unbekannte Eingabe.")

        time.sleep(0.2)  # kurz warten damit Reader-Output erscheint

    reader.stop()
    ser.close()
    print(f"\nPort {port} geschlossen. Auf Wiedersehen!")


if __name__ == "__main__":
    main()