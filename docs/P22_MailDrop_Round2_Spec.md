# Claude Code Prompt — P22: MailDrop-Befunde festhalten, zweite Messrunde

> Ablage: `docs/P22_MailDrop_Round2_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher `CLAUDE.md`, `Backlog.md`, `Testplan.md` lesen.
> Fixture: Mitschnitt `hw_logs/<22.09.2026 18:43>_maildrop.log`.

---

## Befunde vom 22.09.2026, 18:43 (erster vollständiger Lauf)

### Befehle und Antworten (SysOp, lokal nach `MDCHECK`)

| Eingabe | Antwort |
|---|---|
| `L`, Mailbox leer | `*** Message not found.` + Prompt |
| `S <call>` | `Subject:` |
| Betreff | `Enter message, ^Z (CTRL-Z) or /EX to end` + Leerzeile |
| Textzeile | Echo, kein Prompt |
| `/EX` | `Message stored as # <n>` + Prompt |
| `R <n>` | Kopfzeile + Listenzeile, Leerzeile, Text, **`/E`**, Prompt |
| `K <n>` | `*** Done.` + Prompt |
| `B` | `cmd:` |

Kleinbuchstaben werden angenommen. `s oe3gas#` → Empfänger `OE3GAS`
(Sonderzeichen ignoriert).

### Listenformat (feste Spalten, neueste zuerst)

```
Msg#    Size To     From   @ BBS  Date       Time   Title
  2 PN    35 OE3GAS OE3GAS        .........  .....  Test 2
  1 PY    36 OE3GAS OE3GAS        .........  .....  test 1
```

- Statusfeld zweistellig: **Typ** (`P`, laut Handbuch auch `T`, `B`) +
  **Lesestatus** (`N` ungelesen, `Y` gelesen — nach `R 1` wurde `PN` zu `PY`)
- Datum/Zeit als Punkte: TNC-Uhr nach Einschalten nicht gestellt (keine
  Pufferbatterie), **nicht** Formatmerkmal
- `@ BBS` leer, wenn nicht angegeben

### Nummerierung
- fortlaufend, **keine Neuvergabe nach `K`** (Nachricht 2 bleibt 2)
- nach dem Ausschalten beginnt die Zählung neu → die TNC-Nummer ist nur
  innerhalb einer Einschaltperiode eindeutig

### Speicher
- 18536 → 18452 → 18368, nach `K 1` wieder 18452
- pro Nachricht **84 Bytes** bei Größe 36 bzw. 35 → fester Anteil rund
  48 Bytes
- `Size` = Länge Betreff + Länge Text + **9** (in beiden Fällen)

### Firmware-Eigenheit
Der gespeicherte Text endet mit einer Zeile **`/E`** — ein Rest des
Endezeichens `/EX`. Beim Übernehmen ins Archiv abschneiden.

---

## P22.1 — Dokumentation der Befunde

### `CLAUDE.md` — Abschnitt MailDrop ersetzen/erweitern
Alle Befunde oben, dazu die Designfolgen:
- **Archivschlüssel ≠ TNC-Nummer.** Das Archiv vergibt eine eigene,
  dauerhafte ID; die TNC-Nummer ist ein Attribut, gültig bis zum nächsten
  Ausschalten
- abschließende `/E`-Zeile beim Lesen entfernen
- Kapazitätsschätzung vor dem Zurückschreiben: Summe (Größe + 48) gegen
  den freien Speicher aus dem Prompt

### `Testplan.md`
- **T115**: PASS für L/S/R/K/B, Listenformat, Nummerierung, Speicher,
  22.09.2026. Ausschalttest offen (übersprungen)

**Commit:** `Docs: MailDrop protocol facts from first full hardware run`

---

## P22.2 — `tools/hw_check.py`: Ausschalttest bedienbar machen

Die Rückfrage kam, bevor klar war, dass jetzt auszuschalten ist; ein leeres
Enter galt als Nein. Neuer Ablauf:

