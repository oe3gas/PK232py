# Claude Code Prompt — P76: Signalton bei erfolgreichem Connect, in „Appearance" schaltbar

> Ablage: `docs/P76_Connect_Bell_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Grundlage: `main` (nach P72). Wunsch des Betreibers 02.10.2026.
> Doku-Hinweise nach `docs/claude/`. P75 (Zeilenenden) ist reserviert.

---

## Wunsch

Ein Signalton („Glocke") ertönt, wenn ein Connect erfolgreich ist. Unter
**Configure → Appearance** ein- und ausschaltbar.

## Befund (Code)

- Verbindungen kommen an **einer** Stelle an: `comm/link_table.py`.
  Ein echter neuer Connect setzt `STATE_CONNECTED` über
  `on_host_link_message()` (`$5n "CONNECTED to …"`, Host Mode, ein- und
  ausgehend) bzw. `on_verbose_line()` (`*** CONNECTED to …`, verbose).
- Dieselbe Zustandsänderung entsteht aber auch beim **Abgleich**
  (`on_link_status()` nach `CO`-Abfrage, `on_verbose_cstatus()`), z. B.
  nach jedem Host-Mode-Eintritt (P67) — dort darf es **nicht** klingeln,
  denn das ist keine neue Verbindung.
- `subscribe()` meldet Zustände, keine Ereignisse; ein Klingeln am
  Zustandswechsel würde den Abgleich mit erfassen.
- „Configure → Appearance" ist ein Untermenü (`main_window.py`, ab Zeile
  ~449) mit „Font & Colors..." und den Themen als ankreuzbare Einträge.
  Einstellungen dazu liegen in `AppearanceConfig` (`config.py`).
- Bisher erzeugt die App keinen Ton.

---

## Teil A — Ereignis „connected" in der `LinkTable`

- Neue Beobachterliste `subscribe_events(callback(channel, event,
  partner))`, getrennt von `subscribe()`.
- Ereignis `"connected"` **nur** aus `on_host_link_message()` und
  `on_verbose_line()`, und nur, wenn der Kanal vorher **nicht**
  `connected`/`unconfirmed` war.
- `on_link_status()` und `on_verbose_cstatus()` lösen **nie** ein
  Ereignis aus.

**Commit:** `LinkTable: connected event for new connects only`

---

## Teil B — Einstellung

- `AppearanceConfig.connect_bell: bool = True`; INI lesen/schreiben,
  fehlender Schlüssel → `True`.
- Appearance-Untermenü: ankreuzbarer Eintrag **„Connect bell"** nach
  „Font & Colors...", vor dem Themen-Block (eigener Separator). Status-Tip:
  „Sound a bell when a connection is established". Umschalten wirkt sofort
  und wird sofort gespeichert (wie die Themenwahl).

**Commits:**
```
Config: connect_bell in AppearanceConfig
MainWindow: Connect bell toggle in the Appearance menu
```

---

## Teil C — Der Ton

- `MainWindow._ring_connect_bell()` — **einzige** Stelle, die den Ton
  erzeugt: `QApplication.beep()` (Windows: Systemklang „Standard-Piepton";
  keine zusätzliche Abhängigkeit, keine Audiodatei).
- Aufgerufen aus dem `subscribe_events`-Callback bei `"connected"`, wenn
  `connect_bell` an ist. Ein- und ausgehende Verbindungen klingeln gleich.
- Im Abschlussbericht vermerken: Ist unter Windows der Systemklang
  „Standard-Piepton" stumm geschaltet, bleibt `beep()` still — das ist
  keine App-Einstellung.

**Commit:** `MainWindow: ring the bell on a new connect`

---

## Teil D — Tests (zuerst rot)

`_ring_connect_bell` wird im Test durch einen Zähler ersetzt.

- `$51 "CONNECTED to OE3GAS-1"` → genau **ein** Klingeln (heute keins =
  rot).
- verbose `*** CONNECTED to OE3GAS-1` → ein Klingeln.
- Host-Mode-Eintritt mit `CO41000OE3GAS-1` für einen schon bekannten
  Kanal → **kein** Klingeln; ebenso `CSTATUS`-Abgleich.
- Zweite `CONNECTED`-Meldung für einen bereits verbundenen Kanal → kein
  zweites Klingeln.
- `connect_bell = False` → kein Klingeln.
- Menüeintrag existiert, ist ankreuzbar, spiegelt die Config; Umschalten
  speichert.
- INI ohne Schlüssel → `True`.

**Commit:** `Tests: connect bell`

---

## Teil E — Hardware T159 (App, Gerät nach Wahl, Schritte PC 1 / PC 2)

1. PC 1: Host Mode, VHF Packet, Kanal 1: Connect `OE3GAS-1` (TinyBox).
   **Erwartet:** ein Ton bei „connected".
2. PC 2: QtTermTCP `OE3GAS-2` ruft `OE3GAS` an. **Erwartet:** ein Ton.
3. PC 1: Leave Host Mode, Ctrl+H. **Erwartet:** Chips verbunden, **kein**
   Ton (Abgleich).
4. PC 1: Appearance → Connect bell aus; erneuter Connect → **kein** Ton.
5. Danach wieder einschalten.

---

## Teil F — Doku

- `Testplan.md`: T159 OPEN.
- `Backlog.md`: P76.
- `docs/claude/`: „Connect-Ereignis ≠ Zustandsänderung: nur Link-Meldungen
  lösen es aus, der Abgleich nie."

**Commits:**
```
Testplan: T159 connect bell
Docs: connect event vs. state change
Docs: add P76 spec file
```

---

## Definition of Done

- roter Test vorher nachgewiesen, volle Suite grün
- `git grep -n "beep(" -- src` → genau eine Stelle
- **Push nach Freigabe**, Meldung mit Hash; `.\Sources2Text.ps1`