"""Fuse detector scores into candidate clips with confidence and human-readable reasons."""
from __future__ import annotations

import numpy as np

from .signals import moving_average

LABELS = {
    "audio_peak": "Loud moment",
    "loudness_change": "Sudden audio spike",
    "frame_diff": "High-motion sequence",
    "visual_activity": "Visual effects burst",
    "scene_change": "Scene transition",
}
CONTENT_DETECTORS = ("audio_peak", "loudness_change", "frame_diff", "visual_activity")


def mmss(t: float) -> str:
    return f"{int(t // 60):02d}:{t % 60:04.1f}"


def fuse(scores: dict[str, np.ndarray], cfg: dict, hop_s: float) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Weighted, smoothed sum of detector scores, with a penalty for near-static stretches."""
    sc = cfg["scoring"]
    n = int(sc["smooth_s"] / hop_s)
    smoothed = {k: moving_average(v, n) for k, v in scores.items()}
    weights = {k: w for k, w in sc["weights"].items() if k in smoothed and w > 0}
    total = sum(weights.values())
    fused = sum(w * smoothed[k] for k, w in weights.items()) / total
    if "frame_diff" in smoothed:
        # Menus, loading and pause screens: practically no motion for >= 3 s.
        win = max(1, int(3 / hop_s))
        motion = np.lib.stride_tricks.sliding_window_view(
            np.pad(scores["frame_diff"], (win // 2, win - 1 - win // 2), mode="edge"), win).max(axis=1)
        fused = np.where(motion < 0.05, fused * sc["static_penalty"], fused)
    return fused.astype(np.float32), smoothed


def _snap(t: float, cuts: list[float], window: float) -> float | None:
    near = [c for c in cuts if abs(c - t) <= window]
    return min(near, key=lambda c: abs(c - t)) if near else None


def _window(peak_i: int, fused: np.ndarray, hop_s: float, duration: float, sc: dict,
            cuts: list[float], taken: list[tuple[float, float]]) -> tuple[float, float, list[str]] | None:
    notes = []
    peak_t = peak_i * hop_s
    start, end = peak_t - sc["pre_roll_s"], peak_t + sc["post_roll_s"]
    # Grow while the action stays near its peak level.
    keep = 0.6 * fused[peak_i]
    i = int(start / hop_s)
    while i > 0 and fused[i - 1] >= keep and end - (i - 1) * hop_s <= sc["max_duration_s"]:
        i -= 1
    start = min(start, i * hop_s)
    j = int(end / hop_s)
    while j + 1 < len(fused) and fused[j + 1] >= keep and (j + 1) * hop_s - start <= sc["max_duration_s"]:
        j += 1
    end = max(end, j * hop_s)
    # Minimum duration, expanding around the peak.
    if end - start < sc["min_duration_s"]:
        pad = (sc["min_duration_s"] - (end - start)) / 2
        start, end = start - pad, end + pad
    start, end = max(0.0, start), min(duration, end)
    if end - start < sc["min_duration_s"]:  # hit an edge: extend on the other side
        if start == 0:
            end = min(duration, start + sc["min_duration_s"])
        else:
            start = max(0.0, end - sc["min_duration_s"])
    # Snap to scene cuts so clips don't open or close mid-transition.
    s_cut = _snap(start, cuts, sc["snap_window_s"])
    if s_cut is not None and s_cut < peak_t and end - s_cut >= sc["min_duration_s"]:
        start = s_cut
        notes.append(f"start aligned to scene cut at {mmss(s_cut)}")
    e_cut = _snap(end, cuts, sc["snap_window_s"])
    if e_cut is not None and e_cut > peak_t and e_cut - start >= sc["min_duration_s"]:
        end = e_cut
        notes.append(f"end aligned to scene cut at {mmss(e_cut)}")
    # Trim against already chosen clips; drop if too little remains.
    for a, b in taken:
        if start < b and end > a:
            if a <= peak_t <= b:
                return None
            if peak_t < a:
                end = min(end, a)
            else:
                start = max(start, b)
    if end - start < sc["min_duration_s"] * 0.8:
        return None
    return round(start, 2), round(end, 2), notes


def _reasons(i: int, smoothed: dict, scores: dict, raw: dict, weights: dict, cuts: list[float],
             start: float, end: float) -> list[dict]:
    lo, hi = max(0, i - 2), i + 3
    out = []
    for k, w in weights.items():
        if w <= 0 or k not in smoothed:
            continue
        v = float(smoothed[k][lo:hi].max())
        if k == "audio_peak":
            text = f"audio {float(raw['audio_excess_db'][lo:hi].max()):+.1f} dB above the running baseline"
        elif k == "loudness_change":
            text = f"loudness jumped {float(raw['loudness_jump_db'][lo:hi].max()):+.1f} dB within 1 s"
        elif k == "frame_diff":
            pct = float((raw["diff"] < raw["diff"][lo:hi].max()).mean() * 100)
            text = f"on-screen motion higher than {pct:.0f}% of this recording"
        elif k == "visual_activity":
            text = f"{float(raw['changed'][lo:hi].max()) * 100:.0f}% of the frame changing (effects, flashes)"
        else:
            inside = [c for c in cuts if start <= c <= end]
            if not inside:
                continue
            text = f"{len(inside)} scene cut(s) inside the clip"
        out.append({"detector": k, "score": round(v, 3), "weight": w,
                    "contribution": round(v * w, 3), "text": text})
    out.sort(key=lambda r: r["contribution"], reverse=True)
    return out


def _describe(reasons: list[dict], agree_thr: float) -> str:
    strong = [r["detector"] for r in reasons if r["score"] >= agree_thr and r["detector"] in CONTENT_DETECTORS]
    audio = any(d in strong for d in ("audio_peak", "loudness_change"))
    visual = any(d in strong for d in ("frame_diff", "visual_activity"))
    if audio and visual:
        return "Action burst: loud audio with intense on-screen action"
    top = strong[0] if strong else (reasons[0]["detector"] if reasons else "frame_diff")
    return LABELS.get(top, "Highlight")


def select_candidates(scores: dict[str, np.ndarray], raw: dict, cuts: list[float], duration: float,
                      cfg: dict) -> tuple[list[dict], np.ndarray]:
    """Return (candidates sorted by confidence, fused timeline)."""
    sc = cfg["scoring"]
    hop_s = cfg["analysis"]["hop_s"]
    fused, smoothed = fuse(scores, cfg, hop_s)
    weights = sc["weights"]
    order = np.argsort(-fused, kind="stable")
    chosen: list[dict] = []
    taken: list[tuple[float, float]] = []

    thresholds = [sc["min_score"]]
    t = sc["min_score"]
    while t - 0.05 >= sc["min_score_floor"] - 1e-9:
        t = round(t - 0.05, 3)
        thresholds.append(t)

    for thr in thresholds:
        for i in order:
            if len(chosen) >= sc["max_candidates"] or fused[i] < thr:
                break
            peak_t = float(i * hop_s)
            if any(abs(peak_t - c["peak_s"]) < sc["min_gap_s"] for c in chosen):
                continue
            win = _window(int(i), fused, hop_s, duration, sc, cuts, taken)
            if win is None:
                continue
            start, end, notes = win
            reasons = _reasons(int(i), smoothed, scores, raw, weights, cuts, start, end)
            agreeing = [r for r in reasons if r["detector"] in CONTENT_DETECTORS and r["score"] >= sc["agree_threshold"]]
            n_agree = len(agreeing)
            conf = float(fused[i]) * (0.6 + 0.4 * min(n_agree, sc["min_agreeing"]) / sc["min_agreeing"])
            if n_agree < sc["min_agreeing"]:
                notes.append(f"only {n_agree} detector(s) agree (want {sc['min_agreeing']}): confidence reduced")
            else:
                notes.append(f"{n_agree} detectors agree")
            if thr < sc["min_score"]:
                conf *= 0.8
                notes.append(f"below the normal threshold {sc['min_score']}; included to reach "
                             f"{sc['min_candidates']} candidates")
            chosen.append({
                "start_s": start, "end_s": end, "duration_s": round(end - start, 2),
                "peak_s": round(peak_t, 2), "confidence": round(min(conf, 1.0), 3),
                "description": _describe(reasons, sc["agree_threshold"]),
                "reasons": {"peak_score": round(float(fused[i]), 3),
                            "signals": [r for r in reasons if r["score"] >= 0.15][:4],
                            "notes": notes},
            })
            taken.append((start, end))
        if len(chosen) >= sc["min_candidates"]:
            break
    chosen.sort(key=lambda c: c["confidence"], reverse=True)
    return chosen, fused
