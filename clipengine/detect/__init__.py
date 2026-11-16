"""Phase 2 — analyse a recording and store candidate highlights.

Beta 0.2 adds sound-event intelligence: explosions, gunfire, impacts, sirens, engine
revs, sudden silences and music, checked against on-screen evidence and interpreted
through a per-game profile.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from ..config import workspace
from ..intelligence import audio_events
from ..intelligence.profiles import apply_weights, categorize, load_profile
from ..metrics import stage
from . import detectors
from .scoring import mmss, select_candidates
from .signals import audio_rms_db, frame_features, robust_norm

FEATURE_VERSION = 1
AUDIO_EVENT_VERSION = 1


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


def extract_sound_events(media: dict, cfg: dict, cache_dir: Path, feats: dict, force: bool = False) -> list[dict]:
    """Detect sound events (cached) and corroborate them with the visual features."""
    if not media["has_audio"] or not cfg["analysis"].get("sound_events", True):
        return []
    cache = cache_dir / f"sound_events_v{AUDIO_EVENT_VERSION}.json"
    if cache.exists() and not force:
        events = json.loads(cache.read_text())
    else:
        spec = audio_events.spectral_features(media["path"], cfg["analysis"]["audio_rate"])
        events = audio_events.detect_events(spec)
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(events))
    visual = {"flash": robust_norm(feats["flash"]), "motion": robust_norm(feats["diff"])}
    return audio_events.corroborate([dict(e) for e in events], visual, cfg["analysis"]["hop_s"])


def sound_event_signal(events: list[dict], n_hops: int, hop: float, profile: dict) -> np.ndarray:
    sig = np.zeros(n_hops, dtype=np.float32)
    weights = profile["event_weights"]
    for e in events:
        w = float(weights.get(e["type"], 0.0)) * e["confidence"]
        if w <= 0:
            continue
        a = int(e["t"] / hop)
        b = int((e["t"] + min(e["duration"], 3.0) + 0.5) / hop) + 1   # include the reaction just after
        sig[a:min(b, n_hops)] = np.maximum(sig[a:min(b, n_hops)], min(w, 1.0))
    return sig


def compute_scores(feats: dict, cfg: dict, events: list[dict] | None = None,
                   profile: dict | None = None) -> tuple[dict, dict, list[float]]:
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
    if events is not None and profile is not None:
        scores["sound_events"] = sound_event_signal(events, len(ap), hop, profile)
    raw = {**feats, "audio_excess_db": excess, "loudness_jump_db": jump, "events": events or []}
    return scores, raw, cuts


def annotate(cands: list[dict], events: list[dict], scores: dict, profile: dict, hop: float) -> None:
    """Attach the sound events inside each clip, its game category and a draft title."""
    for c in cands:
        inside = [e for e in events if c["start_s"] <= e["t"] <= c["end_s"] and e["type"] != "music"
                  or e["type"] == "music" and e["t"] < c["end_s"] and e["t"] + e["duration"] > c["start_s"]]
        clip_events = []
        for e in inside:
            ce = {k: v for k, v in e.items() if k != "beats"}
            ce["t_clip"] = round(max(0.0, e["t"] - c["start_s"]), 3)
            ce["text"] = audio_events.describe(e)
            if e["type"] == "music":
                ce["beats_clip"] = [round(b - c["start_s"], 3) for b in e.get("beats", [])
                                    if c["start_s"] <= b <= c["end_s"]]
            clip_events.append(ce)
        i = int(c["peak_s"] / hop)
        motion = float(scores["frame_diff"][max(0, i - 2):i + 3].max()) if len(scores["frame_diff"]) else 0.0
        cat = categorize(inside, motion, profile)
        c["reasons"]["events"] = clip_events
        c["reasons"]["game"] = profile["name"]
        story = []
        for e in sorted(inside, key=lambda e: e["t"]):
            name = e["type"].replace("_", " ")
            if e["type"] != "music" and name not in story:
                story.append(name)
        summary = " → ".join(story)
        if cat:
            c["reasons"]["category"] = cat["name"]
            c["reasons"]["title"] = cat.get("title")
            if summary and summary.lower() != cat["name"].lower():
                c["description"] = f"{cat['name']}: {summary}"
            else:   # the category says it all; keep the signal-based description for context
                c["description"] = f"{c['description']} → {cat['name'].lower()}"
        elif summary:
            c["description"] = f"{c['description']}: {summary}" if c["description"] != "Sound event" \
                else summary[:1].upper() + summary[1:]


def analyze(media_id: int, cfg: dict, db, force: bool = False, game: str | None = None) -> list[dict]:
    media = db.get_media(media_id)
    if media is None:
        raise KeyError(f"no media #{media_id}")
    if game:
        db.set_media_game(media_id, game)
        media["game"] = game
    profile = load_profile(media.get("game") or cfg["analysis"].get("game"))
    pcfg = apply_weights(cfg, profile)
    cache_dir = workspace(cfg) / "analysis" / str(media_id)
    with stage(db, "analyze", media_id) as detail:
        feats = extract_features(media, pcfg, cache_dir, force)
        events = extract_sound_events(media, pcfg, cache_dir, feats, force)
        scores, raw, cuts = compute_scores(feats, pcfg, events, profile)
        cands, fused = select_candidates(scores, raw, cuts, media["duration_s"], pcfg)
        hop = pcfg["analysis"]["hop_s"]
        annotate(cands, events, scores, profile, hop)
        ids = db.replace_candidates(media_id, cands)
        for c, cid in zip(cands, ids):
            c["id"] = cid
        timeline = {"hop_s": hop, "fused": [round(float(x), 3) for x in fused],
                    "scene_cuts": cuts, "game": profile["key"],
                    "events": [{k: v for k, v in e.items() if k != "beats"} | {"text": audio_events.describe(e)}
                               for e in events],
                    "signals": {k: [round(float(x), 3) for x in v] for k, v in scores.items()}}
        (cache_dir / "timeline.json").write_text(json.dumps(timeline))
        db.set_media_status(media_id, "analyzed")
        counts: dict[str, int] = {}
        for e in events:
            counts[e["type"]] = counts.get(e["type"], 0) + 1
        detail.update(candidates=len(cands), scene_cuts=len(cuts), duration_s=media["duration_s"],
                      game=profile["key"], sound_events=counts)
    return cands


__all__ = ["analyze", "compute_scores", "extract_features", "mmss"]
