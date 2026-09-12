"""Version-pinned arammeta snapshots; no manual recommendation fallback."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from .paths import CACHE_ROOT, SEED_ROOT

REPOSITORY = "Lanternko/ARAM-Mayhem-Database"
SOURCE_PAGE = "https://arammeta.com/zh-CN/"
COMMITS_URL = f"https://api.github.com/repos/{REPOSITORY}/commits?path=docs/api/tier-list.json&per_page=1"
VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"


def utc_now():
    return datetime.now(timezone.utc)


def fetch_json(url: str):
    request = Request(url, headers={"User-Agent": "Hexassist/0.2 (personal desktop companion)", "Accept": "application/json"})
    for attempt in range(2):
        try:
            with urlopen(request, timeout=15) as response:
                raw = response.read(16 * 1024 * 1024 + 1)
            break
        except HTTPError:
            raise
        except (TimeoutError, URLError):
            if attempt:
                raise
    if len(raw) > 16 * 1024 * 1024:
        raise ValueError("数据源响应过大")
    return json.loads(raw)


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)


def patch_of(version: str) -> str:
    if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", version):
        raise ValueError("资料版本格式不正确")
    return ".".join(version.split(".")[:2])


def validate_payload(payload: dict):
    if not isinstance(payload, dict):
        raise ValueError("推荐数据格式不正确")
    patch_of(payload.get("patch_prefix", ""))
    if not re.fullmatch(r"\d{8}-\d+", payload.get("detailVersion", "")):
        raise ValueError("数据源没有可验证的快照日期")
    datetime.strptime(payload["detailVersion"].split("-")[0], "%Y%m%d")
    if payload.get("detailBase") != "api/champions":
        raise ValueError("数据源详情路径发生变化")
    if not isinstance(payload.get("champs"), dict) or not payload["champs"]:
        raise ValueError("数据源缺少英雄列表")
    if not isinstance(payload.get("augs"), dict) or not payload["augs"]:
        raise ValueError("数据源缺少海克斯列表")
    for hero_id, champion in payload["champs"].items():
        if not str(hero_id).isdigit() or not champion.get("alias") or not isinstance(champion.get("top"), dict):
            raise ValueError("英雄数据结构已变化")


@dataclass
class Snapshot:
    metadata: dict
    payload: dict
    names: dict

    @property
    def aliases(self):
        return {value["alias"]: key for key, value in self.payload["champs"].items()}

    @property
    def source_date(self):
        return datetime.strptime(self.payload["detailVersion"].split("-")[0], "%Y%m%d").replace(tzinfo=timezone.utc)

    @property
    def display_patch(self):
        return self.payload.get("augCategories", {}).get("newPatch") or self.payload["patch_prefix"]

    def freshness_error(self, now=None):
        now = now or utc_now()
        if patch_of(self.payload["patch_prefix"]) != self.metadata["latest_patch"]:
            return f'推荐快照版本 {self.payload["patch_prefix"]} 与已检测到的资料版本 {self.metadata["latest_patch"]} 不一致。'
        if self.source_date.date() > now.date():
            return "数据源快照日期异常。"
        if (now.date() - self.source_date.date()).days > 7:
            return "推荐快照已超过 7 天，请更新后再查看。"
        if now - datetime.fromisoformat(self.metadata["checked_at"]) > timedelta(days=7):
            return "距上次联网检查版本已超过 7 天，请重新更新。"
        return None


class LiveData:
    def __init__(self, cache_dir: Path | None = None, fetcher=fetch_json, seed_dir: Path | None = None):
        self.seed_dir = seed_dir if seed_dir is not None else (SEED_ROOT / "arammeta" if SEED_ROOT and cache_dir is None else None)
        self.cache_dir = cache_dir or CACHE_ROOT / "arammeta"
        self.fetcher = fetcher
        self.snapshot: Snapshot | None = None
        self.details: dict[str, dict] = {}
        self.notice = "尚无有效推荐快照，请更新资料。"
        self.last_refresh_error = None
        sources = [self.cache_dir] + ([self.seed_dir] if self.seed_dir else [])
        for source in sources:
            try:
                raw = json.loads((source / "snapshot.json").read_text(encoding="utf-8"))
                validate_payload(raw["payload"])
                if not re.fullmatch(r"[0-9a-f]{40}", raw["metadata"]["commit"]):
                    raise ValueError("Invalid cached commit")
                self.snapshot = Snapshot(**raw)
                self.snapshot.freshness_error()
                self.notice = "正在使用内置快照；尚未检查在线更新。" if source == self.seed_dir else "正在使用本地快照；尚未检查在线更新。"
                break
            except (OSError, ValueError, KeyError, TypeError):
                self.snapshot = None

    def refresh(self):
        latest = patch_of(self.fetcher(VERSIONS_URL)[0])
        if self.snapshot:
            self.snapshot.metadata["latest_patch"] = latest
        commit = self.fetcher(COMMITS_URL)[0]["sha"]
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("数据源提交编号无效")
        base = f"https://raw.githubusercontent.com/{REPOSITORY}/{commit}/docs/api"
        unchanged = self.snapshot is not None and self.snapshot.metadata["commit"] == commit
        payload = self.snapshot.payload if unchanged else self.fetcher(f"{base}/tier-list.json")
        validate_payload(payload)
        # Only names are used from this dictionary, never outdated item statistics.
        try:
            names = self.snapshot.names if unchanged else self.fetcher(f"{base}/names-zh-cn.json")
            if not isinstance(names.get("augs"), dict):
                names = {}
        except (OSError, ValueError, TypeError, AttributeError):
            names = {}
        metadata = {"commit": commit, "checked_at": utc_now().isoformat(), "latest_patch": latest, "source": SOURCE_PAGE, "queue": 2400}
        snapshot = Snapshot(metadata, payload, names)
        write_json(self.cache_dir / "snapshot.json", {"metadata": metadata, "payload": payload, "names": names})
        self.snapshot = snapshot
        self.details.clear()
        self.notice = "已联网核对资料版本。"
        self.last_refresh_error = None
        return snapshot

    def refresh_safely(self):
        try:
            return self.refresh()
        except Exception as error:
            self.last_refresh_error = str(error)
            self.notice = f"本次更新失败：{error}。保留原快照，未将其标记为最新。"
            if self.snapshot:
                write_json(self.cache_dir / "snapshot.json", {"metadata": self.snapshot.metadata, "payload": self.snapshot.payload, "names": self.snapshot.names})
            return self.snapshot

    def load_detail(self, cid: str):
        snapshot = self.snapshot
        if not snapshot or snapshot.freshness_error():
            return None
        hero_id = snapshot.aliases.get(cid)
        if not hero_id:
            return None
        if cid in self.details:
            return self.details[cid]
        commit = snapshot.metadata["commit"]
        path = self.cache_dir / commit / f"{hero_id}.json"
        candidates = [path] + ([self.seed_dir / commit / f"{hero_id}.json"] if self.seed_dir else [])
        detail = None
        for candidate in candidates:
            try:
                detail = json.loads(candidate.read_text(encoding="utf-8"))
                self.validate_detail(detail)
                break
            except (OSError, ValueError, TypeError):
                detail = None
        if detail is None:
            # Immutable commit prevents cross-version index/detail mixing.
            url = f"https://raw.githubusercontent.com/{REPOSITORY}/{commit}/docs/api/champions/{hero_id}.json"
            detail = self.fetcher(url)
            self.validate_detail(detail)
            write_json(path, detail)
        self.details[cid] = detail
        return detail

    @staticmethod
    def validate_detail(detail):
        if not isinstance(detail, dict) or not isinstance(detail.get("items"), dict) or not isinstance(detail.get("itemClusters", {}).get("groups"), list):
            raise ValueError("装备详情结构已变化，请检查数据源")
