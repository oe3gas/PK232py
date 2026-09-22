# Claude Code Prompt — P24: MailDrop im Host Mode messen

> Ablage: `docs/P24_MailDrop_HostMode_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher `CLAUDE.md`, `Backlog.md`, `Testplan.md`, `SERIAL_CONNECTION_STATE_MACHINE.md`
> lesen. Fixture für die Runde-3-Befunde: `hw_logs/20260922_200013_maildrop.log`.

---

## Befunde Runde 3 (22.09.2026, 20:00) — zuerst dokumentieren

- **Fremder Absender funktioniert:** `S OE3GAS < DL1ABC` → Liste zeigt
  `1 PN 44 OE3GAS DL1ABC … Test Subjekt`. Der SysOp darf das FROM-Feld
  setzen (Syntax `<`, nicht `>`).
- **`/E`-Zeile ist kein Formatbestandteil:** beide `R`-Antworten dieser
  Runde enden mit `\r\n<text>\r\n\r\n`, ohne `/E`. Das Vorkommen in
  Runde 1 blieb einmalig. Parser soll eine abschließende `/E`-Zeile
  **tolerieren**, aber nicht erwarten.
- **`Ctrl-Z` beendet die Nachricht nicht:** `$1A` wurde dreimal gesendet
  und nur zurückgeechot; beendet wurde jedes Mal durch `/EX`. Vermutlich
  fehlt ein `CR` nach `$1A` — **nicht weiter untersucht**, weil `/EX`
  zuverlässig ist und die Anwendung dieses verwenden wird.
- **`R2` ohne Leerzeichen** → `*** Not enough`
- **Nicht-ASCII geht verloren:** „für" kam als `f?r` an (Werkzeug
  ersetzt). Ob der TNC 8-Bit annimmt, hängt an `8BITCONV` und ist
  **ungemessen**.

### Designfolgen (in `CLAUDE.md`)
- Der Dialog **prüft vor dem Senden**, dass keine Textzeile mit `/EX`
  beginnt — sonst bricht die Übertragung mitten im Text ab
- Umlaute vorerst umschreiben (ue, oe, ae, ss), bis `8BITCONV` gemessen ist
- `<` setzt FROM, `@` setzt die BBS, `SB`/`ST` setzen den Typ — damit kann
  eine Wiederherstellung Absender, BBS und Typ erhalten; **nicht** das
  ursprüngliche Datum (der TNC stempelt beim Speichern)

**Commit:** `Docs: MailDrop round 3 results`

---

## P24.1 — Altbestand markieren, nicht raten

`src/pk232py/maildrop/maildrop.py` führt im Docstring eine Tabelle
„MailDrop Host Mode mnemonics (STABO manual Ch. 12)" mit Einträgen wie
`MD MDPROMPT`, `MY MYMAIL`, `LM LASTMSG`, `3P 3RDPARTY`, `KF KILONFWD`,
`DM MDMON`, `TL TMAIL`.

**Keiner dieser Einträge ist belegt**, und `MD` ist laut TRM MDIGI. Das ist
derselbe Fall wie `MI` (T47).

- Tabelle im Docstring als **unverified** kennzeichnen, mit Datum und
  Verweis auf die belegte Tabelle in `CLAUDE.md`
- prüfen, ob der Code diese Mnemonics tatsächlich **sendet**; falls ja: die
  Stellen im Commit-Text auflisten und in `Backlog.md` als Priorität 1
  eintragen (senden, was man nicht belegt hat, ist der Fehler aus T86)
- **nichts umbenennen, nichts korrigieren** — das ist ein eigenes Paket
  nach der Messung

**Commit:** `MailDrop module: mark unverified mnemonic table`

---

## P24.2 — `tools/hw_check.py`: Subcommand `maildrop_host`

### Ausgangslage aus dem Handbuch

Der Befehl `HOST` ist bitweise:

| Bit | Bedeutung |
|---|---|
| 0 | Host Mode ein/aus |
| 1 | **lokales Einloggen in die MailDrop**: 0 → Sendedaten `$20`, Lesedaten `$2F`; 1 → **Sendedaten `$60`, Lesedaten `$70`**, mitgelesene MXMIT-Daten `$2F` |
| 2 | erweiterter Host Mode |

`pk232py` betritt den Host Mode mit `HOST 3` (Bit 0 + Bit 1) — die
Anwendung läuft also bereits in der Variante mit `$60`/`$70`.

**Alles Weitere ist unbekannt** und Gegenstand dieser Messung: ob ein
Einloggen nötig ist, ob Prompt und Listen identisch über `$70` kommen, und
ob Befehle als `$60`-Datenframe genügen.

### Ablauf

**Reiner Empfang und Lesen — keine Aussendung, keine schreibenden
Mailbox-Befehle** (`S`, `K`, `E` sind in dieser Runde verboten; Schreiben
ist im verbose-Weg bereits gemessen).

1. `normalize()` wie bei allen Tests
2. `XMITOK` abfragen und wie bisher warnen
3. **Testnachricht über den bekannten, sicheren Weg anlegen**: verbose
   `MDCHECK`, `S OE3GAS`, Betreff `Host Mode Test`, eine Textzeile, `/EX`,
   `L` (Nummer merken), `B`. Damit ist sicher etwas zum Auflisten da,
   unabhängig davon, ob der TNC gerade ausgeschaltet war
4. verbose: `HOST` abfragen → aktuellen Wert protokollieren
5. Host Mode betreten über den **vorhandenen Pfad** von `pk232py.comm`
   (der `HOST 3` sendet), anstehende Frames abräumen
6. **Sonde A** — Befehl als Datenframe im MailDrop-Block:
   Frame `SOH $60 'L' CR ETB` senden (DLE-Stuffing über die vorhandene
   Funktion, **kein** eigener Frame-Bau). Danach 3 s lang **alle**
   eintreffenden Frames roh protokollieren: CTL, Kanal, Daten hex und
   Text.
   - Erwartung laut Handbuch: Antwort im `$70`-Block
7. **Sonde B** — nur wenn A nichts liefert: `SOH $60 'MDCHECK' CR ETB`,
   danach erneut `SOH $60 'L' CR ETB`, wieder alles protokollieren
8. **Sonde C** — nur wenn A und B nichts liefern: prüfen, ob der TNC
   überhaupt im MailDrop-Bit läuft: verbose `HOST` erneut abfragen
   (nach Verlassen des Host Mode). **Keine** geratenen Mnemonics senden
9. Wenn eine Liste zurückkam: `SOH $60 'R <n>' CR ETB` mit der Nummer aus
   Schritt 3, alles protokollieren
10. Abschluss: `SOH $60 'B' CR ETB` senden, Antwort protokollieren, dann
    Host Mode über den vorhandenen Pfad verlassen
11. `finally`: Host Mode verlassen; danach verbose prüfen, ob `cmd:`
    erscheint; sonst deutliche Warnung

Vor Schritt 6 **eine** Bestätigung `y/N` mit dem Hinweis, dass jetzt
unbekannte Frame-Typen gesendet werden, die nur lesende Mailbox-Befehle
enthalten.

### Auswertung in der Zusammenfassung

- welcher Frame-Typ die Antwort trug (`$70`, `$7x`, etwas anderes)
- ob der Mailbox-Prompt identisch zur verbose-Fassung ist
- ob ein Einloggen nötig war (Sonde A genügte / erst nach `MDCHECK`)
- ob Listenformat und Leseausgabe byteweise dem verbose-Weg entsprechen

**Commit:** `Tools: hw_check maildrop_host measurement`

---

## P24.3 — Tests

Ohne Hardware, für die reinen Logikteile:

- der Frame für Sonde A ist `SOH $60 … ETB` mit korrektem Stuffing
  (gegen die vorhandene Stuffing-Funktion geprüft)
- die Auswertung ordnet eine Antwort mit CTL `$70` als MailDrop-Lesedaten
  ein, `$2F` als mitgelesene MXMIT-Daten, `$4F`/`$5F` wie gehabt
- Sonde B läuft nur, wenn A leer blieb

**Commit:** `Tests: maildrop_host frame building and classification`

---

## P24.4 — Dokumentation

- `docs/HW_Solo_Tests.md`: `maildrop_host` ergänzen
- `Testplan.md`: neuer Fall, Status OPEN, mit den vier Auswertungsfragen
- `CLAUDE.md`: die HOST-Bit-Tabelle aufnehmen (Bit 0/1/2), mit dem
  Hinweis, dass die Anwendung `HOST 3` verwendet und damit das
  MailDrop-Bit gesetzt ist — bisher ungenutzt

**Commit:** `Docs: HOST bits and maildrop_host test`

---

## Definition of Done

- `python -m pytest` grün
- `--dry-run maildrop_host` zeigt jeden geplanten Frame in Hex
- Kein Code unter `src/pk232py/` verändert außer dem Docstring aus P24.1
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"
- Danach vom Operator: `maildrop_host`, Logdatei an den Chat