"""Downloader pipeline unit tests (no network, no yt-dlp calls)."""

from __future__ import annotations

from pathlib import Path

import pytest

from melodine.core.config import AppConfig
from melodine.models import (
    DownloadOptions,
    DownloadTask,
    ScoredCandidate,
    SearchCandidate,
    get_codec_profile,
)
from melodine.services.downloader import (
    DownloadService,
    build_output_path,
)
from melodine.services.search import generate_search_queries


class TestBuildYdlOpts:
    def _service(self, **cfg_overrides) -> DownloadService:
        cfg = AppConfig()
        for section, values in cfg_overrides.items():
            for key, value in values.items():
                setattr(getattr(cfg, section), key, value)
        return DownloadService(cfg, _NullDB())

    def test_postprocessor_staging_matches_upstream(self):
        """Mirror yt_dlp/__init__.py get_postprocessors semantics.

        Upstream stages SponsorBlock at 'after_filter' (it only queries the
        SponsorBlock API and stores chapter info before the download), then
        FFmpegExtractAudio extracts the audio, and ModifyChapters cuts the
        sponsor segments from the already extracted file afterwards
        (ModifyChaptersPP.run() reads info['filepath'] - it needs an
        existing file, so it can never run pre-download).
        """
        service = self._service()
        opts = service._build_ydl_opts(Path("/tmp/x/01 - T.mp3"),
                                       get_codec_profile("mp3"), 320)
        pps = opts["postprocessors"]
        keys = [pp["key"] for pp in pps]
        # SponsorBlock collects segments before the download even starts.
        assert keys[0] == "SponsorBlock"
        assert pps[0]["when"] == "after_filter"
        # Extraction runs before ModifyChapters cuts the file.
        assert keys.index("FFmpegExtractAudio") < keys.index("ModifyChapters")
        # ModifyChapters is a regular post_process (no 'when' override).
        modify = next(pp for pp in pps if pp["key"] == "ModifyChapters")
        assert "when" not in modify

    def test_sponsorblock_disabled_removes_both(self):
        service = self._service(sponsorblock={"enabled": False})
        opts = service._build_ydl_opts(Path("/tmp/x/t.mp3"),
                                       get_codec_profile("mp3"), 320)
        keys = [pp["key"] for pp in opts["postprocessors"]]
        assert "SponsorBlock" not in keys
        assert "ModifyChapters" not in keys
        assert "FFmpegExtractAudio" in keys

    def test_modify_chapters_categories_forwarded(self):
        cfg = AppConfig()
        cfg.sponsorblock.categories = ["sponsor", "music_offtopic"]
        service = DownloadService(cfg, _NullDB())
        opts = service._build_ydl_opts(Path("/tmp/x/t.mp3"),
                                       get_codec_profile("mp3"), 320)
        modify = next(
            pp for pp in opts["postprocessors"] if pp["key"] == "ModifyChapters"
        )
        assert modify["remove_sponsor_segments"] == ["sponsor", "music_offtopic"]
        # No 'when' override: ModifyChapters runs in the default
        # 'post_process' phase, after FFmpegExtractAudio (upstream order).
        assert "when" not in modify
        # Categories are also forwarded to the SponsorBlock marker itself.
        marker = next(
            pp for pp in opts["postprocessors"] if pp["key"] == "SponsorBlock"
        )
        assert marker["categories"] == ["sponsor", "music_offtopic"]
        assert marker["when"] == "after_filter"

    def test_codec_profiles_map_correctly(self):
        for codec, yt_codec, ext in (
            ("opus", "opus", "opus"),
            ("mp3", "mp3", "mp3"),
            ("m4a", "m4a", "m4a"),
            ("flac", "flac", "flac"),
        ):
            service = self._service(audio={"codec": codec})
            profile = get_codec_profile(codec)
            opts = service._build_ydl_opts(Path(f"/tmp/x/t.{ext}"), profile,
                                           profile.default_bitrate)
            # Extract by key: ModifyChapters comes after FFmpegExtractAudio
            # when SponsorBlock is enabled, so [-1] is not the extractor.
            extract = next(
                pp for pp in opts["postprocessors"]
                if pp["key"] == "FFmpegExtractAudio"
            )
            assert extract["preferredcodec"] == yt_codec

    def test_outtmpl_uses_ext_placeholder(self):
        service = self._service()
        opts = service._build_ydl_opts(Path("/music/A/01 - T.mp3"),
                                       get_codec_profile("mp3"), 320)
        assert opts["outtmpl"].endswith(".%(ext)s")
        assert "A" in opts["outtmpl"]

    def test_logger_routed_to_melodine_logger(self):
        service = self._service()
        opts = service._build_ydl_opts(Path("/tmp/x/t.mp3"),
                                       get_codec_profile("mp3"), 320)
        assert opts["logger"] is not None
        assert opts["quiet"] is True
        assert opts["noprogress"] is True

    def test_retry_delay_maps_to_sleep_functions(self):
        """v1 `download.retry_delay` must actually reach yt-dlp retries."""
        service = self._service(download={"retry_delay": 7.5})
        opts = service._build_ydl_opts(Path("/tmp/x/t.mp3"),
                                       get_codec_profile("mp3"), 320)
        sleeps = opts["retry_sleep_functions"]
        for kind in ("http", "fragment", "extractor", "file_access"):
            assert sleeps[kind](3) == 7.5

    def test_retry_delay_zero_omits_sleep_functions(self):
        service = self._service(download={"retry_delay": 0})
        opts = service._build_ydl_opts(Path("/tmp/x/t.mp3"),
                                       get_codec_profile("mp3"), 320)
        assert "retry_sleep_functions" not in opts


