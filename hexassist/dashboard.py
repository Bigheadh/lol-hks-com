"""Presentation layer for the desktop companion; no ranking logic lives here."""
from __future__ import annotations

import hashlib
import io
import queue
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import ttk
from urllib.request import urlopen

import customtkinter as ctk
from PIL import Image

from .paths import CACHE_ROOT, SEED_ROOT
from .recommendation import plain

BG = "#101216"
SIDE = "#15181E"
PANEL = "#1B1F27"
CARD = "#222731"
LINE = "#303641"
FG = "#F2F0EC"
MUTED = "#A0A8B5"
GOLD = "#D9B875"
FONT = "Microsoft YaHei UI"


def label(parent, text="", size=13, color=FG, bold=False, **kwargs):
    kwargs.setdefault("height", 0)
    return ctk.CTkLabel(parent, text=text, font=(FONT, size, "bold" if bold else "normal"), text_color=color, **kwargs)


def button(parent, text, command, primary=False, **kwargs):
    return ctk.CTkButton(parent, text=text, command=command, height=38,
        font=(FONT, 13), corner_radius=8, fg_color=GOLD if primary else CARD,
        text_color=BG if primary else FG, hover_color="#E8CD96" if primary else "#333A47", **kwargs)


class CandidateList(ctk.CTkScrollableFrame):
    """Small Listbox-compatible surface backed by spacious clickable rows."""
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent", corner_radius=0, scrollbar_button_color=LINE)
        self.rows = []
        self.selected = ()
        self.callback = None

    def bind(self, sequence, callback, add=None):
        if sequence == "<<ListboxSelect>>":
            self.callback = callback
        else:
            super().bind(sequence, callback, add)

    def delete(self, *_):
        for row in self.rows:
            row.destroy()
        self.rows.clear()
        self.selected = ()
        self._parent_canvas.yview_moveto(0)

    def insert(self, _, text):
        index = len(self.rows)
        row = ctk.CTkButton(self, text=text, height=44, anchor="w", font=(FONT, 13),
            corner_radius=7, fg_color="transparent", hover_color=CARD, text_color=MUTED,
            command=lambda: self.choose(index))
        row.pack(fill="x", pady=2)
        self.rows.append(row)

    def selection_set(self, index):
        self.selected = (index,)
        for i, row in enumerate(self.rows):
            row.configure(fg_color="#343025" if i == index else "transparent", text_color=GOLD if i == index else MUTED)

    def choose(self, index):
        self.selection_set(index)
        if self.callback:
            self.callback()

    def curselection(self):
        return self.selected


class IconLoader:
    """Fetch only visible official/source icons; failed downloads retain text labels."""
    def __init__(self, root):
        self.root = root
        self.jobs = queue.Queue()
        self.done = queue.Queue()
        self.waiting = {}
        self.images = {}
        self.failed = set()
        for _ in range(3):
            threading.Thread(target=self.worker, daemon=True).start()
        root.after(100, self.poll)

    def attach(self, widget, url, size):
        widget._requested_asset_url = url
        if url in self.images:
            photo = ctk.CTkImage(self.images[url], size=(size, size))
            widget.configure(image=photo, text="")
            widget._asset_image = photo
        elif url not in self.failed:
            if url not in self.waiting:
                self.waiting[url] = []
                self.jobs.put(url)
            self.waiting[url].append((widget, size))

    def worker(self):
        while True:
            url = self.jobs.get()
            try:
                filename = hashlib.sha256(url.encode()).hexdigest() + ".png"
                path = CACHE_ROOT / "icons" / filename
                bundled = SEED_ROOT / "icons" / filename if SEED_ROOT else None
                try:
                    with Image.open(path if path.exists() or not bundled else bundled) as source:
                        picture = source.convert("RGBA")
                except (OSError, ValueError):
                    with urlopen(url, timeout=8) as response:
                        raw = response.read(4 * 1024 * 1024 + 1)
                    if len(raw) > 4 * 1024 * 1024:
                        raise ValueError("Icon too large")
                    with Image.open(io.BytesIO(raw)) as source:
                        picture = source.convert("RGBA")
                    picture.thumbnail((256, 256))
                    path.parent.mkdir(parents=True, exist_ok=True)
                    picture.save(path)
                self.done.put((url, picture))
            except Exception:
                self.done.put((url, None))

    def poll(self):
        try:
            while True:
                url, picture = self.done.get_nowait()
                if picture is None:
                    self.failed.add(url)
                else:
                    self.images[url] = picture
                for widget, size in self.waiting.pop(url, []):
                    if picture is not None and widget.winfo_exists() and getattr(widget, "_requested_asset_url", None) == url:
                        self.attach(widget, url, size)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)


