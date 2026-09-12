from __future__ import annotations

import html
import re

from .catalog import Catalog
from .live_data import LiveData


def plain(value):
    return html.unescape(re.sub(r"<[^>]+>", "", str(value))).strip()


class Recommender:
    def __init__(self, catalog: Catalog, data: LiveData | None = None):
        self.catalog = catalog
        self.data = data or LiveData()

    def available_builds(self, cid):
        return self.data.details.get(cid, {}).get("itemClusters", {}).get("groups", [])

    def item_name(self, item_id):
        key = str(item_id)
        snapshot = self.data.snapshot
        # Do not remove Mayhem special items based on the normal ARAM shop flag.
        local = self.catalog.items.get(key, {}).get("name")
        source = snapshot.payload.get("itemLut", {}).get(key, {}) if snapshot else {}
        translated = snapshot.names.get("items", {}).get(key) if snapshot else None
        return local or translated or source.get("z") or source.get("e") or f"装备 #{key}（名称缺失）"

    def item_list(self, items):
        return " + ".join(self.item_name(item["id"]) for item in items)

    def render(self, cid: str, build_index: int = 0) -> str:
        snapshot = self.data.snapshot
        lines = [self.catalog.label(cid), ""]
        if not snapshot:
            return "\n".join(lines + ["暂无有效推荐资料，请点击“更新资料”。", self.data.notice, "旧版职业模板已撤下，缺失数据不再以通用出装填充。"])
        lines += [f"海克斯大乱斗 · 版本 {snapshot.display_patch}", f"快照日期：{snapshot.source_date:%Y-%m-%d}", "来源：arammeta 社区对局统计（非国服全量数据）", self.data.notice, ""]
        stale = snapshot.freshness_error()
        if stale:
            return "\n".join(lines + ["推荐已暂停显示", stale, "请更新资料，避免沿用旧版本。", snapshot.metadata["source"]])
        hero_id = snapshot.aliases.get(cid)
        if not hero_id:
            return "\n".join(lines + ["当前快照暂无该英雄的推荐。"])
        champion = snapshot.payload["champs"][hero_id]
        lines += [f"该英雄源样本：{champion.get('g', 0):,} 场", "", "出装组合"]
        detail = self.data.details.get(cid)
        builds = self.available_builds(cid)
        if builds:
            selected = builds[max(0, min(build_index, len(builds) - 1))]
            lines += [f"核心组合：{self.item_list(selected.get('core', []))}", f"组合样本：{selected.get('g', 0):,} 场", "同组合下的可选装备："]
            options = sorted(selected.get("options", []), key=lambda v: v.get("g", 0), reverse=True)[:5]
            lines += [f"  • {self.item_name(item['id'])} · {item.get('g', 0):,} 场" for item in options]
            lines += ["这是装备共现组合，不代表购买顺序；可选装备不必全部购买。"]
        elif detail:
            pairs = detail.get("items", {}).get("top", [])[:3]
            lines += [f"  • {self.item_list(pair.get('items', []))} · {pair.get('g', 0):,} 场" for pair in pairs]
            if not pairs:
                lines += ["该英雄暂无足够的装备组合样本。"]
        else:
            lines += ["装备详情尚未加载或获取失败；点击“更新资料”重试。"]
        if detail:
            boots = detail.get("boots", {}).get("top", [])[:3]
            if boots:
                lines += ["", "鞋子候选（部分升级鞋需要特殊获得条件）"]
                lines += [f"  • {self.item_list(row.get('items', []))} · {row.get('g', 0):,} 场" for row in boots]
        lines += ["", "海克斯强化符文 · 逐英雄候选", "沿用来源排序，仅展示该英雄样本 ≥ 100 场的候选。"]
        for rarity, label in [("kPrismatic", "棱彩"), ("kGold", "金色"), ("kSilver", "银色")]:
            lines += ["", label]
            candidates = [a for a in champion.get("top", {}).get(rarity, []) if a.get("g", 0) >= 100][:5]
            for candidate in candidates:
                aid = str(candidate["id"])
                info = snapshot.payload["augs"].get(aid, {})
                name = snapshot.names.get("augs", {}).get(aid) or info.get("name_zh") or info.get("name_en") or f"海克斯 #{aid}"
                if isinstance(name, dict):
                    name = name.get("n") or name.get("name") or name.get("displayName") or info.get("name_zh") or info.get("name_en", aid)
                lines += [f"  • {plain(name)} · {candidate['g']:,} 场"]
                description = plain(info.get("desc_zh") or info.get("desc") or "")
                if description and not any(token in description for token in ("{{", "[數值]", "[数值]")):
                    lines.append(f"    {description}")
            if not candidates:
                lines.append("  样本不足，暂不推荐。")
        lines += ["", "数据说明", "社区历史样本描述关联，不能保证单局效果；未读取本局三选一选项。", "名称优先国服字典，缺失时保留来源繁中名称；说明含未解析数值时仅显示名称。", f"版本检查：{snapshot.metadata['checked_at'][:10]} · 快照 {snapshot.metadata['commit'][:8]}", "来源与统计方法：https://arammeta.com/about/", snapshot.metadata["source"]]
        return "\n".join(lines)
