"""Generate the PWA icons (no design dependency — a simple ink tile with 'N')."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "webapp" / "icons"
OUT.mkdir(parents=True, exist_ok=True)
INK = (15, 23, 42)        # #0f172a
PAPER = (226, 232, 240)   # #e2e8f0


def make(size, name):
    img = Image.new("RGB", (size, size), INK)
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", int(size * 0.56))
    except OSError:
        font = ImageFont.load_default()
    d.text((size / 2, size / 2), "N", fill=PAPER, font=font, anchor="mm")
    img.save(OUT / name)


for size, name in [(192, "icon-192.png"), (512, "icon-512.png"),
                   (180, "apple-touch-icon.png")]:
    make(size, name)
print("icons written to", OUT)
