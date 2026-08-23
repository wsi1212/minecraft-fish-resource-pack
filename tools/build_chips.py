#!/usr/bin/env python3
"""카지노 칩 아이콘 생성기 (barkan:chip/*).

★손으로 PNG 를 고치지 말고 이 스크립트를 고쳐 다시 뽑을 것 — 액면이 늘 때마다
같은 손그림을 반복하면 6장이 조금씩 어긋난다(테두리 두께·글자 베이스라인).

디자인 규약
  · 64×64 item/generated 평면 스프라이트. 테이블 위에서는 눕혀서(rotX −90) 원반이 되고,
    GUI 에서는 그대로 아이콘이 된다.
  · 원·링·엣지 대시는 8× 슈퍼샘플링 후 축소(원이 계단지지 않게).
    ★글자는 축소 대상이 아니다 — 64px 격자에 하드 픽셀로 찍는다(뭉개지면 아무것도 못 읽는다).
  · 액면 글자는 한글이 아니라 1k/5k/10k/50k/100k/1M (2026-08-23 유저 요청).
  · 색은 기존 4종(1k 은색·10k 금색·100k 초록·1M 파랑)을 그대로 유지하고,
    신규 2종만 새 색을 받는다(5k 빨강·50k 보라) — 이미 익힌 액면 색을 흔들지 않는다.
"""
from __future__ import annotations

import json
import os
from PIL import Image, ImageDraw

SIZE = 64
SS = 8                      # 슈퍼샘플링 배율
R_OUTER = 31.0              # 칩 반지름
R_DASH_IN = 24.0            # 엣지 대시 안쪽
R_RING_OUT = 23.5           # 컬러 링 바깥
R_RING_IN = 21.5            # 컬러 링 안쪽 = 안쪽 면 반지름 (글자 «100k» 가 들어갈 만큼 넓게)
DASHES = 8                  # 엣지 대시 개수
DASH_DEG = 22.0             # 대시 하나가 차지하는 각도

BODY = (250, 250, 246, 255)         # 칩 몸통(아이보리)
BODY_EDGE = (214, 214, 209, 255)    # 바깥 1px 음영 — 밝은 배경에서도 실루엣이 살게
FACE_TINT = 0.13                    # 안쪽 면에 섞는 컬러 비율

# 액면 → (본색, 진한색). 진한색은 글자·링 안쪽 선에 쓴다.
CHIPS = {
    "chip_1k":   ("1k",   (184, 192, 206), (92, 100, 118)),     # 은색 (기존, 대비만 한 단 진하게)
    "chip_5k":   ("5k",   (214, 78, 74),   (132, 38, 36)),     # 빨강 (신규)
    "chip_10k":  ("10k",  (226, 172, 58),  (140, 100, 20)),    # 금색 (기존)
    "chip_50k":  ("50k",  (150, 104, 196), (86, 52, 124)),     # 보라 (신규)
    "chip_100k": ("100k", (63, 167, 94),   (26, 96, 50)),      # 초록 (기존)
    "chip_1m":   ("1M",   (79, 169, 216),  (30, 96, 138)),     # 파랑 (기존)
}

# 가변폭 4×6 비트맵 폰트(M 만 5폭) — 2배로 찍어 8×12, 획 2px.
# ★3×5 로 시작했다가 갈아엎었다: 그 폭에선 «5»가 S 로, «M»이 H 로 읽힌다(자기검수 1차).
#   5 는 윗변을 한 줄 꽉 채우고 왼쪽 세로를 각지게, M 은 5폭을 줘야 가운데 V 가 산다.
FONT = {
    "0": ("0110", "1001", "1001", "1001", "1001", "0110"),
    "1": ("0010", "0110", "0010", "0010", "0010", "0111"),
    "2": ("1110", "0001", "0010", "0100", "1000", "1111"),
    "3": ("1110", "0001", "0110", "0001", "0001", "1110"),
    "4": ("0010", "0110", "1010", "1111", "0010", "0010"),
    "5": ("1111", "1000", "1110", "0001", "1001", "0110"),
    "6": ("0110", "1000", "1110", "1001", "1001", "0110"),
    "7": ("1111", "0001", "0010", "0100", "0100", "0100"),
    "8": ("0110", "1001", "0110", "1001", "1001", "0110"),
    "9": ("0110", "1001", "1001", "0111", "0001", "0110"),
    "k": ("1000", "1001", "1010", "1100", "1010", "1001"),
    "M": ("10001", "11011", "10101", "10001", "10001", "10001"),
}
GLYPH_H, GAP, SCALE = 6, 1, 2


