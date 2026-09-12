from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

from PIL import Image, ImageDraw, ImageOps
import customtkinter as ctk

from .dashboard import Dashboard, BG

from .capture import capture_screen, enable_dpi_awareness, foreground_client_region, game_running
from .catalog import Catalog
from .recognition import Recognizer
from .recommendation import Recommender
from .watcher import AutoWatcher

class App(Dashboard):
    def __init__(self, root: tk.Tk, auto_refresh: bool = True, auto_watch: bool = True):
        self.root = root
        self.catalog = Catalog()
        self.recommender = Recommender(self.catalog)
        self.recognizer = Recognizer(self.catalog)
        self.events: queue.Queue = queue.Queue()
        self.busy = False
        self.watching = False
        self.watch_generation = 0
        self.watcher = None
        self.selection_locked = False
        self.resume_after_manual = False
        self.current_id: str | None = None
        self.candidate_ids: list[str] = []
        self.preview_image = None
        self.raw_text: list[str] = []
        self.last_image = None
        self.last_detections = []
        self.buttons = []
        self.data_jobs = queue.Queue()
        self.data_generation = 0
        self.refreshing = False
        root.title("海克斯助手 · 持续跟随版 2026.09.06.1")
        root.geometry("1180x840")
        root.minsize(1020, 700)
        root.configure(bg=BG)
        self.style()
        self.build_ui()
        threading.Thread(target=self.data_worker, daemon=True).start()
        self.root.after(100, self.poll)
        if auto_refresh:
            self.root.after(200, self.refresh_data)
        if auto_watch:
            self.root.after(350, self.toggle_watch)

    def populate(self, ids, detections=None):
        self.candidate_ids = list(ids)
        self.candidates.delete(0, "end")
        lookup = {d.champion_id: d for d in detections or []}
        for cid in self.candidate_ids:
            suffix = " · 待确认" if cid in lookup and lookup[cid].fuzzy else ""
            self.candidates.insert("end", self.catalog.champions[cid]["title"] + "  ·  " + self.catalog.champions[cid]["name"] + suffix)

    def on_search(self, *_):
        ids = self.catalog.search(self.search_text.get())
        self.populate(ids)
        self.list_title.set(f"搜索结果：{len(ids)} 位 · 点击确认")

    def select_champion(self, _=None):
        selected = self.candidates.curselection()
        if not selected:
            return
        self.current_id = self.candidate_ids[selected[0]]
        self.detail_error = None
        self.profiles.configure(values=[], state="disabled")
        self.profile.set("正在加载组合…")
        self.set_output(self.recommender.render(self.current_id))
        self.request_detail()

    def change_profile(self, _=None):
        if self.current_id:
            self.set_output(self.recommender.render(self.current_id, max(0, self.profiles.current())))

    def refresh_data(self):
        if self.refreshing:
            return
        self.refreshing = True
        self.refresh_button.configure(state="disabled")
        self.version_badge.configure(text="资料更新中…")
        if not self.watching and not self.selection_locked:
            self.status.set("正在核对最新版本并更新推荐快照……")
        self.data_jobs.put(("refresh", None, None))

    def request_detail(self):
        self.data_generation += 1
        self.data_jobs.put(("detail", self.current_id, self.data_generation))

    def data_worker(self):
        # Serialize refresh/detail requests so snapshots cannot race each other.
        while True:
            mode, cid, generation = self.data_jobs.get()
            try:
                if mode == "refresh":
                    self.recommender.data.refresh_safely()
                    self.events.put(("data", None, "refreshed", None))
                elif cid == self.current_id and generation == self.data_generation:
                    self.recommender.data.load_detail(cid)
                    self.events.put(("data", generation, "detail", (cid, None)))
            except Exception as error:
                self.events.put(("data", generation, "data_error" if mode == "refresh" else "detail", (cid, str(error))))

    def show_data_event(self, generation, kind, payload):
        data = self.recommender.data
        if kind in ("refreshed", "data_error"):
            self.refreshing = False
            self.refresh_button.configure(state="normal")
            snapshot = data.snapshot
            message = ""
            if kind == "data_error":
                message = f"资料更新失败：{payload[1]}"
                self.version_badge.configure(text="资料更新失败 · 使用缓存")
            elif data.last_refresh_error:
                message = data.notice
                self.version_badge.configure(text="资料更新失败 · 使用缓存" if snapshot else "资料更新失败")
            elif snapshot:
                message = snapshot.freshness_error() or data.notice
                message = f"推荐版本 {snapshot.display_patch} · 快照 {snapshot.source_date:%Y-%m-%d} · {message}"
                self.version_badge.configure(text=f"PATCH {snapshot.display_patch} · {'资料待更新' if snapshot.freshness_error() else '已在线更新'}")
            else:
                message = data.notice
            if not self.watching and not self.selection_locked:
                self.status.set(message)
            if self.current_id:
                self.set_output(self.recommender.render(self.current_id))
                self.request_detail()
        elif kind == "detail":
            cid, error = payload
            if cid != self.current_id or generation != self.data_generation:
                return
            self.detail_error = error
            builds = self.recommender.available_builds(cid)
            self.profiles.configure(values=[f"组合 {i + 1} · {b.get('g', 0):,} 场" for i, b in enumerate(builds)], state="readonly" if builds else "disabled")
            if builds:
                self.profiles.current(0)
            else:
                self.profile.set("暂无可切换组合")
            self.set_output(self.recommender.render(cid))
            if error:
                self.status.set(f"装备详情获取失败：{error}；已有海克斯候选仍可查看。")

    def show_ocr(self):
        popup = ctk.CTkToplevel(self.root)
        popup.title("识别文字 · 用于排查漏识别")
        popup.geometry("520x480")
        popup.transient(self.root)
        text = ctk.CTkTextbox(popup, wrap="word", font=("Microsoft YaHei UI", 13))
        text.pack(fill="both", expand=True, padx=16, pady=16)
        text.insert("1.0", "\n".join(self.raw_text) or "还没有识别结果。")
        text.configure(state="disabled")

    def import_image(self):
        path = filedialog.askopenfilename(title="选择英雄选择界面截图", filetypes=[("图片", "*.png *.jpg *.jpeg *.webp *.bmp"), ("所有文件", "*.*")])
        if path:
            self.resume_after_manual = self.watching
            self.stop_watch()
            self.submit("file", path)

    def set_busy(self, value):
        self.busy = value
        for button in self.buttons:
            button.configure(state="disabled" if value else "normal")
        self.auto_button.configure(state="normal" if self.watching or not value else "disabled")

    def delayed_capture(self):
        if self.busy:
            return
        self.resume_after_manual = self.watching
        self.stop_watch()
        self.set_busy(True)
        self.status.set("3 秒后截屏，请切换到客户端英雄选择界面……")
        self.root.withdraw()
        self.root.after(3000, lambda: self.submit("screen", None, reserved=True))

    def stop_watch(self):
        if self.watcher is not None:
            self.watcher.stop()
            self.watcher = None
        self.watching = False
        self.watch_generation += 1
        self.auto_button.configure(text="开始自动跟随")
        self.set_busy(False)

    def toggle_watch(self):
        if self.watching:
            self.stop_watch()
            self.status.set("自动检测已停止。")
        elif not self.busy:
            self.watching = True
            self.selection_locked = False
            self.watch_generation += 1
            self.auto_button.configure(text="暂停自动跟随")
            self.status.set("持续自动跟随：换英雄后更新，游戏中保留结果，下一局自动继续。")
            generation = self.watch_generation
            self.watcher = AutoWatcher(
                self.recognizer, foreground_client_region, capture_screen,
                lambda kind, payload: self.events.put(("auto", generation, kind, payload)),
                in_game=game_running,
            )
            self.watcher.start()

    def submit(self, mode, value, reserved=False):
        if self.busy and not reserved:
            return
        self.set_busy(True)
        self.status.set("正在识别，首次加载 OCR 模型可能需要稍等……")

        def work():
            try:
                if mode == "file":
                    with Image.open(value) as source:
                        image = ImageOps.exif_transpose(source).convert("RGB")
                elif mode == "screen":
                    region = foreground_client_region()
                    if region is None:
                        raise ValueError("未找到前台英雄联盟客户端，请在倒计时内切回选英雄界面。")
                    image = capture_screen(region=region)
                else:
                    raise ValueError(f"未知截图模式：{mode}")
                detections, raw = self.recognizer.recognize_selection(image)
                self.events.put((mode, value, "result", (image, detections, raw)))
            except Exception as error:
                self.events.put((mode, value, "error", str(error)))

        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            while True:
                mode, generation, kind, payload = self.events.get_nowait()
                if mode == "data":
                    self.show_data_event(generation, kind, payload)
                    continue
                if mode == "auto" and (not self.watching or generation != self.watch_generation):
                    continue
                if mode != "auto":
                    self.set_busy(False)
                if mode == "screen":
                    self.root.deiconify()
                if kind == "error":
                    self.stop_watch()
                    self.auto_button.configure(state="normal")
                    self.status.set(f"识别失败：{payload}")
                elif kind == "result":
                    if mode == "auto":
                        self.selection_locked = False
                    self.show_result(*payload)
                elif kind == "locked":
                    self.selection_locked = True
                    self.status.set("游戏中保留最后选择，返回下一局选英雄界面后自动更新。" if self.current_id else "游戏中待机，返回选英雄界面后自动读取；也可手动搜索英雄。")
                elif kind == "waiting":
                    message, raw = payload
                    self.status.set(message)
                    if raw is not None:
                        self.raw_text = raw
                if mode in {"file", "screen"} and self.resume_after_manual:
                    self.resume_after_manual = False
                    if not self.watching:
                        self.toggle_watch()
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def show_result(self, image, detections, raw):
        previous_id = self.current_id
        self.last_image, self.last_detections, self.raw_text = image, detections, raw
        preview = image.copy()
        preview.thumbnail((216, 112))
        draw = ImageDraw.Draw(preview)
        for detection in detections:
            x, y = detection.x * preview.width / image.width, detection.y * preview.height / image.height
            draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill="#59d8bc")
        self.preview_image = ctk.CTkImage(preview, size=preview.size)
        self.preview.configure(image=self.preview_image, text="", width=216, height=112)
        if detections and detections[0].champion_id == previous_id:
            # Update the last selection image without resetting build choices or
            # queuing redundant detail downloads on every unchanged frame.
            if self.watching:
                self.status.set(f"自动跟随：{self.catalog.label(previous_id)}；换英雄后自动更新。")
            return
        self.current_id = None
        self.profiles.configure(values=[], state="disabled")
        self.profile.set("选择英雄后查看")
        self.set_output("正在读取自己的英雄；也可以在左侧手动搜索。")
        self.search_text.set("")
        if detections:
            self.populate([d.champion_id for d in detections], detections)
            self.current_id = detections[0].champion_id
            self.detail_error = None
            self.profile.set("正在加载组合…")
            self.set_output(self.recommender.render(self.current_id))
            self.request_detail()
            self.list_title.set("已识别自己的英雄 · 可搜索纠正")
            self.status.set(f"已识别：{self.catalog.label(self.current_id)}；" + ("换英雄后自动更新。" if self.watching else "可开启自动跟随。"))
        else:
            self.populate(self.catalog.search(""))
            self.list_title.set("未识别到英雄 · 可手动搜索")
            self.status.set("未读到中央立绘下方的英雄或皮肤名称，请提供完整选英雄界面截图；也可以手动搜索。")


def main():
    enable_dpi_awareness()
    import os
    if os.name == "nt":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Hexassist.Desktop")
    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    try:
        App(root)
    except Exception as error:
        messagebox.showerror("启动失败", f"{error}\n\n请先安装 requirements.txt 中的依赖。缺少资料时运行 python scripts/update_data.py。")
        root.destroy()
        raise
    root.mainloop()
