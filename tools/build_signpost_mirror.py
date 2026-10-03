#!/usr/bin/env python3
"""이정표 모델의 파생형 — 양갈래(harbor_signpost_fork)와 좌우반전(harbor_signpost_*_mirror) — 을 원본에서 생성한다.

양갈래: 삼거리(junction)에서 직진 팻말(forward_board)을 빼고, 우·좌 팻말을 FORK_LIFT 만큼 올려
우 팻말이 직진 팻말 자리(y 25~30)에 오게 한다. ★BlockShip `nav/SignpostPanels.FORK` 판면 높이와 짝이다.

왜: 팻말이 기둥 한쪽에만 붙어 있어서, 길 쪽에서 보면 기둥에 가려진 뒷면이 보인다.
BlockShip 이정표(`nav/SignpostManager`)가 `mirror` 설정이면 이 모델을 쓴다(OP 기둥 웅크리고 우클릭).
디스플레이 scale −1 로 뒤집으면 면 감기가 반대라 컬링으로 속이 드러나므로 모델을 따로 굽는다.

★원본(harbor_signpost_straight/junction.json)을 고치면 이 스크립트를 다시 돌릴 것 — 결과물을 손편집하지 말 것.
변환: x → 16−x (from/to 교환), east↔west 면 교환, 모든 면 u 반전(거울상 텍스처).
요소·면 회전은 원본에 없다 — 생기면 여기서 멈추게 해 두었다.
"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent / "assets" / "barkan"
MODELS = ROOT / "models" / "item" / "furniture" / "signposts"
ITEMS = ROOT / "items"

def mirror(model):
    out = json.loads(json.dumps(model))
    out.pop("display", None)  # ItemDisplay FIXED 는 display 없음 — 손·GUI 변환은 원본 아이템이 맡는다
    for e in out["elements"]:
        if e.get("rotation"):
            sys.exit(f"요소 회전 미지원: {e.get('name')}")
        f, t = e["from"], e["to"]
        e["from"], e["to"] = [16 - t[0], f[1], f[2]], [16 - f[0], t[1], t[2]]
        faces = {}
        for k, v in e["faces"].items():
            if v.get("rotation"):
                sys.exit(f"면 UV 회전 미지원: {e.get('name')}.{k}")
            v = dict(v)
            u0, v0, u1, v1 = v["uv"]
            v["uv"] = [u1, v0, u0, v1]
            faces[{"east": "west", "west": "east"}.get(k, k)] = v
        e["faces"] = faces
    return out

FORK_LIFT = 6.5

def fork(junction):
    out = json.loads(json.dumps(junction))
    groups = {g["name"]: g["children"] for g in out.get("groups", [])}
    drop = set(groups["forward_board"])
    lift = set(groups["right_board"]) | set(groups["left_board"])
    elements = []
    for i, e in enumerate(out["elements"]):
        if i in drop:
            continue
        if i in lift:
            e["from"][1] += FORK_LIFT
            e["to"][1] += FORK_LIFT
        elements.append(e)
    out["elements"] = elements
    out.pop("groups", None)  # 요소 인덱스가 바뀌어 Blockbench 그룹이 어긋난다 — 게임은 안 쓴다
    return out

def write_item(name, gui_icon=None):
    model = {"type": "minecraft:model", "model": f"barkan:item/furniture/signposts/{name}"}
    if gui_icon:
        model = {"type": "minecraft:select", "property": "minecraft:display_context",
                 "cases": [{"when": "gui", "model": {"type": "minecraft:model",
                            "model": f"barkan:item/furniture/signposts/icon/{gui_icon}"}}],
                 "fallback": model}
    (ITEMS / f"{name}.json").write_text(json.dumps({"model": model}, indent=2) + "\n", encoding="utf-8")

junction = json.loads((MODELS / "harbor_signpost_junction.json").read_text(encoding="utf-8"))
(MODELS / "harbor_signpost_fork.json").write_text(json.dumps(fork(junction), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
write_item("harbor_signpost_fork", gui_icon="harbor_signpost_junction")
print("wrote harbor_signpost_fork")

for kind in ("straight", "junction", "fork"):
    src = json.loads((MODELS / f"harbor_signpost_{kind}.json").read_text(encoding="utf-8"))
    name = f"harbor_signpost_{kind}_mirror"
    (MODELS / f"{name}.json").write_text(json.dumps(mirror(src), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_item(name)
    print("wrote", name)
