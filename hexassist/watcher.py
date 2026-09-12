"""Watch the champion-select client independently of OCR latency."""
from __future__ import annotations

import queue
import threading
import time

from PIL import ImageChops, ImageStat

from .recognition import looks_like_selection


class AutoWatcher:
    def __init__(self, recognizer, locate, capture, emit, interval=0.5, in_game=lambda: False):
        self.recognizer = recognizer
        self.locate = locate
        self.capture = capture
        self.emit = emit
        self.interval = interval
        self.in_game = in_game
        self.stopped = threading.Event()
        self.capture_done = threading.Event()
        self.frames = queue.Queue(maxsize=1)
        self.threads = []

    def start(self):
        # Capture and recognition remain independent during hero swaps.
        for target in (self._capture_loop, self._recognize_loop):
            thread = threading.Thread(target=target, daemon=True)
            self.threads.append(thread)
            thread.start()

    def stop(self):
        self.stopped.set()
        while True:
            try:
                self.frames.get_nowait()
            except queue.Empty:
                break

    def _send(self, kind, payload):
        if not self.stopped.is_set():
            self.emit(kind, payload)

    def _capture_loop(self):
        previous = None
        last_frame = 0.0
        last_notice = None
        while not self.stopped.is_set():
            started = time.monotonic()
            notice = None
            try:
                # A visible client takes priority over a lingering game process.
                region = self.locate()
                if region is None:
                    if self.in_game():
                        self.capture_done.set()
                    elif not self.capture_done.is_set():
                        notice = "自动跟随待机：请切回客户端选英雄界面。"
                else:
                    self.capture_done.clear()
                    try:
                        image = self.capture(region=region)
                    except ValueError as error:
                        # A black frame is normal while the game opens/transitions.
                        notice = f"等待可见客户端画面：{error}"
                    else:
                        fingerprint = image.convert("L").resize((128, 72))
                        difference = (255 if previous is None else
                                      ImageStat.Stat(ImageChops.difference(fingerprint, previous)).mean[0])
                        if difference >= 1.5 or started - last_frame >= 1.0:
                            try:
                                self.frames.put_nowait(image)
                            except queue.Full:
                                # A recent choice must replace queued older choices.
                                try:
                                    self.frames.get_nowait()
                                except queue.Empty:
                                    pass
                                self.frames.put_nowait(image)
                            previous = fingerprint
                            last_frame = started
            except Exception as error:
                # Window recreation and capture errors must not disable future games.
                notice = f"截图暂不可用，正在自动重试：{error}"
            if notice and notice != last_notice:
                self._send("waiting", (notice, None))
            last_notice = notice
            self.stopped.wait(max(0.0, self.interval - (time.monotonic() - started)))

    def _recognize_loop(self):
        locked = False
        while not self.stopped.is_set():
            try:
                self.recognizer.warm_up()
                if self.stopped.is_set():
                    return
                try:
                    image = self.frames.get(timeout=0.1)
                except queue.Empty:
                    if self.capture_done.is_set() and not locked:
                        self._send("locked", None)
                        locked = True
                    continue
                detections, raw = self.recognizer.recognize_selection(image)
                if looks_like_selection(detections, image.size):
                    locked = False
                    self._send("result", (image, detections, raw))
                else:
                    self._send("waiting", (
                        "正在读取当前英雄；切换动画期间保留上次结果。", raw))
            except Exception as error:
                self._send("waiting", (f"识别暂时失败，正在自动重试：{error}", None))
                self.stopped.wait(1.0)
