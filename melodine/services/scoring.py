"""Anti-MV Studio Scorer.

Ranks YouTube search candidates so that official studio audio uploads win
(Topic channels, Official Audio, duration matches) while story-driven music
videos, lives, covers, slowed/8d edits and Shorts sink - unless the user
explicitly asked for that variant.
"""

from __future__ import annotations

import re
import unicodedata

from melodine.models import (
    IntentFlags,
    ScoredCandidate,
    ScoreReason,
    SearchCandidate,
)
from melodine.services.titles import clean_track_title, parse_artist_title, token_similarity

# Base score every candidate starts from.
BASE_SCORE = 50

# Artist identity: compare whole normalized names, never substring matches.
_TOPIC_SUFFIX = re.compile(r"\s*[-–—]\s*topic\s*$", re.IGNORECASE)
_CREDIT_SPLIT = re.compile(r"\s*,\s*|\s+[&/×]\s+|\s+(?:feat\.?|ft\.?|featuring|и|x)\s+", re.I)
_UPLOAD_SUFFIX = re.compile(r"\s*\(слив\s+(?:трека|клипа)(?:\s*,\s*\d{4})?\)\s*$", re.I)
_CYRILLIC = dict(zip("абвгдежзийклмнопрстуфхцчшщъыьэюя",
    ("a", "b", "v", "g", "d", "e", "zh", "z", "i", "i", "k", "l", "m", "n",
     "o", "p", "r", "s", "t", "u", "f", "kh", "ts", "ch", "sh", "shch", "",
     "y", "", "e", "yu", "ya"), strict=True))
_CYRILLIC["ё"] = "e"


def _name_key(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"[^\W_]+", value))


def _credits(value: str) -> set[str]:
    names = {_name_key(part) for part in _CREDIT_SPLIT.split(value)}
    names.add(_name_key(value))
    return names - {""}


def _one_edit_name(a: str, b: str) -> bool:
    """Only one insertion/deletion/substitution in long single-token names."""
    if min(len(a), len(b)) < 8 or " " in a or " " in b:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b, strict=True)) == 1
    if len(a) > len(b):
        a, b = b, a
    return len(b) == len(a) + 1 and any(
        b[:i] + b[i + 1:] == a for i in range(len(b))
    )


def _title_phonetic_key(value: str) -> str:
    # A deliberately narrow cross-script fallback, not an identity check.
    value = "".join(_CYRILLIC.get(ch, ch) for ch in _name_key(value))
    value = re.sub(r"c(?=[eiy])", "s", value).replace("c", "k")
    return re.sub(r"(.)\1+", r"\1", value)


def _cross_script_title_match(a: str, b: str) -> bool:
    a, b = _name_key(a), _name_key(b)
    if not a or not b or max(len(a), len(b)) < 4:
        return False
    if bool(re.search(r"[а-яё]", a)) == bool(re.search(r"[а-яё]", b)):
        return False
    return _title_phonetic_key(a) == _title_phonetic_key(b)


# --------------------------------------------------------------------------- #
# Intent detection
# --------------------------------------------------------------------------- #

_INTENT_PATTERNS: dict[str, re.Pattern[str]] = {
    "live": re.compile(r"\b(live|вживую|живь[её]м|концерт\w*)\b", re.IGNORECASE),
    "remix": re.compile(r"\b(remix|ремикс|mashup|мэшап|bootleg)\b", re.IGNORECASE),
    "cover": re.compile(r"\b(cover|кавер|covered)\b", re.IGNORECASE),
    "instrumental": re.compile(r"\b(instrumental|инструментал\w*|минус\w*)\b", re.IGNORECASE),
    "acoustic": re.compile(r"\b(acoustic|акустик\w*)\b", re.IGNORECASE),
    "slowed": re.compile(r"\b(slowed|слоу|8d|nightcore)\b", re.IGNORECASE),
    "sped": re.compile(r"\b(sped\s*up|speed\s*up)\b", re.IGNORECASE),
    "extended": re.compile(r"\b(extended|extended\s+mix)\b", re.IGNORECASE),
    "karaoke": re.compile(r"\b(karaoke|караоке)\b", re.IGNORECASE),
}


def detect_intent(text: str) -> IntentFlags:
    """Detect variant keywords explicitly present in the user's query."""
    return IntentFlags(
        live=bool(_INTENT_PATTERNS["live"].search(text)),
        remix=bool(_INTENT_PATTERNS["remix"].search(text)),
        cover=bool(_INTENT_PATTERNS["cover"].search(text)),
        instrumental=bool(_INTENT_PATTERNS["instrumental"].search(text)),
        acoustic=bool(_INTENT_PATTERNS["acoustic"].search(text)),
        slowed=bool(_INTENT_PATTERNS["slowed"].search(text)),
        sped=bool(_INTENT_PATTERNS["sped"].search(text)),
        extended=bool(_INTENT_PATTERNS["extended"].search(text)),
        karaoke=bool(_INTENT_PATTERNS["karaoke"].search(text)),
    )


