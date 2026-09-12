from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from difflib import SequenceMatcher

from .catalog import Catalog, normalize


@dataclass(frozen=True)
class Detection:
    champion_id: str
    text: str
    confidence: float
    x: float
    y: float
    fuzzy: bool = False


def match_text(text: str, catalog: Catalog) -> tuple[list[str], bool]:
    """Prefer exact names/skin aliases; never silently resolve ambiguous skins."""
    key = normalize(text)
    if key in catalog.aliases:
        return sorted(catalog.aliases[key]), False
    matches = []
    for alias, ids in catalog.aliases.items():
        if alias.isascii():
            # Vi must not match inside a player's name such as David.
            found = bool(re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", text.casefold()))
        else:
            found = len(alias) >= 3 and alias in key
        if found:
            matches.append((len(alias), ids))
    if matches:
        longest = max(length for length, _ in matches)
        return sorted({cid for length, ids in matches if length == longest for cid in ids}), False
    # Short Chinese names are too easy to confuse; fuzzy candidates require >=4 characters.
    if len(key) < 4:
        return [], False
    scores: dict[str, float] = {}
    for alias, ids in catalog.aliases.items():
        if len(alias) < 4 or abs(len(alias) - len(key)) > 1:
            continue
        score = SequenceMatcher(None, key, alias).ratio()
        if score >= (0.82 if len(key) >= 6 else 0.84):
            for cid in ids:
                scores[cid] = max(score, scores.get(cid, 0))
    if not scores:
        return [], False
    best = max(scores.values())
    return sorted(cid for cid, score in scores.items() if best - score < 0.03), True


def parse_ocr(rows: list, catalog: Catalog, min_confidence: float = 0.65) -> list[Detection]:
    best: dict[str, Detection] = {}
    for box, text, confidence in rows:
        if float(confidence) < min_confidence:
            continue
        ids, fuzzy = match_text(text, catalog)
        # Ambiguous aliases and fuzzy matches are displayed as candidates, not certain results.
        uncertain = fuzzy or len(ids) > 1
        x = sum(point[0] for point in box) / len(box)
        y = sum(point[1] for point in box) / len(box)
        for cid in ids:
            detection = Detection(cid, text, float(confidence), x, y, uncertain)
            old = best.get(cid)
            if old is None or (not detection.fuzzy, detection.confidence) > (not old.fuzzy, old.confidence):
                best[cid] = detection
    return sorted(best.values(), key=lambda value: (value.y, value.x))


def looks_like_loading(detections: list[Detection], image_size: tuple[int, int]) -> bool:
    """Conservative two-row heuristic for automatic capture; user still confirms."""
    width, height = image_size
    certain = [d for d in detections if not d.fuzzy]
    if not 6 <= len(certain) <= 10:
        return False
    upper = [d for d in certain if d.y < height / 2]
    lower = [d for d in certain if d.y >= height / 2]
    return all(
        3 <= len(row) <= 5
        and max(d.x for d in row) - min(d.x for d in row) > width * 0.3
        and max(d.y for d in row) - min(d.y for d in row) < height * 0.12
        for row in (upper, lower)
    )


def own_title_region(x: float, y: float, image_size: tuple[int, int]) -> bool:
    """The selected skin/hero title under the local player's central portrait."""
    width, height = image_size
    return 650 / 1920 <= x / width <= 1270 / 1920 and 675 / 1080 <= y / height <= 735 / 1080


def parse_selection_ocr(rows: list, catalog: Catalog, image_size: tuple[int, int]) -> list[Detection]:
    selected = {}
    for box, text, confidence in rows:
        x = sum(p[0] for p in box) / len(box)
        y = sum(p[1] for p in box) / len(box)
        ids, fuzzy = match_text(text, catalog)
        if not own_title_region(x, y, image_size) or len(ids) != 1 or fuzzy or float(confidence) < .65:
            continue
        detection = Detection(ids[0], text, float(confidence), x, y)
        if ids[0] not in selected or detection.confidence > selected[ids[0]].confidence:
            selected[ids[0]] = detection
    # Conflicting names in the local title are uncertain; never choose a teammate.
    return list(selected.values()) if len(selected) == 1 else []


def looks_like_selection(detections: list[Detection], image_size: tuple[int, int]) -> bool:
    return (len(detections) == 1 and not detections[0].fuzzy
            and own_title_region(detections[0].x, detections[0].y, image_size))


class Recognizer:
    def __init__(self, catalog: Catalog):
        self.catalog = catalog
        self.engine = None
        self.lock = threading.RLock()

    def warm_up(self):
        from rapidocr_onnxruntime import RapidOCR
        with self.lock:
            if self.engine is None:
                self.engine = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=2)

    def recognize(self, image) -> tuple[list[Detection], list[str]]:
        with self.lock:
            self.warm_up()
            return self._recognize(image)

    def recognize_selection(self, image) -> tuple[list[Detection], list[str]]:
        import numpy as np
        from PIL import Image

        with self.lock:
            self.warm_up()
            width, height = image.size
            left, top = round(width * 650 / 1920), round(height * 675 / 1080)
            right, bottom = round(width * 1270 / 1920), round(height * 735 / 1080)
            crop = image.convert("RGB").crop((left, top, right, bottom))
            # One local skin/hero title, independent of teammate visibility/count.
            target = (1240, 120)
            sx, sy = target[0] / crop.width, target[1] / crop.height
            crop = crop.resize(target, Image.Resampling.LANCZOS)
            rows, _ = self.engine(np.asarray(crop)[:, :, ::-1].copy())
            rows = rows or []
            for box, _, _ in rows:
                for point in box:
                    point[0] = point[0] / sx + left
                    point[1] = point[1] / sy + top
            return parse_selection_ocr(rows, self.catalog, image.size), [str(row[1]) for row in rows]

    def _recognize(self, image) -> tuple[list[Detection], list[str]]:
        import numpy as np
        image = image.convert("RGB")
        # Keep native 1440p/4K text. Downsampling 2560px loading screens to
        # 2400px can drop short titles such as 腕豪 below the confidence threshold.
        scale = min(1.0, 3840 / max(image.size))
        if scale < 1:
            from PIL import Image
            image = image.resize(
                (round(image.width * scale), round(image.height * scale)),
                Image.Resampling.LANCZOS,
            )
        # RapidOCR accepts OpenCV BGR arrays.
        rows, _ = self.engine(np.asarray(image)[:, :, ::-1].copy())
        rows = rows or []
        for box, _, _ in rows:
            for point in box:
                point[0] /= scale
                point[1] /= scale
        return parse_ocr(rows, self.catalog), [str(row[1]) for row in rows]
