"""Minimal HTTP helper used by all external providers.

Centralizing requests here keeps providers trivially mockable in tests.
"""

from __future__ import annotations

import threading
from typing import Any

import requests

from melodine import __user_agent__
from melodine.core.logging import get_logger

logger = get_logger("http")

_session: requests.Session | None = None
_session_lock = threading.Lock()


def get_session() -> requests.Session:
    global _session
    with _session_lock:
        if _session is None:
            _session = requests.Session()
            _session.headers.update({"User-Agent": __user_agent__})
        return _session


def get_json(
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
) -> Any:
    """GET a URL and parse JSON. Raises requests exceptions on failure."""
    response = get_session().get(url, params=params, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()


def get_bytes(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: float = 20.0,
) -> bytes:
    """GET a URL returning raw bytes (artwork downloads)."""
    response = get_session().get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.content
