"""The v2 download pipeline.

Stages (per task):

1. Resolve  - URL passthrough or Anti-MV ranked search
2. Inspect  - full yt-dlp metadata extraction + duration guard
3. Dedup    - source_id / fuzzy artist+title+duration duplicate check
4. Enrich   - iTunes -> MusicBrainz metadata with cleaned-source fallback
5. Download - yt-dlp with SponsorBlock -> ModifyChapters -> FFmpegExtractAudio
              (strictly in that postprocessor order)
6. Normalize- optional two-pass EBU R128 loudnorm (ffmpeg)
7. Artwork  - 16:9 -> 1:1 smart crop (Pillow) + embed
8. Lyrics   - LRCLIB synced/plain lookup + embed (+ optional .lrc file)
9. Tags     - mutagen tagging for mp3/flac/opus/ogg/m4a
10. Persist - library upsert + history record
"""

from __future__ import annotations

import contextlib
import os
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

import yt_dlp

from melodine.core.config import AppConfig
from melodine.core.exceptions import CancelledError
from melodine.core.logging import YtdlpLogger, get_logger
from melodine.core.shutdown import GracefulShutdown
from melodine.db.database import Database
from melodine.models import (
    CodecProfile,
    DownloadOptions,
    DownloadResult,
    DownloadTask,
    EnrichedMeta,
    SearchCandidate,
    get_codec_profile,
)
from melodine.services.artwork import crop_to_square
from melodine.services.dedup import normalize_name
from melodine.services.lrclib import LRCLIBClient, write_lrc_file
from melodine.services.metadata import MetadataEnricher
from melodine.services.normalize import normalize_file
from melodine.services.search import SearchService
from melodine.services.tagger import Tagger
from melodine.services.titles import clean_artist, clean_track_title
from melodine.utils import sanitize_filename

logger = get_logger("downloader")

Reporter = Callable[[str, DownloadTask, dict[str, Any]], None]

UNKNOWN_ARTIST = "Unknown Artist"
UNKNOWN_ALBUM = "Unknown Album"


def build_output_path(
    folder: str,
    template: str,
    *,
    artist: str,
    album: str,
    title: str,
    track_number: int | None,
    year: int | None,
    extension: str,
) -> Path:
    """Render the configured path template into a concrete file path."""
    parts = {
        "artist": sanitize_filename(artist or UNKNOWN_ARTIST),
        "album": sanitize_filename(album or UNKNOWN_ALBUM),
        "title": sanitize_filename(title or "Unknown Title"),
        "track_num": f"{track_number:02d}" if track_number else "01",
        "year": str(year) if year else "",
        "ext": extension,
    }
    relative = template.format(**parts)
    return Path(folder) / relative


