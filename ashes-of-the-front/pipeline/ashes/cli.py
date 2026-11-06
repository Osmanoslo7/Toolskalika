"""Command line entry point: ./ashes doctor | validate | approve | consistency."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .deps import check_all
from .paths import PROJECT_ROOT


def cmd_doctor(_args: argparse.Namespace) -> int:
    failed = False
    for check in check_all():
        if check.ok:
            status = "OK"
        else:
            status = "FAIL" if check.required else "MISSING"
            failed = failed or check.required
        print(f"{status:8}{check.name:14}{check.detail}")
        if not check.ok:
            print(f"{'':8}{'':14}needed for: {check.needed_for}")
    if failed:
        print("\nRequired dependencies are missing. Install them, then run ./ashes doctor again.")
        return 1
    print("\nRequired dependencies are present.")
    return 0


def cmd_validate(_args: argparse.Namespace) -> int:
    try:
        from .config import load_config
        from .validate import validate_project
    except ImportError as exc:
        print(f"Cannot validate: {exc}. Run: python3 -m pip install -r requirements.txt")
        return 2

    report = validate_project(PROJECT_ROOT, load_config())
    for warning in report.warnings:
        print(f"WARN   {warning}")
    for error in report.errors:
        print(f"ERROR  {error}")
    print(
        f"\nChecked {report.checked} manifest(s): "
        f"{len(report.errors)} error(s), {len(report.warnings)} warning(s)."
    )
    return 0 if report.ok else 1


def _character(character_id: str):
    """Return (folder, asset, label) for a character, or None after printing why."""
    from .manifests import load_json, schema_errors

    folder = PROJECT_ROOT / "characters" / character_id
    path = folder / "asset.json"
    if not path.is_file():
        print(f"No character '{character_id}' (expected {path.relative_to(PROJECT_ROOT)}).")
        return None
    asset = load_json(path)
    errors = schema_errors("asset", asset)
    if errors or asset.get("type") != "character":
        print(f"{path.relative_to(PROJECT_ROOT)} is not a valid character manifest: {errors or 'wrong type'}")
        return None
    return folder, asset, path.relative_to(PROJECT_ROOT).as_posix()


def cmd_approve(args: argparse.Namespace) -> int:
    from .approval import ApprovalError, approve_character
    from .config import load_config

    found = _character(args.character)
    if found is None:
        return 1
    folder, asset, label = found
    try:
        entry = approve_character(folder, asset, label, load_config())
    except ApprovalError as exc:
        print(f"Not approved.\n{exc}")
        return 1
    snapshot = (folder / "history" / f"v{entry['version']}").relative_to(PROJECT_ROOT)
    print(f"Approved '{asset['id']}' version {entry['version']}: {len(entry['layers'])} layer(s).")
    print(f"Snapshot: {snapshot}/   Record: {(folder / 'approval.json').relative_to(PROJECT_ROOT)}")
    return 0


def cmd_consistency(args: argparse.Namespace) -> int:
    from .consistency import build_comparison

    found = _character(args.character)
    if found is None:
        return 1
    folder, asset, label = found
    result, masks = build_comparison(folder, asset, label)

    out: Path = PROJECT_ROOT / "build" / "consistency" / asset["id"]
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for name, mask in masks.items():
        mask.point(lambda value: 255 if value else 0).save(out / f"{name}.changed.png")

    if result["problems"]:
        for problem in result["problems"]:
            print(f"  {problem}")
    if result["approved_version"] is None:
        return 1
    print(f"Compared with approved version {result['approved_version']}:")
    clean = True
    for name, row in result["layers"].items():
        clean = clean and row["status"] == "unchanged"
        detail = ""
        if row["status"] == "changed" and row.get("size_match"):
            detail = (
                f"  pixels {row['changed_pixels']} ({row['changed_fraction']:.2%}), "
                f"aHash {row['ahash_distance']}/64, dHash {row['dhash_distance']}/64"
            )
        print(f"  {name:20}{row['status']}{detail}")
    print(f"Report: {(out / 'report.json').relative_to(PROJECT_ROOT)}")
    return 0 if clean and not result["problems"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ashes", description="Ashes of the Front pipeline")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="check required and optional software").set_defaults(run=cmd_doctor)
    commands.add_parser("validate", help="check all asset, shot and dialogue manifests").set_defaults(run=cmd_validate)

    approve = commands.add_parser("approve", help="freeze a character's approved artwork as a new version")
    approve.add_argument("character", help="character id, e.g. elias_vale")
    approve.set_defaults(run=cmd_approve)

    consistency = commands.add_parser("consistency", help="compare a character with its latest approved version")
    consistency.add_argument("character", help="character id, e.g. elias_vale")
    consistency.set_defaults(run=cmd_consistency)

    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
