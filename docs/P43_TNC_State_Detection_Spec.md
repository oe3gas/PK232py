# Claude Code Prompt — P43: Zustandserkennung beim Verbindungsaufbau

> Ablage: `docs/P43_TNC_State_Detection_Spec.md` im Repo.
> **Ersetzt** den früheren Entwurf `P43_Confirm_Verbose_Spec.md`, falls er
> schon im Repo liegt — in diesem Fall die alte Datei löschen und das im
> Commit-Text vermerken.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher `CLAUDE.md`, `SERIAL_CONNECTION_STATE_MACHINE.md` (§1 Wakeup,
> §14 aus P40), `docs/P34_Normalize_Verify_Spec.md` lesen.

---

## Belegte Ursache

Vom Operator am Gerät reproduziert (24.09.2026):

- **frisch eingeschalteter TNC**: Verbindungsaufbau läuft normal durch
- **TNC im Host Mode** (die Anwendung hinterlässt ihn dort beim Beenden):
  der Upload läuft in jede Zeitgrenze — 68 Befehle × 5 s, keiner
  ausgeführt

Damit ist die Kette belegt: Beim Neustart der Anwendung steht der TNC im
Host Mode, der Wakeup bemerkt es nicht, und der Uploader sendet Klartext
an ein Gerät, das Frames erwartet.

Der Wächter aus P40.2 greift hier **nicht**: `SerialManager.is_host_mode`
ist die *Überzeugung der Software*. Nach einem frischen Start steht das
Flag auf `False`, während der TNC im Host Mode ist. Geprüft werden muss
das **Gerät**.

---

## P43.1 — Die Erkennungskette

`SerialManager._init_tnc_thread()` bekommt vier Schritte. Jeder Schritt
wird protokolliert (gesendete Bytes, empfangene Bytes, Schlussfolgerung).
Zeitgrenzen **kurz**: 1,5 s je Schritt — die Erkennung darf nicht länger
dauern als das, was sie verhindert.

| # | Reiz | Antwort | Schluss |
|---|---|---|---|
| 1 | `*` | Banner **oder** `cmd:` | verbose, frisch eingeschaltet → fertig |
| 2 | `CR` | `cmd:` | verbose, bereits wach → fertig |
| 3 | `SOH $4F H P ETB` (HPOLL-Abfrage) | ein `$4F`-Frame | **Host Mode** → dokumentierten Austritt fahren, danach Schritt 2 wiederholen |
| 4 | — | nichts von alldem | kein PK-232 erreichbar |

Begründungen, die als Kommentar in den Code gehören:

- Schritt 2 **vor** Schritt 3: Der bereits wache, verbose TNC ist der
  häufigere Fall und mit einem einzigen `CR` erledigt
- Schritt 3 muss **aktiv fragen**: Im Host Mode sendet der TNC von sich
  aus nichts, solange `HPOLL` auf ON steht (Werkseinstellung), und `*`
  ist für ihn kein gültiges Frame — er antwortet gar nicht
- Der HPOLL-Abfrageframe wird beim Host-Mode-Eintritt bereits verwendet;
  **vorhandene Funktionen nutzen**, nichts nachbauen

Für Schritt 3: Austritt über den dokumentierten Weg; gelingt er, muss
Schritt 2 danach `cmd:` liefern. Tut er das nicht, gilt Schritt 4.

### Ergebnis der Kette

- Erfolg: Eigenschaft `verbose_confirmed = True`, dazu im Log, welcher
  Schritt gegriffen hat
- Misserfolg: Verbindungsaufbau **abbrechen**, kein Upload, Meldung:

  ```
  No PK-232 responding on <port> at <baud>: no banner, no cmd: prompt and
  no Host Mode frame. Check port and baud rate, or power-cycle the TNC —
  it may be stuck (see the troubleshooting note in CLAUDE.md).
  ```

  Die Meldung nennt **beide** Möglichkeiten — falscher Port/Baudrate
  oder hängendes Gerät —, weil sie sich von außen nicht unterscheiden
  lassen. Genau die Triage, die der Operator am 23.09. mit einem
  Terminalprogramm gefahren hat.

