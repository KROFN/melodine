"""Watchlist subscriptions, playlist listing and M3U8 generation."""

from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yt_dlp

from melodine.core.config import AppConfig
from melodine.core.logging import YtdlpLogger, get_logger
from melodine.db.database import Database
from melodine.models import DownloadResult, DownloadTask, WatchlistEntry
from melodine.services.downloader import DownloadService
from melodine.utils import sanitize_filename

logger = get_logger("playlists")

MAX_PLAYLIST_ENTRIES = 1000


# --------------------------------------------------------------------------- #
# M3U8 writing
# --------------------------------------------------------------------------- #


def write_m3u8(
    path: str | Path,
    name: str,
    entries: list[dict[str, Any]],
    *,
    relative_to: str | Path | None = None,
) -> int:
    """Write an extended M3U8 playlist. Returns the number of entries."""
    lines = ["#EXTM3U"]
    if name:
        lines.append(f"#PLAYLIST:{name}")
    count = 0
    for entry in entries:
        filepath = str(entry.get("filepath") or "")
        if not filepath:
            continue
        if relative_to:
            with contextlib.suppress(ValueError):
                filepath = str(Path(filepath).relative_to(Path(relative_to)))
        duration = int(float(entry.get("duration") or 0))
        title = str(entry.get("title") or "")
        artist = str(entry.get("artist") or "")
        label = f"{artist} - {title}" if artist else title
        lines.append(f"#EXTINF:{duration},{label}")
        lines.append(filepath)
        count += 1
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return count


# --------------------------------------------------------------------------- #
# URL helpers
# --------------------------------------------------------------------------- #


def detect_kind(url: str) -> str:
    """Classify a YouTube URL as playlist / channel / unknown."""
    lowered = url.lower()
    if "list=" in lowered or "/playlist" in lowered:
        return "playlist"
    if any(marker in lowered for marker in ("/channel/", "/@")):
        return "channel"
    if re.search(r"youtube\.com/(c|user)/", lowered):
        return "channel"
    return "unknown"


def watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def list_playlist_entries(url: str, timeout: int = 30) -> list[dict[str, Any]]:
    """Flat-list a playlist or channel without downloading anything."""
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "playlistend": MAX_PLAYLIST_ENTRIES,
        "socket_timeout": timeout,
        "logger": YtdlpLogger(logger),
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        logger.warning("playlist listing failed for %s: %s", url, exc)
        return []
    if not info:
        return []

    raw: list[Any] = list(info.get("entries") or [])

    # Channel URLs return tab objects; prefer the "Videos" tab.
    if raw and all(isinstance(item, dict) and item.get("entries") is not None for item in raw):
        tabs = raw
        chosen = None
        for tab in tabs:
            title = str(tab.get("title") or "")
            if "videos" in title.lower():
                chosen = tab
                break
        if chosen is None and tabs:
            chosen = max(tabs, key=lambda t: len(list(t.get("entries") or [])))
        raw = list((chosen or {}).get("entries") or []) if chosen else []

    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        entry_id = str(item.get("id") or "")
        if not entry_id or entry_id in seen:
            continue
        seen.add(entry_id)
        entries.append(
            {
                "id": entry_id,
                "title": str(item.get("title") or ""),
                "duration": int(item.get("duration") or 0),
                "channel": str(item.get("channel") or item.get("uploader") or ""),
                "url": str(item.get("url") or item.get("webpage_url") or watch_url(entry_id)),
            }
        )
    return entries


# --------------------------------------------------------------------------- #
# Watchlist service
# --------------------------------------------------------------------------- #


@dataclass
class SyncReport:
    """Outcome of a single watchlist sync."""

    entry: WatchlistEntry
    listed: int = 0
    new: int = 0
    downloaded: int = 0
    failed: int = 0
    duplicates: int = 0
    results: list[DownloadResult] = field(default_factory=list)


