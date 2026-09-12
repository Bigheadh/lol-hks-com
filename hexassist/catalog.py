from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from .paths import RESOURCE_ROOT

ROOT = RESOURCE_ROOT
DATA_DIR = ROOT / "data"


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", value)


class Catalog:
    def __init__(self, data_dir: Path = DATA_DIR):
        with (data_dir / "catalog.json").open(encoding="utf-8") as stream:
            self.raw = json.load(stream)
        self.version = self.raw["version"]
        self.champions = self.raw["champions"]
        self.items = self.raw["items"]
        self.aliases: dict[str, set[str]] = {}
        for cid, champion in self.champions.items():
            for alias in [cid, champion["name"], champion["title"], *champion["aliases"]]:
                key = normalize(alias)
                if key:
                    self.aliases.setdefault(key, set()).add(cid)

    def label(self, cid: str) -> str:
        c = self.champions[cid]
        return f'{c["name"]} · {c["title"]}'

    def search(self, query: str) -> list[str]:
        key = normalize(query)
        if not key:
            return sorted(self.champions, key=self.label)
        exact = self.aliases.get(key, set())
        others = {cid for alias, ids in self.aliases.items() if key in alias for cid in ids}
        return sorted(exact, key=self.label) + sorted(others - exact, key=self.label)

    def item_name(self, item_id: str) -> str | None:
        item = self.items.get(str(item_id))
        # Data Dragon's map flag is a basic filter, not a guarantee for Mayhem.
        if not item or not item.get("purchasable") or not item.get("aram"):
            return None
        return item["name"]
