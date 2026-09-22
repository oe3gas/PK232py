# Claude Code Prompt — P19: ein Weg für Modusinstanzen, SIAM-Screen prüfen

> Ablage: `docs/P19_Mode_Factory_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher `CLAUDE.md`, `Backlog.md`, `Testplan.md` lesen.

---

## Warum

P18.1 bringt `hf_packet.maxframe` und `hf_packet.slottime` über
`_on_mode_selected()` in den HF-Modus. `ModeManager.set_mode()` erzeugt aber
eine **frische Instanz mit Konstruktor-Defaults**, sobald kein
`mode_instance` übergeben wird. Jeder andere Aufruf von
`set_mode("HF Packet")` bekommt also 1/30 statt der konfigurierten Werte.

Solange die Konfiguration auf den Defaults steht, ist das unsichtbar. Es
wird sichtbar, sobald der Operator im Dialog etwas ändert — und dann nur je
nachdem, auf welchem Weg der Modus aktiviert wurde. `tools/hw_check.py t112`
findet das **nicht**, weil das Werkzeug die Frames direkt aus der
Konfiguration baut und die Anwendung nicht durchläuft.

---

## P19.1 — Untersuchung: alle Aktivierungswege

Im ganzen Repo jeden Aufruf von `set_mode(` und jede Stelle suchen, an der
eine Modusinstanz entsteht (`HFPacketMode(`, `VHFPacketMode(`,
`MODE_BY_NAME[...]()` bzw. `cls()` in `mode_manager.py`). Für jede Fundstelle
festhalten:

- Datei, Funktion, Zeile
- wann sie im Betrieb durchlaufen wird (Benutzerwahl, Host-Mode-Eintritt,
  Rückkehr aus verbose-Aktivierung, Wiederherstellung nach Fehler …)
- ob sie konfigurierte Werte übergibt

Ergebnis in den Commit-Text von P19.2.

---

## P19.2 — `src/pk232py/ui/main_window.py`: eine Fabrik

Eine einzige Methode, die jede Modusinstanz mit Konfiguration baut:

```python
def _build_mode_instance(self, mm_name: str) -> Optional[BaseMode]:
    """Return a mode instance carrying the configured values, or None
    for modes that need no configuration (ModeManager then uses its
    default instance)."""
```

- zunächst nur `"HF Packet"` (die Logik aus P18.1 hierher verschieben)
- **jeder** Aufruf von `self._modes.set_mode(...)` in `main_window.py`
  übergibt `mode_instance=self._build_mode_instance(mm_name)`
- findet P19.1 Aufrufe außerhalb von `main_window.py` (etwa in
  `mode_manager.py` selbst): **nicht** umbauen, sondern als Befund in
  `Backlog.md` eintragen — das wäre ein Eingriff in den
  Moduswechsel-Zustandsautomaten und gehört in ein eigenes Paket

Unit-Test: Konfiguration auf `maxframe=2, slottime=20` setzen, jeden in
P19.1 gefundenen Aktivierungsweg in `main_window.py` auslösen, und prüfen,
dass die gesendeten HF-Init-Frames `MX 2` und `SL 20` enthalten. **Mit
Werten ungleich den Defaults** — ein Test mit 1/30 würde auch ohne Fix grün.

**Commit:** `MainWindow: build mode instances in one place with config values`

---

## P19.3 — `src/pk232py/modes/packet_hf.py` / `packet_vhf.py`: Aufräumen

- Die Konstruktor-Defaults von `HFPacketMode` **aus `HFPacketConfig`
  ableiten** statt die Zahlen zu wiederholen (Standardwerte der
  Dataclass lesen), damit es nur eine Quelle gibt. Falls das einen
  Importzyklus erzeugt: Zahlen lassen, aber einen Unit-Test ergänzen, der
  Gleichheit mit `HFPacketConfig` prüft — dann fällt ein Auseinanderlaufen
  sofort auf.
- `VHFPacketMode`: im Docstring festhalten, dass die geerbten Parameter
  `maxframe`/`slottime` **nicht verwendet** werden und VHF bewusst die
  festen Werte 4/10 sendet (Backlog-Verweis auf den fehlenden
  VHF-Parametersatz).

**Commits (je Datei):**
```
HFPacketMode: derive constructor defaults from HFPacketConfig
VHFPacketMode: document unused inherited maxframe/slottime
```

---

## P19.4 — SIAM-Screen: nutzt er das zusammengesetzte Ergebnis?

Prüfen, wie `_wire_mode_callbacks()` den Signal-Screen an `SignalMode`
bindet:

- an `on_result` (Rohzeile) oder an `on_result_parsed` (`SiamResult`)?
- hat der Screen einen **eigenen** Parser für die Ergebniszeile? Wenn ja:
  durch `SiamResult` ersetzen — zwei Parser für dasselbe Format laufen
  auseinander (siehe die zwei Frame-Decoder in `CLAUDE.md`)
- zeigt der Screen fortlaufende Ergebnisse sinnvoll an? Der TNC liefert
  etwa alle 10 s ein neues. Mindestanforderung für v0.1: das **neueste**
  Ergebnis oben, alle im Verlauf; das bisher **sicherste** (höchste
  Konfidenz) sichtbar markiert

Nur die Anbindung und die Anzeige ändern, nicht `SignalMode`.

Unit-Test mit den T113-Frames: nach vier vollständigen Ergebnissen zeigt
der Screen 0,73 als sicherstes an.

**Commit:** `Signal screen: use SiamResult, show latest and best result`

---

## P19.5 — Dokumentation

- `CLAUDE.md`: Regel ergänzen — **Modusinstanzen mit Konfiguration
  entstehen nur in `_build_mode_instance()`**; ein direkter
  `set_mode(name)` ohne Instanz liefert Konstruktor-Defaults
- `Testplan.md`: T114 (SIAM-Screen am Gerät) konkretisieren — erwartet ein
  Ergebnis pro Zeile, nicht zwei Hälften; sicherstes Ergebnis markiert
- `Backlog.md`: Befunde aus P19.1, falls vorhanden; VHF-Parametersatz
  (eigene Konfigurationssektion statt fester 4/10) als offener Punkt

**Commit:** `Docs: mode instance factory, SIAM screen expectations`

---

## Definition of Done

- `python -m pytest` grün
- Der P19.2-Test benutzt Werte ungleich den Defaults und wäre ohne den Fix
  rot — kurz gegenprobiert
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"