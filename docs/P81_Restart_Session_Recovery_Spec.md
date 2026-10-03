# Claude Code Prompt — P81: Neustart von PK232PY bei laufenden Packet-Verbindungen — erst prüfen, dann initialisieren

> Ablage: `docs/P81_Restart_Session_Recovery_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Grundlage: `main` (nach P79/P80). Betreiberwunsch 03.10.2026.
> Doku nach `docs/claude/`. **Teil 0 (Messung) zuerst.**

---

## Wunsch des Betreibers

Stürzt PK232PY ab oder wird beendet, während der TNC Packet-Verbindungen
hält, beginnt der Neustart heute „bei Null". Künftig: Beim Verbinden wird
geprüft, ob in Packet aktive Sessions bestehen. **Entfällt**, wenn sich der
TNC mit Banner meldet (dann ist er gerade aufgewacht, es gibt keine
Verbindungen).

## Befund

- Der Init (Erkennungskette P43, `_init_tnc_thread`) bringt den TNC aus
  jedem bekannten Zustand in den Befehlsmodus — auch aus Converse (P66,
  `escape_converse`) und aus dem Host Mode. Verbindungen überstehen den
  Wechsel verbose ↔ Host Mode (P67 M8, T142/T143).
- Danach folgt der Parameter-Upload (Phase 2, `ParamsUploader.upload()`),
  dann ggf. der Host-Mode-Eintritt mit `CO`-Abgleich (P67).
- Die `LinkTable` startet leer. Ohne Host-Mode-Eintritt erfährt die App
  von bestehenden Verbindungen nie; im Host Mode erst nach dem Upload.
- **Ungemessen:** Was der vollständige Init-Upload (~70 Befehle, darunter
  `MYCALL`, `PACKET`, `EXPERT`, Bandparameter) mit einer **bestehenden**
  Verbindung macht. T152 zeigt nur, dass sieben Parameter im Host Mode bei
  bestehender Verbindung angenommen werden; das TRM nennt für manche
  Befehle „not while connected" (`$09`).
- Gemessen und vorhanden: verbose `CSTATUS` liefert alle zehn Kanäle mit
  Partner und I/O-Markierung (T141/T142), Parser
  `comm/link_status.parse_cstatus()`, `LinkTable.on_verbose_cstatus()`.

---

## Teil 0 — Messung: `hw_check.py restart_probe` (T168, Gerät B, PC 1 + PC 2)

Simuliert den Absturz und den Neustart **mit dem Init der App**:

1. PC 1: Verbindung zur TinyBox `OE3GAS-1` auf Kanal 1 (Host Mode,
   `cmd_connect`), PC 2: QtTermTCP `OE3GAS-2` ruft an (landet auf 0).
   Danach verbose bleiben bzw. einmal Host Mode und **ohne Aufräumen** den
   Port schließen („Absturz") — beide Varianten: (a) TNC im verbose
   Befehlsmodus, (b) TNC im Host Mode, (c) TNC in Converse auf Kanal 0.
2. Port neu öffnen und **genau** den Init der App fahren
   (`SerialManager`-Erkennungskette + `ParamsUploader.upload()`), jede
   Antwort des Uploads mitschreiben.
3. Danach `CSTATUS`: Verbindungen noch da? Je Upload-Befehl: Antwort
   (`was/now`, `?…`, Fehlertext).
4. PC 2: in QtTermTCP eine Zeile senden → kommt sie an?
5. Aufräumen: `DI` auf den verbundenen Kanälen.

Ergebnis je Variante: `links_before`, `links_after`, Liste der Upload-
Befehle mit Ablehnung. Mit `operator_step()`.

**Commit:** `hw_check: restart_probe - app init with live links`

Die Teile A–C erst nach T168; ergibt T168, dass der Upload Verbindungen
trennt oder Befehle ablehnt, bestimmt das Teil B.

---

## Teil A — Prüfung beim Verbinden

In `SerialManager` bzw. dem Init-Ablauf, **direkt nach** der
Erkennungskette und **vor** dem Upload:

- War ein Banner da (`fresh_boot_defaults` / Banner-Release) → keine
  Prüfung (Betreibervorgabe).
- Sonst: verbose `CSTATUS` → `parse_cstatus()` → `LinkTable.
  on_verbose_cstatus()`; zusätzlich `OPMODE` und `VHF` lesen (Betriebsart
  und Band der bestehenden Verbindungen).
- Ergebnis als `[SYS]`-Zeile: „2 active connections found: ch0 OE3GAS-2,
  ch1 OE3GAS-1 (VHF Packet)" bzw. „no active connections".

**Commit:** `Init: check for live Packet links when the TNC was already awake`

---

## Teil B — Upload bei bestehenden Verbindungen

Abhängig von T168:
- Trennt oder stört der Upload nichts → normal hochladen.
- Sonst: bei gefundenen Verbindungen nur die Befehle senden, die T168 als
  unschädlich belegt; die übrigen zurückstellen mit Hinweis
  „N parameters deferred until all connections are closed" und
  Statusfeld „TNC differs from parameters" (P72). Nach dem Ende der
  letzten Verbindung (`LinkTable`-Ereignis) nachholen.

**Commit:** `Init: parameter upload respects live links`

---

## Teil C — Ansicht

- Gefundene Verbindungen → Betriebsart HF/VHF Packet entsprechend `VHF`
  wählen (`LinkTable.mode_name`); die Packet-Maske zeigt die Chips
  verbunden, den I/O-Kanal als sichtbaren Kanal.
- Stand der TNC in Converse (`CSTATUS` I/O-Kanal verbunden und vorher
  Converse erkannt) → nach dem Init wieder `CONVERSE` nur nach P67-Regel
  (verbundener I/O-Kanal). Sonst Befehlsmodus.
- Mit Host-Mode-Verbindungsart: anschließend Host-Mode-Eintritt wie
  gewohnt (P67 `CO`-Abgleich bestätigt).

**Commit:** `MainWindow: show live links found at start-up`

---

## Teil D — Tests (zuerst rot)

- Kein Banner, `CSTATUS` mit Kanal 0 und 1 verbunden → `LinkTable` hat
  beide verbunden, `[SYS]`-Zeile, Packet-Maske aktiv (heute: leer = rot).
- Banner vorhanden → **kein** `CSTATUS`.
- Teil B gemäß T168 (Testfälle aus den echten Log-Zeilen).
- Kein Klingeln (P76) für gefundene Verbindungen — sie sind nicht neu.

**Commit:** `Tests: live links found at start-up`

---

## Teil E — Hardware T169 (App, Gerät B)

1. Zwei Verbindungen wie in Teil 0 aufbauen, PK232PY über den Task-Manager
   beenden, neu starten → beide Chips verbunden, Meldung, keine Glocke.
2. Dasselbe, aber PK232PY normal beenden.
3. Gegenprobe: TNC aus/ein, PK232PY starten → keine Prüfung, Banner.

---

## Definition of Done

- T168 gemessen, bevor Teil B festgelegt wird
- rote Tests vorher nachgewiesen, volle Suite grün
- `Testplan.md`: T168, T169 OPEN; `Backlog.md`: P81
- **Push nach Freigabe**; `.\Sources2Text.ps1`