"""Rich UI widgets shared by the TUI and CLI: console, banner, progress,
score bars, result tables and the queue event bridge."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table
from rich.text import Text

from melodine import __version__
from melodine.i18n import t
from melodine.ui.themes import Theme

if TYPE_CHECKING:  # pragma: no cover
    from melodine.models import DownloadResult, DownloadTask, ScoredCandidate

console = Console()

LOGO = r"""
  ♫ ♪ ♫ ♪ ♫
  __  __      _           _ _
 |  \/  | ___| | ___   __| (_)_ __   ___
 | |\/| |/ _ \ |/ _ \ / _` | | '_ \ / _ \
 | |  | |  __/ | (_) | (_| | | | | |  __/
 |_|  |_|\___|_|\___/ \__,_|_|_| |_|\___|
"""

BADGE_STYLES = {
    "studio": "success",
    "video": "warning",
    "live": "error",
    "alt": "muted",
}

STATUS_ICONS = {
    "success": ("[bold {success}]✓[/]"),
    "failed": ("[bold {error}]✗[/]"),
    "skipped": ("[{muted}]–[/]"),
    "cancelled": ("[{warning}]![/]"),
}


def draw_banner(theme: Theme, subtitle: str | None = None) -> None:
    """Print the Melodine header."""
    console.print(Text(LOGO, style=f"bold {theme.primary}"))
    console.print(
        Text(f"     {subtitle or t('app_tagline')}", style=f"italic {theme.subtitle}")
    )
    console.print(Text(f"{'':>47}v{__version__}", style=theme.muted))
    console.print()


def build_progress(theme: Theme) -> Progress:
    """A download progress with speed and ETA columns."""
    return Progress(
        SpinnerColumn(style=theme.primary),
        TextColumn("[bold]{task.description}"),
        BarColumn(
            complete_style=theme.bar_complete,
            finished_style=theme.success,
        ),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
    )


def score_bar(theme: Theme, score: int, width: int = 10) -> str:
    """Render a 0..100 score as a compact colored bar."""
    filled = round(score / 100 * width)
    if score >= 75:
        color = theme.success
    elif score >= 50:
        color = theme.warning
    else:
        color = theme.error
    return f"[{color}]{'█' * filled}{'░' * (width - filled)}[/] {score}"


def render_scored_results(scored: list[ScoredCandidate], theme: Theme, limit: int = 12) -> None:
    """Anti-MV ranked search results table."""
    table = Table(
        title=f"[{theme.title}]✦ {t('search_title')}[/]",
        border_style=theme.border,
        box=box.ROUNDED,
        show_lines=False,
    )
    table.add_column(t("search_col_num"), style=theme.muted, width=3, justify="right")
    table.add_column(t("search_col_title"), style=theme.primary, ratio=3)
    table.add_column(t("search_col_channel"), style=theme.muted, ratio=2)
    table.add_column(t("search_col_duration"), style=theme.info, justify="right")
    table.add_column(t("search_col_score"), justify="left", ratio=1)
    table.add_column(t("search_col_badge"), justify="center")

    from melodine.utils import format_duration

    for i, item in enumerate(scored[:limit], 1):
        badge_style = BADGE_STYLES.get(item.badge, "muted")
        badge_color = getattr(theme, badge_style)
        badge_key = f"badge_{item.badge}"
        table.add_row(
            str(i),
            item.candidate.title[:64],
            item.candidate.channel[:28],
            format_duration(item.candidate.duration),
            score_bar(theme, item.score),
            f"[{badge_color}]{t(badge_key)}[/]",
        )
    console.print(table)


def render_score_reasons(scored: ScoredCandidate, theme: Theme) -> None:
    """Metadata preview panel explaining why a candidate scored as it did."""
    lines: list[str] = []
    for reason in scored.reasons:
        color = theme.success if reason.points > 0 else theme.error
        sign = "+" if reason.points > 0 else ""
        value = f" ({reason.value})" if reason.value else ""
        lines.append(
            f"[{theme.muted}]•[/] {t(reason.key)}{value} "
            f"[{color}]{sign}{reason.points}[/]"
        )
    if not lines:
        lines.append(f"[{theme.muted}]{t('not_available')}[/]")
    console.print(
        Panel(
            "\n".join(lines),
            title=f"[{theme.title}]{t('search_details_title')}[/] "
            f"[{theme.primary}]{scored.candidate.title[:48]}[/] "
            f"({t('search_col_score')} {scored.score})",
            border_style=theme.border,
        )
    )


def _status_icon(theme: Theme, status: str) -> str:
    template = STATUS_ICONS.get(status, STATUS_ICONS["failed"])
    return template.format(
        success=theme.success, error=theme.error, muted=theme.muted, warning=theme.warning
    )


def render_download_results(results: list[DownloadResult], theme: Theme) -> None:
    """Post-batch summary table with the killer-feature checklist per track."""
    if not results:
        return
    table = Table(
        title=f"[{theme.title}]✦ {t('panel_result')}[/]",
        border_style=theme.border,
        box=box.ROUNDED,
    )
    table.add_column("", width=2)
    table.add_column(t("search_col_title"), style=theme.primary, ratio=3)
    table.add_column(t("result_artwork"), justify="center", width=3)
    table.add_column(t("result_lyrics"), justify="center", ratio=1)
    table.add_column("SB", justify="center", width=3)
    table.add_column("R128", justify="center", width=4)

    for result in results:
        label = result.meta.title or result.task.title or result.task.query
        if result.duplicate and result.status == "skipped":
            label = f"{label} [{theme.muted}]({t('result_duplicate')})[/]"
        artwork = (
            f"[{theme.success}]✓[/]" if result.artwork_embedded else f"[{theme.muted}]–[/]"
        )
        if result.lyrics is not None and result.lyrics.has_synced:
            lyrics = f"[{theme.success}]{t('lyrics_synced')}[/]"
        elif result.lyrics is not None and result.lyrics.has_plain:
            lyrics = f"[{theme.info}]{t('lyrics_plain')}[/]"
        else:
            lyrics = f"[{theme.muted}]{t('lyrics_none')}[/]"
        sponsorblock = (
            f"[{theme.success}]✓[/]" if result.sponsorblock else f"[{theme.muted}]–[/]"
        )
        normalized = (
            f"[{theme.success}]✓[/]" if result.normalized else f"[{theme.muted}]–[/]"
        )
        table.add_row(
            _status_icon(theme, result.status),
            label[:60],
            artwork,
            lyrics,
            sponsorblock,
            normalized,
        )
    console.print(table)


def render_stats(stats: dict[str, Any], theme: Theme) -> None:
    """v1-style statistics panel with the weekly chart (soul preserved)."""
    from melodine.utils import format_size, format_time

    pct = stats["success"] / stats["total"] * 100 if stats["total"] else 0
    main = (
        f"[{theme.info}]{t('stats_total')}  [{theme.primary}]{stats['total']}[/] "
        f"{t('stats_tracks')}\n"
        f"[{theme.success}]{t('stats_success')}        {stats['success']} ({pct:.1f}%)[/]\n"
        f"[{theme.error}]{t('stats_failed')}       {stats['failed']}[/]\n"
        f"[{theme.info}]{t('stats_size')}   "
        f"[{theme.primary}]{format_size(stats['total_size'])}[/]\n"
        f"[{theme.info}]{t('stats_time')}    {format_time(stats['total_time'])}[/]"
    )

    daily = stats.get("daily", [])
    peak = max((d["count"] for d in daily), default=1) or 1
    bars = "░▁▂▃▄▅▆▇█"
    chart = f"\n[{theme.subtitle}]{t('stats_week')}[/]\n"
    for day in daily:
        level = int(day["count"] / peak * (len(bars) - 1)) if day["count"] else 0
        chart += (
            f"[{theme.muted}]  {day['day']}  "
            f"[{theme.bar_complete}]{bars[level] * 5}[/]  {day['count']:>5}\n"
        )

    artists = ""
    if stats.get("top_artists"):
        artists = f"\n[{theme.subtitle}]{t('stats_top')}[/]\n"
        for i, artist in enumerate(stats["top_artists"][:7], 1):
            artists += (
                f"[{theme.muted}]  {i}. [{theme.primary}]{artist['artist']:<25}[/] "
                f"— {artist['count']} {t('stats_tracks')}\n"
            )

    console.print(
        Panel(main + chart + artists, title=t("stats_title"), border_style=theme.border)
    )


class ProgressBridge:
    """Thread-safe adapter: DownloadPool reporter events -> rich Progress."""

    def __init__(self, progress: Progress, theme: Theme) -> None:
        self.progress = progress
        self.theme = theme
        self._lock = threading.Lock()
        self._tasks: dict[str, Any] = {}
        self._labels: dict[str, str] = {}

    def __call__(self, event: str, task: DownloadTask, payload: dict[str, Any]) -> None:
        try:
            with self._lock:
                if event == "start":
                    label = f"{payload.get('title', task.title or task.query)[:48]}"
                    self._tasks[task.task_id] = self.progress.add_task(label, total=100.0)
                elif event == "progress" and task.task_id in self._tasks:
                    total = float(payload.get("total") or 0)
                    downloaded = float(payload.get("downloaded") or 0)
                    speed = payload.get("speed")
                    if total > 0:
                        self.progress.update(
                            self._tasks[task.task_id],
                            completed=downloaded,
                            total=total,
                            speed=speed,
                        )
                    else:
                        self.progress.update(
                            self._tasks[task.task_id], total=None, speed=speed
                        )
                elif event == "post" and task.task_id in self._tasks:
                    stage = str(payload.get("stage") or "")
                    label = self._labels.get(task.task_id, "")
                    if stage == "normalize":
                        self.progress.update(
                            self._tasks[task.task_id],
                            description=f"{label} [R128]",
                        )
                    elif stage == "lyrics":
                        self.progress.update(
                            self._tasks[task.task_id],
                            description=f"{label} [LRC]",
                        )
                elif event == "done" and task.task_id in self._tasks:
                    result = payload.get("result")
                    task_id = self._tasks[task.task_id]
                    if getattr(result, "status", None) in {"success", "skipped"}:
                        self.progress.update(task_id, completed=100.0, total=100.0)
                    else:
                        self.progress.update(task_id, completed=0.0, total=100.0)
                    icon = {
                        "success": f"[{self.theme.success}]✓",
                        "skipped": f"[{self.theme.muted}]–",
                        "failed": f"[{self.theme.error}]✗",
                        "cancelled": f"[{self.theme.warning}]!",
                    }.get(getattr(result, "status", "failed"), "!")
                    label = self._labels.get(task.task_id, "")
                    self.progress.update(task_id, description=f"{icon} {label}")
        except Exception:  # never let UI break downloads
            pass


class QueueLive:
    """Context manager rendering the queue status panel + progress."""

    def __init__(self, progress: Progress, theme: Theme, status_provider: Any) -> None:
        self.theme = theme
        self.progress = progress
        self.status_provider = status_provider
        self._live: Live | None = None

    def __enter__(self) -> QueueLive:
        self._live = Live(
            Group(self._panel, self.progress),
            console=console,
            refresh_per_second=6,
        )
        self._live.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._live is not None:
            self._live.stop()

    def _panel(self) -> Panel:
        lines = self.status_provider()
        return Panel(
            "\n".join(lines),
            title=f"[{self.theme.title}]✦ {t('queue_title')}[/]",
            border_style=self.theme.border,
        )

    def refresh(self) -> None:
        if self._live is not None:
            self._live.update(Group(self._panel, self.progress))
