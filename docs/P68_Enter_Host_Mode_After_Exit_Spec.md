# Claude Code Prompt — P68: „Enter Host Mode" bleibt nach „Leave Host Mode" ausgegraut

> Ablage: `docs/P68_Enter_Host_Mode_After_Exit_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Grundlage: `main` @ `2f87fcd`, Betreiberbeobachtung T144 (29.09.2026,
> Gerät B). Kleines, eigenständiges Paket — unabhängig vom Kanal-Umbau
> (P69 Messung, P70 Umsetzung).

---

## Befund

Nach TNC → Leave Host Mode ist TNC → Enter Host Mode (Ctrl+H) grau und
bleibt es, bis die Verbindung zum TNC getrennt und neu aufgebaut wird.

Ursache (gelesen):

- `MainWindow._update_tnc_menu_gating()`:
  `can_enter = connected and verbose and not host`, mit
  `verbose = self._serial.is_verbose_mode`.
- `SerialManager.is_verbose_mode` = `is_connected and _verbose_ready and not
  _in_host_mode`.
- `SerialManager.exit_host_mode()` setzt `_verbose_ready = False`, sendet
  danach `host_mode_changed(False)` und führt **erst dann** die
  COMMAND-Zeichen-Resynchronisation aus (`write_verbose_wait(...)`, Ergebnis
  `ok`). `_verbose_ready` wird dort **nie wieder** `True`. Gesetzt wird es
  nur im Init (`_finish_verbose_init()`).

Der Fehler besteht seit P49 (Ctrl+H eingeführt); vor P67 fiel er kaum auf,
weil nach einem Benutzerausstieg selten sofort wieder eingestiegen wurde.

---

## Umsetzung

### A. `SerialManager.exit_host_mode()`
Nach der Resynchronisation `_verbose_ready = True` setzen — **in beiden
Fällen** des bestehenden Logs („reached cmd:" und „got no cmd: (TNC may
already be at the prompt)"): Der TNC hat `HOST OFF` bekommen und der
neue Reader läuft im verbose Pfad; das ist dieselbe Voraussetzung, unter
der `_finish_verbose_init()` das Flag setzt. `_verbose_confirmed` (P43,
„aktiv bestätigt") nur im Fall „reached cmd:" auf `True`.

Danach ein neues Signal `verbose_resumed` emittieren (nicht
`verbose_mode_ready` — das löst Banner-Sammlung und Parameter-Upload aus,
die hier nicht hingehören).

### B. `MainWindow`
`verbose_resumed` → `_update_tnc_menu_gating()`. Keine weitere Logik.

**Commits:**
```
SerialManager: verbose ready again after Host Mode exit
MainWindow: refresh TNC menu when verbose mode resumes
```

---

## Tests (zuerst rot)

- `test_serial_manager.py`: nach `exit_host_mode()` mit Resync „reached
  cmd:" → `is_verbose_mode is True`, `verbose_confirmed is True`,
  `verbose_resumed` genau einmal; mit „got no cmd:" →
  `is_verbose_mode is True`, `verbose_confirmed` unverändert.
- `test_main_window_connection.py`: verbunden, Host Mode betreten,
  Benutzerausstieg → `_act_enter_host_mode.isEnabled()` ist `True`.
  (Heute `False` — das ist der rote Test.)

**Commit:** `Tests: Enter Host Mode enabled again after leaving Host Mode`

---

## Doku

- `Testplan.md`: **T145** — Ctrl+H, Leave Host Mode, Ctrl+H erneut ohne
  Neuverbindung; erwartet: zweiter Eintritt möglich. Gerät B, OPEN.
- `Backlog.md`: Eintrag als erledigt (P68).
- `CLAUDE.md`, Known Gotchas: `_verbose_ready` wird von Init **und** Host-
  Mode-Ausstieg gesetzt; `verbose_resumed` ≠ `verbose_mode_ready`.

**Commits:**
```
Testplan: T145 re-enter Host Mode
Docs: CLAUDE.md verbose_resumed after Host Mode exit
Docs: add P68 spec file
```

---

## Definition of Done

- roter Test vorher nachgewiesen, volle Suite grün
- **Push**, Meldung mit Hash; `.\Sources2Text.ps1`, „sources aktualisiert"