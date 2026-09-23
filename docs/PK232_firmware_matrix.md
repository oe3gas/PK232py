# PK-232(MBX) — Befehlssatz nach Firmware-Release

Begleitdokument zu `tools/pk232_fw_scan.py`.
Ziel: Überblick, welche Verbose-Befehle welche Firmware-Generation kennt — und
wie man das am realen Gerät **empirisch** validiert.

> **Verwandtes Dokument:** `docs/DEVICES.md` (P32) ist das Inventar der drei
> vorhandenen EPROMs/Geräte (A/B/C) mit der Spalte, an welchem Gerät ein
> Befund entstand. Diese Datei hier beantwortet eine andere Frage — welcher
> Befehl in welcher Firmware-**Generation** existiert, unabhängig davon,
> welches physische Gerät gerade am Port hängt.

---

## 1. Wie die Firmware ihre Version meldet

Der PK-232 zeigt seinen Firmware-Stand im **Einschalt-Banner** (nach Power-On
bzw. nach `RESTART`, sobald die Autobaud-Routine mit `*` ausgelöst wurde):

```
PK-232M is using default values.
AEA PK-232M Data Controller
Copyright (C) 1986-1990 by
Advanced Electronic Applications, Inc.
Release DD.MM.YY
cmd:
```

Die Zeile **`Release DD.MM.YY`** ist der maßgebliche Versionsstempel. Deine drei
EPROMs (30.12.1988, 01.08.1991, 11.09.1995) sind genau solche Release-Daten.
Es gibt **keinen** eigenen Konsolen-Befehl „Version" — over-the-air kann ein
MailDrop-*User* zwar `VERSION` senden, lokal am Terminal ist der Banner der Weg.

> Wichtig: **`RESTART`** ist nicht-destruktiv (initialisiert frisch, behält das
> bbRAM). **`RESET`** löscht alle Einstellungen, **`REINT`** setzt die meisten
> Parameter auf Default. Das Tool benutzt ausschließlich `RESTART`.

---

## 2. Die drei Generationen (belegte AEA/Timewave-Meilensteine)

| Gen. | Kürzel | Zeit | Prägende Neuerungen | Deine EPROM |
|-----:|--------|------|---------------------|-------------|
| 1 | **BASE**   | 1986–89 | Ur-PK-232: Baudot/ASCII-RTTY, AMTOR/SITOR, CW, AX.25-Packet, HF-FAX; KISS ab ~Juli 1987 | **30.12.1988** |
| 2 | **MBX**    | ~1990–92 | „PakMail"-Mailbox-Tochterplatine (1989), Ende 1989 integriert → **PK-232MBX**; MailDrop-Befehle, NAVTEX, SIAM/TDM | **01.08.1991** |
| 3 | **PACTOR** | ab 1993 | **PACTOR I** + **Gateway** hinzugefügt; PT*-Familie, MFILTER; letztes EPROM **v7.2** (1998) | **11.09.1995** |

Quellenlage (Kurzfassung): Die Modell-/Feature-Historie ist über
repeater-builder.com (WA6ILQ), das Timewave-Upgrade-Guide und diverse Manuals
gut belegt; **die exakte Zuordnung einzelner Befehle zu einem EPROM-Datum ist
in den AEA-Changelogs jedoch nicht lückenlos dokumentiert.** Deshalb ist die
Matrix in §4 eine *Hypothese mit Konfidenz-Spalte* — und dein Scan der drei
EPROMs ist der eigentliche Beweis (siehe §5).

---

## 2a. Tatsächlich gemessene Befunde — getrennt von der Hypothese

> **Alles in §4 unten ist Hypothese** (Konfidenz H/M/L), keine Messung — die
> Tabelle ist der vollständige STABO-Superset (194 Befehle), noch gegen
> keines der drei EPROMs real gegengeprüft (das leistet erst der
> Dreifach-Scan aus §5). Was tatsächlich am Gerät gemessen wurde, steht
> ausschließlich in dieser Tabelle hier — alles andere in diesem Dokument
> ist Annahme, auch wenn es mit hoher Konfidenz (H) markiert ist.

