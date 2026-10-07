# PK232PY — Device Inventory

Inventory of the three physical PK-232(MBX) units used for hardware testing,
so a finding recorded anywhere in `CLAUDE.md`/`Backlog.md`/`Testplan.md` can
be traced back to the EPROM it actually came from.

> **Verwandtes Dokument:** `docs/PK232_firmware_matrix.md` beantwortet eine
> andere Frage — welcher Befehl in welcher Firmware-**Generation** existiert,
> unabhängig vom physischen Gerät. Diese Datei hier beantwortet: welches
> Gerät hängt gerade am Port, und was wurde an genau diesem Gerät gemessen.

**Governing rule (P37, CLAUDE.md §"UI / PyQt6" — see there for the full
text):** a measured finding is valid for the device it was measured on.
Where behaviour differs between two runs, check the firmware/device first,
before assuming the code changed or the earlier run was wrong.

---

## Inventory

| Gerät | Release (Banner) | Generation | PACTOR | MailDrop | Prompt-Klammer | Letzte Messung | Besonderheiten |
|---|---|---|---|---|---|---|---|
| **A** | 13.SEP.95 | PACTOR | ja | ja | rund | 02.10.2026 (T152, T156) | Quelle aller `CLAUDE.md` "Known Gotchas"-Befunde bis 22.09.2026 (Mnemonics, MailDrop-Ablauf, Packet-/Channel-Verhalten). `MI` = MFILTER (T115). |
| **B** | 01.AUG.91 | MBX | nein | ja | eckig | 24.09.2026 (T119, P37) | MDCHECK hat kein Host-Mode-Kürzel (T118, wie Gerät A). Volles MailDrop-Protokoll (`L`/`S`/`SB`/`R`/`K`/`B`/`<`-Fremdabsender) 10/10 PASS, identisch zu Gerät A. |
| **C** | 30.DEC.88 | BASE | nein | **nein** | unbekannt | 23.09.2026 (Betreiberangabe, PuTTY) | Nie über die App/`hw_check.py` angeschlossen — MailDrop-Abwesenheit direkt mit einem Terminalprogramm geprüft, nicht gemessen über das hier dokumentierte Werkzeug. Ab P37 (24.09.2026) erkennt die App das automatisch über `SerialManager.detect_maildrop()` (`MAILDROP`-Abfrage, verbose, vor dem Upload — niemals `MDCHECK`); noch nicht an diesem Gerät verifiziert. |

**Gerät C, Release (T180, 06.10.2026):** Das Banner druckt `Release 30.DEC.88` (`hw_logs/20261006_fw_scan_C.log`, `AEA PK-232 Data Controller`, `Checksum $80`) - nicht die frühere Abschrift `30.12.1988`. Wie bei Gerät A (11.09.1995 -> 13.SEP.95) gilt ab jetzt überall der Bannerwert (Matrix-Spalten, `comm/devices.py`, Register, Tests; ein Test prüft, dass jeder Release-Schlüssel das Bannerformat `DD.MMM.YY` hat). Ältere Einträge (`PK232_firmware_matrix.md`, P37/P78/P80/P85/P88-Specs, historische Testplan-/Backlog-/Gotcha-Einträge) nennen weiterhin `30.12.1988` und sind bewusst nicht umgeschrieben.

**Aus- und Einschalten, Werkszustand (P89b, Handtest Gerät A, 07.10.2026):** Kein Gerät hat eine
Pufferbatterie (richtig), aber ein Aus-/Einschalten stellt **nicht immer** den Werkszustand her: nach kurzer
Pause kam das Banner ohne Zusatzzeile und `MYSELCAL` blieb `NONE`; nach längerer Pause kam zuerst
`PK-232M is using default values.`, danach war `MYSELCAL` `none`. Werkszustand gilt nur, wenn diese Zeile vor dem
Banner kam (`constants.is_factory_banner()`): Geräte A und B drucken `PK-232M is using default values.`, Gerät C
`PK-232 is using default values.` (ohne M, `hw_logs/20261006_fw_scan_C.log`); ein RESTART-Banner hat sie nie. Wie lange
die Pause sein muss, ist nicht gemessen (der Scanner verlangt 10 s als Startwert). `MYSELCAL` lässt sich an A und B
mit keinem Befehl löschen (Handtests des Betreibers, 07.10.2026, je Zeile ein eigener Test an A und an B:
`MYSELCAL %` -> `?callsign`, `MYSELCAL &` -> `?callsign`, `MYSELCAL OFF` -> `?callsign`, `MYSELCAL NONE` -> `now NONE`, ein
gültiger Selcal), nur durch einen Werkszustands-Start. Der Scanner setzt ein nicht gesetztes MYSELCAL deshalb nie und schaltet das
Gerät dafür nicht aus (ein Scan-Kit-Gerät kann eine Pufferbatterie haben).

