"""
pk232py.comm.serial_manager
============================
Kern-Kommunikationsschicht für den AEA PK-232/PK-232MBX.

Verantwortlichkeiten:
  1. Seriellen Port öffnen und schließen
  2. Host Mode aktivieren und deaktivieren
  3. Frames senden (build_frame + serial.write)
  4. Frames empfangen in einem Hintergrund-Thread (serial.read → FrameParser)
  5. Empfangene Frames über Qt-Signals an die UI weitergeben

Threading-Modell:
  ┌─────────────┐    signal/slot    ┌──────────────────────┐
  │  Qt UI      │ ←────────────── │  SerialManager       │
  │  (Main)     │                  │  (Main Thread)       │
  └─────────────┘                  └──────────────────────┘
                                            ↑ emit()
                                   ┌──────────────────────┐
                                   │  _ReaderThread       │
                                   │  (Hintergrund)       │
                                   │  liest serial.read() │
                                   │  → FrameParser       │
                                   └──────────────────────┘

Warum ein eigener Thread?
  serial.read() blockiert, bis Daten ankommen. Wenn wir das im Main Thread
  täten, würde die UI einfrieren. Der Reader-Thread läuft im Hintergrund
  und schickt fertige Frames über Qt-Signals sicher in den Main Thread.
"""

from __future__ import annotations

import logging
import time
import threading
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
    HOSTMODE_ENTER_CMDS,
    HOSTMODE_EXIT_FRAME,
    HOSTMODE_RECOVERY_FRAME,
    Port,
    FrameType,
)
from .frame import build_frame, build_command_frame, FrameParser, HostFrame

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hintergrund-Thread für das Lesen vom seriellen Port
# ---------------------------------------------------------------------------

class _ReaderThread(threading.Thread):
    """
    Interner Lese-Thread.

    Läuft als Daemon-Thread, d.h. er wird automatisch beendet wenn
    das Hauptprogramm endet – wir müssen uns nicht explizit darum kümmern.

    Der Thread liest Bytes aus dem seriellen Port, gibt sie an den
    FrameParser und ruft für jeden vollständigen Frame den callback auf.
    """

    def __init__(self, port: "serial.Serial", callback) -> None:
        super().__init__(daemon=True, name="PK232-Reader")
        self._port = port
        self._callback = callback
        self._stop_event = threading.Event()
        self._parser = FrameParser()

    def stop(self) -> None:
        """Signalisiert dem Thread, dass er aufhören soll."""
        self._stop_event.set()

    def run(self) -> None:
        """Läuft bis stop() aufgerufen wird."""
        logger.debug("ReaderThread gestartet")
        while not self._stop_event.is_set():
            try:
                # Lese bis zu 64 Bytes auf einmal (nicht blockierend dank timeout)
                raw = self._port.read(64)
                if raw:
                    frames = self._parser.feed_bytes(raw)
                    for frame in frames:
                        try:
                            self._callback(frame)
                        except Exception as e:
                            logger.error(f"Fehler im Frame-Callback: {e}")
            except Exception as e:
                if not self._stop_event.is_set():
                    logger.error(f"Lesefehler auf Serial Port: {e}")
                    break
        logger.debug("ReaderThread beendet")


# ---------------------------------------------------------------------------
# SerialManager – die öffentliche API
# ---------------------------------------------------------------------------

