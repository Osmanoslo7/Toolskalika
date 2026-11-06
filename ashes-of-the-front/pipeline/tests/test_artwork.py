import dataclasses
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from ashes.artwork import average_hash, check_layer, check_point, difference_hash, hamming, layer_facts, load_png
from ashes.report import Report
from tests.support import BODY_BOX, CANVAS, CONFIG, make_png


class LayerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.path = self.tmp / "layers" / "body.png"
        self.report = Report()

    def check(self, approved=False, settings=CONFIG.artwork):
        return check_layer(self.report, "hero", "layers/body.png", self.path, CANVAS, settings, approved)

    def assertError(self, fragment):
        self.assertTrue(any(fragment in e for e in self.report.errors), self.report.errors)

    def test_valid_layer_passes_and_reports_its_bounding_box(self):
        make_png(self.path)
        facts = self.check()
        self.assertTrue(self.report.ok, self.report.errors)
        self.assertEqual(facts.bbox, BODY_BOX)
        self.assertEqual((facts.width, facts.height), CANVAS)
        self.assertEqual(len(facts.sha256), 64)

    def test_missing_file_is_a_warning_for_drafts_and_an_error_for_approved(self):
        self.assertIsNone(self.check(approved=False))
        self.assertTrue(any("missing file 'layers/body.png'" in w for w in self.report.warnings))
        self.report = Report()
        self.assertIsNone(self.check(approved=True))
        self.assertError("missing file 'layers/body.png'")

    def test_corrupted_png_is_rejected(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00garbage" * 40)
        self.assertIsNone(self.check())
        self.assertError("corrupted PNG")

    def test_non_png_file_is_rejected(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(b"hello, this is not an image")
        self.assertIsNone(self.check())
        self.assertError("not a PNG")

    def test_missing_alpha_channel_is_rejected(self):
        make_png(self.path, mode="RGB")
        self.assertIsNone(self.check())
        self.assertError("no alpha channel")

    def test_wrong_canvas_size_is_rejected(self):
        make_png(self.path, size=(200, 200), box=(40, 40, 160, 160))
        self.assertIsNone(self.check())
        self.assertError("is 200x200, canvas is 256x256")

    def test_content_inside_the_padding_is_rejected(self):
        make_png(self.path, box=(0, 0, 100, 100))
        self.check()
        self.assertError("breaks the 8px transparent padding")

    def test_empty_layer_is_rejected(self):
        make_png(self.path, box=None)
        self.assertIsNone(self.check())
        self.assertError("no visible pixels")

    def test_solid_opaque_background_is_rejected(self):
        make_png(self.path, box=(0, 0, 256, 256))
        self.check()
        self.assertError("solid opaque fill")

    def test_too_little_transparency_is_rejected(self):
        make_png(self.path)
        strict = dataclasses.replace(CONFIG.artwork, min_transparent_fraction=0.9)
        self.check(settings=strict)
        self.assertError("is only")

    def test_pivot_outside_the_canvas_is_rejected(self):
        check_point(self.report, "hero", "layer 'body' pivot", [999, 10], CANVAS)
        self.assertError("outside the 256x256 canvas")

    def test_pivot_on_the_canvas_edge_is_allowed(self):
        check_point(self.report, "hero", "layer 'body' pivot", [0, 256], CANVAS)
        self.assertTrue(self.report.ok)


class HashTests(unittest.TestCase):
    def test_identical_images_have_identical_perceptual_hashes(self):
        image = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
        self.assertEqual(average_hash(image), average_hash(image.copy()))
        self.assertEqual(difference_hash(image), difference_hash(image.copy()))

    def test_hamming_distance_counts_differing_bits(self):
        self.assertEqual(hamming("0" * 16, "0" * 16), 0)
        self.assertEqual(hamming("0" * 16, "f" * 16), 64)
        self.assertEqual(hamming("0" * 15 + "1", "0" * 16), 1)

    def test_facts_are_deterministic_for_the_same_file(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        path = tmp / "body.png"
        make_png(path)
        first = layer_facts(path, load_png(path))
        second = layer_facts(path, load_png(path))
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
