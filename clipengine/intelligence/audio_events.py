"""Sound-event detection from signal features (numpy only, no trained model).

Detects events with clear acoustic signatures:

    impact          sharp broadband transient (hit, crash, landing)
    explosion       impact whose low-frequency energy sustains (boom)
    gunfire         burst of >= 3 short transients 60-400 ms apart
    sudden_silence  level collapses by >= 20 dB after sustained sound
    siren           strong tonal component sweeping up and down (police, alarms)
    engine_rise     rising low-frequency pitch with rising level (acceleration)
    music           periodic onsets at 60-180 BPM (beat), with tempo

Not detected, because they need a trained classifier: screaming, laughter, speech
content, specific victory jingles. Confidences are heuristic and should be validated on
labelled footage.
"""
from __future__ import annotations

import subprocess

import numpy as np

from ..detect.signals import rolling_median

FRAME = 1024
HOP = 512
EPS = 1e-10


def spectral_features(src: str, rate: int = 16000) -> dict[str, np.ndarray]:
    """Stream mono PCM from ffmpeg and compute per-frame (32 ms at 16 kHz) features."""
    args = ["ffmpeg", "-v", "error", "-i", src, "-vn", "-sn", "-ac", "1", "-ar", str(rate),
            "-f", "s16le", "-"]
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    freqs = np.fft.rfftfreq(FRAME, 1 / rate)
    win = np.hanning(FRAME).astype(np.float32)
    bands = {"low": (freqs >= 20) & (freqs < 250), "mid": (freqs >= 250) & (freqs < 2000),
             "high": (freqs >= 2000)}
    tonal = (freqs >= 300) & (freqs <= 2000)
    lowtonal = (freqs >= 60) & (freqs <= 600)
    out = {k: [] for k in ("level_db", "low_db", "mid_db", "high_db", "flux", "dom_hz", "dom_prom",
                           "dom_low_hz", "dom_low_prom")}
    buf = np.zeros(0, dtype=np.float32)
    prev_log = None
    try:
        while True:
            raw = proc.stdout.read(HOP * 2 * 256)
            if not raw:
                break
            buf = np.concatenate([buf, np.frombuffer(raw[: len(raw) // 2 * 2], dtype="<i2").astype(np.float32) / 32768])
            n = (len(buf) - FRAME) // HOP + 1
            if n <= 0:
                continue
            frames = np.lib.stride_tricks.sliding_window_view(buf, FRAME)[::HOP][:n] * win
            buf = buf[n * HOP:]
            mag = np.abs(np.fft.rfft(frames, axis=1)) / FRAME
            power = mag ** 2
            out["level_db"].append(10 * np.log10(power.sum(1) + EPS))
            for name, m in bands.items():
                out[f"{name}_db"].append(10 * np.log10(power[:, m].sum(1) + EPS))
            log = np.log(mag + 1e-6)
            if prev_log is None:
                prev_log = log[:1]
            diff = np.diff(np.vstack([prev_log, log]), axis=0)
            out["flux"].append(np.clip(diff, 0, None).sum(1))
            prev_log = log[-1:]
            for key, m in (("dom", tonal), ("dom_low", lowtonal)):
                sub = mag[:, m]
                idx = sub.argmax(1)
                peak = sub[np.arange(len(sub)), idx]
                out[f"{key}_hz"].append(freqs[m][idx])
                out[f"{key}_prom"].append(peak / (np.median(sub, axis=1) + 1e-9))
    finally:
        proc.stdout.close()
        proc.wait()
    feats = {k: (np.concatenate(v).astype(np.float32) if v else np.zeros(0, np.float32)) for k, v in out.items()}
    feats["hop_t"] = np.array([HOP / rate], dtype=np.float32)
    return feats


# --- helpers --------------------------------------------------------------------------------

def _runs(mask: np.ndarray, min_len: int, max_gap: int = 0) -> list[tuple[int, int]]:
    """[start, end) index runs where mask is true, bridging gaps up to max_gap frames."""
    runs, i, n = [], 0, len(mask)
    while i < n:
        if not mask[i]:
            i += 1
            continue
        j, gap = i, 0
        end = i
        while j < n:
            if mask[j]:
                end, gap = j, 0
            else:
                gap += 1
                if gap > max_gap:
                    break
            j += 1
        if end + 1 - i >= min_len:
            runs.append((i, end + 1))
        i = end + 1 + max(gap, 1)
    return runs


def onsets(flux: np.ndarray, hop_t: float) -> np.ndarray:
    if len(flux) < 5:
        return np.zeros(0, dtype=int)
    med = rolling_median(flux, int(1.0 / hop_t))
    mad = rolling_median(np.abs(flux - med), int(1.0 / hop_t))
    thr = med + 4 * mad + 1e-3 + 0.05 * flux.max()
    peak = (flux[1:-1] > thr[1:-1]) & (flux[1:-1] >= flux[:-2]) & (flux[1:-1] > flux[2:])
    idx = np.flatnonzero(peak) + 1
    keep, last = [], -10
    for i in idx:
        if i - last >= 2:
            keep.append(i)
            last = i
    return np.array(keep, dtype=int)


def _event(kind: str, t: float, dur: float, conf: float, **detail) -> dict:
    return {"type": kind, "t": round(float(t), 3), "duration": round(float(dur), 3),
            "confidence": round(float(np.clip(conf, 0, 1)), 3), **detail}


# --- detectors --------------------------------------------------------------------------------

def detect_events(f: dict[str, np.ndarray]) -> list[dict]:
    if len(f.get("level_db", [])) < 10:
        return []
    hop_t = float(f["hop_t"][0])
    level, low, mid, high = f["level_db"], f["low_db"], f["mid_db"], f["high_db"]
    n = len(level)
    sec = lambda s: max(1, int(round(s / hop_t)))  # noqa: E731
    events: list[dict] = []

    # Transients: level jump relative to the preceding 250 ms.
    on = onsets(f["flux"], hop_t)
    trans = []
    for i in on:
        before = level[max(0, i - sec(0.25)):max(1, i - 1)]
        if len(before) == 0:
            continue
        jump = float(level[i:i + 3].max() - np.median(before))
        hjump = float(high[i:i + 3].max() - np.median(high[max(0, i - sec(0.25)):max(1, i - 1)]))
        # Does the sound die away (hit, shot, boom) or carry on (a sound simply starting)?
        pk = i + int(np.argmax(level[i:i + 3]))            # measure decay from the peak, not the onset
        top = float(level[pk])
        after = level[pk:pk + sec(3)]
        decay10 = int(np.argmax(after < top - 10)) if (after < top - 10).any() else len(after)
        decay8 = int(np.argmax(after[:sec(0.5)] < top - 8)) if (after[:sec(0.5)] < top - 8).any() else sec(0.5)
        # Spectral balance after the initial crack: rumble = low band dominates.
        lpk = i + int(np.argmax(low[i:i + sec(0.15)]))
        low_top = float(low[lpk])
        low_after = low[lpk:lpk + sec(3)]
        low_rel = int(np.argmax(low_after < low_top - 10)) if (low_after < low_top - 10).any() else len(low_after)
        tail = slice(i + 3, i + sec(0.6))
        low_dom = len(low[tail]) > 0 and float(low[tail].mean()) >= float(mid[tail].mean()) + 3
        # A hit is loudest at its start; a sound that keeps growing (engine, music swell) is not.
        front_loaded = float(level[pk:pk + sec(1.0)].max()) <= top + 3
        trans.append({"i": int(i), "jump": jump, "hjump": hjump, "decay_s": decay8 * hop_t,
                      "front_loaded": front_loaded,
                      "release_s": decay10 * hop_t, "decays": decay10 < len(after) and decay10 * hop_t <= 2.5,
                      "low_release_s": low_rel * hop_t,
                      "low_dominant": low_dom})

    # Gunfire: bursts of short transients 60-400 ms apart.
    short = [t for t in trans if t["jump"] >= 8 and t["decay_s"] <= 0.2]
    used = set()
    k = 0
    while k < len(short):
        burst = [short[k]]
        while k + 1 < len(short) and 0.06 <= (short[k + 1]["i"] - burst[-1]["i"]) * hop_t <= 0.4:
            k += 1
            burst.append(short[k])
        if len(burst) >= 3:
            t0, t1 = burst[0]["i"] * hop_t, burst[-1]["i"] * hop_t
            events.append(_event("gunfire", t0, t1 - t0 + 0.1, 0.5 + 0.1 * min(len(burst), 5), shots=len(burst)))
            used.update(b["i"] for b in burst)
        k += 1

    # Explosions and impacts.
    last_t = -9.0
    for t in trans:
        if t["i"] in used or t["jump"] < 12 or t["hjump"] < 6:
            continue
        ts = t["i"] * hop_t
        if ts - last_t < 0.4:
            continue
        last_t = ts
        if not t["decays"] or not t["front_loaded"]:
            continue                       # a sustained or swelling sound starting, not a hit
        if t["low_release_s"] >= 0.4 and t["low_dominant"]:
            events.append(_event("explosion", ts, t["low_release_s"],
                                 0.45 + t["jump"] / 40 + min(t["low_release_s"], 1) / 4,
                                 jump_db=round(t["jump"], 1)))
        elif t["release_s"] <= 0.4:
            events.append(_event("impact", ts, max(t["release_s"], 0.1), 0.35 + t["jump"] / 40,
                                 jump_db=round(t["jump"], 1)))

    # Sudden silence: sustained sound, then a collapse of >= 20 dB that holds.
    smooth = np.convolve(level, np.ones(sec(0.25)) / sec(0.25), mode="same")
    i, last = sec(2), -sec(3)
    while i < n - sec(0.8):
        win = smooth[i - sec(2):i]
        pre = float(np.median(win))
        steady = float(np.percentile(win, 80) - np.percentile(win, 20)) <= 8
        just_before = float(level[i - sec(0.1):i].mean())        # raw level, not smoothed
        post = float(level[i + sec(0.15):i + sec(0.8)].max())     # >= 20 dB down within 0.15 s: a cut, not a fade
        lead_in = float(level[i - sec(0.5):i - sec(0.3)].mean())   # a fade is already falling here
        abrupt = just_before >= pre - 3 and abs(lead_in - just_before) <= 3 and just_before - post >= 20
        if pre > -45 and steady and abrupt and i - last > sec(3):
            events.append(_event("sudden_silence", i * hop_t, 0.8, 0.5 + (pre - post - 20) / 40,
                                 drop_db=round(pre - post, 1)))
            last = i
            i += sec(1)
        i += 1

    # Siren: a strong tone in 450-1900 Hz that sweeps repeatedly.
    tonal = (f["dom_prom"] >= 6) & (f["dom_hz"] >= 450) & (f["dom_hz"] <= 1900) & (level > -50)
    for a, b in _runs(tonal, sec(1.5), max_gap=sec(0.2)):
        hz = f["dom_hz"][a:b]
        span = float(np.percentile(hz, 90) - np.percentile(hz, 10))
        tt = np.arange(len(hz)) * hop_t
        trend = hz - np.polyval(np.polyfit(tt, hz, 1), tt)        # remove slow drift
        trend = np.convolve(trend, np.ones(sec(0.15)) / sec(0.15), mode="same")  # remove jitter
        crossings = int(np.sum(np.diff(np.sign(trend)) != 0))
        per_s = crossings / ((b - a) * hop_t)
        if span >= 150 and 0.5 <= per_s <= 8:
            events.append(_event("siren", a * hop_t, (b - a) * hop_t, 0.5 + min(span, 600) / 1200,
                                 sweep_hz=round(span)))

    # Engine rise: low tonal pitch and level both climbing over >= 1.5 s.
    eng = (f["dom_low_prom"] >= 4) & (level > -55)
    for a, b in _runs(eng, sec(1.5), max_gap=sec(0.15)):
        w = sec(1.5)
        j = a
        while j + w <= b:
            hz = f["dom_low_hz"][j:j + w]
            tt = np.arange(w) * hop_t
            slope = np.polyfit(tt, hz, 1)[0]
            r = np.corrcoef(tt, hz)[0, 1] if hz.std() > 0 else 0
            rise = float(level[j + w - sec(0.3):j + w].mean() - level[j:j + sec(0.3)].mean())
            if slope >= 40 and r >= 0.8 and rise >= 3:
                events.append(_event("engine_rise", j * hop_t, (b - j) * hop_t, 0.4 + min(r, 1) * 0.3 + min(rise, 12) / 40,
                                     slope_hz_s=round(float(slope))))
                break
            j += sec(0.5)

    # Music: periodic onset strength at 60-180 BPM in 6 s windows.
    flux = f["flux"] - f["flux"].mean()
    wlen, step = sec(6), sec(1)
    lo, hi = int(60 / 180 / hop_t), int(60 / 60 / hop_t) + 1
    segs = []
    for s in range(0, max(0, n - wlen) + 1, step):
        x = flux[s:s + wlen] - flux[s:s + wlen].mean()
        ac = np.correlate(x, x, mode="full")[wlen - 1:]
        if ac[0] <= 0 or hi + 1 >= len(ac):
            continue
        ac = ac / ac[0]
        # Beat periods rarely fall exactly on a frame boundary: take the best neighbouring lag.
        ac = np.maximum(ac, np.maximum(np.roll(ac, 1), np.roll(ac, -1)))
        band = ac[lo:hi]
        best = float(band.max())
        if best < 0.4:
            continue
        # Prefer the shortest period that is nearly as strong (avoids half-tempo errors).
        lag = lo + int(np.flatnonzero(band >= 0.85 * best)[0])
        # refine the period with a parabola through the peak
        a, b, c = ac[lag - 1], ac[lag], ac[lag + 1]
        off = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0.0
        segs.append((s, s + wlen, 60 / ((lag + float(np.clip(off, -0.5, 0.5))) * hop_t), best))
    merged: list[list] = []
    for s, e, bpm, st in segs:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = e
            merged[-1][2].append(bpm)
            merged[-1][3] = max(merged[-1][3], st)
        else:
            merged.append([s, e, [bpm], st])
    for s, e, bpms, st in merged:
        beat_idx = [i for i in on if s <= i < e]
        t0, t1 = (beat_idx[0] * hop_t, beat_idx[-1] * hop_t) if beat_idx else (0, 0)
        if len(beat_idx) < 8 or t1 - t0 < 4:
            continue                                          # too short to be music (e.g. a gun burst)
        events.append(_event("music", t0, t1 - t0 + 0.25, 0.3 + min(st, 1) * 0.6,
                             bpm=round(float(np.median(bpms))),
                             beats=[round(float(i * hop_t), 3) for i in beat_idx][:400]))

    # Beats inside music are transients too. Keep impacts/gunfire there only if they stand
    # out clearly from the beat (>= 6 dB louder than the typical onset in that segment).
    music = [(e["t"], e["t"] + e["duration"]) for e in events if e["type"] == "music"]
    if music:
        def in_music(e):
            return any(a <= e["t"] <= b for a, b in music)
        seg_jump = {}
        for a, b in music:
            jumps = [t["jump"] for t in trans if a <= t["i"] * hop_t <= b]
            seg_jump[(a, b)] = float(np.median(jumps)) if jumps else 0.0
        kept = []
        for e in events:
            if e["type"] in ("impact", "explosion", "gunfire") and in_music(e):
                seg = next((a, b) for a, b in music if a <= e["t"] <= b)
                jump = e.get("jump_db") or max((t["jump"] for t in trans
                                                if e["t"] <= t["i"] * hop_t <= e["t"] + e["duration"]), default=0)
                if jump < seg_jump[seg] + 6:
                    continue
            kept.append(e)
        events = kept

    events.sort(key=lambda e: e["t"])
    return events


# --- visual corroboration -------------------------------------------------------------------

def corroborate(events: list[dict], visual: dict[str, np.ndarray], hop_s: float) -> list[dict]:
    """Check transient audio events against on-screen evidence.

    A gunshot or explosion usually comes with a flash or a burst of motion; a microphone
    pop or an off-screen sound does not. Unconfirmed events keep a reduced confidence.
    """
    flash, motion = visual.get("flash"), visual.get("motion")
    for e in events:
        if e["type"] not in ("impact", "explosion", "gunfire") or flash is None or not len(flash):
            continue
        a = max(0, int(e["t"] / hop_s) - 1)
        b = min(len(flash), int((e["t"] + e["duration"]) / hop_s) + 2)
        v = float(max(flash[a:b].max(initial=0), motion[a:b].max(initial=0)))
        e["visual"] = round(v, 3)
        if v >= 0.5:
            e["confirmed"] = True
            e["confidence"] = round(min(1.0, e["confidence"] * 1.15), 3)
        else:
            e["confirmed"] = False
            e["confidence"] = round(e["confidence"] * 0.6, 3)
    return events


def describe(e: dict) -> str:
    from ..detect.scoring import mmss
    t = mmss(e["t"])
    base = {
        "impact": f"impact at {t} (+{e.get('jump_db', 0):.0f} dB)",
        "explosion": f"explosion at {t} (+{e.get('jump_db', 0):.0f} dB, {e['duration']:.1f}s rumble)",
        "gunfire": f"gunfire at {t} ({e.get('shots', 0)} shots)",
        "sudden_silence": f"sudden silence at {t} (−{e.get('drop_db', 0):.0f} dB)",
        "siren": f"siren from {t} for {e['duration']:.1f}s",
        "engine_rise": f"engine revving up at {t}",
        "music": f"music at {e.get('bpm', 0)} BPM from {t}",
    }.get(e["type"], f"{e['type']} at {t}")
    if e.get("confirmed") is True:
        base += ", confirmed on screen"
    elif e.get("confirmed") is False:
        base += ", audio only (could be off-screen or a mic pop)"
    return base
