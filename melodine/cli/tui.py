"""Melodine TUI - the flagship interactive experience.

Screens: dashboard menu, live search with Anti-MV previews, download queue
with per-track progress bars (speed + ETA), history & library, watchlist
management, lyrics tool, doctor, export, and a full settings section.
Hotkeys: [t] cycle theme, [g] toggle RU/EN, [q] quit (graceful).
"""

from __future__ import annotations

import contextlib
import os
import time
from pathlib import Path
from typing import Any

from rich import box
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table
from rich.text import Text

from melodine.core.config import AppConfig, save_config
from melodine.core.shutdown import GracefulShutdown
from melodine.db.database import Database
from melodine.i18n import get_language, set_language, t
from melodine.models import CODEC_PRESETS, DownloadTask, ScoredCandidate
from melodine.services.doctor import run_checks
from melodine.services.downloader import DownloadPool
from melodine.services.exporter import Exporter
from melodine.services.lrclib import LRCLIBClient, write_lrc_file
from melodine.services.playlists import WatchlistService
from melodine.services.search import SearchService
from melodine.services.tagger import Tagger, is_audio_file
from melodine.ui import shell
from melodine.ui.themes import Theme, get_theme, list_themes
from melodine.ui.widgets import (
    ProgressBridge,
    QueueLive,
    build_progress,
    console,
    render_download_results,
    render_score_reasons,
    render_scored_results,
    render_stats,
)
from melodine.utils import parse_playlist

IS_WINDOWS = os.name == "nt"

MENU_ITEMS = [
    ("1", "menu_search"),
    ("2", "menu_playlist"),
    ("3", "menu_queue"),
    ("4", "menu_history"),
    ("5", "menu_watchlist"),
    ("6", "menu_lyrics_tool"),
    ("7", "menu_doctor"),
    ("8", "menu_export"),
    ("9", "menu_settings"),
    ("h", "menu_guide"),
    ("0", "menu_exit"),
]

SETTINGS_ITEMS = [
    ("1", "settings_audio"),
    ("2", "settings_search"),
    ("3", "settings_sponsorblock"),
    ("4", "settings_lyrics"),
    ("5", "settings_artwork"),
    ("6", "settings_paths"),
    ("7", "settings_theme"),
    ("8", "settings_language"),
    ("9", "settings_show"),
    ("r", "settings_reset"),
    ("0", "settings_back"),
]


