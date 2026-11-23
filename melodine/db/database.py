"""SQLite persistence: track library, history, watchlist, queue state.

v1 databases (``downloads`` + ``sessions`` tables) are migrated in place:
every historical row survives, successful downloads are backfilled into the
new dedup-aware ``tracks`` library, and new tables are added alongside.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from melodine.core.logging import get_logger
from melodine.models import DownloadTask, WatchlistEntry

logger = get_logger("db")

SCHEMA_VERSION = 20


def _now() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


class Database:
    """Thread-safe SQLite wrapper with idempotent v1 -> v2 migration."""

    def __init__(self, path: str | Path = "melodine.db") -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            str(self.path), check_same_thread=False, timeout=15.0
        )
        self._conn.row_factory = sqlite3.Row
        with contextlib.suppress(sqlite3.DatabaseError):  # exotic filesystems
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    # ------------------------------------------------------------------ #
    # migration
    # ------------------------------------------------------------------ #

    def _migrate(self) -> None:
        with self._lock, self._conn:
            existing = {
                row["name"]
                for row in self._conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }

            # --- v1 `downloads` table: extend or create ---
            if "downloads" in existing:
                columns = {
                    row["name"]
                    for row in self._conn.execute("PRAGMA table_info(downloads)")
                }
                if "source_id" not in columns:
                    self._conn.execute(
                        "ALTER TABLE downloads ADD COLUMN source_id TEXT DEFAULT ''"
                    )
                if "message" not in columns:
                    self._conn.execute(
                        "ALTER TABLE downloads ADD COLUMN message TEXT DEFAULT ''"
                    )
                if "duration" not in columns:
                    self._conn.execute(
                        "ALTER TABLE downloads ADD COLUMN duration REAL DEFAULT 0"
                    )
            else:
                self._conn.execute(
                    """
                    CREATE TABLE downloads (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        query TEXT NOT NULL,
                        artist TEXT DEFAULT '',
                        title TEXT DEFAULT '',
                        status TEXT NOT NULL,
                        attempts INTEGER DEFAULT 1,
                        file_path TEXT DEFAULT '',
                        file_size INTEGER DEFAULT 0,
                        duration REAL DEFAULT 0,
                        downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        source_id TEXT DEFAULT '',
                        message TEXT DEFAULT ''
                    )
                    """
                )

            # --- v1 `sessions` table: keep untouched ---
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    playlist_file TEXT,
                    total_tracks INTEGER DEFAULT 0,
                    success INTEGER DEFAULT 0,
                    failed INTEGER DEFAULT 0,
                    skipped INTEGER DEFAULT 0,
                    total_size INTEGER DEFAULT 0,
                    duration_seconds REAL DEFAULT 0,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # --- v2 library ---
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tracks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    artist TEXT NOT NULL DEFAULT '',
                    album TEXT DEFAULT '',
                    album_artist TEXT DEFAULT '',
                    genre TEXT DEFAULT '',
                    year INTEGER,
                    track_number INTEGER,
                    duration REAL DEFAULT 0,
                    normalized_artist TEXT NOT NULL DEFAULT '',
                    normalized_title TEXT NOT NULL DEFAULT '',
                    filepath TEXT NOT NULL DEFAULT '',
                    codec TEXT DEFAULT '',
                    bitrate INTEGER DEFAULT 0,
                    filesize INTEGER DEFAULT 0,
                    artwork INTEGER DEFAULT 0,
                    lyrics TEXT DEFAULT '',
                    normalized INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tracks_norm "
                "ON tracks(normalized_artist, normalized_title)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tracks_source ON tracks(source_id)"
            )

            # --- v2 watchlist ---
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS watchlist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE NOT NULL,
                    name TEXT DEFAULT '',
                    kind TEXT DEFAULT 'unknown',
                    playlist_path TEXT DEFAULT '',
                    last_synced_at TEXT DEFAULT '',
                    active INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS watchlist_items (
                    watchlist_id INTEGER NOT NULL,
                    source_id TEXT NOT NULL,
                    added_at TEXT NOT NULL,
                    UNIQUE (watchlist_id, source_id)
                )
                """
            )

            # --- v2 queue state (graceful shutdown persistence) ---
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS queue_state (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

            self._conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

        self._backfill_tracks_from_history()

    def _backfill_tracks_from_history(self) -> None:
        """Import successful v1 downloads into the v2 track library."""
        from melodine.services.dedup import normalize_name

        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, artist, title, file_path, file_size, duration, source_id
                FROM downloads
                WHERE status = 'success'
                  AND file_path IS NOT NULL AND file_path != ''
                  AND id NOT IN (SELECT CAST(REPLACE(source_id, 'legacy-', '') AS INTEGER)
                                 FROM tracks WHERE source_id LIKE 'legacy-%')
                  AND NOT EXISTS (
                      SELECT 1 FROM tracks t
                      WHERE downloads.source_id != '' AND t.source_id = downloads.source_id
                  )
                """
            ).fetchall()

        imported = 0
        for row in rows:
            artist = row["artist"] or ""
            title = row["title"] or ""
            if not title:
                continue
            with self._lock, self._conn:
                try:
                    self._conn.execute(
                        """
                        INSERT OR IGNORE INTO tracks (
                            source_id, title, artist, normalized_artist,
                            normalized_title, filepath, filesize, duration,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            f"legacy-{row['id']}",
                            title,
                            artist,
                            normalize_name(artist),
                            normalize_name(title),
                            row["file_path"],
                            row["file_size"] or 0,
                            row["duration"] or 0,
                            _now(),
                            _now(),
                        ),
                    )
                    imported += 1
                except sqlite3.IntegrityError:
                    continue
        if imported:
            logger.info("Migrated %d legacy downloads into the track library", imported)

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #

    def close(self) -> None:
        with self._lock, contextlib.suppress(sqlite3.Error):
            self._conn.close()

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def integrity_check(self) -> bool:
        try:
            row = self._conn.execute("PRAGMA integrity_check").fetchone()
            return bool(row) and row[0] == "ok"
        except sqlite3.DatabaseError:
            return False

    # ------------------------------------------------------------------ #
    # tracks (library + dedup)
    # ------------------------------------------------------------------ #

    def upsert_track(
        self,
        source_id: str,
        *,
        title: str,
        artist: str,
        album: str = "",
        album_artist: str = "",
        genre: str = "",
        year: int | None = None,
        track_number: int | None = None,
        duration: float = 0.0,
        normalized_artist: str = "",
        normalized_title: str = "",
        filepath: str = "",
        codec: str = "",
        bitrate: int = 0,
        filesize: int = 0,
        artwork: bool = False,
        lyrics: str = "",
        normalized: bool = False,
    ) -> int:
        now = _now()
        with self._lock, self._conn:
            cursor = self._conn.execute(
                """
                INSERT INTO tracks (
                    source_id, title, artist, album, album_artist, genre, year,
                    track_number, duration, normalized_artist, normalized_title,
                    filepath, codec, bitrate, filesize, artwork, lyrics,
                    normalized, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    title=excluded.title, artist=excluded.artist,
                    album=excluded.album, album_artist=excluded.album_artist,
                    genre=excluded.genre, year=excluded.year,
                    track_number=excluded.track_number, duration=excluded.duration,
                    normalized_artist=excluded.normalized_artist,
                    normalized_title=excluded.normalized_title,
                    filepath=excluded.filepath, codec=excluded.codec,
                    bitrate=excluded.bitrate, filesize=excluded.filesize,
                    artwork=excluded.artwork, lyrics=excluded.lyrics,
                    normalized=excluded.normalized, updated_at=excluded.updated_at
                """,
                (
                    source_id, title, artist, album, album_artist, genre, year,
                    track_number, duration, normalized_artist, normalized_title,
                    filepath, codec, bitrate, filesize, int(artwork), lyrics,
                    int(normalized), now, now,
                ),
            )
            return int(cursor.lastrowid or 0)

    def find_track(
        self,
        source_id: str = "",
        *,
        artist: str = "",
        title: str = "",
        duration: float = 0.0,
        tolerance: int = 3,
    ) -> dict[str, Any] | None:
        """Duplicate detection: exact source_id or fuzzy artist+title+duration."""
        from melodine.services.dedup import variant_signature

        with self._lock:
            if source_id:
                row = self._conn.execute(
                    "SELECT * FROM tracks WHERE source_id = ?", (source_id,)
                ).fetchone()
                if row:
                    return dict(row)
            if not (artist and title):
                return None
            rows = self._conn.execute(
                """
                SELECT * FROM tracks
                WHERE normalized_artist = ? AND normalized_title = ?
                """,
                (normalize_artist_for_db(artist), normalize_title_for_db(title)),
            ).fetchall()

        for row in rows:
            # A live/remix/cover is a different recording than the studio
            # version even when the normalized names match.
            if variant_signature(str(row["title"] or "")) != variant_signature(title):
                continue
            track_duration = row["duration"] or 0
            if track_duration <= 0 or duration <= 0:
                return dict(row)  # cannot compare - conservative duplicate
            if abs(track_duration - duration) <= tolerance:
                return dict(row)
        return None

    def list_tracks(
        self, limit: int = 200, offset: int = 0, search: str = ""
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM tracks"
        params: list[Any] = []
        if search:
            query += " WHERE artist LIKE ? OR title LIKE ? OR album LIKE ?"
            like = f"%{search}%"
            params = [like, like, like]
        query += " ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?"
        params += [limit, offset]
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def count_tracks(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS c FROM tracks").fetchone()
        return int(row["c"]) if row else 0

    def missing_files(self) -> list[dict[str, Any]]:
        tracks = self.list_tracks(limit=100_000)
        return [t for t in tracks if t["filepath"] and not Path(t["filepath"]).exists()]

    # ------------------------------------------------------------------ #
    # history (v1 compatible + extended)
    # ------------------------------------------------------------------ #

    def record_download(
        self,
        query: str,
        artist: str,
        title: str,
        status: str,
        attempts: int = 1,
        file_path: str = "",
        file_size: int = 0,
        source_id: str = "",
        message: str = "",
    ) -> None:
        with self._lock, self._conn:
            existing = self._conn.execute(
                "SELECT id FROM downloads WHERE query = ?", (query,)
            ).fetchone()
            if existing:
                self._conn.execute(
                    """
                    UPDATE downloads SET status=?, attempts=?, file_path=?,
                        file_size=?, downloaded_at=CURRENT_TIMESTAMP,
                        source_id=COALESCE(NULLIF(?, ''), source_id), message=?
                    WHERE query=?
                    """,
                    (status, attempts, file_path, file_size, source_id, message, query),
                )
            else:
                self._conn.execute(
                    """
                    INSERT INTO downloads (
                        query, artist, title, status, attempts, file_path,
                        file_size, source_id, message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        query, artist, title, status, attempts, file_path,
                        file_size, source_id, message,
                    ),
                )

    def record_session(
        self,
        playlist_file: str,
        total: int,
        success: int,
        failed: int,
        skipped: int,
        total_size: int,
        duration_seconds: float,
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO sessions (
                    playlist_file, total_tracks, success, failed, skipped,
                    total_size, duration_seconds
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (playlist_file, total, success, failed, skipped, total_size, duration_seconds),
            )

    def list_history(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT query, artist, title, status, file_path, file_size,
                       downloaded_at
                FROM downloads ORDER BY downloaded_at DESC, id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def failed_tracks(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT query, artist, title FROM downloads WHERE status='failed'"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_stats(self) -> dict[str, Any]:
        """v1-compatible statistics payload (weekly chart + top artists)."""
        with self._lock:
            total = self._conn.execute(
                "SELECT COUNT(*) AS c FROM downloads"
            ).fetchone()["c"]
            success = self._conn.execute(
                "SELECT COUNT(*) AS c FROM downloads WHERE status='success'"
            ).fetchone()["c"]
            failed = self._conn.execute(
                "SELECT COUNT(*) AS c FROM downloads WHERE status='failed'"
            ).fetchone()["c"]
            total_size = self._conn.execute(
                "SELECT COALESCE(SUM(file_size), 0) AS s FROM downloads "
                "WHERE status='success'"
            ).fetchone()["s"]
            total_time = self._conn.execute(
                "SELECT COALESCE(SUM(duration_seconds), 0) AS t FROM sessions"
            ).fetchone()["t"]

            daily: list[dict[str, Any]] = []
            for i in range(6, -1, -1):
                day = datetime.now() - timedelta(days=i)
                date_str = day.strftime("%Y-%m-%d")
                count = self._conn.execute(
                    "SELECT COUNT(*) AS c FROM downloads "
                    "WHERE date(downloaded_at) = ? AND status='success'",
                    (date_str,),
                ).fetchone()["c"]
                daily.append(
                    {"day": day.strftime("%a"), "date": date_str, "count": count}
                )

            top_artists = self._conn.execute(
                """
                SELECT artist, COUNT(*) AS c FROM downloads
                WHERE status='success' AND artist != ''
                GROUP BY artist ORDER BY c DESC LIMIT 10
                """
            ).fetchall()

        return {
            "total": total,
            "success": success,
            "failed": failed,
            "total_size": total_size,
            "total_time": total_time,
            "daily": daily,
            "top_artists": [
                {"artist": r["artist"], "count": r["c"]} for r in top_artists
            ],
        }

    # ------------------------------------------------------------------ #
    # watchlist
    # ------------------------------------------------------------------ #

    def watchlist_add(
        self, url: str, name: str, kind: str, playlist_path: str = ""
    ) -> WatchlistEntry:
        now = _now()
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO watchlist (url, name, kind, playlist_path, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET name=excluded.name, kind=excluded.kind
                """,
                (url, name, kind, playlist_path, now),
            )
            row = self._conn.execute(
                "SELECT * FROM watchlist WHERE url = ?", (url,)
            ).fetchone()
        return self._watchlist_row_to_entry(row)

    def watchlist_list(self, active_only: bool = False) -> list[WatchlistEntry]:
        query = "SELECT * FROM watchlist"
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY id"
        with self._lock:
            rows = self._conn.execute(query).fetchall()
            entries = []
            for row in rows:
                entry = self._watchlist_row_to_entry(row)
                count = self._conn.execute(
                    "SELECT COUNT(*) AS c FROM watchlist_items WHERE watchlist_id = ?",
                    (row["id"],),
                ).fetchone()
                entry.track_count = int(count["c"]) if count else 0
                entries.append(entry)
        return entries

    def watchlist_get(self, entry_id: int) -> WatchlistEntry | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM watchlist WHERE id = ?", (entry_id,)
            ).fetchone()
        return self._watchlist_row_to_entry(row) if row else None

    def watchlist_remove(self, entry_id: int) -> bool:
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT id FROM watchlist WHERE id = ?", (entry_id,)
            ).fetchone()
            if not row:
                return False
            self._conn.execute(
                "DELETE FROM watchlist_items WHERE watchlist_id = ?", (entry_id,)
            )
            self._conn.execute("DELETE FROM watchlist WHERE id = ?", (entry_id,))
        return True

    def watchlist_update_synced(self, entry_id: int, when: str | None = None) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE watchlist SET last_synced_at = ? WHERE id = ?",
                (when or _now(), entry_id),
            )

    def watchlist_set_playlist_path(self, entry_id: int, path: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE watchlist SET playlist_path = ? WHERE id = ?",
                (path, entry_id),
            )

    def watchlist_known_ids(self, entry_id: int) -> set[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT source_id FROM watchlist_items WHERE watchlist_id = ?",
                (entry_id,),
            ).fetchall()
        return {row["source_id"] for row in rows}

    def watchlist_add_known(self, entry_id: int, source_ids: list[str]) -> None:
        now = _now()
        with self._lock, self._conn:
            self._conn.executemany(
                """
                INSERT OR IGNORE INTO watchlist_items (watchlist_id, source_id, added_at)
                VALUES (?, ?, ?)
                """,
                [(entry_id, sid, now) for sid in source_ids],
            )

    def watchlist_tracks(self, entry_id: int) -> list[dict[str, Any]]:
        """Library tracks that belong to this watchlist (via known source ids)."""
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT t.* FROM tracks t
                JOIN watchlist_items wi ON wi.source_id = t.source_id
                WHERE wi.watchlist_id = ?
                ORDER BY t.created_at DESC
                """,
                (entry_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _watchlist_row_to_entry(row: sqlite3.Row) -> WatchlistEntry:
        return WatchlistEntry(
            id=int(row["id"]),
            url=str(row["url"]),
            name=str(row["name"] or ""),
            kind=str(row["kind"] or "unknown"),
            playlist_path=str(row["playlist_path"] or ""),
            last_synced_at=str(row["last_synced_at"] or ""),
            active=bool(row["active"]),
        )

    # ------------------------------------------------------------------ #
    # queue state (graceful shutdown)
    # ------------------------------------------------------------------ #

    def save_queue(self, tasks: list[DownloadTask]) -> int:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM queue_state")
            for task in tasks:
                self._conn.execute(
                    "INSERT INTO queue_state (payload, created_at) VALUES (?, ?)",
                    (json.dumps(task.to_payload(), ensure_ascii=False), _now()),
                )
        return len(tasks)

    def load_queue(self) -> list[DownloadTask]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload FROM queue_state ORDER BY id"
            ).fetchall()
        tasks: list[DownloadTask] = []
        for row in rows:
            try:
                tasks.append(DownloadTask.from_payload(json.loads(row["payload"])))
            except (json.JSONDecodeError, TypeError, KeyError):
                continue
        return tasks

    def clear_queue(self) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM queue_state")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def normalize_artist_for_db(artist: str) -> str:
    from melodine.services.dedup import normalize_name

    return normalize_name(artist)


def normalize_title_for_db(title: str) -> str:
    from melodine.services.dedup import normalize_name

    return normalize_name(title)
