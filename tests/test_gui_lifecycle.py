import time
import unittest
from unittest.mock import patch

import customtkinter as ctk
from PIL import Image

from hexassist.gui import App
from hexassist.recognition import Detection


class FakeWatcher:
    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        pass

    def stop(self):
        pass


class LifecycleTests(unittest.TestCase):
    @staticmethod
    def close_root(root):
        for callback in root.tk.call("after", "info"):
            root.after_cancel(callback)
        root.destroy()

    def test_each_start_schedules_online_refresh_and_follow(self):
        for _ in range(2):
            root = ctk.CTk()
            root.withdraw()
            try:
                with patch.object(App, "refresh_data") as refresh, patch("hexassist.gui.AutoWatcher", FakeWatcher):
                    app = App(root)
                    deadline = time.monotonic() + 1
                    while time.monotonic() < deadline and not app.watching:
                        root.update()
                        time.sleep(.01)
                    refresh.assert_called_once()
                    self.assertTrue(app.watching)
                    app.stop_watch()
            finally:
                self.close_root(root)

    def test_follow_preserves_build_on_same_hero_and_locks_last_frame(self):
        root = ctk.CTk()
        root.withdraw()
        try:
            app = App(root, auto_refresh=False, auto_watch=False)
            with patch("hexassist.gui.AutoWatcher", FakeWatcher), patch.object(app, "request_detail") as detail:
                app.toggle_watch()
                generation = app.watch_generation
                image = Image.new("RGB", (1920, 1080))

                def result(cid):
                    return image, [Detection(cid, cid, .99, 960, 710)], [cid]

                app.events.put(("auto", generation, "result", result("Katarina")))
                app.poll()
                self.assertTrue(app.watching)
                self.assertEqual(app.current_id, "Katarina")
                detail.assert_called_once()
                app.profile.set("保留组合选择")
                app.events.put(("auto", generation, "result", result("Katarina")))
                app.events.put(("auto", generation, "waiting", ("窗口暂不可见", None)))
                app.poll()
                self.assertEqual(app.profile.get(), "保留组合选择")
                self.assertTrue(app.watching)
                self.assertEqual(detail.call_count, 1)
                app.events.put(("auto", generation, "result", result("Zoe")))
                app.events.put(("auto", generation, "locked", None))
                app.poll()
                self.assertEqual(app.current_id, "Zoe")
                self.assertIs(app.last_image, image)
                self.assertTrue(app.selection_locked)
                self.assertTrue(app.watching)
                self.assertEqual(detail.call_count, 2)
                app.events.put(("auto", generation, "result", result("Garen")))
                app.poll()
                self.assertEqual(app.current_id, "Garen")
                self.assertFalse(app.selection_locked)
                self.assertTrue(app.watching)
                self.assertEqual(detail.call_count, 3)
                # A manually cancelled watcher still cannot overwrite a new one.
                app.stop_watch()
                app.toggle_watch()
                app.events.put(("auto", generation, "result", result("Zoe")))
                app.poll()
                self.assertEqual(app.current_id, "Garen")
                app.stop_watch()
        finally:
            self.close_root(root)