class TestBuildOutputPath:
    def test_full_template(self):
        path = build_output_path(
            "/music",
            "{artist}/{album}/{track_num} - {title}.{ext}",
            artist="Daft Punk",
            album="Homework",
            title="Around the World",
            track_number=7,
            year=1997,
            extension="opus",
        )
        assert path == Path("/music/Daft Punk/Homework/07 - Around the World.opus")

    def test_sanitizes_unsafe_characters(self):
        path = build_output_path(
            "/music",
            "{artist}/{title}.{ext}",
            artist='AC/DC: "Back"',
            album="",
            title="What's You*r Problem?",
            track_number=None,
            year=None,
            extension="mp3",
        )
        assert "/" not in path.parts[-1]
        assert '"' not in str(path)
        assert path.suffix == ".mp3"

    def test_defaults_for_missing_fields(self):
        path = build_output_path(
            "/music",
            "{artist}/{album}/{track_num} - {title}.{ext}",
            artist="",
            album="",
            title="Song",
            track_number=None,
            year=None,
            extension="mp3",
        )
        assert path.parts[-3] == "Unknown Artist"
        assert path.parts[-2] == "Unknown Album"
        assert path.parts[-1].startswith("01 - ")


class TestEffectiveProfile:
    def test_config_defaults(self):
        service = DownloadService(AppConfig(), _NullDB())
        profile, bitrate = service.effective_profile()
        assert profile.key == "mp3"
        assert bitrate == 320

    def test_flac_has_no_bitrate(self):
        cfg = AppConfig()
        cfg.audio.codec = "flac"
        service = DownloadService(cfg, _NullDB())
        profile, bitrate = service.effective_profile()
        assert profile.lossless is True
        assert bitrate == 0


class TestResolve:
    def test_url_passthrough(self):
        service = DownloadService(AppConfig(), _NullDB())
        url, artist, title, candidate = service.resolve(
            DownloadTask(url="https://youtu.be/x", artist="A", title="T")
        )
        assert url == "https://youtu.be/x"
        assert (artist, title) == ("A", "T")
        assert candidate is None

    def test_query_uses_search(self, monkeypatch):
        calls: list[str] = []

        def fake_best(self, query, **kwargs):
            calls.append(query)
            candidate = SearchCandidate(
                source_id="x", url="https://youtu.be/x",
                title="Song", channel="Artist - Topic", duration=200,
            )
            return ScoredCandidate(candidate=candidate, score=95), []

        monkeypatch.setattr(
            "melodine.services.search.SearchService.best", fake_best
        )
        service = DownloadService(AppConfig(), _NullDB())
        url, _artist, _title, candidate = service.resolve(
            DownloadTask(query="Artist - Song")
        )
        assert url == "https://youtu.be/x"
        assert "Artist - Song" in calls
        assert candidate is not None
        assert candidate.source_id == "x"


