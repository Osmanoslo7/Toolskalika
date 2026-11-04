# Ashes of the Front: project conventions

These rules apply to every change in this project. Read them before editing anything here.

## What this is

An original fictional military animated series. Format: 1080×1920 vertical, 24 fps, 3–5 minute episodes. Style: hybrid of hand-inked graphic-novel panels and fully animated action. Palette: black, white, graphite, restrained red.

Pipeline: 2D skeletal characters and 2.5D layered environments, assembled in Blender through Python, encoded and mixed with FFmpeg.

## Layout

- `config/project.toml`: the only home for video, episode and project settings.
- `schemas/`: JSON Schemas for asset and shot manifests. Changing a schema needs a note in the commit message.
- `characters/`, `environments/`, `props/`, `effects/`: each asset is `<folder>/<id>/asset.json` plus its files.
- `audio/`: dialogue, narration, radio, sfx, music. Shot audio paths are relative to the project root.
- `shots/<id>/shot.json`: one shot manifest per shot.
- `renders/`, `build/`: generated output. Git-ignored. Never edit by hand.
- `pipeline/ashes/`: the Python package. `pipeline/tests/`: its tests. Entry point: `./ashes`.

## Rules

1. **Character identity is fixed.** `character.identity` in `asset.json` is the source of truth. Never regenerate or reinterpret a character's appearance. To change it, bump `version` and get the user's approval first.
2. **Approved files are protected.** Never overwrite a file in an asset with `status: "approved"` without the user's approval.
3. **Ids are lowercase snake_case** and unique across all asset folders. A folder's name must equal its id.
4. **Time is in seconds** (floats) in every manifest. Frames are derived only inside the engine. A shot's duration must land on whole frames at the project fps.
5. **Coordinates are pixels**, origin top-left, on the 1080×1920 canvas.
6. **Mouth shapes** use the viseme keys in the schema (`rest, AI, E, O, U, etc, FV, L, MBP, WQ`). **Expressions** use snake_case names.
7. **Validate before rendering.** `./ashes validate` must report zero errors.
8. **Preview before final.** Render a preview first. Final renders go to `renders/`.
9. **Report honestly.** Don't call an animation working until it has rendered and been checked. Name unfinished features as unfinished.
10. **Check dependencies.** Run `./ashes doctor` before assuming Blender or FFmpeg exists. Any new dependency goes in `requirements.txt` and the README.
11. **Keep modules small.** One responsibility per module. No absolute paths; resolve everything through `pipeline/ashes/paths.py`.
12. **Don't overwrite existing project files without approval.**

## Commands

```bash
./ashes doctor                                   # software check
./ashes validate                                 # manifest check
cd pipeline && python3 -m unittest discover -s tests -t .   # tests
```
