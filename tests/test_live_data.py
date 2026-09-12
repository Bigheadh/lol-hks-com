import copy
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from hexassist.catalog import Catalog
from hexassist.live_data import COMMITS_URL, VERSIONS_URL, LiveData, Snapshot, utc_now, validate_payload, write_json
from hexassist.recommendation import Recommender


def fixture():
    today = utc_now()
    payload = {
        "patch_prefix": "16.17", "detailVersion": today.strftime("%Y%m%d") + "-1000",
        "detailBase": "api/champions", "augCategories": {"newPatch": "26.17"},
        "champs": {"222": {"alias": "Jinx", "g": 2000, "top": {"kGold": [{"id": 1, "g": 500}, {"id": 2, "g": 8}]}}},
        "augs": {"1": {"name_zh": "候选甲", "desc": "测试说明"}, "2": {"name_zh": "低样本"}},
        "itemLut": {"999999": {"z": "特殊测试装备"}},
    }
    return Snapshot({"commit": "a" * 40, "checked_at": today.isoformat(), "latest_patch": "16.17", "source": "https://arammeta.com/", "queue": 2400}, payload, {})


DETAIL = {"items": {"top": []}, "itemClusters": {"groups": [
    {"core": [{"id": 3032}, {"id": 3085}], "g": 1000, "options": [{"id": 3031, "g": 800}]},
    {"core": [{"id": 6676}, {"id": 3031}], "g": 500, "options": []},
]}}


class LiveDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = LiveData(Path(self.temp.name), fetcher=lambda _: (_ for _ in ()).throw(OSError("offline")))
        self.data.snapshot = fixture()

    def test_expired_snapshot_refuses_advice_even_if_just_downloaded(self):
        self.data.snapshot.payload["detailVersion"] = (utc_now() - timedelta(days=9)).strftime("%Y%m%d") + "-1000"
        text = Recommender(Catalog(), self.data).render("Jinx")
        self.assertIn("推荐已暂停显示", text)
        self.assertNotIn("候选甲", text)

    def test_patch_mismatch_refuses_advice(self):
        self.data.snapshot.metadata["latest_patch"] = "16.18"
        self.assertIn("不一致", self.data.snapshot.freshness_error())

    def test_failed_refresh_keeps_old_check_timestamp(self):
        old = self.data.snapshot.metadata["checked_at"]
        self.data.refresh_safely()
        self.assertEqual(self.data.snapshot.metadata["checked_at"], old)
        self.assertIn("失败", self.data.notice)
        self.assertIsNotNone(self.data.last_refresh_error)

    def test_cached_snapshot_is_checked_online_on_every_refresh(self):
        calls = []
        def fetch(url):
            calls.append(url)
            if url == VERSIONS_URL:
                return ["16.17.1"]
            if url == COMMITS_URL:
                return [{"sha": "a" * 40}]
            raise AssertionError("Unchanged snapshot should not be redownloaded")
        self.data.fetcher = fetch
        self.data.last_refresh_error = "old failure"
        self.data.refresh_safely()
        self.data.refresh_safely()
        self.assertEqual(calls.count(VERSIONS_URL), 2)
        self.assertEqual(calls.count(COMMITS_URL), 2)
        self.assertIsNone(self.data.last_refresh_error)

    def test_new_patch_discovery_survives_provider_failure(self):
        def fetch(url):
            if url == VERSIONS_URL:
                return ["16.18.1"]
            raise OSError("provider down")
        self.data.fetcher = fetch
        self.data.refresh_safely()
        reloaded = LiveData(Path(self.temp.name))
        self.assertIn("不一致", reloaded.snapshot.freshness_error())

    def test_detail_is_bound_to_immutable_snapshot_commit(self):
        calls = []
        self.data.fetcher = lambda url: calls.append(url) or copy.deepcopy(DETAIL)
        self.data.load_detail("Jinx")
        self.assertIn("/" + "a" * 40 + "/", calls[0])
        self.data.load_detail("Jinx")
        self.assertEqual(len(calls), 1)
        self.data.snapshot.metadata["commit"] = "b" * 40
        self.data.details.clear()
        self.data.load_detail("Jinx")
        self.assertIn("/" + "b" * 40 + "/", calls[1])

    def test_refresh_has_real_source_date_and_clears_old_details(self):
        sample = fixture()
        def fetch(url):
            if url == VERSIONS_URL:
                return ["16.17.1"]
            if url == COMMITS_URL:
                return [{"sha": "c" * 40}]
            return sample.payload if url.endswith("tier-list.json") else {"augs": {}}
        self.data.fetcher = fetch
        self.data.details["Jinx"] = DETAIL
        self.data.refresh()
        self.assertEqual(self.data.details, {})
        self.assertEqual(self.data.snapshot.source_date.date(), utc_now().date())

    def test_missing_data_never_falls_back_to_role_template(self):
        self.data.snapshot = None
        text = Recommender(Catalog(), self.data).render("Jinx")
        self.assertIn("暂无有效推荐", text)
        self.assertNotIn("收集者", text)

    def test_small_sample_filter_and_build_switch(self):
        self.data.details["Jinx"] = copy.deepcopy(DETAIL)
        rec = Recommender(Catalog(), self.data)
        text = rec.render("Jinx", 0)
        self.assertIn("候选甲", text)
        self.assertNotIn("低样本", text)
        self.assertIn("不代表购买顺序", text)
        self.assertIn("收集者 + 无尽之刃", rec.render("Jinx", 1))

    def test_special_item_is_preserved_without_normal_aram_shop_entry(self):
        self.assertEqual(Recommender(Catalog(), self.data).item_name(999999), "特殊测试装备")

    def test_chinese_name_record_and_unresolved_tooltip(self):
        self.data.snapshot.names = {"augs": {"1": {"n": "国服候选名称", "d": "旧描述不得使用"}}}
        self.data.snapshot.payload["augs"]["1"]["desc"] = "触发 {{ Item_Keyword_OnHit }}"
        text = Recommender(Catalog(), self.data).render("Jinx")
        self.assertIn("国服候选名称", text)
        self.assertNotIn("Item_Keyword", text)
        self.assertNotIn("旧描述不得使用", text)

    def test_corrupt_cache_is_ignored(self):
        (Path(self.temp.name) / "snapshot.json").write_text("broken", encoding="utf-8")
        self.assertIsNone(LiveData(Path(self.temp.name)).snapshot)

    def test_bundled_seed_works_without_network_or_writing_into_resources(self):
        seed = Path(self.temp.name) / "readonly-seed"
        writable = Path(self.temp.name) / "user-cache"
        snapshot = fixture()
        write_json(seed / "snapshot.json", {"metadata": snapshot.metadata, "payload": snapshot.payload, "names": snapshot.names})
        write_json(seed / snapshot.metadata["commit"] / "222.json", DETAIL)
        data = LiveData(writable, fetcher=self.data.fetcher, seed_dir=seed)
        self.assertIsNotNone(data.snapshot)
        self.assertEqual(data.load_detail("Jinx"), DETAIL)
        self.assertFalse(writable.exists())

    def test_newer_user_snapshot_does_not_reuse_different_seed_details(self):
        seed = Path(self.temp.name) / "seed"
        writable = Path(self.temp.name) / "user-cache"
        snapshot = fixture()
        write_json(seed / snapshot.metadata["commit"] / "222.json", DETAIL)
        snapshot.metadata["commit"] = "b" * 40
        write_json(writable / "snapshot.json", {"metadata": snapshot.metadata, "payload": snapshot.payload, "names": snapshot.names})
        data = LiveData(writable, fetcher=self.data.fetcher, seed_dir=seed)
        with self.assertRaises(OSError):
            data.load_detail("Jinx")

    def test_missing_patch_or_date_is_rejected(self):
        for key in ("patch_prefix", "detailVersion"):
            payload = copy.deepcopy(fixture().payload)
            payload.pop(key)
            with self.assertRaises(ValueError):
                validate_payload(payload)


if __name__ == "__main__":
    unittest.main()
