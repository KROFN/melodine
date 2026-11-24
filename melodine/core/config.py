"""Typed, backward-compatible configuration for Melodine v2.

v1 ``config.yaml`` files load transparently:

* ``paths.output`` / ``paths.failed_log``  -> ``output.folder`` / ``output.failed_log``
* ``download.quality``                    -> ``audio.bitrate``
* ``download.download_covers``            -> ``artwork.embed``
* ``metadata.add_tags``                   -> ``tags.enabled``
* ``metadata.download_covers``            -> ``artwork.embed``

All v1 sections (``download``, ``metadata``) keep their original field names
where the semantics survived into v2, so hand-edited configs never break.
"""

from __future__ import annotations

import contextlib
import copy
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from melodine.core.exceptions import ConfigError

DEFAULT_CONFIG_PATH = Path("config.yaml")

VALID_LANGUAGES = ("ru", "en")
VALID_PROVIDERS = ("itunes", "musicbrainz")


class SearchConfig(BaseModel):
    """Anti-MV search tuning."""

    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    anti_mv: bool = True
    results: int = Field(default=10, ge=3, le=30)
    min_score: int = Field(default=50, ge=0, le=100)
    duration_tolerance: int = Field(default=3, ge=1, le=15)


class DownloadConfig(BaseModel):
    """Transport-level behaviour (v1 compatible field names)."""

    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    threads: int = Field(default=4, ge=1, le=15)
    pause: float = Field(default=0.5, ge=0.0, le=10.0)
    retry_attempts: int = Field(default=3, ge=0, le=10)
    retry_delay: float = Field(default=5.0, ge=0.0, le=60.0)
    max_duration: int = Field(default=900, ge=60, le=7200)
    timeout: int = Field(default=30, ge=5, le=120)
    smart_search: bool = True
    # Anti-bot / datacenter survival: pass cookies through to yt-dlp.
    cookies_file: str = ""
    cookies_from_browser: str = ""


class AudioConfig(BaseModel):
    """Codec profile and EBU R128 normalization settings."""

    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    codec: str = "mp3"
    bitrate: int = Field(default=320, ge=32, le=320)
    normalize: bool = False
    target_lufs: float = Field(default=-14.0, ge=-30.0, le=-5.0)
    true_peak: float = Field(default=-1.5, ge=-9.0, le=0.0)
    lra: int = Field(default=11, ge=1, le=20)

    @field_validator("codec")
    @classmethod
    def _validate_codec(cls, value: str) -> str:
        from melodine.models import CODEC_PRESETS

        normalized = value.strip().lower()
        if normalized not in CODEC_PRESETS:
            allowed = ", ".join(sorted(CODEC_PRESETS))
            raise ValueError(f"unknown codec {value!r}; expected one of: {allowed}")
        return normalized


class OutputConfig(BaseModel):
    """Where files land and how they are named."""

    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    folder: str = "./downloads"
    template: str = "{artist}/{album}/{track_num} - {title}.{ext}"
    failed_log: str = "./failed_tracks.txt"

    @field_validator("template")
    @classmethod
    def _validate_template(cls, value: str) -> str:
        if "{title}" not in value or "{ext}" not in value:
            raise ValueError("output template must contain {title} and {ext}")
        return value


class SponsorBlockConfig(BaseModel):
    """SponsorBlock + ModifyChapters postprocessing (runs before audio extraction)."""

    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    enabled: bool = True
    categories: list[str] = Field(
        default_factory=lambda: [
            "music_offtopic",
            "sponsor",
            "intro",
            "outro",
            "selfpromo",
        ]
    )
    force_keyframes: bool = True

    @field_validator("categories")
    @classmethod
    def _validate_categories(cls, value: list[str]) -> list[str]:
        allowed = {
            "sponsor",
            "selfpromo",
            "interaction",
            "intro",
            "outro",
            "preview",
            "music_offtopic",
            "filler",
        }
        cleaned: list[str] = []
        for category in value:
            normalized = category.strip()
            if normalized in allowed and normalized not in cleaned:
                cleaned.append(normalized)
        return cleaned or ["music_offtopic"]


class LyricsConfig(BaseModel):
    """LRCLIB powered synced-lyrics engine."""

    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    enabled: bool = True
    synced: bool = True
    save_lrc: bool = True
    rate_limit_ms: int = Field(default=350, ge=0, le=5000)
    duration_tolerance: int = Field(default=3, ge=1, le=15)


class ArtworkConfig(BaseModel):
    """Smart 16:9 -> 1:9 square artwork cropping and embedding."""

    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    embed: bool = True
    crop: bool = True
    size: int = Field(default=1000, ge=256, le=2000)


class MetadataConfig(BaseModel):
    """Metadata enrichment via iTunes Search / MusicBrainz."""

    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    enrich: bool = True
    providers: list[str] = Field(default_factory=lambda: ["itunes", "musicbrainz"])

    @field_validator("providers")
    @classmethod
    def _validate_providers(cls, value: list[str]) -> list[str]:
        cleaned = [p.strip().lower() for p in value if p.strip().lower() in VALID_PROVIDERS]
        return cleaned or ["itunes"]


