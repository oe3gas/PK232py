# Claude Code Prompt — P61: Testlauf beschleunigen — Fenster entsorgen, Timeouts im Test verkürzen, QSettings isolieren

> Ablage: `docs/P61_Test_Suite_Speed_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Grundlage: Messung am `main` @ `6222441` (vor P60), Linux-Container,
> 1 CPU, `QT_QPA_PLATFORM=offscreen`. Absolute Zeiten auf dem
> Entwicklungsrechner sind andere — **Verhältnisse** sind maßgeblich.
> **Kein Test wird gestrichen.** Produktionsverhalten bleibt unverändert,
> mit einer Ausnahme (Teil D, Werkzeugleiste).

---

## Befund

### B.1 80 % der Laufzeit stecken in 60 von 700 Tests

`pytest --durations=60`: **700 passed in 324 s**. Die 60 langsamsten
Einträge summieren sich auf **259 s**:

| Datei | Phase | Einträge | Summe |
|---|---|---|---|
| `test_main_window_packet.py` | setup | 37 | 134,9 s |
| `test_serial_manager.py` | call | 14 | 105,5 s |
| übrige | | 9 | 18,4 s |

Die restlichen ~640 Tests brauchen zusammen gut eine Minute.

### B.2 MainWindow-Fixtures: quadratisches Wachstum durch nie gelöschte Fenster

Ein einzelnes `MainWindow()` braucht **0,1 s**. Im Testlauf dauert das
`setup` trotzdem bis zu **6,4 s**. Ursache:

- `main_window.py:250`: `QApplication.instance().installEventFilter(self)` —
  jedes Fenster filtert **jedes Ereignis der ganzen Anwendung**.
- Die Fixtures rufen zwar `w.close()` auf, das versteckt das Fenster aber
  nur. Gelöscht wird es nicht (kein `WA_DeleteOnClose`, und
  Signalverbindungen/Closures halten das Python-Objekt am Leben). Der
  anwendungsweite Filter bleibt aktiv.

Jedes weitere Fenster wird dadurch langsamer, und jedes Ereignis läuft
durch alle bisherigen Filter. Messung (neue Fenster nacheinander, ohne
Löschen):

| lebende Fenster davor | Aufbau des nächsten |
|---|---|
| 0 | 0,11 s |
| 5 | 0,72 s |
| 11 | 2,62 s |
| jeweils `deleteLater()` + `sendPostedEvents(DeferredDelete)` | **0,07 s konstant** |

Beleg im Profil: bei nur drei lebenden Fenstern bereits 48 815 Aufrufe von
`MainWindow.eventFilter` während **eines** Fensteraufbaus.

**Nicht** `qtbot.addWidget()` verwenden: pytest-qt ruft beim Aufräumen
`close()` auf — mit verbundenem Stub öffnet `closeEvent()` eine modale
Rückfrage (Test hängt, siehe Kommentar `test_main_window_packet.py:120`),
und `close()` schreibt in die QSettings (B.4).

### B.3 Erkennungskette: echte Wartezeiten im Test

`test_serial_manager.py` simuliert einen stummen oder halb antwortenden TNC
und wartet dabei die **Produktions-Timeouts** ab:
`_TNC_STATE_STEP_TIMEOUT = 1.5`, `_WAKEUP_TIMEOUT = 3.0`,
`_POLL_TIMEOUT = 3.0`, dazu `_RESTART_DELAY`, `_HOSTMODE_DELAY`,
`_GG_RETRY_DELAY` und mehrere literale `time.sleep()` (z. B. Zeilen 1051,
1243, 1288, 1292, 1529, 1561). Ergebnis: Einzeltests von 8–11 s, z. B.
`test_silence_throughout_reports_failure_and_power_cycle_hint` 11,4 s.

### B.4 Tests schreiben in die echten QSettings des Operators

`main_window.py:5535/5549`: `QSettings("OE3GAS", APP_TITLE)` — unter Windows
die **echte Registry** des Operators. `closeEvent()` →
`_save_window_geometry()` schreibt dort Fenstergeometrie und
Splittergrößen. Sechs Testdateien rufen `w.close()` auf
(`test_config_isolation.py:64`, `test_main_window_connection.py:100`,
`test_main_window_packet.py:125`, `test_main_window_verbose.py:58`,
`test_opmode_screen_layout.py:100/128`).

P48 isoliert nur die INI-Datei (`CONFIG_PATH_ENV_VAR`), nicht die
QSettings. Das ist dieselbe Fehlerklasse wie der P47-Vorfall (Testwerte in
der echten Konfiguration), nur an einem zweiten Speicherort.

### B.5 Nebenbefund Werkzeugleiste

Beim Schließen meldet Qt:
`QMainWindow::saveState(): 'objectName' not set for QToolBar ... 'Main'`.
`main_window.py:556` erzeugt `QToolBar("Main", self)` ohne
`setObjectName()`. Ohne Objektname kann `restoreState()` die Leiste beim
nächsten Start nicht zuordnen.

---

## Teil A — Fenster nach jedem Test entsorgen (eine Stelle: `conftest.py`)

`src/pk232py/tests/conftest.py`, neue autouse-Fixture neben
`isolate_config_path`:

```python
@pytest.fixture(autouse=True)
def dispose_main_windows():
    """P61: every MainWindow a test built is destroyed at teardown.
    MainWindow installs an application-wide event filter; a window that
    is only hidden (close()) keeps filtering every event of every later
    test - setup time grew quadratically (0.11 s -> 2.6 s after 11
    windows). Never calls close(): that would run closeEvent() (modal
    question with a connected stub, QSettings write)."""
    yield
    app = QApplication.instance()
    for w in [w for w in app.topLevelWidgets() if isinstance(w, MainWindow)]:
        app.removeEventFilter(w)
        w.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
