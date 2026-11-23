"""Color themes.

All seven v1 themes are preserved (dracula, dark, nord, monokai, ocean,
cyberpunk, pastel) and joined by five new premium palettes: daybreak,
forest, sakura, terminal and gruvbox.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    name: str
    label: str
    # Core roles
    primary: str
    secondary: str
    accent: str
    # Statuses
    success: str
    error: str
    warning: str
    info: str
    # UI chrome
    border: str
    title: str
    subtitle: str
    muted: str
    # Progress bar
    bar_complete: str
    bar_remaining: str
    # Light background hint (affects panel styles)
    light: bool = False


THEMES: dict[str, Theme] = {
    # -- preserved v1 themes --
    "dracula": Theme(
        name="dracula",
        label="Dracula",
        primary="#bd93f9",
        secondary="#ff79c6",
        accent="#8be9fd",
        success="#50fa7b",
        error="#ff5555",
        warning="#f1fa8c",
        info="#8be9fd",
        border="#6272a4",
        title="#bd93f9",
        subtitle="#ff79c6",
        muted="#6272a4",
        bar_complete="#bd93f9",
        bar_remaining="#44475a",
    ),
    "dark": Theme(
        name="dark",
        label="Dark",
        primary="#61afef",
        secondary="#c678dd",
        accent="#56b6c2",
        success="#98c379",
        error="#e06c75",
        warning="#e5c07b",
        info="#61afef",
        border="#5c6370",
        title="#61afef",
        subtitle="#c678dd",
        muted="#5c6370",
        bar_complete="#61afef",
        bar_remaining="#3e4452",
    ),
    "nord": Theme(
        name="nord",
        label="Nord",
        primary="#88c0d0",
        secondary="#81a1c1",
        accent="#8fbcbb",
        success="#a3be8c",
        error="#bf616a",
        warning="#ebcb8b",
        info="#88c0d0",
        border="#4c566a",
        title="#88c0d0",
        subtitle="#81a1c1",
        muted="#4c566a",
        bar_complete="#88c0d0",
        bar_remaining="#3b4252",
    ),
    "monokai": Theme(
        name="monokai",
        label="Monokai",
        primary="#a6e22e",
        secondary="#f92672",
        accent="#66d9ef",
        success="#a6e22e",
        error="#f92672",
        warning="#e6db74",
        info="#66d9ef",
        border="#75715e",
        title="#a6e22e",
        subtitle="#f92672",
        muted="#75715e",
        bar_complete="#a6e22e",
        bar_remaining="#3e3d32",
    ),
    "ocean": Theme(
        name="ocean",
        label="Ocean",
        primary="#6cb6ff",
        secondary="#d2a8ff",
        accent="#3ddbd9",
        success="#56d364",
        error="#f47067",
        warning="#e3b341",
        info="#6cb6ff",
        border="#444c56",
        title="#6cb6ff",
        subtitle="#d2a8ff",
        muted="#444c56",
        bar_complete="#6cb6ff",
        bar_remaining="#2d333b",
    ),
    "cyberpunk": Theme(
        name="cyberpunk",
        label="Cyberpunk",
        primary="#ff2a6d",
        secondary="#05d9e8",
        accent="#d1f7ff",
        success="#01c38d",
        error="#ff2a6d",
        warning="#f3e600",
        info="#05d9e8",
        border="#711c91",
        title="#ff2a6d",
        subtitle="#05d9e8",
        muted="#711c91",
        bar_complete="#ff2a6d",
        bar_remaining="#12002b",
    ),
    "pastel": Theme(
        name="pastel",
        label="Pastel",
        primary="#b4befe",
        secondary="#f5c2e7",
        accent="#94e2d5",
        success="#a6e3a1",
        error="#f38ba8",
        warning="#f9e2af",
        info="#89dceb",
        border="#585b70",
        title="#b4befe",
        subtitle="#f5c2e7",
        muted="#585b70",
        bar_complete="#b4befe",
        bar_remaining="#313244",
    ),
    # -- new v2 themes --
    "daybreak": Theme(
        name="daybreak",
        label="Daybreak",
        primary="#b3541e",
        secondary="#6d9dc5",
        accent="#d08c60",
        success="#3a7d44",
        error="#c0392b",
        warning="#caa52b",
        info="#6d9dc5",
        border="#d8c3a5",
        title="#b3541e",
        subtitle="#6d9dc5",
        muted="#8d99ae",
        bar_complete="#b3541e",
        bar_remaining="#e5e0d5",
        light=True,
    ),
    "forest": Theme(
        name="forest",
        label="Forest",
        primary="#8ec07c",
        secondary="#fabd2f",
        accent="#83a598",
        success="#b8bb26",
        error="#fb4934",
        warning="#fe8019",
        info="#8ec07c",
        border="#504945",
        title="#8ec07c",
        subtitle="#fabd2f",
        muted="#7c6f64",
        bar_complete="#8ec07c",
        bar_remaining="#32302f",
    ),
    "sakura": Theme(
        name="sakura",
        label="Sakura",
        primary="#d16ba5",
        secondary="#9059ff",
        accent="#f6b1c1",
        success="#77c593",
        error="#e4572e",
        warning="#f7b32b",
        info="#ba63a8",
        border="#9d8189",
        title="#d16ba5",
        subtitle="#f6b1c1",
        muted="#9d8189",
        bar_complete="#d16ba5",
        bar_remaining="#40323a",
    ),
    "terminal": Theme(
        name="terminal",
        label="Terminal",
        primary="#33ff66",
        secondary="#1fd65f",
        accent="#2ee06a",
        success="#33ff66",
        error="#ff4444",
        warning="#ffd733",
        info="#33ff66",
        border="#1e7a36",
        title="#33ff66",
        subtitle="#7dffa0",
        muted="#1e7a36",
        bar_complete="#33ff66",
        bar_remaining="#0c2a14",
    ),
    "gruvbox": Theme(
        name="gruvbox",
        label="Gruvbox",
        primary="#fe8019",
        secondary="#d3869b",
        accent="#8ec07c",
        success="#b8bb26",
        error="#fb4934",
        warning="#fabd2f",
        info="#83a598",
        border="#665c54",
        title="#fabd2f",
        subtitle="#d3869b",
        muted="#928374",
        bar_complete="#fe8019",
        bar_remaining="#3c3836",
    ),
}

DEFAULT_THEME = "dracula"


def get_theme(name: str) -> Theme:
    """Return a theme by name with graceful fallback to the default."""
    return THEMES.get((name or "").strip().lower(), THEMES[DEFAULT_THEME])


def list_themes() -> list[tuple[str, str]]:
    """Return ``(key, label)`` pairs in stable registration order."""
    return [(key, theme.label) for key, theme in THEMES.items()]


def is_valid_theme(name: str) -> bool:
    return (name or "").strip().lower() in THEMES
