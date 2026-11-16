import json

import numpy as np
import pytest

from clipengine.config import workspace
from clipengine.detect import analyze, compute_scores, detectors
from clipengine.detect.scoring import select_candidates
from clipengine.detect.signals import moving_average, robust_norm, rolling_median
from clipengine.ingest import ingest_file

HOP = 0.5


def overlaps(c, a, b):
    return c["start_s"] < b and c["end_s"] > a


# --- unit tests on synthetic signals (no video needed) -------------------------------

def test_signal_utils():
    x = np.array([0, 0, 10, 0, 0], dtype=np.float32)
    assert moving_average(x, 1).tolist() == x.tolist()
    assert moving_average(x, 3)[2] == pytest.approx(10 / 3)
    assert rolling_median(np.array([1, 1, 9, 1, 1], dtype=np.float32), 3).tolist() == [1, 1, 1, 1, 1]
    assert robust_norm(np.ones(10, dtype=np.float32)).tolist() == [0] * 10
    r = robust_norm(np.arange(100, dtype=np.float32))
    assert r.min() == 0 and r.max() == 1


def test_audio_peak_and_loudness_change():
    db = np.full(200, -40.0, dtype=np.float32)
    db[100:106] = -10.0                      # +30 dB burst at 50 s
    peak, excess = detectors.audio_peak(db, HOP, 30)
    assert peak[:90].max() == 0
    assert peak[101:105].min() > 0.9 and excess.max() > 25
    change, jump = detectors.loudness_change(db, HOP)
    assert change.argmax() in range(100, 104)
    assert change[106:].max() == 0           # falling loudness is not a "change" event


def test_scene_cuts_ignore_sustained_churn():
    hist = np.full(120, 0.02, dtype=np.float32)
    hist[30] = 0.8                           # isolated hard cut
    hist[60:90] = 0.5                        # sustained fast motion: churn, not cuts
    _, cuts = detectors.scene_cuts(hist, HOP, 0.35)
    assert cuts[0] == 15.0
    assert all(not (30 < c < 45) for c in cuts[1:-1])


def test_scoring_needs_agreement_and_respects_limits(cfg):
    n = 240                                  # 120 s
    z = np.zeros(n, dtype=np.float32)
    scores = {k: z.copy() for k in ("audio_peak", "loudness_change", "frame_diff", "visual_activity", "scene_change")}
    for k in ("audio_peak", "frame_diff", "visual_activity", "loudness_change"):
        scores[k][60:70] = 1.0               # strong agreed event at 30-35 s
    scores["audio_peak"][180:184] = 1.0      # audio-only blip at 90 s
    scores["frame_diff"][:] = np.maximum(scores["frame_diff"], 0.2)   # avoid static penalty
    raw = {"audio_excess_db": scores["audio_peak"] * 20, "loudness_jump_db": scores["loudness_change"] * 12,
           "diff": scores["frame_diff"] * 10, "changed": scores["visual_activity"]}
    cands, fused = select_candidates(scores, raw, [], 120.0, cfg)
    assert len(fused) == n
    top = cands[0]
    assert overlaps(top, 30, 35)
    assert cfg["scoring"]["min_duration_s"] <= top["duration_s"] <= cfg["scoring"]["max_duration_s"]
    assert "agree" in " ".join(top["reasons"]["notes"])
    blip = [c for c in cands if overlaps(c, 89, 92)]
    if blip:                                  # a single-detector event must rank lower
        assert blip[0]["confidence"] < top["confidence"]
        assert any("only 1 detector" in n for n in blip[0]["reasons"]["notes"])
    for a in cands:                          # no overlapping clips
        for b in cands:
            if a is not b:
                assert not overlaps(a, b["start_s"], b["end_s"])


def test_scene_cut_alone_is_not_a_highlight(cfg):
    n = 240
    scores = {k: np.zeros(n, dtype=np.float32) for k in
              ("audio_peak", "loudness_change", "frame_diff", "visual_activity", "scene_change")}
    scores["frame_diff"][:] = 0.2
    scores["scene_change"][100] = 1.0
    raw = {"audio_excess_db": scores["audio_peak"], "loudness_jump_db": scores["audio_peak"],
           "diff": scores["frame_diff"], "changed": scores["visual_activity"]}
    cands, _ = select_candidates(scores, raw, [50.0], 120.0, cfg)
    assert cands == []


# --- end to end on planted-event footage ------------------------------------------------

def test_analyze_finds_planted_events(footage_dir, cfg, db):
    r = ingest_file(footage_dir / "match.mp4", cfg, db)
    cands = analyze(r.media_id, cfg, db)
    assert len(cands) >= 2
    found_1 = [c for c in cands if overlaps(c, 10, 14)]
    found_2 = [c for c in cands if overlaps(c, 20, 23)]
    assert found_1 and found_2, cands
    # every candidate carries the required fields
    for c in db.candidates(r.media_id):
        assert c["end_s"] > c["start_s"] and c["duration_s"] == pytest.approx(c["end_s"] - c["start_s"], abs=0.01)
        assert 0 < c["confidence"] <= 1
        assert c["reasons"]["signals"] and c["description"]
        assert c["media_id"] == r.media_id
    # the strongest event (bigger, both audio and visual) ranks first
    assert overlaps(cands[0], 10, 14)
    tl = json.loads((workspace(cfg) / "analysis" / str(r.media_id) / "timeline.json").read_text())
    for expected in (10.0, 14.0, 20.0, 23.0):
        assert any(abs(c - expected) <= 0.5 for c in tl["scene_cuts"]), tl["scene_cuts"]
    assert db.get_media(r.media_id)["status"] == "analyzed"


def test_rescoring_uses_cache(footage_dir, cfg, db):
    r = ingest_file(footage_dir / "match.mp4", cfg, db)
    analyze(r.media_id, cfg, db)
    first = db.stage_runs(r.media_id)[-1]["wall_s"]
    cfg["scoring"]["weights"]["audio_peak"] = 0.0
    analyze(r.media_id, cfg, db)
    assert db.stage_runs(r.media_id)[-1]["wall_s"] < first


def test_analyze_without_audio(footage_dir, cfg, db):
    r = ingest_file(footage_dir / "silent.mov", cfg, db)
    cands = analyze(r.media_id, cfg, db)
    assert any(overlaps(c, 10, 14) for c in cands)
    for c in cands:
        assert all(s["detector"] not in ("audio_peak", "loudness_change") or s["score"] == 0
                   for s in c["reasons"]["signals"])
