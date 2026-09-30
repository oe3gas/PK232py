# Claude Code Prompt — P71: Messpaket `host_params_probe` — Parameter im Host Mode abfragen und setzen

> Ablage: `docs/P71_Host_Params_Probe_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Grundlage: `main` @ `5ffc750`.
> **Ersetzt** die am 30.09.2026 übergebene erste Fassung von P71
> („Apply Now" mit Verbose-Umweg) — die wird **nicht** umgesetzt.
> **Nur Messung** (hw_check-Regel 6). Umsetzung folgt als P72.
> Doku-Hinweise nach `docs/claude/`.

---

## Vorgabe des Betreibers (30.09.2026)

Parameteränderungen aus den Masken müssen **im Host Mode direkt** gesetzt
werden. Ein Wechsel in den verbose Modus dafür ist **ausgeschlossen**.
PcPackRatt, das Vorbild von PK232PY, fragt und setzt Parameter im Host
Mode.

## Befund

- TRM Host Mode: Befehlsframe `SOH $4F <Mnemonic> <Argument> ETB` setzt,
  ohne Argument fragt ab; Antwort `SOH $4F <Mnemonic> …`.
- Gemessen (Gerät B) sind bisher nur: `UN` (T138 A.3/A.4), `CF` (T138
  A.5), `OP` (T142), `HP`, und die Moduswechsel-Frames `PA`, `VH`, `HB`,
  `MX`, `SL`, `MN` (T31, T141 A.8 — ob sie wirklich die Werte setzen, misst
  P73 Teil 0).
- Für alle übrigen ~70 Parameter aus `ParamsUploader._build_commands()`
  steht das Host-Mnemonic nur als **Hypothese** in
  `docs/PK232_firmware_matrix.md` (Konfidenz M/L), z. B. `UR` USERS,
  `PL` PACLEN, `MX` MAXFRAME, `FR` FRACK, `RY` RETRY, `PE` PERSIST,
  `DW` DWAIT, `CK` CHECK, `RP` RESPTIME, `TD` TXDELAY, `AV` AX25L2V2,
  `XO` XMITOK, `ML` MYCALL.
- Unbekannt: Format der Abfrage-Antworten (Zahl als ASCII? Y/N?), Antwort
  auf das Setzen (ACK `$00`? Fehlercodes?), und welche Parameter der TNC
  bei bestehender Verbindung ablehnt (TRM: Fehler `$09` „not while
  connected", Testplan T104).

---

## Teil A — Eine Tabelle: `comm/host_params.py`

Qt-frei, **einzige** Stelle für die Zuordnung verbose Name → Host-Mnemonic:

```python
@dataclass(frozen=True)
class HostParam:
    name: str                 # verbose name as in ParamsUploader
    mnemonic: bytes           # e.g. b"UR"
    kind: str                 # "int" | "bool" | "text" | "call" | "char"
    lo: int | None = None     # int range, from the parameter dialogs
    hi: int | None = None
    verified_releases: tuple[str, ...] = ()   # filled after T151
