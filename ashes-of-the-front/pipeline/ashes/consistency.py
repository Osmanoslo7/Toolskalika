"""Character consistency: approved snapshots, exact (SHA-256) and perceptual comparisons.

Rules:
- SHA-256 detects any byte-level change. A changed approved file is always an error.
- Perceptual hashes and pixel differences do not decide anything. They are reported so
  a person can judge whether a change is visible. Nothing is overwritten automatically.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from PIL import Image, ImageChops

from .artwork import ArtworkError, average_hash, difference_hash, hamming, load_png
from .manifests import load_json, schema_errors
from .report import Report

APPROVAL_FILE = "approval.json"
HISTORY_DIR = "history"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot_dir(folder: Path, version: int) -> Path:
    return folder / HISTORY_DIR / f"v{version}"


def load_record(folder: Path, report: Report, label: str) -> dict | None:
    """Load and schema-check approval.json. Returns None (and reports why) if it is missing or invalid."""
    path = folder / APPROVAL_FILE
    try:
        record = load_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        report.error(f"{label}: {APPROVAL_FILE} cannot be read ({exc})")
        return None
    errors = schema_errors("approval", record)
    for error in errors:
        report.error(f"{label}: {APPROVAL_FILE}: {error}")
    return None if errors else record


def write_record(folder: Path, record: dict) -> None:
    """Replace approval.json atomically, so a crash never leaves half a history behind."""
    path = folder / APPROVAL_FILE
    temporary = folder / (APPROVAL_FILE + ".tmp")
    temporary.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def check_approval(folder: Path, asset: dict, label: str, report: Report) -> None:
    approved = asset["status"] == "approved"
    if not (folder / APPROVAL_FILE).is_file():
        if approved:
            report.error(f"{label}: status is approved but {APPROVAL_FILE} is missing; run ./ashes approve {asset['id']}")
        return

    record = load_record(folder, report, label)
    if record is None:
        return

    versions = record["versions"]
    numbers = [entry["version"] for entry in versions]
    if numbers != sorted(set(numbers)):
        report.error(f"{label}: approval history versions must be unique and increasing")

    for entry in versions:
        for name, info in entry["layers"].items():
            snapshot = folder / info["file"]
            if not snapshot.is_file():
                report.error(f"{label}: approved snapshot v{entry['version']} of layer '{name}' is missing")
            elif sha256_file(snapshot) != info["sha256"]:
                report.error(f"{label}: approved snapshot v{entry['version']} of layer '{name}' was altered")

    latest = versions[-1]
    version = asset["version"]
    if version < latest["version"]:
        report.error(f"{label}: version {version} is older than approved version {latest['version']}")
    elif version > latest["version"]:
        if approved:
            report.error(
                f"{label}: version {version} is marked approved but has not been approved; "
                f"run ./ashes approve {asset['id']}"
            )
    else:
        _compare_to_approved(folder, asset, latest, label, report)


def _compare_to_approved(folder: Path, asset: dict, latest: dict, label: str, report: Report) -> None:
    version = latest["version"]
    approved_layers = latest["layers"]
    current = {layer["name"]: layer for layer in asset["layers"]}
    hint = f"Restore the approved file, or bump the version and re-approve. Details: ./ashes consistency {asset['id']}"

    for name in sorted(set(approved_layers) - set(current)):
        report.error(f"{label}: approved layer '{name}' (v{version}) was removed. {hint}")
    for name in sorted(set(current) - set(approved_layers)):
        report.error(f"{label}: layer '{name}' is not in approved version v{version}. Bump the version and re-approve.")
    for name in sorted(set(current) & set(approved_layers)):
        path = folder / current[name]["file"]
        if not path.is_file():
            continue  # reported as a missing file by the artwork check
        if sha256_file(path) != approved_layers[name]["sha256"]:
            report.error(f"{label}: approved artwork changed: layer '{name}' differs from v{version}. {hint}")


def compare_images(reference: Image.Image, current: Image.Image) -> tuple[dict, Image.Image | None]:
    """Pixel comparison. Returns a summary and a mask of changed pixels (None if sizes differ)."""
    if reference.size != current.size:
        return (
            {
                "size_match": False,
                "reference_size": list(reference.size),
                "current_size": list(current.size),
            },
            None,
        )
    difference = ImageChops.difference(reference.convert("RGBA"), current.convert("RGBA"))
    channels = difference.split()
    mask = channels[0]
    for channel in channels[1:]:
        mask = ImageChops.lighter(mask, channel)
    total = reference.width * reference.height
    changed = total - mask.histogram()[0]
    box = mask.getbbox()
    summary = {
        "size_match": True,
        "changed_pixels": changed,
        "changed_fraction": round(changed / total, 6),
        "changed_bbox": list(box) if box else None,
    }
    return summary, mask


def _compare_layer(folder: Path, name: str, approved: dict | None, layer: dict | None, masks: dict) -> dict:
    if approved is None:
        return {"status": "new"}
    if layer is None:
        return {"status": "removed"}
    current_path = folder / layer["file"]
    if not current_path.is_file():
        return {"status": "missing"}

    row = {
        "reference_sha256": approved["sha256"],
        "current_sha256": sha256_file(current_path),
    }
    if row["current_sha256"] == row["reference_sha256"]:
        row["status"] = "unchanged"
        return row

    row["status"] = "changed"
    try:
        reference_image = load_png(folder / approved["file"])
        current_image = load_png(current_path)
    except ArtworkError as exc:
        row["status"] = "invalid"
        row["reason"] = str(exc)
        return row

    summary, mask = compare_images(reference_image, current_image)
    row.update(summary)
    row["reference_bbox"] = approved["bbox"]
    row["current_bbox"] = list(current_image.getchannel("A").getbbox() or (0, 0, 0, 0))
    row["reference_ahash"] = approved["ahash"]
    row["current_ahash"] = average_hash(current_image)
    row["ahash_distance"] = hamming(row["reference_ahash"], row["current_ahash"])
    row["reference_dhash"] = approved["dhash"]
    row["current_dhash"] = difference_hash(current_image)
    row["dhash_distance"] = hamming(row["reference_dhash"], row["current_dhash"])
    if mask is not None:
        masks[name] = mask
    return row


def build_comparison(folder: Path, asset: dict, label: str) -> tuple[dict, dict[str, Image.Image]]:
    """Compare the current layers with the latest approved version. Read-only."""
    result: dict = {"character": asset["id"], "approved_version": None, "layers": {}, "problems": []}
    masks: dict[str, Image.Image] = {}
    if not (folder / APPROVAL_FILE).is_file():
        result["problems"].append("no approved version exists yet")
        return result, masks

    report = Report()
    record = load_record(folder, report, label)
    if record is None:
        result["problems"].extend(report.errors)
        return result, masks

    latest = record["versions"][-1]
    result["approved_version"] = latest["version"]
    current = {layer["name"]: layer for layer in asset["layers"]}
    for name in sorted(set(latest["layers"]) | set(current)):
        result["layers"][name] = _compare_layer(folder, name, latest["layers"].get(name), current.get(name), masks)
    return result, masks
