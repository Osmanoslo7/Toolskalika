"""Detect the software the pipeline depends on. Nothing is assumed to be installed."""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from importlib import metadata


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    required: bool  # needed by the steps that exist today
    needed_for: str
    detail: str


def _python() -> Check:
    version = ".".join(map(str, sys.version_info[:3]))
    ok = sys.version_info >= (3, 11)
    detail = version if ok else f"{version} (3.11 or newer is required)"
    return Check("python", ok, True, "everything", detail)


def _package(dist: str, required: bool, needed_for: str) -> Check:
    try:
        return Check(dist, True, required, needed_for, metadata.version(dist))
    except metadata.PackageNotFoundError:
        return Check(dist, False, required, needed_for, "not installed (pip install -r requirements.txt)")


def _binary(name: str, args: list[str], needed_for: str) -> Check:
    path = shutil.which(name)
    if path is None:
        return Check(name, False, False, needed_for, "not found on PATH")
    try:
        result = subprocess.run([path, *args], capture_output=True, text=True, timeout=30, check=False)
        first_line = (result.stdout or result.stderr).splitlines()[0]
    except (OSError, subprocess.SubprocessError, IndexError) as exc:
        return Check(name, False, False, needed_for, f"found at {path} but gave no version ({exc})")
    return Check(name, True, False, needed_for, first_line)


def check_all() -> list[Check]:
    return [
        _python(),
        _package("jsonschema", True, "manifest validation"),
        _binary("blender", ["--version"], "scene build and animation (Phase 3)"),
        _binary("ffmpeg", ["-version"], "audio and rendering (Phase 4)"),
        _binary("ffprobe", ["-version"], "checking rendered output (Phase 4)"),
    ]
