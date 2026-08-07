#!/usr/bin/env python3
"""Build the first five Barkan skill-tree badge icons.

The art is intentionally deterministic and pixel-native: no antialiasing, no
semi-transparent pixels, and every icon keeps the same badge silhouette while
owning a different central glyph.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

SKILL_ROOT = Path("/Users/user/Library/Application Support/feather/player-server/servers/07de2d81-991a-47e2-b62d-06c0d1b5150a/plugins/Skript/scripts/.agents/skills/item-icons")
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
from iconlib import canvas, disk, put, selout, sparkle  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = Path(__file__).with_name("manifest.json")
TEXTURES = ROOT / "assets/minecraft/textures/item/barkan_icon"
MODELS = ROOT / "assets/barkan/models/barkan_icon"
ITEMS = ROOT / "assets/barkan/items/barkan_icon"
PREVIEW = Path(__file__).with_name("skill-icons-preview-32.png")


def rect(im: Image.Image, x0: int, y0: int, x1: int, y1: int, col: str) -> None:
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            put(im, x, y, col)


def pixels(im: Image.Image, coords: list[tuple[int, int]], col: str) -> None:
    for x, y in coords:
        put(im, x, y, col)


def badge(palette: list[str]) -> Image.Image:
    dark, base, light, glyph, sparkle_col = palette
    im = canvas(16)
    # Dark selout first; the inner field is vertically shaded toward the fixed
    # upper-left light source instead of pillow-shading the center.
    disk(im, 7.5, 7.5, 7.1, dark)
    for y in range(1, 15):
        for x in range(1, 15):
            if (x - 7.5) ** 2 + (y - 7.5) ** 2 <= 6.1 ** 2:
                col = light if y <= 4 else base if y <= 10 else dark
                put(im, x, y, col)
    # Selective rim highlights; lower-right stays dark.
    pixels(im, [(4, 2), (5, 1), (6, 1), (7, 1), (3, 3)], light)
    selout(im, dark, light)
    return im


def fish(im: Image.Image, p: list[str]) -> None:
    dark, _, _, glyph, hi = p
    outline = [(5, 6), (6, 5), (9, 5), (10, 6), (12, 5), (11, 7), (12, 9),
               (10, 8), (9, 9), (6, 9), (5, 8), (4, 8), (5, 7)]
    pixels(im, outline, dark)
    pixels(im, [(6, 6), (7, 6), (8, 6), (9, 6), (6, 7), (7, 7), (8, 7),
                (9, 7), (10, 7), (6, 8), (7, 8), (8, 8), (9, 8)], glyph)
    put(im, 8, 6, hi)
    put(im, 10, 7, dark)
    # Two quiet water pixels are part of the fish glyph, not a second object.
    pixels(im, [(4, 10), (5, 10), (6, 10), (9, 11), (10, 11), (11, 11)], hi)


def spyglass(im: Image.Image, p: list[str]) -> None:
    dark, _, _, glyph, hi = p
    pixels(im, [(4, 10), (5, 9), (6, 8), (7, 7), (8, 6), (9, 5),
                (10, 4), (11, 3), (12, 4), (12, 6), (11, 7),
                (10, 7), (9, 8), (8, 9), (7, 10)], dark)
    pixels(im, [(5, 9), (6, 8), (7, 7), (8, 6), (9, 5), (10, 4),
                (10, 5), (9, 6), (8, 7), (7, 8)], glyph)
    disk(im, 10.5, 5, 2.0, dark)
    disk(im, 10.5, 5, 1.0, hi)
    pixels(im, [(4, 10), (5, 11), (6, 11)], glyph)
    put(im, 11, 4, hi)


def wheat(im: Image.Image, p: list[str]) -> None:
    dark, _, _, glyph, hi = p
    pixels(im, [(7, 12), (7, 11), (7, 10), (7, 9), (7, 8), (8, 7),
                (8, 6), (8, 5), (8, 4), (7, 4), (6, 5), (6, 6),
                (9, 6), (9, 7), (6, 8), (5, 8), (9, 9), (10, 9),
                (5, 10), (6, 10)], dark)
    pixels(im, [(7, 12), (7, 11), (7, 10), (7, 9), (7, 8), (8, 7),
                (8, 6), (8, 5), (8, 4), (6, 5), (6, 6), (9, 6),
                (9, 7), (6, 8), (5, 8), (9, 9), (10, 9), (5, 10)], glyph)
    pixels(im, [(8, 4), (6, 5), (9, 6), (5, 8), (10, 9)], hi)


def crown(im: Image.Image, p: list[str]) -> None:
    dark, _, _, glyph, hi = p
    outline = [(4, 5), (5, 6), (6, 4), (8, 6), (10, 4), (11, 6),
               (12, 5), (11, 10), (5, 10)]
    pixels(im, outline, dark)
    pixels(im, [(5, 6), (6, 6), (6, 5), (7, 7), (8, 7), (9, 7),
                (10, 5), (10, 6), (11, 6), (10, 8), (6, 8), (7, 8),
                (8, 8), (9, 8), (10, 8), (6, 9), (7, 9), (8, 9),
                (9, 9), (10, 9)], glyph)
    pixels(im, [(6, 5), (10, 5), (8, 7)], hi)
    sparkle(im, 8, 3, hi, arm=0)


def eye(im: Image.Image, p: list[str]) -> None:
    dark, _, _, glyph, hi = p
    outline = [(3, 8), (4, 7), (5, 6), (6, 5), (9, 5), (10, 6),
               (11, 7), (12, 8), (11, 9), (10, 10), (9, 11), (6, 11),
               (5, 10), (4, 9)]
    pixels(im, outline, dark)
    pixels(im, [(5, 7), (6, 6), (7, 6), (8, 6), (9, 6), (10, 7),
                (11, 8), (10, 8), (10, 9), (9, 10), (8, 10), (7, 10),
                (6, 9), (5, 9), (4, 8)], glyph)
    disk(im, 8, 8, 2.0, dark)
    disk(im, 8, 8, 1.0, hi)
    put(im, 8, 8, glyph)
    sparkle(im, 12, 4, hi, arm=0)


PAINTERS = {
    "skill_fishing_root": fish,
    "skill_mining_scan": spyglass,
    "skill_farming_bounty": wheat,
    "skill_cooking_master": crown,
    "skill_gather_intuition": eye,
}


def render(icon: dict) -> Image.Image:
    im = badge(icon["palette"])
    PAINTERS[icon["id"]](im, icon["palette"])
    im = im.resize((32, 32), Image.Resampling.NEAREST)
    add_32px_detail(im, icon["id"], icon["palette"])
    return im


def add_32px_detail(im: Image.Image, icon_id: str, p: list[str]) -> None:
    """Add readable 32px-only accents after the 16px silhouette is enlarged."""
    dark, _, _, glyph, hi = p
    if icon_id == "skill_fishing_root":
        # Fish eye, fin separation, scale glints, and a clear two-line ripple.
        rect(im, 19, 12, 21, 14, dark)
        rect(im, 17, 16, 19, 17, hi)
        rect(im, 13, 14, 14, 15, hi)
        rect(im, 15, 17, 16, 18, hi)
        rect(im, 8, 21, 17, 21, hi)
        rect(im, 21, 23, 27, 23, hi)
    elif icon_id == "skill_mining_scan":
        # Spyglass lens rim and segmented handle make the object read as a tool.
        rect(im, 20, 7, 23, 8, hi)
        rect(im, 23, 9, 24, 12, hi)
        rect(im, 13, 18, 15, 19, glyph)
        rect(im, 10, 21, 12, 22, dark)
        rect(im, 13, 21, 15, 22, glyph)
    elif icon_id == "skill_farming_bounty":
        # Seed marks on the grain heads and a split stem add a readable sheaf.
        rect(im, 15, 7, 17, 8, hi)
        rect(im, 11, 10, 13, 11, hi)
        rect(im, 18, 12, 20, 13, hi)
        rect(im, 10, 16, 12, 17, hi)
        rect(im, 19, 18, 21, 19, hi)
        rect(im, 14, 20, 15, 25, glyph)
    elif icon_id == "skill_cooking_master":
        # Crown points, band, and central jewel; a single crown glyph remains dominant.
        rect(im, 10, 11, 12, 13, hi)
        rect(im, 14, 13, 17, 14, hi)
        rect(im, 20, 11, 22, 13, hi)
        rect(im, 12, 18, 21, 19, hi)
        rect(im, 15, 16, 17, 18, dark)
        rect(im, 16, 16, 16, 17, hi)
    elif icon_id == "skill_gather_intuition":
        # Larger iris ring and two catchlights make the eye legible at GUI scale.
        rect(im, 13, 14, 14, 17, hi)
        rect(im, 18, 14, 19, 17, hi)
        rect(im, 15, 15, 17, 16, dark)
        rect(im, 16, 15, 17, 16, hi)
        rect(im, 24, 8, 25, 9, hi)


def preview_32(paths: list[Path], out: Path) -> None:
    """Show the 32px icons on 34px inventory slots, enlarged for inspection."""
    from PIL import ImageDraw
    slot = 34
    pad = 8
    gap = 4
    board = Image.new("RGBA", (pad * 2 + len(paths) * slot + (len(paths) - 1) * gap,
                                pad * 2 + slot), (198, 198, 198, 255))
    draw = ImageDraw.Draw(board)
    for i, path in enumerate(paths):
        x0 = pad + i * (slot + gap)
        y0 = pad
        draw.rectangle((x0, y0, x0 + slot - 1, y0 + slot - 1), fill=(139, 139, 139, 255), outline=(55, 55, 55, 255), width=1)
        draw.line((x0 + 1, y0 + slot - 2, x0 + slot - 2, y0 + slot - 2), fill=(255, 255, 255, 255), width=1)
        draw.line((x0 + slot - 2, y0 + 1, x0 + slot - 2, y0 + slot - 2), fill=(255, 255, 255, 255), width=1)
        board.alpha_composite(Image.open(path).convert("RGBA"), (x0 + 1, y0 + 1))
    board.resize((board.width * 4, board.height * 4), Image.Resampling.NEAREST).save(out)
    print(f"32px 슬롯 목업 → {out} (5칸)")


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    TEXTURES.mkdir(parents=True, exist_ok=True)
    MODELS.mkdir(parents=True, exist_ok=True)
    ITEMS.mkdir(parents=True, exist_ok=True)
    icons = []
    texture_paths = []
    for icon in manifest["icons"]:
        im = render(icon)
        out = TEXTURES / f"{icon['id']}.png"
        im.save(out)
        texture_paths.append(out)
        (MODELS / f"{icon['id']}.json").write_text(json.dumps({
            "parent": "minecraft:item/generated",
            "textures": {"layer0": f"minecraft:item/barkan_icon/{icon['id']}"}
        }, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        (ITEMS / f"{icon['id']}.json").write_text(json.dumps({
            "model": {"type": "minecraft:model", "model": f"barkan:barkan_icon/{icon['id']}"}
        }, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        icons.append(im)

    preview_32(texture_paths, PREVIEW)
    print(f"built {len(icons)} skill icons")


if __name__ == "__main__":
    main()
