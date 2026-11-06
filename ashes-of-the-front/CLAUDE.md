# Ashes of the Front: project conventions

These rules apply to every change in this project. Read them before editing anything here.

## What this is

An original fictional military animated series. Format: 1080×1920 vertical, 24 fps, 3–5 minute episodes. Style: hybrid of hand-inked graphic-novel panels and fully animated action. Palette: black, white, graphite, restrained red.

Pipeline: 2D skeletal characters and 2.5D layered environments, assembled in Blender through Python, encoded and mixed with FFmpeg.

## Layout

- `config/project.toml`: video, episode and artwork settings. The only home for them.
- `schemas/`: versioned JSON Schemas (asset v2, rig v1, face v1, dialogue v1, approval v1, shot v1).
- `characters/<id>/`: `asset.json`, `rig.json`, `face.json`, `layers/*.png`, plus `approval.json` and `history/` once approved.
- `environments/`, `props/`, `effects/`: `<folder>/<id>/asset.json` and its files.
- `dialogue/*.json`: viseme schedules for spoken lines, one per line.
- `audio/`: dialogue, narration, radio, sfx, music. Shot audio paths are relative to the project root.
- `shots/<id>/shot.json`: one shot manifest per shot.
- `templates/`: starting points for new rigs and faces. Copy them and replace `CHARACTER_ID`.
- `build/`, `renders/`: generated output, git-ignored, never edited by hand.
- `pipeline/ashes/`: the Python package. `pipeline/tests/`: its tests. Entry point: `./ashes`.

## Artwork convention

Applies to every layer PNG.

1. **Format:** RGBA PNG, 8-bit. RGB or palette images are rejected.
2. **Canvas:** every layer of a character is exactly `character.canvas.width × height` (1024×1536 for the current cast). A layer of a different size is an error.
3. **Coordinates:** pixels, origin top-left, y down. `canvas.root` is the character's origin (the hip joint). Rig translations are relative to it.
4. **Pivots:** each layer declares a `pivot` in canvas pixels. A pivot outside the canvas, including its edges, is an error.
5. **Naming:** a layer's `name` is snake_case and its file is `layers/<name>.png`, exactly. Anything else is an error.
6. **Padding:** all visible pixels sit at least `padding_px` (8) inside the canvas edge. Content touching the padding is an error.
7. **Transparency:** at least `min_transparent_fraction` (10%) of the canvas is fully transparent.
8. **No background:** one opaque colour covering more than `max_background_fraction` (50%) of the canvas is a background fill and is an error. Layers are cut-outs, not pictures.
9. **File integrity:** the file must be a valid PNG. Corrupt files and files that only look like PNGs are errors.
10. **Paths:** layer and reference paths are relative and stay inside the character folder. Absolute paths and `..` escapes are errors and are never read.

## Rig convention (`rig.json`)

- Versioned: `schema_version` 1. Coordinates are character-relative pixels. Rotation is in degrees.
- Exactly one root bone (`parent: null`). Every other bone names an existing parent. Cycles are errors.
- Each bone's `transform` is local to its parent (`x`, `y`, `rotation`, `scale_x`, `scale_y`). `length` is the bone's visual length.
- `attachments` place a layer on a bone. Each layer is attached at most once. The layer must exist in `asset.json`.
- `draw_order` lists every attached layer exactly once, back to front.
- `constraints`: `ik` takes a two-bone parent-to-child chain plus a `target` bone. `rotation_limit` takes one bone with `min` ≤ `max`.
- `deform` (optional): vertices in layer pixels. Each vertex has influences whose weights sum to 1.
- IK-ready metadata: bones may carry tags such as `ik_chain`, `ik_target` and `jaw`.

## Face and visemes (`face.json`, `dialogue/*.json`)

- **Visemes:** `REST, MBP, FV, TH, DNT, KG, CHJ, SZ, L, AA, E, I, O, U`. These are the only mouth shapes. `pipeline/ashes/visemes.py` is the source in code, and a test keeps the schemas in step with it.
- **Expressions:** `neutral, angry, determined, surprised, injured`. Each sets `eye_open`, `eye_direction` (each axis in -1..1), `brow_angle` (degrees), `brow_height` and `jaw_open` (0..1). An expression may also swap eye or brow sprites.
- `jaw_bone` must exist in `rig.json`. Jaw movement drives it.
- `mouth_sprites` maps every viseme to a layer name. Missing entries are a warning while drafting and an error once approved.
- **Dialogue timeline:** integer frames at the project fps (24). The first event is at frame 0. Frames are strictly increasing and less than `duration_frames`. Each viseme holds until the next event. Timestamps are converted to frames once, at authoring time, with `seconds_to_frame`. The file stores frames only.

## Approval and versioning

1. **Draft:** `status: "draft"`. Art and rig may change freely at the same version.
2. **Approve:** set `status: "approved"`, bump `version` above the last approved version, then run `./ashes approve <id>`. Approval checks the whole character, then copies each layer PNG to `history/v<version>/` and appends one entry to `approval.json`.
3. **Immutable history:** approved snapshots and `approval.json` entries are never edited or removed. Approval refuses to overwrite an existing snapshot or to reuse a version number.
4. **Changing approved art:** a changed layer is an error. The fix is to restore the approved file, or bump the version and approve again.
5. **Hashing:** SHA-256 decides exact identity, and any mismatch is an error. aHash and dHash (64-bit, over neutral grey) and pixel counts are for human review only. They never decide anything.
6. **Consistency report:** `./ashes consistency <id>` compares the current art with the latest approved version. It writes `build/consistency/<id>/report.json` and a changed-pixel mask per changed layer. It never changes the project.
7. **Never automatic:** nothing overwrites approved artwork. Approval only writes new history, and the artwork files stay where they are.

## Rules

1. **Character identity is fixed.** `character.identity` is the source of truth for appearance. Never regenerate or reinterpret a character. To change it, bump `version` and get the user's approval.
2. **Approved files are protected.** Do not overwrite a layer in an approved asset without the user's approval. Use the approval flow above.
3. **Do not invent approved artwork.** Only the user approves art. Placeholder art and synthetic test PNGs are never approved.
4. **Ids are lowercase snake_case**, unique across all asset folders. A folder's name must equal its id.
5. **Time is in seconds** (floats) in shot and asset manifests. Dialogue schedules use integer frames. Frames are otherwise derived only inside the engine.
6. **Validate before rendering.** `./ashes validate` must report zero errors.
7. **Preview before final.** Render a preview first. Final renders go to `renders/`.
8. **Report honestly.** Don't call an animation working until it has rendered and been checked. Name unfinished features as unfinished.
9. **Check dependencies.** Run `./ashes doctor` before assuming Blender or FFmpeg exists. A new dependency goes in `requirements.txt` and the README.
10. **Keep modules small.** One responsibility per module. No absolute paths; resolve through `pipeline/ashes/paths.py`.
11. **Don't overwrite existing project files without approval.**

## Commands

```bash
./ashes doctor                    # software check
./ashes validate                  # all manifests, rigs, faces, artwork, dialogue
./ashes approve <character>       # freeze approved art as a new version
./ashes consistency <character>   # compare with the approved version
cd pipeline && python3 -m unittest discover -s tests -t .
```
