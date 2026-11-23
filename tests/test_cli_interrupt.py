"""Regression tests for headless CLI interrupt semantics.

These tests cover the control-flow gap that unit-testing DownloadPool alone
cannot catch: GracefulShutdown's signal handler sets an event instead of
raising KeyboardInterrupt, so the CLI main loop must explicitly observe it.
"""

from __future__ import annotations

import importlib

import pytest
import typer
from typer.testing import CliRunner

from melodine.core.config import AppConfig
from melodine.db.database import Database
from melodine.models import DownloadResult, DownloadTask
from melodine.services.downloader import DownloadService

cli_main = importlib.import_module("melodine.cli.main")
runner = CliRunner()


class _NullLive:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _NullProgress:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeShutdown:
    last = None

    def __init__(self, *, triggered: bool = False):
        self._triggered = triggered
        self.restored = False
        _FakeShutdown.last = self

    @property
    def triggered(self) -> bool:
        return self._triggered

    def install(self) -> None:
        pass

    def restore(self) -> None:
        self.restored = True


def test_headless_batch_observes_shutdown_event_and_persists(monkeypatch):
    """A first Ctrl+C is an event, not a Python KeyboardInterrupt.

    The main loop must still enter cancel_and_persist before workers can all
    become done/cancelled and the normal path clears queue_state.
    """

    class FakeDB:
        def __init__(self):
            self.closed = False
            self.cleared = False

        def close(self):
            self.closed = True

        def clear_queue(self):
            self.cleared = True

    class FakePool:
        last = None

        def __init__(self, cfg, db, *, shutdown=None, options=None, reporter=None):
            self.shutdown = shutdown
            self.results = []
            self.submitted = []
            self.cancelled = False
            FakePool.last = self

        def submit(self, task):
            self.submitted.append(task)
            # Simulate SIGINT arriving after work has been queued.
            self.shutdown._triggered = True

        def is_done(self):
            # The important assertion is that shutdown.triggered is checked
            # before this can lead the CLI into its normal clear_queue path.
            return True

        @property
        def active_count(self):
            return len(self.submitted)

        def counts(self):
            return {"success": 0, "failed": 0, "skipped": 0, "cancelled": 0}

        def cancel_and_persist(self):
            self.cancelled = True
            return len(self.submitted)

    db = FakeDB()
    cfg = AppConfig()

    monkeypatch.setattr(cli_main, "GracefulShutdown", _FakeShutdown)
    monkeypatch.setattr(cli_main, "DownloadPool", FakePool)
    monkeypatch.setattr(cli_main, "QueueLive", _NullLive)
    monkeypatch.setattr(cli_main, "build_progress", lambda theme: object())
    monkeypatch.setattr(cli_main, "ProgressBridge", lambda progress, theme: object())

    with pytest.raises(typer.Exit) as exc:
        cli_main._run_batch(
            cfg,
            db,
            [DownloadTask(query="one"), DownloadTask(query="two")],
        )

    assert exc.value.exit_code == 130
    assert FakePool.last is not None
    assert FakePool.last.cancelled is True
    assert db.closed is True
    assert db.cleared is False
    assert _FakeShutdown.last is not None
    assert _FakeShutdown.last.restored is True


def test_single_track_passes_shutdown_token_and_exits_130(monkeypatch, tmp_path):
    """Single-track get must share the signal token with DownloadService."""

    captured = {}

    class FakeService:
        def __init__(self, cfg, db, *, shutdown=None, options=None):
            captured["shutdown"] = shutdown
            self.shutdown = shutdown

        def process(self, task, *, report=None):
            # Simulate first Ctrl+C while DownloadService owns the operation:
            # the signal handler sets the shared event and the service returns
            # its cooperative cancelled result.
            self.shutdown._triggered = True
            return DownloadResult(task=task, status="cancelled", error="cancelled")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli_main, "GracefulShutdown", _FakeShutdown)
    monkeypatch.setattr(cli_main, "DownloadService", FakeService)
    monkeypatch.setattr(cli_main, "build_progress", lambda theme: _NullProgress())
    monkeypatch.setattr(cli_main, "ProgressBridge", lambda progress, theme: None)

    result = runner.invoke(
        cli_main.app,
        ["--lang", "en", "get", "Artist - Song"],
    )

    assert result.exit_code == 130, result.output
    assert captured["shutdown"] is not None
    assert captured["shutdown"].triggered is True
    assert captured["shutdown"].restored is True


def test_download_service_honors_pretriggered_shutdown_before_resolve(
    monkeypatch, tmp_path
):
    """Single-track cancellation is observed before network/search work starts."""

    class TriggeredShutdown:
        triggered = True

    cfg = AppConfig()
    db = Database(str(tmp_path / "melodine.db"))
    service = DownloadService(cfg, db, shutdown=TriggeredShutdown())

    def should_not_resolve(task):
        raise AssertionError("resolve must not run after shutdown was triggered")

    monkeypatch.setattr(service, "resolve", should_not_resolve)
    try:
        result = service.process(DownloadTask(query="Artist - Song"))
    finally:
        db.close()

    assert result.status == "cancelled"
    assert result.error == "cancelled"
