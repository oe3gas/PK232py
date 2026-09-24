# Claude Code Prompt — P42: Connect direkt im Kanal-Button

> Ablage: `docs/P42_Connect_In_Chip_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorlage: aktualisiertes Mockup `docs/mockups/packet_screen.py`
> (Kanal-Chips mit eingebautem Eingabefeld, Zeile „Connect" entfernt),
> Screenshots `pr_chip_normal.png`, `pr_chip_edit.png`.
> Vorher `CLAUDE.md` lesen, besonders die Abschnitte zum Kanalmodell und
> zum Tastaturfilter (P41).

---

## Was sich ändert

Die Zeile mit `Connect`, `Dest`, `…` und `Disconnect` **entfällt**. Das
Rufzeichen wird direkt in den Kanal-Button getippt, auf dem verbunden
werden soll.

Begründung, die als Kommentar in die Datei gehört: Der Kanal ist der Ort,
an dem die Verbindung entsteht — damit kann ein Connect nie auf einem
anderen Kanal landen als dem, den man ansieht. Nebenbei verschwindet die
Fehlerquelle aus P41 (Eingabefeld in einer eigenen Zeile, das der
Tastaturfilter verschluckt).

---

## P42.1 — `ChannelChip`: Knopf, der zum Eingabefeld wird

Jeder Chip wird ein `QWidget` mit `QStackedLayout` aus zwei Seiten:
`QPushButton` (Anzeige) und `QLineEdit` (Eingabe).

### Wann die Eingabe öffnet

| Auslöser | Verhalten |
|---|---|
| Klick auf einen **anderen** Chip | wechselt nur den Kanal |
| Klick auf den **bereits gewählten freien** Chip | öffnet die Eingabe |
| Doppelklick auf einen freien Chip | öffnet die Eingabe |
| `Enter` bei gewähltem freien Chip (Fokus nicht im TX-Fenster) | öffnet die Eingabe |
| Doppelklick in der MHEARD-Liste | öffnet die Eingabe im ersten freien Chip, vorbelegt mit dem Rufzeichen |

**Belegte Chips öffnen keine Eingabe.** Kanal 0 (UI) nie — dort gibt es
keine Verbindungen.

### Während der Eingabe
- Eingabefeld mit bernsteinfarbenem Rahmen, zentrierter Monospace-Text
- Vervollständigung aus der Rufzeichen-Historie (`QCompleter`), die die
  bisherige Dest-Liste übernimmt; die Historie bleibt erhalten und wird
  weiter gepflegt
- `Enter`: Rufzeichen prüfen (Buchstaben, Ziffern, optionale SSID), dann
  Connect **auf diesem Kanal**. Ungültig → Feld bleibt offen, roter
  Rahmen, Tooltip mit dem Grund
- `Esc`: Eingabe verwerfen, Chip zeigt wieder seine Nummer
- Fokusverlust: wie `Esc`

### Kontextmenü (rechte Maustaste)
| Chip | Einträge |
|---|---|
| frei | `Connect…` (öffnet die Eingabe), `Connect via…` (Dialog mit NET/ROM-Mehrfachpfad, `;`-Syntax) |
| verbunden / rufend | `Disconnect`, `Copy callsign` |
| UI (0) | keine Einträge |

**Commit:** `Packet screen: channel chips accept a callsign`

---

## P42.2 — Connect und Disconnect ohne eigene Zeile

- `connect_requested(channel, callsign)` vom Chip → `main_window` sendet
  `CO` **auf genau diesem Kanal** und schaltet den aktuellen Kanal dorthin
- Disconnect: Kontextmenü des Chips, zusätzlich `Ctrl+D` auf dem
  gewählten belegten Kanal. Beides fragt **nicht** nach — der Zustand ist
  am Chip sichtbar, und ein Disconnect ist wiederholbar
- Der `PacketConnectDialog` bleibt erhalten, erreichbar über
  `Connect via…`; er bekommt den Kanal aus dem Chip und nicht mehr aus
  einem Auswahlfeld
- Der Zustandswechsel bleibt wie gehabt: `CH_CALLING` beim Absenden,
  `CH_CONNECTED` nach der Link-Meldung, `CH_FREE` nach Disconnect

### Entfallende Bezeichner
`btn_connect`, `btn_disconnect`, `cb_dest`, `btn_connect_dlg`,
`dest_callsign()`, `set_dest_callsign()` entfallen. **Jede** Fundstelle
prüfen — `main_window._wire_packet_buttons()`, `_on_packet_connect()`,
`_on_packet_disconnect()`, `set_link_state()`, die Tests — und im
Commit-Text auflisten.

`set_link_state()` steuerte bisher die Freigabe dieser Knöpfe. Künftig
steuert es nur noch die Statusanzeige und den Unproto-Knopf; die
Verbindungsfreigabe ergibt sich aus dem Chip-Zustand. Die kanalbezogene
Regel aus P16 (nur Meldungen des sichtbaren Kanals ändern die Anzeige)
bleibt.

**Commit:** `MainWindow: connect and disconnect driven by the channel chips`

---

## P42.3 — Tastaturfilter

Die Eingabefelder der Chips sind `QLineEdit` und müssen von der
Umleitung ins TX-Fenster ausgenommen sein (P41). Prüfen, dass die
Ausnahme greift, **auch** während das Feld erst im laufenden Betrieb
sichtbar wird.

`Ctrl+Up`/`Ctrl+Down` wechseln weiterhin den Kanal — aber **nicht**,
solange eine Chip-Eingabe offen ist.

**Commit:** wird Teil von P42.1, wenn keine Änderung nötig ist; sonst
eigener Commit.

---

## P42.4 — Tests

- Klick auf einen anderen Chip wechselt nur; zweiter Klick auf denselben
  freien Chip öffnet die Eingabe
- belegter Chip und Chip 0 öffnen keine Eingabe
- `Enter` mit gültigem Rufzeichen löst `connect_requested(ch, call)` aus,
  mit **diesem** Kanal
- ungültiges Rufzeichen: kein Signal, Feld bleibt offen
- `Esc` schließt ohne Signal
- MHEARD-Doppelklick füllt den ersten freien Chip vor
- Tippen in einem offenen Chip-Feld landet nicht im TX-Fenster
- `Ctrl+Up` bei offener Eingabe wechselt den Kanal nicht
- `Ctrl+D` auf einem belegten Chip löst Disconnect auf diesem Kanal aus

**Commit:** `Tests: connect via channel chips`

---

## P42.5 — Dokumentation

- `CLAUDE.md`, Kanalmodell: Connects entstehen im Chip; es gibt keine
  Dest-Zeile mehr. Begründung (der Kanal ist der Ort der Verbindung) und
  die Bedienwege in einer kurzen Tabelle
- `Testplan.md`: Fälle anpassen, die `btn_connect`/`cb_dest` benutzen
  (T33–T37 und was sonst betroffen ist) — **nicht löschen**, sondern auf
  die neue Bedienung umschreiben, mit Vermerk, dass die alte Bedienung
  entfallen ist
- `docs/mockups/packet_screen.py` aktualisiert ablegen (liegt bei)

**Commit:** `Docs: connect in the channel chip`

---

## Offen gelassen

Der UI-Chip trägt im Mockup noch die Beschriftung `0`; in der Anwendung
heißt er `UI` (P10). Das bleibt so — die Mockup-Fassung ist an dieser
Stelle älter.

---

## Definition of Done

- `.venv\Scripts\python.exe -m pytest` grün
- Kein Bezeichner `cb_dest`/`btn_connect`/`btn_disconnect` mehr im
  Packet-Pfad
- Tippen im Chip-Feld landet im Chip, nicht im TX-Fenster — Test
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"
- Danach vom Operator: Rufzeichen in einen freien Chip tippen, Enter,
  Verbindung prüfen; danach `Ctrl+D`