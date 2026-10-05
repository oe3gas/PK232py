# Claude Code Prompt — P83: Parameter-Upload ohne Widget-Zugriffe aus dem Hintergrund-Thread

> Ablage: `docs/P83_Upload_Thread_GUI_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Grundlage: `main` (nach P77c). Backlog-Eintrag „`_run_param_upload` greift
> aus dem Upload-Thread auf Widgets zu" (hohe Priorität). Doku nach
> `docs/claude/`.

---

## Befund (Code, `main_window.py`)

`_start_param_upload_thread()` (1471) startet `_run_param_upload()` in einem
`threading.Thread` („PK232-ParamUpload"). Darin, also **außerhalb** des
GUI-Threads:

| Zugriff | Stelle | Art |
|---|---|---|
| `self._vt_append(...)` | mehrfach in `_run_param_upload` | schreibt in `QTextEdit` (`_vt_display`), setzt Cursor |
| `echo_callback=self._vt_append` | an `ParamsUploader` übergeben | jede Upload-Antwort → `QTextEdit` aus dem Thread |
| `self._log_monitor(...)` | mehrfach | schreibt in `QTextEdit` (`_monitor`), liest Schaltflächenzustand |
| `self._vt_input.setFocus()` | Ende beider Zweige | Widget-Fokus |
| `self._update_maildrop_gate_ui()` | nach dem Upload | aktiviert/deaktiviert Aktionen |
| `self._check_live_links()` | Anfang | laut Docstring korrekt per Signal (P81) — prüfen |
| `self._params_deferred.emit(...)` | korrekt (Signal) | — |

Qt erlaubt Widget-Zugriffe nur im GUI-Thread. Verstöße führen zu
sporadischen Abstürzen oder beschädigter Anzeige, die sich kaum nachstellen
lassen. Seit P81 läuft dieser Upload öfter und mit mehr Ausgaben.

Weitere Hintergrund-Threads: `SerialManager` (Init 1058, 1584, 1870),
`maildrop/session.py:164`. Für diese ist im Bericht zu belegen, dass sie
Widgets nur über Signale erreichen.

---

## Grundsatz

Der Upload-Thread spricht **nur über Signale** mit der Oberfläche. Alles,
was nach dem Upload an der Oberfläche passiert (Meldungen, Fokus,
MailDrop-Freigabe, Host-Mode-Eintritt), entscheidet ein Slot im GUI-Thread.

---

## Teil A — Prüfhilfe: Widget-Zugriffe außerhalb des GUI-Threads erkennen

- Eine Funktion `_assert_gui_thread(where: str)` (eine Stelle, z. B.
  `ui/thread_guard.py`): vergleicht `QThread.currentThread()` mit
  `QApplication.instance().thread()`. Im Fehlerfall `logger.error(...)` mit
  Ort und Thread-Name; im **Testmodus** (Umgebungsvariable oder
  pytest-Fixture) zusätzlich eine Ausnahme.
- Aufruf am Anfang von `_vt_append`, `_log_monitor`, `_log_terminal` und
  aller Methoden, die der Upload heute aus dem Thread erreicht.

**Commit:** `ui: thread guard for widget access`

---

## Teil B — Signale statt direkter Aufrufe

- `MainWindow` bekommt Signale (Qt queued connection, Standard bei
  Thread-Grenze): `_upload_vt_line(str, str)` (Text, Farbe oder „"),
  `_upload_monitor_line(str)`, `_upload_finished(object)`.
- `_run_param_upload` und der `echo_callback` des `ParamsUploader` senden
  **nur** über diese Signale. Kein direkter Widget-Aufruf mehr im Thread.
- `_upload_finished` trägt ein kleines Ergebnisobjekt (Anzahl, Prüfergebnis,
  zurückgestellte Namen, `has_maildrop`, `connect_mode`, ob Fast Init). Der
  Slot im GUI-Thread schreibt die Abschlussmeldungen, aktualisiert die
  MailDrop-Freigabe, setzt den Fokus und ruft `enter_host_mode()` auf.
- Reihenfolge der Ausgaben im Terminal bleibt wie heute (Signale derselben
  Quelle werden in Sendereihenfolge zugestellt; im Test belegen).

**Commits:**
```
MainWindow: parameter upload talks to the GUI through signals only
MainWindow: upload finish handled in the GUI thread
```

---

## Teil C — Andere Threads prüfen

Bericht (nicht zwingend Code): `SerialManager`-Threads und
`maildrop/session.py:164` — erreichen sie Widgets nur über Signale? Fund →
im selben Muster beheben, eigener Commit je Datei.

---

## Teil D — Tests (zuerst rot)

- Mit aktivem Thread-Guard im Testmodus: `_run_param_upload` in einem echten
  `threading.Thread` mit Fake-Serial laufen lassen → heute Ausnahme bzw.
  Fehlerlog (rot), danach keiner.
- Ausgabereihenfolge im Terminal nach dem Upload identisch zu vorher
  (Vergleich gegen eine vorher aufgezeichnete Zeilenliste).
- `connect_mode == "host"` → `enter_host_mode()` wird im GUI-Thread
  aufgerufen (Thread-Name im Fake prüfen).
- Fast-Init-Zweig ebenso.

**Commit:** `Tests: no widget access from the upload thread`

---

## Teil E — Hardware T171 (Gerät B)

1. Normaler Start mit Upload (verbose und Host Mode als Verbindungsart).
   Ausgaben im Terminal vollständig und in richtiger Reihenfolge.
2. Neustart mit zwei Verbindungen (wie T169): Ausgaben, Zurückstellung,
   Host-Mode-Eintritt unverändert.
3. App-Log: **keine** Zeile des Thread-Guards.

---

## Definition of Done

- In `_run_param_upload` und im `echo_callback` kein Widget-Zugriff mehr
  (Thread-Guard im Test belegt)
- Bericht zu Teil C
- rote Tests vorher nachgewiesen, volle Suite grün
- `Testplan.md`: T171 OPEN; `Backlog.md`: Eintrag erledigt; `docs/claude/`:
  Regel „Hintergrund-Threads nur über Signale"
- **Push nach Freigabe**; `.\Sources2Text.ps1`