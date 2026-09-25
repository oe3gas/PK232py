# Claude Code Prompt — P45: Recovery mit Rückmeldung, ehrlicher Verbindungszustand

> Ablage: `docs/P45_Recovery_Feedback_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher `CLAUDE.md`, `SERIAL_CONNECTION_STATE_MACHINE.md`,
> `docs/P43_TNC_State_Detection_Spec.md`,
> `docs/P44_Chip_States_Init_Recovery_Spec.md` lesen.

---

## Befund (25.09.2026, Operator am Gerät)

Ablauf: TNC stand im Host Mode → Anwendung gestartet → `Connect` →
Fehlermeldung der Erkennungskette → **die Anwendung zeigte sich trotzdem
als verbunden** (Host-Mode-Knopf grün, Firmware `unknown`) → `Recovery`
gedrückt → **keine sichtbare Reaktion** → `Host Mode` gedrückt →
„Switching" → Baudot-Maske → TNC im Host Mode, also wieder ansprechbar.

Zwei Lücken:

1. **Der Verbindungszustand log.** Nach einem gescheiterten Init darf die
   Anwendung sich nicht als verbunden darstellen.
2. **Recovery meldet nichts** und hinterlässt einen undefinierten
   Zustand. Dass sie gewirkt hat, zeigte sich erst über einen Umweg.

Ergänzend zur Einordnung: **Ein gesunder TNC im Host Mode antwortet auch
in einem Terminalprogramm nicht** — er verarbeitet dort nur gerahmte
Frames. Stille in PuTTY unterscheidet „normal im Host Mode" nicht von
„festgefahren". Die Halbframe-Erklärung aus P44 Teil C bleibt damit eine
**Vermutung**; in `CLAUDE.md` entsprechend als „vermutet, Messung
ausstehend" formulieren, nicht als Befund.

---

## P45.1 — Recovery endet in einem belegten Zustand

`Recovery` läuft künftig in drei Abschnitten und meldet jeden:

1. **Rückholsequenz senden** (vorhandene Funktion, Doppel-`SOH`, `GG`,
   `HOST OFF`) — Logzeile mit den gesendeten Bytes in Hex
2. **Zustand feststellen**: die Erkennungskette aus P43 fahren (`CR` →
   `cmd:`; sonst HPOLL-Frame; sonst Rückholsequenz erneut). Es wird die
   **vorhandene** Kette aufgerufen, keine zweite Fassung gebaut
3. **Ergebnis melden** — im Log **und** sichtbar in der Anwendung:

| Ergebnis | Meldung |
|---|---|
| `cmd:` bestätigt | „Recovery successful — TNC is at the command prompt (verbose mode)." |
| nur HPOLL antwortet | „TNC responds in Host Mode — leaving Host Mode…" → danach Schritt 2 wiederholen |
| nichts antwortet | „Recovery did not reach the TNC. Power-cycle it and reconnect." |

Endzustand bei Erfolg: **verbose, `verbose_confirmed` gesetzt.** Von dort
kann der Operator normal weiterarbeiten — Parameter-Upload und
Host-Mode-Eintritt laufen über die bestehenden Wege.

Die Rückmeldung erscheint als Statuszeile **und** im RX-Fenster des
verbose-Terminals (`[SYS] …`), damit sie auch später im Mitschnitt steht.
Dauert die Sequenz länger als eine Sekunde, währenddessen den Knopf
sperren und „Recovery running…" anzeigen.

**Commit:** `Recovery: report what happened and end in a confirmed verbose state`

---

## P45.2 — Nach gescheitertem Init nicht „verbunden" sein

Schlägt `init_tnc` fehl:

- der Port wird geschlossen oder der Zustand ausdrücklich auf
  „nicht verbunden" gesetzt — **kein** grüner Host-Mode-Knopf, kein
  „connected" in der Statusleiste
- die Betriebsart-Anzeige bleibt leer oder zeigt „—"; `TNC-Firmware`
  zeigt weiterhin `unknown`, was dann stimmig ist
- `Recovery` bleibt bedienbar (es ist der Ausweg), ebenso `Connect`
- die Fehlermeldung der Kette erscheint einmal als Dialog **und** in der
  Statuszeile — nicht nur in der Konsole

Prüfen, welche Zustände die Anwendung dafür führt (`is_connected`,
Knopffreigaben, Statusleiste) und ob sie aus **einer** Quelle gespeist
werden. Werden sie an mehreren Stellen gesetzt, das in `Backlog.md`
vermerken — dieselbe Fehlerklasse wie „zwei Wahrheiten" bei den
QObject-Signalen.

**Commit:** `MainWindow: a failed init does not leave the app connected`

---

## P45.3 — Tests

- Recovery: Attrappe antwortet nach der Sequenz mit `cmd:` → Erfolgsmeldung,
  `verbose_confirmed` gesetzt
- Recovery: Attrappe antwortet nur auf HPOLL → Host-Mode-Austritt wird
  gefahren, danach Erfolgsmeldung
- Recovery: Attrappe schweigt durchgehend → Fehlermeldung mit dem
  Handgriff, `verbose_confirmed` **nicht** gesetzt
- Init scheitert → `is_connected` ist falsch, Host-Mode-Knopf nicht grün,
  Fehlermeldung sichtbar
- Recovery ist auch nach gescheitertem Init bedienbar

**Commit:** `Tests: recovery feedback and connection state after a failed init`

---

## P45.4 — Dokumentation

- `CLAUDE.md`:
  - **Ein TNC im Host Mode antwortet auch in PuTTY nicht.** Stille im
    Terminal unterscheidet „normal im Host Mode" nicht von
    „festgefahren"; nur eine gerahmte Abfrage trennt die beiden Fälle
  - die Halbframe-Erklärung als **Vermutung** kennzeichnen
  - Recovery: was sie tut, in welchem Zustand sie endet
- `SERIAL_CONNECTION_STATE_MACHINE.md`: Recovery als eigener Abschnitt mit
  den drei Abschnitten und dem Endzustand
- `Testplan.md`: Fall — Anwendung im Host Mode abwürgen, starten,
  `Connect` (muss scheitern und **nicht** verbunden zeigen), `Recovery`
  (muss Erfolg melden und in verbose enden), dann normal verbinden

**Commit:** `Docs: recovery behaviour and Host Mode silence`

---

## Definition of Done

- `.venv\Scripts\python.exe -m pytest` grün
- Nach einem gescheiterten Init zeigt die Anwendung sich nicht als
  verbunden
- `Recovery` meldet in jedem der drei Fälle etwas Sichtbares
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"
- Danach vom Operator: der Ablauf aus dem Testplan-Fall, einmal
  durchgespielt