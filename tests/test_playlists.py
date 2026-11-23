"""Playlists / M3U8 / watchlist sync tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from melodine.models import DownloadResult, DownloadTask
from melodine.services.playlists import (
    WatchlistService,
    detect_kind,
    write_m3u8,
)


class TestDetectKind:
    def test_playlist(self):
        assert detect_kind("https://www.youtube.com/playlist?list=PL123") == "playlist"

    def test_channel_at(self):
        assert detect_kind("https://www.youtube.com/@somechannel") == "channel"

    def test_channel_id(self):
        assert detect_kind("https://www.youtube.com/channel/UC123") == "channel"

    def test_unknown(self):
        assert detect_kind("https://example.com/foo") == "unknown"


class TestM3U8:
    def test_write_m3u8(self, tmp_path: Path):
        target = tmp_path / "out" / "playlist.m3u8"
        entries = [
            {"filepath": str(tmp_path / "a.mp3"), "title": "Song A",
             "artist": "Artist A", "duration": 200},
            {"filepath": str(tmp_path / "b.mp3"), "title": "Song B",
             "artist": "Artist B", "duration": 181},
        ]
        (tmp_path / "a.mp3").write_bytes(b"a")
        (tmp_path / "b.mp3").write_bytes(b"b")

        count = write_m3u8(target, "My List", entries, relative_to=tmp_path)
        assert count == 2
        content = target.read_text(encoding="utf-8")
        assert content.startswith("#EXTM3U")
        assert "#PLAYLIST:My List" in content
        assert "#EXTINF:200,Artist A - Song A" in content
        assert "a.mp3" in content and "b.mp3" in content
        assert "\\" not in content  # relative paths, no absolute separators

    def test_write_m3u8_skips_empty_paths(self, tmp_path: Path):
        target = tmp_path / "p.m3u8"
        entries = [{"filepath": "", "title": "X", "artist": "", "duration": 0}]
        assert write_m3u8(target, "N", entries) == 0


class FakeDownloadService:
    """Deterministic download service double."""

    def __init__(self) -> None:
        self.shutdown = None
        self.processed: list[DownloadTask] = []

    def process(self, task: DownloadTask, report: Any = None) -> DownloadResult:
        self.processed.append(task)
        return DownloadResult(task=task, status="success", path="/x/y.mp3")


class TestWatchlistSync:
    def _service(self, db, tmp_path):
        from melodine.core.config import AppConfig

        cfg = AppConfig()
        cfg.output.folder = str(tmp_path / "music")
        cfg.database.path = str(tmp_path / "melodine.db")
        service = WatchlistService(cfg, db, service=FakeDownloadService())
        return cfg, service

    def test_sync_downloads_only_new(
        self, db, tmp_path, monkeypatch
    ):
        _cfg, service = self._service(db, tmp_path)
        entry = service.add("https://www.youtube.com/playlist?list=PL1", "Test List")

        listing = [
            {"id": "v1", "title": "Song One", "duration": 200, "channel": "Chan",
             "url": "https://youtu.be/v1"},
            {"id": "v2", "title": "Song Two", "duration": 210, "channel": "Chan",
             "url": "https://youtu.be/v2"},
        ]
        monkeypatch.setattr(
            "melodine.services.playlists.list_playlist_entries",
            lambda url, timeout=30: listing,
        )

        report = service.sync(entry)
        assert report.listed == 2
        assert report.downloaded == 2
        assert len(service.service.processed) == 2  # type: ignore[attr-defined]
        assert db.watchlist_known_ids(entry.id) == {"v1", "v2"}

        # m3u8 got written
        assert Path(entry.playlist_path).exists()
        content = Path(entry.playlist_path).read_text(encoding="utf-8")
        assert content.startswith("#EXTM3U")

        # Second sync: nothing new
        service.service.processed.clear()  # type: ignore[attr-defined]
        report2 = service.sync(entry)
        assert report2.downloaded == 0
        assert len(service.service.processed) == 0  # type: ignore[attr-defined]

    def test_sync_skips_known_library_duplicates(
        self, db, tmp_path, monkeypatch
    ):
        _cfg, service = self._service(db, tmp_path)
        db.upsert_track(
            "v1",
            title="Song One",
            artist="Chan",
            normalized_artist="chan",
            normalized_title="song one",
            duration=200,
            filepath="/lib/one.mp3",
        )
        entry = service.add("https://www.youtube.com/playlist?list=PL2", "Second")

        listing = [
            {"id": "v1", "title": "Song One", "duration": 200, "channel": "Chan",
             "url": "https://youtu.be/v1"},
        ]
        monkeypatch.setattr(
            "melodine.services.playlists.list_playlist_entries",
            lambda url, timeout=30: listing,
        )
        report = service.sync(entry)
        assert report.downloaded == 0
        assert report.duplicates == 1
        assert db.watchlist_known_ids(entry.id) == {"v1"}

    def test_add_guesses_names(self, db, tmp_path):
        _cfg, service = self._service(db, tmp_path)
        entry = service.add("https://www.youtube.com/@mychannel")
        assert entry.kind == "channel"
        assert "mychannel" in entry.name.lower()

        entry2 = service.add("https://www.youtube.com/playlist?list=PLXYZ987654321")
        assert entry2.kind == "playlist"
        assert "Playlist" in entry2.name

    def test_remove(self, db, tmp_path):
        _cfg, service = self._service(db, tmp_path)
        entry = service.add("https://youtu.be/x", "X", "playlist")
        assert service.remove(entry.id) is True
        assert service.list() == []
