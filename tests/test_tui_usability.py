"""Regression tests for interactive choices, navigation and audio settings."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console
from rich.prompt import Confirm, Prompt

from melodine.cli import tui as tui_module
from melodine.cli.tui import MelodineTUI
from melodine.i18n import get_language, set_language
from melodine.models import DownloadOptions
from melodine.services.downloader import DownloadService


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
