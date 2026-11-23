"""Track title parsing & cleaning.

Strips YouTube noise (Official Video, MV, prod. by, HD...) and extracts
featured artists, in both English and Russian.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from melodine.utils import DASHES

# Noise that may appear inside () or [] groups and must be dropped entirely.
_BRACKET_NOISE = re.compile(
    r"""
    (
        official\s+(music\s+)?video |
        official\s+audio |
        official\s+lyric(s)?\s+video |
        official\s+visualizer |
        audio\s+only |
        (with\s+)?lyrics?(\s+video)? |
        visualizer |
        video\s+oficial |
        prod(uced)?\.?\s*by\b[^)]* |
        remaster(ed)?(\s*\d{4})? |
        \b(hd|4k|uhd|60\s*fps|hq)\b |
        \b(mv|m/v)\b |
        (официальный|официальное|официальная)\s+(клип|видео|аудио|аудиоверсия) |
        клип |
        аудиоверсия |
        текст\s+песни |
        премьера\s+клипа
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

_FEAT_RE = re.compile(
    r"\b(feat\.?|ft\.?|featuring|при\s+уч\.?|при\s+участии)\s*", re.IGNORECASE
)

_TRAILING_NOISE = re.compile(
    r"\s*[|\-–—]\s*(official\s+)?(music\s+)?(video|audio|lyric(s)?|visualizer)\s*$",
    re.IGNORECASE,
)

# Standalone noise tokens that may trail a title without brackets
# (e.g. "Song MV", "Song HD", "Song Official Video").
_TRAILING_TOKENS = re.compile(
    r"\s*(?:[|\-–—]\s*)?"
    r"(?:"
    r"official\s+(?:music\s+)?(?:video|audio|visualizer)"
    r"|(?:music\s+)?(?:video|audio)\s+oficial"
    r"|\b(?:mv|m/v|hd|hq|4k|uhd|60\s*fps)\b"
    r")\s*$",
    re.IGNORECASE,
)


@dataclass
class CleanTitle:
    """Result of cleaning a raw YouTube-style title."""

    title: str = ""
    featured: list[str] = field(default_factory=list)


def clean_track_title(raw: str) -> CleanTitle:
    """Remove noise markers from a raw track title, extracting featured artists."""
    if not raw:
        return CleanTitle()

    text = raw.strip()
    featured: list[str] = []

    # -- bracketed groups ----------------------------------------------------
    def _process_group(match: re.Match[str]) -> str:
        content = match.group(1).strip()
        if not content:
            return ""
        if _FEAT_RE.search(content):
            names = _FEAT_RE.sub("", content, count=1).strip(" ,&")
            for name in filter(None, re.split(r"\s*(?:,|&|и)\s*", names)):
                if name:
                    featured.append(name.strip())
            return ""
        if _BRACKET_NOISE.fullmatch(content):
            return ""
        noise_match = _BRACKET_NOISE.search(content)
        if noise_match and len(noise_match.group(0)) >= len(content) - 2:
            # mostly noise with tiny residue such as stray punctuation
            return ""
        return f" ({content})"

    text = re.sub(r"\(([^)]*)\)", _process_group, text)
    text = re.sub(r"\[([^\]]*)\]", _process_group, text)

    # -- unbracketed feat ----------------------------------------------------
    feat_match = _FEAT_RE.search(text)
    if feat_match:
        head, tail = text[: feat_match.start()].strip(), text[feat_match.end() :].strip()
        for name in filter(None, re.split(r"\s*(?:,|&)\s*", tail.split("(", 1)[0])):
            if name:
                featured.append(name.strip())
        text = head

    # -- trailing noise after separators --------------------------------------
    text = _TRAILING_NOISE.sub("", text)
    text = _TRAILING_TOKENS.sub("", text).strip()

    # -- tidy -----------------------------------------------------------------
    text = re.sub(r"\s+", " ", text).strip(" -–—|,.:")
    return CleanTitle(title=text, featured=featured)


def clean_artist(raw: str) -> str:
    """Strip feat sections and brackets from an artist string."""
    if not raw:
        return ""
    text = raw.strip()
    text = re.sub(
        r"\(([^)]*)\)",
        lambda m: f" {m.group(1)} " if _FEAT_RE.search(m.group(1)) else " ",
        text,
    )
    text = re.sub(r"\[[^\]]*\]", " ", text)
    feat_match = _FEAT_RE.search(text)
    if feat_match:
        text = text[: feat_match.start()]
    text = re.sub(r"\s+", " ", text).strip(" ,&")
    return text


def parse_artist_title(raw: str) -> tuple[str, str]:
    """Split a raw 'Artist - Title' string (all v1 dash styles supported)."""
    line = raw.strip()
    for sep in DASHES:
        if sep in line:
            artist, title = line.split(sep, 1)
            artist, title = artist.strip(), title.strip()
            if artist and title:
                return artist, title
    return "", line


def token_similarity(a: str, b: str) -> float:
    """Jaccard similarity over whitespace tokens (0.0 - 1.0)."""
    tokens_a = set(a.lower().split())
    tokens_b = set(b.lower().split())
    if not tokens_a or not tokens_b:
        return 0.0
    union = tokens_a | tokens_b
    if not union:
        return 0.0
    return len(tokens_a & tokens_b) / len(union)