| Gerät | EPROM | Generation | Befund | Beleg |
|---|---|---|---|---|
| A | 11.09.1995 | PACTOR | Der gesamte unter `CLAUDE.md` → "Known Gotchas" dokumentierte Bestand an Hardware-Befunden (Mnemonics, MailDrop-Ablauf, Packet-/Channel-Verhalten, runde Prompt-Klammer, …) stammt von diesem Gerät. | `hw_logs/` (P9–P31), `CLAUDE.md` |
| A | 11.09.1995 | PACTOR | `MI` = MFILTER (nicht MDCHECK) — siehe Anmerkung unten. | T115, `CLAUDE.md` |
| B | 01.08.1991 | MBX | Nur die eckige Prompt-Klammer (`[AEA PK-232M]  18340 free  (B,E,K,L,R,S) >`) ist von diesem Gerät gemessen — ein einzelner Datenpunkt, kein Vergleichsscan gegen Gerät A. | `hw_logs/20260923_184302_maildrop_session.log` (P31) |
| B | 01.08.1991 | MBX | MDCHECK hat kein Host-Mode-Kürzel — `mdcheck_scan` fand keinen Treffer unter denselben 23 Kandidaten wie auf Gerät A. Der Befund gilt damit über zwei Firmwaregenerationen (MBX + PACTOR). | T118, `hw_logs/20260923_203256_mdcheck_scan.log` (P34) |
| B | 01.08.1991 | MBX | `MDCHECK` öffnet die Mailbox zuverlässig (Prompt erkannt), aber der direkt folgende `L`-Befehl antwortet mit `*** What?` — auf Gerät A funktioniert dieselbe Abfolge anstandslos. Ursache noch offen, siehe §6. | T119 (P35), `hw_logs/20260923_204041_maildrop_session.log` |
| C | 30.12.1988 | BASE | MailDrop fehlt auf diesem Gerät — direkt mit einem Terminalprogramm (PuTTY) geprüft, nicht über die App. | Betreiberangabe, 23.09.2026 |

**Kandidat für einen echten Generationsunterschied:** `MI` löst auf Gerät A
zu MFILTER auf — nicht MDCHECK, obwohl die TRM dasselbe Kürzel `MI` für
beide Befehle führt (bekannter Widerspruch im Handbuch selbst, T115,
`CLAUDE.md`). Gerät A ist PACTOR-Generation, genau die Generation, die
MFILTER laut §2 überhaupt erst einführt. Gerät B (MBX-Generation, eine
Stufe früher) hat MFILTER laut der Hypothese in §4 noch **nicht** — dort
könnte `MI` also tatsächlich MDCHECK bedeuten (oder gar nichts). **Weiterhin
ungeprüft** — der Gerät-B-`mdcheck_scan`-Lauf oben klärt das NICHT: `MI`
steht auf der Denyliste des Scans (gilt als bereits identifiziert, wird nie
mitgesendet), auf keinem der beiden Geräte. Für diesen Kandidaten braucht es
einen gezielten Lauf von `tools/hw_check.py mi` auf Gerät B, nicht
`mdcheck_scan`.

---

## 3. So testet das Skript — sicher

Ein blinder Scan aller Mnemonics wäre gefährlich (`RESET` löscht die Config,
`XMIT`/`CONNECT`/`ARQ`/`FEC` **tasten den Sender**, `BAUDOT`/`FAX`/`PACKET`
verlassen den Command-Mode). Darum unterscheidet die DB zwei Probentypen:

- **Q (QUERY)** — reiner Parameter-Befehl. Nacktes Absetzen zeigt nur den Wert.
  Ein bekannter Befehl echot seinen Namen (`HBaud 300`); ein unbekannter
  antwortet mit **`*** What?`**. → Diese Befehle werden automatisch geprüft.
- **S (SKIP)** — Aktion/Modus/zerstörend. Wird **nie** automatisch abgesetzt;
  seine Verfügbarkeit wird aus Banner-Datum + den sicheren Generations-Markern
  abgeleitet.

Die **Generations-Marker** (sicher abfragbare Parameter, die sauber pro
Generation vorhanden/abwesend sind):

