"""Anti-MV Studio Scorer.

Ranks YouTube search candidates so that official studio audio uploads win
(Topic channels, Official Audio, duration matches) while story-driven music
videos, lives, covers, slowed/8d edits and Shorts sink - unless the user
explicitly asked for that variant.
"""

from __future__ import annotations

import re

from melodine.models import (
    IntentFlags,
    ScoredCandidate,
    ScoreReason,
    SearchCandidate,
)
from melodine.services.titles import clean_track_title, token_similarity

# Base score every candidate starts from.
BASE_SCORE = 50

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
    r"(official\s+music\s+video|music\s+video|videoclip|официальн\w+\s+клип|\bклип\b"
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

    # -- positive signals (studio audio) --------------------------------------
    if penalize:
        if candidate.channel.strip().lower().endswith("- topic"):
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
        cleaned = clean_track_title(candidate.title).title
        if cleaned.lower() == target_title.strip().lower():
            _add("score_reason_title_exact", 12)
        else:
            similarity = token_similarity(cleaned, target_title)
            if similarity >= 0.5:
                _add("score_reason_title_similar", int(15 * similarity),
                     f"{int(similarity * 100)}%")

    # -- negative signals (video / alternate versions) -------------------------
    if penalize:
        matched: list[str] = []
        for pattern, flag in _INTENT_FLAGS_BY_PATTERN:
            if pattern.search(text) and getattr(intent, flag):
                matched.append(flag)
        if getattr(intent, "karaoke", False) and _P_INSTRUMENTAL.search(text):
            matched.append("karaoke")
        if getattr(intent, "sped", False) and _P_ALT_MIX.search(text):
            matched.append("sped")

        if matched:
            # The user explicitly requested this variant: reward it.
            _add("score_reason_intent_match", 15, ", ".join(sorted(set(matched))))
        else:
            penalties: tuple[tuple[re.Pattern[str], str, int], ...] = (
                (_P_MUSIC_VIDEO, "score_penalty_music_video", -35),
                (_P_OFFICIAL_VIDEO, "score_penalty_official_video", -20),
                (_P_LIVE, "score_penalty_live", -50),
                (_P_COVER, "score_penalty_cover", -40),
                (_P_ALT_MIX, "score_penalty_alt_mix", -55),
                (_P_REMIX, "score_penalty_remix", -35),
                (_P_INSTRUMENTAL, "score_penalty_instrumental", -30),
                (_P_REACTION, "score_penalty_reaction", -60),
                (_P_SHORTS, "score_penalty_shorts", -40),
                (_P_LONGFORM, "score_penalty_longform", -30),
                (_P_QUALITY, "score_penalty_quality_markers", -5),
            )
            applied: set[str] = set()
            for pattern, key, points in penalties:
                if pattern.search(text) and key not in applied:
                    _add(key, points)
                    applied.add(key)

    final = max(0, min(100, score))
    return ScoredCandidate(candidate=candidate, score=final, reasons=reasons)


def rank_candidates(
    candidates: list[SearchCandidate],
    **kwargs: object,
) -> list[ScoredCandidate]:
    """Score and sort candidates from best to worst."""
    scored = [
        score_candidate(candidate, **kwargs)  # type: ignore[arg-type]
        for candidate in candidates
    ]
    scored.sort(key=lambda item: item.score, reverse=True)
    return scored
