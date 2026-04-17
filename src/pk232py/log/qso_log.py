# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""QSO Log — SQLite-based contact logging.

Stores QSO (contact) records in a local SQLite database.
Each record captures the essential data for a radio contact:
callsign, frequency, mode, date/time (UTC), RST sent/received,
and optional free-text notes.

Database location: ~/.pk232py/qso_log.db

Schema
------
Table: qsos
  id          INTEGER PRIMARY KEY AUTOINCREMENT
  callsign    TEXT    NOT NULL        — remote station callsign
  frequency   REAL                   — frequency in kHz
  mode        TEXT                   — operating mode (HF Packet, PACTOR, …)
  date_on     TEXT    NOT NULL        — QSO start UTC date (YYYY-MM-DD)
  time_on     TEXT    NOT NULL        — QSO start UTC time (HH:MM:SS)
  date_off    TEXT                   — QSO end UTC date
  time_off    TEXT                   — QSO end UTC time
  rst_sent    TEXT    DEFAULT '599'  — RST sent
  rst_rcvd    TEXT    DEFAULT '599'  — RST received
  name        TEXT                   — operator name
  qth         TEXT                   — location
  notes       TEXT                   — free text
  created_at  TEXT    NOT NULL        — record creation timestamp

Usage::

    log = QSOLog()
    log.open()
    qso_id = log.add_qso(callsign='OE3XYZ', frequency=14085.0, mode='HF Packet')
    log.update_qso(qso_id, rst_sent='599', rst_rcvd='579', name='Hans')
    log.close_qso(qso_id)
    records = log.search(callsign='OE3XYZ')
    log.close()
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DB_FILE = Path.home() / ".pk232py" / "qso_log.db"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS qsos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    callsign    TEXT    NOT NULL,
    frequency   REAL,
    mode        TEXT,
    date_on     TEXT    NOT NULL,
    time_on     TEXT    NOT NULL,
    date_off    TEXT,
    time_off    TEXT,
    rst_sent    TEXT    DEFAULT '599',
    rst_rcvd    TEXT    DEFAULT '599',
    name        TEXT,
    qth         TEXT,
    notes       TEXT,
    created_at  TEXT    NOT NULL
)
"""


# ---------------------------------------------------------------------------
# QSO record dataclass
# ---------------------------------------------------------------------------

@dataclass
class QSORecord:
    """A single QSO (radio contact) record."""
    id:         Optional[int] = None
    callsign:   str           = ""
    frequency:  Optional[float] = None    # kHz
    mode:       str           = ""
    date_on:    str           = ""        # YYYY-MM-DD UTC
    time_on:    str           = ""        # HH:MM:SS UTC
    date_off:   Optional[str] = None
    time_off:   Optional[str] = None
    rst_sent:   str           = "599"
    rst_rcvd:   str           = "599"
    name:       str           = ""
    qth:        str           = ""
    notes:      str           = ""
    created_at: str           = ""

    @property
    def is_closed(self) -> bool:
        """True if the QSO has an end time."""
        return self.date_off is not None and self.time_off is not None

    @property
    def duration_minutes(self) -> Optional[float]:
        """QSO duration in minutes, or None if not closed."""
        if not self.is_closed:
            return None
        try:
            fmt = "%Y-%m-%d %H:%M:%S"
            t_on  = datetime.strptime(f"{self.date_on} {self.time_on}",  fmt)
            t_off = datetime.strptime(f"{self.date_off} {self.time_off}", fmt)
            return (t_off - t_on).total_seconds() / 60
        except ValueError:
            return None


# ---------------------------------------------------------------------------
# QSOLog
# ---------------------------------------------------------------------------

class QSOLog:
    """SQLite-backed QSO log.

    Args:
        path: Path to the SQLite database file.
              Defaults to ``~/.pk232py/qso_log.db``.

    Usage::

        log = QSOLog()
        log.open()
        try:
            qso_id = log.add_qso('OE3XYZ', frequency=14085.0, mode='PACTOR')
            log.close_qso(qso_id)
        finally:
            log.close()
    """

    def __init__(self, path: Path = DB_FILE) -> None:
        self._path = path
        self._conn: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Open (or create) the database and ensure the schema exists."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_CREATE_TABLE)
        self._conn.commit()
        logger.info("QSO log opened: %s", self._path)

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.info("QSO log closed")

    def __enter__(self) -> "QSOLog":
        self.open()
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def add_qso(
        self,
        callsign:  str,
        frequency: Optional[float] = None,
        mode:      str  = "",
        rst_sent:  str  = "599",
        rst_rcvd:  str  = "599",
        name:      str  = "",
        qth:       str  = "",
        notes:     str  = "",
    ) -> int:
        """Add a new QSO record with the current UTC time as start time.

        Args:
            callsign:  Remote station callsign (required).
            frequency: Frequency in kHz (optional).
            mode:      Operating mode string, e.g. ``"HF Packet"``.
            rst_sent:  RST sent (default ``"599"``).
            rst_rcvd:  RST received (default ``"599"``).
            name:      Operator name (optional).
            qth:       Location (optional).
            notes:     Free-text notes (optional).

        Returns:
            The ``id`` of the newly created record.
        """
        self._require_open()
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")
        created  = now.strftime("%Y-%m-%d %H:%M:%S")

        cur = self._conn.execute(
            """INSERT INTO qsos
               (callsign, frequency, mode, date_on, time_on,
                rst_sent, rst_rcvd, name, qth, notes, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (callsign.upper(), frequency, mode,
             date_str, time_str,
             rst_sent, rst_rcvd, name, qth, notes, created),
        )
        self._conn.commit()
        qso_id = cur.lastrowid
        logger.info("QSO added: id=%d %s", qso_id, callsign.upper())
        return qso_id

    def close_qso(self, qso_id: int) -> None:
        """Set the end time of a QSO to the current UTC time.

        Args:
            qso_id: Record id returned by :meth:`add_qso`.
        """
        self._require_open()
        now = datetime.now(timezone.utc)
        self._conn.execute(
            "UPDATE qsos SET date_off=?, time_off=? WHERE id=?",
            (now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), qso_id),
        )
        self._conn.commit()
        logger.info("QSO closed: id=%d", qso_id)

    def update_qso(self, qso_id: int, **kwargs) -> None:
        """Update fields of an existing QSO record.

        Accepted keyword arguments: ``callsign``, ``frequency``, ``mode``,
        ``rst_sent``, ``rst_rcvd``, ``name``, ``qth``, ``notes``.

        Args:
            qso_id: Record id to update.
            **kwargs: Field name → new value pairs.
        """
        self._require_open()
        allowed = {
            "callsign", "frequency", "mode",
            "rst_sent", "rst_rcvd", "name", "qth", "notes",
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        if "callsign" in updates:
            updates["callsign"] = updates["callsign"].upper()
        set_clause = ", ".join(f"{k}=?" for k in updates)
        values = list(updates.values()) + [qso_id]
        self._conn.execute(
            f"UPDATE qsos SET {set_clause} WHERE id=?", values
        )
        self._conn.commit()
        logger.debug("QSO updated: id=%d fields=%s", qso_id, list(updates))

    def delete_qso(self, qso_id: int) -> None:
        """Delete a QSO record by id."""
        self._require_open()
        self._conn.execute("DELETE FROM qsos WHERE id=?", (qso_id,))
        self._conn.commit()
        logger.info("QSO deleted: id=%d", qso_id)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_qso(self, qso_id: int) -> Optional[QSORecord]:
        """Fetch a single QSO record by id.

        Returns:
            :class:`QSORecord` or ``None`` if not found.
        """
        self._require_open()
        row = self._conn.execute(
            "SELECT * FROM qsos WHERE id=?", (qso_id,)
        ).fetchone()
        return self._row_to_record(row) if row else None

    def search(
        self,
        callsign:   Optional[str]   = None,
        mode:       Optional[str]   = None,
        date_from:  Optional[str]   = None,   # YYYY-MM-DD
        date_to:    Optional[str]   = None,   # YYYY-MM-DD
        limit:      int             = 100,
    ) -> list[QSORecord]:
        """Search QSO records with optional filters.

        Args:
            callsign:  Filter by callsign (case-insensitive, partial match).
            mode:      Filter by exact mode string.
            date_from: Filter records on or after this UTC date.
            date_to:   Filter records on or before this UTC date.
            limit:     Maximum number of records to return (default 100).

        Returns:
            List of :class:`QSORecord`, newest first.
        """
        self._require_open()
        where, params = [], []

        if callsign:
            where.append("callsign LIKE ?")
            params.append(f"%{callsign.upper()}%")
        if mode:
            where.append("mode=?")
            params.append(mode)
        if date_from:
            where.append("date_on >= ?")
            params.append(date_from)
        if date_to:
            where.append("date_on <= ?")
            params.append(date_to)

        sql = "SELECT * FROM qsos"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY date_on DESC, time_on DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_record(r) for r in rows]

    def recent(self, n: int = 20) -> list[QSORecord]:
        """Return the most recent *n* QSO records (newest first)."""
        return self.search(limit=n)

    def count(self) -> int:
        """Return the total number of QSO records in the log."""
        self._require_open()
        return self._conn.execute(
            "SELECT COUNT(*) FROM qsos"
        ).fetchone()[0]

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_adif(self, path: Path) -> int:
        """Export all QSO records to an ADIF file.

        ADIF (Amateur Data Interchange Format) is the standard format
        for exchanging QSO logs between amateur radio applications.

        Args:
            path: Output file path.

        Returns:
            Number of records exported.
        """
        self._require_open()
        records = self.search(limit=99999)
        lines = [
            "ADIF export from PK232PY\n",
            "<ADIF_VER:5>3.1.0\n",
            "<EOH>\n\n",
        ]
        for r in records:
            fields = [
                f"<CALL:{len(r.callsign)}>{r.callsign}",
                f"<QSO_DATE:8>{r.date_on.replace('-', '')}",
                f"<TIME_ON:6>{r.time_on.replace(':', '')}",
            ]
            if r.mode:
                fields.append(f"<MODE:{len(r.mode)}>{r.mode}")
            if r.frequency is not None:
                freq_mhz = f"{r.frequency / 1000:.4f}"
                fields.append(f"<FREQ:{len(freq_mhz)}>{freq_mhz}")
            if r.rst_sent:
                fields.append(f"<RST_SENT:{len(r.rst_sent)}>{r.rst_sent}")
            if r.rst_rcvd:
                fields.append(f"<RST_RCVD:{len(r.rst_rcvd)}>{r.rst_rcvd}")
            if r.name:
                fields.append(f"<NAME:{len(r.name)}>{r.name}")
            if r.qth:
                fields.append(f"<QTH:{len(r.qth)}>{r.qth}")
            if r.notes:
                fields.append(f"<COMMENT:{len(r.notes)}>{r.notes}")
            lines.append(" ".join(fields) + " <EOR>\n")

        path.write_text("".join(lines), encoding="utf-8")
        logger.info("ADIF export: %d records → %s", len(records), path)
        return len(records)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _require_open(self) -> None:
        if self._conn is None:
            raise RuntimeError("QSOLog is not open — call open() first")

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> QSORecord:
        return QSORecord(
            id         = row["id"],
            callsign   = row["callsign"],
            frequency  = row["frequency"],
            mode       = row["mode"] or "",
            date_on    = row["date_on"],
            time_on    = row["time_on"],
            date_off   = row["date_off"],
            time_off   = row["time_off"],
            rst_sent   = row["rst_sent"] or "599",
            rst_rcvd   = row["rst_rcvd"] or "599",
            name       = row["name"] or "",
            qth        = row["qth"] or "",
            notes      = row["notes"] or "",
            created_at = row["created_at"],
        )