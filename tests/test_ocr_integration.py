"""Optional real model integration test, enabled with HEXASSIST_TEST_OCR=1."""
import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from hexassist.catalog import Catalog
from hexassist.recognition import Recognizer, looks_like_loading, looks_like_selection
from scripts.create_demo import create_demo


@unittest.skipUnless(os.environ.get("HEXASSIST_TEST_OCR") == "1", "Set HEXASSIST_TEST_OCR=1 to run the actual OCR model")
class OCRIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("HEXASSIST_TEST_SELECTION_IMAGE"), "Set HEXASSIST_TEST_SELECTION_IMAGE to the real selection screenshot")
    def test_real_selection_at_three_client_sizes(self):
        expected = ["Zoe"]
        recognizer = Recognizer(Catalog())
        with Image.open(os.environ["HEXASSIST_TEST_SELECTION_IMAGE"]) as source:
            for size in ((1920, 1080), (1600, 900), (1280, 720)):
                with self.subTest(size=size):
                    image = source.resize(size, Image.Resampling.LANCZOS)
                    detections, raw = recognizer.recognize_selection(image)
                    self.assertEqual([d.champion_id for d in detections], expected, raw)
                    self.assertTrue(looks_like_selection(detections, size))

    @unittest.skipUnless(os.environ.get("HEXASSIST_TEST_SOLO_IMAGE"), "Set HEXASSIST_TEST_SOLO_IMAGE to the solo Katarina screenshot")
    def test_own_hero_without_any_teammates_at_three_sizes(self):
        recognizer = Recognizer(Catalog())
        with Image.open(os.environ["HEXASSIST_TEST_SOLO_IMAGE"]) as source:
            for size in ((1920, 1080), (1600, 900), (1280, 720)):
                with self.subTest(size=size):
                    image = source.resize(size, Image.Resampling.LANCZOS)
                    detections, raw = recognizer.recognize_selection(image)
                    self.assertEqual([d.champion_id for d in detections], ["Katarina"], raw)
                    self.assertTrue(looks_like_selection(detections, size))

    def test_synthetic_loading_screen(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "demo.png"
            expected = set(create_demo(target))
            with Image.open(target) as image:
                detections, raw = Recognizer(Catalog()).recognize(image)
                self.assertEqual({d.champion_id for d in detections}, expected, raw)
                self.assertTrue(looks_like_loading(detections, image.size))

    @unittest.skipUnless(os.environ.get("HEXASSIST_TEST_IMAGE"), "Set HEXASSIST_TEST_IMAGE to a local real loading screenshot")
    def test_real_loading_screen_short_title_at_native_and_1080p(self):
        # The supplied regression screenshot stays outside the repository/bundle.
        expected = {"XinZhao", "Kaisa", "Sett", "Kayle", "Vayne", "Singed",
                    "Akali", "Corki", "Ambessa", "MissFortune"}
        recognizer = Recognizer(Catalog())
        with Image.open(os.environ["HEXASSIST_TEST_IMAGE"]) as source:
            for size in (source.size, (1920, 1080)):
                with self.subTest(size=size):
                    image = source.resize(size, Image.Resampling.LANCZOS)
                    detections, raw = recognizer.recognize(image)
                    self.assertEqual({d.champion_id for d in detections}, expected, raw)
                    self.assertTrue(looks_like_loading(detections, image.size))


if __name__ == "__main__":
    unittest.main()
