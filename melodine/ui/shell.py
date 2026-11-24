"""Reusable terminal presentation and keyboard selection for the interactive app."""

from __future__ import annotations

import sys
from dataclasses import replace
from typing import TYPE_CHECKING

from rich import box
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from melodine import __version__
from melodine.i18n import get_language

if TYPE_CHECKING:
    from rich.console import Console

    from melodine.ui.themes import Theme


def display_theme(theme: Theme, console: Console) -> Theme:
    """Readable ANSI roles on legacy Windows; truecolor palettes elsewhere."""
    if not console.legacy_windows:
        return theme
    primary = {
        "dracula": "bright_magenta", "dark": "bright_blue", "nord": "bright_cyan",
        "monokai": "bright_green", "ocean": "bright_blue", "cyberpunk": "bright_magenta",
        "pastel": "bright_magenta", "daybreak": "bright_yellow", "forest": "bright_green",
        "sakura": "bright_magenta", "terminal": "bright_green", "gruvbox": "bright_yellow",
    }.get(theme.name, "bright_cyan")
    return replace(
        theme, primary=primary, title=primary, subtitle="bright_cyan",
        accent="bright_cyan", muted="white", border="bright_black",
        success="bright_green", warning="bright_yellow", error="bright_red",
        info="bright_cyan", bar_complete=primary,
    )


def tr(ru: str, en: str) -> str:
    return ru if get_language() == "ru" else en


def width(console: Console) -> int:
    return max(1, min(console.width, 104))


def header(console: Console, theme: Theme, title: str, *, home: bool = False) -> None:
    """Compact brand, location and version, shared by every screen."""
    line = Text()
    line.append(" MELODINE ", style=f"bold white on {theme.primary}"
                if not theme.primary.startswith("bright_") else f"bold black on {theme.primary}")
    line.append("  /  ", style=theme.muted)
    line.append(title, style="bold")
    line.append(f"   v{__version__}", style=theme.muted)
    console.print(line)
    console.print(Text("━" * width(console), style=theme.border))
    if home:
        console.print(Text(tr(
            "Музыка, а не видеоролики. Твоя локальная медиатека.",
            "Music, not videos. Your local library.",
        ), style=theme.muted))
    console.print()


def panel(console: Console, theme: Theme, body, title: str = "") -> Panel:
    return Panel(
        body, title=Text(title, style=f"bold {theme.primary}") if title else None,
        title_align="left", border_style=theme.border, box=box.ROUNDED,
        padding=(0, 1), width=width(console),
    )


def heading(console: Console, theme: Theme, title: str, hint: str = "") -> None:
    console.print(Text(title, style=f"bold {theme.primary}"))
    if hint:
        console.print(Text(hint, style=theme.muted))
    console.print()


def status_grid(console: Console, theme: Theme, entries: list[tuple[str, str]]) -> None:
    """Responsive compact status strip; labels never compete with values."""
    cols = min(len(entries), max(1, width(console) // 21))
    table = Table.grid(expand=True, padding=(0, 2))
    for _ in range(cols):
        table.add_column(ratio=1)
    for start in range(0, len(entries), cols):
        cells = []
        for label, value in entries[start:start + cols]:
            cell = Text(label + "\n", style=theme.muted)
            cell.append(value, style=f"bold {theme.primary}")
            cells.append(cell)
        table.add_row(*cells, *([Text("")] * (cols - len(cells))))
    console.print(panel(console, theme, table, tr("Состояние", "Workspace")))
    console.print()


def keyboard_available(console: Console) -> bool:
    """Keep plain prompts for pipes, tests and terminals without a keyboard."""
    if not console.is_terminal or console.is_dumb_terminal or not sys.stdin.isatty():
        return False
    try:
        import InquirerPy  # noqa: F401
    except ImportError:
        return False
    return True


def choice_rows(console: Console, theme: Theme, items: list[tuple[str, str]]) -> None:
    for key, label in items:
        if not key:
            console.print()
            console.print(Text(label, style=f"bold {theme.primary}"))
            continue
        row = Text(f"  [{key}] ", style=f"bold {theme.accent}")
        row.append(label)
        console.print(row)


def select(
    console: Console, theme: Theme, message: str, items: list[tuple[str, str]],
    *, default: str, show_rows: bool = True,
) -> str:
    """Arrow selection and direct one-key shortcuts; numeric fallback."""
    valid = {key: label for key, label in items if key}
    if not keyboard_available(console):
        if show_rows:
            choice_rows(console, theme, items)
        keys = list(valid) + (["q"] if "0" in valid and "q" not in valid else [])
        answer = Prompt.ask(message, choices=keys, default=default, show_choices=not show_rows)
        return "0" if answer == "q" and "q" not in valid else answer

    from InquirerPy import inquirer
    from InquirerPy.separator import Separator
    from InquirerPy.utils import get_style

    choices = [
        {"name": f"[{key}] {label}", "value": key} if key else Separator(f"── {label}")
        for key, label in items
    ]
    # A high-contrast native ANSI palette on classic Windows.
    color = "ansicyan" if console.legacy_windows else theme.accent
    prompt = inquirer.select(
        message=message, choices=choices, default=default, pointer="❯",
        qmark=" ", amark=" ", instruction=tr("(↑↓ Enter / Esc — назад)", "(↑↓ Enter / Esc back)"),
        style=get_style({"pointer": color, "question": "bold", "questionmark": color,
                         "answer": color, "instruction": "ansigray",
                         "selected": f"{color} bold", "separator": "ansigray"}),
        max_height="55%", show_cursor=False,
    )

    def bind(shortcut: str, value: str) -> None:
        @prompt.register_kb(shortcut)
        def choose(event):
            prompt.status["answered"] = True
            prompt.status["result"] = valid[value]
            event.app.exit(result=value)

    for key in valid:
        if len(key) == 1 and not any(other != key and other.startswith(key) for other in valid):
            bind(key, key)
    if "0" in valid:
        bind("escape", "0")
        if "q" not in valid:
            bind("q", "0")
    return str(prompt.execute())
