"""SQLite migration tests: v1 database -> v2 schema with data preservation."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from melodine.db.database import SCHEMA_VERSION, Database
from tests.conftest import make_v1_database


class TestV1Migration:
    def test_v1_data_survives(self, tmp_path: Path):
        db_file = tmp_path / "melodine.db"
        make_v1_database(db_file)

        db = Database(db_file)
        try:
            history = db.list_history(limit=100)
            queries = {row["query"] for row in history}
            assert "Daft Punk - Around the World" in queries
            assert "Muse - Hysteria" in queries

            stats = db.get_stats()
            assert stats["total"] == 2
            assert stats["success"] == 1
            assert stats["failed"] == 1
        finally:
            db.close()

    def test_successful_downloads_backfilled_into_tracks(self, tmp_path: Path):
        db_file = tmp_path / "melodine.db"
        make_v1_database(db_file)

        db = Database(db_file)
        try:
            tracks = db.list_tracks()
            assert len(tracks) == 1
            track = tracks[0]
            assert track["artist"] == "Daft Punk"
            assert track["title"] == "Around the World"
            assert track["filepath"] == "/music/daft.mp3"
            assert track["source_id"].startswith("legacy-")
            assert track["normalized_artist"] == "daft punk"
        finally:
            db.close()

    def test_migration_is_idempotent(self, tmp_path: Path):
        db_file = tmp_path / "melodine.db"
        make_v1_database(db_file)
        Database(db_file).close()
        Database(db_file).close()

        conn = sqlite3.connect(str(db_file))
        count = conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
        conn.close()
        assert count == 1

    def test_user_version_bumped(self, tmp_path: Path):
        db_file = tmp_path / "melodine.db"
        make_v1_database(db_file)
        Database(db_file).close()

        conn = sqlite3.connect(str(db_file))
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        conn.close()
        assert version == SCHEMA_VERSION

    def test_v2_tables_created(self, tmp_path: Path):
        db = Database(tmp_path / "melodine.db")
        try:
            conn = sqlite3.connect(str(tmp_path / "melodine.db"))
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            conn.close()
            assert {"downloads", "sessions", "tracks", "watchlist",
                    "watchlist_items", "queue_state"} <= tables
        finally:
            db.close()


class TestFreshDatabase:
    def test_fresh_install(self, tmp_path: Path):
        db = Database(tmp_path / "fresh.db")
        try:
            assert db.count_tracks() == 0
            assert db.integrity_check() is True
            assert db.list_history() == []
        finally:
            db.close()
