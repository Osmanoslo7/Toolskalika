"""Shared fixtures: small synthetic recordings with known, planted events."""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from clipengine.config import load_config
from clipengine.db import open_db


def ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def make_gameplay(path: Path, *, audio: bool = True) -> Path:
    """30 s, 640x360@30, with planted events:

    0-10 s   calm: slowly drifting gradient, quiet tone
    10-14 s  ACTION: fast noisy motion + loud noise burst        (highlight 1)
    14-20 s  calm, different scene (hard cut at 14 s)
    20-23 s  ACTION: fast moving test pattern + loud burst       (highlight 2)
    23-30 s  calm
    """
    calm = "gradients=s=640x360:r=30:speed=0.002:seed={seed}"
    segs = [
        (calm.format(seed=1), 10, "sine=f=220:r=48000", 0.05),
        ("cellauto=s=640x360:r=30:rule=110:random_fill_ratio=0.5", 4, "anoisesrc=r=48000:a=0.9", 1.0),
        (calm.format(seed=7), 6, "sine=f=330:r=48000", 0.05),
        ("testsrc2=s=640x360:r=30", 3, "anoisesrc=r=48000:a=0.9:c=pink", 1.0),
        (calm.format(seed=3), 7, "sine=f=262:r=48000", 0.05),
    ]
    inputs, filt = [], []
    for i, (v, d, a, vol) in enumerate(segs):
        inputs += ["-f", "lavfi", "-i", f"{v}:d={d}" if "testsrc" in v or "gradients" in v else f"{v}",
                   "-f", "lavfi", "-t", str(d), "-i", a]
        filt.append(f"[{2*i}:v]trim=duration={d},setpts=PTS-STARTPTS,format=yuv420p[v{i}];"
                    f"[{2*i+1}:a]volume={vol},aformat=sample_rates=48000:channel_layouts=stereo[a{i}]")
    n = len(segs)
    concat = "".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[v][a]"
    tmp = path.with_name(path.stem + "_full.mp4") if not audio else path
    ff(*inputs, "-filter_complex", ";".join(filt) + ";" + concat, "-map", "[v]", "-map", "[a]",
       "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-c:a", "aac", str(tmp))
    if not audio:
        ff("-i", str(tmp), "-map", "0:v", "-c", "copy", str(path))
        tmp.unlink()
    return path


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture(scope="session")
def footage_dir(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("footage")
    make_gameplay(d / "match.mp4")
    make_gameplay(d / "silent.mov", audio=False)
    return d


@pytest.fixture
def cfg(tmp_path):
    return load_config(overrides={"workspace": str(tmp_path / "ws")})


@pytest.fixture
def db(cfg):
    from clipengine.config import workspace
    d = open_db(workspace(cfg))
    yield d
    d.close()
