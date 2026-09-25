# Claude Code Prompt — P44: Chip-Zustände, verbose-Terminal, Rückholstufe im Init

> Ablage: `docs/P44_Chip_States_Init_Recovery_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher `CLAUDE.md`, `SERIAL_CONNECTION_STATE_MACHINE.md` (§1, §14),
> `docs/P43_TNC_State_Detection_Spec.md` lesen.

---

## Teil A — Chip-Zustände: rufend ist nicht verbunden

### Befund (25.09.2026, Screenshot)
Chip 1 steht bernstein mit `OE3TEC`, während die Statusanzeige
`DISCONNECTED` meldet. Der Verbindungsversuch ist gescheitert, der Chip
blieb aber im Zustand „rufend" stehen.

Zusätzlich widersprechen sich zwei Farblegenden im selben Fenster: Im
MHEARD-Panel steht „amber = connected", am Chip bedeutet bernstein
„rufend".

### A.1 Zustände und Darstellung

| Zustand | Farbe | Beschriftung | Rahmen |
|---|---|---|---|
| frei | grau | Kanalnummer | normal |
| **rufend** | bernstein, **pulsierende Fläche** | `OE3TEC …` (Auslassungspunkte) | normal |
| verbunden | grün | `OE3TEC` | normal |
| gescheitert | rot, **1,5 s**, dann frei | Kanalnummer | normal |

Die Auslassungspunkte sind Pflicht, die Pulsation Kür: Der Zustand muss
auch ohne Farbunterscheidung erkennbar sein — und auf einem Screenshot.

### Pulsation der Chipfläche

**Eine** `QVariantAnimation` für die gesamte Kanalleiste, nicht eine je
Chip. Sie interpoliert zwischen zwei Bernsteintönen und setzt den Wert
per Stylesheet auf **alle** rufenden Chips. Vorteil des einen
Animationsobjekts: die Chips pulsieren synchron — das wirkt beabsichtigt
statt zufällig.

- Zyklus **1,2 s**, `InOutSine`, `setLoopCount(-1)`
- Farbhub klein: `#8a6a1e` ↔ `#b08a2a`. Ein kräftig blinkender Knopf
  ermüdet innerhalb von Minuten, und ein HF-Connect kann über `RETRY` und
  `FRACK` eine Minute dauern
- unter 3 Hz bleiben (hier 0,8 Hz) — Rücksicht auf lichtempfindliche
  Menschen
- **starten**, sobald mindestens ein Kanal ruft; **stoppen**, sobald
  keiner mehr ruft. Kein Dauerläufer auf dem Notebook
- die Textfarbe bleibt konstant, damit die Beschriftung ruhig steht

### A.2 Gescheiterter Connect räumt den Chip

Die Link-Meldungen, die einen Fehlschlag bedeuten, führen den Chip
**zurück auf frei** (über den roten Zwischenzustand):

- `Retry count exceeded`
- `<call> busy`
- `DISCONNECTED`, solange der Kanal im Zustand „rufend" war

Die Zuordnung läuft weiterhin kanalbezogen über `on_channel_state`
(P18/P16) — **kein** neuer Pfad.

### A.3 Eine Farblogik im ganzen Fenster

MHEARD-Panel auf dieselbe Semantik umstellen: verbundene Stationen
**grün**, nicht bernstein. Legende entsprechend ändern
(`* = direct (no digi) | green = connected`).

**Commits:**
```
Packet screen: calling, connected and failed chip states
Packet screen: one colour semantics for chips and MHEARD
```

---

## Teil B — Verbose-Terminal

### Befund
- Nach `TNC connect + enter verbose mode` erscheint **kein `cmd:`** im
  RX-Fenster
- Ein leeres `CR` aus dem TX-Feld wird nicht gesendet; erst ein beliebiges
  Zeichen plus `CR` führt zu `?What?` und danach zum Prompt

### B.1 Leeres CR senden
Im verbose-Terminal löst `Enter` bei leerem Eingabefeld ein `CR` aus. Ein
nacktes Enter ist die übliche Art, sich den Prompt zu holen — und die
einzige, die nichts verändert.

### B.2 Prompt nach dem Init zeigen
Nach erfolgreichem Init ist der Prompt bereits geflossen und im
Init-Ablauf verbraucht worden. Zwei Wege, CC wählt und begründet:

- die im Init empfangene Antwort (Banner + `cmd:`) ins RX-Fenster
  spiegeln, oder
