# Claude Code Prompt — P54: Porteinstellungen und Flusskontrolle

> Ablage: `docs/P54_Port_Settings_Flow_Control_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Belege: Konsolenmitschnitt 26.09.2026 15:25–15:27 und ein
> Gegenversuch des Operators mit PuTTY.

---

## Befundlage

Nach `Ctrl+D` (Port schließen) und `Ctrl+T` (neu verbinden):

```
step 1 TX: 2a    -> 2a 5c 0d 0a      Echo, kein cmd:
step 2 TX: 0d    -> 0d 0a            Echo, kein cmd:
step 2b TX: 03 0d-> 0d 0a            Echo, kein cmd:
step 3/3b        -> nur Echo
-> Abbruch
```

**Gegenversuch (Operator, 26.09.2026):** Anwendung beenden, PuTTY an
COM6, 9600 8N1, Flusskontrolle **keine**, einmal `Enter` — der Prompt
`cmd:` erscheint sofort. Kein `Ctrl-C` nötig.

**Der TNC ist also in Ordnung.** Derselbe Reiz (`CR`) liefert in PuTTY
einen Prompt und in der Anwendung nicht. Der Unterschied liegt in der
Art, wie die Anwendung den Port öffnet und bedient.

Das Verhaltensmuster ist bezeichnend: Der TNC **echot** weiterhin alles,
sendet aber nichts, was er **selbst erzeugt** (Prompt, Meldungen). Genau
so wirkt eine angehaltene Software-Flusskontrolle. Dass der PK-232 sie
benutzt, zeigt das Banner: `... 0d 0a 11 41 45 41 ...` — das `$11` ist
**XON**.

Ebenfalls belegt (Handbuch Kap. 12): `CMDTIME`, `TRFLOW`, `XFLOW`,
`START`/`STOP` steuern die Flusskontrolle; der TRANSPARENT-Modus braucht
**drei** COMMAND-Zeichen innerhalb `CMDTIME` — für CONVERSE genügt eines.

---

## P54.1 — Porteinstellungen protokollieren

Beim Öffnen des Ports **alle** Parameter protokollieren, die das
Verhalten beeinflussen:

```
port COM6 opened: 9600 8N1, xonxoff=?, rtscts=?, dsrdtr=?,
                  dtr=?, rts=?, timeout=?, write_timeout=?
```

Dasselbe **nach** dem Öffnen erneut lesen (die Leitungszustände können
sich beim Öffnen ändern) und beim Schließen eine Zeile mit dem
Endzustand.

Ohne diese Zeilen ist die Ursache nicht zu belegen — bisher steht im Log
nur `Port COM6 opened at 9600 baud`.

**Commit:** `SerialManager: log the full port configuration on open and close`

---

## P54.2 — Bekannten Zustand herstellen

Die Anwendung öffnet den Port künftig mit derselben Konfiguration, mit
der PuTTY nachweislich funktioniert:

- `xonxoff = False`, `rtscts = False`, `dsrdtr = False`
- `dtr = True`, `rts = True` **ausdrücklich gesetzt**, nicht dem
  Betriebssystem überlassen
- nach dem Öffnen `reset_input_buffer()` **und** `reset_output_buffer()`

Weicht die heutige Konfiguration davon ab, im Commit-Text nennen, was
vorher gesetzt war.

**Wichtig:** Das ist die Konfiguration **unserer Seite**. Ob der TNC
seinerseits angehalten ist, steht damit noch nicht fest — siehe P54.3.

**Commit:** `SerialManager: open the port with an explicit, known configuration`

---

## P54.3 — XON senden, bevor aufgegeben wird

Ist der TNC durch ein XOFF angehalten — etwa weil während des Host Mode
ein Frame-Byte `$13` durchgelaufen ist —, sendet er nichts Selbsterzeugtes
mehr, echot aber weiter. Genau das beobachtete Bild.

Neue Zwischenstufe, **vor** dem HPOLL-Frame:

- `$11` (XON) senden, kurz warten, dann `CR`
- kommt `cmd:`, war der TNC angehalten → Logzeile
  `step 2c - XON released a stopped TNC`

Das kostet zwei Bytes und ist folgenlos, wenn der TNC gar nicht
angehalten war.

**Commit:** `SerialManager: send XON before giving up on the prompt`

---

## P54.4 — Zweites CR

PuTTY hat genau **ein** Enter gebraucht — unsere Kette sendet bereits
eines und bekommt nur `0d 0a`. Trotzdem: nach dem XON-Versuch ein
zweites `CR` senden, bevor Stufe 3 beginnt. Billig, und es deckt den Fall
ab, dass das erste CR eine unvollständige Eingabezeile abschließt.

**Commit:** wird Teil von P54.3, wenn keine eigene Logik nötig ist.

---

## P54.5 — Tests

- Portkonfiguration: `open()` setzt die Werte aus P54.2; ein Test liest
  sie vom Attrappen-Port zurück
- Stufe 2c: Attrappe antwortet erst nach `$11` mit `cmd:` → Erfolg über
  Stufe 2c, **kein** HPOLL-Frame gesendet
- Attrappe antwortet weiterhin nicht → Kette läuft wie bisher weiter bis
  Stufe 4
- die Logzeilen aus P54.1 enthalten alle genannten Felder

**Commit:** `Tests: port configuration and XON stage`

---

## P54.6 — Dokumentation

`CLAUDE.md`:

- **Der PK-232 benutzt Software-Flusskontrolle** (XON `$11` / XOFF
  `$13`); im Banner ist das XON sichtbar. Ein angehaltener TNC echot
  weiter, sendet aber nichts Selbsterzeugtes — das sieht aus wie ein
  fehlender Prompt
- **Gegenprobe mit einem Terminalprogramm gehört zur Fehlersuche:**
  Liefert PuTTY mit einem Enter den Prompt und die Anwendung nicht, liegt
  es an der Portkonfiguration, nicht am TNC (belegt 26.09.2026)
- Handbuchwissen ergänzen: TRANSPARENT verlangt **drei** COMMAND-Zeichen
  innerhalb `CMDTIME`, CONVERSE nur eines

`SERIAL_CONNECTION_STATE_MACHINE.md`: Stufe 2c aufnehmen, dazu die
Portkonfiguration als Vorbedingung des Verbindungsaufbaus.

`Testplan.md`: Fall — verbinden, Host Mode, zurück, trennen, neu
verbinden; erwartet wird ein Aufbau ohne Fehlermeldung.

**Commit:** `Docs: flow control and port configuration`

---

## Definition of Done

- `.venv\Scripts\python.exe -m pytest` grün
- Das Log nennt beim Öffnen alle Portparameter
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"
- Danach vom Operator: derselbe Ablauf erneut, mit Konsolenmitschnitt —
  die neuen Portzeilen sind der eigentliche Messwert