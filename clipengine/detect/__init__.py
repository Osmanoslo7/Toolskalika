"""Phase 2 — analyse a recording and store candidate highlights."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from ..config import workspace
from ..metrics import stage
from . import detectors
from .scoring import select_candidates
from .signals import audio_rms_db, frame_features

FEATURE_VERSION = 1


def _feature_key(cfg: dict) -> str:
    a = cfg["analysis"]
    blob = json.dumps({k: a[k] for k in ("hop_s", "frame_fps", "frame_width", "audio_rate")}, sort_keys=True)
    return hashlib.sha1(f"{FEATURE_VERSION}:{blob}".encode()).hexdigest()[:12]


def extract_features(media: dict, cfg: dict, cache_dir: Path, force: bool = False) -> dict[str, np.ndarray]:
    """Raw features, cached per analysis settings so re-scoring never re-decodes."""
    a = cfg["analysis"]
    cache = cache_dir / f"features_{_feature_key(cfg)}.npz"
    if cache.exists() and not force:
        return dict(np.load(cache))
    hop = a["hop_s"]
    n_hops = max(1, int(np.ceil(media["duration_s"] / hop)))
    rms = (audio_rms_db(media["path"], n_hops, hop, a["audio_rate"]) if media["has_audio"]
           else np.full(n_hops, -90.0, dtype=np.float32))
    vis = frame_features(media["path"], n_hops, hop, a["frame_fps"], a["frame_width"],
                         media["width"], media["height"])
    feats = {"rms_db": rms, **vis}
    cache_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache, **feats)
    return feats


def compute_scores(feats: dict, cfg: dict) -> tuple[dict, dict, list[float]]:
    a = cfg["analysis"]
    hop = a["hop_s"]
    ap, excess = detectors.audio_peak(feats["rms_db"], hop, a["baseline_window_s"])
    lc, jump = detectors.loudness_change(feats["rms_db"], hop)
    sc, cuts = detectors.scene_cuts(feats["hist"], hop, a["scene_threshold"])
    scores = {
        "audio_peak": ap,
        "loudness_change": lc,
        "frame_diff": detectors.frame_diff(feats["diff"]),
        "visual_activity": detectors.visual_activity(feats["changed"], feats["flash"]),
        "scene_change": sc,
    }
    raw = {**feats, "audio_excess_db": excess, "loudness_jump_db": jump}
    return scores, raw, cuts


def analyze(media_id: int, cfg: dict, db, force: bool = False) -> list[dict]:
    media = db.get_media(media_id)
    if media is None:
        raise KeyError(f"no media #{media_id}")
    cache_dir = workspace(cfg) / "analysis" / str(media_id)
    with stage(db, "analyze", media_id) as detail:
        feats = extract_features(media, cfg, cache_dir, force)
        scores, raw, cuts = compute_scores(feats, cfg)
        cands, fused = select_candidates(scores, raw, cuts, media["duration_s"], cfg)
        ids = db.replace_candidates(media_id, cands)
        for c, cid in zip(cands, ids):
            c["id"] = cid
        hop = cfg["analysis"]["hop_s"]
        timeline = {"hop_s": hop, "fused": [round(float(x), 3) for x in fused],
                    "scene_cuts": cuts,
                    "signals": {k: [round(float(x), 3) for x in v] for k, v in scores.items()}}
        (cache_dir / "timeline.json").write_text(json.dumps(timeline))
        db.set_media_status(media_id, "analyzed")
        detail.update(candidates=len(cands), scene_cuts=len(cuts), duration_s=media["duration_s"])
    return cands
