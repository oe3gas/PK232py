# Claude Code Prompt — P71a: `host_params_probe` nachbessern — Rückstellung im Host Mode, Auswertung gegen die verbose Ausgangswerte, Auslöser für `?What?` finden

> Ablage: `docs/P71a_Host_Params_Probe_Followup_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Grundlage: `main` @ `cd9a212`, Lauf T151 vom 01.10.2026,
> `hw_logs/20261001_185959_host_params_probe.log`, **Gerät B, Release
> 01.AUG.91** (Banner). Weiterhin **nur Messung**.

---

## Befund

### B.1 Setzen und Abfragen im Host Mode funktionieren
Für alle 38 gesetzten Parameter: Abfrage liefert `<mn><Wert>`, Setzen
antwortet `<mn> $00` (ACK), erneute Abfrage zeigt den Testwert.
Beispiele: `PL128` → `PL\x00` → `PL129`; `UR1` → `UR\x00` → `UR2`;
`AVY` → `AV\x00` → `AVN`.

Antwortformat (gemessen): Zahl als ASCII-Dezimalziffern, Schalter als
`Y`/`N`, Texte wörtlich (`UNCQ`, `CFall`, `MTnone`), Steuerzeichen als
`$hh` (`CN$03`, `CL$18`, `SP$0D`), leerer Text als `\r` (`BT\r`, `CT\r`).

### B.2 Fehlercodes
- `$07` auf Abfrage von `EX`, `PH`, `PB`, `PV`: Befehl auf diesem Gerät
  unbekannt (verbose `EXPERT`/`PTHUFF`/… → `?What?`; Gerät B hat kein
  PACTOR). Bestätigt die Annahme in `rejected_code()`.
- `$10` auf Abfrage von `DA` (DAYTIME, nicht gestellt). Bedeutung
  ungemessen, nur festhalten.

### B.3 Die Zuordnung ist für 50 Parameter belegt — aus Pass 0, nicht Pass 2
Pass 2 lieferte nichts (B.4). Aber Pass 0 hat die verbose Ausgangswerte
gelesen, und **jeder** Host-Abfragewert aus Pass 1 stimmt mit dem verbose
Wert desselben Parameters überein (normalisiert `Y`/`N` ↔ `ON`/`OFF`):
PACLEN 128, TXDELAY 30, MAXFRAME 4, FRACK 5, RETRY 10, PERSIST 63,
SLOTTIME 30, DWAIT 16, CHECK 30, MONITOR 4, USERS 1, MSPEED 20, TDBAUD 96,
ARQTMO 60, COMMAND `$03` usw.

Für Zahlen ist das ein starker Beleg; bei Schaltern kann ein gleicher
Wert zufällig sein, deshalb dort „schwach", bis Pass 2 funktioniert.

- **`AO` = ARQTMO** (verbose ARQTMO 60 = `AO60`; verbose ARQTOL → `?What?`
  auf Gerät B). Der Matrix-Eintrag `AO ARQTOL` ist falsch.
- **KILONFWD**: verbose `KILONFWD  ON` wurde nicht geparst (`original =
  None`), Host `KLY` passt dazu — Parserfehler im Werkzeug.

### B.4 Nach Pass 1 versteht der TNC fast keine verbose Befehle mehr
Pass 2 (19:02:42): `MYCALL` → Antwort korrekt; **jede** weitere Abfrage
(`PACLEN`, `TXDELAY`, … `MTEXT`) → `?What?`. Dieselben Befehle gingen in
Pass 0 (19:00:16 ff.). Folge: Pass 2 konnte nichts prüfen und **nichts
zurückstellen** — der TNC blieb mit allen Testwerten stehen, u. a.
`XMITOK N`, `AX25L2V2 N`, `MAILDROP Y`, `MONITOR 5`, `USERS 2`.
Abhilfe bis zur Korrektur: TNC aus- und einschalten (keine Pufferbatterie, danach Werkseinstellung).

Einer der in Pass 1 gesetzten Testwerte schaltet den verbose
Befehlsinterpreter um. Welcher, ist unbekannt.

### B.5 Werkzeugfehler
- Rückstellung hängt am verbose Weg (B.4) — dabei ist der Host-Weg gerade
  als funktionierend gemessen.
- `classify_host_param` vergleicht nur mit Pass 2; die Pass-0-Werte
  bleiben ungenutzt → alle Ergebnisse `unparsed`.
- Verbose Parser: `KILONFWD  ON` → `None`.

---

## Teil A — Rückstellung im Host Mode

Am Ende von Pass 1, **vor** dem Verlassen des Host Mode: jeden gesetzten
Parameter per Host-Frame auf den Pass-1-Abfragewert (q1) zurücksetzen und
erneut abfragen. Ergebnis je Parameter `restored` / `restore_failed`.
Danach Host Mode verlassen. Pass 2 prüft dann nur noch.

**Commit:** `hw_check: host_params_probe restores in Host Mode`

---

## Teil B — Auswertung mit Pass 0

`classify_host_param` bekommt zusätzlich `verbose_before`. Neue Ergebnisse:

| Ergebnis | Bedingung |
|---|---|
| `verified` | q1 == verbose_before (normalisiert), Set-ACK `$00`, q2 == Testwert; bei Zahlen/Text **oder** bei Schaltern mit bestandenem Pass 2 |
| `verified_weak` | wie oben, aber Schalter ohne Pass 2 |
| `host_only` | verbose `?What?`, Host liefert Wert (z. B. ARQTOL/AO auf B) |
| `rejected` | Fehlercode, wörtlich |

Normalisierung (eine Funktion): `Y`↔`ON`, `N`↔`OFF`, Groß-/Kleinschreibung
egal, `$hh` unverändert.

Verbose-Parser: Werte nach einem Namen ohne Abkürzungsgroßschreibung
(`KILONFWD  ON`) erkennen; Test mit genau dieser Zeile.

**Ohne neuen Hardware-Lauf** lässt sich T151 nachträglich auswerten: neue
Option `--reevaluate <logfile>` liest q1/set/q2 und die Pass-0-Werte aus
dem Log und gibt die neue Zusammenfassung aus.

**Commits:**
```
hw_check: classify host params against the pass-0 verbose values
hw_check: verbose parser reads KILONFWD-style lines
hw_check: --reevaluate a host_params_probe log
```

---

## Teil C — Den `?What?`-Auslöser finden: `--part C`

Bisektion über Gruppen, je Gruppe:
1. Host Mode: Testwerte der Gruppe setzen (wie Pass 1).
2. Host Mode verlassen, verbose `PACLEN` und `USERS` abfragen.
3. `?What?` → Gruppe enthält den Auslöser; Host Mode betreten, Gruppe per
   Host zurückstellen; Gruppe halbieren, weiter. Sonst: Host Mode
   betreten, zurückstellen, nächste Gruppe.

Gruppen: Packet-Zahlen · Packet-Schalter · RTTY/AMTOR/Morse ·
MailDrop-Schalter (`MV`, `MU`, `TL`, `3R`) · `8B`, `XO`.
Ergebnis: der einzelne Parameter (oder die Kombination), nach dem verbose
`PACLEN` mit `?What?` beantwortet wird, plus die verbose Antwort auf
`HELP` in diesem Zustand (zeigt, welche Befehle noch gelten).

Nur PC 1, mit `operator_step()`. Sicherheitsnetz: Gelingt die
Host-Rückstellung nicht, Schlussanweisung „power-cycle the TNC".

**Commit:** `hw_check: host_params_probe part C - find the parameter that breaks verbose commands`

---

## Teil D — Tests (zuerst rot)

- `classify_host_param` mit den **echten Bytes** aus dem T151-Log:
  PACLEN (`PL128`/`PL\x00`/`PL129`, verbose 128) → `verified`;
  AX25L2V2 (`AVY`/…/`AVN`, verbose ON, kein Pass 2) → `verified_weak`;
  ARQTOL (verbose `?What?`, `AO60`) → `host_only`; EXPERT (`EX\x07`) →
  `rejected (0x07)`.
- `--reevaluate` mit einem Auszug des echten Logs.
- Dry-Run: Rückstellframes stehen **vor** dem Verlassen des Host Mode.

**Commit:** `Tests: host_params_probe evaluation against real T151 bytes`

---

## Teil E — Tabelle und Doku

- `comm/host_params.py`: ARQTOL `mnemonic=b""` mit Kommentar „matrix lists
  AO, but AO answers ARQTMO's value; ARQTOL is ?What? on 01.AUG.91" — und
  ein Test, dass jedes Mnemonic in der Tabelle **höchstens einmal**
  vorkommt.
- `docs/PK232_firmware_matrix.md`: AO-Zeile für ARQTOL als widerlegt
  markieren (T151).
- `docs/claude/`: B.1–B.3 als Fakten Gerät B.
- `Testplan.md`: T151 PASS mit Einschränkung B.4; neu T155 (`--part C`).

**Commits:**
```
host_params: AO belongs to ARQTMO, mnemonics unique
Docs: Host Mode parameter answers on device B
Testplan: T151 result, new T155
Docs: add P71a spec file
```

---

## Definition of Done

- neue Tests zuerst rot, volle Suite grün
- `--reevaluate` auf das T151-Log ergibt ≥ 30 × `verified`
- **Push**, Meldung mit Hash; `.\Sources2Text.ps1`, „sources aktualisiert"