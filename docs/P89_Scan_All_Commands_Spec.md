# Claude Code Prompt — P89: Scanner prüft **alle** Befehle — auch Moduswechsel, Aktionen und „gefährliche"

> Ablage: `docs/P89_Scan_All_Commands_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Grundlage: `main` @ `b3db915` (nach P88 + Folgen). Doku nach `docs/claude/`.

---

## Vorgabe des Betreibers (06.10.2026)

- Der Scanner läuft **immer** an einem TNC, der **nicht senden kann**: kein
  Funkgerät angeschlossen. Aussendung ist also kein Risiko.
- Deshalb sollen **alle** Befehle gescannt werden, auch die 37, die heute
  nie gesendet werden (`danger`, `action_tx`, `mode`, `NEVER_AUTO`).
- Bei Befehlen, die Probleme machen können (z. B. `RESTART`), ist das
  **Verhalten** besonders interessant — es soll gemessen und festgehalten
  werden, nicht vermieden.

## Befund

- `tools/pk232_fw_scan.py --plan` listet die 37 nie gesendeten Befehle.
- Bekannte Wirkungen (Juli-Lauf, Gerät A): `TRANS` und `CALIBRATE` ließen
  sich mit schnell gesendetem Ctrl-C **nicht** verlassen; die Sitzung war
  verloren.
- Handbuch (STABO, Kap. 4 „TRANSPARENT-Modus"): Zurück in den Befehlsmodus
  durch **dreimal** das COMMAND-Zeichen innerhalb von `CMDTIME` (Default
  1 s). Der Juli-Lauf sandte Ctrl-C ohne Pause davor — das genügt offenbar
  nicht.
- Handbuch (STABO, Kap. 3): `CALIBRATE` — `K` tastet, Leertaste wechselt
  Mark/Space, nach **60 s** automatisch zurück auf Empfang. Wie man den
  Modus verlässt, steht dort nicht; zu messen.
- Kein Gerät hat eine Pufferbatterie - aber **Aus- und Einschalten stellt NICHT immer den Werkszustand her**
  (korrigiert 07.10.2026, P89b: nach kurzer Pause blieb der Speicher erhalten, Banner ohne Zusatzzeile,
  `MYSELCAL` blieb `NONE`; erst nach längerer Pause kam zuerst `PK-232M is using default values.` und
  `MYSELCAL` war `none`). Werkszustand gilt nur, wenn diese Zeile vor dem Banner kam
  (`constants.is_factory_banner()`, Geräte A/B: `PK-232M …`, Gerät C: `PK-232 …` ohne M). `RESET` bleibt der
  sichere Weg zum Werkszustand.

---

## Teil A — Vorbedingung, nicht abschaltbar

Vor jedem Lauf mit riskanten Befehlen (`--all`): Schrittanweisung
(`operator_step`), Betreiber bestätigt **einzeln**:
1. „No radio is connected to the TNC (or only a dummy load)."
2. „I am at the TNC and can power-cycle it when asked."
Ohne beide Bestätigungen: Abbruch, Exit-Code 5.

**Commit:** `tools: pk232_fw_scan --all requires an operator check`

---

## Teil B — Ablauf für riskante Befehle

Neue Option `--all`. Die heutigen 172 Abfragen laufen wie bisher **zuerst**.
Danach jeder riskante Befehl **einzeln**, vom harmlosen zum heikelsten,
jeweils:

1. **Ausgangszustand prüfen**: `cmd:` erreichbar (sonst Wecken wie die App).
2. **Befehl senden** (Name, ohne Argument; Zeilenende `\r`), danach
   **3 s** alles mitschreiben, was der TNC sendet (roh, mit Zeitstempeln).
3. **Zurück in den Befehlsmodus** nach dem für diese Art hinterlegten
   **Rückweg** (Teil C), Schritt für Schritt, jeder Schritt mit Ergebnis
   im Log.
4. **Klappt kein Rückweg**: `operator_step` „Switch the TNC off, wait at least 10 seconds, switch it on."
   (P89b; die **10 s sind ein Startwert, nicht gemessen**), danach Wecken wie die App und Banner lesen
   (`power_cycle_and_check()`); fehlt die Zeile `PK-232M is using default values.` im Banner, meldet der
   Scanner „TNC kept its settings - switch off longer and repeat“ und zeigt den Schritt erneut (3 Versuche);
   nach dem dritten: „TNC keeps its settings (RAM battery?) - factory state not reached“ (auch im Log), kein vierter
   Versuch, der Lauf geht weiter. Ergebnis `needs_power_cycle`. Dieser Schritt ist **nur** für einen TNC, der nicht mehr
   antwortet - nie, um den Werkszustand absichtlich herzustellen (Gerät mit RAM-Batterie, P90). Ein nicht gesetztes
   `MYSELCAL` wird nur abgefragt und nie gesetzt (kein Befehl löscht es, A und B).
5. Nach jedem riskanten Befehl: `OPMODE` und `MYCALL` abfragen und
   protokollieren (hat der Befehl Modus oder Einstellungen verändert?).
   War ein Aus-/Einschalten nötig: MYCALL aus der Konfiguration neu setzen.

Ergebnis je Befehl (neue Klasse `Behaviour`): `exists` (yes/no aus der
Antwort: `?What?` = no), `effect` (z. B. „enters transparent mode",
„keys PTT", „changes OPMODE to BAudot", „prints banner", „no output"),
`recovery` (welcher Rückweg wirkte, oder `needs_power_cycle`), Rohantwort.

**Commit:** `tools: pk232_fw_scan --all probes mode, action and danger commands one by one`

---

## Teil C — Rückwege, eine Tabelle

In `pk232_fw_scan.py` **eine** Tabelle Art → Rückwege in Reihenfolge:

| Art | Rückwege (der Reihe nach probieren) |
|---|---|
| `mode` (BAUDOT, AMTOR, SIGNAL …) | `PACKET\r` · Ctrl-C |
| `action_tx` (XMIT, ARQ, FEC, CONNECT, PTCONN …) | Ctrl-C · `RCVE\r` · `DISCONNE\r` · `PACKET\r` |
| `TRANS` | 1,5 s Pause · 3 × Ctrl-C im Abstand 0,2 s · 1,5 s Pause (Handbuch) · dann Ctrl-C |
| `CALIBRATE` | `Q` · Ctrl-C · 65 s warten (Handbuch: nach 60 s automatisch Empfang) · Ctrl-C |
| `CONVERSE` | Ctrl-C (wie `escape_converse()` der App) |
| `RESTART`, `RESET`, `REINIT` | auf Banner warten · `*` falls kein Banner · danach MYCALL neu setzen |
| `HOST` (falls in der Liste) | Rückweg wie die App (`HOST OFF`-Frame) |
| sonstige `danger` | Ctrl-C · `\r` |

Die Tabelle ist **Messgegenstand**: Welcher Rückweg wirkte, wird je Befehl
und Firmware festgehalten.

**Commit:** `tools: pk232_fw_scan recovery table per command kind`

---

## Teil D — Ergebnisse in die Matrix

- `fw_<release>` / `ev_<release>` wie bisher (yes/no + Beleg).
- **Neue Spalten** `fx_<release>`: Wirkung und Rückweg in Kurzform, z. B.
  `transparent; exit 3xCtrl-C/CMDTIME` oder `power-cycle needed`.
- `--update-matrix` füllt auch `fx_`-Zellen nur, wenn sie leer sind;
  Widerspruch → Abbruch mit Liste (wie bisher).
- `gen_command_matrix.py` zeigt die Wirkung in `COMMAND_MATRIX.md`.

**Commits:**
```
data: effect columns in the command matrix
tools: --update-matrix fills effect cells
```

---

## Teil E — Tests (zuerst rot)

Mock-TNC mit Verhalten je Art: Transparentmodus, der nur auf 3 × Ctrl-C mit
Pausen reagiert; Calibrate, der erst nach `Q` oder 60 s zurückkehrt; ein
Befehl, nach dem der Mock stumm bleibt (→ `needs_power_cycle`, der Test
simuliert die Betreiberbestätigung). Prüfen: Reihenfolge der Rückwege,
Protokollierung jedes Schritts, `needs_power_cycle` statt Hängenbleiben,
Abbruch ohne Betreiberbestätigung, `fx_`-Zellen nur bei leerem Feld.

**Commit:** `Tests: scanning risky commands`

---

## Teil F — Läufe

T182 Gerät A, T183 Gerät B, T184 Gerät C — je `--all --update-matrix`,
**ohne Funkgerät**. Der Betreiber bleibt am Gerät.

---

## Definition of Done

- `--plan` zeigt bei `--all` keine ausgelassenen Befehle mehr (außer solchen,
  die der Betreiber ausdrücklich ausschließt — keine vorgesehen)
- jeder riskante Befehl einzeln, mit Rückweg und Wirkung im Log
- neue Tests zuerst rot, volle Suite grün
- `Testplan.md`: T182–T184 OPEN; `Backlog.md`: P89
- **Push nach Freigabe**; `.\Sources2Text.ps1`