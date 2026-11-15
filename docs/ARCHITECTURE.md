# Architecture — Vice City Clip Engine (Phase 0 prototype)

Local-first pipeline: **ingest → analyse → score candidates → render → QA → human review.**
Each stage is its own module. Stages talk to each other only through the SQLite database and
files in `workspace/`, so any stage can be re-run on its own.

```
             originals (read-only, never copied)
                         │
  ┌──────────┐   ┌───────▼────────┐   ┌────────────┐   ┌──────────┐   ┌──────┐   ┌────────┐
  │  config  │──▶│ 1 ingest       │──▶│ 2 analyse  │──▶│ 3 select │──▶│4 edit│──▶│ 5 QA   │──▶ review
  │  (YAML)  │   │ probe, thumbs, │   │ signals →  │   │ fuse,    │   │render│   │checks, │   (HTML/CLI)
  └──────────┘   │ fingerprint    │   │ timelines  │   │ score,   │   │9:16, │   │report  │
                 └───────┬────────┘   └─────┬──────┘   │ explain  │   │16:9  │   └───┬────┘
                         └──────────────────┴──────────┴────┬─────┴───┴──┬───┘───────┘
                                                      SQLite (library.db) + workspace/
```

## Package layout (planned)

```
clipengine/
  config.py          # load + validate YAML presets (pydantic)
  db.py              # SQLite schema and data access, nothing else
  media/
    probe.py         # ffprobe wrapper → typed metadata
    ffmpeg.py        # safe command builder/runner (never writes to source paths)
    thumbs.py        # thumbnails / contact sheet
  ingest.py          # Phase 1: register file, fingerprint, metadata, thumbnails
  analysis/          # Phase 2: each detector → per-second signal timeline (0..1)
    frames.py        # single decode pass, downscaled + subsampled frame iterator
    scenes.py        # scene-change score (scdet / histogram diff)
    motion.py        # optical-flow / frame-difference magnitude
    activity.py      # visual activity: edge density, saturation, flashes
    audio.py         # RMS / loudness peaks, onset detection, silence
    speech.py        # OPTIONAL transcription (faster-whisper); no-op if unavailable
  select/            # Phase 2: turn signals into candidate clips
    fuse.py          # weighted fusion + temporal smoothing
    candidates.py    # peak picking, padding, merging, min/max duration, NMS
    explain.py       # human-readable reason + confidence
  edit/              # Phase 3
    reframe.py       # saliency/motion-tracked crop path for 9:16 (smoothed)
    subtitles.py     # ASS generation, safe-area positioning per aspect
    render.py        # build the ffmpeg graph: trim, reframe, fades, loudnorm, encode
  qa/                # Phase 4
    checks.py        # black frames, freeze, silence/missing audio, A/V drift,
                     # aspect/resolution, decodability, subtitle safe area, cut sanity
  review/            # human review: static HTML page of clips + scores + QA results
  cli.py             # `clipengine ingest|analyse|candidates|render|qa|review|run`
config/
  default.yaml       # detection weights, durations, render presets
  presets/*.yaml     # e.g. shorts_vertical.yaml, horizontal_1080p.yaml
tests/               # pytest; synthetic fixture videos generated with ffmpeg lavfi
scripts/audit_env.py
workspace/           # git-ignored: library.db, thumbs/, analysis/, renders/, reports/
```

## Key design points

**Single decode pass.** `analysis/frames.py` decodes each source once, at reduced resolution
and frame rate. It feeds motion, activity and reframing saliency at the same time. Audio is
extracted once to 16 kHz mono PCM and shared by the audio and speech detectors. Analysis results
are cached in `workspace/analysis/<fingerprint>/` as `.npz` files, so changing scoring weights
doesn't trigger a re-decode.

**Scene changes are context, not highlights.** On its own a scene cut carries low weight. In
gameplay, a cut usually means a menu, a loading screen or a mission transition. Cuts are used to
(a) snap clip boundaries so a clip doesn't start mid-transition, and (b) penalise windows that
contain loading screens or menus (low motion, static frames). An interesting moment needs
agreement between signals, for example sustained motion together with an audio peak or speech
energy.

