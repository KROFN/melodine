"""Keyboard workspace checks using prompt_toolkit's real input dispatcher."""

from __future__ import annotations

import pytest
from prompt_toolkit.application import create_app_session
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from rich.console import Console

from melodine.ui.themes import get_theme
from melodine.ui.workspace import workspace_select


@pytest.mark.parametrize(("keys", "expected"), [
    ("\x1b[B\r", "2"),
    ("\x1b[A\r", "0"),
    ("9", "9"),
    ("q", "0"),
])
def test_workspace_keyboard(keys, expected):
    with create_pipe_input() as pipe:
        pipe.send_text(keys)
        with create_app_session(input=pipe, output=DummyOutput()):
            result = workspace_select(
                Console(), get_theme("dracula"), "Home",
                [("", "Download"), ("1", "Search"), ("2", "Playlist"),
                 ("9", "Settings"), ("0", "Back")],
                {"1": "Find a track", "2": "Import a list"}, [],
                default="1",
            )
    assert result == expected


def test_preview_selection_is_returned_only_on_confirm():
    with create_pipe_input() as pipe:
        pipe.send_text("\x1b[B\r")
        with create_app_session(input=pipe, output=DummyOutput()):
            result = workspace_select(
                Console(), get_theme("dracula"), "Themes",
                [("1", "Dracula"), ("2", "Nord"), ("0", "Back")], {}, [],
                default="1", previews={"1": get_theme("dracula"), "2": get_theme("nord")},
            )
    assert result == "2"
