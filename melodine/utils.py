import re
from pathlib import Path
from melodine.locales import t


def sanitize_filename(name: str) -> str:
    s = re.sub(r'[<>:"/\\|?*]', '_', name)
    return s.strip('. ')[:200]


def format_size(b: int) -> str:
    if b < 1024:
        return f"{b} B"
    if b < 1024 ** 2:
        return f"{b / 1024:.1f} KB"
    if b < 1024 ** 3:
        return f"{b / 1024**2:.1f} MB"
    return f"{b / 1024**3:.2f} GB"


def format_time(seconds: float) -> str:
    if seconds < 60:
        return t("time_sec", v=int(seconds))
    if seconds < 3600:
        m, s = divmod(int(seconds), 60)
        return t("time_min", m=m, s=s)
    h, rem = divmod(int(seconds), 3600)
    m, _ = divmod(rem, 60)
    return t("time_hour", h=h, m=m)


# --- playlist parser ---

_NUM_PREFIX = [
    r'^\d{1,4}\.\s+',
    r'^\d{1,4}\)\s+',
    r'^\d{1,4}\]\s+',
    r'^#\d{1,4}\s+',
    r'^\d{1,4}\s*[-–—]\s+',
    r'^\d{1,4}\s+',
]

_JUNK = [
    r'^#', r'^//', r'^--',
    r'^\d+$',
    r'^(всего|total|итого|экспорт|export|дата|date)\s*[:：]',
    r'^https?://', r'^www\.',
    r'^[=\-*_]{3,}',
]

_DASHES = [' - ', ' — ', ' – ', ' − ', ' ‐ ', ' ─ ']


def parse_playlist(filepath: str) -> list[dict]:
    path = Path(filepath)
    if not path.exists():
        return []

    raw = path.read_text(encoding="utf-8-sig")
    tracks = []

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
                tracks.append({"artist": "", "title": line, "query": line, "line": line_num})
            continue

        query = f"{artist} - {title}" if artist else title
        tracks.append({"artist": artist, "title": title, "query": query, "line": line_num})

    return tracks


def _is_junk(line):
    low = line.lower().strip()
    for p in _JUNK:
        if re.match(p, low):
            return True
    return re.match(r'^[\d\s.,:;]+$', line) is not None


def _strip_number(line):
    for p in _NUM_PREFIX:
        cleaned = re.sub(p, '', line)
        if cleaned != line and len(cleaned) > 2:
            return cleaned.strip()
    return line


def _split_track(line):
    for sep in _DASHES:
        if sep in line:
            parts = line.split(sep, 1)
            a, t_ = parts[0].strip(), parts[1].strip()
            if a and t_:
                return a, t_
    return "", ""


def _looks_like_track(line):
    if len(line) > 200:
        return False
    if not re.search(r'[a-zA-Zа-яА-ЯёЁ]', line):
        return False
    if re.match(r'^\d{2,4}[-/.]\d{2}[-/.]\d{2,4}', line):
        return False
    return True