# --------------------------------------------------------------------------- #
# Penalty / bonus patterns
# --------------------------------------------------------------------------- #

_P_MUSIC_VIDEO = re.compile(
    r"(official\s+music\s+video|music\s+video|videoclip|официальн\w+\s+клип|\bклип(?:а|у|ом|е|ы|ов|ам|ами|ах)?\b"
    r"|\bmv\b|m/v)",
    re.IGNORECASE,
)
_P_OFFICIAL_VIDEO = re.compile(r"official\s+video", re.IGNORECASE)
_P_LIVE = re.compile(r"(\blive\b|вживую|живь[её]м|концерт\w*)", re.IGNORECASE)
_P_COVER = re.compile(r"(\bcover\b|\bcovers\b|кавер\w*|covered\s+by)", re.IGNORECASE)
_P_ALT_MIX = re.compile(
    r"(slowed(?:\s*\+\s*reverb)?|8d|\b9d\b|nightcore|bass\s*boosted|reverb|слоу)",
    re.IGNORECASE,
)
_P_REMIX = re.compile(r"(\bremix\b|remixes|remixed|ремикс|mashup|мэшап|bootleg)", re.IGNORECASE)
_P_INSTRUMENTAL = re.compile(r"(instrumental|караоке|karaoke|минус\b|минусовка)", re.IGNORECASE)
_P_REACTION = re.compile(r"(reaction|reacts?\s+to|реакция|обзор\s+на)", re.IGNORECASE)
_P_SHORTS = re.compile(r"(#shorts|\bshorts\b)", re.IGNORECASE)
_P_LONGFORM = re.compile(
    r"(\d+\s*(hour|час)[s]?|full\s+album|полный\s+альбом|compilation|сборник"
    r"|\bmix\b|микс\b|\bloop\b|extended\s+(mix|version))",
    re.IGNORECASE,
)
_P_QUALITY = re.compile(r"(\bhd\b|\b4k\b|60\s*fps|2160p|1080p)", re.IGNORECASE)
# "extended" alone (extended mix / extended version) - the only part of
# _P_LONGFORM that an explicit --extended intent may waive.
_EXTENDED_MARKER = re.compile(r"extended", re.IGNORECASE)

_B_OFFICIAL_AUDIO = re.compile(
    r"(official\s+audio|audio\s+only|официальн\w+\s+аудио|аудиоверсия)", re.IGNORECASE
)
_B_AUDIO = re.compile(r"(\baudio\b|аудио)", re.IGNORECASE)
_B_LYRICS = re.compile(r"(текст\s+песни|lyrics)", re.IGNORECASE)

_INTENT_FLAGS_BY_PATTERN: tuple[tuple[re.Pattern[str], str], ...] = (
    (_P_LIVE, "live"),
    (_P_COVER, "cover"),
    (_P_REMIX, "remix"),
    (_P_INSTRUMENTAL, "instrumental"),
    (_P_ALT_MIX, "slowed"),
    (_P_LONGFORM, "extended"),
)


