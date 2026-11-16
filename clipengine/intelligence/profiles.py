"""Game profiles: per-game event weights, highlight categories and enhancement rules."""
from __future__ import annotations

from pathlib import Path

import yaml

from ..config import DETECTORS, ConfigError

PROFILE_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "game_profiles"
EVENT_TYPES = ("impact", "explosion", "gunfire", "sudden_silence", "siren", "engine_rise", "music")
PSEUDO = ("confirmed_hit",)


def list_profiles() -> dict[str, str]:
    out = {}
    for p in sorted(PROFILE_DIR.glob("*.yaml")):
        with open(p) as fh:
            out[p.stem] = (yaml.safe_load(fh) or {}).get("name", p.stem)
    return out


def load_profile(key: str | None) -> dict:
    key = (key or "generic").lower()
    path = PROFILE_DIR / f"{key}.yaml"
    if not path.is_file():
        raise ConfigError(f"unknown game profile {key!r}; available: {', '.join(list_profiles())}")
    with open(path) as fh:
        prof = yaml.safe_load(fh) or {}
    prof["key"] = key
    prof.setdefault("weights", {})
    prof.setdefault("event_weights", {})
    prof.setdefault("categories", [])
    prof.setdefault("enhance", {})
    bad = set(prof["weights"]) - set(DETECTORS)
    if bad:
        raise ConfigError(f"profile {key}: unknown detector weights {sorted(bad)}")
    bad = set(prof["event_weights"]) - set(EVENT_TYPES)
    if bad:
        raise ConfigError(f"profile {key}: unknown events {sorted(bad)}")
    for c in prof["categories"]:
        names = set(c.get("all", [])) | set(c.get("any", []))
        if names - set(EVENT_TYPES) - set(PSEUDO):
            raise ConfigError(f"profile {key}: category {c.get('name')} uses unknown events")
    return prof


def apply_weights(cfg: dict, profile: dict) -> dict:
    """Return a copy of cfg with the profile's detector weight overrides applied."""
    import copy
    out = copy.deepcopy(cfg)
    out["scoring"]["weights"].update(profile.get("weights", {}))
    return out


def present_events(events: list[dict]) -> set[str]:
    names = {e["type"] for e in events}
    if any(e["type"] in ("impact", "explosion", "gunfire") and e.get("confirmed") for e in events):
        names.add("confirmed_hit")
    return names


def categorize(events: list[dict], motion: float, profile: dict) -> dict | None:
    """First category whose conditions hold for the events inside a clip."""
    present = present_events(events)
    for c in profile["categories"]:
        if c.get("all") and not set(c["all"]) <= present:
            continue
        if c.get("any") and not set(c["any"]) & present:
            continue
        if motion < c.get("motion", 0):
            continue
        return c
    return None
