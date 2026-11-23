"""Shared helpers: filename sanitizing, human formatting, playlist parsing.

The playlist parser is the beating heart of Melodine v1 and is preserved
byte-for-byte in spirit: it eats dirty text playlists with line numbers,
junk lines, different dash styles and RU/EN headers.
"""

from __future__ import annotations

import re
from pathlib import Path

from melodine.i18n import t

DASHES = (" - ", " — ", " – ", " − ", " ‐ ", " ─ ")

_NUM_PREFIX = [
    r"^\d{1,4}\.\s+",
    r"^\d{1,4}\)\s+",
    r"^\d{1,4}\]\s+",
    r"^#\d{1,4}\s+",
    r"^\d{1,4}\s*[-–—]\s+",
    r"^\d{1,4}\s+",
]

_JUNK = [
    r"^#",
    r"^//",
    r"^--",
    r"^\d+$",
    r"^(всего|total|итого|экспорт|export|дата|date)\s*[:：]",
    r"^https?://",
    r"^www\.",
    r"^[=\-*_]{3,}",
]


def sanitize_filename(name: str) -> str:
    """Make a string safe as a filename on all major platforms."""
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    s = re.sub(r"\s+", " ", s).strip(" .")
    return s[:200] or "untitled"


def format_size(num_bytes: int | float) -> str:
    value = float(num_bytes)
    if value < 1024:
        return f"{int(value)} B"
    if value < 1024**2:
        return f"{value / 1024:.1f} KB"
    if value < 1024**3:
        return f"{value / 1024**2:.1f} MB"
    return f"{value / 1024**3:.2f} GB"


def format_time(seconds: float) -> str:
    total = int(seconds)
    if total < 60:
        return t("time_sec", v=total)
    if total < 3600:
        m, s = divmod(total, 60)
        return t("time_min", m=m, s=s)
    h, rem = divmod(total, 3600)
    m, _ = divmod(rem, 60)
    return t("time_hour", h=h, m=m)


def format_duration(seconds: int | float | None) -> str:
    if not seconds:
        return "?"
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_views(views: int | None) -> str:
    if not views:
        return "?"
    if views >= 1_000_000_000:
        return f"{views / 1_000_000_000:.1f}B"
    if views >= 1_000_000:
        return f"{views / 1_000_000:.1f}M"
    if views >= 1_000:
        return f"{views / 1_000:.1f}K"
    return str(views)


def format_speed(bytes_per_second: float | None) -> str:
    if not bytes_per_second:
        return "--"
    return f"{format_size(bytes_per_second)}/s"


# --------------------------------------------------------------------------- #
# Playlist (.txt) parsing - preserved from v1
# --------------------------------------------------------------------------- #


def parse_playlist(filepath: str | Path) -> list[dict[str, str | int]]:
    """Parse a text playlist into ``{artist, title, query, line}`` dicts."""
    path = Path(filepath)
    if not path.exists():
        return []

    raw = path.read_text(encoding="utf-8-sig")
    tracks: list[dict[str, str | int]] = []

    for line_num, raw_line in enumerate(raw.splitlines(), 1):
        line = raw_line.strip()
        if not line or len(line) < 3:
            continue
        if _is_junk(line):
            continue

        line = _strip_number(line)
        if not line or len(line) < 3:
            continue

        artist, title = _split_track(line)

        if not title:
            if _looks_like_track(line):
                tracks.append(
                    {"artist": "", "title": line, "query": line, "line": line_num}
                )
            continue

        query = f"{artist} - {title}" if artist else title
        tracks.append(
            {"artist": artist, "title": title, "query": query, "line": line_num}
        )

    return tracks


def _is_junk(line: str) -> bool:
    low = line.lower().strip()
    for pattern in _JUNK:
        if re.match(pattern, low):
            return True
    return re.match(r"^[\d\s.,:;]+$", line) is not None


def _strip_number(line: str) -> str:
    for pattern in _NUM_PREFIX:
        cleaned = re.sub(pattern, "", line)
        if cleaned != line and len(cleaned) > 2:
            return cleaned.strip()
    return line


def _split_track(line: str) -> tuple[str, str]:
    for sep in DASHES:
        if sep in line:
            parts = line.split(sep, 1)
            artist, title = parts[0].strip(), parts[1].strip()
            if artist and title:
                return artist, title
    return "", ""


def _looks_like_track(line: str) -> bool:
    if len(line) > 200:
        return False
    if not re.search(r"[a-zA-Zа-яА-ЯёЁ]", line):
        return False
    return not re.match(r"^\d{2,4}[-/.]\d{2}[-/.]\d{2,4}", line)