class SerialManager(QObject):
    """
    Verwaltet die Verbindung zum PK-232/PK-232MBX über den seriellen Port.

    Qt-Signals (können mit Slots in der UI verbunden werden):
        frame_received(HostFrame)  : Ein vollständiger Frame wurde empfangen.
        connection_changed(bool)   : True = verbunden, False = getrennt.
        status_message(str)        : Statusmeldung für die Statusleiste.

    Typische Verwendung:
        mgr = SerialManager()
        mgr.frame_received.connect(self.on_frame)
        mgr.connection_changed.connect(self.update_status_bar)

        mgr.connect_port("COM3", baudrate=9600)
        mgr.enter_host_mode()
        mgr.send_command("MYCALL OE3GAS")
        # ... arbeiten ...
        mgr.disconnect_port()
    """

    # Qt-Signals
    frame_received    = pyqtSignal(object)   # object = HostFrame
    connection_changed = pyqtSignal(bool)
    status_message    = pyqtSignal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._serial: Optional["serial.Serial"] = None
        self._reader: Optional[_ReaderThread] = None
        self._host_mode_active: bool = False
        self._lock = threading.Lock()   # Schutz für serial.write()

    # -----------------------------------------------------------------------
    # Port-Verbindung
    # -----------------------------------------------------------------------

    def connect_port(
        self,
        port_name: str,
        baudrate: int = SerialDefaults.BAUDRATE,
        rtscts: bool = SerialDefaults.RTSCTS,
    ) -> bool:
        """
        Öffnet den seriellen Port.

        Args:
            port_name: Z.B. "COM3" (Windows) oder "/dev/ttyUSB0" (Linux)
            baudrate : Übertragungsrate (Standard: 9600)
            rtscts   : Hardware-Handshake (Standard: True, empfohlen)

        Returns:
            True bei Erfolg, False bei Fehler.
        """
        if not PYSERIAL_AVAILABLE:
            self.status_message.emit("Fehler: pyserial nicht installiert!")
            return False

        if self._serial and self._serial.is_open:
            logger.warning("Port bereits geöffnet – erst schließen.")
            return False

        try:
            self._serial = serial.Serial(
                port=port_name,
                baudrate=baudrate,
                bytesize=SerialDefaults.BYTESIZE,
                parity=SerialDefaults.PARITY,
                stopbits=SerialDefaults.STOPBITS,
                timeout=SerialDefaults.TIMEOUT,
                xonxoff=SerialDefaults.XONXOFF,
                rtscts=rtscts,
            )
            logger.info(f"Port {port_name} geöffnet ({baudrate} Bd)")
            self.status_message.emit(f"Verbunden: {port_name} @ {baudrate} Bd")
            self.connection_changed.emit(True)

            # Reader-Thread starten
            self._reader = _ReaderThread(self._serial, self._on_frame_received)
            self._reader.start()
            return True

        except Exception as e:
            logger.error(f"Port {port_name} konnte nicht geöffnet werden: {e}")
            self.status_message.emit(f"Verbindungsfehler: {e}")
            self._serial = None
            return False

    def disconnect_port(self) -> None:
        """Beendet den Reader-Thread und schließt den seriellen Port."""
        if self._host_mode_active:
            self.exit_host_mode()

        if self._reader:
            self._reader.stop()
            self._reader.join(timeout=2.0)
            self._reader = None

        if self._serial and self._serial.is_open:
            self._serial.close()
            logger.info("Serieller Port geschlossen")

        self._serial = None
        self._host_mode_active = False
        self.connection_changed.emit(False)
        self.status_message.emit("Verbindung getrennt")

    @property
    def is_connected(self) -> bool:
        """True wenn der Port geöffnet ist."""
        return self._serial is not None and self._serial.is_open

    @property
    def is_host_mode(self) -> bool:
        """True wenn Host Mode aktiv ist."""
        return self._host_mode_active

    # -----------------------------------------------------------------------
    # Host Mode Verwaltung
    # -----------------------------------------------------------------------

    def enter_host_mode(self) -> bool:
        """
        Versetzt den PK-232 in den Host Mode.

        Ablauf:
          1. Sende Vorbereitungs-Kommandos als ASCII (CANLINE, COMMAND)
          2. Sende "HOST Y\\r" als ASCII
          3. Warte kurz auf TNC-Antwort
          4. Setze internen Flag

        Returns:
            True bei Erfolg.
        """
        if not self.is_connected:
            logger.error("Kein Port verbunden")
            return False

        if self._host_mode_active:
            logger.warning("Host Mode bereits aktiv")
            return True

        logger.info("Aktiviere Host Mode...")
        try:
            for cmd in HOSTMODE_ENTER_CMDS:
                with self._lock:
                    self._serial.write(cmd)
                time.sleep(0.05)   # kurze Pause zwischen Kommandos

            # Warte auf TNC-Initialisierung
            time.sleep(0.2)
            self._host_mode_active = True
            self.status_message.emit("Host Mode aktiv")
            logger.info("Host Mode aktiviert")
            return True

        except Exception as e:
            logger.error(f"Fehler beim Aktivieren des Host Mode: {e}")
            self.status_message.emit(f"Host Mode Fehler: {e}")
            return False

    def exit_host_mode(self) -> None:
        """
        Beendet den Host Mode (sendet HON-Frame).

        Wichtig: Im Host Mode kann kein ASCII "HOST OFF\\r" gesendet werden –
        der TNC versteht nur Binär-Frames! Daher den speziellen HON-Frame.
        """
        if not self.is_connected or not self._host_mode_active:
            return

        try:
            with self._lock:
                self._serial.write(HOSTMODE_EXIT_FRAME)
            time.sleep(0.1)
            self._host_mode_active = False
            self.status_message.emit("Host Mode beendet")
            logger.info("Host Mode deaktiviert")
        except Exception as e:
            logger.error(f"Fehler beim Beenden des Host Mode: {e}")

    def host_mode_recovery(self) -> None:
        """
        Notfall-Recovery bei hängendem Host Mode.

        Sendet den speziellen SOH-SOH-Recovery-Frame laut AEA Manual Kap. 4.1.6.
        Danach HOST OFF. Erspart in vielen Fällen das Aus-/Einschalten des TNC.
        """
        if not self.is_connected:
            return
        try:
            with self._lock:
                self._serial.write(HOSTMODE_RECOVERY_FRAME)
            time.sleep(0.2)
            self.exit_host_mode()
            self.status_message.emit("Recovery durchgeführt")
            logger.info("Host Mode Recovery gesendet")
        except Exception as e:
            logger.error(f"Recovery fehlgeschlagen: {e}")

    # -----------------------------------------------------------------------
    # Daten senden
    # -----------------------------------------------------------------------

    def send_command(self, cmd: str, port: int = Port.PORT1) -> bool:
        """
        Sendet einen ASCII-Befehl an den TNC (im Host Mode).

        Args:
            cmd : Befehlsstring ohne \\r, z.B. "MYCALL OE3GAS"
            port: Port.PORT1 oder Port.PORT2

        Returns:
            True bei Erfolg.
        """
        if not self._check_ready():
            return False

        frame = build_command_frame(cmd, port)
        return self._write_raw(frame)

    def send_data(
        self, data: bytes, port: int = Port.PORT1
    ) -> bool:
        """
        Sendet Rohdaten (z.B. Packet-Nutzdaten) als Connected-Data-Frame.

        Args:
            data: Zu sendende Bytes
            port: Port.PORT1 oder Port.PORT2
        """
        if not self._check_ready():
            return False

        ctl = port | FrameType.CONNECT_DATA
        frame = build_frame(ctl, data)
        return self._write_raw(frame)

    def send_raw_frame(self, ctl: int, data: bytes) -> bool:
        """
        Sendet einen Frame mit beliebigem CTL-Byte (für fortgeschrittene Nutzung).
        """
        if not self._check_ready():
            return False
        frame = build_frame(ctl, data)
        return self._write_raw(frame)

    # -----------------------------------------------------------------------
    # Hilfsmethoden
    # -----------------------------------------------------------------------

    def _write_raw(self, data: bytes) -> bool:
        """Thread-sicheres Schreiben auf den seriellen Port."""
        try:
            with self._lock:
                self._serial.write(data)
            return True
        except Exception as e:
            logger.error(f"Schreibfehler: {e}")
            self.status_message.emit(f"Sendefehler: {e}")
            return False

    def _check_ready(self) -> bool:
        """Prüft ob Port verbunden und Host Mode aktiv ist."""
        if not self.is_connected:
            logger.warning("Kein Port verbunden")
            return False
        if not self._host_mode_active:
            logger.warning("Host Mode nicht aktiv")
            return False
        return True

    def _on_frame_received(self, frame: HostFrame) -> None:
        """
        Callback aus dem Reader-Thread.

        Qt-Signals sind thread-safe: emit() aus einem Nicht-Main-Thread
        ist erlaubt – Qt sorgt dafür, dass der verbundene Slot im
        richtigen Thread aufgerufen wird.
        """
        logger.debug(f"Frame empfangen: {frame}")
        self.frame_received.emit(frame)

    # -----------------------------------------------------------------------
    # Statische Hilfsmethode: Verfügbare Ports auflisten
    # -----------------------------------------------------------------------

    @staticmethod
    def list_ports() -> list[str]:
        """
        Gibt eine Liste aller verfügbaren seriellen Ports zurück.

        Verwendung in der UI für die Port-Auswahl-ComboBox:
            ports = SerialManager.list_ports()
            # z.B. ["COM1", "COM3", "COM7"] unter Windows
            #      ["/dev/ttyUSB0", "/dev/ttyS0"] unter Linux
        """
        if not PYSERIAL_AVAILABLE:
            return []
        return [p.device for p in serial.tools.list_ports.comports()]
