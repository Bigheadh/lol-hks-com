import unittest

from hexassist.catalog import Catalog
from hexassist.recognition import (Detection, looks_like_loading, match_text, parse_ocr,
                                  parse_selection_ocr, looks_like_selection)


class RecognitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog()

    def test_exact_names_nicknames_and_single_character(self):
        for text, cid in [("金克丝", "Jinx"), ("暴走萝莉", "Jinx"), ("女警", "Caitlyn"), ("ＥＺ", "Ezreal"), ("劫", "Zed"), ("烬", "Jhin")]:
            self.assertIn(cid, match_text(text, self.catalog)[0], text)

    def test_skin_names(self):
        self.assertEqual(match_text("神王 盖伦", self.catalog), (["Garen"], False))

    def test_short_name_is_not_substring_of_player_name(self):
        self.assertNotIn("Vi", match_text("David", self.catalog)[0])
        self.assertNotIn("Vi", match_text("Viktor", self.catalog)[0])

    def test_unknown_and_short_ocr_errors_do_not_force_a_match(self):
        self.assertEqual(match_text("QZXW12345", self.catalog)[0], [])
        self.assertEqual(match_text("剑魇", self.catalog)[0], [])

    def test_confidence_filter_dedup_and_fuzzy_flag(self):
        box = [[0, 0], [100, 0], [100, 40], [0, 40]]
        rows = [[box, "暴走萝莉", .91], [box, "金克丝", .98], [box, "德玛西亚之力", .2], [box, "德玛西哑之力", .99]]
        results = parse_ocr(rows, self.catalog)
        self.assertEqual(len([d for d in results if d.champion_id == "Jinx"]), 1)
        garen = next(d for d in results if d.champion_id == "Garen")
        self.assertTrue(garen.fuzzy)

    def test_ambiguous_alias_is_not_silently_resolved(self):
        catalog = Catalog()
        catalog.aliases["测试皮肤"] = {"Garen", "Jinx"}
        box = [[0, 0], [100, 0], [100, 40], [0, 40]]
        detections = parse_ocr([[box, "测试皮肤", .99]], catalog)
        self.assertEqual(len(detections), 2)
        self.assertTrue(all(d.fuzzy for d in detections))

    def test_loading_requires_two_spread_out_rows(self):
        ids = list(self.catalog.champions)[:10]
        detections = [Detection(cid, cid, .99, 150 + (i % 5) * 350, 400 if i < 5 else 900) for i, cid in enumerate(ids)]
        self.assertTrue(looks_like_loading(detections, (1920, 1080)))
        self.assertFalse(looks_like_loading(detections[:5], (1920, 1080)))
        one_row = [Detection(d.champion_id, d.text, .99, d.x, 400) for d in detections]
        self.assertFalse(looks_like_loading(one_row, (1920, 1080)))

    def test_search_all_and_single_character(self):
        self.assertEqual(len(self.catalog.search("")), len(self.catalog.champions))
        self.assertEqual(self.catalog.search("劫")[0], "Zed")
        self.assertIn("Malphite", self.catalog.search("石头人"))

    def test_selection_ignores_player_names_chat_bench_and_overlay(self):
        def row(text, x, y, score=.99):
            return [[[x-10, y-8], [x+10, y-8], [x+10, y+8], [x-10, y+8]], text, score]
        rows = [row("赏金猎人 卡特琳娜", 960, 710),
                row("暮光星灵", 230, 190), row("远古巫灵", 230, 310),
                row("死亡颂唱者", 240, 430), row("酒桶", 220, 550), row("异画师", 230, 670),
                row("盖伦", 220, 219), row("赵信", 250, 900),
                row("金克丝", 700, 50), row("佐伊", 1800, 586)]
        detections = parse_selection_ocr(rows, self.catalog, (1920, 1080))
        self.assertEqual([d.champion_id for d in detections], ["Katarina"])
        self.assertTrue(looks_like_selection(detections, (1920, 1080)))
        self.assertEqual(parse_selection_ocr(rows[1:], self.catalog, (1920, 1080)), [])
        self.assertEqual(parse_selection_ocr(rows + [row("暮光星灵", 960, 700)], self.catalog, (1920, 1080)), [])
        self.assertFalse(looks_like_selection([], (1920, 1080)))


if __name__ == "__main__":
    unittest.main()
