# Claude Code Prompt — P78: Firmware ohne Banner erkennen, verbose Änderungen in die Konfiguration übernehmen, ein Weg für MONITOR

> Ablage: `docs/P78_Release_Fingerprint_And_Verbose_Sync_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Grundlage: `main` (nach P77), Betreiberbefund T162, 03.10.2026, Gerät B.
> Doku nach `docs/claude/`.

---

## Befund (T162, Betreiber, mit Screenshots)

1. Host Mode, VHF Packet, Parametermaske MONITOR 4 → 6, OK → Dialog
   „MONITOR not verified for Host Mode on **unknown** - saved, TNC
   unchanged". Symbolleiste: „TNC-Firmware: —". MAXFRAME-Änderung
   ebenso wirkungslos.
2. Dieselbe Änderung über das Monitor-Auswahlfeld in der VHF-Packet-
   Maske wirkt sofort (verbose danach 6).
3. verbose `MONITOR 3`, zurück in den Host Mode → Auswahlfeld und TNC
   zeigen wieder **6**.
4. Der Hinweisdialog heißt noch „HF Packet parameters not taken…".

### Ursachen (Code)

**B.1 Release nur aus dem Banner.** `SerialManager.tnc_release` kommt
ausschließlich aus dem Einschalt-Banner. War der TNC beim Verbinden schon
wach, bleibt er `None`; P72 behandelt „unbekannt" wie „nicht freigegeben"
und setzt im Host Mode **nichts**. Einen Befehl „VERSION" hat der PK-232
lokal nicht (Firmware-Matrix §1). `RESTART` würde den Banner neu
ausgeben, trennt aber womöglich bestehende Verbindungen — scheidet aus.

**B.2 Gemessen: EXPERT unterscheidet die Generationen.**

| Gerät | verbose `EXPERT` | Host `EX` (Abfrage) | Beleg |
|---|---|---|---|
| B, 01.AUG.91 | `?What?` | Fehlercode `$07` | T151, T155 |
| A, 13.SEP.95 | Wert (`ON`/`OFF`) | `EXY`/`EXN` | T151 22:07, T152, T158 |
| C, 30.12.1988 | ungemessen | ungemessen | — |

Laut `docs/DEVICES.md` gibt es je Generation genau ein Gerät.

**B.3 Zwei Wahrheiten für einen Parameter.** Die Konfiguration ist Quelle
für Init-Upload und Moduswechsel-Frames (P73: `MN<monitor>`). Ein
Parameter, den der Betreiber im verbose Terminal ändert, kommt in der
Konfiguration nie an — der nächste Moduswechsel überschreibt ihn (Befund
3).

**B.4 Das Monitor-Auswahlfeld** der Packet-Maske ist ein zweiter Weg für
MONITOR neben der Parametermaske (Befund 2). Ob es die Konfiguration
schreibt, ist im Abschlussbericht zu belegen.

---

## Teil A — Release ohne Banner: Fingerabdruck

- Neues Qt-freies Modul `comm/devices.py`, **eine** Stelle:
  `KNOWN_DEVICES` aus `docs/DEVICES.md` (Generation, Release, Gerät) und
  `infer_release(expert_answer) -> Optional[tuple[str, str]]`:
  `?What?`/`$07` → `("01.AUG.91", "inferred")`;
  Wert → `("13.SEP.95", "inferred")`; sonst `None`.
- `SerialManager`: Ist nach dem Init kein Banner-Release bekannt, **eine**
  Abfrage — verbose `EXPERT` bzw. im Host Mode `EX` — und Ergebnis in
  `tnc_release` mit Quelle `inferred` speichern. Banner hat immer Vorrang.
- Symbolleiste: „Release 01.AUG.91 (inferred)" bzw. wie bisher bei Banner.
- `ParamApplier`: `inferred` gilt wie Banner. Docstring: gilt nur, solange
  `DEVICES.md` je Generation ein Gerät führt; ein zweites Gerät derselben
  Generation macht den Fingerabdruck mehrdeutig → dann `None`.
- Gerät C: bewusst `None` (ungemessen).

**Commits:**
```
comm: devices table and release fingerprint from EXPERT
SerialManager: infer the release when no banner was seen
MainWindow: show inferred release in the toolbar
```

---

## Teil B — verbose Änderungen in die Konfiguration übernehmen

Der TNC bestätigt jede verbose Änderung einheitlich:

```
MOnitor    was 4 (...)
MOnitor    now 3 (...)
```

(Format aus den Init-Upload-Logs und T151.)

- **Ein** Parser `parse_was_now(lines) -> Optional[(name, old, new)]` in
  `comm/link_status.py` oder einem neuen `comm/verbose_parse.py` (nicht
  doppelt): Name case-insensitiv gegen die Namen aus
  `ParamsUploader._build_commands()` abgleichen (TNC kürzt die
  Großschreibung, z. B. `MAXframe`, `UBit   0`).
- `MainWindow`: jede verbose Ausgabezeile läuft durch den Parser; Treffer →
  Konfiguration setzen und speichern, `[SYS] MONITOR 3 taken into the
  parameters` im Terminal. Werte aus dem eigenen Init-Upload und aus
  `ParamApplier` lösen das ebenfalls aus — das ist harmlos (gleicher Wert),
  aber **kein** zweites Speichern bei unverändertem Wert.
- Bandwerte (MAXFRAME, SLOTTIME): zugeordnet nach aktivem Band (P73-
  Bandtabelle).
- Nicht übernommen: Parameter ohne Config-Feld (nur Hinweis im Log).

**Commit:** `MainWindow: verbose was/now answers update the parameters`

---

## Teil C — ein Weg für MONITOR

Das Monitor-Auswahlfeld der Packet-Maske ändert die Konfiguration und
setzt den TNC **über `ParamApplier`** (wie die Parametermaske). Kein
eigener Sendeweg mehr. Im Abschlussbericht: wie es vorher funktionierte.

**Commit:** `PacketScreen: monitor selector goes through ParamApplier`

---

## Teil D — Kleinkram

- Hinweisdialog-Titel „HF Packet parameters not taken…" → „Packet
  parameters not taken by the TNC" (Rest von P73).

**Commit:** `MainWindow: Packet in the not-taken dialog title`

---

## Teil E — Tests (zuerst rot)

- `infer_release`: `?What?` → 01.AUG.91, `EXN` → 13.SEP.95, `b"EX\x07"` →
  01.AUG.91, Unbekanntes → `None`.
- Kein Banner + verbose `EXPERT` → `?What?`: `tnc_release ==
  "01.AUG.91"`, Quelle `inferred`; ParamApplier sendet `MN6` (heute:
  nichts = rot).
- `parse_was_now` mit echten Zeilen (`MOnitor was 4 / now 3`,
  `MAXframe …`, `UBit   0  now OFF`).
- verbose `MONITOR 3` → Config `monitor == 3`; anschließender Host-Mode-
  Eintritt sendet `MN3` (heute `MN6` = rot).
- Monitor-Auswahlfeld → ParamApplier-Aufruf, Config geändert.

**Commit:** `Tests: release fingerprint, verbose sync, monitor path`

---

## Teil F — Hardware T164 (Gerät B, TNC **ohne** Aus-/Einschalten)

1. App verbinden, während der TNC schon läuft. **Erwartet:**
   „Release 01.AUG.91 (inferred)".
2. Host Mode, VHF Packet, Parametermaske MONITOR 4 → 6 → `ok`.
3. VHF-MAXFRAME 4 → 5 → `ok`; Leave Host Mode, `MAXFRAME` → 5.
4. verbose `MONITOR 3` → Hinweis „taken into the parameters"; Ctrl+H →
   Auswahlfeld zeigt 3; Leave, `MONITOR` → 3.
5. Danach mit Gerät A wiederholen (Schritt 1: „13.SEP.95 (inferred)").

---

## Teil G — Doku

- `Testplan.md`: T162 FAIL (Befund oben), T164 OPEN.
- `docs/claude/`: Fingerabdruck (B.2) und die Regel „verbose Änderungen
  landen über den was/now-Parser in der Konfiguration".
- `DEVICES.md`: Hinweis, dass ein weiteres Gerät derselben Generation den
  Fingerabdruck mehrdeutig macht.

**Commits:**
```
Testplan: T162 FAIL, T164
Docs: release fingerprint and verbose sync
Docs: add P78 spec file
```

---

## Definition of Done

- rote Tests vorher nachgewiesen, volle Suite grün
- Monitor-Wert hat genau einen Schreibweg (ParamApplier)
- **Push nach Freigabe**; `.\Sources2Text.ps1`