# Beta implementation notes

Status: phases 1–5 are implemented and tested. 31 automated tests pass.

## Plan as executed

| Phase | Module(s) | Done when | Status |
|---|---|---|---|
| 1 Ingestion | `config`, `db`, `ffmpeg`, `ingest`, `cli ingest` | Metadata in SQLite, duplicates caught, thumbnails, originals untouched | ✅ 7 tests |
| 2 Detection | `detect/signals`, `detect/detectors`, `detect/scoring` | Planted events found, reasons and confidence stored | ✅ 8 tests |
| 3 Editing | `render` | 1920×1080 and 1080×1920, −14 LUFS ±1.5, fades, subtitles, thumbnails | ✅ 3 tests |
| 4 Review | `dashboard/server`, `dashboard/index.html`, `export` | Browse, preview, approve or reject, export | ✅ 4 tests + browser check |
| 5 QA | `qa` | Deliberately broken files are flagged | ✅ 6 tests |

**Dependencies:** FFmpeg, numpy, PyYAML, and pytest for development. No paid APIs, no network access at runtime.

**Main risks:**
- Rule-based detection may not suit every game.
- CPU-only rendering limits throughput.
- Speech transcription is not included yet.

## Changes from the Phase 0 architecture, and why

| Change | Reason |
|---|---|
| No OpenCV | Frame difference, activity and scene cuts are computed with numpy on grayscale frames piped from FFmpeg. That removes a heavy dependency (rule 9), and FFmpeg does the downscaling anyway. |
| Dashboard uses `http.server` from the standard library | Enough for a single-user local tool. No web framework dependency. |
| Config is plain YAML dicts with explicit checks, not pydantic | Fewer moving parts. Invalid weights, sizes and modes raise `ConfigError`. |
| WebM and MKV accepted alongside MP4 and MOV | Common recording formats, and the licensed test footage is WebM. |
| 9:16 uses a centre crop (`crop`) or a blurred-background fit (`blur`) | The beta brief asks for simple cropping first. Subject tracking comes later. |
| Speech transcription not included | Not mandatory per the brief. The Whisper model host is blocked in the dev container. Subtitles come from a sidecar `.srt`. |

## Measurements (dev container: 4 vCPU Xeon 2.1 GHz, 15.7 GB RAM, no GPU)

3-minute 1080p60 recording with 12 planted action events, `run --top 3`:

| Metric | Result |
|---|---|
| End-to-end wall time (ingest, analyse, 6 renders, QA) | 39 s |
| Analysis speed | 13.7× realtime (13.2 s for 180 s), peak 115 MB RAM |
| Render speed per preset | ≈2× realtime (7 s clip: 2.8 s landscape, 3.7–4.4 s vertical) |
| Peak memory while rendering | 438 MB (FFmpeg) |
| QA | 6/6 passed |
| Loudness of renders | −14.4 LUFS (target −14) |
| Detection precision | 10/10 candidates overlap a planted event |
| Detection recall | 10/12 events. The two misses come only from the `max_candidates: 10` cap. |
| Storage | 9.7 MB for 6 renders, about 100 KB of database and thumbnails. Originals referenced, not copied. |

Planted-event accuracy only proves the detectors work as designed. It does not
show that they pick what a human finds interesting. That needs real gameplay and
human labels (see below).

## Acceptance criteria

| Criterion | Evidence |
|---|---|
| Import a gameplay recording | `ingest`, `run`, dashboard import box; `test_ingest.py` |
| Analyse it | `analyze`; `test_detect.py::test_analyze_finds_planted_events` |
| ≥ 3 candidates when suitable highlights exist | 10 on the 3-minute benchmark. If fewer than 3 clear the threshold, it is relaxed step by step down to a floor, and those clips are labelled as below-threshold. A recording with no action yields none rather than invented clips. |
| Landscape and vertical renders | `test_render_both_formats_and_pass_qa` |
| Outputs pass QA | All renders pass; broken files fail (`test_qa_flags_*`) |
| Preview, approve or reject | Dashboard; `test_dashboard_import_review_render_export` |
| Originals unchanged | SHA-256 before and after in the ingest, render, dashboard and CLI tests |

## Known limitations

- **No subject tracking** for vertical clips. A centre crop can cut off HUD or action at the frame edges. The `blur` mode keeps the whole frame.
- **Detection is heuristic.** Weights are hand-set defaults. Approve and reject decisions are stored, so the weights can be tuned (or learned) from them later.
- **One job at a time** in the dashboard worker, and renders are sequential.
- **No transcription.** Subtitles only come from an `.srt` next to the recording.
- **The QA "frozen" check** can warn on legitimately calm scenes, such as menus or standing still. It fails a clip only when more than 50% of it is frozen.
