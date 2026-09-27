# Claude Code Prompt — P60: P59-Nachbesserung — Restore-Auslöser verbrauchen, Fehlerpfad des Auto-Restore

> Ablage: `docs/P60_Archive_Restore_Oneshot_Fix_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Grundlage: Review von P59, `main` @ `6222441`.
> **Bis P60 umgesetzt ist, T137 NICHT mit `archive_restore = auto` fahren**
> (siehe B.1 — Endlosschleife von MailDrop-Sitzungen).

---

## Befund

### B.1 Der Auslöser feuert bei jedem Wiedereintritt in den Host Mode erneut (schwer)

`fresh_boot_defaults` wird nur zu Beginn von `_init_tnc_thread()`
zurückgesetzt (`serial_manager.py`, P59.A). Ausgewertet wird es aber in
`_update_host_mode_ui(True)` (`main_window.py:5070`) — und
`host_mode_changed(True)` kommt nicht nur nach einem Init, sondern auch aus
`SerialManager._enter_host_mode_thread()` (`serial_manager.py:1519`), das
`_init_tnc_thread()` **nicht** aufruft.

Genau diesen Weg nimmt jede MailDrop-Sitzung beim Verlassen
(`maildrop/session.py:85–86` → `SerialManager.enter_host_mode()`), ebenso
„Enter Host Mode" aus dem TNC-Menü (P49).

Damit bleibt das „Ereignis" für den ganzen Einschaltzyklus wahr. Ablauf mit
`archive_restore = auto`, Scope `all`, zwei Nachrichten im Archiv:

1. Einschalten → Init mit Banner → `fresh_boot_defaults = True` → vorgemerkt
2. Tor offen → `_offer_archive_restore()` → Dialog mit `auto_restore=True`
3. Restore, `_end_session()`, Sitzung verlässt die Mailbox →
   `enter_host_mode()` → `host_mode_changed(True)`
4. `_check_archive_restore_trigger()`: `fresh_boot_defaults` immer noch
   `True` → **wieder vorgemerkt**
5. `dlg.exec()` kehrt zurück → `_update_maildrop_gate_ui()` → Tor offen →
   `_offer_archive_restore()` zählt Kandidaten **nur aus dem Archiv**
   (2 > 0) → neuer Dialog → Sitzung öffnen, Listing zeigt alles als
   `TNC + archive`, keine Kandidaten → verlassen → weiter bei 3.

Ergebnis: **Endlosschleife** von MailDrop-Sitzungen (je ca. 7 s,
Packet-Betrieb dauerhaft ausgesetzt, fremde Stationen erhalten BUSY).
Mit `ask` dieselbe Schleife, nur mit einer Rückfrage je Durchlauf — auch
nach „No", auch nach jeder manuell geöffneten MailDrop-Sitzung.

Das ist genau der Fehler aus P59 B.3, eine Ebene weiter oben: P59 hat das
Ereignis vom klebrigen Zustand getrennt, es aber nie **verbraucht**. Der
Fehler liegt auch in der P59-Spec selbst (D.1 hängt am
`host_mode_changed`-Signal, ohne festzulegen, dass das Ereignis nur einmal
gilt) — CC hat sie korrekt umgesetzt.

Kein Test hat es gefangen: P59 F prüft „zweiter Gate-Update → keine zweite
Rückfrage", aber nicht „zweites `host_mode_changed(True)` im selben
Einschaltzyklus".

### B.2 Scheitert der Auto-Restore, bleibt die Sitzung offen (mittel)

`maildrop_dialog.py`, `_on_failed()`, Zweig `restore`:

```python
if then is not None and then == self.session.leave:
    then()
