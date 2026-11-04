"""Command line entry point: `./ashes doctor` and `./ashes validate`."""

from __future__ import annotations

import argparse
import sys

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
        print(f"Cannot validate: {exc}. Run: pip install -r requirements.txt")
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ashes", description="Ashes of the Front pipeline")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="check required and optional software").set_defaults(run=cmd_doctor)
    commands.add_parser("validate", help="check all asset and shot manifests").set_defaults(run=cmd_validate)
    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
