# Claude Code Prompt — P59: MailDrop-Archiv automatisch — Sync beim Verlassen, Restore nach dem Einschalten

> Ablage: `docs/P59_MailDrop_Archive_Auto_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher lesen: `CLAUDE.md` (Abschnitt MailDrop), `docs/P38_MailDrop_Archive_Spec.md`,
> `docs/P39_MailDrop_Session_Window_Spec.md`, `Backlog.md` (Eintrag
> „Sync/Restore auto-trigger, still a separate follow-up (P39)").
> Stand der Analyse: `main` @ `7757a10` (26.09.2026).

---

## Befund

### B.1 Die drei Einstellungen wirken nicht
`archive_sync`, `archive_restore`, `archive_restore_scope` werden gespeichert
(`config.py:270–272`) und im Parameterdialog angezeigt
(`params_maildrop.py`), aber **kein anderer Code liest sie**. Beleg:

```
grep -rn "archive_sync\|archive_restore" src/pk232py --include=*.py | grep -v tests/
→ nur config.py und ui/dialogs/params_maildrop.py
```

Der Dialog sagt das selbst: *„Automatic sync/restore (on_session_end / ask /
auto) is not wired up yet - see Backlog.md."*

### B.2 Der manuelle Restore ignoriert `archive_restore_scope`
`maildrop_dialog.py`, `_on_restore_clicked()`:

```python
queue = [r for r in self._rows if r.where == WHERE_ARCHIVE]
```

Es wird **alles** zurückgeschrieben, was nur im Archiv liegt — unabhängig
davon, ob `unread`, `all` oder `none` eingestellt ist. P38.1 definiert den
Scope aber allgemein („begrenzt, wie viel zurückgeschrieben wird"), nicht
nur für den Automatikfall.

### B.3 `tnc_defaults` ist klebrig — als Auslöser unbrauchbar
`SerialManager.tnc_defaults` wird aus `self._tnc_banner` abgeleitet. Dieser
wird genau an **einer** Stelle gesetzt (`serial_manager.py:1311`, in
`_finish_verbose_init()`, nur wenn Bannermarker im Empfang stehen) und
**nie zurückgesetzt** (`:541` ist nur die Initialisierung).

Folge: Nach einem Einschalten mit Werkseinstellung bleibt `tnc_defaults ==
True` für die ganze Laufzeit der Anwendung — auch bei jedem späteren
Reconnect oder jeder Recovery, bei der der TNC längst läuft und gar kein
Banner kommt. Ein Restore-Auslöser, der nur `tnc_defaults` prüft, würde bei
jedem Wiederverbinden erneut fragen bzw. zurückschreiben.

`tnc_release` und `has_pactor` sind aus demselben Grund klebrig. Für sie ist
das **gewollt** (die Firmware ändert sich nicht, nur weil kein Banner kam) —
sie bleiben in diesem Paket unverändert.

### B.4 Zwei Wege aus der Sitzung, beide rufen `leave()` direkt
- `maildrop_dialog.py:702` — `self.btn_end.clicked.connect(self.session.leave)`
- `maildrop_dialog.py:822` — `_request_close()` nach bestätigtem Schließen

Ein „vor dem Verlassen einsammeln" muss an **einer** Stelle hängen, sonst
wirkt es nur auf einem der beiden Wege.

### B.5 Die MailDrop-Sitzung ist nur unter Bedingungen möglich
`MainWindow._maildrop_gate()`: verbunden **und** Host Mode, Betriebsart HF
oder VHF Packet, **kein** verbundener Kanal, `has_maildrop` nicht `False`.
Direkt nach dem Init steht die Anwendung nicht zwingend in Packet. Ein
Restore nach dem Einschalten kann also nicht einfach „beim Init" laufen,
sondern erst, wenn das Tor offen ist.

### B.6 Was gemessen ist und was nicht
| Aussage | Beleg | Gerät |
|---|---|---|
| Banner enthält `is using default values` nach Einschalten | T131, Screenshot 25.09.2026 | B |
| Nachricht schreiben (Restore) ≈ 6–7 s, Sitzung öffnen ≈ 4 s, verlassen ≈ 3 s | P38, T119 | B |
| Dauer „Nachricht lesen" (Sync) | **ungemessen** | — |
| Banner-Formulierung auf Gerät A und C | **ungemessen** | — |

Die Umsetzung muss mit „kein Banner" und „Banner ohne die Phrase" sicher
umgehen: beides heißt **kein** automatischer Restore.

---

## Grundhaltung (aus P38, unverändert)

Nichts passiert automatisch, solange der Anwender es nicht ausdrücklich
eingeschaltet hat. Jede automatische Aktion ist **sichtbar** (Banner,
Statuszeile, `[SYS]`-Zeile im Monitor) und **abbrechbar**. Die Standardwerte
(`manual` / `never` / `unread`) bleiben.

---

## Teil A — SerialManager: „frisch eingeschaltet" nur für diesen Init

`src/pk232py/comm/serial_manager.py`

- Neues Attribut `self._banner_this_init: bool = False`.
- Zu Beginn von `_init_tnc_thread()` **und** `_recovery_thread()` auf
  `False` setzen — vor dem ersten Schreibzugriff, also in derselben Phase wie
  `_take_over_read_path()`.
- In `_finish_verbose_init()` im bestehenden `if any(m in resp …)`-Zweig
  zusätzlich auf `True` setzen. Keine zweite Bannererkennung bauen — die
  vorhandene Stelle ist die einzige.
- Neue Property:

```python
@property
def fresh_boot_defaults(self) -> bool:
    """True only if THIS init/recovery run captured a boot banner that
    said 'is using default values' (P59). Unlike tnc_defaults, which
    keeps the last banner ever seen, this is reset at the start of every
    init and recovery - the only safe trigger for 'the TNC was just
    powered on and its MailDrop is empty'."""
    return self._banner_this_init and self.tnc_defaults is True
