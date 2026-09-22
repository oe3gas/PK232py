# Claude Code Prompt — P17: Messungen für SIAM, T111 und T112

> Ablage: `docs/P17_HW_Measure_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher `CLAUDE.md`, `Backlog.md`, `Testplan.md` lesen.

---

## Warum eine Messung und kein Fix

Der P16.3-Befund zu `SignalMode.handle_frame()` lässt sich nicht beheben,
ohne vorher am Gerät zu messen. Im Code stehen **zwei widersprüchliche
Annahmen** nebeneinander:

- Modul-Docstring: SIAM-Ergebnisse kommen als `$4F` CMD_RESP
- `handle_frame()`: behandelt zusätzlich `$50` LINK_MSG, Kommentar
  „SIAM liefert Ergebnisse als LINK_MSG ($50)"

Und zwei verschiedene Ausgabeformate:

- Docstring (STABO-Handbuch Kap. 10): `BAUDOT 45 170`
- Mockup `signal_screen.py`: `0.47: 50 Baud, Baudot, RXREV OFF`

Ein Filter „nur SIAM-Ergebnisse durchlassen" setzt voraus, dass man ein
SIAM-Ergebnis erkennt. Das weiß derzeit niemand. **Erst messen, dann
ändern** — die Lehre aus T86.

Dieses Paket ändert **keinen Code unter `src/pk232py/`**.

---

## P17.1 — `tools/hw_check.py`: Subcommand `siam`

**Reiner Empfang, keine Aussendung.**

1. Konsolenhinweis: Empfänger auf ein bekanntes FSK-Signal abstimmen
   (Amateur-RTTY 45 Bd / 170 Hz ist der einfachste Fall; Betriebsart,
   Baudrate und Shift des Signals dem Operator vorab abfragen und
   protokollieren, damit das Ergebnis vergleichbar ist). Weiter erst nach
   Bestätigung.
2. Host Mode betreten, anstehende Frames abräumen
   (`drain_pending_frames()`, P16)
3. `SignalMode().get_activate_frames()` senden — **die echten Frames der
   Anwendung**, nicht nachgebaut
4. **60 Sekunden lang jeden eintreffenden Frame protokollieren**: CTL-Byte,
   Frame-Typ (`FrameKind`), Kanal, Daten roh in Hex und als Text. Keine
   Filterung, keine Auswertung — das ist der Zweck der Messung
5. Zwischenstand alle 10 Sekunden auf der Konsole („n frames so far")
6. Nach Ablauf oder bei Ctrl-C: in die vorherige Betriebsart zurück, Host
   Mode verlassen (im `finally`)
7. Zusammenfassung: Anzahl Frames je `FrameKind`, und jeder Frame, dessen
   Text wie ein Analyseergebnis aussieht (enthält „Baud" oder eine der
   Betriebsartbezeichnungen aus `KNOWN_MODES`), vollständig mit Typ und Hex

Der Operator vergleicht danach das angezeigte Ergebnis mit dem bekannten
Signal und trägt es ein.

Aufruf:

```
python tools/hw_check.py --port COM6 siam
python tools/hw_check.py --port COM6 siam --seconds 120
```

Standardlänge 60 s, mit `--seconds` änderbar. `siam` gehört **nicht** zu
`all`, weil es einen abgestimmten Empfänger braucht.

---

## P17.2 — `tools/hw_check.py`: Subcommand `t111`

PASSALL am Gerät schalten und prüfen, dass PASS unberührt bleibt. Keine
Aussendung.

1. Host Mode, Puffer abräumen
2. `PX` und `PS` abfragen → Ausgangswerte merken (erwartet `PXN`,
   `PS$16`)
3. `PX Y` senden (über `build_command(b'PX', b'Y')`)
4. `PX` abfragen → erwartet `Y`
5. `PS` abfragen → muss **unverändert** `$16` sein
6. im `finally`: `PX` auf den Ausgangswert, mit Nachweis (P15.2)

Ergebnis `PASS`, wenn PASSALL umschaltet und PASS gleich bleibt.

Ergänzend einen Unit-Test (nicht Hardware), der sicherstellt, dass
`t111` für den Schaltbefehl **denselben Mnemonic** verwendet wie der
`toggle_map`-Eintrag von `btn_passall` in `main_window.py` — sonst misst
das Werkzeug etwas anderes als das, was die Anwendung sendet.

---

## P17.3 — `tools/hw_check.py`: Subcommand `t112`

Die vermutete Lücke aus P16: beim Wechsel VHF → HF sendet der HF-Modus
kein `MX`/`SL`, HF-Packet liefe danach mit den VHF-Werten weiter. Keine
Aussendung.

1. verbose: `MAXFRAME`, `SLOTTIME`, `VHF`, `HBAUD` abfragen →
   Ausgangswerte merken
2. Host Mode betreten, Puffer abräumen
3. **die echten Frames** senden, in der Reihenfolge, in der die Anwendung
   sie bei einem Wechsel HF → VHF → HF sendet:
   - `VHFPacketMode().get_activate_frames()` und `.get_init_frames()`
   - `VHFPacketMode.vhf_off_frame()` (Verlassen von VHF, T51)
   - `HFPacketMode().get_activate_frames()` und `.get_init_frames()`

   Die Reihenfolge aus `_on_mode_selected()` in `main_window.py` ablesen
   und im Protokoll dokumentieren, nicht annehmen
4. Host Mode verlassen
5. verbose: `MAXFRAME` und `SLOTTIME` abfragen
6. im `finally`: alle vier Ausgangswerte zurück, mit Nachweis

Auswertung:

| MAXFRAME / SLOTTIME nach dem Wechsel | Ergebnis |
|---|---|
| HF-Werte (Config: 1 / 30) | `PASS` — keine Lücke, Backlog-Eintrag schließen |
| VHF-Werte (4 / 10) | `FAIL` — Lücke bestätigt, Werte im Protokoll |
| anders | `INCONCLUSIVE` mit allen Werten |

Die HF-Sollwerte aus der geladenen Konfiguration lesen, nicht fest
eintragen.

**Commit:** `Tools: hw_check siam, t111, t112 measurements`

---

## P17.4 — Tests

Für die logischen Teile, ohne serielle Schnittstelle:

- die Frame-Folge von `t112` wird aus den echten Modusklassen gebaut
  (Test prüft, dass sie mit dem übereinstimmt, was
  `get_activate_frames()`/`get_init_frames()` liefern)
- die Mnemonic-Übereinstimmung `t111` ↔ `toggle_map` (siehe P17.2)
- die Klassifikation der SIAM-Zusammenfassung (welche Frames als
  „sieht aus wie Ergebnis" markiert werden) mit beiden bekannten
  Formatbeispielen aus Docstring und Mockup

**Commit:** `Tests: hw_check siam, t111, t112 logic`

---

## P17.5 — Dokumentation

### `docs/HW_Solo_Tests.md`

Die drei neuen Subcommands ergänzen: Vorbereitung (für `siam` der
abgestimmte Empfänger und die Angaben zum bekannten Signal), Aufruf,
Rückfragen, Auswertung. Abhaktabelle erweitern.

### `Testplan.md`

- T111, T112 auf das Werkzeug verweisen
- neuer Fall für die SIAM-Messung (nächste freie Nummer), Status OPEN
- **Kosmetik:** bei T86 `--port COM3` → `COM6`; in der Änderungstabelle
  die Datumsformate vereinheitlichen (ISO `2026-09-21`, wie der Rest der
  Tabelle)

### `Backlog.md`

Beim SIAM-Eintrag vermerken: Fix hängt an der Messung aus P17, weil
Frame-Typ und Ausgabeformat widersprüchlich dokumentiert sind (Docstring
vs. Code-Kommentar vs. Mockup).

**Commit:** `Docs: SIAM measurement, T111/T112 tooling, cosmetic fixes`

---

## Definition of Done

- `python -m pytest` grün
- `--dry-run siam`, `--dry-run t111`, `--dry-run t112` zeigen die
  geplanten Frames in Hex
- Kein Code unter `src/pk232py/` verändert
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"
- Danach vom Operator am Gerät: `t111`, `t112`, und `siam` mit einem
  bekannten Signal
