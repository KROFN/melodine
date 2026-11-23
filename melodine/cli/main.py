"""Melodine CLI (typer).

``melodine`` without arguments launches the interactive TUI; every command
below is fully headless and scriptable.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any, Optional

import typer
from rich import box
from rich.panel import Panel
from rich.table import Table

from melodine import __version__
from melodine.core.config import AppConfig, load_config
from melodine.core.exceptions import ConfigError
from melodine.core.logging import setup_logging, shutdown_logging
from melodine.core.shutdown import GracefulShutdown
from melodine.db.database import Database
from melodine.i18n import set_language, t
from melodine.models import (
    DownloadOptions,
    DownloadResult,
    DownloadTask,
    IntentFlags,
)
from melodine.services.doctor import has_failures, run_checks
from melodine.services.downloader import DownloadPool, DownloadService
from melodine.services.exporter import Exporter
from melodine.services.lrclib import LRCLIBClient, write_lrc_file
from melodine.services.playlists import WatchlistService
from melodine.services.scoring import detect_intent
from melodine.services.tagger import Tagger, is_audio_file
from melodine.services.titles import (
    clean_artist,
    clean_track_title,
    parse_artist_title,
)
from melodine.ui.themes import get_theme
from melodine.ui.widgets import (
    ProgressBridge,
    QueueLive,
    build_progress,
    console,
    render_download_results,
)
from melodine.utils import parse_playlist

app = typer.Typer(
    add_completion=False,
    invoke_without_command=True,
    no_args_is_help=False,
    help="Melodine - flagship YouTube music downloader (TUI + headless CLI).",
)
watchlist_app = typer.Typer(help="Manage watchlist subscriptions.")
app.add_typer(watchlist_app, name="watchlist")


# --------------------------------------------------------------------------- #
# globals & helpers
# --------------------------------------------------------------------------- #


def _version_cb(value: bool) -> None:
    if value:
        typer.echo(f"Melodine v{__version__}")
        raise typer.Exit()


@app.callback()
def root(
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(
        None, "--version", callback=_version_cb, is_eager=True, help="Show version."
    ),
    config_path: Optional[Path] = typer.Option(
        None, "--config", help="Path to config.yaml."
    ),
    lang: Optional[str] = typer.Option(None, "--lang", help="Override language (ru|en)."),
    theme: Optional[str] = typer.Option(None, "--theme", help="Override theme name."),
    verbose: bool = typer.Option(False, "--verbose", help="Verbose logging to stderr."),
) -> None:
    """Melodine v2 - your playlist, downloaded, beautifully."""
    try:
        cfg, created = load_config(config_path)
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    if lang:
        cfg.language = lang.strip().lower()
    if theme:
        cfg.theme = theme.strip().lower()
    set_language(cfg.language)
    setup_logging(cfg.logging, verbose=verbose)
    ctx.obj = {"cfg": cfg, "created": created, "verbose": verbose}

    if ctx.invoked_subcommand is None:
        from melodine.cli.tui import MelodineTUI

        MelodineTUI(cfg, first_run=created).run()
        raise typer.Exit()


def _get_cfg(ctx: typer.Context) -> AppConfig:
    return ctx.obj["cfg"]


def _options_from_flags(
    fmt: Optional[str],
    bitrate: Optional[int],
    normalize: Optional[bool],
    sponsorblock: Optional[bool],
    lyrics: Optional[bool],
    enrich: Optional[bool],
    index: Optional[int],
    folder: Optional[Path],
) -> DownloadOptions:
    return DownloadOptions(
        codec=fmt,
        bitrate=bitrate,
        normalize=normalize,
        sponsorblock=sponsorblock,
        lyrics=lyrics,
        enrich=enrich,
        index=index,
        folder=str(folder) if folder else None,
    )


def _intent_from_flags(
    live: bool, remix: bool, cover: bool, instrumental: bool
) -> IntentFlags:
    return IntentFlags(
        live=live, remix=remix, cover=cover, instrumental=instrumental
    )


def _run_batch(
    cfg: AppConfig,
    db: Database,
    tasks: list[DownloadTask],
    *,
    options: DownloadOptions | None = None,
) -> list[DownloadResult]:
    """Run a batch of tasks with a live progress display; Ctrl+C persists state."""
    theme = get_theme(cfg.theme)
    shutdown = GracefulShutdown()
    shutdown.install()
    progress = build_progress(theme)
    bridge = ProgressBridge(progress, theme)
    pool = DownloadPool(
        cfg, db, shutdown=shutdown, options=options, reporter=bridge
    )

    def status_lines() -> list[str]:
        counts = pool.counts()
        active = pool.active_count
        return [
            f"[{theme.success}]✓ {t('result_ok')} {counts['success']}[/]   "
            f"[{theme.error}]✗ {t('result_fail')} {counts['failed']}[/]   "
            f"[{theme.muted}]– {t('result_skip')} {counts['skipped']}[/]   "
            f"[{theme.info}]▸ {t('queue_active')} {active}[/]"
        ]

    try:
        for task in tasks:
            pool.submit(task)
        with QueueLive(progress, theme, status_lines):
            while not pool.is_done():
                import time as _time

                _time.sleep(0.25)
    except KeyboardInterrupt:
        console.print(f"\n[{theme.warning}]{t('queue_stopping')}[/]")
        saved = pool.cancel_and_persist()
        if saved:
            console.print(f"[{theme.muted}]{t('queue_saved_state', n=saved)}[/]")
        shutdown.restore()
        return list(pool.results)

    shutdown.restore()
    db.clear_queue()
    return list(pool.results)


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #


@app.command()
def get(
    ctx: typer.Context,
    query: Optional[str] = typer.Argument(
        None, help="Track query or YouTube URL (.txt file also works)."
    ),
    fmt: Optional[str] = typer.Option(None, "--format", "-f", help="opus | mp3 | m4a | flac."),
    bitrate: Optional[int] = typer.Option(None, "--bitrate", help="Target bitrate in kbps."),
    normalize: Optional[bool] = typer.Option(
        None, "--normalize/--no-normalize", help="EBU R128 normalization."
    ),
    sponsorblock: Optional[bool] = typer.Option(
        None, "--sponsorblock/--no-sponsorblock", help="Cut non-music segments."
    ),
    lyrics: Optional[bool] = typer.Option(
        None, "--lyrics/--no-lyrics", help="Fetch and embed lyrics."
    ),
    enrich: Optional[bool] = typer.Option(
        None, "--enrich/--no-enrich", help="Metadata enrichment."
    ),
    index: Optional[int] = typer.Option(None, "--index", "-i", help="Pick the Nth search result."),
    folder: Optional[Path] = typer.Option(None, "--folder", help="Output folder override."),
    live: bool = typer.Option(False, "--live", help="Prefer live versions."),
    remix: bool = typer.Option(False, "--remix", help="Prefer remixes."),
    cover: bool = typer.Option(False, "--cover", help="Prefer covers."),
    instrumental: bool = typer.Option(False, "--instrumental", help="Prefer instrumentals."),
    resume: bool = typer.Option(
        False, "--resume", help="Resume the queue persisted by an interrupted run."
    ),
) -> None:
    """Download a track (or a whole .txt playlist) with the full v2 pipeline."""
    cfg = _get_cfg(ctx)
    theme = get_theme(cfg.theme)
    db = Database(cfg.database.path)

    options = _options_from_flags(
        fmt, bitrate, normalize, sponsorblock, lyrics, enrich, index, folder
    )
    flags_intent = _intent_from_flags(live, remix, cover, instrumental)

    # -- resume mode: continue a queue saved by Ctrl+C --
    if resume:
        pending = db.load_queue()
        if not pending:
            typer.secho(t("cli_nothing_to_resume"), fg=typer.colors.YELLOW)
            db.close()
            raise typer.Exit(code=0)
        console.print(
            f"[{theme.primary}]{t('cli_resume_title')}[/]: {len(pending)}"
        )
        results = _run_batch(cfg, db, pending, options=options)
        render_download_results(results, theme)
        failed = sum(1 for r in results if r.status == "failed")
        db.close()
        raise typer.Exit(code=1 if failed else 0)

    if query is None:
        typer.secho(t("cli_missing_query"), fg=typer.colors.RED)
        db.close()
        raise typer.Exit(code=1)

    # -- playlist batch mode (v1 soul) --
    maybe_file = Path(query)
    if maybe_file.suffix.lower() == ".txt":
        if not maybe_file.is_file():
            # A missing .txt must fail fast instead of being treated as a
            # (very odd) search query that would hit the network.
            typer.secho(t("pl_file_not_found"), fg=typer.colors.RED)
            db.close()
            raise typer.Exit(code=1)
        tracks = parse_playlist(maybe_file)
        if not tracks:
            typer.secho(t("pl_no_tracks"), fg=typer.colors.RED)
            db.close()
            raise typer.Exit(code=1)
        console.print(
            f"[{theme.primary}]{t('cli_batch_title')}[/]: "
            f"{maybe_file} ({len(tracks)})"
        )
        tasks = [
            DownloadTask(
                query=str(track["query"]),
                artist=str(track["artist"]),
                title=str(track["title"]),
                source="playlist",
                # Explicit CLI intent flags override per-line detection.
                intent=flags_intent
                if flags_intent.any
                else detect_intent(str(track["query"])),
            )
            for track in tracks
        ]
        # CLI flags (format / normalize / sponsorblock / folder / ...) apply
        # to batch runs exactly like they do to single-track runs.
        results = _run_batch(cfg, db, tasks, options=options)
        render_download_results(results, theme)
        failed = sum(1 for r in results if r.status == "failed")
        db.close()
        raise typer.Exit(code=1 if failed else 0)

    # -- single track mode --
    task_artist, task_title = "", ""
    if not query.startswith("http"):
        # "Artist - Title" queries feed the scorer's target artist/title so
        # relevance (not just studio-likeness) drives candidate selection.
        raw_artist, raw_title = parse_artist_title(query)
        if raw_artist:
            task_artist = clean_artist(raw_artist)
            task_title = clean_track_title(raw_title).title or raw_title

    service = DownloadService(cfg, db, options=options)
    task = DownloadTask(
        query=query,
        url=query if query.startswith("http") else "",
        artist=task_artist,
        title=task_title,
        intent=IntentFlags(
            live=live, remix=remix, cover=cover, instrumental=instrumental
        )
        if not query.startswith("http")
        else detect_intent(query),
    )

    console.print(f"[{theme.muted}]{t('cli_get_searching', query=query[:60])}[/]")

    progress = build_progress(theme)
    bridge = ProgressBridge(progress, theme)
    shutdown = GracefulShutdown()
    shutdown.install()
    try:
        with progress:
            result = service.process(task, report=bridge)
    except KeyboardInterrupt:
        console.print(f"\n[{theme.warning}]{t('error_interrupted')}[/]")
        shutdown.restore()
        raise typer.Exit(code=130) from None
    shutdown.restore()

    if result.status == "skipped" and result.duplicate:
        console.print(f"[{theme.warning}]{t('cli_get_duplicate')}[/]")
        raise typer.Exit(code=0)
    if result.status != "success":
        console.print(f"[{theme.error}]{t('cli_get_failed', error=result.error)}[/]")
        raise typer.Exit(code=1)

    meta = result.meta
    lyrics_state = (
        t("lyrics_synced")
        if result.lyrics is not None and result.lyrics.has_synced
        else (t("lyrics_plain") if result.lyrics is not None else t("lyrics_none"))
    )
    from melodine.utils import format_size

    detail = (
        f"[{theme.muted}]{t('result_path')}[/] [{theme.primary}]{result.path}[/]\n"
        f"[{theme.muted}]{t('result_album')}[/] {meta.album or '-'}   "
        f"[{theme.muted}]{t('result_year')}[/] {meta.year or '-'}   "
        f"[{theme.muted}]{t('result_genre')}[/] {meta.genre or '-'}\n"
        f"[{theme.muted}]{t('result_artwork')}[/] "
        f"[{theme.success if result.artwork_embedded else theme.muted}]"
        f"{'✓' if result.artwork_embedded else '–'}[/]   "
        f"[{theme.muted}]{t('result_lyrics')}[/] {lyrics_state}   "
        f"[{theme.muted}]SponsorBlock[/] "
        f"[{theme.success if result.sponsorblock else theme.muted}]"
        f"{'✓' if result.sponsorblock else '–'}[/]   "
        f"[{theme.muted}]R128[/] "
        f"[{theme.success if result.normalized else theme.muted}]"
        f"{'✓' if result.normalized else '–'}[/]\n"
        f"[{theme.muted}]{t('result_size')}[/] {format_size(result.filesize)}"
    )
    console.print(
        Panel(
            detail,
            title=f"[{theme.title}]✓ {meta.artist} - {meta.title}[/]",
            border_style=theme.success if result.status == "success" else theme.border,
        )
    )
    db.close()


@app.command()
def sync(
    ctx: typer.Context,
    entry_id: Optional[int] = typer.Option(None, "--id", help="Sync a single watchlist entry."),
) -> None:
    """Download new tracks from watchlist subscriptions and refresh M3U8 files."""
    cfg = _get_cfg(ctx)
    theme = get_theme(cfg.theme)
    db = Database(cfg.database.path)
    service = WatchlistService(cfg, db)

    entries = service.list()
    if not entries:
        typer.secho(t("cli_sync_no_watchlist"), fg=typer.colors.YELLOW)
        raise typer.Exit(code=0)
    if entry_id is not None:
        entries = [e for e in entries if e.id == entry_id]
        if not entries:
            typer.secho(t("wl_not_found"), fg=typer.colors.RED)
            raise typer.Exit(code=1)

    console.print(f"[{theme.primary}]{t('cli_sync_title')}[/]")
    failed = 0
    for entry in entries:
        console.print(f"[{theme.muted}]{t('wl_syncing', name=entry.name)}[/]")
        report = service.sync(entry)
        console.print(
            f"[{theme.info}]  {t('wl_sync_done', added=report.downloaded, total=report.listed)}"
            f"  [duplicates: {report.duplicates}, failed: {report.failed}][/]"
        )
        for result in report.results:
            if result.status == "failed":
                failed += 1
                console.print(
                    f"[{theme.error}]  ✗ {result.task.title or result.task.url}: "
                    f"{result.error}[/]"
                )
        console.print(
            f"[{theme.muted}]  M3U8: {entry.playlist_path}[/]"
        )
    db.close()
    raise typer.Exit(code=1 if failed else 0)


@watchlist_app.command("add")
def watchlist_add(
    ctx: typer.Context,
    url: str = typer.Argument(..., help="Playlist or channel URL."),
    name: Optional[str] = typer.Option(None, "--name", help="Display name."),
) -> None:
    """Subscribe to a playlist or channel."""
    cfg = _get_cfg(ctx)
    theme = get_theme(cfg.theme)
    db = Database(cfg.database.path)
    service = WatchlistService(cfg, db)
    entry = service.add(url, name or "")
    console.print(f"[{theme.success}]{t('wl_added', name=entry.name)}[/] ({entry.kind})")
    db.close()


@watchlist_app.command("list")
def watchlist_list(ctx: typer.Context) -> None:
    """Show watchlist subscriptions."""
    cfg = _get_cfg(ctx)
    theme = get_theme(cfg.theme)
    db = Database(cfg.database.path)
    service = WatchlistService(cfg, db)
    entries = service.list()
    if not entries:
        typer.secho(t("wl_empty"), fg=typer.colors.YELLOW)
        raise typer.Exit(code=0)
    table = Table(border_style=theme.border, box=box.ROUNDED)
    table.add_column(t("wl_col_id"), style=theme.muted, justify="right")
    table.add_column(t("wl_col_name"), style=theme.primary)
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
    db.close()


@watchlist_app.command("remove")
def watchlist_remove(
    ctx: typer.Context,
    entry_id: int = typer.Argument(..., help="Watchlist entry ID."),
) -> None:
    """Remove a subscription (downloaded files are kept)."""
    cfg = _get_cfg(ctx)
    theme = get_theme(cfg.theme)
    db = Database(cfg.database.path)
    service = WatchlistService(cfg, db)
    if service.remove(entry_id):
        console.print(f"[{theme.success}]{t('wl_removed')}[/]")
    else:
        typer.secho(t("wl_not_found"), fg=typer.colors.RED)
        raise typer.Exit(code=1)
    db.close()


@app.command()
def lyrics(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Folder with audio files."),
    force: bool = typer.Option(False, "--force", help="Re-fetch when lyrics already exist."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Only report, do not modify."),
) -> None:
    """Backfill synced lyrics (.lrc) for an existing music folder."""
    cfg = _get_cfg(ctx)
    theme = get_theme(cfg.theme)

    if not path.exists():
        typer.secho(t("pl_file_not_found"), fg=typer.colors.RED)
        raise typer.Exit(code=1)

    files = sorted(p for p in path.rglob("*") if is_audio_file(p))
    console.print(f"[{theme.muted}]{t('lyr_files', n=len(files))}[/]")
    if not files:
        raise typer.Exit(code=0)
    if dry_run:
        console.print(f"[{theme.warning}]{t('lyr_dry_run')}[/]")

    client = LRCLIBClient(rate_limit=cfg.lyrics.rate_limit_ms / 1000.0)
    tagger = Tagger()
    embedded = plain = missing = failed = 0

    with build_progress(theme) as progress:
        task = progress.add_task(t("cli_lyrics_title"), total=len(files))
        for file in files:
            progress.update(task, advance=1, description=file.name[:48])
            try:
                meta = tagger.read(file)
            except Exception:
                failed += 1
                continue
            if not force and Tagger.has_lyrics(file):
                embedded += 1
                continue
            record = client.best_match(
                meta.artist,
                meta.title,
                duration=meta.duration,
                tolerance=cfg.lyrics.duration_tolerance,
            )
            if record is None:
                missing += 1
                continue
            if dry_run:
                if record.has_synced:
                    embedded += 1
                else:
                    plain += 1
                continue
            if tagger.apply(file, meta, record):
                if record.has_synced:
                    embedded += 1
                    if cfg.lyrics.save_lrc:
                        with contextlib.suppress(OSError):
                            write_lrc_file(str(file), record)
                else:
                    plain += 1
            else:
                failed += 1

    console.print(
        f"[{theme.info}]{t('lyr_done', ok=embedded + plain, miss=missing, fail=failed)}[/]"
    )
    raise typer.Exit(code=0 if failed == 0 else 1)


@app.command()
def doctor(
    ctx: typer.Context,
    offline: bool = typer.Option(False, "--offline", help="Skip network checks."),
) -> None:
    """Diagnose the environment: ffmpeg, yt-dlp, database health, network."""
    cfg = _get_cfg(ctx)
    theme = get_theme(cfg.theme)
    db = Database(cfg.database.path)
    results = run_checks(cfg, db, offline=offline)

    status_colors = {"ok": theme.success, "warn": theme.warning, "fail": theme.error}
    status_keys = {"ok": "status_ok", "warn": "status_warn", "fail": "status_fail"}
    table = Table(
        title=f"[{theme.title}]✦ {t('doctor_title')}[/]",
        border_style=theme.border,
        box=box.ROUNDED,
    )
    table.add_column(t("doctor_col_check"), style=theme.primary)
    table.add_column(t("doctor_col_status"), justify="center")
    table.add_column(t("doctor_col_detail"), style=theme.muted)
    for result in results:
        color = status_colors[result.status]
        table.add_row(
            t(result.key),
            f"[{color}]{t(status_keys[result.status])}[/]",
            result.detail,
        )
    console.print(table)

    for result in results:
        if result.status == "fail" and result.hint_key:
            console.print(f"[{theme.warning}]→ {t(result.hint_key)}[/]")

    issues = sum(1 for r in results if r.status != "ok")
    if issues:
        console.print(f"[{theme.warning}]{t('doctor_issues', n=issues)}[/]")
    else:
        console.print(f"[{theme.success}]{t('doctor_all_ok')}[/]")
    db.close()
    raise typer.Exit(code=1 if has_failures(results) else 0)


@app.command()
def export(
    ctx: typer.Context,
    fmt: str = typer.Option(
        "m3u8", "--format", "-f", help="m3u8 or json."
    ),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Output file."),
    scope: str = typer.Option("library", "--scope", help="library or history."),
) -> None:
    """Export the library or history to an M3U8 playlist / JSON."""
    cfg = _get_cfg(ctx)
    theme = get_theme(cfg.theme)
    db = Database(cfg.database.path)
    exporter = Exporter(db, cfg)

    fmt = fmt.strip().lower()
    scope = scope.strip().lower()
    if fmt not in {"m3u8", "json"}:
        typer.secho(t("invalid_value"), fg=typer.colors.RED)
        raise typer.Exit(code=1)

    target = out or exporter.default_path(fmt, scope)
    try:
        count = (
            exporter.export_json(target, scope=scope)
            if fmt == "json"
            else exporter.export_m3u8(target, scope=scope)
        )
    except Exception as exc:
        typer.secho(t("export_error", error=exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    console.print(f"[{theme.success}]{t('export_done', n=count, path=target)}[/]")
    db.close()


@app.command()
def tui(ctx: typer.Context) -> None:
    """Launch the interactive TUI (same as running melodine with no command)."""
    cfg = _get_cfg(ctx)
    from melodine.cli.tui import MelodineTUI

    MelodineTUI(cfg).run()


def main() -> Any:
    """Console-script entry point."""
    try:
        return app()
    except KeyboardInterrupt:
        print(f"\n{t('goodbye')}")
        raise SystemExit(130) from None
    finally:
        shutdown_logging()


if __name__ == "__main__":
    main()
