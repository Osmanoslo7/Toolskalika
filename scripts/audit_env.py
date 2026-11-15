#!/usr/bin/env python3
"""Environment audit for the Vice City Clip Engine.

Stdlib only, so it runs before any dependency is installed.
Usage:
    python3 scripts/audit_env.py                 # audit the machine
    python3 scripts/audit_env.py clip1.mp4 ...   # also probe sample videos
    python3 scripts/audit_env.py --json          # machine-readable output
"""
from __future__ import annotations

import importlib
import json
import os
import platform
import shutil
import subprocess
import sys

PY_MODULES = [
    "numpy", "cv2", "scenedetect", "faster_whisper", "whisper", "torch",
    "PIL", "yaml", "pydantic", "pytest", "scipy",
]
FFMPEG_ENCODERS = ["libx264", "aac", "h264_nvenc", "h264_qsv", "h264_vaapi", "h264_videotoolbox"]
FFMPEG_FILTERS = ["scdet", "blackdetect", "silencedetect", "freezedetect",
                  "loudnorm", "ebur128", "subtitles", "ass"]


def run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def module_version(name: str) -> str | None:
    try:
        mod = importlib.import_module(name)
    except Exception:
        return None
    return str(getattr(mod, "__version__", "installed"))


def memory_gb() -> float | None:
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemTotal"):
                    return round(int(line.split()[1]) / 1024 / 1024, 1)
    except OSError:
        pass
    if sys.platform == "darwin":
        out = run(["sysctl", "-n", "hw.memsize"]).strip()
        return round(int(out) / 1024**3, 1) if out.isdigit() else None
    return None


def gpu_info() -> dict:
    info = {"nvidia": None, "dri_render_nodes": []}
    if shutil.which("nvidia-smi"):
        info["nvidia"] = run(["nvidia-smi", "--query-gpu=name,memory.total",
                              "--format=csv,noheader"]).strip() or None
    if os.path.isdir("/dev/dri"):
        info["dri_render_nodes"] = sorted(os.listdir("/dev/dri"))
    return info


def ffmpeg_info() -> dict:
    if not shutil.which("ffmpeg"):
        return {"installed": False}
    version = run(["ffmpeg", "-version"]).splitlines()[:1]
    enc = run(["ffmpeg", "-hide_banner", "-encoders"])
    flt = run(["ffmpeg", "-hide_banner", "-filters"])
    flt_names = {ln.split()[1] for ln in flt.splitlines() if len(ln.split()) > 2}
    enc_names = {ln.split()[1] for ln in enc.splitlines() if len(ln.split()) > 1}
    return {
        "installed": True,
        "ffprobe": bool(shutil.which("ffprobe")),
        "version": version[0] if version else "",
        # "compiled in" != "usable": hardware encoders also need a device + driver.
        "encoders_compiled": {e: e in enc_names for e in FFMPEG_ENCODERS},
        "filters": {f: f in flt_names for f in FFMPEG_FILTERS},
    }


def probe_video(path: str) -> dict:
    out = run(["ffprobe", "-v", "error", "-print_format", "json",
               "-show_format", "-show_streams", path])
    if not out:
        return {"path": path, "error": "ffprobe failed or file unreadable"}
    data = json.loads(out)
    fmt = data.get("format", {})
    result = {"path": path, "container": fmt.get("format_name"),
              "duration_s": float(fmt.get("duration", 0) or 0),
              "size_mb": round(int(fmt.get("size", 0) or 0) / 1024**2, 1),
              "streams": []}
    for s in data.get("streams", []):
        entry = {"type": s.get("codec_type"), "codec": s.get("codec_name")}
        if s.get("codec_type") == "video":
            entry.update(width=s.get("width"), height=s.get("height"),
                         fps=s.get("avg_frame_rate"), pix_fmt=s.get("pix_fmt"))
        elif s.get("codec_type") == "audio":
            entry.update(sample_rate=s.get("sample_rate"), channels=s.get("channels"))
        result["streams"].append(entry)
    return result


def main(argv: list[str]) -> int:
    as_json = "--json" in argv
    videos = [a for a in argv if not a.startswith("--")]
    disk = shutil.disk_usage(".")
    report = {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "cpu": {"logical_cores": os.cpu_count(), "model": platform.processor() or None},
        "memory_gb": memory_gb(),
        "disk_free_gb": round(disk.free / 1024**3, 1),
        "gpu": gpu_info(),
        "ffmpeg": ffmpeg_info(),
        "python_modules": {m: module_version(m) for m in PY_MODULES},
        "videos": [probe_video(v) for v in videos],
    }
    if as_json:
        print(json.dumps(report, indent=2))
    else:
        for key, value in report.items():
            print(f"{key}: {json.dumps(value, indent=2) if isinstance(value, (dict, list)) else value}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
