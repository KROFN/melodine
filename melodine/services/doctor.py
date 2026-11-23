"""Environment diagnostics for ``melodine doctor``."""

from __future__ import annotations

import shutil
import subprocess
import sys

from melodine import __version__
from melodine.core.config import AppConfig
from melodine.core.logging import get_logger
from melodine.db.database import Database
from melodine.models import CheckResult
from melodine.services import http

logger = get_logger("doctor")

MIN_PYTHON = (3, 10)


def _tool_version(binary: str) -> str | None:
    path = shutil.which(binary)
    if not path:
        return None
    try:
        proc = subprocess.run(
            [binary, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    first_line = (proc.stdout or proc.stderr).splitlines()
    return first_line[0].strip() if first_line else binary


def _check_python() -> CheckResult:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= MIN_PYTHON:
        return CheckResult("doctor_python", "ok", version)
    return CheckResult("doctor_python", "fail", f"{version} (< 3.10)")


def _check_binary(key: str, binary: str, hint_key: str) -> CheckResult:
    version = _tool_version(binary)
    if version is None:
        if shutil.which(binary):
            return CheckResult(key, "warn", "present (version unknown)")
        return CheckResult(key, "fail", "not found", hint_key)
    return CheckResult(key, "ok", version.split("(")[0].strip()[:60])


def _check_module(key: str, module_name: str) -> CheckResult:
    try:
        module = __import__(module_name)
    except ImportError:
        return CheckResult(key, "fail", "not installed")
    version: object = getattr(module, "__version__", None)
    if not version and module_name == "yt_dlp":
        try:
            from yt_dlp.version import __version__ as ytdlp_version

            version = ytdlp_version
        except ImportError:  # pragma: no cover
            version = None
    if not version:
        version = getattr(module, "version", "")
    if isinstance(version, tuple):
        version = ".".join(str(part) for part in version)
    return CheckResult(key, "ok", str(version))


def _check_config(cfg: AppConfig) -> CheckResult:
    return CheckResult("doctor_config", "ok", f"valid ({cfg.audio.codec})")


def _check_database(db: Database | None) -> CheckResult:
    if db is None:
        return CheckResult("doctor_database", "warn", "not opened")
    if not db.integrity_check():
        return CheckResult("doctor_database", "fail", "integrity check failed",
                           "doctor_hint_database")
    track_count = db.count_tracks()
    missing = db.missing_files()
    if missing:
        return CheckResult(
            "doctor_database",
            "warn",
            f"tracks: {track_count}, missing files: {len(missing)}",
            "doctor_hint_database",
        )
    return CheckResult("doctor_database", "ok", f"tracks: {track_count}")


def _check_network(offline: bool) -> CheckResult:
    if offline:
        return CheckResult("doctor_network", "warn", "skipped (offline mode)")
    reachable = 0
    for url in ("https://lrclib.net", "https://itunes.apple.com"):
        try:
            http.get_json(f"{url}/", timeout=3.0)
        except Exception:
            continue
        reachable += 1
    if reachable == 2:
        return CheckResult("doctor_network", "ok", "lrclib + itunes reachable")
    if reachable == 1:
        return CheckResult("doctor_network", "warn", "partially reachable")
    return CheckResult("doctor_network", "warn", "unreachable (offline?)")


def run_checks(
    cfg: AppConfig,
    db: Database | None = None,
    *,
    offline: bool = False,
) -> list[CheckResult]:
    """Run all diagnostics and return results in display order."""
    results = [
        _check_python(),
        _check_binary("doctor_ffmpeg", "ffmpeg", "doctor_hint_ffmpeg"),
        _check_binary("doctor_ffprobe", "ffprobe", "doctor_hint_ffmpeg"),
        _check_module("doctor_ytdlp", "yt_dlp"),
        _check_module("doctor_mutagen", "mutagen"),
        _check_module("doctor_pillow", "PIL"),
        _check_config(cfg),
        _check_database(db),
        _check_network(offline),
    ]
    logger.info(
        "doctor: %d checks, %d issues (melodine %s)",
        len(results),
        sum(1 for r in results if r.status != "ok"),
        __version__,
    )
    return results


def has_failures(results: list[CheckResult]) -> bool:
    return any(result.status == "fail" for result in results)