def mix(a, b, t):
    return tuple(round(x * (1 - t) + y * t) for x, y in zip(a, b))


def disc(colour, dark):
    """글자를 뺀 칩 원반 — 슈퍼샘플링으로 그린 뒤 64px 로 줄인다."""
    n = SIZE * SS
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = (SIZE / 2) * SS

    def circle(r, fill):
        d.ellipse([c - r * SS, c - r * SS, c + r * SS, c + r * SS], fill=fill)

    circle(R_OUTER, BODY_EDGE)
    circle(R_OUTER - 1.0, BODY)
    # 엣지 대시 — 링 바깥 테두리까지 파고들어 «끼워 넣은 색조각»처럼 보이게.
    for i in range(DASHES):
        mid = 360.0 * i / DASHES
        box = [c - R_OUTER * SS, c - R_OUTER * SS, c + R_OUTER * SS, c + R_OUTER * SS]
        d.pieslice(box, mid - DASH_DEG / 2, mid + DASH_DEG / 2, fill=colour + (255,))
    circle(R_DASH_IN, BODY)
    circle(R_RING_OUT, colour + (255,))
    circle(R_RING_IN + 0.9, dark + (255,))          # 링 안쪽 가는 선
    circle(R_RING_IN, mix(BODY[:3], colour, FACE_TINT) + (255,))
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def text_width(text):
    return sum(len(FONT[c][0]) for c in text) * SCALE + (len(text) - 1) * GAP * SCALE


def stamp(img, text, dark):
    """64px 격자에 하드 픽셀로 글자를 찍는다(안티에일리어싱 금지)."""
    w = text_width(text)
    h = GLYPH_H * SCALE
    # ★가장 긴 «100k» 가 안쪽 면의 현(chord) 안에 들어가는지 여기서 깨뜨린다 — 링을 조이다
    #   글자가 링 위로 올라타는 사고를 조용히 넘기지 않으려고.
    chord = 2 * (R_RING_IN ** 2 - (h / 2) ** 2) ** 0.5
    if w > chord - 2:
        raise SystemExit("글자 «" + text + "» 폭 " + str(w) + "px 가 안쪽 면 현 "
                         + str(round(chord, 1)) + "px 를 넘는다 — 폰트나 링 반지름을 고칠 것")
    x0 = (SIZE - w) // 2
    y0 = (SIZE - h) // 2
    px = img.load()
    gx = x0
    for ch in text:
        rows = FONT[ch]
        for ry, row in enumerate(rows):
            for rx, bit in enumerate(row):
                if bit != "1":
                    continue
                for dy in range(SCALE):
                    for dx in range(SCALE):
                        px[gx + rx * SCALE + dx, y0 + ry * SCALE + dy] = dark + (255,)
        gx += (len(rows[0]) + GAP) * SCALE
    return img


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tex = os.path.join(root, "assets/minecraft/textures/item/chip")
    mdl = os.path.join(root, "assets/barkan/models/chip")
    itm = os.path.join(root, "assets/barkan/items/chip")
    for p in (tex, mdl, itm):
        os.makedirs(p, exist_ok=True)

    for name, (text, colour, dark) in CHIPS.items():
        img = stamp(disc(colour, dark), text, dark)
        img.save(os.path.join(tex, name + ".png"))
        with open(os.path.join(mdl, name + ".json"), "w") as f:
            json.dump({"parent": "minecraft:item/generated",
                       "textures": {"layer0": "minecraft:item/chip/" + name}}, f,
                      separators=(",", ":"))
        with open(os.path.join(itm, name + ".json"), "w") as f:
            json.dump({"model": {"type": "minecraft:model", "model": "barkan:chip/" + name}}, f,
                      separators=(",", ":"))
        print("  " + name.ljust(11) + text)
    print(str(len(CHIPS)) + " chips")


if __name__ == "__main__":
    main()