**Release-Spalte, Genauigkeit:** Gerät B ist die einzige Zeile mit einer
byte-genauen Banner-Erfassung (P30/P37, `hw_logs/20260924_181446_maildrop_session.log`)
— der Wert steht hier exakt wie im Banner (`Release 01.AUG.91`), unverändert,
siehe `SerialManager.tnc_release`. **Gerät A** hat seit dem 02.10.2026 (T152,
`hw_logs/20261002_172135_host_params_probe.log`, Banner: `release=13.SEP.95
pactor=yes`; Betreiber bestätigt) ebenfalls eine Banner-Erfassung - die frühere
Abschrift `11.09.1995` ist damit ersetzt. Ältere Dokumente (historische Einträge
in `Testplan.md`, `Backlog.md` und der P37-Spec) verwenden weiterhin die frühere
Abschrift 11.09.1995 und sind bewusst nicht umgeschrieben; `PK232_firmware_matrix.md`
und `docs/claude/GOTCHAS_SERIAL_TNC.md` sind korrigiert. Geräte A (frühere Messungen) und C stammen aus älteren,
vom Betreiber transkribierten Angaben (kanonisches `DD.MM.YYYY`, vor der
byte-genauen Banner-Erfassung entstanden) — keine wörtliche Banner-Erfassung
und nicht nachträglich vereinheitlicht, um nichts zu erfinden.

---

## Wie ein neuer Befund einzuordnen ist

1. Vor jedem `hw_check.py`-Lauf mit echter Hardware: welches der drei
   EPROMs steckt gerade im TNC? (Der `device:`-Zeile im Log glauben, nicht
   raten — sie stammt direkt aus dem Banner, siehe
   `SerialManager.tnc_release`/`has_pactor`/`tnc_defaults`.)
2. Jeder Eintrag in `CLAUDE.md`s "Known Gotchas", der aus einer echten
   Hardware-Messung stammt, sollte das Gerät nennen (A/B/C) — nicht nur
   das Datum. Ältere Einträge (vor P37) tun das nicht durchgängig; siehe
   `CLAUDE.md`s "Bestehende Befunde zuordnen"-Regel unter "TNC / firmware
   v7.1" für die pauschale Zuordnung nach Datum.
3. Verhält sich ein Gerät anders als erwartet: zuerst hier nachsehen, ob es
   überhaupt dieselbe Generation/dasselbe EPROM ist, bevor der Code
   verdächtigt wird.

---

## Firmware-Fingerabdruck (P78) - Eindeutigkeit

Wurde beim Verbinden kein Banner gesehen (TNC schon wach), erkennt die App die
Generation am Befehl `EXPERT` (`comm/devices.py`, `KNOWN_DEVICES`):

| Gerät | verbose `EXPERT` | Host `EX` (Abfrage) |
|---|---|---|
| B (01.AUG.91) | `?What?` | Fehlercode `$07` |
| A (13.SEP.95) | `ON`/`OFF` | `EXY`/`EXN` |
| C (30.DEC.88) | `?What?` (T180) | ungemessen (erwartet `$07`) |

**`EXPERT` allein trennt nur A von B/C:** Gerät C antwortet wie B mit `?What?` (T180) - die Antwort ist
mehrdeutig. Dann folgt EINE zweite Abfrage, und welche, wird aus der Befehls-Matrix abgeleitet
(`devices.discriminating_command()`: ein Parameter, dessen Zelle auf allen Kandidaten gemessen ist und sich
unterscheidet - heute `MAILDROP`: auf 01.AUG.91 vorhanden, auf 30.DEC.88 `?What?`; im Host Mode über das
gemessene Kürzel `MV` aus der Matrix). Nichts davon ist in `devices.py` fest codiert. Kein
unterscheidender Befehl, unbrauchbare Antwort oder weiter mehrdeutig: `infer_release()` liefert `None`,
nie eine Vermutung. **Der Fingerabdruck gilt nur, solange die Matrix die Kandidaten unterscheiden kann** - ein
weiteres Gerät derselben Generation braucht `KNOWN_DEVICES` und die Matrix gemeinsam.

## Offene Punkte

- Gerät C wurde nie über `hw_check.py` angeschlossen — Prompt-Klammernform,
  MDCHECK-Verhalten und jedes andere `hw_check`-Ergebnis für dieses Gerät
  sind offen.
- `SerialManager.detect_maildrop()` (P37) noch nicht gegen echte
  Gerät-C-Hardware verifiziert — software-/mock-geprüft
  (`test_serial_manager.py`, `test_params_uploader.py`,
  `test_params_maildrop_dialog.py`). Erster echter Test: App mit Gerät C
  starten, Upload beobachten (kein `?What?` für MailDrop-Befehle
  erwartet) und prüfen, dass MailDrop-Button/-Dialog gesperrt bleiben,
  siehe `Testplan.md`.
- `MI` auf Gerät B (MFILTER oder MDCHECK?) — siehe
  `docs/PK232_firmware_matrix.md` §2a, "Kandidat für einen echten
  Generationsunterschied".
