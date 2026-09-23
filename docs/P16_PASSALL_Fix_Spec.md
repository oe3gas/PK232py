# Claude Code Prompt — P16: PASSALL-Korrektur und Antwortzuordnung

> Ablage: `docs/P16_PASSALL_Fix_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher `CLAUDE.md`, `Backlog.md`, `Testplan.md` lesen.

---

## Hardwarebefund T17/T86 (21.09.2026, 15:41)

Rohframes aus dem Host Mode, PK-232MBX Firmware v7.1:

```
>> HOST query b'PX'
<< ctl=0x4F ch=15 data=b'HP\x00'   <- liegengebliebene HPOLL-Antwort vom Host-Mode-Eintritt
<< ctl=0x4F ch=15 data=b'PXN'      <- Antwort auf PX: Schalterwert N
>> HOST query b'PS'
<< ctl=0x4F ch=15 data=b'PS$16'    <- Antwort auf PS: Zeichenwert $16 (Ctrl-V)
```

**Ergebnis: `PX` = PASSALL (Schalter), `PS` = PASS (Maskierungszeichen,
Werkseinstellung `$16`).** Deckt sich mit TRM 4.2.2 (`PS PASS`,
`PX PASSALL`).

**Folge:** Der Fix vom 2026-06-22 (`PA` → `PS`) war falsch. Der
PASSALL-Toggle sendet seither `PS Y`/`PS N` und überschreibt damit das
PASS-Zeichen mit dem Buchstaben `Y` oder `N`. Im verbose-/Terminalbetrieb
würde danach jeder getippte Buchstabe `Y` (bzw. `N`) als Maskierungszeichen
verschluckt.

Das Werkzeug meldete `INCONCLUSIVE`, weil es die **erste** Antwort nach dem
Senden als Antwort auf `PX` nahm — tatsächlich war das die verspätete
`HP`-Antwort vom Host-Mode-Eintritt.

---

## P16.1 — `src/pk232py/ui/main_window.py`: PASSALL auf `PX`

In `_wire_packet_buttons()` den `toggle_map`-Eintrag für `btn_passall` von
`b'PS'` auf **`b'PX'`** ändern. Kommentar mit Verweis auf T86 und den
Rohframe `PXN`.

Danach **das ganze Repo nach `b'PS'` durchsuchen** (auch `"PS"` in
Strings, Tooltips, Kommentaren) und jede Fundstelle prüfen:

- ist sie PASSALL gemeint → auf `PX` ändern
- ist sie tatsächlich PASS gemeint → so lassen, Kommentar ergänzen
- die UI-Tooltips der Packet-Maske (`PASSALL … (PS)`) auf `(PX)` ändern

Unit-Test: der PASSALL-Toggle erzeugt einen Frame mit Mnemonic `b'PX'`
und Argument `Y`/`N`; ein zweiter Test stellt sicher, dass **kein** Button
der Packet-Maske einen Frame mit `b'PS'` erzeugt.

**Commit:** `Fix PASSALL mnemonic: PX, not PS (hardware-verified T86)`

---

## P16.2 — `tools/hw_check.py`: Antworten am Mnemonic zuordnen

`query_host(mnemonic)`:

- nach dem Senden **alle** eintreffenden `$4F`-Frames innerhalb des
  Zeitfensters sammeln
- als Antwort gilt nur der Frame, dessen Daten **mit dem gesendeten
  Mnemonic beginnen** (`data.startswith(b'PX')`)
- alle anderen Frames protokollieren als `INFO: unrelated frame <hex>`,
  aber nicht auswerten
- kein passender Frame im Zeitfenster → `None`

Nach dem Host-Mode-Eintritt vor der ersten Abfrage den Eingangspuffer
leeren (anstehende Frames protokollieren und verwerfen).

T17-Auswertung neu:

| Antwort auf PX | Antwort auf PS | Ergebnis |
|---|---|---|
| `PX` + `Y`/`N` | `PS` + `$xx` | PASS: PX = PASSALL, PS = PASS |
| `PS` + `Y`/`N` | `PX` + `$xx` | PASS: umgekehrt |
| sonst | sonst | INCONCLUSIVE mit Rohframes |

Fixtures aus diesem Lauf, **inklusive des vorangestellten `HP\x00`** —
das ist genau der Fall, an dem die alte Zuordnung gescheitert ist.

**Commits (je Datei):**
```
Tools: hw_check correlates host responses by mnemonic prefix
Tests: hw_check T17 fixtures incl. stale HP frame
```

---

## P16.3 — Anwendung: Zuordnung nach Reihenfolge? (nur Untersuchung)

Prüfen, ob die Anwendung selbst irgendwo `$4F`-Antworten **nach
Reihenfolge** statt nach Mnemonic zuordnet — Kandidaten:
`ModeManager`-ACK-Erkennung beim Moduswechsel, MHEARD-Poll `MH0…MH17`,
Parameterabfragen. Die verspätete `HP`-Antwort nach dem Host-Mode-Eintritt
ist am Gerät belegt; jede Stelle, die „die nächste Antwort" erwartet, kann
davon getroffen werden.

**Nichts ändern.** Befunde mit Datei, Funktion und Zeile in `Backlog.md`
eintragen (Priorität 1, falls eine betroffene Stelle gefunden wird).

---

## P16.4 — Dokumentation

### `CLAUDE.md` — zwei Stellen berichtigen

Beide Aussagen `PASSALL = PS` (Abschnitt Mnemonic-Tabelle und Abschnitt
Packet) ersetzen durch:

- **PASSALL = `PX`, PASS = `PS`** — hardwareverifiziert 21.09.2026 (T86,
  Rohframes `PXN` und `PS$16`)
- **Korrekturvermerk**: Der Fix vom 2026-06-22 hat `PA` durch `PS` ersetzt,
  ohne Beleg aus der TRM-Tabelle, die `PX` nennt. Lehre: „never guess" gilt
  auch für Korrekturen — ein Fix braucht dieselbe Quelle wie neuer Code.

Neuer Fallstrick im Host-Mode-Abschnitt:

- Nach dem Host-Mode-Eintritt trifft verspätet eine `HP`-Antwort
  (`$4F`, Daten `HP\x00`) ein. **Antworten immer am Mnemonic-Präfix
  zuordnen, nie an der Reihenfolge.**

Hardwareabschnitt:

- Am 21.09.2026 stand der TNC vor dem Lauf auf **Werkszustand**
  (`MYCALL PK232`, `EXPERT OFF`, `PACLEN 128`, `MAXFRAME 4`, `FRACK 4`,
  AEA-Standard-`MTEXT`). Mögliche Ursache: RAM-Pufferbatterie. Alles, was
  der Uploader nicht sendet, fällt dann bei jedem Ausschalten zurück.

### `Backlog.md`

- Abschnitt „Known bug — fixed (2026-06-22)": **nicht löschen**, sondern
  einen Korrekturvermerk anfügen (`PS` war ebenfalls falsch, richtig ist
  `PX`, siehe T86). Die Geschichte des Fehlers bleibt lesbar.
- **VHF-Eintrag aus P15 umformulieren:** Die Werte vor dem Upload
  (`PACLEN 128`, `MAXFRAME 4`, `FRACK 4`) waren Werkseinstellungen, keine
  VHF-Werte. `VHFPacketMode` sendet beim Aktivieren bereits `MX 4` und
  `SL 10`. Vermutete Lücke ist die **Gegenrichtung**: beim Wechsel
  VHF → HF sendet der HF-Modus nur `VH N`, `HB 300`, `MN Y` — kein
  `MX`/`SL`. HF-Packet liefe danach mit `MAXFRAME 4` / `SLOTTIME 10`
  weiter. **Aus dem Code abgeleitet, nicht gemessen** — Prüfschritt:
  VHF aktivieren, zurück auf HF, im Terminal `MAXFRAME` und `SLOTTIME`
  abfragen.
- Betreibernotiz: Pufferbatterie des PK-232 prüfen (TNC aus/ein, dann
  `MYCALL` abfragen — `PK232` bedeutet Speicherverlust).

### `Testplan.md`

- **T86**: PASS, 21.09.2026, Rohframes wie oben, Befund `PX`/`PS`
- neuer Fall **T110** (Hardware, OPEN): PASSALL-Button nach dem Fix am
  Gerät schalten, danach im Terminal `PASSALL` und `PASS` abfragen —
  PASSALL muss wechseln, PASS muss `$16` bleiben
- neuer Fall **T111** (Hardware, OPEN): der VHF→HF-Prüfschritt aus dem
  Backlog-Eintrag

**Commit:** `Docs: PASSALL is PX (T86), stale HP frame, VHF entry corrected`

---

## Definition of Done

- `python -m pytest` grün, neue Tests eingeschlossen
- Kein Frame mit Mnemonic `b'PS'` mehr aus der Packet-Maske
- `--dry-run t17` zeigt die Host-Frames, ein Test mit dem realen
  `HP\x00`-Vorlauf ergibt PASS
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"