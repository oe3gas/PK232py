# Claude Code Prompt — P13: Parameterkette bis zum TNC schließen

> Ablage: `docs/P13_Param_Upload_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher `CLAUDE.md`, `Backlog.md`, `Testplan.md` lesen.

---

## Warum

Ein Parameter erreicht den TNC nur, wenn alle vier Glieder der Kette
vorhanden sind:

```
Widget im Dialog → Feld in der Config → INI-Datei → _build_commands() → TNC
      (1)                 (2)               (3)            (4)
```

`ParamsUploader._build_commands()` liest ausschließlich die Config-Dataclasses,
Feld für Feld, nie die Dialog-Widgets. Das P12-Audit prüft die Glieder
(1)–(3). Glied (4) ist ungeprüft — und dort fehlen nachweislich Felder:
`resptime`, `txsmt` und `aerpack` bestehen die Tests A, B und C, werden aber
nie hochgeladen.

Zusätzlich reißt die Kette für ~60 Widgets schon bei (1)→(2) (Backlog-Tabelle
aus P12). Dieses Paket schließt die Kette für die betriebsrelevanten
Packet-Parameter und macht Glied (4) prüfbar.

---

## Grundregel für jeden Befehlsnamen

Jeder Befehl, der neu in `_build_commands()` kommt, wird **vorher** belegt:

1. primär gegen `pk232_mnemonic_table.txt` (Scan des realen Geräts, v7.1)
2. sekundär gegen die Mnemonic-Liste im TRM, Abschnitt 4.2.2
3. bei Widerspruch oder fehlendem Beleg: **nicht hochladen**, Befund in
   `Backlog.md`, Kommentar `# TODO command name unverified` im Uploader

Der Upload läuft im verbose-Modus, es wird also der **Befehlsname**
gesendet, nicht die Zwei-Buchstaben-Mnemonic. Die Tabelle dient nur als
Beleg, dass der Befehl auf dem Gerät existiert.

---

## P13.1 — Test D: jedes Config-Feld muss hochgeladen werden

Neue Testfunktion in `src/pk232py/tests/test_param_dialogs_roundtrip.py`
(dieselbe Datei wie A–C, damit alle vier Glieder an einer Stelle geprüft
sind).

Mechanik wie Test A — **keine Zuordnung von Feldnamen zu Befehlen nötig**:

```
für jede TNC-Parameter-Sektion (hf_packet, pactor, amtor, baudot,
                                misc, maildrop):
    für jedes Feld der Dataclass:
        vorher  = uploader._build_commands(has_pactor=True)
        Feldwert verändern (_bump_field_value aus Test B wiederverwenden)
        nachher = uploader._build_commands(has_pactor=True)
        assert nachher != vorher     # sonst: Feld wird nie hochgeladen
```

`AppConfig.tnc` wird **als Ganzes** ausgenommen, mit einer einzigen
begründeten Zeile: das sind PC-seitige Verbindungseinstellungen (Port,
TBaud, Echo, Fast Init …), keine TNC-Parameter. Das ist eine
Sektionsentscheidung, kein Namensfilter.

Alle weiteren Ausnahmen einzeln und begründet in einer neuen Liste:

```python
# Config fields that deliberately never produce an upload command.
UPLOAD_EXEMPT: dict[tuple[str, str], str] = {
    # ("hf_packet", "feldname"): "Begründung",
}
```

Erwartung für den ersten Lauf: **Test D schlägt fehl** und nennt mindestens
`resptime`, `txsmt`, `aerpack`. Das ist gewollt — es ist der Nachweis, dass
der Test die Lücke sieht. Den Fehlerbericht des ersten Laufs in den
Commit-Text übernehmen, dann die Befunde in den folgenden Paketen beheben.

Hinweis: einige Befehle werden nur bei nicht-leerem Wert gesendet
(`if hf.btext:`). `_bump_field_value()` macht leere Strings nicht-leer, damit
greift der Test auch dort korrekt.

**Commit:** `Tests: upload coverage audit (Test D)`