```

`tnc_defaults`, `tnc_release`, `has_pactor` bleiben **unverändert**.

**Lernmodus-Hinweis für den Commit-Kommentar:** Der Unterschied zwischen
„Zustand" (welche Firmware steckt drin — bleibt gültig) und „Ereignis" (der
TNC ist gerade neu gestartet — gilt nur einmal) ist der Kern dieses Teils.
Ein Ereignis darf nicht aus einem Zustand abgeleitet werden, der nie
zurückgesetzt wird.

**Commit:** `SerialManager: fresh_boot_defaults flag per init run`

---

## Teil B — `archive.py`: Scope-Filter als reine Funktion

`src/pk232py/maildrop/archive.py` — neue Modulfunktion, kein Qt:

```python
RESTORE_SCOPES = ("all", "unread", "none")

def filter_restore_scope(
    messages: Sequence[ArchivedMessage], scope: str,
) -> list[ArchivedMessage]:
    """all -> unchanged, unread -> read_flag False, none -> [].
    Unknown scope -> ValueError (never silently 'all')."""
```

`unread` bezieht sich auf das Lesekennzeichen **zum Zeitpunkt der
Archivierung** (`read_flag` aus der TNC-Liste). Das in den Docstring
schreiben — `mark_read()` wird derzeit nirgends aufgerufen, das ist kein
Fehler dieses Pakets, aber es muss dastehen.

**Commit:** `MailDrop archive: restore scope filter`

---

## Teil C — `maildrop_dialog.py`

### C.1 Eine Warteschlange für Sync, eine für Restore — mit Fortsetzung
`_on_sync_clicked`/`_advance_sync` und `_on_restore_clicked`/
`_advance_restore` werden so umgebaut, dass die Warteschlangenlogik genau
einmal existiert und am Ende eine übergebene Fortsetzung aufruft:

```python
def _start_sync(self, numbers: list[int], then: Callable[[], None]) -> None
def _start_restore(self, rows: list[_Row], then: Callable[[], None]) -> None
```

- Manuelle Knöpfe: `then=self.session.list` (heutiges Verhalten).
- `_on_failed()` während einer Warteschlange: Warteschlange leeren, dann
  **trotzdem** die Fortsetzung aufrufen, wenn sie das Verlassen der Sitzung
  ist (C.2) — der Packet-Betrieb muss wieder anlaufen. Bei manuellen
  Aktionen bleibt es beim heutigen Verhalten (keine Fortsetzung).

### C.2 Ein Weg aus der Sitzung: `_end_session()`
Neue Methode, einziger Aufrufer von `self.session.leave()`:

- `btn_end.clicked` → `_end_session`
- `_request_close()` → nach Bestätigung `_end_session`

Ablauf:
1. Wenn Archiv an **und** `archive_sync == "on_session_end"` **und** es
   Zeilen mit `WHERE_TNC` gibt → `_start_sync(queue, then=self.session.leave)`.
   Statuszeile: `Collecting N message(s) into the archive before leaving...`
2. Sonst direkt `self.session.leave()`.

Die Rückfrage in `_request_close()` nennt den Sync, wenn er ansteht:
*„End the MailDrop session? N new message(s) will be collected into the
local archive first."*

Bricht der Sync ab (C.1), steht in der Statuszeile
`Sync incomplete: X of N archived - leaving the session anyway.`

### C.3 Scope gilt auch für den manuellen Restore
- `_on_restore_clicked()` filtert die `WHERE_ARCHIVE`-Zeilen über
  `filter_restore_scope()` (Zuordnung Zeile → `ArchivedMessage` über
  `archive_id`). Die Zuordnung „nur im Archiv" bleibt die bestehende über
  `_header_key` — keine zweite Vergleichslogik.
- Tooltip des Knopfs nennt den Scope: `Restore scope: unread (Parameters ->
  MailDrop...)`.
- Scope `none` → Knopf gesperrt, Tooltip `Restore scope is 'none'`.
- Nichts im Scope, aber Archiv-only-Zeilen vorhanden → gesperrt, Tooltip
  `Nothing archive-only within restore scope '<scope>'.`

### C.4 Automatischer Restore: Konstruktorargument `auto_restore`
`MailDropDialog(..., auto_restore: bool = False)`

Mit `auto_restore=True`:
1. Nach dem Aufbau **selbst** `session.open()` auslösen (die bestehende
   `_can_open()`-Prüfung greift unverändert).
2. Banner während der ganzen Sitzung:
   `Restoring the local archive after TNC power-on   ·   packet operation is
   suspended`.
3. Nach dem **ersten** `listing` im Zustand ACTIVE: Kandidaten = Zeilen
   `WHERE_ARCHIVE`, gefiltert nach Scope →
   `_start_restore(candidates, then=<Sitzung beenden und Dialog schließen>)`.
   Leere Kandidatenliste → sofort beenden.
4. Schließen/Esc während des Restores: Rückfrage *„Stop restoring and end
   the session?"* → Ja: Warteschlange leeren, die gerade laufende Nachricht
   läuft zu Ende (kein `abort()` mitten im Schreiben — `/EX`-Regel aus
   `CLAUDE.md`), dann `_end_session()`.
5. Sitzung CLOSED → Dialog schließt sich selbst (gleicher Mechanismus wie
   `_closing_confirmed`). `on_session_end`-Sync findet dabei **nicht** statt —
   die gerade zurückgeschriebenen Nachrichten sind ja schon im Archiv.

**Commits:**
```
MailDrop dialog: one queue per direction with continuation
MailDrop dialog: single end-session path with on_session_end sync
MailDrop dialog: restore scope for manual restore
MailDrop dialog: auto_restore mode
```
(Bei vier Commits auf dieselbe Datei: in dieser Reihenfolge, Tests nach
jedem Schritt grün.)

---

## Teil D — `main_window.py`: der Restore-Auslöser

### D.1 Vormerken
In den Slots für `host_mode_changed(True)` und `recovery_finished(True, …)`:

```
wenn serial.fresh_boot_defaults
 und maildrop.archive_enabled
 und maildrop.archive_restore in ("ask", "auto")
 und maildrop.archive_restore_scope != "none"
 und serial.has_maildrop is not False
