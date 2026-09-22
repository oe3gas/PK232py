# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""Message Store — SQLite-backed MailDrop message storage.

Stores messages received via the TNC MailDrop in a local SQLite
database.  Messages can be listed, read, deleted and exported.

Database location: ~/.pk232py/maildrop.db

Schema
------
Table: messages
  id          INTEGER PRIMARY KEY AUTOINCREMENT
  from_call   TEXT    NOT NULL    — sender callsign
  to_call     TEXT    NOT NULL    — recipient callsign (usually MYMAIL)
  subject     TEXT                — message subject
  body        TEXT                — message body
  received_at TEXT    NOT NULL    — UTC timestamp (YYYY-MM-DD HH:MM:SS)
  read        INTEGER DEFAULT 0   — 0=unread, 1=read
  forwarded   INTEGER DEFAULT 0   — 0=not forwarded, 1=forwarded
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DB_FILE = Path.home() / ".pk232py" / "maildrop.db"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    from_call   TEXT    NOT NULL,
    to_call     TEXT    NOT NULL,
    subject     TEXT    DEFAULT '',
    body        TEXT    DEFAULT '',
    received_at TEXT    NOT NULL,
    read        INTEGER DEFAULT 0,
    forwarded   INTEGER DEFAULT 0
)
"""


@dataclass
class MailMessage:
    """A single MailDrop message."""
    id:          Optional[int] = None
    from_call:   str  = ""
    to_call:     str  = ""
    subject:     str  = ""
    body:        str  = ""
    received_at: str  = ""
    read:        bool = False
    forwarded:   bool = False

    @property
    def is_unread(self) -> bool:
        return not self.read

    def __str__(self) -> str:
        return (f"[{self.id}] From:{self.from_call} To:{self.to_call} "
                f"{'(unread)' if self.is_unread else ''} — {self.subject}")


class MessageStore:
    """SQLite-backed MailDrop message store.

    Usage::

        store = MessageStore()
        store.open()
        msg_id = store.add_message('W1AW', 'OE3GAS',
                                   subject='Test', body='Hello!')
        store.mark_read(msg_id)
        store.close()
    """

    def __init__(self, path: Path = DB_FILE) -> None:
        self._path = path
        self._conn: Optional[sqlite3.Connection] = None

    def open(self) -> None:
        """Open (or create) the message database."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_CREATE_TABLE)
        self._conn.commit()
        logger.info("MessageStore opened: %s", self._path)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "MessageStore":
        self.open(); return self

    def __exit__(self, *_) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add_message(
        self,
        from_call: str,
        to_call:   str,
        subject:   str = "",
        body:      str = "",
    ) -> int:
        """Store a new incoming message.

        Returns:
            The id of the new message.
        """
        self._require_open()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        cur = self._conn.execute(
            """INSERT INTO messages
               (from_call, to_call, subject, body, received_at)
               VALUES (?,?,?,?,?)""",
            (from_call.upper(), to_call.upper(), subject, body, now),
        )
        self._conn.commit()
        msg_id = cur.lastrowid
        logger.info("Message stored: id=%d from=%s", msg_id, from_call.upper())
        return msg_id

    def mark_read(self, msg_id: int) -> None:
        """Mark a message as read."""
        self._require_open()
        self._conn.execute(
            "UPDATE messages SET read=1 WHERE id=?", (msg_id,)
        )
        self._conn.commit()

    def mark_forwarded(self, msg_id: int) -> None:
        """Mark a message as forwarded."""
        self._require_open()
        self._conn.execute(
            "UPDATE messages SET forwarded=1 WHERE id=?", (msg_id,)
        )
        self._conn.commit()

    def delete_message(self, msg_id: int) -> None:
        """Delete a message by id."""
        self._require_open()
        self._conn.execute("DELETE FROM messages WHERE id=?", (msg_id,))
        self._conn.commit()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_message(self, msg_id: int) -> Optional[MailMessage]:
        """Fetch a message by id."""
        self._require_open()
        row = self._conn.execute(
            "SELECT * FROM messages WHERE id=?", (msg_id,)
        ).fetchone()
        return self._row_to_msg(row) if row else None

    def list_messages(
        self,
        to_call:   Optional[str] = None,
        unread_only: bool = False,
        limit:     int   = 50,
    ) -> list[MailMessage]:
        """List messages with optional filters, newest first."""
        self._require_open()
        where, params = [], []
        if to_call:
            where.append("to_call=?")
            params.append(to_call.upper())
        if unread_only:
            where.append("read=0")
        sql = "SELECT * FROM messages"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY received_at DESC LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_msg(r) for r in rows]

    def unread_count(self) -> int:
        """Return the number of unread messages."""
        self._require_open()
        return self._conn.execute(
            "SELECT COUNT(*) FROM messages WHERE read=0"
        ).fetchone()[0]

    def total_count(self) -> int:
        """Return total number of stored messages."""
        self._require_open()
        return self._conn.execute(
            "SELECT COUNT(*) FROM messages"
        ).fetchone()[0]

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _require_open(self) -> None:
        if self._conn is None:
            raise RuntimeError("MessageStore is not open")

    @staticmethod
    def _row_to_msg(row: sqlite3.Row) -> MailMessage:
        return MailMessage(
            id          = row["id"],
            from_call   = row["from_call"],
            to_call     = row["to_call"],
            subject     = row["subject"] or "",
            body        = row["body"] or "",
            received_at = row["received_at"],
            read        = bool(row["read"]),
            forwarded   = bool(row["forwarded"]),
        )