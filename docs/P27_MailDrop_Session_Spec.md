# Claude Code Prompt — P27: MailDrop-Protokollschicht und Sitzungsautomat

> Ablage: `docs/P27_MailDrop_Session_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher `CLAUDE.md`, `Backlog.md`, `Testplan.md`,
> `SERIAL_CONNECTION_STATE_MACHINE.md` und `OPMODE_SWITCH_STATE_MACHINE.md`
> lesen.
> Fixtures: die MailDrop-Mitschnitte in `hw_logs/` vom 22./23.09.2026.
> Dieses Paket baut **keine UI** — nur Protokoll, Zustandsautomat, Tests.

---

## Ausgangslage (alles hardwaregemessen)

MDCHECK hat **kein** Host-Mode-Kürzel (`mdcheck_scan`, 23 Kandidaten, kein
Treffer). Die Mailbox-Verwaltung läuft deshalb über den verbose-Weg und ist
**exklusiv**: laut Handbuch funktioniert MDCHECK nur, wenn keine Packet-
oder AMTOR-Station verbunden ist, und während der Sitzung erhalten fremde
Stationen ein BUSY-Frame.

Daraus folgt der Lebenszyklus:

```
Host Mode --> verbose --> MDCHECK --> [Sitzung] --> B --> Host Mode
```

Beide Übergänge existieren bereits als erprobte Abläufe in
`SerialManager` — **sie werden verwendet, nicht nachgebaut**.

### Gemessenes Protokoll

| Ereignis | Bytes vom TNC |
|---|---|
| Prompt | `(AEA PK-232M)  18536 free  (B,E,K,L,R,S) >` |
| ungelesene Post beim Login | zusätzlich `You have mail.` davor |
| leere Mailbox auf `L` | `*** Message not found.` |
| Listenkopf | `Msg#    Size To     From   @ BBS  Date       Time   Title` |
| Listenzeile | `  1 PN    36 OE3GAS OE3GAS        22-Sep-26  18:00  test 1` |
| Lesen `R 1` | Kopfzeile + Listenzeile + Leerzeile + Text + Leerzeile |
| Senden | `S <call> [@ BBS] [< FROM]` → `Subject:` → Betreff → `Enter message, ^Z (CTRL-Z) or /EX to end` → Zeilen → `/EX` → `Message stored as # n` |
| Löschen | `K <n>` → `*** Done.` |
| fehlendes Argument | `*** Not enough` (z. B. `R2` statt `R 2`) |
| Speicher voll | `*** No free memory` |
| unbekannter Befehl | `*** What?` |
| Verlassen | `B` → `cmd:` |

Weitere belegte Eigenheiten:
- Statusfeld zweistellig: Typ `P`/`T`/`B` + Lesestatus `N`/`Y`
- Datum `DD-Mon-YY  HH:MM`, beim **Speichern** gestempelt; ungestellte Uhr
  ergibt Punktreihen (`.........`)
- `Größe = Länge Betreff + Länge Text + 9` (an sieben Nachrichten bestätigt)
- Speicherverbrauch **nicht** berechenbar (84 bzw. 112 Bytes gemessen) —
  der freie Speicher wird aus **jedem** Prompt gelesen
- `Ctrl-Z` (`$1A`) beendet den Text **nicht**, nur `/EX`
- Nicht-ASCII geht verloren (`für` → `f?r`)
- der TNC ignoriert unbekannte Zusätze im `S`-Befehl **kommentarlos**
- einmalig beobachtet, seither nie: eine abschließende `/E`-Zeile im Text

---

## P27.1 — `src/pk232py/maildrop/protocol.py` (neu, reine Funktionen)

Kein I/O, keine Qt-Abhängigkeit, vollständig aus den Mitschnitten testbar.

```python
@dataclass(frozen=True)
class MailDropEntry:
    number: int
    mtype: str          # "P" | "T" | "B"
    read: bool          # aus N/Y
    size: int
    to: str
    frm: str
    bbs: str            # "" wenn leer
    stamp: str | None   # "22-Sep-26  18:00", None bei ungestellter Uhr
    title: str

@dataclass(frozen=True)
class PromptInfo:
    free: int
    commands: str       # "B,E,K,L,R,S"
    have_mail: bool
```

Funktionen:

- `find_prompt(text) -> PromptInfo | None` — erkennt den Prompt am Ende
  einer Antwort; toleriert vorangestellte Zeilen (`You have mail.`,
  eingeschobene SIAM-Ausgabe)
