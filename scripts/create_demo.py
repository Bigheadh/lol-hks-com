"""Generate a visibly synthetic loading layout for OCR integration checks."""
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from hexassist.catalog import Catalog


def create_demo(target: Path):
    font_path = Path("C:/Windows/Fonts/msyh.ttc")
    if not font_path.exists():
        raise RuntimeError("Demo generation needs a Chinese font: edit font_path for this system.")
    font = ImageFont.truetype(str(font_path), 32)
    small = ImageFont.truetype(str(font_path), 23)
    image = Image.new("RGB", (1920, 1080), "#101821")
    draw = ImageDraw.Draw(image)
    draw.text((70, 25), "合成 OCR 测试图 · 非真实游戏截图", font=font, fill="#59d8bc")
    catalog = Catalog()
    ids = ["Garen", "Jinx", "Lux", "Malphite", "Soraka", "Yasuo", "Ahri", "Darius", "Ezreal", "Thresh"]
    for index, cid in enumerate(ids):
        x = 65 + (index % 5) * 360
        y = 110 + (index // 5) * 485
        draw.rounded_rectangle((x, y, x + 340, y + 415), radius=12, fill="#1d2d3d", outline="#35536a", width=2)
        draw.text((x + 22, y + 36), f"SAMPLE {index + 1:02}", font=font, fill="#6a8397")
        champion = catalog.champions[cid]
        # Use an official skin alias for one card to exercise skin-name matching.
        label = "神王 盖伦" if cid == "Garen" else champion["name"]
        draw.text((x + 18, y + 278), label, font=font, fill="#f2e3ac")
        draw.text((x + 18, y + 346), f"Player {index + 1:02}", font=small, fill="#c2ced9")
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)
    return ids


def create_selection_demo(target: Path):
    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 24)
    image = Image.new("RGB", (1920, 1080), "#101821")
    draw = ImageDraw.Draw(image)
    draw.text((600, 80), "合成选英雄 OCR 测试图 · 非真实游戏截图", font=font, fill="#59d8bc")
    catalog = Catalog()
    ids = ["Zoe", "Xerath", "Karthus", "Gragas", "Hwei"]
    for slot, cid in enumerate(ids):
        y = 190 + slot * 120
        draw.rectangle((28, y-45, 550, y+70), fill="#1d2d3d", outline="#35536a")
        name = catalog.champions[cid]["title" if cid == "Gragas" else "name"]
        draw.text((190, y), name, anchor="lm", font=font, fill="#f2e3ac")
        draw.text((190, y+32), f"Player {slot+1}", anchor="lm", font=font, fill="#6a8397")
    draw.text((1800, 590), "赵信", font=font, fill="#f2e3ac")
    draw.text((190, 900), "聊天：盖伦", font=font, fill="#f2e3ac")
    draw.text((960, 710), "赏金猎人 卡特琳娜", anchor="mm", font=font, fill="#f2e3ac")
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)
    return ["Katarina"]


if __name__ == "__main__":
    target = ROOT / "examples" / "selection_demo.png"
    create_selection_demo(target)
    print(target)
