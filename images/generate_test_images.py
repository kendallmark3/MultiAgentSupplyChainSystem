"""
generate_test_images.py — Creates synthetic warehouse shelf test images.

Each image has a known ground-truth item count, making vision agent
output directly verifiable. Run once to regenerate all images:
    python images/generate_test_images.py

Images generated:
    shelf_0_items.jpg         Empty shelf — tests zero-count edge case
    shelf_1_item.jpg          Single box — tests minimum detection
    shelf_3_items.jpg         3 boxes in a row
    shelf_5_items.jpg         5 boxes, two rows
    shelf_8_items.jpg         8 boxes, mixed sizes
    shelf_12_items.jpg        12 boxes, dense shelf
    shelf_15_items.jpg        15 boxes, full warehouse shelf
    shelf_mixed_types.jpg     Boxes + cylinders — tests multi-type detection
    shelf_dark.jpg            Low-light shelf — tests robustness
    shelf_cluttered.jpg       Overlapping items — tests occlusion handling
    shelf_single_row_10.jpg   10 boxes in a single long row
    shelf_tall_stack.jpg      Stacked column of 6 boxes
"""

import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

OUT_DIR = Path(__file__).parent
OUT_DIR.mkdir(exist_ok=True)

W, H = 800, 500


def shelf_bg(draw, rows=2, color=(210, 190, 160)):
    """Draw shelf planks as background."""
    draw.rectangle([0, 0, W, H], fill=(180, 170, 150))
    for i in range(rows + 1):
        y = 60 + i * ((H - 80) // rows)
        draw.rectangle([0, y - 6, W, y + 6], fill=(140, 120, 90))
    draw.rectangle([0, 0, W, 60], fill=(100, 85, 65))
    draw.rectangle([0, H - 30, W, H], fill=(100, 85, 65))


def box(draw, x, y, w, h, shade=0):
    """Draw a cardboard box with basic shading."""
    r = random.randint
    base = (r(180, 220), r(140, 170), r(80, 110))
    dark = (base[0] - 30, base[1] - 25, base[2] - 15)
    light = (min(255, base[0] + 20), min(255, base[1] + 15), min(255, base[2] + 10))
    draw.rectangle([x, y, x + w, y + h], fill=base)
    draw.rectangle([x, y, x + w, y + 8], fill=light)
    draw.rectangle([x, y, x + 8, y + h], fill=light)
    draw.rectangle([x + w - 8, y, x + w, y + h], fill=dark)
    draw.rectangle([x, y + h - 8, x + w, y + h], fill=dark)
    draw.rectangle([x, y, x + w, y + h], outline=(80, 60, 30), width=2)
    mx = x + w // 2
    draw.line([mx, y, mx, y + h], fill=(80, 60, 30), width=1)
    draw.line([x, y + h // 3, x + w, y + h // 3], fill=(80, 60, 30), width=1)


def cylinder(draw, x, y, w, h):
    """Draw a cylindrical container (barrel/can)."""
    r = random.randint
    col = (r(60, 100), r(80, 130), r(140, 200))
    draw.ellipse([x, y, x + w, y + 20], fill=col, outline=(30, 30, 30), width=2)
    draw.rectangle([x, y + 10, x + w, y + h], fill=col, outline=None)
    draw.ellipse([x, y + h - 10, x + w, y + h + 10], fill=(col[0]-20, col[1]-20, col[2]-20), outline=(30, 30, 30), width=2)
    draw.rectangle([x, y + 10, x + w, y + h], outline=None)
    draw.line([x, y + 10, x, y + h], fill=(30, 30, 30), width=2)
    draw.line([x + w, y + 10, x + w, y + h], fill=(30, 30, 30), width=2)


def label(img, filename, count):
    """Add ground truth label to bottom-left corner."""
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, H - 30, 300, H], fill=(0, 0, 0, 180))
    draw.text((8, H - 24), f"Ground truth: {count} item{'s' if count != 1 else ''}  |  {filename}", fill=(255, 255, 0))


def save(img, name, count):
    path = OUT_DIR / name
    label(img, name, count)
    img.save(path, "JPEG", quality=92)
    print(f"  {name:35s}  ({count} items)")


# ── 1. Empty shelf ─────────────────────────────────────────────
img = Image.new("RGB", (W, H))
d = ImageDraw.Draw(img)
shelf_bg(d, rows=2)
save(img, "shelf_0_items.jpg", 0)

# ── 2. Single box ──────────────────────────────────────────────
img = Image.new("RGB", (W, H))
d = ImageDraw.Draw(img)
shelf_bg(d, rows=2)
box(d, 320, 200, 120, 110)
save(img, "shelf_1_item.jpg", 1)

# ── 3. Three boxes in a row ────────────────────────────────────
img = Image.new("RGB", (W, H))
d = ImageDraw.Draw(img)
shelf_bg(d, rows=2)
for i in range(3):
    box(d, 100 + i * 200, 200, 130, 120)
save(img, "shelf_3_items.jpg", 3)

# ── 4. Five boxes, two rows ────────────────────────────────────
img = Image.new("RGB", (W, H))
d = ImageDraw.Draw(img)
shelf_bg(d, rows=2)
for i in range(3):
    box(d, 80 + i * 210, 90, 120, 100)
for i in range(2):
    box(d, 180 + i * 240, 290, 130, 110)
save(img, "shelf_5_items.jpg", 5)

# ── 5. Eight boxes, mixed sizes ────────────────────────────────
img = Image.new("RGB", (W, H))
d = ImageDraw.Draw(img)
shelf_bg(d, rows=2)
positions = [
    (40, 90, 100, 95), (155, 85, 130, 100), (300, 90, 90, 90),
    (405, 80, 140, 105), (560, 85, 110, 100), (685, 88, 95, 97),
    (80, 295, 120, 110), (320, 290, 150, 115),
]
for (x, y, w, h) in positions:
    box(d, x, y, w, h)
save(img, "shelf_8_items.jpg", 8)

# ── 6. Twelve boxes, dense shelf ──────────────────────────────
img = Image.new("RGB", (W, H))
d = ImageDraw.Draw(img)
shelf_bg(d, rows=3)
row_y = [75, 220, 365]
for ry in row_y:
    for i in range(4):
        box(d, 20 + i * 192, ry, 160, 95)
save(img, "shelf_12_items.jpg", 12)

# ── 7. Fifteen boxes, full warehouse shelf ─────────────────────
img = Image.new("RGB", (W, H))
d = ImageDraw.Draw(img)
shelf_bg(d, rows=3)
row_y = [70, 215, 360]
cols = [5, 5, 5]
for ry, n in zip(row_y, cols):
    for i in range(n):
        box(d, 10 + i * 156, ry, 136, 90)
save(img, "shelf_15_items.jpg", 15)

# ── 8. Mixed types: boxes + cylinders ─────────────────────────
img = Image.new("RGB", (W, H))
d = ImageDraw.Draw(img)
shelf_bg(d, rows=2)
box(d, 30,  100, 110, 100)
box(d, 160, 95,  120, 105)
cylinder(d, 310, 100, 80, 110)
cylinder(d, 420, 95,  75, 115)
box(d, 530, 100, 100, 100)
box(d, 50,  305, 120, 105)
cylinder(d, 210, 300, 85, 110)
box(d, 340, 305, 130, 110)
cylinder(d, 510, 300, 80, 115)
save(img, "shelf_mixed_types.jpg", 9)

# ── 9. Low-light shelf ────────────────────────────────────────
img = Image.new("RGB", (W, H))
d = ImageDraw.Draw(img)
shelf_bg(d)
for i in range(4):
    box(d, 50 + i * 180, 180, 130, 120)
dark_overlay = Image.new("RGBA", (W, H), (0, 0, 0, 140))
img = img.convert("RGBA")
img = Image.alpha_composite(img, dark_overlay).convert("RGB")
save(img, "shelf_dark.jpg", 4)

# ── 10. Cluttered / overlapping ───────────────────────────────
img = Image.new("RGB", (W, H))
d = ImageDraw.Draw(img)
shelf_bg(d)
positions_overlap = [
    (30,  170, 140, 130),
    (110, 155, 130, 125),
    (230, 165, 145, 130),
    (340, 155, 135, 140),
    (450, 170, 130, 125),
    (545, 160, 140, 135),
    (640, 165, 130, 125),
]
for (x, y, w, h) in positions_overlap:
    box(d, x, y, w, h)
save(img, "shelf_cluttered.jpg", 7)

# ── 11. Single long row of 10 ─────────────────────────────────
img = Image.new("RGB", (W, H))
d = ImageDraw.Draw(img)
shelf_bg(d, rows=1)
for i in range(10):
    box(d, 5 + i * 79, 180, 68, 110)
save(img, "shelf_single_row_10.jpg", 10)

# ── 12. Tall stacked column ───────────────────────────────────
img = Image.new("RGB", (W, H))
d = ImageDraw.Draw(img)
shelf_bg(d, rows=4)
for i in range(6):
    box(d, 310, 30 + i * 74, 150, 64)
save(img, "shelf_tall_stack.jpg", 6)

print()
print(f"Generated 12 test images in {OUT_DIR}/")
print("Upload any to http://localhost:8080 to test the vision agent.")
