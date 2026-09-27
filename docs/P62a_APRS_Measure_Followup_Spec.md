# Claude Code Prompt — P62a: APRS-Messpaket nachbessern — PACLEN, Paste-Ende, A.6, Direwolf als Anrufer

> Ablage: `docs/P62a_APRS_Measure_Followup_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Grundlage: `main` @ `2acdaf7` und die ersten Hardware-Läufe T138/T139 vom
> 27.09.2026 an **Gerät B (Release 01.AUG.91)**.
> Weiterhin **nur Messung** (hw_check-Regel 6).

---

## Teil 0 — Ergebnisse der ersten Läufe eintragen

In `Testplan.md` bei T138/T139 je eine Ergebniszeile **Gerät B, 27.09.2026**.
Die Läufe zeigten `device: unknown (no banner - TNC was already awake)`;
die Gerätezuordnung stammt vom Betreiber (siehe `docs/DEVICES.md`, Regel
„der `device:`-Zeile glauben, nicht raten" — hier gab es keine, daher
Betreiberangabe, so kennzeichnen).

### T138 `aprs_query` — Gerät B
| Schritt | Ergebnis | Befund |
|---|---|---|
| A.2 | PASS | `UNPROTO APZ232 VIA WIDE1-1,WIDE2-1` verbose angenommen |
| A.3 | PASS | derselbe Pfad über Host-Frame `UN` gesetzt, verbose bestätigt |
| A.4 | INFO | Host-Abfrage `UN` liefert `UNAPZ232 via WIDE1-1, WIDE2-1` — **`via` klein, Leerzeichen nach dem Komma** |
| A.5 | PASS | `CF NONE` / `CF ALL` im Host Mode wirksam |
| A.6 | **nicht auswertbar** | nach dem 9-Digi-Versuch zeigt die Abfrage die 8 Digis des **vorherigen** Schritts — abgeschnitten oder abgelehnt ist nicht unterscheidbar (Messfehler der P62-Spec, Teil B unten) |

### T139 `aprs_tx` — Gerät B, `PACLEN 64`
| Runde | Ergebnis | Befund |
|---|---|---|
| R1 | PASS | Ziel `APZ232`, Info exakt, **kein angehängtes CR** |
| R2 | PASS | Pfad `WIDE1-1,WIDE2-1` exakt, H-Bits ungesetzt (Direwolf ohne `*`) |
| R3 | **ungültig** | Probe 106 Zeichen > PACLEN 64 → 2 Frames; eingefügt wurden versehentlich R2-Zeilen. Zeichentreue weiterhin **ungeprüft** |
| R4 | **Befund** | 204 Zeichen → **4 UI-Frames: 64 + 64 + 64 + 12 Byte**, Schnitt exakt an PACLEN. Belegt durch die Direwolf-Zeilen (Folgeframes beginnen mit `6789…`, `0123…`, `45678901 END`; Direwolf: „Unknown APRS Data Type Indicator") |
| R5 | übersprungen | Rest des Pastes landete in der Bestätigungsfrage |

**Kernbefund für P63:** Daten auf Kanal 0 werden in UI-Frames zu je höchstens
`PACLEN` Byte zerlegt. Eine APRS-Meldung muss in **einem** Frame stehen →
der APRS-Modus muss PACLEN besitzen und setzen wie UNPROTO.

Nebenbefund Direwolf: `>PK232PY …` wird als Status mit Maidenhead-Locator
gedeutet (`PK23` + Overlay `2` + Symbol `P`), daher „Found 'Y' instead of
space". Kein TNC-Befund; für P63 notieren: Statustexte, die mit zwei
Buchstaben und zwei Ziffern beginnen, werden fehlgedeutet.

**Commit:** `Testplan: T138 T139 first results on device B`

---

## Teil A — Paste-Eingabe mit eindeutigem Ende

Befund: Die Eingabe endet an der ersten Leerzeile. Direwolf setzt zwischen
Pakete selbst Leerzeilen → bei mehreren Frames (R4) bricht das Einlesen ab,
der Rest landete in der Frame-Zahl-Frage, der R5-Bestätigung und danach in
**PowerShell**, wo jede Zeile als Befehl ausgeführt wurde (diesmal nur
Fehlermeldungen).

- Eine Hilfsfunktion `read_pasted_block(prompt: str) -> str`, einzige Stelle
  für mehrzeilige Eingaben in `hw_check.py`. Ende: eine Zeile, die nur
  `.` enthält. Leerzeilen gehören zum Inhalt.
- Aufforderungstext: `Paste the decoder output, then a line with a single
  "." to finish:`
- Die Frage nach der Frame-Anzahl entfällt: `evaluate_aprs_round()` zählt
  Frames selbst aus dem eingefügten Text (Zeilen der Form
  `[<Kanal>] <QUELLE>><ZIEL>…:`). Die Betreiberzahl war die zweite
  Fehlerquelle in R4.
- Vor **jeder** `confirm_tx()`-Frage den Eingabepuffer nicht verwerfen,
  sondern die Frage wiederholen, bis genau `y`, `n` oder leer kommt — eine
  eingefügte Direwolf-Zeile darf nie als Antwort gelten.

Tests (zuerst rot): Block mit Leerzeilen zwischen zwei Frames wird
vollständig gelesen; Frame-Zählung 1/2/4 aus echten Direwolf-Zeilen (die
R4-Zeilen aus Teil 0 als Testdaten); `confirm_tx` mit Eingabe
`[0.5] OE3GAS>APZ232:…` → fragt erneut.

**Commit:** `hw_check: paste block ends with a dot line, frames counted from the paste`

---

## Teil B — `aprs_query` erweitern

### B.1 A.6 richtig messen
Vor dem 9-Digi-Versuch UNPROTO auf `CQ` setzen. Die **Antwort des
Setzbefehls** (nicht nur die Abfrage) loggen. Auswertung als `INFO` mit
einer von drei Aussagen: `rejected` (Abfrage zeigt `CQ`), `truncated`
(Abfrage zeigt 8 Digis), `accepted` (9 Digis).

### B.2 Neu: A.7 PACLEN-Bereich
Verbose, mit Wiederherstellung (`run_with_restore`): nacheinander
`PACLEN 128`, `255`, `256`, `0` setzen, je Setzantwort und Abfrage
wörtlich loggen. Frage: Welcher Höchstwert, und was bedeutet `0`?

### B.3 Neu: A.8 PACLEN im Host Mode
Wie A.5 mit `CF`: Host-Frame `build_command(b"PL", b"128")` → verbose
Abfrage → erwartet `128`; danach Host-Abfrage `query_host(b"PL")` wörtlich.
`PL` ist in der Firmware-Matrix nur Hypothese (Konfidenz M). P63 braucht
PACLEN im Host Mode, weil der Moduswechsel dort stattfindet.

**Commits:**
```
hw_check: aprs_query A.6 from a different prior value
hw_check: aprs_query A.7 PACLEN range and A.8 PL in Host Mode
```

---

## Teil C — `aprs_tx` nachbessern

### C.1 Ausgangszustand herstellen
Befund aus der Vorbesprechung: `aprs_tx`/`aprs_reject` rufen `normalize()`
nicht auf (nur `aprs_query` tut es). Nach dem Einschalten stünde MYCALL auf
`PK232` — Aussendung ohne eigenes Rufzeichen.

- `session.normalize()` am Anfang von `aprs_tx` **und** `aprs_reject`.
- `VHF` und `HBAUD` abfragen und anzeigen; stehen sie nicht auf `ON`/`1200`,
  fragt das Programm: `TNC is not on VHF 1200 Bd (VHF=…, HBAUD=…). Set VHF ON
  and HBAUD 1200 for this run? [y/N]` — bei `y` setzen und in
  `run_with_restore` zurücksetzen, bei `N` abbrechen (`INFO`).

### C.2 R3 mit PACLEN, das die Probe fasst
R3 setzt `PACLEN 128` (verbose, mit Wiederherstellung), damit R3 **nur** die
Zeichentreue misst. R4 bleibt absichtlich beim Gerätewert und misst die
Zerlegung — Kommentar im Code, warum die beiden Runden das unterschiedlich
machen.

### C.3 Neue Runde R6: 200 Zeichen in einem Frame
Nach A.7 bekannt ist, welcher Höchstwert gilt: R6 setzt PACLEN auf den
Wert, den A.7 als größten angenommenen gemeldet hat (aus der Abfrage im
selben Lauf, nicht fest codiert), und sendet das R4-Info-Feld erneut.
Erwartung: 1 Frame. Ist A.7 im selben Lauf nicht gelaufen, fragt das
Programm den Betreiber nach dem Wert.

### C.4 Statustexte
Info-Felder der Runden R1/R2/R5 beginnen mit `>Test PK232PY …` statt
`>PK232PY …`, damit Direwolf sie nicht als Locator-Status deutet.

**Commits:**
```
hw_check: aprs_tx and aprs_reject normalize and check VHF/HBAUD
hw_check: aprs_tx R3 with PACLEN 128, new R6 single-frame 200 chars
```

---

## Teil D — `aprs_reject` mit Direwolf als Anrufer

Der Betreiber hat nur einen PK-232. Anrufer ist **Direwolf** (AX.25
Connected Mode über die AGW-Schnittstelle, ab Direwolf 1.4) mit einem
AGW-fähigen Terminal (z. B. QtTermTCP von G8BPQ).

- Vorab-Hinweistext im Programm:
  ```
  Calling station: Direwolf on the second radio, connected mode via AGW.
    - direwolf.conf needs PTT configured (Direwolf must transmit),
      MYCALL different from this TNC (e.g. OE3GAS-1), AGWPORT 8000.
    - Terminal (e.g. QtTermTCP) connected to localhost:8000.
  ```
- Die Frage nach dem Gerät der Gegenstation (A/B/C) entfällt; stattdessen
  `Calling station software (e.g. Direwolf 1.7 + QtTermTCP)?` — wörtlich
  loggen.
- Anweisung je Phase: `From the terminal, connect to <MYCALL> now` — MYCALL
  aus der vorherigen `normalize()`-Abfrage, nicht fest codiert.
- Frage nach der Anzeige der rufenden Station über `read_pasted_block()`
  (Teil A).
- Frage nach der SEND-LED bleibt.

**Commit:** `hw_check: aprs_reject with Direwolf/AGW as the calling station`

---

## Teil E — Tests und Doku

- Tests aus Teil A; für B/C/D je ein Dry-Run-Test, der die neuen Befehle
  (A.6 mit `CQ` davor, A.7-Folge, `PL`-Frame, `PACLEN 128` vor R3, R6)
  in der Vorschau zeigt.
- `Backlog.md`: „APRS-Modus P63: PACLEN gehört dem Modus (Befund T139 R4,
  Gerät B) — Wert aus T138 A.7."
- `CLAUDE.md`, Known Gotchas (Gerät B nennen): Daten auf Kanal 0 werden in
  PACLEN-große UI-Frames zerlegt; Host-Abfrage `UN` formatiert den Pfad um.
- `Testplan.md`: T138 um A.7/A.8, T139 um R6 ergänzen (OPEN).

**Commits:**
```
Tests: hw_check APRS follow-up
Docs: CLAUDE.md PACLEN splits channel 0 data (device B)
Backlog: P63 owns PACLEN
Docs: add P62a spec file
```

---

## Definition of Done

- betroffene Tests zuerst rot, volle Suite vor dem Push grün
- `grep -n 'line == ""' tools/hw_check.py` → keine mehrzeilige Eingabe
  endet mehr an einer Leerzeile
- Dry-Run aller drei Unterbefehle zeigt die neuen Schritte
- **Push**, Meldung mit Hash; `.\Sources2Text.ps1`, „sources aktualisiert"