`verbose_confirmed` wird bei jedem Verbindungsaufbau zurückgesetzt und
beim Host-Mode-Eintritt gelöscht.

**Commit:** `SerialManager: detect the TNC state before doing anything else`

---

## P43.2 — Uploader prüft den Beleg

`ParamsUploader.upload()`:

- die Prüfung aus P40.2 bleibt (Software glaubt, im Host Mode zu sein →
  verweigern)
- **zusätzlich**: ohne `verbose_confirmed` verweigern:
  „refusing to upload: the verbose prompt was never confirmed in this
  session"
- beides einmal vor dem ersten Befehl

**Commit:** `Params uploader: require a confirmed verbose prompt`

---

## P43.3 — Was beim Beenden zurückbleibt

Prüfen, was `host_mode_on_exit` bewirkt und ob es konfigurierbar ist.

- Bleibt der TNC absichtlich im Host Mode: nichts ändern — Schritt 3 der
  Kette deckt den Normalfall ab. So in
  `SERIAL_CONNECTION_STATE_MACHINE.md` festhalten
- Ist es **nicht** beabsichtigt: den Austritt beim Beenden ergänzen

Nicht raten: Git-Historie und Konfiguration ansehen, Befund in den
Commit-Text. Bei Unklarheit die erste Variante (die Kette trägt beides).

**Commit:** `Connection: define the TNC state left behind on exit`

---

## P43.4 — Tests

Gegen eine Attrappe der seriellen Schnittstelle, je ein Fall pro Zweig:

- `*` → Banner + `cmd:` → Schritt 1, kein `CR`, kein HPOLL gesendet
- `*` → nur Echo, `CR` → `cmd:` → Schritt 2, kein HPOLL gesendet
- `*` und `CR` stumm, HPOLL → `$4F`-Frame → Austritt gefahren, danach
  `cmd:` → Erfolg
- alle drei stumm → Abbruch, **kein Byte** an den Uploader, Meldung
  enthält Port und Baudrate
- HPOLL antwortet, aber der Austritt scheitert → Abbruch wie oben
- `verbose_confirmed` nicht gesetzt → Upload verweigert, auch wenn
  `is_host_mode` False meldet

**Commit:** `Tests: TNC state detection branches`

---

## P43.5 — Dokumentation

- `CLAUDE.md`, Fallstricke:
  - **`is_host_mode` ist die Überzeugung der Software, nicht der Zustand
    des Geräts.** Vor jedem verbose-Befehl gilt: Prompt belegen, nicht
    annehmen (Regel aus P34, jetzt auch in der Anwendung)
  - **Im Host Mode antwortet der TNC nicht auf `*`.** Er sendet von sich
    aus nichts, solange `HPOLL` ON ist; erkennen lässt er sich nur durch
    eine HPOLL-Abfrage in Framesprache
  - Befund des Operators: frisch eingeschaltet schnell, im Host Mode 68
    Zeitgrenzen
- `SERIAL_CONNECTION_STATE_MACHINE.md`, §1: die vier Schritte als
  Tabelle, mit den Zeitgrenzen
- `Backlog.md`: P29 (CR-Rückfall im Wakeup) **schließen** — Schritt 2 der
  Kette deckt ihn ab
- `Testplan.md`: Fall — Anwendung beenden, sofort neu starten und
  verbinden, ohne den TNC aus- und einzuschalten; erwartet wird ein
  Aufbau unter einer Minute mit „parameter upload verified (3/3)" und
  ohne „no cmd:"-Warnung

**Commit:** `Docs: four-step TNC state detection`

---

## Definition of Done

- `.venv\Scripts\python.exe -m pytest` grün
- Der Test „alle drei stumm" belegt, dass **kein** Parameter gesendet wird
- Die Erkennungskette braucht im schlechtesten Fall unter 5 Sekunden
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"
- Danach vom Operator: Anwendung beenden, sofort neu verbinden — ohne den
  TNC aus- und einzuschalten