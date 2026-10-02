# Claude Code Prompt — P72: Geänderte Parameter sofort in den TNC — im Host Mode direkt per Host-Befehl

> Ablage: `docs/P72_Params_Apply_Now_Spec.md` im Repo — **ersetzt** die
> bisher untracked liegende Fassung gleichen Namens.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Grundlage: `main` (nach P74), Messläufe T151 (Gerät B), T152 und T156
> (Gerät A). Doku-Hinweise nach `docs/claude/`.

---

## Vorgabe des Betreibers

1. Nach OK in einer Parametermaske steht der Wert **sofort** im TNC.
2. Im Host Mode **direkt per Host-Befehl** (wie PcPackRatt). Ein Wechsel in
   den verbose Modus dafür ist **ausgeschlossen**.

## Grundsatz

Was in der Maske steht, steht im TNC — oder der Betreiber sieht klar,
welcher Wert nicht übernommen wurde und warum.

---

## Befund

### B.1 Heute
Alle sechs Parameter-Handler in `main_window.py` speichern nur und melden
„sent to TNC on next initialisation"; `ParamsUploader.upload()` läuft nur
im Init. Betreiber 30.09.2026: USERS 1 → 10, OK, verbose `USERS` zeigt 1.

### B.2 Gemessen: Host-Befehle für Parameter

**Format** (T151, T152, T156): Setzen `SOH $4F <mn><Wert> ETB` → Antwort
`<mn> $00` (ACK). Abfrage `SOH $4F <mn> ETB` → `<mn><Wert>`. Zahlen
ASCII-dezimal, Schalter `Y`/`N`, Texte wörtlich, Steuerzeichen als `$hh`,
leerer Text als `\r`. Fehler: einzelnes Byte (`$07` = Befehl auf diesem
Gerät unbekannt, `$10` bei DAYTIME ungestellt).

**Gerät B, Release `01.AUG.91`** — `host_params_probe --part A --exclude IL`
(T151, 01.10.2026 20:55, Log `20261001_205535_host_params_probe.log`):
37 Parameter `verified` (Setzen + ACK + Rücklesen + verbose Gegenprüfung
mit dem Testwert): PACLEN, TXDELAY, MAXFRAME, FRACK, RETRY, PERSIST,
SLOTTIME, DWAIT, CHECK, MONITOR, RESPTIME, USERS, AX25L2V2, HEADERLN,
CONSTAMP, DAYSTAMP, ACRPACK, ALFPACK, MRPT, PPERSIST, XMITOK, 8BITCONV,
ARQTMO, ADELAY, TDBAUD, TDCHAN, RFEC, RXREV, TXREV, MSPEED, ALFRTTY,
DIDDLE, MAILDROP, MMSG, TMAIL, 3RDPARTY, KILONFWD.
Zusätzlich gesetzt und verbose bestätigt: `UN` (T138 A.3) und `CF`
(T138 A.5).

**Gerät A, Release `13.SEP.95`**:
- T152 (02.10.2026, Log `20261002_172135_host_params_probe.log`):
  USERS, MAXFRAME, PACLEN, FRACK, RETRY, MONITOR, TXDELAY — gesetzt,
  ACK, Rücklesen = Testwert, **bei bestehender Verbindung**, Verbindung
  danach unverändert.
- T156 (02.10.2026 16:28, Betreiberangabe Gerät A, Log ohne Banner):
  **UBIT 0** — Setzen `UB0 N` / `UB0 Y` (mit Leerzeichen), Abfrage `UB0`
  → `UBN`/`UBY`, verbose bestätigt, übersteht die VHF-Moduswechsel-Frames.

**Nicht** gemessen: alle übrigen Parameter auf Gerät A; UBIT auf Gerät B;
alles auf Gerät C.

### B.3 ILFPACK
T155 (Gerät B): Mit `ILFPACK OFF` versteht der TNC nach dem ersten
verbose Befehl keinen weiteren mehr (`?What?`), weil die App Befehle mit
`\r\n` abschließt und das LF dann als erstes Zeichen des nächsten Befehls
gilt. Setzen per Host funktioniert, aber die Folgen treffen den verbose
Betrieb der App. **ILFPACK wird in P72 nicht live gesetzt** (Teil C);
die Zeilenenden löst ein eigenes Paket (P75).

