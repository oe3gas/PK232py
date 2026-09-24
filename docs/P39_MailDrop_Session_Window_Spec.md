# Claude Code Prompt — P39: Sitzungsmaske MailDrop

> Ablage: `docs/P39_MailDrop_Session_Window_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher `CLAUDE.md` (MailDrop, Qt-Threading, „zwei Wahrheiten"),
> `Backlog.md`, `Testplan.md` lesen.
> Vorlage: das freigegebene Mockup `maildrop_dialog.py` (Sitzungsfassung
> mit Eingangstor, Banner, `Where`-Spalte, Verfassen-Dialog).
> Bausteine, die alle bereits stehen: `maildrop/protocol.py`,
> `maildrop/session.py` (T119: 10/10 am Gerät), `maildrop/archive.py`.

---

## Was gebaut wird

Ein **modaler Dialog**, kein Eintrag in der Betriebsart-ComboBox.

Begründung, die als Kommentar in die Datei gehört: MailDrop ist **keine
Betriebsart des TNC**, sondern eine Sitzung innerhalb des Packet-Betriebs
— `MDCHECK` wechselt den Modus nicht. Ein Eintrag in der ComboBox würde
die Moduszustandsmaschine mit einem Eintrag belasten, der keiner ist, und
die Frage aufwerfen, was ein Moduswechsel während laufender Mailbox-Sitzung
bedeutet.

### Zwei Zugänge, beide mit denselben Bedingungen

1. `btn_maildrop` in der Packet-Maske (existiert, derzeit deaktiviert)
2. Menüeintrag `TNC → MailDrop…`

Beide öffnen denselben Dialog. Beide sind **gesperrt** mit Begründung im
Tooltip, wenn eine Bedingung fehlt:

| Lage | Tooltip |
|---|---|
| `has_maildrop is False` | this firmware has no MailDrop |
| ein Kanal verbunden | disconnect channel N first |
| aktuelle Betriebsart nicht HF/VHF Packet | switch to HF or VHF Packet first |
| keine Verbindung / kein Host Mode | connect to the TNC first |

Die Kanalinformation kommt aus der Kanalleiste (`channel_map()`), die
Betriebsart aus dem `ModeManager` — **nicht** neu ermitteln.

---

## P39.1 — `src/pk232py/ui/dialogs/maildrop_dialog.py` (neu)

Aufbau nach dem Mockup, zwei Seiten in einem `QStackedWidget`:

**Seite „geschlossen" (Eingangstor)**
- Erklärtext: Die Sitzung legt den Packet-Betrieb still, fremde Stationen
  erhalten BUSY
- Prüfliste mit drei Zuständen — `OK` (grün), `--` (sperrend, bernstein),
  `i` (Hinweis, grau; etwa fehlendes `MYMAIL`, das nur den Fernzugriff
  betrifft)
- Knopf `Open MailDrop session`, gesperrt bei sperrender Bedingung
- Fußnote zum Unterschied Fernzugriff (MAILDROP ON) vs. lokale Verwaltung

**Seite „Sitzung"**
- Banner über die volle Breite, bernstein, dauerhaft sichtbar:
  „MailDrop session active · packet operation is suspended · incoming
  connects receive BUSY"
- Werkzeugzeile: `Sync to archive`, `Restore to TNC`, `New…`, `Reply`,
  `Kill`, `Header…`, `Save as…`, Filter
- Liste (`QTreeWidget`) mit den Spalten aus dem Mockup, `Where` farbig
- Lesebereich darunter
- Fußzeile: Archivpfad, Zähler, Knopf `End session`

### Die `Where`-Spalte und der leere Anfang

`TNC + archive` / `TNC only` / `archive only` entstehen über den
Fingerabdruck aus `archive.py`. **Wichtig:** Bei leerem Archiv steht
alles auf `TNC only`, und `archive only` kann es erst nach dem ersten
`Sync to archive` geben.

Der Dialog erklärt das, statt es rätseln zu lassen: ist das Archiv leer
oder ausgeschaltet, erscheint über der Liste eine Hinweiszeile —
„Archive is empty (or disabled) — every message shows as 'TNC only'
until you sync." Ist `archive_enabled` aus, sind `Sync to archive` und
`Restore to TNC` gesperrt, mit Verweis auf den Parameterdialog.

**Commit:** `UI: MailDrop session dialog`

---

## P39.2 — Anbindung an die Sitzung

- `MailDropSession` wird vom Dialog erzeugt und besessen; `can_open`
  liefert die Prüfliste aus P39.0
- **Ausschließlich signalgetrieben.** Nie auf `session.state` pollen —
  siehe die Regel „zwei Wahrheiten" in `CLAUDE.md`: gewartet wird auf das
  Signal, das den Wert liefert, den man danach benutzt
- Während `OPENING` und `CLOSING`: Bedienelemente gesperrt, Fortschritt
  sichtbar (siehe P39.3)
- `failed(text)`: Text in einer Statuszeile des Dialogs anzeigen, Sitzung
  nicht stillschweigend als beendet behandeln. Meldet die Sitzung
  `FAILED`, zeigt der Dialog den Handgriff für den Bediener und bietet
  `Retry` sowie `Close` an
- `prompt_info`: freier Speicher in der Kopfzeile
- jede Nachricht, die über `message_read` kommt, wandert bei aktivem
  Archiv über `add()` hinein (Duplikate fängt der Fingerabdruck)

**Commit:** `UI: MailDrop dialog drives the session by signals only`

---

## P39.3 — Schließen: Rückfrage, dann beenden mit Statusanzeige

Fenster schließen (X, Esc, `Close`) bei laufender Sitzung:

1. Rückfrage: „The MailDrop session is still open. End it and return to
   normal packet operation?" mit `End session` / `Cancel`
2. Bei Bestätigung: Sitzung beenden **und dabei anzeigen, was passiert** —
   bei 9600 Bd dauert der Rückweg mehrere Sekunden:

   ```
   Leaving the mailbox (B) …
   Re-entering Host Mode …
   Confirming Host Mode …
   ```

   Umsetzung über `state_changed` und die Meldungen der Sitzung; ein
   unbestimmter Fortschrittsbalken genügt, **kein** eingefrorenes Fenster
3. Erst nach `CLOSED` schließt der Dialog. Bei `FAILED` bleibt er offen
   und zeigt den Handgriff
4. Die Rückfrage entfällt, wenn die Sitzung bereits geschlossen ist

**Commit:** `UI: confirm and show progress when ending the session`

---

## P39.4 — Verfassen und Löschen

- `MailComposeDialog` aus dem Mockup übernehmen, inklusive der beiden
  gemessenen Regeln: eine Zeile, die mit `/EX` beginnt, sperrt das Senden;
  Nicht-ASCII wird angekündigt und über `sanitize_body()` umgeschrieben
- Felder `To`, `@ BBS`, `From`, `Type` → `build_send_command()`;
  **nichts selbst zusammensetzen**
- `Kill` fragt nach und nennt dabei, **wo** gelöscht wird (TNC, Archiv
  oder beides) — bei zwei Speichern muss das dastehen
- `Header…` vorerst gesperrt: `E` (EDIT) ist ungemessen. Tooltip
  „EDIT not measured yet", Backlog-Eintrag

**Commit:** `UI: compose and kill in the MailDrop dialog`

---

## P39.5 — Knopf und Menü

- `btn_maildrop` und `TNC → MailDrop…` öffnen den Dialog; Sperrlogik und
  Tooltips wie oben, an **einer** Stelle berechnet und von beiden benutzt
- Der Knopf färbt sich, wenn Post wartet: `PromptInfo.have_mail` aus der
  letzten Sitzung, und — sobald das gemessen ist — `MDMON` im laufenden
  Betrieb. Solange nur die erste Quelle existiert, nur danach färben,
  ohne Vermutung über den Rest
- P21.5 (Knopf sendete `MI`) ist damit abgelöst: kein Frame mehr, sondern
  ein Dialog

**Commit:** `UI: MailDrop button and menu entry open the session dialog`

---

## P39.6 — Tests

Qt-Tests offscreen, wie in `test_packet_screen.py`:

- Eingangstor: jede der vier Sperrbedingungen sperrt den Knopf und zeigt
  ihren Tooltip; keine Sperre → Knopf frei
- Sitzung gegen eine Attrappe von `MailDropSession`: `listing` füllt die
  Liste, `stored` löst ein erneutes `list()` aus, `failed` zeigt die
  Statuszeile und schließt **nicht**
- Schließen mit laufender Sitzung: Rückfrage erscheint; bei `Cancel`
  bleibt die Sitzung offen; bei `End session` wird `leave()` gerufen und
  der Dialog schließt erst nach `CLOSED`
- `FAILED` beim Beenden → Dialog bleibt offen, Text sichtbar
- leeres Archiv → Hinweiszeile erscheint, `Restore to TNC` gesperrt
- `archive_enabled` aus → beide Archivknöpfe gesperrt, Verweis auf die
  Einstellungen

**Commit:** `Tests: MailDrop session dialog`

---

## P39.7 — Dokumentation

- `CLAUDE.md`: Der MailDrop-Dialog ist ein Dialog, keine Betriebsart, mit
  der Begründung; Zugänge und Sperrbedingungen
- `Testplan.md`: Hardwarefälle — Dialog öffnen, Nachricht schreiben,
  lesen, löschen, beenden; Eintritt bei verbundenem Kanal verweigert;
  Schließen mit laufender Sitzung
- `Backlog.md`: `Header…`/EDIT ungemessen; `MDMON` als zweite Quelle für
  „Post wartet"; `Sync`/`Restore` als eigenes Folgepaket, falls sie hier
  noch nicht vollständig werden

**Commit:** `Docs: MailDrop session window`

---

## Definition of Done

- `.venv\Scripts\python.exe -m pytest` grün
- Kein Pollen auf `session.state` im Dialog — geprüft
- Der Dialog schließt nie, solange die Sitzung nicht `CLOSED` meldet
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"
- Danach vom Operator: Dialog am Gerät öffnen, eine Nachricht schreiben,
  lesen, löschen, Sitzung beenden