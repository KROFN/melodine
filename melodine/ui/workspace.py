"""Full-screen workspace navigation using prompt_toolkit's native drivers."""

from __future__ import annotations

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

    def menu_width():
        cols = get_app().output.get_size().columns
        return min(46, max(40 if previews else 34, cols * 2 // 5)) if cols >= 82 else cols

    def menu_text():
        fragments = []
        for i, (key, label) in enumerate(items):
            if not key:
                fragments.append(("class:group", f"  {label}\n"))
                continue
            selected = i == current
            line = f" {'❯' if selected else ' '} {key:>2}  {label}"
            row_style = "class:selected" if selected else "class:menu"
            if previews and key in previews:
                fragments.append((row_style, line.ljust(21)))
                for i in range(6):
                    fragments.append((f"class:swatch-{key}-{i}", "  "))
                    fragments.append((row_style, " "))
                fragments.append((row_style, " " * max(0, menu_width() - 41) + "\n"))
            else:
                fragments.append((row_style, line.ljust(max(0, menu_width() - 2)) + "\n"))
        return fragments

    def detail_text():
        key, label = items[current]
        fragments = [
            ("class:muted", f"  {tr('ВЫБРАНО', 'SELECTED')}  /  {key.upper()}\n\n"),
            ("class:heading", f"  {label}\n\n"),
            ("class:body", f"  {details.get(key, '')}\n\n"),
        ]
        if previews and key in previews:
            fragments.extend([
                ("class:heading", f"  {tr('ПРЕДПРОСМОТР', 'PREVIEW')}\n\n"),
                ("class:success", f"  ✓ {tr('Трек загружен', 'Track downloaded')}\n"),
                ("class:warning", f"  ! {tr('Проверка источника', 'Checking source')}\n"),
                ("class:error", f"  × {tr('Ошибка соединения', 'Connection failed')}\n\n"),
                ("class:value", "  ━━━━━━━━━━━━━━━  75%\n\n"),
                ("class:muted", tr("  Enter — применить, Esc — отменить.\n",
                                   "  Enter — apply, Esc — cancel.\n")),
            ])
            return fragments
        fragments.append(("class:muted", f"  {tr('СОСТОЯНИЕ', 'STATUS')}\n"))
        for name, value in status:
            fragments.extend([("class:muted", f"  {name}\n"),
                              ("class:value", f"  {value}\n\n")])
        if context:
            fragments.extend([("class:muted", f"  {tr('ПАПКА МУЗЫКИ', 'MUSIC FOLDER')}\n"),
                              ("class:value", f"  {context}\n")])
        return fragments

    def compact_text():
        key, _ = items[current]
        return [("class:muted", "  " + details.get(key, ""))]

    menu_control = FormattedTextControl(
        menu_text, focusable=True, show_cursor=False,
        get_cursor_position=lambda: Point(x=0, y=current),
    )
    menu = Window(menu_control, always_hide_cursor=True)
    wide = Condition(lambda: get_app().output.get_size().columns >= 82)
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
        ("class:brand", " MELODINE "),
        ("class:heading", f"  /  {title}"),
        ("class:muted", f"  v{__version__}"),
    ]), height=1)
    footer = Window(FormattedTextControl([
        ("class:heading", " ↑↓ "),
        ("class:body", tr("выбор ", "move ")),
        ("class:heading", " Enter "),
        ("class:body", tr("открыть ", "open ")),
        ("class:heading", " Esc "),
        ("class:body", tr("назад ", "back ")),
        ("class:heading", " 0–9 " if not previews else ""),
        ("class:body", tr("команды ", "actions ") if not previews else ""),
        ("class:heading", " q "),
        ("class:body", tr("выход", "back/quit")),
    ]), height=1)
    root = HSplit([
        header,
        Window(height=1, char="─", style="class:group"),
        VSplit([left, right], padding=1),
        ConditionalContainer(
            Window(FormattedTextControl(compact_text), wrap_lines=True, height=3),
            filter=~wide & tall,
        ),
        footer,
    ])
    def style_for(active: Theme) -> Style:
        # prompt_toolkit translates ANSI styles through its Win32 output driver.
        if console.legacy_windows:
            active = display_theme(active, console)
            accent = {
                "bright_magenta": "ansibrightmagenta", "bright_blue": "ansibrightblue",
                "bright_green": "ansibrightgreen", "bright_yellow": "ansibrightyellow",
            }.get(active.primary, "ansibrightcyan")
            muted, background, foreground = "ansiwhite", "ansiblack", "ansiwhite"
            success, warning, error = "ansibrightgreen", "ansibrightyellow", "ansibrightred"
            selected = f"bg:{accent} ansiblack bold"
        else:
            accent = active.primary
            muted, background, foreground = "#a8aec0", "#14161e", "#e4e6ef"
            if active.light:
                muted, background, foreground = "#4b5563", "#f6f4ef", "#21242c"
            success, warning, error = active.success, active.warning, active.error
            selected = f"bg:{accent} #101118 bold"
            if active.light:
                selected = f"bg:{accent} #ffffff bold"
        styles = {
            "": f"bg:{background} {foreground}",
            "brand": selected,
            "heading": f"{accent} bold",
            "group": f"{muted} bold",
            "muted": muted,
            "body": foreground,
            "menu": foreground,
            "selected": selected,
            "value": f"{accent} bold",
            "success": success,
            "warning": warning,
            "error": error,
            "frame.border": muted,
            "frame.label": f"{accent} bold",
        }
        for key, palette in (previews or {}).items():
            for i, color in enumerate((palette.primary, palette.secondary, palette.accent,
                                       palette.success, palette.warning, palette.error)):
                styles[f"swatch-{key}-{i}"] = f"bg:{color}"
        return Style.from_dict(styles)

    style = DynamicStyle(
        lambda: style_for((previews or {}).get(items[current][0], theme))
    )
    return Application(
        layout=Layout(root, focused_element=menu_control), key_bindings=bindings,
        style=style, full_screen=True, mouse_support=False,
    ).run()