**Scoring model (v0, rule-based and explainable).** Each detector produces a 0–1 signal per
second, normalised per video with robust percentiles. The steps are:
1. Fused score = weighted sum, smoothed over a 2–4 s window. Weights come from config.
2. Peak picking with minimum separation.
3. Each peak grows into a window bounded by `min/max_duration`, with lead-in and lead-out
   padding, snapped to nearby scene cuts or silences.
4. Overlapping windows are merged or suppressed.
5. Confidence = calibrated fused score, plus a bonus when several signals agree.
6. The reason text lists the top contributing signals, e.g. "audio peak +18 dB over baseline
   at 02:14, sustained high motion for 6 s, speech: 'oh no no no'".

Later phases can replace the rule-based scoring with a learned model trained on the user's
accept/reject decisions from the review page.

**Intelligent 9:16 reframing.** For every analysed frame, compute a saliency centroid
(motion-weighted, with a weak centre prior and HUD regions masked out via config). Smooth the
crop path with a dead-zone and a velocity limit so the camera doesn't jitter, and clamp it to
the frame. Render with a time-varying `crop` expression, or with per-segment crops through
`sendcmd`. A **blurred-background "fit" mode** keeps the full 16:9 frame inside a 9:16 canvas and
is the fallback when there is no clear subject or when HUD elements (minimap, ammo, wanted
level) would be cut off. The choice is configurable per preset.

**Rendering.** One ffmpeg invocation per clip/aspect: accurate seek → trim → reframe/scale →
optional ASS burn-in → short fade-in/fade-out → two-pass `loudnorm` (measure, then apply,
target −14 LUFS) → libx264 (yuv420p, constant frame rate, `+faststart`) + AAC 48 kHz. Encoding
parameters come only from presets, which keeps output consistent.

**QA gates.** Each render is probed and checked. A failing render is marked `qa_failed` with
reasons and still shows up in the review page. Nothing is deleted automatically.

## Data model (SQLite)

- `media(id, path, fingerprint UNIQUE, size_bytes, mtime, container, duration_s, width, height, fps, video_codec, audio_codec, has_audio, created_at)`
- `thumbnails(media_id, t_s, path)`
- `analysis_runs(id, media_id, detector, version, params_json, cache_path, created_at)`
- `candidates(id, media_id, start_s, end_s, duration_s, description, confidence, reason_json, status[new|approved|rejected], created_at)`
- `renders(id, candidate_id, preset, path, width, height, size_bytes, render_s, qa_status, qa_json, created_at)`

## Dependencies

| Dependency | Why | Source |
|---|---|---|
| FFmpeg ≥ 6 (ffprobe, libx264, libass) | probe, decode, filters, encode | system package |
| Python ≥ 3.11 | runtime | system |
| numpy | signal processing | PyPI |
| opencv-python-headless | motion, saliency, frame analysis | PyPI |
| PyYAML, pydantic | configuration presets | PyPI |
| pytest | tests | PyPI (dev) |
| faster-whisper | *optional* transcription | PyPI + one-time model download |

No paid APIs. No network access is needed at runtime, apart from the optional one-time Whisper
model download.

## Incremental plan

| Step | Scope | Exit criterion |
|---|---|---|
| 0 | Audit and architecture (this document) | Findings documented ✅ |
| 1 | `config`, `db`, `media/probe`, `ingest`, thumbnails, CLI `ingest`, tests with synthetic fixtures | MP4/MOV ingested, metadata in SQLite, duplicates detected by fingerprint, originals untouched |
| 2a | Frame/audio extraction and individual detectors | Each detector finds its injected events in the synthetic fixtures |
| 2b | Fusion, candidates, explanations | ≥ 3 candidates with reasons. Precision/recall measured on the fixtures |
| 3 | Rendering 16:9, 9:16 (fit + tracked), loudnorm, subtitles | Renders pass ffprobe validation |
| 4 | QA checks and report | Corrupted or black-frame renders deliberately created in tests get flagged |
| 5 | Run on real footage, benchmarks, review page | Metrics report: time, storage, accuracy against hand-labelled moments |
