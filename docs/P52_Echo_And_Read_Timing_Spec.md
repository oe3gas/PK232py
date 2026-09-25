# Claude Code Prompt — P52: Echo ist keine Antwort, und es wird zu kurz gelesen

> Ablage: `docs/P52_Echo_And_Read_Timing_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> **Ersetzt Teil A von `P51_Pruefdurchgang_Befunde_Spec.md`** — die
> Ursache ist durch den Konsolenmitschnitt vom 25.09.2026, 23:30 belegt.
> Die übrigen Teile von P51 (B bis I) bleiben gültig.

---

## Belegte Ursache

Mitschnitt des fehlgeschlagenen Verbindungsaufbaus:

```
23:30:43,174  Init: step 1 TX: 2a
23:30:43,358  Init: step 1 response (4 B): 2a 5c 0d 0a
23:30:43,358  Init: step 2 - CR (already awake?)
23:30:43,563  Init: step 2 response (2 B): 0d 0a
23:30:43,564  Init: step 3 TX: 01 4f 48 50 17
23:30:43,585  Init: step 3 raw (5 B): 01 4f 48 50 17  -- 1 frame(s)
23:30:43,585  Init: step 3 confirmed Host Mode (0x4F frame) - exiting to verbose
23:30:43,585  Init: step 3 exit TX: 01 4f 48 4f 4e 17
23:30:44,032  Init: post-exit response (8 B): 01 4f 48 4f 4e 17 0d 0a
23:30:44,032  ERROR Init: Host Mode exit did not reach cmd:
```

### Fehler 1 — Das Echo wird für eine Antwort gehalten
Die „Antwort" in Schritt 3 ist **byteweise identisch mit dem Gesendeten**.
Im verbose-Befehlsmodus echot der PK-232 **jedes** Zeichen, auch
Binärbytes. Eine echte HPOLL-Antwort ist **sechs** Bytes lang und enthält
den Wert — im selben Mitschnitt um 23:30:09 belegt:

```
TX (6 B): 01 4f 48 50 4e 17
RX (6 B): 01 4f 48 50 00 17      <- echte Antwort, Wertbyte 00
```

Die Kette hielt also einen verbose-TNC für einen Host-Mode-TNC, schickte
`HOST OFF` — ebenfalls nur echot — und gab auf.

### Fehler 2 — Zu kurz gelesen
Schritt 1: 184 ms, dann Abbruch mit 4 Bytes. Im geglückten Lauf vom
23.09.2026 kam an derselben Stelle `2a 5c 0d 0a 63 6d 64 3a`, also
`*\` CRLF **`cmd:`**. Die vier Bytes sind dieselbe Antwort, nur
abgeschnitten — das `cmd:` war noch unterwegs.

Dasselbe bei Schritt 2 (205 ms) und bei der Upload-Prüfung:

```
ParamsUploader: no answer verifying MYCALL (expected 'OE3GAS')
ParamsUploader: no answer verifying PACLEN (expected '64')
ParamsUploader: no answer verifying MAXFRAME (expected '1')
```

Damit ist auch P51 Teil F erklärt: Die Zeile `parameter upload verified
(3/3)` fehlte nicht in der Anzeige — sie ist nie entstanden.

**Der TNC war durchgehend ansprechbar.** Die gescheiterte Recovery
erklärt sich mit, weil sie dieselbe Kette fährt.

---

## P52.1 — Lesen bis zum Erwarteten, nicht bis zur ersten Pause

Die Lesefunktion der Erkennungskette und der Upload-Prüfung liest künftig
**bis das erwartete Muster erscheint oder die Zeitgrenze abläuft** — nicht
bis zur ersten Ruhephase.

- erwartetes Muster: `cmd:` (Erkennungskette, Upload-Prüfung)
- Zeitgrenze wie festgelegt **1,5 s** je Schritt; sie wird ausgeschöpft,
  wenn das Muster ausbleibt
- Rückgabe: alles bis dahin Gelesene, plus ein Kennzeichen, ob das Muster
  gefunden wurde
- die vorhandene Ruhe-Erkennung (`read_until_idle`) bleibt, wo sie richtig
  ist — etwa im Mailbox-Terminal, wo kein festes Muster existiert. **Nicht
  ersetzen**, sondern die passende Funktion an der passenden Stelle
  verwenden

Prüfen, ob es bereits eine Funktion mit dieser Semantik gibt (im Werkzeug
existiert sie), und **eine** gemeinsame Umsetzung anstreben.

**Commit:** `SerialManager: read until the expected prompt, not until the first pause`

---

## P52.2 — Echo erkennen

In der Erkennungskette, Schritt 3:

- die Antwort gilt **nicht** als Host-Mode-Frame, wenn sie byteweise
  gleich dem Gesendeten ist
- ein gültiger `$4F`-Antwortframe hat die Form
  `SOH $4F <m1> <m2> <wert> ETB` — **sechs** Bytes; die Abfrage, die wir
  senden, hat fünf. Länge und Wertbyte mit prüfen
- dasselbe gilt nach dem `HOST OFF`-Frame: ein Echo ist keine Bestätigung

Logzeile bei Echo: `step 3: response equals the frame we sent (echo) —
TNC is in verbose mode, not Host Mode`.

**Commit:** `SerialManager: an echo is not a Host Mode response`

---

## P52.3 — Upload-Prüfung

Mit P52.1 liefert die Stichprobe wieder Werte. Zusätzlich:

- bleibt eine Abfrage trotz voller Zeitgrenze ohne Antwort, das im
  Terminal sichtbar machen (nicht nur in der Konsole), zusammen mit der
  `verified (n/n)`-Zeile aus P51 Teil F
- stimmen Soll und Ist nicht überein, beides nennen

**Commit:** `Params uploader: verification uses the corrected read`

---

## P52.4 — Tests

Mit **echten** Byte-Folgen aus den Mitschnitten:

- Antwort kommt in zwei Stücken (`2a 5c 0d 0a`, dann `63 6d 64 3a`) →
  die Funktion wartet und findet `cmd:`
- Antwort bleibt ganz aus → volle Zeitgrenze, Kennzeichen „nicht
  gefunden"
- Schritt 3: Rückgabe `01 4f 48 50 17` (Echo) → **kein** Host Mode
- Schritt 3: Rückgabe `01 4f 48 50 00 17` → Host Mode erkannt
- Upload-Prüfung: `MYcall    OE3GAS` nach 400 ms → erkannt

**Commit:** `Tests: prompt-terminated reads and echo detection`

---

## P52.5 — Dokumentation

`CLAUDE.md`, Fallstricke:

- **Im verbose-Befehlsmodus echot der PK-232 alles**, auch Binärframes.
  Ein Echo ist keine Antwort: Antwortframes sind länger und tragen ein
  Wertbyte
- **Nicht bis zur ersten Pause lesen, sondern bis zum erwarteten Muster.**
  Bei 9600 Bd kommen `cmd:`-Prompt und Banner in Stücken; eine Pause von
  200 ms bedeutet nicht, dass die Antwort vollständig ist (belegt
  25.09.2026: 4 statt 8 Bytes, das `cmd:` fehlte)

`SERIAL_CONNECTION_STATE_MACHINE.md`: beide Punkte in der Beschreibung der
Kette ergänzen.

`Testplan.md`: Fall — Verbindung trennen und sofort neu verbinden; es darf
keine Fehlermeldung „No PK-232 responding" geben.

**Commit:** `Docs: echo is not a response, read until the prompt`

---

## Definition of Done

- `.venv\Scripts\python.exe -m pytest` grün
- Der Echo-Test ist ohne P52.2 rot, der Stück-für-Stück-Test ohne P52.1 —
  beide kurz gegengeprüft
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"
- Danach vom Operator: Block 1 und 2 des Prüfdurchgangs erneut