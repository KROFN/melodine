import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, Event

import yt_dlp
from rich.progress import (
    Progress, SpinnerColumn, BarColumn, TextColumn,
    TimeRemainingColumn, MofNCompleteColumn,
)
from rich.live import Live
from rich.panel import Panel
from rich.console import Group

from melodine.config import AppConfig
from melodine.themes import Theme
from melodine.tagger import add_tags
from melodine.search import generate_search_queries
from melodine.database import record_download
from melodine.utils import sanitize_filename, format_size
from melodine.locales import t
from melodine.display import console


class DownloadResult:
    __slots__ = ("query", "artist", "title", "status", "attempts", "file_path", "file_size", "error")

    def __init__(self, query, artist, title):
        self.query = query
        self.artist = artist
        self.title = title
        self.status = "pending"
        self.attempts = 0
        self.file_path = ""
        self.file_size = 0
        self.error = ""


class DownloadEngine:
    def __init__(self, config: AppConfig, theme: Theme):
        self.config = config
        self.theme = theme
        self._lock = Lock()
        self._stop = Event()

        self.success_count = 0
        self.failed_count = 0
        self.skipped_count = 0
        self.retry_count = 0
        self.total_size = 0
        self.failed_list: list[str] = []
        self.last_done = ""

    def download_playlist(self, tracks: list[dict]) -> dict:
        output_dir = self.config.paths.output
        os.makedirs(output_dir, exist_ok=True)

        total = len(tracks)
        t0 = time.time()

        progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold]{task.description}"),
            BarColumn(complete_style=self.theme.bar_complete, finished_style=self.theme.success),
            MofNCompleteColumn(),
            TimeRemainingColumn(),
            console=console,
        )
        task_id = progress.add_task(t("dl_progress"), total=total)

        def status_panel():
            elapsed = time.time() - t0
            text = (
                f"[{self.theme.success}]✅ {self.success_count}[/]  "
                f"[{self.theme.error}]❌ {self.failed_count}[/]  "
                f"[{self.theme.warning}]🔄 {self.retry_count}[/]  "
                f"[{self.theme.muted}]⏭ {self.skipped_count}[/]  "
                f"[{self.theme.info}]💾 {format_size(self.total_size)}[/]  "
                f"[{self.theme.muted}]⏱ {int(elapsed)}s[/]"
            )
            if self.last_done:
                text += f"\n[{self.theme.muted}]{t('dl_last')}: [{self.theme.success}]✅ {self.last_done[:50]}[/]"
            return Panel(text, title=f"[{self.theme.title}]{t('dl_progress_title')}[/]", border_style=self.theme.border)

        with Live(Group(status_panel(), progress), console=console, refresh_per_second=4) as live:
            with ThreadPoolExecutor(max_workers=self.config.download.threads) as pool:
                futures = {pool.submit(self._download_one, tr, output_dir): tr for tr in tracks}

                for future in as_completed(futures):
                    if self._stop.is_set():
                        break

                    res: DownloadResult = future.result()
                    with self._lock:
                        if res.status == "success":
                            self.success_count += 1
                            self.total_size += res.file_size
                            self.last_done = res.query
                            if res.attempts > 1:
                                self.retry_count += 1
                        elif res.status == "skipped":
                            self.skipped_count += 1
                        else:
                            self.failed_count += 1
                            self.failed_list.append(res.query)

                    progress.update(task_id, advance=1)
                    live.update(Group(status_panel(), progress))

                    record_download(
                        query=res.query, artist=res.artist, title=res.title,
                        status=res.status, attempts=res.attempts,
                        file_path=res.file_path, file_size=res.file_size,
                    )

        return {
            "success": self.success_count, "failed": self.failed_count,
            "skipped": self.skipped_count, "retried": self.retry_count,
            "total": total, "elapsed": time.time() - t0,
            "total_size": self.total_size, "failed_list": self.failed_list,
        }

    def _download_one(self, track: dict, output_dir: str) -> DownloadResult:
        artist = track["artist"]
        title = track["title"]
        query = track["query"]
        res = DownloadResult(query, artist, title)

        fname = f"{artist} - {title}" if artist else title
        safe = sanitize_filename(fname)
        mp3_path = os.path.join(output_dir, f"{safe}.mp3")

        if os.path.exists(mp3_path):
            res.status = "skipped"
            res.file_path = mp3_path
            return res

        out_tpl = os.path.join(output_dir, f"{safe}.%(ext)s")
        cfg = self.config.download

        queries = generate_search_queries(artist, title) if cfg.smart_search else [query]

        ydl_opts = {
            "format": "bestaudio/best",
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": str(cfg.quality)}],
            "outtmpl": out_tpl,
            "noplaylist": True,
            "quiet": True, "no_warnings": True, "noprogress": True,
            "overwrites": True,
            "socket_timeout": cfg.timeout,
            "retries": 3, "fragment_retries": 3, "extractor_retries": 3,
            "match_filter": yt_dlp.utils.match_filter_func(f"duration < {cfg.max_duration}"),
        }

        last_err = ""
        for sq in queries:
            if self._stop.is_set():
                res.status = "failed"
                return res

            for attempt in range(1, cfg.retry_attempts + 1):
                if self._stop.is_set():
                    res.status = "failed"
                    return res

                res.attempts += 1
                try:
                    opts = {**ydl_opts, "default_search": "ytsearch1"}
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        ydl.download([sq])

                    if os.path.exists(mp3_path):
                        if self.config.metadata.add_tags and artist:
                            add_tags(mp3_path, artist, title)
                        res.status = "success"
                        res.file_path = mp3_path
                        res.file_size = os.path.getsize(mp3_path)
                        time.sleep(cfg.pause)
                        return res

                except Exception as e:
                    last_err = str(e)
                    if attempt < cfg.retry_attempts:
                        time.sleep(cfg.retry_delay * attempt)

        res.status = "failed"
        res.error = last_err
        return res

    def stop(self):
        self._stop.set()