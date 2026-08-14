"""Remove the green screen from the aurora without deleting green/cyan light.

The generic chroma-key helper intentionally removes key-coloured pixels
anywhere in the image.  That is unsafe for this aurora because some of its
cyan/teal light is close to the green key.  This pass only treats key-coloured
pixels connected to the outer border as background, so enclosed light keeps
its colour and opacity.
"""

from collections import deque
from pathlib import Path

from PIL import Image, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools/imagegen-source/aurora-large-source.png"
OUTPUT = ROOT / "tools/imagegen-source/aurora-large-transparent-clean.png"
KEY = (13, 248, 7)
KEY_DISTANCE = 82
EDGE_DISTANCE = 150
EDGE_RADIUS = 2


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
    count = width * height

    # Mark only pixels close enough to the key colour to be possible screen.
    eligible = bytearray(count)
    for y in range(height):
        row = y * width
        for x in range(width):
            eligible[row + x] = distance(pixels[x, y][:3]) <= KEY_DISTANCE

    # Flood-fill from the border.  Green/cyan subject pixels enclosed by the
    # aurora are not connected to this mask and remain opaque.
    background = bytearray(count)
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
        if x > 0:
            seed(index - 1)
        if x + 1 < width:
            seed(index + 1)
        if y > 0:
            seed(index - width)
        if y + 1 < height:
            seed(index + width)

    # A small dilation identifies antialiased pixels immediately around the
    # connected screen.  Only these pixels receive a soft alpha ramp.
    near_background = bytearray(background)
    for _ in range(EDGE_RADIUS):
        expanded = bytearray(near_background)
        for y in range(height):
            row = y * width
            for x in range(width):
                index = row + x
                if near_background[index]:
                    continue
                if (
                    (x > 0 and near_background[index - 1])
                    or (x + 1 < width and near_background[index + 1])
                    or (y > 0 and near_background[index - width])
                    or (y + 1 < height and near_background[index + width])
                ):
                    expanded[index] = 1
        near_background = expanded

    alpha = bytearray(count)
    transparent = 0
    partial = 0
    for y in range(height):
        row = y * width
        for x in range(width):
            index = row + x
            rgb = pixels[x, y][:3]
            if background[index]:
                output_alpha = 0
            elif near_background[index]:
                d = distance(rgb)
                if d <= KEY_DISTANCE:
                    output_alpha = 0
                elif d >= EDGE_DISTANCE:
                    output_alpha = 255
                else:
                    output_alpha = round(
                        255 * smoothstep(
                            (d - KEY_DISTANCE) / (EDGE_DISTANCE - KEY_DISTANCE)
                        )
                    )
            else:
                output_alpha = 255

            alpha[index] = output_alpha
            if output_alpha == 0:
                transparent += 1
            elif output_alpha < 255:
                partial += 1

    # Feather only the alpha silhouette.  The RGB colour is retained so the
    # light does not acquire a black/green outline when composited.
    alpha_image = Image.frombytes("L", (width, height), bytes(alpha))
    alpha_image = alpha_image.filter(ImageFilter.GaussianBlur(radius=0.8))
    image.putalpha(alpha_image)

    # Undo the green contribution in antialiased edge pixels.  This is a
    # restrained colour unmix: fully opaque aurora colours are untouched, and
    # only the pixels that still contain screen/background are corrected.
    output_pixels = image.load()
    alpha_pixels = alpha_image.load()
    for y in range(height):
        for x in range(width):
            red, green, blue, _ = output_pixels[x, y]
            output_alpha = alpha_pixels[x, y]
            if output_alpha == 0:
                output_pixels[x, y] = (0, 0, 0, 0)
                continue
            if output_alpha >= 250:
                # Opaque pixels can still contain a trace of the green screen
                # in the generated edge paint.  Only correct strongly green
                # pixels; blue/cyan light is left alone.
                if green <= blue + 25 or green <= red + 25:
                    continue
                green = round(green * 0.72 + max(red, blue) * 0.28)
                blue = max(blue, round(green * 0.56))
                output_pixels[x, y] = (red, green, blue, output_alpha)
                continue

            mix = min(0.75, (255 - output_alpha) / 160.0)
            denominator = max(32, output_alpha)
            source = (red, green, blue)
            unmixed = tuple(
                max(
                    0,
                    min(
                        255,
                        round(
                            (channel * 255 - (255 - output_alpha) * key_channel)
                            / denominator
                        ),
                    ),
                )
                for channel, key_channel in zip(source, KEY)
            )
            corrected = tuple(
                round(channel * (1.0 - mix) + clean * mix)
                for channel, clean in zip(source, unmixed)
            )
            red, green, blue = corrected
            if green > blue + 25 and green > red + 25:
                green = round(green * 0.72 + max(red, blue) * 0.28)
                blue = max(blue, round(green * 0.56))
            output_pixels[x, y] = (red, green, blue, output_alpha)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT, optimize=True)
    print(f"Wrote {OUTPUT}")
    print(f"Connected background pixels: {transparent}")
    print(f"Partial edge pixels before feather: {partial}")


if __name__ == "__main__":
    main()
