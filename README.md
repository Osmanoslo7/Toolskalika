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

## Audio intelligence and game profiles (Beta 0.2)

```bash
python3 -m clipengine run recording.mp4 --game gta --enhance
python3 -m clipengine profiles -v        # generic, gta, call_of_duty, fortnite, minecraft
python3 -m clipengine sounds             # sound assets and their licences
```

- **Sound events** are detected from the audio signal: explosions, gunfire, impacts,
  sirens, engine revs, sudden silences, and music with its tempo. Hits are checked
  against on-screen flashes and motion. A bang with nothing on screen is marked
  "audio only (could be a mic pop)" and is not allowed to shape the clip.
- **Game profiles** (`config/game_profiles/*.yaml`) weight those events per game and
  name the clip. The same footage reads as "Police chase: explosion → gunfire →
  siren → engine rise" under GTA, and as "Explosive moment" under the generic
  profile. Each clip also gets a title idea.
- **Clip editing follows the action.** A clip never cuts a sound event in half,
  keeps a 1 s lead-in, and joins action separated by short lulls into one clip.
- **Enhancement** (`--enhance`, or the dashboard checkbox) adds a subtle impact
  sound 10 dB under the game audio and a brief 8% punch-in zoom on confirmed hits,
  at most 3 per clip.
- **Licensing:** the built-in effects are synthesised locally (original, no
  restrictions). Every render records each sound it contains along with its
  licence. Export refuses any clip that contains a sound whose licence is unknown.
  Register your own sounds with
  `sounds add NAME PATH --license cc0|licensed|youtube-audio-library|original|unknown`.

## Commands

| Command | What it does |
|---|---|
| `ingest PATH... [--game G]` | Register files or folders (MP4, MOV, WebM, MKV). Duplicates are detected by content fingerprint. |
| `analyze ID... \| all` | Detect candidates. Features are cached, so re-scoring after a config change is instant. `--force` re-decodes. |
| `render CAND_ID...` or `render --media ID --top N` | Render landscape and vertical clips, then run QA. |
| `qa all \| RENDER_ID...` | Re-run the quality checks (`-v` shows every check). |
| `run PATH... [--top N] [--game G] [--enhance]` | Ingest, analyse, render and QA in one step. |
| `profiles [-v]` / `sounds [add ...]` | List game profiles / list or register sound assets and their licences. |
| `list [-c]` | List recordings (`-c` also lists candidates). |
| `serve [--port]` | Local review dashboard. |
| `export [--dest DIR]` | Copy approved clips that passed QA (hard-linked when possible) plus `manifest.json`. |
| `report` | Processing time, CPU, peak memory, render speed and storage use. |

Global options: `--workspace DIR` (default `./workspace`) and `--config my.yaml`.

## Configuration

`config/default.yaml   config/game_profiles/*.yaml` holds every setting: detector weights, thresholds, clip
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
  intelligence/ audio_events.py profiles.py sfx.py   # Beta 0.2 audio + game intelligence
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
