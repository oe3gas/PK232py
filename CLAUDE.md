# CLAUDE.md — PK232PY

> Kurzer Einstieg für Claude Code. Details stehen in `docs/claude/` und `docs/`;
> lies sie nur, wenn die Aufgabe das jeweilige Thema berührt (Tabelle unten).
> Last updated: 2026-09-29

## Projekt

**PK232PY** — Python/PyQt6-Terminalanwendung für den AEA PK-232MBX (Multi-Mode-TNC,
Amateurfunk). Ersetzt PCPackRatt (Win9x, nicht mehr gepflegt).

- Repo: `github.com/oe3gas/PK232py`, lokal `E:\PK232\pk232py_repo`, Lizenz GPL v2
- Entwickler: OE3GAS (Gerhard), Ziel: Beta-Release
- Hardware: PK-232MBX, Firmware v7.1, Prolific-USB-Seriell, 9600 Baud
  (drei Testgeräte A/B/C, siehe `docs/DEVICES.md`)
- Modi (je ein Screen im `QStackedWidget` des `MainWindow`): Baudot RTTY, ASCII RTTY,
  AMTOR, CW/Morse, PACTOR I, NAVTEX, Signal/SIAM, HF FAX, HF Packet, VHF Packet (AX.25/APRS)

## Technik

Python 3.10+ (CI 3.10/3.11/3.12), PyQt6, pyserial, INI via `configparser`, SQLite (QSO-Log),
Windows 11 + PowerShell, venv im Repo-Root (`.venv`), Git-Branch `main`.

## Build / Test

```
.venv\Scripts\python.exe -m pytest src/pk232py/tests/<datei>.py      # während der Arbeit: nur betroffene Datei
.venv\Scripts\python.exe -m pytest --durations=15                    # vor jedem Push: gesamte Suite
```

- **Immer `.venv\Scripts\python.exe`**, nicht das System-`python` (3.14, ohne PyQt6-DLLs → irreführender ImportError).
- Kein einzelner Test über 1 s ohne Docstring-Begründung.
- Tests laufen headless (`QT_QPA_PLATFORM=offscreen`); `tests/conftest.py` isoliert INI-Config und QSettings
  und zerstört jedes `MainWindow` — nie `close()` auf einem `MainWindow` mit Stub-Serial, der `is_connected=True` meldet (hängt).
- Kein Push ohne Freigabe des Betreibers.

## Workflow

- `pk232py_sources.txt` (erzeugt von `Sources2Text.ps1`, deckt `src/pk232py/**/*.py` und `tools/**/*.py` ab) ist die
  **Code-Wahrheit**; nach Codeänderungen neu erzeugen. Die Doku-Dateien (`CLAUDE.md`, `docs/`) sind **nicht** im Export
  und werden in eigenen Commits gepflegt.
- Keine Patch-Skripte, keine Zwischenkopien; ein Modul pro Commit.
- Dateien in PowerShell nur mit `UTF8Encoding($false)` (UTF-8 ohne BOM) schreiben, nie per PowerShell-Copy deployen.
  `main_window.py` kennt ein Append-Artefakt (No-op-String mit Mojibake, §10) — Details: `docs/claude/GOTCHAS_UI_AND_TOOLING.md`, „Dead Code“.
- Git: Datei heißt `CLAUDE.md` (Großschreibung; Rename 2026-09-29).

## Repository-Struktur (Kurzform; vollständiger Baum: Anhang in `docs/claude/PROTOCOL_AND_ARCHITECTURE.md`)

```
src/pk232py/
  config.py, main.py, mode_manager.py
  comm/       constants, frame, hostmode, serial_manager, link_table, link_status, params_uploader
  modes/      base_mode + je Betriebsart (rtty_baudot, amtor, morse, pactor, fax, packet_hf/vhf, aprs_decoder, ...)
  ui/         main_window.py, screens/ (ein Screen je Modus, packet_screen.py, tx_controller.py,
              screen_focus_controller.py), dialogs/
  help/       Markdown-Hilfe (help_viewer.py, HELP_TOPICS)
  maildrop/   protocol, session, archive (TNC-Mailbox)
  log/, macros/, tests/
tools/        Standalone-Dev-Tools (hw_check.py, FAX-WAV-Generator/-Decoder) — NICHT Teil der ausgelieferten App
docs/         Specs (P-Nummern), Backlog.md, Testplan.md, State-Machine-Docs
docs/claude/  Aus CLAUDE.md ausgelagerte Details (siehe unten)
```

## Harte Regeln (nie brechen)

