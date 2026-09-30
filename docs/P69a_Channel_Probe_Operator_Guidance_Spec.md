# Claude Code Prompt — P69a: `channel_probe` — klare Betreiberführung, Teile getrennt, ein Paste statt vieler

> Ablage: `docs/P69a_Channel_Probe_Operator_Guidance_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Grundlage: `main` @ `f79bba4`. Ersetzt die mündlich weitergegebene
> `--part`-Anweisung vom 29.09.2026 (in dieses Paket integriert).
> Nur Werkzeug, **keine** Änderung an `src/`.

---

## Befund

Betreiber, 29.09.2026: Der Ablauf von `channel_probe` ist nicht
durchführbar; mehrere Läufe mussten abgebrochen werden.

Aufbau des Betreibers (fest, `docs/DEVICES.md`):

- **PC 1:** `hw_check.py`, PK-232 (Gerät B) am TS-790E
- **PC 2:** Direwolf am FT-818, TinyBox (`OE3GAS-1`), QtTermTCP über AGW

Ursachen im Werkzeug:

1. Keine Anweisung sagt, **an welchem PC** etwas zu tun ist.
2. Es gibt keine Übersicht: Der Betreiber weiß nicht, wie viele Schritte
   kommen und wo er gerade steht.
3. Nach **jeder** Aussendung muss er an PC 2 Direwolf-Zeilen kopieren und
   an PC 1 einfügen — in B dreimal hin und her.
4. In C startet nach `y` ein 60-s-Fenster, in dem er an PC 2 wechseln,
   QtTermTCP bedienen und zurückkommen muss — Zeitdruck ohne Anzeige.
5. `--part` fehlt: T147 lässt sich nicht ohne T146 fahren.

---

## Teil A — Eine Stelle für Betreieranweisungen: `operator_step()`

Neue Funktion in `tools/hw_check.py`, einzige Stelle, die
Betreieranweisungen ausgibt (für `channel_probe`; andere Unterbefehle
folgen später, Backlog):

```python
def operator_step(
    run: "StepRun", title: str, where: str, do: list[str], then: str,
) -> None
```

Ausgabe, immer gleich aufgebaut:

```
==============================================================
STEP 4 of 11   T146 B.3   (about 2 minutes)
WHERE: PC 2  - Direwolf / TinyBox / QtTermTCP
DO:
  1. Look at the Direwolf window.
  2. Nothing to type there - just watch for new lines.
THEN: go back to PC 1 and press ENTER here.
==============================================================
```

- `StepRun` zählt die Schritte (`STEP n of N`); `N` steht vor dem Start
  fest und wird aus der geplanten Schrittliste berechnet, nicht geschätzt.
- `WHERE` ist genau einer von zwei festen Texten: `PC 1  - this program
  / PK-232` oder `PC 2  - Direwolf / TinyBox / QtTermTCP`. Keine anderen
  Formulierungen.
- `DO` sind nummerierte, einzelne Handgriffe, je eine Zeile, jeweils mit
  dem Namen des Fensters bzw. Programms und dem **Rufzeichen**, das
  gemeint ist.
- `THEN` sagt immer, was an PC 1 zu tun ist (ENTER, `y`, einfügen).
- Jeder Schritt steht mit Nummer und Titel auch im Log, damit Log und
  Anweisung zusammenpassen.

Sprache: Englisch (Projektregel), aber kurze Sätze, keine
Fachabkürzungen ohne Erklärung (nicht „UA", sondern „the TNC will answer
the call").

**Commit:** `hw_check: operator_step - one place for operator instructions`

---

## Teil B — Übersicht und Vorbereitungs-Checkliste

Beim Start (nach `normalize()`, vor der ersten Aussendung):

1. Übersicht aller Schritte des gewählten Teils: Nummer, Titel, `PC 1`/
   `PC 2`, grobe Dauer. Gesamtdauer.
2. Checkliste, je Punkt einzeln mit ENTER bestätigen:
   - PC 2: Direwolf läuft und zeigt dekodierte Pakete.
   - PC 2: TinyBox `OE3GAS-1` läuft (nur Teil B, B.3).
   - PC 2: QtTermTCP hat zwei Sitzungen, Rufzeichen `OE3GAS-2` und
     `OE3GAS-3`, **beide getrennt** (nur Teil C).
   - Beide Stationen auf derselben APRS-freien Frequenz, Dummy-Load oder
     minimale Leistung.
   - PK232PY ist auf PC 1 geschlossen.

**Commit:** `hw_check: channel_probe overview and preparation checklist`

---

## Teil C — Teil B mit **einem** Paste am Ende

- Alle drei B-Aussendungen (B.1, B.2, B.3 samt `\r` an die TinyBox) laufen
  nacheinander **ohne** Paste dazwischen; nur die `confirm_tx()`-Fragen an
  PC 1 bleiben.
- Zum Schluss **ein** Schritt `WHERE: PC 2`:
  „In the Direwolf window, select everything from the line containing
  `P69 B1` down to the last line, copy it" → `THEN: PC 1, paste, then a
  line with a single "."`.
- Die Auswertung sucht die Zeilen je Schritt über die **eindeutigen
  Texte** (`P69 B1 ch3 …`, `P69 B2 ch9 …`, `P69 B3 ch3 …`) und den
  Connected-Frame über `OE3GAS>OE3GAS-1` bzw. die gelernte
  I-Frame-Kennung. `classify_decoder_line()` bleibt die einzige
  Vergleichsfunktion; neu ist nur die Zuordnung eines langen Pastes zu
  den Schritten (reine Funktion `split_paste_by_marker()`).
- Fehlt eine Zeile im Paste: `FAIL` mit „not found in the pasted decoder
  output" — **nicht** erneut fragen.

**Commit:** `hw_check: channel_probe part B - one decoder paste at the end`

---

## Teil D — Teil C ohne Zeitdruck

Je Anruf ein `operator_step`:

```
STEP 7 of 10   T147 C.1   first incoming call
WHERE: PC 2  - Direwolf / TinyBox / QtTermTCP
DO:
  1. In QtTermTCP, use the session with callsign OE3GAS-2.
  2. Connect to OE3GAS.
  3. Wait until QtTermTCP shows it is connected - or 30 seconds pass.
  4. Leave this connection OPEN.
