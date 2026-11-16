import os
import shutil
from pathlib import Path

import pytest

from clipengine.config import ConfigError, load_config
from clipengine.ingest import fingerprint, ingest_file, ingest_paths

from .conftest import sha256


def test_config_defaults_and_override(tmp_path):
    user = tmp_path / "u.yaml"
    user.write_text("scoring:\n  weights:\n    audio_peak: 0.9\n")
    cfg = load_config(user)
    assert cfg["scoring"]["weights"]["audio_peak"] == 0.9
    assert cfg["scoring"]["weights"]["frame_diff"] == 0.25          # untouched default kept
    assert cfg["render"]["presets"]["vertical"]["height"] == 1920


@pytest.mark.parametrize("bad", [
    {"scoring": {"weights": {"nonsense": 1}}},
    {"scoring": {"weights": {"audio_peak": -1}}},
    {"render": {"presets": {"landscape": {"width": 1921}}}},
])
def test_config_rejects_invalid(bad):
    with pytest.raises(ConfigError):
        load_config(overrides=bad)


def test_ingest_extracts_metadata_and_thumbnails(footage_dir, cfg, db):
    src = footage_dir / "match.mp4"
    before = sha256(src), os.stat(src).st_mtime
    r = ingest_file(src, cfg, db)
    assert r.status == "ingested", r.message
    m = db.get_media(r.media_id)
    assert (m["width"], m["height"]) == (640, 360)
    assert m["fps"] == 30
    assert 29.5 < m["duration_s"] < 30.5
    assert m["has_audio"] == 1 and m["audio_codec"] == "aac"
    thumbs = db.thumbnails(r.media_id)
    assert len(thumbs) == cfg["ingest"]["thumbnails"]
    assert all(os.path.getsize(t["path"]) > 0 for t in thumbs)
    # original untouched and not copied into the workspace
    assert (sha256(src), os.stat(src).st_mtime) == before
    assert list(Path(db.path).parent.rglob("*.mp4")) == []


def test_duplicate_detection(footage_dir, cfg, db, tmp_path):
    src = footage_dir / "match.mp4"
    assert ingest_file(src, cfg, db).status == "ingested"
    again = ingest_file(src, cfg, db)
    assert again.status == "duplicate" and "already" in again.message
    copy = tmp_path / "renamed_copy.mp4"
    shutil.copy(src, copy)
    dup = ingest_file(copy, cfg, db)
    assert dup.status == "duplicate" and "duplicate of" in dup.message
    assert len(db.list_media()) == 1


def test_fingerprint_changes_with_content(tmp_path):
    a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    a.write_bytes(b"x" * 10_000_000)
    b.write_bytes(b"x" * 9_999_999 + b"y")
    assert fingerprint(a) != fingerprint(b)
    assert fingerprint(a) == fingerprint(a)


def test_rejects_bad_inputs(cfg, db, tmp_path):
    txt = tmp_path / "notes.txt"
    txt.write_text("hi")
    assert ingest_file(txt, cfg, db).status == "rejected"
    fake = tmp_path / "broken.mp4"
    fake.write_bytes(b"not a video")
    r = ingest_file(fake, cfg, db)
    assert r.status == "rejected" and db.list_media() == []
    assert ingest_file(tmp_path / "missing.mp4", cfg, db).status == "rejected"


def test_ingest_directory_and_no_audio(footage_dir, cfg, db):
    results = ingest_paths([str(footage_dir)], cfg, db)
    assert sorted(r.status for r in results) == ["ingested", "ingested"]
    silent = next(r for r in results if r.path.endswith("silent.mov"))
    assert db.get_media(silent.media_id)["has_audio"] == 0
    assert "no audio" in silent.message


def test_stage_metrics_recorded(footage_dir, cfg, db):
    ingest_file(footage_dir / "match.mp4", cfg, db)
    runs = db.stage_runs()
    assert runs and runs[0]["stage"] == "ingest" and runs[0]["wall_s"] > 0
