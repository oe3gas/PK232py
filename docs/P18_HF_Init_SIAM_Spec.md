# Claude Code Prompt — P18: HF-Init ergänzen, SIAM-Ergebnisse zusammensetzen

> Ablage: `docs/P18_HF_Init_SIAM_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher `CLAUDE.md`, `Backlog.md`, `Testplan.md` lesen.

---

## Hardwarebefunde vom 22.09.2026

### T111 — PASS
`PX Y` schaltet PASSALL (`PXN` → `PXY`), `PS` bleibt `$16`. Wiederherstellung
auf `N` bestätigt. Der P16-Fix ist am Gerät belegt.

### T112 — FAIL, Lücke bestätigt
Gesendete Frame-Folge (aus den echten Modusklassen, Reihenfolge wie
`_on_mode_selected()`):

```
PA · VH Y · HB 1200 · MX 4 · SL 10 · MN Y      (VHF aktivieren + init)
VH N                                           (VHF verlassen)
PA · VH N · HB 300 · MN Y                      (HF aktivieren + init)
```

Ergebnis: `SLOTTIME` vorher 30, danach **10** → die VHF-Slottime bleibt auf
HF stehen. **Beweiskräftig ist nur SLOTTIME**: `MAXFRAME` stand schon vor dem
Test auf 4 (= VHF-Wert), das Ergebnis 4 sagt also nichts. Der Mnemonic `MX`
ist damit am Gerät **noch nicht belegt**.

Nebenbefund: `VH N` wird doppelt gesendet (Verlassen von VHF und HF-Init).
Harmlos, nicht ändern.

### T113 — SIAM: Frame-Typ und Format geklärt
Referenzsignal: RTTY 50 Bd, 450 Hz Shift. Erfasste Ergebnisse:

```
$50 ch0  "0.12: 248 baud, "      $50 ch0  "Baudot, RXRev OFF\r\n"
$50 ch0  "0.32: 50 baud, "       $50 ch0  "Baudot, RXRev ON\r\n"
$50 ch0  "0.73: 50 baud, "       $50 ch0  "Baudot, RXRev ON\r\n"
$50 ch0  "0.33: 51 baud, "       (Rest nach Ablauf der 60 s abgeschnitten)
```

- Ergebnisse kommen als **`$50` LINK_MSG auf Kanal 0**, **nie** als
  `$4F` CMD_RESP
- **jedes Ergebnis ist auf zwei Frames verteilt**, abgeschlossen mit `\r\n`
- Format: `<Konfidenz>: <Baud> baud, <Betriebsart>, RXRev <ON|OFF>` —
  entspricht dem Mockup, **nicht** dem STABO-Beispiel `BAUDOT 45 170`
- der TNC analysiert **fortlaufend**, etwa alle 10 s ein neues Ergebnis
- Erkennung korrekt: 50 Bd Baudot, beste Konfidenz 0,73; bei 450 Hz Shift
  ohne `WIDESHFT`

### Hardware: keine Pufferbatterie
Der TNC hat keine Pufferbatterie. Nach jedem Ausschalten steht er auf
Werkseinstellung (`MYCALL PK232`). Der Init ist damit die einzige Quelle der
TNC-Konfiguration, und der MailDrop-Inhalt geht bei jedem Ausschalten
verloren.

---

## P18.1 — `src/pk232py/modes/packet_hf.py`: HF-Init setzt MX und SL

**Regel:** Jeder Parameter, den ein Band beim Aktivieren setzt, muss das
andere Band ebenfalls setzen. Sonst bleibt der Wert des zuletzt aktiven
Bandes stehen. VHF setzt `HB`, `MX`, `SL` — HF setzt bisher nur `HB`.

`HFPacketMode.get_init_frames()` um `MX` und `SL` ergänzen, **mit den Werten
aus der HF-Konfiguration** (`hf_packet.maxframe`, `hf_packet.slottime`),
nicht fest eingetragen. Falls `HFPacketMode` die Konfiguration bisher nicht
kennt: den Weg wählen, auf dem der Modus schon heute andere Werte bekommt,
und im Commit-Text begründen.

Mnemonics: `MX` = MAXFRAME, `SL` = SLOTTIME (TRM 4.2.2). `SL` ist durch T112
am Gerät belegt; `MX` wird es durch die Wiederholung von T112 (P18.3).

`VHFPacketMode` muss weiterhin **nicht** `super().get_init_frames()`
aufrufen (bekannte Falle, siehe `CLAUDE.md`) — die neuen Frames dürfen dort
nicht versehentlich mit hineinrutschen.

Unit-Test: nach `VHF → HF` enthält die HF-Folge `MX` und `SL` mit den
Config-Werten; die VHF-Folge enthält weiterhin `VH Y` und kein `VH N`.

**Commit:** `HFPacketMode: reset MAXFRAME and SLOTTIME from HF config`

---

## P18.2 — `src/pk232py/modes/signal_analysis.py`: Ergebnisse zusammensetzen

### CMD_RESP meldet keine Ergebnisse mehr

SIAM-Ergebnisse kommen nie als CMD_RESP (T113). Der CMD_RESP-Zweig
protokolliert nur noch auf `debug`-Ebene und ruft **nie** `on_result()`
auf. Damit ist der P16.3-Befund (liegengebliebene Antworten als Ergebnis
gemeldet) ohne jede Annahme über SIAM-Präfixe erledigt.

### LINK_MSG-Fragmente sammeln

```python
self._siam_buffer: str = ""
```

- LINK_MSG-Text an `_siam_buffer` anhängen
- erst bei `\r\n` bzw. `\n` die vollständige Zeile auswerten und
  `on_result()` **einmal** mit der ganzen Zeile aufrufen
- Puffer beim Aktivieren des Modus leeren (`get_activate_frames()` bzw.
  der vorhandene Aktivierungspfad), damit ein abgebrochenes Fragment nicht
  in die nächste Analyse rutscht
- Schutz gegen Endlospuffer: wächst der Puffer über 200 Zeichen ohne
  Zeilenende, verwerfen und `warning` loggen

### Strukturierte Auswertung

Zusätzlicher Callback, `on_result` bleibt für Rückwärtskompatibilität:

```python
@dataclass
class SiamResult:
    confidence: float     # 0.73
    baud: int             # 50
    mode: str             # "Baudot"
    rxrev: bool           # True für "RXRev ON"
    raw: str              # die vollständige Zeile

