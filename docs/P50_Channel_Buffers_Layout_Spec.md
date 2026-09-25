# Claude Code Prompt — P50: Kanalpuffer, Fenstergrößen, Präfixe, MHEARD

> Ablage: `docs/P50_Channel_Buffers_Layout_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher `CLAUDE.md` (Kanalmodell, P9 TX-Puffer), `Testplan.md` (T100)
> lesen.

---

## Teil A — Befund zuerst klären: Kanal 1 oder Kanal 2?

Im Screenshot vom 25.09.2026, 19:07:

- Chip **1** grün mit `OE3TEC`, Statuszeile „Ch 1 Partner: OE3TEC"
- **alle** empfangenen Zeilen tragen `[CH2]`, ebenso
  `*** DISCONNECTED: OE3TEC-1 ***`

Entweder führt der TNC die Verbindung auf einem anderen Kanal als
angefordert, oder zwischen dem Kanal im gesendeten `CO`-Frame und dem
Kanal der empfangenen Frames liegt ein Versatz.

**Messen, nicht raten:**

- den gesendeten `CO`-Frame in Hex protokollieren (CTL-Byte sichtbar)
- den Kanal jedes empfangenen `$3x`/`$5x`-Frames protokollieren
- Ergebnis in den Commit-Text; besteht ein Versatz, die Ursache benennen
  (Frame-Bau, `ctl_channel()`, Anzeige) und **eine** Stelle korrigieren

Erst danach Teil B, sonst baut man die Kanalpuffer auf eine falsche
Kanalnummer.

**Commit:** `Packet: log CO frame and incoming channel numbers`

---

## Teil B — Ein Puffer je Kanal

### Warum
Heute liegt alles in **einem** Textfeld, und die ALL/CH-Umschaltung
filtert beim **Anhängen** (T100). Wer auf `CH` wechselt, sieht deshalb nur
das, was ab diesem Moment kommt — der bisherige Verlauf des Kanals fehlt.

Das ist dieselbe Aufgabe wie bei den TX-Entwürfen aus P9, nur für die
Empfangsseite.

### B.1 Struktur

```python
self._rx_docs: dict[int, QTextDocument]   # je Kanal ein Dokument
self._rx_doc_all: QTextDocument           # zusammengeführter Strom
```

- **Kanal 0 (UI)**: Monitorverkehr, Unproto, Meldungen ohne Kanalbezug
  (`$5F`)
- **Kanal 1–9**: je ein Dokument mit dem Gesprächsverlauf
- **ALL**: eigenes Dokument, das **alles** in Ankunftsreihenfolge enthält

Jede eingehende Zeile wird in **zwei** Dokumente geschrieben: in das des
Kanals und in das ALL-Dokument. Das kostet Speicher, spart aber die
Zusammenführung beim Umschalten — und der Verlauf bleibt vollständig.

Umschalten (Chip oder ALL/CH) setzt nur `rx_display.setDocument(...)`;
die Bildlaufposition je Dokument merken und wiederherstellen.

Obergrenze je Dokument: `maximumBlockCount` (Vorschlag 5000 Zeilen),
konfigurierbar lassen, damit ein langer Betriebstag nicht den Speicher
füllt.

`reset_channels()` (P8) leert alle Dokumente.

**Commit:** `Packet screen: one RX document per channel`

---

## Teil C — Präfixe kürzen

`[19:05:56] [CH2] ` vor jeder Zeile kostet rund ein Drittel der Breite.

| Ansicht | Präfix |
|---|---|
| `CH` (ein Kanal) | **keines** — der Kanal steht im Chip |
| `ALL` | knapp: `2│` (Kanalziffer + schmaler Trenner), farblich gedämpft |
| Zeitstempel | **optional**, Standard **aus** |

- neue Anzeige-Einstellung `show_timestamps` im Packet-Parameterdialog,
  Abschnitt Anzeige (dort, wo P47 die Spiegelung der Link-Meldungen
  einträgt); PC-seitig, also `UPLOAD_EXEMPT`
- ist sie an, `HH:MM:SS` in gedämpfter Farbe voranstellen
- Systemmeldungen (`*** … ***`) behalten ihre auffällige Farbe und in der
  ALL-Ansicht ihren Kanalhinweis

**Commits:**
```
Config: optional timestamps in the packet RX view
Packet screen: compact channel prefix, no prefix in CH view
```

---

## Teil D — Fenstergrößen

### D.1 RX wächst mit dem Fenster
Das RX-Fenster nimmt den verfügbaren Platz ein; beim Vergrößern des
Anwendungsfensters wächst es mit. Prüfen, welche `QSizePolicy` und
welche Stretch-Faktoren das heute verhindern — im Screenshot bleibt unten
eine große leere Fläche.

### D.2 TX-Höhe durch Ziehen einstellbar
Zwischen RX und TX ein `QSplitter` (senkrecht). Die Höhe des TX-Bereichs
ist damit vom Bediener einstellbar; die feste Höhe von fünf Zeilen
entfällt als Vorgabe, bleibt aber Startwert.

- die Aufteilung beim Beenden speichern und beim Start wiederherstellen
  (dort, wo die Fenstergeometrie schon gespeichert wird)
- Mindesthöhen setzen, damit keiner der beiden Bereiche verschwindet
- die Knöpfe rechts neben dem TX-Feld (`Hold TX`, `Clear TX`, `Clear RX`)
  bleiben an ihrer Stelle und wachsen nicht mit

**Commit:** `Packet screen: RX expands, TX height adjustable by splitter`

---

## Teil E — MHEARD zeigt auch die Verbindungspartner

Heute erscheinen dort nur Stationen aus einem `MH`-Abruf, und der läuft
nur auf Knopfdruck. Verbindungspartner fehlen deshalb.

- bei jeder Link-Meldung mit Kanalbezug (`CONNECTED`, `DISCONNECTED`,
  `busy`, `Connect request`) den Partner in die Liste aufnehmen, falls er
  nicht schon darin steht — mit Zeit und Kanalnummer, grün wie jede
  verbundene Station (P44 A.3)
- nach `CONNECTED` und `DISCONNECTED` zusätzlich einen `MH`-Abruf
  auslösen, damit die Liste auch die übrigen Gehörten nachzieht
  (ein Abruf, nicht mehrere; vorhandene Funktion verwenden)
- getrennte Stationen bleiben in der Liste stehen, verlieren aber die
  Kanalnummer und die grüne Farbe — sie waren ja zu hören

**Commit:** `MHEARD panel: connection partners appear without a manual refresh`

---

## Teil F — Tests

- Kanalpuffer: Text auf Kanal 1, Umschalten auf 3 und zurück → der
  Verlauf von Kanal 1 ist vollständig da
- ALL enthält beide Kanäle in Ankunftsreihenfolge
- `CH`-Ansicht ohne Präfix, `ALL`-Ansicht mit `2│`
- Zeitstempel aus/an
- Bildlaufposition je Kanal bleibt erhalten
- Splitter: Aufteilung wird gespeichert und wiederhergestellt
- MHEARD: nach einer CONNECTED-Meldung steht der Partner in der Liste,
  mit Kanalnummer; nach DISCONNECTED ohne
- `reset_channels()` leert alle Dokumente

**Commit:** `Tests: per-channel RX buffers, prefixes, splitter, MHEARD`

---

## Teil G — Dokumentation

- `CLAUDE.md`: **Jeder Kanal hat sein eigenes RX-Dokument.** Die
  ALL/CH-Umschaltung wechselt das Dokument, sie filtert nicht mehr beim
  Anhängen. Begründung: der Verlauf eines Kanals muss beim Umschalten
  vollständig sichtbar sein
- `Testplan.md`: T100 umschreiben (Filterung → Dokumentwechsel), neue
  Fälle für Splitter, Präfixe und MHEARD
- Befund aus Teil A dokumentieren, egal wie er ausgeht

**Commit:** `Docs: per-channel RX buffers and display options`

---

## Definition of Done

- `.venv\Scripts\python.exe -m pytest` grün
- Der Kanalversatz aus Teil A ist geklärt und im Commit-Text belegt
- Umschalten auf einen Kanal zeigt dessen vollständigen Verlauf
- RX wächst mit dem Fenster, TX-Höhe ist ziehbar und bleibt erhalten
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"