"""Sound-effect library and licensing registry.

The built-in effects are synthesised locally with FFmpeg, so they are original works
with no licensing restrictions. Any sound added later (music, packs) must be
registered with its licence; renders record every sound they use, and export refuses
clips that contain a sound whose licence is unknown or unverified.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .. import ffmpeg
from ..config import workspace

# name -> (category, ffmpeg aevalsrc expression, duration s, extra filters)
BUILTIN = {
    "impact_low": ("cinematic impact",
                   "0.9*sin(2*PI*48*t)*exp(-7*t)+0.35*sin(2*PI*96*t)*exp(-12*t)", 0.9,
                   "lowpass=f=400"),
    "impact_soft": ("cinematic impact",
                    "0.7*sin(2*PI*70*t)*exp(-10*t)+0.25*(random(0)*2-1)*exp(-40*t)", 0.6,
                    "lowpass=f=1800"),
    "whoosh": ("whoosh",
               "(random(0)*2-1)*sin(PI*t/0.5)*0.6", 0.5,
               "bandpass=f=1200:width_type=o:w=2,afade=t=in:d=0.2"),
    "riser": ("riser",
              "0.4*sin(2*PI*(200*t+300*t*t))*(t/1.5)", 1.5,
              "afade=t=out:st=1.4:d=0.1"),
}

# "user-recording" = the user's own gameplay capture (publisher video policies apply; the
# user is responsible for it). Everything else must be original, CC0 or explicitly licensed.
SAFE_LICENSES = {"original", "cc0", "licensed", "youtube-audio-library", "user-recording"}


def library_dir(cfg: dict) -> Path:
    d = workspace(cfg) / "sfx"
    d.mkdir(parents=True, exist_ok=True)
    return d


def registry_path(cfg: dict) -> Path:
    return library_dir(cfg) / "registry.json"


def load_registry(cfg: dict) -> dict:
    p = registry_path(cfg)
    return json.loads(p.read_text()) if p.exists() else {}


def save_registry(cfg: dict, reg: dict) -> None:
    registry_path(cfg).write_text(json.dumps(reg, indent=2))


def register_sound(cfg: dict, name: str, path: str, license: str, source: str, notes: str = "") -> dict:
    """Add a user-supplied sound. license: original | cc0 | licensed | youtube-audio-library | unknown."""
    reg = load_registry(cfg)
    reg[name] = {"path": str(Path(path).resolve()), "license": license.lower(), "source": source,
                 "notes": notes, "verified": license.lower() in SAFE_LICENSES,
                 "added": time.strftime("%Y-%m-%d")}
    save_registry(cfg, reg)
    return reg[name]


def ensure_builtin(cfg: dict) -> dict:
    """Synthesise the built-in effects once and register them as original works."""
    reg = load_registry(cfg)
    changed = False
    for name, (category, expr, dur, extra) in BUILTIN.items():
        out = library_dir(cfg) / f"{name}.wav"
        if not out.exists():
            ffmpeg.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        f"aevalsrc='{expr}':s=48000:d={dur}", "-af", f"{extra},aformat=channel_layouts=stereo",
                        str(out)])
        if name not in reg:
            reg[name] = {"path": str(out), "license": "original", "category": category,
                         "source": "synthesised locally by clipengine (ffmpeg aevalsrc)",
                         "verified": True, "added": time.strftime("%Y-%m-%d")}
            changed = True
    if changed:
        save_registry(cfg, reg)
    return reg


def audio_sources_ok(sources: list[dict]) -> tuple[bool, list[str]]:
    """True if every sound used in a render has a verified licence."""
    problems = [f"{s['name']}: licence {s.get('license', 'unknown')}" for s in sources
                if s.get("license") not in SAFE_LICENSES]
    return not problems, problems
