#!/usr/bin/env python3
"""빗줄기 텍스처 생성 — assets/minecraft/textures/environment/rain.png

## 왜 생성기인가
우리 팩이 2023년에 넣은 커스텀 빗줄기(`tools/rain_src.png`)는 바닐라보다 단위
면적당 알파가 3.2배였다(커버리지 60.5% vs 2.5%). 낱개 픽셀은 흐리지만 마인크래프트가
빗막 쿼드를 여러 겹 겹쳐 그리기 때문에 누적되어 화면이 뿌옇게 되고, **낚시 찌가
잠기는 물결이 그 뒤로 묻혀 입질을 눈으로 못 잡는다.** 그래서 밀도를 깎는다.

알파를 일괄로 낮추면 빗줄기가 사라지는 대신 화면 전체가 균일하게 흐려져 안개처럼
보인다(가림은 그대로다). 진짜 원인은 **텍스처 높이의 절반(257px)에 달하는 긴 줄이
128열 전부에 깔린** 구조라서, 줄 자체를 솎아내야 사이로 물이 보인다.

## 처리 5단
1. **열 솎기** — 세로줄을 열 단위로 KEEP 비율만 남긴다. 결정적 시드라 매번 같은
   결과가 나온다. 인접 3열 연속 유지(뭉쳐서 벽이 됨)와 MAX_GAP열 연속 삭제(비가
   끊긴 띠로 보임)를 둘 다 막아 blue-noise 처럼 흩는다.
2. **길이 자르기** — 남은 줄을 MAX_RUN 픽셀에서 끊는다. 위아래를 관통하는 줄이
   시야를 가장 많이 막는다. 끊은 끝은 페이드해 잘린 티가 안 나게 한다.
3. **알파 게인** — 살아남은 줄만 조금 진하게(cap ALPHA_CAP). 총량은 줄지만 남은
   줄은 또렷해서 «비가 약해진 것»이 아니라 «빗발이 성긴 것»으로 보인다.
4. **굵기 번짐** — 남은 줄을 옆 열로 THICKEN 만큼 번지게 한다. 1px 줄만 성기게
   남기면 비가 아니라 «필름 긁힘»처럼 보인다. 줄 사이는 그대로 뚫려 있으니 굵어져도
   물속 가시성은 거의 안 깎인다.
5. **청색 틴트** — 원본은 무채색 회색(127,127,127)이라 성기게 만들면 먼지처럼 읽힌다.
   바닐라 빗줄기가 «비»로 보이는 이유의 절반은 파란 색조다.

★생성물(rain.png)을 손으로 고치지 말고 이 스크립트의 파라미터를 고칠 것.
사용: python3 tools/gen_rain.py [--preview]
"""
import os
import random
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(HERE, "rain_src.png")
OUT = os.path.join(ROOT, "assets/minecraft/textures/environment/rain.png")

# ── 파라미터 (여기만 만지면 된다) ───────────────────────────────────────────
# 확정값 근거 (tools/preview_rain.py, 시드 8회 평균 «찌 대비유지율»)
#   기존 커스텀 밀도 9.33 → 64.4%   (찌 대비의 1/3을 비가 잡아먹었다 = 입질이 안 보인다)
#   바닐라        밀도 2.91 → 82.5%
#   ★확정        밀도 2.80 → 86.9%  (바닐라와 같은 밀도인데 가시성은 더 좋다)
SEED = 20260821
KEEP = 0.46        # 남길 세로줄 비율
MAX_RUN = 140      # 한 줄의 최대 길이(px). 원본은 최대 260 = 텍스처 절반
ALPHA_GAIN = 1.55  # 살아남은 줄의 알파 배율
ALPHA_CAP = 190    # 알파 상한 (바닐라 최대 255보다 낮게 — 우리 비는 부드러운 톤)
MAX_GAP = 6        # 이 이상 연속으로 열을 비우지 않는다
FADE = 6           # 잘린 줄 끝 페이드 길이(px)
THICKEN = 0.55     # 옆 열에 이 비율로 줄을 번지게 (0이면 1px 줄)
TINT = (118, 142, 178)  # 빗줄기 색 (원본은 무채색 회색이었다)


def pick_columns(width, rnd):
    """열 유지 마스크. 뭉침(3연속)과 빈 띠(MAX_GAP 연속)를 동시에 막는다."""
    keep = []
    run_keep = run_drop = 0
    for _ in range(width):
        if run_drop >= MAX_GAP:
            take = True
        elif run_keep >= 2:
            take = False
        else:
            take = rnd.random() < KEEP
        keep.append(take)
        run_keep = run_keep + 1 if take else 0
        run_drop = 0 if take else run_drop + 1
    return keep


def thin_column(alphas, rnd):
    """한 열의 알파 배열을 받아 긴 줄을 MAX_RUN 에서 끊고 끝을 페이드한다."""
    h = len(alphas)
    out = [0] * h
    y = 0
    while y < h:
        if alphas[y] < 8:
            y += 1
            continue
        end = y
        while end < h and alphas[end] >= 8:
            end += 1
        run = end - y
        if run <= MAX_RUN:
            segs = [(y, end)]
        else:
            # 긴 줄은 한 토막만 남긴다 (자르고 나머지를 버리는 게 곧 밀도 감소)
            length = rnd.randint(MAX_RUN // 2, MAX_RUN)
            start = rnd.randint(y, max(y, end - length))
            segs = [(start, min(end, start + length))]
        for s, t in segs:
            for i in range(s, t):
                a = min(ALPHA_CAP, int(alphas[i] * ALPHA_GAIN))
                # 양끝 페이드 — 잘린 단면이 눈에 안 띄게
                edge = min(i - s, t - 1 - i)
                if edge < FADE:
                    a = int(a * (edge + 1) / (FADE + 1))
                out[i] = a
        y = end
    return out


def build():
    rnd = random.Random(SEED)
    im = Image.open(SRC).convert("RGBA")
    w, h = im.size
    src = im.load()
    dst = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    put = dst.load()
    keep = pick_columns(w, rnd)
    # 열별 알파를 먼저 계산해 두고, 굵기 번짐은 그 위에 합성한다
    #   (마스크를 직접 넓히면 pick_columns 의 «뭉침 방지»가 무의미해진다)
    cols = {}
    for x in range(w):
        if keep[x]:
            cols[x] = thin_column([src[x, y][3] for y in range(h)], rnd)
    final = [[0] * h for _ in range(w)]
    for x, alphas in cols.items():
        for y in range(h):
            a = alphas[y]
            if a <= 0:
                continue
            final[x][y] = max(final[x][y], a)
            if THICKEN > 0:
                nx = x + 1
                if nx < w and nx not in cols:
                    final[nx][y] = max(final[nx][y], int(a * THICKEN))
    for x in range(w):
        for y in range(h):
            if final[x][y] > 0:
                put[x, y] = (TINT[0], TINT[1], TINT[2], min(ALPHA_CAP, final[x][y]))
    return im, dst


def load_density(img):
    """정규화 알파량 = 픽셀당 평균 알파. 화면을 얼마나 덮는지의 대리지표."""
    w, h = img.size
    px = img.load()
    return sum(px[x, y][3] for x in range(w) for y in range(h)) / (w * h)


def main():
    before, after = build()
    after.save(OUT)
    d0, d1 = load_density(before), load_density(after)
    print(f"rain.png 갱신 — 정규화 알파량 {d0:.2f} → {d1:.2f}  ({d1 / d0 * 100:.0f}%)")
    print(f"  바닐라(64x256) 기준값 2.91 대비 {d1 / 2.91:.2f}배")


if __name__ == "__main__":
    main()
