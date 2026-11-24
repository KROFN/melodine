"""Compact workspace navigation for modern terminals."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from prompt_toolkit.application import Application, get_app
from prompt_toolkit.data_structures import Point
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import ConditionalContainer, HSplit, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.styles import DynamicStyle, Style
from prompt_toolkit.widgets import Frame

from melodine import __version__
from melodine.ui.shell import display_theme, tr

if TYPE_CHECKING:
    from rich.console import Console

    from melodine.ui.themes import Theme


def workspace_select(
    console: Console,
    theme: Theme,
    title: str,
    items: list[tuple[str, str]],
    details: dict[str, str],
    status: list[tuple[str, str]],
    *,
    default: str,
    context: str = "",
    previews: dict[str, Theme] | None = None,
) -> str:
    """Keyboard-driven split view; responsive to resize, no manual cursor escapes."""
    selectable = [i for i, (key, _) in enumerate(items) if key]
    current = next((i for i in selectable if items[i][0] == default), selectable[0])
    valid = {key for key, _ in items if key}
    bindings = KeyBindings()

    @bindings.add("up")
    @bindings.add("k")
    def up(event):
        nonlocal current
        current = selectable[(selectable.index(current) - 1) % len(selectable)]

    @bindings.add("down")
    @bindings.add("j")
    def down(event):
        nonlocal current
        current = selectable[(selectable.index(current) + 1) % len(selectable)]

    @bindings.add("enter")
    def enter(event):
        event.app.exit(result=items[current][0])

    @bindings.add("escape")
    def back(event):
        event.app.exit(result="0")

    @bindings.add("c-c")
    def interrupt(event):
        event.app.exit(exception=KeyboardInterrupt())

    def bind(key: str, value: str) -> None:
        @bindings.add(key)
        def shortcut(event):
            event.app.exit(result=value)

    for key in valid:
        if (len(key) == 1 and key not in {"j", "k"}
                and not any(other != key and other.startswith(key) for other in valid)):
            bind(key, key)
    if "q" not in valid:
        bind("q", "0")

    def workspace_width():
        return min(88, get_app().output.get_size().columns)

    def menu_width():
        cols = workspace_width()
        return 42 if cols >= 82 and previews else 38 if cols >= 82 else cols

    def workspace_height():
        rows = get_app().output.get_size().rows
        return max(3, min(max(15, len(items) + 5), 22, rows - 2))

    def menu_text():
        fragments = []
        for i, (key, label) in enumerate(items):
            if not key:
                fragments.append(("class:melodine-group", f"  {label}\n"))
                continue
            selected = i == current
            line = f" {'❯' if selected else ' '} {key:>2}  {label}"
            row_style = "class:melodine-selected" if selected else "class:melodine-menu"
            if previews and key in previews:
                fragments.append((row_style, line.ljust(21)))
                for i in range(6):
                    fragments.append((f"class:melodine-swatch-{key}-{i}", "  "))
                    fragments.append((row_style, " "))
                fragments.append((row_style, " " * max(0, menu_width() - 41) + "\n"))
            else:
                fragments.append((row_style, line.ljust(max(0, menu_width() - 2)) + "\n"))
        return fragments

    def detail_text():
        key, label = items[current]
        fragments = [
            ("class:melodine-muted", f"  {tr('ВЫБРАНО', 'SELECTED')}  /  {key.upper()}\n\n"),
            ("class:melodine-heading", f"  {label}\n\n"),
            ("class:melodine-body", f"  {details.get(key, '')}\n\n"),
        ]
        if previews and key in previews:
            fragments.extend([
                ("class:melodine-heading", f"  {tr('ПРЕДПРОСМОТР', 'PREVIEW')}\n\n"),
                ("class:melodine-success", f"  ✓ {tr('Трек загружен', 'Track downloaded')}\n"),
                ("class:melodine-warning", f"  ! {tr('Проверка источника', 'Checking source')}\n"),
                ("class:melodine-error", f"  × {tr('Ошибка соединения', 'Connection failed')}\n\n"),
                ("class:melodine-value", "  ━━━━━━━━━━━━━━━  75%\n\n"),
                ("class:melodine-muted", tr("  Enter — применить, Esc — отменить.\n",
                                   "  Enter — apply, Esc — cancel.\n")),
            ])
            return fragments
        fragments.append(("class:melodine-muted", f"  {tr('СОСТОЯНИЕ', 'STATUS')}\n\n"))
        for name, value in status:
            fragments.extend([("class:melodine-muted", f"  {name.rstrip(':')}: "),
                              ("class:melodine-value", f"{value}\n")])
        if context:
            fragments.append(("", "\n"))
            fragments.extend([("class:melodine-muted", f"  {tr('ПАПКА МУЗЫКИ', 'MUSIC FOLDER')}\n"),
                              ("class:melodine-value", f"  {context}\n")])
        return fragments

    def compact_text():
        key, _ = items[current]
        return [("class:melodine-muted", "  " + details.get(key, ""))]

    menu_control = FormattedTextControl(
        menu_text, focusable=True, show_cursor=False,
        get_cursor_position=lambda: Point(x=0, y=current),
    )
    menu = Window(menu_control, always_hide_cursor=True)
    wide = Condition(lambda: workspace_width() >= 82)
    tall = Condition(lambda: get_app().output.get_size().rows >= 18)
    # ConditionalContainers avoid duplicate focusable controls on small screens.
    left = Frame(menu, title=tr("Навигация", "Navigation"),
                 width=lambda: Dimension.exact(menu_width()))
    right = ConditionalContainer(
        Frame(Window(FormattedTextControl(detail_text), wrap_lines=True),
              title=tr("Обзор", "Overview")),
        filter=wide,
    )
    header = Window(FormattedTextControl([
        ("class:melodine-brand", " MELODINE "),
        ("class:melodine-heading", f"  /  {title}"),
        ("class:melodine-muted", f"  v{__version__}"),
    ]), height=1)
    footer = Window(FormattedTextControl([
        ("class:melodine-heading", " ↑↓ "),
        ("class:melodine-body", tr("выбор ", "move ")),
        ("class:melodine-heading", " Enter "),
        ("class:melodine-body", tr("открыть ", "open ")),
        ("class:melodine-heading", " Esc "),
        ("class:melodine-body", tr("назад ", "back ")),
        ("class:melodine-heading", " 0–9 " if not previews else ""),
        ("class:melodine-body", tr("команды ", "actions ") if not previews else ""),
        ("class:melodine-heading", " q "),
        ("class:melodine-body", tr("выход", "back/quit")),
    ]), height=1)
    root = HSplit([
        header,
        Window(height=1, char="─", style="class:melodine-group"),
        VSplit([left, right], padding=1),
        ConditionalContainer(
            Window(FormattedTextControl(compact_text), wrap_lines=True, height=3),
            filter=~wide & tall,
        ),
        footer,
    ], width=lambda: Dimension.exact(workspace_width()),
       height=lambda: Dimension.exact(workspace_height()))
    @lru_cache(maxsize=16)
    def style_for(active: Theme) -> Style:
        # Do not paint the terminal background or inherit built-in menu/reverse
        # styles. Only the focused item and semantic status text carry color.
        if console.legacy_windows:
            active = display_theme(active, console)
            accent = {"green": "ansigreen", "yellow": "ansiyellow",
                      "magenta": "ansimagenta"}.get(active.accent, "ansicyan")
            muted, foreground = "ansiwhite", "ansiwhite"
            success, warning, error = "ansigreen", "ansiyellow", "ansired"
        else:
            accent = active.primary
            muted, foreground = "ansigray", "default"
            success, warning, error = active.success, active.warning, active.error
        styles = {
            "": "",
            "melodine-brand": f"{accent} bold",
            "melodine-heading": f"{accent} bold",
            "melodine-group": f"{muted} bold",
            "melodine-muted": muted,
            "melodine-body": foreground,
            "melodine-menu": foreground,
            "melodine-selected": f"{accent} bold",
            "melodine-value": f"{accent} bold",
            "melodine-success": success,
            "melodine-warning": warning,
            "melodine-error": error,
            "frame.border": muted,
            "frame.label": f"{accent} bold",
        }
        for key, palette in (previews or {}).items():
            for i, color in enumerate((palette.primary, palette.secondary, palette.accent,
                                       palette.success, palette.warning, palette.error)):
                styles[f"melodine-swatch-{key}-{i}"] = f"bg:{color}"
        return Style.from_dict(styles)

    style = DynamicStyle(
        lambda: style_for((previews or {}).get(items[current][0], theme))
    )
    return Application(
        layout=Layout(root, focused_element=menu_control), key_bindings=bindings,
        style=style, full_screen=False, erase_when_done=True, mouse_support=False,
    ).run()
