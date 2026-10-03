# Claude Code Prompt — P73: Parametermaske „Packet" — HF/VHF nebeneinander, drei Spalten ohne Rollbalken, keine wirkungslosen Schalter

> Ablage: `docs/P73_Packet_Params_Dialog_Spec.md` im Repo — **ersetzt** die
> untracked liegende ältere Fassung gleichen Namens.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Grundlage: `main` @ `312f98f` (nach P72, P74). Doku nach `docs/claude/`.

---

## Wunsch des Betreibers (30.09.2026)

- Menü Parameters → „HF Packet..." heißt **„Packet..."**.
- HF- und VHF-spezifische Werte stehen in **dieser** Maske.
- Kein Rollbalken: **drei Spalten**.
- (P72) Jede Änderung wirkt sofort im TNC.

---

## Befund

### B.1 Versteckte, fest codierte VHF-Werte
`modes/packet_vhf.py::get_init_frames()` sendet bei jeder Aktivierung fest
`MX 4` (Zeile 89) und `SL 10` (Zeile 90). HF Packet sendet dagegen
`maxframe`/`slottime` aus der Konfiguration. Die Maske zeigt nur einen Satz
Werte. Wer in VHF Packet MAXFRAME einstellt, verliert ihn beim nächsten
Moduswechsel.

### B.2 `MN Y` überschreibt den eingestellten MONITOR-Wert
Beide Packet-Modi senden bei der Aktivierung `MN Y`. Handbuch (STABO,
UBIT 1): „OFF (Default): Mit MONITOR ON oder YES wird MONITOR auf 4
gesetzt." Die Maske zeigt beim Betreiber MONITOR 6 — nach jedem
Moduswechsel steht der TNC aber auf 4. Host-Setzen von `MN<Zahl>` ist auf
beiden Geräten gemessen (T151: `MN4` → `MN5`, verbose bestätigt).

### B.3 Wechselwirkung mit P72
`ParamsUploader._build_commands()` sendet MAXFRAME/SLOTTIME **ohne Band**
(HF-Werte). Ändert der Betreiber im VHF-Betrieb die HF-MAXFRAME, schickt
P72 sie sofort — und überschreibt damit den VHF-Wert im TNC.

### B.4 Wirkungslose Schalter in der Maske
Im Reiter Parameters, Spalte Flags:

| Schalter | in Config gespeichert | hochgeladen | Matrix-Kürzel |
|---|---|---|---|
| MBELL | ja | **nein** | `ME` (L) |
| MDIGI | **nein** | **nein** | `MD` (L) |
| MPROTO | **nein** | **nein** | `MQ` (L) |
| MSTAMP | **nein** | **nein** | `MS` (L) |
| PASSALL | **nein** | **nein** | `PX` (M) |
| BBSMSGS | **nein** | **nein** | `BB` (L) |
| FULLDP | **nein** | **nein** | nicht in der Matrix |

Ein Haken dort bewirkt nichts — wie die toten UBIT-Felder, die P74
entfernt hat. MPROTO und PASSALL sind für das Mitlesen wichtig.

### B.5 Heutiger Aufbau
`ui/dialogs/params_hf.py`: Titel „HF Packet Parameters", Reiter
Parameters / Message Params / Display; im Reiter Parameters eine
`QScrollArea` (Zeile 77) mit zwei Spalten (Formular, Flags). Die
Checkbox „UBIT 0 (DCD gate)" (P74) steht in den Flags.

---

## Teil A — MONITOR aus der Konfiguration statt `MN Y`

`packet_hf.py` und `packet_vhf.py`: `build_command(b'MN', str(monitor))`
statt `b'MN', b'Y'`. Wert aus `HFPacketConfig.monitor`. Docstrings
anpassen (Befund B.2, Handbuch, T151).

**Commit:** `Packet modes: send the configured MONITOR value instead of MN Y`

---

## Teil B — Band-Werte in der Konfiguration

- `HFPacketConfig`: neu `vhf_maxframe: int = 4`, `vhf_slottime: int = 10`
  (heutige feste Werte → ohne Zutun keine Änderung). `maxframe`/
  `slottime` sind die **HF**-Werte (Kommentar). INI: neue Schlüssel,
  fehlend → Standard.
- `packet_vhf.py`: `MX`/`SL` aus `vhf_maxframe`/`vhf_slottime`.
- **P72, bandbewusst:** MAXFRAME und SLOTTIME werden live nur gesendet,
  wenn das zugehörige Band aktiv ist (HF-Werte bei HF Packet, VHF-Werte
  bei VHF Packet). Sonst Meldung `[SYS] MAXFRAME (VHF) saved - applies
  when VHF Packet is selected`. Die Bandzuordnung liegt an **einer**
  Stelle (Tabelle Parametername → Band), die sowohl `changed_values` als
  auch die Moduswechsel-Frames verwenden.
