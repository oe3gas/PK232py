# Claude Code Prompt — P21: MailDrop-Rekorder sicher machen

> Ablage: `docs/P21_MailDrop_Recorder_Fix_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher `CLAUDE.md`, `Backlog.md`, `Testplan.md` lesen, dazu das
> STABO-Handbuch Kapitel 5 (MailDrop-Betrieb, S. 56–63).
> Die Konsolenmitschnitte vom 22.09.2026, 15:40–15:43 (`mi` zweimal,
> `maildrop` zweimal) dienen als Fixtures — beim Operator anfordern, falls
> nicht unter `hw_logs/`.

---

## Befunde vom 22.09.2026

### Belegt
- **`MI` = MFILTER**: Host Mode `MI$80`, verbose `MFIlter $80` (zweiter
  Lauf). Der MailDrop-Button der Anwendung sendet `MI` → fragt MFILTER ab.
- **`MDCHECK` öffnet die Mailbox auch im Werkszustand** (`MYCALL PK232`,
  `MAILDROP OFF`). Realer Prompt:
  `(AEA PK-232M)  18536 free  (B,E,K,L,R,S) >` — runde Klammern, doppelte
  Leerzeichen, abweichend vom Handbuch (`[AEA PK-232M] … >`).
- **`H` im SysOp-Modus → `*** What?`** (Handbuch: SysOp-Befehle nur
  `B,E,K,L,R,S`; `H`/`?` nur für fremde User).
- **`B` → sofort `cmd:`**, ohne weitere Meldung.
- **`KILONFWD` → `?EXPERT command`** (erklärt die `EXPERT ON`-Klammer im
  Uploader).
- Auf **TNC-Ebene**: `E` → `?EXPERT command`; `K` → `?need MYcall`
  (`K` = CONVERSE).

### Fehler im Werkzeug
1. **Sicherheitsproblem:** Nach `B` war die Mailbox geschlossen, der
   `md>`-Prompt blieb. Folgende Eingaben gingen an den TNC-Befehlsinterpreter.
   `K` dort = CONVERSE; mit gesetztem `MYCALL` und `XMITOK ON` wären
   weitere Zeilen **ausgesendet** worden.
2. **Kein definierter Startzustand:** Im ersten Lauf lief SIAM weiter und
   schrieb Ergebnisse asynchron in alle Antworten (`Baudot, RXRev OFF`
   mitten in der XMITOK-Antwort, `0.78: 50 baud,` nach dem Mailbox-Prompt).
3. **Verbose-Parser nach Position:** `parse_query_value()` nimmt die erste
   Zeile als Echo. Ein Rest `d:\` vor dem Echo und eine eingeschobene
   SIAM-Zeile machten `MAILDROP` und `XMITOK` unlesbar; `MFILTER` kam leer.
4. **Falsche Befehlsfolge in meiner Spezifikation (P20):** „zuerst `H`" —
   für den SysOp nicht verfügbar.

---

## P21.1 — Verbose-Parser: Zeile am Inhalt finden

`parse_query_value(command, response)` sucht die **Wertzeile am Namen**,
nicht an der Position:

- die Wertzeile beginnt mit dem Parameternamen in der gemischten
  Schreibweise des TNC (`MAildrop`, `XMITOk`, `MFIlter`, `MYcall`) —
  Vergleich ohne Groß-/Kleinschreibung: die Zeile beginnt mit einem Präfix
  des abgefragten Befehls, gefolgt von mindestens zwei Leerzeichen
- alle anderen Zeilen ignorieren (Echo, Reste, eingeschobene SIAM-Ausgabe)
- mehrzeilige Werte weiterhin `None`
- `?EXPERT command` als eigener Befund erkennen: `parse_query_value`
  liefert `None`, eine Hilfsfunktion `query_error(response)` liefert den
  Fehlertext (`"?EXPERT command"`, `"?What?"`, `"?bad"`)

Fixtures aus den Mitschnitten, mindestens:

```
'd:\\\r\nMAILDROP\r\nMAildrop  OFF\r\ncmd:'             -> 'OFF'
'XMITOK\r\nBaudot, RXRev OFF\r\nXMITOk    ON\r\ncmd:'    -> 'ON'
'MFILTER\r\nMFIlter   $80\r\ncmd:'                      -> '$80'
'KILONFWD\r\n?EXPERT command\r\ncmd:'                   -> None, Fehler '?EXPERT command'
```

Das ist die verbose-Seite derselben Regel wie beim Host Mode (T86):
**zuordnen am Inhalt, nie an der Reihenfolge.**

**Commit:** `Tools: verbose parser finds the value line by name`

---

## P21.2 — Definierter Startzustand für jeden Hardwaretest

Neue Funktion `Session.normalize()`, aufgerufen **zu Beginn jedes
Subcommands** und **nach jedem Aus-/Einschalten**:

1. `Ctrl-C` (`$03`, COMMAND-Zeichen) senden, dann `\r`, lesen bis Ruhe →
   erwartet `cmd:`
2. `PACKET` senden — beendet eine laufende SIAM- oder andere
   Betriebsart. **Nicht** in Host Mode wechseln.
3. zwei Sekunden lesen: kommt weiterhin asynchrone Ausgabe (z. B.
   SIAM-Zeilen), Warnung ausgeben und protokollieren
4. `MYCALL` abfragen; bei `PK232` (Werkszustand) den Wert aus der
   Konfiguration setzen und das im Protokoll vermerken
   („factory state detected — no RAM battery")

Für `t112`, `t111`, `t17`, `mi`, `siam`, `maildrop` gleichermaßen. Die
vorhandenen Einzelschritte in den Subcommands, die dasselbe tun, dürfen
bleiben, sollen aber nicht doppelt senden.

**Commit:** `Tools: hw_check normalizes TNC state before every test`

---

## P21.3 — Mailbox-Terminal mit Zustandserkennung

### Zustände

| Zustand | erkannt an | Prompt auf der Konsole |
|---|---|---|
| `MAILBOX` | letzte Zeile passt auf `\(AEA PK-232M?\)\s+\d+ free\s+\([A-Z,]+\) >` | `md[18536 free]>` |
| `ENTRY` | nach `S …`, solange kein Mailbox-Prompt kommt | `md-text>` |
| `CMD` | Antwort endet mit `cmd:` | — Terminal beendet sich |

### Regeln

- **Nach jeder Antwort** den Zustand neu bestimmen.
- **Sobald `cmd:` erkannt wird, endet die interaktive Phase sofort** —
  keine weitere Eingabe wird gesendet. Meldung:

  ```
  Mailbox closed (cmd: prompt). Interactive phase ended: further input
  would reach the TNC command interpreter, where 'K' means CONVERSE.
  ```
- Im Zustand `ENTRY` jede Zeile senden; `/EX` in einer eigenen Zeile und
  `^Z` beenden die Nachricht (Handbuch, `MDPROMPT`-Standard). Nach
  `*** No free memory` Warnung ausgeben.
- Unbekannte Antwort ohne Mailbox-Prompt und ohne `cmd:` → Zustand
  unverändert, Warnung „unrecognised response" mit Hexdump.
- Der freie Speicher aus dem Prompt wird bei jeder Antwort protokolliert —
  daraus ergibt sich, wie viel Speicher eine Nachricht belegt.

### `finally`

Ist der Zustand am Ende `MAILBOX` oder `ENTRY`: bei `ENTRY` zuerst `/EX`
senden, dann `B` — beide Befehle sind **im Handbuch belegt und am Gerät
bestätigt** (`B` → `cmd:`, 22.09.2026). Danach `cmd:` verifizieren.
Gelingt das nicht: deutliche Warnung wie bisher.

### Vorgeschlagene Folge (Handbuch Kap. 5, SysOp-Befehle B, E, K, L, R, S)

```
L                list - probably empty after power-up
S OE3GAS         new message - answer the subject prompt, then the text,
                 end with /EX on its own line
