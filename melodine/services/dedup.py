"""Smart deduplication helpers.

Tracks are considered duplicates when they share a ``source_id`` or when
their normalized artist + title match and durations are within tolerance.
Version variants (live / remix / cover / instrumental / ...) are part of
the track identity: "Song" and "Song (Live)" are NOT duplicates.
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


# Variant keywords that change the *identity* of a recording. They are
# deliberately a subset of _NOISE_WORDS: remaster / radio / edit / version
# keep the same identity (same studio recording), while live/remix/cover
# are different recordings and must never dedup against each other.
_VARIANT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("live", re.compile(r"\blive\b|вживую|живь[её]м|концерт", re.IGNORECASE)),
    ("remix", re.compile(r"\bremix\w*|ремикс|\bmashup\b|мэшап|\bbootleg\b", re.IGNORECASE)),
    ("cover", re.compile(r"\bcovers?\b|кавер|covered\s+by", re.IGNORECASE)),
    (
        "instrumental",
        re.compile(r"instrumental|инструментал|\bминус\w*|караоке|karaoke", re.IGNORECASE),
    ),
    ("acoustic", re.compile(r"acoustic|акустик", re.IGNORECASE)),
    ("slowed", re.compile(r"slowed|слоу|\b8d\b|\b9d\b|nightcore", re.IGNORECASE)),
    ("sped", re.compile(r"sped\s*up|speed\s*up", re.IGNORECASE)),
    ("acapella", re.compile(r"a\s*capp?ella|без\s+инструмента", re.IGNORECASE)),
    ("demo", re.compile(r"\bdemo\b|демо", re.IGNORECASE)),
)


def variant_signature(text: str) -> frozenset[str]:
    """Extract the variant identity markers from a raw title.

    ``Song`` -> frozenset(), ``Song (Live at Wembley)`` -> frozenset({'live'}),
    ``Song (Remix)`` -> frozenset({'remix'}). Two tracks can only be
    duplicates when their signatures are equal.
    """
    if not text:
        return frozenset()
    found = {name for name, pattern in _VARIANT_PATTERNS if pattern.search(text)}
    return frozenset(found)


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
    # A live/remix/cover is a different recording than the studio track:
    # identical normalized names are not enough, variants must match too.
    if variant_signature(title_a) != variant_signature(title_b):
        return False
    if duration_a <= 0 or duration_b <= 0:
        return True  # unknown durations: be conservative
    return abs(duration_a - duration_b) <= tolerance
