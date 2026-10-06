# Claude Code Prompt — P88: Befehls-/Firmware-Matrix als einzige Wahrheit

> Ablage: `docs/P88_Command_Matrix_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Grundlage: `main` (nach P87). Doku nach `docs/claude/`.
> Betreiberentscheid 06.10.2026: Eine Befehls-/Firmware-Matrix, die mit der
> Zeit wächst und die **einzige Wahrheit** ist — auch um Messläufe nicht
> unnötig zu wiederholen.

---

## Ausgangslage

Wissen darüber, welcher Befehl auf welcher Firmware existiert, liegt heute
verstreut:

| Ort | Inhalt |
|---|---|
| `comm/devices.py` | `unknown_verbose` je Gerät (P85) |
| `comm/host_params.py` | Host-Kürzel, `verified_releases` (P71/P72) |
| `comm/mnemonic_registry.py` | Host-Kürzel mit Belegen (P80) |
| `docs/PK232_firmware_matrix.md` | Hypothesen-Matrix (Konfidenz H/M/L), §2a Einzelbefunde |
| `docs/Testplan.md`, `hw_logs/` | Messungen T151 … T175 |
| Parametermasken | Felder ohne Prüfung, ob der Befehl existiert (Q-Werte, XLENGTH, TXSMT, PTSUM …) |

Nicht im Repo, vom Betreiber jetzt übergeben:

- `PK232_FW_scan.py` — Live-Scanner (Juli 2026, Chat „PK232 Befehle nach
  Firmware-Version testen"). **Ältere Fassung**: enthält noch `AMOTR`
  (Tippfehler, gemessen UNSUPPORTED) und probt `TRANS` (bricht die Sitzung;
  danach liefern TRFLOW/XFLOW `ERROR`).
- `out.csv` — Ergebnis eines Laufs mit diesem Scanner an **Gerät A
  (13.SEP.95, v7.1)**, 28.07.2026: 177 SUPPORTED, 1 UNSUPPORTED (AMOTR),
  2 ERROR (TRFLOW, XFLOW — Folge von TRANS; vom Betreiber danach im Terminal
  als vorhanden und EXPERT-gesperrt bestätigt), 1 NOT_PROBED (CALIBRATE).
  Die CSV hat **keine** Release-Spalte; die Zuordnung zu Gerät A stammt aus
  dem damaligen Chat (Banner `Release 13.SEP.95`, COM22).
- `PK232 Commands (Timewave copy).txt` — Befehlsliste von Timewave (237
  Zeilen: Name mit Kurzform, Default, Funktion). Nicht vollständig: PTUP/
  PTDOWN fehlen, obwohl sie in der v7.1-Mnemonic-Tabelle stehen.

---

## Teil A — Rohdaten ins Repo, unverändert

- `tools/pk232_fw_scan.py` ← `PK232_FW_scan.py` (Inhalt unverändert, nur
  umbenannt; Kopfkommentar: Herkunft, „ältere Fassung, siehe P88 Teil D").
- `docs/reference/fw_scan/20260728_deviceA_13SEP95.csv` ← `out.csv`
  (unverändert; daneben eine `.md` mit Herkunft, Gerät, Datum, bekannten
  Mängeln AMOTR/TRANS/TRFLOW/XFLOW).
- `docs/reference/timewave_commands.txt` ← Timewave-Liste (unverändert).

**Commits:** je Datei einer.

---

## Teil B — Die Matrix: eine Datendatei, ein Lesemodul

**Datei** `src/pk232py/data/command_matrix.csv` (UTF-8, eine Zeile je
Befehl, sortiert nach Name). Spalten:

| Spalte | Inhalt |
|---|---|
| `name` | voller Name (`ILFPACK`) |
| `abbrev` | Mindestabkürzung laut Großschreibung der Quelle (`IL`) |
| `host` | Host-Kürzel, nur wenn **gemessen**; sonst leer |
| `kind` | `param` · `immediate` · `mode` · `action_tx` (tastet Sender) · `danger` (RESET, RESTART, MEMORY, CALIBRATE, TRANS …) |
| `default` | laut Quelle |
| `function` | kurze englische Beschreibung |
| `src_desc` | Quelle der Beschreibung (`timewave`, `stabo`, `trm`) |
| `fw_01.AUG.91` | `yes` · `no` · `expert` (vorhanden, EXPERT nötig) · `?` |
| `fw_13.SEP.95` | dto. |
| `fw_30.12.1988` | dto. |
| `ev_01.AUG.91`, `ev_13.SEP.95`, `ev_30.12.1988` | Beleg je Zelle: Testnummer + Log, `fw_scan 20260728`, `operator 2026-10-06`, `rom v7.1` … Pflicht, sobald die Zelle nicht `?` ist |
| `note` | frei |

Regeln:
- `?` ist der Normalfall für Ungemessenes. **Nie** aus einer Hypothese
  `yes`/`no` setzen.
- Eine Zelle ändert sich nur mit neuem Beleg; der alte Beleg bleibt in der
  Git-Historie.

**Lesemodul** `comm/command_matrix.py` (Qt-frei), einzige Leseschnittstelle:
`exists(name, release) -> "yes"|"no"|"expert"|"?"`, `host(name)`,
`evidence(name, release)`, `kind(name)`, `entry(name)`.

**Erzeugte Ansicht** `docs/COMMAND_MATRIX.md` per
`tools/gen_command_matrix.py --update` (wie `MNEMONIC_AUDIT.md`); ein Test
schlägt fehl, wenn sie veraltet ist.

**Commits:**
```
data: command matrix (empty schema)
comm: command_matrix reader
tools: gen_command_matrix writes docs/COMMAND_MATRIX.md
```

---

## Teil C — Erstbefüllung nur aus Belegen

Reihenfolge, je Quelle ein Commit, im Commit-Text die Zahl der gesetzten
Zellen:

1. **Namen, Kurzform, Default, Funktion** aus der Timewave-Liste
   (`src_desc=timewave`). Offensichtliche OCR-Fehler korrigieren und in
   `note` vermerken (`Ax2512v2` → `AX25L2V2`, „racket" → „packet",
   „PAX" → „FAX"). Befehle aus PK232PY/STABO, die in der Liste fehlen
   (PTUP, PTDOWN …), als eigene Zeilen mit `src_desc=stabo` bzw. leer.
2. **Gerät A aus `fw_scan 20260728`**: SUPPORTED → `yes` (bzw. `expert`,
   wo das Log das zeigt); AMOTR nicht übernehmen (Tippfehler); TRFLOW/XFLOW
   → `expert` mit Beleg `operator 2026-07-28 terminal (XFLOW ON, TRFLOW OFF
   after EXPERT ON)`; TRANS/CALIBRATE `kind=danger`, Zelle `?`.
3. **Messungen aus diesem Projekt** (aus Testplan/Logs, nicht abschreiben,
   wo es eine Quelle im Code gibt — z. B. `host_params.verified_sources()`):
   - T151/T160/T161/T166/T167: vorhanden + Host-Kürzel je Gerät
   - T155/T160/T168 (`?What?` auf B): EXPERT, MYPTCALL, PTHUFF, PT200,
     PTOVER, ARQTOL, MOPT(T) → `no` auf 01.AUG.91
   - T161: FULLDP → `no` auf 13.SEP.95 und 01.AUG.91
   - T166/T167: XL, EE → `no`; NE = NEWMODE, PT = PACTIME
   - T175: ILFPACK auf 13.SEP.95 → `expert`
   - Q-Werte (QHPACKET, QVPACKET, QMORSE, QRTTY, QWIDE, QTOR, QPTOR, QTDM):
     `no`, Beleg `operator 2026-10-06 terminal` — für die Geräte, die der
     Betreiber nennt (siehe Rückfrage im Bericht)
   - Gerät C: MAILDROP → `no` (Betreiber, PuTTY, 23.09.2026); sonst `?`.
4. **Bericht**: Zahl der Zellen `yes`/`no`/`expert`/`?` je Firmware.

---

## Teil D — Scanner aktualisieren (für B und C)

`tools/pk232_fw_scan.py` an die Stand-Juli-Korrekturen und an P75 bringen:
`NEVER_AUTO = {CALIBRATE, TRANS}` und alle `kind=danger/action_tx/mode`
aus der Matrix; AMOTR raus; Befehlsliste **aus der Matrix** statt eigener
`_RAW`-Tabelle; nach Betriebsart gruppiert; EXPERT entsperren und
zurückstellen; `?EXPERT command` → `expert`; Zeilenende nur `\r`
(`verbose_line`); CSV mit Spalten `release`, `device`, `date`; Option
`--update-matrix`, die **nur `?`-Zellen** füllt und Belege einträgt
(vorhandene Belege nie überschreiben — Widerspruch → Abbruch mit Liste).

Danach Läufe: **T179** Gerät B, **T180** Gerät C (erster Kontakt C:
Betreiber vorher fragen), optional T181 Gerät A zur Bestätigung.

**Commits:**
```
tools: pk232_fw_scan reads the command matrix, never probes danger commands
tools: pk232_fw_scan --update-matrix fills unknown cells only
```

---

## Teil E — Code liest die Matrix (eigenes Folgepaket, nach T179)

Nur vormerken (Backlog), nicht in P88 umsetzen: `devices.unknown_verbose`,
`host_params.verified_releases`, Mnemonic-Register und die Parametermasken
(Felder nur anzeigen, wenn der Befehl auf der Firmware `yes`/`expert` ist)
aus der Matrix ableiten. Bis dahin prüft ein Test, dass diese Stellen der
Matrix **nicht widersprechen**.

**Commit:** `Tests: existing firmware knowledge agrees with the command matrix`

---

## Definition of Done

- Rohdaten unverändert im Repo, Herkunft dokumentiert
- Matrix + Lesemodul + erzeugte Ansicht + Aktualitätstest
- keine Zelle ohne Beleg außer `?`
- Widerspruchstest grün (oder Widersprüche im Bericht, nicht still gelöst)
- volle Suite grün, **Push nach Freigabe**, `.\Sources2Text.ps1`
- `CLAUDE.md`: Regel „Firmware-Wissen nur über die Matrix"
