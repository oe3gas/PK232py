# Note on `pk232_mnemonic_table.txt`

`pk232_mnemonic_table.txt` is a historical attempt at a Host Mode
mnemonic scan of a real PK-232MBX — its "KNOWN NAME" column is a
name-to-mnemonic mapping (most likely transcribed from TRM 4.2.2), not a
device response. The scan itself failed: of 676 mnemonic combinations
queried, only `AC` and `AD` ever answered, both with an error code, so
the file is **not** hardware evidence for any mnemonic in it (P13/P14
described it as one — a specification error, corrected in P20). For an
actual hardware-confirmed mnemonic, see the "Hardware-confirmed Host Mode
mnemonics" table in `CLAUDE.md`'s "TNC / firmware v7.1" gotchas, or run
`tools/hw_check.py` against the real TNC.