---

## P13.2 — Die drei Befunde aus Glied (4)

### RESPTIME
Belegt (TRM: `RP RESPTIME`). In den HF-Packet-Block des Uploaders aufnehmen.

### AERPACK
Die TRM-Liste enthält **`ACRPACK`** (`AK`), kein `AERPACK`. Sehr
wahrscheinlich ein Tippfehler aus der Spezifikation.

Vorgehen:
1. gegen `pk232_mnemonic_table.txt` prüfen
2. **Wenn `ACRPACK` bestätigt:** Feld `aerpack` → `acrpack` umbenennen, in
   Dataclass, Dialog (`_chk_aerpack` → `_chk_acrpack`, Beschriftung
   `ACRPACK`), INI und Tests. **INI-Kompatibilität:** beim Lesen den alten
   Schlüssel `aerpack` als Rückfall akzeptieren, geschrieben wird nur noch
   `acrpack`. Das ist eine begründete Ausnahme von der Regel „keine
   internen Umbenennungen" — ein Name, der einen nicht existierenden
   Befehl bezeichnet, ist ein Fehler, keine Namenskonvention. Im
   Commit-Text so begründen.
3. **Wenn nicht bestätigt:** nicht hochladen, `UPLOAD_EXEMPT`-Eintrag mit
   Verweis auf den Backlog.

### TXSMT
Steht in der PK-232-Befehlsliste des TRM **gar nicht**. Möglicherweise ein
Befehl anderer AEA-Geräte (PK-900, DSP-2232).

Vorgehen:
1. gegen `pk232_mnemonic_table.txt` und das STABO-Handbuch prüfen
2. **Wenn auf dem PK-232 nicht vorhanden:** nicht hochladen. Widget im
   Dialog deaktivieren (`setEnabled(False)`), Tooltip
   „Not a PK-232 command — has no effect". `UPLOAD_EXEMPT`-Eintrag mit
   derselben Begründung. Feld und INI-Eintrag bleiben bestehen, damit
   vorhandene INI-Dateien sauber geladen werden.
3. **Wenn doch vorhanden:** normal hochladen.

### Nebenbefund: MYCALL doppelt
`_build_commands()` sendet `MYCALL` zweimal — einmal im Identity-Block,
einmal bei den Message-Parametern. Den zweiten Aufruf entfernen; der erste
prüft zusätzlich auf `"NOCALL"` und ist damit der richtige.

**Commit:** `Params uploader: RESPTIME, verified flag names, single MYCALL`

---

## P13.3 — Packet-Parameter: Kette vollständig schließen

Für jedes der folgenden Felder **alle vier Glieder** herstellen:
Config-Feld, Dialog-Anbindung (`_populate()`/`apply_to()`), INI
(`_apply_hf_packet()`/`_build_hf_packet()`), Upload. Danach den Eintrag aus
`UNWIRED_OK` entfernen — Test A muss ihn dann als verdrahtet erkennen.

### Zugriffsfilter: CFROM, DFROM, MFROM, MTO

Belegt im TRM (`CF`, `DF`, `MF`, `MT`). Der Dialog hat je eine ComboBox
(`_cb_cfrom` …) und ein Textfeld (`_cb_cfrom_le` …).

Config-Darstellung je Filter: zwei Felder

```python
cfrom_mode:  str = "ALL"     # ALL | NONE | YES | NO
cfrom_calls: str = ""        # kommagetrennt, max. 8 Rufzeichen
```

Upload:

| Modus | gesendet |
|---|---|
| `ALL` | `CFROM ALL` |
| `NONE` | `CFROM NONE` |
| `YES` + Rufzeichen | `CFROM YES OE3XYZ,OE1ABC` |
| `NO` + Rufzeichen | `CFROM NO OE3XYZ,OE1ABC` |
| `YES`/`NO` ohne Rufzeichen | **nicht senden**, Warnung ins Log |