- `MBX` (MB) vorhanden ⟹ **≥ MBX-Generation** (ab 1990).
- `PTHUFF` (PH) vorhanden ⟹ **≥ PACTOR-Generation** (ab 1993).
  (Zusätzlich enthält der Boot-Banner den String „PACTOR" — das nutzt
  `SerialManager.has_pactor` in PK232PY bereits.)

Das Skript vergleicht anschließend „laut Banner-Generation **erwartet**" gegen
„vom Gerät **bestätigt**" und markiert **Anomalien** (`unexpected-present` /
`unexpected-absent`). Genau diese Anomalien sind Gold: Sie zeigen, wo die
Hypothese in §4 zu korrigieren ist.

---

## 3a. Sonderfall EXPERT (Anfänger-/Experten-Ebene)

`EXPERT ON|OFF` (Host-Mnemonic `EX`, Default **OFF**) steuert, welche Befehle im
Verbose-Modus überhaupt sichtbar sind. Bei **EXPERT OFF** ist rund die Hälfte
der Befehle — die „Experten-Befehle", darunter **PASSALL** — gesperrt und
tauchen in keiner Anzeige auf. Der Versuch, einen davon zu benutzen, liefert die
eigene Meldung **`?EXPERT command`** (nicht `*** What?`). **EXPERT ON** schaltet
alle Befehle frei. Direkte Befehle (CONNECT, PACKET …) sind stets „Anfänger"-
Befehle; im **Host-Mode** ignoriert das Gerät EXPERT komplett.