- nach dem Init ein `CR` senden und die Antwort anzeigen

Bevorzugt der erste Weg: er zeigt, was das Gerät wirklich gesendet hat
(inklusive Banner und Firmwarezeile), und sendet nichts zusätzlich.

**Commit:** `Verbose terminal: bare CR and prompt after init`

---

## Teil C — Rückholstufe in der Erkennungskette

### Befund (Konsole, 25.09.2026 13:35)
Nach dem Abwürgen der Anwendung im Host Mode (`Ctrl-C` in der Konsole)
antwortete der TNC auf **alle drei** Schritte mit 0 Bytes — auch auf den
HPOLL-Frame:

```
step 1 - wakeup '*'        -> 0 B
step 2 - CR                -> 0 B
step 3 - HPOLL query frame -> 0 B, 0 frame(s)
```

Ein sauber im Host Mode stehender TNC müsste auf die HPOLL-Abfrage
antworten. **Vermutung:** Der Abbruch mitten in einer Frame-Übertragung
hat den Frameparser des TNC in einem unvollständigen Frame stehen lassen;
er wartet auf `ETB` und verwirft alles Weitere — auch ein neues `SOH`.

### C.1 Neue Stufe 3b
Vor dem Aufgeben die **dokumentierte Rückholsequenz** fahren, die in der
Anwendung bereits als Menüpunkt `Recovery` existiert (Doppel-`SOH`, `GG`,
danach `HOST OFF`). **Vorhandene Funktion verwenden, nichts nachbauen.**

Ablauf:

1. Stufe 3a wie bisher: HPOLL-Abfrageframe → `$4F`-Frame? → Host Mode
2. **Stufe 3b (neu):** Rückholsequenz senden, kurz warten, dann `CR` →
   `cmd:`? → verbose, weiter
3. erst danach Stufe 4 (Abbruch mit der bekannten Meldung)

Die Rückholsequenz ist harmlos, wenn gar kein TNC angeschlossen ist — es
gehen ein paar Bytes ins Leere.

### C.2 Rohbytes protokollieren
Die Kette protokolliert derzeit nur die Byte-**Anzahl**. Für jeden Schritt
zusätzlich die **gesendeten und empfangenen Bytes in Hex** auf
`DEBUG`-Ebene, wie im Werkzeug. Bei 0 Bytes kostet das nichts und beim
nächsten unklaren Fall spart es einen Messlauf.

**Commit:** `SerialManager: recovery stage in the detection chain`

---

## Teil D — Tests

- Chip: `CH_CALLING` zeigt Auslassungspunkte; `Retry count exceeded`,
  `busy` und `DISCONNECTED` aus dem Zustand „rufend" führen über rot nach
  frei
- Pulsations-Timer läuft nur, solange ein Kanal ruft, und wird gestoppt
- MHEARD: verbundene Station grün, Legende passt
- Verbose-Terminal: leeres Enter sendet genau ein `\r`
- Erkennungskette: HPOLL stumm → Rückholsequenz wird gefahren; danach
  `cmd:` → Erfolg; bleibt auch das stumm → Abbruch, **kein** Upload

**Commit:** `Tests: chip states, bare CR, recovery stage`

---

## Teil E — Dokumentation

- `CLAUDE.md`:
  - Farbsemantik der Packet-Maske als Tabelle (grau/bernstein/grün/rot),
    gültig für Chips **und** MHEARD
  - neuer Fallstrick: **Ein im Host Mode abgewürgter Prozess kann den TNC
    mit einem halben Frame zurücklassen.** Er antwortet dann auf gar
    nichts mehr, auch nicht auf HPOLL; die dokumentierte Rückholsequenz
    holt ihn zurück. Beobachtet 25.09.2026
- `SERIAL_CONNECTION_STATE_MACHINE.md`, §1: Stufe 3b ergänzen
- `Testplan.md`: Fall — Anwendung im Host Mode abwürgen, neu starten,
  verbinden; erwartet wird ein Aufbau über die Rückholstufe

**Commit:** `Docs: colour semantics, half-frame recovery`

---

## Definition of Done

- `.venv\Scripts\python.exe -m pytest` grün
- Ein gescheiterter Connect hinterlässt keinen bernsteinfarbenen Chip
- Leeres Enter im verbose-Terminal liefert den Prompt
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"
- Danach vom Operator: Anwendung im Host Mode abwürgen, neu starten,
  verbinden; dazu ein Connect auf ein nicht erreichbares Rufzeichen