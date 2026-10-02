# Claude Code Prompt — P74: `UBIT 0 OFF` als Packet-Parameter — Pakete unter der DCD-Schwelle nicht verwerfen

> Ablage: `docs/P74_VHF_UBIT0_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Grundlage: `main` (aktuell), Betreiberbefund 01.10.2026.
> Doku-Hinweise nach `docs/claude/`.
> Reihenfolge: **Teil 0 (Backlog) sofort**. Teil B (Parameter, Upload,
> Maske) braucht nur die verbose Form und kann sofort folgen; nur die
> Host-Form in `host_params` wartet auf Teil A (T156).

---

## Befund

### B.1 Betreiberbefund (01.10.2026, Gerät B laut Betreiber — im Log/Testplan bestätigen)
Empfang in VHF Packet war unzuverlässig. Mit `WHYNOT ON` meldete der TNC
für verworfene Pakete **„packet received below threshold"** (DCD). Nach
`UBIT 0 OFF` (verbose, von Hand) werden alle Pakete mit korrekter CRC
verarbeitet, unabhängig vom DCD-Zustand; der Empfang ist seither
zuverlässig.

### B.2 Handbuch (STABO, Kapitel 12, UBIT; CUSTOM Bit 0)
- `UBIT 0 ON` (Default): Der PK-232 **unterdrückt** ein empfangenes Paket,
  das zu schwach ist, die DCD-LED zum Leuchten zu bringen.
- `UBIT 0 OFF`: Das Paket wird angezeigt, ohne Rücksicht auf die DCD.
- UBIT gilt in **allen** Betriebsarten; Host-Kürzel laut Handbuch **`UB`**.
- Das Handbuch beschreibt nur die **Empfangsseite**. Dass `UBIT 0` die
  Kanalbelegungserkennung beim **Senden** nicht beeinflusst, steht dort
  nicht ausdrücklich — Teil A misst es mit.

### B.3 Was ungemessen ist
- **Host-Form** von `UBIT 0 OFF`: Das Handbuch nennt nur `UB`. Ob das
  Argument `0 N`, `0N`, `0 OFF` lautet, ist unbekannt. Die Firmware-
  Matrix führt `UB UBIT` mit Konfidenz **L** und **nicht** für die
  BASE-Generation (Gerät C).
- Abfrage-Antwort im Host Mode.
- Ob `UBIT 0` nach einem Moduswechsel (`PA`, `VH`, `HB` …) erhalten bleibt.

### B.4 Nebenbefund: USERS ist im Handbuch klar beschrieben
STABO, USERS: „`USERS n` gestattet Connects von außerhalb nur auf den
Kanälen 0 bis n−1; `USERS 0` auf jedem freien Kanal." Das ist mit T147
vereinbar (USERS 1: zweiter Anrufer abgewiesen; USERS 10: Kanal 1) und
beantwortet die in P70 offen gelassene Frage „Anzahl oder Kanalbereich"
zugunsten **Kanalbereich**. Tooltips (Parametermaske und Kanal-Chip)
entsprechend präzisieren, mit Quellenangabe Handbuch + T147.

---

## Teil 0 — Backlog-Eintrag (sofort)

In `docs/Backlog.md`, Priority 1:

```markdown
### UBIT 0 OFF als Packet-Parameter (gilt fuer alle Modi) — open (P74, 2026-10-01)

**Begruendung:** In VHF Packet verwarf der TNC gueltige Pakete. WHYNOT ON
zeigte "packet received below threshold": Mit UBIT 0 ON (Werksvorgabe)
unterdrueckt der PK-232 jedes Paket, das die DCD-LED nicht zum Leuchten
bringt - auch bei korrekter CRC (STABO Kap. 12, UBIT / CUSTOM Bit 0).
Mit UBIT 0 OFF wird jedes CRC-korrekte Paket verarbeitet; der Empfang war
danach zuverlaessig (Betreiber, 01.10.2026, Geraet B).
Da der TNC ohne Pufferbatterie bei jedem Einschalten auf UBIT 0 ON steht,
muss die App den Wert setzen. Betreiberentscheid: UBIT 0 ist ein sichtbarer,
aenderbarer Parameter in der Packet-Maske (Standard OFF) und wird bei jedem
Init und sofort nach Aenderung (P72) gesetzt; er gilt fuer alle Betriebsarten.

