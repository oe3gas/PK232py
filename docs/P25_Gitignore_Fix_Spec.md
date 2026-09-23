# Claude Code Prompt — P25: `maildrop/` ins Git holen, Fallstricke festhalten

> Ablage: `docs/P25_Gitignore_Fix_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher `CLAUDE.md` und `Backlog.md` lesen.

---

## Warum

`src/pk232py/maildrop/` (`maildrop.py`, `message_store.py`, `__init__.py`)
ist nie im Git gewesen: eine nackte Zeile `maildrop/` in `.gitignore`
greift auf **jedes** gleichnamige Verzeichnis in jeder Tiefe und hat damit
das Quellmodul ausgeschlossen. Gemeint war mit hoher Wahrscheinlichkeit ein
Datenverzeichnis.

Folge: Das Modul liegt nur im Arbeitsverzeichnis, wandert aber über
`Sources2Text.ps1` in den Export und damit ins Projektwissen. Es sieht
überall nach gepflegtem Projektcode aus, wäre nach einem frischen Klon aber
verschwunden — und seine erfundene Mnemonic-Tabelle
(`MD MDPROMPT`, `MY MYMAIL`, `3P 3RDPARTY`, …) hat deshalb bereits einmal
in die Irre geführt.

---

## P25.1 — `.gitignore` korrigieren

- die Zeile `maildrop/` entfernen
- ermitteln, was ursprünglich gemeint war (Git-Historie der `.gitignore`,
  umliegende Kommentare, tatsächlich vorhandene Datenverzeichnisse). Wenn
  nicht ermittelbar: verankerte, spezifische Muster setzen, z. B.

  ```
  /maildrop_data/
  *.db
  ```

- im Commit-Text festhalten: Muster ohne führenden Schrägstrich greifen in
  jeder Tiefe; Datenverzeichnisse werden ab jetzt verankert ausgeschlossen
- prüfen, ob **weitere** Zeilen in `.gitignore` dasselbe Problem haben
  (nackte Verzeichnisnamen wie `logs/`, `build/`, `data/`), und die Befunde
  im Commit-Text auflisten — **nicht** ungefragt alle ändern, nur die
  melden, die Quellcode treffen könnten

**Commit:** `Fix gitignore: anchored data dir patterns, maildrop source was excluded`

---

## P25.2 — `src/pk232py/maildrop/` einchecken

- die drei Dateien unverändert einchecken, bis auf die UNVERIFIED-Markierung
  am Docstring aus P24.1
- **vorher prüfen**, ob irgendein Modul unter `src/pk232py/` das Paket
  importiert (`from .maildrop import`, `pk232py.maildrop`, `MailDropController`,
  `MessageStore`). Ergebnis in den Commit-Text.
  - **wird es importiert**: Priorität-1-Eintrag in `Backlog.md`, weil
    `MailDropController.upload_config()` ungeprüfte Mnemonics an den TNC
    senden würde (Fehlerklasse aus T86/T47)
  - **wird es nicht importiert**: ebenfalls vermerken — das Paket ist dann
    toter Code, der nach T117 neu geschrieben wird
- `Backlog.md`: Eintrag, dass `src/pk232py/maildrop/` nach Abschluss von
  T117 (MailDrop im Host Mode) gegen eine gemessene Protokollschicht
  ersetzt wird; bis dahin nicht verdrahten

**Commit:** `Track maildrop module (unverified mnemonics, to be rewritten after T117)`

---

## P25.3 — Fallstricke dokumentieren

`CLAUDE.md`, Abschnitt mit den bekannten Fallstricken:

1. **`.gitignore`-Muster ohne führenden Schrägstrich greifen in jeder
   Tiefe.** `maildrop/` hat `src/pk232py/maildrop/` mit ausgeschlossen; das
   Modul war nie im Git, tauchte aber im `Sources2Text`-Export auf. Bei
   Datenverzeichnissen immer verankert ausschließen (`/name/`).
2. **Tests laufen über `.venv\Scripts\python.exe`.** Das blanke `python`
   dieser Maschine zeigt auf eine Python-3.14-Installation ohne PyQt6;
   `python -m pytest` scheitert dort an fehlenden DLLs.
3. **Der `Sources2Text`-Export ist kein Nachweis dafür, dass eine Datei im
   Repository ist.** Das Skript sammelt vom Dateisystem, nicht aus Git.

**Commit:** `Docs: gitignore depth pitfall, venv pytest, export is not git`

---

## Definition of Done

- `git status` zeigt `src/pk232py/maildrop/` als getrackt, nicht mehr als
  ignoriert
- `git ls-files src/pk232py/maildrop/` listet die drei Dateien
- `.venv\Scripts\python.exe -m pytest` grün
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"