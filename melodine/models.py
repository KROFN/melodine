"""Domain models shared across services (typed, immutable where possible)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

# --------------------------------------------------------------------------- #
# Codec profiles
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CodecProfile:
    """A yt-dlp compatible audio extraction profile."""

    key: str
    yt_codec: str
    yt_quality: str | None
    extension: str
    lossless: bool
    ffmpeg_encoder: str
    default_bitrate: int = 0  # 0 = encoder default (e.g. FLAC)


CODEC_PRESETS: dict[str, CodecProfile] = {
    "opus": CodecProfile(
        key="opus",
        yt_codec="opus",
        yt_quality="160",
        extension="opus",
        lossless=False,
        ffmpeg_encoder="libopus",
        default_bitrate=160,
    ),
    "mp3": CodecProfile(
        key="mp3",
        yt_codec="mp3",
        yt_quality="320",
        extension="mp3",
        lossless=False,
        ffmpeg_encoder="libmp3lame",
        default_bitrate=320,
    ),
    "m4a": CodecProfile(
        key="m4a",
        yt_codec="m4a",
        yt_quality="256",
        extension="m4a",
        lossless=False,
        ffmpeg_encoder="aac",
        default_bitrate=256,
    ),
    "flac": CodecProfile(
        key="flac",
        yt_codec="flac",
        yt_quality=None,
        extension="flac",
        lossless=True,
        ffmpeg_encoder="flac",
        default_bitrate=0,
    ),
}


def get_codec_profile(key: str) -> CodecProfile:
    """Return a codec profile by key (case-insensitive), mp3 as fallback."""
    return CODEC_PRESETS.get(key.strip().lower(), CODEC_PRESETS["mp3"])


# --------------------------------------------------------------------------- #
# Search & scoring
# --------------------------------------------------------------------------- #


@dataclass
class SearchCandidate:
    """A single YouTube search result."""

    source_id: str = ""
    url: str = ""
    title: str = ""
    channel: str = ""
    duration: int = 0
    views: int = 0

    @classmethod
    def from_ytdlp(cls, entry: dict[str, Any]) -> SearchCandidate:
        return cls(
            source_id=str(entry.get("id") or ""),
            url=str(entry.get("webpage_url") or entry.get("url") or ""),
            title=str(entry.get("title") or ""),
            channel=str(entry.get("channel") or entry.get("uploader") or ""),
            duration=int(entry.get("duration") or 0),
            views=int(entry.get("view_count") or 0),
        )


@dataclass(frozen=True)
class ScoreReason:
    """A single scoring contribution (shown in the metadata preview panel)."""

    key: str  # i18n key, e.g. "score_reason_topic"
    points: int
    value: str = ""  # optional context, e.g. "3s" or "82%"


@dataclass
class ScoredCandidate:
    """A search candidate together with its Anti-MV studio score."""

    candidate: SearchCandidate
    score: int = 0  # 0..100
    reasons: list[ScoreReason] = field(default_factory=list)

    @property
    def badge(self) -> str:
        """One of: studio | video | live | alt (for UI badges)."""
        text = f"{self.candidate.title} {self.candidate.channel}".lower()
        if " topic" in text or "official audio" in text or "audio only" in text:
            return "studio"
        if "live" in text or "концерт" in text:
            return "live"
        if any(
            marker in text
            for marker in (
                "music video",
                "official video",
                "клип",
                " mv ",
                "m/v",
            )
        ):
            return "video"
        return "alt"


# --------------------------------------------------------------------------- #
# Intent detection (Anti-MV override flags)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class IntentFlags:
    """User-requested variants that must not be penalized by the scorer."""

    live: bool = False
    remix: bool = False
    cover: bool = False
    instrumental: bool = False
    acoustic: bool = False
    slowed: bool = False
    sped: bool = False
    extended: bool = False
    karaoke: bool = False

    @property
    def any(self) -> bool:
        return any(
            (
                self.live,
                self.remix,
                self.cover,
                self.instrumental,
                self.acoustic,
                self.slowed,
                self.sped,
                self.extended,
                self.karaoke,
            )
        )


# --------------------------------------------------------------------------- #
# Metadata
# --------------------------------------------------------------------------- #


@dataclass
class EnrichedMeta:
    """Metadata resolved from an external provider (iTunes / MusicBrainz)."""

    title: str = ""
    artist: str = ""
    album: str = ""
    album_artist: str = ""
    genre: str = ""
    year: int | None = None
    track_number: int | None = None
    track_total: int | None = None
    duration: float = 0.0
    artwork_url: str = ""
    source: str = ""

    @classmethod
    def from_itunes(cls, result: dict[str, Any]) -> EnrichedMeta:
        release_date = str(result.get("releaseDate") or "")
        try:
            year = int(release_date[:4]) if release_date[:4].isdigit() else None
        except ValueError:
            year = None
        try:
            duration = float(result.get("trackTimeMillis", 0)) / 1000.0
        except (TypeError, ValueError):
            duration = 0.0
        artwork = str(result.get("artworkUrl100") or "")
        if artwork:
            artwork = artwork.replace("100x100bb", "1000x1000bb")
        try:
            track_number = int(result.get("trackNumber") or 0) or None
        except (TypeError, ValueError):
            track_number = None
        try:
            track_total = int(result.get("trackCount") or 0) or None
        except (TypeError, ValueError):
            track_total = None
        return cls(
            title=str(result.get("trackName") or ""),
            artist=str(result.get("artistName") or ""),
            album=str(result.get("collectionName") or ""),
            album_artist=str(result.get("collectionArtistName") or ""),
            genre=str(result.get("primaryGenreName") or ""),
            year=year,
            track_number=track_number,
            track_total=track_total,
            duration=duration,
            artwork_url=artwork,
            source="itunes",
        )

    @classmethod
    def from_musicbrainz(cls, recording: dict[str, Any]) -> EnrichedMeta:
        artist = ""
        credits = recording.get("artist-credit") or []
        if credits and isinstance(credits[0], dict):
            artist = str(credits[0].get("name") or "")
        album, year = "", None
        releases = recording.get("releases") or []
        if releases:
            album = str(releases[0].get("title") or "")
            date = str(releases[0].get("date") or "")
            if date[:4].isdigit():
                try:
                    year = int(date[:4])
                except ValueError:
                    year = None
        return cls(
            title=str(recording.get("title") or ""),
            artist=artist,
            album=album,
            album_artist=artist,
            year=year,
            source="musicbrainz",
        )


@dataclass
class TrackMeta:
    """Final metadata embedded into a downloaded file."""

    title: str = ""
    artist: str = ""
    album: str = ""
    album_artist: str = ""
    genre: str = ""
    year: int | None = None
    track_number: int | None = None
    track_total: int | None = None
    duration: float = 0.0
    artwork: bytes | None = None


# --------------------------------------------------------------------------- #
# Lyrics
# --------------------------------------------------------------------------- #


@dataclass
class LyricsRecord:
    """A lyrics payload returned by LRCLIB."""

    plain: str = ""
    synced: str = ""
    duration: float = 0.0
    track_name: str = ""
    artist_name: str = ""
    album_name: str = ""
    instrumental: bool = False

    @property
    def has_synced(self) -> bool:
        return bool(self.synced and self.synced.strip())

    @property
    def has_plain(self) -> bool:
        return bool(self.plain and self.plain.strip())

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> LyricsRecord:
        return cls(
            plain=str(payload.get("plainLyrics") or ""),
            synced=str(payload.get("syncedLyrics") or ""),
            duration=float(payload.get("duration") or 0),
            track_name=str(payload.get("trackName") or ""),
            artist_name=str(payload.get("artistName") or ""),
            album_name=str(payload.get("albumName") or ""),
            instrumental=bool(payload.get("instrumental")),
        )


# --------------------------------------------------------------------------- #
# Downloads
# --------------------------------------------------------------------------- #


@dataclass
class DownloadTask:
    """A unit of work for the download pipeline."""

    query: str = ""
    url: str = ""
    title: str = ""
    artist: str = ""
    source: str = "manual"  # manual | search | playlist | watchlist | resume
    intent: IntentFlags = field(default_factory=IntentFlags)
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])

    def to_payload(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "url": self.url,
            "title": self.title,
            "artist": self.artist,
            "source": self.source,
            "intent": {
                "live": self.intent.live,
                "remix": self.intent.remix,
                "cover": self.intent.cover,
                "instrumental": self.intent.instrumental,
                "acoustic": self.intent.acoustic,
                "slowed": self.intent.slowed,
                "sped": self.intent.sped,
                "extended": self.intent.extended,
                "karaoke": self.intent.karaoke,
            },
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> DownloadTask:
        intent_raw = payload.get("intent") or {}
        intent = IntentFlags(
            live=bool(intent_raw.get("live")),
            remix=bool(intent_raw.get("remix")),
            cover=bool(intent_raw.get("cover")),
            instrumental=bool(intent_raw.get("instrumental")),
            acoustic=bool(intent_raw.get("acoustic")),
            slowed=bool(intent_raw.get("slowed")),
            sped=bool(intent_raw.get("sped")),
            extended=bool(intent_raw.get("extended")),
            karaoke=bool(intent_raw.get("karaoke")),
        )
        return cls(
            query=str(payload.get("query") or ""),
            url=str(payload.get("url") or ""),
            title=str(payload.get("title") or ""),
            artist=str(payload.get("artist") or ""),
            source=str(payload.get("source") or "resume"),
            intent=intent,
        )


@dataclass
class DownloadOptions:
    """Per-run overrides (CLI flags). ``None`` means inherit from config."""

    codec: str | None = None
    bitrate: int | None = None
    normalize: bool | None = None
    sponsorblock: bool | None = None
    lyrics: bool | None = None
    enrich: bool | None = None
    artwork: bool | None = None
    dedup: bool | None = None
    folder: str | None = None
    index: int | None = None  # 1-based pick from search results


@dataclass
class DownloadResult:
    """Outcome of processing one DownloadTask."""

    task: DownloadTask
    status: str = "failed"  # success | failed | skipped | cancelled
    path: str = ""
    meta: TrackMeta = field(default_factory=TrackMeta)
    lyrics: LyricsRecord | None = None
    artwork_embedded: bool = False
    normalized: bool = False
    sponsorblock: bool = False
    duplicate: bool = False
    elapsed: float = 0.0
    filesize: int = 0
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "success"


# --------------------------------------------------------------------------- #
# Watchlist / doctor
# --------------------------------------------------------------------------- #


@dataclass
class WatchlistEntry:
    """A tracked playlist/channel subscription."""

    id: int
    url: str
    name: str
    kind: str  # playlist | channel | unknown
    playlist_path: str = ""
    last_synced_at: str = ""
    active: bool = True
    track_count: int = 0


@dataclass
class CheckResult:
    """A single doctor diagnostic."""

    key: str  # i18n key for the check name
    status: str  # ok | warn | fail
    detail: str = ""
    hint_key: str = ""  # optional i18n key with a fix hint
