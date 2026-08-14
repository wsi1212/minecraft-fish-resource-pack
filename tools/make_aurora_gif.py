"""Create a readable night-sky GIF preview of the aurora animation."""

from math import cos, pi, sin
from pathlib import Path

from PIL import Image

from build_aurora_assets import FRAMES, FULL_SIZE, SOURCE, modulate, translated


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "tools/imagegen-source/aurora-animation-preview.gif"
PREVIEW_SIZE = (768, 523)
NIGHT = (5, 10, 28, 255)


def main() -> None:
    with Image.open(SOURCE) as loaded:
        master = loaded.convert("RGBA").resize(FULL_SIZE, Image.Resampling.LANCZOS)

    frames: list[Image.Image] = []
    for frame in range(FRAMES):
        phase = 2.0 * pi * frame / FRAMES
        dx = round(4.0 * sin(phase))
        dy = round(2.0 * cos(phase))
        animated = modulate(
            translated(master, dx, dy),
            brightness=1.0 + 0.035 * sin(phase),
            alpha_scale=1.0 + 0.02 * cos(phase),
        )
        resized = animated.resize(PREVIEW_SIZE, Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", PREVIEW_SIZE, NIGHT)
        canvas.alpha_composite(resized)
        frames.append(canvas.convert("RGB").quantize(colors=256, method=Image.Quantize.MEDIANCUT))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        OUTPUT,
        save_all=True,
        append_images=frames[1:],
        duration=1200,
        loop=0,
        disposal=2,
        optimize=False,
    )
    print(f"Wrote {OUTPUT} ({PREVIEW_SIZE[0]}x{PREVIEW_SIZE[1]}, {FRAMES} frames)")


if __name__ == "__main__":
    main()