class TagsConfig(BaseModel):
    """Whether to write tags into downloaded files (v1: metadata.add_tags)."""

    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    enabled: bool = True


class DatabaseConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    path: str = "melodine.db"


class LoggingConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    file: str = "melodine.log"
    level: str = "INFO"
    max_bytes: int = Field(default=1_048_576, ge=64_000)
    backups: int = Field(default=3, ge=1, le=20)

    @field_validator("level")
    @classmethod
    def _validate_level(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
            raise ValueError(f"unknown log level {value!r}")
        return normalized


class WatchlistConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    m3u8_folder: str = ""  # empty -> next to output.folder


class AppConfig(BaseModel):
    """Root configuration object."""

    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    theme: str = "dracula"
    language: str = "ru"
    show_legacy_terminal_notice: bool = True
    search: SearchConfig = Field(default_factory=SearchConfig)
    download: DownloadConfig = Field(default_factory=DownloadConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    sponsorblock: SponsorBlockConfig = Field(default_factory=SponsorBlockConfig)
    lyrics: LyricsConfig = Field(default_factory=LyricsConfig)
    artwork: ArtworkConfig = Field(default_factory=ArtworkConfig)
    metadata: MetadataConfig = Field(default_factory=MetadataConfig)
    tags: TagsConfig = Field(default_factory=TagsConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    watchlist: WatchlistConfig = Field(default_factory=WatchlistConfig)

    @field_validator("language")
    @classmethod
    def _validate_language(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in VALID_LANGUAGES:
            raise ValueError(f"language must be one of {VALID_LANGUAGES}, got {value!r}")
        return normalized


def migrate_legacy_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Map a v1 config dictionary onto the v2 structure (in place, returns copy)."""
    data = copy.deepcopy(data)

    legacy_download = data.get("download") or {}
    if isinstance(legacy_download, dict):
        audio = dict(data.get("audio") or {})
        if "quality" in legacy_download and "bitrate" not in audio:
            with contextlib.suppress(TypeError, ValueError):
                audio["bitrate"] = int(legacy_download["quality"])
        data["audio"] = audio

        artwork = dict(data.get("artwork") or {})
        if legacy_download.get("download_covers") is not None and "embed" not in artwork:
            artwork["embed"] = bool(legacy_download["download_covers"])
        data["artwork"] = artwork

    legacy_paths = data.get("paths")
    if isinstance(legacy_paths, dict):
        output = dict(data.get("output") or {})
        if legacy_paths.get("output") and "folder" not in output:
            output["folder"] = legacy_paths["output"]
        if legacy_paths.get("failed_log") and "failed_log" not in output:
            output["failed_log"] = legacy_paths["failed_log"]
        data["output"] = output
        data.pop("paths", None)

    legacy_metadata = data.get("metadata") or {}
    if isinstance(legacy_metadata, dict):
        tags = dict(data.get("tags") or {})
        if legacy_metadata.get("add_tags") is not None and "enabled" not in tags:
            tags["enabled"] = bool(legacy_metadata["add_tags"])
        data["tags"] = tags

        artwork = dict(data.get("artwork") or {})
        if legacy_metadata.get("download_covers") is not None and "embed" not in artwork:
            artwork["embed"] = bool(legacy_metadata["download_covers"])
        data["artwork"] = artwork

    # Drop legacy-only keys so pydantic never sees conflicting leftovers.
    download = data.get("download")
    if isinstance(download, dict):
        for key in ("quality", "download_covers"):
            download.pop(key, None)
    metadata = data.get("metadata")
    if isinstance(metadata, dict):
        for key in ("add_tags", "download_covers"):
            metadata.pop(key, None)
    return data


def load_config(path: str | Path | None = None) -> tuple[AppConfig, bool]:
    """Load configuration, migrating v1 files transparently.

    Returns a tuple ``(config, created_default)`` where ``created_default``
    is True when no config file existed and a fresh default was written.
    """
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        config = AppConfig()
        # Read-only CWD: fall back to in-memory defaults.
        with contextlib.suppress(OSError):
            save_config(config, config_path)
        return config, True

    try:
        raw: Any = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError) as exc:
        raise ConfigError(f"cannot read {config_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raw = {}

    migrated = migrate_legacy_dict(raw)
    try:
        return AppConfig.model_validate(migrated), False
    except Exception as exc:  # pydantic ValidationError
        raise ConfigError(f"invalid configuration in {config_path}: {exc}") from exc


def save_config(config: AppConfig, path: str | Path | None = None) -> None:
    """Persist the configuration in canonical v2 YAML form."""
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    payload = config.model_dump(mode="json")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as fh:
        yaml.dump(
            payload,
            fh,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
