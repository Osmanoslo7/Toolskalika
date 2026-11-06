"""Approving a character freezes its current artwork as a new, immutable version.

Approval only reads the artwork. It writes a snapshot under history/v<version>/ and
appends to approval.json. It never edits or deletes an existing file.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .artwork import ArtworkError, layer_facts, load_png
from .characters import validate_character
from .config import ProjectConfig
from .consistency import APPROVAL_FILE, HISTORY_DIR, load_record, snapshot_dir, write_record
from .report import Report


class ApprovalError(Exception):
    """Approval was refused. The message says what to fix."""


def approve_character(folder: Path, asset: dict, label: str, config: ProjectConfig) -> dict:
    if asset["status"] != "approved":
        raise ApprovalError('set "status" to "approved" in asset.json before approving')

    report = Report()
    validate_character(folder, asset, label, config, report, approval=False)
    if not report.ok:
        raise ApprovalError("character has errors:\n  " + "\n  ".join(report.errors))

    versions: list[dict] = []
    if (folder / APPROVAL_FILE).is_file():
        record_report = Report()
        record = load_record(folder, record_report, label)
        if record is None:
            raise ApprovalError("existing approval history is invalid:\n  " + "\n  ".join(record_report.errors))
        versions = record["versions"]

    version = asset["version"]
    if versions and version <= versions[-1]["version"]:
        raise ApprovalError(
            f"version {version} must be higher than approved version {versions[-1]['version']}; bump the version in asset.json"
        )

    snapshot = snapshot_dir(folder, version)
    if snapshot.exists():
        raise ApprovalError(f"{snapshot.relative_to(folder)} already exists; approved snapshots are never overwritten")

    snapshot.mkdir(parents=True)
    layers: dict[str, dict] = {}
    for layer in asset["layers"]:
        source = folder / layer["file"]
        try:
            image = load_png(source)
        except ArtworkError as exc:  # validated above, so this only guards against a race
            raise ApprovalError(f"{layer['file']} changed while approving: {exc}") from exc
        facts = layer_facts(source, image)
        target = snapshot / f"{layer['name']}.png"
        target.write_bytes(source.read_bytes())
        layers[layer["name"]] = {
            "file": f"{HISTORY_DIR}/v{version}/{layer['name']}.png",
            "sha256": facts.sha256,
            "ahash": facts.ahash,
            "dhash": facts.dhash,
            "width": facts.width,
            "height": facts.height,
            "bbox": list(facts.bbox),
        }

    entry = {
        "version": version,
        "approved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "layers": layers,
    }
    write_record(folder, {"schema_version": 1, "character": asset["id"], "versions": versions + [entry]})
    return entry
