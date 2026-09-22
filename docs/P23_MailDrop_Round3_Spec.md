# Claude Code Prompt — P23: MailDrop Runde 2 festhalten, Werkzeug nachbessern, Runde 3

> Ablage: `docs/P23_MailDrop_Round3_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher `CLAUDE.md`, `Backlog.md`, `Testplan.md` lesen.
> Fixture: `hw_logs/20260922_191657_maildrop.log`.

---

## Befunde Runde 2 (22.09.2026, 19:16)

### Beantwortet
- **`@BBS`**: `S OE1XYZ @ DB0MUC` → Spalte `@ BBS` = `DB0MUC`
- **Bulletin als SysOp**: `SB ALL` → Status `BN`, An `ALL`
- **Traffic als SysOp**: `ST OE3GAS` → Status `TN`
- **Datumsformat**: `22-Sep-26  17:20` (`DD-Mon-YY  HH:MM`, UTC wie mit
  `DAYTIME` gestellt). Das Datum wird **beim Speichern** eingetragen:
  Nachricht 2 aus Runde 1 (vor dem Stellen der Uhr angelegt) zeigt weiter
  Punkte
- **`MDCHECK` mit ungelesener Post**: zusätzliche Zeile `You have mail.`
  vor dem Prompt
- **Größe = Länge Betreff + Länge Text + 9** — bestätigt an allen sechs
  bisher gemessenen Nachrichten
- **Verlust beim Ausschalten: PASS** — sechs Nachrichten gespeichert, nach
  Aus/Ein `*** Message not found.`, frei 18536, `MYCALL PK232`

### Nicht beantwortet
- **Fremder Absender**: getippt wurde `s oe3gas > dl1abc` (`>` statt `<`).
  Der TNC ignorierte den Rest **ohne Fehlermeldung**, Absender `OE3GAS`.
  Ebenso in Runde 1: `s oe3gas#` → An `OE3GAS`. **Der TNC meldet unbekannte
  Zusätze im S-Befehl nicht** — Eingaben müssen vor dem Senden geprüft
  werden.
- **`Ctrl-Z` als Ende**: unter Windows erzeugt `Ctrl-Z` + Enter in der
  Konsole ein `EOFError`. Das Werkzeug schloss mit `/EX` ab (Nachricht 7)
  und verließ die Mailbox; `$1A` wurde nie gesendet.

### Richtigstellung: Speicherverbrauch
Die Formel „Größe + ~48 Bytes" aus P22 stammt aus zwei Messpunkten und
ist **falsch**:

| Nr. | Größe | belegt | @BBS |
|---|---|---|---|
| 1 (R1) | 36 | 84 | – |
| 2 (R1) | 35 | 84 | – |
| 3 | 37 | 84 | – |
| 4 | 41 | 112 | DB0MUC |
| 5 | 52 | 84 | – |
| 6 | 33 | 84 | – |
| 7 | 30 | 112 | DB0MUC |

Vermutung, **nicht belegt**: Zuteilung in Blöcken zu 28 Bytes, eine
BBS-Angabe kostet einen Block mehr. Designfolge unabhängig davon: **keine
Vorab-Rechnung**, sondern beim Zurückschreiben nach jeder Nachricht den
freien Speicher aus dem Prompt lesen und vor `*** No free memory`
aufhören.

---

## P23.1 — Dokumentation

### `CLAUDE.md`
- MailDrop-Abschnitt um alle Befunde oben ergänzen
- **Die Formel „size + ~48 bytes" entfernen** und durch die Tabelle plus
  die Designfolge ersetzen; Vermerk, dass sie aus zu wenigen Messpunkten
  abgeleitet war
- neue Regel: der TNC akzeptiert unbekannte Zusätze im S-Befehl
  kommentarlos — der Dialog validiert Empfänger, BBS und Absender selbst

### `Testplan.md`
- MailDrop-Fall: Ergebnisse Runde 2 eintragen, Ausschalttest PASS
- offen: fremder Absender (`<`), `Ctrl-Z`-Ende und `/E`-Zeile

**Commit:** `Docs: MailDrop round 2 results, memory formula withdrawn`

---

## P23.2 — `tools/hw_check.py`: Texteingabe an der Antwort erkennen

