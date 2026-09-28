# Claude Code Prompt — P66a: CHSWITCH-Wert richtig umsetzen; Transparent-Escape als Backlog

> Ablage: `docs/P66a_CHSWITCH_Value_Fix_Spec.md` im Repo.
> Eine Datei pro Commit, Commit-Messages ASCII-only.
> Grundlage: Review von P66, `main` @ `2767c51`.
> **Vor** den Hardware-Läufen T141/T142/T143 umsetzen — sonst ist D.2.3
> ungültig.

---

## Befund

### B.1 D.2.3 sendet den Text `$7C` statt des Zeichens `|`

`tools/hw_check.py` (`link_carry_host`, D.2.3):

```python
chswitch_char = parse_query_value("CHSWITCH", chswitch_raw)
...
chswitch_char.encode("ascii", errors="replace") + b"1" + b"CONVERSE\r\n\r"
```

`parse_query_value()` liefert den Wert **so, wie der TNC ihn anzeigt** —
geprüft:

```
parse_query_value('CHSWITCH', 'CHSWITCH\r\nCHswitch  $7C\r\ncmd:') -> '$7C'
parse_query_value('CHSWITCH', 'CHSWITCH\r\nCHswitch  $00\r\ncmd:') -> '$00'
```

Gesendet würden also die drei Zeichen `$`, `7`, `C`, dann `1CONVERSE` —
ein ungültiger Befehl, kein Kanalwechsel. D.2.3 würde „kein BBS-Prompt"
messen, obwohl nur das Werkzeug falsch war.

Zusätzlich: Ist der Wert `$00`, ist das Kanalumschaltzeichen **nicht
gesetzt** — dann gibt es im verbose Modus keinen Kanalwechsel per Zeichen,
und D.2.3 darf nichts senden. PK232PY führt `CHSWITCH` weder in der
Konfiguration noch im Parameter-Upload (`git grep -i chswitch --
src/pk232py/config.py src/pk232py/comm/params_uploader.py` → leer); es gilt
also, was der TNC gerade hat.

### B.2 `escape_converse()` kann Transparent nicht verlassen

`comm/pk232_hostmode_sub.py::escape_converse()` sendet je Versuch
`command_char + b"\r"` und wartet dann bis zu 2 s. Für Converse ist das
richtig (ein Zeichen genügt). Für Transparent verlangt der TNC **drei
COMMAND-Zeichen innerhalb von CMDTIME, ohne andere Zeichen dazwischen** —
das `\r` nach jedem Zeichen und die 2-s-Pausen verhindern genau das. Der
Docstring behauptet dennoch „or Transparent (needs three)".

PK232PY schaltet heute nirgends in Transparent; für Packet ist das
**kein** akuter Fehler. Nicht jetzt umbauen (P66 ist in Converse
nachgewiesen richtig) — aber die Behauptung darf nicht stehen bleiben.

---

## Teil A — CHSWITCH-Wert umsetzen (hw_check)

Neue reine Funktion in `tools/hw_check.py`:

```python
def chswitch_byte(value: str) -> Optional[bytes]:
    """'$7C' -> b'|'; '$00' -> None (no channel-switch character set);
    anything else -> None (unparsed, never guessed)."""
```

D.2.3 verwendet sie. Bei `None`: `SKIPPED` mit Grund
`CHSWITCH is $00 (not set)` bzw. `unparsed value`, nichts senden.

Tests (zuerst rot): `$7C` → `b'|'`, `$00` → `None`, `7C` / `` / `$ZZ` →
`None`; D.2.3 im Dry-Run mit `$7C` zeigt `7C 31 43 4F 4E …` (also `|1CONVERSE`)
in der Vorschau.

**Commit:** `hw_check: CHSWITCH query value is a hex byte, not text`

---

## Teil B — Transparent-Behauptung korrigieren

- `escape_converse()`-Docstring: „or Transparent (needs three)" ersetzen
  durch *„Converse only. Transparent needs three COMMAND characters within
  CMDTIME with no other bytes in between - this function sends a CR after
  each one and waits between attempts, so it cannot leave Transparent.
  See Backlog."*
- `Backlog.md`, neu: „`escape_converse()` verlässt Transparent nicht (P66a
  B.2). Relevant, sobald ein Modus Transparent nutzt oder die Erkennungskette
  Transparent zuverlässig erkennen soll. Vorher messen: Zeitverhalten von
  drei COMMAND-Zeichen, Guard-Zeiten, CMDTIME-Wert je Gerät."

**Commits:**
```
Host Mode entry: escape_converse docstring - Converse only
Backlog: Transparent escape (P66a)
Docs: add P66a spec file
```

---

## Definition of Done

- neue Tests zuerst rot, volle Suite grün
- `--dry-run link_carry_host` zeigt in D.2.3 das umgesetzte Zeichen
- **Push**, Meldung mit Hash; `.\Sources2Text.ps1`, „sources aktualisiert"