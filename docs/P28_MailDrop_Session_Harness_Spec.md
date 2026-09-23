# Claude Code Prompt — P28: Prüfstand für die MailDrop-Sitzung (T119)

> Ablage: `docs/P28_MailDrop_Session_Harness_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher `CLAUDE.md`, `Testplan.md` (T119) und
> `docs/P27_MailDrop_Session_Spec.md` lesen.

---

## Warum

`MailDropSession` ist fertig und getestet, aber nur gegen abgespielte
Mitschnitte. Für T119 braucht es einen Weg, die Klasse **am echten TNC**
zu fahren — ohne UI, ohne die Anwendung zu starten, und ohne die
Sitzungslogik im Prüfstand nachzubauen.

**Der Prüfstand darf keine eigene Protokolllogik enthalten.** Er baut die
Kette auf, ruft `open()`, `list()`, `send()`, `read()`, `kill()`,
`leave()` auf und protokolliert die Signale. Alles, was er selbst
parst oder sendet, wäre eine zweite Wahrheit neben `protocol.py`.

---

## P28.1 — `tools/hw_check.py`: Subcommand `maildrop_session`

### Aufbau

Weil `MailDropSession` Qt-Signale verwendet, braucht der Prüfstand eine
Qt-Ereignisschleife: `QCoreApplication` (nicht `QApplication` — keine GUI),
die Schritte über `QTimer.singleShot` verkettet oder über eine kleine
Ablaufklasse, die auf `state_changed` reagiert. Keine `time.sleep`-Ketten
im Hauptthread.

### Ablauf

1. `SerialManager` aufbauen wie die Anwendung: Port öffnen, Wakeup,
   Parameter-Upload **überspringen** (`--skip-upload`, Standard: an —
   die Parameter sind bereits geprüft, und der Upload kostet eine Minute),
   Host Mode betreten über den vorhandenen Weg
2. `MailDropSession` erzeugen, `can_open` mit einem Rückruf versorgen, der
   für diesen Lauf `(True, "")` liefert — mit Kommentar, dass im
   Produktivbetrieb das Kanalmodell antwortet
3. **jedes** Signal protokollieren: `state_changed`, `prompt_info`
   (freier Speicher), `listing`, `message_read`, `stored`, `killed`,
   `failed`
4. Schrittfolge, jeder Schritt mit Ergebniszeile für die Zusammenfassung:

   | Schritt | Erwartung |
   |---|---|
   | `open()` | Zustand `ACTIVE`, Prompt mit freiem Speicher |
   | `list()` | Liste (leer nach dem Einschalten ist in Ordnung) |
   | `send()` Personal an MYCALL, Betreff `T119 personal` | `stored` mit Nummer |
   | `send()` mit fremdem Absender (`< DL1ABC`) | `stored`, Absender in der nächsten Liste |
   | `send()` Bulletin an `ALL` | `stored`, Typ `B` |
   | `list()` | drei Einträge, Typen und Absender wie gesendet |
   | `read(n)` der ersten Nachricht | Text stimmt, Lesestatus wechselt in der Folgeliste auf `Y` |
   | `kill(n)` | `killed`, freier Speicher steigt |
   | `list()` | Nummer der gelöschten fehlt, übrige Nummern unverändert |
   | `leave()` | Zustand `CLOSED`, danach Host Mode aktiv |

5. Nach `leave()` prüfen, dass der Host Mode wirklich wieder läuft: ein
   `HPOLL`-Frame senden und auf die Antwort warten (vorhandene Funktion
   verwenden), Ergebnis protokollieren
6. `finally`: falls der Zustand nicht `CLOSED` ist, den Rückweg der
   Sitzung anstoßen und das Ergebnis melden

### Zusätzlicher Fehlerfall (optional, `--abort-test`)

Nach dem Betreff eines `send()` den Ablauf abbrechen (Methode der Sitzung
für „Abbruch" verwenden, falls vorhanden; sonst `leave()` mitten im
Texteingabemodus). Erwartung: der Rückweg läuft, es wird **kein** Erfolg
gemeldet, und der TNC steht danach wieder am `cmd:`-Prompt bzw. im Host
Mode. Das ist die Hardwareprobe für den Fehlerpfad, der bisher nur
gefälscht getestet ist.

### Protokoll

Wie bei den übrigen Subcommands: `hw_logs/<zeit>_maildrop_session.log`,
alle Signale mit Zeitstempel, am Ende die Zusammenfassung zum Übertragen
in den Testplan.

**Commit:** `Tools: hw_check maildrop_session harness for T119`

---

## P28.2 — Tests

Ohne Hardware, nur die Ablauflogik:

- die Schrittfolge ruft die Sitzungsmethoden in der festgelegten
  Reihenfolge auf (gegen eine Attrappe der Sitzung)
- ein `failed`-Signal beendet den Ablauf und markiert den Schritt
- der `finally`-Zweig stößt den Rückweg an, wenn der Zustand nicht
  `CLOSED` ist

**Commit:** `Tests: maildrop_session harness sequencing`

---

## P28.3 — Dokumentation

- `docs/HW_Solo_Tests.md`: `maildrop_session` ergänzen — Vorbereitung
  (Anwendung geschlossen, TNC eingeschaltet), Aufruf, was zu erwarten ist,
  Abhakzeile
- `Testplan.md`: T119 auf den Prüfstand verweisen, Schrittfolge als
  Erwartungsliste übernehmen

**Commit:** `Docs: T119 via the maildrop_session harness`

---

## Definition of Done

- `.venv\Scripts\python.exe -m pytest` grün
- `--dry-run maildrop_session` zeigt die geplante Schrittfolge, ohne den
  Port zu öffnen
- Der Prüfstand enthält **kein** eigenes Parsen von TNC-Antworten und
  **keinen** selbst gebauten Mailbox-Befehl
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"
- Danach vom Operator: `maildrop_session`, Logdatei an den Chat