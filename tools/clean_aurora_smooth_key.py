"""Key the smooth aurora generation while preserving its cyan light."""

from collections import deque
from pathlib import Path

from PIL import Image, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools/imagegen-source/aurora-smooth-source.png"
OUTPUT = ROOT / "tools/imagegen-source/aurora-smooth-transparent.png"
KEY = (13, 248, 7)
KEY_DISTANCE = 54
SOFT_DISTANCE = 150


def distance(rgb: tuple[int, int, int]) -> int:
    return max(abs(rgb[0] - KEY[0]), abs(rgb[1] - KEY[1]), abs(rgb[2] - KEY[2]))


def smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def main() -> None:
    with Image.open(SOURCE) as loaded:
        image = loaded.convert("RGBA")
    width, height = image.size
    pixels = image.load()
    total = width * height

    eligible = bytearray(total)
    for y in range(height):
        for x in range(width):
            eligible[y * width + x] = distance(pixels[x, y][:3]) <= KEY_DISTANCE

    background = bytearray(total)
    queue: deque[int] = deque()

    def seed(index: int) -> None:
        if eligible[index] and not background[index]:
            background[index] = 1
            queue.append(index)

    for x in range(width):
        seed(x)
        seed((height - 1) * width + x)
    for y in range(height):
        seed(y * width)
        seed(y * width + width - 1)

    while queue:
        index = queue.popleft()
        x = index % width
        y = index // width
        if x:
            seed(index - 1)
        if x + 1 < width:
            seed(index + 1)
        if y:
            seed(index - width)
        if y + 1 < height:
            seed(index + width)

    # Use the distance to the connected green screen for a broad, soft alpha
    # ramp. The smooth source already has clean geometry, so no hard erosion.
    alpha = Image.new("L", (width, height), 255)
    alpha_pixels = alpha.load()
    for y in range(height):
        for x in range(width):
            index = y * width + x
            if background[index]:
                alpha_pixels[x, y] = 0
                continue

            # Only subject pixels immediately touching the keyed area need a
            # soft ramp. A 5x5 neighbourhood avoids a one-pixel cut line.
            near = False
            for oy in range(-2, 3):
                ny = y + oy
                if ny < 0 or ny >= height:
                    continue
                for ox in range(-2, 3):
                    nx = x + ox
                    if 0 <= nx < width and background[ny * width + nx]:
                        near = True
                        break
                if near:
                    break
            if near:
                d = distance(pixels[x, y][:3])
                alpha_pixels[x, y] = round(
                    255 * smoothstep((d - KEY_DISTANCE) / (SOFT_DISTANCE - KEY_DISTANCE))
                )

    alpha = alpha.filter(ImageFilter.GaussianBlur(radius=1.15))
    image.putalpha(alpha)
    image_pixels = image.load()
    for y in range(height):
        for x in range(width):
            if alpha_pixels[x, y] == 0:
                image_pixels[x, y] = (0, 0, 0, 0)

    image.save(OUTPUT, optimize=True)
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