### B.4 Bei bestehender Verbindung
T152 (Gerät A): keiner der sieben geprüften Parameter wurde mit „not
while connected" abgelehnt. Für andere Parameter ungemessen — deshalb
liest P72 **immer** zurück und meldet Ablehnungen wörtlich.

---

## Teil A — `comm/host_params.py`: Messergebnisse eintragen

- `verified_releases` je Zeile:
  - die 37 Parameter aus B.2 Gerät B sowie `UNPROTO`, `CFROM`:
    `"01.AUG.91"`
  - USERS, MAXFRAME, PACLEN, FRACK, RETRY, MONITOR, TXDELAY zusätzlich
    `"13.SEP.95"`
  - `UBIT` (Index 0): Mnemonic `UB`, `"13.SEP.95"`
- Kommentar je Freigabe: Testnummer und Log-Datei.
- **Eine** Funktion je Richtung, abhängig von `kind`:
  `host_set_args(param, value) -> bytes` (z. B. `b"10"`, `b"Y"`,
  `b"0 N"` für UBIT 0) und `parse_host_answer(param, data) -> str | None`
  (Bytes nach dem Mnemonic; UBIT: `UBN` → `OFF`). Normalisierung
  `Y`↔`ON`, `N`↔`OFF` aus P71a wiederverwenden.

**Commit:** `host_params: releases verified by T151 T152 T156`

---

## Teil B — Nur die Änderungen

`ParamsUploader.changed_values(before, after) -> list[tuple[str, str]]`
— (Name, neuer Wert) für jeden Befehl aus `_build_commands(after)`, der in
`_build_commands(before)` nicht byte-gleich vorkommt. Dieselbe Quelle wie
der Init-Upload; keine zweite Liste.

**Commit:** `ParamsUploader: changed_values from two config snapshots`

---

## Teil C — `ParamApplier` (Qt-frei, eine Stelle)

| Zustand | Weg |
|---|---|
| Host Mode | je Parameter Host-Frame aus `host_set_args`, Antwort auswerten (`$00` = ACK, sonst Fehlercode wörtlich), danach Host-Abfrage und `parse_host_answer` zum Rücklesen. **Nur** für Parameter, deren `verified_releases` den aktuellen `SerialManager.tnc_release` enthält. |
| verbose, `cmd:` | verbose Befehl aus `_build_commands`, Rücklesen mit `query_verbose_value()` |
| verbose, Converse | `escape_converse()`, wie oben, danach `CONVERSE` nur bei verbundenem I/O-Kanal (P67) |
| nicht verbunden | nichts senden |

- Ohne Freigabe für die aktuelle Firmware: **nicht** senden, Meldung
  `not verified for Host Mode on <release>`. **Kein** Rückfall auf den
  verbose Weg, **kein** `exit_host_mode()`.
- ILFPACK: nie live setzen (B.3); Meldung `ILFPACK is applied at the next
  initialisation (see P75)`.
- `tnc_release` unbekannt (kein Banner): wie „nicht freigegeben".
- Ergebnis je Parameter: `name`, `wanted`, `tnc_now`, `ok`, `reason`.

**Commit:** `ParamApplier: set changed parameters in Host Mode or verbose, read back`

---

## Teil D — Alle Parametermasken

Jeder Handler: vor dem Öffnen `before = copy.deepcopy(config)`; nach OK
speichern und `ParamApplier` aufrufen. Anzeige in MON bzw. im verbose
Terminal, bei Fehlern zusätzlich ein Dialog:

```
[SYS] USERS  1 -> 10  ok
[SYS] MAXFRAME  4 -> 7  rejected by TNC: <code>   (TNC still 4)
[SYS] CODE  not verified for Host Mode on 01.AUG.91 - saved, TNC unchanged
```

Nicht übernommene Werte bleiben in der Konfiguration; Statusfeld **„TNC
differs from parameters"**, bis ein erfolgreicher Versuch oder der nächste
Init es behebt (eine Zustandsvariable). Die Meldungen „sent to TNC on next
initialisation" entfallen.

