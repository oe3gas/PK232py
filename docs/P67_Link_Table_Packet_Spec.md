# Claude Code Prompt — P67: Verbindungstabelle — Betriebsart und Verbindungen über verbose ↔ Host Mode mitnehmen (Packet)

> Ablage: `docs/P67_Link_Table_Packet_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Grundlage: `main` @ `01362bf`, Läufe 28.09.2026 14:57–15:04, **Gerät B,
> Release 01.AUG.91** (Banner im ersten Lauf; danach „TNC was already
> awake", gleiches Gerät, kein Tausch).
> Vorgabe des Betreibers (P64): Die App führt eine eigene Verbindungstabelle
> als Parallelstatus zum TNC und nimmt Verbindungen und Betriebsart bei
> jedem Wechsel mit. **Nur Packet.** PACTOR/AMTOR folgen in einem eigenen
> Paket.

---

## Befund — was jetzt gemessen ist (Gerät B)

| # | Aussage | Beleg |
|---|---|---|
| M1 | Host-Mode-Eintritt aus Converse bei bestehender Verbindung gelingt (Handshake: `HP $00`, `OPPA`, kein Late-Entry nötig) | T141 14:57 A.4a; T143 (App) |
| M2 | Link-Status `CO` je Kanal liefert Zustand und Partner zuverlässig: verbunden `CO41000OE3GAS-1`, frei `CO00000` | T141 A.6 (3 Läufe), T142 |
| M3 | Eine verbose aufgebaute Verbindung liegt im Host Mode auf **demselben** Kanal (0) | T141 A.6 |
| M4 | Daten laufen auf `$3n` des verbundenen Kanals (`\r` auf Kanal 0 → TinyBox-Prompt auf `$30`) | T141 A.7 (3 Läufe) |
| M5 | Die VHF-Packet-Frames `PA`, `VH Y`, `HB 1200`, `MX 4`, `SL 10`, `MN Y` stören eine bestehende Verbindung **nicht**; OPMODE bleibt `PA` | T141 A.8 (3 Läufe) |
| M6 | Nach `HOST OFF` ist der verbose I/O-Kanal der Kanal des **letzten** `$4x`-Frames | T142 D.1 (3 Läufe) |
| M7 | Letzter Frame `CO` auf dem verbundenen Kanal → `CSTATUS` zeigt `IO` dort; `CONVERSE` + `\r` → TinyBox-Prompt kommt zurück | T142 D.3 (15:04:21–15:04:27) |
| M8 | Die Verbindung übersteht Host → verbose → Host | T142, T143 |
| M9 | `CHSWITCH` steht auf `$00` | T142 D.2.3 |
| M10 | Verbose Ausgaben mit Kanalbezug tragen das Präfix `NUL` + Ziffer + `:` + Leerzeichen, z. B. `\x000: ?already connected …`, `\x009: cmd:` | T141 14:59:31 |

Nicht gemessen, bewusst offen: Wann genau das Präfix aus M10 erscheint
(nur bei mehreren aktiven Kanälen? nur bei Meldungen eines anderen als des
I/O-Kanals?). Der Parser muss beide Formen verarbeiten (Teil B.3).

### Fehler in den Messwerkzeugen (aus denselben Läufen)
- **H.1** `link_carry` A.10 trennt verbose auf dem I/O-Kanal — nach A.6/A.8
  ist das Kanal 9 (M6), die Verbindung auf Kanal 0 blieb stehen. Folge: Die
  Läufe 2 und 3 bekamen `?already connected` und prüften damit **nicht**
  den Converse-Fall, sondern einen verbundenen Kanal bei Befehlsmodus. Nur
  Lauf 1 (14:57) ist ein echter Converse-Lauf.
- **H.2** `link_carry` A.9 wertet `CONNECT` ohne Argument aus — das zeigt
  den I/O-Kanal (9), nicht den verbundenen. „INCONCLUSIVE" ist ein
  Werkzeugfehler, kein TNC-Befund.
- **H.3** `link_carry_host` meldet den `CO`-Fehler `01 4F 43 4F 0C 17`
  (`CO` + `$0C`) auf einen Connect zur schon verbundenen Station nur als
  „inconclusive". Das Byte ist ein Fehlercode, nicht protokolliert als
  solcher.
- **H.4** Die TinyBox-Antwort in D.3 kam erst nach dem 2-s-Fenster (sichtbar
  im folgenden `cmd:`-Check). Das Fenster ist zu knapp.

---

## Teil A — Link-Status an eine Stelle: `comm/link_status.py`

Neues Qt-freies Modul, **einzige** Stelle für:

- `decode_link_status(ctl, data) -> LinkStatus` — aus `tools/hw_check.py`
  hierher verschieben (Dataclass statt dict: `channel`, `state`,
  `connected: bool` = `state == 5`, `v2`, `unacked`, `retries`, `conperm`,
  `partner`, `digis`), `unparsed` als eigener Fall. hw_check importiert
  von hier.
- `parse_cstatus(text) -> dict[int, (bool io, str state_text, str partner)]`
  für verbose `CSTATUS` (Format aus M2/M6-Logs).
- `split_channel_prefix(line) -> (Optional[int], str)` für M10.

`comm/serial_manager.py::_make_host_frame()`: `0x40 <= ctl <= 0x49` →
`FrameKind.LINK_STATUS` (heute `CMD_RESP`; offener Backlog-Eintrag). `0x4F`
bleibt `CMD_RESP`.

**Commits:**
```
comm: link_status module - one decoder for CO, CSTATUS and channel prefix
SerialManager: $40-$49 frames are LINK_STATUS
hw_check: use comm.link_status
```

---

## Teil B — Die Verbindungstabelle: `comm/link_table.py`

Qt-frei, reines Python, vollständig per Unit-Test prüfbar.

### B.1 Daten
```python
@dataclass
class ChannelLink:
    state: str        # "free" | "calling" | "connected" | "unconfirmed"
    partner: str = ""
    since: float = 0.0

