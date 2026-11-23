"""Smart deduplication helpers.

Tracks are considered duplicates when they share a ``source_id`` or when
their normalized artist + title match and durations are within tolerance.
"""

from __future__ import annotations

import re
import unicodedata

# Words that carry no identity signal when comparing track names.
_NOISE_WORDS = frozenset(
    {
        "official",
        "video",
        "audio",
        "lyrics",
        "lyric",
        "hd",
        "hq",
        "4k",
        "mv",
        "remaster",
        "remastered",
        "radio",
        "edit",
        "version",
        "live",
        "cover",
        "remix",
        "prod",
        "ft",
        "feat",
        "featuring",
        "the",
        "а",
        "официальный",
        "официальное",
        "официальная",
        "клип",
        "аудио",
        "видео",
        "текст",
        "песни",
        "ремикс",
        "кавер",
    }
)


def normalize_name(text: str) -> str:
    """Normalize an artist/title for fuzzy matching.

    Lowercases, strips accents (latin only), removes punctuation, feat
    sections and noise words while keeping Cyrillic intact.
    """
    if not text:
        return ""

    # Remove feat sections: everything from the marker up to the next dash
    # (or the end of the string), keeping artist and title intact.
    text = re.sub(
        r"\b(?:feat\.?|ft\.?|featuring|при\s+уч\.?|при\s+участии)\b[^-–—]*",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    # Drop bracketed content entirely - usually qualifiers.
    text = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", text)

    # Apostrophes join words rather than splitting them (Don't -> dont).
    text = text.replace("'", "").replace("\u2019", "")

    # Unicode: compose, then drop combining marks for latin scripts.
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = unicodedata.normalize("NFKC", text)

    # Keep letters (any script), digits and spaces only.
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"[_\d]+", " ", text)

    tokens = [
        token
        for token in text.lower().split()
        if token and token not in _NOISE_WORDS
    ]
    return " ".join(tokens)


def is_same_track(
    artist_a: str,
    title_a: str,
    artist_b: str,
    title_b: str,
    duration_a: float = 0.0,
    duration_b: float = 0.0,
    tolerance: float = 3.0,
) -> bool:
    """Fuzzy equality used by the dedup engine."""
    if not artist_b or not title_b:
        return False
    if normalize_name(artist_a) != normalize_name(artist_b):
        return False
    if normalize_name(title_a) != normalize_name(title_b):
        return False
    if duration_a <= 0 or duration_b <= 0:
        return True  # unknown durations: be conservative
    return abs(duration_a - duration_b) <= tolerance
