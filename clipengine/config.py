"""Load the YAML configuration: defaults deep-merged with an optional user file."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "default.yaml"
DETECTORS = ("audio_peak", "loudness_change", "frame_diff", "visual_activity", "scene_change", "sound_events")


class ConfigError(ValueError):
    pass


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def validate(cfg: dict) -> dict:
    weights = cfg["scoring"]["weights"]
    unknown = set(weights) - set(DETECTORS)
    if unknown:
        raise ConfigError(f"unknown detector weights: {sorted(unknown)}")
    if any(not isinstance(w, (int, float)) or w < 0 for w in weights.values()):
        raise ConfigError("detector weights must be non-negative numbers")
    if sum(weights.values()) <= 0:
        raise ConfigError("at least one detector weight must be positive")
    s = cfg["scoring"]
    if not 0 < s["min_duration_s"] <= s["max_duration_s"]:
        raise ConfigError("need 0 < min_duration_s <= max_duration_s")
    for name, p in cfg["render"]["presets"].items():
        if p["width"] % 2 or p["height"] % 2:
            raise ConfigError(f"preset {name}: width/height must be even")
        if p["mode"] not in ("fit", "crop", "blur"):
            raise ConfigError(f"preset {name}: mode must be fit, crop or blur")
    cfg["ingest"]["extensions"] = [e.lower() for e in cfg["ingest"]["extensions"]]
    return cfg


def load_config(path: str | Path | None = None, overrides: dict | None = None) -> dict[str, Any]:
    with open(DEFAULT_PATH) as fh:
        cfg = yaml.safe_load(fh)
    if path:
        with open(path) as fh:
            cfg = deep_merge(cfg, yaml.safe_load(fh) or {})
    if overrides:
        cfg = deep_merge(cfg, overrides)
    return validate(cfg)


def workspace(cfg: dict) -> Path:
    ws = Path(cfg["workspace"]).expanduser().resolve()
    ws.mkdir(parents=True, exist_ok=True)
    return ws
