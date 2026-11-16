"""Beta 0.2: sound events, visual corroboration, game profiles, enhancement, licensing."""
import subprocess

import numpy as np
import pytest

from clipengine.config import ConfigError
from clipengine.detect import analyze
from clipengine.export import export_approved
from clipengine.ingest import ingest_file
from clipengine.intelligence.audio_events import corroborate, detect_events, spectral_features
from clipengine.intelligence.profiles import categorize, list_profiles, load_profile
from clipengine.intelligence.sfx import audio_sources_ok, ensure_builtin, load_registry, register_sound
from clipengine.qa import check_render
from clipengine.render import render_all_presets, zoom_filter

from .audio_fixtures import EVENTS, SR, make_event_video, soundtrack, write_wav
from .conftest import ff, sha256


@pytest.fixture(scope="module")
def event_video(tmp_path_factory):
    return make_event_video(tmp_path_factory.mktemp("ev") / "chase.mp4")


# --- sound events -------------------------------------------------------------------------

@pytest.mark.parametrize("seed", [0, 1, 2])
def test_detects_each_planted_sound_event(tmp_path, seed):
    wav = write_wav(tmp_path / "s.wav", soundtrack(seed))
    events = detect_events(spectral_features(str(wav)))
    found = {(e["type"]) for e in events}
    assert found == set(EVENTS), events                      # every type, nothing extra
    for kind, t in EVENTS.items():
        e = next(e for e in events if e["type"] == kind)
        assert abs(e["t"] - t) <= 0.3, (kind, e["t"])
    music = next(e for e in events if e["type"] == "music")
    assert 115 <= music["bpm"] <= 125                         # planted at 120 BPM
    gun = next(e for e in events if e["type"] == "gunfire")
    assert gun["shots"] == 5


def test_no_events_in_ambience_and_speechlike_audio(tmp_path):
    rng = np.random.default_rng(5)
    n = SR * 20
    t = np.arange(n) / SR
    amb = rng.normal(0, 0.05, n) * (1 + 0.5 * np.sin(2 * np.pi * 0.2 * t))
    gate, i = np.zeros(n), 0
    while i < n:                                              # irregular "syllables"
        on, off = int(rng.uniform(0.08, 0.35) * SR), int(rng.uniform(0.05, 0.4) * SR)
        gate[i:i + on] = 1
        i += on + off
    speech = np.convolve(rng.normal(0, 1, n), np.ones(20) / 20, "same") * 0.2 * \
        np.convolve(gate, np.ones(400) / 400, "same")
    wav = write_wav(tmp_path / "neg.wav", np.clip(amb + speech, -1, 1))
    assert detect_events(spectral_features(str(wav))) == []


def test_fade_out_is_not_sudden_silence(tmp_path):
    x = np.random.default_rng(1).normal(0, 0.2, SR * 8)
    x[SR * 4:SR * 5] *= np.linspace(1, 0, SR)                # 1 s fade
    x[SR * 5:] = 0
    events = detect_events(spectral_features(str(write_wav(tmp_path / "f.wav", x))))
    assert not [e for e in events if e["type"] == "sudden_silence"]


def test_corroboration_downgrades_audio_only_hits():
    events = [{"type": "explosion", "t": 2.0, "duration": 0.5, "confidence": 0.8},
              {"type": "impact", "t": 6.0, "duration": 0.1, "confidence": 0.8},
              {"type": "siren", "t": 1.0, "duration": 3.0, "confidence": 0.9}]
    flash = np.zeros(20, dtype=np.float32)
    flash[4] = 1.0                                            # flash at 2.0 s (hop 0.5)
    out = corroborate(events, {"flash": flash, "motion": np.zeros(20, np.float32)}, 0.5)
    exp, imp, sir = out
    assert exp["confirmed"] is True and exp["confidence"] > 0.8
    assert imp["confirmed"] is False and imp["confidence"] < 0.8
    assert "confirmed" not in sir                             # not a transient: untouched


# --- profiles -----------------------------------------------------------------------------

def test_all_profiles_load():
    keys = list_profiles()
    assert {"generic", "gta", "call_of_duty", "fortnite", "minecraft"} <= set(keys)
    for k in keys:
        p = load_profile(k)
        assert p["categories"] and p["event_weights"]
    with pytest.raises(ConfigError):
        load_profile("not_a_game")


def test_categorize_rules():
    gta = load_profile("gta")
    chase = [{"type": "siren", "t": 1}, {"type": "engine_rise", "t": 3}]
    assert categorize(chase, 0.8, gta)["name"] == "Police chase"
    assert categorize([{"type": "siren", "t": 1}], 0.8, gta) is None      # siren alone isn't a chase
    boom = [{"type": "explosion", "t": 1, "confirmed": True}]
    assert categorize(boom, 0.6, gta)["name"] == "Vehicle destruction"
    low_motion = categorize(boom, 0.1, gta)                   # motion gates "Vehicle destruction"
    assert low_motion is None or low_motion["name"] != "Vehicle destruction"
    assert categorize([], 1.0, gta) is None


