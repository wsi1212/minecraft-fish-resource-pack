"""Extract a soft alpha matte from the final night-sky aurora master.

The source is already composited over a nearly uniform navy sky.  Instead of
keying on a hue (which damaged the earlier green/cyan aurora), estimate the
sky colour from the border and turn luminance/colour departure from that sky
into a broad, antialiased alpha ramp.
"""

from pathlib import Path
from statistics import median

from PIL import Image, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools/imagegen-source/aurora-final-night-master.png"
OUTPUT = ROOT / "tools/imagegen-source/aurora-final-night-transparent.png"
ALPHA_START = 8.0
ALPHA_FULL = 64.0
DISTANCE_BLUR_RADIUS = 7.0
BLUR_RADIUS = 1.5


def smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def main() -> None:
    with Image.open(SOURCE) as loaded:
        source = loaded.convert("RGB")

    width, height = source.size
    pixels = source.load()
    border: list[tuple[int, int, int]] = []
    step = max(1, min(width, height) // 256)
    for x in range(0, width, step):
        border.append(pixels[x, 0])
        border.append(pixels[x, height - 1])
    for y in range(0, height, step):
        border.append(pixels[0, y])
        border.append(pixels[width - 1, y])

    background = tuple(
        int(round(median(sample[channel] for sample in border)))
        for channel in range(3)
    )
    # Blur the *signal* before thresholding.  Thresholding raw generated
    # pixels was the source of the toothy contour in the previous preview:
    # tiny background texture became a row of visible alpha spikes.
    distance_map = bytearray(width * height)
    for y in range(height):
        for x in range(width):
            rgb = pixels[x, y]
            distance_map[y * width + x] = max(
                abs(rgb[channel] - background[channel]) for channel in range(3)
            )
    distance_image = Image.frombytes("L", (width, height), bytes(distance_map))
    distance_image = distance_image.filter(
        ImageFilter.GaussianBlur(radius=DISTANCE_BLUR_RADIUS)
    )

    alpha = Image.new("L", (width, height), 0)
    alpha_pixels = alpha.load()
    distance_pixels = distance_image.load()

    for y in range(height):
        for x in range(width):
            # Max-channel distance is stable for blue/cyan light and the
            # blurred signal keeps the alpha contour continuous.
            distance = distance_pixels[x, y]
            alpha_pixels[x, y] = round(
                255 * smoothstep((distance - ALPHA_START) / (ALPHA_FULL - ALPHA_START))
            )

    alpha = alpha.filter(ImageFilter.GaussianBlur(radius=BLUR_RADIUS))
    output = source.convert("RGBA")
    output.putalpha(alpha)

    # Unmix the navy background only where the matte is established enough to
    # be numerically stable. This removes a dark halo when the tile is placed
    # over a slightly different night sky.
    output_pixels = output.load()
    alpha_pixels = alpha.load()
    for y in range(height):
        for x in range(width):
            a = alpha_pixels[x, y]
            if a == 0:
                output_pixels[x, y] = (0, 0, 0, 0)
                continue
            if a < 80:
                continue
            fraction = a / 255.0
            values = []
            for channel in range(3):
                recovered = (pixels[x, y][channel] - (1.0 - fraction) * background[channel]) / fraction
                values.append(max(0, min(255, round(recovered))))
            output_pixels[x, y] = (*values, a)

    output.save(OUTPUT, optimize=True)
    print(f"Wrote {OUTPUT}")
    print(f"Estimated background: #{background[0]:02x}{background[1]:02x}{background[2]:02x}")
    print(f"Alpha ramp: {ALPHA_START:g}..{ALPHA_FULL:g}, blur={BLUR_RADIUS:g}px")


if __name__ == "__main__":
    main()
