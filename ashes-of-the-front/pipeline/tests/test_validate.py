import json
import shutil
import tempfile
import unittest
from pathlib import Path

from ashes.config import load_config
from ashes.deps import check_all
from ashes.paths import PROJECT_ROOT
from ashes.validate import validate_project

CONFIG = load_config()


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def asset(asset_id: str, asset_type: str = "character", **overrides) -> dict:
    data = {
        "id": asset_id,
        "type": asset_type,
        "name": asset_id.title(),
        "version": 1,
        "status": "draft",
        "description": "Test asset.",
        "layers": [],
    }
    if asset_type == "character":
        data["character"] = {"identity": {"age": 30, "role": "tester"}}
    data.update(overrides)
    return data


def shot(**overrides) -> dict:
    data = {
        "id": "s01",
        "title": "Test shot",
        "duration_seconds": 6,
        "fps": 24,
        "width": 1080,
        "height": 1920,
        "characters": ["hero"],
        "environment": "bunker",
        "camera": {"keyframes": [{"time": 0, "x": 0, "y": 0, "zoom": 1}, {"time": 6, "zoom": 1.2}]},
        "layers": [
            {"id": "hero_layer", "asset": "hero", "z": 10, "keyframes": [{"time": 0, "x": 540, "y": 1200}]}
        ],
        "effects": [],
        "dialogue": [{"speaker": "hero", "text": "Hold.", "start": 1, "end": 2}],
        "audio": [],
        "output": {"file": "renders/s01.mp4"},
    }
    data.update(overrides)
    return data


class FixtureProject(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        write_json(self.root / "characters" / "hero" / "asset.json", asset("hero"))
        write_json(self.root / "environments" / "bunker" / "asset.json", asset("bunker", "environment"))
        write_json(self.root / "shots" / "s01" / "shot.json", shot())

    def validate(self):
        return validate_project(self.root, CONFIG)


class ValidProjectTests(FixtureProject):
    def test_fixture_project_is_valid(self):
        report = self.validate()
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(report.warnings, [])
        self.assertEqual(report.checked, 3)

    def test_real_project_is_valid(self):
        report = validate_project(PROJECT_ROOT, CONFIG)
        self.assertTrue(report.ok, report.errors)


class AssetTests(FixtureProject):
    def test_duplicate_id_is_an_error(self):
        write_json(self.root / "characters" / "hero_copy" / "asset.json", asset("hero"))
        report = self.validate()
        self.assertTrue(any("duplicate id 'hero'" in e for e in report.errors), report.errors)

    def test_folder_must_match_id(self):
        write_json(self.root / "characters" / "other" / "asset.json", asset("someone_else"))
        report = self.validate()
        self.assertTrue(any("must match id" in e for e in report.errors), report.errors)

    def test_type_must_match_its_folder(self):
        write_json(self.root / "props" / "bunker" / "asset.json", asset("bunker", "environment"))
        report = self.validate()
        self.assertTrue(any("does not belong in 'props/'" in e for e in report.errors), report.errors)

    def test_character_section_is_required_for_characters(self):
        data = asset("hero")
        del data["character"]
        write_json(self.root / "characters" / "hero" / "asset.json", data)
        self.assertTrue(any("character" in e for e in self.validate().errors))

    def test_draft_with_missing_layer_file_is_a_warning(self):
        data = asset("hero", layers=[{"name": "body", "file": "layers/body.png", "z": 1}])
        write_json(self.root / "characters" / "hero" / "asset.json", data)
        report = self.validate()
        self.assertTrue(report.ok, report.errors)
        self.assertTrue(any("missing file 'layers/body.png'" in w for w in report.warnings))

    def test_approved_asset_with_missing_layer_file_is_an_error(self):
        data = asset(
            "hero",
            status="approved",
            layers=[{"name": "body", "file": "layers/body.png", "z": 1}],
        )
        write_json(self.root / "characters" / "hero" / "asset.json", data)
        report = self.validate()
        self.assertTrue(any("missing file 'layers/body.png'" in e for e in report.errors), report.errors)

    def test_approved_asset_needs_a_layer(self):
        write_json(self.root / "characters" / "hero" / "asset.json", asset("hero", status="approved"))
        report = self.validate()
        self.assertTrue(any("need at least one layer" in e for e in report.errors), report.errors)

    def test_file_path_cannot_escape_the_asset_folder(self):
        data = asset("hero", layers=[{"name": "body", "file": "../secret.png", "z": 1}])
        write_json(self.root / "characters" / "hero" / "asset.json", data)
        report = self.validate()
        self.assertTrue(any("inside the asset folder" in e for e in report.errors), report.errors)

    def test_unknown_key_fails_the_schema(self):
        write_json(self.root / "characters" / "hero" / "asset.json", asset("hero", colour="red"))
        self.assertTrue(any("colour" in e for e in self.validate().errors))


class ShotTests(FixtureProject):
    def set_shot(self, **overrides):
        write_json(self.root / "shots" / "s01" / "shot.json", shot(**overrides))
        return self.validate()

    def assertError(self, report, fragment):
        self.assertTrue(any(fragment in e for e in report.errors), report.errors)

    def test_duration_must_land_on_whole_frames(self):
        self.assertError(self.set_shot(duration_seconds=1.02), "whole number of frames")

    def test_resolution_must_match_the_project(self):
        self.assertError(self.set_shot(width=1920, height=1080), "1080x1920 at 24 fps")

    def test_unknown_character_is_an_error(self):
        self.assertError(self.set_shot(characters=["ghost"]), "unknown asset")

    def test_asset_type_must_match_the_slot(self):
        self.assertError(self.set_shot(environment="hero"), "has type character, expected environment")

    def test_camera_keyframes_must_increase(self):
        keys = [{"time": 3, "zoom": 1}, {"time": 2, "zoom": 1.1}]
        self.assertError(self.set_shot(camera={"keyframes": keys}), "strictly increasing")

    def test_keyframe_after_the_shot_is_an_error(self):
        keys = [{"time": 0, "zoom": 1}, {"time": 7, "zoom": 1.1}]
        self.assertError(self.set_shot(camera={"keyframes": keys}), "outside 0..6")

    def test_dialogue_speaker_must_be_in_the_shot(self):
        line = [{"speaker": "noah", "text": "Copy.", "start": 1, "end": 2}]
        self.assertError(self.set_shot(dialogue=line), "is not listed in characters")

    def test_unknown_key_fails_the_schema(self):
        self.assertError(self.set_shot(bogus=True), "bogus")

    def test_missing_audio_file_is_a_warning(self):
        cue = [{"kind": "sfx", "file": "audio/sfx/shot.wav", "start": 0}]
        report = self.set_shot(audio=cue)
        self.assertTrue(report.ok, report.errors)
        self.assertTrue(any("does not exist yet" in w for w in report.warnings))


class DependencyTests(unittest.TestCase):
    def test_python_version_is_detected(self):
        python_check = check_all()[0]
        self.assertEqual(python_check.name, "python")
        self.assertTrue(python_check.ok)


if __name__ == "__main__":
    unittest.main()