self.on_result_parsed: Optional[Callable[[SiamResult], None]] = None
```

Regex auf die zusammengesetzte Zeile:

```
^\s*(\d+\.\d+):\s*(\d+)\s+baud,\s*(.+?),\s*RXRev\s+(ON|OFF)\s*$
```

(Groß-/Kleinschreibung ignorieren.) Passt die Zeile nicht, nur `on_result`
mit dem Rohtext aufrufen und `info` loggen — kein Fehler, weil andere
Signaltypen (TDM, AMTOR, „Noise") ein abweichendes Format haben können,
das noch nicht gemessen ist.

### Tests

Fixtures sind die **echten Frames aus T113**, in genau der empfangenen
Reihenfolge:

- zwei Fragmente → genau ein `on_result`-Aufruf mit der ganzen Zeile
- geparst: `0.73 / 50 / Baudot / True`
- ein CMD_RESP (`HP\x00`, `PXN`, `SI\x00`) → **kein** `on_result`
- abgeschnittenes letztes Fragment (`"0.33: 51 baud, "` ohne Rest) →
  kein Aufruf
- Puffer über 200 Zeichen ohne Zeilenende → verworfen

**Commit:** `SignalMode: assemble split LINK_MSG results, ignore CMD_RESP`

---

## P18.3 — `tools/hw_check.py`: T112 eindeutig machen

Vor dem Senden der Frame-Folge `MAXFRAME` und `SLOTTIME` auf Werte setzen,
die **weder** zu HF **noch** zu VHF passen (z. B. `MAXFRAME 2`,
`SLOTTIME 20`), damit jede der beiden Ursachen im Ergebnis sichtbar wird.
Diese Vorbelegung gehört mit in die Wiederherstellung.

Auswertung erweitern: `MAXFRAME` und `SLOTTIME` getrennt beurteilen und
getrennt ausgeben — ein gemeinsames PASS/FAIL hat bei diesem Lauf die
Aussagekraft von MAXFRAME überdeckt.

**Commit:** `Tools: t112 starts from neutral values, judges MX and SL separately`

---

## P18.4 — Dokumentation

### `CLAUDE.md`

- Hardwareabschnitt: **keine Pufferbatterie** — der TNC steht nach jedem
  Einschalten auf Werkseinstellung. Der Init ist die einzige
  Konfigurationsquelle; MailDrop-Inhalt geht beim Ausschalten verloren.
- SIAM-Abschnitt ersetzen: `$50` LINK_MSG auf Kanal 0, auf zwei Frames
  verteilt, Format mit Beispiel, fortlaufende Analyse etwa alle 10 s.
  Den Modul-Docstring von `signal_analysis.py` im selben Zug korrigieren
  (gehört in den P18.2-Commit).
- Neue Regel bei den Packet-Fallstricken: jeder Parameter, den ein Band
  setzt, muss auch das andere setzen (T112).

### `Testplan.md`

- **T111** PASS, 22.09.2026
- **T112** FAIL, 22.09.2026 — SLOTTIME-Übernahme belegt, MAXFRAME nicht
  aussagekräftig; Wiederholung nach P18
- **T113** Messung abgeschlossen, Befunde wie oben; neuer Fall für den
  SIAM-Screen am Gerät nach P18.2 (zusammengesetztes Ergebnis erscheint
  einmal, nicht in zwei Hälften)

### `Backlog.md`

- MailDrop: **Sichern der Mailbox auf Platte und Zurückladen beim Start**
  als Pflichtfunktion eintragen (Begründung: keine Pufferbatterie), nicht
  als Komfortfunktion
- `MTEXT`-Überschreibungsfrage aus P15 schließen: nach dem Einschalten gibt
  es keine TNC-eigenen Werte zu bewahren
- Die 21 zurückgestellten Upload-Felder aus P13 mit dem Hinweis versehen,
  dass sie ohne Pufferbatterie nach jedem Einschalten auf Werkswert stehen
- SIAM-Screen: fortlaufende Ergebnisse — anzeigen, welches das aktuelle
  bzw. sicherste ist; „OK → in erkannte Betriebsart wechseln" braucht eine
  Regel, welches Ergebnis gilt

**Commit:** `Docs: T111-T113 results, no RAM battery, SIAM format`

---

## Definition of Done

- `python -m pytest` grün, T113-Fixtures eingeschlossen
- Kein `on_result()`-Aufruf aus dem CMD_RESP-Zweig mehr
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"
- Danach vom Operator: `python tools/hw_check.py --port COM6 t112` erneut
  — erwartet MAXFRAME und SLOTTIME auf den HF-Werten der Konfiguration