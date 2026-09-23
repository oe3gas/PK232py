# Claude Code Prompt — P34: Kein Befehl ohne bestätigten Prompt

> Ablage: `docs/P34_Normalize_Verify_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Vorher `CLAUDE.md`, `SERIAL_CONNECTION_STATE_MACHINE.md`, `Backlog.md` lesen.
> Fixture: `hw_logs/20260923_203256_mdcheck_scan.log`.

---

## Befund (23.09.2026, 20:32, Gerät B)

### Ergebnis des Scans
Auch auf der MBX-Firmware (01.08.1991) **kein Treffer** unter den 23
`M?`-Kandidaten. Die Host-Mode-Abfragen selbst liefen normal
(`MAnone`, `MC0`, `MX4`, …), der Scan ist also gültig. Damit ist für
Gerät A **und** B belegt: MDCHECK ist im Host Mode nicht über ein Kürzel
erreichbar.

### Fehlverhalten des Werkzeugs
Die verbose-Phase vor dem Scan lief vollständig ins Leere:

```
>> PACKET\r\n     << 'PACKET\r\n'        (nur Echo, kein Opmode, kein cmd:)
>> MYCALL\r\n     << 'MYCALL\r\n'        MYCALL: None
>> XMITOK\r\n     << 'XMITOK\r\n'        XMITOK: None
```

`normalize()` hat den fehlenden Prompt **nicht als Fehler behandelt** und
weitergemacht: `MDCHECK`, `S OE3GAS`, Betreff, Text, `/EX`, `B` —
allesamt an einen TNC, der nicht im Befehlsmodus war. Anschließend
protokollierte das Werkzeug „Test message stored as # None".

Nach dem Host-Mode-Ein- und -Austritt war der TNC wieder normal
ansprechbar; der Eintritt hat den Zustand bereinigt.

**Sicherheitsrelevant:** Der wahrscheinlichste Ausgangszustand ist
Converse — dort wird getippter Text echot und in den Sendepuffer gelegt.
`XMITOK` war unbekannt, weil die Abfrage selbst nicht ausgeführt wurde;
stand es wie in allen bisherigen Läufen auf `ON`, sind die Befehlszeilen
als UI-Frames ausgesendet worden. Das Werkzeug verspricht in jeder Zeile
„never transmits on the air" — diese Zusage darf nicht davon abhängen,
dass der TNC zufällig im richtigen Zustand steht.

---

## P34.1 — `Session.normalize()`: prüfen statt hoffen

`normalize()` bekommt eine harte Abbruchbedingung und einen Resync.

1. `Ctrl-C` + `CR` senden, Antwort lesen. **Erwartet wird `cmd:`.**
2. Kein `cmd:` → Resync-Stufe 1: `CR` allein, erneut prüfen.
3. Immer noch kein `cmd:` → Resync-Stufe 2: die dokumentierte
   Host-Mode-Rückholung verwenden (`SOH SOH $4F G G ETB`, danach
   `SOH $4F H O N ETB`, siehe `SERIAL_CONNECTION_STATE_MACHINE.md`,
   Abschnitt „Recovery"), danach `Ctrl-C` + `CR` und erneut prüfen.
   Vorhandene Funktionen verwenden, nichts nachbauen.
4. Immer noch kein `cmd:` → **Abbruch des gesamten Subcommands** mit
   `FAIL` und dem Text:
   „TNC is not at the command prompt (echo only). Nothing was sent.
   Check with a terminal program; power-cycle the TNC if it stays
   unresponsive."
5. Erst nach bestätigtem Prompt die übrigen Schritte (`PACKET`, `MYCALL`,
   `XMITOK` …).

**Grundregel, die für jedes Subcommand gilt und im Code als Kommentar
stehen soll:** *Kein verbose-Befehl wird gesendet, solange der
`cmd:`-Prompt nicht in derselben Sitzung bestätigt wurde.*

**Commit:** `Tools: normalize verifies the command prompt and aborts otherwise`

---

## P34.2 — Abfragen, die `None` liefern, sind Fehler

Überall im Werkzeug gilt bisher: `parse_query_value()` liefert `None`, es
wird protokolliert und weitergemacht. Das ist für einen einzelnen
Parameter vertretbar, für die **Zustandsabfragen** der Normalisierung
nicht.

- `MYCALL` und `XMITOK` in `normalize()`: `None` → Abbruch wie in P34.1,
  Schritt 4. Kein Weiterlaufen
- die übrigen Abfragen (Parameterlisten in `maildrop`,
  `maildrop_host`) dürfen weiterhin `None` liefern, protokollieren das
  aber deutlicher: `WARNING: <CMD> unanswered`
- `XMITOK` unbekannt bedeutet ausdrücklich: **die Zusage „keine
  Aussendung" kann nicht gehalten werden** — das gehört in die Meldung

**Commit:** `Tools: unanswered state queries abort the run`

---

## P34.3 — Kein Schreiben ohne bestätigten Zustand

Der Testnachrichten-Schritt (`maildrop_host`, `mdcheck_scan`) schreibt in
die Mailbox. Er darf nur laufen, wenn

- der `cmd:`-Prompt bestätigt ist **und**
- `MDCHECK` mit einem erkannten Mailbox-Prompt geantwortet hat
  (`find_prompt()` aus `protocol.py` verwenden — beide Klammerformen)

Andernfalls: Schritt überspringen, `INFO` ins Protokoll, Scan trotzdem
fahren (er braucht die Nachricht nicht zwingend). „Test message stored as
# None" darf es nicht mehr geben — entweder eine Nummer oder ein
ausdrückliches „skipped".

**Commit:** `Tools: test message only after a confirmed mailbox prompt`

---

## P34.4 — Tests

Gegen die Attrappe, mit den echten Byte-Folgen aus dem Mitschnitt:

- Echo ohne `cmd:` → `normalize()` bricht ab, **nichts weiter gesendet**
  (der Test prüft, dass nach dem Abbruch keine Bytes mehr an die
  Schnittstelle gehen — dieselbe Bauart wie der Sicherheitstest aus P21.4)
- `cmd:` erst nach Resync-Stufe 1 → Lauf geht weiter
- `cmd:` erst nach Stufe 2 → Lauf geht weiter, Resync protokolliert
- `MYCALL` unbeantwortet → Abbruch
- Testnachricht ohne Mailbox-Prompt → übersprungen, nicht „# None"

**Commit:** `Tests: prompt verification and abort paths`

---

## P34.5 — Dokumentation

### `CLAUDE.md`
- neuer Fallstrick: **Echo ohne Ausführung** — der TNC kann in einem
  Zustand stehen (vermutlich Converse), in dem er jede Zeile echot und
  nichts ausführt. Erkennungsmerkmal: keine `cmd:`-Antwort. Gefahr: mit
  `XMITOK ON` geht der getippte Text als UI-Frame auf die Luft.
  Beobachtet am 23.09.2026; der Host-Mode-Ein- und -Austritt hat den
  Zustand bereinigt
- Werkzeugregel aufnehmen: kein verbose-Befehl ohne in derselben Sitzung
  bestätigten `cmd:`-Prompt

### `Testplan.md`
- `mdcheck_scan` auf Gerät B: **kein Treffer**, 23.09.2026 — zusammen mit
  Gerät A gilt der Befund für zwei Firmwaregenerationen
- Vermerk, dass die verbose-Phase dieses Laufs ungültig war und die
  Testnachricht nie entstand

### `docs/PK232_firmware_matrix.md`
- gemessener Eintrag: MDCHECK ohne Host-Mode-Kürzel auf MBX (1991) **und**
  PACTOR (1995)

### `Backlog.md`
- offen: in welchem Zustand stand der TNC zu Beginn des Laufs? Falls es
  reproduzierbar auftritt, gezielt messen (Converse? Transparent?)

**Commit:** `Docs: echo-without-execution state, mdcheck_scan on device B`

---

## Definition of Done

- `.venv\Scripts\python.exe -m pytest` grün
- Der Abbruchtest ist ohne den Fix rot — gegengeprüft
- `.\Sources2Text.ps1`, danach Meldung "sources aktualisiert"