# Claude Code Prompt — P12: Verdrahtungsprüfung für alle Parameterdialoge

> Ablage: `docs/P12_Dialog_Audit_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher `CLAUDE.md`, `Backlog.md`, `Testplan.md` lesen.

---

## Warum

`USERS` hatte im HF-Parameterdialog ein fertiges Bedienelement, war aber in
keine Richtung verdrahtet: `_populate()` schrieb hart `1` hinein, `apply_to()`
las den Wert nie zurück. Der Dialog sah funktionsfähig aus und verwarf jede
Eingabe stillschweigend. Beim Wiederöffnen zeigte er `1` — was wie ein
Standardwert aussieht, nicht wie ein verlorener Wert.

Die Dialoge haben zusammen rund hundert Bedienelemente. Die Prüfung, ob jedes
davon in beide Richtungen angebunden ist, ist rein mechanisch und gehört
deshalb in einen Test, nicht in eine einmalige Durchsicht.

---

## P12.1 — Neue Testdatei `src/pk232py/tests/test_param_dialogs_roundtrip.py`

Ein Test je Richtung, parametrisiert über alle Parameterdialoge. Die Dialoge
haben **unterschiedliche APIs** (`_populate()`/`apply_to()` im HF-Dialog,
`set_values()`/`get_values()` in anderen) — zuerst im Repo erheben, welche
Dialogklasse welche Methoden hat, und im Test über einen kleinen Adapter
vereinheitlichen (`_load(dlg, cfg)` / `_read(dlg)`), statt die Dialoge
umzubauen. **Keine Änderung an den Dialog-APIs in diesem Paket.**

Offscreen-Plattform wie in `test_packet_screen.py` auf Modulebene setzen.

### Test A — Leserichtung: jedes Bedienelement muss ankommen

Der Test, der den `USERS`-Fehler gefunden hätte. Er braucht **keine**
Zuordnung von Feldnamen zu Widgets:

```
für jedes Widget in dlg.findChildren(QSpinBox | QDoubleSpinBox |
                                      QCheckBox | QLineEdit | QComboBox):
    vorher  = _read(dlg)                # Konfiguration aus dem Dialog
    Widget-Wert ändern (siehe unten)
    nachher = _read(dlg)
    assert nachher != vorher            # sonst: Widget nicht angebunden
    Widget-Wert zurücksetzen
```

Wertänderung je Typ:

- `QSpinBox` / `QDoubleSpinBox`: `value() + singleStep()`, falls das über
  `maximum()` läge, stattdessen `value() - singleStep()`. Klemmt beides auf
  den Ausgangswert (Bereich hat nur einen gültigen Wert), das Widget in den
  Bericht aufnehmen und übergehen — das ist kein Verdrahtungsfehler, sondern
  ein degenerierter Bereich.
- `QCheckBox`: `setChecked(not isChecked())`
- `QLineEdit`: Text um `"X"` ergänzen — außer das Feld ist `isReadOnly()`
- `QComboBox`: nächster Index, modulo `count()`; bei `count() < 2` übergehen

Die Fehlermeldung muss den **Objektnamen und die Beschriftung** des Widgets
nennen, nicht nur „Assertion failed" — sonst sucht man in achtzig Feldern.
Dafür `objectName()` setzen, falls nicht vorhanden: dann den
Attributnamen über `vars(dlg)` rückwärts auflösen.

### Test B — Schreibrichtung: jedes Konfigurationsfeld muss ankommen

```
für jedes Feld der Konfigurations-Dataclass:
    cfg = Standardkonfiguration
    Feldwert verändern (int: +1, bool: invertieren, str: anderer Text)
    _load(dlg, cfg)
    zurück = _read(dlg)
    assert getattr(zurück, feld) == getattr(cfg, feld)
