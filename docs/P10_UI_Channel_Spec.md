# Claude Code Prompt — P10: Kanal 0 wird der UI-/Unproto-Kanal

> Ablage: `docs/P10_UI_Channel_Spec.md` im Repo, damit CC sie direkt lesen kann.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher `CLAUDE.md`, `Backlog.md`, `Testplan.md` lesen.

---

## Warum

Im AEA Host Mode gibt es für ausgehende Daten nur `$2x` mit `x` = 0–9; ein
`$2F` existiert nicht. Unproto ist deshalb kein eigener Kanal, sondern der
Zustand eines Kanals, auf dem keine Verbindung besteht — der TNC sendet dort
nach dem UNPROTO-Pfad. Empfangsseitig ist die Trennung dagegen schon da:
`$3x` sind Daten einer verbundenen Station auf Kanal x, `$3F` sind mitgehörte
Frames ohne Kanalzugehörigkeit.

Konsequenz für die UI: **Kanal 0 wird reserviert als UI-/Monitor-Kanal**,
Kanäle 1–9 bleiben die Gesprächskanäle. Damit fällt der Unproto-TX-Puffer
ohne Sondermechanik ab — Kanal 0 hat wie jeder andere Chip seinen Eintrag in
`_tx_buffers` (P9).

`CHANNEL_COUNT` bleibt 10. Es wird **kein** elfter Kanal eingeführt.

---

## P10.1 — `src/pk232py/ui/screens/packet_screen.py`: Chip 0 als UI-Kanal

### Beschriftung und Aussehen

- Chip 0 zeigt statt der Ziffer `0` die Beschriftung **`UI`**.
- Eigene Füllfarbe, klar unterscheidbar von `free`/`calling`/`connected`
  (Vorschlag: gedecktes Blau, etwa `#2a6496`) — der Chip hat keinen
  Verbindungszustand, den die drei vorhandenen Farben ausdrücken könnten.
- Tooltip: dass dies der Unproto-/Monitor-Kanal ist, dass hier keine
  Verbindung aufgebaut werden kann und dass der TNC Text von diesem Kanal
  nach dem UNPROTO-Pfad als UI-Frame aussendet.
- `_update_chip()` entsprechend erweitern; die Sonderbehandlung an **einer**
  Stelle halten, nicht über mehrere Methoden verteilen.

### Zustandsschutz

- `set_channel_state(0, …)` ignoriert Zustandsänderungen für Kanal 0 —
  der UI-Kanal wird nie `calling` oder `connected`. Defensive Absicherung,
  falls der TNC doch einmal eine Link-Message mit Kanal 0 schickt
  (Kommentar dazu: in Nicht-Packet-Betriebsarten ist 0 der einzige Kanal,
  also ist eine solche Meldung nicht völlig ausgeschlossen).
- `channel_map()` nimmt Kanal 0 nie auf.
- `step()` bezieht Kanal 0 weiterhin ein — Ctrl+Up/Down soll auch zum
  UI-Kanal führen können.
- `reset()` / `reset_channels()` ändern den aktuellen Kanal nicht.

### Monitordaten in der CH-Ansicht

`append_monitor_data()` bekommt dieselbe Filterlogik wie
`append_channel_data()`:

- Ansicht `ALL` → Monitordaten immer anzeigen (wie bisher)
- Ansicht `CH` → Monitordaten nur anzeigen, wenn Kanal 0 der aktuelle ist

Damit bekommt die CH-Ansicht eine durchgehende Bedeutung: Chip 0 gewählt =
Mithörbetrieb, Chip 3 gewählt = nur das QSO auf 3.

**Commit:** `Packet screen: channel 0 is the UI monitor channel`

---

## P10.2 — `src/pk232py/ui/main_window.py`: Bedienlogik

### Unproto-Button

- `_on_packet_unproto(checked=True)` → zusätzlich
  `screen.channel_bar.set_current(0)`. Der Puffertausch aus P9 läuft dabei
  automatisch mit, es ist kein eigener Unproto-Puffer nötig.
- `checked=False` → **kein** automatischer Rücksprung auf einen anderen
  Kanal. Der Operator wählt selbst einen Chip; ein stiller Sprung würde den
  sichtbaren TX-Text austauschen, ohne dass jemand etwas angeklickt hat.

