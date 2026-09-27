#!/usr/bin/env python3
"""짚라인 밧줄 «구운» 모델 생성기 — 줄 한 토막 = ItemDisplay 1개.

예전 밧줄은 1블록마다 체인 BlockDisplay 를 하나씩 세웠다(prod 6줄 535블록 ≈ 엔티티 540개). 엔티티 추적
비용은 «엔티티 수 × 근처 플레이어 수» 라, 줄을 토막(≤48블록)당 엔티티 1개로 바꾼다. 도개교 발판을
ItemDisplay 1개로 구운 것(bake_drawbridge.py)과 같은 발상이다.

원리: 체인 고리 K개가 모델 Y 축(-16→32, 48 유닛)을 따라 이어진 모델을 K 별로 미리 만든다. 플러그인
(ZiplineManager)은 토막 길이 L 에 맞는 K = round(L / 1블록) 모델을 고르고, 디스플레이를 밧줄 방향으로 돌린 뒤
Y 축만 L/3 배 늘린다(단면은 그대로). 그래서 고리 하나가 늘 약 1블록이고 두께도 바닐라 체인(3px)과 같다.

모양: 바닐라 체인은 평면 두 장을 X 자로 겹친 모델이지만, 우리 자산은 평면 교차를 쓰지 않는다(부피 규칙).
그래서 3×3px 단면의 박스로 굽는다 — 앞·뒤 면에는 고리를 정면에서 본 열(UV 0-3), 옆면에는 옆에서 본
열(UV 3-6)을 입혀 바닐라 체인과 같은 인상을 부피로 낸다. 텍스처는 1.21.11 클라이언트의 iron_chain 을
barkan 네임스페이스로 벤더링한 것(바닐라 텍스처 직접 참조는 체커보드 사고가 있었다).

산출물(매번 전부 다시 쓴다 — 손편집 금지):
  assets/barkan/models/zipline/rope_<K>.json
  assets/barkan/items/zipline/rope_<K>.json
K = 1..MAX_K. MAX_K 는 플러그인의 ROPE_MODEL_MAX_K 와 같아야 한다.
"""
import json
import os
import sys

MAX_K = 64
Y0, Y1 = -16.0, 32.0          # 모델 공간에서 밧줄이 차지하는 Y 범위(48 유닛 = 3블록)
LO, HI = 6.5, 9.5              # 단면 3px (바닐라 체인 폭)
TEX = "barkan:item/zipline/iron_chain"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(ROOT, "assets", "barkan", "models", "zipline")
ITEM_DIR = os.path.join(ROOT, "assets", "barkan", "items", "zipline")


def r(v: float) -> float:
    return round(v, 4)


def model(k: int) -> dict:
    step = (Y1 - Y0) / k
    elements = []
    for i in range(k):
        y0 = Y0 + step * i
        y1 = y0 + step
        faces = {
            "north": {"uv": [3, 0, 0, 16], "texture": "#chain"},
            "south": {"uv": [0, 0, 3, 16], "texture": "#chain"},
            "west": {"uv": [6, 0, 3, 16], "texture": "#chain"},
            "east": {"uv": [3, 0, 6, 16], "texture": "#chain"},
        }
        # 끝마개 — 중간 이음새는 서로 가려서 필요 없다.
        if i == 0:
            faces["down"] = {"uv": [0, 0, 3, 3], "texture": "#chain"}
        if i == k - 1:
            faces["up"] = {"uv": [0, 0, 3, 3], "texture": "#chain"}
        elements.append({
            "from": [LO, r(y0), LO],
            "to": [HI, r(y1), HI],
            "shade": False,
            "faces": faces,
        })
    return {
        "textures": {"chain": TEX, "particle": TEX},
        "elements": elements,
    }


def main() -> int:
    tex = os.path.join(ROOT, "assets", "barkan", "textures", "item", "zipline", "iron_chain.png")
    if not os.path.isfile(tex):
        print(f"텍스처 없음: {tex}", file=sys.stderr)
        return 2
    os.makedirs(MODEL_DIR, exist_ok=True)
    os.makedirs(ITEM_DIR, exist_ok=True)
    # 옛 산출물 정리(MAX_K 를 줄였을 때 남는 파일이 없게)
    for d in (MODEL_DIR, ITEM_DIR):
        for f in os.listdir(d):
            if f.startswith("rope_") and f.endswith(".json"):
                os.remove(os.path.join(d, f))
    for k in range(1, MAX_K + 1):
        with open(os.path.join(MODEL_DIR, f"rope_{k}.json"), "w", encoding="utf-8") as fh:
            json.dump(model(k), fh, separators=(",", ":"))
        with open(os.path.join(ITEM_DIR, f"rope_{k}.json"), "w", encoding="utf-8") as fh:
            json.dump({"model": {"type": "minecraft:model", "model": f"barkan:zipline/rope_{k}"}}, fh,
                      separators=(",", ":"))
    print(f"짚라인 밧줄 모델 {MAX_K}종 생성 → {os.path.relpath(MODEL_DIR, ROOT)}, {os.path.relpath(ITEM_DIR, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
