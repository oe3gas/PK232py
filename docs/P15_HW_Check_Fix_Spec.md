# Claude Code Prompt — P15: hw_check reparieren + Ergebnisse festhalten

> Ablage: `docs/P15_HW_Check_Fix_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Die beiden Konsolenmitschnitte vom 21.09.2026 (Lauf `all` und zwei Läufe
> `t101`) liegen dem Operator vor — CC bittet darum, falls sie nicht unter
> `hw_logs/` zu finden sind.

---

## Befunde aus dem ersten Lauf am Gerät

### Am Werkzeug

1. **T17 lief im verbose-Modus.** Gesendet wurde `PX\r\n` und `PS\r\n` im
   verbose-Modus → beide `?What?`. Zwei-Buchstaben-Mnemonics gibt es nur im
   Host Mode. Die Spezifikation P14 verlangte
   `SOH $4F P X ETB` bzw. `SOH $4F P S ETB` nach Host-Mode-Eintritt.
2. **Der Wert-Parser nimmt die Eingabeaufforderung als Wert.** Gesendet
   wurden `PTHUFF cmd:`, `UNPROTO cmd:`, `MONITOR cmd:` → `?bad` bzw.
   `?callsign`. Bei `USERS` hat es funktioniert — der Parser arbeitet nicht
   einheitlich.
3. **Die Wiederherstellung meldet Erfolg ohne Prüfung.** Nach `?callsign`
   und `?bad` kam trotzdem `UNPROTO/MONITOR restored`. Folge: der TNC blieb
   auf `UNPROTO TEST2` stehen.
4. **Bei PTHUFF wurde vor dem eigentlichen Test bereits ein fehlerhafter
   Setzbefehl gesendet** (`PTHUFF cmd:` vor `PTHUFF OFF`). Ursache klären
   — vermutlich derselbe Parser, der in `run_with_restore()` den Ausgangswert
   vorab zurückschreibt.

### Am Gerät bestätigt

- **T103 PASS**: `USERS 4` nach Upload bestätigt, Wiederherstellung auf 1
  korrekt
- **Alle 68 Upload-Befehle ohne `?`-Antwort** — damit sind `RESPTIME`,
  `ACRPACK`, `CFROM`, `DFROM`, `MFROM`, `MTO`, `8BITCONV`, `HID` am Gerät
  belegt; der TNC meldet `ACRPack`, die Umbenennung aus P13 war richtig
- **T101 PASS** (zweiter Lauf): UI-Frame auf unverbundenem Kanal 0 geht
  nach UNPROTO-Pfad raus, Gegenprobe TEST1/TEST2 eindeutig. Erster Lauf
  Runde A negativ, vom Operator als Empfängereffekt eingeschätzt; die
  TNC-Antworten waren in allen vier Aussendungen identisch
- **Kein `$3F`-Echo eigener Aussendungen**, auch nicht bei `MONITOR 6`.
  Der PK-232 zeigt eigene Frames im Host Mode nicht im Monitor
- **Antwort des TNC auf jedes Datenframe:** `ctl=0x5F ch=15 data=b'XX\x00'`
  — Bedeutung gegen TRM 4.4 prüfen und dokumentieren, kein Fehlerframe
- **PTHUFF:** numerisch (`PTHuff 0`); `PTHUFF OFF` wird ohne Fehler
  angenommen und belässt den Wert bei 0. `PTHUFF ON` ungetestet

---

## P15.1 — Antwort-Parser auf echte TNC-Antworten umstellen

Eine zentrale Funktion in `tools/hw_check.py`, die alle Abfragen und
Wiederherstellungen benutzt:

```python
def parse_query_value(command: str, response: str) -> str | None:
    """Wert aus einer verbose-Abfrageantwort des PK-232.

    Reale Form:
        '<ECHO>\\r\\n<Name>   <Wert>[ (<Erläuterung>)]\\r\\ncmd:'
    Beispiele aus dem Gerät (21.09.2026):
        'USERS\\r\\nUSers     1\\r\\ncmd:'                     -> '1'
        'PTHUFF\\r\\nPTHuff    0\\r\\ncmd:'                    -> '0'
        'UNPROTO\\r\\nUnproto   CQ\\r\\ncmd:'                  -> 'CQ'
        'MONITOR\\r\\nMonitor   6 (seq, P/F + all)\\r\\ncmd:'  -> '6'
        'TXDELAY\\r\\nTXdelay   30 (300 msec.)\\r\\ncmd:'      -> '30'
        'CANLINE\\r\\nCANline   $18 (CTRL-X)\\r\\ncmd:'        -> '$18'
    Liefert None, wenn keine Wertzeile gefunden wird oder die Antwort
    mit '?' beginnt.
    """
