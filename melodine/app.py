import os, sys, signal
from InquirerPy import inquirer
from InquirerPy.separator import Separator

from melodine.config import load_config, save_config, reset_config, CONFIG_PATH
from melodine.themes import get_theme, list_themes
from melodine.locales import t, set_language, get_language
from melodine.display import (
    console, draw_header, show_first_run, show_playlist_info,
    show_download_result, show_stats, show_failed_tracks,
    show_search_results, show_config, show_message, wait_enter,
)
from melodine.database import init_db, get_stats, get_failed_count, get_failed_tracks, record_session
from melodine.downloader import DownloadEngine
from melodine.search import search_tracks, format_duration
from melodine.utils import parse_playlist, sanitize_filename


def _v_int(lo, hi):
    def check(val):
        try:
            return lo <= int(val) <= hi
        except (ValueError, TypeError):
            return False
    return check


def _v_float(lo, hi):
    def check(val):
        try:
            return lo <= float(val) <= hi
        except (ValueError, TypeError):
            return False
    return check


class MelodineApp:
    def __init__(self):
        self._first_run = not CONFIG_PATH.exists()
        self.config = load_config()
        self.theme = get_theme(self.config.theme)
        set_language(self.config.language)
        init_db()

    def run(self):
        if self._first_run:
            self._pick_language_first_run()
            draw_header(self.theme)
            show_first_run(self.theme)

        while True:
            try:
                self._main_menu()
            except KeyboardInterrupt:
                draw_header(self.theme)
                show_message(self.theme, t("goodbye"), "muted")
                break

    def _pick_language_first_run(self):
        draw_header(self.theme)
        lang = inquirer.select(
            message="🌐 Language / Язык:",
            choices=[
                {"name": "🇷🇺 Русский", "value": "ru"},
                {"name": "🇬🇧 English", "value": "en"},
            ],
            default="ru", pointer="❯", qmark="🌐", amark="🌐",
        ).execute()
        self.config.language = lang
        set_language(lang)
        save_config(self.config)

    # --- main menu ---

    def _main_menu(self):
        draw_header(self.theme)

        fc = get_failed_count()
        retry_label = t("menu_retry_n", n=fc) if fc else t("menu_retry")

        action = inquirer.select(
            message=t("menu_prompt"),
            choices=[
                {"name": t("menu_download"), "value": "download"},
                {"name": retry_label, "value": "retry", "disabled": t("menu_retry_disabled") if not fc else False},
                {"name": t("menu_search"), "value": "search"},
                Separator(),
                {"name": t("menu_stats"), "value": "stats"},
                {"name": t("menu_settings"), "value": "settings"},
                Separator(),
                {"name": t("menu_exit"), "value": "exit"},
            ],
            pointer="❯", qmark="🎵", amark="🎵",
        ).execute()

        handlers = {
            "download": self._download_playlist,
            "retry": self._retry_failed,
            "search": self._search_track,
            "stats": self._show_stats,
            "settings": self._settings_menu,
            "exit": self._exit,
        }
        fn = handlers.get(action)
        if fn:
            fn()

    def _exit(self):
        draw_header(self.theme)
        show_message(self.theme, t("goodbye"), "muted")
        sys.exit(0)

    # --- download ---

    def _download_playlist(self):
        draw_header(self.theme)
        console.print(f"[{self.theme.subtitle}]{t('dl_title')}[/]\n")

        filepath = inquirer.filepath(
            message=t("dl_filepath"), qmark="📂", amark="📂",
            validate=lambda p: os.path.isfile(p),
            invalid_message=t("dl_file_not_found"),
            only_files=True,
        ).execute()

        tracks = parse_playlist(filepath)
        if not tracks:
            show_message(self.theme, t("dl_no_tracks"), "error")
            wait_enter(self.theme)
            return

        out = self.config.paths.output
        new = sum(1 for tr in tracks if not os.path.exists(
            os.path.join(out, f"{self._fname(tr)}.mp3")
        ))

        draw_header(self.theme)
        show_playlist_info(self.theme, filepath, len(tracks), new)

        if new == 0:
            show_message(self.theme, t("dl_all_done"), "success")
            wait_enter(self.theme)
            return

        if not inquirer.confirm(
            message=t("dl_confirm", n=new), default=True, qmark="⬇️ ", amark="⬇️ ",
        ).execute():
            return

        self._run_download(tracks, filepath)

    def _retry_failed(self):
        draw_header(self.theme)
        console.print(f"[{self.theme.subtitle}]{t('retry_title')}[/]\n")

        failed = get_failed_tracks()
        if not failed:
            show_message(self.theme, t("retry_none"), "success")
            wait_enter(self.theme)
            return

        show_message(self.theme, t("retry_found", n=len(failed)), "info")
        console.print()

        if inquirer.confirm(
            message=t("retry_confirm", n=len(failed)), default=True, qmark="🔄", amark="🔄",
        ).execute():
            self._run_download(failed, "retry")

    def _run_download(self, tracks, source=""):
        engine = DownloadEngine(self.config, self.theme)
        orig_handler = signal.getsignal(signal.SIGINT)

        def on_interrupt(sig, frame):
            engine.stop()
            console.print(f"\n[{self.theme.warning}]{t('dl_stopping')}[/]")

        signal.signal(signal.SIGINT, on_interrupt)
        try:
            result = engine.download_playlist(tracks)
        finally:
            signal.signal(signal.SIGINT, orig_handler)

        draw_header(self.theme)
        show_download_result(
            self.theme,
            success=result["success"], failed=result["failed"],
            skipped=result["skipped"], retried=result["retried"],
            total=result["total"], elapsed=result["elapsed"],
            total_size=result["total_size"],
        )

        record_session(
            playlist_file=source, total=result["total"],
            success=result["success"], failed=result["failed"],
            skipped=result["skipped"], total_size=result["total_size"],
            duration_seconds=result["elapsed"],
        )

        if result["failed_list"]:
            console.print()
            show_failed_tracks(self.theme, result["failed_list"])
            with open(self.config.paths.failed_log, "w", encoding="utf-8") as f:
                f.write("\n".join(result["failed_list"]) + "\n")

        console.print()

        post = []
        if result["failed_list"]:
            post.append({"name": t("retry_again"), "value": "retry"})
        post += [
            {"name": t("post_open"), "value": "open"},
            {"name": t("post_menu"), "value": "menu"},
        ]

        choice = inquirer.select(
            message=t("post_prompt"), choices=post, pointer="❯", qmark="?", amark="?",
        ).execute()

        if choice == "retry":
            retry_tracks = []
            for q in result["failed_list"]:
                a, ti = (q.split(" - ", 1) + [""])[:2] if " - " in q else ("", q)
                retry_tracks.append({"query": q, "artist": a, "title": ti})
            self._run_download(retry_tracks, "retry")
        elif choice == "open":
            self._open_folder(self.config.paths.output)

    # --- search ---

    def _search_track(self):
        draw_header(self.theme)
        console.print(f"[{self.theme.subtitle}]{t('search_title')}[/]\n")

        query = inquirer.text(
            message=t("search_prompt"), qmark="🔍", amark="🔍",
            validate=lambda x: len(x.strip()) > 0,
            invalid_message=t("search_empty"),
        ).execute().strip()

        console.print(f"[{self.theme.muted}]{t('search_wait')}[/]")
        results = search_tracks(query, max_results=5)

        if not results:
            show_message(self.theme, t("search_nothing"), "error")
            wait_enter(self.theme)
            return

        draw_header(self.theme)
        show_search_results(self.theme, results)
        console.print()

        choices = [
            {"name": f"{i}. {r['title'][:55]}  [{format_duration(r['duration'])}]", "value": i - 1}
            for i, r in enumerate(results, 1)
        ]
        choices.append({"name": t("search_cancel"), "value": -1})

        sel = inquirer.select(
            message=t("search_select"), choices=choices, pointer="❯", qmark="🎵", amark="🎵",
        ).execute()

        if sel == -1:
            return

        info = results[sel]
        self._run_download(
            [{"query": info["url"], "artist": info["channel"], "title": info["title"]}],
            "search",
        )

    # --- stats ---

    def _show_stats(self):
        draw_header(self.theme)
        stats = get_stats()
        if stats["total"] == 0:
            show_message(self.theme, t("stats_empty"), "muted")
        else:
            show_stats(self.theme, stats)
        wait_enter(self.theme)

    # --- settings ---

    def _settings_menu(self):
        while True:
            draw_header(self.theme)
            console.print(f"[{self.theme.subtitle}]{t('settings_title')}[/]\n")

            action = inquirer.select(
                message=t("settings_prompt"),
                choices=[
                    {"name": t("settings_download"), "value": "download"},
                    {"name": t("settings_theme"), "value": "theme"},
                    {"name": t("settings_paths"), "value": "paths"},
                    {"name": t("settings_meta"), "value": "metadata"},
                    {"name": t("settings_lang"), "value": "lang"},
                    {"name": t("settings_show"), "value": "show"},
                    {"name": t("settings_reset"), "value": "reset"},
                    Separator(),
                    {"name": t("settings_back"), "value": "back"},
                ],
                pointer="❯", qmark="⚙️ ", amark="⚙️ ",
            ).execute()

            if action == "back":
                break

            handler = {
                "download": self._set_download,
                "theme": self._set_theme,
                "paths": self._set_paths,
                "metadata": self._set_metadata,
                "lang": self._set_language,
                "show": self._set_show,
                "reset": self._set_reset,
            }.get(action)
            if handler:
                handler()

    def _set_download(self):
        draw_header(self.theme)
        console.print(f"[{self.theme.subtitle}]{t('settings_download')}[/]\n")
        cfg = self.config.download

        cfg.threads = int(inquirer.text(
            message=t("cfg_threads", v=cfg.threads), default=str(cfg.threads),
            qmark="⚡", amark="⚡",
            validate=_v_int(1, 15), invalid_message=t("cfg_threads_err"),
        ).execute())

        cfg.pause = float(inquirer.text(
            message=t("cfg_pause", v=cfg.pause), default=str(cfg.pause),
            qmark="⏱ ", amark="⏱ ",
            validate=_v_float(0, 10), invalid_message=t("cfg_pause_err"),
        ).execute())

        cfg.retry_attempts = int(inquirer.text(
            message=t("cfg_retry", v=cfg.retry_attempts), default=str(cfg.retry_attempts),
            qmark="🔄", amark="🔄",
            validate=_v_int(0, 10), invalid_message=t("cfg_retry_err"),
        ).execute())

        cfg.retry_delay = float(inquirer.text(
            message=t("cfg_retry_delay", v=cfg.retry_delay), default=str(cfg.retry_delay),
            qmark="⏳", amark="⏳",
            validate=_v_float(0, 60), invalid_message=t("cfg_retry_delay_err"),
        ).execute())

        cfg.quality = int(inquirer.select(
            message=t("cfg_quality"),
            choices=["320", "256", "192", "128"], default=str(cfg.quality),
            qmark="🎵", amark="🎵",
        ).execute())

        cfg.max_duration = int(inquirer.text(
            message=t("cfg_duration", v=cfg.max_duration), default=str(cfg.max_duration),
            qmark="⏰", amark="⏰",
            validate=_v_int(60, 3600), invalid_message=t("cfg_duration_err"),
        ).execute())

        cfg.timeout = int(inquirer.text(
            message=t("cfg_timeout", v=cfg.timeout), default=str(cfg.timeout),
            qmark="🌐", amark="🌐",
            validate=_v_int(5, 120), invalid_message=t("cfg_timeout_err"),
        ).execute())

        cfg.smart_search = inquirer.confirm(
            message=t("cfg_smart"), default=cfg.smart_search, qmark="🧠", amark="🧠",
        ).execute()

        self.config.download = cfg
        save_config(self.config)
        console.print(f"\n[{self.theme.success}]{t('settings_saved')}[/]")
        wait_enter(self.theme)

    def _set_theme(self):
        draw_header(self.theme)
        console.print(f"[{self.theme.subtitle}]{t('settings_theme')}[/]\n")
        console.print(f"[{self.theme.muted}]{t('theme_current')} [{self.theme.primary}]{self.theme.label}[/]\n")

        themes = list_themes()
        sel = inquirer.select(
            message=t("theme_select"),
            choices=[{"name": label, "value": key} for key, label in themes],
            default=self.config.theme, pointer="❯", qmark="🎨", amark="🎨",
        ).execute()

        self.config.theme = sel
        self.theme = get_theme(sel)
        save_config(self.config)

        draw_header(self.theme)
        console.print(f"[{self.theme.success}]{t('theme_changed', name=self.theme.label)}[/]")
        wait_enter(self.theme)

    def _set_paths(self):
        draw_header(self.theme)
        console.print(f"[{self.theme.subtitle}]{t('settings_paths')}[/]\n")
        console.print(f"[{self.theme.muted}]{t('paths_current')} [{self.theme.primary}]{self.config.paths.output}[/]\n")

        path = inquirer.text(
            message=t("paths_prompt"), default=self.config.paths.output,
            qmark="📂", amark="📂",
        ).execute()

        self.config.paths.output = path
        save_config(self.config)
        console.print(f"\n[{self.theme.success}]{t('paths_set', path=path)}[/]")
        wait_enter(self.theme)

    def _set_metadata(self):
        draw_header(self.theme)
        console.print(f"[{self.theme.subtitle}]{t('settings_meta')}[/]\n")

        self.config.metadata.add_tags = inquirer.confirm(
            message=t("cfg_tags"), default=self.config.metadata.add_tags,
            qmark="🏷️ ", amark="🏷️ ",
        ).execute()

        self.config.metadata.download_covers = inquirer.confirm(
            message=t("cfg_covers"), default=self.config.metadata.download_covers,
            qmark="🖼️ ", amark="🖼️ ",
        ).execute()

        save_config(self.config)
        console.print(f"\n[{self.theme.success}]{t('settings_saved')}[/]")
        wait_enter(self.theme)

    def _set_language(self):
        draw_header(self.theme)

        lang = inquirer.select(
            message="🌐 Language / Язык:",
            choices=[
                {"name": "🇷🇺 Русский", "value": "ru"},
                {"name": "🇬🇧 English", "value": "en"},
            ],
            default=self.config.language, pointer="❯", qmark="🌐", amark="🌐",
        ).execute()

        self.config.language = lang
        set_language(lang)
        save_config(self.config)

        draw_header(self.theme)
        console.print(f"[{self.theme.success}]✅ {'Язык изменён!' if lang == 'ru' else 'Language changed!'}[/]")
        wait_enter(self.theme)

    def _set_show(self):
        draw_header(self.theme)
        show_config(self.theme, self.config)
        wait_enter(self.theme)

    def _set_reset(self):
        draw_header(self.theme)
        if inquirer.confirm(
            message=t("settings_reset_confirm"), default=False, qmark="⚠️ ", amark="⚠️ ",
        ).execute():
            self.config = reset_config()
            self.theme = get_theme(self.config.theme)
            set_language(self.config.language)
            console.print(f"\n[{self.theme.success}]{t('settings_reset_done')}[/]")
        else:
            console.print(f"\n[{self.theme.muted}]{t('settings_cancelled')}[/]")
        wait_enter(self.theme)

    # --- helpers ---

    @staticmethod
    def _fname(track):
        a = track.get("artist", "")
        ti = track.get("title", "")
        return sanitize_filename(f"{a} - {ti}" if a else ti)

    @staticmethod
    def _open_folder(path):
        import subprocess
        p = os.path.abspath(path)
        os.makedirs(p, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(p)
            elif sys.platform == "darwin":
                subprocess.run(["open", p])
            else:
                subprocess.run(["xdg-open", p])
        except Exception:
            pass