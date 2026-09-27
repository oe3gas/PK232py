# Claude Code Prompt — P62: APRS-Messpaket für `tools/hw_check.py`

> Ablage: `docs/P62_APRS_Measure_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Grundlage: `main` @ `be77d15`.
> **Dieses Paket MISST nur** (hw_check-Regel 6). Die Umsetzung des
> APRS-Modus folgt als P63 und stützt sich ausschließlich auf die hier
> gemessenen Befunde.

---

## Zweck und Designrahmen

APRS-Senden kommt als **eigener Modus** neben HF Packet, VHF Packet und
MailDrop — ein Modus, ein Screen, HF und VHF per Umschalter im Screen.
Entscheidungen des Betreibers (27.09.2026), hier festgehalten, damit P63
darauf aufbauen kann:

- Normales Packet: UI-Frames sind herkömmliches Unproto; die vorhandene
  APRS-Ansicht **übersetzt nur** (empfangsseitig), sendet nie APRS.
- APRS-Modus: sendet und empfängt APRS, **keine** Connects.
- UNPROTO gehört genau einem Modus; der APRS-Modus setzt ihn beim
  Aktivieren, die Packet-Modi setzen ihren eigenen wieder.
- Baken-Timer in der App (`QTimer`), **nicht** TNC-`BEACON`/`BTEXT` — endet
  sicher mit dem Modus, keine Längenbegrenzung durch BTEXT.
- Eigene Aussendungen protokolliert die App selbst — T101 (Gerät A): kein
  `$3F`-Echo eigener UI-Frames, auch nicht bei `MONITOR 6`.

Was P63 dafür wissen muss und **nicht** weiß, misst dieses Paket.

---

## Befund — was bekannt ist, was nicht

| Frage | Stand | Beleg |
|---|---|---|
| Text auf Kanal 0 geht als UI-Frame entlang UNPROTO raus | ✅ Gerät A | T101, 21.09.2026 |
| Ziel ohne VIA wird übernommen (`TEST1`, `TEST2`) | ✅ Gerät A | T101 |
| dasselbe auf Gerät B / C | ❓ | nie gemessen |
| UNPROTO **mit** VIA-Pfad (`WIDE1-1,WIDE2-1`) angenommen und korrekt gesendet | ❓ | T101 verwendete nie VIA |
| UNPROTO im **Host Mode** gesetzt (`UN`) — P63 schaltet im Host Mode um | ❓ | T101 setzte UNPROTO verbose; `hostmode.cmd_unproto()` existiert, wird aber nirgends aufgerufen; `UN` in der Firmware-Matrix nur Hypothese |
| Info-Feld kommt **byte-genau** an (APRS-Sonderzeichen `! = / \ { } \| ~ : > @ _`) | ❓ | T101 sendete nur Buchstaben, Ziffern, Doppelpunkt |
| hängt der TNC ein CR an das Info-Feld an? | ❓ | für APRS-Parser relevant |
| wird ein Info-Feld > PACLEN auf **mehrere** UI-Frames aufgeteilt? | ❓ | APRS braucht **ein** Frame je Meldung |
| wie lassen sich eingehende Connects abweisen? | ❓ | siehe unten |

### Korrektur zur Chat-Vorarbeit
In der Vorbesprechung wurden `MXMIT` (Echo eigener Frames) und `CONOK`
(Connects annehmen) als Kandidaten genannt. **Beide gibt es im
PK-232-Befehlssatz nicht** — sie fehlen im vollständigen STABO-Superset
(194 Befehle, `docs/PK232_firmware_matrix.md` §4). Nicht messen, nicht
verwenden. Der Kommentar zu `CONOK` in `modes/packet_hf.py:361` ist
entsprechend irreführend → Backlog-Eintrag (Teil F).

### Kandidat zum Abweisen von Connects: `CFROM NONE`
STABO: `CFrom all | none | yes/no call1…`, Host `CF` — *„none: Keine Station
darf Sie connecten."* `CFROM` ist in PK232PY bereits ein HF-Packet-Parameter
(`HFPacketConfig.cfrom_mode`, `ParamsUploader._access_filter_cmds`).
Unbekannt ist, **was die rufende Station erlebt** (Busy? gar nichts, bis
„Retry count exceeded"?) und **was der eigene TNC meldet** (Link-Meldung
„Connect request"? nichts?). Beides entscheidet, wie der APRS-Screen damit
umgeht.

---

## Teil A — `hw_check.py aprs_query` (kein Senden)

Neuer Unterbefehl. Nur Abfragen und Setzen mit Wiederherstellung, **kein
Aussenden**. Läuft allein, ohne zweite Station.

Alle geänderten Parameter vorher abfragen und in `run_with_restore()`
wiederherstellen (Regel 2): `UNPROTO`, `CFROM`.

Schritte, je mit Logzeile und Einzelergebnis:

1. **Ausgangslage verbose abfragen:** `UNPROTO`, `CFROM`, `PACLEN`, `VHF`,
   `HBAUD`, `MONITOR`. Nur loggen.
2. **A.2 VIA verbose:** `UNPROTO APZ232 VIA WIDE1-1,WIDE2-1` →
   Antwort loggen (Fehlermeldung wie `?VIA` / `?bad`?) → `UNPROTO` abfragen,
   Rückgabe **wörtlich** loggen.
   Ergebnis: `PASS` wenn die Abfrage Ziel und beide Digis enthält.
3. **A.3 `UN` im Host Mode setzen:** zuerst verbose auf `CQ` setzen, dann
   Host Mode, Frame `UN APZ232 VIA WIDE1-1,WIDE2-1` über
   `HostMode.cmd_unproto()` (bestehender Frame-Bauer — keine zweite
   Implementierung), **alle** Antwortframes 2 s lang unverändert loggen,
   Host Mode verlassen, verbose abfragen.
   Ergebnis: `PASS` wenn die verbose Abfrage den im Host Mode gesetzten
   Pfad zeigt; die Antwort-CTL/Daten gehören ins Ergebnisdetail.
4. **A.4 `UN` im Host Mode abfragen:** `session.query_host(b"UN")` — liefert
   der TNC den Pfad zurück? Wörtlich loggen. (Für P63: kann die App den
   gesetzten Pfad per Host-Abfrage prüfen?)
5. **A.5 `CF` im Host Mode:** wie A.3 mit `CFROM`: Host-Frame `CF NONE`
   → verbose Abfrage → erwartet `NONE`; danach Host-Frame `CF ALL` →
   verbose → `ALL`. `ParamsUploader._access_filter_cmds()` baut nur
   **verbose** Befehle (`CFROM NONE\r\n`), keinen Host-Frame. Den Host-Frame
   deshalb mit demselben generischen `build_command()` aus
   `comm/hostmode.py` erzeugen, auf dem `cmd_unproto()` aufsetzt:
   `build_command(b"CF", b"NONE")`. **Keinen** weiteren Bauer anlegen
   (es gibt bereits zwei `build_command()`, in `hostmode.py` und
   `frame.py` — Doppelung nicht vergrößern, siehe Teil F).
6. **A.6 Längenprobe `UNPROTO`:** 8 Digis
   (`APZ232 VIA D1,D2,D3,D4,D5,D6,D7,D8`) verbose setzen und abfragen;
   danach 9 Digis. Laut STABO sind bis zu 8 Digis erlaubt. Ergebnis
   wörtlich — keine Bewertung nötig, nur Befund.

`--dry-run aprs_query` gibt alle Befehle/Frames aus, ohne Port.

**Commit:** `hw_check: aprs_query - UNPROTO/CFROM verbose and Host Mode, no TX`

---

## Teil B — `hw_check.py aprs_tx` (SENDET)

Wie `t101`: Hinweis, `confirm_tx()` vor **jeder** Runde, zweite Station mit
AX.25-Decoder (Direwolf) nötig.

### Sicherheitshinweis im Programmtext (vor dem ersten `y/N`)
> Do NOT run this on 144.800 MHz or any APRS frequency. Test frames with
> WIDEn-N paths are repeated by digipeaters and gated to APRS-IS. Use a
> simplex frequency with no APRS infrastructure, low power or a dummy load.

Info-Felder sind **Status-** oder Testtexte, keine Positionen — damit
entsteht auch bei versehentlichem Gating kein Phantom-Standort.

### Runden
UNPROTO jeweils **im Host Mode** über `UN` setzen (so wird P63 es tun),
dann Daten auf Kanal 0 über `send_data_channel0()`.

| Runde | UNPROTO | Info-Feld | Zweck |
|---|---|---|---|
| R1 | `APZ232` | `>PK232PY P62 R1 HH:MM:SS` | Grundfall wie T101, jetzt je Gerät |
| R2 | `APZ232 VIA WIDE1-1,WIDE2-1` | `>PK232PY P62 R2 HH:MM:SS` | VIA-Pfad kommt an, H-Bits ungesetzt |
| R3 | `APZ232` | Zeichenprobe (s. u.) | byte-genaue Übertragung, CR? |
| R4 | `APZ232` | 200 Zeichen (s. u.) | Aufteilung bei > PACLEN? |
| R5 | `APZ232`, **`CFROM NONE`** aktiv | `>PK232PY P62 R5 HH:MM:SS` | Senden unbeeinflusst von CFROM |

**Zeichenprobe R3** (exakt, 1 Frame):
```
>P62 R3 !"#$%&'()*+,-./:;<=>?@[\]^_`{|}~ END
```

**R4:** `>P62 R4 ` + Ziffernfolge `0123456789` wiederholt bis Gesamtlänge
**200** + ` END`. Vorher `PACLEN` loggen.

### Was der Betreiber je Runde beantwortet
Das Programm fragt nacheinander und loggt die Antworten wörtlich:

1. Decoder zeigt einen Frame? `[y/n]`
2. **Die Decoder-Zeile bitte vollständig einfügen** (Direwolf zeigt
   nicht druckbare Bytes als `<0x0d>` o. Ä. — genau das wollen wir sehen).
   Mehrzeilig, Ende mit Leerzeile.
3. Wie viele Frames hat der Decoder für diese Runde gezeigt? `[Zahl]`

Das Programm vergleicht die eingefügte Zeile mit dem gesendeten Info-Feld
und setzt je Runde: `PASS` (Info-Feld exakt enthalten, 1 Frame, bei R2 beide
Digis im Pfad), `FAIL` (mit Grund) oder `INFO` (übersprungen). Eine
**reine Funktion** `evaluate_aprs_round(sent_info, sent_path, pasted, frames)`
macht den Vergleich — testbar ohne Hardware (Teil D). Sie meldet getrennt:
`info_exact`, `trailing_cr`, `path_ok`, `frames`.

Außerdem wie T101: alle Host-Frames 2 s nach jedem Senden unverändert
loggen (Datenquittung `$5F`, eventuelle Fehler).

**Commit:** `hw_check: aprs_tx - five UI rounds incl. VIA path, charset, length, CFROM`

---

## Teil C — `hw_check.py aprs_reject` (zweite Station ruft an)

Der eigene TNC sendet hier nur, was die Firmware selbst auf einen
Connect-Versuch antwortet. Die rufende Station ist eine **zweite Station
nach Wahl des Betreibers** (zweiter PK-232 mit Terminalprogramm, oder
Direwolf mit einem Connected-Mode-Client). Das Programm fragt vorab, **welche
Gegenstation und welches Gerät (A/B/C) sie ist**, und loggt es.

1. **C.1 Basislinie `CFROM ALL`:** Host Mode, alle Frames 60 s lang
   aufzeichnen. Betreiber lässt die Gegenstation `MYCALL` connecten und
   sofort wieder trennen. Erwartung (bekannt): `CONNECTED`-Link-Meldung,
   danach `DISCONNECTED`. Dient nur als Vergleich im selben Lauf.
2. **C.2 `CFROM NONE`:** per `CF`-Host-Frame setzen, dann 90 s aufzeichnen,
   Gegenstation ruft erneut an.
3. Nach jeder Phase fragt das Programm den Betreiber:
   - Was zeigte die **rufende** Station? Zeile einfügen
     (`*** busy`, `Retry count exceeded`, nichts …).
   - Leuchtete am eigenen TNC die **PTT/SEND-LED**? `[y/n]` — antwortet der
     TNC überhaupt auf den Anruf?
4. Das Programm loggt je Phase alle `$5x`-Link-Meldungen mit Kanal und
   Text, alle `$3F`-Frames und alle übrigen Frames, wörtlich.
5. `CFROM` wird in `run_with_restore()` wiederhergestellt.

Ergebnis: `INFO` mit einer Zusammenfassung je Phase (Link-Meldungen,
Betreiberangaben). Hier gibt es kein PASS/FAIL — gesucht ist das
Verhalten.

**Commit:** `hw_check: aprs_reject - incoming connect with CFROM ALL vs NONE`

---

## Teil D — Tests (headless, zuerst rot)

`src/pk232py/tests/test_hw_check_aprs.py` (neu), nach dem Muster der
vorhandenen `evaluate_t101`-Tests:

- `evaluate_aprs_round`: exakte Übereinstimmung; fehlendes Zeichen aus der
  Probe → `info_exact False`; eingefügte Zeile mit `<0x0d>` am Ende →
  `trailing_cr True`; zwei Frames → nicht PASS; R2 ohne `WIDE2-1` in der
  Zeile → `path_ok False`; leere Eingabe → `INFO`.
- Zeichenprobe R3 enthält **jedes** druckbare ASCII-Zeichen 0x21–0x7E
  (Test über `set(range(0x21, 0x7F))`), damit sie nicht versehentlich
  gekürzt wird.
- R4 ist genau 200 Zeichen lang.
- `--dry-run` für `aprs_query`, `aprs_tx`, `aprs_reject`: öffnet keinen
  Port, sendet nichts, gibt die geplanten Befehle aus (Muster der
  bestehenden Dry-Run-Tests).
- Der `UN`-Frame in A.3/B stammt aus `HostMode.cmd_unproto()` —
  Test vergleicht die Bytes mit diesem Bauer, nicht mit einer Kopie.

**Commit:** `Tests: hw_check APRS evaluation and dry-run`

---

## Teil E — Durchführung (Betreiber)

Reihenfolge je Gerät: `aprs_query` → `aprs_tx` → `aprs_reject`.

| Gerät | Pflicht | Hinweis |
|---|---|---|
| **B** | ja | aktuelles Arbeitsgerät |
| **A** | ja | T101-Befunde gelten bisher nur hier; R1 wiederholt sie |
| **C** | optional | erster `hw_check`-Kontakt überhaupt — erst `aprs_query` allein |

Neue Testfälle in `Testplan.md` (Status OPEN, je Gerät eine Ergebniszeile):
- **T138** — `aprs_query`: UNPROTO mit VIA und über `UN`/`CF` im Host Mode
- **T139** — `aprs_tx`: fünf Runden, Decoder-Zeilen im Ergebnis
- **T140** — `aprs_reject`: Verhalten bei `CFROM NONE` aus beiden Richtungen

**Commit:** `Testplan: T138 T139 T140 APRS measurement`

---

## Teil F — Dokumentation

- `tools/README.md` und Modul-Docstring von `hw_check.py`: drei neue
  Unterbefehle, `aprs_tx`/`aprs_reject` **nicht** in `all` (senden bzw.
  brauchen eine Gegenstation).
- `Backlog.md`:
  - „APRS-Modus (P63) — wartet auf T138–T140 (Geräte A und B)"
  - „Kommentar zu CONOK in `modes/packet_hf.py:361`: PK-232 hat kein
    CONOK (STABO-Superset); Kommentar korrigieren, sobald T140 zeigt, wann
    ‚Connect request' tatsächlich kommt."
  - Der alte Eintrag „APRS — Phase 2 / Beacon TX" (UNPROTO `APRS VIA …`
    aus dem Packet-Screen) wird durch den APRS-Modus **ersetzt** — als
    überholt markieren, mit Verweis auf P62.
  - „Zwei `build_command()` (`comm/hostmode.py:145`, `comm/frame.py:223`)
    — eine Sache, zwei Stellen. Eigenes Aufräumpaket."
- `docs/DEVICES.md`: Spalte „Letzte Messung" nach den Läufen.

**Commits:**
```
Docs: hw_check APRS subcommands
Backlog: APRS mode supersedes Phase 2 beacon TX
Docs: add P62 spec file
```

---

## Definition of Done

- `pytest` (betroffene Datei während der Arbeit, volle Suite vor dem Push)
  grün; neue Tests vorher rot
- `python tools/hw_check.py --dry-run aprs_query|aprs_tx|aprs_reject`
  läuft ohne Port und zeigt alle geplanten Befehle
- Kein neuer Frame-Bauer: `UN` über `HostMode.cmd_unproto()`, `CF` über
  `build_command()` aus `comm/hostmode.py`
- Jede Aussendung hinter `confirm_tx()`; Frequenzwarnung vor der ersten
- T138–T140 als OPEN im Testplan
- **Push**, Meldung mit Hash; `.\Sources2Text.ps1`, „sources aktualisiert"