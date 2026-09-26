# Claude Code Prompt — P57: Chip-Eingabe schließt beim Wechsel

> Ablage: `docs/P57_Chip_Editor_Focus_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Beleg: Screenshot vom 26.09.2026 (Eingabe in Kanal 3 offen, Klick auf
> Kanal 4).

---

## Befund

Doppelklick auf einen freien Chip öffnet die Rufzeichen-Eingabe. `Esc`
schließt sie. **Ein Klick auf einen anderen Chip nicht:** Im Screenshot
steht der Cursor weiterhin in Kanal 3, während Kanal 4 den aktiven Rahmen
trägt. Tastenanschläge landen im Feld von Kanal 3.

**Ursache:** Die Chips sind `NoFocus` (damit die Tastatur im TX-Fenster
bleibt, P41). Ein Klick auf einen Chip nimmt dem offenen `QLineEdit`
deshalb den Fokus **nicht** — `focusOutEvent` feuert nie, und die in P42
vorgesehene Regel „Fokusverlust schließt wie `Esc`" greift nicht.

Zweiter Punkt aus demselben Screenshot: Das offene Eingabefeld hat einen
dunklen Hintergrund **ohne** den bernsteinfarbenen Rahmen, den P42 dafür
vorsieht. Der bearbeitete Chip sieht dadurch weniger aktiv aus als der
gewählte.

---

## P57.1 — Nur eine Eingabe gleichzeitig

`ChannelBar` schließt eine offene Eingabe, sobald sie an anderer Stelle
gebraucht wird. Die Leiste weiß als Einzige, welcher ihrer Chips gerade
editiert wird — dort gehört die Regel hin, nicht in jeden Chip.

Geschlossen wird (jeweils **verwerfend**, wie `Esc`; nichts wird
gesendet):

| Auslöser | Verhalten |
|---|---|
| Klick auf einen anderen Chip | offene Eingabe schließen, dann Kanal wechseln |
| `set_current()` von außen (MHEARD-Doppelklick, Unproto, Programm) | offene Eingabe schließen |
| Betriebsartwechsel, `reset_channels()`, Trennen des TNC | offene Eingabe schließen |
| Klick irgendwo anders in der Maske | offene Eingabe schließen |

Für den letzten Fall reicht der vorhandene Ereignisfilter der Maske
(P41): Ein Mausklick, dessen Ziel nicht der editierende Chip ist,
schließt die Eingabe. **Kein neuer Filter** — den bestehenden erweitern.

Der Klick, der die Eingabe schließt, soll seine normale Wirkung behalten:
Ein Klick auf Chip 4 schließt die Eingabe in Chip 3 **und** wechselt auf
Kanal 4. Kein „erster Klick schließt nur".

**Commit:** `Channel bar: only one chip editor open at a time`

---

## P57.2 — Das Eingabefeld sieht aus wie eine Eingabe

Nach P42: bernsteinfarbener Rahmen, zentrierter Monospace-Text. Im
Screenshot fehlt der Rahmen.

- Rahmenfarbe wie festgelegt (`#e8b23a`), Rahmenstärke wie beim
  gewählten Chip, damit die Leiste nicht springt
- Schrift aus derselben Quelle wie die übrigen Chips
- der **gewählte** Chip trägt weiterhin seinen Rahmen; ist er zugleich
  der editierte, hat der Eingaberahmen Vorrang

**Commit:** `Channel bar: chip editor keeps the amber frame`

---

## P57.3 — Tests

- Eingabe in Chip 3 offen, Klick auf Chip 4 → Eingabe geschlossen,
  **kein** `connect_requested`, aktueller Kanal ist 4
- danach landet ein Tastenanschlag im TX-Fenster, nicht im Feld von
  Chip 3
- Eingabe offen, `set_current(5)` von außen → geschlossen
- Eingabe offen, Klick ins TX-Feld → geschlossen
- Eingabe offen, `reset_channels()` → geschlossen
- Eingabe offen, `Esc` → geschlossen (unverändert)
- Eingabe offen, `Enter` mit gültigem Rufzeichen → `connect_requested`
  (unverändert)
- gleichzeitig offene Eingaben sind nicht möglich: zwei Doppelklicks
  hintereinander auf verschiedene Chips hinterlassen genau eine offene
  Eingabe

**Commit:** `Tests: chip editor closes on channel switch`

---

## P57.4 — Dokumentation

`CLAUDE.md`, Abschnitt Kanalmodell:

- **Chips sind `NoFocus`** — deshalb schließt ein Klick auf einen anderen
  Chip die Eingabe **nicht** über `focusOut`; die Kanalleiste schließt sie
  ausdrücklich. Wer künftig ein Eingabefeld in ein `NoFocus`-Widget
  einbettet, muss dasselbe tun
- die Liste der Auslöser aus P57.1 als Tabelle

**Commit:** `Docs: chip editor lifecycle`

---

## Definition of Done

- `.venv\Scripts\python.exe -m pytest` grün
- Der Test „Klick auf anderen Chip" ist ohne den Fix rot — gegengeprüft
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"
- Danach vom Operator: Eingabe öffnen, auf einen anderen Chip klicken,
  tippen — der Text muss im TX-Fenster landen