```

Klemmt ein Spinbox-Bereich den veränderten Wert ab (`+1` über `maximum()`),
mit `-1` erneut versuchen, bevor der Test fehlschlägt. Das hält den Test
unabhängig von Bereichsgrenzen, die sich später ändern.

### Test C — INI-Rundreise

Eigene Fehlerklasse: ein Feld ist im Dialog korrekt verdrahtet, fehlt aber
in `configparser`-Lesen oder -Schreiben und geht beim Neustart verloren.

```
cfg mit durchgehend von den Defaults abweichenden Werten
→ speichern in eine temporäre INI (tmp_path)
→ frisch laden
→ feldweise vergleichen
```

### Ausnahmenliste

Am Kopf der Datei eine explizite, kommentierte Liste:

```python
# Widgets die bewusst nicht in die Konfiguration zurückschreiben.
# Jede Zeile braucht einen Grund — eine Ausnahme ohne Begründung ist
# ein verstecktes Verdrahtungsproblem.
UNWIRED_OK = {
    ("HFPacketParamsDialog", "_le_beispiel"): "read-only, TNC query result",
}
```

Keine pauschalen Filter über Namensmuster — jede Ausnahme wird einzeln
eingetragen und begründet. Das Schaltflächenfeld (`QDialogButtonBox`) und
alles darin ist generell ausgenommen, ebenso Widgets in Unterdialogen, die
`findChildren()` mitliefert.

**Commit:** `Tests: parameter dialog wiring round-trip audit`

---

## P12.2 — Befunde beheben

Der Test wird mit hoher Wahrscheinlichkeit weitere Felder finden. Für jeden
Befund:

- **je betroffener Datei ein eigener Commit**, nicht ein Sammelcommit
- Commit-Text nennt das Feld und die Richtung, in der die Verdrahtung fehlte
  (Beispiel: `HF params dialog: wire RESPTIME in apply_to`)
- **keine stillen Bereichsänderungen**: wenn ein Spinbox-Bereich nicht zum
  TNC-Parameter passt, im Commit-Text begründen und gegen die
  Handbuch-Angabe belegen — andernfalls Bereich lassen und den Befund melden
- Findet der Test ein Widget, zu dem es **kein** Konfigurationsfeld gibt:
  nicht raten, ob es eins braucht. Befund in `Backlog.md` eintragen und in
  `UNWIRED_OK` mit dem Grund „no config field yet — see Backlog" aufnehmen,
  damit der Test grün ist und der offene Punkt trotzdem sichtbar bleibt.

Wenn der Test nichts findet: das ist ein Ergebnis und gehört so in den
Doku-Commit.

---

## P12.3 — Dokumentation

### `CLAUDE.md`

Unter den bekannten Fallstricken ergänzen: Parameterdialoge müssen in beide
Richtungen verdrahtet sein (`_populate()`/`apply_to()` bzw.
`set_values()`/`get_values()`), ein neues Bedienelement ohne beide Hälften
verwirft Eingaben stillschweigend und sieht dabei funktionsfähig aus
(gefunden bei `USERS`, 2026-09-20). `test_param_dialogs_roundtrip.py` prüft
das automatisch — ein neues Feld im Dialog ohne Anbindung lässt den Test
fehlschlagen.

### `Testplan.md`

**T106 — Parameterdialog-Verdrahtung**
Automatisch über `test_param_dialogs_roundtrip.py`. Status ergibt sich aus
dem Testlauf; im Testplan nur der Verweis plus die Liste der beim ersten
Lauf gefundenen Felder.

**Commit:** `Docs: dialog wiring audit, test T106`

---

## Definition of Done

- `python -m pytest` grün
- Der Bericht des ersten Testlaufs (welche Felder waren nicht verdrahtet)
  steht im Commit-Text von P12.1 oder im Doku-Commit
- Ein absichtlich abgeklemmtes Feld lässt den Test fehlschlagen — kurz
  gegenprobiert, damit der Test nicht nur formal grün ist
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"