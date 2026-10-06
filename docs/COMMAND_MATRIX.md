# Command / firmware matrix

> GENERATED from `src/pk232py/data/command_matrix.csv` by `tools/gen_command_matrix.py --update` -
> do not edit. The CSV is the ONE truth about which command exists on which firmware (P88).
> `yes` present, `no` answers `?What?`, `expert` present but needs EXPERT ON, `?` not measured.
> A cell that is not `?` has its evidence in the last column (`A` = 13.SEP.95, `B` = 01.AUG.91,
> `C` = 30.12.1988, docs/DEVICES.md).

## Cells per firmware

| Release | Device | yes | no | expert | ? |
|---|---|---|---|---|---|
| 01.AUG.91 | B | 0 | 0 | 0 | 260 |
| 13.SEP.95 | A | 0 | 0 | 0 | 260 |
| 30.12.1988 | C | 0 | 0 | 0 | 260 |

260 commands.

## Commands

| Name | Abbrev | Host | Kind | 01.AUG.91 | 13.SEP.95 | 30.12.1988 | Default | Function | Evidence |
|---|---|---|---|---|---|---|---|---|---|
| 3RDPARTY | 3R |  | param | ? | ? | ? | OFF | Enables 3rd party MailDrop messages |  |
| 5BIT | 5B |  | mode | ? | ? | ? | Immediate Command | Starts copying special 5 bit stations |  |
| 6BIT | 6B |  | mode | ? | ? | ? | Immediate Command | Starts copying special 6 bit stations |  |
| 8BITCONV | 8B |  | param | ? | ? | ? | OFF | Enables 8 bit data in packet/ASCII CONVERSE |  |
| AAB | AA |  | param | ? | ? | ? | (empty) | Sets the 0-24 character WRU Auto-answerback |  |
| ABAUD | AB |  | param | ? | ? | ? | 110 baud | Sets the ASCII baud rate |  |
| ACHG | AC |  | action_tx | ? | ? | ? | Immediate Command | Forces AMTOR and Pactor ARQ Changeover |  |
| ACKPRIOR | ACK |  | param | ? | ? | ? | OFF | Enables priority acknowledgment in packet |  |
| ACRDISP | ACRD |  | param | ? | ? | ? | 0 | Sets terminal output Screen width |  |
| ACRPACK | ACRP |  | param | ? | ? | ? | ON | Adds Carriage Returns to transmitted packets |  |
| ACRRTTY | ACRR |  | param | ? | ? | ? | 71 | Sets the RTTY/AMTOR Auto <CR> insert column (PK232PY mask label is ACRTTY (config acrtty)) |  |
| ADDRESS | ADD |  | param | ? | ? | ? | $0000 | Setting an Address in the PK-232 memory |  |
| ADELAY | AD |  | param | ? | ? | ? | 4 | Sets AMTOR and Pactor transmit delay, 10 ms. |  |
| AFILTER | AF |  | param | ? | ? | ? | OFF | Enables All-mode-receive character filter |  |
| ALFDISP | ALFD |  | param | ? | ? | ? | ON | Sends <LF> after <CR> to terminal |  |
| ALFPACK | ALFP |  | param | ? | ? | ? | OFF | Sends <LF> after <CR> in transmitted packets |  |
| ALFRTTY | ALFR |  | param | ? | ? | ? | ON | Sends <LF> after <CR> in transmitted RTTY |  |
| ALIST | AL |  | mode | ? | ? | ? | Immediate Command | Starts the AMTOR ARQ 'Listen' mode |  |
| ALTMODEM | ALTM |  | param | ? | ? | ? | 0 | Setting an optional 2400-Baud modem |  |
| AMTOR | AM |  | mode | ? | ? | ? | Immediate command | Starts the AMTOR mode in ARQ standby |  |
| ARQ | AR |  | action_tx | ? | ? | ? | Immediate command | Starts the AMTOR ARQ call with SELCAL |  |
| ARQE | ARQ |  | mode | ? | ? | ? | Immediate Command | Starts the ARQ-E receive mode |  |
| ARQTMO | ARQT |  | param | ? | ? | ? | 60 | Sets the AMTOR/Pactor ARQ call time-out |  |
| ARQTOL | ARQTOL |  | param | ? | ? | ? | 3 | Sets bit jitter tolerance in ARQ AMTOR (source reads 'A.RQ' (OCR); corrected to 'ARQ') |  |
| ARXTOR | ARXT |  | param | ? | ? | ? | OFF | Enable/Disable auto-detect AMTOR/PACTOR modes |  |
| ASCII | AS |  | mode | ? | ? | ? | Immediate Command | Starts the ASCII RTTY mode |  |
| ASPECT | ASP |  | param | ? | ? | ? | 2 (576) | Sets the received aspect ratio in FAX |  |
| ATXRTTY | AT |  | param | ? | ? | ? | 0 | Sends MORSE/BAUDOT/ASCII auto in CONVERSE |  |
| AUDELAY | AU |  | param | ? | ? | ? | 2 (20 msec.) | Sets delay before audio is applied after PTT |  |
| AUTOBAUD | AUTOB |  | param | ? | ? | ? | OFF | Enables Autobaud routine at every power-on |  |
| AWLEN | AW |  | param | ? | ? | ? | 7 | Sets ASCII word length to RS-232 terminal |  |
| AX25L2V2 |  |  | param | ? | ? | ? | ON | Sets AX.25 Version 2.0 packet protocol (Timewave list reads 'Ax2512v2' (OCR); name corrected, abbreviation unclear from the source) |  |
| AXDELAY | AXD |  | param | ? | ? | ? | 0 (zero) | Sets packet Repeater key-up delay (×10 ms) |  |
| AXHANG | AXH |  | param | ? | ? | ? | 0 (zero) | Sets packet Repeater hang time (×10 ms) (source reads 'racket' (OCR); corrected to 'packet') |  |
| BARGRAPH |  |  | param | ? | ? | ? |  |  (named in PK232PY (Misc mask, read-only); not in the Timewave list) |  |
| BAUDOT | BA |  | mode | ? | ? | ? | Immediate Command | Starts the Baudot RTTY mode |  |
| BBSMSGS | BBS |  | param | ? | ? | ? | OFF | Enables TAPR style status messages |  |
| BEACON | B |  | param | ? | ? | ? | Every 0 | Sets the packet beacon timing (×10 seconds) |  |
| BITINV | BI |  | param | ? | ? | ? | $00 | Sets the XOR value to copy bit inverted RTTY |  |
| BKONDEL | BK |  | param | ? | ? | ? | ON | Sends <BS><SP><BS> for DELETE char. |  |
| BRIGHT |  |  | param | ? | ? | ? |  |  (named in PK232PY (Misc mask, read-only); not in the Timewave list) |  |
| BTEXT | BT |  | param | ? | ? | ? | (Empty) | Sets the 120-byte packet BEACON message text |  |
| CALIBRATE | CAL |  | danger | ? | ? | ? | Immediate Command | Starts PK-232 AFSK tone calibrate mode (source name truncated to 8 characters (CALibrat); keys the AFSK tones - never probed) |  |
| CANLINE | CAN |  | param | ? | ? | ? | $18 <CTRL-X> | Sets the LINE DELETE character for editing |  |
| CANPAC | CANP |  | param | ? | ? | ? | $19 <CTRL-Y> | Sets the PACKET DELETE character for editing |  |
| CASEDISP | CAS |  | param | ? | ? | ? | 0 (as is) | Sets the display case (as is/lower/upper) |  |
| CBELL | CB |  | param | ? | ? | ? | OFF | Enables packet and Pactor 'Connect' bell |  |
| CCITT | CCITT |  | param | ? | ? | ? | ON | (Use the CODE COMMAND instead!) (source: the function column only says to use CODE instead) |  |
| CFROM | CF |  | param | ? | ? | ? | Empty; enter calls | Sets the Connect request/accept list |  |
| CHCALL | CHC |  | param | ? | ? | ? | OFF | Shows call sign after packet channel ID |  |
| CHDOUBLE | CHD |  | param | ? | ? | ? | OFF | Shows CHSWITCH character twice |  |
| CHECK | CH |  | param | ? | ? | ? | 30 | Sets Idle packet link time-cut (×10 seconds) |  |
| CHSWITCH | CHS |  | param | ? | ? | ? | $00 | Sets the channel-select character |  |
| CMDTIME | CM |  | param | ? | ? | ? | 10 | Sets the Transparent Mode escape time |  |
| CMSG | CMS |  | param | ? | ? | ? | OFF | Sends CTEXT message to packet caller |  |
| CODE | COD |  | param | ? | ? | ? | 0 (international) | Selects Morse/Baudot/AMTOR character sets |  |
| COMMAND | COM |  | param | ? | ? | ? | $03 <CTRL-C> | Sets COMMAND Mode escape character |  |
| CONMODE | CONM |  | param | ? | ? | ? | CONVERSE | Selects the mode used when data link starts |  |
| CONNECT | C |  | action_tx | ? | ? | ? | Immediate Command | Sends a packet request to <Call> |  |
| CONOK | CON |  | param | ? | ? | ? |  |  (not in the Timewave list; named by the fw_scan hypothesis table ("legacy TAPR; use CFROM instead")) |  |
| CONPERM | CONP |  | param | ? | ? | ? | OFF | Selects a permanent connection packet link |  |
| CONSTAMP | CONS |  | param | ? | ? | ? | OFF | Marks connections with time/date stamp |  |
| CONVERSE | CONV |  | mode | ? | ? | ? | Immediate Command | Enters the Converse Mode (Abbrev. K) |  |
| CPACTIME | CP |  | param | ? | ? | ? | OFF | Uses PACTIME time-out in Converse mode |  |
| CRADD | CRA |  | param | ? | ? | ? | OFF | Sends <CR><CR><LF> in RTTY Mode |  |
| CSTATUS | CS |  | immediate | ? | ? | ? | Immediate command | Shows status of channels (links) |  |
| CTEXT | CT |  | param | ? | ? | ? | (Sample Text) | Sets 120-byte packet CONNECT message text |  |
| CUSTOM | CU |  | param | ? | ? | ? | $0A15 | (Use the UBIT command instead!) (source: the function column only says to use UBIT instead) |  |
| CWID | CW |  | param | ? | ? | ? | $06 <CTRL-F> | Sets the command to send CWID in RTTY modes |  |
| DAYSTAMP | DAYS |  | param | ? | ? | ? | OFF | Includes DATE in time-stamp (PK232PY mask label is DAGSTAMP (config dagstamp); the command sent is DAYSTAMP) |  |
| DAYTIME | DA |  | param | ? | ? | ? | None | Set or read the internal time-of-day clock |  |
| DCDCONN | DC |  | param | ? | ? | ? | OFF | Sets RS-232 Pin 8 to follow DCD or Connect |  |
| DELETE | DEL |  | param | ? | ? | ? | OFF | Uses DEL ($7F), not <BS> ($08) to erase |  |
| DFROM | DF |  | param | ? | ? | ? | Empty; enter calls | Sets the digipeat yes or no call sign list |  |
| DIDDLE | DID |  | param | ? | ? | ? | ON | Transmits idle characters in Baudot and ASCII |  |
| DIGIPEAT | DG |  | param | ? | ? | ? |  |  (not in the Timewave list; named by the fw_scan hypothesis table ("TAPR-compat digipeat toggle")) |  |
| DISCONNECT | D |  | action_tx | ? | ? | ? | Immediate Command | Sends packet DISC request to distant station (source name truncated to 8 characters (Disconne)) |  |
| DISPLAY | DISP |  | immediate | ? | ? | ? | Immediate Command | Shows the PK-232 parameters and classes |  |
| DWAIT | DW |  | param | ? | ? | ? | 16 | Sets the delay for digipeated packets |  |
| EAS | EAS |  | param | ? | ? | ? | OFF | Echoes characters as sent, non-packet modes |  |
| ECHO | E |  | param | ? | ? | ? | ON | Echoes typed keyboard characters |  |
| ERRCHAR | ER |  | param | ? | ? | ? | $5F (_) | Sets AMTOR/Morse displayed error Character |  |
| ESCAPE | ES |  | param | ? | ? | ? | OFF | Sends ESC character $lB to display as $24 |  |
| EXPERT | EXP |  | param | ? | ? | ? | OFF | ON/OFF verbose mode controller commands |  |
| FAX | FA |  | mode | ? | ? | ? | Immediate command | Enters the facsimile mode |  |
| FAXNEG | FAXN |  | param | ? | ? | ? | OFF | Reverses the black/white FAX sense |  |
| FEC | FE |  | action_tx | ? | ? | ? | Immediate command | Starts an AMTOR FEC transmission |  |
| FLOW | F |  | param | ? | ? | ? | ON | stops displaying received data while typing |  |
| FRACK | FR |  | param | ? | ? | ? | 5 | Sets time (×1 Sec) to wait for packet ACK |  |
| FREE | FRE |  | immediate | ? | ? | ? | Immediate Command | Displays available memory for MailDrop |  |
| FRICK | FRI |  | param | ? | ? | ? | 0 | Sets timer for packet meteor scatter mode |  |
| FSPEED | FS |  | param | ? | ? | ? | 2 | Sets the FAX horizontal scan rate per second |  |
| FULLDUP | FU |  | param | ? | ? | ? | OFF | Enables Full-Duplex packet operation |  |
| GRAPHICS | GR |  | param | ? | ? | ? | 1 (960 dots) | Sets the dot density used for FAX operation |  |
| GUSERS | GU |  | param | ? | ? | ? | 0 | Sets the maximum users allowed to use your node |  |
| HBAUD | HB |  | param | ? | ? | ? | 1200 bauds | Sets the Packet-Radio link baud rate |  |
| HEADERLN | HEA |  | param | ? | ? | ? | ON | Inserts <CR> after monitored packet headers |  |
| HELP | H |  | immediate | ? | ? | ? | None | Shows a brief HELP text on screen |  |
| HEREIS | HER |  | param | ? | ? | ? | $02 <CTRL-B> | Sets the character that sends your AAB text |  |
| HID | HI |  | param | ? | ? | ? | OFF | Sends HDLC ID UI packet every 9.5 minutes |  |
| HOMEBBS | HOM |  | param | ? | ? | ? | None | Sets callsign of the BBS for forwarding |  |
| HOST | HOST |  | param | ? | ? | ? | OFF | Enables HOST computer interface |  |
| HOSTKEY | HY |  | param | ? | ? | ? |  |  (not in the Timewave list; named by the fw_scan hypothesis table ("host-mode key")) |  |
| HPOLL | HP |  | param | ? | ? | ? | ON | Sets Host polling be used in Host interface |  |
| ID | I |  | action_tx | ? | ? | ? | Immediate command | Sends an ID in Baudot, ASCII AMTOR and Packet |  |
| ILFPACK | IL |  | param | ? | ? | ? | ON | Ignores line feeds from terminal in Packet |  |
| IO | IO |  | param | ? | ? | ? | none | A hex value used to access the PK-232s memory |  |
| JUSTIFY | J |  | immediate | ? | ? | ? | Immediate command | Moves received FAX left a number × 0.5" |  |
| K | K |  | mode | ? | ? | ? | Immediate command | Enters the Converse mode (same as CONVerse) (same as CONVERSE) |  |
| KILONFWD | KILONFWD |  | param | ? | ? | ? | ON | Kills messages after reverse forwarding |  |
| KISS | KI |  | param | ? | ? | ? | 0 (OFF) | Starts the KISS INC host protocol (KISS ON enters KISS mode) |  |
| KISSADDR | KISSA |  | param | ? | ? | ? | 0 | Sets the Address used in extended KISS mode |  |
| LASTMSG | LA |  | immediate | ? | ? | ? | Immediate Command | Sets/shows the Last maildrop message number |  |
| LEFTRITE | LE |  | param | ? | ? | ? | ON | Sets left-to-right Scan direction for FAX |  |
| LITE | LI |  | param | ? | ? | ? | OFF | Enables Timewave's Packet Lite HP protocol |  |
| LOCK | L |  | immediate | ? | ? | ? | Immediate Command | Locks Morse speed/ forces lower case in RTTY |  |
| MAILDROP | MA |  | param | ? | ? | ? | OFF | Enables the Packet MailDrop for remote users |  |
| MARK |  |  | param | ? | ? | ? |  |  (named in PK232PY (Misc mask, tone frequency); not in the Timewave list) |  |
| MARSDISP | MAR |  | param | ? | ? | ? | OFF | Translates received LTRS & FIGS characters |  |
| MAXFRAME | MA |  | param | ? | ? | ? | 4 | Sets a maximum of un-ACK'd packet frames |  |
| MBELL | MBE |  | param | ? | ? | ? | OFF | Rings bell when packet station heard |  |
| MBX | MBX |  | param | ? | ? | ? | none, (calls) | Monitors packet channel without headers |  |
| MCON | MC |  | param | ? | ? | ? | 0 | Monitors packets while connected (0–6) |  |
| MDCHECK | MDC |  | danger | ? | ? | ? | Immediate Command | Allows you to check into your own MailDrop (logs into the mailbox and halts packet operation - never auto (gotchas, P37)) |  |
| MDIGI | MD |  | param | ? | ? | ? | OFF | Monitors packet frames that you digipeat |  |
| MDMON | MDM |  | param | ? | ? | ? | OFF | Monitors stations using your MailDrop |  |
| MDPROMPT | MDP |  | param | ? | ? | ? | (see text) | Sets an 80 character MailDrop message prompt |  |
| MEMORY | ME |  | danger | ? | ? | ? | none | A hex value used to access the PK-232s memory |  |
| MFILTER | MFI |  | param | ? | ? | ? | $80 | Filters received ASCII characters |  |
| MFROM | MF |  | param | ? | ? | ? | ALL (calls) | Monitors packets FROM other packet stations |  |
| MHEARD | MH |  | immediate | ? | ? | ? | Immediate Command | Displays call packet signs heard |  |
| MID | MI |  | param | ? | ? | ? | 0 | Enables a Morse ID to be sent in packet |  |
| MMSG | MM |  | param | ? | ? | ? | OFF | Enables the MailDrop sign on message |  |
| MODEM |  |  | param | ? | ? | ? |  |  (named in PK232PY (Misc mask); not in the Timewave list) |  |
| MONITOR | M |  | param | ? | ? | ? | 4 (UA DM C D I UI) | Sets the packet Monitor mode level (0–6) |  |
| MOPTT | MOP |  | param | ? | ? | ? | OFF | Controls PTT output in Morse mode only (PK232PY sends the abbreviation MOPT (params_uploader.py); the mask label is MOPT) |  |
| MORSE | MO |  | mode | ? | ? | ? | Immediate Command | Starts the Morse mode, unlock speed |  |
| MPROTO | MP |  | param | ? | ? | ? | OFF | Enables monitoring of all packet protocols |  |
| MRPT | MR |  | param | ? | ? | ? | ON | Shows digipeaters in packet headers |  |
| MSPEED | MSP |  | param | ? | ? | ? | 20 | Sets the Morse speed in WPM (5-99) |  |
| MSTAMP | MS |  | param | ? | ? | ? | OFF | Time-stamps monitored packet frames |  |
| MTEXT | MTE |  | param | ? | ? | ? | (see text) | Sets a 120 character MailDrop sign-on message |  |
| MTO | MT |  | param | ? | ? | ? | Empty; enter calls | Monitors packets TO other station callsigns |  |
| MWEIGHT | MW |  | param | ? | ? | ? | 10 | Sets the Morse transmit dot weighting |  |
| MXMIT | MX |  | param | ? | ? | ? | OFF | Monitors transmitted packet frames |  |
| MYALIAS | MYA |  | param | ? | ? | ? | None; enter yours | Sets the alternate MYCALL for digipeating (source runs default and text together ('None Enter yours Sets ...')) |  |
| MYALTCAL | MYALT |  | param | ? | ? | ? | Empty; enter yours | Sets the alternate AMTOR SELCAL |  |
| MYCALL | MY |  | param | ? | ? | ? | PK232; enter yours | Sets YOUR packet call sign (MUST BE ENTERED) |  |
| MYGATE | MYG |  | param | ? | ? | ? | none | Node callsign used by other stations |  |
| MYIDENT | MYI |  | param | ? | ? | ? | None; enter yours | Sets your CCIR-625 7-character AMTOR SELCAL |  |
| MYMAIL | MYM |  | param | ? | ? | ? | None; enter yours | Sets your Packet MailDrop callsign |  |
| MYPTCALL | MYPT |  | param | ? | ? | ? | None; enter yours | Sets your Pactor callsign |  |
| MYSELCAL | MYS |  | param | ? | ? | ? | Empty; enter yours | Sets your AMTOR SELCAL, 4 letters |  |
| NAVMSG | NAVM |  | param | ? | ? | ? | ALL | Determines which NAVTEX messages you monitor |  |
| NAVSTN | NAVS |  | param | ? | ? | ? | ALL | Determines which NAVTEX stations you monitor |  |
| NAVTEX | NA |  | mode | ? | ? | ? | Immediate Command | Starts the NAVTEX/AMTEX receive mode |  |
| NEWMODE | NE |  | param | ? | ? | ? | ON | Returns to Command mode at disconnect |  |
| NOMODE | NO |  | param | ? | ? | ? | OFF | Sets NO mode changes (eg. cmd: to CONVERSE) |  |
| NUCR | NUC |  | param | ? | ? | ? | OFF | Sends Nulls to terminal after <CR> |  |
| NULF | NUL |  | param | ? | ? | ? | OFF | Sends Nulls to terminal after <LF> |  |
| NULLS | NULL |  | param | ? | ? | ? | 0 | Sets the number of for NUCR and NULF (source text incomplete ('the number of for NUCR and NULF')) |  |
| NUMS | N |  | immediate | ? | ? | ? | Immediate Command | Forces FIGS case in Baudot, AMTOR and TDM |  |
| OK | OK |  | immediate | ? | ? | ? | Immediate Command | Transfers to mode after Signal Identification |  |
| OPMODE | O |  | immediate | ? | ? | ? | Immediate Command | Displays current PK-232 operating mode |  |
| OVER | OV |  | action_tx | ? | ? | ? | Immediate Command | Reverses the link direction in AMTOR and PACTOR |  |
| PACKET | PA |  | mode | ? | ? | ? | Immediate Command | Starts the Packet Mode |  |
| PACLEN | PACL |  | param | ? | ? | ? | 128 | Sets the number user data bytes in a packet |  |
| PACTIME | PACT |  | param | ? | ? | ? | AFTER 10 | Sets the Packet automatic transmit timer |  |
| PACTOR | PACT |  | mode | ? | ? | ? | Immediate Command | Enters the Pactor mode (PT for short) |  |
| PARITY | PAR |  | param | ? | ? | ? | 3 (even) | Sets the terminal program parity (0-3) |  |
| PASS | PAS |  | param | ? | ? | ? | $16 <CTRL-V> | Sets the converse mode pass character |  |
| PASSALL | PASSA |  | param | ? | ? | ? | OFF | Ignores CRC in receiving packets (Junk mode) |  |
| PERSIST | PE |  | param | ? | ? | ? | 63 | Sets the P-persistent CSMA threshold |  |
| PK | PK |  | param | ? | ? | ? | none | A hex value used to access the PK-232s memory |  |
| PPERSIST | PP |  | param | ? | ? | ? | 014 | Selects P-persistent CSMA operation |  |
| PRCON | PRC |  | param | ? | ? | ? | OFF | Enables a parallel printer you have connected |  |
| PRFAX | PRF |  | param | ? | ? | ? | ON | Prints received FAX to parallel printer (source reads 'PAX' (OCR); corrected to 'FAX') |  |
| PROUT | PRO |  | param | ? | ? | ? | OFF | Sends all received data to parallel printer |  |
| PRTYPE | PRT |  | param | ? | ? | ? | 2 (Epson) | Sets the graphics emulation for FAX printing |  |
| PT200 | PT200 |  | param | ? | ? | ? | ON | Allows 200 bauds for Pactor if link is good |  |
| PTCONN | PTC |  | action_tx | ? | ? | ? | Immediate Command | Starts a Pactor connect with (CALLSIGN) |  |
| PTDOWN |  |  | param | ? | ? | ? |  |  (named in PK232PY (PACTOR mask, config); not in the Timewave list) |  |
| PTHUFF | PTH |  | param | ? | ? | ? | 0 | Selects Pactor data compression (0 = OFF) |  |
| PTLIST | PTL |  | mode | ? | ? | ? | Immediate Command | Starts the Pactor Listen mode |  |
| PTOVER | PTO |  | param | ? | ? | ? | $1A <CTRL-Z> | Sets the Pactor link direction change character |  |
| PTROUND | PTR |  | param | ? | ? | ? | OFF | Returns the TNC to the PACTOR-Standby mode or not |  |
| PTSEND | PTS |  | action_tx | ? | ? | ? | Immediate Command | Starts the Pactor unproto send mode (call CQ) |  |
| PTSUM |  |  | param | ? | ? | ? |  |  (named in PK232PY (PACTOR mask, config); not in the Timewave list) |  |
| PTTRIES |  |  | param | ? | ? | ? |  |  (named in PK232PY (PACTOR mask, config); not in the Timewave list) |  |
| PTUP |  |  | param | ? | ? | ? |  |  (named in PK232PY (PACTOR mask, config); not in the Timewave list) |  |
| QHPACKET |  |  | param | ? | ? | ? |  |  (read-only field of a PK232PY mask; whether a command of this name exists is unmeasured) |  |
| QMORSE |  |  | param | ? | ? | ? |  |  (read-only field of a PK232PY mask; whether a command of this name exists is unmeasured) |  |
| QPTOR |  |  | param | ? | ? | ? |  |  (read-only field of a PK232PY mask; whether a command of this name exists is unmeasured) |  |
| QRTTY |  |  | param | ? | ? | ? |  |  (read-only field of a PK232PY mask; whether a command of this name exists is unmeasured) |  |
| QTDM |  |  | param | ? | ? | ? |  |  (read-only field of a PK232PY mask; whether a command of this name exists is unmeasured) |  |
| QTOR |  |  | param | ? | ? | ? |  |  (read-only field of a PK232PY mask; whether a command of this name exists is unmeasured) |  |
| QVPACKET |  |  | param | ? | ? | ? |  |  (read-only field of a PK232PY mask; whether a command of this name exists is unmeasured) |  |
| QWIDE |  |  | param | ? | ? | ? |  |  (read-only field of a PK232PY mask; whether a command of this name exists is unmeasured) |  |
| RADIO | RA |  | param | ? | ? | ? | 1 | ??? (source gives only '???' as the function) |  |
| RAWHDLC | RAW |  | param | ? | ? | ? | OFF | Starts Raw HDLC mode |  |
| RBAUD | RB |  | param | ? | ? | ? | 45 bauds (60 WPM) | Sets the Baudot RTTY baud rate selection |  |
| RCVE | R |  | mode | ? | ? | ? | Immediate Command | Selects the receive mode Morse/RTTY/AMTOR |  |
| RECEIVE | REC |  | param | ? | ? | ? | $04 <CTRL-D> | Selects the Receive character used in text |  |
| REDISPLAY | RED |  | param | ? | ? | ? | $12 <CTRL-R> | Re-displays current terminal input buffer (source name truncated to 8 characters (REDispla); the PK232PY mask label is REDISPLA) |  |
| REINIT | REINIT |  | danger | ? | ? | ? | Immediate Command | Re-initializes most of the commands to their default |  |
| RELINK | REL |  | param | ? | ? | ? | OFF | Re-connects after link fails due to retries |  |
| RESET | RESET |  | danger | ? | ? | ? | Immediate Command | RESETs PK-232 and bbRAM to factory defaults |  |
| RESPTIME | RES |  | param | ? | ? | ? | 0 | Sets the minimum delay before sending an ACK |  |
| RESTART | RESTART |  | danger | ? | ? | ? | Immediate Command | Restarts PK-232, same as turning power off/on |  |
| RETRY | RE |  | param | ? | ? | ? | 10 | Sets the maximum number of packet repeats |  |
| RFEC | RF |  | param | ? | ? | ? | ON | Receives FEC in AMTOR Standby |  |
| RFRAME | RFR |  | param | ? | ? | ? | OFF | Checks RTTY characters for framing errors |  |
| RXREV | RXR |  | param | ? | ? | ? | OFF | Reverses the received data mark-space sense |  |
| SAMPLE | SA |  | mode | ? | ? | ? | Immediate Command | Enters the raw data sampling mode |  |
| SELFEC | SEL |  | action_tx | ? | ? | ? | Immediate Command | Starts a selective FEC call with SELCAL |  |
| SENDPAC | SE |  | param | ? | ? | ? | $0D <CTRL-M> | Sets the converse mode "Send packet" character |  |
| SIGNAL | SI |  | mode | ? | ? | ? | Immediate Command | Starts the Signal Identification mode |  |
| SLOTTIME | SL |  | param | ? | ? | ? | 30 | Sets the P-persistent CSMA slot time |  |
| SPACE |  |  | param | ? | ? | ? |  |  (named in PK232PY (Misc mask, tone frequency); not in the Timewave list) |  |
| SQUELCH | SQ |  | param | ? | ? | ? | OFF | Sets the receiver squelch carrier polarity |  |
| SRXALL | SRX |  | param | ? | ? | ? | OFF | Allows reception of ALL received SELFEC calls |  |
| START | STA |  | param | ? | ? | ? | $11 <CTRL-Q> | Sets character to start sending terminal data |  |
| STOP | STO |  | param | ? | ? | ? | $13 <CTRL-S> | Sets character to stop sending terminal data (source reads 'sendina' (OCR); corrected to 'sending') |  |
| TBAUD | TB |  | param | ? | ? | ? | 1200 bauds | Sets the ASCII terminal data rate |  |
| TCLEAR | TC |  | immediate | ? | ? | ? | Immediate Command | Clears the transmit Buffer (Non-Packet modes) |  |
| TDBAUD | TDB |  | param | ? | ? | ? | 96 | Sets the receive data rate for TDM signals |  |
| TDCHAN | TDC |  | param | ? | ? | ? | 0 | Sets the receive channel for TDM signals |  |
| TDM | TD |  | mode | ? | ? | ? | Immediate Command | Enters the TDM receive mode |  |
| THRESHOLD |  |  | param | ? | ? | ? |  |  (named in PK232PY (Misc mask, read-only); not in the Timewave list) |  |
| TIME | TI |  | param | ? | ? | ? | $14 <CTRL-T> | Inserts the time (in DAYTIME) in text (source reads 'S14' (OCR); corrected to '$14') |  |
| TMAIL | TM |  | param | ? | ? | ? | OFF | Enables AMTOR and Pactor Maildrop |  |
| TMPROMPT | TMP |  | param | ? | ? | ? | (see text) | Sets an 80 character AMTOR Maildrop Message |  |
| TRACE | TRAC |  | param | ? | ? | ? | OFF | Enables a Hex dump of received data |  |
| TRANS | T |  | danger | ? | ? | ? | Immediate Command | Enters the Transparent data mode (leaves the command mode - never auto (CLAUDE.md rule 8)) |  |
| TRFLOW | TRF |  | param | ? | ? | ? | OFF | Enables software flow control RX in Trans. |  |
| TRIES | TRI |  | param | ? | ? | ? | 0 (zero) | Displays or forces packet retry counter |  |
| TXDELAY | TX |  | param | ? | ? | ? | 30 | Sets the PTT key-to-data delay (×10 ms) |  |
| TXFLOW | TXF |  | param | ? | ? | ? | OFF | Enables software flow control TX in Trans. |  |
| TXREV | TX |  | param | ? | ? | ? | OFF | Reverses transmitted mark-space data sense |  |
| TXSMT |  |  | param | ? | ? | ? |  |  (named in PK232PY (Packet mask, disabled); P13: not in the TRM Host Mode list, probably another AEA product) |  |
| UBIT | UB |  | param | ? | ? | ? | 0 | Controls seldom used ON/OFF commands |  |
| UCMD | UC |  | param | ? | ? | ? | 0 | Controls seldom used numeric commands |  |
| UNPROTO | U |  | param | ? | ? | ? | CQ | Sets the UI packet frame sending Path/address |  |
| USERS | US |  | param | ? | ? | ? | 1 | Sets allowed number of packet multi-connects |  |
| USOS | USO |  | param | ? | ? | ? | OFF | Sets RTTY 'unshift on space' |  |
| VHF | V |  | param | ? | ? | ? | ON | Selects VHF Packet - wide (1000 Hz) shift |  |
| WHYNOT | WHY |  | param | ? | ? | ? | OFF | Displays reason why packet not displayed |  |
| WIDESHFT | WI |  | param | ? | ? | ? | OFF | Selects RTTY wide or narrow (200 Hz) shift |  |
| WORDOUT | WO |  | param | ? | ? | ? | OFF | Sets Word output in RTTY/AMTOR/Pactor modes |  |
| WRU | WR |  | param | ? | ? | ? | OFF | Enables auto-answerback (AAB) in RTTY/ASCII |  |
| XBAUD | XB |  | param | ? | ? | ? | 0 | Sets 8530 baud rate to receive Baudot/ASCII |  |
| XFLOW | XF |  | param | ? | ? | ? | ON | Sets Software (XON/XOFF) RS-232 flow control |  |
| XGATEWAY |  |  | param | ? | ? | ? |  |  (named in PK232PY (PACTOR mask); not in the Timewave list) |  |
| XLENGTH |  |  | param | ? | ? | ? |  |  (named in PK232PY (AMTOR and Baudot masks); not in the Timewave list) |  |
| XMIT | X |  | action_tx | ? | ? | ? | Immediate Command | Starts sending Baudot/Morse/FAX transmission |  |
| XMITOK | XMITO |  | param | ? | ? | ? | ON | Allows transmitter PTT line to be keyed |  |
| XOFF | XO |  | param | ? | ? | ? | $13 <CTRL-S> | Sets character to stop sending received data |  |
| XON | XON |  | param | ? | ? | ? | $11 <CTRL-Q> | Sets character to start sending received data |  |
| ZFREE | ZF |  | immediate | ? | ? | ? | Immediate Command | Returns number of blocks of available memory |  |
| ZSTATUS | ZS |  | immediate | ? | ? | ? | Immediate Command | Returns status of several internal parameters |  |
