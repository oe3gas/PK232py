# Claude Code Prompt — P37: T119 festhalten, Herkunft und Fähigkeitserkennung

> Ablage: `docs/P37_T119_Provenance_Capability_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher `CLAUDE.md`, `Backlog.md`, `Testplan.md`,
> `docs/PK232_firmware_matrix.md` lesen.
> Fixture: `hw_logs/20260924_181446_maildrop_session.log`.
>
> **Dieses Paket ersetzt die nie umgesetzten Entwürfe P32 (Geräteherkunft)
> und P33 (MailDrop-Fähigkeit).** Deren Inhalt steht hier in aktualisierter
> Form; die Dateien `docs/P32_*.md` und `docs/P33_*.md` werden nicht mehr
> gebraucht.

---

## Teil A — Ergebnis T119 (24.09.2026, Gerät B, MBX 01.08.1991)

**10 von 10 Schritten PASS.** Öffnen, leere Liste, drei Nachrichten
(personal, fremder Absender, Bulletin), Liste mit drei Einträgen, Lesen,
Löschen, Liste nach dem Löschen, Verlassen — dazu Host Mode per `HPOLL`
bestätigt.

### A.1 Die `L`-Frage ist geklärt
Das `*** What?` vom 23.09. war die Antwort auf unser überzähliges LF nach
`MDCHECK`. Mit `MDCHECK\r` kommt der Prompt allein, und `L` antwortet
`*** Message not found.` **Ursache war die Software, nicht die Firmware.**

### A.2 Die `/E`-Zeile ist systematisch
Beim Lesen: `...harness<CR><LF>/E<CR><LF>`. Die frühere Einstufung als
Einzelfall (P31) war falsch. `parse_read()` schneidet sie korrekt ab.
**In `CLAUDE.md` von „einmalig beobachtet" auf „tritt regelmäßig auf,
wird entfernt" ändern.**

### A.3 Die Blockhypothese zum Speicher ist widerlegt
Verbrauch in diesem Lauf: Größe 61 → 112 Bytes, 43 → 84, 35 → 84. Die 112
hängt hier an der Größe, während auf Gerät A dieselbe Zahl bei einer
kleinen Nachricht **mit** BBS-Angabe auftrat. Es gibt keine erkennbare
Regel.
**In `CLAUDE.md` die Vermutung „BBS kostet einen Block mehr" streichen**
und dabei festhalten: der freie Speicher wird ausschließlich aus dem
Prompt gelesen, nie berechnet.

### A.4 Bestätigt geblieben
`Größe = Betreff + Text + 9` gilt auch auf Gerät B. Fremder Absender über
`<` funktioniert auf beiden Firmwareständen.

### A.5 Dokumentation
- `Testplan.md`: T119 **PASS**, 24.09.2026, Gerät B, alle zehn Schritte
  einzeln; Verweis auf die Logdatei
- `CLAUDE.md`: A.1 bis A.4 einarbeiten
- `docs/PK232_firmware_matrix.md`: gemessener Eintrag — MailDrop-Protokoll
  (L, S, SB, R, K, B, `<`-Absender) auf MBX **und** PACTOR identisch

**Commit:** `Docs: T119 passed on device B, LF cause, /E trailer, memory hypothesis withdrawn`

---

## Teil B — Prüfstand: Identität und Uhrzeit setzen

Im Lauf trugen die Nachrichten `PK232` als Absender, und die Datumsspalten
blieben Punktreihen: `MYCALL` und `DAYTIME` werden im Sitzungspfad nicht
gesetzt.

In `maildrop_session`, **vor** dem Host-Mode-Eintritt, in der
verbose-Phase:

- `MYCALL` aus der Konfiguration setzen (wie `normalize()` es tut,
  vorhandene Funktion verwenden)
- `DAYTIME` setzen, wie es der `maildrop`-Rekorder bereits macht
  (Format aus `ParamsUploader`, nicht neu bauen)
- beides protokollieren; schlägt es fehl, Lauf abbrechen (P34-Regel)

Danach zeigen die Listen echte Absender und Zeitstempel — und das Format
der Datumsspalte ist erstmals auch auf Gerät B belegt.

**Commit:** `Tools: maildrop_session sets MYCALL and DAYTIME before the session`

---

## Teil C — Geräteherkunft in jedem Lauf (ersetzt P32)

Der Banner liefert alles Nötige ohne Zusatzabfragen:

```
PK-232M is using default values.
AEA PK-232M Data Controller
Copyright (C) 1986-1991 by Advanced Electronic Applications, Inc.
Release 01.AUG.91
```

### C.1 Erfassen
- `SerialManager` wertet den Banner bereits aus (`has_pactor`). Zusätzlich
  **Release-Datum** und die Meldung `is using default values` erfassen und
  als Eigenschaften bereitstellen
- steht der TNC schon am `cmd:`-Prompt, gibt es keinen Banner: dann
  bleiben die Felder leer — **nichts erfinden**

### C.2 Protokollieren
Kopfzeile jeder `hw_check`-Logdatei und erste Zeile jeder Zusammenfassung:

```
device: release=01.AUG.91  pactor=no  defaults=yes  (source: banner)
```

Fehlt der Banner: `device: unknown (no banner - TNC was already awake)`.

### C.3 `docs/DEVICES.md` (neu)
Inventar der drei Geräte: Kennung, Release-Datum, PACTOR, MailDrop,
Prompt-Klammern, letzte Messung, Besonderheiten.

| Gerät | Release | PACTOR | MailDrop | Prompt |
|---|---|---|---|---|
| A | 11.09.1995 | ja | ja | rund |
| B | 01.AUG.91 | nein | ja | eckig |
| C | 30.12.1988 | nein | **nein** (PuTTY, 23.09.2026) | unbekannt |

Querverweis auf `docs/PK232_firmware_matrix.md` setzen und dort den
Rückverweis ergänzen (der fehlt bisher, weil `DEVICES.md` nicht existierte).

### C.4 Bestehende Befunde zuordnen
In `CLAUDE.md` kenntlich machen: alle Mnemonic- und MailDrop-Befunde bis
22.09. stammen von **Gerät A**, die Läufe ab 23.09. von **Gerät B**.
Regel ergänzen: **ein Messbefund gilt für das Gerät, an dem er entstand** —
bei abweichendem Verhalten zuerst die Firmware prüfen, nicht den Code.

**Commits:**
```
SerialManager: capture firmware release and default-values flag from the banner
Tools: hw_check logs device provenance
Docs: device inventory and per-device attribution of findings
```

---

## Teil D — MailDrop-Fähigkeit erkennen (ersetzt P33)

Gerät C (30.12.1988) hat **keine MailDrop** — am 23.09. mit PuTTY geprüft.
Heute sendet der Parameter-Upload dort sieben Befehle
(`MAILDROP`, `MDMON`, `MMSG`, `TMAIL`, `3RDPARTY`, `KILONFWD`, `MTEXT`),
die alle mit `?What?` beantwortet würden.

### D.1 Erkennung
Wie `has_pactor` aufgebaut, aber über eine **Abfrage**, weil der Banner
nur nach dem Einschalten kommt:

- in der verbose-Phase, **vor** dem Upload: `MAILDROP` ohne Argument
- `MAildrop  ON|OFF` → `has_maildrop = True`
- `?What?` → `False`
- keine oder unklare Antwort → `None`, behandelt wie `True` (ein
  Erkennungsfehler darf keine vorhandene Funktion sperren)

**`MDCHECK` kommt in keinem Erkennungspfad vor** — der Befehl loggt in die
Mailbox ein und legt den Packet-Betrieb still.

### D.2 Upload
Den MailDrop-Block überspringen, wenn `has_maildrop is False`, mit **einer**
Logzeile statt sieben Fehlermeldungen. Liste der Befehle aus dem Code
übernehmen, nicht aus dieser Spezifikation.

### D.3 UI
- MailDrop-Button: Tooltip abhängig vom Grund („not implemented yet" bzw.
  „this firmware has no MailDrop")
- Parameterdialog: MailDrop-Felder sperren, **nicht ausblenden**, mit
  demselben Hinweis

### D.4 Dokumentation
`docs/DEVICES.md` und `CLAUDE.md` (Abschnitt Firmware-Unterschiede):
1988er Firmware ohne MailDrop; Erkennung über die `MAILDROP`-Abfrage.
`Testplan.md`: Fall — Anwendung mit Gerät C starten, erwartet wird ein
Upload ohne `?What?` und gesperrte MailDrop-Bedienelemente.

**Commits:**
```
SerialManager: detect MailDrop capability via MAILDROP query
Params uploader: skip the MailDrop block when unsupported
UI: disable MailDrop controls on firmware without MailDrop
Docs: firmware without MailDrop
```

---

## Definition of Done

- `.venv\Scripts\python.exe -m pytest` grün
- Ein Test belegt, dass der Upload ohne MailDrop-Unterstützung die sieben
  Befehle auslässt
- Jede neue Logdatei beginnt mit einer `device:`-Zeile
- `MDCHECK` kommt in keinem Erkennungspfad vor
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"
- Danach vom Operator: `maildrop_session` erneut (zeigt echte Absender und
  Zeitstempel), und bei Gelegenheit ein Start mit Gerät C