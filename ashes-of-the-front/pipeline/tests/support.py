"""Shared test helpers. Every image and manifest is generated here, in temporary folders.

No test writes artwork into the real project. The PNGs are plain synthetic test shapes,
not character art, and nothing generated here is ever approved.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

from ashes.approval import approve_character
from ashes.config import load_config
from ashes.visemes import VISEMES

CONFIG = load_config()
CANVAS = (256, 256)
ROOT_POINT = [128, 200]
BODY_BOX = (60, 60, 190, 200)  # (left, top, right, bottom), right/bottom exclusive
MOUTH_BOX = (100, 150, 150, 180)
RED = (180, 30, 30, 255)


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def make_png(path: Path, size=CANVAS, box=BODY_BOX, color=RED, mode="RGBA") -> None:
    """Write a synthetic layer: a filled rectangle on a transparent canvas (or no box at all)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    if box is not None:
        ImageDraw.Draw(image).rectangle((box[0], box[1], box[2] - 1, box[3] - 1), fill=color)
    if mode != "RGBA":
        image = image.convert(mode)
    image.save(path, "PNG")


def minimal_rig(character_id: str) -> dict:
    """A valid rig with one root bone and a jaw. No attachments."""
    return {
        "schema_version": 1,
        "character": character_id,
        "coordinate_space": "character",
        "units": "pixels",
        "rotation_units": "degrees",
        "bones": [
            {"name": "root", "parent": None, "transform": {"x": 0, "y": 0}},
            {"name": "jaw", "parent": "root", "transform": {"x": 0, "y": -100}},
        ],
        "attachments": [],
        "draw_order": [],
        "constraints": [],
        "deform": [],
    }


def default_expressions() -> dict:
    neutral = {"eye_open": 1, "eye_direction": [0, 0], "brow_angle": 0, "brow_height": 0, "jaw_open": 0}
    return {name: dict(neutral) for name in ("neutral", "angry", "determined", "surprised", "injured")}


def minimal_face(character_id: str, mouth_sprites: dict | None = None) -> dict:
    return {
        "schema_version": 1,
        "character": character_id,
        "jaw_bone": "jaw",
        "mouth_sprites": mouth_sprites or {},
        "expressions": default_expressions(),
    }


def character_asset(character_id: str = "hero", status: str = "draft", version: int = 1, layers=None) -> dict:
    return {
        "schema_version": 2,
        "id": character_id,
        "type": "character",
        "name": character_id.title(),
        "version": version,
        "status": status,
        "description": "Synthetic test character.",
        "layers": layers or [],
        "character": {
            "identity": {"age": 30, "role": "tester"},
            "canvas": {"width": CANVAS[0], "height": CANVAS[1], "root": ROOT_POINT},
        },
    }


def build_character(root: Path, character_id: str = "hero", status: str = "draft", version: int = 1,
                    visemes: bool = False) -> Path:
    """Create a complete synthetic character under `root`. With visemes=True it gets all 14 mouth sprites."""
    folder = root / "characters" / character_id
    names = ["body"] + ([f"mouth_{v.lower()}" for v in VISEMES] if visemes else [])
    layers = []
    for z, name in enumerate(names):
        make_png(folder / "layers" / f"{name}.png", box=BODY_BOX if name == "body" else MOUTH_BOX)
        layers.append({"name": name, "file": f"layers/{name}.png", "z": z, "pivot": ROOT_POINT})

    write_json(folder / "asset.json", character_asset(character_id, status, version, layers))
    rig = minimal_rig(character_id)
    rig["bones"].append({"name": "head", "parent": "root", "transform": {"x": 0, "y": -200}})
    rig["attachments"] = [{"layer": "body", "bone": "root"}]
    rig["attachments"] += [{"layer": n, "bone": "jaw"} for n in names[1:]]
    rig["draw_order"] = names
    write_json(folder / "rig.json", rig)
    mouths = {v: f"mouth_{v.lower()}" for v in VISEMES} if visemes else {}
    write_json(folder / "face.json", minimal_face(character_id, mouths))
    return folder


def approve(folder: Path, label: str):
    """Approve through the real approval code path, exactly as ./ashes approve does."""
    asset = json.loads((folder / "asset.json").read_text(encoding="utf-8"))
    return approve_character(folder, asset, label, CONFIG)
