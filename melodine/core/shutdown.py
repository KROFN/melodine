"""Graceful shutdown support (Ctrl+C / SIGTERM).

First signal: set the event and run registered callbacks (cancel downloads,
persist queue state).  Second signal: hard exit so a hung subprocess cannot
trap the user.
"""

from __future__ import annotations

import contextlib
import os
import signal
import threading
from collections.abc import Callable
from types import FrameType


class GracefulShutdown:
    """Cooperative cancellation token driven by SIGINT/SIGTERM."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._callbacks: list[Callable[[], None]] = []
        self._lock = threading.Lock()
        self._installed = False
        self._previous: dict[int, signal.Handlers | None] = {}

    # -- state ---------------------------------------------------------------

    @property
    def triggered(self) -> bool:
        return self._event.is_set()

    def trigger(self) -> None:
        """Programmatically trigger shutdown (used by tests and UI buttons)."""
        self._handle(signal.SIGINT, None)

    # -- installation --------------------------------------------------------

    def install(self) -> None:
        if self._installed:
            return
        handled = [signal.SIGINT]
        with contextlib.suppress(AttributeError, ValueError, OSError):  # Windows
            handled.append(signal.SIGTERM)
        for sig in handled:
            try:
                self._previous[sig] = signal.signal(sig, self._handle)
            except (ValueError, OSError):
                # Not on the main thread, or unsupported platform: keep going.
                continue
        self._installed = True

    def restore(self) -> None:
        if not self._installed:
            return
        for sig, handler in self._previous.items():
            try:
                signal.signal(sig, handler)  # type: ignore[arg-type]
            except (ValueError, OSError, TypeError):
                continue
        self._previous.clear()
        self._installed = False

    # -- callbacks -----------------------------------------------------------

    def on_shutdown(self, callback: Callable[[], None]) -> None:
        with self._lock:
            self._callbacks.append(callback)

    def _run_callbacks(self) -> None:
        with self._lock:
            callbacks = list(self._callbacks)
        for callback in callbacks:
            with contextlib.suppress(Exception):
                callback()

    # -- internals -----------------------------------------------------------

    def _handle(self, sig: int, frame: FrameType | None) -> None:
        if self._event.is_set():
            # Second Ctrl+C: the user insists - exit immediately.
            os._exit(130)
        self._event.set()
        self._run_callbacks()
