#!/usr/bin/env python3
"""빗줄기 후보의 «가림 정도»를 정량으로 재고 콘택트 시트를 뽑는다.

마인크래프트는 빗막 쿼드를 여러 겹(원경일수록 작게) 겹쳐 그린다. 그래서 텍스처 한
장만 보면 흐릿해 보여도 게임에서는 누적되어 화면을 덮는다. 여기서는 LAYERS 겹을
랜덤 오프셋으로 합성해 그 누적을 근사한다.

판정 지표는 «찌 대비 유지율» — 물결/찌 픽셀과 주변 물 픽셀의 밝기 차가 비를 씌운
뒤 몇 % 남는지. 눈으로 예쁜지와 별개로, 입질을 볼 수 있는지를 직접 재는 값이다.
"""
import random
import sys

from PIL import Image

LAYERS = 12
W = H = 220
BASE_W = 150  # 첫 빗막 겹이 화면에서 차지할 폭(px)
# ★텍스처를 원해상도로 타일링하면 안 된다 — 64px 텍스처는 128px 텍스처보다 화면에서
#   두 배 촘촘하게 반복되어 «해상도가 큰 팩이 성겨 보이는» 가짜 차이가 생긴다.
#   마인크래프트는 빗막 쿼드(월드 좌표 고정 크기)에 텍스처를 늘려 붙이므로, 비교는
#   반드시 같은 화면 폭으로 리샘플한 뒤에 해야 공정하다.


def scene():
    """바다 위 찌 장면 근사 — 하늘/수평선/물 + 찌 + 물결 링."""
    im = Image.new("RGB", (W, H))
    px = im.load()
    for y in range(H):
        if y < H * 0.42:                       # 흐린 하늘
            c = (118, 126, 138)
        else:                                  # 물 (아래로 갈수록 어두움)
            t = (y - H * 0.42) / (H * 0.58)
            c = (int(40 - 14 * t), int(72 - 24 * t), int(96 - 30 * t))
        for x in range(W):
            px[x, y] = c
    cx, cy = W // 2, int(H * 0.68)
    for r in (9, 15, 21):                      # 물결 링 (밝은 청록)
        for a in range(0, 360, 4):
            x = int(cx + r * 1.6 * __import__("math").cos(__import__("math").radians(a)))
            y = int(cy + r * 0.45 * __import__("math").sin(__import__("math").radians(a)))
            if 0 <= x < W and 0 <= y < H:
                px[x, y] = (96, 150, 168)
    for dy in range(-4, 3):                    # 찌 (빨강/흰)
        for dx in range(-1, 2):
            px[cx + dx, cy + dy] = (200, 40, 40) if dy < -1 else (232, 232, 232)
    return im, (cx, cy)


def overlay(base, tex, seed=7):
    rnd = random.Random(seed)
    out = base.copy()
    norm = tex.resize((BASE_W, max(1, round(BASE_W * tex.height / tex.width))), Image.LANCZOS)
    for i in range(LAYERS):
        s = 1.0 + i * 0.55                     # 원경 겹은 쿼드가 작게 보인다
        w = max(8, int(norm.width / s))
        h = max(8, int(norm.height / s))
        layer = norm.resize((w, h), Image.LANCZOS)
        tile = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ox, oy = rnd.randrange(w), rnd.randrange(h)
        for tx in range(-1, W // w + 2):
            for ty in range(-1, H // h + 2):
                tile.paste(layer, (tx * w - ox, ty * h - oy))
        out = Image.alpha_composite(out.convert("RGBA"), tile).convert("RGB")
    return out


def contrast(im, c):
    """찌·물결 픽셀 대비 배경 물의 밝기 차 평균."""
    cx, cy = c
    px = im.load()
    lum = lambda p: 0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2]
    marks = [(cx + dx, cy + dy) for dx in (-1, 0, 1) for dy in range(-4, 3)]
    marks += [(cx + dx, cy) for dx in (-34, -22, 22, 34)]
    bg = [(cx + dx, cy + dy) for dx in (-60, 60) for dy in (-12, 0, 12)]
    b = sum(lum(px[x, y]) for x, y in bg) / len(bg)
    return sum(abs(lum(px[x, y]) - b) for x, y in marks) / len(marks)


def main(cands):
    base, c = scene()
    ref = contrast(base, c)
    cells, labels = [base], [f"비 없음 (기준 {ref:.1f})"]
    for name, path in cands:
        tex = Image.open(path).convert("RGBA")
        d = sum(tex.load()[x, y][3] for x in range(tex.width) for y in range(tex.height)) / (tex.width * tex.height)
        img = overlay(base, tex)
        k = contrast(img, c)
        cells.append(img)
        labels.append(f"{name}  밀도{d:.2f}  대비유지 {k / ref * 100:.0f}%")
        print(f"{name:<22} 밀도 {d:5.2f}  찌 대비유지율 {k / ref * 100:5.1f}%")
    sheet = Image.new("RGB", (W * len(cells), H), (20, 20, 20))
    for i, im in enumerate(cells):
        sheet.paste(im, (i * W, 0))
    sheet = sheet.resize((sheet.width * 2, sheet.height * 2), Image.NEAREST)
    sheet.save("/tmp/rain_preview.png")
    print("시트:", "/tmp/rain_preview.png", "|", " / ".join(labels))


if __name__ == "__main__":
    main([tuple(a.split("=", 1)) for a in sys.argv[1:]])
