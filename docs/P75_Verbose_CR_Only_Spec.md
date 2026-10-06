# Claude Code Prompt — P75: Verbose-Befehle nur mit `\r` abschließen, damit ILFPACK OFF die App nicht bricht

> Ablage: `docs/P75_Verbose_CR_Only_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Grundlage: `main` @ `9865e7f` (nach P85). Doku nach `docs/claude/`.
> **Teil 0 (Messung) zuerst**, Teil A–D erst nach T175.

---

## Befund

### B.1 Gemessen (T155, Gerät B, `20261001_202242_host_params_probe.log`)
Mit `ILFPACK OFF` beantwortet der TNC nach dem Verlassen des Host Mode den
**ersten** verbose Befehl richtig, jeden weiteren mit `?What?`:

```
>> PACLEN\r\n   << PACLen 128
>> USERS\r\n    << ?What?
>> HELP\r\n     << ?What?
```

Erklärung: Die App schließt Befehle mit `\r\n` ab. Bei `ILFPACK ON`
ignoriert der TNC das LF; bei `OFF` bleibt es stehen und wird zum ersten
Zeichen des nächsten Befehls (`<LF>USERS`).

### B.2 Heutiger Umgang
P72 setzt ILFPACK **nie live** („applied at the next initialisation"), damit
eine Änderung auf OFF die App nicht lahmlegt. Der Init-Upload setzt es aber
trotzdem — ein Betreiber mit `ILFPACK OFF` in der Konfiguration bricht sich
damit nach jedem Init die verbose Befehle.

### B.3 Wo `\r\n` als **Befehlsende** gesendet wird (statische Zählung)
`comm/params_uploader.py` (`_cmd`, `_bool`), `comm/param_applier.py`
(368, 375, 385), `comm/serial_manager.py` (`_CMD_AWLEN`, `_CMD_PARITY`,
`_CMD_8BITCONV`, `_CMD_RESTART`, 704, 757, 796, 827), alle
`verbose_command` in `modes/*.py`, `ui/main_window.py:2095` (`CONVERSE`),
`maildrop/protocol.py:194` (MailDrop-Befehle).

**Nicht** betroffen und **unverändert** zu lassen: Datenzeilen, die auf
die Luft gehen (RTTY-TX `main_window.py:3269/3401`, TX-Controller, Packet-
Senden), sowie Lesepfade (`read_until(... b"\r\n")`).

---

## Teil 0 — Messung: `hw_check.py eol_probe` (T175, nur PC 1, Gerät B und A)

Mit `operator_step()`, kein Senden auf der Luft:

1. verbose `ILFPACK ON` (Ausgangszustand), dann eine Folge von fünf Abfragen
   mit **nur `\r`**: `PACLEN`, `USERS`, `MAXFRAME`, `MYCALL`, `HELP` →
   jede Antwort roh loggen.
2. Dieselbe Folge mit `\r\n` (Gegenprobe, erwartet: alles richtig).
3. Host Mode betreten, `IL` per Host auf `N` setzen (Kürzel `IL`, T155),
   Abfrage roh, Host Mode verlassen.
4. Dieselbe Folge mit nur `\r` → **Kernfrage: alle fünf richtig?**
5. Dieselbe Folge mit `\r\n` → erwartet wie T155 (ab dem zweiten
   `?What?`).
6. Ein MailDrop-Befehl im Befehlsmodus mit nur `\r` (`MAILDROP`-Abfrage).
7. `CONVERSE` mit nur `\r`, dann COMMAND-Zeichen → `cmd:` erreicht?
8. Rückstellung: Host Mode, `IL Y`, verbose Kontrolle `ILFPACK ON`.

Ergebnis je Schritt `PASS`/`FAIL` mit Rohantworten. Zusätzlich: Setzt `IL`
per Host den Wert, den verbose `ILFPACK` anzeigt? (Freigabe für P72.)

**Commit:** `hw_check: eol_probe - CR-only verbose commands with ILFPACK ON and OFF`

---

## Teil A — Eine Stelle für das Befehlsende

- `comm/` bekommt **eine** Konstante bzw. Funktion, z. B.
  `verbose_line(text: str) -> bytes` = `text + "\r"` (ASCII).
- Alle Fundstellen aus B.3 nutzen sie; keine Literale `…\r\n` mehr für
  Befehle.
- Antworten des TNC enthalten weiter `\r\n` — Parser bleiben unverändert.

**Commit:** `comm: one place for the verbose command terminator (CR only)`

---

## Teil B — ILFPACK wieder normal

- Die P72-Sonderregel „ILFPACK nie live" entfällt, wenn T175 Schritt 4
  bestanden ist. `IL` in `host_params.py` mit T175-Beleg freigeben (beide
  Geräte, falls gemessen).
- Tooltip ILFPACK in der Packet-Maske: was es tut, nach Handbuch; kein
  Warnhinweis mehr nötig.

**Commit:** `ParamApplier: ILFPACK applied live again (T175)`

---

## Teil C — Tests (zuerst rot)

- Statischer Test: Kein Befehls-Literal mit `\r\n` in `comm/`, `modes/`,
  `maildrop/` und den Befehlspfaden von `main_window.py`; Datenpfade
  stehen auf einer ausdrücklichen Ausnahmeliste (Datei:Funktion).
- Upload-Schreibprotokoll: jeder Befehl endet auf `\r`, nicht auf `\r\n`.
- Fake-TNC, der LF nicht ignoriert (simuliert ILFPACK OFF): heute ab dem
  zweiten Befehl `?What?` (rot), danach alle Antworten richtig.
- RTTY-TX-Zeilenende unverändert `\r\n`.

**Commit:** `Tests: verbose commands end with CR only`

---

## Teil D — Hardware T176 (App, Gerät B)

1. Packet-Maske: ILFPACK aus → OK → sofort übernommen (`ok`), Leave Host
   Mode, im Terminal `PACLEN`, `USERS`, `HELP` — alle richtig beantwortet.
2. PK232PY neu starten (TNC weiter mit ILFPACK OFF): Init, Upload,
   Host-Mode-Eintritt ohne `?What?`.
3. ILFPACK wieder an.

---

## Definition of Done

- T175 gemessen, bevor Teil A–C umgesetzt werden
- rote Tests vorher nachgewiesen, volle Suite grün
- `Testplan.md`: T175, T176 OPEN; `Backlog.md`: P75
- **Push nach Freigabe**; `.\Sources2Text.ps1`