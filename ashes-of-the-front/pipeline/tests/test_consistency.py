import json
import shutil
import tempfile
import unittest
from pathlib import Path

from ashes.approval import ApprovalError
from ashes.consistency import build_comparison, snapshot_dir
from ashes.manifests import load_json
from ashes.paths import PROJECT_ROOT
from ashes.validate import validate_project
from tests.support import CONFIG, RED, approve, build_character, character_asset, make_png, write_json

LABEL = "characters/hero/asset.json"
CHANGED_BODY_BOX = (50, 50, 200, 210)


class ProjectFixture(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self.folder = self.root / "characters" / "hero"

    def asset(self):
        return load_json(self.folder / "asset.json")

    def save_asset(self, asset):
        write_json(self.folder / "asset.json", asset)

    def validate(self):
        return validate_project(self.root, CONFIG)

    def assertError(self, report, fragment):
        self.assertTrue(any(fragment in e for e in report.errors), report.errors)

    def approved_character(self, version=1):
        build_character(self.root, "hero", status="approved", version=version, visemes=True)
        return approve(self.folder, LABEL)


class ApprovedArtworkTests(ProjectFixture):
    def test_approved_character_validates_after_approval(self):
        self.approved_character()
        report = self.validate()
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(report.warnings, [])

    def test_approval_snapshots_each_layer_and_records_hashes(self):
        entry = self.approved_character()
        self.assertEqual(entry["version"], 1)
        self.assertEqual(set(entry["layers"]), {"body"} | {f"mouth_{v.lower()}" for v in
                                                 ("REST", "MBP", "FV", "TH", "DNT", "KG", "CHJ", "SZ", "L", "AA", "E", "I", "O", "U")})
        self.assertTrue((snapshot_dir(self.folder, 1) / "body.png").is_file())
        record = load_json(self.folder / "approval.json")
        self.assertEqual(record["versions"][0]["layers"]["body"]["file"], "history/v1/body.png")

    def test_approval_never_changes_the_artwork(self):
        build_character(self.root, "hero", status="approved", visemes=True)
        before = (self.folder / "layers" / "body.png").read_bytes()
        approve(self.folder, LABEL)
        self.assertEqual((self.folder / "layers" / "body.png").read_bytes(), before)

    def test_changed_approved_artwork_is_an_error(self):
        self.approved_character()
        make_png(self.folder / "layers" / "body.png", box=CHANGED_BODY_BOX)
        self.assertError(self.validate(), "approved artwork changed: layer 'body' differs from v1")

    def test_consistency_reports_exact_and_perceptual_differences(self):
        self.approved_character()
        make_png(self.folder / "layers" / "body.png", box=CHANGED_BODY_BOX)
        result, masks = build_comparison(self.folder, self.asset(), LABEL)
        row = result["layers"]["body"]
        self.assertEqual(row["status"], "changed")
        self.assertGreater(row["changed_pixels"], 0)
        self.assertNotEqual(row["reference_sha256"], row["current_sha256"])
        self.assertIsInstance(row["ahash_distance"], int)
        self.assertIn("body", masks)
        self.assertEqual(result["layers"]["mouth_aa"]["status"], "unchanged")

    def test_unchanged_artwork_compares_as_unchanged(self):
        self.approved_character()
        result, masks = build_comparison(self.folder, self.asset(), LABEL)
        self.assertTrue(all(row["status"] == "unchanged" for row in result["layers"].values()))
        self.assertEqual(masks, {})

    def test_approving_the_same_version_again_is_refused(self):
        self.approved_character()
        with self.assertRaisesRegex(ApprovalError, "must be higher than approved version 1"):
            approve(self.folder, LABEL)

    def test_snapshot_directory_is_never_overwritten(self):
        self.approved_character()
        snapshot_dir(self.folder, 2).mkdir(parents=True)
        self.save_asset({**self.asset(), "version": 2})
        with self.assertRaisesRegex(ApprovalError, "never overwritten"):
            approve(self.folder, LABEL)

    def test_version_bump_marked_approved_without_approval_is_an_error(self):
        self.approved_character()
        self.save_asset({**self.asset(), "version": 2})
        self.assertError(self.validate(), "marked approved but has not been approved")

    def test_new_version_can_be_approved_and_history_is_kept(self):
        self.approved_character()
        history_before = load_json(self.folder / "approval.json")["versions"][0]
        make_png(self.folder / "layers" / "body.png", box=CHANGED_BODY_BOX)
        self.save_asset({**self.asset(), "version": 2})
        approve(self.folder, LABEL)
        record = load_json(self.folder / "approval.json")
        self.assertEqual([entry["version"] for entry in record["versions"]], [1, 2])
        self.assertEqual(record["versions"][0], history_before)
        self.assertTrue((snapshot_dir(self.folder, 1) / "body.png").is_file())
        self.assertTrue(self.validate().ok)

    def test_draft_changes_to_an_approved_version_need_a_bump(self):
        self.approved_character()
        self.save_asset({**self.asset(), "status": "draft"})
        make_png(self.folder / "layers" / "body.png", box=CHANGED_BODY_BOX)
        self.assertError(self.validate(), "approved artwork changed")

    def test_draft_on_a_new_version_may_change_freely(self):
        self.approved_character()
        self.save_asset({**self.asset(), "status": "draft", "version": 2})
        make_png(self.folder / "layers" / "body.png", box=CHANGED_BODY_BOX)
        self.assertTrue(self.validate().ok)

    def test_tampered_snapshot_is_detected(self):
        self.approved_character()
        make_png(snapshot_dir(self.folder, 1) / "body.png", box=CHANGED_BODY_BOX)
        self.assertError(self.validate(), "approved snapshot v1 of layer 'body' was altered")

    def test_approved_status_without_approval_record_is_an_error(self):
        build_character(self.root, "hero", status="approved", visemes=True)
        self.assertError(self.validate(), "approval.json is missing")

    def test_removing_an_approved_layer_is_an_error(self):
        self.approved_character()
        asset = self.asset()
        asset["layers"] = [layer for layer in asset["layers"] if layer["name"] != "mouth_aa"]
        self.save_asset(asset)
        self.assertError(self.validate(), "approved layer 'mouth_aa' (v1) was removed")

    def test_adding_a_layer_after_approval_is_an_error(self):
        self.approved_character()
        asset = self.asset()
        asset["layers"].append({"name": "shadow", "file": "layers/shadow.png", "z": 99, "pivot": [128, 200]})
        make_png(self.folder / "layers" / "shadow.png", box=(70, 70, 180, 180))
        self.save_asset(asset)
        self.assertError(self.validate(), "layer 'shadow' is not in approved version v1")

    def test_approval_refuses_a_character_with_errors(self):
        build_character(self.root, "hero", status="approved", visemes=False)
        with self.assertRaisesRegex(ApprovalError, "no mouth sprite mapped for 14 viseme"):
            approve(self.folder, LABEL)
        self.assertFalse((self.folder / "approval.json").exists())

    def test_approval_refuses_a_draft(self):
        build_character(self.root, "hero", status="draft", visemes=True)
        with self.assertRaisesRegex(ApprovalError, 'set "status" to "approved"'):
            approve(self.folder, LABEL)

    def test_comparison_without_approval_reports_no_version(self):
        build_character(self.root, "hero", status="draft")
        result, masks = build_comparison(self.folder, self.asset(), LABEL)
        self.assertIsNone(result["approved_version"])
        self.assertEqual(result["problems"], ["no approved version exists yet"])


class IdentityAndPathTests(ProjectFixture):
    def test_invalid_character_id_is_rejected(self):
        build_character(self.root, "hero")
        self.save_asset({**self.asset(), "id": "Hero Man"})
        self.assertTrue(any("Hero Man" in e or "does not match" in e for e in self.validate().errors))

    def test_layer_path_escaping_the_character_folder_is_rejected(self):
        build_character(self.root, "hero")
        make_png(self.root / "outside.png")
        asset = self.asset()
        asset["layers"][0]["file"] = "../../outside.png"
        self.save_asset(asset)
        self.assertError(self.validate(), "must be a relative path inside the asset folder")

    def test_absolute_layer_path_is_rejected(self):
        build_character(self.root, "hero")
        asset = self.asset()
        asset["layers"][0]["file"] = str(self.root / "outside.png")
        self.save_asset(asset)
        self.assertError(self.validate(), "must be a relative path inside the asset folder")

    def test_layer_stored_outside_the_naming_convention_is_rejected(self):
        build_character(self.root, "hero")
        asset = self.asset()
        asset["layers"][0]["file"] = "layers/other.png"
        self.save_asset(asset)
        self.assertError(self.validate(), "must be stored as 'layers/body.png'")

    def test_layer_with_invalid_pivot_is_rejected(self):
        build_character(self.root, "hero")
        asset = self.asset()
        asset["layers"][0]["pivot"] = [400, 10]
        self.save_asset(asset)
        self.assertError(self.validate(), "pivot [400, 10] is outside the 256x256 canvas")

    def test_rig_for_another_character_is_rejected(self):
        build_character(self.root, "hero")
        rig = load_json(self.folder / "rig.json")
        rig["character"] = "noah"
        write_json(self.folder / "rig.json", rig)
        self.assertError(self.validate(), "rig.json is for 'noah', not 'hero'")

    def test_corrupted_layer_file_is_reported_without_crashing(self):
        build_character(self.root, "hero")
        (self.folder / "layers" / "body.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\xff" * 64)
        self.assertError(self.validate(), "corrupted PNG")

    def test_real_project_characters_validate(self):
        report = validate_project(PROJECT_ROOT, CONFIG)
        self.assertTrue(report.ok, report.errors)


if __name__ == "__main__":
    unittest.main()
