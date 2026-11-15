# Toolskalika — Vice City Clip Engine

A local-first prototype for automated gameplay video editing. It takes your own recordings,
finds highlight candidates, renders 9:16 and 16:9 clips, runs QA on them and presents them for
human review. Nothing is uploaded automatically.

**Status:** Phase 0 (environment audit and architecture) is complete.

- [docs/AUDIT.md](docs/AUDIT.md): environment findings, benchmarks, blockers
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): module layout, data model, incremental plan

## Audit your machine

```bash
python3 scripts/audit_env.py                  # hardware, FFmpeg, Python modules
python3 scripts/audit_env.py path/to/clip.mp4 # also probe sample footage
```

Requirements: Python ≥ 3.11 and FFmpeg ≥ 6 (with ffprobe, libx264, libass).
