"""Downloader pipeline unit tests (no network, no yt-dlp calls)."""

from __future__ import annotations

from pathlib import Path

from melodine.core.config import AppConfig
from melodine.models import (
    DownloadTask,
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

    def test_postprocessor_order_sponsorblock_first(self):
        service = self._service()
        opts = service._build_ydl_opts(Path("/tmp/x/01 - T.mp3"),
                                       get_codec_profile("mp3"), 320)
        keys = [pp["key"] for pp in opts["postprocessors"]]
        assert keys.index("SponsorBlock") < keys.index("ModifyChapters")
        assert keys.index("ModifyChapters") < keys.index("FFmpegExtractAudio")

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
        assert modify["when"] == "pre_process"

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
            extract = opts["postprocessors"][-1]
            assert extract["key"] == "FFmpegExtractAudio"
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
            from melodine.models import ScoredCandidate

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
