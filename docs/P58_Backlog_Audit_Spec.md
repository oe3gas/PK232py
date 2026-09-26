# Claude Code Prompt — P58: Backlog auf Stand bringen

> Ablage: `docs/P58_Backlog_Audit_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Zweck: Übergabe an eine neue Arbeitssitzung. `Backlog.md` und
> `Testplan.md` müssen den Stand vom 26.09.2026 abbilden.

---

## A — Bekannte Abweichungen, die zu korrigieren sind

### A.1 T122 ist am Gerät bestanden
Der Eintrag zum MailDrop-Dialog sagt derzeit sinngemäß „software/mock
verified only — never run against a real TNC". **Das stimmt nicht mehr.**

Am **25.09.2026** hat der Operator den Dialog an Gerät B (Release
01.AUG.91) vollständig durchlaufen: Eingangstor mit Prüfliste, Sitzung
öffnen, Nachricht schreiben, lesen, löschen, Schließen über das
Fensterkreuz mit Rückfrage und sichtbarem Fortschritt, danach
Packet-Betrieb wieder verfügbar. Ergebnis: **alles in Ordnung.**

- `Testplan.md`: T122 auf **PASS** setzen, mit Datum und Gerät
- `Backlog.md`: den Vorbehalt streichen

### A.2 P51 ist durch P52–P55 abgelöst
`docs/P51_Pruefdurchgang_Befunde_Spec.md` wurde nie umgesetzt: Teil A ist
durch P52 (Echo/Lesefenster), P53 (Ctrl-C, Lesepfad) und P54 (DTR/RTS)
erledigt, die Teile B–I durch P55. Im Backlog entsprechend vermerken,
damit die Datei niemanden in die Irre führt.

### A.3 „Fensterausnutzung nicht reproduzierbar" war falsch
P55 Teil E kam zu dem Schluss, es gebe keinen Codefehler. P56 hat ihn
gefunden und gemessen: Splitter und Statuszeile hatten beide
Stretch 0, Qt gab der Statuszeile daraufhin rund 683 px. Der Eintrag
gehört korrigiert — mit dem Vermerk, **warum** die erste Untersuchung
danebenlag (nicht maximiertes Fenster, falsche Maske gemessen).

### A.4 Die Schriftkorrektur aus P55 war selbst ein Fehler
P55 Teil C führte die Konstante `_RX_FONT` ein und erzeugte damit eine
zweite Schriftquelle; P56 hat sie entfernt. Als Lehre eintragen, nicht
nur als erledigt.

### A.5 Hardwarebestätigungen vom 25./26.09.2026
Im Testplan nachtragen, jeweils mit Gerät B:

- Verbindungsaufbau in allen geprüften Zuständen (nach Host Mode, nach
  Trennen, nach Abwürgen), `parameter upload verified (3/3)`
- Chip-Zustände: Pulsation, rotes Blitzen, Rückkehr auf frei
- Link-Meldungen bleiben in ihrem Kanal
- Kanalpuffer: Verlauf beim Zurückwechseln vollständig
- MHEARD: Partner mit Rufzeichen, Kanalnummer und Zeit, ohne manuelles
  Refresh
- Firmware-Anzeige aus dem Banner
- **kein Kanalversatz** (`1│` passend zu Chip 1)

---

## B — Vollständigkeitsprüfung

`Backlog.md` gegen diese Quellen durchgehen und fehlende Punkte
ergänzen, erledigte als erledigt kennzeichnen:

1. alle `docs/P*.md` ab P40 — jedes Paket hinterlässt entweder einen
   erledigten oder einen offenen Eintrag
2. `Testplan.md` — jeder Fall mit Status OPEN muss im Backlog eine
   Entsprechung haben, wenn er Arbeit bedeutet
3. `docs/DEVICES.md` — Gerät C ist unvermessen (T120)

Bekannte offene Punkte, die enthalten sein müssen (prüfen, nicht blind
ergänzen):

- **MailDrop-Archiv:** Ablage steht (P38), aber `archive_sync`,
  `archive_restore`, `archive_restore_scope` wirken nur manuell über die
  Knöpfe der Sitzungsmaske; die automatischen Betriebsarten sind nicht
  verdrahtet
- **`Header…`/EDIT** im MailDrop-Dialog: gesperrt, weil ungemessen
- **`MDMON`:** zweite Quelle für „Post wartet" und mögliche
  Archivierung ohne Sitzung — beides ungemessen
- **21 zurückgestellte Upload-Felder** (P13) über PACTOR, AMTOR, Baudot
  und Misc
- **`PTHUFF`** wird als ON/OFF gesendet, der TNC erwartet numerisch
- **`MYALTCAL`** wird vom TNC auf vier Zeichen gekürzt
- **Mnemonic-Neuscan** mit Sperrliste für Aktionsbefehle (Priorität 2)
- **Gerät C (T120):** Start mit der 1988er Firmware, Upload ohne
  `?What?`, gesperrte MailDrop-Bedienelemente
- **P57** (Chip-Eingabe schließt beim Wechsel), falls noch nicht
  umgesetzt

---

## C — Form

- der Backlog behält seine bisherige Gliederung; **keine Umstrukturierung**
- jeder Eintrag nennt Paketnummer und Datum, wie bisher
- erledigte Einträge werden **nicht gelöscht**, sondern gekennzeichnet —
  die Geschichte ist mehrfach nützlich gewesen (T86, Klammerformen,
  Fensterausnutzung)

**Commits:**
```
Testplan: hardware results from 2026-09-25/26
Backlog: correct superseded entries and add the open items
```

---

## Definition of Done

- `Backlog.md` enthält keinen Eintrag mehr, der einem Hardwarebefund vom
  25./26.09.2026 widerspricht
- jeder Testplan-Fall mit Status OPEN hat eine Entsprechung im Backlog
  oder eine Begründung, warum nicht
- `.venv\Scripts\python.exe -m pytest` grün (Doku-Änderungen dürfen
  nichts brechen)
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"