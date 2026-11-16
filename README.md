# Toolskalika — Vice City Clip Engine (local beta)

Turns your own gameplay recordings into highlight clips on your computer. It
detects candidate moments, renders 16:9 and 9:16 clips, runs quality checks on
them, and lets you approve or reject each one in a local web page.
**Nothing is uploaded or published.** Original recordings are only read: never
modified, moved or copied.

```
recording ──▶ ingest ──▶ analyse ──▶ candidates ──▶ render 16:9 + 9:16 ──▶ QA ──▶ review ──▶ export
             metadata    5 detectors   start/end,      loudness, fades,         black, frozen,   approve/
             fingerprint               confidence,     optional subtitles       audio, aspect,   reject
             thumbnails                reasons                                  duration, decode
```

## Requirements

- Python ≥ 3.11
- FFmpeg ≥ 6 with ffprobe, libx264 and libass
- `pip install numpy PyYAML` (plus `pytest` for the tests)

Check a machine with `python3 scripts/audit_env.py`.

## Quick start

```bash
# one step: ingest, analyse, render the top 3 clips in both formats, run QA
python3 -m clipengine run ~/Videos/gameplay.mp4

# review, approve or reject, and export in the browser
python3 -m clipengine serve          # → http://127.0.0.1:8765/
```

## Commands

| Command | What it does |
|---|---|
| `ingest PATH...` | Register files or folders (MP4, MOV, WebM, MKV). Duplicates are detected by content fingerprint. |
| `analyze ID... \| all` | Detect candidates. Features are cached, so re-scoring after a config change is instant. `--force` re-decodes. |
| `render CAND_ID...` or `render --media ID --top N` | Render landscape and vertical clips, then run QA. |
| `qa all \| RENDER_ID...` | Re-run the quality checks (`-v` shows every check). |
| `run PATH... [--top N]` | Ingest, analyse, render and QA in one step. |
| `list [-c]` | List recordings (`-c` also lists candidates). |
| `serve [--port]` | Local review dashboard. |
| `export [--dest DIR]` | Copy approved clips that passed QA (hard-linked when possible) plus `manifest.json`. |
| `report` | Processing time, CPU, peak memory, render speed and storage use. |

Global options: `--workspace DIR` (default `./workspace`) and `--config my.yaml`.

## Configuration

`config/default.yaml` holds every setting: detector weights, thresholds, clip
durations, render presets (size, `fit` / `crop` / `blur`), fps, fades, loudness
target, encoder settings, subtitles and QA limits. To change something, put only
the keys you want to override in your own file and pass it with `--config`.

Subtitles: place an `.srt` with the same name next to the recording
(`match.mp4` + `match.srt`). It is re-timed and burned into each clip.

## How detection works

Five independent detectors each score every half-second from 0 to 1:

| Detector | Measures |
|---|---|
| `audio_peak` | Loudness above the recording's running 30 s baseline (+15 dB scores 1) |
| `loudness_change` | Sudden rises in loudness within 1 s |
| `frame_diff` | Pixel change between frames, relative to this recording |
| `visual_activity` | Share of the frame changing, plus brightness flashes |
| `scene_change` | Hard cuts (histogram jumps that stand out from the local level) |

The scores are smoothed and combined with configurable weights. Near-static
stretches (menus, loading screens) are penalised. Peaks become clips with lead-in
and lead-out, limited to 6–30 s, aligned to nearby scene cuts, and never
overlapping. Confidence goes up when several detectors agree. A scene cut on
its own never produces a clip. Every candidate records its reasons, for example
"audio +36 dB above the running baseline" or "4 detectors agree".

## Layout

```
clipengine/
  config.py   db.py   ffmpeg.py   metrics.py
  ingest.py                       # Phase 1
  detect/ signals.py detectors.py scoring.py   # Phase 2
  render.py                       # Phase 3
  dashboard/ server.py index.html # Phase 4 (standard library HTTP server)
  qa.py                           # Phase 5
  export.py   report.py   cli.py
config/default.yaml
tests/                            # pytest, synthetic footage with planted events
docs/                             # audit, architecture, beta notes
```

## Tests

```bash
python3 -m pytest -q
```

The tests generate synthetic recordings that contain known action bursts and
scene cuts, then check that each one is detected. They also feed deliberately
broken files (black, frozen, silent, truncated, wrong aspect) to QA and check
that every one is flagged. On top of that they cover the dashboard API and the
full CLI run, and confirm that originals are byte-identical afterwards.

See [docs/BETA.md](docs/BETA.md) for results, measurements and known limitations.
