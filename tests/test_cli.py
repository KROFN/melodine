"""CLI tests (typer CliRunner): version, doctor, export, watchlist, get."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from melodine.cli.main import app
from melodine.db.database import Database

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b")


def _strip_ansi(text: str) -> str:
    """Remove ANSI styling so substring asserts are version/environment-proof."""
    return _ANSI_RE.sub("", text)


def seed_library(db_path: Path) -> None:
    db = Database(str(db_path))
    db.upsert_track(
        "v1",
        title="Song One",
        artist="Artist One",
        album="Album",
        normalized_artist="artist one",
        normalized_title="song one",
        duration=200,
        filepath="a.mp3",
        codec="mp3",
    )
    db.upsert_track(
        "v2",
        title="Song Two",
        artist="Artist Two",
        album="Album",
        normalized_artist="artist two",
        normalized_title="song two",
        duration=220,
        filepath="b.mp3",
        codec="opus",
    )
    db.close()


class TestVersion:
    def test_version_flag(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "Melodine v" in result.output


class TestDoctor:
    def test_doctor_ok(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            "melodine.services.doctor._tool_version",
            lambda binary: f"{binary} version 7.0",
        )
        result = runner.invoke(app, ["--lang", "en", "doctor", "--offline"])
        assert result.exit_code == 0, result.output
        assert "OK" in result.output
        assert (tmp_path / "melodine.db").exists()

    def test_doctor_reports_failure(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            "melodine.services.doctor._tool_version", lambda binary: None
        )
        monkeypatch.setattr(
            "melodine.services.doctor.shutil.which", lambda name: None
        )
        result = runner.invoke(app, ["--lang", "en", "doctor", "--offline"])
        assert result.exit_code == 1
        assert "FAIL" in result.output


class TestExport:
    def test_export_m3u8(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        seed_library(tmp_path / "melodine.db")
        result = runner.invoke(app, ["export", "--format", "m3u8", "--scope", "library"])
        assert result.exit_code == 0, result.output
        out = tmp_path / "downloads" / "melodine-library.m3u8"
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert content.startswith("#EXTM3U")
        assert "a.mp3" in content

    def test_export_json(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        seed_library(tmp_path / "melodine.db")
        result = runner.invoke(app, ["export", "--format", "json"])
        assert result.exit_code == 0, result.output
        out = tmp_path / "downloads" / "melodine-library.json"
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert '"Song One"' in content

    def test_export_bad_format(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["export", "--format", "wma"])
        assert result.exit_code == 1


class TestWatchlistCLI:
    def test_add_list_remove(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(
            app,
            ["watchlist", "add", "https://www.youtube.com/@testchannel", "--name", "Test"],
        )
        assert result.exit_code == 0, result.output
        assert "Test" in result.output

        result = runner.invoke(app, ["--lang", "en", "watchlist", "list"])
        assert result.exit_code == 0
        assert "Test" in result.output
        assert "channel" in result.output

        result = runner.invoke(app, ["--lang", "en", "watchlist", "remove", "1"])
        assert result.exit_code == 0
        assert "Removed" in result.output

    def test_list_empty(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["watchlist", "list"])
        assert result.exit_code == 0

    def test_remove_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["watchlist", "remove", "99"])
        assert result.exit_code == 1

    def test_sync_empty_watchlist(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["sync"])
        assert result.exit_code == 0


class TestGet:
    def test_get_playlist_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["get", "nonexistent.txt"])
        assert result.exit_code == 1
        # Must fail fast with an explicit message, never fall through to
        # treating the .txt name as a search query (which would hit the
        # network - the offline socket guard makes that a hard failure).
        assert not isinstance(result.exception, type(None))

    def test_get_missing_txt_message_is_file_not_found(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["--lang", "en", "get", "nonexistent.txt"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_get_without_query_shows_usage_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["--lang", "en", "get"])
        assert result.exit_code == 1
        assert "Provide a query" in result.output or "query" in result.output.lower()

    def test_get_resume_empty_queue(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["--lang", "en", "get", "--resume"])
        assert result.exit_code == 0
        assert "Nothing to resume" in result.output

    def test_get_txt_batch_applies_cli_flags(self, tmp_path, monkeypatch):
        """Regression: `.txt` batch runs used to silently drop every CLI
        flag (-f/--normalize/--no-sponsorblock/...) and fall back to the
        config defaults."""
        from melodine.models import DownloadOptions

        playlist = tmp_path / "list.txt"
        playlist.write_text("Artist - Song One\nArtist - Song Two\n")

        captured: dict = {}

        def fake_run_batch(cfg, db, tasks, *, options=None):
            captured["tasks"] = list(tasks)
            captured["options"] = options
            return []

        # melodine.cli/__init__ re-exports `main`, shadowing the submodule,
        # so resolve the real module object from sys.modules.
        import sys

        cli_main_module = sys.modules["melodine.cli.main"]
        monkeypatch.setattr(cli_main_module, "_run_batch", fake_run_batch)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            app,
            [
                "--lang", "en",
                "get", str(playlist),
                "-f", "opus",
                "--normalize",
                "--no-sponsorblock",
                "--bitrate", "160",
            ],
        )
        assert result.exit_code == 0, result.output
        assert len(captured["tasks"]) == 2
        opts: DownloadOptions = captured["options"]
        assert opts is not None
        assert opts.codec == "opus"
        assert opts.bitrate == 160
        assert opts.normalize is True
        assert opts.sponsorblock is False

    def test_get_help(self):
        # Wide COLUMNS forces a single-column layout and _strip_ansi() removes
        # ANSI codes (some typer/rich versions style the option dashes
        # separately), keeping the assertions independent of the environment.
        result = runner.invoke(app, ["get", "--help"], env={"COLUMNS": "200"})
        assert result.exit_code == 0
        plain = _strip_ansi(result.output)
        assert "--sponsorblock" in plain
        assert "--normalize" in plain

    def test_get_full_pipeline_mocked(self, tmp_path, monkeypatch):
        """End-to-end `get` with yt-dlp, providers and lyrics mocked."""
        from melodine.services.downloader import DownloadService

        audio = tmp_path / "out.mp3"
        audio.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 413 * 4)

        fake_info = {
            "id": "vid123",
            "title": "Song (Official Audio)",
            "channel": "Artist - Topic",
            "duration": 200,
            "thumbnail": None,
            "thumbnails": [],
            "requested_downloads": [{"filepath": str(audio)}],
        }

        def fake_extract_info(self, url, opts, download):
            return dict(fake_info)

        def fake_resolve(self, task):
            return "https://youtu.be/vid123", "Artist", "Song", None

        monkeypatch.setattr(DownloadService, "_extract_info", fake_extract_info)
        monkeypatch.setattr(DownloadService, "resolve", fake_resolve)
        monkeypatch.setattr(
            "melodine.services.metadata.MetadataEnricher.enrich",
            lambda self, a, b: None,
        )
        monkeypatch.setattr(
            "melodine.services.lrclib.LRCLIBClient.best_match",
            lambda self, *a, **k: None,
        )

        config_yaml = (
            "language: en\n"
            "metadata:\n  enrich: false\n"
            "lyrics:\n  enabled: false\n"
            "artwork:\n  embed: false\n"
            "tags:\n  enabled: false\n"
            "sponsorblock:\n  enabled: false\n"
        )
        monkeypatch.chdir(tmp_path)
        (tmp_path / "config.yaml").write_text(config_yaml, encoding="utf-8")
        result = runner.invoke(app, ["--lang", "en", "get", "Artist - Song"])
        assert result.exit_code == 0, result.output
        assert "Song" in result.output
        # history + library persisted
        db = Database(tmp_path / "melodine.db")
        assert db.count_tracks() == 1
        assert db.list_history()[0]["status"] == "success"
        db.close()


class TestHelp:
    def test_all_commands_have_help(self):
        result = runner.invoke(app, ["--help"], env={"COLUMNS": "200"})
        assert result.exit_code == 0
        plain = _strip_ansi(result.output)
        for command in ("get", "sync", "lyrics", "doctor", "export", "watchlist"):
            assert command in plain

    @pytest.mark.parametrize(
        "command",
        ["get", "sync", "lyrics", "doctor", "export", "tui"],
    )
    def test_command_help(self, command: str):
        result = runner.invoke(app, [command, "--help"])
        assert result.exit_code == 0
