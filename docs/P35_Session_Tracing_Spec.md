# Claude Code Prompt — P35: Mitschnitt in der Sitzung, CR statt CRLF, ehrliche Wakeup-Erkennung

> Ablage: `docs/P35_Session_Tracing_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Fixture: `hw_logs/20260923_204041_maildrop_session.log`.

---

## Befunde (23.09.2026, 20:40, Gerät B — MBX 1991)

### Erfolge
- `open()` **PASS**: Host Mode verlassen, `Ctrl-C`, `MDCHECK`,
  Mailbox-Prompt erkannt (`bracket='square'`, `free=18340`)
- Der Rückweg aus P31 läuft vollständig: `B` → Host Mode betreten →
  `HPOLL` bestätigt → `CLOSED`
- Die Klammerform steht in der Zusammenfassung

### Offen: `L` wird mit `*** What?` beantwortet
Gesendet wurde `4C 0D` (`L` + CR) — der Befehl steht im Prompt selbst
(`B,E,K,L,R,S`) und lief auf Gerät A einwandfrei.

Drei mögliche Ursachen, aus dem Protokoll **nicht** unterscheidbar, weil
die Sitzung ihre Empfangsdaten nicht mitschreibt:

1. **Überzähliges LF:** `MDCHECK` wird mit `\r\n` gesendet
   (`4D 44 43 48 45 43 4B 0D 0A`). Der TNC tritt beim CR in die Mailbox
   ein; das LF käme dort als leere Eingabe an und würde mit `*** What?`
   beantwortet. Die Meldung gehörte dann zu `MDCHECK`, nicht zu `L`.
   Dafür spricht, dass zwei `prompt_info` kurz hintereinander kommen.
2. Firmwareunterschied der MBX-Generation.
3. Verschmolzene Antworten: `parse_error()` findet das `*** What?` im
   gemeinsamen Puffer beider Befehle.

### Nebenbefund: Wakeup-Erkennung meldet Unzutreffendes
```
>> hex=2A                       (wakeup '*')
<< hex=2A 5C 0D 0A              ('*\' CR LF -- kein cmd:)
[serial_manager] TNC at cmd: prompt
```
Die Antwort enthält **kein** `cmd:`, die Meldung behauptet es trotzdem.
Die Einordnung des Prüfstands war in diesem Punkt genauer („banner
truncated").

---

## P35.1 — Mitschnitt in der Sitzung

`MailDropSession` bekommt einen optionalen Mitschnitt-Rückruf, wie ihn der
Rekorder schon hat:

```python
trace: Callable[[str, bytes], None] | None = None   # ("tx"|"rx", data)
```

- vor jedem Senden und nach jedem Lesen aufrufen, mit den **Rohbytes**
- ist kein Rückruf gesetzt, ändert sich nichts (die Anwendung bleibt
  unberührt)
- `tools/hw_check.py` setzt den Rückruf und schreibt wie gewohnt
  `>> hex=… text=…` / `<< hex=… text=…` mit sichtbaren Steuerzeichen

Damit zeigt der nächste Lauf, was nach `MDCHECK` und nach `L` tatsächlich
zurückkam — und welche der drei Ursachen zutrifft.

**Commit:** `MailDrop session: optional raw trace callback`

---

## P35.2 — Befehle mit CR abschließen

Das Handbuch schließt Befehle mit CR ab; das LF ist eine Zugabe der
Software.

- in `session.py` **alle** Mailbox-Befehle und `MDCHECK` mit `\r`
  abschließen, nicht `\r\n`
- Ausnahme prüfen und begründen: Falls eine Stelle das LF nachweislich
  braucht (Mitschnitt zeigt es), dort belassen und kommentieren
- im Commit-Text festhalten, dass die bisherigen erfolgreichen Läufe auf
  Gerät A mit `\r\n` liefen — die Änderung ist also nicht rückwirkend als
  Fehlerbehebung zu verstehen, sondern als Angleichung an das Handbuch

**Commit:** `MailDrop session: terminate commands with CR only`

---

## P35.3 — Antwortgrenzen sauber ziehen

Damit Ursache 3 ausgeschlossen ist:

- vor dem Senden eines Mailbox-Befehls den Empfangspuffer leeren und das
  im Mitschnitt vermerken, falls dabei noch Bytes anfielen
  (`INFO: discarded N bytes before command`)
- `parse_error()` nur auf den Teil der Antwort anwenden, der **nach** dem
  Echo des gesendeten Befehls steht; fehlt das Echo, die gesamte Antwort
  auswerten und das protokollieren
- Unit-Test mit einem künstlich verschmolzenen Puffer
  (`MDCHECK`-Antwort + `*** What?` + Prompt + `L`-Antwort): der Fehler
  darf **nicht** `L` zugeordnet werden

**Commit:** `MailDrop session: attribute responses to the command that caused them`

---

## P35.4 — Wakeup-Erkennung ehrlich machen

`SerialManager._init_tnc_thread()`:

- „TNC at cmd: prompt" nur melden, wenn `cmd:` tatsächlich in der Antwort
  steht
- sonst: „wakeup answered without prompt (N bytes) — continuing" auf
  `warning`-Ebene, Rohbytes ins Log
- die bestehende Logik, die danach ohnehin weiterläuft, **nicht** ändern —
  es geht nur um die Wahrheit der Meldung. Der Rückfall aus P29 bleibt ein
  eigener Punkt

**Commit:** `SerialManager: wakeup log states what was actually received`

---

## P35.5 — Dokumentation

- `CLAUDE.md`: Mailbox-Befehle werden mit CR abgeschlossen; `L` auf Gerät B
  vorerst ungeklärt, Untersuchung läuft über den Mitschnitt
- `Testplan.md`: T119 — Teilergebnis 23.09.2026: `open` PASS, `list` FAIL
  (`*** What?`), Rückweg vollständig bestätigt
- `docs/PK232_firmware_matrix.md`: offener Punkt — verhält sich `L` auf
  MBX anders als auf PACTOR?

**Commit:** `Docs: session trace, CR terminator, open question on L`

---

## Definition of Done

- `.venv\Scripts\python.exe -m pytest` grün
- `maildrop_session` schreibt jeden gesendeten und empfangenen Rohblock
- Kein Verhalten der Anwendung geändert, solange kein Mitschnitt-Rückruf
  gesetzt ist
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"
- Danach vom Operator: `maildrop_session` erneut, Logdatei an den Chat