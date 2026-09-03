"""Build smooth aurora tiles and a night-background GIF preview.

★2026-09-03: 이 스크립트는 «폐기된 실험»이다. 그대로 돌리면 라이브 팩이 깨진다.
  · 소스가 다르고(aurora-smooth-transparent) 타일 크기도 다르다(370x252 vs 라이브 185x196)
    → aurora.json 의 ascent/height(98/196) 계약과 어긋나 오로라가 찌그러진다.
  · 12프레임 768장을 assets/barkan/textures/font 에 직접 써서, 애니메이션 제거로
    64장까지 줄여 둔 것(18.9MB → 1.6MB)을 되돌린다.
  라이브 타일의 권위는 build_aurora_assets.py 하나다. 미리보기만 필요하면
  make_final_aurora_gif.py 를 쓸 것(그건 팩에 쓰지 않는다).
  그래도 돌려야 한다면 AURORA_SMOOTH_OVERWRITE=1 을 붙여 «의도»를 남길 것.
"""

import os
import sys
from math import cos, pi, sin
from pathlib import Path

from PIL import Image, ImageEnhance

if os.environ.get("AURORA_SMOOTH_OVERWRITE") != "1":
    sys.exit(
        "거부: 이 스크립트는 라이브 오로라 타일을 다른 크기(370x252)로 768장 덮어쓴다.\n"
        "     권위는 build_aurora_assets.py 다. 정말 덮어쓰려면 AURORA_SMOOTH_OVERWRITE=1"
    )


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools/imagegen-source/aurora-smooth-transparent.png"
TILE_DIR = ROOT / "assets/barkan/textures/font"
GIF = ROOT / "tools/imagegen-source/aurora-smooth-animation-preview.gif"

FRAMES = 12
COLS = ROWS = 8
MASTER_SIZE = (2960, 2016)
TILE_SIZE = (370, 252)
PREVIEW_SIZE = (768, 523)
NIGHT = (5, 10, 28, 255)


def translate(image: Image.Image, dx: int, dy: int) -> Image.Image:
    out = Image.new("RGBA", image.size, (0, 0, 0, 0))
    w, h = image.size
    left = max(0, -dx)
    top = max(0, -dy)
    right = min(w, w - dx)
    bottom = min(h, h - dy)
    if right > left and bottom > top:
        crop = image.crop((left, top, right, bottom))
        out.paste(crop, (left + dx, top + dy), crop)
    return out


def frame_image(master: Image.Image, frame: int) -> Image.Image:
    phase = 2.0 * pi * frame / FRAMES
    shifted = translate(master, round(3.0 * sin(phase)), round(1.5 * cos(phase)))
    rgb = ImageEnhance.Brightness(shifted.convert("RGB")).enhance(
        1.0 + 0.025 * sin(phase)
    )
    alpha = shifted.getchannel("A").point(
        lambda value: max(0, min(255, round(value * (1.0 + 0.015 * cos(phase)))))
    )
    rgb.putalpha(alpha)
    return rgb


def main() -> None:
    with Image.open(SOURCE) as loaded:
        master = loaded.convert("RGBA").resize(MASTER_SIZE, Image.Resampling.LANCZOS)

    previews: list[Image.Image] = []
    for frame in range(FRAMES):
        animated = frame_image(master, frame)
        for tile in range(COLS * ROWS):
            row, col = divmod(tile, COLS)
            crop = animated.crop(
                (col * TILE_SIZE[0], row * TILE_SIZE[1],
                 (col + 1) * TILE_SIZE[0], (row + 1) * TILE_SIZE[1])
            )
            crop.save(TILE_DIR / f"aurora_f{frame}_t{tile}.png", optimize=True)

        small = animated.resize(PREVIEW_SIZE, Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", PREVIEW_SIZE, NIGHT)
        canvas.alpha_composite(small)
        previews.append(canvas.convert("RGB").quantize(colors=256, method=Image.Quantize.MEDIANCUT))

    previews[0].save(
        GIF,
        save_all=True,
        append_images=previews[1:],
        duration=1200,
        loop=0,
        disposal=2,
        optimize=False,
    )
    print(f"Wrote {FRAMES * COLS * ROWS} tiles and {GIF}")


if __name__ == "__main__":
    main()
