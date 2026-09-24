# Claude Code Prompt — P41: Tastatureingaben in Auswahlfeldern der Packet-Maske

> Ablage: `docs/P41_Focus_Filter_Fix_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.

---

## Befund (24.09.2026, Anwendung, VHF-Packet-Maske)

Der Operator klickt in das **Dest**-Feld und tippt ein Rufzeichen — die
Zeichen erscheinen im **TX-Fenster** statt im Feld.

**Ursache:** Der Ereignisfilter der Packet-Maske leitet alle
Tastenanschläge ins TX-Fenster um, damit man ohne Klick sofort tippen
kann. Die Ausnahme prüft:

```python
focused = self.focusWidget()
if isinstance(focused, (QTextEdit, QLineEdit)):
    return super().eventFilter(obj, event)
```

`Dest` ist eine **editierbare `QComboBox`**, keine `QLineEdit`. Liefert
`focusWidget()` die Combobox selbst statt ihres inneren Eingabefelds,
greift die Ausnahme nicht.

Vermutlich betroffen: `Dest`, `Monitor`, `HBAUD` — alle Auswahlfelder.
Das `via`-Feld ist eine echte `QLineEdit` und sollte funktionieren; das
ist die Gegenprobe.

Der Fehler stammt aus der Mockup-Vorlage und ist damit auch in den
anderen Masken zu erwarten, die denselben Filter verwenden.

---

## P41.1 — Ausnahme vollständig machen

Die Prüfung erfasst künftig **jedes** Widget, das Tastatureingaben
erwartet:

- `QLineEdit`, `QTextEdit`, `QPlainTextEdit`
- `QComboBox` **und** ihr inneres `lineEdit()`
- `QAbstractSpinBox` (deckt `QSpinBox`, `QDoubleSpinBox` ab)

Robuster als eine Typliste ist die Frage nach der Absicht des Widgets:
prüfe, ob das fokussierte Widget (oder eines seiner Elternteile bis zur
Maske) Tastatureingaben annimmt — etwa über
`focusPolicy() & Qt.FocusPolicy.StrongFocus` in Verbindung mit der
Typliste. CC entscheidet, welche Variante sich sauber testen lässt, und
begründet die Wahl im Commit-Text.

**Wichtig:** Auch das **Eltern-Widget** berücksichtigen. Bei einer
editierbaren Combobox kann `focusWidget()` je nach Plattform die Box oder
ihr inneres Feld liefern — beide Fälle müssen greifen.

**Commit:** `Packet screen: keyboard redirection respects combo boxes and spin boxes`

---

## P41.2 — Dieselbe Stelle in den anderen Masken

Der Filter stammt aus der gemeinsamen Vorlage. Alle Masken durchsehen, die
ihn verwenden (Baudot, AMTOR, PACTOR, Morse, NAVTEX, Signal, Packet), und
dort dieselbe Korrektur anwenden — oder, falls der Filter bereits
gemeinsam liegt, nur an der einen Stelle.

Im Commit-Text nennen, welche Masken betroffen waren und ob es eine
gemeinsame Stelle gibt. Gibt es sie **nicht**, den Befund in `Backlog.md`
eintragen: derselbe Filter mehrfach kopiert ist die Fehlerklasse, die uns
schon bei den Frame-Decodern und beim Wakeup begegnet ist.

**Commit:** `Opmode screens: same fix for the shared keyboard filter`

---

## P41.3 — Kanalwechsel per Tastatur gegenprüfen

Die Kanalleiste reagiert auf `Ctrl+Up`/`Ctrl+Down`. Prüfen, dass diese
Tastenkombination **nicht** ausgelöst wird, während der Fokus in einem
Eingabefeld steht, und dass die blanken Pfeiltasten dort weiterhin den
Cursor bewegen.

**Commit:** wird Teil von P41.1, wenn keine Änderung nötig ist — dann nur
ein Test.

---

## P41.4 — Tests

Qt-Tests offscreen:

- Fokus im `Dest`-Feld, Taste `O` → Text landet im Feld, **nicht** im
  TX-Fenster
- Fokus im `via`-Feld → wie bisher
- Fokus auf einem Knopf oder der Kanalleiste → Zeichen landet im
  TX-Fenster (das bestehende Verhalten bleibt)
- Fokus im `Monitor`-Auswahlfeld, Taste `4` → Auswahl reagiert, TX bleibt
  leer
- `Ctrl+Up` im `Dest`-Feld → kein Kanalwechsel

**Commit:** `Tests: keyboard focus handling in the packet screen`

---

## P41.5 — Dokumentation

- `CLAUDE.md`, UI-Abschnitt: Der Ereignisfilter leitet Tastatureingaben
  ins TX-Fenster um; **jedes** eingabefähige Widget braucht eine Ausnahme.
  Editierbare Comboboxen sind der Fall, der leicht übersehen wird, weil
  `focusWidget()` je nach Plattform die Box oder ihr inneres Feld liefert
- `Testplan.md`: Fall — in jedes Eingabefeld der Packet-Maske tippen und
  prüfen, dass der Text dort ankommt

**Commit:** `Docs: keyboard filter must exempt every input widget`

---

## Definition of Done

- `.venv\Scripts\python.exe -m pytest` grün
- Der Test für das `Dest`-Feld ist ohne den Fix rot — gegengeprüft
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"
- Danach vom Operator: in Dest, via, Monitor und HBAUD tippen