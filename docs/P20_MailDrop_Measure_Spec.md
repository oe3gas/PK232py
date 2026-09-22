# Claude Code Prompt — P20: MailDrop-Protokoll messen, Scan-Tabelle richtigstellen

> Ablage: `docs/P20_MailDrop_Measure_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher `CLAUDE.md`, `Backlog.md`, `Testplan.md` und das MailDrop-Mockup
> `maildrop_dialog.py` lesen.

---

## Teil A — Richtigstellung: die Mnemonic-Tabelle ist kein Hardwarebeleg

`pk232_mnemonic_table.txt` trägt die Überschrift „Host Mode Mnemonic Scan",
nennt einen COM-Port und wirkt wie ein Messergebnis. Am Dateiende steht:

```
No response (674): AA AB AE AF ...
```

Von 676 abgefragten Kombinationen haben **nur `AC` und `AD`** geantwortet,
beide mit Fehlercode. Die Spalte „KNOWN NAME" stammt nicht vom Gerät,
sondern aus einer Zuordnungsliste (vermutlich TRM 4.2.2). Der Scan ist
gescheitert.

Die Tabelle wurde in P13 und P14 fälschlich als „Scan des realen Geräts"
und primäre Belegquelle bezeichnet (Fehler in der Spezifikation, nicht in
der Umsetzung). Folgen sind begrenzt: die P13-Befehlsnamen sind durch den
Upload in T103 am Gerät bestätigt (verbose, „was/now"-Antworten).

### A.1 — Dokumentation

**`CLAUDE.md`:** jede Stelle suchen, die die Tabelle als Hardwarebeleg,
„Scan" oder „scanned" bezeichnet, und korrigieren:

- die Tabelle ist eine **Namensliste**, keine Messung (674/676 ohne Antwort)
- Belegquellen in dieser Reihenfolge: (1) eigener Lauf mit
  `tools/hw_check.py` am Gerät, (2) TRM 4.2.2, (3) die Tabelle nur noch als
  Transkript des TRM
- neuer Abschnitt **„Hardware-confirmed Host Mode mnemonics"** mit Quelle
  je Eintrag:

| Mnemonic | Bedeutung | Beleg |
|---|---|---|
| `PX` | PASSALL | T86, T111 (`PXN`/`PXY`) |
| `PS` | PASS | T86, T111 (`PS$16`) |
| `SL` | SLOTTIME | T112 (30 → 10) |
| `VH` | VHF | T112 (Wiederherstellung meldet `Vhf was OFF`) |
| `HB` | HBAUD | T112 (Wiederherstellung meldet `HBaud was 300`) |
| `HP` | HPOLL | verspätete Antwort nach Host-Mode-Eintritt |
| `MX` | MAXFRAME | **offen** — T112-Wiederholung |

Jeder künftige Hardwarebefund zu einem Mnemonic wird in diese Tabelle
eingetragen.

**Kopfzeile der Datei `pk232_mnemonic_table.txt` selbst nicht ändern** —
sie ist ein historisches Artefakt. Stattdessen eine Datei
`docs/MNEMONIC_TABLE_NOTE.md` mit drei Sätzen: was die Datei ist, dass der
Scan gescheitert ist, wo die belegte Tabelle steht.

### A.2 — Backlog

- **Neuer Mnemonic-Scan** mit dem inzwischen funktionierenden
  `query_host()` (Zuordnung am Präfix, Puffer abräumen). **Nicht blind über
  alle 676 Kombinationen:** ein nacktes Mnemonic kann eine Sofortaktion
  auslösen — Connect, Disconnect, Moduswechsel, Senden, Reset. Voraussetzung
  ist eine Sperrliste aller Aktionsbefehle aus dem TRM, die nie gesendet
  werden. Eigenes Paket, Priorität 2.
- **`MI` im MailDrop-Button** (T47): laut TRM-Liste MFILTER, nicht
  MailDrop. T47 war nur frame-verifiziert. Mit Verweis auf Teil C.

**Commit:** `Docs: mnemonic table is a name list, not a hardware scan`

---

## Teil B — `tools/hw_check.py`: Subcommand `maildrop` (Mitschreib-Terminal)

### Warum ein geführtes Terminal statt eines Skripts

Wie man die Mailbox lokal öffnet, welche Befehle sie kennt, wie ein
Nachrichtentext beendet wird und wie die Liste aussieht, ist **nicht
bekannt**. Ein Skript müsste all das raten. Deshalb: die Mailbox erklärt
sich über ihre eigene Hilfe, der Operator tippt, das Werkzeug schreibt
**jedes Byte** in beide Richtungen mit Zeitstempel mit.

**Reiner verbose-Betrieb, keine Aussendung** — die lokale Mailbox-Sitzung
läuft über die serielle Schnittstelle, nicht über Funk. Trotzdem vorab
`XMITOK` abfragen und protokollieren; steht es auf `ON`, den Operator
darauf hinweisen (Sicherheit, falls die Mailbox wider Erwarten etwas
aussendet).

### Ablauf

1. verbose: abfragen und protokollieren — `MAILDROP`, `MYMAIL`, `MYCALL`,
   `MTEXT`, `MMSG`, `3RDPARTY`, `KILONFWD`, `TMAIL`, `MDMON`, `XMITOK`.
   Ein `?What?` ist ein Befund (Befehl existiert nicht), kein Abbruch.
2. Hinweis: „Opening the local MailDrop with MDCHECK" — Befehl `MDCHECK`
   senden. **Nicht auf `cmd:` warten** — in der Mailbox gilt ein anderer
   Prompt. Stattdessen lesen, bis 1,5 s lang nichts mehr kommt
   (`read_until_idle(idle=1.5, max_total=10)`, neue Hilfsfunktion). Die
   Antwort roh und als Text anzeigen.
3. **Interaktive Phase**: Eingabezeile `md>` auf der Konsole. Jede Zeile
   wird mit `\r` an den TNC gesendet, danach `read_until_idle()`, Ausgabe
   anzeigen. Steuerzeichen sind eingebbar als `^Z`, `^D`, `^C` (werden als
   Byte `$1A`, `$04`, `$03` gesendet und im Protokoll als solche vermerkt).
4. Vor der interaktiven Phase einen **Vorschlag** anzeigen, keine Pflicht:

   ```
   Suggested sequence (follow the mailbox's own prompts):
     H           help - learn the real command set first
     L           list (probably empty after power-up)
     S OE3GAS    write a test message to yourself - follow the prompts
                 for subject and text; the help tells how to end the text
     L           list again - note number, status letters, format
     R <n>       read it
     S OE3GAS    a second message
     K <n>       kill the first one
     L           list again
     B           leave the mailbox (or whatever the help says)
   ```

5. Beenden der interaktiven Phase mit `/quit` (Werkzeug-Befehl, wird nicht
   gesendet). Danach eine Sekunde lesen und prüfen, ob `cmd:` erscheint —
   das zeigt, ob die Mailbox verlassen wurde.
6. **Kein automatisches Verlassen im `finally`**: der Befehl dafür ist
   unbekannt. Hängt die Sitzung noch in der Mailbox, eine deutliche
   Warnung ausgeben, welche Eingabe laut Protokoll zuletzt ankam, und dass
   der Operator die Mailbox im normalen Terminal verlassen muss.

### Optionaler Schritt: Verlust beim Ausschalten

Nach `/quit` fragen: „Power-cycle the TNC now to confirm the mailbox is
lost? (y/n)". Bei `y`: Operator schaltet aus und ein, bestätigt, Werkzeug
öffnet erneut die serielle Verbindung (Autobaud/Banner wie beim normalen
Start, vorhandene Funktion wiederverwenden), fragt `MYCALL` ab und öffnet
erneut `MDCHECK` für ein einzelnes `L`. Alles protokolliert.

### Protokoll

`hw_logs/<zeit>_maildrop.log`: jede Zeile mit Zeitstempel und Richtung
(`>>` / `<<`), Rohbytes in Hex **und** als Text, Steuerzeichen sichtbar
(`<CR>`, `<LF>`, `<^Z>`). Am Ende eine Zusammenfassung mit allen
Antworten aus Schritt 1 und allen Mailbox-Ausgaben in Reihenfolge.

---

## Teil C — `tools/hw_check.py`: Subcommand `mi` (nur Abfrage)

Was sendet der MailDrop-Button der Anwendung tatsächlich?

1. Host Mode betreten, Puffer abräumen
2. `MI` **ohne Argument abfragen** (`SOH $4F M I ETB`), Antwort per
   Präfix zuordnen und protokollieren
3. Host Mode verlassen
4. verbose: `MFILTER` abfragen → Wert protokollieren

Auswertung: liefert `MI` denselben Wert wie `MFILTER`, ist `MI` = MFILTER
belegt und der MailDrop-Button der Anwendung sendet den falschen Befehl.
**Keine schreibenden Befehle.**

Unit-Test (ohne Hardware): der Mnemonic, den `mi` abfragt, ist derselbe,
den `main_window.py` für `btn_maildrop` sendet — sonst misst das Werkzeug
etwas anderes als die Anwendung (Muster aus P17.2).

**Commits:**
```
Tools: hw_check maildrop recorder and mi probe
Tests: hw_check maildrop recorder and mi probe logic
```

---

## Teil D — Dokumentation der Werkzeuge

- `docs/HW_Solo_Tests.md`: `maildrop` und `mi` ergänzen — Vorbereitung,
  Ablauf, vorgeschlagene Sequenz, wie man die Sitzung beendet, was bei
  hängender Mailbox zu tun ist
- `Testplan.md`: zwei neue Fälle (nächste freie Nummern) für die
  MailDrop-Messung und die `MI`-Abfrage, Status OPEN

**Commit:** `Docs: MailDrop measurement and MI probe`

---

## Definition of Done

- `python -m pytest` grün
- `--dry-run maildrop` und `--dry-run mi` zeigen die geplanten Schritte
- Kein Code unter `src/pk232py/` verändert
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"
- Danach vom Operator: `mi`, dann `maildrop` mit der vorgeschlagenen
  Sequenz, Protokoll an den Chat