"""Synthetic soundtracks with planted sound events at known times.

Sounds other than the planted "sudden silence" fade out naturally, so the only abrupt
cut-off is the one at 25 s.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 48000
EVENTS = {"impact": 3.0, "explosion": 6.0, "gunfire": 9.0, "siren": 12.0,
          "engine_rise": 17.0, "sudden_silence": 25.0, "music": 28.0}


def _t(dur):
    return np.arange(int(SR * dur)) / SR


def soundtrack(seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    total = 37.0
    x = rng.normal(0, 0.003, int(SR * total))                     # quiet noise floor

    def put(t0, sig):
        i = int(t0 * SR)
        x[i:i + len(sig)] += sig[: len(x) - i]

    t = _t(0.3)                                                    # impact: short broadband crack
    put(3.0, rng.normal(0, 0.6, len(t)) * np.exp(-t / 0.02))
    t = _t(1.6)                                                    # explosion: crack + long low rumble
    boom = 0.8 * np.sin(2 * np.pi * 50 * t) * np.exp(-t / 0.7)
    rumble = np.convolve(rng.normal(0, 1, len(t)), np.ones(60) / 60, mode="same") * 2.5 * np.exp(-t / 0.6)
    put(6.0, boom + rumble + rng.normal(0, 0.5, len(t)) * np.exp(-t / 0.03))
    t = _t(0.1)                                                    # gunfire: 5 shots, 120 ms apart
    for k in range(5):
        put(9.0 + 0.12 * k, rng.normal(0, 0.6, len(t)) * np.exp(-t / 0.012))
    t = _t(3.0)                                                    # siren: 1 kHz +- 400 Hz wail at 1 Hz
    phase = 2 * np.pi * np.cumsum(1000 + 400 * np.sin(2 * np.pi * 1.0 * t)) / SR
    put(12.0, 0.3 * np.sin(phase) * np.clip((3.0 - t) / 0.6, 0, 1))   # siren fades as it passes
    t = _t(2.5)                                                    # engine: sawtooth 100 -> 350 Hz, louder
    f = 100 + 100 * t
    saw = 2 * ((np.cumsum(f) / SR) % 1) - 1
    put(17.0, saw * (0.03 + 0.15 * t) * np.clip((2.5 - t) / 0.5, 0, 1))  # engine eases off
    put(21.0, rng.normal(0, 0.2, int(SR * 4.0)))                  # loud ambience 21-25 s, then silence
    t = _t(0.15)                                                   # music: kick every 0.5 s (120 BPM)
    kick = 0.7 * np.sin(2 * np.pi * 60 * t) * np.exp(-t / 0.05)
    hat = rng.normal(0, 0.08, len(t)) * np.exp(-t / 0.01)
    for k in range(16):
        put(28.0 + 0.5 * k, kick)
        put(28.25 + 0.5 * k, hat)
    return np.clip(x, -1, 1)


def write_wav(path: Path, x: np.ndarray) -> Path:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype("<i2").tobytes())
    return path


def make_event_video(path: Path, seed: int = 0) -> Path:
    """37 s video + planted soundtrack. On-screen evidence:

    6.0 s  explosion  -> white flash
    9.0 s  gunfire    -> muzzle flashes
    12-19.5 s chase   -> fast motion (siren + engine)
    3.0 s  impact     -> NO visual change (should be marked audio-only)
    """
    import subprocess
    wav = write_wav(path.with_suffix(".wav"), soundtrack(seed))
    flashes = "+".join([f"between(t,{a},{b})" for a, b in
                        [(6.0, 6.25), (8.95, 9.0), (9.07, 9.12), (9.19, 9.24), (9.31, 9.36), (9.43, 9.48)]])
    vf = (f"[0:v][1:v]overlay=enable='between(t,12,19.5)'[m];"
          f"[m]drawbox=x=0:y=0:w=iw:h=ih:color=white@0.9:t=fill:enable='{flashes}'[v]")
    subprocess.run(["ffmpeg", "-v", "error", "-y",
                    "-f", "lavfi", "-i", "gradients=s=640x360:r=30:speed=0.002:seed=4:d=37",
                    "-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=37",
                    "-i", str(wav), "-filter_complex", vf, "-map", "[v]", "-map", "2:a",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(path)],
                   check=True)
    wav.unlink()
    return path
