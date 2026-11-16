"""Phase 1 — register recordings: metadata, fingerprint, duplicates, thumbnails.

Originals are only ever opened for reading. Nothing is copied: the database stores the
path plus a content fingerprint.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from . import ffmpeg
from .config import workspace
from .metrics import stage

CHUNK = 4 * 1024 * 1024


def fingerprint(path: str | Path) -> str:
    """Fast content fingerprint: SHA-256 of size + first, middle and last 4 MB.

    Stable across renames/moves, so a copy of the same file is detected as a duplicate,
    without reading multi-GB recordings in full.
    """
    size = os.path.getsize(path)
    h = hashlib.sha256(str(size).encode())
    with open(path, "rb") as fh:
        for offset in sorted({0, max(0, size // 2 - CHUNK // 2), max(0, size - CHUNK)}):
            fh.seek(offset)
            h.update(fh.read(CHUNK))
    return h.hexdigest()


@dataclass
class IngestResult:
    path: str
    status: str            # ingested | duplicate | rejected
    media_id: int | None = None
    message: str = ""


def generate_thumbnails(src: str, duration: float, out_dir: Path, count: int, width: int) -> list[tuple[float, str]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    thumbs = []
    for i in range(count):
        t = duration * (i + 0.5) / count
        out = out_dir / f"thumb_{i:02d}.jpg"
        ffmpeg.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", src, "-frames:v", "1",
                    "-vf", f"scale={width}:-2", "-q:v", "4", str(out)])
        if out.exists() and out.stat().st_size > 0:
            thumbs.append((round(t, 3), str(out)))
    return thumbs


def ingest_file(path: str | Path, cfg: dict, db) -> IngestResult:
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        return IngestResult(str(p), "rejected", message="file not found")
    if p.suffix.lower() not in cfg["ingest"]["extensions"]:
        return IngestResult(str(p), "rejected", message=f"unsupported extension {p.suffix}")
    ws = workspace(cfg)
    if ws == p.parent or ws in p.parents:
        return IngestResult(str(p), "rejected", message="file is inside the workspace")

    with stage(db, "ingest") as detail:
        fp = fingerprint(p)
        existing = db.media_by_fingerprint(fp)
        if existing:
            same = existing["path"] == str(p)
            return IngestResult(str(p), "duplicate", existing["id"],
                                "already ingested" if same else f"duplicate of {existing['path']}")
        try:
            meta = ffmpeg.probe(p)
        except ffmpeg.FFmpegError as exc:
            return IngestResult(str(p), "rejected", message=str(exc))
        if meta["duration_s"] <= 0:
            return IngestResult(str(p), "rejected", message="zero duration")

        media_id = db.add_media(
            path=str(p), fingerprint=fp, size_bytes=meta["size_bytes"], mtime=p.stat().st_mtime,
            container=meta["container"], duration_s=meta["duration_s"], width=meta["width"],
            height=meta["height"], fps=meta["fps"], video_codec=meta["video_codec"],
            audio_codec=meta["audio_codec"], has_audio=int(meta["has_audio"]))
        thumbs = generate_thumbnails(str(p), meta["duration_s"], ws / "thumbs" / str(media_id),
                                     cfg["ingest"]["thumbnails"], cfg["ingest"]["thumbnail_width"])
        for t, tp in thumbs:
            db.add_thumbnail(media_id, t, tp)
        detail.update(media_id=media_id, duration_s=meta["duration_s"], thumbnails=len(thumbs))
    msg = f"{meta['width']}x{meta['height']} {meta['fps']}fps {meta['duration_s']:.1f}s" + \
          ("" if meta["has_audio"] else " (no audio)")
    return IngestResult(str(p), "ingested", media_id, msg)


def ingest_paths(paths: list[str], cfg: dict, db) -> list[IngestResult]:
    """Ingest files and/or directories (directories are scanned recursively)."""
    results = []
    exts = cfg["ingest"]["extensions"]
    for raw in paths:
        p = Path(raw).expanduser()
        if p.is_dir():
            files = sorted(f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in exts)
            results.extend(ingest_file(f, cfg, db) for f in files)
        else:
            results.append(ingest_file(p, cfg, db))
    return results
