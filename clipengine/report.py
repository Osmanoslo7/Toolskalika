"""Processing time, resource usage, storage and QA summary."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .config import workspace


def dir_size(p: Path) -> int:
    if not p.exists():
        return 0
    # Count each inode once, so hard-linked exports are not double counted.
    seen, total = set(), 0
    for f in p.rglob("*"):
        if f.is_file():
            st = f.stat()
            if (st.st_dev, st.st_ino) not in seen:
                seen.add((st.st_dev, st.st_ino))
                total += st.st_size
    return total


def collect(cfg: dict, db) -> dict:
    ws = workspace(cfg)
    media = db.list_media()
    stages = defaultdict(lambda: {"runs": 0, "wall_s": 0.0, "cpu_s": 0.0, "peak_rss_mb": 0.0})
    for r in db.stage_runs():
        key = r["stage"].split(":")[0] + (":" + r["stage"].split(":")[1] if ":" in r["stage"] else "")
        s = stages[key]
        s["runs"] += 1
        s["wall_s"] += r["wall_s"]
        s["cpu_s"] += r["cpu_s"]
        s["peak_rss_mb"] = max(s["peak_rss_mb"], r["peak_rss_mb"] or 0)
    renders = db.renders()
    qa = defaultdict(int)
    for r in renders:
        qa[r["qa_status"]] += 1
    rendered_s = sum((r["duration_s"] or 0) for r in renders)
    render_wall = sum((r["render_s"] or 0) for r in renders)
    source_s = sum(m["duration_s"] or 0 for m in media)
    analyze_wall = stages.get("analyze", {}).get("wall_s", 0)
    storage = {name: dir_size(ws / name) for name in ("thumbs", "analysis", "renders", "exports")}
    storage["library.db"] = sum(f.stat().st_size for f in ws.glob("library.db*"))
    return {
        "recordings": len(media),
        "source_minutes": round(source_s / 60, 2),
        "source_bytes": sum(m["size_bytes"] for m in media),
        "candidates": sum(m["n_candidates"] for m in media),
        "renders": len(renders),
        "qa": dict(qa),
        "stages": {k: {kk: round(vv, 2) if isinstance(vv, float) else vv for kk, vv in v.items()}
                   for k, v in stages.items()},
        "analysis_speed_x_realtime": round(source_s / analyze_wall, 1) if analyze_wall else None,
        "render_speed_x_realtime": round(rendered_s / render_wall, 2) if render_wall else None,
        "storage_bytes": storage,
    }


def build_report(cfg: dict, db, as_json: bool = False) -> str:
    d = collect(cfg, db)
    if as_json:
        return json.dumps(d, indent=2)
    mb = lambda b: f"{b / 1e6:,.1f} MB"  # noqa: E731
    lines = [
        f"Recordings: {d['recordings']} ({d['source_minutes']} min, {mb(d['source_bytes'])} — referenced, not copied)",
        f"Candidates: {d['candidates']}   Renders: {d['renders']}   QA: {d['qa']}",
        f"Analysis speed: {d['analysis_speed_x_realtime']}x realtime   "
        f"Render speed: {d['render_speed_x_realtime']}x realtime (per preset)",
        "", f"{'stage':20} {'runs':>5} {'wall s':>9} {'cpu s':>9} {'peak RSS':>10}",
    ]
    for k, s in sorted(d["stages"].items()):
        lines.append(f"{k:20} {s['runs']:>5} {s['wall_s']:>9.1f} {s['cpu_s']:>9.1f} {s['peak_rss_mb']:>8.0f}MB")
    lines += ["", "Workspace storage:"]
    lines += [f"  {k:12} {mb(v):>12}" for k, v in d["storage_bytes"].items()]
    lines.append(f"  {'total':12} {mb(sum(d['storage_bytes'].values())):>12}")
    return "\n".join(lines)
