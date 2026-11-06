import copy
import unittest

from ashes.manifests import schema_errors
from ashes.report import Report
from ashes.rig import validate_rig
from tests.support import minimal_rig

LAYERS = {"body", "arm_l", "jaw_sprite"}


def base_rig() -> dict:
    rig = minimal_rig("hero")
    rig["bones"] = [
        {"name": "root", "parent": None, "transform": {"x": 0, "y": 0}},
        {"name": "upper_arm_l", "parent": "root", "transform": {"x": -100, "y": -120}},
        {"name": "forearm_l", "parent": "upper_arm_l", "transform": {"x": 0, "y": 150}},
        {"name": "jaw", "parent": "root", "transform": {"x": 0, "y": -200}},
    ]
    rig["attachments"] = [
        {"layer": "body", "bone": "root"},
        {"layer": "arm_l", "bone": "forearm_l"},
        {"layer": "jaw_sprite", "bone": "jaw"},
    ]
    rig["draw_order"] = ["body", "arm_l", "jaw_sprite"]
    return rig


class RigTests(unittest.TestCase):
    def run_rig(self, rig, layers=LAYERS):
        """Schema check first, then the cross-file checks, as the project validator does."""
        report = Report()
        errors = schema_errors("rig", rig)
        report.errors.extend(errors)
        if not errors:
            validate_rig(rig, "hero/rig.json", layers, report)
        return report

    def assertError(self, report, fragment):
        self.assertTrue(any(fragment in e for e in report.errors), report.errors)

    def test_valid_rig_passes(self):
        report = self.run_rig(base_rig())
        self.assertTrue(report.ok, report.errors)

    def test_missing_parent_bone(self):
        rig = base_rig()
        rig["bones"][1]["parent"] = "ghost"
        self.assertError(self.run_rig(rig), "bone 'upper_arm_l' has missing parent 'ghost'")

    def test_circular_hierarchy(self):
        rig = base_rig()
        rig["bones"] = [
            {"name": "root", "parent": None, "transform": {}},
            {"name": "a", "parent": "b", "transform": {}},
            {"name": "b", "parent": "a", "transform": {}},
        ]
        rig["attachments"], rig["draw_order"] = [], []
        self.assertError(self.run_rig(rig), "circular bone hierarchy")

    def test_self_parented_bone_is_circular(self):
        rig = base_rig()
        rig["bones"][1]["parent"] = "upper_arm_l"
        self.assertError(self.run_rig(rig), "circular bone hierarchy: upper_arm_l -> upper_arm_l")

    def test_two_root_bones_are_rejected(self):
        rig = base_rig()
        rig["bones"].append({"name": "stray", "parent": None, "transform": {}})
        self.assertError(self.run_rig(rig), "exactly one root bone, found 2")

    def test_attachment_to_missing_sprite(self):
        rig = base_rig()
        rig["attachments"].append({"layer": "shoulder_pad", "bone": "root"})
        rig["draw_order"].append("shoulder_pad")
        self.assertError(self.run_rig(rig), "references missing sprite 'shoulder_pad'")

    def test_attachment_to_unknown_bone(self):
        rig = base_rig()
        rig["attachments"][0]["bone"] = "ghost"
        self.assertError(self.run_rig(rig), "attachment 'body' uses unknown bone 'ghost'")

    def test_layer_attached_twice(self):
        rig = base_rig()
        rig["attachments"].append({"layer": "body", "bone": "jaw"})
        self.assertError(self.run_rig(rig), "layer 'body' is attached more than once")

    def test_draw_order_must_match_attachments(self):
        rig = base_rig()
        rig["draw_order"] = ["body", "arm_l"]
        self.assertError(self.run_rig(rig), "attachment 'jaw_sprite' is missing from draw_order")
        rig = base_rig()
        rig["draw_order"].append("ghost_layer")
        self.assertError(self.run_rig(rig), "draw_order lists 'ghost_layer', which has no attachment")

    def test_ik_chain_must_be_parent_to_child(self):
        rig = base_rig()
        rig["constraints"] = [
            {"name": "ik_arm", "type": "ik", "bones": ["forearm_l", "upper_arm_l"], "target": "jaw"}
        ]
        self.assertError(self.run_rig(rig), "is not parent-to-child")

    def test_ik_needs_a_target(self):
        rig = base_rig()
        rig["constraints"] = [{"name": "ik_arm", "type": "ik", "bones": ["upper_arm_l", "forearm_l"]}]
        self.assertError(self.run_rig(rig), "needs a target bone")

    def test_rotation_limit_min_must_not_exceed_max(self):
        rig = base_rig()
        rig["constraints"] = [{"name": "jaw_limit", "type": "rotation_limit", "bones": ["jaw"], "min": 30, "max": 5}]
        self.assertError(self.run_rig(rig), "min greater than max")

    def test_deform_weights_must_sum_to_one(self):
        rig = base_rig()
        rig["deform"] = [
            {
                "layer": "arm_l",
                "vertices": [[0, 0], [10, 0], [0, 10]],
                "influences": [
                    [{"bone": "upper_arm_l", "weight": 0.5}, {"bone": "forearm_l", "weight": 0.2}],
                    [{"bone": "upper_arm_l", "weight": 1}],
                    [{"bone": "forearm_l", "weight": 1}],
                ],
            }
        ]
        self.assertError(self.run_rig(rig), "vertex 0 weights sum to 0.700")

    def test_deform_needs_its_layer_attached(self):
        rig = base_rig()
        rig["deform"] = [
            {
                "layer": "arm_l",
                "vertices": [[0, 0], [1, 0], [0, 1]],
                "influences": [[{"bone": "jaw", "weight": 1}]] * 3,
            }
        ]
        rig = copy.deepcopy(rig)
        rig["attachments"] = [a for a in rig["attachments"] if a["layer"] != "arm_l"]
        rig["draw_order"] = ["body", "jaw_sprite"]
        self.assertError(self.run_rig(rig), "deform for 'arm_l' needs that layer to be attached")

    def test_schema_rejects_wrong_coordinate_space(self):
        rig = base_rig()
        rig["coordinate_space"] = "world"
        self.assertTrue(schema_errors("rig", rig))


if __name__ == "__main__":
    unittest.main()
