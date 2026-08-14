"""Create the final transparent-tile aurora GIF preview."""

from math import cos, pi, sin
from pathlib import Path

from PIL import Image, ImageEnhance


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools/imagegen-source/aurora-final-night-transparent.png"
OUTPUT = ROOT / "tools/imagegen-source/aurora-final-transparent-animation.gif"
FRAMES = 12
MASTER_SIZE = (2960, 2016)
PREVIEW_SIZE = (768, 523)
NIGHT = (5, 10, 28, 255)


def translated(image: Image.Image, dx: int, dy: int) -> Image.Image:
    result = Image.new("RGBA", image.size, (0, 0, 0, 0))
    width, height = image.size
    left = max(0, -dx)
    top = max(0, -dy)
    right = min(width, width - dx)
    bottom = min(height, height - dy)
    if right <= left or bottom <= top:
        return result
    crop = image.crop((left, top, right, bottom))
    result.paste(crop, (left + dx, top + dy), crop)
    return result


def animate(master: Image.Image, frame: int) -> Image.Image:
    phase = 2.0 * pi * frame / FRAMES
    moved = translated(master, round(3.0 * sin(phase)), round(2.0 * cos(phase)))
    rgb = ImageEnhance.Brightness(moved.convert("RGB")).enhance(
        1.0 + 0.025 * sin(phase)
    )
    alpha = moved.getchannel("A").point(
        lambda value: max(0, min(255, round(value * (1.0 + 0.015 * cos(phase)))))
    )
    rgb.putalpha(alpha)
    return rgb


def main() -> None:
    with Image.open(SOURCE) as loaded:
        master = loaded.convert("RGBA").resize(MASTER_SIZE, Image.Resampling.LANCZOS)

    frames: list[Image.Image] = []
    for frame in range(FRAMES):
        small = animate(master, frame).resize(PREVIEW_SIZE, Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", PREVIEW_SIZE, NIGHT)
        canvas.alpha_composite(small)
        frames.append(canvas.convert("RGB").quantize(colors=256, method=Image.Quantize.MEDIANCUT))

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
