# Claude Code Prompt — P80b: Ergebnisse T166/T167 eintragen, widerlegte Kürzel nicht mehr senden

> Ablage: `docs/P80b_Mnemonic_Results_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Grundlage: `main` (nach P80a), Läufe 03.10.2026, beide mit Banner:
> T166 Gerät B `01.AUG.91` (`20261003_213830_mnemonic_probe.log`),
> T167 Gerät A `13.SEP.95` (`20261003_214801_mnemonic_probe.log`).
> Die Ergebnisse sind auf beiden Geräten **gleich**, soweit nicht anders
> genannt.

---

## Befund

### B.1 Moduswechsel — bestätigt
`BA`→`OPBAR`, `AS`→`OPASR`, `MO`→`OPMOR..`, `AM`→`OPAM0R`, `FA`→`OPFA0R`,
`SI`→`OPSI`, `TV`→`OPTV0R`, `NA`→`OPNA0`; jeweils ACK `$00`, zurück auf
`PA` geprüft. Gerät A zusätzlich: `PN` → `OPPN1R1000` (PTLIST, ein Modus).

### B.2 Parameter — bestätigt
Setzen + ACK + Rücklesen + verbose Gegenprüfung + Rückstellung:
`EA` (EAS), `WI` (WIDESHFT), `SR` (SRXALL), `US` (USOS), `WO` (WORDOUT),
`FN` (FAXNEG), `SQ` (SQUELCH), `AY` (ASPECT, 2→3).
Nur abgefragt, Wert = verbose: `RB` (RBAUD 45), `FS` (FSPEED 2),
`NM` (NAVMSG all), `NS` (NAVSTN all).
Das Werkzeug wertete diese als `unparsed` (Normalisierung `Y`↔`ON` fehlt
im Pfad von `mnemonic_probe`) — Werkzeugfehler, Teil C.

### B.3 Widerlegt bzw. falsch zugeordnet
| Kürzel | App nutzt es für | Messung | Folge |
|---|---|---|---|
| `NE` | NAVTEX-Modus (`hostmode.cmd_navtex`) | Antwort `NEY`, OPMODE bleibt `PA` → Parameter NEWMODE (Matrix), kein Modus | Helfer entfernen |
| `PT` | PACTOR-Standby / erster Schritt von Connect (Gerät A) | Antwort `PTA 10`, OPMODE bleibt `PA` → **PACTIME** (Matrix) | nicht mehr als Standby senden |
| `XL` | XLENGTH (Baudot/ASCII) | `$07` beide Geräte | nicht senden |
| `EE` | ERRCHAR | `$07` beide Geräte | nicht senden |
| `MW` | MWEIGHT (Morse, Zahl) | Abfrage `MWN` (Schalter), Setzen `11` → `$01` | nicht senden |
| `CI` | CODE | Abfrage `CIN` (Schalter), verbose CODE `0` | nicht senden |
| `MY` | MYIDENT | B: `$07`; A: `MYnone` — mehrdeutig | nicht senden bis Text-Setztest |
| MID | Morse-ID | Scan `MA MB MC MJ MZ` ohne Treffer | bleibt aus (P80a) |

### B.4 Ungeklärt
`MH` (MHEARD-Abfrage) antwortet nur `MH\x01` (B) bzw. `MH\x03` (A), keine
Liste. Wie die App heute MHEARD anzeigt, ist im Bericht zu belegen.

---

## Teil A — Register

- `comm/mnemonic_registry.py`: Belege aus beiden Logs für B.1 und B.2
  (je Release); `NE` = NEWMODE (Abfrage), `PT` = PACTIME (Abfrage, A),
  `PN` = PTLIST-Modus (A); B.3-Kürzel mit `sent=False` und Grund.
- Neue Parameterzeilen für B.2 in `host_params.py` mit
  `verified_releases` beider Geräte (bzw. als Abfrage belegt), damit
  P72 sie sofort setzen kann.
- `MNEMONIC_AUDIT.md` neu erzeugen.

**Commit:** `registry: T166 T167 results`

---

## Teil B — Code

- `hostmode.cmd_navtex` entfernen (NAVTEX läuft über `NA`).
- PACTOR (Gerät A): `PT` wird nicht mehr als „Standby" gesendet. Die
  Schaltflächen STBY und der Standby-Schritt von Connect werden
  **ausgegraut** mit Tooltip „No Host Mode PACTOR standby command verified
  (PT is PACTIME, T167)". PTLIST (`PN`) bleibt.
- `XL`, `EE`, `MW`, `CI`, `MY`: Bedienelemente ausgrauen, Tooltip mit
  Grund und Testnummer (zentral in `tooltips.py`), Frames entfernen. Die
  zugehörigen verbose Parameter (Upload) bleiben unberührt.
- `PT`, `XL`, `EE`, `MW`, `CI`, `MY` im Register `sent=False` → der
  Registertest schützt die Entscheidung.

**Commits:**
```
hostmode: remove cmd_navtex (NE is NEWMODE)
PACTOR: no PT standby in Host Mode (PT is PACTIME)
Screens: grey out controls with refuted mnemonics
```

---

## Teil C — Werkzeug

`mnemonic_probe`: Parameterauswertung über dieselbe Normalisierung wie
`host_params_probe` (`norm_value`), sodass B.2 `verified` ergibt;
`--reevaluate` auf beide Logs muss das zeigen.

**Commit:** `hw_check: mnemonic_probe uses norm_value`

---

## Teil D — Tests (zuerst rot)

- PACTOR STBY sendet kein `PT` mehr; Bedienelement ausgegraut.
- `cmd_navtex` existiert nicht mehr; NAVTEX-Aktivierung = `NA`.
- Je B.3-Kürzel: kein Frame, Bedienelement ausgegraut.
- `--reevaluate` auf Auszügen beider Logs: B.2 `verified`.

**Commit:** `Tests: refuted mnemonics are not sent`

---

## Teil E — Bericht und Doku

- Bericht: B.4 (MHEARD) — wie die App MHEARD heute darstellt, welcher Weg
  verwendet wird (Host `MH`? verbose?), und ob es im Betrieb funktioniert.
- Bericht: PACTOR-Abläufe in Host Mode (Connect, Standby, Disconnect) —
  was nach Teil B noch funktioniert. Das wird Grundlage des
  PACTOR/AMTOR-Pakets.
- `Testplan.md`: T166, T167 PASS mit Befunden. `Backlog.md`: P80b;
  neu „PACTOR-Standby im Host Mode: Kürzel unbekannt, messen".
- `docs/claude/`: B.3 als Fakten.

**Commits:**
```
Testplan: T166 T167
Backlog: P80b, PACTOR standby open
Docs: add P80b spec file
```

---

## Definition of Done

- rote Tests vorher nachgewiesen, volle Suite grün
- Registertest grün, kein `sent=False`-Kürzel im Code
- **Push nach Freigabe**; `.\Sources2Text.ps1`