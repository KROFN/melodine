"""Core building blocks: config, logging, shutdown handling, exceptions."""

from __future__ import annotations

from melodine.core.config import AppConfig, load_config, save_config
from melodine.core.exceptions import (
    CancelledError,
    ConfigError,
    DownloadError,
    MelodineError,
)
from melodine.core.logging import get_logger, setup_logging, shutdown_logging
from melodine.core.shutdown import GracefulShutdown

__all__ = [
    "AppConfig",
    "CancelledError",
    "ConfigError",
    "DownloadError",
    "GracefulShutdown",
    "MelodineError",
    "get_logger",
    "load_config",
    "save_config",
    "setup_logging",
    "shutdown_logging",
]
