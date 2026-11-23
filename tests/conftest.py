"""Shared fixtures for the Melodine test suite.

The suite is fully offline by design. A session-scoped socket guard makes
any accidental real network connection fail the test immediately instead
of hanging on a firewall - this is what makes "no network" a *verified*
property rather than a hopeful claim. Set ``MELODINE_TEST_ALLOW_NETWORK=1``
to disable the guard for local live-smoke runs.
"""

from __future__ import annotations

import atexit
import os
import shutil
import socket
import sqlite3
import subprocess
from pathlib import Path

import pytest

from melodine.core.config import AppConfig, save_config
from melodine.db.database import Database
from melodine.services.tagger import Tagger

# --------------------------------------------------------------------------- #
# network guard: the suite must never touch the real network
# --------------------------------------------------------------------------- #


class NetworkBlockedError(RuntimeError):
    """Raised when a test attempts a real network connection."""


def _install_network_guard() -> None:
    """Replace socket.connect/connect_ex with loud failures.

    Applied at conftest import time - before any test runs - unless
    MELODINE_TEST_ALLOW_NETWORK=1 is set for manual live-smoke runs.
    """

    def _deny_connect(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise NetworkBlockedError(
            "Real network connection attempted during the offline test "
            "suite. Tests must mock HTTP clients (see FakeSession); set "
            "MELODINE_TEST_ALLOW_NETWORK=1 only for manual live-smoke runs."
        )

    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    socket.socket.connect = _deny_connect  # type: ignore[method-assign]
    socket.socket.connect_ex = _deny_connect  # type: ignore[method-assign]
    atexit.register(_restore_network_guard, original_connect, original_connect_ex)


def _restore_network_guard(original_connect, original_connect_ex) -> None:  # type: ignore[no-untyped-def]
    socket.socket.connect = original_connect  # type: ignore[method-assign]
    socket.socket.connect_ex = original_connect_ex  # type: ignore[method-assign]


if os.environ.get("MELODINE_TEST_ALLOW_NETWORK") != "1":
    _install_network_guard()


# A minimal valid MPEG-1 Layer III frame (128 kbps, 44.1 kHz, silent).
_MP3_FRAME = b"\xff\xfb\x90\x00" + b"\x00" * 413


def silent_mp3_bytes(frames: int = 40) -> bytes:
    """Return playable silent MP3 audio (~1s)."""
    return _MP3_FRAME * frames


@pytest.fixture
def tmp_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run with a pristine working directory."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def cfg(tmp_cwd: Path) -> AppConfig:
    """A default config persisted inside the temporary working directory."""
    config = AppConfig()
    config.database.path = "melodine.db"
    config.logging.file = "melodine.log"
    save_config(config, tmp_cwd / "config.yaml")
    return config


@pytest.fixture
def db(tmp_cwd: Path) -> Database:
    database = Database("melodine.db")
    yield database
    database.close()


@pytest.fixture
def mp3_file(tmp_cwd: Path) -> Path:
    path = tmp_cwd / "track.mp3"
    path.write_bytes(silent_mp3_bytes())
    return path


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


@pytest.fixture
def ffmpeg_audio(tmp_cwd: Path):
    """Factory fixture producing tiny real audio files via ffmpeg.

    Skips the test when ffmpeg is not installed.
    """

    def _make(name: str, codec: str) -> Path:
        if not ffmpeg_available():
            pytest.skip("ffmpeg not available")
        path = tmp_cwd / name
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=44100:cl=mono",
                "-t",
                "0.5",
                "-c:a",
                codec,
                str(path),
            ],
            check=True,
            capture_output=True,
        )
        return path

    return _make


@pytest.fixture
def tagger() -> Tagger:
    return Tagger()


def make_v1_database(path: Path) -> None:
    """Create a Melodine v1 schema database with sample rows."""
    conn = sqlite3.connect(str(path))
    conn.executescript(
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
            downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE sessions (
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
        """
    )
    conn.execute(
        "INSERT INTO downloads (query, artist, title, status, file_path, file_size) "
        "VALUES ('Daft Punk - Around the World', 'Daft Punk', 'Around the World', "
        "'success', '/music/daft.mp3', 12345)"
    )
    conn.execute(
        "INSERT INTO downloads (query, artist, title, status, file_path) "
        "VALUES ('Muse - Hysteria', 'Muse', 'Hysteria', 'failed', '')"
    )
    conn.execute(
        "INSERT INTO sessions (playlist_file, total_tracks, success, failed) "
        "VALUES ('list.txt', 2, 1, 1)"
    )
    conn.commit()
    conn.close()


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: object = None) -> None:
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> object:
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeSession:
    """Programmable requests.Session double for provider tests."""

    def __init__(self) -> None:
        self.responses: list[FakeResponse] = []
        self.requests: list[dict] = []

    def queue(self, response: FakeResponse) -> None:
        self.responses.append(response)

    def get(self, url, params=None, headers=None, timeout=None):
        self.requests.append(
            {"url": url, "params": params, "headers": headers, "timeout": timeout}
        )
        if not self.responses:
            raise AssertionError("no queued response")
        return self.responses.pop(0)
