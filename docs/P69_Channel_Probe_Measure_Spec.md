# Claude Code Prompt — P69: Messpaket `channel_probe` — Unproto auf beliebigen freien Kanälen, Kanalwahl bei eingehenden Verbindungen

> Ablage: `docs/P69_Channel_Probe_Measure_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Grundlage: `main` @ `2f87fcd` (bzw. nach P68).
> **Nur Messung** (hw_check-Regel 6). Die Umsetzung (P70) baut die
> Kanalleiste auf `MON · 0 · 1 · … · 9` um und stützt sich nur auf diese
> Befunde.

---

## Zweck und Designrahmen (Betreiberentscheid 29.09.2026)

Kanal 0 ist heute fest der „UI-Kanal" (P10): Chip 0 zeigt Monitor und
Unproto, `ChannelBar.set_channel_state()` weist jeden Zustand für Kanal 0
ab. T144 zeigte die Folge: Eine im verbose Modus aufgebaute Verbindung liegt
auf TNC-Kanal 0 (P67 M3) und ist in der Maske **unsichtbar**.

Entscheidung des Betreibers: **Vorschlag 1** — ein eigener Chip **MON**
(kein TNC-Kanal) für Monitor und Unproto, daneben die Chips **0–9 eins zu
eins** wie die TNC-Kanäle. Unproto sendet über den **niedrigsten freien
Kanal** laut Verbindungstabelle; sind alle zehn belegt, ist Unproto
gesperrt.

Dafür muss gemessen sein, was heute nur für Kanal 0 bekannt ist.

---

## Befund — bekannt und unbekannt

| Frage | Stand | Beleg |
|---|---|---|
| Daten auf **Kanal 0** unverbunden → UI-Frame über UNPROTO-Pfad | ✅ Gerät A, B | T101, T139 |
| Daten auf einem **anderen** freien Kanal (1–9) → UI-Frame? | ❓ | nie gemessen |
| Dasselbe, während auf einem anderen Kanal eine Verbindung besteht | ❓ | nie gemessen |
| Auf welchen Kanal legt der TNC eine **eingehende** Verbindung? | ❓ | nie gemessen |
| Und wenn Kanal 0 schon belegt ist? | ❓ | nie gemessen |
| Wirkung von `USERS` darauf | ❓ | App lädt `USERS` hoch (`hf_packet.users`, Standard 1) |

Wichtig für C: Mit `USERS 1` nimmt der TNC vermutlich nur **eine**
eingehende Verbindung an. Das ist eine Vermutung aus dem Parameternamen,
kein Messbefund — deshalb wird `USERS` vorab abgefragt und protokolliert,
und C.3 läuft einmal mit dem vorgefundenen Wert und einmal mit `USERS 10`.

---

## Teil A — Aufbau des Unterbefehls

`python tools/hw_check.py --port COM6 channel_probe`

- `normalize()`, VHF/1200-Prüfung wie in `link_carry` (dieselbe
  Hilfsfunktion).
- Verbose vorab abfragen und loggen: `UNPROTO`, `USERS`, `MYCALL`.
- Rückstellung per `run_with_restore()`: `UNPROTO`, `USERS`.
- Gegenstation: Direwolf am FT-818 (dekodiert **alle** Frames, auch
  I-Frames) mit TinyBox (`OE3GAS-1`) und QtTermTCP über AGW.
- Alle Eingaben des Betreibers über `read_pasted_block()` (Ende mit `.`),
  alle Aussendungen hinter `confirm_tx()`.
- Nach **jedem** Schritt im Host Mode: `CO` auf 0–9 mit
  `comm.link_status.decode_link_status()`, Ergebnis als Zeile
  `links: 0=free 1=free … ` loggen.

---

## Teil B — Unproto auf freien Kanälen

UNPROTO im Host Mode per `UN` auf `P69TST` setzen (Ziel ohne VIA —
eindeutig erkennbar, kein Digi).

- **B.1** Kanal 3, alle Kanäle frei: Datenframe `P69 B1 ch3 HH:MM:SS` auf
  `$23`. Betreiber fügt die Direwolf-Ausgabe ein.
- **B.2** Kanal 9, alle frei: `P69 B2 ch9 HH:MM:SS` auf `$29`.
- **B.3** Verbindung auf Kanal 0 aufbauen (Host `cmd_connect(0,
  "OE3GAS-1")`, auf `CONNECTED` warten), dann `P69 B3 ch3 HH:MM:SS` auf
  `$23`. Danach auf `$20` ein `\r` (erwartet: TinyBox-Prompt auf `$30`,
  Vergleich wie T141 A.7). Danach `DI` auf Kanal 0.

Reine Auswertefunktion `classify_decoder_line(pasted, src, dest, text) ->
str` mit den Ergebnissen `ui` (Zeile `SRC>DEST…:` mit dem Text, ohne
Connected-Mode-Kennung), `connected` (Direwolf-Kennzeichnung eines
I-Frames), `absent`, `unknown`. Welche Kennzeichnung Direwolf für I-Frames
ausgibt, ist **nicht** fest codiert, sondern wird aus B.3 (`\r` auf `$20`,
bekanntermaßen ein I-Frame an die TinyBox) abgeleitet und im Log
gezeigt; bis dahin `unknown`.

Ergebnis je Schritt: `PASS`, wenn `ui` und der Text exakt enthalten ist.

**Commit:** `hw_check: channel_probe B - unproto on free channels 3 and 9`

---

## Teil C — Eingehende Verbindungen

Der Betreiber ruft aus **QtTermTCP** (Rufzeichen dort z. B. `OE3GAS-2`)
`MYCALL` des PK-232 an. Das Programm zeichnet je Phase 60 s alle Frames
auf und fragt danach die Anzeige in QtTermTCP ab.

- **C.1** Alle Kanäle frei, `USERS` wie vorgefunden: Anruf. Auf welchem
  Kanal kommt `$5n CONNECTED to OE3GAS-2`? Danach `CO` 0–9.
- **C.2** Bestehende Verbindung aus C.1 **stehen lassen**, zusätzlich
  Kanal 0 belegen, falls C.1 nicht schon auf 0 lag: Host
  `cmd_connect(0, "OE3GAS-1")`. Zweiter Anruf aus QtTermTCP mit anderem
  Rufzeichen (z. B. `OE3GAS-3`): angenommen? Kanal? Was zeigt QtTermTCP
  (Busy, Verbindung, Timeout)?
- **C.3** Alle trennen (`DI` auf jeden verbundenen Kanal laut `CO`),
  `USERS 10` verbose setzen, C.2 wiederholen.
- Aufräumen: `DI` auf allen verbundenen Kanälen laut `CO`, dann
  Rückstellung.

Ergebnis `INFO` je Phase: `incoming_channel=<n>`, `accepted=<bool>`,
Betreiberangabe wörtlich.

**Commit:** `hw_check: channel_probe C - which channel an incoming connect lands on`

---

## Teil D — Tests (zuerst rot)

`test_hw_check_channel_probe.py`:
- `classify_decoder_line`: UI-Zeile mit Text → `ui`; Text fehlt →
  `absent`; unbekanntes Format → `unknown`; Zeile mit gelernter
  I-Frame-Kennung → `connected`.
- Dry-Run: kein Port, zeigt `UN P69TST`, Datenframes auf `$23`, `$29`,
  Connect auf Kanal 0, `USERS 10` in C.3, und dass jede Aussendung hinter
  `confirm_tx()` liegt.

**Commit:** `Tests: hw_check channel_probe evaluation and dry-run`

---

## Teil E — Testplan und Doku

- `Testplan.md`: **T146** `channel_probe` B (Gerät B), **T147**
  `channel_probe` C (Gerät B), OPEN.
- `tools/README.md`, Modul-Docstring: neuer Unterbefehl, nicht in `all`.
- `Backlog.md`: „Kanalleiste MON · 0–9 (P70) — wartet auf T146/T147".

**Commits:**
```
Testplan: T146 T147 channel probe
Docs: hw_check channel_probe
Backlog: channel bar MON plus 0-9 waits on P69
Docs: add P69 spec file
```

---

## Definition of Done

- neue Tests zuerst rot, volle Suite grün
- `--dry-run channel_probe` ohne Port
- kein neuer Frame-Bauer (`cmd_unproto`, `cmd_connect`, `build_ch_cmd`,
  `decode_link_status` wiederverwenden)
- **Push**, Meldung mit Hash; `.\Sources2Text.ps1`, „sources aktualisiert"