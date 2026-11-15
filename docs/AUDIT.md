# Phase 0 — Environment Audit

Date: 2026-11-15 · Reproduce with: `python3 scripts/audit_env.py [video ...]`

> **Note:** this audit ran in a cloud dev container, **not** on the machine that will
> eventually run the engine. The engine is designed to run locally on your machine, so run
> `scripts/audit_env.py` there too. It uses only the standard library, so it works before
> anything is installed.

## 1. Findings

| Area | Result | Impact |
|---|---|---|
| OS | Linux x86_64, glibc 2.39 | — |
| Python | 3.13.18 | Fine. Target ≥ 3.11. |
| CPU | 4 logical cores, Xeon @ 2.1 GHz | Rendering is CPU-bound. |
| Memory | 15.7 GB, no swap | Enough. Analysis must still stream frames, not load whole videos. |
| Disk | ~30 GB free | Fine for a prototype. Renders must be cleaned up or kept under a size limit. |
| GPU | **None** (no NVIDIA, no `/dev/dri`) | No hardware encode or GPU inference. NVENC/QSV/VAAPI are compiled into FFmpeg but can't be used here. |
| FFmpeg | 6.1.1 with ffprobe, libx264, aac, libass | Covers everything the prototype needs. |
| FFmpeg filters | `scdet`, `blackdetect`, `silencedetect`, `freezedetect`, `loudnorm`, `ebur128`, `subtitles`/`ass` all present | Scene detection, quality checks, loudness normalisation and subtitle burn-in can all be done in FFmpeg. |
| Fonts | DejaVu, Inter, FreeSans | Subtitles can render without bundling fonts. |
| numpy / Pillow / PyYAML / pydantic | Installed (2.5.3 / 12.3.0 / 6.0.3 / 2.13.5) | Config loading and validation are covered. |
| OpenCV (`cv2`) | **Not installed.** `opencv-python-headless` downloads fine from PyPI. | Install it in Phase 1/2. |
| pytest, scipy, scenedetect | Not installed. All on PyPI. | Install as needed. |
| Speech-to-text | `faster-whisper`/`whisper` not installed. **huggingface.co is blocked by this container's network policy**, so model weights can't be downloaded here. | See Blocker B2. |
| Sample footage | **None.** No `.mp4`/`.mov` anywhere on the filesystem. The repo holds only a README. | See Blocker B1. |

### Benchmark (synthetic 1080p60, 10 s, with audio)

| Operation | Wall time | Speed |
|---|---|---|
| 16:9 encode, x264 `veryfast` CRF 20 | 5.7 s | ~1.75× realtime |
| 16:9 encode, x264 `medium` CRF 20 | 11.1 s | ~0.9× realtime |
| 9:16 crop + scale to 1080×1920 + `loudnorm`, `veryfast` | 5.7 s | ~1.75× realtime |
| Analysis decode + `scdet` at 960 px width | 1.5 s | ~6.7× realtime |

These are synthetic `testsrc2` frames. Real gameplay is harder to encode, so expect lower speeds.

**What this means:**
- Analysis must run on downscaled frames (about 480–960 px wide), sampled at a reduced rate (for example 10 fps for motion), and should decode each file **once**, sharing the frames across detectors.
- Only selected clips get rendered. Rendering the whole source is too slow on this CPU.
- Default render preset: `veryfast`, CRF ~20. A `medium` "final" preset can be selected in config.
- Hardware encoding is an optional config switch, detected at runtime and off by default.

## 2. Blockers

| # | Blocker | Status / proposed resolution |
|---|---|---|
| **B1** | **No user gameplay footage available.** Phase 5 requires real footage. | Development uses synthetic FFmpeg-generated test videos (scene cuts, motion bursts, loud audio peaks, black frames) with known ground truth, so unit tests can measure detection accuracy. **Real footage is needed to validate quality.** Please supply 2–3 MP4/MOV recordings (ideally 2–10 min, with game audio and commentary if you record any). Large files should stay out of git. Either put them in a local `footage/` directory (git-ignored) or tell me where they live. |
| **B2** | **Whisper weights can't be downloaded in this container** (Hugging Face is blocked). | Transcription becomes an **optional, pluggable detector**. The pipeline works without it. On your local machine `faster-whisper` (free, offline after the first model download, runs on CPU) should work. Alternatively, Hugging Face can be allow-listed in this environment's network settings. No paid APIs. |
| B3 | No GPU | Not a blocker. CPU path only, as benchmarked above. |

## 3. Decisions taken in Phase 0

1. **FFmpeg CLI is the media backend**, called through `subprocess`. It is already installed, all the filters we need are present, and the commands are easy to reproduce and debug. No MoviePy, which is slow and has heavy dependencies.
2. **OpenCV (headless) + numpy for frame analysis**: motion, visual activity and reframing saliency.
3. **SQLite (stdlib `sqlite3`)** for the media library and candidate clips. No server.
4. **YAML config + pydantic validation** for editing presets.
5. **Originals are never modified or copied.** The database stores the absolute path, size, mtime and a fast content fingerprint (hash of the first and last few MB plus the size). Every stage reads originals read-only. Output goes to a separate `workspace/` directory.
6. Nothing is uploaded or published. YouTube work is out of scope until the editing pipeline is proven.