- `classify(text) -> str` — `"prompt" | "cmd" | "subject" | "body" |
  "error" | "unknown"`; `"cmd"` sobald `cmd:` am Ende steht
- `parse_list(text) -> list[MailDropEntry]` — Kopfzeile überspringen,
  Zeilen **an festen Spalten** lesen, mit Rückfall auf Trennung an
  Leerzeichen, wenn die Spaltenbreiten nicht passen; `*** Message not
  found.` → leere Liste
- `parse_read(text) -> tuple[MailDropEntry | None, str]` — Kopf und Text
  trennen; eine abschließende `/E`-Zeile entfernen, falls vorhanden
- `parse_error(text) -> str | None` — `*** What?`, `*** Not enough`,
  `*** No free memory`, `*** Done.` (letzteres als Erfolg kennzeichnen)
- `sanitize_body(text) -> tuple[str, list[str]]` — Umlaute umschreiben
  (ä→ae, ö→oe, ü→ue, ß→ss, Groß analog), übriges Nicht-ASCII durch `?`
  ersetzen; zurück kommt der bereinigte Text plus eine Liste der
  Änderungen für die Anzeige
- `check_body(text) -> list[str]` — Ablehngründe; **Pflichtregel**: eine
  Zeile, die nach `strip()` mit `/EX` beginnt, ist unzulässig
- `build_send_command(to, bbs, frm, mtype) -> str` — `S`/`ST`/`SB`,
  `@ BBS` nur bei gesetzter BBS, `< FROM` nur, wenn der Absender von
  MYCALL abweicht. Rufzeichen vorher prüfen (Buchstaben, Ziffern,
  optionale SSID) — der TNC meldet Unsinn **nicht**

**Commit:** `MailDrop: protocol parsing and command building`

---

## P27.2 — `src/pk232py/maildrop/session.py` (neu, Zustandsautomat)

`MailDropSession(QObject)`. **Serielle Arbeit in einem Worker-Thread**,
Ergebnisse ausschließlich über Signale an die GUI (Qt-Regeln in
`CLAUDE.md`).

### Zustände

`CLOSED → OPENING → ACTIVE → CLOSING → CLOSED`, dazu `FAILED`.
Ein Zustandswechsel wird **immer** über `state_changed(str)` gemeldet.

### Signale

```python
state_changed = pyqtSignal(str)
prompt_info   = pyqtSignal(object)   # PromptInfo nach jeder Antwort
listing       = pyqtSignal(list)     # list[MailDropEntry]
message_read  = pyqtSignal(object, str)
stored        = pyqtSignal(int)      # "Message stored as # n"
killed        = pyqtSignal(int)
failed        = pyqtSignal(str)      # Klartext für die Statuszeile
```

### Öffnen

1. Vorbedingung prüfen: ein injizierter Rückruf
   `can_open() -> tuple[bool, str]` liefert Freigabe und Begründung. Der
   Aufrufer (später die UI) beantwortet damit „kein Kanal verbunden".
   Die Sitzung entscheidet das **nicht** selbst, sie kennt das Kanalmodell
   nicht.
2. Host Mode über den vorhandenen `SerialManager`-Weg verlassen
3. auf `cmd:` warten (Zeitgrenze 5 s)
4. `MDCHECK\r` senden, bis Ruhe lesen (1,5 s Pause, wie im Werkzeug),
   `find_prompt()` erwarten
5. Erfolg → `ACTIVE`, `prompt_info` senden. Kein Prompt → `FAILED` und
   **Rückweg fahren** (siehe unten)

### Befehle im Zustand `ACTIVE`

`list()`, `read(n)`, `kill(n)`, `send(to, bbs, frm, mtype, subject, body)`,
`leave()`. Jeder Befehl:

- Argumenttrennung beachten: `R 2`, **nicht** `R2` (`*** Not enough`)
- Antwort bis Ruhe lesen, `classify()`, dann die passende Auswertung
- `prompt_info` bei jedem erkannten Prompt senden — daraus kommt der freie
  Speicher
- Fehlermeldung des TNC → `failed(text)`, Zustand bleibt `ACTIVE`

`send()` läuft als Unterablauf: Befehlszeile → `Subject:` abwarten →
Betreff → Aufforderung abwarten → Textzeilen → `/EX` → `Message stored as
# n`. Bricht ein Schritt ab, wird `/EX` gesendet, um den Texteingabemodus
sicher zu verlassen, danach `failed()`.