class Dashboard:
    def style(self):
        ctk.set_appearance_mode("dark")
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=CARD, background=CARD, foreground=FG,
            arrowcolor=MUTED, bordercolor=LINE, padding=7, font=(FONT, 10))
        style.map("TCombobox", fieldbackground=[("readonly", CARD)], foreground=[("readonly", FG)])
        self.root.option_add("*TCombobox*Listbox.background", CARD)
        self.root.option_add("*TCombobox*Listbox.foreground", FG)
        self.root.option_add("*TCombobox*Listbox.selectBackground", "#49402D")

    def build_ui(self):
        self.output_text = ""
        self.expanded_augments = False
        self.icons = IconLoader(self.root)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)
        side = ctk.CTkFrame(self.root, width=260, fg_color=SIDE, corner_radius=0)
        side.grid(row=0, column=0, sticky="nsew")
        side.grid_propagate(False)
        side.grid_columnconfigure(0, weight=1)
        side.grid_rowconfigure(7, weight=1)
        brand = ctk.CTkFrame(side, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=22, pady=(24, 24))
        label(brand, "⬡", 37, GOLD).pack(side="left", padx=(0, 10))
        words = ctk.CTkFrame(brand, fg_color="transparent")
        words.pack(side="left")
        label(words, "海克斯助手", 20, bold=True).pack(anchor="w")
        label(words, "ARAM  /  MAYHEM", 10, MUTED).pack(anchor="w")

        self.auto_button = button(side, "开始自动跟随", self.toggle_watch, primary=True)
        self.auto_button.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 8))
        actions = ctk.CTkFrame(side, fg_color="transparent")
        actions.grid(row=2, column=0, sticky="ew", padx=20)
        actions.grid_columnconfigure((0, 1), weight=1)
        for i, (text, command) in enumerate([("导入截图", self.import_image), ("延时截屏", self.delayed_capture)]):
            control = button(actions, text, command, width=96)
            control.grid(row=0, column=i, sticky="ew", padx=(0, 6) if i == 0 else (0, 0))
            self.buttons.append(control)
        ctk.CTkFrame(side, height=1, fg_color=LINE).grid(row=3, column=0, sticky="ew", padx=20, pady=22)
        label(side, "选择你的英雄", 14, bold=True).grid(row=4, column=0, sticky="w", padx=22, pady=(0, 10))
        self.search_text = tk.StringVar()
        self.search = ctk.CTkEntry(side, height=38, textvariable=self.search_text,
            font=(FONT, 13), fg_color=BG, border_color=LINE,
            corner_radius=8, text_color=FG)
        self.search.grid(row=5, column=0, sticky="ew", padx=20)
        self.search_text.trace_add("write", self.on_search)
        self.list_title = tk.StringVar(value="英雄 / 称号 / 昵称 · Ctrl+F 搜索")
        label(side, size=11, color=MUTED, textvariable=self.list_title).grid(row=6, column=0, sticky="w", padx=22, pady=(9, 4))
        self.candidates = CandidateList(side)
        self.candidates.grid(row=7, column=0, sticky="nsew", padx=(10, 8))
        self.candidates.bind("<<ListboxSelect>>", self.select_champion)
        self.preview = ctk.CTkLabel(side, text="尚未导入截图", height=44, text_color=MUTED,
            fg_color=BG, corner_radius=8, font=(FONT, 11))
        self.preview.grid(row=8, column=0, sticky="ew", padx=20, pady=(10, 6))
        ctk.CTkButton(side, text="识别详情  ↗", command=self.show_ocr, fg_color="transparent",
            text_color=MUTED, hover_color=CARD, height=28, font=(FONT, 11)).grid(row=9, column=0, pady=(0, 16))

        main = ctk.CTkFrame(self.root, fg_color=BG, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=1)
        top = ctk.CTkFrame(main, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=26, pady=(24, 15))
        label(top, "对局准备", 22, bold=True).pack(side="left")
        self.version_badge = label(top, "资料检查中", 11, GOLD, fg_color="#30291D", corner_radius=6, padx=10, height=27)
        self.version_badge.pack(side="left", padx=14)
        self.topmost = tk.BooleanVar(value=False)
        ctk.CTkSwitch(top, text="置顶", variable=self.topmost, width=76, switch_width=30, switch_height=16,
            font=(FONT, 12), progress_color=GOLD, button_color=FG,
            command=lambda: self.root.attributes("-topmost", self.topmost.get())).pack(side="right")
        self.refresh_button = button(top, "更新资料", self.refresh_data, width=88)
        self.refresh_button.pack(side="right", padx=12)

        self.hero_bar = ctk.CTkFrame(main, corner_radius=12, fg_color=PANEL, border_width=1, border_color=LINE)
        self.hero_bar.grid(row=1, column=0, sticky="ew", padx=26, pady=(0, 18))
        self.hero_icon = label(self.hero_bar, "◇", 35, GOLD, width=72, height=72, fg_color=CARD, corner_radius=8)
        self.hero_icon.pack(side="left", padx=18, pady=16)
        hero_text = ctk.CTkFrame(self.hero_bar, fg_color="transparent")
        hero_text.pack(side="left", fill="x", expand=True)
        self.hero_title = label(hero_text, "准备好下一场乱斗", 24, bold=True)
        self.hero_title.pack(anchor="w")
        self.hero_subtitle = label(hero_text, "选择英雄，查看专属出装与海克斯候选", 12, MUTED)
        self.hero_subtitle.pack(anchor="w", pady=(5, 0))
        self.copy_button = button(self.hero_bar, "复制推荐", self.copy_output, width=90)
        self.copy_button.pack(side="right", padx=18)
        self.copy_button.configure(state="disabled")

        self.content = ctk.CTkScrollableFrame(main, fg_color="transparent", corner_radius=0, scrollbar_button_color=LINE)
        self.content.grid(row=2, column=0, sticky="nsew", padx=(20, 15))
        self.content.grid_columnconfigure(0, weight=1)
        # Keep the selector alive when card contents are rebuilt.
        self.build_panel = ctk.CTkFrame(self.content, fg_color=PANEL, corner_radius=12)
        self.build_panel.pack(fill="x", padx=5, pady=(0, 16))
        heading = ctk.CTkFrame(self.build_panel, fg_color="transparent")
        heading.pack(fill="x", padx=20, pady=(13, 8))
        label(heading, "01", 12, GOLD, bold=True).pack(side="left", padx=(0, 10))
        label(heading, "装备组合", 17, bold=True).pack(side="left")
        self.profile = tk.StringVar(value="选择英雄后查看")
        self.profiles = ttk.Combobox(heading, textvariable=self.profile, values=[], state="disabled", width=19)
        self.profiles.pack(side="right")
        self.profiles.bind("<<ComboboxSelected>>", self.change_profile)
        self.equipment_body = ctk.CTkFrame(self.build_panel, fg_color="transparent")
        self.equipment_body.pack(fill="x", padx=20, pady=(0, 17))
        aug_heading = ctk.CTkFrame(self.content, fg_color="transparent")
        aug_heading.pack(fill="x", padx=8, pady=(0, 12))
        label(aug_heading, "02", 12, GOLD, bold=True).pack(side="left", padx=(0, 10))
        label(aug_heading, "海克斯候选", 17, bold=True).pack(side="left")
        self.expand_button = ctk.CTkButton(aug_heading, text="展开全部  ↓", command=self.toggle_augments,
            height=28, width=96, fg_color="transparent", text_color=MUTED, hover_color=CARD, font=(FONT, 12))
        self.expand_button.pack(side="right")
        self.augments_body = ctk.CTkFrame(self.content, fg_color="transparent")
        self.augments_body.pack(fill="x", padx=5)
        self.augments_body.grid_columnconfigure((0, 1, 2), weight=1, uniform="rarity")
        self.source_summary = label(self.content, "", 11, MUTED, anchor="w", justify="left", wraplength=760)
        self.source_summary.pack(fill="x", padx=8, pady=(12, 14))

        footer = ctk.CTkFrame(main, fg_color=BG, height=48)
        footer.grid(row=3, column=0, sticky="ew", padx=26, pady=(4, 12))
        footer.grid_columnconfigure(0, weight=1)
        self.status = tk.StringVar(value="就绪 · 导入截图，或直接选择英雄")
        label(footer, textvariable=self.status, size=11, color=MUTED, anchor="w", justify="left", wraplength=600).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(footer, text="数据说明 ↗", command=self.show_data_info, width=92, height=28,
            fg_color="transparent", text_color=MUTED, hover_color=CARD, font=(FONT, 11)).grid(row=0, column=1, sticky="e")
        self.populate(self.catalog.search(""))
        self.set_output("")
        self.root.bind("<Control-f>", lambda _: self.search.focus_set())

    def set_output(self, text):
        self.output_text = text
        self.render_cards()

    def copy_output(self):
        if not self.current_id:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.output_text)
        self.status.set("推荐已复制")

    def toggle_augments(self):
        self.expanded_augments = not self.expanded_augments
        self.expand_button.configure(text="收起候选  ↑" if self.expanded_augments else "展开全部  ↓")
        self.render_cards()

    def show_data_info(self):
        popup = ctk.CTkToplevel(self.root)
        popup.title("推荐详情与数据说明")
        popup.geometry("680x600")
        popup.transient(self.root)
        box = ctk.CTkTextbox(popup, font=(FONT, 13), fg_color=PANEL, wrap="word")
        box.pack(fill="both", expand=True, padx=20, pady=20)
        extra = "\n\n截图只在本地识别，不上传。\n资料为 arammeta 社区统计，不代表国服全量数据。\n本工具未获 Riot Games 认可，相关商标归 Riot Games 所有。"
        box.insert("1.0", (self.output_text or self.recommender.data.notice) + extra)
        box.configure(state="disabled")
        button(popup, "打开数据来源", lambda: webbrowser.open("https://arammeta.com/about/")).pack(pady=(0, 16))

    def icon(self, parent, url, fallback, size=40):
        tile = label(parent, fallback[:1], size // 2, GOLD, width=size, height=size, fg_color=CARD, corner_radius=6)
        self.icons.attach(tile, url, size)
        return tile

    def item_tile(self, parent, item_id, sample=None, compact=False):
        tile = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=9)
        name = self.recommender.item_name(item_id)
        size = 36 if compact else 46
        snapshot = self.recommender.data.snapshot
        version = snapshot.payload.get("ddv", self.catalog.version)
        url = f"https://ddragon.leagueoflegends.com/cdn/{version}/img/item/{item_id}.png"
        self.icon(tile, url, name, size).pack(side="left", padx=(10, 9), pady=10)
        text = ctk.CTkFrame(tile, fg_color="transparent")
        text.pack(side="left", fill="x", expand=True, padx=(0, 9), pady=8)
        label(text, name, 12 if compact else 14, bold=not compact, anchor="w", wraplength=185 if not compact else 145, justify="left").pack(anchor="w")
        if sample is not None:
            label(text, f"{sample:,} 场样本", 10, MUTED).pack(anchor="w", pady=(3, 0))
        return tile

    def render_cards(self):
        for container in (self.equipment_body, self.augments_body):
            for child in container.winfo_children():
                child.destroy()
        snapshot = self.recommender.data.snapshot
        if snapshot:
            self.version_badge.configure(text=f"PATCH {snapshot.display_patch}")
        cid = self.current_id
        self.copy_button.configure(state="normal" if cid else "disabled")
        self.source_summary.configure(text="")
        if not cid:
            self.hero_title.configure(text="准备好下一场乱斗")
            self.hero_subtitle.configure(text="选择英雄，查看专属出装与海克斯候选")
            self.hero_icon.configure(image=None, text="◇")
            self.hero_icon._requested_asset_url = None
            label(self.equipment_body, "从你的英雄开始", 22, bold=True).pack(anchor="w", pady=(25, 10))
            label(self.equipment_body, "持续跟随自己选择的英雄，换英雄后更新推荐。\n游戏中保留结果，下一局自动继续；也可手动搜索。", 14, MUTED, justify="left").pack(anchor="w", pady=(0, 25))
            for i, (name, color) in enumerate([("棱彩", "#BEAAED"), ("金色", GOLD), ("银色", "#BAC8D9")]):
                card = ctk.CTkFrame(self.augments_body, fg_color=PANEL, corner_radius=10, height=135)
                card.grid(row=0, column=i, sticky="nsew", padx=(0, 10) if i < 2 else 0)
                label(card, "◇  " + name, 14, color, bold=True).pack(anchor="w", padx=18, pady=(18, 10))
                label(card, "选择英雄后查看", 12, MUTED).pack(anchor="w", padx=18, pady=(0, 25))
            return
        champion = self.catalog.champions[cid]
        self.hero_title.configure(text=champion["title"])
        self.hero_icon.configure(image=None, text=champion["title"][:1])
        self.icons.attach(self.hero_icon, f"https://ddragon.leagueoflegends.com/cdn/{self.catalog.version}/img/champion/{cid}.png", 72)
        hero_id = snapshot.aliases.get(cid) if snapshot else None
        stale = snapshot.freshness_error() if snapshot else "暂无有效推荐资料，请点击更新资料。"
        source_hero = snapshot.payload["champs"].get(hero_id, {}) if snapshot else {}
        games = source_hero.get("g", 0)
        self.hero_subtitle.configure(text=f"{champion['name']}  /  {cid}     ·     {games:,} 场英雄样本" if source_hero else champion["name"])
        if stale or not hero_id:
            label(self.equipment_body, "资料待更新" if stale else "暂无该英雄数据", 20, GOLD, bold=True).pack(anchor="w", pady=15)
            label(self.equipment_body, stale or "当前来源没有该英雄的推荐。", 13, MUTED, wraplength=650, justify="left").pack(anchor="w", pady=(0, 20))
            self.source_summary.configure(text=self.recommender.data.notice)
            return
        builds = self.recommender.available_builds(cid)
        detail = self.recommender.data.details.get(cid)
        if builds:
            selected = builds[max(0, min(self.profiles.current(), len(builds) - 1))]
            core = ctk.CTkFrame(self.equipment_body, fg_color="transparent")
            core.pack(fill="x", pady=(0, 9))
            for i, item in enumerate(selected.get("core", [])):
                core.grid_columnconfigure(i, weight=1, uniform="core")
                self.item_tile(core, item["id"]).grid(row=0, column=i, sticky="ew", padx=(0, 8))
            label(self.equipment_body, "后续可选  ·  根据阵容与已选海克斯调整", 11, MUTED).pack(anchor="w", pady=(3, 8))
            options = sorted(selected.get("options", []), key=lambda x: x.get("g", 0), reverse=True)[:3]
            row = ctk.CTkFrame(self.equipment_body, fg_color="transparent")
            row.pack(fill="x")
            for i, item in enumerate(options):
                row.grid_columnconfigure(i, weight=1, uniform="options")
                self.item_tile(row, item["id"], item.get("g", 0), True).grid(row=0, column=i, sticky="nsew", padx=(0, 8))
            label(self.equipment_body, f"组合样本 {selected.get('g', 0):,} 场  ·  装备共现组合，不代表购买顺序", 10, MUTED).pack(anchor="w", pady=(11, 0))
        elif detail:
            pairs = detail.get("items", {}).get("top", [])[:3]
            for pair in pairs:
                label(self.equipment_body, self.recommender.item_list(pair.get("items", [])), 14, wraplength=650).pack(anchor="w", pady=8)
            if not pairs:
                label(self.equipment_body, "该英雄暂无足够的装备组合样本", 14, MUTED).pack(pady=30)
        else:
            error = getattr(self, "detail_error", None)
            label(self.equipment_body, "装备暂时无法加载，请点击更新资料重试。" if error else "正在获取该英雄的装备组合…", 14, MUTED).pack(pady=30)
        if detail:
            shoes = detail.get("boots", {}).get("top", [])[:2]
            if shoes:
                shoe_row = ctk.CTkFrame(self.equipment_body, fg_color="transparent")
                shoe_row.pack(fill="x", pady=(12, 0))
                label(shoe_row, "鞋子候选", 11, MUTED).pack(side="left", padx=(0, 12))
                for shoe in shoes:
                    label(shoe_row, self.recommender.item_list(shoe.get("items", [])), 12, FG).pack(side="left", padx=(0, 18))
        for col, (rarity, title, color) in enumerate([("kPrismatic", "棱彩", "#BEAAED"), ("kGold", "金色", GOLD), ("kSilver", "银色", "#BAC8D9")]):
            group = ctk.CTkFrame(self.augments_body, fg_color=PANEL, corner_radius=10)
            group.grid(row=0, column=col, sticky="nsew", padx=(0, 10) if col < 2 else 0)
            label(group, "◇  " + title, 14, color, bold=True).pack(anchor="w", padx=15, pady=(11, 8))
            candidates = [a for a in source_hero.get("top", {}).get(rarity, []) if a.get("g", 0) >= 100][:5 if self.expanded_augments else 3]
            for i, candidate in enumerate(candidates):
                aid = str(candidate["id"])
                info = snapshot.payload["augs"].get(aid, {})
                translated = snapshot.names.get("augs", {}).get(aid)
                name = translated.get("n") if isinstance(translated, dict) else translated
                name = name or info.get("name_zh") or info.get("name_en") or aid
                cell = ctk.CTkFrame(group, fg_color="#282633" if col == 0 and i == 0 else CARD, corner_radius=7)
                cell.pack(fill="x", padx=10, pady=(0, 7))
                icon_path = info.get("icon", "")
                if icon_path.startswith("assets/icons/") and ".." not in icon_path:
                    icon = self.icon(cell, "https://arammeta.com/" + icon_path, str(i + 1), 32)
                    icon.pack(side="left", padx=(9, 8), pady=9)
                body = ctk.CTkFrame(cell, fg_color="transparent")
                body.pack(side="left", fill="x", expand=True, padx=(0, 6), pady=8)
                label(body, plain(name), 12, color if i == 0 else FG, bold=i == 0, wraplength=165, justify="left").pack(anchor="w")
                label(body, f"{candidate['g']:,} 场样本", 10, MUTED).pack(anchor="w", pady=(3, 0))
            if not candidates:
                label(group, "样本不足，暂不推荐", 12, MUTED).pack(padx=12, pady=25)
        self.source_summary.configure(text=f"arammeta  ·  {snapshot.source_date:%Y-%m-%d} 更新  ·  候选沿用来源排序，样本 ≥ 100 场\n选英雄阶段的搭配参考；实际选择以本局出现的强化为准。")