```

Regeln:

- Echozeile (erste Zeile) und abschließendes `cmd:` verwerfen
- Wertzeile: Name steht in gemischter Schreibweise (`USers`), Vergleich
  ohne Groß-/Kleinschreibung gegen den abgefragten Befehl
- Erläuterung in runden Klammern am Ende abschneiden
- **Mehrwortige Werte erhalten**: `UNPROTO CQ VIA WIDE1-1` muss vollständig
  zurückkommen, nicht nur `CQ`. Nur die Klammer-Erläuterung wird entfernt
- Text-Parameter mit Zeilenumbruch im Wert (`MTEXT` hatte zwei Zeilen)
  zunächst **nicht** unterstützen: `None` zurückgeben und den Test mit
  `INFO: multi-line value, restore skipped` fortsetzen, statt einen
  abgeschnittenen Wert zurückzuschreiben

**Unit-Tests mit den echten Antworten** aus den Mitschnitten vom
21.09.2026 als Fixtures — mindestens die sechs Beispiele oben, dazu
`?What?`, `?bad`, eine `was/now`-Antwort und die zweizeilige
MTEXT-Antwort. Die bisherigen idealisierten Antworten in
`test_hw_check.py` durch diese ersetzen oder ergänzen. Das ist die
eigentliche Lehre dieses Pakets: die 18 vorhandenen Tests haben keinen der
Fehler gefunden, weil sie mit Antworten arbeiteten, die der TNC so nicht
schickt.

---

## P15.2 — Wiederherstellung mit Nachweis

`run_with_restore()`:

1. vor der Änderung: Ausgangswert mit `parse_query_value()` lesen; ist er
   `None`, **nichts ändern**, Test als `SKIPPED` melden — ohne sicheren
   Ausgangswert keine Änderung
2. **kein Setzbefehl vor der eigentlichen Testaktion** (siehe Befund 4)
3. nach dem Zurückschreiben: erneut abfragen und vergleichen
4. Meldung nur bei Übereinstimmung `restored`; sonst **`FAIL: restore of
   <PARAM> failed — TNC now reports <Wert>, expected <Wert>`**, deutlich
   sichtbar in der Zusammenfassung, mit der Zeile, die der Operator von
   Hand eingeben muss (`UNPROTO CQ`)

Unit-Test mit simulierter fehlgeschlagener Wiederherstellung: die Meldung
darf dann auf keinen Fall `restored` lauten.

---

## P15.3 — T17 im Host Mode

1. Host Mode betreten (vorhandene Funktion aus `pk232py.comm`)
2. `SOH $4F P X ETB` senden, Antwortframe protokollieren (roh und
   dekodiert)
3. `SOH $4F P S ETB` senden, ebenso
4. Host Mode verlassen

Auswertung:

| Antwort auf PX | Antwort auf PS | Ergebnis |
|---|---|---|
| Y oder N | Zeichen/Hex-Wert | `PX` = PASSALL, `PS` = PASS → **PASS**, Befund: Toggle-Button muss auf `PX` |
| Zeichen/Hex-Wert | Y oder N | umgekehrt → **PASS**, Button ist richtig |
| Fehlerframe | Fehlerframe | **INCONCLUSIVE**, beide Frames im Protokoll |

Weiterhin **nur Abfragen**, keine schreibenden Befehle.

**Commits (je Datei):**

```
Tools: hw_check parses real TNC responses and verifies restores
Tests: hw_check fixtures from real PK-232 responses
```

---

## P15.4 — Dokumentation der Ergebnisse

### `Testplan.md`

- **T103**: PASS, 21.09.2026, mit Verweis auf den Upload ohne `?`-Fehler
- **T101**: PASS, 21.09.2026 (zweiter Lauf), erster Lauf Runde A als
  Empfängereffekt vermerkt
- **PTHUFF**: FAIL (Typ), mit dem beobachteten Verhalten
- **T86 (PASSALL)**: bleibt OPEN, Vermerk: erster Lauf ungültig
  (verbose-Modus), Wiederholung nach P15

### `CLAUDE.md`

- Der PK-232 zeigt eigene Aussendungen im Host Mode **nicht** als
  `$3F`-Frame, auch nicht bei `MONITOR 6` (Hardwarebefund 21.09.2026)
- Die 68 Upload-Befehle sind am Gerät bestätigt; Liste der P13-Befehle
  ausdrücklich nennen
- Format der verbose-Abfrageantworten (Echo, `Name   Wert (Erläuterung)`,
  `cmd:`), mit Hinweis auf `parse_query_value()`
- Bedeutung der `$5F`-Antwort `XX\x00` nach einem Datenframe, sobald im
  TRM geklärt

### `Backlog.md`

- `PTHUFF`: Typ auf Zahl umstellen; Wertebereich aus dem Handbuch belegen,
  nicht raten
- `MYALTCAL`: der TNC schreibt `OE3GAS` zu `OGAS` um — es ist ein
  vierstelliger AMTOR-SELCAL, kein Rufzeichen. Dialog und Config
  entsprechend behandeln
- **VHF-Parametersatz**: der Band-Umschalter der Packet-Maske zeigt für
  VHF `MAXFRAME 4 · PACLEN 128` an, der Upload sendet aber immer die
  HF-Werte (beobachtet: 128→64, 4→1, FRACK 4→7). Eigenes Paket für das
  PR-Modul
- Der Init überschreibt TNC-eigene Texte mit Config-Defaults (beobachtet:
  `MTEXT`). Prüfen, ob Standardtexte bei leerer Config überhaupt gesendet
  werden sollen

**Commit:** `Docs: first hardware run results 2026-09-21`

---

## Definition of Done

- `python -m pytest` grün, neue Fixture-Tests eingeschlossen
- Ein Unit-Test beweist: bei fehlgeschlagener Wiederherstellung erscheint
  **nicht** das Wort `restored`
- `--dry-run t17` zeigt die Host-Frames in Hex
- Kein Code unter `src/pk232py/` verändert
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"
- Danach vom Operator: `python tools/hw_check.py --port COM6 t17` erneut