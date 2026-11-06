"""Character checks: canvas, layer artwork, rig, face and approval state."""

from __future__ import annotations

import json
from pathlib import Path

from .artwork import check_layer, check_point
from .config import ProjectConfig
from .consistency import check_approval
from .face import validate_face
from .manifests import load_json, schema_errors
from .paths import resolve_inside
from .report import Report
from .rig import validate_rig

RIG_FILE = "rig.json"
FACE_FILE = "face.json"


def validate_character(
    folder: Path,
    asset: dict,
    label: str,
    config: ProjectConfig,
    report: Report,
    approval: bool = True,
) -> None:
    """`approval=False` skips the approval-history check; `./ashes approve` uses it while creating a version."""
    approved = asset["status"] == "approved"
    canvas_info = asset["character"]["canvas"]
    canvas = (canvas_info["width"], canvas_info["height"])
    check_point(report, label, "canvas root", canvas_info["root"], canvas)

    if approved and not asset["layers"]:
        report.error(f"{label}: approved assets need at least one layer")

    names = [layer["name"] for layer in asset["layers"]]
    for name in sorted({n for n in names if names.count(n) > 1}):
        report.error(f"{label}: duplicate layer name '{name}'")

    for layer in asset["layers"]:
        check_point(report, label, f"layer '{layer['name']}' pivot", layer["pivot"], canvas)
        target = resolve_inside(folder, layer["file"])
        if target is None:
            continue  # the escaping path is already reported by the project check
        check_layer(report, label, layer["file"], target, canvas, config.artwork, approved)

    rig = _load_definition(folder / RIG_FILE, "rig", label, RIG_FILE, approved, report)
    face = _load_definition(folder / FACE_FILE, "face", label, FACE_FILE, approved, report)

    bones = None
    if rig is not None:
        if rig["character"] != asset["id"]:
            report.error(f"{label}: {RIG_FILE} is for '{rig['character']}', not '{asset['id']}'")
        validate_rig(rig, label, set(names), report)
        bones = {bone["name"] for bone in rig["bones"]}
    if face is not None:
        if face["character"] != asset["id"]:
            report.error(f"{label}: {FACE_FILE} is for '{face['character']}', not '{asset['id']}'")
        validate_face(face, label, approved, set(names), bones, report)

    if approval:
        check_approval(folder, asset, label, report)


def mouth_info(folder: Path, asset: dict) -> tuple[bool, set[str]]:
    """(approved, visemes with a mouth sprite) for dialogue checks. Reads face.json without validating it."""
    approved = asset["status"] == "approved"
    path = folder / FACE_FILE
    try:
        face = load_json(path) if path.is_file() else {}
    except json.JSONDecodeError:
        face = {}
    return approved, set(face.get("mouth_sprites", {}))


def _load_definition(path: Path, schema: str, label: str, rel: str, approved: bool, report: Report) -> dict | None:
    if not path.is_file():
        report.issue(approved, f"{label}: missing {rel}")
        return None
    try:
        data = load_json(path)
    except json.JSONDecodeError as exc:
        report.error(f"{label}: {rel} is not valid JSON ({exc})")
        return None
    errors = schema_errors(schema, data)
    for error in errors:
        report.error(f"{label}: {rel}: {error}")
    return None if errors else data