class MelodineTUI:
    """The interactive Melodine application."""

    def __init__(self, cfg: AppConfig, *, first_run: bool = False) -> None:
        self.cfg = cfg
        self.first_run = first_run
        self.theme: Theme = shell.display_theme(get_theme(cfg.theme), console)
        set_language(cfg.language)
        self.db = Database(cfg.database.path)
        self.shutdown = GracefulShutdown()
        self.shutdown.on_shutdown(self._on_shutdown)
        self.search = SearchService(cfg)
        self.watchlist = WatchlistService(cfg, self.db)
        self.pool: DownloadPool | None = None
        self.bridge: ProgressBridge | None = None
        self._theme_keys = [key for key, _label in list_themes()]
        self._home_selection = "1"
        self._settings_selection = "1"

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #

    def run(self) -> None:
        self.shutdown.install()
        try:
            if self.first_run:
                self._first_run_flow()
            self._offer_resume()
            while not self.shutdown.triggered:
                try:
                    if not self._main_menu():
                        break
                except KeyboardInterrupt:
                    break
        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        if self.pool is not None and not self.pool.is_done():
            with contextlib.suppress(Exception):
                self.pool.cancel_and_persist()
        self.shutdown.restore()
        self.db.close()
        console.print(f"[{self.theme.subtitle}]{t('goodbye')}[/]")

    def _on_shutdown(self) -> None:
        # Deliberately does NOT touch the download pool: the queue screen
        # asks the user first ("stop downloads?") and only cancels on
        # confirmation, and the exit path persists via _cleanup(). Cancelling
        # here would make the interactive prompt pointless - the pool would
        # already be dead before the user answered.
        return

    # ------------------------------------------------------------------ #
    # dashboard & menu
    # ------------------------------------------------------------------ #

    def _clear_screen(self) -> None:
        """Redraw only interactive terminals; preserve redirected output."""
        if not console.is_terminal or console.is_dumb_terminal:
            return
        if IS_WINDOWS:
            # Rich's legacy Win32 renderer handles HOME but not CLEAR:
            # Console.clear() moves the cursor over the old screen contents.
            # Use the native cls command, as Melodine v1 did.
            os.system("cls")
        else:
            console.clear()

    def _screen(self, title: str) -> None:
        self._clear_screen()
        shell.header(console, self.theme, title)

    def _menu_items(self) -> list[tuple[str, str]]:
        labels = dict(MENU_ITEMS)
        tr = shell.tr
        return [
            ("", tr("ЗАГРУЗКА", "DOWNLOAD")),
            *[(k, t(labels[k])) for k in ("1", "2", "3")],
            ("", tr("МЕДИАТЕКА", "LIBRARY")),
            *[(k, t(labels[k])) for k in ("4", "5", "6", "8")],
            ("", tr("ПРИЛОЖЕНИЕ", "APPLICATION")),
            *[(k, t(labels[k])) for k in ("9", "7", "h")],
            ("t", tr("Выбрать тему", "Choose theme")),
            ("g", tr("Выбрать язык", "Choose language")),
            ("0", t("menu_exit")),
        ]

    def _draw_dashboard(self) -> None:
        self._clear_screen()
        shell.header(console, self.theme, shell.tr("Главная", "Home"), home=True)
        stats = self.db.get_stats()
        active = self.pool.active_count if self.pool else 0
        codec = self.cfg.audio.codec.upper()
        if codec != "FLAC":
            codec += f" · {self.cfg.audio.bitrate} kbps"
        shell.status_grid(console, self.theme, [
            (t("library_title"), str(self.db.count_tracks())),
            (t("stats_success"), str(stats["success"])),
            (t("queue_title"), str(active)),
            (shell.tr("Формат", "Format"), codec),
        ])
        detail = Text(f"{self.theme.label}  ·  {get_language().upper()}  ·  ",
                      style=self.theme.muted)
        detail.append(str(Path(self.cfg.output.folder).expanduser()), style=self.theme.accent)
        console.print(detail)
        if not shell.keyboard_available(console):
            shell.choice_rows(console, self.theme, self._menu_items())
            console.print(Text(t("menu_hint"), style=self.theme.muted))
        console.print()

    def _main_menu(self) -> bool:
        """One menu iteration; returns False to exit."""
        if shell.keyboard_available(console):
            from melodine.ui.workspace import workspace_select

            stats = self.db.get_stats()
            tr = shell.tr
            details = {
                "1": tr("Найди трек, сравни версии и скачай подходящую.",
                        "Find a track, compare versions and download the right one."),
                "2": tr("Импорт списка треков из текстового файла.",
                        "Import a track list from a text file."),
                "3": tr("Прогресс, скорость и состояние загрузок.",
                        "Download progress, speed and status."),
                "4": tr("Скачанные треки, история и статистика.",
                        "Downloaded tracks, history and statistics."),
                "5": tr("Отслеживай обновления плейлистов и каналов.",
                        "Track playlist and channel updates."),
                "6": tr("Найди и добавь тексты в существующие аудиофайлы.",
                        "Find and add lyrics to existing audio files."),
                "7": tr("Проверь FFmpeg, yt-dlp и доступность сервисов.",
                        "Check FFmpeg, yt-dlp and service connectivity."),
                "8": tr("Экспортируй медиатеку в M3U8 или JSON.",
                        "Export your library to M3U8 or JSON."),
                "9": tr("Формат аудио, качество, поиск, папки и оформление.",
                        "Audio format, quality, search, folders and appearance."),
                "h": tr("Короткое руководство и примеры использования.",
                        "Quick guide and examples."),
                "t": tr("Выбери одну из 12 цветовых палитр.",
                        "Choose one of 12 color palettes."),
                "g": tr("Переключи язык интерфейса.", "Switch the interface language."),
                "0": tr("Закрыть приложение.", "Close the application."),
            }
            codec = self.cfg.audio.codec.upper()
            if codec != "FLAC":
                codec += f" · {self.cfg.audio.bitrate} kbps"
            choice = workspace_select(
                console, self.theme, tr("Главная", "Home"), self._menu_items(), details,
                [(tr("Треков в медиатеке", "Library tracks"), str(self.db.count_tracks())),
                 (t("stats_success"), str(stats["success"])),
                 (tr("Формат аудио", "Audio format"), codec),
                 (tr("Оформление", "Appearance"),
                  self.theme.label + " · " + get_language().upper())],
                default=self._home_selection, context=str(
                    Path(self.cfg.output.folder).expanduser().resolve()),
            )
        else:
            self._draw_dashboard()
            choice = shell.select(
                console, self.theme, t("menu_prompt"), self._menu_items(),
                default=self._home_selection, show_rows=False,
            )
        self._home_selection = choice

        if choice in {"q", "quit", "exit", "0"}:
            return False
        if choice == "t":
            self._settings_theme()
            return True
        if choice == "g":
            self._choose_language()
            return True

        handlers = {
            "1": self.screen_search,
            "2": self.screen_playlist,
            "3": self.screen_queue,
            "4": self.screen_history,
            "5": self.screen_watchlist,
            "6": self.screen_lyrics_tool,
            "7": self.screen_doctor,
            "8": self.screen_export,
            "9": self.screen_settings,
            "h": self.screen_guide,
        }
        handler = handlers.get(choice)
        if handler is not None:
            handler()
        else:
            console.print(t("invalid_value"))
            self._wait_enter()
        return True

    def _wait_enter(self) -> None:
        console.print()
        console.input(Text("← " + t("press_enter"), style=self.theme.muted))

    # ------------------------------------------------------------------ #
    # hotkey actions
    # ------------------------------------------------------------------ #

    def _cycle_theme(self) -> None:
        try:
            current = self._theme_keys.index(self.cfg.theme)
        except ValueError:
            current = 0
        nxt = self._theme_keys[(current + 1) % len(self._theme_keys)]
        self.cfg.theme = nxt
        self.theme = shell.display_theme(get_theme(nxt), console)
        with contextlib.suppress(OSError):
            save_config(self.cfg)
        label = dict(list_themes()).get(nxt, nxt)
        console.print(f"[{self.theme.success}]{t('theme_changed', name=label)}[/]")

    def _toggle_language(self) -> None:
        new_lang = "en" if get_language() == "ru" else "ru"
        self.cfg.language = new_lang
        set_language(new_lang)
        with contextlib.suppress(OSError):
            save_config(self.cfg)
        console.print(f"[{self.theme.success}]{t('lang_changed')}[/]")

    def _choose_language(self) -> None:
        self._screen("Language / Язык")
        shell.heading(console, self.theme, "Language / Язык",
                      "Choose the interface language / Выберите язык интерфейса")
        choice = shell.select(
            console, self.theme, "Language / Язык",
            [("1", "Русский"), ("2", "English"), ("0", "Back / Назад")],
            default="1" if self.cfg.language == "ru" else "2",
        )
        if choice != "0":
            self.cfg.language = "ru" if choice == "1" else "en"
            set_language(self.cfg.language)
            self._save()

    def _first_run_flow(self) -> None:
        self._choose_language()
        self.screen_guide()

    def screen_guide(self) -> None:
        self._screen(t("guide_title"))
        shell.heading(console, self.theme, shell.tr("Начни с одного трека", "Start with one track"),
                      t("guide_intro"))
        steps = Table.grid(padding=(0, 1), expand=True)
        steps.add_column(width=4, style=f"bold {self.theme.accent}")
        steps.add_column(ratio=1)
        for number, label, hint in [
            ("01", t("menu_search"), t("guide_search")),
            ("02", t("menu_playlist"), t("guide_playlist")),
            ("03", t("menu_settings"), t("guide_settings")),
            ("04", t("menu_doctor"), t("guide_doctor")),
        ]:
            body = Text(label + "\n", style="bold")
            body.append(hint, style=self.theme.muted)
            steps.add_row(number, body)
            steps.add_row("", "")
        console.print(shell.panel(console, self.theme, steps, t("guide_title")))
        console.print(Text(t("guide_output", path=str(
            Path(self.cfg.output.folder).expanduser().resolve())), style=self.theme.accent))
        console.print(Text(t("guide_resume"), style=self.theme.muted))
        console.print(Text(shell.tr(
            "↑↓ и Enter — выбор · Esc — назад · h — справка",
            "↑↓ and Enter — select · Esc — back · h — guide",
        ), style=self.theme.muted))
        self._wait_enter()

    def _offer_resume(self) -> None:
        pending = self.db.load_queue()
        if not pending:
            return
        console.print(f"[{self.theme.warning}]{t('queue_resume_prompt', n=len(pending))}[/]")
        if Confirm.ask("", default=True):
            console.print(
                f"[{self.theme.info}]{t('queue_resumed', n=len(pending))}[/]"
            )
            self._start_batch(pending)

    # ------------------------------------------------------------------ #
    # batch runner (queue screen)
    # ------------------------------------------------------------------ #

    def _start_batch(self, tasks: list[DownloadTask]) -> None:
        """Create a fresh pool and jump straight into the live queue screen."""
        progress = build_progress(self.theme)
        self.bridge = ProgressBridge(progress, self.theme)
        self.pool = DownloadPool(
            self.cfg, self.db, shutdown=self.shutdown, reporter=self.bridge
        )
        for task in tasks:
            self.pool.submit(task)
        self.screen_queue()

    def screen_queue(self) -> None:
        self._screen(t("queue_title"))
        if self.pool is None or self.pool.total == 0:
            console.print(f"[{self.theme.muted}]{t('queue_empty')}[/]")
            self._wait_enter()
            return

        pool, theme = self.pool, self.theme
        progress = self.bridge.progress if self.bridge else build_progress(theme)

        def status_lines() -> list[str]:
            counts = pool.counts()
            return [
                f"[{theme.success}]✓ {t('queue_done')} {counts['success']}[/]   "
                f"[{theme.error}]✗ {t('queue_failed')} {counts['failed']}[/]   "
                f"[{theme.muted}]– {t('queue_skipped')} {counts['skipped']}[/]   "
                f"[{theme.warning}]! {t('queue_cancelled')} {counts['cancelled']}[/]   "
                f"[{theme.info}]▸ {t('queue_active')} {pool.active_count}[/]",
                f"[{theme.muted}]{t('queue_return_hint')}[/]",
            ]

        while not pool.is_done():
            try:
                with QueueLive(progress, theme, status_lines):
                    while not pool.is_done():
                        if self.shutdown.triggered:
                            raise KeyboardInterrupt
                        time.sleep(0.25)
            except KeyboardInterrupt:
                console.print(f"\n[{theme.warning}]{t('queue_stopping')}[/]")
                if Confirm.ask(t("queue_stop_prompt"), default=False):
                    saved = pool.cancel_and_persist()
                    if saved:
                        console.print(f"[{theme.muted}]{t('queue_saved_state', n=saved)}[/]")
                    break
                # The user wants to keep downloading: clear the interrupt
                # flag so the app continues normally instead of exiting.
                self.shutdown.reset()

        if not self.shutdown.triggered:
            self.db.clear_queue()
        results = list(pool.results)
        if results:
            render_download_results(results, theme)
        pool.shutdown_pool()
        self.pool = None
        self._wait_enter()

    # ------------------------------------------------------------------ #
    # search screen
    # ------------------------------------------------------------------ #

    def screen_search(self) -> None:
        self._screen(t("search_title"))
        shell.heading(console, self.theme,
                      shell.tr("Найди нужную версию", "Find the right version"),
                      shell.tr("Исполнитель - Название или прямая ссылка YouTube.",
                               "Artist - Title or a direct YouTube URL."))
        console.print(Text(shell.tr("Пример: Muse - Hysteria", "Example: Muse - Hysteria"),
                           style=self.theme.muted))
        console.print(Text(shell.tr("Пустой Enter — назад", "Empty Enter — back"),
                           style=self.theme.muted))
        query = Prompt.ask(
            Text("❯ " + t("search_prompt").rstrip(":"), style=self.theme.primary),
            default="", show_default=False,
        ).strip()
        if not query:
            return

        if query.startswith("http"):
            self._start_batch(
                [DownloadTask(url=query, query=query, source="search")]
            )
            return

        with console.status(f"[{self.theme.muted}]{t('search_searching')}[/]"):
            _best, scored = self.search.best(query)
        if not scored:
            console.print(f"[{self.theme.error}]{t('search_nothing')}[/]")
            self._wait_enter()
            return

        render_scored_results(scored, self.theme)

        visible = scored[:12]
        choice = shell.select(
            console, self.theme, t("search_select"),
            [(str(i), f"{item.candidate.title} · {item.score}")
             for i, item in enumerate(visible, 1)] + [("0", t("back"))],
            default="1", show_rows=False,
        )
        if choice == "0":
            return
        picked: ScoredCandidate = visible[int(choice) - 1]
        render_score_reasons(picked, self.theme)

        candidate = picked.candidate
        task = DownloadTask(
            query=query,
            url=candidate.url,
            title=candidate.title,
            artist=candidate.channel,
            source="search",
        )
        if Confirm.ask(shell.tr("Скачать выбранную версию?", "Download this version?"),
                       default=True):
            self._start_batch([task])

    # ------------------------------------------------------------------ #
    # playlist screen (v1 soul)
    # ------------------------------------------------------------------ #

    def screen_playlist(self) -> None:
        self._screen(t("pl_title"))
        shell.heading(console, self.theme, shell.tr("Загрузка списком", "Batch download"),
                      shell.tr("Один трек на строку в .txt. Можно вставить путь к файлу.",
                               "One track per line in a .txt file. Paste its path."))
        console.print(shell.panel(console, self.theme, Text(
            "Daft Punk - Around the World\nMuse - Hysteria\nMassive Attack - Teardrop"
        ), "playlist.txt"))
        path = Prompt.ask(t("pl_filepath").rstrip(":"), default="", show_default=False).strip()
        path = path.strip('"')
        if not path:
            return
        file_path = Path(path).expanduser()
        if not file_path.is_file():
            console.print(f"[{self.theme.error}]{t('pl_file_not_found')}[/]")
            self._wait_enter()
            return

        tracks = parse_playlist(file_path)
        if not tracks:
            console.print(f"[{self.theme.error}]{t('pl_no_tracks')}[/]")
            self._wait_enter()
            return

        console.print(f"[{self.theme.info}]{t('pl_found', n=len(tracks))}[/]")
        if not Confirm.ask(t("pl_confirm", n=len(tracks)), default=True):
            return

        from melodine.services.scoring import detect_intent

        tasks = [
            DownloadTask(
                query=str(track["query"]),
                artist=str(track["artist"]),
                title=str(track["title"]),
                source="playlist",
                intent=detect_intent(str(track["query"])),
            )
            for track in tracks
        ]
        self._start_batch(tasks)

    # ------------------------------------------------------------------ #
    # history / library screen
    # ------------------------------------------------------------------ #

    def screen_history(self) -> None:
        self._screen(t("library_title"))
        stats = self.db.get_stats()
        if stats["total"] == 0 and self.db.count_tracks() == 0:
            console.print(f"[{self.theme.muted}]{t('history_empty')}[/]")
            self._wait_enter()
            return

        if stats["total"]:
            render_stats(stats, self.theme)

        tracks = self.db.list_tracks(limit=25)
        if tracks:
            table = Table(
                title=f"[{self.theme.title}]✦ {t('library_title')}[/]",
                border_style=self.theme.border,
                box=box.ROUNDED,
            )
            table.add_column(t("library_col_artist"), style=self.theme.primary, ratio=2)
            table.add_column(t("library_col_title"), ratio=3)
            table.add_column(t("library_col_album"), style=self.theme.muted, ratio=2)
            table.add_column(t("library_col_codec"), justify="center")
            for track in tracks:
                table.add_row(
                    (track["artist"] or "-")[:26],
                    (track["title"] or "-")[:40],
                    (track["album"] or "-")[:30],
                    track["codec"] or "-",
                )
            console.print(table)
        self._wait_enter()

    # ------------------------------------------------------------------ #
    # watchlist screen
    # ------------------------------------------------------------------ #

    def screen_watchlist(self) -> None:
        while True:
            self._screen(t("wl_title"))
            entries = self.watchlist.list()

            if entries:
                table = Table(border_style=self.theme.border, box=box.ROUNDED)
                table.add_column(t("wl_col_id"), style=self.theme.muted, justify="right")
                table.add_column(t("wl_col_name"), style=self.theme.primary)
                table.add_column(t("wl_col_kind"))
                table.add_column(t("wl_col_tracks"), justify="right")
                table.add_column(t("wl_col_synced"))
                for entry in entries:
                    table.add_row(
                        str(entry.id),
                        entry.name,
                        t(f"wl_kind_{entry.kind}"),
                        str(entry.track_count),
                        entry.last_synced_at or t("wl_never"),
                    )
                console.print(table)
            else:
                console.print(f"[{self.theme.muted}]{t('wl_empty')}[/]")

            console.print(
                f"[{self.theme.accent}]\\[a][/] {t('wl_action_add')}   "
                f"[{self.theme.accent}]\\[s][/] {t('wl_action_sync')}   "
                f"[{self.theme.accent}]\\[r][/] {t('wl_action_remove')}   "
                f"[{self.theme.accent}]\\[0][/] {t('back')}"
            )
            action = Prompt.ask(
                f"[{self.theme.primary}]{t('menu_prompt')}[/]", default="0"
            ).strip().lower()

            if action == "0":
                return
            if action == "a":
                self._watchlist_add()
            elif action == "s":
                self._watchlist_sync()
            elif action == "r":
                self._watchlist_remove()
            if action in {"a", "s", "r"}:
                self._wait_enter()

    def _watchlist_add(self) -> None:
        url = Prompt.ask(f"[{self.theme.primary}]{t('wl_add_prompt')}[/]").strip()
        if not url:
            return
        name = Prompt.ask(f"[{self.theme.muted}]{t('wl_add_name')}[/]", default="").strip()
        entry = self.watchlist.add(url, name)
        console.print(f"[{self.theme.success}]{t('wl_added', name=entry.name)}[/]")

    def _watchlist_remove(self) -> None:
        entry_id = IntPrompt.ask(f"[{self.theme.primary}]{t('wl_remove_prompt')}[/]", default=0)
        if entry_id <= 0:
            return
        if self.watchlist.remove(entry_id):
            console.print(f"[{self.theme.success}]{t('wl_removed')}[/]")
        else:
            console.print(f"[{self.theme.error}]{t('wl_not_found')}[/]")

    def _watchlist_sync(self) -> None:
        entry_id = IntPrompt.ask(f"[{self.theme.primary}]{t('wl_sync_prompt')}[/]", default=0)
        if entry_id == -1:
            return
        entries = self.watchlist.list()
        if entry_id > 0:
            entries = [e for e in entries if e.id == entry_id]
        if not entries:
            console.print(f"[{self.theme.error}]{t('wl_not_found')}[/]")
            return
        for entry in entries:
            console.print(f"[{self.theme.info}]{t('wl_syncing', name=entry.name)}[/]")
            with console.status("..."):
                report = self.watchlist.sync(entry)
            console.print(
                f"[{self.theme.success}]"
                f"{t('wl_sync_done', added=report.downloaded, total=report.listed)}[/]"
            )
            if report.results:
                render_download_results(report.results, self.theme)

    # ------------------------------------------------------------------ #
    # lyrics tool screen
    # ------------------------------------------------------------------ #

    def screen_lyrics_tool(self) -> None:
        self._screen(t("lyr_title"))
        path = Prompt.ask(f"[{self.theme.primary}]{t('lyr_path_prompt')}[/]", default="").strip()
        if not path:
            return
        folder = Path(path).expanduser()
        if not folder.exists():
            console.print(f"[{self.theme.error}]{t('pl_file_not_found')}[/]")
            self._wait_enter()
            return

        with console.status(f"[{self.theme.muted}]{t('lyr_scanning')}[/]"):
            files = sorted(p for p in folder.rglob("*") if is_audio_file(p))
        console.print(f"[{self.theme.info}]{t('lyr_files', n=len(files))}[/]")
        if not files:
            self._wait_enter()
            return

        client = LRCLIBClient(rate_limit=self.cfg.lyrics.rate_limit_ms / 1000.0)
        tagger = Tagger()
        embedded = plain = missing = failed = 0

        progress = build_progress(self.theme)
        with progress:
            task = progress.add_task(t("cli_lyrics_title"), total=len(files))
            for file in files:
                progress.update(task, advance=1, description=file.name[:48])
                try:
                    meta = tagger.read(file)
                except Exception:
                    failed += 1
                    continue
                if Tagger.has_lyrics(file):
                    embedded += 1
                    continue
                record = client.best_match(
                    meta.artist,
                    meta.title,
                    duration=meta.duration,
                    tolerance=self.cfg.lyrics.duration_tolerance,
                )
                if record is None:
                    missing += 1
                    continue
                if tagger.apply(file, meta, record):
                    if record.has_synced:
                        embedded += 1
                        if self.cfg.lyrics.save_lrc:
                            with contextlib.suppress(OSError):
                                write_lrc_file(str(file), record)
                    else:
                        plain += 1
                else:
                    failed += 1

        console.print(
            f"[{self.theme.info}]"
            f"{t('lyr_done', ok=embedded + plain, miss=missing, fail=failed)}[/]"
        )
        self._wait_enter()

    # ------------------------------------------------------------------ #
    # doctor / export screens
    # ------------------------------------------------------------------ #

    def screen_doctor(self) -> None:
        self._screen(t("doctor_title"))
        shell.heading(console, self.theme, shell.tr("Проверка системы", "System check"),
                      shell.tr("FFmpeg, yt-dlp, база и внешние сервисы.",
                               "FFmpeg, yt-dlp, database and external services."))
        results = run_checks(self.cfg, self.db)
        status_colors = {
            "ok": self.theme.success,
            "warn": self.theme.warning,
            "fail": self.theme.error,
        }
        status_keys = {"ok": "status_ok", "warn": "status_warn", "fail": "status_fail"}
        table = Table(
            title=f"[{self.theme.title}]✦ {t('doctor_title')}[/]",
            border_style=self.theme.border,
            box=box.ROUNDED,
        )
        table.add_column(t("doctor_col_check"), style=self.theme.primary)
        table.add_column(t("doctor_col_status"), justify="center")
        table.add_column(t("doctor_col_detail"), style=self.theme.muted)
        for result in results:
            table.add_row(
                t(result.key),
                f"[{status_colors[result.status]}]{t(status_keys[result.status])}[/]",
                result.detail,
            )
        console.print(table)
        for result in results:
            if result.status == "fail" and result.hint_key:
                console.print(f"[{self.theme.warning}]→ {t(result.hint_key)}[/]")
        issues = sum(1 for r in results if r.status != "ok")
        if issues:
            console.print(f"[{self.theme.warning}]{t('doctor_issues', n=issues)}[/]")
        else:
            console.print(f"[{self.theme.success}]{t('doctor_all_ok')}[/]")
        self._wait_enter()

    def screen_export(self) -> None:
        self._screen(t("export_title"))
        console.print("  [1] M3U8   [2] JSON", markup=False)
        fmt = Prompt.ask(
            f"[{self.theme.primary}]{t('export_format_prompt')}[/]",
            choices=["1", "2"],
            default="1",
        )
        fmt_key = "m3u8" if fmt == "1" else "json"
        console.print(Text(t("export_scope_choices")))
        scope = Prompt.ask(
            f"[{self.theme.primary}]{t('export_scope_prompt')}[/]",
            choices=["1", "2"],
            default="1",
        )
        scope_key = "library" if scope == "1" else "history"

        exporter = Exporter(self.db, self.cfg)
        default_path = exporter.default_path(fmt_key, scope_key)
        out = Prompt.ask(
            f"[{self.theme.muted}]{t('export_path_prompt')}[/]",
            default=str(default_path),
        ).strip()
        try:
            count = (
                exporter.export_json(out, scope=scope_key)
                if fmt_key == "json"
                else exporter.export_m3u8(out, scope=scope_key)
            )
            console.print(f"[{self.theme.success}]{t('export_done', n=count, path=out)}[/]")
        except Exception as exc:
            console.print(f"[{self.theme.error}]{t('export_error', error=exc)}[/]")
        self._wait_enter()

    # ------------------------------------------------------------------ #
    # settings screens
    # ------------------------------------------------------------------ #

    def screen_settings(self) -> None:
        while True:
            labels = dict(SETTINGS_ITEMS)
            items = [
                ("", shell.tr("ЗВУК И ЗАГРУЗКА", "AUDIO & DOWNLOAD")),
                *[(k, t(labels[k])) for k in ("1", "2", "3", "4", "5", "6")],
                ("", shell.tr("ИНТЕРФЕЙС", "APPEARANCE")),
                *[(k, t(labels[k])) for k in ("7", "8")],
                ("", shell.tr("КОНФИГУРАЦИЯ", "CONFIGURATION")),
                *[(k, t(labels[k])) for k in ("9", "r", "0")],
            ]
            status = [
                (shell.tr("Формат", "Format"), self.cfg.audio.codec.upper()),
                (t("theme_current"), self.theme.label),
                ("Language / Язык", get_language().upper()),
            ]
            if shell.keyboard_available(console):
                from melodine.ui.workspace import workspace_select

                tr = shell.tr
                details = {
                    "1": tr("Кодек, битрейт, громкость и параметры загрузки.",
                            "Codec, bitrate, loudness and download settings."),
                    "2": tr("Правила выбора подходящего аудио.", "Audio selection rules."),
                    "3": tr("Удаление размеченных немузыкальных сегментов.",
                            "Remove marked non-music segments."),
                    "4": tr("Встроенные тексты и файлы .lrc.", "Embedded lyrics and .lrc files."),
                    "5": tr("Обложки, альбомы и теги.", "Artwork, albums and tags."),
                    "6": tr("Папка локальной медиатеки.", "Local library folder."),
                    "7": tr("Цветовые палитры интерфейса.", "Interface color palettes."),
                    "8": tr("Русский или английский.", "Russian or English."),
                    "9": tr("Текущие значения настроек.", "Current configuration values."),
                    "r": tr("Вернуть настройки по умолчанию.", "Restore default settings."),
                    "0": tr("Вернуться на главную.", "Return home."),
                }
                choice = workspace_select(
                    console, self.theme, t("settings_title"), items, details, status,
                    default=self._settings_selection,
                )
            else:
                self._screen(t("settings_title"))
                shell.status_grid(console, self.theme, status)
                choice = shell.select(
                    console, self.theme, t("settings_prompt"), items, default="0",
                )
            self._settings_selection = choice

            handlers: dict[str, Any] = {
                "1": self._settings_audio,
                "2": self._settings_search,
                "3": self._settings_sponsorblock,
                "4": self._settings_lyrics,
                "5": self._settings_artwork,
                "6": self._settings_paths,
                "7": self._settings_theme,
                "8": self._choose_language,
                "9": self._settings_show,
                "r": self._settings_reset,
            }
            if choice == "0":
                return
            handler = handlers.get(choice)
            if handler is not None:
                handler()
                self._wait_enter()
            else:
                console.print(t("invalid_value"))
                self._wait_enter()

    def _save(self) -> None:
        try:
            save_config(self.cfg)
            console.print(f"[{self.theme.success}]{t('settings_saved')}[/]")
        except OSError as exc:
            console.print(f"[{self.theme.error}]{t('error_generic', error=exc)}[/]")

    def _ask_int(self, message: str, current: int, lo: int, hi: int) -> int:
        while True:
            raw = Prompt.ask(f"[{self.theme.primary}]{message}[/]", default=str(current))
            try:
                value = int(raw)
                if lo <= value <= hi:
                    return value
            except ValueError:
                pass
            console.print(f"[{self.theme.error}]{t('invalid_value')}[/]")

    def _ask_float(self, message: str, current: float, lo: float, hi: float) -> float:
        while True:
            raw = Prompt.ask(f"[{self.theme.primary}]{message}[/]", default=str(current))
            try:
                value = float(raw)
                if lo <= value <= hi:
                    return value
            except ValueError:
                pass
            console.print(f"[{self.theme.error}]{t('invalid_value')}[/]")

    def _settings_audio(self) -> None:
        self._screen(t("settings_audio"))
        codecs = list(CODEC_PRESETS)
        current = self.cfg.audio.codec
        shell.heading(console, self.theme, shell.tr("Формат аудио", "Audio format"),
                      shell.tr("Выбери баланс совместимости, размера и качества.",
                               "Choose a balance of compatibility, size and quality."))
        table = Table(box=box.SIMPLE, border_style=self.theme.border,
                      show_header=False, width=shell.width(console))
        table.add_column(width=10)
        table.add_column(ratio=1)
        for i, key in enumerate(codecs, 1):
            marker = "▸" if key == current else " "
            table.add_row(Text(f"{marker} {i}. {key.upper()}", style=self.theme.accent),
                          Text(t(f"codec_help_{key}")))
        console.print(table)
        codec = shell.select(
            console, self.theme, t("cfg_codec"),
            [(str(i), key.upper()) for i, key in enumerate(codecs, 1)] + [("0", t("back"))],
            default=str(codecs.index(current) + 1), show_rows=False,
        )
        if codec == "0":
            return
        chosen = codecs[int(codec) - 1]
        profile = CODEC_PRESETS[chosen]
        self.cfg.audio.codec = chosen
        if not profile.lossless:
            default_bitrate = (
                self.cfg.audio.bitrate if chosen == current else profile.default_bitrate
            )
            console.print(Text(t("bitrate_help"), style=self.theme.muted))
            self.cfg.audio.bitrate = self._ask_int(
                t("cfg_bitrate", v=default_bitrate), default_bitrate, 32, 320
            )
        console.print(Text(t("normalize_help"), style=self.theme.muted))
        self.cfg.audio.normalize = Confirm.ask(
            t("cfg_normalize"), default=self.cfg.audio.normalize
        )
        if self.cfg.audio.normalize:
            self.cfg.audio.target_lufs = self._ask_float(
                t("cfg_lufs", v=self.cfg.audio.target_lufs),
                self.cfg.audio.target_lufs,
                -30.0,
                -5.0,
            )
        console.print(Text(t("threads_help"), style=self.theme.muted))
        self.cfg.download.threads = self._ask_int(
            t("cfg_threads", v=self.cfg.download.threads), self.cfg.download.threads, 1, 15
        )
        self.cfg.download.max_duration = self._ask_int(
            t("cfg_max_duration", v=self.cfg.download.max_duration),
            self.cfg.download.max_duration,
            60,
            7200,
        )
        self.cfg.download.timeout = self._ask_int(
            t("cfg_timeout", v=self.cfg.download.timeout), self.cfg.download.timeout, 5, 120
        )
        self._save()

    def _settings_search(self) -> None:
        self._screen(t("settings_search"))
        shell.heading(console, self.theme, "Anti-MV", shell.tr(
            "Приоритет официального аудио перед клипами и реакциями.",
            "Prefer official audio over music videos and reactions."))
        self.cfg.search.anti_mv = Confirm.ask(t("cfg_anti_mv"), default=self.cfg.search.anti_mv)
        self.cfg.search.results = self._ask_int(
            t("cfg_results", v=self.cfg.search.results), self.cfg.search.results, 3, 30
        )
        self.cfg.search.min_score = self._ask_int(
            t("cfg_min_score", v=self.cfg.search.min_score), self.cfg.search.min_score, 0, 100
        )
        self.cfg.download.smart_search = Confirm.ask(
            t("cfg_smart"), default=self.cfg.download.smart_search
        )
        self._save()

    def _settings_sponsorblock(self) -> None:
        self._screen(t("settings_sponsorblock"))
        shell.heading(console, self.theme, "SponsorBlock", shell.tr(
            "Удаление размеченных немузыкальных вставок. Не все ролики имеют разметку.",
            "Remove marked non-music segments. Not every video has markers."))
        self.cfg.sponsorblock.enabled = Confirm.ask(
            t("cfg_sb_enabled"), default=self.cfg.sponsorblock.enabled
        )
        current = ", ".join(self.cfg.sponsorblock.categories)
        raw = Prompt.ask(
            f"[{self.theme.primary}]{t('cfg_sb_categories')}[/]", default=current
        )
        categories = [c.strip() for c in raw.split(",") if c.strip()]
        if categories:
            self.cfg.sponsorblock.categories = categories
        self.cfg.sponsorblock.force_keyframes = Confirm.ask(
            t("cfg_sb_keyframes"), default=self.cfg.sponsorblock.force_keyframes
        )
        self._save()

    def _settings_lyrics(self) -> None:
        self._screen(t("settings_lyrics"))
        shell.heading(console, self.theme, "LRCLIB", shell.tr(
            "Синхронизированные тексты и отдельные файлы .lrc.",
            "Synchronized lyrics and separate .lrc files."))
        self.cfg.lyrics.enabled = Confirm.ask(t("cfg_ly_enabled"), default=self.cfg.lyrics.enabled)
        self.cfg.lyrics.synced = Confirm.ask(t("cfg_ly_synced"), default=self.cfg.lyrics.synced)
        self.cfg.lyrics.save_lrc = Confirm.ask(t("cfg_ly_lrc"), default=self.cfg.lyrics.save_lrc)
        self._save()

    def _settings_artwork(self) -> None:
        self._screen(t("settings_artwork"))
        shell.heading(console, self.theme, shell.tr("Оформление треков", "Track details"),
                      shell.tr("Обложки, альбомы и теги для локального плеера.",
                               "Covers, albums and tags for your local player."))
        self.cfg.artwork.embed = Confirm.ask(t("cfg_aw_embed"), default=self.cfg.artwork.embed)
        self.cfg.artwork.crop = Confirm.ask(t("cfg_aw_crop"), default=self.cfg.artwork.crop)
        self.cfg.metadata.enrich = Confirm.ask(
            t("cfg_md_enrich"), default=self.cfg.metadata.enrich
        )
        self.cfg.tags.enabled = Confirm.ask(t("cfg_tags"), default=self.cfg.tags.enabled)
        self._save()

    def _settings_paths(self) -> None:
        self._screen(t("settings_paths"))
        console.print(
            f"[{self.theme.muted}]{t('paths_current')}[/] "
            f"[{self.theme.primary}]{self.cfg.output.folder}[/]"
        )
        folder = Prompt.ask(t("paths_prompt"), default=self.cfg.output.folder).strip()
        if folder:
            self.cfg.output.folder = folder
        self._save()

    def _settings_theme(self) -> None:
        labels = list_themes()
        default = self._theme_keys.index(self.theme.name) + 1
        if shell.keyboard_available(console):
            from melodine.ui.workspace import workspace_select

            items = [(str(i), label) for i, (_, label) in enumerate(labels, 1)]
            previews = {str(i): get_theme(key) for i, (key, _) in enumerate(labels, 1)}
            hint = shell.tr(
                "Предпросмотр интерфейса. Enter сохраняет тему, Esc отменяет.",
                "Preview the interface. Enter saves the theme, Esc cancels.",
            )
            if console.legacy_windows:
                hint += shell.tr(
                    " Цвета приближённые: классическая консоль Windows.",
                    " Approximate colors: classic Windows console.",
                )
            choice = workspace_select(
                console, self.theme, t("settings_theme"), [*items, ("0", t("back"))],
                {key: hint for key, _ in items}, [], default=str(default),
                previews=previews,
            )
        else:
            self._screen(t("settings_theme"))
            shell.heading(console, self.theme, shell.tr("Оформление", "Appearance"),
                          shell.tr("Выбери палитру интерфейса.", "Choose the interface palette."))
            console.print(f"[{self.theme.muted}]{t('theme_current')}[/] {self.theme.label}\n")
            table = Table.grid(padding=(0, 2), expand=True)
            columns = 2 if shell.width(console) >= 64 else 1
            for _ in range(columns):
                table.add_column(ratio=1)
            cells = []
            for i, (key, label) in enumerate(labels, 1):
                palette = get_theme(key)
                marker = "▸" if key == self.theme.name else " "
                row = Text(f"{marker} {i:>2}. {label:<12} ")
                for color in (palette.primary, palette.secondary, palette.accent,
                              palette.success, palette.warning, palette.error):
                    row.append("██ ", style=color)
                cells.append(row)
            for i in range(0, len(cells), columns):
                table.add_row(*cells[i:i + columns])
            console.print(shell.panel(console, self.theme, table,
                                      shell.tr("Палитры", "Palettes")))
            if console.legacy_windows:
                console.print(Text(shell.tr(
                    "Классическая консоль: цвета приблизительные. "
                    "Windows Terminal — полная палитра.",
                    "Classic console: approximate colors. Windows Terminal shows the full palette.",
                ), style=self.theme.muted))
            choice = shell.select(
                console, self.theme, t("theme_select"),
                [(str(i), label) for i, (_, label) in enumerate(labels, 1)] + [("0", t("back"))],
                default=str(default), show_rows=False,
            )
        if choice != "0":
            self.cfg.theme = labels[int(choice) - 1][0]
            self.theme = shell.display_theme(get_theme(self.cfg.theme), console)
            self._save()
            console.print(
                f"[{self.theme.success}]{t('theme_changed', name=self.theme.label)}[/]"
            )

    def _settings_show(self) -> None:
        self._screen(t("config_title"))
        table = Table(
            title=t("config_title"), border_style=self.theme.border, box=box.ROUNDED
        )
        table.add_column(t("config_param"), style=self.theme.primary)
        table.add_column(t("config_value"), style=self.theme.accent)
        rows = [
            ("Language", self.cfg.language.upper()),
            ("Theme", self.theme.label),
            ("Codec", self.cfg.audio.codec),
            ("Bitrate", f"{self.cfg.audio.bitrate} kbps"),
            ("Normalize", str(self.cfg.audio.normalize)),
            ("SponsorBlock", str(self.cfg.sponsorblock.enabled)),
            ("SB categories", ", ".join(self.cfg.sponsorblock.categories)),
            ("Lyrics", str(self.cfg.lyrics.enabled)),
            ("Save .lrc", str(self.cfg.lyrics.save_lrc)),
            ("Artwork embed", str(self.cfg.artwork.embed)),
            ("Artwork crop", str(self.cfg.artwork.crop)),
            ("Enrich", str(self.cfg.metadata.enrich)),
            ("Anti-MV", str(self.cfg.search.anti_mv)),
            ("Threads", str(self.cfg.download.threads)),
            ("Output", self.cfg.output.folder),
            ("Template", self.cfg.output.template),
        ]
        for param, value in rows:
            table.add_row(param, value)
        console.print(table)

    def _settings_reset(self) -> None:
        self._screen(t("settings_reset"))
        if Confirm.ask(t("settings_reset_confirm"), default=False):
            from melodine.core.config import AppConfig

            self.cfg = AppConfig()
            self.theme = shell.display_theme(get_theme(self.cfg.theme), console)
            set_language(self.cfg.language)
            self._save()
            console.print(f"[{self.theme.success}]{t('settings_reset_done')}[/]")
        else:
            console.print(f"[{self.theme.muted}]{t('settings_cancelled')}[/]")