```
Power-cycle test.
  1. Switch the TNC OFF now.
  2. Wait 5 seconds.
  3. Switch it back ON.
Type 'done' when the TNC is back on (or 'skip' to skip this test):
```

- nur `done` oder `skip` akzeptieren, alles andere → Frage wiederholen
- danach `normalize()` (setzt `MYCALL`), `MDCHECK`, `L`, `B`
- Ergebnis: `PASS`, wenn `L` → `*** Message not found.` **und** vorher
  mindestens eine Nachricht bestand; sonst `INCONCLUSIVE` mit Begründung

**Commit:** `Tools: clearer power-cycle step in the maildrop recorder`

---

## P22.3 — `tools/hw_check.py`: Uhr stellen vor der Mailbox

Im `maildrop`-Subcommand nach `normalize()` die TNC-Uhr stellen, genau wie
der Uploader es tut (`DAYTIME yymmddhhmm` bzw. das vorhandene Format aus
`ParamsUploader`, **nicht** neu gebaut), UTC vom PC. Damit zeigt die Liste
echte Datums- und Zeitwerte, deren Format dann belegt ist.

Nicht in `normalize()` selbst — die übrigen Tests brauchen die Uhr nicht.

**Commit:** `Tools: maildrop recorder sets DAYTIME before MDCHECK`

---

## P22.4 — Vorgeschlagene Folge für Runde 2

`_MAILDROP_SUGGESTED_SEQUENCE` ersetzen. Ziel sind die drei Fragen, an
denen die Wiederherstellungsfunktion hängt:

```
Round 2 - questions for the restore feature:

  S OE3GAS < DL1ABC      does the SysOp keep a foreign FROM callsign?
  (subject, text, /EX)
  S OE1XYZ @ DB0MUC      does @BBS appear in the list?
  (subject, text, ^Z)    ^Z instead of /EX - is there still a '/E' line?
  SB ALL                 can the SysOp create a bulletin directly?
  (subject, text, /EX)
  ST OE3GAS              traffic type?
  (subject, text, /EX)
  L                      FROM, @BBS, type letters, date/time format
  R <n>                  for the ^Z message - trailing '/E' or not?
  E <n>                  OPTIONAL, last: see what EDIT asks; keep every
                         field with Enter, or abort with Ctrl-X
  B                      the terminal ends at cmd:
  then the power-cycle test
```

`^Z` wird vom Terminal als Byte `$1A` gesendet (vorhandene Funktion). Im
Zustand `ENTRY` muss `$1A` den Zustand auf `MAILBOX` zurückführen, sobald
der Prompt kommt — prüfen, dass die Zustandsmaschine das schon kann.

`E` steht bewusst am Ende und ist optional: EDIT fragt Felder interaktiv
ab, deren Prompts unbekannt sind. Die Zustandsmaschine muss unbekannte
Antworten ohne Mailbox-Prompt und ohne `cmd:` tolerieren (P21.3: Zustand
unverändert, Warnung) — das genügt.

**Commit:** `Tools: maildrop recorder round-2 sequence`

---

## P22.5 — Tests

- Listenparser (nur als Werkzeughilfe, noch nicht für die Anwendung):
  die drei Listen aus dem Mitschnitt → Nummer, Typ, Lesestatus, Größe,
  An, Von, BBS, Titel; Punkte in Datum/Zeit → `None`
- Lesen: `/E` am Textende wird erkannt
- Ausschalttest-Eingabe: nur `done`/`skip`, alles andere wiederholt
- `$1A` im Zustand `ENTRY` → nach Prompt `MAILBOX`

**Commit:** `Tests: maildrop list parser, /E trailer, power-cycle prompt`

---

## Definition of Done

- `python -m pytest` grün
- `--dry-run maildrop` zeigt `normalize()`, das Stellen der Uhr und die
  Runde-2-Folge
- Kein Code unter `src/pk232py/` verändert
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"
- Danach vom Operator: `maildrop` mit der Runde-2-Folge und dem
  Ausschalttest, komplette Logdatei an den Chat