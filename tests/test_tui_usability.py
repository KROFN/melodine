"""Regression tests for interactive choices, navigation and audio settings."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from rich.console import Console
from rich.prompt import Confirm, Prompt

from melodine.cli import tui as tui_module
from melodine.cli.tui import MelodineTUI
from melodine.core.config import load_config
from melodine.i18n import get_language, set_language
from melodine.models import DownloadOptions, SearchCandidate
from melodine.services.downloader import DownloadService
from melodine.services.scoring import score_candidate
from melodine.ui import shell
from melodine.ui.themes import get_theme


@pytest.fixture
def ui(cfg, monkeypatch):
    original_language = get_language()
    output = StringIO()
    terminal = Console(file=output, width=120, force_terminal=False, color_system=None)
    monkeypatch.setattr(tui_module, "console", terminal)
    # The banner shares the widgets console.
    monkeypatch.setattr("melodine.ui.widgets.console", terminal)
    app = MelodineTUI(cfg)
    try:
        yield app, output
    finally:
        app.db.close()
        set_language(original_language)


def test_menu_keys_and_guide_visible(ui):
    app, output = ui
    app._draw_dashboard()
    assert "[h]" in output.getvalue()
    assert "[q]" in output.getvalue()
    assert "[1]" in output.getvalue()
    assert "\x1b[2J" not in output.getvalue()


@pytest.mark.parametrize("windows", [False, True])
def test_clear_only_on_interactive_terminal(ui, monkeypatch, windows):
    app, _ = ui
    calls = []
    monkeypatch.setattr(tui_module, "IS_WINDOWS", windows)
    monkeypatch.setattr(tui_module.os, "system", lambda cmd: calls.append(cmd) or 0)

    class FakeTerminal:
        is_terminal = True
        is_dumb_terminal = False

        def clear(self):
            calls.append("clear")

    terminal = FakeTerminal()
    monkeypatch.setattr(tui_module, "console", terminal)
    app._clear_screen()
    terminal.is_terminal = False
    app._clear_screen()
    terminal.is_terminal = True
    terminal.is_dumb_terminal = True
    app._clear_screen()
    assert calls == (["cls"] if windows else ["clear"])


def test_language_default_is_current(ui, monkeypatch):
    app, output = ui
    app.cfg.language = "en"
    set_language("en")

    def ask(*args, **kwargs):
        assert kwargs["default"] == "2"
        return kwargs["default"]

    monkeypatch.setattr(Prompt, "ask", ask)
    app._choose_language()
    assert app.cfg.language == "en"
    assert "[1] Русский" in output.getvalue()
    assert "[2] English" in output.getvalue()


def test_codec_choice_and_preset(ui, monkeypatch):
    app, output = ui
    monkeypatch.setattr(Prompt, "ask", lambda *a, **kw: "1")
    monkeypatch.setattr(Confirm, "ask", lambda *a, **kw: False)
    monkeypatch.setattr(app, "_ask_int", lambda message, current, lo, hi: current)
    app._settings_audio()
    assert app.cfg.audio.codec == "opus"
    assert app.cfg.audio.bitrate == 160
    for codec in ("OPUS", "MP3", "M4A", "FLAC"):
        assert codec in output.getvalue()


def test_flac_skips_bitrate(ui, monkeypatch):
    app, _ = ui
    prompts = []
    monkeypatch.setattr(Prompt, "ask", lambda *a, **kw: "4")
    monkeypatch.setattr(Confirm, "ask", lambda *a, **kw: False)

    def ask_int(message, current, lo, hi):
        prompts.append((lo, hi))
        return current

    monkeypatch.setattr(app, "_ask_int", ask_int)
    app._settings_audio()
    assert app.cfg.audio.codec == "flac"
    assert (32, 320) not in prompts


def test_theme_enter_keeps_current_and_shows_swatches(ui, monkeypatch):
    app, output = ui
    app.cfg.theme = "monokai"
    app.theme = tui_module.get_theme("monokai")

    def ask(*args, **kwargs):
        assert kwargs["default"] == "4"
        return kwargs["default"]

    monkeypatch.setattr(Prompt, "ask", ask)
    app._settings_theme()
    assert app.cfg.theme == "monokai"
    assert "Monokai" in output.getvalue()
    assert "██" in output.getvalue()


def test_guide_shows_output_and_navigation(ui, monkeypatch):
    app, output = ui
    monkeypatch.setattr(app, "_wait_enter", lambda: None)
    app.screen_guide()
    # A long Windows path may wrap inside the bounded Rich panel.
    rendered = "".join(line.strip("│ ") for line in output.getvalue().splitlines())
    assert str(Path(app.cfg.output.folder).resolve()) in rendered
    assert "Ctrl+C" in output.getvalue()


@pytest.mark.parametrize(
    ("override", "expected"),
    [
        (DownloadOptions(), 192),
        (DownloadOptions(codec="opus"), 160),
        (DownloadOptions(codec="opus", bitrate=96), 96),
    ],
)
def test_bitrate_reaches_extractor(cfg, db, override, expected):
    cfg.audio.bitrate = 192
    service = DownloadService(cfg, db, options=override)
    profile, bitrate = service.effective_profile()
    assert bitrate == expected
    opts = service._build_ydl_opts(Path("track.mp3"), profile, bitrate)
    extract = next(
        pp for pp in opts["postprocessors"] if pp["key"] == "FFmpegExtractAudio"
    )
    assert extract["preferredquality"] == str(expected)


@pytest.mark.parametrize(("legacy", "keyboard", "expected"), [
    (True, True, False),
    (False, True, True),
    (False, False, False),
])
def test_workspace_requires_modern_interactive_terminal(monkeypatch, legacy, keyboard, expected):
    monkeypatch.setattr(shell, "keyboard_available", lambda console: keyboard)
    terminal = SimpleNamespace(legacy_windows=legacy)
    assert shell.workspace_available(terminal) is expected


def test_legacy_home_routes_to_compact_selector(ui, monkeypatch):
    app, _ = ui
    monkeypatch.setattr(tui_module.console, "legacy_windows", True)
    monkeypatch.setattr(shell, "keyboard_available", lambda console: True)
    calls = []
    monkeypatch.setattr(app, "_draw_dashboard", lambda: calls.append("compact"))

    def choose(*args, **kwargs):
        calls.append("select")
        return "0"

    monkeypatch.setattr(shell, "select", choose)
    assert app._main_menu() is False
    assert calls == ["compact", "select"]


def test_legacy_theme_keeps_neutral_readable_text():
    terminal = SimpleNamespace(legacy_windows=True)
    theme = shell.display_theme(get_theme("dracula"), terminal)
    assert theme.primary == "white"
    assert theme.accent == "cyan"


@pytest.mark.parametrize(("windows", "legacy", "interactive", "enabled", "expected"), [
    (True, True, True, True, True),
    (True, False, True, True, False),
    (False, True, True, True, False),
    (True, True, False, True, False),
    (True, True, True, False, False),
])
def test_terminal_notice_gate(ui, monkeypatch, windows, legacy, interactive, enabled, expected):
    app, _ = ui
    app.cfg.show_legacy_terminal_notice = enabled
    monkeypatch.setattr(tui_module, "IS_WINDOWS", windows)
    terminal = SimpleNamespace(
        legacy_windows=legacy, is_terminal=interactive, is_dumb_terminal=False
    )
    monkeypatch.setattr(tui_module, "console", terminal)
    monkeypatch.setattr(shell, "keyboard_available", lambda console: True)
    calls = []
    monkeypatch.setattr(app, "_screen", lambda title: calls.append(title))
    # Replace only the rendering surface; the actual gate is exercised.
    terminal.print = lambda *args: None
    monkeypatch.setattr(shell, "panel", lambda *args: None)
    monkeypatch.setattr(shell, "select", lambda *args, **kwargs: "0")
    app._terminal_notice()
    assert bool(calls) is expected
    assert app.cfg.show_legacy_terminal_notice is enabled


def test_terminal_notice_dismissal_persists(ui, monkeypatch):
    app, output = ui
    monkeypatch.setattr(tui_module, "IS_WINDOWS", True)
    monkeypatch.setattr(tui_module.console, "legacy_windows", True)
    monkeypatch.setattr(tui_module.console, "_force_terminal", True)
    monkeypatch.setitem(tui_module.console._environ, "TERM", "xterm")
    monkeypatch.setattr(shell, "keyboard_available", lambda console: True)
    monkeypatch.setattr(app, "_clear_screen", lambda: None)
    monkeypatch.setattr(shell, "select", lambda *args, **kwargs: "1")
    app._terminal_notice()
    assert "Windows Terminal" in output.getvalue()
    loaded, _ = load_config()
    assert not loaded.show_legacy_terminal_notice
    before = output.getvalue()
    app._terminal_notice()
    assert output.getvalue() == before


@pytest.mark.parametrize("language", ["ru", "en"])
def test_score_preview_explains_neutral_candidate(ui, language):
    app, output = ui
    set_language(language)
    scored = score_candidate(SearchCandidate(title="Cadillac", channel="Artist"))
    assert scored.score == 50
    assert not scored.reasons
    tui_module.render_score_reasons(scored, app.theme)
    rendered = output.getvalue()
    assert "50/100" in rendered
    assert ("Версия не подтверждена" if language == "ru" else "Version not verified") in rendered


def test_tui_search_passes_query_context(ui, monkeypatch):
    app, _ = ui
    monkeypatch.setattr(Prompt, "ask", lambda *a, **kw: "Muse - Hysteria live")
    monkeypatch.setattr(app, "_wait_enter", lambda: None)
    calls = []

    def best(query, **kwargs):
        calls.append((query, kwargs))
        return None, []

    monkeypatch.setattr(app.search, "best", best)
    app.screen_search()
    query, kwargs = calls[0]
    assert query == "Muse - Hysteria live"
    assert kwargs["target_artist"] == "Muse"
    assert kwargs["target_title"] == "Hysteria live"
    assert kwargs["intent"].live
