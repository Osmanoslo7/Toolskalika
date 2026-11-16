"""Low-level signal extraction. Each function streams from ffmpeg; no full decode in memory.

Every detector returns one value per hop (default 0.5 s), so signals line up for fusion.
"""
from __future__ import annotations

import subprocess

import numpy as np


def _stream(args: list[str], block: int):
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        while True:
            buf = proc.stdout.read(block)
            if not buf:
                break
            yield buf
    finally:
        proc.stdout.close()
        proc.wait()


def audio_rms_db(src: str, n_hops: int, hop_s: float, rate: int) -> np.ndarray:
    """RMS level in dBFS per hop. Silence is floored at -90 dB."""
    hop = int(rate * hop_s)
    out = np.full(n_hops, -90.0, dtype=np.float32)
    args = ["ffmpeg", "-v", "error", "-i", src, "-vn", "-sn", "-ac", "1", "-ar", str(rate),
            "-f", "s16le", "-"]
    i, rest = 0, b""
    for buf in _stream(args, hop * 2 * 64):
        data = rest + buf
        usable = len(data) - len(data) % (hop * 2)
        rest = data[usable:]
        if not usable:
            continue
        x = np.frombuffer(data[:usable], dtype="<i2").astype(np.float32) / 32768.0
        rms = np.sqrt(np.mean(x.reshape(-1, hop) ** 2, axis=1))
        db = 20 * np.log10(np.maximum(rms, 10 ** (-90 / 20)))
        take = min(len(db), n_hops - i)
        out[i:i + take] = db[:take]
        i += take
        if i >= n_hops:
            break
    return out


def frame_features(src: str, n_hops: int, hop_s: float, fps: float, width: int,
                   src_w: int, src_h: int) -> dict[str, np.ndarray]:
    """Per-hop visual features from downscaled grayscale frames.

    diff      mean absolute pixel difference between consecutive frames (motion)
    changed   fraction of pixels changing by more than 20/255 (spatial extent of change)
    flash     absolute change in mean brightness (explosions, muzzle flashes, hits)
    hist      histogram distance between consecutive frames (0..1) — scene cut evidence
    """
    h = max(2, int(round(width * src_h / src_w / 2)) * 2)
    size = width * h
    per_hop = {k: [[] for _ in range(n_hops)] for k in ("diff", "changed", "flash", "hist")}
    args = ["ffmpeg", "-v", "error", "-i", src, "-an", "-sn",
            "-vf", f"fps={fps},scale={width}:{h}:flags=area,format=gray",
            "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    prev, prev_hist, idx, rest = None, None, 0, b""
    for buf in _stream(args, size * 16):
        data = rest + buf
        usable = len(data) - len(data) % size
        rest = data[usable:]
        for k in range(usable // size):
            f = np.frombuffer(data[k * size:(k + 1) * size], dtype=np.uint8).astype(np.int16)
            hist = np.bincount(f >> 3, minlength=32).astype(np.float32) / size
            hop_i = min(int((idx / fps) / hop_s), n_hops - 1)
            if prev is not None:
                d = np.abs(f - prev)
                per_hop["diff"][hop_i].append(float(d.mean()))
                per_hop["changed"][hop_i].append(float((d > 20).mean()))
                per_hop["flash"][hop_i].append(abs(float(f.mean() - prev.mean())))
                per_hop["hist"][hop_i].append(0.5 * float(np.abs(hist - prev_hist).sum()))
            prev, prev_hist = f, hist
            idx += 1
    agg = {"diff": np.mean, "changed": np.mean, "flash": np.max, "hist": np.max}
    return {k: np.array([agg[k](v) if v else 0.0 for v in per_hop[k]], dtype=np.float32)
            for k in per_hop}


# --- signal utilities --------------------------------------------------------------------

def moving_average(x: np.ndarray, n: int) -> np.ndarray:
    if n <= 1 or len(x) == 0:
        return x.astype(np.float32)
    k = np.ones(n, dtype=np.float32) / n
    pad = n // 2
    xp = np.pad(x, (pad, n - 1 - pad), mode="edge")
    return np.convolve(xp, k, mode="valid").astype(np.float32)


def rolling_median(x: np.ndarray, n: int) -> np.ndarray:
    if len(x) == 0:
        return x
    n = max(1, min(n, len(x)))
    pad = n // 2
    xp = np.pad(x, (pad, n - 1 - pad), mode="edge")
    win = np.lib.stride_tricks.sliding_window_view(xp, n)
    return np.median(win, axis=1).astype(np.float32)


def robust_norm(x: np.ndarray, lo_pct: float = 50, hi_pct: float = 98) -> np.ndarray:
    """Map the recording's median to 0 and its 98th percentile to 1 (clipped)."""
    if len(x) == 0:
        return x
    lo, hi = np.percentile(x, lo_pct), np.percentile(x, hi_pct)
    if hi - lo < 1e-6:
        return np.zeros_like(x, dtype=np.float32)
    return np.clip((x - lo) / (hi - lo), 0, 1).astype(np.float32)