class LinkTable:
    channels: list[ChannelLink]   # 0..9
    io_channel: int               # verbose I/O-Kanal (M6)
    converse: bool                # TNC stand in Converse (verbose)
    mode_name: Optional[str]      # zuletzt vom Betreiber gewaehlte Betriebsart
```

### B.2 Eingänge (jeder genau eine Methode)
- `on_host_link_message(ch, text)` — `$5x`, bestehende Texte
  (`CONNECTED to`, `DISCONNECTED`, `busy`, `Retry count exceeded`).
- `on_link_status(status: LinkStatus)` — `CO`-Antwort; setzt den Kanal
  **bestätigt** (`connected`/`free`).
- `on_verbose_line(line)` — `*** CONNECTED to X` → Kanal (Präfix oder
  `io_channel`) verbunden, `converse = True`; `*** DISCONNECTED: X` → frei;
  Zeile, die mit `cmd:` endet → `converse = False`.
- `on_verbose_cstatus(parsed)` — `CSTATUS`-Abgleich, setzt `io_channel`.
- `mark_unconfirmed()` — alle `connected` → `unconfirmed` (vor jedem
  Abgleich).
- `reset()` — nur bei echtem Verlust: Trennen vom TNC, neuer Banner
  (`fresh_boot_defaults`), Recovery ohne Abgleich.

### B.3 Ausgang
Beobachter-Liste (`subscribe(callback)`), Aufruf mit `(channel, ChannelLink)`
bei jeder Änderung. **Keine** Qt-Signale im Modul; `MainWindow` übersetzt.

**Commit:** `comm: LinkTable - app-side mirror of the TNC channel state`

---

## Teil C — Anbindung in `MainWindow`

### C.1 Eine Tabelle, eine Anzeige
- `MainWindow` besitzt genau eine `LinkTable`.
- `$5x`-Link-Meldungen und `LINK_STATUS`-Frames gehen **in die Tabelle**;
  die Packet-Masken (`ChannelBar.set_channel_state`) werden **nur** aus dem
  Tabellen-Callback gesetzt. Kein zweiter Zustand in der Maske.
- Neuer Chip-Zustand `unconfirmed` (gestrichelter Rand, Tooltip
  „carried over from verbose - waiting for confirmation").

### C.2 verbose → Host (`_update_host_mode_ui(True)`)
1. Betriebsart: statt fest „Baudot RTTY" → `table.mode_name`, falls
   gesetzt und Packet; sonst wie bisher Baudot. Die Moduswechsel-Frames
   dürfen bei bestehender Verbindung gesendet werden (M5).
2. `table.mark_unconfirmed()`, dann `CO` für Kanal 0–9 (M2). Antworten
   laufen über C.1 in die Tabelle. Kanal 0 **zuletzt** abfragen ist nicht
   nötig (im Host Mode ohne Bedeutung).
3. Die Maske wählt den verbundenen Kanal als sichtbaren Kanal, falls genau
   einer verbunden ist; bei mehreren den `io_channel` aus der Tabelle.

### C.3 Host → verbose (Benutzerausstieg)
- `reset_channels()` beim Verlassen **entfällt** (heute
  `main_window.py:5119–5122`). Die Tabelle bleibt.
- Vor `HOST OFF`: ist der sichtbare Kanal der Packet-Maske verbunden, als
  **letzten** `$4x`-Frame `CO` auf diesem Kanal senden (M6/M7). Dafür
  bekommt `SerialManager.exit_host_mode()` einen optionalen Parameter
  `io_channel: Optional[int]`; die Reihenfolge (erst `CO`, dann
  `HOST OFF`) liegt **in** `exit_host_mode()`, nicht beim Aufrufer.
- Nach dem Ausstieg (`exit_host_mode()` endet mit Ctrl-C → `cmd:`):
  stand vor dem Host-Eintritt `table.converse == True` **und** ist dieser
  Kanal verbunden → `CONVERSE` senden. Sonst im Befehlsmodus bleiben.
  **Nie** `CONVERSE` auf einem freien Kanal (sendet UNPROTO, P66b B.5).
- `table.io_channel` auf diesen Kanal setzen.
- Die Betriebsart wird beim Benutzerausstieg **nicht** mehr vergessen:
  vor `deactivate()` den Namen in `table.mode_name` sichern
  (heute `main_window.py:5127–5130`).

### C.4 verbose-Terminal füttert die Tabelle
Jede empfangene verbose Zeile → `table.on_verbose_line()`. Ein vom
Betreiber getipptes `CONVERSE`/`CONV`/`K` bzw. Ctrl-C ändert
`converse` erst, wenn der TNC es bestätigt (Echo ohne `cmd:` bzw. `cmd:`) —
nicht auf den Tastendruck hin.

**Commits:**
```
MainWindow: one LinkTable feeds both Packet screens
MainWindow: Host Mode entry keeps the selected Packet mode and reconciles links
SerialManager: exit_host_mode selects the verbose I/O channel via a last CO
MainWindow: Host Mode exit keeps links and returns to Converse on the connected channel
PacketScreen: unconfirmed channel chip
```

---

## Teil D — hw_check nachbessern (H.1–H.4)

- `link_carry` A.10: wie `link_carry_host` — im Host Mode `DI` auf dem
  verbundenen Kanal aus der letzten `CO`-Abfrage, **vor** dem Ausstieg.
- `link_carry` A.2: Antwort `?already connected` → `FAIL` mit Hinweis
  „disconnect the counterpart first", keine weiteren Schritte.
- A.9 und `link_carry_host` werten `parse_cstatus()` für den **verbundenen**
  Kanal aus, nicht `CONNECT` ohne Argument.
- `CO`-Antwort `CO` + ein einzelnes Byte (`$0C` in H.3) als Fehlercode
  loggen (`error_code=0x0C`), Bedeutung nicht raten.
- D.3 `CONVERSE`: Aufzeichnungsfenster 10 s statt 2 s.

**Commit:** `hw_check: link_carry cleanup, CSTATUS-based checks, CO error code`

---

## Teil E — Tests (zuerst rot)

**`test_link_status.py`** (neu): die echten Bytes aus den Logs —
`CO41000OE3GAS-1`, `CO00000`, `CO\x0c`; `CSTATUS` mit `IO` auf Kanal 0, 3,
9; Präfixzeilen `\x000: ?already connected …`, `\x009: cmd:`.

**`test_link_table.py`** (neu):
- verbose `*** CONNECTED to OE3GAS-1` → Kanal 0 verbunden, `converse`
  True; danach `cmd:` → `converse` False, Kanal bleibt verbunden
- `mark_unconfirmed()` + `CO` frei → Kanal frei; + `CO` verbunden →
  bestätigt
- Beobachter wird genau einmal je Änderung gerufen

**`test_main_window_packet.py`**:
- Host-Eintritt mit `table.mode_name == "VHF Packet"` → VHF-Packet-Maske,
  **kein** `BA`-Frame gesendet
- Host-Eintritt sendet `CO` auf 0–9; Antwort `CO41000OE3GAS-1` auf Kanal 0
  → Chip 0 „connected", Partner `OE3GAS-1`
- Benutzerausstieg ruft **kein** `reset_channels()` mehr; Chip bleibt
- Ausstieg mit verbundenem sichtbarem Kanal 0: Schreibreihenfolge
  `01 40 43 4F 17` **vor** `HOST OFF`; danach `CONVERSE` nur, wenn
  `converse` vorher True war; mit freiem Kanal nie `CONVERSE`

**`test_serial_manager.py`**: `_make_host_frame(0x43, b"CO00000")` →
`LINK_STATUS`; `exit_host_mode(io_channel=2)` schreibt `CO` auf `$42` vor
`HOST OFF`.

**Commit:** `Tests: LinkTable, link_status decoder, Host Mode carry-over`

---

## Teil F — Hardware: T144 (App, Gerät B)

1. Verbose, VHF Packet, `CONNECT OE3GAS-1`, TinyBox-Prompt abwarten.
2. Ctrl+H → **erwartet:** VHF-Packet-Maske, Chip 0 zuerst gestrichelt,
   nach dem Abgleich „connected OE3GAS-1"; `H` im Eingabefeld von Kanal 0
   senden → TinyBox-Hilfe erscheint.
3. Leave Host Mode → **erwartet:** verbose Terminal, `H` tippen → TinyBox
   antwortet (Converse auf Kanal 0 ohne weiteres Zutun).
4. Ctrl+H erneut → Chip 0 wieder verbunden; in der Maske `Disconnect` →
   Chip frei.
5. Gegenprobe: ohne Verbindung Ctrl+H und zurück → verbose im
   Befehlsmodus (`cmd:`), **kein** `CONVERSE`.
6. `link_carry` einmal nach Teil D (echter Converse-Lauf mit sauberem
   Aufräumen).

---

## Teil G — Dokumentation

- `CLAUDE.md`: Abschnitt „Link table" (eine Tabelle, Eingänge, wer sie
  zurücksetzt), M1–M10 als Known Facts Gerät B; „Channel model" auf die
  Tabelle umstellen.
- `Backlog.md`: P64 → erledigt für Packet (P67), neu „P64 für PACTOR und
  AMTOR"; „`_make_host_frame()` misclassifies LINK_STATUS" → erledigt.
- `Testplan.md`: T141 (14:57 PASS; 14:59/15:00 nur eingeschränkt gültig,
  H.1), T142 (15:02: D.1/D.3 PASS, Connect-Teil ungültig wegen
  Vorverbindung), neu T144.

**Commits:**
```
Docs: CLAUDE.md link table and Device B facts
Backlog: P64 done for Packet, PACTOR/AMTOR next
Testplan: 28.09.2026 afternoon results and T144
Docs: add P67 spec file
```

---

## Definition of Done

- neue Tests zuerst rot, volle Suite grün
- `git grep -n "reset_channels()" -- src/pk232py/ui/main_window.py` zeigt
  keinen Aufruf mehr im Host-Mode-Ausstieg
- `decode_link_status` existiert genau einmal (in `comm/link_status.py`)
- `ChannelBar.set_channel_state` wird nur noch aus dem LinkTable-Callback
  aufgerufen
- **Push**, Meldung mit Hash; `.\Sources2Text.ps1`, „sources aktualisiert"