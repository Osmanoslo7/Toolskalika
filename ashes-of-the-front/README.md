# Ashes of the Front: animation engine

An original military animated series. This repo is the production pipeline: a
manifest-driven system that turns character, environment and shot data into
1080×1920 / 24 fps episodes.

Read [CLAUDE.md](CLAUDE.md) for the project conventions.

## Status

| Phase | Scope | State |
|---|---|---|
| 1 | Project foundation: structure, schemas, config, validation | **done** |
| 2 | Character pipeline: layered art, 2D rig, expressions, consistency checks | next |
| 3 | Blender animation engine: keyframes, camera, parallax, lighting, effects | not started |
| 4 | Audio sync and rendering: dialogue, FFmpeg encode, output checks | not started |
| 5 | Pilot: 6-second Elias Vale test in an armoured vehicle | not started |

Phase 1 covers manifests and validation only. There is no art, rig or renderer yet.

## Requirements

- Python 3.11 or newer
- `jsonschema` (installed from `requirements.txt`)
- Blender 4.x and FFmpeg are needed from Phases 3 and 4. `./ashes doctor` reports whether they are present.

```bash
cd ashes-of-the-front
python3 -m pip install -r requirements.txt
./ashes doctor
./ashes validate
cd pipeline && python3 -m unittest discover -s tests -t .
```

## Folder layout

```
config/project.toml     video size, fps, episode length
schemas/                JSON Schemas: asset.schema.json, shot.schema.json
characters/<id>/        asset.json (+ layers/, faces/, mouths/, rig/ when they exist)
environments/<id>/      asset.json
props/<id>/             asset.json
effects/<id>/           asset.json
audio/                  dialogue, narration, radio, sfx, music
shots/<id>/shot.json    one shot manifest per shot
pipeline/ashes/         Python package (CLI, validation, dependency checks)
pipeline/tests/         unit tests
```

## Manifests

**Asset** (`asset.json`): `id`, `type` (character, environment, prop, effect), `name`,
`version`, `status` (draft, review, approved), `description`, `layers` (each with
`name`, `file`, `z`), plus a `character` section for characters. The character
section holds `identity` (age, role, and optional fields), `expressions`
(name → image file), `mouth_shapes` (viseme → image file) and an optional `rig`.

**Shot** (`shot.json`): `duration_seconds`, `fps`, `width`, `height` (must match
`config/project.toml`), the `characters` and `environment` used, `camera`
keyframes, `layers` with keyframes and parallax, `effects` (smoke, dust,
muzzle_flash, light_sweep, shake, vignette, flicker), `dialogue`, `audio` cues
and `output.file`. All times are seconds from the start of the shot.

## What validation checks

Schema errors, duplicate ids, folder/id mismatches, asset type in the wrong
folder, unknown asset or character references, speakers not in the shot,
keyframe times out of order or outside the shot, durations that don't land on
whole frames, wrong resolution or fps, and file paths that escape their folder.

A missing file is an **error** for an approved asset and a **warning** for a
draft. Missing shot audio is always a warning.

## Adding a character

1. Create `characters/<id>/asset.json`. Use a lowercase snake_case id that matches the folder.
2. Fill in `character.identity` from the approved design only.
3. Run `./ashes validate`.

## Known limits

- Validation is manifest-level. It doesn't check image content, rig correctness or animation quality. Those come in Phases 2–3.
- Consistency checking (is this character still the same?) is a Phase 2 feature. Phase 1 only ensures identity fields exist and are typed.
- Blender and FFmpeg are not used yet, so `./ashes doctor` will mark them as missing until those phases.
