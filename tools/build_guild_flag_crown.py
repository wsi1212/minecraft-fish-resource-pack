#!/usr/bin/env python3
"""Build the 16px back-panel art for the guild banner.

The front panel is a dynamic guild emblem.  The reverse is deliberately static:
a navy cloth field with a readable three-point gold crown, shaded from top-left.
"""
from pathlib import Path
from PIL import Image, ImageDraw

# The flag body otherwise uses block-atlas textures (wood, wool, gold).  Keep the
# crown in that same atlas: mixing item + block atlases makes 1.21.11 reject the
# entire model and show the purple-black missing-model checkerboard.
OUT = Path(__file__).parents[1] / "assets/barkan/textures/block/guild_flag_crown.png"

# Navy cloth: cool shadows and a restrained top-left highlight.
SHADOW = "#171d53"
BASE = "#222b78"
LIT = "#34429c"
GOLD_OUTLINE = "#776602"
GOLD_SHADOW = "#9e7e0a"
GOLD = "#c69214"
GOLD_LIGHT = "#eea321"
GEM = "#4fc3d8"


def build() -> Image.Image:
    image = Image.new("RGBA", (16, 16), BASE)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 15, 1), fill=LIT)
    draw.rectangle((0, 14, 15, 15), fill=SHADOW)
    draw.rectangle((0, 0, 1, 15), fill=SHADOW)
    draw.rectangle((14, 0, 15, 15), fill="#1b2364")

    # 8×8 heraldic crown: two low outer tips, one high centre tip, and a thin band.
    # This is the compact silhouette used by readable Minecraft rank/badge icons.
    outer = [(4, 5), (5, 5), (6, 7), (7, 3), (8, 3), (9, 7),
             (10, 5), (11, 5), (10, 9), (11, 9), (11, 11),
             (4, 11), (4, 9), (5, 9)]
    draw.polygon(outer, fill=GOLD_OUTLINE)
    inner = [(5, 6), (6, 8), (7, 4), (8, 8), (10, 6),
             (9, 9), (6, 9)]
    draw.polygon(inner, fill=GOLD)
    draw.rectangle((5, 9, 10, 10), fill=GOLD_SHADOW)
    draw.rectangle((5, 9, 10, 9), fill=GOLD_LIGHT)
    draw.rectangle((6, 10, 9, 10), fill=GOLD)
    # Highlights follow the same top-left light source without flattening the form.
    draw.line([(5, 6), (6, 8)], fill=GOLD_LIGHT)
    draw.line([(7, 4), (7, 6)], fill=GOLD_LIGHT)
    draw.point((10, 6), fill=GOLD_LIGHT)
    draw.point((8, 10), fill=GEM)
    return image


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    build().save(OUT)
    print(OUT)
