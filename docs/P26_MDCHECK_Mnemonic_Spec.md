# Claude Code Prompt — P26: Das Host-Kürzel für MDCHECK finden

> Ablage: `docs/P26_MDCHECK_Mnemonic_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher `CLAUDE.md`, `Backlog.md`, `Testplan.md` lesen.
> Fixture: `hw_logs/20260922_211322_maildrop_host.log`.

---

## Befunde aus dem `maildrop_host`-Lauf (22.09.2026, 21:13)

1. **Sonde A blieb ohne Mailbox-Antwort.** `SOH $60 'L' CR ETB` → nur
   `$5F` mit `XX\x00` (die übliche Datenquittung, bekannt aus T101).
   **Kein `$70`-Frame.**
2. **Die Auswertung des Werkzeugs ist falsch:** gemeldet wurde
   „login not needed — probe A alone got a response". Ein `$5F` ist eine
   Quittung, keine Antwort der Mailbox. Sonde B wurde dadurch
   übersprungen.
3. **Handbuchwiderspruch, durch Messung entschieden:** Kapitel 12 nennt
   sowohl `MDCheck … Host: MI` als auch `MFIlter … Default: $80 … Host: MI`.
   Die Messung (`MI` → `$80`, verbose `MFILTER` → `$80`) belegt
   **`MI` = MFILTER**. Der MDCheck-Eintrag im Handbuch ist fehlerhaft;
   **das Host-Kürzel für MDCHECK ist unbekannt.**
4. Ohne Login werden `$60`-Frames quittiert und verworfen — das erklärt
   Sonde A vollständig.

### Nebenbefund im Anwendungscode
`pk232_hostmode_sub.py` bzw. `serial_manager.py` kommentieren `HOST 3` als
„poll level 3 (undocumented/expert command)". Das ist falsch: `HOST` ist
ein Bitfeld (Handbuch Kap. 12) — Bit 0 = Host Mode ein, **Bit 1 = lokales
MailDrop-Login, Sendedaten `$60`, Lesedaten `$70`**, Bit 2 = erweiterter
Host Mode. Die Anwendung fährt seit jeher mit gesetztem MailDrop-Bit.

---

## P26.1 — Dokumentation und Korrekturen ohne Hardware

### `CLAUDE.md`
- HOST-Bitfeld richtigstellen, den falschen „poll level"-Kommentar im Code
  ersetzen (nur den Kommentar — **die Bytefolge `HOST 3` bleibt
  unverändert**, sie ist bewährt)
- Mnemonic-Tabelle: `MI` = MFILTER **hardwareverifiziert**; Vermerk, dass
  das Handbuch dasselbe Kürzel fälschlich auch bei MDCheck führt
- neuer Fallstrick: **das Handbuch ist an dieser Stelle widersprüchlich** —
  bei Kürzeln gilt Messung vor Handbuch

### `tools/hw_check.py`
- Auswertung von `maildrop_host`: „Antwort" heißt **Datenframe mit
  Mailbox-Inhalt** (`$70`, hilfsweise irgendein Frame ≠ `$4F`/`$5F`),
  nicht „irgendein Frame". Sonde B muss laufen, wenn A nur Quittungen
  bringt. Unit-Test mit dem realen `$5F`-`XX\x00`-Frame: Verdikt muss
  „no mailbox response" lauten und Sonde B auslösen

**Commits:**
```
Docs: HOST is a bit field, MI is MFILTER (hardware), manual contradicts itself
Tools: maildrop_host verdict requires a mailbox data frame
```

---

## P26.2 — Neues Subcommand `mdcheck_scan`

**Ziel:** das Host-Kürzel für MDCHECK finden, ohne zu raten — durch einen
eng begrenzten, protokollierten Suchlauf.

### Vorgehen

1. `normalize()`, Testnachricht über den verbose-Weg anlegen (wie in
   `maildrop_host`), Mailbox mit `B` verlassen
2. Host Mode betreten, Puffer abräumen
3. Für jedes Kürzel `M?` mit `?` von `A` bis `Z`:
   - Kürzel **ohne Argument** senden (`SOH $4F 'M' '?' ETB`)
   - 1,5 s lang alle Frames sammeln und protokollieren
   - **Treffer** = eine Antwort, die den Mailbox-Prompt enthält
     (`(AEA PK-232M)` und `free`), gleich in welchem Frame-Typ
   - bei einem Treffer: Suchlauf **sofort beenden**, Kürzel melden
4. Nach einem Treffer: `SOH $60 'L' CR ETB` senden, Antwort
   protokollieren (erwartet `$70` mit der Liste), dann
   `SOH $60 'B' CR ETB`
5. Host Mode verlassen, verbose `cmd:` prüfen, `normalize()`

### Sperrliste — diese Kürzel werden **nicht** gesendet

| Kürzel | Grund |
|---|---|
| `MO` | MORSE — Betriebsartwechsel |
| `MI` | MFILTER — bereits belegt, kein Kandidat |
| `MM` | MEMORY — liest Speicher und erhöht den ADDRESS-Zähler |

Alle übrigen `M?`-Kürzel sind laut Handbuch Parameterabfragen oder
harmlose Direktbefehle (`MH` MHEARD gibt eine Liste aus, `MV` MAILDROP,
`MD` MDIGI, `MC` MCON, `ME` MBELL, `MF` MFROM, `MT` MTO, `MN` MONITOR,
`MX` MAXFRAME, `MW` MARSDISP …). Die Sperrliste im Code mit genau diesen
Begründungen kommentieren.

### Sicherheit

- vor dem Suchlauf **eine** Bestätigung `y/N` mit dem Hinweis, dass 23
  Abfrage-Frames gesendet werden und welche gesperrt sind
- `XMITOK` vorher abfragen und den Zustand melden; **keine** Aussendung
  wird ausgelöst, alle Kandidaten sind Abfragen
- `finally`: Host Mode verlassen, Zustand prüfen
- schlägt der Suchlauf fehl (kein Treffer), ist das ein vollwertiges
  Ergebnis: dann ist MDCHECK im Host Mode womöglich gar nicht als
  Kürzel erreichbar, und der Dialog muss die Mailbox über den
  verbose-Weg bedienen. In `Backlog.md` als Entscheidungspunkt notieren

**Commit:** `Tools: hw_check mdcheck_scan -- find the MailDrop login mnemonic`

---

## P26.3 — Tests

- Sperrliste: `MO`, `MI`, `MM` werden nie erzeugt
- Treffererkennung: eine Antwort mit `(AEA PK-232M)  18536 free  (B,E,K,L,R,S) >`
  gilt als Treffer, ein `$4F`-Echo (`MV` + Wert) und ein `$5F`-`XX\x00`
  nicht
- der Suchlauf endet beim ersten Treffer

**Commit:** `Tests: mdcheck_scan denylist and hit detection`

---

## P26.4 — Dokumentation

- `docs/HW_Solo_Tests.md`: `mdcheck_scan` ergänzen
- `Testplan.md`: T117 um den Befund aus dem ersten `maildrop_host`-Lauf
  erweitern (kein `$70`, nur Quittung), neuer Fall für `mdcheck_scan`

**Commit:** `Docs: mdcheck_scan, maildrop_host first-run result`

---

## Definition of Done

- `.venv\Scripts\python.exe -m pytest` grün
- `--dry-run mdcheck_scan` listet alle 23 Kandidaten in Hex und nennt die
  drei gesperrten
- Kein Code unter `src/pk232py/` verändert außer den Kommentaren aus P26.1
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"
- Danach vom Operator: `mdcheck_scan`, Logdatei an den Chat