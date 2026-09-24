# Claude Code Prompt — P38: MailDrop-Archiv (optional, ausdrücklich zu wählen)

> Ablage: `docs/P38_MailDrop_Archive_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher `CLAUDE.md` (Abschnitt MailDrop), `Backlog.md`, `Testplan.md`
> lesen. Fixture für die Feldbelegung:
> `hw_logs/20260924_181446_maildrop_session.log`.
> Dieses Paket baut **keine Sitzungsmaske** — nur Speicher, Einstellungen
> und deren Anbindung.

---

## Warum optional

Der PK-232 verliert seine Mailbox bei jedem Ausschalten (keine
Pufferbatterie). Ein lokales Archiv ist deshalb sinnvoll — aber **nicht
für jeden Betrieb**: Wer die MailDrop nicht nutzt, braucht es nicht, und
es kostet Zeit.

Gemessen am 24.09.2026 (Gerät B, T119):

| Vorgang | Dauer |
|---|---|
| Sitzung öffnen (Host Mode verlassen, `MDCHECK`) | ~4 s |
| eine Nachricht schreiben | **6–7 s** |
| Sitzung verlassen, Host Mode zurück | ~3 s |

20 Nachrichten zurückzuschreiben dauert damit gut **zwei Minuten**, und
während der gesamten Sitzung ist der Packet-Betrieb ausgesetzt: fremde
Stationen erhalten BUSY.

**Auch das Einsammeln kostet eine Sitzung** — die Mailbox ist nur über
`MDCHECK` lesbar. Das Archiv füllt sich also nie nebenbei.

Daraus folgt die Grundhaltung dieses Pakets: **nichts passiert
automatisch, solange der Anwender es nicht ausdrücklich eingeschaltet
hat**, und jede Einstellung nennt ihren Preis.

---

## P38.1 — Einstellungen im MailDrop-Parameterdialog

Neuer, klar abgesetzter Abschnitt **„Local archive (PC side)"**, mit einem
einleitenden Satz, dass diese Einstellungen **nicht** an den TNC gehen.

| Feld | Typ | Standard | Bedeutung |
|---|---|---|---|
| `archive_enabled` | bool | **aus** | Archiv überhaupt benutzen |
| `archive_path` | str | `~/.pk232py/maildrop_archive.db` | Ablageort, mit Auswahlknopf |
| `archive_sync` | Auswahl | `manual` | `manual` (nur auf Knopfdruck) / `on_session_end` (beim Verlassen der Sitzung automatisch einsammeln) |
| `archive_restore` | Auswahl | `never` | `never` / `ask` (fragen, wenn der TNC im Werkszustand hochkommt) / `auto` |
| `archive_restore_scope` | Auswahl | `unread` | `all` / `unread` / `none` — begrenzt, wie viel zurückgeschrieben wird |

Im Dialog sichtbar, nicht nur als Tooltip:

```
Restoring messages takes about 7 seconds each and suspends packet
operation for the whole session - other stations receive BUSY.
```

Bei `auto` zusätzlich ein Hinweis, dass der Start der Anwendung dadurch
länger dauert.

Die Felder sind **PC-seitig** und gehören in `UPLOAD_EXEMPT` (Test D aus
P13), mit der Begründung „local archive setting, not a TNC parameter".
Die Verdrahtungsprüfung aus P12 (Tests A/B/C) muss für sie greifen wie für
jedes andere Feld.

**Commits:**
```
Config: local MailDrop archive settings
MailDrop params dialog: local archive section
```

---

## P38.2 — `src/pk232py/maildrop/archive.py` (neu)

`message_store.py` passt nicht (P27.3: keine TNC-Nummer, keine BBS, kein
Typ, lokaler statt TNC-Zeitstempel) und wird **ersetzt**; die alte Datei
löschen, wenn nichts sie mehr importiert.

### Schema (SQLite)

Ein eigener, dauerhafter Schlüssel — **nicht** die TNC-Nummer, die nach
jedem Einschalten wieder bei 1 beginnt.

```
id            INTEGER PRIMARY KEY          -- lokal, dauerhaft
fingerprint   TEXT UNIQUE                  -- Duplikaterkennung, siehe unten
mtype         TEXT      -- P | T | B
read_flag     INTEGER   -- aus N/Y
to_call       TEXT
from_call     TEXT
bbs           TEXT      -- '' wenn leer
tnc_stamp     TEXT      -- '22-Sep-26  18:00', NULL bei ungestellter Uhr
size          INTEGER   -- Angabe des TNC
subject       TEXT
body          TEXT      -- ohne die abschliessende /E-Zeile
archived_at   TEXT      -- UTC, wann PK232PY sie gesichert hat
tnc_number    INTEGER   -- Nummer in der letzten Sitzung, nur als Hinweis
device        TEXT      -- Release aus dem Banner, falls bekannt
```

**Duplikaterkennung:** `fingerprint` = Hash über
`mtype | to_call | from_call | bbs | subject | body`. Der TNC-Zeitstempel
geht **nicht** ein — er wird beim Speichern gesetzt und wäre nach einem
Zurückschreiben ein anderer. Damit wird dieselbe Nachricht nach
Wiederherstellung und erneutem Einsammeln nicht doppelt abgelegt.

### Schnittstelle

```python
class MailDropArchive:
    def __init__(self, path: Path) -> None
    def add(self, entry, body, device=None) -> tuple[int, bool]   # (id, neu?)
    def all(self) -> list[ArchivedMessage]
    def missing_in_tnc(self, entries) -> list[ArchivedMessage]
    def mark_read(self, archive_id: int) -> None
    def delete(self, archive_id: int) -> None
    def count(self) -> int
