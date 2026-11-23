"""Metadata enrichment: iTunes Search API with MusicBrainz fallback.

Providers are tried in configured order; results are validated with fuzzy
title/artist similarity so a wrong match never poisons the library.  On
failure the pipeline falls back to cleaned YouTube source tags.
"""

from __future__ import annotations

from typing import Any

from melodine import __user_agent__
from melodine.core.config import MetadataConfig
from melodine.core.logging import get_logger
from melodine.models import EnrichedMeta
from melodine.services import http
from melodine.services.titles import token_similarity

logger = get_logger("metadata")

ITUNES_URL = "https://itunes.apple.com/search"
MUSICBRAINZ_URL = "https://musicbrainz.org/ws/2/recording"

#: Minimum combined similarity for a provider match to be accepted.
MATCH_THRESHOLD = 0.45


class ItunesProvider:
    """Free, key-less iTunes Search API."""

    name = "itunes"

    def search(self, artist: str, title: str, timeout: float = 8.0) -> EnrichedMeta | None:
        try:
            payload = http.get_json(
                ITUNES_URL,
                params={"term": f"{artist} {title}".strip(), "entity": "song", "limit": 8},
                timeout=timeout,
            )
        except Exception as exc:
            logger.debug("itunes request failed: %s", exc)
            return None
        results = payload.get("results") if isinstance(payload, dict) else None
        if not results:
            return None

        best: tuple[float, dict[str, Any]] | None = None
        for result in results:
            if not isinstance(result, dict):
                continue
            similarity = 0.6 * token_similarity(str(result.get("trackName", "")), title)
            similarity += 0.4 * token_similarity(str(result.get("artistName", "")), artist)
            if best is None or similarity > best[0]:
                best = (similarity, result)
        if best is None or best[0] < MATCH_THRESHOLD:
            return None
        return EnrichedMeta.from_itunes(best[1])


class MusicBrainzProvider:
    """Open MusicBrainz recording search (respectful UA, single request)."""

    name = "musicbrainz"

    def search(self, artist: str, title: str, timeout: float = 8.0) -> EnrichedMeta | None:
        query = f'recording:"{title}" AND artist:"{artist}"'
        try:
            payload = http.get_json(
                MUSICBRAINZ_URL,
                params={"query": query, "fmt": "json", "limit": 5},
                headers={"User-Agent": __user_agent__},
                timeout=timeout,
            )
        except Exception as exc:
            logger.debug("musicbrainz request failed: %s", exc)
            return None
        recordings = payload.get("recordings") if isinstance(payload, dict) else None
        if not recordings:
            return None

        best: tuple[float, dict[str, Any]] | None = None
        for recording in recordings:
            if not isinstance(recording, dict):
                continue
            credits = recording.get("artist-credit") or []
            recording_artist = (
                str(credits[0].get("name", "")) if credits and isinstance(credits[0], dict) else ""
            )
            similarity = 0.6 * token_similarity(str(recording.get("title", "")), title)
            similarity += 0.4 * token_similarity(recording_artist, artist)
            if best is None or similarity > best[0]:
                best = (similarity, recording)
        if best is None or best[0] < MATCH_THRESHOLD:
            return None
        return EnrichedMeta.from_musicbrainz(best[1])


PROVIDERS: dict[str, type[ItunesProvider] | type[MusicBrainzProvider]] = {
    "itunes": ItunesProvider,
    "musicbrainz": MusicBrainzProvider,
}


class MetadataEnricher:
    """Chain-of-providers metadata resolver."""

    def __init__(self, cfg: MetadataConfig) -> None:
        self.cfg = cfg
        self._instances = [PROVIDERS[key]() for key in cfg.providers if key in PROVIDERS]

    def enrich(self, artist: str, title: str) -> EnrichedMeta | None:
        """Try each provider in order; first confident match wins."""
        if not self.cfg.enrich or not (artist and title):
            return None
        for provider in self._instances:
            try:
                result = provider.search(artist, title)
            except Exception as exc:  # defensive: providers must not break downloads
                logger.warning("provider %s crashed: %s", provider.name, exc)
                continue
            if result is not None:
                logger.info("enriched via %s: %s - %s", provider.name, result.artist, result.title)
                return result
        return None
