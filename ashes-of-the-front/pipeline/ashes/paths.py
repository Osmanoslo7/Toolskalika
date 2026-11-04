"""Canonical locations inside the project. Resolved from this file, never from the working directory."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = PROJECT_ROOT / "config" / "project.toml"
SCHEMA_DIR = PROJECT_ROOT / "schemas"
SHOTS_DIR = "shots"

# Asset folder -> the asset type it must hold.
ASSET_TYPE_BY_FOLDER = {
    "characters": "character",
    "environments": "environment",
    "props": "prop",
    "effects": "effect",
}