def test_game_profile_changes_interpretation(event_video, cfg, db):
    r = ingest_file(event_video, cfg, db)
    gta = analyze(r.media_id, cfg, db, game="gta")[0]
    assert gta["reasons"]["category"] == "Police chase"
    assert gta["reasons"]["title"]
    kinds = [e["type"] for e in gta["reasons"]["events"]]
    assert {"explosion", "gunfire", "siren", "engine_rise"} <= set(kinds)
    # the whole escalation is one clip: starts before the explosion, ends after the engine rev
    assert gta["start_s"] <= 5.5 and gta["end_s"] >= 19.0
    assert db.get_media(r.media_id)["game"] == "gta"
    generic = analyze(r.media_id, cfg, db, game="generic")[0]
    assert generic["reasons"]["category"] == "Explosive moment"
    # the impact at 3 s has no on-screen evidence: it never drives the story
    assert "impact" not in generic["description"]


# --- enhancement + licensing -------------------------------------------------------------

def test_builtin_sfx_are_original_and_registered(cfg):
    reg = ensure_builtin(cfg)
    assert set(reg) >= {"impact_low", "impact_soft", "whoosh", "riser"}
    assert all(e["license"] == "original" and e["verified"] for e in reg.values())
    register_sound(cfg, "mystery_song", __file__, "unknown", "downloaded somewhere")
    assert load_registry(cfg)["mystery_song"]["verified"] is False
    assert audio_sources_ok([{"name": "x", "license": "original"}])[0]
    assert not audio_sources_ok([{"name": "song", "license": "unknown"}])[0]


def test_zoom_filter_only_changes_frames_in_window(tmp_path):
    src = tmp_path / "pattern.mp4"
    ff("-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=3", "-c:v", "libx264", "-preset", "ultrafast", str(src))
    out = tmp_path / "zoom.mp4"
    ff("-i", str(src), "-vf", zoom_filter([1.0], 0.15, 640, 360), "-c:v", "libx264", "-preset", "ultrafast", str(out))

    def frame(path, t):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(path), "-frames:v", "1",
                              "-vf", "scale=160:90,format=gray", "-f", "rawvideo", "-"],
                             capture_output=True, check=True).stdout
        return np.frombuffer(raw, np.uint8).astype(int)
    assert np.abs(frame(src, 0.5) - frame(out, 0.5)).mean() < 2         # before: unchanged
    assert np.abs(frame(src, 1.05) - frame(out, 1.05)).mean() > 5       # during: zoomed
    assert np.abs(frame(src, 2.5) - frame(out, 2.5)).mean() < 2         # after: back to normal


def test_enhanced_render_passes_qa_and_records_audio(event_video, cfg, db, tmp_path):
    before = sha256(event_video)
    r = ingest_file(event_video, cfg, db)
    cand = analyze(r.media_id, cfg, db, game="gta")[0]
    rend = render_all_presets(cand["id"], cfg, db, ["landscape"], enhance=True)[0]
    assert rend["enhanced"] == 1
    names = {a["name"]: a["license"] for a in rend["audio_sources"]}
    assert names["source recording"] == "user-recording" and names.get("impact_low") == "original"
    assert check_render(rend, cfg, db)["status"] in ("passed", "warning")
    plain = render_all_presets(cand["id"], cfg, db, ["vertical"], enhance=False)[0]
    assert plain["enhanced"] == 0 and [a["name"] for a in plain["audio_sources"]] == ["source recording"]
    assert sha256(event_video) == before


def test_export_blocks_unverified_audio(event_video, cfg, db, tmp_path):
    r = ingest_file(event_video, cfg, db)
    cand = analyze(r.media_id, cfg, db, game="gta")[0]
    rend = render_all_presets(cand["id"], cfg, db, ["landscape"], enhance=True)[0]
    check_render(rend, cfg, db)
    db.set_candidate_status(cand["id"], "approved")
    ok = export_approved(cfg, db, tmp_path / "ok")
    assert len(ok["exported"]) == 1 and ok["exported"][0]["category"] == "Police chase"
    assert ok["exported"][0]["draft_metadata"]["title"]
    # simulate a render that used a sound with no verified licence
    db.conn.execute("UPDATE renders SET audio_json = ? WHERE id = ?",
                    ('[{"name": "random_song", "license": "unknown"}]', rend["id"]))
    db.conn.commit()
    blocked = export_approved(cfg, db, tmp_path / "blocked")
    assert blocked["exported"] == []
    assert "unverified audio licence" in blocked["skipped"][0]["reason"]
