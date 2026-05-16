from __future__ import annotations

import hashlib
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created REAL NOT NULL,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT,
    image_path TEXT,
    thumb_path TEXT,
    pinned INTEGER NOT NULL DEFAULT 0,
    content_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entries_created ON entries(created DESC);
CREATE INDEX IF NOT EXISTS idx_entries_pinned ON entries(pinned);
"""


@dataclass(frozen=True, slots=True)
class ClipEntry:
    id: int
    created: float
    kind: str
    title: str
    body: str | None
    image_path: str | None
    thumb_path: str | None
    pinned: bool
    content_hash: str


class Database:
    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            try:
                conn.execute("ALTER TABLE entries ADD COLUMN thumb_path TEXT")
            except sqlite3.OperationalError:
                pass

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._path, timeout=30)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            yield conn
            conn.commit()
        finally:
            conn.close()

    def insert(
        self,
        *,
        kind: str,
        title: str,
        body: str | None,
        image_path: str | None,
        content_hash: str,
        thumb_path: str | None = None,
        pinned: bool = False,
    ) -> int:
        now = time.time()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO entries (created, kind, title, body, image_path, thumb_path, pinned, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now,
                    kind,
                    title,
                    body,
                    image_path,
                    thumb_path,
                    1 if pinned else 0,
                    content_hash,
                ),
            )
            return int(cur.lastrowid)

    def exists_hash(self, content_hash: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM entries WHERE content_hash = ? LIMIT 1",
                (content_hash,),
            ).fetchone()
            return row is not None

    def touch_hash(self, content_hash: str) -> None:
        now = time.time()
        with self.connect() as conn:
            conn.execute(
                "UPDATE entries SET created = ? WHERE content_hash = ?",
                (now, content_hash),
            )

    def list_entries(self, limit: int = 500) -> list[ClipEntry]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, created, kind, title, body, image_path, thumb_path, pinned, content_hash
                FROM entries
                ORDER BY pinned DESC, created DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_row_to_entry(r) for r in rows]

    def search_entries(self, query: str, limit: int = 500) -> list[ClipEntry]:
        q = query.strip()
        if not q:
            return self.list_entries(limit=limit)
        pattern = f"%{_escape_like(q)}%"
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, created, kind, title, body, image_path, thumb_path, pinned, content_hash
                FROM entries
                WHERE title LIKE ? ESCAPE '\\'
                   OR IFNULL(body, '') LIKE ? ESCAPE '\\'
                   OR kind LIKE ? ESCAPE '\\'
                ORDER BY pinned DESC, created DESC
                LIMIT ?
                """,
                (pattern, pattern, pattern, limit),
            ).fetchall()
        return [_row_to_entry(r) for r in rows]

    def get(self, entry_id: int) -> ClipEntry | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id, created, kind, title, body, image_path, thumb_path, pinned, content_hash
                FROM entries WHERE id = ?
                """,
                (entry_id,),
            ).fetchone()
        return _row_to_entry(row) if row else None

    def set_pinned(self, entry_id: int, pinned: bool) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE entries SET pinned = ? WHERE id = ?",
                (1 if pinned else 0, entry_id),
            )

    def delete(self, entry_id: int) -> None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT image_path, thumb_path FROM entries WHERE id = ?", (entry_id,)
            ).fetchone()
            if row:
                for key in ("image_path", "thumb_path"):
                    if row[key]:
                        p = Path(row[key])
                        try:
                            p.unlink(missing_ok=True)
                        except OSError:
                            pass
            conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))

    def prune(self, max_entries: int) -> None:
        with self.connect() as conn:
            try:
                conn.execute(
                    """
                    DELETE FROM entries
                    WHERE id IN (
                        SELECT id FROM (
                            SELECT id, pinned,
                                   ROW_NUMBER() OVER (
                                       ORDER BY pinned DESC, created DESC
                                   ) AS rn
                            FROM entries
                        )
                        WHERE rn > ?
                    )
                    """,
                    (max_entries,),
                )
            except sqlite3.OperationalError:
                rows = conn.execute(
                    """
                    SELECT id FROM entries
                    ORDER BY pinned DESC, created DESC
                    """
                ).fetchall()
                if len(rows) <= max_entries:
                    return
                for row in rows[max_entries:]:
                    conn.execute("DELETE FROM entries WHERE id = ?", (row[0],))


def _row_to_entry(row: sqlite3.Row) -> ClipEntry:
    return ClipEntry(
        id=int(row["id"]),
        created=float(row["created"]),
        kind=str(row["kind"]),
        title=str(row["title"]),
        body=row["body"],
        image_path=row["image_path"],
        thumb_path=row["thumb_path"],
        pinned=bool(int(row["pinned"])),
        content_hash=str(row["content_hash"]),
    )


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def stable_hash(parts: list[bytes]) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p)
        h.update(b"\x1e")
    return h.hexdigest()
