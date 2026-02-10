import yt_dlp


def search_tracks(query: str, max_results: int = 5) -> list[dict]:
    ydl_opts = {
        "default_search": f"ytsearch{max_results}",
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "noplaylist": True,
    }

    results = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)

            entries = info.get("entries", [info]) if info else []

            for entry in entries:
                if not entry:
                    continue
                results.append({
                    "url": entry.get("webpage_url", ""),
                    "title": entry.get("title", "Unknown"),
                    "channel": entry.get("channel", entry.get("uploader", "Unknown")),
                    "duration": entry.get("duration", 0),
                    "views": entry.get("view_count", 0),
                    "id": entry.get("id", ""),
                })
    except Exception:
        pass

    return results


def generate_search_queries(artist: str, title: str) -> list[str]:
    queries = []
    original = f"{artist} - {title}" if artist else title
    queries.append(original)

    if artist:
        # Убрать feat., prod., скобки
        import re
        clean_artist = re.sub(r'\(.*?\)', '', artist).strip()
        clean_artist = re.sub(r'feat\.?.*', '', clean_artist, flags=re.IGNORECASE).strip()
        clean_title = re.sub(r'\(.*?\)', '', title).strip()

        if f"{clean_artist} - {clean_title}" != original:
            queries.append(f"{clean_artist} - {clean_title}")

        # Только первый артист
        first_artist = re.split(r'[,&/]', artist)[0].strip()
        if first_artist != artist:
            queries.append(f"{first_artist} - {title}")

        # Только название
        queries.append(title)

        # С "official audio"
        queries.append(f"{first_artist} - {title} official audio")

    return queries


def format_duration(seconds: int) -> str:
    if not seconds:
        return "?"
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def format_views(views: int) -> str:
    if not views:
        return "?"
    if views >= 1_000_000_000:
        return f"{views / 1_000_000_000:.1f}B"
    if views >= 1_000_000:
        return f"{views / 1_000_000:.1f}M"
    if views >= 1_000:
        return f"{views / 1_000:.1f}K"
    return str(views)