1. **Serielle Kommunikation: immer direktes `port.write()`/`read_until()`. NIE Worker-Thread oder Queue für Host-Mode-Frames.**
   Der Windows-Prolific-Treiber liefert ACKs nur bei direktem `read()`.
2. **Nach dem Host-Mode-Subprozess immer ein frisches `serial.Serial()`-Objekt** (sonst 20–35 s Verzögerung);
   Port-Konfiguration `xonxoff=False` (XON `$11` muss für `HOST 3` ungefiltert durchgehen), DTR/RTS asserted.
3. **GUI-Thread-Sicherheit:** Widgets nur im GUI-Thread anfassen; aus Hintergrund-Threads ausschließlich über
   Signals/Slots. *Bekannte offene Verletzung:* der Thread `PK232-ParamUpload` (`MainWindow._run_param_upload()`)
   ruft `_vt_append()`, `_log_monitor()` und `_vt_input.setFocus()` direkt auf — potenzieller Segfault; nicht kopieren, bei Gelegenheit auf Signals umstellen.
4. **Vor jedem eigenen synchronen Port-Read den Lesepfad exklusiv übernehmen** (`_take_over_read_path()`), sonst
   verschluckt der `ReaderThread` die Antworten.
5. **Ein Echo ist keine Antwort.** Im Verbose-Modus echot der TNC alles, auch binäre Frames. Erfolgschecks müssen
   etwas prüfen, das nur der TNC selbst senden kann (z. B. Wertbyte in der Antwort).
6. **Host-Mode-Mnemonics nie raten** — gegen TRM 4.2.2 bzw. echte Messung (`tools/hw_check.py`) prüfen; bei
   Widerspruch gewinnt die Messung. Mnemonics sind eine feste Tabelle (PASSALL=`PX`, PASS=`PS`, MYCALL=`ML` …).
7. **Parameter-Upload nur im Verbose-Modus**, vor dem Host-Mode-Eintritt (im Host Mode gibt es keinen `cmd:`-Prompt).
   `is_host_mode` ist nur die Software-Annahme; `verbose_confirmed` braucht aktive Bestätigung in dieser Session.
8. **`CALIBRATE` und `TRANS`/`CONMODE TRANS` nie automatisch senden** (weder App noch `tools/`) — nur auf ausdrückliche
   Operator-Aktion. (Es gibt aktuell keine `NEVER_AUTO`-Konstante im Code; die Regel ist eine Vorgabe.)
9. **`_send_active` wird nur von `_on_screen_send(True)` gesetzt** und ist unabhängig vom Qt-Button-Zustand;
   AMTOR-Zustand nie daraus ableiten (AMTOR hat keinen SEND-Button).
10. **Keine Umbenennung interner Bezeichner** (Attribute, Config-Keys, Mnemonics, Signale) — nur sichtbare UI-Texte ändern.
11. **Messbefunde gelten für das Gerät, an dem gemessen wurde** (A/B/C, `docs/DEVICES.md`) — Gerät/Firmware zuerst prüfen.
12. **Jeder `set_mode(...)`-Aufruf in `main_window.py` geht über `MainWindow._build_mode_instance()`**, sonst gehen
    Konfigurationswerte verloren.
13. **Keine Erfolgsmeldung ohne Beweis** (kein „connected“/„verified“ ohne aktive Bestätigung).
14. **Layout-/Geometrie-Behauptungen mit echtem `show()/resize()/processEvents()`-Test messen**, nicht nur Properties prüfen.
15. **`QTimer.singleShot(ms, cb)` mit Zugriff auf `self`-Widgets vermeiden** — geparenteten `QTimer(self)` verwenden.

## UI-Konventionen

- Alle UI-Texte **Englisch**; Identity-Felder (`lbl_mycall` …) sind `QLabel`, nicht `QLineEdit`.
- `Qt.FocusPolicy.NoFocus` auf **allen** `QPushButton`s (Tastatur bleibt im TX-Fenster).
- TX-Fokus initial per `QTimer.singleShot(0)`; Blockcursor über `style_tx_widget()`;
  `insertPlainText()` statt `append()` fürs Streaming; `\r` vor Anzeige filtern.
- Modus-Namen im Screen-Dict müssen exakt `ModeManager.ALL_MODES` entsprechen.
- Tastatur-Umleitung ins TX-Fenster: Eingabewidgets (`QLineEdit`, `QTextEdit`, `QComboBox`, `QAbstractSpinBox`)
  ausnehmen über `screen_focus_controller.is_keyboard_input_widget()`. Drei EventFilter-Ebenen
  (MainWindow app-weit → Screen → `ScreenFocusController` je Feld): `docs/Eventfilter_architecture.md`.
