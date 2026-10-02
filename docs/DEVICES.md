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
| **C** | 30.12.1988 | BASE | nein | **nein** | unbekannt | 23.09.2026 (Betreiberangabe, PuTTY) | Nie über die App/`hw_check.py` angeschlossen — MailDrop-Abwesenheit direkt mit einem Terminalprogramm geprüft, nicht gemessen über das hier dokumentierte Werkzeug. Ab P37 (24.09.2026) erkennt die App das automatisch über `SerialManager.detect_maildrop()` (`MAILDROP`-Abfrage, verbose, vor dem Upload — niemals `MDCHECK`); noch nicht an diesem Gerät verifiziert. |

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
