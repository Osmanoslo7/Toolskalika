"""Record processing time and resource usage per pipeline stage."""
from __future__ import annotations

import contextlib
import resource
import sys
import time


def _cpu() -> float:
    s = resource.getrusage(resource.RUSAGE_SELF)
    c = resource.getrusage(resource.RUSAGE_CHILDREN)  # ffmpeg subprocesses
    return s.ru_utime + s.ru_stime + c.ru_utime + c.ru_stime


def _peak_rss_mb() -> float:
    s = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    c = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    div = 1024 * 1024 if sys.platform == "darwin" else 1024  # bytes on macOS, KB on Linux
    return round(max(s, c) / div, 1)


@contextlib.contextmanager
def stage(db, name: str, media_id: int | None = None, detail: dict | None = None):
    """Time a stage and store wall time, CPU time (incl. ffmpeg children) and peak RSS."""
    detail = detail if detail is not None else {}
    t0, c0 = time.perf_counter(), _cpu()
    try:
        yield detail
    finally:
        wall = time.perf_counter() - t0
        cpu = _cpu() - c0
        detail.setdefault("cpu_util", round(cpu / wall, 2) if wall > 0 else 0)
        if db is not None:
            db.add_stage_run(stage=name, media_id=media_id or detail.get("media_id"), wall_s=round(wall, 3),
                             cpu_s=round(cpu, 3), peak_rss_mb=_peak_rss_mb(), detail_json=detail)
