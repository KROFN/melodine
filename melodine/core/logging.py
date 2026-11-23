"""Centralized non-blocking logging.

All library chatter (yt-dlp, ffmpeg subprocesses, providers) is routed to a
background ``QueueListener`` that writes to a rotating log file.  Nothing ever
prints to stdout, so the rich TUI rendering can never be corrupted.
"""

from __future__ import annotations

import contextlib
import logging
import logging.handlers
import queue
import sys
from pathlib import Path
from typing import Any

from melodine import __version__
from melodine.core.config import LoggingConfig

_ROOT_LOGGER_NAME = "melodine"

_state: dict[str, Any] = {"listener": None, "configured": False}


class YtdlpLogger:
    """Adapter satisfying the yt-dlp ``logger`` option protocol."""

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def debug(self, msg: str) -> None:
        self._logger.debug(msg)

    def info(self, msg: str) -> None:
        self._logger.info(msg)

    def warning(self, msg: str) -> None:
        self._logger.warning(msg)

    def error(self, msg: str) -> None:
        self._logger.error(msg)


def setup_logging(cfg: LoggingConfig, verbose: bool = False) -> logging.Logger:
    """Install the queue-based rotating handler (idempotent)."""
    if _state["configured"]:
        return logging.getLogger(_ROOT_LOGGER_NAME)

    root = logging.getLogger(_ROOT_LOGGER_NAME)
    level_name = "DEBUG" if verbose else cfg.level
    root.setLevel(logging.getLevelName(level_name))
    root.propagate = False

    log_path = Path(cfg.file)
    if log_path.parent and not log_path.parent.exists():
        with contextlib.suppress(OSError):
            log_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=cfg.max_bytes,
            backupCount=cfg.backups,
            encoding="utf-8",
        )
    except OSError:
        # Cannot open the log file (read-only FS): fall back to a null handler
        # so callers never crash because of logging.
        root.addHandler(logging.NullHandler())
        _state["configured"] = True
        return root

    file_handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    handlers: list[logging.Handler] = [file_handler]
    if verbose:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(
            logging.Formatter(fmt="%(levelname)-8s | %(name)s | %(message)s")
        )
        handlers.append(console_handler)

    log_queue: queue.SimpleQueue[logging.LogRecord] = queue.SimpleQueue()
    root.addHandler(logging.handlers.QueueHandler(log_queue))
    listener = logging.handlers.QueueListener(
        log_queue, *handlers, respect_handler_level=True
    )
    listener.start()

    _state["listener"] = listener
    _state["configured"] = True

    root.info("Melodine v%s starting", __version__)
    return root


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced child logger (e.g. ``melodine.services.lyrics``)."""
    clean = name.removeprefix(_ROOT_LOGGER_NAME + ".")
    return logging.getLogger(f"{_ROOT_LOGGER_NAME}.{clean}")


def shutdown_logging() -> None:
    """Flush and stop the background listener (call on exit)."""
    listener = _state.get("listener")
    if listener is not None:
        with contextlib.suppress(Exception):
            listener.stop()
        _state["listener"] = None
    _state["configured"] = False
