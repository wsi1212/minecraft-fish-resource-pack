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
# 실제로 «굽는» 프레임 수. FRAMES 와 다르면 나머지 프레임의 글리프는 구운 프레임을
# 돌려 쓴다(파일을 공유). 1 이면 정지 오로라다.
#
# 왜 1 인가 (2026-09-03):
#   12프레임의 차이는 ±4px 이동 + 밝기 3.5% 가 전부인데(인접 프레임 픽셀차 평균 1.4~3.1/255)
#   그 흔들림에 18.9MB 를 쓰고 있었다. 팩이 112MB 까지 커져 느린 회선 유저가 다 받지 못하고
#   접속에 실패했기에 애니메이션을 뺐다. 정지 1프레임 = 1.6MB (-17.3MB), 해상도는 그대로다.
#
# ★FRAMES 는 그대로 12 로 둔다. 자바(AuroraDisplayManager)가 E010 + frame*64 + tile 로
#   12프레임 분량 글리프를 계속 찍기 때문에, 글리프 정의가 사라지면 14.4초 중 13.2초 동안
#   오로라가 빈 화면이 된다. 여기서는 «파일만» 공유시켜 jar 을 건드리지 않고도 안전하게 만든다.
#   (나중에 자바 FRAMES 를 1 로 내리면 1.2초마다 나가는 TextDisplay 갱신도 없앨 수 있다.)
BAKE_FRAMES = 1
COLS = 8
ROWS = 8
FULL_SIZE = (1480, 1568)
TILE_SIZE = (FULL_SIZE[0] // COLS, FULL_SIZE[1] // ROWS)
SPACER_BASE = 0xE400
GLYPH_BASE = 0xE010                 # 타일 글리프 시작점 — 자바와 같은 값이어야 한다


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

    baked_advances: list[list[int]] = []
    for frame in range(BAKE_FRAMES):
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

        advances: list[int] = []
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
            advances.append(TILE_SIZE[0] - bitmap_provider_advance(crop))
        baked_advances.append(advances)

    # \uad7d\uc9c0 \uc54a\uc740 \ud504\ub808\uc784\uc758 \ub0a1\uc740 \ud0c0\uc77c\uc740 \uc9c0\uc6b4\ub2e4 (\ud329\uc5d0 \uc2e4\ub824 \uc6a9\ub7c9\ub9cc \uba39\ub294\ub2e4).
    removed = 0
    for frame in range(BAKE_FRAMES, FRAMES):
        for tile in range(COLS * ROWS):
            stale = OUT_DIR / f"aurora_f{frame}_t{tile}.png"
            if stale.exists():
                stale.unlink()
                removed += 1

    # \ud504\ub808\uc784 f \ub294 \uad6c\uc6b4 \ud504\ub808\uc784 (f % BAKE_FRAMES) \uc758 \ud0c0\uc77c\uc744 \uadf8\ub300\ub85c \uc4f4\ub2e4.
    def source_frame(frame: int) -> int:
        return frame % BAKE_FRAMES

    spacer_advances: list[int] = []
    for frame in range(FRAMES):
        spacer_advances.extend(baked_advances[source_frame(frame)])
    if len(spacer_advances) != FRAMES * COLS * ROWS:
        raise RuntimeError(f"Expected {FRAMES * COLS * ROWS} spacer advances, got {len(spacer_advances)}")

    font = json.loads(FONT_JSON.read_text())
    space_provider = next(provider for provider in font["providers"] if provider["type"] == "space")
    advances_map = {"\ue00e": -1}
    for tile, advance in enumerate(spacer_advances):
        advances_map[chr(SPACER_BASE + tile)] = advance
    space_provider["advances"] = advances_map

    # \ud0c0\uc77c \uae00\ub9ac\ud504 provider \uc758 file \uc744 \u00ab\uad6c\uc6b4\u00bb \ud504\ub808\uc784\uc73c\ub85c \ub3cc\ub9b0\ub2e4.
    # \ubb38\uc790 \ubc30\uc815(E010 + frame*64 + tile)\u00b7ascent\u00b7height \ub294 \uac74\ub4dc\ub9ac\uc9c0 \uc54a\ub294\ub2e4 \u2014 \uc790\ubc14\uc640 \ud654\uba74 \ud06c\uae30\uc758 \uacc4\uc57d\uc774\ub2e4.
    wanted = {
        chr(GLYPH_BASE + frame * COLS * ROWS + tile):
            f"barkan:font/aurora_f{source_frame(frame)}_t{tile}.png"
        for frame in range(FRAMES)
        for tile in range(COLS * ROWS)
    }
    repointed = 0
    for provider in font["providers"]:
        if provider.get("type") != "bitmap":
            continue
        chars = "".join(provider.get("chars") or [])
        if len(chars) != 1 or chars not in wanted:
            continue                      # aurora_256 \ud3f4\ubc31 \ub4f1\uc740 \uadf8\ub300\ub85c \ub454\ub2e4
        if provider["file"] != wanted[chars]:
            provider["file"] = wanted[chars]
            repointed += 1

    FONT_JSON.write_text(json.dumps(font, ensure_ascii=True, indent=2) + "\n")

    print(
        f"Built {BAKE_FRAMES * COLS * ROWS} tiles at "
        f"{TILE_SIZE[0]}x{TILE_SIZE[1]} from {SOURCE.name} "
        f"(frames baked={BAKE_FRAMES}/{FRAMES}, stale removed={removed}, providers repointed={repointed})"
    )


if __name__ == "__main__":
    main()
