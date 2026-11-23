"""Localization subsystem (RU / EN) with 100% key parity."""

from __future__ import annotations

from melodine.i18n.locales import (
    LOCALES,
    get_language,
    set_language,
    t,
)

__all__ = ["LOCALES", "get_language", "set_language", "t"]
