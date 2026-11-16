"""Phase 5 — automatic quality checks on rendered clips.

One decode pass per clip runs blackdetect, freezedetect and volumedetect, and collects
decoder errors. Failed clips are flagged in the database, never deleted.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import ffmpeg

PASS, WARN, FAIL = "pass", "warn", "fail"


def _check(name: str, level: str, message: str) -> dict:
    return {"name": name, "level": level, "message": message}


def _intervals(log: str, kind: str, total: float) -> list[tuple[float, float]]:
    if kind == "black":
        return [(float(a), float(b)) for a, b in
                re.findall(r"black_start:\s*([\d.]+)\s+black_end:\s*([\d.]+)", log)]
    starts = [float(x) for x in re.findall(r"freeze_start:\s*([\d.]+)", log)]
    ends = [float(x) for x in re.findall(r"freeze_end:\s*([\d.]+)", log)]
    ends += [total] * (len(starts) - len(ends))      # a freeze running to the end has no end line
    return list(zip(starts, ends))


def _outside(intervals, keep_out: list[tuple[float, float]]) -> float:
    """Total length of intervals after removing the given zones (fade-in/out)."""
    total = 0.0
    for a, b in intervals:
        length = b - a
        for za, zb in keep_out:
            length -= max(0.0, min(b, zb) - max(a, za))
        total += max(0.0, length)
    return total


def analyse_file(path: str | Path, *, width: int, height: int, duration: float, fade_in: float,
                 fade_out: float, source_has_audio: bool, qcfg: dict) -> dict:
    checks: list[dict] = []
    p = Path(path)

    # 1. integrity
    if not p.is_file() or p.stat().st_size == 0:
        checks.append(_check("integrity", FAIL, "output file missing or empty"))
        return _summary(checks)
    try:
        meta = ffmpeg.probe(p)
    except ffmpeg.FFmpegError as exc:
        checks.append(_check("integrity", FAIL, f"ffprobe cannot read the file: {str(exc)[-200:]}"))
        return _summary(checks)
    checks.append(_check("integrity", PASS, f"{meta['container']}, {p.stat().st_size / 1e6:.1f} MB"))

    # 2. resolution / aspect ratio
    if (meta["width"], meta["height"]) != (width, height) or meta["sar"] != "1:1":
        checks.append(_check("aspect_ratio", FAIL, f"got {meta['width']}x{meta['height']} SAR {meta['sar']}, "
                                                   f"expected {width}x{height} SAR 1:1"))
    else:
        checks.append(_check("aspect_ratio", PASS, f"{width}x{height}"))

    # 3. duration
    diff = abs(meta["duration_s"] - duration)
    lvl = PASS if diff <= qcfg["duration_tolerance_s"] else FAIL
    checks.append(_check("duration", lvl, f"{meta['duration_s']:.2f}s (expected {duration:.2f}s)"))

    # 4. one decode pass: errors, black, frozen, audio level
    proc = ffmpeg.run(["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "level+info", "-i", str(p),
                       "-vf", "blackdetect=d=0.1:pic_th=0.98:pix_th=0.10,freezedetect=n=0.003:d=0.5",
                       "-af", "volumedetect", "-f", "null", "-"], check=False)
    log = proc.stderr
    errors = [ln for ln in log.splitlines() if ln.startswith(("[error]", "[fatal]")) or "] [error]" in ln
              or "] [fatal]" in ln]
    if proc.returncode != 0 or errors:
        checks.append(_check("decodable", FAIL, f"{len(errors)} decode error(s): "
                                                f"{(errors[0] if errors else 'exit code ' + str(proc.returncode))[:160]}"))
    else:
        checks.append(_check("decodable", PASS, "full decode without errors"))

    total = meta["duration_s"]
    fades = [(0.0, fade_in + 0.15), (total - fade_out - 0.15, total)]
    black = _outside(_intervals(log, "black", total), fades)
    checks.append(_check("black_frames", FAIL if black > qcfg["max_black_s"] else PASS,
                         f"{black:.2f}s of black outside fades"))

    frozen = _intervals(log, "freeze", total)
    frozen_total = sum(b - a for a, b in frozen)
    longest = max((b - a for a, b in frozen), default=0.0)
    if total and frozen_total / total > qcfg["max_frozen_ratio"]:
        lvl = FAIL
    elif longest > qcfg["frozen_warn_s"]:
        lvl = WARN
    else:
        lvl = PASS
    checks.append(_check("frozen_frames", lvl, f"{frozen_total:.1f}s frozen in total, longest {longest:.1f}s"))

    # 5. audio
    if not meta["has_audio"]:
        checks.append(_check("audio", FAIL, "no audio stream"))
    else:
        m = re.search(r"max_volume:\s*(-?[\d.]+|-inf) dB", log)
        max_vol = float(m.group(1)) if m and m.group(1) != "-inf" else -200.0
        if max_vol < qcfg["silent_max_volume_db"]:
            lvl = WARN if not source_has_audio else FAIL
            msg = "silent audio track" + (" (the source recording has no audio)" if not source_has_audio else "")
            checks.append(_check("audio", lvl, msg))
        else:
            checks.append(_check("audio", PASS, f"peak {max_vol:.1f} dB"))
    return _summary(checks, meta)


def _summary(checks: list[dict], meta: dict | None = None) -> dict:
    levels = {c["level"] for c in checks}
    status = "failed" if FAIL in levels else "warning" if WARN in levels else "passed"
    return {"status": status, "checks": checks,
            "probe": {k: meta[k] for k in ("width", "height", "duration_s", "fps", "video_codec", "audio_codec")}
            if meta else None}


def check_render(render: dict, cfg: dict, db) -> dict:
    cand = db.get_candidate(render["candidate_id"])
    media = db.get_media(cand["media_id"])
    preset = cfg["render"]["presets"][render["preset"]]
    rc = cfg["render"]
    dur = cand["duration_s"]
    result = analyse_file(render["path"], width=preset["width"], height=preset["height"], duration=dur,
                          fade_in=min(rc["fade_in_s"], dur / 3), fade_out=min(rc["fade_out_s"], dur / 3),
                          source_has_audio=bool(media["has_audio"]), qcfg=cfg["qa"])
    db.set_render_qa(render["id"], result["status"], result)
    return result
