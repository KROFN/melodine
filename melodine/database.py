import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path("melodine.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS downloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT NOT NULL,
            artist TEXT DEFAULT '',
            title TEXT DEFAULT '',
            status TEXT NOT NULL,
            attempts INTEGER DEFAULT 1,
            file_path TEXT DEFAULT '',
            file_size INTEGER DEFAULT 0,
            duration REAL DEFAULT 0,
            downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

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
        );

        CREATE INDEX IF NOT EXISTS idx_downloads_status ON downloads(status);
        CREATE INDEX IF NOT EXISTS idx_downloads_date ON downloads(downloaded_at);
        CREATE INDEX IF NOT EXISTS idx_downloads_artist ON downloads(artist);
    """)
    conn.commit()
    conn.close()


def record_download(query: str, artist: str, title: str, status: str,
                    attempts: int = 1, file_path: str = "", file_size: int = 0) -> None:
    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM downloads WHERE query = ?", (query,)
    ).fetchone()

    if existing:
        conn.execute("""
            UPDATE downloads SET status=?, attempts=?, file_path=?, file_size=?,
                   downloaded_at=CURRENT_TIMESTAMP
            WHERE query=?
        """, (status, attempts, file_path, file_size, query))
    else:
        conn.execute("""
            INSERT INTO downloads (query, artist, title, status, attempts, file_path, file_size)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (query, artist, title, status, attempts, file_path, file_size))

    conn.commit()
    conn.close()


def record_session(playlist_file: str, total: int, success: int,
                   failed: int, skipped: int, total_size: int,
                   duration_seconds: float) -> None:
    conn = get_connection()
    conn.execute("""
        INSERT INTO sessions (playlist_file, total_tracks, success, failed,
                              skipped, total_size, duration_seconds)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (playlist_file, total, success, failed, skipped, total_size, duration_seconds))
    conn.commit()
    conn.close()


def get_stats() -> dict:
    conn = get_connection()

    total = conn.execute("SELECT COUNT(*) as c FROM downloads").fetchone()["c"]
    success = conn.execute(
        "SELECT COUNT(*) as c FROM downloads WHERE status='success'"
    ).fetchone()["c"]
    failed = conn.execute(
        "SELECT COUNT(*) as c FROM downloads WHERE status='failed'"
    ).fetchone()["c"]
    total_size = conn.execute(
        "SELECT COALESCE(SUM(file_size), 0) as s FROM downloads WHERE status='success'"
    ).fetchone()["s"]

    total_time = conn.execute(
        "SELECT COALESCE(SUM(duration_seconds), 0) as t FROM sessions"
    ).fetchone()["t"]

    # По дням (последние 7)
    daily = []
    for i in range(6, -1, -1):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        count = conn.execute(
            "SELECT COUNT(*) as c FROM downloads WHERE date(downloaded_at) = ? AND status='success'",
            (date,)
        ).fetchone()["c"]
        day_name = (datetime.now() - timedelta(days=i)).strftime("%a")
        daily.append({"day": day_name, "date": date, "count": count})

    # Топ артисты
    top_artists = conn.execute("""
        SELECT artist, COUNT(*) as c FROM downloads
        WHERE status='success' AND artist != ''
        GROUP BY artist ORDER BY c DESC LIMIT 10
    """).fetchall()

    conn.close()

    return {
        "total": total,
        "success": success,
        "failed": failed,
        "total_size": total_size,
        "total_time": total_time,
        "daily": daily,
        "top_artists": [{"artist": r["artist"], "count": r["c"]} for r in top_artists],
    }


def get_failed_count() -> int:
    conn = get_connection()
    count = conn.execute(
        "SELECT COUNT(*) as c FROM downloads WHERE status='failed'"
    ).fetchone()["c"]
    conn.close()
    return count


def get_failed_tracks() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT query, artist, title FROM downloads WHERE status='failed'"
    ).fetchall()
    conn.close()
    return [{"query": r["query"], "artist": r["artist"], "title": r["title"]} for r in rows]