```

Beim Restore ist die Fortsetzung **nie** `session.leave` — sie ist
`session.list` (manuell), `_finish_auto_restore` (Auto) oder
`_end_session` (Abbruch per Schließen). Die Bedingung ist also toter Code.
Schlägt beim Auto-Restore ein `send` fehl (z. B. Mailbox voll), bleibt die
Sitzung ACTIVE, das Banner meldet weiter „Restoring…", der Packet-Betrieb
bleibt ausgesetzt, bis jemand den Dialog schließt. Beim Auto-Restore direkt
nach dem Start sitzt womöglich niemand davor.

P59 C.1 verlangte: Fortsetzung trotzdem aufrufen, **wenn sie das Verlassen
der Sitzung ist**. Der Vergleich über die Identität einer bestimmten Methode
bildet das nicht ab.

### B.3 Docstring von `filter_restore_scope()` ist sachlich falsch (klein)

Dort steht, `unread` verhalte sich derzeit „like 'all'", weil `mark_read()`
nie aufgerufen wird. Das stimmt nicht: `read_flag` kommt aus der
TNC-Liste (`N`/`Y`) zum Zeitpunkt der Archivierung. Eine Nachricht, die im
TNC schon gelesen war, als sie archiviert wurde, ist ausgeschlossen — genau
das prüft P59s eigener Test
`test_unread_scope_never_restores_the_already_read_message`.

---

## Teil A — Das Ereignis wird verbraucht

### A.1 `SerialManager`
Neue Methode, einzige Stelle, die das Ereignis liest **und** löscht:

```python
def consume_fresh_boot_defaults(self) -> bool:
    """Return fresh_boot_defaults and clear it (P60). An event is handled
    once: every later host_mode_changed(True) in the same power cycle -
    leaving a MailDrop session, 'Enter Host Mode' from the menu - must
    read False. Only a new init/recovery run with a new banner can set
    it again."""
    fresh = self.fresh_boot_defaults
    self._banner_this_init = False
    return fresh
