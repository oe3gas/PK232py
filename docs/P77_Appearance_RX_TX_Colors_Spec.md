# Claude Code Prompt — P77: Schriftfarben für RX und TX in „Appearance" — eine Farbquelle für alle Fenster

> Ablage: `docs/P77_Appearance_RX_TX_Colors_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Grundlage: `main` (nach P73), Betreiber-Screenshots 03.10.2026.
> Doku nach `docs/claude/`.

---

## Wunsch des Betreibers

- Im Baudot-Fenster (und im verbose Terminal) ist die Schrift auf hellem
  Hintergrund zu hell: TX-Eingabe **gelb auf Weiß**, TNC-Ausgabe im
  Terminal **hellgrau auf Weiß**.
- „Appearance → Font & Colors" um **Schriftfarbe RX** und **Schriftfarbe
  TX** erweitern.

## Befund (Code)

### B.1 Zwei Farbsysteme
- `ui/themes.py` + `AppearanceConfig`: Themen `dark`/`mono`/`retro`/`air`
  bzw. `custom`, mit `bg_color`, `fg_color`, Schrift. Der Dialog
  „Appearance Settings" bearbeitet nur diese Werte.
- `ui/screens/ui_theme.py`: eigene Paletten `dark`/`light` mit
  `rx_color` (`#88ccff` / `#000080`) und `tx_color` (`#ffee88` /
  `#006600`), Auswahl über `_current_theme` (Standard `"dark"`).
  `opmode_rtty_base.py` (396, 432) und `main_window.py` (2511, ~5115)
  nehmen TX/RX-Farben **von hier**.

Beim Betreiber: Hintergrund `#ffffff` aus `AppearanceConfig` (custom),
TX-Farbe `#ffee88` aus der **dunklen** Palette von `ui_theme.py` → gelb auf
Weiß. Die beiden Systeme wissen nichts voneinander.

### B.2 Fest codierte Farben
- verbose Terminal: `_vt_append(..., color="#cccccc")`
  (`main_window.py:5721`, `5750`) und Stylesheet `background-color:#0c0c0c;
  color:#cccccc` (`:823`) — fest dunkel/hellgrau, unabhängig vom Thema.
- Kommentare „TX text color: always yellow" (`main_window.py:~5115`),
  „RX echo (yellow)" (`:2887`), „inverse yellow" (`opmode_rtty_base.py`
  248–270, 579, 609).

---

## Grundsatz

**Eine** Quelle für Display-Farben: `AppearanceConfig`. Jede Anzeigefläche
(RX-Fenster, TX-Eingabe, verbose Terminal, Packet-Kanäle, MON) liest ihre
Farben daraus. Die Themen setzen nur Vorgabewerte.

---

## Teil A — Konfiguration

`AppearanceConfig` bekommt:

| Feld | Bedeutung |
|---|---|
| `rx_color` | empfangener Text, TNC-Ausgabe im verbose Terminal |
| `tx_color` | eingegebener/gesendeter Text, eigene Befehle im Terminal |

- Jedes Thema in `ui/themes.py` erhält Vorgaben für beide (Dark: heutige
  Werte `#88ccff`/`#ffee88`; helle Themen: dunkle Farben, z. B. Air
  `#000080`/`#006600` aus der heutigen Light-Palette).
- Fehlen die INI-Schlüssel: Werte des gespeicherten Themas.
- Eigene Änderung im Dialog → `theme = "custom"` (wie heute bei
  Hintergrund/Vordergrund).

**Commit:** `Config: RX and TX colors in AppearanceConfig, per-theme defaults`

---

## Teil B — Ein Farbsystem

- `ui/screens/ui_theme.py`: `rx_color`/`tx_color` werden **nicht** mehr
  dort definiert; `get_theme()` liefert sie aus `AppearanceConfig`. Die
  übrigen Palettenwerte (Buttons, Rahmen …) bleiben vorerst, werden aber
  passend zum hellen/dunklen Hintergrund gewählt (Helligkeit von
  `bg_color`, eine Funktion) statt über den separaten Schalter
  `_current_theme`.
