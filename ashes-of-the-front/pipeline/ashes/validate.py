"""Project-wide validation: schema checks plus the rules a JSON Schema cannot express."""

from __future__ import annotations

import json
from pathlib import Path

from . import characters, dialogue
from .config import ProjectConfig
from .manifests import load_json, schema_errors
from .paths import ASSET_TYPE_BY_FOLDER, DIALOGUE_DIR, SHOTS_DIR, resolve_inside
from .report import Report

ASSET_FILE = "asset.json"
SHOT_FILE = "shot.json"
EPSILON = 1e-6

Assets = dict[str, tuple[Path, dict]]


def validate_project(root: Path, config: ProjectConfig) -> Report:
    """Check every asset, shot and dialogue schedule under `root`. Errors block rendering; warnings do not."""
    report = Report()
    assets = load_assets(root, report)
    mouth_info: dict[str, tuple[bool, set[str]]] = {}
    for asset_id, (path, data) in assets.items():
        label = _label(path, root)
        _check_layer_paths(path, data, label, report)
        if data["type"] == "character":
            characters.validate_character(path.parent, data, label, config, report)
            mouth_info[asset_id] = characters.mouth_info(path.parent, data)
    for path in sorted((root / SHOTS_DIR).glob(f"*/{SHOT_FILE}")):
        _check_shot(path, root, config, assets, report)
    for path in sorted((root / DIALOGUE_DIR).glob("*.json")):
        _check_dialogue(path, root, config, mouth_info, report)
    return report


def load_assets(root: Path, report: Report) -> Assets:
    assets: Assets = {}
    for folder, expected_type in ASSET_TYPE_BY_FOLDER.items():
        for path in sorted((root / folder).glob(f"*/{ASSET_FILE}")):
            label = _label(path, root)
            data = _read(path, root, report)
            if data is None:
                continue
            report.checked += 1
            errors = schema_errors("asset", data)
            for error in errors:
                report.error(f"{label}: {error}")
            if errors:
                continue
            asset_id = data["id"]
            if path.parent.name != asset_id:
                report.error(f"{label}: folder '{path.parent.name}' must match id '{asset_id}'")
            if data["type"] != expected_type:
                report.error(f"{label}: type '{data['type']}' does not belong in '{folder}/' (expected '{expected_type}')")
            if asset_id in assets:
                report.error(f"{label}: duplicate id '{asset_id}' (also used by {_label(assets[asset_id][0], root)})")
                continue
            assets[asset_id] = (path, data)
    return assets


def _label(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _read(path: Path, root: Path, report: Report):
    try:
        return load_json(path)
    except json.JSONDecodeError as exc:
        report.error(f"{_label(path, root)}: invalid JSON ({exc})")
        return None


def _check_layer_paths(path: Path, data: dict, label: str, report: Report) -> None:
    """Every layer file must be layers/<name>.png inside the asset folder.

    Character layers that are missing are reported by the artwork check instead.
    """
    approved = data["status"] == "approved"
    for layer in data["layers"]:
        name, rel = layer["name"], layer["file"]
        if resolve_inside(path.parent, rel) is None:
            report.error(f"{label}: layer '{name}' file '{rel}' must be a relative path inside the asset folder")
        elif rel != f"layers/{name}.png":
            report.error(f"{label}: layer '{name}' must be stored as 'layers/{name}.png', not '{rel}'")
        elif data["type"] != "character" and not (path.parent / rel).is_file():
            report.issue(approved, f"{label}: missing file '{rel}'")


def _check_shot(path: Path, root: Path, config: ProjectConfig, assets: Assets, report: Report) -> None:
    label = _label(path, root)
    data = _read(path, root, report)
    if data is None:
        return
    report.checked += 1
    errors = schema_errors("shot", data)
    for error in errors:
        report.error(f"{label}: {error}")
    if errors:
        return

    if path.parent.name != data["id"]:
        report.error(f"{label}: folder '{path.parent.name}' must match id '{data['id']}'")

    video = config.video
    if (data["width"], data["height"], data["fps"]) != (video.width, video.height, video.fps):
        report.error(f"{label}: must be {video.width}x{video.height} at {video.fps} fps (see config/project.toml)")

    duration = data["duration_seconds"]
    frames = duration * video.fps
    if abs(frames - round(frames)) > EPSILON:
        report.error(f"{label}: duration {duration}s is not a whole number of frames at {video.fps} fps")

    _check_times(label, "camera.keyframes", [k["time"] for k in data["camera"]["keyframes"]], duration, report)

    for character_id in data["characters"]:
        _require_asset(label, "characters", character_id, assets, "character", report)
    _require_asset(label, "environment", data["environment"], assets, "environment", report)

    for layer in data["layers"]:
        where = f"layers[{layer['id']}]"
        _require_asset(label, where, layer["asset"], assets, None, report)
        _check_times(label, f"{where}.keyframes", [k["time"] for k in layer["keyframes"]], duration, report)

    speakers = set(data["characters"])
    for i, line in enumerate(data["dialogue"]):
        where = f"dialogue[{i}]"
        _check_span(label, where, line["start"], line["end"], duration, report)
        if line.get("kind", "dialogue") == "dialogue" and line["speaker"] not in speakers:
            report.error(f"{label}: {where} speaker '{line['speaker']}' is not listed in characters")

    for i, cue in enumerate(data["audio"]):
        where = f"audio[{i}]"
        if not 0 <= cue["start"] < duration:
            report.error(f"{label}: {where} starts at {cue['start']}s, outside the shot")
        audio_file = resolve_inside(root, cue["file"])
        if audio_file is None:
            report.error(f"{label}: {where} file '{cue['file']}' must stay inside the project")
        elif not audio_file.is_file():
            report.warn(f"{label}: {where} audio file '{cue['file']}' does not exist yet")

    for i, effect in enumerate(data["effects"]):
        _check_span(label, f"effects[{i}] ({effect['type']})", effect["start"], effect["end"], duration, report)


def _check_dialogue(path: Path, root: Path, config: ProjectConfig, mouth_info: dict, report: Report) -> None:
    label = _label(path, root)
    data = _read(path, root, report)
    if data is None:
        return
    report.checked += 1
    errors = schema_errors("dialogue", data)
    for error in errors:
        report.error(f"{label}: {error}")
    if not errors:
        dialogue.validate_dialogue(data, label, config.video.fps, mouth_info, report)


def _check_times(label: str, where: str, times: list[float], duration: float, report: Report) -> None:
    for t in times:
        if not 0 <= t <= duration:
            report.error(f"{label}: {where} time {t}s is outside 0..{duration}s")
    if any(later <= earlier for earlier, later in zip(times, times[1:])):
        report.error(f"{label}: {where} times must be strictly increasing")


def _check_span(label: str, where: str, start: float, end: float, duration: float, report: Report) -> None:
    if not 0 <= start < end <= duration:
        report.error(f"{label}: {where} must satisfy 0 <= start < end <= {duration}s")


def _require_asset(label: str, where: str, asset_id: str, assets: Assets, expected_type: str | None, report: Report) -> None:
    if asset_id not in assets:
        report.error(f"{label}: {where} refers to unknown asset '{asset_id}'")
        return
    actual_type = assets[asset_id][1]["type"]
    if expected_type and actual_type != expected_type:
        report.error(f"{label}: {where} '{asset_id}' has type {actual_type}, expected {expected_type}")