```

- kein Qt, keine serielle Schicht — reine Ablage, vollständig testbar
- `missing_in_tnc()` vergleicht über den Fingerabdruck, nicht über Nummern
- Schema-Version in einer `meta`-Tabelle, damit spätere Änderungen
  migrierbar sind

**Commits:**
```
MailDrop: local archive store
MailDrop: drop the unused message_store module
Tests: archive store and duplicate detection
```

---

## P38.3 — Was dieses Paket NICHT tut

Ausdrücklich **nicht** enthalten, damit der Zuschnitt klar bleibt:

- kein automatisches Einsammeln oder Zurückschreiben (kommt mit der
  Sitzungsmaske)
- keine Anbindung an `MailDropSession`
- keine UI außer dem Einstellungsabschnitt

Im Backlog festhalten, dass `archive_sync` und `archive_restore` erst mit
der Sitzungsmaske wirksam werden; bis dahin sind es gespeicherte
Vorgaben. Der Dialog soll das **nicht** verschweigen: Hinweiszeile
„takes effect once the MailDrop session window is available".

---

## P38.4 — Dokumentation

- `CLAUDE.md`, Abschnitt MailDrop: das Archiv ist optional und
  standardmäßig **aus**; Begründung mit den gemessenen Zeiten; der
  Fingerabdruck als Schlüssel, nie die TNC-Nummer
- `Testplan.md`: Fälle für die Verdrahtung der neuen Felder (greift
  automatisch über P12) und ein Fall „Archiv aus → keine Datei wird
  angelegt"
- `Backlog.md`: Sitzungsmaske als Folgepaket, dazu die Idee, ob sich über
  `MDMON` mitgelesene Fremdzugriffe **ohne** Sitzung archivieren lassen —
  ungemessen, eigener Prüfpunkt

**Commit:** `Docs: optional MailDrop archive`

---

## Definition of Done

- `.venv\Scripts\python.exe -m pytest` grün
- Bei `archive_enabled = False` wird **keine** Datenbankdatei angelegt —
  eigener Test
- Zweimaliges `add()` derselben Nachricht ergibt einen Eintrag
- Die neuen Felder bestehen die Verdrahtungsprüfung aus P12 und stehen in
  `UPLOAD_EXEMPT`
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"