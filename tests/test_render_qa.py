import re
import shutil
import subprocess

import pytest

from clipengine.detect import analyze
from clipengine.ingest import ingest_file
from clipengine.qa import analyse_file, check_render
from clipengine.render import parse_srt, render_all_presets, shift_srt

from .conftest import ff, sha256


@pytest.fixture
def analysed(footage_dir, cfg, db, tmp_path):
    src = tmp_path / "game.mp4"
    shutil.copy(footage_dir / "match.mp4", src)
    (tmp_path / "game.srt").write_text("1\n00:00:09,000 --> 00:00:12,000\nIncoming!\n")
    r = ingest_file(src, cfg, db)
    cands = analyze(r.media_id, cfg, db)
    return src, r.media_id, cands


def loudness(path) -> float:
    out = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", out)[-1])


def test_srt_parse_and_shift():
    entries = parse_srt("1\n00:00:01,000 --> 00:00:03,500\nHello\n\n2\n00:01:00,000 --> 00:01:02,000\nLater\n")
    assert entries == [(1.0, 3.5, "Hello"), (60.0, 62.0, "Later")]
    shifted = shift_srt(entries, 2.0, 10.0)
    assert "00:00:00,000 --> 00:00:01,500" in shifted and "Later" not in shifted


def test_render_both_formats_and_pass_qa(analysed, cfg, db):
    src, media_id, cands = analysed
    before = sha256(src)
    cand = cands[0]
    renders = render_all_presets(cand["id"], cfg, db)
    sizes = {r["preset"]: (r["width"], r["height"]) for r in renders}
    assert sizes == {"landscape": (1920, 1080), "vertical": (1080, 1920)}
    for r in renders:
        assert r["duration_s"] == pytest.approx(cand["duration_s"], abs=0.1)
        assert r["thumb_path"] and r["size_bytes"] > 0
        q = check_render(r, cfg, db)
        assert q["status"] in ("passed", "warning"), q
        assert abs(loudness(r["path"]) - cfg["render"]["loudness"]["integrated"]) < 1.5
        assert r["path"].endswith(".mp4")
        assert (src.parent / "game.srt").exists()
    assert sha256(src) == before                     # original untouched
    assert {r["qa_status"] for r in db.renders(cand["id"])} <= {"passed", "warning"}
    stages = {s["stage"] for s in db.stage_runs(media_id)}
    assert {"ingest", "analyze", "render:landscape", "render:vertical"} <= stages


def test_render_blur_mode_and_silent_source(footage_dir, cfg, db):
    cfg["render"]["presets"]["vertical"]["mode"] = "blur"
    r = ingest_file(footage_dir / "silent.mov", cfg, db)
    cand = analyze(r.media_id, cfg, db)[0]
    rend = render_all_presets(cand["id"], cfg, db, ["vertical"])[0]
    assert (rend["width"], rend["height"]) == (1080, 1920)
    q = check_render(rend, cfg, db)
    audio = next(c for c in q["checks"] if c["name"] == "audio")
    assert audio["level"] == "warn" and "no audio" in audio["message"]   # flagged, not hidden


# --- QA on deliberately broken files --------------------------------------------------------

QA = dict(width=640, height=360, duration=4.0, fade_in=0.0, fade_out=0.0, source_has_audio=True)


def qa(path, cfg, **kw):
    return analyse_file(path, qcfg=cfg["qa"], **{**QA, **kw})


def levels(result):
    return {c["name"]: c["level"] for c in result["checks"]}


@pytest.fixture
def good_clip(tmp_path):
    p = tmp_path / "good.mp4"
    ff("-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=4", "-f", "lavfi", "-i", "sine=f=440:d=4",
       "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(p))
    return p


def test_qa_passes_good_clip(good_clip, cfg):
    assert qa(good_clip, cfg)["status"] == "passed"


def test_qa_flags_black(tmp_path, cfg):
    p = tmp_path / "black.mp4"
    ff("-f", "lavfi", "-i", "color=black:s=640x360:r=30:d=4", "-f", "lavfi", "-i", "sine=d=4",
       "-c:v", "libx264", "-c:a", "aac", "-shortest", str(p))
    r = qa(p, cfg)
    assert r["status"] == "failed" and levels(r)["black_frames"] == "fail"


def test_qa_flags_frozen(tmp_path, cfg):
    p = tmp_path / "frozen.mp4"
    ff("-f", "lavfi", "-i", "testsrc=s=640x360:r=1:d=1", "-f", "lavfi", "-i", "sine=d=4",
       "-vf", "loop=loop=-1:size=1,fps=30", "-t", "4", "-c:v", "libx264", "-c:a", "aac", str(p))
    assert levels(qa(p, cfg))["frozen_frames"] == "fail"


def test_qa_flags_missing_audio(tmp_path, good_clip, cfg):
    p = tmp_path / "noaudio.mp4"
    ff("-i", str(good_clip), "-an", "-c", "copy", str(p))
    assert levels(qa(p, cfg))["audio"] == "fail"
    silent = tmp_path / "silent.mp4"
    ff("-i", str(good_clip), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-map", "0:v", "-map", "1:a",
       "-c:v", "copy", "-c:a", "aac", "-shortest", str(silent))
    assert levels(qa(silent, cfg))["audio"] == "fail"


def test_qa_flags_wrong_aspect_and_duration(good_clip, cfg):
    r = qa(good_clip, cfg, width=1080, height=1920, duration=10.0)
    assert levels(r)["aspect_ratio"] == "fail" and levels(r)["duration"] == "fail"


def test_qa_flags_corrupt_and_missing(tmp_path, good_clip, cfg):
    data = good_clip.read_bytes()
    cut = tmp_path / "truncated.mp4"
    cut.write_bytes(data[: len(data) // 2])            # moov atom at the end -> unreadable
    assert qa(cut, cfg)["status"] == "failed"
    garbage = tmp_path / "garbage.mp4"
    garbage.write_bytes(data[:2000] + b"\x00" * 50000 + data[52000:])
    assert qa(garbage, cfg)["status"] == "failed"
    assert qa(tmp_path / "nope.mp4", cfg)["checks"][0]["level"] == "fail"
