"""Independent detectors. Each maps raw features to a 0..1 score per hop.

Detectors are pure functions of the raw features, so each can be tested on its own and
re-scored without decoding video again.
"""
from __future__ import annotations

import numpy as np

from .signals import moving_average, robust_norm, rolling_median


def audio_peak(rms_db: np.ndarray, hop_s: float, baseline_window_s: float) -> tuple[np.ndarray, np.ndarray]:
    """How far the audio rises above the recording's running baseline.

    Returns (score, excess_db). 0 at baseline, 1 at +15 dB or more.
    """
    base = rolling_median(rms_db, int(baseline_window_s / hop_s))
    excess = np.clip(moving_average(rms_db, 2) - base, 0, None)
    return np.clip(excess / 15.0, 0, 1).astype(np.float32), excess.astype(np.float32)


def loudness_change(rms_db: np.ndarray, hop_s: float) -> tuple[np.ndarray, np.ndarray]:
    """Sudden rises in loudness within ~1 s. 1 at a +12 dB jump. Returns (score, jump_db)."""
    smooth = moving_average(rms_db, 2)
    lag = max(1, int(round(1.0 / hop_s)))
    jump = np.zeros_like(smooth)
    jump[lag:] = smooth[lag:] - smooth[:-lag]
    jump = np.clip(jump, 0, None)
    return np.clip(jump / 12.0, 0, 1).astype(np.float32), jump.astype(np.float32)


def frame_diff(diff: np.ndarray) -> np.ndarray:
    """On-screen motion relative to this recording (median → 0, 98th percentile → 1)."""
    return robust_norm(diff)


def visual_activity(changed: np.ndarray, flash: np.ndarray) -> np.ndarray:
    """Spatial extent of change plus brightness flashes, relative to this recording."""
    return robust_norm(changed + 2.0 * flash / 255.0)


def scene_cuts(hist: np.ndarray, hop_s: float, threshold: float) -> tuple[np.ndarray, list[float]]:
    """Hard cuts: histogram distance above threshold AND well above the local level.

    The second condition stops sustained fast motion (whose histograms churn constantly)
    from being read as a series of cuts. Returns (score per hop, cut times in seconds).
    """
    local = rolling_median(hist, int(4 / hop_s))
    is_cut = (hist > threshold) & (hist > 2.5 * local + 0.05)
    score = np.where(is_cut, 1.0, 0.0).astype(np.float32)
    cuts = [round(float(i * hop_s), 3) for i in np.flatnonzero(is_cut)]
    return score, cuts
