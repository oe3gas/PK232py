# Claude Code Prompt — P70: Kanalleiste `MON · 0 · 1 · … · 9` — Kanal 0 wird ein normaler Kanal

> Ablage: `docs/P70_Channel_Bar_MON_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Grundlage: `main` @ `88d4612`, Läufe T146/T147 vom 30.09.2026,
> **Gerät B, Release 01.AUG.91** (Banner in beiden Logs:
> `20260930_210627_channel_probe.log`, `20260930_212141_channel_probe.log`).
> Betreiberentscheid 29.09.2026: **Vorschlag 1** — eigener MON-Chip,
> daneben die Kanäle 0–9 eins zu eins wie im TNC.
> Doku-Hinweise gehören nach `docs/claude/` (Regel aus `CLAUDE.md`).

---

## Befund

### Messbefunde (Gerät B)

| # | Aussage | Beleg |
|---|---|---|
| F1 | Daten auf freiem Kanal 3 und 9 → UI-Frame über den UNPROTO-Pfad | T146 B.1, B.2 PASS |
| F2 | Dasselbe auf Kanal 3, während Kanal 0 mit der TinyBox verbunden ist; gleichzeitig läuft die Verbindung auf Kanal 0 normal (`\r` → Prompt auf `$30`) | T146 B.3 PASS, Log 21:09:09 |
| F3 | Eingehende Verbindung landet auf dem **niedrigsten freien** Kanal: erster Anrufer Kanal 0, zweiter (bei `USERS 10`) Kanal 1 | T147 C.1, C.3.1, C.3.2 |
| F4 | Bei `USERS 1` wird der zweite Anrufer abgewiesen (auf der Luft `DM`, Betreiber-Mitschnitt Direwolf); der Host erhält `$50 "Connect request: OE3GAS-3\r\n"` | T147 C.2, Log 21:24:29 |
| F5 | `USERS` steht auf 1 (Wert aus `HFPacketConfig.users`, Standard 1) | beide Logs, Abfrage vorab |
| F6 | Nach `DI` meldet `CO` kurzzeitig Zustand 4 (Trennung läuft), dann frei | T146 21:09:36, T147 21:25:20 |

Aus P67 (Gerät B) weiter gültig: verbose aufgebaute Verbindungen liegen auf
Kanal 0 (M3); `CO` liefert Zustand und Partner je Kanal (M2).

### Code-Befund
`UI_CHANNEL = 0` (`ui/screens/packet_screen.py:185`) steht für drei
verschiedene Dinge zugleich:

1. **Anzeige:** das RX-Dokument für Monitor, Unproto und Systemmeldungen
   (`_rx_docs[UI_CHANNEL]`, Zeilen 1645–1680; `main_window.py:2056–2068`).
2. **Senden:** Unproto geht auf TNC-Kanal 0 (`main_window.py:4369–4386`).
3. **Zustandssperre:** Kanal 0 kann nie einen Verbindungszustand haben
   (`set_channel_state()`, Zeile 600; Chip-Füllfarbe Zeile 876–879;
   Kontextmenü 401, 807; Anzeige „UI" Zeile 1565).

26 Stellen außerhalb der Tests. F3 zeigt: Schon der **erste** eingehende
Anruf ist mit Punkt 3 unsichtbar — nicht nur der verbose Fall aus T144.

---

## Zielbild

```
[ MON ] [ 0 ] [ 1 ] [ 2 ] … [ 9 ]
```

- **MON** ist kein TNC-Kanal. Er zeigt Monitor (`$3F`), Unproto (eigene
  gesendete UI-Frames), Systemmeldungen und Hinweise wie abgewiesene
  Anrufe. Eingabefeld dort = Unproto senden.
- **0–9** sind genau die TNC-Kanäle, alle gleich behandelt: frei,
  rufend, verbunden, unbestätigt (P67), trennend (neu, F6), fehlgeschlagen.
- **Unproto** geht über den **niedrigsten freien** Kanal laut
  `LinkTable` (F1, F2). Sind alle zehn belegt: Senden gesperrt, Hinweis
  „all 10 channels are connected - no free channel for unproto".

---

## Teil A — Begriffe trennen: `MON_VIEW` statt `UI_CHANNEL`

- `UI_CHANNEL` **entfällt**. Neu in `packet_screen.py`:
  `MON_VIEW = "MON"` — Schlüssel der Monitor-Ansicht (kein int, damit
  keine Verwechslung mit einem TNC-Kanal möglich ist).
- `_rx_docs` bekommt einen Eintrag `MON_VIEW`; die Kanäle 0–9 behalten
  ihre int-Schlüssel.
- Jede der 26 Stellen wird einer der drei Bedeutungen zugeordnet und
  entsprechend umgestellt; im Abschlussbericht als Tabelle *Zeile →
  Bedeutung → neue Umsetzung*.

**Commit:** `PacketScreen: MON_VIEW replaces UI_CHANNEL for the monitor view`

---

## Teil B — Kanal 0 ist ein normaler Kanal

- `set_channel_state()`: Sperre für Kanal 0 entfernt.
- Chip-Füllfarbe, Kontextmenü (Connect/Disconnect), Eingabefeld,
  Kanalbeschriftung: für 0 wie für 1–9.
- `LinkTable` ist die einzige Quelle für Chip-Zustände (P67). Der
  Chip-Zustand `disconnecting` kommt neu hinzu (CO-Zustand 4, F6);
  `decode_link_status()` liefert den Zustand bereits, die Abbildung
  Zustand → Chip liegt an **einer** Stelle (`LinkTable`), nicht in der
  Maske.
- P67-Nachtrag: `reset_channels()` bei der Aktivierung der Packet-Maske
  (`main_window.py`, Aktivierungspfad) wird ersetzt durch „alle Chips aus
  der `LinkTable` neu zeichnen". Die Maske setzt keinen Zustand mehr
  selbst.

**Commits:**
```
PacketScreen: channel 0 is a regular TNC channel
LinkTable: disconnecting state from CO state 4
MainWindow: repaint chips from LinkTable on activation instead of reset
```

---

## Teil C — MON-Chip

- Eigener Chip links vor 0, optisch abgesetzt (die bisherige
  UI-Füllfarbe `_UI_CHANNEL_FILL` wandert hierher), Beschriftung `MON`.
- Klick → Monitor-Ansicht; das Eingabefeld sendet Unproto.
- Kein Kontextmenü mit Connect/Disconnect.
- Tastatur: die bisherige Kanalwahl über Tasten (falls vorhanden) bekommt
  MON als eigene Position; im Abschlussbericht aufführen, welche Tasten
  sich verschoben haben.

**Commit:** `PacketScreen: MON chip for monitor and unproto`

---

## Teil D — Unproto über den niedrigsten freien Kanal

- `LinkTable.lowest_free_channel() -> Optional[int]` — frei heißt
  Zustand `free` (nicht `unconfirmed`, nicht `disconnecting`).
- `MainWindow`: Unproto aus der MON-Ansicht → Datenframe auf `$2n` mit
  `n = lowest_free_channel()`. `None` → nicht senden, Hinweis wie im
  Zielbild, Eingabetext bleibt stehen.
- Die MON-Ansicht zeigt jede eigene Unproto-Zeile mit dem Kanal, über den
  sie ging (`[via ch3]`), damit der Betreiber das nachvollziehen kann.
- Das bisherige Sperren des Unproto-Knopfs bei Verbindung auf Kanal 0
  (`main_window.py:4386`) entfällt.

**Commit:** `MainWindow: unproto via the lowest free channel`

---

## Teil E — Abgewiesene Anrufe sichtbar machen (F4)

- `$5n`-Text `Connect request: <CALL>` → `LinkTable` ändert **nichts**
  (kein Zustandswechsel), aber `MainWindow` schreibt in die MON-Ansicht
  und in die Statusleiste: `Incoming call from <CALL> rejected by the TNC
  (USERS <n>)`. `<n>` aus der Konfiguration (`HFPacketConfig.users`).
- Nur für diesen Text; andere `$5n`-Meldungen unverändert.

**Commit:** `MainWindow: show calls the TNC rejected`

---

## Teil E2 — `USERS` Standard 10 (Betreiberentscheid 30.09.2026)

- `config.py:102`: `users: int = 10` (Kommentar: Betreiberentscheid, F3/F4).
- `ui/dialogs/params_hf.py:109`: Spinbox-Vorgabe `spin(1, 10, 10)`.
- **Keine** Migration bestehender INI-Dateien: ein gespeicherter Wert
  (auch `users = 1`) bleibt, er kann eine bewusste Wahl sein. Der
  Hinweis aus Teil E nennt den tatsächlich hochgeladenen Wert.
- Test: frische Konfiguration ohne INI → `users == 10`, Upload enthält
  `USERS 10`; INI mit `users = 1` → bleibt 1.

**Commit:** `Config: USERS defaults to 10`

---

## Teil F — Tests (zuerst rot)

- `test_packet_screen.py`: `set_channel_state(0, connected)` → Chip 0
  „connected" (heute abgewiesen = roter Test); MON-Chip existiert, liegt
  vor 0, hat kein Connect-Menü; MON-Ansicht nimmt Monitorzeilen auf.
- `test_link_table.py`: `lowest_free_channel()` für: alles frei → 0;
  0 verbunden → 1; 0 unbestätigt → 1; alles belegt → `None`; CO-Zustand 4
  → `disconnecting`.
- `test_main_window_packet.py`:
  - eingehende Verbindung auf Kanal 0 (`$50 CONNECTED to OE3GAS-2`) →
    Chip 0 verbunden, Partner sichtbar
  - Unproto bei Kanal 0 verbunden → Frame auf `$21`, MON zeigt `[via ch1]`
  - alle zehn verbunden → kein Frame, Hinweis
  - `$50 Connect request: OE3GAS-3` → Hinweis in MON und Statusleiste,
    kein Chip-Wechsel
  - Aktivierung der Packet-Maske mit verbundenem Kanal 0 in der
    `LinkTable` → Chip 0 bleibt verbunden (P67-Nachtrag)
- Alle bestehenden Tests, die `UI_CHANNEL` verwenden, auf `MON_VIEW`
  bzw. Kanal 0 umstellen — **nicht** löschen.

**Commit:** `Tests: MON chip, channel 0 as a regular channel, unproto channel choice`

---

## Teil G — Hardware: T148 (App, Gerät B)

Durchgang mit Schrittanweisung wie `channel_probe` (Betreiber: zwei PCs):

1. PC 1: App im Host Mode, VHF Packet. PC 2: QtTermTCP `OE3GAS-2` ruft
   `OE3GAS` an. **Erwartet:** Chip 0 verbunden, Partner OE3GAS-2.
2. PC 1: MON-Chip, Unproto-Text senden. **Erwartet:** MON zeigt
   `[via ch1]`; PC 2: Direwolf zeigt einen UI-Frame.
3. PC 2: QtTermTCP `OE3GAS-3` ruft an (USERS 10). **Erwartet:** Chip 1
   verbunden, Partner OE3GAS-3; Chip 0 unverändert OE3GAS-2.
3b. Optional, nur für die Anzeige abgewiesener Anrufe: in den Parametern
   USERS auf 1, erneut hochladen, beide trennen, OE3GAS-2 und dann
   OE3GAS-3 anrufen lassen. **Erwartet:** „Incoming call from OE3GAS-3
   rejected by the TNC (USERS 1)". Danach USERS wieder auf 10.
4. PC 1: Chip 0 → Disconnect. **Erwartet:** kurz „disconnecting", dann frei.
5. PC 1: verbose, `CONNECT OE3GAS-1`, Ctrl+H. **Erwartet:** Chip 0
   verbunden mit OE3GAS-1 (der offene Punkt aus T144).

---

## Teil H — Dokumentation

- `docs/claude/`: F1–F6 als Fakten Gerät B; „`UI_CHANNEL` gibt es nicht
  mehr — Monitor ist `MON_VIEW`, Kanal 0 ist ein TNC-Kanal".
- `Backlog.md`: „Kanalleiste MON · 0–9" → erledigt (P70); T144 Schritt 3
  wird mit T148 Schritt 5 erneut geprüft.
- `Testplan.md`: T146 PASS, T147 INFO mit F3/F4 (beide Gerät B,
  30.09.2026), neu T148.

**Commits:**
```
Docs: channel model MON plus 0-9 and Device B facts
Backlog: channel bar done
Testplan: T146 T147 results, new T148
Docs: add P70 spec file
```

---

## Definition of Done

- neue Tests zuerst rot, volle Suite grün
- `git grep -n "UI_CHANNEL" -- src` → keine Treffer
- `ChannelBar.set_channel_state` wird nur aus dem `LinkTable`-Callback
  aufgerufen; `reset_channels()` nicht mehr im Aktivierungspfad
- **Push**, Meldung mit Hash; `.\Sources2Text.ps1`, „sources aktualisiert"