```

- Eintrag für **jeden** Namen, den `_build_commands()` erzeugt. Mnemonic
  aus der Firmware-Matrix übernehmen, Zeilenverweis im Kommentar. Fehlt er
  in der Matrix: `mnemonic=b""` und Kommentar „not in matrix".
- Ein Test prüft, dass die Namensmenge der Tabelle **gleich** der
  Namensmenge von `_build_commands()` ist (neue Parameter können nicht
  vergessen werden).
- `verified_releases` bleibt in diesem Paket leer; P72 trägt die
  Ergebnisse aus T151 ein.

**Commit:** `comm: host_params table - one mapping from verbose name to Host mnemonic`

---

## Teil B — `hw_check.py host_params_probe`

Mit Schrittführung `operator_step()` (P69a). Zwei getrennte Teile
(`--part A` / `--part B`), wie beim `channel_probe`.

### Teil A — Abfragen und setzen, keine Verbindung (nur PC 1)

Zweipass-Verfahren, damit eine **falsche Zuordnung** (Mnemonic gehört zu
einem anderen Parameter) auffällt:

1. **Pass 1, Host Mode**, für jede Tabellenzeile mit Mnemonic:
   1. Abfrage `SOH $4F <mn> ETB` → Rohantwort (hex + Text) loggen.
   2. Bei `kind` `int` oder `bool`: Testwert setzen — `int`: ein
      gültiger Wert ≠ aktuell (aus `lo`/`hi`), `bool`: umgekehrt.
      Antwortframe roh loggen (ACK? Fehlercode?).
   3. Erneut abfragen → Rohantwort loggen.
   - `text`: nur abfragen; Ausnahme `BTEXT`: Testtext `P71` setzen.
   - `call` und `char` (MYCALL, MYPTCALL, MYSELCAL, COMMAND, CANLINE,
     CANPAC, SENDPAC, CHSWITCH …): **nur abfragen**, nie setzen — eine
     falsch gesetzte Steuerzeichen-Einstellung legt die Verbindung lahm.
2. **Einmal** Host Mode verlassen (nur das Messwerkzeug darf das).
3. **Pass 2, verbose**: jeden in Pass 1 gesetzten Parameter mit dem
   verbose Namen abfragen. Stimmt er mit dem Testwert überein → Mnemonic
   bestätigt. Dann verbose auf den Ausgangswert zurücksetzen.
4. Reine Auswertefunktion `classify_host_param(name, query1, set_resp,
   query2, verbose_now, test_value) -> str` mit den Ergebnissen:
   `verified` (Host-Abfrage liefert Wert, Setzen wirkt, verbose bestätigt),
   `set_ok_query_unparsed`, `query_only` (für nicht gesetzte Arten, wenn
   eine Antwort mit Wert kommt), `rejected` (Fehlercode, wörtlich),
   `no_answer`, `wrong_param` (verbose zeigt den Testwert nicht).
   Das Antwortformat wird **nicht** geraten: Die Funktion nimmt die Bytes
   nach dem Mnemonic als Wert und vergleicht textuell; alles andere wird
   `unparsed` mit Rohbytes.

Zusammenfassung: eine Zeile je Parameter, plus Zählung je Ergebnis.

### Teil B — Setzen bei bestehender Verbindung (PC 1 und PC 2)

1. PC 2: QtTermTCP `OE3GAS-2` verbindet sich mit `OE3GAS` (landet auf
   Kanal 0, T147).
2. PC 1, Host Mode: für `USERS`, `MAXFRAME`, `PACLEN`, `FRACK`, `RETRY`,
   `MONITOR`, `TXDELAY` — jeweils Testwert setzen, Antwort roh loggen,
   abfragen, Ausgangswert zurücksetzen. Nach jedem Parameter `CO` auf
   Kanal 0: Verbindung noch da?
3. PC 2: in QtTermTCP eine Zeile senden → PC 1 sieht sie auf `$30`?
4. Aufräumen: `DI` Kanal 0 (hinter `confirm_tx()`).

Ergebnis je Parameter: `accepted` / `rejected (<code>)`, `link_after`.

**Commits:**
```
hw_check: host_params_probe part A - query, set, verbose cross-check
hw_check: host_params_probe part B - set while connected
```

---

## Teil C — Tests (zuerst rot)

- Tabelle deckt `_build_commands()` vollständig ab (Namensmengen gleich).
- `classify_host_param` für jeden Ergebnisfall mit konstruierten Bytes.
- Dry-Run `--part A`: für jede Zeile mit Mnemonic ein Abfrage-Frame; für
  `call`/`char` **kein** Setz-Frame (geprüft über die Frame-Liste).
- Dry-Run `--part B`: Schritte mit `WHERE: PC 2` für die Verbindung.

**Commit:** `Tests: host_params table coverage and probe evaluation`

---

## Teil D — Testplan und Doku

- `Testplan.md`: **T151** `host_params_probe --part A`, **T152**
  `--part B`, Gerät B, OPEN.
- `Backlog.md`: P72 (Übernehmen ohne verbose) wartet auf T151/T152;
  P73 (Maske Packet) danach.
- `tools/README.md`: neuer Unterbefehl, nicht in `all`.

**Commits:**
```
Testplan: T151 T152 host parameter probe
Docs: hw_check host_params_probe
Docs: add P71 spec file
```

---

## Definition of Done

- neue Tests zuerst rot, volle Suite grün
- `--dry-run host_params_probe --part A|B` ohne Port
- kein neuer Frame-Bauer (`build_command` aus `comm/hostmode.py`)
- **Push**, Meldung mit Hash; `.\Sources2Text.ps1`, „sources aktualisiert"