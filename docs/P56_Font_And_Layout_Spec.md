# Claude Code Prompt — P56: Eine Schriftquelle, Maske füllt das Fenster

> Ablage: `docs/P56_Font_And_Layout_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Belege: drei Screenshots vom 26.09.2026 (maximiertes Fenster,
> CH-Ansicht, ALL-Ansicht).

**Erledigt:** Firmware wird beim Init gelesen und angezeigt
(`Release 01.AUG.91`). MHEARD steht noch aus — der Operator hat derzeit
keine Gegenstation.

---

## Teil A — Die Schrift hat zwei Quellen

### Befund
In der **ALL**-Ansicht stimmt die Schrift: sie entspricht der
Appearance-Einstellung des Bedieners (Cascadia Mono SemiBold 14 pt, im
Log sichtbar: `Appearance applied: Cascadia Mono SemiBold 14pt`).
In der **CH**-Ansicht ist sie kleiner.

Ursache: P55 Teil C hat eine Konstante `_RX_FONT` eingeführt und auf die
Kanaldokumente gesetzt. Das ALL-Dokument ist das ursprüngliche Dokument
des Textfelds und trägt weiterhin die Appearance-Schrift. **Zwei Quellen
für dieselbe Sache.**

### A.1 Eine Quelle
- `_RX_FONT` entfällt. Alle RX-Dokumente — die der Kanäle **und** das
  ALL-Dokument — erhalten die Schrift aus der Appearance-Einstellung,
  aus derselben Stelle, die sie heute schon auf das Textfeld anwendet
- beim Erzeugen eines Dokuments wird sie gesetzt
  (`setDefaultFont()`), und bei einer **Änderung der
  Appearance-Einstellung** werden alle vorhandenen Dokumente
  nachgezogen — auch die, die gerade nicht sichtbar sind
- prüfen, ob das TX-Feld und das MHEARD-Panel an derselben Quelle hängen;
  falls nicht, im Commit-Text nennen (nicht ungefragt ändern)

### A.2 Test
- Appearance auf eine deutlich andere Größe stellen, zwischen ALL und CH
  umschalten, einen neuen Kanal öffnen → überall dieselbe Schrift
- ein Dokument, das vor der Änderung entstand, trägt danach die neue
  Schrift

**Commit:** `Packet screen: RX documents use the appearance font, not a constant`

---

## Teil B — Die Maske füllt das Fenster nicht

### Befund
Im maximierten Fenster (2560 × 1440) endet der Inhalt bei etwa einem
Drittel der Höhe; darunter ist alles leer. Die Makrozeile steht in der
Mitte des Bildschirms, nicht unten.

P55 Teil E konnte keinen Fehler reproduzieren — vermutlich, weil die
Messung an einem nicht maximierten Fenster oder ohne die tatsächliche
Widget-Verschachtelung stattfand.

### B.1 Zuerst prüfen: Scrollbereich
Wahrscheinlichste Ursache: Die Maske sitzt in einem `QScrollArea`, dessen
`widgetResizable` **nicht** gesetzt ist. Dann behält das eingebettete
Widget seine natürliche Höhe, und darunter bleibt Leerraum — genau das
beobachtete Bild.

- prüfen, ob ein `QScrollArea` im Weg ist (`mockup`-Basis und die
  Produktivmasken importieren einen); falls ja:
  `setWidgetResizable(True)`
- falls kein Scrollbereich beteiligt ist: die Kette der Layouts vom
  zentralen Widget bis zur Makrozeile durchgehen und den fehlenden
  Stretch-Faktor bzw. die fehlende `QSizePolicy` benennen

### B.2 Sollzustand
- die Maske dehnt sich über die volle Fensterhöhe
- der RX/TX-Splitter bekommt den verbleibenden Platz (Stretch)
- die Makrozeile sitzt **am unteren Rand**
- die Statuszeile bleibt darunter

### B.3 Messbar prüfen
Ein Test, der die Behauptung belegt statt sie zu beschreiben: Fenster auf
eine feste Größe setzen (etwa 1600 × 1200), Maske aufbauen, `show()`,
Ereignisse abarbeiten — die Unterkante der Makrozeile muss innerhalb
weniger Pixel an der Unterkante des Inhaltsbereichs liegen.

Ein Test, der nur prüft, ob eine `QSizePolicy` gesetzt ist, genügt
nicht — P55 Teil E hat gezeigt, dass das nichts über die tatsächliche
Geometrie aussagt.

### B.4 Für alle Masken
Die Korrektur an **einer** Stelle, damit sie für Baudot, AMTOR, PACTOR,
Morse, NAVTEX, Signal und Packet gleichermaßen gilt. Im Commit-Text
nennen, welche Masken betroffen waren.

**Commit:** `Opmode screens: the screen fills the window height`

---

## Teil C — Dokumentation

- `CLAUDE.md`, UI-Abschnitt: **Schrift kommt aus der
  Appearance-Einstellung**, nicht aus Konstanten in den Masken; neue
  Textdokumente ziehen sie beim Erzeugen und bei Änderungen nach
- ergänzen: Geometrie-Behauptungen werden **gemessen**, nicht über
  gesetzte Eigenschaften geprüft (Lehre aus P55 Teil E)

**Commit:** `Docs: one font source, measure geometry in tests`

---

## Definition of Done

- `.venv\Scripts\python.exe -m pytest` grün
- Der Geometrietest aus B.3 ist ohne den Fix rot — gegengeprüft
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"
- Danach vom Operator: Fenster maximieren, zwischen ALL und CH
  umschalten