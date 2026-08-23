#!/usr/bin/env python3
"""카지노 칩 아이콘 생성기 (barkan:chip/*).

★손으로 PNG 를 고치지 말고 이 스크립트를 고쳐 다시 뽑을 것 — 액면이 늘 때마다
같은 손그림을 반복하면 6장이 조금씩 어긋난다(테두리 두께·글자 베이스라인).

디자인 규약
  · 128×128 item/generated 평면 스프라이트(리소스팩 빌더의 아이템 상한이 128px).
    테이블 위에서는 눕혀서(rotX −90) 원반이 되고, GUI 에서는 그대로 아이콘이 된다.
  · 원·링·엣지 대시·글자를 전부 8× 슈퍼샘플(1024px)로 그린 뒤 한 번에 축소한다.
  · 액면 글자는 한글이 아니라 1k/5k/10k/50k/100k/1M (2026-08-23 유저 요청).
  · 글꼴은 **리소스팩에 이미 들어 있는 어그로체 Bold** — 서버 전역 폰트와 같은 얼굴이고,
    같은 저장소에 있어서 다른 기계에서도 같은 그림이 나온다(시스템 폰트에 기대지 않는다).
    후보 중 가장 획이 굵어 축소에서 제일 늦게 무너진다(Arial Black·Rounded·Helvetica 비교).

해상도 이력
  · 64px + 손으로 찍은 4×6 비트맵 폰트 → 글자가 8×12px 라 계단이 보였다.
  · 2026-08-23 유저 요청("글씨 해상도 좀 더 키워줘")으로 128px + 실제 글꼴 렌더로 교체.
    글자 높이가 12px → 34px 로 약 3배.
"""
from __future__ import annotations

import json
import os
from PIL import Image, ImageDraw, ImageFont

SIZE = 128                  # 최종 텍스처 한 변 (리소스팩 아이템 상한)
SS = 8                      # 슈퍼샘플링 배율
R_OUTER = 62.0              # 칩 반지름
R_DASH_IN = 48.0            # 엣지 대시 안쪽
R_RING_OUT = 47.0           # 컬러 링 바깥
R_RING_IN = 43.0            # 컬러 링 안쪽 = 안쪽 면 반지름
DASHES = 8                  # 엣지 대시 개수
DASH_DEG = 22.0             # 대시 하나가 차지하는 각도

BODY = (250, 250, 246, 255)         # 칩 몸통(아이보리)
BODY_EDGE = (214, 214, 209, 255)    # 바깥 1px 음영 — 밝은 배경에서도 실루엣이 살게
FACE_TINT = 0.13                    # 안쪽 면에 섞는 컬러 비율

TEXT_W_RATIO = 0.82         # 글자 폭 ÷ 안쪽 면 지름 (링에 안 닿게 숨통을 남긴다)
TEXT_H_RATIO = 0.42         # 글자 높이 ÷ 안쪽 면 지름
# ★짧은 액면(«1k»)은 폭이 남아 혼자 커진다 — 제일 긴 «100k» 높이의 이 배수까지만 허용해
#   6장이 한 세트로 보이게 한다(안 묶으면 36px 대 21px 로 따로 논다).
TEXT_H_SPREAD = 1.35

FONT_PATH = "assets/barkan/font/aggro_bold.ttf"

# 액면 → (표기, 본색, 진한색). 진한색은 글자·링 안쪽 선에 쓴다.
CHIPS = {
    "chip_1k":   ("1k",   (184, 192, 206), (92, 100, 118)),    # 은색 (기존)
    "chip_5k":   ("5k",   (214, 78, 74),   (132, 38, 36)),     # 빨강 (신규)
    "chip_10k":  ("10k",  (226, 172, 58),  (140, 100, 20)),    # 금색 (기존)
    "chip_50k":  ("50k",  (150, 104, 196), (86, 52, 124)),     # 보라 (신규)
    "chip_100k": ("100k", (63, 167, 94),   (26, 96, 50)),      # 초록 (기존)
    "chip_1m":   ("1M",   (79, 169, 216),  (30, 96, 138)),     # 파랑 (기존)
}


def mix(a, b, t):
    return tuple(round(x * (1 - t) + y * t) for x, y in zip(a, b))


