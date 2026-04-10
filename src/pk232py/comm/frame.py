"""
pk232py.comm.frame
==================
Bauen und Parsen von AEA PK-232 Host Mode Frames.

Ein Frame hat folgende Struktur:
    [SOH] [CTL] [DATA mit DLE-Escaping] [ETB]

Diese Klasse arbeitet rein mit bytes-Objekten und hat keine
Abhängigkeit zum seriellen Port – dadurch ist sie leicht testbar.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from .constants import (
    SOH, ETB, DLE,
    ESCAPE_CHARS,
    FrameType, Port,
    MAX_DATA_LEN,
)


# ---------------------------------------------------------------------------
# Das Frame-Datenmodell
# ---------------------------------------------------------------------------

@dataclass
class HostFrame:
    """
    Repräsentiert einen dekodierten Host Mode Frame.

    Attribute:
        port     : Port-Nummer (Port.PORT1 oder Port.PORT2)
        frame_type: Frame-Typ (FrameType.CMD_RESPONSE, etc.)
        data     : Nutzdaten, bereits DLE-dekodiert (reine bytes)

    Beispiel:
        frame = HostFrame(port=Port.PORT1,
                          frame_type=FrameType.CMD_RESPONSE,
                          data=b"MYCALL OE3GAS\\r")
    """
    port: int
    frame_type: int
    data: bytes

    @property
    def ctl(self) -> int:
        """Rekonstruiert das CTL-Byte aus Port und Frame-Typ."""
        return (self.port & 0xF0) | (self.frame_type & 0x0F)

    def is_command_response(self) -> bool:
        return self.frame_type == FrameType.CMD_RESPONSE

    def is_connect_data(self) -> bool:
        return self.frame_type == FrameType.CONNECT_DATA

    def __repr__(self) -> str:
        port_str = "P1" if self.port == Port.PORT1 else "P2"
        return (
            f"HostFrame({port_str}, "
            f"type=0x{self.frame_type:02X}, "
            f"data={self.data!r})"
        )


# ---------------------------------------------------------------------------
# Frame bauen (PC → TNC)
# ---------------------------------------------------------------------------

def build_frame(ctl: int, data: bytes) -> bytes:
    """
    Baut einen vollständigen Host Mode Frame zum Senden.

    Schritt 1: DLE-Escaping auf data anwenden
    Schritt 2: [SOH] + [CTL] + [escaped_data] + [ETB] zusammensetzen

    Args:
        ctl  : Das CTL-Byte (Port + Frame-Typ kombiniert)
        data : Rohe Nutzdaten (noch ohne Escaping)

    Returns:
        Fertiger Frame als bytes, bereit zum Senden über serial.write()

    Beispiel:
        >>> build_frame(0x00, b"MYCALL OE3GAS\\r")
        b'\\x01\\x00MYCALL OE3GAS\\r\\x17'
    """
    if len(data) > MAX_DATA_LEN:
        raise ValueError(
            f"Datenlänge {len(data)} überschreitet Maximum {MAX_DATA_LEN}"
        )

    escaped = _dle_encode(data)
    return bytes([SOH, ctl]) + escaped + bytes([ETB])


def build_command_frame(cmd: str, port: int = Port.PORT1) -> bytes:
    """
    Hilfsfunktion: Baut einen Command-Frame aus einem ASCII-Befehlsstring.

    Args:
        cmd  : Befehl als String, z.B. "MYCALL OE3GAS"
               Das \\r wird automatisch angehängt.
        port : Port.PORT1 (Standard) oder Port.PORT2

    Returns:
        Fertiger Frame als bytes.

    Beispiel:
        >>> build_command_frame("MYCALL OE3GAS")
        b'\\x01\\x00MYCALL OE3GAS\\r\\x17'
    """
    ctl = port | FrameType.CMD_RESPONSE
    payload = cmd.encode("ascii") + b"\r"
    return build_frame(ctl, payload)


# ---------------------------------------------------------------------------
# Frame parsen (TNC → PC)
# ---------------------------------------------------------------------------

class FrameParser:
    """
    Zustandsbasierter Parser für eingehende Host Mode Frames.

    Der PK-232 schickt Bytes über die serielle Schnittstelle in einem
    kontinuierlichen Strom. Dieser Parser sammelt Bytes solange, bis ein
    vollständiger Frame erkannt wurde.

    Verwendung:
        parser = FrameParser()

        # In der Read-Schleife, Byte für Byte (oder in Chunks):
        for byte in incoming_bytes:
            frame = parser.feed(byte)
            if frame is not None:
                # vollständiger Frame empfangen!
                process(frame)

    Warum zustandsbasiert?
        Frames können über mehrere serial.read()-Aufrufe verteilt ankommen.
        Der Parser merkt sich, wo er gerade ist (State Machine).
    """

    # Interne Zustände der State Machine
    _ST_WAIT_SOH = 0   # Warte auf $01
    _ST_READ_CTL = 1   # Nächstes Byte ist CTL
    _ST_READ_DATA = 2  # Lese DATA bis ETB (mit DLE-Handling)
    _ST_DLE_ESC  = 3   # Letztes Byte war DLE, nächstes ist escaped

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        """Setzt den Parser in den Ausgangszustand zurück."""
        self._state = self._ST_WAIT_SOH
        self._ctl: int = 0
        self._buf: bytearray = bytearray()

    def feed(self, byte: int) -> Optional[HostFrame]:
        """
        Verarbeitet ein einzelnes Byte.

        Args:
            byte: Ganzzahl 0-255

        Returns:
            Ein HostFrame-Objekt wenn ein vollständiger Frame erkannt wurde,
            sonst None.
        """
        if self._state == self._ST_WAIT_SOH:
            if byte == SOH:
                self._state = self._ST_READ_CTL
                self._buf.clear()

        elif self._state == self._ST_READ_CTL:
            self._ctl = byte
            self._state = self._ST_READ_DATA

        elif self._state == self._ST_READ_DATA:
            if byte == ETB:
                # Frame vollständig!
                frame = self._finalize()
                self.reset()
                return frame
            elif byte == DLE:
                # Nächstes Byte ist escaped
                self._state = self._ST_DLE_ESC
            elif byte == SOH:
                # Unerwartetes SOH → Frame-Neustart (Resync)
                self._buf.clear()
                self._state = self._ST_READ_CTL
            else:
                self._buf.append(byte)

        elif self._state == self._ST_DLE_ESC:
            # DLE-Dekodierung: XOR mit $20 liefert Original-Byte zurück
            original = byte ^ 0x20
            self._buf.append(original)
            self._state = self._ST_READ_DATA

        return None

    def feed_bytes(self, data: bytes) -> list[HostFrame]:
        """
        Verarbeitet mehrere Bytes auf einmal (z.B. aus serial.read()).

        Returns:
            Liste aller vollständig erkannten Frames (kann leer sein).
        """
        frames = []
        for b in data:
            frame = self.feed(b)
            if frame is not None:
                frames.append(frame)
        return frames

    def _finalize(self) -> HostFrame:
        """Erstellt ein HostFrame aus dem aktuellen Puffer."""
        port = self._ctl & 0xF0
        frame_type = self._ctl & 0x0F
        return HostFrame(
            port=port,
            frame_type=frame_type,
            data=bytes(self._buf),
        )


# ---------------------------------------------------------------------------
# DLE-Encoding (intern)
# ---------------------------------------------------------------------------

def _dle_encode(data: bytes) -> bytes:
    """
    Wendet DLE-Escaping auf einen Datenpuffer an.

    Jedes Byte aus ESCAPE_CHARS {SOH=$01, ETB=$17, DLE=$10}
    wird ersetzt durch: DLE ($10) + (byte XOR $20)

    Beispiele:
        $01 → $10 $21
        $17 → $10 $37
        $10 → $10 $30
    """
    result = bytearray()
    for byte in data:
        if byte in ESCAPE_CHARS:
            result.append(DLE)
            result.append(byte ^ 0x20)
        else:
            result.append(byte)
    return bytes(result)
