# Claude Code Prompt — P14: Hardware-Prüfwerkzeug für die Solo-Tests

> Ablage: `docs/P14_HW_Solo_Check_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher `CLAUDE.md`, `Backlog.md`, `Testplan.md` und die Abschnitte zu
> Host-Mode-Eintritt/-Austritt in `CLAUDE.md` lesen.

---

## Ziel

Ein Kommandozeilenwerkzeug, mit dem der Operator vier Tests am echten
PK-232MBX ohne Gegenstation durchführt, reproduzierbar und mit Protokoll:

| Test | Frage | sendet auf HF? |
|---|---|---|
| T17 | Ist `PASSALL` im Host Mode `PS` oder `PX`? | nein |
| T103 | Kommt `USERS` beim Upload an? | nein |
| PTHUFF | Wie antwortet der TNC auf das, was der Uploader sendet? | nein |
| T101 | Sendet der TNC Daten auf dem unverbundenen Kanal 0 als UI-Frame nach UNPROTO-Pfad? | **ja** |

Das Werkzeug ersetzt nicht die Anwendung und ist nicht Teil davon. Es lebt
unter `tools/`, wie `mock_tnc_bbs.py`.

---

## Harte Regeln

1. **Vorhandenen Kommunikationscode wiederverwenden.** Serielle Öffnung,
   verbose-Senden mit Prompt-Warten (`write_verbose_wait`), Host-Mode-Eintritt
   und -Austritt, Frame-Aufbau und -Parsing kommen aus `pk232py.comm`. Keine
   zweite serielle Implementierung — die Eigenheiten beim Host-Mode-Wechsel
   sind in `CLAUDE.md` dokumentiert und schon einmal teuer gelernt worden.
2. **Erst abfragen, dann ändern, immer zurückstellen.** Jeder Test liest den
   Ausgangswert jedes Parameters, den er verändert, und stellt ihn am Ende
   wieder her — in einem `try/finally`, also auch bei Abbruch oder Ausnahme.
3. **Keine Aussendung ohne ausdrückliche Bestätigung.** Vor jeder
   HF-Aussendung eine Rückfrage an der Konsole (`y/N`, Default Nein), mit
   Hinweis auf Frequenz, Betriebsart und dass der Sender angeschlossen ist.
   Der Funkamateur muss jede Aussendung selbst freigeben.
4. **`--dry-run`** für jeden Test: zeigt, was gesendet würde, öffnet den
   Port nicht.
5. **Die Anwendung darf nicht gleichzeitig laufen.** Der COM-Port ist
   exklusiv; beim Öffnungsfehler eine klare Meldung „Port busy — is
   pk232py running?" statt eines Tracebacks.
6. **Mnemonic-Grundregel gilt weiter.** Das Werkzeug *misst*, es korrigiert
   nichts im Anwendungscode. Befunde gehen in `Testplan.md` und `Backlog.md`,
   Korrekturen am Code sind ein eigenes späteres Paket.

---

## P14.1 — `tools/hw_check.py`

Aufruf:

```
python tools/hw_check.py --port COM3 t17
python tools/hw_check.py --port COM3 t103
python tools/hw_check.py --port COM3 pthuff
python tools/hw_check.py --port COM3 t101
python tools/hw_check.py --port COM3 all        # t17, t103, pthuff — NICHT t101
python tools/hw_check.py ... --dry-run
```

`all` schließt T101 bewusst aus, weil es sendet und einen zweiten Empfänger
braucht.

Baudrate aus der Anwendungskonfiguration (`TNCConfig.tbaud`), mit
`--baud` überschreibbar.

### Protokoll

Jeder Lauf schreibt eine Datei `hw_logs/YYYYMMDD_HHMMSS_<test>.log`:
Zeitstempel, jeder gesendete Befehl (verbose-Text bzw. Host-Frame in Hex),
jede Antwort roh und dekodiert, Ergebnis je Prüfschritt (`PASS` / `FAIL` /
`INFO`). `hw_logs/` in `.gitignore` aufnehmen — die Ergebnisse werden von
Hand in `Testplan.md` übertragen, die Rohprotokolle bleiben lokal.

Am Ende jedes Laufs eine Zusammenfassung auf der Konsole, die man direkt
in den Testplan übernehmen kann.

---

## Die vier Tests im Detail

### T17 — PASSALL: `PS` oder `PX`

**Befundlage:** Die TRM-Mnemonic-Liste (4.2.2) führt **`PS PASS`** und
**`PX PASSALL`**. `PASS` ist kein Schalter, sondern das Maskierungszeichen
(Standard `$16`, Ctrl-V). Der Anwendungscode sendet für PASSALL `PS` — das
würde also das PASS-Zeichen auf `Y` oder `N` setzen statt PASSALL zu
schalten. Der Test bestätigt das am Gerät, **ausschließlich über Abfragen**:

1. Host Mode betreten
2. `PX` ohne Argument abfragen (`SOH $4F P X ETB`) → Antwort protokollieren.
   Erwartet: ein Y/N-Wert → `PX` ist PASSALL.
3. `PS` ohne Argument abfragen (`SOH $4F P S ETB`) → Antwort protokollieren.
   Erwartet: ein Zeichen- oder Hex-Wert → `PS` ist PASS, nicht PASSALL.
4. Host Mode verlassen

**Keine schreibenden Befehle in T17.** Ein testweises `PS Y` würde das
PASS-Zeichen verändern; das ist unnötig, weil die Abfrage allein die Frage
beantwortet.

Ergebnis in der Zusammenfassung: welche Mnemonic PASSALL ist, und der
Hinweis, dass der Toggle-Button der Packet-Maske korrigiert werden muss,
falls `PX` bestätigt wird.

### T103 — USERS kommt beim Upload an

1. verbose: `USERS` abfragen → Ausgangswert merken
2. eine Konfiguration mit `hf_packet.users = 4` erzeugen (Kopie der
   geladenen Anwendungskonfiguration, **nicht** die INI überschreiben)
3. **den echten `ParamsUploader._build_commands()`** mit dieser
   Konfiguration aufrufen und die Befehle über `write_verbose_wait` senden
4. `USERS` abfragen → erwartet `USERS 4` → `PASS`, sonst `FAIL`
5. im `finally`: Ausgangswert von `USERS` zurückschreiben

**Nebenprodukt, ausdrücklich gewollt:** Weil Schritt 3 den vollständigen
Upload sendet, wird für **jeden** Befehl der Liste die Antwort des TNC
protokolliert. Jede Antwort mit `?What?`, `?bad`, `?too many` oder einer
anderen `?`-Meldung wird in der Zusammenfassung als eigener Befund
aufgeführt. Das ist die erste Hardwarebestätigung der in P13 neu
aufgenommenen Befehle (`RESPTIME`, `ACRPACK`, `8BITCONV`, `HID`, `CFROM`,
`DFROM`, `MFROM`, `MTO`) und der Kern des späteren Verdrahtungstests am
Gerät.

Weil der Upload alle Parameter setzt, vorher **alle** Parameter abfragen,
die er berührt, und im `finally` zurückstellen — oder, einfacher und
sicherer: vor dem Test den Operator darauf hinweisen und eine Rückfrage
stellen, dass der TNC danach mit den Konfigurationswerten der Anwendung
läuft (was beim nächsten Programmstart ohnehin geschieht). CC entscheidet,
welche Variante mit dem vorhandenen Code sauber umsetzbar ist, und
begründet die Wahl im Commit-Text.

### PTHUFF — Antwort auf den gesendeten Wert

**Befundlage:** `PACTORConfig.pthuff` ist ein Bool, der Uploader sendet
`PTHUFF ON` / `PTHUFF OFF`. Laut Spezifikation ist PTHUFF ein Zahlenwert.

1. verbose: `PTHUFF` abfragen → Ausgangswert **und sein Format**
   protokollieren (Zahl oder ON/OFF) — das allein beantwortet schon, welchen
   Typ der Parameter hat
2. genau das senden, was der Uploader senden würde (`PTHUFF ON` bzw. `OFF`,
   aus `_build_commands()` entnommen, nicht nachgebaut) → Antwort
   protokollieren
3. `PTHUFF` erneut abfragen → was steht jetzt drin?
4. im `finally`: Ausgangswert zurückschreiben

Wenn der TNC keine PACTOR-Option hat (`has_pactor` falsch), Test mit
`INFO: no PACTOR option` überspringen.

### T101 — UI-Frame auf unverbundenem Kanal 0

**Sendet auf HF. Braucht einen zweiten Empfänger** (SDR mit Direwolf oder
multimon-ng) auf der Sendefrequenz. Das Werkzeug kann die Aussendung nicht
selbst verifizieren — ob der PK-232 eigene Frames im Monitor zurückmeldet,
ist nicht belegt.

1. Vorab-Hinweis an der Konsole: Frequenz einstellen, Leistung niedrig,
   zweiten Empfänger mit Decoder starten. Weiter erst nach Bestätigung.
2. verbose: `UNPROTO` und `MONITOR` abfragen → Ausgangswerte merken
3. verbose: `UNPROTO TEST1`
4. Host Mode betreten
5. **Rückfrage `y/N`**, dann ein Datenframe auf Kanal 0 senden
   (`SOH $20 <Text> ETB`), Text z. B. `PK232PY T101 A <Uhrzeit>`
6. zwei Sekunden auf eingehende Frames warten und alles protokollieren,
   insbesondere `$4F`/`$5F`-Antworten (Fehler?) und `$3F`-Frames (echot der
   TNC das eigene Frame?)
7. Operator fragen: „Hat der Decoder ein UI-Frame mit Ziel TEST1
   empfangen? (y/n)" → Antwort protokollieren
8. Host Mode verlassen, verbose `UNPROTO TEST2`, Host Mode betreten
9. **Rückfrage `y/N`**, Frame `PK232PY T101 B <Uhrzeit>` senden
10. Operator fragen: „Ziel jetzt TEST2? (y/n)"
11. im `finally`: Host Mode verlassen, `UNPROTO` und `MONITOR`
    zurückstellen

**Auswertung:**

| Decoder zeigt | Bedeutung |
|---|---|
| TEST1, dann TEST2 | UI-Frame über UNPROTO-Pfad bestätigt → `PASS` |
| beide Male dasselbe Ziel | Pfad kommt nicht aus UNPROTO → `FAIL`, Befund |
| nichts, TNC antwortet mit Fehlerframe | Kanal 0 nimmt im Host Mode keine Daten → `FAIL`, Befund |
| nichts, keine Fehlermeldung | Empfänger prüfen, Test wiederholen → `INCONCLUSIVE` |

Zusätzlich festhalten, ob in Schritt 6 ein `$3F`-Echo des eigenen Frames
kam — das beantwortet nebenbei die offene Frage, ob der PK-232 eigene
Aussendungen im Monitor zeigt.

**Commit:** `Tools: hw_check solo hardware tests (T17, T101, T103, PTHUFF)`

---

## P14.2 — `docs/HW_Solo_Tests.md`

Kurze Bedienanleitung für den Operator, zum Ausdrucken:

- Vorbereitung: pk232py beenden, COM-Port, TNC eingeschaltet, für T101
  Sender an Dummy-Load **oder** Antenne mit niedriger Leistung, zweiter
  Empfänger mit Decoder
- Reihenfolge: `all` (T17, T103, PTHUFF), danach getrennt `t101`
- pro Test: Aufruf, was auf der Konsole passiert, welche Rückfragen kommen,
  woran man `PASS`/`FAIL` erkennt
- Tabelle zum Abhaken mit Spalten Test / Datum / Ergebnis / Bemerkung
- Hinweis, wo das Protokoll liegt und dass die Befunde in `Testplan.md`
  übertragen werden

**Commit:** `Docs: operator guide for solo hardware tests`

---

## P14.3 — `Testplan.md` und `Backlog.md`

- T17, T101, T103 und einen neuen Eintrag für PTHUFF auf das Werkzeug
  verweisen lassen (Aufrufzeile), Status bleibt `OPEN` bis zum Lauf am Gerät
- `Backlog.md`: die Vermutung aus T17 notieren (`PS` = PASS, `PX` = PASSALL
  laut TRM; Toggle-Button sendet vermutlich den falschen Befehl), mit
  Verweis auf den Test

**Commit:** `Docs: link solo hardware tests to hw_check`

---

## Definition of Done

- `python tools/hw_check.py --dry-run all` und `--dry-run t101` laufen ohne
  Gerät durch und zeigen jede geplante Sendung
- Unit-Tests für die rein logischen Teile (Aufbau der Abfrage-Frames,
  Auswertung der Antworten, Wiederherstellung im `finally` bei simulierter
  Ausnahme) — ohne echte serielle Schnittstelle
- Kein Code unter `src/pk232py/` verändert, außer Importe wären ohne eine
  kleine öffentliche Hilfsfunktion nicht möglich; dann im Commit-Text
  begründen
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"