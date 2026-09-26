# Claude Code Prompt — P53: Ctrl-C in die Erkennungskette, Prüfung besitzt den Lesepfad

> Ablage: `docs/P53_CtrlC_And_Verify_Readpath_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Belege: Konsolenmitschnitt und Screenshot vom 26.09.2026, 13:13–13:16.

---

## Teil A — Die Prüfung liest, während der ReaderThread schon läuft

### Befund
Im Terminal ist die Antwort sichtbar:

```
cmd:MYCALL
MYcall    OE3GAS
cmd:[SYS] no answer verifying MYCALL (expected 'OE3GAS')
```

Der TNC hat also geantwortet. Im Log startet der `ReaderThread` direkt
nach `Init complete` (13:13:48,871), und der Upload samt Prüfung läuft
**danach**. Die Prüfung liest direkt vom Port, der `ReaderThread` nimmt
die Bytes für das Terminal — die Prüfung geht leer aus.

Dieselbe Fehlerklasse wie bei der Recovery in P46: **wer liest, muss den
Lesepfad besitzen.**

### A.1 Ein Besitzer je Phase
Upload **und** Prüfung gehören noch in die Init-Phase, solange der
Lesepfad der Init-Logik gehört. Der `ReaderThread` startet erst, wenn
beides abgeschlossen ist.

Prüfen, wo `ReaderThread` heute gestartet wird und ob der Uploader von
dort aus aufgerufen wird; die Reihenfolge entsprechend umstellen.

Geht das nicht ohne größeren Umbau (etwa weil der Uploader aus der
UI-Schicht angestoßen wird), dann die Alternative: Upload und Prüfung
übernehmen den Lesepfad über die vorhandene Funktion aus P46
(`_take_over_read_path()`) und geben ihn danach zurück. **Nicht beides**
— eine Lösung, begründet im Commit-Text.

### A.2 Sichtbarkeit bleibt
Die Zeilen, die heute im Terminal erscheinen (`cmd:MYCALL`,
`MYcall OE3GAS`), sollen weiterhin sichtbar sein. Wenn die Prüfung den
Lesepfad besitzt, spiegelt sie das Gelesene ins Terminal, so wie der Init
sein Banner spiegelt (P49 Teil B).

**Commit:** `Params uploader: verification owns the read path`

---

## Teil B — `Ctrl-C` fehlt in der Erkennungskette

### Befund
```
step 1 TX: 2a          -> 2a 5c 0d 0a      (Echo, volle 1,5 s, kein cmd:)
step 2 TX: 0d          -> 0d 0a            (Echo, kein cmd:)
step 3: Echo erkannt, kein Host Mode        (P52 greift korrekt)
step 3b: Rückholsequenz  -> nur Echo
-> Abbruch
```

Der TNC echot alles und liefert nie einen Prompt: Das ist der
**Converse-Modus**. Dort wird jedes Zeichen echot und in den Sendepuffer
gelegt, ein Prompt erscheint nicht.

**Warum er dort steht:** Vor dem Trennen war die Betriebsart **Baudot
RTTY** aktiv. Nach `HOST OFF` kehrt der TNC in diese Betriebsart zurück,
nicht in den Befehlsmodus.

**Der Ausweg ist ein Byte:** `Ctrl-C` (`$03`), das COMMAND-Zeichen.
`normalize()` im Prüfstand macht das seit P21 und kommt damit zuverlässig
zum `cmd:`-Prompt.

### B.1 Neue Stufe
Die Kette bekommt einen Schritt **zwischen** dem heutigen Schritt 1 und
Schritt 3:

| # | Reiz | Antwort | Schluss |
|---|---|---|---|
| 1 | `*` | Banner oder `cmd:` | verbose, frisch eingeschaltet |
| 2 | `CR` | `cmd:` | verbose am Prompt |
| **2b** | **`$03` + `CR`** | **`cmd:`** | **verbose, war im Converse-Modus** |
| 3 | HPOLL-Frame | echter `$4F`-Frame (6 Bytes, kein Echo) | Host Mode |
| 3b | Rückholsequenz | `cmd:` nach `CR` | war festgefahren |
| 4 | — | nichts | kein PK-232 erreichbar |

- `$03` ist das Standard-COMMAND-Zeichen; ist es in der Konfiguration
  abweichend gesetzt, den konfigurierten Wert verwenden
- Logzeile: `step 2b - COMMAND char (Ctrl-C) - TNC may be in converse mode`

### B.2 Nach dem Verlassen des Host Mode
Verlässt die Anwendung den Host Mode (`Ctrl+L`, Trennen), kehrt der TNC in
die zuletzt aktive Betriebsart zurück — bei Baudot, AMTOR, PACTOR also in
deren Converse-Zustand. Damit das Terminal danach unmittelbar benutzbar
ist, **nach dem Host-Mode-Austritt `Ctrl-C` senden** und auf `cmd:`
prüfen; Ergebnis im Log.

Das erspart der nächsten Verbindung Stufe 2b — und dem Bediener ein
Terminal, das nur echot.

**Commits:**
```
SerialManager: Ctrl-C step for a TNC in converse mode
Connection: return to the command prompt after leaving Host Mode
```

---

## Teil C — Tests

Mit den echten Byte-Folgen aus dem Mitschnitt:

- `*` → `2a 5c 0d 0a`, `CR` → `0d 0a`, `$03`+`CR` → `…cmd:` → Erfolg über
  Stufe 2b, **kein** HPOLL-Frame gesendet
- `*` → Banner mit `cmd:` → Stufe 1, weder `CR` noch `$03` gesendet
- Host Mode: echte `$4F`-Antwort (6 Bytes) → Stufe 3
- Echo der eigenen Abfrage (5 Bytes) → **kein** Host Mode (P52 bleibt)
- Prüfung: Antwort `MYcall    OE3GAS` erreicht die Prüfung, nicht nur das
  Terminal → `verified (3/3)`
- abweichender COMMAND-Zeichen-Wert aus der Konfiguration wird verwendet

**Commit:** `Tests: converse-mode detection and verification read path`

---

## Teil D — Dokumentation

`CLAUDE.md`, Fallstricke:

- **Nach `HOST OFF` steht der TNC in der zuletzt aktiven Betriebsart**,
  nicht im Befehlsmodus. Bei Baudot, AMTOR und PACTOR bedeutet das
  Converse: Der TNC echot jedes Zeichen und gibt **keinen** Prompt.
  `Ctrl-C` (COMMAND-Zeichen) holt ihn zurück. Belegt am 26.09.2026
- **Echo ohne Prompt heißt Converse, nicht „Gerät hängt"** — die frühere
  Einschätzung („TNC festgefahren") war in diesen Fällen falsch
- der Hinweis aus P46 („wer liest, muss den Lesepfad besitzen") gilt auch
  für den Uploader und seine Prüfung

`SERIAL_CONNECTION_STATE_MACHINE.md`: Stufe 2b in die Tabelle, und den
`Ctrl-C`-Schritt nach dem Host-Mode-Austritt.

`Testplan.md`: Fall — im Host Mode mit aktiver Baudot-Betriebsart
trennen, dann neu verbinden; erwartet wird Erfolg über Stufe 2b ohne
Fehlermeldung.

**Commit:** `Docs: converse mode after leaving Host Mode`

---

## Definition of Done

- `.venv\Scripts\python.exe -m pytest` grün
- Der Stufe-2b-Test ist ohne den Fix rot — gegengeprüft
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"
- Danach vom Operator: Block 1 Schritt 4 bis 7 erneut (Host Mode, zurück,
  trennen, neu verbinden) — erwartet wird `verified (3/3)` und kein
  Fehlerdialog