- `_build_commands()` (Init-Upload) bleibt unverändert; der Moduswechsel
  setzt danach ohnehin die Werte des aktiven Bands.

**Commits:**
```
Config: VHF MAXFRAME and SLOTTIME
PacketVHF: MAXFRAME and SLOTTIME from config
ParamApplier: band values only for the active band
```

---

## Teil C — Die wirkungslosen Schalter verdrahten

- `HFPacketConfig`: Felder für MDIGI, MPROTO, MSTAMP, PASSALL, BBSMSGS,
  FULLDP (MBELL existiert). Standardwerte = heutige Vorbelegung der
  Checkboxen. INI lesen/schreiben.
- `ParamsUploader._build_commands()`: alle sieben als verbose Schalter.
- `comm/host_params.py`: neue Zeilen mit dem Matrix-Kürzel (Tabelle
  B.4); FULLDP `mnemonic=b""`. `verified_releases` **leer** — P72 meldet
  sie bis zur Messung als „not verified for Host Mode" und sie wirken beim
  nächsten Init. Der Coverage-Test erzwingt die Zeilen ohnehin.
- Danach Messung: `host_params_probe --part A --exclude IL` an Gerät A
  und B (T160, T161) — die neuen Zeilen laufen automatisch mit. Freigaben
  trägt ein Folge-Commit nach den Läufen ein.

**Commits:**
```
Config: store the Packet monitor flags
ParamsUploader: upload MBELL MDIGI MPROTO MSTAMP PASSALL BBSMSGS FULLDP
host_params: rows for the Packet monitor flags (not yet verified)
```

---

## Teil D — Maske „Packet"

- Menü „HF Packet..." → **„Packet..."**; Titel „Packet Parameters";
  Klasse `PacketParamsDialog` (Umbenennung eigener Commit, alle Aufrufer).
- Reiter **Parameters** ohne `QScrollArea`, drei Spalten:

| Spalte 1 — Link | Spalte 2 — Band & Status | Spalte 3 — Flags |
|---|---|---|
| PACLEN, TXDELAY, FRACK, RETRY, PERSIST, DWAIT, CHECK, RESPTIME, MONITOR, USERS | Tabelle **HF \| VHF**: HBAUD (300 \| 1200, nur Anzeige), MAXFRAME, SLOTTIME; darunter TXSMT, QHPACKET, QVPACKET (r/o) | alle Flags, in zwei Unterspalten falls nötig; UBIT 0 mit P74-Tooltip |

- Reiter Message Params und Display unverändert.
- Nach OK: P72 `ParamApplier` mit der Bandregel aus Teil B.

**Commits:**
```
Params: rename HF Packet dialog to Packet
Params: Packet dialog in three columns without scrolling
Params: HF and VHF values side by side
```

---

## Teil E — Tests (zuerst rot)

- `get_init_frames()` HF und VHF mit `monitor=6` → Frame `MN6`, kein `MNY`.
- VHF mit `vhf_maxframe=7` → `MX7`; ohne neue INI-Schlüssel → `MX4`, `SL10`.
- P72 im VHF-Betrieb: HF-MAXFRAME geändert → **kein** `MX`-Frame, Meldung;
  VHF-MAXFRAME geändert → `MX<wert>`.
- Jeder Checkbox-Wert der Flags-Spalte landet in der Config und in
  `_build_commands` (Round-Trip je Schalter, Liste aus dem Dialog
  abgeleitet — so fällt ein künftig toter Schalter sofort auf).
- Maske bei 100 %: kein sichtbarer vertikaler Rollbalken, alle Widgets im
  sichtbaren Bereich (Geometrie gemessen).
- Menü enthält „Packet..." und nicht „HF Packet...".

**Commit:** `Tests: Packet dialog, band values, MONITOR, monitor flags`

---

## Teil F — Hardware und Doku

- **T160 / T161:** `host_params_probe --part A --exclude IL` an Gerät A
  bzw. B (neue Flags).
- **T162** (App, Gerät B): MONITOR 6 einstellen, VHF Packet wählen, verbose
  `MONITOR` nach Leave Host Mode → 6 (heute 4). VHF-MAXFRAME 5 → nach
  Moduswechsel HF und zurück VHF → verbose `MAXFRAME` 5.
- `Testplan.md`: T160–T162 OPEN. `Backlog.md`: P73.
- `docs/claude/`: B.2 (MN Y setzt 4), B.3 (Bandregel), B.4.

**Commits:**
```
Testplan: T160 T161 T162
Docs: MONITOR and band values
Docs: add P73 spec file
```

---

## Definition of Done

- `git grep -n "b'MX', b'4'\|b'MN', b'Y'" -- src` → keine Treffer
- kein `QScrollArea` im Reiter Parameters
- jede Checkbox der Flags-Spalte ist gespeichert und hochgeladen (Test)
- neue Tests zuerst rot, volle Suite grün
- **Push nach Freigabe**, Meldung mit Hash; `.\Sources2Text.ps1`