class TestCookies:
    def test_cookies_forwarded_to_ydl(self):
        cfg = AppConfig()
        cfg.download.cookies_file = "cookies.txt"
        service = DownloadService(cfg, _NullDB())
        opts: dict = {}
        service._apply_cookies(opts)
        assert opts["cookiefile"] == "cookies.txt"

    def test_browser_cookies_forwarded(self):
        cfg = AppConfig()
        cfg.download.cookies_from_browser = "firefox"
        service = DownloadService(cfg, _NullDB())
        opts: dict = {}
        service._apply_cookies(opts)
        assert opts["cookiesfrombrowser"][0] == "firefox"

    def test_no_cookies_by_default(self):
        service = DownloadService(AppConfig(), _NullDB())
        opts: dict = {}
        service._apply_cookies(opts)
        assert "cookiefile" not in opts
        assert "cookiesfrombrowser" not in opts


class TestSmartQueries:
    def test_v1_variants_preserved(self):
        queries = generate_search_queries("A feat. B", "Song")
        assert queries[0] == "A feat. B - Song"
        assert "Song" in queries
        assert any("official audio" in q for q in queries)

    def test_artistless(self):
        assert generate_search_queries("", "Song")[0] == "Song"


class _NullDB:
    """Database double that accepts every call (for pure unit tests)."""

    def __getattr__(self, name):
        def _noop(*args, **kwargs):
            return None

        return _noop


class TestQueuePersistence:
    """Regression: Ctrl+C must persist *every* unfinished task.

    The old cancel_and_persist() persisted only futures with
    ``not future.done()`` - but Future.cancel() flips queued futures to
    done() instantly, so cancelled queued tasks vanished from the saved
    queue and were silently lost on resume.
    """

    def _pool(self, tmp_path, monkeypatch, process_fn):  # type: ignore[no-untyped-def]
        from melodine.core.shutdown import GracefulShutdown
        from melodine.db.database import Database
        from melodine.services.downloader import DownloadPool

        db_path = tmp_path / "melodine.db"
        db = Database(str(db_path))
        cfg = AppConfig()
        cfg.download.threads = 1
        cfg.download.pause = 0
        shutdown = GracefulShutdown()
        pool = DownloadPool(cfg, db, shutdown=shutdown)
        monkeypatch.setattr(DownloadService, "process", process_fn)
        return pool, db, shutdown

    def test_cancelled_queued_tasks_are_persisted(self, tmp_path, monkeypatch):
        import threading
        import time as _time

        from melodine.models import DownloadResult

        pool = db = shutdown = None
        started = threading.Event()

        def fake_process(self, task, report=None):  # type: ignore[no-untyped-def]
            started.set()
            while not self.shutdown.triggered:  # simulate in-flight download
                _time.sleep(0.01)
            return DownloadResult(task=task, status="failed", error="interrupted")

        pool, db, shutdown = self._pool(tmp_path, monkeypatch, fake_process)
        try:
            pool.submit(DownloadTask(task_id="t1", query="one"))
            assert started.wait(timeout=5)  # t1 is now in-flight
            pool.submit(DownloadTask(task_id="t2", query="two"))  # queued
            pool.submit(DownloadTask(task_id="t3", query="three"))  # queued
            _time.sleep(0.1)

            shutdown.trigger()  # SIGINT flag first, like the real handler
            saved = pool.cancel_and_persist()

            # All three tasks are unfinished -> all three must be saved,
            # including the two whose futures were cancelled while queued.
            assert saved == 3
            persisted = [t.query for t in db.load_queue()]
            assert persisted == ["one", "two", "three"]
        finally:
            db.close()

    def test_completed_tasks_are_not_persisted(self, tmp_path, monkeypatch):

        from melodine.models import DownloadResult

        def fake_process(self, task, report=None):  # type: ignore[no-untyped-def]
            return DownloadResult(task=task, status="success")

        pool, db, shutdown = self._pool(tmp_path, monkeypatch, fake_process)
        try:
            pool.submit(DownloadTask(task_id="t1", query="one"))
            pool.submit(DownloadTask(task_id="t2", query="two"))
            pool.wait(timeout=5)
            shutdown.trigger()
            saved = pool.cancel_and_persist()
            # Both tasks finished successfully: nothing to persist.
            assert saved == 0
            assert db.load_queue() == []
        finally:
            db.close()

    def test_failed_tasks_are_persisted_for_retry(self, tmp_path, monkeypatch):
        from melodine.models import DownloadResult

        def fake_process(self, task, report=None):  # type: ignore[no-untyped-def]
            return DownloadResult(task=task, status="failed", error="boom")

        pool, db, shutdown = self._pool(tmp_path, monkeypatch, fake_process)
        try:
            pool.submit(DownloadTask(task_id="t1", query="one"))
            pool.wait(timeout=5)
            shutdown.trigger()
            saved = pool.cancel_and_persist()
            # Failed tasks get another chance on resume (dedup protects
            # the successes).
            assert saved == 1
            assert [t.query for t in db.load_queue()] == ["one"]
        finally:
            db.close()