→ self._archive_restore_pending = True
   [SYS] TNC came up at factory defaults - MailDrop archive restore pending
```

Nichts öffnen, keine Datei anlegen — nur vormerken.

### D.2 Auslösen, sobald das Tor offen ist
`_update_maildrop_gate_ui()` wird bereits bei jeder relevanten Änderung
aufgerufen (Verbindung, Host Mode, Moduswechsel, Kanalzustand). Dort:

```
wenn self._archive_restore_pending und _maildrop_gate() offen:
    self._archive_restore_pending = False        # einmalig
    QTimer.singleShot(0, self._offer_archive_restore)
```

`singleShot(0)`, weil aus dem Gate-Update heraus kein modaler Dialog
geöffnet werden darf.

Ist das Tor beim Vormerken zu, **einmal** ein Hinweis in Statusleiste und
Monitor: `[SYS] MailDrop archive restore pending - switch to HF/VHF Packet
(no connected channels) to start it.`

Trennung vom TNC → `_archive_restore_pending = False` (die nächste
Verbindung entscheidet neu über D.1).

### D.3 `_offer_archive_restore()`
1. `open_archive()`; `None` oder Kandidaten nach Scope = 0 →
   `[SYS] MailDrop archive restore: nothing to restore (scope '<scope>')`,
   Ende.
2. `ask` → `QMessageBox.question` mit Anzahl und Schätzung:
   *„The TNC came up at factory defaults, so its MailDrop is empty. Restore
   N message(s) from the local archive now? This takes about M seconds and
   suspends packet operation — other stations receive BUSY."*
   `M = N × 7 + 7` (Messwerte aus P38, Gerät B — im Code als benannte
   Konstante mit Verweis auf P38, nicht als nackte Zahl).
   Nein → `[SYS] MailDrop archive restore declined`, Ende.
3. `auto` oder Ja → `[SYS] MailDrop archive restore started (N message(s))`,
   dann `MailDropDialog(..., auto_restore=True).exec()`, danach wie in
   `_on_open_maildrop_dialog()` `last_have_mail` übernehmen.

Die Kandidatenzahl in Schritt 1 ist eine **Vorab-Schätzung** aus dem Archiv
allein (der TNC ist nach dem Einschalten leer). Maßgeblich ist die Liste, die
der Dialog nach dem Listing selbst bildet (C.4.3).

**Commit:** `MainWindow: archive restore after TNC power-on`

---

## Teil E — Parameterdialog-Text

`params_maildrop.py`: den `effect_note`-Text und den Kommentar zu P38.3
ersetzen. Neu:
*„'on_session_end' collects new messages when you end a MailDrop session.
'ask'/'auto' restore from the archive when the TNC comes up at factory
defaults (detected from its power-on banner) and a MailDrop session is
possible."*

**Commit:** `MailDrop params dialog: describe automatic sync and restore`

---

## Teil F — Tests (jeder Test einmal rot gesehen)

**`test_serial_manager.py`**
- `fresh_boot_defaults` True nach einem Init mit Banner inkl. Phrase
- nach einem zweiten Init **ohne** Banner: `fresh_boot_defaults` False,
  `tnc_defaults` weiterhin True (beweist B.3 und dass A den Zustand nicht
  angefasst hat)
- Banner ohne Phrase → False; kein Banner → False
- Recovery setzt das Flag ebenfalls zurück

**`test_maildrop_archive.py`**
- `filter_restore_scope` für `all`/`unread`/`none`; unbekannter Scope →
  `ValueError`

**`test_maildrop_dialog.py`** (FakeSession, echtes Archiv in `tmp_path`)
- `btn_end` bei `on_session_end` mit zwei TNC-only-Zeilen: Aufrufe
  `read, read, leave` in dieser Reihenfolge
- dasselbe über bestätigtes Schließen — **gleiche** Aufruffolge (beweist den
  einen Weg aus C.2)
- `manual`: `btn_end` → nur `leave`
- Sync-Fehler mitten in der Warteschlange: `leave` wird trotzdem aufgerufen,
  Statuszeile enthält `Sync incomplete`
- manueller Restore mit Scope `unread`: gelesene Archivnachricht wird **nicht**
  gesendet; Scope `none` → Knopf gesperrt
- `auto_restore=True`: `open` ohne Klick; nach Listing `send` je Kandidat,
  dann `leave`; kein `read` (kein Sync beim Auto-Restore)
- Schließen während Auto-Restore mit Bestätigung: keine weiteren `send`
  nach dem laufenden, dann `leave`

**`test_main_window_packet.py`**
- `fresh_boot_defaults` True, `ask`, Tor offen → genau **eine** Rückfrage;
  zweiter Gate-Update → keine zweite
- Tor zu (nicht in Packet) → keine Rückfrage, Hinweis einmal; Wechsel nach HF
  Packet → Rückfrage
- `never` / Scope `none` / `has_maildrop False` / Archiv aus → nichts
- Trennen löscht die Vormerkung

---

## Teil G — Hardware (Gerät B), neue Testfälle

### T136 — Sync beim Verlassen (`on_session_end`)
1. Archiv an, `archive_sync = on_session_end`.
2. Sitzung öffnen, zwei Nachrichten schreiben, `End session`.
3. **Erwartet:** Statuszeile „Collecting 2 message(s)…", danach normale
   Rückkehr in Host Mode; im nächsten Dialog beide als `TNC + archive`.
4. **Messen:** Dauer je `read` aus den Zeitstempeln im Log — schließt die
   Lücke aus B.6.

### T137 — Restore nach dem Einschalten (`ask`)
1. Archiv mit ≥ 2 Nachrichten (aus T136), `archive_restore = ask`,
   Scope `all`.
2. TNC aus- und einschalten, Anwendung verbinden, HF Packet wählen.
3. **Erwartet:** genau eine Rückfrage mit Anzahl und Zeitschätzung; nach Ja
   läuft der Dialog selbständig, schließt sich, Packet-Betrieb läuft; im
   nächsten manuellen Dialog stehen die Nachrichten als `TNC + archive`.
4. **Gegenprobe:** Anwendung trennen und neu verbinden, **ohne** den TNC
   auszuschalten → **keine** Rückfrage.
5. **Messen:** tatsächliche Dauer gegen die Schätzung.

Gerät A und C: ausdrücklich nicht Teil dieses Pakets; Befunde nicht
übertragen (`docs/DEVICES.md`).

---

## Teil H — Dokumentation

- `CLAUDE.md`, Abschnitt MailDrop: `fresh_boot_defaults` vs. `tnc_defaults`
  (Ereignis vs. Zustand); ein Weg aus der Sitzung; Scope gilt für beide
  Restore-Arten; Auto-Restore wartet auf das offene Tor.
- `Backlog.md`: Eintrag „Sync/Restore auto-trigger" als erledigt (P59), mit
  Verweis auf T136/T137. **Neu:** „`tnc_release`/`has_pactor` bleiben nach
  einem Gerätetausch ohne Banner auf dem alten Gerät stehen — das Archiv
  würde Nachrichten mit falschem `device` ablegen. Ungemessen, eigenes
  Paket."
- `Testplan.md`: T136, T137 (OPEN), Softwaretests aus Teil F referenzieren.

**Commits:**
```
Docs: CLAUDE.md MailDrop automatic archive
Backlog: P59 archive auto sync/restore
Testplan: T136 T137 archive sync and restore
Docs: add P59 spec file
```

---

## Definition of Done

- `.venv\Scripts\python.exe -m pytest` grün; jeder neue Test wurde vor der
  Umsetzung einmal rot gesehen (im Abschlussbericht je Test die Zeile des
  roten Laufs)
- `grep -rn "session.leave()" src/pk232py/ui/dialogs/maildrop_dialog.py`
  findet genau **eine** Stelle (in `_end_session`)
- Keine zweite Bannererkennung, keine zweite Sync-/Restore-Warteschlange
- Standardwerte unverändert (`manual`/`never`/`unread`); mit ihnen verhält
  sich die Anwendung exakt wie vor P59
- T136/T137 als OPEN im Testplan
- `.\Sources2Text.ps1`, danach Meldung „sources aktualisiert"