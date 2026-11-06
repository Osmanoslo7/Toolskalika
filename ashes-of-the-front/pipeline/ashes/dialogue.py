"""Dialogue viseme schedules. The file stores integer frames on the canonical 24 fps timeline."""

from __future__ import annotations

from .report import Report


def seconds_to_frame(seconds: float, fps: int) -> int:
    """Convert an audio timestamp to the nearest frame. Authoring tools use this; the file stores frames only."""
    if seconds < 0:
        raise ValueError("timestamps cannot be negative")
    return round(seconds * fps)


def validate_dialogue(
    data: dict,
    label: str,
    fps: int,
    mouth_info: dict[str, tuple[bool, set[str]]],
    report: Report,
) -> None:
    """`mouth_info` maps character id -> (approved, visemes that character has a mouth sprite for)."""
    if data["fps"] != fps:
        report.error(f"{label}: fps must be {fps} (see config/project.toml)")

    character = data["character"]
    if character not in mouth_info:
        report.error(f"{label}: unknown character '{character}'")

    duration = data["duration_frames"]
    frames = [event["frame"] for event in data["events"]]
    if frames[0] != 0:
        report.error(f"{label}: the first viseme event must be at frame 0")
    if any(later <= earlier for earlier, later in zip(frames, frames[1:])):
        report.error(f"{label}: event frames must be strictly increasing")
    for frame in frames:
        if frame >= duration:
            report.error(f"{label}: event at frame {frame} is outside duration_frames {duration}")

    if character in mouth_info:
        approved, mapped = mouth_info[character]
        used = {event["viseme"] for event in data["events"]}
        for viseme in sorted(used - mapped):
            report.issue(approved, f"{label}: viseme {viseme} has no mouth sprite on '{character}'")