def disc(colour, dark):
    """칩 원반 — 슈퍼샘플 캔버스에 그린다(축소는 호출부에서 글자까지 얹은 뒤 한 번에)."""
    n = SIZE * SS
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = (SIZE / 2) * SS

    def circle(r, fill):
        d.ellipse([c - r * SS, c - r * SS, c + r * SS, c + r * SS], fill=fill)

    circle(R_OUTER, BODY_EDGE)
    circle(R_OUTER - 2.0, BODY)
    # 엣지 대시 — 링 바깥 테두리까지 파고들어 «끼워 넣은 색조각»처럼 보이게.
    for i in range(DASHES):
        mid = 360.0 * i / DASHES
        box = [c - R_OUTER * SS, c - R_OUTER * SS, c + R_OUTER * SS, c + R_OUTER * SS]
        d.pieslice(box, mid - DASH_DEG / 2, mid + DASH_DEG / 2, fill=colour + (255,))
    circle(R_DASH_IN, BODY)
    circle(R_RING_OUT, colour + (255,))
    circle(R_RING_IN + 1.8, dark + (255,))          # 링 안쪽 가는 선
    circle(R_RING_IN, mix(BODY[:3], colour, FACE_TINT) + (255,))
    return img


def ink(text, font):
    """글자만 담긴 레이어를 <b>실제 잉크 경계</b>로 잘라 돌려준다.

    ★TTF 의 'mm' 앵커는 어센더/디센더 기준이라 «1k» 처럼 위아래가 비는 문자열이
    광학적으로 위로 뜬다. 잉크 bbox 로 잘라서 붙여야 칩 한가운데에 온다.
    """
    probe = Image.new("L", (font.size * len(text) * 2 + 40, font.size * 3), 0)
    ImageDraw.Draw(probe).text((20, font.size), text, font=font, fill=255)
    box = probe.getbbox()
    if box is None:
        raise SystemExit("글자 «" + text + "» 가 비어 있다 — 글꼴에 없는 문자인지 확인")
    return probe.crop(box)


def fit_font(text, path, max_h=None):
    """안쪽 면에 들어가는 최대 글꼴 크기를 잉크 크기 기준으로 찾는다."""
    face = 2 * R_RING_IN * SS
    max_w = face * TEXT_W_RATIO
    max_h = face * TEXT_H_RATIO if max_h is None else max_h
    best = None
    for size in range(20, int(face)):
        layer = ink(text, ImageFont.truetype(path, size))
        if layer.width > max_w or layer.height > max_h:
            break
        best = layer
    if best is None:
        raise SystemExit("글자 «" + text + "» 가 최소 크기에도 안 들어간다 — 링 반지름을 늘릴 것")
    return best


def downsample(img):
    """SS 캔버스를 최종 크기로 줄인다.

    ★RGB 와 알파를 따로 줄인다 — RGBA 를 통째로 줄이면 투명 픽셀의 RGB(=검정)가
    가장자리에 섞여 칩 테두리에 어두운 띠가 생긴다(프리멀티플라이 안 하는 PIL 의 함정).
    투명부를 몸통색으로 먼저 메운 뒤 줄이면 테두리가 아이보리로 곱게 빠진다.
    """
    alpha = img.getchannel("A").resize((SIZE, SIZE), Image.LANCZOS)
    filled = Image.new("RGBA", img.size, BODY)
    filled.alpha_composite(img)
    rgb = filled.convert("RGB").resize((SIZE, SIZE), Image.LANCZOS)
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    return out


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    font_path = os.path.join(root, FONT_PATH)
    if not os.path.exists(font_path):
        raise SystemExit("글꼴이 없다: " + font_path)
    tex = os.path.join(root, "assets/minecraft/textures/item/chip")
    mdl = os.path.join(root, "assets/barkan/models/chip")
    itm = os.path.join(root, "assets/barkan/items/chip")
    for p in (tex, mdl, itm):
        os.makedirs(p, exist_ok=True)

    # 1차: 각자 최대로 키워 보고 → 제일 작은 글자(=제일 긴 액면) 기준으로 높이 상한을 잡는다.
    shortest = min(fit_font(text, font_path).height for text, _, _ in CHIPS.values())
    cap_h = shortest * TEXT_H_SPREAD

    for name, (text, colour, dark) in CHIPS.items():
        img = disc(colour, dark)
        layer = fit_font(text, font_path, max_h=cap_h)
        c = (SIZE // 2) * SS
        img.paste(dark + (255,), (c - layer.width // 2, c - layer.height // 2), layer)
        img = downsample(img)
        img.save(os.path.join(tex, name + ".png"))
        with open(os.path.join(mdl, name + ".json"), "w") as f:
            json.dump({"parent": "minecraft:item/generated",
                       "textures": {"layer0": "minecraft:item/chip/" + name}}, f,
                      separators=(",", ":"))
        with open(os.path.join(itm, name + ".json"), "w") as f:
            json.dump({"model": {"type": "minecraft:model", "model": "barkan:chip/" + name}}, f,
                      separators=(",", ":"))
        print("  " + name.ljust(11) + text.ljust(6)
              + "글자 " + str(round(layer.width / SS)) + "×" + str(round(layer.height / SS)) + "px")
    print(str(len(CHIPS)) + " chips @ " + str(SIZE) + "px")


if __name__ == "__main__":
    main()
