"""Download a compact, versioned Riot Data Dragon catalog. No API key required."""
from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent


def fetch(url: str):
    request = Request(url, headers={"User-Agent": "HexassistPrototype/0.1"})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except Exception:
            if attempt == 2:
                raise


def main():
    version = sys.argv[1] if len(sys.argv) > 1 else fetch("https://ddragon.leagueoflegends.com/api/versions.json")[0]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Expected Data Dragon version such as 16.17.1")
    base = f"https://ddragon.leagueoflegends.com/cdn/{version}/data"
    champions = fetch(f"{base}/zh_CN/champion.json")["data"]
    english = fetch(f"{base}/en_US/champion.json")["data"]
    items = fetch(f"{base}/zh_CN/item.json")["data"]
    extra = json.loads((ROOT / "data" / "aliases.json").read_text(encoding="utf-8"))
    output = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(fetch, f"{base}/zh_CN/champion/{cid}.json"): cid for cid in champions}
        for index, future in enumerate(as_completed(futures), 1):
            cid = futures[future]
            c = champions[cid]
            detail = future.result()["data"][cid]
            aliases = [english[cid]["name"], *extra.get(cid, [])]
            aliases += [skin["name"] for skin in detail["skins"] if skin["num"] != 0]
            output[cid] = {"name": c["name"], "title": c["title"], "tags": c["tags"], "aliases": sorted(set(aliases))}
            if index % 25 == 0:
                print(f"Downloaded {index}/{len(champions)} champion records", flush=True)
    data = {
        "version": version,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "https://developer.riotgames.com/docs/lol#data-dragon",
        "champions": dict(sorted(output.items())),
        "items": {iid: {"name": item["name"], "purchasable": item.get("gold", {}).get("purchasable", False), "aram": item.get("maps", {}).get("12", False)} for iid, item in items.items()},
    }
    target = ROOT / "data" / "catalog.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)
    print(f"Saved {len(output)} champions, {len(items)} items; version {version}")


if __name__ == "__main__":
    main()

