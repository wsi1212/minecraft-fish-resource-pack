#!/usr/bin/env python3
"""Build the slot-readable 학꽁치 (halfbeak) item texture.

The former photo-style 256px source became a near-transparent diagonal when
Minecraft minified it into a 16px inventory slot.  This source is deliberately
drawn on a 16px pixel grid, then enlarged without interpolation so the long
lower jaw, silver body, and forked tail all survive that minification.
"""
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets/minecraft/textures/item/fish/hagkkongchi.png"
SIZE = 16
SCALE = 16

# Fixed upper-left light, with a cool silver-blue halfbeak ramp.
OUTLINE = "#26313a"
DEEP = "#355361"
SHADOW = "#5f7f89"
SILVER = "#a9c4c7"
BELLY = "#d7e3d8"
HIGHLIGHT = "#f1f4df"
EYE = "#14212a"
IRIS = "#c6a25b"


def cells(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]], color: str) -> None:
    for x, y in points:
        draw.point((x, y), fill=color)


def build() -> Image.Image:
    icon = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(icon)

    # Silhouette: the fish faces left.  Its lower jaw is deliberately longer
    # than the upper snout; the forked tail occupies two full pixels vertically.
    outline = [(0, 6), (1, 6), (2, 5), (3, 5), (4, 4), (5, 4), (6, 4),
               (7, 5), (9, 5), (10, 6), (12, 6), (13, 7), (14, 5),
               (15, 5), (15, 8), (14, 9), (15, 12), (14, 12), (12, 10),
               (10, 10), (8, 9), (6, 9), (4, 8), (0, 8)]
    cells(draw, outline, OUTLINE)
    draw.polygon([(2, 6), (5, 5), (7, 5), (10, 6), (13, 8), (12, 9),
                  (9, 9), (6, 8), (4, 7), (0, 7)], fill=OUTLINE)

    # Silver body, a continuous blue dorsal band, and a distinct pale belly.
    draw.polygon([(4, 6), (6, 5), (9, 6), (12, 7), (13, 8), (11, 9),
                  (8, 8), (5, 7), (1, 7)], fill=SILVER)
    cells(draw, [(1, 7), (2, 7), (3, 7), (4, 7)], HIGHLIGHT)  # long lower jaw
    cells(draw, [(5, 5), (6, 5), (7, 6), (8, 6), (9, 6), (10, 7), (11, 7)], DEEP)
    cells(draw, [(6, 7), (7, 7), (8, 7), (9, 8), (10, 8), (11, 8)], BELLY)
    cells(draw, [(7, 7), (9, 7), (10, 7)], HIGHLIGHT)
    cells(draw, [(7, 8), (8, 8), (9, 9), (10, 9)], SHADOW)

    # Eye, operculum, and pectoral fin establish this as a fish at 16px.
    cells(draw, [(5, 6)], EYE)
    cells(draw, [(5, 5)], IRIS)
    cells(draw, [(6, 6), (6, 7)], SHADOW)
    cells(draw, [(8, 9), (9, 10)], DEEP)

    # The fork is filled rather than translucent so the lower tail cannot vanish.
    cells(draw, [(13, 7), (14, 6), (14, 7), (13, 8)], SILVER)
    cells(draw, [(13, 9), (14, 10), (14, 11)], SILVER)
    cells(draw, [(13, 8), (14, 8), (14, 9)], DEEP)
    cells(draw, [(15, 6), (15, 7), (15, 11)], OUTLINE)

    return icon


if __name__ == "__main__":
    icon = build()
    # Minecraft's generated-item renderer supports high-resolution textures;
    # nearest enlargement keeps this authored 16px grid intact.
    icon.resize((SIZE * SCALE, SIZE * SCALE), Image.Resampling.NEAREST).save(OUT)
    print(f"wrote {OUT}")