class DownloadService:
    """Synchronous per-track pipeline (thread-safe by construction)."""

    def __init__(
        self,
        cfg: AppConfig,
        db: Database,
        *,
        shutdown: GracefulShutdown | None = None,
        options: DownloadOptions | None = None,
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.shutdown = shutdown
        self.options = options or DownloadOptions()
        self.search = SearchService(cfg)
        self.enricher = MetadataEnricher(cfg.metadata)
        self.lyrics_client = LRCLIBClient(
            rate_limit=cfg.lyrics.rate_limit_ms / 1000.0,
        )
        self.tagger = Tagger()

    # ------------------------------------------------------------------ #
    # option resolution
    # ------------------------------------------------------------------ #

    def _opt(self, name: str, config_value: object) -> object:
        override = getattr(self.options, name, None)
        return override if override is not None else config_value

    def effective_profile(self) -> tuple[CodecProfile, int]:
        codec_key = str(self._opt("codec", self.cfg.audio.codec))
        profile = get_codec_profile(codec_key)
        bitrate = int(self._opt("bitrate", self.cfg.audio.bitrate) or profile.default_bitrate)
        if profile.lossless:
            bitrate = 0
        return profile, bitrate

    # ------------------------------------------------------------------ #
    # resolution
    # ------------------------------------------------------------------ #

    def resolve(
        self, task: DownloadTask
    ) -> tuple[str, str, str, SearchCandidate | None]:
        """Return ``(url, artist_hint, title_hint, candidate)`` for a task."""
        if task.url:
            return task.url, task.artist, task.title, None
        best, _scored = self.search.best(
            task.query,
            intent=task.intent,
            target_title=task.title,
            target_artist=task.artist,
        )
        if best is None:
            raise RuntimeError("no search results")
        index = self.options.index
        if index and index > 1:
            # Caller picked a specific result: re-run search for the list.
            _top, scored = self.search.best(
                task.query,
                intent=task.intent,
                target_title=task.title,
                target_artist=task.artist,
            )
            if 0 < index <= len(scored):
                chosen = scored[index - 1]
                return (
                    chosen.candidate.url,
                    task.artist or chosen.candidate.channel,
                    task.title or chosen.candidate.title,
                    chosen.candidate,
                )
        return (
            best.candidate.url,
            task.artist or best.candidate.channel,
            task.title or best.candidate.title,
            best.candidate,
        )

    # ------------------------------------------------------------------ #
    # yt-dlp integration
    # ------------------------------------------------------------------ #

    def _build_ydl_opts(
        self,
        out_path: Path,
        profile: CodecProfile,
        bitrate: int,
        progress_hook: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        postprocessors: list[dict[str, Any]] = []

        sponsorblock_enabled = bool(self._opt("sponsorblock", self.cfg.sponsorblock.enabled))
        if sponsorblock_enabled:
            # Order is critical: SponsorBlock marks chapters, ModifyChapters
            # cuts them - both strictly BEFORE FFmpegExtractAudio.
            postprocessors.append({"key": "SponsorBlock", "when": "pre_process"})
            postprocessors.append(
                {
                    "key": "ModifyChapters",
                    "when": "pre_process",
                    "remove_sponsor_segments": list(self.cfg.sponsorblock.categories),
                    "force_keyframes": self.cfg.sponsorblock.force_keyframes,
                }
            )

        quality: str | None
        if profile.lossless:
            quality = None
        elif profile.yt_quality and not self._opt("bitrate", None):
            quality = profile.yt_quality
        else:
            quality = str(bitrate) if bitrate else profile.yt_quality

        postprocessors.append(
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": profile.yt_codec,
                "preferredquality": quality,
            }
        )

        opts: dict[str, Any] = {
            "format": "bestaudio/best",
            "outtmpl": str(out_path.with_suffix(".%(ext)s")),
            "postprocessors": postprocessors,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": False,
            "noprogress": True,
            "socket_timeout": self.cfg.download.timeout,
            "retries": self.cfg.download.retry_attempts,
            "fragment_retries": self.cfg.download.retry_attempts,
            "extractor_retries": 1,
            "logger": YtdlpLogger(logger),
            "windowsfilenames": True,
        }
        self._apply_cookies(opts)
        if progress_hook:
            opts["progress_hooks"] = [progress_hook]
        return opts

    def _apply_cookies(self, opts: dict[str, Any]) -> None:
        """Forward cookie configuration so datacenter/anti-bot setups work."""
        if self.cfg.download.cookies_file:
            opts["cookiefile"] = self.cfg.download.cookies_file
        if self.cfg.download.cookies_from_browser:
            opts["cookiesfrombrowser"] = (
                self.cfg.download.cookies_from_browser,
                None,
                None,
                None,
            )

    @staticmethod
    def _extract_info(url: str, opts: dict[str, Any], download: bool) -> dict[str, Any]:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=download)
        return info or {}

    @staticmethod
    def _find_final_file(info: dict[str, Any], expected: Path) -> Path:
        for requested in info.get("requested_downloads") or []:
            filepath = requested.get("filepath")
            if filepath and Path(filepath).exists():
                return Path(filepath)
        if expected.exists():
            return expected
        # Last resort: any file sharing the expected stem.
        for candidate in expected.parent.glob(f"{expected.stem}.*"):
            if candidate.suffix != ".part":
                return candidate
        raise FileNotFoundError(f"downloaded file not found near {expected}")

    # ------------------------------------------------------------------ #
    # metadata helpers
    # ------------------------------------------------------------------ #

    def _resolve_meta(
        self, info: dict[str, Any], artist_hint: str, title_hint: str
    ) -> tuple[str, str, EnrichedMeta | None]:
        raw_title = title_hint or str(info.get("title") or "")
        raw_artist = artist_hint or str(info.get("channel") or info.get("uploader") or "")
        cleaned = clean_track_title(raw_title)
        cleaned_artist = clean_artist(raw_artist) or UNKNOWN_ARTIST
        cleaned_title = cleaned.title or raw_title

        enriched: EnrichedMeta | None = None
        if bool(self._opt("enrich", self.cfg.metadata.enrich)):
            enriched = self.enricher.enrich(cleaned_artist, cleaned_title)

        if enriched is not None:
            artist = enriched.artist or cleaned_artist
            title = enriched.title or cleaned_title
        else:
            artist, title = cleaned_artist, cleaned_title
        return artist, title, enriched

    def _fetch_artwork(self, info: dict[str, Any], enriched: EnrichedMeta | None) -> bytes | None:
        if not bool(self._opt("artwork", self.cfg.artwork.embed)):
            return None
        from melodine.services import http

        # Prefer the clean, already-square 1000x1000 provider artwork.
        if enriched is not None and enriched.artwork_url:
            try:
                return http.get_bytes(enriched.artwork_url, timeout=15.0)
            except Exception as exc:
                logger.debug("provider artwork fetch failed: %s", exc)

        thumbnails = info.get("thumbnails") or []
        if info.get("thumbnail"):
            thumbnails.append({"url": info["thumbnail"]})
        best_url = ""
        best_area = 0
        for thumb in thumbnails:
            url = thumb.get("url") or ""
            width = int(thumb.get("width") or 0)
            height = int(thumb.get("height") or 0)
            area = width * height if width and height else 0
            if url and area >= best_area:
                best_area, best_url = area, url
        if not best_url:
            return None
        try:
            return http.get_bytes(best_url, timeout=15.0)
        except Exception as exc:
            logger.debug("thumbnail fetch failed: %s", exc)
            return None

    # ------------------------------------------------------------------ #
    # the pipeline
    # ------------------------------------------------------------------ #

    def process(
        self,
        task: DownloadTask,
        *,
        report: Reporter | None = None,
    ) -> DownloadResult:
        start = time.monotonic()
        result = DownloadResult(task=task)

        def _emit(event: str, **payload: Any) -> None:
            if report is not None:
                with contextlib.suppress(Exception):
                    report(event, task, payload)

        try:
            url, artist_hint, title_hint, candidate = self.resolve(task)
            _emit("resolve", url=url)

            # -- inspect ---------------------------------------------------
            inspect_opts: dict[str, Any] = {
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "socket_timeout": self.cfg.download.timeout,
                "logger": YtdlpLogger(logger),
            }
            self._apply_cookies(inspect_opts)
            try:
                info = self._extract_info(url, inspect_opts, download=False)
            except Exception as exc:
                # Full extraction can be blocked (datacenter IPs, bot
                # checks). Fall back to the metadata we already have from
                # search / task hints so dedup and tagging still work; the
                # actual download attempt will surface the real error.
                logger.warning("full metadata extraction failed (%s); "
                               "falling back to search metadata", exc)
                if candidate is None:
                    raise
                info = {
                    "id": candidate.source_id,
                    "title": candidate.title,
                    "channel": candidate.channel,
                    "duration": candidate.duration,
                    "thumbnail": None,
                    "thumbnails": [],
                }
            if not info:
                raise RuntimeError("yt-dlp returned no metadata")
            video_id = str(
                info.get("id")
                or (candidate.source_id if candidate else "")
                or task.task_id
            )
            duration = float(info.get("duration") or 0)

            if duration and duration > self.cfg.download.max_duration:
                raise RuntimeError(
                    f"track too long ({int(duration)}s > {self.cfg.download.max_duration}s)"
                )

            # -- dedup -----------------------------------------------------
            if bool(self._opt("dedup", True)):
                artist_probe = artist_hint or str(info.get("channel") or "")
                title_probe = title_hint or str(info.get("title") or "")
                existing = self.db.find_track(
                    source_id=video_id,
                    artist=artist_probe,
                    title=title_probe,
                    duration=duration,
                    tolerance=self.cfg.search.duration_tolerance,
                )
                if existing is not None:
                    result.status = "skipped"
                    result.duplicate = True
                    result.path = existing.get("filepath", "")
                    result.error = "duplicate"
                    _emit("done", result=result)
                    self._record_history(task, result)
                    return result
            # -- metadata --------------------------------------------------
            artist, title, enriched = self._resolve_meta(info, artist_hint, title_hint)
            album = (enriched.album if enriched else "") or UNKNOWN_ALBUM
            result.meta = self._meta_from(
                artist=artist,
                title=title,
                album=album,
                enriched=enriched,
                duration=duration,
            )

            profile, bitrate = self.effective_profile()
            folder = str(self._opt("folder", self.cfg.output.folder))
            out_path = build_output_path(
                folder,
                self.cfg.output.template,
                artist=artist,
                album=album,
                title=title,
                track_number=result.meta.track_number,
                year=result.meta.year,
                extension=profile.extension,
            )
            out_path.parent.mkdir(parents=True, exist_ok=True)

            if out_path.exists():
                result.status = "skipped"
                result.duplicate = True
                result.path = str(out_path)
                _emit("done", result=result)
                self._upsert_library(video_id, result, profile, bitrate)
                self._record_history(task, result, source_id=video_id)
                return result

            # -- download ----------------------------------------------------
            _emit("start", title=title, artist=artist, video_id=video_id)

            def _hook(data: dict[str, Any]) -> None:
                if self.shutdown is not None and self.shutdown.triggered:
                    raise CancelledError()
                if data.get("status") == "downloading":
                    _emit(
                        "progress",
                        downloaded=float(data.get("downloaded_bytes") or 0),
                        total=float(
                            data.get("total_bytes")
                            or data.get("total_bytes_estimate")
                            or 0
                        ),
                        speed=data.get("speed"),
                        eta=data.get("eta"),
                    )

            download_opts = self._build_ydl_opts(out_path, profile, bitrate, _hook)
            try:
                info = self._extract_info(url, download_opts, download=True)
            except Exception as exc:
                if "Sign in to confirm" in str(exc):
                    raise RuntimeError(
                        "YouTube requires verification for this IP "
                        "(bot check). Configure cookies in config.yaml "
                        "(download.cookies_from_browser or download.cookies_file) "
                        "or run from a residential connection."
                    ) from exc
                raise
            final_path = self._find_final_file(info, out_path)
            _emit("post", stage="download")

            # -- normalize ---------------------------------------------------
            if bool(self._opt("normalize", self.cfg.audio.normalize)):
                _emit("post", stage="normalize")
                result.normalized = normalize_file(
                    final_path,
                    profile,
                    bitrate=bitrate,
                    target_lufs=self.cfg.audio.target_lufs,
                    true_peak=self.cfg.audio.true_peak,
                    lra=self.cfg.audio.lra,
                )

            # -- artwork -----------------------------------------------------
            _emit("post", stage="artwork")
            artwork_bytes = self._fetch_artwork(info, enriched)
            if artwork_bytes and bool(self._opt("artwork", self.cfg.artwork.embed)):
                if bool(self.cfg.artwork.crop):
                    artwork_bytes = crop_to_square(
                        artwork_bytes, size=self.cfg.artwork.size
                    )
                result.meta.artwork = artwork_bytes

            # -- lyrics ------------------------------------------------------
            lyrics_record = None
            if bool(self._opt("lyrics", self.cfg.lyrics.enabled)):
                _emit("post", stage="lyrics")
                lyrics_record = self.lyrics_client.best_match(
                    artist,
                    title,
                    album="" if album == UNKNOWN_ALBUM else album,
                    duration=duration,
                    tolerance=self.cfg.lyrics.duration_tolerance,
                )
                result.lyrics = lyrics_record

            # -- tags --------------------------------------------------------
            _emit("post", stage="tags")
            if bool(self.cfg.tags.enabled):
                self.tagger.apply(final_path, result.meta, lyrics_record)
            if (
                lyrics_record is not None
                and self.cfg.lyrics.save_lrc
                and lyrics_record.has_synced
            ):
                try:
                    write_lrc_file(str(final_path), lyrics_record)
                except OSError as exc:
                    logger.warning("could not write .lrc file: %s", exc)

            # -- persist -----------------------------------------------------
            result.status = "success"
            result.path = str(final_path)
            try:
                result.filesize = os.path.getsize(final_path)
            except OSError:
                result.filesize = 0
            result.artwork_embedded = result.meta.artwork is not None
            result.sponsorblock = bool(
                self._opt("sponsorblock", self.cfg.sponsorblock.enabled)
            )
            self._upsert_library(video_id, result, profile, bitrate)
            self._record_history(task, result, source_id=video_id)
            _emit("done", result=result)
            return result

        except CancelledError:
            result.status = "cancelled"
            result.error = "cancelled"
            _emit("done", result=result)
            return result
        except Exception as exc:
            logger.error("download failed for %r: %s", task.query or task.url, exc)
            result.status = "failed"
            result.error = str(exc)
            _emit("done", result=result)
            self._record_history(task, result)
            return result
        finally:
            result.elapsed = time.monotonic() - start

    # ------------------------------------------------------------------ #
    # persistence helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _meta_from(
        *,
        artist: str,
        title: str,
        album: str,
        enriched: EnrichedMeta | None,
        duration: float,
    ) -> Any:
        from melodine.models import TrackMeta

        return TrackMeta(
            title=title,
            artist=artist,
            album=album,
            album_artist=(enriched.album_artist if enriched else "") or artist,
            genre=enriched.genre if enriched else "",
            year=enriched.year if enriched else None,
            track_number=enriched.track_number if enriched else None,
            track_total=enriched.track_total if enriched else None,
            duration=duration,
        )

    def _upsert_library(
        self, video_id: str, result: DownloadResult, profile: CodecProfile, bitrate: int
    ) -> None:
        meta = result.meta
        try:
            self.db.upsert_track(
                video_id,
                title=meta.title,
                artist=meta.artist,
                album=meta.album,
                album_artist=meta.album_artist,
                genre=meta.genre,
                year=meta.year,
                track_number=meta.track_number,
                duration=meta.duration,
                normalized_artist=normalize_name(meta.artist),
                normalized_title=normalize_name(meta.title),
                filepath=result.path,
                codec=profile.extension,
                bitrate=bitrate,
                filesize=result.filesize,
                artwork=result.artwork_embedded,
                lyrics="synced"
                if result.lyrics is not None and result.lyrics.has_synced
                else ("plain" if result.lyrics is not None and result.lyrics.has_plain else ""),
                normalized=result.normalized,
            )
        except Exception as exc:
            logger.warning("library upsert failed: %s", exc)

    def _record_history(
        self, task: DownloadTask, result: DownloadResult, source_id: str = ""
    ) -> None:
        try:
            self.db.record_download(
                query=task.query or task.url or result.meta.title,
                artist=result.meta.artist or task.artist,
                title=result.meta.title or task.title,
                status=result.status,
                file_path=result.path,
                file_size=result.filesize,
                source_id=source_id,
                message=result.error or "",
            )
        except Exception as exc:
            logger.warning("history record failed: %s", exc)


