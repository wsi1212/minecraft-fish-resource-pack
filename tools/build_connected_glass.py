#!/usr/bin/env python3
"""연결 유리(Connected Glass) 생성기 — Vanilla Tweaks 와 같은 결과를 직접 구현한 것.

원리는 세 줄이다.

1. **바닐라 클라는 이웃을 못 본다.** 블록 텍스처는 이웃 블록을 모르는 채로 그려지므로,
   "옆이 유리면 테두리를 지운다" 는 판정 자체가 리소스팩 문법에 없다. 이걸 가능하게 하는
   유일한 규약이 **CTM**(Connected Textures Method) — 옵티파인이 정하고 Continuity·Athena 가
   그대로 읽는 포맷이다. 그래서 산출물은 `optifine/ctm/**` 에 들어간다.
2. **CTM 은 이웃 8칸 조합을 47장의 타일로 압축한다.** 8칸이면 256가지지만, 그림이 실제로
   달라지는 경우는 47가지뿐이라(대각선은 양 변이 붙어 있을 때만 보인다) 256→47 매핑표를 쓴다.
3. **타일 한 장을 그리는 규칙**은 결국 "윤곽선만 남긴다" 다.
     · 이웃이 유리가 **아닌** 변 → 바닐라 테두리 픽셀 그대로 (윤곽선)
     · 이웃이 유리인 변       → 유리 속살로 밀어 지운다 (이음선 소멸)
     · 양 변은 붙었는데 대각이 빈 모서리 → **1px 만 찍어 윤곽선을 이어 준다**
       (안 찍으면 ㄱ자 안쪽에서 선이 대각으로 1px 끊겨 보인다)

★ 바닐라 텍스처(`textures/block/*.png`)는 **건드리지 않는다.** CTM 을 못 읽는 클라(순수 바닐라)는
   지금까지처럼 바닐라 유리를 그대로 본다 — 아무것도 망가지지 않는다. 예전 '클리어 글라스'는
   이걸 덮어써서 전원의 유리 테두리를 지워 버렸고(유리가 거의 안 보임), 그게 2026-08-20 에 걷혔다.

사용:
    python3 tools/build_connected_glass.py                    # 생성
    python3 tools/build_connected_glass.py --check            # 규칙 자동 검산 (배포 전 필수)
    python3 tools/build_connected_glass.py --preview out.png  # 오프라인 육안 대조 렌더

★ 생성물을 손으로 고치지 말 것. 바닐라가 바뀌면 --jar 만 바꿔 다시 돌린다.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from collections import Counter
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parent.parent
CTM_DIR = REPO / "assets" / "minecraft" / "optifine" / "ctm" / "glass"

DEFAULT_JAR = Path.home() / "Library/Application Support/minecraft/versions/1.21.11/1.21.11.jar"

COLORS = [
    "white", "orange", "magenta", "light_blue", "yellow", "lime", "pink", "gray",
    "light_gray", "cyan", "purple", "blue", "brown", "green", "red", "black",
]

# (ctm 폴더 = 텍스처 이름, matchBlocks 대상)
BLOCKS = (
    [("glass", "minecraft:glass")]
    + [(f"{c}_stained_glass", f"minecraft:{c}_stained_glass") for c in COLORS]
    + [("tinted_glass", "minecraft:tinted_glass")]
)
# 유리판의 넓은 면은 블록 유리와 **같은 텍스처**를 쓴다 → 같은 타일 세트를 이름만 달리 얹는다.
# 판의 얇은 띠(`*_pane_top`)는 바닐라 그대로 둔다 (아래 「알려진 한계」 참조).
PANES = [("glass_pane", "minecraft:glass_pane", "glass")] + [
    (f"{c}_stained_glass_pane", f"minecraft:{c}_stained_glass_pane", f"{c}_stained_glass")
    for c in COLORS
]

# ── CTM 47타일 이웃 표 ─────────────────────────────────────────────────────
# ★이 표는 추측하면 타일이 어긋난다. MCPatcher 원본(pclewis/mcpatcher,
#   newcode/src/com/pclewis/mcpatcher/mod/TileOverride.java 의 class CTM)에 있는
#   256엔트리 neighborMap 을 그대로 옮긴 것 — 옵티파인이 이 규약을 물려받았고
#   Continuity·Athena 도 같은 표를 쓴다.
# 인덱스 비트 배치 (블록 면을 정면에서 봤을 때):
#     128  64  32
#       1   *  16
#       2   4   8
NEIGHBOR_MAP = [
    0, 3, 0, 3, 12, 5, 12, 15, 0, 3, 0, 3, 12, 5, 12, 15,
    1, 2, 1, 2, 4, 7, 4, 29, 1, 2, 1, 2, 13, 31, 13, 14,
    0, 3, 0, 3, 12, 5, 12, 15, 0, 3, 0, 3, 12, 5, 12, 15,
    1, 2, 1, 2, 4, 7, 4, 29, 1, 2, 1, 2, 13, 31, 13, 14,
    36, 17, 36, 17, 24, 19, 24, 43, 36, 17, 36, 17, 24, 19, 24, 43,
    16, 18, 16, 18, 6, 46, 6, 21, 16, 18, 16, 18, 28, 9, 28, 22,
    36, 17, 36, 17, 24, 19, 24, 43, 36, 17, 36, 17, 24, 19, 24, 43,
    37, 40, 37, 40, 30, 8, 30, 34, 37, 40, 37, 40, 25, 23, 25, 45,
    0, 3, 0, 3, 12, 5, 12, 15, 0, 3, 0, 3, 12, 5, 12, 15,
    1, 2, 1, 2, 4, 7, 4, 29, 1, 2, 1, 2, 13, 31, 13, 14,
    0, 3, 0, 3, 12, 5, 12, 15, 0, 3, 0, 3, 12, 5, 12, 15,
    1, 2, 1, 2, 4, 7, 4, 29, 1, 2, 1, 2, 13, 31, 13, 14,
    36, 39, 36, 39, 24, 41, 24, 27, 36, 39, 36, 39, 24, 41, 24, 27,
    16, 42, 16, 42, 6, 20, 6, 10, 16, 42, 16, 42, 28, 35, 28, 44,
    36, 39, 36, 39, 24, 41, 24, 27, 36, 39, 36, 39, 24, 41, 24, 27,
    37, 38, 37, 38, 30, 11, 30, 32, 37, 38, 37, 38, 25, 33, 25, 26,
]
assert len(NEIGHBOR_MAP) == 256
assert sorted(set(NEIGHBOR_MAP)) == list(range(47)), "47타일 전부가 쓰여야 정상"

BIT_LEFT, BIT_BL, BIT_BOTTOM, BIT_BR = 1, 2, 4, 8
BIT_RIGHT, BIT_TR, BIT_TOP, BIT_TL = 16, 32, 64, 128

EDGES = {"left": BIT_LEFT, "right": BIT_RIGHT, "top": BIT_TOP, "bottom": BIT_BOTTOM}
# 모서리 → (인접한 변 2개, 대각 비트)
CORNERS = {
    "tl": (("left", "top"), BIT_TL),
    "tr": (("right", "top"), BIT_TR),
    "bl": (("left", "bottom"), BIT_BL),
    "br": (("right", "bottom"), BIT_BR),
}
CORNER_XY = {"tl": (0, 0), "tr": (-1, 0), "bl": (0, -1), "br": (-1, -1)}  # -1 = 마지막 픽셀

# 이웃 방향 → 비트 (타일 선택 흉내내기·검산 공용). 화면 좌표계(y 아래로 증가).
NEIGHBOR_BITS = (
    (-1, 0, BIT_LEFT), (-1, 1, BIT_BL), (0, 1, BIT_BOTTOM), (1, 1, BIT_BR),
    (1, 0, BIT_RIGHT), (1, -1, BIT_TR), (0, -1, BIT_TOP), (-1, -1, BIT_TL),
)


def tile_states() -> list[dict]:
    """neighborMap 을 역산해 타일 0~46 각각의 '연결 상태'를 뽑는다.

    같은 타일로 모이는 모든 이웃 마스크에서 값이 일정한 비트만 확정 상태로 본다.
    변이 끊긴 쪽의 대각 비트는 그림에 영향이 없어 값이 섞이는데(=don't-care), None 으로 둔다.
    """
    buckets: dict[int, list[int]] = {}
    for mask, tile in enumerate(NEIGHBOR_MAP):
        buckets.setdefault(tile, []).append(mask)

    states = []
    for tile in range(47):
        masks = buckets[tile]
        st: dict[str, bool | None] = {}
        for name, bit in EDGES.items():
            vals = {bool(m & bit) for m in masks}
            assert len(vals) == 1, f"타일 {tile} 의 {name} 변이 확정되지 않음"
            st[name] = vals.pop()
        for name, (adj, bit) in CORNERS.items():
            vals = {bool(m & bit) for m in masks}
            if len(vals) == 1:
                st[name] = vals.pop()
            else:
                # 대각이 섞인다 = 양 변 중 하나가 끊겼다 = 이 모서리는 어차피 윤곽선이 지나간다
                assert not (st[adj[0]] and st[adj[1]]), f"타일 {tile} 의 {name} 대각이 don't-care 인데 양 변이 붙어 있음"
                st[name] = None
        states.append(st)
    return states


def interior_fill(px, w: int, h: int):
    """테두리 링을 제외한 안쪽 픽셀의 최빈값 = 유리의 '속살' 색.

    맑은 유리면 (0,0,0,0) 이라 이음선이 완전히 사라지고, 색유리면 낮은 알파의 색이라
    링만 지워지고 색은 남는다. 스크래치(대각 하이라이트)는 최빈값이 아니라 안 골라진다.
    """
    counts = Counter(px[x, y] for y in range(1, h - 1) for x in range(1, w - 1))
    return counts.most_common(1)[0][0]


def build_tile(src: Image.Image, state: dict) -> Image.Image:
    """타일 한 장. 붙은 변은 지우고, 끊긴 변엔 바닐라 테두리를 남기고, 안쪽 모서리는 1px 로 잇는다."""
    w, h = src.size
    sp = src.load()
    fill = interior_fill(sp, w, h)

    out = src.copy()
    op = out.load()

    def open_edge(name: str) -> bool:
        """이웃이 유리가 아니다 = 여기에 윤곽선을 그린다."""
        return not state[name]

    # 변 — 모서리 픽셀은 아래에서 따로 판정하므로 여기선 제외한다
    for y in range(1, h - 1):
        op[0, y] = sp[0, y] if open_edge("left") else fill
        op[w - 1, y] = sp[w - 1, y] if open_edge("right") else fill
    for x in range(1, w - 1):
        op[x, 0] = sp[x, 0] if open_edge("top") else fill
        op[x, h - 1] = sp[x, h - 1] if open_edge("bottom") else fill

    # 모서리
    for name, (adj, _) in CORNERS.items():
        x, y = CORNER_XY[name]
        x = x % w
        y = y % h
        if open_edge(adj[0]) or open_edge(adj[1]):
            op[x, y] = sp[x, y]           # 바깥 모서리 — 윤곽선 두 줄이 만나는 자리
        elif state[name] is False:
            op[x, y] = sp[x, y]           # ★안쪽 모서리 — 대각만 빈 곳. 1px 로 윤곽선을 이어 준다
        else:
            op[x, y] = fill               # 사방이 유리 → 완전히 매끈
    return out


def write_properties(path: Path, match_blocks: str) -> None:
    path.write_text(
        "# 자동 생성물 — tools/build_connected_glass.py 가 만든다. 손으로 고치지 말 것.\n"
        "method=ctm\n"
        "tiles=0-46\n"
        f"matchBlocks={match_blocks}\n"
        "connect=block\n",
        encoding="utf-8",
    )


def load_sources(jar: Path) -> dict[str, Image.Image]:
    """바닐라 원본을 매번 jar 에서 다시 읽는다 (사본 고정 금지)."""
    src: dict[str, Image.Image] = {}
    with zipfile.ZipFile(jar) as z:
        for name, _ in BLOCKS:
            with z.open(f"assets/minecraft/textures/block/{name}.png") as f:
                src[name] = Image.open(f).convert("RGBA")
    return src


def tile_for(wall: set[tuple[int, int]], cx: int, cy: int) -> int:
    """옵티파인이 고를 타일 번호를 그대로 흉내낸다 (검산·프리뷰 공용)."""
    bits = 0
    for dx, dy, bit in NEIGHBOR_BITS:
        if (cx + dx, cy + dy) in wall:
            bits |= bit
    return NEIGHBOR_MAP[bits]


# ── 자동 검산 ──────────────────────────────────────────────────────────────
def check_bit_layout() -> list[str]:
    """비트 배치(1=왼쪽, 2=좌하, 4=아래 …)가 표와 정말 맞는지 구조로 검산한다.

    8방향 라벨을 8! 가지로 뒤섞어 tile_states() 의 구조 조건(변 4개는 항상 확정,
    대각이 don't-care 면 인접 변 중 하나는 끊겨 있음)을 걸어 본다. 통과하는 건
    **정확히 8가지 = 정사각형의 대칭(회전4 x 거울2)** 뿐이고 우리 라벨링이 그중 하나다.
    즉 표는 전역 회전/거울 하나까지만 모호하며, 그리기 규칙은 그 대칭에 불변이라
    어느 쪽을 골라도 결과가 같다. 이 개수가 8이 아니면 표나 비트 상수가 깨진 것이다.
    """
    import itertools

    dirs = ["left", "bl", "bottom", "br", "right", "tr", "top", "tl"]
    bits = [1, 2, 4, 8, 16, 32, 64, 128]
    buckets: dict[int, list[int]] = {}
    for mask, tile in enumerate(NEIGHBOR_MAP):
        buckets.setdefault(tile, []).append(mask)

    def survives(perm) -> bool:
        lab = dict(zip(perm, bits))
        edge_bits = {e: lab[e] for e in ("left", "right", "top", "bottom")}
        corner_bits = {"tl": (("left", "top"), lab["tl"]), "tr": (("right", "top"), lab["tr"]),
                       "bl": (("left", "bottom"), lab["bl"]), "br": (("right", "bottom"), lab["br"])}
        for tile in range(47):
            masks = buckets[tile]
            st = {}
            for name, bit in edge_bits.items():
                vals = {bool(mm & bit) for mm in masks}
                if len(vals) != 1:
                    return False
                st[name] = vals.pop()
            for name, (adj, bit) in corner_bits.items():
                vals = {bool(mm & bit) for mm in masks}
                if len(vals) != 1 and st[adj[0]] and st[adj[1]]:
                    return False
        return True

    ok = [p for p in itertools.permutations(dirs) if survives(p)]
    problems = []
    if len(ok) != 8:
        problems.append(f"비트 배치 후보가 {len(ok)}개 (정사각형 대칭 8개여야 정상) — 표가 깨졌다")
    if tuple(dirs) not in ok:
        problems.append("우리 비트 상수가 후보에 없다 — BIT_* 값이 표와 안 맞는다")
    return problems


CHECK_SHAPES = {
    "1칸": {(0, 0)},
    "3x3": {(x, y) for x in range(3) for y in range(3)},
    "가로줄": {(x, 0) for x in range(4)},
    "세로줄": {(0, y) for y in range(4)},
    # 참고 이미지의 ㄱ자 노치 — 안쪽 모서리가 두 번 꺾인다
    "ㄱ자노치": {(0, 0), (1, 0), (2, 0), (0, 1), (0, 2), (1, 2), (2, 2), (2, 1)} - {(1, 1)},
    "대각접합": {(0, 0), (1, 1)},
    "계단": {(0, 0), (1, 0), (1, 1), (2, 1), (2, 2)},
}


def check(src: dict[str, Image.Image], states: list[dict]) -> int:
    """규칙이 실제 픽셀로 지켜졌는지 기계로 검산. 육안 대조 전에 이걸 통과해야 한다."""
    fails: list[str] = check_bit_layout()

    for name in ("glass", "lime_stained_glass", "tinted_glass"):
        base = src[name]
        w, h = base.size
        bp = base.load()
        fill = interior_fill(bp, w, h)
        tiles = [build_tile(base, st) for st in states]

        # ① 외톨이 블록은 바닐라와 완전히 같아야 한다 (연결 유리는 '지우기'만 해야 한다)
        lone = tiles[NEIGHBOR_MAP[0]]
        if lone.tobytes() != base.tobytes():
            fails.append(f"{name}: 외톨이 타일이 바닐라와 다르다")

        # ② 사방이 유리면 링에 테두리가 한 픽셀도 남으면 안 된다
        full = tiles[NEIGHBOR_MAP[255]].load()
        ring = ([(x, 0) for x in range(w)] + [(x, h - 1) for x in range(w)]
                + [(0, y) for y in range(h)] + [(w - 1, y) for y in range(h)])
        leftover = [(x, y) for x, y in ring if full[x, y] != fill]
        if leftover:
            fails.append(f"{name}: 사방연결 타일에 테두리 잔재 {len(leftover)}px {leftover[:4]}")

        # ③ 모양별 — 붙은 경계엔 선이 없고, 열린 경계엔 선이 꽉 차고, 대각은 이어져야 한다
        for shape_name, shape in CHECK_SHAPES.items():
            def px_of(cell, x, y):
                return tiles[tile_for(shape, *cell)].load()[x, y]

            def is_border(cell, x, y):
                return px_of(cell, x, y) != fill

            for (gx, gy) in sorted(shape):
                # 붙은 변: 이음선이 남아 있으면 실패
                for dx, dy, edge in ((-1, 0, "left"), (1, 0, "right"), (0, -1, "top"), (0, 1, "bottom")):
                    nb = (gx + dx, gy + dy)
                    line = ([(x, 0) for x in range(1, w - 1)] if edge == "top" else
                            [(x, h - 1) for x in range(1, w - 1)] if edge == "bottom" else
                            [(0, y) for y in range(1, h - 1)] if edge == "left" else
                            [(w - 1, y) for y in range(1, h - 1)])
                    marks = [p for p in line if is_border((gx, gy), *p)]
                    if nb in shape and marks:
                        fails.append(f"{name}/{shape_name} {(gx, gy)}: {edge} 이음선 {len(marks)}px 잔존")
                    if nb not in shape and len(marks) != len(line):
                        fails.append(f"{name}/{shape_name} {(gx, gy)}: {edge} 윤곽선 구멍 "
                                     f"{len(line) - len(marks)}px")
                # 안쪽 모서리: 양 변은 붙었는데 대각이 비면 1px 이 있어야 한다
                for cname, (adj, _) in CORNERS.items():
                    ddx = -1 if "l" in cname[1] else 1
                    ddy = -1 if cname[0] == "t" else 1
                    both = (gx + ddx, gy) in shape and (gx, gy + ddy) in shape
                    diag = (gx + ddx, gy + ddy) in shape
                    cx, cy = CORNER_XY[cname]
                    got = is_border((gx, gy), cx % w, cy % h)
                    if both and not diag and not got:
                        fails.append(f"{name}/{shape_name} {(gx, gy)}: {cname} 안쪽 모서리 1px 누락 "
                                     f"(윤곽선이 대각으로 끊긴다)")
                    if both and diag and got:
                        fails.append(f"{name}/{shape_name} {(gx, gy)}: {cname} 사방 유리인데 점이 남음")

    for f in fails:
        print("  ✗ " + f)
    print(f"검산 {'실패' if fails else '통과'} — 문제 {len(fails)}건 "
          f"(비트배치 + 모양 {len(CHECK_SHAPES)}종 × 유리 3종)")
    return 1 if fails else 0


# ── 오프라인 육안 대조 렌더 ────────────────────────────────────────────────
def render_preview(src, states, out_path: Path) -> None:
    """모양별로 '바닐라 | 연결' 2열을 나란히. 유리 뒤가 보이도록 체크 배경을 깐다."""
    scale = 10
    span = 4                                   # 모양이 들어갈 격자 크기(칸)
    names = ["glass", "lime_stained_glass", "tinted_glass"]
    shapes = list(CHECK_SHAPES.items())
    cell = span * 16 * scale
    pad, label_h = 12, 22

    cols = 2 * len(shapes)
    canvas = Image.new("RGBA",
                       (cols * (cell + pad) + pad, len(names) * (cell + pad) + pad + label_h),
                       (24, 26, 30, 255))
    bg = Image.new("RGBA", (cell, cell), (0, 0, 0, 0))
    bp = bg.load()
    for y in range(cell):
        for x in range(cell):
            bp[x, y] = (96, 104, 120, 255) if ((x // 20) + (y // 20)) % 2 else (58, 64, 76, 255)

    from PIL import ImageDraw
    draw = ImageDraw.Draw(canvas)

    for r, name in enumerate(names):
        c = 0
        for shape_name, shape in shapes:
            for mode in ("바닐라", "연결"):
                layer = Image.new("RGBA", (cell, cell), (0, 0, 0, 0))
                for (gx, gy) in shape:
                    img = (src[name] if mode == "바닐라"
                           else build_tile(src[name], states[tile_for(shape, gx, gy)]))
                    img = img.resize((16 * scale, 16 * scale), Image.NEAREST)
                    layer.alpha_composite(img, ((gx + 1) * 16 * scale, (gy + 1) * 16 * scale))
                composed = bg.copy()
                composed.alpha_composite(layer)
                ox, oy = pad + c * (cell + pad), pad + label_h + r * (cell + pad)
                canvas.alpha_composite(composed, (ox, oy))
                if r == 0:
                    draw.text((ox + 4, pad + 4), f"{shape_name} / {mode}", fill=(220, 226, 236, 255))
                c += 1
    canvas.save(out_path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", type=Path, default=DEFAULT_JAR, help="바닐라 클라이언트 jar")
    ap.add_argument("--check", action="store_true", help="규칙 자동 검산만 하고 끝")
    ap.add_argument("--preview", type=Path, help="검증용 렌더를 이 경로에 저장하고 끝")
    args = ap.parse_args()

    if not args.jar.exists():
        print(f"클라이언트 jar 없음: {args.jar}", file=sys.stderr)
        return 1

    src = load_sources(args.jar)
    states = tile_states()

    if args.check:
        return check(src, states)
    if args.preview:
        render_preview(src, states, args.preview)
        print(f"검증 렌더: {args.preview}")
        return 0

    if check(src, states) != 0:
        print("검산 실패 — 생성 중단", file=sys.stderr)
        return 1

    if CTM_DIR.exists():
        shutil.rmtree(CTM_DIR)              # 낡은 타일이 남아 섞이지 않게
    CTM_DIR.mkdir(parents=True, exist_ok=True)

    n_tile = 0
    for folder, match, tex in [(n, m, n) for n, m in BLOCKS] + PANES:
        d = CTM_DIR / folder
        d.mkdir(parents=True, exist_ok=True)
        write_properties(d / "ctm.properties", match)
        for i, st in enumerate(states):
            build_tile(src[tex], st).save(d / f"{i}.png")
            n_tile += 1

    print(f"CTM 타일 {n_tile}개 ({len(BLOCKS) + len(PANES)}세트) 생성 → {CTM_DIR}")
    print("바닐라 텍스처(textures/block)는 건드리지 않음 — CTM 미지원 클라는 바닐라 유리 그대로.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
