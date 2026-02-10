from dataclasses import dataclass


@dataclass
class Theme:
    name: str
    label: str
    # Основные
    primary: str
    secondary: str
    accent: str
    # Статусы
    success: str
    error: str
    warning: str
    info: str
    # UI
    border: str
    title: str
    subtitle: str
    muted: str
    # Прогресс-бар
    bar_complete: str
    bar_remaining: str


THEMES: dict[str, Theme] = {
    "dracula": Theme(
        name="dracula",
        label="🧛 Dracula",
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
        label="🌑 Dark",
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
        label="❄️  Nord",
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
        label="🌈 Monokai",
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
        label="🌊 Ocean",
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
        label="🔥 Cyberpunk",
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
        label="🍦 Pastel",
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
}


def get_theme(name: str) -> Theme:
    return THEMES.get(name, THEMES["dracula"])


def list_themes() -> list[tuple[str, str]]:
    return [(key, theme.label) for key, theme in THEMES.items()]