# --------------------------------------------------------------------------- #
# Threaded pool (TUI queue + CLI batch mode)
# --------------------------------------------------------------------------- #


class DownloadPool:
    """Thread pool running DownloadService tasks with live reporting."""

    def __init__(
        self,
        cfg: AppConfig,
        db: Database,
        *,
        shutdown: GracefulShutdown | None = None,
        options: DownloadOptions | None = None,
        reporter: Reporter | None = None,
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.shutdown = shutdown
        self.reporter = reporter
        self.service = DownloadService(cfg, db, shutdown=shutdown, options=options)
        self._executor: ThreadPoolExecutor | None = None
        self._jobs: list[tuple[Future[DownloadResult], DownloadTask]] = []
        self.results: list[DownloadResult] = []
        self._lock = threading.Lock()

    # -- lifecycle --------------------------------------------------------- #

    def start(self) -> None:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=self.cfg.download.threads,
                thread_name_prefix="melodine-dl",
            )

    def submit(self, task: DownloadTask) -> None:
        self.start()
        assert self._executor is not None
        self._jobs.append((self._executor.submit(self._run, task), task))

    def _run(self, task: DownloadTask) -> DownloadResult:
        if self.shutdown is not None and self.shutdown.triggered:
            result = DownloadResult(task=task, status="cancelled", error="cancelled")
            with self._lock:
                self.results.append(result)
            return result
        result = self.service.process(task, report=self._forward)
        with self._lock:
            self.results.append(result)
        if self.cfg.download.pause > 0:
            time.sleep(self.cfg.download.pause)
        return result

    def _forward(self, event: str, task: DownloadTask, payload: dict[str, Any]) -> None:
        if self.reporter is not None:
            self.reporter(event, task, payload)

    # -- status ------------------------------------------------------------ #

    @property
    def active_count(self) -> int:
        return sum(1 for future, _task in self._jobs if not future.done())

    @property
    def total(self) -> int:
        return len(self._jobs)

    def counts(self) -> dict[str, int]:
        with self._lock:
            results = list(self.results)
        return {
            "success": sum(1 for r in results if r.status == "success"),
            "failed": sum(1 for r in results if r.status == "failed"),
            "skipped": sum(1 for r in results if r.status == "skipped"),
            "cancelled": sum(1 for r in results if r.status == "cancelled"),
        }

    def wait(self, timeout: float | None = None) -> None:
        for future, _task in self._jobs:
            try:
                future.result(timeout=timeout)
            except Exception:
                continue

    def is_done(self) -> bool:
        return all(future.done() for future, _task in self._jobs)

    # -- graceful shutdown -------------------------------------------------- #

    def cancel_and_persist(self) -> int:
        """Interrupt running tasks and persist the unfinished ones."""
        for future, _task in self._jobs:
            future.cancel()
        # Give in-flight tasks a moment to observe the shutdown flag.
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not self.is_done():
            time.sleep(0.1)

        finished_ok = {
            result.task.task_id
            for result in self.results
            if result.status in {"success", "skipped"}
        }
        pending = [
            task
            for future, task in self._jobs
            if not future.done() and task.task_id not in finished_ok
        ]
        saved = self.db.save_queue(pending)
        self.shutdown_pool()
        return saved

    def shutdown_pool(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=False)
            self._executor = None
