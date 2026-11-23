"""Exception hierarchy for Melodine.

Services are encouraged to return typed results instead of raising,
but these exceptions model unrecoverable or control-flow situations.
"""

from __future__ import annotations


class MelodineError(Exception):
    """Base class for all Melodine errors."""


class ConfigError(MelodineError):
    """Raised when the configuration file cannot be parsed or is invalid."""


class DownloadError(MelodineError):
    """Raised when a download cannot be started or completed."""


class CancelledError(MelodineError):
    """Raised when the user gracefully interrupted an operation."""

    def __init__(self, message: str = "Operation cancelled by user") -> None:
        super().__init__(message)


class ExternalServiceError(MelodineError):
    """Raised when an external API (LRCLIB, iTunes, MusicBrainz) fails hard."""
