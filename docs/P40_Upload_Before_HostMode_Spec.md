# Claude Code Prompt — P40: Parameter-Upload zurück in den verbose-Modus

> Ablage: `docs/P40_Upload_Before_HostMode_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher `CLAUDE.md`, `SERIAL_CONNECTION_STATE_MACHINE.md`, `Backlog.md`
> lesen.

---

## Befund (24.09.2026, 21:27)

Beim Verbindungsaufbau protokolliert der Uploader für **jeden** Parameter:

```
21:27:29,483  TX: MYCALL OE3GAS
21:27:34,491  WARNING: no cmd: after b'MYCALL OE3GAS', continuing
21:27:34,492  TX: PACLEN 64
21:27:39,509  WARNING: no cmd: after b'PACLEN 64', continuing
```

Exakt 5,0 s je Befehl — das ist die Zeitgrenze, nicht die Übertragung.
Bei 68 Befehlen rund **sechs Minuten**.

**Ursache:** Der Upload läuft, während der TNC im **Host Mode** steht.
Dort gibt es keinen `cmd:`-Prompt; der TNC erwartet SOH-gerahmte Frames.
Unverpackter Text wird nicht als Befehl ausgeführt.

**Folge, schwerwiegender als die Wartezeit:** Die Parameter kommen
höchstwahrscheinlich **gar nicht an**. Zum Vergleich derselbe Upload im
verbose-Modus (T103, 22.09.): jeder Befehl in unter einer Sekunde mit
`MYcall was PK232 / now OE3GAS` quittiert, alle 68 ohne Fehler.

Die Alternative — alle Parameter als `$4F`-Befehlsframes mit
Zwei-Buchstaben-Kürzeln — scheidet aus: Für die meisten Befehle sind die
Kürzel unbelegt, und geratene Kürzel haben in diesem Projekt bereits
`PA`, `PS` und `MI` verursacht.

---

## P40.1 — Reihenfolge wiederherstellen

Im Verbindungsaufbau: **Parameter-Upload vollständig im verbose-Modus,
danach Host-Mode-Eintritt.**

- die Stelle finden, an der die Reihenfolge gedreht wurde (Git-Historie),
  und im Commit-Text nennen, seit wann und warum
- `SERIAL_CONNECTION_STATE_MACHINE.md` gegenlesen: beschreibt das Dokument
  die verbose-Reihenfolge, ist der Code von ihr abgewichen — dann ist das
  Dokument die Vorgabe und der Code folgt ihm; beschreibt es die
  Host-Mode-Reihenfolge, wird das Dokument korrigiert
- der Uploader läuft damit wieder mit seinen ursprünglichen Zeitgrenzen;
  der Gesamtaufbau dauert wieder rund eine Minute statt sechs

**Commit:** `Connection: upload parameters in verbose mode before entering Host Mode`

---

## P40.2 — Schutz gegen Wiederholung

`ParamsUploader` verweigert den verbose-Upload, wenn der `SerialManager`
den Host Mode als aktiv meldet:

- Prüfung **vor** dem ersten Befehl, nicht je Befehl
- bei aktivem Host Mode: `ERROR`-Logzeile
  „refusing to upload parameters in Host Mode — verbose text is not
  executed there" und Abbruch des Uploads mit klarem Rückgabewert; **kein**
  stilles Durchlaufen
- Unit-Test: Uploader mit einem Manager im Host Mode → kein einziges Byte
  gesendet

Damit kann dieselbe Umstellung nicht noch einmal sechs Minuten lang
wirkungslos laufen.

**Commit:** `Params uploader: refuse to run while the TNC is in Host Mode`

---

## P40.3 — Nachweis, dass die Parameter angekommen sind

Nach dem Upload, noch in verbose, drei Stichproben abfragen und mit der
Konfiguration vergleichen — Kandidaten, die in den Messungen zuverlässig
antworten: `MYCALL`, `PACLEN`, `MAXFRAME`.

- Übereinstimmung: eine `INFO`-Zeile „parameter upload verified (3/3)"
- Abweichung: `WARNING` mit Soll und Ist je Parameter, Verbindungsaufbau
  läuft weiter
- keine Antwort: `WARNING`, ebenfalls weiter

Die Stichprobe kostet unter einer Sekunde und hätte den jetzigen Fehler
sofort sichtbar gemacht.

**Commit:** `Connection: verify a sample of uploaded parameters`

---

## P40.4 — Zeitgrenze und Meldung des Uploaders

- Die Meldung „no cmd: after …, continuing" ist zu harmlos formuliert für
  das, was sie bedeutet: der Befehl wurde vermutlich nicht ausgeführt.
  Auf `WARNING` belassen, aber den Text schärfen:
  „no cmd: after <CMD> — command probably NOT executed"
- Bleiben **mehr als drei** Befehle in Folge ohne Antwort, den Upload
  abbrechen statt 65-mal fünf Sekunden zu warten; `ERROR` mit dem Hinweis,
  den TNC-Zustand zu prüfen

**Commit:** `Params uploader: clearer warning and abort after repeated silence`

---

## P40.5 — Dokumentation

- `CLAUDE.md`, Fallstricke: **Im Host Mode gibt es keinen `cmd:`-Prompt.**
  Verbose-Text wird dort nicht ausgeführt. Parameter werden ausschließlich
  vor dem Host-Mode-Eintritt hochgeladen. Beobachtet am 24.09.2026: 68
  Befehle, je 5 s Zeitgrenze, keiner ausgeführt
- `SERIAL_CONNECTION_STATE_MACHINE.md`: Reihenfolge eindeutig festhalten
- `Testplan.md`: Fall — Verbindungsaufbau dauert unter einer Minute, im
  Log keine „no cmd:"-Warnung, Stichprobe bestätigt drei Parameter

**Commit:** `Docs: no cmd: prompt in Host Mode, upload order`

---

## Definition of Done

- `.venv\Scripts\python.exe -m pytest` grün
- Test belegt: Uploader sendet im Host Mode nichts
- Ein realer Verbindungsaufbau zeigt die „verified (3/3)"-Zeile und keine
  „no cmd:"-Warnung
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"