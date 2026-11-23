"""Library / history exporter (M3U8 + JSON)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from melodine.core.config import AppConfig
from melodine.core.exceptions import ConfigError
from melodine.db.database import Database
from melodine.services.playlists import write_m3u8


class Exporter:
    """Export the track library or download history."""

    def __init__(self, db: Database, cfg: AppConfig) -> None:
        self.db = db
        self.cfg = cfg

    # ------------------------------------------------------------------ #

    def _entries(self, scope: str) -> list[dict[str, Any]]:
        if scope == "history":
            return self.db.list_history(limit=100_000)
        return self.db.list_tracks(limit=100_000)

    def default_path(self, fmt: str, scope: str) -> Path:
        base = Path(self.cfg.output.folder)
        base.mkdir(parents=True, exist_ok=True)
        return base / f"melodine-{scope}.{fmt}"

    # ------------------------------------------------------------------ #

    def export_m3u8(self, path: str | Path, *, scope: str = "library", name: str = "") -> int:
        if scope not in {"library", "history"}:
            raise ConfigError(f"unknown export scope: {scope}")
        if scope == "history":
            # M3U8 needs playable file paths - only successful history rows.
            entries = [
                {
                    "filepath": row["file_path"],
                    "title": row["title"] or row["query"],
                    "artist": row["artist"],
                    "duration": 0,
                }
                for row in self.db.list_history(limit=100_000)
                if row["status"] == "success" and row["file_path"]
            ]
        else:
            entries = self._entries(scope)
        return write_m3u8(
            path,
            name or "Melodine Library",
            entries,
            relative_to=Path(path).parent,
        )

    def export_json(self, path: str | Path, *, scope: str = "library") -> int:
        if scope not in {"library", "history"}:
            raise ConfigError(f"unknown export scope: {scope}")
        entries = self._entries(scope)
        payload = {
            "app": "melodine",
            "version": 2,
            "scope": scope,
            "count": len(entries),
            "entries": entries,
        }
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return len(entries)
