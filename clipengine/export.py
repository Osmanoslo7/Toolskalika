"""Export approved, QA-checked clips to a folder for publishing. Nothing is uploaded."""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from .config import workspace


def _place(src: str, dest: Path) -> str:
    """Hard-link when possible (no extra disk space), otherwise copy."""
    try:
        os.link(src, dest)
        return "hardlink"
    except OSError:
        shutil.copy2(src, dest)
        return "copy"


def _ts(t: float) -> str:
    return f"{int(t // 60)}m{int(t % 60):02d}s"


def export_approved(cfg: dict, db, dest: str | Path | None = None) -> dict:
    out = Path(dest) if dest else workspace(cfg) / "exports" / time.strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"created_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "exported": [], "skipped": []}
    for cand in db.candidates(status="approved"):
        media = db.get_media(cand["media_id"])
        renders = db.renders(cand["id"])
        if not renders:
            manifest["skipped"].append({"candidate_id": cand["id"], "reason": "not rendered"})
            continue
        for r in renders:
            if r["qa_status"] not in ("passed", "warning"):
                manifest["skipped"].append({"candidate_id": cand["id"], "preset": r["preset"],
                                            "reason": f"QA {r['qa_status']}"})
                continue
            name = f"{Path(media['path']).stem}_{_ts(cand['start_s'])}_{r['preset']}"
            method = _place(r["path"], out / f"{name}.mp4")
            if r.get("thumb_path"):
                _place(r["thumb_path"], out / f"{name}.jpg")
            manifest["exported"].append({
                "file": f"{name}.mp4", "thumbnail": f"{name}.jpg" if r.get("thumb_path") else None,
                "candidate_id": cand["id"], "preset": r["preset"], "width": r["width"], "height": r["height"],
                "duration_s": r["duration_s"], "qa_status": r["qa_status"], "method": method,
                "source": media["path"], "source_start_s": cand["start_s"], "source_end_s": cand["end_s"],
                "confidence": cand["confidence"], "description": cand["description"],
                # Draft metadata for a later, human-triggered YouTube step. Not uploaded.
                "draft_metadata": {"title": f"{cand['description']} ({Path(media['path']).stem})",
                                   "shorts": r["height"] > r["width"]},
            })
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    manifest["path"] = str(out)
    return manifest
