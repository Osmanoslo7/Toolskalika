"""Load config/project.toml into typed settings."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from .paths import CONFIG_FILE


@dataclass(frozen=True)
class VideoSettings:
    width: int
    height: int
    fps: int


@dataclass(frozen=True)
class EpisodeSettings:
    min_seconds: float
    max_seconds: float


@dataclass(frozen=True)
class ProjectConfig:
    name: str
    slug: str
    video: VideoSettings
    episode: EpisodeSettings


def load_config(path: Path = CONFIG_FILE) -> ProjectConfig:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return ProjectConfig(
        name=data["project"]["name"],
        slug=data["project"]["slug"],
        video=VideoSettings(**data["video"]),
        episode=EpisodeSettings(**data["episode"]),
    )