- verbose Terminal: Hintergrund und Farben aus `AppearanceConfig`
  (`bg_color`, `rx_color` für TNC-Ausgabe, `tx_color` für eigene
  Befehle). Die festen `#0c0c0c`/`#cccccc` entfallen.
- Die „inverse" Darstellung gesendeter Zeichen (heute schwarz auf gelb)
  wird: Hintergrund `tx_color`, Schrift `bg_color` — passt so zu jedem
  Thema.
- Kommentare mit „yellow" an die neue Logik anpassen.
- Inventur: `git grep -n "#[0-9a-fA-F]\{6\}" -- src/pk232py/ui` — jede
  fest codierte Farbe in einer **Anzeigefläche** (nicht Menü-Chrome,
  nicht MON-Chip-Füllung) im Abschlussbericht mit Datei:Zeile und neuer
  Quelle aufführen.

**Commits:**
```
ui_theme: RX and TX colors come from AppearanceConfig
MainWindow: verbose terminal colors from AppearanceConfig
RttyBase: sent-character highlight from tx/bg colors
```

---

## Teil C — Dialog „Appearance Settings"

- Gruppe „Display Colors" um zwei Felder erweitern: **RX text** und
  **TX text** (gleiche Farbwahl-Schaltfläche wie Background/Foreground).
- Vorschau zeigt eine RX-Zeile und eine TX-Zeile in den gewählten Farben
  auf dem gewählten Hintergrund.
- **Kontrastwarnung:** Liegt der Kontrast einer der drei Schriftfarben zum
  Hintergrund unter 4,5 : 1 (WCAG-Formel, eine reine Funktion), erscheint
  unter der Vorschau ein Hinweis „Low contrast: TX text on background
  (2.1 : 1)". Speichern bleibt möglich.
- „Reset" setzt alle Farben auf die Vorgaben des aktuellen Themas.

**Commit:** `Appearance: RX and TX text colors with contrast warning`

---

## Teil D — Tests (zuerst rot)

- Thema Air, Hintergrund `#ffffff`: TX-Farbe im Baudot-TX-Feld ≠
  `#ffee88` (heute `#ffee88` = rot); entspricht `AppearanceConfig.tx_color`.
- verbose Terminal: TNC-Ausgabe mit `rx_color`, kein `#cccccc`.
- `rx_color`/`tx_color` im Dialog geändert → Config, Thema `custom`,
  Anzeige aktualisiert.
- Kontrastfunktion: `#ffee88` auf `#ffffff` < 4,5; `#000080` auf
  `#ffffff` ≥ 4,5; Warnung erscheint bzw. nicht.
- INI ohne neue Schlüssel → Themenvorgaben.
- `git grep -n "#cccccc" -- src/pk232py/ui/main_window.py` → leer.

**Commit:** `Tests: one color source, RX/TX colors, contrast`

---

## Teil E — Hardware/Sichtprüfung T163

1. Thema Air: Baudot-Fenster — TX-Eingabe gut lesbar; verbose Terminal —
   TNC-Ausgabe gut lesbar.
2. Appearance: TX-Farbe ändern → sofort im Baudot-TX-Feld und im Terminal.
3. Thema Dark: unverändert wie bisher.
4. Bewusst schlechte Farbe wählen (hellgelb auf weiß) → Kontrastwarnung.

---

## Definition of Done

- `rx_color`/`tx_color` nur noch in `AppearanceConfig` (bzw. Themen-
  Vorgaben) definiert — `git grep -n "\"tx_color\":" -- src` zeigt keine
  Palette in `ui_theme.py` mehr
- roter Test vorher nachgewiesen, volle Suite grün
- `Testplan.md`: T163 OPEN; `Backlog.md`: P77
- **Push nach Freigabe**; `.\Sources2Text.ps1`