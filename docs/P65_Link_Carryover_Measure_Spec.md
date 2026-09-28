# Claude Code Prompt — P65: Messpaket — Verbindung und Betriebsart beim Wechsel verbose ↔ Host Mode (Packet)

> Ablage: `docs/P65_Link_Carryover_Measure_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Grundlage: `main` @ `c986785`, Backlog-Eintrag P64.
> **Nur Messung** (hw_check-Regel 6). Die Umsetzung (Verbindungstabelle,
> Betriebsart mitnehmen) folgt als P66 und stützt sich nur auf diese Befunde.
> APRS (P63) ruht auf Wunsch des Betreibers.

---

## Befund

### B.1 Betreiberbeobachtung (P64)
Verbose, VHF Packet, Verbindung zu einer BBS (TinyBox) → `Enter Host Mode`
(Ctrl+H) → App zeigt Baudot RTTY statt VHF Packet und erkennt die
Verbindung nicht. Zurück in verbose ging die BBS-Sitzung normal weiter:
**die AX.25-Verbindung übersteht den Wechsel** (Betreiber, 27.09.2026;
Gerät bei diesem Lauf festhalten).

### B.2 Das TRM beschreibt zwei Abfragen, die der Code nie benutzt

`CLAUDE.md` („Channel model", 2026-09-20) behauptet: *„There is no CSTATUS
poll in Host Mode — the PK-232 never tells the host 'channel N is connected
to X' on demand."* Das ist **nicht gemessen** und widerspricht dem TRM:

- **TRM 4.3.3 Link Status Request:** `SOH $4x C O ETB` fragt den Zustand von
  Kanal x ab. Antwort `SOH $4x C O a b c d e <path> ETB` mit
  `a` = Link-Zustand − 1 (ODER `$30`), `b` = AX.25 v2, `c` = unbestätigte
  Pakete, `d` = Retries, `e` = CONPERM, danach Partner und Digis.
  `HostModeProtocol.cmd_link_status()` baut diesen Frame bereits
  (`comm/hostmode.py:312`), wird aber **nirgends** aufgerufen.
- **TRM 4.3.2 OPMODE:** `SOH $4F O P ETB` liefert die aktuelle Betriebsart
  (`O P P A` = Packet, `O P B A x` = Baudot, `O P A C v x` = AMTOR ARQ …).
  Damit lässt sich nach jedem Wechsel feststellen, in welcher Betriebsart der
  TNC tatsächlich steht.

Beides ist genau das, was P64 für den Abgleich der Verbindungstabelle
braucht. Ungemessen, also: messen.

### B.3 Antworten `$40–$4E` werden heute falsch einsortiert
Backlog „`_make_host_frame()` misclassifies LINK_STATUS ($40–$4E) as
CMD_RESP — open": Antworten auf die Link-Status-Abfrage landen im Parser
als `CMD_RESP`. Das Messwerkzeug muss daher die **rohen Bytes** loggen und
darf sich nicht auf die Klassifikation verlassen.

### B.4 Die App sendet beim Host-Eintritt Moduswechsel-Frames
`_update_host_mode_ui(True)` aktiviert ohne aktiven Modus Baudot RTTY und
sendet damit dessen Aktivierungsframes — bei bestehender Packet-Verbindung.
Dass die Verbindung das überstand (B.1), ist bemerkenswert, aber ob der TNC
danach in Baudot stand, wissen wir nicht. P66 wird stattdessen die
Packet-Frames senden (oder gar keine) — ob das eine laufende Verbindung
stört, muss gemessen sein.

### B.5 Zugehörigkeit zu Betriebsarten
PACTOR und AMTOR (ebenfalls Modi mit Verbindung) folgen in einem eigenen
Paket, sobald Packet gelöst ist. P65 misst nur Packet, erfasst aber OPMODE
so, dass dieselbe Abfrage später dort wiederverwendbar ist.

---

## Teil A — `hw_check.py link_carry` (Richtung verbose → Host → verbose)

Neuer Unterbefehl. Gegenstation nach Wahl des Betreibers (die TinyBox wie
in B.1, oder Direwolf + QtTermTCP über AGW wie in P62a Teil D). Das
Programm fragt vorab Gegenstation und Gerät (A/B/C) ab und loggt beides.

Ablauf, jeder Schritt mit wörtlichem Log aller Bytes/Zeilen:

1. **A.1 Vorbereitung verbose:** `normalize()`, dann `VHF`/`HBAUD` prüfen
   und bei Bedarf anbieten wie in P62a C.1 (gleiche Hilfsfunktion
   wiederverwenden, nicht kopieren).
2. **A.2 Verbindung aufbauen lassen:** Anweisung an den Betreiber:
   `Connect to the counterpart now from THIS program's prompt:` — das
   Programm fragt das Zielrufzeichen ab und sendet verbose
   `CONNECT <call>`; danach bis 30 s auf `*** CONNECTED` warten und die
   Zeile wörtlich loggen. (Kein Terminal nebenbei — der Port gehört
   `hw_check`.)