class WatchlistService:
    """Track playlists/channels and pull only the new tracks."""

    def __init__(
        self, cfg: AppConfig, db: Database, service: DownloadService | None = None
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.service = service or DownloadService(cfg, db)

    # -- CRUD --------------------------------------------------------------- #

    def add(self, url: str, name: str = "", kind: str | None = None) -> WatchlistEntry:
        url = url.strip()
        resolved_kind = kind or detect_kind(url)
        if not name:
            name = self._guess_name(url, resolved_kind)
        playlist_path = self._playlist_path(name)
        entry = self.db.watchlist_add(url, name, resolved_kind, playlist_path)
        logger.info("watchlist added: %s (%s)", name, resolved_kind)
        return entry

    def remove(self, entry_id: int) -> bool:
        return self.db.watchlist_remove(entry_id)

    def list(self) -> list[WatchlistEntry]:
        return self.db.watchlist_list()

    # -- sync --------------------------------------------------------------- #

    def sync(
        self,
        entry: WatchlistEntry,
        *,
        reporter: Any = None,
    ) -> SyncReport:
        report = SyncReport(entry=entry)
        entries = list_playlist_entries(entry.url, timeout=self.cfg.download.timeout)
        report.listed = len(entries)
        if not entries:
            self.db.watchlist_update_synced(entry.id)
            return report

        known = self.db.watchlist_known_ids(entry.id)
        fresh = [item for item in entries if item["id"] not in known]
        report.new = len(fresh)

        for item in fresh:
            if self.service.shutdown is not None and self.service.shutdown.triggered:
                break
            existing = self.db.find_track(
                source_id=item["id"],
                artist=item["channel"],
                title=item["title"],
                duration=float(item["duration"] or 0),
                tolerance=self.cfg.search.duration_tolerance,
            )
            if existing is not None:
                # Known elsewhere in the library: mark as seen, no download.
                self.db.watchlist_add_known(entry.id, [item["id"]])
                report.duplicates += 1
                continue

            task = DownloadTask(
                url=item["url"],
                title=item["title"],
                artist=item["channel"],
                source="watchlist",
            )
            result = self.service.process(task, report=reporter)
            report.results.append(result)
            if result.status == "success":
                report.downloaded += 1
                self.db.watchlist_add_known(entry.id, [item["id"]])
            elif result.status == "skipped":
                report.duplicates += 1
                self.db.watchlist_add_known(entry.id, [item["id"]])
            else:
                report.failed += 1

        self.refresh_m3u8(entry)
        self.db.watchlist_update_synced(entry.id)
        return report

    def sync_all(self, *, reporter: Any = None) -> list[SyncReport]:
        return [self.sync(entry, reporter=reporter) for entry in self.list() if entry.active]

    # -- m3u8 --------------------------------------------------------------- #

    def refresh_m3u8(self, entry: WatchlistEntry) -> int:
        tracks = self.db.watchlist_tracks(entry.id)
        path = entry.playlist_path or self._playlist_path(entry.name)
        self.db.watchlist_set_playlist_path(entry.id, path)
        return write_m3u8(
            path,
            entry.name or "Melodine Watchlist",
            tracks,
            relative_to=Path(path).parent,
        )

    # -- helpers ------------------------------------------------------------ #

    def _playlist_path(self, name: str) -> str:
        base = self.cfg.watchlist.m3u8_folder or self.cfg.output.folder
        safe = sanitize_filename(name or "watchlist")
        return str(Path(base) / f"{safe}.m3u8")

    @staticmethod
    def _guess_name(url: str, kind: str) -> str:
        match = re.search(r"[?&]list=([A-Za-z0-9_-]+)", url)
        if match:
            return f"Playlist {match.group(1)[:12]}"
        match = re.search(r"/@([A-Za-z0-9_.-]+)", url)
        if match:
            return match.group(1)
        match = re.search(r"/channel/([A-Za-z0-9_-]+)", url)
        if match:
            return f"Channel {match.group(1)[:12]}"
        return "Watchlist" if kind == "unknown" else kind.title()
