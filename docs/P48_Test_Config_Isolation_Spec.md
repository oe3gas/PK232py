# Claude Code Prompt — P48: Tests dürfen die echte Konfiguration nicht anfassen

> Ablage: `docs/P48_Test_Config_Isolation_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher `CLAUDE.md` lesen (die Gotcha-Notiz aus P47 steht schon dort).

---

## Befund (25.09.2026, während P47)

Zwei Tests bauten ein echtes `MainWindow()`, dessen `ConfigManager` auf
`~/.pk232py/pk232py.ini` zeigt. `closeEvent()` speichert beim Schließen —
damit landeten Testwerte in der **Produktivkonfiguration des Operators**
(auf der Platte bestätigt: Port COM7, echte Rufzeichen) und wirkten in
spätere Tests hinein.

Der Einzelfall ist behoben (explizit setzen, im `finally` zurücksetzen).
Die Ursache bleibt: Solange Tests den echten Pfad sehen, hängt die
Isolation an der Disziplin des Testautors — und der nächste Vorfall fällt
womöglich nicht auf, weil kein anderer Test darüber stolpert.

---

## P48.1 — Pfad umleitbar machen

1. Feststellen, wie `ConfigManager` seinen Pfad bestimmt und ob er von
   außen setzbar ist (Parameter, Umgebungsvariable, Klassenattribut).
2. Ist er hart verdrahtet: die **kleinste nötige** Öffnung schaffen —
   etwa ein optionaler Parameter mit dem bisherigen Vorgabewert oder eine
   Umgebungsvariable, die nur gelesen wird, wenn sie gesetzt ist. Im
   Commit-Text begründen, welche Variante gewählt wurde und warum.
3. **Kein** Umbau der Konfigurationslogik darüber hinaus.

**Commit:** `Config: allow redirecting the config path`

---

## P48.2 — Autouse-Fixture

In `conftest.py` eine **autouse**-Fixture, die für **jeden** Test den
Konfigurationspfad auf ein `tmp_path`-Verzeichnis umbiegt.

Damit ist die Isolation eine Eigenschaft der Testumgebung, nicht eine
Gedächtnisleistung beim Schreiben neuer Tests.

- greift auch für Tests, die gar keine Konfiguration erwarten — sie
  kostet dort nichts
- vorhandene Tests, die den Pfad selbst setzen, bleiben gültig; doppelte
  Umleitung ist harmlos

**Commit:** `Tests: autouse fixture redirects the config path`

---

## P48.3 — Nachweis, dass die Umleitung greift

Ein Test, der die Umleitung selbst prüft:

- den **echten** Pfad ermitteln (ohne ihn zu verändern)
- Zeitstempel oder Hash festhalten
- einen vollständigen `MainWindow()`-Lebenszyklus durchlaufen lassen
  (erzeugen, schließen)
- prüfen, dass die echte Datei **unverändert** ist

Existiert die Datei auf dem Testrechner nicht, gilt: sie darf danach
**nicht** existieren.

**Commit:** `Tests: prove the real config file is never touched`

---

## P48.4 — Dokumentation

`CLAUDE.md`: die vorhandene Gotcha-Notiz aus P47 um den Verweis auf die
Fixture ergänzen — ein Test, der ein echtes `MainWindow` baut, schreibt
beim Schließen die Konfiguration; dagegen schützt jetzt die
autouse-Fixture, nicht die Sorgfalt des Autors.

**Commit:** `Docs: test config isolation`

---

## Definition of Done

- `.venv\Scripts\python.exe -m pytest` grün
- Der Nachweis-Test aus P48.3 ist vorhanden und wäre ohne die Fixture rot
  — kurz gegengeprüft
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"