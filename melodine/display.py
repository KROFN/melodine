import os
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from melodine.themes import Theme
from melodine.locales import t
from melodine.utils import format_size, format_time
from melodine import __version__

console = Console()

LOGO = r"""
  ♫ ♪ ♫ ♪ ♫
  __  __      _           _ _
 |  \/  | ___| | ___   __| (_)_ __   ___
 | |\/| |/ _ \ |/ _ \ / _` | | '_ \ / _ \
 | |  | |  __/ | (_) | (_| | | | | |  __/
 |_|  |_|\___|_|\___/ \__,_|_|_| |_|\___|
"""


def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


def draw_header(theme: Theme):
    clear_screen()
    console.print(Text(LOGO, style=f"bold {theme.primary}"))
    console.print(Text(f"     {t('subtitle')}", style=f"italic {theme.subtitle}"))
    console.print(Text(f"{'':>47}v{__version__}", style=theme.muted))
    console.print()


def show_first_run(theme: Theme):
    content = (
        f"[{theme.info}]{t('welcome_text')}[/]\n"
        f"[{theme.muted}]{t('welcome_folder')}[/]\n"
        f"[{theme.muted}]{t('welcome_theme')}[/]\n\n"
        f"[{theme.subtitle}]{t('welcome_hint')}[/]"
    )
    console.print(Panel(content, title=t("welcome_title"), border_style=theme.border))
    console.print()
    console.input(f"[{theme.muted}]{t('press_enter')}[/]")


def show_playlist_info(theme: Theme, filepath, total, new):
    content = (
        f"[{theme.muted}]{t('playlist_file')}   [{theme.primary}]{filepath}[/]\n"
        f"[{theme.muted}]{t('playlist_tracks')} [{theme.primary}]{total}[/]\n"
        f"[{theme.muted}]{t('playlist_new')}  [{theme.success}]{new}[/] "
        f"[{theme.muted}]({total - new} {t('playlist_existing')})[/]"
    )
    console.print(Panel(content, title=t("panel_playlist"), border_style=theme.border))
    console.print()


def show_download_result(theme: Theme, success, failed, skipped, retried, total, elapsed, total_size):
    content = (
        f"[{theme.success}]{t('result_ok')}     {success}[/] / {total}\n"
        f"[{theme.error}]{t('result_fail')}  {failed}[/]\n"
        f"[{theme.warning}]{t('result_retry')}  {retried}[/]\n"
        f"[{theme.muted}]{t('result_skip')}  {skipped}[/]\n"
        f"[{theme.info}]{t('result_time')}       {format_time(elapsed)}[/]\n"
        f"[{theme.info}]{t('result_size')}      {format_size(total_size)}[/]"
    )
    console.print(Panel(content, title=t("panel_result"), border_style=theme.border))


def show_stats(theme: Theme, stats: dict):
    pct = (stats["success"] / stats["total"] * 100) if stats["total"] else 0
    main = (
        f"[{theme.info}]{t('stats_total')}  [{theme.primary}]{stats['total']}[/] {t('stats_tracks')}\n"
        f"[{theme.success}]{t('stats_success')}        {stats['success']} ({pct:.1f}%)[/]\n"
        f"[{theme.error}]{t('stats_failed')}       {stats['failed']}[/]\n"
        f"[{theme.info}]{t('stats_size')}   [{theme.primary}]{format_size(stats['total_size'])}[/]\n"
        f"[{theme.info}]{t('stats_time')}    {format_time(stats['total_time'])}[/]"
    )

    # weekly chart
    daily = stats.get("daily", [])
    peak = max((d["count"] for d in daily), default=1) or 1
    bars = "░▁▂▃▄▅▆▇█"
    chart = f"\n[{theme.subtitle}]{t('stats_week')}[/]\n"
    for d in daily:
        lvl = int(d["count"] / peak * (len(bars) - 1)) if d["count"] else 0
        chart += f"[{theme.muted}]  {d['day']}  [{theme.bar_complete}]{bars[lvl] * 5}[/]  {d['count']:>5}\n"

    artists = ""
    if stats.get("top_artists"):
        artists = f"\n[{theme.subtitle}]{t('stats_top')}[/]\n"
        for i, a in enumerate(stats["top_artists"][:7], 1):
            artists += (
                f"[{theme.muted}]  {i}. [{theme.primary}]{a['artist']:<25}[/] "
                f"— {a['count']} {t('stats_tracks')}\n"
            )

    console.print(Panel(main + chart + artists, title=t("stats_title"), border_style=theme.border))


def show_failed_tracks(theme: Theme, tracks: list[str], max_show=15):
    lines = ""
    for i, track in enumerate(tracks[:max_show], 1):
        lines += f"[{theme.muted}]  {i}. [{theme.error}]{track}[/]\n"
    if len(tracks) > max_show:
        lines += f"[{theme.muted}]  {t('failed_more', n=len(tracks) - max_show)}[/]\n"
    lines += f"\n[{theme.info}]{t('failed_saved')}[/]"

    console.print(Panel(lines, title=t("panel_failed", n=len(tracks)), border_style=theme.error))


def show_search_results(theme: Theme, results: list[dict]):
    from melodine.search import format_duration, format_views

    tbl = Table(title="🔍", border_style=theme.border, box=box.ROUNDED)
    tbl.add_column("#", style=theme.muted, width=3)
    tbl.add_column("Title", style=theme.primary)
    tbl.add_column("Channel", style=theme.muted)
    tbl.add_column("⏱", style=theme.info, justify="right")
    tbl.add_column("👁", style=theme.muted, justify="right")

    for i, r in enumerate(results, 1):
        tbl.add_row(
            str(i), r["title"][:50], r["channel"][:20],
            format_duration(r["duration"]), format_views(r["views"]),
        )
    console.print(tbl)


def show_config(theme: Theme, config):
    tbl = Table(title=t("config_title"), border_style=theme.border, box=box.ROUNDED)
    tbl.add_column(t("config_param"), style=theme.primary)
    tbl.add_column(t("config_value"), style=theme.accent)

    d = config.download
    rows = [
        ("Threads", str(d.threads)),
        ("Pause", f"{d.pause} s"),
        ("Retries", str(d.retry_attempts)),
        ("Retry delay", f"{d.retry_delay} s"),
        ("Quality", f"{d.quality} kbps"),
        ("Max duration", f"{d.max_duration} s"),
        ("Timeout", f"{d.timeout} s"),
        ("Smart Search", "✅" if d.smart_search else "❌"),
        ("Covers", "✅" if config.metadata.download_covers else "❌"),
        ("Theme", theme.label),
        ("Language", config.language.upper()),
        ("Output", config.paths.output),
    ]
    for param, val in rows:
        tbl.add_row(param, val)

    console.print(tbl)


def show_message(theme: Theme, msg, style="info"):
    color = getattr(theme, style, theme.info)
    console.print(f"[{color}]{msg}[/]")


def wait_enter(theme: Theme, msg=None):
    console.print()
    console.input(f"[{theme.muted}]{msg or t('press_enter')}[/]")