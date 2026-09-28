# Claude Code Prompt — P66: Host-Mode-Eintritt aus Converse meldet falschen Erfolg

> Ablage: `docs/P66_HostMode_Entry_From_Converse_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Grundlage: `main` @ `d1d731f`, Hardware-Läufe T141/T142 vom 28.09.2026,
> **Gerät B, Release 01.AUG.91** (Quelle: Banner, beide Logs).
> Die Verbindungstabelle (bisher als P66 angekündigt) wird **P67** — sie
> setzt voraus, dass der Host-Mode-Eintritt stimmt.

---

## Befund

### B.1 T141: Der TNC war nie im Host Mode

Nach `CONNECT oe3gas-1` im verbose Modus steht der PK-232 in **Converse**
(Standard `CONMODE CONVERSE`). Alles, was danach gesendet wurde, ging als
Daten an die BBS und wurde vom TNC **als Echo zurückgegeben**. Belege aus
`20260928_094001_link_carry.log`:

| Gesendet | Zurück | Deutung |
|---|---|---|
| `OPMODE\r\n` (A.3) | `Unknown command. Type H for help.` + TinyBox-Prompt | Antwort der **BBS**, nicht des TNC |
| `CSTATUS\r\n`, `CONNECT\r\n` (A.3) | TinyBox-Prompt bzw. „Unknown command" | dito |
| Host-Frame `01 4F 4F 50 17` (OP) | `ctl=0x4F data=b'OP'` | **Echo des eigenen Frames** — eine echte Antwort trägt den Wert (T142: `OPPA`) |
| Host-Frames `01 4x 43 4F 17` (CO ch0–9) | je `data=b'CO'` | Echo; echte Antwort hat 5 Statusbytes (T142: `CO00000`) |
| Datenframe `01 20 0D 17` (A.7) | `ctl=0x20 data=b'\r\n'` | `$20` ist ein **Host→TNC**-CTL; der TNC sendet nie `$20`. Echo mit CR→CRLF |
| (A.4, unaufgefordert) | `ctl=0x4F data=b'HPN'` | Echo des `HP N`, das `_enter_host_mode_thread()` nach dem Handshake sendet (Schritt 5) |

Danach, zurück im verbose Modus (A.9): `CSTATUS` → `Ch. 0 - IO CONNECTED to
OE3GAS-1; v2`. Die Verbindung bestand — weil der TNC **Converse nie
verlassen hat**.

Nebenwirkung: `XFLOW OFF`, `HOST 3`, alle Host-Frames als Binärbytes und
der Datenframe wurden **als Packet-Daten an die BBS gesendet**.

### B.2 Ursache: der Handshake akzeptiert sein eigenes Echo

`comm/pk232_hostmode_sub.py::enter_host_mode()`:

```python
port.write(b"\rXFLOW OFF\r\rHOST 3")   # kein COMMAND-Zeichen davor
...
port.write(HPOLL_Y)                      # 01 4F 48 50 59 17
r = read_until(port, [HPOLL_ACK, HPOLL_Y], timeout=2.0)
# Accept both HP $00 (ACK) and HP Y (already in HPOLL ON) as success.
return (HPOLL_ACK in r or HPOLL_Y in r), r
```

1. Es wird **kein COMMAND-Zeichen** (`$03`) gesendet. Aus Converse heraus
   kommt `HOST 3` deshalb nie beim Befehlsinterpreter an. (Der Kommentar in
   `serial_manager.py:16` — „HOST 3 (XON + CANLINE + COMMAND + HOST Y)" —
   beschreibt eine Sequenz mit COMMAND, die der Code nicht sendet.)
2. Als Erfolg gilt auch `HPOLL_Y` im Empfang — das sind **exakt die Bytes,
   die gerade gesendet wurden**. In Converse kommt genau dieses Echo zurück.
   `CLAUDE.md` („Both `HP Y` and `HP $00` are valid success responses")
   nennt keinen Messbeleg, bei dem `HP Y` die echte Antwort auf das
   **Setzen** war.

Dieselbe Funktion benutzen App (`SerialManager._enter_host_mode_thread()`,
Ctrl+H, P49) und `hw_check`. **Das erklärt die ursprüngliche Beobachtung
(P64) vollständig:** Ctrl+H nach einem verbose Connect → Handshake „OK"
aus dem Echo → App glaubt Host Mode, aktiviert Baudot, sendet dessen Frames
(als Daten an die BBS), keine Link-Meldungen → Verbindung „nicht erkannt".
Zurück im verbose Modus geht es weiter, weil nie etwas umgeschaltet wurde.

### B.3 T142: Link-Status und OPMODE funktionieren im Host Mode

`20260928_094231_link_carry_host.log` — Verbindung **im Host Mode** auf
Kanal 1 aufgebaut:

- `OP` → `OPPA` (Packet) — TRM 4.3.2 bestätigt.
- `CO` Kanal 1 → `CO41000OE3GAS-1`; freie Kanäle → `CO00000`.
  `a='4'` → Zustand 5 (verbunden), `'0'` → Zustand 1 (frei); `b='1'` → v2.
  Pfad folgt **ohne Trennzeichen** direkt nach den fünf Statusbytes.
  TRM 4.3.3 bestätigt.
- Host → verbose: `CSTATUS` zeigt `Ch. 1 - CONNECTED to OE3GAS-1; v2`.
  Zurück in den Host Mode: `CO` Kanal 1 unverändert verbunden.
  **Eine Verbindung übersteht den Wechsel in beide Richtungen, sofern der
  TNC beim Wechsel im Befehlsmodus ist** (der zweite Host-Eintritt erfolgte
  nach `exit_host_mode()`, das seit P53.B selbst `$03` sendet).

**Damit ist die Aussage in `CLAUDE.md` („Channel model": „There is no
CSTATUS poll in Host Mode — the PK-232 never tells the host 'channel N is
connected to X' on demand") für Gerät B widerlegt.**

### B.4 Beobachtung: aktiver Kanal nach Host → verbose ist 9

In T142 zeigt `CSTATUS` nach dem Verlassen des Host Mode `Ch. 9 - IO`, und
`CONNECT` ohne Argument meldet `DISCONNECTED` (Zustand des aktiven Kanals
9, nicht des verbundenen Kanals 1). Die letzte Host-Abfrage vor dem Verlassen
war `CO` auf Kanal 9. **Hypothese:** Ein `$4x`-Frame setzt den aktiven
Kanal des TNC. Folge wäre: Nach Host → verbose tippt der Betreiber auf dem
falschen Kanal. Ungemessen — Teil D.

### B.5 `decode_link_status()` gibt Rohbytes statt Werte zurück
T142 liefert `v2: 48`, `unacked: 48` … — der Docstring sagt bewusst
„raw byte values". Jetzt ist das Format gemessen: alle fünf Felder sind
„value ORed with $30" (TRM), also `& 0x0F`.

---

## Teil A — Handshake: COMMAND-Zeichen vorab, Erfolg nur bei echter Antwort

`src/pk232py/comm/pk232_hostmode_sub.py`, `enter_host_mode()`:

### A.1 Converse verlassen
Vor `\rXFLOW OFF\r\rHOST 3` das COMMAND-Zeichen senden und auf `cmd:`
warten (bis 2 s). Das Zeichen kommt als **Parameter** (`command_char:
bytes = b"\x03"`), gespeist aus `SerialManager.command_char` — keine zweite
Quelle für den Wert. Im Subprozesspfad als drittes Argument übergeben.

Kommt kein `cmd:`: ein zweites und drittes COMMAND-Zeichen innerhalb von
`CMDTIME` (TRANSPARENT braucht drei, `CLAUDE.md` P53.B) — dieselbe Regel,
die die Erkennungskette Stufe 2b verwendet; die **vorhandene** Hilfsfunktion
wiederverwenden, falls sie ohne Qt/Port-Objekt aufrufbar ist, sonst die
Regel in eine gemeinsame reine Funktion auslagern und beide Stellen darauf
umstellen.

### A.2 Erfolg prüfen, den ein Echo nicht fälschen kann
Nach dem bisherigen `HPOLL_Y`-Schritt zusätzlich:

```
SOH $4F O P ETB   (Abfrage OPMODE)
```

Erfolg **nur**, wenn eine Antwort `SOH $4F O P <mindestens ein weiteres
Byte> ETB` kommt. Ein Echo liefert `O P` ohne Wert (B.1), eine echte
Antwort liefert den Wert (B.3: `OPPA`).

`HPOLL_Y` im Empfang allein gilt nicht mehr als Erfolg. `HPOLL_ACK`
(`HP $00`) bleibt notwendig. Den Kommentar „Accept both HP $00 (ACK) and HP
Y (already in HPOLL ON)" entfernen; im Docstring festhalten, warum.

### A.3 Rückgabe
`(False, raw)` mit dem Grund im Log, wenn die OPMODE-Prüfung fehlschlägt
(„echo instead of Host Mode response — TNC probably in Converse/Transparent").
`SerialManager._enter_host_mode_thread()` behandelt das wie jeden anderen
Fehlschlag (vorhandener Pfad: Port wieder öffnen, Statusmeldung) — **kein**
`host_mode_changed(True)`.

**Commits:**
```
Host Mode entry: leave Converse with the COMMAND character first
Host Mode entry: success needs a real OPMODE answer, not an echo
```

---

## Teil B — `decode_link_status()` liefert Werte

`tools/hw_check.py`: `v2`, `unacked`, `retries`, `conperm` jeweils
`& 0x0F`; `v2`/`conperm` als `bool`. Docstring: Format gemessen, T142,
Gerät B. Die Funktion wandert **noch nicht** in `src/` — das macht P67, dann
als einzige Stelle für App und hw_check.

**Commit:** `hw_check: decode_link_status returns values (T142 format)`

---

## Teil C — `link_carry` misst im Befehlsmodus

`hw_check.py link_carry`, A.3 und A.9: vor den verbose Abfragen das
COMMAND-Zeichen senden und `cmd:` abwarten (gleiche Hilfsfunktion wie
Teil A.1). Ohne `cmd:` → A.3 `FAIL` mit „still in Converse", keine
Abfragen senden (sie gingen sonst an die Gegenstation).

Neu **A.4a**: im Log vermerken, ob der Handshake aus Teil A die
OPMODE-Prüfung bestanden hat (Rohantwort).

**Commit:** `hw_check: link_carry queries only from command mode`

---

## Teil D — aktiver Kanal nach Host → verbose (Hypothese B.4)

### D.1 Aktiver Kanal
`hw_check.py link_carry_host`, nach dem bestehenden „recheck":
1. `CO` auf Kanal **3** (frei) senden, danach **nichts** mehr auf `$4x`.
2. Host Mode verlassen, `CSTATUS` — auf welchem Kanal steht `IO`?
3. Ergebnis `INFO`: `io_channel_after_exit=<n>`, `last_co_channel=3`.

Stimmt `n == 3`, ist B.4 bestätigt; dann muss P67 beim Wechsel nach
verbose den aktiven Kanal ausdrücklich setzen.

### D.2 Zurück in Converse nach Host → verbose
Betreiberhinweis (28.09.2026): Bei bestehender Verbindung kommt man **nur**
mit dem COMMAND-Zeichen (Ctrl-C) nach `cmd:`; mit `CONVERSE` (`CONV`)
zurück, danach geht jede Eingabe als Paketinhalt an die Gegenstation.
`exit_host_mode()` endet heute mit `$03`, also in `cmd:` — für einen
Betreiber, der im verbose Modus weiterschreiben will, fehlt der Schritt
zurück nach Converse, **auf dem verbundenen Kanal**.

Messung im Anschluss an D.1 (Verbindung auf Kanal 1 besteht noch):
1. `CONVERSE` senden (ohne Kanalwechsel, aktiver Kanal wie D.1 ergab),
   dann `\r` → 10 s aufzeichnen: kommt der BBS-Prompt, oder eine
   TNC-Meldung (z. B. dass der Kanal nicht verbunden ist)?
2. COMMAND-Zeichen, `cmd:` abwarten.
3. Auf Kanal 1 wechseln — mit dem CHSWITCH-Zeichen des TNC
   (`SerialManager`/Konfiguration ist die Quelle; ist dort keins geführt,
   verbose `CHSWITCH` abfragen und den Wert loggen, nicht raten) gefolgt
   von `1` —, dann `CONVERSE`, `\r` → 10 s aufzeichnen: BBS-Prompt?
4. COMMAND-Zeichen, `cmd:`; `CSTATUS` loggen.

Ergebnis `INFO` je Schritt mit Rohtext. Das zeigt P67, ob nach dem
Rückweg ein Kanalwechsel **und** `CONVERSE` nötig sind, damit der
Betreiber dort weiterschreiben kann, wo er vor dem Host Mode war.

**Commit:** `hw_check: link_carry_host checks active channel and CONVERSE after exit`

---

## Teil E — Tests (zuerst rot)

`src/pk232py/tests/test_hostmode_sub.py` (neu oder vorhandene Datei):
- **Fake-Port, der jedes geschriebene Byte zurückgibt** (Converse mit
  ECHO): `enter_host_mode()` → `False`. **Heute `True`** — das ist der rote
  Test für B.2.
- Fake-Port im Befehlsmodus, der auf `HOST 3` mit `cmd:` und auf die
  Frames mit echten Antworten (`HP $00`, `OPPA`) antwortet → `True`.
- Fake-Port in Converse, der auf `$03` mit `cmd:` antwortet und danach
  wie oben → `True`, und das COMMAND-Zeichen wurde **vor** `HOST 3`
  geschrieben (Reihenfolge der Schreibzugriffe prüfen).
- `command_char` wird durchgereicht (anderer Wert → dieser Wert steht im
  Schreibprotokoll).

`test_hw_check_link_carry.py`: `decode_link_status()` mit den echten
T142-Bytes `CO41000OE3GAS-1` und `CO00000`.

`test_serial_manager.py`: `_enter_host_mode_thread()` mit einem Handshake,
der `(False, …)` liefert → **kein** `host_mode_changed(True)`.

**Commit:** `Tests: Host Mode entry rejects its own echo`

---

## Teil F — Dokumentation

- `Testplan.md`:
  - T141, Gerät B, 28.09.2026: **ungültig** — Handshake aus Converse
    (B.1); nach P66 wiederholen.
  - T142, Gerät B, 28.09.2026: PASS mit den Befunden aus B.3 und der
    Beobachtung B.4.
  - Neu **T143**: Ctrl+H in der App nach einem verbose Connect (der
    Originalfall aus P64) — erwartet nach P66: Host Mode wird wirklich
    betreten; die Verbindungsanzeige kommt erst mit P67.
- `CLAUDE.md`:
  - „Channel model": die No-CSTATUS-Aussage für Gerät B **ersetzen** durch
    den T142-Befund (CO-Abfrage je Kanal, Format, Beispielbytes).
  - „Both `HP Y` and `HP $00` are valid success responses" **ersetzen**
    durch: nur `HP $00`; `HP Y` im Empfang ist in Converse das eigene
    Echo (B.2). Erfolg zusätzlich über OPMODE-Wert.
  - Known Gotcha: „In Converse echot der TNC auch Host-Frames — jede
    Prüfung, die auf Bytes wartet, die man selbst gesendet hat, ist dort
    wertlos."
  - Kommentar `serial_manager.py:16` an die tatsächliche Sequenz anpassen.
- `Backlog.md`, P64-Eintrag: Ursache für „Verbindung nicht erkannt" ist
  B.2; P67 = Verbindungstabelle mit CO-Abgleich.

**Commits:**
```
Testplan: T141 invalid, T142 results, new T143
Docs: CLAUDE.md CO query works, HP Y is an echo in Converse
Backlog: P64 root cause and P67
Docs: add P66 spec file
```

---

## Definition of Done

- Die roten Tests aus Teil E waren vor der Umsetzung nachweislich rot
- `git grep -n "HPOLL_Y in r" -- src` → keine Treffer
- Der COMMAND-Zeichen-Wert hat genau eine Quelle
- volle Suite grün, **Push**, Meldung mit Hash;
  `.\Sources2Text.ps1`, „sources aktualisiert"