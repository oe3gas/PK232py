# Claude Code Prompt — P46: Recovery als Notfall-Verbindung, TNC-Aktionen nur im Menü

> Ablage: `docs/P46_Recovery_Emergency_Connect_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher `CLAUDE.md`, `SERIAL_CONNECTION_STATE_MACHINE.md`,
> `docs/P43_TNC_State_Detection_Spec.md`,
> `docs/P45_Recovery_Feedback_Spec.md` lesen.

---

## Teil A — Der Fehler: Recovery besitzt den Lesepfad nicht

### Befund (25.09.2026, Screenshot)

Im RX-Fenster steht vor der Fehlermeldung:

```
␁␁OGG␁␁␁OHONO[SYS] Recovery did not reach the TNC.
```

Das sind die **eigenen Recovery-Frames** als Text: `SOH SOH $4F 'G' 'G'
ETB` ergibt `␁␁OGG␁` (`$4F` ist das Zeichen `O`). Diese Bytes wurden also
empfangen — aber sie landeten im **Terminal**, nicht bei der
Erkennungskette.

**Ursache:** Der `ReaderThread` läuft während der Recovery weiter und
nimmt die Antwortbytes entgegen, während die Kette parallel auf eigene
Lesevorgänge wartet und leer ausgeht. Daher „did not reach the TNC",
obwohl Daten flossen.

Der Init macht es richtig — dort steht im Log `ReaderThread stopped`,
bevor der Wakeup beginnt.

### A.1 Recovery übernimmt den Lesepfad

`SerialManager.recovery()` verfährt wie `init_tnc()`:

1. `ReaderThread` anhalten, Eingangspuffer leeren
2. Sequenz senden und die Erkennungskette fahren — **mit direktem
   Lesen**, wie im Init
3. `ReaderThread` wieder starten

Prüfen, ob der Einstieg in die Erkennungskette dafür bereits eine
gemeinsame Funktion hat; falls nicht, **eine** schaffen, die Init und
Recovery benutzen. Zwei Fassungen derselben Kette sind genau das Muster,
das in diesem Projekt schon mehrfach auseinandergelaufen ist.

### A.2 Keine Rohframes im Terminal

Empfangene Bytes, die zur Erkennung gehören, gehören **nicht** ins
RX-Fenster. Solange die Recovery läuft, erscheint dort nur:

```
[SYS] Recovery: sending recovery frames …
[SYS] Recovery: <Ergebnis>
```

Die Rohbytes stehen im Log (Hex, `DEBUG`), wie in P44 Teil C.2 festgelegt.

**Commits:**
```
SerialManager: recovery takes over the read path like init does
Verbose terminal: no raw detection bytes in the RX window
```

---

## Teil B — Recovery wird zur Notfall-Verbindung

Der Menüpunkt heißt künftig sinngemäß **„Emergency Reconnect (Host Mode
Recovery)"** und tut Folgendes, unabhängig davon, ob eine Verbindung
steht:

1. Port öffnen, falls er nicht offen ist (Port und Baudrate aus der
   Konfiguration)
2. Lesepfad übernehmen (Teil A)
3. den TNC auf allen bekannten Wegen ansprechen — die Kette aus P43/P44:
   `*` → `CR` → HPOLL-Frame → Rückholsequenz
4. bei Erfolg den TNC in den **verbose-Modus** zurückholen und melden:
   `Connection recovered — TNC is at the command prompt (verbose mode).`
5. bei Misserfolg: die bekannte Meldung mit Port, Baudrate und beiden
   möglichen Ursachen
6. Endzustand bei Erfolg: `verbose_confirmed` gesetzt, Anwendung im
   Zustand „verbose verbunden" — von dort laufen Parameter-Upload und
   Host-Mode-Eintritt über die bestehenden Wege

Der Punkt ist **immer** bedienbar: ohne Verbindung, im Fehlerzustand, im
Host Mode. Er ist der Ausweg, also darf ihn kein Zustand sperren.

**Commit:** `Recovery: emergency reconnect that works from any state`

---

## Teil C — TNC-Aktionen nur noch im TNC-Menü

Die Leiste unter dem Menü enthält `Connect`, `Disconnect`, `Host Mode`,
`Recovery` — und **„Connect" ist doppelt belegt**: einmal die serielle
Verbindung zum TNC, einmal die AX.25-Verbindung zur Gegenstation. In der
Packet-Maske stehen beide Bedeutungen gleichzeitig auf dem Schirm, in
PACTOR und AMTOR ebenso.

### C.1 Leiste aufräumen

Aus der Leiste **entfernen**: `Connect`, `Disconnect`, `Host Mode`,
`Recovery`.

Dort **bleiben**: Betriebsart-Auswahl, `TNC-Firmware`, die
Zustandsanzeige rechts (`VERBOSE MODE` / `HOST MODE` / `ERROR` /
`CONNECTING`).

### C.2 TNC-Menü

Die vorhandenen Einträge behalten ihre klaren Bezeichnungen und bekommen
den Recovery-Punkt dazu:

```
Connect + Enter Terminal Mode…        Ctrl+T
Connect + Enter Host Mode…            Ctrl+M
Leave Host Mode + Return to Terminal  Ctrl+L
Disconnect + Close Serial Port        Ctrl+D
---
Emergency Reconnect (Host Mode Recovery)   Ctrl+R
---
MailDrop…
```

**Achtung Tastenkonflikt:** `Ctrl+D` ist im TNC-Menü mit „Disconnect +
Close Serial Port" belegt und seit P42 zusätzlich mit „Disconnect des
gewählten Kanals" in der Packet-Maske. Das ist genau die Verwechslung,
die dieses Paket beseitigen soll. Vorschlag: der Kanal-Disconnect in der
Packet-Maske wird auf **`Ctrl+K`** gelegt (oder einen anderen freien
Kurzbefehl); im Kontextmenü des Chips steht er ohnehin. CC prüft die
tatsächlich belegten Kurzbefehle und schlägt im Commit-Text vor, was frei
ist.

### C.3 Konsequenzen prüfen

Alle Stellen suchen, die auf die entfernten Knöpfe verweisen
(`Testplan.md`, Tests, Doku, Tooltips) und umschreiben — **nicht**
löschen: die Handlungen gibt es weiterhin, nur an anderer Stelle.

**Commits:**
```
MainWindow: TNC actions live in the TNC menu only
Packet screen: channel disconnect shortcut no longer collides with the TNC menu
Docs: TNC connect and station connect are different things
```

---

## Teil D — Tests

- Recovery bei laufendem `ReaderThread`: die Antwortbytes erreichen die
  Kette, **nicht** das RX-Fenster
- Recovery ohne offenen Port: Port wird geöffnet, Kette läuft
- Recovery im Fehlerzustand: Menüpunkt ist bedienbar
- Erfolgsfall: `verbose_confirmed` gesetzt, Meldung „Connection
  recovered"
- Misserfolg: Meldung nennt Port und Baudrate
- Leiste enthält keine TNC-Knöpfe mehr; die Menüeinträge lösen dieselben
  Abläufe aus wie zuvor die Knöpfe
- der Kanal-Disconnect-Kurzbefehl kollidiert nicht mit dem TNC-Menü

**Commit:** `Tests: emergency reconnect and menu-only TNC actions`

---

## Teil E — Dokumentation

- `CLAUDE.md`:
  - **Jede Erkennung braucht den Lesepfad exklusiv.** Läuft der
    `ReaderThread` weiter, landen die Antworten im Terminal und die
    Erkennung sieht nichts — beobachtet 25.09.2026 an der Recovery
  - **„Connect" ist zweideutig**: TNC-Verbindung im Menü,
    Stationsverbindung in der Betriebsart-Maske. Neue Bedienelemente
    dürfen den Begriff nicht wieder vermischen
- `SERIAL_CONNECTION_STATE_MACHINE.md`: Recovery als Notfall-Verbindung
  beschreiben, mit dem Endzustand verbose
- `Testplan.md`: Fälle auf die Menüführung umschreiben; neuer Fall —
  Recovery aus dem Fehlerzustand heraus

**Commit:** `Docs: recovery owns the read path, menu-only TNC actions`

---

## Definition of Done

- `.venv\Scripts\python.exe -m pytest` grün
- Im RX-Fenster erscheinen keine Rohframes mehr
- Recovery holt einen im Host Mode abgewürgten TNC zurück und meldet es
- Die Leiste enthält keine TNC-Knöpfe mehr
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"
- Danach vom Operator: Anwendung im Host Mode abwürgen, starten,
  `Emergency Reconnect` — erwartet wird „Connection recovered"