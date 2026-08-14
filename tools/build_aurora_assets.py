"""Build the aurora bitmap-font tiles from one master image.

The bitmap font uses 185x196 pixels per tile.  The master is intentionally
stretched vertically before cutting so the Minecraft font provider and the
TextDisplay transform use one uniform scale on both axes.  That keeps row
boundaries pixel-perfect instead of relying on a non-uniform display scale.
"""

from math import cos, pi, sin
import json
from pathlib import Path

from PIL import Image, ImageEnhance


ROOT = Path(__file__).resolve().parents[1]
# Final night-sky master with the navy backdrop extracted into a soft alpha
# matte. This avoids the green/cyan chroma-key damage from earlier passes.
SOURCE = ROOT / "tools/imagegen-source/aurora-final-night-transparent.png"
OUT_DIR = ROOT / "assets/barkan/textures/font"
FONT_JSON = ROOT / "assets/barkan/font/aurora.json"

FRAMES = 12
COLS = 8
ROWS = 8
FULL_SIZE = (1480, 1568)
TILE_SIZE = (FULL_SIZE[0] // COLS, FULL_SIZE[1] // ROWS)
SPACER_BASE = 0xE400


def translated(image: Image.Image, dx: int, dy: int) -> Image.Image:
    """Translate an RGBA image without wrapping its edges around."""

    width, height = image.size
    result = Image.new("RGBA", image.size, (0, 0, 0, 0))
    src_left = max(0, -dx)
    src_top = max(0, -dy)
    src_right = min(width, width - dx)
    src_bottom = min(height, height - dy)
    if src_right <= src_left or src_bottom <= src_top:
        return result
    crop = image.crop((src_left, src_top, src_right, src_bottom))
    result.paste(crop, (src_left + dx, src_top + dy), crop)
    return result


def modulate(image: Image.Image, brightness: float, alpha_scale: float) -> Image.Image:
    """Apply a restrained global shimmer while preserving the alpha silhouette."""

    rgb = ImageEnhance.Brightness(image.convert("RGB")).enhance(brightness)
    alpha = image.getchannel("A").point(
        lambda value: max(0, min(255, round(value * alpha_scale)))
    )
    rgb.putalpha(alpha)
    return rgb


def bitmap_provider_advance(tile: Image.Image) -> int:
    """Match Minecraft BitmapProvider's rightmost-opaque-pixel advance."""

    bbox = tile.getchannel("A").getbbox()
    rightmost = bbox[2] if bbox else 0
    return rightmost + 1


def main() -> None:
    if not SOURCE.is_file():
        raise SystemExit(f"Missing transparent master: {SOURCE}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    master = Image.open(SOURCE).convert("RGBA").resize(
        FULL_SIZE, Image.Resampling.LANCZOS
    )

    # Keep the legacy single-glyph fallback in sync with the new artwork.
    master.resize((256, 271), Image.Resampling.LANCZOS).save(
        OUT_DIR / "aurora_256.png", optimize=True
    )

    spacer_advances: list[int] = []
    for frame in range(FRAMES):
        phase = 2.0 * pi * frame / FRAMES
        # Only a few source pixels of movement: enough to breathe, not enough
        # to reveal a hard frame swap in the game.
        dx = round(4.0 * sin(phase))
        dy = round(2.0 * cos(phase))
        shifted = translated(master, dx, dy)
        animated = modulate(
            shifted,
            brightness=1.0 + 0.035 * sin(phase),
            alpha_scale=1.0 + 0.02 * cos(phase),
        )

        for tile in range(COLS * ROWS):
            row, col = divmod(tile, COLS)
            left = col * TILE_SIZE[0]
            top = row * TILE_SIZE[1]
            crop = animated.crop(
                (left, top, left + TILE_SIZE[0], top + TILE_SIZE[1])
            )
            crop.save(
                OUT_DIR / f"aurora_f{frame}_t{tile}.png",
                optimize=True,
            )
            spacer_advances.append(TILE_SIZE[0] - bitmap_provider_advance(crop))

    if len(spacer_advances) != FRAMES * COLS * ROWS:
        raise RuntimeError(f"Expected 768 spacer advances, got {len(spacer_advances)}")

    font = json.loads(FONT_JSON.read_text())
    space_provider = next(provider for provider in font["providers"] if provider["type"] == "space")
    advances = {"\ue00e": -1}
    for tile, advance in enumerate(spacer_advances):
        advances[chr(SPACER_BASE + tile)] = advance
    space_provider["advances"] = advances
    FONT_JSON.write_text(json.dumps(font, ensure_ascii=True, indent=2) + "\n")

    print(
        f"Built {FRAMES * COLS * ROWS} tiles at "
        f"{TILE_SIZE[0]}x{TILE_SIZE[1]} from {SOURCE.name}"
    )


if __name__ == "__main__":
    main()
