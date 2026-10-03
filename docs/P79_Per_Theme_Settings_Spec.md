# Claude Code Prompt — P79: Jedes Thema merkt sich Schrift, Hintergrund und RX/TX-Farbe

> Ablage: `docs/P79_Per_Theme_Settings_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Grundlage: `main` @ `6c756d0` (nach P78). Wunsch des Betreibers 03.10.2026.
> Doku nach `docs/claude/`.

---

## Befund

- `AppearanceConfig` (`config.py:306`) hält **einen** Satz Werte:
  `theme`, `font_family`, `font_size`, `bg_color`, `fg_color`, `rx_color`,
  `tx_color`, `connect_bell`; INI-Abschnitt `[Appearance]`.
- Eine Themenwahl (`main_window.py` ~5057) überschreibt Schrift und Farben
  mit den Vorgaben des Themas (`ui/themes.py`, `colors.THEME_TEXT_COLORS`).
- Eine Änderung im Dialog „Font & Colors" macht das Thema zu `custom`.
- Folge (Betreiber, T163): Schriften, die er unter verschiedenen Themen
  gewählt hatte, sind nach dem nächsten Themenwechsel weg. Gespeichert
  wurden sie nie je Thema.

## Wunsch

Jedes Thema hat **eigene** Einstellungen für Schrift (Familie, Größe),
Hintergrund, Vordergrund, RX- und TX-Farbe. Ein Themenwechsel stellt die
Einstellungen dieses Themas wieder her.

---

## Teil A — Konfiguration

- `AppearanceConfig` bekommt `overrides: dict[str, dict[str, str|int]]` —
  je Themenschlüssel nur die **Abweichungen** von der Vorgabe
  (`font_family`, `font_size`, `bg_color`, `fg_color`, `rx_color`,
  `tx_color`).
- Die bisherigen Einzelfelder bleiben als **wirksame** Werte des aktuellen
  Themas (alle Leser bleiben unverändert), werden aber an **einer** Stelle
  berechnet: `effective(theme) = Vorgabe(theme) ⊕ overrides[theme]`.
- `custom` bleibt ein eigenes, fünftes Thema mit Vorgaben = Dark; es
  verliert seinen Sonderstatus („wird automatisch gesetzt") — der Dialog
  bearbeitet immer das **aktuell gewählte** Thema.
- INI: je Thema ein Abschnitt `[Appearance.dark]`, `[Appearance.air]` …
  nur mit den abweichenden Schlüsseln; `[Appearance]` behält `theme` und
  `connect_bell`.
- **Migration** beim Laden einer alten INI: Die Werte aus `[Appearance]`
  werden, soweit sie von der Vorgabe des gespeicherten Themas abweichen,
  als dessen Overrides übernommen (bei `theme = custom` in den Slot
  `custom`). Danach werden die alten Einzelschlüssel nicht mehr
  geschrieben.

**Commit:** `Config: per-theme appearance overrides with migration`

---

## Teil B — Verhalten

- Themenwahl im Menü: wirksame Werte = `effective(neues Thema)`, Anzeige
  aktualisieren, speichern.
- Dialog „Font & Colors": Titel zeigt das bearbeitete Thema („Appearance —
  Air"). OK speichert die Abweichungen in `overrides[aktuelles Thema]`;
  ein Wert gleich der Vorgabe wird **entfernt** (keine toten Overrides).
- „Reset" im Dialog: Overrides des aktuellen Themas löschen.
- Kontrastanzeige (P77b) unverändert, bezogen auf die wirksamen Werte.

**Commits:**
```
MainWindow: theme selection applies the theme's own settings
Appearance: dialog edits the current theme, reset clears its overrides
```

---

## Teil C — Tests (zuerst rot)

- Air: Schrift → Consolas 12; Wechsel zu Dark; zurück zu Air → Consolas 12
  (heute: Air-Vorgabe = rot).
- Retro: TX-Farbe ändern; Air und Dark unberührt.
- Override gleich Vorgabe → nicht gespeichert.
- Reset in Air → Air-Vorgabe, Overrides von Dark bleiben.
- INI-Round-Trip mit drei Themen mit Overrides.
- Migration: alte INI `theme = custom`, eigene Schrift → Slot `custom`;
  alte INI `theme = air`, Schrift abweichend → `overrides["air"]`.

**Commit:** `Tests: per-theme appearance`

---

## Teil D — Sichtprüfung T165

1. Air: Schrift A, Grün als TX. Dark: Schrift B. Retro: Schrift C.
2. Zwischen den Themen wechseln → jeweils die eigene Schrift/Farbe.
3. PK232PY beenden und neu starten → alles erhalten.
4. Air → Reset → Air-Vorgaben; Dark und Retro unverändert.

---

## Definition of Done

- roter Test vorher nachgewiesen, volle Suite grün
- `effective()` ist die einzige Stelle, die Vorgabe und Override verknüpft
- `Testplan.md`: T165 OPEN; `Backlog.md`: P79; `docs/claude/`: Regel
- **Push nach Freigabe**; `.\Sources2Text.ps1`