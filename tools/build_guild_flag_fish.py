#!/usr/bin/env python3
"""Draw the compact reverse-side fish emblem for the guild flag (16×16)."""
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).parents[1]
OUT = ROOT / "assets/barkan/textures/block/guild_flag_fish.png"
PREVIEW = Path("/tmp/guild-flag-fish-preview.png")

NAVY_DARK = "#171d53"
NAVY = "#222b78"
NAVY_LIGHT = "#34429c"
FISH_OUTLINE = "#14213d"
FISH_SHADOW = "#355477"
FISH_BASE = "#6696bb"
FISH_LIGHT = "#c4e9ef"
FISH_FIN = "#496e93"
EYE = "#f3c645"


def fish_tile() -> Image.Image:
    image = Image.new("RGBA", (16, 16), NAVY)
    draw = ImageDraw.Draw(image)
    # Same quiet cloth field as the current banner; the emblem itself stays 8×6.
    draw.rectangle((0, 0, 15, 1), fill=NAVY_LIGHT)
    draw.rectangle((0, 14, 15, 15), fill=NAVY_DARK)
    draw.rectangle((0, 0, 1, 15), fill=NAVY_DARK)
    draw.rectangle((14, 0, 15, 15), fill="#1b2364")

    # Right-facing fish: readable tail fork, oval body and one dorsal fin at tiny scale.
    outline = [(4, 7), (5, 6), (7, 6), (9, 7),
               (11, 5), (10, 8), (11, 11), (9, 9),
               (7, 10), (5, 10), (4, 9)]
    draw.polygon(outline, fill=FISH_OUTLINE)
    body = [(5, 7), (6, 7), (8, 7), (9, 8), (7, 9), (5, 9)]
    draw.polygon(body, fill=FISH_BASE)
    # Tail is a separate darker fin so the fork stays readable against navy cloth.
    draw.polygon([(9, 7), (10, 6), (10, 8), (10, 10), (9, 9)], fill=FISH_FIN)
    draw.point((10, 6), fill=FISH_LIGHT)
    draw.line([(6, 7), (6, 8), (8, 8)], fill=FISH_LIGHT)
    draw.line([(5, 9), (8, 9)], fill=FISH_SHADOW)
    draw.polygon([(7, 6), (7, 5), (8, 6)], fill=FISH_FIN)
    draw.point((5, 7), fill=EYE)
    return image


def banner_preview(tile: Image.Image) -> Image.Image:
    """A proportional banner-face mockup: 10×16 cloth pixels inside its gold frame."""
    scale = 20
    preview = Image.new("RGBA", (14 * scale, 20 * scale), "#2a1a0f")
    draw = ImageDraw.Draw(preview)
    draw.rectangle((1 * scale, 1 * scale, 12 * scale - 1, 18 * scale - 1), fill="#b98b18")
    panel = tile.crop((3, 0, 13, 16)).resize((10 * scale, 16 * scale), Image.Resampling.NEAREST)
    preview.alpha_composite(panel, (2 * scale, 2 * scale))
    return preview


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tile = fish_tile()
    tile.save(OUT)
    banner_preview(tile).save(PREVIEW)
    print(OUT)
    print(PREVIEW)