3. **A.3 Verbose-Basislinie:** `OPMODE`, `CSTATUS`, `CONNECT` (ohne
   Argument, liefert „Link state is: …"). Antworten wörtlich.
4. **A.4 Host Mode betreten** (`session.enter_host_mode()`), dann **3 s
   alles aufzeichnen, ohne etwas zu senden**: meldet der TNC von sich aus
   etwas zur bestehenden Verbindung?
5. **A.5 OPMODE im Host Mode:** `query_host(b"OP")`, Rohbytes loggen.
6. **A.6 Link-Status aller Kanäle:** für Kanal 0–9 je
   `HostModeProtocol.cmd_link_status(ch)` senden (bestehender Bauer),
   Antwort bis 1 s je Kanal **roh** loggen: CTL-Byte, alle Datenbytes hex
   und als Text. Eine **reine Funktion**
   `decode_link_status(ctl: int, data: bytes) -> dict` wertet nach TRM
   4.3.3 aus (Kanal, Zustand, v2, unbestätigt, Retries, CONPERM, Pfad) und
   meldet `unparsed` statt zu raten, wenn das Format abweicht.
7. **A.7 Welcher Kanal trägt die Verbindung?** `confirm_tx()`: auf dem Kanal,
   den A.6 als verbunden meldet (sonst Kanal 0), einen einzelnen `\r` als
   Datenframe senden. Eine BBS antwortet mit ihrem Prompt, Direwolf/QtTermTCP
   zeigt die Leerzeile — der Betreiber tippt dort eine kurze Antwort.
   10 s aufzeichnen: auf welchem `$3x` kommt die Antwort?
8. **A.8 Moduswechsel-Frames bei bestehender Verbindung:**
   `confirm`-Frage (kein Senden auf HF, aber Einstellungsänderung). Die
   Frames **aus `VHFPacketMode().get_activate_frames()` und
   `get_init_frames()`** senden — nicht kopieren, damit genau das gemessen
   wird, was die App senden würde. Je Frame die Quittung loggen. Danach
   A.5 und A.6 wiederholen: Verbindung noch da, Betriebsart Packet?
   Dann A.7 wiederholen: Datenverkehr läuft noch?
9. **A.9 Zurück nach verbose:** `session.exit_host_mode()`, dann A.3
   wiederholen (`OPMODE`, `CSTATUS`, `CONNECT`).
10. **A.10 Aufräumen:** Frage an den Betreiber: `Disconnect now? [Y/n]` →
    verbose `DISCONNECT`, auf `*** DISCONNECTED` warten, loggen.

Zusammenfassung am Ende (INFO je Schritt, PASS/FAIL nur wo eindeutig):
- `A.6` PASS, wenn `decode_link_status()` für genau einen Kanal „connected"
  mit dem erwarteten Partner liefert
- `A.8` PASS, wenn A.6/A.7 nach den Moduswechsel-Frames unverändert sind
- `A.9` PASS, wenn `CSTATUS`/`CONNECT` die Verbindung weiterhin zeigen

**Commit:** `hw_check: link_carry - verbose connect survives Host Mode, CO and OP queries`

---

## Teil B — `hw_check.py link_carry_host` (Richtung Host → verbose)

Spiegelbild: Verbindung **im Host Mode** aufbauen
(`HostModeProtocol.cmd_connect()` auf Kanal 1, wie die App es tut), auf die
`$5x`-Meldung `CONNECTED to` warten, dann A.5/A.6, dann Host Mode
verlassen und verbose `OPMODE`, `CSTATUS`, `CONNECT` abfragen. Frage: Auf
welchem Kanal steht die Verbindung in verbose, und ist sie dort der aktive
Kanal? Danach wieder Host Mode betreten und A.6 — ist sie noch auf Kanal 1?
Aufräumen mit Host-`DI` auf dem gemeldeten Kanal.

**Commit:** `hw_check: link_carry_host - Host Mode connect seen from verbose`

---

## Teil C — Tests (headless, zuerst rot)

`src/pk232py/tests/test_hw_check_link_carry.py` (neu):
- `decode_link_status()`: TRM-Beispiel aus 4.3.3 (Zustand `$34` → S05,
  Pfad `W6CUS-1 via K6LLK, WD6CMU-1`), freier Kanal, zu kurze Daten →
  `unparsed`, Kanal aus dem CTL-Nibble (`$43` → 3)
- Dry-Run beider Unterbefehle: kein Port, alle geplanten Befehle/Frames
  sichtbar; die A.8-Frames stammen nachweislich aus `VHFPacketMode`
  (Bytevergleich mit den Methoden, nicht mit einer Kopie)
- Der CO-Frame in A.6 stammt aus `HostModeProtocol.cmd_link_status()`

**Commit:** `Tests: hw_check link carry evaluation and dry-run`

---

## Teil D — Testplan und Doku

- `Testplan.md`: **T141** `link_carry`, **T142** `link_carry_host` (OPEN,
  je Gerät eine Ergebniszeile).
- `Backlog.md`, P64-Eintrag: Verweis auf P65/T141/T142; B.2 als neue
  Kandidaten (CO-Abfrage, OPMODE) nachtragen.
- `CLAUDE.md`, „Channel model": Die Aussage „no CSTATUS poll in Host Mode"
  **nicht** löschen, aber kennzeichnen: *„Unmeasured - TRM 4.3.3 documents
  a per-channel CO query; see P65/T141."* Erst nach T141 wird sie
  bestätigt oder ersetzt.
- `tools/README.md` / Modul-Docstring: zwei neue Unterbefehle, nicht in
  `all` (brauchen eine Gegenstation).

**Commits:**
```
Testplan: T141 T142 link carry-over
Backlog: P64 measurement via P65
Docs: CLAUDE.md channel model claim marked unmeasured
Docs: hw_check link carry subcommands
Docs: add P65 spec file
```

---

## Definition of Done

- neue Tests zuerst rot, volle Suite vor dem Push grün
- `--dry-run link_carry` und `--dry-run link_carry_host` laufen ohne Port
- Kein neuer Frame-Bauer: CO über `cmd_link_status()`/`cmd_connect()`,
  OP über `query_host()`, Moduswechsel-Frames aus `VHFPacketMode`
- Jede Aussendung hinter `confirm_tx()`
- **Push**, Meldung mit Hash; `.\Sources2Text.ps1`, „sources aktualisiert"