- Tooltips zentral in `tooltips.py` (`TOOLTIPS` + klassenspezifisch `SCREEN_TOOLTIPS`); `apply_tooltips(self)` am Ende von `__init__`.
- „Connect“ immer eindeutig benennen (TNC-Seriell vs. Station); TNC-Aktionen leben nur im TNC-Menü.
- Packet: Connect passiert im `ChannelChip` (Inline-Editor); Kanal 0 = UI/Unproto-Kanal; Chip-Zustand kommt
  ausschließlich aus der `LinkTable`-Subscription (`comm/link_table.py`).

## TxController (Kurz)

`tx_controller.py` ist die modus-agnostische ACK-getriebene TX-Zustandsmaschine (Baudot, ASCII, Morse, AMTOR).
`_is_txctrl_mode()` in `main_window.py` ist die einzige Wahrheit, welche Modi darüber laufen. Morse ist echo-gepaced (EAS).
Packet nutzt **keinen** TxController und kein `[^D]`. Details: `docs/TX_STATE_MACHINE.md`, `docs/claude/PROTOCOL_AND_ARCHITECTURE.md` §11.

## Aktueller Stand

Alle 10 Opmode-Screens implementiert; Packet mit Channel-Bar/LinkTable (P67, 2026-09-28), MailDrop-Dialog und Archiv,
FAX-Live-Decode, APRS-Decoder, Help-System, Tooltip-System. Offene Arbeit steht **ausschließlich** in `docs/Backlog.md`
(u. a. P63 APRS-Modus wartet auf T138–T140; P64 für PACTOR/AMTOR als P67-Folgepaket offen). Testfälle/Ergebnisse: `docs/Testplan.md`.

## Ausgelagerte Details

Keine `@`-Imports — die Dateien nur bei Bedarf öffnen.

| Datei | Lesen, bevor … |
|---|---|
| `docs/claude/GOTCHAS_SERIAL_TNC.md` | `serial_manager.py`, Host-Mode-, Init-/Detection- oder MailDrop-Code geändert wird (auch Mnemonic-Tabelle, Firmware-/Geräte-Messungen) |
| `docs/claude/GOTCHAS_PACKET.md` | Channel-Modell, ChannelBar, Link table, MHEARD, Packet-RX-Anzeige angefasst wird (auch PACLEN/UNPROTO/APRS) |
| `docs/claude/GOTCHAS_UI_AND_TOOLING.md` | Screens, Dialoge, FAX, Parameter-Dialoge, Tests oder `tools/` geändert werden |
| `docs/claude/PROTOCOL_AND_ARCHITECTURE.md` | EventFilter, Zustandsautomaten, TxController oder TNC-Protokollfakten geändert werden; enthält den vollständigen Repo-Baum |
| `docs/claude/STATUS_HISTORY.md` | nur bei Fragen zur Historie (Sprints P16–P67) — nicht standardmäßig lesen |
| `docs/DEVICES.md`, `docs/PK232_firmware_matrix.md` | Verhalten zwischen Geräten/Firmwares abweicht |
| `docs/OPMODE_SWITCH_STATE_MACHINE.md`, `docs/SERIAL_CONNECTION_STATE_MACHINE.md`, `docs/TX_STATE_MACHINE.md` | Modus-Wechsel, Verbindungsaufbau oder TX-Ablauf geändert wird |
| `docs/ui_design.md` | UI-Layout/Theme/Buttons geändert werden |
| `docs/Backlog.md`, `docs/Testplan.md`, `docs/P*_Spec.md` | eine neue Aufgabe beginnt / ein Paket (P-Nummer) referenziert wird |

Hardware-Referenz (nicht im Repo, im Claude-Projekt-Knowledge): TRM `AEA-PK-232-TechnicalReferenceManual.pdf`, `PPWIN.HLP`.
**Neue Erkenntnisse** (Gotchas, Messungen) gehören in die passende Datei unter `docs/claude/`, nicht hierher.
CLAUDE.md bleibt unter ca. 200 Zeilen.

## Lernmodus

Der Entwickler lernt am Code mit. Jeder nicht triviale Codeblock bekommt eine kurze Erklärung:
**Was** er tut, **warum** dieser Ansatz (statt Alternativen), und **PyQt6-/PK-232-spezifische Fallstricke**.
Einfache, bewährte Muster vor cleveren Lösungen.
