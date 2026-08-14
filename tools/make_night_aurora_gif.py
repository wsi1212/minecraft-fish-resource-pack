"""Make a smooth, composited aurora GIF preview from a night-sky master."""

from math import cos, pi, sin
from pathlib import Path

from PIL import Image, ImageEnhance


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools/imagegen-source/aurora-final-night-master.png"
OUTPUT = ROOT / "tools/imagegen-source/aurora-final-night-animation.gif"
FRAMES = 12
PREVIEW_SIZE = (768, 512)


def translated(image: Image.Image, dx: int, dy: int) -> Image.Image:
    out = Image.new("RGBA", image.size, (0, 0, 0, 0))
    w, h = image.size
    left = max(0, -dx)
    top = max(0, -dy)
    right = min(w, w - dx)
    bottom = min(h, h - dy)
    if right > left and bottom > top:
        crop = image.crop((left, top, right, bottom))
        out.paste(crop, (left + dx, top + dy))
    return out


def main() -> None:
    with Image.open(SOURCE) as loaded:
        master = loaded.convert("RGBA")

    frames: list[Image.Image] = []
    for frame in range(FRAMES):
        phase = 2 * pi * frame / FRAMES
        moved = translated(master, round(3 * sin(phase)), round(2 * cos(phase)))
        # Restrained shimmer only; the silhouette stays stable and the motion
        # reads as breathing light instead of a frame swap.
        rgb = ImageEnhance.Brightness(moved.convert("RGB")).enhance(
            1.0 + 0.025 * sin(phase)
        )
        small = rgb.resize(PREVIEW_SIZE, Image.Resampling.LANCZOS)
        frames.append(small.quantize(colors=256, method=Image.Quantize.MEDIANCUT))

    frames[0].save(
        OUTPUT,
        save_all=True,
        append_images=frames[1:],
        duration=1200,
        loop=0,
        disposal=2,
        optimize=False,
    )
    print(f"Wrote {OUTPUT} ({FRAMES} frames, 1200 ms/frame)")


if __name__ == "__main__":
    main()