```

Die Property `fresh_boot_defaults` bleibt (lesend, für Anzeige und Tests).

### A.2 `MainWindow._check_archive_restore_trigger()`
- Ruft `consume_fresh_boot_defaults()` auf, **bevor** die übrigen
  Bedingungen geprüft werden — das Ereignis ist damit verbraucht, egal ob
  die Einstellungen einen Restore wollen. Sonst würde ein späteres
  Umschalten von `never` auf `ask` mitten im Betrieb einen Restore für
  einen längst vergangenen Einschaltvorgang auslösen.
- `getattr(serial, "fresh_boot_defaults", False)` entfällt.

### A.3 `_offer_archive_restore()` bleibt eine Vorab-Schätzung
Keine Änderung nötig, sobald A.1/A.2 greifen. Im Docstring festhalten,
dass die Kandidatenzahl aus dem Archiv allein **nur** deshalb korrekt ist,
weil der Aufruf ausschließlich direkt nach einem Einschalten mit leerer
Mailbox erfolgt.

**Commits:**
```
SerialManager: consume_fresh_boot_defaults reads and clears the event
MainWindow: consume the power-on event once per init run
```

---

## Teil B — Fehlerpfad: ausdrückliche Kennzeichnung statt Methodenvergleich

`maildrop_dialog.py`:

```python
def _start_sync(self, numbers, then, *, ends_session: bool = False) -> None
def _start_restore(self, rows, then, *, ends_session: bool = False) -> None
```

- `ends_session=True` bei: Sync aus `_end_session()`, Auto-Restore aus
  `_on_listing()`, und wenn `_request_close()` die Fortsetzung eines
  laufenden Auto-Restore auf `_end_session` umstellt (dort das Flag
  ebenfalls setzen).
- `_on_failed()`: in **beiden** Zweigen gilt — Warteschlange leeren, und
  wenn `ends_session`, die Fortsetzung aufrufen. Alle Vergleiche
  `then == self.session.leave` entfallen.
- Statuszeile beim Restore-Abbruch:
  `Restore incomplete: X of N restored - ending the session.`
  (Zähler analog zu `_sync_done`/`_sync_total`.)

**Commit:** `MailDrop dialog: failure path follows ends_session, not method identity`

---

## Teil C — Docstring

`archive.py`, `filter_restore_scope()`: den Satz über „behaves like 'all'"
ersetzen durch: *„'unread' uses the read flag as the TNC listed it when the
message was archived. mark_read() is not called anywhere yet, so a message
read later inside PK232PY stays 'unread' here."*

**Commit:** `MailDrop archive: correct the unread scope docstring`

---

## Teil D — Tests (jeder zuerst rot)

**`test_serial_manager.py`**
- nach Init mit Banner: `consume_fresh_boot_defaults()` → True, zweiter
  Aufruf → False, `tnc_defaults` bleibt True
- neuer Init mit Banner nach dem Verbrauch → wieder True

**`test_main_window_packet.py`**
- **Regressionstest B.1:** Init mit Banner, `ask`, Tor offen; dann
  `host_mode_changed(True)` ein **zweites** Mal (simuliert das Verlassen
  einer MailDrop-Sitzung) → insgesamt genau **eine** Rückfrage
- dasselbe mit `auto` und gepatchtem `MailDropDialog`: genau **ein**
  Dialog, auch wenn dessen `exec()` selbst `host_mode_changed(True)`
  auslöst (so läuft es am Gerät)
- `never` beim Einschalten, danach auf `ask` umgestellt, danach
  `host_mode_changed(True)` → **keine** Rückfrage (A.2)

**`test_maildrop_dialog.py`**
- `auto_restore=True`, zwei Kandidaten, erstes `send` → `failed` →
  `leave` wird aufgerufen, kein zweites `send`, Statuszeile
  `Restore incomplete: 0 of 2`
- Abbruch per Schließen, danach `failed` → `leave` wird aufgerufen
- manueller Restore, `failed` → **kein** `leave` (Verhalten wie bisher)

Im Abschlussbericht je Test die Zeile des roten Laufs.

---

## Teil E — Hardware: T137 ergänzen

In `Testplan.md` bei T137 nach Schritt 3 einfügen:

> 3a. Nach dem erfolgreichen Restore die MailDrop-Sitzung **manuell**
> öffnen und wieder beenden. **Erwartet:** keine erneute Rückfrage, kein
> erneuter Restore.
> 3b. TNC → Leave Host Mode, dann Enter Host Mode. **Erwartet:** ebenso
> keine Rückfrage.

Und als Vorbedingung: „Erst mit `ask` durchführen. `auto` erst, wenn 3a/3b
mit `ask` bestanden sind."

**Commit:** `Testplan: T137 re-entry steps (P60)`

---

## Teil F — Dokumentation

- `CLAUDE.md`, Abschnitt MailDrop: Ereignisse werden **verbraucht**, nicht
  nur von Zuständen getrennt. Merkregel: ein Signal wie
  `host_mode_changed(True)` sagt „Host Mode ist jetzt aktiv", nicht „der
  TNC wurde gerade eingeschaltet" — es kommt aus mehreren Quellen.
- `Backlog.md`: P59-Eintrag um den Verweis auf P60 ergänzen.

**Commits:**
```
Docs: CLAUDE.md consume one-shot events
Backlog: P60 follow-up to P59
Docs: add P60 spec file
```

---

## Definition of Done

- `pytest` grün; die drei Regressionstests aus D (B.1 zweimal, B.2) waren
  vor der Umsetzung nachweislich rot
- `git grep -n "then == self.session.leave" -- src` → keine Treffer
- `git grep -n "fresh_boot_defaults" -- src/pk232py/ui` → keine Treffer
  (die UI liest das Ereignis nur noch über `consume_…`)
- T137 in `Testplan.md` mit den Schritten 3a/3b und der Vorbedingung
- **Push nach dem letzten Commit** (`git push`), Meldung mit dem Hash
- `.\Sources2Text.ps1`, danach Meldung „sources aktualisiert"