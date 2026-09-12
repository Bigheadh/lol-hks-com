import threading
import unittest

from PIL import Image

from hexassist.recognition import Detection
from hexassist.watcher import AutoWatcher


class WatcherTests(unittest.TestCase):
    def test_latest_swap_is_drained_before_game_lock(self):
        release_model = threading.Event()
        final_captured = threading.Event()
        locked = threading.Event()
        received = []
        count = 0

        class SlowRecognizer:
            def warm_up(self):
                release_model.wait(5)

            def recognize_selection(self, image):
                cid = "Zoe" if image.getpixel((0, 0))[0] >= 80 else "Katarina"
                return [Detection(cid, cid, .99, 200, 148)], [cid]

        def capture(**_):
            nonlocal count
            count += 1
            if count == 8:
                final_captured.set()
            return Image.new("RGB", (400, 225), (count * 20,) * 3)

        def emit(kind, payload):
            received.append((kind, payload))
            if kind == "locked":
                locked.set()

        watcher = AutoWatcher(SlowRecognizer(), lambda: {} if count < 8 else None, capture, emit,
                              interval=.01, in_game=lambda: count >= 8)
        watcher.start()
        try:
            self.assertTrue(final_captured.wait(3))
            self.assertTrue(watcher.capture_done.wait(3))
            self.assertEqual(watcher.frames.qsize(), 1)
            release_model.set()
            self.assertTrue(locked.wait(3))
            results = [payload[1][0].champion_id for kind, payload in received if kind == "result"]
            self.assertEqual(results, ["Zoe"])
            self.assertEqual(received[-1][0], "locked")
        finally:
            release_model.set()
            watcher.stop()
            for thread in watcher.threads:
                thread.join(2)

    def test_continues_through_swap_and_blank_then_locks(self):
        first = threading.Event()
        second = threading.Event()
        locked = threading.Event()
        received = []
        count = 0

        class Recognizer:
            def warm_up(self):
                pass

            def recognize_selection(self, image):
                value = image.getpixel((0, 0))[0]
                if value == 100:
                    return [], []
                cid = "Katarina" if value == 20 else "Zoe"
                return [Detection(cid, cid, .99, 200, 148)], [cid]

        def capture(**_):
            nonlocal count
            count += 1
            if count > 1:
                first.wait(3)
            value = 20 if count == 1 else (100 if count == 2 else 200)
            return Image.new("RGB", (400, 225), (value,) * 3)

        def emit(kind, payload):
            received.append((kind, payload))
            if kind == "result":
                (first if payload[1][0].champion_id == "Katarina" else second).set()
            elif kind == "locked":
                locked.set()

        watcher = AutoWatcher(Recognizer(), lambda: None if second.is_set() else {}, capture, emit,
                              interval=.03, in_game=second.is_set)
        watcher.start()
        try:
            self.assertTrue(locked.wait(4))
            results = [payload[1][0].champion_id for kind, payload in received if kind == "result"]
            self.assertEqual(results, ["Katarina", "Zoe"])
            self.assertIn("waiting", [kind for kind, _ in received])
            self.assertEqual(received[-1][0], "locked")
            self.assertFalse(watcher.stopped.is_set())
        finally:
            watcher.stop()
            for thread in watcher.threads:
                thread.join(2)

    def test_stop_suppresses_result_from_inflight_ocr(self):
        started = threading.Event()
        release = threading.Event()
        received = []

        class Recognizer:
            def warm_up(self):
                started.set()
                release.wait(3)

            def recognize_selection(self, image):
                raise AssertionError("Stopped watcher must not start OCR")

        watcher = AutoWatcher(Recognizer(), lambda: {},
                              lambda **_: Image.new("RGB", (100, 100)),
                              lambda kind, payload: received.append(kind), interval=.01)
        watcher.start()
        self.assertTrue(started.wait(2))
        watcher.stop()
        release.set()
        for thread in watcher.threads:
            thread.join(2)
        self.assertEqual(received, [])

    def test_same_watcher_reads_second_and_third_games_and_recovers_errors(self):
        import queue
        events = queue.Queue()
        scene = {"visible": True, "game": False, "hero": "Katarina", "capture_error": False, "ocr_error": False}
        colors = {"Katarina": 20, "Zoe": 120, "Garen": 220}

        class Recognizer:
            def warm_up(self):
                pass

            def recognize_selection(self, image):
                if scene["ocr_error"]:
                    scene["ocr_error"] = False
                    raise RuntimeError("temporary OCR failure")
                shade = image.getpixel((0, 0))[0]
                cid = next(cid for cid, color in colors.items() if color == shade)
                return [Detection(cid, cid, .99, 200, 148)], [cid]

        def capture(**_):
            if scene["capture_error"]:
                scene["capture_error"] = False
                raise OSError("window recreated")
            return Image.new("RGB", (400, 225), (colors[scene["hero"]],) * 3)

        def wait_for(kind, hero=None):
            import time
            end = time.monotonic() + 5
            while time.monotonic() < end:
                event, payload = events.get(timeout=max(.01, end-time.monotonic()))
                if event == kind and (hero is None or payload[1][0].champion_id == hero):
                    return
            self.fail(f"Missing {kind}: {hero}")

        watcher = AutoWatcher(Recognizer(), lambda: {} if scene["visible"] else None,
                              capture, lambda kind, payload: events.put((kind, payload)),
                              interval=.01, in_game=lambda: scene["game"])
        watcher.start()
        try:
            wait_for("result", "Katarina")
            scene.update(visible=False, game=True)
            wait_for("locked")
            self.assertTrue(all(thread.is_alive() for thread in watcher.threads))
            # Second selection must work even when the old game process lingers.
            scene.update(hero="Zoe", visible=True, capture_error=True, ocr_error=True)
            wait_for("result", "Zoe")
            scene.update(visible=False)
            wait_for("locked")
            scene.update(hero="Garen", visible=True, game=False)
            wait_for("result", "Garen")
            self.assertFalse(watcher.stopped.is_set())
        finally:
            watcher.stop()
            for thread in watcher.threads:
                thread.join(2)


if __name__ == "__main__":
    unittest.main()
