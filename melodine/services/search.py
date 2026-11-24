"""YouTube search backed by yt-dlp, ranked by the Anti-MV Studio Scorer."""

from __future__ import annotations

import re
from typing import Any

import yt_dlp

from melodine.core.config import AppConfig
from melodine.core.logging import YtdlpLogger, get_logger
from melodine.models import IntentFlags, ScoredCandidate, SearchCandidate
from melodine.services import scoring

logger = get_logger("search")


def generate_search_queries(artist: str, title: str) -> list[str]:
    """Smart query variants - preserved from Melodine v1."""
    queries: list[str] = []
    original = f"{artist} - {title}" if artist else title
    queries.append(original)

    if artist:
        clean_artist = re.sub(r"\(.*?\)", "", artist).strip()
        clean_artist = re.sub(r"feat\.?.*", "", clean_artist, flags=re.IGNORECASE).strip()
        clean_title = re.sub(r"\(.*?\)", "", title).strip()

        if f"{clean_artist} - {clean_title}" != original:
            queries.append(f"{clean_artist} - {clean_title}")

        first_artist = re.split(r"[,&/]", artist)[0].strip()
        if first_artist != artist:
            queries.append(f"{first_artist} - {title}")

        queries.append(title)
        queries.append(f"{first_artist} - {title} official audio")

    return queries


class SearchService:
    """Search + rank pipeline shared by the TUI, CLI and watchlist sync."""

    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg

    # ------------------------------------------------------------------ #

    def search(self, query: str, limit: int | None = None) -> list[SearchCandidate]:
        """Run a raw yt-dlp ``ytsearch`` query (never raises).

        Flat extraction keeps this to a single request for N results
        (instead of N full extractions): dramatically faster and far less
        likely to trip YouTube's bot detection.
        """
        limit = limit or self.cfg.search.results
        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "extract_flat": True,
            "socket_timeout": self.cfg.download.timeout,
            "logger": YtdlpLogger(logger),
        }
        candidates: list[SearchCandidate] = []
        try:
            # NB: default_search + extract_flat returns an unresolved URL
            # stub in modern yt-dlp, so the prefix must be explicit.
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
            entries = (info or {}).get("entries") or [info]
            for entry in entries:
                if not entry:
                    continue
                candidate = SearchCandidate.from_ytdlp(entry)
                if candidate.source_id or candidate.url:
                    candidates.append(candidate)
        except Exception as exc:  # yt-dlp raises a wide variety
            logger.warning("search failed for %r: %s", query, exc)
        return candidates

    # ------------------------------------------------------------------ #

    def smart_search(
        self,
        artist: str,
        title: str,
        limit: int | None = None,
    ) -> list[SearchCandidate]:
        """Try the original query, then v1-style variants when nothing is found."""
        collected: list[SearchCandidate] = []
        seen: set[str] = set()

        for variant in generate_search_queries(artist, title):
            if len(collected) >= (limit or self.cfg.search.results):
                break
            for candidate in self.search(variant, limit):
                if candidate.source_id not in seen:
                    seen.add(candidate.source_id)
                    collected.append(candidate)
            if collected:
                break  # v1 semantics: use the first variant that yields results

        if not collected and self.cfg.download.smart_search:
            for variant in generate_search_queries(artist, title):
                for candidate in self.search(variant, limit):
                    if candidate.source_id not in seen:
                        seen.add(candidate.source_id)
                        collected.append(candidate)
        return collected

    # ------------------------------------------------------------------ #

    def best(
        self,
        query: str,
        *,
        intent: IntentFlags | None = None,
        expected_duration: float | None = None,
        target_title: str = "",
        target_artist: str = "",
    ) -> tuple[ScoredCandidate | None, list[ScoredCandidate]]:
        """Return ``(best_candidate, all_scored)`` using Anti-MV ranking.

        When the top score is below ``search.min_score`` and Smart Search is
        enabled, additional audio-biased query variants are merged in.
        """
        candidates = self.search(query)
        if not candidates and self.cfg.download.smart_search:
            candidates = self.smart_search(target_artist or "", query)

        scored = scoring.rank_candidates(
            candidates,
            target_title=target_title,
            target_artist=target_artist,
            expected_duration=expected_duration,
            intent=intent,
            penalize=self.cfg.search.anti_mv,
        )

        if (
            self.cfg.download.smart_search
            and (
                not scored
                or scored[0].score < self.cfg.search.min_score
                or (self.cfg.search.anti_mv and not scored[0].reasons)
            )
        ):
            seen = {item.candidate.source_id for item in scored}
            for variant in (f"{query} audio", f"{query} official audio", f"{query} topic"):
                for extra in scoring.rank_candidates(
                    self.search(variant),
                    target_title=target_title,
                    target_artist=target_artist,
                    expected_duration=expected_duration,
                    intent=intent,
                    penalize=self.cfg.search.anti_mv,
                ):
                    if extra.candidate.source_id not in seen:
                        seen.add(extra.candidate.source_id)
                        scored.append(extra)
            scored.sort(key=lambda item: item.score, reverse=True)

        return (scored[0] if scored else None), scored
