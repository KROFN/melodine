"""LRCLIB.net client - synced karaoke lyrics engine.

* Correct User-Agent identifying Melodine
* 350 ms (configurable) rate-limit pause between requests, enforced with a
  lock so the limit holds globally across worker threads
* Exact ``/api/get`` lookup first, fuzzy ``/api/search`` fallback with
  duration filtering and preference for synced lyrics (a synced fuzzy hit
  beats a plain-only exact hit)
"""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable
from typing import Any

import requests

from melodine import __user_agent__
from melodine.core.logging import get_logger
from melodine.models import LyricsRecord

logger = get_logger("lrclib")

BASE_URL = "https://lrclib.net/api"
DEFAULT_TIMEOUT = 10.0
DEFAULT_RATE_LIMIT = 0.35  # seconds between requests


class LRCLIBClient:
    """Thin, polite client for https://lrclib.net.

    Thread-safe: ``DownloadPool`` shares one client between worker threads,
    so both the rate-limit throttle and the HTTP request itself run under
    the same lock - the polite 350 ms pause is a *global* guarantee.
    """

    def __init__(
        self,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        rate_limit: float = DEFAULT_RATE_LIMIT,
        session: requests.Session | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.timeout = timeout
        self.rate_limit = max(0.0, rate_limit)
        self._session = session
        self._sleeper = sleeper
        self._clock = clock
        self._last_request_at = 0.0
        self._request_lock = threading.Lock()

    # ------------------------------------------------------------------ #

    @property
    def session(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({"User-Agent": __user_agent__})
        return self._session

    def _throttle(self) -> None:
        """Enforce the rate limit pause between consecutive requests."""
        if self.rate_limit <= 0:
            return
        now = self._clock()
        elapsed = now - self._last_request_at
        wait = self.rate_limit - elapsed
        if wait > 0:
            self._sleeper(wait)
        self._last_request_at = self._clock()

    def _get(self, endpoint: str, params: dict[str, Any]) -> Any:
        """GET an endpoint returning parsed JSON, or None on any failure."""
        with self._request_lock:
            self._throttle()
            url = f"{BASE_URL}/{endpoint}"
            try:
                response = self.session.get(
                    url,
                    params=params,
                    headers={"User-Agent": __user_agent__},
                    timeout=self.timeout,
                )
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                return response.json()
            except requests.RequestException as exc:
                logger.debug(
                    "LRCLIB request failed (%s %s): %s", endpoint, params, exc
                )
                return None
            except ValueError as exc:
                logger.debug("LRCLIB returned invalid JSON: %s", exc)
                return None

    # ------------------------------------------------------------------ #

    def get(
        self,
        artist: str,
        title: str,
        album: str = "",
        duration: float | None = None,
    ) -> LyricsRecord | None:
        """Exact lookup via /api/get (returns None when not found)."""
        if not artist or not title:
            return None
        params: dict[str, Any] = {
            "artist_name": artist,
            "track_name": title,
        }
        if album:
            params["album_name"] = album
        if duration is not None and duration > 0:
            params["duration"] = round(duration)
        payload = self._get("get", params)
        if not isinstance(payload, dict):
            return None
        return LyricsRecord.from_api(payload)

    def search(
        self,
        artist: str,
        title: str,
        limit: int = 10,
    ) -> list[LyricsRecord]:
        """Fuzzy search via /api/search."""
        if not title:
            return []
        params: dict[str, Any] = {
            "track_name": title,
            "limit": limit,
        }
        if artist:
            params["artist_name"] = artist
        payload = self._get("search", params)
        if not isinstance(payload, list):
            return []
        return [LyricsRecord.from_api(item) for item in payload if isinstance(item, dict)]

    # ------------------------------------------------------------------ #

    def best_match(
        self,
        artist: str,
        title: str,
        album: str = "",
        duration: float | None = None,
        tolerance: float = 3.0,
    ) -> LyricsRecord | None:
        """Strategy: exact get -> search with duration + synced preference.

        Ranking of outcomes:

        1. exact ``/api/get`` hit that has *synced* lyrics (gold standard:
        right artist, right track, karaoke timing)
        2. fuzzy hit with synced lyrics within the duration tolerance
        (synced karaoke beats a plain-only exact hit)
        3. exact hit with plain lyrics only
        4. best fuzzy hit (duration-aware, synced preferred)
        """
        exact = self.get(artist, title, album=album, duration=duration)
        if exact is not None and exact.has_synced:
            return exact

        records = self.search(artist, title)
        best_fuzzy: LyricsRecord | None = None
        if records:

            def _duration_penalty(item: LyricsRecord) -> float:
                if duration is None or duration <= 0 or item.duration <= 0:
                    return 0.0
                return abs(item.duration - duration)

            def _in_tolerance(item: LyricsRecord) -> bool:
                return bool(
                    duration
                    and duration > 0
                    and item.duration > 0
                    and abs(item.duration - duration) <= tolerance
                )

            def _rank_key(item: LyricsRecord) -> tuple[int, int, int, float]:
                in_tolerance = 1 if _in_tolerance(item) else 0
                has_lyrics = 1 if (item.has_synced or item.has_plain) else 0
                has_synced = 1 if item.has_synced else 0
                return (has_lyrics, in_tolerance, has_synced, -_duration_penalty(item))

            ranked = sorted(records, key=_rank_key, reverse=True)
            if ranked[0].has_synced or ranked[0].has_plain:
                best_fuzzy = ranked[0]

        # Synced karaoke beats a plain-only exact hit.
        if (
            best_fuzzy is not None
            and best_fuzzy.has_synced
            and _in_tolerance(best_fuzzy)
        ):
            return best_fuzzy
        if exact is not None and (exact.has_synced or exact.has_plain):
            return exact
        return best_fuzzy


# --------------------------------------------------------------------------- #
# LRC parsing / serialization
# --------------------------------------------------------------------------- #

_LRC_LINE = re.compile(r"((?:\[\d{1,2}:\d{1,2}(?:[.:]\d{1,3})?\])+)(.*)")


def parse_lrc(text: str) -> list[tuple[int, str]]:
    """Parse LRC text into ``[(milliseconds, line), ...]``."""
    result: list[tuple[int, str]] = []
    for raw_line in (text or "").splitlines():
        match = _LRC_LINE.match(raw_line.strip())
        if not match:
            continue
        stamps, content = match.group(1), match.group(2).strip()
        for stamp in re.findall(r"\[(\d{1,2}):(\d{1,2})(?:[.:](\d{1,3}))?\]", stamps):
            minutes = int(stamp[0])
            seconds = int(stamp[1])
            fraction = stamp[2] or "0"
            ms = int(fraction.ljust(3, "0")) if fraction else 0
            total_ms = (minutes * 60 + seconds) * 1000 + ms
            result.append((total_ms, content))
    result.sort(key=lambda pair: pair[0])
    return result


def format_lrc(lines: list[tuple[int, str]], title: str = "", artist: str = "") -> str:
    """Serialize ``[(ms, line), ...]`` back into LRC text."""
    parts: list[str] = ["[re:Melodine]"]
    if title:
        parts.append(f"[ti:{title}]")
    if artist:
        parts.append(f"[ar:{artist}]")
    for ms, content in lines:
        minutes, rem = divmod(ms // 1000, 60)
        centis = (ms % 1000) // 10
        parts.append(f"[{minutes:02d}:{rem:02d}.{centis:02d}]{content}")
    return "\n".join(parts) + "\n"


def write_lrc_file(audio_path: str, record: LyricsRecord) -> str:
    """Persist a paired ``.lrc`` file next to the audio file. Returns its path."""
    base = audio_path.rsplit(".", 1)[0] if "." in audio_path else audio_path
    lrc_path = f"{base}.lrc"
    content = record.synced if record.has_synced else record.plain
    with open(lrc_path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return lrc_path