Der Zustand `ENTRY` wird derzeit aus der **Eingabe** abgeleitet (`S …`).
`SB`, `ST`, `SP` und alle anderen Varianten blieben deshalb im Zustand
`MAILBOX` („unrecognised response"). Beim Aufräumen hätte das `B` statt
`/EX` gesendet — `B` wäre Textzeile geworden.

Neu: der Zustand wird **aus der Antwort** bestimmt:

| Antwort endet mit | Zustand |
|---|---|
| `Subject:` | `ENTRY` (Betreff erwartet) |
| `Enter message, ^Z (CTRL-Z) or /EX to end` | `ENTRY` (Text erwartet) |
| Mailbox-Prompt | `MAILBOX` |
| `cmd:` | `CMD` → Ende |
| Echo einer Textzeile ohne Prompt, vorher `ENTRY` | `ENTRY` bleibt |

Die Erkennung an der Eingabe entfällt. Unit-Tests mit den `SB`- und
`ST`-Sequenzen aus dem Mitschnitt.

**Commit:** `Tools: mailbox entry state from TNC response, not typed command`

---

## P23.3 — `tools/hw_check.py`: `Ctrl-Z` unter Windows

- Die Eingabe der **zwei Zeichen** `^` und `Z` sendet bereits `$1A`
  (vorhandene Funktion). Im Hinweistext vor dem Prompt ausdrücklich sagen:
  „type the two characters ^ and Z — do NOT press Ctrl-Z, on Windows that
  ends the input"
- Zusätzlich: ein `EOFError` **im Zustand `ENTRY`** wird als Absicht „Text
  beenden" gewertet → `$1A` senden, im Protokoll vermerken
  („console Ctrl-Z interpreted as message end"), danach weiter lesen. Prüfen,
  ob `input()` nach einem Konsolen-`EOFError` unter Windows weiter
  funktioniert; falls nicht: nach `$1A` die Mailbox wie bisher sauber
  verlassen
- Ein `EOFError` außerhalb von `ENTRY` bleibt „Eingabe geschlossen"

**Commit:** `Tools: explicit ^Z input, console Ctrl-Z in entry sends 0x1A`

---

## P23.4 — Runde 3: nur die zwei offenen Fragen

`_MAILDROP_SUGGESTED_SEQUENCE` ersetzen:

```
Round 3 - two open questions:

  S OE3GAS < DL1ABC     foreign FROM - note: '<' (less-than), not '>'
  (subject, text, /EX)
  S OE3GAS              end the text with ^Z - type the TWO characters
  (subject, text)        ^ and Z, do not press Ctrl-Z
  ^Z
  L                     is FROM = DL1ABC for the first one?
  R <n>                 read the ^Z message - trailing '/E' line or not?
  R <n>                 read the /EX message - trailing '/E' (as in round 1)?
  B
```

Das Werkzeug soll nach `R` automatisch vermerken, ob die Antwort mit
einer `/E`-Zeile endet (vorhandene Funktion
`maildrop_response_has_e_trailer()`), und das in die Zusammenfassung
schreiben — getrennt für `^Z`- und `/EX`-Nachrichten.

Den Ausschalttest in Runde 3 **weglassen** (in Runde 2 bestätigt):
`--skip-power-cycle` als Option oder die Frage standardmäßig überspringen,
wenn in derselben Sitzung schon ein PASS vorliegt — CC entscheidet und
begründet.

**Commit:** `Tools: maildrop recorder round-3 sequence`

---

## P23.5 — Tests

- `SB`/`ST` aus dem Mitschnitt → Zustand `ENTRY` nach `Subject:`
- `You have mail.` vor dem Prompt → Zustand `MAILBOX`, freier Speicher
  korrekt gelesen
- `EOFError` in `ENTRY` → `$1A` gesendet; außerhalb → Eingabe beendet
- Listenparser mit der Runde-2-Liste: Typen `T`/`B`/`P`, `@ BBS`,
  Datum/Zeit `22-Sep-26`/`17:20`, Punkte → `None`

**Commit:** `Tests: maildrop round-2 fixtures`

---

## Definition of Done

- `python -m pytest` grün
- `--dry-run maildrop` zeigt die Runde-3-Folge und den `^Z`-Hinweis
- Kein Code unter `src/pk232py/` verändert
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"
- Danach vom Operator: `maildrop` mit der Runde-3-Folge, Logdatei an den
  Chat