def test_pipeline_reports_transfer_and_postprocessor_stages(cfg, db, monkeypatch, tmp_path):
    cfg.output.folder = str(tmp_path / "music")
    cfg.metadata.enrich = False
    cfg.artwork.embed = False
    cfg.lyrics.enabled = False
    cfg.tags.enabled = False
    service = DownloadService(cfg, db)
    events = []

    def fake_extract(url, opts, download):
        info = {"id": "abc", "title": "Song", "channel": "Artist", "duration": 180}
        if download:
            opts["postprocessor_hooks"][0]({"status": "started", "postprocessor": "SponsorBlock"})
            opts["progress_hooks"][0]({"status": "downloading", "downloaded_bytes": 10,
                                      "total_bytes": 10})
            opts["progress_hooks"][0]({"status": "finished"})
            opts["postprocessor_hooks"][0]({"status": "started", "postprocessor": "ModifyChapters"})
            path = Path(opts["outtmpl"].replace("%(ext)s", "mp3"))
            path.write_bytes(b"test")
            info["requested_downloads"] = [{"filepath": str(path)}]
        return info

    monkeypatch.setattr(service, "_extract_info", fake_extract)
    result = service.process(
        DownloadTask(url="https://youtu.be/abc", artist="Artist", title="Song"),
        report=lambda event, task, payload: events.append((event, payload.get("stage"))),
    )
    assert result.status == "success", result.error
    assert ("post", "sponsorblock") in events
    assert events.index(("progress", None)) < events.index(("post", "convert"))
    assert events.index(("post", "cut")) < events.index(("post", "persist"))
    assert events[-1] == ("done", None)

@pytest.mark.parametrize("index", [1, 2, 3, None])
def test_explicit_search_index_uses_same_results_without_research(monkeypatch, index):
    service = DownloadService(AppConfig(), _NullDB(), options=DownloadOptions(index=index))
    items = [ScoredCandidate(SearchCandidate(url=f"https://youtu.be/{i}"), score=0)
             for i in (1, 2)]
    calls = []

    def best(*args, **kwargs):
        calls.append(args)
        return None, items

    monkeypatch.setattr(service.search, "best", best)
    task = DownloadTask(query="Muse - Hysteria", artist="Muse", title="Hysteria")
    if index in (1, 2):
        assert service.resolve(task)[0] == f"https://youtu.be/{index}"
    else:
        with pytest.raises(RuntimeError):
            service.resolve(task)
    assert len(calls) == 1