**Offen vor der Umsetzung:** Host-Form von UBIT (Handbuch: Kuerzel UB,
Argumentform unbekannt), Verhalten auf Geraet A und C (Matrix: UBIT nicht
in BASE), Wirkung auf das Senden, Wirkung in den
anderen Betriebsarten.
```

**Commit:** `Backlog: UBIT 0 OFF as a Packet parameter (reason and open points)`

---

## Teil A — Messung: `hw_check.py ubit_probe` (nur PC 1)

Mit `operator_step()`; kein Senden.

1. verbose `UBIT 0` abfragen (Ausgangswert, wörtlich).
2. Host Mode betreten. Nacheinander die Kandidaten senden, nach **jedem**
   Kandidaten Antwort roh loggen, dann Host-Abfrage `UB0` roh loggen:
   `UB0 N`, `UB0N`, `UB0 OFF`, `UB0OFF`. Abbruch nach dem ersten
   Kandidaten, dessen Antwort `$00` ist.
3. Host Mode verlassen, verbose `UBIT 0` → muss `OFF` zeigen. Damit ist
   der Kandidat bestätigt (verbose Gegenprüfung wie T151).
4. Host Mode betreten, VHF-Packet-Frames senden
   (`VHFPacketMode().get_activate_frames() + get_init_frames()`), Host
   Mode verlassen, verbose `UBIT 0` → bleibt `OFF`?
5. Rückstellung im Host Mode mit dem bestätigten Kandidaten (Y/ON),
   verbose Kontrolle.

Ergebnis: `host_form=<Kandidat>`, `query_answer=<roh>`,
`survives_mode_frames=<bool>`.

Läufe: **T156** an Gerät B; danach A; Gerät C nur nach Rücksprache (erster
`hw_check`-Kontakt).

**Commit:** `hw_check: ubit_probe - Host Mode form of UBIT 0`

---

## Teil B — Umsetzung: UBIT 0 als Packet-Parameter (Betreiberentscheid 01.10.2026)

**Entscheid:** UBIT 0 wird **kein** Moduswechsel-Frame. Es ist ein
normaler Parameter in der Packet-Maske, für den Betreiber sichtbar und
änderbar, und gilt — wie im TNC selbst — für **alle** Betriebsarten.

- `config.py`, `HFPacketConfig`: `ubit0: bool = False` (False = `UBIT 0
  OFF`). Kommentar: Begründung aus Teil 0. Bestehende INI ohne Schlüssel
  → `False`.
- `ParamsUploader._build_commands()`: `UBIT 0 ON`/`UBIT 0 OFF` (verbose;
  diese Form hat der Betreiber am 01.10.2026 von Hand verwendet). Damit
  wird der Wert bei jedem Init hochgeladen — nötig, da der TNC ohne
  Pufferbatterie auf ON startet.
- `comm/host_params.py`: Zeile `UBIT0` (Name wie in `_build_commands`),
  Mnemonic `UB`, `kind="ubit"`, Index 0; die Host-Form kommt aus T156 in
  **einer** Funktion. Der Coverage-Test (Tabelle = `_build_commands`)
  bleibt grün. P72 setzt den Wert damit sofort im Host Mode, sobald T156
  die Form bestätigt hat.
- Packet-Maske (`params_hf.py`, nach P73 Spalte „Flags"): Checkbox
  **„UBIT 0 (DCD gate)"** — Haken = ON. Tooltip:
  > „OFF (recommended): every packet with a correct CRC is processed,
  > also when the signal is too weak to light the DCD LED. ON (factory
  > default) silently drops such packets - with WHYNOT ON the TNC reports
  > 'packet received below threshold' (found 01.10.2026, device B). Keep
  > it OFF. Applies to all modes."
- **Entfernen:** Die freien Textfelder `UBIT:` in `params_baudot.py` und
  `params_amtor.py` werden weder gespeichert noch hochgeladen (`git grep
  -n ubit -- src/pk232py/config.py src/pk232py/comm` → leer). Sie sind
  toter Code und eine zweite Stelle für denselben TNC-Wert → entfernen.
- Keine Änderung an `modes/packet_vhf.py` / `packet_hf.py`.

**Commits:**
```
Config: UBIT 0 as a Packet parameter, default OFF
ParamsUploader: upload UBIT 0
host_params: UBIT 0 row
Params: UBIT 0 checkbox with tooltip in the Packet dialog
Params: remove unused UBIT text fields from AMTOR and Baudot dialogs
```

---

## Teil C — Tests (zuerst rot)

- `_build_commands` enthält `UBIT 0 OFF` bei Standardkonfiguration
  (heute nicht = rot), `UBIT 0 ON` bei `ubit0=True`.
- INI ohne Schlüssel → `ubit0 is False`; INI mit `ubit0 = true` → True.
- Packet-Maske: Checkbox vorhanden, Tooltip enthält „recommended" und
  „below threshold"; Round-Trip Dialog → Config → Dialog.
- AMTOR- und Baudot-Maske haben kein `UBIT`-Feld mehr.
- `host_params`-Coverage-Test grün mit der neuen Zeile.
- `ubit_probe` Dry-Run ohne Port, Kandidatenreihenfolge wie in Teil A.

**Commit:** `Tests: UBIT 0 parameter, upload and dialog`

---

## Teil D — Doku

- `docs/claude/`: B.1–B.3; USERS-Semantik aus B.4.
- Tooltips USERS (Parametermaske, Kanal-Chip): „Incoming connects are
  accepted only on channels 0 to n-1; USERS 0 = any free channel (STABO
  manual; consistent with T147, device B)."
- `Testplan.md`: T156 OPEN.

**Commits:**
```
Docs: UBIT 0 and USERS semantics
Params: USERS tooltip per manual and T147
Testplan: T156 UBIT probe
Docs: add P74 spec file
```

---

## Definition of Done

- Teil 0 committet und gepusht, bevor Teil A beginnt
- Host-Form in `host_params` erst nach T156; Kandidat nicht geraten
- `git grep -n -i ubit -- src/pk232py/ui/dialogs/params_amtor.py src/pk232py/ui/dialogs/params_baudot.py` → leer
- neue Tests zuerst rot, volle Suite grün
- **Push**, Meldung mit Hash; `.\Sources2Text.ps1`