L                list - note number, status letter (P/T/B), size, format
R <n>            read it
S OE3GAS         second message
L                list - does numbering continue?
K <n>            kill the FIRST message
L                list - does the gap stay, or are numbers reassigned?
B                leave the mailbox - the terminal ends at cmd:
```

`E` (EDIT) bewusst **nicht** in dieser Runde — Syntax und Rückfragen sind
noch ungemessen; eigene Runde später.

### Ausschalttest

Nach `B` optional wie bisher. **Nach dem Einschalten `normalize()`**
(setzt `MYCALL` wieder), dann `MDCHECK`, `L`, `B`.

**Commit:** `Tools: mailbox terminal tracks state and stops at cmd:`

---

## P21.4 — Tests

Fixtures aus den Mitschnitten vom 22.09.2026:

- Mailbox-Prompt mit runden Klammern und doppelten Leerzeichen → `MAILBOX`,
  `free = 18536`
- `b\r\ncmd:` → `CMD`, interaktive Phase beendet
- **Sicherheitstest:** nach einer `cmd:`-Antwort wird **keine** weitere
  Eingabe gesendet — der Test schickt `k` nach `cmd:` und prüft, dass nichts
  an die Schnittstelle geht
- `h\r\n*** What?\r\n(AEA PK-232M) … >` → `MAILBOX`, kein Fehlerzustand
- eingeschobene SIAM-Zeile nach dem Prompt → Zustand bleibt `MAILBOX`

**Commit:** `Tests: mailbox terminal state machine and cmd: stop`

---

## P21.5 — Anwendung: MailDrop-Button

`main_window._on_packet_maildrop()` sendet `MI` = MFILTER-Abfrage. Bis der
MailDrop-Dialog existiert:

- **keinen Frame mehr senden**
- Button deaktivieren, Tooltip „MailDrop dialog not implemented yet"
- Kommentar mit Verweis auf den Hardwarebefund

Unit-Test: der Button erzeugt keinen Host-Frame.

**Commit:** `MainWindow: MailDrop button no longer sends MI (= MFILTER)`

---

## P21.6 — Dokumentation

### `CLAUDE.md`
- Mnemonic-Tabelle: **`MI` = MFILTER** (22.09.2026, `MI$80` / `MFIlter $80`)
- MailDrop-Abschnitt: realer Prompt, SysOp-Befehlssatz `B,E,K,L,R,S`,
  `B` → `cmd:`, `MDCHECK` funktioniert im Werkszustand, `KILONFWD` ist ein
  EXPERT-Befehl
- **SIAM läuft weiter, bis eine andere Betriebsart gewählt wird**, und
  schreibt asynchron in jede Ausgabe — auch in den Befehlsmodus und in die
  Mailbox. Jeder verbose-Parser muss eingeschobene Zeilen vertragen.
- **Sicherheitsregel für Werkzeuge:** jede interaktive Phase, die in einem
  Unterzustand des TNC läuft (Mailbox, später weitere), endet, sobald der
  TNC `cmd:` meldet. Auf TNC-Ebene sind Einzelbuchstaben Befehle
  (`K` = CONVERSE).

### `Testplan.md`
- **T47**: Korrekturvermerk — `MI` ist MFILTER, der Button hat nie die
  Mailbox angesprochen
- **T116 (MI)**: FAIL-Befund als Ergebnis eintragen (`MI` = MFILTER
  belegt)
- **T115 (MailDrop)**: Teilergebnis 22.09.2026 (Prompt, `H`, `B`),
  Wiederholung nach P21 mit der neuen Folge

### `Backlog.md`
- MailDrop-Protokollschicht: hängt an der Wiederholung von T115
- Host-Mode-Zugang zur Mailbox (Handbuch nennt Host-Mode-Befehle für
  `B` und `E`, im Scan unleserlich) — eigene Messung später

**Commit:** `Docs: MI is MFILTER, MailDrop facts, SIAM output is asynchronous`

---

## Definition of Done

- `python -m pytest` grün, Sicherheitstest aus P21.4 eingeschlossen
- `--dry-run maildrop` zeigt `normalize()` und die neue Folge
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"
- Danach vom Operator: `maildrop` mit der neuen Folge, komplette Logdatei
  an den Chat