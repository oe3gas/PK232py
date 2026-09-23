# Claude Code Prompt — P31: Prompt-Variante und vollständiger Rückweg

> Ablage: `docs/P31_Prompt_Variant_Recovery_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher `CLAUDE.md`, `Backlog.md`, `Testplan.md` lesen.
> Fixture: `hw_logs/20260923_184302_maildrop_session.log`.

---

## Befunde aus dem ersten Sitzungslauf (23.09.2026, 18:43)

Erfolgreich: Wakeup, Host-Mode-Eintritt, Host-Mode-Austritt durch die
Sitzung, `Ctrl-C`, `MDCHECK`. Die Portübergaben sind im Protokoll
lückenlos nachvollziehbar — P30 hat seinen Zweck erfüllt.

### 1. Der Mailbox-Prompt kommt in **eckigen** Klammern

```
MDCHECK\r\n[AEA PK-232M]  18340 free  (B,E,K,L,R,S) >\r\n
```

Alle früheren Messungen (22.09., drei Runden) zeigen im Hex-Dump
eindeutig die **runde** Form `28 41 45 41 … 29` = `(AEA PK-232M)`. Das
STABO-Handbuch zeigt die eckige. Beide Formen sind damit belegt.

**Ursache unbekannt.** Der Unterschied zum Vortag: der TNC hing fest und
wurde zurückgesetzt. Ob ein Parameter, ein Firmware-Codepfad oder der
Reset dahintersteckt, ist offen — **nicht raten**, sondern beide Formen
verarbeiten und beobachten.

### 2. Der Rückweg endet nach `B`

```
[18:43:08] send: not in Host Mode      <- Prüfstand fragt HPOLL zu früh
[18:43:10] TX (2 B): 42 0d             <- B
[18:43:10] no HPOLL response -- Host Mode state unclear
```

Schritt 5 des in P27.2 festgelegten Rückwegs („Host Mode betreten") wurde
nie ausgeführt. Der TNC blieb im verbose-Modus zurück.

### 3. Der Prüfstand prüft zu früh

Die HPOLL-Kontrolle lief, bevor der Rückweg abgeschlossen war. Die
Meldung „Host Mode state unclear" ist dadurch selbst erzeugt.

---

## P31.1 — `src/pk232py/maildrop/protocol.py`: beide Prompt-Formen

`find_prompt()` erkennt

```
(AEA PK-232M)  18536 free  (B,E,K,L,R,S) >
[AEA PK-232M]  18340 free  (B,E,K,L,R,S) >
```

- Klammerpaar rund **oder** eckig, Gerätename tolerant (`PK-232M`,
  `PK-232MBX`, `PK-232`)
- der Befehlssatz in der zweiten Klammer bleibt rund — so in **beiden**
  Messungen
- mehrfache Leerzeichen nicht fest verdrahten
- welche Form erkannt wurde, in `PromptInfo` mitführen
  (`bracket: str`), damit ein späterer Lauf zeigen kann, wann die Form
  wechselt

Tests mit **beiden** echten Zeichenfolgen aus den Mitschnitten, dazu
`You have mail.` davor.

**Commit:** `MailDrop protocol: accept round and square prompt brackets`

---

## P31.2 — `src/pk232py/maildrop/session.py`: Rückweg zu Ende fahren

Der Rückweg (P27.2) hat fünf Schritte; Schritt 5 fehlt in der Umsetzung.

```
1. /EX          (falls Texteingabe offen sein könnte)
2. B
3. Ctrl-C + CR
4. auf cmd: prüfen
5. Host Mode betreten   <-- fehlt
6. bestätigen           <-- neu: HPOLL-Antwort abwarten
```

- Schritt 5 über den vorhandenen `SerialManager`-Weg, **nicht** nachbauen
- Schritt 6: nach dem Eintritt bestätigen, dass der Host Mode läuft
  (vorhandene Prüfung verwenden). Erst danach `CLOSED` melden
- scheitert 4, 5 oder 6: Zustand `FAILED`, und `failed()` nennt den
  Handgriff für den Bediener („TNC steht im verbose-Modus, Anwendung neu
  verbinden" bzw. „TNC aus- und einschalten")
- **kein** `CLOSED` ohne bestätigten Host Mode — die Regel aus P15:
  kein gemeldeter Erfolg ohne Beleg

Test mit der Attrappe: Rückweg nach fehlgeschlagenem `open()` fährt alle
sechs Schritte; bleibt die Bestätigung aus, ist der Endzustand `FAILED`
und **nicht** `CLOSED`.

**Commit:** `MailDrop session: recovery re-enters and confirms Host Mode`

---

## P31.3 — `tools/hw_check.py`: erst der Rückweg, dann die Kontrolle

- die HPOLL-Kontrolle des Prüfstands läuft erst, **nachdem** die Sitzung
  `CLOSED` oder `FAILED` gemeldet hat
- meldet die Sitzung `FAILED`, wird die Kontrolle übersprungen und der
  Grund der Sitzung zitiert, statt eine eigene Diagnose zu erfinden
- in der Zusammenfassung sichtbar machen, welche Prompt-Form gesehen wurde

**Commit:** `Tools: maildrop_session checks Host Mode after recovery finishes`

---

## P31.4 — Dokumentation

### `CLAUDE.md`
- MailDrop-Abschnitt: **beide** Prompt-Formen sind belegt, mit Datum und
  Rohzeile; Ursache des Wechsels offen
- Hardwareabschnitt neu: **Der PK-232 kann sich aufhängen** und reagiert
  dann auf nichts mehr, auch nicht auf `*`. Triage: zuerst mit einem
  Terminalprogramm (PuTTY) prüfen, ob das Gerät überhaupt antwortet,
  bevor die Software verdächtigt wird; Abhilfe ist Aus- und Einschalten.
  Beobachtet am 23.09.2026 — der Wakeup-Fehlschlag von 18:01 ging darauf
  zurück, nicht auf die Software

### `Backlog.md`
- offener Punkt: wann wechselt der Prompt zwischen runder und eckiger
  Form? Bei künftigen Läufen die in `PromptInfo` mitgeführte Form
  protokollieren und Auffälligkeiten sammeln
- P29 (CR-Rückfall im Wakeup) bleibt sinnvoll, ist aber **nicht** die
  Ursache der Fehlschläge vom 23.09. — Priorität entsprechend senken und
  das im Eintrag vermerken

### `Testplan.md`
- T119: Teilergebnis 23.09.2026 — Schritte bis `MDCHECK` bestätigt,
  Abbruch an der Prompt-Erkennung, Wiederholung nach P31

**Commit:** `Docs: prompt bracket variants, TNC deadlock triage`

---

## Definition of Done

- `.venv\Scripts\python.exe -m pytest` grün
- Der Prompt-Test mit der eckigen Form ist ohne P31.1 rot — gegengeprüft
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"
- Danach vom Operator: `maildrop_session` erneut, Logdatei an den Chat