> Hinweis: Die deutsche STABO-Übersetzung vertauscht in der ON/OFF-Kurzbe­schreibung
> versehentlich die Bedeutungen. Operativ korrekt (und mit „EXP ON eingeben, um
> Expertenbefehle zu nutzen" konsistent) ist: **ON = alles frei, OFF = gesperrt.**

**Ab welchem Release?** Die Ur-Firmware (1986/87) kennt EXPERT nicht — weder die
TRM (Rev. A 5/87, Release 29.JUL.86) noch das 1986er Operating-Manual (dessen
Fehlerliste nur `?not enough` / `?too many` / `?need …` führt) erwähnen EXPERT
oder `?EXPERT command`. In der MBX/PACTOR-Ära ist EXPERT dokumentiert und steht
in der REINT-Erhaltungsliste mitten unter den MBX-Befehlen (MYALIAS, MYMAIL,
HOMEBBS, MYGATE, NAVSTN, 3RDPARTY, TMAIL, MVIA …). **Best-Estimate: eingeführt
mit der MBX-Generation (~1989/1990), Konfidenz L.** Dein **30.12.1988-EPROM ist
der Grenzfall** — genau das klärt der Scan: EXPERT ist ein sicherer Query-Befehl,
also zeigt der 1988er-Lauf sofort `SUPPORTED` (dann gab es EXPERT schon) oder
`*** What?` (dann nicht).

**Konsequenz fürs Tool:** Der Scanner setzt vor dem Durchlauf automatisch
`EXPERT ON` (und stellt den vorherigen Zustand danach wieder her). Sonst kämen
für die halbe Befehlsliste `?EXPERT command`-Antworten statt echter Werte. Ein
`EXPERT_GATED`-Ergebnis im Report bedeutet: Befehl vorhanden, aber Unlock hat
(für diesen Befehl) nicht gegriffen — es zählt als „vorhanden".

---

## 4. Hypothesen-Matrix (Befehl × Generation)

> ⚠️ **Jede Zeile dieser Tabelle ist Hypothese, keine Messung** — auch die
> mit Konfidenz **H**. Die einzigen tatsächlich gemessenen Befunde stehen
> in §2a oben.

`x` = laut Hypothese in dieser Generation vorhanden.
Konfidenz **H/M/L** (L = unsicher, vom Scan zu klären).
Probe **Q** = sicher abfragbar, **S** = Aktion/Modus (nicht auto-getestet).

Der Befehlssatz ist der **vollstaendige Superset** (194 Befehle) aus der
STABO-Befehlszusammenfassung (juengste MBX/PACTOR-Firmware). Nur so lassen sich
Abweichungen zwischen den FW-Staenden ueberhaupt erkennen: ein Befehl, der auf
einem aelteren EPROM `*** What?` liefert, auf einem neueren aber einen Wert, ist
genau die gesuchte Differenz. Die Tabelle wird aus derselben `COMMAND_DB` erzeugt
wie das Tool (`python pk232_fw_scan.py --matrix`), bleibt also konsistent.

Die Generation vieler neuerer Befehle (MailDrop/Gateway/NAVTEX/PACTOR) ist
heuristisch mit **Konfidenz L** gesetzt — der Dreifach-Scan deiner EPROMs
haertet sie ab.

| MN | Befehl | Gruppe | 1988 | 1991 | 1995 | Konf | Probe | Anm. |
|----|--------|--------|:----:|:----:|:----:|:----:|:-----:|------|
| AU | AAB | amtor |  x   |  x   |  x   | M | Q |  |
| AG | ACHG | amtor |  x   |  x   |  x   | M | S | direct |
| AD | ADELAY | amtor |  x   |  x   |  x   | M | Q |  |
| AL | ALIST | amtor |  x   |  x   |  x   | M | S | read-only list |
| AC | ARQ | amtor |  x   |  x   |  x   | M | S | direct |
| AO | ARQTMO | amtor |  x   |  x   |  x   | M | Q |  |
| AO | ARQTOL | amtor |  x   |  x   |  x   | M | Q |  |
| CU | CBELL | amtor |  x   |  x   |  x   | M | Q |  |
| DC | DCDCONN | amtor |  x   |  x   |  x   | M | Q |  |
| EA | EAS | amtor |  x   |  x   |  x   | M | Q |  |
| FE | FEC | amtor |  x   |  x   |  x   | M | S | direct |
| ID | ID | amtor |  x   |  x   |  x   | M | S | direct |
| MW | MARSDISP | amtor |  x   |  x   |  x   | M | Q |  |
| MK | MYALTCAL | amtor |  x   |  x   |  x   | M | Q |  |
| MG | MYSELCAL | amtor |  x   |  x   |  x   | M | Q |  |
| OV | OVER | amtor |  x   |  x   |  x   | M | S | AMTOR/PACTOR changeover |
| RF | RFEC | amtor |  x   |  x   |  x   | M | Q |  |
| RX | RXREV | amtor |  x   |  x   |  x   | M | Q |  |
| SE | SELFEC | amtor |  x   |  x   |  x   | M | S | direct |
| SR | SRXALL | amtor |  x   |  x   |  x   | M | Q |  |
| TX | TXREV | amtor |  x   |  x   |  x   | M | Q |  |
| WO | WORDOUT | amtor |  x   |  x   |  x   | M | Q |  |
| RI | REINIT | danger |      |  x   |  x   | H | S | resets most params |
| RS | RESET | danger |  x   |  x   |  x   | H | S | WIPES bbRAM |
| RT | RESTART | danger |  x   |  x   |  x   | H | S | reboot (tool uses it) |
| AY | ASPECT | fax |  x   |  x   |  x   | M | Q |  |
| AQ | AUDELAY | fax |  x   |  x   |  x   | M | Q |  |
| CW | CWID | fax |  x   |  x   |  x   | M | Q |  |
| FN | FAXNEG | fax |  x   |  x   |  x   | M | Q |  |
| FS | FSPEED | fax |  x   |  x   |  x   | M | Q |  |
| GR | GRAPHICS | fax |  x   |  x   |  x   | M | Q |  |
| JU | JUSTIFY | fax |  x   |  x   |  x   | M | S | direct |
| LR | LEFTRITE | fax |  x   |  x   |  x   | M | Q |  |
| LO | LOCK | fax |  x   |  x   |  x   | M | S | direct |
| PF | PRFAX | fax |  x   |  x   |  x   | M | Q |  |
| PY | PRTYPE | fax |  x   |  x   |  x   | M | Q |  |
| RC | RCVE | fax |  x   |  x   |  x   | M | S | direct |
| TR | TRACE | fax |  x   |  x   |  x   | M | Q |  |
| XM | XMIT | fax |  x   |  x   |  x   | M | S | direct |
| 5B | 5BIT | global |  x   |  x   |  x   | M | S | direct |
| 6B | 6BIT | global |  x   |  x   |  x   | M | S | direct |
| AA | ACRDISP | global |  x   |  x   |  x   | M | Q |  |
| AE | ADDRESS | global |  x   |  x   |  x   | M | Q |  |
| AZ | AFILTER | global |  x   |  x   |  x   | M | Q |  |
| AI | ALFDISP | global |  x   |  x   |  x   | M | Q |  |
| AM | AMTOR | global |  x   |  x   |  x   | M | S | direct |
| AS | ASCII | global |  x   |  x   |  x   | M | S | direct |
| AW | AWLEN | global |  x   |  x   |  x   | M | Q |  |
| BA | BAUDOT | global |  x   |  x   |  x   | M | S | direct |
| BK | BKONDEL | global |  x   |  x   |  x   | M | Q |  |
| CL | CANLINE | global |  x   |  x   |  x   | M | Q |  |
| CQ | CMDTIME | global |  x   |  x   |  x   | M | Q |  |
| CN | COMMAND | global |  x   |  x   |  x   | M | Q |  |
| DS | DAYSTAMP | global |  x   |  x   |  x   | M | Q |  |
| DA | DAYTIME | global |  x   |  x   |  x   | M | Q |  |
| EC | ECHO | global |  x   |  x   |  x   | M | Q |  |
| ES | ESCAPE | global |  x   |  x   |  x   | M | Q |  |
| EX | EXPERT | global |      |  x   |  x   | L | Q | unlocks expert cmds; verbose-only |
| FA | FAX | global |  x   |  x   |  x   | M | S | direct |
| FL | FLOW | global |  x   |  x   |  x   | M | Q |  |
| HO | HOST | global |  x   |  x   |  x   | M | Q |  |
| IO | IO | global |  x   |  x   |  x   | M | Q |  |
| MO | MORSE | global |  x   |  x   |  x   | M | S | direct |
| NR | NUCR | global |  x   |  x   |  x   | M | Q |  |
| NF | NULF | global |  x   |  x   |  x   | M | Q |  |
| NU | NULLS | global |  x   |  x   |  x   | M | Q |  |
| OP | OPMODE | global |      |      |  x   | M | Q | safe: queries opmode |
| PA | PACKET | global |  x   |  x   |  x   | M | S | direct |
| PR | PARITY | global |  x   |  x   |  x   | M | Q |  |
| PC | PRCON | global |  x   |  x   |  x   | M | Q |  |
| PO | PROUT | global |  x   |  x   |  x   | M | Q |  |
| RD | REDISPLAY | global |  x   |  x   |  x   | M | Q |  |
| SA | SAMPLE | global |  x   |  x   |  x   | M | S | direct |
| SI | SIGNAL | global |  x   |  x   |  x   | M | S | direct |
| ST | START | global |  x   |  x   |  x   | M | Q |  |
| SO | STOP | global |  x   |  x   |  x   | M | Q |  |
| TB | TBAUD | global |  x   |  x   |  x   | M | Q |  |
| TC | TCLEAR | global |  x   |  x   |  x   | M | S | direct |
| TM | TIME | global |  x   |  x   |  x   | M | Q |  |
| TW | TRFLOW | global |  x   |  x   |  x   | M | Q |  |
| XW | XFLOW | global |  x   |  x   |  x   | M | Q |  |
| XO | XMITOK | global |  x   |  x   |  x   | M | Q |  |
| XF | XOFF | global |  x   |  x   |  x   | M | Q |  |
| XN | XON | global |  x   |  x   |  x   | M | Q |  |
| 3R | 3RDPARTY | maildrop |      |  x   |  x   | L | Q |  |
| BB | BBSMSGS | maildrop |      |  x   |  x   | L | Q |  |
| CM | CMSG | maildrop |      |  x   |  x   | L | Q |  |
| CT | CTEXT | maildrop |      |  x   |  x   | L | Q |  |
| DL | DELETE | maildrop |      |  x   |  x   | L | Q |  |
| FZ | FREE | maildrop |      |  x   |  x   | L | S | direct |
| HR | HEREIS | maildrop |      |  x   |  x   | L | Q |  |
| HM | HOMEBBS | maildrop |      |  x   |  x   | L | Q |  |
| KL | KILONFWD | maildrop |      |  x   |  x   | L | Q |  |
| LM | LASTMSG | maildrop |      |  x   |  x   | L | Q |  |
| MV | MAILDROP | maildrop |      |  x   |  x   | L | Q |  |
| ME | MBELL | maildrop |      |  x   |  x   | L | Q |  |
| MB | MBX | maildrop |      |  x   |  x   | H | Q | GEN-MARKER MBX |
| MK | MDCHECK | maildrop |      |  x   |  x   | L | S | direct |
| MD | MDIGI | maildrop |      |  x   |  x   | L | Q |  |
| MM | MEMORY | maildrop |      |  x   |  x   | M | Q | verify read-only |
| MU | MMSG | maildrop |      |  x   |  x   | L | Q |  |
| MQ | MPROTO | maildrop |      |  x   |  x   | L | Q |  |
| MS | MSTAMP | maildrop |      |  x   |  x   | L | Q |  |
| MA | MYALIAS | maildrop |      |  x   |  x   | L | Q |  |
| MY | MYGATE | maildrop |      |  x   |  x   | L | Q |  |
| TL | TMAIL | maildrop |      |  x   |  x   | L | Q |  |
| UB | UBIT | maildrop |      |  x   |  x   | L | Q |  |
| UR | USERS | maildrop |      |  x   |  x   | L | Q |  |
| OK | OK | misc |  x   |  x   |  x   | M | S | direct |
| RE | RECEIVE | misc |  x   |  x   |  x   | M | S | name implies action |
| MP | MSPEED | morse |  x   |  x   |  x   | M | Q |  |
| ER | ERRCHAR | navtex |      |  x   |  x   | L | Q |  |
| NM | NAVMSG | navtex |      |  x   |  x   | L | Q |  |
| NS | NAVSTN | navtex |      |  x   |  x   | L | Q |  |
| NA | NAVTEX | navtex |      |  x   |  x   | L | S | direct |
| AN | ACKPRIOR | packet |  x   |  x   |  x   | M | Q |  |
| AK | ACRPACK | packet |  x   |  x   |  x   | M | Q |  |
| AP | ALFPACK | packet |  x   |  x   |  x   | M | Q |  |
| AV | AX25L2V2 | packet |  x   |  x   |  x   | M | Q |  |
| AX | AXDELAY | packet |  x   |  x   |  x   | M | Q |  |
| AH | AXHANG | packet |  x   |  x   |  x   | M | Q |  |
| BE | BEACON | packet |  x   |  x   |  x   | M | Q |  |
| BT | BTEXT | packet |  x   |  x   |  x   | M | Q |  |
| CX | CASEDISP | packet |  x   |  x   |  x   | M | Q |  |
| CF | CFROM | packet |  x   |  x   |  x   | M | Q |  |
| CB | CHCALL | packet |  x   |  x   |  x   | M | Q |  |
| CD | CHDOUBLE | packet |  x   |  x   |  x   | M | Q |  |
| CK | CHECK | packet |  x   |  x   |  x   | M | Q |  |
| CH | CHSWITCH | packet |  x   |  x   |  x   | M | Q |  |
| CE | CONMODE | packet |  x   |  x   |  x   | M | Q |  |
| CO | CONNECT | packet |  x   |  x   |  x   | M | S | direct |
| CY | CONPERM | packet |  x   |  x   |  x   | M | Q |  |
| CG | CONSTAMP | packet |  x   |  x   |  x   | M | Q |  |
| CI | CPACTIME | packet |  x   |  x   |  x   | M | Q |  |
| DF | DFROM | packet |  x   |  x   |  x   | M | Q |  |
| DI | DISCONNECT | packet |  x   |  x   |  x   | M | S | direct |
| DW | DWAIT | packet |  x   |  x   |  x   | M | Q |  |
| FR | FRACK | packet |  x   |  x   |  x   | M | Q |  |
| FU | FULLDUP | packet |  x   |  x   |  x   | M | Q |  |
| HB | HBAUD | packet |  x   |  x   |  x   | M | Q |  |
| HD | HEADERLN | packet |  x   |  x   |  x   | M | Q |  |
| HP | HPOLL | packet |  x   |  x   |  x   | M | Q |  |
| IL | ILFPACK | packet |  x   |  x   |  x   | M | Q |  |
| KA | KISSADDR | packet |  x   |  x   |  x   | M | Q |  |
| MX | MAXFRAME | packet |  x   |  x   |  x   | M | Q |  |
| MC | MCON | packet |  x   |  x   |  x   | M | Q |  |
| MF | MFROM | packet |  x   |  x   |  x   | M | Q |  |
| MH | MHEARD | packet |  x   |  x   |  x   | M | S | read-only list |
| MN | MONITOR | packet |  x   |  x   |  x   | M | Q |  |
| MR | MRPT | packet |  x   |  x   |  x   | M | Q |  |
| MT | MTO | packet |  x   |  x   |  x   | M | Q |  |
| ML | MYCALL | packet |  x   |  x   |  x   | M | Q |  |
| PL | PACLEN | packet |  x   |  x   |  x   | M | Q |  |
| PT | PACTIME | packet |  x   |  x   |  x   | M | Q |  |
| PX | PASSALL | packet |  x   |  x   |  x   | M | Q |  |
| PE | PERSIST | packet |  x   |  x   |  x   | M | Q |  |
| PP | PPERSIST | packet |  x   |  x   |  x   | M | Q |  |
| RW | RAWHDLC | packet |  x   |  x   |  x   | M | Q |  |
| RL | RELINK | packet |  x   |  x   |  x   | M | Q |  |
| RP | RESPTIME | packet |  x   |  x   |  x   | M | Q |  |
| RY | RETRY | packet |  x   |  x   |  x   | M | Q |  |
| SP | SENDPAC | packet |  x   |  x   |  x   | M | Q |  |
| SL | SLOTTIME | packet |  x   |  x   |  x   | M | Q |  |
| SQ | SQUELCH | packet |  x   |  x   |  x   | M | Q |  |
| 71 | TRIES | packet |  x   |  x   |  x   | M | Q |  |
| TF | TXFLOW | packet |  x   |  x   |  x   | M | Q |  |
| UN | UNPROTO | packet |  x   |  x   |  x   | M | Q |  |
| VH | VHF | packet |  x   |  x   |  x   | M | Q |  |
| WN | WHYNOT | packet |  x   |  x   |  x   | M | Q |  |
| MI | MFILTER | pactor |      |      |  x   | L | Q |  |
| NE | NEWMODE | pactor |      |      |  x   | L | Q |  |
| PB | PT200 | pactor |      |      |  x   | L | Q |  |
| PG | PTCON | pactor |      |      |  x   | L | S | direct |
| PN | PTLIST | pactor |      |      |  x   | M | S | read-only list |
| PV | PTOVER | pactor |      |      |  x   | L | Q |  |
| PD | PTSEND | pactor |      |      |  x   | L | Q |  |
| UC | UCMD | pactor |      |      |  x   | L | Q |  |
| 8B | 8BITCONV | rtty |  x   |  x   |  x   | M | Q |  |
| AB | ABAUD | rtty |  x   |  x   |  x   | M | Q |  |
| AT | ACRRTTY | rtty |  x   |  x   |  x   | M | Q |  |
| AR | ALFRTTY | rtty |  x   |  x   |  x   | M | Q |  |
| BI | BITINV | rtty |  x   |  x   |  x   | M | Q |  |
| CR | CRADD | rtty |  x   |  x   |  x   | M | Q |  |
| DD | DIDDLE | rtty |  x   |  x   |  x   | M | Q |  |
| PS | PASS | rtty |  x   |  x   |  x   | M | Q |  |
| RB | RBAUD | rtty |  x   |  x   |  x   | M | Q |  |
| TD | TXDELAY | rtty |  x   |  x   |  x   | M | Q |  |
| US | USOS | rtty |  x   |  x   |  x   | M | Q |  |
| WR | WRU | rtty |  x   |  x   |  x   | M | Q |  |
| XB | XBAUD | rtty |  x   |  x   |  x   | M | Q |  |
| NX | NUMS | signal |      |  x   |  x   | L | S | direct |
| TU | TDBAUD | signal |      |  x   |  x   | L | Q |  |
| TN | TDCHAN | signal |      |  x   |  x   | L | Q |  |
| TV | TDM | signal |      |  x   |  x   | L | S | direct |
---

## 5. Empirische Matrix in drei Läufen erzeugen

Auf jedem EPROM einmal laufen lassen und den Report festhalten:

```powershell
python tools\pk232_fw_scan.py --port COM16 --csv fw_1988.csv --json fw_1988.json
# EPROM wechseln ...
python tools\pk232_fw_scan.py --port COM16 --csv fw_1991.csv
python tools\pk232_fw_scan.py --port COM16 --csv fw_1995.csv
```

Danach die drei CSVs nebeneinanderlegen (Spalte `result` je Befehl). Wo sich
`SUPPORTED`/`UNSUPPORTED` zwischen den Ständen ändert, hast du die **echte**
Einführungs-Generation. Die `anomaly`-Spalte weist dich direkt auf jeden
Befehl hin, bei dem Hypothese und Realität auseinanderlaufen — die trägst du
dann mit hoher Konfidenz in die DB zurück.

Trockenlauf ohne Hardware (zum Ausprobieren der Ausgabe):

```powershell
python tools\pk232_fw_scan.py --selftest 1988   # bzw. 1991 / 1995
```

---

## 6. Offene Punkte / bewusste Unsicherheiten (Konfidenz L)

Diese Einordnungen sind Schätzungen und der Hauptgrund, den echten Scan zu
fahren:

- **Drucker-Familie** `PRCON/PRFAX/PROUT/PRTYPE` — Generation unklar (MBX?).
- **NAVTEX** — dem MBX-Handbuch nach MBX-Klasse, exaktes Einführungsdatum offen.
- **`MDIGI`, `MSTAMP`** — BASE oder erst MBX?
- **`NEWMODE`/`NOMODE`/`MFILTER`/`OPMODE`** — als PACTOR/Gateway-nah eingeordnet,
  aber nicht hart belegt.
- **`MEMORY`** — als Query behandelt; am Gerät verifizieren, dass es nur
  anzeigt und nichts löscht, bevor man ihm traut.
- **Gesamte MailDrop-/Gateway-/NAVTEX-/TDM-/PACTOR-Ebene** (HOMEBBS, MYGATE,
  MAILDROP, 3RDPARTY, TMAIL, BBSMSGS, KILONFWD, MMSG, LASTMSG, MDCHECK, UBIT,
  UCMD, PT200, PTCON, NAVMSG, NAVSTN, TDCHAN, TDBAUD …) — als MBX bzw. PACTOR
  eingeordnet, aber die genaue Einführungs-Generation ist heuristisch (Konf. L).
- **Direkte Befehle** (Probe `S`) werden nicht automatisch geprüft; ihre Präsenz
  wird aus Banner-Datum + Query-Nachbarn derselben Generation abgeleitet. Wo ein
  direkter Befehl empirisch interessiert, lässt er sich am Gerät gezielt (mit
  gültigem Argument, Sender aus/Dummy-Load) manuell testen.
- **Verhält sich `L` (MailDrop LIST) auf MBX (Gerät B) anders als auf
  PACTOR (Gerät A)? (P35, 23.09.2026, offen.)** Auf Gerät A öffnet
  `MDCHECK` die Mailbox und `L` listet zuverlässig (P20–P24). Auf Gerät
  B öffnete `MDCHECK` die Mailbox ebenso (Prompt erkannt,
  `bracket='square'`, `free=18340`), aber der direkt folgende `L`-Befehl
  antwortete mit `*** What?`
  (`hw_logs/20260923_204041_maildrop_session.log`). Drei aus dem
  Mitschnitt nicht unterscheidbare Ursachen — ein Software-Artefakt
  (überzähliges LF nach `MDCHECK`, seitdem entfernt, P35.2), ein echter
  Generationsunterschied im MailDrop-Befehlssatz, oder verschmolzene
  Antwortpuffer ohne Protokollursache — siehe CLAUDE.md, "Mailbox
  commands terminate with CR only". `MailDropSession` protokolliert
  jetzt jeden Rohblock (P35.1); ein erneuter Lauf auf Gerät B mit
  aktivem Mitschnitt sollte klären, welche der drei zutrifft.

Nach dem ersten realen Dreifach-Scan lassen sich fast alle L→H hochstufen — und
genau die Befehle, die zwischen 1988/1991/1995 kippen, sind die gesuchten
Versionsunterschiede.