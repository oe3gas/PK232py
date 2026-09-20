# Claude Code Prompt — P11: USERS (Anzahl gleichzeitiger Verbindungen)

> Ablage: `docs/P11_USERS_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher `CLAUDE.md`, `Backlog.md`, `Testplan.md` lesen.

---

## Warum

Die Kanalleiste kann zehn Kanäle darstellen, aber der PK-232 nimmt nur so
viele gleichzeitige Verbindungen an, wie `USERS` erlaubt — Standard ist 1.
Solange `USERS` nicht erhöht wird, bleiben die Chips 2–9 im echten Betrieb
tot, und das Mehrkanalmodell ist praktisch nicht nutzbar. `USERS` fehlt
bisher in Konfiguration, Dialog und Upload.

`USERS` gehört in den Parameterdialog, nicht in die Betriebsmaske: es wird
einmal eingestellt und nicht im QSO verändert.

---

## P11.1 — `src/pk232py/config.py`

`users: int = 1` in `HFPacketConfig` ergänzen, bei den übrigen numerischen
Parametern (neben `check`, `monitor`, `resptime`). Falls es eine eigene
`VHFPacketConfig` gibt, dort ebenso; erbt VHF von HF, entfällt der zweite
Eintrag.

Kommentar am Feld: `USERS — max. simultaneous AX.25 connections (1-10)`.

**Commit:** `Config: add USERS to packet parameters`

---

## P11.2 — `src/pk232py/ui/dialogs/params_hf.py`

Im Haupt-Tab eine `QSpinBox` für `USERS` ergänzen:

- Bereich 1–10, Schrittweite 1
- Beschriftung: `USERS` mit Tooltip:
  „Maximum number of simultaneous AX.25 connections the TNC will accept.
  Channels above this number stay unused. Default 1."
- Einordnung bei den übrigen Verbindungsparametern (`CHECK`, `RETRY`,
  `FRACK`), nicht bei den Timing-Werten
- in `set_values()` und `get_values()` aufnehmen, gleiche Namenskonvention
  wie die vorhandenen Felder (`self._sb_users`)

**Commit:** `HF packet params dialog: USERS spinbox`

---

## P11.3 — `src/pk232py/ui/dialogs/params_vhf.py`

Dasselbe im VHF-Dialog. Existiert der Dialog als eigene Datei, eigener
Commit; teilt er sich die Klasse mit HF, entfällt dieser Schritt und das
wird im Commit-Text von P11.2 vermerkt.

**Commit:** `VHF packet params dialog: USERS spinbox`

---

## P11.4 — `src/pk232py/ui/params_uploader.py`

`USERS` mit in die Parameterliste aufnehmen, bei den übrigen
`self._cmd(...)`-Aufrufen des HF-Packet-Blocks:

```python
self._cmd("USERS", str(hf.users)),
```

**Wichtig — keine Mnemonic raten.** Dieser Upload-Pfad benutzt die
verbose-Befehlsnamen, nicht die Host-Mode-Mnemonics; `USERS` ist damit der
korrekte Bezeichner und muss nicht gegen die Mnemonic-Tabelle geprüft
werden. Die Host-Mode-Mnemonic `UR` steht zwar in
`pk232_mnemonic_table.txt`, wird hier aber **nicht** verwendet und auch
nicht eingebaut — ein Ändern von `USERS` zur Laufzeit im Host Mode ist
nicht Teil dieses Pakets.

Zu beachten und als Kommentar festzuhalten: der PK-232 weist einige
Parameteränderungen ab, solange eine Verbindung besteht (Fehlercode `$09`
„not while connected", TRM 4.3). Ob `USERS` dazugehört, ist nicht belegt —
siehe T104.

**Commit:** `Params uploader: send USERS`

---

## P11.5 — `src/pk232py/ui/screens/packet_screen.py` (nur Hinweis, keine Sperre)

`ChannelBar` bekommt eine Methode:

```python
def set_user_limit(self, limit: int) -> None:
    """Number of simultaneous connections the TNC accepts (USERS)."""
```

Wirkung ausschließlich im Tooltip: Chips mit `ch > limit` bekommen eine
zusätzliche Zeile

```
USERS is set to N — incoming connects on this channel will not be accepted.
```

**Keine** Sperre, keine Ausgrauung, keine Farbänderung:

- `USERS` begrenzt laut Handbuch die *angenommenen* Verbindungen. Ob es auch
  ausgehende Connects auf höheren Kanälen verhindert, ist nicht belegt —
  eine Sperre könnte also funktionierende Bedienung verhindern.
- Ein Tooltip, der sich als falsch herausstellt, kostet nichts. Ein
  gesperrter Chip, der eigentlich ginge, kostet den Operator ein QSO.

Aufgerufen wird `set_user_limit()` dort, wo die Betriebsart aktiviert und
`set_mycall()` gesetzt wird, mit dem Wert aus der Konfiguration.

**Commit:** `Channel bar: show USERS limit in chip tooltips`

---

## P11.6 — Dokumentation

### `CLAUDE.md`

Im Abschnitt „Channel model" ergänzen: die Kanalleiste zeigt immer zehn
Kanäle, aber `USERS` (Standard 1) bestimmt, wie viele gleichzeitige
Verbindungen der TNC überhaupt annimmt. Ohne Erhöhung bleiben die Chips 2–9
im echten Betrieb ungenutzt — das ist keine Fehlfunktion der UI.

### `Testplan.md`

**T103 — USERS wird übertragen**
1. Parameterdialog HF Packet öffnen, `USERS` auf 4 setzen, OK
2. Parameter-Upload auslösen
3. Erwartung: im Monitor erscheint `USERS 4`, der TNC quittiert ohne Fehler
4. Wert bleibt nach Neustart der Anwendung erhalten (INI)

**T104 — USERS während bestehender Verbindung** (Hardware, Status OPEN)
1. Verbindung auf Kanal 1 aufbauen
2. `USERS` im Dialog ändern und hochladen
3. Erwartung offen: akzeptiert der TNC die Änderung, oder antwortet er mit
   `$09` „not while connected"? Ergebnis in `CLAUDE.md` nachtragen; falls
   abgelehnt, den Upload für `USERS` bei bestehender Verbindung
   überspringen statt einen Fehler zu erzeugen.

**T105 — zweite gleichzeitige Verbindung** (Hardware, Status OPEN)
1. `USERS` auf 2 oder höher setzen und hochladen
2. Verbindung auf Kanal 1 aufbauen
3. Zweite Station auf Kanal 2 connecten lassen
4. Erwartung: beide Chips grün mit dem jeweiligen Rufzeichen, Daten laufen
   getrennt in die richtige Kanalansicht, TX-Puffer bleiben getrennt (P9)

### `Backlog.md`

T104 und T105 unter den Hardwaretests eintragen, Priorität 1 — T105 ist der
eigentliche Nachweis, dass das Mehrkanalmodell trägt.

**Commit:** `Docs: USERS parameter, tests T103-T105`

---

## Definition of Done

- `python -m pytest` grün, Test für die Dialog-Rundreise
  (`set_values()` → `get_values()` liefert `users` zurück) eingeschlossen
- `USERS` wird beim Upload tatsächlich gesendet, im Monitor sichtbar
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"