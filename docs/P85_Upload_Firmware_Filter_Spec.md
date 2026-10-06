# Claude Code Prompt — P85: Init-Upload sendet nur Befehle, die die Firmware kennt

> Ablage: `docs/P85_Upload_Firmware_Filter_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Grundlage: `main` (nach P84). Backlog „Init-Upload sendet Befehle, die die
> Firmware nicht kennt". Doku nach `docs/claude/`.

---

## Befund (gemessen)

Der Init-Upload (`ParamsUploader.upload()`) sendet für jede Firmware dieselbe
Befehlsliste. Verbose Antwort `?What?` (Befehl unbekannt), jeweils mit
Banner:

| Release | Gerät | `?What?` beim Upload / bei der Abfrage | Belege |
|---|---|---|---|
| `01.AUG.91` | B | `EXPERT` (ON und OFF), `MYPTCALL`, `PTHUFF`, `PT200`, `PTOVER`, `ARQTOL`, `MOPT` | T168 A/B/C (`20261003_220612`, `20261004_124240`, `20261004_122301`), T155, T160 |
| `13.SEP.95` | A | keiner (FULLDP inzwischen entfernt, P73) | T161 (`20261003_145006`) |
| `30.12.1988` | C | ungemessen | — |

Folge auf Gerät B: acht abgelehnte Befehle bei jedem Init, Zeit und
Log-Rauschen; die Einträge stehen außerdem als Fehler in der
Upload-Prüfung.

---

## Teil A — Eine Tabelle: was eine Firmware nicht kennt

`comm/devices.py` (dort liegt `KNOWN_DEVICES`, P78) bekommt je Gerät ein
Feld `unknown_verbose: frozenset[str]` mit den Befehlsnamen aus der Tabelle
oben und je Eintrag einen Kommentar mit Testnummer und Log.

- Gerät A: leere Menge (gemessen).
- Gerät C: `None` = ungemessen.
- Funktion `unknown_commands(release) -> frozenset[str] | None`:
  `None` bei unbekanntem oder ungemessenem Release.

**Commit:** `devices: verbose commands each firmware does not know`

---

## Teil B — Upload filtert

- `ParamsUploader.upload()` lässt Befehle weg, deren Name in
  `unknown_commands(tnc_release)` steht. Release-Quelle wie P72/P78 (Banner
  oder `inferred`).
- `None` (unbekannte/ungemessene Firmware) → **alles** senden wie heute.
- Eine Zeile im Terminal und im Log: `[SYS] 8 commands skipped - not
  supported by 01.AUG.91 (EXPERT, MYPTCALL, …)`.
- `verify()` und die P81-Zurückstellung berücksichtigen nur gesendete
  Befehle.
- **Nicht** filtern: Kommt trotzdem ein `?What?` für einen Befehl, der
  nicht in der Tabelle steht, wird er wie bisher gemeldet — das ist ein
  neuer Befund, kein Fall zum Verschweigen.

**Commit:** `ParamsUploader: skip commands the firmware does not know`

---

## Teil C — Parametermasken

Bedienelemente für Befehle aus `unknown_commands(release)` werden
ausgegraut, Tooltip „Not supported by firmware <release> (T…)". Betrifft
z. B. ARQTOL und MOPT in AMTOR/Misc bzw. die PACTOR-Felder auf Gerät B
(prüfen, ob die PACTOR-Maske auf Geräten ohne PACTOR ohnehin gesperrt ist —
dann nichts doppelt sperren). Werte bleiben in der Konfiguration erhalten.

**Commit:** `Params: grey out settings the firmware does not support`

---

## Teil D — Tests (zuerst rot)

- Release `01.AUG.91`: Upload-Schreibprotokoll enthält keinen der acht
  Befehle; Terminalzeile „8 commands skipped".
- Release `13.SEP.95`: Liste unverändert gegenüber heute.
- Release `None` und `30.12.1988`: alles gesendet.
- `verify()` meldet für Gerät B keine Abweichung mehr wegen ausgelassener
  Befehle.
- Ein `?What?` auf einen Befehl außerhalb der Tabelle wird weiter gemeldet.
- Maske AMTOR auf `01.AUG.91`: ARQTOL ausgegraut mit Tooltip.

**Commit:** `Tests: upload filtered per firmware`

---

## Teil E — Hardware T173

1. Gerät B, Start mit Banner: Terminal zeigt „8 commands skipped …", **kein**
   `?What?` im Upload-Teil von `pk232py.log`.
2. Gerät B, Neustart ohne Banner (`inferred`): dasselbe.
3. Gerät A, Start mit Banner: kein Befehl ausgelassen, kein `?What?`.

---

## Definition of Done

- rote Tests vorher nachgewiesen, volle Suite grün
- Tabelle an einer Stelle (`devices.py`), Belege je Eintrag
- `Testplan.md`: T173 OPEN; `Backlog.md`: Eintrag erledigt
- **Push nach Freigabe**; `.\Sources2Text.ps1`