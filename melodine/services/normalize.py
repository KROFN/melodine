"""EBU R128 loudness normalization via two-pass ffmpeg loudnorm."""

from __future__ import annotations

import contextlib
import json
import re
import shutil
import subprocess
from pathlib import Path

from melodine.core.logging import get_logger
from melodine.models import CodecProfile

logger = get_logger("normalize")


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _run(args: list[str], timeout: float = 120.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def measure_loudness(
    path: str | Path,
    *,
    target_lufs: float = -14.0,
    true_peak: float = -1.5,
    lra: int = 11,
) -> dict[str, str] | None:
    """First pass: measure integrated loudness statistics."""
    if not ffmpeg_available():
        return None
    args = [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-i",
        str(path),
        "-af",
        f"loudnorm=I={target_lufs}:TP={true_peak}:LRA={lra}:print_format=json",
        "-f",
        "null",
        "-",
    ]
    try:
        proc = _run(args)
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("loudness measurement failed: %s", exc)
        return None
    match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", proc.stderr, re.DOTALL)
    if not match:
        logger.warning("could not parse loudnorm measurement output")
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def normalize_file(
    path: str | Path,
    profile: CodecProfile,
    *,
    bitrate: int = 0,
    target_lufs: float = -14.0,
    true_peak: float = -1.5,
    lra: int = 11,
) -> bool:
    """Two-pass linear loudnorm; re-encodes with the track's codec.

    Returns True when the file was normalized in place.  Any failure is
    logged and returns False so downloads never break because of it.
    """
    path = Path(path)
    if not ffmpeg_available():
        logger.warning("ffmpeg not found - skipping normalization")
        return False

    stats = measure_loudness(
        path, target_lufs=target_lufs, true_peak=true_peak, lra=lra
    )
    if not stats:
        return False

    # Already at target? Skip re-encode when within 0.5 LU.
    try:
        if abs(float(stats.get("input_i", "-100")) - target_lufs) < 0.5:
            logger.info("%s already at target loudness - skipping", path.name)
            return False
    except ValueError:
        pass

    filter_args = (
        f"loudnorm=I={target_lufs}:TP={true_peak}:LRA={lra}"
        f":measured_I={stats.get('input_i')}"
        f":measured_TP={stats.get('input_tp')}"
        f":measured_LRA={stats.get('input_lra')}"
        f":measured_thresh={stats.get('input_thresh')}"
        f":offset={stats.get('target_offset')}"
        f":linear=true:print_format=summary"
    )

    encode_args: list[str] = ["-c:a", profile.ffmpeg_encoder]
    if bitrate > 0 and not profile.lossless:
        encode_args += ["-b:a", f"{bitrate}k"]

    temp_path = path.with_suffix(f".normalized{path.suffix}")
    args = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-nostats",
        "-i",
        str(path),
        "-af",
        filter_args,
        *encode_args,
        str(temp_path),
    ]
    try:
        proc = _run(args, timeout=300.0)
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("normalization failed for %s: %s", path.name, exc)
        _cleanup(temp_path)
        return False
    if proc.returncode != 0 or not temp_path.exists():
        logger.warning("ffmpeg normalization failed: %s", proc.stderr[-400:])
        _cleanup(temp_path)
        return False

    temp_path.replace(path)
    logger.info("normalized %s to %s LUFS", path.name, target_lufs)
    return True


def _cleanup(path: Path) -> None:
    with contextlib.suppress(OSError):
        path.unlink(missing_ok=True)