THEN: go back to PC 1 and press ENTER here.
```

- Die Aufzeichnung beginnt **vor** der Anweisung und endet mit ENTER
  (höchstens 120 s, dann automatisch weiter mit Hinweis). Kein fester
  60-s-Countdown mehr.
- **Vorher messen, nicht annehmen:** Gehen während eines blockierenden
  `input()` empfangene Frames verloren, oder puffert der Reader-Thread sie?
  Ein Dry-Run-freier Unit-Test mit Fake-Session reicht nicht — im Code
  nachweisen, wo die Frames während des Wartens landen (Queue des
  Readers), und das im Commit-Text belegen. Gibt es keinen Puffer: die
  Wartezeit mit `_pump_capture()` in kurzen Scheiben und nicht-blockierender
  Tastaturabfrage (`msvcrt.kbhit()` unter Windows) umsetzen.
- Danach ein Schritt `WHERE: PC 2`: „What does QtTermTCP show for
  OE3GAS-2? (connected / busy / nothing) - type it on PC 1".
- Vor der zweiten Runde (`USERS 10`) ein Schritt `WHERE: PC 2`: „In
  QtTermTCP, disconnect BOTH sessions (OE3GAS-2 and OE3GAS-3)" — das
  Programm trennt seine Seite selbst, aber QtTermTCP soll ebenfalls frei
  sein.

**Commit:** `hw_check: channel_probe part C - operator-paced incoming calls`

---

## Teil E — `--part {B,C,all}`

- Standard `all` (heutiges Verhalten, jetzt ohne die Zwischenfrage „Run
  part C").
- `--part B`: nur Teil B. `--part C`: nur Teil C, fragt das Rufzeichen für
  die Kanal-0-Belegung.
- Vorbereitung und Rückstellung in allen Fällen gleich.

**Commit:** `hw_check: channel_probe --part B/C/all`

---

## Teil F — Abbruch ist sicher

Ctrl-C an **jeder** Stelle (auch während `input()`):
- Rückstellung (`UNPROTO`, `USERS`, VHF/HBAUD) läuft;
- verbundene Kanäle laut letzter `CO`-Abfrage werden getrennt (nach
  `confirm_tx`, wie bisher);
- Schlusszeile: `Stopped at STEP n of N (<title>). Next run: --part <X>`.

**Commit:** `hw_check: channel_probe clean stop with the step reached`

---

## Teil G — Tests (zuerst rot)

- `operator_step`: Ausgabe enthält `STEP n of N`, genau eine der zwei
  `WHERE`-Zeilen, nummerierte `DO`-Zeilen, `THEN`.
- `StepRun`: `N` für `--part B`, `--part C`, `all` stimmt mit der Anzahl
  tatsächlich ausgegebener Schritte überein (Dry-Run mitzählen).
- `split_paste_by_marker`: ein echter Paste mit Leerzeilen zwischen den
  Paketen ordnet B.1/B.2/B.3 richtig zu; fehlender Marker → `FAIL`-Grund.
- Dry-Run `--part B` enthält keinen Teil-C-Schritt und umgekehrt.
- `ensure_vhf_1200`: Prompt-Zweig mit gestubbtem `input` (`y` setzt und
  merkt zur Rückstellung, `n` bricht mit `INFO` ab) — das von CC
  angebotene Nachreichen.

**Commit:** `Tests: channel_probe guidance, part selection, paste split, ensure_vhf_1200 prompt`

---

## Teil H — Doku

- `tools/README.md`: Abschnitt „channel_probe - what you do where" mit
  der Schrittübersicht aus Teil B für beide Teile.
- `Backlog.md`: „`operator_step` auch in `link_carry`, `link_carry_host`,
  `aprs_*`, `maildrop_session` verwenden" (eigenes Paket).
- `Testplan.md`: T146/T147 mit `--part B` bzw. `--part C` beschreiben.

**Commits:**
```
Docs: channel_probe operator walkthrough
Backlog: operator_step for the other subcommands
Testplan: T146 T147 run as separate parts
Docs: add P69a spec file
```

---

## Definition of Done

- neue Tests zuerst rot, volle Suite grün
- `--dry-run channel_probe --part B` und `--part C` zeigen jeden Schritt
  mit `STEP n of N`, `WHERE`, `DO`, `THEN`
- Keine Betreieranweisung außerhalb von `operator_step()` in
  `channel_probe`
- **Push**, Meldung mit Hash; `.\Sources2Text.ps1`, „sources aktualisiert"