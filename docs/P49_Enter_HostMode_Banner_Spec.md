# Claude Code Prompt — P49: Umschalten in den Host Mode, saubere Bannerausgabe

> Ablage: `docs/P49_Enter_HostMode_Banner_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher `CLAUDE.md`, `SERIAL_CONNECTION_STATE_MACHINE.md`,
> `docs/P46_Recovery_Emergency_Connect_Spec.md` lesen.

---

## Teil A — Menüpunkt „Enter Host Mode" fehlt

### Befund (25.09.2026)
Das TNC-Menü hat den **Ausgang** (`Leave Host Mode + Return to Terminal`),
aber keinen **Eingang** aus einer bestehenden verbose-Verbindung.
`Connect + Enter Host Mode…` ist ausgegraut, sobald verbunden ist. Wer im
Terminal-Modus verbunden hat, kommt nicht mehr in den Host Mode.

### A.1 Menü

```
Connect + Enter Terminal Mode…             Ctrl+T   (nur wenn getrennt)
Connect + Enter Host Mode…                 Ctrl+M   (nur wenn getrennt)
---
Enter Host Mode                            Ctrl+H   (verbunden + verbose)   [NEU]
Leave Host Mode + Return to Terminal       Ctrl+L   (verbunden + Host Mode)
---
Disconnect + Close Serial Port             Ctrl+D
Emergency Reconnect (Host Mode Recovery)   Ctrl+R
---
MailDrop…
```

Freigabe streng nach Zustand; im deaktivierten Zustand erklärt der Tooltip
den Grund („already in Host Mode", „not connected"). `Ctrl+H` vorher gegen
die belegten Kurzbefehle prüfen und bei Kollision einen freien wählen —
Befund in den Commit-Text.

### A.2 Der Parameter-Upload ist die eigentliche Frage

**Im Host Mode lässt sich nicht mehr hochladen** (P40/P43). Der Wechsel
ist also der letzte Zeitpunkt dafür.

Der neue Menüpunkt verhält sich so:

| Lage | Verhalten |
|---|---|
| Upload lief in dieser Sitzung bereits | direkt in den Host Mode, Logzeile „parameters already uploaded" |
| Upload steht aus, **Fast Init aus** | Upload fahren, Stichprobe (P40.3), dann Host Mode |
| Upload steht aus, **Fast Init an** | **nachfragen**: „Fast Init skipped the parameter upload. The TNC is running on its stored values and cannot be configured once Host Mode is active. Upload parameters now?" mit `Upload and switch` / `Switch without upload` / `Cancel` |

Bei einem TNC **ohne Pufferbatterie** sind die „stored values" die
Werkseinstellungen — der Hinweistext soll das nicht behaupten, aber die
Folge benennen: ohne Upload läuft der TNC mit dem, was er beim Einschalten
hatte.

Ob ein Upload in dieser Sitzung stattgefunden hat, muss die Anwendung
bereits wissen (P40.3 protokolliert das Ergebnis). Falls nicht, ein
Kennzeichen ergänzen — **eine** Quelle, nicht mehrere.

**Commits:**
```
MainWindow: Enter Host Mode from an existing verbose connection
Connection: last chance to upload parameters before Host Mode
```

---

## Teil B — Bannerausgabe kommt zerhackt an

### Befund (Screenshot)

```
PK-232M is u[SYS] TNC ready in verbose mode
[SYS] Fast Init — parameter upload skipped
[SYS] Verbose terminal ready (fast init)
sing default values.
```

Das Wort „using" ist zerrissen; dazwischen stehen drei `[SYS]`-Zeilen.
Zusätzlich erscheinen am Zeilenanfang Kästchen — ungefilterte
Steuerzeichen (`SOH` und Ähnliches) aus der Init-Phase.

### B.1 Banner als ein Block

Der in P44 Teil B gespiegelte Init-Text wird **vollständig gesammelt** und
**in einem Stück** eingefügt, bevor die `[SYS]`-Meldungen der Anwendung
folgen. Kein zeilenweises Einfügen während anderer Ausgaben.

Reihenfolge im RX-Fenster:

```
<Banner des TNC, vollständig>
cmd:
[SYS] TNC ready in verbose mode
[SYS] …
```

### B.2 Steuerzeichen filtern

Vor der Anzeige alles außer `CR`, `LF` und `TAB` aus dem Bereich `$00–$1F`
entfernen; `$7F` ebenfalls. Die Rohbytes bleiben im Log (Hex, `DEBUG`) —
sichtbar sein sollen sie dort, nicht im Terminal.

Prüfen, ob es bereits eine Filterfunktion für die Terminalausgabe gibt;
falls ja, diese verwenden statt einer zweiten.

**Commit:** `Verbose terminal: banner as one block, control characters filtered`

---

## Teil C — Tests

- Menü: bei „getrennt" sind die beiden Connect-Punkte frei, die übrigen
  gesperrt; bei „verbunden + verbose" ist `Enter Host Mode` frei und
  `Leave Host Mode` gesperrt; bei „verbunden + Host Mode" umgekehrt
- `Enter Host Mode` mit bereits erfolgtem Upload → kein zweiter Upload
- `Enter Host Mode` mit ausstehendem Upload, Fast Init aus → Upload läuft
  vor dem Wechsel
- Fast Init an → Rückfrage erscheint; `Switch without upload` wechselt
  ohne Upload; `Cancel` wechselt nicht
- Banner mit eingestreuten Steuerzeichen → Anzeige ohne Kästchen, Text
  zusammenhängend, `[SYS]`-Zeilen danach

**Commit:** `Tests: Enter Host Mode gating and banner rendering`

---

## Teil D — Dokumentation

- `CLAUDE.md`: **Der Wechsel in den Host Mode ist der letzte Zeitpunkt für
  den Parameter-Upload.** Danach ist er unmöglich (kein `cmd:`-Prompt).
  Fast Init überspringt den Upload — der TNC läuft dann mit seinen
  gespeicherten Werten, bei fehlender Pufferbatterie also mit
  Werkseinstellungen
- `SERIAL_CONNECTION_STATE_MACHINE.md`: den Übergang verbose → Host Mode
  als eigenen, vom Verbindungsaufbau getrennten Weg beschreiben
- `Testplan.md`: Fälle für die Menüführung und für den Upload beim Wechsel

**Commit:** `Docs: entering Host Mode from verbose`

---

## Definition of Done

- `.venv\Scripts\python.exe -m pytest` grün
- Aus einer verbose-Verbindung ist der Host Mode über das Menü erreichbar
- Das Banner steht zusammenhängend und ohne Kästchen im Terminal
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"
- Danach vom Operator: mit `Ctrl+T` verbinden, dann `Ctrl+H` — einmal mit
  und einmal ohne Fast Init