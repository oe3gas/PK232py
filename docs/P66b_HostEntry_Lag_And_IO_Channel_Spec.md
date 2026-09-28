# Claude Code Prompt — P66b: Verspäteter Host-Mode-Eintritt bei bestehender Verbindung; aktiver Kanal folgt dem letzten `$4x`-Frame

> Ablage: `docs/P66b_HostEntry_Lag_And_IO_Channel_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Grundlage: `main` @ `2767c51`, Läufe vom 28.09.2026 13:35–13:42 und T143,
> **Gerät B, Release 01.AUG.91** (Banner in allen Logs).
> **P66a zuerst umsetzen** (CHSWITCH-Wert) — die Läufe unten liefen noch
> ohne P66a, D.2.3 sendete nachweislich `$001CONVERSE` → `?What?`.

---

## Befund

### B.1 T141 (13:35): Host-Mode-Eintritt scheitert — der TNC geht aber verspätet doch hinein

A.3 funktioniert jetzt (Ctrl-C → `cmd:`; `OPMODE` → `PAcket`; `CSTATUS` →
`Ch. 0 - IO CONNECTED to OE3GAS-1; v2`). Danach meldet der Handshake:

```
enter_host_mode: echo instead of Host Mode response ... (hpoll_ack=False ...)
FAIL:014f4850591758466c6f772020202020776173204f4e014f4f5017
```

Dekodiert: `01 4F 'HPY' 17` · `XFlow     was ON` · `01 4F 'OP' 17`

1. Die Antwort auf `XFLOW OFF` (`XFlow was ON`) kommt **erst nach** dem
   Echo des `HPOLL Y`-Frames — also Sekunden nach dem Senden. Der
   Befehlsinterpreter hinkt hinterher; das sofortige Zeichen-Echo nicht.
2. Direkt danach: `VHF ON`, `VHF`, `HBAUD 1200`, `HBAUD` → jeweils **keine
   Antwort** (`''`). Ein TNC im verbose Modus antwortet immer. Stumm bleibt
   er im **Host Mode** — `HOST 3` wurde also verspätet doch ausgeführt,
   nachdem der Handshake schon aufgegeben hatte.
3. Nächster Lauf 13:37:23: `TNC did not respond to wakeup` (plus
   `ClearCommError ... Das Handle ist ungültig`) — passt zu einem TNC, der
   im Host Mode zurückgelassen wurde.

**Folge:** App/hw_check glauben „verbose", der TNC ist im Host Mode —
genau der Zustandsversatz, den P66 verhindern sollte, nur umgekehrt.

In T143 (App, gleicher Ausgangszustand: verbose Connect, Converse, Ctrl+H)
gelang der Eintritt. Das Verhalten ist also **zeitabhängig**, nicht
grundsätzlich. Warum der Interpreter in T141 so langsam war (unmittelbar
davor liefen drei Abfragen, die Verbindung ist aktiv), ist ungemessen.

### B.2 Der Handshake protokolliert zu wenig
`FAIL:` enthält nur den Empfang der **letzten** Schritte. Was nach
`escape_converse()`, nach `HOST 3` und nach dem CR ankam, fehlt — damit
lässt sich B.1 nicht zeitlich auflösen.

### B.3 T142 D.1 bestätigt: der aktive Kanal folgt dem letzten `$4x`-Frame
Zwei Läufe (13:38, 13:40): letzter Frame vor `HOST OFF` war `CO` auf
Kanal 3 → verbose `CSTATUS` zeigt `Ch. 3 - IO`. Ohne D.1-Probe (erste
Hälfte) war es Kanal 9 = letzter `CO`. **Bestätigt für Gerät B.**

Nutzen für P67: Wer vor `HOST OFF` als **letzten** `$4x`-Frame einen auf
Kanal n sendet (z. B. `CO` für den verbundenen Kanal), steht danach im
verbose Modus auf Kanal n — ohne CHSWITCH-Zeichen.

### B.4 CHSWITCH ist auf Gerät B `$00`
`CHSWITCH` → `CHSwitch  $00` in beiden Läufen: kein Umschaltzeichen
gesetzt. Ein Kanalwechsel im verbose Modus per Zeichen ist so nicht
möglich; B.3 ist der Weg.

### B.5 `CONVERSE` auf einem freien Kanal
D.2.1: `CONVERSE` auf Kanal 3 (frei), danach `\r` → nur Echo, kein Prompt,
keine Fehlermeldung. Der TNC ist damit in Converse auf einem **nicht
verbundenen** Kanal. Nach TRM sendet er dort jede Eingabezeile als
**UNPROTO-UI-Frame** aus — das `\r` aus D.2.1 wurde vermutlich gesendet.
Für P67: `CONVERSE` nur auf einem verbundenen Kanal. Für hw_check: D.2.1
nur mit `confirm_tx()`.

### B.6 Aufräumen trennt den falschen Kanal
Ende T142: verbose `DISCONNECT` auf dem aktiven Kanal 3 →
`Link state is: DISCONNECTED`. Die Verbindung auf **Kanal 1** blieb stehen
(bis zum TinyBox-Timeout).

### B.7 T143 (App)
Betreiber: nach Ctrl+H erscheint die VHF-Packet-Maske, **keine**
Verbindungsanzeige, obwohl der TNC verbunden ist; nach Leave Host Mode
zeigt `CSTATUS` Kanal 0 weiterhin `CONNECTED to OE3GAS-1`. Eintritt und
Verbindungserhalt: **bestanden**. Verbindungsanzeige: erwartet offen (P67).

---

## Teil A — Handshake: vollständiges Protokoll

`comm/pk232_hostmode_sub.py::enter_host_mode()`: jeden Schritt mit
Zeitstempel (monoton, ms seit Beginn), gesendeten Bytes und **allen**
empfangenen Bytes sammeln und im Fehlerfall vollständig nach stderr
schreiben (eine Zeile je Schritt, hex + Text). Im Erfolgsfall auf
`logger.debug`. Kein Verhaltenswechsel in diesem Teil.

**Commit:** `Host Mode entry: log every step with timestamps`

---

## Teil B — Handshake: verspäteten Eintritt erkennen statt Zustandsversatz

Schlägt die OPMODE-Prüfung fehl (nur Echo), **nicht sofort aufgeben**:

1. Bis zu 3 weitere Versuche im Abstand von 1,5 s: `OPMODE_QUERY` erneut
   senden, bis `ETB` lesen. Kommt eine echte Antwort (`O P` + Wert) →
   Erfolg („late entry", im Protokoll vermerkt, mit Versuchsnummer).
2. Bleibt es beim Echo: Fehlschlag wie bisher.

Begründung: Ein Echo beweist, dass der TNC (noch) nicht im Host Mode ist.
Ein verspätet ausgeführtes `HOST 3` macht die spätere Abfrage echt — B.1
zeigt, dass genau das passiert. Die Wartezeit gilt nur im Fehlerpfad; der
Normalfall wird nicht langsamer.

Die Zahlen (3 × 1,5 s) als benannte Konstanten mit Verweis auf B.1; nach
der Hardware-Messung (Teil E) anpassen.

**Commit:** `Host Mode entry: retry the OPMODE check to catch a late HOST 3`

---

## Teil C — hw_check: Aufräumen und CONVERSE

- `link_carry_host`, Aufräumen: den verbundenen Kanal aus der letzten
  `CO`-Abfrage nehmen und dort trennen — im Host Mode per `DI` auf
  `$4n` **vor** `HOST OFF` (die Funktion existiert schon als
  „B cleanup DI" im ersten T142-Lauf). Kein verbose `DISCONNECT` auf dem
  aktiven Kanal mehr.
- D.2.1: vor `CONVERSE` + `\r` auf einem nicht verbundenen Kanal
  `confirm_tx()` mit Hinweis „may transmit an UNPROTO frame".
- Neu **D.3**, die P67-Technik aus B.3 prüfen: im Host Mode als letzten
  `$4x`-Frame `CO` auf dem **verbundenen** Kanal senden, `HOST OFF`,
  `CSTATUS` (erwartet `IO` auf diesem Kanal), dann `CONVERSE` + `\r`
  (hinter `confirm_tx()`) → 10 s aufzeichnen: kommt der BBS-Prompt?
  Danach Ctrl-C, `cmd:`.

**Commits:**
```
hw_check: link_carry_host disconnects the connected channel
hw_check: link_carry_host D.3 last CO selects the verbose channel
```

---

## Teil D — Tests (zuerst rot)

- Fake-Port, der zuerst nur echot und ab dem dritten OPMODE-Versuch mit
  `01 4F 'OPPA' 17` antwortet → `enter_host_mode()` → `True`, Protokoll
  enthält „late entry" (heute `False`).
- Fake-Port, der dauerhaft nur echot → `False`, nach genau 1 + 3
  OPMODE-Versuchen.
- Fehlerfall: stderr enthält je Schritt eine Zeile mit Zeitstempel und
  Empfang (Teil A).
- hw_check Dry-Run: Aufräumen zeigt `DI` auf dem Kanal der letzten
  verbundenen `CO`-Antwort; D.3 in der Vorschau.

**Commit:** `Tests: late Host Mode entry and full handshake log`

---

## Teil E — Doku und Testplan

- `Testplan.md`:
  - T141 (28.09. 13:35, Gerät B): FAIL — verspäteter Eintritt (B.1);
    nach P66b wiederholen, **dreimal**, um die Zeitabhängigkeit zu sehen.
  - T142 (13:38, 13:40, Gerät B): PASS; D.1 bestätigt B.3; D.2.3
    ungültig (vor P66a).
  - T143 (Gerät B): PASS für Eintritt und Verbindungserhalt; Anzeige
    offen → P67.
- `CLAUDE.md` Known Gotchas (Gerät B):
  - Der aktive verbose Kanal nach `HOST OFF` ist der Kanal des letzten
    `$4x`-Frames.
  - `CHSWITCH` steht nach dem Einschalten auf `$00`.
  - `CONVERSE` auf einem freien Kanal sendet Eingaben als UNPROTO.
  - Bei aktiver Verbindung kann der Befehlsinterpreter Sekunden hinter dem
    Zeichen-Echo liegen; `HOST 3` kann nach dem Handshake-Timeout wirken.
- `Backlog.md`, P67: die Technik aus B.3 als Grundlage für „zurück auf den
  verbundenen Kanal".

**Commits:**
```
Testplan: T141 T142 T143 results 28.09.2026
Docs: CLAUDE.md IO channel follows last channel frame
Backlog: P67 uses last-CO channel selection
Docs: add P66b spec file
```

---

## Definition of Done

- neue Tests zuerst rot, volle Suite grün
- Dry-Run `link_carry_host` zeigt korrektes Aufräumen und D.3
- **Push**, Meldung mit Hash; `.\Sources2Text.ps1`, „sources aktualisiert"