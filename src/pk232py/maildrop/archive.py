# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""MailDrop local archive (P38) — a durable PC-side record of MailDrop
messages, independent of the TNC's own volatile mailbox.

The PK-232 has no RAM buffer battery (CLAUDE.md): every message and
message number is lost on power-off, and the mailbox is reachable only
through a MDCHECK session that also suspends packet operation for its
whole duration (docs/P38_MailDrop_Archive_Spec.md). This module is
therefore deliberately narrow — it is ONLY the local store and the
config that controls it (P38.1). It does not:

  - collect or restore anything automatically
  - know about MailDropSession, SerialManager, or Qt at all
  - have any UI beyond the settings section (params_maildrop.py)

Replaces message_store.py (deleted, P27.3 finding: that schema had no
TNC message number, no @BBS, no P/T/B type, and stored the LOCAL
receipt timestamp instead of the TNC's own store-time stamp — it did
not match what a real archive needs).
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from pk232py.config import MailDropConfig
    from .protocol import MailDropEntry

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 1

_CREATE_META = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
)
"""

_CREATE_MESSAGES = """
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT    UNIQUE NOT NULL,
    mtype       TEXT    NOT NULL,
    read_flag   INTEGER NOT NULL DEFAULT 0,
    to_call     TEXT    NOT NULL,
    from_call   TEXT    NOT NULL,
    bbs         TEXT    NOT NULL DEFAULT '',
    tnc_stamp   TEXT,
    size        INTEGER NOT NULL DEFAULT 0,
    subject     TEXT    NOT NULL DEFAULT '',
    body        TEXT    NOT NULL DEFAULT '',
    archived_at TEXT    NOT NULL,
    tnc_number  INTEGER,
    device      TEXT
)
"""


def _fingerprint(
    mtype: str, to_call: str, from_call: str, bbs: str, subject: str, body: str,
) -> str:
    """Duplicate-detection key (P38): a hash over everything that makes a
    message unique EXCEPT the TNC timestamp, which is set at store time
    and would differ after a restore-then-collect round trip — without
    this exclusion, the same message would be archived twice. Uses
    \\x1f (unit separator) between fields so no field's own content can
    forge a collision by shifting a delimiter.
    """
    parts = [mtype, to_call, from_call, bbs, subject, body]
    joined = "\x1f".join(parts)
    return hashlib.sha256(joined.encode("utf-8", errors="replace")).hexdigest()


@dataclass(frozen=True)
class ArchivedMessage:
    """One row of the local archive (P38) — the schema in
    docs/P38_MailDrop_Archive_Spec.md P38.2."""
    id:          int
    fingerprint: str
    mtype:       str
    read_flag:   bool
    to_call:     str
    from_call:   str
    bbs:         str
    tnc_stamp:   Optional[str]
    size:        int
    subject:     str
    body:        str
    archived_at: str
    tnc_number:  Optional[int]
    device:      Optional[str]


class MailDropArchive:
    """SQLite-backed local MailDrop archive.

    No Qt, no serial I/O — reads and writes a local file only, fully
    testable without hardware. Opening (the constructor) always creates
    the file if it does not already exist; callers that must NOT create
    a file when archiving is disabled should use open_archive() instead
    of constructing this directly.
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_CREATE_META)
        self._conn.execute(_CREATE_MESSAGES)
        self._conn.execute(
            "INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', ?)",
            (str(_SCHEMA_VERSION),),
        )
        self._conn.commit()
        logger.info("MailDropArchive opened: %s", self._path)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "MailDropArchive":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add(
        self, entry: "MailDropEntry", body: str, device: Optional[str] = None,
    ) -> tuple[int, bool]:
        """Store one message (a parsed listing row + its body text, as
        MailDropSession's own message_read signal delivers them).

        *body* is expected already stripped of the trailing '/E' line,
        same as MailDropSession/parse_read() already does (CLAUDE.md).
        *device* is the TNC's firmware release string
        (SerialManager.tnc_release), if known.

        Returns (id, is_new) — is_new is False when the same fingerprint
        was already archived, in which case the EXISTING row's id is
        returned and nothing is written again.
        """
        fingerprint = _fingerprint(
            entry.mtype, entry.to, entry.frm, entry.bbs, entry.title, body,
        )
        existing = self._conn.execute(
            "SELECT id FROM messages WHERE fingerprint=?", (fingerprint,)
        ).fetchone()
        if existing is not None:
            return existing["id"], False

        archived_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        cur = self._conn.execute(
            """INSERT INTO messages
               (fingerprint, mtype, read_flag, to_call, from_call, bbs,
                tnc_stamp, size, subject, body, archived_at, tnc_number,
                device)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                fingerprint, entry.mtype, int(entry.read), entry.to,
                entry.frm, entry.bbs, entry.stamp, entry.size, entry.title,
                body, archived_at, entry.number, device,
            ),
        )
        self._conn.commit()
        logger.info(
            "MailDropArchive: stored id=%d from=%s subject=%r",
            cur.lastrowid, entry.frm, entry.title,
        )
        return cur.lastrowid, True

    def mark_read(self, archive_id: int) -> None:
        self._conn.execute(
            "UPDATE messages SET read_flag=1 WHERE id=?", (archive_id,)
        )
        self._conn.commit()

    def delete(self, archive_id: int) -> None:
        self._conn.execute("DELETE FROM messages WHERE id=?", (archive_id,))
        self._conn.commit()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def all(self) -> list[ArchivedMessage]:
        rows = self._conn.execute(
            "SELECT * FROM messages ORDER BY archived_at DESC"
        ).fetchall()
        return [self._row_to_msg(r) for r in rows]

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]

    def missing_in_tnc(
        self, current: Sequence[tuple["MailDropEntry", str]],
    ) -> list[ArchivedMessage]:
        """Archived messages whose fingerprint is absent from *current*
        — i.e. messages this archive has that the mailbox no longer does
        (killed, or lost to a power-cycle), compared by fingerprint,
        NEVER by TNC message number (the TNC renumbers from 1 after
        every power-off, CLAUDE.md).

        *current* is (entry, body) pairs, matching add()'s own
        arguments — a bare listing (MailDropEntry only, no body) cannot
        reproduce the same fingerprint, since the fingerprint covers the
        body text too.
        """
        current_fps = {
            _fingerprint(e.mtype, e.to, e.frm, e.bbs, e.title, body)
            for e, body in current
        }
        return [m for m in self.all() if m.fingerprint not in current_fps]

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_msg(row: sqlite3.Row) -> ArchivedMessage:
        return ArchivedMessage(
            id          = row["id"],
            fingerprint = row["fingerprint"],
            mtype       = row["mtype"],
            read_flag   = bool(row["read_flag"]),
            to_call     = row["to_call"],
            from_call   = row["from_call"],
            bbs         = row["bbs"] or "",
            tnc_stamp   = row["tnc_stamp"],
            size        = row["size"],
            subject     = row["subject"] or "",
            body        = row["body"] or "",
            archived_at = row["archived_at"],
            tnc_number  = row["tnc_number"],
            device      = row["device"],
        )


RESTORE_SCOPES = ("all", "unread", "none")


def filter_restore_scope(
    messages: Sequence[ArchivedMessage], scope: str,
) -> list[ArchivedMessage]:
    """Narrow *messages* (archive-only candidates) to what
    MailDropConfig.archive_restore_scope (P59) actually permits
    restoring: 'all' -> unchanged, 'unread' -> only messages whose
    read_flag was False AT ARCHIVING TIME (P60, B.3, correcting an
    earlier version of this docstring: 'unread' uses the read flag as
    the TNC listed it when the message was archived. mark_read() is not
    called anywhere yet, so a message read later inside PK232PY stays
    'unread' here — that is a real, working filter, not a no-op; see
    test_maildrop_archive.py::test_unread_excludes_the_read_flag),
    'none' -> always []. An unknown scope
    raises ValueError rather than silently falling back to 'all' — a
    typo'd or future config value must not restore more than the
    operator asked for.

    Used both by the manual "Restore to TNC" button and by the automatic
    restore-after-power-on trigger (P59), so the two can never disagree
    about what "restore scope X" means.
    """
    if scope == "all":
        return list(messages)
    if scope == "unread":
        return [m for m in messages if not m.read_flag]
    if scope == "none":
        return []
    raise ValueError(f"unknown restore scope: {scope!r}")


def open_archive(config: "MailDropConfig") -> Optional[MailDropArchive]:
    """Open the local archive per *config* (MailDropConfig, P38.1), or
    return None without ever creating a database file when
    archive_enabled is False — the "nothing happens automatically unless
    the user turned it on" rule this whole package is built around
    (docs/P38_MailDrop_Archive_Spec.md, "Warum optional").
    """
    if not config.archive_enabled:
        return None
    return MailDropArchive(Path(config.archive_path).expanduser())
