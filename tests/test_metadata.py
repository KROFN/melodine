"""Metadata enrichment tests (iTunes + MusicBrainz, fully mocked)."""

from __future__ import annotations

import pytest

from melodine.core.config import MetadataConfig
from melodine.services import metadata
from melodine.services.metadata import (
    MATCH_THRESHOLD,
    ItunesProvider,
    MetadataEnricher,
    MusicBrainzProvider,
)

ITUNES_PAYLOAD = {
    "resultCount": 2,
    "results": [
        {
            "trackName": "Around the World",
            "artistName": "Daft Punk",
            "collectionName": "Homework",
            "releaseDate": "1997-01-20T08:00:00Z",
            "primaryGenreName": "Electronic",
            "trackNumber": 7,
            "trackCount": 16,
            "trackTimeMillis": 428000,
            "artworkUrl100": "https://example.com/100x100bb.jpg",
        },
        {
            "trackName": "Totally Different Song",
            "artistName": "Other Artist",
            "collectionName": "Other Album",
        },
    ],
}

MB_PAYLOAD = {
    "recordings": [
        {
            "title": "Around the World",
            "artist-credit": [{"name": "Daft Punk"}],
            "releases": [{"title": "Homework", "date": "1997-01-20"}],
        }
    ],
}


class TestItunesProvider:
    def test_enrich_success(self, monkeypatch):
        monkeypatch.setattr(
            metadata.http, "get_json", lambda *a, **k: ITUNES_PAYLOAD
        )
        result = ItunesProvider().search("Daft Punk", "Around the World")
        assert result is not None
        assert result.title == "Around the World"
        assert result.artist == "Daft Punk"
        assert result.album == "Homework"
        assert result.year == 1997
        assert result.genre == "Electronic"
        assert result.track_number == 7
        assert result.track_total == 16
        assert result.duration == pytest.approx(428.0)
        assert result.artwork_url == "https://example.com/1000x1000bb.jpg"
        assert result.source == "itunes"

    def test_enrich_no_match(self, monkeypatch):
        monkeypatch.setattr(
            metadata.http,
            "get_json",
            lambda *a, **k: {"resultCount": 0, "results": []},
        )
        assert ItunesProvider().search("X", "Y") is None

    def test_enrich_network_error(self, monkeypatch):
        def boom(*args, **kwargs):
            raise ConnectionError("down")

        monkeypatch.setattr(metadata.http, "get_json", boom)
        assert ItunesProvider().search("X", "Y") is None

    def test_low_similarity_rejected(self, monkeypatch):
        monkeypatch.setattr(
            metadata.http, "get_json", lambda *a, **k: ITUNES_PAYLOAD
        )
        # Query has nothing in common with the payload's best result.
        assert ItunesProvider().search("Zzz Qqq", "Vvv Www") is None

    def test_params_sent(self, monkeypatch):
        captured: dict = {}

        def fake_get_json(url, params=None, headers=None, timeout=None):
            captured.update(url=url, params=params)
            return ITUNES_PAYLOAD

        monkeypatch.setattr(metadata.http, "get_json", fake_get_json)
        ItunesProvider().search("Daft Punk", "Around the World")
        assert captured["url"] == "https://itunes.apple.com/search"
        assert captured["params"]["entity"] == "song"
        assert "Daft Punk" in captured["params"]["term"]


class TestMusicBrainzProvider:
    def test_enrich_success(self, monkeypatch):
        monkeypatch.setattr(metadata.http, "get_json", lambda *a, **k: MB_PAYLOAD)
        result = MusicBrainzProvider().search("Daft Punk", "Around the World")
        assert result is not None
        assert result.title == "Around the World"
        assert result.artist == "Daft Punk"
        assert result.album == "Homework"
        assert result.year == 1997
        assert result.source == "musicbrainz"

    def test_enrich_empty(self, monkeypatch):
        monkeypatch.setattr(
            metadata.http, "get_json", lambda *a, **k: {"recordings": []}
        )
        assert MusicBrainzProvider().search("X", "Y") is None


class TestEnricherChain:
    def test_itunes_first_then_musicbrainz(self, monkeypatch):
        calls: list[str] = []
        payloads = [ITUNES_PAYLOAD, MB_PAYLOAD]

        def fake_get_json(url, params=None, headers=None, timeout=None):
            calls.append(url)
            return payloads[len(calls) - 1]

        monkeypatch.setattr(metadata.http, "get_json", fake_get_json)
        cfg = MetadataConfig(enrich=True, providers=["itunes", "musicbrainz"])
        enricher = MetadataEnricher(cfg)
        result = enricher.enrich("Daft Punk", "Around the World")
        assert result is not None
        assert result.source == "itunes"
        assert len(calls) == 1  # chain short-circuits on first success

    def test_falls_back_to_musicbrainz(self, monkeypatch):
        def fake_get_json(url, params=None, headers=None, timeout=None):
            if "itunes" in url:
                raise ConnectionError("down")
            return MB_PAYLOAD

        monkeypatch.setattr(metadata.http, "get_json", fake_get_json)
        cfg = MetadataConfig(enrich=True, providers=["itunes", "musicbrainz"])
        result = MetadataEnricher(cfg).enrich("Daft Punk", "Around the World")
        assert result is not None
        assert result.source == "musicbrainz"

    def test_disabled_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            metadata.http, "get_json", lambda *a, **k: ITUNES_PAYLOAD
        )
        cfg = MetadataConfig(enrich=False)
        assert MetadataEnricher(cfg).enrich("A", "B") is None

    def test_threshold_is_sane(self):
        assert 0 < MATCH_THRESHOLD < 1