Validierung im Dialog: mehr als 8 Rufzeichen → beim OK ablehnen mit
Hinweis. Defaults: `CFROM ALL`, `DFROM ALL`, `MFROM ALL`, `MTO NONE`
(TNC-Werkseinstellungen — vor dem Festschreiben gegen das Handbuch prüfen).

Tooltip am `CFROM`-Feld zwingend: „NONE rejects every incoming connect."
— wer sich damit aussperrt, soll es nicht erst am Gerät merken.

### Einzelflags: 8BITCONV, HID, MBELL

- `8BITCONV` — belegt (`8B`). Voraussetzung für ANSI-Darstellung von
  Mailboxmenüs.
- `HID` — belegt (`HI`). Steuert die HDLC-Identifikation; Voraussetzung
  dafür, dass der ID-Button auf der Packet-Maske wirkt.
- `MBELL` — **in der TRM-Liste von 1987 nicht enthalten**, möglicherweise
  erst in späterer MBX-Firmware. Gegen `pk232_mnemonic_table.txt` prüfen;
  ohne Beleg nach der Grundregel verfahren (nicht hochladen, Backlog).

### Commits

je Datei ein Commit:

```
Config: packet access filters and flags (fields + INI)
HF packet params dialog: wire access filters and flags
Params uploader: send access filters and flags
```

---

## P13.4 — Ehrliche Rückmeldung nach dem Dialog

`main_window._on_params_hf_packet()` loggt nach OK
„HF Packet parameters updated". Das legt nahe, der TNC sei aktualisiert —
tatsächlich ändert sich nur die Konfiguration; der TNC erfährt es erst beim
nächsten Init, weil der Uploader nur vor dem Eintritt in den Host Mode läuft.

Meldung ändern in:

```
[SYS] HF Packet parameters saved — sent to TNC on next initialisation
```

Gleiche Korrektur für die übrigen Parameterdialoge mit derselben
Formulierung. Ob die Parameter künftig auch während einer laufenden
Sitzung per Host-Mode-Mnemonic nachgeladen werden sollen, ist **nicht**
Teil dieses Pakets — als eigener Backlog-Punkt eintragen.

**Commit:** `MainWindow: parameter dialogs report when changes reach the TNC`

---

## P13.5 — Dokumentation

### `CLAUDE.md`

Den Fallstrick aus P12 um Glied (4) erweitern: die Kette hat vier Glieder,
und der Uploader liest nur Config-Felder, nie Widgets. Ein Parameter ohne
Eintrag in `_build_commands()` ist im Dialog, in der Config und in der INI
vollständig vorhanden und erreicht den TNC trotzdem nie. Test D prüft das.

Außerdem: die Befundlage zu `ACRPACK`/`AERPACK` und `TXSMT` festhalten.

### `Testplan.md`

**T107 — Upload-Abdeckung** (automatisch, Test D)
Verweis auf den Test plus die Befunde des ersten Laufs.

**T108 — Zugriffsfilter am Gerät** (Hardware, Status OPEN)
1. `CFROM YES <eigene Zweitstation>` setzen, Init
2. Connect von der Zweitstation → wird angenommen
3. Connect von einer anderen Station → wird abgewiesen
4. `CFROM ALL` zurücksetzen

**T109 — Log-Meldung nach Dialog**
Parameter ändern, OK → Meldung nennt den nächsten Init als Zeitpunkt.

### `Backlog.md`

- Befunde aus der Befehlsprüfung (`TXSMT`, ggf. `MBELL`, ggf. `ACRPACK`)
- Laufzeit-Upload von Parameteränderungen im Host Mode (eigener Punkt)
- Die übrigen Felder der P12-Tabelle bleiben dort stehen

**Commit:** `Docs: upload coverage, access filters, tests T107-T109`

---

## Definition of Done

- `python -m pytest` grün, Test D eingeschlossen
- Test D war beim ersten Lauf **rot** und hat die erwarteten Felder genannt
  (Bericht im Commit-Text von P13.1)
- Jeder neu hochgeladene Befehlsname ist im Commit-Text mit seiner Quelle
  belegt (Mnemonic-Tabelle oder TRM)
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"