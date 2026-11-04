"""Project-wide validation: schema checks plus the rules a JSON Schema cannot express."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .config import ProjectConfig
from .manifests import load_json, schema_errors
from .paths import ASSET_TYPE_BY_FOLDER, SHOTS_DIR

ASSET_FILE = "asset.json"
SHOT_FILE = "shot.json"
EPSILON = 1e-6

Assets = dict[str, tuple[Path, dict]]


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checked: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_project(root: Path, config: ProjectConfig) -> Report:
    """Check every asset and shot under `root`. Errors block rendering; warnings are reported only."""
    report = Report()
    assets = _load_assets(root, report)
    for path, data in assets.values():
        _check_asset_files(path, data, root, report)
    for path in sorted((root / SHOTS_DIR).glob(f"*/{SHOT_FILE}")):
        _check_shot(path, root, config, assets, report)
    return report


def _label(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _read(path: Path, root: Path, report: Report):
    try:
        return load_json(path)
    except json.JSONDecodeError as exc:
        report.errors.append(f"{_label(path, root)}: invalid JSON ({exc})")
        return None


def _inside(base: Path, rel: str) -> Path | None:
    """Resolve a manifest path, refusing absolute paths and anything that escapes `base`."""
    if Path(rel).is_absolute():
        return None
    target = (base / rel).resolve()
    if not target.is_relative_to(base.resolve()):
        return None
    return target


def _load_assets(root: Path, report: Report) -> Assets:
    assets: Assets = {}
    for folder, expected_type in ASSET_TYPE_BY_FOLDER.items():
        for path in sorted((root / folder).glob(f"*/{ASSET_FILE}")):
            label = _label(path, root)
            data = _read(path, root, report)
            if data is None:
                continue
            report.checked += 1
            errors = schema_errors("asset", data)
            report.errors.extend(f"{label}: {e}" for e in errors)
            if errors:
                continue
            asset_id = data["id"]
            if path.parent.name != asset_id:
                report.errors.append(f"{label}: folder '{path.parent.name}' must match id '{asset_id}'")
            if data["type"] != expected_type:
                report.errors.append(
                    f"{label}: type '{data['type']}' does not belong in '{folder}/' (expected '{expected_type}')"
                )
            if asset_id in assets:
                report.errors.append(f"{label}: duplicate id '{asset_id}' (also used by {_label(assets[asset_id][0], root)})")
                continue
            assets[asset_id] = (path, data)
    return assets


def _file_refs(data: dict) -> list[tuple[str, str]]:
    refs = [(f"layers[{i}].file", layer["file"]) for i, layer in enumerate(data["layers"])]
    character = data.get("character", {})
    refs += [(f"character.expressions.{name}", rel) for name, rel in character.get("expressions", {}).items()]
    refs += [(f"character.mouth_shapes.{name}", rel) for name, rel in character.get("mouth_shapes", {}).items()]
    if "rig" in character:
        refs.append(("character.rig.file", character["rig"]["file"]))
    return refs


def _check_asset_files(path: Path, data: dict, root: Path, report: Report) -> None:
    label = _label(path, root)
    approved = data["status"] == "approved"
    if approved and not data["layers"]:
        report.errors.append(f"{label}: approved assets need at least one layer")
    for where, rel in _file_refs(data):
        target = _inside(path.parent, rel)
        if target is None:
            report.errors.append(f"{label}: {where} '{rel}' must be a relative path inside the asset folder")
        elif not target.is_file():
            message = f"{label}: {where} points to missing file '{rel}'"
            # An approved asset must be complete; a draft may still be waiting for its art.
            (report.errors if approved else report.warnings).append(message)


def _check_shot(path: Path, root: Path, config: ProjectConfig, assets: Assets, report: Report) -> None:
    label = _label(path, root)
    data = _read(path, root, report)
    if data is None:
        return
    report.checked += 1
    errors = schema_errors("shot", data)
    report.errors.extend(f"{label}: {e}" for e in errors)
    if errors:
        return

    if path.parent.name != data["id"]:
        report.errors.append(f"{label}: folder '{path.parent.name}' must match id '{data['id']}'")

    video = config.video
    if (data["width"], data["height"], data["fps"]) != (video.width, video.height, video.fps):
        report.errors.append(
            f"{label}: must be {video.width}x{video.height} at {video.fps} fps (see config/project.toml)"
        )

    duration = data["duration_seconds"]
    frames = duration * video.fps
    if abs(frames - round(frames)) > EPSILON:
        report.errors.append(f"{label}: duration {duration}s is not a whole number of frames at {video.fps} fps")

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
            report.errors.append(f"{label}: {where} speaker '{line['speaker']}' is not listed in characters")

    for i, cue in enumerate(data["audio"]):
        where = f"audio[{i}]"
        if not 0 <= cue["start"] < duration:
            report.errors.append(f"{label}: {where} starts at {cue['start']}s, outside the shot")
        audio_file = _inside(root, cue["file"])
        if audio_file is None:
            report.errors.append(f"{label}: {where} file '{cue['file']}' must stay inside the project")
        elif not audio_file.is_file():
            report.warnings.append(f"{label}: {where} audio file '{cue['file']}' does not exist yet")

    for i, effect in enumerate(data["effects"]):
        _check_span(label, f"effects[{i}] ({effect['type']})", effect["start"], effect["end"], duration, report)


def _check_times(label: str, where: str, times: list[float], duration: float, report: Report) -> None:
    for t in times:
        if not 0 <= t <= duration:
            report.errors.append(f"{label}: {where} time {t}s is outside 0..{duration}s")
    if any(later <= earlier for earlier, later in zip(times, times[1:])):
        report.errors.append(f"{label}: {where} times must be strictly increasing")


def _check_span(label: str, where: str, start: float, end: float, duration: float, report: Report) -> None:
    if not 0 <= start < end <= duration:
        report.errors.append(f"{label}: {where} must satisfy 0 <= start < end <= {duration}s")


def _require_asset(
    label: str, where: str, asset_id: str, assets: Assets, expected_type: str | None, report: Report
) -> None:
    if asset_id not in assets:
        report.errors.append(f"{label}: {where} refers to unknown asset '{asset_id}'")
        return
    actual_type = assets[asset_id][1]["type"]
    if expected_type and actual_type != expected_type:
        report.errors.append(f"{label}: {where} '{asset_id}' has type {actual_type}, expected {expected_type}")