def score_candidate(
    candidate: SearchCandidate,
    *,
    target_title: str = "",
    target_artist: str = "",
    expected_duration: float | None = None,
    intent: IntentFlags | None = None,
    penalize: bool = True,
) -> ScoredCandidate:
    """Score one candidate in the 0..100 range with a human-readable trail."""
    intent = intent or IntentFlags()
    text = f"{candidate.title} {candidate.channel}".lower()
    reasons: list[ScoreReason] = []
    score = BASE_SCORE

    def _add(key: str, points: int, value: str = "") -> None:
        nonlocal score
        score += points
        reasons.append(ScoreReason(key=key, points=points, value=value))

    credited_artist, track_title = parse_artist_title(clean_track_title(candidate.title).title)
    track_title = _UPLOAD_SUFFIX.sub("", track_title)
    channel_artist = _TOPIC_SUFFIX.sub("", candidate.channel)
    requested = _credits(target_artist)
    channel_key = _name_key(channel_artist)
    credits = _credits(credited_artist)
    channel_match = channel_key in requested
    credit_match = bool(requested & credits)
    title_match = bool(target_title) and (
        _name_key(track_title) == _name_key(target_title)
        or _cross_script_title_match(track_title, target_title)
    )
    # A typo is only accepted when the channel's whole name also occurs in
    # the video's artist credits and the requested track title matches.
    corroborated_typo = title_match and channel_key in credits and any(
        _one_edit_name(name, channel_key) for name in requested
    )
    if channel_match or credit_match or corroborated_typo:
        _add("score_reason_artist_match", 20)
    if (candidate.channel_is_verified is True and title_match
            and (channel_match or corroborated_typo)):
        _add("score_reason_verified_artist", 15)

    # -- positive signals (studio audio) --------------------------------------
    if penalize:
        if _TOPIC_SUFFIX.search(candidate.channel) and (not requested or channel_match or corroborated_typo):
            _add("score_reason_topic", 40)
        if _B_OFFICIAL_AUDIO.search(text):
            _add("score_reason_official_audio", 25)
        elif _B_AUDIO.search(text):
            _add("score_reason_audio", 10)
        if _B_LYRICS.search(text) and not _P_MUSIC_VIDEO.search(text):
            _add("score_reason_lyrics", 5)

    # -- duration match --------------------------------------------------------
    if expected_duration and expected_duration > 0 and candidate.duration > 0:
        delta = abs(candidate.duration - expected_duration)
        if delta <= 2:
            _add("score_reason_duration_exact", 25)
        elif delta <= 5:
            _add("score_reason_duration_close", 15, f"{delta:.0f}s")
        elif delta > 15:
            _add("score_reason_duration_far", -15, f"{delta:.0f}s")

    # -- title similarity ------------------------------------------------------
    if target_title:
        cleaned = track_title
        if _name_key(cleaned) == _name_key(target_title):
            _add("score_reason_title_exact", 12)
        elif _cross_script_title_match(cleaned, target_title):
            _add("score_reason_title_transliterated", 10)
        else:
            similarity = token_similarity(cleaned, target_title)
            if similarity >= 0.5:
                _add("score_reason_title_similar", int(15 * similarity),
                     f"{int(similarity * 100)}%")

    # -- negative signals (video / alternate versions) -------------------------
    if penalize:
        matched: set[str] = set()
        for pattern, flag in _INTENT_FLAGS_BY_PATTERN:
            if pattern.search(text) and getattr(intent, flag):
                matched.add(flag)
        if getattr(intent, "karaoke", False) and _P_INSTRUMENTAL.search(text):
            matched.add("karaoke")
        if getattr(intent, "sped", False) and _P_ALT_MIX.search(text):
            matched.add("sped")

        if matched:
            # The user explicitly requested this variant: reward it.
            _add("score_reason_intent_match", 15, ", ".join(sorted(matched)))

        # Penalties apply unconditionally - an explicit `--live` only waives
        # the *live* penalty, it must not silence the cover/reaction/MV
        # penalties of a candidate like "LIVE COVER REACTION".
        penalties: tuple[tuple[re.Pattern[str], str, int, frozenset[str]], ...] = (
            (_P_MUSIC_VIDEO, "score_penalty_music_video", -35, frozenset()),
            (_P_OFFICIAL_VIDEO, "score_penalty_official_video", -20, frozenset()),
            (_P_LIVE, "score_penalty_live", -50, frozenset({"live"})),
            (_P_COVER, "score_penalty_cover", -40, frozenset({"cover"})),
            (_P_ALT_MIX, "score_penalty_alt_mix", -55, frozenset({"slowed", "sped"})),
            (_P_REMIX, "score_penalty_remix", -35, frozenset({"remix"})),
            (
                _P_INSTRUMENTAL,
                "score_penalty_instrumental",
                -30,
                frozenset({"instrumental", "karaoke"}),
            ),
            (_P_REACTION, "score_penalty_reaction", -60, frozenset()),
            (_P_SHORTS, "score_penalty_shorts", -40, frozenset()),
            (
                _P_LONGFORM,
                "score_penalty_longform",
                -30,
                # "extended" only waives the extended-mix part of the pattern,
                # never the "full album" / "1 hour mix" parts.
                frozenset({"extended"}) if _EXTENDED_MARKER.search(text) else frozenset(),
            ),
            (_P_QUALITY, "score_penalty_quality_markers", -5, frozenset()),
        )
        applied: set[str] = set()
        for pattern, key, points, waivable_by in penalties:
            if key in applied:
                continue
            if pattern.search(text):
                if waivable_by & matched:
                    # Requested variant: waive exactly this penalty.
                    _add(key, 0, "requested")
                else:
                    _add(key, points)
                applied.add(key)

    final = max(0, min(100, score))
    return ScoredCandidate(candidate=candidate, score=final, reasons=reasons)


def ranking_key(item: ScoredCandidate) -> tuple[int, int]:
    return item.score, sum(reason.points for reason in item.reasons)


def rank_candidates(
    candidates: list[SearchCandidate],
    **kwargs: object,
) -> list[ScoredCandidate]:
    """Score and sort candidates from best to worst."""
    scored = [
        score_candidate(candidate, **kwargs)  # type: ignore[arg-type]
        for candidate in candidates
    ]
    scored.sort(key=ranking_key, reverse=True)
    return scored
