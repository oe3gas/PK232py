# Claude Code Prompt — P47: Link-Meldungen gehören in ihren Kanal

> Ablage: `docs/P47_Link_Message_Routing_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher `CLAUDE.md` (Kanalmodell), `Testplan.md` (T100, T102) lesen.

---

## Befund (25.09.2026, Screenshot)

Auf dem UI-Chip (Kanal 0) erscheint:

```
*** Retry count exceeded ****** 25-Sep-26  16:22:06  DISCONNECTED: OE3XTC ***
```

Die Meldung gehört zu **Kanal 1**, wo der Connect lief.

### Die Kanalnummer ist vorhanden

`HFPacketMode._handle_link_msg()` liest sie aus dem CTL-Nibble des
`$5x`-Frames und ruft `on_link_message(ch, text)`. Zwei Verbraucher
nutzen sie bereits kanalbezogen: `_make_channel_state_handler()` (Chips,
MHEARD) und die Button-Freigabe in `_make_link_handler()` (T102).

Verloren geht sie erst im dritten: `_on_mode_link_message(msg)` bekommt
**nur den Text** und schreibt ihn ins RX-Fenster des gerade sichtbaren
Kanals.

**Nicht** über das Rufzeichen zuordnen: `Retry count exceeded` enthält
keines, und dieselbe Station kann auf zwei Kanälen liegen.

---

## P47.1 — Anzeige kanalbezogen

`_make_link_handler()` gibt die Kanalnummer an die Anzeige weiter.

- Kanal **0–9** → `screen.append_channel_data(channel, text)`; damit
  greift die ALL/CH-Filterung von selbst (T100)
- Kanal **15** (`$5F`, nicht kanalbezogen — etwa die Datenquittung
  `XX\x00`) → **nicht** in einen Kanal schreiben; siehe P47.2
- Betriebsarten ohne Kanäle (AMTOR, PACTOR) rufen weiterhin mit einem
  Argument auf; dort bleibt alles wie bisher

Die Meldung wird als TNC-Meldung kenntlich gemacht, nicht als empfangener
Text: eigene Farbe (die bestehende semantische Farbe für Systemmeldungen)
und das vorhandene `*** … ***`-Format bleiben.

`_set_status()` bleibt unverändert **ereignisbezogen** — es zeigt weiter
jede Meldung, unabhängig vom sichtbaren Kanal (Begründung steht bereits
im Code, T102).

**Commit:** `Packet screen: link messages appear in their own channel`

---

## P47.2 — Optionale Zweitanzeige

Manche Meldungen sollen sichtbar sein, auch wenn man gerade auf einem
anderen Kanal steht.

- neue Einstellung im Packet-Parameterdialog, Abschnitt Anzeige:
  **„Show TNC link messages in the UI channel"**, Standard **aus**
- ist sie an, erscheint **jede** Link-Meldung zusätzlich im UI-Kanal,
  mit Kanalangabe im Text: `[ch1] *** Retry count exceeded ***`
- Meldungen ohne Kanalbezug (Kanal 15) erscheinen **immer** im UI-Kanal,
  unabhängig von der Einstellung — sie haben sonst keinen Ort
- PC-seitige Einstellung: in `UPLOAD_EXEMPT` aufnehmen, Begründung
  „display setting, not a TNC parameter"; die Verdrahtungsprüfung aus P12
  greift wie für jedes andere Feld

**Commits:**
```
Config: optional mirror of link messages into the UI channel
Packet params dialog: display section for link messages
```

---

## P47.3 — Tests

- Link-Meldung für Kanal 1, sichtbar ist Kanal 1 → Text erscheint
- dieselbe Meldung, sichtbar ist Kanal 0, Ansicht `CH` → Text erscheint
  **nicht**
- Ansicht `ALL` → Text erscheint mit Kanalangabe
- Kanal 15 → Text erscheint im UI-Kanal, auch bei ausgeschalteter Option
- Option an → Meldung erscheint zusätzlich im UI-Kanal, mit `[chN]`
- AMTOR/PACTOR (Aufruf mit einem Argument) → unverändertes Verhalten
- `_set_status()` zeigt die Meldung weiterhin unabhängig vom Kanal

**Commit:** `Tests: link message routing per channel`

---

## P47.4 — Dokumentation

- `CLAUDE.md`, Kanalmodell: **Jede `$5x`-Meldung trägt ihre Kanalnummer im
  CTL-Nibble.** Drei Verbraucher nutzen sie — Chips, Button-Freigabe und
  jetzt die Anzeige. Zuordnung über das Rufzeichen ist ausdrücklich
  falsch: `Retry count exceeded` enthält keines
- `Testplan.md`: neuer Fall analog zu T100/T102 — Link-Meldung erscheint
  nur im zugehörigen Kanal

**Commit:** `Docs: link messages are channel-scoped`

---

## Definition of Done

- `.venv\Scripts\python.exe -m pytest` grün
- Eine Meldung für Kanal 1 erscheint nicht mehr auf dem UI-Chip
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"
- Danach vom Operator: Connect auf ein unerreichbares Rufzeichen auf
  Kanal 1, während Kanal 0 sichtbar ist — die Meldung darf dort nicht
  erscheinen; nach Umschalten auf Kanal 1 steht sie da