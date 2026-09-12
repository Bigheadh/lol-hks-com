"""Prepare public recommendation snapshots and UI assets for a standalone EXE."""
import hashlib
import io
import json
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import urlopen

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from hexassist.catalog import Catalog
from hexassist.live_data import LiveData, write_json


def main():
    target = ROOT / "build_assets"
    target.mkdir(exist_ok=True)
    data = LiveData()
    snapshot = data.refresh()
    if snapshot.freshness_error():
        raise RuntimeError(snapshot.freshness_error())
    catalog = Catalog()
    print(f"Preparing {len(catalog.champions)} heroes / patch {snapshot.display_patch}", flush=True)
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(data.load_detail, cid): cid for cid in catalog.champions}
        for i, future in enumerate(as_completed(futures), 1):
            if future.result() is None:
                raise ValueError(f"Missing equipment data: {futures[future]}")
            if i % 25 == 0:
                print(f"Equipment records: {i}/{len(futures)}", flush=True)
    commit = snapshot.metadata["commit"]
    seed = target / "seed" / "arammeta"
    write_json(seed / "snapshot.json", {"metadata": snapshot.metadata, "payload": snapshot.payload, "names": snapshot.names})
    for cid, detail in data.details.items():
        write_json(seed / commit / f"{snapshot.aliases[cid]}.json", detail)
    version = snapshot.payload.get("ddv", catalog.version)
    urls = {f"https://ddragon.leagueoflegends.com/cdn/{catalog.version}/img/champion/{cid}.png" for cid in catalog.champions}
    urls |= {f"https://ddragon.leagueoflegends.com/cdn/{version}/img/item/{iid}.png" for iid in snapshot.payload.get("itemLut", {})}
    urls |= {"https://arammeta.com/" + a["icon"] for a in snapshot.payload["augs"].values() if a.get("icon", "").startswith("assets/icons/")}
    icon_dir = target / "seed" / "icons"
    icon_dir.mkdir(parents=True, exist_ok=True)
    def download_icon(url):
        filename = hashlib.sha256(url.encode()).hexdigest() + ".png"
        cached = ROOT / ".cache" / "icons" / filename
        destination = icon_dir / filename
        try:
            if destination.exists():
                return None
            if cached.exists():
                shutil.copy2(cached, destination)
                return None
            with urlopen(url, timeout=10) as response:
                raw = response.read(4 * 1024 * 1024)
            with Image.open(io.BytesIO(raw)) as source:
                image = source.convert("RGBA")
                image.thumbnail((256, 256))
                image.save(destination)
            return None
        except Exception as error:
            return {"url": url, "error": str(error)}
    failed = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(download_icon, url) for url in sorted(urls)]
        for i, future in enumerate(as_completed(futures), 1):
            result = future.result()
            if result:
                failed.append(result)
            if i % 100 == 0:
                print(f"Icons: {i}/{len(futures)}", flush=True)
    write_json(target / "manifest.json", {"patch": snapshot.display_patch, "source_date": str(snapshot.source_date.date()), "commit": commit, "heroes": len(data.details), "augments": len(snapshot.payload["augs"]), "icons": len(urls) - len(failed), "failed_icons": failed})
    canvas = Image.new("RGBA", (256, 256), "#101216")
    draw = ImageDraw.Draw(canvas)
    draw.regular_polygon((128, 128, 106), 6, rotation=30, fill="#252A32", outline="#D9B875", width=12)
    draw.polygon([(139, 51), (88, 133), (123, 133), (109, 205), (169, 114), (133, 114)], fill="#D9B875")
    canvas.save(target / "hexassist.ico", sizes=[(16,16), (32,32), (48,48), (64,64), (128,128), (256,256)])
    print(f"Ready: {len(data.details)} heroes; {len(urls)-len(failed)} icons; {len(failed)} unavailable icons", flush=True)


if __name__ == "__main__":
    main()
