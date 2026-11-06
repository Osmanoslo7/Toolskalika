# Ashes of the Front: animation engine

An original military animated series. This repo is the production pipeline: a
manifest-driven system that turns character, environment and shot data into
1080×1920 / 24 fps episodes.

Read [CLAUDE.md](CLAUDE.md) for the project conventions. It holds the full
artwork, rig, viseme and approval rules.

## Status

| Phase | Scope | State |
|---|---|---|
| 1 | Project foundation: structure, schemas, config, validation | **done** |
| 2 | Character pipeline: artwork convention, rig, face and visemes, consistency and approval | **done** (validated, see below) |
| 3 | Blender animation engine: rig import, keyframes, camera, parallax, lighting, effects | not started |
| 4 | Audio sync and rendering: dialogue, FFmpeg encode, output checks | not started |
| 5 | Pilot: 6-second Elias Vale test in an armoured vehicle | not started |

**What Phase 2 does not include:** no character art has been created or approved.
The four characters are still drafts: they have canvases, rigs and face presets,
but no layer PNGs. Nothing is approved, so consistency checks have no approved
reference yet. Blender does not read these rigs yet; Phase 3 will add that.

## Requirements

- Python 3.11 or newer
- `jsonschema` and `Pillow` (from `requirements.txt`)
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
config/project.toml       video size, fps, episode length, artwork thresholds
schemas/                  asset (v2), rig (v1), face (v1), dialogue (v1), approval (v1), shot (v1)
templates/                humanoid_rig.json and face_default.json: starting points
characters/<id>/          asset.json, rig.json, face.json, layers/*.png
                          (+ approval.json and history/v<n>/ once approved)
environments/ props/ effects/   asset.json per asset
dialogue/                 one viseme schedule per spoken line
audio/                    dialogue, narration, radio, sfx, music
shots/<id>/shot.json      one shot manifest per shot
pipeline/ashes/           Python package
pipeline/tests/           unit and integration tests
```

## Creating a character

1. Copy the templates into the character folder, replacing `CHARACTER_ID`:
   ```bash
   mkdir -p characters/<id>/layers
   sed "s/CHARACTER_ID/<id>/" templates/humanoid_rig.json > characters/<id>/rig.json
   sed "s/CHARACTER_ID/<id>/" templates/face_default.json > characters/<id>/face.json
   ```
2. Write `asset.json` (schema v2) with a `character.canvas` and `character.identity`.
3. Export each layer as an RGBA PNG at canvas size into `layers/<name>.png`.
4. Attach each layer in `rig.json` and list it in `draw_order`. Map all 14 visemes in `face.json`.
5. `./ashes validate` until there are no errors.
6. When the user approves the art, set `status` to `approved`, bump `version`, and run
   `./ashes approve <id>`.

The bone offsets in `templates/humanoid_rig.json` are placeholders. Set them per
character from the approved art.

## Checks

`./ashes validate` checks, among other things:

- **Schemas** for every manifest, including rig, face, dialogue and approval files.
- **Artwork:** valid RGBA PNG, canvas size, padding, transparency, no background fill, pivots on the canvas, `layers/<name>.png` naming.
- **Rig:** one root, no missing parents, no cycles, attachments that exist, draw order that matches attachments, valid IK chains and rotation limits, deform weights summing to 1.
- **Face:** jaw bone exists, sprite references exist, all 14 visemes mapped (error once approved, warning while drafting).
- **Dialogue:** integer frames, first event at frame 0, strictly increasing, inside the duration, visemes the character has.
- **Approval:** approved characters have a record, the record's snapshots are intact, approved art is unchanged, and version numbers only go up.

Errors block rendering. Warnings are for drafts that are still in progress.

## Consistency and approval

```bash
./ashes approve elias_vale       # records the current art as the next approved version
./ashes consistency elias_vale   # compares current art with the approved version
```

- `approve` never edits artwork. It copies the layers into `history/v<n>/` and appends to `approval.json`.
- `consistency` writes `build/consistency/<id>/report.json` and one `*.changed.png` mask per changed layer.
- The SHA-256 hash decides whether art changed. The perceptual hashes (aHash and dHash, out of 64 bits) and the pixel counts are for a person to judge.

## Known limits

- **No art yet.** The pipeline works on synthetic test PNGs only. Real layers are the user's to produce and approve.
- **No Blender import yet.** `rig.json` is designed to map to Blender armatures (bone parent, local transform, length, constraints) in Phase 3. That mapping is not implemented or tested.
- **Shape of the check, not the look.** Validation confirms the convention and the file structure. It does not judge whether the drawing is good.
- **Perceptual hashes are coarse.** An 8×8 hash can miss small changes. That's why a changed file is always an error and the hash is only advisory.
