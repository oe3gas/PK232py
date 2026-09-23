# Claude Code Prompt — P30: Mitschnitt und Portbesitz im Sitzungs-Prüfstand

> Ablage: `docs/P30_Session_Harness_Logging_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher `CLAUDE.md` und `SERIAL_CONNECTION_STATE_MACHINE.md` lesen.

---

## Befund

`maildrop_session` scheitert am Wakeup, **auch direkt nach dem Einschalten
des TNC**. Der Operator sieht an den LEDs, dass das `*` ankommt und die
Autobaud-Erkennung greift (9600 Bd). Die Antwort erreicht die Software
trotzdem nicht.

Das Protokoll endet nach:

```
[18:01:42] Opened COM6 @ 9600 Bd
[18:01:50] ERROR: TNC did not respond to wakeup
```

Acht Sekunden ohne eine einzige Zeile darüber, **was gesendet und was
empfangen wurde**. Alle anderen Subcommands protokollieren jedes Byte in
beide Richtungen; der Prüfstand tut es nicht, weil die serielle Arbeit
dort im `SerialManager` steckt.

**Erster zu prüfender Verdacht — nicht als gesetzt behandeln, sondern
belegen:** `hw_check` öffnet den Port selbst (`Opened COM6 @ 9600 Bd`),
und anschließend soll `SerialManager` denselben Port öffnen. Unter Windows
ist ein COM-Port exklusiv. Hält der Prüfstand ihn weiter, schreibt der
eine Besitzer und der andere liest nichts — was genau zum Bild passt
(LEDs reagieren, Software sieht nichts).

---

## P30.1 — Portbesitz klären und protokollieren

In `maildrop_session`:

1. **Vor** dem Erzeugen des `SerialManager` protokollieren, ob der
   Prüfstand selbst einen Port offen hat, und ihn dann **schließen** —
   mit Logzeile („harness released COM6 before handing it to
   SerialManager")
2. Nach jedem Besitzerwechsel eine Zeile: wer hält den Port jetzt
   (`harness` / `SerialManager` / `hostmode subprocess`)
3. Schlägt `SerialManager` beim Öffnen fehl, die Ursache im Klartext
   melden („port busy — still held by the harness?") statt der
   allgemeinen Wakeup-Meldung
4. Prüfen, ob die übrigen Schritte des Prüfstands (Normalisierung,
   Testnachricht über den verbose-Weg) überhaupt einen eigenen Port
   brauchen. Wenn ja: **vollständig abschließen und schließen**, bevor
   der `SerialManager` übernimmt, und das im Log sichtbar machen

**Commit:** `Tools: maildrop_session logs and releases port ownership`

---

## P30.2 — Mitschnitt der Init-Phase

Der Prüfstand bekommt denselben Mitschnitt wie die übrigen Subcommands,
ohne dass der `SerialManager` dafür umgebaut wird:

- eine schlanke Hüllklasse um das `serial.Serial`-Objekt, die `write()`,
  `read()`, `in_waiting`, `reset_input_buffer()` und `close()`
  durchreicht und dabei jede Richtung mit Zeitstempel, Hex **und** Text
  protokolliert (Steuerzeichen sichtbar, wie in den anderen Subcommands)
- die Hülle wird **nur im Prüfstand** eingesetzt (Injektion beim Erzeugen
  des `SerialManager`, oder über den vorhandenen Weg, auf dem der Manager
  sein Portobjekt bekommt). Ist keine Injektion vorgesehen: **nicht**
  durch Monkeypatching erzwingen, sondern die kleinste nötige Öffnung im
  `SerialManager` schaffen (ein optionaler Parameter „port factory") und
  das im Commit-Text begründen
- zusätzlich das Logging von `pk232py.comm` auf `DEBUG` heben und in
  dieselbe Datei schreiben — die vorhandene Zeile
  `logger.debug("Wakeup response (%d B): %s", ...)` beantwortet die Frage
  vermutlich schon allein

Ziel: das Protokoll zeigt für die Init-Phase mindestens

```
>> hex=2A text=*            (wakeup)
<< hex=...                  (Banner? Echo? nichts?)
```

**Commit:** `Tools: byte-level log of the init phase in maildrop_session`

---

## P30.3 — Auswertung in der Zusammenfassung

Am Ende des Laufs eine kurze Einordnung, die dem Operator die Deutung
abnimmt:

| Beobachtung | Zusammenfassung |
|---|---|
| gar keine Bytes empfangen | „no data at all — port held elsewhere or wrong port" |
| nur das Echo `*` | „TNC already awake — needs CR (see P29)" |
| Banner ohne `cmd:` | „banner truncated — timeout too short" |
| `SOH` im Empfang | „TNC still in Host Mode" |

Die Zuordnung ist eine Hilfe, kein Urteil: die Rohbytes stehen weiter
darüber im Protokoll.

**Commit:** `Tools: maildrop_session summarises the init phase`

---

## P30.4 — Tests

- die Hüllklasse protokolliert jede Richtung und reicht Rückgabewerte
  unverändert durch
- die Einordnung aus P30.3 gegen vier erfundene, aber realistische
  Byte-Folgen (leer, nur Echo, Banner ohne Prompt, mit `SOH`)
- der Prüfstand schließt seinen eigenen Port, bevor der `SerialManager`
  erzeugt wird (gegen eine Attrappe geprüft)

**Commit:** `Tests: init phase logging wrapper and classification`

---

## Definition of Done

- `.venv\Scripts\python.exe -m pytest` grün
- `--dry-run maildrop_session` unverändert lauffähig
- Ein realer Lauf zeigt im Protokoll die gesendeten und empfangenen Bytes
  der Init-Phase
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"
- Danach vom Operator: `maildrop_session`, Logdatei an den Chat