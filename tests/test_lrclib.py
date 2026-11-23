"""LRCLIB client tests (fully mocked network + clock)."""

from __future__ import annotations

import pytest

from melodine.models import LyricsRecord
from melodine.services.lrclib import (
    LRCLIBClient,
    format_lrc,
    parse_lrc,
    write_lrc_file,
)
from tests.conftest import FakeResponse, FakeSession

SYNCED = "[00:01.00]First line\n[00:05.50]Second line\n"


def make_client(session: FakeSession) -> LRCLIBClient:
    sleeps: list[float] = []
    clock = [0.0]

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock[0] += seconds

    client = LRCLIBClient(
        rate_limit=0.35,
        session=session,
        sleeper=fake_sleep,
        clock=lambda: clock[0],
    )
    client._sleep_log = sleeps  # type: ignore[attr-defined]
    return client


class TestGet:
    def test_get_success(self):
        session = FakeSession()
        session.queue(
            FakeResponse(
                payload={
                    "id": 1,
                    "trackName": "Song",
                    "artistName": "Artist",
                    "albumName": "Album",
                    "duration": 200.5,
                    "plainLyrics": "plain text",
                    "syncedLyrics": SYNCED,
                    "instrumental": False,
                }
            )
        )
        client = make_client(session)
        record = client.get("Artist", "Song", album="Album", duration=200)
        assert record is not None
        assert record.track_name == "Song"
        assert record.artist_name == "Artist"
        assert record.has_synced and record.has_plain
        assert record.duration == pytest.approx(200.5)

    def test_get_404_returns_none(self):
        session = FakeSession()
        session.queue(FakeResponse(status_code=404))
        client = make_client(session)
        assert client.get("Artist", "Unknown Song") is None

    def test_user_agent_sent(self):
        session = FakeSession()
        session.queue(FakeResponse(status_code=404))
        client = make_client(session)
        client.get("Artist", "Song")
        request = session.requests[0]
        assert request["headers"]["User-Agent"].startswith("Melodine/2.0")

    def test_rate_limit_pause_between_requests(self):
        session = FakeSession()
        session.queue(FakeResponse(status_code=404))
        session.queue(FakeResponse(status_code=404))
        client = make_client(session)
        client.get("Artist", "Song")
        client.get("Artist", "Song2")
        # The second request must have waited for the rate limit window.
        assert any(s > 0 for s in client._sleep_log)  # type: ignore[attr-defined]


class TestSearch:
    def test_search_parses_list(self):
        session = FakeSession()
        session.queue(
            FakeResponse(
                payload=[
                    {
                        "trackName": "Song",
                        "artistName": "Artist",
                        "duration": 200,
                        "plainLyrics": "text",
                        "syncedLyrics": SYNCED,
                    },
                    {
                        "trackName": "Song",
                        "artistName": "Cover Band",
                        "duration": 180,
                        "plainLyrics": None,
                        "syncedLyrics": None,
                    },
                ]
            )
        )
        client = make_client(session)
        records = client.search("Artist", "Song")
        assert len(records) == 2
        assert records[0].has_synced
        assert not records[1].has_synced

    def test_network_error_returns_empty(self):
        import requests

        session = FakeSession()

        def boom(*args, **kwargs):
            raise requests.exceptions.ConnectionError("offline")

        session.get = boom  # type: ignore[method-assign]
        client = make_client(session)
        assert client.search("Artist", "Song") == []


class TestBestMatch:
    def test_exact_get_wins(self):
        session = FakeSession()
        session.queue(
            FakeResponse(
                payload={
                    "trackName": "Song",
                    "artistName": "Artist",
                    "duration": 200,
                    "plainLyrics": "plain",
                    "syncedLyrics": SYNCED,
                }
            )
        )
        client = make_client(session)
        record = client.best_match("Artist", "Song", duration=200)
        assert record is not None and record.has_synced
        assert len(session.requests) == 1

    def test_fallback_search_prefers_synced_and_duration(self):
        session = FakeSession()
        session.queue(FakeResponse(status_code=404))
        session.queue(
            FakeResponse(
                payload=[
                    {
                        "trackName": "Song",
                        "artistName": "Artist",
                        "duration": 250,  # wrong duration, no lyrics
                        "plainLyrics": None,
                        "syncedLyrics": None,
                    },
                    {
                        "trackName": "Song",
                        "artistName": "Artist",
                        "duration": 201,  # in tolerance, synced
                        "plainLyrics": "plain",
                        "syncedLyrics": SYNCED,
                    },
                ]
            )
        )
        client = make_client(session)
        record = client.best_match("Artist", "Song", duration=200, tolerance=3)
        assert record is not None
        assert record.duration == 201
        assert record.has_synced


class TestLRC:
    def test_parse_lrc(self):
        lines = parse_lrc(SYNCED)
        assert lines == [(1000, "First line"), (5500, "Second line")]

    def test_parse_lrc_multiple_timestamps(self):
        lines = parse_lrc("[00:01.00][00:09.00]Chorus")
        assert lines == [(1000, "Chorus"), (9000, "Chorus")]

    def test_parse_lrc_ignores_metadata(self):
        lines = parse_lrc("[ti:Song]\n[00:01.00]Line")
        assert lines == [(1000, "Line")]

    def test_roundtrip(self):
        lines = [(1000, "First"), (5500, "Second")]
        text = format_lrc(lines, title="Song", artist="Artist")
        assert "[ti:Song]" in text
        assert "[ar:Artist]" in text
        assert parse_lrc(text) == lines

    def test_write_lrc_file(self, tmp_path):
        audio = tmp_path / "track.opus"
        audio.write_bytes(b"x")
        record = LyricsRecord(synced=SYNCED)
        lrc_path = write_lrc_file(str(audio), record)
        assert lrc_path == str(tmp_path / "track.lrc")
        assert SYNCED in PathRead(lrc_path)


def PathRead(path: str) -> str:
    from pathlib import Path

    return Path(path).read_text(encoding="utf-8")
