"""Facial animation checks: sprite references, jaw bone and the viseme-to-mouth-sprite map."""

from __future__ import annotations

from .report import Report
from .visemes import VISEMES


def validate_face(
    face: dict,
    label: str,
    approved: bool,
    layer_names: set[str],
    bone_names: set[str] | None,
    report: Report,
) -> None:
    """`bone_names` is None when rig.json is missing or invalid; bone checks are then skipped."""
    jaw = face["jaw_bone"]
    if bone_names is not None and jaw not in bone_names:
        report.error(f"{label}: jaw_bone '{jaw}' is not a bone in rig.json")

    for expression_name, expression in face["expressions"].items():
        for part, layer in expression.get("sprites", {}).items():
            if layer not in layer_names:
                report.error(
                    f"{label}: expression '{expression_name}' uses {part} sprite '{layer}', "
                    "which is not a layer in asset.json"
                )

    mouth = face["mouth_sprites"]
    for viseme, layer in mouth.items():
        if layer not in layer_names:
            report.error(f"{label}: viseme {viseme} uses sprite '{layer}', which is not a layer in asset.json")

    # A character with no artwork yet is a concept only, so it doesn't need a mouth map yet.
    missing = [viseme for viseme in VISEMES if viseme not in mouth]
    if missing and (approved or layer_names):
        report.issue(
            approved,
            f"{label}: no mouth sprite mapped for {len(missing)} viseme(s): {', '.join(missing)}",
        )