**Commits:**
```
MainWindow: apply parameter changes right after OK
MainWindow: show parameters the TNC did not take
```

---

## Teil E — Tests (zuerst rot)

- Host Mode, `tnc_release="01.AUG.91"`, USERS 1 → 10: Schreibprotokoll
  enthält genau `01 4F 55 52 31 30 17`, dann die Abfrage `01 4F 55 52 17`;
  **kein** verbose Byte, **kein** `HOST OFF`. Heute: nichts = roter Test.
- Host Mode, `"13.SEP.95"`, UBIT 0 OFF → `01 4F 55 42 30 20 4E 17`;
  Antwort `UBN` → `ok`.
- Host Mode, `"13.SEP.95"`, AX25L2V2 (nur auf B freigegeben) → nichts
  gesendet, Meldung `not verified for Host Mode on 13.SEP.95`.
- ILFPACK geändert → nichts gesendet, Meldung.
- verbose `cmd:` → verbose Befehl + Rücklesen.
- Konstruierte Fehlerantwort `UR\x07` → `ok=False`, Statusfeld gesetzt.
- `changed_values`: USERS 1 → 10 → genau `("USERS","10")`.

**Commit:** `Tests: parameters applied in Host Mode without leaving it`

---

## Teil F — Doku

- `docs/DEVICES.md`, Gerät A: Release **`13.SEP.95`** (Banner, 02.10.2026,
  T152; Betreiber bestätigt) statt der früheren Abschrift „11.09.1995";
  Letzte Messung T152, T156.
- `docs/claude/`: B.2 und B.4 als Fakten je Gerät.
- `Testplan.md`: T152 (Gerät A, zwei Läufe; erster Lauf B.3 ohne Zeile,
  zweiter mit), T156 (Gerät A), neu **T157** (App, siehe Teil G).
- `Backlog.md`:
  - P72 erledigt nach T157.
  - **Neu:** „`host_params_probe --part A --exclude IL` an Gerät A (alle
    übrigen Parameter für 13.SEP.95 freigeben) und `ubit_probe` an Gerät
    B" — bis dahin meldet P72 diese Parameter als nicht freigegeben.
  - **Neu (P75):** „Verbose Befehle nur mit `\r` abschließen, damit
    ILFPACK OFF sie nicht bricht — vorher messen (CR-only mit ILFPACK ON
    und OFF)".
  - **Neu:** „Trennen: PK-232 hört das UA von Direwolf nicht und wiederholt
    DISC RETRY-mal (Gerät A, 02.10.2026, UBIT 0 ON). Gegentest mit UBIT 0
    OFF."

**Commits:**
```
Docs: device A release is 13.SEP.95
Docs: Host Mode parameter facts per device
Testplan: T152 T156 results, new T157
Backlog: open probes per device, P75 line endings, DISC retries
Docs: add P72 spec file
```

---

## Teil G — Hardware T157 (App, mit Schrittanweisung PC 1 / PC 2)

1. PC 1, Gerät B, Host Mode, VHF Packet: USERS 10 → 9 → OK. **Erwartet:**
   `[SYS] USERS 10 -> 9 ok`, Host Mode bleibt, kein verbose Byte im Log.
2. PC 1, Gerät B: AX25L2V2 umschalten → `ok`.
3. PC 2: QtTermTCP `OE3GAS-2` verbindet sich. PC 1: MAXFRAME ändern →
   `ok`, Verbindung bleibt.
4. PC 1, Gerät B: CTEXT ändern → Meldung `not verified for Host Mode`,
   Statusfeld „TNC differs".
5. PC 1, verbose: PACLEN ändern → `ok`.

---

## Definition of Done

- roter Test „Host Mode, kein verbose Byte" vorher nachgewiesen
- `git grep -n "on next initialisation" -- src` → keine Treffer
- `git grep -n "exit_host_mode" -- src/pk232py/comm/param_applier.py` →
  keine Treffer
- volle Suite grün, **Push nach Freigabe**, Meldung mit Hash;
  `.\Sources2Text.ps1`