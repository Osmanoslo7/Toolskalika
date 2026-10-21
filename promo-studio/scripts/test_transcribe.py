import os
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(__file__))
import transcribe  # noqa: E402


def word(text, start, end, p=0.9):
    return SimpleNamespace(word=text, start=start, end=end, probability=p)


class WordsFromSegments(unittest.TestCase):
    def test_flattens_strips_and_rounds(self):
        segments = [
            SimpleNamespace(words=[word(" Your", 0.1234, 0.3), word(" site", 0.3, 0.61111)]),
            SimpleNamespace(words=None),
            SimpleNamespace(words=[word("  ", 1.0, 1.1), word(" works.", 1.2, 1.5, 0.5)]),
        ]
        self.assertEqual(
            transcribe.words_from_segments(segments),
            [
                {"text": "Your", "start": 0.123, "end": 0.3, "probability": 0.9},
                {"text": "site", "start": 0.3, "end": 0.611, "probability": 0.9},
                {"text": "works.", "start": 1.2, "end": 1.5, "probability": 0.5},
            ],
        )

    def test_hash_is_stable(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"abc")
        try:
            self.assertEqual(transcribe.file_sha1(f.name), "a9993e364706816aba3e25717850c26c9cd0d89d")
        finally:
            os.unlink(f.name)


if __name__ == "__main__":
    unittest.main()
