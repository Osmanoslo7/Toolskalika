"""Canonical locations inside the project. Resolved from this file, never from the working directory."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = PROJECT_ROOT / "config" / "project.toml"
SCHEMA_DIR = PROJECT_ROOT / "schemas"
TEMPLATE_DIR = PROJECT_ROOT / "templates"
SHOTS_DIR = "shots"
DIALOGUE_DIR = "dialogue"

# Asset folder -> the asset type it must hold.
ASSET_TYPE_BY_FOLDER = {
    "characters": "character",
    "environments": "environment",
    "props": "prop",
    "effects": "effect",
}


def resolve_inside(base: Path, rel: str) -> Path | None:
    """Resolve a manifest path under `base`.

    Returns None for absolute paths and for anything that escapes `base`
    (for example "../secret.png"). Nothing outside `base` is ever read.
    """
    if not isinstance(rel, str) or Path(rel).is_absolute():
        return None
    target = (base / rel).resolve()
    if not target.is_relative_to(base.resolve()):
        return None
    return target