### Verlassen und Rückweg

`leave()`: `B\r` → `cmd:` erwarten → Host Mode über den vorhandenen Weg
betreten → `CLOSED`.

**Rückweg bei jedem Fehler** (eigene Methode, auch aus `FAILED` heraus
aufrufbar), in dieser Reihenfolge, jeder Schritt protokolliert:

1. `/EX\r` (falls der Texteingabemodus offen sein könnte)
2. `B\r`
3. `Ctrl-C` + `\r`
4. auf `cmd:` prüfen
5. Host Mode betreten

Gelingt Schritt 4 nicht, bleibt der Zustand `FAILED`, und `failed()` nennt
dem Bediener den Handgriff (TNC aus/ein). **Niemals stillschweigend einen
Erfolg melden** — das ist die Lehre aus P15.

### Zeitgrenzen

Ruhe-Erkennung 1,5 s, Gesamtgrenze je Befehl 15 s (Listen können lang
sein), `MDCHECK` 8 s. Werte als Modulkonstanten mit Begründung.

**Commit:** `MailDrop: verbose session state machine`

---

## P27.3 — Altbestand ersetzen

`src/pk232py/maildrop/maildrop.py` (geratene Mnemonics, `upload_config()`)
ist toter Code und wird durch P27.1/P27.2 abgelöst:

- Datei löschen, `__init__.py` auf die neuen Module umstellen
- `message_store.py` **prüfen**: passt das vorhandene Schema für das
  Archiv (eigene dauerhafte ID, TNC-Nummer als Attribut, Absender, BBS,
  Typ, Lesestatus, Zeitstempel des TNC, Rohtext)? Ergebnis im Commit-Text.
  Passt es: behalten und im Docstring auf P27 verweisen. Passt es nicht:
  **nicht umbauen**, sondern Befund notieren — das Archiv ist ein eigenes
  Paket
- `Backlog.md` entsprechend aktualisieren

**Commit:** `MailDrop: drop the unverified legacy module`

---

## P27.4 — Tests

Fixtures sind die **echten Mitschnitte**; die Antworten daraus wörtlich in
die Testdatei übernehmen.

- `find_prompt`: mit und ohne `You have mail.`, mit eingeschobener
  SIAM-Zeile
- `parse_list`: die Listen aus Runde 1, 2 und 3 — Typen `P`/`T`/`B`,
  Lesestatus, `@ BBS` gesetzt und leer, Punktreihen → `stamp is None`,
  fremder Absender `DL1ABC`
- `parse_read`: mit und ohne `/E`-Zeile
- `parse_error`: `*** What?`, `*** Not enough`, `*** Message not found.`,
  `*** Done.`
- `check_body`: Zeile `/EX`, Zeile `  /ex  `, harmloser Text mit `/E`
- `sanitize_body`: `für` → `fuer` samt Änderungsliste
- `build_send_command`: alle vier Formen, inklusive `SB ALL`
- Zustandsautomat gegen einen **gefälschten seriellen Kanal**, der die
  Mitschnitte abspielt: Öffnen, Liste, Lesen, Senden, Löschen, Verlassen;
  dazu ein Abbruchfall, in dem der Prompt ausbleibt — geprüft wird, dass
  der Rückweg gefahren und **kein** Erfolg gemeldet wird

**Commit:** `Tests: MailDrop protocol and session from hardware transcripts`

---

## P27.5 — Dokumentation

- `CLAUDE.md`: Abschnitt „MailDrop session" — Lebenszyklus, Exklusivität,
  BUSY für fremde Stationen, Rückweg, und dass MDCHECK kein Host-Kürzel hat
- `Testplan.md`: neue Fälle für die Sitzung am Gerät (ohne UI über ein
  kleines Skript oder den Python-Prompt): öffnen, auflisten, senden,
  lesen, löschen, verlassen; dazu ein Fall „Eintritt bei verbundenem
  Kanal wird verweigert"
- `Backlog.md`: UI (Sitzungsmaske) und Archiv als Folgepakete

**Commit:** `Docs: MailDrop session lifecycle`

---

## Definition of Done

- `.venv\Scripts\python.exe -m pytest` grün
- Kein Aufruf, der Host-Mode-Eintritt oder -Austritt selbst nachbaut
- Kein geratener Befehl: jede gesendete Zeichenfolge steht entweder in den
  Mitschnitten oder im Handbuch, mit Quelle im Kommentar
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"