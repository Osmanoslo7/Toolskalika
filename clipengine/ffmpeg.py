"""Thin wrappers around the ffmpeg / ffprobe command-line tools."""
from __future__ import annotations

import json
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path


class FFmpegError(RuntimeError):
    pass


def require_tools() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise FFmpegError(f"{tool} not found on PATH")


def run(args: list[str], *, capture_bytes: bool = False, check: bool = True,
        timeout: float | None = None) -> subprocess.CompletedProcess:
    """Run ffmpeg/ffprobe. Arguments are a list (never a shell string)."""
    proc = subprocess.run(args, capture_output=True, text=not capture_bytes, timeout=timeout)
    if check and proc.returncode != 0:
        err = proc.stderr if isinstance(proc.stderr, str) else proc.stderr.decode(errors="replace")
        raise FFmpegError(f"{args[0]} failed ({proc.returncode}): {err.strip()[-800:]}")
    return proc


def _fps(rate: str | None) -> float | None:
    try:
        f = Fraction(rate)
        return round(float(f), 3) if f else None
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def probe(path: str | Path) -> dict:
    """Return normalised metadata for a media file. Raises FFmpegError if unreadable."""
    out = run(["ffprobe", "-v", "error", "-print_format", "json",
               "-show_format", "-show_streams", str(path)]).stdout
    data = json.loads(out)
    fmt = data.get("format", {})
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    if video is None:
        raise FFmpegError(f"{path}: no video stream")
    duration = float(fmt.get("duration") or video.get("duration") or 0)
    sar = video.get("sample_aspect_ratio", "1:1")
    return {
        "container": fmt.get("format_name"),
        "duration_s": duration,
        "size_bytes": int(fmt.get("size") or Path(path).stat().st_size),
        "width": int(video["width"]),
        "height": int(video["height"]),
        "sar": sar if sar not in ("0:1", "N/A") else "1:1",
        "fps": _fps(video.get("avg_frame_rate")) or _fps(video.get("r_frame_rate")),
        "video_codec": video.get("codec_name"),
        "pix_fmt": video.get("pix_fmt"),
        "audio_codec": audio.get("codec_name") if audio else None,
        "audio_rate": int(audio["sample_rate"]) if audio and audio.get("sample_rate") else None,
        "has_audio": audio is not None,
    }
