"""Explicit --self-test mode verifies the actual frozen executable offline."""
import json
import sys
import traceback
from pathlib import Path


def run(report_path: str, test_image: str | None = None) -> int:
    report = {"frozen": bool(getattr(sys, "frozen", False)), "checks": {}}
    root = None
    try:
        import customtkinter as ctk
        from PIL import Image
        from .catalog import Catalog
        from .capture import enable_dpi_awareness
        from .gui import App
        from .paths import RESOURCE_ROOT, CACHE_ROOT
        from .recognition import Recognizer, looks_like_selection

        enable_dpi_awareness()
        catalog = Catalog()
        report["checks"]["champions"] = len(catalog.champions)
        root = ctk.CTk()
        root.withdraw()
        app = App(root, auto_refresh=False, auto_watch=False)
        data = app.recommender.data
        def no_network(_):
            raise RuntimeError("Self-test requires bundled recommendation data")
        data.fetcher = no_network
        assert data.snapshot is not None, "No bundled recommendation snapshot"
        assert data.snapshot.freshness_error() is None, data.snapshot.freshness_error()
        for cid in catalog.champions:
            assert data.load_detail(cid) is not None, cid
        report["checks"]["offline_equipment_details"] = len(data.details)
        app.current_id = "Jinx"
        app.show_data_event(app.data_generation, "detail", ("Jinx", None))
        root.update_idletasks()
        assert len(app.augments_body.winfo_children()) == 3
        assert "海克斯强化符文" in app.output_text
        report["checks"]["gui"] = "passed"
        recognizer = Recognizer(catalog)
        with Image.open(RESOURCE_ROOT / "examples" / "selection_demo.png") as image:
            detections, _ = recognizer.recognize_selection(image)
        expected = {"Katarina"}
        assert {d.champion_id for d in detections} == expected
        report["checks"]["ocr"] = sorted(expected)
        if test_image:
            with Image.open(test_image) as image:
                detections, _ = recognizer.recognize_selection(image)
                report["checks"]["provided_image_ocr"] = sorted(d.champion_id for d in detections)
                report["checks"]["provided_image_selection"] = looks_like_selection(detections, image.size)
                assert report["checks"]["provided_image_selection"], "Provided image did not pass selection detection"
                supplied = image.copy()
            # Exercise the production watcher in this frozen process across three
            # simulated game transitions using real OCR, without restarting it.
            import queue
            import time
            from .watcher import AutoWatcher
            with Image.open(RESOURCE_ROOT / "examples" / "selection_demo.png") as demo:
                samples = [supplied, demo.copy(), supplied]
            observed = queue.Queue()
            scene = {"visible": True, "image": samples[0]}
            watcher = AutoWatcher(recognizer,
                lambda: {} if scene["visible"] else None,
                lambda **_: scene["image"].copy(),
                lambda kind, payload: observed.put((kind, payload)),
                interval=.05, in_game=lambda: True)
            watcher.start()
            rounds = []
            try:
                for sample, cid in zip(samples, [detections[0].champion_id, "Katarina", detections[0].champion_id]):
                    scene.update(image=sample, visible=True)
                    deadline = time.monotonic() + 15
                    while True:
                        kind, payload = observed.get(timeout=max(.01, deadline - time.monotonic()))
                        if kind == "result" and payload[1][0].champion_id == cid:
                            rounds.append(cid)
                            break
                        assert time.monotonic() < deadline, "Continuous OCR did not resume"
                    scene["visible"] = False
                    deadline = time.monotonic() + 15
                    while True:
                        kind, _ = observed.get(timeout=max(.01, deadline - time.monotonic()))
                        if kind == "locked":
                            break
                        assert time.monotonic() < deadline, "Game pause did not complete"
                    assert not watcher.stopped.is_set(), "Watcher exited after one game"
                report["checks"]["continuous_ocr_simulated_rounds"] = rounds
            finally:
                watcher.stop()
                for thread in watcher.threads:
                    thread.join(3)
        import mss
        with mss.mss() as screen:
            report["checks"]["monitor_count"] = len(screen.monitors) - 1
        CACHE_ROOT.mkdir(parents=True, exist_ok=True)
        probe = CACHE_ROOT / "self-test-write.tmp"
        probe.write_text("ok", encoding="utf-8")
        assert probe.read_text() == "ok"
        probe.unlink()
        report["checks"]["cache_path"] = str(CACHE_ROOT)
        report["checks"]["resources"] = str(RESOURCE_ROOT)
        report["success"] = True
    except Exception:
        report["success"] = False
        report["error"] = traceback.format_exc()
    finally:
        if root is not None:
            root.destroy()
        target = Path(report_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["success"] else 1
