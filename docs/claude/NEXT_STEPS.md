# PK232PY - Open Questions / Next Steps

> Priorisierte offene Arbeit.
> Ausgelagert aus CLAUDE.md (unveraendert uebernommen, Stand 2026-09-29).

## Open Questions / Next Steps

### Immediate (next session)

1. **Packet Connect/Disconnect** — CO/DI frames + CONNECTED pill software-verified
   via mock (T33–T39); hardware re-test needs a second AX.25 station on
   144.800 MHz. T38/T39 also need an interactive mock GUI re-click.
2. **Packet MHEARD** — parse MH frame into MheardPanel (T41–T42)
3. ~~**Packet toggle/button tests** (T43–T51)~~ — **done 2026-06-22**
   (frame/code-verified; PASSALL `PA`→`PS` bugfix). See Backlog.md.

### Medium term

4. **CTRL+D EOT — Paket 2b (AMTOR):** ARQ → `OV`, FEC → `RC`; add AMTOR to
   `_is_txctrl_mode()`. CW/Morse (Paket 2a) is done — hardware test pending.
5. ~~**Stop Sending — Paket 3**~~ ✅ DONE 2026-06-22 (software/mock). No new
   button needed: RECEIVE (RTTY/Morse → `RC`) + Clear TX (all; AMTOR → `AM`)
   cover it; Packet/PACTOR send none. See §11 + the `_send_active` Gotcha.
6. **Theme persistence** — `[UI]` section in INI, `Configure → Appearance` dialog
7. ~~**Tooltip system** — central `tooltips.py`~~ ✅ DONE 2026-06-22. Global
   `TOOLTIPS` + per-class `SCREEN_TOOLTIPS` overrides; wired into all 10 screens.
   See the tooltip Gotcha under Known Gotchas. Follow-up: T86 PASSALL `PS`/`PX`
   hardware verification.
8. ~~**Help system** — split `help_baudot.md` into topic files, add Help buttons~~
   ✅ DONE 2026-06-22. `help_viewer.py` `HELP_TOPICS` covers all 10 modes +
   common topics (default `index`, internal topic-link navigation); 10 reviewed
   help files (`vhf` → `help_packet.md`, shared); `make_help_button()` (`?`) on
   all 10 screens; Help menu (Contents = F1, About). See the HelpViewer Gotcha.
   Follow-up: `help_amtor.md` proof-read; `help_shortcuts.md` / `help_controls.md`
   as own files (v0.2).

### Before beta

9. **APRS Phase 2** — beacon TX, beacon config UI, MHEARD APRS stations
10. **PACTOR/AMTOR identity** — wire parameter dialogs to TNC commands (T52–T58)
11. **Parameter integration** — load/save screen parameters from AppConfig on mode switch

---
