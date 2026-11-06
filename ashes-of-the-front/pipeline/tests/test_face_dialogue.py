import unittest

from ashes.dialogue import seconds_to_frame, validate_dialogue
from ashes.face import validate_face
from ashes.manifests import schema_errors
from ashes.report import Report
from ashes.visemes import EXPRESSIONS, VISEMES
from tests.support import minimal_face

BONES = {"root", "jaw"}
LAYERS = {"mouth_aa", "mouth_rest"}


def dialogue(**overrides) -> dict:
    data = {
        "schema_version": 1,
        "character": "hero",
        "fps": 24,
        "duration_frames": 48,
        "events": [
            {"frame": 0, "viseme": "REST"},
            {"frame": 6, "viseme": "AA"},
            {"frame": 12, "viseme": "MBP"},
        ],
    }
    data.update(overrides)
    return data


class FaceTests(unittest.TestCase):
    def test_complete_mapping_has_no_problems(self):
        mapping = {v: "mouth_aa" for v in VISEMES}
        report = Report()
        validate_face(minimal_face("hero", mapping), "hero", True, {"mouth_aa"}, BONES, report)
        self.assertTrue(report.ok and not report.warnings, (report.errors, report.warnings))

    def test_missing_viseme_mapping_is_an_error_for_approved_characters(self):
        report = Report()
        validate_face(minimal_face("hero", {"REST": "mouth_rest"}), "hero", True, {"mouth_rest"}, BONES, report)
        self.assertTrue(any("no mouth sprite mapped for 13 viseme(s)" in e for e in report.errors), report.errors)

    def test_missing_viseme_mapping_is_a_warning_for_drafts_with_artwork(self):
        report = Report()
        validate_face(minimal_face("hero", {}), "hero", False, {"mouth_rest"}, BONES, report)
        self.assertTrue(report.ok)
        self.assertTrue(any("no mouth sprite mapped" in w for w in report.warnings))

    def test_concept_character_without_artwork_needs_no_mouth_map(self):
        report = Report()
        validate_face(minimal_face("hero", {}), "hero", False, set(), BONES, report)
        self.assertTrue(report.ok and not report.warnings)

    def test_viseme_mapped_to_an_undeclared_layer_is_an_error(self):
        report = Report()
        validate_face(minimal_face("hero", {"AA": "ghost_mouth"}), "hero", False, LAYERS, BONES, report)
        self.assertTrue(any("'ghost_mouth', which is not a layer" in e for e in report.errors), report.errors)

    def test_jaw_bone_must_exist_in_the_rig(self):
        face = minimal_face("hero")
        face["jaw_bone"] = "chin"
        report = Report()
        validate_face(face, "hero", False, set(), BONES, report)
        self.assertTrue(any("jaw_bone 'chin' is not a bone" in e for e in report.errors), report.errors)

    def test_all_five_expressions_are_required(self):
        face = minimal_face("hero")
        del face["expressions"]["injured"]
        self.assertTrue(schema_errors("face", face))

    def test_eye_direction_is_limited_to_unit_range(self):
        face = minimal_face("hero")
        face["expressions"]["angry"]["eye_direction"] = [2, 0]
        self.assertTrue(schema_errors("face", face))

    def test_expression_names_match_the_constant(self):
        face = minimal_face("hero")
        self.assertEqual(tuple(face["expressions"]), EXPRESSIONS)


class DialogueTests(unittest.TestCase):
    def check(self, data, approved=False, mapped=None):
        report = Report()
        errors = schema_errors("dialogue", data)
        report.errors.extend(errors)
        if not errors:
            info = {"hero": (approved, set(VISEMES) if mapped is None else mapped)}
            validate_dialogue(data, "dialogue/line.json", 24, info, report)
        return report

    def assertError(self, report, fragment):
        self.assertTrue(any(fragment in e for e in report.errors), report.errors)

    def test_valid_schedule_passes(self):
        report = self.check(dialogue())
        self.assertTrue(report.ok and not report.warnings, (report.errors, report.warnings))

    def test_fractional_frame_is_rejected_by_the_schema(self):
        data = dialogue(events=[{"frame": 0, "viseme": "REST"}, {"frame": 6.5, "viseme": "AA"}])
        self.assertTrue(schema_errors("dialogue", data))

    def test_unknown_viseme_is_rejected_by_the_schema(self):
        data = dialogue(events=[{"frame": 0, "viseme": "REST"}, {"frame": 6, "viseme": "XX"}])
        self.assertTrue(schema_errors("dialogue", data))

    def test_frames_must_be_strictly_increasing(self):
        data = dialogue(events=[{"frame": 0, "viseme": "REST"}, {"frame": 8, "viseme": "AA"}, {"frame": 8, "viseme": "E"}])
        self.assertError(self.check(data), "strictly increasing")

    def test_event_beyond_the_duration_is_rejected(self):
        data = dialogue(events=[{"frame": 0, "viseme": "REST"}, {"frame": 48, "viseme": "AA"}])
        self.assertError(self.check(data), "outside duration_frames 48")

    def test_first_event_must_be_at_frame_zero(self):
        data = dialogue(events=[{"frame": 3, "viseme": "REST"}])
        self.assertError(self.check(data), "first viseme event must be at frame 0")

    def test_unknown_character_is_rejected(self):
        self.assertError(self.check(dialogue(character="noah")), "unknown character 'noah'")

    def test_wrong_fps_is_rejected(self):
        self.assertError(self.check(dialogue(fps=30)), "fps must be 24")

    def test_unmapped_viseme_is_an_error_for_approved_characters(self):
        report = self.check(dialogue(), approved=True, mapped={"REST"})
        self.assertError(report, "viseme AA has no mouth sprite")

    def test_unmapped_viseme_is_a_warning_for_drafts(self):
        report = self.check(dialogue(), approved=False, mapped={"REST"})
        self.assertTrue(report.ok)
        self.assertTrue(any("viseme AA has no mouth sprite" in w for w in report.warnings))

    def test_timestamps_convert_to_nearest_integer_frame(self):
        self.assertEqual(seconds_to_frame(0.5, 24), 12)
        self.assertEqual(seconds_to_frame(0.02, 24), 0)
        self.assertEqual(seconds_to_frame(0.03, 24), 1)
        self.assertEqual(seconds_to_frame(1.0, 24), 24)
        with self.assertRaises(ValueError):
            seconds_to_frame(-0.1, 24)

    def test_viseme_names_match_the_schema_enum(self):
        dialogue_enum = schema_errors("dialogue", dialogue(events=[{"frame": 0, "viseme": "NOPE"}]))
        self.assertTrue(dialogue_enum)
        from ashes.manifests import load_json
        from ashes.paths import SCHEMA_DIR

        for name in ("dialogue", "face"):
            schema = load_json(SCHEMA_DIR / f"{name}.schema.json")
            text = str(schema)
            for viseme in VISEMES:
                self.assertIn(f"'{viseme}'", text, f"{name} schema is missing viseme {viseme}")


if __name__ == "__main__":
    unittest.main()
