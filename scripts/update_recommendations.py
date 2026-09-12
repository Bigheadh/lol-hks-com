"""Refresh current Mayhem recommendations and optionally preload selected heroes."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from hexassist.live_data import LiveData


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("champions", nargs="*", help="Champion IDs, e.g. Jinx Garen Yasuo")
    args = parser.parse_args()
    data = LiveData()
    snapshot = data.refresh()
    print(f"arammeta | patch {snapshot.display_patch} | {snapshot.source_date:%Y-%m-%d}", flush=True)
    print(f"{len(snapshot.payload['champs'])} champions / {len(snapshot.payload['augs'])} augments", flush=True)
    if snapshot.freshness_error():
        raise RuntimeError(snapshot.freshness_error())
    for cid in args.champions:
        if cid not in snapshot.aliases:
            raise ValueError(f"Unknown champion: {cid}")
        data.load_detail(cid)
        print(f"Cached equipment combinations: {cid}", flush=True)


if __name__ == "__main__":
    main()
