# Claude Code Prompt — P55: Oberflächenbefunde aus dem Prüfdurchgang

> Ablage: `docs/P55_UI_Befunde_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> **Ersetzt `P51_Pruefdurchgang_Befunde_Spec.md`**, dessen Teil A durch
> P52–P54 erledigt ist (Ursache: `connect_port()` setzte DTR/RTS auf
> `False`). Die übrigen Teile sind hier zusammengefasst und aktualisiert.
> Belege: Screenshots und Mitschnitte vom 25./26.09.2026, Gerät B
> (Release 01.AUG.91).

**Erledigt und nicht mehr offen:** MailDrop-Sitzung (T122), Chip-Zustände
mit Pulsation und rotem Blitzen, kanalbezogene Link-Meldungen,
Verbindungsaufbau in allen geprüften Zuständen. **Kein Kanalversatz** —
in der ALL-Ansicht steht `1│` passend zu Chip 1.

---

## Teil A — MHEARD zeigt Datum statt Rufzeichen

In der Spalte `Callsign` stehen Werte wie `25-Sep-26` und `00:05`. Die
Einträge stammen aus der in P50 Teil E ergänzten Übernahme aus
Link-Meldungen und/oder aus dem `MH`-Abruf.

- Feldzuordnung prüfen: Rufzeichen, Kanal, Zeit sind offensichtlich
  verschoben
- Tests mit einer echten `MH`-Antwort **und** mit einer Link-Meldung als
  Fixture — beide Wege füllen die Liste

**Commit:** `MHEARD panel: fix column mapping for callsign, channel and time`

---

## Teil B — Gesendeter Text fehlt in der Kanalansicht

In der ALL-Ansicht erscheint `> ch1 just testing`, in der CH-Ansicht von
Kanal 1 nicht — Link-Meldungen dagegen schon.

Das TX-Echo wird also nur in das ALL-Dokument geschrieben. Es gehört in
**beide**: in das Dokument des Kanals, auf dem gesendet wurde, und in das
ALL-Dokument.

**Commit:** `Packet screen: TX echo goes into the channel document too`

---

## Teil C — Schrift wechselt beim Umschalten der Ansicht

Beim Wechsel zwischen ALL und CH ändert sich die Schrift im Textbereich.
Vermutlich werden die Dokumente aus P50 ohne die konfigurierte Schrift
erzeugt, und `setDocument()` übernimmt die Dokumentvorgabe.

- beim Erzeugen jedes Dokuments Schrift und Grundformat setzen
  (`setDefaultFont()`), aus derselben Quelle wie bisher
- prüfen, ob auch die Zeichenformate eingefügter Zeilen betroffen sind

**Commit:** `Packet screen: all RX documents share the configured font`

---

## Teil D — Firmware wird nicht angezeigt

Die Kopfzeile zeigt `TNC-Firmware: unknown`, obwohl das Banner im
Terminal steht und der Init es auswertet
(`TNC banner captured: PACTOR=False (176 bytes)`).

Prüfen, wo `tnc_release` aus P37 Teil C gesetzt wird und warum es die
Kopfzeile nicht erreicht. Die Anbindung dort herstellen, wo das Banner
ohnehin gesammelt wird (P49 Teil B).

**Commit:** `MainWindow: show the firmware release from the collected banner`

---

## Teil E — Fensterausnutzung

Die Betriebsart-Maske füllt das Anwendungsfenster nicht: unterhalb der
Makroknöpfe bleibt eine große leere Fläche.

- die Maske dehnt sich über die volle Höhe
- die Makrozeile sitzt **am unteren Rand**
- der RX/TX-Splitter bekommt den verbleibenden Platz
- die Ursache (fehlende `QSizePolicy` oder fehlender Stretch-Faktor im
  übergeordneten Layout) an **einer** Stelle beheben, damit die Korrektur
  für alle Masken gilt

**Commit:** `Opmode screens: fill the window, macros anchored at the bottom`

---

## Teil F — Zeitstempel: zwei Quellen auseinanderhalten

Die Stempel in Link-Meldungen (`*** 25-Sep-26 21:04:36 CONNECTED to
OE3TEC ***`) kommen **vom TNC**: `CONSTAMP` und `DAYSTAMP` werden beim
Upload eingeschaltet. Die Anzeigeoption aus P50 Teil C betrifft nur das
**eigene** Präfix der Anwendung.

- im Parameterdialog, Abschnitt Anzeige, einen erklärenden Satz:
  „Link messages carry the TNC's own timestamp (CONSTAMP / DAYSTAMP).
  This option only controls the timestamp PK232PY adds itself."
- auf die vorhandenen Felder `CONSTAMP`/`DAYSTAMP` im Dialog verweisen
- denselben Zusammenhang in `CLAUDE.md`

**Commit:** `Docs: two sources of timestamps in the packet view`

---

## Teil G — Tests

- MHEARD: `MH`-Antwort und Link-Meldung als Fixture → Rufzeichen in der
  Rufzeichenspalte, Kanal in der Kanalspalte, Zeit in der Zeitspalte
- TX-Echo landet im Kanaldokument **und** im ALL-Dokument
- alle Dokumente tragen dieselbe Schrift
- Firmware aus dem Banner erscheint im Kopfzeilen-Feld
- Maske füllt die Höhe, Makrozeile unten

**Commit:** `Tests: UI findings from the test run`

---

## Definition of Done

- `.venv\Scripts\python.exe -m pytest` grün
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"
- Danach vom Operator: Block 3 bis 5 des Prüfdurchgangs
  (`Pruefdurchgang_P44_bis_P50.md`) erneut