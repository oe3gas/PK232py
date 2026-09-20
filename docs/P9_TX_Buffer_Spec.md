# P9 — TX-Puffer je Kanal (Pflicht)

**Anforderung.** Text, der auf einem Kanal getippt wurde, bleibt auf diesem
Kanal — auch ungesendet, auch über beliebig viele Kanalwechsel hinweg. Ein
Kanalwechsel darf niemals dazu führen, dass Text auf dem falschen Kanal
landet oder verlorengeht.

Gilt für jeden Weg, auf dem der Kanal wechselt: Chip-Klick, Ctrl+Up/Down,
Doppelklick in der MHEARD-Liste, `PacketConnectDialog` (Kanalauswahl),
programmatisches `channel_bar.set_current()`.

---

## P9.1 Speicher im Screen — `src/pk232py/ui/screens/packet_screen.py`

```python
self._tx_buffers: dict[int, tuple[str, int]] = {}   # ch -> (text, cursor_pos)
self._tx_channel: int = <Startkanal>                # Kanal, dessen Text gerade
                                                    # im tx_input liegt
```

`_tx_channel` ist **nicht** dasselbe wie `channel_bar.current()`: er hält
fest, zu welchem Kanal der momentan im Widget sichtbare Text gehört. Nur so
lässt sich beim Wechsel der alte Text der *richtigen* Kanalnummer zuordnen —
das Signal `channel_changed(int)` liefert nur den neuen Kanal.

## P9.2 Umschalten

```python
def _on_tx_channel_switch(self, new_ch: int) -> None:
    """Text des bisherigen Kanals sichern, Text des neuen Kanals laden."""
```

Ablauf:

1. aktuellen Stand unter `self._tx_channel` ablegen — Text **und**
   Cursorposition
2. `self._tx_channel = new_ch`
3. gespeicherten Text des neuen Kanals setzen (leerer String, wenn noch
   keiner existiert), Cursor an die gespeicherte Position, sonst ans Ende
4. Schritt 3 in `blockSignals(True/False)` klammern, damit kein `textChanged`
   / `char_typed` feuert und eine Sendelogik triggert

**Verbindung im Screen selbst herstellen**, im Konstruktor, direkt nach dem
Bau der `ChannelBar` — nicht über `main_window`. Qt ruft Slots in der
Reihenfolge ihrer Verbindung auf; der Screen verbindet in `__init__`,
MainWindow erst in `_wire_packet_buttons()`. Damit ist garantiert, dass der
Puffertausch abgeschlossen ist, bevor MainWindow-Slots auf `tx_input`
zugreifen. Diese Reihenfolgeabhängigkeit als Kommentar im Code festhalten.

## P9.3 Schreibende Zugriffe kanalisieren

Neue öffentliche Methoden, damit niemand mehr direkt `tx_input.clear()` ruft:

```python
def tx_text(self) -> str:
    """Aktuell sichtbarer TX-Text."""

def clear_tx(self, channel: int | None = None) -> None:
    """Widget leeren UND den Puffereintrag dieses Kanals löschen.
    channel=None → der aktuell sichtbare Kanal."""
```

Anzupassen:

- `Clear TX`-Button → `clear_tx()` (nur der aktuelle Kanal, nie alle)
- `reset_channels()` (P8.1) → alle Puffer verwerfen
- `main_window._on_packet_tx_enter()` → am Ende `screen.clear_tx(channel)`
  statt `screen.tx_input.clear()`, mit genau der Kanalnummer, auf der
  tatsächlich gesendet wurde

## P9.4 Sendepfad absichern — `src/pk232py/ui/main_window.py`

In `_on_packet_tx_enter()` die Kanalnummer **einmal** zu Beginn bestimmen und
danach ausschließlich diese Variable verwenden — für `send_data()`, für den
Capture-Eintrag, für das RX-Echo und für `clear_tx()`. Kein zweiter Aufruf
von `current_channel()` im selben Handler: sonst kann ein Kanalwechsel
zwischen zwei Aufrufen den Text eines Kanals löschen, auf dem nie gesendet
wurde.

---

## Commits

```
Packet screen: per-channel TX buffers
MainWindow: send and clear TX on one fixed channel
```

Eine Datei pro Commit, Commit-Messages ASCII-only.

---

## Testfälle für `Testplan.md`

Nummerierung an den vorhandenen Stand anschließen; T87–T93 nicht
überschreiben.

### T94 — TX-Puffer je Kanal

1. Kanal 1 wählen, `test eins` tippen, **nicht** senden
2. Kanal 3 wählen → TX-Fenster ist leer
3. `test drei` tippen, **nicht** senden
4. Zurück auf Kanal 1 → `test eins` steht wieder da, Cursor am Ende
5. Zurück auf Kanal 3 → `test drei` steht da
6. Auf Kanal 3 senden → nur Kanal 3 ist leer, Kanal 1 hält `test eins`

**Erwartung:** kein Textverlust, kein Text auf dem falschen Kanal.

### T95 — MHEARD-Doppelklick wechselt Kanal ohne Textverlust

1. Auf Kanal 1 Text tippen, nicht senden
2. In der MHEARD-Liste eine auf Kanal 4 verbundene Station doppelklicken
3. **Erwartung:** Wechsel auf Kanal 4, TX-Fenster zeigt Kanal 4s Text
   (oder leer), Kanal 1 behält seinen Text

### T96 — `reset_channels()` beim Moduswechsel

1. Verbindung auf Kanal 2 aufbauen, auf Kanal 5 Text tippen
2. Betriebsart auf Baudot wechseln, zurück auf HF Packet
3. **Erwartung:** alle Chips `free`, keine Partner-Rufzeichen, TX-Puffer leer

### T97 — `CONNECTED to:` mit Doppelpunkt

Gegen `tools/mock_tnc_bbs.py` mit beiden Meldungsformen prüfen; der Chip
zeigt in beiden Fällen das Rufzeichen, nie `":"`.

---

## Definition of Done

- `python -m pytest` grün, neue Tests eingeschlossen
- Kanalwechsel mit ungesendetem Text in mindestens zwei Kanälen manuell
  durchgespielt (T94)
- `.\Sources2Text.ps1` ausgeführt, danach Meldung "sources aktualisiert"