```

- Die bestehenden `w.close()`-Aufrufe in den Fixtures bleiben, wo ein Test
  `closeEvent()` selbst prüft (z. B. `test_config_isolation.py`). Wo
  `close()` nur „aufräumen" soll, entfernen — das erledigt jetzt die
  Fixture.
- **Messender Test** (`test_conftest_disposal.py`, neu): zwei Tests
  hintereinander; der erste baut drei Fenster, der zweite prüft, dass
  `topLevelWidgets()` **kein** `MainWindow` mehr enthält. Muss vor Teil A
  rot sein.

**Commits:**
```
Tests: dispose every MainWindow after each test
Tests: remove close() used only for cleanup
Tests: prove no MainWindow survives into the next test
```

---

## Teil B — QSettings isolieren (eine Stelle: `conftest.py`)

Autouse, in `isolate_config_path` oder als eigene Fixture daneben:

```python
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat,
                  QSettings.Scope.UserScope, str(tmp_path / "qsettings"))
```

`QSettings("OE3GAS", APP_TITLE)` verwendet `defaultFormat()` und
`UserScope` — damit landet jeder Schreibzugriff unter `tmp_path`.
Produktionscode bleibt unverändert.

**Messender Test** (`test_config_isolation.py`): 
`QSettings("OE3GAS", APP_TITLE).fileName()` liegt unter `tmp_path`. Muss
vor Teil B rot sein (unter Windows zeigt `fileName()` sonst einen
Registry-Pfad).

**Commit:** `Tests: isolate QSettings like the INI file (P48 gap)`

---

## Teil C — Zeitkonstanten im Test verkürzen

### C.1 Literale Wartezeiten benennen (Produktionscode, reine Umbenennung)
In `serial_manager.py` jedes `time.sleep(<Zahl>)` **innerhalb der
Erkennungskette und der Recovery** durch eine benannte Modulkonstante mit
**identischem Wert** ersetzen, jeweils mit Kommentar, woher der Wert stammt
(TRM-Abschnitt, Messung, P-Nummer). Keine Wertänderung, kein anderes
Verhalten. Außerhalb dieser Pfade nichts anfassen.

**Stolperfalle:** Standardargumente wie `def f(timeout=_TNC_STATE_STEP_TIMEOUT)`
werden **beim Definieren** ausgewertet. Liegt eine solche Definition auf
Modul- oder Klassenebene, wirkt ein späteres `monkeypatch` darauf nicht.
Jede Fundstelle prüfen; bei Bedarf `timeout=None` und im Rumpf
`timeout = _TNC_STATE_STEP_TIMEOUT if timeout is None else timeout`.

**Commit:** `SerialManager: name the detection and recovery wait times`

### C.2 Fixture `fast_serial_timing`
In `test_serial_manager.py` (nur dort nötig): alle Konstanten aus C.1 und
B.3 per `monkeypatch.setattr` um denselben Faktor verkleinern (Vorschlag
1/30). **Ein** Faktor, damit Verhältnisse zwischen den Stufen erhalten
bleiben.

- Anwenden auf die Klassen mit Wartezeiten (`TestTncStateDetectionChain`,
  `TestRecoverySequence`, `TestXonFlowControlDetection`,
  `TestStep3EchoDetection`, `TestConverseModeDetection`, …) — per
  `pytestmark` oder Klassen-Dekorator, nicht in jedem Test einzeln.
- Stubs, die ihre Antwort **zeitverzögert** liefern, müssen ihre Verzögerung
  mit demselben Faktor skalieren — sonst prüft ein Test plötzlich etwas
  anderes (z. B. „Antwort kommt zu spät" statt „kommt rechtzeitig").
  Jeden solchen Stub im Bericht nennen.

### C.3 Nachweis, dass die Tests noch prüfen, was sie prüfen sollen
Für **drei** Tests je Klasse aus C.2: die Produktionslogik absichtlich
brechen (z. B. eine Stufe überspringen), mit `fast_serial_timing` laufen
lassen → **rot**; Bruch zurücknehmen → grün. Im Bericht je Fall der
Eingriff und die rote Zeile. Dieser Nachweis ersetzt hier „zuerst rot",
weil die Tests selbst bereits existieren.

**Commit:** `Tests: scale serial detection wait times in tests`

---

## Teil D — Werkzeugleiste mit Objektnamen

`main_window.py:556`: `tb.setObjectName("mainToolBar")`.
Test: nach `MainWindow()` hat jede `QToolBar` einen nicht leeren
`objectName()`; zuerst rot.

**Commit:** `MainWindow: object name for the main toolbar`

---

## Teil E — Arbeitsregel und Messung

### E.1 `CLAUDE.md`, Abschnitt Tests
- Während eines Pakets nur die betroffenen Testdateien laufen lassen, z. B.
  `pytest src/pk232py/tests/test_maildrop_dialog.py`.
- Vor jedem Push die **volle** Suite mit `--durations=15`; die Ausgabe der
  15 langsamsten gehört in den Abschlussbericht.
- Regel: Kein Test über **1 s** ohne Begründung im Docstring.
- Warum Fenster entsorgt und nie per `close()` aufgeräumt werden (B.2/B.4).

### E.2 Messung im Abschlussbericht
Vorher/nachher auf **demselben** Rechner:
- Gesamtdauer der vollen Suite
- `--durations=15` beider Läufe
- Anzahl Tests (muss ≥ vorher sein)

**Commits:**
```
Docs: CLAUDE.md test run rules and window disposal
Backlog: P61 test suite speed
Docs: add P61 spec file
```

---

## Definition of Done

- `pytest` grün, Testanzahl nicht gesunken
- Gesamtdauer auf dem Entwicklungsrechner **deutlich** unter dem Vorher-Wert
  (Erwartung aus der Messung: Faktor 4–5); kein Test über 1 s ohne
  Begründung
- Neuer Test „kein MainWindow überlebt" und QSettings-Test waren vorher rot
- C.3-Nachweise im Bericht
- `git grep -n "time.sleep([0-9]" -- src/pk232py/comm/serial_manager.py`
  zeigt in Erkennungskette und Recovery keine literalen Werte mehr
- **Push**, Meldung mit Hash
- `.\Sources2Text.ps1`, danach Meldung „sources aktualisiert"