### Kanalwahl steuert die Buttons

In `_on_packet_channel_changed(channel)` ergänzen:

- `channel == 0` → `btn_connect` und `btn_disconnect` deaktivieren
  (auf dem UI-Kanal gibt es nichts zu verbinden)
- `channel != 0` → beide wieder freigeben, sofern die Link-Logik das erlaubt
  (`set_link_state()` bleibt die Autorität über den Verbindungszustand — die
  Kanalwahl darf ihre Sperren nicht überschreiben)
- `channel != 0` **und** `btn_unproto.isChecked()` → Unproto ausschalten,
  inklusive der Stilrückstellung über `screen.on_unproto_toggled(False)`

Damit ergibt sich die bisherige T39-Regel (Connect und Unproto schließen
sich aus) aus der Kanalwahl selbst. Die vorhandene Verriegelung in
`_on_packet_unproto()` nicht ersatzlos löschen, sondern auf diese neue
Grundlage umstellen und im Kommentar auf T39 verweisen.

### Connect-Schutz

`_on_packet_connect()`: wenn der aktuelle Kanal 0 ist, keinen `CO`-Frame
senden, den Button wieder entrasten und in einer QMessageBox erklären, dass
Kanal 0 der UI-/Monitor-Kanal ist und Verbindungen auf den Kanälen 1–9
laufen. Gleiche Behandlung im Connect-Dialog: der `QSpinBox` bekommt den
Bereich 1–9 statt 0–9.

**Commit:** `MainWindow: unproto uses channel 0, connect blocked there`

---

## P10.3 — Dokumentation

### `CLAUDE.md`

Abschnitt „Channel model" erweitern:

- Kanal 0 = UI-/Unproto-/Monitorkanal, Kanäle 1–9 = Gesprächskanäle
- Begründung über die Frametypen: `$2x` kennt kein `F`, `$3F` kennt keinen
  Kanal; Unproto ist ein Kanalzustand, kein eigener Kanal
- Hinweis, dass in allen Nicht-Packet-Betriebsarten ohnehin nur Kanal 0
  benutzt wird (TRM 4.3) — die Belegung ist damit konsistent zum Rest der App

### `Testplan.md`

**T98 — Unproto schaltet auf den UI-Kanal**
1. Kanal 3 wählen, Text tippen, nicht senden
2. Unproto einschalten
3. Erwartung: Chip `UI` ist aktiv, TX-Fenster zeigt den Unproto-Entwurf
   (anfangs leer), Connect und Disconnect sind gesperrt
4. Chip 3 wählen → Unproto geht aus, der Text von Schritt 1 ist wieder da

**T99 — Connect auf Kanal 0 wird abgewiesen**
1. Chip `UI` wählen, Rufzeichen in Dest eintragen, Connect drücken
2. Erwartung: kein `CO`-Frame auf der Leitung, Hinweisdialog, Button entrastet

**T100 — Monitordaten in der CH-Ansicht**
1. Ansicht auf `CH`, Chip 3 aktiv → mitgehörte Frames erscheinen **nicht**
2. Chip `UI` wählen → mitgehörte Frames erscheinen
3. Ansicht auf `ALL` → Monitordaten erscheinen unabhängig vom Chip

**T101 — Hardwareprüfung: UI-Frame auf unverbundenem Kanal**
Status `OPEN`, braucht echtes Gerät. Zu klären: sendet die v7.1 Text, der
über `$20` auf dem unverbundenen Kanal 0 hereinkommt, tatsächlich als
UI-Frame nach dem eingestellten UNPROTO-Pfad aus? Das ist
AX.25-Standardverhalten, aber für den Host Mode der v7.1 nicht belegt.
Falls nein: Fehlerframe protokollieren und den Befund in `CLAUDE.md`
nachtragen, bevor wir uns auf die Belegung festlegen.

### `Backlog.md`

T101 als Priorität 1 unter den Hardwaretests eintragen.

**Commit:** `Docs: UI channel model, tests T98-T101`

---

## Definition of Done

- `python -m pytest` grün, neue Tests für Chip-0-Sonderfälle eingeschlossen
- P9-Verhalten unverändert: Entwürfe auf 1–9 überleben Wechsel auf 0 und
  zurück
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"