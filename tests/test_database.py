"""Database v2 behaviour tests."""

from __future__ import annotations

from melodine.db.database import Database
from melodine.models import DownloadTask


class TestTracks:
    def test_upsert_and_find_by_source_id(self, db: Database):
        db.upsert_track(
            "vid1",
            title="Song",
            artist="Artist",
            normalized_artist="artist",
            normalized_title="song",
            filepath="/music/song.mp3",
            codec="mp3",
        )
        found = db.find_track("vid1")
        assert found is not None
        assert found["title"] == "Song"
        assert found["source_id"] == "vid1"

    def test_fuzzy_duplicate_detection(self, db: Database):
        db.upsert_track(
            "vid1",
            title="Song",
            artist="Artist",
            normalized_artist="artist",
            normalized_title="song",
            duration=200,
            filepath="/music/song.mp3",
        )
        found = db.find_track(
            "other-id", artist="artist", title="Song (Official Audio)", duration=201
        )
        assert found is not None
        assert found["source_id"] == "vid1"

    def test_no_duplicate_for_different_track(self, db: Database):
        db.upsert_track(
            "vid1",
            title="Song",
            artist="Artist",
            normalized_artist="artist",
            normalized_title="song",
            duration=200,
        )
        assert db.find_track("x", artist="artist", title="Other", duration=200) is None

    def test_duration_outside_tolerance_not_duplicate(self, db: Database):
        db.upsert_track(
            "vid1",
            title="Song",
            artist="Artist",
            normalized_artist="artist",
            normalized_title="song",
            duration=200,
        )
        assert db.find_track("x", artist="artist", title="song", duration=260) is None

    def test_upsert_updates_existing(self, db: Database):
        db.upsert_track("vid1", title="Old", artist="A", normalized_artist="a",
                        normalized_title="old")
        db.upsert_track("vid1", title="New", artist="A", normalized_artist="a",
                        normalized_title="new", album="Album")
        tracks = db.list_tracks()
        assert len(tracks) == 1
        assert tracks[0]["title"] == "New"
        assert tracks[0]["album"] == "Album"

    def test_list_tracks_search(self, db: Database):
        db.upsert_track("v1", title="Alpha", artist="One", normalized_artist="one",
                        normalized_title="alpha")
        db.upsert_track("v2", title="Beta", artist="Two", normalized_artist="two",
                        normalized_title="beta")
        assert len(db.list_tracks(search="alpha")) == 1
        assert len(db.list_tracks(search="two")) == 1
        assert len(db.list_tracks()) == 2

    def test_missing_files_detection(self, db: Database, tmp_path):
        existing = tmp_path / "exists.mp3"
        existing.write_bytes(b"x")
        db.upsert_track("v1", title="A", artist="A", normalized_artist="a",
                        normalized_title="a", filepath=str(existing))
        db.upsert_track("v2", title="B", artist="B", normalized_artist="b",
                        normalized_title="b", filepath="/nonexistent/b.mp3")
        missing = db.missing_files()
        assert len(missing) == 1
        assert missing[0]["source_id"] == "v2"


class TestHistory:
    def test_record_download_insert_then_update(self, db: Database):
        db.record_download("Artist - Song", "Artist", "Song", "success",
                           file_path="/a.mp3", file_size=10)
        db.record_download("Artist - Song", "Artist", "Song", "failed")
        history = db.list_history()
        assert len(history) == 1
        assert history[0]["status"] == "failed"

    def test_failed_tracks(self, db: Database):
        db.record_download("q1", "A", "T1", "failed")
        db.record_download("q2", "A", "T2", "success")
        failed = db.failed_tracks()
        assert len(failed) == 1
        assert failed[0]["query"] == "q1"

    def test_stats_shape(self, db: Database):
        db.record_download("q", "Artist", "Song", "success", file_size=100)
        db.record_session("list.txt", 1, 1, 0, 0, 100, 12.5)
        stats = db.get_stats()
        assert stats["total"] == 1
        assert stats["success"] == 1
        assert stats["total_size"] == 100
        assert len(stats["daily"]) == 7
        assert stats["top_artists"][0]["artist"] == "Artist"


class TestWatchlist:
    def test_add_list_remove(self, db: Database):
        entry = db.watchlist_add(
            "https://www.youtube.com/playlist?list=PL123", "Chill", "playlist"
        )
        assert entry.id > 0
        entries = db.watchlist_list()
        assert len(entries) == 1
        assert entries[0].name == "Chill"

        assert db.watchlist_remove(entry.id) is True
        assert db.watchlist_list() == []
        assert db.watchlist_remove(entry.id) is False

    def test_known_ids(self, db: Database):
        entry = db.watchlist_add("https://youtu.be/x", "X", "playlist")
        assert db.watchlist_known_ids(entry.id) == set()
        db.watchlist_add_known(entry.id, ["a", "b"])
        db.watchlist_add_known(entry.id, ["b", "c"])  # idempotent
        assert db.watchlist_known_ids(entry.id) == {"a", "b", "c"}

    def test_synced_timestamp(self, db: Database):
        entry = db.watchlist_add("https://youtu.be/x", "X", "playlist")
        db.watchlist_update_synced(entry.id, "2025-01-01 10:00:00")
        assert db.watchlist_get(entry.id).last_synced_at == "2025-01-01 10:00:00"

    def test_watchlist_tracks_join(self, db: Database):
        entry = db.watchlist_add("https://youtu.be/x", "X", "playlist")
        db.upsert_track("vid9", title="Song", artist="A", normalized_artist="a",
                        normalized_title="song")
        db.watchlist_add_known(entry.id, ["vid9"])
        tracks = db.watchlist_tracks(entry.id)
        assert len(tracks) == 1
        assert tracks[0]["source_id"] == "vid9"


class TestQueueState:
    def test_save_load_clear(self, db: Database):
        tasks = [
            DownloadTask(query="Artist - Song", source="manual"),
            DownloadTask(url="https://youtu.be/xyz", source="search"),
        ]
        assert db.save_queue(tasks) == 2
        loaded = db.load_queue()
        assert len(loaded) == 2
        assert loaded[0].query == "Artist - Song"
        assert loaded[1].url == "https://youtu.be/xyz"
        assert loaded[1].source == "search"

        db.clear_queue()
        assert db.load_queue() == []
